#!/usr/bin/env python3
"""Bake the hex pakset's slope-transition deliverable from `render.py`.

Thin caller of `hex_synth.bake_pakset` — see that helper for the
shared atlas / .dat / argparse skeleton across synth-overlay
families.  Slope-trans is a `(slope, corner_mask)` family like
shore; unlike shore the inner mask isn't constrained to a
slope-dependent subset (climate transitions can in principle hit
any corner), so the iterator yields all 6-bit nonempty masks per
slope — 141 slopes × 63 masks = 8883 cells.

Run:
    python3 build_pakset.py [--w 128] [--cols 12] [--out-dir <dir>]

Re-running this script should produce a byte-identical diff
against the committed PNG/.dat (a future CI check will enforce
that).
"""

from __future__ import annotations

from pathlib import Path

import render
from render import hex_synth


HEADER_DOC = """\
One Image[<slope_t>][<corner_mask>] entry per (slope, corner_mask)
combination realisable on real terrain.  The engine's
`grund.cc::display` builds `climate_corners` by walking each hex
corner and setting bit `ci` when one of the corner's three
vertex-owners is a *higher* climate at the matching vertex height.
A neighbour tile borders the home tile across an *edge* (sharing
both that edge's corners), so a same-climate-band neighbour sets a
2-bit pair in `climate_corners` — and the per-`transition_climate`
partition the engine then runs in `grund.cc:1186-1209` accumulates
exactly the bits whose corner-max climate matches the seed corner's
(corner ci's transition_climate = max(edge[ci-1].climate,
edge[ci].climate); both endpoints of any edge with that climate are
in the same group), so each `overlay_corners` mask passed to
`draw_alpha` is itself a union of edge pairs.  Single-bit (isolated)
masks can't appear on real terrain for the climate path; the bake
omits them.

The snowline path (`get_alpha_tile(slope)` with no caller-supplied
mask) routes through the same table with mask = the slope's high
corners (`corner_height > 0`, since slopes are normalised to
`min(ch) == 0`).  Single-corner-up slopes (and other height
patterns like opposite-corners-up or alternating-corners-up)
produce isolated-bit masks that way — for those slopes
`get_alpha_tile(slope)` resolves to IMG_EMPTY here and the snow
overlay is skipped.  Visible regression vs. the legacy 15-cell
square pakset; tracked as a follow-up — needs either a mask
derivation in the engine that always returns an edge-union (e.g.
expand to include one neighbour bit per isolated corner) or a
per-slope renderer for the snow-only cells separate from the
climate-keyed table.

The .dat indexes by raw `slope_t` (base-4 per corner: E=1, SE=4,
SW=16, W=64, NW=256, NE=1024) and the 6-bit corner mask (E=1,
SE=2, SW=4, W=8, NW=16, NE=32) so the engine's hex-aware climate
lookup can call
`transition_slope_texture->get_image(slope, corner_mask)`
directly.

The atlas stays packed (sequential cell positions); the index
space is sparse — invalid `slope_t` values, the empty mask, and
all isolated-bit masks never appear, and the engine reads them as
IMG_EMPTY.

Sparsity: {n_entries} populated entries out of {n_slots} declared
image slots × 64 mask values.

The engine's `draw_alpha` reads two alpha keys from this same
texture: ALPHA_GREEN | ALPHA_BLUE for full transitions (climate
mixing, case-1 snowline) and ALPHA_BLUE alone for the tighter
case-2 snowline (mid-slope crossing — only the highest mask
region shows snow).  Three colours encode both:

  RED   — alpha=0 under both keys; base climate stays.
  GREEN — opaque under ALPHA_GREEN | ALPHA_BLUE; transparent
          under ALPHA_BLUE alone.
  BLUE  — opaque under both keys (the highest mask region).

A position-deterministic hashed dither at the band boundaries
preserves the gritty soft-edge look of the legacy
`texture-slope.png` rather than collapsing to clean lines.

Per-line comment carries the per-corner height tuple and the
per-corner mask-flag tuple, both as (E SE SW W NW NE).
"""


def _is_edge_union(mask: int, n: int) -> bool:
    """True iff every set bit has at least one set cyclic neighbour mod n.

    Climate-transition masks are unions of 2-bit edge pairs (a
    same-height neighbour with a different climate sets both
    endpoints of the shared edge), so any mask without isolated
    bits is realisable and any mask with an isolated bit is not.
    """
    if mask == 0:
        return False
    for i in range(n):
        if (mask >> i) & 1:
            left  = (mask >> ((i - 1) % n)) & 1
            right = (mask >> ((i + 1) % n)) & 1
            if not (left or right):
                return False
    return True


def _slope_entries(geom):
    """Yield `(slope, corner_mask, render_args, comment)` for every
    realisable slope-trans cell — see HEADER_DOC for the engine
    reasoning behind the predicate.
    """
    n = hex_synth.CORNER_COUNT
    for slope in hex_synth.iter_valid_slopes():
        ch = hex_synth.decode_corner_heights(slope)
        for corner_mask in range(1, 1 << n):
            if not _is_edge_union(corner_mask, n):
                continue
            bits = [(corner_mask >> i) & 1 for i in range(n)]
            comment = (
                f"corners=(E={ch[hex_synth.E]} SE={ch[hex_synth.SE]} "
                f"SW={ch[hex_synth.SW]} W={ch[hex_synth.W_C]} "
                f"NW={ch[hex_synth.NW]} NE={ch[hex_synth.NE]}) "
                f"mask=(E={bits[hex_synth.E]} SE={bits[hex_synth.SE]} "
                f"SW={bits[hex_synth.SW]} W={bits[hex_synth.W_C]} "
                f"NW={bits[hex_synth.NW]} NE={bits[hex_synth.NE]})"
            )
            yield slope, corner_mask, (slope, corner_mask), comment


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="texture-slope",
        obj_name="SlopeTrans",
        header_doc=HEADER_DOC,
        render_cell=lambda slope, corner_mask, geom: render.render_slope(
            slope, corner_mask, geom=geom),
        iter_entries=_slope_entries,
    )
