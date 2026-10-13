"""3D models of the pak128 one-tile townhalls for the hex grid.

`02_CITYdesert` (red brick under a spired corner tower) and
`01_CITYrmax` (orange brick, a hipped green roof, a white portico) are
1x1.  The engine founds a 1x1 townhall facing any of the six hex
sides and seeds its road there (`stadt_t::check_bau_townhall`), so
each gets a layout per side (`Dims=1,1,6`, layouts 0..5 facing S, SE,
N, NW, NE, SW like the terminals): the entrance on the road side, a
paved apron in front of it.

    python3 -m special_buildings.townhalls.hex_small.scene
    python3 -m special_buildings.townhalls.hex_small.scene --preview out.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from infrastructure.road_stops.hex_terminals.scene import FACES
from tools.threed.building import composite, ground_cell, render_tiles
from tools.threed.building_kit import (
    AMBIENT, STOREY, Palette, bake_rotations, facade, gabled_block,
    rewrite_images, set_layouts, speckle_shader)
from tools.threed.factory_kit import ground_shader
from tools.threed.hex_synth import HexGeom
from tools.threed.render import Model
from tools.threed.solids import Frame, add_block, add_face, add_frustum
from tools.threed.way import edge_midpoint

TOWNHALLS_DIR = Path(__file__).resolve().parent.parent

RED_BRICK = Palette(wall=(158, 62, 48), trim=(222, 206, 176),
                    roof=(84, 64, 70), glass=(50, 60, 80))
ORANGE_BRICK = Palette(wall=(214, 128, 70), trim=(244, 238, 222),
                       roof=(62, 110, 76), glass=(56, 70, 92))
PAVING = (186, 178, 160)
LAWN = (98, 142, 64)
STONE = (210, 206, 196)


def apron(model, fr: Frame):
    """Paving over the tile, a lawn on the far half."""
    model_q = [fr.world(s, p, 0.003) for s, p in
               ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    shader = ground_shader(PAVING, patches=[(fr, -0.55, 0.0, 0.45, LAWN)])
    add_face(model, model_q, (0, 0, 0), outward=fr.world(0, 0, -1),
             shader=shader)


def steps(model, fr: Frame, s, w):
    for k in range(3):
        add_block(model, fr, s, s + 0.12 - 0.035 * k, -w, w, 0,
                  0.02 * (k + 1), STONE)


def hip_roof(model, fr: Frame, s0, s1, w, z, rise, color):
    """Four slopes up to a short ridge along `s`."""
    o = 0.04
    a, b = s0 - o, s1 + o
    r0, r1 = s0 + w, s1 - w
    eave = [fr.world(a, -w - o, z), fr.world(b, -w - o, z),
            fr.world(b, w + o, z), fr.world(a, w + o, z)]
    ridge = [fr.world(r0, 0, z + rise), fr.world(r1, 0, z + rise)]
    inside = fr.world((s0 + s1) / 2, 0, z)
    add_face(model, [eave[0], eave[1], ridge[1], ridge[0]], color,
             outward=inside, shader=speckle_shader(color))
    add_face(model, [eave[2], eave[3], ridge[0], ridge[1]], color,
             outward=inside, shader=speckle_shader(color))
    add_face(model, [eave[1], eave[2], ridge[1]], color, outward=inside,
             shader=speckle_shader(color))
    add_face(model, [eave[3], eave[0], ridge[0]], color, outward=inside,
             shader=speckle_shader(color))


def desert(face: str) -> Model:
    """Red brick, two storeys, a corner tower with a spire."""
    model = Model()
    fr = Frame(edge_midpoint(face))
    apron(model, fr)
    s0, s1, w = -0.62, 0.2, 0.36
    gabled_block(model, fr, s0, s1, w, 2, RED_BRICK, pitch=0.3, door=True,
                 stepped=False, bays=3)
    facade(model, fr, (s0, w), (s0, -w), (1, 0), RED_BRICK, storeys=2,
           bays=3)
    # Tower on the front corner, a belfry and a spire.
    ts, tp, tw = s1 - 0.05, -w + 0.02, 0.13
    top = 3 * STOREY + 0.06
    add_block(model, fr, ts - tw, ts + tw, tp - tw, tp + tw, 0.0, top,
              RED_BRICK.wall, side_shader=speckle_shader(RED_BRICK.wall))
    facade(model, fr, (ts + tw, tp - tw), (ts + tw, tp + tw), (-1, 0),
           RED_BRICK, storeys=3, bays=1)
    add_block(model, fr, ts - tw - 0.02, ts + tw + 0.02, tp - tw - 0.02,
              tp + tw + 0.02, top, top + 0.03, RED_BRICK.trim)
    add_frustum(model, fr, ts, tp, tw * 1.3, 0.0, top + 0.03, top + 0.42,
                RED_BRICK.roof, n=4, side_shader=speckle_shader(
                    RED_BRICK.roof))
    steps(model, fr, s1, 0.12)
    return model


def rmax(face: str) -> Model:
    """Orange brick under a hipped roof, a portico on four columns."""
    model = Model()
    fr = Frame(edge_midpoint(face))
    apron(model, fr)
    s0, s1, w = -0.6, 0.22, 0.42
    eave = 2 * STOREY + 0.04
    add_block(model, fr, s0, s1, -w, w, 0.0, eave, ORANGE_BRICK.wall,
              side_shader=speckle_shader(ORANGE_BRICK.wall))
    add_block(model, fr, s0 - 0.015, s1 + 0.015, -w - 0.015, w + 0.015,
              eave - 0.04, eave, ORANGE_BRICK.trim)
    for side in (-1, 1):
        facade(model, fr, (s0, side * w), (s1, side * w), (0, -side),
               ORANGE_BRICK, storeys=2, bays=3)
    facade(model, fr, (s1, -w), (s1, w), (-1, 0), ORANGE_BRICK, storeys=2,
           bays=4, door=True)
    facade(model, fr, (s0, w), (s0, -w), (1, 0), ORANGE_BRICK, storeys=2,
           bays=4)
    hip_roof(model, fr, s0, s1, w, eave, 0.24, ORANGE_BRICK.roof)
    # Portico: four columns, an entablature and a pediment.
    ps, pw, ph = s1 + 0.16, 0.2, 2 * STOREY - 0.02
    for p in np.linspace(-pw, pw, 4):
        add_frustum(model, fr, ps, p, 0.022, 0.02, 0.04, ph, STONE, n=8)
    add_block(model, fr, s1, ps + 0.03, -pw - 0.04, pw + 0.04, 0.0, 0.04,
              STONE)
    add_block(model, fr, s1, ps + 0.03, -pw - 0.04, pw + 0.04, ph,
              ph + 0.05, ORANGE_BRICK.trim)
    add_face(model, [fr.world(ps + 0.03, -pw - 0.04, ph + 0.05),
                     fr.world(ps + 0.03, pw + 0.04, ph + 0.05),
                     fr.world(ps + 0.03, 0.0, ph + 0.17)],
             ORANGE_BRICK.trim, outward=fr.world(s1, 0, ph))
    for side in (-1, 1):
        add_face(model, [fr.world(s1, side * (pw + 0.04), ph + 0.05),
                         fr.world(ps + 0.03, side * (pw + 0.04), ph + 0.05),
                         fr.world(ps + 0.03, 0.0, ph + 0.17),
                         fr.world(s1, 0.0, ph + 0.17)],
                 ORANGE_BRICK.roof, outward=fr.world(s1, 0, ph))
    steps(model, fr, ps + 0.03, pw)
    return model


TOWNHALLS = {
    "02_CITYdesert": ("desert-townhall.dat", "desert_townhall_hex.png", desert),
    "01_CITYrmax": ("rmax-townhall.dat", "rmax_townhall_hex.png", rmax),
}


def bake_pakset() -> None:
    for name, (dat, png, build) in TOWNHALLS.items():
        lines = bake_rotations([build(face) for face in FACES],
                               TOWNHALLS_DIR / png)
        rewrite_images(TOWNHALLS_DIR / dat, {name: lines})
        set_layouts(TOWNHALLS_DIR / dat, len(FACES))


def preview(out: Path) -> None:
    """Every layout of each townhall side by side on grass."""
    from PIL import Image
    grass = ground_cell(HexGeom())
    rows = []
    for _, _, build in TOWNHALLS.values():
        cells = [composite(render_tiles(build(f), (1, 1), ambient=AMBIENT),
                           grass) for f in FACES]
        row = Image.new("RGBA", (sum(c.width for c in cells),
                                 max(c.height for c in cells)))
        x = 0
        for c in cells:
            row.alpha_composite(c, (x, row.height - c.height))
            x += c.width
        rows.append(row)
    sheet = Image.new("RGBA", (max(r.width for r in rows),
                               sum(r.height for r in rows)))
    y = 0
    for r in rows:
        sheet.alpha_composite(r, (0, y))
        y += r.height
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write every layout on grass here instead of baking")
    a = ap.parse_args()
    if a.preview:
        preview(a.preview)
    else:
        bake_pakset()
