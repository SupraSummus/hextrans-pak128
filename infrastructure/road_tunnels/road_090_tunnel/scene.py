"""3D model of the road_090_tunnel portal.  All values live in
`infrastructure/tunnel_params.ROAD_090_TUNNEL`, measured from the legacy cell in
`src/` by `infrastructure/measure_tunnel.py`.

Hex deliverable: `road_090_tunnel.png`, the 6×2 atlas the sibling `road_090_tunnel.dat`
points at.
"""
from pathlib import Path

from infrastructure.tunnel_params import ROAD_090_TUNNEL, make_tunnel

PORTAL, bake_pakset = make_tunnel(
    ROAD_090_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    bake_pakset()
