#!/usr/bin/env python3
"""Bake the hex pakset's way-wall (intra-tile cut/embankment) deliverable.

A way running through a tile at chord height `h_way` differs from the
natural ground at the off-axis corners of every hex edge it doesn't
touch directly.  Each such mismatch produces a vertical wall inside
the tile, separating the way surface from the ground earth — a
*cutting* wall when the ground rises above the way (`G > W`), an
*embankment* wall when it sinks below (`G < W`).

The atlas keys cells by `(wall, index)` with `wall in 0..5` (all six
hex edges; see `hex_synth.CLIFF_WALL_ENDPOINTS`) and `index in 1..10`
reusing the shared `(h1, h2)` encoding.  Polygon geometry comes from
`hex_synth.render_cliff_cell`, the same path back_wall uses; only the
per-wall cutting palette lives here.

The engine's `grund_t::display_way_walls` (companion engine commit)
iterates the 6 hex edges, computes `(h1, h2)` between
`slope_way_h_at_edge` and `corner_height`, and asserts the
pinched-wall invariant (exactly one endpoint at zero) before looking
up here.  Sign-bit packing (cutting vs embankment) lives engine-side;
this atlas carries only the unsigned cliff polygon, palette baked in.

Distinct from back_wall:
  * back_wall draws *inter-tile* cliffs against the 3 screen-up
    neighbour edges (NW, N, NE) and is sized for that pass.
  * way_wall draws *intra-tile* cuts on all 6 hex edges of the
    tile itself and is sized for the per-edge pass in
    `display_boden`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.threed import hex_synth


WALL_COUNT = 6
IMAGE_COUNT = hex_synth.CLIFF_IMAGE_COUNT


# Cutting-palette per wall: darker / less saturated than back_wall's
# natural cliff to read as a shadowed cut face rather than a lit
# weather-facing cliff.  Per-wall darkening keeps adjacent faces
# visually distinct; walls 3..5 mirror walls 2..0 across the
# screen-mid line so a tile with cuts on opposite edges reads
# symmetric.  Values quantise to RGB555 (5-bit replicate-high) so the
# engine's RGB555 pipeline preserves them bit-for-bit.
FACE_COLOR = {
    0: ( 49,  41,  16),  # NW edge (darkest)
    1: ( 66,  49,  24),  # N  edge
    2: ( 82,  66,  33),  # NE edge (lightest of back row)
    3: ( 82,  66,  33),  # SE edge — mirror of NE
    4: ( 66,  49,  24),  # S  edge — mirror of N
    5: ( 49,  41,  16),  # SW edge — mirror of NW
}


def render_cell(wall: int, index: int,
                geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one way-wall cell."""
    h1, h2 = hex_synth.decode_cliff_index(index)
    return hex_synth.render_cliff_cell(wall, h1, h2, FACE_COLOR[wall], geom)


HEADER_DOC = f"""\
Intra-tile cut / embankment walls keyed by `(wall, index)` with
`wall in 0..5` (six hex edges: 0=NW, 1=N, 2=NE, 3=SE, 4=S, 5=SW) and
`index in 1..{IMAGE_COUNT - 1}` under the back_wall `(h1, h2)` encoding
`index = h1 + 3*h2`.  Index 0 ("no wall") is not emitted; the engine
treats the absent slot as IMG_EMPTY.  Indices 9 and 10 are
placeholder half-cliffs for the legacy double-height notch.

Cutting-palette companion to back_wall's slopes atlas — shadowed cut
face, mirrored across all six hex edges so the engine's per-edge
display_way_walls pass picks the right orientation without rotation.
"""


def _wall_index_entries(_geom):
    """`iter_entries` for way-wall: yield `(wall, index)` cells.

    Wall-major emission order so each atlas row carries one wall.
    """
    for wall in range(WALL_COUNT):
        for index in range(1, IMAGE_COUNT):
            h1, h2 = hex_synth.decode_cliff_index(index)
            yield wall, index, (wall, index), \
                  f"wall={wall} h1={h1} h2={h2}"


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="way_wall",
        obj_name="WayWall",
        header_doc=HEADER_DOC,
        render_cell=lambda wall, index, geom: render_cell(wall, index, geom),
        iter_entries=_wall_index_entries,
        default_cols=IMAGE_COUNT - 1,  # one row per wall
    )
