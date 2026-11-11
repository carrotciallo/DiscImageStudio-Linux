import sys, json, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan, imagedisc
from scipy.ndimage import uniform_filter1d
from PIL import Image
S=sys.argv[1]
px=600/25.4; NT=7200; res=360/NT
fm=588*277.66208524226016e-6
Ls=np.arange(-40,40.01,0.05)
A=np.load(S+"/Lscan.npy")
tot=(A-np.median(A,axis=1,keepdims=True)).sum(0)
top=np.argsort(tot)[-1]
print(f"sum over 8 scans: best L {Ls[top]:+.2f} mm = {Ls[top]/fm:+.1f} frames; score {tot[top]:.1f}; next-best away from it:")
far=np.abs(Ls-Ls[top])>2
j=np.argmax(np.where(far,tot,-1e9)); print(f"   {Ls[j]:+.2f} mm = {Ls[j]/fm:+.1f} frames, score {tot[j]:.1f}; std of score {tot.std():.1f}")
R=np.arange(26,56,0.1); R=R[np.abs((R+2.5)%5-2.5)>0.45]
TH=np.arange(NT)*2*np.pi/NT
design=imagedisc.grid_design(r_min=26.0,r_max=56.0,line=0.6)
x=R[:,None]*np.cos(TH); y=R[:,None]*np.sin(TH)
D=np.where(design[np.clip(((60-y)/0.02).astype(int),0,5999),np.clip(((x+60)/0.02).astype(int),0,5999)],-1.0,0.0); D-=D.mean(1,keepdims=True)
Fd=np.fft.rfft(D,axis=1); Fd[:,:12]=0
k=np.arange(Fd.shape[1])
fine=np.arange(Ls[top]-3,Ls[top]+3,0.01)
rows=[]; L0=None
for i in range(1,9):
    img,_=scan.load_gray(f"scans/cd_grid_m2f1_p{i}.png")
    o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    xx=cx+R[:,None]*px*np.cos(TH); yy=cy-R[:,None]*px*sy*np.sin(TH)
    pol=img[yy.astype(int),xx.astype(int)].astype(float)
    mean=uniform_filter1d(pol,size=161,axis=1,mode="wrap"); hp=(pol-mean)/np.maximum(mean,1e-3)
    bri=mean[(R>30)&(R<50)].mean(0); w=uniform_filter1d((bri<np.percentile(bri,22)).astype(float),size=41,mode="wrap")
    F=np.fft.rfft(hp*w,axis=1); F[:,:12]=0
    C=F*np.conj(Fd)
    best=(0,0,0)
    for L in fine:
        ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(L/R)[:,None]/360))
        c=np.fft.irfft((C*ph).sum(0),n=NT); s=c.max()/c.std()
        if s>best[0]: best=(s,L,c.argmax()*res)
    rows.append((i,)+best)
    print(f"scan {i}: L {best[1]:+.2f} mm = {best[1]/fm:+.1f} frames, peak/std {best[0]:.1f}, rotation {best[2]:.1f}",flush=True)
    # local residual in radial bins with this scan's best L
    ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(best[1]/R)[:,None]/360))
    Cal=C*ph; j0=int(best[2]/res)
    resid=[]
    for a,b in [(26,31),(31,36),(36,41),(41,46),(46,51),(51,56)]:
        m=(R>=a)&(R<b)
        c=np.fft.irfft(Cal[m].sum(0),n=NT)
        idx=(np.arange(-40,41)+j0)%NT; jj=idx[np.argmax(c[idx])]
        d=((jj-j0+NT//2)%NT-NT//2)*res
        resid.append(d)
    print("    local rotation by radius bin (deg, 26..56):"," ".join(f"{x:+.2f}" for x in resid))
    if i==1:
        ph2=np.degrees(best[1]/R)+best[2]
        idx=(np.arange(NT)[None,:]+np.round(ph2/res).astype(int)[:,None])%NT
        det=hp[np.arange(len(R))[:,None],idx]
        Image.fromarray(np.clip(128+det*1500,0,255).astype(np.uint8)).resize((1800,700)).save(S+"/grid_detwist_1.jpg",quality=90)
        Image.fromarray(np.clip(128+D*70,0,255).astype(np.uint8)).resize((1800,700)).save(S+"/grid_design_polar.jpg",quality=90)
json.dump(rows,open(S+"/grid_L_rows.json","w"))
