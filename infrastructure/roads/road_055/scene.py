"""3D model of the road_055 55 km/h gravel road (one tile, mid-segment).

Cross-section: a narrow grey-tan gravel carriageway with no kerb;
carriageway dither lets terrain show through.  Same shape as road_030
with a lighter gravel palette, matching pak128 cell 1.5 / 1.6 in
`road_055.png`.  All tier-specific values live in
`infrastructure/roads/road_params.ROAD_055`.

Hex deliverable: `road_055_hex.png` + `road_055_hex_slope.png`,
referenced from the sibling `road_055.dat`.
"""
from infrastructure.roads.road_params import ROAD_055, make_tier

CS, bake_pakset = make_tier(ROAD_055)


if __name__ == "__main__":
    bake_pakset()
