"""3D model of the rail_080 track (80 km/h): one tile, mid-segment.

Cross-section: timber ties on a dense brown gravel bed, matching pak128
cells 1.5 / 1.6 in `rail_080_tracks.png`.  All tier-specific values live
in `infrastructure/rail_tracks/rail_params.RAIL_080`.

Hex deliverable: the three atlases `rail_080_tracks_hex.png`,
`rail_080_tracks_hex_slope.png` and
`rail_080_tracks_hex_slope_half.png`, referenced from the sibling
`rail_080_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_080, make_tier

CS, bake_pakset = make_tier(RAIL_080)


if __name__ == "__main__":
    bake_pakset()
