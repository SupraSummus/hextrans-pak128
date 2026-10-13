"""3D models of the pak128 parking extensions for the hex grid.

A parking extension is a through stop: a parking lane along each side
of the road, bays marked across it, cars of its era parked along the
road, a lamp and a P sign.  It shares the axes, layouts and lane
outline of `infrastructure.road_stops.hex_stops`; `ERAS` lists the
three pak128 ones, which share `parking.dat`.

Writes `parking_hex.png` (per era a row per axis: back/front for its
four end cases; an open end stops the lane short) and rewrites the
image lines of each building in `parking.dat`.

    python3 -m infrastructure.road_stops.hex_parking.scene
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from infrastructure.road_stops.hex_stops.scene import (
    AXES, LAYOUTS, PLATFORM_IN, PLATFORM_OUT, POST, STOPS_DIR, edge_frame,
    platform_poly)
from infrastructure.road_stops.hex_terminals.scene import junction_preview
from tools.threed.bespoke import bake_atlas
from tools.threed.building_kit import rewrite_images, set_layouts
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import Frame, add_block, add_prism

LANE = (84, 84, 88)
LINE = (226, 226, 220)
SIGN_BLUE = (36, 70, 170)
GLASS = (70, 86, 104)
TYRE = (30, 30, 32)


@dataclass(frozen=True)
class CarStyle:
    length: float
    width: float
    body_h: float           # sill to waistline
    cabin: tuple[float, float, float]   # start, end along the car, height
    fenders: bool = False   # separate wings over the wheels


@dataclass(frozen=True)
class Era:
    name: str               # the .dat object
    car: CarStyle
    colours: tuple[tuple[int, int, int], ...]
    bays: tuple[float, ...]  # car centres along the road, either side


ERAS = [
    Era("parking_(catchemnt_area_ext)1",
        CarStyle(0.2, 0.09, 0.035, (-0.06, 0.05, 0.045), fenders=True),
        ((52, 82, 56), (186, 160, 104), (40, 38, 36), (200, 130, 40)),
        (-0.34, 0.12)),
    Era("parking_(catchemnt_area_ext)2",
        CarStyle(0.24, 0.1, 0.03, (-0.07, 0.06, 0.032)),
        ((40, 90, 190), (200, 190, 150), (150, 150, 160), (60, 150, 210)),
        (-0.3, 0.02, 0.32)),
    Era("parking_(catchemnt_area_ext)3",
        CarStyle(0.19, 0.1, 0.035, (-0.07, 0.05, 0.035)),
        ((190, 40, 40), (230, 230, 226), (110, 140, 190), (220, 200, 60),
         (90, 120, 70)),
        (-0.36, -0.12, 0.12, 0.36)),
]

LANE_Z = 0.006


def lane_shader(fr: Frame, side: int, bays):
    """Asphalt with white lines between the bays and along the kerb."""
    base = np.array(LANE, float)
    line = np.array(LINE, float)
    pitch = bays[1] - bays[0]
    ends = [bays[0] - pitch / 2] + [b + pitch / 2 for b in bays]

    def shader(wx, wy, sx, sy):
        s, p = fr.local(wx, wy)
        p = p * side
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (0.92 + 0.14 * n)[:, None]
        mark = np.zeros(len(wx), bool)
        for e in ends:
            mark |= np.abs(s - e) < 0.008
        mark &= p > PLATFORM_IN + 0.02
        mark |= np.abs(p - (PLATFORM_IN + 0.012)) < 0.006
        rgb[mark] = line
        return rgb, np.ones(len(wx), bool)

    return shader


def car(model, fr: Frame, s, p, style: CarStyle, colour, layer):
    """A car parked along the road, centred on `(s, p)`."""
    half_l, half_w = style.length / 2, style.width / 2
    z0, z1 = 0.016, 0.016 + style.body_h
    dark = tuple(int(c * 0.7) for c in colour)
    for ds in (-half_l * 0.62, half_l * 0.62):
        add_block(model, fr, s + ds - 0.022, s + ds + 0.022, p - half_w,
                  p + half_w, LANE_Z, z0 + 0.01, TYRE, layer)
    if style.fenders:
        # Narrow body between wings, the wings over the wheels.
        add_block(model, fr, s - half_l, s + half_l, p - half_w * 0.7,
                  p + half_w * 0.7, z0, z1, colour, layer, side_color=dark)
        for ds in (-half_l * 0.62, half_l * 0.62):
            add_block(model, fr, s + ds - 0.035, s + ds + 0.035, p - half_w,
                      p + half_w, z0 + 0.008, z0 + 0.03, dark, layer)
    else:
        add_block(model, fr, s - half_l, s + half_l, p - half_w, p + half_w,
                  z0, z1, colour, layer, side_color=dark)
    c0, c1, ch = style.cabin
    inset = 0.012
    add_block(model, fr, s + c0, s + c1, p - half_w + inset,
              p + half_w - inset, z1, z1 + ch, GLASS, layer)
    add_block(model, fr, s + c0 - 0.005, s + c1 + 0.005,
              p - half_w + inset - 0.003, p + half_w - inset + 0.003,
              z1 + ch, z1 + ch + 0.008, colour, layer)


def lamp(model, fr: Frame, s, p, layer):
    add_block(model, fr, s - 0.01, s + 0.01, p - 0.01, p + 0.01,
              LANE_Z, 0.5, POST, layer)
    add_block(model, fr, s - 0.04, s + 0.04, p - 0.025, p + 0.025,
              0.48, 0.51, (200, 200, 190), layer)


def p_sign(model, fr: Frame, s, p, layer):
    add_block(model, fr, s - 0.01, s + 0.01, p - 0.01, p + 0.01,
              LANE_Z, 0.32, POST, layer)
    add_block(model, fr, s - 0.045, s + 0.045, p - 0.01, p + 0.01,
              0.22, 0.34, SIGN_BLUE, layer)
    # The P: a white stem and bowl on the plate's face.
    for p_off in (-0.012, 0.012):
        add_block(model, fr, s - 0.022, s - 0.008, p + p_off - 0.002,
                  p + p_off + 0.002, 0.24, 0.32, LINE, layer)
        add_block(model, fr, s - 0.008, s + 0.02, p + p_off - 0.002,
                  p + p_off + 0.002, 0.285, 0.32, LINE, layer)


def build(era: Era, layout: int) -> Model:
    ends = layout & 3
    fr = edge_frame(AXES[layout // 4])
    model = Model()
    front = fr.front_sign()
    for k, side in enumerate((+1, -1)):
        layer = "front" if side == front else "back"
        add_prism(model, fr, platform_poly(side, ends), 0.0, LANE_Z, LANE,
                  layer,
                  top_shader=lane_shader(fr, side, era.bays),
                  side_color=(64, 64, 66))
        p = side * (PLATFORM_IN + PLATFORM_OUT) / 2
        for i, s in enumerate(era.bays):
            colour = era.colours[(i + 2 * k) % len(era.colours)]
            car(model, fr, s, p, era.car, colour, layer)
        edge = side * (PLATFORM_OUT - 0.02)
        if side == (-front if front else -1):
            lamp(model, fr, 0.0 if len(era.bays) % 2 == 0 else -0.16,
                 edge, layer)
        else:
            p_sign(model, fr, 0.5, edge, layer)
    return model


def render_layer(era: Era, layout: int, layer: str):
    return render(build(era, layout), HexCamera(), layer_filter=layer)


def dat_lines(era_row: int) -> list[str]:
    """Image lines of the era whose axes start at atlas row `era_row`."""
    lines = []
    for layout in range(LAYOUTS):
        row, col = era_row + layout // 4, (layout % 4) * 2
        for i, key in enumerate(("Back", "Front")):
            lines.append(f"{key}Image[{layout}][0][0][0][0]="
                         f"parking_hex.{row}.{col + i}")
    return lines


def bake_pakset() -> None:
    entries = [(f"{era.name} {layer}[{layout}]",
                lambda e=era, lo=layout, la=layer: render_layer(e, lo, la))
               for era in ERAS for layout in range(LAYOUTS)
               for layer in ("back", "front")]
    bake_atlas(out_png=STOPS_DIR / "parking_hex.png", entries=entries,
               cols_per_row=8)
    rewrite_images(STOPS_DIR / "parking.dat",
                   {era.name: dat_lines(len(AXES) * k)
                    for k, era in enumerate(ERAS)})
    set_layouts(STOPS_DIR / "parking.dat", LAYOUTS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write each era on the six legs of a junction, "
                         "side by side, instead of baking")
    a = ap.parse_args()
    if a.preview:
        layout = {"N": 3, "S": 3, "NW": 7, "SE": 7, "NE": 11, "SW": 11}
        junction_preview(
            [lambda f, e=e: {la: render_layer(e, layout[f], la)
                             for la in ("back", "front")} for e in ERAS],
            a.preview)
    else:
        bake_pakset()
