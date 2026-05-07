# TODO

Running registry of open debt for the pak 3D-modelling work. Plain
paragraphs, not lists — adding or removing one entry produces a
clean diff that doesn't reflow its neighbours. When an entry is
resolved, **delete it in the same commit**: no strikethrough, no
"done" note. Git history is the changelog. Glance at this file
before starting new work; it doubles as a map of where the rough
edges are.

When you notice something wrong while working on something else —
a sketchy pattern, a missing piece, an inconsistency, an
assumption that wants verifying — log it here as a paragraph
rather than fixing it on the spot (scope creep) or leaving it as
an in-code `// TODO` (invisible outside that file). Concrete
enough that someone else can pick it up cold.

## Open

**Way .dat migration to hex ribi keys.** The engine's `way_writer`
now reads a 64-slot flat-image table keyed by hex ribi names
(`Image[se]`, `Image[se_nw]`, …; `_` separator).  Two worked
examples now exist, both with bespoke 3D bakes covering the full
63-cell hex set: `infrastructure/rail_tracks/rail_060_tracks` and
`infrastructure/roads/road_040`.  Every other way .dat —
rail_080..rail_400, remaining roads (road_030/050/055/070/090,
cityroad_030, highway_*), trams, runways, kanals, narrowgauge,
monorails, maglevs, plus all elevated / catenary variants — still
carries the legacy `Image[N]` / `Image[NSE]` keys.  These compile
without fatal but every connectivity except `Image[-]` resolves to
`IMG_EMPTY` at runtime, so those ways will be invisible on the
map.  Two paths to migrate per family: a cell-repoint (pak `N` =
hex NE etc.) leaves third-axis combos invisible; a 3D bake of the
family's cross-section through the shared topology produces the
full 63-cell set.  Roads share `infrastructure/roads/road_params.py`
(pavement width / surface z / colour) so road_030 / road_050 / …
land as a copy of `road_040/scene.py` with one parameter override.

**Way-baker shared topology.** `tools/threed/way.py` +
`tools/threed/way_topology.py` carry the asset-agnostic hex topology
(stub / curve / junction / axis-slope path builders + a
`CrossSection` painter ABC).  Two consumers today —
`infrastructure/rail_tracks/rail_060_tracks` (ballast + ties + rails
cross-section, with a `paint_arc` override for radial ties) and
`infrastructure/roads/road_040` (one pavement slab) — both bake the
full 63-cell hex set into `<asset>_hex.png` plus a 6-cell axis-slope
atlas.  Open work: 3+ way junctions are placeholder "stub-per-edge"
geometry — a pass should promote any 60°-apart pair inside a
junction to an arc (through-route) and leave the remaining edges as
branching stubs; rail also wants a buffer-stop short beam at the
centre end of single-edge stubs (currently a clean cut reads as
"track ending mid-air"); the no-way `Image[-]` placeholder still
borrows an upstream pak128 square cell on both bakers.

**Way winter art.** Both `rail_060_tracks.dat` and `road_040.dat`
are now single-season — engine treats `Image[-][1]` absent as
year-round summer.  Hex winter art is deferred per family; lands
as a colour/material variant on the same scene parts (rail: ballast
+ tie palette swap; road: snow-dusted pavement) producing
`<asset>_hex_winter.png` and re-introducing the `[1]` season block.

**X-bracing on rail_060_bridge.** The numpy z-buffer rasterizer
in `tools/threed/render.py` only supports axis-aligned boxes via
`add_box`, so the diagonal X-bracing between trestle posts can't
be modelled cleanly. Two options: extend `Scene.add_quad` with
explicit non-axis-aligned corners (a thin plate in the y-z plane,
rendered double-sided), or switch this asset class to Blender.
Defer until other rail bridge variants are in flight so the fix
applies once across the family.

**rail_060_bridge remaining sheet calibration.** Mid-segments
(NS/EW back+front), ramps, starts, start2, and pillars are now
modelled and bake into both the square verification renders
(`build.py` refs table) and the hex atlas.  Ramps/starts are still
first-pass geometry — coherent with the 60 bridge model, but not yet
closely fitted to the upstream pak128 cells.  Pillar geometry is also
a first-pass stub — a single
stone box from z=PILLAR_BOTTOM_Z to deck-bottom; it doesn't match
the reference's wider cross-section or the asymmetric face that
`pillar_asymmetric=1` implies (alpha_iou ≈ 0.15 per the diff).
Winter variants of every entry remain entirely deferred — should
plug in as a colour/material variant on the same parts once the
summer set reads right.

**rail_060_bridge_hex end-entry calibration.**  Engine
`bridge_desc_t::img_t` is the hex layout — 3 way
axes for segments / pillars (`ns`, `ne_sw`, `nw_se`) and 6 hex edges
for starts / ramps (`n`, `s`, `ne`, `se`, `sw`, `nw`); the writer
reads keys at those names (`bridge_writer.cc`).  The hex dat now
covers the full summer set: segments + pillars via the axis
orientations, and ramps / starts / start2 via edge orientations.
Next pass should tune the ramp grade, landward cut, and front railing
placement against the square reference diffs before cloning the
material variant for winter.

**rail_060_bridge_hex deep supports clip at the image bottom.**
`PILLAR_BOTTOM_Z = -0.55` projects to screen-y ≈ 156 under the hex
camera (`hex_anchor_y=106 + 0.55 × HEX_Z_SCALE`), but the hex output
is 128 tall, so all three pillar cells land y_max=127.  Pillar
accessible depth tops out at z ≈ -0.23 — about a third of the
modelled pillar.  Start/start2 end cells also touch y=127 where
their support posts extend below the deck.  The deck-anchor
calibration (`hex_anchor_y` 96→106 to match pak128's deck-vs-tile
offset) tightened this — every px the deck moves down in the cell
trades against pillar head-room.  Either shorten deep supports for
the hex bake (an axis-by-axis check whether the engine actually
composites the full max-depth shape would say if that's safe —
pak128's square cells ship the full depth and the engine clips at
composite time; hex may want the same contract), or extend the hex
output buffer vertically (give the cell a bottom-pad analogous to
HexGeom's existing top_pad for slope room).  Tracks don't hit this
because they sit at z ≥ 0.

**rail_060_bridge silhouette y mismatch — remaining structural
question after the deck-anchor shift.**  The 6-px-too-high
hypothesis was confirmed: shifting `screen_center_y` 68→74 (+ hex
anchor 96→106) raised IoUs across the board (BackImage 0.66→0.74,
FrontImage 0.31→0.53).  What's left is the front-half score plateau
at ~0.53 — likely the second hypothesis from the prior entry: pak128
uses a fascia under the deck edge (front-side bar that extends
below deck) rather than our kick-rail-on-top-of-deck geometry.
Verify by eyeballing a front-half ref cell side-by-side with the
candidate, then add the fascia geometry.  The kick-rail tweaks
(RAILING_TOP_Z, TOP_BAR_THICKNESS) are still the wrong move —
they fit the bbox by shrinking the railing to a hairline.

**Aggregate scoring across slices not designed.** Multi-view
supervision gives one score per slice; there's no rolled-up
per-asset or per-pakset score. For tracking progress across many
slices and assets, need a strategy (sum, max, weighted, separate
panes). Defer until more slices are wired and the right shape
becomes obvious from use.

**render.py projection vs canonical engine math.** Rasterizer uses
`YAW=45°`, `ELEV=29.5°` hardcoded, both empirically calibrated
against the flat tile. The canonical math is
`screen_x = (tile_x-tile_y)*W/2`, `screen_y = (tile_x+tile_y)*W/4`
(`viewport.cc::get_screen_coord`); a 30° elevation gives a 2:1
dimetric exactly. Cross-check that the rasterizer reproduces the
engine projection bit-for-bit, not just close enough — pick this
up before scaling to many assets where rounding errors compound.

**`Image[<slope>][k]` second-axis semantics on the engine writer.**
The marker baker emits `Image[<slope>][0]` (front) and
`Image[<slope>][1]` (back) under one `Obj=ground / Name=Marker`
block — using `[k]` as a front/back discriminator rather than the
season axis it conventionally is.  Lightmap and borders only use
`[0]`, so this encoding hasn't been exercised yet.  Whether
`descriptor/writer/ground_writer.cc` (or whatever ends up parsing
the hex marker block) preserves `[k]>0` for `Obj=ground` is
unverified.  If it doesn't, the alternatives are a split-by-
offset encoding (`Image[<slope>][0]` front, `Image[<slope>+4096][0]`
back) or a separate `Obj=ground / Name=MarkerBack` block.  Pin
this when wiring the engine-side hex marker lookup, before any
in-game test depends on the current shape.

**Per-slope water_ani.** The `landscape/grounds/water_ani/` baker
covers all 6 × 32 (depth, stage) cells but only at the flat slope.
`get_water_tile`'s slope axis (`stage + water_animation_stages *
doubleslope_to_imgnr[slope]`) is still collapsed to slope_idx = 0.
The shore-side equivalent is now done —
`landscape/grounds/texture_shore/` bakes one ALPHA_RED-keyed alpha
cell per realisable
`(slope, water_mask)`, and the wet/dry boundary lives there — so
this is the last slope-axis collapse in the parametric ground
family.

**Water_ani art is procedural-placeholder.** The renderer is a
top-K hash speckle that reads as uniform-random sparkle rather
than the layered, clustered glints of pak128's palette art.  Two
measurable gaps remain against the legacy: (a) motion energy/cycle
392 vs 201 — per-frame ~1 / GLINT_PERSISTENCE re-hash is still
roughly twice the legacy shimmer rate; raising GLINT_PERSISTENCE
or cross-fading two hash sets phased on `cos(2π t/32)` /
`sin(2π t/32)` would lower it.  (b) Per-frame stddev 13.8 vs 8.8 —
single-tier glint amplitude too high; multi-tier brightness (e.g.
4% + 4% + 4% at staggered deltas) would lower contrast while
keeping mean exact.  Both deferred until the deliverable is in-game
and the cartoon-vs-realistic balance can be judged against the
rest of the hex tileset.

