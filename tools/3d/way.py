"""Pure-data helpers shared by every hex way baker.

Constants and small helpers that depend only on hex-tile geometry and
the engine's ribi encoding — no rendering, no asset cross-section.
The asset-specific cross-section (ballast for rail, pavement for road,
…) lives in the asset's own scene file and is consumed by
`tools/3d/way_topology.py` through the `CrossSection` interface.

The names here are deliberately one source of truth for both the
.dat-side index space (hex ribi codes per `way_writer.cc::hex_ribi_code`)
and the renderer-side geometry (corners, edges).
"""
from __future__ import annotations

import math


# ---- Hex ribi -------------------------------------------------------------
# Bit order matches `way_writer.cc::hex_dir_name`: SE=0, S=1, SW=2, NW=3,
# N=4, NE=5.  `_` is the .dat-key separator (`,` and `-` inside `[…]`
# trigger tabfile parameter expansion, so they can't be reused).

RIBI_BIT_NAMES: tuple[str, ...] = ("SE", "S", "SW", "NW", "N", "NE")


def ribi_edges(r: int) -> tuple[str, ...]:
    """Edges set in ribi value `r`, in the upper-case names used by the
    geometry tables below (HEX_EDGES, HEX_OPPOSITE_EDGE)."""
    return tuple(name for b, name in enumerate(RIBI_BIT_NAMES) if r & (1 << b))


def ribi_label(r: int) -> str:
    """`.dat`-key form of ribi `r` — bit names lower-cased and joined
    low-to-high with `_` (matches `hex_ribi_code` in the engine writer).
    `r=0` returns `-`, the `Image[-]` no-way slot."""
    if r == 0:
        return "-"
    return "_".join(name.lower() for name in ribi_edges(r))


# Atlas entries used by every way bake.  HEX_ENTRIES is in popcount-
# then-ribi order (6 single-edge stubs first, then 15 edge pairs, 20
# three-way, 15 four-way, 6 five-way, 1 six-way) — the same order the
# engine writer keys against, so cell index `i` lands at row `i//8`,
# col `i%8` in a standard 8-wide atlas.
HEX_ENTRIES: list[tuple[str, tuple[str, ...]]] = [
    (ribi_label(r), ribi_edges(r))
    for r in sorted(range(1, 64),
                    key=lambda r: (bin(r).count("1"), r))
]

# Slope sprites — one per hex axis low edge, in clockwise-from-north
# order matching `way_writer.cc::slope_keys`.  Narrow and wide variants
# of the same low edge typically share a cell (the way climbs the same
# 0→1 path; only the off-axis ground inflection differs), so callers
# emit `ImageUp[<key>]` and `ImageUp[<key>_wide]` pointing at the same
# atlas cell.
SLOPE_HEX_ENTRIES: list[tuple[str, str]] = [
    ("n",  "N"),
    ("ne", "NE"),
    ("se", "SE"),
    ("s",  "S"),
    ("sw", "SW"),
    ("nw", "NW"),
]


# ---- Hex tile geometry ----------------------------------------------------
# Flat-top hex of radius 0.5 centred at origin.  Corner order matches
# `hex_corner_t` in `dataobj/ribi.h`; edge naming matches the EDGE
# convention ("flat-top hexes have due-N and due-S edges, corners do
# not") — see hextrans/AGENTS.md.

_R = 0.5

HEX_CORNERS: dict[str, tuple[float, float]] = {
    "E":  ( _R,                 0.0),
    "SE": ( _R / 2,            -_R * math.sqrt(3) / 2),
    "SW": (-_R / 2,            -_R * math.sqrt(3) / 2),
    "W":  (-_R,                 0.0),
    "NW": (-_R / 2,             _R * math.sqrt(3) / 2),
    "NE": ( _R / 2,             _R * math.sqrt(3) / 2),
}

# Each named edge → (corner_a, corner_b).  Edge midpoint = mean of corners.
HEX_EDGES: dict[str, tuple[str, str]] = {
    "N":  ("NE", "NW"),
    "NE": ("E",  "NE"),
    "SE": ("SE", "E"),
    "S":  ("SW", "SE"),
    "SW": ("W",  "SW"),
    "NW": ("NW", "W"),
}

# 180° pair across the hex centre — the slope axis a low edge sits on.
HEX_OPPOSITE_EDGE: dict[str, str] = {
    "N": "S", "S": "N",
    "NE": "SW", "SW": "NE",
    "NW": "SE", "SE": "NW",
}


def edge_midpoint(edge: str) -> tuple[float, float]:
    a, b = HEX_EDGES[edge]
    ax, ay = HEX_CORNERS[a]
    bx, by = HEX_CORNERS[b]
    return ((ax + bx) / 2.0, (ay + by) / 2.0)


def edge_unit_dir(edge: str) -> tuple[float, float]:
    """Unit vector along edge from its first corner to its second
    (HEX_EDGES order).  Used as the cap direction for chord segments
    that meet this edge at its midpoint, so adjacent tiles' segments
    meet flush across the shared edge."""
    a, b = HEX_EDGES[edge]
    ax, ay = HEX_CORNERS[a]
    bx, by = HEX_CORNERS[b]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


def shared_corner(edge_a: str, edge_b: str) -> str:
    """Corner shared by two 60°-apart hex edges; the centre of the
    corner-radius arc that connects their midpoints.  Asserts the
    edges share exactly one corner — callers gate with
    `set(HEX_EDGES[a]) & set(HEX_EDGES[b])` first if they want to
    distinguish 60° pairs from 120°/180° ones."""
    shared = set(HEX_EDGES[edge_a]) & set(HEX_EDGES[edge_b])
    assert len(shared) == 1, (
        f"edges {edge_a}/{edge_b} don't share exactly one corner")
    return next(iter(shared))


# Through-tile chord between opposite edge midpoints (= R·√3 ≈ 0.866).
# Useful as a per-length cadence reference for assets that scale a
# count along the chord (rail's tie cadence, …).
STRAIGHT_CHORD: float = 2.0 * math.hypot(*edge_midpoint("N"))
