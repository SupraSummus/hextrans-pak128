"""3D models of the pak128 red-brick townhalls for the hex grid.

The townhalls are `Dims=2,2`: on hex the 4-tile rhombus `(0,0),
(1,0), (0,1), (1,1)`.  Its back three tiles form a triangle around
one shared vertex; the hall stands on that triangle, centred on the
vertex and facing the front tile, which holds the forecourt with the
fountain, as pak128's forecourt does.  The building never relies on
the fourth tile, so it carries over when the engine learns 3-tile
footprints.

`TOWNHALLS` lists the five sizes as `TownhallParams`; one scene builds
them all.  `tools.threed.building` slices the model into the per-tile,
per-height images.

    python3 -m special_buildings.townhalls.hex_townhalls.scene
    python3 -m special_buildings.townhalls.hex_townhalls.scene \
        --preview sheet.png     # all five on grass, nothing written
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, STOREY, Palette, bake_tiles, facade,
    gabled_block, ground, outside_distance, preview, rewrite_images,
    side_frame, speckle_shader, wall_quad)
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import Model
from tools.threed.solids import add_block, add_frustum

TOWNHALLS_DIR = Path(__file__).resolve().parent.parent
DAT = TOWNHALLS_DIR / "city-townhalls-128.dat"
DIMS = (2, 2)

BRICK = (236, 92, 66)
TRIM = (246, 232, 196)
RED_BRICK = Palette(wall=BRICK, trim=TRIM, roof=(150, 152, 160))
SETTS = (176, 170, 156)
LAWN = (98, 142, 64)
KERB = (206, 202, 190)
STONE = (196, 192, 182)
WATER = (96, 148, 196)
CONIFER = (46, 98, 58)
TRUNK = (70, 44, 32)
COPPER = (88, 160, 120)


@dataclass(frozen=True)
class TownhallParams:
    name: str
    storeys: int = 2
    length: float = 1.6         # hall along `s`
    width: float = 1.0          # hall across `p`
    tower: float = 0.0          # tower height above the eaves, 0 for none
    wings: int = 0              # storeys of the side wings, 0 for none


TOWNHALLS = [
    TownhallParams("01_CITY"),
    TownhallParams("02_CITY", storeys=3, length=1.7, width=1.05),
    TownhallParams("03_CITY", storeys=3, length=1.8, width=1.1, tower=0.75),
    TownhallParams("04_CITY", storeys=3, length=1.8, width=1.1, tower=0.75,
                   wings=2),
    TownhallParams("05_CITY", storeys=3, length=2.3, width=1.1, tower=0.95,
                   wings=3),
]

# Side wings: centred at `WING_S` along the hall, reaching `WING_REACH`
# out from its axis into the side tiles of the triangle.
WING_S, WING_REACH, WING_HALF = 0.15, 1.3, 0.36


# --- Ground ---------------------------------------------------------------

def ground_shader(hall: TownhallParams):
    setts, lawn, kerb = (np.array(c, float) for c in (SETTS, LAWN, KERB))
    s_front = hall.length / 2

    def shader(wx, wy, sx, sy):
        s, p = FRAME.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        edge = outside_distance(DIMS, wx, wy)
        fountain = np.hypot(s - FRONT_S, p)
        # Lawn beds: either side of the path to the door and around
        # the fountain, inside a paved border.
        bed = (edge > 0.16) & (np.abs(p) > 0.17) & (fountain > 0.4)
        bed &= (s > s_front + 0.25) | (np.abs(p) > hall.width / 2 + 0.16)
        rgb = np.empty((len(wx), 3))
        rgb[:] = setts * np.where(n < 0.25, 0.86, np.where(n < 0.9, 1.0,
                                                          1.08))[:, None]
        rgb[bed] = lawn * (0.9 + 0.2 * n[bed])[:, None]
        border = ~bed & (edge > 0.16) & (np.abs(p) > 0.15) & (fountain > 0.38)
        border &= (s > s_front + 0.23) | (np.abs(p) > hall.width / 2 + 0.14)
        rgb[border & ~bed] = kerb
        rgb[edge < 0.035] = kerb
        return rgb, np.ones(len(wx), bool)

    return shader


# --- Parts ---------------------------------------------------------------

def chimneys(model, fr, z_ridge, s_list):
    for k, s in enumerate(s_list):
        p = 0.2 if k % 2 else -0.2
        add_block(model, fr, s - 0.05, s + 0.05, p - 0.04, p + 0.04,
                  z_ridge - 0.25, z_ridge + 0.1, BRICK,
                  side_shader=speckle_shader(BRICK))


def steps(model, s):
    for k in range(3):
        add_block(model, FRAME, s, s + 0.18 - 0.05 * k, -0.17, 0.17,
                  0, 0.025 * (k + 1), STONE)


def tower(model, s_gable, z_top):
    """Square brick tower in front of the gable, a trimmed belfry,
    and a copper spire on an octagonal drum."""
    s0, s1, w = s_gable - 0.14, s_gable + 0.28, 0.22
    sc = (s0 + s1) / 2
    add_block(model, FRAME, s0, s1, -w, w, 0, z_top, BRICK,
              side_shader=speckle_shader(BRICK))
    floors = int(z_top / STOREY)
    facade(model, FRAME, (s1, -w), (s1, w), (-1, 0), RED_BRICK,
           storeys=floors, bays=1, door=True)
    facade(model, FRAME, (s0, -w), (s1, -w), (0, 1), RED_BRICK,
           storeys=floors, bays=1)
    add_block(model, FRAME, s0 - 0.03, s1 + 0.03, -w - 0.03, w + 0.03,
              z_top, z_top + 0.04, TRIM)
    add_block(model, FRAME, s0, s1, -w, w, z_top + 0.04, z_top + 0.3, TRIM)
    for a, b, inward in (((s1, -0.1), (s1, 0.1), (-1, 0)),
                         ((sc - 0.1, -w), (sc + 0.1, -w), (0, 1))):
        wall_quad(model, FRAME, a, b, z_top + 0.09, z_top + 0.25, 0.004,
                  RED_BRICK.glass, inward)
    add_block(model, FRAME, s0 - 0.03, s1 + 0.03, -w - 0.03, w + 0.03,
              z_top + 0.3, z_top + 0.34, TRIM)
    # Copper cap, open lantern, spire.
    add_frustum(model, FRAME, sc, 0, 0.2, 0.08, z_top + 0.34, z_top + 0.5,
                COPPER, n=8)
    add_frustum(model, FRAME, sc, 0, 0.08, 0.08, z_top + 0.5, z_top + 0.62,
                TRIM, n=8)
    add_frustum(model, FRAME, sc, 0, 0.1, 0.0, z_top + 0.62, z_top + 0.85,
                COPPER, n=8)
    steps(model, s1)


def fountain(model):
    s, p = FRONT_S, 0.0
    add_frustum(model, FRAME, s, p, 0.3, 0.3, 0, 0.06, STONE, n=12)
    add_frustum(model, FRAME, s, p, 0.26, 0.26, 0.06, 0.062, WATER, n=12)
    add_frustum(model, FRAME, s, p, 0.05, 0.04, 0.06, 0.2, STONE, n=8)
    add_frustum(model, FRAME, s, p, 0.12, 0.13, 0.2, 0.24, STONE, n=12)
    add_frustum(model, FRAME, s, p, 0.03, 0.0, 0.24, 0.33, WATER, n=6)


def conifer(model, s, p, height=0.75):
    k = height / 0.75
    add_frustum(model, FRAME, s, p, 0.03, 0.03, 0, 0.08, TRUNK, n=6)
    for r, z0, z1 in ((0.2, 0.06, 0.45), (0.15, 0.3, 0.65), (0.1, 0.5, 0.8)):
        add_frustum(model, FRAME, s, p, r * k, 0.0, z0 * k, z1 * k, CONIFER,
                    n=10)


def build(h: TownhallParams) -> Model:
    model = Model()
    ground(model, ground_shader(h))
    s1 = h.length / 2
    z_eave, z_ridge = gabled_block(model, FRAME, -s1, s1, h.width / 2,
                                   h.storeys, RED_BRICK, door=not h.tower)
    chimneys(model, FRAME, z_ridge, (-s1 + 0.35, 0.1))
    if h.tower:
        tower(model, s1, z_eave + h.tower)
    else:
        steps(model, s1)
    if h.wings:
        for side in (-1, 1):
            gabled_block(model, side_frame(side, WING_S), h.width / 2 - 0.05,
                         WING_REACH, WING_HALF, h.wings, RED_BRICK,
                         pitch=0.32)
    fountain(model)
    for p in (-0.62, 0.62):
        conifer(model, FRONT_S - 0.55, p)
        if not h.wings:
            conifer(model, 0.25, p * 1.75, height=0.6)
    return model


# --- Bake ---------------------------------------------------------------------

def bake_pakset() -> None:
    rewrite_images(DAT, {
        h.name: bake_tiles(build(h), DIMS,
                           TOWNHALLS_DIR / f"town{h.name[:2].lstrip('0')}_hex.png")
        for h in TOWNHALLS})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write all five on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build(h) for h in TOWNHALLS], DIMS, a.preview)
    else:
        bake_pakset()
