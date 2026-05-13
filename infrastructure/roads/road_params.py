"""Road-family parameters and the shared cross-section painter.

Parallel to `infrastructure/rail_tracks/rail_060_tracks/track_params.py`
for the rail family — every road tier (road_030 ... road_090,
cityroad_030, highway_*) reduces to a `RoadParams` instance plus a
short scene file that pipes it into the shared `RoadCrossSection`.

`RoadParams` captures the cross-section in the abstract: a carriageway
slab down the middle plus an optional pair of kerb slabs on the
shoulders.  Setting `pavement_half_w == carriageway_half_w` (or
`sidewalk_color=None`) drops the kerbs entirely — the dirt / gravel
tiers go that route.  `carriageway_dither_keep < 1.0` lets the
underlying terrain show through the carriageway slab, which is how
the dirt tiers read as a wagon track rather than a paved surface.

Per-tier values were sampled from each tier's pak128 NS / EW straight
cells (1.5 / 1.6) so the hex bake matches the upstream square art in
carriageway colour, kerb colour, and rough cross-section width.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from landscape.grounds.sidewalk.render import PAVEMENT_RGB
from tools.threed import way_topology as wt
from tools.threed import way_verify
from tools.threed.way_bake import bake_way_atlases


ROADS_DIR = Path(__file__).resolve().parent


# --- Per-tier parameter type ------------------------------------------------

@dataclass(frozen=True)
class RoadParams:
    """Cross-section + materials for one road tier.  See module
    docstring for how the kerb / carriageway / dither knobs interact."""
    name: str
    carriageway_color: tuple[int, int, int]
    # Half-widths on either side of the chord, in world units (1 unit
    # = entry-edge length).  `pavement_half_w = 0.5` fills the entry
    # edge exactly; the kerb spans `[carriageway_half_w,
    # pavement_half_w]` per side.
    pavement_half_w: float = 0.5
    carriageway_half_w: float = 0.38
    sidewalk_color: tuple[int, int, int] | None = PAVEMENT_RGB
    # Dither knobs.  Carriageway < 1.0 lets terrain show through the
    # surface (dirt / gravel tiers); sidewalk dither is the cobble
    # speckle borrowed from pak128's stone-city kerb art.
    carriageway_dither_keep: float = 1.0
    sidewalk_dither_keep: float = 0.65
    # Z-stack: carriageway sits a hair above the kerb so it wins the
    # z-buffer where one stub's kerb crosses another stub's
    # carriageway at a junction; otherwise the dark surface would read
    # as a cobblestone criss-cross instead of a continuous
    # intersection.  The 0.006 gap is invisible in oblique views
    # (the visible top-face brightness is the same — sun direction
    # unchanged) but unambiguous to the depth test.
    sidewalk_top_z: float = 0.008
    carriageway_top_z: float = 0.014
    # `has_double_slopes=1` opt-in in the tier's .dat.  When True the
    # bake emits a second 1×6 row in `<name>_hex_slope.png` with the
    # 0→2 chord climb; the .dat references those cells via
    # `ImageUp[<axis>_double]`.  Mirrors each tier's pre-port square
    # `ImageUp2[*]` presence — see commit 1c8c877 in the .dats.
    has_double_slopes: bool = False


# --- Per-tier instances -----------------------------------------------------

# road_040 — the worked example, dark olive-brown carriageway flanked
# by lighter cobblestone kerbs.  These constants are the literal
# defaults of `RoadParams` plus the road_040 colour pair.
ROAD_040 = RoadParams(
    name="road_040",
    carriageway_color=(97, 91, 72),
    has_double_slopes=True,
)

# road_050 — 50 km/h urban road that reads like asphalt under stone-
# city kerbs.  Carriageway is a cooler dark grey; kerb dither stays.
ROAD_050 = RoadParams(
    name="road_050",
    carriageway_color=(86, 80, 68),
    has_double_slopes=True,
)

# road_070 / road_090 / highway_110 — asphalt intercity / trunk.  No
# kerbs (the upstream art runs the asphalt straight to the tile edge
# with no cobble band on the shoulders).  road_070 is slightly
# narrower than the entry edge (the upstream cell shows grass on
# either side); road_090 and highway_110 fill it.
ROAD_070 = RoadParams(
    name="road_070",
    carriageway_color=(102, 95, 80),
    pavement_half_w=0.42,
    carriageway_half_w=0.42,
    sidewalk_color=None,
    has_double_slopes=True,
)
ROAD_090 = RoadParams(
    name="road_090",
    carriageway_color=(102, 95, 80),
    pavement_half_w=0.50,
    carriageway_half_w=0.50,
    sidewalk_color=None,
    has_double_slopes=True,
)
HIGHWAY_110 = RoadParams(
    name="highway_110",
    carriageway_color=(94, 88, 74),
    pavement_half_w=0.50,
    carriageway_half_w=0.50,
    sidewalk_color=None,
)

# road_030 — 30 km/h dirt road, narrow brown wagon track.  No kerbs;
# carriageway dither lets terrain show through, matching pak128's
# scrubby grass-and-dirt look.
#
# Note for the next reader of `way_verify` JSON: the dither-tier
# tiers below (road_030 / road_055 / cityroad_030) all score
# `alpha_iou ≈ 0.5` against pak128 cell 1.5 / 1.6.  That's not a
# bbox mismatch — both ref and candidate render the carriageway
# as a speckled alpha mask, and two ~60 % dithers IoU around 0.5
# by construction.  Read the score-vs-baseline trend, not the
# absolute number; cross-check with the diff_debug PNG.
ROAD_030 = RoadParams(
    name="road_030",
    carriageway_color=(132, 104, 74),
    pavement_half_w=0.32,
    carriageway_half_w=0.32,
    sidewalk_color=None,
    carriageway_dither_keep=0.60,
    has_double_slopes=True,
)

# road_055 — 55 km/h gravel road, narrow grey-tan path.  Same shape
# as road_030, lighter palette.
ROAD_055 = RoadParams(
    name="road_055",
    carriageway_color=(160, 148, 140),
    pavement_half_w=0.34,
    carriageway_half_w=0.34,
    sidewalk_color=None,
    carriageway_dither_keep=0.65,
    has_double_slopes=True,
)

# cityroad_030 — same speed/cost as road_030 but with the urban sand
# palette (lighter, warmer tan).
CITYROAD_030 = RoadParams(
    name="cityroad_030",
    carriageway_color=(197, 153, 107),
    pavement_half_w=0.40,
    carriageway_half_w=0.40,
    sidewalk_color=None,
    carriageway_dither_keep=0.65,
    has_double_slopes=True,
)


# --- Cross-section painter --------------------------------------------------

class RoadCrossSection(wt.CrossSection):
    """Carriageway slab + optional kerb slabs, configured by `RoadParams`.

    No cadence yet — uniform bands along every chord and bend leg
    (centre-line dashes are deferred, see `TODO.md`).
    """

    def __init__(self, params: RoadParams) -> None:
        self.params = params

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        p = self.params
        add_slab, _ = wt.make_slab_emitter(model, path)

        # Carriageway down the middle.  Perp range ascending so the
        # top-face winding is consistent (normal +z).
        add_slab(0.0, 1.0, -p.carriageway_half_w, +p.carriageway_half_w,
                 0.0, p.carriageway_top_z, p.carriageway_color,
                 dither_keep=p.carriageway_dither_keep)

        # Kerb slabs only if the tier has them and there's room.  The
        # `> carriageway_half_w` guard catches the no-kerb tiers where
        # the two half-widths are equal.
        if (p.sidewalk_color is not None
                and p.pavement_half_w > p.carriageway_half_w):
            for perp_lo, perp_hi in (
                (-p.pavement_half_w, -p.carriageway_half_w),
                (+p.carriageway_half_w, +p.pavement_half_w),
            ):
                add_slab(0.0, 1.0, perp_lo, perp_hi,
                         0.0, p.sidewalk_top_z, p.sidewalk_color,
                         dither_keep=p.sidewalk_dither_keep)


# --- Per-tier scene helper --------------------------------------------------

def make_tier(params: RoadParams):
    """Wire one road tier up for hex bake + square verification.

    Each tier's `scene.py` reduces to::

        from infrastructure.roads.road_params import ROAD_050, make_tier
        CS, bake_pakset = make_tier(ROAD_050)
        if __name__ == "__main__":
            bake_pakset()

    The returned `CS` is the per-tier `RoadCrossSection` instance
    (consumed by `way_verify.verify_square` for the dimetric diff
    against pak128 cells 1.5 / 1.6).  `bake_pakset()` delegates to
    `tools.threed.way_bake.bake_way_atlases`, which writes the three
    standard hex atlases (`_hex.png`, `_hex_slope.png`,
    `_hex_slope_half.png`) next to the tier's `.dat` — see that
    module for the atlas shapes.
    """
    cs = RoadCrossSection(params)

    def bake_pakset() -> None:
        bake_way_atlases(cs, out_dir=ROADS_DIR, name=params.name,
                         has_double_slopes=params.has_double_slopes)

    return cs, bake_pakset


def verify_tier(scene_mod) -> None:
    """Square-projection verification + hex bake for one road tier.

    Cropped refs, candidate renders, debug diffs land in the tier's
    own model dir under `infrastructure/roads/<name>/`.  Each tier's
    `build.py` reduces to::

        from . import scene
        from infrastructure.roads.road_params import verify_tier
        if __name__ == "__main__":
            verify_tier(scene)
    """
    name = scene_mod.CS.params.name
    way_verify.verify_square(
        scene_mod=scene_mod,
        sheet_path=ROADS_DIR / f"{name}.png",
        here=ROADS_DIR / name,
    )
