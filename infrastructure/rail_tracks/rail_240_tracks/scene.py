"""3D model of the rail_240 track (240 km/h): one tile, mid-segment.

Cross-section: rail_200's bed and rails, ties paler than the bed,
matching pak128 cells 1.5 / 1.6 in `rail_240_tracks.png`.  All
tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_240`.

Hex deliverable: the three atlases `rail_240_tracks_hex.png`,
`rail_240_tracks_hex_slope.png` and
`rail_240_tracks_hex_slope_half.png`, referenced from the sibling
`rail_240_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_240, make_tier

CS, bake_pakset = make_tier(RAIL_240)


if __name__ == "__main__":
    bake_pakset()
