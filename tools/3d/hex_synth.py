"""Shared utilities for the parametric hex synth pipeline.

Mirror of the engine's `descriptor/synth_geometry.h` +
`descriptor/synth_plane_partition.h` — the per-slope geometry,
per-region plane partition, and polygon fill conventions used by the
engine's `synth_overlay::*` ground truth.  Keeping a single Python copy
here means the per-asset bakers (lightmap, borders, marker, alpha,
back_wall) all share one definition of "what is a hex slope" and one
implementation of the integer math the engine bakes into its PIXVAL
buffers.

Asset-specific renderers (per-region Lambert shading for the lightmap,
6-edge outline for borders, …) live next to the asset they bake; this
module only carries what's universal across them.

An earlier crash-fast probe validated bit-for-bit that the lightmap
renderer reproduces the engine's flat-tile output across all 8
climates, so the constants here (`HexGeom`, `LIGHT`, fill convention)
are known reproducible.  Border / marker / alpha bakers reuse the same
geometry without re-validating each time.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np


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


# ---- Hex corner indices (matching `hex_corner_t::type` in dataobj/ribi.h) --

E, SE, SW, W_C, NW, NE = 0, 1, 2, 3, 4, 5
CORNER_COUNT = 6

# Raw slope_t per-corner weights.  `slope = sum(ch[i] * CORNER_WEIGHTS[i])`.
CORNER_WEIGHTS = (1, 4, 16, 64, 256, 1024)


def decode_corner_heights(slope: int) -> list[int]:
    return [(slope // CORNER_WEIGHTS[i]) % 4 for i in range(CORNER_COUNT)]


# ---- synth_hex_geometry replication (from synth_geometry.h) ---------------

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

    def lifted_vy(self, slope: int) -> list[int]:
        """All 6 corner screen-y values for `slope`, with corner lift applied.

        Y grows down; corner height lifts UP, so subtract `ch[i]*lift`.
        Single decode of `slope` into corner heights, vs. one decode per
        `vy(slope, corner)` call — the loop callers in
        `synth_overlay.cc::rasterise_outline` and `_per_region_brightness`
        both want the full vector, not one corner at a time.
        """
        ch = decode_corner_heights(slope)
        return [self.vy_base[i] - ch[i] * self.lift for i in range(CORNER_COUNT)]


# Canonical corner traversal paths matching `synth_overlay.cc`:
#
#   FULL_PATH  — closed 6-edge hex outline (engine debug-grid).
#   BACK_PATH  — open polyline of the 3 north-side edges
#                (E → NE → NW → W).  Pakset border + marker back-half.
#   FRONT_PATH — open polyline of the 3 south-side edges
#                (E → SE → SW → W).  Marker front-half.
#
# Each shared edge is owned by exactly one tile under the BACK_PATH
# convention (this tile's NW edge = the NW neighbour's SE edge in
# their FRONT, etc.), so painting BACK_PATH per tile across the world
# covers every grid line once.  Square pak128 `borders.png` uses the
# same single-side convention, just rotated for the square topology.
HEX_FULL_PATH  = (E, SE, SW, W_C, NW, NE)
HEX_BACK_PATH  = (E, NE, NW, W_C)
HEX_FRONT_PATH = (E, SE, SW, W_C)


# ---- Slope validity -------------------------------------------------------

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


# ---- Plane partitioning (from synth_plane_partition.h) --------------------
#
# The hex tile is partitioned into the **fewest** coplanar polygonal
# regions; ties broken by maximum projected area of horizontal regions
# (so saddles pick the partition that keeps the most "flat ground").
# Each region then gets one Lambert face normal in renderers that care
# about per-region shading.

# 9 candidate chords between non-adjacent hex corners.
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


# ---- Polygon fill (independent re-implementation of synth_overlay.cc) -----

def fill_polygon(buf: np.ndarray, xs: list[int], ys: list[int],
                 color_rgb: tuple[int, int, int]):
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
            if y < y_lo or y >= y_hi:
                continue
            xa, xb = xs[i], xs[j]
            num = (y - ya) * (xb - xa)
            den = (yb - ya)
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


def seal_horizontal_edges(buf: np.ndarray, xs: list[int], ys: list[int],
                          color_rgb: tuple[int, int, int]):
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


# ---- Line drawing (from synth_overlay.cc draw_line) -----------------------

def draw_line(buf: np.ndarray, x0: int, y0: int, x1: int, y1: int,
              color_rgb: tuple[int, int, int]):
    """Bresenham line into an HxWx4 RGBA buffer with full-alpha output.

    Mirrors `synth_overlay.cc::draw_line` — same dy negation trick and
    same `2*err` step decisions, so two callers (engine and bake) lay
    pixels along identical integer paths.
    """
    h, w, _ = buf.shape
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= x0 < w and 0 <= y0 < h:
            buf[y0, x0, 0] = color_rgb[0]
            buf[y0, x0, 1] = color_rgb[1]
            buf[y0, x0, 2] = color_rgb[2]
            buf[y0, x0, 3] = 255
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def rasterise_outline(buf: np.ndarray, geom: HexGeom, slope: int,
                      path, color_rgb: tuple[int, int, int],
                      closed: bool):
    """Walk `path` (a sequence of corner indices), drawing each edge
    via `draw_line` at the slope's lifted vertices.  Mirrors
    `synth_overlay.cc::rasterise_outline`'s edge loop.
    """
    vy = geom.lifted_vy(slope)
    n_edges = len(path) if closed else len(path) - 1
    for i in range(n_edges):
        a = path[i]
        b = path[(i + 1) % len(path)]
        draw_line(buf, geom.vx[a], vy[a], geom.vx[b], vy[b], color_rgb)


# ---- Atlas + bake helpers -------------------------------------------------

def _build_atlas(geom: HexGeom, cols: int, halves: int, render_cell):
    """Bake a packed atlas of `halves` cells per valid slope.

    Cells are written half-major: all `half=0` cells in
    `iter_valid_slopes()` order, then all `half=1` cells in the same
    order, etc.  Sparsity lives in the .dat (raw `slope_t` index →
    atlas cell), not in the PNG.  `render_cell(slope, half, geom)`
    returns an HxWx4 RGBA array sized `(geom.h, geom.w)`.

    Returns `(atlas_rgba, layout, rows)` where `layout` is the
    `[(slope, half, row, col), …]` list in pakset emission order.
    """
    valid = list(iter_valid_slopes())
    n_total = len(valid) * halves
    rows = (n_total + cols - 1) // cols
    cell_w, cell_h = geom.w, geom.h
    atlas = np.zeros((rows * cell_h, cols * cell_w, 4), dtype=np.uint8)
    layout: list[tuple[int, int, int, int]] = []
    idx = 0
    for half in range(halves):
        for slope in valid:
            r, c = divmod(idx, cols)
            cell = render_cell(slope, half, geom)
            atlas[r * cell_h:(r + 1) * cell_h, c * cell_w:(c + 1) * cell_w] = cell
            layout.append((slope, half, r, c))
            idx += 1
    return atlas, layout, rows


def _write_dat(path: Path, layout, rows: int, cols: int,
               asset_name: str, obj_name: str, header_doc: str,
               halves: int):
    valid_slopes = sorted({slope for slope, *_ in layout})
    n_entries = len(valid_slopes)
    max_slope = max(valid_slopes)
    n_slots = max_slope + 1

    doc_body = header_doc.format(
        n_entries=n_entries,
        n_slots=n_slots,
        halves=halves,
    ).rstrip("\n")
    doc_lines = [(f"# {ln}" if ln else "#") for ln in doc_body.split("\n")]

    lines = [
        "#",
        f"# Generated by landscape/grounds/{asset_name}/build_pakset.py from render.py.",
        "# Do not edit by hand — regenerate after changing the canonical renderer.",
        "#",
        *doc_lines,
        "#",
        "Obj=ground",
        f"Name={obj_name}",
        "",
        f"# atlas: {cols} cols x {rows} rows, cells named {asset_name}.<row>.<col>",
        "",
    ]
    for slope, half, r, c in layout:
        ch = decode_corner_heights(slope)
        side = "" if halves == 1 else ("front " if half == 0 else "back ")
        idx_axis = "0" if halves == 1 else str(half)
        lines.append(
            f"Image[{slope}][{idx_axis}]={asset_name}.{r}.{c}\t"
            f"# {side}corners=(E={ch[E]} SE={ch[SE]} "
            f"SW={ch[SW]} W={ch[W_C]} NW={ch[NW]} NE={ch[NE]})"
        )
    lines.append("")
    path.write_text("\n".join(lines))


def bake_pakset(*, script_path: Path, asset_name: str, obj_name: str,
                header_doc: str, render_cell, halves: int = 1,
                default_cols: int = 12, argv=None):
    """Run argparse, bake atlas + .dat for one synth-overlay family.

    Each per-asset `build_pakset.py` shrinks to a single call to this
    helper plus its asset-specific `HEADER_DOC` template and
    `render_cell` callback.  Common boilerplate (CLI, output-dir
    resolution, atlas write, dat write loop, per-line corner comment,
    stderr summary) lives here.

    Args:
        script_path: caller's `Path(__file__).resolve()`.  Used to
            derive the default `--out-dir` (one level up — the parent
            `landscape/grounds/` directory) and the relative path
            shown in the stderr summary.
        asset_name: filename basename for the deliverable
            (`borders`, `marker`, `texture-hex-lightmap`, …).  Doubles
            as the source-dir name (`script_path.parent.name`); the
            two are required to match by the co-location convention.
        obj_name: pakset `Name=…` field
            (`Borders`, `Marker`, `LightTexture`, …).
        header_doc: per-asset doc paragraph for the .dat header,
            inserted between the auto-generated boilerplate and
            `Obj=ground`.  Each input line gets a `# ` prefix; blank
            lines become `#`.  The string is `.format()`-substituted
            with `n_entries`, `n_slots`, and `halves` available.
        render_cell: `callable(slope, half, geom) -> HxWx4 ndarray`.
            For `halves=1` the `half` arg is always `0`; for
            `halves=2` it is `0` (front) or `1` (back).
        halves: 1 or 2.  Marker uses 2 (front + back); everything
            else is 1.
    """
    assert script_path.parent.name == asset_name, (
        f"script lives in {script_path.parent.name!r} but asset_name is "
        f"{asset_name!r}; co-location convention requires they match"
    )

    p = argparse.ArgumentParser()
    p.add_argument("--w", type=int, default=DEFAULT_W,
                   help=f"raster tile width (default {DEFAULT_W})")
    p.add_argument("--cols", type=int, default=default_cols,
                   help=f"atlas columns (default {default_cols})")
    p.add_argument("--out-dir", type=Path, default=script_path.parent.parent,
                   help="output directory (default <repo>/landscape/grounds/)")
    args = p.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    geom = HexGeom(raster_w=args.w)
    atlas, layout, rows = _build_atlas(geom, args.cols, halves, render_cell)

    png_path = args.out_dir / f"{asset_name}.png"
    dat_path = args.out_dir / f"{asset_name}.dat"
    from PIL import Image
    Image.fromarray(atlas, mode="RGBA").save(str(png_path))
    _write_dat(dat_path, layout, rows, args.cols, asset_name, obj_name,
               header_doc, halves)

    rel_root = script_path.parents[3]
    n = len(layout)
    print(f"build_pakset.py: wrote {n} cells into "
          f"{png_path.relative_to(rel_root)} "
          f"({args.cols}x{rows} atlas, {atlas.shape[1]}x{atlas.shape[0]} px)",
          file=sys.stderr)
    print(f"build_pakset.py: wrote .dat with {n} entries -> "
          f"{dat_path.relative_to(rel_root)}",
          file=sys.stderr)
