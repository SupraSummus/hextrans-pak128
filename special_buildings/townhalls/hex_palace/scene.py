"""3D models of the pak128 white-palace townhalls for the hex grid.

`01_CITY_1`..`04_CITY_1`, the townhalls of hot climates, share one
square sheet (`city-townhall-2-128.png`): a white palace under blue
domes, a pink portal with a pointed arch, a walled garden with palms.
Here they are the `Dims=2,2` layout of the red-brick townhalls
(`hex_townhalls`): the palace on the back triangle, the garden with a
pool on the front tile, and each size a little grander than the last.

    python3 -m special_buildings.townhalls.hex_palace.scene
    python3 -m special_buildings.townhalls.hex_palace.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tools.threed.building_kit import (
    FRONT_S, RHOMBUS_FRAME as FRAME, STOREY, bake_tiles, footprint_outline,
    ground, outside_distance, preview, rewrite_images, speckle_shader,
    wall_quad)
from tools.threed.factory_kit import palm
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import Model
from tools.threed.solids import add_block, add_frustum, add_solid

TOWNHALLS_DIR = Path(__file__).resolve().parent.parent
DAT = TOWNHALLS_DIR / "city-townhalls-128.dat"
DIMS = (2, 2)

PLASTER = (234, 226, 206)
TRIM = (250, 246, 234)
PINK = (210, 124, 118)
BLUE = (70, 104, 196)
DARK = (48, 42, 46)
GOLD = (220, 186, 70)
PAVING = (214, 200, 166)
LAWN = (104, 146, 66)
WATER = (90, 150, 200)


@dataclass(frozen=True)
class PalaceParams:
    name: str
    storeys: int
    half: float             # half the palace's side
    dome: float             # radius of the central dome, 0 for none


PALACES = [
    PalaceParams("01_CITY_1", storeys=1, half=0.55, dome=0.0),
    PalaceParams("02_CITY_1", storeys=2, half=0.6, dome=0.0),
    PalaceParams("03_CITY_1", storeys=2, half=0.65, dome=0.26),
    PalaceParams("04_CITY_1", storeys=3, half=0.7, dome=0.32),
]
CENTRE = -0.2       # the palace's centre along the frame
GATE = 0.22         # the gap either side of the front corner


def garden_shader(wx, wy, sx, sy):
    """Paving round the palace, lawn beds and a pool on the front tile."""
    s, p = FRAME.local(wx, wy)
    n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
    rgb = np.empty((len(wx), 3))
    rgb[:] = np.array(PAVING, float) * (0.92 + 0.12 * n)[:, None]
    front = s - FRONT_S
    bed = (np.abs(p) > 0.14) & (np.abs(front) < 0.55) & (np.abs(p) < 0.62)
    bed &= outside_distance(DIMS, wx, wy) > 0.12
    rgb[bed] = np.array(LAWN, float) * (0.9 + 0.2 * n[bed])[:, None]
    pool = (np.abs(front - 0.05) < 0.16) & (np.abs(p) < 0.1)
    rgb[pool] = WATER
    return rgb, np.ones(len(wx), bool)


def onion(model, s, p, z, r, color=BLUE):
    """A dome on a short drum, slightly swelling, with a gold finial."""
    profile = [(1.0, 0.0), (1.08, 0.3), (1.0, 0.6), (0.75, 0.9), (0.4, 1.12),
               (0.0, 1.3)]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        add_frustum(model, FRAME, s, p, r * r0, r * r1, z + r * z0,
                    z + r * z1, color, n=12)
    add_frustum(model, FRAME, s, p, 0.012, 0.0, z + r * 1.3,
                z + r * 1.3 + 0.08, GOLD, n=4)


def pointed_arch(model, a, b, z0, z1, off, color, inward, steps=6):
    """An opening from `a` to `b` on a wall, square up to two thirds of
    its height, then narrowing to a point."""
    zs = z0 + (z1 - z0) * 0.62
    wall_quad(model, FRAME, a, b, z0, zs, off, color, inward)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    for k in range(steps):
        t = 1 - (k + 0.5) / steps
        aa = (mid[0] + (a[0] - mid[0]) * math.sqrt(t),
              mid[1] + (a[1] - mid[1]) * math.sqrt(t))
        bb = (mid[0] + (b[0] - mid[0]) * math.sqrt(t),
              mid[1] + (b[1] - mid[1]) * math.sqrt(t))
        wall_quad(model, FRAME, aa, bb, zs + (z1 - zs) * k / steps,
                  zs + (z1 - zs) * (k + 1) / steps, off, color, inward)


def arcade(model, a, b, inward, z0, z1, n):
    """`n` pointed windows evenly along the wall from `a` to `b`."""
    length = math.dist(a, b)
    d = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    pitch = length / n
    for k in range(n):
        c = (k + 0.5) * pitch
        w = pitch * 0.22
        pa = (a[0] + d[0] * (c - w), a[1] + d[1] * (c - w))
        pb = (a[0] + d[0] * (c + w), a[1] + d[1] * (c + w))
        pointed_arch(model, pa, pb, z0, z1, 0.008, DARK, inward)


def palace(model, h: PalaceParams):
    c, w = CENTRE, h.half
    s0, s1 = c - w, c + w
    top = h.storeys * STOREY + 0.06
    add_block(model, FRAME, s0, s1, -w, w, 0.0, top, PLASTER,
              side_shader=speckle_shader(PLASTER))
    add_block(model, FRAME, s0 - 0.02, s1 + 0.02, -w - 0.02, w + 0.02, top,
              top + 0.03, TRIM)
    # Crenellated parapet.
    for (a, b) in (((s0, -w), (s1, -w)), ((s1, -w), (s1, w)),
                   ((s1, w), (s0, w)), ((s0, w), (s0, -w))):
        n = round(math.dist(a, b) / 0.1)
        for k in range(0, n, 2):
            t0, t1 = k / n, (k + 1) / n
            add_block(model, FRAME, min(a[0] + (b[0] - a[0]) * t0,
                                        a[0] + (b[0] - a[0]) * t1) - 0.015,
                      max(a[0] + (b[0] - a[0]) * t0,
                          a[0] + (b[0] - a[0]) * t1) + 0.015,
                      min(a[1] + (b[1] - a[1]) * t0,
                          a[1] + (b[1] - a[1]) * t1) - 0.015,
                      max(a[1] + (b[1] - a[1]) * t0,
                          a[1] + (b[1] - a[1]) * t1) + 0.015,
                      top + 0.03, top + 0.07, TRIM)
    # Pointed windows round every storey.
    for k in range(h.storeys):
        z0 = k * STOREY + 0.06
        for a, b, inward in (((s0, -w), (s1, -w), (0, 1)),
                             ((s0, w), (s1, w), (0, -1)),
                             ((s0, -w), (s0, w), (1, 0))):
            arcade(model, a, b, inward, z0 + 0.03, z0 + 0.17, 4)
        for q in (-w, w):
            arcade(model, (s1, q * 0.95), (s1, q * 0.45), (-1, 0),
                   z0 + 0.03, z0 + 0.17, 1)
    # The portal: a pink frame standing proud of the front, a deep
    # pointed arch in it, the door at its foot.
    pw = w * 0.42
    ph = top + 0.14
    add_block(model, FRAME, s1, s1 + 0.06, -pw, pw, 0.0, ph, PINK,
              side_shader=speckle_shader(PINK))
    add_block(model, FRAME, s1 - 0.01, s1 + 0.07, -pw - 0.01, pw + 0.01, ph,
              ph + 0.03, TRIM)
    pointed_arch(model, (s1 + 0.06, -pw * 0.7), (s1 + 0.06, pw * 0.7), 0.0,
                 ph - 0.06, 0.004, TRIM, (-1, 0))
    pointed_arch(model, (s1 + 0.06, -pw * 0.6), (s1 + 0.06, pw * 0.6), 0.0,
                 ph - 0.1, 0.008, (120, 60, 70), (-1, 0))
    wall_quad(model, FRAME, (s1 + 0.06, -0.06), (s1 + 0.06, 0.06), 0.0, 0.16,
              0.012, (92, 60, 40), (-1, 0))
    # Corner turrets, standing proud of the corners.
    for ds in (s0, s1):
        for q in (-w, w):
            add_frustum(model, FRAME, ds, q, 0.12, 0.11, 0.0, top + 0.14,
                        PLASTER, n=8, side_shader=speckle_shader(PLASTER))
            add_frustum(model, FRAME, ds, q, 0.13, 0.13, top + 0.14,
                        top + 0.17, TRIM, n=8)
            onion(model, ds, q, top + 0.17, 0.1)
    if h.dome:
        add_frustum(model, FRAME, c, 0.0, h.dome * 0.95, h.dome * 0.95, top,
                    top + 0.12, PLASTER, n=16,
                    side_shader=speckle_shader(PLASTER))
        onion(model, c, 0.0, top + 0.12, h.dome)
    else:
        # A skylight pavilion on the roof instead of the dome.
        add_block(model, FRAME, c - 0.18, c + 0.18, -0.18, 0.18, top,
                  top + 0.1, (160, 200, 220))


def garden_wall(model):
    """A low white wall round the plot, open at the front corner between
    two domed gate posts."""
    gate = FRAME.world(FRONT_S + 1.0, 0.0, 0.0)[:2]
    for a, b in footprint_outline(DIMS, inset=0.05):
        length = math.dist(a, b)
        u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        if math.dist(a, gate) < 0.2:
            a = (a[0] + u[0] * GATE, a[1] + u[1] * GATE)
            gate_post(model, a)
        if math.dist(b, gate) < 0.2:
            b = (b[0] - u[0] * GATE, b[1] - u[1] * GATE)
            gate_post(model, b)
        quad = [(a[0] - u[1] * 0.025, a[1] + u[0] * 0.025),
                (b[0] - u[1] * 0.025, b[1] + u[0] * 0.025),
                (b[0] + u[1] * 0.025, b[1] - u[0] * 0.025),
                (a[0] + u[1] * 0.025, a[1] - u[0] * 0.025)]
        add_solid(model, [(x, y, 0.0) for x, y in quad],
                  [(x, y, 0.12) for x, y in quad], TRIM,
                  side_shader=speckle_shader(PLASTER))


def gate_post(model, at):
    s, p = FRAME.local(*at)
    add_frustum(model, FRAME, s, p, 0.05, 0.05, 0.0, 0.2, PLASTER, n=8,
                side_shader=speckle_shader(PLASTER))
    onion(model, s, p, 0.2, 0.045)


def build(h: PalaceParams) -> Model:
    model = Model()
    ground(model, garden_shader)
    palace(model, h)
    garden_wall(model)
    for q in (-0.42, 0.42):
        palm(model, FRAME, FRONT_S - 0.1, q, 0.75, lean=(0.03, q * 0.08))
    palm(model, FRAME, -0.4, -1.05, 0.6)
    return model


def bake_pakset() -> None:
    rewrite_images(DAT, {
        h.name: bake_tiles(build(h), DIMS,
                           TOWNHALLS_DIR / f"palace{h.name[1]}_hex.png")
        for h in PALACES})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write all four on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build(h) for h in PALACES], DIMS, a.preview)
    else:
        bake_pakset()
