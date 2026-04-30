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
    iter_region_polygons,
    iter_valid_slopes,
    lambert_brightness,
    seal_horizontal_edges,
    slope_is_valid,
)


# Engine reserved palette (engine `descriptor/image.cc::rgbtab`).  Any
# opaque pixel whose RGB888 matches one of these is encoded by makeobj
# (`descriptor/writer/image_writer.cc::pixrgb_to_pixval`) as a
# special-color PIXVAL `0x8000+i` instead of a normal RGB555.  The
# runtime `create_textured_tile` then mis-reads the `0x80…` bits as
# RGB555 channels, producing a bogus tint that scales with the climate
# texture — see TODO note on slope 336 for the symptom.  The lightmap's
# uniform-grey Lambert ramp lands exactly on `0x6B6B6B` (= 107) at one
# brightness level, hence the dodge below.
_RGBTAB_RESERVED = frozenset({
    0x244B67, 0x395E7C, 0x4C7191, 0x6084A7,
    0x7497BD, 0x88ABD3, 0x9CBEE9, 0xB0D2FF,
    0x7B5803, 0x8E6F04, 0xA18605, 0xB49D07,
    0xC6B408, 0xD9CB0A, 0xECE20B, 0xFFF90D,
    0x57656F, 0x7F9BF1, 0xFFFF53, 0xFF211D,
    0x01DD01, 0x6B6B6B, 0x9B9B9B, 0xB3B3B3,
    0xC9C9C9, 0xDFDFDF, 0xE3E3FF, 0xC1B1D1,
    0x4D4D4D, 0xFF017F, 0x0101FF,
})


def _safe_face_rgb(gray8: int) -> tuple[int, int, int]:
    """Uniform-grey `(g, g, g)` unless that triple is one of the engine's
    reserved palette entries, in which case nudge blue by ±1.

    The pakset side has to dodge the reserved palette because makeobj
    encodes any matching opaque pixel as a special-color PIXVAL —
    perceptually identical 5-bit grey, catastrophic at multiply time.
    Nudging by 1 RGB8 unit shifts under the same RGB555 quantisation
    bucket as the original on every collision (the reserved greys are
    spaced by ≥ 16 RGB8 units), so `create_textured_tile` produces
    bit-identical output on the non-collision path.
    """
    triple = (gray8 << 16) | (gray8 << 8) | gray8
    if triple not in _RGBTAB_RESERVED:
        return (gray8, gray8, gray8)
    nudged = gray8 - 1 if gray8 > 0 else gray8 + 1
    return (gray8, gray8, nudged)


def _region_brightness(region: list[int], slope: int, geom: HexGeom) -> int:
    """Lambert brightness for one region from its first non-degenerate
    triangle.  Returns 256 (= 1.0×) if the region is fully collinear.
    """
    ch = decode_corner_heights(slope)
    vy = geom.lifted_vy(slope)
    i0 = region[0]
    for k in range(2, len(region)):
        i1 = region[k - 1]
        i2 = region[k]
        ax = geom.vx[i1] - geom.vx[i0]
        ay = vy[i1] - vy[i0]
        az = (ch[i1] - ch[i0]) * geom.lift
        bx = geom.vx[i2] - geom.vx[i0]
        by = vy[i2] - vy[i0]
        bz = (ch[i2] - ch[i0]) * geom.lift
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx
        if nx == 0.0 and ny == 0.0 and nz == 0.0:
            continue
        if nz < 0.0:
            nx, ny, nz = -nx, -ny, -nz
        return lambert_brightness(nx, ny, nz)
    return lambert_brightness(0.0, 0.0, 1.0)


def render_lightmap(slope: int, geom: HexGeom | None = None) -> np.ndarray:
    """Render one slope's lightmap cell.

    Per-region grayscale = `brightness/16` (5-bit), expanded to RGB8
    with the same `(c5*255+15)/31` rounding the engine uses.  Brightness
    256 (1.0×) lands at 5-bit value 16, RGB8 ~132 — matches pak128's
    identity-multiplier convention so `create_textured_tile` returns the
    biome texture unchanged on flat tiles.

    Hex shape is carried in the alpha channel (255 inside, 0 outside).
    The engine's `create_textured_tile` walks the lightmap RLE, so the
    transparent border becomes the implicit hex mask in the final
    composited tile.  Region iteration goes through
    `hex_synth.iter_region_polygons` so `silhouette_mask` can't drift
    away from this baker's silhouette by construction.
    """
    if geom is None:
        geom = HexGeom()

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    for region, xs, ys in iter_region_polygons(slope, geom):
        brightness = _region_brightness(region, slope, geom)
        gray5 = min(brightness // 16, 31)
        gray8 = (gray5 * 255 + 15) // 31
        face_rgb = _safe_face_rgb(gray8)
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
