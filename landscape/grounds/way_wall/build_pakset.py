#!/usr/bin/env python3
"""Bake the hex pakset's way-wall (intra-tile nasyp / way-cut) deliverable.

A way running through a tile on one of the three hex axes occupies a
chord strip of half-width `hex_synth.WAY_HALF_WIDTH` from one touched
edge midpoint to the opposite midpoint, at chord height `h_way`.
Outside the strip is natural ground at the slope's corner heights.
Where they differ the engine renders a vertical wall along the strip's
long edge — a *cut* face if natural ground rises above the way
(`h_off > h_way`), a *nasyp* face if it sinks below.

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

Geometry per cell: one trapezoid quad per off-axis side, anchored at
the chord strip's long edge.  Top edge follows the chord plane
(ramped on ramp axes), bottom edge flat at the off-axis corner's
natural height.  The trapezoid is an approximation — the true natural
ground height along the long edge varies according to the slope's
piecewise-linear surface; the corner-height constant suffices for v1.

The engine's `grund_t::display_way_walls` calls `get_way_wall_back_image`
in `display_boden` before the way draw; `display_way_walls_front` calls
`get_way_wall_front_image` from `display_obj_fg` after vehicles render.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.threed import hex_synth
from tools.threed.render import (
    HexCamera,
    Model,
    engine_z_per_step,
    render,
)


# Flat earth / ballast tone for the cliff face.  Distinct from
# back_wall's drab brown so a way cut into a cliff reads as a separate
# material from the cliff itself.  Per-axis / cut-vs-nasyp shading is
# a phase-3 follow-up; v1 keeps a single colour to focus the diff on
# shape correctness.
NASYP_RGB = (110, 102, 90)


def _side_layer(axis: int, side_sign: int) -> str:
    """Which atlas layer carries the off-axis side cliff at `side_sign`.

    Quad plan-view centre is at `side_sign * WAY_HALF_WIDTH * perp` (the
    touched-edge midpoints sum to zero by axis symmetry), so we evaluate
    `front_back_split` at that single point.  `"front"` means the cliff
    is on the camera-near half — drawn after vehicles so the train
    occludes correctly.
    """
    perp = hex_synth.axis_perp_vector(axis)
    cx = side_sign * hex_synth.WAY_HALF_WIDTH * perp[0]
    cy = side_sign * hex_synth.WAY_HALF_WIDTH * perp[1]
    return "front" if bool(hex_synth.front_back_split(cx, cy, axis)) else "back"


def _add_side_quad(model: Model, mp1, mp2, perp, side_sign: int,
                   h_top1: int, h_top2: int, h_bot: int,
                   z_per_step: float, color, layer: str) -> None:
    """Append one off-axis-side cliff quad (CCW from outside)."""
    if h_top1 == h_bot and h_top2 == h_bot:
        return

    p_start = (mp1[0] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[0],
               mp1[1] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[1])
    p_end   = (mp2[0] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[0],
               mp2[1] + side_sign * hex_synth.WAY_HALF_WIDTH * perp[1])

    z_top1 = h_top1 * z_per_step
    z_top2 = h_top2 * z_per_step
    z_bot  = h_bot  * z_per_step

    pts = [
        (p_start[0], p_start[1], z_top1),
        (p_end[0],   p_end[1],   z_top2),
        (p_end[0],   p_end[1],   z_bot),
        (p_start[0], p_start[1], z_bot),
    ]
    if side_sign < 0:
        pts = list(reversed(pts))
    model.add_quad(pts, color, layer=layer)


def _add_top_quad(model: Model, mp1, mp2, perp,
                  h_top1: int, h_top2: int,
                  z_per_step: float, color, layer: str = "back") -> None:
    """Chord-strip top face at `h_way` (CCW from +z).  Always in `"back"`
    so it sits under the way sprite and any vehicles.
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
    model.add_quad([a, b, c, d], color, layer=layer)


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
                  NASYP_RGB, layer="back")
    _add_side_quad(model, mp1, mp2, perp, +1,
                   h_we1, h_we2, ch[off_pos], z_per_step, NASYP_RGB,
                   layer=_side_layer(axis, +1))
    _add_side_quad(model, mp1, mp2, perp, -1,
                   h_we1, h_we2, ch[off_neg], z_per_step, NASYP_RGB,
                   layer=_side_layer(axis, -1))
    return model


def _render_layer(axis: int, slope: int, layer: str,
                  geom: hex_synth.HexGeom | None) -> np.ndarray:
    if geom is None:
        geom = hex_synth.HexGeom()
    if hex_synth.axis_h_way(slope, axis) is None:
        return np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    model = _build_model(axis, slope, geom)
    return render(model, HexCamera(geom=geom), layer_filter=layer)


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

Carries only the off-axis side cliff on the camera-near half of the
axis (per `hex_synth.front_back_split`).  Drawn AFTER vehicles by
`grund_t::display_way_walls_front` so a cut wall on the camera-side
correctly occludes the train.  All other geometry (chord-strip top,
back-side cliff) lives in the companion BACK atlas.

Same `(axis, slope)` keying as the back atlas; populated independently
because some (axis, slope) pairs have no camera-near cliff to draw
(e.g. flat-chord on a saddle slope where the camera-near corner is at
chord height).  Engine treats absent slots as IMG_EMPTY and skips the
post-vehicle draw.

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
