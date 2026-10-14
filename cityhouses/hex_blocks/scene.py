"""The pak128 apartment blocks (`cityhouses/res/blocks`) for the hex grid.

504 residential blocks of the 1950s to 1980s, one `.dat` each, all
one tile with 8 layouts and a winter season.  Each becomes a
`tools.threed.city.Apartment`: its level sets the storeys, its
climates the palette (northern brick and render, or southern white
and ochre), and its name the rest (colours, footprint, balconies,
roof, a wing), so the family keeps its variety from bake to bake.

    python3 -m cityhouses.hex_blocks.scene
    python3 -m cityhouses.hex_blocks.scene --preview out.png [--count 24]
"""
from __future__ import annotations

import argparse
import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

from PIL import Image

from tools.threed.building import composite, ground_cell, render_tiles
from tools.threed.building_kit import AMBIENT
from tools.threed.city import (
    FACES, Apartment, apartment, bake_city, dat_fields, pick,
    rewrite_city_dat, seasons_of, unit)
from tools.threed.hex_synth import HexGeom

BLOCKS_DIR = Path(__file__).resolve().parent.parent / "res" / "blocks"

NORTH_WALLS = ((176, 170, 160), (150, 146, 140), (168, 92, 70),
               (190, 160, 110), (196, 184, 164), (140, 150, 140),
               (200, 120, 90))
SOUTH_WALLS = ((236, 230, 216), (230, 210, 170), (214, 170, 120),
               (238, 214, 200), (200, 186, 150), (226, 190, 140))
TRIMS = ((214, 210, 200), (190, 188, 184), (230, 226, 216), (120, 116, 112))
RAILS = ((190, 110, 60), (70, 120, 80), (120, 120, 124), (210, 200, 180),
         (150, 60, 50), (60, 90, 140), None)
STAIRS = ((150, 180, 200), (120, 160, 120), (200, 210, 210), (190, 120, 80))
ROOFS = ((96, 96, 100), (140, 70, 52), (110, 104, 100))


def params(dat: Path) -> Apartment:
    f = dat_fields(dat)
    name = f["name"]
    level = int(f.get("level", "20"))
    south = "desert" in f.get("climates", "") or \
        "tropic" in f.get("climates", "")
    storeys = max(3, min(12, 3 + level // 7
                         + pick(name, "storeys", (-1, 0, 1))))
    # A rectangle with half extents (S, P) is inside the hex while
    # S / 2 + P * sqrt(3) / 2 <= sqrt(3) / 2; balconies take 0.1 more.
    depth = 0.95 + 0.3 * unit(name, "depth")
    half = 1 - depth / 2 / math.sqrt(3) - 0.1 - 0.12 * unit(name, "width")
    hip = not south and storeys <= 6 and unit(name, "roof") < 0.4
    return Apartment(
        storeys=storeys,
        s0=-depth / 2, s1=depth / 2, w=half,
        wall=pick(name, "wall", SOUTH_WALLS if south else NORTH_WALLS),
        trim=pick(name, "trim", TRIMS),
        rail=pick(name, "rail", RAILS),
        stair=pick(name, "stair", STAIRS),
        roof="hip" if hip else "flat",
        roof_colour=pick(name, "roofc", ROOFS) if hip else (110, 110, 114),
        wing=0.0)


def bake_one(dat: Path) -> None:
    a = params(dat)
    seasons = seasons_of(dat)
    models = [[apartment(replace(a, snow=season == 1), face)
               for face in FACES] for season in range(seasons)]
    lines = bake_city(models, dat.with_name(f"{dat.stem}_hex.png"), 8)
    rewrite_city_dat(dat, lines)


def bake_pakset() -> None:
    # The workers find `bake_one` by its module's name: run as a script
    # (or by `tools.bake_all`), this module is a `__main__` they can't see.
    from cityhouses.hex_blocks.scene import bake_one
    dats = sorted(BLOCKS_DIR.glob("*.dat"))
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        list(pool.map(bake_one, dats, chunksize=8))
    print(f"baked {len(dats)} blocks")


def preview(out: Path, count: int) -> None:
    """The first `count` blocks round a 6-way junction of city road,
    each facing it, a winter copy below."""
    dats = sorted(BLOCKS_DIR.glob("*.dat"))[:count]
    grass = ground_cell(HexGeom())
    cells = []
    for snow in (False, True):
        for k, dat in enumerate(dats):
            a = replace(params(dat), snow=snow)
            face = FACES[k % 6]
            cells.append(composite(render_tiles(apartment(a, face), (1, 1),
                                                ambient=AMBIENT), grass))
    w = max(c.width for c in cells)
    h = max(c.height for c in cells)
    cols = 8
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGBA", (w * cols, h * rows))
    for k, c in enumerate(cells):
        sheet.alpha_composite(c, ((k % cols) * w,
                                  (k // cols) * h + h - c.height))
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write the first --count blocks, each facing a "
                         "side, here instead of baking")
    ap.add_argument("--count", type=int, default=16)
    a = ap.parse_args()
    if a.preview:
        preview(a.preview, a.count)
    else:
        bake_pakset()
