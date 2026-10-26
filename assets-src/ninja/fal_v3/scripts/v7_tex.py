# v7 body texture pass (on top of v6: hood untouched). From a dump of the final rest-pose mesh (dump_v7.py):
#  - scarf / neck wrap / shoulder mantle recoloured to the hood charcoal (no colour jump at the scarf line);
#    leather straps (saturated brown) and metal (bright, grey) inside that region are kept
#  - the v7 body cloth creases (body_folds.py, the same field the geometry uses, narrower) in the normal map +
#    crease shading in the albedo; mild ray-cast AO over the body (below the face)
#  - strap / belt / pouch edges: a small bevel in the normal map from the leather mask, a stitch line along them
# usage: python v7_tex.py dump.npz basecolor_v6.webp normal_v6.webp OUTDIR -> basecolor_v7.png, normal_v7.png
import numpy as np, sys, os
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import body_folds as bf
d = np.load(sys.argv[1])
Q = d['P']; F = d['F']; UV = d['uv']; AO = d['ao']; VN = d['N']
wn = [str(x) for x in d['wnames']]; Wm = d['W']
Wd = {n: Wm[:, i] for i, n in enumerate(wn)}
SEG = {str(n): (d['seg'][i, 0], d['seg'][i, 1]) for i, n in enumerate(d['segn'])}
bc = np.asarray(Image.open(sys.argv[2]).convert('RGBA')).astype(np.float32)
nm = np.asarray(Image.open(sys.argv[3]).convert('RGB')).astype(np.float32)
OUT = sys.argv[4]
T = bc.shape[0]
ss = bf._ss
FT = bf.features(Q, Wd, SEG)
keys = sorted(FT)
head = Wd.get('head', np.zeros(len(Q)))
X, Y, Z = Q.T
r_neck = np.hypot(X, Y + 0.02)
# scarf / mantle region (3D): around the neck and over the shoulders, below the hood / face
scarf3 = ss((Z - 0.475) / 0.02) * (1 - ss((Z - 0.655) / 0.015)) * (1 - ss((r_neck - 0.215) / 0.03)) * (1 - ss((head - 0.6) / 0.3))
face3 = (Y < -0.06) & (Z > 0.6)
scarf3 = scarf3 * (~face3)
body3 = 1 - ss((Z - 0.6) / 0.03)
vals = np.c_[np.stack([FT[k] for k in keys], 1), AO, scarf3, body3, Q, VN]
def raster(vals):
    out = np.full((T, T, vals.shape[1]), np.nan, np.float32)
    uvp = np.c_[UV[:, 0] * T, (1 - UV[:, 1]) * T]
    tt = uvp.reshape(-1, 3, 2)
    area = 0.5 * np.abs((tt[:, 1, 0] - tt[:, 0, 0]) * (tt[:, 2, 1] - tt[:, 0, 1]) - (tt[:, 2, 0] - tt[:, 0, 0]) * (tt[:, 1, 1] - tt[:, 0, 1]))
    for f in np.argsort(-area):
        t = uvp[3 * f:3 * f + 3]
        x0, y0 = np.maximum(np.floor(t.min(0)).astype(int) - 1, 0); x1, y1 = np.minimum(np.ceil(t.max(0)).astype(int) + 1, T - 1)
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, ay), (bx, by), (qx, qy) = t; den = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
        if abs(den) < 1e-14: continue
        l1 = ((by - qy) * (gx - qx) + (qx - bx) * (gy - qy)) / den; l2 = ((qy - ay) * (gx - qx) + (ax - qx) * (gy - qy)) / den; l3 = 1 - l1 - l2
        m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not m.any(): continue
        i0, i1, i2 = F[f]
        v = (l1[..., None] * vals[i0] + l2[..., None] * vals[i1] + l3[..., None] * vals[i2])
        s = out[y0:y1 + 1, x0:x1 + 1]; s[m] = v[m]
    return out
Rf = raster(vals)
valid = np.isfinite(Rf[..., 0]); Rf = np.nan_to_num(Rf)
nk = len(keys)
FTt = {k: Rf[..., i] for i, k in enumerate(keys)}
AOt = Rf[..., nk]; SC = Rf[..., nk + 1]; BOD = Rf[..., nk + 2]; QT = Rf[..., nk + 3:nk + 6]; NT = Rf[..., nk + 6:nk + 9]
for k in ('arm_c_L', 'arm_s_L', 'arm_c_R', 'arm_s_R', 'leg_c_L', 'leg_s_L', 'leg_c_R', 'leg_s_R', 'scarf_c', 'scarf_s'):
    pass  # interpolated cos/sin: atan2 in the field is scale-free, so no renormalising needed
sel = valid & (BOD > 0.01)
h_sharp = np.zeros((T, T), np.float32); h_full = np.zeros((T, T), np.float32)
Fs = {k: v[sel] for k, v in FTt.items()}
h_sharp[sel] = bf.field(Fs, sharp=True); h_full[sel] = bf.field(Fs)
print('fold texels', int((h_full > 0.0005).sum()))
# ---- material masks from the v6 albedo
rgb = bc[..., :3].copy()
mx = rgb.max(-1); mn = rgb.min(-1); sat = (mx - mn) / np.maximum(mx, 1)
lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
leather = ss((sat - 0.28) / 0.12) * ss((rgb[..., 0] - rgb[..., 2] - 18) / 12) * ss((lum - 35) / 20)
metal = ss((lum - 120) / 30) * (1 - ss((sat - 0.3) / 0.1))
cloth = (1 - leather) * (1 - metal)
# ---- albedo
loc = ndi.gaussian_filter(lum * valid, 6) / np.maximum(ndi.gaussian_filter(valid.astype(np.float32), 6), 1e-4)
detail = np.clip(lum / np.maximum(loc, 1), 0.7, 1.35)
char = np.array([40, 37, 38], np.float32)                  # the hood charcoal (v6)
ao_t = np.clip((AOt - 0.35) / 0.6, 0, 1) ** 0.8
crease = np.clip(h_sharp / 0.0035, 0, 1); deep = np.clip(h_full / 0.004, 0, 1)
shade_scarf = (0.62 + 0.38 * ao_t) * (1 - 0.3 * crease - 0.15 * deep)
sw = (SC * cloth)[..., None]
scarf_c = char[None, None] * (detail ** 0.6)[..., None] * shade_scarf[..., None] * 1.08
out = rgb * (1 - sw) + scarf_c * sw
# the rest of the body: crease + mild AO shading (multiplied, keeps the painted detail)
bw = (BOD * (1 - SC))[..., None]
mul = (0.8 + 0.2 * ao_t) * (1 - 0.28 * crease - 0.12 * deep)
out = out * (1 - bw) + out * mul[..., None] * bw
# stitches along leather edges (dark dashes 1.5 px inside the edge)
le = leather > 0.5
edge_in = le & ~ndi.binary_erosion(le, iterations=2) & ndi.binary_erosion(le, iterations=1)
dash = ((np.add.outer(np.arange(T), np.arange(T)) // 3) % 2 == 0)
st = edge_in & dash & (BOD > 0.5)
out[st] *= 0.72
delta = np.where(valid[..., None], out - rgb, 0)
dist, (iy, ix) = ndi.distance_transform_edt(~valid, return_distances=True, return_indices=True)
gut = (~valid) & (dist < 10)
out[gut] = rgb[gut] + delta[iy[gut], ix[gut]]
bco = bc.copy(); bco[..., :3] = np.clip(out, 0, 255)
Image.fromarray(bco.astype(np.uint8), 'RGBA').save(OUT + '/basecolor_v7.png')
# ---- normal map: crease height (pressed in) + leather edge bevel (raised), via the UV jacobian
lsoft = ndi.gaussian_filter(leather * valid, 1.2) * (BOD > 0.01)
hgt = h_sharp - 0.0006 * lsoft                                 # leather sits ~0.6 mm proud (bevelled edge)
di, (jy, jx) = ndi.distance_transform_edt(~valid, return_distances=True, return_indices=True)
hgt_f = hgt[jy, jx]; Qf = QT[jy, jx]
def dxy(A):
    gx = np.zeros_like(A); gy = np.zeros_like(A)
    gx[:, 1:-1] = 0.5 * (A[:, 2:] - A[:, :-2]); gy[1:-1] = 0.5 * (A[2:] - A[:-2])
    return gx, gy
hx, hy = dxy(hgt_f)
qx = np.stack([dxy(Qf[..., c])[0] for c in range(3)], -1); qy = np.stack([dxy(Qf[..., c])[1] for c in range(3)], -1)
lx = np.linalg.norm(qx, axis=-1); ly = np.linalg.norm(qy, axis=-1)
ok = valid & (lx > 1e-6) & (ly > 1e-6) & (lx < 0.004) & (ly < 0.004)
sT = np.where(ok, hx / np.maximum(lx, 1e-9), 0); sB = np.where(ok, -hy / np.maximum(ly, 1e-9), 0)
nx = np.clip(sT, -1.5, 1.5); ny = np.clip(sB, -1.5, 1.5)
for A in (nx, ny): A[:] = ndi.gaussian_filter(A, 0.7)
fb = nm / 127.5 - 1
pdx = fb[..., 0] / np.maximum(fb[..., 2], 0.3) + nx
pdy = fb[..., 1] / np.maximum(fb[..., 2], 0.3) + ny
comb = np.stack([pdx, pdy, np.ones_like(pdx)], -1); comb /= np.linalg.norm(comb, axis=-1, keepdims=True)
newn = (comb + 1) * 127.5
wN = (BOD > 0.01) & valid
nmo = np.where(wN[..., None], newn, nm)
nmo[gut] = np.where(wN[iy[gut], ix[gut]][..., None], newn[iy[gut], ix[gut]], nm[gut])
Image.fromarray(np.clip(nmo, 0, 255).astype(np.uint8)).save(OUT + '/normal_v7.png')
np.save(OUT + '/scarfmask.npy', SC * cloth)
print('scarf texels', int((SC * cloth > 0.5).sum()), 'leather texels', int((leather > 0.5).sum()), 'done')
