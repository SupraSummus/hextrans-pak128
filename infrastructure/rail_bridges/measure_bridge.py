#!/usr/bin/env python3
"""Measure a rail bridge tier's structure from its pak128 square cells.

    python3 -m infrastructure.rail_bridges.measure_bridge [rail_080_bridge ...]

With no arguments, every tier in `LEGACY_CELLS`.  Counterpart of
`rail_tracks/measure_tier.py`: the `BridgeParams` values of the tiers
after rail_060 are to be read off the pak128 art by this script, not
tuned by eye.  The report prints material colours and the pillar box
today; the plane helpers below (`deck_half_width`, `side_z_range`,
envelopes, arch opening) are the building blocks for the per-tier
structure, not yet wired into `report` (TODO.md, "Rail bridge tiers
still legacy").

Cells.  The tier `.dat`s now carry the hex keys, so the pak128 square
layout the measurements read is pinned in `LEGACY_CELLS` (row, col and
the draw offset of each cell, copied from the pre-hex `.dat`s; see git
history).  Every cell is placed in composite coordinates — cell pixel
+ dat offset — where world z=0 lands at y=106 on the tile's centre
column x=64, the anchor `tools/threed/bridge.py` calibrated on
rail_060 (`_SQ_CAMERA` + the `,0,32` shift).  A cell drawn with a
different offset therefore needs no special case.

Geometry.  A pixel is a ray; it fixes a world point once one
coordinate is assumed, so every measurement names the plane it
unprojects onto, all in the NS segment's frame (bridge along world y,
the viewer-side edge at +x):

    deck plane   z = DECK_TOP_Z     the deck-top surface (track bed,
                                     ties) -> its half-width.
    side plane   x = +w             the viewer-side structure, the
                                     FrontImage cell when the tier has
                                     one (else the Back cell's lower
                                     envelope) -> the z range of the
                                     side parts.  w is the measured
                                     deck-top half-width plus `inset`.
    pillar       the pillar cell's screen-x extent and the column where
                 the two visible faces meet (the shading step) -> the
                 box's half extents across and along the bridge.

Colours.  Pixels are split into material classes by hue / saturation
/ luminance (`CLASSES`).  A part's model colour is the class median
over the shade the renderer gives the face it is mostly seen on: the
top face for horizontal parts (deck, bed), a south-facing wall for
vertical parts (girders, trusses, walls, pillars) — the face the hex
camera looks at most squarely.  So the model colour renders back to
the observed pak128 pixel on that face.
"""
from __future__ import annotations

import colorsys
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed import crop_ref
from tools.threed.bridge import DECK_TOP_Z
from tools.threed.render import ELEV, PIXELS_PER_UNIT, SUN_DIR, SquareCamera

HERE = Path(__file__).resolve().parent

# Composite anchor (see module docstring).
CX, CY = 64.0, 106.0
# Composite canvas: cells land at y + PAD so negative offsets fit.
PAD = 48
CANVAS = (128, 128 + 2 * PAD)

# (row, col, x offset, y offset) of the pak128 square cells, from the
# pre-hex `.dat`s.  NS segment, S pillar, N start and ramp.
LEGACY_CELLS = {
    "rail_060_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backpillar[s]": (4, 4, 0, 0), "backstart[n]": (2, 4, 0, 32), "frontstart[n]": (2, 5, 0, 32), "backramp[n]": (1, 4, 0, 0), "frontramp[n]": (1, 5, 0, 0)},
    "rail_060b_bridge": {"backimage[ns]": (1, 0, 0, 32), "backpillar[s]": (2, 6, 0, 16), "backstart[n]": (1, 6, 0, 32), "backramp[n]": (1, 2, 0, 0)},
    "rail_080_bridge": {"backimage[ns]": (1, 2, 0, 32), "backimage2[ns]": (1, 0, 0, 32), "backpillar[s]": (3, 0, 0, 16), "backstart[n]": (2, 0, 0, 32), "backramp[n]": (1, 4, 0, 0)},
    "rail_080b_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backpillar[s]": (4, 0, 0, 16), "backstart[n]": (2, 0, 0, 32), "frontstart[n]": (2, 1, 0, 32), "backramp[n]": (1, 4, 0, 0)},
    "rail_100_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backpillar[s]": (4, 0, 0, 0), "backstart[n]": (2, 0, 0, 32), "frontstart[n]": (2, 1, 0, 32), "backramp[n]": (1, 4, 0, 0)},
    "rail_120_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backimage2[ns]": (1, 2, 0, 40), "frontimage2[ns]": (1, 3, 0, 32), "backpillar[s]": (5, 0, -12, 4), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 32), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_120b_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backpillar[s]": (4, 0, 0, 0), "backstart[n]": (3, 4, 0, 32), "frontstart[n]": (3, 5, 0, 32), "backramp[n]": (1, 4, 0, 0), "frontramp[n]": (1, 5, 0, 0)},
    "rail_140_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backimage2[ns]": (1, 2, 0, 40), "frontimage2[ns]": (1, 3, 0, 32), "backpillar[s]": (5, 0, -12, 4), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 32), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_160_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backimage2[ns]": (1, 2, 0, 40), "frontimage2[ns]": (1, 3, 0, 32), "backpillar[s]": (5, 0, -12, 4), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 32), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_180_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backimage2[ns]": (1, 2, 0, 40), "frontimage2[ns]": (1, 3, 0, 32), "backpillar[s]": (5, 0, -12, 4), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 32), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_200_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 32), "backimage2[ns]": (1, 2, 0, 32), "frontimage2[ns]": (1, 3, 0, 32), "backpillar[s]": (5, 0, -9, 5), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 32), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_240_bridge": {"backimage[ns]": (1, 0, 0, 8), "frontimage[ns]": (1, 1, 0, 8), "backpillar[s]": (4, 4, -9, 5), "backstart[n]": (2, 4, 0, 8), "frontstart[n]": (2, 5, 0, 36), "backramp[n]": (1, 4, 0, 0), "frontramp[n]": (1, 5, 0, -8)},
    "rail_280_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 16), "backimage2[ns]": (1, 4, 0, 32), "frontimage2[ns]": (1, 5, 0, 16), "backpillar[s]": (5, 0, 0, 0), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 16), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_320_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 16), "backimage2[ns]": (1, 4, 0, 32), "frontimage2[ns]": (1, 5, 0, 16), "backpillar[s]": (5, 0, 0, 0), "backstart[n]": (3, 0, 0, 32), "frontstart[n]": (3, 1, 0, 16), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
    "rail_400_bridge": {"backimage[ns]": (1, 0, 0, 32), "frontimage[ns]": (1, 1, 0, 16), "backimage2[ns]": (1, 4, 0, 32), "frontimage2[ns]": (1, 5, 0, 16), "backpillar[s]": (5, 0, 0, 0), "backstart[n]": (4, 0, 0, 32), "frontstart[n]": (4, 1, 0, 16), "backramp[n]": (2, 0, 0, 0), "frontramp[n]": (2, 1, 0, 0)},
}


# --- Shading -----------------------------------------------------------------

_AMB = SquareCamera().ambient


def _shade(normal) -> float:
    return _AMB + (1.0 - _AMB) * max(0.0, float(np.dot(-SUN_DIR, normal)))


SHADE_TOP = _shade((0.0, 0.0, 1.0))
SHADE_SOUTH = _shade((0.0, -1.0, 0.0))


def model_colour(observed, shade: float):
    return tuple(int(min(255, round(c / shade))) for c in observed)


# --- Material classes -----------------------------------------------------

def _hsv(rgb: np.ndarray) -> np.ndarray:
    flat = rgb.reshape(-1, 3) / 255.0
    return np.array([colorsys.rgb_to_hsv(*p) for p in flat]).reshape(rgb.shape)


# name -> predicate over (rgb float array HxWx3, hsv HxWx3)
CLASSES = {
    # pak128 bridge-steel blue
    "steel": lambda rgb, hsv: (hsv[..., 0] > 0.50) & (hsv[..., 0] < 0.70)
                              & (hsv[..., 1] > 0.20),
    # warm-tinted stone, brick, timber, gravel
    "warm": lambda rgb, hsv: (hsv[..., 0] < 0.17) & (hsv[..., 1] > 0.08)
                             & (hsv[..., 2] > 0.25),
    # concrete and grey stone
    "grey": lambda rgb, hsv: (hsv[..., 1] <= 0.08) & (hsv[..., 2] > 0.30),
    # tie and shadow blacks
    "dark": lambda rgb, hsv: hsv[..., 2] <= 0.25,
}


# --- Cells -----------------------------------------------------------------

class Cell:
    """One pak128 cell in composite coordinates."""

    def __init__(self, tier: str, key: str):
        row, col, ox, oy = LEGACY_CELLS[tier][key]
        sheet = Image.open(HERE / f"{tier}.png").convert("RGB")
        tile = crop_ref.mask_transparent(
            crop_ref.crop_tile(sheet, row, col, crop_ref.DEFAULT_TILE_SIZE),
            crop_ref.PAK128_TRANSPARENT)
        canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        canvas.alpha_composite(tile, (ox, oy + PAD))
        self.rgba = np.asarray(canvas, dtype=np.uint8)
        self.rgb = self.rgba[..., :3].astype(float)
        self.opaque = self.rgba[..., 3] > 0
        self.hsv = _hsv(self.rgba[..., :3])
        sy, sx = np.mgrid[0:CANVAS[1], 0:CANVAS[0]]
        self.sx = sx + 0.5
        self.sy = sy + 0.5 - PAD

    def cls(self, name: str) -> np.ndarray:
        return self.opaque & CLASSES[name](self.rgb, self.hsv)

    def __or__(self, other: "Cell") -> "Cell":
        out = object.__new__(Cell)
        out.__dict__.update(self.__dict__)
        take = other.opaque & ~self.opaque
        out.rgba = np.where(take[..., None], other.rgba, self.rgba)
        out.rgb = out.rgba[..., :3].astype(float)
        out.opaque = self.opaque | other.opaque
        out.hsv = np.where(take[..., None], other.hsv, self.hsv)
        return out


def cell(tier: str, key: str) -> Cell | None:
    return Cell(tier, key) if key in LEGACY_CELLS[tier] else None


# --- Unprojection (NS frame, square camera) -------------------------------

_A = -(math.pi / 2.0 - ELEV)
_CA, _SA = math.cos(_A), math.sin(_A)
_P = PIXELS_PER_UNIT


def _uv(sx, sy):
    """Screen -> (u, v): u = (x + y)/√2, v = ca·(y - x)/√2 - sa·z."""
    return (sx - CX) / _P, (CY - sy) / _P


def on_z(sx, sy, z):
    """World (x, y) of the pixel's ray at height z."""
    u, v = _uv(sx, sy)
    b = (v + _SA * z) / _CA
    return (u - b) / math.sqrt(2.0), (u + b) / math.sqrt(2.0)


def on_x(sx, sy, x):
    """World (y, z) of the pixel's ray at x."""
    u, v = _uv(sx, sy)
    y = math.sqrt(2.0) * u - x
    z = (_CA * (y - x) / math.sqrt(2.0) - v) / _SA
    return y, z


def screen_x_per_unit() -> float:
    """Screen px per world unit along x (or y) on the screen's x axis."""
    return _P / math.sqrt(2.0)


# --- Measurements ------------------------------------------------------------

ALONG = 0.30  # |y| window around the tile centre, clear of cut ends


def deck_half_width(c: Cell, mask: np.ndarray) -> float:
    """Half the perpendicular extent of `mask` pixels on the deck plane
    (2 % / 98 % percentiles, |y| < ALONG)."""
    x, y = on_z(c.sx, c.sy, DECK_TOP_Z)
    sel = mask & (np.abs(y) < ALONG)
    lo, hi = np.percentile(x[sel], [2, 98])
    return float(hi - lo) / 2.0


def side_z_range(c: Cell, mask: np.ndarray, w: float,
                 pct=(1, 99)) -> tuple[float, float]:
    """z range of `mask` pixels on the side plane x = w (|y| < ALONG)."""
    y, z = on_x(c.sx, c.sy, w)
    sel = mask & (np.abs(y) < ALONG)
    lo, hi = np.percentile(z[sel], pct)
    return float(lo), float(hi)


def lower_envelope_z(c: Cell, mask: np.ndarray, w: float) -> float:
    """Median over columns of the lowest `mask` pixel, on x = w: the
    bottom edge of the viewer-side structure."""
    y, z = on_x(c.sx, c.sy, w)
    sel = mask & (np.abs(y) < ALONG)
    zs = [z[:, i][sel[:, i]].min() for i in range(sel.shape[1])
          if sel[:, i].any()]
    return float(np.median(zs))


def upper_envelope_z(c: Cell, mask: np.ndarray, w: float) -> float:
    """Median over columns of the highest `mask` pixel, on x = w."""
    y, z = on_x(c.sx, c.sy, w)
    sel = mask & (np.abs(y) < ALONG)
    zs = [z[:, i][sel[:, i]].max() for i in range(sel.shape[1])
          if sel[:, i].any()]
    return float(np.median(zs))


def opening_crown_z(c: Cell, w: float, z_below: float) -> float:
    """Highest transparent pixel on x = w over the tile centre
    (|y| < 0.05) below `z_below`, with opaque pixels further down the
    same column: the crown of an arch opening in the viewer-side
    spandrel."""
    y, z = on_x(c.sx, c.sy, w)
    best = float("nan")
    for i in range(c.opaque.shape[1]):
        col = (np.abs(y[:, i]) < 0.05)
        if not col.any():
            continue
        zc, oc = z[:, i][col], c.opaque[:, i][col]
        hole = ~oc & (zc < z_below)
        if not hole.any() or not oc[zc < zc[hole].min()].any():
            continue
        best = np.nanmax([best, zc[hole].max()])
    return best


def opening_span(c: Cell, w: float, z_at: float) -> float:
    """Along-length of the transparent run through the tile centre on
    x = w at height `z_at`: the arch opening's width there."""
    # Screen point of (w, y, z_at) for each y; walk y in fine steps.
    ys = np.arange(-0.6, 0.6, 0.002)
    u = (w + ys) / math.sqrt(2.0)
    v = _CA * (ys - w) / math.sqrt(2.0) - _SA * z_at
    px = np.floor(CX + u * _P).astype(int)
    py = np.floor(CY - v * _P).astype(int) + PAD
    ok = (px >= 0) & (px < CANVAS[0]) & (py >= 0) & (py < CANVAS[1])
    hole = np.zeros_like(ys, dtype=bool)
    hole[ok] = ~c.opaque[py[ok], px[ok]]
    i0 = int(np.argmin(np.abs(ys)))
    if not hole[i0]:
        return 0.0
    lo = hi = i0
    while lo > 0 and hole[lo - 1]:
        lo -= 1
    while hi < len(ys) - 1 and hole[hi + 1]:
        hi += 1
    return float(ys[hi] - ys[lo])


def pillar_box(c: Cell, mask: np.ndarray) -> tuple[float, float]:
    """Half extents (across, along) of a box pillar from its cell.

    For the S pillar of an NS bridge the box's leftmost silhouette
    point is the corner (-a, -b), the rightmost (+a, +b) and the edge
    between the two visible side faces the corner (+a, -b), so with
    k = screen px per world unit on screen-x: width = 2k(a + b) and
    edge - centre = k(a - b).  The edge is the column where the
    face shading steps (largest jump of the column-mean luminance)."""
    cols = np.where(mask.any(axis=0))[0]
    x0, x1 = cols.min(), cols.max() + 1
    lum = c.rgb.mean(axis=2)
    means = np.array([lum[:, i][mask[:, i]].mean() for i in range(x0, x1)])
    # Smooth over 3 columns, step = difference of 3-column means.
    k = 3
    steps = [abs(means[i:i + k].mean() - means[i - k:i].mean())
             for i in range(k, len(means) - k + 1)]
    edge = x0 + k + int(np.argmax(steps))
    centre = 0.5 * (x0 + x1)
    kx = screen_x_per_unit()
    s, d = (x1 - x0) / (2 * kx), (edge - centre) / kx
    return (s + d) / 2.0, (s - d) / 2.0


def class_colour(c: Cell, mask: np.ndarray):
    return tuple(int(v) for v in np.median(c.rgb[mask], axis=0))


# --- Report ------------------------------------------------------------------

def report(tier: str) -> None:
    back = cell(tier, "backimage[ns]")
    front = cell(tier, "frontimage[ns]")
    both = back | front if front is not None else back
    print(f"=== {tier} ===")
    for name in CLASSES:
        m = both.cls(name)
        if m.sum() < 40:
            continue
        obs = class_colour(both, m)
        print(f"  {name:5s} {int(m.sum()):5d} px  observed {obs}  "
              f"model top {model_colour(obs, SHADE_TOP)}  "
              f"south {model_colour(obs, SHADE_SOUTH)}")
    pil = cell(tier, "backpillar[s]")
    for name in CLASSES:
        m = pil.cls(name)
        if m.sum() < 40:
            continue
        obs = class_colour(pil, m)
        print(f"  pillar {name:5s} {int(m.sum()):5d} px observed {obs} "
              f"model south {model_colour(obs, SHADE_SOUTH)}")
    a, b = pillar_box(pil, pil.opaque)
    print(f"  pillar box half across {a:.3f} along {b:.3f}")


def main(argv: list[str]) -> None:
    print(f"shade top {SHADE_TOP:.3f} south {SHADE_SOUTH:.3f}")
    for tier in argv or LEGACY_CELLS:
        report(tier)


if __name__ == "__main__":
    main(sys.argv[1:])
