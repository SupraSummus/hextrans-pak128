#!/usr/bin/env bash
# Render the bridge in two layers and diff each against the matching
# pak128 sheet entry (multi-view supervision).
#
# Pak128 layout (from rail_060_bridge.dat):
#   BackImage[NS][0]  = rail_060_bridge.1.0  (sheet row 1, col 0)
#   FrontImage[NS][0] = rail_060_bridge.1.1  (sheet row 1, col 1)
# The engine draws Back with the way (behind vehicles), then the
# vehicle, then Front on top. Back is the full bridge silhouette;
# Front is just the front-side railing.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
TOOLS="$ROOT/models/tools"

SHEET="$ROOT/infrastructure/rail_bridges/rail_060_bridge.png"

python3 "$TOOLS/crop_ref.py" "$SHEET" --row 1 --col 0 -o "$HERE/refs/back.png"
python3 "$TOOLS/crop_ref.py" "$SHEET" --row 1 --col 1 -o "$HERE/refs/front.png"

python3 "$HERE/scene.py"

echo "=== back ==="
python3 "$TOOLS/diff.py" "$HERE/refs/back.png" "$HERE/out_back.png" \
    --debug "$HERE/diff_debug_back.png"
echo "=== front ==="
python3 "$TOOLS/diff.py" "$HERE/refs/front.png" "$HERE/out_front.png" \
    --debug "$HERE/diff_debug_front.png"
