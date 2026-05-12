#!/usr/bin/env python3
"""Bake the hex pakset's way-ground deliverable: per-`(axis, slope)`
ground lightmap for tiles carrying a way along that axis.

A way running through a tile on one of the three hex axes occupies
the central chord strip of half-width `hex_synth.WAY_HALF_WIDTH =
0.5`.  That makes the strip exactly one edge wide, so any way fits
regardless of its painted width, and the strip's long edges land on
the touched-edge corners.  The strip is at chord height `h_way`
(`axis_h_way`).  The two off-axis corner triangles of the hex sit
at the slope's natural corner heights and meet the strip along its
long edge — a *cut* triangle when the corner rises above the chord,
a *nasyp* (embankment) triangle when it sinks below.  Together the
chord strip + two corner triangles cover the entire hex outline, so
this atlas is a full-tile ground lightmap that replaces the natural-
ground `texture_lightmap` lookup for tiles with a way on top.

Cells ship as **lightmaps**: per-face Lambert grey under
`hex_synth.LIGHT` in RGB, coverage mask in alpha.  The engine
composes the final per-climate tile at startup via
`create_textured_tile(way_ground_lightmap, boden_texture[climate])`
— the same path `texture_lightmap` uses for ground tiles.  See
`tools/threed/lightmap.py` for the encoding convention.

Atlas keyed by `(axis, slope)` (matches
`display/hex_proj.h::hex_way_axis_t` for the axis dimension; `slope`
is the raw normalised `slope_t` value, base-4 per corner, same
encoding `texture_lightmap` uses).  Only slopes admitting a way on
that axis are emitted; others read as `IMG_EMPTY` and the engine
falls back to the natural-ground lightmap.

Geometry: the strip top quad + one off-axis corner triangle per
side (apex at the hex corner, base along the strip's long edge).
No front/back split — the strip and triangles all draw together in
a single pre-vehicle pass, replacing the natural-ground tile.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from tools.threed import hex_synth
from tools.threed.lightmap import brightness_to_grey_rgb
from tools.threed.render import (
    HEX_Z_SCALE,
    HexCamera,
    Model,
    engine_z_per_step,
    render,
)
from tools.threed.way import HEX_TILE_RADIUS


def _face_lightmap_rgb(face_pts_world,
                       geom: hex_synth.HexGeom) -> tuple[int, int, int]:
    """Lambert grey for one face given its vertices in world coords
    (`+x = east`, `+y = north`, `+z = up`).  Maps each point into the
    engine's Lambert frame the same way `world_to_screen_hex` does
    (`sy = base_y - y·scale_y - z·HEX_Z_SCALE`), then defers to
    `hex_synth.face_normal_brightness` so the cross-product / flip
    / Lambert convention stays in lockstep with `region_brightness`.
    Flat-up faces produce `(0, 0, 1)` in this frame, so a flat
    way_ground slot is bit-identical to the flat-slope
    `texture_lightmap` slot once climate-composited.
    """
    scale_x = geom.w / (2.0 * HEX_TILE_RADIUS)
    scale_y = geom.w / (2.0 * HEX_TILE_RADIUS * math.sqrt(3.0))
    pts = [(x * scale_x,
            -y * scale_y - z * HEX_Z_SCALE,
            z * HEX_Z_SCALE)
           for x, y, z in face_pts_world]
    return brightness_to_grey_rgb(hex_synth.face_normal_brightness(pts))


def _validate_axis_geometry() -> None:
    """Module-load asserts on the hex-axis invariants the side-triangle
    construction depends on.

    Invariants:

      * `axis_perp_vector(axis)` is parallel (up to sign) to the
        touched-edge direction — so `p_start = mp1 + side_sign *
        WAY_HALF_WIDTH * perp` lands on the touched-edge line.  With
        `WAY_HALF_WIDTH = 0.5` this puts `p_start` exactly on the
        touched-edge corner.
      * `AXIS_OFF_AXIS_CORNERS[axis] = (off_pos, off_neg)` puts
        `HEX_CORNER_XY[off_pos]` on the +perp side of the axis and
        `[off_neg]` on the -perp side — the signed pairing
        `_build_model` uses to feed each side its own apex corner.
    """
    for axis in (hex_synth.NS, hex_synth.NE_SW, hex_synth.NW_SE):
        perp = hex_synth.axis_perp_vector(axis)
        (a0_i, a1_i), _ = hex_synth.AXIS_EDGE_CORNERS[axis]
        ca = hex_synth.HEX_CORNER_XY[a0_i]
        cb = hex_synth.HEX_CORNER_XY[a1_i]
        edge_dx, edge_dy = cb[0] - ca[0], cb[1] - ca[1]
        cross = perp[0] * edge_dy - perp[1] * edge_dx
        assert abs(cross) < 1e-9, \
            f"axis {axis}: perp not parallel to touched edge (cross={cross})"

        off_pos, off_neg = hex_synth.AXIS_OFF_AXIS_CORNERS[axis]
        for off_i, want_sign in ((off_pos, +1), (off_neg, -1)):
            c = hex_synth.HEX_CORNER_XY[off_i]
            dot = c[0] * perp[0] + c[1] * perp[1]
            assert dot * want_sign > 1e-9, (
                f"axis {axis} off-axis corner {off_i}: "
                f"corner·perp={dot}, expected sign {want_sign}")


_validate_axis_geometry()


def _add_corner_triangle(model: Model, mp1, mp2, perp, side_sign: int,
                         corner_xy,
                         h_top1: int, h_top2: int, h_bot: int,
                         z_per_step: float, geom: hex_synth.HexGeom) -> None:
    """Append one off-axis corner triangle.

    Base along the chord strip's long edge from `(p_start, h_top1)`
    to `(p_end, h_top2)`; apex at the off-axis hex corner
    `(corner_xy, h_bot)`.  With `WAY_HALF_WIDTH = 0.5` `p_start` and
    `p_end` sit on the touched-edge corners, so the triangle is the
    natural off-axis corner triangle of the hex.  When `h_bot ==
    h_top1 == h_top2` the triangle is coplanar with the chord strip
    (no visible cut/nasyp).

    Winding flips with `side_sign` so the outward normal tilts +z
    (the renderer flips any face whose cross product points -z, so
    consistent winding here just means consistent Lambert input).
    Submitted via `Model.add_quad` with the apex duplicated as the
    fourth vertex; the renderer's second sub-triangle is zero-area
    and skipped by `_draw_triangle`'s denom check.
    """
    p_start = (mp1[0] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[0],
               mp1[1] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[1])
    p_end   = (mp2[0] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[0],
               mp2[1] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[1])

    v_start = (p_start[0],  p_start[1],  h_top1 * z_per_step)
    v_end   = (p_end[0],    p_end[1],    h_top2 * z_per_step)
    v_apex  = (corner_xy[0], corner_xy[1], h_bot * z_per_step)

    if side_sign > 0:
        pts = [v_start, v_end, v_apex, v_apex]
    else:
        pts = [v_end, v_start, v_apex, v_apex]
    color = _face_lightmap_rgb(pts[:3], geom)
    model.add_quad(pts, color)


def _add_top_quad(model: Model, mp1, mp2, perp,
                  h_top1: int, h_top2: int,
                  z_per_step: float, geom: hex_synth.HexGeom) -> None:
    """Chord-strip top quad at `h_way` (CCW from +z).  Flat on level
    axes (identity 1.0× grey), tilted on ramp axes — Lambert reads
    as a ramp surface."""
    a = (mp1[0] + hex_synth.WAY_HALF_WIDTH * perp[0],
         mp1[1] + hex_synth.WAY_HALF_WIDTH * perp[1],
         h_top1 * z_per_step)
    b = (mp1[0] - hex_synth.WAY_HALF_WIDTH * perp[0],
         mp1[1] - hex_synth.WAY_HALF_WIDTH * perp[1],
         h_top1 * z_per_step)
    c = (mp2[0] - hex_synth.WAY_HALF_WIDTH * perp[0],
         mp2[1] - hex_synth.WAY_HALF_WIDTH * perp[1],
         h_top2 * z_per_step)
    d = (mp2[0] + hex_synth.WAY_HALF_WIDTH * perp[0],
         mp2[1] + hex_synth.WAY_HALF_WIDTH * perp[1],
         h_top2 * z_per_step)
    pts = [a, b, c, d]
    color = _face_lightmap_rgb(pts, geom)
    model.add_quad(pts, color)


def _build_model(axis: int, slope: int, geom: hex_synth.HexGeom) -> Model:
    h_we1, h_we2 = hex_synth.axis_h_way(slope, axis)
    ch = hex_synth.decode_corner_heights(slope)
    off_pos, off_neg = hex_synth.AXIS_OFF_AXIS_CORNERS[axis]
    corner_pos = hex_synth.HEX_CORNER_XY[off_pos]
    corner_neg = hex_synth.HEX_CORNER_XY[off_neg]
    mp1, mp2 = hex_synth.axis_edge_midpoints(axis)
    perp = hex_synth.axis_perp_vector(axis)
    z_per_step = engine_z_per_step(1, geom.w)

    model = Model()
    _add_top_quad(model, mp1, mp2, perp, h_we1, h_we2, z_per_step, geom)
    _add_corner_triangle(model, mp1, mp2, perp, +1, corner_pos,
                         h_we1, h_we2, ch[off_pos], z_per_step, geom)
    _add_corner_triangle(model, mp1, mp2, perp, -1, corner_neg,
                         h_we1, h_we2, ch[off_neg], z_per_step, geom)
    return model


def render_cell(axis: int, slope: int,
                geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    if geom is None:
        geom = hex_synth.HexGeom()
    if hex_synth.axis_h_way(slope, axis) is None:
        return np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    model = _build_model(axis, slope, geom)
    # `ambient=1.0` so the renderer rasterises the pre-baked per-face
    # Lambert grey verbatim — its own SUN_DIR-based shading would
    # double up and drift off the lightmap multiplier convention.
    return render(model, HexCamera(geom=geom, ambient=1.0))


AXIS_NAME = {hex_synth.NS: "NS",
             hex_synth.NE_SW: "NE-SW",
             hex_synth.NW_SE: "NW-SE"}


def _iter_entries():
    def gen(geom):
        for axis in (hex_synth.NS, hex_synth.NE_SW, hex_synth.NW_SE):
            for slope in hex_synth.iter_valid_slopes():
                if hex_synth.axis_h_way(slope, axis) is None:
                    continue
                ch = hex_synth.decode_corner_heights(slope)
                comment = (f"axis={AXIS_NAME[axis]} slope={slope} "
                           f"corners=(E={ch[hex_synth.E]} "
                           f"SE={ch[hex_synth.SE]} SW={ch[hex_synth.SW]} "
                           f"W={ch[hex_synth.W_C]} NW={ch[hex_synth.NW]} "
                           f"NE={ch[hex_synth.NE]})")
                yield axis, slope, (axis, slope), comment
    return gen


HEADER_DOC = """\
Per-`(axis, slope)` ground lightmap for tiles carrying a way along
that axis.  Replaces the natural-ground `texture_lightmap` lookup
for those tiles: the central chord strip is rendered at the way's
chord height, the two off-axis corner triangles at the slope's
natural corner heights so a *cut* or *nasyp* reads as the corner
triangle slanting up or down to meet the chord plane.

Cells are **lightmaps**, not pigmented sprites: RGB carries per-face
Lambert grey under `hex_synth.LIGHT`, alpha is the coverage mask.
The engine composes a final tile at startup via
`create_textured_tile(way_ground, boden_texture[climate])` so the
tile shows the same earth/grass texture as a normal ground tile,
Lambert-shaded by face normal — see `tools/threed/lightmap.py` for
the multiplier convention.

  * `axis` in 0..2 — 0=NS, 1=NE-SW, 2=NW-SE.
  * `slope` is the raw normalised `slope_t` value (base-4 per
    corner); engine callers normalise via
    `slope_t::lower_min_corner` before lookup.

Sparsity: {n_entries} populated entries.
"""


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="way_ground",
        obj_name="WayGround",
        header_doc=HEADER_DOC,
        render_cell=lambda axis, slope, geom: render_cell(axis, slope, geom),
        iter_entries=_iter_entries(),
        default_cols=12,
    )
