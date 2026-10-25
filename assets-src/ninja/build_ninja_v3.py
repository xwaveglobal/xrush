# Ninja player character v3 for xrush: the fal.ai (nano-banana-pro views -> Tripo v2.5 multiview) mesh,
# texture-fixed (fal_v3/basecolor_v3.webp), rigged + animated here, exported for the game.
#
#   blender -b --factory-startup -P assets-src/ninja/build_ninja_v3.py
#   blender -b --factory-startup -P assets-src/ninja/build_ninja_v3.py -- --blend out.blend --glb out.glb
#
# Inputs (assets-src/ninja/fal_v3/):  ninja_v2_textured.glb  textured ~30k tri mesh (glTF, faces +X)
#                                     basecolor_v6.webp      albedo (v6: near-black hood, baked AO + fold crease shading, faint
#                                                            weave; scripts/v6_tex.py from basecolor_v4; v5 kept; --basecolor)
#                                     normal_v6.webp         normal map: hood fold creases + fabric weave baked (--normal)
#                                     hood_folds.py          the hood fold field shared by this build and v6_tex.py
#                                     emit_v3.png            eye-white emission mask
# v4: hood_sculpt() (soft dome, no back ridge, tip falling back; --no-sculpt to skip), procedural cape
# keys (cape_keys: hangs down / trails back, side chains pulled in, travelling wave + flutter), extra
# local weight relaxation at the stretch hot spots (HOT).
# v5: hood rebuilt: small scan cracks around the hood closed (holes_fill), hood shell projected onto an
# analytic gumdrop (piecewise super-ellipsoid + soft tip leaning back, HOOD), Taubin-smoothed (extra on
# the brim, open borders pinned), a few real cloth folds pressed in. Topology/UVs kept; the hood stays
# head-rigid via the head weights computed after the sculpt.
# v6: clearer cloth folds: the hood shell's long edges are split once (14-25 mm scan triangles could not hold
# folds; tris given back by a light collapse of the lower front body, body stays ~30.5k), the shell is
# re-smoothed with 3x the passes, folds from fal_v3/hood_folds.py (long folds from the tip down the back and
# sides, pleats/sags where it bunches into the scarf) are low-passed on the mesh and pressed in, folded-over or
# pinched faces are relaxed, and the scan's custom normals are reset to smooth on the hood (--no-subdiv to skip).
# Reused from the previous build (git: build_ninja.py): bone names, the six pose sets, cape helper,
# in-place baking, the optional accessories (appended from --acc-blend, default: old NinjaCharacter.blend
# saved as fal_v3/accessories.blend).
#
# Units: metres, Blender axes (Z up, the character faces -Y, its left hand on +X), feet on z = 0,
# 1.0 m tall. glTF export is +Y up / faces +Z, which NinjaRig.ts turns 180 deg.
import bpy, bmesh, math, os, sys, json, struct
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fal_v3'))
import hood_folds
from mathutils import Vector, Matrix, Euler, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(HERE, 'fal_v3')
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def _arg(k, d):
    return argv[argv.index(k) + 1] if k in argv else d
OUT_BLEND = _arg('--blend', os.path.join(HERE, 'NinjaCharacter.blend'))
OUT_GLB = _arg('--glb', os.path.join(REPO, 'src', 'assets', 'models', 'ninja.glb'))
ACC_BLEND = _arg('--acc-blend', os.path.join(SRC, 'accessories.blend'))
FPS = 30
EMIT = float(_arg('--emit', '0.45'))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
coll = scene.collection

# ----------------------------------------------------------------------------------------------
# mesh: import, orient (+X -> -Y), feet on z = 0, weld UV-seam duplicates (UVs live on loops)
# ----------------------------------------------------------------------------------------------
bpy.ops.import_scene.gltf(filepath=os.path.join(SRC, 'ninja_v2_textured.glb'))
body = [o for o in scene.objects if o.type == 'MESH'][0]
for o in list(scene.objects):
    if o is not body:
        bpy.data.objects.remove(o)
body.parent = None
body.name = 'Ninja_Body'; body.data.name = 'Ninja_Body'
mw = Matrix.Rotation(math.radians(-90), 4, 'Z') @ body.matrix_world
body.data.transform(mw)
body.matrix_world = Matrix.Identity(4)
co = np.array([v.co[:] for v in body.data.vertices])
body.data.transform(Matrix.Translation((-0.5 * (co[:, 0].max() + co[:, 0].min()), 0, -co[:, 2].min())))
bm = bmesh.new(); bm.from_mesh(body.data)
n0 = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0004)
# v5: close the small cracks of the scan around the hood / brim / cowl (they open once the hood shell is
# reshaped): fill boundary loops of <= 8 edges above the shoulders, UVs taken from the vertices' own faces
uvl = bm.loops.layers.uv.active
bnd_e = [e for e in bm.edges if e.is_boundary]
loops_, seen_ = [], set()
for e0 in bnd_e:
    if e0 in seen_:
        continue
    comp, st = [], [e0]
    while st:
        e = st.pop()
        if e in seen_:
            continue
        seen_.add(e); comp.append(e)
        for v in e.verts:
            st += [f for f in v.link_edges if f.is_boundary and f not in seen_]
    loops_.append(comp)
small = [c for c in loops_ if len(c) <= 8 and sum(v.co.z for e in c for v in e.verts) / (2 * len(c)) > 0.58]
old_faces = set(bm.faces)
for c in small:
    bmesh.ops.holes_fill(bm, edges=c, sides=len(c))
new_faces = [f for f in bm.faces if f not in old_faces]
bmesh.ops.triangulate(bm, faces=new_faces)
for f in [f for f in bm.faces if f not in old_faces]:
    for lp in f.loops:
        src = [l for l in lp.vert.link_loops if l.face in old_faces]
        if src:
            lp[uvl].uv = src[0][uvl].uv
print('[ninja] closed %d small scan cracks around the hood (%d tris)' % (len(small), len([f for f in bm.faces if f not in old_faces])))
# v6: the hood shell of the scan has 14-25 mm triangles, too coarse to hold cloth folds: split its long edges
# once (UVs interpolated by bmesh), and give the tris back by a light collapse-decimate of the body below the
# shoulders (legs, torso under the cape), so the body stays ~30k tris
if '--no-subdiv' not in argv:
    _C = Vector((0.0, -0.01, 0.74))
    def _in_hood(v):
        d = v.co - _C
        if v.co.z < 0.60 or d.length < 0.12:
            return False
        dn = d.normalized()
        az = math.degrees(math.atan2(dn.x, -dn.y)); el = math.degrees(math.asin(max(-1, min(1, dn.z))))
        return math.hypot(az / 45, max(el, 0) / 34) > 0.95
    # collapse the scan's crumpled micro-triangles on the hood shell first (they fold over once smoothed)
    hv = set(v for v in bm.verts if _in_hood(v))
    ne0 = len(bm.edges)
    bmesh.ops.dissolve_degenerate(bm, dist=0.0032, edges=[e for e in bm.edges if e.verts[0] in hv and e.verts[1] in hv])
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    print('[ninja] hood micro-edges collapsed: edges %d -> %d' % (ne0, len(bm.edges)))
    for _pass, lim in enumerate((0.014,)):
        hv = set(v for v in bm.verts if _in_hood(v))
        ed = [e for e in bm.edges if e.verts[0] in hv and e.verts[1] in hv and e.calc_length() > lim]
        nf0 = len(bm.faces)
        bmesh.ops.subdivide_edges(bm, edges=ed, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
        print('[ninja] hood subdiv pass %d: %d edges split, faces %d -> %d' % (_pass, len(ed), nf0, len(bm.faces)))
bm.to_mesh(body.data); bm.free()
if '--no-subdiv' not in argv:
    _ntri = len(body.data.polygons)
    _vg = body.vertex_groups.new(name='_dec')
    _lo = [v.index for v in body.data.vertices if v.co.z < 0.52 and v.co.y < 0.02]   # front / legs / boots, never the cape sheet
    _vg.add(_lo, 1.0, 'REPLACE')
    _target = int(_arg('--tri-budget', '30500'))
    _ratio = _target / _ntri                       # the modifier ratio is for the whole mesh; the group limits where
    _md = body.modifiers.new('dec', 'DECIMATE'); _md.decimate_type = 'COLLAPSE'; _md.ratio = max(0.5, min(1.0, _ratio))
    _md.vertex_group = '_dec'; _md.vertex_group_factor = 1.0; _md.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = body; body.select_set(True)
    bpy.ops.object.modifier_apply(modifier='dec')
    body.vertex_groups.remove(body.vertex_groups['_dec'])
    print('[ninja] lower-front-body collapse (ratio %.3f): tris %d -> %d' % (max(0.5, min(1.0, _ratio)), _ntri, len(body.data.polygons)))
for p in body.data.polygons:
    p.use_smooth = True
print('[ninja] welded verts %d -> %d' % (n0, len(body.data.vertices)))

# ----------------------------------------------------------------------------------------------
# hood sculpt (v4): smooth the vertical ridge / lumps down the back, flatten the bulge, soft tip that
# falls back and down. Only vertices above the scarf (z > 0.62) on the back half move.
# ----------------------------------------------------------------------------------------------
def _ss(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)
HOOD = dict(c=(0.0, -0.01, 0.74), ax=0.19, ayb=0.158, ayf=0.23, azu=0.25, azd=0.17, p=2.1,
            tip=(32, 0.055, 0.42), droop=(55, 0.015, 0.30))
def _vnormals(Q, F):
    fn = np.cross(Q[F[:, 1]] - Q[F[:, 0]], Q[F[:, 2]] - Q[F[:, 0]])
    vn = np.zeros_like(Q)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
def hood_target(D, H=HOOD):
    """radius of the clean hood shell along unit directions D (from the hood centre): a piecewise
    super-ellipsoid dome + a soft tip leaning back (and a smaller droop behind it, so it falls back/down)"""
    p = H['p']
    ay = np.where(D[:, 1] > 0, H['ayb'], H['ayf']); az = np.where(D[:, 2] > 0, H['azu'], H['azd'])
    r = (np.abs(D[:, 0] / H['ax']) ** p + np.abs(D[:, 1] / ay) ** p + np.abs(D[:, 2] / az) ** p) ** (-1 / p)
    for ang, amp, sig in (H['tip'], H['droop']):
        t = np.array([0, math.sin(math.radians(ang)), math.cos(math.radians(ang))])
        th = np.arccos(np.clip(D @ t, -1, 1))
        r = r + amp * np.exp(-(th / sig) ** 2)
    return r
def hood_sculpt(me):
    """v5: replace the lumpy Tripo hood shell by a clean analytic dome (verts slide along rays from the
    hood centre), Taubin-smooth the brim / cowl join, then press in a few real cloth folds."""
    P = np.array([v.co[:] for v in me.vertices])
    E = np.array([e.vertices[:] for e in me.edges])
    F = np.array([q.vertices[:] for q in me.polygons])
    n = len(P)
    deg = np.bincount(E.ravel(), minlength=n).astype(float)
    def lap(Q):
        acc = np.zeros_like(Q)
        np.add.at(acc, E[:, 0], Q[E[:, 1]]); np.add.at(acc, E[:, 1], Q[E[:, 0]])
        return acc / np.maximum(deg, 1)[:, None] - Q
    def relax(m, k):
        for _ in range(k):
            acc = np.zeros(n); np.add.at(acc, E[:, 0], m[E[:, 1]]); np.add.at(acc, E[:, 1], m[E[:, 0]])
            m = 0.5 * m + 0.5 * acc / np.maximum(deg, 1)
        return m
    # open borders of the scan (small holes at the brim corners / cowl join): pinned, with a soft falloff
    es = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    ue, ce = np.unique(es, axis=0, return_counts=True)
    bnd = np.zeros(n); bnd[np.unique(ue[ce != 2])] = 1.0
    for _ in range(4):
        acc = np.zeros(n); np.add.at(acc, E[:, 0], bnd[E[:, 1]]); np.add.at(acc, E[:, 1], bnd[E[:, 0]])
        bnd = np.maximum(bnd, 0.75 * acc / np.maximum(deg, 1) * 2)
    pin = 1 - np.clip(bnd, 0, 1)
    C = np.array(HOOD['c'])
    X, Y, Z = P.T
    N0 = _vnormals(P, F)
    V = P - C; R = np.linalg.norm(V, axis=1); D = V / np.maximum(R, 1e-9)[:, None]
    face = (Y < -0.10) & (np.abs(X) < 0.135) & (Z < 0.87) & (Z > 0.58)       # mask / skin / lining inside the opening
    outward = _ss(((N0 * D).sum(1) + 0.05) / 0.35)
    # face opening as a cone around the front (-Y): azimuth < ~45 deg, elevation < ~34 deg; the brim rim sits at its edge
    az = np.degrees(np.arctan2(D[:, 0], -D[:, 1])); el = np.degrees(np.arcsin(np.clip(D[:, 2], -1, 1)))
    rho = np.sqrt((az / 45) ** 2 + (np.maximum(el, 0) / 34) ** 2)
    w = outward * _ss((rho - 1.05) / 0.55) * _ss((Z - 0.63) / 0.06) * (~face)
    w = w * _ss((R / hood_target(D) - 0.80) / 0.08)                          # only the shell itself, never the head inside
    w = relax(w, 3)                                               # no hard steps between shell / lining
    Q = P + (w * (hood_target(D) - R))[:, None] * D
    # smooth: the whole hood (shell, brim, crown front, cowl join), not the face
    m = _ss((Z - 0.60) / 0.04) * (~face)
    m = (relax(m, 2) * pin)[:, None]
    KS = 1 if '--no-subdiv' in argv else 3                      # finer hood mesh (v6 subdiv) needs more passes
    for _ in range(30 * KS):
        Q += 0.5 * m * lap(Q); Q -= 0.53 * m * lap(Q)
    # the rolled brim around the face opening: extra smoothing (it was wrinkled / cracked in the scan)
    mb = (np.exp(-((rho - 1.1) / 0.28) ** 2) * _ss((Z - 0.70) / 0.05) * pin * (~face))
    mb = relax(mb, 2 * KS)[:, None]
    for _ in range(40 * KS):
        Q += 0.5 * mb * lap(Q); Q -= 0.53 * mb * lap(Q)
    # re-project the fully-dome part once more (smoothing pulled it a little) and blend
    V = Q - C; R = np.linalg.norm(V, axis=1); D = V / np.maximum(R, 1e-9)[:, None]
    Q = Q + (0.8 * w * (hood_target(D) - R))[:, None] * D
    for _ in range(6):
        Q += 0.5 * m * lap(Q); Q -= 0.53 * m * lap(Q)
    # cloth folds (v6, pressed in along the normal): fal_v3/hood_folds.py (shared with the texture bake):
    # deep folds radiating from the tip down the back and sides, soft creases beside the face opening,
    # short pleats + sags where the hood bunches into the scarf
    Nn = _vnormals(Q, F)
    V = Q - C; R = np.linalg.norm(V, axis=1); D = V / np.maximum(R, 1e-9)[:, None]
    wf = (outward * _ss((rho - 1.12) / 0.22) * _ss((Z - 0.615) / 0.045) * (~face)
          * _ss((R / hood_target(D) - 0.80) / 0.08))
    wf = relax(wf, 2) * pin
    fold = hood_folds.fold_field(Q) * wf
    fold = relax(fold, 4)            # low-pass on the mesh: the geometry keeps what ~7 mm edges can hold, the sharp
                                     # crease line is in the baked normal map (scripts/v6_tex.py, same fold field)
    print('[ninja] hood folds: max %.1f mm, verts > 2 mm: %d, > 8 mm: %d' % (1000 * fold.max(), (fold > 0.002).sum(), (fold > 0.008).sum()))
    Q = Q - Nn * fold[:, None]
    for _ in range(6):
        Q += 0.5 * m * lap(Q); Q -= 0.53 * m * lap(Q)
    # untangle: faces folded over (scan layers squeezed onto the same shell) -> plain Laplacian on them + 1 ring;
    # later rounds also soften faces > ~28 deg off the local smooth normal (fold-start lips, pinches)
    hz = (_ss((Z - 0.60) / 0.04) * (~face)) > 0.5
    for it_ in range(6):
        fnr = np.cross(Q[F[:, 1]] - Q[F[:, 0]], Q[F[:, 2]] - Q[F[:, 0]])
        fnr /= np.maximum(np.linalg.norm(fnr, axis=1, keepdims=True), 1e-12)
        vn_ = _vnormals(Q, F)
        for _ in range(3):
            acc = np.zeros_like(vn_); np.add.at(acc, E[:, 0], vn_[E[:, 1]]); np.add.at(acc, E[:, 1], vn_[E[:, 0]])
            vn_ = acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
        badf = ((fnr * vn_[F].mean(1)).sum(1) < (0.3 if it_ < 2 else 0.88)) & hz[F].all(1)
        if not badf.any():
            break
        bv = np.zeros(n); bv[F[badf].ravel()] = 1
        bv = np.clip(relax(bv, 2) * 4, 0, 1)[:, None]
        for _ in range(8):
            Q += 0.5 * bv * lap(Q)
        print('[ninja] hood untangle round %d: %d folded faces' % (it_, badf.sum()))
    for v, q in zip(me.vertices, Q):
        v.co = q
    mv = np.linalg.norm(Q - P, axis=1)
    print('[ninja] hood sculpt v5: %d verts on the dome (w>0.5), max move %.1f mm, mean %.1f mm, back max y %.3f -> %.3f' % (
        (w > 0.5).sum(), 1000 * mv.max(), 1000 * mv[w > 0.5].mean(), P[P[:, 2] > 0.64, 1].max(), Q[Q[:, 2] > 0.64, 1].max()))
    return w
HOOD_W = None
if '--no-sculpt' not in argv:
    HOOD_W = hood_sculpt(body.data)
# v6: the imported scan carries custom split normals (Tripo noise, and stale where the hood was reshaped /
# subdivided): on the hood they are replaced by the true smooth normals of the new surface, blended out below it
if '--no-sculpt' not in argv:
    _me = body.data
    _ln = np.array([c.vector[:] for c in _me.corner_normals])
    _vn = np.array([v.vector[:] for v in _me.vertex_normals])
    _co = np.array([v.co[:] for v in _me.vertices])
    _face = (_co[:, 1] < -0.10) & (np.abs(_co[:, 0]) < 0.135) & (_co[:, 2] < 0.87) & (_co[:, 2] > 0.58)
    _hm = _ss((_co[:, 2] - 0.60) / 0.04) * (~_face)
    _lv = np.array([l.vertex_index for l in _me.loops])
    _w = _hm[_lv][:, None]
    _nl = _ln * (1 - _w) + _vn[_lv] * _w
    _nl /= np.maximum(np.linalg.norm(_nl, axis=1, keepdims=True), 1e-9)
    _me.normals_split_custom_set([tuple(x) for x in _nl])
    print('[ninja] hood normals: %d corners reset to smooth' % int((_w[:, 0] > 0.5).sum()))

# material: swap in the v3 albedo, eye-white emission
mat = body.data.materials[0]; mat.name = 'Ninja_Fal'
nt = mat.node_tree; N = nt.nodes; Lk = nt.links
bsdf = [n for n in N if n.type == 'BSDF_PRINCIPLED'][0]
bc_node = bsdf.inputs['Base Color'].links[0].from_node
img = bpy.data.images.load(os.path.join(SRC, _arg('--basecolor', 'basecolor_v6.webp')))
img.name = 'ninja_basecolor'; img.alpha_mode = 'STRAIGHT'
old = bc_node.image
bc_node.image = img
if old and old.users == 0:
    bpy.data.images.remove(old)
if not bsdf.inputs['Alpha'].is_linked:
    Lk.new(bc_node.outputs['Alpha'], bsdf.inputs['Alpha'])
em = N.new('ShaderNodeTexImage'); em.image = bpy.data.images.load(os.path.join(SRC, _arg('--emit-tex', 'emit_v3.png'))); em.image.name = 'ninja_emit'
NRM = _arg('--normal', 'normal_v6.webp')
if NRM != '-':
    for n_ in N:
        if n_.type == 'TEX_IMAGE' and n_.image and 'normal' in n_.image.name.lower():
            o_ = n_.image; n_.image = bpy.data.images.load(os.path.join(SRC, NRM)); n_.image.name = 'ninja_normal'
            n_.image.colorspace_settings.name = 'Non-Color'
            if o_.users == 0:
                bpy.data.images.remove(o_)
Lk.new(em.outputs['Color'], bsdf.inputs['Emission Color'])
bsdf.inputs['Emission Strength'].default_value = EMIT
try:
    mat.blend_method = 'CLIP'; mat.alpha_threshold = 0.5
except Exception:
    pass
mat.use_backface_culling = False

# ----------------------------------------------------------------------------------------------
# armature (same bone names as build_ninja.py; joints fitted to this mesh)
# ----------------------------------------------------------------------------------------------
SH = {s: Vector((0.155 * s, 0.0, 0.535)) for s in (1, -1)}
ELB = {s: Vector((0.222 * s, 0.0, 0.468)) for s in (1, -1)}
WRI = {s: Vector((0.262 * s, -0.015, 0.405)) for s in (1, -1)}
HTIP = {s: Vector((0.298 * s, -0.02, 0.335)) for s in (1, -1)}
HIPJ = {s: Vector((0.085 * s, -0.02, 0.335)) for s in (1, -1)}
KNEE = {s: Vector((0.09 * s, -0.03, 0.215)) for s in (1, -1)}
ANK = {s: Vector((0.09 * s, -0.005, 0.085)) for s in (1, -1)}
TOE = {s: Vector((0.095 * s, -0.10, 0.02)) for s in (1, -1)}
# rest directions of the previous (procedural) rig, used to carry its poses over
OLD_ARM = math.radians(40)
OLD_DIR = {}
for s, sd in ((1, 'L'), (-1, 'R')):
    a = Vector((math.cos(OLD_ARM) * s, 0.0, -math.sin(OLD_ARM)))
    OLD_DIR['upper_arm.' + sd] = OLD_DIR['forearm.' + sd] = OLD_DIR['hand.' + sd] = a
    OLD_DIR['thigh.' + sd] = (Vector((0.068 * s, -0.005, 0.178)) - Vector((0.064 * s, 0, 0.272))).normalized()
    OLD_DIR['shin.' + sd] = (Vector((0.07 * s, 0, 0.098)) - Vector((0.068 * s, -0.005, 0.178))).normalized()
    OLD_DIR['foot.' + sd] = (Vector((0.072 * s, -0.105, 0.03)) - Vector((0.07 * s, 0, 0.098))).normalized()
ARM_LIFT = math.radians(10)   # bulkier coat than the old body: keep the hanging arms ~10 deg further out

CAPE_TOP = 0.545
CAPE = {   # column -> 4 points top..hem (left column on +X; R mirrors it)
    'C': [(0, 0.075, CAPE_TOP), (0, 0.10, 0.40), (0, 0.125, 0.26), (0, 0.20, 0.11)],
    'L': [(0.13, 0.06, 0.53), (0.185, 0.085, 0.40), (0.225, 0.105, 0.27), (0.252, 0.12, 0.15)],
}
CAPE['R'] = [(-x, y, z) for x, y, z in CAPE['L']]

arm = bpy.data.armatures.new('Ninja_Rig')
rig = bpy.data.objects.new('Ninja_Rig', arm)
coll.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
def eb(name, h, t, parent=None, deform=True):
    b = arm.edit_bones.new(name)
    b.head, b.tail = Vector(h), Vector(t)
    b.use_deform = deform
    if parent:
        b.parent = arm.edit_bones[parent]; b.use_connect = False
    return b
eb('root', (0, 0, 0), (0, 0, 0.08), deform=False)
eb('hips', (0, -0.02, 0.30), (0, -0.02, 0.40), 'root')
eb('spine', (0, -0.02, 0.40), (0, -0.02, 0.47), 'hips')
eb('chest', (0, -0.02, 0.47), (0, -0.02, 0.555), 'spine')
eb('neck', (0, -0.02, 0.555), (0, -0.02, 0.62), 'chest')
eb('head', (0, -0.02, 0.62), (0, -0.02, 1.0), 'neck')
for s, sd in ((1, 'L'), (-1, 'R')):
    eb('upper_arm.' + sd, SH[s], ELB[s], 'chest')
    eb('forearm.' + sd, ELB[s], WRI[s], 'upper_arm.' + sd)
    eb('hand.' + sd, WRI[s], HTIP[s], 'forearm.' + sd)
    eb('thigh.' + sd, HIPJ[s], KNEE[s], 'hips')
    eb('shin.' + sd, KNEE[s], ANK[s], 'thigh.' + sd)
    eb('foot.' + sd, ANK[s], TOE[s], 'shin.' + sd)
for k, pts in CAPE.items():
    par = 'chest'
    for i in range(3):
        nm = 'cape_%s%d' % (k, i + 1)
        eb(nm, pts[i], pts[i + 1], par); par = nm
bpy.ops.object.mode_set(mode='OBJECT')
SEG = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm.bones}
CAPE_BONES = [b.name for b in arm.bones if b.name.startswith('cape_')]
BODY_BONES = [b.name for b in arm.bones if b.use_deform and not b.name.startswith('cape_')]

# ----------------------------------------------------------------------------------------------
# skin weights: automatic (bone heat) on the body bones, then fixed up:
#   head + hood rigid on 'head'; cape on the cape chains (never on legs / arms); no unweighted verts
# ----------------------------------------------------------------------------------------------
for b in arm.bones:
    b.use_deform = b.name in BODY_BONES
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
for b in arm.bones:
    b.use_deform = b.name != 'root'
nv = len(body.data.vertices)
names = BODY_BONES + CAPE_BONES
col = {n: i for i, n in enumerate(names)}
W = np.zeros((nv, len(names)))
gidx = {g.index: g.name for g in body.vertex_groups}
for v in body.data.vertices:
    for g in v.groups:
        n = gidx[g.group]
        if n in col:
            W[v.index, col[n]] = g.weight
P = np.array([v.co[:] for v in body.data.vertices])
X, Y, Z = P[:, 0], P[:, 1], P[:, 2]
def sstep(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)
def seg_d(Q, a, b):
    a = np.array(a); b = np.array(b); ab = b - a
    t = np.clip(((Q - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(Q - (a + t[:, None] * ab), axis=1)
def dist_w(Q, bones, k=3, rad=0.05):
    D = np.stack([seg_d(Q, *SEG[n]) for n in bones], 1) / rad
    Wd = 1.0 / (D * D + 0.02) ** 2
    if k < len(bones):
        thr = np.sort(Wd, 1)[:, -k][:, None]; Wd = np.where(Wd >= thr, Wd, 0)
    return Wd / Wd.sum(1, keepdims=True)
# 0) verts the heat solver missed -> distance weights on the body bones
miss = W.sum(1) < 0.3
if miss.any():
    W[miss, :len(BODY_BONES)] = dist_w(P[miss], BODY_BONES, 3, 0.06)
print('[ninja] auto-weights missed %d verts (distance fallback)' % miss.sum())
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
# 0b) heat weights jump between stacked layers (cowl over shoulder, coat over belt): relax along edges
EI = np.array([e.vertices[:] for e in body.data.edges])
deg = np.bincount(EI.ravel(), minlength=nv).astype(float)[:, None]
for _ in range(6):
    acc = np.zeros_like(W)
    np.add.at(acc, EI[:, 0], W[EI[:, 1]]); np.add.at(acc, EI[:, 1], W[EI[:, 0]])
    W = np.where(deg > 0, 0.5 * W + 0.5 * acc / np.maximum(deg, 1), W)
for sd, sg in (('L', 1), ('R', -1)):                 # arms never pull the spine line
    k = sstep((X * sg - 0.10) / 0.06)
    for b in ('upper_arm', 'forearm', 'hand'):
        W[:, col[b + '.' + sd]] *= k
lo = W.sum(1) < 0.3
if lo.any():
    tw = dist_w(P[lo], ['hips', 'spine', 'chest', 'neck'], 2, 0.08)
    for j, n in enumerate(['hips', 'spine', 'chest', 'neck']):
        W[lo, col[n]] += tw[:, j]
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
# 1) cape: below z ~0.5 the cape is a separate sheet (air gap to the body) -> flood fill from its hem;
#    above that it is fused with the shoulders: a thin band behind the back that fades to the chest
from collections import deque
nbr = [[] for _ in range(nv)]
for e in body.data.edges:
    a, b = e.vertices
    nbr[a].append(b); nbr[b].append(a)
seen = np.zeros(nv, bool)
q = deque(np.nonzero((Y > 0.12) & (Z < 0.3))[0].tolist())
seen[list(q)] = True
while q:
    i = q.popleft()
    for j in nbr[i]:
        if not seen[j] and Z[j] < 0.5:
            seen[j] = True; q.append(j)
assert seen.sum() < nv * 0.25 and Y[seen].min() > 0.04, 'cape flood fill leaked into the body'
seen |= (Y > 0.1) & (Z < 0.5)                      # stray islands of the cape sheet
top = sstep((Z - 0.49) / 0.02) * (Z < 0.56) * sstep((Y - 0.055) / 0.025) * (np.abs(X) < 0.2)
c_cape = np.maximum(seen.astype(float), top) * sstep((CAPE_TOP - 0.005 - Z) / 0.07)
for _ in range(3):                                   # relax along edges: no hard weight steps inside the sheet
    c_cape = 0.5 * c_cape + 0.5 * np.array([c_cape[n].mean() if n else c_cape[i] for i, n in enumerate(nbr)])
limbs = [col[n] for n in BODY_BONES if n.split('.')[0] in ('thigh', 'shin', 'foot', 'upper_arm', 'forearm', 'hand')]
cm = c_cape > 0.001
# body share of cape verts: no limb influence (legs must not drag the cape) -> hips / spine / chest
Wb = W[cm].copy()
Wb[:, limbs] = 0
Wb[:, len(BODY_BONES):] = 0
trunk = dist_w(P[cm], ['hips', 'spine', 'chest'], 2, 0.08)
for j, n in enumerate(['hips', 'spine', 'chest']):
    Wb[:, col[n]] += trunk[:, j] * (Wb.sum(1) < 0.2)
Wb /= np.maximum(Wb.sum(1, keepdims=True), 1e-9)
Wc = np.zeros_like(Wb)
cw = dist_w(P[cm], CAPE_BONES, 3, 0.07)
for j, n in enumerate(CAPE_BONES):
    Wc[:, col[n]] = cw[:, j]
cc = c_cape[cm][:, None]
W[cm] = Wb * (1 - cc) + Wc * cc
# 2) head + hood rigid (blend over the cowl)
h = sstep((Z - 0.595) / 0.05)
h[(Z > 0.56) & (Z < 0.66) & (np.abs(X) > 0.19)] = 0     # shoulders never follow the head (the hood sides above do)
W *= (1 - h)[:, None]
W[:, col['head']] += h
# 2b) v4: extra local relaxation at the worst stretch spots found with stretch.py (shoulder/collar join,
#     upper-coat seam, chest strap buckle, cape hem corners); mirrored in X, never inside the rigid head
HOT = [(0.155, 0.05, 0.565, 0.035), (0.13, 0.05, 0.57, 0.03), (0.095, 0.051, 0.484, 0.025), (0.12, 0.012, 0.493, 0.025),
       (0.02, -0.11, 0.48, 0.025), (0.15, 0.02, 0.377, 0.025), (0.12, 0.16, 0.19, 0.03), (0.118, 0.154, 0.217, 0.025),
       (0.105, 0.035, 0.515, 0.025), (0.022, -0.112, 0.377, 0.025), (0.08, -0.09, 0.51, 0.025),
       (0.10, -0.076, 0.515, 0.03), (0.0, -0.122, 0.448, 0.02), (0.157, 0.06, 0.543, 0.03)]
mh = np.zeros(nv)
for hx, hy, hz, hr in HOT:
    for sx in (1, -1):
        d2 = (X - sx * hx) ** 2 + (Y - hy) ** 2 + (Z - hz) ** 2
        mh = np.maximum(mh, np.exp(-d2 / hr ** 2))
mh *= (1 - h)
mh = mh[:, None]
for _ in range(12):
    acc = np.zeros_like(W)
    np.add.at(acc, EI[:, 0], W[EI[:, 1]]); np.add.at(acc, EI[:, 1], W[EI[:, 0]])
    W = np.where(deg > 0, (1 - 0.6 * mh) * W + 0.6 * mh * acc / np.maximum(deg, 1), W)
# ... plus a spatial pass (layers that touch but share no edges: strap over coat, buckle over belt)
from mathutils.kdtree import KDTree
kd = KDTree(nv)
for i in range(nv):
    kd.insert(P[i], i)
kd.balance()
hot_i = np.nonzero(mh[:, 0] > 0.05)[0]
NB = [np.array([j for (_, j, _) in kd.find_range(P[i], 0.012)]) for i in hot_i]
for _ in range(4):
    Wn = W.copy()
    for i, nb in zip(hot_i, NB):
        Wn[i] = (1 - 0.6 * mh[i, 0]) * W[i] + 0.6 * mh[i, 0] * W[nb].mean(0)
    W = Wn
# 3) clean: drop < 0.02, max 4 influences, normalise
W[W < 0.02] = 0
o = np.argsort(-W, 1)
keep = np.zeros_like(W, bool); np.put_along_axis(keep, o[:, :4], True, 1)
W = np.where(keep, W, 0); W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
for g in list(body.vertex_groups):
    body.vertex_groups.remove(g)
groups = {n: body.vertex_groups.new(name=n) for n in names}
for n in names:
    j = col[n]; idx = np.nonzero(W[:, j] > 0)[0]
    for i in idx:
        groups[n].add([int(i)], float(W[i, j]), 'REPLACE')
CAPE_MASK = c_cape > 0.5
print('[ninja] cape verts %d, head-rigid verts %d' % (CAPE_MASK.sum(), (h > 0.99).sum()))

# ----------------------------------------------------------------------------------------------
# optional accessories (from the previous build): re-seated in the new right hand, 100 % hand.R
# ----------------------------------------------------------------------------------------------
ACC = {}
if os.path.exists(ACC_BLEND):
    with bpy.data.libraries.load(ACC_BLEND, link=False) as (src, dst):
        dst.meshes = [m for m in src.meshes if m in ('Acc_Dagger', 'Acc_HandProp')]
        dst.armatures = [a for a in src.armatures if a == 'Ninja_Rig']
    old_arm = [a for a in bpy.data.armatures if a is not arm][0]
    Mo = old_arm.bones['hand.R'].matrix_local
    Mn = arm.bones['hand.R'].matrix_local
    T = Mn @ Matrix.Diagonal((1.15, 1.15, 1.15, 1.0)) @ Mo.inverted()   # bigger glove -> 15 % bigger props
    for me in dst.meshes:
        me.transform(T)
        ob = bpy.data.objects.new(me.name, me)
        coll.objects.link(ob)
        g = ob.vertex_groups.new(name='hand.R'); g.add(list(range(len(me.vertices))), 1.0, 'REPLACE')
        ob.parent = rig
        m = ob.modifiers.new('Armature', 'ARMATURE'); m.object = rig
        ob['optional_accessory'] = 'dagger' if 'Dagger' in me.name else 'handprop'
        ob.hide_render = True
        ob.hide_set(True)
        ACC[me.name] = ob
    bpy.data.armatures.remove(old_arm)
else:
    print('[ninja] WARNING: no accessory source', ACC_BLEND)

# ----------------------------------------------------------------------------------------------
# animation: the previous build's poses (rotations in armature axes, deg) carried over to this rig
# ----------------------------------------------------------------------------------------------
def mirror_name(n):
    return n[:-2] + '.R' if n.endswith('.L') else n[:-2] + '.L' if n.endswith('.R') else n
def mirror_pose(p):
    out = {}
    for n, v in p.items():
        if n.startswith('cape_'):
            k = n[5]; mk = {'L': 'R', 'R': 'L', 'C': 'C'}[k]
            out['cape_' + mk + n[6:]] = (v[0], -v[1], -v[2])
        elif n == 'lift':
            out[n] = v
        else:
            out[mirror_name(n)] = (v[0], -v[1], -v[2])
    return out
def merge(*ps):
    out = {}
    for p in ps:
        out.update(p)
    return out
def cape(a, b, c, sway=0.0, side=0.0):
    """a/b/c: swing back per bone level (deg); sway: twist; side: the edges flare outward (symmetric cape)"""
    out = {}
    for k, w in (('C', 0.0), ('L', 1.0), ('R', -1.0)):
        out['cape_%s1' % k] = (a * (1 - 0.15 * abs(w)), -w * side * 0.35, sway * (1 + 0.5 * w))
        out['cape_%s2' % k] = (b, -w * side * 0.45, sway * 0.5)
        out['cape_%s3' % k] = (c, -w * side * 0.35, sway * 0.3)
    return out

STAND = merge({'upper_arm.L': (0, 34, 0), 'upper_arm.R': (0, -34, 0), 'forearm.L': (-18, 0, 0), 'forearm.R': (-18, 0, 0),
               'thigh.L': (-8, -5, 0), 'thigh.R': (-8, 5, 0), 'shin.L': (15, 5, 0), 'shin.R': (15, -5, 0),
               'foot.L': (-7, 0, 0), 'foot.R': (-7, 0, 0), 'spine': (4, 0, 0), 'head': (-4, 0, 0)}, cape(4, 2, 2))
IDLE_B = merge(STAND, {'chest': (-2, 0, 0), 'upper_arm.L': (0, 37, 0), 'upper_arm.R': (0, -37, 0), 'head': (-6, 0, 0),
                       'thigh.L': (-11, -5, 0), 'thigh.R': (-11, 5, 0), 'shin.L': (20, 5, 0), 'shin.R': (20, -5, 0),
                       'foot.L': (-9, 0, 0), 'foot.R': (-9, 0, 0)}, cape(7, 4, 4, 2, 3))
RUN_BODY = {'spine': (14, 0, 0), 'chest': (8, 0, -6), 'hips': (0, 0, 6), 'head': (-20, 0, 6),
            'upper_arm.L': (68, 26, 0), 'upper_arm.R': (62, -26, 0), 'forearm.L': (12, 0, 0), 'forearm.R': (12, 0, 0)}
RUN_C = merge(RUN_BODY, {'thigh.L': (-48, 0, 0), 'shin.L': (22, 0, 0), 'foot.L': (-6, 0, 0),
                         'thigh.R': (32, 0, 0), 'shin.R': (58, 0, 0), 'foot.R': (22, 0, 0)}, cape(26, 14, 10, 4, 16))
RUN_P = merge(RUN_BODY, {'hips': (0, 0, 0), 'chest': (8, 0, 0), 'head': (-20, 0, 0),
                         'thigh.L': (-6, 0, 0), 'shin.L': (14, 0, 0), 'foot.L': (-8, 0, 0),
                         'thigh.R': (-38, 0, 0), 'shin.R': (104, 0, 0), 'foot.R': (12, 0, 0), 'lift': 0.022}, cape(32, 16, 12, 0, 20))
CROUCH = {'thigh.L': (-58, -4, 0), 'thigh.R': (-58, 4, 0), 'shin.L': (88, 0, 0), 'shin.R': (88, 0, 0), 'foot.L': (-30, 0, 0),
          'foot.R': (-30, 0, 0), 'spine': (26, 0, 0), 'chest': (6, 0, 0), 'head': (-26, 0, 0),
          'upper_arm.L': (55, 26, 0), 'upper_arm.R': (55, -26, 0), 'forearm.L': (10, 0, 0), 'forearm.R': (10, 0, 0)}
JUMP_UP = merge({'thigh.L': (-12, 0, 0), 'thigh.R': (-6, 0, 0), 'shin.L': (14, 0, 0), 'shin.R': (10, 0, 0), 'foot.L': (32, 0, 0),
                 'foot.R': (32, 0, 0), 'spine': (-4, 0, 0), 'head': (-6, 0, 0),
                 'upper_arm.L': (-140, 12, 0), 'upper_arm.R': (-140, -12, 0), 'forearm.L': (-12, 0, 0), 'forearm.R': (-12, 0, 0)}, cape(14, 6, 4, 0, 6))
JUMP_TUCK = merge({'thigh.L': (-72, -6, 0), 'thigh.R': (-34, 6, 0), 'shin.L': (104, 0, 0), 'shin.R': (64, 0, 0), 'foot.L': (12, 0, 0),
                   'foot.R': (22, 0, 0), 'spine': (10, 0, 0), 'head': (-12, 0, 0),
                   'upper_arm.L': (-40, -22, 0), 'upper_arm.R': (-40, 22, 0), 'forearm.L': (-30, 0, 0), 'forearm.R': (-30, 0, 0)}, cape(36, 14, 10, 0, 14))
FALL_A = merge({'thigh.L': (-36, -6, 0), 'thigh.R': (-10, 6, 0), 'shin.L': (52, 0, 0), 'shin.R': (28, 0, 0), 'foot.L': (20, 0, 0),
                'foot.R': (24, 0, 0), 'spine': (-5, 0, 0), 'head': (-10, 0, 0),
                'upper_arm.L': (-28, -55, 0), 'upper_arm.R': (-28, 55, 0), 'forearm.L': (-22, 0, 0), 'forearm.R': (-22, 0, 0)}, cape(50, 20, 14, -4, 14))
FALL_B = merge(FALL_A, {'thigh.L': (-26, -6, 0), 'thigh.R': (-20, 6, 0), 'shin.L': (40, 0, 0), 'shin.R': (40, 0, 0),
                        'upper_arm.L': (-32, -63, 0), 'upper_arm.R': (-32, 63, 0)}, cape(58, 24, 18, 4, 18))
LAND_IMPACT = merge(CROUCH, {'thigh.L': (-66, -6, 0), 'thigh.R': (-66, 6, 0), 'shin.L': (102, 0, 0), 'shin.R': (102, 0, 0),
                             'foot.L': (-36, 0, 0), 'foot.R': (-36, 0, 0), 'spine': (30, 0, 0), 'upper_arm.L': (42, 30, 0),
                             'upper_arm.R': (42, -30, 0)}, cape(24, 6, 6))
LAND_MID = merge(CROUCH, {'thigh.L': (-44, -4, 0), 'thigh.R': (-44, 4, 0), 'shin.L': (70, 0, 0), 'shin.R': (70, 0, 0),
                          'foot.L': (-25, 0, 0), 'foot.R': (-25, 0, 0), 'spine': (20, 0, 0)}, cape(32, 8, 8, 0, 8))
LAND_END = merge(RUN_BODY, {'hips': (0, 0, 0), 'chest': (8, 0, 0), 'head': (-20, 0, 0), 'thigh.L': (-14, -3, 0), 'thigh.R': (-10, 3, 0),
                            'shin.L': (24, 0, 0), 'shin.R': (20, 0, 0), 'foot.L': (-10, 0, 0), 'foot.R': (-10, 0, 0)}, cape(28, 10, 8, 0, 12))
SLIDE_A = merge({'thigh.L': (-86, -4, 0), 'shin.L': (6, 0, 0), 'foot.L': (24, 0, 0),
                 'thigh.R': (-34, 10, 0), 'shin.R': (122, 0, 0), 'foot.R': (22, 0, 0),
                 'spine': (-20, 0, 0), 'chest': (-6, 0, 0), 'head': (16, 0, 0),
                 'upper_arm.L': (-36, -28, 0), 'upper_arm.R': (40, 12, 0), 'forearm.L': (-24, 0, 0), 'forearm.R': (-10, 0, 0)}, cape(52, 14, 10, 3, 14))
SLIDE_B = merge(SLIDE_A, {'spine': (-23, 0, 0), 'head': (18, 0, 0), 'upper_arm.L': (-40, -32, 0)}, cape(58, 18, 14, -3, 18))

# ----------------------------------------------------------------------------------------------
# cape motion (v4): the cape hangs DOWN and trails BACK (+Y), side chains pulled in toward the centre
# as it lifts so the silhouette from behind stays about shoulder wide; travelling wave down the chain
# (each level lags) + a faster small flutter. Cyclic clips are exactly periodic.
# angles (deg) are in armature space: X+ swings the hem back, Y+ moves a hanging bone toward -X.
# ----------------------------------------------------------------------------------------------
def _lerp_keys(kf, f):
    for (f0, v0), (f1, v1) in zip(kf, kf[1:]):
        if f0 <= f <= f1:
            t = (f - f0) / max(f1 - f0, 1e-6); t = t * t * (3 - 2 * t)
            return v0 + (v1 - v0) * t
    return kf[-1][1]
CAPE_MOTION = {   # lift: total trail-back angle (deg) over frame keys; wave / flutter amplitude (deg); cycles per clip
    'Idle':  dict(lift=[(0, 5), (24, 7), (48, 5)], wave=1.5, flut=0.8, k=1, kf=2),
    'Run':   dict(lift=[(0, 30), (16, 30)], wave=4.0, flut=2.5, k=1, kf=2, sway=3.0),
    'Jump':  dict(lift=[(0, 5), (4, 3), (8, 22), (14, 38), (18, 42)], wave=3.0, flut=2.5, k=1, kf=2),
    'Fall':  dict(lift=[(0, 50), (12, 54), (24, 50)], wave=5.0, flut=3.5, k=1, kf=3),
    'Land':  dict(lift=[(0, 50), (3, 40), (9, 14), (14, 1), (20, 7)], wave=2.5, flut=1.5, k=1, kf=2, decay=True),
    'Slide': dict(lift=[(0, 84), (8, 90), (16, 84)], wave=4.0, flut=3.0, k=1, kf=2),
}
CAPE_SPLIT = (0.46, 0.32, 0.22)       # share of the lift per level (top..hem)
CAPE_IN = 0.45                        # side chains: inward swing per degree of their lift
def cape_keys(act, f, T):
    m = CAPE_MOTION[act]
    lift = _lerp_keys(m['lift'], f)
    ph = 2 * math.pi * f / max(T, 1)
    amp = (1 - 0.7 * f / max(T, 1)) if m.get('decay') else 1.0
    out = {}
    for col, w in (('C', 0.0), ('L', 1.0), ('R', -1.0)):
        for i in range(3):
            lag = 0.9 * (i + 1) + 0.6 * w           # wave runs down the chain; the edges a bit out of phase
            a = lift * CAPE_SPLIT[i] * (1 - 0.12 * abs(w))
            a += amp * m['wave'] * (0.5 + 0.35 * i) * math.sin(m['k'] * ph - lag)
            a += amp * m['flut'] * (0.3 + 0.45 * i) * math.sin(m['kf'] * ph - 1.3 * lag + (0.8 * w))
            sway = m.get('sway', 0.0) * math.sin(ph - 0.7 * i)          # follows the hips in Run
            inward = w * CAPE_IN * max(a, 0.0)                            # keep the edges in behind the body
            twist = w * 0.6 * amp * m['flut'] * math.sin(m['kf'] * ph - lag)
            out['cape_%s%d' % (col, i + 1)] = (a, inward + sway * (1 if i == 0 else 0.5), twist)
    return out

ACTIONS = [
    ('Idle', [(0, STAND), (24, IDLE_B), (48, STAND)]),
    ('Run', [(0, RUN_C), (4, RUN_P), (8, mirror_pose(RUN_C)), (12, mirror_pose(RUN_P)), (16, RUN_C)]),
    ('Jump', [(0, STAND), (4, CROUCH), (8, JUMP_UP), (14, JUMP_TUCK), (18, merge(JUMP_TUCK, cape(40, 16, 12, 0, 14)))]),
    ('Fall', [(0, FALL_A), (12, FALL_B), (24, FALL_A)]),
    ('Land', [(0, merge(FALL_A, {'thigh.L': (-15, -6, 0), 'thigh.R': (-12, 6, 0), 'shin.L': (16, 0, 0), 'shin.R': (14, 0, 0)})),
              (3, LAND_IMPACT), (9, LAND_MID), (20, LAND_END)]),
    ('Slide', [(0, SLIDE_A), (8, SLIDE_B), (16, SLIDE_A)]),
]

PB = rig.pose.bones
for pb in PB:
    pb.rotation_mode = 'QUATERNION'
# Delta: rest-direction change old rig -> this rig per limb bone (arms also lifted by ARM_LIFT);
# a pose rotation R (old rig) becomes  D_parent . R . D_self^-1  so every limb ends up pointing where it did.
DELTA = {}
for n, od in OLD_DIR.items():
    if n.split('.')[0] in ('upper_arm', 'forearm', 'hand'):
        s = 1 if n.endswith('.L') else -1
        od = Matrix.Rotation(-s * ARM_LIFT, 3, 'Y') @ od     # +Y lowers the left arm -> -Y lifts it
    b = arm.bones[n]
    nd = (b.tail_local - b.head_local).normalized()
    DELTA[n] = od.rotation_difference(nd).to_matrix()
I3 = Matrix.Identity(3)
def pose_rot(name, deg):
    R = Euler([math.radians(a) for a in deg], 'XYZ').to_matrix() if deg is not None else I3.copy()
    b = arm.bones[name]
    Dp = DELTA.get(b.parent.name, I3) if b.parent else I3
    Ds = DELTA.get(name, I3)
    return Dp @ R @ Ds.inverted()
def to_local(name, R):
    M = arm.bones[name].matrix_local.to_3x3()
    return (M.inverted() @ R @ M).to_quaternion()
GROUND_IDX = np.nonzero(~CAPE_MASK & (Z < 0.45))[0]
def lowest_z():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    c = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get('co', c)
    ev.to_mesh_clear()
    return float(c.reshape(-1, 3)[GROUND_IDX, 2].min())
def apply_pose(pose):
    for pb in PB:
        pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
    for pb in PB:
        n = pb.name
        if n in pose or n in DELTA or (pb.parent and pb.parent.name in DELTA):
            pb.rotation_quaternion = to_local(n, pose_rot(n, pose.get(n)))
    bpy.context.view_layer.update()
    dz = -lowest_z() + pose.get('lift', 0.0)
    Mh = arm.bones['hips'].matrix_local.to_3x3()
    PB['hips'].location = Mh.inverted() @ Vector((0, 0, dz))
    bpy.context.view_layer.update()

rig.animation_data_create()
for name, keys in ACTIONS:
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data.action = act
    prev = {}
    for f, pose in keys:
        apply_pose(pose)
        for pb in PB:
            q = pb.rotation_quaternion.copy()
            if pb.name in prev and prev[pb.name].dot(q) < 0:
                q.negate(); pb.rotation_quaternion = q
            prev[pb.name] = q
            pb.keyframe_insert('rotation_quaternion', frame=f, group=pb.name)
        PB['hips'].keyframe_insert('location', frame=f, group='hips')
    # v4: the cape bones get their own keys every 2 frames (overriding the pose-set values above)
    T = keys[-1][0]
    for f in range(0, T + 1, 2):
        for n_, e_ in cape_keys(name, f, T).items():
            q = to_local(n_, Euler([math.radians(a) for a in e_], 'XYZ').to_matrix())
            if n_ in prev and prev[n_].dot(q) < 0:
                q.negate()
            prev[n_] = q
            PB[n_].rotation_quaternion = q
            PB[n_].keyframe_insert('rotation_quaternion', frame=f, group=n_)
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, keys[-1][0]
    act.use_cyclic = name in ('Idle', 'Run', 'Fall', 'Slide')
    tr = rig.animation_data.nla_tracks.new(); tr.name = name
    tr.strips.new(name, 0, act); tr.mute = True
    print('[ninja] action %-6s frames 0-%d  (%.2fs)' % (name, keys[-1][0], keys[-1][0] / FPS))
rig.animation_data.action = bpy.data.actions['Idle']
scene.frame_start, scene.frame_end = 0, 48
scene.frame_set(0)

# ----------------------------------------------------------------------------------------------
# report + save + export
# ----------------------------------------------------------------------------------------------
for ob in [body] + list(ACC.values()):
    print('[ninja] %-14s verts %6d tris %6d' % (ob.name, len(ob.data.vertices), sum(len(p.vertices) - 2 for p in ob.data.polygons)))
for im in bpy.data.images:
    print('[ninja] texture %-20s %dx%d' % (im.name, im.size[0], im.size[1]))
bpy.ops.file.pack_all()
bpy.context.preferences.filepaths.save_version = 0
os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('[ninja] saved', OUT_BLEND)

os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
for ob in bpy.data.objects:
    ob.hide_set(False)
kw = dict(filepath=OUT_GLB, export_format='GLB', use_selection=False, use_visible=False, export_extras=True,
          export_yup=True, export_apply=False, export_animations=True, export_animation_mode='ACTIONS',
          export_force_sampling=True, export_frame_range=False, export_anim_slide_to_zero=True, export_skins=True,
          export_def_bones=False, export_all_influences=False, export_materials='EXPORT', export_image_format='WEBP',
          export_image_quality=90, export_morph=False, export_reset_pose_bones=True)
while True:
    try:
        bpy.ops.export_scene.gltf(**kw); break
    except TypeError as e:
        bad = [k for k in kw if ('"%s"' % k) in str(e)]
        if not bad:
            raise
        print('[ninja] exporter: dropping unknown option', bad)
        for k in bad:
            kw.pop(k)
for ob in ACC.values():
    ob.hide_set(True)

# the exporter writes alphaMode BLEND for an alpha-linked base colour: the cape holes are a cutout -> MASK
with open(OUT_GLB, 'rb') as f:
    data = f.read()
jl = struct.unpack_from('<I', data, 12)[0]
js = json.loads(data[20:20 + jl])
for m in js.get('materials', []):
    if m.get('name') == 'Ninja_Fal':
        m['alphaMode'] = 'MASK'; m['alphaCutoff'] = 0.5; m['doubleSided'] = True
jb = json.dumps(js, separators=(',', ':')).encode()
jb += b' ' * ((4 - len(jb) % 4) % 4)
rest = data[20 + jl:]
out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(jb) + len(rest)) + struct.pack('<II', len(jb), 0x4E4F534A) + jb + rest
with open(OUT_GLB, 'wb') as f:
    f.write(out)
print('[ninja] exported', OUT_GLB, os.path.getsize(OUT_GLB), 'bytes')
