#!/usr/bin/env bash
# Run the game without a GPU/display (what the automated test runs used): Xvfb + Mesa lavapipe.
# Usage: tools/run_headless.sh [game args...]
# Example: tools/run_headless.sh --map five_families.ron --autoplay --speed 2 --screenshot-after 15 --quit-after 92
set -euo pipefail
cd "$(dirname "$0")/.."
export DISPLAY="${DISPLAY_NUM:-:99}"
export VK_ICD_FILENAMES="${VK_ICD_FILENAMES:-/usr/share/vulkan/icd.d/lvp_icd.json}"
export WGPU_BACKEND=vulkan
export RUST_LOG="${RUST_LOG:-warn,swarm_assault_3d=info}"
if ! pgrep -x Xvfb >/dev/null; then
  Xvfb "$DISPLAY" -screen 0 1280x720x24 >/tmp/xvfb.log 2>&1 &
  sleep 1
fi
BIN=target/release/swarm_assault_3d
[ -x "$BIN" ] || BIN=target/debug/swarm_assault_3d
[ -x "$BIN" ] || cargo build -p swarm_assault_3d
exec "$BIN" "$@"
