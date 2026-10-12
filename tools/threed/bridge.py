"""Bridge family generator: one `BridgeParams` per bridge tier.

A bridge tier is a small set of structural parts with per-tier
dimensions and materials, composed by one builder for every sheet
entry the engine reads (`descriptor/writer/bridge_writer.cc`):
segments and pillars on the 3 hex way axes, ramps / starts / start2 on
the 6 hex edges, each split into Back and Front layers by the engine's
depth-clip plane (`HEX_DEPTH_CLIP_NORMAL`).  The per-tier instances
live next to the assets (`infrastructure/rail_bridges/rail_bridge_params.py`);
this module holds the parts, the orientation frames and the bake.

Parts, emitted in this order (the order is the z-buffer tie-break, so
it is part of the output):

    deck     the slab the way lies on (`Deck`).
    support  what carries the deck down to the ground, under it
             (`Trestle` timber bents, ...); optional.
    sides    what stands along both deck edges (`Railing`, ...).
    track    the way surface on the deck top, supplied by the way
             family (`OpenTieTrack` from a rail tier's `RailParams`; a
             road deck would supply its carriageway the same way).
    pillar   the separate pillar cell the engine stacks under long
             spans every `pillar_distance` tiles (`BoxPillar`, ...).

Every part builds in a canonical NS frame — length along world y over
`[-length_half, +length_half]`, width along x — and emits boxes through
an `add` callback that rotates them onto the target axis or edge
(`Orient`) and tags each quad Back or Front.  A part implements
`segment(add, length_half, deck)` for the mid-span tile and
`end(add, length_half, profile, deck)` for ramps and starts, whose deck
height varies along the tile (`EndProfile`).

Shared heights.  Every bridge deck top sits at `DECK_TOP_Z` so a slow
bridge upgraded to a fast one doesn't tilt (CLAUDE.md, "Heights shared
across variants"); per-tier geometry hangs off it.  The end profiles
(ramp foot, start / start2 support depth) are family constants too.
The z=0 anchors of the two cameras were calibrated on rail_060
against pak128 (`_SQ_CAMERA`, `_HEX_CAMERA`).

Bridge length.  The chord between two opposite tile edges is 1.0 in
square and √3 in hex once world units match the entry edge
(`tools/threed/way.py::HEX_TILE_RADIUS`), hence the explicit
`length_half` per projection (TODO.md, "rail_060_bridge bypasses
way_topology").
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import numpy as np
from PIL import Image

from tools.threed.bespoke import bake_atlas
from tools.threed.hex_synth import (
    HEX_DEPTH_CLIP_NORMAL,
    NE_SW as HEX_NE_SW,
    NS as HEX_NS,
    NW_SE as HEX_NW_SE,
)
from tools.threed.render import HexCamera, Model, SquareCamera, render

RGB = tuple[int, int, int]

# --- Family constants -------------------------------------------------------

# Deck top, shared by every tier.
DECK_TOP_Z = 0.13

BRIDGE_LEN_HALF_SQUARE = 0.5
BRIDGE_LEN_HALF_HEX = math.sqrt(3.0) / 2.0


def length_half(projection: str) -> float:
    return BRIDGE_LEN_HALF_HEX if projection == "hex" else BRIDGE_LEN_HALF_SQUARE


# End profiles (first-pass values from rail_060, TODO.md "end-entry
# calibration"): a ramp's deck bottom climbs from `RAMP_FOOT_Z` at the
# landward end to the tier's deck bottom at the bridge end; a start's
# supports reach down to `START_SUPPORT_Z`, start2's (the double-height
# start) to `START2_SUPPORT_Z`.
RAMP_FOOT_Z = 0.015
START_SUPPORT_Z = -0.10
START2_SUPPORT_Z = -0.24
# Ramp and deck run are cut into this many flat steps.
END_STEPS = 10


# --- Orientation = (rotation around z, depth-clip-plane front normal) -----
# A bridge orientation is fully described by two facts: how to rotate
# the canonical NS-frame geometry so it lies along the target axis, and
# which world half-plane is "front" (the FrontImage layer).
#
# Square pak128 axes use the legacy compositing convention (NS:
# front=+x, EW: front=-y); hex axes pull `n` from the engine spec
# `display/hex_proj.h::HEX_DEPTH_CLIP_NORMAL`.  Hex way axes pair
# opposite edges (`NE_SW = NE edge ↔ SW edge`), so the rotations
# (0° / -60° / -120°) land world +y on the edge-midpoint axis line; `n`
# is then perpendicular to the bridge length, which makes the
# front/back split a clean perpendicular offset (constant `n·p` along a
# side rail — no mid-bar layer flips).

@dataclass(frozen=True)
class Orient:
    rot_deg: float
    front_normal: tuple[float, float]


ORIENT_NS    = Orient(   0.0, HEX_DEPTH_CLIP_NORMAL[HEX_NS])     # square + hex
ORIENT_EW    = Orient( -90.0, (0.0, -1.0))                       # square only
ORIENT_NE_SW = Orient( -60.0, HEX_DEPTH_CLIP_NORMAL[HEX_NE_SW])  # hex only
ORIENT_NW_SE = Orient(-120.0, HEX_DEPTH_CLIP_NORMAL[HEX_NW_SE])  # hex only

# End tiles: canonical +y points at the bridge edge the key names.
ORIENT_SQUARE_EDGE = {
    "N": Orient(0.0, ORIENT_NS.front_normal),
    "S": Orient(180.0, ORIENT_NS.front_normal),
    "E": Orient(-90.0, ORIENT_EW.front_normal),
    "W": Orient(90.0, ORIENT_EW.front_normal),
}

ORIENT_HEX_EDGE = {
    "n":  Orient(0.0, HEX_DEPTH_CLIP_NORMAL[HEX_NS]),
    "s":  Orient(180.0, HEX_DEPTH_CLIP_NORMAL[HEX_NS]),
    "ne": Orient(-60.0, HEX_DEPTH_CLIP_NORMAL[HEX_NE_SW]),
    "sw": Orient(120.0, HEX_DEPTH_CLIP_NORMAL[HEX_NE_SW]),
    "se": Orient(-120.0, HEX_DEPTH_CLIP_NORMAL[HEX_NW_SE]),
    "nw": Orient(60.0, HEX_DEPTH_CLIP_NORMAL[HEX_NW_SE]),
}

HEX_AXES = (("n_s", ORIENT_NS), ("ne_sw", ORIENT_NE_SW), ("nw_se", ORIENT_NW_SE))
HEX_EDGES = ("n", "s", "ne", "se", "sw", "nw")


def _add_oriented_box(model: Model, orient: Orient,
                      along_lo: float, along_hi: float,
                      side_lo: float, side_hi: float,
                      z_lo: float, z_hi: float, color,
                      force_layer: str | None = None,
                      dither_keep: float = 1.0) -> None:
    """Append a box in NS-frame coordinates (along = world y, side =
    world x), rotated by `orient.rot_deg` around z, emitted as 5
    outward-facing quads (skips the bottom, like `Model.add_box`).
    Layer is `force_layer` when set, else per-quad-centroid via
    `n · centroid > 0` against `orient.front_normal`.

    Rotated boxes go through `add_quad` instead of `add_box` because
    the rasterizer expects axis-aligned extents in `add_box`; the
    per-face vertex order matches `add_box`'s outward-CCW convention
    so face shading lands the same way for square and hex output.
    """
    a = math.radians(orient.rot_deg)
    ca, sa = math.cos(a), math.sin(a)

    def rot(x, y, z):
        return (ca * x - sa * y, sa * x + ca * y, z)

    c = [
        rot(side_lo, along_lo, z_lo), rot(side_hi, along_lo, z_lo),
        rot(side_hi, along_hi, z_lo), rot(side_lo, along_hi, z_lo),
        rot(side_lo, along_lo, z_hi), rot(side_hi, along_lo, z_hi),
        rot(side_hi, along_hi, z_hi), rot(side_lo, along_hi, z_hi),
    ]
    quads = (
        (c[4], c[5], c[6], c[7]),  # top
        (c[0], c[1], c[5], c[4]),  # -y face
        (c[2], c[3], c[7], c[6]),  # +y face
        (c[1], c[2], c[6], c[5]),  # +x face
        (c[0], c[4], c[7], c[3]),  # -x face
    )
    nx, ny = orient.front_normal
    for q in quads:
        if force_layer is not None:
            layer = force_layer
        else:
            cx = sum(p[0] for p in q) / 4.0
            cy = sum(p[1] for p in q) / 4.0
            layer = "front" if nx * cx + ny * cy > 0.0 else "back"
        model.add_quad(q, color, layer=layer, dither_keep=dither_keep)


AddBox = Callable[..., None]


def _steps(length_half: float, n: int):
    """`(a0, a1, amid)` of `n` equal steps over the bridge length."""
    for i in range(n):
        a0 = -length_half + (i / n) * 2 * length_half
        a1 = -length_half + ((i + 1) / n) * 2 * length_half
        yield a0, a1, (a0 + a1) / 2.0


# --- End profile ------------------------------------------------------------

@dataclass(frozen=True)
class EndProfile:
    """Deck height along a ramp / start / start2 tile.  Canonical +along
    points at the bridge edge named by the entry (`n`, `ne`, ...);
    `-length_half` is the landward end."""
    kind: str            # "ramp" | "start" | "start2"
    deck_bottom_z: float  # the tier's mid-span deck bottom
    length_half: float

    def at(self, along: float) -> tuple[float, float]:
        """`(deck_bottom, support_bottom)` at `along`."""
        if self.kind == "ramp":
            t = (along + self.length_half) / (2.0 * self.length_half)
            deck_bottom = RAMP_FOOT_Z + t * (self.deck_bottom_z - RAMP_FOOT_Z)
            return deck_bottom, 0.0
        if self.kind == "start2":
            return self.deck_bottom_z, START2_SUPPORT_Z
        if self.kind == "start":
            return self.deck_bottom_z, START_SUPPORT_Z
        raise ValueError(f"unknown bridge end kind: {self.kind}")

    def deck_top(self, along: float) -> float:
        deck_bottom, _support = self.at(along)
        return deck_bottom + (DECK_TOP_Z - self.deck_bottom_z)


# --- Parts ------------------------------------------------------------------

class Part(Protocol):
    def segment(self, add: AddBox, length_half: float, deck: "Deck") -> None: ...
    def end(self, add: AddBox, length_half: float, profile: EndProfile,
            deck: "Deck") -> None: ...


@dataclass(frozen=True)
class Deck:
    """Slab from `bottom_z` to `DECK_TOP_Z`, `half_w` either side of
    the axis.  Back layer: the vehicle draws on top of it."""
    half_w: float
    bottom_z: float
    color: RGB

    def segment(self, add, length_half, deck):
        add(-length_half, +length_half, -self.half_w, +self.half_w,
            self.bottom_z, DECK_TOP_Z, self.color, force_layer="back")

    def end(self, add, length_half, profile, deck):
        for a0, a1, amid in _steps(length_half, END_STEPS):
            deck_bottom, _support = profile.at(amid)
            add(a0, a1, -self.half_w, +self.half_w,
                deck_bottom, deck_bottom + (DECK_TOP_Z - self.bottom_z),
                self.color, force_layer="back")


@dataclass(frozen=True)
class Trestle:
    """Timber trestle: `n_panels + 1` square posts per deck edge from
    the ground (z=0) to the deck bottom, posts at both tile edges so
    the deck is supported to the boundary.  End tiles add a heavier
    bent at both ends and reach down to the profile's support depth;
    ramp posts are dropped where the deck is still within `min_post`
    of the ground.  All Back: the viewer-side trestle is part of the
    silhouette, not the FrontImage railing.

    X-bracing between the posts is not modelled (TODO.md, "X-bracing
    on rail_060_bridge")."""
    n_panels: int
    post_half: float
    color: RGB
    end_bent_half_along: float = 0.030
    end_bent_half_side: float = 0.024
    end_bent_overlap: float = 0.03
    min_post: float = 0.04

    def segment(self, add, length_half, deck):
        for i in range(self.n_panels + 1):
            along = -length_half + (i / self.n_panels) * 2 * length_half
            for side in (-deck.half_w, +deck.half_w):
                add(along - self.post_half, along + self.post_half,
                    side - self.post_half, side + self.post_half,
                    0.0, deck.bottom_z, self.color, force_layer="back")

    def end(self, add, length_half, profile, deck):
        for i in range(self.n_panels + 1):
            along = -length_half + (i / self.n_panels) * 2 * length_half
            deck_bottom, support_bottom = profile.at(along)
            if deck_bottom - support_bottom < self.min_post:
                continue
            for side in (-deck.half_w, +deck.half_w):
                add(along - self.post_half, along + self.post_half,
                    side - self.post_half, side + self.post_half,
                    support_bottom, deck_bottom, self.color,
                    force_layer="back")
        for along in (-length_half, +length_half):
            deck_bottom, support_bottom = profile.at(along)
            if profile.kind == "ramp" and along < 0:
                support_bottom = 0.0
            for side in (-deck.half_w, +deck.half_w):
                add(along - self.end_bent_half_along,
                    along + self.end_bent_half_along,
                    side - self.end_bent_half_side,
                    side + self.end_bent_half_side,
                    support_bottom, deck_bottom + self.end_bent_overlap,
                    self.color, force_layer="back")


@dataclass(frozen=True)
class Railing:
    """Post-and-rail fence along both deck edges: `n_posts` posts per
    side from the deck top to `top_z`, a top bar `top_bar` thick under
    `top_z` and a bottom bar straddling the deck edge.  Layer per quad,
    so the viewer-side railing lands in the Front slice."""
    n_posts: int
    top_z: float
    color: RGB
    post_half: float = 0.016
    bar_half: float = 0.012
    top_bar: float = 0.030
    bottom_bar_lo: float = 0.010   # below the deck top
    bottom_bar_hi: float = 0.020   # above the deck top

    def segment(self, add, length_half, deck):
        for i in range(self.n_posts):
            along = -length_half + ((i + 0.5) / self.n_posts) * 2 * length_half
            for side in (-deck.half_w, +deck.half_w):
                add(along - self.post_half, along + self.post_half,
                    side - self.post_half, side + self.post_half,
                    DECK_TOP_Z, self.top_z, self.color)
        for side in (-deck.half_w, +deck.half_w):
            add(-length_half, +length_half,
                side - self.bar_half, side + self.bar_half,
                self.top_z - self.top_bar, self.top_z, self.color)
            add(-length_half, +length_half,
                side - self.bar_half, side + self.bar_half,
                DECK_TOP_Z - self.bottom_bar_lo,
                DECK_TOP_Z + self.bottom_bar_hi, self.color)

    def end(self, add, length_half, profile, deck):
        height = self.top_z - DECK_TOP_Z
        for i in range(self.n_posts):
            along = -length_half + ((i + 0.5) / self.n_posts) * 2 * length_half
            deck_top = profile.deck_top(along)
            for side in (-deck.half_w, +deck.half_w):
                add(along - self.post_half, along + self.post_half,
                    side - self.post_half, side + self.post_half,
                    deck_top, deck_top + height, self.color)
        for a0, a1, amid in _steps(length_half, END_STEPS):
            deck_top = profile.deck_top(amid)
            for side in (-deck.half_w, +deck.half_w):
                add(a0, a1, side - self.bar_half, side + self.bar_half,
                    deck_top + height - self.top_bar, deck_top + height,
                    self.color)
                add(a0, a1, side - self.bar_half, side + self.bar_half,
                    deck_top - self.bottom_bar_lo,
                    deck_top + self.bottom_bar_hi, self.color)


@dataclass(frozen=True)
class OpenTieTrack:
    """Rail on an open deck: undithered cross-ties straight on the deck
    top, twin rails on them, no ballast.  Cross-section from the joining
    track tier (`rail_params.RailParams`) so the deck track lines up
    with the standalone track; tie count is the tier's `n_ties` across
    the bridge length, tie thickness along the track `tie_half_along`."""
    rail: object  # infrastructure.rail_tracks.rail_params.RailParams
    tie_half_along: float = 0.025

    def segment(self, add, length_half, deck):
        p = self.rail
        tie_thickness = p.tie_top_z - p.ballast_top_z
        rail_thickness = p.rail_top_z - p.tie_top_z
        tie_top_z = DECK_TOP_Z + tie_thickness
        for i in range(p.n_ties):
            along = -length_half + ((i + 0.5) / p.n_ties) * 2 * length_half
            add(along - self.tie_half_along, along + self.tie_half_along,
                -p.tie_half_w, +p.tie_half_w,
                DECK_TOP_Z, tie_top_z, p.tie_color, force_layer="back")
        rail_top_z = tie_top_z + rail_thickness
        for gauge_x in (-p.rail_gauge_half, +p.rail_gauge_half):
            add(-length_half, +length_half,
                gauge_x - p.rail_half_w, gauge_x + p.rail_half_w,
                tie_top_z, rail_top_z, p.rail_color, force_layer="back")

    def end(self, add, length_half, profile, deck):
        p = self.rail
        tie_thickness = p.tie_top_z - p.ballast_top_z
        rail_thickness = p.rail_top_z - p.tie_top_z
        rail_top_offset = tie_thickness + rail_thickness
        for i in range(p.n_ties):
            along = -length_half + ((i + 0.5) / p.n_ties) * 2 * length_half
            deck_top = profile.deck_top(along)
            add(along - self.tie_half_along, along + self.tie_half_along,
                -p.tie_half_w, +p.tie_half_w,
                deck_top, deck_top + tie_thickness, p.tie_color,
                force_layer="back")
        for gauge_x in (-p.rail_gauge_half, +p.rail_gauge_half):
            for a0, a1, amid in _steps(length_half, END_STEPS):
                deck_top = profile.deck_top(amid)
                add(a0, a1, gauge_x - p.rail_half_w, gauge_x + p.rail_half_w,
                    deck_top + tie_thickness, deck_top + rail_top_offset,
                    p.rail_color, force_layer="back")


@dataclass(frozen=True)
class BoxPillar:
    """Single column centred on the tile, `half_side` either side of
    the axis and `half_side * along_aspect` along it (aspect < 1 turns
    the broad face to the viewer), from `bottom_z` up to the deck
    bottom.  Back layer.  The cell ships the maximum-depth shape; the
    engine clips it against the gap floor at composite time."""
    half_side: float
    along_aspect: float
    bottom_z: float
    color: RGB

    def build(self, add, deck):
        along_half = self.half_side * self.along_aspect
        add(-along_half, +along_half, -self.half_side, +self.half_side,
            self.bottom_z, deck.bottom_z, self.color, force_layer="back")


# --- Tier ---------------------------------------------------------------------

@dataclass(frozen=True)
class BridgeParams:
    """One bridge tier: the structural parts above, with this tier's
    dimensions and materials.  `name` is the asset stem; the hex atlas
    is `<name>_hex.png` next to the tier's `.dat`."""
    name: str
    deck: Deck
    sides: tuple
    track: Part
    pillar: BoxPillar
    support: Part | None = None

    def parts(self) -> tuple:
        return ((self.deck,)
                + ((self.support,) if self.support is not None else ())
                + tuple(self.sides) + (self.track,))


def build_segment(model: Model, params: BridgeParams, orient: Orient,
                  length_half: float) -> None:
    add = functools.partial(_add_oriented_box, model, orient)
    for part in params.parts():
        part.segment(add, length_half, params.deck)


def build_end(model: Model, params: BridgeParams, orient: Orient, kind: str,
              length_half: float) -> None:
    add = functools.partial(_add_oriented_box, model, orient)
    profile = EndProfile(kind, params.deck.bottom_z, length_half)
    for part in params.parts():
        part.end(add, length_half, profile, params.deck)


def build_pillar(model: Model, params: BridgeParams, orient: Orient) -> None:
    params.pillar.build(functools.partial(_add_oriented_box, model, orient),
                        params.deck)


# --- Cameras and render -------------------------------------------------------

# Per-projection cameras, calibrated on rail_060 so the deck lands at
# the same composite screen-y in both — `ypos + 94` ≈ 2 px above the
# tile-centre, matching pak128's reference cells.  Square: dat `,0,32`
# shift adds 32 at composite time, so cell-anchor 74 + 32 = 106
# composite for z=0; deck at z=0.13 lands 11.77 px above z=0.  Hex: no
# dat shift, so the cell pixels carry the full offset — anchor 106 for
# z=0.
_SQ_CAMERA = SquareCamera(screen_center_y=74)
_HEX_CAMERA = HexCamera(anchor_y=106)


def camera(projection: str):
    return _HEX_CAMERA if projection == "hex" else _SQ_CAMERA


def render_segment(params: BridgeParams, orient: Orient, projection: str
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Render a mid-segment in `orient`; return `(back, front)`."""
    m = Model()
    build_segment(m, params, orient, length_half(projection))
    cam = camera(projection)
    return (render(m, cam, layer_filter="back"),
            render(m, cam, layer_filter="front"))


def render_pillar(params: BridgeParams, orient: Orient, projection: str
                  ) -> np.ndarray:
    """Render a pillar in `orient`; single-layer (back)."""
    m = Model()
    build_pillar(m, params, orient)
    return render(m, camera(projection), layer_filter="back")


def render_end(params: BridgeParams, orient: Orient, kind: str,
               projection: str) -> tuple[np.ndarray, np.ndarray]:
    """Render a ramp/start/start2 end; return `(back, front)`."""
    m = Model()
    build_end(m, params, orient, kind, length_half(projection))
    cam = camera(projection)
    return (render(m, cam, layer_filter="back"),
            render(m, cam, layer_filter="front"))


# --- Square verification renders --------------------------------------------

def square_outputs(params: BridgeParams):
    """`(out filename, render fn)` for every pak128 square sheet entry
    the scene models: NS / EW segments, S / W pillars, and ramp / start
    / start2 at N / S / E / W."""
    out = [
        ("out_back_ns.png",  lambda: render_segment(params, ORIENT_NS, "square")[0]),
        ("out_front_ns.png", lambda: render_segment(params, ORIENT_NS, "square")[1]),
        ("out_back_ew.png",  lambda: render_segment(params, ORIENT_EW, "square")[0]),
        ("out_front_ew.png", lambda: render_segment(params, ORIENT_EW, "square")[1]),
        ("out_pillar_s.png", lambda: render_pillar(params, ORIENT_NS, "square")),
        ("out_pillar_w.png", lambda: render_pillar(params, ORIENT_EW, "square")),
    ]
    for kind in ("ramp", "start", "start2"):
        for d in ("N", "S", "E", "W"):
            orient = ORIENT_SQUARE_EDGE[d]
            stem = f"{kind}_{d.lower()}"
            out.extend([
                (f"out_back_{stem}.png",
                 lambda orient=orient, kind=kind:
                     render_end(params, orient, kind, "square")[0]),
                (f"out_front_{stem}.png",
                 lambda orient=orient, kind=kind:
                     render_end(params, orient, kind, "square")[1]),
            ])
    return out


def write_square_outputs(params: BridgeParams, here: Path) -> None:
    for name, fn in square_outputs(params):
        Image.fromarray(fn(), mode="RGBA").save(here / name)


# --- Hex bake -----------------------------------------------------------------

# Atlas layout, shared by every tier's .dat: 9 cells a row, entries in
# this order (row-major).
HEX_COLS = 9


def hex_entries(params: BridgeParams) -> list[tuple[str, Callable]]:
    """`(dat key, render fn)` for every hex sheet entry, in atlas order:
    Back/Front segment per axis, the 3 pillars, then Back/Front ramp,
    start, start2 per edge."""
    entries: list[tuple[str, Callable]] = []
    for key, orient in HEX_AXES:
        entries.extend([
            (f"BackImage[{key}][0]",
             lambda o=orient: render_segment(params, o, "hex")[0]),
            (f"FrontImage[{key}][0]",
             lambda o=orient: render_segment(params, o, "hex")[1]),
        ])
    for key, orient in HEX_AXES:
        entries.append((f"backPillar[{key}][0]",
                        lambda o=orient: render_pillar(params, o, "hex")))
    for kind, dat_key in (("ramp", "Ramp"), ("start", "Start"),
                          ("start2", "Start2")):
        for edge in HEX_EDGES:
            orient = ORIENT_HEX_EDGE[edge]
            entries.extend([
                (f"Back{dat_key}[{edge}][0]",
                 lambda o=orient, k=kind: render_end(params, o, k, "hex")[0]),
                (f"Front{dat_key}[{edge}][0]",
                 lambda o=orient, k=kind: render_end(params, o, k, "hex")[1]),
            ])
    return entries


def bake_pakset(params: BridgeParams, out_dir: Path) -> None:
    bake_atlas(out_png=out_dir / f"{params.name}_hex.png",
               entries=hex_entries(params), cols_per_row=HEX_COLS)
