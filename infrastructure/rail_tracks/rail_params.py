"""Rail-family parameters and the shared cross-section painter.

Counterpart of `infrastructure/roads/road_params.py`: every rail track
tier reduces to a `RailParams` instance plus a short scene file that
pipes it into the shared `RailCrossSection`.  `RAIL_060` is also the
track-line source for `rail_060_bridge`, so the bridge deck carries the
same ballast / tie / rail stack as the standalone track that joins it.

A tier's cross-section is a ballast bed, cross-ties and twin rails.
The bed is a stack of concentric bands, each with its own colour and
dither density: dense near the rails, fading to a ragged shoulder (the
pak128 convention).

The bed (colour, width, density) and the tie and rail colours differ
from tier to tier and are the required fields; rail gauge, tie length,
tie cadence and the z-stack are the same in every tier and sit in the
dataclass defaults.  The values of rail_080 and up are sampled from
each tier's pak128 cells 1.5 / 1.6 by `measure_tier.py`, never tuned by
eye.

Perpendicular distances are in world units, 1 unit = 1 entry-edge
length = 1 square-tile side = 1 hex-edge length
(`tools/threed/way.py::HEX_TILE_RADIUS`), so 0.5 fills the entry edge
in either projection.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from tools.threed import way_topology as wt
from tools.threed import way_verify
from tools.threed.way import STRAIGHT_CHORD
from tools.threed.way_bake import bake_way_atlases


RAIL_DIR = Path(__file__).resolve().parent

RGB = tuple[int, int, int]

# Cross-tie thickness along the track and dither density of the tie
# slab; the same in every tier, so painter constants, not parameters.
TIE_HALF_ALONG = 0.025
TIE_DITHER_KEEP = 0.75


# --- Per-tier parameter type ------------------------------------------------

class BallastBand(NamedTuple):
    """One concentric band of the ballast bed, `inner`..`outer` world
    units either side of the track centreline, kept at density `keep`
    (1.0 opaque, lower lets the terrain show through)."""
    inner: float
    outer: float
    keep: float
    color: RGB


@dataclass(frozen=True)
class RailParams:
    """Cross-section + materials for one rail track tier."""
    # Asset name: `<name>.png` / `<name>.dat` in `rail_tracks/`, model
    # dir `<name>/`.
    name: str
    ballast_bands: tuple[BallastBand, ...]
    tie_color: RGB
    rail_color: RGB
    # Family constants, the same in every tier.  `measure_tier.py`
    # finds the half-gauge at 0.0474 in every tier's pak128 cells; keep
    # it working, and re-run it after a pak128 refresh, rather than
    # tweaking the number by eye.  The tie length and cadence are
    # rail_060's hex choices, not the pak128 values `measure_tier.py`
    # reads (TODO.md, "RAIL_060 predates measure_tier").
    tie_half_w: float = 0.16
    rail_half_w: float = 0.008       # rail head thickness (perpendicular)
    rail_gauge_half: float = 0.0474  # half the rail-to-rail spacing
    # Stack heights above ground (z=0).  Bridge scenes lift these onto
    # their deck top via `DECK_TOP_Z + (tie_top_z - ballast_top_z)` etc.
    ballast_top_z: float = 0.020
    tie_top_z: float = 0.030
    rail_top_z: float = 0.045
    # Cross-ties across a through-tile chord (`STRAIGHT_CHORD`).
    n_ties: int = 12


# --- Per-tier instances -----------------------------------------------------

# rail_060 — timber track on a thin dithered gravel bed.  The bed is
# laid as concentric bands whose dither-keep tapers from dense near the
# rails to sparse at the outer edge; distances are |x| from the
# centreline.  Reference cell 1.5 shows this taper as a gradient:
# nearly opaque between the rails, fading into pure speckle at the
# shoulders.  These values predate `measure_tier.py` and are hand-set;
# they stay as they are so the committed art is unchanged (TODO.md,
# "RAIL_060 predates measure_tier").
_GRAVEL_060 = (130, 110, 85)
RAIL_060 = RailParams(
    name="rail_060_tracks",
    ballast_bands=(
        BallastBand(0.000, 0.105, 0.85, _GRAVEL_060),  # between & under the rails
        BallastBand(0.105, 0.155, 0.55, _GRAVEL_060),  # inside the cross-tie footprint
        BallastBand(0.155, 0.220, 0.22, _GRAVEL_060),  # shoulders fading into terrain
    ),
    tie_color=(100, 70, 45),
    rail_color=(140, 140, 130),
)


# Tiers rail_080 .. rail_400: every value is `measure_tier.py` output
# for the tier's pak128 cells (`python3 -m
# infrastructure.rail_tracks.measure_tier rail_080_tracks`), colours as
# model colours (observed / top-face shade).
#
# Ballast silhouette.  The pak128 bed is one ragged shape shared by
# tiers 080..240: opaque out to 0.22 off the axis, then a taper to
# nothing by 0.30.  Three bands of (inner, outer, keep) follow.
_GRAVEL_PROFILE = ((0.00, 0.22, 0.99), (0.22, 0.26, 0.65), (0.26, 0.30, 0.14))


def _bed(profile, *colors: RGB) -> tuple[BallastBand, ...]:
    """Bands of `profile` coloured `colors` (core, shoulder, fringe)."""
    return tuple(BallastBand(lo, hi, keep, color)
                 for (lo, hi, keep), color in zip(profile, colors))


# rail_080 / rail_100 — timber ties on brown gravel.  The two tiers'
# pak128 cells measure identically.
RAIL_080 = RailParams(
    name="rail_080_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (130, 113, 92), (130, 117, 93), (178, 155, 122)),
    tie_color=(68, 51, 34),
    rail_color=(193, 177, 147),
)
RAIL_100 = replace(RAIL_080, name="rail_100_tracks")

# rail_080b — lighter rails, redder gravel.
RAIL_080B = RailParams(
    name="rail_080b_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (120, 100, 74), (117, 98, 74), (166, 129, 84)),
    tie_color=(90, 63, 38),
    rail_color=(232, 220, 198),
)

# rail_120 — grey gravel, bright cream rails.
RAIL_120 = RailParams(
    name="rail_120_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (143, 137, 128), (145, 140, 130), (167, 163, 151)),
    tie_color=(68, 51, 36),
    rail_color=(248, 226, 188),
)

# rail_120b — brown gravel like rail_080's under pale rails, lighter ties.
RAIL_120B = RailParams(
    name="rail_120b_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (132, 115, 92), (130, 117, 93), (178, 155, 122)),
    tie_color=(93, 66, 39),
    rail_color=(235, 222, 200),
)

# rail_140 — bed and rails like rail_120's, lighter ties.
RAIL_140 = RailParams(
    name="rail_140_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (143, 136, 128), (145, 140, 130), (167, 163, 151)),
    tie_color=(92, 66, 40),
    rail_color=(248, 226, 188),
)

# rail_160 — grey gravel, pale rails, pale grey ties.
RAIL_160 = RailParams(
    name="rail_160_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (146, 139, 131), (145, 140, 130), (167, 163, 151)),
    tie_color=(158, 156, 149),
    rail_color=(235, 222, 200),
)

# rail_180 — bed and rails like rail_160's, paler ties.
RAIL_180 = RailParams(
    name="rail_180_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (145, 138, 129), (145, 140, 130), (167, 163, 151)),
    tie_color=(188, 187, 177),
    rail_color=(235, 222, 200),
)

# rail_200 — light-grey gravel, steel-grey rails, dark-grey ties.
RAIL_200 = RailParams(
    name="rail_200_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (180, 176, 168), (180, 178, 168), (197, 195, 186)),
    tie_color=(126, 125, 118),
    rail_color=(215, 217, 221),
)

# rail_240 — bed and rails like rail_200's, ties paler than the bed.
RAIL_240 = RailParams(
    name="rail_240_tracks",
    ballast_bands=_bed(_GRAVEL_PROFILE,
                       (180, 177, 168), (180, 178, 168), (197, 195, 186)),
    tie_color=(181, 181, 174),
    rail_color=(215, 217, 221),
)

# Tiers 280 and up: a wider bed, the taper starting near the tile edge
# (0.44) instead of at 0.22.
_WIDE_PROFILE = ((0.00, 0.44, 1.00), (0.44, 0.47, 0.68), (0.47, 0.50, 0.32))

# rail_280 — pale gravel out to the tile edge, white rails, dark-grey ties.
RAIL_280 = RailParams(
    name="rail_280_tracks",
    ballast_bands=_bed(_WIDE_PROFILE,
                       (203, 198, 192), (202, 199, 192), (212, 211, 206)),
    tie_color=(127, 126, 120),
    rail_color=(255, 255, 255),
)

# rail_320 — rail_280 on a concrete slab: flat cool grey out to 0.18 off
# the axis (the bed's colour spread is 3..5 there against 9+ in the
# gravel beside it).
RAIL_320 = RailParams(
    name="rail_320_tracks",
    ballast_bands=(
        BallastBand(0.00, 0.18, 1.00, (209, 210, 210)),
        BallastBand(0.18, 0.44, 1.00, (201, 196, 190)),
        BallastBand(0.44, 0.47, 0.68, (201, 193, 188)),
        BallastBand(0.47, 0.50, 0.32, (208, 205, 199)),
    ),
    tie_color=(135, 135, 135),
    rail_color=(255, 255, 255),
)

# rail_400 — slab track: concrete across the whole tile.
RAIL_400 = RailParams(
    name="rail_400_tracks",
    ballast_bands=(
        BallastBand(0.00, 0.50, 1.00, (209, 210, 210)),
    ),
    tie_color=(135, 135, 135),
    rail_color=(255, 255, 255),
)


# --- Cross-section painter --------------------------------------------------

class RailCrossSection(wt.CrossSection):
    """Ballast bed + cross-ties + twin rails on top, configured by
    `RailParams`.  Tie count is proportional to the segment's chord
    length so density stays uniform — `n_ties` across a through-tile
    chord (`STRAIGHT_CHORD`), half that across a stub, ~3 across a
    V-bend leg, all the same ties-per-world-unit."""

    def __init__(self, params: RailParams) -> None:
        self.params = params

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        p = self.params
        add_slab, chord_len = wt.make_slab_emitter(model, path)

        # 1. Ballast bands.
        for band in p.ballast_bands:
            for sign in (-1, +1):
                a, b = sign * band.inner, sign * band.outer
                add_slab(0.0, 1.0, min(a, b), max(a, b),
                         0.0, p.ballast_top_z, band.color,
                         dither_keep=band.keep)

        # 2. Cross-ties.  Tie thickness in chord direction is fixed in
        #    world units; convert to the s-parameter.  Ties span the
        #    chord from a margin in (so the angled caps don't clip them
        #    off-tile).
        n_ties = round(p.n_ties * chord_len / STRAIGHT_CHORD)
        if n_ties > 0:
            tie_half_along_s = TIE_HALF_ALONG / chord_len
            margin_s = 1.5 * tie_half_along_s
            for i in range(n_ties):
                s_centre = margin_s + (i + 0.5) / n_ties * (1.0 - 2 * margin_s)
                add_slab(s_centre - tie_half_along_s,
                         s_centre + tie_half_along_s,
                         -p.tie_half_w, +p.tie_half_w,
                         p.ballast_top_z, p.tie_top_z, p.tie_color,
                         dither_keep=TIE_DITHER_KEEP)

        # 3. Twin rails on top of the ties.
        for x in (-p.rail_gauge_half, +p.rail_gauge_half):
            add_slab(0.0, 1.0, x - p.rail_half_w, x + p.rail_half_w,
                     p.tie_top_z, p.rail_top_z, p.rail_color)


# --- Per-tier scene helper --------------------------------------------------

def make_tier(params: RailParams):
    """Wire one rail tier up for hex bake + square verification.

    Each tier's `scene.py` reduces to::

        from infrastructure.rail_tracks.rail_params import RAIL_080, make_tier
        CS, bake_pakset = make_tier(RAIL_080)
        if __name__ == "__main__":
            bake_pakset()

    The returned `CS` is the per-tier `RailCrossSection` instance
    (consumed by `way_verify.verify_square` for the dimetric diff
    against pak128 cells 1.5 / 1.6).  `bake_pakset()` delegates to
    `tools.threed.way_bake.bake_way_atlases`, which writes the three
    standard hex atlases (`_hex.png`, `_hex_slope.png`,
    `_hex_slope_half.png`) next to the tier's `.dat` — see that
    module for the atlas shapes.
    """
    cs = RailCrossSection(params)

    def bake_pakset() -> None:
        bake_way_atlases(cs, out_dir=RAIL_DIR, name=params.name)

    return cs, bake_pakset


def verify_tier(scene_mod) -> None:
    """Square-projection verification + hex bake for one rail tier.

    Cropped refs, candidate renders, debug diffs land in the tier's
    own model dir under `infrastructure/rail_tracks/<name>/`.  Each
    tier's `build.py` reduces to::

        from . import scene
        from infrastructure.rail_tracks.rail_params import verify_tier
        if __name__ == "__main__":
            verify_tier(scene)
    """
    name = scene_mod.CS.params.name
    way_verify.verify_square(
        scene_mod=scene_mod,
        sheet_path=RAIL_DIR / f"{name}.png",
        here=RAIL_DIR / name,
    )
