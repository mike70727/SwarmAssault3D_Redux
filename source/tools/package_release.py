"""Build the Windows release zip that players download from GitHub's Releases page.

It packs what is committed (git archive of HEAD: assets, docs, README, LICENSE, AUTHORS, RUN.txt),
so nobody's own settings, saves or logs can slip in, plus the game exe. The loose model textures are
left out (they are baked into the GLB models; only assets/textures/terrain is read at run time).

Build the exe first with the C runtime linked in, so players need no Visual C++ redistributable
(a separate target folder keeps the everyday builds' cache):

    cd source
    set CARGO_TARGET_DIR=target-win& set RUSTFLAGS=-C target-feature=+crt-static
    cargo build --release -p swarm_assault_3d

usage: python tools/package_release.py <version> <exe> <out dir>
   e.g. python tools/package_release.py v0.1.0 target-win/release/swarm_assault_3d.exe ../../dist
"""
import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

version, exe, out_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
repo = Path(__file__).resolve().parents[2]
name = f"SwarmAssault3D-Redux-{version}-windows-x64"
stage = out_dir / name
if stage.exists():
    raise SystemExit(f"{stage} exists already: move it away first")
if not exe.is_file():
    raise SystemExit(f"no exe at {exe}")

tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", "HEAD", "assets", "docs", "README.md", "LICENSE", "AUTHORS", "RUN.txt"], capture_output=True, check=True).stdout
stage.mkdir(parents=True)
with tarfile.open(fileobj=io.BytesIO(tar)) as t:
    t.extractall(stage, filter="data")
for d in (stage / "assets" / "textures").iterdir():
    if d.name != "terrain":
        shutil.rmtree(d)
shutil.copy2(exe, stage / "swarm_assault_3d.exe")

zip_path = out_dir / f"{name}.zip"
files = sorted(p for p in stage.rglob("*") if p.is_file())
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in files:
        z.write(p, Path(name) / p.relative_to(stage))
digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
unpacked = sum(p.stat().st_size for p in files)
print(f"{zip_path}: {zip_path.stat().st_size / 1e6:.1f} MB ({len(files)} files, {unpacked / 1e6:.1f} MB unpacked)")
print(f"sha256 {digest}")
