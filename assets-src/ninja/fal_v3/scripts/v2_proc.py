import trimesh, numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
A='/workspace/artifacts/ninja/'; W='/workspace/free3d/w2/'
g=list(trimesh.load(W+'v2_dec.glb').geometry.values())[0]
V=g.vertices; F=g.faces; UV=g.visual.uv; N=g.vertex_normals
tex=np.asarray(g.visual.material.baseColorTexture.convert('RGB')).astype(np.float32); T=tex.shape[0]
img=np.asarray(Image.open(A+'views_v2g_back_belt.png').convert('RGB')).astype(np.float32); R=img.shape[0]
white=img.min(2)>232
lab,_=ndimage.label(white)
border=set(np.unique(np.r_[lab[0],lab[-1],lab[:,0],lab[:,-1]]))-{0}
outside=np.isin(lab,list(border)); holes=white&~outside; sil=~outside
holes=ndimage.binary_dilation(holes,iterations=1)
print('hole px',holes.sum())
P=np.c_[V[:,2],V[:,1]]
def rsil(px):
    m=Image.new('L',(R,R),0); d=ImageDraw.Draw(m)
    for f in F: d.polygon([tuple(px[i]) for i in f],fill=1)
    return np.asarray(m)>0
ys,xs=np.where(sil)
sy=(ys.max()-ys.min())/(P[:,1].max()-P[:,1].min()); sx0=(xs.max()-xs.min())/(P[:,0].max()-P[:,0].min())
oy=ys.min()+P[:,1].max()*sy; cx=(xs.max()+xs.min())/2
best=None; sub=sil[::4,::4]
for sxk in [0.9,0.95,1.0,1.05,1.1]:
  sx=sx0*sxk
  for dx in [-12,-6,0,6,12]:
    for dy in [-12,-6,0,6,12]:
      px=np.c_[P[:,0]*sx+cx-(P[:,0].max()+P[:,0].min())/2*sx+dx, -P[:,1]*sy+oy+dy]
      a=rsil(px)[::4,::4]; iou=(a&sub).sum()/(a|sub).sum()
      if best is None or iou>best[0]: best=(iou,sx,dx,dy)
iou,sx,dx,dy=best; print('reg iou',iou,sx/sx0,dx,dy)
px=np.c_[P[:,0]*sx+cx-(P[:,0].max()+P[:,0].min())/2*sx+dx, -P[:,1]*sy+oy+dy]
meshsil=rsil(px)
depth=V[:,0]
zb=np.full((R,R),np.inf,np.float32)
for fi in range(len(F)):
    t=px[F[fi]]; x0,y0=np.maximum(np.floor(t.min(0)).astype(int),0); x1,y1=np.minimum(np.ceil(t.max(0)).astype(int),R-1)
    if x1<x0 or y1<y0: continue
    gx,gy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
    (ax,ay),(bx,by),(qx,qy)=t; den=(by-qy)*(ax-qx)+(qx-bx)*(ay-qy)
    if abs(den)<1e-12: continue
    l1=((by-qy)*(gx-qx)+(qx-bx)*(gy-qy))/den; l2=((qy-ay)*(gx-qx)+(ax-qx)*(gy-qy))/den; l3=1-l1-l2
    m=(l1>=-1e-4)&(l2>=-1e-4)&(l3>=-1e-4)
    z=l1*depth[F[fi,0]]+l2*depth[F[fi,1]]+l3*depth[F[fi,2]]
    s=zb[y0:y1+1,x0:x1+1]; u=m&(z<s); s[u]=z[u]
# image row -> model y
def row2y(r): return -(r-dy-oy)/sy
# cape vertical range from image: hem region = lower part of the cape
lum=img.mean(2)
leather=(img[...,0]-img[...,2]>28)&(lum>50)&(lum<170)&sil
metal=((img.max(2)-img.min(2))<22)&(lum>95)&(lum<225)&sil&~white
metal=ndimage.binary_opening(metal,iterations=1)
# keep strap/belt only in torso band, buckle near leather
tb_top=np.where(sil.any(1))[0].min()
rows=np.arange(R)[:,None]
yrow=row2y(rows)
band=(yrow>-0.2)&(yrow<0.2)
leather&=band; metal&=band&ndimage.binary_dilation(leather,iterations=6)
print('leather px',leather.sum(),'metal px',metal.sum())
smooth_sil=ndimage.binary_erosion(sil,iterations=2)
uvp=np.c_[UV[:,0]*T,(1-UV[:,1])*T]
out=tex.copy(); wsum=np.zeros((T,T),np.float32)
alpha=np.ones((T,T),np.float32); height=np.zeros((T,T),np.float32)
posY=np.full((T,T),np.nan,np.float32); mtl=np.zeros((T,T),np.float32); lth=np.zeros((T,T),np.float32)
HEM_Y=-0.12   # below this, outside-image cape texels get cut
cuts=0
for fi in range(len(F)):
    t=uvp[F[fi]]; x0,y0=np.maximum(np.floor(t.min(0)).astype(int)-1,0); x1,y1=np.minimum(np.ceil(t.max(0)).astype(int)+1,T-1)
    gx,gy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
    (ax,ay),(bx,by),(qx,qy)=t; den=(by-qy)*(ax-qx)+(qx-bx)*(ay-qy)
    if abs(den)<1e-14: continue
    l1=((by-qy)*(gx-qx)+(qx-bx)*(gy-qy))/den; l2=((qy-ay)*(gx-qx)+(ax-qx)*(gy-qy))/den; l3=1-l1-l2
    m=(l1>=-0.03)&(l2>=-0.03)&(l3>=-0.03)
    if not m.any(): continue
    i0,i1,i2=F[fi]
    L=lambda a: l1*a[i0]+l2*a[i1]+l3*a[i2]
    pos=l1[...,None]*V[i0]+l2[...,None]*V[i1]+l3[...,None]*V[i2]
    nrm=l1[...,None]*N[i0]+l2[...,None]*N[i1]+l3[...,None]*N[i2]; nrm/=np.linalg.norm(nrm,axis=-1,keepdims=True)+1e-9
    ix=L(px[:,0]); iy=L(px[:,1]); z=pos[...,0]
    xi=np.clip(ix.astype(int),0,R-1); yi=np.clip(iy.astype(int),0,R-1)
    zz=zb[yi,xi]; vis=z<=zz+0.008
    layer=(z<=zz+0.035)            # cape outer+inner shell, not legs behind
    facing=-nrm[...,0]
    w=np.clip((facing-0.1)/0.45,0,1)*vis*smooth_sil[yi,xi]*m
    sl=(slice(y0,y1+1),slice(x0,x1+1))
    py=posY[sl]; py[m]=pos[...,1][m]
    # cutouts: interior holes, and hem outside image silhouette (cape layer only, behind the body midline)
    cape=(pos[...,1]<0.12)&(pos[...,1]>-0.42)&(pos[...,0]<0.02)
    cut=m&layer&cape&(holes[yi,xi] | (~sil[yi,xi] & meshsil[yi,xi] & (pos[...,1]<HEM_Y)))
    if cut.any(): a=alpha[sl]; a[cut]=0; cuts+=cut.sum()
    if w.any():
        col=img[yi,xi]
        o=out[sl]; ws=wsum[sl]; upd=w>ws
        o[upd]=tex[sl][upd]*(1-w[upd,None])+col[upd]*w[upd,None]; ws[upd]=w[upd]
        hv=height[sl]; lt=leather[yi,xi]|metal[yi,xi]; hv[upd]=np.maximum(hv[upd],(lt*w)[upd])
        mt=mtl[sl]; mt[upd]=np.maximum(mt[upd],(metal[yi,xi]*w)[upd])
print('cut texels',cuts,'proj texels',(wsum>0).sum())
np.savez_compressed(W+'proc.npz',out=out,wsum=wsum,alpha=alpha,height=height,posY=posY,mtl=mtl,tex=tex)
Image.fromarray((meshsil*120+sil*120).astype(np.uint8)).save(W+'reg_check.png')
