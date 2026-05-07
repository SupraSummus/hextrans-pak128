"""3D model of the road_040 stone city road (one tile, mid-segment).

Cross-section (per `RoadCrossSection`): a dark olive-brown carriageway
down the middle flanked by two lighter, dithered cobblestone kerbs —
matching the pak128 reference (cells 1.5 / 1.6 in `road_040.png`).
Topology (stub / curve / junction / axis-slope) comes from
`tools/threed/way_topology.py`; family-shared materials and dimensions
come from `infrastructure/roads/road_params.py`, so the asset code
reduces to "subclass `CrossSection`, point the bake at the atlas
filename".

Hex deliverable: `road_040_hex.png` (8×8 atlas, 63 ribi cells) plus
`road_040_hex_slope.png` (1×6 axis slopes), referenced from the
sibling `road_040.dat`.  Square verification: `build.py` lays straights
via `way_verify` and diffs against pak128 cells 1.5 / 1.6 (the upstream
dimetric NS / EW straight art).
"""
from pathlib import Path

from tools.threed import way_topology as wt
from tools.threed.bespoke import bake_atlas
from tools.threed.render import HexCamera, Model, render
from tools.threed.way import HEX_ENTRIES, SLOPE_HEX_ENTRIES

from infrastructure.roads.road_params import (
    CARRIAGEWAY_BROWN, CARRIAGEWAY_HALF_W, CARRIAGEWAY_TOP_Z,
    PAVEMENT_HALF_W, SIDEWALK_DITHER_KEEP, SIDEWALK_GREY, SIDEWALK_TOP_Z,
)


HERE = Path(__file__).resolve().parent


class RoadCrossSection(wt.CrossSection):
    """Three-band cross-section: kerb / carriageway / kerb.  Default
    `paint_arc` chord-piece subdivision is sufficient since the bands
    are uniform along the chord (no tie / dash cadence yet)."""

    def paint_straight(self, model, path: wt.StraightPath) -> None:
        add_slab, _chord_len = wt.make_slab_emitter(model, path)

        # Carriageway down the middle, dithered cobblestone kerbs on
        # the two long sides.  Carriageway sits a hair above the kerbs
        # (CARRIAGEWAY_TOP_Z > SIDEWALK_TOP_Z) so it wins the z-buffer
        # at junctions where one stub's kerb crosses another stub's
        # carriageway.  Perp range is ascending in both bands so the
        # top-face winding is consistent (normal +z).
        add_slab(0.0, 1.0, -CARRIAGEWAY_HALF_W, +CARRIAGEWAY_HALF_W,
                 0.0, CARRIAGEWAY_TOP_Z, CARRIAGEWAY_BROWN)
        for perp_lo, perp_hi in (
            (-PAVEMENT_HALF_W, -CARRIAGEWAY_HALF_W),
            (+CARRIAGEWAY_HALF_W, +PAVEMENT_HALF_W),
        ):
            add_slab(0.0, 1.0, perp_lo, perp_hi,
                     0.0, SIDEWALK_TOP_Z, SIDEWALK_GREY,
                     dither_keep=SIDEWALK_DITHER_KEEP)


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
    )
    bake_atlas(
        out_png=HERE.parent / "road_040_hex.png",
        entries=[(ribi, lambda edges=edges: render_hex_cell(edges))
                 for ribi, edges in HEX_ENTRIES],
        cols_per_row=8,
    )


if __name__ == "__main__":
    bake_pakset()
