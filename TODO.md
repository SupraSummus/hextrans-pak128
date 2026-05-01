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
→ `rail_060_tracks_hex.png`.  60°-apart corner curves use a
hex-centred arc (radius = R·√3/2, tangent to each edge at its
midpoint) rather than the straight-with-mitred-cap chord that
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

**X-bracing on rail_060_bridge.** The numpy z-buffer rasterizer
in `tools/3d/render.py` only supports axis-aligned boxes via
`add_box`, so the diagonal X-bracing between trestle posts can't
be modelled cleanly. Two options: extend `Scene.add_quad` with
explicit non-axis-aligned corners (a thin plate in the y-z plane,
rendered double-sided), or switch this asset class to Blender.
Defer until other rail bridge variants are in flight so the fix
applies once across the family.

**rail_060_bridge Back-layer height off by ~6 px.** The Back
debug XOR shows the candidate is taller than the reference at the
railing top. Likely `RAILING_TOP_Z` (currently 0.24) is slightly
too high. Back-solve from the reference's top y_min when picking
this up.

**rail_060_bridge remaining sheet entries.** ~28 entries still
un-modelled: BackImage/FrontImage[EW] (perpendicular orientation),
BackRamp/FrontRamp × {N,S,E,W}, BackStart/FrontStart × 4,
BackStart2/FrontStart2 × 4 (double-height), backPillar[S/W], plus
winter variants of all of the above. The scene composes from 3D
parts (deck, pillar, ramp), so most should drop in once the core
NS segment is right; the exception is the EW orientation which
exercises the perpendicular layer split.

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
