"""3D model of the rail_080b track (80 km/h heavy-duty): one tile, mid-segment.

Cross-section: timber ties on a redder gravel bed under lighter rails,
matching pak128 cells 1.5 / 1.6 in `rail_080b_tracks.png`.  All
tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_080B`.

Hex deliverable: the three atlases `rail_080b_tracks_hex.png`,
`rail_080b_tracks_hex_slope.png` and
`rail_080b_tracks_hex_slope_half.png`, referenced from the sibling
`rail_080b_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_080B, make_tier

CS, bake_pakset = make_tier(RAIL_080B)


if __name__ == "__main__":
    bake_pakset()
