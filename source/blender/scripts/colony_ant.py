"""Ant colony: a steep granite cone lashed with team-coloured rope rings and thick twisted-rope
buttresses, two panelled towers carrying mushroom-cap dome turrets with twin machine guns.

Built by build_colony.py (usage in its docstring); shared helpers in colony_common.py.  The crew-A
helpers in the first section (baked shading, rope tubes, displaced lathes, and ca_finish_colony: the
_finish_colony of colony_common with packed UVs instead of salib.uv_unwrap's smart project) are also
used by colony_spider.py and colony_wasp.py.

Fifth iteration (colony crew A, 2026-10-14; Mike: "the buildings are not up to par with the original
vision").  The layout stays fitted to the original sprite (u = X, v = -(0.866 Y + 0.5 Z) at 60 deg:
cone axis, rope rings, bands, towers, south-east wall - see qa/agents/colonies/notes.txt); what
changed is bulk, relief and surface:
  * the cone is a craggy granite mass: boulder facets and cracks displaced into the mesh (Worley
    F1/F2), the ropes bedded into it, a steeper summit (the tall cone of loading screen 0);
  * the thick bands are twisted three-strand ropes (real geometry) whose feet flare onto the ground
    like buttresses; the thin rings carry a two-strand twist in the baked normal and colour maps;
  * the towers are panelled columns with bands and a capital, the south one on a fluted skirt;
  * the turrets are mushroom-cap domes (loading screen 0) with a twin machine-gun cradle on the
    crown: two long, thick, jacketed grey barrels run out over the brim (no dark bores or bright
    muzzle rings: seen end-on, as idle turrets are, those read as eyes), so they read as guns;
  * every material bakes light-independent shading into its colour map: wide-range ambient
    occlusion, crevice occlusion, ground contact, sky light (bright tops, darker flanks) and grain
    (team-coloured ones stay near white where open, so the runtime tint keeps its depth).
"""
import math
import os
import random

import mathutils
from mathutils import Matrix, Vector, noise

from colony_common import *  # noqa: F401,F403


# =============================================================================================
# crew-A shared helpers
# =============================================================================================
def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _m(nt, op, a, b=0.0, c=None):
    """Math node with up to three inputs (sockets or constants)."""
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if hasattr(v, "node"):
            nt.links.new(v, n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n.outputs[0]


def _remap(nt, value, from_lo, from_hi, to_lo, to_hi):
    n = nt.nodes.new("ShaderNodeMapRange")
    n.clamp = True
    n.inputs["From Min"].default_value = from_lo
    n.inputs["From Max"].default_value = from_hi
    n.inputs["To Min"].default_value = to_lo
    n.inputs["To Max"].default_value = to_hi
    nt.links.new(value, n.inputs["Value"])
    return n.outputs["Result"]


def _mul_base(mat, factor):
    """Multiply the material's base colour by a scalar or colour socket."""
    nt = mat.node_tree
    p = _principled(mat)
    src = p.inputs["Base Color"].links[0].from_socket
    nt.links.new(salib._mix_rgb(nt, "MULTIPLY", src, factor, 1.0), p.inputs["Base Color"])


def ca_bake_shading(mat, ao=0.8, ao_dark=0.3, ao_gamma=1.3, crevice=0.12, crevice_dark=0.6, edge=0.0,
                    edge_dist=0.06, grain=0.0, grain_scale=45.0, foot=0.35, foot_dark=0.6, sky=0.3, local=False):
    """Light-independent shading multiplied into the base colour, so the colour bake carries it:
    wide-range occlusion (deep shadow under bands, between towers and cone), crevice occlusion,
    ground contact, sky light (up-facing 1, vertical 1 - sky/2, down-facing 1 - sky: the original
    renders' bright tops and darker flanks), fine grain, and optionally brighter worn convex edges
    (inside-AO edge mask)."""
    nt = mat.node_tree
    terms = []
    if sky > 0:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
        terms.append(_remap(nt, sep.outputs["Z"], -1.0, 1.0, 1.0 - sky, 1.0))

    def occlusion(dist, inside=False):
        n = nt.nodes.new("ShaderNodeAmbientOcclusion")
        n.inputs["Distance"].default_value = dist
        n.samples = 16
        n.only_local = local
        n.inside = inside
        return n.outputs["AO"]

    if ao > 0:
        v = occlusion(ao)
        if ao_gamma != 1.0:
            v = _m(nt, "POWER", v, ao_gamma)
        terms.append(_remap(nt, v, 0.0, 1.0, ao_dark, 1.0))
    if crevice > 0:
        terms.append(_remap(nt, occlusion(crevice), 0.0, 1.0, crevice_dark, 1.0))
    if edge > 0:
        terms.append(_remap(nt, occlusion(edge_dist, inside=True), 0.55, 1.0, 1.0 + edge, 1.0))
    if grain > 0:
        g = salib._noise(nt, _coord(nt), grain_scale, detail=3.0, roughness=0.6)
        terms.append(_remap(nt, g.outputs["Factor"], 0.3, 0.7, 1.0 - grain, 1.0))
    if foot > 0:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
        terms.append(_remap(nt, sep.outputs["Z"], 0.0, foot, foot_dark, 1.0))
    fac = terms[0]
    for t in terms[1:]:
        fac = _m(nt, "MULTIPLY", fac, t)
    _mul_base(mat, fac)
    return mat


def ca_rope_pattern(mat, strands=3, groove_dark=0.5, weight=1.0):
    """Twisted strands on tubes built by rope_tube(): the mesh attribute `rope` = (s, cos t, sin t)
    (s = length along the rope / pitch, t = angle round it) gives the helical strand phase.  The
    grooves go dark in the colour and low in the bump (both end up in the baked maps)."""
    nt = mat.node_tree
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = "rope"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(at.outputs["Vector"], sep.inputs["Vector"])
    theta = _m(nt, "ARCTAN2", sep.outputs["Z"], sep.outputs["Y"])
    phase = _m(nt, "MULTIPLY", _m(nt, "SUBTRACT", theta, _m(nt, "MULTIPLY", sep.outputs["X"], 2.0 * math.pi)), strands)
    crest = _m(nt, "MULTIPLY_ADD", _m(nt, "COSINE", phase), 0.5, 0.5)  # 1 on a strand, 0 in a groove
    height = _m(nt, "POWER", crest, 0.5)
    add_height(mat, height, weight)
    _mul_base(mat, _remap(nt, height, 0.0, 0.75, groove_dark, 1.0))
    return mat


def ca_cracks(mat, scale=4.0, width=0.035, dark=0.45, weight=0.8, distort=0.35):
    """Wandering hairline cracks (Voronoi distance-to-edge on a noise-distorted lookup)."""
    nt = mat.node_tree
    coord = _coord(nt)
    n = salib._noise(nt, coord, 2.5, detail=3.0, roughness=0.5)
    off = nt.nodes.new("ShaderNodeVectorMath")
    off.operation = "MULTIPLY_ADD"
    nt.links.new(n.outputs["Color"], off.inputs[0])
    off.inputs[1].default_value = (distort, distort, distort)
    nt.links.new(coord, off.inputs[2])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = scale
    nt.links.new(off.outputs["Vector"], vor.inputs["Vector"])
    line = _remap(nt, vor.outputs["Distance"], 0.0, width, 0.0, 1.0)
    _mul_base(mat, _remap(nt, line, 0.0, 1.0, dark, 1.0))
    add_height(mat, line, weight)
    return mat


def ca_material(name, color, kind="chitin", tint=False, roughness=0.45, metallic=0.0, variation=0.1,
                cell_scale=8.0, bump=0.3, coat=0.3, shading=None, **kw):
    """salib procedural material (its own crevice dirt off) + ca_bake_shading(**shading)."""
    mat = salib.material(name, color, roughness=roughness, metallic=metallic, kind=kind, tint=tint,
                         variation=variation, cell_scale=cell_scale, bump=bump, dirt=0.0, coat=coat, **kw)
    ca_bake_shading(mat, **(shading or {}))
    return mat


# ---------------------------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------------------------
def _mesh_object(name, verts, faces, mat_obj, smooth=True, attrs=None, uvs=None):
    """Mesh object from vertices/faces; `attrs` = {name: (type, per-vertex vectors)}, `uvs` = per face
    the list of its corner UVs (layer "UVMap", the name every bpy primitive uses, so joins merge)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    if attrs:
        for an, (atype, values) in attrs.items():
            a = me.attributes.new(an, atype, "POINT")
            flat = [c for v in values for c in v]
            a.data.foreach_set("vector", flat)
    if uvs is not None:
        layer = me.uv_layers.new(name="UVMap")
        for poly, fuv in zip(me.polygons, uvs):
            for li, uv in zip(poly.loop_indices, fuv):
                layer.data[li].uv = uv
    o = bpy.data.objects.new(name, me)
    salib.link(o)
    o.data.materials.append(mat_obj)
    for f in o.data.polygons:
        f.use_smooth = smooth
    return o


def ensure_uv(o):
    """Give a part without UVs (colony_common's fluted_cyl, curved_wall...) its own smart-project
    islands before it is joined."""
    if not o.data.uv_layers:
        salib.select_only([o])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    return o


def ca_unwrap(obj, margin=0.006):
    """Pack the islands the parts brought along (primitive UVs, tube and lathe unwraps) at one texel
    density - instead of salib.uv_unwrap's smart project, which cut the displaced rock and the ropes
    into hundreds of tiny islands and left most of the atlas empty."""
    salib.select_only([obj])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def ca_finalize_asset(asset, objects, preview_radius, preview_center=(0, 0, 0.3), texture_size=1024, small_size=512,
                      views=("front", "back", "left", "right", "threequarter"), preview_size=512, preview_samples=64):
    """salib.finalize_asset with ca_unwrap() in place of salib.uv_unwrap() (bake, baked materials,
    GLB export, previews, contact sheet, .blend)."""
    meshes = [o for o in objects if o.type == "MESH"]
    for i, m in enumerate(meshes):
        ca_unwrap(m)
        images = salib.bake_object_textures(m, asset, size=texture_size if i == 0 else small_size)
        salib.build_baked_materials(m, asset, images)
    path = salib.export_glb(asset, objects=objects)
    summary = salib.print_summary(path)
    previews = salib.render_previews(asset, radius=preview_radius, center=preview_center, size=preview_size,
                                     samples=preview_samples, views=views)
    salib.contact_sheet(asset, previews)
    salib.save_blend(asset)
    return path, summary


def ca_finish_colony(name, body, turrets, barrels_all, radius, center_z, quick=False):
    """colony_common._finish_colony with ca_finalize_asset() (packed UVs) for the bake/export."""
    objs = [body] + turrets + [b for bs in barrels_all for b in bs]
    tris = {o.name: tri_count(o) for o in objs}
    total = sum(tris.values())
    salib.log(name, "triangles", total, tris)
    assert total <= TRI_BUDGET, f"{name}: {total} triangles over budget {TRI_BUDGET}"
    for t in turrets:
        assert t.rotation_euler[:] == (0.0, 0.0, 0.0) and tuple(round(s, 4) for s in t.scale) == (1, 1, 1)
    for o in objs:
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            assert abs(w.x) <= 3.05 and abs(w.y) <= 3.05, f"{name}: {o.name} leaves the 6x6 footprint at {w}"
    if quick:
        if QA_DIR:
            os.makedirs(QA_DIR, exist_ok=True)
            sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview_body.png"), turrets=False, transparent=True)
            png = sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview_quick.png"))
            sprite_comparison(name, png, os.path.join(QA_DIR, f"{name}_compare_quick.jpg"))
        return None
    idle_clip(body)
    for t, bs in zip(turrets, barrels_all):
        turret_fire_clip(t, bs)
    _clear_textures(name)
    path, s = ca_finalize_asset(name, objs, preview_radius=radius, preview_center=(0, 0, center_z),
                                views=("front", "back", "left", "right", "threequarter", "top"))
    for i in range(len(turrets)):
        assert f"Turret_{i + 1}" in s["node_names"], s["node_names"]
    assert "M_Colony" in s["materials"], s["materials"]
    clips = sorted(a["name"] for a in s["animations"])
    assert clips == ["idle", "turret_fire"], clips
    if QA_DIR:
        os.makedirs(QA_DIR, exist_ok=True)
        sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview_body.png"), turrets=False, transparent=True)
        png = sprite_view_render(os.path.join(QA_DIR, f"{name}_spriteview.png"))
        sprite_comparison(name, png, os.path.join(QA_DIR, f"{name}_compare.jpg"))
        with open(os.path.join(QA_DIR, f"{name}_build.txt"), "w") as f:
            f.write(f"{name}\ntriangles {total} {tris}\nnodes {s['node_names']}\nmaterials {s['materials']}\n"
                    f"clips {s['animations']}\nturrets {[tuple(round(c, 3) for c in t.matrix_world.translation) for t in turrets]}\n")
    return path


def resample_path(pts, step):
    """Catmull-Rom through `pts`, then even arc-length samples about `step` apart.
    Returns (samples, total_length, fraction-of-control-path per sample)."""
    dense = [Vector(p) for p in _smooth_path(pts, 10)]
    cum = [0.0]
    for a, b in zip(dense, dense[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    n = max(2, int(round(total / step)) + 1)
    out, fr = [], []
    j = 0
    for i in range(n):
        s = total * i / (n - 1)
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        t = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append(dense[j].lerp(dense[j + 1], t))
        fr.append(i / (n - 1))
    return out, total, fr


def _transport_frames(pts, closed=False):
    n = len(pts)
    tans = []
    for i in range(n):
        if closed:
            a, b = pts[(i - 1) % n], pts[(i + 1) % n]
        else:
            a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        tans.append((b - a).normalized())
    t0 = tans[0]
    ref = Vector((0, 0, 1)) if abs(t0.z) < 0.9 else Vector((1, 0, 0))
    nrm = (ref - t0 * ref.dot(t0)).normalized()
    norms = [nrm]
    for i in range(1, n):
        axis = tans[i - 1].cross(tans[i])
        if axis.length > 1e-9:
            nrm = Matrix.Rotation(tans[i - 1].angle(tans[i]), 3, axis.normalized()) @ nrm
        nrm = (nrm - tans[i] * nrm.dot(tans[i])).normalized()
        norms.append(nrm)
    return tans, norms


def rope_tube(mats, name, pts, radius, mat, radius_fn=None, sides=12, step=0.07, closed=False, pitch=0.5,
              strands=0, depth=0.0, caps=True, surface_fn=None):
    """Round tube swept along a smooth path through `pts` (radius x radius_fn(fraction along)).
    `strands` > 0 twists `strands` lobes into the cross-section (`depth` = groove depth, relative),
    one turn per `pitch` cells, like a laid rope; surface_fn(p) (p = the undisplaced surface point)
    scales the radius per vertex (knobs, scales).  Every vertex stores the attribute
    `rope` = (s / pitch, cos t, sin t) for ca_rope_pattern()."""
    if closed:  # `pts` = a dense loop (the curve closes from the last point back to the first)
        p = [Vector(q) for q in pts]
        smp = resample_path(p + [p[0]], step)[0][:-1]
        fr = [i / len(smp) for i in range(len(smp))]
        loop = sum((smp[(i + 1) % len(smp)] - smp[i]).length for i in range(len(smp)))
        pitch = loop / max(1, round(loop / pitch))  # whole turns: no seam in the twist
    else:
        smp, total, fr = resample_path(pts, step)
    tans, norms = _transport_frames(smp, closed)
    verts, faces, ropev, us, rads = [], [], [], [], []
    s_acc = 0.0
    for i, (c, t, nv) in enumerate(zip(smp, tans, norms)):
        if i:
            s_acc += (smp[i] - smp[i - 1]).length
        us.append(s_acc)
        bv = t.cross(nv)
        r = radius * (radius_fn(fr[i]) if radius_fn else 1.0)
        rads.append(r)
        s = s_acc / pitch
        for j in range(sides):
            th = 2.0 * math.pi * j / sides
            d = nv * math.cos(th) + bv * math.sin(th)
            k = 1.0
            if strands and depth > 0:
                g = 0.5 - 0.5 * math.cos(strands * (th - 2.0 * math.pi * s))  # 0 crest .. 1 groove
                k = 1.0 - depth * g ** 2.2
            if surface_fn is not None:
                k *= surface_fn(c + d * r)
            verts.append(c + d * (r * k))
            ropev.append((s, math.cos(th), math.sin(th)))
    rows = len(smp)
    if closed:
        us.append(us[-1] + (smp[0] - smp[-1]).length)
    last = rows if closed else rows - 1
    circ = 2.0 * math.pi * sum(rads) / len(rads)
    uvs = []
    for i in range(last):
        a0, b0 = i * sides, ((i + 1) % rows) * sides
        for j in range(sides):
            k = (j + 1) % sides
            faces.append((a0 + j, a0 + k, b0 + k, b0 + j))
            v0, v1 = circ * j / sides, circ * (j + 1) / sides
            uvs.append([(us[i], v0), (us[i], v1), (us[i + 1], v1), (us[i + 1], v0)])
    cap_faces = []
    if caps and not closed:
        for ring, rr, ox in ((range(sides - 1, -1, -1), rads[0], -2.0 * rads[0] - 0.1),
                             (range(sides), rads[-1], us[-1] + 2.0 * rads[-1] + 0.1)):
            ring = list(ring)
            cap_faces.append(tuple((0 if ox < 0 else rows - 1) * sides + j for j in ring))
            uvs.append([(ox + rr * math.cos(2 * math.pi * j / sides), circ + rr + rr * math.sin(2 * math.pi * j / sides))
                        for j in ring])
    o = _mesh_object(name, verts, faces + cap_faces, mats[mat], attrs={"rope": ("FLOAT_VECTOR", ropev)}, uvs=uvs)
    for f in o.data.polygons[len(faces):]:
        f.use_smooth = False
    return o


def lathe_samples(profile, step=0.05):
    """Even samples along a lathe profile [(r, z), ...] (Catmull-Rom; ends with r = 0 for a closed
    top): [(r, z, nr, nz)] with the outward unit normal of the profile curve."""
    dense = _catmull(profile, 16)
    cum = [0.0]
    for (r0, z0), (r1, z1) in zip(dense, dense[1:]):
        cum.append(cum[-1] + math.hypot(r1 - r0, z1 - z0))
    n = max(3, int(round(cum[-1] / step)) + 1)
    out = []
    j = 0
    for i in range(n):
        s = cum[-1] * i / (n - 1)
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        t = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        r = dense[j][0] + (dense[j + 1][0] - dense[j][0]) * t
        z = dense[j][1] + (dense[j + 1][1] - dense[j][1]) * t
        dr, dz = dense[j + 1][0] - dense[j][0], dense[j + 1][1] - dense[j][1]
        ln = math.hypot(dr, dz) or 1.0
        out.append((r, z, dz / ln, -dr / ln))
    return out


def worley_rock(p, cell=0.55, amp=0.12, crack=0.05, seed=0, rough=0.035):
    """Displacement of a craggy rock surface at p: rounded boulder facets (Worley F1) parted by
    cracks (F2 - F1 -> 0 on the cell borders), plus a little fractal roughness."""
    off = Vector((seed * 7.31, seed * 3.17 + 1.3, seed * 1.93 + 4.1))
    q = p / cell + off
    d, _ = noise.voronoi(q, distance_metric="DISTANCE", exponent=2.5)
    border = smoothstep(0.0, 0.32, d[1] - d[0])
    bulge = max(0.0, 1.0 - min(1.0, d[0] / 1.05) ** 2) ** 0.35  # broad, flattish facets
    v = amp * (0.3 + 0.7 * bulge) * border - crack * (1.0 - border)
    return v + rough * noise.fractal(p * 1.9 + off, 0.55, 2.0, 3)


def displaced_lathe(name, mats, mat, axis, profile, scale=(1.0, 1.0), segments=96, step=0.06, disp=None,
                    damp=None, sink=0.02, rot=0.0, seam_deg=90.0):
    """Lathe solid on the ground (open bottom) whose vertices move along the surface normal by
    disp(p) * damp(p) - sink * (1 - damp(p)) (damp = 0 where ropes/bands lie on it).  UVs: one
    island, cut along the meridian at seam_deg."""
    smp = lathe_samples(profile, step)
    cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    verts, faces, rings = [], [], []
    for (r, z, nr, nz) in smp[:-1]:
        ring = []
        for j in range(segments):
            a = 2.0 * math.pi * j / segments
            ca, sa = math.cos(a), math.sin(a)
            lx, ly = r * scale[0] * ca, r * scale[1] * sa
            p = Vector((axis[0] + lx * cr - ly * sr, axis[1] + lx * sr + ly * cr, z))
            nx, ny = nr * ca / scale[0], nr * sa / scale[1]
            n = Vector((nx * cr - ny * sr, nx * sr + ny * cr, nz)).normalized()
            if disp is not None:
                w = damp(p) if damp else 1.0
                p = p + n * (disp(p) * w - sink * (1.0 - w))
            p.z = 0.0 if z <= 1e-6 else max(0.0, p.z)
            ring.append(len(verts))
            verts.append(p)
        rings.append(ring)
    top_r, top_z = smp[-1][0], smp[-1][1]
    apex = Vector((axis[0], axis[1], top_z))
    if disp is not None:
        apex.z += disp(apex) * (damp(apex) if damp else 1.0)
    verts.append(apex)
    for ra, rb in zip(rings, rings[1:]):
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((ra[j], ra[k], rb[k], rb[j]))
    last = rings[-1]
    for j in range(segments):
        faces.append((last[j], last[(j + 1) % segments], len(verts) - 1))
    o = _mesh_object(name, verts, faces, mats[mat])
    # one seam down the meridian at `seam_deg` (the back, away from the game camera): the lathe
    # unrolls into a single island
    js = int(round(seam_deg / 360.0 * segments)) % segments
    seam = {tuple(sorted((ra[js], rb[js]))) for ra, rb in zip(rings, rings[1:])}
    seam.add(tuple(sorted((rings[-1][js], len(verts) - 1))))
    for e in o.data.edges:
        if tuple(sorted(e.vertices)) in seam:
            e.use_seam = True
    salib.select_only([o])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    return o


def band_damp(rings_z, band_pts, band_r, ring_w=(0.05, 0.16), band_w=(0.03, 0.2)):
    """damp(p) for displaced_lathe: 0 under the rope rings (at heights rings_z) and the bands (paths
    band_pts, tube radius band_r), 1 elsewhere."""
    kd = None
    if band_pts:
        kd = mathutils.kdtree.KDTree(len(band_pts))
        for i, q in enumerate(band_pts):
            kd.insert(q, i)
        kd.balance()

    def damp(p):
        w = 1.0
        for zr in rings_z:
            w = min(w, smoothstep(ring_w[0], ring_w[1], abs(p.z - zr)))
        if kd is not None:
            _, _, dist = kd.find(p)
            w = min(w, smoothstep(band_r + band_w[0], band_r + band_w[1], dist))
        return w

    return damp


# =============================================================================================
# ANT
# =============================================================================================
# Layout measured off the sprite by the previous crew (60-degree ortho projection), kept: the rope
# rings at z 1.0 / 1.35 / 1.7 (radii 1.27 / 0.95 / 0.66) fix the cone axis and its 49-degree flank;
# the summit now rises to 2.82 (loading screen 0 shows a tall, pointed cone as high as the towers;
# the guns on the turret crowns, at 3.1, still clear it).
ANT_AXIS = (-0.33, 0.59)
# (the rock displacement adds ~0.08 on average, so the lathe sits that much inside the sprite outline)
ANT_PROFILE = [(2.06, 0.0), (1.99, 0.14), (1.73, 0.48), (1.21, 1.0), (0.9, 1.35), (0.62, 1.7), (0.43, 2.05),
               (0.27, 2.38), (0.12, 2.66), (0.0, 2.82)]
ANT_SCALE = (1.0, 0.95)
ANT_RINGS = (1.0, 1.35, 1.7)
ANT_TOWER_H = 2.5
ANT_TOWER_R = 0.48
ANT_TOWERS = ((0.5, 1.33), (-0.12, -1.29))  # Turret_1 north-east (foot hidden in the cone), Turret_2 south
ANT_BAND_R = 0.19
# thick buttress bands (top angle, top height, foot angle, foot flare), from the sprite: the C-arc
# over the north-west shoulder down to the west foot, two on the south-west flank (their feet at
# u -2.35 and u -1.1), one east-north-east (foot at u 1.75, v 0.75)
ANT_BANDS = ((95, 1.0, 174, 0.05), (218, 1.35, 200, 0.05), (238, 1.35, 249, 0.05), (45, 1.35, 8, 0.04))
ANT_GUN_Z = 0.6  # barrel axis above the tower top (guns on the dome's crown) -> colonies.ron height 3.1


def ant_r(z):
    return lathe_r(ANT_PROFILE, z)


def ant_point(angle_deg, r, z):
    a = math.radians(angle_deg)
    return Vector((ANT_AXIS[0] + r * ANT_SCALE[0] * math.cos(a), ANT_AXIS[1] + r * ANT_SCALE[1] * math.sin(a), z))


def ant_band_path(a_top, z_top, a_foot, flare, n=12):
    """Centre line of a band lying on the cone: from (a_top, z_top) down the flank (turning to
    a_foot); its lower part bows off the flank and lands beyond the foot like a buttress."""
    pts = []
    for k in range(n + 1):
        f = k / n
        a = a_top + (a_foot - a_top) * f
        z = z_top * (1.0 - f)
        r = ant_r(z) + ANT_BAND_R * 0.5 + flare * smoothstep(0.45, 1.0, f)
        if k == n:
            z = ANT_BAND_R * 0.62
        pts.append(ant_point(a, r, z))
    return pts


def ant_materials():
    col = (0.97, 0.85, 0.47)
    team = dict(ao=0.85, ao_dark=0.3, ao_gamma=1.4, crevice=0.1, crevice_dark=0.55, grain=0.07, foot=0.45,
                foot_dark=0.55)
    m = {}
    m["M_Colony"] = ca_material("M_Colony", col, tint=True, roughness=0.36, variation=0.08, cell_scale=7.0, bump=0.25,
                                coat=0.35, shading=team)
    m["M_Colony.rope"] = ca_rope_pattern(ca_material("M_Colony.rope", col, tint=True, roughness=0.42, variation=0.08,
                                                     cell_scale=12.0, bump=0.3, coat=0.25, shading=team),
                                         strands=3, groove_dark=0.62, weight=1.0)
    m["M_Colony.ring"] = ca_rope_pattern(ca_material("M_Colony.ring", col, tint=True, roughness=0.42, variation=0.08,
                                                     cell_scale=12.0, bump=0.3, coat=0.25, shading=team),
                                         strands=2, groove_dark=0.62, weight=1.0)
    m["M_Colony.dark"] = darken(ca_material("M_Colony.dark", col, tint=True, roughness=0.4, variation=0.06, bump=0.2,
                                            coat=0.3, shading=dict(team, foot=0.0)), 0.42)
    # granite: olive grey-brown (the game's ambient is bluish: a warm-purple base reads mauve) with
    # black and white crystal speckle big enough to survive at game distance, hairline cracks
    granite = ca_material("M_Granite", (0.44, 0.39, 0.3), kind="stone", roughness=0.86, variation=0.55, bump=0.7,
                          coat=0.0, shading=dict(ao=1.0, ao_dark=0.2, ao_gamma=1.3, crevice=0.16, crevice_dark=0.38,
                                                 edge=0.35, edge_dist=0.07, foot=0.35, foot_dark=0.6, sky=0.35))
    m["M_Granite"] = ca_cracks(speckle(granite, scale=18.0, dark=0.36, light=1.6, lo=0.36, hi=0.64, bump=0.3),
                               scale=3.0, width=0.035, dark=0.42, weight=0.9)
    m["M_GunA"] = ca_material("M_GunA", (0.42, 0.41, 0.38), kind="glossy", roughness=0.3, metallic=0.3, coat=0.5,
                              shading=dict(ao=0.3, ao_dark=0.45, crevice=0.05, crevice_dark=0.55, foot=0.0, sky=0.25))
    return m


def ant_tower(mats, x, y, skirt):
    h, r = ANT_TOWER_H, ANT_TOWER_R
    parts = [ensure_uv(fluted_cyl(mats, (x, y, 0.0), r, h - 0.2, "M_Colony", flutes=12, groove=0.045, segs_per=3,
                                  name="Shaft"))]
    for z in (0.86, 1.68):  # raised bands round the shaft
        parts.append(_torus(mats, (x, y, z), r + 0.005, 0.05, "M_Colony", segs=(32, 6)))
    # capital: a thick collar with rolled edges under the turret
    parts.append(_cyl(mats, (x, y, h - 0.11), r + 0.04, 0.2, "M_Colony", verts=40))
    for z in (h - 0.205, h - 0.02):
        parts.append(_torus(mats, (x, y, z), r + 0.04, 0.045, "M_Colony", segs=(32, 6)))
    if skirt:  # the fluted skirt round the foot of the south tower (sprite)
        parts.append(ensure_uv(fluted_cyl(mats, (x, y, 0.0), r + 0.11, 0.72, "M_Colony", flutes=18, groove=0.07,
                                          segs_per=2, name="Skirt")))
        parts.append(_torus(mats, (x, y, 0.73), r + 0.07, 0.055, "M_Colony", segs=(32, 6)))
    return parts


def ant_turret(name, mats, pivot):
    """Mushroom-cap dome (team colour; the caps of loading screen 0) on a dark seat ring; on its crown
    a twin machine-gun cradle whose two long barrels run out over the brim, as the turret sprite's
    barrels leave the ball's centre.  Mid-grey metal with cooling jackets, a clamp and plain muzzle
    brakes (no dark bores or bright rings: seen end-on those read as eyes).  Barrel tips 1.26 from
    the yaw axis, barrel axis ANT_GUN_Z above the tower top."""
    p = Vector(pivot)
    g = ANT_GUN_Z
    fixed = [_cyl(mats, p + Vector((0, 0, 0.05)), 0.42, 0.1, "M_Colony.dark", verts=32),
             _sphere(mats, p + Vector((0, 0, 0.26)), 0.56, "M_Colony", scale=(1, 1, 0.54), segments=32, rings=16),
             _torus(mats, p + Vector((0, 0, 0.2)), 0.55, 0.07, "M_Colony", segs=(32, 8)),
             _torus(mats, p + Vector((0, 0, 0.42)), 0.36, 0.02, "M_Colony.dark", segs=(32, 4))]
    for k in range(8):  # rivets round the brim
        a = math.radians(22.5 + 45 * k)
        fixed.append(_sphere(mats, p + Vector((0.52 * math.cos(a), 0.52 * math.sin(a), 0.27)), 0.035, "M_GunA",
                             segments=6, rings=4))
    rx = math.radians(90)
    moving = [_box(mats, p + Vector((0, 0.03, g - 0.03)), (0.36, 0.52, 0.2), "M_GunA", bevel=0.05),  # receiver
              _box(mats, p + Vector((0, 0.33, g - 0.05)), (0.24, 0.16, 0.16), "M_Colony.dark", bevel=0.04),  # ammo box
              _box(mats, p + Vector((0, -0.86, g)), (0.3, 0.07, 0.09), "M_GunA", bevel=0.02)]  # barrel clamp
    for sx in (-1, 1):
        x = sx * 0.095
        moving += [_cyl(mats, p + Vector((x, -0.74, g)), 0.056, 1.04, "M_GunA", verts=14, rot=(rx, 0, 0)),
                   _cyl(mats, p + Vector((x, -0.42, g)), 0.085, 0.42, "M_GunA", verts=14, rot=(rx, 0, 0)),
                   _cyl(mats, p + Vector((x, -1.2, g)), 0.074, 0.12, "M_GunA", verts=14, rot=(rx, 0, 0))]
    return _make_turret(name, mats, pivot, fixed, moving)


def build_ant_colony(quick=False):
    name = "colony_ant"
    salib.reset_scene(name)
    mats = colony_materials("Y")
    mats.update(ant_materials())
    bands = [ant_band_path(*b) for b in ANT_BANDS]
    band_pts = [q for path in bands for q in resample_path(path, 0.05)[0]]
    damp = band_damp(ANT_RINGS, band_pts, ANT_BAND_R)
    parts = [displaced_lathe("Mound", mats, "M_Granite", ANT_AXIS, ANT_PROFILE, scale=ANT_SCALE, segments=112, step=0.065,
                             disp=lambda p: (worley_rock(p, cell=0.46, amp=0.12, crack=0.06, seed=4) +
                                             worley_rock(p, cell=0.22, amp=0.035, crack=0.02, seed=9, rough=0.0)) *
                             (1.0 - 0.6 * smoothstep(2.3, 2.82, p.z)), damp=damp)]
    rnd = random.Random(8)
    # loose boulders round the foot (not where the wall, the south tower or band feet stand)
    k = 0
    while k < 10:
        a = rnd.uniform(70, 300)
        if any(abs(a - b[2]) < 9 for b in ANT_BANDS):
            continue
        x, y, _ = ant_point(a, ant_r(0.0) + rnd.uniform(-0.2, -0.04), 0.0)
        s = rnd.uniform(0.15, 0.24)
        parts.append(_sphere(mats, (x, y, s * 0.25), s, "M_Granite", ico=1, jitter=s * 0.1, seed=40 + k,
                             scale=(rnd.uniform(1.0, 1.45), rnd.uniform(1.0, 1.45), rnd.uniform(0.6, 0.85)),
                             rot=(0, 0, rnd.uniform(0, 3))))
        k += 1
    # thin rope rings round the cone (two-strand twist in the baked maps), bedded in the rock
    for i, z in enumerate(ANT_RINGS):
        r = ant_r(z) + 0.035
        ring = [ant_point(j * 360 / 48, r, z) for j in range(48)]
        parts.append(rope_tube(mats, f"Ring{i}", ring, 0.072, "M_Colony.ring", sides=10, step=0.075, closed=True,
                               pitch=0.24))
    # thick three-strand buttress bands, fatter where they meet the ground
    for i, path in enumerate(bands):
        parts.append(rope_tube(mats, f"Band{i}", path, ANT_BAND_R, "M_Colony.rope", sides=15, step=0.065, pitch=0.8,
                               strands=3, depth=0.1, radius_fn=lambda f: 0.85 + 0.2 * smoothstep(0.5, 1.0, f)))
    for i, (x, y) in enumerate(ANT_TOWERS):
        parts += ant_tower(mats, x, y, skirt=(i == 1))

    # the curved ramp-wall round the south-east foot: a flat top about 1 high with a sloping outer
    # face, from the south tower round to the east, where it curls down; a rolled lip and ribs

    def wall_h(t):
        return 1.0 - 0.08 * t - (0.6 * ((t - 0.72) / 0.28) ** 1.5 if t > 0.72 else 0.0)

    def batter(t):
        return 0.1 + 0.45 * max(0.0, 1 - t / 0.45) ** 2

    parts.append(ensure_uv(curved_wall(mats, ANT_AXIS, -78, -20, lambda t: 2.12, lambda t: 2.48, wall_h, "M_Colony",
                                       steps=40, bevel=0.07, name="Wall", batter=batter)))
    lip = []
    for k in range(25):
        t = k / 24
        a = math.radians(-78 + 58 * t)
        r = 2.47
        lip.append((ANT_AXIS[0] + r * math.cos(a), ANT_AXIS[1] + r * math.sin(a), wall_h(t) - 0.01))
    parts.append(rope_tube(mats, "WallLip", lip, 0.06, "M_Colony", sides=10, step=0.07))
    for t in (0.12, 0.3, 0.48, 0.64):
        a = math.radians(-78 + 58 * t)
        h = wall_h(t)
        top = Vector((ANT_AXIS[0] + 2.5 * math.cos(a), ANT_AXIS[1] + 2.5 * math.sin(a), h - 0.08))
        foot = Vector((ANT_AXIS[0] + (2.5 + batter(t)) * math.cos(a), ANT_AXIS[1] + (2.5 + batter(t)) * math.sin(a), 0.04))
        parts.append(rope_tube(mats, f"Rib{t}", [top, top.lerp(foot, 0.5), foot], 0.055, "M_Colony", sides=8, step=0.08))
    body = join_into(parts, "ColonyBody")
    turrets, barrels_all = [], []
    for i, (x, y) in enumerate(ANT_TOWERS):
        t, bs = ant_turret(f"Turret_{i + 1}", mats, (x, y, ANT_TOWER_H))
        _attach(t, body)
        turrets.append(t)
        barrels_all.append(bs)
    return ca_finish_colony(name, body, turrets, barrels_all, 9.0, 1.2, quick)
