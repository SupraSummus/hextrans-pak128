# CLAUDE.md

Notes for AI agents (and humans) working on this fork of pak128.

## Bigger picture

This fork exists because we want to port Simutrans to a **hex grid**
(`SupraSummus/hextrans`). A hex-grid map needs sprites rendered from
hex-appropriate camera angles — the existing pak128 sprites are drawn for the
square-tile dimetric projection and can't simply be reused.

The plan is to obtain hex-grid sprites by introducing an intermediate
representation we don't currently have: **3D models** of pakset assets. Once
an asset is a 3D scene, we can render it from any camera angle — including
hex viewpoints — to produce the new tileset.

We don't have time or skill to model the entire pakset by hand. The hope is
that an iterative, automated pipeline can carry most of the load.

## The approach: render-and-diff

For each asset we want to convert, we set up:

1. A **3D scene description** (format and tool chosen per asset — see below).
2. A **build command** that renders that scene to a PNG.
3. A **diff** of that PNG against the corresponding tile region of the
   original pak128 sprite sheet.

The objective is to drive the diff toward zero by editing the scene
(geometry, materials, camera, lighting). Once the rendered output matches
pak128 closely, we know the 3D model is faithful, and we can re-render it
from hex camera angles for the new pakset.

### Who does the modeling

The 3D modeling is done by an **AI agent** acting as the modeler, the
same way a human artist would: examine the reference sprite, build a
scene, render it, look at the diff, edit, iterate. **It is not numerical
optimization** (no scipy, no gradient descent over vertex positions).
The intelligence in the loop is a directed agent making judgment calls
about geometry, material, and lighting — not a black-box minimizer.

### Structural correctness, not just pixel match

Visual diff is **one** criterion, not the only one. The 3D model must
also be **structurally correct**:

- A bridge deck must meet the ground at the correct world-space point
  at each end.
- Posts must reach from deck to ground (no floating geometry).
- Spans, heights, and tile-grid alignment must be consistent across
  variants (e.g. all `rail_*_bridge` decks share a deck height).
- Repeating elements must repeat at the right pitch.

A model that pixel-matches but is structurally wrong is a failure —
because the goal is to re-render the same asset from hex camera angles
and have it remain geometrically valid.

### Model the whole asset, then slice for sprites

Pak128 packs a single in-game asset into many sheet tiles
(`BackImage`, `FrontImage`, `BackRamp`, `BackStart`, `backPillar`, etc.)
because the engine composites them at runtime around moving vehicles.
**That decomposition is a renderer concern, not a modeling concern.**
We model the asset **as one complete 3D structure**. To produce the
individual sheet tiles, we then slice / depth-mask the same model:

- `composite_*` = render everything = simplest diff target.
- `BackImage` = the part of the render behind a depth plane.
- `FrontImage` = the part in front of that plane.
- `backPillar[*]` = isolate just the pillar volume(s).

For the first iteration on any new asset, target the composite — it
needs no slicing. Add slicing only once the whole model is solid.

Implications for tooling:

- The scene file must be **text and editable by an AI agent** —
  `.scad`, `.py`, `.pov`, structured JSON, etc. Binary formats are out.
- The diff tool's primary output is a **visual debug image** the AI can
  view to understand what's wrong. The numerical score is a secondary
  sanity check, not the steering signal.
- The renderer must expose **lighting, projection, and camera as
  scene-file parameters**, not hardcoded behavior — otherwise the AI
  can't edit them as part of modeling. (This is a strong argument
  against OpenSCAD's preview rendering and for a custom Python
  rasterizer or Blender Python.)

### Why not pin a specific format?

3D content varies wildly — flat slope tiles want parametric CSG, gnarled
trees want sculpting, vehicles want hard-surface modeling. Forcing one
format (STL, OpenSCAD, glTF, ...) optimizes for one of these and hurts the
others.

Instead, the contract is **per-asset**:

- Each asset directory contains whatever source files the modeler chose
  (`.scad`, `.blend`, `.py` for `bpy`, `.pov`, `.obj` + materials, ...).
- Each asset directory has a build command that produces `out.png`.
- The diff tool consumes `out.png` and the pakset reference; it doesn't
  care how `out.png` was made.

Bias toward **text-based, AI-editable formats** (OpenSCAD `.scad`, Blender
Python `.py`, POV-Ray `.pov`) over binary ones, but don't insist.

### Diff scope: one tile region at a time

The unit of diffing is one **single sprite tile** — the atomic image the
game looks up. Pak128 sprite sheets pack many tiles per PNG, with the
layout declared in an accompanying `.dat` file (e.g. `landscape/grounds/
slope.dat` ↔ `slope.png`, with entries like `Image[1][0]=slope.1.0`
meaning "row 1, col 0 of slope.png" in tile-sized cells).

The diff tool takes `(sprite_sheet.png, .dat, image_index)` (or a
direct tile reference), crops the reference tile, and compares pixel-wise
against the candidate `out.png`. Always diff at the game's atomic unit so
we can't accidentally score against a whole sheet.

### Anti-cheat

We can't fully prevent a clever modeler from baking the answer into the
scene, but the system relies on these honor-rules:

- An asset's source tree must not contain the reference PNG or any file
  pixel-identical to it.
- The build command must not read from `references/` or from the original
  `landscape/`, `vehicles/`, etc. PNGs.
- The pakset's own *materials* (e.g. the flat-grass texture for slope
  tiles) **may** be reused as material inputs — that's how the original
  was made — but only as inputs to a real renderer, not as the answer.
- We can spot-check by perturbing camera or lighting parameters and
  verifying the output reacts plausibly.

### Texture / material policy

Two phases:

1. **Shape-only diff (start here).** Compare alpha mask plus luminance
   gradient. This carries most of the information for terrain (slopes
   especially) and avoids dragging in a texturing pipeline on day one.
2. **Textured diff (later).** Allow the pakset's own flat tile textures
   as material inputs. Diff full RGB.

## Reference: pak128 rendering conventions

From `devdocs/128painting.txt`:

- Isometric/dimetric projection (parallel lines stay parallel).
- Sun from the south (bottom-left of screen), 60° above ground.
- One tile ≈ 20×20 m; 12 px ≈ 2 m.
- A building story ≈ 14 px tall.

These need to be the defaults for our 3D scenes. Once we lock down a
scene template that reproduces a flat tile correctly, every other asset
inherits the same camera and sun.

## Repo layout (proposed, evolves)

New work lives under a `models/` directory at the repo root, parallel to
`landscape/`, `vehicles/`, etc.:

```
models/
  README.md                  # short pointer to this file
  tools/
    diff.py                  # diff CLI (reference tile vs candidate PNG)
    crop_ref.py              # extract a single tile from a pak sheet via .dat
  terrain/
    slope_w_0/               # one asset per directory
      build.sh               # produces out.png
      scene.<ext>            # whatever source format the modeler picked
      out.png                # rendered output (gitignored or committed?)
      score.txt              # last diff score (committed for tracking)
```

Open question: commit `out.png` and `score.txt`, or regenerate? Probably
commit them so reviewers see the current state without rebuilding.

## Current state

The first target turned out to be `landscape/grounds/texture-lightmap.png`
(not `slope.png`, which is the rocky cliff-face wall under slopes).
`texture-lightmap.png` is the per-pixel shading multiplier applied to
ground tiles — exactly the "slope shading" we want to model.

Sheet layout: 1920×640, 15 columns × 5 rows of 128×128 tiles.
Reference `Image[N][0]=texture-lightmap.row.col` in the .dat, and
`crop_ref.py` parses that automatically.

What's built:

- `models/tools/crop_ref.py` — extract a single tile from a sheet by
  `--dat path --image N`. Masks pak128's transparent color (231,255,255)
  to alpha=0.
- `models/tools/diff.py` — score (alpha IoU + luminance RMSE in
  intersection + alpha XOR) and a 4-panel debug PNG (ref | candidate |
  lum diff | xor).
- `models/tools/render_openscad.sh` — shared OpenSCAD render wrapper.
  Headless via `xvfb-run`. Background masked from `--colorscheme=Sunset`
  (170,68,68) → alpha 0. Calibrated dimetric camera defaults:
  `--camera=0,0,0.5,55.5,0,45,3.5 --projection=ortho`. Produces a 128×128
  RGBA PNG with a unit ground tile rendered as a 128×63 diamond filling
  the bottom half (matches the flat reference bbox exactly).
- `models/terrain/flat_tile/` — Image[0] flat tile. Calibration scene.
  Score ~0.41 (shape near-perfect; brightness off, see below).
- `models/terrain/slope_sw1/` — Image[1] sw1 slope. Starting point only;
  shape and shading don't match yet.

### Findings / open issues from the first iteration

1. **Lightmap silhouette is nearly invariant.** sw1's reference bbox is
   essentially the flat diamond — only ~1 px taller. The lightmap is
   **shading-only**: it encodes per-pixel brightness multipliers, not
   the actual slope geometry's silhouette. So we shouldn't try to match
   silhouettes; we should match the *shading pattern* on a (nearly)
   fixed diamond.
2. **OpenSCAD's preview lighting is fixed** — we can't aim its sun at
   pak128's south-bottom-left at 60°. This caps how well OpenSCAD alone
   can match shading. Two reasonable next moves:
   - Post-process the OpenSCAD render: extract the surface normal at
     each pixel (e.g. by rendering normal maps via per-axis gradients)
     and re-light against the pak128 sun direction in Python.
   - Switch the slope-shading assets to a small custom Python rasterizer
     with a controllable directional light. Pure-numpy, ~100 lines,
     full control. The format-agnostic build contract makes this
     cheap to do per-asset.
3. **Brightness offset on the flat tile.** Our render uses (189,189,189)
   while the reference is darker. The flat lightmap is the canonical
   neutral shade — we should sample the reference and use that exact
   gray as the baseline material.
4. **Half-height geometric rise looks wrong.** Setting SW corner z=0.25
   (`H_HALF`) deformed the silhouette far more than the reference
   shows — confirming finding (1). When matching the lightmap
   specifically, treat the geometry as a flat diamond and only vary
   the per-corner *normal* used for shading, not the actual vertex
   positions.

### Recommended next iteration

- Write a tiny pure-numpy rasterizer (`models/tools/rasterize.py`) that:
  - Takes a scene = quad with 4 corner positions + a sun direction.
  - Projects with the locked dimetric matrix.
  - Lambert-shades using a known-good baseline gray and the pak128 sun.
  - Outputs RGBA at 128×128 with proper alpha.
- Match the flat tile's exact baseline gray.
- Re-do `slope_sw1` using the rasterizer with sw1 corner heights, and
  verify shading direction matches before tuning rise magnitude.

## Workflow rules

- All work on this stream goes on branch `claude/pak128-3d-models-F7qBa`.
- The companion engine repo is `SupraSummus/hextrans`, branch
  `claude/pak128-3d-models-F7qBa`. Cross-repo changes are coordinated.
- Commit small, push often; no PRs unless the user asks.

## Open questions / TBD

- **Renderer choice.** Blender (headless via `blender -b`) is the default
  pick — Python-scriptable, supports textures and complex geometry — but
  not enforced. OpenSCAD is fine for blocky parametric assets.
- **Optimization loop.** Manual edit + diff for now. Camera-parameter
  auto-fit (scipy over tilt/offset/scale) is a clear next step once shape
  is roughly right. True geometry optimization is much harder and
  probably never automated end-to-end.
- **Hex-camera spec.** Once a few assets match in square-grid projection,
  we need to nail down the hex camera (angle, tile aspect ratio, sprite
  pixel size) on the engine side. That decision lives in
  `SupraSummus/hextrans` and feeds back here.
