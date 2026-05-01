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
world +z = up.  The "default" track runs along the world +y axis; for
hex output we render it three times rotated by 0°, 60°, -60° to cover
the three hex straight axes (s_n, sw_ne, se_nw).

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

from render import Scene  # noqa: E402

# --- Material colors ---------------------------------------------------------
BALLAST_DARK = (95, 80, 65)
BALLAST_MID = (130, 110, 85)
TIE_BROWN = (100, 70, 45)
RAIL_GREY = (140, 140, 130)

# --- Track dimensions (1 unit = 1 tile width) -------------------------------
# `length_half` is the half-length along the track axis; for a square pak128
# tile we use 0.5 (full tile diagonal).  The hex tile's edge-midpoint
# spacing is √3/2·R = √3/4 ≈ 0.433 in the same world units, so passing
# 0.433 produces a track that meets the hex silhouette at the edge
# midpoints rather than overshooting.
DEFAULT_LENGTH_HALF = 0.5

# Cross-section dimensions (perpendicular to the track axis).  These match
# the rough proportions of the pak128 cell 1.5 reference: rails ~12 px
# apart on screen at the cell's middle row, ballast ~30 px wide.
BALLAST_TOP_Z = 0.020
TIE_HALF_W = 0.16
TIE_TOP_Z = 0.030
RAIL_HALF_W = 0.008      # rail head thickness (perpendicular to track)
RAIL_GAUGE_HALF = 0.085  # half the rail-to-rail spacing
RAIL_TOP_Z = 0.045

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

N_TIES = 12              # cross-ties along the span


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
    #    margin in (so the angled caps don't clip them off-tile).
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


def main() -> None:
    # Square dimetric verification: world +y axis track and world +x axis
    # track, matching pak128 cells 1.5 and 1.6 respectively.  Tracks ship
    # no per-image (0, 32) shift, so we use Scene's default ground anchor.
    s_ns = Scene()
    build(s_ns, length_half=0.5, axis_yaw_deg=0.0)
    s_ns.render(str(HERE / "out_square_ns.png"))

    s_ew = Scene()
    build(s_ew, length_half=0.5, axis_yaw_deg=90.0)
    s_ew.render(str(HERE / "out_square_ew.png"))

    # Hex bake.  Goes through `build_between_edges` so the three opposite-
    # edge axes (perpendicular caps) and the 120°-apart "curves" (mitred
    # caps along the local edge direction) share one code path.
    #
    # 60°-apart edge pairs (e.g. SE↔NE or SW↔NW, the two `dat` entries
    # `se_ne` and `sw_nw`) don't fit the straight-chord-with-mitred-caps
    # model: their two edges share a corner, and a ballast wider than the
    # mid-edge-to-corner distance (0.125 in unit-tile coords here) cannot
    # be cut to fit between them.  Those need a real arc or a wedge
    # geometry — TBD; left out of the bake until that lands.
    hex_entries = [
        # opposite-edge straights (perpendicular caps)
        ("s_n",   "S",  "N"),
        ("sw_ne", "SW", "NE"),
        ("nw_se", "NW", "SE"),
        # 120°-apart "curves" (mitred caps along the local edge)
        ("se_sw", "SE", "SW"),
        ("nw_ne", "NW", "NE"),
    ]
    for name, edge_a, edge_b in hex_entries:
        s = Scene()
        build_between_edges(s, edge_a, edge_b)
        s.render(str(HERE / f"out_hex_{name}.png"), projection="hex")


if __name__ == "__main__":
    main()
