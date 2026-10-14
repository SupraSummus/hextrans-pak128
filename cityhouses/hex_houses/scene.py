"""The pak128 houses (`cityhouses/res`, `res/no-winter`, `res/pioneer`)
for the hex grid.

352 residential buildings, one `.dat` each, from cottages to towers.
Their level tells their size: below 12 a house in a garden, below 25
a town house of two to four storeys, from 25 an apartment block
(`tools.threed.city.Apartment`, as `hex_blocks` bakes).  Their year
picks the period (half-timbering and steep roofs before 1920,
dormers and hips to 1950, flat roofs and plain walls after) and their
climates the palette; a hash of the name does the rest.

    python3 -m cityhouses.hex_houses.scene
    python3 -m cityhouses.hex_houses.scene --preview out.png [--count 24]
"""
from __future__ import annotations

import argparse
import math
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

from PIL import Image

from tools.threed.building import composite, ground_cell, render_tiles
from tools.threed.building_kit import AMBIENT
from tools.threed.city import (
    FACES, Apartment, House, apartment, bake_city, city_buildings, house,
    pick, rewrite_city_building, unit)
from tools.threed.hex_synth import HexGeom

CITY_DIR = Path(__file__).resolve().parent.parent
DIRS = [CITY_DIR / "res", CITY_DIR / "res" / "no-winter",
        CITY_DIR / "res" / "pioneer"]

NORTH_OLD = ((168, 80, 60), (226, 214, 186), (196, 176, 140), (150, 66, 50))
NORTH_NEW = ((232, 230, 222), (214, 204, 170), (176, 176, 170),
             (196, 120, 90), (220, 200, 150))
SOUTH = ((240, 234, 220), (232, 206, 160), (226, 180, 130), (240, 216, 206))
ROOFS_NORTH = ((150, 70, 52), (84, 80, 86), (120, 60, 46), (96, 90, 84))
ROOFS_SOUTH = ((186, 96, 60), (198, 110, 70))
TRIMS = ((236, 232, 222), (200, 196, 186), (120, 110, 100))


def year_of(f) -> int:
    return int(re.sub(r"\D", "", f.get("intro_year", "1950")) or 1950)


def params(f: dict[str, str]):
    name, level, year = f["name"], int(f.get("level", "5")), year_of(f)
    climates = f.get("climates", "")
    south = "desert" in climates or "tropic" in climates
    if level >= 25:
        storeys = max(5, min(12, 3 + level // 6))
        depth = 0.95 + 0.3 * unit(name, "depth")
        return Apartment(
            storeys=storeys, s0=-depth / 2, s1=depth / 2,
            w=1 - depth / 2 / math.sqrt(3) - 0.1 - 0.12 * unit(name, "w"),
            wall=pick(name, "wall", SOUTH if south else NORTH_NEW),
            trim=pick(name, "trim", TRIMS),
            rail=pick(name, "rail", ((120, 120, 124), (150, 60, 50), None)),
            stair=pick(name, "stair", ((150, 180, 200), (200, 210, 210))))
    old, modern = year < 1920, year >= 1950
    town = level >= 12
    if town:
        storeys = 2 + min(2, (level - 12) // 5)
        depth = 0.75 + 0.25 * unit(name, "depth")
        half = 0.42 + 0.12 * unit(name, "w")
        s1 = 0.25
    else:
        storeys = 1 + (unit(name, "storeys") < (0.3 if modern else 0.6))
        depth = 0.5 + 0.2 * unit(name, "depth")
        half = 0.32 + 0.16 * unit(name, "w")
        s1 = 0.05 + 0.15 * unit(name, "set")
    if south:
        roof = pick(name, "roof", ("flat", "hip", "flat"))
        wall = pick(name, "wall", SOUTH)
        roof_colour = pick(name, "roofc", ROOFS_SOUTH)
    else:
        roof = "flat" if modern and unit(name, "flat") < 0.4 else \
            pick(name, "roof", ("gable", "gable", "hip"))
        wall = pick(name, "wall", NORTH_OLD if not modern else NORTH_NEW)
        roof_colour = pick(name, "roofc", ROOFS_NORTH)
    return House(
        storeys=storeys, s0=s1 - depth, s1=s1, w=half, wall=wall,
        trim=pick(name, "trim", TRIMS), roof_colour=roof_colour, roof=roof,
        pitch=(0.34 if old else 0.24) * (1 + 0.5 * (half - 0.3)),
        garden=not town or unit(name, "garden") < 0.3,
        timber=old and not south and not town and unit(name, "timber") < 0.4,
        dormers=not modern and roof == "gable" and town,
        porch=not town and unit(name, "porch") < 0.5,
        trees=1 + int(3 * unit(name, "trees")) if not town else 1,
        seed=name)


def build(p, face):
    return apartment(p, face) if isinstance(p, Apartment) else house(p, face)


def bake_one(dat: Path) -> None:
    for f in city_buildings(dat):
        p = params(f)
        seasons = int(f["seasons"])
        models = [[build(replace(p, snow=season == 1), face)
                   for face in FACES] for season in range(seasons)]
        png = dat.with_name(f"{dat.stem}_hex.png")
        rewrite_city_building(dat, f["name"], bake_city(models, png, 8))


def dats() -> list[Path]:
    return sorted(d for folder in DIRS for d in folder.glob("*.dat"))


def bake_pakset() -> None:
    # The workers find `bake_one` by its module's name: run as a script
    # (or by `tools.bake_all`), this module is a `__main__` they can't see.
    from cityhouses.hex_houses.scene import bake_one
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        list(pool.map(bake_one, dats(), chunksize=8))
    print(f"baked {len(dats())} houses")


def preview(out: Path, count: int, start: int) -> None:
    """`count` houses from `start`, each facing a different side."""
    grass = ground_cell(HexGeom())
    fields = [f for d in dats()[start:start + count]
              for f in city_buildings(d)]
    cells = [composite(render_tiles(build(params(f), FACES[k % 6]), (1, 1),
                                    ambient=AMBIENT), grass)
             for k, f in enumerate(fields)]
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
                    help="write --count houses from --start, each facing a "
                         "side, here instead of baking")
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--start", type=int, default=0)
    a = ap.parse_args()
    if a.preview:
        preview(a.preview, a.count, a.start)
    else:
        bake_pakset()
