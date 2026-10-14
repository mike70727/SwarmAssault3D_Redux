"""Colonies from Tripo image-to-3D models (sixth iteration, 2026-10-14).

Mike generated each colony in Tripo from its original in-game sprite (the 144-px body sprite,
enlarged); this script turns such a raw Tripo download (OBJ + base colour / roughness / metallic /
normal maps, ~2 M triangles) into a game colony with the colony contract of build_colony.py:

  1. fit   - import the OBJ and find the rotation about Z, uniform scale and ground offset that lay
             the model's silhouette, seen from the sprite camera (u = X, v = -(0.866 Y + 0.5 Z),
             24 px per cell, frame centre = colony centre), over the original sprite's silhouette;
  2. build - the fitted model is the high-poly source: a decimated copy is unwrapped and gets the
             source's colour, roughness, metallic and normals baked onto it; its faces are split
             into team-coloured parts (M_Colony: the bright team colour; M_ColonyPale: the muted
             towers) and the rest (shell: chrome, earth, the dark interior - the source's own
             colours); team texels are stored as grey (brightness relative to the team colour) so
             the game's colour factor recolours them; the procedural turrets of the colony's own
             builder go on the tower tops; idle / turret_fire clips; GLB export; sprite-view check.

Usage: blender -b --factory-startup --python colony_tripo.py -- colony_spider --src <model.obj>
           [--fit-only] [--quick]
SA_COLONY_REF_DIR = folder with colony_<family>/colony_body_Y.png (the original sprite sheets, 3x,
background (52, 56, 62)); SA_COLONY_QA_DIR = where the check images go.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import salib  # noqa: E402
from colony_common import QA_DIR, REF_DIR, SPRITE_ELEVATION  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

PX_PER_CELL = 24  # original sprite scale
FRAME = 144  # original sprite frame (px)
SHEET_BG = (52, 56, 62)  # background of the 3x reference sheets


# ---------------------------------------------------------------------------------------------
# sprite silhouette and projection
# ---------------------------------------------------------------------------------------------
def sprite_mask(name, team="Y"):
    """The original body sprite's silhouette (FRAME x FRAME bool, row 0 = top) from the 3x sheet."""
    path = os.path.join(REF_DIR, name, f"colony_body_{team}.png")
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    rgb = np.flipud(px.reshape(h, w, 4))[:, :, :3]  # Blender rows start at the bottom
    frame = rgb[: 3 * FRAME, : 3 * FRAME]
    bg = np.array(SHEET_BG, np.float32) / 255.0
    solid = np.abs(frame - bg).max(axis=2) > 1.5 / 255.0
    # the sheet is a 3x nearest-neighbour enlargement: one sample per original pixel
    return solid[1::3, 1::3]


def sprite_classes(name, team="Y"):
    """Colour classes of the original body sprite (-1 outside its silhouette)."""
    path = os.path.join(REF_DIR, name, f"colony_body_{team}.png")
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    rgb = np.flipud(px.reshape(h, w, 4))[: 3 * FRAME, : 3 * FRAME, :3][1::3, 1::3]
    # float pixels of a byte PNG come in the image's own colour space (sRGB): no conversion needed
    cls = colour_classes(rgb).astype(np.int8)
    cls[~sprite_mask(name, team)] = -1
    return cls


def sprite_uv(x, y, z, el=SPRITE_ELEVATION):
    """Sprite-screen position (cells, v down) of world points (arrays)."""
    se, ce = math.sin(math.radians(el)), math.cos(math.radians(el))
    return x, -(se * y + ce * z)


def fit_matrix(theta, s, tx, ty, sy=1.0, sz=1.0):
    """The fit transform: rotation `theta` about Z, scale `s` (times `sy` along the game's
    north-south axis and `sz` vertically), ground offset (tx, ty)."""
    return (Matrix.Translation((tx, ty, 0.0)) @ Matrix.Diagonal((s, s * sy, s * sz, 1.0))
            @ Matrix.Rotation(theta, 4, "Z"))


def _transform(verts, theta, s, tx, ty, sy=1.0, sz=1.0):
    c, sn = math.cos(theta), math.sin(theta)
    x = s * (c * verts[:, 0] - sn * verts[:, 1]) + tx
    y = s * sy * (sn * verts[:, 0] + c * verts[:, 1]) + ty
    z = s * sz * verts[:, 2]
    return x, y, z


def _pixels(x, y, z, res):
    u, v = sprite_uv(x, y, z)
    k = res / FRAME * PX_PER_CELL
    col = np.floor(u * k + res / 2).astype(np.int64)
    row = np.floor(v * k + res / 2).astype(np.int64)
    ok = (col >= 0) & (col < res) & (row >= 0) & (row < res)
    return row * res + col, ok


def silhouette(verts, theta, s, tx, ty, sy=1.0, sz=1.0, res=FRAME):
    """Occupancy of the sprite frame by the vertices of a dense mesh under the fit transform."""
    idx, ok = _pixels(*_transform(verts, theta, s, tx, ty, sy, sz), res)
    grid = np.zeros(res * res, bool)
    grid[idx[ok]] = True
    return grid.reshape(res, res)


def class_map(verts, classes, theta, s, tx, ty, sy=1.0, sz=1.0, res=FRAME):
    """Colour class seen at each pixel (-1 = empty): the vertex nearest the sprite camera wins."""
    x, y, z = _transform(verts, theta, s, tx, ty, sy, sz)
    idx, ok = _pixels(x, y, z, res)
    se, ce = math.sin(math.radians(SPRITE_ELEVATION)), math.cos(math.radians(SPRITE_ELEVATION))
    depth = -ce * y + se * z  # along the direction to the camera
    order = np.argsort(depth[ok], kind="stable")
    grid = np.full(res * res, -1, np.int8)
    grid[idx[ok][order]] = classes[ok][order]  # later (nearer) points overwrite
    return grid.reshape(res, res)


def colour_classes(rgb, source="sprite", rule=None):
    """0 = other (chrome, earth, shadow), 1 = bright team colour, 2 = muted tower colour - from sRGB
    colours in 0..1 (array (..., 3)).  The original sprites' yellow team colour is an olive yellow;
    Tripo paints it a saturated yellow (hue 44-50) and fills what the picture did not show (under-
    sides, insides) with a khaki brown (hue ~36, value ~0.35) that must not count as team colour.
    `rule` = (hue min, hue max, saturation min, value min) of the team colour for one Tripo model
    (the wasp's is a darker olive)."""
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.degrees(np.arctan2(math.sqrt(3) * (g - b), 2 * r - g - b)) % 360.0
    cls = np.zeros(rgb.shape[:-1], np.int8)
    if source == "sprite":
        warm = (hue > 18.0) & (hue < 80.0)
        cls[warm & (sat >= 0.42) & (mx > 0.22)] = 1
        cls[warm & (sat > 0.14) & (sat < 0.42) & (mx > 0.45)] = 2
    else:
        h0, h1, s0, v0 = rule or (43.0, 70.0, 0.55, 0.45)
        cls[(hue >= 37.0) & (hue < 43.0) & (sat >= 0.3) & (mx >= 0.5)] = 2
        cls[(hue >= h0) & (hue < h1) & (sat >= s0) & (mx >= v0)] = 1
    return cls


def iou(a, b):
    return float((a & b).sum()) / max(1.0, float((a | b).sum()))


def fit_to_sprite(verts, mask, log=print):
    """Rotation, scale and offset that best lay the model's silhouette over the sprite's: every 2
    degrees with scale and offset from the silhouette bounds, then a pattern search on the best."""
    rows, cols = np.nonzero(mask)
    m_u0, m_u1 = (cols.min() - FRAME / 2) / PX_PER_CELL, (cols.max() + 1 - FRAME / 2) / PX_PER_CELL
    m_v0, m_v1 = (rows.min() - FRAME / 2) / PX_PER_CELL, (rows.max() + 1 - FRAME / 2) / PX_PER_CELL
    se = math.sin(math.radians(SPRITE_ELEVATION))
    sub = verts[:: max(1, len(verts) // 250000)]

    def bounds_guess(theta):
        c, sn = math.cos(theta), math.sin(theta)
        x = c * sub[:, 0] - sn * sub[:, 1]
        y = sn * sub[:, 0] + c * sub[:, 1]
        u, v = sprite_uv(x, y, sub[:, 2])
        s = (m_u1 - m_u0) / (u.max() - u.min())
        tx = (m_u0 + m_u1) / 2 - s * (u.max() + u.min()) / 2
        # v = s v_model - se ty  ->  ty from the vertical centres
        ty = (s * (v.max() + v.min()) / 2 - (m_v0 + m_v1) / 2) / se
        return s, tx, ty

    coarse = []
    for deg in range(0, 360, 2):
        th = math.radians(deg)
        s, tx, ty = bounds_guess(th)
        coarse.append((iou(silhouette(sub, th, s, tx, ty), mask), th, s, tx, ty))
    coarse.sort(key=lambda r: -r[0])
    log("fit: best coarse", [(round(r[0], 3), round(math.degrees(r[1]), 1)) for r in coarse[:6]])
    best = None
    for start in coarse[:4]:
        p = list(start[1:])
        score = start[0]
        steps = [math.radians(2.0), 0.03 * p[1], 0.1, 0.1]
        for _ in range(60):
            improved = False
            for i in range(4):
                for sign in (1, -1):
                    q = list(p)
                    q[i] += sign * steps[i]
                    sc = iou(silhouette(sub, *q), mask)
                    if sc > score:
                        p, score, improved = q, sc, True
            if not improved:
                steps = [st * 0.5 for st in steps]
                if steps[2] < 0.005:
                    break
        if best is None or score > best[0]:
            best = (score, *p)
    score, th, s, tx, ty = best
    log(f"fit: IoU {score:.3f} rotation {math.degrees(th):.2f} deg scale {s:.4f} offset ({tx:.3f}, {ty:.3f})")
    return th, s, tx, ty, score


def fit_features(verts, classes, sprite_cls, start, log=print, bounds=((0.75, 1.1), (0.9, 1.6)), fix_sy=False):
    """Second stage: the sprite's inner layout (where the team colour, the muted towers and the
    rest show) besides its outline.  Adds a north-south scale `sy` and a vertical scale `sz` - one
    oblique picture leaves depth open, and the generator need not have assumed the sprite camera's
    60 degrees - and searches all six parameters."""
    sub = slice(None, None, max(1, len(verts) // 250000))
    v, c = verts[sub], classes[sub]
    sil = sprite_cls >= 0
    # one picture cannot tell "further south" from "taller": the colony also has to stand centred
    # on its 6x6 footprint and inside it

    def score(p):
        cm = class_map(v, c, *p)
        got = cm >= 0
        parts = [iou(got, sil)]
        for k in (1, 2):
            parts.append(iou(cm == k, sprite_cls == k))
        x, y, _ = _transform(v, *p)
        off = math.hypot((x.min() + x.max()) / 2, (y.min() + y.max()) / 2)
        over = max(0.0, max(np.abs(x).max(), np.abs(y).max()) - 3.0)
        parts += [off, over]
        return 0.5 * parts[0] + 0.5 * parts[1] - 0.15 * off - 1.0 * over, parts

    th, s, tx, ty = start[:4]
    p = [th, s, tx, ty, 1.0, 1.0]
    best, parts = score(p)
    log("fit: features at start", round(best, 4), [round(x, 3) for x in parts])
    steps = [math.radians(2.0), 0.03 * s, 0.1, 0.1, 0.05, 0.08]
    for _ in range(200):
        improved = False
        for i in range(6):
            if fix_sy and i == 4:
                continue
            for sign in (1, -1):
                q = list(p)
                q[i] += sign * steps[i]
                if not (bounds[0][0] <= q[4] <= bounds[0][1] and bounds[1][0] <= q[5] <= bounds[1][1]):
                    continue
                sc, pt = score(q)
                if sc > best:
                    p, best, parts, improved = q, sc, pt, True
        if not improved:
            steps = [st * 0.5 for st in steps]
            if steps[2] < 0.004:
                break
    log(f"fit: features {best:.4f} (outline, team, towers IoU, base offset, overflow {[round(x, 3) for x in parts]}) rotation "
        f"{math.degrees(p[0]):.2f} scale {p[1]:.4f} offset ({p[2]:.3f}, {p[3]:.3f}) sy {p[4]:.3f} sz {p[5]:.3f}")
    return p, best


# ---------------------------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------------------------
def import_tripo(path):
    """Import a Tripo OBJ as one mesh object with its transform applied (Z up)."""
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    ob = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
    salib.select_only([ob])
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.name = ob.data.name = "TripoSource"
    level_base(ob, log=lambda *a: salib.log(*a))
    return ob


def level_base(ob, log=print):
    """Stand the model upright: Tripo leaves the flat base of a model made from an oblique picture
    tilted by several degrees (one rim on the ground, the opposite rim lifted).  Find the tilt about
    X and Y that brings the most of the model into a thin slab at its lowest level - the base lying
    flat - then rotate the mesh by it and put the base on z = 0."""
    v = mesh_verts(ob)
    sub = v[:: max(1, len(v) // 200000)]
    h = float(v[:, 2].max() - v[:, 2].min())
    slab = 0.006 * h

    def flat_count(ax, ay):
        ca, sa, cb, sb = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay)
        # z of Ry(ay) @ Rx(ax) @ v
        y1 = ca * sub[:, 1] - sa * sub[:, 2]
        z1 = sa * sub[:, 1] + ca * sub[:, 2]
        z = -sb * sub[:, 0] + cb * z1
        del y1
        return int((z < z.min() + slab).sum())

    best = (flat_count(0.0, 0.0), 0.0, 0.0)
    log(f"level: untilted base slab {best[0]} vertices")
    for step, span in ((math.radians(1.0), math.radians(16.0)), (math.radians(0.2), math.radians(1.2)),
                       (math.radians(0.05), math.radians(0.25))):
        cx, cy = best[1], best[2]
        n = int(round(span / step))
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                c = flat_count(cx + i * step, cy + j * step)
                if c > best[0]:
                    best = (c, cx + i * step, cy + j * step)
    _, ax, ay = best
    m = Matrix.Rotation(ay, 4, "Y") @ Matrix.Rotation(ax, 4, "X")
    ob.data.transform(m)
    ob.data.update()
    zmin = mesh_verts(ob)[:, 2].min()
    ob.data.transform(Matrix.Translation((0.0, 0.0, -zmin)))
    ob.data.update()
    log(f"level: tilt X {math.degrees(ax):+.2f} deg, Y {math.degrees(ay):+.2f} deg -> base slab {best[0]} vertices")
    return ax, ay


def mesh_verts(ob):
    co = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def apply_fit(ob, p):
    ob.data.transform(fit_matrix(*p))
    ob.data.update()


def base_color_image(ob):
    for m in ob.data.materials:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and any(lk.to_socket.name == "Base Color" for lk in n.outputs["Color"].links):
                return n.image
    raise RuntimeError("no base colour texture on the Tripo material")


def vertex_colours(ob):
    """sRGB colour (0..1) of the base colour texture at each vertex (one of its UVs)."""
    img = base_color_image(ob)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    me = ob.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), np.int32)  # foreach_get needs the property's own C type
    me.loops.foreach_get("vertex_index", lv)
    vuv = np.zeros((len(me.vertices), 2), np.float32)
    vuv[lv] = uv
    cx = np.clip((vuv[:, 0] * w).astype(np.int64), 0, w - 1)
    cy = np.clip((vuv[:, 1] * h).astype(np.int64), 0, h - 1)
    return px[cy, cx, :3]


# ---------------------------------------------------------------------------------------------
# check renders
# ---------------------------------------------------------------------------------------------
def workbench_sprite_view(path, size=432):
    """Fast textured render from the sprite camera (orthographic, 6 cells wide, from the south at
    SPRITE_ELEVATION) on the sheets' background colour."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "TEXTURE"
    sc.view_settings.view_transform = "Standard"
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    sc.world.color = tuple(salib.srgb_to_linear(tuple(c / 255 for c in SHEET_BG)))
    cd = bpy.data.cameras.new("FitCam")
    cd.type = "ORTHO"
    cd.ortho_scale = FRAME / PX_PER_CELL
    cam = bpy.data.objects.new("FitCam", cd)
    salib.link(cam)
    el = math.radians(SPRITE_ELEVATION)
    cam.location = (0.0, -math.cos(el) * 40.0, math.sin(el) * 40.0)
    cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    old = sc.camera
    sc.camera = cam
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    sc.camera = old
    bpy.data.objects.remove(cam, do_unlink=True)
    return path


CLASS_COLOURS = {-1: (0.0, 0.0, 0.0), 0: (0.45, 0.45, 0.47), 1: (0.95, 0.85, 0.2), 2: (0.75, 0.55, 0.4)}


def _class_panel(cls, size):
    big = np.repeat(np.repeat(cls, size // cls.shape[0], axis=0), size // cls.shape[1], axis=1)
    out = np.zeros((size, size, 4), np.float32)
    out[..., 3] = 1.0
    for k, c in CLASS_COLOURS.items():
        out[big == k, :3] = c
    return np.flipud(out)


def fit_report(name, verts_fitted, mask, render_png, out_png, classes=None, sprite_cls=None):
    """Sheet: original sprite | fitted model, same view | silhouettes (white both, red sprite
    only, blue model only) | colour classes of the sprite | of the model (grey other, yellow team,
    tan towers).  Written with bpy images (no PIL inside Blender)."""
    size = 3 * FRAME
    ref = bpy.data.images.load(os.path.join(REF_DIR, name, "colony_body_Y.png"), check_existing=False)
    rw, rh = ref.size
    rp = np.empty(rw * rh * 4, np.float32)
    ref.pixels.foreach_get(rp)
    rp = rp.reshape(rh, rw, 4)[rh - size:, :size]  # bottom rows of the flipped buffer = top of the sheet
    ren = bpy.data.images.load(render_png, check_existing=False)
    qp = np.empty(size * size * 4, np.float32)
    ren.pixels.foreach_get(qp)
    qp = qp.reshape(size, size, 4)
    sil = silhouette(verts_fitted, 0.0, 1.0, 0.0, 0.0, res=size)
    msk = np.repeat(np.repeat(mask, 3, axis=0), 3, axis=1)
    ov = np.zeros((size, size, 4), np.float32)
    ov[..., 3] = 1.0
    ov[sil & msk] = (0.9, 0.9, 0.9, 1)
    ov[msk & ~sil] = (0.9, 0.15, 0.15, 1)
    ov[sil & ~msk] = (0.2, 0.4, 1.0, 1)
    ov = np.flipud(ov)
    panels = [rp, qp, ov]
    if classes is not None and sprite_cls is not None:
        panels += [_class_panel(sprite_cls, size), _class_panel(class_map(verts_fitted, classes, 0.0, 1.0, 0.0, 0.0), size)]
    sheet = np.concatenate(panels, axis=1)
    out = bpy.data.images.new("FitSheet", size * len(panels), size, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = out_png
    out.file_format = "PNG"
    out.save()
    for im in (ref, ren, out):
        bpy.data.images.remove(im)
    salib.log("fit report", out_png)


def run_fit(name, src):
    salib.reset_scene(name)
    hp = import_tripo(src)
    verts = mesh_verts(hp)
    salib.log(name, "source", len(verts), "vertices", len(hp.data.polygons), "faces")
    mask = sprite_mask(name)
    logf = lambda *a: salib.log(*a)  # noqa: E731
    first = fit_to_sprite(verts, mask, log=logf)
    classes = colour_classes(vertex_colours(hp), source="tripo", rule=TRIPO.get(name, {}).get("team_rule"))
    salib.log(name, "source colour classes", np.bincount(classes, minlength=3).tolist())
    sprite_cls = sprite_classes(name)
    p, score = fit_features(verts, classes, sprite_cls, first, log=logf)
    p1, score1 = fit_features(verts, classes, sprite_cls, first, log=logf, fix_sy=True)
    if score1 >= score - 0.01:  # keep the footprint's proportions unless squeezing it clearly helps
        p, score = p1, score1
    apply_fit(hp, p)
    if QA_DIR:
        os.makedirs(QA_DIR, exist_ok=True)
        png = workbench_sprite_view(os.path.join(QA_DIR, f"{name}_tripo_fit_view.png"))
        fit_report(name, mesh_verts(hp), mask, png, os.path.join(QA_DIR, f"{name}_tripo_fit.png"), classes, sprite_cls)
    lo = mesh_verts(hp).min(axis=0)
    hi = mesh_verts(hp).max(axis=0)
    salib.log(name, "fitted bounds", tuple(np.round(lo, 3)), tuple(np.round(hi, 3)))
    return hp, p



# ---------------------------------------------------------------------------------------------
# per-colony settings
# ---------------------------------------------------------------------------------------------
# mounts: the original's turret Mount Points (Game.ANI "Mount Point 1/2", sprite-screen cells, v
# down) in Turret_1.. order (colonies.ron); mount_turrets() puts each turret where the sprite
# camera's ray through it meets the model.  gun_z: barrel axis above the pivot (the turret
# builder's own value).
# fit: the six fit parameters (rotation rad, scale, tx, ty, sy, sz) once chosen - the build then
# skips the search; None = search.
TRIPO = {
    "colony_spider": dict(module="colony_spider", turret_fn="spider_turret", materials_fn="spider_materials",
                          mounts=[(-0.83, -2.00), (0.92, -0.50)], gun_z=0.13, shell="M_SpiderShell",
                          # outline IoU 0.922, team 0.707, towers 0.514, footprint centre 0.21 off
                          # (2026-10-14, Tripo "spider hut"; base already level)
                          fit=(0.78103, 5.67367, -0.06217, -0.07896, 0.92812, 1.17)),
    "colony_beetle": dict(module="colony_beetle", turret_fn="beetle_turret", materials_fn="beetle_materials",
                          mounts=[(0.0, -0.88)], gun_z=0.42, shell="M_BeetleShell", climb=True,
                          # outline 0.872, team 0.76, footprint centre 0.30 off (Tripo "beetle hut", base
                          # levelled by 12 degrees)
                          fit=(0.80285, 5.68139, -0.22424, -0.45126, 1.0, 0.9)),
    "colony_ant": dict(module="colony_ant", turret_fn="ant_turret", materials_fn="ant_materials",
                       mounts=[(0.50, -2.42), (-0.12, -0.12)], gun_z=0.6, shell="M_AntShell",
                       # outline 0.969, team 0.689, footprint centre 0.13 off (Tripo "Ant hut", levelled 11 deg)
                       fit=(0.80067, 4.58605, -0.29902, 0.02651, 1.05625, 1.01)),
    "colony_scorpion": dict(module="colony_scorpion", turret_fn="scorpion_turret", materials_fn="scorp_materials",
                            mounts=[(0.42, -2.17)], gun_z=0.45, shell="M_ScorpionShell", plateau=True,
                            # outline 0.866, team 0.699, footprint centre 0.31 off (Tripo "scorpion hut 2" -
                            # it beat the first generation's 0.846 / 0.672 / 0.49; base levelled 16 degrees)
                            fit=(0.67195, 5.56848, 0.00362, -0.31757, 1.0, 0.9)),
    "colony_wasp": dict(module="colony_wasp", turret_fn="wasp_turret", materials_fn="wasp_materials",
                        mounts=[(-0.92, -1.33)], gun_z=0.5, shell="M_WaspShell",
                        # outline 0.961, team 0.771 (Tripo "wasp hut", base level; its yellow is a darker
                        # olive than the others', hence the wider team rule)
                        fit=(5.86431, 4.92284, 0.09558, -0.54293, 1.0, 1.0), team_rule=(43.0, 62.0, 0.45, 0.24)),
}
BODY_TRIS = 34000  # body share of TRI_BUDGET (the procedural turrets take the rest)
TEXTURE_SIZE = 2048
TEAM_Y = (0.961, 0.827, 0.471)  # sa_sim::team_rgb("Y") - the colour factor the game multiplies in


def srgb_to_lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def luminance(lin):
    lin = np.asarray(lin, np.float32)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def pale_lin(team_lin):
    """The muted tower colour of a team colour - the mirror of sa_game's colony_pale_color() (linear):
    a fifth of the way to its own grey and a quarter darker (the original's spider towers: dark red
    for red, beige for yellow)."""
    t = np.asarray(team_lin, np.float32)
    return (t * 0.8 + luminance(t)[..., None] * 0.2) * 0.75


# ---------------------------------------------------------------------------------------------
# flat tops (tower tops) of the fitted model
# ---------------------------------------------------------------------------------------------
def flat_tops(ob, cell=0.04, min_z_frac=0.45, nz=0.95):
    """Clusters of upward-facing faces (normal z > `nz`) high on the model: [(area, (x, y, z), r_equiv)]."""
    me = ob.data
    nf = len(me.polygons)
    nrm = np.empty(nf * 3, np.float32)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    cen = np.empty(nf * 3, np.float32)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    area = np.empty(nf, np.float32)
    me.polygons.foreach_get("area", area)
    sel = np.nonzero((nrm[:, 2] > nz) & (cen[:, 2] > min_z_frac * cen[:, 2].max()))[0]
    keys = np.floor(cen[sel, :2] / cell).astype(np.int64)
    cells = {}
    for i, k in zip(sel, map(tuple, keys)):
        cells.setdefault(k, []).append(i)
    seen, out = set(), []
    for k in cells:
        if k in seen:
            continue
        stack, members = [k], []
        seen.add(k)
        while stack:
            c = stack.pop()
            members += cells[c]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nb = (c[0] + dx, c[1] + dy)
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        m = np.array(members)
        a = float(area[m].sum())
        c = (cen[m] * area[m, None]).sum(0) / a
        out.append((a, tuple(float(x) for x in c), math.sqrt(a / math.pi)))
    out.sort(key=lambda r: -r[0])
    return out


MOUNT_LIFT = 0.21  # sprite rows (cells) between a turret's pivot and the Mount Point its sprite hangs on


def plateau_centre(verts, x0, y0, z0, cell=0.08, tol=0.2, reach=1.0):
    """Centre of the plateau around (x0, y0) at height z0: the cells of a height map (highest vertex
    per `cell`) reachable from it through neighbours within `tol` of z0, no further than `reach`."""
    near = verts[np.hypot(verts[:, 0] - x0, verts[:, 1] - y0) < reach + cell]
    keys = np.floor((near[:, :2] - (x0, y0)) / cell).astype(np.int64)
    hmax = {}
    for k, z in zip(map(tuple, keys), near[:, 2]):
        if z > hmax.get(k, -1e9):
            hmax[k] = z
    start = (int(math.floor(0.0)), int(math.floor(0.0)))
    seen, stack = {start}, [start]
    while stack:
        c = stack.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nb = (c[0] + dx, c[1] + dy)
                if nb in seen or nb not in hmax or abs(hmax[nb] - z0) > tol:
                    continue
                if math.hypot((nb[0] + 0.5) * cell, (nb[1] + 0.5) * cell) > reach:
                    continue
                seen.add(nb)
                stack.append(nb)
    cells = [c for c in seen if c in hmax]
    cx = x0 + cell * (np.mean([c[0] for c in cells]) + 0.5)
    cy = y0 + cell * (np.mean([c[1] for c in cells]) + 0.5)
    zs = np.array([hmax[c] for c in cells])
    return float(cx), float(cy), float(np.percentile(zs, 90)), len(cells) * cell * cell


def mount_turrets(ob, mounts, climb=False, top_nz=0.95, snap=0.6, plateau=False, log=print):
    """Turret pivots from the original's Mount Points (Game.ANI, sprite-screen cells, v down; the
    turret sprite hangs MOUNT_LIFT above its pivot - calibrated on the spider's two flat tower
    tops): the sprite camera's view ray through each point hits the fitted model on the tower top /
    dome / cell the turret stands on.  A flat top close by (a tower; the ray may graze a leg in front
    of it) takes the pivot to its centre; otherwise the pivot goes to the highest ground within
    0.4 cells of the hit (the crown of a cell or cap, not its front slope).  `climb` (a dome: the
    beetle) skips the flat tops and walks uphill from the hit to the dome's crown; `top_nz` / `snap`
    loosen the flat-top test; `plateau` (the scorpion's bumpy honeycomb top) takes the centre of the
    level ground around the hit."""
    from mathutils.bvhtree import BVHTree

    bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
    el = math.radians(SPRITE_ELEVATION)
    d = Vector((0.0, math.cos(el), -math.sin(el)))
    tops = [t for t in flat_tops(ob, nz=top_nz) if 0.15 <= t[2] <= 0.8]
    verts = mesh_verts(ob)
    pivots, radii = [], []
    for u, v in mounts:
        vp = v + MOUNT_LIFT
        ground = Vector((u, -vp / math.sin(el), 0.0))
        hit, _, _, _ = bvh.ray_cast(ground - d * 60.0, d)
        assert hit is not None, f"mount point {(u, v)} misses the model"
        near = [] if (climb or plateau) else [t for t in tops if math.hypot(t[1][0] - hit.x, t[1][1] - hit.y) < snap
                                              and -0.6 < t[1][2] - hit.z < 0.3]
        if plateau:
            px, py, pz, area = plateau_centre(verts, hit.x, hit.y, hit.z)
            pv, r = (px, py, pz), math.sqrt(area / math.pi)
            how = f"plateau of {area:.2f} cells^2"
        elif near:
            t = min(near, key=lambda t: math.hypot(t[1][0] - hit.x, t[1][1] - hit.y))
            pv, r = t[1], t[2]
            how = f"flat top r {r:.2f}"
        else:
            cx, cy = hit.x, hit.y
            for _ in range(12 if climb else 1):
                reg = verts[np.hypot(verts[:, 0] - cx, verts[:, 1] - cy) < 0.4]
                ztop = float(np.percentile(reg[:, 2], 98))
                crown = reg[reg[:, 2] >= ztop - 0.05]
                nx, ny = float(crown[:, 0].mean()), float(crown[:, 1].mean())
                moved = math.hypot(nx - cx, ny - cy)
                cx, cy = nx, ny
                if moved < 0.02:
                    break
            pv, r = (cx, cy, ztop), 0.4
            how = "dome crown" if climb else "crown"
        log(f"mount ({u:+.2f}, {v:+.2f}): ray hit ({hit.x:+.3f}, {hit.y:+.3f}, {hit.z:.3f}) -> pivot "
            f"({pv[0]:+.3f}, {pv[1]:+.3f}, {pv[2]:.3f}) on {how}")
        pivots.append(tuple(pv))
        radii.append(r)
    return pivots, radii


# ---------------------------------------------------------------------------------------------
# low poly + bake
# ---------------------------------------------------------------------------------------------
def decimated_copy(hp, target_tris, name="ColonyBody"):
    lp = hp.copy()
    lp.data = hp.data.copy()
    lp.name = lp.data.name = name
    salib.link(lp)
    salib.select_only([lp])
    mod = lp.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = target_tris / max(1, len(hp.data.polygons))
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    for f in lp.data.polygons:
        f.use_smooth = True
    salib.log("decimated", len(hp.data.polygons), "->", len(lp.data.polygons), "faces")
    return lp


def unwrap(lp, margin=0.003):
    salib.select_only([lp])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def _feeding_image(nt, socket):
    """The image texture node behind a shader input (through any converter nodes)."""
    stack = [lk.from_node for lk in socket.links]
    while stack:
        n = stack.pop()
        if n.type == "TEX_IMAGE":
            return n
        for inp in n.inputs:
            stack += [lk.from_node for lk in inp.links]
    return None


def bake_from_source(hp, lp, size=TEXTURE_SIZE):
    """Bake the Tripo material of `hp` onto `lp`'s UVs: colour, roughness, metallic (emission
    passes - exact texture values, no lighting) and the tangent-space normal (hp geometry + its
    normal map).  Returns {pass: float array (size, size, 4), rows from the bottom}."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    salib.use_cycles_device(sc)
    sc.cycles.samples = 4
    sc.cycles.use_denoising = False
    bk = sc.render.bake
    bk.use_selected_to_active = True
    bk.use_cage = False
    bk.cage_extrusion = 0.05
    bk.max_ray_distance = 0.2
    bk.margin = 16
    bk.use_clear = True

    mat = hp.data.materials[0]
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    src = {k: _feeding_image(nt, p.inputs[k]) for k in ("Base Color", "Roughness", "Metallic", "Normal")}
    # the OBJ importer loads Tripo's data maps as sRGB colour: roughness 0.35 would read as 0.1
    for k in ("Roughness", "Metallic", "Normal"):
        if src[k] is not None:
            src[k].image.colorspace_settings.name = "Non-Color"
    salib.log("tripo maps", {k: (v.image.name, v.image.colorspace_settings.name) if v else None for k, v in src.items()})
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0

    target = bpy.data.materials.new("BakeTarget")
    target.use_nodes = True
    tnode = target.node_tree.nodes.new("ShaderNodeTexImage")
    target.node_tree.nodes.active = tnode
    lp.data.materials.clear()
    lp.data.materials.append(target)

    hp.hide_render = False
    salib.select_only([lp, hp])
    bpy.context.view_layer.objects.active = lp
    results = {}
    for pname, socket_key in (("color", "Base Color"), ("rough", "Roughness"), ("metal", "Metallic"), ("normal", None)):
        img = bpy.data.images.new(f"bake_{pname}", size, size, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Linear Rec.709" if pname == "color" else "Non-Color"
        tnode.image = img
        if socket_key is None:
            nt.links.new(p.outputs[0], out.inputs["Surface"])
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
        else:
            node = src[socket_key]
            if node is None:  # a constant: bake the input's value
                v = p.inputs[socket_key].default_value
                emit.inputs["Color"].default_value = tuple(v) if hasattr(v, "__len__") else (v, v, v, 1.0)
                for lk in list(emit.inputs["Color"].links):
                    nt.links.remove(lk)
            else:
                nt.links.new(node.outputs["Color"], emit.inputs["Color"])
            nt.links.new(emit.outputs[0], out.inputs["Surface"])
            bpy.ops.object.bake(type="EMIT")
        px = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(px)
        results[pname] = px.reshape(size, size, 4)
        bpy.data.images.remove(img)
        salib.log("baked", pname)
    nt.links.new(p.outputs[0], out.inputs["Surface"])
    nt.nodes.remove(emit)
    lp.data.materials.clear()
    bpy.data.materials.remove(target)
    return results


# ---------------------------------------------------------------------------------------------
# team split
# ---------------------------------------------------------------------------------------------
def face_uv_samples(lp):
    """Per triangle of `lp`: its three corner UVs (n, 3, 2)."""
    me = lp.data
    me.calc_loop_triangles()
    tri_loops = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tri_loops)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    poly = np.empty(len(me.loop_triangles), np.int32)
    me.loop_triangles.foreach_get("polygon_index", poly)
    return uv[tri_loops].reshape(-1, 3, 2), poly


def classify_faces(lp, color_lin, pivots, radii, rule=None, log=print):
    """Class of every face of `lp` (0 shell, 1 team, 2 muted tower) from the baked colour (several
    samples inside the face) - and every face of a tower column (under a turret's flat top, within
    its radius) that is not team colour counts as tower."""
    size = color_lin.shape[0]
    tri_uv, poly = face_uv_samples(lp)
    bary = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]], np.float32)
    pts = np.einsum("sk,tkd->tsd", bary, tri_uv)  # (tris, samples, 2)
    cx = np.clip((pts[..., 0] * size).astype(np.int64), 0, size - 1)
    cy = np.clip((pts[..., 1] * size).astype(np.int64), 0, size - 1)
    rgb = lin_to_srgb(color_lin[cy, cx, :3]).mean(axis=1)  # (tris, 3) sRGB
    tri_cls = colour_classes(rgb, source="tripo", rule=rule)
    me = lp.data
    npoly = len(me.polygons)
    votes = np.zeros((npoly, 3), np.int64)
    np.add.at(votes, (poly, tri_cls), 1)
    cls = votes.argmax(axis=1).astype(np.int8)
    cen = np.empty(npoly * 3, np.float32)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    for (x, y, z), r in zip(pivots, radii):
        inside = (np.hypot(cen[:, 0] - x, cen[:, 1] - y) <= 1.15 * r) & (cen[:, 2] <= z + 0.05)
        cls[inside & (cls != 1)] = 2
    log("face classes (shell, team, tower):", np.bincount(cls, minlength=3).tolist())
    return cls


def rasterize_classes(lp, cls, size):
    """Texel -> class of the face covering it (-1 = gutter), then grown into the gutters so the
    bake's edge padding gets its face's treatment."""
    tri_uv, poly = face_uv_samples(lp)
    lab = np.full((size, size), -1, np.int8)
    tri_cls = cls[poly]
    P = tri_uv * size - 0.5  # texel centres at integer + 0.5
    for t in range(len(P)):
        a, b, c = P[t]
        x0, x1 = int(max(0, math.floor(min(a[0], b[0], c[0])))), int(min(size - 1, math.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, math.floor(min(a[1], b[1], c[1])))), int(min(size - 1, math.ceil(max(a[1], b[1], c[1]))))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.float32), np.arange(y0, y1 + 1, dtype=np.float32))
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        w0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        w2 = 1.0 - w0 - w1
        e = -0.02
        inside = (w0 >= e) & (w1 >= e) & (w2 >= e)
        lab[y0:y1 + 1, x0:x1 + 1][inside] = tri_cls[t]
    for _ in range(24):  # grow into the gutters
        empty = lab < 0
        if not empty.any():
            break
        grown = lab.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh = np.roll(lab, (dy, dx), axis=(0, 1))
            take = empty & (grown < 0) & (sh >= 0)
            grown[take] = sh[take]
        lab = grown
    lab[lab < 0] = 0
    return lab


def compose_colour(color_lin, labels, team_srgb=TEAM_Y):
    """Final base colour (sRGB 0..1, rows from the bottom): team texels -> grey = their brightness
    relative to the team colour (the game multiplies the team colour back in), muted tower texels ->
    grey relative to the muted team colour, shell texels keep the source colours."""
    team = srgb_to_lin(team_srgb)
    lum = luminance(color_lin[..., :3])
    out = lin_to_srgb(color_lin[..., :3])
    for k, ref in ((1, team), (2, pale_lin(team))):
        g = np.clip(lum / float(luminance(ref)), 0.0, 1.0)
        sel = labels == k
        out[sel] = lin_to_srgb(g[sel])[:, None]
    return out


def save_jpeg(rgb01, path, quality=90, subsampling=None):
    """Write an (h, w, 3) array (rows from the bottom, values as stored) as a JPEG (PIL, as
    salib.bake_object_textures does)."""
    from PIL import Image as PILImage

    arr = (np.flipud(np.clip(rgb01, 0.0, 1.0)) * 255.0 + 0.5).astype(np.uint8)
    kw = {} if subsampling is None else {"subsampling": subsampling}
    PILImage.fromarray(arr, "RGB").save(path, "JPEG", quality=quality, **kw)
    return path


def baked_material(name, images, tint_srgb=None):
    """Image-based material like salib.build_baked_materials makes (colour x tint factor, ORM,
    tangent normal map)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = images["color"]
    if tint_srgb is not None:
        tint = (*salib.srgb_to_linear(tint_srgb), 1.0)
        nt.links.new(salib._mix_rgb(nt, "MULTIPLY", tc.outputs["Color"], tint, 1.0), bsdf.inputs["Base Color"])
        mat.diffuse_color = tint
    else:
        nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
    to = nt.nodes.new("ShaderNodeTexImage")
    to.image = images["orm"]
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(to.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = images["normal"]
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.space = "TANGENT"
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    mat["sa_tint"] = tint_srgb is not None
    return mat


def texture_body(name, hp, lp, cfg, pivots, radii, log=print):
    """Bake, split and texture the low-poly body; returns the face classes."""
    unwrap(lp)
    maps = bake_from_source(hp, lp)
    cls = classify_faces(lp, maps["color"], pivots, radii, rule=cfg.get("team_rule"), log=log)
    labels = rasterize_classes(lp, cls, TEXTURE_SIZE)
    colour = compose_colour(maps["color"], labels)
    out_dir = os.path.join(salib.TEXTURE_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    tag = lp.name.lower()
    paths = {"color": os.path.join(out_dir, f"{tag}_color.jpg"), "orm": os.path.join(out_dir, f"{tag}_orm.jpg"),
             "normal": os.path.join(out_dir, f"{tag}_normal.jpg")}
    save_jpeg(colour, paths["color"], quality=90)
    orm = np.ones((TEXTURE_SIZE, TEXTURE_SIZE, 3), np.float32)
    orm[..., 1] = np.clip(maps["rough"][..., 0], 0.0, 1.0)
    orm[..., 2] = np.clip(maps["metal"][..., 0], 0.0, 1.0)
    save_jpeg(orm, paths["orm"], quality=88, subsampling=0)
    save_jpeg(np.clip(maps["normal"][..., :3], 0.0, 1.0), paths["normal"], quality=92, subsampling=0)
    log("textures", {k: os.path.getsize(v) for k, v in paths.items()})
    images = {}
    for k, pth in paths.items():
        im = bpy.data.images.load(pth, check_existing=False)
        im.colorspace_settings.name = "sRGB" if k == "color" else "Non-Color"
        im.pack()
        images[k] = im
    mats = [baked_material("M_Colony.body", images, TEAM_Y),
            baked_material("M_ColonyPale.body", images, tuple(float(x) for x in lin_to_srgb(pale_lin(srgb_to_lin(TEAM_Y))))),
            baked_material(cfg["shell"], images)]
    lp.data.materials.clear()
    for m in mats:
        lp.data.materials.append(m)
    mi = np.array([{0: 2, 1: 0, 2: 1}[int(c)] for c in cls], np.int32)  # class -> slot
    lp.data.polygons.foreach_set("material_index", mi)
    lp.data.update()
    return cls


# ---------------------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------------------
def build(name, src, fit_only=False, refit=False):
    import importlib

    from colony_ant import ca_unwrap
    from colony_common import (TRI_BUDGET, _attach, _clear_textures, colony_materials, idle_clip, sprite_view_render,
                               tri_count, turret_fire_clip)

    cfg = TRIPO[name]
    hp, p = run_fit(name, src) if (cfg["fit"] is None or refit) else (None, cfg["fit"])
    if hp is None:
        salib.reset_scene(name)
        hp = import_tripo(src)
        apply_fit(hp, p)
    salib.log(name, "fit parameters", [round(x, 5) for x in p])
    if fit_only:
        return None
    pivots, radii = mount_turrets(hp, cfg["mounts"], climb=cfg.get("climb", False), top_nz=cfg.get("top_nz", 0.95),
                                  snap=cfg.get("snap", 0.6), plateau=cfg.get("plateau", False), log=salib.log)
    _clear_textures(name)
    # the turrets first: their procedural materials take the plain names (M_Colony ...)
    mod = importlib.import_module(cfg["module"])
    mats = colony_materials("Y")
    mats.update(getattr(mod, cfg["materials_fn"])())
    turret_fn = getattr(mod, cfg["turret_fn"])
    turrets, barrels_all = [], []
    for i, pv in enumerate(pivots):
        t, bs = turret_fn(f"Turret_{i + 1}", mats, pv)
        turrets.append(t)
        barrels_all.append(bs)
    lp = decimated_copy(hp, BODY_TRIS)
    texture_body(name, hp, lp, cfg, pivots, radii, log=salib.log)
    bpy.data.objects.remove(hp, do_unlink=True)
    for t in turrets:
        _attach(t, lp)
    objs = [lp] + turrets + [b for bs in barrels_all for b in bs]
    tris = {o.name: tri_count(o) for o in objs}
    total = sum(tris.values())
    salib.log(name, "triangles", total, tris)
    assert total <= TRI_BUDGET, f"{name}: {total} triangles over budget {TRI_BUDGET}"
    for o in objs:
        if o.name.endswith("_Barrels"):  # they swing round with the turret: only the rest pose would be checked
            continue
        co = np.empty(len(o.data.vertices) * 3, np.float32)
        o.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ np.array(o.matrix_world.to_3x3()).T + np.array(o.matrix_world.translation)
        assert np.abs(co[:, :2]).max() <= 3.05, f"{name}: {o.name} leaves the 6x6 footprint ({np.abs(co[:, :2]).max():.3f})"
    # turret parts: the shared bake (packed UVs, 512 px)
    for o in turrets + [b for bs in barrels_all for b in bs]:
        ca_unwrap(o)
        images = salib.bake_object_textures(o, name, size=512)
        salib.build_baked_materials(o, name, images)
    idle_clip(lp)
    for t, bs in zip(turrets, barrels_all):
        turret_fire_clip(t, bs)
    path = salib.export_glb(name, objects=objs)
    s = salib.print_summary(path)
    for i in range(len(turrets)):
        assert f"Turret_{i + 1}" in s["node_names"], s["node_names"]
    assert any(m.split(".")[0] == "M_Colony" for m in s["materials"]), s["materials"]
    clips = sorted(a["name"] for a in s["animations"])
    assert clips == ["idle", "turret_fire"], clips
    previews = salib.render_previews(name, radius=9.5, center=(0, 0, 1.4), size=512, samples=64,
                                     views=("front", "back", "left", "right", "threequarter", "top"))
    salib.contact_sheet(name, previews)
    gun_z = cfg["gun_z"]
    ron = [f"(offset: ({x:.2f}, {-y:.2f}), height: {z + gun_z:.2f})" for (x, y, z) in pivots]
    salib.log(name, "colonies.ron turrets", ron)
    if QA_DIR:
        os.makedirs(QA_DIR, exist_ok=True)
        png = sprite_view_render(os.path.join(QA_DIR, f"{name}_tripo_spriteview.png"))
        compare_with_sprite(name, png, os.path.join(QA_DIR, f"{name}_tripo_compare.png"))
        with open(os.path.join(QA_DIR, f"{name}_tripo_build.txt"), "w") as f:
            f.write(f"{name}\nsource {src}\nfit {p}\ntriangles {total} {tris}\nnodes {s['node_names']}\n"
                    f"materials {s['materials']}\nclips {s['animations']}\nturrets {ron}\n")
    salib.save_blend(name)
    return path


def compare_with_sprite(name, render_png, out_png):
    """Original sprite | the built colony from the sprite camera (with turrets)."""
    size = 3 * FRAME
    ref = bpy.data.images.load(os.path.join(REF_DIR, name, "colony_body_Y.png"), check_existing=False)
    rw, rh = ref.size
    rp = np.empty(rw * rh * 4, np.float32)
    ref.pixels.foreach_get(rp)
    rp = rp.reshape(rh, rw, 4)[rh - size:, :size]
    ren = bpy.data.images.load(render_png, check_existing=False)
    w, h = ren.size
    qp = np.empty(w * h * 4, np.float32)
    ren.pixels.foreach_get(qp)
    qp = qp.reshape(h, w, 4)
    if (w, h) != (size, size):
        ys = (np.arange(size) * h // size)
        xs = (np.arange(size) * w // size)
        qp = qp[ys][:, xs]
    sheet = np.concatenate([rp, qp], axis=1)
    out = bpy.data.images.new("CompareSheet", size * 2, size, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = out_png
    out.file_format = "PNG"
    out.save()
    for im in (ref, ren, out):
        bpy.data.images.remove(im)
    salib.log("compare", out_png)


if __name__ == "__main__":
    args = salib.script_args()
    name = args[0]
    src = args[args.index("--src") + 1]
    build(name, src, fit_only="--fit-only" in args, refit="--refit" in args)
    print("BUILT" if "--fit-only" not in args else "FIT", name, flush=True)
