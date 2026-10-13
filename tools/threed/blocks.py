"""One-tile buildings made of boxes, and their bake.

Many pak128 buildings are a box or two in a period style: a number of
storeys over a footprint, a palette, a roof (flat, glazed, gabled,
hipped or north-light), window bands and a parapet.  `Block` describes
one box in the frame of the building's front, `Building` a one-tile
building as its blocks plus a function for the rest, and
`bake_catalogue` bakes a list of them, each layout `l` facing
`FACES[l]` (S, SE, N, NW, NE, SW as `ribi_t::layout_to_ribi`); a
building with one layout faces SE, so it shows two sides as pak128's
square art did.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from .building import composite, ground_cell, render_tiles
from .building_kit import (
    AMBIENT, STOREY, Palette, bake_rotations, facade, gabled_block,
    rewrite_images, speckle_shader, wall_quad)
from .factory_kit import ground_shader, sawtooth_roof
from .hex_synth import HexGeom
from .render import Model
from .solids import Frame, add_block, add_face, add_roof, add_solid
from .way import edge_midpoint

# Layout -> the hex side a one-tile building faces (ribi_t::layout_to_ribi).
FACES = ("S", "SE", "N", "NW", "NE", "SW")

APRON = (178, 176, 168)
ROOF_GLASS = (70, 168, 190)
WHITE = (236, 236, 232)
DARK = (50, 50, 54)


@dataclass(frozen=True)
class Block:
    s0: float
    s1: float
    w: float                    # half width across the frame
    storeys: int
    pal: Palette
    roof: str = "flat"          # flat, glazed, gable, hip, mansard, sawtooth
    bands: bool = False         # coloured bands at each floor
    parapet: str | None = None  # None, "plain", "chequer"
    door: bool = False
    pitch: float = 0.18


@dataclass
class Building:
    name: str                   # the .dat object
    stem: str                   # .dat file stem
    layouts: int
    blocks: list[Block] = field(default_factory=list)
    extras: Callable | None = None
    ground: tuple[int, int, int] = APRON


# --- Parts --------------------------------------------------------------------

def apron(model, fr: Frame, colour=APRON):
    pts = [fr.world(s, p, 0.003)
           for s, p in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    add_face(model, pts, (0, 0, 0), outward=fr.world(0, 0, -1),
             shader=ground_shader(colour, grain=0.1))


def block(model, fr: Frame, b: Block):
    top = b.storeys * STOREY + 0.04
    pal = b.pal
    if b.roof in ("gable", "sawtooth"):
        if b.roof == "gable":
            gabled_block(model, fr, b.s0, b.s1, b.w, b.storeys, pal,
                         pitch=b.pitch, door=b.door, stepped=False)
            return
        add_block(model, fr, b.s0, b.s1, -b.w, b.w, 0.0, top, pal.wall,
                  side_shader=speckle_shader(pal.wall))
        sawtooth_roof(model, fr, b.s0, b.s1, -b.w, b.w, top, pal, teeth=3,
                      glass=pal.glass)
    else:
        add_block(model, fr, b.s0, b.s1, -b.w, b.w, 0.0, top, pal.wall,
                  side_shader=speckle_shader(pal.wall))
    walls = (((b.s1, -b.w), (b.s1, b.w), (-1, 0)),
             ((b.s0, b.w), (b.s0, -b.w), (1, 0)),
             ((b.s0, -b.w), (b.s1, -b.w), (0, 1)),
             ((b.s1, b.w), (b.s0, b.w), (0, -1)))
    for k, (a, c, inward) in enumerate(walls):
        bays = max(1, round(math.dist(a, c) / 0.2))
        if b.bands:
            for st in range(b.storeys):
                z = st * STOREY + 0.04
                wall_quad(model, fr, a, c, z + 0.06, z + 0.14, 0.006,
                          pal.glass, inward)
                wall_quad(model, fr, a, c, z + 0.17, z + 0.22, 0.008,
                          pal.trim, inward)
        else:
            facade(model, fr, a, c, inward, pal, storeys=b.storeys,
                   bays=bays, door=b.door and k == 0)
    if b.roof == "hip":
        hip(model, fr, b.s0, b.s1, b.w, top, b.pitch, pal.roof)
    elif b.roof == "mansard":
        mansard(model, fr, b, top)
    elif b.roof == "glazed":
        add_block(model, fr, b.s0 + 0.03, b.s1 - 0.03, -b.w + 0.03,
                  b.w - 0.03, top, top + 0.012, pal.roof)
        for q in np.linspace(-b.w + 0.1, b.w - 0.1, 3):
            add_roof(model, fr, b.s0 + 0.08, b.s1 - 0.08, q - 0.06, q + 0.06,
                     top + 0.012, top + 0.05, 0.006, ROOF_GLASS)
    elif b.roof == "flat":
        add_block(model, fr, b.s0 + 0.02, b.s1 - 0.02, -b.w + 0.02,
                  b.w - 0.02, top, top + 0.012, pal.roof)
    if b.parapet:
        parapet(model, fr, b, top, chequer=b.parapet == "chequer")


def hip(model, fr: Frame, s0, s1, w, z, rise, colour):
    o = 0.03
    r0, r1 = s0 + min(w, (s1 - s0) / 2), s1 - min(w, (s1 - s0) / 2)
    e = [fr.world(s0 - o, -w - o, z), fr.world(s1 + o, -w - o, z),
         fr.world(s1 + o, w + o, z), fr.world(s0 - o, w + o, z)]
    r = [fr.world(r0, 0, z + rise), fr.world(r1, 0, z + rise)]
    inside = fr.world((s0 + s1) / 2, 0, z)
    sh = speckle_shader(colour)
    for face in ([e[0], e[1], r[1], r[0]], [e[2], e[3], r[0], r[1]],
                 [e[1], e[2], r[1]], [e[3], e[0], r[0]]):
        add_face(model, face, colour, outward=inside, shader=sh)


def mansard(model, fr: Frame, b: Block, top):
    """A steep lower slope with dormers, a low hipped cap above it."""
    inset, h = 0.1, 0.2
    ring0 = [(b.s0 - 0.02, -b.w - 0.02), (b.s1 + 0.02, -b.w - 0.02),
             (b.s1 + 0.02, b.w + 0.02), (b.s0 - 0.02, b.w + 0.02)]
    ring1 = [(b.s0 + inset, -b.w + inset), (b.s1 - inset, -b.w + inset),
             (b.s1 - inset, b.w - inset), (b.s0 + inset, b.w - inset)]
    add_solid(model, [fr.world(s, p, top) for s, p in ring0],
              [fr.world(s, p, top + h) for s, p in ring1], b.pal.roof,
              side_shader=speckle_shader(b.pal.roof))
    hip(model, fr, b.s0 + inset, b.s1 - inset, b.w - inset, top + h,
        b.pitch * 0.5, b.pal.roof)
    # Dormers on the front and `-w` slopes, the two the camera sees on a
    # building facing SE; turned to another face, it shows bare slopes.
    for (a, c, inward) in (((b.s1, -b.w), (b.s1, b.w), (-1, 0)),
                           ((b.s0, -b.w), (b.s1, -b.w), (0, 1))):
        n = max(1, round(math.dist(a, c) / 0.22))
        for k in range(n):
            t = (k + 0.5) / n
            ds, dp = a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t
            ds += inward[0] * 0.06
            dp += inward[1] * 0.06
            add_block(model, fr, ds - 0.035, ds + 0.035, dp - 0.035,
                      dp + 0.035, top + 0.04, top + 0.13, b.pal.trim)
            add_block(model, fr, ds - 0.025 - inward[0] * 0.01,
                      ds + 0.025 - inward[0] * 0.01,
                      dp - 0.025 - inward[1] * 0.01,
                      dp + 0.025 - inward[1] * 0.01, top + 0.055,
                      top + 0.115, b.pal.glass)


def parapet(model, fr: Frame, b: Block, top, *, chequer):
    edges = (((b.s0, -b.w), (b.s1, -b.w)), ((b.s1, -b.w), (b.s1, b.w)),
             ((b.s1, b.w), (b.s0, b.w)), ((b.s0, b.w), (b.s0, -b.w)))
    for a, c in edges:
        n = max(2, round(math.dist(a, c) / 0.06))
        for k in range(n):
            t0, t1 = k / n, (k + 1) / n
            s0, s1 = sorted(a[0] + (c[0] - a[0]) * t for t in (t0, t1))
            p0, p1 = sorted(a[1] + (c[1] - a[1]) * t for t in (t0, t1))
            colour = (DARK if k % 2 else WHITE) if chequer else b.pal.trim
            add_block(model, fr, s0 - 0.012, s1 + 0.012, p0 - 0.012,
                      p1 + 0.012, top, top + 0.04, colour)


def canopy(model, fr: Frame, s, w, z, colour):
    """A flat canopy on two posts over the entrance at `s`."""
    add_roof(model, fr, s, s + 0.18, -w, w, z, z, 0.02, colour)
    for q in (-w + 0.03, w - 0.03):
        add_block(model, fr, s + 0.14, s + 0.16, q - 0.01, q + 0.01, 0.0, z,
                  DARK)


# --- Bake ---------------------------------------------------------------------

def build(b: Building, face: str) -> Model:
    model = Model()
    fr = Frame(edge_midpoint(face))
    apron(model, fr, b.ground)
    for blk in b.blocks:
        block(model, fr, blk)
    if b.extras:
        b.extras(model, fr)
    return model


def bake_catalogue(buildings: list[Building], folder: Path) -> None:
    """Bake each building into `<stem>_hex.png` next to its `.dat` in
    `folder` and rewrite its image lines."""
    for b in buildings:
        faces = FACES[:b.layouts] if b.layouts > 1 else ("SE",)
        lines = bake_rotations([build(b, f) for f in faces],
                               folder / f"{b.stem}_hex.png")
        rewrite_images(folder / f"{b.stem}.dat", {b.name: lines})


def preview(buildings: list[Building], out: Path, face="SE", cols=7) -> None:
    """Every building facing `face`, on grass."""
    grass = ground_cell(HexGeom())
    cells = [composite(render_tiles(build(b, face), (1, 1), ambient=AMBIENT),
                       grass) for b in buildings]
    h = max(c.height for c in cells)
    w = cells[0].width
    sheet = Image.new("RGBA", (w * cols, h * math.ceil(len(cells) / cols)))
    for k, c in enumerate(cells):
        sheet.alpha_composite(c, ((k % cols) * w,
                                  (k // cols) * h + h - c.height))
    sheet.save(out)
