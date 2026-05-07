"""3D model of the highway_110 110 km/h highway (one tile, mid-segment).

Cross-section: a wide dark-grey asphalt carriageway filling the
entry edge.  No kerb.  Same surface as road_090 with a slightly
darker palette.  All tier-specific values live in
`infrastructure/roads/road_params.HIGHWAY_110`.

Hex deliverable: `highway_110_hex.png` + `highway_110_hex_slope.png`,
referenced from the sibling `highway_110.dat`.
"""
from infrastructure.roads.road_params import HIGHWAY_110, make_tier

CS, bake_pakset = make_tier(HIGHWAY_110)


if __name__ == "__main__":
    bake_pakset()
