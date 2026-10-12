"""3D model of the rail_200 200 km/h rail track (one tile, mid-segment).

Cross-section: dark-grey ties on light-grey gravel under steel-grey rails, matching pak128 cells 1.5 / 1.6 in
`rail_200_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_200`.

Hex deliverable: `rail_200_tracks_hex.png` + `rail_200_tracks_hex_slope.png` +
`rail_200_tracks_hex_slope_half.png`, referenced from the sibling
`rail_200_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_200, make_tier

CS, bake_pakset = make_tier(RAIL_200)


if __name__ == "__main__":
    bake_pakset()
