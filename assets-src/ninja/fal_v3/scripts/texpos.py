import trimesh, numpy as np
W='/workspace/free3d/w2/'
g=list(trimesh.load(W+'v2_dec.glb').geometry.values())[0]
V=g.vertices; F=g.faces; UV=g.visual.uv; N=g.vertex_normals; T=2048
uvp=np.c_[UV[:,0]*T,(1-UV[:,1])*T]
pos=np.full((T,T,3),np.nan,np.float32); nrm=np.zeros((T,T,3),np.float32)
for fi in range(len(F)):
    t=uvp[F[fi]]; x0,y0=np.maximum(np.floor(t.min(0)).astype(int)-1,0); x1,y1=np.minimum(np.ceil(t.max(0)).astype(int)+1,T-1)
    gx,gy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
    (ax,ay),(bx,by),(qx,qy)=t; den=(by-qy)*(ax-qx)+(qx-bx)*(ay-qy)
    if abs(den)<1e-14: continue
    l1=((by-qy)*(gx-qx)+(qx-bx)*(gy-qy))/den; l2=((qy-ay)*(gx-qx)+(ax-qx)*(gy-qy))/den; l3=1-l1-l2
    m=(l1>=-0.03)&(l2>=-0.03)&(l3>=-0.03)
    if not m.any(): continue
    i0,i1,i2=F[fi]
    p=l1[...,None]*V[i0]+l2[...,None]*V[i1]+l3[...,None]*V[i2]
    n=l1[...,None]*N[i0]+l2[...,None]*N[i1]+l3[...,None]*N[i2]
    s=pos[y0:y1+1,x0:x1+1]; s[m]=p[m]; s2=nrm[y0:y1+1,x0:x1+1]; s2[m]=n[m]
np.savez_compressed(W+'texpos.npz',pos=pos,nrm=nrm)
print('done', np.isfinite(pos[...,0]).mean())
