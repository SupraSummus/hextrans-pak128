#!/usr/bin/env python3
"""Measure rail gauge from a pak128 square-dimetric track sprite by
fitting two parallel lines to the rail-head pixels.

Why this exists: eyeballing "rails look about N pixels apart" mixes up
horizontal screen distance with the perpendicular gauge — they differ
by a factor of √(1 + slope²) for the dimetric projection's diagonal
rails.  This script does the conversion once, against the actual
reference, so `track_params.RAIL_GAUGE_HALF` is set from data rather
than from a sibling asset's calibration.

Pipeline:
  1. Find rail-head pixels by exact RGB match (pak128 rails are a
     single solid colour with no anti-aliasing).
  2. Fit one line through all of them, then split into two clusters
     by sign of residual; refit each.
  3. Verify the two lines are near-parallel; report perpendicular
     distance in screen pixels.
  4. Invert the dimetric projection to recover the world half-gauge.

The conversion factor (`PERP_PX_PER_HALF_GAUGE`) is derived from
`tools/3d/render.py`'s YAW=45°, ELEV=29.5°, PIXELS_PER_UNIT=128/√2,
applied to the rail-pair displacement (Δworld = (2G, 0, 0)) for a
NS-running track; the EW case mirrors and lands on the same number.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

from render import ELEV, PIXELS_PER_UNIT, YAW  # noqa: E402

# Pak128 rail-head colour in `rail_060_tracks.png` cells 1.5 / 1.6.
PAK128_RAIL_RGB = (174, 159, 132)


def _projection_factors():
    """Return (rail_axis_screen_len_per_world_unit,
    perp_screen_px_per_world_half_gauge) for a NS-running rail.

    Square dimetric: world (x,y,z) → screen (sx,sy).  The rail axis is
    +y in world; the gauge displacement is +x in world.  Both project
    to screen vectors whose magnitudes we need to convert px ↔ world.
    """
    cy, sy = math.cos(-YAW), math.sin(-YAW)
    a = -(math.pi / 2.0 - ELEV)
    ca, sa = math.cos(a), math.sin(a)

    def world_to_screen_offset(dx, dy, dz):
        x1 = cy * dx - sy * dy
        y1 = sy * dx + cy * dy
        z1 = dz
        y2 = ca * y1 - sa * z1
        return (x1 * PIXELS_PER_UNIT, -y2 * PIXELS_PER_UNIT)

    rail_axis = world_to_screen_offset(0.0, 1.0, 0.0)
    rail_axis_len = math.hypot(*rail_axis)
    rail_unit = (rail_axis[0] / rail_axis_len, rail_axis[1] / rail_axis_len)
    perp_unit = (-rail_unit[1], rail_unit[0])

    pair_disp = world_to_screen_offset(2.0, 0.0, 0.0)  # rail+ minus rail- per world half-G
    perp_px_per_full_gauge = abs(pair_disp[0] * perp_unit[0]
                                 + pair_disp[1] * perp_unit[1])
    perp_px_per_half_gauge = perp_px_per_full_gauge

    return rail_axis_len, perp_px_per_half_gauge


RAIL_AXIS_PX_PER_UNIT, PERP_PX_PER_HALF_GAUGE = _projection_factors()


def measure(png_path: Path, rail_rgb=PAK128_RAIL_RGB):
    img = np.array(Image.open(png_path).convert("RGBA"))
    r, g, b, a = (img[:, :, i] for i in range(4))
    mask = (a > 0) & (r == rail_rgb[0]) & (g == rail_rgb[1]) & (b == rail_rgb[2])
    ys, xs = np.where(mask)
    if len(xs) < 10:
        raise RuntimeError(
            f"{png_path.name}: only {len(xs)} rail-coloured pixels — "
            f"check rail_rgb={rail_rgb}.")

    A = np.vstack([xs, np.ones_like(xs)]).T
    m_all, b_all = np.linalg.lstsq(A, ys, rcond=None)[0]
    res = ys - (m_all * xs + b_all)
    upper = res < 0
    lower = ~upper

    fits = {}
    for label, sel in (("upper", upper), ("lower", lower)):
        xx, yy = xs[sel], ys[sel]
        A = np.vstack([xx, np.ones_like(xx)]).T
        m, b = np.linalg.lstsq(A, yy, rcond=None)[0]
        fits[label] = (m, b, len(xx))

    m_u, b_u, n_u = fits["upper"]
    m_l, b_l, n_l = fits["lower"]
    if abs(m_u - m_l) > 0.05:
        raise RuntimeError(
            f"{png_path.name}: rail slopes diverge: {m_u:.4f} vs {m_l:.4f}.")
    m = 0.5 * (m_u + m_l)
    perp_px = abs(b_l - b_u) / math.sqrt(1.0 + m * m)
    half_gauge_world = perp_px / PERP_PX_PER_HALF_GAUGE
    return {
        "n_pixels": len(xs),
        "slope_upper": m_u, "intercept_upper": b_u, "n_upper": n_u,
        "slope_lower": m_l, "intercept_lower": b_l, "n_lower": n_l,
        "perp_px": perp_px,
        "half_gauge_world": half_gauge_world,
    }


def main():
    print(f"projection: rail_axis_px_per_unit={RAIL_AXIS_PX_PER_UNIT:.3f}, "
          f"perp_px_per_half_gauge={PERP_PX_PER_HALF_GAUGE:.3f}")
    print()
    targets = [
        ("NS (cell 1.5)", HERE / "refs" / "square_ns.png"),
        ("EW (cell 1.6)", HERE / "refs" / "square_ew.png"),
    ]
    halves = []
    for label, path in targets:
        if not path.exists():
            print(f"{label}: missing {path} — run build.py to crop refs first.")
            continue
        m = measure(path)
        print(f"=== {label} ===")
        print(f"  upper: slope={m['slope_upper']:+.4f} intercept={m['intercept_upper']:.3f} (n={m['n_upper']})")
        print(f"  lower: slope={m['slope_lower']:+.4f} intercept={m['intercept_lower']:.3f} (n={m['n_lower']})")
        print(f"  perp distance (px): {m['perp_px']:.3f}")
        print(f"  → world half-gauge: {m['half_gauge_world']:.5f}")
        halves.append(m["half_gauge_world"])
    if halves:
        mean = sum(halves) / len(halves)
        print()
        print(f"mean half-gauge across {len(halves)} cells: {mean:.5f}")
        print(f"suggested RAIL_GAUGE_HALF = {mean:.4f}")


if __name__ == "__main__":
    main()
