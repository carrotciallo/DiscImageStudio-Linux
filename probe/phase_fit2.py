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

ri, ro = 23.98815, 57.856098
c1, c2, c3 = -0.014823, -0.002077, -0.000079
rgrid = np.linspace(ri, ro, 40001)
xg = (rgrid-ri)/(ro-ri); fg = 1 + c1*xg + c2*xg**2 + c3*xg**3
def make_theta(b):
    dthdr = 1.0/(b*fg); dLdr = np.sqrt(rgrid**2 + (b*fg)**2)/(b*fg)
    th = cumulative_trapezoid(dthdr, rgrid, initial=0); Lg = cumulative_trapezoid(dLdr, rgrid, initial=0)
    return lambda Lv: np.interp(Lv, Lg, th), Lg
def resB3(p):
    thB, Lg = make_theta(p[0])
    return wrap(np.degrees(thB(L + p[2]) - thB(np.array([Lref + p[2]]))[0]) + p[1] - phase)
fit = least_squares(resB3, [1.182155e-4, 0.0, 0.0], bounds=([1e-5, -180, -2e5], [1e-3, 180, 2e5]))
r = resB3(fit.x)
b, c, L0 = fit.x
thB, Lg = make_theta(b)
r_at_lba0 = np.interp(L0, Lg, rgrid)
print(f"B EST-H + origin offset: b={b:.6e} c={c:+.3f} L0={L0:+.1f} mm (={L0/(BPS*BIT_MM):+.0f} sectors, radius at LBA0 = {r_at_lba0:.4f} mm)")
print(f"rms={np.sqrt(np.mean(r**2)):.4f} max={np.max(np.abs(r)):.4f}")
