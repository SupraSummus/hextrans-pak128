"""3D models of the pak128 shaft coal mines for the hex grid.

Both mines are `Dims=2,2`, laid out as the townhalls are (see
`tools.threed.building_kit`): the headframe stands on the vertex of
the back triangle, the winding house on the triangle's left tile with
its ropes running up to the sheaves, and the coal heap with its
rails and tubs on the front tile.

    python3 -m factories.hex_mines.scene
    python3 -m factories.hex_mines.scene --preview sheet.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, STOREY, Palette, add_beam, bake_tiles,
    gabled_block, ground, outside_distance, preview, rewrite_images,
    side_frame, speckle_shader)
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import Model
from tools.threed.solids import add_block, add_frustum

FACTORIES_DIR = Path(__file__).resolve().parent.parent
DIMS = (2, 2)

IRON = (128, 70, 46)
SHEAVE = (226, 222, 210)
WALKWAY = (196, 190, 178)
SHEAVE_R = 0.25
ROPE = (40, 36, 34)
COAL = (52, 52, 58)
DIRT = (150, 138, 118)
GRAVEL = (124, 120, 114)
RAIL = (70, 66, 62)
SLEEPER = (104, 80, 58)
TUB = (96, 92, 88)
PLASTER = Palette(wall=(238, 210, 140), trim=(246, 238, 214),
                  roof=(92, 94, 104))


@dataclass(frozen=True)
class MineParams:
    name: str
    height: float       # headframe, ground to sheave deck
    sheaves: int        # 1 or 2, side by side along the rope
    house_storeys: int
    heap: float         # coal heap radius


MINES = [
    MineParams("shaft_coal_mine", height=1.9, sheaves=2, house_storeys=2,
               heap=0.55),
    MineParams("shaft_coal_mine_small", height=1.55, sheaves=1,
               house_storeys=1, heap=0.4),
]

# The house sits across the hall axis on the left tile; ropes leave
# the sheaves towards it, so the sheaves face the camera.
HOUSE = side_frame(-1, 0.5)
HOUSE_IN, HOUSE_OUT, HOUSE_HALF = 0.55, 1.35, 0.3


# --- Ground -------------------------------------------------------------------

def yard_shader(wx, wy, sx, sy):
    """Dirt yard, dusted with coal towards the heap, with the track from
    the shaft and a gravel edge."""
    dirt, gravel = np.array(DIRT, float), np.array(GRAVEL, float)
    coal = np.array(COAL, float)
    rail, sleeper = np.array(RAIL, float), np.array(SLEEPER, float)
    s, p = FRAME.local(wx, wy)
    n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
    edge = outside_distance(DIMS, wx, wy)
    rgb = np.empty((len(wx), 3))
    rgb[:] = dirt * (0.9 + 0.16 * n)[:, None]
    # Coal dust darkens the yard towards the heap.
    dust = np.clip(1.2 - np.hypot(s - FRONT_S, p - 0.25) / 0.9, 0, 1)
    dust *= n < 0.75
    rgb = rgb * (1 - 0.6 * dust)[:, None] + coal * (0.6 * dust)[:, None]
    # Track from the shaft to the heap: sleepers, then two rails.
    on = (s > 0.25) & (s < FRONT_S + 0.9) & (np.abs(p + 0.25) < 0.11)
    ties = on & ((s / 0.07) % 1.0 < 0.45)
    rgb[ties] = sleeper
    rails = on & (np.abs(np.abs(p + 0.25) - 0.065) < 0.012)
    rgb[rails] = rail
    rgb[edge < 0.04] = gravel * 0.85
    return rgb, np.ones(len(wx), bool)


# --- Parts --------------------------------------------------------------------

def headframe(model, m: MineParams):
    """Lattice tower narrowing upwards over the shaft, braced across each
    face, with a deck and sheaves on top and a strut leaning towards
    the winding house."""
    base, top, h = 0.42, 0.26, m.height
    levels = max(4, round(h / 0.3))
    w = 0.04

    def corner(i, z):
        r = base + (top - base) * z / h
        return FRAME.world((-1 if i in (0, 3) else 1) * r,
                           (-1 if i in (0, 1) else 1) * r, z)

    for i in range(4):
        add_beam(model, corner(i, 0), corner(i, h), w, IRON)
    for k in range(1, levels + 1):
        z0, z1 = h * (k - 1) / levels, h * k / levels
        for i in range(4):
            j = (i + 1) % 4
            add_beam(model, corner(i, z1), corner(j, z1), w * 0.8, IRON)
            add_beam(model, corner(i, z0), corner(j, z1), w * 0.6, IRON)
            add_beam(model, corner(j, z0), corner(i, z1), w * 0.6, IRON)
        if k % 2 == 0 and k < levels:
            # Walkway round the tower, the light band of pak128's frames.
            r = base + (top - base) * z1 / h
            for a, b in ((-r - 0.06, -r + 0.02), (r - 0.02, r + 0.06)):
                add_block(model, FRAME, a, b, -r - 0.06, r + 0.06,
                          z1 - 0.012, z1 + 0.012, WALKWAY)
                add_block(model, FRAME, -r - 0.06, r + 0.06, a, b,
                          z1 - 0.012, z1 + 0.012, WALKWAY)
    # Deck, with a rail around it.
    add_block(model, FRAME, -top - 0.06, top + 0.06, -top - 0.06, top + 0.06,
              h, h + 0.03, IRON)
    # Strut from high on the tower down towards the house.
    for ds in (-0.12, 0.12):
        add_beam(model, FRAME.world(ds, -0.12, h * 0.8),
                 FRAME.world(ds * 1.6, -0.9, 0), w * 1.4, IRON)
    # Two sheaves sit one behind the other, the back one higher.
    pairs = ((-0.14, 0.5), (0.14, 0.28)) if m.sheaves == 2 else ((0.0, 0.28),)
    for ds, dz in pairs:
        sheave_z = h + dz
        sheave(model, ds, sheave_z, SHEAVE_R)
        add_block(model, FRAME, ds - 0.02, ds + 0.02, -0.05, 0.05, h + 0.03,
                  sheave_z, IRON)
        # Rope from the sheave's top over to the house roof.
        add_beam(model, FRAME.world(ds, -SHEAVE_R, sheave_z),
                 HOUSE.world(HOUSE_IN + 0.15, ds,
                             m.house_storeys * STOREY + 0.2),
                 0.012, ROPE)
        add_beam(model, FRAME.world(ds, 0.0, sheave_z - SHEAVE_R),
                 FRAME.world(ds, 0.0, h), 0.012, ROPE)


def sheave(model, s, z, r, n=18):
    """Spoked wheel in the plane across the frame (`p`, `z`), centred
    on `(s, 0, z)`: it faces down `s`, towards the camera."""
    def at(a, rr):
        return FRAME.world(s, rr * math.cos(a), z + rr * math.sin(a))

    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        add_beam(model, at(a0, r), at(a1, r), 0.05, SHEAVE,
                 up=(*FRAME.u, 0.0))
    for k in range(6):
        a = 2 * math.pi * k / 6
        add_beam(model, at(a, 0.02), at(a, r - 0.02), 0.022, SHEAVE)
    add_beam(model, FRAME.world(s - 0.05, 0, z), FRAME.world(s + 0.05, 0, z),
             0.05, IRON)


def winding_house(model, m: MineParams):
    gabled_block(model, HOUSE, HOUSE_IN, HOUSE_OUT, HOUSE_HALF,
                 m.house_storeys, PLASTER, pitch=0.26, door=True,
                 stepped=False, bays=3)
    z = m.house_storeys * STOREY + 0.26
    add_block(model, HOUSE, HOUSE_OUT - 0.25, HOUSE_OUT - 0.15, 0.08, 0.18,
              z - 0.2, z + 0.22, (150, 70, 52),
              side_shader=speckle_shader((150, 70, 52)))


def heap(model, m: MineParams):
    """Coal heap: stacked flattened cones, darker grain on top."""
    s, p, r = FRONT_S + 0.1, 0.35, m.heap
    for k, (rr, z0, z1) in enumerate(((1.0, 0.0, 0.14), (0.7, 0.12, 0.26),
                                      (0.38, 0.24, 0.34))):
        add_frustum(model, FRAME, s, p, r * rr, r * rr * 0.75,
                    z0 * r / 0.55, z1 * r / 0.55, COAL, n=14,
                    top_shader=speckle_shader(COAL),
                    side_shader=speckle_shader(COAL))


def tubs(model):
    """Two mine tubs on the track."""
    for s in (0.75, 1.15):
        add_block(model, FRAME, s - 0.1, s + 0.1, -0.33, -0.17, 0.03, 0.15,
                  TUB, side_color=tuple(int(c * 0.8) for c in TUB))
        add_block(model, FRAME, s - 0.08, s + 0.08, -0.31, -0.19, 0.15, 0.17,
                  COAL)


def build(m: MineParams) -> Model:
    model = Model()
    ground(model, yard_shader)
    headframe(model, m)
    winding_house(model, m)
    heap(model, m)
    tubs(model)
    return model


# --- Bake ---------------------------------------------------------------------

def bake_pakset() -> None:
    for m in MINES:
        dat = FACTORIES_DIR / f"{m.name}.dat"
        rewrite_images(dat, {m.name: bake_tiles(
            build(m), DIMS, FACTORIES_DIR / f"{m.name}_hex.png")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write both on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build(m) for m in MINES], DIMS, a.preview)
    else:
        bake_pakset()
