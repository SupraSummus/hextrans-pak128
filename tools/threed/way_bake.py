"""Shared baker for hex way-asset atlases.

Every hex way asset (rail tracks, roads, future trams) emits the same
three atlases — flat ribi cells, axis-slope crossings, half-slope
stubs — and uses the same chord/caps frame machinery from
`way_topology.py`.  This module is the single bake entry point that
threads a `CrossSection` through `for_edges_paths` / `lay_axis_slope`
/ `lay_axis_slope_half` and writes the three PNGs.

Caller responsibility shrinks to: define a `CrossSection`, point at
an output dir, declare whether the tier has `has_double_slopes`.
The pakset's `.dat` keys map onto the cells this writer lays down;
they're not encoded here — see `descriptor/way_image_keys::slope_slot_keys`
on the engine side for the contract.
"""
from __future__ import annotations

from pathlib import Path

from . import way_topology as wt
from .bespoke import bake_atlas
from .render import HexCamera, Model, render
from .way import (
    HEX_ENTRIES,
    SLOPE_HEX_DOUBLE_ENTRIES,
    SLOPE_HEX_ENTRIES,
    SLOPE_HEX_HALF_DOUBLE_ENTRIES,
    SLOPE_HEX_HALF_ENTRIES,
)


def _render_flat(cs: wt.CrossSection, edges):
    m = Model()
    cs.paint(m, wt.for_edges_paths(edges))
    return render(m, HexCamera())


def _render_slope(cs: wt.CrossSection, low_edge: str, *, steps: int):
    m = Model()
    wt.lay_axis_slope(cs, m, low_edge, steps=steps)
    return render(m, HexCamera())


def _render_slope_half(cs: wt.CrossSection, low_edge: str, *, steps: int, high_half: bool):
    m = Model()
    wt.lay_axis_slope_half(cs, m, low_edge, steps=steps, high_half=high_half)
    return render(m, HexCamera())


def bake_way_atlases(cs: wt.CrossSection, *, out_dir: Path, name: str,
                     has_double_slopes: bool = False) -> None:
    """Bake the three hex atlases for one way asset.

    - `<name>_hex.png` — 8×8 ribi atlas (63 cells, last slot empty),
      in `HEX_ENTRIES` popcount-then-ribi order.
    - `<name>_hex_slope.png` — axis crossings.  1×6 for single-height
      only; 2×6 for `has_double_slopes` tiers (row 0 single, row 1
      `0→2` double).
    - `<name>_hex_slope_half.png` — half-slope stubs (way ends on the
      ramp's low or high edge).  2×6 (row 0 = low halves, row 1 =
      high halves) for single-height only; 4×6 with rows 2-3 carrying
      the matching double-height variants when `has_double_slopes`.

    The pakset's `.dat` `ImageUp[…]` keys map onto these cells; the
    key vocabulary is the engine's `way_image_keys::slope_slot_keys`.
    """
    slope_entries = [
        (label, lambda e=edge: _render_slope(cs, e, steps=1))
        for label, edge in SLOPE_HEX_ENTRIES
    ]
    slope_half_entries = [
        (label, lambda e=edge, h=high: _render_slope_half(cs, e, steps=1, high_half=h))
        for label, edge, high in SLOPE_HEX_HALF_ENTRIES
    ]
    if has_double_slopes:
        slope_entries += [
            (label, lambda e=edge: _render_slope(cs, e, steps=2))
            for label, edge in SLOPE_HEX_DOUBLE_ENTRIES
        ]
        slope_half_entries += [
            (label, lambda e=edge, h=high: _render_slope_half(cs, e, steps=2, high_half=h))
            for label, edge, high in SLOPE_HEX_HALF_DOUBLE_ENTRIES
        ]
    bake_atlas(out_png=out_dir / f"{name}_hex_slope.png",
               entries=slope_entries, cols_per_row=6)
    bake_atlas(out_png=out_dir / f"{name}_hex_slope_half.png",
               entries=slope_half_entries, cols_per_row=6)
    bake_atlas(out_png=out_dir / f"{name}_hex.png",
               entries=[(ribi, lambda edges=edges: _render_flat(cs, edges))
                        for ribi, edges in HEX_ENTRIES],
               cols_per_row=8)
