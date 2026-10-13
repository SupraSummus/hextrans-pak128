"""3D models of the pak128 terminal road stops for the hex grid.

A terminal stands on a dead end and faces its exit.  The engine gives
it a layout per hex side when the .dat has six (layouts 0..5 face S,
SE, N, NW, NE, SW, as `ribi_t::layout_to_ribi`); with four it folds NE
and SW onto N and S.  `TERMINALS` lists the two pak128 terminals:

- `bus_terminus`: an asphalt apron with a raised platform round the
  three back edges, under glass canopies, with benches and a kiosk.
- `CarStop`: a concrete freight yard fenced on five sides, a loading
  dock round the back and a gatehouse with a raised barrier at the exit.

Each layout renders twice: parts on the camera side of the tile centre
go to `FrontImage` (drawn over vehicles), the rest to `BackImage`.

Writes `<png>_hex.png` (back/front for layouts 0..5) next to each
`.dat`, and rewrites its image lines and `Dims`.

    python3 -m infrastructure.road_stops.hex_terminals.scene
    python3 -m infrastructure.road_stops.hex_terminals.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from infrastructure.road_stops.hex_stops.scene import (
    COBBLE, CRATE, PLATFORM_SIDE, YELLOW, bench, cobble_shader, sign)
from tools.threed.building import composite, ground_cell
from tools.threed.building_kit import (
    add_beam, bake_layers, rewrite_images, set_layouts)
from tools.threed.hex_synth import HexGeom, hash_noise01
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import (
    Frame, add_block, add_frustum, add_prism, add_roof)
from tools.threed.way import edge_midpoint
from tools.threed.way_surface import APOTHEM
from tools.threed.way_preview import STEP, dat_cells

STOPS_DIR = Path(__file__).resolve().parent.parent
ROAD_050 = STOPS_DIR.parent / "roads" / "road_050.dat"

# Layout -> the hex edge the exit faces (ribi_t::layout_to_ribi).
FACES = ("S", "SE", "N", "NW", "NE", "SW")

ASPHALT = (78, 78, 82)
CONCRETE = (170, 168, 160)
FENCE = (84, 112, 160)
GLASS = (170, 200, 220)
STEEL = (225, 228, 232)


# --- Geometry -----------------------------------------------------------------

def edge_frames(face: str) -> list[Frame]:
    """One frame per hex edge, counted round from the exit (0) to the
    back (3): `p` points out through the edge, so `p = APOTHEM` is the
    edge itself, and `s` runs along it."""
    ex, ey = edge_midpoint(face)
    a0 = math.atan2(ey, ex)
    frames = []
    for k in range(6):
        a = a0 + k * math.pi / 3
        frames.append(Frame((math.sin(a), -math.cos(a))))
    return frames


def layer_at(fr: Frame, p: float) -> str:
    """Front when the frame's point `(0, p)` is on the camera side of
    the tile centre."""
    return "front" if fr.world(0, p, 0)[1] < -1e-6 else "back"


def band(p0: float, p1: float) -> list[tuple[float, float]]:
    """Strip along an edge between `p0` and `p1` from the centre, mitred
    to meet the strips of the neighbouring edges."""
    t0, t1 = p0 / math.sqrt(3), p1 / math.sqrt(3)
    return [(-t0, p0), (t0, p0), (t1, p1), (-t1, p1)]


def hexagon(r: float = 1.0) -> list[tuple[float, float]]:
    return [(r * math.cos(math.pi / 3 * k), r * math.sin(math.pi / 3 * k))
            for k in range(6)]


def apron(model, shader):
    """The whole hex, just above the way, so the dead end disappears
    under it."""
    pts = [(x, y, 0.003) for x, y in hexagon()]
    model.add_quad(pts[:4], (0, 0, 0), layer="back", shader=shader)
    model.add_quad([pts[0], pts[3], pts[4], pts[5]], (0, 0, 0),
                   layer="back", shader=shader)


# --- Shaders ------------------------------------------------------------------

def asphalt_shader(wx, wy, sx, sy):
    n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
    rgb = np.array(ASPHALT, float) * (0.9 + 0.18 * n)[:, None]
    return rgb, np.ones(len(wx), bool)


def slab_shader(fr: Frame, pitch=0.29):
    """Concrete slabs on a grid along the exit's frame."""
    base = np.array(CONCRETE, float)

    def shader(wx, wy, sx, sy):
        s, p = fr.local(wx, wy)
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (0.93 + 0.1 * n)[:, None]
        joint = ((s / pitch) % 1.0 < 0.05) | ((p / pitch) % 1.0 < 0.05)
        rgb[joint] *= 0.8
        return rgb, np.ones(len(wx), bool)

    return shader


def glass_shader(fr: Frame, pitch=0.12):
    """Panes between white ribs across the canopy."""
    base = np.array(GLASS, float)

    def shader(wx, wy, sx, sy):
        s = fr.local(wx, wy)[0]
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (1.0 + 0.1 * n)[:, None]
        rgb[np.abs((s / pitch) % 1.0 - 0.5) > 0.42] = STEEL
        return rgb, np.ones(len(wx), bool)

    return shader


def ribbed_shader(fr: Frame, base, pitch=0.035):
    """Corrugated sheet: light and dark ribs along `s`."""
    base = np.array(base, float)

    def shader(wx, wy, sx, sy):
        s = fr.local(wx, wy)[0]
        k = 0.88 + 0.16 * (np.abs((s / pitch) % 1.0 - 0.5) * 2)
        return base * k[:, None], np.ones(len(wx), bool)

    return shader


# --- Bus terminus -------------------------------------------------------------

PLATFORM_IN, PLATFORM_OUT, PLATFORM_Z = 0.56, APOTHEM - 0.01, 0.05


def bus_terminus(face: str) -> Model:
    model = Model()
    apron(model, asphalt_shader)
    frames = edge_frames(face)
    for k in (2, 3, 4):
        fr = frames[k]
        layer = layer_at(fr, PLATFORM_OUT)
        add_prism(model, fr, band(PLATFORM_IN, PLATFORM_OUT), 0.0,
                  PLATFORM_Z, COBBLE, layer,
                  top_shader=cobble_shader(PLATFORM_IN + 0.035, fr, 1),
                  side_color=PLATFORM_SIDE)
        # Yellow line along the kerb.
        t = PLATFORM_IN / math.sqrt(3)
        add_block(model, fr, -t + 0.03, t - 0.03, PLATFORM_IN - 0.06,
                  PLATFORM_IN - 0.035, 0.0, 0.006, YELLOW, layer)
        canopy(model, fr, layer)
        for s in (-0.16, 0.16):
            bench(model, fr, 1, layer, s, PLATFORM_OUT - 0.09)
    kiosk(model, frames[2], layer_at(frames[2], PLATFORM_OUT))
    sign(model, frames[4], 1, layer_at(frames[4], PLATFORM_OUT), s=-0.3,
         kerb=PLATFORM_IN)
    return model


def canopy(model, fr: Frame, layer):
    z0 = PLATFORM_Z
    p_in, p_out = PLATFORM_IN + 0.03, PLATFORM_OUT - 0.03
    for s in (-0.28, 0.28):
        add_block(model, fr, s - 0.012, s + 0.012, p_out - 0.024, p_out,
                  z0, z0 + 0.44, STEEL, layer)
    add_roof(model, fr, -0.36, 0.36, p_in - 0.04, p_out + 0.02,
             z0 + 0.4, z0 + 0.47, 0.015, GLASS, layer,
             shader=glass_shader(fr), side_color=STEEL)


def kiosk(model, fr: Frame, layer):
    """Ticket kiosk at the end of the platform nearest the exit."""
    s0, s1, p0, p1 = 0.12, 0.3, PLATFORM_IN + 0.09, PLATFORM_OUT - 0.04
    z0 = PLATFORM_Z
    add_block(model, fr, s0, s1, p0, p1, z0, z0 + 0.22, (120, 150, 200),
              layer)
    add_block(model, fr, s0 + 0.03, s1 - 0.03, p0 - 0.004, p0, z0 + 0.09,
              z0 + 0.18, (60, 56, 70), layer)
    add_block(model, fr, s0 - 0.02, s1 + 0.02, p0 - 0.03, p1 + 0.01,
              z0 + 0.22, z0 + 0.245, (84, 104, 140), layer)


# --- Freight yard -------------------------------------------------------------

DOCK_IN, DOCK_Z = 0.6, 0.11
FENCE_P, FENCE_H = APOTHEM - 0.03, 0.17


def freight_yard(face: str) -> Model:
    model = Model()
    frames = edge_frames(face)
    apron(model, slab_shader(frames[0]))
    for k in (2, 3, 4):
        fr = frames[k]
        layer = layer_at(fr, FENCE_P)
        add_prism(model, fr, band(DOCK_IN, FENCE_P - 0.012), 0.0, DOCK_Z,
                  CONCRETE, layer, side_color=(128, 126, 120))
        t = DOCK_IN / math.sqrt(3)
        add_block(model, fr, -t + 0.02, t - 0.02, DOCK_IN, DOCK_IN + 0.03,
                  DOCK_Z, DOCK_Z + 0.003, YELLOW, layer)
    for k in (1, 2, 3, 4, 5):
        fence(model, frames[k], layer_at(frames[k], FENCE_P),
              z0=0.0)
    crates(model, frames[2], layer_at(frames[2], FENCE_P), (-0.2, 0.05))
    crates(model, frames[3], layer_at(frames[3], FENCE_P), (-0.25, 0.15))
    barrels(model, frames[4], layer_at(frames[4], FENCE_P), (-0.1, 0.2))
    gate(model, frames)
    return model


def fence(model, fr: Frame, layer, z0):
    """Corrugated sheet fence along the whole edge, on posts."""
    t = FENCE_P / math.sqrt(3)
    add_block(model, fr, -t, t, FENCE_P - 0.012, FENCE_P, z0 + 0.01,
              z0 + FENCE_H, FENCE, layer,
              side_shader=ribbed_shader(fr, FENCE))
    for s in np.linspace(-t + 0.02, t - 0.02, 4):
        add_block(model, fr, s - 0.014, s + 0.014, FENCE_P - 0.03,
                  FENCE_P - 0.004, z0, z0 + FENCE_H + 0.02, (70, 74, 84),
                  layer)


def crates(model, fr: Frame, layer, at):
    for i, s in enumerate(at):
        p = DOCK_IN + 0.12 + 0.04 * i
        h = 0.08 + 0.02 * i
        add_block(model, fr, s - 0.06, s + 0.06, p - 0.06, p + 0.06,
                  DOCK_Z, DOCK_Z + h, CRATE, layer,
                  side_color=tuple(int(c * 0.85) for c in CRATE))


def barrels(model, fr: Frame, layer, at):
    for i, s in enumerate(at):
        add_frustum(model, fr, s, DOCK_IN + 0.13, 0.045, 0.045, DOCK_Z,
                    DOCK_Z + 0.11, (96, 70, 52), layer, n=10)


def gate(model, frames):
    """Gatehouse beside the exit, on the right going out, and a raised
    red and white barrier across the other side."""
    fr = frames[0]
    hut = Frame(fr.u, origin=fr.world(-0.38, 0.56, 0)[:2])
    layer = layer_at(hut, 0)
    add_block(model, hut, -0.08, 0.08, -0.07, 0.07, 0.0, 0.2,
              (232, 226, 210), layer)
    add_block(model, hut, -0.06, 0.06, 0.07, 0.074, 0.08, 0.16,
              (60, 56, 70), layer)
    add_block(model, hut, -0.1, 0.1, -0.09, 0.09, 0.2, 0.225, (90, 60, 50),
              layer)
    post = Frame(fr.u, origin=fr.world(0.36, 0.62, 0)[:2])
    layer = layer_at(post, 0)
    add_block(model, post, -0.02, 0.02, -0.02, 0.02, 0.0, 0.12,
              (220, 220, 220), layer)
    # The pole, raised steeply over the post, in red and white bands.
    a = np.array([*post.origin, 0.11])
    up = np.array([*fr.u, 0.0]) * -0.12 + np.array([0, 0, 0.48])
    for i in range(5):
        add_beam(model, a + up * i / 5, a + up * (i + 1) / 5, 0.022,
                 (200, 40, 40) if i % 2 == 0 else (240, 240, 236),
                 layer=layer)


# --- Bake ---------------------------------------------------------------------

@dataclass(frozen=True)
class Terminal:
    name: str           # the .dat object
    dat: str
    png: str
    build: Callable[[str], Model]


TERMINALS = [
    Terminal("bus_terminus", "terminus.dat", "terminus", bus_terminus),
    Terminal("CarStop", "player-loadbay-128.dat", "player-loadbay-128",
             freight_yard),
]


def render_layers(t: Terminal, face: str):
    model = t.build(face)
    return {layer: render(model, HexCamera(), layer_filter=layer)
            for layer in ("back", "front")}


def bake_pakset() -> None:
    for t in TERMINALS:
        lines = bake_layers([render_layers(t, face) for face in FACES],
                            STOPS_DIR / f"{t.png}_hex.png")
        rewrite_images(STOPS_DIR / t.dat, {t.name: lines})
        set_layouts(STOPS_DIR / t.dat, len(FACES))


def junction_preview(renders, out: Path, way_dat: Path = ROAD_050) -> None:
    """Each of `renders` (face -> {layer: cell}) six times round a 6-way
    junction, every one facing it, on the way of `way_dat`, side by side."""
    geom = HexGeom()
    stem = f"{way_dat.stem}_hex"
    road = Image.open(way_dat.with_name(f"{stem}.png")).convert("RGBA")
    cells = dat_cells(way_dat, stem)

    def road_cell(key):
        row, col = cells[key]
        return road.crop((col * geom.w, row * geom.h,
                          (col + 1) * geom.w, (row + 1) * geom.h))

    back = {v: k for k, v in STEP.items()}
    sheets = []
    for render_face in renders:
        tiles = {(0, 0): [np.asarray(road_cell("se_s_sw_nw_n_ne"))]}
        for dq, dr in STEP.values():
            face = back[(-dq, -dr)]
            im = road_cell(face)
            for layer in render_face(face.upper()).values():
                im.alpha_composite(Image.fromarray(layer))
            tiles[(dq, dr)] = [np.asarray(im)]
        sheets.append(composite(tiles, ground_cell(geom)))
    sheet = Image.new("RGBA", (sum(s.width for s in sheets),
                               max(s.height for s in sheets)))
    x = 0
    for s in sheets:
        sheet.alpha_composite(s, (x, 0))
        x += s.width
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write both round a junction here instead of baking")
    a = ap.parse_args()
    if a.preview:
        junction_preview([lambda f, t=t: render_layers(t, f)
                          for t in TERMINALS], a.preview)
    else:
        bake_pakset()
