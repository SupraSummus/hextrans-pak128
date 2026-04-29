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

**Hex depth-clip plane spec missing on engine side.** The bespoke
pipeline can't emit hex sheet entries until the engine specifies
how the Back / Front layer split projects under the hex camera —
analogous to `synth_geometry.h` for the camera and light. Blocks
all bespoke hex deliverables. Lives on the engine side
(`SupraSummus/hextrans`), not here.

**Engine has no hex-aware ground lookup yet.** `build_pakset.py`
emits `landscape/grounds/texture-hex-lightmap.{png,dat}` with 141
`HexLightTexture` entries — one per normalised slope shape (per-edge
delta ≤ 1 and min(corner_heights) == 0, since base elevation lives
in the tile's `hgt` field, not in the slope encoding).  The .dat is
indexed by **raw `slope_t`** itself (base-4 per corner; sparse, with
gaps for invalid encodings that read as IMG_EMPTY) so the engine
just needs to do `slope -= hgt_shift; get_image_ptr(slope)` — no
compact-index translation table.  The engine's `get_ground_tile`
currently indexes via `climate_image[c] + doubleslope_to_imgnr[slope]`,
square-only, 81 slopes after the 6→4 projection.  A hex-aware
`get_hex_ground_tile(slope, c)` needs to shift `slope_t` so its
minimum corner is 0 and re-apply that shift in the drawn yoff so the
elevation factored out comes back at draw time.  As a heads-up: the
engine's own `synth_overlay::init` currently iterates 0..4095 and
generates 340 sprites without the min=0 normalisation — that's also
worth tightening alongside the consumption work, since the redundant
elevated copies waste startup time and gfx slots.  Until the engine
path lands, the baked atlas sits unused on disk and the in-process
synth path keeps serving ground tiles.


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

**Naming for future hex-baked deliverables.** The first parametric
deliverable went out as `texture-hex-lightmap.{png,dat}` — the
square-projection legacy was `texture-lightmap`, and the hex
variant inserted `hex-` after the `texture-` prefix. The remaining
synth families (marker, borders, alpha, back_wall) don't all have a
`texture-` prefix in their legacy names (compare
`landscape/grounds/marker.{png,dat}` vs
`landscape/grounds/texture-slope.{png,dat}`), so the analogous hex
names are not obvious. Pick a rule before the next family bakes
(probably: `<legacy-stem>-hex.{png,dat}` so the legacy and hex
variants sort next to each other in the directory listing) and
commit it to CLAUDE.md's repo-layout section.

**Re-bake CI check.** `landscape/grounds/texture-hex-lightmap.{png,dat}`
are committed alongside their generator at
`landscape/grounds/texture-hex-lightmap/`. Re-running `build_pakset.py`
should produce a byte-identical diff. Add a CI job that does the
re-run and fails on diff so the committed deliverable can't drift
from the source. Same pattern will apply to the future synth
families (marker, borders, …) and to bespoke models once one
graduates to producing packaged output.

**Sheet-coordinate compass cross-check on the bridge.** I
established N=upper-right / E=lower-right / S=lower-left /
W=upper-left from `viewport.cc` + `koord.cc` for the NS bridge,
and the orientation matches the reference. Worth verifying the
same convention on a different asset family (e.g. road bridge or
station) before the lookup graduates to "always trust" status —
the .dat keys (`[NS]`, `[N]`, `[S]`) might mean different things
in different desc types.
