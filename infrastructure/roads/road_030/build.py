#!/usr/bin/env python3
"""Crop pak128 references, render road_030 in both projections, diff
each square render against its reference cell.  Hex per-cell bbox is
reported by `scene.bake_pakset()`; no hex reference art exists yet."""
from infrastructure.roads.road_params import verify_tier

from . import scene


if __name__ == "__main__":
    verify_tier(scene)
