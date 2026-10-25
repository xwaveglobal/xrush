import trimesh, numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
A='/workspace/artifacts/ninja/'
s=trimesh.load(A+'fal_tripo_raw.glb'); g=list(s.geometry.values())[0]
V=g.vertices; F=g.faces; UV=g.visual.uv; N=g.vertex_normals
tex=np.asarray(g.visual.material.baseColorTexture.convert('RGB')).astype(np.float32)
T=tex.shape[0]
img=np.asarray(Image.open(A+'views_clean_back.png').convert('RGB')).astype(np.float32); R=img.shape[0]
# image silhouette & holes
white=img.min(2)>232
lab,n=ndimage.label(white)
border=set(np.unique(np.r_[lab[0],lab[-1],lab[:,0],lab[:,-1]]))-{0}
outside=np.isin(lab,list(border)); holes=white&~outside
sil=~outside
print('hole px',holes.sum())
# project vertices: back view, image right=+Z, up=+Y
P=np.c_[V[:,2],V[:,1]]
def raster_sil(sx,sy,ox,oy):
    px=np.c_[P[:,0]*sx+ox, -P[:,1]*sy+oy]
    m=Image.new('L',(R,R),0)
    from PIL import ImageDraw
    d=ImageDraw.Draw(m)
    for f in F: d.polygon([tuple(px[i]) for i in f],fill=1)
    return np.asarray(m)>0, px
ys,xs=np.where(sil)
sy=(ys.max()-ys.min())/(P[:,1].max()-P[:,1].min()); sx=(xs.max()-xs.min())/(P[:,0].max()-P[:,0].min())
ox=xs.min()-P[:,0].min()*sx; oy=ys.min()+P[:,1].max()*sy
best=None
# coarse refine on downsampled silhouettes
sub=sil[::4,::4]
for ks in [0.94,0.97,1.0,1.03]:
  for dx in [-16,-8,0,8,16]:
    for dy in [-16,-8,0,8,16]:
        a,_=raster_sil(sx*ks,sy*ks,ox+dx+(1-ks)*(R/2-ox)*0,oy+dy)
        a=a[::4,::4]; iou=(a&sub).sum()/(a|sub).sum()
        if best is None or iou>best[0]: best=(iou,ks,dx,dy)
print('reg',best,sx,sy)
iou,ks,dx,dy=best; sx*=ks; sy*=ks; ox+=dx; oy+=dy
px=np.c_[P[:,0]*sx+ox, -P[:,1]*sy+oy]; depth=V[:,0]   # camera at -X: smaller x = closer
# z-buffer in image space
zb=np.full((R,R),np.inf,np.float32)
def tri_raster(p2, extra_cb):
    pass
tri=px[F]; 
for fi in range(len(F)):
    t=tri[fi]; x0,y0=np.floor(t.min(0)).astype(int); x1,y1=np.ceil(t.max(0)).astype(int)
    x0=max(x0,0);y0=max(y0,0);x1=min(x1,R-1);y1=min(y1,R-1)
    if x1<x0 or y1<y0: continue
    gx,gy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
    (ax,ay),(bx,by),(cx,cy)=t
    den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
    if abs(den)<1e-12: continue
    l1=((by-cy)*(gx-cx)+(cx-bx)*(gy-cy))/den; l2=((cy-ay)*(gx-cx)+(ax-cx)*(gy-cy))/den; l3=1-l1-l2
    m=(l1>=-1e-4)&(l2>=-1e-4)&(l3>=-1e-4)
    if not m.any(): continue
    z=l1*depth[F[fi,0]]+l2*depth[F[fi,1]]+l3*depth[F[fi,2]]
    sub=zb[y0:y1+1,x0:x1+1]; upd=m&(z<sub); sub[upd]=z[upd]
np.save('fix/zb.npy',zb)
# texel rasterisation in UV space
uvp=np.c_[UV[:,0]*T, (1-UV[:,1])*T]
out=tex.copy(); wsum=np.zeros((T,T),np.float32)
smooth_sil=ndimage.binary_erosion(sil,iterations=3)
for fi in range(len(F)):
    t=uvp[F[fi]]; x0,y0=np.floor(t.min(0)).astype(int); x1,y1=np.ceil(t.max(0)).astype(int)
    x0=max(x0-1,0);y0=max(y0-1,0);x1=min(x1+1,T-1);y1=min(y1+1,T-1)
    gx,gy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
    (ax,ay),(bx,by),(cx,cy)=t
    den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
    if abs(den)<1e-14: continue
    l1=((by-cy)*(gx-cx)+(cx-bx)*(gy-cy))/den; l2=((cy-ay)*(gx-cx)+(ax-cx)*(gy-cy))/den; l3=1-l1-l2
    m=(l1>=-0.02)&(l2>=-0.02)&(l3>=-0.02)
    if not m.any(): continue
    i0,i1,i2=F[fi]
    nrm=l1[...,None]*N[i0]+l2[...,None]*N[i1]+l3[...,None]*N[i2]
    nrm/=np.linalg.norm(nrm,axis=-1,keepdims=True)+1e-9
    facing=-nrm[...,0]   # toward camera at -X
    w=np.clip((facing-0.15)/0.45,0,1)
    ix=l1*px[i0,0]+l2*px[i1,0]+l3*px[i2,0]; iy=l1*px[i0,1]+l2*px[i1,1]+l3*px[i2,1]
    z=l1*depth[i0]+l2*depth[i1]+l3*depth[i2]
    xi=np.clip(ix.astype(int),0,R-1); yi=np.clip(iy.astype(int),0,R-1)
    vis=z<=zb[yi,xi]+0.01
    insil=smooth_sil[yi,xi]
    w=w*vis*insil*m
    if not w.any(): continue
    col=img[yi,xi]
    hole=holes[yi,xi]
    col[hole]=np.array([12,10,11],np.float32)  # dark hole look
    sub=out[y0:y1+1,x0:x1+1]; ws=wsum[y0:y1+1,x0:x1+1]
    upd=w>ws
    sub[upd]=(tex[y0:y1+1,x0:x1+1][upd]*(1-w[upd,None])+col[upd]*w[upd,None]); ws[upd]=w[upd]
print('texels projected',(wsum>0).sum())
np.save('fix/out_raw.npy',out); np.save('fix/wsum.npy',wsum)
