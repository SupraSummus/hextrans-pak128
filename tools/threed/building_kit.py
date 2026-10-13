"""Parts and bake plumbing shared by the 3D building scenes.

Buildings on a `Dims=2,2` rhombus stand on its back triangle and keep
the front tile as a yard (see CLAUDE.md, "Multi-tile buildings"):
`RHOMBUS_FRAME` has its origin on the vertex the triangle's three
hexes share and `s` pointing at the front tile's centre, `FRONT_S`
away.  Walls, roofs and facades take a `Palette`, so a brick hall and
a plastered mine house are the same parts.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .bespoke import bake_atlas
from .building import (
    NEIGHBOURS, SQRT3, composite, footprint, ground_cell, render_tiles,
    tile_centre)
from .hex_synth import HexGeom, hash_noise01
from .render import Model, unit
from .solids import Frame, add_block, add_face, add_roof, add_solid

RHOMBUS_FRAME = Frame((0.5, -SQRT3 / 2), origin=(0.5, -SQRT3 / 2))
FRONT_S = 2.0
STOREY = 0.22
AMBIENT = 0.5   # walls read too dark under the ways' 0.25


@dataclass(frozen=True)
class Palette:
    wall: tuple[int, int, int]
    trim: tuple[int, int, int]
    roof: tuple[int, int, int]
    plinth: tuple[int, int, int] = (150, 142, 128)
    glass: tuple[int, int, int] = (52, 62, 84)
    door: tuple[int, int, int] = (70, 44, 32)


# --- Ground -------------------------------------------------------------------

def outside_distance(dims, wx, wy):
    """Distance from a plan point to the nearest hex outside the
    footprint (negative inside one)."""
    tiles = set(footprint(dims))
    ring = {(x + dx, y + dy) for x, y in tiles for dx, dy in NEIGHBOURS}
    d = np.full(np.shape(wx), np.inf)
    for x, y in ring - tiles:
        cx, cy = tile_centre(x, y)
        ax, ay = np.abs(wx - cx), np.abs(wy - cy)
        d = np.minimum(d, np.maximum(ay, (SQRT3 * ax + ay) / 2) - SQRT3 / 2)
    return d


def footprint_outline(dims, inset: float = 0.0
                      ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """The hex edges round the footprint as world plan segments, moved
    `inset` into it; neighbouring segments still meet, so a fence or a
    hedge that follows them closes."""
    tiles = set(footprint(dims))
    edges = []                  # two corners and the inward normal
    for x, y in sorted(tiles):
        cx, cy = tile_centre(x, y)
        for dx, dy in NEIGHBOURS:
            if (x + dx, y + dy) in tiles:
                continue
            nx, ny = tile_centre(x + dx, y + dy)
            ux, uy = (nx - cx) / SQRT3, (ny - cy) / SQRT3
            mx, my = cx + ux * SQRT3 / 2, cy + uy * SQRT3 / 2
            edges.append(((mx + 0.5 * uy, my - 0.5 * ux),
                          (mx - 0.5 * uy, my + 0.5 * ux), (-ux, -uy)))
    meeting = {}
    for a, b, n in edges:
        for c in (a, b):
            meeting.setdefault((round(c[0], 6), round(c[1], 6)), []).append(n)

    def moved(c):
        # Where the two edges at `c`, each moved `inset` along its own
        # normal, cross.
        (ax, ay), (bx, by) = meeting[(round(c[0], 6), round(c[1], 6))]
        det = ax * by - ay * bx
        return (c[0] + inset * (by - ay) / det, c[1] + inset * (ax - bx) / det)

    return [(moved(a), moved(b)) for a, b, _ in edges]


def ground(model: Model, shader):
    """One flat quad over the whole rhombus, coloured by `shader`; each
    tile's render clips it to its own hex."""
    pts = [RHOMBUS_FRAME.world(s, p, 0.002)
           for s, p in ((-2.2, -1.8), (3.2, -1.8), (3.2, 1.8), (-2.2, 1.8))]
    add_face(model, pts, (0, 0, 0), outward=RHOMBUS_FRAME.world(0, 0, -1),
             shader=shader)


# --- Shaders ------------------------------------------------------------------

def speckle_shader(base):
    """Brick or plaster grain: per-pixel noise, a few darker and
    lighter flecks."""
    base = np.array(base, float)

    def shader(wx, wy, sx, sy):
        n = hash_noise01(sx.astype(np.uint32) // 2, sy.astype(np.uint32))
        k = np.where(n < 0.12, 0.84, np.where(n > 0.93, 1.1,
                                              0.96 + 0.06 * n))
        return base * k[:, None], np.ones(len(wx), bool)

    return shader


def course_shader(fr: Frame, base, pitch=0.045):
    """Slate or tile courses parallel to a ridge along the frame's `s`."""
    base = np.array(base, float)

    def shader(wx, wy, sx, sy):
        d = np.abs(fr.local(wx, wy)[1]) / pitch
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        k = 0.95 + 0.08 * n
        k = np.where(d % 1.0 < 0.22, 0.84, k)
        return base * k[:, None], np.ones(len(wx), bool)

    return shader


# --- Walls --------------------------------------------------------------------

def wall_quad(model, fr, a, b, z0, z1, off, color, inward):
    """Quad on the wall from plan point `a` to `b` (frame `(s, p)`),
    pushed `off` along the outward normal `-inward`."""
    ns, np_ = -inward[0], -inward[1]
    pts = [fr.world(a[0] + ns * off, a[1] + np_ * off, z0),
           fr.world(b[0] + ns * off, b[1] + np_ * off, z0),
           fr.world(b[0] + ns * off, b[1] + np_ * off, z1),
           fr.world(a[0] + ns * off, a[1] + np_ * off, z1)]
    inside = fr.world(a[0] + inward[0], a[1] + inward[1], (z0 + z1) / 2)
    add_face(model, pts, color, outward=inside)


def facade(model, fr, a, b, inward, pal: Palette, *, storeys, bays,
           door=False):
    """Windows, storey bands, plinth and corner quoins on one wall."""
    length = math.dist(a, b)
    d = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)

    def at(t):
        return (a[0] + d[0] * t, a[1] + d[1] * t)

    def quad(t0, t1, z0, z1, off, color):
        wall_quad(model, fr, at(t0), at(t1), z0, z1, off, color, inward)

    top = storeys * STOREY
    quad(0, length, 0, 0.06, 0.004, pal.plinth)
    for k in range(1, storeys + 1):
        quad(0, length, k * STOREY - 0.02, k * STOREY, 0.004, pal.trim)
    for t0 in (0, length - 0.05):
        quad(t0, t0 + 0.05, 0.06, top, 0.006, pal.trim)
    pitch = length / bays
    for k in range(storeys):
        z0 = k * STOREY + 0.08
        for i in range(bays):
            c = (i + 0.5) * pitch
            if door and k == 0 and i == bays // 2:
                quad(c - 0.08, c + 0.08, 0.0, 0.2, 0.006, pal.trim)
                quad(c - 0.055, c + 0.055, 0.0, 0.17, 0.01, pal.door)
                continue
            quad(c - 0.05, c + 0.05, z0 - 0.015, z0 + 0.15, 0.006, pal.trim)
            quad(c - 0.034, c + 0.034, z0, z0 + 0.135, 0.01, pal.glass)


def stepped_gable(model, fr, s, w, z_eave, z_ridge, pal: Palette, steps=4):
    """Gable at `s` stepping up to the ridge, each step capped in trim;
    it faces `+s`."""
    for k in range(steps):
        half = w * (1 - (k + 0.5) / steps)
        z0 = z_eave + (z_ridge - z_eave) * k / steps
        z1 = z_eave + (z_ridge - z_eave) * (k + 1) / steps
        add_block(model, fr, s - 0.06, s, -half, half, z0, z1, pal.wall,
                  side_shader=speckle_shader(pal.wall))
        add_block(model, fr, s - 0.07, s + 0.01, -half - 0.01, half + 0.01,
                  z1, z1 + 0.025, pal.trim)


def gabled_block(model, fr, s0, s1, w, storeys, pal: Palette, *,
                 pitch=0.36, door=False, stepped=True, bays=None):
    """Block from `s0` to `s1`, `w` either side of the frame axis, under
    a roof with its ridge along `s`: a plain gable at `s0` and, at `s1`,
    the end that faces out, a stepped one or a plain one."""
    z_eave = storeys * STOREY
    z_ridge = z_eave + pitch
    add_block(model, fr, s0, s1, -w, w, 0, z_eave, pal.wall,
              side_shader=speckle_shader(pal.wall))
    add_block(model, fr, s0 - 0.015, s1 + 0.015, -w - 0.015, w + 0.015,
              z_eave - 0.04, z_eave, pal.trim)
    o = 0.05
    slope = pitch / w
    s_end = s1 - 0.04 if stepped else s1 + 0.04
    for side in (-1, 1):
        add_roof(model, fr, s0 - 0.02 if stepped else s0 - 0.04, s_end,
                 side * (w + o), 0, z_eave - o * slope, z_ridge, 0.03,
                 pal.roof, shader=course_shader(fr, pal.roof))
    gables = [s0] if stepped else [s0, s1]
    for s in gables:
        add_face(model, [fr.world(s, p, z) for p, z in
                         ((-w, z_eave), (w, z_eave), (0, z_ridge))],
                 pal.wall, outward=fr.world((s0 + s1) / 2, 0, z_eave))
    if stepped:
        stepped_gable(model, fr, s1, w + 0.02, z_eave, z_ridge + 0.08, pal)
    bays = bays or max(2, round((s1 - s0) / 0.3))
    for side in (-1, 1):
        facade(model, fr, (s0, side * w), (s1, side * w), (0, -side), pal,
               storeys=storeys, bays=bays)
    facade(model, fr, (s1, -w), (s1, w), (-1, 0), pal, storeys=storeys,
           bays=max(3, round(2 * w / 0.3)), door=door)
    return z_eave, z_ridge


def side_frame(side, s_centre, fr=RHOMBUS_FRAME):
    """Frame of a wing across `fr`: `s` runs out from `fr`'s axis."""
    return Frame((side * fr.v[0], side * fr.v[1]),
                 origin=fr.world(s_centre, 0, 0)[:2])


def add_beam(model, a, b, w, color, *, up=(0.0, 0.0, 1.0), **kw):
    """Square beam `w` thick between world points `a` and `b`."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    d = unit(d)
    side = np.cross(d, up)
    if math.hypot(*side) < 1e-6:
        side = np.cross(d, (1.0, 0.0, 0.0))
    side = unit(side)
    lift = np.cross(side, d)
    h = w / 2
    ring = [side * h + lift * h, -side * h + lift * h,
            -side * h - lift * h, side * h - lift * h]
    add_solid(model, [tuple(a + r) for r in ring], [tuple(b + r) for r in ring],
              color, **kw)


# --- Bake ---------------------------------------------------------------------

def bake_tiles(model: Model, dims, out_png: Path, *, levels: int = 4
               ) -> list[str]:
    """Write the atlas of `model` sliced over `dims` tiles, one column
    per tile and one row per height; return the `.dat` image lines.
    `levels` is the most heights a tile may take."""
    tiles = render_tiles(model, dims, levels=levels, ambient=AMBIENT)
    keys = footprint(dims)
    rows = max(len(c) for c in tiles.values())
    blank = np.zeros_like(tiles[keys[0]][0])
    entries = [(f"{key}[{z}]",
                lambda c=(tiles[key][z] if z < len(tiles[key]) else blank): c)
               for z in range(rows) for key in keys]
    bake_atlas(out_png=out_png, entries=entries, cols_per_row=len(keys))
    stem = out_png.stem
    return [f"BackImage[0][{y}][{x}][{z}][0][0]={stem}.{z}.{col}"
            for col, (x, y) in enumerate(keys)
            for z in range(len(tiles[(x, y)]))]


def bake_rotations(models: list[Model], out_png: Path) -> list[str]:
    """Write the atlas of a 1x1 building with one model per layout, a
    column per layout and a row per height; return the `.dat` image
    lines (`BackImage` only: nothing on the tile drives under it)."""
    stacks = [render_tiles(m, (1, 1), ambient=AMBIENT)[(0, 0)]
              for m in models]
    rows = max(len(s) for s in stacks)
    blank = np.zeros_like(stacks[0][0])
    entries = [(f"[{lo}][{z}]",
                lambda c=(s[z] if z < len(s) else blank): c)
               for z in range(rows) for lo, s in enumerate(stacks)]
    bake_atlas(out_png=out_png, entries=entries, cols_per_row=len(models))
    return [f"BackImage[{lo}][0][0][{z}][0][0]={out_png.stem}.{z}.{lo}"
            for lo, s in enumerate(stacks) for z in range(len(s))]


def bake_layers(cells: list[dict[str, np.ndarray]], out_png: Path
                ) -> list[str]:
    """Write the back and front cell of each layout of a 1x1 building
    side by side; return the `.dat` image lines."""
    bake_atlas(out_png=out_png,
               entries=[(f"{layer}[{lo}]", lambda c=c[layer]: c)
                        for lo, c in enumerate(cells)
                        for layer in ("back", "front")])
    return [f"{key}Image[{lo}][0][0][0][0][0]={out_png.stem}.0.{2 * lo + i}"
            for lo in range(len(cells))
            for i, key in enumerate(("Back", "Front"))]


def edit_dat(dat: Path, edit) -> None:
    """Rewrite `dat` through `edit`, a function of its list of lines,
    keeping the file's line ends."""
    raw = dat.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    lines = edit(raw.decode(errors="replace").splitlines())
    dat.write_bytes((nl.join(lines) + nl).encode())


DIMS = re.compile(r"(?i)^(dims\s*=\s*\d+\s*,\s*\d+)\s*,\s*\d+")


def set_layouts(dat: Path, layouts: int | dict[str, int]) -> None:
    """`Dims=w,h,n` for the buildings in `dat`: `layouts` is `n`, or
    `n` by object name."""
    def edit(lines):
        out, name = [], None
        for line in lines:
            if line.lower().startswith("name="):
                name = line[len("name="):].strip()
            n = layouts if isinstance(layouts, int) else layouts.get(name)
            out.append(line if n is None
                       else DIMS.sub(rf"\g<1>,{n}", line))
        return out
    edit_dat(dat, edit)


IMAGE_LINE = re.compile(r"^\s*(Back|Front)Image\[|^\s*animation_time=",
                        re.I)


def rewrite_images(dat: Path, images: dict[str, list[str]]) -> None:
    """Replace the image lines of each named object in `dat`, its
    `animation_time`, which only animated the replaced images, and the
    comments among them, which described the old cells."""
    def edit(lines):
        pending = dict(images)
        out, name, in_images = [], None, False
        for line in lines:
            if line.lower().startswith("name="):
                name = line[len("name="):].strip()
            if name in images and IMAGE_LINE.match(line):
                out += pending.pop(name, [])
                in_images = True
                continue
            if in_images and line.startswith("#"):
                continue
            in_images = False
            out.append(line)
        return out
    edit_dat(dat, edit)


def preview(models: list[Model], dims, out: Path, *, levels: int = 4) -> None:
    """The models side by side on grass, as the engine draws them."""
    grass = ground_cell(HexGeom())
    sheets = [composite(render_tiles(m, dims, levels=levels, ambient=AMBIENT),
                        grass)
              for m in models]
    sheet = Image.new("RGBA", (sum(s.width for s in sheets),
                               max(s.height for s in sheets)))
    x = 0
    for s in sheets:
        sheet.alpha_composite(s, (x, sheet.height - s.height))
        x += s.width
    sheet.save(out)
