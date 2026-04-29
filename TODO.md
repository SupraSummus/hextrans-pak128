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

**X-bracing on rail_060_bridge_NS.** The numpy z-buffer rasterizer
in `models/tools/render.py` only supports axis-aligned boxes via
`add_box`, so the diagonal X-bracing between trestle posts can't
be modelled cleanly. Two options: extend `Scene.add_quad` with
explicit non-axis-aligned corners (a thin plate in the y-z plane,
rendered double-sided), or switch this asset class to Blender.
Defer until other rail bridge variants are in flight so the fix
applies once across the family.

**rail_060_bridge_NS Back-layer height off by ~6 px.** The Back
debug XOR shows the candidate is taller than the reference at the
railing top. Likely `RAILING_TOP_Z` (currently 0.24) is slightly
too high. Back-solve from the reference's top y_min when picking
this up.

**rail_060_bridge_NS remaining sheet entries.** ~28 entries still
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

**Synth capture mechanism not built.** No tooling yet to dump
`synth_overlay::{get_ground, get_marker, get_border, get_alpha,
get_back_wall}` outputs as PNGs. Blocks all parametric pipeline
work. Cleanest option is a small standalone C++ harness that
links the engine's descriptor module and writes through the
existing image writer; alternative is a headless engine run with
a screenshot hook. Re-implementing the synth algorithm in Python
defeats the purpose of having synth as ground truth.

**Old terrain attempts not deleted.** `models/terrain/flat_tile/`
and `models/terrain/slope_sw1/` were mis-targeted (diffed against
pak128's square-projection legacy lightmap rather than synth
output, rendered with OpenSCAD's square camera). Current state in
CLAUDE.md flags them as "skip". Either delete them (clean
directory) or keep them as a worked counterexample with a README;
not both.

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

**Sheet-coordinate compass cross-check on the bridge.** I
established N=upper-right / E=lower-right / S=lower-left /
W=upper-left from `viewport.cc` + `koord.cc` for the NS bridge,
and the orientation matches the reference. Worth verifying the
same convention on a different asset family (e.g. road bridge or
station) before the lookup graduates to "always trust" status —
the .dat keys (`[NS]`, `[N]`, `[S]`) might mean different things
in different desc types.
