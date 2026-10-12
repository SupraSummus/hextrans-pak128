#!/usr/bin/env python3
"""Measure a tunnel portal from its legacy pak128 cell.

    python3 -m infrastructure.measure_tunnel [--overlay] [rail_080_tunnel ...]

With no names, every tunnel that has legacy art in its model dir
(`<family>/<name>/src/<name>.{png,dat}`).  Reads the cell the legacy
.dat names `BackImage[N][0]`: the one tunnel cell in which the portal
faces the viewer (legacy keys name the high edge, so `[N]` opens to the
S, towards the camera) and the face, opening and dark interior are all
visible.  The report lines paste into `tunnel_params.py`.

The portal face is a vertical plane, `y = y0` in the scene frame
(`infrastructure/tunnel_params.py`), and the dimetric camera maps that
plane to the screen without ambiguity: a horizontal run along the face
is `PIXELS_PER_UNIT * cos(YAW)` = 64 px per world unit whatever its
height, a vertical run is `PIXELS_PER_UNIT * cos(ELEV)` = 78.8 px per
world unit, and moving the plane's depth `y0` shifts the whole picture
by a fixed amount along both.  So the pixel marks below, which are read
off the cell and need no 3D model, convert to world units once the
plane's depth is known; and the depth follows from the portal being
centred on the way (x = 0): it is the column of the midpoint between
the opening's two edges.

What is read, per tunnel, in `MARKS` (pixel-boundary coordinates in the
128x128 cell, found on the grid `--overlay` draws):

  open_l, open_r  columns of the opening's left and right edges: where
                  the dark interior, or the lit floor and road seen
                  through the opening, meets the surrounding face.  The
                  ring and reveal around an arch belong to the face.
  crest_y         row of the opening's top edge at the column midway
                  between the two (the arch crest; a box's top).
  face_tl/_tr     the face's top-left and top-right corners, where the
                  face meets the roof strip and, on the right, the dark
                  side face.  Where the block runs past the cell edge
                  the corner is put on the cell edge, on the top-edge
                  line.

Everything else is computed: opening half-width and height, face
half-width and height, and the wall colour, which is the median colour
of the face pixels around the opening (in the upper half, clear of the
wing walls in front of the face), as a model colour: observed divided
by the shade the renderer gives a south-facing wall, so the model
renders back to the observed pixel.  Where a colour would exceed 255 the
colour is scaled down together, keeping its hue (pale concrete cannot
render as bright as pak128 draws it under this lighting).

Read marks are good to about 2 px, 0.03 world units.  They are checked
here against the dark interior where the cell has one (it must lie
between the two edges) and against each other (the two top corners must
agree on the face height, within 0.05).  `--overlay` writes the cell at
8x with the marks' rectangles projected back onto it to
`<model dir>/refs/measure_overlay.png`, to audit the reading by eye.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw

from tools.threed import crop_ref
from tools.threed.render import (
    ELEV, PIXELS_PER_UNIT, SCREEN_CENTER_X, SCREEN_CENTER_Y_GROUND,
    SUN_DIR, YAW, SquareCamera, world_to_screen,
)

INFRA = Path(__file__).resolve().parent

C, S = math.cos(YAW), math.sin(YAW)
# Screen px per world unit along the face (horizontal) and up (vertical).
PX_ALONG = PIXELS_PER_UNIT * C
PX_UP = PIXELS_PER_UNIT * math.cos(ELEV)


class Marks(NamedTuple):
    open_l: float
    open_r: float
    crest_y: float
    face_tl: tuple[float, float]
    face_tr: tuple[float, float]


# Tunnels that share a portal model share the opening: pak128 repaints
# one 3D portal in several materials, which the identical silhouettes
# and dark-interior positions show.  The marks were checked on each
# tunnel's own overlay.
_ARCH = (52, 78, 65)    # rail_080 / 080b / 100 / 120b
_ARCH2 = (35, 59, 70)   # rail_120 / 140
_BOX = (0, 48), (64, 80)    # rail_200 .. 400: the block spans the tile

MARKS: dict[str, Marks] = {
    "rail_080_tunnel":  Marks(*_ARCH, (46, 50), (86, 72)),
    "rail_080b_tunnel": Marks(*_ARCH, (46, 50), (86, 72)),
    "rail_100_tunnel":  Marks(*_ARCH, (36, 47), (86, 72)),
    "rail_120_tunnel":  Marks(*_ARCH2, (17, 50), (67, 75)),
    "rail_120b_tunnel": Marks(*_ARCH, (33, 46), (86, 72)),
    "rail_140_tunnel":  Marks(*_ARCH2, (17, 50), (67, 75)),
    "rail_160_tunnel":  Marks(36, 64, 69, (17, 46), (80, 78)),
    "rail_180_tunnel":  Marks(44, 66, 67, (17, 46), (80, 78)),
    "rail_200_tunnel":  Marks(16, 56, 73, *_BOX),
    "rail_240_tunnel":  Marks(19, 56, 76, *_BOX),
    "rail_280_tunnel":  Marks(19, 56, 76, *_BOX),
    "rail_320_tunnel":  Marks(19, 56, 76, *_BOX),
    "rail_400_tunnel":  Marks(19, 56, 76, *_BOX),
    # Road portals.  The tubes' (road_090, highway_130) ring is thin, so
    # the face top is put 6 px above the crest.  highway_110 and
    # road_070 are not measured: their wing walls run past the face and
    # the top corners cannot be told from the wings' (TODO.md).
    "highway_130_tunnel": Marks(10, 66, 66, (3, 44), (66, 75)),
    "road_040_tunnel":  Marks(10, 56, 81, (0, 62), (64, 93)),
    "road_050_tunnel":  Marks(10, 56, 81, (0, 62), (64, 93)),
    "road_090_tunnel":  Marks(10, 63, 69, (3, 47), (66, 78)),
}

# Brightness the renderer gives a wall facing the camera side (normal
# -y): the face the legacy [N] cell shows.
_AMBIENT = SquareCamera().ambient
FACE_SHADE = _AMBIENT + (1.0 - _AMBIENT) * max(0.0, float(SUN_DIR[1]))


def model_dir(name: str) -> Path:
    for fam in sorted(INFRA.glob("*_tunnels")):
        if (fam / name / "src" / f"{name}.png").exists():
            return fam / name
    raise SystemExit(f"{name}: no legacy art in <family>/{name}/src/")


def legacy_back_n(dat: Path) -> tuple[int, int]:
    pat = re.compile(r"^\s*backimage\[n\]\[0\]\s*=\s*[\w\-]+\.(\d+)\.(\d+)",
                     re.IGNORECASE)
    for line in dat.read_text(errors="replace").splitlines():
        m = pat.match(line)
        if m:
            return int(m.group(1)), int(m.group(2))
    raise SystemExit(f"{dat}: no BackImage[N][0] cell")


def load_cell(name: str) -> np.ndarray:
    src = model_dir(name) / "src"
    row, col = legacy_back_n(src / f"{name}.dat")
    sheet = Image.open(src / f"{name}.png").convert("RGB")
    tile = crop_ref.crop_tile(sheet, row, col, crop_ref.DEFAULT_TILE_SIZE)
    tile = crop_ref.mask_transparent(tile, crop_ref.PAK128_TRANSPARENT)
    return np.asarray(tile, dtype=np.uint8)  # RGBA


# --- Face plane <-> screen --------------------------------------------------

def to_screen(x: float, y0: float, z: float) -> tuple[float, float]:
    sx, sy, _ = world_to_screen(np.array([x, y0, z]))
    return float(sx), float(sy)


def on_plane(sx: float, sy: float, y0: float) -> tuple[float, float]:
    """World (x, z) of the point of the plane `y = y0` that the camera
    shows at screen (sx, sy)."""
    x = ((sx - SCREEN_CENTER_X) / PIXELS_PER_UNIT - S * y0) / C
    y1 = -S * x + C * y0
    y2 = (SCREEN_CENTER_Y_GROUND - sy) / PIXELS_PER_UNIT
    ca, sa = math.cos(-(math.pi / 2.0 - ELEV)), math.sin(-(math.pi / 2.0 - ELEV))
    return x, (ca * y1 - y2) / sa


class Portal(NamedTuple):
    y0: float
    opening_half_w: float
    opening_top_z: float
    face_half_w: float
    face_top_z: float
    top_corner_gap: float


def solve(m: Marks) -> Portal:
    sxc = 0.5 * (m.open_l + m.open_r)
    y0 = ((sxc - SCREEN_CENTER_X) / PIXELS_PER_UNIT) / S
    half_w = (m.open_r - m.open_l) / 2.0 / PX_ALONG
    _, open_top = on_plane(sxc, m.crest_y, y0)
    xl, zl = on_plane(*m.face_tl, y0)
    xr, zr = on_plane(*m.face_tr, y0)
    return Portal(y0, half_w, open_top, (xr - xl) / 2.0, (zl + zr) / 2.0,
                  abs(zl - zr))


# --- Colour -----------------------------------------------------------------

def wall_pixels(cell: np.ndarray, p: Portal) -> np.ndarray:
    """RGB of the cell's face pixels around the opening: the upper half
    of the face, inside its edges and outside the opening, each with a
    0.03 margin."""
    margin, step = 0.03, 0.005
    out = []
    for x in np.arange(-p.face_half_w + margin, p.face_half_w - margin, step):
        if abs(x) < p.opening_half_w + margin:
            zs = np.arange(p.opening_top_z + margin,
                           p.face_top_z - margin / 3, step)
        else:
            zs = np.arange(0.5 * p.face_top_z, p.face_top_z - margin / 3, step)
        for z in zs:
            sx, sy = to_screen(x, p.y0, z)
            ix, iy = int(math.floor(sx)), int(math.floor(sy))
            if 0 <= ix < 128 and 0 <= iy < 128 and cell[iy, ix, 3]:
                out.append(cell[iy, ix, :3])
    return np.asarray(out, dtype=float)


def model_color(observed) -> tuple[tuple[int, int, int], bool]:
    """Observed face colour -> model colour (inverse of the wall shade),
    scaled down together if a channel would pass 255."""
    scale = 1.0 / FACE_SHADE
    top = float(max(observed))
    clipped = top * scale > 255.0
    if clipped:
        scale = 255.0 / top
    return tuple(int(round(c * scale)) for c in observed), clipped


# --- Dark interior cross-check ---------------------------------------------

def dark_core_columns(cell: np.ndarray):
    """Column extent of the cell's dark interior, or None: the largest
    8-connected blob of pixels darker than T, for the lowest T of 40, 50,
    ..., 80 that gives one of at least 150 px (stone dithers have dark
    pixels everywhere, so a fixed T would flood them)."""
    lum = cell[..., :3].astype(float).mean(axis=2)
    opaque = cell[..., 3] > 0
    for t in (40, 50, 60, 70, 80):
        dark = opaque & (lum < t)
        seen = np.zeros_like(dark)
        best = None
        for y, x in zip(*np.nonzero(dark)):
            if seen[y, x]:
                continue
            stack, blob = [(y, x)], []
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                blob.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if (0 <= ny < 128 and 0 <= nx < 128 and dark[ny, nx]
                                and not seen[ny, nx]):
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            if best is None or len(blob) > len(best):
                best = blob
        if best is not None and len(best) >= 150:
            xs = [x for _y, x in best]
            return min(xs), max(xs) + 1
    return None


# --- Report -----------------------------------------------------------------

def measure(name: str):
    m = MARKS[name]
    cell = load_cell(name)
    p = solve(m)
    px = wall_pixels(cell, p)
    color, clipped = model_color(np.median(px, axis=0))
    return m, cell, p, px, color, clipped


def report(name: str, overlay: bool = False) -> None:
    m, cell, p, px, color, clipped = measure(name)
    print(f"=== {name} ===")
    print(f"  face plane y0 = {p.y0:+.3f}; wall pixels {len(px)}, "
          f"observed {tuple(int(c) for c in np.median(px, axis=0))}"
          + ("  (scaled to keep hue)" if clipped else ""))
    core = dark_core_columns(cell)
    if core is not None:
        inside = m.open_l - 1 <= core[0] and core[1] <= m.open_r + 1
        print(f"  dark interior columns {core[0]}..{core[1]}, marks "
              f"{m.open_l:g}..{m.open_r:g}: {'ok' if inside else 'OUTSIDE'}")
    if p.top_corner_gap > 0.05:
        print(f"  WARNING: top corners disagree by {p.top_corner_gap:.3f}")
    if len(px) < 30:
        print(f"  WARNING: only {len(px)} wall pixels sampled")
    print(f"  TunnelParams(name=\"{name}\", wall_color={color}, "
          f"face_half_w={p.face_half_w:.3f}, "
          f"opening_half_w={p.opening_half_w:.3f}, "
          f"face_top_z={p.face_top_z:.3f}, "
          f"opening_top_z={p.opening_top_z:.3f})")
    if overlay:
        out = model_dir(name) / "refs" / "measure_overlay.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        draw_overlay(cell, m, p).save(out)
        print(f"  wrote {out.relative_to(INFRA.parent)}")


def draw_overlay(cell: np.ndarray, m: Marks, p: Portal, zoom: int = 8):
    im = Image.fromarray(cell[..., :3]).resize(
        (128 * zoom, 128 * zoom), Image.NEAREST)
    d = ImageDraw.Draw(im)
    for i in range(0, 128, 8):
        d.line([(i * zoom, 0), (i * zoom, 128 * zoom)], fill=(0, 130, 0))
        d.line([(0, i * zoom), (128 * zoom, i * zoom)], fill=(0, 130, 0))
        d.text((i * zoom + 2, 2), str(i), fill=(255, 255, 0))
        d.text((2, i * zoom + 2), str(i), fill=(255, 255, 0))

    def rect(half_w, top, color, x_off=0.0):
        pts = [to_screen(x_off + sx_, p.y0, z) for sx_, z in
               ((-half_w, 0), (half_w, 0), (half_w, top), (-half_w, top))]
        pts = [(a * zoom, b * zoom) for a, b in pts]
        d.line(pts + [pts[0]], fill=color, width=2)

    rect(p.opening_half_w, p.opening_top_z, (255, 0, 0))
    rect(p.face_half_w, p.face_top_z, (0, 200, 255))
    for pt in (m.face_tl, m.face_tr, ((m.open_l + m.open_r) / 2, m.crest_y)):
        x, y = pt[0] * zoom, pt[1] * zoom
        d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(255, 255, 0), width=2)
    return im


def main(argv: list[str]) -> None:
    overlay = "--overlay" in argv
    names = [a for a in argv if not a.startswith("--")] or sorted(MARKS)
    for name in names:
        report(name, overlay)


if __name__ == "__main__":
    main(sys.argv[1:])
