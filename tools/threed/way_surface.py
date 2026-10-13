"""Centreline fields for ways painted as one flat surface per cell.

A painted way (see `devdocs/hex-road-style.md`) colours every pixel
from where it sits relative to the way's centreline, measured in plan
view.  This module owns the centreline shapes; the asset decides what
the bands look like.

Shapes, by the set of edges the way leaves the tile through:

- two opposite edges: a straight between the midpoints;
- two other edges: a circular arc tangent to the radial legs at both
  midpoints, as in pak128's curve cells;
- one edge: a leg from the midpoint, cut square at the centre;
- three or more: one such leg per edge, the gaps between their square
  ends filled flat and the inside corners between legs bevelled, so
  every outer kerb stays straight.

`Field` holds, per pixel:

- `d` — distance to the centreline, so `d < w` is a band of
  half-width `w` that meets every edge it leaves through at exactly
  `w` either side of the midpoint (which keeps neighbouring cells
  seamless);
- `s` — distance along the nearest path from its first edge midpoint;
- `length` — the path length dash patterns are fitted to; a leg
  counts as the straight it continues beyond its edge;
- `v` — signed lateral offset from that path (left positive);
- `leg_end` — True on legs that stop inside the tile.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .way import HEX_OPPOSITE_EDGE, edge_midpoint, edge_unit_dir

APOTHEM = math.sqrt(3) / 2
STRAIGHT = 2 * APOTHEM


@dataclass
class Field:
    d: np.ndarray
    s: np.ndarray
    v: np.ndarray
    length: np.ndarray
    leg_end: np.ndarray


def _segment(px, py, a, b):
    """Distance, along-coordinate and signed lateral offset to segment a→b."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    rx, ry = px - ax, py - ay
    t = np.clip(rx * ux + ry * uy, 0.0, length)
    d = np.hypot(px - (ax + ux * t), py - (ay + uy * t))
    v = ux * ry - uy * rx
    return d, t, v, length


def _arc(px, py, edge_a, edge_b):
    """Arc tangent to the radial legs at both edge midpoints; its centre
    is where the two edge lines meet."""
    ma, mb = edge_midpoint(edge_a), edge_midpoint(edge_b)
    ua, ub = edge_unit_dir(edge_a), edge_unit_dir(edge_b)
    det = ub[0] * ua[1] - ua[0] * ub[1]
    k = ((mb[0] - ma[0]) * -ub[1] + (mb[1] - ma[1]) * ub[0]) / det
    ox, oy = ma[0] + k * ua[0], ma[1] + k * ua[1]
    radius = math.hypot(ma[0] - ox, ma[1] - oy)
    ang_a = math.atan2(ma[1] - oy, ma[0] - ox)
    ang_b = math.atan2(mb[1] - oy, mb[0] - ox)
    turn = math.copysign(1.0, (ang_b - ang_a + math.pi) % math.tau - math.pi)
    rel = (np.arctan2(py - oy, px - ox) - ang_a + math.pi) % math.tau - math.pi
    r = np.hypot(px - ox, py - oy)
    sweep = abs((ang_b - ang_a + math.pi) % math.tau - math.pi)
    # Left of travel is towards the arc centre for a left turn.
    return (np.abs(r - radius), rel * turn * radius, (radius - r) * turn,
            sweep * radius)


@dataclass
class _Leg:
    """Leg from an edge midpoint `m` towards the centre along unit `u`;
    `n` is its length, `t`/`v` the along/lateral coordinates."""
    m: tuple[float, float]
    u: tuple[float, float]
    n: float
    t: np.ndarray
    v: np.ndarray

    def side_towards(self, other: "_Leg") -> float:
        """Sign of `v` on the side of this leg that faces `other`."""
        dx, dy = other.m[0] - self.m[0], other.m[1] - self.m[1]
        return math.copysign(1.0, self.u[0] * dy - self.u[1] * dx)


def _leg(edge, px, py) -> _Leg:
    m = edge_midpoint(edge)
    n = math.hypot(*m)
    u = (-m[0] / n, -m[1] / n)
    rx, ry = px - m[0], py - m[1]
    return _Leg(m, u, n, rx * u[0] + ry * u[1], u[0] * ry - u[1] * rx)


def _hull_distance(ks, r, px, py):
    """Signed distance to the convex polygon with vertices at radius `r`
    in the directions `k·60°` for each `k` in `ks`."""
    pts = [(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3))
           for k in sorted(ks)]
    inside, outside = -np.inf, np.inf
    for a, b in zip(pts, pts[1:] + pts[:1]):
        nx, ny = b[1] - a[1], a[0] - b[0]          # outward, CCW order
        n = math.hypot(nx, ny)
        inside = np.maximum(inside, ((px - a[0]) * nx + (py - a[1]) * ny) / n)
        outside = np.minimum(outside, _segment(px, py, a, b)[0])
    return np.where(inside <= 0, inside, outside)


def _legs_field(edges, px, py, *, band_w, bevel):
    legs = [_leg(e, px, py) for e in edges]
    square = np.stack([np.maximum(np.abs(g.v), g.t - g.n) for g in legs])
    nearest = np.argmin(square, axis=0)
    s = np.choose(nearest, [g.t for g in legs])
    v = np.choose(nearest, [g.v for g in legs])
    if len(legs) == 1:
        return square[0], s, v

    # A leg reaches the centre; beyond it the hull of the legs' square
    # ends takes over.  Its vertices sit at `band_w` along each leg's
    # perpendiculars, which on the hex grid are multiples of 60°.
    d = np.min([np.where(g.t <= g.n, np.abs(g.v), np.inf) for g in legs],
               axis=0)
    ks = set()
    for g in legs:
        k = round(math.degrees(math.atan2(g.u[1], g.u[0])) / 60 + 1.5)
        ks |= {k % 6, (k + 3) % 6}
    d = np.minimum(d, _hull_distance(ks, band_w, px, py) + band_w)

    # Bevel the inside corner between each pair of non-opposite legs.
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            if a.u[0] * b.u[0] + a.u[1] * b.u[1] < -0.99:
                continue
            va, vb = a.side_towards(b) * a.v, b.side_towards(a) * b.v
            corner = (va >= 0) & (vb >= 0) & (a.t <= a.n) & (b.t <= b.n)
            d = np.where(corner,
                         np.minimum(d, (va + vb - bevel) * math.sqrt(0.5)), d)
    return d, s, v


def centreline_field(edges, px, py, *, band_w: float, bevel: float) -> Field:
    """Field for a way leaving the tile through `edges` (names from
    `HEX_EDGES`).  `band_w` is the half-width of the band the junction
    fill is sized for; `bevel` the size of its cut inside corners."""
    px = np.asarray(px, dtype=np.float64)
    py = np.asarray(py, dtype=np.float64)
    ones = np.ones_like(px)
    if len(edges) == 2 and HEX_OPPOSITE_EDGE[edges[0]] == edges[1]:
        d, s, v, length = _segment(px, py, edge_midpoint(edges[0]),
                                   edge_midpoint(edges[1]))
        return Field(d, s, v, ones * length, ones < 0)
    if len(edges) == 2:
        d, s, v, length = _arc(px, py, *edges)
        return Field(d, s, v, ones * length, ones < 0)
    d, s, v = _legs_field(edges, px, py, band_w=band_w, bevel=bevel)
    return Field(d, s, v, ones * STRAIGHT, ones > 0)


def straight_field(path, px, py) -> Field:
    """Field for one `way_topology.StraightPath` (square verification)."""
    d, s, v, length = _segment(np.asarray(px, float), np.asarray(py, float),
                               path.start, path.end)
    return Field(d, s, v, np.full_like(d, length), np.zeros_like(d, bool))


def dashes(s, length, *, period: float, duty: float = 0.5):
    """Mask of a dash pattern along `s`, gaps centred on the path ends.
    The period is fitted to a whole number per `length`, so dashes meet
    the neighbouring cell's."""
    p = length / np.maximum(1, np.round(length / period))
    return np.abs((s / p) % 1.0 - 0.5) < duty / 2


def hex_cover_quad(z: float):
    """A plan-view quad covering the whole hex at height `z`; the hex
    camera's plan clip trims it to the tile."""
    return [(-1.0, -1.0, z), (1.0, -1.0, z), (1.0, 1.0, z), (-1.0, 1.0, z)]
