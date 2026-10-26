# v7 cape texture (1024^2): albedo + alpha cutout (torn hem, ragged holes) and a tangent-space normal map, from
# the cape layout in fal_v3/cape_v7.py (same hem / holes / folds as the mesh).
#   python v7_cape_tex.py OUTDIR   -> OUTDIR/cape_basecolor_v7.png (RGBA), cape_normal_v7.png  (-> webp in fal_v3/)
import numpy as np, sys, os
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import cape_v7 as cv
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
T = 1024
rng = np.random.default_rng(5)
def noise(sig, seed):
    r = np.random.default_rng(seed).normal(size=(T, T)).astype(np.float32)
    r = ndi.gaussian_filter(r, sig, mode='wrap'); return r / (r.std() + 1e-9)
n_fray = noise(1.2, 1); n_mid = noise(4, 2); n_big = noise(14, 3); n_fine = noise(0.7, 4)
yy, xx = np.mgrid[0:T, 0:T].astype(np.float32) + 0.5
alpha = np.zeros((T, T), np.float32); hgt = np.zeros((T, T), np.float32)
col = np.zeros((T, T, 3), np.float32); edge = np.zeros((T, T), np.float32)
base = np.array([31, 28, 29], np.float32)                       # near-black, slightly warm (as the references)
for layer, L in cv.LAYERS.items():
    s0, t0, s1, t1 = L['uv']
    pad = 6
    x0, x1 = int(s0 * T) - pad, int(s1 * T) + pad; y0, y1 = int(t0 * T) - pad, int(t1 * T) + pad
    sl = (slice(max(y0, 0), min(y1, T)), slice(max(x0, 0), min(x1, T)))
    U = ((xx[sl] / T - s0) / (s1 - s0)) * 2 - 1
    V = (yy[sl] / T - t0) / (t1 - t0)
    Uc = np.clip(U, -1, 1)
    us = np.linspace(-1, 1, L['nu'])
    hemv = np.interp(Uc, us, cv.hem_len(us, L['seed']) * L['vlen'])     # the mesh hem (piecewise linear)
    rows_px = (t1 - t0) * T                                          # pixels per unit v
    fr = n_fray[sl]; fm = n_mid[sl]
    cut = hemv - (0.006 + 0.012 * np.clip(fm * 0.5 + 0.5, 0, 1) + 0.006 * np.clip(fr, -1, 2))    # ragged, inside the mesh hem
    inside = (V >= -0.002) & (V <= cut) & (np.abs(U) <= 0.995 - 0.010 * np.clip(fm * 0.4 + 0.6, 0, 1.2) * (V > 0.15))
    d_edge = np.minimum(cut - V, (0.995 - np.abs(U)) * 0.6)          # distance (v units) to the torn border
    for hu, hv, ru, rv in cv.HOLES[layer]:
        ang = np.arctan2((V - hv) / rv, (U - hu) / ru)
        rr = np.sqrt(((U - hu) / ru) ** 2 + ((V - hv) / rv) ** 2)
        lim = 1.04 + 0.16 * np.clip(0.5 + 0.5 * np.sin(5 * ang + hu * 7) * 0.6 + 0.3 * fm, 0, 1.3) + 0.05 * np.clip(fr, -1, 1)
        inside &= rr > lim
        d_edge = np.minimum(d_edge, (rr - lim) * rv)
    a = inside.astype(np.float32)
    alpha[sl] = np.maximum(alpha[sl], a)
    # shading: fold valleys darker, ridges lighter, top edge in the mantle's shadow, worn (browner, lighter) torn edges
    f = cv.folds(U * L['uscale'], np.clip(V, 0, 1))
    ff = f / (0.0025 + 0.015 * np.clip(V, 0, 1) ** 1.1 + 1e-4)
    cr = cv.fold_crease(U * L['uscale'], np.clip(V, 0, 1))
    shade = (1 + 0.16 * np.clip(ff, -1, 1)) * (1 - 0.30 * cr) * (0.72 + 0.28 * cv._ss(V / 0.12))
    shade *= 1 + 0.10 * n_big[sl] + 0.05 * fm
    if layer == 'inner':
        shade *= 0.78
    wear = np.clip(1 - np.maximum(d_edge, 0) / 0.035, 0, 1) ** 1.5
    c = base[None, None] * shade[..., None]
    c = c * (1 - 0.55 * wear[..., None]) + np.array([72, 52, 43], np.float32)[None, None] * (0.45 * wear[..., None]) * shade[..., None]
    m = (np.abs(U) <= 1.02) & (V >= -0.02) & (V <= L['vlen'] + 0.02)
    col[sl][m] = c[m]
    edge[sl][m] = wear[m]
    # height (pixel-ish units): fold creases + crumpled cloth + frayed edge thinning
    h = -1.0 * cr - 0.35 * fm * 0.3 - 0.6 * wear
    hgt[sl][m] = h[m]
# fabric weave (diagonal twill ~3 px) and slub, everywhere
tw = 0.5 * np.sin(2 * np.pi * (xx + yy) / 3.2) + 0.5 * np.sin(2 * np.pi * (xx - 0.5 * yy) / 4.1)
hgt += 0.10 * tw + 0.08 * n_fine
col *= (1 + 0.05 * tw + 0.04 * n_fine)[..., None]
# fill outside (gutters) from the nearest painted texel
valid = col.sum(-1) > 0
di, (iy, ix) = ndi.distance_transform_edt(~valid, return_distances=True, return_indices=True)
col = col[iy, ix]; hgt = hgt[iy, ix]
alpha = ndi.gaussian_filter(alpha, 0.6)
bc = np.dstack([np.clip(col, 0, 255), np.clip(alpha * 255 * 1.2, 0, 255)]).astype(np.uint8)
Image.fromarray(bc, 'RGBA').save(OUT + '/cape_basecolor_v7.png')
# normal map (OpenGL): tangent = +s (= +u, +X across), bitangent = +t (Blender v up = towards the top edge, image up)
hs = ndi.gaussian_filter(hgt, 0.8)
gx = np.gradient(hs, axis=1); gy = np.gradient(hs, axis=0)
K = 0.9
nx = -K * gx; ny = K * gy                     # dh/dB = -dh/drow  ->  n_y = -dh/dB = +dh/drow
nn = np.dstack([nx, ny, np.ones_like(nx)]); nn /= np.linalg.norm(nn, axis=-1, keepdims=True)
Image.fromarray(((nn + 1) * 127.5).clip(0, 255).astype(np.uint8)).save(OUT + '/cape_normal_v7.png')
print('cape texture: alpha cover %.3f' % (alpha > 0.5).mean())
