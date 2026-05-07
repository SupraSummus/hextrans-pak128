"""3D model of the road_040 stone city road (one tile, mid-segment).

Cross-section comes from the shared `RoadCrossSection` parameterised
by `infrastructure/roads/road_params.ROAD_040` — dark olive-brown
carriageway down the middle, lighter dithered cobblestone kerbs on
the shoulders.  Topology (stub / curve / junction / axis-slope) comes
from `tools/threed/way_topology.py`.

Hex deliverable: `road_040_hex.png` (8×8 atlas, 63 ribi cells) plus
`road_040_hex_slope.png` (1×6 axis slopes), referenced from the
sibling `road_040.dat`.  Square verification: `build.py` lays straights
via `way_verify` and diffs against pak128 cells 1.5 / 1.6 (the
upstream dimetric NS / EW straight art).
"""
from infrastructure.roads.road_params import ROAD_040, make_tier

CS, bake_pakset = make_tier(ROAD_040)


if __name__ == "__main__":
    bake_pakset()
