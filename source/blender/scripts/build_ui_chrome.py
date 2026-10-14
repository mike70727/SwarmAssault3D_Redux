"""Renders the interface chrome in Blender/Cycles, the way the original's pre-rendered panels were made.

Own artwork (nothing is copied from the game): a mottled stone slab with bevelled steel pipes, the
honeycomb emblem plate, the radar rim, the breeding buttons, the red bar rail, the LED mount, the
dialog frame, the black command bar and the five faction insignia (coloured plates with the unit
models embossed on them).  Layout follows the original 226x448 sidebar; the slab continues below it
for tall windows.  Everything is rendered at 2x and downsampled to assets/ui/.

    bpyenv/bin/python blender/scripts/build_ui_chrome.py            # everything
    bpyenv/bin/python blender/scripts/build_ui_chrome.py sidebar    # one piece (sidebar, buttons,
                                                                    # bars, leds, dialog, blackbar,
                                                                    # emblems)
Environment: SAMPLES (default 96), SCALE (default 2).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import salib  # noqa: E402
from mathutils import Vector  # noqa: E402

OUT = os.path.join(salib.ASSET_ROOT, "ui")
SAMPLES = int(os.environ.get("SAMPLES", "96"))
SCALE = int(os.environ.get("SCALE", "2"))
W, H_TOP, H = 226, 448, 1080

# --------------------------------------------------------------------------------------------
# geometry helpers (image coordinates: x right, y down; 1 unit = 1 pixel; z up towards the camera)
# --------------------------------------------------------------------------------------------


def P(x, y, z=0.0):
    return Vector((x, -y, z))


def rounded_rect(x0, y0, x1, y1, r, n=7):
    """Points of a rounded rectangle (image coords), clockwise from the top-left arc."""
    pts = []
    corners = ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180))
    for cx, cy, start in corners:
        for i in range(n + 1):
            a = math.radians(start + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def regular_polygon(cx, cy, r, sides, rot=0.0):
    return [(cx + r * math.cos(math.radians(rot + 360 * i / sides)), cy + r * math.sin(math.radians(rot + 360 * i / sides))) for i in range(sides)]


def star(cx, cy, r_out, r_in, points):
    pts = []
    for i in range(points * 2):
        a = math.radians(-90 + 180 * i / points)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def mesh_object(name, verts, faces, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    return ob


def plate(name, pts, z, height, bevel, mat, segments=4, smooth=True):
    """Extruded polygon with bevelled top edges (a raised metal/plastic plate)."""
    verts = [P(x, y, z) for x, y in pts]
    ob = mesh_object(name, verts, [list(range(len(verts)))], mat)
    sol = ob.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = height
    sol.offset = 1.0
    sol.use_even_offset = True
    if bevel > 0:
        bv = ob.modifiers.new("Bevel", "BEVEL")
        bv.width = bevel
        bv.segments = segments
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(40)
    if smooth:
        for p in ob.data.polygons:
            p.use_smooth = True
        ob.data.shade_smooth()
        if hasattr(ob.data, "set_sharp_from_angle"):
            ob.data.set_sharp_from_angle(angle=math.radians(50))
    return ob


def ring(name, outer, inner, z, height, bevel, mat, segments=4):
    """Raised rim between two loops with the same point count (frames of the insets)."""
    n = len(outer)
    assert len(inner) == n
    verts = [P(x, y, z) for x, y in outer] + [P(x, y, z) for x, y in inner]
    faces = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    ob = mesh_object(name, verts, faces, mat)
    sol = ob.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = height
    sol.offset = 1.0
    sol.use_even_offset = True
    if bevel > 0:
        bv = ob.modifiers.new("Bevel", "BEVEL")
        bv.width = bevel
        bv.segments = segments
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(40)
    ob.data.shade_smooth()
    if hasattr(ob.data, "set_sharp_from_angle"):
        ob.data.set_sharp_from_angle(angle=math.radians(50))
    return ob


def pipe(name, pts, radius, mat, z=0.0, cyclic=False, res=10):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = res
    cu.fill_mode = "FULL"
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        sp.points[i].co = (x, -y, z, 1.0)
    sp.use_cyclic_u = cyclic
    sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    cu.materials.append(mat)
    return ob


def sphere(name, x, y, z, r, mat, flatten=1.0):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=16, location=P(x, y, z))
    ob = bpy.context.object
    ob.name = name
    ob.scale.z = flatten
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


def cylinder(name, x, y, z, r, h, mat, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=P(x, y, z + h / 2))
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    bv = ob.modifiers.new("Bevel", "BEVEL")
    bv.width = min(1.2, h * 0.4)
    bv.segments = 3
    bpy.ops.object.shade_smooth()
    if hasattr(ob.data, "set_sharp_from_angle"):
        ob.data.set_sharp_from_angle(angle=math.radians(50))
    return ob


def flat(name, pts, z, mat):
    verts = [P(x, y, z) for x, y in pts]
    return mesh_object(name, verts, [list(range(len(verts)))], mat)


def rivet(x, y, z, mat, r=2.6):
    return sphere("Rivet", x, y, z, r, mat, flatten=0.6)


# --------------------------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------------------------


def _principled(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    return mat, nt, bsdf


def lin(c):
    return (*salib.srgb_to_linear(c), 1.0)


def mat_metal(name="M_Steel", color=(0.58, 0.55, 0.50), rough=0.34, anis=0.0):
    mat, nt, bsdf = _principled(name)
    bsdf.inputs["Base Color"].default_value = lin(color)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = rough
    # faint brushed grain
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 0.6
    tex.inputs["Detail"].default_value = 6.0
    tex.inputs["Roughness"].default_value = 0.7
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.15, 1.0, 1.0)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (rough * 0.8, rough * 0.8, rough * 0.8, 1)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (min(1, rough * 1.35), min(1, rough * 1.35), min(1, rough * 1.35), 1)
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    return mat


def mat_stone(name="M_Stone"):
    """Dark mottled granite: warm brown-olive base, lighter marbled streaks, a few reddish flecks."""
    mat, nt, bsdf = _principled(name)
    bsdf.inputs["Roughness"].default_value = 0.88
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")  # large mottling
    n1.inputs["Scale"].default_value = 0.045
    n1.inputs["Detail"].default_value = 10.0
    n1.inputs["Roughness"].default_value = 0.66
    n1.inputs["Distortion"].default_value = 0.9
    n2 = nt.nodes.new("ShaderNodeTexNoise")  # fine grain and flecks
    n2.inputs["Scale"].default_value = 0.4
    n2.inputs["Detail"].default_value = 5.0
    n2.inputs["Roughness"].default_value = 0.5
    n3 = nt.nodes.new("ShaderNodeTexNoise")  # marbled streaks
    n3.inputs["Scale"].default_value = 0.03
    n3.inputs["Detail"].default_value = 7.0
    n3.inputs["Roughness"].default_value = 0.6
    n3.inputs["Distortion"].default_value = 2.5
    for n in (n1, n2, n3):
        nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.30
    cr.elements[0].color = lin((0.07, 0.06, 0.045))
    cr.elements[1].position = 0.56
    cr.elements[1].color = lin((0.25, 0.22, 0.16))
    e = cr.elements.new(0.80)
    e.color = lin((0.46, 0.42, 0.32))
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    # streaks: narrow band of the distorted noise lightens the surface
    sramp = nt.nodes.new("ShaderNodeValToRGB")
    sramp.color_ramp.elements[0].position = 0.47
    sramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    sramp.color_ramp.elements[1].position = 0.52
    sramp.color_ramp.elements[1].color = (0.8, 0.75, 0.62, 1)
    e2 = sramp.color_ramp.elements.new(0.57)
    e2.color = (0, 0, 0, 1)
    nt.links.new(n3.outputs["Fac"], sramp.inputs["Fac"])
    mix_streak = nt.nodes.new("ShaderNodeMix")
    mix_streak.data_type = "RGBA"
    mix_streak.blend_type = "ADD"
    mix_streak.inputs["Factor"].default_value = 0.16
    nt.links.new(ramp.outputs["Color"], mix_streak.inputs[6])
    nt.links.new(sramp.outputs["Color"], mix_streak.inputs[7])
    framp = nt.nodes.new("ShaderNodeValToRGB")
    framp.color_ramp.elements[0].position = 0.64
    framp.color_ramp.elements[0].color = (0, 0, 0, 1)
    framp.color_ramp.elements[1].position = 0.78
    framp.color_ramp.elements[1].color = lin((0.42, 0.14, 0.09))
    nt.links.new(n2.outputs["Fac"], framp.inputs["Fac"])
    mix_fleck = nt.nodes.new("ShaderNodeMix")
    mix_fleck.data_type = "RGBA"
    mix_fleck.blend_type = "ADD"
    mix_fleck.inputs["Factor"].default_value = 0.35
    nt.links.new(mix_streak.outputs[2], mix_fleck.inputs[6])
    nt.links.new(framp.outputs["Color"], mix_fleck.inputs[7])
    nt.links.new(mix_fleck.outputs[2], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 1.2
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mat_plain(name, color, rough=0.5, metallic=0.0, emission=None, strength=0.0):
    mat, nt, bsdf = _principled(name)
    bsdf.inputs["Base Color"].default_value = lin(color)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = lin(emission)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def mat_black(name="M_Screen"):
    mat = mat_plain(name, (0.003, 0.003, 0.004), rough=0.55)
    mat.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.08
    return mat


# --------------------------------------------------------------------------------------------
# scene
# --------------------------------------------------------------------------------------------


def new_scene(name):
    sc = salib.reset_scene(name)
    world = sc.world
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.26, 0.27, 0.30, 1.0)
    bg.inputs[1].default_value = 1.0
    # key light from the upper left (highlights on the top-left of every bevel, like the reference)
    sun_data = bpy.data.lights.new("Key", "SUN")
    sun_data.energy = 3.2
    sun_data.angle = math.radians(4)
    sun = bpy.data.objects.new("Key", sun_data)
    sc.collection.objects.link(sun)
    sun.rotation_euler = Vector((0.9, -0.75, -1.6)).to_track_quat("-Z", "Y").to_euler()
    # broad soft light for the metal streaks
    area_data = bpy.data.lights.new("Fill", "AREA")
    area_data.energy = 70000.0
    area_data.size = 600.0
    area = bpy.data.objects.new("Fill", area_data)
    sc.collection.objects.link(area)
    area.location = P(-150, -120, 520)
    area.rotation_euler = Vector((0.45, -0.3, -1.0)).to_track_quat("-Z", "Y").to_euler()
    rim_data = bpy.data.lights.new("Rim", "SUN")
    rim_data.energy = 0.9
    rim_data.angle = math.radians(10)
    rim = bpy.data.objects.new("Rim", rim_data)
    sc.collection.objects.link(rim)
    rim.rotation_euler = Vector((-0.6, 0.8, -1.2)).to_track_quat("-Z", "Y").to_euler()
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.resolution_percentage = 100
    return sc


def camera(sc, x0, y0, w, h):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(w, h)
    cam_data.clip_end = 5000
    cam = bpy.data.objects.new("Cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = P(x0 + w / 2, y0 + h / 2, 800)
    cam.rotation_euler = (0, 0, 0)
    sc.camera = cam
    sc.render.resolution_x = w * SCALE
    sc.render.resolution_y = h * SCALE
    return cam


def render(sc, path, w, h, transparent=True):
    sc.render.film_transparent = transparent
    tmp = path + ".2x.png"
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    from PIL import Image

    im = Image.open(tmp).convert("RGBA")
    im = im.resize((w, h), Image.LANCZOS)
    im.save(path)
    os.remove(tmp)
    print("CHROME", path, im.size, flush=True)


# --------------------------------------------------------------------------------------------
# pieces
# --------------------------------------------------------------------------------------------


def stone_slab(name, pts, mat, thickness=6.0, displace=1.6):
    """Rough slab: filled polygon, subdivided and displaced by a cloud texture."""
    ob = plate(name, pts, -thickness, thickness, 0.0, mat, smooth=False)
    sub = ob.modifiers.new("Subdiv", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = 6
    sub.render_levels = 7
    tex = bpy.data.textures.new(name + "_tex", "CLOUDS")
    tex.noise_scale = 15.0
    tex.noise_depth = 5
    disp = ob.modifiers.new("Displace", "DISPLACE")
    disp.texture = tex
    disp.strength = displace * 1.4
    disp.mid_level = 0.5
    disp.texture_coords = "GLOBAL"
    return ob


def inset_screen(name, x0, y0, x1, y1, r, rim, mats, z=0.0, height=3.5, bevel=1.6, depth=1.5):
    """Black screen sunk into the slab with a raised rounded rim around it."""
    outer = rounded_rect(x0 - rim, y0 - rim, x1 + rim, y1 + rim, r + rim)
    inner = rounded_rect(x0, y0, x1, y1, r)
    ring(name + "_rim", outer, inner, z, height, bevel, mats["steel"])
    flat(name + "_screen", rounded_rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1, r), z - depth, mats["screen"])
    # inner shadow lip
    ring(name + "_lip", inner, rounded_rect(x0 + 1.5, y0 + 1.5, x1 - 1.5, y1 - 1.5, max(1, r - 1.5)), z - depth + 0.2, 1.3, 0.5, mats["dark"])


def hex_plate(mats, cx=113, cy=43):
    pts = regular_polygon(cx, cy, 25, 6, rot=30)
    plate("EmblemPlate", pts, 1.0, 3.0, 1.4, mats["steel"])
    # honeycomb: three recessed hexagonal cells
    for dx, dy in ((-7.5, -4.5), (7.5, -4.5), (0, 8.5)):
        cell = regular_polygon(cx + dx, cy + dy, 6.2, 6, rot=30)
        ring("Cell_rim", regular_polygon(cx + dx, cy + dy, 7.2, 6, rot=30), cell, 4.0, 0.8, 0.4, mats["steel_dark"])
        flat("Cell", cell, 1.3, mats["dark"])


def buttons_rail(mats):
    # pipe at the button row, from the frame to the buttons
    pipe("ButtonPipe", [(6, 355), (220, 355)], 3.2, mats["steel"], z=0.5)
    # rail with the three red bar slots
    x0, y0, x1, y1 = 16, 386, 210, 414
    outer = rounded_rect(x0, y0, x1, y1, 9)
    inner = rounded_rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, 5)
    ring("Rail_rim", outer, inner, 0.0, 4.0, 1.8, mats["steel"])
    flat("Rail_floor", rounded_rect(x0 + 3, y0 + 3, x1 - 3, y1 - 3, 5), 0.6, mats["steel_dark"])
    for bx in (25, 86, 146):
        slot = rounded_rect(bx, 393, bx + 52, 405, 2.5)
        ring("Slot_rim", rounded_rect(bx - 1.2, 391.8, bx + 53.2, 406.2, 3.5), slot, 0.8, 1.0, 0.4, mats["dark"])
        flat("Slot", slot, 0.2, mats["slot"])
    cylinder("RailBoltL", 21, 400, 4.0, 4.0, 2.2, mats["steel"])
    cylinder("RailBoltR", 205, 400, 4.0, 4.0, 2.2, mats["steel"])
    # LED loop and mount
    pipe("LedPipe", [(53, 414), (53, 428), (170, 428), (170, 414)], 1.8, mats["steel"], z=0.3)
    cylinder("LedMount", 113, 428, 0.0, 9.5, 3.2, mats["steel"])
    cylinder("LedMountInner", 113, 428, 3.2, 6.2, 1.0, mats["steel_dark"])
    flat("LedWell", regular_polygon(113, 428, 5.2, 32), 3.4, mats["dark"])


def build_sidebar(mats):
    sc = bpy.context.scene
    stone_slab("Slab", [(-4, -4), (W + 4, -4), (W + 4, H + 4), (-4, H + 4)], mats["stone"])
    steel = mats["steel"]
    # outer frame and dividers
    pipe("Frame", rounded_rect(6, 6, 220, H - 6, 14), 5.2, steel, z=0.5, cyclic=True)
    pipe("TopDivider", [(6, 48), (220, 48)], 3.2, steel, z=0.3)
    pipe("PlatePipeL", [(105, 0), (105, 32)], 2.4, steel, z=0.8)
    pipe("PlatePipeR", [(121, 0), (121, 32)], 2.4, steel, z=0.8)
    pipe("PlatePipeDown", [(113, 60), (113, 104)], 2.4, steel, z=0.8)
    hex_plate(mats)
    # timer pill
    pill = rounded_rect(13, 19, 66, 34, 7)
    ring("Pill_rim", rounded_rect(11.5, 17.5, 67.5, 35.5, 8.5), pill, 0.3, 1.6, 0.7, steel)
    flat("Pill_screen", pill, -0.6, mats["screen"])
    # radar
    inset_screen("Radar", 13, 108, 215, 310, 9, 7, mats, height=4.0, bevel=2.0)
    for x, y in ((9, 104), (219, 104), (9, 314), (219, 314)):
        rivet(x, y, 4.0, steel)
    buttons_rail(mats)
    # lower section (3-D version only): selection screen between two dividers
    pipe("MidDivider", [(6, 452), (220, 452)], 3.2, steel, z=0.3)
    inset_screen("Select", 17, 468, 211, 564, 8, 6, mats, height=3.5, bevel=1.6)
    pipe("LowDivider", [(6, 586), (220, 586)], 3.2, steel, z=0.3)
    for y in range(640, H - 40, 88):
        rivet(6, y, 5.5, steel, r=2.4)
        rivet(220, y, 5.5, steel, r=2.4)
    for x, y in ((6, 452), (220, 452), (6, 586), (220, 586), (6, 48), (220, 48), (6, 355), (220, 355)):
        rivet(x, y, 5.6, steel, r=2.4)
    camera(sc, 0, 0, W, H)
    render(sc, os.path.join(OUT, "sidebar.png"), W, H, transparent=False)


def metal_button(mats, name, size=50, pressed=False):
    sc = bpy.context.scene
    r = 11
    m = 2
    body = mats["steel"] if not pressed else mats["steel_pressed"]
    plate("Btn_rim", rounded_rect(m, m, size - m, size - m, r), 0.0, 2.0, 0.9, mats["steel_dark"])
    h = 7.0 if not pressed else 3.0
    plate("Btn_body", rounded_rect(m + 3, m + 3, size - m - 3, size - m - 3, r - 2), 2.0, h, 3.0 if not pressed else 1.4, body, segments=6)
    camera(sc, 0, 0, size, size)
    render(sc, os.path.join(OUT, f"{name}.png"), size, size)


def dialog_button(mats, name, w=160, h=32, tone="normal"):
    sc = bpy.context.scene
    color = {"normal": (0.52, 0.42, 0.33), "hover": (0.66, 0.55, 0.44), "pressed": (0.30, 0.24, 0.19), "disabled": (0.28, 0.25, 0.22)}[tone]
    body = mat_plain("M_Btn_" + tone, color, rough=0.5, metallic=0.35)
    plate("DBtn_rim", rounded_rect(1, 1, w - 1, h - 1, 11), 0.0, 1.6, 0.7, mats["steel_dark"])
    plate("DBtn_body", rounded_rect(3, 3, w - 3, h - 3, 9), 1.6, 4.5 if tone != "pressed" else 2.0, 2.2 if tone != "pressed" else 1.0, body, segments=5)
    camera(sc, 0, 0, w, h)
    render(sc, os.path.join(OUT, f"{name}.png"), w, h)


def dialog_frame(mats, size=160):
    """Stone frame with a pipe border and a dark green glass inside (9-slice, border 30)."""
    sc = bpy.context.scene
    stone_slab("DlgSlab", rounded_rect(0, 0, size, size, 14), mats["stone"], displace=1.2)
    pipe("DlgFrame", rounded_rect(6, 6, size - 6, size - 6, 10), 4.2, mats["steel"], z=0.5, cyclic=True)
    inner = rounded_rect(22, 22, size - 22, size - 22, 8)
    ring("DlgRim", rounded_rect(17, 17, size - 17, size - 17, 11), inner, 0.0, 3.2, 1.5, mats["steel"])
    flat("DlgGlass", rounded_rect(21, 21, size - 21, size - 21, 8), -1.2, mats["glass"])
    for x, y in ((12, 12), (size - 12, 12), (12, size - 12), (size - 12, size - 12)):
        rivet(x, y, 4.5, mats["steel"], r=2.4)
    camera(sc, 0, 0, size, size)
    render(sc, os.path.join(OUT, "dialog.png"), size, size)


def black_bar(mats, w=128, h=46):
    """Black command/message bar with a bevelled rim (9-slice, border 20)."""
    sc = bpy.context.scene
    inner = rounded_rect(6, 6, w - 6, h - 6, 14)
    ring("BarRim", rounded_rect(1, 1, w - 1, h - 1, 19), inner, 0.0, 3.5, 1.7, mats["steel"])
    flat("BarScreen", rounded_rect(5, 5, w - 5, h - 5, 14), -1.0, mats["screen"])
    ring("BarLip", inner, rounded_rect(7.5, 7.5, w - 7.5, h - 7.5, 12.5), -0.8, 1.2, 0.5, mats["dark"])
    camera(sc, 0, 0, w, h)
    render(sc, os.path.join(OUT, "blackbar.png"), w, h)


def red_bar(mats, name="bar", w=52, h=12, lit=True):
    sc = bpy.context.scene
    color = (0.86, 0.10, 0.07) if lit else (0.30, 0.05, 0.04)
    m = mat_plain("M_Bar", color, rough=0.25, emission=color if lit else None, strength=0.35 if lit else 0.0)
    plate("Bar", rounded_rect(0.5, 0.5, w - 0.5, h - 0.5, 2.5), 0.0, 3.0, 1.3, m, segments=5)
    camera(sc, 0, 0, w, h)
    render(sc, os.path.join(OUT, f"{name}.png"), w, h)


def led(mats, name, color, on=True, size=20):
    sc = bpy.context.scene
    m = mat_plain("M_Led", color, rough=0.15, emission=color if on else None, strength=1.6 if on else 0.0)
    sphere("Led", size / 2, size / 2, 0.0, 5.6, m, flatten=0.8)
    camera(sc, 0, 0, size, size)
    render(sc, os.path.join(OUT, f"{name}.png"), size, size)


# --------------------------------------------------------------------------------------------
# emblems: coloured plate + the unit model embossed in the same colour
# --------------------------------------------------------------------------------------------

EMBLEMS = {
    "ant": dict(unit="ant_soldier", color=(0.28, 0.66, 0.26), shape="square", fit=62, rot=0, zs=0.55),
    "beetle": dict(unit="beetle_ladybug", color=(0.36, 0.47, 0.84), shape="circle", fit=50, rot=0, zs=0.75),
    "spider": dict(unit="spider_black_widow", color=(0.80, 0.24, 0.19), shape="star", fit=56, rot=180, zs=0.6),
    "wasp": dict(unit="wasp_assault", color=(0.92, 0.72, 0.30), shape="hex", fit=60, rot=-35, zs=0.5),
    "scorpion": dict(unit="scorpion_savage", color=(0.72, 0.26, 0.86), shape="blob", fit=66, rot=25, zs=0.85),
}


def append_unit(unit):
    """Appends the unit's objects from its .blend and returns (objects, bounds lo, hi)."""
    path = os.path.join(salib.BLEND_DIR, f"{unit}.blend")
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    objs = [o for o in bpy.data.objects if o not in before]
    keep = []
    for o in objs:
        if o.name.startswith("Preview") or o.type in ("CAMERA", "LIGHT"):
            continue
        bpy.context.scene.collection.objects.link(o)
        keep.append(o)
        if o.type == "ARMATURE":
            o.data.pose_position = "REST"
    bpy.context.view_layer.update()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in keep:
        if o.type == "MESH":
            for c in o.bound_box:
                p = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    return keep, lo, hi


def emblem(mats, family, spec, size=82):
    sc = bpy.context.scene
    cx = cy = size / 2
    color = spec["color"]
    base = mat_plain("M_Emb", color, rough=0.45)
    relief = mat_plain("M_EmbRelief", tuple(min(1.0, c * 1.12) for c in color), rough=0.4)
    shape = spec["shape"]
    z_top = 7.0
    if shape == "square":
        pts = rounded_rect(5, 5, size - 5, size - 5, 16)
        plate("Plate", pts, 0.0, z_top, 3.2, base, segments=6)
    elif shape == "circle":
        pts = regular_polygon(cx, cy, 38, 64)
        plate("Plate", pts, 0.0, z_top, 3.0, base, segments=6)
        ring("Shield", regular_polygon(cx, cy, 33, 64), regular_polygon(cx, cy, 28, 64), z_top, 1.6, 0.7, base)
    elif shape == "star":
        pts = star(cx, cy, 39, 29, 8)
        plate("Plate", pts, 0.0, z_top, 2.4, base, segments=5)
        # web: rings and spokes in relief
        web = mat_plain("M_Web", tuple(min(1.0, c * 1.2) for c in color), rough=0.4)
        for r in (10, 18, 26):
            pipe(f"Web{r}", regular_polygon(cx, cy, r, 8, rot=22.5), 0.9, web, z=z_top + 0.3, cyclic=True, res=4)
        for i in range(8):
            a = math.radians(22.5 + 45 * i)
            pipe(f"Spoke{i}", [(cx, cy), (cx + 34 * math.cos(a), cy + 34 * math.sin(a))], 0.9, web, z=z_top + 0.3, res=4)
    elif shape == "hex":
        pts = regular_polygon(cx, cy, 40, 6, rot=0)
        plate("Plate", pts, 0.0, z_top, 3.0, base, segments=6)
        cells = mat_plain("M_Cells", tuple(c * 0.9 for c in color), rough=0.5)
        for dx, dy in ((0, 0), (0, -17), (0, 17), (14.7, -8.5), (14.7, 8.5), (-14.7, -8.5), (-14.7, 8.5)):
            ring("Cell", regular_polygon(cx + dx, cy + dy, 8.4, 6, rot=30), regular_polygon(cx + dx, cy + dy, 7.0, 6, rot=30), z_top, 1.2, 0.5, cells)
    else:  # blob: a crumpled rock
        import random

        rb = random.Random(5)
        pts = []
        for i in range(36):
            a = math.radians(10 * i)
            rr = 35 + rb.uniform(-5, 5)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        ob = plate("Plate", pts, 0.0, z_top, 2.6, base, segments=5)
        tex = bpy.data.textures.new("BlobTex", "CLOUDS")
        tex.noise_scale = 7.0
        sub = ob.modifiers.new("Subdiv", "SUBSURF")
        sub.subdivision_type = "SIMPLE"
        sub.levels = 4
        sub.render_levels = 5
        disp = ob.modifiers.new("Displace", "DISPLACE")
        disp.texture = tex
        disp.strength = 1.3
        disp.texture_coords = "GLOBAL"
    # the unit, flattened a little so it reads as a relief
    objs, lo, hi = append_unit(spec["unit"])
    root = bpy.data.objects.new("UnitRoot", None)
    sc.collection.objects.link(root)
    ext = max(hi.x - lo.x, hi.y - lo.y)
    s = spec["fit"] / max(ext, 1e-6)
    centre = (lo + hi) / 2
    for o in objs:
        if o.parent is None:
            o.parent = root
    zs = spec.get("zs", 0.55)
    root.scale = (s, s, s * zs)
    root.rotation_euler = (0, 0, math.radians(spec["rot"]))
    # place the model's centre on the plate centre, resting on the plate top
    rot = root.rotation_euler.to_matrix()
    off = rot @ Vector((centre.x * s, centre.y * s, 0))
    root.location = Vector((cx - off.x, -cy - off.y, z_top + 0.4 - lo.z * s * zs))
    for o in objs:
        if o.type == "MESH":
            for i in range(len(o.data.materials)):
                o.data.materials[i] = relief
            if not o.data.materials:
                o.data.materials.append(relief)
            for mod in list(o.modifiers):
                if mod.type in ("SUBSURF",):
                    mod.render_levels = min(mod.render_levels, 1)
    camera(sc, 0, 0, size, size)
    render(sc, os.path.join(OUT, f"emblem_{family}.png"), size, size)


# --------------------------------------------------------------------------------------------


def make_materials():
    return {
        "stone": mat_stone(),
        "steel": mat_metal("M_Steel"),
        "steel_dark": mat_metal("M_SteelDark", color=(0.30, 0.28, 0.25), rough=0.45),
        "steel_pressed": mat_metal("M_SteelPressed", color=(0.42, 0.40, 0.37), rough=0.5),
        "screen": mat_black(),
        "dark": mat_plain("M_Dark", (0.05, 0.045, 0.04), rough=0.7),
        "slot": mat_plain("M_Slot", (0.16, 0.03, 0.02), rough=0.6),
        "glass": mat_plain("M_Glass", (0.10, 0.17, 0.11), rough=0.3),
    }


def main(pieces):
    os.makedirs(OUT, exist_ok=True)
    if "sidebar" in pieces:
        new_scene("sidebar")
        build_sidebar(make_materials())
    if "buttons" in pieces:
        new_scene("buttons")
        m = make_materials()
        metal_button(m, "button")
        new_scene("buttons2")
        metal_button(make_materials(), "button_pressed", pressed=True)
        for tone in ("normal", "hover", "pressed", "disabled"):
            new_scene("dbtn")
            dialog_button(make_materials(), "dbutton_" + tone, tone=tone)
    if "bars" in pieces:
        new_scene("bars")
        red_bar(make_materials(), "bar", lit=True)
        new_scene("bars2")
        red_bar(make_materials(), "bar_dim", lit=False)
    if "leds" in pieces:
        for name, color, on in (("led", (0.25, 0.95, 0.30), True), ("led_red", (0.95, 0.22, 0.15), True), ("led_off", (0.12, 0.16, 0.12), False)):
            new_scene(name)
            led(make_materials(), name, color, on)
    if "dialog" in pieces:
        new_scene("dialog")
        dialog_frame(make_materials())
    if "blackbar" in pieces:
        new_scene("blackbar")
        black_bar(make_materials())
    if "emblems" in pieces:
        for fam, spec in EMBLEMS.items():
            new_scene("emb")
            emblem(make_materials(), fam, spec)


if __name__ == "__main__":
    args = [a for a in salib.script_args() if not a.startswith("-")]
    main(set(args) if args else {"sidebar", "buttons", "bars", "leds", "dialog", "blackbar", "emblems"})
