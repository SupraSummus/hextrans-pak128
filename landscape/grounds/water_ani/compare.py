#!/usr/bin/env python3
"""Side-by-side comparison of legacy square water_ani vs. the hex bake.

Produces one PNG strip per atlas (32 frames laid out as 8×4) plus a
per-frame stats table on stderr.  No engine ground truth exists for
water, so the comparison is qualitative — the strip is for the eye,
the stats catch gross amplitude / loop-closure mismatches the eye misses.

Legacy convention: outside-silhouette pixels carry the special
transparency-key colour (231, 255, 255).  This script remaps that to
alpha=0 before comparing, so silhouette-shape and inside-colour are
the only signals.

Usage:
    python3 compare.py [--out compare.png]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[3]
NEW_PATH = REPO_ROOT / "landscape" / "grounds" / "water_ani.png"
# The hex bake overwrites the upstream pak128 water_ani.png, so we keep a
# copy of the upstream art alongside this script for the eval to compare
# against.  Lives in the model dir (which makeobj does not scan), so it's
# not packaged into the pakset — it's reference data, kin to the bridge
# `refs/` caches.
LEGACY_DEFAULT = Path(__file__).resolve().parent / "legacy_reference.png"

CELL = 128
LEGACY_TRANSPARENT_RGB = (231, 255, 255)


def load_legacy(path: Path, depth: int) -> list[np.ndarray]:
    """Return 32 RGBA cells from the legacy row corresponding to `depth`.

    The legacy `Image[depth][0-31]` lives in PNG row `depth + 1` (row 0
    is unused in the legacy atlas).
    """
    a = np.array(Image.open(path).convert("RGBA"))
    cells = []
    r = depth + 1
    for c in range(32):
        cell = a[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL].copy()
        # Remap transparency-key to alpha=0 so silhouette compares cleanly.
        key = (
            (cell[..., 0] == LEGACY_TRANSPARENT_RGB[0]) &
            (cell[..., 1] == LEGACY_TRANSPARENT_RGB[1]) &
            (cell[..., 2] == LEGACY_TRANSPARENT_RGB[2])
        )
        cell[key, 3] = 0
        cells.append(cell)
    return cells


def _atlas_cell(a: np.ndarray, idx: int, cols: int) -> np.ndarray:
    r, c = divmod(idx, cols)
    return a[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL].copy()


def load_new(path: Path, depth: int, stage: int) -> np.ndarray:
    """One (depth, stage) cell — atlas is depth-major, 32 stages per depth."""
    a = np.array(Image.open(path).convert("RGBA"))
    cols = a.shape[1] // CELL
    return _atlas_cell(a, depth * 32 + stage, cols)


def load_new_depth(path: Path, depth: int) -> list[np.ndarray]:
    """All 32 stages of a single depth tier — for motion-energy comparison."""
    return [load_new(path, depth, s) for s in range(32)]


def cell_stats(cell: np.ndarray):
    """Per-cell mean RGB, stddev, and inside-silhouette pixel count."""
    mask = cell[..., 3] > 0
    n = int(mask.sum())
    if n == 0:
        return n, np.zeros(3), np.zeros(3)
    rgb = cell[mask, :3].astype(np.float32)
    return n, rgb.mean(axis=0), rgb.std(axis=0)


def motion_energy(cells: list[np.ndarray]) -> float:
    """Sum of per-frame L2 differences over the closed cycle.

    Comparable across atlases: bigger = more shimmer per cycle.
    """
    total = 0.0
    n = len(cells)
    for t in range(n):
        a = cells[t][..., :3].astype(np.float32)
        b = cells[(t + 1) % n][..., :3].astype(np.float32)
        # Mask to pixels opaque in both — compares only inside the silhouette.
        ma = cells[t][..., 3] > 0
        mb = cells[(t + 1) % n][..., 3] > 0
        m = ma & mb
        if m.sum() == 0:
            continue
        diff = (a - b)[m]
        total += float(np.sqrt((diff * diff).sum() / m.sum()))
    return total


def composite_alpha(cell: np.ndarray, bg=(64, 64, 64)) -> np.ndarray:
    """Flatten alpha onto a neutral grey so the silhouette reads in PNG."""
    rgb = cell[..., :3].astype(np.float32)
    a = (cell[..., 3:4].astype(np.float32)) / 255.0
    bg_arr = np.array(bg, dtype=np.float32)
    out = rgb * a + bg_arr * (1.0 - a)
    return out.clip(0, 255).astype(np.uint8)


def build_strip(legacy: list[np.ndarray], new: list[np.ndarray]) -> np.ndarray:
    """Two rows of 32 cells: top legacy, bottom new (each at native CELL height)."""
    strip = np.zeros((2 * CELL, 32 * CELL, 3), dtype=np.uint8)
    for i, cell in enumerate(legacy):
        strip[0:CELL, i * CELL:(i + 1) * CELL] = composite_alpha(cell)
    for i, cell in enumerate(new):
        strip[CELL:2 * CELL, i * CELL:(i + 1) * CELL] = composite_alpha(cell)
    return strip


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--legacy", type=Path, default=LEGACY_DEFAULT,
                   help=f"path to the legacy square water_ani.png "
                        f"(default {LEGACY_DEFAULT.name} alongside this script)")
    p.add_argument("--new", type=Path, default=NEW_PATH,
                   help=f"new hex water_ani.png (default {NEW_PATH})")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "compare.png",
                   help="output side-by-side strip PNG (depth 0 animation)")
    args = p.parse_args()

    legacy = load_legacy(args.legacy, depth=0)
    new = load_new_depth(args.new, depth=0)

    def fmt_rgb(v):
        return f"({v[0]:5.1f},{v[1]:5.1f},{v[2]:5.1f})"

    print(f"{'stage':>5}  {'old px':>7} {'old mean RGB':>20} {'old std':>6}"
          f"    {'new px':>7} {'new mean RGB':>20} {'new std':>6}",
          file=sys.stderr)
    for t in range(32):
        n_o, mean_o, std_o = cell_stats(legacy[t])
        n_n, mean_n, std_n = cell_stats(new[t])
        print(f"{t:>5}  {n_o:>7} {fmt_rgb(mean_o):>20} {std_o.mean():>6.2f}"
              f"    {n_n:>7} {fmt_rgb(mean_n):>20} {std_n.mean():>6.2f}",
              file=sys.stderr)

    print(f"\nmotion energy / cycle  old={motion_energy(legacy):8.2f}   "
          f"new={motion_energy(new):8.2f}", file=sys.stderr)

    print(f"\ndepth tier mean RGB (stage 0):", file=sys.stderr)
    print(f"{'depth':>6} {'legacy':>20} {'new':>20}", file=sys.stderr)
    for d in range(6):
        _, mean_lg, _ = cell_stats(load_legacy(args.legacy, depth=d)[0])
        _, mean_new, _ = cell_stats(load_new(args.new, depth=d, stage=0))
        print(f"{d:>6} {fmt_rgb(mean_lg):>20} {fmt_rgb(mean_new):>20}",
              file=sys.stderr)

    Image.fromarray(build_strip(legacy, new), mode="RGB").save(str(args.out))
    print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
