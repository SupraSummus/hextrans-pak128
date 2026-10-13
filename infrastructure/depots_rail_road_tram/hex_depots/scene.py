"""3D models of the pak128 road, rail, tram and monorail depots for the hex grid.

A depot stands on a dead end and faces its exit, one layout per hex
side like the terminal stops (see `infrastructure.road_stops.hex_terminals`):
a shed on the back half of the tile, gable and doors towards the exit,
which the way runs into.  `DEPOTS` lists each depot as a `DepotParams`.
The shed goes to `FrontImage` when it stands on the camera side of the
tile centre, so a vehicle on the yard behind it is hidden; the yard is
always `BackImage`.

    python3 -m infrastructure.depots_rail_road_tram.hex_depots.scene
    python3 -m infrastructure.depots_rail_road_tram.hex_depots.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from infrastructure.road_stops.hex_terminals.scene import (
    FACES, ROAD_050, apron, junction_preview, ribbed_shader)
from tools.threed.building_kit import (
    AMBIENT, Palette, bake_layers, facade, gabled_block, rewrite_images,
    set_layouts, speckle_shader, wall_quad)
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import Frame, add_block, add_roof
from tools.threed.way import edge_midpoint

DEPOTS_DIR = Path(__file__).resolve().parent.parent
RAIL_060 = DEPOTS_DIR.parent / "rail_tracks" / "rail_060_tracks.dat"
MONORAIL_DIR = DEPOTS_DIR.parent / "schwebebahn_all"

DOOR = (64, 58, 54)
PLANK = (84, 76, 70)
SETTS = (150, 146, 136)
HAZARD = ((232, 196, 40), (30, 30, 32))


@dataclass(frozen=True)
class DepotParams:
    name: str               # the .dat object
    png: str                # stem of the .dat and its legacy sheet
    pal: Palette
    back_s: float = -0.72   # back wall, along the exit's frame
    front_s: float = 0.1    # gable with the doors
    half_w: float = 0.42
    pitch: float = 0.28
    door_w: float = 0.19    # half width
    door_h: float = 0.29
    arched: bool = False
    hazard: bool = False    # open doorway between striped posts
    corrugated: bool = False  # sheet walls instead of brick
    lean_to: bool = False   # open shed along the left side
    setts: bool = False     # paved yard over the whole tile
    preview_way: Path = ROAD_050
    folder: Path = DEPOTS_DIR


DEPOTS = [
    DepotParams("CarDepot", "player-depot-road-128",
                Palette(wall=(150, 74, 54), trim=(206, 196, 176),
                        roof=(172, 96, 62)),
                setts=True),
    DepotParams("TrainDepot", "player-depot-rail_2-128",
                Palette(wall=(146, 62, 48), trim=(214, 200, 176),
                        roof=(104, 106, 112)),
                back_s=-0.76, front_s=0.16, half_w=0.44, pitch=0.24,
                door_w=0.2, door_h=0.3, arched=True, lean_to=True,
                preview_way=RAIL_060),
    DepotParams("TramDepot", "player-depot-tram_0-128",
                Palette(wall=(222, 208, 176), trim=(244, 238, 222),
                        roof=(184, 92, 56)),
                pitch=0.24, door_w=0.17, door_h=0.31, arched=True),
    # The suspended train hangs under a girder about 0.5 up.
    DepotParams("MonorailDepot", "ls-depot-monorail",
                Palette(wall=(142, 140, 148), trim=(176, 174, 182),
                        roof=(98, 94, 128)),
                back_s=-0.74, front_s=0.14, pitch=0.2, door_w=0.2,
                door_h=0.5, hazard=True, corrugated=True,
                folder=MONORAIL_DIR),
]


def shed_in_front(d: DepotParams, face: str) -> bool:
    """The shed is on the camera side of the tile centre."""
    return Frame(edge_midpoint(face)).world(d.back_s / 2, 0, 0)[1] < 0


def doors(model, fr: Frame, d: DepotParams):
    """Planked doors in the gable, in a lighter frame; an arched head
    is stacked from strips."""
    def opening(w, h, off, color):
        rect_h = h - w if d.arched else h
        wall_quad(model, fr, (d.front_s, -w), (d.front_s, w), 0.0, rect_h,
                  off, color, (-1, 0))
        if d.arched:
            n = 6
            for k in range(n):
                half = w * math.sqrt(1 - ((k + 0.5) / n) ** 2)
                wall_quad(model, fr, (d.front_s, -half), (d.front_s, half),
                          rect_h + w * k / n, rect_h + w * (k + 1) / n, off,
                          color, (-1, 0))

    opening(d.door_w + 0.03, d.door_h + 0.03, 0.008, d.pal.trim)
    opening(d.door_w, d.door_h, 0.012, DOOR)
    if d.hazard:
        for side in (-1, 1):
            p = side * (d.door_w + 0.02)
            add_block(model, fr, d.front_s, d.front_s + 0.04, p - 0.035,
                      p + 0.035, 0.0, d.door_h, HAZARD[0],
                      side_shader=hazard_shader)
        return
    plank_h = d.door_h - (d.door_w if d.arched else 0)
    for k in range(-3, 4):
        p = k * d.door_w / 3.5
        wall_quad(model, fr, (d.front_s, p - 0.004), (d.front_s, p + 0.004),
                  0.0, plank_h, 0.014, PLANK, (-1, 0))


def hazard_shader(wx, wy, sx, sy):
    """Yellow and black diagonal stripes."""
    rgb = np.where((((sx + sy) // 6) % 2 == 0)[:, None],
                   np.array(HAZARD[0], float), np.array(HAZARD[1], float))
    return rgb, np.ones(len(wx), bool)


def lantern(model, fr: Frame, d: DepotParams, z_ridge):
    """Glazed lantern along the ridge, as on a vehicle shed."""
    s0, s1 = d.back_s + 0.12, d.front_s - 0.12
    add_block(model, fr, s0, s1, -0.07, 0.07, z_ridge - 0.04, z_ridge + 0.05,
              d.pal.glass, side_color=d.pal.glass)
    for side in (-1, 1):
        add_roof(model, fr, s0 - 0.02, s1 + 0.02, side * 0.1, 0.0,
                 z_ridge + 0.04, z_ridge + 0.09, 0.015, d.pal.roof)


def lean_to(model, fr: Frame, d: DepotParams, z_eave):
    """Open shed on posts along the left wall, under a single slope."""
    p0, p1 = d.half_w, d.half_w + 0.17
    s0, s1 = d.back_s + 0.1, d.front_s - 0.08
    for s in np.linspace(s0 + 0.02, s1 - 0.02, 3):
        add_block(model, fr, s - 0.012, s + 0.012, p1 - 0.03, p1 - 0.006,
                  0.0, z_eave * 0.62, (92, 70, 52))
    add_roof(model, fr, s0, s1, p1, p0, z_eave * 0.6, z_eave * 0.82, 0.015,
             d.pal.roof)


def build(d: DepotParams, face: str, *, yard=True, shed=True) -> Model:
    model = Model()
    fr = Frame(edge_midpoint(face))
    if yard and d.setts:
        apron(model, speckle_shader(SETTS))
    if not shed:
        return model
    wall_shader = ribbed_shader(fr, d.pal.wall) if d.corrugated else None
    z_eave, z_ridge = gabled_block(model, fr, d.back_s, d.front_s, d.half_w,
                                   2, d.pal, pitch=d.pitch, stepped=False,
                                   bays=3, wall_shader=wall_shader)
    facade(model, fr, (d.back_s, d.half_w), (d.back_s, -d.half_w), (1, 0),
           d.pal, storeys=2, bays=3)
    lantern(model, fr, d, z_ridge)
    if d.lean_to:
        lean_to(model, fr, d, z_eave)
    doors(model, fr, d)
    # Lamp over the doors.
    add_block(model, fr, d.front_s, d.front_s + 0.05, -0.02, 0.02,
              d.door_h + 0.07, d.door_h + 0.09, (40, 40, 44))
    return model


def render_layers(d: DepotParams, face: str):
    camera = HexCamera(ambient=AMBIENT)
    if shed_in_front(d, face):
        return {"back": render(build(d, face, shed=False), camera),
                "front": render(build(d, face, yard=False), camera)}
    back = render(build(d, face), camera)
    return {"back": back, "front": np.zeros_like(back)}


def bake_pakset() -> None:
    for d in DEPOTS:
        lines = bake_layers([render_layers(d, face) for face in FACES],
                            d.folder / f"{d.png}_hex.png")
        dat = d.folder / f"{d.png}.dat"
        rewrite_images(dat, {d.name: lines})
        set_layouts(dat, len(FACES))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write each six times round a junction, one file "
                         "per depot suffixed with its name, instead of baking")
    a = ap.parse_args()
    if a.preview:
        for d in DEPOTS:
            junction_preview([lambda f, d=d: render_layers(d, f)],
                             a.preview.with_stem(f"{a.preview.stem}_{d.name}"),
                             d.preview_way)
    else:
        bake_pakset()
