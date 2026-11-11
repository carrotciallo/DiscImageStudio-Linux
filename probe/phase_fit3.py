import csv, math
import numpy as np
from scipy.optimize import least_squares
from scipy.integrate import cumulative_trapezoid

BIT_MM = 133.3e-6; BPS = 38688; REF = 1009904
rows = list(csv.DictReader(open("/home/carrot/muse/disc-probe/results/geo-sr0-20261109-023521/targets.csv")))
lbas = np.array([int(r["lba"]) for r in rows], float)
phase = np.array([float(r["phase_deg"]) for r in rows])
L = lbas * BPS * BIT_MM; Lref = REF * BPS * BIT_MM
def wrap(d): return (d + 180.0) % 360.0 - 180.0

def make_theta(ri, ro, c1, c2, c3, b):
    rgrid = np.linspace(ri, ro, 20001)
    xg = (rgrid-ri)/(ro-ri); fg = 1 + c1*xg + c2*xg**2 + c3*xg**3
    if np.any(fg <= 0.05): return None
    dthdr = 1.0/(b*fg); dLdr = np.sqrt(rgrid**2 + (b*fg)**2)/(b*fg)
    th = cumulative_trapezoid(dthdr, rgrid, initial=0); Lg = cumulative_trapezoid(dLdr, rgrid, initial=0)
    return lambda Lv: np.interp(Lv, Lg, th)

# 1) EST-H shape, multi-start over b and c
best = None
for b0 in [1.10e-4, 1.14e-4, 1.168e-4, 1.182e-4, 1.22e-4, 1.26e-4]:
    for c0 in [0, 90, 180, 270]:
        def resB(p):
            thB = make_theta(23.98815, 57.856098, -0.014823, -0.002077, -0.000079, p[0])
            return wrap(np.degrees(thB(L) - thB(np.array([Lref]))[0]) + p[1] - phase)
        f = least_squares(resB, [b0, c0])
        rms = np.sqrt(np.mean(resB(f.x)**2))
        if best is None or rms < best[0]: best = (rms, f.x)
print(f"B EST-H multi-start best: rms={best[0]:.4f}  b={best[1][0]:.6e} c={best[1][1]:+.2f}")

# 2) DIS cubic family fully free (ri, b, c1, c2, c3, c), ro fixed 57.856098
def resF(p):
    thF = make_theta(p[0], 57.856098, p[2], p[3], p[4], p[1])
    if thF is None: return np.full(len(L), 999.0)
    return wrap(np.degrees(thF(L) - thF(np.array([Lref]))[0]) + p[5] - phase)
f2 = least_squares(resF, [23.98815, 1.182e-4, -0.014823, -0.002077, -0.000079, 0.0],
                   bounds=([22.0, 5e-5, -0.5, -0.5, -0.5, -180], [26.0, 3e-4, 0.5, 0.5, 0.5, 180]))
r2 = resF(f2.x)
ri2, b2 = f2.x[0], f2.x[1]
p_at = lambda rr: 2*math.pi*b2*(1 + f2.x[2]*((rr-ri2)/(57.856098-ri2)) + f2.x[3]*((rr-ri2)/(57.856098-ri2))**2 + f2.x[4]*((rr-ri2)/(57.856098-ri2))**3)*1000
print(f"F cubic free: rms={np.sqrt(np.mean(r2**2)):.4f} max={np.max(np.abs(r2)):.4f}")
print(f"   ri={ri2:.5f} pitch@ri={p_at(ri2):.5f}um pitch@40mm={p_at(40.0):.5f}um pitch@ro={p_at(57.856098):.5f}um c=({f2.x[2]:+.5f},{f2.x[3]:+.5f},{f2.x[4]:+.5f}) phase0={f2.x[5]:+.2f}")
