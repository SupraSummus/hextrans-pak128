"""3D model of the rail_060 timber rail bridge.

Reference: `infrastructure/rail_bridges/rail_060_bridge.png` + `.dat`.
The .dat enumerates 28 summer entries (× 2 seasons) — mid-segments for
the two square-dimetric axes, ramps and starts at each compass
direction, and two pillar variants — and the scene is built from
reusable 3D parts that compose for each.

Square and hex bakes run through one build path: `build_segment`
takes an `Orient` (rotation around z + depth-clip-plane front
normal), and the same scene re-renders through either projection.
The four orient values cover every sheet entry — square pak128
NS / EW for verification, hex NS / NE-SW / NW-SE for the engine-
side bake.  Per `display/hex_proj.h::hex_way_axis_t` the hex axes
pair OPPOSITE EDGES (e.g. NE_SW = NE edge ↔ SW edge), so the
chosen rotations (0° / -60° / -120°) land world +y on the
edge-midpoint axis line; `front_normal` for hex axes pulls from
the engine spec `HEX_DEPTH_CLIP_NORMAL`, for square axes it
encodes the legacy pak128 compositing convention.  Pak128 has no
NE-SW or NW-SE square sprites, so those two axes have no square
diff reference; the NS hex bake stays comparable to the pak128
NS sheet via `front_back_split(NS) ≡ cx > 0`.

Mid-segment layers:

    BackImage[NS|EW][0]   = the full silhouette: deck, ties, rails,
                            trestle, far-side railing.  Drawn behind
                            the way (vehicle is on top of it).
    FrontImage[NS|EW][0]  = just the viewer-side railing (posts +
                            top + bottom bar).  Drawn in front of the
                            vehicle.

The whole bridge is one 3D structure tagged per-quad with the layer
it belongs to (`"back"` vs `"front"`).  The renderer emits one PNG
per layer; `build.py` diffs each against the matching pak128 cell
(multi-view supervision).

Coordinate system (matches simutrans's square dimetric, see
`display/viewport.cc::get_screen_coord` and `koord::{north,south,
east,west}`): world +y = north (upper-right onscreen), -y = south
(lower-left), +x = east (lower-right), -x = west (upper-left).

Per-axis frames (`ORIENT_*`, all rotations of the canonical NS
geometry; bridge length spans world y ∈ [-0.5, +0.5] before
rotation):
- ORIENT_NS    rot=0°,    front=+x   — NS square + hex.
- ORIENT_EW    rot=-90°,  front=-y   — EW square only (legacy
                                      pak128 compositing rule).
- ORIENT_NE_SW rot=-60°,  front from `HEX_DEPTH_CLIP_NORMAL[NE_SW]`
                                    — hex only (no square ref).
- ORIENT_NW_SE rot=-120°, front from `HEX_DEPTH_CLIP_NORMAL[NW_SE]`
                                    — hex only (no square ref).

Trestle posts anchor the deck at the tile edge to z=0 (structural
correctness: deck supported all the way to the tile edge; a slow
bridge upgraded to a fast one shouldn't tilt, all rail_*_bridge
decks share a deck-top z).

Per-projection cameras (`_SQ_CAMERA`, `_HEX_CAMERA`) at the bottom
of the file carry the calibrated z=0 anchor for each side; both are
empirically tuned to match pak128 reference cells.  The .dat's
`0,32` square-only shift is a draw-time compositing offset the
engine applies, not a shift baked into the cell — the in-cell
anchor and the dat offset add at composite time.
"""
import functools
import math
from dataclasses import dataclass
from pathlib import Path

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

# Track-family parameters live next to rail_060_tracks; the bridge
# pulls them in so its deck-top track lines up with the joining
# standalone track.
from infrastructure.rail_tracks.rail_060_tracks.track_params import (
    BALLAST_TOP_Z, N_TIES, RAIL_GAUGE_HALF, RAIL_GREY, RAIL_HALF_W,
    RAIL_TOP_Z, TIE_BROWN, TIE_HALF_W, TIE_TOP_Z,
)


HERE = Path(__file__).resolve().parent

# Track-relative thicknesses derived from the cross-section stack
# (rail head sits on top of ties, ties on top of ballast).
RAIL_THICKNESS = RAIL_TOP_Z - TIE_TOP_Z
TIE_THICKNESS = TIE_TOP_Z - BALLAST_TOP_Z

# --- Bridge-specific material colors -----------------------------------------
TIMBER_DARK = (90, 65, 40)
TIMBER_MID = (130, 95, 60)
TIMBER_LIGHT = (170, 135, 90)
STONE_GREY = (140, 130, 115)

# --- Bridge dimensions (1 unit = 1 tile width) -------------------------------
BRIDGE_LEN_HALF = 0.5
# Deck must be wide enough to host the rail_060 cross-ties (TIE_HALF_W).
DECK_WIDTH_HALF = max(0.20, TIE_HALF_W + 0.04)
DECK_BOTTOM_Z = 0.10
DECK_TOP_Z = 0.13
RAILING_TOP_Z = 0.24
TOP_BAR_THICKNESS = 0.030

# Slimmer trestle posts than the original first pass; reference shows
# delicate timber framing rather than chunky pillars.
POST_HALF_X = 0.018
POST_HALF_Y = 0.018
N_PANELS = 8              # trestle panels along the span -> 9 posts per side
N_RAIL_POSTS = 10         # vertical posts in top railing per side

# Pillar (separate sheet entry: backPillar[S][0] / backPillar[W][0]) —
# a single vertical stone column rendered against an empty tile, drawn
# behind the bridge segment by the engine when it composites a multi-
# tile bridge over a deep gap.  The reference cell's pillar extends
# from just under the deck down to deep below tile-ground (the engine
# clips it against the gap floor at composite time, so the cell ships
# the maximum-depth shape).
# Pillar is wider perpendicular to the bridge axis than along it
# (ASPECT < 1) so its broad face points at the viewer.  Both extents
# are placeholders — TODO.md tracks the calibration debt.
PILLAR_HALF = 0.085
PILLAR_ALONG_ASPECT = 0.55
PILLAR_TOP_Z = DECK_BOTTOM_Z
PILLAR_BOTTOM_Z = -0.55


# --- Orientation = (rotation around z, depth-clip-plane front normal) -----
# A bridge orientation is fully described by two facts: how to rotate
# the canonical NS-frame geometry so it lies along the target axis,
# and which world half-plane is "front" (the FrontImage layer).
# `Orient` packs both; the per-axis frames below are the only places
# either constant lives.
#
# Square pak128 axes use the legacy compositing convention (NS:
# front=+x, EW: front=-y); hex axes pull `n` from the engine spec
# `display/hex_proj.h::HEX_DEPTH_CLIP_NORMAL`.  Hex way axes pair
# opposite edges (`NE_SW = NE edge ↔ SW edge`), so the chosen
# rotations land world +y on the corresponding edge-midpoint axis
# line; `n` is then perpendicular to the bridge length, which makes
# the front/back split a clean perpendicular offset (constant `n·p`
# along a side rail — no mid-bar layer flips).

@dataclass(frozen=True)
class Orient:
    rot_deg: float
    front_normal: tuple[float, float]


ORIENT_NS    = Orient(   0.0, HEX_DEPTH_CLIP_NORMAL[HEX_NS])     # square + hex
ORIENT_EW    = Orient( -90.0, (0.0, -1.0))                       # square only
ORIENT_NE_SW = Orient( -60.0, HEX_DEPTH_CLIP_NORMAL[HEX_NE_SW])  # hex only
ORIENT_NW_SE = Orient(-120.0, HEX_DEPTH_CLIP_NORMAL[HEX_NW_SE])  # hex only

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


def build_segment(model: Model, orient: Orient) -> None:
    """Build a mid-segment bridge in `orient`'s frame.

    Emits all parts (deck, trestle, railings, ties, rails) tagged
    with `back` / `front` layers per `orient.front_normal` so the
    renderer can slice off Back / Front from one model.
    """
    add = functools.partial(_add_oriented_box, model, orient)

    # 1. Deck slab — back layer (deck is part of the silhouette,
    #    vehicle draws on top).
    add(-BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
        -DECK_WIDTH_HALF, +DECK_WIDTH_HALF,
        DECK_BOTTOM_Z, DECK_TOP_Z, TIMBER_MID, force_layer="back")

    # 2. Trestle posts on both long sides, anchored to tile edges so
    #    the deck is supported all the way to the boundary.  Both
    #    sides are "back" — front-side trestle is part of the
    #    silhouette, not the FrontImage railing.
    #
    #    X-bracing between trestle posts is genuinely diagonal and
    #    the axis-aligned box rasterizer doesn't model it well.
    #    Deferred (TODO.md "X-bracing on rail_060_bridge").
    for i in range(N_PANELS + 1):
        along = -BRIDGE_LEN_HALF + (i / N_PANELS) * 2 * BRIDGE_LEN_HALF
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            add(along - POST_HALF_Y, along + POST_HALF_Y,
                side - POST_HALF_X, side + POST_HALF_X,
                0.0, DECK_BOTTOM_Z, TIMBER_DARK, force_layer="back")

    # 3. Top railing posts.  Layer auto-resolved per quad — the
    #    front-side posts land in the front slice via
    #    `orient.front_normal`.
    for i in range(N_RAIL_POSTS):
        along = -BRIDGE_LEN_HALF + ((i + 0.5) / N_RAIL_POSTS) * 2 * BRIDGE_LEN_HALF
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            add(along - 0.016, along + 0.016,
                side - 0.016, side + 0.016,
                DECK_TOP_Z, RAILING_TOP_Z, TIMBER_LIGHT)

    # 4. Top + bottom railing horizontal bars on each side.
    BOTTOM_BAR_Z_LO = DECK_TOP_Z - 0.010
    BOTTOM_BAR_Z_HI = DECK_TOP_Z + 0.020
    for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
        add(-BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
            side - 0.012, side + 0.012,
            RAILING_TOP_Z - TOP_BAR_THICKNESS, RAILING_TOP_Z, TIMBER_LIGHT)
        add(-BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
            side - 0.012, side + 0.012,
            BOTTOM_BAR_Z_LO, BOTTOM_BAR_Z_HI, TIMBER_LIGHT)

    # 5. Cross-ties on deck top — back layer (under the vehicle).
    #    Cross-section reused from rail_060_tracks so the bridge's
    #    deck-top track lines up with the joining standalone track.
    tie_top_z = DECK_TOP_Z + TIE_THICKNESS
    for i in range(N_TIES):
        along = -BRIDGE_LEN_HALF + ((i + 0.5) / N_TIES) * 2 * BRIDGE_LEN_HALF
        add(along - 0.025, along + 0.025,
            -TIE_HALF_W, +TIE_HALF_W,
            DECK_TOP_Z, tie_top_z, TIE_BROWN, force_layer="back")

    # 6. Two parallel rails on top of ties — back layer.
    rail_top_z = tie_top_z + RAIL_THICKNESS
    for gauge_x in (-RAIL_GAUGE_HALF, +RAIL_GAUGE_HALF):
        add(-BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
            gauge_x - RAIL_HALF_W, gauge_x + RAIL_HALF_W,
            tie_top_z, rail_top_z, RAIL_GREY, force_layer="back")


def _end_profile(kind: str, along: float) -> tuple[float, float]:
    """Return (deck_bottom, support_bottom) for an end tile.

    Canonical local +along points toward the bridge edge named by the
    entry (`N`, `ne`, ...).  Ramps climb from ground at the landward
    side (-0.5) to the normal bridge height at the outer edge (+0.5).
    Starts are the flat first bridge tile, with `start2` using deeper
    trestle posts for the double-height case.
    """
    if kind == "ramp":
        t = (along + BRIDGE_LEN_HALF) / (2.0 * BRIDGE_LEN_HALF)
        deck_bottom = 0.015 + t * (DECK_BOTTOM_Z - 0.015)
        return deck_bottom, 0.0
    if kind == "start2":
        return DECK_BOTTOM_Z, -0.24
    if kind == "start":
        return DECK_BOTTOM_Z, -0.10
    raise ValueError(f"unknown bridge end kind: {kind}")


def build_end(model: Model, orient: Orient, kind: str) -> None:
    """Build a bridge ramp/start/start2 end tile in `orient`'s frame.

    The parts deliberately mirror `build_segment` so early bridge
    graphics stay coherent: deck + track are Back, while the viewer
    side railing is sliced into Front by the same depth plane logic.
    The ramp is built from short horizontal steps; at pak128 scale the
    silhouette reads as a continuous incline while keeping the simple
    box rasterizer.
    """
    add = functools.partial(_add_oriented_box, model, orient)

    deck_steps = 10
    for i in range(deck_steps):
        a0 = -BRIDGE_LEN_HALF + (i / deck_steps) * 2 * BRIDGE_LEN_HALF
        a1 = -BRIDGE_LEN_HALF + ((i + 1) / deck_steps) * 2 * BRIDGE_LEN_HALF
        amid = (a0 + a1) / 2.0
        deck_bottom, _support_bottom = _end_profile(kind, amid)
        add(a0, a1, -DECK_WIDTH_HALF, +DECK_WIDTH_HALF,
            deck_bottom, deck_bottom + (DECK_TOP_Z - DECK_BOTTOM_Z),
            TIMBER_MID, force_layer="back")

    # Trestle posts.  Ramps only gain real height near the bridge end;
    # starts keep the full run supported, with start2 reaching deeper.
    for i in range(N_PANELS + 1):
        along = -BRIDGE_LEN_HALF + (i / N_PANELS) * 2 * BRIDGE_LEN_HALF
        deck_bottom, support_bottom = _end_profile(kind, along)
        if kind == "ramp" and deck_bottom < 0.04:
            continue
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            add(along - POST_HALF_Y, along + POST_HALF_Y,
                side - POST_HALF_X, side + POST_HALF_X,
                support_bottom, deck_bottom, TIMBER_DARK, force_layer="back")

    # A heavier end bent makes the bridge/ground transition legible.
    for along in (-BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF):
        deck_bottom, support_bottom = _end_profile(kind, along)
        if kind == "ramp" and along < 0:
            support_bottom = 0.0
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            add(along - 0.030, along + 0.030,
                side - 0.024, side + 0.024,
                support_bottom, deck_bottom + 0.03,
                TIMBER_DARK, force_layer="back")

    # Railing posts and bars, following the deck profile.
    for i in range(N_RAIL_POSTS):
        along = -BRIDGE_LEN_HALF + ((i + 0.5) / N_RAIL_POSTS) * 2 * BRIDGE_LEN_HALF
        deck_bottom, _support_bottom = _end_profile(kind, along)
        deck_top = deck_bottom + (DECK_TOP_Z - DECK_BOTTOM_Z)
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            add(along - 0.016, along + 0.016,
                side - 0.016, side + 0.016,
                deck_top, deck_top + (RAILING_TOP_Z - DECK_TOP_Z),
                TIMBER_LIGHT)

    bar_steps = 10
    for i in range(bar_steps):
        a0 = -BRIDGE_LEN_HALF + (i / bar_steps) * 2 * BRIDGE_LEN_HALF
        a1 = -BRIDGE_LEN_HALF + ((i + 1) / bar_steps) * 2 * BRIDGE_LEN_HALF
        amid = (a0 + a1) / 2.0
        deck_bottom, _support_bottom = _end_profile(kind, amid)
        deck_top = deck_bottom + (DECK_TOP_Z - DECK_BOTTOM_Z)
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            add(a0, a1, side - 0.012, side + 0.012,
                deck_top + (RAILING_TOP_Z - DECK_TOP_Z) - TOP_BAR_THICKNESS,
                deck_top + (RAILING_TOP_Z - DECK_TOP_Z),
                TIMBER_LIGHT)
            add(a0, a1, side - 0.012, side + 0.012,
                deck_top - 0.010, deck_top + 0.020,
                TIMBER_LIGHT)

    # Track on the end tile.
    tie_top_offset = TIE_THICKNESS
    rail_top_offset = TIE_THICKNESS + RAIL_THICKNESS
    for i in range(N_TIES):
        along = -BRIDGE_LEN_HALF + ((i + 0.5) / N_TIES) * 2 * BRIDGE_LEN_HALF
        deck_bottom, _support_bottom = _end_profile(kind, along)
        deck_top = deck_bottom + (DECK_TOP_Z - DECK_BOTTOM_Z)
        add(along - 0.025, along + 0.025,
            -TIE_HALF_W, +TIE_HALF_W,
            deck_top, deck_top + tie_top_offset, TIE_BROWN,
            force_layer="back")
    for gauge_x in (-RAIL_GAUGE_HALF, +RAIL_GAUGE_HALF):
        for i in range(deck_steps):
            a0 = -BRIDGE_LEN_HALF + (i / deck_steps) * 2 * BRIDGE_LEN_HALF
            a1 = -BRIDGE_LEN_HALF + ((i + 1) / deck_steps) * 2 * BRIDGE_LEN_HALF
            amid = (a0 + a1) / 2.0
            deck_bottom, _support_bottom = _end_profile(kind, amid)
            deck_top = deck_bottom + (DECK_TOP_Z - DECK_BOTTOM_Z)
            add(a0, a1, gauge_x - RAIL_HALF_W, gauge_x + RAIL_HALF_W,
                deck_top + TIE_THICKNESS,
                deck_top + rail_top_offset, RAIL_GREY,
                force_layer="back")


def build_pillar(model: Model, orient: Orient) -> None:
    """Single stone pillar centred on the tile, drawn behind the
    bridge segment when the engine composites a multi-tile bridge
    over a deep gap.  pak128 ships `pillar_asymmetric=1` so only the
    viewer-visible face has a sprite; the engine mirrors it.

    Wider perpendicular to the bridge axis than along it so the
    broad face shows from the front.  All quads "back".
    """
    along_half = PILLAR_HALF * PILLAR_ALONG_ASPECT
    _add_oriented_box(model, orient,
                      -along_half, +along_half,
                      -PILLAR_HALF, +PILLAR_HALF,
                      PILLAR_BOTTOM_Z, PILLAR_TOP_Z, STONE_GREY,
                      force_layer="back")


# Per-projection cameras, calibrated so the deck lands at the same
# composite screen-y in both — `ypos + 94` ≈ 2 px above the
# tile-centre, matching pak128's reference cells (the existing
# `silhouette y mismatch` TODO entry diagnosed cand 6 px too high
# against the square reference).  Square: dat `,0,32` shift adds 32
# at composite time, so cell-anchor 74 + 32 = 106 composite for z=0;
# deck at z=0.13 lands 11.77 px above z=0.  Hex: no dat shift, so
# the cell pixels carry the full offset — anchor 106 for z=0.
_SQ_CAMERA = SquareCamera(screen_center_y=74)
_HEX_CAMERA = HexCamera(anchor_y=106)


def _camera(projection: str):
    return _HEX_CAMERA if projection == "hex" else _SQ_CAMERA


def render_segment(orient: Orient, projection: str
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Render a mid-segment bridge in `orient`; return `(back, front)`."""
    m = Model()
    build_segment(m, orient)
    cam = _camera(projection)
    return (render(m, cam, layer_filter="back"),
            render(m, cam, layer_filter="front"))


def render_pillar(orient: Orient, projection: str) -> np.ndarray:
    """Render a pillar in `orient`; single-layer (back)."""
    m = Model()
    build_pillar(m, orient)
    return render(m, _camera(projection), layer_filter="back")


def render_end(orient: Orient, kind: str, projection: str
               ) -> tuple[np.ndarray, np.ndarray]:
    """Render a ramp/start/start2 end; return `(back, front)`."""
    m = Model()
    build_end(m, orient, kind)
    cam = _camera(projection)
    return (render(m, cam, layer_filter="back"),
            render(m, cam, layer_filter="front"))


# --- Square verification renders -------------------------------------------
# Each entry: (out filename relative to HERE, callable returning RGBA).
SQUARE_OUTPUTS = [
    ("out_back_ns.png",  lambda: render_segment(ORIENT_NS, "square")[0]),
    ("out_front_ns.png", lambda: render_segment(ORIENT_NS, "square")[1]),
    ("out_back_ew.png",  lambda: render_segment(ORIENT_EW, "square")[0]),
    ("out_front_ew.png", lambda: render_segment(ORIENT_EW, "square")[1]),
    ("out_pillar_s.png", lambda: render_pillar(ORIENT_NS, "square")),
    ("out_pillar_w.png", lambda: render_pillar(ORIENT_EW, "square")),
]

for _kind, _prefix in [
    ("ramp", "ramp"),
    ("start", "start"),
    ("start2", "start2"),
]:
    for _dir in ("N", "S", "E", "W"):
        _orient = ORIENT_SQUARE_EDGE[_dir]
        _stem = f"{_prefix}_{_dir.lower()}"
        SQUARE_OUTPUTS.extend([
            (f"out_back_{_stem}.png",
             lambda orient=_orient, kind=_kind:
                 render_end(orient, kind, "square")[0]),
            (f"out_front_{_stem}.png",
             lambda orient=_orient, kind=_kind:
                 render_end(orient, kind, "square")[1]),
        ])


def main() -> None:
    for name, fn in SQUARE_OUTPUTS:
        Image.fromarray(fn(), mode="RGBA").save(HERE / name)


# --- Hex bake --------------------------------------------------------------
# Atlas row/col matches `rail_060_bridge_hex.dat`'s entries.  Same scene
# build as the square renders — only the `Orient` and the projection
# differ.  Pillars carry single-layer.
HEX_ENTRIES: list[tuple[str, callable]] = [
    ("BackImage[ns][0]",     lambda: render_segment(ORIENT_NS,    "hex")[0]),
    ("FrontImage[ns][0]",    lambda: render_segment(ORIENT_NS,    "hex")[1]),
    ("BackImage[ne_sw][0]",  lambda: render_segment(ORIENT_NE_SW, "hex")[0]),
    ("FrontImage[ne_sw][0]", lambda: render_segment(ORIENT_NE_SW, "hex")[1]),
    ("BackImage[nw_se][0]",  lambda: render_segment(ORIENT_NW_SE, "hex")[0]),
    ("FrontImage[nw_se][0]", lambda: render_segment(ORIENT_NW_SE, "hex")[1]),
    ("backPillar[ns][0]",    lambda: render_pillar(ORIENT_NS,    "hex")),
    ("backPillar[ne_sw][0]", lambda: render_pillar(ORIENT_NE_SW, "hex")),
    ("backPillar[nw_se][0]", lambda: render_pillar(ORIENT_NW_SE, "hex")),
]

for _kind, _key in [
    ("ramp", "Ramp"),
    ("start", "Start"),
    ("start2", "Start2"),
]:
    for _edge in ("n", "s", "ne", "se", "sw", "nw"):
        _orient = ORIENT_HEX_EDGE[_edge]
        HEX_ENTRIES.extend([
            (f"Back{_key}[{_edge}][0]",
             lambda orient=_orient, kind=_kind:
                 render_end(orient, kind, "hex")[0]),
            (f"Front{_key}[{_edge}][0]",
             lambda orient=_orient, kind=_kind:
                 render_end(orient, kind, "hex")[1]),
        ])


def bake_pakset() -> None:
    bake_atlas(
        out_png=HERE.parent / "rail_060_bridge_hex.png",
        entries=HEX_ENTRIES,
        cols_per_row=9,
    )


if __name__ == "__main__":
    main()
    bake_pakset()
