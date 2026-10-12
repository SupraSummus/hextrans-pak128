"""3D model of the rail_400_tunnel portal.  All values live in
`infrastructure/tunnel_params.RAIL_400_TUNNEL`, measured from the legacy cell in
`src/` by `infrastructure/measure_tunnel.py`.

Hex deliverable: `rail_400_tunnel.png`, the 6×2 atlas the sibling `rail_400_tunnel.dat`
points at.
"""
from pathlib import Path

from infrastructure.tunnel_params import RAIL_400_TUNNEL, make_tunnel

PORTAL, bake_pakset = make_tunnel(
    RAIL_400_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    bake_pakset()
