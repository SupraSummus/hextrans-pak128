"""3D model of the rail_320 320 km/h rail track (one tile, mid-segment).

Cross-section: rail_280 on a concrete slab down the middle of the bed, matching pak128 cells 1.5 / 1.6 in
`rail_320_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_320`.

Hex deliverable: `rail_320_tracks_hex.png` + `rail_320_tracks_hex_slope.png` +
`rail_320_tracks_hex_slope_half.png`, referenced from the sibling
`rail_320_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_320, make_tier

CS, bake_pakset = make_tier(RAIL_320)


if __name__ == "__main__":
    bake_pakset()
