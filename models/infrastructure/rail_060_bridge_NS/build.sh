#!/usr/bin/env bash
# Build the candidate render and (re)build the composite reference.
#
# Composite reference: pak128 splits this bridge into BackImage[NS] and
# FrontImage[NS] sheet tiles that the engine alpha-composites at runtime.
# Our 3D model produces a single render, so we diff against the same
# alpha-composite of the two reference tiles.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
TOOLS="$ROOT/models/tools"

SHEET="$ROOT/infrastructure/rail_bridges/rail_060_bridge.png"
DAT="$ROOT/infrastructure/rail_bridges/rail_060_bridge.dat"

# Extract Back and Front, then alpha-composite into the single reference.
# In rail_060_bridge.dat:
#   BackImage[NS][0]  = rail_060_bridge.1.0  (row 1, col 0)
#   FrontImage[NS][0] = rail_060_bridge.1.1  (row 1, col 1)
python3 "$TOOLS/crop_ref.py" "$SHEET" --row 1 --col 0 -o "$HERE/refs/back.png"
python3 "$TOOLS/crop_ref.py" "$SHEET" --row 1 --col 1 -o "$HERE/refs/front.png"
python3 - "$HERE/refs/back.png" "$HERE/refs/front.png" "$HERE/refs/reference.png" <<'PY'
import sys
from PIL import Image
back = Image.open(sys.argv[1]).convert("RGBA")
front = Image.open(sys.argv[2]).convert("RGBA")
out = Image.new("RGBA", back.size, (0, 0, 0, 0))
out = Image.alpha_composite(out, back)
out = Image.alpha_composite(out, front)
out.save(sys.argv[3])
PY

python3 "$HERE/scene.py"

# Print diff metrics + write debug image.
python3 "$TOOLS/diff.py" "$HERE/refs/reference.png" "$HERE/out.png" \
    --debug "$HERE/diff_debug.png"
