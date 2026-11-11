import sys, numpy as np
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import discprobe.efmplus as E
from discprobe.imagedisc import texture_bytes

def lv_rows(q_rows, b):
    out = []
    for i, row in enumerate(q_rows):
        for h in range(2):
            lv, b = E.encode_frame(row[91*h:91*(h+1)], E.ROW_SYNC[i % 13][h], b); out.append(lv[32:])
    return out

def frac(lvs, P):
    tot = fund = 0.0
    for lv in lvs:
        x = 2.0*lv - 1; x -= x.mean(); n = np.arange(x.size)
        fund += abs(np.sum(x*np.exp(-2j*np.pi*n/P)))**2/x.size; tot += np.sum(x*x)
    return 2*fund/tot

def rows_for(spec, nrows=6, seed=0):
    # real sector layout: 12 header bytes, PI parity random, 172 data bytes per row
    q = texture_bytes(spec, np.array([1000 + seed]))[0]
    frame = np.concatenate([np.random.default_rng(seed).integers(0,256,12).astype(np.uint8), q[:172*nrows-12]])
    rows = frame.reshape(nrows, 172)
    pi = np.random.default_rng(seed+7).integers(0, 256, (nrows, 10)).astype(np.uint8)
    return np.hstack([rows, pi])

def robust(spec, P):
    vals = []
    for seed, (dsv, land) in enumerate([(0, True), (60, False), (-60, True), (30, False)]):
        vals.append(frac(lv_rows(rows_for(spec, seed=seed), E.Boundary(1, dsv, land)), P))
    return min(vals), float(np.mean(vals))

def runstats(spec):
    lvs = lv_rows(rows_for(spec), E.Boundary())
    r = np.concatenate([np.diff(np.flatnonzero(np.diff(lv.astype(int)) != 0)) for lv in lvs])
    return r.mean(), np.mean(r == 3)

for spec, P in [("92",16),("8B",32),("00",32),("2424",32),("00048B",48),("2AE304",48),("FB0702",48),("5002",64),("ED00",64),("1200AB",96)]:
    mn, av = robust(spec, P); print(f"{spec:8s} P{P:<3d} min {mn:.2f} mean {av:.2f}  runs mean {runstats(spec)[0]:.2f}")
rng = np.random.default_rng(1)
hi = [b for b in range(88, 256)]
best = []
for _ in range(20000):
    s = "".join(f"{int(x):02X}" for x in rng.choice(hi, 3))
    try: best.append((frac(lv_rows(rows_for(s, nrows=2), E.Boundary()), 48), s))
    except ValueError: pass
best.sort(reverse=True)
print("triples >= 88, P48:", [(s, round(v, 3)) for v, s in best[:6]])
for v, s in best[:3]: print(s, "robust", [round(x, 2) for x in robust(s, 48)])
print("mixes:")
for spec in ["MIX:92,87,83,8D,60", "MIX:92,4F,55,15,16,20,26", "MIX:A5,62,B1,61,65,A7", "RND", "A5", "B9", "66", "E4", "64"]:
    m, f3 = runstats(spec)
    print(f"  {spec:28s} runs mean {m:.2f}  3T share {f3:.2f}  P16 {robust(spec,16)[1]:.2f}  P32 {robust(spec,32)[1]:.2f}")
