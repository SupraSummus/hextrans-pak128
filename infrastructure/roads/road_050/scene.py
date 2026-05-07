"""3D model of the road_050 50 km/h urban road (one tile, mid-segment).

Cross-section: a cool dark-grey asphalt carriageway flanked by light
dithered cobblestone kerbs — same shape as road_040 with a cooler
palette, matching pak128 cell 1.5 / 1.6 in `road_050.png`.  All
tier-specific values live in
`infrastructure/roads/road_params.ROAD_050`.

Hex deliverable: `road_050_hex.png` + `road_050_hex_slope.png`,
referenced from the sibling `road_050.dat`.
"""
from infrastructure.roads.road_params import ROAD_050, make_tier

CS, bake_pakset = make_tier(ROAD_050)


if __name__ == "__main__":
    bake_pakset()
