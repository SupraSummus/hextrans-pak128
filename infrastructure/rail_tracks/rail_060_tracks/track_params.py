"""Track-family parameters for rail_060.

Imported by both `rail_060_tracks/scene.py` (the canonical track
sprite) and `rail_060_bridge/scene.py` (so the bridge's deck-top
track lines up with the standalone track that joins it).  Per
CLAUDE.md "Modelling as programming": shared structural facts live
in one module, not duplicated per asset.

The values below are the rail_060-specific cross-section.  When a
second rail width arrives (rail_080 etc.) it gets its own params
file; what's *family*-shared (cross-section conventions, dither
band shape) graduates higher up only if the second member confirms
the abstraction.
"""
# --- Material colors ---------------------------------------------------------
TIE_BROWN = (100, 70, 45)
RAIL_GREY = (140, 140, 130)

# --- Cross-section (perpendicular to the track axis) ------------------------
# 1 unit = 1 tile width.  Calibrated against pak128 cells 1.5 / 1.6 of
# `rail_060_tracks.png` by `measure_gauge.py`, which fits a line to the
# rail-head pixels of each rail and inverts the dimetric projection's
# perpendicular px-per-world factor.  Both cells land on 0.04744 — keep
# `measure_gauge.py` working (and re-run after pak128 refresh) rather
# than tweaking this number by eye.
TIE_HALF_W = 0.16
RAIL_HALF_W = 0.008      # rail head thickness (perpendicular to track)
RAIL_GAUGE_HALF = 0.0474  # half the rail-to-rail spacing

# Stack heights above ground (z=0).  Bridge scenes lift these onto
# their deck top via `DECK_TOP_Z + (TIE_TOP_Z - BALLAST_TOP_Z)` etc.
BALLAST_TOP_Z = 0.020
TIE_TOP_Z = 0.030
RAIL_TOP_Z = 0.045

# Cross-tie cadence along the span.
N_TIES = 12
