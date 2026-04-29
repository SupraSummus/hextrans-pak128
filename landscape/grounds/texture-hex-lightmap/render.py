#!/usr/bin/env python3
"""Canonical renderer for the hex ground pakset's lightmap cells.

The pakset deliverable splits per-tile geometry from per-climate biome
art exactly the way pak128 does: a grayscale lightmap PNG carries the
hex silhouette and the per-region Lambert shading; pak128's existing
`texture-climate.png` carries the biome colours unchanged.  At runtime
the engine multiplies the two via `create_textured_tile`, so we never
need to bake climate colours into a candidate render — only the
lightmap.

An earlier crash-fast probe validated bit-for-bit that this renderer
reproduces the engine's `synth_overlay::rasterise_ground` flat-tile
output across all 8 climates, so we trust the documented constants in
`synth_geometry.h` (vertex layout, lift, light direction, shade math,
fill convention).  Going forward this script *is* the canonical source
of truth for the hex ground deliverable; the engine's in-process synth
path is just a runtime fallback floor.

Per-region shading uses a Python port of
`synth_plane_partition.h::find_min_partition` so multi-region slopes
(saddles, wedges) get one Lambert face per coplanar region rather than
a single average shade.

Usage:
    render.py <slope> <out.png>          # one lightmap cell
    build_pakset.py                      # bake the full 340-cell atlas
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ---- Engine constants (from `src/simutrans/descriptor/synth_geometry.h`) ----

# pak128 raster width.  `u = W/4` is the natural lattice unit.  At
# height_step=16 this gives a 128x128 hex bbox that drops into the
# pakset's 128x128 cell layout without padding.  Override via --w when
# producing pak64 (W=64) or other sizes.
DEFAULT_W = 128
HEIGHT_STEP = 16  # env_t::pak_tile_height_step at runtime; 16 for pak64/pak128


def tile_raster_scale_y(v: int, rh: int) -> int:
    # `simconst.h`: `tile_raster_scale_y(v, rh)   (((v)*(rh)) >> 6)`
    return (v * rh) >> 6


def hex_height_raster_scale_y(height_steps: int, w: int) -> int:
    # `display/hex_proj.h`: half the legacy lift so base-elevation and
    # per-corner relief stay in the same projection.
    return tile_raster_scale_y(height_steps, w) // 2


# ---- synth_hex_geometry replication (from synth_geometry.h) ----------------

# Hex corner indices (matching `hex_corner_t::type` in dataobj/ribi.h).
E, SE, SW, W_C, NW, NE = 0, 1, 2, 3, 4, 5
CORNER_COUNT = 6


class HexGeom:
    """The output of `synth_overlay::synth_hex_geometry(u, height_step)`.

    Mirrors the C++ struct field for field — kept verbose rather than
    folded into a function so the call sites read like the engine's.
    """

    def __init__(self, raster_w: int = DEFAULT_W, height_step: int = HEIGHT_STEP):
        u = raster_w // 4
        self.u = u
        self.w = 4 * u
        self.lift = hex_height_raster_scale_y(height_step, self.w)
        self.top_pad = 4 * self.lift
        self.h = 2 * u + self.top_pad
        self.top_y = self.top_pad
        self.mid_y = self.top_pad + u
        self.bot_y = self.top_pad + 2 * u - 1

        # Vertex screen X (independent of slope) and Y baseline (no lift).
        self.vx = [0] * CORNER_COUNT
        self.vy_base = [0] * CORNER_COUNT
        self.vx[E ] = self.w - 1; self.vy_base[E ] = self.mid_y
        self.vx[SE] = 3 * u;      self.vy_base[SE] = self.bot_y
        self.vx[SW] = u;          self.vy_base[SW] = self.bot_y
        self.vx[W_C] = 0;         self.vy_base[W_C] = self.mid_y
        self.vx[NW] = u;          self.vy_base[NW] = self.top_y
        self.vx[NE] = 3 * u;      self.vy_base[NE] = self.top_y


# ---- Slope decoding (from dataobj/ribi.h) ---------------------------------
#
# Hex slopes are base-4 per corner; 6 corners; total 4^6 = 4096 indices.
# Per-corner weights from `ribi.h`'s slope_t:
#   E  weight 1   (4^0)
#   SE weight 4
#   SW weight 16
#   W  weight 64
#   NW weight 256
#   NE weight 1024
# A slope value `s` decodes to corner heights `(s / weight) % 4`.

CORNER_WEIGHTS = (1, 4, 16, 64, 256, 1024)


def decode_corner_heights(slope: int) -> list[int]:
    return [(slope // CORNER_WEIGHTS[i]) % 4 for i in range(CORNER_COUNT)]


# ---- Lambert lighting (from synth_geometry.h) -----------------------------
#
# Light `L = (-1, 1, 2)`, calibrated against the flat tile so flat = 1.0×
# and only deviations from the flat plane produce highlights/shadows.
# Brightness lives in [128, 352] (= 0.5× .. 1.375×).

LIGHT = (-1.0, 1.0, 2.0)


def lambert_brightness(nx: float, ny: float, nz: float) -> int:
    Lx, Ly, Lz = LIGHT
    L_norm = math.sqrt(Lx * Lx + Ly * Ly + Lz * Lz)
    flat_cos = Lz / L_norm

    n_norm = math.sqrt(nx * nx + ny * ny + nz * nz)
    if n_norm <= 0.0:
        return 256
    cos_theta = (nx * Lx + ny * Ly + nz * Lz) / (n_norm * L_norm)
    brightness = 256 + int((cos_theta - flat_cos) * 384.0)
    if brightness < 128:
        brightness = 128
    if brightness > 352:
        brightness = 352
    return brightness


# ---- Plane partitioning ---------------------------------------------------
#
# Port of `synth_plane_partition.h::find_min_partition`.  The hex tile
# is partitioned into the **fewest** coplanar polygonal regions; ties
# broken by maximum projected area of horizontal regions (so saddles
# pick the partition that keeps the most "flat ground").  Each region
# then gets one Lambert face normal in the renderer, so a multi-region
# slope reads as multiple shaded planes rather than a single average.

# 9 candidate chords between non-adjacent hex corners
# (corner indices: E=0, SE=1, SW=2, W=3, NW=4, NE=5).
HEX_ALL_CHORDS = [
    (0, 2), (0, 3), (0, 4),
    (1, 3), (1, 4), (1, 5),
    (2, 4), (2, 5), (3, 5),
]

# Top-down projected (x, y) for each corner — used by the coplanarity
# determinant and the flat-area tiebreak.  Identical to the engine
# constants in `synth_plane_partition.h`.
HEX_CORNER_PROJECTED_X = [ 1,  0, -1, -1,  0,  1]
HEX_CORNER_PROJECTED_Y = [ 0,  1,  1,  0, -1, -1]


def _chords_cross(c1, c2) -> bool:
    a, b = sorted(c1)
    c, d = sorted(c2)
    return (a < c < b < d) or (c < a < d < b)


def _compute_regions_from_chord_mask(mask: int):
    """Apply each set chord; split the region containing both endpoints
    into two.  Return list of regions, or None if the mask exceeds the
    4-region cap or a region exceeds 6 vertices."""
    regions: list[list[int]] = [[0, 1, 2, 3, 4, 5]]
    for ci in range(9):
        if not (mask & (1 << ci)):
            continue
        a, b = HEX_ALL_CHORDS[ci]
        split_idx = -1
        for ri, reg in enumerate(regions):
            if a in reg and b in reg:
                split_idx = ri
                break
        if split_idx < 0 or len(regions) >= 4:
            return None
        reg = regions[split_idx]
        ai = reg.index(a)
        bi = reg.index(b)
        s = min(ai, bi)
        e = max(ai, bi)
        # Match the engine: r1 walks s..e inclusive, r2 wraps e..len-1 then 0..s
        # so each split vertex is shared by both regions.
        r1 = reg[s:e + 1]
        r2 = reg[e:] + reg[:s + 1]
        if len(r1) > CORNER_COUNT or len(r2) > CORNER_COUNT:
            return None
        regions[split_idx] = r1
        regions.append(r2)
    return regions


def _region_coplanar(region: list[int], ch: list[int]) -> bool:
    n = len(region)
    if n <= 3:
        return True
    # Every set of 4 vertices must be coplanar in 3D — det of the
    # three edge vectors from one anchor must be zero.
    for a in range(n):
        for b in range(a + 1, n):
            for c in range(b + 1, n):
                for d in range(c + 1, n):
                    ia, ib, ic, id_ = region[a], region[b], region[c], region[d]
                    v1x = HEX_CORNER_PROJECTED_X[ib] - HEX_CORNER_PROJECTED_X[ia]
                    v1y = HEX_CORNER_PROJECTED_Y[ib] - HEX_CORNER_PROJECTED_Y[ia]
                    v1z = ch[ib] - ch[ia]
                    v2x = HEX_CORNER_PROJECTED_X[ic] - HEX_CORNER_PROJECTED_X[ia]
                    v2y = HEX_CORNER_PROJECTED_Y[ic] - HEX_CORNER_PROJECTED_Y[ia]
                    v2z = ch[ic] - ch[ia]
                    v3x = HEX_CORNER_PROJECTED_X[id_] - HEX_CORNER_PROJECTED_X[ia]
                    v3y = HEX_CORNER_PROJECTED_Y[id_] - HEX_CORNER_PROJECTED_Y[ia]
                    v3z = ch[id_] - ch[ia]
                    det = (v1x * (v2y * v3z - v2z * v3y)
                           - v1y * (v2x * v3z - v2z * v3x)
                           + v1z * (v2x * v3y - v2y * v3x))
                    if det != 0:
                        return False
    return True


def _region_flat_horizontal(region: list[int], ch: list[int]) -> bool:
    return all(ch[v] == ch[region[0]] for v in region)


def _region_projected_area2(region: list[int]) -> int:
    a2 = 0
    n = len(region)
    for i in range(n):
        j = (i + 1) % n
        a2 += (HEX_CORNER_PROJECTED_X[region[i]] * HEX_CORNER_PROJECTED_Y[region[j]]
               - HEX_CORNER_PROJECTED_X[region[j]] * HEX_CORNER_PROJECTED_Y[region[i]])
    return abs(a2)


def find_min_partition(slope: int) -> list[list[int]]:
    """Return the engine-equivalent minimum-region partition for a slope.

    Falls back to a single-region cover only if no valid partition is
    found (which shouldn't happen for any valid slope, but keeps the
    renderer well-defined if a future encoding produces one).
    """
    ch = decode_corner_heights(slope)
    best: list[list[int]] | None = None
    best_count = CORNER_COUNT + 1
    best_flat_area = -1

    for mask in range(1 << 9):
        chords_set = [HEX_ALL_CHORDS[i] for i in range(9) if mask & (1 << i)]
        ok = True
        for i in range(len(chords_set)):
            for j in range(i + 1, len(chords_set)):
                if _chords_cross(chords_set[i], chords_set[j]):
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            continue

        cand = _compute_regions_from_chord_mask(mask)
        if cand is None:
            continue
        if not all(_region_coplanar(r, ch) for r in cand):
            continue

        flat_area = sum(_region_projected_area2(r)
                        for r in cand if _region_flat_horizontal(r, ch))
        if (len(cand) < best_count
                or (len(cand) == best_count and flat_area > best_flat_area)):
            best = cand
            best_count = len(cand)
            best_flat_area = flat_area
            if best_count == 1:
                break

    return best if best is not None else [[0, 1, 2, 3, 4, 5]]


def trivial_partition() -> list[list[int]]:
    """Single-region cover used as a no-op partition (e.g. for callers
    that don't care about per-region shading).  `find_min_partition` is
    the right call for canonical pakset output."""
    return [[E, SE, SW, W_C, NW, NE]]


# ---- Polygon fill (independent implementation) ----------------------------

def fill_polygon(buf: np.ndarray, xs: list[int], ys: list[int], color_rgb: tuple[int, int, int]):
    """Even-odd half-open scanline fill into an HxWx4 RGBA buffer.

    Independent re-implementation — not copied from synth_overlay.cc.  The
    crash-fast question is whether two from-scratch fills produce the
    same pixels under the same vertices and conventions.
    """
    h, w, _ = buf.shape
    n = len(xs)
    y_min = max(0, min(ys))
    y_max = min(h - 1, max(ys))

    for y in range(y_min, y_max + 1):
        xints: list[int] = []
        for i in range(n):
            j = (i + 1) % n
            ya, yb = ys[i], ys[j]
            if ya == yb:
                continue  # skip horizontal edges (parity)
            y_lo = min(ya, yb)
            y_hi = max(ya, yb)
            # Half-open [y_lo, y_hi)
            if y < y_lo or y >= y_hi:
                continue
            xa, xb = xs[i], xs[j]
            # Match engine integer math: `xa + (y-ya)*(xb-xa) / (yb-ya)`
            # with C-style truncation toward zero.
            num = (y - ya) * (xb - xa)
            den = (yb - ya)
            # Python `//` floors; emulate C truncation.
            q = abs(num) // abs(den)
            if (num < 0) ^ (den < 0):
                q = -q
            xints.append(xa + q)
        xints.sort()
        for k in range(0, len(xints) - 1, 2):
            x0 = max(0, xints[k])
            x1 = min(w - 1, xints[k + 1])
            if x0 <= x1:
                buf[y, x0:x1 + 1, 0] = color_rgb[0]
                buf[y, x0:x1 + 1, 1] = color_rgb[1]
                buf[y, x0:x1 + 1, 2] = color_rgb[2]
                buf[y, x0:x1 + 1, 3] = 255


def seal_horizontal_edges(buf: np.ndarray, xs: list[int], ys: list[int], color_rgb: tuple[int, int, int]):
    """Fill horizontal polygon edges that the parity scanline skips."""
    h, w, _ = buf.shape
    n = len(xs)
    for i in range(n):
        j = (i + 1) % n
        if ys[i] != ys[j]:
            continue
        y = ys[i]
        if y < 0 or y >= h:
            continue
        x0 = min(xs[i], xs[j])
        x1 = max(xs[i], xs[j])
        x0 = max(0, x0)
        x1 = min(w - 1, x1)
        buf[y, x0:x1 + 1, 0] = color_rgb[0]
        buf[y, x0:x1 + 1, 1] = color_rgb[1]
        buf[y, x0:x1 + 1, 2] = color_rgb[2]
        buf[y, x0:x1 + 1, 3] = 255


# ---- Top-level renderer ---------------------------------------------------

def slope_is_valid(slope: int) -> bool:
    """Whether a raw slope_t encoding is a normalised pakset slope.

    Two constraints:

    * **Per-edge delta ≤ 1.** The constraint `synth_overlay::init`
      enforces — slopes with a steeper jump can't appear on real
      terrain.

    * **min(corner_heights) == 0.** Base elevation lives in the tile's
      `hgt` field, not in the slope encoding, so e.g. (1,1,1,0,0,0)
      and (2,2,2,1,1,1) describe the same shape at different absolute
      heights.  The pakset only emits one cell per shape; the engine's
      hex-aware ground lookup is responsible for normalising
      `slope_t` → `slope_t - min(ch)` before indexing the atlas.

    Yields 141 distinct shapes out of 4096 raw slope_t values.
    """
    ch = decode_corner_heights(slope)
    if min(ch) != 0:
        return False
    for i in range(CORNER_COUNT):
        j = (i + 1) % CORNER_COUNT
        if ch[i] > ch[j] + 1 or ch[j] > ch[i] + 1:
            return False
    return True


def iter_valid_slopes():
    for slope in range(4096):
        if slope_is_valid(slope):
            yield slope


def _per_region_brightness(slope: int, geom: HexGeom, partition: list[list[int]]):
    """Yield (region, brightness) for each region in the partition.

    Pulled out of `render_ground` so the lightmap path reuses the same
    Lambert math without recomputing.
    """
    ch = decode_corner_heights(slope)
    vy = [geom.vy_base[i] - ch[i] * geom.lift for i in range(CORNER_COUNT)]

    for region in partition:
        if len(region) < 3:
            continue
        i0 = region[0]
        nx_v = ny_v = nz_v = 0.0
        have_normal = False
        for k in range(2, len(region)):
            i1 = region[k - 1]
            i2 = region[k]
            ax = geom.vx[i1] - geom.vx[i0]
            ay = vy[i1] - vy[i0]
            az = (ch[i1] - ch[i0]) * geom.lift
            bx = geom.vx[i2] - geom.vx[i0]
            by = vy[i2] - vy[i0]
            bz = (ch[i2] - ch[i0]) * geom.lift
            nx_v = ay * bz - az * by
            ny_v = az * bx - ax * bz
            nz_v = ax * by - ay * bx
            if nx_v != 0.0 or ny_v != 0.0 or nz_v != 0.0:
                have_normal = True
                break
        if not have_normal:
            nx_v, ny_v, nz_v = 0.0, 0.0, 1.0
        if nz_v < 0.0:
            nx_v, ny_v, nz_v = -nx_v, -ny_v, -nz_v

        brightness = lambert_brightness(nx_v, ny_v, nz_v)
        xs = [geom.vx[i] for i in region]
        ys = [vy[i] for i in region]
        yield region, xs, ys, brightness


def render_lightmap(slope: int, geom: HexGeom | None = None,
                    partition: list[list[int]] | None = None) -> np.ndarray:
    """Render one slope's lightmap cell.

    Per-region grayscale = `brightness/16` (5-bit), expanded to RGB8
    with the same `(c5*255+15)/31` rounding the engine uses.  Brightness
    256 (1.0×) lands at 5-bit value 16, RGB8 ~132 — matches pak128's
    identity-multiplier convention so `create_textured_tile` returns the
    biome texture unchanged on flat tiles.

    Hex shape is carried in the alpha channel (255 inside, 0 outside).
    The engine's `create_textured_tile` walks the lightmap RLE, so the
    transparent border becomes the implicit hex mask in the final
    composited tile.
    """
    if geom is None:
        geom = HexGeom()
    if partition is None:
        partition = find_min_partition(slope)

    buf = np.zeros((geom.h, geom.w, 4), dtype=np.uint8)
    for _region, xs, ys, brightness in _per_region_brightness(slope, geom, partition):
        gray5 = brightness // 16
        if gray5 > 31:
            gray5 = 31
        gray8 = (gray5 * 255 + 15) // 31
        face_rgb = (gray8, gray8, gray8)
        fill_polygon(buf, xs, ys, face_rgb)
        seal_horizontal_edges(buf, xs, ys, face_rgb)

    return buf


def save_rgba(buf: np.ndarray, path: Path):
    Image.fromarray(buf, mode="RGBA").save(str(path))


def main():
    p = argparse.ArgumentParser(description="Render one hex slope as a grayscale "
                                            "lightmap cell.")
    p.add_argument("slope", type=int, help="raw slope_t index (0..4095)")
    p.add_argument("out", type=Path, help="output PNG path")
    p.add_argument("--w", type=int, default=DEFAULT_W,
                   help=f"raster tile width (default {DEFAULT_W})")
    args = p.parse_args()

    geom = HexGeom(raster_w=args.w)
    save_rgba(render_lightmap(args.slope, geom=geom), args.out)


if __name__ == "__main__":
    main()
