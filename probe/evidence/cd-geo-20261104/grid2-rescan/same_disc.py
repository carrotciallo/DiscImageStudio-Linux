# Same physical disc? Fine spots in the rim and hub, in rows wide enough to tolerate centring error.
import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan
from multiprocessing import Pool
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
px=600/25.4; NT=14400
ZONES={"hub":np.arange(17,24.5,0.05),"rim":np.arange(56.6,59.4,0.05)}
TH=np.arange(NT)*2*np.pi/NT
def pol(f):
    img,_=scan.load_gray(f); o,_=scan.locate_disc(img,px); cx,cy=o["cx"],o["cy"]; sy=o["ry"]/o["rx"]
    out={}
    for z,R in ZONES.items():
        xx=cx+R[:,None]*px*np.cos(TH); yy=cy-R[:,None]*px*sy*np.sin(TH)
        p=img[np.clip(yy.astype(int),0,img.shape[0]-1),np.clip(xx.astype(int),0,img.shape[1]-1)].astype(np.float32)
        p=uniform_filter1d(p,6,axis=0)[::6]                     # 0.3 mm rows
        p=gaussian_filter1d(p,3,axis=1,mode="wrap")-gaussian_filter1d(p,25,axis=1,mode="wrap")   # spots a few tenths of a mm long
        s=1.4826*np.median(np.abs(p),axis=1,keepdims=True)+1e-6; p=np.clip(p/s,-6,6)
        out[z]=np.fft.rfft(p,axis=1)
    return f,out
if __name__=="__main__":
    fs=[f"scans/cd_grid2b_m2f1_p{i}.png" for i in (1,5,6,13,15)]+[f"scans/cd_grid2_m2f1_p{i}.png" for i in (3,5,7,9)]+[f"scans/cd_grid_m2f1_p{i}.png" for i in (1,3,7)]
    with Pool(6) as p: r=p.map(pol,fs)
    names=[x[0].replace("scans/cd_","").replace("_m2f1","").replace(".png","") for x in r]
    for z in ZONES:
        print(z,"(peak over the median peak-free level, in robust sigmas of the correlation)")
        print(" "*11+" ".join(n[-7:].rjust(7) for n in names))
        for a,n in zip(r,names):
            row=[]
            for b in r:
                if a is b: row.append("      ."); continue
                c=np.fft.irfft((a[1][z]*np.conj(b[1][z])).sum(0),n=NT)
                row.append(f"{(c.max()-np.median(c))/(1.4826*np.median(np.abs(c-np.median(c)))):7.1f}")
            print(n.ljust(11)+" ".join(row))
    idx={n:i for i,n in enumerate(names)}
    print("\nlag at the peak (deg), and disc centre in the scan")
    for u,v in (("grid2b_p1","grid2_p7"),("grid2b_p5","grid2_p9"),("grid2b_p13","grid2_p5"),("grid2b_p1","grid2b_p5"),("grid2b_p5","grid2b_p13"),("grid2b_p1","grid_p1")):
        out=[]
        for z in ZONES:
            c=np.fft.irfft((r[idx[u]][1][z]*np.conj(r[idx[v]][1][z])).sum(0),n=NT); out.append(f"{z} {c.argmax()*360/NT:7.2f}")
        print(u,v,*out)
    for n in ("grid2b_p1","grid2_p7","grid2b_p5","grid2_p9"):
        img,_=scan.load_gray(f"scans/cd_{n.split('_')[0]}_m2f1_{n.split('_')[1]}.png"); o,_=scan.locate_disc(img,px); print(n,round(o["cx"]),round(o["cy"]))
