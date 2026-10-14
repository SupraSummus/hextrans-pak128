"""3D models of pak128's one-sided rail platforms for the hex grid.

The SNFOS stations, `station_03_*` and the subway stations stand a
platform on one side of the track.  The engine gives them 24 layouts,
`12 * side + 4 * axis + ends`: axis and ends as in the through stops of
`infrastructure.road_stops.hex_stops`, side 0 left of the track looking
from its S, SE or SW end and side 1 right of it.  A stop built beside
another on the parallel track takes the other side, so two of them face
each other across the strip between the tracks.

Everything on the platform side is cut to the hex: the platform runs from
its edge at the track to the tile's border, so two facing platforms meet
in one island and stops along a track join.  Halls and canopies are cut
the same way and join just as well.  The subway's `single` stations have
a platform on both sides and the 12 layouts of a two-sided stop.

    python3 -m infrastructure.rail_stations.hex_platforms.scene
    python3 -m infrastructure.rail_stations.hex_platforms.scene --preview out.png
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from infrastructure.rail_stations.hex_rail_stops.scene import (
    DARK, GLASS, IRON, P_IN, P_Z, RAIL_060, WHITE, YELLOW, glass_shader)
from infrastructure.road_stops.hex_stops.scene import AXES, RAMP, edge_frame
from infrastructure.road_stops.hex_terminals.scene import junction_preview
from tools.threed.bespoke import bake_atlas
from tools.threed.building_kit import (
    add_beam, course_shader, rewrite_images, set_layouts, speckle_shader)
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import Frame, add_block, add_face, add_prism
from tools.threed.way_surface import APOTHEM

STATIONS_DIR = Path(__file__).resolve().parent.parent
MARGIN = 0.005             # keeps a tile's parts off its neighbours'

GRAVEL = (168, 162, 150)
ASPHALT = (66, 66, 70)
CONCRETE = (184, 182, 174)
EDGE = (226, 224, 214)
SIDE = (110, 108, 100)
WOOD = (120, 76, 46)
SIGN = (40, 70, 150)
CONCRETE_ROOF = (150, 148, 142)
SLATE = (96, 96, 102)


@dataclass(frozen=True)
class PlatformParams:
    name: str
    dat: str                   # .dat stem holding the object
    surface: str = "concrete"  # gravel, asphalt, concrete or tiles
    lamps: str | None = None   # early, med or modern
    shelter: str | None = None  # hut, booth or glass
    canopy: str | None = None  # iron, white, concrete, mesh or wood
    hall: str | None = None    # early, modern or wood, over the track too
    inner: bool = False        # hall columns on the far side as well
    subway: str | None = None  # old, med or modern
    sides: int = 1             # 2: a platform on both sides, 12 layouts

    @property
    def layouts(self) -> int:
        return 12 if self.sides == 2 else 24


SNFOS = "SNFOSstations"
PLATFORMS = [
    PlatformParams("train_platform_early", SNFOS, "gravel", lamps="early"),
    PlatformParams("train_platform_med", SNFOS, "asphalt", lamps="med"),
    PlatformParams("train_platform_modern", SNFOS, lamps="modern"),
    PlatformParams("train_small_station_early", SNFOS, "gravel",
                   shelter="hut"),
    PlatformParams("train_small_station_med", SNFOS, "asphalt", lamps="med",
                   shelter="booth"),
    PlatformParams("train_small_station_modern", SNFOS, lamps="modern",
                   shelter="glass"),
    PlatformParams("train_station_early", SNFOS + "2", "asphalt",
                   canopy="iron"),
    PlatformParams("train_station_modern", SNFOS + "2", canopy="white"),
    PlatformParams("train_flat_station_early", SNFOS + "2", "asphalt",
                   canopy="concrete"),
    PlatformParams("train_flat_station_modern", SNFOS + "2", canopy="mesh"),
    PlatformParams("train_big_station_early_ext", SNFOS + "3", "asphalt",
                   hall="early"),
    PlatformParams("train_big_station_modern_ext", SNFOS + "3",
                   hall="modern"),
    PlatformParams("train_big_station_modern_int", SNFOS + "3",
                   hall="modern", inner=True),
    PlatformParams("station_03_02", "station_03_02", canopy="wood"),
    PlatformParams("station_03_03", "station_03_03", hall="wood"),
    PlatformParams("subway_single_old_station", "subway_station_0", "tiles",
                   subway="old", sides=2),
    PlatformParams("subway_double_old_station", "subway_station_0", "tiles",
                   subway="old"),
    PlatformParams("subway_single_station", "subway_station_1", "tiles",
                   subway="med", sides=2),
    PlatformParams("subway_double_station", "subway_station_1", "tiles",
                   subway="med"),
    PlatformParams("subway_single_modern_station", "subway_station_2",
                   "tiles", subway="modern", sides=2),
    PlatformParams("subway_double_modern_station", "subway_station_2",
                   "tiles", subway="modern"),
]


# --- The hex, cut across the track --------------------------------------------

def reach(p: float) -> float:
    """Half the length along the track of the hex at `p` from it."""
    a = APOTHEM if abs(p) <= 0.5 else 2 * APOTHEM * (1 - abs(p))
    return max(a - MARGIN, 0.0)


def p_at_reach(a: float) -> float:
    """The `p` > 0.5 where the hex is `2 a` long."""
    return 1 - (a + MARGIN) / (2 * APOTHEM)


def hex_poly(p0: float, p1: float, lo: float | None = None,
             hi: float | None = None) -> list[tuple[float, float]]:
    """The hex between `p0` and `p1` across the track, cut short of
    `s = -lo` and `s = hi` along it when they are given: a convex
    polygon of `(s, p)` corners."""
    lo = APOTHEM if lo is None else lo
    hi = APOTHEM if hi is None else hi
    ps = {p0, p1}
    for p in (-0.5, 0.5):
        if p0 < p < p1:
            ps.add(p)
    for cap in (lo, hi):
        if cap < reach(0.5):
            for p in (p_at_reach(cap), -p_at_reach(cap)):
                if p0 < p < p1:
                    ps.add(p)
    ps = sorted(ps)
    right = [(min(reach(p), hi), p) for p in ps]
    left = [(-min(reach(p), lo), p) for p in reversed(ps)]
    poly = right + left
    out = []
    for pt in poly:   # drop repeated corners where the hex comes to a point
        if not out or np.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) > 1e-6:
            out.append(pt)
    if len(out) > 1 and np.allclose(out[0], out[-1]):
        out.pop()
    return out


def side_frame(fr: Frame, sign: int) -> Frame:
    """`fr` with `p` running out to the platform on side `sign`."""
    f = Frame(fr.u)
    f.v = (fr.v[0] * sign, fr.v[1] * sign)
    return f


def layer_of(f: Frame, p: float) -> str:
    """The layer of a part at `p`: front when it is on the camera side
    of the track."""
    return "front" if f.front_sign() * p > 0 else "back"


# --- Platform -----------------------------------------------------------------

def surface_shader(f: Frame, surface: str, subway: str | None):
    base = np.array({"gravel": GRAVEL, "asphalt": ASPHALT,
                     "concrete": CONCRETE, "tiles": TILE[subway]}[surface],
                    float)

    def top(wx, wy, sx, sy):
        s, p = f.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        if surface == "gravel":
            rgb = base * np.where(n < 0.35, 0.82, np.where(n < 0.85, 1.0, 1.12)
                                  )[:, None]
        elif surface == "tiles":
            check = ((np.floor(s / 0.08) + np.floor(p / 0.08)) % 2)[:, None]
            rgb = base * (0.97 + 0.04 * check + 0.03 * n[:, None])
        else:
            rgb = base * (0.95 + 0.08 * n)[:, None]
        rgb[p < P_IN + 0.03] = EDGE
        rgb[np.abs(p - P_IN - 0.05) < 0.007] = YELLOW if surface != "gravel" \
            else (240, 240, 236)
        return rgb, np.ones(len(wx), bool)

    return top


def platform(model, f: Frame, ends: int, st: PlatformParams) -> None:
    """The platform from its edge at the track to the tile's border,
    ramped down short of an open end (`ends` bit 0 at `-s`, bit 1 at
    `+s`)."""
    cap = reach(P_IN) - RAMP
    lo = cap if ends & 1 else None
    hi = cap if ends & 2 else None
    layer = layer_of(f, 1)
    add_prism(model, f, hex_poly(P_IN, 1.0, lo, hi), 0.0, P_Z,
              TILE[st.subway] if st.subway else CONCRETE, layer,
              top_shader=surface_shader(f, st.surface, st.subway),
              side_color=SIDE)
    p_x = p_at_reach(cap)
    for bit, sign in ((1, -1), (2, 1)):
        if ends & bit:
            add_face(model, [f.world(sign * cap, P_IN, P_Z),
                             f.world(sign * cap, p_x, P_Z),
                             f.world(sign * (cap + RAMP), P_IN, 0.002)],
                     CONCRETE, layer,
                     outward=f.world(sign * cap, (P_IN + p_x) / 2, -1))


def bench(model, f, s, p, layer, colour=WOOD):
    add_block(model, f, s - 0.09, s + 0.09, p - 0.03, p + 0.03, P_Z + 0.04,
              P_Z + 0.055, colour, layer)
    add_block(model, f, s - 0.09, s + 0.09, p + 0.02, p + 0.03, P_Z + 0.055,
              P_Z + 0.1, colour, layer)
    for ds in (-0.07, 0.07):
        add_block(model, f, s + ds - 0.01, s + ds + 0.01, p - 0.02, p + 0.02,
                  P_Z, P_Z + 0.04, DARK, layer)


def post(model, f, s, p, z1, colour, layer, w=0.012):
    add_block(model, f, s - w, s + w, p - w, p + w, P_Z, z1, colour, layer)


def lamps(model, f, kind):
    for s in (-0.4, 0.4):
        p = 0.62
        layer = layer_of(f, p)
        post(model, f, s, p, 0.44 if kind == "modern" else 0.38,
             (200, 202, 206) if kind == "modern" else DARK, layer)
        if kind == "early":
            add_block(model, f, s - 0.025, s + 0.025, p - 0.025, p + 0.025,
                      0.36, 0.42, (238, 226, 160), layer)
            add_block(model, f, s - 0.03, s + 0.03, p - 0.03, p + 0.03,
                      0.42, 0.44, DARK, layer)
        else:
            add_block(model, f, s - 0.05, s + 0.05, p - 0.08, p + 0.01,
                      0.4 if kind == "med" else 0.44, 0.42 if kind == "med"
                      else 0.455, WHITE, layer)
    # Station name board between the lamps.
    if kind in ("med", "modern"):
        p = 0.6
        layer = layer_of(f, p)
        for s in (-0.12, 0.12):
            post(model, f, s, p, 0.3, DARK, layer, w=0.008)
        add_block(model, f, -0.15, 0.15, p - 0.008, p + 0.008, 0.22, 0.3,
                  SIGN, layer)


# --- Shelters -----------------------------------------------------------------

def shelter(model, f, kind):
    p0, p1, s0 = 0.4, 0.76, 0.26
    layer = layer_of(f, p0)
    if kind == "hut":
        wall = speckle_shader(WOOD)
        add_block(model, f, -s0, s0, p1 - 0.04, p1, P_Z, 0.32, WOOD, layer,
                  side_shader=wall)
        for s in (-s0, s0 - 0.04):
            add_block(model, f, s, s + 0.04, p0 + 0.06, p1, P_Z, 0.32, WOOD,
                      layer, side_shader=wall)
        add_block(model, f, -s0 - 0.04, s0 + 0.04, p0, p1 + 0.04, 0.32,
                  0.35, SLATE, layer, top_shader=course_shader(f, SLATE))
        bench(model, f, 0.0, p1 - 0.12, layer)
    elif kind == "booth":
        grey = (176, 176, 170)
        add_block(model, f, -s0, s0, p0 + 0.06, p1, P_Z, 0.3, grey, layer,
                  side_shader=speckle_shader(grey))
        add_block(model, f, -s0 + 0.03, s0 - 0.03, p0 + 0.055, p0 + 0.06,
                  0.16, 0.26, (80, 120, 180), layer)
        add_block(model, f, -s0 - 0.03, s0 + 0.03, p0 + 0.03, p1 + 0.03,
                  0.3, 0.33, (120, 120, 118), layer)
    else:
        for s in (-s0, s0):
            for p in (p0 + 0.06, p1):
                post(model, f, s, p, 0.3, WHITE, layer)
        add_block(model, f, -s0, s0, p1 - 0.01, p1, P_Z + 0.03, 0.28, GLASS,
                  layer)
        for s in (-s0, s0):
            add_block(model, f, s - 0.005, s + 0.005, p0 + 0.06, p1, P_Z + 0.03,
                      0.28, GLASS, layer)
        add_block(model, f, -s0 - 0.03, s0 + 0.03, p0, p1 + 0.03, 0.3, 0.32,
                  (40, 60, 110), layer)
        bench(model, f, 0.0, p1 - 0.1, layer, colour=(200, 202, 206))


# --- Canopies and halls -------------------------------------------------------

def slab(model, f, p0, p1, z, t, colour, layer, shader=None):
    add_prism(model, f, hex_poly(p0, p1), z, z + t, colour, layer,
              top_shader=shader, side_color=tuple(int(c * 0.8) for c in colour))


def canopy(model, f, kind):
    """A roof over the platform on posts along its middle."""
    p_post = 0.62
    layer = layer_of(f, p_post)
    colour = {"iron": IRON, "white": WHITE, "concrete": CONCRETE_ROOF,
              "mesh": WHITE, "wood": WOOD}[kind]
    z = 0.42
    for s in (-0.4, 0.4):
        if kind == "concrete":
            add_block(model, f, s - 0.03, s + 0.03, p_post - 0.03,
                      p_post + 0.03, P_Z, z, CONCRETE_ROOF, layer,
                      side_shader=speckle_shader(CONCRETE_ROOF))
        else:
            post(model, f, s, p_post, z, colour, layer, w=0.016)
        if kind in ("iron", "wood"):
            # Brackets from the post out under both eaves.
            for dp in (-0.3, 0.25):
                add_beam(model, f.world(s, p_post, z - 0.12),
                         f.world(s, p_post + dp, z - 0.005), 0.012, colour,
                         layer=layer)
    roof = {"iron": glass_shader(f, GLASS, IRON),
            "white": glass_shader(f, (214, 222, 228), WHITE),
            "mesh": glass_shader(f, (200, 214, 224), WHITE),
            "concrete": speckle_shader(CONCRETE_ROOF),
            "wood": course_shader(f, (110, 84, 60))}[kind]
    tone = {"iron": GLASS, "white": (214, 222, 228), "mesh": (200, 214, 224),
            "concrete": CONCRETE_ROOF, "wood": (110, 84, 60)}[kind]
    slab(model, f, P_IN + 0.03, 1.0, z, 0.025 if kind != "concrete" else 0.04,
         tone, layer, roof)
    if kind == "concrete":
        # A wind wall down the platform under the cantilever.
        add_block(model, f, -0.36, 0.36, p_post - 0.012, p_post + 0.012, P_Z,
                  0.3, CONCRETE_ROOF, layer,
                  side_shader=speckle_shader(CONCRETE_ROOF))
    for s in (-0.25, 0.25):
        bench(model, f, s, 0.5, layer)


def hall(model, f, kind, inner):
    """A roof over the platform and the track on columns along the
    platform, and along the far side of the track for an inner bay.  It
    ends straight half a tile beyond the track, where the hall over the
    next track begins."""
    z = 0.62
    colour = {"early": IRON, "modern": WHITE, "wood": WOOD}[kind]
    columns = [0.64] + ([-0.42] if inner else [])
    for p in columns:
        layer = layer_of(f, p)
        for s in (-0.3, 0.3):
            post(model, f, s, p, z, colour, layer, w=0.02)
            add_beam(model, f.world(s, p, z - 0.15),
                     f.world(s, p - 0.3, z - 0.01), 0.014, colour,
                     layer=layer)
            add_beam(model, f.world(s, p, z - 0.15),
                     f.world(s, p + 0.25, z - 0.01), 0.014, colour,
                     layer=layer)
    if kind == "early":
        roof = course_shader(f, (110, 112, 118))
        slab(model, f, -0.5, 1.0, z, 0.03, (110, 112, 118), "front", roof)
        # Glazed lantern over the track.
        add_prism(model, f, hex_poly(-0.3, 0.3), z + 0.03, z + 0.1, IRON,
                  "front", top_shader=glass_shader(f, GLASS, IRON))
    elif kind == "modern":
        slab(model, f, -0.5, 1.0, z, 0.025, (206, 218, 228), "front",
             glass_shader(f, (206, 218, 228), WHITE))
    else:
        # Timber station roof, hipped over the platform.
        slab(model, f, -0.5, 1.0, z - 0.06, 0.04, (110, 84, 60), "front",
             course_shader(f, (110, 84, 60)))
        add_prism(model, f, hex_poly(-0.4, 0.8), z - 0.02, z + 0.06,
                  (96, 72, 52), "front",
                  top_shader=course_shader(f, (96, 72, 52)))
    for s in (-0.25, 0.25):
        bench(model, f, s, 0.45, layer_of(f, 0.45))


# --- Subway -------------------------------------------------------------------

TILE = {None: CONCRETE, "old": (214, 204, 176), "med": (222, 224, 226),
        "modern": (210, 214, 220)}
SUBWAY_TRIM = {"old": (120, 60, 40), "med": (40, 80, 160),
               "modern": (60, 64, 72)}
POSTERS = ((200, 70, 50), (60, 110, 170), (220, 180, 60), (90, 150, 90))


def subway(model, f, kind, two_sided):
    """Benches back to back with an advert board between them down the
    middle of the platform, and a sign hung over its edge."""
    p = 0.62 if not two_sided else 0.58
    layer = layer_of(f, p)
    trim = SUBWAY_TRIM[kind]
    for k, s in enumerate((-0.35, 0.35)):
        add_block(model, f, s - 0.14, s + 0.14, p - 0.012, p + 0.012, P_Z,
                  0.3, trim, layer)
        add_block(model, f, s - 0.12, s + 0.12, p - 0.014, p + 0.014, 0.1,
                  0.26, POSTERS[(k + len(kind)) % len(POSTERS)], layer)
        bench(model, f, s, p - 0.08, layer,
              colour=WOOD if kind == "old" else trim)
    for s in (-0.18, 0.18):
        post(model, f, s, P_IN + 0.12, 0.42, DARK, layer, w=0.006)
    add_block(model, f, -0.2, 0.2, P_IN + 0.11, P_IN + 0.13, 0.34, 0.4, trim,
              layer)
    if kind == "modern":
        # Glass screen along the platform edge.
        add_block(model, f, -0.7, 0.7, P_IN + 0.035, P_IN + 0.045, P_Z,
                  0.22, GLASS, layer)


# --- Scene --------------------------------------------------------------------

def build(st: PlatformParams, layout: int) -> Model:
    ends = layout & 3
    fr = edge_frame(AXES[(layout % 12) // 4])
    model = Model()
    signs = (1, -1) if st.sides == 2 else ((1, -1)[layout // 12],)
    for sign in signs:
        f = side_frame(fr, sign)
        platform(model, f, ends, st)
        if st.lamps:
            lamps(model, f, st.lamps)
        if st.shelter:
            shelter(model, f, st.shelter)
        if st.canopy:
            canopy(model, f, st.canopy)
        if st.hall:
            hall(model, f, st.hall, st.inner)
        if st.subway:
            subway(model, f, st.subway, st.sides == 2)
    return model


def render_layer(st, layout, layer):
    return render(build(st, layout), HexCamera(), layer_filter=layer)


def image_lines(st: PlatformParams) -> list[str]:
    lines = []
    for layout in range(st.layouts):
        row, col = divmod(2 * layout, 8)
        lines.append(f"BackImage[{layout}][0][0][0][0][0]="
                     f"{st.name}_hex.{row}.{col}")
        lines.append(f"FrontImage[{layout}][0][0][0][0][0]="
                     f"{st.name}_hex.{row}.{col + 1}")
    return lines


def bake_pakset() -> None:
    for st in PLATFORMS:
        entries = [(f"{layer}[{layout}]",
                    lambda s=st, lo=layout, la=layer: render_layer(s, lo, la))
                   for layout in range(st.layouts)
                   for layer in ("back", "front")]
        bake_atlas(out_png=STATIONS_DIR / f"{st.name}_hex.png",
                   entries=entries, cols_per_row=8)
    for dat in sorted({st.dat for st in PLATFORMS}):
        path = STATIONS_DIR / f"{dat}.dat"
        own = [st for st in PLATFORMS if st.dat == dat]
        rewrite_images(path, {st.name: image_lines(st) for st in own})
        set_layouts(path, {st.name: st.layouts for st in own})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write each station on the legs of a junction, "
                         "one file per station, instead of baking")
    ap.add_argument("--only", nargs="*", help="names to preview")
    a = ap.parse_args()
    if a.preview:
        face = {"N": 3, "S": 3, "NW": 7, "SE": 7, "NE": 11, "SW": 11}
        for st in PLATFORMS:
            if a.only and st.name not in a.only:
                continue
            junction_preview(
                [lambda d, s=st: {la: render_layer(s, face[d], la)
                                  for la in ("back", "front")},
                 lambda d, s=st: {la: render_layer(
                     s, face[d] + (12 if s.sides == 1 else 0), la)
                     for la in ("back", "front")}],
                a.preview.with_stem(f"{a.preview.stem}_{st.name}"), RAIL_060)
    else:
        bake_pakset()
