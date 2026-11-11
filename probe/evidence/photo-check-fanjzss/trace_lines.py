import numpy as np, sys
from scipy.ndimage import gaussian_filter1d, median_filter
S=sys.argv[1]
z=np.load(S+'/fan.npz'); cx,cy=z['centre']; B=z['B']; U=np.load(S+'/fan_U.npy')
da=0.1; a=np.arange(0,360,da); drho=0.0005; rho=np.arange(0.28,1.0,drho)
hp=U-gaussian_filter1d(U,30,axis=0,mode='wrap')
pxmm=2*np.mean(np.linalg.svd(B,compute_uv=False))/120.0
print('px per mm',round(pxmm,2))
def xy(r,al):
    u,v=r*np.cos(np.radians(al)),r*np.sin(np.radians(al))
    return cx+B[0,0]*u+B[0,1]*v, cy+B[1,0]*u+B[1,1]*v
tr={}
for seed in (43.8,141.0,234.5,316.5):
    pts=[]; cur=seed
    for r0 in np.arange(0.42,0.95,0.01):
        m=(rho>=r0)&(rho<r0+0.01)
        i0=int(round(seed/da)); w=int(3.5/da); idx=np.arange(i0-w,i0+w)%len(a)
        prof=gaussian_filter1d(hp[:,m].mean(1)[idx],2)
        j=int(np.argmin(prof)); c=(prof[j]-np.median(prof))/(1.4826*np.median(np.abs(prof-np.median(prof)))+1e-6)
        if 2<j<len(prof)-3:
            y0,y1,y2=prof[j-1],prof[j],prof[j+1]; sub=j+0.5*(y0-y2)/(y0-2*y1+y2)
            pts.append((r0+0.005,seed-3.5+sub*da,c))
    tr[seed]=np.array(pts)
out={}
for seed,p in tr.items():
    good=p[:,2]<-1.5; print("seed",seed,"contrast pct",np.round(np.percentile(p[:,2],[10,50,90]),1))
    X,Y=xy(p[:,0],p[:,1]); P=np.c_[X,Y]
    # robust straight line through good points
    idx=np.where(good)[0]; best=None
    if len(idx)<8: print("  too few"); continue
    rng=np.random.default_rng(1)
    for _ in range(3000):
        i,j=rng.choice(idx,2,replace=False); d=P[j]-P[i]; n=np.array([-d[1],d[0]])/np.hypot(*d)
        res=(P-P[i])@n; s=np.sum(np.abs(res[idx])<4)
        if best is None or s>best[0]: best=(s,P[i],n)
    s,p0,n=best; use=idx[np.abs((P[idx]-p0)@n)<8]
    c=P[use].mean(0); _,_,Vt=np.linalg.svd(P[use]-c); n=Vt[1]; res=(P-c)@n
    out[seed]=(p[:,0]*60,res/pxmm,use,c,Vt[0],n)
    print(f'spoke {seed}: {len(idx)} strong of {len(p)}, on line {len(use)}, rms {res[use].std()/pxmm:.3f} mm over r {p[use,0].min()*60:.0f}-{p[use,0].max()*60:.0f}')
    bins=[(a_,a_+5) for a_ in range(25,57,5)]
    print('   dev mm by r:',' '.join(f"{a_}-{b_}:{np.median((res/pxmm)[use][(p[use,0]*60>=a_)&(p[use,0]*60<b_)]) if ((p[use,0]*60>=a_)&(p[use,0]*60<b_)).any() else float('nan'):+.2f}" for a_,b_ in bins))
    ang=np.degrees(np.arctan2(*Vt[0][::-1])); print('   direction',round(ang,2))
np.save(S+'/fan_out.npy',np.array([0]))
ks=list(out)
if len(ks)<4: raise SystemExit
for a_,b_ in ((0,2),(1,3)):
    (ra,da_,ua,ca,va,na),(rb,db_,ub,cb,vb,nb)=out[ks[a_]],out[ks[b_]]
    ang=np.degrees(np.arccos(abs(va@vb)))
    # lateral gap of the second half's fit from the first half's fit, at the disc centre
    print(f'diameter {ks[a_]}/{ks[b_]}: angle between the halves {ang:.3f} deg, gap of centre lines {abs((cb-ca)@na)/pxmm:.3f} mm at mid-span')
# Does each diameter stay one straight line? Fit one line through both halves, using the reliable ranges.
def diam(k1,k2):
    (r1,d1,u1,c1,v1,n1),(r2,d2,u2,c2,v2,n2)=out[ks[k1]],out[ks[k2]]
    p1=c1+np.outer(np.r_[d1[u1]]*0,n1)  # unused
    print('diameter',ks[k1],ks[k2],'halves differ in direction by',round(float(np.degrees(np.arccos(abs(v1@v2)))),3),'deg')
    # where the two half-lines pass the disc centre: take the crossing with the other diameter's mean line
diam(0,2); diam(1,3)
c=[out[k][3] for k in ks]; v=[out[k][4] for k in ks]
def cross(a,b):
    A=np.array([v[a],-v[b]]).T; t=np.linalg.solve(A,c[b]-c[a]); return c[a]+t[0]*v[a]
pts=[cross(0,1),cross(1,2),cross(2,3),cross(3,0)]
print('crossings of adjacent half-lines (px):',[tuple(np.round(p,1)) for p in pts])
P=np.array(pts); print('scatter of the crossings about their mean: %.3f mm rms'%(np.sqrt(((P-P.mean(0))**2).sum(1).mean())/pxmm))
import csv
with open(S+'/lines.csv','w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['line','r_mm','deviation_mm','used','x_px','y_px'])
    for i,k in enumerate(ks):
        r,d,u,c,v,n=out[k]; used=set(u.tolist())
        # recover image points from the fit frame
        p=tr[k]; X,Y=xy(p[:,0],p[:,1])
        for j in range(len(r)):
            w.writerow([i+1,round(float(r[j]),2),round(float(d[j]),4),int(j in used),round(float(X[j]),1),round(float(Y[j]),1)])
