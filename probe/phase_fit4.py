import csv, math
import numpy as np
from scipy.integrate import cumulative_trapezoid

BIT_MM = 133.3e-6; BPS = 38688; REF = 1009904
rows = list(csv.DictReader(open("/home/carrot/muse/disc-probe/results/geo-sr0-20261109-023521/targets.csv")))
lbas = np.array([int(r["lba"]) for r in rows], float)
phase = np.array([float(r["phase_deg"]) for r in rows])
L = lbas * BPS * BIT_MM; Lref = REF * BPS * BIT_MM
def wrap(d): return (d + 180.0) % 360.0 - 180.0
def circ_rms(diff):
    # choose c as circular median-ish: scan c grid, pick min rms (robust, global)
    cs = np.arange(0, 360, 0.25)
    best = min(((np.sqrt(np.mean(wrap(diff + c)**2)), c) for c in cs), key=lambda t: t[0])
    return best

# A as shipped (u,v -> r0,pitch at 133.3nm; c from summary -0.1739 replaced by fit)
r0A, pA = 24.17331443619965, 0.7340611201663617e-3
bA = pA/(2*math.pi)
thA = lambda Lv: np.degrees((np.sqrt(r0A**2 + 2*bA*Lv) - r0A)/bA)
dA = thA(L) - thA(np.array([Lref]))[0] - phase
rmsA, cA = circ_rms(dA)
print(f"A as-shipped + best c ({cA:+.2f}): phase rms = {rmsA:.4f} deg")

# B as shipped: b solved from DIS total-length constraint (2294880 sectors), as solver does
ri, ro = 23.98815, 57.856098
c1, c2, c3 = -0.014823, -0.002077, -0.000079
Lt = 2294880 * BPS * BIT_MM
rgrid = np.linspace(ri, ro, 40001)
xg = (rgrid-ri)/(ro-ri); fg = 1 + c1*xg + c2*xg**2 + c3*xg**3
from scipy.optimize import brentq
def total_len(b):
    return np.trapezoid(np.sqrt(rgrid**2 + (b*fg)**2)/(b*fg), rgrid)
bB = brentq(lambda b: total_len(b) - Lt, 1e-5, 1e-3, xtol=1e-14)
dthdr = 1.0/(bB*fg); dLdr = np.sqrt(rgrid**2 + (bB*fg)**2)/(bB*fg)
thg = cumulative_trapezoid(dthdr, rgrid, initial=0); Lg = cumulative_trapezoid(dLdr, rgrid, initial=0)
thB = lambda Lv: np.degrees(np.interp(Lv, Lg, thg))
dB = thB(L) - thB(np.array([Lref]))[0] - phase
rmsB, cB = circ_rms(dB)
print(f"B EST-H as-shipped + best c ({cB:+.2f}): phase rms = {rmsB:.4f} deg   (b from length constraint = {bB:.6e})")
