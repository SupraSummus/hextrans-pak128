#!/bin/bash
# Install dependencies for the models/ pipeline (parametric + bespoke 3D
# asset rendering and diff). Idempotent.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Python deps used by models/tools/{diff.py,crop_ref.py,mask_bg.py,render.py}.
pip3 install --quiet --break-system-packages numpy Pillow >/dev/null

# Blender for the bespoke pipeline renderer (Blender Python).
if ! command -v blender >/dev/null 2>&1; then
  apt-get install -y --no-install-recommends blender >/dev/null
fi
