"""Tiny numpy rasterizer for AI-directed pak128 modeling.

Why this and not OpenSCAD/Blender:

- The scene file must expose lighting, projection, and camera as
  scene-level parameters so the AI agent can edit them as part of
  modeling. OpenSCAD's preview lighting is hardcoded; Blender adds a
  GB of dependencies. A ~150-line numpy rasterizer is enough for
  hard-surface assets (terrain, bridges, low-poly buildings, vehicles).
- The renderer outputs the per-asset 128x128 RGBA PNG that
  `models/tools/diff.py` consumes.
- pak128 dimetric defaults (camera + sun) live here. Per-asset sheet
  offsets (e.g. bridges' (0,32)) shift world z=0 up the screen via
  `screen_center_y`.

Usage in a scene file:

    from render import Scene
    s = Scene(screen_center_y=64)            # bridge tile offset
    s.add_box((-0.5,-0.2,0), (0.5,0.2,0.05), (130,95,60))
    ...
    s.render("out.png")

Conventions:
- World axes: +x, +y horizontal; +z up. Tile spans [-0.5, 0.5] in x,y.
- Camera: yaw 45 deg around z, pitch ~29.5 deg above horizontal
  (calibrated against the texture-lightmap flat tile bbox).
- Sun: from south, 60 deg above horizon (pak128 standard, see
  devdocs/128painting.txt).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

# --- Camera / projection -----------------------------------------------------
YAW = np.deg2rad(45.0)
ELEV = np.deg2rad(29.5)
IMG_SIZE = 128
PIXELS_PER_UNIT = 128.0 / np.sqrt(2.0)
SCREEN_CENTER_X = IMG_SIZE / 2.0
SCREEN_CENTER_Y_GROUND = IMG_SIZE / 2.0 + 32.0  # 96: matches flat-tile bbox

# Sun: from south (-y), 60 deg above horizon. Light travels +y (north) +
# downward.
SUN_DIR = np.array([
    0.0,
    float(np.cos(np.deg2rad(60.0))),
    -float(np.sin(np.deg2rad(60.0))),
])
SUN_DIR /= np.linalg.norm(SUN_DIR)


def world_to_screen(p, screen_center_y=SCREEN_CENTER_Y_GROUND):
    p = np.asarray(p, dtype=np.float64)
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    cy, sy = np.cos(-YAW), np.sin(-YAW)
    x1 = cy * x - sy * y
    y1 = sy * x + cy * y
    z1 = z
    a = -(np.pi / 2.0 - ELEV)
    ca, sa = np.cos(a), np.sin(a)
    x2 = x1
    y2 = ca * y1 - sa * z1
    z2 = sa * y1 + ca * z1
    sx = SCREEN_CENTER_X + x2 * PIXELS_PER_UNIT
    sy_screen = screen_center_y - y2 * PIXELS_PER_UNIT
    return np.stack([sx, sy_screen, z2], axis=-1)


# --- Rasterizer --------------------------------------------------------------
def _quad_normal(verts):
    a = verts[1] - verts[0]
    b = verts[3] - verts[0]
    n = np.cross(a, b)
    norm = np.linalg.norm(n)
    return n / norm if norm > 0 else np.array([0.0, 0.0, 1.0])


def _draw_triangle(rgba, zbuf, verts_screen, color):
    H, W = rgba.shape[:2]
    xs, ys, zs = verts_screen[:, 0], verts_screen[:, 1], verts_screen[:, 2]
    x_min = max(int(np.floor(xs.min())), 0)
    x_max = min(int(np.ceil(xs.max())), W - 1)
    y_min = max(int(np.floor(ys.min())), 0)
    y_max = min(int(np.ceil(ys.max())), H - 1)
    if x_max < x_min or y_max < y_min:
        return
    x0, y0 = xs[0], ys[0]
    x1, y1 = xs[1], ys[1]
    x2, y2 = xs[2], ys[2]
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denom) < 1e-9:
        return
    py, px = np.mgrid[y_min:y_max + 1, x_min:x_max + 1].astype(np.float32) + 0.5
    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denom
    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denom
    w2 = 1.0 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
    region_z = zbuf[y_min:y_max + 1, x_min:x_max + 1]
    region_rgba = rgba[y_min:y_max + 1, x_min:x_max + 1]
    write = inside & (z > region_z)
    region_z[write] = z[write]
    region_rgba[write, 0] = color[0]
    region_rgba[write, 1] = color[1]
    region_rgba[write, 2] = color[2]
    region_rgba[write, 3] = 255


# --- Scene API ---------------------------------------------------------------
class Scene:
    """Append-only collection of vertices and quads, plus a renderer.

    A quad is (i0, i1, i2, i3, color_rgb) with vertices in CCW order seen
    from outside (so the cross product (v1-v0) x (v3-v0) points outward).
    """

    def __init__(self, screen_center_y=SCREEN_CENTER_Y_GROUND, ambient=0.25,
                 sun_dir=None):
        self.verts = []
        self.quads = []
        self.screen_center_y = screen_center_y
        self.ambient = ambient
        self.sun_dir = SUN_DIR if sun_dir is None else sun_dir / np.linalg.norm(sun_dir)

    def add_quad(self, points, color):
        """Append a quad given 4 world-space points (CCW from outside)."""
        base = len(self.verts)
        self.verts.extend(map(tuple, points))
        self.quads.append((base, base + 1, base + 2, base + 3, color))

    def add_box(self, p0, p1, color):
        """Append the 5 outward-facing quads of a box (skips the bottom).

        p0, p1 are opposite corners; p0 < p1 component-wise.
        """
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        b = len(self.verts)
        self.verts.extend([
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ])
        self.quads.extend([
            (b + 4, b + 5, b + 6, b + 7, color),  # top
            (b + 0, b + 1, b + 5, b + 4, color),  # south (-y)
            (b + 2, b + 3, b + 7, b + 6, color),  # north (+y)
            (b + 1, b + 2, b + 6, b + 5, color),  # east  (+x)
            (b + 0, b + 4, b + 7, b + 3, color),  # west  (-x)
        ])

    def render(self, out_path: str, img_size=IMG_SIZE):
        verts = np.asarray(self.verts, dtype=np.float64)
        rgba = np.zeros((img_size, img_size, 4), dtype=np.uint8)
        zbuf = np.full((img_size, img_size), -np.inf, dtype=np.float32)

        for v0, v1, v2, v3, color in self.quads:
            wq = verts[[v0, v1, v2, v3]]
            n = _quad_normal(wq)
            light = max(0.0, float(np.dot(-self.sun_dir, n)))
            shade = self.ambient + (1.0 - self.ambient) * light
            c = (np.array(color) * shade).clip(0, 255).astype(np.uint8)
            sq = world_to_screen(wq, screen_center_y=self.screen_center_y)
            for tri in [(0, 1, 2), (0, 2, 3)]:
                _draw_triangle(rgba, zbuf, sq[list(tri)], c)

        Image.fromarray(rgba, mode="RGBA").save(out_path)
        return rgba
