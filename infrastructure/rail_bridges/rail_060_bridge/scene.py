"""3D model of the rail_060 timber rail bridge.

Reference: `infrastructure/rail_bridges/rail_060_bridge.png` + `.dat`.
The .dat enumerates 28 summer entries (× 2 seasons) — mid-segments for
the two square-dimetric axes, ramps and starts at each compass
direction, and two pillar variants — and the scene is built from
reusable 3D parts that compose for each.

Mid-segment layers:

    BackImage[NS|EW][0]   = the full silhouette: deck, ties, rails,
                            trestle, far-side railing.  Drawn behind
                            the way (vehicle is on top of it).
    FrontImage[NS|EW][0]  = just the viewer-side railing (posts +
                            top + bottom bar).  Drawn in front of the
                            vehicle.

The whole bridge is one 3D structure tagged per-quad with the layer
it belongs to (`"back"` vs `"front"`).  The renderer emits one PNG
per layer; `build.py` diffs each against the matching pak128 cell
(multi-view supervision).

Coordinate system (matches simutrans's square dimetric, see
`display/viewport.cc::get_screen_coord` and `koord::{north,south,
east,west}`): world +y = north (upper-right onscreen), -y = south
(lower-left), +x = east (lower-right), -x = west (upper-left).

Per-axis orientation:
- NS bridge: length spans world y in [-0.5, +0.5], sides face east
  (+x, FRONT — closer to viewer) and west (-x, BACK).
- EW bridge: length spans world x in [-0.5, +0.5], sides face south
  (-y, FRONT) and north (+y, BACK).

Trestle posts anchor the deck at the tile edge to z=0 (structural
correctness: deck supported all the way to the tile edge; a slow
bridge upgraded to a fast one shouldn't tilt, all rail_*_bridge
decks share a deck-top z).

pak128 sheet offset for the mid-segment images is `(0, 32)`, so we
render with world z=0 anchored to a screen y derived empirically
from the references (see `screen_center_y=68`).  The .dat's `0,32`
is a draw-time compositing shift, not a shift baked into the cell;
the empirical anchor is what matters for the cell pixels.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]  # infrastructure/rail_bridges/rail_060_bridge -> repo
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))
# Track-family parameters live next to rail_060_tracks; the bridge
# pulls them in so its deck-top track lines up with the joining
# standalone track.
sys.path.insert(0, str(REPO_ROOT / "infrastructure" / "rail_tracks"
                       / "rail_060_tracks"))

from bespoke import bake_atlas  # noqa: E402
from render import Scene  # noqa: E402
from track_params import (  # noqa: E402
    BALLAST_TOP_Z, N_TIES, RAIL_GAUGE_HALF, RAIL_GREY, RAIL_HALF_W,
    RAIL_TOP_Z, TIE_BROWN, TIE_HALF_W, TIE_TOP_Z,
)

# Track-relative thicknesses derived from the cross-section stack
# (rail head sits on top of ties, ties on top of ballast).
RAIL_THICKNESS = RAIL_TOP_Z - TIE_TOP_Z
TIE_THICKNESS = TIE_TOP_Z - BALLAST_TOP_Z

# --- Bridge-specific material colors -----------------------------------------
TIMBER_DARK = (90, 65, 40)
TIMBER_MID = (130, 95, 60)
TIMBER_LIGHT = (170, 135, 90)
STONE_GREY = (140, 130, 115)

# --- Bridge dimensions (1 unit = 1 tile width) -------------------------------
BRIDGE_LEN_HALF = 0.5
# Deck must be wide enough to host the rail_060 cross-ties (TIE_HALF_W).
DECK_WIDTH_HALF = max(0.20, TIE_HALF_W + 0.04)
DECK_BOTTOM_Z = 0.10
DECK_TOP_Z = 0.13
RAILING_TOP_Z = 0.24
TOP_BAR_THICKNESS = 0.030

# Slimmer trestle posts than the original first pass; reference shows
# delicate timber framing rather than chunky pillars.
POST_HALF_X = 0.018
POST_HALF_Y = 0.018
N_PANELS = 8              # trestle panels along the span -> 9 posts per side
N_RAIL_POSTS = 10         # vertical posts in top railing per side

# Pillar (separate sheet entry: backPillar[S][0] / backPillar[W][0]) —
# a single vertical stone column rendered against an empty tile, drawn
# behind the bridge segment by the engine when it composites a multi-
# tile bridge over a deep gap.  The reference cell's pillar extends
# from just under the deck down to deep below tile-ground (the engine
# clips it against the gap floor at composite time, so the cell ships
# the maximum-depth shape).
# Pillar is wider perpendicular to the bridge axis than along it
# (ASPECT < 1) so its broad face points at the viewer.  Both extents
# are placeholders — TODO.md tracks the calibration debt.
PILLAR_HALF = 0.085
PILLAR_ALONG_ASPECT = 0.55
PILLAR_TOP_Z = DECK_BOTTOM_Z
PILLAR_BOTTOM_Z = -0.55


def _add_axis_box(scene: Scene, axis: str,
                  along_lo: float, along_hi: float,
                  side_lo: float, side_hi: float,
                  z_lo: float, z_hi: float,
                  color, layer: str = "back",
                  dither_keep: float = 1.0) -> None:
    """Add a box whose extent is given in (along, side, z) bridge-local
    coordinates, mapped into world (x, y, z) per `axis` ("NS" or "EW").

    "along" runs along the bridge length, "side" perpendicular.  For
    NS the bridge axis is world y, perpendicular is world x; for EW
    it's the other way.  This lets the same scene-build code emit
    both orientations without duplicating geometry tables.
    """
    if axis == "NS":
        x0, x1 = side_lo, side_hi
        y0, y1 = along_lo, along_hi
    else:  # "EW"
        x0, x1 = along_lo, along_hi
        y0, y1 = side_lo, side_hi
    scene.add_box((x0, y0, z_lo), (x1, y1, z_hi), color,
                  layer=layer, dither_keep=dither_keep)


def _front_layer_for_side(axis: str, side_centre: float) -> str:
    """Return "front" if the given side is the viewer-facing one for
    the bridge axis, else "back".

    NS bridge: front side is +x (east, lower-right onscreen).
    EW bridge: front side is -y (south, lower-left onscreen).
    """
    if axis == "NS":
        return "front" if side_centre > 0 else "back"
    else:  # "EW"
        return "front" if side_centre < 0 else "back"


def build_segment(scene: Scene, axis: str = "NS") -> None:
    """Build a mid-segment bridge in `axis` orientation ("NS" or "EW").

    Emits all parts of the bridge (deck, trestle, railings, ties,
    rails) tagged with `back`/`front` layers so the renderer can
    slice off `BackImage[axis]` / `FrontImage[axis]` from one scene.
    """
    # 1. Deck slab.
    _add_axis_box(scene, axis,
                  -BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
                  -DECK_WIDTH_HALF, +DECK_WIDTH_HALF,
                  DECK_BOTTOM_Z, DECK_TOP_Z, TIMBER_MID)

    # 2. Trestle posts on both long sides, anchored to tile edges so the
    #    deck is supported all the way to the tile boundary. Both sides
    #    are "back" — the front-side trestle is part of the silhouette,
    #    not the FrontImage railing.
    for i in range(N_PANELS + 1):
        t = i / N_PANELS
        along = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            _add_axis_box(scene, axis,
                          along - POST_HALF_Y, along + POST_HALF_Y,
                          side - POST_HALF_X, side + POST_HALF_X,
                          0.0, DECK_BOTTOM_Z, TIMBER_DARK)

    # X-bracing between trestle posts is genuinely diagonal and the
    # axis-aligned box rasterizer doesn't model it well. Deferred.

    # 3. Top railing posts.  Side-dependent layer assignment puts the
    #    viewer-facing railing in `front`, the far-side railing in `back`.
    for i in range(N_RAIL_POSTS):
        t = (i + 0.5) / N_RAIL_POSTS
        along = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
            layer = _front_layer_for_side(axis, side)
            _add_axis_box(scene, axis,
                          along - 0.016, along + 0.016,
                          side - 0.016, side + 0.016,
                          DECK_TOP_Z, RAILING_TOP_Z, TIMBER_LIGHT,
                          layer=layer)

    # 4. Top + bottom railing horizontal bars on each side. Same
    #    side/layer mapping as the posts.
    BOTTOM_BAR_Z_LO = DECK_TOP_Z - 0.010
    BOTTOM_BAR_Z_HI = DECK_TOP_Z + 0.020
    for side in (-DECK_WIDTH_HALF, +DECK_WIDTH_HALF):
        layer = _front_layer_for_side(axis, side)
        # Top bar.
        _add_axis_box(scene, axis,
                      -BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
                      side - 0.012, side + 0.012,
                      RAILING_TOP_Z - TOP_BAR_THICKNESS, RAILING_TOP_Z,
                      TIMBER_LIGHT, layer=layer)
        # Bottom bar (kick-rail along the deck edge).
        _add_axis_box(scene, axis,
                      -BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
                      side - 0.012, side + 0.012,
                      BOTTOM_BAR_Z_LO, BOTTOM_BAR_Z_HI,
                      TIMBER_LIGHT, layer=layer)

    # 5. Cross-ties on deck top — back layer (under the vehicle).
    #    Cross-section reused from rail_060_tracks so the bridge's
    #    deck-top track lines up with the standalone track that joins
    #    it at either end.
    tie_top_z = DECK_TOP_Z + TIE_THICKNESS
    for i in range(N_TIES):
        t = (i + 0.5) / N_TIES
        along = -BRIDGE_LEN_HALF + t * (2 * BRIDGE_LEN_HALF)
        _add_axis_box(scene, axis,
                      along - 0.025, along + 0.025,
                      -TIE_HALF_W, +TIE_HALF_W,
                      DECK_TOP_Z, tie_top_z, TIE_BROWN)

    # 6. Two parallel rails on top of ties — back layer.
    rail_top_z = tie_top_z + RAIL_THICKNESS
    for x in (-RAIL_GAUGE_HALF, +RAIL_GAUGE_HALF):
        _add_axis_box(scene, axis,
                      -BRIDGE_LEN_HALF, +BRIDGE_LEN_HALF,
                      x - RAIL_HALF_W, x + RAIL_HALF_W,
                      tie_top_z, rail_top_z, RAIL_GREY)


def build_pillar(scene: Scene, axis: str) -> None:
    """Build a single stone pillar centred on the tile, used by the
    engine when compositing a bridge over a deep gap.

    `axis` selects bridge orientation, per the .dat's `backPillar[S]`
    (NS bridge, viewer-facing south side) / `backPillar[W]` (EW bridge,
    viewer-facing west side) keys.  pak128 ships the pillar
    asymmetric=1 so only the two viewer-visible orientations have
    cells; the engine mirrors them for N / E.

    Drawn behind the bridge segment ("back" layer).  Wider
    perpendicular to the bridge axis so the broad face shows from
    the viewer's side; `_add_axis_box` flips along/side into world
    (x,y) per orientation, so one set of half-extents covers both
    NS and EW.
    """
    along_half = PILLAR_HALF * PILLAR_ALONG_ASPECT
    _add_axis_box(scene, axis,
                  -along_half, +along_half,
                  -PILLAR_HALF, +PILLAR_HALF,
                  PILLAR_BOTTOM_Z, PILLAR_TOP_Z, STONE_GREY)


def render_segment(axis: str, projection: str = "square"
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Render a mid-segment bridge in `axis` orientation; return
    `(back, front)` RGBA arrays (one per sheet layer).
    """
    scene = Scene(screen_center_y=68)
    build_segment(scene, axis=axis)
    back = scene.render(layer_filter="back", projection=projection)
    front = scene.render(layer_filter="front", projection=projection)
    return back, front


def render_pillar(axis: str, projection: str = "square") -> np.ndarray:
    scene = Scene(screen_center_y=68)
    build_pillar(scene, axis=axis)
    return scene.render(layer_filter="back", projection=projection)


# --- Square verification renders -------------------------------------------
# Each entry: (out filename relative to HERE, callable returning RGBA).
SQUARE_OUTPUTS = [
    ("out_back_ns.png",     lambda: render_segment("NS")[0]),
    ("out_front_ns.png",    lambda: render_segment("NS")[1]),
    ("out_back_ew.png",     lambda: render_segment("EW")[0]),
    ("out_front_ew.png",    lambda: render_segment("EW")[1]),
    ("out_pillar_s.png",    lambda: render_pillar("NS")),
    ("out_pillar_w.png",    lambda: render_pillar("EW")),
]


def main() -> None:
    for name, fn in SQUARE_OUTPUTS:
        Image.fromarray(fn(), mode="RGBA").save(HERE / name)


# --- Hex bake --------------------------------------------------------------
# Atlas col matches `rail_060_bridge_hex.dat`'s entries.  Multi-layer hex
# output via per-quad hardcoded `back`/`front` tags: the NS axis matches
# `front_back_split`'s `n=(1,0)` rule (front=+x), the EW axis matches
# `n=(0,-1)` (front=-y).  Pillars carry through unchanged (single layer).
# See TODO.md "Depth-clip plane spec partially used" for the auto-tagging
# story when NE_SW / NW_SE axes are added.
HEX_ENTRIES: list[tuple[str, callable]] = [
    ("BackImage[NS][0]",    lambda: render_segment("NS", projection="hex")[0]),
    ("FrontImage[NS][0]",   lambda: render_segment("NS", projection="hex")[1]),
    ("BackImage[EW][0]",    lambda: render_segment("EW", projection="hex")[0]),
    ("FrontImage[EW][0]",   lambda: render_segment("EW", projection="hex")[1]),
    ("backPillar[S][0]",    lambda: render_pillar("NS", projection="hex")),
    ("backPillar[W][0]",    lambda: render_pillar("EW", projection="hex")),
]


def bake_pakset() -> None:
    bake_atlas(
        out_png=HERE.parent / "rail_060_bridge_hex.png",
        entries=HEX_ENTRIES,
        repo_root=REPO_ROOT,
    )


if __name__ == "__main__":
    main()
    bake_pakset()
