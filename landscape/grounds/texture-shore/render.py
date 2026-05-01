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


def _hash_noise01(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Vectorised position-deterministic noise in `[0.0, 1.0)`.

    Pure function of `(x, y)` so the bake stays byte-stable across
    runs.  All ops run on `uint32` arrays — bit-for-bit identical to
    the previous scalar version of this hash, just looped by numpy
    instead of Python.
    """
    h = ((x.astype(np.uint32) * np.uint32(73856093))
         ^ (y.astype(np.uint32) * np.uint32(19349663)))
    h ^= h >> np.uint32(13)
    h *= np.uint32(1274126177)
    h ^= h >> np.uint32(16)
    return ((h & np.uint32(0xFFFF)).astype(np.float32)
            / np.float32(65536.0))


def _wetness_field(slope: int, water_mask: int,
                   geom: hex_synth.HexGeom) -> np.ndarray:
    """Per-pixel wetness ∈ [0, 1] over the full geom rectangle.

    Wetness is barycentric over each of the 6 centre-fan triangles
    `(corner_i, corner_(i+1), centre)` with centre wetness pinned
    to 0.  The overlay is only ever drawn on land tiles
    (`grund.cc::display`'s `if(get_typ()!=wasser)` branch), so a
    dry centre keeps a land bite even when all 6 corners border
    water — a 1×1 island still reads as land with a water rim.
    """
    vx = np.array(geom.vx, dtype=np.float32)
    vy = np.array(geom.lifted_vy(slope), dtype=np.float32)
    wet = np.array([(water_mask >> i) & 1 for i in range(hex_synth.CORNER_COUNT)],
                   dtype=np.float32)

    cx = float(vx.mean())
    cy = float(vy.mean())

    xs = np.arange(geom.w, dtype=np.float32) + 0.5
    ys = np.arange(geom.h, dtype=np.float32) + 0.5
    px, py = np.meshgrid(xs, ys)

    wetness = np.zeros((geom.h, geom.w), dtype=np.float32)
    assigned = np.zeros((geom.h, geom.w), dtype=bool)

    for i in range(hex_synth.CORNER_COUNT):
        j = (i + 1) % hex_synth.CORNER_COUNT
        ax, ay, aw = vx[i], vy[i], wet[i]
        bx, by, bw = vx[j], vy[j], wet[j]
        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if denom == 0.0:
            continue
        u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
        v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
        w = 1.0 - u - v
        in_tri = (u >= 0) & (v >= 0) & (w >= 0) & ~assigned
        wetness[in_tri] = u[in_tri] * aw + v[in_tri] * bw
        assigned |= in_tri

    return wetness


def render_shore(slope: int, water_mask: int,
                 geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one `(slope, water_mask)` shore-transition cell.

    Output is HxWx4 RGBA.  Alpha mask is `hex_synth.silhouette_mask`,
    bit-identical to the lightmap baker's silhouette so the engine's
    `draw_alpha` walks source and alpha streams in lockstep without
    a runtime normalisation cache.  Inside pixels carry `RED` or
    `BLUE` chosen by dithered wetness; outside pixels stay alpha=0.
    """
    if geom is None:
        geom = hex_synth.HexGeom()

    silhouette = hex_synth.silhouette_mask(slope, geom)
    wetness = _wetness_field(slope, water_mask, geom)

    xs = np.arange(geom.w, dtype=np.uint32)
    ys = np.arange(geom.h, dtype=np.uint32)
    gx, gy = np.meshgrid(xs, ys)
    # Symmetric ±0.2 dither — keeps a soft gritty edge ~3 px wide
    # without smearing the wet/dry boundary.  Threshold 0.65 biases
    # the cut further toward land so the bake reads as "land tile
    # with a water bite", not "half-and-half blend".
    jitter = (_hash_noise01(gx, gy) - 0.5) * 0.4

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
