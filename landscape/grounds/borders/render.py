#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's grid-border cells.

Per-slope cell carrying the **3 north-side edges** of the hex
outline at the slope's lifted vertices — open polyline E → NE →
NW → W — drawn over the tile when `grund_t::show_grid` is on.

Hex equivalent of square pak128's `borders.png` convention: each
tile only draws its top/back edges; the south neighbour's back
edges cover this tile's south side, so the union over all tiles
paints every grid edge exactly once.  Diverges from
`synth_overlay::build_border`, which draws a closed 6-edge outline
per tile (every shared edge twice) — the engine's synth path is a
runtime fallback floor and ships with debug-friendly redundancy;
the baked pakset deliverable follows the legacy art convention.

Style also follows the legacy: thin dark-grey lines on a
transparent background, not the engine's debug-yellow
`OUTLINE_COLOR = 0x7FE0`.

Usage:
    render.py <slope> <out.png>          # one border cell
    build_pakset.py                      # bake the full atlas
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


# Pak128 grid-line colour, matching the legacy `borders.png`.
OUTLINE_COLOR_RGB = (32, 32, 32)


def render_border(slope: int, geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one slope's grid-border cell.

    Output is HxWx4 RGBA: outline pixels along the back path are
    opaque dark-grey; everything else stays alpha=0 so makeobj's PNG →
    RLE encoder skips them at compile time.
    """
    if geom is None:
        geom = hex_synth.HexGeom()

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    hex_synth.rasterise_outline(buf, geom, slope, hex_synth.HEX_BACK_PATH,
                                OUTLINE_COLOR_RGB, closed=False)
    return buf


def main():
    p = argparse.ArgumentParser(description="Render one hex slope as a grid-border cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    Image.fromarray(render_border(args.slope, geom=geom), mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
