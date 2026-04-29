#!/bin/bash
# Install dependencies for the 3D-modelling pipeline (parametric bakers
# colocated with their pakset assets, e.g.
# `landscape/grounds/texture-hex-lightmap/`, plus bespoke supervised
# models like `infrastructure/rail_bridges/rail_060_bridge/`). Tools
# shared by both pipelines live in `tools/3d/`. Idempotent.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Python deps used by tools/3d/{render,diff,crop_ref}.py and the
# per-asset render/build_pakset scripts.
pip3 install --quiet --break-system-packages numpy Pillow >/dev/null

# Blender for the bespoke pipeline renderer (Blender Python).
if ! command -v blender >/dev/null 2>&1; then
  apt-get install -y --no-install-recommends blender >/dev/null
fi
