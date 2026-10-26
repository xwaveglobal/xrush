# Ninja cape v7: a clean, purpose-built two-layer cape (replaces the scanned cape sheet), shared by
# build_ninja_v3.py (geometry, UVs, skin weights) and scripts/v7_cape_tex.py (albedo/alpha, normal map).
# Blender axes: Z up, the character faces -Y, the cape hangs behind it (+Y). Units: metres.
#
# A layer is a (u, v) grid: u in [-1, 1] across (+u = the character's left, +X), v in [0, 1] from the top edge
# (tucked under the shoulder mantle) to the hem. The hem is torn: every column has its own length (teeth), a
# few holes are cut out of the grid (faces removed) and the texture's alpha mask rags all those borders.
import numpy as np

def _ss(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)

# --- layers --------------------------------------------------------------------------------------------
# nu/nv: grid columns/rows; uv: atlas rectangle (s0, t0, s1, t1) in image space (t down) of the cape texture
LAYERS = {
    'outer': dict(nu=35, nv=27, uscale=1.0, off=0.0, vlen=1.0, uv=(0.01, 0.01, 0.99, 0.57), seed=11),
    'inner': dict(nu=25, nv=19, uscale=0.90, off=-0.0075, vlen=0.86, uv=(0.01, 0.61, 0.99, 0.99), seed=23),
}
# torn hem: per-column length (fraction of the layer's vlen) = 1 - teeth
def hem_len(u, seed):
    rng = np.random.default_rng(seed)
    n = len(u)
    # irregular strips 2..4 columns wide, each a pointed tongue of its own length (not a regular saw)
    tooth = np.zeros(n); i = 0
    while i < n:
        w = int(rng.integers(2, 5)); d = 0.05 + 0.13 * rng.random()
        for j in range(w):
            if i + j < n:
                tooth[i + j] = d * (1.0 if j in (0, w - 1) else 0.25 * rng.random()) + (0.06 if j == 0 else 0.0)
        i += w
    depth = 1.0
    big = np.zeros(n)
    for c, w, d in ((-0.62, 0.16, 0.20), (0.18, 0.12, 0.15), (0.74, 0.14, 0.24)) if seed == 11 else ((-0.3, 0.2, 0.18), (0.45, 0.16, 0.14)):
        big = np.maximum(big, d * np.exp(-((u - c) / w) ** 2))      # a few deeper rips
    side = 0.10 * np.abs(u) ** 3                                       # corners a little shorter
    return np.clip(1.0 - tooth - big - side - 0.03 * rng.random(n), 0.55, 1.0)
# holes (u, v, radius_u, radius_v) in layer coordinates; faces fully inside are removed, alpha rags the rim
HOLES = {
    'outer': [(-0.44, 0.70, 0.075, 0.085), (0.34, 0.80, 0.06, 0.07), (0.68, 0.56, 0.05, 0.065),
              (-0.08, 0.90, 0.055, 0.05)],
    'inner': [(0.22, 0.62, 0.08, 0.07)],
}

def surface(u, v, layer='outer'):
    """rest position of layer points (u, v) -> (N, 3); also the outward (away from the body) unit normal"""
    L = LAYERS[layer]
    u = np.asarray(u, float) * L['uscale']; v = np.asarray(v, float)
    zt = 0.530 - 0.035 * u ** 2                       # top edge: under the mantle, following the shoulders
    zh = 0.120 + 0.030 * np.abs(u)                    # hem line before tearing
    z = zt + (zh - zt) * v
    hw = 0.165 + 0.100 * v ** 0.85                    # half width: shoulder wide at the top, flaring
    x = u * hw
    yc = 0.084 + 0.100 * v ** 1.6                     # hangs clear of the seat, trails back a little
    k = 1.45 * (0.65 + 0.35 * v)                      # wraps around the body
    y = yc - k * x ** 2
    # outward normal of the unfolded sheet (horizontal component of the wrap + a little tilt)
    n = np.stack([2 * k * x, np.ones_like(x), 0.15 * np.ones_like(x)], -1)   # dy/dx = -2kx -> outward (2kx, 1, .)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    P = np.stack([x, y, z], -1)
    P = P + folds(u, v)[:, None] * n + L['off'] * n
    return P, n

def folds(u, v):
    """big cloth folds (m, + = outward): ~5 folds fanning out from the gathered top, deeper towards the hem"""
    ph = 2 * np.pi * (2.6 * (u + 1)) + 0.5 * np.sin(2.3 * u + 0.7)
    a = 0.0025 + 0.0150 * v ** 1.1
    f = a * np.sin(ph)
    f += 0.0035 * v * np.sin(2 * np.pi * (4.3 * (u + 1)) + 3.1 * v + 1.0)    # smaller secondary folds
    f += 0.0030 * np.exp(-(v / 0.10) ** 2) * np.sin(2 * np.pi * 7 * (u + 1))  # gathered pleats at the top
    return f

def fold_crease(u, v):
    """sharp crease lines (0..1) at the fold valleys, for the normal map / shading (texture only)"""
    ph = 2 * np.pi * (2.6 * (u + 1)) + 0.5 * np.sin(2.3 * u + 0.7)
    val = np.clip(-np.sin(ph), 0, 1) ** 6 * _ss(v / 0.25)
    return val

def build(layer):
    """grid -> verts (N,3), quads (M,4), uv per vertex (N,2, Blender space: t up), (u, v) per vertex, normals"""
    L = LAYERS[layer]
    nu, nv = L['nu'], L['nv']
    us = np.linspace(-1, 1, nu)
    hl = hem_len(us, L['seed']) * L['vlen']
    U, Vf = np.meshgrid(us, np.linspace(0, 1, nv))
    U = U.ravel(); V = (Vf * hl[None, :]).ravel()            # each column ends at its own torn length
    idx = np.arange(nu * nv).reshape(nv, nu)
    Q = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    # holes: quads touching a grid point inside the hole ellipse are removed and the ring of grid points around
    # them is snapped onto the ellipse, so the mesh hole is an ellipse-inscribed polygon; the texture's alpha hole
    # (>= 1.04 x the ellipse, ragged) is always a little bigger, so the visible rim is the ragged one
    keep = np.ones(len(Q), bool)
    for hu, hv, ru, rv in HOLES[layer]:
        r = np.sqrt(((U - hu) / ru) ** 2 + ((V - hv) / rv) ** 2)
        ins = r < 1
        if not ins.any():
            continue
        drop = ins[Q].any(1) & keep
        ring = np.unique(Q[drop].ravel()); ring = ring[~ins[ring]]
        keep &= ~drop
        k = 1.0 / np.maximum(r[ring], 1e-9)
        U[ring] = hu + (U[ring] - hu) * k; V[ring] = hv + (V[ring] - hv) * k
    P, N = surface(U, V, layer)
    s0, t0, s1, t1 = L['uv']
    uvs = np.stack([s0 + (U + 1) / 2 * (s1 - s0), 1 - (t0 + V * (t1 - t0))], -1)
    return P, Q[keep], uvs, np.stack([U, V], -1), N

# --- skin weights ---------------------------------------------------------------------------------------
LEVEL_V = (0.0, 0.30, 0.65, 1.0)        # cape bone joints along v (C chain: z 0.545 / 0.40 / 0.26 / 0.11)
def weights(UV, layer):
    """per vertex: dict bone -> weight (chest pins the top edge; C/L/R columns x 3 levels)"""
    u = UV[:, 0] * LAYERS[layer]['uscale']; v = UV[:, 1]
    s = np.interp(v, LEVEL_V, [0, 1, 2, 3])
    lv = [1 - _ss((s - 0.80) / 0.40), None, _ss((s - 1.80) / 0.40)]
    lv[1] = np.clip(1 - lv[0] - lv[2], 0, 1)
    side = _ss(np.abs(u) / 0.85)                          # 0 at the centre column, 1 at the edge columns
    pin = 1 - _ss(v / 0.10)
    out = {}
    for i in range(3):
        out['cape_C%d' % (i + 1)] = lv[i] * (1 - side) * (1 - pin)
        out['cape_L%d' % (i + 1)] = lv[i] * side * (u > 0) * (1 - pin)
        out['cape_R%d' % (i + 1)] = lv[i] * side * (u <= 0) * (1 - pin)
    out['chest'] = pin
    return out
