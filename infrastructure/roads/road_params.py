"""Road-family parameters and the shared surface painter.

Parallel to `infrastructure/rail_tracks/rail_params.py` for the rail
family — every road tier (road_030 ... road_090, cityroad_030,
highway_110) reduces to a `RoadParams` instance plus a short scene
file that pipes it into the shared `RoadSurface`.

Unlike rail, a road cell is not built from slabs: `RoadSurface`
draws one flat quad over the hex and colours each pixel from the
centreline field in `tools/threed/way_surface.py` — carriageway
material, verge, kerb and markings are bands and patterns over that
field.  What tells the tiers apart is set out in
`devdocs/hex-road-style.md`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from landscape.grounds.sidewalk.render import PAVEMENT_RGB
from tools.threed import way_surface as ws
from tools.threed import way_topology as wt
from tools.threed import way_verify
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import SUN_DIR
from tools.threed.way_bake import bake_way_atlases


ROADS_DIR = Path(__file__).resolve().parent


# --- Per-tier parameter type ------------------------------------------------

# Surface materials (`RoadParams.surface`).
ASPHALT, SETTS, DIRT, GRAVEL = "asphalt", "setts", "dirt", "gravel"
# Verges, i.e. what borders the carriageway (`RoadParams.verge`):
# a cobble sidewalk behind a kerb, sand, a clean tarmac edge, or the
# carriageway's own ragged edge fading into grass.
SIDEWALK, SAND, CLEAN, SOFT = "sidewalk", "sand", "clean", "soft"

WHITE = (214, 218, 208)
GRASS = (74, 110, 52)


@dataclass(frozen=True)
class RoadParams:
    """Look of one road tier; see `devdocs/hex-road-style.md` for what
    tells the tiers apart.  Widths are half-widths from the centreline
    in world units (edge length 1, so 0.5 fills the entry edge)."""
    name: str
    surface: str
    surface_color: tuple[int, int, int]
    half_w: float
    verge: str = SOFT
    verge_color: tuple[int, int, int] | None = None
    verge_half_w: float = 0.5
    centre_dashes: bool = False
    centre_double: bool = False
    edge_lines: bool = False
    lane_dashes: bool = False
    zebras: bool = False
    ruts: bool = False
    # `has_double_slopes=1` opt-in in the tier's .dat.  When True the
    # bake emits a second 1×6 row in `<name>_hex_slope.png` with the
    # 0→2 chord climb; the .dat references those cells via
    # `ImageUp[<axis>_double]`.
    has_double_slopes: bool = False


# --- Per-tier instances -----------------------------------------------------
# Colours are medians of each tier's pak128 straight cell (1.5).

ROAD_030 = RoadParams(
    name="road_030", surface=DIRT, surface_color=(148, 116, 78),
    half_w=0.24, ruts=True, has_double_slopes=True,
)
CITYROAD_030 = RoadParams(
    name="cityroad_030", surface=DIRT, surface_color=(140, 108, 72),
    half_w=0.26, verge=SAND, verge_color=(206, 160, 108),
    ruts=True, has_double_slopes=True,
)
ROAD_040 = RoadParams(
    name="road_040", surface=SETTS, surface_color=(101, 93, 74),
    half_w=0.32, verge=SIDEWALK, verge_color=PAVEMENT_RGB,
    has_double_slopes=True,
)
ROAD_050 = RoadParams(
    name="road_050", surface=ASPHALT, surface_color=(115, 107, 90),
    half_w=0.32, verge=SIDEWALK, verge_color=PAVEMENT_RGB,
    centre_dashes=True, zebras=True, has_double_slopes=True,
)
ROAD_055 = RoadParams(
    name="road_055", surface=GRAVEL, surface_color=(162, 151, 145),
    half_w=0.27, has_double_slopes=True,
)
ROAD_070 = RoadParams(
    name="road_070", surface=ASPHALT, surface_color=(115, 107, 90),
    half_w=0.36, verge=CLEAN, centre_dashes=True, has_double_slopes=True,
)
ROAD_090 = RoadParams(
    name="road_090", surface=ASPHALT, surface_color=(112, 105, 89),
    half_w=0.43, verge=CLEAN, centre_dashes=True, edge_lines=True,
    has_double_slopes=True,
)
HIGHWAY_110 = RoadParams(
    name="highway_110", surface=ASPHALT, surface_color=(98, 93, 80),
    half_w=0.5, verge=CLEAN, centre_double=True, edge_lines=True,
    lane_dashes=True,
)


# --- Surface painter --------------------------------------------------------

# Flat top faces are lit by this factor; colours above are what the
# player should see, so the painter divides it back out.
_FLAT_SHADE = 0.25 + 0.75 * float(max(0.0, -SUN_DIR[2]))

DASH_PERIOD = ws.STRAIGHT / 3      # three dashes per straight tile
LINE_W = 0.022                     # half-width of a painted line
BEVEL = 0.08                       # cut inside corners at junctions
ZEBRA_LEN = 0.2
KERB_W = 0.035                     # kerb stone band outside the carriageway


def _noise(sx, sy, salt: int):
    return hash_noise01(sx.astype(np.uint32) + np.uint32(salt * 7919),
                        sy.astype(np.uint32) + np.uint32(salt * 104729))


class RoadSurface(wt.CrossSection):
    """Paints a road tier as one flat surface per cell (see
    `tools/threed/way_surface.py`): carriageway, verge and markings are
    bands and patterns over the centreline field."""

    def __init__(self, params: RoadParams) -> None:
        self.params = params
        self.outer_w = params.verge_half_w \
            if params.verge in (SIDEWALK, SAND) else params.half_w

    def paint_edges(self, model, edges) -> None:
        def shader(wx, wy, sx, sy):
            f = ws.centreline_field(edges, wx, wy, band_w=self.params.half_w,
                                    bevel=BEVEL)
            return self.shade(f, sx, sy, legs=len(edges))

        model.add_quad(ws.hex_cover_quad(0.01), (0, 0, 0), shader=shader)

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        def shader(wx, wy, sx, sy):
            return self.shade(ws.straight_field(path, wx, wy), sx, sy)

        r = self.outer_w + 0.05
        (ax, ay), (bx, by) = path.start, path.end
        lo_x, hi_x = min(ax, bx) - r, max(ax, bx) + r
        lo_y, hi_y = min(ay, by) - r, max(ay, by) + r
        model.add_quad([(lo_x, lo_y, 0.01), (hi_x, lo_y, 0.01),
                        (hi_x, hi_y, 0.01), (lo_x, hi_y, 0.01)],
                       (0, 0, 0), shader=shader)

    def shade(self, f: ws.Field, sx, sy, *, legs: int = 2):
        """Colour and draw mask for the pixels of field `f`; `legs` is
        the number of edges the way leaves the cell through."""
        noise = [_noise(sx, sy, k) for k in (1, 2, 3)]
        rgb = self._material(f, noise, junction=legs >= 3)
        keep = self._verge(f, noise, rgb)
        self._markings(f, noise, rgb, legs)
        return rgb / _FLAT_SHADE, keep

    def _material(self, f, noise, *, junction):
        p = self.params
        n1, n2, n3 = noise
        s, v = f.s, f.v
        rgb = np.empty(f.d.shape + (3,))
        rgb[:] = p.surface_color
        if p.surface == ASPHALT:
            rgb *= (1 + 0.10 * (n1 - 0.5))[:, None]
            rgb[n2 < 0.05] *= 0.84
            rgb[n2 > 0.975] *= 1.12
        elif p.surface == SETTS:
            row_len, col_w = 0.07, 0.085
            row = np.floor(s / row_len)
            col = np.floor(v / col_w + 0.5 * (row % 2))
            tone = hash_noise01(row.astype(np.int64).astype(np.uint32),
                                col.astype(np.int64).astype(np.uint32))
            rgb *= (0.86 + 0.26 * tone + 0.06 * (n1 - 0.5))[:, None]
            joint = ((s / row_len) % 1 < 0.2) | \
                ((v / col_w + 0.5 * (row % 2)) % 1 < 0.16)
            rgb[joint] *= 0.7
        elif p.surface == DIRT:
            rgb *= (1 + 0.28 * (n1 - 0.5))[:, None]
            if p.ruts:
                # Worn wheel tracks: soft, broken, and absent where legs
                # cross so a junction doesn't read as crossing rails.
                lane = (np.abs(v) / p.half_w - 0.45) / 0.18
                wear = np.clip(1 - lane * lane, 0, 1) * (n3 > 0.2)
                if junction:
                    wear *= ~(f.leg_end & (s > ws.APOTHEM - p.half_w * 1.4))
                rgb *= (1 - 0.22 * wear * (0.7 + 0.6 * n2))[:, None]
                mid = (np.abs(v) < p.half_w * 0.14) & (n3 < 0.4) & ~junction
                rgb[mid] = np.array(GRASS) * (0.85 + 0.3 * n2[mid])[:, None]
        elif p.surface == GRAVEL:
            rgb *= (0.82 + 0.36 * n1)[:, None]
            rgb[n2 < 0.12] *= 0.74
            rgb[n2 > 0.94] *= 1.15
        return rgb

    def _verge(self, f, noise, rgb):
        """Paint the verge into `rgb`; return the mask of pixels drawn."""
        p = self.params
        n1, n2, n3 = noise
        d = f.d
        on_road = d < p.half_w
        if p.verge == SOFT:
            # Ragged edge: the surface thins out into the grass.
            return d < p.half_w - 0.05 + 0.08 * n3
        if p.verge == CLEAN:
            rgb[on_road & (d > p.half_w - 0.02)] *= 0.78
            return on_road
        band = (d >= p.half_w) & (d < self.outer_w)
        vc = np.empty((band.sum(), 3))
        vc[:] = p.verge_color
        nb = n1[band]
        if p.verge == SIDEWALK:
            # Cobble speckle in three tones, kerb stones on the
            # carriageway side.
            vc *= np.where(nb < 0.3, 0.82,
                           np.where(nb < 0.85, 1.0, 1.16))[:, None]
            vc[d[band] < p.half_w + KERB_W] = np.array(p.verge_color) * 1.22
        else:
            vc *= (1 + 0.16 * (nb - 0.5))[:, None]
            vc[n2[band] < 0.02] *= 0.62
        rgb[band] = vc
        rgb[on_road & (d > p.half_w - 0.018)] *= 0.62     # gutter
        return d < self.outer_w

    def _markings(self, f, noise, rgb, legs):
        """White lines on the carriageway.  On junction and dead-end legs
        they stop short of the middle; zebras cross junction legs where
        the legs' bands start to overlap."""
        p = self.params
        d, s, v = f.d, f.s, f.v
        on_road = d < p.half_w
        core = ws.APOTHEM - (p.half_w / math.sin(math.pi / 3) + BEVEL)
        zebra_lo, zebra_hi = core - ZEBRA_LEN - 0.02, core - 0.02
        stop = np.zeros_like(on_road)
        if legs >= 3:
            stop = f.leg_end & (s > (zebra_lo - 0.05 if p.zebras else core))
        elif legs == 1:
            stop = f.leg_end & (s > ws.APOTHEM - 0.1)
        paint = on_road & ~stop
        marks = np.zeros_like(on_road)
        if p.centre_dashes:
            marks |= paint & (np.abs(v) < LINE_W) & \
                ws.dashes(s, f.length, period=DASH_PERIOD)
        if p.centre_double:
            marks |= paint & (np.abs(np.abs(v) - 0.035) < LINE_W * 0.8)
        if p.lane_dashes:
            marks |= paint & (np.abs(np.abs(v) - p.half_w * 0.5) < LINE_W) & \
                ws.dashes(s, f.length, period=DASH_PERIOD)
        if p.edge_lines:
            marks |= on_road & (np.abs(d - (p.half_w - 0.055)) < LINE_W)
        if p.zebras and legs >= 3:
            marks |= on_road & f.leg_end & (s > zebra_lo) & (s < zebra_hi) & \
                (np.abs(v) < p.half_w - 0.04) & ((v / 0.1 + 0.25) % 1 < 0.5)
        rgb[marks] = np.array(WHITE) * (0.94 + 0.08 * noise[0][marks])[:, None]


# --- Per-tier scene helper --------------------------------------------------

def make_tier(params: RoadParams):
    """Wire one road tier up for hex bake + square verification.

    Each tier's `scene.py` reduces to::

        from infrastructure.roads.road_params import ROAD_050, make_tier
        CS, bake_pakset = make_tier(ROAD_050)
        if __name__ == "__main__":
            bake_pakset()

    The returned `CS` is the per-tier `RoadSurface` instance
    (consumed by `way_verify.verify_square` for the dimetric diff
    against pak128 cells 1.5 / 1.6).  `bake_pakset()` delegates to
    `tools.threed.way_bake.bake_way_atlases`, which writes the three
    standard hex atlases (`_hex.png`, `_hex_slope.png`,
    `_hex_slope_half.png`) next to the tier's `.dat` — see that
    module for the atlas shapes.
    """
    cs = RoadSurface(params)

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
