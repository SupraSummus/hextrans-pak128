#!/usr/bin/env python3
"""Crop the legacy pak128 cells, render rail_200_tunnel in both
projections, diff each square render against its reference cell."""
from infrastructure.tunnel_params import verify_tunnel

from . import scene


if __name__ == "__main__":
    verify_tunnel(scene)
