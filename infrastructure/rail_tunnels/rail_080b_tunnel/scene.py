"""3D model of the rail_080b_tunnel portal.  All values live in
`infrastructure/tunnel_params.RAIL_080B_TUNNEL`, measured from the legacy cell in
`src/` by `infrastructure/measure_tunnel.py`.

Hex deliverable: `rail_080b_tunnel.png`, the 6×2 atlas the sibling `rail_080b_tunnel.dat`
points at.
"""
from pathlib import Path

from infrastructure.tunnel_params import RAIL_080B_TUNNEL, make_tunnel

PORTAL, bake_pakset = make_tunnel(
    RAIL_080B_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    bake_pakset()
