"""3D models of the pak128 air depots for the hex grid.

A hangar stands on a dead end and faces its exit, one layout per hex
side like the other depots (see `infrastructure.depots_rail_road_tram.
hex_depots`), but fills most of the tile, so it is cut on the plane
through the tile centre: the half on the camera side goes to
`FrontImage`, over an aircraft rolling in, the rest and the apron to
`BackImage`.

Every hangar is one cross-section, `HangarParams.profile`, swept from
the back wall to the doors.  `HANGARS` lists the five pak128 ones.

    python3 -m infrastructure.airport_depots.hex_hangars.scene
    python3 -m infrastructure.airport_depots.hex_hangars.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from infrastructure.road_stops.hex_terminals.scene import (
    FACES, apron, junction_preview, ribbed_shader, slab_shader)
from tools.threed.building_kit import (
    AMBIENT, Palette, bake_layers, cut_at_centre, gable, hall,
    rewrite_images, set_layouts, speckle_shader, vault, wall_quad)
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import Frame, add_block, add_roof
from tools.threed.way import edge_midpoint

HANGARS_DIR = Path(__file__).resolve().parent.parent

S0, S1 = -0.78, 0.5     # back wall and doors, along the exit's frame
W = 0.5                 # half width
INTERIOR = (40, 40, 44)
CHECKER = ((236, 236, 230), (36, 36, 40))


@dataclass(frozen=True)
class HangarParams:
    name: str                       # the .dat object
    png: str                        # stem of the .dat and its legacy sheet
    pal: Palette
    profile: list[tuple[float, float]]   # (p, z) across, wall to wall
    door_w: float                   # half width of the opening
    door_h: float
    roof_shader: Callable = None    # (frame, colour) -> shader
    windows: bool = False           # a band of windows along each side
    parapet: bool = False           # chequered, round a flat roof
    lantern: bool = False           # glazed, along the ridge
    skylights: bool = False         # on the vault, either side


HANGARS = [
    HangarParams("1920_AirDepot", "1920_airdepot",
                 Palette(wall=(96, 74, 52), trim=(150, 128, 92),
                         roof=(196, 178, 140), door=(84, 92, 52)),
                 gable(W, 0.2, 0.46), door_w=0.4, door_h=0.19),
    HangarParams("1930AirDepot", "1930airdepot",
                 Palette(wall=(150, 72, 50), trim=(70, 140, 128),
                         roof=(128, 132, 138)),
                 gable(W, 0.26, 0.48), door_w=0.38, door_h=0.24,
                 roof_shader=ribbed_shader, windows=True, lantern=True),
    HangarParams("1940AirDepot", "1940airdepot",
                 Palette(wall=(142, 144, 140), trim=(110, 112, 110),
                         roof=(150, 152, 148)),
                 vault(W, 0.0, 0.42), door_w=0.4, door_h=0.3,
                 roof_shader=ribbed_shader),
    HangarParams("1950AirDepot", "1950airdepot",
                 Palette(wall=(212, 206, 178), trim=(180, 176, 160),
                         roof=(110, 112, 120)),
                 [(-W, 0.32), (W, 0.32)], door_w=0.4, door_h=0.27,
                 parapet=True),
    HangarParams("1990AirDepot", "1990airdepot",
                 Palette(wall=(218, 204, 172), trim=(196, 184, 156),
                         roof=(54, 84, 150), door=(204, 112, 48)),
                 vault(W, 0.28, 0.18), door_w=0.42, door_h=0.26,
                 roof_shader=ribbed_shader, skylights=True),
]


def doors(model, fr: Frame, h: HangarParams):
    """The open doorway, framed, with the leaves pushed to either side."""
    def opening(w, ht, off, color):
        wall_quad(model, fr, (S1, -w), (S1, w), 0.0, ht, off, color, (-1, 0))

    opening(h.door_w + 0.025, h.door_h + 0.025, 0.006, h.pal.trim)
    opening(h.door_w, h.door_h, 0.01, INTERIOR)
    for side in (-1, 1):
        p = side * h.door_w
        wall_quad(model, fr, (S1, p - 0.07), (S1, p + 0.07), 0.0, h.door_h,
                  0.02, h.pal.door, (-1, 0))


def windows(model, fr: Frame, h: HangarParams):
    """A band along each side wall."""
    eave = h.profile[0][1]
    for side in (-1, 1):
        for s in np.linspace(S0 + 0.12, S1 - 0.12, 5):
            wall_quad(model, fr, (s - 0.05, side * W), (s + 0.05, side * W),
                      eave * 0.55, eave * 0.85, 0.006, h.pal.glass, (0, -side))


def parapet(model, fr: Frame, h: HangarParams):
    """Black and white blocks round the flat roof."""
    z = h.profile[0][1]
    edges = [((S0, -W), (S1, -W)), ((S1, -W), (S1, W)),
             ((S1, W), (S0, W)), ((S0, W), (S0, -W))]
    for (a_s, a_p), (b_s, b_p) in edges:
        n = max(2, round(math.dist((a_s, a_p), (b_s, b_p)) / 0.07))
        for k in range(n):
            s0 = a_s + (b_s - a_s) * k / n
            s1 = a_s + (b_s - a_s) * (k + 1) / n
            p0 = a_p + (b_p - a_p) * k / n
            p1 = a_p + (b_p - a_p) * (k + 1) / n
            add_block(model, fr, min(s0, s1) - 0.02, max(s0, s1) + 0.02,
                      min(p0, p1) - 0.02, max(p0, p1) + 0.02, z, z + 0.05,
                      CHECKER[k % 2])
    # Plant room on the roof.
    add_block(model, fr, S0 + 0.25, S1 - 0.35, -0.2, 0.2, z, z + 0.08,
              h.pal.wall, side_shader=speckle_shader(h.pal.wall))
    add_roof(model, fr, S0 + 0.23, S1 - 0.33, -0.22, 0.22, z + 0.08,
             z + 0.08, 0.02, (84, 132, 84))


def lantern(model, fr: Frame, h: HangarParams):
    ridge = max(z for _, z in h.profile)
    s0, s1 = S0 + 0.15, S1 - 0.15
    add_block(model, fr, s0, s1, -0.08, 0.08, ridge - 0.03, ridge + 0.05,
              h.pal.glass, side_color=h.pal.glass)
    for side in (-1, 1):
        add_roof(model, fr, s0 - 0.02, s1 + 0.02, side * 0.11, 0.0,
                 ridge + 0.04, ridge + 0.09, 0.015, h.pal.roof)


def skylights(model, fr: Frame, h: HangarParams):
    """Glazed panes on the vault, a third of the way up either side."""
    k = len(h.profile) // 3
    for (p0, z0), (p1, z1) in (h.profile[k:k + 2], h.profile[-k - 2:-k]):
        for s in np.linspace(S0 + 0.12, S1 - 0.12, 5):
            add_roof(model, fr, s - 0.04, s + 0.04, p0, p1, z0 + 0.026,
                     z1 + 0.026, 0.004, (200, 220, 236))


def build(h: HangarParams, face: str) -> Model:
    model = Model()
    fr = Frame(edge_midpoint(face))
    hall(model, fr, S0, S1, h.profile, h.pal,
         roof_shader=h.roof_shader and h.roof_shader(fr, h.pal.roof))
    doors(model, fr, h)
    if h.windows:
        windows(model, fr, h)
    if h.parapet:
        parapet(model, fr, h)
    if h.lantern:
        lantern(model, fr, h)
    if h.skylights:
        skylights(model, fr, h)
    return model


def render_layers(h: HangarParams, face: str):
    camera = HexCamera(ambient=AMBIENT)
    floor = Model()
    apron(floor, slab_shader(Frame(edge_midpoint(face))))
    layers = cut_at_centre(build(h, face), camera)
    back = layers["back"]
    layers["back"] = np.where(back[..., 3:] > 0, back, render(floor, camera))
    return layers


def bake_pakset() -> None:
    for h in HANGARS:
        lines = bake_layers([render_layers(h, face) for face in FACES],
                            HANGARS_DIR / f"{h.png}_hex.png")
        dat = HANGARS_DIR / f"{h.png}.dat"
        rewrite_images(dat, {h.name: lines})
        set_layouts(dat, len(FACES))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write all five six times round a junction "
                         "instead of baking")
    a = ap.parse_args()
    if a.preview:
        junction_preview([lambda f, h=h: render_layers(h, f)
                          for h in HANGARS], a.preview)
    else:
        bake_pakset()
