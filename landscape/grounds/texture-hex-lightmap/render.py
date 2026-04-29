#!/usr/bin/env python3
"""Canonical renderer for the hex ground pakset's lightmap cells.

The pakset deliverable splits per-tile geometry from per-climate biome
art exactly the way pak128 does: a grayscale lightmap PNG carries the
hex silhouette and the per-region Lambert shading; pak128's existing
`texture-climate.png` carries the biome colours unchanged.  At runtime
the engine multiplies the two via `create_textured_tile`, so we never
need to bake climate colours into a candidate render — only the
lightmap.

An earlier crash-fast probe validated bit-for-bit that this renderer
reproduces the engine's `synth_overlay::rasterise_ground` flat-tile
output across all 8 climates, so we trust the documented constants in
`synth_geometry.h` (vertex layout, lift, light direction, shade math,
fill convention).  Going forward this script *is* the canonical source
of truth for the hex ground deliverable; the engine's in-process synth
path is just a runtime fallback floor.

Per-region shading uses a Python port of
`synth_plane_partition.h::find_min_partition` so multi-region slopes
(saddles, wedges) get one Lambert face per coplanar region rather than
a single average shade.

Geometry, slope decoding, partitioning, and polygon fill are pulled
from `tools/3d/hex_synth.py` so the per-asset bakers (lightmap,
borders, …) share one definition of "what is a hex slope" and stay in
lockstep when the engine's synth_geometry constants move.

Usage:
    render.py <slope> <out.png>          # one lightmap cell
    build_pakset.py                      # bake the full atlas
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Make `tools/3d/` importable from the per-asset bake dir.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "tools" / "3d"))

import hex_synth  # noqa: E402
from hex_synth import (  # noqa: E402
    DEFAULT_W,
    HexGeom,
    CORNER_COUNT,
    E, SE, SW, W_C, NW, NE,
    decode_corner_heights,
    fill_polygon,
    find_min_partition,
    iter_valid_slopes,
    lambert_brightness,
    seal_horizontal_edges,
    slope_is_valid,
)


def _per_region_brightness(slope: int, geom: HexGeom, partition: list[list[int]]):
    """Yield (region, xs, ys, brightness) for each region in the partition.

    Pulled out so the lightmap path reuses the same per-region Lambert
    math without recomputing.  Other synth-overlay families (border,
    marker) don't need shading and use the geometry directly.
    """
    ch = decode_corner_heights(slope)
    vy = geom.lifted_vy(slope)

    for region in partition:
        if len(region) < 3:
            continue
        i0 = region[0]
        nx_v = ny_v = nz_v = 0.0
        have_normal = False
        for k in range(2, len(region)):
            i1 = region[k - 1]
            i2 = region[k]
            ax = geom.vx[i1] - geom.vx[i0]
            ay = vy[i1] - vy[i0]
            az = (ch[i1] - ch[i0]) * geom.lift
            bx = geom.vx[i2] - geom.vx[i0]
            by = vy[i2] - vy[i0]
            bz = (ch[i2] - ch[i0]) * geom.lift
            nx_v = ay * bz - az * by
            ny_v = az * bx - ax * bz
            nz_v = ax * by - ay * bx
            if nx_v != 0.0 or ny_v != 0.0 or nz_v != 0.0:
                have_normal = True
                break
        if not have_normal:
            nx_v, ny_v, nz_v = 0.0, 0.0, 1.0
        if nz_v < 0.0:
            nx_v, ny_v, nz_v = -nx_v, -ny_v, -nz_v

        brightness = lambert_brightness(nx_v, ny_v, nz_v)
        xs = [geom.vx[i] for i in region]
        ys = [vy[i] for i in region]
        yield region, xs, ys, brightness


def render_lightmap(slope: int, geom: HexGeom | None = None,
                    partition: list[list[int]] | None = None) -> np.ndarray:
    """Render one slope's lightmap cell.

    Per-region grayscale = `brightness/16` (5-bit), expanded to RGB8
    with the same `(c5*255+15)/31` rounding the engine uses.  Brightness
    256 (1.0×) lands at 5-bit value 16, RGB8 ~132 — matches pak128's
    identity-multiplier convention so `create_textured_tile` returns the
    biome texture unchanged on flat tiles.

    Hex shape is carried in the alpha channel (255 inside, 0 outside).
    The engine's `create_textured_tile` walks the lightmap RLE, so the
    transparent border becomes the implicit hex mask in the final
    composited tile.
    """
    if geom is None:
        geom = HexGeom()
    if partition is None:
        partition = find_min_partition(slope)

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    for _region, xs, ys, brightness in _per_region_brightness(slope, geom, partition):
        gray5 = brightness // 16
        if gray5 > 31:
            gray5 = 31
        gray8 = (gray5 * 255 + 15) // 31
        face_rgb = (gray8, gray8, gray8)
        fill_polygon(buf, xs, ys, face_rgb)
        seal_horizontal_edges(buf, xs, ys, face_rgb)

    return buf


def save_rgba(buf: np.ndarray, path: Path):
    Image.fromarray(buf, mode="RGBA").save(str(path))


def main():
    p = argparse.ArgumentParser(description="Render one hex slope as a grayscale "
                                            "lightmap cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=DEFAULT_W,
                   help=f"raster tile width (default {DEFAULT_W})")
    args = p.parse_args()

    geom = HexGeom(raster_w=args.w)
    save_rgba(render_lightmap(args.slope, geom=geom), args.out)


if __name__ == "__main__":
    main()
