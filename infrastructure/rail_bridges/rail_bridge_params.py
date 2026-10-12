"""Rail bridge tiers as `BridgeParams` instances.

Each tier's `scene.py` reduces to `make_tier(<TIER>)`; the parts and
the bake live in `tools/threed/bridge.py`.  The deck track of each
tier comes from the `RailParams` of the matching rail track tier, so
the bridge's track lines up with the standalone track that joins it.
"""
from __future__ import annotations

from pathlib import Path

from tools.threed import bridge as br
from infrastructure.rail_tracks.rail_params import RAIL_060

RAIL_BRIDGES_DIR = Path(__file__).resolve().parent


# rail_060 — timber trestle: open-tie deck on timber posts, post-and-
# rail fence, a stone pillar.  First-pass values set against pak128
# cells by eye before `measure_bridge` existed (TODO.md, "rail_060_bridge
# remaining sheet calibration").
_TIMBER_DARK = (90, 65, 40)
_TIMBER_MID = (130, 95, 60)
_TIMBER_LIGHT = (170, 135, 90)
RAIL_060_BRIDGE = br.BridgeParams(
    name="rail_060_bridge",
    # Wide enough to host the track's cross-ties.
    deck=br.Deck(half_w=max(0.20, RAIL_060.tie_half_w + 0.04),
                 bottom_z=0.10, color=_TIMBER_MID),
    support=br.Trestle(n_panels=8, post_half=0.018, color=_TIMBER_DARK),
    sides=(br.Railing(n_posts=10, top_z=0.24, color=_TIMBER_LIGHT),),
    track=br.OpenTieTrack(RAIL_060),
    pillar=br.BoxPillar(half_side=0.085, along_aspect=0.55, bottom_z=-0.55,
                        color=(140, 130, 115)),
)


def make_tier(params: br.BridgeParams):
    """`bake_pakset()` for one tier: writes `<name>_hex.png` next to
    the tier's `.dat`.  A tier's `scene.py` is::

        from infrastructure.rail_bridges.rail_bridge_params import (
            RAIL_080_BRIDGE, make_tier)
        bake_pakset = make_tier(RAIL_080_BRIDGE)
        if __name__ == "__main__":
            bake_pakset()
    """
    def bake_pakset() -> None:
        br.bake_pakset(params, RAIL_BRIDGES_DIR)

    return bake_pakset
