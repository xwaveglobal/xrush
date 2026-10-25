# v5 hood texture pass (Blender coordinates, after the v5 hood re-shape):
#  - hood cloth (shell, brim, inside lining) darkened toward near-black charcoal, detail kept
#  - cavity shading from the new geometry (folds, brim roll) baked into the albedo
#  - normal map flattened on the hood (the Tripo bumps are what made it look lumpy) + faint weave kept
#  - front-crown strip blended away
# usage: python v5_tex.py RAW.npz FINAL.npz BASECOLOR_v4.png NORMAL_v4.png OUTDIR
import numpy as np, sys
from PIL import Image
from scipy import ndimage as ndi
raw = np.load(sys.argv[1]); fin = np.load(sys.argv[2])
P0 = raw['P']; F0 = raw['F']; UV = raw['uv']; Q = fin['P'][:len(P0)]; F1 = fin['F']
bc = np.asarray(Image.open(sys.argv[3])).astype(np.float32)
nm = np.asarray(Image.open(sys.argv[4]).convert('RGB')).astype(np.float32)
OUT = sys.argv[5]
T = bc.shape[0]
def ss(t): t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)
# ---- per-vertex fields on the final mesh
n = len(Q)
E = np.unique(np.sort(np.r_[F1[:, [0, 1]], F1[:, [1, 2]], F1[:, [2, 0]]], 1), axis=0)
deg = np.bincount(E.ravel(), minlength=n).astype(float)
def nb_mean(A):
    acc = np.zeros_like(A); np.add.at(acc, E[:, 0], A[E[:, 1]]); np.add.at(acc, E[:, 1], A[E[:, 0]])
    return acc / np.maximum(deg, 1).reshape((-1,) + (1,) * (A.ndim - 1))
fn = np.cross(Q[F1[:, 1]] - Q[F1[:, 0]], Q[F1[:, 2]] - Q[F1[:, 0]])
vn = np.zeros_like(Q)
for k in range(3): np.add.at(vn, F1[:, k], fn)
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
cav = ((nb_mean(Q) - Q) * vn).sum(1)            # > 0 = concave (inside a fold / crease)
cav2 = nb_mean(nb_mean(Q)) - Q; cav2 = (cav2 * vn).sum(1)
cav = 0.5 * cav + 0.5 * cav2 / 2
for _ in range(2): cav = 0.5 * cav + 0.5 * nb_mean(cav)
X, Y, Z = Q.T
C = np.array([0.0, -0.01, 0.74]); D = Q - C; R = np.linalg.norm(D, axis=1); D /= R[:, None]
az = np.degrees(np.arctan2(D[:, 0], -D[:, 1])); el = np.degrees(np.arcsin(np.clip(D[:, 2], -1, 1)))
rho = np.sqrt((az / 45) ** 2 + (np.maximum(el, 0) / 34) ** 2)
P0x, P0y, P0z = P0.T
face = (P0y < -0.10) & (np.abs(P0x) < 0.135) & (P0z < 0.87) & (P0z > 0.58) & (rho < 1.02)
hoodv = ss((Z - 0.625) / 0.03) * (~face)
# ---- rasterise: per texel barycentric -> vertex fields
def raster(vals):
    out = np.full((T, T) + vals.shape[1:], np.nan, np.float32)
    uvp = np.c_[UV[:, 0] * T, (1 - UV[:, 1]) * T]
    for f in range(len(F0)):
        t = uvp[3 * f:3 * f + 3]
        x0, y0 = np.maximum(np.floor(t.min(0)).astype(int) - 1, 0); x1, y1 = np.minimum(np.ceil(t.max(0)).astype(int) + 1, T - 1)
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, ay), (bx, by), (qx, qy) = t; den = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
        if abs(den) < 1e-14: continue
        l1 = ((by - qy) * (gx - qx) + (qx - bx) * (gy - qy)) / den; l2 = ((qy - ay) * (gx - qx) + (ax - qx) * (gy - qy)) / den; l3 = 1 - l1 - l2
        m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not m.any(): continue
        i0, i1, i2 = F0[f]
        v = (l1[..., None] * vals[i0] + l2[..., None] * vals[i1] + l3[..., None] * vals[i2])
        s = out[y0:y1 + 1, x0:x1 + 1]; s[m] = v[m]
    return out
fields = np.c_[hoodv, cav, Q, P0]
Rf = raster(fields)
valid = np.isfinite(Rf[..., 0])
H = np.nan_to_num(Rf[..., 0]); CV = np.nan_to_num(Rf[..., 1]); QX, QY, QZ = [np.nan_to_num(Rf[..., 2 + i]) for i in range(3)]
print('hood texels', (H > 0.5).sum(), 'valid', valid.mean())
# ---- albedo
rgb = bc[..., :3].copy()
lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
loc = ndi.gaussian_filter(lum * valid, 6) / np.maximum(ndi.gaussian_filter(valid.astype(np.float32), 6), 1e-4)
detail = np.clip(lum / np.maximum(loc, 1), 0.6, 1.5)          # relative cloth detail
base = np.array([40, 37, 38], np.float32)                     # near-black charcoal, faint warm
shade = 1 - np.clip(CV / 0.002, -0.6, 1.0) * 0.45             # folds darker, ridges a bit lighter
newc = base[None, None] * (detail ** 0.8)[..., None] * shade[..., None]
# front crown strip (|x| < ~1.5 cm, top front): blend to neighbourhood mean (detail flattened there)
strip = ss((0.016 - np.abs(QX)) / 0.008) * ss((QZ - 0.86) / 0.03) * ss((0.02 - QY) / 0.04)
newc = newc * (1 - strip)[..., None] + (base[None, None] * shade[..., None]) * strip[..., None]
w = H[..., None]
out = rgb * (1 - w) + newc * w
# dilate the edit into the UV gutters (no bright seams under mip-mapping)
delta = np.where(valid[..., None], out - rgb, 0)
wv = valid & (H > 0.01)
idx = ndi.distance_transform_edt(~wv, return_distances=True, return_indices=True)
dist, (iy, ix) = idx
gut = (~valid) & (dist < 10)
out[gut] = rgb[gut] + delta[iy[gut], ix[gut]]
bco = bc.copy(); bco[..., :3] = np.clip(out, 0, 255)
Image.fromarray(bco.astype(np.uint8), 'RGBA' if bc.shape[2] == 4 else 'RGB').save(OUT + '/basecolor_v5.png')
# ---- normal map: flat on the hood + 30 % of the fine weave
hp = nm - np.stack([ndi.gaussian_filter(nm[..., c], 3) for c in range(3)], -1)
flat = np.array([128, 128, 255], np.float32) + 0.3 * hp
Hn = H.copy(); Hn[gut] = H[iy[gut], ix[gut]]
nmo = nm * (1 - Hn[..., None]) + flat * Hn[..., None]
Image.fromarray(np.clip(nmo, 0, 255).astype(np.uint8)).save(OUT + '/normal_v5.png')
np.save(OUT + '/hoodmask.npy', H)
print('done')
