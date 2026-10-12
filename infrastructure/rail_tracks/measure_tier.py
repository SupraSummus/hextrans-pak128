#!/usr/bin/env python3
"""Measure a rail tier's cross-section from its pak128 square cells.

    python3 -m infrastructure.rail_tracks.measure_tier [rail_080_tracks ...]

With no arguments, every `rail_*_tracks.png` in this directory.  Reads
the NS and EW straights (sheet cells 1.5 / 1.6, the same crops
`way_verify.verify_square` diffs against), so no build step has to run
first.  Why this exists: eyeballing "the ballast looks about this wide,
the ties about that grey" mixes up screen distances with world
distances (they differ by the dimetric projection's per-axis factors)
and picks colours the lighting then shifts.  This script does both
conversions once, against the reference, so `RailParams` values are set
from data.

What it measures, per tier:

  rail    The two solid-colour pixel clusters pak128 paints for the
          rails: the lighter is the rail head, the darker the shadow
          line beside it.  Head colour, and the gauge by fitting a
          line to each rail's head pixels (perpendicular distance
          between the two fits, over the dimetric perpendicular
          px-per-world factor).
  ties    The along-track period of the luminance between the rails
          (grid search).  Then 2-means on the luminance of the pixels
          between the rails: the cluster farther from the ballast
          outside the tie ends is the tie colour (pak128 ties are a
          lattice of dark or pale pixels, never a solid fill).  Tie
          length: the perpendicular run around the axis where
          tie-like pixels stay at least half-way from their density
          outside the tie ends to their density near the axis; n/a
          where the ties are too faint for that.
  ballast Opaque coverage by perpendicular distance (the silhouette's
          dither) and the median colour of the ballast pixels (rails
          and tie-like pixels excluded), fitted into bands by
          `fit_bands`.  The output lines paste into `RailParams`.

Geometry: pixels are unprojected onto the ground plane (z = 0), which
gives each pixel a (perpendicular, along-track) world coordinate.
Raised parts (rails, ties) unproject displaced by about 1.25 * z along
both axes, so only differences between pixels of one class (gauge, tie
length) are read from them, never absolute positions.

Model colours: `RailParams` colours go through the renderer's lighting
(`SHADE`, the top-face factor), so the suggested colour is
`observed / SHADE`, which renders back to the observed pixel.
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from tools.threed import crop_ref
from tools.threed.render import (
    ELEV, PIXELS_PER_UNIT, SCREEN_CENTER_X, SCREEN_CENTER_Y_GROUND,
    SUN_DIR, YAW, SquareCamera,
)
from tools.threed.way_verify import DEFAULT_STRAIGHTS


HERE = Path(__file__).resolve().parent

# Top-face brightness factor of `render.render` (ambient + diffuse of a
# +z normal under the sun).
_AMBIENT = SquareCamera().ambient
SHADE = _AMBIENT + (1.0 - _AMBIENT) * max(0.0, float(-SUN_DIR[2]))

# Along-track margin that keeps clear of the cell's cut ends.
ALONG_MAX = 0.42
BIN = 0.01  # perpendicular bin, world units


def _perp_px_per_half_gauge() -> float:
    """Screen pixels, perpendicular to the rail axis, between two rails
    2 world units apart, i.e. per world unit of half-gauge, under the
    square dimetric camera (`render.py`'s YAW, ELEV, PIXELS_PER_UNIT).
    For a rail running along world y the rail pair is displaced along
    world x; the EW case mirrors and lands on the same number."""
    cy, sy = math.cos(-YAW), math.sin(-YAW)
    a = -(math.pi / 2.0 - ELEV)
    ca, sa = math.cos(a), math.sin(a)

    def to_screen(dx, dy, dz):
        x1 = cy * dx - sy * dy
        y1 = sy * dx + cy * dy
        y2 = ca * y1 - sa * dz
        return (x1 * PIXELS_PER_UNIT, -y2 * PIXELS_PER_UNIT)

    axis = to_screen(0.0, 1.0, 0.0)
    axis_len = math.hypot(*axis)
    perp_unit = (-axis[1] / axis_len, axis[0] / axis_len)
    pair = to_screen(2.0, 0.0, 0.0)
    return abs(pair[0] * perp_unit[0] + pair[1] * perp_unit[1])


PERP_PX_PER_HALF_GAUGE = _perp_px_per_half_gauge()


def _ground_grid():
    """World (x, y) of every cell pixel centre, unprojected onto z=0."""
    sy, sx = np.mgrid[0:128, 0:128]
    x1 = (sx + 0.5 - SCREEN_CENTER_X) / PIXELS_PER_UNIT
    y1 = (SCREEN_CENTER_Y_GROUND - (sy + 0.5)) / (
        PIXELS_PER_UNIT * math.cos(-(math.pi / 2.0 - ELEV)))
    return (x1 - y1) / math.sqrt(2.0), (x1 + y1) / math.sqrt(2.0)


GROUND_X, GROUND_Y = _ground_grid()


class Cell:
    """One straight: RGBA pixels plus each pixel's (perp, along) world
    coordinate relative to the track axis."""

    def __init__(self, sheet: Image.Image, row: int, col: int, yaw: float):
        tile = crop_ref.crop_tile(sheet, row, col, crop_ref.DEFAULT_TILE_SIZE)
        tile = crop_ref.mask_transparent(tile, crop_ref.PAK128_TRANSPARENT)
        self.rgba = np.asarray(tile, dtype=np.uint8)
        self.rgb = self.rgba[..., :3].astype(float)
        self.opaque = self.rgba[..., 3] > 0
        # Cell 1.5 runs along world y, cell 1.6 along world x.
        if yaw == 0.0:
            self.perp, self.along = GROUND_X, GROUND_Y
        else:
            self.perp, self.along = GROUND_Y, GROUND_X
        self.lum = self.rgb.mean(axis=2)
        self.in_track = self.opaque & (np.abs(self.along) < ALONG_MAX)


# --- Rails ------------------------------------------------------------------

def _clusters(cell: Cell, min_px: int = 60):
    """Solid-colour clusters: colours within 1 per channel of a seed
    colour merge into it (pak128 dithers some rail colours by one
    step).  Returns [(seed_rgb, mask)] for clusters of at least
    `min_px` pixels."""
    counts = Counter(map(tuple, cell.rgba[cell.opaque][:, :3].tolist()))
    seeds: list[tuple] = []
    totals: list[int] = []
    for colour, n in counts.most_common():
        for i, seed in enumerate(seeds):
            if max(abs(a - b) for a, b in zip(colour, seed)) <= 1:
                totals[i] += n
                break
        else:
            seeds.append(colour)
            totals.append(n)
    out = []
    for seed, total in zip(seeds, totals):
        if total >= min_px:
            near = np.all(np.abs(cell.rgba[..., :3].astype(int)
                                 - np.array(seed)) <= 1, axis=2) & cell.opaque
            out.append((seed, near))
    return out


# Rail pixels sit within this |perp| of the axis (half-gauge 0.047 plus
# the raised rail's unprojection offset); flat colours of the ballast
# (the slab tiers' concrete) spread across the whole tile.
RAIL_ZONE = 0.12


def measure_rails(cell: Cell):
    """Head colour, shadow-line colour, half-gauge, and the mask of all
    rail pixels (head + shadow) for excluding them from other stats."""
    clusters = [c for c in _clusters(cell)
                if (np.abs(cell.perp[c[1]]) < RAIL_ZONE).mean() > 0.9]
    if len(clusters) != 2:
        raise RuntimeError(
            f"expected 2 solid-colour rail clusters, found "
            f"{[c[0] for c in clusters]}")
    clusters.sort(key=lambda c: sum(c[0]))
    (shadow_rgb, shadow_mask), (head_rgb, head_mask) = clusters

    ys, xs = np.where(head_mask)
    A = np.vstack([xs, np.ones_like(xs)]).T
    m_all, b_all = np.linalg.lstsq(A, ys, rcond=None)[0]
    upper = (ys - (m_all * xs + b_all)) < 0
    fits = []
    for sel in (upper, ~upper):
        A = np.vstack([xs[sel], np.ones(sel.sum())]).T
        fits.append(np.linalg.lstsq(A, ys[sel], rcond=None)[0])
    (m_u, b_u), (m_l, b_l) = fits
    if abs(m_u - m_l) > 0.05:
        raise RuntimeError(f"rail slopes diverge: {m_u:.4f} vs {m_l:.4f}")
    m = 0.5 * (m_u + m_l)
    perp_px = abs(b_l - b_u) / math.sqrt(1.0 + m * m)
    return {
        "head_rgb": head_rgb, "shadow_rgb": shadow_rgb,
        "half_gauge": perp_px / PERP_PX_PER_HALF_GAUGE,
        "mask": head_mask | shadow_mask,
    }


# --- Ties -------------------------------------------------------------------

def _two_means(values, iters=20):
    """1-D 2-means seeded at the 15th / 85th percentile."""
    centres = np.percentile(values, [15, 85])
    for _ in range(iters):
        label = np.abs(values[:, None] - centres[None, :]).argmin(axis=1)
        centres = np.array([values[label == k].mean() if (label == k).any()
                            else centres[k] for k in (0, 1)])
    return centres, label


def measure_ties(cell: Cell, rails: np.ndarray):
    """Pitch, tie colour, tie length (full length, perpendicular), and
    the mask of tie-like pixels (for excluding them from ballast)."""
    # Ballast outside the tie ends (0.13..0.19 off the axis) is the
    # reference the tie colour is judged against.
    outside = (cell.in_track & ~rails & (np.abs(cell.perp) >= 0.13)
               & (np.abs(cell.perp) < 0.19))
    ref_lum = float(np.median(cell.lum[outside]))

    strip = cell.in_track & ~rails & (np.abs(cell.perp) < 0.035)
    along, lum = cell.along[strip], cell.lum[strip]
    dev = lum - lum.mean()
    period = max(np.arange(0.04, 0.2, 0.0005), key=lambda per: abs(
        (dev * np.exp(-2j * math.pi * along / per)).sum()))

    centres, label = _two_means(lum)
    k = int(np.argmax(np.abs(centres - ref_lum)))
    tie_rgb = np.median(cell.rgb[strip][label == k], axis=0)

    # Tie-like: luminance nearer the tie cluster than the ballast.
    like = cell.in_track & ~rails & (
        np.abs(cell.lum - centres[k]) < np.abs(cell.lum - ref_lum))
    edges = np.arange(-0.24, 0.2401, BIN * 2)
    centre_bins = (edges[:-1] + edges[1:]) / 2
    dens = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = cell.in_track & ~rails & (cell.perp >= lo) & (cell.perp < hi)
        dens.append(like[sel].mean() if sel.sum() >= 10 else np.nan)
    dens = np.array(dens)
    baseline = np.nanmean(dens[np.abs(centre_bins) > 0.15])
    core = np.nanmean(dens[np.abs(centre_bins) < 0.08])
    # The run of bins around the axis whose density holds at least
    # half-way from the baseline to the core (bins covered by the
    # rails have no data and are crossed).  A run, not every such
    # bin: slab seams outside the ties are dark lines too.
    tie_len = float("nan")
    if core - baseline > 0.15:
        thr = baseline + 0.5 * (core - baseline)
        i0 = int(np.argmin(np.abs(centre_bins)))
        lo_i = hi_i = i0
        while lo_i > 0 and not dens[lo_i - 1] < thr:
            lo_i -= 1
        while hi_i < len(dens) - 1 and not dens[hi_i + 1] < thr:
            hi_i += 1
        tie_len = edges[hi_i + 1] - edges[lo_i]
        zone = (cell.perp >= edges[lo_i]) & (cell.perp < edges[hi_i + 1])
    else:
        zone = np.abs(cell.perp) < 0.1
    return {
        "period": period, "tie_rgb": tie_rgb, "tie_len": tie_len,
        "mask": like & zone,
    }


# --- Ballast ----------------------------------------------------------------

def coverage_profile(cells):
    """Opaque fraction of the pixels at each |perp| bin, both cells and
    both sides pooled.  Rails and ties count as opaque: the model's sit
    on top of the bed, so the bed's own density is read with them in."""
    edges = np.arange(0.0, 0.5001, BIN)
    num = np.zeros(len(edges) - 1)
    den = np.zeros(len(edges) - 1)
    for cell in cells:
        reg = np.abs(cell.along) < ALONG_MAX
        a = np.abs(cell.perp)
        for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
            sel = reg & (a >= lo) & (a < hi)
            num[i] += (sel & cell.opaque).sum()
            den[i] += sel.sum()
    return edges[:-1], num / np.maximum(den, 1)


def _ballast_pixels(cells, rail_masks, tie_masks, lo, hi):
    """RGB of ballast pixels with `lo <= |perp| < hi`: opaque, not a
    rail pixel, not tie-like."""
    px = [cell.rgb[cell.in_track & ~rails & ~ties
                   & (np.abs(cell.perp) >= lo) & (np.abs(cell.perp) < hi)]
          for cell, rails, ties in zip(cells, rail_masks, tie_masks)]
    return np.concatenate(px)


MIN_PX = 30  # fewer ballast pixels than this: no colour estimate
# Slab test.  A concrete slab is nearly one colour (spread = median
# per-pixel max-channel deviation from the median colour, about 4
# against 7+ for gravel), so it is the flat core of the bed out to
# where the spread at least FLAT_JUMPs.
FLAT_SPREAD = 5.5
FLAT_JUMP = 1.6


def _spread(cells, rail_masks, tie_masks, lo, hi):
    px = _ballast_pixels(cells, rail_masks, tie_masks, lo, hi)
    if len(px) < MIN_PX:
        return float("nan")
    return float(np.median(np.abs(px - np.median(px, axis=0)).max(axis=1)))


def _slab_outer(cells, rail_masks, tie_masks, outer):
    """Radius out to which the ballast is a flat-coloured slab, 0.0 if
    it is gravel throughout.  The first 0.06..0.12 off the axis is the
    reference: it has to be flat, then the slab ends where the spread
    over the next 0.04 reaches `FLAT_JUMP` times the core's."""
    core = _spread(cells, rail_masks, tie_masks, 0.06, 0.12)
    if not core <= FLAT_SPREAD:
        return 0.0
    for lo in np.arange(0.12, outer - 0.04 + 1e-9, 0.02):
        if _spread(cells, rail_masks, tie_masks, lo, lo + 0.04) >= FLAT_JUMP * core:
            return float(lo)
    return float(outer)


def _merge(bands, keep_tol=0.03, colour_tol=12):
    """Merge neighbouring bands that agree in density and colour (the
    slab test's edge can fall inside a bed that is slab throughout)."""
    out = [bands[0]]
    for lo, hi, keep, colour in bands[1:]:
        plo, _phi, pkeep, pcolour = out[-1]
        if (abs(keep - pkeep) <= keep_tol
                and sum(abs(a - b) for a, b in zip(colour, pcolour)) <= colour_tol):
            out[-1] = (plo, hi, pkeep, pcolour)
        else:
            out.append((lo, hi, keep, colour))
    return out


def fit_bands(cells, rail_masks, tie_masks, radius, cov):
    """Fit ballast bands `(inner, outer, keep, model_rgb)`.

    Edges.  outer: first radius where coverage falls under 2 % (clamped
    to the entry edge, 0.5).  e1: last radius where coverage is still
    at least 90 % of the core (mean over |perp| < 0.10).  e2: midpoint
    of e1 and outer.  Plus the slab edge, for the slab-track tiers
    (`_slab_outer`).
    keep: mean coverage over the band, so the fitted bed has the
    measured opaque area.
    colour: median ballast pixel colour over the band, as a model
    colour; a band with too few pixels takes its inner neighbour's.
    """
    core = cov[radius < 0.10].mean()
    below = np.where(cov < 0.02)[0]
    outer = float(min(radius[below[0]] if len(below) else 0.5, 0.5))
    solid = np.where((cov >= 0.9 * core) & (radius < outer))[0]
    e1 = float(radius[solid[-1]] + BIN) if len(solid) else 0.0
    edges = {0.0, outer}
    if outer - e1 >= 0.03:
        edges |= {e1, 0.5 * (e1 + outer)}
    slab = _slab_outer(cells, rail_masks, tie_masks, outer)
    if slab >= 0.05:
        edges = {e for e in edges if e >= slab + 0.03 or e == 0.0} | {slab}

    bands = []
    colour = None
    edges = sorted(edges)
    for lo, hi in zip(edges[:-1], edges[1:]):
        px = _ballast_pixels(cells, rail_masks, tie_masks, lo, hi)
        if len(px) >= MIN_PX or colour is None:
            colour = _model(np.median(px, axis=0))
        sel = (radius >= lo - 1e-9) & (radius < hi - 1e-9)
        bands.append((round(lo, 3), round(hi, 3),
                      round(float(cov[sel].mean()), 2), colour))
    return _merge(bands)


# --- Report -----------------------------------------------------------------

def _model(rgb):
    """Observed colour -> model colour (inverse of the top-face shade)."""
    return tuple(int(min(255, round(c / SHADE))) for c in rgb)


def _ints(rgb):
    return tuple(int(round(c)) for c in rgb)


def measure(name: str):
    sheet = Image.open(HERE / f"{name}.png").convert("RGB")
    cells = [Cell(sheet, row, col, yaw)
             for row, col, _name, yaw, _label in DEFAULT_STRAIGHTS]
    rails = [measure_rails(c) for c in cells]
    ties = [measure_ties(c, r["mask"]) for c, r in zip(cells, rails)]
    radius, cov = coverage_profile(cells)
    return cells, rails, ties, radius, cov


def report(name: str):
    cells, rails, ties, radius, cov = measure(name)
    print(f"=== {name} ===")
    for (_r, _c, label, _y, _l), rl, ti in zip(DEFAULT_STRAIGHTS, rails, ties):
        length = (f"{ti['tie_len']:.2f}" if ti["tie_len"] == ti["tie_len"]
                  else "n/a (ties too faint)")
        print(f"  {label}: rail head {_ints(rl['head_rgb'])} shadow "
              f"{_ints(rl['shadow_rgb'])} half-gauge {rl['half_gauge']:.5f}; "
              f"tie {_ints(ti['tie_rgb'])} pitch {ti['period']:.4f} "
              f"length {length}")
    half_gauge = float(np.mean([r["half_gauge"] for r in rails]))
    print(f"  rail_color = {_model(rails[0]['head_rgb'])}  "
          f"rail_gauge_half = {half_gauge:.4f}")
    print(f"  tie_color = {_model(np.mean([t['tie_rgb'] for t in ties], axis=0))}")
    print("  coverage by |perp|, every 0.02: "
          + " ".join(f"{c:.2f}" for c in cov[::2]))
    print("  ballast_bands (inner, outer, keep, color):")
    for band in fit_bands(cells, [r["mask"] for r in rails],
                          [t["mask"] for t in ties], radius, cov):
        print(f"    BallastBand{band},")
    lengths = [t["tie_len"] for t in ties if t["tie_len"] == t["tie_len"]]
    return (half_gauge, float(np.mean(lengths)) if lengths else float("nan"),
            float(np.mean([t["period"] for t in ties])))


def main(argv: list[str]) -> None:
    names = argv or sorted(p.stem for p in HERE.glob("rail_*_tracks.png"))
    print(f"top-face shade {SHADE:.4f}; model colour = observed / shade")
    family = np.array([report(name) for name in names])
    if len(names) > 1:
        lo, hi = np.nanmin(family, axis=0), np.nanmax(family, axis=0)
        print("=== across tiers (min .. max) ===")
        for label, a, b in zip(("half-gauge", "tie length", "tie pitch"), lo, hi):
            print(f"  {label}: {a:.4f} .. {b:.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
