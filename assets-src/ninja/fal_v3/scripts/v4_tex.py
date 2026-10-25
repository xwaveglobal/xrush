# v4 texture fixes on top of v3 (basecolor_v3.png) + normal map clean-up on the hood back.
#  1. hood: repaint the grey back-repair patch + the vertical seam, soft fold shading, flatten the normal map there
#  2. face: smaller skin band (mask lower, scarf pulled up over the chin), neutral skin tone
#  3. leftover streak tint on the hood sides, skin-toned rim at the scarf top
import numpy as np, sys
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
W='/workspace/free3d/w2/'; O='/workspace/free3d/v4/'
d=np.load(W+'texpos.npz'); pos=d['pos']; nrm=d['nrm']
bc=np.asarray(Image.open(W+'basecolor_v3.png')).astype(np.float32)
rgb=bc[...,:3].copy(); src=rgb.copy()
nm=np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(np.float32)   # normal_v2
valid=np.isfinite(pos[...,0]); X,Y,Z=[np.nan_to_num(pos[...,i]) for i in range(3)]
NX=nrm[...,0]
def sstep(t): t=np.clip(t,0,1); return t*t*(3-2*t)
rng=np.random.default_rng(4)
# ---------------------------------------------------------------- 1. hood back
hood=valid&(Y>0.185)&~((X>0.03)&(np.abs(Z)<0.125)&(Y<0.33))       # everything above the scarf except the face
back=hood&(NX<0.05)&(X<0.06)
wb=sstep((0.15-np.abs(Z))/0.05)*sstep((0.05-X)/0.04)*back            # central back band (the repair patch)
# back projection grid (1 mm): a = (0.25-Z), b = (0.5-Y)
I=np.where(back); ga=((0.25-Z[I])*1000).astype(int).clip(0,499); gb=((0.5-Y[I])*1000).astype(int).clip(0,399)
o=np.argsort(-X[I])                       # nearest to a viewer behind wins
G=np.zeros((400,500,3),np.float32); H=np.zeros((400,500),bool)
G[gb[o],ga[o]]=src[I][o]; H[gb[o],ga[o]]=True
side=H.copy(); side[:,int((0.25-0.13)*1000):int((0.25+0.13)*1000)]=False   # sides only (|Z|>0.13)
def nconv(g,ok,s):
    w=ndi.gaussian_filter(ok.astype(np.float32),s)
    return np.stack([ndi.gaussian_filter(g[...,c]*ok,s) for c in range(3)],-1)/np.maximum(w[...,None],1e-5)
low=nconv(G,side,(14,40))                 # smooth colour, mostly from the same height on both sides
lowG=nconv(G,H,6)
hp=np.clip(G-nconv(G,H,3),-18,18)*ndi.binary_erosion(H,iterations=12)[...,None]   # fine cloth detail, away from outlines
la=np.arange(500); shift=np.where(la<250,-140,140)
det=hp[:,np.clip(la+shift,0,499)]
A=(0.25-Z[I]); B=(0.5-Y[I])
# soft folds: curves falling from the tip region (Z~0, Y~0.47) down and outward
fold=np.zeros(len(A))
for s in (-1,1):
    for z0,k,dep in ((0.03,0.30,0.07),(0.07,0.50,0.05),(0.11,0.55,0.04)):
        zc=s*(z0+k*np.clip(0.47-Y[I],0,None)**1.4)
        dd=np.abs(Z[I]-zc)
        fold+=dep*np.exp(-(dd/0.009)**2)*sstep((0.43-Y[I])/0.07)*sstep((Y[I]-0.2)/0.06)
fold=np.clip(fold,0,0.12)
# low-frequency colour: inverse-distance mean of the nearest good cloth texels in 3D (outside the band)
good=hood&(wb<0.02)&~((np.abs(Z)<0.016)&(Y>0.28))&(NX<0.3)
gi=np.where(good); sel=rng.choice(len(gi[0]),min(250000,len(gi[0])),replace=False)
gP=np.c_[X[gi][sel],Y[gi][sel],Z[gi][sel]]; gC=src[gi][sel]
trg=cKDTree(gP)
bi=wb[I]>0.0
dq,iq=trg.query(np.c_[X[I][bi],Y[I][bi],Z[I][bi]],k=96)
wq=1/np.maximum(dq,0.004)**2
lowc=np.zeros((len(A),3)); lowc[bi]=(gC[iq]*wq[...,None]).sum(1)/wq.sum(1)[:,None]
# smooth that field once more in the back grid to remove k-NN steps
Gl=np.zeros((400,500,3),np.float32); Hl=np.zeros((400,500),bool); Gl[gb[o],ga[o]]=lowc[o]; Hl[gb[o],ga[o]]=bi[o]
lowc=nconv(Gl,Hl,8)[gb,ga]
new=lowc+0.8*det[gb,ga]
new=new*(1-fold)[:,None]*(1+0.04*(rng.random((len(A),1))-0.5))
w=wb[I][:,None]
rgb[I]=src[I]*(1-w)+new*w
# folds also lightly on the rest of the back (outside the band)
rgb[I]*= (1-fold*0.6*(1-w[:,0]))[:,None]
print('hood back band texels',(wb>0.05).sum())
# seam: |Z|<~1.3 cm over the whole hood (incl. the top/front of it) -> median of the nearby non-seam cloth
seam=hood&(np.abs(Z)<0.014)&(Y>0.28)&~((X>0.03)&(Y<0.36))
pool=hood&(np.abs(Z)>0.016)&(np.abs(Z)<0.04)&(Y>0.26)
P=np.c_[X[pool],Y[pool],Z[pool]]; Cpool=rgb[pool]
tr=cKDTree(P); S=np.where(seam)
_,ix=tr.query(np.c_[X[S],Y[S],Z[S]],k=12)
ws=sstep((0.014-np.abs(Z[S]))/0.005)[:,None]
rgb[S]=rgb[S]*(1-ws)+np.median(Cpool[ix],axis=1)*ws
print('seam texels',len(S[0]))
# normal map: keep only fine weave (35 %) in the band + seam; flat tangent normal elsewhere there
nb=np.maximum(wb,np.where(seam,sstep((0.016-np.abs(Z))/0.006),0))
nb=ndi.grey_dilation(nb,size=3)
blur=np.stack([ndi.gaussian_filter(nm[...,c],3) for c in range(3)],-1)
flat=np.array([128,128,255],np.float32)
nm2=nm*(1-nb[...,None])+(flat+0.35*(nm-blur))*nb[...,None]
# ---------------------------------------------------------------- 3a. streak leftovers on the hood sides
for s in (1,-1):
    v=valid&(nrm[...,2]*s>0.1)&(Y>0.17)&(X<0.12)&hood
    I=np.where(v)
    cx=((X[I]+0.22)*1000).astype(int).clip(0,439); cy=((0.5-Y[I])*1000).astype(int).clip(0,519)
    o=np.argsort(Z[I]*s)
    g=np.zeros((520,440,3),np.float32); h=np.zeros((520,440),bool); g[cy[o],cx[o]]=rgb[I][o]; h[cy[o],cx[o]]=True
    C=rgb[I]; L=C.mean(1); warm=C[:,0]-C[:,2]
    lum=g.mean(2); medL=ndi.median_filter(np.where(h,lum,np.median(lum[h])),size=61)
    gw=g[...,0]-g[...,2]; medW=ndi.median_filter(np.where(h,gw,np.median(gw[h])),size=61)
    ex=(L-medL[cy,cx])+(warm-medW[cy,cx])*0.8
    stt=ex>3
    sg=np.zeros((520,440),bool); sg[cy[stt],cx[stt]]=True
    sg=ndi.binary_opening(sg,iterations=1); sg=ndi.binary_dilation(sg,iterations=3)
    fill=nconv(g,h&~sg,9)
    t=np.clip((ex+1)/6,0,1)*sg[cy,cx]
    rgb[I]=C*(1-t[:,None])+(fill[cy,cx]+(C-C.mean(1,keepdims=True))*0.3)*t[:,None]
    print('streak2 side',s,(t>0.05).sum())
# ---------------------------------------------------------------- 2. face
v=valid&(NX>0.0)&(X>0.0)&(Y>0.1)&(Y<0.45)&(np.abs(Z)<0.16)
I=np.where(v)
fz=((Z[I]+0.16)*1000).astype(int).clip(0,319); fy=((0.45-Y[I])*1000).astype(int).clip(0,349)
C=rgb[I].copy(); L=C.mean(1); warm=C[:,0]-C[:,2]
grid=np.zeros((350,320,3),np.float32); o=np.argsort(X[I]); grid[fy[o],fz[o]]=C[o]
eyesw=(C.min(1)>200)|(L<25)&(((fz-95)/40)**2+((fy-182)/34)**2<1)|(L<25)&(((fz-225)/40)**2+((fy-182)/34)**2<1)
skin=(C[:,0]>90)&(warm>30)
face_open=((fz-160)/112)**2+((fy-200)/108)**2<1
# new layout (grid px): mask down to fy 236 (follows the old lower edge at the sides), skin band to fy 268,
# below it the scarf is pulled up over the chin
mask_lo=236+0.0035*(fz-160)**2*0.6                    # slightly curved lower mask edge (lower at the sides)
mask_lo=np.minimum(mask_lo,246)
chin_y=268-0.0016*(fz-160)**2                         # scarf edge, rising toward the cheeks
nose=(np.hypot(fz-160,(fy-222)*1.1)<17)
# a) mask: skin texels above mask_lo (except the nose) -> mask black
mk=face_open&skin&(fy<mask_lo)&~nose
mband=face_open&~skin&(fy<mask_lo)&(L<150)
ref_mask=np.median(C[mband],axis=0) if mband.any() else np.array([18,17,19])
C[mk]=ref_mask*(0.9+0.2*rng.random((mk.sum(),1)))
# b) skin band -> neutral tone, keep the shading (luminance ratio)
sk=face_open&skin&(fy>=mask_lo-1)&(fy<chin_y) | (face_open&skin&nose)
target=np.array([196,152,128],np.float32)
r=np.clip(L[sk]/np.median(L[sk]),0.75,1.2)[:,None]
C[sk]=target*r
hl=sk&nose&(src[I].min(1)>140)
C[hl]=target*1.05
# c) chin -> scarf: copy the scarf wraps from 44 mm lower in the same column, darkened edge at the top
ch=(face_open|skin|(fy>=296))&(fy>=chin_y)&(fy<324)
srcrow=np.clip(324+((fy[ch]-chin_y[ch]).astype(int)%24),0,349)   # wraps copied from the scarf below the old rim
scol=grid[srcrow,fz[ch]]
bad=scol.max(1)<1
scol[bad]=np.array([40,30,27])
edge=np.clip((fy[ch]-chin_y[ch])/5,0,1)[:,None]        # rolled top edge of the scarf: a bit darker first
C[ch]=scol*(0.7+0.3*edge)
# mouth: a small frown line stays (darker short line inside the skin band)
mouth=sk&(np.abs(fz-160)<22)&(np.abs(fy-(256+0.012*(fz-160)**2))<1.4)
pass   # the original frown line is kept by the luminance-preserving recolour
rgb[I]=C
print('mask+',mk.sum(),'skin',sk.sum(),'chin->scarf',ch.sum())
# chin texels facing down / outside the front grid (face sphere below the new scarf edge) -> scarf dark
HC=np.array([0.04426,0.21433,0.0]); HR=0.12655
rr=np.linalg.norm(np.nan_to_num(pos)-HC,axis=-1)-HR
under=valid&(rr>-0.012)&(rr<0.006)&(Y<0.182)&(X>0.0)&(np.abs(Z)<0.12)&~v
sc_med=np.median(rgb[valid&(Y>0.12)&(Y<0.15)&(X>0.06)&(np.abs(Z)<0.08)],axis=0)
rgb[under]=sc_med*0.8
# 3b. skin-toned rim at the scarf top (warm, light texels around the scarf top, away from the face band)
L2=rgb.mean(2); w2=rgb[...,0]-rgb[...,2]
rim=valid&(Y>0.15)&(Y<0.2)&(w2>30)&(L2>75)&~(v&(np.abs(Z)<0.125))
rgb[rim]=sc_med*(0.85+0.15*rng.random((rim.sum(),1)))
print('scarf rim',rim.sum(),'scarf med',sc_med)
out=bc.copy(); out[...,:3]=np.clip(rgb,0,255)
Image.fromarray(out.astype(np.uint8)).save(O+'basecolor_v4.png')
Image.fromarray(np.clip(nm2,0,255).astype(np.uint8)).save(O+'normal_v4.png')
