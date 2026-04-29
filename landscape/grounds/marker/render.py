#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's marker cells.

Per-slope cell carrying **one half** of the hex outline at the
slope's lifted vertices, drawn as an open polyline:

  * front half: E → SE → SW → W (3 south-side edges)
  * back  half: E → NE → NW → W (3 north-side edges)

The two halves bracket tile content at draw time — back drawn
before vehicles/buildings, front drawn after — so the cursor
silhouette wraps around objects on the tile.  This mirrors
`synth_overlay::build_marker` in the engine.

Style follows the legacy pak128 cursor: bright orange lines
(255, 128, 0) on a transparent background, matching the only
non-background colour in the upstream `marker.png` this fork
overwrites.  Diverges from the engine's debug-yellow
`OUTLINE_COLOR = 0x7FE0` for the same reason borders does — the
engine's synth path ships with debug-friendly redundancy; the
baked pakset deliverable follows the legacy art convention.

Usage:
    render.py <slope> <half> <out.png>   # half ∈ {front, back}
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


# Marker colour — bright orange, matching the legacy pak128 cursor.
OUTLINE_COLOR_RGB = (255, 128, 0)


def render_marker(slope: int, background: bool,
                  geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one slope's marker half.

    `background=False` draws the front half (3 south-side edges);
    `background=True` draws the back half (3 north-side edges).
    Output is HxWx4 RGBA: outline pixels are opaque yellow,
    everything else stays alpha=0 so makeobj's PNG → RLE encoder
    skips them at compile time.
    """
    if geom is None:
        geom = hex_synth.HexGeom()

    path = hex_synth.HEX_BACK_PATH if background else hex_synth.HEX_FRONT_PATH
    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    hex_synth.rasterise_outline(buf, geom, slope, path,
                                OUTLINE_COLOR_RGB, closed=False)
    return buf


def main():
    p = argparse.ArgumentParser(description="Render one hex slope as a marker half cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("half", choices=("front", "back"),
                   help="which half to render")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    cell = render_marker(args.slope, background=(args.half == "back"), geom=geom)
    Image.fromarray(cell, mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
