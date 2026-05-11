#!/usr/bin/env python3
"""Bake the hex pakset's way-wall (intra-tile nasyp / way-cut) deliverable.

A way running through a tile on one of the three hex axes occupies a
chord strip of half-width `hex_synth.WAY_HALF_WIDTH` from one touched
edge midpoint to the opposite midpoint, at chord height `h_way`.
Outside the strip is natural ground at the slope's corner heights.
Where they differ the engine renders a vertical wall along the strip's
long edge — a *cut* face if natural ground rises above the way
(`h_off > h_way`), a *nasyp* face if it sinks below.

Cells ship as **lightmaps**: per-face Lambert grey under
`hex_synth.LIGHT` in RGB, coverage mask in alpha.  The engine composes
the final per-climate tile at startup via
`create_textured_tile(way_wall_lightmap, boden_texture[climate])` so
the wall surface inherits the ground tile's earth/grass texture and
the lightmap supplies the slope shading — the same path
`texture_lightmap` uses for ground tiles, applied to wall geometry.
See `tools/threed/lightmap.py` for the encoding convention.

The atlas is keyed by `(axis, slope)` and split into two deliverables
along `hex_synth.front_back_split`:

  * `way_wall_back.{png,dat}` — chord-strip top + the off-axis side
    cliff that's on the camera-far half of the axis.  Drawn before
    the way sprite and before vehicles.
  * `way_wall_front.{png,dat}` — only the cliff on the camera-near
    half of the axis.  Drawn AFTER vehicles so a cut wall on the
    camera-side correctly occludes the train.

`axis ∈ {0:NS, 1:NE_SW, 2:NW_SE}` (matches
`display/hex_proj.h::hex_way_axis_t`).  `slope` is the raw normalised
`slope_t` value (base-4 per corner, `min(corner_height) == 0` — same
encoding `texture_lightmap` uses).  Only slopes admitting a way on
that axis are emitted; others read as `IMG_EMPTY`.

Geometry per cell: one triangle per off-axis side, anchored at the
chord strip's long edge.  The base follows the chord plane (ramped
on ramp axes) from `(p_start, h_we1)` to `(p_end, h_we2)`; the apex
sits at the long edge's midpoint at the off-axis corner's natural
height `h_off`.  At the touched-edge ends the wall has zero height —
the level-edge constraint (`axis_h_way`) guarantees natural ground
is at `h_we` there, so the wall must taper to nothing.  Apex height
= corner height is exact only at the corner itself; the engine's
surface triangulation between the long edge and the corner is not
mirrored here, so the apex slightly over- or under-estimates the
true ground height at the long edge's midpoint.

The engine's `grund_t::display_way_walls` calls `get_way_wall_back_image`
in `display_boden` before the way draw; `display_way_walls_front` calls
`get_way_wall_front_image` from `display_obj_fg` after vehicles render.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from tools.threed import hex_synth
from tools.threed.lightmap import lambert_grey_rgb
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
    """Lambert grey for one face under hex_synth's `LIGHT`, encoded for
    `create_textured_tile`.  `face_pts_world` is a list of ≥3 world-
    space `(x, y, z)` points; only the first non-degenerate triangle's
    normal is used (faces here are coplanar by construction).

    World coords are mapped into the same pixel-space scaling
    `world_to_screen_hex` uses (and `region_brightness` mirrors for
    `texture_lightmap`), so a flat-up face here produces the same
    grey as a flat ground tile.
    """
    scale_x = geom.w / (2.0 * HEX_TILE_RADIUS)
    scale_y = geom.w / (2.0 * HEX_TILE_RADIUS * math.sqrt(3.0))
    p = [(x * scale_x, y * scale_y, z * HEX_Z_SCALE)
         for x, y, z in face_pts_world]
    p0 = p[0]
    for k in range(2, len(p)):
        p1, p2 = p[k - 1], p[k]
        ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        bx, by, bz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx
        if nx == 0.0 and ny == 0.0 and nz == 0.0:
            continue
        if nz < 0.0:
            nx, ny, nz = -nx, -ny, -nz
        return lambert_grey_rgb(nx, ny, nz)
    return lambert_grey_rgb(0.0, 0.0, 1.0)


def _validate_axis_geometry() -> None:
    """Module-load asserts on the hex-axis geometry the triangle wall
    depends on.  Cheap (3 axes × a handful of dot products) and runs
    once at import; cheap insurance against `hex_synth` changing one
    of these invariants out from under us.

    Invariants:

      * The midpoint of `(mp1, mp2)` is the hex centre `(0, 0)` for
        every axis.  Equivalent: `mp2 == -mp1`, since the touched
        edges are antipodal across the centre.  This is what makes
        the long-edge midpoint reduce to `side_sign * WAY_HALF_WIDTH
        * perp`.
      * `axis_perp_vector(axis)` is parallel (up to sign) to the
        touched-edge direction.  Equivalent: the chord strip's long
        edge ends sit on the touched-edge lines of the hex.  Without
        this, `p_start` and `p_end` wouldn't sit on the touched edges
        and the wall's "zero height at the ends" claim breaks.
      * Both off-axis corners project to `t == 0.5` on the axis —
        i.e. the apex `(p_mid, h_off)` is exactly the long edge's
        closest point to the off-axis corner.
    """
    for axis in (hex_synth.NS, hex_synth.NE_SW, hex_synth.NW_SE):
        mp1, mp2 = hex_synth.axis_edge_midpoints(axis)
        assert abs(mp1[0] + mp2[0]) < 1e-9 and abs(mp1[1] + mp2[1]) < 1e-9, \
            f"axis {axis}: mp1+mp2 != 0 (mp1={mp1}, mp2={mp2})"

        perp = hex_synth.axis_perp_vector(axis)
        (a0_i, a1_i), _ = hex_synth.AXIS_EDGE_CORNERS[axis]
        ca = hex_synth.HEX_CORNER_XY[a0_i]
        cb = hex_synth.HEX_CORNER_XY[a1_i]
        edge_dx, edge_dy = cb[0] - ca[0], cb[1] - ca[1]
        # perp ∥ edge ⇔ cross == 0
        cross = perp[0] * edge_dy - perp[1] * edge_dx
        assert abs(cross) < 1e-9, \
            f"axis {axis}: perp not parallel to touched edge (cross={cross})"

        d = (mp2[0] - mp1[0], mp2[1] - mp1[1])
        d_norm_sq = d[0] * d[0] + d[1] * d[1]
        off_pos, off_neg = hex_synth.AXIS_OFF_AXIS_CORNERS[axis]
        for off_i in (off_pos, off_neg):
            c = hex_synth.HEX_CORNER_XY[off_i]
            t = ((c[0] - mp1[0]) * d[0] + (c[1] - mp1[1]) * d[1]) / d_norm_sq
            assert abs(t - 0.5) < 1e-9, \
                f"axis {axis} off-axis corner {off_i}: t={t}, expected 0.5"


_validate_axis_geometry()


def _side_layer(axis: int, side_sign: int) -> str:
    """Which atlas layer carries the off-axis side cliff at `side_sign`.

    The triangle is edge-on in plan view (all three vertices lie on
    the chord strip's long edge), so its plan-view centroid is the
    long edge's midpoint `side_sign * WAY_HALF_WIDTH * perp` — the
    touched-edge midpoints sum to zero by axis symmetry.  We evaluate
    `front_back_split` at that single point.  `"front"` means the
    cliff is on the camera-near half — drawn after vehicles so the
    train occludes correctly.
    """
    perp = hex_synth.axis_perp_vector(axis)
    cx = side_sign * hex_synth.WAY_HALF_WIDTH * perp[0]
    cy = side_sign * hex_synth.WAY_HALF_WIDTH * perp[1]
    return "front" if bool(hex_synth.front_back_split(cx, cy, axis)) else "back"


def _add_side_triangle(model: Model, mp1, mp2, perp, side_sign: int,
                       h_top1: int, h_top2: int, h_bot: int,
                       z_per_step: float, geom: hex_synth.HexGeom,
                       layer: str) -> None:
    """Append one off-axis-side cliff triangle as a per-face lightmap.

    Base along the chord top from `(p_start, h_we1=h_top1)` to
    `(p_end, h_we2=h_top2)`; apex at `(p_mid, h_off=h_bot)`, where
    `p_mid` is the long edge's midpoint.  Winding flips with
    `side_sign` so the outward normal lands on the same side as the
    original rectangular cliff: toward the way in both cut and nasyp.
    Submitted via `Model.add_quad` with the apex duplicated as the
    fourth vertex; the renderer's second sub-triangle is zero-area
    and skipped by `_draw_triangle`'s denom check.

    The face's Lambert grey comes from `_face_lightmap_rgb` so the
    rasterised RGB lands on `create_textured_tile`'s multiplier
    convention — the renderer is run with `ambient=1.0` to keep this
    grey verbatim.
    """
    if h_top1 == h_bot and h_top2 == h_bot:
        return

    p_start = (mp1[0] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[0],
               mp1[1] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[1])
    p_end   = (mp2[0] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[0],
               mp2[1] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[1])
    p_mid   = ((p_start[0] + p_end[0]) / 2.0,
               (p_start[1] + p_end[1]) / 2.0)

    v_start = (p_start[0], p_start[1], h_top1 * z_per_step)
    v_end   = (p_end[0],   p_end[1],   h_top2 * z_per_step)
    v_apex  = (p_mid[0],   p_mid[1],   h_bot  * z_per_step)

    if side_sign > 0:
        pts = [v_start, v_end, v_apex, v_apex]
    else:
        pts = [v_end, v_start, v_apex, v_apex]
    color = _face_lightmap_rgb(pts[:3], geom)
    model.add_quad(pts, color, layer=layer)


def _add_top_quad(model: Model, mp1, mp2, perp,
                  h_top1: int, h_top2: int,
                  z_per_step: float, geom: hex_synth.HexGeom,
                  layer: str = "back") -> None:
    """Chord-strip top face at `h_way` (CCW from +z).  Always in `"back"`
    so it sits under the way sprite and any vehicles.  Carries the
    same per-face Lambert grey as the cliff faces — flat chord strips
    on level axes land on the 1.0× identity multiplier.
    """
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
    model.add_quad(pts, color, layer=layer)


def _build_model(axis: int, slope: int, geom: hex_synth.HexGeom) -> Model:
    """Build the shared Model for one (axis, slope), tagged per-quad
    with the right `layer` so a `layer_filter` render emits the back
    or front atlas cell.
    """
    h_we1, h_we2 = hex_synth.axis_h_way(slope, axis)
    ch = hex_synth.decode_corner_heights(slope)
    off_pos, off_neg = hex_synth.AXIS_OFF_AXIS_CORNERS[axis]
    mp1, mp2 = hex_synth.axis_edge_midpoints(axis)
    perp = hex_synth.axis_perp_vector(axis)
    z_per_step = engine_z_per_step(1, geom.w)

    model = Model()
    _add_top_quad(model, mp1, mp2, perp, h_we1, h_we2, z_per_step,
                  geom, layer="back")
    _add_side_triangle(model, mp1, mp2, perp, +1,
                       h_we1, h_we2, ch[off_pos], z_per_step, geom,
                       layer=_side_layer(axis, +1))
    _add_side_triangle(model, mp1, mp2, perp, -1,
                       h_we1, h_we2, ch[off_neg], z_per_step, geom,
                       layer=_side_layer(axis, -1))
    return model


def _render_layer(axis: int, slope: int, layer: str,
                  geom: hex_synth.HexGeom | None) -> np.ndarray:
    if geom is None:
        geom = hex_synth.HexGeom()
    if hex_synth.axis_h_way(slope, axis) is None:
        return np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    model = _build_model(axis, slope, geom)
    # `ambient=1.0` so the renderer rasterises the pre-baked per-face
    # Lambert grey verbatim — its own SUN_DIR-based shading would
    # double up and drift off the lightmap multiplier convention.
    return render(model, HexCamera(geom=geom, ambient=1.0),
                  layer_filter=layer)


def render_back_cell(axis: int, slope: int,
                     geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    return _render_layer(axis, slope, "back", geom)


def render_front_cell(axis: int, slope: int,
                      geom: hex_synth.HexGeom | None = None) -> np.ndarray:
    return _render_layer(axis, slope, "front", geom)


def _cell_has_pixels(cell: np.ndarray) -> bool:
    return bool((cell[..., 3] > 0).any())


AXIS_NAME = {hex_synth.NS: "NS",
             hex_synth.NE_SW: "NE-SW",
             hex_synth.NW_SE: "NW-SE"}


def _iter_entries_for_layer(layer: str):
    """Yield only (axis, slope) pairs whose cell has visible pixels in
    `layer` — avoids baking transparent atlas slots on the front side
    of slopes whose camera-near cliff is at chord height.
    """
    def gen(geom):
        for axis in (hex_synth.NS, hex_synth.NE_SW, hex_synth.NW_SE):
            for slope in hex_synth.iter_valid_slopes():
                if hex_synth.axis_h_way(slope, axis) is None:
                    continue
                cell = _render_layer(axis, slope, layer, geom)
                if not _cell_has_pixels(cell):
                    continue
                ch = hex_synth.decode_corner_heights(slope)
                comment = (f"axis={AXIS_NAME[axis]} slope={slope} "
                           f"corners=(E={ch[hex_synth.E]} "
                           f"SE={ch[hex_synth.SE]} SW={ch[hex_synth.SW]} "
                           f"W={ch[hex_synth.W_C]} NW={ch[hex_synth.NW]} "
                           f"NE={ch[hex_synth.NE]})")
                yield axis, slope, (axis, slope), comment
    return gen


HEADER_DOC_BACK = """\
Intra-tile nasyp / way-cut walls — BACK atlas, keyed by `(axis, slope)`.

Cells are **lightmaps**, not pigmented sprites: RGB carries per-face
Lambert grey under `hex_synth.LIGHT`, alpha is the coverage mask.
The engine composes a final tile at startup via
`create_textured_tile(way_wall_back, boden_texture[climate])` so the
wall surface shows the same earth/grass texture as the ground tile,
Lambert-shaded by face normal — see `tools/threed/lightmap.py` for
the multiplier convention.

Carries the chord-strip top quad plus the off-axis side cliff that's
on the camera-far half of the axis (per
`hex_synth.front_back_split`).  Drawn from `grund_t::display_boden`
before the way sprite and before vehicles — vehicles render on top.

  * `axis` in 0..2 — 0=NS, 1=NE-SW, 2=NW-SE.
  * `slope` is the raw normalised `slope_t` value (base-4 per
    corner); engine callers normalise via
    `slope_t::lower_min_corner` before lookup.

Companion FRONT atlas (`way_wall_front.{{png,dat}}`) carries the
camera-near cliff drawn after vehicles by
`grund_t::display_way_walls_front`.

Sparsity: {n_entries} populated entries.
"""


HEADER_DOC_FRONT = """\
Intra-tile nasyp / way-cut walls — FRONT atlas, keyed by `(axis, slope)`.

Cells are lightmaps under the same convention as the BACK atlas
(`way_wall_back.{{png,dat}}`); the engine composes both against the
climate texture at startup.

Carries only the off-axis side cliff on the camera-near half of the
axis (per `hex_synth.front_back_split`).  Drawn AFTER vehicles by
`grund_t::display_way_walls_front` so a cut wall on the camera-side
correctly occludes the train.  All other geometry (chord-strip top,
back-side cliff) lives in the companion BACK atlas.

Same `(axis, slope)` keying as the back atlas; populated independently
because some (axis, slope) pairs have no camera-near cliff to draw —
either the camera-near corner sits at chord height, or on a double-
step ramp the off-axis corner sits at the chord-midpoint height so
the wall triangle collapses to zero area.  Engine treats absent
slots as IMG_EMPTY and skips the post-vehicle draw.

Sparsity: {n_entries} populated entries.
"""


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="way_wall_back",
        obj_name="WayWallBack",
        header_doc=HEADER_DOC_BACK,
        render_cell=lambda axis, slope, geom: render_back_cell(axis, slope, geom),
        iter_entries=_iter_entries_for_layer("back"),
        default_cols=12,
    )
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="way_wall_front",
        obj_name="WayWallFront",
        header_doc=HEADER_DOC_FRONT,
        render_cell=lambda axis, slope, geom: render_front_cell(axis, slope, geom),
        iter_entries=_iter_entries_for_layer("front"),
        default_cols=12,
    )
