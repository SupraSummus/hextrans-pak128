"""3D model of the pak128 oil field for the hex grid.

`Dims=2,2` with one layout, laid out like the other factories (see
`tools.threed.building_kit`): two storage tanks on the back triangle,
beam pumps round them, a drilling derrick on the front tile, pipes
between them.

    python3 -m factories.hex_oil.scene
    python3 -m factories.hex_oil.scene --preview sheet.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, add_beam, bake_tiles, ground, preview,
    rewrite_images, side_frame)
from tools.threed.factory_kit import (
    STEEL, YELLOW, cylinder, ground_shader, lattice_tower, pumpjack)
from tools.threed.render import Model
from tools.threed.solids import add_block

FACTORIES_DIR = Path(__file__).resolve().parent.parent
DIMS = (2, 2)

GRAVEL = (118, 114, 106)
OIL = (40, 38, 36)
TANK = (70, 128, 84)
PIPE = (150, 152, 156)


def oelfeld() -> Model:
    model = Model()
    ground(model, ground_shader(GRAVEL, patches=[
        (FRAME, 0.4, 0.75, 0.15, OIL), (FRAME, FRONT_S, 0.0, 0.2, OIL),
        (FRAME, -0.6, -0.8, 0.12, OIL)]))
    # Two storage tanks, a dark band at the top and a ladder up the side.
    tanks = ((-0.75, 0.05, 0.45, 0.32), (0.2, -0.5, 0.34, 0.26))
    for s, p, r, h in tanks:
        cylinder(model, FRAME, s, p, r, 0.0, h, TANK, roof="dome", n=24,
                 dome=0.2)
        cylinder(model, FRAME, s, p, r * 1.01, h - 0.05, h, (52, 96, 64),
                 n=24)
        add_beam(model, FRAME.world(s + r * 0.7, p - r * 0.75, 0.0),
                 FRAME.world(s + r * 0.7, p - r * 0.75, h), 0.02, STEEL)
    # Pumps on the left tile and in front of the tanks.
    left = side_frame(1, 0.4)
    for s, p, tilt in ((0.75, -0.25, 0.2), (0.8, 0.3, -0.15)):
        pumpjack(model, left, s, p, tilt=tilt)
    pumpjack(model, FRAME, 0.55, 0.0, tilt=0.05)
    # Derrick on the front tile, its floor on a skid.
    add_block(model, FRAME, FRONT_S - 0.25, FRONT_S + 0.25, -0.05, 0.45,
              0.0, 0.05, (90, 84, 76))
    lattice_tower(model, FRAME, FRONT_S, 0.2, 0.2, 0.05, 1.3, YELLOW)
    # Pipes from the wells to the tanks, just above the ground.
    for a, b in (((0.78, 0.4), (-0.4, 0.2)), ((FRONT_S, 0.2), (0.4, -0.3)),
                 ((0.55, 0.0), (0.2, -0.2))):
        add_beam(model, FRAME.world(*a, 0.03), FRAME.world(*b, 0.03), 0.02,
                 PIPE)
    return model


def bake_pakset() -> None:
    dat = FACTORIES_DIR / "oelfeld.dat"
    rewrite_images(dat, {"Oelfeld": bake_tiles(
        oelfeld(), DIMS, FACTORIES_DIR / "oelfeld_hex.png")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write it on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([oelfeld()], DIMS, a.preview)
    else:
        bake_pakset()
