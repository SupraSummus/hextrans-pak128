#!/usr/bin/env python3
"""Crop pak128 references, render rail_060_tunnel in both projections,
diff each square render against its reference cell.

Pak128 layout (from rail_060_tunnel.dat):

  row 0 (Front summer):  [N]=0.0  [W]=0.1  [S]=0.2  [E]=0.3
  row 1 (Back  summer):  [N]=1.0  [W]=1.1  [S]=1.2  [E]=1.3

Pak128 keys are *high-edge* naming ("[N]" means mountain at N, rails
enter from S), so the candidate that supervises against pak128 [N] is
the one rendered with rotation 180° (mountain pointing to +y in our
canonical NS frame).  See `scene.SQUARE_DIR_TO_ROT_DEG`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from tools.threed import crop_ref
from tools.threed import diff as diff_mod

from . import scene as scene_mod


HERE = Path(__file__).resolve().parent
# Legacy upstream art lives in `src/` — a subdir makeobj does not
# scan — so the deliverable shipped from `infrastructure/rail_tunnels/`
# is just the model-baked `rail_060_tunnel_hex.{png,dat}`.
SHEET = HERE / "src" / "rail_060_tunnel.png"

# (row, col) per direction in pak128's row-major layout above.
PAK128_CELLS = {
    "N": (0, 0), "W": (0, 1), "S": (0, 2), "E": (0, 3),  # front
    "n": (1, 0), "w": (1, 1), "s": (1, 2), "e": (1, 3),  # back (lowercase
                                                          # to disambiguate)
}

SQUARE_REFS = []
for direction in ("N", "S", "E", "W"):
    for layer, key_for_dat in (("front", direction), ("back", direction.lower())):
        row, col = PAK128_CELLS[key_for_dat]
        ref_name = f"{layer}_{direction.lower()}.png"
        cand_name = f"out_{layer}_{direction.lower()}.png"
        label = f"{layer.title()}Image[{direction}][0] (cell {row}.{col})"
        SQUARE_REFS.append((row, col, ref_name, cand_name, label))


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

    scene_mod.main()           # square candidates next to scene.py
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
