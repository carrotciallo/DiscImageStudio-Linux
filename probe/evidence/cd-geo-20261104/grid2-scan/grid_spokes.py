import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan
from scipy.ndimage import uniform_filter1d
prefix,nscans,Lmin,Lmax=sys.argv[1],int(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4])
px=600/25.4; NT=7200; res=360/NT; fm=588*277.66208524226016e-6
R=np.arange(26,56,0.1); R=R[np.abs((R+2.5)%5-2.5)>0.45]
TH=np.arange(NT)*2*np.pi/NT
# spokes only: one radial line every 30 deg, 0.6 mm wide (same widths as grid_design)
ang=np.degrees(TH)[None,:]; d=np.abs(((ang+15)%30)-15)
D=np.where(np.radians(d)*R[:,None]<0.3,-1.0,0.0); D-=D.mean(1,keepdims=True)
Fd=np.fft.rfft(D,axis=1); Fd[:,:12]=0; k=np.arange(Fd.shape[1])
Ls=np.arange(Lmin,Lmax+1e-6,0.1)
curve=[]; rots=[]
for i in range(1,nscans+1):
    img,_=scan.load_gray(f"{prefix}{i}.png")
    o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    xx=cx+R[:,None]*px*np.cos(TH); yy=cy-R[:,None]*px*sy*np.sin(TH)
    pol=img[yy.astype(int),xx.astype(int)].astype(float)
    mean=uniform_filter1d(pol,size=161,axis=1,mode="wrap"); hp=(pol-mean)/np.maximum(mean,1e-3)
    bri=mean[(R>30)&(R<50)].mean(0); w=uniform_filter1d((bri<np.percentile(bri,22)).astype(float),size=41,mode="wrap")
    F=np.fft.rfft(hp*w,axis=1); F[:,:12]=0
    C=F*np.conj(Fd)
    row=[];rr=[]
    for L in Ls:
        ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(L/R)[:,None]/360))
        c=np.fft.irfft((C*ph).sum(0),n=NT); row.append(c.max()/c.std()); rr.append(c.argmax()*res)
    curve.append(row); rots.append(rr)
curve=np.array(curve); z=(curve-np.median(curve,axis=1,keepdims=True))/curve.std(axis=1,keepdims=True); tot=z.sum(0)
best=curve.argmax(1)
print("per scan best:", " ".join(f"s{i+1}:{Ls[b]:+.1f}mm/{curve[i,b]:.1f}" for i,b in enumerate(best)))
o=np.argsort(tot)[::-1]; top=[]
for j in o:
    if all(abs(Ls[j]-Ls[t])>1.5 for t in top): top.append(j)
    if len(top)==5: break
print("top by sum of z:",[(f"{Ls[t]:+.1f} mm",f"{Ls[t]/fm:+.1f} fr",round(float(tot[t]),1)) for t in top])
