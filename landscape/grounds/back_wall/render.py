#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's cliff-face (back-wall) cells.

Per-(wall, index, artificial) cell carrying one cliff-face polygon
attached to one of the tile's three north-side edges:

  * wall 0 — NW edge (W -> NW corners)
  * wall 1 — N  edge (NW -> NE corners)
  * wall 2 — NE edge (NE -> E  corners)

The lower edge of the polygon sits at the unlifted edge in screen
space; the upper edge is lifted by `h1 * geom.lift` at the first
endpoint and `h2 * geom.lift` at the second, matching the
`get_back_image_from_diff` encoding the engine's `grund.cc` produces:
index 0 = no cliff (not emitted), 1..8 = `(h1, h2)` for
`h1, h2 in {0, 1, 2}` with `index = h1 + 3*h2`, and 9..10 = the
middle slopes of double-height stacks (currently rendered as the
corresponding single-step half-cliffs; see `TODO.md` for the missing
notch shape).

Style: drab brown for natural cliffs, drab grey for the man-made
fundament platform; per-wall darkening so adjacent faces read as
separate planes.

Usage:
    render.py <wall> <index> {natural,fundament} <out.png>
    build_pakset.py                              # bake both atlases
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Make `tools/3d/` importable from the per-asset bake dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "3d"))

import hex_synth  # noqa: E402


WALL_COUNT = 3
IMAGE_COUNT = 11   # per-wall image slots; index 0 = "no cliff", not baked


# Lower-edge endpoint corners per wall.
WALL_ENDPOINTS = (
    (hex_synth.W_C, hex_synth.NW),  # wall 0: NW edge
    (hex_synth.NW,  hex_synth.NE),  # wall 1: N edge
    (hex_synth.NE,  hex_synth.E),   # wall 2: NE edge
)


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


def _decode_index(index: int) -> tuple[int, int]:
    """`(h1, h2)` for the cliff polygon's two endpoint lifts.

    Indices 1..8 are the standard `index = h1 + 3*h2` encoding;
    indices 9 and 10 are placeholder shapes for the legacy
    double-height notch (see hextrans `TODO.md`).
    """
    if index == 10:
        return 1, 0
    if index == 9:
        return 0, 1
    return index % 3, index // 3


def render_back_wall(wall: int, index: int, artificial: bool,
                     geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one cliff-face cell.

    Output is HxWx4 RGBA: cliff-face pixels are opaque shaded base,
    everything else stays alpha=0 so makeobj's PNG -> RLE encoder
    skips them at compile time.  Index 0 is never baked (no cliff,
    empty cell); other indices with `h1 == h2 == 0` shouldn't occur
    under the encoding but render as empty for safety.
    """
    if geom is None:
        geom = hex_synth.HexGeom()

    h1, h2 = _decode_index(index)
    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    if h1 == 0 and h2 == 0:
        return buf

    a, b = WALL_ENDPOINTS[wall]
    ax, ay = geom.vx[a], geom.vy_base[a]
    bx, by = geom.vx[b], geom.vy_base[b]
    color = FACE_COLOR[(artificial, wall)]

    # Quad: lower edge a -> b at unlifted edge y; upper edge lifted up
    # by h2*lift at b and h1*lift at a (y grows down so subtract).
    xs = [ax, bx, bx,                   ax                  ]
    ys = [ay, by, by - h2 * geom.lift,  ay - h1 * geom.lift ]
    hex_synth.fill_polygon(buf, xs, ys, color)
    # `fill_polygon`'s parity rule skips horizontal edges; close them
    # explicitly for wall 1 (lower edge horizontal) and for any quad
    # with `h1 == h2` (upper edge horizontal -- includes the uniform
    # extension cliffs at indices 4 and 8 the engine reuses for
    # `get_back_wall_extension_image`).
    hex_synth.seal_horizontal_edges(buf, xs, ys, color)
    return buf


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
