"""3D model of the rail_060 tunnel portal: two stone buttresses, a
lintel and a dark opening.  All values live in
`infrastructure/tunnel_params.RAIL_060_TUNNEL`.

Hex deliverable: `rail_060_tunnel.png`, the 6×2 atlas the sibling
`rail_060_tunnel.dat` points at.  The legacy upstream art is in `src/`.
"""
from pathlib import Path

from infrastructure.tunnel_params import RAIL_060_TUNNEL, make_tunnel

PORTAL, bake_pakset = make_tunnel(
    RAIL_060_TUNNEL, out_dir=Path(__file__).resolve().parent.parent)


if __name__ == "__main__":
    bake_pakset()
