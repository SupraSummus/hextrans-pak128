#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's shore-transition cells.

Per `(slope, water_mask)` cell carrying an **ALPHA_RED-keyed alpha
mask** for water tiles drawn on a beach-bordering hex.  The engine's
`grund.cc::display` calls

    draw_alpha(get_water_tile(slope, stage),
               get_beach_tile(slope, water_corners),
               ALPHA_RED, ...)

so only the **red channel** of this image's pixels is read as alpha
intensity (`(masked & 0x7c00) >> 5` → 0..31).  Two colours are
enough: pure red where water shows fully, pure blue where it's
suppressed (climate ground wins).  A position-deterministic
hashed dither at the wet/dry boundary preserves the gritty,
soft-edge look of the legacy `texture-shore.png` rather than
collapsing to a clean line.

`water_mask` is the 6-bit hex-corner mask `grund.cc` builds from
`vertex_corner_height(...) == water_climate` checks: bit `i` set
means hex corner `i` (E=0, SE=1, SW=2, W=3, NW=4, NE=5) is at sea
level and bordered by water climate.  Wetness across the tile is
the centre-fan barycentric mix of corner wetness, so a
single-water-corner tile fades from red at that corner out to
blue at the opposite side.

Hex silhouette is the slope's lifted-corner hexagon (matches the
`LightTexture` cell's silhouette pixel-for-pixel) — the engine's
`draw_alpha` samples each pixel position directly without
perspective unwarp, so cell + lightmap silhouette must agree.

Usage:
    render.py <slope> <mask> <out.png>   # one shore cell
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


# ALPHA_RED-keyed two-colour palette.  Engine reads only the red
# channel as alpha (`mask & 0x7c00`), so blue's RGB doesn't matter
# beyond `R == 0` — picked to match the legacy art's dominant cold
# colour (`(0, 0, 255)` had ~75% of legacy non-red pixels) so the
# raw atlas reads similarly under any future image-channel debug.
SHORE_RED  = np.array([255, 0,   0,   255], dtype=np.uint8)
SHORE_BLUE = np.array([0,   0,   255, 255], dtype=np.uint8)


def render_shore(slope: int, water_mask: int,
                 geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one `(slope, water_mask)` shore-transition cell.

    Output is HxWx4 RGBA.  Alpha mask is `hex_synth.silhouette_mask`,
    bit-identical to the lightmap baker's silhouette so the engine's
    `draw_alpha` walks source and alpha streams in lockstep without
    a runtime normalisation cache.  Inside pixels carry `RED` or
    `BLUE` chosen by dithered wetness; outside pixels stay alpha=0.

    Wetness is `hex_synth.centre_fan_field` with `centre = 0.0` —
    pinning the centre dry keeps a land bite even when all 6 corners
    border water (a 1×1 island still reads as land with a water
    rim).  The overlay is only ever drawn on land tiles
    (`grund.cc::display`'s `if(get_typ()!=wasser)` branch), so a
    centre that grew with corner wetness would defeat the point.
    """
    if geom is None:
        geom = hex_synth.HexGeom()

    silhouette = hex_synth.silhouette_mask(slope, geom)
    wet = [(water_mask >> i) & 1 for i in range(hex_synth.CORNER_COUNT)]
    wetness = hex_synth.centre_fan_field(slope, wet, 0.0, geom)

    xs = np.arange(geom.w, dtype=np.uint32)
    ys = np.arange(geom.h, dtype=np.uint32)
    gx, gy = np.meshgrid(xs, ys)
    # Symmetric ±0.2 dither — keeps a soft gritty edge ~3 px wide
    # without smearing the wet/dry boundary.  Threshold 0.65 biases
    # the cut further toward land so the bake reads as "land tile
    # with a water bite", not "half-and-half blend".
    jitter = (hex_synth.hash_noise01(gx, gy) - 0.5) * 0.4

    is_wet = silhouette & ((wetness + jitter) >= 0.65)
    is_dry = silhouette & ~is_wet

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    buf[is_wet] = SHORE_RED
    buf[is_dry] = SHORE_BLUE
    return buf


def main():
    p = argparse.ArgumentParser(
        description="Render one (slope, water_mask) shore-transition cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("mask", type=int,
                   help="6-bit water-corner mask (1..63); bit i = corner i is water")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    cell = render_shore(args.slope, args.mask, geom=geom)
    Image.fromarray(cell, mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
