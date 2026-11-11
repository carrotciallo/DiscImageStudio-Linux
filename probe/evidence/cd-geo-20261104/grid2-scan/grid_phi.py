import sys, json, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan, imagedisc
from scipy.ndimage import uniform_filter1d
prefix, nscans = sys.argv[1], int(sys.argv[2])
px=600/25.4; NT=7200; res=360/NT
fm=588*277.66208524226016e-6
R=np.arange(26,56,0.1); R=R[np.abs((R+2.5)%5-2.5)>0.45]
TH=np.arange(NT)*2*np.pi/NT
design=imagedisc.grid_design(r_min=26.0,r_max=56.0,line=0.6)
x=R[:,None]*np.cos(TH); y=R[:,None]*np.sin(TH)
D=np.where(design[np.clip(((60-y)/0.02).astype(int),0,5999),np.clip(((x+60)/0.02).astype(int),0,5999)],-1.0,0.0); D-=D.mean(1,keepdims=True)
Fd=np.fft.rfft(D,axis=1); Fd[:,:12]=0
k=np.arange(Fd.shape[1])
Ls=np.arange(-40,40.01,0.05)
bins=[(a,a+2.5) for a in np.arange(26,56,2.5)]
allphi=[]; rows=[]; scores=[]
for i in range(1,nscans+1):
    img,_=scan.load_gray(f"{prefix}{i}.png")
    o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    xx=cx+R[:,None]*px*np.cos(TH); yy=cy-R[:,None]*px*sy*np.sin(TH)
    pol=img[yy.astype(int),xx.astype(int)].astype(float)
    mean=uniform_filter1d(pol,size=161,axis=1,mode="wrap"); hp=(pol-mean)/np.maximum(mean,1e-3)
    bri=mean[(R>30)&(R<50)].mean(0); w=uniform_filter1d((bri<np.percentile(bri,22)).astype(float),size=41,mode="wrap")
    F=np.fft.rfft(hp*w,axis=1); F[:,:12]=0
    C=F*np.conj(Fd)
    sc=[]
    for L in Ls:
        ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(L/R)[:,None]/360))
        c=np.fft.irfft((C*ph).sum(0),n=NT); sc.append((c.max()/c.std(),c.argmax()*res))
    sc=np.array(sc); j=int(sc[:,0].argmax()); scores.append(sc[:,0])
    fine=np.arange(Ls[j]-1,Ls[j]+1,0.01); best=(0,0,0)
    for L in fine:
        ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(L/R)[:,None]/360))
        c=np.fft.irfft((C*ph).sum(0),n=NT); s=c.max()/c.std()
        if s>best[0]: best=(s,L,c.argmax()*res)
    ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(best[1]/R)[:,None]/360)); Cal=C*ph; j0=int(best[2]/res)
    phi=[]
    for a,b in bins:
        m=(R>=a)&(R<b); c=np.fft.irfft(Cal[m].sum(0),n=NT)
        idx=(np.arange(-60,61)+j0)%NT; jj=idx[np.argmax(c[idx])]
        phi.append(((jj-j0+NT//2)%NT-NT//2)*res)
    allphi.append(phi); rows.append(dict(scan=i,L_mm=float(best[1]),frames=float(best[1]/fm),peak=float(best[0]),rot=float(best[2]),phi=phi))
    print(f"scan {i}: L {best[1]:+.2f} mm = {best[1]/fm:+.1f} frames, peak/std {best[0]:.1f}, rotation {best[2]:.1f}; phi by bin "+" ".join(f"{p:+.2f}" for p in phi),flush=True)
tot=(np.array(scores)-np.median(scores,axis=1,keepdims=True)).sum(0); t=int(tot.argmax())
far=np.abs(Ls-Ls[t])>2
print(f"\nsum over scans: best L {Ls[t]:+.2f} mm = {Ls[t]/fm:+.1f} frames, score {tot[t]:.1f}, next best {tot[far].max():.1f}, score std {tot.std():.1f}")
good=[r for r in rows if r["peak"]>=6]
if good:
    print("strong scans:",[r["scan"] for r in good],"frames",[round(r["frames"],1) for r in good])
    a=np.array([r["phi"] for r in good]); print("median phi by bin:"," ".join(f"{(p+q)/2:.0f}mm {v:+.2f}" for (p,q),v in zip(bins,np.median(a,axis=0))))
json.dump(rows,open(sys.argv[3],"w"),indent=1)
