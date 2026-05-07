#!/usr/bin/env python3
"""Crop pak128 references, render road_040 in both projections, diff
each square render against its reference cell.  Hex per-cell bbox is
reported by `scene.bake_pakset()` itself; no hex reference art exists
yet, so no hex diff."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

import scene  # noqa: E402  # adjacent file
import way_verify  # noqa: E402


if __name__ == "__main__":
    way_verify.verify_square(
        scene_mod=scene,
        sheet_path=HERE.parent / "road_040.png",
        here=HERE,
    )
