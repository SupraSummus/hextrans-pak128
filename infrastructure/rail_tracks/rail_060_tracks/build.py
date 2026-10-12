#!/usr/bin/env python3
"""Crop pak128 references, render rail_060 in both projections, diff
each square render against its reference cell.  Hex per-cell bbox is
reported by `scene.bake_pakset()` itself; no hex reference art exists
yet, so no hex diff."""
from infrastructure.rail_tracks.rail_params import verify_tier

from . import scene


if __name__ == "__main__":
    verify_tier(scene)
