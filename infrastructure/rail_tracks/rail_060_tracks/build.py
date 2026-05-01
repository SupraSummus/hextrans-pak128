#!/usr/bin/env python3
"""Crop pak128 references, render the rail_060 track in both projections,
diff each square render against its reference cell.

Pak128 layout (from rail_060_tracks.dat):
  Image[sw_ne][0] / Image[s_n][0] = rail_060_tracks.1.5
                      (square: track along world +y axis)
  Image[se_nw][0]                  = rail_060_tracks.1.6
                      (square: track along world +x axis)

Hex per-cell PNGs are emitted by `build_pakset.main()` as a side-effect
of the atlas bake; this script bbox-checks them but doesn't diff (no
hex reference art yet).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

import build_pakset  # noqa: E402  # adjacent file (hex bake)
import crop_ref  # noqa: E402
import diff as diff_mod  # noqa: E402
import scene as scene_mod  # noqa: E402  # adjacent file


SHEET = HERE.parent / "rail_060_tracks.png"

SQUARE_REFS = [
    # (sheet row, sheet col, ref filename, candidate filename, label)
    (1, 5, "square_ns.png", "out_square_ns.png",
     "square NS (cell 1.5 sw_ne / s_n)"),
    (1, 6, "square_ew.png", "out_square_ew.png",
     "square EW (cell 1.6 se_nw)"),
]


def crop_sheet_cell(row: int, col: int, out: Path) -> None:
    sheet = Image.open(SHEET).convert("RGB")
    tile = crop_ref.crop_tile(sheet, row, col, crop_ref.DEFAULT_TILE_SIZE)
    tile = crop_ref.mask_transparent(tile, crop_ref.PAK128_TRANSPARENT)
    out.parent.mkdir(parents=True, exist_ok=True)
    tile.save(out)


def bbox_of(path: Path) -> tuple[int, int, int, int, int] | None:
    im = np.array(Image.open(path).convert("RGBA"))
    m = im[..., 3] > 0
    if not m.any():
        return None
    ys, xs = np.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()), int(m.sum())


def main() -> None:
    refs_dir = HERE / "refs"
    for row, col, ref_name, _cand, _label in SQUARE_REFS:
        crop_sheet_cell(row, col, refs_dir / ref_name)

    scene_mod.main()      # square verification renders next to scene.py
    build_pakset.main()   # hex atlas + per-cell out_hex_*.png

    print()
    for row, col, ref_name, cand_name, label in SQUARE_REFS:
        ref = diff_mod.load_rgba(refs_dir / ref_name)
        cand = diff_mod.load_rgba(HERE / cand_name)
        metrics = diff_mod.score(ref, cand)
        debug = HERE / f"diff_debug_{Path(cand_name).stem.replace('out_', '')}.png"
        diff_mod.make_debug(ref, cand, debug)
        print(f"=== {label} ===")
        json.dump(metrics, sys.stdout, indent=2)
        sys.stdout.write("\n")

    print("\n=== hex renders (bbox only; no reference yet) ===")
    for path in sorted(HERE.glob("out_hex_*.png")):
        name = path.stem.removeprefix("out_hex_")
        bb = bbox_of(path)
        if bb is None:
            print(f"  {name:7s} EMPTY")
        else:
            x0, y0, x1, y1, n = bb
            print(f"  {name:7s} bbox=({x0},{y0})-({x1},{y1}) px={n}")


if __name__ == "__main__":
    main()
