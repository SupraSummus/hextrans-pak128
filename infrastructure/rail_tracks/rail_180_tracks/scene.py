"""3D model of the rail_180 180 km/h rail track (one tile, mid-segment).

Cross-section: paler grey ties on grey gravel under pale rails, matching pak128 cells 1.5 / 1.6 in
`rail_180_tracks.png`.  All tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_180`.

Hex deliverable: `rail_180_tracks_hex.png` + `rail_180_tracks_hex_slope.png` +
`rail_180_tracks_hex_slope_half.png`, referenced from the sibling
`rail_180_tracks.dat`.
"""
from infrastructure.rail_tracks.rail_params import RAIL_180, make_tier

CS, bake_pakset = make_tier(RAIL_180)


if __name__ == "__main__":
    bake_pakset()
