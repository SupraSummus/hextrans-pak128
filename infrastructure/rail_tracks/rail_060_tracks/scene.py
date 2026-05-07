"""3D model of the rail_060 timber rail track (one tile, mid-segment).

Cross-section (per `RailCrossSection`): banded ballast bed (3 dither
densities), evenly-spaced cross-ties, twin rails — emitted into the
chord+caps frame supplied by `tools/3d/way_topology.py::make_slab_emitter`.
The asset-agnostic topology (stub / curve / junction / axis-slope) lives
in `way_topology` and dispatches into `paint_straight` / `paint_arc`.

Hex deliverable: `rail_060_tracks_hex.png` (8×8 atlas, 63 ribi cells)
plus `rail_060_tracks_hex_slope.png` (1×6 axis slopes), referenced
from the sibling `rail_060_tracks.dat`.  Square verification: `build.py`
lays straights via `way_verify` and diffs against pak128 cells
1.5 / 1.6 (the upstream dimetric NS / EW straight art).

Coordinate system matches `render.py` and `rail_060_bridge/scene.py`:
world +x = east (lower-right onscreen in square dimetric, screen-right
in hex), world +y = north (upper-right in square, screen-up in hex),
world +z = up.  Track is "back" layer — engine draws track before
vehicles, no front/back split.

Tracks ship no per-image dat offset (unlike `rail_060_bridge`'s `,0,32`),
so we render with world z=0 at the default ground anchor sy=96 (=
IMG_SIZE/2 + 32, the flat-tile bbox midpoint).
"""
import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

from bespoke import bake_atlas  # noqa: E402
from render import HexCamera, Model, render  # noqa: E402
from way import HEX_ENTRIES, SLOPE_HEX_ENTRIES, STRAIGHT_CHORD  # noqa: E402
import way_topology as wt  # noqa: E402
# Track-family parameters (cross-section, colours) live in a sibling
# module so other rail assets (rail_060_bridge, future rail_060_*)
# can pull them in without loading this whole scene file.
from track_params import (  # noqa: E402
    BALLAST_TOP_Z, N_TIES, RAIL_GAUGE_HALF, RAIL_GREY, RAIL_HALF_W,
    RAIL_TOP_Z, TIE_BROWN, TIE_HALF_W, TIE_TOP_Z,
)

# Ballast is laid as concentric perpendicular bands so the dither-keep
# tapers from dense near the rails to sparse at the bed's outer edges.
# Distances are |x| from the track centerline.  The reference cell 1.5
# shows this taper as a clear gradient: nearly opaque between the rails,
# fading into pure speckle at the gravel shoulders.
BALLAST_MID = (130, 110, 85)
BALLAST_BANDS = [
    # (inner_half, outer_half, dither_keep)
    (0.000, 0.105, 0.85),  # between & under the rails
    (0.105, 0.155, 0.55),  # inside the cross-tie footprint
    (0.155, 0.220, 0.22),  # gravel shoulders fading into terrain
]


class RailCrossSection(wt.CrossSection):
    """Ballast bed + cross-ties + twin rails on top.

    `paint_straight` reads `path.role` to pick a tie count: a full
    through-tile chord gets `N_TIES`; a half-tile stub gets
    `N_TIES // 2`; an arc-piece (subdivision inside `paint_arc`) gets
    none, since `paint_arc` lays radial ties separately at a cadence
    scaled by arc length.
    """

    _ROLE_TIE_COUNT = {
        "full": N_TIES,
        "half": N_TIES // 2,
        "arc_piece": 0,
    }

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        add_slab, chord_len = wt.make_slab_emitter(model, path)

        # 1. Ballast bands.
        for inner, outer, keep in BALLAST_BANDS:
            for sign in (-1, +1):
                a, b = sign * inner, sign * outer
                add_slab(0.0, 1.0, min(a, b), max(a, b),
                         0.0, BALLAST_TOP_Z, BALLAST_MID, dither_keep=keep)

        # 2. Cross-ties.  Tie thickness in chord direction is fixed in
        #    world units; convert to the s-parameter.  Ties span the
        #    chord from a margin in (so the angled caps don't clip them
        #    off-tile).
        n_ties = self._ROLE_TIE_COUNT[path.role]
        if n_ties > 0:
            tie_half_along_s = 0.025 / chord_len
            margin_s = 1.5 * tie_half_along_s
            for i in range(n_ties):
                s_centre = margin_s + (i + 0.5) / n_ties * (1.0 - 2 * margin_s)
                add_slab(s_centre - tie_half_along_s,
                         s_centre + tie_half_along_s,
                         -TIE_HALF_W, +TIE_HALF_W,
                         BALLAST_TOP_Z, TIE_TOP_Z, TIE_BROWN,
                         dither_keep=0.75)

        # 3. Twin rails on top of the ties.
        for x in (-RAIL_GAUGE_HALF, +RAIL_GAUGE_HALF):
            add_slab(0.0, 1.0, x - RAIL_HALF_W, x + RAIL_HALF_W,
                     TIE_TOP_Z, RAIL_TOP_Z, RAIL_GREY)

    def paint_arc(self, model, path: wt.ArcPath) -> None:
        # super() emits ballast+rails per chord piece (role="arc_piece"
        # → 0 ties).  Lay radial ties here at a per-length cadence so
        # density matches the straight chord ties.
        super().paint_arc(model, path)
        arc_len = abs(path.delta) * path.radius
        n_ties_arc = max(1, round(N_TIES * arc_len / STRAIGHT_CHORD))
        for i in range(n_ties_arc):
            s = (i + 0.5) / n_ties_arc
            _add_radial_tie(model, path.cx, path.cy, path.radius,
                            path.az_start + path.delta * s)


CS = RailCrossSection()


def _add_radial_tie(model: Model, arc_cx: float, arc_cy: float,
                    radius: float, angle: float) -> None:
    """Lay one cross-tie at `radius` and `angle` around arc centre
    `(arc_cx, arc_cy)`.

    The tie is a small radial slab: short along the local arc tangent
    (its "thickness", same 0.05 world units the straight ties use) and
    wide across the rails (`±TIE_HALF_W` along the radial direction).
    Built as 5 outward-facing quads.  Local axes are picked so
    `tangent × radial = +ẑ` (right-handed, matching `Model.add_box`'s
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

    pts = [c(-1, -1, z0), c(+1, -1, z0), c(+1, +1, z0), c(-1, +1, z0),
           c(-1, -1, z1), c(+1, -1, z1), c(+1, +1, z1), c(-1, +1, z1)]

    kw = {"layer": "back", "dither_keep": 0.75}
    model.add_quad([pts[4], pts[5], pts[6], pts[7]], TIE_BROWN, **kw)  # top
    model.add_quad([pts[0], pts[1], pts[5], pts[4]], TIE_BROWN, **kw)  # -v side
    model.add_quad([pts[2], pts[3], pts[7], pts[6]], TIE_BROWN, **kw)  # +v side
    model.add_quad([pts[1], pts[2], pts[6], pts[5]], TIE_BROWN, **kw)  # +u side
    model.add_quad([pts[0], pts[4], pts[7], pts[3]], TIE_BROWN, **kw)  # -u side


def render_hex_cell(edges):
    """Build a fresh Model with one hex sprite and render it through
    the hex camera.  Single edge → stub; two edges → straight or
    curve; 3+ edges → junction (placeholder one-stub-per-edge "frog
    blob").  Returns the (h, w, 4) uint8 RGBA array."""
    m = Model()
    CS.paint(m, wt.for_edges_paths(edges))
    return render(m, HexCamera())


def render_hex_slope_cell(low_edge: str):
    """One axis-aligned slope sprite for the given low edge."""
    m = Model()
    wt.lay_axis_slope(CS, m, low_edge)
    return render(m, HexCamera())


def bake_pakset() -> None:
    bake_atlas(
        out_png=HERE.parent / "rail_060_tracks_hex_slope.png",
        entries=[(label, lambda e=edge: render_hex_slope_cell(e))
                 for label, edge in SLOPE_HEX_ENTRIES],
        repo_root=REPO_ROOT,
    )
    # 8×8 grid (63 cells, last slot empty) — a single 63-wide row is
    # ~8000 px wide and unhelpful to scroll.  Per-row mapping: i//8 →
    # row, i%8 → col, in HEX_ENTRIES order.
    bake_atlas(
        out_png=HERE.parent / "rail_060_tracks_hex.png",
        entries=[(ribi, lambda edges=edges: render_hex_cell(edges))
                 for ribi, edges in HEX_ENTRIES],
        repo_root=REPO_ROOT,
        cols_per_row=8,
    )


if __name__ == "__main__":
    bake_pakset()
