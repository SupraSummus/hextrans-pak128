"""3D model of the road_030 30 km/h dirt road (one tile, mid-segment).

Cross-section: a narrow brown carriageway, no kerb; carriageway dither
lets terrain show through, matching pak128's scrubby grass-and-dirt
look (cell 1.5 / 1.6 in `road_030.png`).  All tier-specific values
live in `infrastructure/roads/road_params.ROAD_030`; topology comes
from `tools/threed/way_topology.py`.

Hex deliverable: `road_030_hex.png` + `road_030_hex_slope.png`,
referenced from the sibling `road_030.dat`.
"""
from infrastructure.roads.road_params import ROAD_030, make_tier

CS, bake_pakset = make_tier(ROAD_030)


if __name__ == "__main__":
    bake_pakset()
