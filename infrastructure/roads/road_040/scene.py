"""3D model of the road_040 stone city road (one tile, mid-segment).

Cross-section (per `RoadCrossSection`): one full-width pavement slab,
opaque (no banded dither — unlike rail's ballast bed which fades into
terrain at the shoulders).  Topology (stub / curve / junction / axis-
slope) comes from `tools/3d/way_topology.py`; family-shared materials
and dimensions come from `infrastructure/roads/road_params.py`, so the
asset code reduces to "subclass `CrossSection`, point the bake at the
atlas filename".

Hex deliverable: `road_040_hex.png` (8×8 atlas, 63 ribi cells) plus
`road_040_hex_slope.png` (1×6 axis slopes), referenced from the
sibling `road_040.dat`.  Square verification: `build.py` lays straights
via `way_verify` and diffs against pak128 cells 1.5 / 1.6 (the upstream
dimetric NS / EW straight art).
"""
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROAD_FAMILY = HERE.parent          # infrastructure/roads/
REPO_ROOT = ROAD_FAMILY.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))
sys.path.insert(0, str(ROAD_FAMILY))

from bespoke import bake_atlas  # noqa: E402
from render import HexCamera, Model, render  # noqa: E402
from road_params import (  # noqa: E402
    PAVEMENT_GREY, PAVEMENT_HALF_W, PAVEMENT_TOP_Z,
)
from way import HEX_ENTRIES, SLOPE_HEX_ENTRIES  # noqa: E402
import way_topology as wt  # noqa: E402


class RoadCrossSection(wt.CrossSection):
    """One pavement slab, full chord width, opaque.  No `role`-based
    cadence (no ties / no markings yet); default `paint_arc`
    chord-piece subdivision is sufficient since pavement is uniform
    along the arc."""

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        add_slab, _chord_len = wt.make_slab_emitter(model, path)
        add_slab(0.0, 1.0, -PAVEMENT_HALF_W, +PAVEMENT_HALF_W,
                 0.0, PAVEMENT_TOP_Z, PAVEMENT_GREY)


CS = RoadCrossSection()


def render_hex_cell(edges):
    m = Model()
    CS.paint(m, wt.for_edges_paths(edges))
    return render(m, HexCamera())


def render_hex_slope_cell(low_edge: str):
    m = Model()
    wt.lay_axis_slope(CS, m, low_edge)
    return render(m, HexCamera())


def bake_pakset() -> None:
    bake_atlas(
        out_png=HERE.parent / "road_040_hex_slope.png",
        entries=[(label, lambda e=edge: render_hex_slope_cell(e))
                 for label, edge in SLOPE_HEX_ENTRIES],
        repo_root=REPO_ROOT,
    )
    bake_atlas(
        out_png=HERE.parent / "road_040_hex.png",
        entries=[(ribi, lambda edges=edges: render_hex_cell(edges))
                 for ribi, edges in HEX_ENTRIES],
        repo_root=REPO_ROOT,
        cols_per_row=8,
    )


if __name__ == "__main__":
    bake_pakset()
