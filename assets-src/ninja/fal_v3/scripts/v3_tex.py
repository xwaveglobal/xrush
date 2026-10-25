# v3 texture fixes on the v2 basecolor (projection-space edits mapped back to texels):
#  1. hood side streak removal  2. eyes: white whites, black pupils, black mask band  3. skin desaturate
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
W='/workspace/free3d/w2/'
d=np.load(W+'texpos.npz'); pos=d['pos']; nrm=d['nrm']
bc=np.asarray(Image.open(W+'basecolor_v2.png')).astype(np.float32)
rgb=bc[...,:3].copy()
valid=np.isfinite(pos[...,0])
X,Y,Z=[np.nan_to_num(pos[...,i]) for i in range(3)]
def nfill(val,ok,sig):
    w=ndi.gaussian_filter(ok.astype(np.float32),sig)
    out=np.stack([ndi.gaussian_filter(val[...,c]*ok,sig) for c in range(3)],-1)
    return out/np.maximum(w[...,None],1e-4), w
# ---------- 1. hood streak (side projections, 1 mm cells)
for s in (1,-1):
    v=valid&(nrm[...,2]*s>0.15)&(Y>0.17)&(X<0.11)
    I=np.where(v)
    cx=((X[I]+0.22)*1000).astype(int).clip(0,439); cy=((0.5-Y[I])*1000).astype(int).clip(0,519)
    o=np.argsort(Z[I]*s)
    grid=np.zeros((520,440,3),np.float32); has=np.zeros((520,440),bool)
    grid[cy[o],cx[o]]=rgb[I][o]; has[cy[o],cx[o]]=True
    lum=grid.mean(2)
    med=ndi.median_filter(np.where(has,lum,np.nan_to_num(np.median(lum[has]))),size=45)
    C=rgb[I]; L=C.mean(1); ex=L-med[cy,cx]; warm=C[:,0]-C[:,2]
    st=(ex>5)&(warm>8)
    sg=np.zeros((520,440),bool); sg[cy[st],cx[st]]=True
    sg=ndi.binary_dilation(ndi.binary_closing(sg,iterations=2),iterations=2)
    ok=has&~sg
    fill,_=nfill(grid,ok,7)
    t=np.clip((ex+2)/8,0,1)*sg[cy,cx]
    newc=C*(1-t[:,None])+(fill[cy,cx]+(C-C.mean(1,keepdims=True))*0.3)*t[:,None]
    rgb[I]=newc
    print('streak side',s,'texels changed',(t>0.05).sum())
# ---------- 2. face (front projection, 1 mm cells; z in [-0.16,0.16], y in [0.1,0.45])
v=valid&(nrm[...,0]>0.2)&(X>0.05)&(Y>0.1)&(Y<0.45)&(np.abs(Z)<0.16)
I=np.where(v)
fz=((Z[I]+0.16)*1000).astype(int).clip(0,319); fy=((0.45-Y[I])*1000).astype(int).clip(0,349)
C=rgb[I]; mx,mn=C.max(1),C.min(1); sat=mx-mn; L=C.mean(1)
grid=np.zeros((350,320,3),np.float32); o=np.argsort(X[I]); grid[fy[o],fz[o]]=C[o]
def ell(cz,cy,rz,ry):
    return ((fz-cz)/rz)**2+((fy-cy)/ry)**2<1
eyes=[]
from scipy.spatial import Delaunay
for cz in (95,225):   # eye centres in grid px
    E=ell(cz,182,37,31)
    cand=E&((mn>95)|((C[:,0]-C[:,2]>14)&(L<150)&(L>25)))
    g=np.zeros((350,320),bool); g[fy[cand],fz[cand]]=True
    g=ndi.binary_opening(ndi.binary_fill_holes(ndi.binary_closing(g,iterations=3)),iterations=2)
    lab,n=ndi.label(g)
    if n>1:
        sizes=ndi.sum(g,lab,range(1,n+1)); g=lab==(1+np.argmax(sizes))
    pts=np.argwhere(g)                      # (fy,fz)
    tri=Delaunay(pts)
    eye=(tri.find_simplex(np.c_[fy,fz])>=0)&E
    ec=pts.mean(0)
    icz=ec[1]+(6 if cz<160 else -6); icy=ec[0]+3   # pupils slightly toward the nose and down: angry stare
    eyes.append((eye,icz,icy,0))
    print('eye',cz,'texels',eye.sum(),'pupil centre',icz,icy)
neweye=np.zeros_like(C)
alleye=np.zeros(len(C),bool)
for eye,icz,icy,_ in eyes:
    r=np.hypot(fz-icz,(fy-icy)*1.05)
    white=np.array([240,238,232],np.float32); black=np.array([12,11,12],np.float32)
    k=np.clip((r-10.5)/2.0,0,1)[:,None]          # pupil radius ~10.5 mm (1px soft edge)
    col=black*(1-k)+white*k
    hl=np.hypot(fz-(icz-4),fy-(icy-4))<2.6       # small catchlight
    col[hl]=white
    neweye[eye]=col[eye]; alleye|=eye
# soft dark rim at the eye border (2 px)
eg=np.zeros((350,320),bool); eg[fy[alleye],fz[alleye]]=True
dist=ndi.distance_transform_edt(eg)
rim=np.clip((dist[fy,fz]-0.5)/2.0,0,1)[:,None]
neweye=neweye*rim+np.array([15,14,15])*(1-rim)
C2=C.copy(); C2[alleye]=neweye[alleye]
# mask band: low-saturation grey cloth inside the face opening (not eyes, not skin), pushed to near black
face_open=((fz-160)/112)**2+((fy-200)/108)**2<1
skin=(C[:,0]>95)&(C[:,0]-C[:,2]>38)
warm=C[:,0]-C[:,2]
band=face_open&~alleye&~skin&(L<150)&(fy<262)
medL=np.median(L[band])
shade=np.clip(L/medL,0.6,1.4)[:,None]
C2[band]=np.array([20,19,21])*shade[band]*0.85+C[band]*0.12
# nose highlight blob -> skin
nose=face_open&(np.hypot(fz-160,fy-230)<16)&(mn>140)
C2[nose]=np.array([178,118,86])
# chin: grey / dark stripes left by the generator between the skin and the scarf -> flat skin tone
cheek=face_open&skin&(fy>205)&(fy<250)
skin_med=np.median(C[cheek],axis=0)
chin=(np.abs(fz-160)<105)&(fy>=268)&(fy<=322)&(L>=50)&~alleye
print('chin',chin.sum(),'skin med',skin_med)
# skin: desaturate ~30%, slightly darker
sk=face_open&skin&~alleye
gm=C2[sk].mean(1,keepdims=True)
C2[sk]=(C2[sk]*0.68+gm*0.32)*0.95+np.array([4,4,6])
rgb[I]=C2
# lower face / chin (incl. normals pointing down): texels on the fitted face sphere -> flat skin tone
HC=np.array([0.04426,0.21433,0.0]); HR=0.12655
rr=np.linalg.norm(np.nan_to_num(pos)-HC,axis=-1)-HR
mouth=(np.abs(Z)<0.045)&(Y>0.176)
chin2=valid&(rr>-0.009)&(rr<0.0045)&(Y<0.205)&(X>0.03)&(np.abs(Z)<0.118)&~mouth
gsk=skin_med.mean()
skin_d=(skin_med*0.68+gsk*0.32)*0.95+np.array([4,4,6])
rgb[chin2]=skin_d*(1+0.03*(np.random.default_rng(2).random((chin2.sum(),1))-0.5))
mz=valid&(rr>-0.009)&(rr<0.0045)&mouth&(Y<0.215)&(X>0.03)
Lm2=rgb.mean(2)
mouth_skin=mz&(Lm2>70)
mouth_line=mz&(Lm2<=70)
rgb[mouth_skin]=skin_d
rgb[mouth_line]=rgb[mouth_line]*0.6+np.array([40,22,16])*0.4
print('chin2',chin2.sum())
print('band',band.sum(),'skin',sk.sum(),'nose',nose.sum())
out=bc.copy(); out[...,:3]=np.clip(rgb,0,255)
Image.fromarray(out.astype(np.uint8)).save(W+'basecolor_v3.png')
# emission mask: eye whites only
em=np.zeros(rgb.shape[:2],np.float32)
ew=alleye&(neweye.mean(1)>200)
em[I[0][ew],I[1][ew]]=1
em=ndi.grey_dilation(em,size=3)
Image.fromarray((em*255).astype(np.uint8)).save(W+'emit_v3.png')
