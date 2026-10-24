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
# ~1.02 m tall here; the game scales it (RENDER.ninja in src/config.ts). Feet rest on z = 0.
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

def fabric_textures(n=512, threads=32):
    y, x = np.mgrid[0:n, 0:n] / n * threads
    i, j = np.floor(x).astype(int), np.floor(y).astype(int)
    fu, fv = x - i, y - j
    warp_top = ((i + j) % 4) < 2  # 2/2 twill
    warp = np.sin(np.pi * fu) ** 0.6 * (0.55 + 0.45 * np.sin(np.pi * fv))
    weft = np.sin(np.pi * fv) ** 0.6 * (0.55 + 0.45 * np.sin(np.pi * fu))
    h = np.where(warp_top, warp, weft * 0.85)
    fib = periodic_noise(n, 90, 3)
    low = periodic_noise(n, 6, 4)
    h2 = h + 0.08 * fib
    alb = 0.86 + 0.08 * h + 0.04 * low + 0.015 * fib
    nrm = height_to_normal(h2, 2.2)
    rough = 0.80 + 0.08 * (1 - h) + 0.04 * low
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
    h = (np.sin(y * np.pi * 2 * 8) > 0.2).astype(float)  # tread bars
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
make_mat('Ninja_Cloth', (0.175, 0.168, 0.172), tex=fab_a, normal=fab_n, orm=fab_o, nstr=0.7)
make_mat('Ninja_ClothDark', (0.115, 0.108, 0.11), tex=fab_a, normal=fab_n, orm=fab_o, nstr=0.7)
make_mat('Ninja_Seam', (0.15, 0.14, 0.14), tex=se_a, normal=se_n, orm=se_o, nstr=0.8)
make_mat('Ninja_LeatherBrown', (0.20, 0.135, 0.095), tex=lea_a, normal=lea_n, orm=lea_o, nstr=0.6)
make_mat('Ninja_LeatherBlack', (0.105, 0.098, 0.098), tex=lea_a, normal=lea_n, orm=lea_o, nstr=0.6)
make_mat('Ninja_Strap', (0.19, 0.13, 0.09), tex=st_a, normal=st_n, orm=st_o, nstr=0.8)
make_mat('Ninja_Sole', (0.23, 0.16, 0.115), rough=0.85, normal=TEX['sole_n'], nstr=0.8)
make_mat('Ninja_Skin', (0.96, 0.64, 0.43), rough=0.55)
make_mat('Ninja_Mask', (0.06, 0.058, 0.065), rough=0.42)
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
# proportions (chibi: big head, short limbs). x = character's left, -y = front, z = up
# ----------------------------------------------------------------------------------------------
HEAD_C = Vector((0, 0, 0.77)); HEAD_R = Vector((0.185, 0.172, 0.185))
ARM_ANG = math.radians(40)          # A-pose: arms 40 deg below horizontal
SH = {s: Vector((0.125 * s, 0.0, 0.545)) for s in (1, -1)}
def arm_dir(s):
    return Vector((math.cos(ARM_ANG) * s, 0.0, -math.sin(ARM_ANG)))
ELB = {s: SH[s] + arm_dir(s) * 0.115 for s in (1, -1)}
WRI = {s: ELB[s] + arm_dir(s) * 0.10 for s in (1, -1)}
HTIP = {s: WRI[s] + arm_dir(s) * 0.07 for s in (1, -1)}
HIPJ = {s: Vector((0.07 * s, 0.0, 0.335)) for s in (1, -1)}
KNEE = {s: Vector((0.076 * s, -0.005, 0.222)) for s in (1, -1)}
ANK = {s: Vector((0.078 * s, 0.0, 0.12)) for s in (1, -1)}
TOE = {s: Vector((0.08 * s, -0.10, 0.03)) for s in (1, -1)}

def lerp(a, b, t):
    return a + (b - a) * t

def head_surface(direction, off=0.0):
    """point on the head ellipsoid along a direction from HEAD_C"""
    d = Vector(direction).normalized()
    k = 1.0 / math.sqrt((d.x / HEAD_R.x) ** 2 + (d.y / HEAD_R.y) ** 2 + (d.z / HEAD_R.z) ** 2)
    return HEAD_C + d * (k + off)

def face_dir(u, v):
    """u: horizontal angle (rad, + = character's left), v: vertical angle (rad, + = up), 0,0 = straight ahead (-y)"""
    return Vector((math.sin(u) * math.cos(v), -math.cos(u) * math.cos(v), math.sin(v)))

# ---------------- Body: torso, arms, legs (the dark jumpsuit) ----------------
P = part('Ninja_Body')
torso = [(0.30, 0.10, 0.082), (0.335, 0.108, 0.088), (0.39, 0.112, 0.088), (0.45, 0.12, 0.092),
         (0.51, 0.128, 0.095), (0.545, 0.118, 0.09), (0.57, 0.085, 0.07), (0.595, 0.055, 0.05), (0.64, 0.05, 0.047)]
rings = [ellipse_ring((0, 0, z), (1, 0, 0), (0, 1, 0), rx, ry, 24) for z, rx, ry in torso]
loft(P, rings, 'Ninja_Cloth', 'pole', 'pole', pole0=(0, 0, 0.285), pole1=(0, 0, 0.65))
for s in (1, -1):
    sh_in = SH[s] - Vector((0.03 * s, 0, -0.005))
    pts = [sh_in, lerp(SH[s], ELB[s], 0.35), ELB[s], lerp(ELB[s], WRI[s], 0.5), WRI[s]]
    tube(P, pts, [0.042, 0.04, 0.035, 0.033, 0.03], 'Ninja_Cloth', ns=12, hint=(0, -1, 0))
    pts = [HIPJ[s] + Vector((0, 0, 0.03)), HIPJ[s], lerp(HIPJ[s], KNEE[s], 0.5), KNEE[s], lerp(KNEE[s], ANK[s], 0.5), ANK[s]]
    tube(P, pts, [0.055, 0.058, 0.056, 0.05, 0.045, 0.04], 'Ninja_Cloth', ns=14, hint=(0, -1, 0))

# ---------------- Face: skin opening + dark under-mask, nose, mouth ----------------
P = part('Ninja_Face')
OPEN_U, OPEN_V0, OPEN_V1 = math.radians(64), math.radians(-30), math.radians(40)
def in_opening(d, margin=0.0):
    u = math.atan2(d.x, -d.y)
    v = math.asin(max(-1, min(1, d.z)))
    vc = (OPEN_V0 + OPEN_V1) / 2; vr = (OPEN_V1 - OPEN_V0) / 2
    return (u / (OPEN_U + margin)) ** 2 + ((v - vc) / (vr + margin)) ** 2 < 1.0
face_rings = []
NS_H, NZ_H = 40, 22
for i in range(1, NZ_H):
    th = math.pi * i / NZ_H
    ring = []
    for k in range(NS_H):
        ph = 2 * math.pi * k / NS_H
        d = Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)))
        ring.append(head_surface(d))
    face_rings.append(ring)
V = loft(P, face_rings, 'Ninja_Mask', 'pole', 'pole', pole0=HEAD_C - Vector((0, 0, HEAD_R.z)), pole1=HEAD_C + Vector((0, 0, HEAD_R.z)))
for f in P.bm.faces:
    c = f.calc_center_median() - HEAD_C
    if in_opening(c.normalized(), margin=0.06):
        f.material_index = P.mi('Ninja_Skin')
# nose: a soft bump; mouth: small flattened dark ellipsoid with a slight frown
nose = head_surface(face_dir(0, math.radians(-6)), -0.006)
ellipsoid(P, nose, (0.016, 0.014, 0.013), 'Ninja_Skin', ns=12, nz=8)
if True:
    mc = head_surface(face_dir(0, math.radians(-21)), -0.002)
    ellipsoid(P, mc, (0.026, 0.008, 0.0075), 'Ninja_Mouth', ns=14, nz=6,
              axes=((1, 0, 0), (0, 1, 0.25), (0, -0.25, 1)))
# cheeks: subtle volume
for s in (1, -1):
    ellipsoid(P, head_surface(face_dir(s * math.radians(32), math.radians(-15)), -0.02), (0.04, 0.03, 0.03), 'Ninja_Skin', ns=12, nz=8)

# ---------------- Eyes: whites with an angry slanted lid, pupils, highlights ----------------
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
    cu, cv = s * math.radians(21), math.radians(3)
    ru, rv = math.radians(13), math.radians(9.5)
    pts = []
    for k in range(28):
        a = 2 * math.pi * k / 28
        u, v = cu + ru * math.cos(a), cv + rv * math.sin(a)
        # angry lid: the upper edge slants down toward the nose
        lid = cv + rv * 0.55 - (1 - (u - cu) / ru * s) * rv * 0.5
        v = min(v, lid)
        pts.append((u, v))
    surface_disc(P, pts, (cu, cv - rv * 0.2), 0.0015, 'Ninja_EyeWhite')
    pu, pv = cu - s * math.radians(3.5), cv - math.radians(1.5)
    pr = math.radians(5.2)
    ppts = []
    for k in range(20):
        a = 2 * math.pi * k / 20
        u, v = pu + pr * math.cos(a), pv + pr * 1.12 * math.sin(a)
        lid = cv + rv * 0.55 - (1 - (u - cu) / ru * s) * rv * 0.5 - math.radians(0.6)
        ppts.append((u, min(v, lid)))
    surface_disc(P, ppts, (pu, pv), 0.0045, 'Ninja_Pupil', 0.002)
    hu, hv, hr = pu + s * math.radians(1.6), pv + math.radians(1.8), math.radians(1.5)
    surface_disc(P, [(hu + hr * math.cos(2 * math.pi * k / 10), hv + hr * math.sin(2 * math.pi * k / 10)) for k in range(10)],
                 (hu, hv), 0.0068, 'Ninja_EyeWhite', 0.0015)
    # dark brow ridge over the slanted lid (part of the hood/mask look)
    bpts = []
    for k in range(9):
        u = cu - ru * 1.05 + 2.1 * ru * k / 8
        lid = cv + rv * 0.55 - (1 - (u - cu) / ru * s) * rv * 0.5
        bpts.append(head_surface(face_dir(u, lid + math.radians(2.2)), 0.002))
    nrm = [(q - HEAD_C).normalized() for q in bpts]
    ribbon(P, bpts, nrm, 0.011, 0.004, 'Ninja_Mask')

# ---------------- Hood (with face opening, back peak, centre seam) ----------------
P = part('Ninja_Hood')
hood_prof = [(0.565, 0.165, 0.135), (0.598, 0.14, 0.118), (0.63, 0.152, 0.138), (0.66, 0.182, 0.168), (0.70, 0.2, 0.188),
             (0.74, 0.208, 0.196), (0.78, 0.21, 0.198), (0.82, 0.206, 0.194), (0.86, 0.192, 0.182), (0.895, 0.168, 0.16),
             (0.925, 0.134, 0.13), (0.948, 0.095, 0.094), (0.962, 0.058, 0.058), (0.97, 0.025, 0.025)]
NSEG = 48
def hood_pt(z, rx, ry, ph):
    q = Vector((rx * math.sin(ph), -ry * math.cos(ph), z))
    w = max(0.0, (z - 0.80) / 0.17) * max(0.0, -math.cos(ph))  # back peak
    q.y += 0.06 * w * w
    q.z += 0.035 * w * w
    return q
hv = [[P.bm.verts.new(hood_pt(z, rx, ry, 2 * math.pi * k / NSEG)) for k in range(NSEG)] for z, rx, ry in hood_prof]
top = P.bm.verts.new(hood_pt(0.975, 0.0, 0.0, math.pi))
top.co = hood_pt(0.975, 0.004, 0.004, math.pi)
def opening(q):
    d = (q - HEAD_C)
    return in_opening(d.normalized(), margin=0.0) and q.z > 0.645
for i in range(len(hv) - 1):
    for k in range(NSEG):
        k2 = (k + 1) % NSEG
        quad = [hv[i][k], hv[i][k2], hv[i + 1][k2], hv[i + 1][k]]
        c = sum((v.co for v in quad), Vector()) / 4
        if opening(c):
            continue
        P.face(quad, [(k / NSEG * 6, i / 13 * 4), ((k + 1) / NSEG * 6, i / 13 * 4), ((k + 1) / NSEG * 6, (i + 1) / 13 * 4), (k / NSEG * 6, (i + 1) / 13 * 4)], 'Ninja_Cloth')
for k in range(NSEG):
    k2 = (k + 1) % NSEG
    P.face([hv[-1][k], hv[-1][k2], top], [(k / NSEG * 6, 4), ((k + 1) / NSEG * 6, 4), (k / NSEG * 6, 4.1)], 'Ninja_Cloth')
# rolled rim around the face opening
rim = []
vc = (OPEN_V0 + OPEN_V1) / 2; vr = (OPEN_V1 - OPEN_V0) / 2
for k in range(36):
    a = 2 * math.pi * k / 36
    u, v = OPEN_U * 0.97 * math.cos(a), vc + vr * 0.97 * math.sin(a)
    q = head_surface(face_dir(u, v), 0.026)
    q.z = max(q.z, 0.655)
    rim.append(q)
ring_tube(P, rim, 0.013, 0.010, 'Ninja_ClothDark', ns=8)
# centre seam: over the top from the front rim down the back, plus a stitched welt
seam_pts, seam_n = [], []
for i in range(len(hood_prof) - 1, 0, -1):
    z, rx, ry = hood_prof[i]
    seam_pts.append(hood_pt(z, rx, ry, math.pi) + Vector((0, 0.006, 0)))
front = [hood_pt(z, rx, ry, 0.0) + Vector((0, -0.006, 0)) for z, rx, ry in hood_prof if z > 0.86]
seam_pts = front + seam_pts
for i, q in enumerate(seam_pts):
    seam_n.append(Vector((0, q.y, q.z - 0.77)).normalized())
ribbon(P, seam_pts, seam_n, 0.018, 0.003, 'Ninja_Seam', density=6)

# ---------------- Cape: torn, holed, folded; hangs behind ----------------
P = part('Ninja_Cape')
NC, NRW = 41, 19
rng = random.Random(11)
col_len = [1.0 - 0.09 * rng.random() for _ in range(NC)]
for centre, depth, half in ((7, 0.22, 3), (19, 0.17, 2), (30, 0.24, 3), (37, 0.12, 2)):
    for c in range(NC):
        d = abs(c - centre)
        if d <= half:
            col_len[c] -= depth * (1 - d / (half + 0.5))
CAPE_TOP, CAPE_BOT = 0.575, 0.085
cv = []
for r in range(NRW):
    t = r / (NRW - 1)
    row = []
    for c in range(NC):
        ph = math.radians(118 + (242 - 118) * c / (NC - 1))
        tl = t * col_len[c]
        z = lerp(CAPE_TOP, CAPE_BOT, tl)
        e = tl ** 0.8
        rx, ry = lerp(0.13, 0.25, e), lerp(0.122, 0.215, e)
        fold = 1 + 0.07 * e * math.sin(ph * 9 + 0.6) + 0.03 * e * math.sin(ph * 23)
        row.append(P.bm.verts.new(Vector((rx * fold * math.sin(ph), -ry * fold * math.cos(ph), z))))
    cv.append(row)
holes = set()
while len(holes) < 11:
    r, c = rng.randint(7, 16), rng.randint(2, NC - 4)
    if all(abs(r - a) + abs(c - b) > 3 for a, b in holes):
        holes.add((r, c))
skip = set()
for r, c in holes:
    skip |= {(r, c), (r, c + 1)} if rng.random() < 0.5 else {(r, c)}
for r in range(NRW - 1):
    for c in range(NC - 1):
        if (r, c) in skip:
            continue
        P.face([cv[r][c], cv[r + 1][c], cv[r + 1][c + 1], cv[r][c + 1]],
               [(c / 10, 4 - r / 5), (c / 10, 4 - (r + 1) / 5), ((c + 1) / 10, 4 - (r + 1) / 5), ((c + 1) / 10, 4 - r / 5)], 'Ninja_ClothDark')

# ---------------- Clothing: tunic skirt, collar, overlap, belt, strap, pouches, pads, wraps, guards ----------------
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
skirt = [(0.372, 0.118, 0.097), (0.335, 0.124, 0.104), (0.295, 0.137, 0.116), (0.258, 0.149, 0.126), (0.232, 0.156, 0.132)]
rings = [ellipse_ring((0, 0, z), (1, 0, 0), (0, 1, 0), rx, ry, 32) for z, rx, ry in skirt]
for k in range(32):
    rings[-1][k].z += 0.012 * math.sin(k * 2.3) + (0.01 if k % 5 == 0 else 0)
loft(part('Ninja_Tunic'), rings, 'Ninja_Cloth', None, None)
# collar where the hood meets the shoulders
ring_tube(P, ellipse_ring((0, 0, 0.574), (1, 0, 0), (0, 1, 0), 0.152, 0.13, 32), 0.024, 0.017, 'Ninja_ClothDark', ns=8)
# kimono overlap edge across the chest
pts, nrm = [], []
for k in range(10):
    t = k / 9
    q, n = torso_pt(math.radians(lerp(38, -24, t)), lerp(0.548, 0.375, t), 0.004)
    pts.append(q); nrm.append(n)
ribbon(P, pts, nrm, 0.016, 0.004, 'Ninja_Seam')
# belt + buckle
BELT_Z = 0.35
pts, nrm = [], []
for k in range(40):
    a = 2 * math.pi * k / 40
    pts.append(Vector((0.127 * math.sin(a), -0.106 * math.cos(a), BELT_Z)))
    nrm.append(Vector((math.sin(a) / 0.127, -math.cos(a) / 0.106, 0)).normalized())
ribbon(P, pts, nrm, 0.036, 0.008, 'Ninja_Strap', closed=True, vertical=True)
frame_rect(P, (0, -0.114, BELT_Z), (1, 0, 0), (0, 0, 1), (0, -1, 0), 0.02, 0.019, 0.006, 0.007, 'Ninja_Metal')
box(P, (0, -0.121, BELT_Z), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.003, 0.003, 0.017), 'Ninja_Metal')
# diagonal chest strap (left shoulder -> right hip), buckle on the back
pts, nrm = [], []
def strap_z(a):
    return 0.445 + 0.075 * math.sin(a) + 0.01 * math.cos(a)
for k in range(48):
    a = 2 * math.pi * k / 48
    q, n = torso_pt(a, strap_z(a), 0.012)
    pts.append(q); nrm.append(n)
ribbon(P, pts, nrm, 0.03, 0.006, 'Ninja_Strap', closed=True)
ab = math.radians(150)
qb, nb = torso_pt(ab, strap_z(ab), 0.019)
tb = (torso_pt(ab + 0.05, strap_z(ab + 0.05), 0.019)[0] - torso_pt(ab - 0.05, strap_z(ab - 0.05), 0.019)[0]).normalized()
frame_rect(P, qb, tb, nb.cross(tb), nb, 0.02, 0.021, 0.006, 0.007, 'Ninja_Metal')
# pouches on the belt (left, right, back-left)
for ang, sz in ((70, 1.0), (-72, 0.9), (200, 0.85)):
    a = math.radians(ang)
    n = Vector((math.sin(a) / 0.127, -math.cos(a) / 0.106, 0)).normalized()
    t = Vector((0, 0, 1)).cross(n).normalized()
    c = Vector((0.127 * math.sin(a), -0.106 * math.cos(a), BELT_Z - 0.012)) + n * 0.02 * sz
    box(P, c, (t, n, (0, 0, 1)), (0.03 * sz, 0.017 * sz, 0.032 * sz), 'Ninja_LeatherBrown', bevel=0.007)
    box(P, c + n * 0.003 + Vector((0, 0, 0.022 * sz)), (t, n, (0, 0, 1)), (0.032 * sz, 0.019 * sz, 0.012 * sz), 'Ninja_LeatherBlack', bevel=0.004)
    box(P, c + n * (0.022 * sz) + Vector((0, 0, 0.012 * sz)), (t, n, (0, 0, 1)), (0.005, 0.003, 0.005), 'Ninja_Metal')
for s in (1, -1):
    # knee pads
    ellipsoid(P, KNEE[s] + Vector((0, -0.045, 0.006)), (0.038, 0.016, 0.042), 'Ninja_LeatherBlack', ns=14, nz=8,
              axes=((1, 0, 0), (0, 1, -0.15), (0, 0.15, 1)))
    # shin wraps
    for i, z in enumerate((0.142, 0.168, 0.194)):
        tilt = 0.006 * (1 if i % 2 else -1)
        loop = [Vector((ANK[s].x + 0.047 * math.sin(a), -0.047 * math.cos(a), z + tilt * math.sin(a))) for a in [2 * math.pi * k / 16 for k in range(16)]]
        ring_tube(P, loop, 0.006, 0.009, 'Ninja_ClothDark', ns=6)
    # forearm guards with brown bands
    d = arm_dir(s)
    g0, g1 = lerp(ELB[s], WRI[s], 0.12), WRI[s] + d * 0.008
    tube(P, [g0, lerp(g0, g1, 0.5), g1], [0.039, 0.039, 0.036], 'Ninja_LeatherBlack', ns=14, cap0=None, cap1=None)
    for t in (0.3, 0.78):
        c = lerp(g0, g1, t)
        A = Vector((0, -1, 0)); B = d.cross(A).normalized()
        ring_tube(P, ellipse_ring(c, A, B, 0.041, 0.041, 14), 0.004, 0.0065, 'Ninja_LeatherBrown', ns=6)

# ---------------- Gloves ----------------
P = part('Ninja_Gloves')
HAND_C = {}
for s in (1, -1):
    A = arm_dir(s); Bf = Vector((0, -1, 0)); Cin = A.cross(Bf).normalized() * s
    hc = lerp(WRI[s], HTIP[s], 0.42)
    HAND_C[s] = (hc, A, Bf, Cin)
    ellipsoid(P, hc, (0.034, 0.03, 0.022), 'Ninja_LeatherBlack', ns=14, nz=8, axes=(A, Bf, Cin))
    for j, off in enumerate((-0.018, -0.006, 0.006, 0.018)):
        b = hc + A * 0.022 + Bf * off
        L = 1.0 - 0.1 * abs(j - 1.5)
        tube(P, [b, b + A * 0.016 * L, b + A * 0.021 * L + Cin * 0.014, b + A * 0.009 * L + Cin * 0.024],
             [0.0095, 0.009, 0.0085, 0.008], 'Ninja_LeatherBlack', ns=8, hint=Cin)
    tb = hc + Bf * 0.026 + A * 0.0
    tube(P, [tb, tb + Bf * 0.012 + A * 0.012, tb + Bf * 0.006 + A * 0.026 + Cin * 0.012], [0.011, 0.01, 0.009], 'Ninja_LeatherBlack', ns=8, hint=Cin)
    ring_tube(P, ellipse_ring(WRI[s] + A * 0.004, Bf, A.cross(Bf), 0.034, 0.034, 14), 0.005, 0.007, 'Ninja_LeatherBlack', ns=6)

# ---------------- Boots ----------------
P = part('Ninja_Boots')
for s in (1, -1):
    x = ANK[s].x
    tube(P, [Vector((x, 0.004, 0.158)), Vector((x, 0.004, 0.115)), Vector((x, 0.006, 0.07))], [0.05, 0.049, 0.048], 'Ninja_LeatherBlack', ns=16, cap0=None, cap1=None)
    tube(P, [Vector((x, 0.038, 0.05)), Vector((x, 0.01, 0.054)), Vector((x, -0.045, 0.046)), Vector((x, -0.088, 0.038)), Vector((x, -0.106, 0.033))],
         [0.046, 0.049, 0.05, 0.044, 0.032], 'Ninja_LeatherBlack', ns=16, hint=(1, 0, 0), radii_b=[0.036, 0.042, 0.036, 0.028, 0.02], ext=0.7)
    ring_tube(P, ellipse_ring((x, 0.004, 0.158), (1, 0, 0), (0, 1, 0), 0.052, 0.052, 18), 0.009, 0.007, 'Ninja_LeatherBlack', ns=8)
    box(P, (x, -0.033, 0.0105), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.05, 0.083, 0.0105), 'Ninja_Sole', bevel=0.006)
    box(P, (x, -0.031, 0.025), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.048, 0.079, 0.006), 'Ninja_LeatherBlack', bevel=0.003)
    box(P, (x, 0.033, 0.033), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.04, 0.012, 0.016), 'Ninja_LeatherBlack', bevel=0.005)

# ---------------- Optional accessories (hidden by default, never both equipped) ----------------
hc, A, Bf, Cin = HAND_C[-1]
P = part('Acc_Dagger')   # right hand, blade forward
g = hc + Cin * 0.0
tube(P, [g + Vector((0, 0.038, 0)), g, g + Vector((0, -0.036, 0))], [0.0105, 0.011, 0.0105], 'Ninja_LeatherBlack', ns=10, hint=(0, 0, 1))
ellipsoid(P, g + Vector((0, 0.043, 0)), (0.014, 0.01, 0.014), 'Ninja_Metal', ns=10, nz=6)
box(P, g + Vector((0, -0.042, 0)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.009, 0.005, 0.026), 'Ninja_Metal', bevel=0.002)
tube(P, [g + Vector((0, -0.046, 0)), g + Vector((0, -0.1, 0.002)), g + Vector((0, -0.15, 0.012)), g + Vector((0, -0.17, 0.02))],
     [0.0035, 0.003, 0.0022, 0.0006], 'Ninja_Blade', ns=8, hint=(1, 0, 0), radii_b=[0.016, 0.015, 0.01, 0.002], ext=0.2)
hc, A, Bf, Cin = HAND_C[1]
P = part('Acc_HandProp')  # left hand: a four-point throwing star held at the fingers
c = hc + A * 0.03 + Cin * 0.006 + Bf * 0.0
Nn = Cin; X1 = Bf; Y1 = Nn.cross(X1).normalized()
outline = []
for k in range(8):
    a = math.pi / 4 * k
    r = 0.048 if k % 2 == 0 else 0.013
    outline.append(c + X1 * (r * math.cos(a)) + Y1 * (r * math.sin(a)))
inner = [c + X1 * (0.007 * math.cos(math.pi / 4 * k)) + Y1 * (0.007 * math.sin(math.pi / 4 * k)) for k in range(8)]
bm = P.bm
T = [bm.verts.new(q + Nn * 0.002) for q in outline]; B = [bm.verts.new(q - Nn * 0.002) for q in outline]
Ti = [bm.verts.new(q + Nn * 0.003) for q in inner]; Bi = [bm.verts.new(q - Nn * 0.003) for q in inner]
for k in range(8):
    k2 = (k + 1) % 8
    uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    P.face([T[k], T[k2], Ti[k2], Ti[k]], uv, 'Ninja_Blade', False)
    P.face([B[k2], B[k], Bi[k], Bi[k2]], uv, 'Ninja_Blade', False)
    P.face([B[k], B[k2], T[k2], T[k]], uv, 'Ninja_Blade', False)
    P.face([Bi[k2], Bi[k], Ti[k], Ti[k2]], uv, 'Ninja_Metal', False)

# ----------------------------------------------------------------------------------------------
# objects (+ solidify for single-layer cloth) 
# ----------------------------------------------------------------------------------------------
coll = scene.collection
OBJ = {}
SOLID = {'Ninja_Hood': 0.012, 'Ninja_Cape': 0.007, 'Ninja_Tunic': 0.007}
for name, p in PARTS.items():
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
eb('hips', (0, 0, 0.32), (0, 0, 0.40), 'root', r=0.10)
eb('spine', (0, 0, 0.40), (0, 0, 0.47), 'hips', r=0.11)
eb('chest', (0, 0, 0.47), (0, 0, 0.56), 'spine', r=0.11)
eb('neck', (0, 0, 0.56), (0, 0, 0.62), 'chest', r=0.06)
eb('head', (0, 0, 0.62), (0, 0, 0.98), 'neck', r=0.19)
for s, sd in ((1, 'L'), (-1, 'R')):
    eb('upper_arm.' + sd, SH[s], ELB[s], 'chest', r=0.04)
    eb('forearm.' + sd, ELB[s], WRI[s], 'upper_arm.' + sd, r=0.036)
    eb('hand.' + sd, WRI[s], HTIP[s], 'forearm.' + sd, r=0.035)
    eb('thigh.' + sd, HIPJ[s], KNEE[s], 'hips', r=0.055)
    eb('shin.' + sd, KNEE[s], ANK[s], 'thigh.' + sd, r=0.045)
    eb('foot.' + sd, ANK[s], TOE[s], 'shin.' + sd, r=0.045)
def cape_pt(ph_deg, t):
    ph = math.radians(ph_deg)
    e = t ** 0.8
    return Vector((lerp(0.13, 0.25, e) * math.sin(ph), -lerp(0.122, 0.215, e) * math.cos(ph), lerp(CAPE_TOP, CAPE_BOT, t)))
CAPE_COLS = {'C': 180, 'L': 142, 'R': 218}
for k, ph in CAPE_COLS.items():
    ts = (0.0, 0.33, 0.66, 1.0)
    par = 'chest'
    for i in range(3):
        nm = 'cape_%s%d' % (k, i + 1)
        eb(nm, cape_pt(ph, ts[i]), cape_pt(ph, ts[i + 1]), par, r=0.08)
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
        return {'hand.L': 1.0}
    if obname == 'Ninja_Hood':
        if z > 0.655:
            return {'head': 1.0}
        f = max(0.0, min(1.0, (z - 0.575) / 0.08))
        return {'head': 0.35 + 0.65 * f, 'chest': 0.65 * (1 - f)} if f < 1 else {'head': 1.0}
    if obname == 'Ninja_Cape':
        f = max(0.0, min(1.0, 1 - (CAPE_TOP - z) / 0.07))
        w = dist_weights(q, [n for n in DEFORM if n.startswith('cape_')], 3)
        out = {n: v * (1 - f) for n, v in w.items()}
        out['chest'] = out.get('chest', 0) + f
        return out
    if obname == 'Ninja_Gloves':
        return dist_weights(q, ['hand.' + sd, 'forearm.' + sd], 2)
    if obname == 'Ninja_Boots':
        return dist_weights(q, ['foot.' + sd, 'shin.' + sd], 2)
    if obname == 'Ninja_Clothing' and z > 0.552 and abs(x) < 0.2:
        return {'chest': 0.6, 'neck': 0.4}
    if obname == 'Ninja_Tunic':
        return dist_weights(q, ['hips', 'spine', 'thigh.L', 'thigh.R'], 2) if z > 0.3 else \
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
        if n in ('lift', 'off'):
            out[n] = v if n == 'lift' else (-v[0], v[1], v[2])
        else:
            out[mirror_name(n)] = (v[0], -v[1], -v[2])
    return out
def merge(*ps):
    out = {}
    for p in ps:
        out.update(p)
    return out
def cape(a, b, c, sway=0.0):
    out = {}
    for k, w in (('C', 0.0), ('L', 1.0), ('R', -1.0)):
        out['cape_%s1' % k] = (a, 0, sway * w * 0.5 + sway)
        out['cape_%s2' % k] = (b, 0, sway * 0.5)
        out['cape_%s3' % k] = (c, 0, sway * 0.3)
    return out

STAND = merge({'upper_arm.L': (0, 34, 0), 'upper_arm.R': (0, -34, 0), 'forearm.L': (-18, 0, 0), 'forearm.R': (-18, 0, 0),
               'thigh.L': (-8, -5, 0), 'thigh.R': (-8, 5, 0), 'shin.L': (15, 5, 0), 'shin.R': (15, -5, 0),
               'foot.L': (-7, 0, 0), 'foot.R': (-7, 0, 0), 'spine': (4, 0, 0), 'head': (-4, 0, 0)}, cape(4, 2, 2))
IDLE_B = merge(STAND, {'chest': (-2, 0, 0), 'upper_arm.L': (0, 37, 0), 'upper_arm.R': (0, -37, 0), 'head': (-6, 0, 0),
                       'thigh.L': (-11, -5, 0), 'thigh.R': (-11, 5, 0), 'shin.L': (20, 5, 0), 'shin.R': (20, -5, 0),
                       'foot.L': (-9, 0, 0), 'foot.R': (-9, 0, 0)}, cape(6, 4, 4, 2))
RUN_BODY = {'spine': (14, 0, 0), 'chest': (8, 0, -6), 'hips': (0, 0, 6), 'head': (-20, 0, 6),
            'upper_arm.L': (68, 26, 0), 'upper_arm.R': (62, -26, 0), 'forearm.L': (12, 0, 0), 'forearm.R': (12, 0, 0)}
RUN_C = merge(RUN_BODY, {'thigh.L': (-48, 0, 0), 'shin.L': (22, 0, 0), 'foot.L': (-6, 0, 0),
                         'thigh.R': (32, 0, 0), 'shin.R': (58, 0, 0), 'foot.R': (22, 0, 0)}, cape(24, 8, 6, 4))
RUN_P = merge(RUN_BODY, {'hips': (0, 0, 0), 'chest': (8, 0, 0), 'head': (-20, 0, 0),
                         'thigh.L': (-6, 0, 0), 'shin.L': (14, 0, 0), 'foot.L': (-8, 0, 0),
                         'thigh.R': (-38, 0, 0), 'shin.R': (104, 0, 0), 'foot.R': (12, 0, 0), 'lift': 0.022}, cape(31, 12, 10, 0))
CROUCH = {'thigh.L': (-58, -4, 0), 'thigh.R': (-58, 4, 0), 'shin.L': (88, 0, 0), 'shin.R': (88, 0, 0), 'foot.L': (-30, 0, 0),
          'foot.R': (-30, 0, 0), 'spine': (26, 0, 0), 'chest': (6, 0, 0), 'head': (-26, 0, 0),
          'upper_arm.L': (55, 26, 0), 'upper_arm.R': (55, -26, 0), 'forearm.L': (10, 0, 0), 'forearm.R': (10, 0, 0)}
JUMP_UP = merge({'thigh.L': (-12, 0, 0), 'thigh.R': (-6, 0, 0), 'shin.L': (14, 0, 0), 'shin.R': (10, 0, 0), 'foot.L': (32, 0, 0),
                 'foot.R': (32, 0, 0), 'spine': (-4, 0, 0), 'head': (-6, 0, 0),
                 'upper_arm.L': (-140, 12, 0), 'upper_arm.R': (-140, -12, 0), 'forearm.L': (-12, 0, 0), 'forearm.R': (-12, 0, 0)}, cape(12, 6, 4))
JUMP_TUCK = merge({'thigh.L': (-72, -6, 0), 'thigh.R': (-34, 6, 0), 'shin.L': (104, 0, 0), 'shin.R': (64, 0, 0), 'foot.L': (12, 0, 0),
                   'foot.R': (22, 0, 0), 'spine': (10, 0, 0), 'head': (-12, 0, 0),
                   'upper_arm.L': (-40, -22, 0), 'upper_arm.R': (-40, 22, 0), 'forearm.L': (-30, 0, 0), 'forearm.R': (-30, 0, 0)}, cape(32, 12, 10))
FALL_A = merge({'thigh.L': (-36, -6, 0), 'thigh.R': (-10, 6, 0), 'shin.L': (52, 0, 0), 'shin.R': (28, 0, 0), 'foot.L': (20, 0, 0),
                'foot.R': (24, 0, 0), 'spine': (-5, 0, 0), 'head': (-10, 0, 0),
                'upper_arm.L': (-28, -55, 0), 'upper_arm.R': (-28, 55, 0), 'forearm.L': (-22, 0, 0), 'forearm.R': (-22, 0, 0)}, cape(72, 22, 16, -4))
FALL_B = merge(FALL_A, {'thigh.L': (-26, -6, 0), 'thigh.R': (-20, 6, 0), 'shin.L': (40, 0, 0), 'shin.R': (40, 0, 0),
                        'upper_arm.L': (-32, -63, 0), 'upper_arm.R': (-32, 63, 0)}, cape(80, 28, 22, 4))
LAND_IMPACT = merge(CROUCH, {'thigh.L': (-66, -6, 0), 'thigh.R': (-66, 6, 0), 'shin.L': (102, 0, 0), 'shin.R': (102, 0, 0),
                             'foot.L': (-36, 0, 0), 'foot.R': (-36, 0, 0), 'spine': (30, 0, 0), 'upper_arm.L': (42, 30, 0),
                             'upper_arm.R': (42, -30, 0)}, cape(20, 6, 6))
LAND_MID = merge(CROUCH, {'thigh.L': (-44, -4, 0), 'thigh.R': (-44, 4, 0), 'shin.L': (70, 0, 0), 'shin.R': (70, 0, 0),
                          'foot.L': (-25, 0, 0), 'foot.R': (-25, 0, 0), 'spine': (20, 0, 0)}, cape(30, 8, 8))
LAND_END = merge(RUN_BODY, {'hips': (0, 0, 0), 'chest': (8, 0, 0), 'head': (-20, 0, 0), 'thigh.L': (-14, -3, 0), 'thigh.R': (-10, 3, 0),
                            'shin.L': (24, 0, 0), 'shin.R': (20, 0, 0), 'foot.L': (-10, 0, 0), 'foot.R': (-10, 0, 0)}, cape(40, 10, 8))
SLIDE_A = merge({'thigh.L': (-86, -4, 0), 'shin.L': (6, 0, 0), 'foot.L': (24, 0, 0),
                 'thigh.R': (-34, 10, 0), 'shin.R': (122, 0, 0), 'foot.R': (22, 0, 0),
                 'spine': (-20, 0, 0), 'chest': (-6, 0, 0), 'head': (16, 0, 0),
                 'upper_arm.L': (-36, -28, 0), 'upper_arm.R': (40, 12, 0), 'forearm.L': (-24, 0, 0), 'forearm.R': (-10, 0, 0)}, cape(70, 16, 10, 3))
SLIDE_B = merge(SLIDE_A, {'spine': (-23, 0, 0), 'head': (18, 0, 0), 'upper_arm.L': (-40, -32, 0)}, cape(77, 22, 16, -3))

ACTIONS = [
    ('Idle', [(0, STAND), (24, IDLE_B), (48, STAND)]),
    ('Run', [(0, RUN_C), (4, RUN_P), (8, mirror_pose(RUN_C)), (12, mirror_pose(RUN_P)), (16, RUN_C)]),
    ('Jump', [(0, STAND), (4, CROUCH), (8, JUMP_UP), (14, JUMP_TUCK), (18, merge(JUMP_TUCK, cape(38, 14, 12)))]),
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
