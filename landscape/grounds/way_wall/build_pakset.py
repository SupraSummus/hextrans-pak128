#!/usr/bin/env python3
"""Bake the hex pakset's way-wall (intra-tile nasyp / way-cut) deliverable.

A way running through a tile on one of the three hex axes occupies a
chord strip of half-width `hex_synth.WAY_HALF_WIDTH` from one touched
edge midpoint to the opposite midpoint, at chord height `h_way`.
Outside the strip is natural ground at the slope's corner heights.
Where they differ the engine renders an angled face spanning from the
strip's long edge at chord height to the off-axis corner at natural
ground height — a *cut* slope if natural ground rises above the way
(`h_off > h_way`), a *nasyp* (embankment) slope if it sinks below.

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

Geometry per cell: one triangle per off-axis side.  The base
follows the chord plane (ramped on ramp axes) along the chord
strip's long edge from `(p_start, h_we1)` to `(p_end, h_we2)`; the
apex sits at the off-axis hex corner `(corner_xy, h_off)`.  At the
touched-edge ends the slope has zero height — the level-edge
constraint (`axis_h_way`) guarantees natural ground is at `h_we`
there, so the face must taper to nothing.  Because the apex lies at
the corner itself, apex height = corner height is exact: the
triangle's three vertices all sit on real ground points, so the
embankment face matches the natural-ground surface at its boundary.
The face is no longer vertical — its normal tilts toward +z — so
its Lambert grey reads as a sloped terrain surface (real nasyp /
cut angle) rather than a wall.

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
    """Module-load asserts on the hex-axis invariants the side-slope
    triangle depends on.  Cheap insurance against `hex_synth` changing
    one of these out from under us.

    Invariants:

      * `axis_perp_vector(axis)` is parallel (up to sign) to the
        touched-edge direction.  This is what makes `p_start = mp1 +
        side_sign * WAY_HALF_WIDTH * perp` (and `p_end` from `mp2`)
        sit on the touched-edge line of the hex.  Combined with
        `axis_h_way`'s level-edge constraint (both touched-edge
        corners at `h_we`), it pins the slope's base ends to natural
        ground — so the triangle tapers to zero height there.
      * `AXIS_OFF_AXIS_CORNERS[axis] = (off_pos, off_neg)` puts
        `HEX_CORNER_XY[off_pos]` on the +perp side of the axis and
        `[off_neg]` on the -perp side.  This is the signed pairing
        `_build_model` relies on: `side_sign = +1` is fed `corner_pos`
        so the triangle's three vertices land on the same half-plane
        of the axis (consistent winding → consistent outward normal).
    """
    for axis in (hex_synth.NS, hex_synth.NE_SW, hex_synth.NW_SE):
        perp = hex_synth.axis_perp_vector(axis)
        (a0_i, a1_i), _ = hex_synth.AXIS_EDGE_CORNERS[axis]
        ca = hex_synth.HEX_CORNER_XY[a0_i]
        cb = hex_synth.HEX_CORNER_XY[a1_i]
        edge_dx, edge_dy = cb[0] - ca[0], cb[1] - ca[1]
        # perp ∥ edge ⇔ cross == 0
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


def _side_layer(axis: int, corner_xy) -> str:
    """Which atlas layer carries the off-axis side slope whose apex is
    at `corner_xy`.

    All three triangle vertices sit on the same half-plane of the axis
    (the perp-side check in `_validate_axis_geometry`), so any vertex
    classifies the face identically.  We pick the corner because it's
    the apex and the cleanest reference point.  `"front"` means the
    slope is on the camera-near half — drawn after vehicles so the
    train occludes correctly.
    """
    return ("front" if bool(hex_synth.front_back_split(corner_xy[0],
                                                       corner_xy[1], axis))
            else "back")


def _add_side_triangle(model: Model, mp1, mp2, perp, side_sign: int,
                       corner_xy,
                       h_top1: int, h_top2: int, h_bot: int,
                       z_per_step: float, geom: hex_synth.HexGeom,
                       layer: str) -> None:
    """Append one off-axis-side slope triangle as a per-face lightmap.

    Base along the chord strip's long edge from `(p_start, h_we1=h_top1)`
    to `(p_end, h_we2=h_top2)`; apex at the off-axis hex corner
    `(corner_xy, h_off=h_bot)`.  The triangle therefore spans from the
    strip's edge outward to the natural-ground corner, slanting in z
    by `h_top - h_bot` — a real nasyp / cut angle rather than a
    vertical wall.

    Winding flips with `side_sign` so the outward normal lands on
    the same side as the original rectangular cliff: away from the
    way in both cut and nasyp.  Submitted via `Model.add_quad` with
    the apex duplicated as the fourth vertex; the renderer's second
    sub-triangle is zero-area and skipped by `_draw_triangle`'s
    denom check.

    The face's Lambert grey comes from `_face_lightmap_rgb` so the
    rasterised RGB lands on `create_textured_tile`'s multiplier
    convention — the renderer is run with `ambient=1.0` to keep this
    grey verbatim.  With the apex at the corner the face normal is no
    longer horizontal, so this grey reads as terrain-slope shading
    (front-side sprite blends with the surrounding ground), not a
    wall.
    """
    if h_top1 == h_bot and h_top2 == h_bot:
        return

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
    corner_pos = hex_synth.HEX_CORNER_XY[off_pos]
    corner_neg = hex_synth.HEX_CORNER_XY[off_neg]
    mp1, mp2 = hex_synth.axis_edge_midpoints(axis)
    perp = hex_synth.axis_perp_vector(axis)
    z_per_step = engine_z_per_step(1, geom.w)

    model = Model()
    _add_top_quad(model, mp1, mp2, perp, h_we1, h_we2, z_per_step,
                  geom, layer="back")
    _add_side_triangle(model, mp1, mp2, perp, +1, corner_pos,
                       h_we1, h_we2, ch[off_pos], z_per_step, geom,
                       layer=_side_layer(axis, corner_pos))
    _add_side_triangle(model, mp1, mp2, perp, -1, corner_neg,
                       h_we1, h_we2, ch[off_neg], z_per_step, geom,
                       layer=_side_layer(axis, corner_neg))
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
