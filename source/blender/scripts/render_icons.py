"""Renders transparent top-front icons of the five light units for the faction emblems and the
production buttons (own artwork, replaces nothing from the original).  Output: assets/ui/icon_<unit>.png"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from mathutils import Vector  # noqa: E402

UNITS = ["ant_soldier", "beetle_ladybug", "spider_black_widow", "scorpion_savage", "wasp_assault"]
OUT = os.path.join(salib.ASSET_ROOT, "ui")


def render(unit, size=128):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(salib.BLEND_DIR, f"{unit}.blend"))
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        if o.name.startswith("Preview"):
            bpy.data.objects.remove(o, do_unlink=True)
    cam_data = bpy.data.cameras.new("IconCam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("IconCam", cam_data)
    sc.collection.objects.link(cam)
    # bounds of the mesh objects
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in sc.objects:
        if o.type == "MESH":
            for c in o.bound_box:
                p = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    center = (lo + hi) / 2
    extent = max(hi.x - lo.x, hi.y - lo.y) * 1.15
    cam_data.ortho_scale = extent
    cam.location = center + Vector((0, -0.35 * extent, 2.0 * extent))
    cam.rotation_euler = (Vector((0, 0, 0)) - cam.location + center).to_track_quat("-Z", "Y").to_euler()
    sun_data = bpy.data.lights.new("IconSun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("IconSun", sun_data)
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(35), math.radians(15), math.radians(-30))
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.device = "CPU"
    sc.render.film_transparent = True
    sc.render.resolution_x = size
    sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    sc.frame_set(1)
    path = os.path.join(OUT, f"icon_{unit}.png")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("ICON", path, flush=True)


if __name__ == "__main__":
    for u in [a for a in salib.script_args() if not a.startswith("-")] or UNITS:
        render(u)
