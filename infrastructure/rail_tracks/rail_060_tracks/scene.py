"""3D model of the rail_060 timber rail track (one tile, mid-segment).

Reference (square dimetric): infrastructure/rail_tracks/rail_060_tracks.png.
The dat repoints square cells onto hex direction names, but the cells
themselves are the original pak128 square art:

  rail_060_tracks.1.5  — straight track running along world +y axis
                         (square dimetric "sw_ne" / hex "s_n" / "sw_ne")
  rail_060_tracks.1.6  — straight track running along world +x axis
                         (square dimetric "se_nw")

Track parts (one shared 3D scene used for square verification *and*
hex bake; see `tools/3d/render.py` projection split):

  - ballast bed      : low trapezoidal gravel bed, full track length
  - cross-ties       : evenly spaced timber blocks across the bed
  - twin rails       : thin metal strips on top of the ties

Everything is "back" layer — the engine draws track before vehicles, so
there's no front/back split (unlike the rail_060_bridge that has a
viewer-side railing).

Coordinate system matches `render.py` and `rail_060_bridge/scene.py`:
world +x = east (lower-right onscreen in square dimetric, screen-right
in hex), world +y = north (upper-right in square, screen-up in hex),
world +z = up.  The "default" track runs along the world +y axis (used
by `build()` for the two square verification renders).  Hex output
goes through `build_curve()` / `build_stub()` instead, which lay each
sprite directly between the relevant hex edge midpoints — no
rotate-and-clip pass.

Tracks have no per-image sheet offset in the dat (unlike bridges which
ship `,0,32`), so we render with world z=0 at the default ground
anchor sy=96 (= IMG_SIZE/2 + 32, the flat-tile bbox midpoint).
"""
import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

from bespoke import bake_atlas  # noqa: E402
from render import Scene  # noqa: E402
# Track-family parameters (cross-section, colours) live in a sibling
# module so other rail assets (rail_060_bridge, future rail_060_*)
# can pull them in without loading this whole scene file.
from track_params import (  # noqa: E402
    BALLAST_TOP_Z, N_TIES, RAIL_GAUGE_HALF, RAIL_GREY, RAIL_HALF_W,
    RAIL_TOP_Z, TIE_BROWN, TIE_HALF_W, TIE_TOP_Z,
)

# --- Material colors (track-only — not part of the shared family) -----------
BALLAST_DARK = (95, 80, 65)
BALLAST_MID = (130, 110, 85)

# --- Track dimensions (1 unit = 1 tile width) -------------------------------
# `length_half` is the half-length along the track axis; for a square pak128
# tile we use 0.5 (full tile diagonal).  The hex tile's edge-midpoint
# spacing is √3/2·R = √3/4 ≈ 0.433 in the same world units, so passing
# 0.433 produces a track that meets the hex silhouette at the edge
# midpoints rather than overshooting.
DEFAULT_LENGTH_HALF = 0.5

# Ballast is laid as concentric perpendicular bands so the dither-keep
# tapers from dense near the rails to sparse at the bed's outer edges.
# Distances are |x| from the track centerline.  The reference cell 1.5
# shows this taper as a clear gradient: nearly opaque between the rails,
# fading into pure speckle at the gravel shoulders.
BALLAST_BANDS = [
    # (inner_half, outer_half, dither_keep)
    (0.000, 0.105, 0.85),  # between & under the rails
    (0.105, 0.155, 0.55),  # inside the cross-tie footprint
    (0.155, 0.220, 0.22),  # gravel shoulders fading into terrain
]
BALLAST_HALF_W = BALLAST_BANDS[-1][1]


def _add_track_segment(scene, start_mid, end_mid,
                       cap_dir_start, cap_dir_end,
                       n_ties: int):
    """Lay one straight track segment with arbitrary end caps.

    A "segment" is the chord from `start_mid` to `end_mid`.  The track's
    cross-section is taken perpendicular to the chord at every point
    along it, *except* at the two ends where the cap can lie along an
    arbitrary direction in the ground plane (`cap_dir_start` /
    `cap_dir_end`).  When the cap directions are perpendicular to the
    chord this collapses to a plain rectangular footprint (the
    axis-aligned NS / EW / hex-straight case); when they're parallel to
    the local hex edge the segment renders as a parallelogram (mitred)
    so adjacent tiles' rails meet flush across non-axis edges like SE,
    SW.

    All quads are emitted in world space; per-band `dither_keep`,
    cross-tie cadence, and rail height carry the same convention as the
    axis-aligned case.
    """
    sx, sy = start_mid
    ex, ey = end_mid
    # Chord direction (unit) and perpendicular.
    cx, cy = ex - sx, ey - sy
    chord_len = math.hypot(cx, cy)
    cux, cuy = cx / chord_len, cy / chord_len
    pux, puy = -cuy, cux  # left perpendicular

    def cap_for(s, perp_amount):
        # Linearly interpolate cap direction along the chord, scaled so
        # the +1/-1 perp value lands on the cap's edge.  Cap directions
        # passed in are unit vectors; the length we want at world-perp
        # `perp_amount` is `perp_amount / sin(angle_to_chord)` so the
        # perpendicular distance from the chord matches.  When the cap
        # is perpendicular to the chord this is just `perp_amount`.
        cdx = (1 - s) * cap_dir_start[0] + s * cap_dir_end[0]
        cdy = (1 - s) * cap_dir_start[1] + s * cap_dir_end[1]
        cdn = math.hypot(cdx, cdy) or 1.0
        cdx, cdy = cdx / cdn, cdy / cdn
        # Scale: we want the world-space perpendicular distance from the
        # chord (along (pux, puy)) to equal perp_amount.  Project cap
        # direction onto perpendicular: dot.  Then multiplier = 1/dot.
        dot = cdx * pux + cdy * puy
        if abs(dot) < 1e-6:
            dot = 1e-6 if dot >= 0 else -1e-6
        scale = perp_amount / dot
        return cdx * scale, cdy * scale

    def world(s, perp, z):
        # Centerline point + cap-aligned perpendicular offset.
        bx = (1 - s) * sx + s * ex
        by = (1 - s) * sy + s * ey
        ox, oy = cap_for(s, perp)
        return (bx + ox, by + oy, z)

    def add_slab(s0, s1, perp0, perp1, z0, z1, color, dither_keep=1.0):
        corners = [
            world(s0, perp0, z0), world(s1, perp0, z0),
            world(s1, perp1, z0), world(s0, perp1, z0),
            world(s0, perp0, z1), world(s1, perp0, z1),
            world(s1, perp1, z1), world(s0, perp1, z1),
        ]
        kw = {"layer": "back", "dither_keep": dither_keep}
        scene.add_quad([corners[4], corners[5], corners[6], corners[7]], color, **kw)
        scene.add_quad([corners[0], corners[1], corners[5], corners[4]], color, **kw)
        scene.add_quad([corners[2], corners[3], corners[7], corners[6]], color, **kw)
        scene.add_quad([corners[1], corners[2], corners[6], corners[5]], color, **kw)
        scene.add_quad([corners[0], corners[4], corners[7], corners[3]], color, **kw)

    # 1. Ballast bands.
    for inner, outer, keep in BALLAST_BANDS:
        for sign in (-1, +1):
            a, b = sign * inner, sign * outer
            add_slab(0.0, 1.0, min(a, b), max(a, b),
                     0.0, BALLAST_TOP_Z, BALLAST_MID, dither_keep=keep)

    # 2. Cross-ties.  Tie thickness in chord direction is fixed in world
    #    units; convert to the s-parameter.  Ties span the chord from a
    #    margin in (so the angled caps don't clip them off-tile).  Skipped
    #    when n_ties == 0 — arc curves lay their ballast + rails as short
    #    chord pieces but place ties separately along the arc with
    #    `_add_radial_tie`, since the per-segment chord is shorter than a
    #    single tie's world-space thickness.
    if n_ties > 0:
        tie_half_along_s = 0.025 / chord_len
        margin_s = 1.5 * tie_half_along_s
        for i in range(n_ties):
            s_centre = margin_s + (i + 0.5) / n_ties * (1.0 - 2 * margin_s)
            add_slab(s_centre - tie_half_along_s, s_centre + tie_half_along_s,
                     -TIE_HALF_W, +TIE_HALF_W,
                     BALLAST_TOP_Z, TIE_TOP_Z, TIE_BROWN, dither_keep=0.75)

    # 3. Twin rails on top of the ties.
    for x in (-RAIL_GAUGE_HALF, +RAIL_GAUGE_HALF):
        add_slab(0.0, 1.0, x - RAIL_HALF_W, x + RAIL_HALF_W,
                 TIE_TOP_Z, RAIL_TOP_Z, RAIL_GREY)


def build(scene: Scene, length_half: float = DEFAULT_LENGTH_HALF,
          axis_yaw_deg: float = 0.0) -> None:
    """Build a straight rail track centred on the origin.

    The default track runs along the world +y axis.  Pass `axis_yaw_deg`
    to rotate the whole track around z (e.g. ±60° for the two non-NS
    hex axes; ±90° for the world-x-aligned square sheet entry).
    """
    yaw = math.radians(axis_yaw_deg)
    tx, ty = -math.sin(yaw), math.cos(yaw)
    start = (-length_half * tx, -length_half * ty)
    end = (+length_half * tx, +length_half * ty)
    perp = (-ty, tx)
    _add_track_segment(scene, start, end, perp, perp, n_ties=N_TIES)


# ---- Hex tile geometry helpers --------------------------------------------

# Flat-top hex of radius 0.5 centred at origin.  Corner order matches
# `hex_corner_t` in `dataobj/ribi.h`.
_R = 0.5
HEX_CORNERS = {
    "E":  ( _R,                 0.0),
    "SE": ( _R / 2,            -_R * math.sqrt(3) / 2),
    "SW": (-_R / 2,            -_R * math.sqrt(3) / 2),
    "W":  (-_R,                 0.0),
    "NW": (-_R / 2,             _R * math.sqrt(3) / 2),
    "NE": ( _R / 2,             _R * math.sqrt(3) / 2),
}
# Each named edge → (corner_a, corner_b).  Edge midpoint = mean of corners.
HEX_EDGES = {
    "N":  ("NE", "NW"),
    "NE": ("E",  "NE"),
    "SE": ("SE", "E"),
    "S":  ("SW", "SE"),
    "SW": ("W",  "SW"),
    "NW": ("NW", "W"),
}


def _edge_midpoint(edge: str) -> tuple[float, float]:
    a, b = HEX_EDGES[edge]
    ax, ay = HEX_CORNERS[a]
    bx, by = HEX_CORNERS[b]
    return ((ax + bx) / 2.0, (ay + by) / 2.0)


def _edge_unit_dir(edge: str) -> tuple[float, float]:
    a, b = HEX_EDGES[edge]
    ax, ay = HEX_CORNERS[a]
    bx, by = HEX_CORNERS[b]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


def build_between_edges(scene: Scene, edge_a: str, edge_b: str,
                        n_ties: int = N_TIES) -> None:
    """Lay a straight track between the midpoints of two hex edges,
    with each end mitred along the local edge direction.

    For opposite edges (`N` ↔ `S`, `NE` ↔ `SW`, `NW` ↔ `SE`) the chord
    is perpendicular to both edges, the cap directions coincide with the
    perpendicular, and the result is the same axis-aligned rectangle
    `build()` produces.  For non-opposite pairs (e.g. `SE` ↔ `SW`) the
    chord crosses each edge at an angle and the ends become parallelogram
    cuts, so adjacent tiles' tracks meet flush at the shared edge midpoint.
    """
    start = _edge_midpoint(edge_a)
    end = _edge_midpoint(edge_b)
    cap_a = _edge_unit_dir(edge_a)
    cap_b = _edge_unit_dir(edge_b)
    _add_track_segment(scene, start, end, cap_a, cap_b, n_ties=n_ties)


# Hex straight tracks span between opposite edge midpoints, distance
# 2·R·√3/2 = R·√3 ≈ 0.866.  Used to scale arc tie counts so density
# matches the straight ties.
_STRAIGHT_CHORD = 2.0 * math.hypot(*_edge_midpoint("N"))


def _shared_corner(edge_a: str, edge_b: str) -> str:
    """The corner shared by two 60°-apart hex edges; the centre of the
    corner-radius arc that connects their midpoints."""
    shared = set(HEX_EDGES[edge_a]) & set(HEX_EDGES[edge_b])
    assert len(shared) == 1, (
        f"edges {edge_a}/{edge_b} don't share exactly one corner")
    return next(iter(shared))


def _add_radial_tie(scene: Scene, arc_cx: float, arc_cy: float,
                    radius: float, angle: float) -> None:
    """Lay one cross-tie at `radius` and `angle` around arc centre
    `(arc_cx, arc_cy)`.

    The tie is a small radial slab: short along the local arc tangent
    (its "thickness", same 0.05 world units the straight ties use) and
    wide across the rails (`±TIE_HALF_W` along the radial direction).
    Built as 5 outward-facing quads.  Local axes are picked so
    `tangent × radial = +ẑ` (right-handed, matching `Scene.add_box`'s
    x×y=z convention) — using +tangent = (-sin t, cos t) (the CCW arc
    direction) as `u` and +radial = (cos t, sin t) as `v` gives
    u×v = +ẑ, so the same quad enumeration as `add_box` produces
    outward-facing normals.
    """
    cos_t, sin_t = math.cos(angle), math.sin(angle)
    ux, uy = -sin_t, cos_t          # +tangent (along rails)
    vx, vy = cos_t, sin_t           # +radial  (across rails)
    cx, cy = arc_cx + radius * cos_t, arc_cy + radius * sin_t

    U = 0.025                       # half-thickness along tangent
    V = TIE_HALF_W                  # half-width along radial
    z0, z1 = BALLAST_TOP_Z, TIE_TOP_Z

    def c(su, sv, z):
        return (cx + su * U * ux + sv * V * vx,
                cy + su * U * uy + sv * V * vy,
                z)

    # 8 corners ordered like Scene.add_box's (x,y,z) lattice with
    # (su, sv) playing the role of (sx, sy):
    #   0:(-,-,z0) 1:(+,-,z0) 2:(+,+,z0) 3:(-,+,z0)
    #   4:(-,-,z1) 5:(+,-,z1) 6:(+,+,z1) 7:(-,+,z1)
    pts = [c(-1, -1, z0), c(+1, -1, z0), c(+1, +1, z0), c(-1, +1, z0),
           c(-1, -1, z1), c(+1, -1, z1), c(+1, +1, z1), c(-1, +1, z1)]

    kw = {"layer": "back", "dither_keep": 0.75}
    scene.add_quad([pts[4], pts[5], pts[6], pts[7]], TIE_BROWN, **kw)  # top
    scene.add_quad([pts[0], pts[1], pts[5], pts[4]], TIE_BROWN, **kw)  # -v side
    scene.add_quad([pts[2], pts[3], pts[7], pts[6]], TIE_BROWN, **kw)  # +v side
    scene.add_quad([pts[1], pts[2], pts[6], pts[5]], TIE_BROWN, **kw)  # +u side
    scene.add_quad([pts[0], pts[4], pts[7], pts[3]], TIE_BROWN, **kw)  # -u side


def _build_arc_curve(scene: Scene, edge_a: str, edge_b: str,
                     n_segments: int = 12) -> None:
    """Lay a curved track between two 60°-apart hex edges (sharing a corner).

    The arc is centred on the shared corner, with radius = R/2 = distance
    from corner to either adjacent edge midpoint.  At each midpoint the
    arc's radial direction is parallel to the edge (the corner-to-midpoint
    vector runs along the edge's bisector), so the arc crosses each edge
    perpendicular to it and meets it at the midpoint — flush with whatever
    a neighbouring tile lays through that same midpoint.  The arc bulges
    away from the shared corner, toward the hex centre, which is the
    natural railway turn (centre of curvature on the inside of the bend).

    Ballast and rails are laid as `n_segments` short chord pieces with
    radial-direction caps at every joint, so adjacent segments share an
    endpoint cap and the boundary segments' caps reduce to the edge
    direction at the two edge midpoints.

    Cross-ties are placed separately as discrete radial slabs at evenly
    spaced angles along the arc — one tie's chord-direction thickness
    (0.05) is larger than a single arc segment's chord, so the per-
    segment tie placement in `_add_track_segment` would clump every tie
    at s ≈ 0.5 of its segment.  The tie count is scaled by arc length
    vs. the straight through-tile chord so density matches the straight
    ties.
    """
    corner = _shared_corner(edge_a, edge_b)
    arc_cx, arc_cy = HEX_CORNERS[corner]
    a_mid = _edge_midpoint(edge_a)
    b_mid = _edge_midpoint(edge_b)
    radius = math.hypot(a_mid[0] - arc_cx, a_mid[1] - arc_cy)
    a_az = math.atan2(a_mid[1] - arc_cy, a_mid[0] - arc_cx)
    b_az = math.atan2(b_mid[1] - arc_cy, b_mid[0] - arc_cx)
    # Short signed sweep from a→b around the corner; |Δaz| = 2π/3.
    delta = (b_az - a_az + math.pi) % (2 * math.pi) - math.pi
    for i in range(n_segments):
        t0 = a_az + delta * (i / n_segments)
        t1 = a_az + delta * ((i + 1) / n_segments)
        p0 = (arc_cx + radius * math.cos(t0),
              arc_cy + radius * math.sin(t0))
        p1 = (arc_cx + radius * math.cos(t1),
              arc_cy + radius * math.sin(t1))
        # Cap = radial direction at the joint (perpendicular to the
        # local chord).  At the two boundary midpoints this lines up
        # with the edge direction, so adjacent tiles meet flush.
        cap0 = (math.cos(t0), math.sin(t0))
        cap1 = (math.cos(t1), math.sin(t1))
        _add_track_segment(scene, p0, p1, cap0, cap1, n_ties=0)

    arc_len = abs(delta) * radius
    n_ties_arc = max(1, round(N_TIES * arc_len / _STRAIGHT_CHORD))
    for i in range(n_ties_arc):
        s = (i + 0.5) / n_ties_arc
        _add_radial_tie(scene, arc_cx, arc_cy, radius, a_az + delta * s)


def build_curve(scene: Scene, edge_a: str, edge_b: str) -> None:
    """Lay a track between two hex edges, dispatching on whether they
    share a corner: 60°-apart pairs do (→ corner-centred arc,
    `_build_arc_curve`); 120° / 180° pairs don't (→ chord with mitred /
    perpendicular caps, `build_between_edges`).

    Single entrypoint so callers (preview, bake) don't enumerate the
    three families."""
    if set(HEX_EDGES[edge_a]) & set(HEX_EDGES[edge_b]):
        _build_arc_curve(scene, edge_a, edge_b)
    else:
        build_between_edges(scene, edge_a, edge_b)


def build_stub(scene: Scene, edge: str, n_ties: int = N_TIES // 2) -> None:
    """Lay a half-tile track from the hex centre to one edge midpoint.

    The edge end is mitred along the local edge direction (so it meets
    an adjacent tile's track flush at the shared edge midpoint, same
    convention as `build_between_edges`); the centre end gets a clean
    perpendicular cut — no buffer-stop geometry yet, the rails just
    end.  `n_ties` is half the through-tile count by default since the
    chord is half as long.
    """
    start = (0.0, 0.0)
    end = _edge_midpoint(edge)
    cap_edge = _edge_unit_dir(edge)
    cdx, cdy = end[0] - start[0], end[1] - start[1]
    n = math.hypot(cdx, cdy)
    cap_centre = (-cdy / n, cdx / n)
    _add_track_segment(scene, start, end, cap_centre, cap_edge, n_ties=n_ties)


# Hex sprites the dat declares.  Ribi codes follow
# `way_writer.cc::hex_ribi_code` (low-bit-first joined with `_`,
# bit positions SE=1, S=2, SW=4, NW=8, N=16, NE=32).  Listed in
# ascending ribi-value order — 6 single-edge stubs first (ribi 1,
# 2, 4, 8, 16, 32 → cols 0..5), then 15 edge pairs (ribi 3, 5, 6,
# 9, 10, 12, … → cols 6..20).  Single source of truth for both
# the per-cell preview renders and the atlas bake.
HEX_ENTRIES = [
    # ribi    edges (1 entry → stub, 2 entries → straight or curve)
    ("se",    ("SE",)),
    ("s",     ("S",)),
    ("sw",    ("SW",)),
    ("nw",    ("NW",)),
    ("n",     ("N",)),
    ("ne",    ("NE",)),
    ("se_s",  ("SE", "S")),
    ("se_sw", ("SE", "SW")),
    ("s_sw",  ("S",  "SW")),
    ("se_nw", ("SE", "NW")),  # axis straight
    ("s_nw",  ("S",  "NW")),
    ("sw_nw", ("SW", "NW")),
    ("se_n",  ("SE", "N")),
    ("s_n",   ("S",  "N")),   # axis straight
    ("sw_n",  ("SW", "N")),
    ("nw_n",  ("NW", "N")),
    ("se_ne", ("SE", "NE")),
    ("s_ne",  ("S",  "NE")),
    ("sw_ne", ("SW", "NE")),  # axis straight
    ("nw_ne", ("NW", "NE")),
    ("n_ne",  ("N",  "NE")),
]


def render_hex_cell(edges):
    """Build a fresh Scene with one hex sprite and render it through
    the hex camera.  Single edge → stub; two edges → straight or
    curve (dispatched by `build_curve`).  Returns the (h, w, 4) uint8
    RGBA array; no file written.  Atlas bake and per-cell preview
    share this entrypoint."""
    s = Scene()
    if len(edges) == 1:
        build_stub(s, edges[0])
    else:
        build_curve(s, edges[0], edges[1])
    return s.render(out_path=None, projection="hex")


def main() -> None:
    # Square dimetric verification: world +y / +x axis tracks, matching
    # pak128 cells 1.5 / 1.6.  Tracks ship no per-image (0, 32) shift, so
    # we use Scene's default ground anchor.
    s_ns = Scene()
    build(s_ns, length_half=0.5, axis_yaw_deg=0.0)
    s_ns.render(str(HERE / "out_square_ns.png"))

    s_ew = Scene()
    build(s_ew, length_half=0.5, axis_yaw_deg=90.0)
    s_ew.render(str(HERE / "out_square_ew.png"))

    # Per-cell hex previews are written by `bake_pakset()` as a
    # side-effect of the atlas bake — single source for the rgba.


# Atlas bake of the hex sprites in HEX_ENTRIES; re-runs must be
# byte-identical.  See TODO.md "Track-sprite baker" for the dat-side
# coverage status.

def bake_pakset() -> None:
    bake_atlas(
        out_png=HERE.parent / "rail_060_tracks_hex.png",
        entries=[(ribi, lambda edges=edges: render_hex_cell(edges))
                 for ribi, edges in HEX_ENTRIES],
        repo_root=REPO_ROOT,
    )


if __name__ == "__main__":
    main()
    bake_pakset()
