"""A multi-tile building's plot, in any footprint and layout, and the
small things that stand on one.

`Site(dims, layout)` gives the frame a scene builds in: origin on the
footprint's centre, `s` along its long diagonal towards the camera
(away from it for layouts 2 and 3, the half turns of 0 and 1), `p`
across.  `box(aspect)` is the largest rectangle of that shape inside the
footprint, so a scene written for a box fits a 1x2 as well as a 3x3.
The engine swaps a footprint's extents on odd layouts; `Site` does too.

`ground` paints the plot through a shader that sees frame coordinates;
pixels it leaves out show the map's own ground.  Trees, cars, ponds,
flower beds and the fence are the parts most plots share.
"""
from __future__ import annotations

import math

import numpy as np

from .building import tile_centre
from .building_kit import (
    add_beam, footprint_outline, outside_distance, speckle_shader)
from .hex_synth import hash_noise01
from .render import Model
from .solids import Frame, add_block, add_face, add_frustum, add_prism

TRUNK = (90, 64, 40)
CONIFER = (44, 84, 44)
LEAVES = (78, 120, 50)
POPLAR = (70, 112, 48)
WATER = (60, 96, 140)
CARS = ((190, 40, 50), (40, 80, 170), (230, 200, 60), (60, 140, 80),
        (220, 220, 214), (140, 50, 140), (40, 40, 44))


class Site:
    def __init__(self, dims, layout: int = 0, margin: float = 0.06):
        self.dims = (dims[1], dims[0]) if layout % 2 else tuple(dims)
        dx, dy = self.dims
        a, b = tile_centre(0, 0), tile_centre(dx - 1, dy - 1)
        if (dx, dy) == (1, 1):
            u = (0.5, -math.sqrt(3) / 2)
        else:
            u = (b[0] - a[0], b[1] - a[1])
        if layout >= 2:
            u = (-u[0], -u[1])
        self.fr = Frame(u, origin=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        self.margin = margin
        self._boxes: dict[float, tuple[float, float]] = {}

    def inside(self, s, p, margin=None) -> np.ndarray:
        wx, wy, _ = self.fr.world(np.asarray(s, float), np.asarray(p, float), 0)
        m = self.margin if margin is None else margin
        return outside_distance(self.dims, wx, wy) > m

    def box(self, aspect: float = 1.0) -> tuple[float, float]:
        """Half-lengths `(S, P)`, `P = aspect * S`, of the largest such
        rectangle round the origin inside the footprint."""
        if aspect not in self._boxes:
            t = np.linspace(-1, 1, 21)
            ring_s = np.concatenate([t, t, -np.ones(21), np.ones(21)])
            ring_p = np.concatenate([-np.ones(21), np.ones(21), t, t])
            lo, hi = 0.0, 6.0
            for _ in range(30):
                mid = (lo + hi) / 2
                if self.inside(ring_s * mid, ring_p * mid * aspect).all():
                    lo = mid
                else:
                    hi = mid
            self._boxes[aspect] = (lo, lo * aspect)
        return self._boxes[aspect]

    def ground(self, model: Model, paint) -> None:
        """`paint(s, p, n, edge)` returns `(rgb, keep)` for frame points,
        `n` per-pixel noise in [0, 1), `edge` the distance to the
        footprint's border."""
        fr, dims = self.fr, self.dims

        def shader(wx, wy, sx, sy):
            s, p = fr.local(wx, wy)
            n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
            edge = outside_distance(dims, wx, wy)
            rgb, keep = paint(s, p, n, edge)
            return rgb, keep & (edge > 0.0)

        r = 2.0 * max(dims) + 1
        pts = [fr.world(s, p, 0.002) for s, p in
               ((-r, -r), (r, -r), (r, r), (-r, r))]
        add_face(model, pts, (0, 0, 0), outward=fr.world(0, 0, -1),
                 shader=shader)

    def tile_points(self) -> list[tuple[float, float]]:
        """The frame `(s, p)` of each footprint tile's centre."""
        from .building import footprint
        return [tuple(float(v) for v in self.fr.local(*tile_centre(x, y)))
                for x, y in footprint(self.dims)]

    def edge_points(self, inset=0.3, step=0.6):
        """Frame points round the plot, `inset` in from its border and
        about `step` apart: where a row of trees or bushes goes."""
        out = []
        for a, b in footprint_outline(self.dims, inset=inset):
            n = max(1, round(math.dist(a, b) / step))
            for k in range(n):
                x = a[0] + (b[0] - a[0]) * (k + 0.5) / n
                y = a[1] + (b[1] - a[1]) * (k + 0.5) / n
                out.append(tuple(float(v) for v in self.fr.local(x, y)))
        return out

    def border_trees(self, model, *, kind="mix", inset=0.3, step=0.6,
                     keep=None, seed=0):
        """Trees along the border; `keep(s, p)` may veto a spot (a gate,
        a car park)."""
        for k, (s, p) in enumerate(self.edge_points(inset, step)):
            if keep is not None and not keep(s, p):
                continue
            pick = (k * 7 + seed) % 5
            if kind == "conifer" or (kind == "mix" and pick == 0):
                conifer(model, self.fr, s, p, 0.5 + 0.08 * (k % 3))
            elif kind == "poplar":
                poplar(model, self.fr, s, p, 0.7 + 0.08 * (k % 2))
            elif kind == "bush":
                add_frustum(model, self.fr, s, p, 0.1, 0.06, 0, 0.12,
                            (64, 104, 46), n=8,
                            side_shader=speckle_shader((64, 104, 46)))
            else:
                broadleaf(model, self.fr, s, p, 0.45 + 0.08 * (k % 3))

    def fence(self, model, colour=(110, 80, 52), height=0.16, inset=0.1,
              posts=4, rails=(0.06, 0.13)):
        for (ax, ay), (bx, by) in footprint_outline(self.dims, inset=inset):
            for z in rails:
                add_beam(model, (ax, ay, z), (bx, by, z), 0.012, colour)
            for t in np.linspace(0, 1, posts + 1)[:-1]:
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                add_beam(model, (x, y, 0.0), (x, y, height), 0.02,
                         tuple(int(c * 0.8) for c in colour))

    def wall(self, model, colour, height=0.2, inset=0.08, w=0.05,
             shader=None):
        """A solid wall round the plot, a beam per hex edge."""
        for a, b in footprint_outline(self.dims, inset=inset):
            _wall_segment(model, a, b, height, w, colour, shader)


def _wall_segment(model, a, b, height, w, colour, shader):
    fr = Frame((b[0] - a[0], b[1] - a[1]), origin=a)
    length = math.dist(a, b)
    add_block(model, fr, -w / 2, length + w / 2, -w / 2, w / 2, 0.0, height,
              colour, side_shader=shader)


# --- Things on a plot ---------------------------------------------------------

def conifer(model, fr, s, p, height=0.7):
    k = height / 0.7
    add_frustum(model, fr, s, p, 0.03, 0.03, 0, 0.08, TRUNK, n=6)
    for r, z0, z1 in ((0.18, 0.06, 0.42), (0.14, 0.28, 0.6), (0.09, 0.46, 0.75)):
        add_frustum(model, fr, s, p, r * k, 0.0, z0 * k, z1 * k, CONIFER, n=10)


def broadleaf(model, fr, s, p, height=0.6, colour=LEAVES):
    k = height / 0.6
    add_frustum(model, fr, s, p, 0.03, 0.025, 0, 0.22 * k, TRUNK, n=6)
    for r0, r1, z0, z1 in ((0.08, 0.2, 0.16, 0.34), (0.2, 0.17, 0.34, 0.48),
                           (0.17, 0.04, 0.48, 0.62)):
        add_frustum(model, fr, s, p, r0 * k, r1 * k, z0 * k, z1 * k, colour,
                    n=10, side_shader=speckle_shader(colour))


def poplar(model, fr, s, p, height=0.8):
    add_frustum(model, fr, s, p, 0.02, 0.02, 0, 0.1, TRUNK, n=6)
    add_frustum(model, fr, s, p, 0.05, 0.08, 0.08, 0.4 * height / 0.8 + 0.08,
                POPLAR, n=8)
    add_frustum(model, fr, s, p, 0.08, 0.0, 0.4 * height / 0.8 + 0.08, height,
                POPLAR, n=8)


def palm(model, fr, s, p, height=0.6):
    add_frustum(model, fr, s, p, 0.025, 0.018, 0, height, (120, 96, 66), n=6)
    for k in range(6):
        a = math.pi * k / 3
        tip = fr.world(s + 0.22 * math.cos(a), p + 0.22 * math.sin(a),
                       height - 0.1)
        add_beam(model, fr.world(s, p, height), tip, 0.03, (70, 120, 50))


def car(model, fr, s, p, colour, along_s=False):
    c = Frame(fr.u if along_s else fr.v, origin=fr.world(s, p, 0)[:2])
    add_block(model, c, -0.1, 0.1, -0.045, 0.045, 0.015, 0.06, colour)
    add_block(model, c, -0.05, 0.05, -0.04, 0.04, 0.06, 0.09,
              tuple(int(x * 0.7) for x in colour))


def pond(model, fr, s, p, rs, rp, colour=WATER, n=16):
    """A flat oval of water with a stone rim."""
    ring = [(s + rs * math.cos(2 * math.pi * k / n),
             p + rp * math.sin(2 * math.pi * k / n)) for k in range(n)]
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        _wall_segment(model, fr.world(*a, 0)[:2], fr.world(*b, 0)[:2], 0.03,
                      0.03, (170, 162, 146), None)
    add_prism(model, fr, ring, 0.0, 0.015, colour)


def flower_bed(model, fr, s, p, rs, rp, seed=0):
    colours = ((200, 60, 70), (230, 200, 60), (220, 120, 180), (240, 240, 230))
    add_block(model, fr, s - rs, s + rs, p - rp, p + rp, 0.0, 0.02,
              (96, 72, 50))
    for i, ds in enumerate(np.linspace(-rs + 0.03, rs - 0.03, 4)):
        for j, dp in enumerate(np.linspace(-rp + 0.03, rp - 0.03, 3)):
            c = colours[(i + j + seed) % len(colours)]
            add_frustum(model, fr, s + ds, p + dp, 0.03, 0.02, 0.02, 0.05, c,
                        n=6)


def lamp_post(model, fr, s, p, height=0.32):
    add_frustum(model, fr, s, p, 0.008, 0.008, 0.0, height, (50, 50, 54), n=6)
    add_frustum(model, fr, s, p, 0.025, 0.015, height, height + 0.03,
                (236, 230, 190), n=6)


def flagpole(model, fr, s, p, colour=(40, 80, 170), height=0.7):
    add_frustum(model, fr, s, p, 0.01, 0.008, 0.0, height, (200, 200, 204),
                n=6)
    add_block(model, fr, s - 0.005, s + 0.005, p + 0.01, p + 0.17,
              height - 0.14, height - 0.03, colour)


# --- Bake ---------------------------------------------------------------------

def bake_site(build, dims, layouts: int, out_png) -> list[str]:
    """Bake `build(site) -> Model` for each layout into one atlas, a row
    per layout and height and a column per tile; return the `.dat` image
    lines.  Heights grow until the tallest tile fits."""
    from .bespoke import bake_atlas
    from .building import footprint, render_tiles
    from .building_kit import AMBIENT

    rows, lines, entries = 0, [], []
    for layout in range(layouts):
        site = Site(dims, layout)
        model = build(site)
        for levels in range(4, 16):
            try:
                tiles = render_tiles(model, site.dims, levels=levels,
                                     ambient=AMBIENT)
                break
            except ValueError as e:
                if "top" not in str(e):
                    raise
        keys = footprint(site.dims)
        height = max(len(c) for c in tiles.values())
        blank = np.zeros_like(tiles[keys[0]][0])
        for z in range(height):
            for col, key in enumerate(keys):
                cells = tiles[key]
                entries.append((f"[{layout}]{key}[{z}]",
                                lambda c=(cells[z] if z < len(cells) else blank):
                                c))
                if z < len(cells):
                    lines.append(f"BackImage[{layout}][{key[1]}][{key[0]}][{z}]"
                                 f"[0][0]={out_png.stem}.{rows + z}.{col}")
        rows += height
    bake_atlas(out_png=out_png, entries=entries,
               cols_per_row=dims[0] * dims[1])
    return lines
