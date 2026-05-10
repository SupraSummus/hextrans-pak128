"""3D model of the rail_060 tunnel portal.

Engine spec is `tunnel_desc_t::slope_index` in
`hextrans/src/simutrans/descriptor/tunnel_desc.cc`: 6 portal sprites
keyed by hex edge name (`hex_keys::edge_names = {n, s, ne, se, sw, nw}`)
under the low-edge naming convention — `slope_t::north_narrow` is "low
edge N, mountain rises south, portal points outward through N" → slot
0 ("n").  Each sprite ships as a Front / Back image pair (writer in
`tunnel_writer.cc` reads `frontimage[<edge>][0]` / `backimage[<edge>][0]`),
composited around the way + vehicle: ground + way + back image +
vehicle + front image.

Pak128's tunnel sheet is keyed the same way (`[N]` = portal opens N);
the engine's "INVERTS the upstream tunnel convention" comment
referred to pak64.  `SQUARE_DIR_TO_ROT_DEG` pins the mapping between
pak128 letters and canonical-frame rotations so the square diff loop
and the hex deliverable share one geometry source.

Layer split:
- `front`: just the cliff lintel above the opening, so it draws over
  the vehicle and the train disappears under the arch as it enters
  the portal.
- `back`: cliff buttresses flanking the opening, plus the dark
  interior visible through the opening.

The split is tagged at build time (canonical frame); rotation
preserves the per-quad layer.  The buttresses sit to either side of
the vehicle's screen footprint, so they don't need to occlude — only
the lintel directly above the rails does.

Pak128's reference cells include a separate "near-half cliff"
silhouette in the front-image cell (cell 0.0 etc.); we don't try to
match that.  Reproducing it would mean either duplicating most of
the cliff into the front layer (game-broken: vehicle would render
under the entire cliff) or carving the cliff at a per-orientation
depth-clip plane (needs the renderer to support split boxes, see
TODO.md).  The current asymmetry — back IoU ≈ 0.5 on camera-facing
directions, front IoU low — is the honest trade.

The portal is built once in the canonical NS frame (low edge = N,
low end at world +y), then rotated to the target edge / direction.
The same geometry feeds both the square verification renders (4
cardinal directions) and the hex atlas (6 edges).  No slope tilt:
pak128's tunnel art sits at flat-tile ground; the slope rendering
is the ground baker's job.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed.bespoke import bake_atlas
from tools.threed.render import HexCamera, Model, SquareCamera, render
from tools.threed.way import HEX_TILE_RADIUS

# Reuse the bridge's stone palette so a multi-tile tunnel approach
# composes coherently with a bridge-pillar / bridge-end joining it.
from infrastructure.rail_bridges.rail_060_bridge.scene import (
    STONE_GREY, ORIENT_HEX_EDGE,
)


HERE = Path(__file__).resolve().parent

# Slope chord half-length: distance from tile centre to a low/high
# edge midpoint.  Square tiles span [-0.5, +0.5] (CHORD_HALF=0.5);
# hex tiles have circumradius HEX_TILE_RADIUS=1.0, so the
# perpendicular distance to an edge midpoint is R · √3 / 2 ≈ 0.866.
# Same pattern as `rail_060_bridge::_length_half`.
CHORD_HALF_SQUARE = 0.5
CHORD_HALF_HEX = HEX_TILE_RADIUS * math.sqrt(3.0) / 2.0


# Portal dimensions (in world units, 1 unit = entry-edge length).
# Calibrated against pak128 `rail_060_tunnel.png` cells 1.0/1.1: the
# cliff face is roughly two-thirds the tile width and reaches a touch
# below half a tile-edge in screen height.
CLIFF_HALF_W = 0.32     # half-width of the cliff face along chord-perp
OPENING_HALF_W = 0.10   # half-width of the rectangular rail opening
CLIFF_THICK_HALF = 0.08  # half-depth into the chord (along axis)

# Heights above the (flat) tile ground.  CLIFF_TOP_Z is back-solved
# against the reference: pak128 cell 1.0's cliff reaches ~60 px above
# its base in screen-y, which at the dimetric world-z scale of
# sin(60°) · 90.5 ≈ 78 px per world unit lands around 0.45 once the
# cliff's y-depth eats some of the rise.
CLIFF_TOP_Z = 0.45
OPENING_TOP_Z = 0.22   # top of the opening = bottom of the lintel

# Dark inset visible through the opening — colour darker than the
# way's ballast so the contrast reads as "interior".
INTERIOR_DARK = (32, 26, 22)


def build_portal(model: Model, chord_half: float) -> None:
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
    y_front = -CLIFF_THICK_HALF      # +y face of the cliff
    y_back  = -chord_half * 0.55     # cliff extends into the mountain

    # Cliff buttresses flanking the opening.
    model.add_box(
        (-CLIFF_HALF_W, y_back, 0.0),
        (-OPENING_HALF_W, y_front, CLIFF_TOP_Z),
        STONE_GREY, layer="back")
    model.add_box(
        (+OPENING_HALF_W, y_back, 0.0),
        (+CLIFF_HALF_W,   y_front, CLIFF_TOP_Z),
        STONE_GREY, layer="back")

    # Cliff lintel above the opening — front layer, so it draws over
    # the vehicle as it passes under the arch.
    model.add_box(
        (-OPENING_HALF_W, y_back, OPENING_TOP_Z),
        (+OPENING_HALF_W, y_front, CLIFF_TOP_Z),
        STONE_GREY, layer="front")

    # Dark interior visible through the opening.
    model.add_box(
        (-OPENING_HALF_W, y_back, 0.0),
        (+OPENING_HALF_W, y_front, OPENING_TOP_Z),
        INTERIOR_DARK, layer="back")


def _rotate_around_z(model: Model, deg: float) -> None:
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    model.verts = [
        (ca * x - sa * y, sa * x + ca * y, z) for (x, y, z) in model.verts
    ]


def _build_oriented(rot_deg: float, projection: str) -> Model:
    m = Model()
    chord_half = CHORD_HALF_HEX if projection == "hex" else CHORD_HALF_SQUARE
    build_portal(m, chord_half)
    _rotate_around_z(m, rot_deg)
    return m


# --- Pak128 square dimetric: rotation per direction letter ----------------
# Pak128 cells [N]/[S]/[E]/[W] are low-edge keyed: `[N]` is the portal
# opening through the N edge.  Our canonical NS frame already puts
# the portal at +y (= N onscreen) at rotation 0°.
SQUARE_DIR_TO_ROT_DEG = {
    "N":    0.0,
    "S":  180.0,
    "E":  -90.0,
    "W":   90.0,
}


def render_square(direction: str, layer: str) -> np.ndarray:
    """Render one portal sprite through the pak128 square dimetric
    camera, oriented so the portal opening points in the named
    direction (matching pak128's low-edge naming on the upstream sheet)."""
    m = _build_oriented(SQUARE_DIR_TO_ROT_DEG[direction], "square")
    return render(m, SquareCamera(), layer_filter=layer)


def render_portal(low_edge: str, layer: str) -> np.ndarray:
    """Render one portal sprite through the hex camera, oriented so
    the low edge / portal opening points along `low_edge` (matching
    `hex_keys::edge_names`)."""
    m = _build_oriented(ORIENT_HEX_EDGE[low_edge].rot_deg, "hex")
    return render(m, HexCamera(), layer_filter=layer)


# --- Hex atlas layout -----------------------------------------------------
# One row per layer, one column per edge, in `hex_keys::edge_names`
# order so a future visual diff matches column index against
# `tunnel_desc_t::slope_index`.
EDGE_ORDER = ("n", "s", "ne", "se", "sw", "nw")

HEX_ENTRIES = []
for _layer_name, _layer in (("FrontImage", "front"), ("BackImage", "back")):
    for _edge in EDGE_ORDER:
        HEX_ENTRIES.append(
            (f"{_layer_name}[{_edge}][0]",
             lambda edge=_edge, layer=_layer: render_portal(edge, layer))
        )


def bake_pakset() -> None:
    bake_atlas(
        out_png=HERE.parent / "rail_060_tunnel.png",
        entries=HEX_ENTRIES,
        cols_per_row=6,
    )


# --- Square verification renders -----------------------------------------
SQUARE_OUTPUTS = []
for _direction in ("N", "S", "E", "W"):
    for _layer in ("back", "front"):
        SQUARE_OUTPUTS.append(
            (f"out_{_layer}_{_direction.lower()}.png",
             lambda d=_direction, l=_layer: render_square(d, l))
        )


def main() -> None:
    for name, fn in SQUARE_OUTPUTS:
        Image.fromarray(fn(), mode="RGBA").save(HERE / name)


if __name__ == "__main__":
    main()
    bake_pakset()
