"""3D models of the pak128 airport buildings and towers for the hex grid.

All of them but `Very_Big_Terminal` are one-tile station extensions
with 1, 2 or 4 layouts, baked as a `tools.threed.blocks` catalogue:
most are boxes in one of a few period styles, listed in `BUILDINGS`
as blocks plus extras; the towers and the radar have their own parts.

    python3 -m infrastructure.airport_buildings_towers.hex_airport.scene
    python3 -m infrastructure.airport_buildings_towers.hex_airport.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from tools.threed.blocks import (
    DARK, WHITE, Block, Building, bake_catalogue, block, canopy, hip,
    preview)
from tools.threed.building_kit import (
    STOREY, Palette, add_beam, facade, gabled_block, speckle_shader,
    wall_quad)
from tools.threed.factory_kit import lorry
from tools.threed.solids import Frame, add_block, add_face, add_frustum

AIRPORT_DIR = Path(__file__).resolve().parent.parent

MODERN = Palette(wall=(228, 216, 182), trim=(40, 70, 150),
                 roof=(150, 152, 158), glass=(150, 170, 220))
GREY = Palette(wall=(176, 176, 170), trim=(222, 220, 212),
               roof=(116, 118, 122), glass=(56, 66, 84))
WOOD = Palette(wall=(118, 74, 48), trim=(196, 180, 150), roof=(98, 96, 96),
               glass=(170, 196, 214))
CREAM = Palette(wall=(226, 214, 176), trim=(246, 240, 224),
                roof=(150, 150, 150), glass=(56, 66, 84))
BRICK = Palette(wall=(150, 74, 52), trim=(220, 210, 190),
                roof=(90, 90, 96), glass=(56, 66, 84))
CAB_GLASS = (60, 150, 110)
RED = (196, 40, 36)


# --- Parts --------------------------------------------------------------------

def cab(model, fr: Frame, s, p, z, r, *, glass=CAB_GLASS, roof=MODERN.trim,
        n=12, h=0.12):
    """A control cab: a glazed ring under an overhanging roof."""
    add_frustum(model, fr, s, p, r * 0.9, r, z, z + h, glass, n=n)
    add_frustum(model, fr, s, p, r * 1.15, r * 0.6, z + h, z + h + 0.05,
                roof, n=n)
    add_beam(model, fr.world(s, p, z + h + 0.05), fr.world(s, p, z + h + 0.18),
             0.012, DARK)


def lattice_mast(model, fr: Frame, s, p, z, h, *, w=0.05):
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        add_beam(model, fr.world(s + w * math.cos(a), p + w * math.sin(a), z),
                 fr.world(s, p, z + h), 0.012, RED if k % 2 else WHITE)
    for t in (0.3, 0.6):
        add_block(model, fr, s - w * (1 - t), s + w * (1 - t),
                  p - w * (1 - t), p + w * (1 - t), z + h * t - 0.01,
                  z + h * t + 0.01, RED)


# --- Towers and radar ---------------------------------------------------------

def tower1920(model, fr):
    """A wooden lattice tower with a hut on top, a shed at its foot."""
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        add_beam(model,
                 fr.world(-0.1 + 0.2 * math.cos(a), 0.2 * math.sin(a), 0),
                 fr.world(-0.1 + 0.12 * math.cos(a), 0.12 * math.sin(a), 0.6),
                 0.025, WOOD.wall)
    for z in (0.2, 0.4):
        add_block(model, fr, -0.27, 0.07, -0.17, 0.17, z - 0.01, z + 0.01,
                  WOOD.wall)
    add_block(model, fr, -0.24, 0.04, -0.14, 0.14, 0.6, 0.76, WOOD.wall)
    add_block(model, fr, -0.22, 0.02, -0.15, 0.15, 0.66, 0.72, WOOD.glass)
    hip(model, fr, -0.27, 0.07, 0.17, 0.76, 0.1, (150, 70, 52))
    gabled_block(model, fr, 0.2, 0.55, 0.15, 1, WOOD, pitch=0.12,
                 stepped=False, door=True)


def tower1930(model, fr):
    """A square brick tower, a glazed cab on top, fire engines below."""
    add_block(model, fr, -0.3, 0.0, -0.15, 0.15, 0.0, 0.8, BRICK.wall,
              side_shader=speckle_shader(BRICK.wall))
    facade(model, fr, (0.0, -0.15), (0.0, 0.15), (-1, 0), BRICK, storeys=3,
           bays=1, door=True)
    add_block(model, fr, -0.33, 0.03, -0.18, 0.18, 0.8, 0.84, BRICK.trim)
    add_block(model, fr, -0.3, 0.0, -0.15, 0.15, 0.84, 0.96, CAB_GLASS)
    add_block(model, fr, -0.34, 0.04, -0.19, 0.19, 0.96, 1.0, BRICK.roof)
    for q in (-0.25, 0.25):
        lorry(model, fr, 0.3, q, cab=RED, box=RED, length=0.26)


def tower1950(model, fr):
    """A white tower with a chequered top and a radio mast."""
    b = Block(-0.32, 0.08, 0.18, 4, CREAM, parapet="chequer", door=True)
    block(model, fr, b)
    lattice_mast(model, fr, -0.12, 0.0, 4 * STOREY + 0.04, 0.6)
    add_block(model, fr, 0.08, 0.5, -0.3, 0.1, 0.0, STOREY + 0.04, CREAM.wall,
              side_shader=speckle_shader(CREAM.wall))
    add_block(model, fr, 0.06, 0.52, -0.32, 0.12, STOREY + 0.04,
              STOREY + 0.07, CREAM.trim)


def tower1990(model, fr):
    """A round shaft on a banded base, a wide round cab on top."""
    block(model, fr, Block(-0.45, 0.35, 0.36, 2, MODERN, bands=True))
    top = 2 * STOREY + 0.04
    for k in range(5):
        z0 = top + k * 0.22
        add_frustum(model, fr, -0.05, 0.0, 0.13, 0.13, z0, z0 + 0.18,
                    MODERN.wall, n=14)
        add_frustum(model, fr, -0.05, 0.0, 0.135, 0.135, z0 + 0.18, z0 + 0.22,
                    MODERN.trim, n=14)
    z = top + 5 * 0.22
    add_frustum(model, fr, -0.05, 0.0, 0.13, 0.26, z, z + 0.08, MODERN.wall,
                n=16)
    cab(model, fr, -0.05, 0.0, z + 0.08, 0.27, n=16, h=0.14)


def radar(model, fr):
    """A hut with a radar dish on a pole beside it."""
    add_block(model, fr, -0.2, 0.15, -0.15, 0.15, 0.0, 0.28, GREY.wall,
              side_shader=speckle_shader(GREY.wall))
    add_block(model, fr, -0.22, 0.17, -0.17, 0.17, 0.28, 0.31, GREY.roof)
    wall_quad(model, fr, (0.15, -0.05), (0.15, 0.05), 0.0, 0.18, 0.01, DARK,
              (-1, 0))
    add_beam(model, fr.world(-0.02, 0.0, 0.31), fr.world(-0.02, 0.0, 0.62),
             0.04, DARK)
    # The dish: a shallow paraboloid leaning back, as a fan of strips.
    c = np.array(fr.world(-0.02, 0.0, 0.7))
    tilt = math.radians(35)
    for k in range(12):
        a0, a1 = 2 * math.pi * k / 12, 2 * math.pi * (k + 1) / 12
        ring = []
        for a in (a0, a1):
            x, y = 0.3 * math.cos(a), 0.3 * math.sin(a)
            dz = 0.05 + x * math.sin(tilt)
            ring.append(c + np.array(fr.world(x * math.cos(tilt), y, 0)) -
                        np.array(fr.world(0, 0, 0)) + np.array((0, 0, dz)))
        add_face(model, [tuple(c), tuple(ring[0]), tuple(ring[1])],
                 (210, 210, 206), outward=tuple(c + np.array((0, 0, -1))))


# --- Catalogue ----------------------------------------------------------------

def entrance_extras(model, fr):
    canopy(model, fr, 0.25, 0.3, 0.26, MODERN.trim)
    add_beam(model, fr.world(0.55, 0.4, 0), fr.world(0.55, 0.4, 0.4), 0.02,
             DARK)


def gates_extras(model, fr):
    # A jet bridge reaching out from the gate building.
    add_block(model, fr, 0.25, 0.75, -0.06, 0.06, 0.18, 0.28, (210, 210, 210))
    add_block(model, fr, 0.66, 0.7, -0.03, 0.03, 0.0, 0.18, DARK)


def postoffice1920_extras(model, fr):
    lorry(model, fr, 0.45, 0.25, cab=(60, 70, 60), box=(150, 120, 80),
          length=0.28)


def luftpost_extras(model, fr):
    lorry(model, fr, 0.45, -0.25, cab=(220, 180, 30), box=(220, 180, 30),
          length=0.3)


def bigterminal1930_extras(model, fr):
    top = 2 * STOREY + 0.04
    add_block(model, fr, -0.25, 0.05, -0.12, 0.12, top + 0.15, top + 0.22,
              BRICK.trim)
    add_block(model, fr, -0.22, 0.02, -0.1, 0.1, top + 0.22, top + 0.32,
              CAB_GLASS)
    add_block(model, fr, -0.25, 0.05, -0.13, 0.13, top + 0.32, top + 0.35,
              GREY.roof)


BUILDINGS = [
    Building("Airport1920_AirportBlg", "airport1920_airportblg", 2, [
        Block(-0.6, 0.0, 0.32, 1, GREY, roof="gable", door=True),
        Block(0.05, 0.5, 0.26, 1, GREY, roof="gable", door=True)]),
    Building("Airport1930PostOffice", "airport1930postoffice", 1, [
        Block(-0.55, 0.45, 0.42, 1, WOOD, roof="sawtooth")]),
    Building("PostOffice1920_AirportBlg", "postoffice1920_airportblg", 2, [
        Block(-0.6, 0.15, 0.32, 1, GREY, roof="gable", door=True, pitch=0.14)],
        postoffice1920_extras),
    Building("LuftPost1950_AirportBlg", "luftpost1950_airportblg", 2, [
        Block(-0.6, 0.2, 0.36, 2, CREAM, roof="gable", door=True)],
        luftpost_extras),
    Building("Terminal1930_AirportBlg", "terminal1930_airportblg", 4, [
        Block(-0.55, 0.25, 0.34, 2, GREY, roof="gable", door=True),
        Block(-0.2, 0.15, 0.48, 1, GREY, roof="hip", pitch=0.12)]),
    Building("BigTerminal1930_AirportBlg", "bigterminal1930_airportblg", 4, [
        Block(-0.6, 0.3, 0.42, 2, GREY, roof="hip", door=True, pitch=0.15)],
        bigterminal1930_extras),
    Building("Terminal1950_AirportBlg_S", "terminal1950_airportblg_s", 4, [
        Block(-0.55, 0.3, 0.42, 2, CREAM, parapet="plain", door=True)]),
    Building("BigTerminal1950_AirportBlg_S", "bigterminal1950_airportblg_s", 4,
             [Block(-0.55, 0.25, 0.4, 4, CREAM, parapet="chequer",
                    door=True)]),
    Building("Airport1990_Entrance_AirportBlg",
             "airport1990_entrance_airportblg", 4, [
        Block(-0.6, 0.25, 0.25, 1, MODERN, roof="glazed", bands=True),
        Block(-0.6, -0.1, 0.5, 1, MODERN, roof="glazed", bands=True)],
        entrance_extras),
    Building("Airport1990_Gates_AirportBlg", "airport1990_gates_airportblg", 2,
             [Block(-0.6, 0.25, 0.45, 1, MODERN, roof="flat", bands=True)],
             gates_extras),
    Building("Airport1990_Small_AirportBlg", "airport1990_small_airportblg", 1,
             [Block(-0.45, 0.4, 0.42, 3, MODERN, roof="glazed", bands=True)]),
    Building("Airport1990_Small_PostOffice", "airport1990_small_postoffice", 1,
             [Block(-0.45, 0.4, 0.42, 3, MODERN, roof="glazed", bands=True),
              Block(-0.2, 0.15, 0.2, 4, MODERN, roof="glazed", bands=True)]),
    Building("Airport1990_PostOffice", "airport1990_postoffice", 1, [
        Block(-0.5, 0.4, 0.4, 2, MODERN, roof="glazed", bands=True),
        Block(-0.35, 0.1, 0.25, 3, MODERN, roof="glazed", bands=True)]),
    Building("Airport1990_Big_AirportBlg", "airport1990_big_airportblg", 1, [
        Block(-0.4, 0.3, 0.35, 8, MODERN, roof="glazed", bands=True)]),
    Building("Airport1990_Big_PostOffice", "airport1990_big_postoffice", 1, [
        Block(-0.4, 0.3, 0.35, 8, MODERN, roof="glazed", bands=True)]),
    Building("Airport1990_Warehouse", "airport1990_warehouse", 1, [
        Block(-0.55, 0.45, 0.42, 1, MODERN, roof="gable", pitch=0.14),
        Block(-0.35, 0.25, 0.2, 2, MODERN, roof="gable", pitch=0.12)]),
    Building("Tower1920_AirportBlg", "tower1920_airportblg", 1,
             extras=tower1920),
    Building("Tower1930_AirportBlg", "tower1930_airportblg", 1,
             extras=tower1930),
    Building("Tower1950_AirportBlg", "tower1950_airportblg", 1,
             extras=tower1950),
    Building("Tower1990_AirportBlg", "tower1990_airportblg", 1,
             extras=tower1990),
    Building("Radar3", "radar3", 1, extras=radar),
]


def bake_pakset() -> None:
    bake_catalogue(BUILDINGS, AIRPORT_DIR)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write every building on grass here instead of "
                         "baking")
    a = ap.parse_args()
    if a.preview:
        preview(BUILDINGS, a.preview)
    else:
        bake_pakset()
