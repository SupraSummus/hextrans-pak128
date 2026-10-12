"""rail_060 timber trestle bridge: `RAIL_060_BRIDGE` through the bridge
family generator (`tools/threed/bridge.py`).

`bake_pakset()` writes the hex atlas `../rail_060_bridge_hex.png`
(layout in `rail_060_bridge.dat`); `main()` additionally writes the
square verification renders that `build.py` diffs against the pak128
cells of `rail_060_bridge.png`.
"""
from pathlib import Path

from tools.threed import bridge as br
from infrastructure.rail_bridges.rail_bridge_params import (
    RAIL_060_BRIDGE, make_tier,
)

HERE = Path(__file__).resolve().parent
PARAMS = RAIL_060_BRIDGE
bake_pakset = make_tier(PARAMS)


def main() -> None:
    br.write_square_outputs(PARAMS, HERE)


if __name__ == "__main__":
    main()
    bake_pakset()
