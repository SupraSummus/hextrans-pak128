"""3D model of the rail_060 timber rail track (one tile, mid-segment).

Cross-section (per `RailCrossSection`): banded ballast bed (3 dither
densities), evenly-spaced cross-ties, twin rails — emitted into the
chord+caps frame supplied by `tools/threed/way_topology.py::make_slab_emitter`.
The asset-agnostic topology (stub / chord / V-bend / junction /
axis-slope) lives in `way_topology` and dispatches into
`paint_straight`.

Hex deliverable: three atlases written by
`tools.threed.way_bake.bake_way_atlases` next to the sibling
`rail_060_tracks.dat` — see that module for shape details.  Square
verification: `build.py` lays straights via `way_verify` and diffs
against pak128 cells 1.5 / 1.6 (the upstream dimetric NS / EW
straight art).

Coordinate system matches `render.py` and `rail_060_bridge/scene.py`:
world +x = east (lower-right onscreen in square dimetric, screen-right
in hex), world +y = north (upper-right in square, screen-up in hex),
world +z = up.  Track is "back" layer — engine draws track before
vehicles, no front/back split.

Tracks ship no per-image dat offset (unlike `rail_060_bridge`'s `,0,32`),
so we render with world z=0 at the default ground anchor sy=96 (=
IMG_SIZE/2 + 32, the flat-tile bbox midpoint).
"""
from pathlib import Path

from tools.threed import way_topology as wt
from tools.threed.way import STRAIGHT_CHORD
from tools.threed.way_bake import bake_way_atlases

# Track-family parameters (cross-section, colours) live in a sibling
# module so other rail assets (rail_060_bridge, future rail_060_*)
# can pull them in without loading this whole scene file.
from .track_params import (
    BALLAST_TOP_Z, N_TIES, RAIL_GAUGE_HALF, RAIL_GREY, RAIL_HALF_W,
    RAIL_TOP_Z, TIE_BROWN, TIE_HALF_W, TIE_TOP_Z,
)


HERE = Path(__file__).resolve().parent

# Ballast is laid as concentric perpendicular bands so the dither-keep
# tapers from dense near the rails to sparse at the bed's outer edges.
# Distances are |x| from the track centerline.  The reference cell 1.5
# shows this taper as a clear gradient: nearly opaque between the rails,
# fading into pure speckle at the gravel shoulders.
BALLAST_MID = (130, 110, 85)
BALLAST_BANDS = [
    # (inner_half, outer_half, dither_keep)
    (0.000, 0.105, 0.85),  # between & under the rails
    (0.105, 0.155, 0.55),  # inside the cross-tie footprint
    (0.155, 0.220, 0.22),  # gravel shoulders fading into terrain
]


class RailCrossSection(wt.CrossSection):
    """Ballast bed + cross-ties + twin rails on top.  Tie count is
    proportional to the segment's chord length so density stays
    uniform — N_TIES across a through-tile chord (`STRAIGHT_CHORD`),
    N_TIES/2 across a stub, ~3 across a V-bend leg, all the same
    ties-per-world-unit."""

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        add_slab, chord_len = wt.make_slab_emitter(model, path)

        # 1. Ballast bands.
        for inner, outer, keep in BALLAST_BANDS:
            for sign in (-1, +1):
                a, b = sign * inner, sign * outer
                add_slab(0.0, 1.0, min(a, b), max(a, b),
                         0.0, BALLAST_TOP_Z, BALLAST_MID, dither_keep=keep)

        # 2. Cross-ties.  Tie thickness in chord direction is fixed in
        #    world units; convert to the s-parameter.  Ties span the
        #    chord from a margin in (so the angled caps don't clip them
        #    off-tile).
        n_ties = round(N_TIES * chord_len / STRAIGHT_CHORD)
        if n_ties > 0:
            tie_half_along_s = 0.025 / chord_len
            margin_s = 1.5 * tie_half_along_s
            for i in range(n_ties):
                s_centre = margin_s + (i + 0.5) / n_ties * (1.0 - 2 * margin_s)
                add_slab(s_centre - tie_half_along_s,
                         s_centre + tie_half_along_s,
                         -TIE_HALF_W, +TIE_HALF_W,
                         BALLAST_TOP_Z, TIE_TOP_Z, TIE_BROWN,
                         dither_keep=0.75)

        # 3. Twin rails on top of the ties.
        for x in (-RAIL_GAUGE_HALF, +RAIL_GAUGE_HALF):
            add_slab(0.0, 1.0, x - RAIL_HALF_W, x + RAIL_HALF_W,
                     TIE_TOP_Z, RAIL_TOP_Z, RAIL_GREY)


CS = RailCrossSection()


def bake_pakset() -> None:
    bake_way_atlases(CS, out_dir=HERE.parent, name="rail_060_tracks")


if __name__ == "__main__":
    bake_pakset()
