# v6 hood texture bake (Blender coordinates). From the v4 albedo / normal sources and a dump of the final
# rest-pose mesh (positions, faces, loop UVs, per-vertex AO from dump_ao.py):
#  - hood cloth near-black charcoal (as v5), detail kept, faint front-crown strip blended away
#  - baked shading so the folds read at game distance: ray-cast AO + mesh cavity + the sharp crease line of the
#    shared fold field (hood_folds.py), ridges between folds slightly lifted
#  - normal map: the same folds' sharp crease (narrower than the geometry can hold) + a fine fabric weave / slub,
#    computed as a height field on the 3D surface and converted to tangent space via the UV jacobian
# usage: blender -b NinjaCharacter.blend -P dump_ao.py -- final_ao.npz   (rest pose, built with the v6 geometry)
#        python v6_tex.py final_ao.npz BASECOLOR_v4.png NORMAL_v4.png OUTDIR   (v4 sources = the v4 webp as PNG)
#        -> OUTDIR/basecolor_v6.png, normal_v6.png -> webp q90 (alpha 100) / q92 into fal_v3/
import numpy as np, sys, os
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import hood_folds as hf
d = np.load(sys.argv[1])
Q = d['P']; F = d['F']; UV = d['uv']; AO = d['ao']
bc = np.asarray(Image.open(sys.argv[2])).astype(np.float32)
nm = np.asarray(Image.open(sys.argv[3]).convert('RGB')).astype(np.float32)
OUT = sys.argv[4]
T = bc.shape[0]
ss = hf._ss
n = len(Q)
E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
deg = np.bincount(E.ravel(), minlength=n).astype(float)
def nb_mean(A):
    acc = np.zeros_like(A); np.add.at(acc, E[:, 0], A[E[:, 1]]); np.add.at(acc, E[:, 1], A[E[:, 0]])
    return acc / np.maximum(deg, 1).reshape((-1,) + (1,) * (A.ndim - 1))
fn = np.cross(Q[F[:, 1]] - Q[F[:, 0]], Q[F[:, 2]] - Q[F[:, 0]])
vn = np.zeros_like(Q)
for k in range(3): np.add.at(vn, F[:, k], fn)
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
cav = ((nb_mean(Q) - Q) * vn).sum(1)
for _ in range(2): cav = 0.5 * cav + 0.5 * nb_mean(cav)
X, Y, Z = Q.T
az, el, rho = hf.fold_mask_dirs(Q)
face = (Y < -0.10) & (np.abs(X) < 0.135) & (Z < 0.87) & (Z > 0.58) & (rho < 1.02)
hoodv = ss((Z - 0.625) / 0.03) * (~face)
R = np.linalg.norm(Q - hf.C, axis=1)
foldm = ss((rho - 1.12) / 0.22) * ss((Z - 0.615) / 0.045) * (~face) * ss((R - 0.14) / 0.02)
for _ in range(2): foldm = 0.5 * foldm + 0.5 * nb_mean(foldm)
hb = hf.fold_field(Q) * foldm                         # broad (geometry) fold depth per vertex
ridge = np.clip(nb_mean(nb_mean(nb_mean(hb))) - hb, -1, 1)
for _ in range(4): ridge = nb_mean(ridge)
def raster(vals):
    out = np.full((T, T) + vals.shape[1:], np.nan, np.float32)
    uvp = np.c_[UV[:, 0] * T, (1 - UV[:, 1]) * T]
    # paint the scan's few huge stretched-UV faces first: where UVs overlap, the small (real) faces win
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
Rf = raster(np.c_[hoodv, cav, AO, foldm, ridge, Q, vn])
valid = np.isfinite(Rf[..., 0])
Rf = np.nan_to_num(Rf)
H, CV, AOt, FM, RG = [Rf[..., i] for i in range(5)]
QT = Rf[..., 5:8]; NT = Rf[..., 8:11]
print('hood texels', int((H > 0.5).sum()), 'valid %.3f' % valid.mean())
# ---- per-texel analytic fields on the 3D surface
sel = valid & (H > 0.01)
qs = QT[sel]
h_sharp = np.zeros((T, T), np.float32); h_full = np.zeros((T, T), np.float32)
h_sharp[sel] = hf.fold_field(qs, width_scale=0.42, depth_scale=0.55) * FM[sel]
h_full[sel] = hf.fold_field(qs) * FM[sel]
# the creases beside the face opening live mostly in the texture (the brim geometry stays clean): looser mask
az_t, el_t, rho_t = hf.fold_mask_dirs(qs)
fmf = hf._ss((rho_t - 1.0) / 0.12) * hf._ss((qs[:, 2] - 0.64) / 0.04) * hf._ss((np.linalg.norm(qs - hf.C, axis=1) - 0.15) / 0.02)
hface = hf.fold_field(qs, width_scale=0.5, depth_scale=1.3, kinds=('face',)) * fmf
h_sharp[sel] += hface; h_full[sel] += hface
# fabric: fine twill-like weave (3D, ~2.6 mm pitch, diagonal) + slub noise
lam = 0.0026
e1 = np.array([0.8, 0.45, 0.4]); e1 /= np.linalg.norm(e1); e2 = np.array([-0.45, 0.8, 0.4]); e2 /= np.linalg.norm(e2)
weave = np.zeros((T, T), np.float32)
p1 = qs @ e1 / lam; p2 = qs @ e2 / lam
weave[sel] = 0.5 * np.sin(2 * np.pi * (p1 + 0.5 * np.round(p2))) * 0.5 + 0.5 * np.sin(2 * np.pi * p2) * 0.5
rng = np.random.default_rng(7)
slub = ndi.gaussian_filter(rng.normal(size=(T, T)).astype(np.float32), 1.6); slub /= slub[sel].std() + 1e-9
h_fab = (0.00009 * weave + 0.00006 * slub) * (H > 0.01)
# ---- albedo
rgb = bc[..., :3].copy()
lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
loc = ndi.gaussian_filter(lum * valid, 6) / np.maximum(ndi.gaussian_filter(valid.astype(np.float32), 6), 1e-4)
detail = np.clip(lum / np.maximum(loc, 1), 0.7, 1.35)
base = np.array([40, 37, 38], np.float32)
ao_t = np.clip((AOt - 0.35) / 0.6, 0, 1) ** 0.8                     # ray-cast AO (inside folds, under the brim)
crease = np.clip(h_sharp / 0.0045, 0, 1)                             # sharp line at the fold bottoms
deep = np.clip(h_full / 0.018, 0, 1)
shade = (0.55 + 0.45 * ao_t) * (1 - 0.35 * crease - 0.22 * deep) * (1 - np.clip(CV / 0.002, -0.5, 1.0) * 0.25)
shade *= 1 + 0.5 * np.clip(RG / 0.004, 0, 1) * FM                  # ridges between folds a little lighter
shade *= 1 + 0.06 * np.clip(weave, -1, 1) * (H > 0.01)               # faint weave in the colour too
newc = base[None, None] * (detail ** 0.6)[..., None] * shade[..., None]
strip = ss((0.016 - np.abs(QT[..., 0])) / 0.008) * ss((QT[..., 2] - 0.86) / 0.03) * ss((0.02 - QT[..., 1]) / 0.04)
newc = newc * (1 - strip)[..., None] + (base[None, None] * shade[..., None]) * strip[..., None]
w = H[..., None]
out = rgb * (1 - w) + newc * w
delta = np.where(valid[..., None], out - rgb, 0)
dist, (iy, ix) = ndi.distance_transform_edt(~(valid & (H > 0.01)), return_distances=True, return_indices=True)
gut = (~valid) & (dist < 10)
out[gut] = rgb[gut] + delta[iy[gut], ix[gut]]
bco = bc.copy(); bco[..., :3] = np.clip(out, 0, 255)
Image.fromarray(bco.astype(np.uint8), 'RGBA' if bc.shape[2] == 4 else 'RGB').save(OUT + '/basecolor_v6.png')
# ---- normal map from the height field (metres) via the UV jacobian
hgt = h_sharp + h_fab
# fill outside the valid texels with the nearest valid value (no false slopes at island borders)
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
sT = np.where(ok, hx / np.maximum(lx, 1e-9), 0)          # slope along +u  (tangent)
sB = np.where(ok, -hy / np.maximum(ly, 1e-9), 0)         # slope along +v  (bitangent; image y runs down)
# handedness of the UV map at this texel: mirrored islands flip the bitangent relative to N x T
nT = np.where(ok[..., None], qx / np.maximum(lx, 1e-9)[..., None], 0)
nB = np.where(ok[..., None], -qy / np.maximum(ly, 1e-9)[..., None], 0)
hand = np.sign(np.einsum('ijk,ijk->ij', np.cross(NT, nT), nB)); hand[hand == 0] = 1
# the fold height is a depression (pressed in): surface z = -hgt
K = 1.0
nx = K * sT; ny = K * sB                                   # n ~ (+dh/dT, +dh/dB, 1) for z = -h
for A in (nx, ny):
    A[:] = ndi.gaussian_filter(A, 0.7)
nz = np.ones_like(nx)
nn = np.stack([nx, ny, nz], -1); nn /= np.linalg.norm(nn, axis=-1, keepdims=True)
# base: v5 behaviour (flattened scan noise, 25 % of its fine detail), then add our slopes (partial-derivative blend)
hp = nm - np.stack([ndi.gaussian_filter(nm[..., c], 3) for c in range(3)], -1)
flat = np.array([128, 128, 255], np.float32) + 0.25 * hp
fb = flat / 127.5 - 1
pdx = fb[..., 0] / np.maximum(fb[..., 2], 0.3) + nn[..., 0] / nn[..., 2]
pdy = fb[..., 1] / np.maximum(fb[..., 2], 0.3) + nn[..., 1] / nn[..., 2]
comb = np.stack([pdx, pdy, np.ones_like(pdx)], -1); comb /= np.linalg.norm(comb, axis=-1, keepdims=True)
newn = (comb + 1) * 127.5
Hn = H.copy(); Hn[gut] = H[iy[gut], ix[gut]]
newn_g = newn.copy(); newn_g[gut] = newn[iy[gut], ix[gut]]
nmo = nm * (1 - Hn[..., None]) + newn_g * Hn[..., None]
Image.fromarray(np.clip(nmo, 0, 255).astype(np.uint8)).save(OUT + '/normal_v6.png')
np.save(OUT + '/hoodmask.npy', H)
print('mirrored hood texels', int(((hand < 0) & (H > 0.5)).sum()), 'slope max', float(np.abs(nx[H > 0.5]).max()))
print('done')
