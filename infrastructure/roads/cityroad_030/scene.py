"""3D model of the cityroad_030 30 km/h urban dirt road.

Cross-section: a tan sand-coloured carriageway with no kerb;
carriageway dither lets terrain show through.  Same shape as
road_030 with the warmer urban-sand palette of pak128 cell 1.5 / 1.6
in `cityroad_030.png`.  All tier-specific values live in
`infrastructure/roads/road_params.CITYROAD_030`.

Hex deliverable: `cityroad_030_hex.png` + `cityroad_030_hex_slope.png`,
referenced from the sibling `cityroad_030.dat`.
"""
from infrastructure.roads.road_params import CITYROAD_030, make_tier

CS, bake_pakset = make_tier(CITYROAD_030)


if __name__ == "__main__":
    bake_pakset()
