# Chibi ninja player character for xrush (replaces the X1 car's visual).
#
#   blender -b --factory-startup -P assets-src/ninja/build_ninja.py
#   blender -b --factory-startup -P assets-src/ninja/build_ninja.py -- --blend out.blend --glb out.glb
#
# Builds everything from code (no external files): meshes with UVs, PBR materials with generated
# (and packed) fabric / leather / strap / sole textures, an armature with computed skin weights,
# six in-place actions (Idle, Run, Jump, Fall, Land, Slide), then saves NinjaCharacter.blend and
# exports the GLB the game loads (src/assets/models/ninja.glb).
#
# Units: metres, Blender axes (Z up, the character faces -Y, its left hand is on +X). The model is
# ~1.0 m tall here; the game scales it (RENDER.ninja in src/config.ts). Feet rest on z = 0.
import bpy, bmesh, math, os, sys, random
import numpy as np
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def _arg(k, d):
    return argv[argv.index(k) + 1] if k in argv else d
OUT_BLEND = _arg('--blend', os.path.join(HERE, 'NinjaCharacter.blend'))
OUT_GLB = _arg('--glb', os.path.join(REPO, 'src', 'assets', 'models', 'ninja.glb'))
TEX_DIR = os.path.join(HERE, 'textures')
os.makedirs(TEX_DIR, exist_ok=True)
FPS = 30

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
random.seed(7)

# ----------------------------------------------------------------------------------------------
# textures (generated with numpy, saved next to this script and packed into the .blend)
# ----------------------------------------------------------------------------------------------
def periodic_noise(n, cycles, seed, m=None):
    m = m or n
    rng = np.random.default_rng(seed)
    f = np.fft.fft2(rng.standard_normal((m, n)))
    ky = np.fft.fftfreq(m)[:, None] * m
    kx = np.fft.fftfreq(n)[None, :] * n
    k = np.sqrt(kx ** 2 + ky ** 2)
    r = np.real(np.fft.ifft2(f * np.exp(-(k / cycles) ** 2)))
    return (r - r.mean()) / (r.std() + 1e-9)

def height_to_normal(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    n = np.stack([-dx, -dy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5

def make_image(name, rgb, non_color=False):
    """rgb: HxWx3 in 0..1, row 0 = bottom (Blender pixel order)"""
    h, w = rgb.shape[:2]
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.ones((h, w, 1))], -1).astype(np.float32)
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(TEX_DIR, name + '.png')
    img.file_format = 'PNG'
    img.save()
    img.pack()
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img

def fabric_textures(n=512, threads=40):
    y, x = np.mgrid[0:n, 0:n] / n * threads
    i, j = np.floor(x).astype(int), np.floor(y).astype(int)
    fu, fv = x - i, y - j
    warp_top = ((i + j) % 4) < 2  # 2/2 twill
    warp = np.sin(np.pi * fu) ** 0.6 * (0.55 + 0.45 * np.sin(np.pi * fv))
    weft = np.sin(np.pi * fv) ** 0.6 * (0.55 + 0.45 * np.sin(np.pi * fu))
    h = np.where(warp_top, warp, weft * 0.85)
    fib = periodic_noise(n, 90, 3)
    low = periodic_noise(n, 6, 4)
    sw = periodic_noise(n, 6, 5)                       # embossed swirl / damask-like pattern:
    lines = np.exp(-np.sin(sw * 4.2) ** 2 / 0.05)      # contour lines of a smooth noise
    h2 = 0.45 * h + 0.55 * lines + 0.08 * fib
    alb = 0.84 + 0.05 * h + 0.05 * lines + 0.04 * low + 0.015 * fib
    nrm = height_to_normal(h2, 2.4)
    rough = 0.80 + 0.06 * (1 - h) - 0.07 * lines + 0.04 * low
    ao = 0.82 + 0.18 * h
    orm = np.stack([ao, rough, np.zeros_like(h)], -1)
    return (make_image('T_Fabric_BaseColor', np.repeat(alb[..., None], 3, -1)),
            make_image('T_Fabric_Normal', nrm, True),
            make_image('T_Fabric_ORM', orm, True))

def leather_textures(n=256):
    a = np.abs(periodic_noise(n, 28, 11))
    b = periodic_noise(n, 70, 12)
    h = -a * 0.7 + 0.2 * b
    nrm = height_to_normal(h, 1.4)
    low = periodic_noise(n, 5, 13)
    rough = 0.52 + 0.1 * a + 0.05 * low
    orm = np.stack([np.ones_like(h), rough, np.zeros_like(h)], -1)
    alb = 0.9 + 0.06 * low - 0.05 * a
    return (make_image('T_Leather_BaseColor', np.repeat(alb[..., None], 3, -1)),
            make_image('T_Leather_Normal', nrm, True),
            make_image('T_Leather_ORM', orm, True))

def strap_textures(w=256, hgt=64, stitch_rows=(0.2, 0.8), dash=16):
    """tiles along U; V runs across the strap. Stitch lines + raised edges"""
    y, x = np.mgrid[0:hgt, 0:w].astype(float)
    v = (y + 0.5) / hgt
    u = (x + 0.5) / w
    edge = np.clip(np.minimum(v, 1 - v) / 0.12, 0, 1) ** 0.5
    h = 0.6 * edge
    stitch = np.zeros_like(h)
    for r in stitch_rows:
        phase = (u * dash) % 1.0
        on = (phase > 0.15) & (phase < 0.75)
        prof = np.clip(1 - np.abs(v - r) / 0.05, 0, 1)
        stitch = np.maximum(stitch, prof * on)
        h -= 0.35 * np.clip(1 - np.abs(v - r) / 0.09, 0, 1)  # groove under the thread
    h += 0.6 * stitch
    grain = periodic_noise(w, 40, 21, hgt) * 0.05
    nrm = height_to_normal(h + grain, 3.0)
    alb = (0.9 + 0.06 * edge)[..., None] * np.ones(3)
    thread = np.array([1.0, 0.92, 0.8])  # lighter thread (x the material colour)
    alb = alb * (1 - stitch[..., None]) + thread * stitch[..., None]
    rough = 0.55 + 0.25 * stitch
    orm = np.stack([np.ones_like(h), rough, np.zeros_like(h)], -1)
    return alb, nrm, orm

def sole_textures(n=128):
    y, x = np.mgrid[0:n, 0:n] / n
    h = (np.sin(y * np.pi * 2 * 4) > 0.2).astype(float)  # tread bars
    h = h * 0.8 + 0.2 * (np.abs(periodic_noise(n, 20, 31)) < 0.4)
    nrm = height_to_normal(h, 2.5)
    return make_image('T_Sole_Normal', nrm, True)

TEX = {}
TEX['fab'] = fabric_textures()
TEX['lea'] = leather_textures()
a, nm, orm = strap_textures()
TEX['strap'] = (make_image('T_Strap_BaseColor', a), make_image('T_Strap_Normal', nm, True), make_image('T_Strap_ORM', orm, True))
a, nm, orm = strap_textures(w=128, hgt=32, stitch_rows=(0.5,), dash=10)
TEX['seam'] = (make_image('T_Seam_BaseColor', a), make_image('T_Seam_Normal', nm, True), make_image('T_Seam_ORM', orm, True))
TEX['sole_n'] = sole_textures()

# ----------------------------------------------------------------------------------------------
# materials (glTF-compatible Principled setups: texture x factor via Mix/Multiply)
# ----------------------------------------------------------------------------------------------
def s2l(c):
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

MATS = {}
def make_mat(name, color, rough=0.8, metal=0.0, tex=None, normal=None, nstr=1.0, orm=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    b = N['Principled BSDF']
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    col = (*s2l(color), 1.0)
    if tex is not None:
        t = N.new('ShaderNodeTexImage'); t.image = tex; t.location = (-700, 300)
        mx = N.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.location = (-350, 300)
        mx.inputs['Factor'].default_value = 1.0
        L.new(t.outputs['Color'], mx.inputs[6])
        mx.inputs[7].default_value = col
        L.new(mx.outputs[2], b.inputs['Base Color'])
    else:
        b.inputs['Base Color'].default_value = col
    if orm is not None:
        t = N.new('ShaderNodeTexImage'); t.image = orm; t.location = (-700, 0)
        sp = N.new('ShaderNodeSeparateColor'); sp.location = (-400, 0)
        L.new(t.outputs['Color'], sp.inputs['Color'])
        L.new(sp.outputs['Green'], b.inputs['Roughness'])
    if normal is not None:
        t = N.new('ShaderNodeTexImage'); t.image = normal; t.location = (-700, -300)
        nmn = N.new('ShaderNodeNormalMap'); nmn.location = (-350, -300)
        nmn.inputs['Strength'].default_value = nstr
        L.new(t.outputs['Color'], nmn.inputs['Color'])
        L.new(nmn.outputs['Normal'], b.inputs['Normal'])
    MATS[name] = m
    return m

fab_a, fab_n, fab_o = TEX['fab']
lea_a, lea_n, lea_o = TEX['lea']
st_a, st_n, st_o = TEX['strap']
se_a, se_n, se_o = TEX['seam']
# colours are albedo (sRGB) without the references' blue / orange lighting
make_mat('Ninja_Cloth', (0.178, 0.157, 0.16), tex=fab_a, normal=fab_n, orm=fab_o, nstr=0.8)
make_mat('Ninja_ClothDark', (0.148, 0.13, 0.133), tex=fab_a, normal=fab_n, orm=fab_o, nstr=0.8)
make_mat('Ninja_Seam', (0.15, 0.135, 0.135), tex=se_a, normal=se_n, orm=se_o, nstr=0.8)
make_mat('Ninja_Scuff', (0.21, 0.195, 0.195), rough=0.92)
make_mat('Ninja_LeatherBrown', (0.27, 0.19, 0.14), tex=lea_a, normal=lea_n, orm=lea_o, nstr=0.6)
make_mat('Ninja_LeatherBlack', (0.125, 0.112, 0.112), tex=lea_a, normal=lea_n, orm=lea_o, nstr=0.6)
make_mat('Ninja_Strap', (0.27, 0.19, 0.14), tex=st_a, normal=st_n, orm=st_o, nstr=0.8)
make_mat('Ninja_Sole', (0.15, 0.115, 0.1), rough=0.8, normal=TEX['sole_n'], nstr=0.6)
make_mat('Ninja_Skin', (0.98, 0.63, 0.43), rough=0.55)
make_mat('Ninja_Mask', (0.085, 0.08, 0.085), rough=0.48)
make_mat('Ninja_PropRubber', (0.2, 0.155, 0.14), rough=0.62)
make_mat('Ninja_PropMark', (0.8, 0.76, 0.72), rough=0.6)
make_mat('Ninja_EyeWhite', (0.96, 0.96, 0.94), rough=0.25)
make_mat('Ninja_Pupil', (0.015, 0.015, 0.02), rough=0.18)
make_mat('Ninja_Mouth', (0.33, 0.11, 0.09), rough=0.6)
make_mat('Ninja_Metal', (0.62, 0.62, 0.64), rough=0.32, metal=1.0)
make_mat('Ninja_Blade', (0.82, 0.83, 0.85), rough=0.18, metal=1.0)

# ----------------------------------------------------------------------------------------------
# mesh building helpers
# ----------------------------------------------------------------------------------------------
class Part:
    """bmesh accumulator for one named object; faces carry material names"""
    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.mat_names = []
    def mi(self, name):
        if name not in self.mat_names:
            self.mat_names.append(name)
        return self.mat_names.index(name)
    def face(self, verts, uvs, mat, smooth=True):
        try:
            f = self.bm.faces.new(verts)
        except ValueError:
            return None
        f.material_index = self.mi(mat)
        f.smooth = smooth
        for loop, uv in zip(f.loops, uvs):
            loop[self.uv].uv = uv
        return f

PARTS = {}
def part(name):
    if name not in PARTS:
        PARTS[name] = Part()
    return PARTS[name]

def loft(p, rings, mat, cap0='pole', cap1='pole', closed=False, density=8.0, smooth=True, pole0=None, pole1=None):
    """rings of equal point count -> quad strip (closed = the last ring connects to the first)"""
    bm = p.bm
    nr, ns = len(rings), len(rings[0])
    V = [[bm.verts.new(pt) for pt in ring] for ring in rings]
    circ = sum(sum((Vector(r[(k + 1) % ns]) - Vector(r[k])).length for k in range(ns)) for r in rings) / nr
    cen = [sum((Vector(q) for q in r), Vector()) / ns for r in rings]
    vs = [0.0]
    for i in range(1, nr):
        vs.append(vs[-1] + max((cen[i] - cen[i - 1]).length, 0.002))
    vend = vs[-1] + (cen[0] - cen[-1]).length
    U = lambda k: k / ns * circ * density
    for i in range(nr - 1 + (1 if closed else 0)):
        i2 = (i + 1) % nr
        v0, v1 = vs[i] * density, (vs[i2] if i2 else vend) * density
        for k in range(ns):
            k2 = (k + 1) % ns
            p.face([V[i][k], V[i][k2], V[i2][k2], V[i2][k]], [(U(k), v0), (U(k + 1), v0), (U(k + 1), v1), (U(k), v1)], mat, smooth)
    def cap(ring_i, mode, pole, vv):
        if mode is None:
            return
        ring = V[ring_i]
        c = cen[ring_i]
        if mode == 'pole' and pole is not None:
            c = Vector(pole)
        pv = bm.verts.new(c)
        for k in range(ns):
            k2 = (k + 1) % ns
            p.face([ring[k], ring[k2], pv], [(U(k), vv), (U(k + 1), vv), (U(k + 0.5), vv + 0.05)], mat, smooth)
    if not closed:
        cap(0, cap0, pole0, 0.0)
        cap(nr - 1, cap1, pole1, vs[-1] * density)
    return V

def ellipse_ring(c, A, B, ra, rb, ns, phase=0.0):
    c, A, B = Vector(c), Vector(A).normalized(), Vector(B).normalized()
    return [c + A * (ra * math.cos(phase + 2 * math.pi * k / ns)) + B * (rb * math.sin(phase + 2 * math.pi * k / ns)) for k in range(ns)]

def path_frames(pts, hint):
    """tangent + two perpendicular axes for each point (A follows the hint)"""
    pts = [Vector(q) for q in pts]
    out = []
    for i, q in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        h = Vector(hint)
        A = (h - t * h.dot(t))
        if A.length < 1e-5:
            A = t.orthogonal()
        A.normalize()
        B = t.cross(A).normalized()
        out.append((q, t, A, B))
    return out

def tube(p, pts, radii, mat, ns=14, hint=(0, -1, 0), cap0='pole', cap1='pole', ext=0.6, density=8.0, radii_b=None):
    fr = path_frames(pts, hint)
    rings = []
    for i, (q, t, A, B) in enumerate(fr):
        rings.append(ellipse_ring(q, A, B, radii[i], radii_b[i] if radii_b else radii[i], ns))
    q0, t0 = fr[0][0], fr[0][1]
    q1, t1 = fr[-1][0], fr[-1][1]
    return loft(p, rings, mat, cap0, cap1, density=density,
                pole0=q0 - t0 * radii[0] * ext, pole1=q1 + t1 * radii[-1] * ext)

def ring_tube(p, center_pts, tube_a, tube_b, mat, ns=8, up=None):
    """closed tube along a closed loop of points (bands, cuffs, scarf)"""
    n = len(center_pts)
    pts = [Vector(q) for q in center_pts]
    c = sum(pts, Vector()) / n
    rings = []
    for k in range(n):
        t = (pts[(k + 1) % n] - pts[k - 1]).normalized()
        A = (pts[k] - c)
        if up is not None:
            A = Vector(up)
        A = (A - t * A.dot(t)).normalized()
        B = t.cross(A).normalized()
        ta = tube_a[k] if isinstance(tube_a, (list, tuple)) else tube_a
        tb = tube_b[k] if isinstance(tube_b, (list, tuple)) else tube_b
        rings.append(ellipse_ring(pts[k], A, B, ta, tb, ns))
    return loft(p, rings, mat, closed=True)

def ellipsoid(p, c, r, mat, ns=16, nz=10, axes=None, density=8.0, smooth=True):
    c = Vector(c)
    X, Y, Z = [Vector(a).normalized() for a in axes] if axes else (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
    rings = []
    for i in range(1, nz):
        th = math.pi * i / nz
        z = -math.cos(th)
        s = math.sin(th)
        rings.append([c + X * (r[0] * s * math.cos(2 * math.pi * k / ns)) + Y * (r[1] * s * math.sin(2 * math.pi * k / ns)) + Z * (r[2] * z) for k in range(ns)])
    return loft(p, rings, mat, 'pole', 'pole', density=density, smooth=smooth, pole0=c - Z * r[2], pole1=c + Z * r[2])

def ribbon(p, pts, normals, width, thick, mat, closed=False, density=8.0, vertical=False):
    """flat strap / seam lying on a surface: rectangular cross-section, U along the path, V across.
    vertical=True: the band's width runs along +Z (belt) instead of tangent x normal"""
    n = len(pts)
    pts = [Vector(q) for q in pts]
    normals = [Vector(q).normalized() for q in normals]
    bm = p.bm
    rings = []
    for i in range(n):
        if closed:
            t = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        else:
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        N = normals[i]
        S = Vector((0, 0, 1)) if vertical else t.cross(N).normalized()
        q = pts[i]
        rings.append([q - S * width / 2, q + S * width / 2, q + S * width / 2 + N * thick, q - S * width / 2 + N * thick])
    V = [[bm.verts.new(c) for c in r] for r in rings]
    L = [0.0]
    for i in range(1, n):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    L.append(L[-1] + (pts[0] - pts[-1]).length)
    segs = n if closed else n - 1
    for i in range(segs):
        i2 = (i + 1) % n
        u0, u1 = L[i] * density, L[i + 1] * density
        p.face([V[i][3], V[i][2], V[i2][2], V[i2][3]], [(u0, 0), (u0, 1), (u1, 1), (u1, 0)], mat)  # outer face
        p.face([V[i][0], V[i][1], V[i2][1], V[i2][0]], [(u0, 0), (u0, 1), (u1, 1), (u1, 0)], mat)
        p.face([V[i][1], V[i][2], V[i2][2], V[i2][1]], [(u0, 0.95), (u0, 1), (u1, 1), (u1, 0.95)], mat)
        p.face([V[i][3], V[i][0], V[i2][0], V[i2][3]], [(u0, 0), (u0, 0.05), (u1, 0.05), (u1, 0)], mat)
    if not closed:
        for r in (V[0], V[-1]):
            p.face(r, [(0, 0), (0, 1), (0.05, 1), (0.05, 0)], mat)

def box(p, c, axes, half, mat, bevel=0.0, smooth=False):
    c = Vector(c)
    X, Y, Z = [Vector(a).normalized() for a in axes]
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=2.0)
    if bevel > 0:
        bmesh.ops.bevel(tmp, geom=tmp.edges[:] + tmp.verts[:], offset=min(0.9, bevel / min(half)), segments=2, affect='EDGES', profile=0.5)
    vm = {}
    for v in tmp.verts:
        vm[v] = p.bm.verts.new(c + X * (v.co.x * half[0]) + Y * (v.co.y * half[1]) + Z * (v.co.z * half[2]))
    for f in tmp.faces:
        n = f.normal
        uvs = []
        for v in f.verts:
            co = v.co
            if abs(n.x) > 0.5: uvs.append((co.y * half[1] * 8, co.z * half[2] * 8))
            elif abs(n.y) > 0.5: uvs.append((co.x * half[0] * 8, co.z * half[2] * 8))
            else: uvs.append((co.x * half[0] * 8, co.y * half[1] * 8))
        p.face([vm[v] for v in f.verts], uvs, mat, smooth)
    tmp.free()

def frame_rect(p, c, X, Y, N, w, h, bar, depth, mat):
    """metal buckle: rectangular ring in the plane X/Y, thickness along N"""
    c, X, Y, N = Vector(c), Vector(X).normalized(), Vector(Y).normalized(), Vector(N).normalized()
    outer = [(-w, -h), (w, -h), (w, h), (-w, h)]
    inner = [(-w + bar, -h + bar), (w - bar, -h + bar), (w - bar, h - bar), (-w + bar, h - bar)]
    def V(q, d):
        return p.bm.verts.new(c + X * q[0] + Y * q[1] + N * d)
    of, inf = [V(q, depth) for q in outer], [V(q, depth) for q in inner]
    ob, ib = [V(q, 0) for q in outer], [V(q, 0) for q in inner]
    uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for k in range(4):
        k2 = (k + 1) % 4
        p.face([of[k], of[k2], inf[k2], inf[k]], uv, mat, False)
        p.face([ob[k2], ob[k], ib[k], ib[k2]], uv, mat, False)
        p.face([ob[k], ob[k2], of[k2], of[k]], uv, mat, False)
        p.face([ib[k2], ib[k], inf[k], inf[k2]], uv, mat, False)

# ----------------------------------------------------------------------------------------------
# proportions (chibi, ~2.1 heads: hood + head are about half the height). x = character's left,
# -y = front, z = up
# ----------------------------------------------------------------------------------------------
HEAD_C = Vector((0, 0, 0.712)); HEAD_R = Vector((0.19, 0.176, 0.182))
ARM_ANG = math.radians(40)          # A-pose: arms 40 deg below horizontal
SH = {s: Vector((0.118 * s, 0.0, 0.462)) for s in (1, -1)}
def arm_dir(s):
    return Vector((math.cos(ARM_ANG) * s, 0.0, -math.sin(ARM_ANG)))
ELB = {s: SH[s] + arm_dir(s) * 0.095 for s in (1, -1)}
WRI = {s: ELB[s] + arm_dir(s) * 0.082 for s in (1, -1)}
HTIP = {s: WRI[s] + arm_dir(s) * 0.066 for s in (1, -1)}
HIPJ = {s: Vector((0.064 * s, 0.0, 0.272)) for s in (1, -1)}
KNEE = {s: Vector((0.068 * s, -0.005, 0.178)) for s in (1, -1)}
ANK = {s: Vector((0.07 * s, 0.0, 0.098)) for s in (1, -1)}
TOE = {s: Vector((0.072 * s, -0.105, 0.03)) for s in (1, -1)}

def lerp(a, b, t):
    return a + (b - a) * t

def smooth01(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def head_surface(direction, off=0.0):
    """point on the head ellipsoid along a direction from HEAD_C"""
    d = Vector(direction).normalized()
    k = 1.0 / math.sqrt((d.x / HEAD_R.x) ** 2 + (d.y / HEAD_R.y) ** 2 + (d.z / HEAD_R.z) ** 2)
    return HEAD_C + d * (k + off)

def face_dir(u, v):
    """u: horizontal angle (rad, + = character's left), v: vertical angle (rad, + = up), 0,0 = straight ahead (-y)"""
    return Vector((math.sin(u) * math.cos(v), -math.cos(u) * math.cos(v), math.sin(v)))

def grid_surface(p, G, mat, wrap=False, density=8.0, skip=None, smooth=True):
    """G[r][c] points (rows run top -> bottom); quads between neighbours; wrap closes the columns.
    UVs follow arc length so the fabric texture keeps its scale."""
    bm = p.bm
    R, C = len(G), len(G[0])
    G = [[Vector(q) for q in row] for row in G]
    V = [[bm.verts.new(q) for q in row] for row in G]
    us = []
    for row in G:
        acc = [0.0]
        for c in range(1, C + (1 if wrap else 0)):
            acc.append(acc[-1] + (row[c % C] - row[c - 1]).length)
        us.append(acc)
    vs = [[0.0] * C]
    for r in range(1, R):
        vs.append([vs[-1][c] + (G[r][c] - G[r - 1][c]).length for c in range(C)])
    for r in range(R - 1):
        for c in range(C - (0 if wrap else 1)):
            c2 = (c + 1) % C
            if skip and (r, c) in skip:
                continue
            uv = [(us[r][c] * density, -vs[r][c] * density), (us[r + 1][c] * density, -vs[r + 1][c] * density),
                  (us[r + 1][c + 1] * density, -vs[r + 1][c2] * density), (us[r][c + 1] * density, -vs[r][c2] * density)]
            p.face([V[r][c], V[r + 1][c], V[r + 1][c2], V[r][c2]], uv, mat, smooth)
    return V

def cut_and_snap(params, holes, metric):
    """params[r][c] = (a, b) surface coordinates. holes: list of (a0, b0, ra, rb) ellipses in metric
    space. Faces whose centre falls inside a hole are skipped; the remaining vertices that lie inside
    are pushed onto the ellipse, so the holes / openings get smooth round outlines."""
    R, C = len(params), len(params[0])
    def rho(a, b, h):
        x, y = metric(a, b, h)
        return math.hypot(x, y)
    skip = set()
    for r in range(R - 1):
        for c in range(C - 1):
            a = sum(params[r + i][c + j][0] for i in (0, 1) for j in (0, 1)) / 4
            b = sum(params[r + i][c + j][1] for i in (0, 1) for j in (0, 1)) / 4
            if any(rho(a, b, h) < 1.0 for h in holes):
                skip.add((r, c))
    out = [list(row) for row in params]
    for r in range(R):
        for c in range(C):
            a, b = params[r][c]
            for h in holes:
                k = rho(a, b, h)
                if 1e-6 < k < 1.0:
                    a0, b0 = h[0], h[1]
                    a, b = a0 + (a - a0) / k, b0 + (b - b0) / k
            out[r][c] = (a, b)
    return out, skip

# ---------------- Body: torso, arms, legs (the dark jumpsuit) ----------------
P = part('Ninja_Body')
torso = [(0.235, 0.098, 0.084), (0.265, 0.108, 0.092), (0.31, 0.114, 0.096), (0.36, 0.118, 0.098),
         (0.41, 0.122, 0.1), (0.445, 0.116, 0.095), (0.47, 0.088, 0.074), (0.495, 0.056, 0.05), (0.545, 0.05, 0.047)]
rings = [ellipse_ring((0, 0, z), (1, 0, 0), (0, 1, 0), rx, ry, 24) for z, rx, ry in torso]
loft(P, rings, 'Ninja_Cloth', 'pole', 'pole', pole0=(0, 0, 0.222), pole1=(0, 0, 0.555))
for s in (1, -1):
    sh_in = SH[s] - Vector((0.03 * s, 0, -0.005))
    pts = [sh_in, lerp(SH[s], ELB[s], 0.35), ELB[s], lerp(ELB[s], WRI[s], 0.5), WRI[s]]
    tube(P, pts, [0.045, 0.043, 0.039, 0.036, 0.033], 'Ninja_Cloth', ns=12, hint=(0, -1, 0))
    pts = [HIPJ[s] + Vector((0, 0, 0.03)), HIPJ[s], lerp(HIPJ[s], KNEE[s], 0.5), KNEE[s], lerp(KNEE[s], ANK[s], 0.5), ANK[s]]
    tube(P, pts, [0.058, 0.061, 0.059, 0.054, 0.05, 0.046], 'Ninja_Cloth', ns=14, hint=(0, -1, 0))

# ---------------- Face: black mask over the upper face, peach skin only around nose + mouth ----------------
P = part('Ninja_Face')
NS_H, NZ_H = 40, 24
SKIN_V, SKIN_U = math.radians(-15.0), math.radians(40)
face_rings = []
for i in range(1, NZ_H):
    th = math.pi * i / NZ_H
    ring = []
    for k in range(NS_H):
        ph = 2 * math.pi * k / NS_H
        d = Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)))
        ring.append(head_surface(d))
    face_rings.append(ring)
loft(P, face_rings, 'Ninja_Mask', 'pole', 'pole', pole0=HEAD_C - Vector((0, 0, HEAD_R.z)), pole1=HEAD_C + Vector((0, 0, HEAD_R.z)))
for f in P.bm.faces:
    d = (f.calc_center_median() - HEAD_C).normalized()
    u = math.atan2(d.x, -d.y); v = math.asin(max(-1, min(1, d.z)))
    if v < SKIN_V and abs(u) < SKIN_U and v > math.radians(-62):
        f.material_index = P.mi('Ninja_Skin')
# round nose poking out under the mask edge, soft cheeks, a small crooked mouth
ellipsoid(P, head_surface(face_dir(0, math.radians(-11)), -0.004), (0.024, 0.02, 0.019), 'Ninja_Skin', ns=14, nz=9)
for s in (1, -1):
    ellipsoid(P, head_surface(face_dir(s * math.radians(24), math.radians(-21)), -0.02), (0.032, 0.024, 0.024), 'Ninja_Skin', ns=10, nz=7)
mouth = []
for k in range(9):
    t = k / 8 * 2 - 1
    mouth.append(head_surface(face_dir(math.radians(15) * t, math.radians(-25 + 3.0 * t * t - 2.2 * t + 1.1 * math.sin(t * 3.1))), 0.0005))
tube(P, mouth, [0.0026, 0.0032, 0.0036, 0.0038, 0.0038, 0.0036, 0.0033, 0.003, 0.0024], 'Ninja_Mouth', ns=6, hint=(0, -1, 0))

# ---------------- Eyes: big whites with an angry slanted lid, big pupils, highlights, heavy brows ----------------
P = part('Ninja_Eyes')
def surface_disc(p, outline_uv, centre_uv, off, mat, thick=0.003):
    """outline in face angles (u, v) -> fan polygon lying on the head surface (+thickness)"""
    bm = p.bm
    top = [bm.verts.new(head_surface(face_dir(u, v), off + thick)) for u, v in outline_uv]
    bot = [bm.verts.new(head_surface(face_dir(u, v), off)) for u, v in outline_uv]
    ct = bm.verts.new(head_surface(face_dir(*centre_uv), off + thick * 1.6))
    cb = bm.verts.new(head_surface(face_dir(*centre_uv), off))
    n = len(top)
    for k in range(n):
        k2 = (k + 1) % n
        uv = [(outline_uv[k][0], outline_uv[k][1]), (outline_uv[k2][0], outline_uv[k2][1]), centre_uv]
        p.face([top[k], top[k2], ct], uv, mat)
        p.face([bot[k2], bot[k], cb], uv, mat)
        p.face([bot[k], bot[k2], top[k2], top[k]], uv[:2] + [uv[1], uv[0]], mat)
for s in (1, -1):
    cu, cvv = s * math.radians(23), math.radians(7.5)
    ru, rv = math.radians(17), math.radians(12)
    def lid(u):
        # angry lid: the upper edge slants down toward the nose
        return cvv + rv * 0.62 - (1 - (u - cu) / ru * s) * rv * 0.55
    pts = []
    for k in range(32):
        a = 2 * math.pi * k / 32
        u, v = cu + ru * math.cos(a), cvv + rv * math.sin(a)
        pts.append((u, min(v, lid(u))))
    surface_disc(P, pts, (cu, cvv - rv * 0.2), 0.0015, 'Ninja_EyeWhite')
    pu, pv = cu - s * math.radians(4.5), cvv - math.radians(2.0)
    pr = math.radians(7.2)
    ppts = []
    for k in range(22):
        a = 2 * math.pi * k / 22
        u, v = pu + pr * math.cos(a), pv + pr * 1.1 * math.sin(a)
        u = max(cu - ru * 0.92, min(cu + ru * 0.92, u))
        ppts.append((u, max(cvv - rv * 0.9, min(v, lid(u) - math.radians(0.6)))))
    surface_disc(P, ppts, (pu, pv), 0.0045, 'Ninja_Pupil', 0.002)
    hu, hv_, hr = pu + s * math.radians(2.0), pv + math.radians(2.2), math.radians(1.9)
    surface_disc(P, [(hu + hr * math.cos(2 * math.pi * k / 10), hv_ + hr * math.sin(2 * math.pi * k / 10)) for k in range(10)],
                 (hu, hv_), 0.0068, 'Ninja_EyeWhite', 0.0015)
    # thick angry brow over the slanted lid
    bpts = []
    for k in range(11):
        u = cu - ru * 1.12 + 2.24 * ru * k / 10
        bpts.append(head_surface(face_dir(u, lid(u) + math.radians(3.2)), 0.003))
    tube(P, bpts, [0.006, 0.008, 0.0095, 0.0105, 0.011, 0.011, 0.0105, 0.0095, 0.008, 0.0065, 0.005], 'Ninja_Pupil',
         ns=8, hint=(0, 0, 1), radii_b=[0.003, 0.004, 0.0045, 0.005, 0.005, 0.005, 0.005, 0.0045, 0.004, 0.0035, 0.003])

# ---------------- Hood: big soft dome, tip folding back, flat stitched centre seam, flared hem ----------------
P = part('Ninja_Hood')
HOOD_C = Vector((0, 0.03, 0.718)); HR = (0.262, 0.252, 0.226)
TIP = Vector((0, 0.6, 0.8)).normalized()
# soft creases on the cloth: (ph0, th0, ph1, th1) in degrees, depth (m, - = dent), width (deg)
CREASES = [(150, 150, 120, 95, -0.007, 9), (205, 155, 228, 100, -0.006, 8), (180, 120, 160, 70, 0.006, 10),
           (60, 140, 85, 95, -0.006, 9), (300, 140, 275, 96, -0.006, 9), (110, 75, 140, 45, 0.007, 9), (250, 75, 220, 45, 0.007, 9)]
def crease(th, ph):
    out = 0.0
    for p0, t0, p1, t1, amp, wd in CREASES:
        a = Vector((p0, t0)); b = Vector((p1, t1)); x = Vector((math.degrees(ph) % 360, math.degrees(th)))
        ab = b - a
        t = max(0.0, min(1.0, (x - a).dot(ab) / ab.length_squared))
        d = (x - (a + ab * t)).length
        out += 1.8 * amp * math.exp(-(d / wd) ** 2) * math.sin(math.pi * (0.15 + 0.7 * t))
    return out
TH0 = math.radians(50)               # hem (polar angle from the bottom)
NSEG, NLAT = 40, 18
def hood_pt(th, ph, off=0.0):
    """th: polar angle from the bottom (TH0 = hem, pi = top), ph: around (0 = front, + = character's left)"""
    # gumdrop profile: a dome on top, then the cloth keeps widening down to the hem (drapes over the shoulders)
    lowk = max(0.0, (math.radians(90) - th) / (math.radians(90) - TH0))
    rho = math.sin(th) if th >= math.radians(90) else 1 - 0.03 * lowk - 0.05 * lowk ** 4
    ry = HR[1] - 0.016 * math.cos(ph)            # roomier at the back
    tp = smooth01((th - math.radians(95)) / math.radians(75))   # narrower toward the top: soft gumdrop / onion dome
    q = HOOD_C + Vector((HR[0] * rho * math.sin(ph) * (1 - 0.2 * tp), -ry * rho * math.cos(ph) * (1 - 0.1 * tp),
                         -HR[2] * math.cos(th)))
    d = (q - HOOD_C).normalized()
    w = max(0.0, (d.dot(TIP) - 0.74) / 0.26)
    q = q + TIP * (0.06 * w * w)
    q.y += 0.045 * w ** 3
    q.z -= 0.03 * w ** 4
    hemw = max(0.0, 1 - (th - TH0) / math.radians(14))
    q.z += hemw * (0.012 * math.sin(3 * ph + 1.0) + 0.006 * math.sin(7 * ph))
    n = (q - HOOD_C).normalized()
    lo = max(0.0, (math.radians(95) - th) / (math.radians(95) - TH0))
    s = min(1.0, math.sin(th) * 3)
    wr = s * (0.0075 * math.sin(3 * ph + 2 * th) + 0.0055 * math.sin(5 * ph - 3 * th + 1.0)
              + 0.0035 * math.sin(8 * ph + 5 * th + 2.0)) + 0.011 * lo ** 1.5 * math.sin(9 * ph + 0.4)
    return q + n * (wr + crease(th, ph) * s + off)
# face opening: ellipse in (ph, th) around the front, it runs out through the hem
OPEN = (0.0, math.radians(73), math.radians(50), math.radians(39))
def hood_metric(ph, th, h):
    return ((ph - h[0]) / h[2], (th - h[1]) / h[3])
params = []
for i in range(NLAT):
    th = math.pi - (math.pi - TH0) * (i + 1) / NLAT
    params.append([(-math.pi + 2 * math.pi * c / NSEG, th) for c in range(NSEG + 1)])
params, skip = cut_and_snap(params, [OPEN], hood_metric)
G = [[hood_pt(th, ph) for ph, th in row] for row in params]
V = grid_surface(P, G, 'Ninja_Cloth', skip=skip)
# merge the duplicated back column (ph = -pi and +pi) and close the top with a pole
bmesh.ops.remove_doubles(P.bm, verts=[V[r][0] for r in range(NLAT)] + [V[r][NSEG] for r in range(NLAT)], dist=1e-5)
pole = P.bm.verts.new(hood_pt(math.pi, 0.0))
row0 = [V[0][k] if V[0][k].is_valid else V[0][NSEG] for k in range(NSEG)]
for k in range(len(row0)):
    P.face([row0[(k + 1) % len(row0)], row0[k], pole], [(k * 0.1, 0), ((k + 1) * 0.1, 0), (k * 0.1, 0.05)], 'Ninja_Cloth')
# rolled rim around the face opening (open curve: both ends tuck under the cowl)
rim = []
for k in range(41):
    a = math.radians(-58 + (238 + 58) * k / 40)
    ph, th = OPEN[2] * math.cos(a), OPEN[1] + OPEN[3] * math.sin(a)
    rim.append(hood_pt(max(th, TH0 + 0.02), ph, 0.004))
tube(P, rim, [0.012] * len(rim), 'Ninja_Cloth', ns=8, hint=(0, -1, 0), radii_b=[0.009] * len(rim))
# flat stitched centre seam from the front of the rim over the top and down the back
seam = [hood_pt(math.radians(t), 0.0, 0.0035) for t in range(116, 180, 4)] + [hood_pt(math.radians(t), math.pi, 0.0035) for t in range(178, 36, -4)]
ribbon(P, seam, [(q - HOOD_C).normalized() for q in seam], 0.008, 0.0006, 'Ninja_Seam', density=6)
# a few scuffs / scratches on the back of the hood
for th0, ph0, dth, dph in ((118, 162, 4, 3), (104, 205, -2, 4), (132, 196, 4, -1.5), (92, 150, 3, 2)):
    pts = [hood_pt(math.radians(th0 + dth * t), math.radians(ph0 + dph * t), 0.0066) for t in (0, 0.33, 0.66, 1.0)]
    ribbon(P, pts, [(q - HOOD_C).normalized() for q in pts], 0.0012, 0.0003, 'Ninja_Scuff')

# ---------------- Cowl: draped shoulder shawl under the hood, over the top of the cape ----------------
P = part('Ninja_Cowl')
NSC, NRC = 40, 8
G = []
for r in range(NRC):
    t = r / (NRC - 1)
    row = []
    for c in range(NSC):
        ph = 2 * math.pi * c / NSC
        back = max(0.0, -math.cos(ph)); frontv = max(0.0, math.cos(ph)) ** 6
        zh = 0.472 - 0.095 * back ** 1.2 + 0.0 * max(0.0, math.cos(ph)) ** 1.5 - 0.012 * math.sin(ph) + 0.006 * math.sin(4 * ph + 0.3)
        fr = max(0.0, math.cos(ph)) ** 2
        z = lerp(0.585 - 0.05 * fr, zh, t)
        e = 1 - (1 - t) ** 1.5
        rx, ry = lerp(0.225 - 0.1 * fr, 0.262, e), lerp(0.21 - 0.1 * fr, 0.24, e)
        f = 1 + t ** 1.4 * (0.07 * math.sin(5 * ph + 0.5) + 0.025 * math.sin(11 * ph + 1.3))
        row.append(Vector((rx * f * math.sin(ph), -ry * f * math.cos(ph), z)))
    G.append(row)
grid_surface(P, G, 'Ninja_Cloth', wrap=True)
hem = [lerp(G[-2][c], G[-1][c], 0.55) for c in range(NSC)]
hn = [Vector((q.x, q.y, 0)).normalized() for q in hem]
ribbon(P, [q + n * 0.0052 for q, n in zip(hem, hn)], hn, 0.011, 0.0012, 'Ninja_Seam', closed=True, density=6)
ring_tube(P, [G[-1][c] + Vector((0, 0, 0.002)) for c in range(NSC)], 0.0075, 0.0085, 'Ninja_Cloth', ns=6)   # rolled hem: reads thick

# ---------------- Cape: hangs from the left shoulder / back, flares out, ragged hem, round holes ----------------
P = part('Ninja_Cape')
CAPE_PH0, CAPE_PH1, CAPE_TOP = 48.0, 174.0, 0.44
NU, NV = 38, 19
rng = random.Random(11)
def cape_len(u):
    return lerp(0.31, 0.42, smooth01(u * 1.3))
def cape_pt(u, v, folds=True):
    ph = math.radians(lerp(CAPE_PH0, CAPE_PH1, u))
    e = max(0.0, v) ** 0.85
    R = lerp(0.14, 0.34, e)
    if folds:
        R *= 1 + e * (0.1 * math.sin(2 * math.pi * u * 4.2 + 0.7) + 0.035 * math.sin(2 * math.pi * u * 10.3 + 2.0))
    q = Vector((R * math.sin(ph), -0.9 * R * math.cos(ph), CAPE_TOP - v * cape_len(u)))
    q.x += 0.035 * e * (1 - u)       # the front edge swings out a little
    return q
# saw-tooth hem: alternating tips / notches at random spacing (+ a few deep tears)
teeth, u = [], 0.0
tip = True
while u < 1.06:
    teeth.append((u, rng.uniform(0.95, 1.0) if tip else (rng.uniform(0.6, 0.7) if rng.random() < 0.25 else rng.uniform(0.76, 0.88))))
    u += rng.uniform(0.04, 0.085); tip = not tip
def hem(u):
    for (u0, a), (u1, b) in zip(teeth, teeth[1:]):
        if u0 <= u <= u1:
            return lerp(a, b, (u - u0) / (u1 - u0))
    return teeth[-1][1]
colj = [rng.uniform(-0.02, 0.02) for _ in range(NU)]
params = [[(c / (NU - 1), r / (NV - 1) * (hem(c / (NU - 1)) + colj[c] * (r / (NV - 1)) ** 3)) for c in range(NU)] for r in range(NV)]
# ragged side edges near the bottom
for r in range(NV):
    t = r / (NV - 1)
    for c, sgn in ((0, 1), (NU - 1, -1)):
        u, v = params[r][c]
        params[r][c] = (u + sgn * max(0.0, t - 0.55) * 0.09 * (0.5 + 0.5 * math.sin(r * 2.7 + c)), v)
HOLES = [(0.16, 0.72, 0.026), (0.40, 0.62, 0.03), (0.66, 0.78, 0.025), (0.86, 0.56, 0.027), (0.55, 0.42, 0.016)]
def cape_metric(u, v, h):
    W = math.radians(CAPE_PH1 - CAPE_PH0) * lerp(0.14, 0.34, max(0.0, h[1]) ** 0.85)
    return ((u - h[0]) * W / h[2], (v - h[1]) * cape_len(h[0]) / h[2])
params, skip = cut_and_snap(params, [(a, b, r) for a, b, r in HOLES], cape_metric)
G = [[cape_pt(u, v) for u, v in row] for row in params]
grid_surface(P, G, 'Ninja_ClothDark', skip=skip)

# ---------------- Clothing: overlap edge, belt + rivets + pouches, back strap + buckle, wraps, guards ----------------
P = part('Ninja_Clothing')
def torso_r(z):
    for (z0, a0, b0), (z1, a1, b1) in zip(torso, torso[1:]):
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            return lerp(a0, a1, t), lerp(b0, b1, t)
    return torso[0][1], torso[0][2]
def torso_pt(a, z, off):
    rx, ry = torso_r(z)
    return Vector(((rx + off) * math.sin(a), -(ry + off) * math.cos(a), z)), Vector((math.sin(a) / rx, -math.cos(a) / ry, 0)).normalized()
# short coat hem below the belt (own object: Ninja_Tunic) with a stitched border
TUN = [(0.302, 0.121, 0.103), (0.276, 0.13, 0.111), (0.25, 0.141, 0.121), (0.226, 0.152, 0.131), (0.206, 0.16, 0.138)]
rings = [ellipse_ring((0, 0, z), (1, 0, 0), (0, 1, 0), rx, ry, 40) for z, rx, ry in TUN]
for i, ring in enumerate(rings):
    for k in range(40):
        a = 2 * math.pi * k / 40
        w = i / (len(rings) - 1)
        ring[k] = ring[k] + Vector((math.sin(a), -math.cos(a), 0)) * (0.006 * w * math.sin(5 * a + 0.8)) + Vector((0, 0, 0.005 * w * math.sin(3 * a + 0.2)))
loft(part('Ninja_Tunic'), rings, 'Ninja_Cloth', None, None)
hemp = [lerp(rings[-2][k], rings[-1][k], 0.72) for k in range(40)]
hemn = [Vector((math.sin(2 * math.pi * k / 40) / 0.16, -math.cos(2 * math.pi * k / 40) / 0.138, 0)).normalized() for k in range(40)]
ribbon(part('Ninja_Tunic'), [q + n * 0.0045 for q, n in zip(hemp, hemn)], hemn, 0.011, 0.0012, 'Ninja_Seam', closed=True, density=6)
# kimono overlap edge across the chest
pts, nrm = [], []
for k in range(10):
    t = k / 9
    q, n = torso_pt(math.radians(lerp(38, -24, t)), lerp(0.448, 0.305, t), 0.004)
    pts.append(q); nrm.append(n)
ribbon(P, pts, nrm, 0.016, 0.004, 'Ninja_Seam')
# belt + front buckle + rivets + a square loop plate on the back
BELT_Z = 0.292
brx, bry = [r + 0.012 for r in torso_r(BELT_Z)]
def belt_pt(a, off=0.0):
    return Vector(((brx + off) * math.sin(a), -(bry + off) * math.cos(a), BELT_Z)), Vector((math.sin(a) / brx, -math.cos(a) / bry, 0)).normalized()
pts, nrm = zip(*[belt_pt(2 * math.pi * k / 44) for k in range(44)])
ribbon(P, pts, nrm, 0.036, 0.008, 'Ninja_Strap', closed=True, vertical=True)
q, n = belt_pt(0.0, 0.008)
frame_rect(P, q, (1, 0, 0), (0, 0, 1), n, 0.021, 0.02, 0.006, 0.007, 'Ninja_Metal')
box(P, q + n * 0.004, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.003, 0.003, 0.018), 'Ninja_Metal')
for ang in (52, 122, 238, 300):
    q, n = belt_pt(math.radians(ang), 0.008)
    ellipsoid(P, q, (0.0045, 0.0045, 0.0045), 'Ninja_Metal', ns=8, nz=5)
q, n = belt_pt(math.radians(158), 0.008)
t = Vector((0, 0, 1)).cross(n).normalized()
box(P, q + n * 0.002, (t, n, (0, 0, 1)), (0.017, 0.004, 0.022), 'Ninja_LeatherBrown', bevel=0.003)
ellipsoid(P, q + n * 0.007, (0.0042, 0.0042, 0.0042), 'Ninja_Metal', ns=8, nz=5)
# diagonal strap: right shoulder -> across the back -> left hip, square buckle in the middle of the back
def strap_z(a):
    return 0.33 - 0.06 * math.sin(a) + 0.006 * math.cos(a)
pts, nrm = [], []
for k in range(48):
    a = 2 * math.pi * k / 48
    q, n = torso_pt(a, strap_z(a), 0.012)
    pts.append(q); nrm.append(n)
ribbon(P, pts, nrm, 0.03, 0.006, 'Ninja_Strap', closed=True)
ab = math.radians(192)
qb, nb = torso_pt(ab, strap_z(ab), 0.019)
tb = (torso_pt(ab + 0.05, strap_z(ab + 0.05), 0.019)[0] - torso_pt(ab - 0.05, strap_z(ab - 0.05), 0.019)[0]).normalized()
frame_rect(P, qb, tb, nb.cross(tb), nb, 0.022, 0.021, 0.0065, 0.008, 'Ninja_Metal')
box(P, qb + nb * 0.004, (tb, nb, nb.cross(tb)), (0.0028, 0.003, 0.02), 'Ninja_Metal')
# two tall pouches on the right hip, at the back
for ang in (213, 238):
    a = math.radians(ang)
    q, n = belt_pt(a, 0.0)
    t = Vector((0, 0, 1)).cross(n).normalized()
    c = q + n * 0.024 - Vector((0, 0, 0.016))
    box(P, c, (t, n, (0, 0, 1)), (0.021, 0.016, 0.031), 'Ninja_LeatherBrown', bevel=0.005)
    box(P, c + n * 0.003 + Vector((0, 0, 0.021)), (t, n, (0, 0, 1)), (0.023, 0.018, 0.013), 'Ninja_LeatherBrown', bevel=0.004)
    ellipsoid(P, c + n * 0.021 + Vector((0, 0, 0.012)), (0.0038, 0.0025, 0.0038), 'Ninja_Metal', ns=8, nz=5)
for s in (1, -1):
    # knee pads
    ellipsoid(P, KNEE[s] + Vector((0, -0.05, 0.006)), (0.036, 0.016, 0.04), 'Ninja_LeatherBlack', ns=14, nz=8,
              axes=((1, 0, 0), (0, 1, -0.15), (0, 0.15, 1)))
    # chunky horizontal wraps on the lower legs + a leather band on the boot top
    for i, z in enumerate((0.124, 0.145, 0.166, 0.186)):
        tilt = 0.005 * (1 if i % 2 else -1)
        rr = 0.054 - 0.002 * i
        loop = [Vector((ANK[s].x + rr * math.sin(a), -rr * math.cos(a), z + tilt * math.sin(a))) for a in [2 * math.pi * k / 14 for k in range(14)]]
        ring_tube(P, loop, 0.0095, 0.011, 'Ninja_ClothDark', ns=5)
    loop = [Vector((ANK[s].x + 0.059 * math.sin(a), -0.059 * math.cos(a), 0.108)) for a in [2 * math.pi * k / 18 for k in range(18)]]
    ring_tube(P, loop, 0.006, 0.009, 'Ninja_LeatherBrown', ns=6)
    # thick sleeve cuffs + forearm guards with brown bands
    d = arm_dir(s)
    A = Vector((0, -1, 0)); B = d.cross(A).normalized()
    ring_tube(P, ellipse_ring(lerp(ELB[s], WRI[s], 0.06), A, B, 0.046, 0.046, 16), 0.012, 0.013, 'Ninja_ClothDark', ns=8)
    g0, g1 = lerp(ELB[s], WRI[s], 0.16), WRI[s] + d * 0.006
    tube(P, [g0, lerp(g0, g1, 0.5), g1], [0.042, 0.042, 0.039], 'Ninja_LeatherBlack', ns=14, cap0=None, cap1=None)
    for t in (0.3, 0.78):
        c = lerp(g0, g1, t)
        ring_tube(P, ellipse_ring(c, A, B, 0.0435, 0.0435, 14), 0.004, 0.0065, 'Ninja_LeatherBrown', ns=6)

# ---------------- Gloves (chunky fists) ----------------
P = part('Ninja_Gloves')
HAND_C = {}
for s in (1, -1):
    A = arm_dir(s); Bf = Vector((0, -1, 0)); Cin = A.cross(Bf).normalized() * s
    hc = lerp(WRI[s], HTIP[s], 0.42)
    HAND_C[s] = (hc, A, Bf, Cin)
    ellipsoid(P, hc, (0.037, 0.034, 0.027), 'Ninja_LeatherBlack', ns=14, nz=8, axes=(A, Bf, Cin))
    for j, off in enumerate((-0.02, -0.0067, 0.0067, 0.02)):
        b = hc + A * 0.024 + Bf * off
        L = 1.0 - 0.1 * abs(j - 1.5)
        tube(P, [b, b + A * 0.017 * L, b + A * 0.022 * L + Cin * 0.015, b + A * 0.01 * L + Cin * 0.026],
             [0.0115, 0.011, 0.0105, 0.0095], 'Ninja_LeatherBlack', ns=8, hint=Cin)
    tb = hc + Bf * 0.029
    tube(P, [tb, tb + Bf * 0.013 + A * 0.013, tb + Bf * 0.007 + A * 0.028 + Cin * 0.013], [0.0125, 0.0115, 0.0105], 'Ninja_LeatherBlack', ns=8, hint=Cin)
    ring_tube(P, ellipse_ring(WRI[s] + A * 0.004, Bf, A.cross(Bf), 0.035, 0.035, 14), 0.006, 0.008, 'Ninja_LeatherBlack', ns=6)

# ---------------- Boots: chunky, rounded toe, thick layered sole with tread bars ----------------
P = part('Ninja_Boots')
AX = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
for s in (1, -1):
    x = ANK[s].x
    tube(P, [Vector((x, 0.004, 0.128)), Vector((x, 0.004, 0.096)), Vector((x, 0.006, 0.066))], [0.055, 0.054, 0.053], 'Ninja_LeatherBlack', ns=16, cap0=None, cap1=None)
    tube(P, [Vector((x, 0.044, 0.058)), Vector((x, 0.014, 0.064)), Vector((x, -0.045, 0.057)), Vector((x, -0.09, 0.047)), Vector((x, -0.113, 0.041))],
         [0.051, 0.055, 0.057, 0.051, 0.037], 'Ninja_LeatherBlack', ns=16, hint=(1, 0, 0), radii_b=[0.04, 0.046, 0.041, 0.033, 0.024], ext=0.75)
    ring_tube(P, ellipse_ring((x, 0.004, 0.128), (1, 0, 0), (0, 1, 0), 0.057, 0.057, 18), 0.009, 0.008, 'Ninja_LeatherBlack', ns=8)
    # sole: three stacked layers (horizontal ridges seen from behind) + tread bars underneath
    box(P, (x, -0.031, 0.0115), AX, (0.058, 0.09, 0.0075), 'Ninja_Sole', bevel=0.0055)
    box(P, (x, -0.031, 0.0215), AX, (0.0545, 0.0865, 0.0035), 'Ninja_Sole', bevel=0.002)
    box(P, (x, -0.031, 0.0295), AX, (0.057, 0.089, 0.0055), 'Ninja_Sole', bevel=0.004)
    for i in range(5):
        box(P, (x, 0.038 - i * 0.034, 0.0032), AX, (0.05 - 0.004 * (i == 4), 0.0105, 0.0032), 'Ninja_Sole', bevel=0.0018)
    box(P, (x, 0.036, 0.042), AX, (0.043, 0.013, 0.018), 'Ninja_LeatherBlack', bevel=0.006)

# ---------------- Optional accessories (hidden by default, never both equipped; both in the right hand) ----------------
hc, A, Bf, Cin = HAND_C[-1]
P = part('Acc_Dagger')   # right hand, blade forward
g = hc
tube(P, [g + Vector((0, 0.04, 0)), g, g + Vector((0, -0.038, 0))], [0.011, 0.0115, 0.011], 'Ninja_LeatherBlack', ns=10, hint=(0, 0, 1))
ellipsoid(P, g + Vector((0, 0.046, 0)), (0.015, 0.011, 0.015), 'Ninja_Metal', ns=10, nz=6)
box(P, g + Vector((0, -0.044, 0)), AX, (0.01, 0.0055, 0.029), 'Ninja_Metal', bevel=0.002)
tube(P, [g + Vector((0, -0.048, 0)), g + Vector((0, -0.11, 0.002)), g + Vector((0, -0.165, 0.013)), g + Vector((0, -0.19, 0.022))],
     [0.0038, 0.0032, 0.0024, 0.0006], 'Ninja_Blade', ns=8, hint=(1, 0, 0), radii_b=[0.018, 0.017, 0.011, 0.002], ext=0.2)
P = part('Acc_HandProp')  # right hand: a big foam hand on a stick, cheeky face drawn on the back of it
up = (-Cin).normalized()
side = Bf.cross(up).normalized()
back = -Bf
tube(P, [hc - up * 0.03, hc + up * 0.04, hc + up * 0.1], [0.0075, 0.0075, 0.0075], 'Ninja_PropRubber', ns=10, hint=back)
for t in (0.045, 0.085):
    ring_tube(P, ellipse_ring(hc + up * t, side, back, 0.0085, 0.0085, 10), 0.0022, 0.003, 'Ninja_Metal', ns=5)
tube(P, [hc + up * 0.095, hc + up * 0.115, hc + up * 0.13], [0.011, 0.016, 0.022], 'Ninja_PropRubber', ns=10, hint=back, radii_b=[0.011, 0.012, 0.013])
pc = hc + up * 0.17
ellipsoid(P, pc, (0.05, 0.014, 0.047), 'Ninja_PropRubber', ns=16, nz=10, axes=(side, back, up))
for j, o in enumerate((-0.033, -0.011, 0.011, 0.033)):
    ang = math.radians((j - 1.5) * 9)
    dr = up * math.cos(ang) + side * math.sin(ang)
    b = pc + up * 0.03 + side * o
    L = (0.048, 0.056, 0.054, 0.045)[j]
    tube(P, [b, b + dr * L * 0.5, b + dr * L], [0.0135, 0.013, 0.0125], 'Ninja_PropRubber', ns=10, hint=side, radii_b=[0.0115, 0.011, 0.0105], ext=0.9)
dth = (side * math.cos(math.radians(30)) + up * math.sin(math.radians(30))).normalized()
b = pc + side * 0.042 - up * 0.008
tube(P, [b, b + dth * 0.022, b + dth * 0.042], [0.0145, 0.0135, 0.0125], 'Ninja_PropRubber', ns=10, hint=side, radii_b=[0.0115, 0.011, 0.0105], ext=0.9)
# face marks: ">" "<" eyes and a tongue-out mouth, slightly raised on the back of the hand
fb = pc + back * 0.0145
def mark(pts, r=0.0026):
    tube(P, pts, [r] * len(pts), 'Ninja_PropMark', ns=6, hint=back)
for sg in (1, -1):
    e0 = fb + up * 0.012 + side * (0.02 * sg)
    mark([e0 + side * 0.008 * sg + up * 0.007, e0 - side * 0.004 * sg, e0 + side * 0.008 * sg - up * 0.007])
m0 = fb - up * 0.012
mark([m0 + side * (0.012 * math.cos(math.radians(a))) - up * (0.01 * math.sin(math.radians(a))) for a in range(0, 181, 30)])
mark([m0 - up * 0.004 + side * 0.004, m0 - up * 0.011 + side * 0.006, m0 - up * 0.004 + side * 0.008], 0.002)

# ----------------------------------------------------------------------------------------------
# objects (+ solidify for single-layer cloth) 
# ----------------------------------------------------------------------------------------------
coll = scene.collection
OBJ = {}
DECIMATE = {'Ninja_Clothing': 0.55, 'Ninja_Boots': 0.8}
SOLID = {'Ninja_Hood': 0.012, 'Ninja_Cowl': 0.009, 'Ninja_Cape': 0.008, 'Ninja_Tunic': 0.007}
for name, p in PARTS.items():
    if name == 'Acc_HandProp':   # read at game scale: the foam hand is a big, chunky prop
        for v in p.bm.verts:
            v.co = hc + (v.co - hc) * 1.5
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    me = bpy.data.meshes.new(name)
    p.bm.to_mesh(me)
    p.bm.free()
    for mn in p.mat_names:
        me.materials.append(MATS[mn])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    OBJ[name] = ob
    if name in SOLID:
        m = ob.modifiers.new('Solidify', 'SOLIDIFY')
        m.thickness = SOLID[name]; m.offset = 0.0; m.use_even_offset = True
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=m.name)
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(me); bm.free()
    if name in DECIMATE:   # trim dense straps / bands / soles to stay inside the ~25k tri budget
        m = ob.modifiers.new('Decimate', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'; m.ratio = DECIMATE[name]; m.use_collapse_triangulate = False
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=m.name)
        me.validate(clean_customdata=False)

# ----------------------------------------------------------------------------------------------
# armature
# ----------------------------------------------------------------------------------------------
arm = bpy.data.armatures.new('Ninja_Rig')
rig = bpy.data.objects.new('Ninja_Rig', arm)
coll.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
BONE_R = {}
def eb(name, h, t, parent=None, deform=True, r=0.05):
    b = arm.edit_bones.new(name)
    b.head, b.tail = Vector(h), Vector(t)
    b.use_deform = deform
    if parent:
        b.parent = arm.edit_bones[parent]
        b.use_connect = False
    BONE_R[name] = r
    return b
eb('root', (0, 0, 0), (0, 0, 0.08), deform=False)
eb('hips', (0, 0, 0.262), (0, 0, 0.33), 'root', r=0.10)
eb('spine', (0, 0, 0.33), (0, 0, 0.39), 'hips', r=0.11)
eb('chest', (0, 0, 0.39), (0, 0, 0.465), 'spine', r=0.11)
eb('neck', (0, 0, 0.465), (0, 0, 0.53), 'chest', r=0.06)
eb('head', (0, 0, 0.53), (0, 0, 0.98), 'neck', r=0.2)
for s, sd in ((1, 'L'), (-1, 'R')):
    eb('upper_arm.' + sd, SH[s], ELB[s], 'chest', r=0.04)
    eb('forearm.' + sd, ELB[s], WRI[s], 'upper_arm.' + sd, r=0.036)
    eb('hand.' + sd, WRI[s], HTIP[s], 'forearm.' + sd, r=0.035)
    eb('thigh.' + sd, HIPJ[s], KNEE[s], 'hips', r=0.055)
    eb('shin.' + sd, KNEE[s], ANK[s], 'thigh.' + sd, r=0.045)
    eb('foot.' + sd, ANK[s], TOE[s], 'shin.' + sd, r=0.045)
CAPE_COLS = {'L': 0.15, 'C': 0.5, 'R': 0.85}   # front-left edge, middle, back edge of the cape
for k, u in CAPE_COLS.items():
    ts = (0.0, 0.33, 0.66, 1.0)
    par = 'chest'
    for i in range(3):
        nm = 'cape_%s%d' % (k, i + 1)
        eb(nm, cape_pt(u, ts[i], False), cape_pt(u, ts[i + 1], False), par, r=0.08)
        par = nm
bpy.ops.object.mode_set(mode='OBJECT')
DEFORM = [b.name for b in arm.bones if b.use_deform]
SEG = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm.bones}

def seg_dist(q, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (q - a).dot(ab) / ab.length_squared))
    return (q - (a + ab * t)).length

def dist_weights(q, names, k=3):
    sc = sorted(((seg_dist(q, *SEG[n]) / BONE_R[n], n) for n in names))[:k]
    ws = [(1.0 / (d * d + 0.02) ** 2, n) for d, n in sc]
    tot = sum(w for w, _ in ws)
    return {n: w / tot for w, n in ws if w / tot > 0.01}

def side_of(x):
    return 'L' if x >= 0 else 'R'

GENERAL = ['hips', 'spine', 'chest', 'neck']
def weights_for(obname, q):
    x, y, z = q
    sd = side_of(x)
    if obname in ('Ninja_Face', 'Ninja_Eyes'):
        return {'head': 1.0}
    if obname == 'Acc_Dagger':
        return {'hand.R': 1.0}
    if obname == 'Acc_HandProp':
        return {'hand.R': 1.0}
    if obname == 'Ninja_Hood':
        if z > 0.6:
            return {'head': 1.0}
        f = max(0.0, min(1.0, (z - 0.5) / 0.1))
        return {'head': 0.35 + 0.65 * f, 'chest': 0.65 * (1 - f)} if f < 1 else {'head': 1.0}
    if obname == 'Ninja_Cowl':
        out = {'chest': 0.7, 'neck': 0.3} if z > 0.5 else {'chest': 1.0}
        wa = max(0.0, min(1.0, 1 - seg_dist(q, *SEG['upper_arm.' + sd]) / 0.075)) * 0.55
        out = {n: v * (1 - wa) for n, v in out.items()}
        if wa > 0:
            out['upper_arm.' + sd] = wa
        return out
    if obname == 'Ninja_Cape':
        f = max(0.0, min(1.0, 1 - (CAPE_TOP - z) / 0.06))
        w = dist_weights(q, [n for n in DEFORM if n.startswith('cape_')], 3)
        out = {n: v * (1 - f) for n, v in w.items()}
        out['chest'] = out.get('chest', 0) + f
        return out
    if obname == 'Ninja_Gloves':
        return dist_weights(q, ['hand.' + sd, 'forearm.' + sd], 2)
    if obname == 'Ninja_Boots':
        return dist_weights(q, ['foot.' + sd, 'shin.' + sd], 2)
    if obname == 'Ninja_Clothing' and z > 0.47 and abs(x) < 0.2:
        return {'chest': 0.6, 'neck': 0.4}
    if obname == 'Ninja_Tunic':
        return dist_weights(q, ['hips', 'spine', 'thigh.L', 'thigh.R'], 2) if z > 0.262 else \
            {**{n: v * 0.6 for n, v in dist_weights(q, ['thigh.' + sd], 1).items()}, 'hips': 0.4}
    names = GENERAL + [b + '.' + sd for b in ('upper_arm', 'forearm', 'hand', 'thigh', 'shin', 'foot')]
    return dist_weights(q, names, 3)

for name, ob in OBJ.items():
    groups = {n: ob.vertex_groups.new(name=n) for n in DEFORM}
    for v in ob.data.vertices:
        for n, w in weights_for(name, v.co).items():
            groups[n].add([v.index], w, 'REPLACE')
    for n, g in list(groups.items()):
        pass
    ob.parent = rig
    m = ob.modifiers.new('Armature', 'ARMATURE')
    m.object = rig
    if name.startswith('Acc_'):
        ob['optional_accessory'] = 'dagger' if 'Dagger' in name else 'handprop'
        ob.hide_render = True
        ob.hide_set(True)

# ----------------------------------------------------------------------------------------------
# animation: poses are rotations in armature axes (deg). +X swings a hanging limb back and leans
# the spine forward; +Y on upper_arm.L lowers the left arm (mirror for the right).
# ----------------------------------------------------------------------------------------------
def mirror_name(n):
    return n[:-2] + '.R' if n.endswith('.L') else n[:-2] + '.L' if n.endswith('.R') else \
        n.replace('cape_L', 'cape_X').replace('cape_R', 'cape_L').replace('cape_X', 'cape_R')
def mirror_pose(p):
    out = {}
    for n, v in p.items():
        if n.startswith('cape_'):
            out[n] = v          # the cape hangs on one side only: keep it as is
        elif n in ('lift', 'off'):
            out[n] = v if n == 'lift' else (-v[0], v[1], v[2])
        else:
            out[mirror_name(n)] = (v[0], -v[1], -v[2])
    return out
def merge(*ps):
    out = {}
    for p in ps:
        out.update(p)
    return out
def cape(a, b, c, sway=0.0, side=0.0):
    """a/b/c: swing back per bone level (deg), sway: twist, side: flare outward to the character's left"""
    out = {}
    for k, w in (('C', 0.0), ('L', 1.0), ('R', -1.0)):
        sk = side * (1.25 if k == 'L' else 1.0 if k == 'C' else 0.7)
        out['cape_%s1' % k] = (a, -sk * 0.35, sway * w * 0.5 + sway)
        out['cape_%s2' % k] = (b, -sk * 0.45, sway * 0.5)
        out['cape_%s3' % k] = (c, -sk * 0.35, sway * 0.3)
    return out

STAND = merge({'upper_arm.L': (0, 34, 0), 'upper_arm.R': (0, -34, 0), 'forearm.L': (-18, 0, 0), 'forearm.R': (-18, 0, 0),
               'thigh.L': (-8, -5, 0), 'thigh.R': (-8, 5, 0), 'shin.L': (15, 5, 0), 'shin.R': (15, -5, 0),
               'foot.L': (-7, 0, 0), 'foot.R': (-7, 0, 0), 'spine': (4, 0, 0), 'head': (-4, 0, 0)}, cape(4, 2, 2))
IDLE_B = merge(STAND, {'chest': (-2, 0, 0), 'upper_arm.L': (0, 37, 0), 'upper_arm.R': (0, -37, 0), 'head': (-6, 0, 0),
                       'thigh.L': (-11, -5, 0), 'thigh.R': (-11, 5, 0), 'shin.L': (20, 5, 0), 'shin.R': (20, -5, 0),
                       'foot.L': (-9, 0, 0), 'foot.R': (-9, 0, 0)}, cape(6, 4, 4, 2, 3))
RUN_BODY = {'spine': (14, 0, 0), 'chest': (8, 0, -6), 'hips': (0, 0, 6), 'head': (-20, 0, 6),
            'upper_arm.L': (68, 26, 0), 'upper_arm.R': (62, -26, 0), 'forearm.L': (12, 0, 0), 'forearm.R': (12, 0, 0)}
RUN_C = merge(RUN_BODY, {'thigh.L': (-48, 0, 0), 'shin.L': (22, 0, 0), 'foot.L': (-6, 0, 0),
                         'thigh.R': (32, 0, 0), 'shin.R': (58, 0, 0), 'foot.R': (22, 0, 0)}, cape(40, 18, 12, 4, 26))
RUN_P = merge(RUN_BODY, {'hips': (0, 0, 0), 'chest': (8, 0, 0), 'head': (-20, 0, 0),
                         'thigh.L': (-6, 0, 0), 'shin.L': (14, 0, 0), 'foot.L': (-8, 0, 0),
                         'thigh.R': (-38, 0, 0), 'shin.R': (104, 0, 0), 'foot.R': (12, 0, 0), 'lift': 0.022}, cape(46, 20, 14, 0, 30))
CROUCH = {'thigh.L': (-58, -4, 0), 'thigh.R': (-58, 4, 0), 'shin.L': (88, 0, 0), 'shin.R': (88, 0, 0), 'foot.L': (-30, 0, 0),
          'foot.R': (-30, 0, 0), 'spine': (26, 0, 0), 'chest': (6, 0, 0), 'head': (-26, 0, 0),
          'upper_arm.L': (55, 26, 0), 'upper_arm.R': (55, -26, 0), 'forearm.L': (10, 0, 0), 'forearm.R': (10, 0, 0)}
JUMP_UP = merge({'thigh.L': (-12, 0, 0), 'thigh.R': (-6, 0, 0), 'shin.L': (14, 0, 0), 'shin.R': (10, 0, 0), 'foot.L': (32, 0, 0),
                 'foot.R': (32, 0, 0), 'spine': (-4, 0, 0), 'head': (-6, 0, 0),
                 'upper_arm.L': (-140, 12, 0), 'upper_arm.R': (-140, -12, 0), 'forearm.L': (-12, 0, 0), 'forearm.R': (-12, 0, 0)}, cape(14, 6, 4, 0, 6))
JUMP_TUCK = merge({'thigh.L': (-72, -6, 0), 'thigh.R': (-34, 6, 0), 'shin.L': (104, 0, 0), 'shin.R': (64, 0, 0), 'foot.L': (12, 0, 0),
                   'foot.R': (22, 0, 0), 'spine': (10, 0, 0), 'head': (-12, 0, 0),
                   'upper_arm.L': (-40, -22, 0), 'upper_arm.R': (-40, 22, 0), 'forearm.L': (-30, 0, 0), 'forearm.R': (-30, 0, 0)}, cape(36, 14, 10, 0, 18))
FALL_A = merge({'thigh.L': (-36, -6, 0), 'thigh.R': (-10, 6, 0), 'shin.L': (52, 0, 0), 'shin.R': (28, 0, 0), 'foot.L': (20, 0, 0),
                'foot.R': (24, 0, 0), 'spine': (-5, 0, 0), 'head': (-10, 0, 0),
                'upper_arm.L': (-28, -55, 0), 'upper_arm.R': (-28, 55, 0), 'forearm.L': (-22, 0, 0), 'forearm.R': (-22, 0, 0)}, cape(72, 22, 16, -4, 10))
FALL_B = merge(FALL_A, {'thigh.L': (-26, -6, 0), 'thigh.R': (-20, 6, 0), 'shin.L': (40, 0, 0), 'shin.R': (40, 0, 0),
                        'upper_arm.L': (-32, -63, 0), 'upper_arm.R': (-32, 63, 0)}, cape(80, 28, 22, 4, 14))
LAND_IMPACT = merge(CROUCH, {'thigh.L': (-66, -6, 0), 'thigh.R': (-66, 6, 0), 'shin.L': (102, 0, 0), 'shin.R': (102, 0, 0),
                             'foot.L': (-36, 0, 0), 'foot.R': (-36, 0, 0), 'spine': (30, 0, 0), 'upper_arm.L': (42, 30, 0),
                             'upper_arm.R': (42, -30, 0)}, cape(20, 6, 6))
LAND_MID = merge(CROUCH, {'thigh.L': (-44, -4, 0), 'thigh.R': (-44, 4, 0), 'shin.L': (70, 0, 0), 'shin.R': (70, 0, 0),
                          'foot.L': (-25, 0, 0), 'foot.R': (-25, 0, 0), 'spine': (20, 0, 0)}, cape(30, 8, 8, 0, 8))
LAND_END = merge(RUN_BODY, {'hips': (0, 0, 0), 'chest': (8, 0, 0), 'head': (-20, 0, 0), 'thigh.L': (-14, -3, 0), 'thigh.R': (-10, 3, 0),
                            'shin.L': (24, 0, 0), 'shin.R': (20, 0, 0), 'foot.L': (-10, 0, 0), 'foot.R': (-10, 0, 0)}, cape(40, 10, 8, 0, 14))
SLIDE_A = merge({'thigh.L': (-86, -4, 0), 'shin.L': (6, 0, 0), 'foot.L': (24, 0, 0),
                 'thigh.R': (-34, 10, 0), 'shin.R': (122, 0, 0), 'foot.R': (22, 0, 0),
                 'spine': (-20, 0, 0), 'chest': (-6, 0, 0), 'head': (16, 0, 0),
                 'upper_arm.L': (-36, -28, 0), 'upper_arm.R': (40, 12, 0), 'forearm.L': (-24, 0, 0), 'forearm.R': (-10, 0, 0)}, cape(70, 16, 10, 3, 18))
SLIDE_B = merge(SLIDE_A, {'spine': (-23, 0, 0), 'head': (18, 0, 0), 'upper_arm.L': (-40, -32, 0)}, cape(77, 22, 16, -3, 24))

ACTIONS = [
    ('Idle', [(0, STAND), (24, IDLE_B), (48, STAND)]),
    ('Run', [(0, RUN_C), (4, RUN_P), (8, mirror_pose(RUN_C)), (12, mirror_pose(RUN_P)), (16, RUN_C)]),
    ('Jump', [(0, STAND), (4, CROUCH), (8, JUMP_UP), (14, JUMP_TUCK), (18, merge(JUMP_TUCK, cape(38, 14, 12, 0, 18)))]),
    ('Fall', [(0, FALL_A), (12, FALL_B), (24, FALL_A)]),
    ('Land', [(0, merge(FALL_A, {'thigh.L': (-15, -6, 0), 'thigh.R': (-12, 6, 0), 'shin.L': (16, 0, 0), 'shin.R': (14, 0, 0)})),
              (3, LAND_IMPACT), (9, LAND_MID), (20, LAND_END)]),
    ('Slide', [(0, SLIDE_A), (8, SLIDE_B), (16, SLIDE_A)]),
]

PB = rig.pose.bones
for pb in PB:
    pb.rotation_mode = 'QUATERNION'
def to_local(name, deg):
    R = Euler([math.radians(a) for a in deg], 'XYZ').to_matrix()
    M = arm.bones[name].matrix_local.to_3x3()
    return (M.inverted() @ R @ M).to_quaternion()
GROUND_OBJS = [OBJ[n] for n in ('Ninja_Body', 'Ninja_Boots', 'Ninja_Tunic', 'Ninja_Gloves')]
def lowest_z():
    dg = bpy.context.evaluated_depsgraph_get()
    lo = 1e9
    for ob in GROUND_OBJS:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        mw = np.array(ev.matrix_world)
        z = co @ mw[2, :3] + mw[2, 3]
        lo = min(lo, float(z.min()))
        ev.to_mesh_clear()
    return lo
REST_LOW = None
def apply_pose(pose):
    for pb in PB:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    for n, v in pose.items():
        if n in PB:
            PB[n].rotation_quaternion = to_local(n, v)
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
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, keys[-1][0]
    act.use_cyclic = name in ('Idle', 'Run', 'Fall', 'Slide')
    tr = rig.animation_data.nla_tracks.new()
    tr.name = name
    tr.strips.new(name, 0, act)
    tr.mute = True
    print('[ninja] action %-6s frames 0-%d  (%.2fs)' % (name, keys[-1][0], keys[-1][0] / FPS))
rig.animation_data.action = bpy.data.actions['Idle']
scene.frame_start, scene.frame_end = 0, 48
scene.frame_set(0)

# ----------------------------------------------------------------------------------------------
# report + save + export
# ----------------------------------------------------------------------------------------------
total = 0
for name, ob in OBJ.items():
    me = ob.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    total += tris
    bm = bmesh.new(); bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    bm.free()
    print('[ninja] %-16s verts %5d  tris %6d  non-manifold edges %4d  volume %+.5f  mats %s' %
          (name, len(me.vertices), tris, nm, vol, ','.join(m.name for m in me.materials)))
print('[ninja] TOTAL tris', total, ' (excl. accessories:', total - sum(sum(len(p.vertices) - 2 for p in OBJ[n].data.polygons) for n in OBJ if n.startswith('Acc_')), ')')
for img in bpy.data.images:
    print('[ninja] texture %-20s %dx%d packed=%s' % (img.name, img.size[0], img.size[1], bool(img.packed_file)))

bpy.ops.file.pack_all()
bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backup
os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
print('[ninja] saved', OUT_BLEND)

os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
for ob in bpy.data.objects:
    ob.hide_set(False)  # exporter: include hidden accessories (game hides them by name)
kw = dict(filepath=OUT_GLB, export_format='GLB', use_selection=False, use_visible=False, export_extras=True,
          export_yup=True, export_apply=False, export_animations=True, export_animation_mode='ACTIONS',
          export_force_sampling=True, export_frame_range=False, export_anim_slide_to_zero=True, export_skins=True,
          export_def_bones=False, export_all_influences=False, export_materials='EXPORT', export_image_format='JPEG', export_jpeg_quality=90,
          export_morph=False, export_reset_pose_bones=True)
while True:
    try:
        bpy.ops.export_scene.gltf(**kw)
        break
    except TypeError as e:
        bad = [k for k in kw if ('"%s"' % k) in str(e)]
        if not bad:
            raise
        print('[ninja] exporter: dropping unknown option', bad)
        for k in bad:
            kw.pop(k)
for ob in bpy.data.objects:
    if ob.name.startswith('Acc_'):
        ob.hide_set(True)
print('[ninja] exported', OUT_GLB, os.path.getsize(OUT_GLB), 'bytes')
