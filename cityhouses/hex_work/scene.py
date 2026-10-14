"""The pak128 commercial and industrial city buildings for the hex grid.

`cityhouses/com` (173) and `cityhouses/ind` (158), one `.dat` each.
As for the houses, the level sets the size and a hash of the name the
rest (`tools.threed.city`):

- commercial: below 10 a shop with a car park, below 20 a shop with
  flats over it, from 20 an office block, ribbon-glazed after 1970;
- industrial: below 12 a workshop with a yard, below 25 a works hall
  under a gable or north-light roof with a stack, from 25 a
  multi-storey brick works.

    python3 -m cityhouses.hex_work.scene
    python3 -m cityhouses.hex_work.scene --preview out.png [--kind com]
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
    FACES, Office, Shop, Works, bake_city, city_buildings, office, pick,
    rewrite_city_building, shop, unit, works)
from tools.threed.hex_synth import HexGeom

CITY_DIR = Path(__file__).resolve().parent.parent
DIRS = [CITY_DIR / d for d in ("com", "com/no-winter", "ind",
                               "ind/no-winter")]

SHOP_WALLS = ((232, 228, 218), (214, 196, 160), (190, 120, 90),
              (176, 176, 172), (226, 210, 180))
AWNINGS = ((180, 50, 44), (50, 110, 70), (40, 80, 150), (220, 170, 40),
           (230, 230, 226))
SIGNS = ((200, 40, 40), (40, 90, 180), (230, 190, 40), (40, 140, 90),
         (240, 240, 236))
OFFICE_WALLS = ((214, 210, 200), (170, 170, 168), (120, 120, 124),
                (196, 176, 150), (150, 90, 70))
OFFICE_GLASS = ((80, 110, 150), (60, 90, 110), (110, 150, 170),
                (70, 80, 96), (100, 130, 110))
CROWNS = ((40, 70, 150), (180, 50, 44), (230, 230, 226), None, None, None)
BRICKS = ((150, 70, 50), (128, 62, 48), (170, 100, 70), (110, 90, 80),
          (150, 150, 144), (90, 110, 150))


def year_of(f) -> int:
    return int(re.sub(r"\D", "", f.get("intro_year", "1950")) or 1950)


def footprint(name, depth0, depth1):
    """`(s0, s1, w)` of a box inside the hex, 0.1 to spare."""
    depth = depth0 + (depth1 - depth0) * unit(name, "depth")
    w = 1 - depth / 2 / math.sqrt(3) - 0.1 - 0.15 * unit(name, "w")
    return -depth / 2, depth / 2, w


def params(f: dict[str, str]):
    name, level = f["name"], int(f.get("level", "5"))
    year = year_of(f)
    if f.get("type", "com").lower() == "com":
        if level < 20:
            s0, s1, w = footprint(name, 0.6, 0.9)
            return Shop(
                storeys=1 if level < 10 else 2 + (level >= 15),
                s0=s0 - 0.15, s1=s1 - 0.15, w=w,
                wall=pick(name, "wall", SHOP_WALLS),
                awning=pick(name, "awning", AWNINGS),
                sign=pick(name, "sign", SIGNS),
                roof=("hip" if level >= 10 and unit(name, "hip") < 0.4
                      else "flat"),
                roof_colour=pick(name, "roofc", ((150, 70, 52), (96, 96, 100))),
                parking=level < 10, seed=name)
        s0, s1, w = footprint(name, 0.9, 1.25)
        return Office(
            storeys=max(4, min(16, 2 + level // 4)), s0=s0, s1=s1, w=w,
            wall=pick(name, "wall", OFFICE_WALLS),
            glass=pick(name, "glass", OFFICE_GLASS),
            ribbon=year >= 1970 and unit(name, "ribbon") < 0.6,
            crown=pick(name, "crown", CROWNS))
    if level < 12:
        s0, s1, w = footprint(name, 0.7, 1.0)
        return Works(
            storeys=1, s0=s0 - 0.2, s1=s1 - 0.2, w=w,
            wall=pick(name, "wall", BRICKS),
            roof=pick(name, "roof", ("gable", "gable", "flat")),
            roof_colour=pick(name, "roofc", ((96, 96, 100), (150, 70, 52))),
            tank=unit(name, "tank") < 0.3, seed=name)
    if level < 25:
        s0, s1, w = footprint(name, 0.85, 1.15)
        return Works(
            storeys=2, s0=s0 - 0.1, s1=s1 - 0.1, w=w,
            wall=pick(name, "wall", BRICKS),
            roof=pick(name, "roof", ("sawtooth", "gable")),
            chimney=0.9 + 0.4 * unit(name, "stack")
            if unit(name, "has_stack") < 0.6 else 0.0,
            tank=unit(name, "tank") < 0.25, seed=name)
    s0, s1, w = footprint(name, 0.9, 1.2)
    return Works(
        storeys=max(4, min(9, 1 + level // 7)), s0=s0, s1=s1, w=w,
        wall=pick(name, "wall", BRICKS), roof="flat",
        chimney=0.0 if unit(name, "has_stack") < 0.5 else
        (max(4, min(9, 1 + level // 7))) * 0.22 + 0.5,
        yard=False, seed=name)


def build(p, face):
    if isinstance(p, Shop):
        return shop(p, face)
    if isinstance(p, Office):
        return office(p, face)
    return works(p, face)


def bake_one(dat: Path) -> None:
    for f in city_buildings(dat):
        p = params(f)
        models = [[build(replace(p, snow=season == 1), face) for face in FACES]
                  for season in range(int(f["seasons"]))]
        png = dat.with_name(f"{dat.stem}_hex.png")
        rewrite_city_building(dat, f["name"], bake_city(models, png, 8))


def dats(kind: str | None = None) -> list[Path]:
    return sorted(d for folder in DIRS for d in folder.glob("*.dat")
                  if kind is None or folder.relative_to(CITY_DIR).parts[0]
                  == kind)


def bake_pakset() -> None:
    # The workers find `bake_one` by its module's name: run as a script
    # (or by `tools.bake_all`), this module is a `__main__` they can't see.
    from cityhouses.hex_work.scene import bake_one
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        list(pool.map(bake_one, dats(), chunksize=8))
    print(f"baked {len(dats())} shops, offices and works")


def preview(out: Path, kind: str, count: int) -> None:
    """`count` buildings of `kind` spread over its levels."""
    fields = sorted((f for d in dats(kind) for f in city_buildings(d)),
                    key=lambda f: int(f.get("level", "0")))
    fields = fields[::max(1, len(fields) // count)][:count]
    grass = ground_cell(HexGeom())
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
                    help="write --count buildings of --kind here instead "
                         "of baking")
    ap.add_argument("--kind", default="com", choices=("com", "ind"))
    ap.add_argument("--count", type=int, default=16)
    a = ap.parse_args()
    if a.preview:
        preview(a.preview, a.kind, a.count)
    else:
        bake_pakset()
