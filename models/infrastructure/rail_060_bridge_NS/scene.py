"""Whole 3D model of the rail_060 timber rail bridge (mid-segment, NS).

Reference: infrastructure/rail_bridges/rail_060_bridge.png:
  BackImage[NS][0]  = rail_060_bridge.1.0  (sheet row 1, col 0)
  FrontImage[NS][0] = rail_060_bridge.1.1  (sheet row 1, col 1)
The composite (back overlaid by front) is the visible bridge segment;
in-game it sits over a flat ground tile, with vehicles drawn between
back and front. We model the WHOLE bridge as one structure; slicing
into Back/Front sheet tiles is a future renderer concern.

pak128 sheet offset for these images is (0, 32), so we render with
world z=0 at screen y = 96 - 32 = 64.

Bridge runs along world +x. Tile spans x in [-0.5, 0.5]. Bridge ends
meet ground (z=0) at x = +/- 0.5 via the trestle posts (structural
correctness: the deck is supported all the way to the tile edge).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "tools"))

from render import Scene  # noqa: E402

# --- Material colors ---------------------------------------------------------
TIMBER_DARK = (90, 65, 40)
TIMBER_MID = (130, 95, 60)
TIMBER_LIGHT = (170, 135, 90)
RAIL_GREY = (150, 150, 140)
TIE_BROWN = (100, 70, 45)

# --- Bridge dimensions (1 unit = 1 tile width) -------------------------------
BRIDGE_LEN_HALF = 0.5
DECK_WIDTH_HALF = 0.20
DECK_BOTTOM_Z = 0.10
DECK_TOP_Z = 0.13
RAIL_TOP_Z = 0.155
RAILING_TOP_Z = 0.16

POST_HALF_X = 0.025
POST_HALF_Y = 0.025
N_PANELS = 7              # trestle panels along the span -> 8 posts per side
N_TIES = 12               # cross-ties on top of deck
N_RAIL_POSTS = 10         # vertical posts in top railing per side


def build(scene: Scene) -> None:
    # 1. Deck slab (the main horizontal beam).
    scene.add_box(
        (-BRIDGE_LEN_HALF, -DECK_WIDTH_HALF, DECK_BOTTOM_Z),
        (+BRIDGE_LEN_HALF, +DECK_WIDTH_HALF, DECK_TOP_Z),
        TIMBER_MID,
    )

    # 2. Trestle posts: vertical posts on each long side, deck-bottom to z=0.
    #    Anchored at the tile edges so the bridge structurally meets the
    #    ground at x = +/- 0.5.
    for i in range(N_PANELS + 1):
        t = i / N_PANELS
        x = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        for y_side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            scene.add_box(
                (x - POST_HALF_X, y_side - POST_HALF_Y, 0),
                (x + POST_HALF_X, y_side + POST_HALF_Y, DECK_BOTTOM_Z),
                TIMBER_DARK,
            )

    # 3. Top railing posts (smaller).
    for i in range(N_RAIL_POSTS):
        t = (i + 0.5) / N_RAIL_POSTS
        x = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        for y_side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            scene.add_box(
                (x - 0.012, y_side - 0.012, DECK_TOP_Z),
                (x + 0.012, y_side + 0.012, RAILING_TOP_Z),
                TIMBER_LIGHT,
            )

    # 4. Top railing horizontal bar on each long side.
    for y_side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
        scene.add_box(
            (-BRIDGE_LEN_HALF, y_side - 0.008, RAILING_TOP_Z - 0.020),
            (+BRIDGE_LEN_HALF, y_side + 0.008, RAILING_TOP_Z),
            TIMBER_LIGHT,
        )

    # 5. Cross-ties (sleepers) running across the deck top.
    tie_y_half = DECK_WIDTH_HALF * 0.85
    for i in range(N_TIES):
        t = (i + 0.5) / N_TIES
        x = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        scene.add_box(
            (x - 0.025, -tie_y_half, DECK_TOP_Z),
            (x + 0.025, +tie_y_half, DECK_TOP_Z + 0.012),
            TIE_BROWN,
        )

    # 6. Two parallel rails on top of ties.
    rail_y = DECK_WIDTH_HALF * 0.45
    for y in (-rail_y, +rail_y):
        scene.add_box(
            (-BRIDGE_LEN_HALF, y - 0.008, DECK_TOP_Z + 0.012),
            (+BRIDGE_LEN_HALF, y + 0.008, RAIL_TOP_Z),
            RAIL_GREY,
        )


def main() -> None:
    # pak128 bridge sheet offset (0, 32): z=0 lands at screen y = 96 - 32 = 64.
    scene = Scene(screen_center_y=64)
    build(scene)
    scene.render(str(HERE / "out.png"))


if __name__ == "__main__":
    main()
