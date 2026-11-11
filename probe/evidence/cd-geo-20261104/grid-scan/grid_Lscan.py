import sys, json, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan, imagedisc
from scipy.ndimage import uniform_filter1d
px=600/25.4; NT=7200; res=360/NT
R=np.arange(26,56,0.1); R=R[np.abs((R+2.5)%5-2.5)>0.45]
TH=np.arange(NT)*2*np.pi/NT
design=imagedisc.grid_design(r_min=26.0,r_max=56.0,line=0.6)
def dring(mirror):
    th=-TH if mirror else TH
    x=R[:,None]*np.cos(th); y=R[:,None]*np.sin(th)
    ix=np.clip(((x+60)/0.02).astype(int),0,5999); iy=np.clip(((60-y)/0.02).astype(int),0,5999)
    d=np.where(design[iy,ix],-1.0,0.0); return d-d.mean(1,keepdims=True)
Ls=np.arange(-40,40.01,0.05)
frame_mm=588*277.66208524226016e-6
D={m:np.fft.rfft(dring(m),axis=1) for m in (False,True)}
out={}
for i in range(1,9):
    img,_=scan.load_gray(f"scans/cd_grid_m2f1_p{i}.png")
    o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    x=cx+R[:,None]*px*np.cos(TH); y=cy-R[:,None]*px*sy*np.sin(TH)
    pol=img[y.astype(int),x.astype(int)].astype(float)
    mean=uniform_filter1d(pol,size=161,axis=1,mode="wrap")
    hp=(pol-mean)/np.maximum(mean,1e-3)
    bri=mean[(R>30)&(R<50)].mean(0)
    w=uniform_filter1d((bri<np.percentile(bri,22)).astype(float),size=41,mode="wrap")
    F=np.fft.rfft(hp*w,axis=1); F[:,:12]=0
    for mir in (False,True):
        Fd=D[mir].copy(); Fd[:,:12]=0
        C=F*np.conj(Fd)
        k=np.arange(C.shape[1])
        best=[]
        for L in Ls:
            # design rotated by phi(r)=L/r (rad): align and sum spectra over radius
            ph=np.exp(1j*2*np.pi*k[None,:]*(np.degrees(L/R)[:,None]/360))
            c=np.fft.irfft((C*ph).sum(0),n=NT)
            best.append((c.max()/c.std(),int(c.argmax())))
        best=np.array(best)
        j=int(best[:,0].argmax())
        out[(i,mir)]=(Ls[j],best[j,0],best[j,1]*res,best[:,0])
        print(f"scan {i} mirror {str(mir):5}: best L {Ls[j]:+7.2f} mm = {Ls[j]/frame_mm:+7.1f} frames, peak/std {best[j,0]:.1f}, rotation {best[j,1]*res:6.1f} deg, median score {np.median(best[:,0]):.1f}",flush=True)
np.save(sys.argv[1]+"/Lscan.npy",np.array([out[(i,False)][3] for i in range(1,9)]))
