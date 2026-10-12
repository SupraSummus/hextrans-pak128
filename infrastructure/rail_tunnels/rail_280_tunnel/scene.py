"""3D model of the rail_280_tunnel portal.  All values live in
`infrastructure/tunnel_params.RAIL_280_TUNNEL`, measured from the legacy cell in
`src/` by `infrastructure/measure_tunnel.py`.

Hex deliverable: `rail_280_tunnel.png`, the 6×2 atlas the sibling `rail_280_tunnel.dat`
points at.
"""
from pathlib import Path

from infrastructure.tunnel_params import RAIL_280_TUNNEL, make_tunnel

PORTAL, bake_pakset = make_tunnel(
    RAIL_280_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    bake_pakset()
