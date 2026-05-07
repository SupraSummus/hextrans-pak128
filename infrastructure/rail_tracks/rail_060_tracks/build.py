#!/usr/bin/env python3
"""Crop pak128 references, render rail_060 in both projections, diff
each square render against its reference cell.  Hex per-cell bbox is
reported by `scene.bake_pakset()` itself; no hex reference art exists
yet, so no hex diff."""
from __future__ import annotations

from pathlib import Path

from tools.threed import way_verify

from . import scene


HERE = Path(__file__).resolve().parent


if __name__ == "__main__":
    way_verify.verify_square(
        scene_mod=scene,
        sheet_path=HERE.parent / "rail_060_tracks.png",
        here=HERE,
    )
