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
    s.render("out.png")                      # square dimetric
    s.render("out_hex.png", projection="hex")  # hex flat-top

Conventions:
- World axes: +x, +y horizontal; +z up. Tile spans [-0.5, 0.5] in x,y.
- Square camera: yaw 45 deg around z, pitch ~29.5 deg above horizontal
  (calibrated against the texture-lightmap flat tile bbox).
- Hex camera: flat-top, no yaw — world +x is screen-right, world +y is
  screen-up.  Anchored to the engine's `HexGeom` (`tools/3d/hex_synth.py`,
  mirroring `synth_geometry.h`): the unit hex (radius 0.5 in world)
  maps onto the engine's W-wide × W/2-tall flat-top silhouette so a 3D
  scene shares one geometry source with the parametric ground bakers.
- Sun: from south, 60 deg above horizon (pak128 standard, see
  devdocs/128painting.txt).  Same world-space sun direction in both
  projections; what differs is only the projection of geometry.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from hex_synth import (
    DEFAULT_W, HexGeom, hash_noise01, hex_height_raster_scale_y
)

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


# --- Hex projection ----------------------------------------------------------
# Anchored to `HexGeom` (mirror of `synth_geometry.h`).  The unit hex
# (corners at angles 0,60,...,300 from origin, radius 0.5 in world) projects
# onto the engine's flat-tile silhouette: world (0.5, 0) → (W-1, mid_y),
# world (0.25, sqrt(3)/4) ≈ (0.25, 0.433) → (3u, top_y), and so on.  Doing
# the algebra against E and NE: x-scale = W per world unit, y-scale =
# W/√3 per world unit (so the hex's y-extent ±sqrt(3)/4 maps to
# screen-y ± W/4 = ±u).
#
# z-lift uses the same scale as square dimetric (PIXELS_PER_UNIT) so a
# given 3D part has a comparable on-screen height in both projections.
# The engine's terrain `lift = W/8 per height_step` is for ground-corner
# elevation in HEIGHT_STEP units; bespoke 3D scenes use the world-unit
# convention and need an absolute px/world_z scale, which we share with
# square dimetric.
HEX_Z_SCALE = PIXELS_PER_UNIT


def engine_z_per_step(height_step: int = 1, w: int = DEFAULT_W) -> float:
    """World-z value whose hex projection lifts the screen by `height_step`
    engine height steps.  A bespoke render that wants its sloped sprite
    to align with the engine's ground rendering tilts world-z by this
    amount across one height-step's worth of slope; matches
    `hex_height_raster_scale_y` divided by HEX_Z_SCALE.
    """
    return hex_height_raster_scale_y(height_step, w) / HEX_Z_SCALE


def hex_plan_clip(wx: np.ndarray, wy: np.ndarray, radius: float = 0.5,
                  slack: float = 0.5 / 128.0) -> np.ndarray:
    """Boolean mask: which (world_x, world_y) pixels lie inside the
    flat-top hex of the given radius.

    Half-plane constraints from the 6 edges (R = radius, s = √3):
      |y| ≤ s·R/2                     (N / S edges)
      s·|x| + |y| ≤ s·R               (NE / SE / NW / SW edges)

    Used as a per-pixel clip for hex bespoke output so a 3D scene's
    ground footprint can't extend past the tile silhouette.  `slack`
    is half a screen-pixel of tolerance so corner pixels exactly on
    the silhouette aren't punched out by integer rounding.
    """
    s = math.sqrt(3.0)
    abs_x = np.abs(wx)
    abs_y = np.abs(wy)
    return (abs_y <= s * radius / 2.0 + slack) & \
           (s * abs_x + abs_y <= s * radius + 2.0 * slack)


def world_to_screen_hex(p, geom: HexGeom):
    p = np.asarray(p, dtype=np.float64)
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    sx = geom.w / 2.0 + x * geom.w
    # y-compression by 1/√3 makes the regular hex (corners at radius 0.5)
    # land on the engine's flat-tile vertices.  z lifts up the screen.
    sy = geom.mid_y - y * geom.w / np.sqrt(3.0) - z * HEX_Z_SCALE
    # Depth: +y (further north in world) is further from the camera; +z
    # is closer (sits on top).  Match this to the y-ordering screen so
    # painter's-algorithm via z-buffer works for tilted quads.
    depth = -y + z * 0.001  # tiebreak toward higher z
    return np.stack([sx, sy, depth], axis=-1)


# --- Rasterizer --------------------------------------------------------------
def _quad_normal(verts):
    a = verts[1] - verts[0]
    b = verts[3] - verts[0]
    n = np.cross(a, b)
    norm = np.linalg.norm(n)
    return n / norm if norm > 0 else np.array([0.0, 0.0, 1.0])


def _draw_triangle(rgba, zbuf, verts_screen, color, dither_keep=1.0,
                   world_xy=None, plan_clip=None):
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
    if dither_keep < 1.0:
        # Position-deterministic punch-through: keep only pixels whose
        # `hash_noise01(sx, sy) < dither_keep`.  Reused across square
        # and hex output so the ballast grain stays byte-stable.
        ix = np.mgrid[y_min:y_max + 1, x_min:x_max + 1][1]
        iy = np.mgrid[y_min:y_max + 1, x_min:x_max + 1][0]
        keep_mask = hash_noise01(ix.astype(np.uint32),
                                 iy.astype(np.uint32)) < dither_keep
        write = write & keep_mask
    if plan_clip is not None and world_xy is not None:
        # Clip in world plan view, not screen — z-lifted geometry (rails
        # above ties) keeps its overshoot above the silhouette top while
        # pixels whose ground footprint lies outside the tile are dropped.
        wx0, wy0 = world_xy[0]
        wx1, wy1 = world_xy[1]
        wx2, wy2 = world_xy[2]
        wx = w0 * wx0 + w1 * wx1 + w2 * wx2
        wy = w0 * wy0 + w1 * wy1 + w2 * wy2
        write = write & plan_clip(wx, wy)
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
        self.hex_geom = HexGeom()

    def add_quad(self, points, color, layer="back", dither_keep=1.0):
        """Append a quad given 4 world-space points (CCW from outside).

        `layer` tags which sheet entry the quad belongs to ("back" /
        "front" for pak128 bridge slicing). See render(layer_filter).
        `dither_keep` < 1.0 punches `hash_noise01`-driven holes through
        the quad's pixels so the rendered surface blends with whatever
        terrain texture the engine composites underneath (the pak128
        ballast convention — see cell 1.5 of `rail_060_tracks.png`).
        """
        base = len(self.verts)
        self.verts.extend(map(tuple, points))
        self.quads.append(
            (base, base + 1, base + 2, base + 3, color, layer, dither_keep)
        )

    def add_box(self, p0, p1, color, layer="back", dither_keep=1.0):
        """Append the 5 outward-facing quads of a box (skips the bottom).

        p0, p1 are opposite corners; p0 < p1 component-wise. `layer`
        and `dither_keep` propagate to all 5 quads.
        """
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        b = len(self.verts)
        self.verts.extend([
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ])
        self.quads.extend([
            (b + 4, b + 5, b + 6, b + 7, color, layer, dither_keep),  # top
            (b + 0, b + 1, b + 5, b + 4, color, layer, dither_keep),  # south (-y)
            (b + 2, b + 3, b + 7, b + 6, color, layer, dither_keep),  # north (+y)
            (b + 1, b + 2, b + 6, b + 5, color, layer, dither_keep),  # east  (+x)
            (b + 0, b + 4, b + 7, b + 3, color, layer, dither_keep),  # west  (-x)
        ])

    def render(self, out_path=None, img_size=IMG_SIZE, layer_filter=None,
               projection="square"):
        """Render the scene to an RGBA buffer; if `out_path` is given,
        also save it as a PNG.  Returns the (h, w, 4) uint8 array so
        callers that want to compose multiple renders into one atlas
        don't need a temp-file round-trip.

        `layer_filter`: if not None, only quads whose layer matches are
        drawn — used to emit one PNG per pak128 sheet entry (Back vs.
        Front). The depth buffer still considers only included quads,
        so occlusion within the slice is correct.

        `projection`: "square" (pak128 dimetric) or "hex" (flat-top hex
        camera, anchored to engine `HexGeom`).  Same scene, two views;
        keeps the modeling-unit / output-slicing split that
        `infrastructure/.../CLAUDE.md` calls for.
        """
        verts = np.asarray(self.verts, dtype=np.float64)
        if projection == "hex":
            out_w, out_h = self.hex_geom.w, self.hex_geom.h
        else:
            out_w = out_h = img_size
        rgba = np.zeros((out_h, out_w, 4), dtype=np.uint8)
        zbuf = np.full((out_h, out_w), -np.inf, dtype=np.float32)

        plan_clip = hex_plan_clip if projection == "hex" else None
        for v0, v1, v2, v3, color, layer, dither_keep in self.quads:
            if layer_filter is not None and layer != layer_filter:
                continue
            wq = verts[[v0, v1, v2, v3]]
            n = _quad_normal(wq)
            light = max(0.0, float(np.dot(-self.sun_dir, n)))
            shade = self.ambient + (1.0 - self.ambient) * light
            c = (np.array(color) * shade).clip(0, 255).astype(np.uint8)
            if projection == "hex":
                sq = world_to_screen_hex(wq, self.hex_geom)
            else:
                sq = world_to_screen(wq, screen_center_y=self.screen_center_y)
            world_xy = wq[:, :2]
            for i0, i1, i2 in [(0, 1, 2), (0, 2, 3)]:
                _draw_triangle(rgba, zbuf, sq[[i0, i1, i2]], c,
                               dither_keep=dither_keep,
                               world_xy=world_xy[[i0, i1, i2]],
                               plan_clip=plan_clip)

        if out_path is not None:
            Image.fromarray(rgba, mode="RGBA").save(out_path)
        return rgba
