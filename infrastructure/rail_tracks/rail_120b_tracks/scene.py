"""3D model of the rail_120b track (120 km/h heavy-duty): one tile, mid-segment.

Cross-section: lighter timber ties on brown gravel under pale rails,
matching pak128 cells 1.5 / 1.6 in `rail_120b_tracks.png`.  All
tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_120B`.

Hex deliverable: the three atlases `rail_120b_tracks_hex.png`,
`rail_120b_tracks_hex_slope.png` and
`rail_120b_tracks_hex_slope_half.png`, referenced from the sibling
`rail_120b_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_120B, make_tier

CS, bake_pakset = make_tier(RAIL_120B)


if __name__ == "__main__":
    bake_pakset()
