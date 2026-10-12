"""3D model of the rail_160 160 km/h rail track (one tile, mid-segment).

Cross-section: pale grey ties on grey gravel under pale rails, matching pak128 cells 1.5 / 1.6 in
`rail_160_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_160`.

Hex deliverable: `rail_160_tracks_hex.png` + `rail_160_tracks_hex_slope.png` +
`rail_160_tracks_hex_slope_half.png`, referenced from the sibling
`rail_160_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_160, make_tier

CS, bake_pakset = make_tier(RAIL_160)


if __name__ == "__main__":
    bake_pakset()
