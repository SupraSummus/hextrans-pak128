"""3D model of the rail_120 120 km/h rail track (one tile, mid-segment).

Cross-section: timber ties on grey gravel under bright cream rails, matching pak128 cells 1.5 / 1.6 in
`rail_120_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_120`.

Hex deliverable: `rail_120_tracks_hex.png` + `rail_120_tracks_hex_slope.png` +
`rail_120_tracks_hex_slope_half.png`, referenced from the sibling
`rail_120_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_120, make_tier

CS, bake_pakset = make_tier(RAIL_120)


if __name__ == "__main__":
    bake_pakset()
