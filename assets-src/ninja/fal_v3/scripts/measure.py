import bpy, numpy as np
body=bpy.data.objects['Ninja_Body']; rig=bpy.data.objects['Ninja_Rig']; sc=bpy.context.scene
gi={g.name:g.index for g in body.vertex_groups}
cg=[gi[n] for n in gi if n.startswith('cape')]
w=np.zeros(len(body.data.vertices))
for v in body.data.vertices:
    w[v.index]=sum(g.weight for g in v.groups if g.group in cg)
cape=w>0.5
def ev():
    dg=bpy.context.evaluated_depsgraph_get(); e=body.evaluated_get(dg); me=e.to_mesh()
    c=np.empty(len(me.vertices)*3,np.float32); me.vertices.foreach_get('co',c); e.to_mesh_clear(); return c.reshape(-1,3)
rig.data.pose_position='REST'; sc.frame_set(0); P=ev()
print('REST cape |X| max %.3f  Y max %.3f ; body(non-cape, z 0.3-0.56) |X| max %.3f'%(np.abs(P[cape,0]).max(),P[cape,1].max(),np.abs(P[~cape&(P[:,2]>0.3)&(P[:,2]<0.5),0]).max()))
rig.data.pose_position='POSE'
for a in ['Idle','Run','Jump','Fall','Land','Slide']:
    rig.animation_data.action=bpy.data.actions[a]; e=int(bpy.data.actions[a].frame_range[1]); r=[]
    for f in range(0,e+1,2):
        sc.frame_set(f); P=ev(); C=P[cape]
        r.append((f,np.abs(C[:,0]).max(),np.percentile(np.abs(C[:,0]),98),C[:,1].max(),C[:,2].min()))
    r=np.array(r)
    print('%-5s capeX max %.3f p98 %.3f | Y(back) max %.3f | hem z min %.3f..%.3f'%(a,r[:,1].max(),r[:,2].max(),r[:,3].max(),r[:,4].min(),r[:,4].max()))
