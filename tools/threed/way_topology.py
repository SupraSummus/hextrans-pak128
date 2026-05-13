"""Hex way topology builders parameterised on a `CrossSection`.

Splits the asset-agnostic topology (where on the hex tile a stub /
chord / V-bend / junction / axis-slope segment goes) from the
asset-specific cross-section (rail's ballast bands + ties + rails;
road's pavement slab; tram's pavement + rails; …).  Each builder
calls back into the asset's `CrossSection.paint_straight` for the
actual geometry emission, so adding a new way family is "subclass
`CrossSection`, override one method".

All topology resolves to straight chord pieces — 60° bends are
two-leg V-bends, not arcs, so the cross-section never sees a
curved primitive.
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
    layer="back")` emits a slab in the chord+caps frame: `s` ∈ [0, 1]
    runs from `path.start` to `path.end`; `perp` is the signed
    perpendicular distance from the chord centerline.

    Each end-cap (`path.cap_a` at s=0, `path.cap_b` at s=1) sets the
    lateral shear of that end face — the cap line, not the cap
    direction, is what matters: the slab's perp boundary at s=0
    runs along `cap_a` through `path.start`, the boundary at s=1
    runs along `cap_b` through `path.end`, and each perp boundary
    is the straight line between those two end corners.  In code:
    we precompute the per-cap unit-perp lateral offsets and
    interpolate the OFFSETS linearly along s (which yields a
    straight slab edge for any perp).  Interpolating the cap
    *directions* and re-normalising — what we did until the V-bend
    pieces arrived — hits a 1/(cap · left_perp) singularity when
    the interpolated direction lands parallel to the chord (every
    60° V-bend leg with cap_a along an edge and cap_b along the
    apex bisector crosses chord-parallel at s≈0.5).

    Top face and both perpendicular side faces are always emitted.
    Chord-end side faces at s=s0 / s=s1 are suppressed by
    `path.skip_cap_a` / `path.skip_cap_b`, used for V-bend legs
    that meet at an interior apex with a coplanar opposing-normal
    cap.  Caller must pass caps whose dot with the chord's left
    perpendicular is non-zero — i.e. cap_a / cap_b not parallel to
    the chord direction; the assertion below catches mistakes.

    `chord_len` is returned so cross-sections can scale per-length
    cadence (rail ties, road centre dashes) without duplicating
    the hypot.
    """
    sx, sy = path.start
    ex, ey = path.end
    cx_, cy_ = ex - sx, ey - sy
    chord_len = math.hypot(cx_, cy_)
    cux, cuy = cx_ / chord_len, cy_ / chord_len
    pux, puy = -cuy, cux  # left perpendicular

    def _unit_offset(cap):
        dot = cap[0] * pux + cap[1] * puy
        assert abs(dot) > 1e-9, (
            f"cap {cap} is parallel to chord ({cux:.3f}, {cuy:.3f}) — "
            "perp boundaries would be undefined")
        return cap[0] / dot, cap[1] / dot

    ox_a, oy_a = _unit_offset(path.cap_a)
    ox_b, oy_b = _unit_offset(path.cap_b)

    def world(s, perp, z):
        bx = (1 - s) * sx + s * ex
        by = (1 - s) * sy + s * ey
        ox = ((1 - s) * ox_a + s * ox_b) * perp
        oy = ((1 - s) * oy_a + s * oy_b) * perp
        return (bx + ox, by + oy, z)

    skip_a = path.skip_cap_a
    skip_b = path.skip_cap_b

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
        if not skip_b:
            model.add_quad([corners[1], corners[2], corners[6], corners[5]], color, **kw)
        if not skip_a:
            model.add_quad([corners[0], corners[4], corners[7], corners[3]], color, **kw)

    return add_slab, chord_len


# ---- Cross-section interface ----------------------------------------------

@dataclass
class StraightPath:
    """One straight chord between two points, with cap directions at
    each end.  Cross-sections with per-length cadence (rail ties,
    road centre dashes) scale their content off `chord_len` from
    `make_slab_emitter` so density stays uniform across stubs,
    full chords, and V-bend legs without a discrete role enum.

    `skip_cap_a` / `skip_cap_b` suppress the chord-end side faces at
    s=0 / s=1 respectively.  Used for V-bend legs whose apex caps
    meet the matching leg's cap on the same plane with opposing
    normals — drawing both produces z-fighting that flickers between
    the bright sun-lit face and the dark ambient-only face.
    """
    start: tuple[float, float]
    end: tuple[float, float]
    cap_a: tuple[float, float]
    cap_b: tuple[float, float]
    skip_cap_a: bool = False
    skip_cap_b: bool = False


class CrossSection:
    """Asset-specific painter — owns the cross-section geometry that
    the topology builders compose into stubs / curves / V-bends /
    junctions.  Subclasses override `paint_straight`; the topology
    layer only emits `StraightPath`s, so that's the single dispatch
    point.
    """

    def paint_straight(self, model, path: StraightPath) -> None:
        raise NotImplementedError

    def paint(self, model, paths) -> None:
        """Walk a path list, dispatching each path to `paint_straight`.
        Used by `render_hex_cell` to consume whatever
        `for_edges_paths` / `axis_slope_paths` returned without the
        asset having to enumerate types itself."""
        for p in paths:
            self.paint_straight(model, p)


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
        cap_a=edge_unit_dir(edge_a), cap_b=edge_unit_dir(edge_b))]


def bend_curve_paths(edge_a: str, edge_b: str) -> list[StraightPath]:
    """V-bend between two 60°-apart hex edges sharing one corner.
    The apex sits on the radial through the shared corner at half
    the hex radius — i.e. at `corner / 2` — and the apex miter cap
    is the unit vector toward the corner (which is the bisector of
    the two edge directions there, since the corner is equidistant
    from both edges by hex symmetry).  Each leg is therefore a
    piece of an off-axis through-tile chord: leg A from M_a to the
    apex, parallel to edge_b; leg B from the apex to M_b, parallel
    to edge_a.  Apex caps are suppressed (they're internal and
    would z-fight against each other)."""
    corner = shared_corner(edge_a, edge_b)
    cx, cy = HEX_CORNERS[corner]                       # unit vector
    apex = (cx / 2.0, cy / 2.0)
    apex_cap = (cx, cy)
    return [
        StraightPath(start=edge_midpoint(edge_a), end=apex,
                     cap_a=edge_unit_dir(edge_a), cap_b=apex_cap,
                     skip_cap_b=True),
        StraightPath(start=apex, end=edge_midpoint(edge_b),
                     cap_a=apex_cap, cap_b=edge_unit_dir(edge_b),
                     skip_cap_a=True),
    ]


def curve_paths(edge_a: str, edge_b: str):
    """Two-edge connection: 60°-apart pairs (sharing a corner) →
    V-bend (two off-axis chord pieces); 120° / 180° pairs → mitred
    through-tile chord."""
    if set(HEX_EDGES[edge_a]) & set(HEX_EDGES[edge_b]):
        return bend_curve_paths(edge_a, edge_b)
    return between_edges_paths(edge_a, edge_b)


def stub_paths(edge: str) -> list[StraightPath]:
    """Half-tile chord from the hex centre to one edge midpoint.
    Edge end mitred along the local edge direction; centre end gets a
    perpendicular cut."""
    end = edge_midpoint(edge)
    n = math.hypot(end[0], end[1])
    cap_centre = (-end[1] / n, end[0] / n)
    return [StraightPath(start=(0.0, 0.0), end=end,
                         cap_a=cap_centre, cap_b=edge_unit_dir(edge))]


def junction_paths(edges):
    """N≥3 way junction as the union of all `C(N,2)` pairwise edge
    connections, each routed via `curve_paths` — so 60°-apart pairs
    become V-bends and 120° / 180° pairs become mitred through-tile
    chords.  An asymmetric 3-way like {N, NE, S} reads as one
    straight (N↔S) plus one V-bend (N↔NE) plus one 120° chord
    (NE↔S), instead of three stubs meeting at the centre.
    Through-routes therefore continue as real chords across the
    junction tile."""
    return [path
            for i, a in enumerate(edges)
            for b in edges[i + 1:]
            for path in curve_paths(a, b)]


def for_edges_paths(edges):
    """Dispatch on edge count: 1 → stub, 2 → curve, 3+ → junction.
    The asset's `render_hex_cell(edges)` reduces to building a Model
    and calling `cs.paint(model, for_edges_paths(edges))`."""
    if len(edges) == 1:
        return stub_paths(edges[0])
    if len(edges) == 2:
        return curve_paths(edges[0], edges[1])
    return junction_paths(edges)


def lay_axis_slope(cs: CrossSection, model, low_edge: str,
                   *, steps: int = 1) -> None:
    """Lay a way segment on an axis-aligned hex slope: paint the
    through-tile chord between the low and high edges, then tilt
    every vertex's z linearly so the high-edge midpoint sits
    `steps` engine height steps above the low-edge midpoint.

    `steps=1` is the single-height ramp baked into `slope_t::*_narrow`
    / `*_wide`; `steps=2` matches the double-height 012210 ramp baked
    into `slope_t::*_double`.  The slab itself only models the way
    surface and its chord climb — the off-axis ground inflection
    that distinguishes narrow / wide / double on the same axis (the
    perpendicular side corners' actual height: 0 for narrow, 1 for
    wide and double) is rendered separately by the ground baker.

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
    z_total = engine_z_per_step(height_step=steps)
    model.verts = [
        (vx, vy, vz + ((vx - low_mx) * chord_dx + (vy - low_my) * chord_dy)
                       / chord_len_sq * z_total)
        for vx, vy, vz in model.verts
    ]
