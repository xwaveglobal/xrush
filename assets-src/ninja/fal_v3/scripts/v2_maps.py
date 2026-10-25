import numpy as np
from PIL import Image
from scipy import ndimage
A='/workspace/artifacts/ninja/'; W='/workspace/free3d/w2/'
d=np.load(W+'proc.npz'); out=d['out']; wsum=d['wsum']; alpha=d['alpha']; height=d['height']; posY=d['posY']; mtl=d['mtl']
valid=~np.isnan(posY)
lum=out.mean(2); sat=out.max(2)-out.min(2)
skin=(out[...,0]>120)&(out[...,0]-out[...,2]>45)&(out[...,1]>70)&(posY>0.05)
eyes=(out.min(2)>150)&(sat<40)&(posY>0.05)
# front/side leather from Tripo texture (where back projection didn't write)
leatherT=(out[...,0]-out[...,2]>24)&(lum>45)&(lum<170)&(posY>-0.2)&(posY<0.2)&~skin
metalT=(sat<20)&(lum>100)&(lum<220)&(posY>-0.2)&(posY<0.2)&ndimage.binary_dilation(leatherT,iterations=4)&~eyes
height=np.maximum(height, leatherT.astype(np.float32)*(wsum<0.5))
mtl=np.maximum(mtl, metalT.astype(np.float32)*(wsum<0.5))
# colour grade toward 253528ab (deep brown-black, warm highlights, no mauve)
ref=np.asarray(Image.open('/workspace/free3d/in/rear34_white.png').convert('RGB')).astype(np.float32).reshape(-1,3)
ref=ref[ref.min(1)<225]
rm,rs=ref.mean(0),ref.std(0)
cloth=valid&~skin&~eyes&(alpha>0.5)
cm,cs=out[cloth].mean(0),out[cloth].std(0)
print('ref',rm,rs,'cur',cm,cs)
g=out.copy()
g[cloth]=(out[cloth]-cm)/cs*rs+rm
# warm highlights / suppress mauve: where B > G push B down to G
b=g[...,2]; gg=g[...,1]; mauve=cloth&(b>gg); g[...,2]=np.where(mauve, gg+(b-gg)*0.3, b)
# hood rim streak suppression (Tripo baked a light-brown rim on the hood sides)
lumg=g.mean(2)
hood=cloth&(posY>0.16)&(lumg>52)&((g[...,0]-g[...,2])>12)
k=np.clip((lumg-52)/30,0,1)*hood
tgtc=np.array([52,42,38],np.float32)
g=g*(1-0.9*k[...,None])+tgtc*(0.9*k[...,None])
# warm the dark cloth slightly (brown-black, not grey)
dark=cloth&(g.mean(2)<110)
g[dark]=g[dark]*np.array([1.06,0.99,0.92],np.float32)
g=np.clip(g,0,255)
print('graded',g[cloth].mean(0))
# dilate colour into UV padding to avoid seams
inv=~valid
idx=ndimage.distance_transform_edt(inv,return_distances=False,return_indices=True)
g=g[idx[0],idx[1]]; a=alpha[idx[0],idx[1]]
rgba=np.dstack([g,a*255]).astype(np.uint8)
Image.fromarray(rgba,'RGBA').save(W+'basecolor_v2.png')
# height map (blurred, soft bevel)
h=ndimage.gaussian_filter(height,2.0); h=np.clip(h*1.4,0,1)
h=h[idx[0],idx[1]]
Image.fromarray((h*255).astype(np.uint8)).save(W+'height_v2.png')
# metallicRoughness: R unused(1), G roughness, B metallic
rough=np.full(out.shape[:2],0.85,np.float32)
leatherAll=height>0.5
rough[leatherAll]=0.55; rough[skin]=0.6; rough[eyes]=0.35
bootsish=(posY<-0.38)&valid; rough[bootsish]=np.minimum(rough[bootsish],0.6)
mt=ndimage.gaussian_filter(mtl,1.0); rough=np.where(mt>0.4,0.35,rough)
rough+= (np.random.default_rng(0).random(rough.shape)-0.5)*0.04
rough=ndimage.gaussian_filter(rough,1.0)
rough=rough[idx[0],idx[1]]; met=np.clip(mt*1.5,0,1)[idx[0],idx[1]]
mr=np.dstack([np.full_like(rough,255),rough*255,met*255]).astype(np.uint8)
Image.fromarray(mr).save(W+'mr_v2.png')
print('alpha cut frac',(alpha<0.5).mean(),'leather frac',(height>0.5).mean(),'metal',(mtl>0.4).sum())
