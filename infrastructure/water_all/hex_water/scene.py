"""3D models of pak128's harbours, ship depot and canal stops for the
hex grid.

A harbour is two tiles: the shore tile, a slope rising from the water,
and the water tile in front of it.  The engine builds one on four of the
six hex faces (S, SE, N, NW: layouts 0..3); longer docks have no NE-SW
footprint yet (`dock_footprint_missing` in the engine).  Here the shore
tile carries a stone quay, level with the top of the slope, with the
buildings on it facing the water, and the water tile mooring piles and
buoys, as pak128's harbours do.

The ship depot is a through depot (`Dims=1,1,3`, a layout per hex axis):
a boat shed across the water, open at both ends.  The canal stops are
through stops with the 12 layouts of `infrastructure.road_stops.hex_stops`,
quays along both banks.

    python3 -m infrastructure.water_all.hex_water.scene
    python3 -m infrastructure.water_all.hex_water.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from infrastructure.rail_stations.hex_rail_stops.scene import (
    CONTAINERS, DARK, GLASS, P_IN, P_OUT, P_Z, container, crates, forklift,
    platform)
from infrastructure.road_stops.hex_stops.scene import (
    AXES, LAYOUTS, bench, edge_frame, rewrite_dat)
from tools.threed.bespoke import bake_atlas
from tools.threed.building import (
    SQRT3, composite, ground_cell, render_tiles, tile_centre)
from tools.threed.building_kit import (
    AMBIENT, STOREY, Palette, add_beam, course_shader, gabled_block,
    rewrite_images, set_layouts, speckle_shader)
from tools.threed.hex_synth import HexGeom, hash_noise01
from tools.threed.render import (
    HexCamera, Model, engine_z_per_step, render, unit)
from tools.threed.solids import (
    Frame, add_block, add_frustum, add_prism, add_roof)
from tools.threed.way_surface import APOTHEM

WATER_DIR = Path(__file__).resolve().parent.parent
QUAY = engine_z_per_step(1)      # the top of the shore slope
STONE = (150, 140, 124)
PAVING = (168, 160, 146)
TIMBER = (112, 84, 56)
RED_TILE = Palette(wall=(214, 196, 160), trim=(236, 228, 210),
                   roof=(178, 84, 58))
SHED = Palette(wall=(132, 136, 132), trim=(170, 172, 168),
               roof=(110, 114, 112), glass=(56, 66, 84))
POST = Palette(wall=(150, 150, 140), trim=(206, 202, 190),
               roof=(96, 100, 104))
YELLOW = (226, 190, 30)
CRANE_RED = (170, 46, 36)
CONCRETE = (176, 174, 166)

# Water faces of layouts 0..3, and where the shore and water tiles sit in
# the footprint: the footprint runs from the shore for S and SE and from
# the far end for N and NW (`tool_station_dock_aux`).
DOCK_FACES = ("S", "SE", "N", "NW")
DOCK_TILES = (((0, 0), (0, 1)), ((0, 0), (1, 0)),
              ((0, 1), (0, 0)), ((1, 0), (0, 0)))


@dataclass(frozen=True)
class DockParams:
    name: str
    dat: str
    kind: str            # pax, post, timber, bulk or crates


DOCKS = [
    DockParams("ShipStop", "shipstop", "pax"),
    DockParams("Post_Dock", "post_dock", "post"),
    DockParams("Long_Goods_Dock", "long_goods_dock", "timber"),
    DockParams("Bulk_Dock", "bulk_dock", "bulk"),
    DockParams("Crate_Goods_Dock", "crate_goods_dock", "crates"),
]


# --- Sub-models ---------------------------------------------------------------

def lifted(model: Model, dz: float, build) -> None:
    """Run `build` on a fresh model and add its parts `dz` higher."""
    sub = Model()
    build(sub)
    base = len(model.verts)
    model.verts.extend((x, y, z + dz) for x, y, z in sub.verts)
    model.quads.extend((i0 + base, i1 + base, i2 + base, i3 + base, *rest)
                       for i0, i1, i2, i3, *rest in sub.quads)


def hex_ring(r: float = 1.0) -> list[tuple[float, float]]:
    """The hex corners in such a frame, scaled by `r`: 30 degrees off
    the edge midpoints."""
    return [(r * math.cos(math.radians(a + 30)),
             r * math.sin(math.radians(a + 30))) for a in range(0, 360, 60)]


def paving(fr: Frame, base=PAVING, pitch=0.12):
    base = np.array(base, float)

    def shader(wx, wy, sx, sy):
        s, p = fr.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        joint = (np.abs((s / pitch) % 1 - 0.5) > 0.46) | \
            (np.abs(((p + 0.5 * np.floor(s / pitch)) / pitch) % 1 - 0.5) > 0.46)
        rgb = base * (0.94 + 0.1 * n)[:, None]
        rgb[joint] *= 0.82
        return rgb, np.ones(len(wx), bool)

    return shader


def masonry(fr: Frame):
    base = np.array(STONE, float)

    def shader(wx, wy, sx, sy):
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * np.where(n < 0.15, 0.78, np.where(n < 0.9, 1.0, 1.1)
                              )[:, None]
        rgb[(sy % 5) == 0] *= 0.8
        return rgb, np.ones(len(wx), bool)

    return shader


# --- Harbours -----------------------------------------------------------------

def quay(model, fr):
    """The stone quay over the shore tile, its top level with the top of
    the slope, a kerb and bollards along the water edge."""
    ring = hex_ring()
    add_prism(model, fr, ring, -0.06, QUAY, STONE, top_shader=paving(fr),
              side_shader=masonry(fr))
    edge = APOTHEM - 0.03
    add_block(model, fr, edge - 0.03, edge, -0.5, 0.5, QUAY, QUAY + 0.02,
              (196, 190, 176))
    for p in (-0.35, 0.0, 0.35):
        add_frustum(model, fr, edge - 0.07, p, 0.022, 0.018, QUAY,
                    QUAY + 0.05, DARK, n=6)


def moorings(model, fr):
    """Piles along the berth on the water tile and two buoys."""
    s0 = SQRT3 - APOTHEM + 0.08
    for p in (-0.45, 0.45):
        for ds in (0.0, 0.35):
            add_frustum(model, fr, s0 + ds, p, 0.025, 0.025, -0.05, QUAY + 0.04,
                        TIMBER, n=6)
    for p in (-0.6, 0.6):
        add_frustum(model, fr, SQRT3 + 0.35, p * 0.6, 0.04, 0.025, 0.0, 0.06,
                    (200, 60, 40), n=8)


def lattice_mast(model, a, b, w, colour):
    """Two chords and zigzag braces from `a` to `b` in the vertical
    plane through them."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    side = np.cross(d, (0.0, 0.0, 1.0))
    if math.hypot(*side) < 1e-6:
        side = np.array((1.0, 0.0, 0.0))
    side = unit(side) * w / 2
    for o in (side, -side):
        add_beam(model, a + o, b + o, 0.012, colour)
    n = max(2, int(math.hypot(*d) / 0.08))
    for k in range(n):
        p0 = a + d * k / n + (side if k % 2 else -side)
        p1 = a + d * (k + 1) / n + (-side if k % 2 else side)
        add_beam(model, p0, p1, 0.008, colour)


def jib_crane(model, fr, s, p, colour, height=0.55, reach_s=0.55):
    """A portal crane on the quay edge, its jib out over the water."""
    for ds in (-0.06, 0.06):
        for dp in (-0.06, 0.06):
            add_beam(model, fr.world(s + ds, p + dp, 0.0),
                     fr.world(s + ds * 0.4, p + dp * 0.4, 0.16), 0.02, colour)
    add_block(model, fr, s - 0.05, s + 0.05, p - 0.05, p + 0.05, 0.16, 0.3,
              colour, side_color=tuple(int(c * 0.8) for c in colour))
    add_block(model, fr, s - 0.07, s - 0.02, p - 0.04, p + 0.04, 0.3, 0.36,
              (60, 60, 64))
    lattice_mast(model, fr.world(s, p, 0.3), fr.world(s, p, height), 0.05,
                 colour)
    lattice_mast(model, fr.world(s, p, 0.34),
                 fr.world(s + reach_s, p, height + 0.12), 0.04, colour)
    add_beam(model, fr.world(s + reach_s, p, height + 0.11),
             fr.world(s + reach_s, p, 0.22), 0.004, DARK)


def dock_buildings(model, fr, kind):
    """What stands on the quay, in the frame of the shore tile with `s`
    towards the water."""
    if kind == "pax":
        for p in (-0.3, 0.3):
            gabled_block(model, Frame(fr.u, origin=fr.world(0, p, 0)[:2]),
                         -0.62, -0.1, 0.2, 2, RED_TILE, pitch=0.16,
                         stepped=False, bays=2)
        # Waiting hall along the berth.
        for s in (0.32, 0.66):
            for p in (-0.45, 0.0, 0.45):
                add_block(model, fr, s - 0.012, s + 0.012, p - 0.012, p + 0.012,
                          0.0, 0.24, (70, 80, 96))
        add_roof(model, fr, 0.28, 0.7, -0.5, 0.5, 0.24, 0.24, 0.02, GLASS)
        for p in (-0.25, 0.25):
            bench(model, Frame(fr.v, origin=fr.world(0.5, 0, 0)[:2]),
                  1, "back", p, 0.0)
    elif kind == "post":
        gabled_block(model, Frame(fr.v, origin=fr.world(-0.3, 0, 0)[:2]),
                     -0.5, 0.5, 0.28, 2, POST, pitch=0.1, stepped=False,
                     bays=4)
        add_block(model, fr, 0.0, 0.42, -0.3, 0.3, 0.0, STOREY, POST.wall,
                  side_shader=speckle_shader(POST.wall))
        add_block(model, fr, -0.02, 0.44, -0.32, 0.32, STOREY, STOREY + 0.03,
                  POST.trim)
        add_block(model, fr, 0.42, 0.425, -0.2, 0.2, 0.04, 0.17, (60, 66, 84))
        add_block(model, fr, 0.425, 0.43, -0.1, 0.1, STOREY - 0.06,
                  STOREY - 0.01, YELLOW)
        for p in (-0.42, 0.42):
            crates(model, fr, 0.62, p, n=2, size=0.05, colour=YELLOW)
    elif kind == "timber":
        # Gantry over the timber stacks, legs on both quay sides.
        for s in (-0.55, 0.62):
            for p in (-0.5, 0.5):
                add_block(model, fr, s - 0.025, s + 0.025, p - 0.025,
                          p + 0.025, 0.0, 0.5, YELLOW,
                          side_color=(190, 156, 20))
            lattice_mast(model, fr.world(s, -0.5, 0.5), fr.world(s, 0.5, 0.5),
                         0.06, YELLOW)
        for p in (-0.5, 0.5):
            lattice_mast(model, fr.world(-0.55, p, 0.53),
                         fr.world(0.62, p, 0.53), 0.06, YELLOW)
        add_block(model, fr, 0.0, 0.14, -0.1, 0.1, 0.48, 0.58, YELLOW)
        add_beam(model, fr.world(0.07, 0, 0.48), fr.world(0.07, 0, 0.2), 0.004,
                 DARK)
        for k, (s, p) in enumerate(((-0.35, -0.25), (-0.35, 0.22),
                                    (0.15, -0.25), (0.15, 0.22))):
            for j in range(3 - k % 2):
                add_block(model, fr, s - 0.18, s + 0.18,
                          p - 0.12 + j * 0.02, p + 0.12 - j * 0.02,
                          j * 0.05, (j + 1) * 0.05, TIMBER,
                          top_shader=course_shader(Frame(fr.v), TIMBER, 0.03),
                          side_color=(150, 116, 80))
    elif kind == "bulk":
        for k, (s, p) in enumerate(((-0.55, -0.25), (-0.55, 0.12),
                                    (-0.2, -0.25), (-0.2, 0.12))):
            add_frustum(model, fr, s, p, 0.16, 0.16, 0.0, 0.62, CONCRETE, n=12,
                        side_shader=speckle_shader(CONCRETE))
            add_frustum(model, fr, s, p, 0.16, 0.05, 0.62, 0.7, CONCRETE, n=12)
        add_block(model, fr, -0.3, 0.05, 0.3, 0.55, 0.0, 0.85, (120, 116, 110),
                  side_shader=speckle_shader((120, 116, 110)))
        add_block(model, fr, -0.32, 0.07, 0.28, 0.57, 0.85, 0.88, (90, 88, 86))
        lattice_mast(model, fr.world(0.0, 0.42, 0.75), fr.world(0.7, 0.2, 0.42),
                     0.06, (70, 70, 74))
        add_beam(model, fr.world(0.7, 0.2, 0.42), fr.world(0.82, 0.2, 0.22),
                 0.03, (70, 70, 74))
        add_frustum(model, fr, 0.45, -0.3, 0.18, 0.02, 0.0, 0.12, (52, 48, 46),
                    n=10, side_shader=speckle_shader((52, 48, 46)))
    elif kind == "crates":
        gabled_block(model, Frame(fr.v, origin=fr.world(-0.3, 0, 0)[:2]),
                     -0.5, 0.5, 0.32, 2, SHED, pitch=0.12, stepped=False,
                     bays=4)
        jib_crane(model, fr, 0.55, -0.3, CRANE_RED, height=0.62)
        for k, p in enumerate((0.05, 0.3)):
            container(model, Frame(fr.v, origin=fr.world(0.42, 0, 0)[:2]),
                      p - 0.1, 0.0, 0.0, CONTAINERS[k], "back", length=0.3)
            container(model, Frame(fr.v, origin=fr.world(0.42, 0, 0)[:2]),
                      p - 0.1, 0.0, 0.11, CONTAINERS[k + 2], "back",
                      length=0.3)


def dock_model(kind: str, layout: int) -> Model:
    shore, water = DOCK_TILES[layout]
    a, b = tile_centre(*shore), tile_centre(*water)
    fr = Frame((b[0] - a[0], b[1] - a[1]), origin=a)
    model = Model()
    quay(model, fr)
    lifted(model, QUAY, lambda m: dock_buildings(m, fr, kind))
    if kind == "timber":
        lifted(model, QUAY, lambda m: jib_crane(m, fr, 0.62, 0.3, YELLOW,
                                                 height=0.5, reach_s=0.45))
    moorings(model, fr)
    return model


def dock_dims(layout: int) -> tuple[int, int]:
    return (1, 2) if layout % 2 == 0 else (2, 1)


def bake_dock(dock: DockParams) -> list[str]:
    """One row per layout, the shore tile's heights then the water
    tile's; return the `.dat` image lines."""
    rows, lines = [], []
    for layout in range(4):
        tiles = render_tiles(dock_model(dock.kind, layout), dock_dims(layout),
                             levels=6, ambient=AMBIENT)
        rows.append(tiles)
    width = max(len(c) for t in rows for c in t.values())
    blank = np.zeros_like(next(iter(rows[0].values()))[0])
    entries = []
    for layout, tiles in enumerate(rows):
        for t, xy in enumerate(DOCK_TILES[layout]):
            cells = tiles[xy]
            for z in range(width):
                col = t * width + z
                entries.append((f"[{layout}]{xy}[{z}]",
                                lambda c=(cells[z] if z < len(cells) else blank):
                                c))
                if z < len(cells):
                    lines.append(f"BackImage[{layout}][{xy[1]}][{xy[0]}][{z}]"
                                 f"[0][0]={dock.dat}_hex.{layout}.{col}")
    bake_atlas(out_png=WATER_DIR / f"{dock.dat}_hex.png", entries=entries,
               cols_per_row=2 * width)
    return lines


# --- Ship depot ---------------------------------------------------------------

def boat(model, fr, layer):
    hull = [(-0.42, 0.0), (-0.36, -0.12), (0.3, -0.12), (0.46, 0.0),
            (0.3, 0.12), (-0.36, 0.12)]
    add_prism(model, fr, hull, -0.02, 0.08, (60, 70, 96), layer,
              top_shader=course_shader(fr, (150, 112, 74), 0.04),
              side_color=(48, 56, 78))
    add_block(model, fr, -0.25, 0.05, -0.08, 0.08, 0.08, 0.2, (226, 226, 220),
              layer)
    add_block(model, fr, -0.2, 0.0, -0.085, 0.085, 0.14, 0.18, (60, 70, 90),
              layer)


def depot_model(axis: int) -> Model:
    """A timber boat shed across the water, along the hex axis."""
    fr = edge_frame(AXES[axis])
    model = Model()
    front = fr.front_sign()
    a = APOTHEM - 0.08
    w, eave, ridge = 0.62, 0.36, 0.56
    for side in (-1, 1):
        layer = "front" if side == front else "back"
        add_block(model, fr, -a, a, side * w - 0.03, side * w + 0.03, -0.05,
                  0.06, STONE, layer, side_shader=masonry(fr))
        add_block(model, fr, -a, a, side * w - 0.015, side * w + 0.015, 0.06,
                  eave, TIMBER, layer, side_shader=course_shader(
                      Frame((0.0, 1.0)), TIMBER, 0.03))
        for s in np.linspace(-a + 0.15, a - 0.15, 4):
            add_block(model, fr, s - 0.06, s + 0.06, side * (w + 0.016),
                      side * (w + 0.02), 0.18, 0.28, (60, 66, 84), layer)
        add_roof(model, fr, -a - 0.04, a + 0.04, side * (w + 0.08), 0.0,
                 eave - 0.03, ridge, 0.025, (100, 72, 54), "front",
                 shader=course_shader(fr, (100, 72, 54)))
    boat(model, fr, "back")
    return model


# --- Canal stops --------------------------------------------------------------

CANAL_STOPS = (("canal_ChannelStop", "canal_channelstop", "pax"),
               ("canal_ware_stop", "canal_ware_stop", "goods"))


def canal_stop_model(kind: str, layout: int) -> Model:
    ends = layout & 3
    fr = edge_frame(AXES[layout // 4])
    model = Model()
    front = fr.front_sign()
    far = -front if front else -1
    for side in (1, -1):
        layer = "front" if side == front else "back"
        platform(model, fr, side, layer, ends)
    if kind == "pax":
        # A glazed waiting room on the far bank.
        p0, p1 = P_IN + 0.12, P_OUT - 0.04
        for s in (-0.3, 0.3):
            for p in (p0, p1):
                add_block(model, fr, s - 0.012, s + 0.012, far * p - 0.012,
                          far * p + 0.012, P_Z, 0.3, (40, 60, 110), "back")
        lo, hi = sorted((far * p0, far * p1))
        add_block(model, fr, -0.3, 0.3, far * p1 - 0.008, far * p1 + 0.008,
                  P_Z + 0.04, 0.28, GLASS, "back")
        add_block(model, fr, -0.33, 0.33, lo - 0.03, hi + 0.03, 0.3, 0.33,
                  (40, 60, 110), "back")
        for s in (-0.55, 0.55):
            add_block(model, fr, s - 0.008, s + 0.008, far * (P_IN + 0.1) - 0.008,
                      far * (P_IN + 0.1) + 0.008, P_Z, 0.38, DARK, "back")
            add_block(model, fr, s - 0.04, s + 0.04, far * (P_IN + 0.1) - 0.006,
                      far * (P_IN + 0.1) + 0.006, 0.3, 0.38, (40, 70, 150),
                      "back")
    else:
        forklift(model, fr, -0.2, far * (P_IN + 0.18), "back")
        crates(model, fr, 0.35, far * (P_IN + 0.24))
        crates(model, fr, -0.5, far * (P_IN + 0.22), n=2)
        crates(model, fr, 0.0, -far * (P_IN + 0.22), n=2,
               layer="front" if front else "back")
    return model


# --- Bake ---------------------------------------------------------------------

def bake_pakset() -> None:
    for dock in DOCKS:
        dat = WATER_DIR / f"{dock.dat}.dat"
        rewrite_images(dat, {dock.name: bake_dock(dock)})
    cells = []
    for axis in range(3):
        m = depot_model(axis)
        cells += [(f"{la}[{axis}]", lambda m=m, la=la:
                   render(m, HexCamera(), layer_filter=la))
                  for la in ("back", "front")]
    bake_atlas(out_png=WATER_DIR / "shipdepot_hex.png", entries=cells)
    dat = WATER_DIR / "shipdepot.dat"
    rewrite_images(dat, {"ShipDepot": [
        f"{key}Image[{axis}][0][0][0][0][0]=shipdepot_hex.0.{2 * axis + i}"
        for axis in range(3) for i, key in enumerate(("Back", "Front"))]})
    set_layouts(dat, 3)
    for name, stem, kind in CANAL_STOPS:
        entries = [(f"{la}[{lo}]", lambda k=kind, lo=lo, la=la:
                    render(canal_stop_model(k, lo), HexCamera(),
                           layer_filter=la))
                   for lo in range(LAYOUTS) for la in ("back", "front")]
        bake_atlas(out_png=WATER_DIR / f"{stem}_hex.png", entries=entries,
                   cols_per_row=8)
        dat = WATER_DIR / f"{stem}.dat"
        rewrite_dat(dat, stem)
        set_layouts(dat, LAYOUTS)


def preview(out: Path) -> None:
    """Each harbour in its four layouts, over water, and the depot."""
    geom = HexGeom()
    sheets = []
    for dock in DOCKS:
        for layout in range(4):
            tiles = render_tiles(dock_model(dock.kind, layout),
                                 dock_dims(layout), levels=6, ambient=AMBIENT)
            sheets.append(composite(tiles, ground_cell(geom)))
    w = sum(s.width for s in sheets[:4])
    h = max(s.height for s in sheets)
    sheet = Image.new("RGBA", (w, h * len(DOCKS)), (60, 90, 140, 255))
    for k, s in enumerate(sheets):
        x = sum(t.width for t in sheets[k - k % 4:k])
        sheet.alpha_composite(s, (x, (k // 4) * h + h - s.height))
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write the harbours side by side instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview(a.preview)
    else:
        bake_pakset()
