# Shared cloth-fold field for the ninja hood (v6). Used by build_ninja_v3.py (geometry: broad folds pressed into
# the mesh) and scripts/v6_tex.py (baked normal map + AO/shading: the same folds, plus a sharper crease line).
# Directions are unit vectors from the hood centre C (Blender axes, character faces -Y). A fold is a great-circle
# arc from direction A to B given as (azimuth from the back +Y towards +X, elevation) in degrees.
import numpy as np
C = np.array([0.0, -0.01, 0.74])
# (az_a, el_a, az_b, el_b, depth_m, width, kind)   width = sigma of the angular distance (radians-ish)
FOLDS = [
    # a few long, broad folds radiating from the tip (az 0 / el ~55) down the back and sides, slightly asymmetric
    (5, 58, 14, -20, 0.012, 0.085, 'main'),
    (6, 56, 46, -14, 0.018, 0.105, 'main'), (-5, 56, -40, -16, 0.017, 0.100, 'main'),
    (10, 52, 84, -6, 0.016, 0.100, 'main'), (-10, 52, -80, -8, 0.016, 0.100, 'main'),
    (22, 44, 118, 4, 0.010, 0.080, 'main'), (-22, 44, -116, 2, 0.010, 0.080, 'main'),
    # soft creases at the sides of the face opening (just outside the brim roll)
    (138, 30, 122, -4, 0.008, 0.050, 'face'), (-138, 30, -121, -6, 0.008, 0.050, 'face'),
    (152, 14, 141, -14, 0.006, 0.045, 'face'), (-153, 13, -142, -15, 0.006, 0.045, 'face'),
    # bunching where the hood gathers into the scarf: short near-vertical pleats
    (6, -16, 2, -40, 0.007, 0.060, 'bunch'), (-34, -15, -30, -40, 0.007, 0.060, 'bunch'),
    (36, -14, 40, -40, 0.007, 0.060, 'bunch'), (-66, -12, -64, -38, 0.006, 0.060, 'bunch'),
    (68, -12, 72, -38, 0.006, 0.060, 'bunch'), (-98, -10, -102, -36, 0.006, 0.055, 'bunch'),
    (100, -10, 98, -36, 0.006, 0.055, 'bunch'),
]
GAIN = {'main': 1.35, 'face': 1.2, 'bunch': 1.2}     # overall strength per kind
SAGS = [(0.672, 0.012, 0.006), (0.700, 0.012, 0.004)]   # horizontal sags above the cowl (z, sigma, depth), back half
def _dir(az, el):
    a, e = np.radians(az), np.radians(el)
    return np.array([np.sin(a) * np.cos(e), np.cos(a) * np.cos(e), np.sin(e)])
def _ss(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)
def fold_field(Q, width_scale=1.0, depth_scale=None, kinds=None):
    """depth (m, >0 = pressed in) of the folds at points Q (N,3). width_scale < 1 gives the sharp crease line."""
    V = Q - C; D = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)
    h = np.zeros(len(Q))
    for aa, ea, ab, eb, dep, wid, kind in FOLDS:
        if kinds is not None and kind not in kinds:
            continue
        a, b = _dir(aa, ea), _dir(ab, eb)
        pn = np.cross(a, b); pn /= np.linalg.norm(pn)
        dist = D @ pn
        Dp = D - dist[:, None] * pn
        ang = np.arctan2(Dp @ np.cross(pn, a), Dp @ a)
        s = ang / np.arccos(np.clip(a @ b, -1, 1))
        if kind == 'main':
            taper = _ss((s + 0.05) / 0.45) * _ss((1.08 - s) / 0.3)        # soft at the tip, fading into the cowl
        else:
            taper = _ss(s / 0.25) * _ss((1.0 - s) / 0.3)
        d = dep * GAIN.get(kind, 1.0) * (depth_scale if depth_scale is not None else 1.0)
        h += d * np.exp(-(dist / (wid * width_scale)) ** 2) * taper
    X, Y, Z = Q.T
    for z0, sg, dep in (SAGS if kinds is None or 'sag' in kinds else []):
        d = dep * (depth_scale if depth_scale is not None else 1.0)
        h += d * _ss((Y - 0.02) / 0.05) * np.exp(-((Z - z0) / (sg * max(width_scale, 0.5))) ** 2) * np.exp(-(X / 0.11) ** 2)
    return h
def fold_mask_dirs(Q):
    """az/el/rho of points (rho < ~1.05 = inside the face-opening cone)"""
    V = Q - C; D = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)
    az = np.degrees(np.arctan2(D[:, 0], -D[:, 1])); el = np.degrees(np.arcsin(np.clip(D[:, 2], -1, 1)))
    return az, el, np.sqrt((az / 45) ** 2 + (np.maximum(el, 0) / 34) ** 2)
