"""3D models of the pak128 farms for the hex grid.

The corn, cotton and grain farms are `Dims=2,2`, laid out like the
other factories (see `tools.threed.building_kit`): the farmstead on
the back triangle, the yard on the front tile.  The fields are their
own objects, laid round the farm by the engine.  The corn and cotton
farms ship four layouts in pak128; on the hex rhombus all four would
be the same picture, so they bake one (`Dims=2,2`).

    python3 -m factories.hex_farms.scene
    python3 -m factories.hex_farms.scene --preview sheet.png
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, Palette, add_beam, bake_tiles,
    gabled_block, ground, preview, rewrite_images, set_layouts, side_frame)
from tools.threed.factory_kit import (
    cylinder, ground_shader, lattice_tower, legs, lorry)
from tools.threed.render import Model
from tools.threed.solids import Frame, add_block, add_frustum

FACTORIES_DIR = Path(__file__).resolve().parent.parent
DIMS = (2, 2)

YARD = (138, 124, 96)
GRASS = (100, 138, 62)
RED_BARN = Palette(wall=(168, 40, 36), trim=(236, 230, 214),
                   roof=(70, 70, 76), glass=(56, 66, 84))
GREY_BARN = Palette(wall=(140, 136, 128), trim=(206, 200, 186),
                    roof=(96, 96, 100), glass=(56, 66, 84))
FARMHOUSE = Palette(wall=(232, 226, 210), trim=(250, 248, 240),
                    roof=(96, 92, 96), glass=(56, 66, 84))
BRICK_HOUSE = Palette(wall=(168, 76, 56), trim=(232, 222, 202),
                      roof=(108, 104, 108), glass=(56, 66, 84))
SILO = (196, 198, 198)
CONIFER = (46, 98, 58)
TRUNK = (70, 44, 32)


def yard(model, *patches):
    ground(model, ground_shader(GRASS, patches=[(FRAME, *p) for p in patches]))


def conifer(model, fr: Frame, s, p, height=0.7):
    k = height / 0.75
    add_frustum(model, fr, s, p, 0.03, 0.03, 0, 0.08, TRUNK, n=6)
    for r, z0, z1 in ((0.18, 0.06, 0.45), (0.13, 0.3, 0.65), (0.09, 0.5, 0.8)):
        add_frustum(model, fr, s, p, r * k, 0.0, z0 * k, z1 * k, CONIFER,
                    n=10)


def tractor(model, fr: Frame, s, p, colour=(190, 40, 30)):
    for ds, r in ((-0.05, 0.045), (0.06, 0.03)):
        for dp in (-0.05, 0.05):
            add_block(model, fr, s + ds - r, s + ds + r, p + dp - 0.012,
                      p + dp + 0.012, 0.0, 2 * r, (40, 40, 40))
    add_block(model, fr, s - 0.06, s + 0.09, p - 0.035, p + 0.035, 0.03,
              0.08, colour)
    add_block(model, fr, s - 0.07, s - 0.01, p - 0.04, p + 0.04, 0.08, 0.15,
              (70, 86, 104))


def wind_pump(model, fr: Frame, s, p, h=0.75):
    """A lattice windmill pump: tower, a fan of blades, a tail vane."""
    lattice_tower(model, fr, s, p, 0.08, 0.025, h, (150, 150, 154))
    hub = fr.world(s + 0.03, p, h + 0.03)
    for k in range(12):
        a = 2 * math.pi * k / 12
        tip = fr.world(s + 0.03, p + 0.13 * math.cos(a),
                       h + 0.03 + 0.13 * math.sin(a))
        add_beam(model, hub, tip, 0.02, (200, 200, 196))
    add_beam(model, fr.world(s, p, h + 0.03), fr.world(s - 0.18, p, h + 0.05),
             0.012, (150, 150, 154))
    add_block(model, fr, -0.005 + s - 0.2, s - 0.15, p - 0.004, p + 0.004,
              h, h + 0.1, (200, 200, 196))


def corn_farm() -> Model:
    model = Model()
    yard(model, (0.2, 0.0, 0.7, YARD), (FRONT_S, 0.0, 0.45, YARD))
    gabled_block(model, FRAME, -1.0, 0.25, 0.36, 2, RED_BARN, pitch=0.32,
                 door=True, stepped=False, bays=4)
    silo = side_frame(-1, 0.1)
    cylinder(model, silo, 0.85, 0.0, 0.16, 0.0, 0.95, SILO, roof="dome", n=16)
    house = side_frame(1, 0.35)
    gabled_block(model, house, 0.55, 1.0, 0.2, 2, FARMHOUSE, pitch=0.2,
                 door=True, stepped=False, bays=2)
    wind_pump(model, FRAME, FRONT_S - 0.3, -0.45)
    for s, p in ((-1.2, 0.6), (-1.0, 0.85), (-0.7, 0.95)):
        conifer(model, FRAME, s, p)
    tractor(model, FRAME, FRONT_S + 0.1, 0.2)
    return model


def cotton_farm() -> Model:
    model = Model()
    yard(model, (FRONT_S - 0.3, 0.0, 0.55, YARD))
    gabled_block(model, FRAME, -1.1, 0.35, 0.42, 2, GREY_BARN, pitch=0.3,
                 door=True, stepped=False, bays=4)
    house = side_frame(1, 0.45)
    gabled_block(model, house, 0.5, 1.0, 0.2, 1, BRICK_HOUSE, pitch=0.18,
                 door=True, stepped=False, bays=2)
    # Cotton bales by the barn door.
    for k, q in enumerate((-0.3, -0.12, 0.06)):
        add_block(model, FRAME, FRONT_S - 0.55, FRONT_S - 0.35, q - 0.07,
                  q + 0.07, 0.0, 0.12, (240, 238, 228))
    tractor(model, FRAME, FRONT_S + 0.1, 0.25)
    lorry(model, FRAME, FRONT_S + 0.2, -0.3, cab=(60, 90, 150),
          box=(240, 238, 228), length=0.32)
    return model


def grain_farm() -> Model:
    model = Model()
    yard(model, (0.0, 0.0, 1.1, YARD), (FRONT_S, 0.0, 0.6, YARD))
    gabled_block(model, FRAME, -1.1, -0.3, 0.32, 2, FARMHOUSE, pitch=0.28,
                 door=True, stepped=False, bays=3)
    shed = side_frame(-1, -0.1)
    gabled_block(model, shed, 0.45, 1.15, 0.24, 1, GREY_BARN, pitch=0.18,
                 door=True, stepped=False, bays=3)
    shed2 = side_frame(1, 0.6)
    gabled_block(model, shed2, 0.45, 1.05, 0.22, 1, GREY_BARN, pitch=0.16,
                 stepped=False, bays=3)
    for s, p, h in ((0.15, -0.55, 0.85), (0.15, 0.55, 0.75),
                    (FRONT_S - 0.35, -0.5, 0.65)):
        cylinder(model, FRAME, s, p, 0.15, 0.0, h, SILO, roof="cone", n=16)
    legs(model, FRAME, FRONT_S + 0.2, 0.3, 0.1, 0.25)
    cylinder(model, FRAME, FRONT_S + 0.2, 0.3, 0.12, 0.25, 0.5, SILO,
             roof="cone", n=14)
    tractor(model, FRAME, FRONT_S + 0.25, -0.15, colour=(40, 120, 60))
    return model


FARMS = {
    "Corn_Farm": ("corn_farm", corn_farm),
    "cotton_farm_w_fields": ("cotton_farm_w_fields", cotton_farm),
    "grain_farm_w_fields": ("grain_farm_w_fields", grain_farm),
}


def bake_pakset() -> None:
    for name, (stem, build) in FARMS.items():
        dat = FACTORIES_DIR / f"{stem}.dat"
        rewrite_images(dat, {name: bake_tiles(
            build(), DIMS, FACTORIES_DIR / f"{stem}_hex.png")})
        set_layouts(dat, 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write them all on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build() for _, build in FARMS.values()], DIMS, a.preview)
    else:
        bake_pakset()
