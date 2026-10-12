"""3D model of the rail_100 track (100 km/h): one tile, mid-segment.

Cross-section: the same pak128 art as rail_080: timber ties on a dense
brown gravel bed, matching pak128 cells 1.5 / 1.6 in
`rail_100_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_100`.

Hex deliverable: the three atlases `rail_100_tracks_hex.png`,
`rail_100_tracks_hex_slope.png` and
`rail_100_tracks_hex_slope_half.png`, referenced from the sibling
`rail_100_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_100, make_tier

CS, bake_pakset = make_tier(RAIL_100)


if __name__ == "__main__":
    bake_pakset()
