#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's fence cells.

A fence is one whole-tile cell carrying a fence on any subset of the
tile's three north-side edges (the engine's back-wall slots):

  * bit 0 (1) -- NW edge (W -> NW corners)
  * bit 1 (2) -- N  edge (NW -> NE corners)
  * bit 2 (4) -- NE edge (NE -> E  corners)

The engine draws it where the neighbour behind a level edge is lower
(`calc_back_image` / `display_boden` in `ground/grund.cc`), before the
tile's own ground image.  The ground therefore covers every cell pixel
on or below the edge line, and a fence is only visible above it: the
cell stands the fence on the edge and starts drawing one pixel up.

Edge endpoints are `hex_synth.CLIFF_WALL_ENDPOINTS`, the same corner
pairs the cliff-face baker uses; the cell is the flat tile, the engine
lifts it by the NW / NE corner height.  A fence is flat lines in
screen space -- posts are vertical, rails parallel to the edge -- so
its rail heights are plain vertical offsets from the edge line, exactly
what the hex projection does to a height above ground.

Style follows the legacy pak128 fences (Fabio Gonella, 2006): natural
ground gets a one-pixel dark-olive line along the edge (the cliff
border), artificial ground a low brown wooden fence, six pixels of
posts with two rails at thirds of their height.

Usage:
    render.py <mask> {natural,artificial} <out.png>
    build_pakset.py                          # bake the 14-cell atlas
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed import hex_synth


WALL_COUNT = hex_synth.BACK_WALL_COUNT
EDGE_NAMES = hex_synth.BACK_WALL_EDGE_NAMES

# Non-empty subsets of the back walls: bit `wall` of the mask is set
# when that wall's edge carries a fence.  `fence_offset` in
# `calc_back_image`; the engine looks cells up at `mask - 1`.
MASK_COUNT = (1 << WALL_COUNT) - 1


@dataclass(frozen=True)
class FenceStyle:
    """One fence flavour.

    `color`: flat RGB at RGB555 quantisation points (see back_wall).
    `height`: top of the fence above the edge line, in engine height
    steps (`geom.lift` pixels each; the legacy sprites were 6 px of
    the 16 px a step has at W = 128).
    `rails`: rail heights as fractions of `height`; a rail is at least
    one pixel up, the first row not covered by the ground.
    `posts`: intervals per edge, posts standing at both ends of each
    (so `posts + 1` per edge, equally spaced along the edge as it is
    in the world); 0 = no posts.
    """
    color: tuple[int, int, int]
    height: float
    rails: tuple[float, ...]
    posts: int


# Legacy (48, 64, 32) and (100, 50, 20), snapped to 5-bit points.
NATURAL = FenceStyle(color=(49, 66, 33), height=1 / 16,
                     rails=(1.0,), posts=0)
ARTIFICIAL = FenceStyle(color=(99, 49, 16), height=6 / 16,
                        rails=(1 / 3, 2 / 3), posts=8)


def mask_walls(mask: int) -> list[int]:
    """Back walls a fence mask covers, in wall order."""
    return [wall for wall in range(WALL_COUNT) if mask >> wall & 1]


def _lerp_int(a: int, b: int, k: int, n: int) -> int:
    """`a + (b - a) * k / n` in integers, rounded half up."""
    return a + ((b - a) * k * 2 + n) // (2 * n)


def render_fence(mask: int, artificial: bool,
                 geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one fence cell.

    Output is HxWx4 RGBA: fence pixels are opaque, everything else
    stays alpha=0 so makeobj's PNG -> RLE encoder skips them.
    """
    if not 1 <= mask <= MASK_COUNT:
        raise ValueError(f"fence mask {mask} outside 1..{MASK_COUNT}")
    if geom is None:
        geom = hex_synth.HexGeom()
    style = ARTIFICIAL if artificial else NATURAL

    top = max(1, round(style.height * geom.lift))
    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)

    for wall in mask_walls(mask):
        a, b = hex_synth.CLIFF_WALL_ENDPOINTS[wall]
        ax, ay = geom.vx[a], geom.vy_base[a]
        bx, by = geom.vx[b], geom.vy_base[b]

        for frac in style.rails:
            rise = max(1, round(frac * top))
            hex_synth.draw_line(buf, ax, ay - rise, bx, by - rise,
                                style.color)
        if style.posts:
            for k in range(style.posts + 1):
                px = _lerp_int(ax, bx, k, style.posts)
                py = _lerp_int(ay, by, k, style.posts)
                hex_synth.draw_line(buf, px, py, px, py - top, style.color)
    return buf


def main():
    p = argparse.ArgumentParser(description="Render one hex fence cell.")
    p.add_argument("mask", type=int, choices=range(1, MASK_COUNT + 1),
                   help="edge subset: 1 = NW, 2 = N, 4 = NE, summed")
    p.add_argument("flavor", choices=("natural", "artificial"),
                   help="natural ground or building (artificial) ground")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    cell = render_fence(args.mask, artificial=(args.flavor == "artificial"),
                        geom=geom)
    Image.fromarray(cell, mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
