import csv, math
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.optimize import brentq, least_squares

BIT_MM = 133.3e-6; BPS = 38688; REF = 1009904; BLK = 16
TOTAL = 2298336; RO = 57.912477520380705
rows = list(csv.DictReader(open("/home/carrot/muse/disc-probe/results/geo-sr0-20261109-023521/targets.csv")))
lbas = np.array([int(r["lba"]) for r in rows], float)
phase = np.array([float(r["phase_deg"]) for r in rows])
L = (lbas + BLK) * BPS * BIT_MM; Lref = (REF + BLK) * BPS * BIT_MM

def wrap(d): return (d + 180.0) % 360.0 - 180.0

def dis_theta_fn(ri, ro, total_sectors, c1, c2, c3, ngrid=20001):
    Lt = total_sectors * BPS * BIT_MM
    rgrid = np.linspace(ri, ro, ngrid)
    xg = (rgrid - ri) / (ro - ri); fg = 1 + c1*xg + c2*xg**2 + c3*xg**3
    def total_len(b): return np.trapezoid(np.sqrt(rgrid**2 + (b*fg)**2) / (b*fg), rgrid)
    b = brentq(lambda bb: total_len(bb) - Lt, 1e-6, 1e-2, xtol=1e-14)
    dthdr = 1.0 / (b * fg); dLdr = np.sqrt(rgrid**2 + (b*fg)**2) / (b*fg)
    th = cumulative_trapezoid(dthdr, rgrid, initial=0); Lg = cumulative_trapezoid(dLdr, rgrid, initial=0)
    pitch = lambda rr: 2*math.pi*b*(1 + c1*((rr-ri)/(ro-ri)) + c2*((rr-ri)/(ro-ri))**2 + c3*((rr-ri)/(ro-ri))**3) * 1000
    return (lambda Lv: np.degrees(np.interp(Lv, Lg, th))), pitch

def residuals(p):
    ri, c1, c2, c3, coff = p
    th, _ = dis_theta_fn(ri, RO, TOTAL, c1, c2, c3)
    d = th(L) - th(np.array([Lref]))[0] - phase + coff
    return wrap(d)

p0 = np.array([24.17331445423364, 3.27e-08, -7.23e-08, 5.01e-08, 0.0])
r0 = residuals(p0)
print(f"shipped preset: rms={np.sqrt(np.mean(r0**2)):.4f} deg  max={np.max(np.abs(r0)):.3f}")

sol = least_squares(residuals, p0, method="lm", max_nfev=400)
ri, c1, c2, c3, coff = sol.x
r1 = residuals(sol.x)
print(f"cubic fit:      rms={np.sqrt(np.mean(r1**2)):.4f} deg  max={np.max(np.abs(r1)):.3f}")
print(f"  inner={ri:.8f}  c1={c1:.6e} c2={c2:.6e} c3={c3:.6e}  coff={coff:+.3f}")

# verify at full grid density + pitch sanity
th, pitch = dis_theta_fn(ri, RO, TOTAL, c1, c2, c3, ngrid=60001)
d = wrap(th(L) - th(np.array([Lref]))[0] - phase + coff)
print(f"verify 60001:   rms={np.sqrt(np.mean(d**2)):.4f} deg  max={np.max(np.abs(d)):.3f}")
print(f"  pitch: r24={pitch(24.0):.6f} r40={pitch(40.0):.6f} r57.9={pitch(57.9):.6f} um")
import json
print(json.dumps({"inner": ri, "outer": RO, "total": TOTAL, "c1": c1, "c2": c2, "c3": c3}))
