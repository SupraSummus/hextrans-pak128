"""3D models of the pak128 through depots for the hex grid.

A through depot stands on a straight way, open at both ends, with one
layout per hex axis (`Dims=1,1,3`: layouts 0, 1, 2 along the way from
S, SE and SW).  It stands across the tile centre, so it is cut there
like the hangars (`building_kit.cut_at_centre`).  `DEPOTS` lists the
1936 iron and glass train shed; the ship depot is a boat shed in
`infrastructure.water_all.hex_water`.

    python3 -m infrastructure.depots_rail_road_tram.hex_through_depots.scene
    python3 -m infrastructure.depots_rail_road_tram.hex_through_depots.scene \
        --preview out.png
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from infrastructure.depots_rail_road_tram.hex_depots.scene import RAIL_060
from infrastructure.road_stops.hex_terminals.scene import (
    glass_shader, junction_preview, ribbed_shader)
from tools.threed.building_kit import (
    AMBIENT, Palette, bake_layers, cut_at_centre, gable, hall,
    rewrite_images, set_layouts, wall_quad)
from tools.threed.render import HexCamera, Model
from tools.threed.solids import Frame, add_roof
from tools.threed.way import edge_midpoint

DEPOTS_DIR = Path(__file__).resolve().parent.parent

# Layout -> the hex edge the way comes in from.
AXES = ("S", "SE", "SW")
S1 = 0.8                # either end, along the way
INTERIOR = (40, 40, 44)


@dataclass(frozen=True)
class ThroughParams:
    name: str               # the .dat object
    png: str                # stem of the .dat and its legacy sheet
    pal: Palette
    profile: list[tuple[float, float]]   # (p, z) across, wall to wall
    door_w: float           # half width of each end's opening
    door_h: float
    preview_way: Path


DEPOTS = [
    ThroughParams("Depot_train_1936", "depot_train_1936",
                  Palette(wall=(118, 60, 46), trim=(196, 190, 178),
                          roof=(150, 152, 150), glass=(120, 150, 168)),
                  gable(0.42, 0.3, 0.5), door_w=0.17, door_h=0.3,
                  preview_way=RAIL_060),
]


def openings(model, fr: Frame, d: ThroughParams):
    """A framed opening in each end wall."""
    for s, inward in ((-S1, (1, 0)), (S1, (-1, 0))):
        for w, h, off, color in ((d.door_w + 0.025, d.door_h + 0.025, 0.006,
                                  d.pal.trim),
                                 (d.door_w, d.door_h, 0.01, INTERIOR)):
            wall_quad(model, fr, (s, -w), (s, w), 0.0, h, off, color, inward)


def glazing(model, fr: Frame, d: ThroughParams, z0):
    """Glass between iron mullions along both side walls."""
    w, eave = d.profile[-1]
    n = 8
    for side in (-1, 1):
        wall_quad(model, fr, (-S1 + 0.04, side * w), (S1 - 0.04, side * w),
                  z0, eave - 0.04, 0.006, d.pal.glass, (0, -side))
        for s in np.linspace(-S1 + 0.04, S1 - 0.04, n + 1):
            wall_quad(model, fr, (s - 0.008, side * w), (s + 0.008, side * w),
                      z0, eave - 0.04, 0.01, d.pal.wall, (0, -side))


def skylight(model, fr: Frame, d: ThroughParams):
    """A glazed strip either side of the ridge."""
    ridge = max(z for _, z in d.profile)
    w, eave = d.profile[-1]
    for side in (-1, 1):
        p0, p1 = side * 0.04, side * 0.16
        z0 = ridge - (ridge - eave) * 0.04 / w
        z1 = ridge - (ridge - eave) * 0.16 / w
        add_roof(model, fr, -S1 + 0.08, S1 - 0.08, p0, p1, z0 + 0.026,
                 z1 + 0.026, 0.004, d.pal.glass, shader=glass_shader(fr))


def build(d: ThroughParams, axis: str) -> Model:
    model = Model()
    fr = Frame(edge_midpoint(axis))
    hall(model, fr, -S1, S1, d.profile, d.pal,
         roof_shader=ribbed_shader(fr, d.pal.roof))
    openings(model, fr, d)
    glazing(model, fr, d, 0.08)
    skylight(model, fr, d)
    return model


def render_layers(d: ThroughParams, axis: str):
    return cut_at_centre(build(d, axis), HexCamera(ambient=AMBIENT))


def bake_pakset() -> None:
    for d in DEPOTS:
        lines = bake_layers([render_layers(d, axis) for axis in AXES],
                            DEPOTS_DIR / f"{d.png}_hex.png")
        dat = DEPOTS_DIR / f"{d.png}.dat"
        rewrite_images(dat, {d.name: lines})
        set_layouts(dat, len(AXES))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write each on the six legs of a junction, one "
                         "file per depot suffixed with its name, instead "
                         "of baking")
    a = ap.parse_args()
    if a.preview:
        opposite = {"N": "S", "NW": "SE", "NE": "SW"}
        for d in DEPOTS:
            junction_preview(
                [lambda f, d=d: render_layers(d, opposite.get(f, f))],
                a.preview.with_stem(f"{a.preview.stem}_{d.name}"),
                d.preview_way)
    else:
        bake_pakset()
