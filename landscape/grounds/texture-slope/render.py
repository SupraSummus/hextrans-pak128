#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's slope-transition cells.

Per `(slope, corner_mask)` cell carrying the alpha mask used by the
engine for two related transitions:

  * **Climate-corner mixing** — `grund.cc::display` calls
        draw_alpha(get_climate_tile(higher_climate, slope),
                   get_alpha_tile(slope, climate_corners),
                   ALPHA_GREEN | ALPHA_BLUE, ...)
    on each corner that has a same-height neighbour at a higher
    climate.  RED → base climate stays; GREEN or BLUE → higher
    climate's texture wins.

  * **Snowline transition** — `grund.cc::display` calls
        draw_alpha(get_snow_tile(slope), get_alpha_tile(slope),
                   ALPHA_GREEN | ALPHA_BLUE, ...)            // case 1
        draw_alpha(get_snow_tile(slope), get_alpha_tile(slope),
                   ALPHA_BLUE, ...)                          // case 2
    when the snowline crosses this tile.  Case 1 is the snowline
    sitting at this tile's flat ground (snow over the whole top of
    the slope); case 2 is the snowline crossing mid-slope, with
    snow only on the highest corners.  The engine routes both
    through `get_alpha_tile(slope, mask)` with `mask` = the slope's
    high-corners mask — the cell's RED/GREEN/BLUE bands map to the
    two alpha-flag readers:

      RED   — alpha=0 under both keys.  Base ground stays.
      GREEN — opaque under ALPHA_GREEN | ALPHA_BLUE; transparent
              under ALPHA_BLUE alone.  Transition shows on case 1
              (full snowline / climate transition) but not case 2
              (mid-slope snowline).
      BLUE  — opaque under both keys.  Transition always shows
              wherever this band sits (the highest mask region).

`corner_mask` is the 6-bit hex-corner mask `grund.cc` passes for
climate transitions, plus the `high_corners_of(slope)` mask the
engine derives for the snowline transition (corners with
`corner_height(slope, i) > 0`, since slopes are normalised to
`min(ch) == 0`).  Wetness across the tile is the centre-fan
barycentric mix of corner mask values, identical in shape to
`texture-shore/render.py`'s wetness field — only the band
quantisation differs (3 bands here vs. shore's 2).

Hex silhouette is the slope's lifted-corner hexagon (via
`hex_synth.silhouette_mask`, matching the `LightTexture` cell
silhouette pixel-for-pixel) — `draw_alpha` walks each pixel
position directly without perspective unwarp, so cell + lightmap
silhouette must agree.

Usage:
    render.py <slope> <mask> <out.png>   # one slope-trans cell
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


# Three-colour alpha palette.  See docstring for which engine alpha
# key reads each band.  RGB choices keep masked alpha values clean:
# pure red has G=B=0 (ALPHA_GREEN|ALPHA_BLUE → alpha 0); pure green
# has B=0 (ALPHA_BLUE → alpha 0); pure blue has G=0 — but its
# B channel sums with green's G channel under ALPHA_GREEN|ALPHA_BLUE
# only via different pixels, never within one pixel.
SLOPE_RED   = np.array([255, 0,   0,   255], dtype=np.uint8)
SLOPE_GREEN = np.array([0,   255, 0,   255], dtype=np.uint8)
SLOPE_BLUE  = np.array([0,   0,   255, 255], dtype=np.uint8)


def render_slope(slope: int, corner_mask: int,
                 geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one `(slope, corner_mask)` slope-transition cell.

    Output is HxWx4 RGBA.  Alpha mask is `hex_synth.silhouette_mask`,
    bit-identical to the lightmap baker's silhouette so the engine's
    `draw_alpha` walks source and alpha streams in lockstep without
    a runtime normalisation cache.  Inside pixels carry RED, GREEN,
    or BLUE chosen by dithered strength bands; outside pixels stay
    alpha=0.

    Strength is `hex_synth.centre_fan_field` with `centre =
    mean(corners)` — symmetric (no shore-style land bias; climate
    transitions don't have a "background" the field should retreat
    towards).  Band thresholds: 1/3 (RED→GREEN) and 2/3 (GREEN→BLUE),
    with a ±0.4 hashed-noise jitter so the boundaries fuzz across
    ~6 px per band rather than collapsing to clean lines.
    """
    if geom is None:
        geom = hex_synth.HexGeom()

    silhouette = hex_synth.silhouette_mask(slope, geom)
    weight = [(corner_mask >> i) & 1 for i in range(hex_synth.CORNER_COUNT)]
    strength = hex_synth.centre_fan_field(slope, weight,
                                          sum(weight) / hex_synth.CORNER_COUNT,
                                          geom)

    xs = np.arange(geom.w, dtype=np.uint32)
    ys = np.arange(geom.h, dtype=np.uint32)
    gx, gy = np.meshgrid(xs, ys)
    jitter = (hex_synth.hash_noise01(gx, gy) - 0.5) * 0.8
    s = strength + jitter

    is_blue  = silhouette & (s >= 2.0 / 3.0)
    is_green = silhouette & (s >= 1.0 / 3.0) & ~is_blue
    is_red   = silhouette & ~is_blue & ~is_green

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    buf[is_red]   = SLOPE_RED
    buf[is_green] = SLOPE_GREEN
    buf[is_blue]  = SLOPE_BLUE
    return buf


def main():
    p = argparse.ArgumentParser(
        description="Render one (slope, corner_mask) slope-transition cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("mask", type=int,
                   help="6-bit corner mask (1..63); bit i = corner i transitions")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    cell = render_slope(args.slope, args.mask, geom=geom)
    Image.fromarray(cell, mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
