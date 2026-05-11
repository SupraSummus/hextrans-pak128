#!/usr/bin/env python3
"""Canonical renderer for the hex sidewalk (city-road pavement) cells.

One cell per valid hex slope: a flat-top hex silhouette filled with
warm-grey concrete, per-region Lambert shading, `hash_noise01`-driven
gravel grit on top.  The engine composites the cell under the road
sprite when `weg_t::hat_gehweg()` is true; on flat ground it also
serves as the building's footpath sprite via `gebaeude.cc`.

Geometry, slope decoding, partitioning, and polygon fill come from
`tools/threed/hex_synth.py` so this baker stays in lockstep with the
rest of the parametric ground family (lightmap, borders, marker, …)
when the engine's `synth_geometry.h` constants move.

Usage:
    render.py <slope> <out.png>          # one sidewalk cell
    build_pakset.py                      # bake the full atlas + .dat
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
    hash_noise01,
    iter_region_polygons,
    region_brightness,
    seal_horizontal_edges,
)


# Single source of truth for the city-pavement grey, exported so the
# road bakers (`infrastructure/roads/road_params.RoadParams.sidewalk_color`)
# can key their kerb slabs off the same value — a road tile's kerb
# composites over the sidewalk ground tile under it (dither holes
# expose the underlay), and the tile-to-tile seam between a city road
# and a sidewalk-only neighbour reads as one continuous grey only if
# the two bakers agree.  Value is the median of pak128's upstream
# `src/sidewalk.png` flat cell — cool green-tinted mid-grey (G > R > B).
PAVEMENT_RGB: tuple[int, int, int] = (135, 143, 124)

# `BASE_RGB` is the brightness=256 (1.0×) shade — Lambert darkens it
# on tilted faces.  `NOISE_AMP` scatters per-pixel offsets in
# `[-NOISE_AMP/2, +NOISE_AMP/2]` for gravel grit; `hash_noise01`
# keeps the bake byte-stable across runs.
BASE_RGB = np.array(PAVEMENT_RGB, dtype=np.float32)
NOISE_AMP = np.float32(50.0)


def _shaded_rgb(brightness: int) -> tuple[int, int, int]:
    """Apply Lambert brightness to BASE_RGB and clamp to uint8."""
    shade = brightness / 256.0
    rgb = np.clip(BASE_RGB * shade, 0, 255).astype(np.uint8)
    return tuple(int(c) for c in rgb)


def render_sidewalk(slope: int, geom: HexGeom | None = None) -> np.ndarray:
    """Render one slope's sidewalk cell as HxWx4 RGBA.

    The hex silhouette is opaque (alpha=255) per region; pixels
    outside every coplanar region keep alpha=0 so the engine
    composites the cell against the road sprite without a halo.
    """
    if geom is None:
        geom = HexGeom()

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    for region, xs, ys in iter_region_polygons(slope, geom):
        rgb = _shaded_rgb(region_brightness(region, slope, geom))
        fill_polygon(buf, xs, ys, rgb)
        seal_horizontal_edges(buf, xs, ys, rgb)

    # Per-pixel grit on top of the lit base colour.  Apply only inside
    # the alpha mask so the surrounding pixels stay transparent and
    # makeobj's RLE encoder skips them at compile time.
    iy, ix = np.mgrid[0:geom.h, 0:geom.w]
    delta = ((hash_noise01(ix.astype(np.uint32), iy.astype(np.uint32))
              - 0.5) * NOISE_AMP)
    delta = (delta * (buf[..., 3] > 0))[..., None].astype(np.int16)
    buf[..., :3] = np.clip(buf[..., :3].astype(np.int16) + delta,
                           0, 255).astype(np.uint8)
    return buf


def main():
    p = argparse.ArgumentParser(description="Render one hex slope as a sidewalk cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=DEFAULT_W,
                   help=f"raster tile width (default {DEFAULT_W})")
    args = p.parse_args()

    geom = HexGeom(raster_w=args.w)
    Image.fromarray(render_sidewalk(args.slope, geom=geom),
                    mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
