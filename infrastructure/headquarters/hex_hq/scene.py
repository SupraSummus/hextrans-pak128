"""3D models of the six player headquarters for the hex grid.

`Dims=3,3,1`: one layout on the 9-hex rhombus.  The first three levels
are a fenced yard among trees with a timber office, a Nissen hut for the
lorries and, at the third, a picnic table and a second hut; the last
three are an office block of 4, 9 and 16 storeys over a car park, the
top one with a roof garden of dishes and solar panels.  `FRAME` runs
along the rhombus's long diagonal, `+s` towards the camera.

    python3 -m infrastructure.headquarters.hex_hq.scene
    python3 -m infrastructure.headquarters.hex_hq.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tools.threed.building import tile_centre
from tools.threed.building_kit import (
    STOREY, Palette, add_beam, bake_tiles, course_shader, facade,
    footprint_outline, gabled_block, outside_distance, preview,
    rewrite_images, speckle_shader)
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import Model
from tools.threed.solids import Frame, add_block, add_face, add_frustum

HQ_DIR = Path(__file__).resolve().parent.parent
DIMS = (3, 3)
FRAME = Frame((0.5, -math.sqrt(3) / 2), origin=tile_centre(1, 1))

GRAVEL = (168, 156, 132)
ASPHALT = (86, 86, 90)
PAVING = (178, 172, 160)
TRUNK = (90, 64, 40)
CONIFER = (44, 84, 44)
LEAVES = (78, 120, 50)
TIMBER = Palette(wall=(132, 92, 58), trim=(196, 180, 150),
                 roof=(84, 72, 66), glass=(52, 62, 84))
OFFICE = Palette(wall=(222, 224, 226), trim=(196, 200, 206),
                 roof=(150, 152, 156), glass=(70, 110, 160))
CORRUGATED = (130, 134, 132)
CARS = ((190, 40, 50), (40, 80, 170), (230, 200, 60), (60, 140, 80),
        (220, 220, 214), (140, 50, 140), (40, 40, 44))


@dataclass(frozen=True)
class HqParams:
    name: str
    dat: str
    storeys: int = 0           # office block; 0 for the yard
    huts: int = 0              # Nissen huts in the yard
    picnic: bool = False


HQS = [
    HqParams("HQ1", "hq01"),
    HqParams("HQ2", "hq02", huts=1),
    HqParams("HQ3", "hq03", huts=2, picnic=True),
    HqParams("HQ4", "hq04", storeys=4),
    HqParams("HQ5", "hq05", storeys=9),
    HqParams("HQ6", "hq06", storeys=16),
]

# Office block footprint, and the car park in front of it.
BLOCK_S, BLOCK_P = (-1.0, 0.45), 0.62
PARK_S = (0.85, 2.7)


# --- Ground -------------------------------------------------------------------

def ground_quad(model: Model, shader) -> None:
    pts = [FRAME.world(s, p, 0.002)
           for s, p in ((-4.5, -3.0), (4.5, -3.0), (4.5, 3.0), (-4.5, 3.0))]
    add_face(model, pts, (0, 0, 0), outward=FRAME.world(0, 0, -1),
             shader=shader)


def ground_shader(hq: HqParams):
    gravel = np.array(GRAVEL, float)
    asphalt, paving = np.array(ASPHALT, float), np.array(PAVING, float)

    def shader(wx, wy, sx, sy):
        s, p = FRAME.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        edge = outside_distance(DIMS, wx, wy)
        rgb = np.zeros((len(wx), 3))
        paved = np.zeros(len(wx), bool)
        if hq.storeys:
            plaza = (np.abs(p) < BLOCK_P + 0.25) & (s > BLOCK_S[0] - 0.25) & \
                (s < PARK_S[0])
            park = (np.abs(p) < 1.0) & (s >= PARK_S[0]) & (edge > 0.12)
            rgb[plaza] = paving * (0.92 + 0.12 * n[plaza])[:, None]
            rgb[park] = asphalt * (0.92 + 0.12 * n[park])[:, None]
            stall = park & (np.abs((s - PARK_S[0]) / 0.3 % 1 - 0.5) > 0.46) & \
                (np.abs(p) > 0.25)
            rgb[stall] = (226, 226, 220)
            paved = plaza | park
        else:
            drive = (np.abs(p - 0.3) < 0.18) & (s > 0.2)
            yard = np.hypot(s - 0.2, p) < 0.75
            rgb[drive | yard] = gravel * (0.85 + 0.25 * n[drive | yard])[:, None]
            paved = drive | yard
        # Elsewhere the map's own grass shows through.
        return rgb, paved & (edge > 0.0)

    return shader


# --- Parts --------------------------------------------------------------------

def conifer(model, s, p, height=0.7):
    k = height / 0.7
    add_frustum(model, FRAME, s, p, 0.03, 0.03, 0, 0.08, TRUNK, n=6)
    for r, z0, z1 in ((0.18, 0.06, 0.42), (0.14, 0.28, 0.6), (0.09, 0.46, 0.75)):
        add_frustum(model, FRAME, s, p, r * k, 0.0, z0 * k, z1 * k, CONIFER,
                    n=10)


def broadleaf(model, s, p, height=0.6):
    k = height / 0.6
    add_frustum(model, FRAME, s, p, 0.03, 0.025, 0, 0.22 * k, TRUNK, n=6)
    for r0, r1, z0, z1 in ((0.08, 0.2, 0.16, 0.34), (0.2, 0.17, 0.34, 0.48),
                           (0.17, 0.04, 0.48, 0.62)):
        add_frustum(model, FRAME, s, p, r0 * k, r1 * k, z0 * k, z1 * k, LEAVES,
                    n=10, side_shader=speckle_shader(LEAVES))


def fence(model) -> None:
    """Posts and two rails round the yard, just inside its edge."""
    for (ax, ay), (bx, by) in footprint_outline(DIMS, inset=0.1):
        for z in (0.06, 0.13):
            add_beam(model, (ax, ay, z), (bx, by, z), 0.012, (110, 80, 52))
        for t in np.linspace(0, 1, 5)[:-1]:
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            add_beam(model, (x, y, 0.0), (x, y, 0.16), 0.02, (90, 64, 40))


def nissen_hut(model, s, p, length=0.7, r=0.24):
    """A half-round hut of corrugated iron, its axis along `p`."""
    n = 8
    hut = Frame(FRAME.v, origin=FRAME.world(s, p, 0)[:2])
    for k in range(n):
        a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
        q0 = (r * math.cos(a0), r * math.sin(a0) * 0.8)
        q1 = (r * math.cos(a1), r * math.sin(a1) * 0.8)
        quad = [hut.world(-length / 2, q0[0], q0[1]),
                hut.world(length / 2, q0[0], q0[1]),
                hut.world(length / 2, q1[0], q1[1]),
                hut.world(-length / 2, q1[0], q1[1])]
        add_face(model, quad, CORRUGATED, outward=hut.world(0, 0, 0),
                 shader=course_shader(hut, CORRUGATED, 0.03))
    for end in (-length / 2, length / 2):
        ring = [hut.world(end, r * math.cos(math.pi * k / n),
                          r * math.sin(math.pi * k / n) * 0.8)
                for k in range(n + 1)]
        for k in range(1, n - 1, 2):
            add_face(model, [ring[0], ring[k], ring[k + 1],
                             ring[min(k + 2, n)]], (150, 150, 146),
                     outward=hut.world(0, 0, 0.05))
    door = hut.world(length / 2 + 0.003, 0, 0)
    add_block(model, Frame(FRAME.v, origin=door[:2]), 0, 0.006, -0.08, 0.08,
              0, 0.15, (60, 60, 64))


def lorry(model, s, p, colour=(40, 80, 170)):
    fr = Frame(FRAME.u, origin=FRAME.world(s, p, 0)[:2])
    add_block(model, fr, -0.2, 0.08, -0.07, 0.07, 0.04, 0.17, (200, 200, 196))
    add_block(model, fr, 0.08, 0.2, -0.07, 0.07, 0.04, 0.15, colour)
    add_block(model, fr, 0.15, 0.2, -0.065, 0.065, 0.1, 0.14, (60, 70, 90))
    for ds in (-0.14, 0.12):
        add_block(model, fr, ds - 0.03, ds + 0.03, -0.075, 0.075, 0.0, 0.05,
                  (30, 30, 32))


def car(model, s, p, colour):
    fr = Frame(FRAME.v, origin=FRAME.world(s, p, 0)[:2])
    add_block(model, fr, -0.1, 0.1, -0.045, 0.045, 0.015, 0.06, colour)
    add_block(model, fr, -0.05, 0.05, -0.04, 0.04, 0.06, 0.09,
              tuple(int(c * 0.7) for c in colour))


def picnic_table(model, s, p):
    add_block(model, FRAME, s - 0.1, s + 0.1, p - 0.05, p + 0.05, 0.08, 0.1,
              (150, 112, 70))
    for dp in (-0.09, 0.09):
        add_block(model, FRAME, s - 0.1, s + 0.1, p + dp - 0.02, p + dp + 0.02,
                  0.04, 0.055, (150, 112, 70))
    for ds in (-0.07, 0.07):
        add_block(model, FRAME, s + ds - 0.01, s + ds + 0.01, p - 0.04,
                  p + 0.04, 0.0, 0.08, (110, 80, 52))


def flagpole(model, s, p, colour=(40, 80, 170)):
    add_frustum(model, FRAME, s, p, 0.01, 0.008, 0.0, 0.7, (200, 200, 204),
                n=6)
    add_block(model, FRAME, s - 0.005, s + 0.005, p + 0.01, p + 0.17, 0.56,
              0.67, colour)


# --- Yard (HQ1..HQ3) ----------------------------------------------------------

def yard(model, hq: HqParams):
    fence(model)
    office = Frame(FRAME.u, origin=FRAME.world(-0.35, -0.25, 0)[:2])
    gabled_block(model, office, -0.3, 0.3, 0.22, 1, TIMBER, pitch=0.14,
                 door=True, stepped=False, bays=2)
    lorry(model, 0.55, 0.35)
    flagpole(model, 0.45, -0.75)
    for k in range(hq.huts):
        nissen_hut(model, -0.35 - 0.75 * k, 0.65)
    if hq.picnic:
        picnic_table(model, 1.1, -0.6)
        lorry(model, 0.9, 0.7, colour=(170, 50, 40))
    # Woods round the yard, thinning out towards the drive.
    for k, (s, p) in enumerate(((-2.9, 0.0), (-2.4, -0.55), (-2.3, 0.6),
                                (-1.6, -1.15), (-1.7, 1.2), (-1.2, 0.0),
                                (-0.6, -1.5), (-0.4, 1.55), (0.3, -1.75),
                                (0.4, 1.7), (1.3, -1.2), (2.1, -0.5),
                                (2.4, 0.9), (1.5, 1.35), (2.9, 0.0),
                                (-2.0, -0.1), (-1.0, -0.9))):
        if (k + len(hq.name)) % 3 == 0:
            broadleaf(model, s, p, 0.5 + 0.15 * (k % 3))
        else:
            conifer(model, s, p, 0.55 + 0.12 * (k % 4))


# --- Office block (HQ4..HQ6) --------------------------------------------------

def office_block(model, hq: HqParams):
    s0, s1 = BLOCK_S
    w = BLOCK_P
    top = hq.storeys * STOREY + 0.06
    add_block(model, FRAME, s0, s1, -w, w, 0.0, top, OFFICE.wall,
              side_shader=speckle_shader(OFFICE.wall))
    add_block(model, FRAME, s0 - 0.02, s1 + 0.02, -w - 0.02, w + 0.02, top,
              top + 0.04, OFFICE.trim)
    bays_s = max(3, round((s1 - s0) / 0.22))
    bays_p = max(3, round(2 * w / 0.22))
    for a, b, inward, bays, door in (((s1, -w), (s1, w), (-1, 0), bays_p, True),
                                     ((s0, w), (s0, -w), (1, 0), bays_p, False),
                                     ((s0, -w), (s1, -w), (0, 1), bays_s, False),
                                     ((s1, w), (s0, w), (0, -1), bays_s, False)):
        facade(model, FRAME, a, b, inward, OFFICE, storeys=hq.storeys,
               bays=bays, door=door)
    # Stair tower with the company's blue stripe.
    add_block(model, FRAME, s0 + 0.2, s0 + 0.5, w, w + 0.18, 0.0, top + 0.2,
              OFFICE.wall, side_shader=speckle_shader(OFFICE.wall))
    add_block(model, FRAME, s0 + 0.3, s0 + 0.4, w + 0.18, w + 0.185, 0.1,
              top + 0.1, (40, 80, 170))
    # Name board on the roof edge, facing the camera.
    add_block(model, FRAME, s1 - 0.02, s1, -0.4, 0.4, top + 0.04, top + 0.16,
              (40, 80, 170))
    # Entrance canopy.
    add_block(model, FRAME, s1, s1 + 0.25, -0.3, 0.3, 0.2, 0.23, OFFICE.trim)
    for dp in (-0.27, 0.27):
        add_block(model, FRAME, s1 + 0.22, s1 + 0.24, dp - 0.01, dp + 0.01,
                  0.0, 0.2, (90, 94, 100))
    # Roof plant.
    add_block(model, FRAME, s0 + 0.15, s0 + 0.55, -0.4, -0.05, top + 0.04,
              top + 0.16, (180, 182, 186))
    add_frustum(model, FRAME, s0 + 0.9, -0.3, 0.1, 0.0, top + 0.04, top + 0.16,
                (230, 230, 232), n=10)
    add_frustum(model, FRAME, s0 + 0.9, -0.3, 0.012, 0.012, top + 0.04,
                top + 0.08, (120, 120, 124), n=6)
    if hq.storeys >= 16:
        for k in range(4):
            s = s0 + 0.2 + 0.28 * k
            add_block(model, FRAME, s - 0.11, s + 0.11, 0.05, 0.5, top + 0.06,
                      top + 0.1, (40, 60, 120))
        add_frustum(model, FRAME, s1 - 0.25, -0.35, 0.015, 0.01, top + 0.04,
                    top + 0.6, (200, 200, 204), n=6)


def car_park(model, hq: HqParams):
    k = 0
    for i, s in enumerate(np.arange(PARK_S[0] + 0.15, PARK_S[1] - 0.1, 0.3)):
        for side in (-1, 1):
            if (i * 2 + (side > 0) + len(hq.name)) % 3 == 0:
                continue
            car(model, s, side * 0.62, CARS[k % len(CARS)])
            k += 1
    for s in (PARK_S[0] + 0.2, PARK_S[1] - 0.1):
        for side in (-1, 1):
            conifer(model, s, side * 1.15, 0.5)
    for s, p in ((-2.6, 0.0), (-2.0, -0.6), (-2.0, 0.6), (-1.0, 1.25),
                 (-1.0, -1.25), (0.2, 1.5), (0.2, -1.5)):
        broadleaf(model, s, p, 0.5)
    flagpole(model, PARK_S[0] - 0.1, 0.85)


def build(hq: HqParams) -> Model:
    model = Model()
    ground_quad(model, ground_shader(hq))
    if hq.storeys:
        office_block(model, hq)
        car_park(model, hq)
    else:
        yard(model, hq)
    return model


def levels(hq: HqParams) -> int:
    return 4 + hq.storeys // 6


def bake_pakset() -> None:
    for hq in HQS:
        lines = bake_tiles(build(hq), DIMS, HQ_DIR / f"{hq.dat}_hex.png",
                           levels=levels(hq))
        rewrite_images(HQ_DIR / f"{hq.dat}.dat", {hq.name: lines})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write all six on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview([build(hq) for hq in HQS], DIMS, a.preview,
                levels=max(levels(hq) for hq in HQS))
    else:
        bake_pakset()
