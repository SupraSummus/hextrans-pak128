"""3D model of the road_090 90 km/h intercity road (one tile, mid-segment).

Cross-section: a wide grey asphalt carriageway filling the entry
edge.  No kerb.  Same surface as road_070, wider.  All tier-specific
values live in `infrastructure/roads/road_params.ROAD_090`.

Hex deliverable: `road_090_hex.png` + `road_090_hex_slope.png`,
referenced from the sibling `road_090.dat`.
"""
from infrastructure.roads.road_params import ROAD_090, make_tier

CS, bake_pakset = make_tier(ROAD_090)


if __name__ == "__main__":
    bake_pakset()
