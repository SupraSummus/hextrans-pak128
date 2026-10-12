"""3D model of the rail_280 280 km/h rail track (one tile, mid-segment).

Cross-section: a wide pale gravel bed out to the tile edge under white rails, matching pak128 cells 1.5 / 1.6 in
`rail_280_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_280`.

Hex deliverable: `rail_280_tracks_hex.png` + `rail_280_tracks_hex_slope.png` +
`rail_280_tracks_hex_slope_half.png`, referenced from the sibling
`rail_280_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_280, make_tier

CS, bake_pakset = make_tier(RAIL_280)


if __name__ == "__main__":
    bake_pakset()
