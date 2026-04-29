#!/usr/bin/env bash
# Render this asset's scene to out.png (128x128 RGBA).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/../../tools/render_openscad.sh" "$HERE/scene.scad" "$HERE/out.png" "$@"
