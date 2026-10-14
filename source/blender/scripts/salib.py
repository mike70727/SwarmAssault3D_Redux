"""salib - shared Blender (bpy) helpers for the Swarm Assault 3D asset pipeline.

Every asset script imports this module.  It only uses the public bpy API so it works both inside a
Blender GUI session and with the headless `bpy` pip module (Blender 5.2 LTS was used for the
committed assets).

Conventions enforced here (see docs/ASSET_CHECKLIST.md):
  * 1 Blender unit = 1 map cell, Z up, rest pose faces -Y.
  * Material names M_Team / M_Dark / M_Accent / M_Eye / M_Wing / M_Ground / M_Colony / M_Neutral.
  * Armature object is called "Rig"; actions are called idle / move / fly / attack / death.
  * IK constraints are baked to FK keyframes before export (bake_actions()).
  * GLB export: +Y up, all NLA tracks exported as separately named animation clips.
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys
from dataclasses import dataclass, field

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

# Realism pass (procedural chitin shaders, subdivided/displaced geometry, baked textures).
# Set SA_REALISM=0 in the environment to get the original flat-shaded primitives.
REALISM = os.environ.get("SA_REALISM", "1") != "0"

# --------------------------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
BLEND_DIR = os.path.join(PROJECT_ROOT, "blender", "blend")
PREVIEW_DIR = os.path.join(PROJECT_ROOT, "blender", "previews")


def _asset_root() -> str:
    """The game's `assets` folder: SA_ASSETS, else next to `blender/` (repository layout), else one
    level up (release package layout: `assets/` beside `source/blender/`)."""
    env = os.environ.get("SA_ASSETS")
    if env:
        return os.path.abspath(env)
    for cand in (os.path.join(PROJECT_ROOT, "assets"), os.path.join(PROJECT_ROOT, "..", "assets")):
        if os.path.exists(os.path.join(cand, "data", "units.ron")):
            return os.path.abspath(cand)
    return os.path.join(PROJECT_ROOT, "assets")


ASSET_ROOT = _asset_root()
MODEL_DIR = os.path.join(ASSET_ROOT, "models")
TEXTURE_DIR = os.path.join(ASSET_ROOT, "textures")

for d in (BLEND_DIR, PREVIEW_DIR, MODEL_DIR, TEXTURE_DIR):
    os.makedirs(d, exist_ok=True)

FPS = 30

# Team colours sampled from the reference sprites (docs/GAMEPLAY_RESEARCH.md A12), linear-ish sRGB.
TEAM_COLORS = {
    "Y": (0.72, 0.66, 0.28),
    "R": (0.53, 0.16, 0.16),
    "G": (0.22, 0.47, 0.09),
    "B": (0.22, 0.35, 0.72),
    "X": (0.16, 0.16, 0.16),
}


def script_args() -> list[str]:
    """Command-line arguments of the asset script: the ones after `--` when the script runs inside
    the Blender program (`blender -b --python build_ant.py -- ant_soldier`), else everything after
    the script name (headless `bpy` module: `python build_ant.py ant_soldier`)."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def log(*a):
    print("[salib]", *a, flush=True)


# Cycles renders and bakes on the CPU unless SA_CYCLES_DEVICE names a GPU backend (OPTIX, CUDA,
# HIP, ONEAPI, METAL); the bakes are much faster on a GPU and give the same textures.
CYCLES_DEVICE = os.environ.get("SA_CYCLES_DEVICE", "CPU").upper()


def use_cycles_device(sc):
    """Point Cycles at the device chosen by SA_CYCLES_DEVICE (falls back to the CPU)."""
    sc.cycles.device = "CPU"
    if CYCLES_DEVICE == "CPU":
        return
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = CYCLES_DEVICE
        prefs.get_devices()
        used = 0
        for dev in prefs.devices:
            dev.use = dev.type == CYCLES_DEVICE
            used += int(dev.use)
        if used:
            sc.cycles.device = "GPU"
        else:
            log(f"no {CYCLES_DEVICE} device found: Cycles stays on the CPU")
    except Exception as e:  # noqa: BLE001
        log(f"{CYCLES_DEVICE} unavailable ({e}): Cycles stays on the CPU")


# --------------------------------------------------------------------------------------------
# scene
# --------------------------------------------------------------------------------------------
def reset_scene(name: str = "Scene"):
    """Start from an empty file with sensible units/fps."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = name
    sc.render.fps = FPS
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.frame_start = 1
    sc.frame_end = 60
    # a neutral grey world so preview renders are readable
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.55, 0.6, 0.65, 1.0)
        bg.inputs[1].default_value = 1.0
    sc.world = world
    return sc


def link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


# --------------------------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------------------------
_MATERIAL_CACHE: dict[str, bpy.types.Material] = {}


def srgb_to_linear(c):
    """Blender/glTF store scene-linear colours; our scripts specify display (sRGB) values."""
    out = []
    for v in c[:3]:
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def material(name: str, color=(0.8, 0.8, 0.8), roughness=0.55, metallic=0.0, alpha=1.0,
             emission=None, emission_strength=0.0, kind=None, tint=False, **kw):
    """Create (or fetch) a material with a stable name. `color` is sRGB.

    With REALISM on, a procedural surface of the given `kind` is built instead of a flat colour:
    chitin (default), metal, glossy, membrane, fur, organic, earth, wood, stone, petal, emissive.
    """
    if REALISM:
        if kind is None:
            kind = "metal" if metallic > 0.5 else ("glossy" if roughness < 0.25 else "chitin")
        return procedural_material(name, color, kind=kind, roughness=roughness, metallic=metallic, alpha=alpha,
                                   emission=emission, emission_strength=emission_strength, tint=tint, **kw)
    color = srgb_to_linear(color)
    if emission is not None:
        emission = srgb_to_linear(emission)
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs[0], out.inputs[0])
    c = (*color[:3], 1.0)
    bsdf.inputs["Base Color"].default_value = c
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = c  # workbench / viewport
    mat.roughness = roughness
    mat.metallic = metallic
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED"
    return mat


def standard_materials(team="Y", neutral=False):
    base = TEAM_COLORS["X" if neutral else team]
    dark = tuple(c * 0.45 for c in base) if not neutral else (0.10, 0.10, 0.10)
    return {
        "M_Team": material("M_Team", base, roughness=0.45, kind="chitin", tint=True, sss=0.12, variation=0.4),
        "M_Dark": material("M_Dark", dark, roughness=0.5, kind="chitin", variation=0.3),
        "M_Black": material("M_Black", (0.05, 0.05, 0.06), roughness=0.3, kind="chitin", coat=0.9, variation=0.2),
        "M_Accent": material("M_Accent", (0.45, 0.45, 0.48), roughness=0.35, metallic=0.85, kind="metal"),
        "M_Eye": material("M_Eye", (0.02, 0.02, 0.02), roughness=0.08, kind="glossy"),
        "M_Wing": material("M_Wing", (0.9, 0.85, 0.8), roughness=0.25, alpha=0.45, kind="membrane"),
        "M_Ground": material("M_Ground", (0.30, 0.24, 0.19), roughness=0.95, kind="earth"),
        "M_Colony": material("M_Colony", (0.97, 0.85, 0.47), roughness=0.5, kind="chitin", tint=True, variation=0.45, cell_scale=18.0, bump=0.45),
        "M_Neutral": material("M_Neutral", (0.78, 0.72, 0.66), roughness=0.6, kind="organic"),
    }


# --------------------------------------------------------------------------------------------
# mesh building (all parts of one asset are merged into a single mesh object with vertex groups)
# --------------------------------------------------------------------------------------------
@dataclass
class Part:
    """A mesh primitive that will become part of a skinned body.

    bone: vertex group (bone) that owns every vertex of this part (rigid skinning).
    """
    obj: bpy.types.Object
    bone: str
    material: str


class Body:
    """Collects primitive parts, assigns materials and bone vertex groups, then joins them."""

    def __init__(self, name: str, materials: dict):
        self.name = name
        self.materials = materials
        self.parts: list[Part] = []

    # primitives -------------------------------------------------------------------------
    def _finish(self, obj, bone, mat, smooth=True):
        obj.name = f"{self.name}_part_{len(self.parts):03d}"
        obj.data.materials.append(self.materials[mat])
        if smooth:
            for p in obj.data.polygons:
                p.use_smooth = True
        self.parts.append(Part(obj, bone, mat))
        return obj

    def sphere(self, bone, mat, center, radius, scale=(1, 1, 1), rot=(0, 0, 0), segments=16, rings=10):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments, ring_count=rings,
                                             location=center)
        o = bpy.context.object
        o.scale = scale
        o.rotation_euler = rot
        return self._finish(o, bone, mat)

    def cone(self, bone, mat, center, r1, r2, depth, rot=(0, 0, 0), verts=12):
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth,
                                        location=center, rotation=rot)
        return self._finish(bpy.context.object, bone, mat)

    def cylinder(self, bone, mat, center, radius, depth, rot=(0, 0, 0), verts=12, scale=(1, 1, 1)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth,
                                            location=center, rotation=rot)
        o = bpy.context.object
        o.scale = scale
        return self._finish(o, bone, mat)

    def cube(self, bone, mat, center, size=(1, 1, 1), rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=center, rotation=rot)
        o = bpy.context.object
        o.scale = size
        o["sa_no_subdiv"] = True
        o["sa_bevel"] = min(size) * 0.18
        return self._finish(o, bone, mat, smooth=False)

    def torus(self, bone, mat, center, major, minor, rot=(0, 0, 0), scale=(1, 1, 1)):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=center,
                                         rotation=rot, major_segments=24, minor_segments=8)
        o = bpy.context.object
        o.scale = scale
        return self._finish(o, bone, mat)

    def segment(self, bone, mat, a, b, r1, r2, verts=10):
        """Tapered cylinder from point a to point b (used for legs, antennae, tails)."""
        a, b = Vector(a), Vector(b)
        d = b - a
        length = d.length
        if length < 1e-6:
            raise ValueError("zero length segment")
        center = (a + b) * 0.5
        rot = d.to_track_quat("Z", "Y").to_euler()
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=length,
                                        location=center, rotation=rot)
        return self._finish(bpy.context.object, bone, mat)

    def plane_wing(self, bone, mat, root, tip, width, thickness=0.01, curve=0.0, segments=4):
        """(wings are flagged so the realism pass does not subdivide them)"""
        """A flat tapered wing between root and tip, in the XY plane (Z up) with a slight sweep."""
        root, tip = Vector(root), Vector(tip)
        verts = []
        faces = []
        axis = (tip - root)
        n = axis.normalized()
        side = n.cross(Vector((0, 0, 1))).normalized()
        for i in range(segments + 1):
            t = i / segments
            p = root.lerp(tip, t)
            w = width * (1.0 - 0.15 * t) * math.sin(math.pi * min(1.0, 0.15 + t * 0.85)) + width * 0.08
            z = curve * t * t
            verts.append((p + side * w + Vector((0, 0, z))))
            verts.append((p - side * w + Vector((0, 0, z))))
        for i in range(segments):
            a = i * 2
            faces.append((a, a + 1, a + 3, a + 2))
        me = bpy.data.meshes.new(f"{self.name}_wing")
        me.from_pydata([tuple(v) for v in verts], [], faces)
        me.update()
        o = bpy.data.objects.new(f"{self.name}_wing", me)
        link(o)
        # solidify a bit so it is a real 3-D surface with both faces visible
        mod = o.modifiers.new("Solidify", "SOLIDIFY")
        mod.thickness = thickness
        mod.offset = 0.0
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        o["sa_no_subdiv"] = True
        return self._finish(o, bone, mat)

    # assembly ---------------------------------------------------------------------------
    def join(self, name=None):
        """Join every part into one mesh object with per-bone vertex groups.

        Returns the joined object (materials preserved; slot order is de-duplicated by Blender).
        """
        name = name or f"{self.name}_Mesh"
        for p in self.parts:
            if REALISM and not p.obj.get("sa_no_subdiv"):
                select_only([p.obj])
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                m = p.obj.modifiers.new("Subd", "SUBSURF")
                m.levels = 1
                m.render_levels = 1
                bpy.ops.object.modifier_apply(modifier=m.name)
            elif REALISM and p.obj.get("sa_bevel"):
                select_only([p.obj])
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                bevel_object(p.obj, float(p.obj["sa_bevel"]))
            vg = p.obj.vertex_groups.new(name=p.bone)
            vg.add(list(range(len(p.obj.data.vertices))), 1.0, "REPLACE")
        objs = [p.obj for p in self.parts]
        select_only(objs)
        bpy.ops.object.join()
        obj = bpy.context.object
        obj.name = name
        obj.data.name = name
        # apply scale/rotation so the skin binds to clean transforms
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        if REALISM:
            detail_object(obj, subdiv=0, displace=0.006, smooth_angle=40.0, noise_scale=0.25)
        self.parts.clear()
        return obj


# --------------------------------------------------------------------------------------------
# rigging
# --------------------------------------------------------------------------------------------
@dataclass
class BoneDef:
    name: str
    head: tuple
    tail: tuple
    parent: str | None = None
    connect: bool = False
    roll: float = 0.0
    deform: bool = True


def build_armature(name: str, bones: list[BoneDef]):
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    link(obj)
    select_only([obj])
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    for b in bones:
        e = eb.new(b.name)
        e.head = Vector(b.head)
        e.tail = Vector(b.tail)
        e.roll = b.roll
        e.use_deform = b.deform
        if b.parent:
            e.parent = eb[b.parent]
            e.use_connect = b.connect
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.show_in_front = True
    return obj


def skin(mesh_obj, arm_obj):
    """Parent the mesh to the armature with an Armature modifier (vertex groups already exist)."""
    mesh_obj.parent = arm_obj
    mod = mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    mod.use_vertex_groups = True
    return mod


def add_ik(arm_obj, bone: str, target_bone: str, chain: int, pole_bone: str | None = None,
           pole_angle: float = 0.0):
    """IK constraint on a pose bone, solved by a target bone of the same armature."""
    select_only([arm_obj])
    bpy.ops.object.mode_set(mode="POSE")
    pb = arm_obj.pose.bones[bone]
    c = pb.constraints.new("IK")
    c.target = arm_obj
    c.subtarget = target_bone
    c.chain_count = chain
    if pole_bone:
        c.pole_target = arm_obj
        c.pole_subtarget = pole_bone
        c.pole_angle = pole_angle
    c.use_tail = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return c


# --------------------------------------------------------------------------------------------
# animation
# --------------------------------------------------------------------------------------------
class Clip:
    """Helper to author one action (clip) on an armature by keying pose-bone transforms."""

    def __init__(self, arm_obj, name: str, length_frames: int, loop=True):
        self.arm = arm_obj
        self.name = name
        self.length = length_frames
        self.loop = loop
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        self.action = act
        if arm_obj.animation_data is None:
            arm_obj.animation_data_create()
        arm_obj.animation_data.action = act
        # Blender 4.4+ slotted actions: make sure a slot for this object exists and is assigned
        if hasattr(act, "slots"):
            slot = act.slots.new(arm_obj.id_type, arm_obj.name) if len(act.slots) == 0 else act.slots[0]
            try:
                arm_obj.animation_data.action_slot = slot
            except Exception:  # pragma: no cover - depends on Blender version
                pass
        # reset pose
        for pb in arm_obj.pose.bones:
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (0, 0, 0)
            pb.location = (0, 0, 0)
            pb.scale = (1, 1, 1)

    def key(self, bone: str, frame: int, rot=None, loc=None, scale=None):
        pb = self.arm.pose.bones[bone]
        if rot is not None:
            pb.rotation_euler = Euler(tuple(math.radians(a) for a in rot), "XYZ")
            pb.keyframe_insert("rotation_euler", frame=frame)
        if loc is not None:
            pb.location = loc
            pb.keyframe_insert("location", frame=frame)
        if scale is not None:
            pb.scale = scale
            pb.keyframe_insert("scale", frame=frame)

    def finish(self):
        """Make interpolation cyclic-friendly and store the action in an NLA track."""
        act = self.action
        act.frame_range = (1, self.length)
        act.use_frame_range = True
        act.use_cyclic = self.loop
        for fc in _fcurves(act):
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.easing = "AUTO"
            fc.update()
        return act


def _fcurves(action):
    """Return fcurves of an action regardless of slotted/legacy layout."""
    if hasattr(action, "layers") and len(action.layers):
        fcs = []
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs.extend(cb.fcurves)
        return fcs
    return list(action.fcurves)


def bake_actions(arm_obj, actions, clear_constraints=True):
    """Bake every action to plain FK keys (visual keying) so IK/constraints are not needed.

    After baking, the baked actions are stashed into NLA tracks (one per action) so the glTF exporter
    exports each as its own animation clip.  The constraints are removed at the end.
    """
    select_only([arm_obj])
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    baked = []
    for act in actions:
        arm_obj.animation_data.action = act
        if hasattr(act, "slots") and len(act.slots):
            try:
                arm_obj.animation_data.action_slot = act.slots[0]
            except Exception:
                pass
        start, end = int(act.frame_range[0]), int(act.frame_range[1])
        bpy.context.scene.frame_start = start
        bpy.context.scene.frame_end = end
        bpy.ops.nla.bake(frame_start=start, frame_end=end, only_selected=True, visual_keying=True,
                         clear_constraints=False, use_current_action=False, bake_types={"POSE"},
                         channel_types={"LOCATION", "ROTATION", "SCALE"})
        new_act = arm_obj.animation_data.action
        new_act.name = act.name + "_baked"
        new_act.use_fake_user = True
        new_act.use_frame_range = True
        new_act.frame_range = (start, end)
        new_act.use_cyclic = act.use_cyclic
        baked.append(new_act)
    if clear_constraints:
        for pb in arm_obj.pose.bones:
            for c in list(pb.constraints):
                pb.constraints.remove(c)
    bpy.ops.object.mode_set(mode="OBJECT")
    # rename: baked clip takes the canonical name, original keeps _ik suffix for editing
    for act, new_act in zip(actions, baked):
        act.name = act.name + "_ik"
        new_act.name = new_act.name.replace("_baked", "")
    stash_actions(arm_obj, baked)
    return baked


def stash_actions(arm_obj, actions, track_names=None):
    """Put each action on its own NLA track (what the glTF exporter uses for named clips).

    `track_names` overrides the track (= exported clip) names; tracks with the same name on several
    objects are merged into one glTF animation by the exporter.
    """
    ad = arm_obj.animation_data or arm_obj.animation_data_create()
    ad.action = None
    for t in list(ad.nla_tracks):
        ad.nla_tracks.remove(t)
    for i, act in enumerate(actions):
        track = ad.nla_tracks.new()
        track.name = track_names[i] if track_names else act.name
        strip = track.strips.new(act.name, int(act.frame_range[0]), act)
        strip.name = act.name
        if hasattr(act, "slots") and len(act.slots):
            try:
                strip.action_slot = act.slots[0]
            except Exception:
                pass
        track.mute = False
    return ad


# --------------------------------------------------------------------------------------------
# export / save / previews
# --------------------------------------------------------------------------------------------
def save_blend(asset: str):
    path = os.path.join(BLEND_DIR, f"{asset}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    log("saved", path)
    return path


def export_glb(asset: str, objects=None):
    path = os.path.join(MODEL_DIR, f"{asset}.glb")
    if objects is not None:
        select_only(objects)
        use_selection = True
    else:
        use_selection = False
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_animations=True,
        export_animation_mode="NLA_TRACKS",
        export_nla_strips=True,
        export_nla_strips_merged_animation_name="merged",
        export_force_sampling=True,
        export_frame_range=False,
        export_bake_animation=False,
        export_optimize_animation_size=False,
        export_anim_single_armature=False,
        export_reset_pose_bones=True,
        export_skins=True,
        export_morph=False,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,  # Bevy generates mikktspace tangents for normal-mapped meshes
        export_lights=False,
        export_cameras=False,
        use_selection=use_selection,
    )
    log("exported", path, os.path.getsize(path), "bytes")
    return path


def glb_summary(path: str) -> dict:
    """Read the JSON chunk of a GLB and summarise meshes/materials/animations (for checks/tests)."""
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        assert magic == 0x46546C67, "not a GLB"
        chunk_len, chunk_type = struct.unpack("<II", f.read(8))
        data = json.loads(f.read(chunk_len))
    anims = []
    for a in data.get("animations", []):
        n_samplers = len(a.get("samplers", []))
        # animation length from the max input accessor max value
        max_t = 0.0
        for s in a.get("samplers", []):
            acc = data["accessors"][s["input"]]
            max_t = max(max_t, float(acc.get("max", [0])[0]))
        anims.append({"name": a.get("name"), "channels": len(a.get("channels", [])),
                      "samplers": n_samplers, "seconds": round(max_t, 3)})
    return {
        "meshes": [m.get("name") for m in data.get("meshes", [])],
        "materials": [m.get("name") for m in data.get("materials", [])],
        "nodes": len(data.get("nodes", [])),
        "skins": len(data.get("skins", [])),
        "animations": anims,
        "node_names": [n.get("name") for n in data.get("nodes", [])],
    }


PREVIEW_VIEWS = {
    # name: (azimuth degrees around Z measured from -Y (front), elevation degrees)
    "front": (0.0, 22.0),
    "back": (180.0, 22.0),
    "left": (90.0, 22.0),
    "right": (-90.0, 22.0),
    "threequarter": (40.0, 35.0),
    "top": (0.0, 88.0),
}


def render_previews(asset: str, radius: float, center=(0, 0, 0.25), size=512, samples=48,
                    views=("front", "back", "left", "right", "threequarter"), engine="CYCLES",
                    frame=1):
    """Render the standard preview set.  The camera orbits `center` at `radius`."""
    sc = bpy.context.scene
    sc.frame_set(frame)
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    link(cam)
    sun_data = bpy.data.lights.new("PreviewSun", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("PreviewSun", sun_data)
    link(sun)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    fill_data = bpy.data.lights.new("PreviewFill", "SUN")
    fill_data.energy = 0.6
    fill = bpy.data.objects.new("PreviewFill", fill_data)
    link(fill)
    fill.rotation_euler = (math.radians(60), 0, math.radians(140))
    # ground disc so shadows read
    bpy.ops.mesh.primitive_circle_add(radius=radius * 2.5, fill_type="NGON", location=(0, 0, -0.001))
    ground = bpy.context.object
    ground.name = "PreviewGround"
    ground.data.materials.append(material("M_PreviewGround", (0.36, 0.42, 0.26), roughness=1.0))
    sc.camera = cam
    sc.render.engine = engine
    # Standard view transform keeps team colours readable (AgX/Filmic push yellows to white)
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    if sc.world and sc.world.node_tree:
        bg = sc.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[1].default_value = 0.45
    if engine == "CYCLES":
        sc.cycles.samples = samples
        use_cycles_device(sc)
        sc.cycles.use_denoising = False
    sc.render.resolution_x = size
    sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 88
    out = []
    c = Vector(center)
    for v in views:
        az, el = PREVIEW_VIEWS[v]
        az_r, el_r = math.radians(az), math.radians(el)
        # front = camera on -Y looking +Y
        pos = c + Vector((-math.sin(az_r) * math.cos(el_r) * radius,
                          -math.cos(az_r) * math.cos(el_r) * radius,
                          math.sin(el_r) * radius))
        cam.location = pos
        direction = c - pos
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(PREVIEW_DIR, f"{asset}_{v}.jpg")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        out.append(path)
        log("rendered", path)
    # clean preview helpers so they are not saved/exported
    for o in (cam, sun, fill, ground):
        bpy.data.objects.remove(o, do_unlink=True)
    return out


def contact_sheet(asset: str, paths, out=None, thumb=256):
    """Combine preview renders into one sheet (PIL optional: skipped when unavailable)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    ims = [Image.open(p).convert("RGB").resize((thumb, thumb)) for p in paths]
    sheet = Image.new("RGB", (thumb * len(ims), thumb + 18), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, (p, im) in enumerate(zip(paths, ims)):
        sheet.paste(im, (i * thumb, 18))
        d.text((i * thumb + 4, 3), os.path.basename(p)[:-4], fill=(255, 255, 0))
    out = out or os.path.join(PREVIEW_DIR, f"{asset}_sheet.jpg")
    sheet.save(out, quality=88)
    return out


# --------------------------------------------------------------------------------------------
# generic leg helpers shared by ant / beetle / spider / scorpion / wasp rigs
# --------------------------------------------------------------------------------------------
@dataclass
class LegSpec:
    name: str              # e.g. "L1"
    side: int              # +1 = left (+X), -1 = right (-X)
    root: tuple            # coxa attachment point on the body (local, rest pose)
    knee: tuple            # femur/tibia joint
    foot: tuple            # ground contact point
    phase: float = 0.0     # walk phase 0..1 (tripod gait)
    radius: float = 0.035  # femur radius


def leg_bones(spec: LegSpec, parent="body"):
    """Three-bone FK chain + IK target + pole for one leg."""
    n = f"leg.{spec.name}"
    root, knee, foot = Vector(spec.root), Vector(spec.knee), Vector(spec.foot)
    mid = root.lerp(knee, 0.35)
    bones = [
        BoneDef(f"{n}.coxa", tuple(root), tuple(mid), parent=parent),
        BoneDef(f"{n}.femur", tuple(mid), tuple(knee), parent=f"{n}.coxa", connect=True),
        BoneDef(f"{n}.tibia", tuple(knee), tuple(foot), parent=f"{n}.femur", connect=True),
        # IK target and pole are children of root so they stay on the ground
        BoneDef(f"{n}.ik", tuple(foot), (foot.x, foot.y, foot.z + 0.08), parent="root", deform=False),
        BoneDef(f"{n}.pole", (knee.x * 1.2, knee.y, knee.z + 0.6), (knee.x * 1.2, knee.y, knee.z + 0.7),
                parent="root", deform=False),
    ]
    return bones


def leg_mesh(body: Body, spec: LegSpec, mat="M_Dark", tip_mat=None):
    n = f"leg.{spec.name}"
    root, knee, foot = Vector(spec.root), Vector(spec.knee), Vector(spec.foot)
    mid = root.lerp(knee, 0.35)
    r = spec.radius
    body.sphere(f"{n}.coxa", mat, tuple(root), r * 1.25, segments=10, rings=6)
    body.segment(f"{n}.coxa", mat, tuple(root), tuple(mid), r * 1.1, r)
    body.segment(f"{n}.femur", mat, tuple(mid), tuple(knee), r, r * 0.8)
    body.sphere(f"{n}.femur", mat, tuple(knee), r * 0.95, segments=10, rings=6)
    body.segment(f"{n}.tibia", tip_mat or mat, tuple(knee), tuple(foot), r * 0.8, r * 0.3)


def apply_leg_ik(arm_obj, specs):
    for spec in specs:
        n = f"leg.{spec.name}"
        add_ik(arm_obj, f"{n}.tibia", f"{n}.ik", chain=2, pole_bone=f"{n}.pole",
               pole_angle=math.radians(-90 if spec.side > 0 else 90))


def key_walk_cycle(clip: Clip, specs, frames: int, stride: float, lift: float, body_bob=0.015,
                   heading_axis="Y"):
    """Key IK foot targets for a tripod walk cycle (6 legs) or alternating-tetrapod (8 legs).

    Feet move backwards (+Y, since the bug faces -Y) while planted and swing forward while lifted.
    """
    for spec in specs:
        n = f"leg.{spec.name}.ik"
        steps = 8
        for i in range(steps + 1):
            t = i / steps
            f = 1 + round(t * (frames - 1))
            ph = (t + spec.phase) % 1.0
            # stance for ph in [0,0.5): foot slides back; swing for [0.5,1): foot arcs forward
            if ph < 0.5:
                s = ph / 0.5
                y = -stride / 2 + stride * s
                z = 0.0
            else:
                s = (ph - 0.5) / 0.5
                y = stride / 2 - stride * s
                z = lift * math.sin(math.pi * s)
            clip.key(n, f, loc=(0.0, y, z))
    # body bob
    for i in range(0, frames + 1, max(1, frames // 4)):
        f = 1 + i
        ph = (i / frames) * 2 * math.pi * 2
        clip.key("body", f, loc=(0, 0, body_bob * math.sin(ph)))


def key_idle(clip: Clip, specs, frames: int, body_bob=0.01, antenna_bones=()):
    clip.key("body", 1, loc=(0, 0, 0))
    clip.key("body", frames // 2, loc=(0, 0, body_bob))
    clip.key("body", frames, loc=(0, 0, 0))
    for spec in specs:
        clip.key(f"leg.{spec.name}.ik", 1, loc=(0, 0, 0))
        clip.key(f"leg.{spec.name}.ik", frames, loc=(0, 0, 0))
    for i, b in enumerate(antenna_bones):
        clip.key(b, 1, rot=(0, 0, 0))
        clip.key(b, frames // 2, rot=(8 * (1 if i % 2 else -1), 0, 6))
        clip.key(b, frames, rot=(0, 0, 0))


def key_death(clip: Clip, specs, frames: int, fall_axis_deg=(0, 0, 0), sink=0.12):
    """Collapse: legs fold, body drops and rolls a little."""
    clip.key("body", 1, loc=(0, 0, 0), rot=(0, 0, 0))
    clip.key("body", frames, loc=(0, 0, -sink), rot=fall_axis_deg)
    for spec in specs:
        n = f"leg.{spec.name}.ik"
        clip.key(n, 1, loc=(0, 0, 0))
        # feet pull inward and up (legs curl)
        clip.key(n, frames, loc=(-0.25 * spec.side, 0.0, 0.18))


def print_summary(path):
    s = glb_summary(path)
    log("GLB", os.path.basename(path), "meshes", s["meshes"], "materials", s["materials"],
        "skins", s["skins"], "nodes", s["nodes"])
    for a in s["animations"]:
        log("   clip", a)
    return s


# --------------------------------------------------------------------------------------------
# realism pass: procedural surfaces
# --------------------------------------------------------------------------------------------
# per-kind defaults: clear coat, coat roughness, subsurface weight, bump strength, roughness
# spread and crevice dirt
KIND_DEFAULTS = {
    "chitin": dict(coat=0.40, coat_rough=0.18, sss=0.08, bump=0.16, spread=0.15, dirt=0.35),
    "glossy": dict(coat=1.00, coat_rough=0.05, sss=0.00, bump=0.00, spread=0.00, dirt=0.00),
    "metal": dict(coat=0.10, coat_rough=0.30, sss=0.00, bump=0.10, spread=0.14, dirt=0.45),
    "membrane": dict(coat=0.30, coat_rough=0.10, sss=0.00, bump=0.06, spread=0.10, dirt=0.10),
    "fur": dict(coat=0.00, coat_rough=0.30, sss=0.15, bump=0.45, spread=0.20, dirt=0.40),
    "organic": dict(coat=0.15, coat_rough=0.25, sss=0.20, bump=0.22, spread=0.20, dirt=0.35),
    "earth": dict(coat=0.00, coat_rough=0.50, sss=0.00, bump=0.70, spread=0.10, dirt=0.50),
    "wood": dict(coat=0.08, coat_rough=0.40, sss=0.00, bump=0.35, spread=0.15, dirt=0.45),
    "stone": dict(coat=0.00, coat_rough=0.50, sss=0.00, bump=0.60, spread=0.12, dirt=0.55),
    "petal": dict(coat=0.10, coat_rough=0.30, sss=0.35, bump=0.12, spread=0.15, dirt=0.15),
    "emissive": dict(coat=0.30, coat_rough=0.20, sss=0.00, bump=0.05, spread=0.05, dirt=0.00),
}


def _lin(c):
    return tuple(srgb_to_linear(c)) + (1.0,)


def _scale_color(c, k):
    return tuple(min(1.0, v * k) for v in c[:3]) + (1.0,)


def _link_or_set(nt, src, socket):
    if hasattr(src, "node"):
        nt.links.new(src, socket)
    else:
        socket.default_value = src


def _mix_rgb(nt, blend, a, b, fac=1.0):
    """ShaderNodeMix (RGBA).  `a`/`b` are output sockets or colour tuples.  The glTF exporter
    understands a MULTIPLY mix of a texture and a constant as baseColorFactor."""
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    m.inputs[0].default_value = fac
    _link_or_set(nt, a, m.inputs[6])
    _link_or_set(nt, b, m.inputs[7])
    return m.outputs[2]


def _math(nt, op, a, b=0.0):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    _link_or_set(nt, a, m.inputs[0])
    _link_or_set(nt, b, m.inputs[1])
    return m.outputs[0]


def _map_range(nt, value, lo, hi):
    m = nt.nodes.new("ShaderNodeMapRange")
    m.inputs["From Min"].default_value = 0.0
    m.inputs["From Max"].default_value = 1.0
    m.inputs["To Min"].default_value = lo
    m.inputs["To Max"].default_value = hi
    nt.links.new(value, m.inputs["Value"])
    return m.outputs["Result"]


def _noise(nt, coord, scale, detail=4.0, roughness=0.55, distortion=0.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = roughness
    n.inputs["Distortion"].default_value = distortion
    nt.links.new(coord, n.inputs["Vector"])
    return n


def procedural_material(name, color, kind="chitin", roughness=0.5, metallic=0.0, alpha=1.0, emission=None,
                        emission_strength=0.0, tint=False, coat=None, sss=None, variation=0.35, scale=9.0,
                        cell_scale=12.0, bump=None, dirt=None):
    """Build a physically based procedural surface of the given `kind`.

    Tinted materials (team colour / colony colour) get a neutral light-grey surface multiplied by an RGB
    node named "TeamTint" that holds the colour; the texture bake sets that node to white so the baked
    colour map only carries surface detail and the colour is applied as a factor (glTF baseColorFactor,
    replaced at runtime by the owner's team colour).
    """
    kd = KIND_DEFAULTS.get(kind, KIND_DEFAULTS["chitin"])
    coat_w = kd["coat"] if coat is None else coat
    sss_w = kd["sss"] if sss is None else sss
    bump_s = kd["bump"] if bump is None else bump
    dirt_k = kd["dirt"] if dirt is None else dirt
    lin = _lin(color)
    metallic = max(metallic, 0.8) if kind == "metal" else metallic

    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "Principled"
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    texco = nt.nodes.new("ShaderNodeTexCoord")
    coord = texco.outputs["Object"]

    surf = (0.90, 0.90, 0.90, 1.0) if tint else lin
    n1 = _noise(nt, coord, scale, detail=6.0, roughness=0.6)                      # broad variation
    n2 = _noise(nt, coord, scale * (22.0 if kind == "fur" else 18.0), detail=3.0, roughness=0.5,
                distortion=0.6 if kind == "fur" else 0.0)                         # fine grain
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = cell_scale
    vor.inputs["Randomness"].default_value = 0.85
    nt.links.new(coord, vor.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[1].position = 0.7
    if kind == "earth":
        ramp.color_ramp.elements[0].color = _lin((0.22, 0.16, 0.11))
        ramp.color_ramp.elements[1].color = _lin((0.42, 0.33, 0.24))
    elif kind == "stone":
        ramp.color_ramp.elements[0].color = _scale_color(lin, 0.7)
        ramp.color_ramp.elements[1].color = _scale_color(lin, 1.25)
    elif kind == "wood":
        ramp.color_ramp.elements[0].color = _scale_color(lin, 0.55)
        ramp.color_ramp.elements[1].color = _scale_color(lin, 1.25)
    else:
        ramp.color_ramp.elements[0].color = _scale_color(surf, 1.0 - variation)
        ramp.color_ramp.elements[1].color = _scale_color(surf, 1.0 + 0.4 * variation)
    nt.links.new(n1.outputs["Factor"], ramp.inputs["Fac"])
    base = ramp.outputs["Color"]
    height = n2.outputs["Factor"]

    if kind == "chitin":
        # per-plate brightness variation and gently bulging plates
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(vor.outputs["Color"], bw.inputs["Color"])
        plate = _map_range(nt, bw.outputs["Val"], 0.93, 1.07)
        base = _mix_rgb(nt, "MULTIPLY", base, plate, 1.0)
        height = _math(nt, "ADD", _math(nt, "MULTIPLY", vor.outputs["Distance"], -1.0),
                       _math(nt, "MULTIPLY", n2.outputs["Factor"], 0.35))
    elif kind == "wood":
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.inputs["Scale"].default_value = 3.0
        wave.inputs["Distortion"].default_value = 4.0
        wave.inputs["Detail"].default_value = 3.0
        nt.links.new(coord, wave.inputs["Vector"])
        base = _mix_rgb(nt, "MULTIPLY", base, wave.outputs["Color"], 0.35)
        height = _math(nt, "ADD", _math(nt, "MULTIPLY", wave.outputs["Fac"], 0.5),
                       _math(nt, "MULTIPLY", n2.outputs["Factor"], 0.3))
    elif kind == "membrane":
        # wing venation: thin dark raised lines along voronoi cell borders
        vor.inputs["Scale"].default_value = 7.0
        vor.feature = "DISTANCE_TO_EDGE"
        vr = nt.nodes.new("ShaderNodeValToRGB")
        vr.color_ramp.elements[0].position = 0.0
        vr.color_ramp.elements[0].color = _lin((0.30, 0.24, 0.18))
        vr.color_ramp.elements[1].position = 0.05
        vr.color_ramp.elements[1].color = (1, 1, 1, 1)
        nt.links.new(vor.outputs["Distance"], vr.inputs["Fac"])
        base = _mix_rgb(nt, "MULTIPLY", base, vr.outputs["Color"], 1.0)
        vein = _map_range(nt, vor.outputs["Distance"], 1.0, 0.0)
        height = _math(nt, "ADD", _math(nt, "MULTIPLY", n2.outputs["Factor"], 0.3), _math(nt, "POWER", vein, 12.0))
    elif kind == "petal":
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "SPHERICAL"
        nt.links.new(coord, grad.inputs["Vector"])
        gr = nt.nodes.new("ShaderNodeValToRGB")
        gr.color_ramp.elements[0].color = _scale_color(lin, 0.6)
        gr.color_ramp.elements[1].color = _scale_color(lin, 1.2)
        nt.links.new(grad.outputs["Fac"], gr.inputs["Fac"])
        base = _mix_rgb(nt, "MIX", base, gr.outputs["Color"], 0.5)
    elif kind in ("earth", "stone"):
        height = _math(nt, "ADD", n1.outputs["Factor"], _math(nt, "MULTIPLY", n2.outputs["Factor"], 0.5))

    # dirt / occlusion in crevices
    if dirt_k > 0 and kind not in ("glossy", "emissive"):
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = 0.25
        ao.samples = 8
        ao.only_local = True
        aor = nt.nodes.new("ShaderNodeValToRGB")
        aor.color_ramp.elements[0].position = 0.0
        aor.color_ramp.elements[0].color = (1.0 - dirt_k, 1.0 - dirt_k * 0.9, 1.0 - dirt_k * 0.8, 1.0)
        aor.color_ramp.elements[1].position = 0.85
        aor.color_ramp.elements[1].color = (1, 1, 1, 1)
        nt.links.new(ao.outputs["AO"], aor.inputs["Fac"])
        base = _mix_rgb(nt, "MULTIPLY", base, aor.outputs["Color"], 1.0)

    if tint:
        tint_node = nt.nodes.new("ShaderNodeRGB")
        tint_node.name = "TeamTint"
        tint_node.label = "TeamTint"
        tint_node.outputs[0].default_value = lin
        base = _mix_rgb(nt, "MULTIPLY", base, tint_node.outputs[0], 1.0)
    nt.links.new(base, bsdf.inputs["Base Color"])

    # roughness
    if kd["spread"] <= 0.0:
        bsdf.inputs["Roughness"].default_value = roughness
    else:
        src = n2.outputs["Factor"] if kind in ("metal", "earth", "stone", "fur") else n1.outputs["Factor"]
        nt.links.new(_map_range(nt, src, max(0.03, roughness - kd["spread"]), min(1.0, roughness + kd["spread"])),
                     bsdf.inputs["Roughness"])

    # relief
    if bump_s > 0:
        bmp = nt.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = bump_s
        bmp.inputs["Distance"].default_value = 0.02
        nt.links.new(height, bmp.inputs["Height"])
        nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    bsdf.inputs["Coat Weight"].default_value = coat_w
    bsdf.inputs["Coat Roughness"].default_value = kd["coat_rough"]
    if sss_w > 0:
        bsdf.inputs["Subsurface Weight"].default_value = sss_w
        bsdf.inputs["Subsurface Radius"].default_value = (0.3, 0.12, 0.06)
        bsdf.inputs["Subsurface Scale"].default_value = 0.05
    if kind == "fur":
        bsdf.inputs["Sheen Weight"].default_value = 0.8
        bsdf.inputs["Sheen Roughness"].default_value = 0.6
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = _lin(emission)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED"
    mat.diffuse_color = lin
    mat.roughness = roughness
    mat.metallic = metallic
    mat["sa_kind"] = kind
    mat["sa_tint"] = tint
    mat["sa_alpha"] = alpha
    mat["sa_metallic"] = metallic
    mat["sa_coat"] = coat_w
    mat["sa_emission"] = list(_lin(emission)) if emission is not None else [0.0, 0.0, 0.0, 1.0]
    mat["sa_emission_strength"] = emission_strength
    mat["sa_color"] = list(lin)
    return mat


# --------------------------------------------------------------------------------------------
# realism pass: geometry detail
# --------------------------------------------------------------------------------------------
def detail_object(obj, subdiv=1, displace=0.012, smooth_angle=40.0, noise_scale=0.25):
    """Subdivide (Catmull-Clark), add a subtle procedural displacement and smooth by angle."""
    if not REALISM or obj.type != "MESH":
        return obj
    select_only([obj])
    if subdiv > 0:
        m = obj.modifiers.new("Subd", "SUBSURF")
        m.levels = subdiv
        m.render_levels = subdiv
        bpy.ops.object.modifier_apply(modifier=m.name)
    if displace > 0:
        tex = bpy.data.textures.get("ChitinNoise") or bpy.data.textures.new("ChitinNoise", "CLOUDS")
        tex.noise_scale = noise_scale
        tex.noise_depth = 2
        d = obj.modifiers.new("Displace", "DISPLACE")
        d.texture = tex
        d.strength = displace
        d.mid_level = 0.5
        d.texture_coords = "LOCAL"
        bpy.ops.object.modifier_apply(modifier=d.name)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth_angle))
    except Exception:
        bpy.ops.object.shade_smooth()
    return obj


def bevel_object(obj, width, segments=2):
    """Rounded edges for box-like mechanical parts (instead of subdividing them into blobs)."""
    select_only([obj])
    b = obj.modifiers.new("Bevel", "BEVEL")
    b.width = width
    b.segments = segments
    b.limit_method = "ANGLE"
    b.angle_limit = math.radians(30)
    bpy.ops.object.modifier_apply(modifier=b.name)
    return obj


def uv_unwrap(obj, margin=0.02):
    select_only([obj])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=margin, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


# --------------------------------------------------------------------------------------------
# realism pass: texture baking and export materials
# --------------------------------------------------------------------------------------------
def _new_image(name, size, data=False):
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return img


def _principled(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def bake_object_textures(obj, asset, size=1024, samples=32, color_quality=88, orm_quality=85, normal_quality=92):
    """Bake the procedural materials of `obj` into three JPEG textures in assets/textures/<asset>/:
    `<object>_color.jpg` (albedo with crevice dirt, team tint white), `<object>_orm.jpg`
    (G = roughness, B = metallic, glTF layout) and `<object>_normal.jpg` (tangent space, OpenGL +Y).
    Returns {"color": path, "orm": path, "normal": path}."""
    from PIL import Image as PILImage

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    use_cycles_device(sc)
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 8
    sc.render.bake.use_clear = True
    sc.render.bake.use_selected_to_active = False
    out_dir = os.path.join(TEXTURE_DIR, asset)
    os.makedirs(out_dir, exist_ok=True)
    tag = obj.name.lower()

    targets = []
    backup = {}
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        node = nt.nodes.get("BakeTarget") or nt.nodes.new("ShaderNodeTexImage")
        node.name = node.label = "BakeTarget"
        targets.append((mat, node))
        p = _principled(mat)
        tn = nt.nodes.get("TeamTint")
        backup[mat.name] = {
            "tint": tuple(tn.outputs[0].default_value) if tn else None,
            "metallic": p.inputs["Metallic"].default_value if p else 0.0,
            "sss": p.inputs["Subsurface Weight"].default_value if p else 0.0,
            "alpha": p.inputs["Alpha"].default_value if p else 1.0,
            "em_col": tuple(p.inputs["Emission Color"].default_value) if p else (0, 0, 0, 1),
            "em_str": p.inputs["Emission Strength"].default_value if p else 0.0,
        }
        if tn:
            tn.outputs[0].default_value = (1, 1, 1, 1)

    def set_pass(mode):
        for mat, _ in targets:
            p = _principled(mat)
            if p is None:
                continue
            b = backup[mat.name]
            if mode == "color":
                # albedo only: no metal/subsurface/transparency weighting in the diffuse colour pass
                p.inputs["Metallic"].default_value = 0.0
                p.inputs["Subsurface Weight"].default_value = 0.0
                p.inputs["Alpha"].default_value = 1.0
            elif mode == "metal":
                m = b["metallic"]
                p.inputs["Emission Color"].default_value = (m, m, m, 1.0)
                p.inputs["Emission Strength"].default_value = 1.0
            else:
                p.inputs["Metallic"].default_value = b["metallic"]
                p.inputs["Subsurface Weight"].default_value = b["sss"]
                p.inputs["Alpha"].default_value = b["alpha"]
                p.inputs["Emission Color"].default_value = b["em_col"]
                p.inputs["Emission Strength"].default_value = b["em_str"]

    select_only([obj])
    tmp = {}
    passes = [
        ("color", "DIFFUSE", False, {"pass_filter": {"COLOR"}}, samples, "color"),
        ("rough", "ROUGHNESS", True, {}, 1, "restore"),
        ("metal", "EMIT", True, {}, 1, "metal"),
        ("normal", "NORMAL", True, {"normal_space": "TANGENT"}, 1, "restore"),
    ]
    for pname, btype, data, extra, spp, mode in passes:
        set_pass(mode)
        img = _new_image(f"bake_{tag}_{pname}", size, data=data)
        for mat, node in targets:
            node.image = img
            mat.node_tree.nodes.active = node
        sc.cycles.samples = spp
        bpy.ops.object.bake(type=btype, margin=8, use_clear=True, **extra)
        png = os.path.join(out_dir, f"{tag}_{pname}_tmp.png")
        img.filepath_raw = png
        img.file_format = "PNG"
        img.save()
        tmp[pname] = png
        bpy.data.images.remove(img)
    set_pass("restore")
    for mat, node in targets:
        mat.node_tree.nodes.remove(node)
        b = backup[mat.name]
        tn = mat.node_tree.nodes.get("TeamTint")
        if tn and b["tint"] is not None:
            tn.outputs[0].default_value = b["tint"]

    results = {}
    col = PILImage.open(tmp["color"]).convert("RGB")
    results["color"] = os.path.join(out_dir, f"{tag}_color.jpg")
    col.save(results["color"], "JPEG", quality=color_quality)
    rough = PILImage.open(tmp["rough"]).convert("L")
    metal = PILImage.open(tmp["metal"]).convert("L")
    white = PILImage.new("L", rough.size, 255)
    results["orm"] = os.path.join(out_dir, f"{tag}_orm.jpg")
    PILImage.merge("RGB", (white, rough, metal)).save(results["orm"], "JPEG", quality=orm_quality, subsampling=0)
    nrm = PILImage.open(tmp["normal"]).convert("RGB")
    results["normal"] = os.path.join(out_dir, f"{tag}_normal.jpg")
    nrm.save(results["normal"], "JPEG", quality=normal_quality, subsampling=0)
    for p in tmp.values():
        os.remove(p)
    log("baked", obj.name, f"{size}x{size}", "->", os.path.relpath(out_dir, PROJECT_ROOT),
        {k: os.path.getsize(v) for k, v in results.items()})
    return results


def build_baked_materials(obj, asset, images):
    """Replace the procedural materials of `obj` by image-based ones with the same names (the
    procedural originals are kept with a `_proc` suffix and a fake user so they can be edited and
    re-baked).  The textures are packed into the .blend so the file is self-contained."""
    col = bpy.data.images.load(images["color"], check_existing=True)
    col.colorspace_settings.name = "sRGB"
    orm = bpy.data.images.load(images["orm"], check_existing=True)
    orm.colorspace_settings.name = "Non-Color"
    nrm = bpy.data.images.load(images["normal"], check_existing=True)
    nrm.colorspace_settings.name = "Non-Color"
    for img in (col, orm, nrm):
        if not img.packed_file:
            img.pack()
    for slot in obj.material_slots:
        proc = slot.material
        if proc is None:
            continue
        if proc.name.endswith("_proc"):
            clean = proc.name[:-5]
        else:
            clean = proc.name
            proc.name = clean + "_proc"
            proc.use_fake_user = True
        mat = bpy.data.materials.new(clean)  # becomes `clean.001` when another object already took it
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.name = "Principled"
        nt.links.new(bsdf.outputs[0], out.inputs[0])
        tc = nt.nodes.new("ShaderNodeTexImage")
        tc.image = col
        tc.label = "BaseColor"
        if proc.get("sa_tint"):
            tint = tuple(proc["sa_color"])
            nt.links.new(_mix_rgb(nt, "MULTIPLY", tc.outputs["Color"], tint, 1.0), bsdf.inputs["Base Color"])
        else:
            nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
        to = nt.nodes.new("ShaderNodeTexImage")
        to.image = orm
        to.label = "ORM"
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(to.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = nrm
        tn.label = "Normal"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.space = "TANGENT"
        nm.inputs["Strength"].default_value = 1.0
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        alpha = float(proc.get("sa_alpha", 1.0))
        bsdf.inputs["Alpha"].default_value = alpha
        if alpha < 1.0:
            mat.surface_render_method = "BLENDED"
        bsdf.inputs["Coat Weight"].default_value = float(proc.get("sa_coat", 0.0))
        bsdf.inputs["Coat Roughness"].default_value = 0.15
        if float(proc.get("sa_emission_strength", 0.0)) > 0:
            bsdf.inputs["Emission Color"].default_value = tuple(proc["sa_emission"])
            bsdf.inputs["Emission Strength"].default_value = float(proc["sa_emission_strength"])
        mat.diffuse_color = proc.diffuse_color
        mat["sa_tint"] = bool(proc.get("sa_tint"))
        mat["sa_proc"] = proc.name
        slot.material = mat
    return obj


def finalize_asset(asset, objects, preview_radius, preview_center=(0, 0, 0.3), texture_size=1024, small_size=512,
                   views=("front", "back", "left", "right", "threequarter"), preview_size=512, preview_samples=64):
    """Export + previews + save for an asset, running the realism bake first when enabled.

    `objects` are the exported objects (rig + mesh for units; body, turrets and barrels for colonies).
    The first mesh object is baked at `texture_size`, the others at `small_size`.
    """
    meshes = [o for o in objects if o.type == "MESH"]
    if REALISM:
        for i, m in enumerate(meshes):
            uv_unwrap(m)
            images = bake_object_textures(m, asset, size=texture_size if i == 0 else small_size)
            build_baked_materials(m, asset, images)
    path = export_glb(asset, objects=objects)
    summary = print_summary(path)
    previews = render_previews(asset, radius=preview_radius, center=preview_center, size=preview_size,
                               samples=preview_samples, views=views)
    contact_sheet(asset, previews)
    save_blend(asset)
    return path, summary
