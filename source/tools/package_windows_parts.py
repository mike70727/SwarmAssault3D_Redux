#!/usr/bin/env python3
"""Split the staged Windows package (dist/SwarmAssault3D-windows-x64, made by tools/package_windows.sh)
into zip parts of at most MAX_MIB each. Every part holds the same top-level folder, so extracting all
parts into one place gives the complete game folder (exe + assets + docs).

Usage: tools/package_windows_parts.py [max_mib] [name-prefix]   (default 29.5, SwarmAssault3D-windows-x64)
"""
import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STAGE = os.path.join(ROOT, "dist", "SwarmAssault3D-windows-x64")
TOP = "SwarmAssault3D-windows-x64"
MAX_MIB = float(sys.argv[1]) if len(sys.argv) > 1 else 29.5
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "SwarmAssault3D-windows-x64"

NOTE = """Swarm Assault 3D - Windows x64 build, split into parts for download.

Extract EVERY part into the same folder (they all contain the folder "SwarmAssault3D-windows-x64").
When all parts are extracted the folder holds swarm_assault_3d.exe, assets\\, docs\\ and RUN.txt.
Then double-click swarm_assault_3d.exe (the assets folder must stay next to it).
"""


def compressed_size(path):
    """Compressed size of a single file (estimate by actually deflating it once)."""
    tmp = path + ".zsize"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(path, "x")
    n = os.path.getsize(tmp)
    os.remove(tmp)
    return n


def main():
    if not os.path.isdir(STAGE):
        sys.exit("run tools/package_windows.sh first")
    limit = MAX_MIB * 1024 * 1024
    files = []
    for d, _, fs in os.walk(STAGE):
        for f in fs:
            p = os.path.join(d, f)
            files.append(p)
    # the executable first (largest), then everything else in path order
    exe = [p for p in files if p.endswith(".exe")]
    rest = sorted(p for p in files if not p.endswith(".exe"))
    sizes = {p: compressed_size(p) for p in exe}
    for p in rest:
        sizes[p] = compressed_size(p) if os.path.getsize(p) > 65536 else os.path.getsize(p)
    parts, cur, cur_size = [], [], len(NOTE)
    for p in exe + rest:
        s = sizes[p] + 128
        if s > limit:
            sys.exit(f"{p} alone exceeds the part size ({s / 1048576:.1f} MiB)")
        if cur and cur_size + s > limit:
            parts.append(cur)
            cur, cur_size = [], 0
        cur.append(p)
        cur_size += s
    if cur:
        parts.append(cur)
    n = len(parts)
    for i, part in enumerate(parts, 1):
        zpath = os.path.join(ROOT, "dist", f"{PREFIX}-part{i}of{n}.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr(f"{TOP}/EXTRACT_ALL_PARTS.txt", NOTE)
            for p in part:
                z.write(p, f"{TOP}/" + os.path.relpath(p, STAGE).replace(os.sep, "/"))
        print(f"{os.path.basename(zpath)}  {os.path.getsize(zpath) / 1048576:6.1f} MiB  {len(part)} files")


if __name__ == "__main__":
    main()
