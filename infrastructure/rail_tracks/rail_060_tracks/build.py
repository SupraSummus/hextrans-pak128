#!/usr/bin/env python3
"""Crop pak128 references, render the rail_060 track in both projections,
diff each square render against its reference cell.

Pak128 layout (from rail_060_tracks.dat):
  Image[sw_ne][0] / Image[s_n][0] = rail_060_tracks.1.5
                      (square: track along world +y axis)
  Image[se_nw][0]                  = rail_060_tracks.1.6
                      (square: track along world +x axis)

Hex per-cell bbox is reported by `scene.bake_pakset()` itself (no
reference art yet, so no diff).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

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


def main() -> None:
    refs_dir = HERE / "refs"
    for row, col, ref_name, _cand, _label in SQUARE_REFS:
        crop_sheet_cell(row, col, refs_dir / ref_name)

    scene_mod.main()           # square verification renders next to scene.py
    scene_mod.bake_pakset()    # hex atlas + per-cell bbox summary

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


if __name__ == "__main__":
    main()
