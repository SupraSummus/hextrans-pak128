"""City buildings for the hex grid: one-tile houses from a few
parameters, and their bake.

pak128 has well over a thousand city buildings, each a hand-drawn
square sprite.  Here a family of them is a function from a building's
`.dat` (name, level, climates, intro year) to a parameter set, and a
parameter set to a model, so a family bakes in one pass and each
building keeps its own look through `pick`, a choice keyed to its name.

A city building turns to face its road on any of the six hex sides:
`stadt_t::orient_city_building` uses layouts 0..5 of an 8-layout
building as S, SE, N, NW, NE, SW (`ribi_t::layout_to_ribi`).  The
bake renders those six and points layouts 6 and 7 at 0 and 1.
Season 1, where the `.dat` has one, is winter: snow on the roofs and
the ground.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from .bespoke import bake_atlas
from .blocks import hip
from .building import render_tiles
from .building_kit import AMBIENT, STOREY, edit_dat, speckle_shader, wall_quad
from .factory_kit import ground_shader
from .hex_synth import hash_noise01
from .render import Model
from .solids import Frame, add_block, add_face, add_frustum
from .way import edge_midpoint

FACES = ("S", "SE", "N", "NW", "NE", "SW")
SNOW = (238, 240, 244)
GLASS = (54, 64, 82)
FRAME_WHITE = (226, 224, 216)


def pick(name: str, salt: str, options):
    """One of `options`, the same every bake for the same name."""
    h = hashlib.sha1(f"{name}/{salt}".encode()).digest()
    return options[int.from_bytes(h[:4], "little") % len(options)]


def unit(name: str, salt: str) -> float:
    """A number in [0, 1), the same every bake for the same name."""
    h = hashlib.sha1(f"{name}/{salt}".encode()).digest()
    return int.from_bytes(h[:4], "little") / 2 ** 32


# --- Parts --------------------------------------------------------------------

def lot(model, fr: Frame, colour, snow: bool):
    """The ground of the tile: paving, snowed over in winter."""
    pts = [fr.world(s, p, 0.003) for s, p in
           ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    base = tuple(int(c * 0.35 + s * 0.65) for c, s in zip(colour, SNOW)) \
        if snow else colour
    add_face(model, pts, (0, 0, 0), outward=fr.world(0, 0, -1),
             shader=ground_shader(base, grain=0.12))


def facade_shader(fr: Frame, a, b, wall, storeys, bays, z0, *,
                  glass=GLASS, frame=FRAME_WHITE, h=0.12, w=0.36):
    """Wall colour with `bays` windows a storey along the wall from `a`
    to `b` (frame `(s, p)`), the first storey's sill at `z0`."""
    wall = np.array(wall, float)
    glass, frame = np.array(glass, float), np.array(frame, float)
    ax, ay = fr.world(*a, 0)[:2]
    bx, by = fr.world(*b, 0)[:2]
    length = math.dist((ax, ay), (bx, by))
    ux, uy = (bx - ax) / length, (by - ay) / length
    pitch = length / bays

    def shader(wx, wy, sx, sy, wz):
        t = ((wx - ax) * ux + (wy - ay) * uy) / pitch
        n = hash_noise01(sx.astype(np.uint32) // 2, sy.astype(np.uint32))
        rgb = wall * np.where(n < 0.12, 0.88, 0.96 + 0.06 * n)[:, None]
        zz = (wz - z0 - 0.05) / STOREY
        k = np.floor(zz)
        fz = (zz - k) * STOREY
        fx = np.abs(t % 1.0 - 0.5) * pitch
        in_storeys = (k >= 0) & (k < storeys) & (t > 0) & (t < bays)
        win = in_storeys & (fz < h) & (fx < pitch * w / 2)
        rim = in_storeys & (fz < h + 0.008) & (fx < pitch * w / 2 + 0.008) \
            & ~win
        rgb[rim] = frame
        rgb[win] = glass * (0.9 + 0.25 * n[win])[:, None]
        return rgb, np.ones(len(wx), bool)

    shader.wants_z = True
    return shader


def walls(model, fr: Frame, s0, s1, w, z0, z1, colour, storeys, *,
          sill=0.06, pitch=0.16, glass=GLASS, frame=FRAME_WHITE):
    """A box's four walls from `z0` to `z1`, windowed by `facade_shader`."""
    corners = ((s1, -w), (s1, w), (s0, w), (s0, -w))
    inside = fr.world((s0 + s1) / 2, 0, (z0 + z1) / 2)
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        bays = max(2, round(math.dist(a, b) / pitch))
        add_face(model, [fr.world(*a, z0), fr.world(*b, z0),
                         fr.world(*b, z1), fr.world(*a, z1)], colour,
                 outward=inside,
                 shader=facade_shader(fr, a, b, colour, storeys, bays, sill,
                                      glass=glass, frame=frame))


# --- Apartment blocks ---------------------------------------------------------

@dataclass(frozen=True)
class Apartment:
    storeys: int
    s0: float                   # back wall, along the frame of the front
    s1: float                   # front wall
    w: float                    # half width across
    wall: tuple[int, int, int]
    trim: tuple[int, int, int]  # plinth, cornice, balcony slabs
    rail: tuple[int, int, int] | None   # balcony fronts, None for none
    stair: tuple[int, int, int]         # the glazed stair strip in front
    roof: str = "flat"          # flat or hip
    roof_colour: tuple[int, int, int] = (96, 96, 100)
    wing: float = 0.0           # a lower wing to one side, its depth
    snow: bool = False


def apartment(a: Apartment, face: str) -> Model:
    model = Model()
    fr = Frame(edge_midpoint(face))
    lot(model, fr, (150, 146, 138), a.snow)
    top = a.storeys * STOREY + 0.06
    walls(model, fr, a.s0, a.s1, a.w, 0.0, top, a.wall, a.storeys)
    add_block(model, fr, a.s0 - 0.01, a.s1 + 0.01, -a.w - 0.01, a.w + 0.01,
              0.0, 0.06, a.trim)
    # The stair strip up the front, glazed, with the door at its foot.
    wall_quad(model, fr, (a.s1, -0.06), (a.s1, 0.06), 0.0, top - 0.04,
              0.01, a.stair, (-1, 0))
    wall_quad(model, fr, (a.s1, -0.04), (a.s1, 0.04), 0.0, 0.16, 0.014,
              (70, 54, 44), (-1, 0))
    if a.rail:
        balconies(model, fr, a)
    roof(model, fr, a, top)
    if a.wing:
        wing(model, fr, a)
    return model


def balconies(model, fr: Frame, a: Apartment):
    """A slab and a front at each storey on the front and the left side,
    either side of the stair strip."""
    depth = 0.07
    for k in range(1, a.storeys):
        z = k * STOREY + 0.06
        for p0, p1 in ((-a.w + 0.04, -0.1), (0.1, a.w - 0.04)):
            add_block(model, fr, a.s1, a.s1 + depth, p0, p1, z - 0.012, z,
                      a.trim)
            add_block(model, fr, a.s1 + depth - 0.012, a.s1 + depth, p0, p1,
                      z, z + 0.07, a.rail)
        s0, s1 = a.s0 + 0.05, a.s1 - 0.05
        add_block(model, fr, s0, s1, -a.w - depth, -a.w, z - 0.012, z, a.trim)
        add_block(model, fr, s0, s1, -a.w - depth, -a.w - depth + 0.012, z,
                  z + 0.07, a.rail)


def roof(model, fr: Frame, a: Apartment, top):
    colour = SNOW if a.snow else a.roof_colour
    if a.roof == "hip":
        add_block(model, fr, a.s0 - 0.02, a.s1 + 0.02, -a.w - 0.02, a.w + 0.02,
                  top - 0.03, top, a.trim)
        hip(model, fr, a.s0, a.s1, a.w, top, 0.22, colour)
        return
    add_block(model, fr, a.s0 - 0.015, a.s1 + 0.015, -a.w - 0.015,
              a.w + 0.015, top, top + 0.04, a.trim)
    add_block(model, fr, a.s0 + 0.02, a.s1 - 0.02, -a.w + 0.02, a.w - 0.02,
              top + 0.005, top + 0.03, colour)
    # Lift house over the stair.
    add_block(model, fr, a.s1 - 0.2, a.s1 - 0.04, -0.1, 0.1, top, top + 0.1,
              a.wall)
    add_block(model, fr, a.s1 - 0.21, a.s1 - 0.03, -0.11, 0.11, top + 0.1,
              top + 0.12, SNOW if a.snow else a.trim)


def wing(model, fr: Frame, a: Apartment):
    """A lower wing off the right side."""
    storeys = max(2, a.storeys // 2)
    top = storeys * STOREY + 0.06
    p0, p1 = a.w, a.w + a.wing
    s0, s1 = a.s1 - 0.5, a.s1 - 0.05
    wing_fr = Frame(fr.u, origin=fr.world(0, (p0 + p1) / 2, 0)[:2])
    walls(model, wing_fr, s0, s1, (p1 - p0) / 2, 0.0, top, a.wall, storeys)
    add_block(model, fr, s0 - 0.015, s1 + 0.015, p0, p1 + 0.015, top,
              top + 0.035, a.trim)
    add_block(model, fr, s0 + 0.02, s1 - 0.02, p0 + 0.02, p1 - 0.02,
              top + 0.005, top + 0.025, SNOW if a.snow else a.roof_colour)


# --- Houses -------------------------------------------------------------------

LAWN = (96, 140, 62)
PATH = (176, 168, 150)
LEAF = ((70, 120, 50), (90, 130, 56), (60, 104, 52))
TRUNK = (84, 60, 42)


@dataclass(frozen=True)
class House:
    storeys: int
    s0: float                   # back wall
    s1: float                   # front wall, towards the road
    w: float                    # half width across
    wall: tuple[int, int, int]
    trim: tuple[int, int, int]
    roof_colour: tuple[int, int, int]
    roof: str = "gable"         # gable (ridge across the front), hip, flat
    pitch: float = 0.24
    garden: bool = True         # lawn, a hedge, trees; paving otherwise
    timber: bool = False        # dark beams over the walls
    dormers: bool = False
    porch: bool = False
    trees: int = 1
    seed: str = ""
    snow: bool = False


def tree(model, fr: Frame, s, p, h, colour, snow):
    add_frustum(model, fr, s, p, 0.025, 0.02, 0.0, h * 0.4, TRUNK, n=6)
    crown = tuple(int(c * 0.4 + w * 0.6) for c, w in zip(colour, SNOW)) \
        if snow else colour
    # A round crown, squashed so it draws round (z draws at 90 px a
    # unit against 64 across).
    r, zc = 0.16 + 0.06 * h, h * 0.62
    rings = 6
    for k in range(rings):
        a0 = -math.pi / 2 + math.pi * k / rings
        a1 = -math.pi / 2 + math.pi * (k + 1) / rings
        add_frustum(model, fr, s, p, max(r * math.cos(a0), 0.01),
                    max(r * math.cos(a1), 0.01),
                    zc + r * 0.72 * math.sin(a0), zc + r * 0.72 * math.sin(a1),
                    crown, n=10, side_shader=speckle_shader(crown))


def garden_lot(model, fr: Frame, h: House):
    """Lawn over the tile with a path from the door to the road."""
    lawn = np.array(tuple(int(c * 0.3 + s * 0.7) for c, s in
                          zip(LAWN, SNOW)) if h.snow else LAWN, float)
    path = np.array(PATH, float)

    def shader(wx, wy, sx, sy):
        s, p = fr.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = lawn * (0.88 + 0.22 * n)[:, None]
        on_path = (np.abs(p) < 0.07) & (s > h.s1)
        rgb[on_path] = path * (0.92 + 0.12 * n[on_path])[:, None]
        return rgb, np.ones(len(wx), bool)

    pts = [fr.world(s, p, 0.003) for s, p in
           ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    add_face(model, pts, (0, 0, 0), outward=fr.world(0, 0, -1),
             shader=shader)


def timber_shader(fr: Frame, a, b, wall, z0, z1):
    """Plaster between dark posts and rails, a brace in every bay."""
    wall = np.array(wall, float)
    beam = np.array((70, 50, 36), float)
    ax, ay = fr.world(*a, 0)[:2]
    bx, by = fr.world(*b, 0)[:2]
    length = math.dist((ax, ay), (bx, by))
    ux, uy = (bx - ax) / length, (by - ay) / length
    bays = max(2, round(length / 0.12))
    pitch = length / bays

    def shader(wx, wy, sx, sy, wz):
        t = ((wx - ax) * ux + (wy - ay) * uy) / pitch
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = wall * (0.95 + 0.07 * n)[:, None]
        fz = (wz - z0) / STOREY
        fx = t % 1.0
        post = (fx < 0.12) | (fx > 0.88)
        rail = (np.abs(fz % 1.0) < 0.08) | (np.abs(fz % 1.0 - 0.5) < 0.04)
        brace = np.abs((fz % 1.0) * 0.5 - np.abs(fx - 0.5)) < 0.05
        rgb[post | rail | brace] = beam
        return rgb, np.ones(len(wx), bool)

    shader.wants_z = True
    return shader


def house(h: House, face: str) -> Model:
    model = Model()
    fr = Frame(edge_midpoint(face))
    if h.garden:
        garden_lot(model, fr, h)
    else:
        lot(model, fr, (160, 154, 144), h.snow)
    top = h.storeys * STOREY + 0.04
    walls(model, fr, h.s0, h.s1, h.w, 0.0, top, h.wall, h.storeys,
          sill=0.04, pitch=0.15)
    if h.timber:
        # The upper storeys framed, over the ground-floor plaster.
        corners = ((h.s1, -h.w), (h.s1, h.w), (h.s0, h.w), (h.s0, -h.w))
        inside = fr.world((h.s0 + h.s1) / 2, 0, top / 2)
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            pts = [fr.world(*a, STOREY + 0.04), fr.world(*b, STOREY + 0.04),
                   fr.world(*b, top), fr.world(*a, top)]
            add_face(model, pts, h.wall, outward=inside, shader=
                     timber_shader(fr, a, b, h.wall, STOREY + 0.04, top))
    add_block(model, fr, h.s0 - 0.01, h.s1 + 0.01, -h.w - 0.01, h.w + 0.01,
              0.0, 0.04, h.trim)
    # The door, a step and, maybe, a porch roof over them.
    wall_quad(model, fr, (h.s1, -0.05), (h.s1, 0.05), 0.0, 0.17, 0.008,
              (96, 60, 40), (-1, 0))
    add_block(model, fr, h.s1, h.s1 + 0.05, -0.08, 0.08, 0.0, 0.02, h.trim)
    if h.porch:
        add_block(model, fr, h.s1, h.s1 + 0.14, -0.13, 0.13, 0.2, 0.225,
                  h.roof_colour if not h.snow else SNOW)
        for q in (-0.11, 0.11):
            add_block(model, fr, h.s1 + 0.11, h.s1 + 0.13, q - 0.01, q + 0.01,
                      0.0, 0.2, h.trim)
    house_roof(model, fr, h, top)
    if h.garden:
        hedge = (60, 100, 52) if not h.snow else (210, 216, 214)
        for q in (-0.75, 0.75):
            add_block(model, fr, -0.6, 0.65, q - 0.03, q + 0.03, 0.0, 0.07,
                      hedge, side_shader=speckle_shader(hedge))
        spots = ((-0.65, -0.55), (0.55, 0.55), (-0.6, 0.6), (0.6, -0.55))
        for k in range(h.trees):
            s, p = spots[k % len(spots)]
            tree(model, fr, s, p, 0.55 + 0.25 * unit(h.seed, f"tree{k}"),
                 pick(h.seed, f"leaf{k}", LEAF), h.snow)
    return model


def house_roof(model, fr: Frame, h: House, top):
    colour = SNOW if h.snow else h.roof_colour
    sh = speckle_shader(colour)
    if h.roof == "flat":
        add_block(model, fr, h.s0 - 0.015, h.s1 + 0.015, -h.w - 0.015,
                  h.w + 0.015, top, top + 0.035, h.trim)
        add_block(model, fr, h.s0 + 0.02, h.s1 - 0.02, -h.w + 0.02,
                  h.w - 0.02, top + 0.005, top + 0.025, colour)
        return
    if h.roof == "hip":
        hip(model, fr, h.s0, h.s1, h.w, top, h.pitch, colour)
        return
    # Gable: the ridge runs across the front, the gables at the sides.
    o = 0.04
    inside = fr.world((h.s0 + h.s1) / 2, 0, top)
    sm = (h.s0 + h.s1) / 2
    for s_eave in (h.s0 - o, h.s1 + o):
        add_face(model, [fr.world(s_eave, -h.w - o, top),
                         fr.world(s_eave, h.w + o, top),
                         fr.world(sm, h.w + o, top + h.pitch),
                         fr.world(sm, -h.w - o, top + h.pitch)],
                 colour, outward=inside, shader=sh)
    for q in (-h.w, h.w):
        add_face(model, [fr.world(h.s0, q, top), fr.world(h.s1, q, top),
                         fr.world(sm, q, top + h.pitch)], h.wall,
                 outward=inside)
    if h.dormers:
        for q in (-h.w * 0.5, h.w * 0.5):
            s = (sm + h.s1) / 2
            z = top + h.pitch * 0.35
            add_block(model, fr, s - 0.02, s + 0.05, q - 0.05, q + 0.05,
                      z - 0.02, z + 0.09, h.wall)
            add_block(model, fr, s + 0.05, s + 0.054, q - 0.035, q + 0.035,
                      z, z + 0.07, GLASS)
            add_block(model, fr, s - 0.03, s + 0.07, q - 0.06, q + 0.06,
                      z + 0.09, z + 0.11, colour)
    # A chimney on the ridge.
    add_block(model, fr, sm - 0.04, sm + 0.04, h.w * 0.4 - 0.04,
              h.w * 0.4 + 0.04, top + h.pitch * 0.6, top + h.pitch + 0.1,
              (150, 80, 60))


# --- Bake ---------------------------------------------------------------------

def layout_face(layout: int) -> int:
    """The face a layout shows: 0..5 their own, 6 and 7 those of 0, 1."""
    return layout if layout < 6 else layout - 6


def bake_city(models: list[list[Model]], out_png: Path, layouts: int
              ) -> list[str]:
    """Write the atlas of a one-tile city building, `models[season][face]`
    over the six faces, a column per face and a row per season and
    height; return the `.dat` image lines for `layouts` layouts."""
    stacks = [[render_tiles(m, (1, 1), ambient=AMBIENT)[(0, 0)] for m in row]
              for row in models]
    heights = max(len(s) for row in stacks for s in row)
    blank = np.zeros_like(stacks[0][0][0])
    entries, lines = [], []
    for season, row in enumerate(stacks):
        for z in range(heights):
            for face, s in enumerate(row):
                entries.append((f"[{face}][{z}][{season}]",
                                lambda c=(s[z] if z < len(s) else blank): c))
    bake_atlas(out_png=out_png, entries=entries, cols_per_row=len(FACES),
               palette=True, verbose=False)
    for season, row in enumerate(stacks):
        for layout in range(layouts):
            face = layout_face(layout)
            for z in range(len(row[face])):
                lines.append(f"BackImage[{layout}][0][0][{z}][0][{season}]="
                             f"{out_png.stem}.{season * heights + z}.{face}")
    return lines


IMAGE_LINE = re.compile(r"^\s*(back|front)image\[", re.I)
SEASON_COMMENT = re.compile(r"^\s*#\s*(summer|winter)\s*$", re.I)


def rewrite_city_dat(dat: Path, lines: list[str]) -> None:
    """Replace the image block (and its season comments) of the only
    building in `dat`."""
    def edit(old):
        out, done = [], False
        for line in old:
            if IMAGE_LINE.match(line) or SEASON_COMMENT.match(line):
                if not done:
                    out += lines
                    done = True
                continue
            out.append(line)
        return out
    edit_dat(dat, edit)


def city_buildings(dat: Path) -> list[dict[str, str]]:
    """The `key=value` fields of each building in `dat` (keys
    lower-case), with `seasons`: how many its images have."""
    out = []
    text = dat.read_text(errors="replace")
    for block in re.split(r"(?im)^\s*obj\s*=", text)[1:]:
        if not block.strip().lower().startswith("building"):
            continue
        f = {}
        for line in block.splitlines():
            m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$", line)
            if m:
                f.setdefault(m.group(1).lower(), m.group(2))
        keys = re.findall(r"(?im)^\s*backimage((?:\[\d+\])+)", block)
        f["seasons"] = str(1 + max((int(re.findall(r"\d+", k)[5])
                                     for k in keys if k.count("[") >= 6),
                                    default=0))
        out.append(f)
    return out


def rewrite_city_building(dat: Path, name: str, lines: list[str]) -> None:
    """Give building `name` in `dat` the image lines `lines` and
    `dims=1,1,8`, dropping its old images, season comments and dims."""
    def edit(old):
        out, current, done = [], None, False
        for line in old:
            m = re.match(r"(?i)^\s*name\s*=\s*(.*?)\s*$", line)
            if m:
                current, done = m.group(1), False
                out.append(line)
                if current == name:
                    out.append("dims=1,1,8")
                continue
            if re.match(r"(?i)^\s*obj\s*=", line):
                current = None
            if current == name:
                if re.match(r"(?i)^\s*dims\s*=", line) or \
                        SEASON_COMMENT.match(line):
                    continue
                if IMAGE_LINE.match(line):
                    if not done:
                        out += lines
                        done = True
                    continue
            out.append(line)
        return out
    edit_dat(dat, edit)


def dat_fields(dat: Path) -> dict[str, str]:
    """The `key=value` lines of a one-building `.dat`, keys lower-case."""
    out = {}
    for line in dat.read_text(errors="replace").splitlines():
        m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$", line)
        if m:
            out.setdefault(m.group(1).lower(), m.group(2))
    return out


def seasons_of(dat: Path) -> int:
    idx = re.findall(r"(?im)^\s*backimage((?:\[\d+\]){6})", dat.read_text(
        errors="replace"))
    return 1 + max((int(re.findall(r"\d+", k)[5]) for k in idx), default=0)


__all__ = ["Apartment", "apartment", "bake_city", "dat_fields", "pick",
           "replace", "rewrite_city_dat", "seasons_of", "unit"]
