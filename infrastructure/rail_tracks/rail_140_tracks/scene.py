"""3D model of the rail_140 140 km/h rail track (one tile, mid-segment).

Cross-section: timber ties on grey gravel, rail_120's bed with lighter ties, matching pak128 cells 1.5 / 1.6 in
`rail_140_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_140`.

Hex deliverable: `rail_140_tracks_hex.png` + `rail_140_tracks_hex_slope.png` +
`rail_140_tracks_hex_slope_half.png`, referenced from the sibling
`rail_140_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_140, make_tier

CS, bake_pakset = make_tier(RAIL_140)


if __name__ == "__main__":
    bake_pakset()
