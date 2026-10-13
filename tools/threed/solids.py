"""Solids for 3D scenes, placed in a plan-view frame.

`Frame` maps `(s, p, z)` to world: `s` along a unit direction `u`,
`p` across it (left of `u` positive), from an origin.  Every helper
takes plan corners in frame coordinates, so a scene is written once
in its own frame and placed by choosing the frame.
"""
from __future__ import annotations

import math

import numpy as np

from .render import Model


class Frame:
    def __init__(self, u, origin=(0.0, 0.0)):
        n = math.hypot(*u)
        self.u = (u[0] / n, u[1] / n)
        self.v = (-self.u[1], self.u[0])
        self.origin = origin

    def world(self, s, p, z):
        return (self.origin[0] + s * self.u[0] + p * self.v[0],
                self.origin[1] + s * self.u[1] + p * self.v[1], z)

    def local(self, wx, wy):
        """Frame `(s, p)` of world plan points (arrays welcome)."""
        dx, dy = wx - self.origin[0], wy - self.origin[1]
        return (dx * self.u[0] + dy * self.u[1],
                dx * self.v[0] + dy * self.v[1])

    def front_sign(self) -> int:
        """Sign of `p` on the side nearer the camera (lower world y);
        0 when both sides are equally near."""
        if abs(self.v[1]) < 1e-9:
            return 0
        return -1 if self.v[1] > 0 else 1


def add_face(model: Model, pts, color, layer="back", *, outward=None,
             shader=None):
    """Planar face of 3 or 4 world points, wound so its normal points
    away from `outward` (a point inside the solid) when given."""
    pts = list(pts)
    if len(pts) == 3:
        pts.append(pts[2])
    if outward is not None:
        n = np.cross(np.subtract(pts[1], pts[0]), np.subtract(pts[3], pts[0]))
        if np.dot(n, np.mean(pts, axis=0) - outward) < 0:
            pts = pts[::-1]
    model.add_quad(pts, color, layer=layer, shader=shader)


def add_solid(model: Model, bottom, top, color, layer="back", *,
              top_shader=None, side_color=None, side_shader=None):
    """Solid between two rings of world points (same order, same
    length): the top face (fanned from its first point) and the sides.
    The bottom is never seen."""
    centre = np.mean(list(bottom) + list(top), axis=0)
    n = len(top)
    for i in range(1, n - 1, 2):
        add_face(model, [top[0], top[i], top[i + 1], top[min(i + 2, n - 1)]],
                 color, layer, outward=centre, shader=top_shader)
    for i in range(n):
        j = (i + 1) % n
        add_face(model, [bottom[i], bottom[j], top[j], top[i]],
                 side_color or color, layer, outward=centre,
                 shader=side_shader)


def add_prism(model, fr: Frame, poly, z0, z1, color, layer="back", **kw):
    """Vertical prism over a plan polygon of (s, p) corners."""
    add_solid(model, [fr.world(s, p, z0) for s, p in poly],
              [fr.world(s, p, z1) for s, p in poly], color, layer, **kw)


def add_block(model, fr: Frame, s0, s1, p0, p1, z0, z1, color,
              layer="back", **kw):
    """Box aligned with the frame."""
    add_prism(model, fr, [(s0, p0), (s1, p0), (s1, p1), (s0, p1)],
              z0, z1, color, layer, **kw)


def add_roof(model, fr: Frame, s0, s1, p0, p1, z_p0, z_p1, t, color,
             layer="back", shader=None, **kw):
    """Roof slab `t` thick rising from `z_p0` at `p0` to `z_p1` at `p1`."""
    poly = [(s0, p0), (s1, p0), (s1, p1), (s0, p1)]
    zs = [z_p0, z_p0, z_p1, z_p1]
    add_solid(model, [fr.world(s, p, z) for (s, p), z in zip(poly, zs)],
              [fr.world(s, p, z + t) for (s, p), z in zip(poly, zs)],
              color, layer, top_shader=shader, **kw)


def ngon(cs, cp, r, n=8, phase=0.0):
    """Plan corners of a regular `n`-gon around `(cs, cp)`."""
    return [(cs + r * math.cos(phase + 2 * math.pi * k / n),
             cp + r * math.sin(phase + 2 * math.pi * k / n))
            for k in range(n)]


def add_frustum(model, fr: Frame, cs, cp, r0, r1, z0, z1, color,
                layer="back", n=8, **kw):
    """Vertical frustum (cone when `r1` is 0) over a regular n-gon."""
    add_solid(model, [fr.world(s, p, z0) for s, p in ngon(cs, cp, r0, n)],
              [fr.world(s, p, z1) for s, p in ngon(cs, cp, max(r1, 1e-4), n)],
              color, layer, **kw)
