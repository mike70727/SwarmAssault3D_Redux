#!/usr/bin/env bash
# Package the cross-compiled Windows build with its assets, docs and editable sources.
# Usage: tools/package_windows.sh [target-dir] [--lite]   (default target-win; --lite omits the sources)
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET_DIR="${1:-target-win}"
LITE=0; for a in "$@"; do [ "$a" = "--lite" ] && LITE=1; done
[ "$TARGET_DIR" = "--lite" ] && TARGET_DIR=target-win
EXE="$TARGET_DIR/x86_64-pc-windows-gnu/release/swarm_assault_3d.exe"
if [ ! -f "$EXE" ]; then
  echo "missing $EXE - build first:"
  echo "  CARGO_TARGET_DIR=$TARGET_DIR cargo build --release -p swarm_assault_3d --target x86_64-pc-windows-gnu"
  exit 1
fi
OUT=dist/SwarmAssault3D-windows-x64
rm -rf "$OUT" && mkdir -p "$OUT"
cp "$EXE" "$OUT/"
# mingw runtime DLLs the GNU target may need (only copied when the build actually links them dynamically)
for dll in libgcc_s_seh-1.dll libstdc++-6.dll libwinpthread-1.dll; do
  f=$(find /usr/lib/gcc/x86_64-w64-mingw32 /usr/x86_64-w64-mingw32/lib -name "$dll" 2>/dev/null | head -1 || true)
  if [ -n "$f" ] && x86_64-w64-mingw32-objdump -p "$EXE" 2>/dev/null | grep -qi "$dll"; then cp "$f" "$OUT/"; fi
done
cp -r assets "$OUT/assets"
rm -rf "$OUT/assets/textures"   # baked maps are embedded in the GLBs; the loose JPEGs are only for editing
mkdir -p "$OUT/docs" && cp docs/*.md "$OUT/docs/" && cp -r docs/screenshots "$OUT/docs/" 2>/dev/null || true
cp README.md LICENSE "$OUT/" 2>/dev/null || true
# complete package: the loose baked textures, and the editable project sources (Rust crates, tools,
# Blender scripts, .blend files and preview sheets)
if [ "$LITE" = 0 ]; then
  cp -r assets/textures "$OUT/assets/textures"
  mkdir -p "$OUT/source"
  cp -r crates tools Cargo.toml Cargo.lock rust-toolchain.toml .cargo "$OUT/source/"
  mkdir -p "$OUT/source/blender" && cp -r blender/scripts blender/blend blender/previews blender/README.md "$OUT/source/blender/"
  cp .gitignore "$OUT/source/" 2>/dev/null || true
fi
cat > "$OUT/RUN.txt" <<'EOF'
Swarm Assault 3D - Windows x64 build (cross-compiled with mingw-w64, untested on Windows hardware)

Double-click swarm_assault_3d.exe (keep the assets folder next to it).
Command line options: swarm_assault_3d.exe --help
Settings: assets\data\settings.ron   Controls: assets\data\controls.ron
Docs: docs\  (BUILD_WINDOWS.md has a manual test checklist)
Sources (complete package only): source\ holds the Rust workspace (crates\, Cargo.toml, tools\;
  build with cargo build --release -p swarm_assault_3d from source\ with this assets\ folder copied or
  linked next to it) and source\blender\ (bpy scripts, .blend files with packed textures, previews).
EOF
ZIP=SwarmAssault3D-windows-x64.zip; [ "$LITE" = 1 ] && ZIP=SwarmAssault3D-windows-x64-lite.zip
( cd dist && rm -f "$ZIP" && zip -qr -9 "$ZIP" SwarmAssault3D-windows-x64 )
ls -la "dist/$ZIP"
echo "exe: $(file "$EXE")"
