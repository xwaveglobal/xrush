# dump final body mesh (rest pose) + per-vertex ambient occlusion on the hood region (BVH ray casts)
import bpy, numpy as np, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree
me = bpy.data.objects['Ninja_Body'].data
P = np.array([v.co[:] for v in me.vertices]); F = np.array([p.vertices[:] for p in me.polygons])
uv = np.array([me.uv_layers.active.data[l].uv[:] for p in me.polygons for l in p.loop_indices])
VN = np.array([v.normal[:] for v in me.vertices])
bvh = BVHTree.FromPolygons([tuple(map(tuple, P))][0], [tuple(f) for f in F])
rng = np.random.default_rng(1)
K = 48
dirs = rng.normal(size=(K, 3)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
ao = np.ones(len(P))
idx = np.nonzero(P[:, 2] > 0.58)[0]
MAXD = 0.06
for i in idx:
    n = Vector(VN[i]); o = Vector(P[i]) + n * 0.0015
    occ = 0.0; wsum = 0.0
    for d in dirs:
        c = float(np.dot(d, VN[i]))
        if c <= 0.05:
            continue
        hit = bvh.ray_cast(o, Vector(d), MAXD)
        wsum += c
        if hit[0] is not None:
            occ += c * (1 - hit[3] / MAXD) ** 0.5
    ao[i] = 1 - occ / max(wsum, 1e-6)
np.savez(sys.argv[-1], P=P, F=F, uv=uv, ao=ao, N=VN)
print('AO done', len(idx), ao[idx].mean())
