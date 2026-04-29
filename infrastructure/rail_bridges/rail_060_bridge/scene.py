"""Whole 3D model of the rail_060 timber rail bridge (mid-segment, NS).

Reference: infrastructure/rail_bridges/rail_060_bridge.png:
  BackImage[NS][0]  = rail_060_bridge.1.0  (sheet row 1, col 0)
  FrontImage[NS][0] = rail_060_bridge.1.1  (sheet row 1, col 1)
In-game the engine draws BackImage with the way (behind vehicles), then
the vehicle, then FrontImage on top — Back is the full bridge silhouette
(deck, ties, rails, trestle, back-side railing); Front is just the
viewer-side railing (posts + top bar) which would otherwise be hidden
behind the vehicle.

We model the whole bridge as one 3D structure but tag each part with
the layer it belongs to (`"back"` vs `"front"`). The renderer emits one
PNG per layer; build.sh diffs each against the matching pak128 sheet
entry (multi-view supervision).

Coordinate system (matches simutrans's square dimetric, see
`display/viewport.cc::get_screen_coord` and `koord::{north,south,east,
west}`): world +y = north (upper-right), -y = south (lower-left),
+x = east (lower-right), -x = west (upper-left). NS bridge runs along
the world y-axis, so its length spans y in [-0.5, +0.5] and its sides
face east (+x, the FRONT side closer to the viewer) and west (-x, the
BACK side). Trestle posts anchor the deck at y = +/- 0.5 to z = 0
(structural correctness: deck supported all the way to the tile edge).

pak128 sheet offset for these images is (0, 32), so we render with
world z=0 at screen y = 96 - 32 = 64.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]  # infrastructure/rail_bridges/rail_060_bridge -> repo
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

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
# Railing reaches ~10 px on screen; reference front strip is ~12 px tall.
RAILING_TOP_Z = 0.24

# Slimmer trestle posts than the original first pass; reference shows
# delicate timber framing rather than chunky pillars.
POST_HALF_X = 0.018
POST_HALF_Y = 0.018
BRACE_HALF = 0.010        # diagonal X-brace cross-section
N_PANELS = 8              # trestle panels along the span -> 9 posts per side
N_TIES = 12               # cross-ties on top of deck
N_RAIL_POSTS = 10         # vertical posts in top railing per side


def build(scene: Scene) -> None:
    # 1. Deck slab — back layer (sits behind / under vehicles).
    scene.add_box(
        (-DECK_WIDTH_HALF, -BRIDGE_LEN_HALF, DECK_BOTTOM_Z),
        (+DECK_WIDTH_HALF, +BRIDGE_LEN_HALF, DECK_TOP_Z),
        TIMBER_MID,
        layer="back",
    )

    # 2. Trestle posts on both long sides, anchored to tile edges so the
    #    deck is supported all the way to y = +/- 0.5. Both sides are
    #    "back" — the front-side trestle is visible in BackImage too,
    #    not in FrontImage (FrontImage is JUST the front-side railing).
    for i in range(N_PANELS + 1):
        t = i / N_PANELS
        y = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        for x_side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            scene.add_box(
                (x_side - POST_HALF_X, y - POST_HALF_Y, 0),
                (x_side + POST_HALF_X, y + POST_HALF_Y, DECK_BOTTOM_Z),
                TIMBER_DARK,
                layer="back",
            )

    # X-bracing between trestle posts is genuinely diagonal and the
    # axis-aligned box rasterizer doesn't model it well. Deferred.

    # 3. Top railing posts: east side (+x, viewer side) is front; west is back.
    for i in range(N_RAIL_POSTS):
        t = (i + 0.5) / N_RAIL_POSTS
        y = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        for x_side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            layer = "front" if x_side > 0 else "back"
            scene.add_box(
                (x_side - 0.016, y - 0.016, DECK_TOP_Z),
                (x_side + 0.016, y + 0.016, RAILING_TOP_Z),
                TIMBER_LIGHT,
                layer=layer,
            )

    # 4. Top + bottom railing horizontal bars on each side. The reference
    #    FrontImage shows a railing with both a top bar and a lower bar
    #    at deck level, so the railing reads as a substantial "fence"
    #    rather than just balusters. Same east/west split as posts.
    BOTTOM_BAR_Z_LO = DECK_TOP_Z - 0.010
    BOTTOM_BAR_Z_HI = DECK_TOP_Z + 0.020
    for x_side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
        layer = "front" if x_side > 0 else "back"
        # Top bar.
        scene.add_box(
            (x_side - 0.012, -BRIDGE_LEN_HALF, RAILING_TOP_Z - 0.030),
            (x_side + 0.012, +BRIDGE_LEN_HALF, RAILING_TOP_Z),
            TIMBER_LIGHT,
            layer=layer,
        )
        # Bottom bar (kick-rail, runs along the deck-top edge).
        scene.add_box(
            (x_side - 0.012, -BRIDGE_LEN_HALF, BOTTOM_BAR_Z_LO),
            (x_side + 0.012, +BRIDGE_LEN_HALF, BOTTOM_BAR_Z_HI),
            TIMBER_LIGHT,
            layer=layer,
        )

    # 5. Cross-ties on deck top — back layer (under the vehicle).
    tie_x_half = DECK_WIDTH_HALF * 0.85
    for i in range(N_TIES):
        t = (i + 0.5) / N_TIES
        y = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        scene.add_box(
            (-tie_x_half, y - 0.025, DECK_TOP_Z),
            (+tie_x_half, y + 0.025, DECK_TOP_Z + 0.012),
            TIE_BROWN,
            layer="back",
        )

    # 6. Two parallel rails on top of ties — back layer.
    rail_x = DECK_WIDTH_HALF * 0.45
    for x in (-rail_x, +rail_x):
        scene.add_box(
            (x - 0.008, -BRIDGE_LEN_HALF, DECK_TOP_Z + 0.012),
            (x + 0.008, +BRIDGE_LEN_HALF, RAIL_TOP_Z),
            RAIL_GREY,
            layer="back",
        )


def main() -> None:
    # World z=0 lands at screen y=68 in the cell. The pak128 bridge .dat
    # offset (0, 32) shifts the sprite down 32 px at engine compositing
    # time; within the raw sheet cell the artist drew z=0 around y=68
    # (empirical: cropped ref's south trestle bottom sits at y=90, our
    # geometry says z=0 projects to sy = 68 + 22 = 90 at the south end).
    scene = Scene(screen_center_y=68)
    build(scene)
    scene.render(str(HERE / "out_back.png"), layer_filter="back")
    scene.render(str(HERE / "out_front.png"), layer_filter="front")


if __name__ == "__main__":
    main()
