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
from `tools/threed/hex_synth.py` so the per-asset bakers (lightmap,
borders, …) share one definition of "what is a hex slope" and stay in
lockstep when the engine's synth_geometry constants move.

Usage:
    render.py <slope> <out.png>          # one lightmap cell
    build_pakset.py                      # bake the full atlas
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed.hex_synth import (
    DEFAULT_W,
    HexGeom,
    fill_polygon,
    iter_region_polygons,
    region_brightness,
    seal_horizontal_edges,
)
from tools.threed.lightmap import brightness_to_grey_rgb


def render_lightmap(slope: int, geom: HexGeom | None = None) -> np.ndarray:
    """Render one slope's lightmap cell.

    Per-region Lambert brightness encoded as a 5-bit grey via
    `brightness_to_grey_rgb` — see `tools/threed/lightmap.py` for the
    `create_textured_tile` multiplier convention and the reserved-
    palette dodge.

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
        face_rgb = brightness_to_grey_rgb(region_brightness(region, slope, geom))
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
