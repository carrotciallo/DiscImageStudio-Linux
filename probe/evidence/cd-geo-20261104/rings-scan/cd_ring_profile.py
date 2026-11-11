import json, math, sys
import numpy as np
from PIL import Image
from discprobe import cd
Image.MAX_IMAGE_PIXELS=None
s=json.load(open("results/ringscan-20261104-160935/summary.json"))["scans"]
lay=json.load(open("iso/cd-rings-m2f1.rings.json"))
f=json.load(open("evidence/cd-geo-20261104/full-2080rpm/summary.json"))["fit"]
b=f["bit_nm_assumed"]*1e-6
r_of=lambda lba: b*math.sqrt(f["u"]**2+f["v"]*lba*cd.SECTOR_BITS/math.pi)
rings=[(x["texture"],r_of(x["lba_start"]),r_of(x["lba_end"])) for x in lay["rings"]]
pxmm=600/25.4
R=np.arange(24,58,0.05)
TH=np.radians(np.arange(0,360,0.25))
profiles=[]; values={}
for sc in s:
    im=np.asarray(Image.open(f"scans/{sc['name']}.png").convert("L"),float)
    cx,cy=sc["centre_px"]
    rr,tt=np.meshgrid(R,TH,indexing="ij")
    x=(cx+rr*pxmm*np.cos(tt)).astype(int); y=(cy+rr*pxmm*np.sin(tt)).astype(int)
    pol=im[y,x]
    ang=pol[(R>30)&(R<50)].mean(0)
    # dark sectors: darkest 12% of angles
    thr=np.percentile(ang,12); dark=ang<=thr
    prof=np.median(pol[:,dark],axis=1)
    # remove the smooth radial trend
    k=int(6/0.05)|1
    trend=np.convolve(np.pad(prof,k//2,mode="edge"),np.ones(k)/k,mode="valid")
    hp=prof-trend
    profiles.append(hp)
    print(sc["name"],"dark sector mean",round(float(prof.mean()),1),"lit mean",round(float(pol[(R>30)&(R<50)].mean()),1),"hp rms",round(float(hp.std()),2))
    for t,a,c in rings:
        m=(R>a+0.3)&(R<c-0.3)
        values.setdefault(t,[]).append(float(hp[m].mean()))
    # keep per ring values by order too
    sc["ring_vals"]=[float(hp[(R>a+0.3)&(R<c-0.3)].mean()) for t,a,c in rings]
P=np.mean(profiles,axis=0)
print("\nper ring (high-passed dark-sector level, counts of 255), mean of 5 scans (each scan):")
for i,(t,a,c) in enumerate(rings):
    v=[sc["ring_vals"][i] for sc in s]
    print(f"{i:2d} {t:>3} {a:5.2f}-{c:5.2f}: {np.mean(v):+6.2f}   "+" ".join(f"{x:+5.1f}" for x in v))
print("\nby texture:")
for t in sorted(values): print(f"{t:>3}: {np.mean(values[t]):+.2f} +- {np.std(values[t])/math.sqrt(len(values[t])):.2f} (n {len(values[t])})")
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(figsize=(12,3.6))
for p in profiles: ax.plot(R,p,lw=.5,color="0.7")
ax.plot(R,P,lw=1.2,color="k")
col={"0D":"#c44","AA":"#48c","10":"#4a4","63":"#c84","RND":"#bbb"}
for t,a,c in rings:
    ax.axvspan(a,c,color=col[t],alpha=.18); ax.text((a+c)/2,ax.get_ylim()[1]*.8,t,ha="center",fontsize=8)
ax.set_xlabel("radius (mm)"); ax.set_ylabel("dark-sector level, high-passed"); fig.tight_layout(); fig.savefig(sys.argv[1],dpi=110)
