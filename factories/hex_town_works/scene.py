"""3D models of pak128 town works for the hex grid.

The car dealer, the publisher, the food processing plant, the dairy and
the concrete works are `Dims=2,2` with one layout, laid out like the
other factories (see `tools.threed.building_kit`): the works on the
back triangle, a yard or car park on the front tile.

    python3 -m factories.hex_town_works.scene
    python3 -m factories.hex_town_works.scene --preview sheet.png
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from infrastructure.road_stops.hex_parking.scene import ERAS, car
from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, STOREY, Palette, add_beam, bake_tiles,
    facade, ground, preview, rewrite_images, side_frame, speckle_shader,
    vault, wall_quad)
from tools.threed.factory_kit import (
    YELLOW, conveyor, cylinder, ground_shader, legs, lorry, windows_band)
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import Model
from tools.threed.solids import (
    Frame, add_block, add_face, add_frustum, add_roof)

FACTORIES_DIR = Path(__file__).resolve().parent.parent
DIMS = (2, 2)

ASPHALT = (84, 84, 88)
PAVING = (168, 164, 156)
GRAVEL = (150, 144, 132)
SAND = (206, 186, 140)
BRICK = Palette(wall=(150, 78, 60), trim=(214, 204, 186), roof=(110, 104, 104),
                glass=(56, 66, 84))
DARK_BRICK = Palette(wall=(118, 70, 62), trim=(200, 190, 176),
                     roof=(120, 116, 116), glass=(60, 70, 110))
WHITE_HALL = Palette(wall=(236, 236, 232), trim=(214, 214, 210),
                     roof=(150, 150, 150), glass=(80, 100, 170))
SHOWROOM = Palette(wall=(220, 200, 150), trim=(200, 40, 120),
                   roof=(110, 110, 114), glass=(150, 190, 220))
CONCRETE = (186, 184, 176)
CARS = ((190, 40, 40), (230, 230, 226), (60, 90, 160), (220, 200, 60),
        (80, 80, 86), (90, 130, 80))


def car_lot_shader(base):
    """Asphalt with white bay lines along the frame."""
    base = np.array(base, float)

    def shader(wx, wy, sx, sy):
        s, p = FRAME.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (0.92 + 0.14 * n)[:, None]
        lot = (s > FRONT_S - 0.7)
        lines = lot & (np.abs((p / 0.2) % 1.0 - 0.5) > 0.46)
        rgb[lines] = (226, 226, 220)
        return rgb, np.ones(len(wx), bool)

    return shader


def flat_block(model, fr, s0, s1, w, storeys, pal, *, bays=4, door=True):
    top = storeys * STOREY + 0.04
    add_block(model, fr, s0, s1, -w, w, 0.0, top, pal.wall,
              side_shader=speckle_shader(pal.wall))
    add_block(model, fr, s0 - 0.02, s1 + 0.02, -w - 0.02, w + 0.02, top,
              top + 0.04, pal.trim)
    add_block(model, fr, s0 + 0.02, s1 - 0.02, -w + 0.02, w - 0.02, top + 0.01,
              top + 0.03, pal.roof)
    for k, (a, b, inward) in enumerate((((s1, -w), (s1, w), (-1, 0)),
                                        ((s0, -w), (s1, -w), (0, 1)),
                                        ((s1, w), (s0, w), (0, -1)))):
        facade(model, fr, a, b, inward, pal, storeys=storeys,
               bays=max(2, round(math.dist(a, b) / 0.22)),
               door=door and k == 0)
    return top


# --- Car dealer ---------------------------------------------------------------

def autoshop3() -> Model:
    model = Model()
    ground(model, car_lot_shader(ASPHALT))
    s0, s1, w = -1.0, 0.45, 0.62
    top = STOREY * 1.4
    add_block(model, FRAME, s0, s1, -w, w, 0.0, top, SHOWROOM.wall,
              side_shader=speckle_shader(SHOWROOM.wall))
    add_block(model, FRAME, s0 - 0.02, s1 + 0.02, -w - 0.02, w + 0.02, top,
              top + 0.03, SHOWROOM.roof)
    # Glass showroom front, a coloured band above it.
    wall_quad(model, FRAME, (s1, -w + 0.05), (s1, w - 0.05), 0.02, top - 0.07,
              0.008, SHOWROOM.glass, (-1, 0))
    wall_quad(model, FRAME, (s1, -w), (s1, w), top - 0.06, top, 0.01,
              SHOWROOM.trim, (-1, 0))
    windows_band(model, FRAME, (s0, -w), (s1, -w), (0, 1), 0.1, top - 0.1, 5,
                 SHOWROOM.glass)
    # Sign board on the roof.
    for q in (-0.25, 0.25):
        add_block(model, FRAME, s1 - 0.12, s1 - 0.1, q - 0.01, q + 0.01, top,
                  top + 0.12, (70, 70, 74))
    add_block(model, FRAME, s1 - 0.13, s1 - 0.1, -0.35, 0.35, top + 0.1,
              top + 0.24, (240, 240, 236))
    add_block(model, FRAME, s1 - 0.1, s1 - 0.095, -0.3, 0.3, top + 0.13,
              top + 0.21, SHOWROOM.trim)
    k = 0
    for s in (FRONT_S - 0.4, FRONT_S, FRONT_S + 0.4):
        for p in (-0.3, -0.1, 0.1, 0.3):
            if (s, p) == (FRONT_S + 0.4, 0.3):
                continue
            car(model, FRAME, s, p, ERAS[-1].car, CARS[k % len(CARS)], "back")
            k += 1
    return model


# --- Publisher ----------------------------------------------------------------

def publisher() -> Model:
    model = Model()
    ground(model, ground_shader(PAVING))
    s0, s1, w = -0.95, -0.1, 0.42
    top = flat_block(model, FRAME, s0, s1, w, 9, BRICK, bays=4)
    # Stair tower and plant on the roof, a pipe down the side.
    add_block(model, FRAME, s0 + 0.1, s0 + 0.35, -0.15, 0.15, top, top + 0.16,
              BRICK.wall, side_shader=speckle_shader(BRICK.wall))
    add_block(model, FRAME, s1 - 0.3, s1 - 0.05, 0.05, 0.3, top, top + 0.06,
              (140, 142, 146))
    add_beam(model, FRAME.world(s0 + 0.05, -w - 0.03, 0.0),
             FRAME.world(s0 + 0.05, -w - 0.03, top), 0.04, (200, 200, 204))
    # A low hall reaching into the front tile, lorries in the yard.
    flat_block(model, FRAME, -0.1, 0.8, 0.5, 1, BRICK, bays=3)
    for p in (-0.35, 0.0):
        lorry(model, FRAME, FRONT_S + 0.1, p, cab=(230, 190, 40),
              box=(236, 234, 226))
    return model


# --- Food processing ----------------------------------------------------------

def food_processing_plant() -> Model:
    model = Model()
    ground(model, ground_shader(GRAVEL))
    top = flat_block(model, FRAME, -1.15, 0.45, 0.48, 4, DARK_BRICK, bays=5)
    for s in (-0.9, -0.5, -0.1, 0.25):
        add_block(model, FRAME, s - 0.06, s + 0.06, -0.2, -0.08, top,
                  top + 0.07, (150, 152, 156))
    add_beam(model, FRAME.world(-0.6, 0.3, top), FRAME.world(-0.6, 0.3,
                                                              top + 0.5),
             0.02, (210, 50, 40))
    cylinder(model, FRAME, -0.3, 0.25, 0.08, top, top + 0.16, (210, 210, 206))
    for p in (-0.3, 0.05):
        lorry(model, FRAME, FRONT_S, p, cab=(70, 70, 76), box=(236, 236, 232),
              length=0.42)
    return model


# --- Dairy --------------------------------------------------------------------

def barrel_roof(model, fr: Frame, s0, s1, w, z, rise, colour, n=10):
    prof = vault(w, z, rise, n)
    for (p0, z0), (p1, z1) in zip(prof, prof[1:]):
        add_roof(model, fr, s0 - 0.03, s1 + 0.03, p0, p1, z0, z1, 0.02, colour,
                 shader=speckle_shader(colour))
    inside = fr.world((s0 + s1) / 2, 0, z)
    for s in (s0, s1):
        for (p0, z0), (p1, z1) in zip(prof, prof[1:]):
            add_face(model, [fr.world(s, p0, z), fr.world(s, p1, z),
                             fr.world(s, p1, z1), fr.world(s, p0, z0)],
                     WHITE_HALL.wall, outward=inside)


def dairy() -> Model:
    model = Model()
    ground(model, ground_shader(PAVING))
    s0, s1, w = -1.15, 0.45, 0.5
    eave = STOREY * 1.3
    add_block(model, FRAME, s0, s1, -w, w, 0.0, eave, WHITE_HALL.wall,
              side_shader=speckle_shader(WHITE_HALL.wall))
    barrel_roof(model, FRAME, s0, s1, w, eave, 0.28, WHITE_HALL.roof)
    for side in (-1, 1):
        windows_band(model, FRAME, (s0, side * w), (s1, side * w), (0, -side),
                     0.08, eave - 0.06, 6, WHITE_HALL.glass)
    wall_quad(model, FRAME, (s1, -0.2), (s1, 0.2), 0.0, 0.2, 0.01,
              (60, 60, 64), (-1, 0))
    for s in (-0.8, -0.4, 0.0):
        add_block(model, FRAME, s - 0.04, s + 0.04, -0.04, 0.04, eave + 0.26,
                  eave + 0.31, (70, 140, 170))
    # Milk tanks and a loading dock on the front tile.
    tanks = side_frame(-1, 0.6)
    for q in (-0.12, 0.12):
        cylinder(model, tanks, 0.8, q, 0.1, 0.0, 0.5, (236, 238, 240),
                 roof="dome", n=16)
    add_block(model, FRAME, FRONT_S - 0.55, FRONT_S - 0.3, -0.35, 0.35, 0.0,
              0.08, CONCRETE)
    lorry(model, FRAME, FRONT_S + 0.1, 0.0, cab=(40, 80, 160),
          box=(236, 236, 236))
    return model


# --- Concrete works -----------------------------------------------------------

def concretefactory() -> Model:
    model = Model()
    ground(model, ground_shader(GRAVEL, patches=[(FRAME, FRONT_S, 0.0, 0.55,
                                                  SAND)]))
    # Mixing tower: a tall block with a hopper top.
    add_block(model, FRAME, -0.75, -0.25, -0.25, 0.25, 0.0, 1.05, CONCRETE,
              side_shader=speckle_shader(CONCRETE))
    add_block(model, FRAME, -0.7, -0.3, -0.2, 0.2, 1.05, 1.25, (150, 150, 154))
    for k in range(4):
        z = 0.2 + k * 0.22
        add_block(model, FRAME, -0.25, -0.24, -0.15, 0.15, z, z + 0.1,
                  (56, 66, 84))
    # Cement silos on the left tile, a water tank on legs on the right.
    silos = side_frame(1, -0.1)
    for q in (-0.2, 0.2):
        legs(model, silos, 0.8, q, 0.12, 0.25)
        cylinder(model, silos, 0.8, q, 0.16, 0.25, 0.95, (200, 200, 196),
                 roof="cone", n=16)
    water = side_frame(-1, -0.3)
    legs(model, water, 0.8, 0.0, 0.1, 0.6)
    cylinder(model, water, 0.8, 0.0, 0.14, 0.6, 0.82, (150, 150, 140),
             roof="cone")
    # Sand heap and a belt to the tower; a yellow digger.
    for r, z0, z1 in ((0.38, 0.0, 0.12), (0.26, 0.1, 0.22), (0.14, 0.2, 0.28)):
        add_frustum(model, FRAME, FRONT_S, 0.05, r, r * 0.75, z0, z1, SAND,
                    n=14, top_shader=speckle_shader(SAND),
                    side_shader=speckle_shader(SAND))
    conveyor(model, FRAME.world(FRONT_S - 0.3, 0.05, 0.15),
             FRAME.world(-0.3, 0.05, 0.95))
    add_block(model, FRAME, FRONT_S + 0.2, FRONT_S + 0.4, -0.45, -0.3, 0.03,
              0.12, YELLOW)
    add_beam(model, FRAME.world(FRONT_S + 0.25, -0.38, 0.12),
             FRAME.world(FRONT_S + 0.05, -0.38, 0.3), 0.025, YELLOW)
    add_beam(model, FRAME.world(FRONT_S + 0.05, -0.38, 0.3),
             FRAME.world(FRONT_S - 0.05, -0.38, 0.1), 0.02, YELLOW)
    lorry(model, FRAME, FRONT_S + 0.3, 0.45, cab=(200, 60, 40),
          box=(170, 170, 166))
    return model


FACTORIES = {
    "autoshop3": ("autoshop3", autoshop3),
    "publisher": ("publisher", publisher),
    "food_processing_plant": ("food_processing_plant", food_processing_plant),
    "dairy": ("dairy", dairy),
    "Concretefactory": ("concretefactory", concretefactory),
}


def bake_pakset() -> None:
    for name, (stem, build) in FACTORIES.items():
        rewrite_images(FACTORIES_DIR / f"{stem}.dat", {name: bake_tiles(
            build(), DIMS, FACTORIES_DIR / f"{stem}_hex.png")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write them all on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build() for _, build in FACTORIES.values()], DIMS, a.preview)
    else:
        bake_pakset()
