"""Hex way topology builders parameterised on a `CrossSection`.

Splits the asset-agnostic topology (where on the hex tile a stub /
curve / junction / axis-slope segment goes) from the asset-specific
cross-section (rail's ballast bands + ties + rails; road's pavement
slab; tram's pavement + rails; …).  Each builder calls back into the
asset's `CrossSection` for the actual geometry emission, so adding a
new way family is "subclass `CrossSection`, override two methods".

The builders here used to live as private `_add_*_segment` /
`_build_arc_curve` / `build_curve` / `build_stub` / `build_junction` /
`build_axis_slope` functions in `rail_060_tracks/scene.py`, then got
verbatim-copied into `road_040/scene.py` when the second consumer
arrived.  The duplication signal said it was time to graduate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .way import (
    HEX_CORNERS, HEX_EDGES, HEX_OPPOSITE_EDGE,
    edge_midpoint, edge_unit_dir, shared_corner,
)


# ---- Shared chord/caps slab emitter ---------------------------------------

def make_slab_emitter(model, path: "StraightPath"):
    """Return `(add_slab, chord_len)` for one straight segment.

    `add_slab(s0, s1, perp0, perp1, z0, z1, color, dither_keep=1.0,
    layer="back")` emits a 5-quad slab in the chord+caps frame:
    `s` ∈ [0, 1] runs from `path.start` to `path.end`; `perp` is the
    signed perpendicular distance from the chord centerline; cap
    direction is interpolated linearly between `path.cap_a` (s=0) and
    `path.cap_b` (s=1) so the slab's end faces meet the local edge
    direction at the path's two ends — adjacent tiles' segments meet
    flush across non-axis hex edges (mitred ends).

    The closure is shared by every cross-section's `paint_straight`;
    rail also reads `chord_len` to lay ties at fixed world-unit
    spacing along the chord.
    """
    sx, sy = path.start
    ex, ey = path.end
    cx_, cy_ = ex - sx, ey - sy
    chord_len = math.hypot(cx_, cy_)
    cux, cuy = cx_ / chord_len, cy_ / chord_len
    pux, puy = -cuy, cux  # left perpendicular

    cap_a = path.cap_a
    cap_b = path.cap_b

    def cap_for(s, perp_amount):
        cdx = (1 - s) * cap_a[0] + s * cap_b[0]
        cdy = (1 - s) * cap_a[1] + s * cap_b[1]
        cdn = math.hypot(cdx, cdy) or 1.0
        cdx, cdy = cdx / cdn, cdy / cdn
        dot = cdx * pux + cdy * puy
        if abs(dot) < 1e-6:
            dot = 1e-6 if dot >= 0 else -1e-6
        scale = perp_amount / dot
        return cdx * scale, cdy * scale

    def world(s, perp, z):
        bx = (1 - s) * sx + s * ex
        by = (1 - s) * sy + s * ey
        ox, oy = cap_for(s, perp)
        return (bx + ox, by + oy, z)

    def add_slab(s0, s1, perp0, perp1, z0, z1, color,
                 dither_keep=1.0, layer="back"):
        corners = [
            world(s0, perp0, z0), world(s1, perp0, z0),
            world(s1, perp1, z0), world(s0, perp1, z0),
            world(s0, perp0, z1), world(s1, perp0, z1),
            world(s1, perp1, z1), world(s0, perp1, z1),
        ]
        kw = {"layer": layer, "dither_keep": dither_keep}
        model.add_quad([corners[4], corners[5], corners[6], corners[7]], color, **kw)
        model.add_quad([corners[0], corners[1], corners[5], corners[4]], color, **kw)
        model.add_quad([corners[2], corners[3], corners[7], corners[6]], color, **kw)
        model.add_quad([corners[1], corners[2], corners[6], corners[5]], color, **kw)
        model.add_quad([corners[0], corners[4], corners[7], corners[3]], color, **kw)

    return add_slab, chord_len


# ---- Cross-section interface ----------------------------------------------

@dataclass
class StraightPath:
    """One straight chord between two midpoints, with cap directions
    at each end.  `role` is a hint to the cross-section about how
    much "cadence" content (rail ties, road centre dashes, …) belongs
    on this segment relative to the asset's full-tile reference:

      "full"      — through-tile chord (between opposite edge midpoints)
      "half"      — half-tile chord (centre to one edge midpoint)
      "arc_piece" — short chord piece inside an arc subdivision

    Cross-sections that don't have cadence (road's plain pavement)
    ignore the role.
    """
    start: tuple[float, float]
    end: tuple[float, float]
    cap_a: tuple[float, float]
    cap_b: tuple[float, float]
    role: str = "full"


@dataclass
class ArcPath:
    """Curved path along a circular arc, centred on `(cx, cy)` with the
    given radius, sweeping `delta` radians from `az_start`.  The
    cross-section decides how to render — typically subdivides into
    chord pieces and overlays per-arc cadence elements (rail's radial
    ties).  Roads paint plain chord pieces and stop there."""
    cx: float
    cy: float
    radius: float
    az_start: float
    delta: float


class CrossSection:
    """Asset-specific painter — owns the cross-section geometry that
    the topology builders compose into stubs / curves / junctions.

    Subclasses must override `paint_straight`.  `paint_arc` defaults
    to subdividing the arc into `arc_segments` chord pieces (each
    routed back through `paint_straight` with `role="arc_piece"`);
    assets with extra per-arc cadence (rail's radial ties) override
    `paint_arc` to call `super().paint_arc()` and then add their
    overlay — Python's dynamic dispatch resolves the chord-piece
    `paint_straight` calls to the subclass, so the override gets
    the right cross-section for free.
    """

    # 12 chord pieces over a 120° arc gives ~10° per piece — fine
    # enough that the polyline reads as a smooth curve at 128 px,
    # coarse enough to keep rendering cheap.  Per-asset subclasses
    # can raise it for finer arcs (none do today).
    arc_segments: int = 12

    def paint_straight(self, model, path: StraightPath) -> None:
        raise NotImplementedError

    def paint_arc(self, model, path: ArcPath) -> None:
        for i in range(self.arc_segments):
            t0 = path.az_start + path.delta * (i / self.arc_segments)
            t1 = path.az_start + path.delta * ((i + 1) / self.arc_segments)
            p0 = (path.cx + path.radius * math.cos(t0),
                  path.cy + path.radius * math.sin(t0))
            p1 = (path.cx + path.radius * math.cos(t1),
                  path.cy + path.radius * math.sin(t1))
            cap0 = (math.cos(t0), math.sin(t0))
            cap1 = (math.cos(t1), math.sin(t1))
            self.paint_straight(model, StraightPath(
                start=p0, end=p1, cap_a=cap0, cap_b=cap1, role="arc_piece"))

    def paint(self, model, paths) -> None:
        """Walk a heterogeneous path list, dispatching each path to
        the matching painter.  Used by `render_hex_cell` to consume
        whatever `for_edges_paths` / `axis_slope_paths` returned
        without the asset having to enumerate path types itself."""
        for p in paths:
            if isinstance(p, StraightPath):
                self.paint_straight(model, p)
            elif isinstance(p, ArcPath):
                self.paint_arc(model, p)
            else:
                raise TypeError(f"unknown path: {type(p).__name__}")


# ---- Path builders --------------------------------------------------------
# Each returns a list of paths the cross-section will paint.

def between_edges_paths(edge_a: str, edge_b: str) -> list[StraightPath]:
    """Through-tile straight between two edge midpoints, ends mitred
    along the local edge directions.  For opposite edges the chord is
    perpendicular to both and the result is axis-aligned; for non-
    opposite pairs the ends become parallelogram cuts so adjacent
    tiles' ways meet flush at the shared edge midpoint."""
    return [StraightPath(
        start=edge_midpoint(edge_a), end=edge_midpoint(edge_b),
        cap_a=edge_unit_dir(edge_a), cap_b=edge_unit_dir(edge_b),
        role="full")]


def arc_curve_paths(edge_a: str, edge_b: str) -> list[ArcPath]:
    """Curved path between two 60°-apart hex edges, centred on the
    shared corner.  Radius = R/2 = corner-to-edge-midpoint distance,
    so the arc crosses each edge perpendicular to it at the
    midpoint."""
    corner = shared_corner(edge_a, edge_b)
    cx, cy = HEX_CORNERS[corner]
    a_mid = edge_midpoint(edge_a)
    b_mid = edge_midpoint(edge_b)
    radius = math.hypot(a_mid[0] - cx, a_mid[1] - cy)
    a_az = math.atan2(a_mid[1] - cy, a_mid[0] - cx)
    b_az = math.atan2(b_mid[1] - cy, b_mid[0] - cx)
    delta = (b_az - a_az + math.pi) % (2 * math.pi) - math.pi
    return [ArcPath(cx=cx, cy=cy, radius=radius,
                    az_start=a_az, delta=delta)]


def curve_paths(edge_a: str, edge_b: str):
    """Two-edge connection: 60°-apart pairs (sharing a corner) →
    arc; 120° / 180° pairs → mitred chord."""
    if set(HEX_EDGES[edge_a]) & set(HEX_EDGES[edge_b]):
        return arc_curve_paths(edge_a, edge_b)
    return between_edges_paths(edge_a, edge_b)


def stub_paths(edge: str) -> list[StraightPath]:
    """Half-tile chord from the hex centre to one edge midpoint.
    Edge end mitred along the local edge direction; centre end gets a
    perpendicular cut.  `role="half"` so cross-sections with cadence
    can scale their content by half."""
    start = (0.0, 0.0)
    end = edge_midpoint(edge)
    cap_edge = edge_unit_dir(edge)
    cdx, cdy = end[0] - start[0], end[1] - start[1]
    n = math.hypot(cdx, cdy)
    cap_centre = (-cdy / n, cdx / n)
    return [StraightPath(start=start, end=end,
                         cap_a=cap_centre, cap_b=cap_edge, role="half")]


def junction_paths(edges) -> list[StraightPath]:
    """3+ way junction as one stub per active edge — the placeholder
    "frog blob" shape both rail and road currently use.  Cross-sections
    overlap at the centre; correct silhouette, no real intersection
    geometry yet."""
    return [path for edge in edges for path in stub_paths(edge)]


def for_edges_paths(edges):
    """Dispatch on edge count: 1 → stub, 2 → curve, 3+ → junction.
    The asset's `render_hex_cell(edges)` reduces to building a Model
    and calling `cs.paint(model, for_edges_paths(edges))`."""
    if len(edges) == 1:
        return stub_paths(edges[0])
    if len(edges) == 2:
        return curve_paths(edges[0], edges[1])
    return junction_paths(edges)


def lay_axis_slope(cs: CrossSection, model, low_edge: str) -> None:
    """Lay a way segment on an axis-aligned hex slope: paint the
    through-tile chord between the low and high edges, then tilt
    every vertex's z linearly so the high-edge midpoint sits one
    engine height step above the low-edge midpoint.

    Combines the two steps so callers can't forget the tilt.  The
    `engine_z_per_step` import is lazy because `render.py` pulls in
    numpy; topology callers that don't need slopes shouldn't pay
    the import cost.
    """
    from .render import engine_z_per_step

    high_edge = HEX_OPPOSITE_EDGE[low_edge]
    cs.paint(model, between_edges_paths(low_edge, high_edge))

    low_mx, low_my = edge_midpoint(low_edge)
    high_mx, high_my = edge_midpoint(high_edge)
    chord_dx, chord_dy = high_mx - low_mx, high_my - low_my
    chord_len_sq = chord_dx * chord_dx + chord_dy * chord_dy
    z_total = engine_z_per_step()
    model.verts = [
        (vx, vy, vz + ((vx - low_mx) * chord_dx + (vy - low_my) * chord_dy)
                       / chord_len_sq * z_total)
        for vx, vy, vz in model.verts
    ]
