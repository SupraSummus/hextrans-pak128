#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's cliff-face (back-wall) cells.

Per-(wall, index, artificial) cell carrying one cliff-face polygon
attached to one of the tile's three north-side edges:

  * wall 0 — NW edge (W -> NW corners)
  * wall 1 — N  edge (NW -> NE corners)
  * wall 2 — NE edge (NE -> E  corners)

Polygon geometry and `(h1, h2)` encoding are shared with way_wall via
`hex_synth.render_cliff_cell` / `hex_synth.decode_cliff_index`; only
the per-(artificial, wall) palette lives here.

Style: drab brown for natural cliffs, drab grey for the man-made
fundament platform; per-wall darkening so adjacent faces read as
separate planes.

Usage:
    render.py <wall> <index> {natural,fundament} <out.png>
    build_pakset.py                              # bake both atlases
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed import hex_synth


WALL_COUNT = 3
IMAGE_COUNT = hex_synth.CLIFF_IMAGE_COUNT


# Flat-colour palette, indexed by (artificial, wall).  Wall 0 (NW
# edge) faces screen-up-left, wall 1 (N) faces screen-up, wall 2 (NE)
# faces screen-up-right; per-wall darkening hand-picked to keep
# adjacent walls visually distinct under vertical cliff lighting.
# Values are RGB555 quantisation points (5-bit per channel,
# `(13, 11, 7)` natural / `(20, 20, 20)` fundament, scaled by
# `WALL_SHADE / 256` then expanded to 8-bit via the standard
# replicate-high `x_8 = (x_5 << 3) | (x_5 >> 2)` rule), so the on-disk
# pixels round to a fixed 5-bit point that the engine's RGB555
# pipeline preserves bit-for-bit.
FACE_COLOR = {
    (False, 0): ( 74,  66,  41),  # natural,   wall 0 (darkest)
    (False, 1): ( 90,  74,  49),  # natural,   wall 1
    (False, 2): (107,  90,  57),  # natural,   wall 2 (lightest)
    (True,  0): (123, 123, 123),  # fundament, wall 0
    (True,  1): (140, 140, 140),  # fundament, wall 1
    (True,  2): (165, 165, 165),  # fundament, wall 2
}


def render_back_wall(wall: int, index: int, artificial: bool,
                     geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one cliff-face cell.

    Output is HxWx4 RGBA: cliff-face pixels are opaque shaded base,
    everything else stays alpha=0 so makeobj's PNG -> RLE encoder
    skips them at compile time.  Index 0 is never baked (no cliff,
    empty cell); other indices with `h1 == h2 == 0` shouldn't occur
    under the encoding but render as empty for safety.
    """
    h1, h2 = hex_synth.decode_cliff_index(index)
    return hex_synth.render_cliff_cell(wall, h1, h2,
                                        FACE_COLOR[(artificial, wall)], geom)


def main():
    p = argparse.ArgumentParser(description="Render one hex cliff-face (back-wall) cell.")
    p.add_argument("wall", type=int, choices=(0, 1, 2),
                   help="0 = NW edge, 1 = N edge, 2 = NE edge")
    p.add_argument("index", type=int,
                   help=f"per-wall image index (1..{IMAGE_COUNT - 1}; 0 is no cliff)")
    p.add_argument("flavor", choices=("natural", "fundament"),
                   help="natural cliff or man-made fundament platform")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    cell = render_back_wall(args.wall, args.index,
                            artificial=(args.flavor == "fundament"),
                            geom=geom)
    Image.fromarray(cell, mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
