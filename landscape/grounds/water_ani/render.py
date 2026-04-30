#!/usr/bin/env python3
"""Canonical renderer for the hex pakset's animated open-water cells.

Per-(depth, stage) cell carrying the flat hex silhouette filled with
a procedural sparkle pattern.  No engine `synth_overlay::*` reference
exists for water (unlike lightmap / borders / marker), so the
renderer is the source of truth; the diff against the legacy square
`water_ani.png` is qualitative — see `compare.py`.

Style mirrors the legacy: dark navy base + sparse glint pixels that
re-position between frames rather than fade in place.  Calibrated
against the legacy mean RGB, which is bit-identical across all 32
stages at each depth ((79, 90, 117) at depth 0 → (62, 70, 91) at
depth 5).  Reproduce the constant-mean property by hashing
`(x, y, stage)` and stable-sorting in-silhouette pixels: brightening
the top-K with constant K gives bit-identical per-frame DC.

Outside the hex silhouette is `alpha = 0` (matching borders / marker),
not the `(231, 255, 255)` transparency-key colour the legacy uses.

Usage:
    render.py <stage> <out.png> [--depth D]   # one frame
    build_pakset.py                            # bake the full atlas
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


# Number of (depth, stage) axes — match the legacy pak128 water_ani
# exactly.  Both axes are consumed: wasser_t::display calls
# `sea->get_image(depth, stage)` with the running animation stage on
# every depth tier (so all 6 × 32 cells must be declared, not just
# depth 0); the engine clamps the depth axis at `water_depth_levels =
# count - 2` per `ground_desc.cc::register_desc`.
N_DEPTHS = 6
N_STAGES = 32

# Base + glint colours at depth 0.  At GLINT_FRACTION = 0.12, the
# convex combination 0.88 * BASE + 0.12 * GLINT lands within ~1 RGB
# unit of the legacy depth-0 mean (79, 90, 117).  Both colours scale
# linearly to LEGACY_DEEPEST_FACTOR at depth N_DEPTHS - 1, where the
# legacy mean is (62, 70, 91) — average per-channel ratio 0.78.
WATER_BASE_RGB = (75, 86, 112)
GLINT_RGB = (110, 130, 160)
LEGACY_DEEPEST_FACTOR = 0.78

# Top-K glint promotion: K = round(GLINT_FRACTION * n_inside_silhouette)
# is constant per stage, so the per-frame DC is bit-identical across
# stages — matching the legacy's bit-identical mean across its 32
# frames.  Per-pixel phase staggers a slow-stage ratchet so glints
# persist for GLINT_PERSISTENCE frames before re-hashing, dropping
# motion energy / cycle to roughly 1 / GLINT_PERSISTENCE of full
# re-hash; tuned against the legacy's measured ~200 / cycle.
GLINT_FRACTION = 0.12
GLINT_PERSISTENCE = 8


def depth_shade_factor(depth: int) -> float:
    if N_DEPTHS <= 1:
        return 1.0
    return 1.0 - (depth / (N_DEPTHS - 1)) * (1.0 - LEGACY_DEEPEST_FACTOR)


def _shade(rgb, factor):
    return tuple(int(round(c * factor)) for c in rgb)


def _stage_hash(xs: np.ndarray, ys: np.ndarray, stage: int) -> np.ndarray:
    """Per-pixel pseudo-random integer keyed on (x, y, slow_stage).

    A static per-pixel phase staggers when each pixel's slow_stage
    advances, so consecutive frames re-hash only ~1 / GLINT_PERSISTENCE
    of pixels.  Multiply-XOR-mix is cheap and deterministic — not a
    real PRNG, just enough decorrelation between slow_stages.
    """
    xs_u = xs.astype(np.uint32)
    ys_u = ys.astype(np.uint32)
    phase = (xs_u * np.uint32(0x12345) + ys_u * np.uint32(0x67891)) \
        % np.uint32(GLINT_PERSISTENCE)
    slow_stage = (np.uint32(stage) + phase) // np.uint32(GLINT_PERSISTENCE)

    h = (xs_u * np.uint32(0x9E3779B1)) ^ \
        (ys_u * np.uint32(0x85EBCA6B)) ^ \
        (slow_stage * np.uint32(0xC2B2AE35))
    h ^= h >> np.uint32(13)
    h = (h * np.uint32(0x27D4EB2D)) & np.uint32(0xFFFFFFFF)
    h ^= h >> np.uint32(15)
    return h


def render_water(stage: int, depth: int = 0,
                 geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    """Render one (depth, stage) cell of flat hex water.

    HxWx4 RGBA: depth-shaded base colour inside the hex silhouette,
    `alpha = 0` outside; top-K of those pixels get the depth-shaded
    glint colour.  The speckle pattern is identical across depths —
    only the palette darkens.
    """
    if geom is None:
        geom = hex_synth.HexGeom()
    if not (0 <= stage < N_STAGES):
        raise ValueError(f"stage {stage} out of range [0, {N_STAGES})")
    if not (0 <= depth < N_DEPTHS):
        raise ValueError(f"depth {depth} out of range [0, {N_DEPTHS})")

    factor = depth_shade_factor(depth)
    base_rgb = _shade(WATER_BASE_RGB, factor)
    glint_rgb = _shade(GLINT_RGB, factor)

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    xs_poly, ys_poly = list(geom.vx), geom.lifted_vy(0)
    hex_synth.fill_polygon(buf, xs_poly, ys_poly, base_rgb)
    hex_synth.seal_horizontal_edges(buf, xs_poly, ys_poly, base_rgb)

    # Stable sort + constant K = exactly K glints per stage regardless
    # of hash collisions, so per-frame DC is bit-identical.
    inside = np.argwhere(buf[..., 3] > 0)  # (Npx, 2) array of [y, x]
    k = int(round(GLINT_FRACTION * inside.shape[0]))
    if k > 0:
        h = _stage_hash(inside[:, 1], inside[:, 0], stage)
        glint = inside[np.argsort(h, kind="stable")[-k:]]
        buf[glint[:, 0], glint[:, 1], :3] = glint_rgb

    return buf


def main():
    p = argparse.ArgumentParser(description="Render one (depth, stage) cell of hex open water.")
    p.add_argument("stage", type=int, help=f"animation stage (0..{N_STAGES - 1})")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--depth", type=int, default=0,
                   help=f"depth tier (0..{N_DEPTHS - 1}; 0 = shallow / animated)")
    p.add_argument("--w", type=int, default=hex_synth.DEFAULT_W,
                   help=f"raster tile width (default {hex_synth.DEFAULT_W})")
    args = p.parse_args()

    geom = hex_synth.HexGeom(raster_w=args.w)
    Image.fromarray(render_water(args.stage, depth=args.depth, geom=geom),
                    mode="RGBA").save(str(args.out))


if __name__ == "__main__":
    main()
