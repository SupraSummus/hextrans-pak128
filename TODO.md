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
(`Image[se]`, `Image[se_nw]`, …; `_` separator).  Only
`infrastructure/rail_tracks/rail_060_tracks.dat` has been migrated
as a worked example.  Every other way .dat — rail_080..rail_400,
roads, trams, runways, kanals, narrowgauge, monorails, maglevs,
plus all elevated / catenary variants — still carries the legacy
`Image[N]` / `Image[NSE]` / `Image[NSE1]` keys.  These compile
without fatal but every connectivity except `Image[-]` resolves to
`IMG_EMPTY` at runtime, so those ways will be invisible on the
map.  Migrate per family, repointing existing pak128 cells onto
the matching hex direction by onscreen heading (pak `N` =
upper-right = hex NE; pak `E` = lower-right = hex SE; pak `S` =
lower-left = hex SW; pak `W` = upper-left = hex NW).  The third
hex axis (N straight up / S straight down on screen) has no
upstream cell — `rail_060_tracks` synthesises it from its 3D
model; other unmigrated ways will need to either borrow a
diagonal as a placeholder or share the baker once it generalises.

**Track-sprite baker.** Hex track .dats need slot entries covering
6 single edges, 3 axis-straights, 12 bends and the 3-way / 4-way
junction patterns.  `rail_060_tracks` now bakes 6 stubs + 3
axis-straights + all 12 bends (21 cells in ribi-value order)
through `infrastructure/rail_tracks/rail_060_tracks/scene.py::bake_pakset()`
→ `rail_060_tracks_hex.png`.  60°-apart corner curves arc around
the shared corner (radius = R/2, perpendicular to each edge at
its midpoint) rather than the straight-with-mitred-cap chord that
opposite/120° pairs share; stubs are a half-tile chord from the
hex centre to one edge midpoint, mitred at the edge end and cut
flat at the centre — no buffer-stop geometry yet, the rails just
end.  The no-track `Image[-]` placeholder and `ImageUp` slope
variants still borrow upstream square cells.  Slope-up is the
next chunk; junctions follow once the engine writer grows a slot
for them.  Stub buffer-stop geometry (a short transverse beam at
the centre end) is also worth a pass — the current clean cut
reads as "track that ends mid-air" rather than a buffered
terminus.

**Depth-clip plane spec partially used.** `rail_060_bridge`'s hex
bake (`scene.py::bake_pakset` → `rail_060_bridge_hex.png`) emits
multi-layer hex output via the per-quad hardcoded-layers route.
The NS axis matches `front_back_split`'s `n=(1,0)` rule exactly
(manual `front`=+x ↔ spec `front`=+x>0); EW matches `n=(0,-1)`
(manual `front`=-y ↔ spec `front`=-y>0).  Both implicit; the
`HEX_DEPTH_CLIP_NORMAL` / `front_back_split` symbols in
`tools/3d/hex_synth.py` are still unreferenced from any baker.
When NE_SW or NW_SE axes are modelled they'll need either
auto-tagging at render time or a per-axis re-tag — the manual
NS / EW tags will not pass through to a 60°-rotated bridge.

**X-bracing on rail_060_bridge.** The numpy z-buffer rasterizer
in `tools/3d/render.py` only supports axis-aligned boxes via
`add_box`, so the diagonal X-bracing between trestle posts can't
be modelled cleanly. Two options: extend `Scene.add_quad` with
explicit non-axis-aligned corners (a thin plate in the y-z plane,
rendered double-sided), or switch this asset class to Blender.
Defer until other rail bridge variants are in flight so the fix
applies once across the family.

**rail_060_bridge remaining sheet entries.** Mid-segments (NS/EW
back+front) and pillars (S/W) are now modelled and bake into both
the square verification renders (`build.py` refs table) and the
hex atlas; ramps, starts, and start2 (× 4 directions) are still
un-modelled.  Pillar geometry is a first-pass stub — a single
stone box from z=PILLAR_BOTTOM_Z to deck-bottom; it doesn't match
the reference's wider cross-section or the asymmetric face that
`pillar_asymmetric=1` implies (alpha_iou ≈ 0.15 per the diff).
Tighten the pillar after ramps/starts are in flight, when the
overall sheet coverage is good enough to judge it in context.
Winter variants of every entry remain entirely deferred — should
plug in as a colour/material variant on the same parts once the
summer set reads right.

**rail_060_bridge_hex covers 2 of 3 hex axes; ramps / starts /
double-height entries still missing.**  Engine `bridge_desc_t::img_t`
is now the hex layout — 3 way axes for segments / pillars (`ns`,
`ne_sw`, `nw_se`) and 6 hex edges for starts / ramps (`n`, `s`,
`ne`, `se`, `sw`, `nw`); the writer reads keys at those names
(`bridge_writer.cc`).  The hex deliverable currently models 6 cells
(NS and NW-SE back+front, NS and NW-SE pillars).  The third axis
(`ne_sw`) has no asset and `scene.py::HEX_ENTRIES` lacks an
NE-SW segment render.  All ramps, starts and `*2` (double-height)
entries are absent — makeobj emits "No frontramp[…] specified"
warnings for each, which is the expected partial-coverage signal.
Wire those in as the bridge model gains the matching 3D parts.

**Asymmetric-pillar corner pair for the NE-SW axis is a guess.**
`pillar_t::calc_image` (engine `obj/pillar.cc`) hides an
asymmetric pillar when its reference 2-corner pair sits high.
The square-era pairs (NS: SW+SE, NW-SE: SE+NE) carried a
viewer-side "lower-screen half" semantic that doesn't split a
hex tile into clean halves; the engine's NE-SW choice
(corner_e + corner_se) is provisional.  Verify when a hex
NE-SW bridge bake exists and a real composite shows whether
the right pillar face hides on each ramp slope.

**rail_060_bridge silhouette y mismatch — don't chase it via
RAILING_TOP_Z alone.** Back y_min=27 vs ref 33 (cand 6 px too
tall at the railing top); front y_max=80 vs ref 86 (cand 6 px
too short at the kick-rail bottom).  An earlier pass dropped
RAILING_TOP_Z 0.24→0.16 + TOP_BAR_THICKNESS 0.030→0.015 to
align the back y_min, won the bbox + the score (0.49→0.41 /
0.84→0.63), but visually shrank the timber railing to a 3 px
hairline that reads worse than the original chunky-but-tall
silhouette.  Reverted; scores back to 0.49 / 0.84 and the y
mismatches are open again.  Likely structural causes: pak128's
deck top is at a slightly lower screen-y than ours (so the
whole deck-and-railing stack sits 6 px lower in the cell), or
pak128 uses a fascia under the deck edge (front-side bar
extends below deck) rather than our kick-rail-on-top-of-deck
geometry.  Bbox-fitting RAILING_TOP_Z is the wrong move per
CLAUDE.md "diff is a sanity check, not the steering signal" —
needs a side-by-side eyeball of the references first to figure
out what 3D structure actually produces the reference.

**Sheet offset (`xoff,yoff`) semantics not pinned down.** A .dat
entry like `BackImage[NS][0]=…,0,32` is an engine compositing
shift applied at draw-time, not a shift baked into the cell.
Empirically the rail bridge needed `screen_center_y=68` for the
cropped reference's south trestle bottom (y_max=90) to line up;
the original CLAUDE.md had inferred `screen_center_y=64` from the
.dat's `32`. The mapping between the .dat's yoff and the in-cell y
of world z=0 isn't documented. Trace where the engine applies the
offset (start in `obj/bruecke.cc::calc_image` and the way drawing
path) and add an entry to Engine facts in CLAUDE.md.

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
The shore-side equivalent is now done — `landscape/grounds/texture-
shore/` bakes one ALPHA_RED-keyed alpha cell per realisable
`(slope, water_mask)`, and the wet/dry boundary lives there — so
this is the last slope-axis collapse in the parametric ground
family.

**Shore atlas in-game look unverified.** `landscape/grounds/
texture-shore/` produces a per-`(slope, water_mask)` atlas with a
2-colour (red / blue) ALPHA_RED-keyed mask + hashed dither at the
boundary.  The bake reproduces the legacy gritty-soft-edge feel on
synthetic samples but hasn't been compared against pak128's actual
in-game shore on a real map; first interactive run with the hex
engine should sanity-check the dither width (`±0.4` jitter, ~6 px
band at W=128) and the wetness threshold (`0.5`) against pak128's
beach.  Drop this entry once that's done.

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

**Sheet-coordinate compass cross-check on the bridge.** I
established N=upper-right / E=lower-right / S=lower-left /
W=upper-left from `viewport.cc` + `koord.cc` for the NS bridge,
and the orientation matches the reference. Worth verifying the
same convention on a different asset family (e.g. road bridge or
station) before the lookup graduates to "always trust" status —
the .dat keys (`[NS]`, `[N]`, `[S]`) might mean different things
in different desc types.
