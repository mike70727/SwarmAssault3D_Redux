#!/usr/bin/env bash
# Rebuild every Blender asset (models, rigs, clips, GLB exports, previews, .blend files).
# Usage: tools/build_assets.sh [python-with-bpy]     (default .venv-bpy/bin/python, see blender/README.md)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-.venv-bpy/bin/python}"
for script in build_ant build_beetle build_spider build_scorpion build_flyers build_colony build_environment; do
  echo "=== $script"
  "$PY" "blender/scripts/$script.py" --all 2>&1 | grep -E "BUILT|Traceback|Error|assert|line [0-9]+, in" || true
done
echo "models:"; ls assets/models | wc -l
