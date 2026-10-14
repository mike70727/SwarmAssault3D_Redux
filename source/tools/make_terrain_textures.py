#!/usr/bin/env python3
"""Generate the tileable ground textures of the 3-D terrain (our own procedural art).

Usage: tools/make_terrain_textures.py [assets/textures/terrain]   (needs numpy + Pillow)

For each tileset (normal, desert, swamp, candy) and each of its four ground layers
    ground - the open ground (sand, desert sand, swamp mud, candy sugar)
    bed    - the floor of the "water" (lake bed, tar pit, swamp bottom, syrup pool)
    rock   - the rock layer (pebbles, gravel, moss, biscuit crumbs)
    veg    - the ground under the vegetation layer (moss, cobbles, crystal, jelly)
it writes <tileset>_<layer>_albedo.png (RGB colour, alpha = height for height blending) and
<tileset>_<layer>_normal.png (tangent-space normal: x = +u, y = +v), all 512x512 and seamless.
Plus water_ripples_normal.png for the water surfaces.

The base colours were measured on the original game's ground tiles (two-means per tile family),
so the 3-D ground keeps the original's palette; the pictures themselves are generated here.
"""
import os
import sys

import numpy as np
from PIL import Image

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "textures", "terrain")
os.makedirs(OUT, exist_ok=True)
N = 512


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def fbm(seed, beta=2.0, lo=1.0, hi=None, n=N):
    """Tileable fractal noise (random-phase spectrum with 1/f^beta amplitude), normalised to 0..1."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n) * n
    f = np.sqrt(fx[None, :] ** 2 + fx[:, None] ** 2)
    amp = np.where(f >= lo, 1.0 / np.maximum(f, 1e-6) ** (beta / 2.0), 0.0)
    if hi is not None:
        amp = np.where(f <= hi, amp, 0.0)
    spec = amp * np.exp(2j * np.pi * rng.random((n, n)))
    v = np.real(np.fft.ifft2(spec))
    v -= v.min()
    return (v / max(v.max(), 1e-9)).astype(np.float32)


def worley(seed, count, n=N):
    """Tileable Worley noise: distance to the nearest / second nearest point and the nearest id."""
    from scipy.spatial import cKDTree

    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2))
    offs = np.array([(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)], np.float64)
    allp = (pts[None, :, :] + offs[:, None, :]).reshape(-1, 2)
    ids = np.tile(np.arange(count), 9)
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float64) / n
    d, idx = cKDTree(allp).query(np.stack([xs.ravel(), ys.ravel()], -1), k=2)
    scale = np.sqrt(count)
    f1 = (d[:, 0] * scale).reshape(n, n).astype(np.float32)
    f2 = (d[:, 1] * scale).reshape(n, n).astype(np.float32)
    return f1, f2, ids[idx[:, 0]].reshape(n, n)


def normal_map(h, strength):
    """Tangent-space normals from a tileable height map (x = +u, y = +v)."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5 * strength
    n = np.stack([-dx, -dy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n


def save(name, color, height, strength):
    color = np.clip(color, 0.0, 1.0)
    h = np.clip(height, 0.0, 1.0)
    rgba = np.concatenate([color, h[..., None]], -1)
    Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(OUT, f"{name}_albedo.png"))
    nm = normal_map(h, strength)
    Image.fromarray(((nm * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(OUT, f"{name}_normal.png"))
    print("wrote", name)


def tint(base, v, amount):
    """Base colour brightened/darkened by v in -1..1."""
    return base[None, None, :] * (1.0 + amount * v[..., None])


def mix(a, b, t):
    return a * (1 - t[..., None]) + b * t[..., None]


def per_cell(nid, seed, count):
    return np.random.default_rng(seed).random(count).astype(np.float32)[nid]


# ---- layer recipes --------------------------------------------------------------------------
def sand(seed, base, ripple=0.0, grain=0.35):
    g = fbm(seed, beta=0.6, lo=40)            # grain
    m = fbm(seed + 1, beta=2.4, lo=1, hi=24)  # low-frequency drifts
    h = 0.45 * m + 0.25 * g
    if ripple:
        ys, xs = np.mgrid[0:N, 0:N].astype(np.float32) / N
        warp = fbm(seed + 2, beta=2.6, hi=8)
        r = 0.5 + 0.5 * np.sin(2 * np.pi * (14 * ys + 3 * xs + 2.5 * warp))
        h = h + ripple * r
    col = tint(base, (m - 0.5) * 0.8 + (g - 0.5) * grain * 2, 0.25)
    speck = fbm(seed + 3, beta=0.2, lo=120) > 0.82
    col = np.where(speck[..., None], col * 0.72, col)
    return col, h / h.max(), 3.0


def pebbles(seed, base, gap, count, var=0.18, fill=0.62):
    """Round stones of varied size and colour lying in a gritty bed (not a paving pattern)."""
    f1, f2, nid = worley(seed, count)
    r = per_cell(nid, seed + 7, count)
    rad = fill * (0.7 + 0.6 * per_cell(nid, seed + 9, count))
    warp = (fbm(seed + 11, beta=1.4, lo=6) - 0.5) * 0.35
    t = np.clip((f1 + warp * rad) / rad, 0, 2)
    inside = np.clip((1.0 - t) * 7.0, 0, 1)
    h = np.sqrt(np.clip(1.0 - t ** 2, 0, 1)) * inside
    g = fbm(seed + 3, beta=0.5, lo=60)
    grit = fbm(seed + 4, beta=0.3, lo=90)
    stone = tint(base, (r - 0.5) * 2 * var + (g - 0.5) * 0.25, 1.0)
    bedc = tint(gap, (grit - 0.5) * 0.9, 0.4)
    col = mix(bedc, stone, inside)
    # contact shadow around each stone and a soft highlight on top
    col = col * (0.7 + 0.45 * h[..., None]) * (1.0 - 0.25 * np.clip((t - 1.0) * -1.0 + 0.3, 0, 1)[..., None] * (1 - inside[..., None]))
    return col, 0.08 + 0.92 * h, 7.0


def sugar(seed, base):
    """Candy ground: fine sugar grains with a few glittering crystals and crumbs."""
    g = fbm(seed, beta=0.2, lo=110)
    m = fbm(seed + 1, beta=2.2, lo=1, hi=30)
    f1, f2, nid = worley(seed + 2, 700)
    crumb = np.clip((0.32 - f1) * 9.0, 0, 1)
    h = 0.35 * m + 0.25 * g + 0.4 * crumb
    col = tint(base, (m - 0.5) * 0.5 + (g - 0.5) * 0.5, 0.3)
    spark = g > 0.9
    col = np.where(spark[..., None], np.minimum(col * 1.25 + 0.08, 1.0), col)
    col = col * (0.9 + 0.2 * crumb[..., None])
    return col, h, 4.0


def moss(seed, base, light, clumps=0.6):
    a = fbm(seed, beta=1.6, lo=6)
    b = fbm(seed + 1, beta=0.8, lo=30)
    h = 0.6 * a + 0.4 * b
    t = np.clip((h - 0.35) * 2.2, 0, 1)
    col = mix(np.broadcast_to(base * 0.7, (N, N, 3)), np.broadcast_to(light, (N, N, 3)), t * clumps)
    col = col * (0.85 + 0.3 * b[..., None])
    return col, h, 5.0


def bed(seed, base, dark=0.55):
    a = fbm(seed, beta=2.2, lo=2, hi=40)
    b = fbm(seed + 1, beta=0.8, lo=40)
    h = 0.7 * a + 0.3 * b
    col = tint(base * dark, (h - 0.5) * 1.2, 0.3)
    return col, h, 2.0


def sculpted(seed, base):
    """Swamp mud: wavy ridges and worm trails like the original's sculpted ground."""
    w = fbm(seed, beta=2.8, hi=10)
    ridges = 1.0 - np.abs(np.sin(2 * np.pi * (w * 4.0)))
    fine = fbm(seed + 1, beta=0.8, lo=40)
    h = 0.45 * ridges + 0.35 * fbm(seed + 2, beta=2.0, hi=20) + 0.2 * fine
    col = tint(base, (h - 0.5) * 0.9, 0.2)
    return col, h, 5.0


def crystals(seed, base, count=70):
    f1, f2, nid = worley(seed, count)
    r = per_cell(nid, seed + 5, count)
    edge = np.clip((f2 - f1) * 4.0, 0, 1)
    facet = np.clip(1.0 - f1 * 1.1, 0, 1)
    h = (0.5 * facet + 0.5 * r) * edge ** 0.5
    spark = (fbm(seed + 2, beta=0.1, lo=150) > 0.86) & (edge > 0.3)
    col = tint(base, (r - 0.5) * 0.7 + (facet - 0.5) * 0.6, 0.6)
    col = np.where(spark[..., None], col * 1.0 + 0.35, col)
    col = col * (0.6 + 0.4 * edge[..., None])
    return col, h, 7.0


def jelly(seed, base, gap, count=36):
    f1, f2, nid = worley(seed, count)
    edge = np.clip((f2 - f1) * 3.0, 0, 1)
    h = np.sqrt(np.clip(1.0 - (f1 * 1.05) ** 2, 0, 1)) * edge ** 0.4
    col = tint(base, (h - 0.5) * 0.9, 0.7)
    col = mix(np.broadcast_to(gap, col.shape), col, np.clip(edge * 3, 0, 1))
    return col, 0.1 + 0.9 * h, 4.0


def crumbs(seed, base, gap, count=260):
    f1, f2, nid = worley(seed, count)
    r = per_cell(nid, seed + 3, count)
    edge = np.clip((f2 - f1) * 2.5, 0, 1)
    rough = fbm(seed + 1, beta=0.6, lo=50)
    h = np.clip(1.0 - f1 * 0.9, 0, 1) * edge ** 0.5 * (0.7 + 0.3 * rough)
    col = tint(base, (r - 0.5) * 0.5 + (rough - 0.5) * 0.4, 0.8)
    col = mix(np.broadcast_to(gap, col.shape), col, np.clip(edge * 2.2, 0, 1))
    return col, 0.1 + 0.9 * h, 6.0


# ---- the four tilesets ----------------------------------------------------------------------
# colours measured on the original tiles (ground = family B, the others by two-means per family)
SETS = {
    "normal": dict(
        ground=lambda: sand(11, hexc("#b39272"), grain=0.4),
        bed=lambda: bed(12, hexc("#8f7a62"), dark=0.6),
        rock=lambda: pebbles(13, hexc("#7c7464"), hexc("#5e5342"), 320, var=0.32, fill=0.5),
        veg=lambda: moss(14, hexc("#36512d"), hexc("#4f7a3a")),
    ),
    "desert": dict(
        ground=lambda: sand(21, hexc("#c4844c"), ripple=0.35, grain=0.3),
        bed=lambda: bed(22, hexc("#5a4436"), dark=0.6),
        rock=lambda: pebbles(23, hexc("#8a837c"), hexc("#a8774c"), 380, var=0.25, fill=0.55),
        veg=lambda: pebbles(24, hexc("#6e5a4c"), hexc("#4a3a30"), 46, var=0.3, fill=0.56),
    ),
    "swamp": dict(
        ground=lambda: sculpted(31, hexc("#6d6b52")),
        bed=lambda: bed(32, hexc("#4d4c38"), dark=0.65),
        rock=lambda: moss(33, hexc("#3a4a26"), hexc("#5d7a2f"), clumps=0.8),
        veg=lambda: crystals(34, hexc("#3c5468")),
    ),
    "candy": dict(
        ground=lambda: sugar(41, hexc("#b4a392")),
        bed=lambda: bed(42, hexc("#8c7a76"), dark=0.7),
        rock=lambda: crumbs(43, hexc("#83644f"), hexc("#4a3226"), count=160),
        veg=lambda: jelly(44, hexc("#7e2a24"), hexc("#6a4a36"), count=24),
    ),
}

for tileset, layers in SETS.items():
    for layer, make in layers.items():
        col, h, strength = make()
        save(f"{tileset}_{layer}", col, h, strength)

# water surface ripples (two octaves, tileable)
rip = 0.75 * fbm(91, beta=3.0, lo=2, hi=14) + 0.25 * fbm(92, beta=2.0, lo=10, hi=40)
nm = normal_map(rip, 5.0)
Image.fromarray(((nm * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(OUT, "water_ripples_normal.png"))
print("wrote water_ripples_normal")
