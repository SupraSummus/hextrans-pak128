"""3D models of the pak128 wood and paper chain for the hex grid.

The sawmill, the furniture factory, the paper mill and the printing
works are all `Dims=2,2` with one layout, laid out like the mines
(see `tools.threed.building_kit`): the works on the back triangle,
stock on the front tile.  `FACTORIES` maps each to its `.dat` and
its `build` function; the parts come from `tools.threed.factory_kit`.

    python3 -m factories.hex_wood.scene
    python3 -m factories.hex_wood.scene --preview sheet.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, STOREY, Palette, bake_tiles, facade,
    footprint_outline, gabled_block, ground, preview, rewrite_images,
    side_frame, speckle_shader, wall_quad)
from tools.threed.factory_kit import (
    STEEL, chimney, crate_stack, cylinder, fence, gantry, ground_shader, legs,
    log, log_pile, lorry, open_shed, plank_stack, sawtooth_roof,
    windows_band)
from tools.threed.render import Model
from tools.threed.solids import add_block

FACTORIES_DIR = Path(__file__).resolve().parent.parent
DIMS = (2, 2)

DIRT = (146, 128, 100)
SAWDUST = (206, 178, 124)
GRAVEL = (150, 146, 138)
PAVING = (164, 160, 152)
FENCE = (110, 84, 60)
TIMBER_HALL = Palette(wall=(132, 74, 50), trim=(96, 70, 52),
                      roof=(84, 78, 80))
BRICK_HOUSE = Palette(wall=(150, 72, 52), trim=(214, 204, 184),
                      roof=(92, 94, 104))
YELLOW_BRICK = Palette(wall=(200, 168, 104), trim=(232, 222, 196),
                       roof=(100, 96, 104), glass=(60, 72, 96))
PLASTER = Palette(wall=(222, 206, 168), trim=(244, 236, 214),
                  roof=(122, 70, 52))
DARK_ROOF = Palette(wall=(168, 120, 84), trim=(220, 210, 190),
                    roof=(52, 52, 58))
GLASS = (150, 180, 200)
COPPER = (196, 120, 76)
PAPER = (236, 234, 226)


def yard(model, base, *patches):
    ground(model, ground_shader(base, patches=[(FRAME, *p)
                                               for p in patches]))


# --- Sawmill ------------------------------------------------------------------

def saegewerk() -> Model:
    model = Model()
    yard(model, DIRT, (0.0, 0.0, 0.5, SAWDUST), (FRONT_S, 0.1, 0.4, SAWDUST))
    fence(model, footprint_outline(DIMS, 0.06), FENCE)
    # Open saw shed along the frame, the saw line under it.
    open_shed(model, FRAME, -1.05, 0.45, 0.3, 0.3, TIMBER_HALL, posts=5)
    add_block(model, FRAME, -1.0, 0.4, -0.05, 0.05, 0.0, 0.06, (80, 70, 64))
    log(model, FRAME, -0.3, 0.0, 0.1, 0.5, 0.04)
    # Engine house with its stack on the left tile.
    house = side_frame(1, 0.1)
    gabled_block(model, house, 0.5, 1.0, 0.22, 1, BRICK_HOUSE, pitch=0.18,
                 door=True, stepped=False, bays=2)
    chimney(model, house, 0.8, 0.12, 0.75, r0=0.05, r1=0.035)
    # Logs waiting on the right tile, planks on the front one.
    right = side_frame(-1, 0.3)
    for k, q in enumerate((-0.25, 0.05, 0.35)):
        log_pile(model, right, 0.75, q, 0.55, rows=3, seed=k)
    for q in (-0.35, 0.0, 0.35):
        plank_stack(model, FRAME, FRONT_S + 0.1, q, 0.5, 0.22, 0.16)
    return model


# --- Furniture factory --------------------------------------------------------

def moebelfabrik() -> Model:
    model = Model()
    yard(model, GRAVEL, (FRONT_S, 0.0, 0.55, PAVING))
    # Workshop under a north-light roof.
    s0, s1, w = -1.15, 0.55, 0.62
    eave = STOREY * 1.2
    add_block(model, FRAME, s0, s1, -w, w, 0.0, eave, YELLOW_BRICK.wall,
              side_shader=speckle_shader(YELLOW_BRICK.wall))
    sawtooth_roof(model, FRAME, s0, s1, -w, w, eave, YELLOW_BRICK, teeth=5,
                  glass=GLASS)
    for side in (-1, 1):
        windows_band(model, FRAME, (s0, side * w), (s1, side * w), (0, -side),
                     eave * 0.35, eave * 0.85, 6, YELLOW_BRICK.glass)
    facade(model, FRAME, (s1, -w), (s1, w), (-1, 0), YELLOW_BRICK,
           storeys=1, bays=4, door=True)
    # Office at the back, two storeys under a tiled roof.
    office = side_frame(1, -0.6)
    gabled_block(model, office, 0.62, 1.12, 0.22, 2, PLASTER, pitch=0.2,
                 stepped=False, bays=2)
    # Varnish tanks and timber on the front tile.
    for q in (-0.28, 0.0):
        cylinder(model, FRAME, FRONT_S - 0.2, q - 0.15, 0.1, 0.0, 0.26,
                 COPPER, roof="dome")
    plank_stack(model, FRAME, FRONT_S + 0.3, -0.25, 0.4, 0.2, 0.14)
    plank_stack(model, FRAME, FRONT_S + 0.25, 0.25, 0.4, 0.2, 0.2)
    crate_stack(model, FRAME, FRONT_S - 0.15, 0.4)
    lorry(model, FRAME, FRONT_S + 0.35, -0.3, cab=(60, 110, 60),
          box=(160, 120, 80))
    return model


# --- Paper mill ---------------------------------------------------------------

def papierfabrik() -> Model:
    model = Model()
    yard(model, GRAVEL, (FRONT_S, 0.0, 0.6, DIRT))
    # Mill hall along the frame, three storeys.
    gabled_block(model, FRAME, -1.2, 0.35, 0.34, 3, BRICK_HOUSE, pitch=0.3,
                 stepped=False, bays=5)
    # Lower machine hall across it on the right tile.
    hall = side_frame(-1, 0.2)
    gabled_block(model, hall, 0.38, 1.15, 0.28, 1, BRICK_HOUSE, pitch=0.2,
                 door=True, stepped=False, bays=3)
    # Chip silo on legs on the left tile.
    silo = side_frame(1, 0.35)
    legs(model, silo, 0.75, 0.0, 0.13, 0.3)
    cylinder(model, silo, 0.75, 0.0, 0.18, 0.3, 0.9, (200, 196, 186),
             roof="cone")
    # Log yard under a gantry crane.
    gantry(model, FRAME, FRONT_S - 0.45, FRONT_S + 0.45, 0.42, 0.5)
    for k, q in enumerate((-0.22, 0.12)):
        log_pile(model, FRAME, FRONT_S, q, 0.7, rows=4, r=0.04, seed=k + 3)
    return model


# --- Printing works -----------------------------------------------------------

def druckerei() -> Model:
    model = Model()
    yard(model, PAVING)
    # Press hall: low, long, flat dark roof with vents.
    s0, s1, w = -1.2, 0.6, 0.55
    eave = STOREY * 1.3
    add_block(model, FRAME, s0, s1, -w, w, 0.0, eave, DARK_ROOF.wall,
              side_shader=speckle_shader(DARK_ROOF.wall))
    add_block(model, FRAME, s0 - 0.02, s1 + 0.02, -w - 0.02, w + 0.02,
              eave, eave + 0.03, DARK_ROOF.roof)
    for side in (-1, 1):
        windows_band(model, FRAME, (s0, side * w), (s1, side * w), (0, -side),
                     eave * 0.35, eave * 0.8, 7, (60, 72, 96))
    for s in (-0.9, -0.5, -0.1, 0.3):
        for q in (-0.3, 0.3):
            add_block(model, FRAME, s - 0.06, s + 0.06, q - 0.06, q + 0.06,
                      eave + 0.03, eave + 0.08, STEEL)
    # Office block on the front of the hall, gabled, two storeys.
    office = side_frame(1, 0.35)
    gabled_block(model, office, -0.3, 0.3, 0.25, 2, PLASTER, pitch=0.2,
                 door=True, stepped=False, bays=3)
    for s in (-0.95, -0.75):
        chimney(model, FRAME, s, -0.4, 0.75, r0=0.035, r1=0.03, color=STEEL)
    wall_quad(model, FRAME, (s1, -0.2), (s1, 0.2), 0.0, 0.2, 0.01,
              (70, 66, 64), (-1, 0))
    # Paper rolls on end and a lorry on the front tile.
    for k, (ds, q) in enumerate(((-0.25, -0.35), (-0.25, -0.2), (-0.1, -0.35),
                                 (-0.1, -0.2), (0.05, -0.35))):
        cylinder(model, FRAME, FRONT_S + ds, q, 0.06, 0.0,
                 0.13 if k % 2 else 0.1, PAPER, n=12)
    lorry(model, FRAME, FRONT_S + 0.05, 0.25, cab=(40, 70, 140))
    return model


FACTORIES = {
    "Saegewerk": ("saegewerk", saegewerk),
    "Moebelfabrik": ("moebelfabrik", moebelfabrik),
    "Papierfabrik": ("papierfabrik", papierfabrik),
    "Druckerei": ("druckerei", druckerei),
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
        preview([build() for _, build in FACTORIES.values()], DIMS,
                a.preview)
    else:
        bake_pakset()
