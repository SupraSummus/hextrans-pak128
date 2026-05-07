"""3D model of the road_070 70 km/h intercity road (one tile, mid-segment).

Cross-section: a grey asphalt carriageway running up to (but not
quite filling) the entry-edge width — the upstream cell shows grass
on either side of the asphalt.  No kerb.  All tier-specific values
live in `infrastructure/roads/road_params.ROAD_070`.

Hex deliverable: `road_070_hex.png` + `road_070_hex_slope.png`,
referenced from the sibling `road_070.dat`.
"""
from infrastructure.roads.road_params import ROAD_070, make_tier

CS, bake_pakset = make_tier(ROAD_070)


if __name__ == "__main__":
    bake_pakset()
