"""3D models of pak128's cement mill, glass works and textile mill for
the hex grid.

All three are `Dims=2,2` with one layout, laid out like the mines (see
`tools.threed.building_kit`): the works on the back triangle, stock
on the front tile.  Each build returns its model and the mouth of the
chimney its smoke leaves from; the bake writes the matching
`SmokeTile` / `SmokeOffset` (`factory_kit.smoke_lines`).

    python3 -m factories.hex_industry.scene
    python3 -m factories.hex_industry.scene --preview sheet.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, STOREY, Palette, bake_tiles, facade,
    gabled_block, ground, preview, rewrite_images, side_frame,
    speckle_shader)
from tools.threed.factory_kit import (
    YELLOW, chimney, conveyor, cylinder, ground_shader, heap, legs, lorry,
    open_shed, set_smoke, smoke_lines)
from tools.threed.render import Model
from tools.threed.solids import add_block

FACTORIES_DIR = Path(__file__).resolve().parent.parent
DIMS = (2, 2)

DUST = (176, 172, 160)
LIMESTONE = (214, 204, 176)
GRAVEL = (140, 136, 128)
SAND = (222, 196, 140)
COAL = (52, 52, 58)
CONCRETE = Palette(wall=(196, 194, 186), trim=(160, 158, 152),
                   roof=(132, 134, 138), glass=(60, 72, 96))
SILO = (206, 206, 200)
RED_BRICK = Palette(wall=(150, 70, 50), trim=(206, 196, 176),
                    roof=(112, 128, 120), glass=(56, 66, 84))
MILL_BRICK = Palette(wall=(138, 74, 58), trim=(196, 186, 168),
                     roof=(92, 54, 46), glass=(50, 60, 80))


def yard(model, base, *patches):
    ground(model, ground_shader(base, patches=[(FRAME, *p)
                                               for p in patches]))


# --- Cement mill --------------------------------------------------------------

def cementmill():
    model = Model()
    yard(model, DUST, (FRONT_S, -0.1, 0.5, LIMESTONE))
    # Kiln house: a tall concrete block, a lower one in front of it.
    add_block(model, FRAME, -1.15, -0.45, -0.3, 0.3, 0.0, 0.85, CONCRETE.wall,
              side_shader=speckle_shader(CONCRETE.wall))
    add_block(model, FRAME, -1.18, -0.42, -0.33, 0.33, 0.85, 0.9,
              CONCRETE.roof)
    gabled_block(model, FRAME, -0.45, 0.25, 0.3, 2, CONCRETE, pitch=0.12,
                 stepped=False, bays=3)
    # Two silos on a yellow frame on the left tile.
    silos = side_frame(1, 0.2)
    for q in (-0.2, 0.2):
        legs(model, silos, 0.75, q, 0.14, 0.32, color=YELLOW)
        cylinder(model, silos, 0.75, q, 0.17, 0.32, 1.0, SILO, roof="cone")
    # Raw stone heap on the front tile, belted up to the kiln house.
    heap(model, FRAME, FRONT_S - 0.05, -0.1, 0.42, 0.3, LIMESTONE)
    conveyor(model, FRAME.world(FRONT_S - 0.3, -0.1, 0.2),
             FRAME.world(-0.5, -0.1, 0.8))
    lorry(model, FRAME, FRONT_S + 0.2, 0.4, cab=(210, 150, 30),
          box=(150, 150, 146))
    mouth = chimney(model, FRAME, -0.85, 0.42, 1.55, r0=0.08, r1=0.055,
                    color=CONCRETE.wall)
    return model, mouth


# --- Glass works --------------------------------------------------------------

def glass_factory():
    model = Model()
    yard(model, GRAVEL, (FRONT_S - 0.1, -0.25, 0.3, SAND),
         (FRONT_S + 0.1, 0.3, 0.25, COAL))
    # Furnace hall: three storeys of brick along the frame.
    gabled_block(model, FRAME, -1.2, 0.4, 0.36, 3, RED_BRICK, pitch=0.24,
                 door=True, stepped=False, bays=5)
    # Low batch shed across it on the right tile.
    shed = side_frame(-1, -0.1)
    open_shed(model, shed, 0.45, 1.1, 0.25, 0.24, RED_BRICK, posts=4)
    heap(model, shed, 0.8, 0.0, 0.2, 0.14, SAND)
    heap(model, FRAME, FRONT_S - 0.1, -0.25, 0.3, 0.2, SAND)
    heap(model, FRAME, FRONT_S + 0.1, 0.3, 0.24, 0.16, COAL)
    chimney(model, FRAME, -0.15, 0.62, 1.5, r0=0.08, r1=0.055)
    mouth = chimney(model, FRAME, 0.25, 0.62, 1.7, r0=0.085, r1=0.06)
    return model, mouth


# --- Textile mill -------------------------------------------------------------

def textile_factory():
    model = Model()
    yard(model, GRAVEL)
    # Mill: five storeys, flat roof behind a parapet, windows all round.
    s0, s1, w = -1.15, 0.45, 0.45
    storeys = 5
    top = storeys * STOREY
    add_block(model, FRAME, s0, s1, -w, w, 0.0, top, MILL_BRICK.wall,
              side_shader=speckle_shader(MILL_BRICK.wall))
    add_block(model, FRAME, s0 - 0.02, s1 + 0.02, -w - 0.02, w + 0.02,
              top, top + 0.04, MILL_BRICK.trim)
    add_block(model, FRAME, s0 + 0.03, s1 - 0.03, -w + 0.03, w - 0.03,
              top + 0.01, top + 0.03, MILL_BRICK.roof)
    for side in (-1, 1):
        facade(model, FRAME, (s0, side * w), (s1, side * w), (0, -side),
               MILL_BRICK, storeys=storeys, bays=6)
    facade(model, FRAME, (s1, -w), (s1, w), (-1, 0), MILL_BRICK,
           storeys=storeys, bays=3, door=True)
    # Skylight huts on the roof.
    for s in (-0.8, -0.3, 0.15):
        add_block(model, FRAME, s - 0.1, s + 0.1, -0.12, 0.12, top + 0.03,
                  top + 0.11, MILL_BRICK.roof)
        add_block(model, FRAME, s - 0.08, s + 0.08, -0.13, -0.12, top + 0.05,
                  top + 0.1, (150, 180, 200))
    # Boiler house and its stacks on the left tile.
    boiler = side_frame(1, -0.2)
    gabled_block(model, boiler, 0.5, 1.05, 0.22, 1, MILL_BRICK, pitch=0.16,
                 stepped=False, bays=2)
    chimney(model, boiler, 0.85, -0.3, 1.45, r0=0.07, r1=0.05)
    mouth = chimney(model, boiler, 0.9, 0.15, 1.75, r0=0.08, r1=0.055)
    lorry(model, FRAME, FRONT_S, 0.1, cab=(130, 40, 40), box=(196, 190, 170))
    return model, mouth


FACTORIES = {
    "Cementmill": ("cementmill", cementmill),
    "Glass_factory": ("glass_factory", glass_factory),
    "textile_factory": ("textile_factory", textile_factory),
}


def bake_pakset() -> None:
    for name, (stem, build) in FACTORIES.items():
        model, mouth = build()
        dat = FACTORIES_DIR / f"{stem}.dat"
        rewrite_images(dat, {name: bake_tiles(
            model, DIMS, FACTORIES_DIR / f"{stem}_hex.png")})
        set_smoke(dat, smoke_lines(mouth, DIMS))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write them all on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build()[0] for _, build in FACTORIES.values()], DIMS,
                a.preview)
    else:
        bake_pakset()
