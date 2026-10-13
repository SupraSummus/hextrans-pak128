"""3D models of the pak128 one-tile station buildings for the hex grid.

Station extensions placed beside a stop: post offices, warehouses, the
Avila town houses, a signal box, a car park, tanks for liquids and gas,
a bulk loader and the high platform tiles.  Baked as a
`tools.threed.blocks` catalogue: boxes for most, extras for the rest.
The multi-tile ones (VictorianStation, CunnersdorfStopBlg, the large
post offices and warehouses, the container cranes) are still legacy.

    python3 -m infrastructure.station_buildings.hex_station_buildings.scene
    python3 -m infrastructure.station_buildings.hex_station_buildings.scene \
        --preview out.png
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from infrastructure.road_stops.hex_parking.scene import ERAS, car
from tools.threed.blocks import (
    WHITE, Block, Building, bake_catalogue, block, hip, preview)
from tools.threed.building_kit import (
    STOREY, Palette, add_beam, gabled_block, speckle_shader)
from tools.threed.factory_kit import crate_stack, cylinder, lorry
from tools.threed.solids import Frame, add_block, add_frustum

STATIONS_DIR = Path(__file__).resolve().parent.parent

BRICK = Palette(wall=(156, 70, 50), trim=(226, 214, 190), roof=(150, 74, 56),
                glass=(56, 66, 84))
STONE = Palette(wall=(214, 204, 176), trim=(240, 234, 216),
                roof=(64, 64, 70), glass=(56, 66, 84))
GREY = Palette(wall=(150, 150, 144), trim=(196, 194, 186),
               roof=(92, 94, 98), glass=(56, 66, 84))
CREAM = Palette(wall=(212, 190, 150), trim=(240, 232, 214),
                roof=(110, 84, 70), glass=(56, 66, 84))
MODERN = Palette(wall=(232, 232, 228), trim=(40, 80, 160),
                 roof=(170, 170, 168), glass=(120, 150, 200))
POSTAL = Palette(wall=(236, 232, 220), trim=(230, 190, 30),
                 roof=(170, 170, 168), glass=(120, 150, 200))
TIMBER = Palette(wall=(96, 66, 46), trim=(220, 210, 190), roof=(80, 60, 52),
                 glass=(150, 180, 200))
TANK_BLUE = (50, 80, 150)
CONCRETE = (176, 174, 166)
LAWN = (98, 142, 64)


def fence_ring(model, fr: Frame, s0, s1, w, color=(120, 120, 124), h=0.07):
    for a, b in (((s0, -w), (s1, -w)), ((s1, -w), (s1, w)),
                 ((s1, w), (s0, w)), ((s0, w), (s0, -w))):
        n = max(1, round(math.dist(a, b) / 0.15))
        for k in range(n + 1):
            t = k / n
            s, p = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            add_beam(model, fr.world(s, p, 0), fr.world(s, p, h), 0.012, color)
        add_beam(model, fr.world(*a, h), fr.world(*b, h), 0.008, color)


def roof_units(model, fr: Frame, b: Block, n=3):
    top = b.storeys * STOREY + 0.05
    for k in range(n):
        s = b.s0 + (k + 1) * (b.s1 - b.s0) / (n + 1)
        add_block(model, fr, s - 0.05, s + 0.05, -0.08, 0.08, top, top + 0.06,
                  (130, 132, 136))


# --- Extras -------------------------------------------------------------------

def car_park(model, fr):
    fence_ring(model, fr, -0.55, 0.5, 0.48)
    colours = ((190, 40, 40), (230, 230, 226), (60, 90, 160), (220, 200, 60),
               (80, 80, 86), (90, 130, 80))
    k = 0
    for s in (-0.35, 0.0, 0.35):
        for p in (-0.22, 0.22):
            stall = Frame(fr.v, origin=fr.world(s, p, 0)[:2])
            car(model, stall, 0, 0, ERAS[-1].car, colours[k % len(colours)],
                "back")
            k += 1


def bulk(model, fr):
    """A walled yard with a hopper on legs and a belt up to it."""
    for a, b in (((-0.55, -0.45), (0.45, -0.45)), ((-0.55, 0.45), (0.45, 0.45)),
                 ((-0.55, -0.45), (-0.55, 0.45))):
        add_beam(model, fr.world(*a, 0.05), fr.world(*b, 0.05), 0.1,
                 BRICK.wall)
    for ds in (-0.12, 0.12):
        for dp in (-0.12, 0.12):
            add_beam(model, fr.world(ds - 0.1, dp, 0), fr.world(ds - 0.1, dp,
                                                                 0.32),
                     0.03, (220, 110, 40))
    add_block(model, fr, -0.26, 0.06, -0.16, 0.16, 0.32, 0.6, (130, 150, 200),
              side_shader=speckle_shader((130, 150, 200)))
    add_frustum(model, fr, -0.1, 0.0, 0.15, 0.05, 0.2, 0.32, (130, 150, 200),
                n=4)
    add_beam(model, fr.world(0.45, 0.2, 0.05), fr.world(0.0, 0.1, 0.62), 0.04,
             (220, 180, 40))


def signal_box(model, fr):
    """Brick below, a timber cabin with wide windows above."""
    block(model, fr, Block(-0.3, 0.2, 0.2, 1, BRICK))
    z = STOREY + 0.04
    add_block(model, fr, -0.34, 0.24, -0.24, 0.24, z, z + 0.2, TIMBER.wall)
    add_block(model, fr, -0.32, 0.25, -0.2, 0.2, z + 0.05, z + 0.17,
              TIMBER.glass)
    add_block(model, fr, -0.3, 0.2, -0.25, 0.25, z + 0.05, z + 0.17,
              TIMBER.glass)
    hip(model, fr, -0.34, 0.24, 0.24, z + 0.2, 0.14, TIMBER.roof)
    for s, p in ((0.4, -0.35), (0.42, 0.35)):
        add_frustum(model, fr, s, p, 0.1, 0.0, 0.05, 0.3, (60, 110, 60), n=8)


def fluid(model, fr):
    fence_ring(model, fr, -0.6, 0.55, 0.52)
    cylinder(model, fr, -0.05, 0.0, 0.45, 0.0, 0.28, TANK_BLUE, n=24)
    add_frustum(model, fr, -0.05, 0.0, 0.46, 0.08, 0.28, 0.36,
                (64, 92, 160), n=24)
    add_block(model, fr, 0.35, 0.5, -0.45, -0.3, 0.0, 0.14, CONCRETE)


def sphere(model, fr: Frame, s, p, z, r, colour, n=16):
    """A ball, squashed so it draws round: z draws at 90 px a unit
    against 64 across."""
    steps = 8
    k_z = 64 / 90
    for k in range(steps):
        a0 = -math.pi / 2 + math.pi * k / steps
        a1 = -math.pi / 2 + math.pi * (k + 1) / steps
        add_frustum(model, fr, s, p, max(r * math.cos(a0), 1e-3),
                    max(r * math.cos(a1), 1e-3), z + r * k_z * math.sin(a0),
                    z + r * k_z * math.sin(a1), colour, n=n)


def gas(model, fr):
    fence_ring(model, fr, -0.6, 0.55, 0.52)
    for s, p in ((-0.25, -0.22), (0.15, 0.22)):
        for k in range(6):
            a = 2 * math.pi * k / 6
            add_beam(model, fr.world(s + 0.17 * math.cos(a),
                                     p + 0.17 * math.sin(a), 0),
                     fr.world(s + 0.13 * math.cos(a), p + 0.13 * math.sin(a),
                              0.22), 0.02, (90, 90, 96))
        sphere(model, fr, s, p, 0.36, 0.24, TANK_BLUE)
    add_block(model, fr, 0.25, 0.45, -0.42, -0.22, 0.0, 0.14, CONCRETE)


def goods_sheds(model, fr):
    """Two grey sheds side by side, crates in front."""
    for p in (-0.22, 0.22):
        shed = Frame(fr.u, origin=fr.world(0.0, p, 0.0)[:2])
        gabled_block(model, shed, -0.6, 0.35, 0.19, 1, GREY, pitch=0.14,
                     door=True, stepped=False, bays=3)
    crate_stack(model, fr, 0.55, 0.3)


def high_slab(model, fr):
    add_block(model, fr, -0.7, 0.7, -0.62, 0.62, 0.0, 0.05, CONCRETE)


def floodlight(model, fr):
    high_slab(model, fr)
    add_beam(model, fr.world(-0.3, -0.25, 0.05), fr.world(-0.3, -0.25, 1.0),
             0.03, (110, 112, 116))
    add_block(model, fr, -0.38, -0.22, -0.3, -0.2, 0.98, 1.06, WHITE)
    gabled_block(model, fr, 0.05, 0.45, 0.15, 1, GREY, pitch=0.1,
                 stepped=False, door=True)
    for s in (-0.55, 0.55):
        add_block(model, fr, s - 0.12, s + 0.12, 0.45, 0.47, 0.05, 0.051,
                  (220, 190, 30))


def modern_post_extras(model, fr):
    lorry(model, fr, 0.55, 0.25, cab=(230, 190, 30), box=(230, 190, 30),
          length=0.3)


BUILDINGS = [
    Building("Almuthof_StationBlg", "almuthof_stationblg", 4, [
        Block(-0.5, 0.15, 0.25, 1, BRICK, roof="gable", door=True, pitch=0.16),
        Block(0.15, 0.45, 0.18, 1, BRICK, roof="gable", pitch=0.12)]),
    Building("Avila_Big_StationBlg", "avila_big_stationblg", 1, [
        Block(-0.48, 0.4, 0.42, 4, STONE, roof="mansard", door=True,
              pitch=0.2)]),
    Building("Avila_Small_StationBlg", "avila_small_stationblg", 1, [
        Block(-0.45, 0.35, 0.4, 3, STONE, roof="mansard", door=True,
              pitch=0.2)]),
    Building("Avila_Warehouse_StationBlg", "avila_warehouse_stationblg", 1, [
        Block(-0.6, 0.45, 0.32, 1, STONE, roof="gable", door=True,
              pitch=0.16)]),
    Building("Bulk_StationBlg", "bulk_stationblg", 1, extras=bulk),
    Building("Car_StationBlg", "car_stationblg", 1, extras=car_park),
    Building("Control_StationBlg", "control_stationblg", 1, extras=signal_box,
             ground=(96, 136, 62)),
    Building("Fluid_StationBlg", "fluid_stationblg", 1, extras=fluid),
    Building("Gas_StationBlg", "gas_stationblg", 1, extras=gas),
    Building("Goods_StationBlg", "goods_stationblg", 1, extras=goods_sheds),
    Building("ModernPostOffice", "modernpostoffice", 4, [
        Block(-0.5, 0.35, 0.42, 2, POSTAL, roof="flat", bands=True,
              parapet="plain")], modern_post_extras),
    Building("Modern_Warehouse", "modern_warehouse", 4, [
        Block(-0.55, 0.4, 0.45, 2, MODERN, roof="flat", bands=True,
              parapet="plain")]),
    Building("PostOffice", "postoffice", 4, [
        Block(-0.45, 0.3, 0.36, 2, CREAM, roof="hip", door=True, pitch=0.18)]),
    Building("plain_tile_high", "plain_tile_high", 1, extras=high_slab),
    Building("ramp_tile_high", "ramp_tile_high", 4, extras=floodlight),
]


def bake_pakset() -> None:
    bake_catalogue(BUILDINGS, STATIONS_DIR)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write every building on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview(BUILDINGS, a.preview, cols=5)
    else:
        bake_pakset()
