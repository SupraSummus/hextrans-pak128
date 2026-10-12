#!/usr/bin/env python3
"""Crop pak128 references, render rail_120b in both projections, diff
each square render against its reference cell."""
from infrastructure.rail_tracks.rail_params import verify_tier

from . import scene


if __name__ == "__main__":
    verify_tier(scene)
