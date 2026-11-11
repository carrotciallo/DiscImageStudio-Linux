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

# Model A family: constant pitch, params (r0, pitch_um, c_deg)
def thetaA(Lv, r0, p_um):
    b = p_um*1e-3/(2*math.pi)
    return np.degrees((np.sqrt(r0**2 + 2*b*Lv) - r0)/b)
def resA(p):
    return wrap(thetaA(L, p[0], p[1]) - thetaA(np.array([Lref]), p[0], p[1])[0] + p[2] - phase)
fitA = least_squares(resA, [24.1733, 0.734061, 0.0])
rA = resA(fitA.x)
print(f"A const-pitch free(r0,pitch,c): r0={fitA.x[0]:.5f} pitch={fitA.x[1]:.6f} c={fitA.x[2]:+.3f}  rms={np.sqrt(np.mean(rA**2)):.4f} max={np.max(np.abs(rA)):.4f}")

# Model B family: EST-H shape fixed (ri, ro, cubic), params (b scale, c_deg)
ri, ro = 23.98815, 57.856098
c1, c2, c3 = -0.014823, -0.002077, -0.000079
rgrid = np.linspace(ri, ro, 40001)
xg = (rgrid-ri)/(ro-ri); fg = 1 + c1*xg + c2*xg**2 + c3*xg**3
def thetaB_of(b):
    dthdr = 1.0/(b*fg); dLdr = np.sqrt(rgrid**2 + (b*fg)**2)/(b*fg)
    th = cumulative_trapezoid(dthdr, rgrid, initial=0); Lg = cumulative_trapezoid(dLdr, rgrid, initial=0)
    return lambda Lv: np.interp(Lv, Lg, th)
def resB(p):
    thB = thetaB_of(p[0])
    return wrap(np.degrees(thB(L) - thB(np.array([Lref]))[0]) + p[1] - phase)
fitB = least_squares(resB, [1.182078e-4, 0.0])
rB = resB(fitB.x)
bB = fitB.x[0]
print(f"B EST-H shape free(b,c): b={bB:.6e} (pitch@ri {2*math.pi*bB*fg[0]*1000:.4f} um, @ro {2*math.pi*bB*fg[-1]*1000:.4f} um) c={fitB.x[1]:+.3f}  rms={np.sqrt(np.mean(rB**2)):.4f} max={np.max(np.abs(rB)):.4f}")
print()
print("lba       phase    resA     resB")
for i in range(len(lbas)):
    print(f"{int(lbas[i]):>8}  {phase[i]:7.2f}  {rA[i]:+.3f}  {rB[i]:+.3f}")
