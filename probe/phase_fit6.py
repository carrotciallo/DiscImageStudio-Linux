import csv, math
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.optimize import brentq

BIT_MM = 133.3e-6; BPS = 38688; REF = 1009904; BLK = 16
rows = list(csv.DictReader(open("/home/carrot/muse/disc-probe/results/geo-sr0-20261109-023521/targets.csv")))
lbas = np.array([int(r["lba"]) for r in rows], float)
phase = np.array([float(r["phase_deg"]) for r in rows])
resid_shipped = np.array([float(r["residual_deg"]) for r in rows])
L = (lbas + BLK) * BPS * BIT_MM; Lref = (REF + BLK) * BPS * BIT_MM
def wrap(d): return (d + 180.0) % 360.0 - 180.0
def best_c_rms(diff):
    cs = np.arange(0, 360, 0.1)
    vals = [np.sqrt(np.mean(wrap(diff + c)**2)) for c in cs]
    i = int(np.argmin(vals)); return vals[i], cs[i]

def dis_theta(ri, ro, total_sectors, c1, c2, c3):
    Lt = total_sectors * BPS * BIT_MM
    rgrid = np.linspace(ri, ro, 60001)
    xg = (rgrid-ri)/(ro-ri); fg = 1 + c1*xg + c2*xg**2 + c3*xg**3
    def total_len(b): return np.trapezoid(np.sqrt(rgrid**2 + (b*fg)**2)/(b*fg), rgrid)
    b = brentq(lambda bb: total_len(bb) - Lt, 1e-6, 1e-2, xtol=1e-15)
    dthdr = 1.0/(b*fg); dLdr = np.sqrt(rgrid**2 + (b*fg)**2)/(b*fg)
    th = cumulative_trapezoid(dthdr, rgrid, initial=0); Lg = cumulative_trapezoid(dLdr, rgrid, initial=0)
    pitch = lambda rr: 2*math.pi*b*(1 + c1*((rr-ri)/(ro-ri)) + c2*((rr-ri)/(ro-ri))**2 + c3*((rr-ri)/(ro-ri))**3)*1000
    return (lambda Lv: np.degrees(np.interp(Lv, Lg, th))), pitch

thA, pA = dis_theta(24.17331443318845, 57.914142049973165, 2298496, -1.8146318292173538e-08, 4.455901357213194e-08, -3.27073416773052e-08)
dA = thA(L) - thA(np.array([Lref]))[0] - phase
rmsA, cA = best_c_rms(dA)
print(f"A disc-probe preset: pitch={pA(40.0):.6f}um  phase rms={rmsA:.4f} (c={cA:+.1f})  [tool unwrapped rms={np.sqrt(np.mean(resid_shipped**2)):.4f}]")
thB, pB = dis_theta(23.98815, 57.856098, 2294880, -0.014823, -0.002077, -0.000079)
dB = thB(L) - thB(np.array([Lref]))[0] - phase
rmsB, cB = best_c_rms(dB)
print(f"B EST-H preset:      pitch@24={pB(24.0):.4f} @40={pB(40.0):.4f} @57.8={pB(57.8):.4f}um  phase rms={rmsB:.4f} (c={cB:+.1f})")
print()
print("lba        resA     resB")
rAw = wrap(dA + cA); rBw = wrap(dB + cB)
for i in range(len(lbas)):
    print(f"{int(lbas[i]):>8}  {rAw[i]:+.3f}  {rBw[i]:+.3f}")
