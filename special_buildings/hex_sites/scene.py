"""3D models of pak128's multi-tile attractions for the hex grid.

Schools, churches, parks, sports grounds, a market, a circus, castles,
ruins, a rocket pad and a pyramid: every city and landscape attraction
wider than one tile.  Each is a `build_*` function on a
`tools.threed.site.Site`, which fits the plot to the object's footprint
and layout, so one function serves a 2x2 and its rotations alike.
`SITES` maps each object to its `.dat` and builder; the bake writes
`<dat>_hex.png` next to the `.dat` and rewrites its image lines.

    python3 -m special_buildings.hex_sites.scene [NAME ...]
    python3 -m special_buildings.hex_sites.scene --preview out.png [NAME ...]
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed.building import composite, ground_cell, render_tiles
from tools.threed.building_kit import (
    AMBIENT, STOREY, Palette, add_beam, course_shader, facade,
    footprint_outline, gabled_block, rewrite_images, speckle_shader)
from tools.threed.hex_synth import HexGeom
from tools.threed.render import Model
from tools.threed.site import (
    CARS, Site, bake_site, broadleaf, car, conifer, flagpole, flower_bed,
    lamp_post, palm, pond, poplar)
from tools.threed.solids import (
    Frame, add_block, add_face, add_frustum, add_prism, add_solid)

SPECIAL_DIR = Path(__file__).resolve().parent.parent

BRICK = Palette(wall=(168, 82, 60), trim=(222, 206, 180), roof=(120, 60, 46))
SCHOOL = Palette(wall=(176, 96, 72), trim=(226, 214, 192),
                 roof=(150, 196, 178))
CREAM = Palette(wall=(222, 210, 170), trim=(240, 234, 214), roof=(96, 40, 40))
STONE = Palette(wall=(214, 206, 196), trim=(236, 232, 222), roof=(96, 102, 110))
WHITE = Palette(wall=(232, 234, 236), trim=(210, 214, 220), roof=(150, 152, 156),
                glass=(70, 110, 160))
PINK = Palette(wall=(222, 160, 150), trim=(240, 226, 214), roof=(196, 70, 86))
ALPINE = Palette(wall=(232, 214, 176), trim=(150, 100, 60), roof=(120, 92, 70))
TIMBER = Palette(wall=(140, 96, 60), trim=(200, 184, 150), roof=(96, 80, 70))
CASTLE = Palette(wall=(150, 146, 140), trim=(176, 172, 164), roof=(170, 64, 56))
RUIN = Palette(wall=(128, 126, 120), trim=(150, 148, 140), roof=(96, 94, 90))
GRASS = (92, 136, 60)
PITCH = (86, 140, 58)
GRAVEL = (186, 176, 150)
PAVING = (176, 170, 158)
ASPHALT = (86, 86, 90)
SAND = (214, 196, 150)
WHITE_LINE = (236, 236, 230)
CLAY = (190, 96, 60)
GOLD = (220, 180, 60)


# --- Buildings ----------------------------------------------------------------

def block(model, fr, s0, s1, p0, p1, storeys, pal: Palette, *, roof="flat",
          pitch=0.2, door=True, bays=None):
    """A building between `s0..s1` and `p0..p1`, its door to `+s`: a flat
    roof behind a parapet, a gable with the ridge along `s` or `p`, or a
    hip."""
    if roof == "gable":
        f = Frame(fr.u, origin=fr.world(0, (p0 + p1) / 2, 0)[:2])
        return gabled_block(model, f, s0, s1, (p1 - p0) / 2, storeys, pal,
                            pitch=pitch, door=door, stepped=False, bays=bays)
    if roof == "gable_p":
        f = Frame(fr.v, origin=fr.world((s0 + s1) / 2, 0, 0)[:2])
        return gabled_block(model, f, p0, p1, (s1 - s0) / 2, storeys, pal,
                            pitch=pitch, door=door, stepped=False, bays=bays)
    top = storeys * STOREY
    add_block(model, fr, s0, s1, p0, p1, 0.0, top + 0.02, pal.wall,
              side_shader=speckle_shader(pal.wall))
    sides = (((s1, p0), (s1, p1), (-1, 0), door),
             ((s0, p1), (s0, p0), (1, 0), False),
             ((s0, p0), (s1, p0), (0, 1), False),
             ((s1, p1), (s0, p1), (0, -1), False))
    for a, b, inward, d in sides:
        length = math.dist(a, b)
        facade(model, fr, a, b, inward, pal, storeys=storeys,
               bays=bays or max(2, round(length / 0.24)), door=d)
    if roof == "hip":
        e = 0.04
        lo = [fr.world(s, p, top) for s, p in
              ((s0 - e, p0 - e), (s1 + e, p0 - e), (s1 + e, p1 + e),
               (s0 - e, p1 + e))]
        half = min(s1 - s0, p1 - p0) / 2
        if s1 - s0 >= p1 - p0:
            ridge = [fr.world(s0 + half, (p0 + p1) / 2, top + pitch),
                     fr.world(s1 - half, (p0 + p1) / 2, top + pitch)]
            hi = [ridge[0], ridge[1], ridge[1], ridge[0]]
        else:
            ridge = [fr.world((s0 + s1) / 2, p0 + half, top + pitch),
                     fr.world((s0 + s1) / 2, p1 - half, top + pitch)]
            hi = [ridge[0], ridge[0], ridge[1], ridge[1]]
        add_solid(model, lo, hi, pal.roof,
                  side_shader=course_shader(fr, pal.roof))
        return top, top + pitch
    add_block(model, fr, s0 - 0.01, s1 + 0.01, p0 - 0.01, p1 + 0.01, top,
              top + 0.04, pal.trim)
    add_block(model, fr, s0 + 0.03, s1 - 0.03, p0 + 0.03, p1 - 0.03, top,
              top + 0.025, pal.roof)
    return top, top


def tower(model, fr, s, p, w, height, pal: Palette, *, cap="spire",
          cap_h=0.3, round_=False):
    if round_:
        add_frustum(model, fr, s, p, w, w, 0, height, pal.wall, n=12,
                    side_shader=speckle_shader(pal.wall))
    else:
        add_block(model, fr, s - w, s + w, p - w, p + w, 0, height, pal.wall,
                  side_shader=speckle_shader(pal.wall))
        for ds, dp in ((w, 0), (0, w), (-w, 0), (0, -w)):
            for z in np.arange(0.12, height - 0.1, 0.22):
                add_block(model, fr, s + ds * 1.02 - 0.02, s + ds * 1.02 + 0.02,
                          p + dp * 1.02 - 0.02, p + dp * 1.02 + 0.02,
                          z, z + 0.08, pal.glass)
    if cap == "spire":
        add_frustum(model, fr, s, p, w * 1.25, 0.0, height, height + cap_h,
                    pal.roof, n=4 if not round_ else 12,
                    side_shader=course_shader(fr, pal.roof))
    elif cap == "crenel":
        for k in range(8):
            a = 2 * math.pi * k / 8
            add_block(model, fr, s + w * 0.85 * math.cos(a) - 0.03,
                      s + w * 0.85 * math.cos(a) + 0.03,
                      p + w * 0.85 * math.sin(a) - 0.03,
                      p + w * 0.85 * math.sin(a) + 0.03,
                      height, height + 0.06, pal.wall)
    elif cap == "flat":
        add_block(model, fr, s - w - 0.02, s + w + 0.02, p - w - 0.02,
                  p + w + 0.02, height, height + 0.04, pal.roof)


def dome(model, fr, s, p, r, z, colour, *, onion=False):
    prof = [(1.0, 0.0), (0.98, 0.2), (0.9, 0.42), (0.74, 0.62), (0.52, 0.8),
            (0.26, 0.94), (0.0, 1.0)]
    if onion:
        prof = [(1.0, 0.0), (1.12, 0.25), (1.0, 0.5), (0.68, 0.75),
                (0.3, 0.92), (0.0, 1.05)]
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        add_frustum(model, fr, s, p, r * r0, r * r1, z + r * z0 * 0.9,
                    z + r * z1 * 0.9, colour, n=12)


def cross(model, fr, s, p, z, colour=GOLD):
    add_block(model, fr, s - 0.008, s + 0.008, p - 0.008, p + 0.008, z,
              z + 0.14, colour)
    add_block(model, fr, s - 0.008, s + 0.008, p - 0.04, p + 0.04, z + 0.08,
              z + 0.1, colour)


def stall(model, fr, s, p, colour):
    """A market stall under a striped awning."""
    for ds in (-0.08, 0.08):
        for dp in (-0.06, 0.06):
            add_block(model, fr, s + ds - 0.006, s + ds + 0.006,
                      p + dp - 0.006, p + dp + 0.006, 0, 0.16, (90, 70, 50))
    add_block(model, fr, s - 0.08, s + 0.08, p - 0.06, p + 0.06, 0.06, 0.08,
              (150, 112, 70))
    stripe = np.array(colour, float)

    def shader(wx, wy, sx, sy):
        sl, _ = fr.local(wx, wy)
        rgb = np.where(((sl - s) / 0.04 % 2 < 1)[:, None], stripe,
                       np.array((236, 232, 222), float))
        return rgb, np.ones(len(wx), bool)

    add_block(model, fr, s - 0.1, s + 0.1, p - 0.08, p + 0.08, 0.16, 0.18,
              colour, top_shader=shader)


def bench_row(model, fr, s, p, n=3, step=0.25):
    for k in range(n):
        add_block(model, fr, s + k * step - 0.06, s + k * step + 0.06, p - 0.02,
                  p + 0.02, 0.03, 0.045, (110, 80, 52))


def floodlight(model, fr, s, p, height=0.9):
    add_frustum(model, fr, s, p, 0.015, 0.01, 0, height, (150, 150, 156), n=6)
    add_block(model, fr, s - 0.05, s + 0.05, p - 0.02, p + 0.02, height,
              height + 0.06, (236, 236, 220))


def goal(model, fr, s, p, w=0.12, h=0.08):
    for dp in (-w, w):
        add_block(model, fr, s - 0.005, s + 0.005, p + dp - 0.005,
                  p + dp + 0.005, 0, h, (240, 240, 240))
    add_block(model, fr, s - 0.005, s + 0.005, p - w, p + w, h - 0.008, h,
              (240, 240, 240))


def rugby_posts(model, fr, s, p):
    for dp in (-0.07, 0.07):
        add_block(model, fr, s - 0.005, s + 0.005, p + dp - 0.005,
                  p + dp + 0.005, 0, 0.3, (240, 240, 240))
    add_block(model, fr, s - 0.005, s + 0.005, p - 0.07, p + 0.07, 0.1, 0.11,
              (240, 240, 240))


def stand(model, fr, s0, s1, p, depth, colour=(150, 152, 160), rows=4,
          roof=True):
    """A stand along `s`, its seats rising away from the pitch at `p`
    (towards `+p` when `depth` > 0)."""
    sign = 1 if depth > 0 else -1
    d = abs(depth)
    for k in range(rows):
        q0 = p + sign * d * k / rows
        q1 = p + sign * d * (k + 1) / rows
        add_block(model, fr, s0, s1, min(q0, q1), max(q0, q1), 0,
                  0.05 + 0.05 * k, colour if k % 2 else (200, 60, 50))
    if roof:
        add_block(model, fr, s0 - 0.02, s1 + 0.02, min(p, p + sign * d),
                  max(p, p + sign * d), 0.36, 0.38, (210, 212, 216))
        for s in np.linspace(s0, s1, 3):
            add_block(model, fr, s - 0.01, s + 0.01, p + sign * d - 0.01,
                      p + sign * d + 0.01, 0, 0.36, (100, 100, 106))


def tent(model, fr, s, p, r, height, colour):
    stripe = np.array(colour, float)
    white = np.array((240, 236, 228), float)

    def shader(wx, wy, sx, sy):
        sl, pl = fr.local(wx, wy)
        a = np.arctan2(pl - p, sl - s)
        rgb = np.where(((a / (2 * math.pi) * 16) % 2 < 1)[:, None], stripe,
                       white)
        return rgb, np.ones(len(wx), bool)

    add_frustum(model, fr, s, p, r, r, 0, height * 0.35, colour, n=16,
                side_shader=shader)
    add_frustum(model, fr, s, p, r * 1.04, 0.04, height * 0.35, height,
                colour, n=16, side_shader=shader)
    add_frustum(model, fr, s, p, 0.01, 0.01, height, height + 0.12,
                (90, 90, 96), n=6)


def caravan(model, fr, s, p, colour):
    c = Frame(fr.v, origin=fr.world(s, p, 0)[:2])
    add_block(model, c, -0.12, 0.12, -0.05, 0.05, 0.03, 0.13, colour)
    add_block(model, c, -0.13, 0.13, -0.055, 0.055, 0.13, 0.145,
              (230, 228, 220))


def rocks(model, fr, s, p, r, colour=(130, 124, 116), seed=0):
    for k in range(4):
        a = 2 * math.pi * (k + 0.3 * seed) / 4
        rr = r * (0.5 + 0.12 * ((k + seed) % 3))
        add_frustum(model, fr, s + r * 0.7 * math.cos(a),
                    p + r * 0.7 * math.sin(a), rr, rr * 0.4, 0, rr * 0.9,
                    colour, n=6, side_shader=speckle_shader(colour))


def tree_ring(model, fr, site, aspect=1.0, n=10, kind="mix", radius=1.0,
              seed=0):
    """Trees round the edge of the box: `radius` 1 sits on its border."""
    S, P = site.box(aspect)
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        s, p = S * radius * math.cos(a), P * radius * math.sin(a)
        pick = (k + seed) % 3
        if kind == "conifer" or (kind == "mix" and pick == 0):
            conifer(model, fr, s, p, 0.5 + 0.1 * (k % 3))
        elif kind == "poplar":
            poplar(model, fr, s, p, 0.7 + 0.1 * (k % 2))
        else:
            broadleaf(model, fr, s, p, 0.45 + 0.1 * (k % 3))


def parking(model, fr, s0, s1, p0, p1, seed=0):
    k = seed
    for i, s in enumerate(np.arange(s0 + 0.1, s1 - 0.05, 0.22)):
        for p in (p0 + 0.08, p1 - 0.08):
            if (i + k) % 3:
                car(model, fr, s, p, CARS[(i * 2 + k) % len(CARS)])
            k += 1


# --- Ground painters ----------------------------------------------------------

def paint(base_rgb=None, regions=()):
    """A ground shader: `regions` is a list of `(test(s, p), rgb, grain)`
    painted in order over the map's ground (or `base_rgb`)."""
    def fn(s, p, n, edge):
        rgb = np.zeros((len(s), 3))
        keep = np.zeros(len(s), bool)
        if base_rgb is not None:
            rgb[:] = np.array(base_rgb) * (0.88 + 0.2 * n)[:, None]
            keep[:] = True
        for test, colour, grain in regions:
            m = test(s, p) & (edge > 0.04)
            rgb[m] = np.array(colour) * (1 - grain / 2 + grain * n[m])[:, None]
            keep |= m
        return rgb, keep
    return fn


def rect(s0, s1, p0, p1):
    return lambda s, p: (s > s0) & (s < s1) & (p > p0) & (p < p1)


def oval(cs, cp, rs, rp):
    return lambda s, p: ((s - cs) / rs) ** 2 + ((p - cp) / rp) ** 2 < 1


def lines_of(test, width=0.012):
    """The outline of a rectangle test."""
    def t(s, p):
        return test(s, p) & ~test_shrunk(test, s, p, width)
    return t


def test_shrunk(test, s, p, w):
    return test(s - w, p) & test(s + w, p) & test(s, p - w) & test(s, p + w)


def pitch_markings(s0, s1, p0, p1, w=0.012):
    box = rect(s0, s1, p0, p1)

    def t(s, p):
        edge = box(s, p) & ~test_shrunk(box, s, p, w)
        mid = box(s, p) & (np.abs(s - (s0 + s1) / 2) < w / 2 + 0.003)
        circle = np.abs(np.hypot(s - (s0 + s1) / 2, p - (p0 + p1) / 2) -
                        (p1 - p0) * 0.18) < w / 2 + 0.003
        return edge | mid | circle
    return t


# --- City ---------------------------------------------------------------------

def church_05(site: Site) -> Model:
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PAVING, 0.15),
                                  (rect(0.3 * S, S, 0.25 * P, P), ASPHALT, 0.1)]))
    block(m, fr, -0.75 * S, 0.45 * S, -0.95 * P, 0.1 * P, 3, BRICK,
          roof="gable", pitch=0.26)
    add_frustum(m, fr, -0.75 * S, -0.42 * P, 0.5 * P, 0.5 * P, 0, 0.55,
                BRICK.wall, n=12, side_shader=speckle_shader(BRICK.wall))
    dome(m, fr, -0.75 * S, -0.42 * P, 0.5 * P, 0.55, BRICK.roof)
    add_frustum(m, fr, -0.1 * S, -0.42 * P, 0.2, 0.2, 0.66, 0.92,
                BRICK.wall, n=12, side_shader=speckle_shader(BRICK.wall))
    dome(m, fr, -0.1 * S, -0.42 * P, 0.21, 0.92, (176, 74, 60), onion=True)
    cross(m, fr, -0.1 * S, -0.42 * P, 1.14)
    parking(m, fr, 0.35 * S, 0.95 * S, 0.3 * P, 0.95 * P)
    add_frustum(m, fr, 0.75 * S, -0.55 * P, 0.16, 0.16, 0, 0.04,
                (170, 160, 146), n=12)
    add_frustum(m, fr, 0.75 * S, -0.55 * P, 0.03, 0.02, 0.04, 0.18,
                (190, 184, 170), n=6)
    return m


def school(site: Site, pal: Palette, storeys: int, *, wing=True, fields=True,
           cars=True, seed=0) -> Model:
    m, fr = Model(), site.fr
    S, P = site.box(0.6)
    regions = []
    if fields:
        regions.append((rect(0.2 * S, 0.95 * S, -0.95 * P, -0.1 * P), SAND, 0.2))
    if cars:
        regions.append((rect(0.2 * S, 0.95 * S, 0.1 * P, 0.95 * P), ASPHALT,
                        0.1))
    site.ground(m, paint(regions=regions))
    block(m, fr, -0.95 * S, 0.15 * S, -0.95 * P, -0.05 * P, storeys, pal,
          roof="hip", pitch=0.18)
    if wing:
        block(m, fr, -0.95 * S, -0.4 * S, -0.05 * P, 0.95 * P, storeys, pal,
              roof="hip", pitch=0.18, door=False)
    if fields:
        for k in range(3):
            s = 0.4 * S + 0.18 * k
            for dp in (-0.06, 0.06):
                add_beam(m, fr.world(s, -0.5 * P + dp, 0),
                         fr.world(s, -0.5 * P + dp, 0.14), 0.012, (200, 60, 40))
            add_beam(m, fr.world(s, -0.5 * P - 0.06, 0.14),
                     fr.world(s, -0.5 * P + 0.06, 0.14), 0.012, (200, 60, 40))
    if cars:
        parking(m, fr, 0.25 * S, 0.9 * S, 0.15 * P, 0.9 * P, seed)
    broadleaf(m, fr, 0.95 * S, -0.1 * P, 0.5)
    return m


def elementary_school_1(site):
    return school(site, SCHOOL, 2)


def elementary_school_2(site):
    return school(site, BRICK, 3, wing=False, cars=False)


def high_school_1(site):
    pal = Palette(wall=(222, 210, 170), trim=(240, 234, 214), roof=(90, 40, 40))
    m = school(site, pal, 4, seed=2)
    S, P = site.box(0.6)
    for s in np.linspace(-0.3 * S, 0.9 * S, 4):
        poplar(m, site.fr, s, 0.0, 0.75)
    return m


def high_school_2(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PAVING, 0.12)]))
    for s0, s1, p0, p1 in ((-0.9, 0.9, -0.9, -0.5), (-0.9, 0.9, 0.5, 0.9),
                           (-0.9, -0.5, -0.5, 0.5)):
        block(m, fr, s0 * S, s1 * S, p0 * P, p1 * P, 3, STONE, roof="hip",
              pitch=0.14, door=False)
    broadleaf(m, fr, 0.1 * S, 0.0, 0.55)
    return m


def firestation(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.5)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PAVING, 0.12)]))
    pal = Palette(wall=(206, 196, 176), trim=(236, 230, 220), roof=(60, 80, 150))
    block(m, fr, -0.9 * S, 0.2 * S, -0.9 * P, 0.9 * P, 1, pal, door=False)
    for k, dp in enumerate((-0.5, 0.0, 0.5)):
        add_block(m, fr, 0.2 * S, 0.2 * S + 0.006, dp * P - 0.09, dp * P + 0.09,
                  0.0, 0.18, (190, 40, 40))
    tower(m, fr, -0.55 * S, 0.55 * P, 0.1, 0.9, pal, cap="flat")
    return m


def french_garden(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[
        (rect(-S, S, -P, P), GRAVEL, 0.15),
        (lambda s, p: rect(-S, S, -P, P)(s, p) & (np.abs(s) > 0.12) &
         (np.abs(p) > 0.12) & (np.hypot(s, p) > 0.4), GRASS, 0.2)]))
    pond(m, fr, 0, 0, 0.26, 0.26)
    add_frustum(m, fr, 0, 0, 0.04, 0.03, 0.0, 0.18, (200, 196, 186), n=8)
    for qs in (-1, 1):
        for qp in (-1, 1):
            flower_bed(m, fr, qs * 0.55 * S, qp * 0.55 * P, 0.16, 0.16,
                       seed=qs + qp)
            for k in (0.3, 0.85):
                add_frustum(m, fr, qs * k * S, qp * 0.25 * P, 0.07, 0.0, 0.0,
                            0.32, (50, 90, 50), n=8)
                add_frustum(m, fr, qs * 0.25 * S, qp * k * P, 0.07, 0.0, 0.0,
                            0.32, (50, 90, 50), n=8)
    return m


def grass_stadium(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    ps, pp = 0.92 * S, 0.8 * P
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PITCH, 0.15),
                                  (pitch_markings(-ps, ps, -pp, pp), WHITE_LINE,
                                   0.05)]))
    goal(m, fr, -ps, 0)
    goal(m, fr, ps, 0)
    stand(m, fr, -0.6 * S, 0.6 * S, -P, -0.25, rows=3)
    for s in (-S, S):
        for p in (-P, P):
            floodlight(m, fr, s, p)
    return m


def library(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.8)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PAVING, 0.12)]))
    block(m, fr, -0.2 * S, 0.9 * S, -0.9 * P, -0.2 * P, 2, STONE, roof="gable",
          pitch=0.18)
    block(m, fr, -0.9 * S, -0.2 * S, -0.9 * P, 0.0, 2, STONE, roof="gable_p",
          pitch=0.18, door=False)
    for s, p in ((-0.5 * S, 0.5 * P), (0.2 * S, 0.6 * P), (0.6 * S, 0.3 * P),
                 (-0.1 * S, 0.2 * P)):
        broadleaf(m, fr, s, p, 0.5)
    return m


def central_park(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.45)
    site.ground(m, paint(GRASS, regions=[
        (lambda s, p: (np.abs(p - 0.25 * P * np.sin(s * 2.0)) < 0.06), GRAVEL,
         0.15),
        (lambda s, p: (np.abs(s - 0.3 * S * np.sin(p * 2.5)) < 0.05), GRAVEL,
         0.15)]))
    pond(m, fr, 0.25 * S, -0.45 * P, 0.4, 0.22)
    rng = np.random.default_rng(7)
    for k in range(34):
        s, p = rng.uniform(-S, S), rng.uniform(-P, P)
        if abs(p - 0.25 * P * math.sin(s * 2.0)) < 0.15:
            continue
        if ((s - 0.25 * S) / 0.5) ** 2 + ((p + 0.45 * P) / 0.32) ** 2 < 1:
            continue
        (conifer if k % 3 == 0 else broadleaf)(m, fr, s, p,
                                               0.45 + 0.05 * (k % 4))
    return m


def market_place(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), (164, 150, 132), 0.3)]))
    block(m, fr, -0.95 * S, -0.35 * S, -0.9 * P, -0.2 * P, 2, TIMBER,
          roof="gable", pitch=0.2)
    block(m, fr, -0.95 * S, -0.5 * S, 0.3 * P, 0.9 * P, 2, BRICK, roof="gable",
          pitch=0.2, door=False)
    tower(m, fr, -0.75 * S, 0.0, 0.08, 0.5, BRICK, round_=True, cap_h=0.18)
    for k, (s, p) in enumerate(((0.0, -0.5), (0.0, 0.0), (0.0, 0.5),
                                (0.45, -0.5), (0.45, 0.0), (0.45, 0.5))):
        stall(m, fr, s * S, p * P,
              ((190, 50, 50), (60, 110, 170), (230, 190, 60))[k % 3])
    broadleaf(m, fr, 0.8 * S, 0.8 * P, 0.55)
    return m


def circus(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), SAND, 0.2)]))
    site.fence(m, colour=(40, 40, 44), height=0.1, posts=6)
    tent(m, fr, -0.2 * S, 0.0, 0.5 * min(S, P) + 0.1, 0.55, (196, 40, 50))
    for k, (s, p) in enumerate(((0.7, -0.6), (0.7, 0.0), (0.7, 0.6),
                                (-0.8, 0.8))):
        caravan(m, fr, s * S, p * P, ((60, 160, 200), (230, 200, 60),
                                      (60, 140, 80), (200, 80, 160))[k])
    return m


def green_house(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.5)
    block(m, fr, 0.2 * S, 0.9 * S, -0.8 * P, 0.8 * P, 1,
          Palette(wall=(70, 90, 150), trim=(230, 230, 230), roof=(60, 70, 100)),
          roof="gable_p", pitch=0.14)
    glass = (190, 214, 220)
    add_block(m, fr, -0.9 * S, 0.05 * S, -0.8 * P, 0.8 * P, 0, 0.18, glass)
    f = Frame(fr.u, origin=fr.world(0, 0, 0)[:2])
    for side in (-1, 1):
        add_face(m, [f.world(-0.9 * S, side * 0.8 * P, 0.18),
                     f.world(0.05 * S, side * 0.8 * P, 0.18),
                     f.world(0.05 * S, 0, 0.3), f.world(-0.9 * S, 0, 0.3)],
                 glass, outward=f.world(-0.4 * S, 0, 0))
    for s in np.linspace(-0.9 * S, 0.05 * S, 6):
        add_beam(m, fr.world(s, -0.8 * P, 0.18), fr.world(s, 0, 0.3), 0.008,
                 (230, 230, 230))
        add_beam(m, fr.world(s, 0.8 * P, 0.18), fr.world(s, 0, 0.3), 0.008,
                 (230, 230, 230))
    broadleaf(m, fr, 0.5 * S, 0.9 * P, 0.5)
    return m


def museum(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), GRASS, 0.2)]))
    site.wall(m, (150, 146, 140), height=0.16, shader=speckle_shader(
        (150, 146, 140)))
    block(m, fr, 0.0, 0.85 * S, 0.1 * P, 0.85 * P, 2, CREAM, roof="hip",
          pitch=0.16)
    for s, p in ((-0.85 * S, -0.85 * P), (-0.85 * S, 0.85 * P)):
        tower(m, fr, s, p, 0.1, 0.6, CASTLE, round_=True, cap_h=0.26)
    for s, p in ((-0.3 * S, -0.3 * P), (0.4 * S, -0.5 * P), (-0.4 * S, 0.4 * P)):
        broadleaf(m, fr, s, p, 0.45)
    return m


def park(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(oval(0, 0, S * 1.05, P * 1.05), GRASS, 0.2)]))
    pond(m, fr, 0.0, 0.0, 0.55 * S, 0.45 * P)
    rocks(m, fr, 0.4 * S, -0.3 * P, 0.12)
    rocks(m, fr, -0.45 * S, 0.3 * P, 0.1, seed=1)
    for k, (s, p) in enumerate(((-0.8, -0.6), (-0.7, 0.7), (0.8, 0.6),
                                (0.75, -0.7), (0.0, 0.9), (0.0, -0.9))):
        (conifer if k % 2 else broadleaf)(m, fr, s * S, p * P, 0.5)
    return m


def courthouse(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-0.8 * S, 0.85 * S, -0.8 * P,
                                        0.8 * P), PAVING, 0.12)]))
    pal = Palette(wall=(190, 110, 70), trim=(236, 226, 206), roof=(150, 150, 150))
    block(m, fr, -0.7 * S, 0.5 * S, -0.7 * P, 0.7 * P, 3, pal, door=True)
    block(m, fr, 0.5 * S, 0.75 * S, -0.3 * P, 0.3 * P, 3, pal, roof="gable_p",
          pitch=0.2)
    add_frustum(m, fr, -0.1 * S, 0, 0.3, 0.3, 3 * STOREY, 3 * STOREY + 0.2,
                pal.trim, n=16)
    dome(m, fr, -0.1 * S, 0, 0.28, 3 * STOREY + 0.2, (190, 70, 40))
    for s, p in ((-0.95, -0.9), (-0.95, 0.9), (0.95, -0.9), (0.95, 0.9),
                 (0.0, 0.95), (0.0, -0.95)):
        broadleaf(m, fr, s * S, p * P, 0.55)
    return m


def radiant_house(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.55)
    site.ground(m, paint(regions=[(rect(0.45 * S, 0.95 * S, -0.9 * P, 0.9 * P),
                                   ASPHALT, 0.1)]))
    pal = Palette(wall=(214, 216, 214), trim=(190, 192, 196), roof=(120, 120, 124),
                  glass=(96, 130, 170))
    # The slab on pilotis.
    for s in np.linspace(-0.85 * S, 0.25 * S, 5):
        for p in (-0.45 * P, 0.45 * P):
            add_block(m, fr, s - 0.04, s + 0.04, p - 0.04, p + 0.04, 0, 0.2,
                      (180, 180, 178))
    f = Frame(fr.u, origin=fr.world(0, 0, 0)[:2])
    sub = Model()
    block(sub, f, -0.95 * S, 0.35 * S, -0.55 * P, 0.55 * P, 12, pal,
          door=False)
    base = len(m.verts)
    m.verts.extend((x, y, z + 0.2) for x, y, z in sub.verts)
    m.quads.extend((a + base, b + base, c + base, d + base, *r)
                   for a, b, c, d, *r in sub.quads)
    parking(m, fr, 0.5 * S, 0.95 * S, -0.85 * P, 0.85 * P)
    for s in np.linspace(-0.9 * S, 0.3 * S, 5):
        conifer(m, fr, s, 0.95 * P, 0.5)
    return m


def sacred_heart(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PAVING, 0.12)]))
    pal = Palette(wall=(90, 120, 190), trim=(200, 210, 230), roof=(170, 170, 170),
                  glass=(140, 170, 220))
    block(m, fr, -0.6 * S, 0.5 * S, -0.1 * P, 0.85 * P, 3, pal)
    add_block(m, fr, -0.9 * S, -0.65 * S, -0.85 * P, -0.6 * P, 0, 1.0,
              (110, 110, 114))
    for z in np.arange(0.1, 1.0, 0.18):
        add_block(m, fr, -0.92 * S, -0.63 * S, -0.87 * P, -0.58 * P, z, z + 0.03,
                  (150, 150, 154))
    cross(m, fr, -0.775 * S, -0.725 * P, 1.0, (240, 240, 240))
    parking(m, fr, 0.55 * S, 0.95 * S, -0.9 * P, -0.1 * P)
    for p in (-0.3 * P, 0.2 * P):
        flagpole(m, fr, 0.75 * S, p)
    return m


def stadium_rugby(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.6)
    ps, pp = 0.9 * S, 0.7 * P
    lines = lambda s, p: (pitch_markings(-ps, ps, -pp, pp)(s, p) |
                          (rect(-ps, ps, -pp, pp)(s, p) &
                           (np.abs(((s + ps) / (2 * ps) * 10) % 1 - 0.5) > 0.47)))
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), PITCH, 0.15),
                                  (lines, WHITE_LINE, 0.05)]))
    rugby_posts(m, fr, -ps, 0)
    rugby_posts(m, fr, ps, 0)
    stand(m, fr, -0.5 * S, 0.5 * S, -P, -0.2, rows=3)
    block(m, fr, -0.2 * S, 0.2 * S, P - 0.15, P, 1, WHITE, door=False)
    for s in np.linspace(-S, S, 5):
        poplar(m, fr, s, P + 0.12, 0.7)
    return m


def tennis_court(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    courts = [(-0.95, -0.05, -0.95, -0.05, CLAY), (0.05, 0.95, -0.95, -0.05,
                                                     (70, 130, 80)),
              (-0.95, -0.05, 0.05, 0.95, (60, 90, 140))]
    regions = []
    for s0, s1, p0, p1, c in courts:
        box = rect(s0 * S, s1 * S, p0 * P, p1 * P)
        regions.append((box, c, 0.1))
        regions.append((lines_of(rect((s0 + 0.08) * S, (s1 - 0.08) * S,
                                      (p0 + 0.12) * P, (p1 - 0.12) * P)),
                        WHITE_LINE, 0.05))
    site.ground(m, paint(regions=regions))
    for s0, s1, p0, p1, _ in courts:
        sm = (s0 + s1) / 2 * S
        add_block(m, fr, sm - 0.004, sm + 0.004, (p0 + 0.1) * P, (p1 - 0.1) * P,
                  0, 0.05, (240, 240, 240))
    block(m, fr, 0.15 * S, 0.85 * S, 0.2 * P, 0.8 * P, 1, WHITE)
    return m


# --- Landscape ----------------------------------------------------------------

def skiing_resort(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.7)
    loop = lambda s, p: np.abs(((s / (0.75 * S)) ** 2 + (p / (0.7 * P)) ** 2)
                               ** 0.5 - 1) < 0.06
    site.ground(m, paint(regions=[(loop, (226, 220, 206), 0.1),
                                  (rect(0.7 * S, 0.98 * S, -0.3 * P, 0.3 * P),
                                   ASPHALT, 0.1)]))
    rng = np.random.default_rng(3)
    k = 0
    for cs, cp in site.tile_points():
        for _ in range(5):
            s, p = cs + rng.uniform(-0.6, 0.6), cp + rng.uniform(-0.6, 0.6)
            r = ((s / (0.75 * S)) ** 2 + (p / (0.7 * P)) ** 2) ** 0.5
            if abs(r - 1) < 0.15 or (s > 0.5 * S and abs(p) < 0.85 * P) or \
                    not site.inside(s, p, 0.15):
                continue
            (conifer if k % 4 else broadleaf)(m, fr, s, p, 0.5 + 0.1 * (k % 3))
            k += 1
    block(m, fr, 0.55 * S, 0.68 * S, 0.4 * P, 0.7 * P, 1, TIMBER, roof="gable",
          pitch=0.16)
    parking(m, fr, 0.72 * S, 0.97 * S, -0.28 * P, 0.28 * P)
    return m


def mt_hotel(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.8)
    site.ground(m, paint(regions=[(rect(-0.9 * S, 0.9 * S, -0.9 * P, 0.9 * P),
                                   PAVING, 0.15)]))
    block(m, fr, -0.6 * S, 0.6 * S, -0.7 * P, 0.1 * P, 2, ALPINE, roof="gable",
          pitch=0.24)
    block(m, fr, -0.6 * S, -0.0 * S, 0.1 * P, 0.7 * P, 2, ALPINE,
          roof="gable_p", pitch=0.24, door=False)
    tower(m, fr, 0.4 * S, 0.45 * P, 0.1, 0.85, ALPINE, round_=True, cap_h=0.32)
    for s, p in ((0.85 * S, -0.8 * P), (-0.85 * S, 0.85 * P)):
        conifer(m, fr, s, p, 0.6)
    return m


def castle(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-0.75 * S, 0.75 * S, -0.75 * P,
                                        0.75 * P), GRAVEL, 0.2)]))
    block(m, fr, -0.7 * S, 0.3 * S, -0.7 * P, 0.0, 3, Palette(
        wall=(214, 196, 160), trim=(236, 226, 206), roof=(200, 70, 90)),
        roof="gable", pitch=0.34)
    block(m, fr, -0.7 * S, -0.1 * S, 0.0, 0.7 * P, 3, PINK, roof="gable_p",
          pitch=0.34, door=False)
    tower(m, fr, 0.35 * S, -0.35 * P, 0.14, 1.0, PINK, round_=True, cap_h=0.4)
    tower(m, fr, -0.7 * S, 0.7 * P, 0.12, 0.9, PINK, cap_h=0.36)
    return m


def fort_fun(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), (180, 150, 110), 0.25)]))
    palisade = (120, 84, 50)
    for a, b in footprint_outline(site.dims, inset=0.1):
        n = max(2, int(math.dist(a, b) / 0.05))
        for k in range(n):
            x = a[0] + (b[0] - a[0]) * k / n
            y = a[1] + (b[1] - a[1]) * k / n
            add_beam(m, (x, y, 0), (x, y, 0.24 + 0.03 * (k % 2)), 0.045,
                     palisade)
    for k, (s0, s1, p0, p1) in enumerate(((-0.8, -0.3, -0.8, -0.3),
                                          (-0.8, -0.3, 0.0, 0.5),
                                          (0.0, 0.5, -0.8, -0.35),
                                          (0.1, 0.6, 0.2, 0.7))):
        block(m, fr, s0 * S, s1 * S, p0 * P, p1 * P, 1 + k % 2,
              (TIMBER, ALPINE)[k % 2], roof="gable", pitch=0.12)
    tower(m, fr, 0.8 * S, 0.8 * P, 0.1, 0.5, TIMBER, cap="flat")
    return m


def manor(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.8)
    site.ground(m, paint(regions=[
        (rect(-0.7 * S, 0.6 * S, -0.9 * P, 0.95 * P), GRAVEL, 0.2),
        (lambda s, p: (s > 0.5 * S) & (np.abs(p + 0.2 * P) < 0.12), GRAVEL,
         0.2)]))
    block(m, fr, -0.6 * S, 0.5 * S, -0.8 * P, 0.4 * P, 2, PINK, roof="hip",
          pitch=0.26)
    block(m, fr, -0.6 * S, 0.0, 0.4 * P, 0.85 * P, 2, PINK, roof="hip",
          pitch=0.22, door=False)
    for s in (-0.3 * S, 0.2 * S):
        add_block(m, fr, s - 0.04, s + 0.04, -0.2 * P - 0.04, -0.2 * P + 0.04,
                  2 * STOREY, 2 * STOREY + 0.3, (180, 90, 80))
    for k, (s, p) in enumerate(((0.85, -0.85), (0.85, 0.85), (-0.9, 0.0),
                                (0.0, 1.0), (-0.85, -0.9))):
        (conifer if k % 2 else broadleaf)(m, fr, s * S, p * P, 0.55)
    return m


def icarus(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(oval(0, 0, 0.55 * S, 0.55 * P), (150, 146,
                                                                    140), 0.2),
                                  (rect(0.5 * S, S, -0.15 * P, 0.15 * P),
                                   ASPHALT, 0.1)]))
    site.fence(m, colour=(170, 170, 176), height=0.14, posts=6)
    add_block(m, fr, -0.25, 0.25, -0.25, 0.25, 0, 0.08, (120, 116, 112))
    # The rocket.
    for r0, r1, z0, z1, c in ((0.09, 0.09, 0.08, 1.6, (236, 236, 240)),
                              (0.09, 0.04, 1.6, 1.85, (236, 236, 240)),
                              (0.04, 0.0, 1.85, 2.0, (200, 200, 206))):
        add_frustum(m, fr, 0, 0, r0, r1, z0, z1, c, n=12)
    add_frustum(m, fr, 0, 0, 0.092, 0.092, 0.7, 1.0, (40, 70, 160), n=12)
    for k in range(4):
        a = math.pi / 2 * k + math.pi / 4
        add_beam(m, fr.world(0.13 * math.cos(a), 0.13 * math.sin(a), 0.08),
                 fr.world(0.06 * math.cos(a), 0.06 * math.sin(a), 0.5), 0.03,
                 (220, 220, 226))
    # Service tower beside it.
    red = (180, 50, 40)
    for ds in (-0.08, 0.08):
        for dp in (0.17, 0.33):
            add_beam(m, fr.world(-0.25 + ds, dp, 0.08),
                     fr.world(-0.25 + ds, dp, 1.9), 0.025, red)
    for z in np.arange(0.2, 1.9, 0.18):
        add_block(m, fr, -0.34, -0.16, 0.16, 0.34, z, z + 0.02, red)
        add_beam(m, fr.world(-0.25, 0.17, z), fr.world(-0.25, 0.09, z), 0.02, red)
    for k, (s, p) in enumerate(((0.75, -0.5), (0.7, 0.5))):
        car(m, fr, s * S, p * P, CARS[k + 1], along_s=True)
    return m


def rock(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(oval(0, 0, 1.3 * S, 1.3 * P),
                                   (150, 120, 96), 0.35)]))
    col = (150, 90, 60)
    for r0, r1, z0, z1 in ((0.75, 0.55, 0.0, 0.2), (0.55, 0.45, 0.2, 0.8),
                           (0.45, 0.4, 0.8, 1.0)):
        add_frustum(m, fr, 0, 0, r0 * min(S, P), r1 * min(S, P), z0, z1, col,
                    n=14, side_shader=speckle_shader(col))
    tree_ring(m, fr, site, n=12, kind="conifer", radius=0.95)
    return m


def ruin(site, big=False):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), (140, 136, 124),
                                   0.4)]))
    k = 0.85
    walls = (((-k, -k), (k, -k)), ((k, -k), (k, 0.2)), ((-k, k), (-k, -k)),
             ((-k, k), (0.1, k)))
    for (a0, a1), (b0, b1) in walls:
        a = fr.world(a0 * S, a1 * P, 0)[:2]
        b = fr.world(b0 * S, b1 * P, 0)[:2]
        n = 6
        for i in range(n):
            if (i + int(a0 * 10)) % 4 == 3:
                continue
            x0 = a[0] + (b[0] - a[0]) * i / n
            y0 = a[1] + (b[1] - a[1]) * i / n
            x1 = a[0] + (b[0] - a[0]) * (i + 1) / n
            y1 = a[1] + (b[1] - a[1]) * (i + 1) / n
            seg = Frame((x1 - x0, y1 - y0), origin=(x0, y0))
            add_block(m, seg, 0, math.dist((x0, y0), (x1, y1)), -0.05, 0.05,
                      0, 0.2 + 0.12 * ((i * 7 + int(b0 * 5)) % 3), RUIN.wall,
                      side_shader=speckle_shader(RUIN.wall))
    tower(m, fr, k * S, k * P, 0.16 if big else 0.13, 0.8 if big else 0.6,
          RUIN, round_=True, cap="crenel")
    tower(m, fr, -k * S, -k * P, 0.12, 0.5, RUIN, cap="crenel")
    if big:
        block(m, fr, -0.4 * S, 0.3 * S, -0.4 * P, 0.3 * P, 3, RUIN, door=False)
        tower(m, fr, 0.0, 0.0, 0.18, 1.1, RUIN, cap="crenel")
    rocks(m, fr, 0.3 * S, 0.4 * P, 0.1)
    tree_ring(m, fr, site, n=8 if not big else 14, radius=1.05, seed=2)
    return m


def maya_temple(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(rect(-S, S, -P, P), SAND, 0.2)]))
    site.fence(m, colour=(110, 90, 60), height=0.1)
    stone = (190, 170, 130)
    r = 0.75 * min(S, P)
    for k in range(6):
        h0, h1 = 0.12 * k, 0.12 * (k + 1)
        rr = r * (1 - 0.14 * k)
        add_block(m, fr, -rr, rr, -rr, rr, h0, h1, stone,
                  side_shader=speckle_shader(stone))
    add_block(m, fr, -0.18, 0.18, -0.18, 0.18, 0.72, 0.92, (170, 150, 110))
    # Stairs up the front.
    for k in range(12):
        z = 0.06 * k
        s = r - (r - 0.18) * k / 12
        add_block(m, fr, s - 0.05, s + 0.06, -0.1, 0.1, z, z + 0.06,
                  (210, 196, 160))
    for k in range(3):
        caravan(m, fr, 0.85 * S, (-0.6 + 0.3 * k) * P, (230, 230, 226))
    return m


def oasis(site):
    m, fr = Model(), site.fr
    S, P = site.box(0.65)
    site.ground(m, paint(regions=[(oval(0, 0, S, P), SAND, 0.2)]))
    pond(m, fr, 0.0, 0.0, 0.6 * S, 0.45 * P)
    for k, (s, p) in enumerate(((-0.7, -0.5), (-0.6, 0.55), (0.65, 0.5),
                                (0.2, -0.7), (0.75, -0.3))):
        palm(m, fr, s * S, p * P, 0.55 + 0.1 * (k % 2))
    rocks(m, fr, 0.4 * S, 0.65 * P, 0.08)
    return m


def greened(build, kind="mix", inset=0.3, step=0.6):
    """`build` with trees (or bushes) along the plot's border, outside the
    box the builder fills."""
    def fn(site):
        m = build(site)
        S, P = site.box(0.65)
        site.border_trees(m, kind=kind, inset=inset, step=step,
                          keep=lambda s, p: abs(s) > 0.95 * S or
                          abs(p) > 0.95 * P)
        return m
    return fn


SITES = {
    "CHURCH_05": ("city/church_05", greened(church_05)),
    "ELEMENTARY_SCHOOL_1": ("city/elementary_school_1", greened(elementary_school_1)),
    "ELEMENTARY_SCHOOL_2": ("city/elementary_school_2", greened(elementary_school_2)),
    "Firestation": ("city/firestation", firestation),
    "french_garden_4": ("city/french_garden_4", greened(french_garden, "bush", step=0.35)),
    "GRASS_STADIUM": ("city/grass_stadium", greened(grass_stadium, "poplar")),
    "HIGH_SCHOOL_1": ("city/high_school_1", greened(high_school_1)),
    "HIGH_SCHOOL_2": ("city/high_school_2", greened(high_school_2)),
    "library_holy_genevieve": ("city/library_holy_genevieve", greened(library)),
    "Little_Central_Park": ("city/little_central_park", central_park),
    "MARKET_PLACE_0": ("city/market_place_0", market_place),
    "CIRCUS_0": ("city/no-winter/circus_0", circus),
    "GREEN_HOUSE": ("city/no-winter/green_house", greened(green_house, "bush", step=0.35)),
    "MUSEUM_0": ("city/no-winter/museum_0", museum),
    "PARK_0": ("city/no-winter/park_0", greened(park)),
    "rmax_courthouse": ("city/no-winter/rmax_courthouse", greened(courthouse)),
    "radiant_house": ("city/radiant_house", greened(radiant_house, "conifer")),
    "Sacred_heart_church": ("city/sacred_heart_munchen", greened(sacred_heart, "bush", step=0.4)),
    "STADIUM_RUGBY": ("city/stadium_rugby", stadium_rugby),
    "tennis_court": ("city/tennis_court", greened(tennis_court, "bush", step=0.35)),
    "Cross_Country_skiing_resort": ("landscape/cross_country_skiing_resort",
                                    skiing_resort),
    "MT_HOTEL_0": ("landscape/mt_hotel_0", greened(mt_hotel, "conifer")),
    "CASTLE_0": ("landscape/no-winter/castle_0", greened(castle)),
    "FORT_FUN": ("landscape/no-winter/fort_fun", fort_fun),
    "MANOR_0": ("landscape/no-winter/manor_0", greened(manor)),
    "rmax_icarus": ("landscape/no-winter/rmax_icarus", icarus),
    "ROCK_0": ("landscape/no-winter/rock_0", rock),
    "RUIN_0": ("landscape/no-winter/ruin_0", ruin),
    "RUIN_1": ("landscape/no-winter/ruin_1",
               greened(lambda site: ruin(site, big=True))),
    "Percival_Maya_Temple": ("landscape/percival_maya_temple", maya_temple),
    "sh_oasis_seasons": ("landscape/sh_oasis_seasons", oasis),
}


def dims_of(dat: Path, name: str) -> tuple[tuple[int, int], int]:
    text = dat.read_text(errors="replace")
    for b in re.split(r"(?im)^\s*obj\s*=", text)[1:]:
        n = re.search(r"(?im)^\s*name\s*=\s*(\S+)", b)
        if n and n.group(1) == name:
            d = [int(x) for x in re.search(r"(?im)^\s*dims\s*=\s*([\d,\s]+)",
                                           b).group(1).split(",")]
            return (d[0], d[1]), (d[2] if len(d) > 2 else 1)
    raise KeyError(name)


def bake(name: str) -> None:
    stem, build = SITES[name]
    dat = SPECIAL_DIR / f"{stem}.dat"
    dims, layouts = dims_of(dat, name)
    lines = bake_site(build, dims, layouts,
                      dat.with_name(f"{dat.stem}_hex.png"))
    crlf = b"\r\n" in dat.read_bytes()
    rewrite_images(dat, {name: lines})
    if crlf:
        dat.write_bytes(dat.read_bytes().replace(b"\r\n", b"\n")
                        .replace(b"\n", b"\r\n"))


def preview(names, out: Path) -> None:
    grass = ground_cell(HexGeom())
    sheets = []
    for name in names:
        stem, build = SITES[name]
        dims, _ = dims_of(SPECIAL_DIR / f"{stem}.dat", name)
        site = Site(dims)
        model = build(site)
        for levels in range(4, 16):
            try:
                tiles = render_tiles(model, site.dims, levels=levels,
                                     ambient=AMBIENT)
                break
            except ValueError:
                continue
        sheets.append(composite(tiles, grass))
    w = sum(s.width for s in sheets)
    h = max(s.height for s in sheets)
    sheet = Image.new("RGBA", (w, h))
    x = 0
    for s in sheets:
        sheet.alpha_composite(s, (x, h - s.height))
        x += s.width
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="objects to bake (default all)")
    ap.add_argument("--preview", type=Path,
                    help="write the objects side by side instead of baking")
    a = ap.parse_args()
    names = a.names or list(SITES)
    if a.preview:
        preview(names, a.preview)
    else:
        for name in names:
            bake(name)
