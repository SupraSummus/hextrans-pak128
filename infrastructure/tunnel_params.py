"""Tunnel-portal parameters and the shared portal builder.

Counterpart of `rail_tracks/rail_params.py` and `roads/road_params.py`,
shared by the rail and road tunnels because a portal does not care what
runs through it: every tunnel reduces to a `TunnelParams` instance plus
a short scene file that pipes it into `make_tunnel`.

Engine spec is `tunnel_desc_t::slope_index` in
`hextrans/src/simutrans/descriptor/tunnel_desc.cc`: 6 portal sprites
keyed by hex edge name (`hex_keys::edge_names = {n, s, ne, se, sw, nw}`)
under the low-edge naming convention — `slope_t::north_narrow` is "low
edge N, mountain rises south, portal points outward through N" → slot
0 ("n").  Each sprite ships as a Front / Back image pair (writer in
`tunnel_writer.cc` reads `frontimage[<edge>][0]` / `backimage[<edge>][0]`),
composited around the way + vehicle: ground + way + back image +
vehicle + front image.

Legacy pak128 tunnel keys (`FrontImage[N]`, ...) are the opposite: they
name the HIGH edge, the side the mountain is on, so the portal of `[N]`
faces S, towards the viewer.  A legacy `[N]` cell therefore supervises
the hex `s` portal; `verify_tunnel` pairs them that way.  The engine
reads the same key text at the other edge, so a legacy .dat left as it
is shows every portal turned round (and none at all on the four
diagonal edges).

Layer split:
- `front`: just the lintel above the opening, so it draws over the
  vehicle and the train disappears under the arch as it enters the
  portal.
- `back`: buttresses flanking the opening, plus the dark interior
  visible through the opening.

The split is tagged at build time (canonical frame); rotation preserves
the per-quad layer.  The buttresses sit to either side of the vehicle's
screen footprint, so they don't need to occlude — only the lintel
directly above the rails does.

Pak128's reference cells include a separate "near-half cliff" silhouette
in the front-image cell; the model doesn't try to match that.
Reproducing it would mean either duplicating most of the cliff into the
front layer (game-broken: vehicle would render under the entire cliff)
or carving the cliff at a per-orientation depth-clip plane (needs the
renderer to support split boxes, see TODO.md).  The current asymmetry —
back IoU ≈ 0.5, front IoU low — is the honest trade.

The portal is built once in the canonical NS frame (low edge = N, low
end at world +y), then rotated to the target edge / direction.  The
same geometry feeds both the square verification renders (4 cardinal
directions) and the hex atlas (6 edges).  No slope tilt: pak128's
tunnel art sits at flat-tile ground; the slope rendering is the ground
baker's job.

Distances are in world units, 1 unit = 1 entry-edge length = 1
square-tile side = 1 hex-edge length (`tools/threed/way.py::
HEX_TILE_RADIUS`).
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed import crop_ref
from tools.threed import diff as diff_mod
from tools.threed.bespoke import bake_atlas
from tools.threed.render import HexCamera, Model, SquareCamera, render
from tools.threed.way import HEX_TILE_RADIUS

# Reuse the bridge's stone palette so a multi-tile tunnel approach
# composes coherently with a bridge-pillar / bridge-end joining it.
from infrastructure.rail_bridges.rail_060_bridge.scene import (
    STONE_GREY, ORIENT_HEX_EDGE,
)


RGB = tuple[int, int, int]

# Slope chord half-length: distance from tile centre to a low/high
# edge midpoint.  Square tiles span [-0.5, +0.5] (CHORD_HALF=0.5);
# hex tiles have circumradius HEX_TILE_RADIUS=1.0, so the
# perpendicular distance to an edge midpoint is R · √3 / 2 ≈ 0.866.
# Same pattern as `rail_060_bridge::_length_half`.
CHORD_HALF_SQUARE = 0.5
CHORD_HALF_HEX = HEX_TILE_RADIUS * math.sqrt(3.0) / 2.0

# Family constants, the same in every portal.  The cliff mass reaches
# `MASS_DEPTH` of a chord into the mountain behind the face, which
# stands `FACE_BACKSET` behind the tile centre.
FACE_BACKSET = 0.08
MASS_DEPTH = 0.55
# Dark inset visible through the opening — colour darker than the
# way's ballast so the contrast reads as "interior".
INTERIOR_DARK: RGB = (32, 26, 22)


# --- Per-tunnel parameter type ----------------------------------------------

@dataclass(frozen=True)
class TunnelParams:
    """Portal proportions + material for one tunnel."""
    # Asset name: `<name>.png` / `<name>.dat` in the family dir
    # (`rail_tunnels/` or `road_tunnels/`), model dir `<name>/`.
    name: str
    wall_color: RGB
    # Half-width of the cliff face along the chord perpendicular, and
    # of the opening in it.  The face is built from two buttresses
    # `opening_half_w .. face_half_w` either side of the opening.
    face_half_w: float = 0.32
    opening_half_w: float = 0.10
    # Heights above the (flat) tile ground.  `face_top_z` is
    # back-solved against pak128 `rail_060_tunnel.png` cell 1.0: the
    # cliff reaches ~60 px above its base in screen-y, which at the
    # dimetric world-z scale of sin(60°) · 90.5 ≈ 78 px per world unit
    # lands around 0.45 once the cliff's y-depth eats some of the
    # rise.  `opening_top_z` is the underside of the lintel.
    face_top_z: float = 0.45
    opening_top_z: float = 0.22


# --- Per-tunnel instances ---------------------------------------------------

# rail_060 — the worked example.  Its values predate any measuring and
# are the literal defaults above.
RAIL_060_TUNNEL = TunnelParams(
    name="rail_060_tunnel",
    wall_color=STONE_GREY,
)

# Every other tunnel is `python3 -m infrastructure.measure_tunnel
# <name>` output on its legacy cell (the method, and its precision of
# about 0.03, are in that module's docstring).  Colours are model
# colours; the pale concretes all sit at the top of the range because
# pak128 paints them brighter than this lighting can render.  The ring,
# reveal and wing walls the legacy art has beside the opening are left
# out: the model is a face with a hole in it.  Against the hand-set
# rail_060, the measured openings are mostly wider (0.17 .. 0.44 half
# width against 0.10) and taller (0.38 .. 0.54 against 0.22).
#
# highway_110 and road_070 are not measured yet (TODO.md).

# rail_080 — stone arch.  The same portal model, and so the same opening and face, as rail_080b.
RAIL_080_TUNNEL = TunnelParams(
    name="rail_080_tunnel",
    wall_color=(218, 200, 166),
    face_half_w=0.312, opening_half_w=0.203,
    face_top_z=0.444, opening_top_z=0.387,
)

# rail_080b — concrete arch between stepped wing walls.
RAIL_080B_TUNNEL = TunnelParams(
    name="rail_080b_tunnel",
    wall_color=(247, 251, 255),
    face_half_w=0.312, opening_half_w=0.203,
    face_top_z=0.444, opening_top_z=0.387,
)

# rail_100 — brick, stone-ringed arch; the opening is rail_080's, the brick wall wider.
RAIL_100_TUNNEL = TunnelParams(
    name="rail_100_tunnel",
    wall_color=(255, 227, 192),
    face_half_w=0.391, opening_half_w=0.203,
    face_top_z=0.432, opening_top_z=0.387,
)

# rail_120 — stone arch with a grey ring; the portal model of rail_140.
RAIL_120_TUNNEL = TunnelParams(
    name="rail_120_tunnel",
    wall_color=(246, 245, 230),
    face_half_w=0.391, opening_half_w=0.188,
    face_top_z=0.5, opening_top_z=0.436,
)

# rail_120b — concrete arch, the wall wider than rail_080b's.
RAIL_120B_TUNNEL = TunnelParams(
    name="rail_120b_tunnel",
    wall_color=(249, 251, 255),
    face_half_w=0.414, opening_half_w=0.203,
    face_top_z=0.429, opening_top_z=0.387,
)

# rail_140 — brick, ringed arch; rail_120's portal model.
RAIL_140_TUNNEL = TunnelParams(
    name="rail_140_tunnel",
    wall_color=(255, 233, 207),
    face_half_w=0.391, opening_half_w=0.188,
    face_top_z=0.5, opening_top_z=0.436,
)

# rail_160 — concrete block spanning the tile, round-topped opening.
RAIL_160_TUNNEL = TunnelParams(
    name="rail_160_tunnel",
    wall_color=(252, 252, 255),
    face_half_w=0.492, opening_half_w=0.219,
    face_top_z=0.51, opening_top_z=0.43,
)

# rail_180 — rail_160's block with a narrower, lower opening.
RAIL_180_TUNNEL = TunnelParams(
    name="rail_180_tunnel",
    wall_color=(252, 252, 255),
    face_half_w=0.492, opening_half_w=0.172,
    face_top_z=0.447, opening_top_z=0.424,
)

# rail_200 — concrete box, a wider opening than any arch.
RAIL_200_TUNNEL = TunnelParams(
    name="rail_200_tunnel",
    wall_color=(250, 251, 255),
    face_half_w=0.5, opening_half_w=0.312,
    face_top_z=0.556, opening_top_z=0.467,
)

# rail_240 — concrete box.  rail_280, rail_320 and rail_400 share its geometry and its pale concrete: the legacy cells differ only in details the model does not draw.
RAIL_240_TUNNEL = TunnelParams(
    name="rail_240_tunnel",
    wall_color=(255, 255, 255),
    face_half_w=0.5, opening_half_w=0.289,
    face_top_z=0.537, opening_top_z=0.42,
)

RAIL_280_TUNNEL = replace(RAIL_240_TUNNEL, name="rail_280_tunnel")

RAIL_320_TUNNEL = replace(RAIL_240_TUNNEL, name="rail_320_tunnel")

RAIL_400_TUNNEL = replace(RAIL_240_TUNNEL, name="rail_400_tunnel")

# highway_130 — concrete tube across the whole tile edge; the ring is thin, so the buttresses are slivers.
HIGHWAY_130_TUNNEL = TunnelParams(
    name="highway_130_tunnel",
    wall_color=(250, 251, 255),
    face_half_w=0.492, opening_half_w=0.438,
    face_top_z=0.604, opening_top_z=0.543,
)

# road_040 — brick wall with an arch under a road deck.
ROAD_040_TUNNEL = TunnelParams(
    name="road_040_tunnel",
    wall_color=(255, 222, 190),
    face_half_w=0.5, opening_half_w=0.359,
    face_top_z=0.422, opening_top_z=0.384,
)

# road_050 — concrete version of road_040's wall.
ROAD_050_TUNNEL = TunnelParams(
    name="road_050_tunnel",
    wall_color=(252, 252, 255),
    face_half_w=0.5, opening_half_w=0.359,
    face_top_z=0.422, opening_top_z=0.384,
)

# road_090 — concrete tube, highway_130's portal narrower.
ROAD_090_TUNNEL = TunnelParams(
    name="road_090_tunnel",
    wall_color=(253, 252, 255),
    face_half_w=0.492, opening_half_w=0.414,
    face_top_z=0.585, opening_top_z=0.515,
)


# --- Geometry ---------------------------------------------------------------

def build_portal(model: Model, params: TunnelParams, chord_half: float) -> None:
    """Build the canonical NS-frame portal: low edge at +y, high at -y.

    `chord_half` is the perpendicular distance from tile centre to
    the low/high edge midpoint — picked per projection.

    Geometry:
    - Two cliff buttresses flanking the opening (back layer).
    - Cliff lintel above the opening (front layer).
    - Dark interior visible through the opening (back layer).

    Layer tags are set per box at build time so rotation can be a
    pure vertex transform.
    """
    y_front = -FACE_BACKSET          # +y face of the cliff
    y_back = -chord_half * MASS_DEPTH  # cliff extends into the mountain
    p = params

    # Cliff buttresses flanking the opening.
    model.add_box(
        (-p.face_half_w, y_back, 0.0),
        (-p.opening_half_w, y_front, p.face_top_z),
        p.wall_color, layer="back")
    model.add_box(
        (+p.opening_half_w, y_back, 0.0),
        (+p.face_half_w, y_front, p.face_top_z),
        p.wall_color, layer="back")

    # Cliff lintel above the opening — front layer, so it draws over
    # the vehicle as it passes under the arch.
    model.add_box(
        (-p.opening_half_w, y_back, p.opening_top_z),
        (+p.opening_half_w, y_front, p.face_top_z),
        p.wall_color, layer="front")

    # Dark interior visible through the opening.
    model.add_box(
        (-p.opening_half_w, y_back, 0.0),
        (+p.opening_half_w, y_front, p.opening_top_z),
        INTERIOR_DARK, layer="back")


def _rotate_around_z(model: Model, deg: float) -> None:
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    model.verts = [
        (ca * x - sa * y, sa * x + ca * y, z) for (x, y, z) in model.verts
    ]


def _build_oriented(params: TunnelParams, rot_deg: float,
                    projection: str) -> Model:
    m = Model()
    chord_half = CHORD_HALF_HEX if projection == "hex" else CHORD_HALF_SQUARE
    build_portal(m, params, chord_half)
    _rotate_around_z(m, rot_deg)
    return m


# Square portal directions, by where the portal OPENS: rotation of the
# canonical frame, whose portal opens at +y (N onscreen) at 0°.
# Not the legacy pak128 key letters, which name the high edge (see the
# module docstring).
SQUARE_DIR_TO_ROT_DEG = {
    "N":    0.0,
    "S":  180.0,
    "E":  -90.0,
    "W":   90.0,
}
OPPOSITE_DIR = {"N": "S", "S": "N", "E": "W", "W": "E"}

# Hex atlas layout: one row per layer, one column per edge, in
# `hex_keys::edge_names` order so a visual diff matches column index
# against `tunnel_desc_t::slope_index`.
EDGE_ORDER = ("n", "s", "ne", "se", "sw", "nw")


class Portal:
    """One tunnel's portal, rendered through either camera."""

    def __init__(self, params: TunnelParams, out_dir: Path) -> None:
        self.params = params
        self.out_dir = out_dir
        # Scratch (refs, candidate renders) and legacy art live here.
        self.model_dir = out_dir / params.name

    def render_square(self, direction: str, layer: str) -> np.ndarray:
        """Render one portal sprite through the pak128 square dimetric
        camera, with the portal opening towards `direction`."""
        m = _build_oriented(self.params, SQUARE_DIR_TO_ROT_DEG[direction],
                            "square")
        return render(m, SquareCamera(), layer_filter=layer)

    def render_hex(self, low_edge: str, layer: str) -> np.ndarray:
        """Render one portal sprite through the hex camera, oriented so
        the low edge / portal opening points along `low_edge`."""
        m = _build_oriented(self.params, ORIENT_HEX_EDGE[low_edge].rot_deg,
                            "hex")
        return render(m, HexCamera(), layer_filter=layer)

    def hex_entries(self):
        entries = []
        for layer_name, layer in (("FrontImage", "front"),
                                  ("BackImage", "back")):
            for edge in EDGE_ORDER:
                entries.append(
                    (f"{layer_name}[{edge}][0]",
                     lambda edge=edge, layer=layer:
                         self.render_hex(edge, layer)))
        return entries


def make_tunnel(params: TunnelParams, *, out_dir: Path):
    """Wire one tunnel up for hex bake + square verification.

    Each tunnel's `scene.py` reduces to::

        from pathlib import Path
        from infrastructure.tunnel_params import RAIL_060_TUNNEL, make_tunnel

        PORTAL, bake_pakset = make_tunnel(
            RAIL_060_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)

        if __name__ == "__main__":
            bake_pakset()

    `PORTAL` is consumed by `verify_tunnel`; `bake_pakset()` writes the
    6×2 hex atlas `<out_dir>/<name>.png` (6 columns in `EDGE_ORDER`,
    row 0 = FrontImage, row 1 = BackImage) that the sibling .dat points
    at.
    """
    portal = Portal(params, out_dir)

    def bake_pakset() -> None:
        bake_atlas(
            out_png=out_dir / f"{params.name}.png",
            entries=portal.hex_entries(),
            cols_per_row=len(EDGE_ORDER),
        )

    return portal, bake_pakset


# --- Square verification ----------------------------------------------------

def legacy_cells(dat_path: Path) -> dict[tuple[str, str], tuple[int, int]]:
    """`(layer, legacy key letter) -> (row, col)` of the summer cells a
    legacy tunnel .dat names (`FrontImage[N][0]=name.1.0`); `-` and
    absent keys are left out."""
    pattern = re.compile(
        r"^\s*(front|back)image\[([nsew])\]\[0\]\s*=\s*[\w\-]+\.(\d+)\.(\d+)\b",
        re.IGNORECASE)
    cells = {}
    for line in dat_path.read_text(errors="replace").splitlines():
        m = pattern.match(line)
        if m:
            cells[(m.group(1).lower(), m.group(2).upper())] = (
                int(m.group(3)), int(m.group(4)))
    return cells


def verify_tunnel(scene_mod) -> None:
    """Crop the legacy cells, render the candidates, run the hex bake,
    diff each pair.

    `scene_mod` exposes `PORTAL` and `bake_pakset()`.  The legacy art is
    `src/<name>.png` with its .dat, in the model dir; per-cell outputs
    land next to it: `refs/<layer>_<key>.png` (cropped pak128 cell),
    `out_<layer>_<key>.png` (square render) and `diff_debug_*.png`
    (side-by-side), `<key>` being the legacy letter.  A legacy `[N]`
    cell is paired with the candidate whose portal opens S (see the
    module docstring).
    """
    portal = scene_mod.PORTAL
    name = portal.params.name
    here = portal.model_dir
    cells = legacy_cells(here / "src" / f"{name}.dat")
    sheet = Image.open(here / "src" / f"{name}.png").convert("RGB")

    refs_dir = here / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    pairs = []
    for (layer, key), (row, col) in sorted(cells.items()):
        tile = crop_ref.crop_tile(sheet, row, col, crop_ref.DEFAULT_TILE_SIZE)
        tile = crop_ref.mask_transparent(tile, crop_ref.PAK128_TRANSPARENT)
        stem = f"{layer}_{key.lower()}"
        tile.save(refs_dir / f"{stem}.png")
        cand = portal.render_square(OPPOSITE_DIR[key], layer)
        Image.fromarray(cand, mode="RGBA").save(here / f"out_{stem}.png")
        pairs.append((stem, f"{layer.title()}Image[{key}][0] (cell {row}.{col})"))

    scene_mod.bake_pakset()

    print()
    for stem, label in pairs:
        ref = diff_mod.load_rgba(refs_dir / f"{stem}.png")
        cand = diff_mod.load_rgba(here / f"out_{stem}.png")
        diff_mod.make_debug(ref, cand, here / f"diff_debug_{stem}.png")
        print(f"=== {label} ===")
        json.dump(diff_mod.score(ref, cand), sys.stdout, indent=2)
        sys.stdout.write("\n")
