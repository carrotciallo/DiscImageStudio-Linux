import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan, imagedisc
from scipy.ndimage import uniform_filter1d
prefix,nscans=sys.argv[1],int(sys.argv[2]); Lmin,Lmax=float(sys.argv[3]),float(sys.argv[4])
px=600/25.4; NT=7200; res=360/NT; fm=588*277.66208524226016e-6
R=np.arange(26,56,0.1); R=R[np.abs((R+2.5)%5-2.5)>0.45]
TH=np.arange(NT)*2*np.pi/NT
design=imagedisc.grid_design(r_min=26.0,r_max=56.0,line=0.6)
x=R[:,None]*np.cos(TH); y=R[:,None]*np.sin(TH)
D=np.where(design[np.clip(((60-y)/0.02).astype(int),0,5999),np.clip(((x+60)/0.02).astype(int),0,5999)],-1.0,0.0); D-=D.mean(1,keepdims=True)
Fd=np.fft.rfft(D,axis=1); Fd[:,:12]=0; k=np.arange(Fd.shape[1])
Ls=np.arange(Lmin,Lmax+1e-6,0.1)
Cs=[]
for i in range(1,nscans+1):
    img,_=scan.load_gray(f"{prefix}{i}.png")
    o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    xx=cx+R[:,None]*px*np.cos(TH); yy=cy-R[:,None]*px*sy*np.sin(TH)
    pol=img[yy.astype(int),xx.astype(int)].astype(float)
    mean=uniform_filter1d(pol,size=161,axis=1,mode="wrap"); hp=(pol-mean)/np.maximum(mean,1e-3)
    bri=mean[(R>30)&(R<50)].mean(0); w=uniform_filter1d((bri<np.percentile(bri,22)).astype(float),size=41,mode="wrap")
    F=np.fft.rfft(hp*w,axis=1); F[:,:12]=0
    Cs.append(F*np.conj(Fd))
curve=[]
for i,C in enumerate(Cs):
    row=[]
    for L in Ls:
        ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(L/R)[:,None]/360))
        c=np.fft.irfft((C*ph).sum(0),n=NT); row.append(c.max()/c.std())
    curve.append(row)
curve=np.array(curve)
print("L mm   frames  | "+" ".join(f"s{i+1:<4d}" for i in range(nscans))+"| sum(z)")
z=(curve-np.median(curve,axis=1,keepdims=True))/curve.std(axis=1,keepdims=True)
tot=z.sum(0)
step=max(1,int(round(1.0/0.1)))
for j in range(0,len(Ls),step):
    print(f"{Ls[j]:+6.1f} {Ls[j]/fm:+7.1f} | "+" ".join(f"{v:5.1f}" for v in curve[:,j])+f"| {tot[j]:6.1f}")
o=np.argsort(tot)[::-1]; top=[]
for j in o:
    if all(abs(Ls[j]-Ls[t])>1.0 for t in top): top.append(j)
    if len(top)==5: break
print("top by sum of z:",[(round(float(Ls[t]),1),round(float(Ls[t]/fm),1),round(float(tot[t]),1)) for t in top])
