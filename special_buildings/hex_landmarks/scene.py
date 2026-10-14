"""3D models of the pak128 one-tile monuments and attractions for the
hex grid.

Forty-eight landmarks, each its own `.dat` under
`special_buildings/monuments`, `city` and `landscape`: statues on
plinths, churches, towers, a mosque and a cathedral, an observatory,
lighthouses, a windmill, a pagoda...  `LANDMARKS` maps each building's
name to a function that builds it in the frame of the side it faces;
the parts they share (a plaza, a plinth, a figure, a church, a dome,
trees) are above it.  A building with one layout faces SE, so it
shows two sides as pak128's did; one with two faces S and SE.  Winter,
where the `.dat` has it, puts snow on roofs and lawns.

    python3 -m special_buildings.hex_landmarks.scene
    python3 -m special_buildings.hex_landmarks.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed.blocks import FACES
from tools.threed.building import composite, ground_cell, render_tiles
from tools.threed.building_kit import (
    AMBIENT, STOREY, Palette, add_beam, bake_rotations, facade,
    gabled_block, rewrite_images, speckle_shader, wall_quad)
from tools.threed.hex_synth import HexGeom, hash_noise01
from tools.threed.render import Model
from tools.threed.solids import (
    Frame, add_block, add_face, add_frustum, add_roof)
from tools.threed.way import edge_midpoint

SPECIAL_DIR = Path(__file__).resolve().parent.parent
FOLDERS = ("monuments", "city", "landscape")

SNOW = (238, 240, 244)
PAVING = (176, 172, 162)
LAWN = (96, 140, 62)
DARK_STONE = (58, 56, 62)
STONE = (196, 190, 176)
SANDSTONE = (214, 192, 150)
BRONZE = (150, 116, 70)
VERDIGRIS = (96, 160, 140)
GOLD = (222, 186, 70)
WHITE = (236, 236, 232)
RED = (190, 46, 40)
SLATE = (84, 86, 96)
TILES = (160, 70, 50)
GLASS = (60, 72, 92)
LEAF = (64, 112, 52)
CONIFER = (40, 92, 54)
TRUNK = (84, 60, 42)
Z = 64 / 90         # squash for round things: z draws at 90 px a unit


class Look:
    """What a builder needs besides the frame: the season."""

    def __init__(self, snow: bool):
        self.snow = snow

    def roof(self, colour):
        return SNOW if self.snow else colour

    def lawn(self, colour=LAWN):
        return tuple(int(c * 0.3 + s * 0.7) for c, s in zip(colour, SNOW)) \
            if self.snow else colour


# --- Shared parts -------------------------------------------------------------

def plaza(model, fr: Frame, look: Look, *, lawn_ring=0.62, paving=PAVING):
    """Paving round the centre, lawn towards the tile's edge."""
    pave = np.array(paving, float)
    green = np.array(look.lawn(), float)

    def shader(wx, wy, sx, sy):
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        r = np.hypot(wx - fr.origin[0], wy - fr.origin[1])
        rgb = pave * (0.9 + 0.14 * n)[:, None]
        g = r > lawn_ring
        rgb[g] = green * (0.88 + 0.22 * n[g])[:, None]
        return rgb, np.ones(len(wx), bool)

    pts = [fr.world(s, p, 0.003) for s, p in
           ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    add_face(model, pts, (0, 0, 0), outward=fr.world(0, 0, -1), shader=shader)


def lawn(model, fr: Frame, look: Look):
    plaza(model, fr, look, lawn_ring=0.0)


def plinth(model, fr: Frame, w, h, colour=DARK_STONE, s=0.0, p=0.0):
    add_block(model, fr, s - w, s + w, p - w, p + w, 0.0, h, colour,
              side_shader=speckle_shader(colour))
    add_block(model, fr, s - w - 0.02, s + w + 0.02, p - w - 0.02, p + w + 0.02,
              h, h + 0.02, STONE)


def figure(model, fr: Frame, s, p, z, h, colour, *, pose="stand"):
    """A standing figure `h` tall from `z`: legs, a coat, arms, a head.
    `pose` adds a raised arm (`torch`), a sword (`knight`) or makes it
    a bust on a column (`bust`)."""
    if pose == "bust":
        add_frustum(model, fr, s, p, 0.05, 0.05, z, z + h * 0.4, STONE, n=8)
        add_block(model, fr, s - 0.07, s + 0.07, p - 0.1, p + 0.1,
                  z + h * 0.4, z + h * 0.62, colour)
        add_frustum(model, fr, s, p, 0.06, 0.055, z + h * 0.62, z + h * 0.85,
                    colour, n=10)
        return
    w = h * 0.14
    add_block(model, fr, s - w * 0.6, s + w * 0.6, p - w, p + w, z,
              z + h * 0.42, colour)
    add_frustum(model, fr, s, p, w * 1.3, w * 0.9, z + h * 0.42, z + h * 0.8,
                colour, n=8)
    add_frustum(model, fr, s, p, w * 0.6, w * 0.55, z + h * 0.8, z + h * 0.97,
                colour, n=8)
    if pose == "torch":
        add_beam(model, fr.world(s, p - w, z + h * 0.75),
                 fr.world(s + 0.02, p - w * 1.3, z + h * 1.25), w * 0.6, colour)
        add_frustum(model, fr, s + 0.02, p - w * 1.3, w * 0.8, w * 0.4,
                    z + h * 1.25, z + h * 1.38, GOLD, n=6)
    elif pose == "knight":
        add_beam(model, fr.world(s + w, p + w * 1.2, z + h * 0.5),
                 fr.world(s + w, p + w * 1.2, z + h * 0.05), w * 0.25, STONE)


def round_tree(model, fr: Frame, s, p, h, look: Look):
    add_frustum(model, fr, s, p, 0.02, 0.018, 0.0, h * 0.45, TRUNK, n=6)
    crown = look.lawn(LEAF) if look.snow else LEAF
    r, zc = 0.12 + 0.06 * h, h * 0.65
    for k in range(5):
        a0, a1 = (-math.pi / 2 + math.pi * j / 5 for j in (k, k + 1))
        add_frustum(model, fr, s, p, max(r * math.cos(a0), 0.01),
                    max(r * math.cos(a1), 0.01), zc + r * Z * math.sin(a0),
                    zc + r * Z * math.sin(a1), crown, n=10,
                    side_shader=speckle_shader(crown))


def cone_tree(model, fr: Frame, s, p, h, look: Look):
    add_frustum(model, fr, s, p, 0.02, 0.02, 0.0, h * 0.15, TRUNK, n=6)
    green = look.lawn(CONIFER) if look.snow else CONIFER
    for r, z0, z1 in ((0.12, 0.1, 0.55), (0.09, 0.4, 0.8), (0.06, 0.65, 1.0)):
        add_frustum(model, fr, s, p, r * h / 0.6, 0.0, z0 * h, z1 * h, green,
                    n=10)


def corner_trees(model, fr: Frame, look: Look, kind=cone_tree, h=0.45):
    for s, p in ((-0.55, -0.5), (0.5, 0.55), (-0.55, 0.55), (0.5, -0.5)):
        kind(model, fr, s, p, h, look)


def dome(model, fr: Frame, s, p, z, r, colour, *, n=16, rise=1.0):
    """A hemisphere, squashed to draw round; `rise` scales its height."""
    for k in range(5):
        a0, a1 = math.pi / 2 * k / 5, math.pi / 2 * (k + 1) / 5
        add_frustum(model, fr, s, p, max(r * math.cos(a0), 0.005),
                    max(r * math.cos(a1), 0.005),
                    z + r * Z * rise * math.sin(a0),
                    z + r * Z * rise * math.sin(a1), colour, n=n)


def onion(model, fr: Frame, s, p, z, r, colour, finial=GOLD):
    prof = [(1.0, 0.0), (1.15, 0.35), (1.0, 0.7), (0.6, 1.05), (0.15, 1.35),
            (0.0, 1.5)]
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        add_frustum(model, fr, s, p, max(r * r0, 0.004), max(r * r1, 0.004),
                    z + r * z0, z + r * z1, colour, n=12)
    add_frustum(model, fr, s, p, 0.008, 0.0, z + r * 1.5, z + r * 1.5 + 0.07,
                finial, n=4)


def spire(model, fr: Frame, s, p, z, w, h, colour):
    add_frustum(model, fr, s, p, w * 1.42, 0.0, z, z + h, colour, n=4,
                side_shader=speckle_shader(colour))


def tower(model, fr: Frame, s, p, w, h, pal: Palette, look: Look, *,
          top="spire", top_h=0.4):
    """A square tower `2w` wide and `h` tall, a belfry and a top."""
    add_block(model, fr, s - w, s + w, p - w, p + w, 0.0, h, pal.wall,
              side_shader=speckle_shader(pal.wall))
    for a, b, inward in (((s + w, p - w * 0.5), (s + w, p + w * 0.5), (-1, 0)),
                         ((s - w * 0.5, p - w), (s + w * 0.5, p - w), (0, 1))):
        wall_quad(model, fr, a, b, h - 0.16, h - 0.04, 0.006, GLASS, inward)
    add_block(model, fr, s - w - 0.015, s + w + 0.015, p - w - 0.015,
              p + w + 0.015, h, h + 0.025, pal.trim)
    if top == "spire":
        spire(model, fr, s, p, h + 0.025, w, top_h, look.roof(pal.roof))
    elif top == "onion":
        onion(model, fr, s, p, h + 0.025, w * 0.9, look.roof(pal.roof))
    elif top == "dome":
        dome(model, fr, s, p, h + 0.025, w, look.roof(pal.roof))


def church(model, fr: Frame, pal: Palette, look: Look, *, nave=(-0.55, 0.35),
           w=0.26, storeys=2, tower_at=0.45, tower_w=0.13, tower_h=0.75,
           top="spire", top_h=0.45, aisles=False):
    """A nave along the frame, its door end towards the road, a tower
    before it."""
    s0, s1 = nave
    gabled_block(model, fr, s0, s1, w, storeys, Palette(
        wall=pal.wall, trim=pal.trim, roof=look.roof(pal.roof),
        glass=pal.glass), pitch=0.3, door=False, stepped=False, bays=4)
    if aisles:
        for side in (-1, 1):
            add_block(model, fr, s0 + 0.05, s1 - 0.05, side * w,
                      side * (w + 0.12), 0.0, STOREY, pal.wall,
                      side_shader=speckle_shader(pal.wall))
            add_roof(model, fr, s0 + 0.03, s1 - 0.03, side * (w + 0.14),
                     side * w, STOREY - 0.02, STOREY + 0.1, 0.02,
                     look.roof(pal.roof))
    tower(model, fr, tower_at, 0.0, tower_w, tower_h, pal, look, top=top,
          top_h=top_h)
    wall_quad(model, fr, (tower_at + tower_w, -0.05),
              (tower_at + tower_w, 0.05), 0.0, 0.18, 0.01, (90, 60, 40),
              (-1, 0))


def ring_tower(model, fr: Frame, s, p, r0, r1, h, colours, *, bands=6, n=14):
    """A round tower tapering from `r0` to `r1`, in coloured bands."""
    for k in range(bands):
        z0, z1 = h * k / bands, h * (k + 1) / bands
        ra = r0 + (r1 - r0) * k / bands
        rb = r0 + (r1 - r0) * (k + 1) / bands
        add_frustum(model, fr, s, p, ra, rb, z0, z1, colours[k % len(colours)],
                    n=n)


def mast(model, fr: Frame, s, p, base, top, h, *, levels=8):
    """A lattice mast in red and white sections."""
    def corner(i, z):
        r = base + (top - base) * z / h
        return fr.world(s + (-1 if i in (0, 3) else 1) * r,
                        p + (-1 if i in (0, 1) else 1) * r, z)

    for k in range(levels):
        z0, z1 = h * k / levels, h * (k + 1) / levels
        colour = RED if k % 2 else WHITE
        for i in range(4):
            j = (i + 1) % 4
            add_beam(model, corner(i, z0), corner(i, z1), 0.02, colour)
            add_beam(model, corner(i, z1), corner(j, z1), 0.014, colour)
            add_beam(model, corner(i, z0), corner(j, z1), 0.01, colour)


def columns(model, fr: Frame, s, p0, p1, n, h, colour=WHITE, z=0.0, r=0.025):
    for p in np.linspace(p0, p1, n):
        add_frustum(model, fr, s, p, r, r * 0.9, z, z + h, colour, n=8)


# --- Monuments ---------------------------------------------------------------

def monument(top, *, plinth_h=0.2, plinth_w=0.3, trees=cone_tree):
    """A plinth on a plaza with `top(model, fr, z, look)` on it."""
    def build(model, fr, look):
        plaza(model, fr, look)
        corner_trees(model, fr, look, trees)
        plinth(model, fr, plinth_w, plinth_h)
        top(model, fr, plinth_h + 0.02, look)
    return build


def fountain_top(model, fr, z, look):
    add_frustum(model, fr, 0, 0, 0.26, 0.26, z, z + 0.02, (90, 140, 190), n=16)
    figure(model, fr, 0, 0, z, 0.32, BRONZE)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        add_frustum(model, fr, 0.18 * math.cos(a), 0.18 * math.sin(a), 0.015,
                    0.0, z, z + 0.12, (180, 210, 236), n=4)


def apple_top(model, fr, z, look):
    dome(model, fr, 0, 0, z + 0.14 * Z, 0.14, RED, rise=1.0)
    for k in range(5):
        a0, a1 = -math.pi / 2 * (k + 1) / 5, -math.pi / 2 * k / 5
        add_frustum(model, fr, 0, 0, max(0.14 * math.cos(a0), 0.01),
                    0.14 * math.cos(a1), z + 0.14 * Z + 0.14 * Z * math.sin(a0),
                    z + 0.14 * Z + 0.14 * Z * math.sin(a1), RED, n=16)
    add_beam(model, fr.world(0, 0, z + 0.27), fr.world(0.02, 0, z + 0.33),
             0.015, TRUNK)


def train_top(model, fr, z, look):
    add_block(model, fr, -0.2, 0.2, -0.06, 0.06, z + 0.02, z + 0.12,
              (220, 220, 214))
    add_block(model, fr, -0.2, 0.2, -0.061, 0.061, z + 0.07, z + 0.1,
              (40, 70, 150))
    add_block(model, fr, 0.15, 0.22, -0.05, 0.05, z + 0.02, z + 0.1,
              (220, 220, 214))


def building_top(colour, dome_c=None):
    def top(model, fr, z, look):
        add_block(model, fr, -0.12, 0.12, -0.12, 0.12, z, z + 0.12, colour)
        if dome_c:
            dome(model, fr, 0, 0, z + 0.12, 0.09, dome_c)
        else:
            add_roof(model, fr, -0.13, 0.13, -0.13, 0.0, z + 0.12, z + 0.2,
                     0.01, look.roof(TILES))
            add_roof(model, fr, -0.13, 0.13, 0.13, 0.0, z + 0.12, z + 0.2,
                     0.01, look.roof(TILES))
    return top


def statue(colour, pose="stand", h=0.5):
    def top(model, fr, z, look):
        figure(model, fr, 0, 0, z, h, colour, pose=pose)
    return top


def screen_top(model, fr, z, look):
    add_block(model, fr, -0.02, 0.02, -0.12, 0.12, z, z + 0.22, WHITE)
    add_block(model, fr, 0.02, 0.025, -0.1, 0.1, z + 0.03, z + 0.2,
              (80, 120, 200))
    figure(model, fr, 0.1, -0.12, z, 0.26, (60, 60, 64))


def roundabout(model, fr, look):
    plaza(model, fr, look, lawn_ring=0.35, paving=(90, 90, 94))
    add_frustum(model, fr, 0, 0, 0.36, 0.36, 0.0, 0.03, (200, 196, 186), n=20)
    add_frustum(model, fr, 0, 0, 0.33, 0.33, 0.03, 0.035, look.lawn(), n=20)
    round_tree(model, fr, 0, 0, 0.8, look)
    for k in range(4):
        a = k * math.pi / 2
        add_beam(model, fr.world(0.7 * math.cos(a), 0.7 * math.sin(a), 0),
                 fr.world(0.7 * math.cos(a), 0.7 * math.sin(a), 0.4), 0.015,
                 DARK_STONE)


def server(model, fr, look):
    plaza(model, fr, look)
    add_block(model, fr, -0.15, 0.15, -0.12, 0.12, 0.0, 0.18, (120, 120, 124))
    add_block(model, fr, -0.1, 0.1, -0.08, 0.08, 0.18, 0.42, (210, 210, 206))
    for k in range(5):
        add_block(model, fr, 0.1, 0.104, -0.06, 0.06, 0.2 + k * 0.04,
                  0.22 + k * 0.04, (60, 160, 90))
    corner_trees(model, fr, look, round_tree, 0.35)


# --- Churches and grand buildings --------------------------------------------

BRICK_CHURCH = Palette(wall=(150, 74, 56), trim=(214, 204, 186),
                       roof=(70, 112, 104), glass=(80, 120, 90))
STONE_CHURCH = Palette(wall=(120, 108, 92), trim=(170, 160, 140),
                       roof=(84, 80, 86), glass=(70, 110, 80))
WHITE_CHURCH = Palette(wall=(236, 232, 222), trim=(200, 194, 180),
                       roof=(56, 60, 70), glass=(56, 66, 84))
BAROQUE = Palette(wall=(232, 214, 166), trim=(246, 238, 214),
                  roof=(100, 150, 120), glass=(56, 66, 84))
TIMBER = Palette(wall=(150, 100, 64), trim=(110, 76, 50), roof=(110, 70, 50),
                 glass=(56, 66, 84))


def church_02(model, fr, look):
    lawn(model, fr, look)
    church(model, fr, BRICK_CHURCH, look, aisles=True)
    corner_trees(model, fr, look, cone_tree, 0.4)


def church_03(model, fr, look):
    lawn(model, fr, look)
    church(model, fr, STONE_CHURCH, look, tower_h=0.6, top_h=0.3)
    cone_tree(model, fr, -0.6, 0.55, 0.45, look)


def church_04(model, fr, look):
    plaza(model, fr, look)
    gabled_block(model, fr, -0.55, 0.3, 0.3, 2, Palette(
        wall=(150, 120, 100), trim=(190, 170, 150),
        roof=look.roof((150, 120, 100)), glass=GLASS), pitch=0.0001,
        stepped=False, bays=3)
    dome(model, fr, -0.12, 0.0, 2 * STOREY + 0.02, 0.3, (80, 110, 112))
    tower(model, fr, 0.4, -0.3, 0.1, 0.65, Palette(
        wall=(150, 120, 100), trim=(190, 170, 150), roof=(80, 110, 112),
        glass=GLASS), look, top="dome")


def church_06(model, fr, look):
    lawn(model, fr, look)
    church(model, fr, WHITE_CHURCH, look, tower_h=0.8, top_h=0.3)


def st_peter(model, fr, look):
    plaza(model, fr, look)
    church(model, fr, Palette(wall=(232, 226, 210), trim=(150, 120, 90),
                              roof=(60, 80, 110), glass=GLASS), look,
           nave=(-0.65, 0.25), w=0.3, tower_at=0.4, tower_w=0.14,
           tower_h=0.7, top_h=0.4, aisles=True)
    tower(model, fr, -0.55, -0.35, 0.08, 0.55, Palette(
        wall=(232, 226, 210), trim=(150, 120, 90), roof=(60, 80, 110),
        glass=GLASS), look, top_h=0.3)


def st_benedict(model, fr, look):
    plaza(model, fr, look)
    church(model, fr, BAROQUE, look, nave=(-0.65, 0.2), w=0.32, storeys=3,
           tower_at=0.35, tower_w=0.15, tower_h=0.95, top="onion")
    for p in (-0.42, 0.42):
        tower(model, fr, -0.1, p, 0.08, 0.8, BAROQUE, look, top="onion")


def secession_chapel(model, fr, look):
    lawn(model, fr, look)
    gabled_block(model, fr, -0.45, 0.25, 0.22, 2, Palette(
        wall=(230, 222, 196), trim=(200, 170, 110),
        roof=look.roof((80, 110, 150)), glass=GLASS), pitch=0.25,
        stepped=False, bays=2, door=True)
    tower(model, fr, -0.1, 0.0, 0.1, 0.65, Palette(
        wall=(230, 222, 196), trim=(200, 170, 110), roof=(80, 110, 150),
        glass=GLASS), look, top="dome")
    corner_trees(model, fr, look, cone_tree, 0.5)


def wooden_church(model, fr, look):
    lawn(model, fr, look)
    church(model, fr, TIMBER, look, nave=(-0.5, 0.25), w=0.22,
           storeys=1, tower_h=0.45, tower_w=0.1, top_h=0.3)
    corner_trees(model, fr, look, cone_tree, 0.55)


def mosque(model, fr, look):
    plaza(model, fr, look, paving=SANDSTONE)
    add_block(model, fr, -0.5, 0.35, -0.42, 0.42, 0.0, 0.36, (232, 214, 170),
              side_shader=speckle_shader((232, 214, 170)))
    facade(model, fr, (0.35, -0.42), (0.35, 0.42), (-1, 0), Palette(
        wall=(232, 214, 170), trim=(246, 238, 214), roof=GOLD, glass=GLASS),
        storeys=1, bays=3, door=True)
    add_frustum(model, fr, -0.08, 0.0, 0.28, 0.28, 0.36, 0.44, (232, 214, 170),
                n=16)
    onion(model, fr, -0.08, 0.0, 0.44, 0.25, look.roof(GOLD))
    for s, p in ((-0.4, -0.3), (-0.4, 0.3), (0.25, -0.3), (0.25, 0.3)):
        dome(model, fr, s, p, 0.36, 0.09, look.roof(GOLD))
    for p in (-0.6, 0.6):
        ring_tower(model, fr, 0.2, p, 0.05, 0.04, 0.9, ((232, 214, 170),))
        onion(model, fr, 0.2, p, 0.9, 0.05, look.roof(GOLD))


def russian_cathedral(model, fr, look):
    plaza(model, fr, look)
    add_block(model, fr, -0.45, 0.4, -0.4, 0.4, 0.0, 0.4, (176, 66, 52),
              side_shader=speckle_shader((176, 66, 52)))
    facade(model, fr, (0.4, -0.4), (0.4, 0.4), (-1, 0), Palette(
        wall=(176, 66, 52), trim=WHITE, roof=GOLD, glass=GLASS),
        storeys=1, bays=3, door=True)
    colours = ((60, 120, 180), (60, 150, 80), GOLD, (200, 60, 50),
               (240, 200, 60))
    spots = ((0.0, 0.0, 0.16, 0.7), (-0.3, -0.25, 0.09, 0.5),
             (-0.3, 0.25, 0.09, 0.5), (0.25, -0.25, 0.09, 0.5),
             (0.25, 0.25, 0.09, 0.55))
    for k, (s, p, r, h) in enumerate(spots):
        add_frustum(model, fr, s, p, r, r, 0.4, h, (176, 66, 52), n=10)
        onion(model, fr, s, p, h, r * 1.1, look.roof(colours[k]))


def justice(model, fr, look):
    plaza(model, fr, look)
    add_block(model, fr, -0.55, 0.4, -0.5, 0.5, 0.0, 0.06, STONE)
    add_block(model, fr, -0.5, 0.2, -0.45, 0.45, 0.06, 0.52, (70, 80, 120))
    columns(model, fr, 0.33, -0.4, 0.4, 7, 0.46, WHITE, z=0.06)
    add_block(model, fr, -0.52, 0.38, -0.48, 0.48, 0.52, 0.6, WHITE)
    add_face(model, [fr.world(0.38, -0.48, 0.6), fr.world(0.38, 0.48, 0.6),
                     fr.world(0.38, 0, 0.76)], WHITE,
             outward=fr.world(0, 0, 0.6))
    add_roof(model, fr, -0.52, 0.38, -0.48, 0.0, 0.6, 0.76, 0.01,
             look.roof(SLATE))
    add_roof(model, fr, -0.52, 0.38, 0.48, 0.0, 0.6, 0.76, 0.01,
             look.roof(SLATE))
    tower(model, fr, -0.15, 0.0, 0.1, 0.95, Palette(
        wall=(70, 80, 120), trim=WHITE, roof=GOLD, glass=GLASS), look,
        top="dome")


def observatory(model, fr, look):
    lawn(model, fr, look)
    add_frustum(model, fr, 0.0, 0.0, 0.32, 0.32, 0.0, 0.3, (190, 160, 130),
                n=20, side_shader=speckle_shader((190, 160, 130)))
    dome(model, fr, 0.0, 0.0, 0.3, 0.33, look.roof((236, 236, 240)), n=20)
    add_block(model, fr, -0.02, 0.02, -0.3, 0.3, 0.33, 0.55, (60, 60, 70))
    corner_trees(model, fr, look, round_tree, 0.4)


def old_gate(model, fr, look):
    lawn(model, fr, look)
    add_block(model, fr, -0.25, 0.25, -0.3, 0.3, 0.0, 0.75, STONE,
              side_shader=speckle_shader(STONE))
    wall_quad(model, fr, (0.25, -0.12), (0.25, 0.12), 0.0, 0.28, 0.01,
              (50, 40, 36), (-1, 0))
    for k in range(4):
        q = -0.3 + 0.2 * k
        add_block(model, fr, 0.2, 0.27, q - 0.04, q + 0.04, 0.75, 0.82, STONE)
    spire(model, fr, 0.0, 0.0, 0.75, 0.22, 0.35, look.roof(SLATE))
    for p in (-0.55, 0.55):
        add_block(model, fr, -0.1, 0.1, p - 0.25, p + 0.25, 0.0, 0.3, STONE,
                  side_shader=speckle_shader(STONE))


def old_house(model, fr, look):
    plaza(model, fr, look)
    gabled_block(model, fr, -0.5, 0.3, 0.32, 3, Palette(
        wall=(214, 176, 80), trim=(150, 70, 50), roof=look.roof(TILES),
        glass=GLASS), pitch=0.45, stepped=True, door=True, bays=3)


def clock_tower(model, fr, look):
    plaza(model, fr, look)
    ring_tower(model, fr, 0.0, 0.0, 0.2, 0.15, 1.1,
               (WHITE, (200, 60, 50)), bands=6)
    add_frustum(model, fr, 0.0, 0.0, 0.2, 0.2, 1.1, 1.22, GOLD, n=14)
    onion(model, fr, 0.0, 0.0, 1.22, 0.12, look.roof((200, 60, 50)))
    corner_trees(model, fr, look, cone_tree, 0.4)


def triumph(model, fr, look):
    plaza(model, fr, look)
    for p in (-0.38, 0.38):
        add_block(model, fr, -0.18, 0.18, p - 0.17, p + 0.17, 0.0, 0.6,
                  SANDSTONE, side_shader=speckle_shader(SANDSTONE))
    add_block(model, fr, -0.18, 0.18, -0.55, 0.55, 0.6, 0.9, SANDSTONE,
              side_shader=speckle_shader(SANDSTONE))
    add_block(model, fr, -0.2, 0.2, -0.57, 0.57, 0.9, 0.94, STONE)
    corner_trees(model, fr, look, cone_tree, 0.45)


def atomium(model, fr, look):
    plaza(model, fr, look)
    steel = (196, 198, 204)
    c = np.array(fr.world(0, 0, 0.75))
    origin = np.array(fr.world(0, 0, 0))
    corners = [(x, y, z) for x in (0.3, -0.3) for y in (0.3, -0.3)
               for z in (0.3, -0.3)] + [(0, 0, 0)]
    pts = [c + np.array(fr.world(x, y, 0)) - origin + np.array((0, 0, z))
           for x, y, z in corners]
    for a in pts[:8]:
        add_beam(model, tuple(c), tuple(a), 0.04, steel)
    add_beam(model, tuple(c), tuple(c - np.array((0, 0, 0.75))), 0.06, steel)
    for a in pts:
        s, p = fr.local(a[0], a[1])
        dome(model, fr, s, p, a[2], 0.1, steel, n=12)
        for k in range(4):
            a0, a1 = -math.pi / 2 * (k + 1) / 4, -math.pi / 2 * k / 4
            add_frustum(model, fr, s, p, max(0.1 * math.cos(a0), 0.005),
                        0.1 * math.cos(a1), a[2] + 0.1 * Z * math.sin(a0),
                        a[2] + 0.1 * Z * math.sin(a1), steel, n=12)


def french_park(model, fr, look):
    green = np.array(look.lawn(), float)
    path = np.array(SANDSTONE, float)
    flowers = np.array((200, 60, 70), float)

    def shader(wx, wy, sx, sy):
        s, p = fr.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = green * (0.88 + 0.2 * n)[:, None]
        paths = (np.abs(s) < 0.06) | (np.abs(p) < 0.06) | \
            (np.abs(np.hypot(s, p) - 0.45) < 0.04)
        rgb[paths] = path
        if not look.snow:
            rgb[~paths & (np.hypot(s, p) < 0.4) & (n > 0.6)] = flowers
        return rgb, np.ones(len(wx), bool)

    pts = [fr.world(s, p, 0.003)
           for s, p in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    add_face(model, pts, (0, 0, 0), outward=fr.world(0, 0, -1), shader=shader)
    for s, p in ((-0.5, -0.5), (0.5, 0.5), (-0.5, 0.5), (0.5, -0.5)):
        cone_tree(model, fr, s, p, 0.35, look)
    add_frustum(model, fr, 0, 0, 0.08, 0.08, 0.0, 0.05, STONE, n=10)


def pagoda(model, fr, look):
    lawn(model, fr, look)
    wood = (150, 60, 40)
    roof = look.roof((80, 70, 66))
    z = 0.0
    for k in range(5):
        w = 0.3 - 0.04 * k
        add_block(model, fr, -w, w, -w, w, z, z + 0.14, wood,
                  side_shader=speckle_shader(wood))
        z += 0.14
        for side in (-1, 1):
            add_roof(model, fr, -w - 0.1, w + 0.1, side * (w + 0.1), 0.0,
                     z - 0.03, z + 0.06, 0.015, roof)
            add_roof(model, fr, side * (w + 0.1), 0.0, -w - 0.1, w + 0.1,
                     z - 0.03, z + 0.06, 0.015, roof)
        z += 0.04
    add_beam(model, fr.world(0, 0, z), fr.world(0, 0, z + 0.25), 0.02, GOLD)
    corner_trees(model, fr, look, round_tree, 0.35)


def manor(model, fr, look):
    lawn(model, fr, look)
    gabled_block(model, fr, -0.45, 0.25, 0.3, 2, Palette(
        wall=(214, 196, 160), trim=(240, 232, 214), roof=look.roof(TILES),
        glass=GLASS), pitch=0.3, stepped=False, door=True, bays=3)
    tower(model, fr, -0.25, -0.42, 0.14, 0.85, Palette(
        wall=(160, 130, 100), trim=(200, 190, 170), roof=TILES, glass=GLASS),
        look, top="spire", top_h=0.3)
    corner_trees(model, fr, look, round_tree, 0.45)


def abbey(model, fr, look):
    lawn(model, fr, look)
    pal = Palette(wall=(176, 100, 70), trim=(220, 210, 190),
                  roof=look.roof(TILES), glass=GLASS)
    gabled_block(model, fr, -0.6, 0.2, 0.28, 2, pal, pitch=0.3, stepped=False,
                 bays=4)
    for p in (-0.35, 0.35):
        tower(model, fr, 0.3, p, 0.1, 0.75, Palette(
            wall=(176, 100, 70), trim=(220, 210, 190), roof=TILES,
            glass=GLASS), look, top="onion")


def ruins(model, fr, look):
    lawn(model, fr, look)
    brick = (150, 80, 60)
    for (s0, s1, p0, p1, h) in ((-0.5, 0.3, -0.35, -0.3, 0.5),
                                (-0.5, -0.45, -0.35, 0.3, 0.4),
                                (0.25, 0.3, -0.35, 0.0, 0.35),
                                (-0.5, 0.0, 0.25, 0.3, 0.25)):
        add_block(model, fr, s0, s1, p0, p1, 0.0, h, brick,
                  side_shader=speckle_shader(brick))
    for s, p in ((0.0, 0.0), (0.2, 0.2), (-0.2, 0.1)):
        add_block(model, fr, s - 0.05, s + 0.05, p - 0.04, p + 0.04, 0.0, 0.04,
                  brick)
    round_tree(model, fr, -0.1, 0.0, 0.5, look)


def lighthouse(colours, base):
    def build(model, fr, look):
        lawn(model, fr, look)
        if base:
            add_block(model, fr, 0.15, 0.5, -0.2, 0.2, 0.0, 0.18, WHITE)
            add_roof(model, fr, 0.13, 0.52, -0.22, 0.0, 0.18, 0.28, 0.01,
                     look.roof(RED))
            add_roof(model, fr, 0.13, 0.52, 0.22, 0.0, 0.18, 0.28, 0.01,
                     look.roof(RED))
        ring_tower(model, fr, -0.1, 0.0, 0.17, 0.11, 1.0, colours, bands=5)
        add_frustum(model, fr, -0.1, 0.0, 0.15, 0.15, 1.0, 1.03, DARK_STONE,
                    n=14)
        add_frustum(model, fr, -0.1, 0.0, 0.08, 0.08, 1.03, 1.15,
                    (240, 230, 160), n=10)
        dome(model, fr, -0.1, 0.0, 1.15, 0.1, look.roof(RED), n=10)
    return build


def tv_tower(modern):
    def build(model, fr, look):
        plaza(model, fr, look)
        if modern:
            ring_tower(model, fr, 0.0, 0.0, 0.14, 0.08, 1.6,
                       ((220, 220, 216),), bands=4)
            for z, r in ((1.2, 0.22), (1.32, 0.18)):
                add_frustum(model, fr, 0, 0, r * 0.7, r, z, z + 0.06,
                            (200, 200, 196), n=16)
                add_frustum(model, fr, 0, 0, r, r * 0.7, z + 0.06, z + 0.1,
                            (60, 80, 110), n=16)
            add_beam(model, fr.world(0, 0, 1.6), fr.world(0, 0, 1.95), 0.03,
                     RED)
        else:
            ring_tower(model, fr, 0.0, 0.0, 0.18, 0.12, 1.5,
                       ((230, 230, 226), (210, 210, 206)), bands=6)
            add_block(model, fr, 0.2, 0.55, -0.4, -0.1, 0.0, 0.16,
                      (180, 180, 176))
    return build


def radio_tower(model, fr, look):
    lawn(model, fr, look)
    mast(model, fr, -0.2, 0.2, 0.1, 0.02, 1.6)
    gabled_block(model, fr, 0.0, 0.5, 0.2, 1, Palette(
        wall=(214, 196, 160), trim=WHITE, roof=look.roof(TILES), glass=GLASS),
        pitch=0.14, stepped=False, door=True, bays=3)
    round_tree(model, fr, -0.5, -0.5, 0.5, look)


def radar(model, fr, look):
    lawn(model, fr, look)
    add_block(model, fr, -0.25, 0.25, -0.25, 0.25, 0.0, 0.25, (176, 172, 162))
    add_beam(model, fr.world(0, 0, 0.25), fr.world(0, 0, 0.55), 0.06,
             DARK_STONE)
    c = np.array(fr.world(0, 0, 0.62))
    tilt = math.radians(40)
    ring = []
    for k in range(16):
        a = 2 * math.pi * k / 16
        x, y = 0.38 * math.cos(a), 0.38 * math.sin(a)
        ring.append(c + np.array(fr.world(x * math.cos(tilt), y, 0)) -
                    np.array(fr.world(0, 0, 0)) +
                    np.array((0, 0, 0.08 + x * math.sin(tilt))))
    for k in range(16):
        add_face(model, [tuple(c), tuple(ring[k]), tuple(ring[(k + 1) % 16])],
                 (226, 226, 222), outward=tuple(c + np.array((0, 0, -1))))
    corner_trees(model, fr, look, round_tree, 0.4)


def futuristic(model, fr, look):
    plaza(model, fr, look)
    add_frustum(model, fr, 0, 0, 0.25, 0.04, 0.0, 1.8, (236, 236, 240), n=4)
    add_frustum(model, fr, 0, 0, 0.26, 0.26, 0.0, 0.05, (60, 70, 90), n=4)


def windmill(model, fr, look):
    lawn(model, fr, look)
    add_frustum(model, fr, 0, 0, 0.22, 0.15, 0.0, 0.65, (230, 226, 214), n=8,
                side_shader=speckle_shader((230, 226, 214)))
    add_frustum(model, fr, 0, 0, 0.17, 0.0, 0.65, 0.85,
                look.roof((110, 70, 50)), n=8)
    hub = fr.world(0.22, 0, 0.7)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        tip = fr.world(0.24, 0.55 * math.cos(a), 0.7 + 0.55 * math.sin(a) * Z)
        add_beam(model, hub, tip, 0.02, (110, 80, 60))
        mid = fr.world(0.25, 0.32 * math.cos(a), 0.7 + 0.32 * math.sin(a) * Z)
        add_beam(model, mid, tip, 0.08, (220, 214, 200))


LANDMARKS = {
    # monuments
    "DenkFlor": monument(fountain_top),
    "denkforum": monument(statue(SANDSTONE, h=0.65), plinth_h=0.08,
                          plinth_w=0.18),
    "DenkGeorg": monument(building_top((70, 90, 150)), trees=cone_tree),
    "DenkHajo": monument(statue((40, 40, 44), h=0.4), plinth_h=0.05,
                         plinth_w=0.35, trees=round_tree),
    "DenkOwen": monument(statue((200, 150, 120), h=0.3), plinth_w=0.32),
    "DenkPatrick": monument(apple_top, plinth_h=0.12, trees=round_tree),
    "DenkRaven": monument(train_top),
    "DenkSeth": monument(screen_top),
    "DenkTomas": monument(statue(WHITE, h=0.5), plinth_h=0.3, plinth_w=0.08),
    "denktrack": monument(statue((150, 150, 156), pose="knight", h=0.55),
                          plinth_h=0.08, plinth_w=0.16),
    "DenkTrikky": monument(building_top(WHITE, dome_c=(220, 220, 220))),
    "DenkVM": monument(building_top((70, 120, 90))),
    "DenkVolker": monument(building_top(WHITE, dome_c=GOLD)),
    "rmax_DenkManualTeam": monument(statue(VERDIGRIS, pose="torch", h=0.6),
                                    plinth_h=0.06, plinth_w=0.2),
    "rmax_dictator_statue": monument(statue(VERDIGRIS, h=0.65), plinth_h=0.1,
                                     plinth_w=0.16),
    "rmax_fabio_bust": monument(statue(GOLD, pose="bust", h=0.5),
                                plinth_h=0.06, plinth_w=0.2),
    "roundabout": roundabout,
    "WernerServer": server,
    # city attractions
    "CHURCH_02": church_02,
    "CHURCH_03": church_03,
    "CHURCH_04": church_04,
    "CHURCH_06": church_06,
    "CUR_01_128_JH": atomium,
    "french_park_1": french_park,
    "JUSTICE": justice,
    "OBSERVATORY": observatory,
    "Old_gate": old_gate,
    "OLD_HOUSE_0": old_house,
    "rmax_clock_tower": clock_tower,
    "rmax_mosque": mosque,
    "Russian_Cathedral": russian_cathedral,
    "st_benedict_church": st_benedict,
    "ST_PETER": st_peter,
    "TRIUMPH": triumph,
    # landscape attractions
    "ABBYS_0": abbey,
    "CIVILIAN_RADAR": radar,
    "FUTURISTIC_TOWER_0": futuristic,
    "HOUSE_RUINS_0": ruins,
    "Lighthouse_0": lighthouse(((236, 236, 232), (230, 210, 120)), True),
    "Lighthouse_1": lighthouse(((236, 236, 232), RED), False),
    "Pagoda01": pagoda,
    "RADIO_TOWER_0": radio_tower,
    "Secession_Chapel": secession_chapel,
    "SMALL_MANOR": manor,
    "TV_TOWER_0": tv_tower(False),
    "TV_TOWER_1": tv_tower(True),
    "Windmill": windmill,
    "WOODEN_CHURCH": wooden_church,
}


# --- Bake ---------------------------------------------------------------------

def buildings():
    """`(dat, name, layouts, seasons)` of every one-tile building here."""
    out = []
    for folder in FOLDERS:
        for dat in sorted((SPECIAL_DIR / folder).glob("*.dat")):
            text = dat.read_text(errors="replace")
            for block in re.split(r"(?im)^\s*obj\s*=", text)[1:]:
                if not block.strip().lower().startswith("building"):
                    continue
                name = re.search(r"(?im)^\s*name\s*=\s*(\S+)", block).group(1)
                if name not in LANDMARKS:
                    continue
                dims = re.search(r"(?im)^\s*dims\s*=\s*([\d, ]+)", block)
                parts = [int(x) for x in dims.group(1).split(",")] if dims \
                    else [1, 1]
                keys = re.findall(r"(?im)^\s*backimage((?:\[\d+\])+)", block)
                seasons = 1 + max((int(re.findall(r"\d+", k)[5])
                                   for k in keys if k.count("[") >= 6),
                                  default=0)
                out.append((dat, name, parts[2] if len(parts) > 2 else 1,
                            seasons))
    return out


def faces(layouts: int):
    return ("SE",) if layouts == 1 else FACES[:layouts]


def model_of(name, face, snow=False) -> Model:
    model = Model()
    LANDMARKS[name](model, Frame(edge_midpoint(face)), Look(snow))
    return model


def bake_pakset() -> None:
    for dat, name, layouts, seasons in buildings():
        png = dat.with_name(f"{dat.stem}_hex.png")
        lines = []
        for season in range(seasons):
            stem = png.stem if season == 0 else f"{png.stem}_winter"
            out = png.with_name(f"{stem}.png")
            got = bake_rotations([model_of(name, f, season == 1)
                                  for f in faces(layouts)], out)
            lines += [re.sub(r"\]\[0\]=", f"][{season}]=", line, count=1)
                      for line in got]
        rewrite_images(dat, {name: lines})


def preview(out: Path) -> None:
    grass = ground_cell(HexGeom())
    names = list(LANDMARKS)
    cells = [composite(render_tiles(model_of(n, "SE"), (1, 1),
                                    ambient=AMBIENT), grass) for n in names]
    w = max(c.width for c in cells)
    h = max(c.height for c in cells)
    cols = 8
    sheet = Image.new("RGBA", (w * cols, h * ((len(cells) + cols - 1) // cols)))
    for k, c in enumerate(cells):
        sheet.alpha_composite(c, ((k % cols) * w,
                                  (k // cols) * h + h - c.height))
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write every landmark facing SE on grass here "
                         "instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview(a.preview)
    else:
        bake_pakset()
