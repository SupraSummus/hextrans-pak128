#!/usr/bin/env bash
# Render a .scad file to a 128x128 RGBA PNG with the pak128 dimetric camera.
#
# Usage:
#   render_openscad.sh <scene.scad> <out.png> [extra openscad args...]
#
# The default camera/projection/colorscheme are pak128 dimetric defaults.
# Override with extra args (e.g. --camera=...) which are appended after
# the defaults so they win.
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <scene.scad> <out.png> [extra openscad args...]" >&2
    exit 2
fi

SCENE="$1"
OUT="$2"
shift 2

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_RAW="$(mktemp --suffix=.png)"
trap 'rm -f "$TMP_RAW"' EXIT

# pak128 dimetric defaults, calibrated against the "flat" reference tile
# (texture-lightmap.png Image[0]):
#   yaw 45, pitch 55.5, look-at z=0.5, ortho zoom dist=3.5
# Produces a 128x128 frame with the unit ground tile rendered as a
# 128x63 diamond filling the bottom half (bbox (0,65,128,128)).
xvfb-run -a openscad "$SCENE" \
    -o "$TMP_RAW" \
    --imgsize=128,128 \
    --camera=0,0,0.5,55.5,0,45,3.5 \
    --projection=ortho \
    --colorscheme=Sunset \
    "$@" >/dev/null

python3 "$TOOLS_DIR/mask_bg.py" "$TMP_RAW" -o "$OUT" --bg 170,68,68
