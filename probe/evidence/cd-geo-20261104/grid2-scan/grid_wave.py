import sys, csv, json, math, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan, imagedisc
from scipy.ndimage import uniform_filter1d
px=600/25.4; NT=7200; res=360/NT
R=np.arange(26,56,0.1); R=R[np.abs((R+2.5)%5-2.5)>0.45]
TH=np.arange(NT)*2*np.pi/NT
design=imagedisc.grid_design(r_min=26.0,r_max=56.0,line=0.6)
x=R[:,None]*np.cos(TH); y=R[:,None]*np.sin(TH)
D=np.where(design[np.clip(((60-y)/0.02).astype(int),0,5999),np.clip(((x+60)/0.02).astype(int),0,5999)],-1.0,0.0); D-=D.mean(1,keepdims=True)
Fd=np.fft.rfft(D,axis=1); Fd[:,:12]=0
bins=[(a,a+2.5) for a in np.arange(26,56,2.5)]
out=[]
for i in (3,5,7,9):
    img,_=scan.load_gray(f"scans/cd_grid2_m2f1_p{i}.png")
    o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    xx=cx+R[:,None]*px*np.cos(TH); yy=cy-R[:,None]*px*sy*np.sin(TH)
    pol=img[yy.astype(int),xx.astype(int)].astype(float)
    mean=uniform_filter1d(pol,size=161,axis=1,mode="wrap"); hp=(pol-mean)/np.maximum(mean,1e-3)
    bri=mean[(R>30)&(R<50)].mean(0); w=uniform_filter1d((bri<np.percentile(bri,22)).astype(float),size=41,mode="wrap")
    F=np.fft.rfft(hp*w,axis=1); F[:,:12]=0; C=F*np.conj(Fd)
    c=np.fft.irfft(C.sum(0),n=NT); j0=int(c.argmax())
    phi=[]
    for a,b in bins:
        m=(R>=a)&(R<b); cc=np.fft.irfft(C[m].sum(0),n=NT)
        idx=(np.arange(-40,41)+j0)%NT; jj=idx[np.argmax(cc[idx])]
        phi.append(((jj-j0+NT//2)%NT-NT//2)*res)
    out.append(phi); print(f"scan {i}: rotation {j0*res:.1f}  "+" ".join(f"{p:+.2f}" for p in phi),flush=True)
M=np.median(out,axis=0); mid=[(a+b)/2 for a,b in bins]
print("radius mm:   "+" ".join(f"{m:5.1f}" for m in mid))
print("median phi:  "+" ".join(f"{v:+5.2f}" for v in M))
print("rms %.3f  p-p %.3f deg; in mm at that radius: %s"%(M.std(),M.max()-M.min()," ".join(f"{np.radians(v)*m:+.2f}" for v,m in zip(M,mid))))
# compare with what timing says is left after the quadratic correction
rows=list(csv.DictReader(open("evidence/cd-geo-20261104/full-2080rpm/targets.csv")))
f=json.load(open("evidence/cd-geo-20261104/full-2080rpm/summary.json"))["fit"]; b=f["bit_nm_assumed"]*1e-6
corr=imagedisc.load_correction("evidence/cd-geo-20261104/full-2080rpm/correction_quadratic.json")
r=np.array([b*math.sqrt(f["u"]**2+f["v"]*float(x["n_bits"])/math.pi) for x in rows]); res_t=np.array([float(x["residual_deg"]) for x in rows])
left=res_t+corr(r); left-=left.mean()
print("timing residual after quadratic, binned:  "+" ".join(f"{(left[(r>=a)&(r<b)].mean() if ((r>=a)&(r<b)).any() else float('nan')):+5.2f}" for a,b in bins))
