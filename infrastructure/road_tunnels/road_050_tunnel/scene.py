"""3D model of the road_050_tunnel portal.  All values live in
`infrastructure/tunnel_params.ROAD_050_TUNNEL`, measured from the legacy cell in
`src/` by `infrastructure/measure_tunnel.py`.

Hex deliverable: `road_050_tunnel.png`, the 6×2 atlas the sibling `road_050_tunnel.dat`
points at.
"""
from pathlib import Path

from infrastructure.tunnel_params import ROAD_050_TUNNEL, make_tunnel

PORTAL, bake_pakset = make_tunnel(
    ROAD_050_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    bake_pakset()
