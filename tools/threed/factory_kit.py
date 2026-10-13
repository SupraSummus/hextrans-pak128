"""Parts for factories, on top of `building_kit`.

Each takes a `Frame` and plan coordinates in it, so a part placed in
`RHOMBUS_FRAME` lands on the rhombus and one placed in a `side_frame`
turns with that wing.  Round parts (chimneys, silos, tanks, logs) are
polygons fine enough to read round at 128 px.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from .building import footprint, tile_centre
from .building_kit import add_beam, edit_dat, speckle_shader, wall_quad
from .hex_synth import HexGeom, hash_noise01
from .render import world_to_screen_hex
from .solids import Frame, add_block, add_face, add_frustum, add_roof

BRICK = (150, 72, 52)
SOOT = (46, 42, 40)
STEEL = (120, 124, 130)
YELLOW = (220, 180, 40)
BARK = (112, 80, 54)
CUT_WOOD = (204, 168, 112)
PLANK = (186, 150, 98)


# --- Ground -------------------------------------------------------------------

def ground_shader(base, *, grain=0.16, patches=()):
    """Plain ground with per-pixel grain; `patches` are `(frame, s, p,
    radius, colour)` discs painted over it with a ragged rim."""
    base = np.array(base, float)

    def shader(wx, wy, sx, sy):
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (1 - grain / 2 + grain * n)[:, None]
        for fr, s, p, r, colour in patches:
            ls, lp = fr.local(wx, wy)
            inside = np.hypot(ls - s, lp - p) < r * (0.85 + 0.3 * n)
            rgb[inside] = np.array(colour, float) * (0.9 + 0.2 * n[inside])[:, None]
        return rgb, np.ones(len(wx), bool)

    return shader


# --- Structures ---------------------------------------------------------------

def fence(model, edges, color, *, h=0.07, post_every=0.18):
    """Posts and two rails along `edges` (world plan point pairs)."""
    for (ax, ay), (bx, by) in edges:
        n = max(1, round(math.dist((ax, ay), (bx, by)) / post_every))
        for k in range(n + 1):
            t = k / n
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            add_beam(model, (x, y, 0.0), (x, y, h), 0.016, color)
        for z in (h * 0.45, h * 0.9):
            add_beam(model, (ax, ay, z), (bx, by, z), 0.01, color)


def chimney(model, fr: Frame, s, p, h, *, r0=0.07, r1=0.05, color=BRICK):
    """Tapered round stack with a dark band at the top; returns the
    world point of its mouth, where smoke leaves."""
    add_frustum(model, fr, s, p, r0, r1, 0.0, h, color, n=12,
                side_shader=speckle_shader(color))
    add_frustum(model, fr, s, p, r1 * 1.15, r1 * 1.1, h - 0.05, h, SOOT,
                n=12)
    return fr.world(s, p, h)


def cylinder(model, fr: Frame, s, p, r, z0, z1, color, *, roof="flat",
             n=16, shader=None):
    """Upright tank or silo; `roof` is `flat`, `cone` or `dome`."""
    add_frustum(model, fr, s, p, r, r, z0, z1, color, n=n,
                side_shader=shader or speckle_shader(color))
    shade = tuple(int(c * 0.9) for c in color)
    if roof == "cone":
        add_frustum(model, fr, s, p, r * 1.03, 0.0, z1, z1 + r * 0.6, shade,
                    n=n)
    elif roof == "dome":
        steps = 4
        for k in range(steps):
            a0, a1 = k / steps * math.pi / 2, (k + 1) / steps * math.pi / 2
            add_frustum(model, fr, s, p, r * math.cos(a0), r * math.cos(a1),
                        z1 + r * 0.5 * math.sin(a0),
                        z1 + r * 0.5 * math.sin(a1), shade, n=n)


def legs(model, fr: Frame, s, p, r, h, color=STEEL):
    """Four legs and a ring under a raised silo."""
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        x, y = s + r * math.cos(a), p + r * math.sin(a)
        add_beam(model, fr.world(x, y, 0.0), fr.world(x, y, h), 0.03, color)
    for k in range(4):
        a0, a1 = math.pi / 4 + k * math.pi / 2, math.pi / 4 + (k + 1) * math.pi / 2
        add_beam(model, fr.world(s + r * math.cos(a0), p + r * math.sin(a0), h * 0.5),
                 fr.world(s + r * math.cos(a1), p + r * math.sin(a1), h * 0.5),
                 0.018, color)


def open_shed(model, fr: Frame, s0, s1, w, h, pal, *, pitch=0.16, posts=4):
    """Posts along both sides under a pitched roof, open all round."""
    for side in (-1, 1):
        for s in np.linspace(s0 + 0.03, s1 - 0.03, posts):
            add_block(model, fr, s - 0.018, s + 0.018, side * w - 0.018,
                      side * w + 0.018, 0.0, h, pal.trim)
        add_roof(model, fr, s0 - 0.04, s1 + 0.04, side * (w + 0.05), 0.0,
                 h - 0.02, h + pitch, 0.025, pal.roof,
                 shader=speckle_shader(pal.roof))


def sawtooth_roof(model, fr: Frame, s0, s1, p0, p1, z, pal, *, teeth=4,
                  rise=0.14, glass=(150, 180, 200)):
    """North-light roof over the block `s0..s1` x `p0..p1` at `z`: each
    tooth rises along `p` and drops back behind a glazed face."""
    pitch = (p1 - p0) / teeth
    for k in range(teeth):
        a, b = p0 + k * pitch, p0 + (k + 1) * pitch
        add_roof(model, fr, s0, s1, a, b, z, z + rise, 0.02, pal.roof,
                 shader=speckle_shader(pal.roof))
        add_face(model, [fr.world(s0, b, z), fr.world(s1, b, z),
                         fr.world(s1, b, z + rise), fr.world(s0, b, z + rise)],
                 glass, outward=fr.world((s0 + s1) / 2, a, z))
        for s in (s0, s1):
            add_face(model, [fr.world(s, a, z), fr.world(s, b, z),
                             fr.world(s, b, z + rise)], pal.wall,
                     outward=fr.world((s0 + s1) / 2, (a + b) / 2, z))


def conveyor(model, a, b, w=0.06, color=STEEL):
    """Inclined belt from world point `a` to `b`, on trestles."""
    add_beam(model, a, b, w, color)
    a, b = np.asarray(a, float), np.asarray(b, float)
    for t in (0.35, 0.7):
        top = a + (b - a) * t
        add_beam(model, (top[0], top[1], 0.0), top, 0.025, color)


def gantry(model, fr: Frame, s0, s1, w, h, color=YELLOW):
    """A crane bridge `2w` wide across `p` on legs at `s0` and `s1`."""
    for s in (s0, s1):
        for side in (-1, 1):
            add_beam(model, fr.world(s, side * w, 0.0),
                     fr.world(s, side * w, h), 0.04, color)
        add_beam(model, fr.world(s, -w, h), fr.world(s, w, h), 0.04, color)
    for side in (-0.4, 0.4):
        add_beam(model, fr.world(s0, side * w, h + 0.03),
                 fr.world(s1, side * w, h + 0.03), 0.05, color)
    add_block(model, fr, (s0 + s1) / 2 - 0.07, (s0 + s1) / 2 + 0.07,
              -0.08, 0.08, h + 0.05, h + 0.13, color)


# --- Stock --------------------------------------------------------------------

def log_pile(model, fr: Frame, s, p, length, *, rows=3, r=0.035,
             seed=0):
    """Logs along `s`, stacked in a pyramid across `p`."""
    for row in range(rows):
        count = rows - row
        z = r + row * r * 1.7
        for k in range(count):
            q = p + (k - (count - 1) / 2) * r * 2.05
            key = np.array([seed * 31 + row * 7 + k], np.uint32)
            jitter = (hash_noise01(key, key + 5)[0] - 0.5) * 0.06
            log(model, fr, s + jitter, q, z, length, r)


def log(model, fr: Frame, s, p, z, length, r, n=8, *, bark=BARK,
        end=CUT_WOOD):
    """A log (or a paper roll) along `s` centred on `(s, p, z)`, cut
    ends showing."""
    ring = [(p + r * math.cos(2 * math.pi * k / n),
             z + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    s0, s1 = s - length / 2, s + length / 2
    for (p0, z0), (p1, z1) in zip(ring, ring[1:] + ring[:1]):
        add_face(model, [fr.world(s0, p0, z0), fr.world(s1, p0, z0),
                         fr.world(s1, p1, z1), fr.world(s0, p1, z1)],
                 bark, outward=fr.world(s, p, z))
    for se, out in ((s0, s0 - 1), (s1, s1 + 1)):
        for k in range(1, n - 1, 2):
            pts = [ring[0], ring[k], ring[k + 1], ring[min(k + 2, n - 1)]]
            add_face(model, [fr.world(se, q, zz) for q, zz in pts], end,
                     outward=fr.world(se - (out - se), p, z))


def plank_stack(model, fr: Frame, s, p, length, width, h, *, layers=4,
                color=PLANK):
    """Sawn timber in layers on bearers, gaps between the layers."""
    lh = h / layers
    for k in range(layers):
        z0 = k * lh + 0.01
        add_block(model, fr, s - length / 2, s + length / 2, p - width / 2,
                  p + width / 2, z0 + lh * 0.25, z0 + lh, color,
                  side_color=tuple(int(c * 0.8) for c in color))
        for ds in (-length * 0.35, 0.0, length * 0.35):
            add_block(model, fr, s + ds - 0.01, s + ds + 0.01,
                      p - width / 2, p + width / 2, z0, z0 + lh * 0.25,
                      (90, 70, 52))


def heap(model, fr: Frame, s, p, r, h, color):
    """A loose heap (sand, coal, gravel): stacked flattened cones."""
    shader = speckle_shader(color)
    for rr, z0, z1 in ((1.0, 0.0, 0.42), (0.7, 0.36, 0.76), (0.38, 0.7, 1.0)):
        add_frustum(model, fr, s, p, r * rr, r * rr * 0.75, z0 * h, z1 * h,
                    color, n=14, top_shader=shader, side_shader=shader)


def crate_stack(model, fr: Frame, s, p, *, n=3, size=0.07,
                color=(150, 104, 58)):
    for k in range(n):
        add_block(model, fr, s - size, s + size, p - size + k * 0.02,
                  p + size + k * 0.02, k * size * 1.6, (k + 1) * size * 1.6,
                  color, side_color=tuple(int(c * 0.82) for c in color))


def windows_band(model, fr: Frame, a, b, inward, z0, z1, n, glass,
                 frame=(230, 226, 214)):
    """`n` windows evenly along the wall from `a` to `b`."""
    length = math.dist(a, b)
    d = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    pitch = length / n
    for k in range(n):
        c = (k + 0.5) * pitch
        w = pitch * 0.3
        p0 = (a[0] + d[0] * (c - w), a[1] + d[1] * (c - w))
        p1 = (a[0] + d[0] * (c + w), a[1] + d[1] * (c + w))
        wall_quad(model, fr, p0, p1, z0 - 0.01, z1 + 0.01, 0.006, frame,
                  inward)
        wall_quad(model, fr, p0, p1, z0, z1, 0.01, glass, inward)


def lorry(model, fr: Frame, s, p, *, cab=(170, 40, 36), box=(214, 210, 200),
          length=0.36):
    """A box lorry along `s`, cab towards `+s`."""
    w = 0.07
    s0, s1 = s - length / 2, s + length / 2
    add_block(model, fr, s0, s1, p - w, p + w, 0.02, 0.04, SOOT)
    for ds in (0.06, length * 0.55, length * 0.8):
        add_block(model, fr, s0 + ds - 0.022, s0 + ds + 0.022, p - w,
                  p + w, 0.0, 0.03, SOOT)
    add_block(model, fr, s0, s1 - 0.1, p - w, p + w, 0.04, 0.17, box,
              side_color=tuple(int(c * 0.88) for c in box))
    add_block(model, fr, s1 - 0.09, s1, p - w, p + w, 0.04, 0.13, cab,
              side_color=tuple(int(c * 0.85) for c in cab))
    add_block(model, fr, s1 - 0.004, s1 + 0.002, p - w + 0.012,
              p + w - 0.012, 0.09, 0.125, (70, 86, 104))


# --- Smoke --------------------------------------------------------------------

def smoke_lines(mouth, dims) -> list[str]:
    """`SmokeTile` and `SmokeOffset` for smoke leaving the world point
    `mouth`: the footprint tile under it, and the screen offset from
    that tile's centre in the engine's offset units (two pixels at the
    128 px raster, `fabrik_t::smoke`)."""
    geom = HexGeom()
    x, y = min(footprint(dims), key=lambda t: math.dist(tile_centre(*t),
                                                         mouth[:2]))
    cx, cy = tile_centre(x, y)
    rel = np.array([mouth[0] - cx, mouth[1] - cy, mouth[2]])
    sx, sy, _ = world_to_screen_hex(rel, geom) - \
        world_to_screen_hex(np.zeros(3), geom)
    scale = 64 / geom.w
    return [f"SmokeTile[0]={x},{y}",
            f"SmokeOffset[0]={round(sx * scale)},{round(sy * scale)}"]


SMOKE_LINE = re.compile(r"(?i)^\s*Smoke(Tile|Offset)\[0\]\s*=")


def set_smoke(dat: Path, lines: list[str]) -> None:
    """Replace the `SmokeTile[0]` / `SmokeOffset[0]` lines of `dat`."""
    keys = {line.split("[")[0].lower(): line for line in lines}

    def edit(old):
        return [keys[f"smoke{m.group(1).lower()}"]
                if (m := SMOKE_LINE.match(line)) else line for line in old]
    edit_dat(dat, edit)
