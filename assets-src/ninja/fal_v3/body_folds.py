# Ninja v7 body cloth detail, shared by build_ninja_v3.py (geometry: pressed in along the normal, a few mm) and
# scripts/v7_tex.py (the same creases, sharper, in the normal map + crease shading in the albedo).
# Folds live in bone-local cylindrical coordinates (t along the bone chain, theta around it), so they sit where
# cloth really creases: inner elbow crescents + cuff bunching on the sleeves, knee-pit / knee-front creases and
# thigh diagonals on the trousers, ankle wrinkles on the boots, wrap creases around the neck scarf.
# Blender axes (Z up, the character faces -Y).
import numpy as np

def _ss(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)

FRONT = np.array([0.0, -1.0, 0.0])

def _cyl(P, a, b, chain_len=None):
    a = np.asarray(a, float); b = np.asarray(b, float); e = b - a; L = np.linalg.norm(e); e /= L
    r = P - a; t = (r @ e) / L
    rp = r - np.outer(r @ e, e)
    f = FRONT - (FRONT @ e) * e; f /= np.linalg.norm(f); s = np.cross(e, f)
    th = np.arctan2(rp @ s, rp @ f)          # 0 = front of the limb
    return t, th, np.linalg.norm(rp, axis=1)

def features(P, Wd, SEG):
    """per-vertex fold coordinates. Wd: bone name -> weight array; SEG: bone -> (head, tail).
    returns dict of arrays (all interpolable: angles as cos/sin)"""
    n = len(P); F = {}
    Z = P[:, 2]
    for sd in ('L', 'R'):
        wa = Wd['upper_arm.' + sd] + Wd['forearm.' + sd]
        # arm chain coordinate: 0 at the shoulder, 1 at the elbow, 2 at the wrist
        t1, th1, _ = _cyl(P, *SEG['upper_arm.' + sd]); t2, th2, _ = _cyl(P, *SEG['forearm.' + sd])
        use2 = Wd['forearm.' + sd] > Wd['upper_arm.' + sd]
        F['arm_' + sd] = _ss((wa - 0.35) / 0.4) * (1 - _ss((Wd['hand.' + sd] - 0.25) / 0.3))
        F['arm_t_' + sd] = np.where(use2, 1 + t2, t1)
        th = np.where(use2, th2, th1)
        F['arm_c_' + sd] = np.cos(th); F['arm_s_' + sd] = np.sin(th)
        wl = Wd['thigh.' + sd] + Wd['shin.' + sd]
        u1, ph1, _ = _cyl(P, *SEG['thigh.' + sd]); u2, ph2, _ = _cyl(P, *SEG['shin.' + sd])
        use2 = Wd['shin.' + sd] > Wd['thigh.' + sd]
        F['leg_' + sd] = _ss((wl - 0.35) / 0.4) * _ss((Z - 0.125) / 0.02) * (1 - _ss((Z - 0.33) / 0.02))
        F['leg_t_' + sd] = np.where(use2, 1 + u2, u1)
        ph = np.where(use2, ph2, ph1)
        F['leg_c_' + sd] = np.cos(ph); F['leg_s_' + sd] = np.sin(ph)
        sx = 1 if sd == 'L' else -1
        F['boot_' + sd] = _ss((0.125 - Z) / 0.015) * _ss((Z - 0.055) / 0.012) * (P[:, 0] * sx > 0.02)
    # scarf / neck wrap: around the neck axis, below the rigid hood
    nc = np.array([0.0, -0.02])
    rx = P[:, 0] - nc[0]; ry = P[:, 1] - nc[1]
    F['scarf'] = _ss((Z - 0.535) / 0.015) * (1 - _ss((Z - 0.625) / 0.012)) * (1 - _ss((np.hypot(rx, ry) - 0.2) / 0.03))
    F['scarf_c'] = rx / np.maximum(np.hypot(rx, ry), 1e-6); F['scarf_s'] = ry / np.maximum(np.hypot(rx, ry), 1e-6)
    F['z'] = Z.copy()
    return F

def _crease(d, w):
    return np.exp(-(d / w) ** 2)

def field(F, sharp=False):
    """fold depth (m, positive = pressed in) from features(); sharp=True gives the narrow creases for the normal map"""
    ws = 0.42 if sharp else 1.0
    ds = 0.6 if sharp else 1.0
    h = 0.0
    for sd in ('L', 'R'):
        t = F['arm_t_' + sd]; c = F['arm_c_' + sd]; s = F['arm_s_' + sd]
        th = np.arctan2(s, c)
        # inner elbow (front of the arm at the bend): 3 crescents curving round the joint
        inner = _ss((c + 0.15) / 0.8)
        g = 0
        for k, (t0, a) in enumerate(((0.80, 1.0), (0.96, 1.15), (1.13, 0.9))):
            tc = t0 + 0.07 * (1 - c) + 0.02 * np.sin(2 * th + k)            # crescent: the ends swing toward the wrist
            g = g + a * _crease(t - tc, 0.055 * ws)
        h = h + F['arm_' + sd] * inner * g * 0.0026 * ds
        # cuff bunching just above the glove: wavy rings all around
        g = 0
        for k, t0 in enumerate((1.62, 1.74, 1.85)):
            tc = t0 + 0.035 * np.sin(3 * th + 1.7 * k)
            g = g + _crease(t - tc, 0.045 * ws)
        h = h + F['arm_' + sd] * g * _ss((t - 1.45) / 0.1) * 0.0021 * ds
        # upper sleeve: two long diagonal folds from the armpit
        g = 0
        for k, o in enumerate((0.0, 2.3)):
            d = np.sin(th - 1.6 * t + o)
            g = g + _crease(d, 0.22 * ws) * _ss((t - 0.15) / 0.2) * (1 - _ss((t - 0.75) / 0.15))
        h = h + F['arm_' + sd] * g * 0.0016 * ds
        # trousers
        t = F['leg_t_' + sd]; c = F['leg_c_' + sd]; s = F['leg_s_' + sd]
        th = np.arctan2(s, c)
        back = _ss((-c + 0.1) / 0.8)                                       # knee pit (back of the leg)
        g = 0
        for k, (t0, a) in enumerate(((0.86, 0.8), (0.98, 1.1), (1.10, 0.9), (1.22, 0.6))):
            g = g + a * _crease(t - (t0 - 0.06 * (1 + c) + 0.02 * np.sin(2 * th + k)), 0.05 * ws)
        h = h + F['leg_' + sd] * back * g * 0.0026 * ds
        front = _ss((c - 0.2) / 0.6)                                       # over the knee: two soft horizontal folds
        g = _crease(t - (0.93 + 0.03 * np.sin(2 * th)), 0.06 * ws) + 0.7 * _crease(t - (1.12 + 0.03 * np.cos(2 * th)), 0.06 * ws)
        h = h + F['leg_' + sd] * front * g * 0.0017 * ds
        g = 0                                                              # thigh: diagonals from the crotch / hip
        sg = 1 if sd == 'L' else -1
        for o in (0.0, 2.6):
            g = g + _crease(np.sin(th * sg + 2.2 * t + o), 0.22 * ws) * _ss((t - 0.1) / 0.15) * (1 - _ss((t - 0.7) / 0.12))
        h = h + F['leg_' + sd] * g * 0.0014 * ds
        # lower trouser bunching into the boot top
        g = 0
        for k, t0 in enumerate((1.55, 1.67)):
            g = g + _crease(t - (t0 + 0.03 * np.sin(3 * th + k)), 0.045 * ws)
        h = h + F['leg_' + sd] * g * _ss((t - 1.4) / 0.08) * 0.0018 * ds
        # boots: shallow ankle wrinkles (leather), front of the ankle only
        z = F['z']
        g = 0
        for k, z0 in enumerate((0.072, 0.083, 0.094)):
            g = g + _crease(z - (z0 + 0.003 * np.sin(5 * th + k)), 0.0028 * ws)
        h = h + F['boot_' + sd] * _ss((c + 0.2) / 0.7) * g * 0.0011 * ds
    # scarf: wrap creases running round the neck (slightly spiralling), deeper at the front/sides
    az = np.arctan2(F['scarf_s'], F['scarf_c'])
    z = F['z']
    g = 0
    for k, z0 in enumerate((0.552, 0.571, 0.590, 0.608)):
        g = g + _crease(z - (z0 + 0.006 * np.sin(az + 1.3 * k) + 0.003 * np.sin(3 * az + k)), 0.0045 * ws)
    h = h + F['scarf'] * g * 0.0024 * ds
    return h

FEATURE_KEYS = None
