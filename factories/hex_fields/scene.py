"""Farm fields for the hex grid.

A field is a hex just inside its tile, so a strip of grass parts
neighbouring fields, under rows of crop along the NW-SE axis.  Each
field has four seasonal images and one for snow (`field_t` picks by
month; the last image shows above the snowline): bare soil, young
rows, grown rows, ripe or harvested, snow.  `CROPS` gives the soil,
row height and colours per season; the forest plantation's field is
a stand of conifers instead.

Writes `fields_hex.png` (a row per field, a column per image) next to
the factories and rewrites each field's `Image[k]` lines.

    python3 -m factories.hex_fields.scene
    python3 -m factories.hex_fields.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed.bespoke import bake_atlas
from tools.threed.building import composite, ground_cell
from tools.threed.building_kit import AMBIENT, edit_dat
from tools.threed.hex_synth import HexGeom, hash_noise01
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import Frame, add_block, add_frustum

FACTORIES_DIR = Path(__file__).resolve().parent.parent
OUT_PNG = FACTORIES_DIR / "fields_hex.png"

ROWS = Frame((math.sqrt(3) / 2, -0.5))   # rows run NW-SE
INSET = 0.9                              # the field's hex, against the tile's
PITCH = 0.09                             # between rows
SNOW = (236, 238, 242)


@dataclass(frozen=True)
class Season:
    soil: tuple[int, int, int]
    height: float = 0.0                  # of the rows, 0 for bare soil
    crop: tuple[int, int, int] = (0, 0, 0)
    fleck: tuple[int, int, int] | None = None   # flowers, bolls, tassels


@dataclass(frozen=True)
class Crop:
    name: str                            # the field object
    dat: str
    seasons: tuple[Season, Season, Season, Season, Season]


SOIL = (122, 82, 50)
DARK_SOIL = (70, 56, 44)
CROPS = [
    Crop("grain_field", "fields_agriculture.dat", (
        Season(SOIL),
        Season(SOIL, 0.012, (120, 160, 60)),
        Season(SOIL, 0.03, (120, 170, 60)),
        Season(SOIL, 0.035, (222, 196, 70), fleck=(240, 220, 110)),
        Season(SNOW))),
    Crop("cotton_field", "fields_agriculture.dat", (
        Season(SOIL),
        Season(SOIL, 0.015, (70, 140, 60)),
        Season(SOIL, 0.035, (60, 130, 56)),
        Season(SOIL, 0.035, (90, 120, 70), fleck=(246, 246, 240)),
        Season(SNOW))),
    Crop("corn_field", "corn_farm.dat", (
        Season(DARK_SOIL),
        Season(DARK_SOIL, 0.03, (50, 110, 50)),
        Season(DARK_SOIL, 0.07, (46, 104, 52), fleck=(200, 180, 90)),
        Season(DARK_SOIL, 0.07, (160, 140, 90)),
        Season(SNOW, 0.04, (220, 222, 226))),),
]


def field_hex(r=INSET):
    return [(r * math.cos(math.pi / 3 * k), r * math.sin(math.pi / 3 * k))
            for k in range(6)]


def inside(x, y, r=INSET):
    """Plan points inside the flat-top hex of circumradius `r`."""
    s = math.sqrt(3)
    return (np.abs(y) <= s * r / 2) & (s * np.abs(x) + np.abs(y) <= s * r)


def soil_shader(colour, furrows=True):
    base = np.array(colour, float)

    def shader(wx, wy, sx, sy):
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (0.88 + 0.2 * n)[:, None]
        if furrows:
            p = ROWS.local(wx, wy)[1]
            rgb[np.abs((p / PITCH) % 1.0 - 0.5) > 0.32] *= 0.78
        rgb[~inside(wx, wy, INSET - 0.02)] *= 0.85
        return rgb, inside(wx, wy)

    return shader


def row_shader(colour, fleck):
    base = np.array(colour, float)

    def shader(wx, wy, sx, sy):
        n = hash_noise01(sx.astype(np.uint32) * 3 + 1, sy.astype(np.uint32))
        rgb = base * (0.8 + 0.35 * n)[:, None]
        if fleck is not None:
            rgb[n > 0.82] = fleck
        return rgb, np.ones(len(wx), bool)

    return shader


def build(season: Season) -> Model:
    model = Model()
    pts = [(x, y, 0.002) for x, y in field_hex(1.0)]
    shader = soil_shader(season.soil, furrows=season.soil != SNOW)
    model.add_quad(pts[:4], (0, 0, 0), shader=shader)
    model.add_quad([pts[0], pts[3], pts[4], pts[5]], (0, 0, 0), shader=shader)
    if season.height:
        # Rows as low ridges across the field, cut to its hex.
        for k in range(-int(INSET / PITCH) - 1, int(INSET / PITCH) + 2):
            p = k * PITCH
            # the row's extent along `s` inside the field's hex
            ts = [t for t in np.linspace(-1.2, 1.2, 97)
                  if inside(*ROWS.world(t, p, 0)[:2])]
            if len(ts) < 2:
                continue
            s0, s1 = min(ts) + 0.03, max(ts) - 0.03
            if s1 <= s0:
                continue
            add_block(model, ROWS, s0, s1, p - PITCH * 0.28, p + PITCH * 0.28,
                      0.0, season.height, season.crop,
                      top_shader=row_shader(season.crop, season.fleck),
                      side_shader=row_shader(
                          tuple(int(c * 0.8) for c in season.crop),
                          season.fleck))
    return model


def conifers(snow: bool) -> Model:
    model = Model()
    green = (220, 228, 230) if snow else (44, 96, 54)
    for s, p, h in ((-0.35, -0.2, 0.8), (0.3, -0.3, 0.7), (0.0, 0.3, 0.9),
                    (0.45, 0.35, 0.65), (-0.45, 0.4, 0.6)):
        add_frustum(model, ROWS, s, p, 0.03, 0.03, 0, 0.08, (70, 44, 32), n=6)
        for r, z0, z1 in ((0.2, 0.06, 0.45), (0.15, 0.3, 0.65),
                          (0.1, 0.5, 0.82)):
            k = h / 0.8
            add_frustum(model, ROWS, s, p, r * k, 0.0, z0 * k, z1 * k, green,
                        n=10)
    return model


def cells():
    camera = HexCamera(ambient=AMBIENT)
    out = []
    for crop in CROPS:
        out.append([render(build(s), camera) for s in crop.seasons])
    forest = [render(conifers(False), camera)] * 4 + \
        [render(conifers(True), camera)]
    out.append(forest)
    return out


IMAGE_LINE = re.compile(r"^\s*Image\[(\d+)\]\s*=", re.I)


def rewrite_field(dat: Path, name: str, row: int) -> None:
    """Point the `Image[k]` lines of field `name` at row `row` of the
    atlas, column `k`."""
    def edit(lines):
        out, current = [], None
        for line in lines:
            if line.lower().startswith("name="):
                current = line.split("=", 1)[1].strip()
            m = IMAGE_LINE.match(line)
            if m and current == name:
                line = f"Image[{m.group(1)}]={OUT_PNG.stem}.{row}.{m.group(1)}"
            out.append(line)
        return out
    edit_dat(dat, edit)


def bake_pakset() -> None:
    rows = cells()
    entries = [(f"{r}.{c}", lambda im=im: im)
               for r, row in enumerate(rows) for c, im in enumerate(row)]
    bake_atlas(out_png=OUT_PNG, entries=entries, cols_per_row=5)
    for row, crop in enumerate(CROPS):
        rewrite_field(FACTORIES_DIR / crop.dat, crop.name, row)
    rewrite_field(FACTORIES_DIR / "forestplantation.dat",
                  "forestplantation_field", len(CROPS))


def preview(out: Path) -> None:
    """Each field in each season on a patch of seven tiles."""
    rows = cells()
    sheets = []
    for row in rows:
        for im in row:
            tiles = {(x, y): [im] for x, y in ((0, 0), (1, 0), (0, 1), (1, -1),
                                               (-1, 1), (-1, 0), (0, -1))}
            sheets.append(composite(tiles, ground_cell(HexGeom())))
    w, h = sheets[0].size
    sheet = Image.new("RGBA", (w * 5, h * len(rows)))
    for k, s in enumerate(sheets):
        sheet.alpha_composite(s, ((k % 5) * w, (k // 5) * h))
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write every field on a patch of tiles instead of "
                         "baking")
    a = ap.parse_args()
    if a.preview:
        preview(a.preview)
    else:
        bake_pakset()
