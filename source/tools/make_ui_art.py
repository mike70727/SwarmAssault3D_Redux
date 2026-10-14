#!/usr/bin/env python3
"""Generates the red pixel cursors (own work, in the style of the original's red arrow / crosshair /
selection bracket): assets/ui/cursor_arrow.png, cursor_attack.png, cursor_select.png.
The rest of the interface art is rendered in Blender by blender/scripts/build_ui_chrome.py.
Requires Pillow."""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "ui")
os.makedirs(OUT, exist_ok=True)


# cursors: red arrow (default), crosshair (attack / attack-move), bracket (select)
def cursor_arrow():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    pts = [(2, 2), (2, 24), (8, 18), (13, 28), (17, 26), (12, 16), (20, 16)]
    g.polygon(pts, fill=(200, 30, 24, 255), outline=(60, 0, 0, 255))
    g.line(pts + [pts[0]], fill=(255, 150, 140, 255), width=1)
    return img

def cursor_cross():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    g.ellipse([5, 5, 26, 26], outline=(200, 30, 24, 255), width=3)
    for a, b in (((15, 1), (15, 9)), ((15, 22), (15, 30)), ((1, 15), (9, 15)), ((22, 15), (30, 15))):
        g.line([a, b], fill=(200, 30, 24, 255), width=3)
    return img

def cursor_bracket():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    for (x, y, dx, dy) in ((3, 3, 1, 1), (28, 3, -1, 1), (3, 28, 1, -1), (28, 28, -1, -1)):
        g.line([(x, y), (x + 8 * dx, y)], fill=(200, 30, 24, 255), width=3)
        g.line([(x, y), (x, y + 8 * dy)], fill=(200, 30, 24, 255), width=3)
    return img

cursor_arrow().save(os.path.join(OUT, "cursor_arrow.png"))
cursor_cross().save(os.path.join(OUT, "cursor_attack.png"))
cursor_bracket().save(os.path.join(OUT, "cursor_select.png"))

print("cursors written to", OUT)
