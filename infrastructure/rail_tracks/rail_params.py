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

Perpendicular distances are in world units, 1 unit = 1 entry-edge
length = 1 square-tile side = 1 hex-edge length
(`tools/threed/way.py::HEX_TILE_RADIUS`), so 0.5 fills the entry edge
in either projection.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    # Family constants.  The gauge is calibrated against pak128 cells
    # 1.5 / 1.6 of `rail_060_tracks.png` by `rail_060_tracks/
    # measure_gauge.py`, which fits a line to the rail-head pixels of
    # each rail and inverts the dimetric projection's perpendicular
    # px-per-world factor; both cells land on 0.04744.  Keep
    # `measure_gauge.py` working (and re-run it after a pak128
    # refresh) rather than tweaking this number by eye.
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
# shoulders.
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
