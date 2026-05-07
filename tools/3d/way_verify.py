"""Square-projection verification harness shared by way bakers.

Lays the asset's cross-section as world-axis-aligned straights under
the square dimetric camera, diffs each render against the matching
pak128 sheet cell, and runs the asset's hex bake — one entrypoint
per asset's `build.py`.

The pak128 sheet layout for through-tile straights is universal
across way classes (cell 1.5 = world +y straight = upstream "NS";
cell 1.6 = world +x straight = "EW"), so `verify_square` defaults
to that layout.  Assets with non-standard sheets pass an explicit
`straights` list.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image

import crop_ref
import diff as diff_mod
from render import Model, SquareCamera, render
from way_topology import CrossSection, StraightPath


# Standard pak128 way sheet straights — same row/col across rail,
# road, tram, etc.  Each entry: `(sheet_row, sheet_col, name,
# axis_yaw_deg, label)`.  `name` is the basename for the candidate /
# reference / debug PNGs; `axis_yaw_deg` rotates the world +y straight
# around z to match each cell's heading (0° → cell 1.5; 90° → cell 1.6).
DEFAULT_STRAIGHTS: list[tuple[int, int, str, float, str]] = [
    (1, 5, "square_ns", 0.0,  "square NS (cell 1.5 sw_ne / s_n)"),
    (1, 6, "square_ew", 90.0, "square EW (cell 1.6 se_nw)"),
]


def lay_square_straight(cs: CrossSection, model: Model, *,
                        axis_yaw_deg: float = 0.0,
                        length_half: float = 0.5) -> None:
    """Lay the cross-section as a `length_half × 2` chord along the
    world +y axis (rotated by `axis_yaw_deg` around z).  Used only
    for square-camera verification — hex output goes through
    `way_topology` builders."""
    yaw = math.radians(axis_yaw_deg)
    tx, ty = -math.sin(yaw), math.cos(yaw)
    start = (-length_half * tx, -length_half * ty)
    end = (+length_half * tx, +length_half * ty)
    perp = (-ty, tx)
    cs.paint_straight(model, StraightPath(
        start=start, end=end, cap_a=perp, cap_b=perp, role="full"))


def verify_square(*, scene_mod, sheet_path: Path, here: Path,
                  straights=None) -> None:
    """Crop refs, render candidates, run hex bake, diff each pair.

    `scene_mod` exposes `CS` (a `CrossSection`) and `bake_pakset()`
    (writes the hex atlases).  Per-pair outputs land next to
    `here`: `refs/<name>.png` (cropped pak128 cell), `out_<name>.png`
    (square render of the cross-section), `diff_debug_<name>.png`
    (side-by-side).  Metrics print as JSON.
    """
    straights = straights if straights is not None else DEFAULT_STRAIGHTS

    refs_dir = here / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(sheet_path).convert("RGB")
    for row, col, name, _yaw, _label in straights:
        tile = crop_ref.crop_tile(sheet, row, col, crop_ref.DEFAULT_TILE_SIZE)
        tile = crop_ref.mask_transparent(tile, crop_ref.PAK128_TRANSPARENT)
        tile.save(refs_dir / f"{name}.png")

    for _row, _col, name, yaw, _label in straights:
        m = Model()
        lay_square_straight(scene_mod.CS, m, axis_yaw_deg=yaw)
        render(m, SquareCamera(), out_path=str(here / f"out_{name}.png"))

    scene_mod.bake_pakset()

    print()
    for _row, _col, name, _yaw, label in straights:
        ref = diff_mod.load_rgba(refs_dir / f"{name}.png")
        cand = diff_mod.load_rgba(here / f"out_{name}.png")
        diff_mod.make_debug(ref, cand, here / f"diff_debug_{name}.png")
        print(f"=== {label} ===")
        json.dump(diff_mod.score(ref, cand), sys.stdout, indent=2)
        sys.stdout.write("\n")
