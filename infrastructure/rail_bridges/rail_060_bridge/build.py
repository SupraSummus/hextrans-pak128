#!/usr/bin/env python3
"""Crop pak128 references, render the rail_060 bridge in both projections,
diff each square render against its reference cell.

Mirrors `infrastructure/rail_tracks/rail_060_tracks/build.py` so the
two assets share one DX shape: refs table → crop → render → diff →
JSON metrics.

Pak128 layout (from rail_060_bridge.dat):

  row 1:  BackImage[NS][0]    .1.0  FrontImage[NS][0]   .1.1
          BackImage[EW][0]    .1.2  FrontImage[EW][0]   .1.3
          BackRamp[N][0]      .1.4  FrontRamp[N][0]     .1.5
          BackRamp[S][0]      .1.6  FrontRamp[S][0]     .1.7
  row 2:  BackRamp[E][0]      .2.0  FrontRamp[E][0]     .2.1
          BackRamp[W][0]      .2.2  FrontRamp[W][0]     .2.3
          BackStart[N][0]     .2.4  FrontStart[N][0]    .2.5
          BackStart[S][0]     .2.6  FrontStart[S][0]    .2.7
  row 3:  BackStart[E][0]     .3.0  FrontStart[E][0]    .3.1
          BackStart[W][0]     .3.2  FrontStart[W][0]    .3.3
          BackStart2[N][0]    .3.4  FrontStart2[N][0]   .3.5
          BackStart2[S][0]    .3.6  FrontStart2[S][0]   .3.7
  row 4:  BackStart2[E][0]    .4.0  FrontStart2[E][0]   .4.1
          BackStart2[W][0]    .4.2  FrontStart2[W][0]   .4.3
          backPillar[S][0]    .4.4  backPillar[W][0]    .4.5

Hex per-cell bbox is reported by `scene.bake_pakset()` itself.
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


SHEET = HERE.parent / "rail_060_bridge.png"

# (sheet row, sheet col, ref filename, candidate filename, label).
# Every entry the scene currently emits a candidate render for. New
# sheet entries get one row here when their 3D parts are wired in
# scene.py.
SQUARE_REFS = [
    (1, 0, "back_ns.png",  "out_back_ns.png",  "BackImage[NS][0]  (cell 1.0)"),
    (1, 1, "front_ns.png", "out_front_ns.png", "FrontImage[NS][0] (cell 1.1)"),
    (1, 2, "back_ew.png",  "out_back_ew.png",  "BackImage[EW][0]  (cell 1.2)"),
    (1, 3, "front_ew.png", "out_front_ew.png", "FrontImage[EW][0] (cell 1.3)"),
    (4, 4, "pillar_s.png", "out_pillar_s.png", "backPillar[S][0]  (cell 4.4)"),
    (4, 5, "pillar_w.png", "out_pillar_w.png", "backPillar[W][0]  (cell 4.5)"),
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
    for _row, _col, ref_name, cand_name, label in SQUARE_REFS:
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
