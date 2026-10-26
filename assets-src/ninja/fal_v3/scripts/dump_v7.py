# v7: dump the final body mesh (rest pose) for scripts/v7_tex.py: positions, faces, loop UVs, vertex normals,
# per-vertex ray-cast AO over the whole body, body-bone weights and the bone segments (for body_folds.features)
# usage: blender -b NinjaCharacter.blend -P dump_v7.py -- OUT.npz
import bpy, numpy as np, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ob = bpy.data.objects['Ninja_Body']; me = ob.data
P = np.array([v.co[:] for v in me.vertices]); F = np.array([p.vertices[:] for p in me.polygons])
uv = np.array([me.uv_layers.active.data[l].uv[:] for p in me.polygons for l in p.loop_indices])
VN = np.array([v.normal[:] for v in me.vertices])
bvh = BVHTree.FromPolygons([tuple(p) for p in P], [tuple(f) for f in F])
rng = np.random.default_rng(1)
dirs = rng.normal(size=(40, 3)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
ao = np.ones(len(P)); MAXD = 0.06
for i in range(len(P)):
    o = Vector(P[i]) + Vector(VN[i]) * 0.0015; occ = 0.0; ws = 0.0
    for d in dirs:
        c = float(np.dot(d, VN[i]))
        if c <= 0.05: continue
        hit = bvh.ray_cast(o, Vector(d), MAXD); ws += c
        if hit[0] is not None: occ += c * (1 - hit[3] / MAXD) ** 0.5
    ao[i] = 1 - occ / max(ws, 1e-6)
gn = {g.index: g.name for g in ob.vertex_groups}
names = [g.name for g in ob.vertex_groups]
Wm = np.zeros((len(P), len(names)))
for v in me.vertices:
    for g in v.groups: Wm[v.index, g.group] = g.weight
arm = bpy.data.objects['Ninja_Rig'].data
segn = [b.name for b in arm.bones]
seg = np.array([[b.head_local[:], b.tail_local[:]] for b in arm.bones])
np.savez(sys.argv[-1], P=P, F=F, uv=uv, ao=ao, N=VN, W=Wm, wnames=np.array(names), segn=np.array(segn), seg=seg)
print('DUMP done', len(P), ao.mean())
