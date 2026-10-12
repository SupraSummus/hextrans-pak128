"""3D model of the rail_400 track (400 km/h): one tile, mid-segment.

Cross-section: a concrete slab across the whole tile under white rails,
matching pak128 cells 1.5 / 1.6 in `rail_400_tracks.png`.  All
tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_400`.

Hex deliverable: the three atlases `rail_400_tracks_hex.png`,
`rail_400_tracks_hex_slope.png` and
`rail_400_tracks_hex_slope_half.png`, referenced from the sibling
`rail_400_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_400, make_tier

CS, bake_pakset = make_tier(RAIL_400)


if __name__ == "__main__":
    bake_pakset()
