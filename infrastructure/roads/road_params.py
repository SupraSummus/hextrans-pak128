"""Road-family parameters (cross-section, materials).

Parallel to `infrastructure/rail_tracks/rail_060_tracks/track_params.py`
for the rail family — shared by every road tier (road_030 ... road_090,
city_road, highway_*) so a sidewalk pass or a centre-line pass lands in
one place.

Per-tier overrides happen in the tier's own `scene.py` (cost,
intro_year, the colour palette of asphalt vs. cobble vs. dirt).  The
defaults below describe `road_040` — the 40 km/h stone city road that
is the first hex bake — so a subsequent tier that imports unchanged
gets stone-city geometry until it overrides.
"""
# --- Material colours --------------------------------------------------------
# Warm stone-grey for the 40 km/h cobbled city road.  Asphalt tiers
# (road_070+, highway_*) will override to a cooler dark grey; dirt tier
# (road_030) to a brown.  Hand-picked to read against pak128's flat-
# grass climate without crawling out of the legacy palette.
PAVEMENT_GREY = (140, 130, 115)

# --- Cross-section (perpendicular to the road axis) -------------------------
# 1 unit = 1 tile width.  Pavement is wider than rail's tie footprint
# (TIE_HALF_W=0.16) — roads carry the full lane plus shoulders, where
# rail just carries the ties.  0.20 leaves a small margin to the hex
# edge midpoint at the end caps; widen later if the silhouette reads
# pinched.
PAVEMENT_HALF_W = 0.20

# Pavement surface above ground (z=0).  Lower than rail's BALLAST_TOP_Z
# (0.020) — roads sit nearly flush with terrain, cobbles aren't a raised
# bed.  Non-zero so the surface clears z=0 dither speckle.
PAVEMENT_TOP_Z = 0.010
