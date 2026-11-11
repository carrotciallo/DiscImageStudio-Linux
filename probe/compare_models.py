import csv, math
import numpy as np
from scipy.optimize import brentq
from scipy.integrate import cumulative_trapezoid

BIT_MM = 133.3e-6
BITS_PER_SECTOR = 38688
REF_LBA = 1009904

rows = list(csv.DictReader(open("/home/carrot/muse/disc-probe/results/geo-sr0-20261109-023521/targets.csv")))
lbas = np.array([int(r["lba"]) for r in rows], float)
meas = np.array([float(r["unwrapped_deg"]) for r in rows])  # measured angle rel. to ref, deg
res_a_given = np.array([float(r["residual_deg"]) for r in rows])

def L_of_lba(lba): return lba * BITS_PER_SECTOR * BIT_MM

# Model A: disc-probe constant pitch
r0A, pA = 24.17331443318845, 0.7340611217412282e-3  # mm
bA = pA / (2*math.pi)
def theta_A(L):
    # L = r0*t + b*t^2/2  (b^2 term negligible)
    return (np.sqrt(r0A**2 + 2*bA*L) - r0A) / bA
angA = np.degrees(theta_A(L_of_lba(lbas)) - theta_A(L_of_lba(REF_LBA)))
resA = angA - meas

# Model B: EST-H cubic pitch (DIS convention dr/dth = b*(1+c1 x+c2 x^2+c3 x^3), x=(r-ri)/(ro-ri))
ri, ro = 23.98815, 57.856098
c1, c2, c3 = -0.014823, -0.002077, -0.000079
Lt = 2294880 * BITS_PER_SECTOR * BIT_MM
rgrid = np.linspace(ri, ro, 200001)
x = (rgrid - ri) / (ro - ri)
f = 1 + c1*x + c2*x**2 + c3*x**3
def total_len(b):
    dLdr = np.sqrt(rgrid**2 + (b*f)**2) / (b*f)
    return np.trapezoid(dLdr, rgrid)
bB = brentq(lambda b: total_len(b) - Lt, 1e-5, 1e-3, xtol=1e-14)
dthdr = 1.0 / (bB * f)
dLdr = np.sqrt(rgrid**2 + (bB*f)**2) / (bB * f)
th_grid = cumulative_trapezoid(dthdr, rgrid, initial=0)
L_grid = cumulative_trapezoid(dLdr, rgrid, initial=0)
def theta_B(L):
    return np.interp(L, L_grid, th_grid)
angB = np.degrees(theta_B(L_of_lba(lbas)) - theta_B(L_of_lba(REF_LBA)))
resB = angB - meas

def stats(name, res):
    print(f"{name}: rms {np.sqrt(np.mean(res**2)):.4f} deg, max|.| {np.max(np.abs(res)):.4f}, mean {np.mean(res):+.4f}")
print(f"bB solved = {bB:.6e} mm/rad -> pitch at ri {2*math.pi*bB*f[0]*1000:.4f} um, at ro {2*math.pi*bB*f[-1]*1000:.4f} um")
stats("A disc-probe constant (recomputed)", resA)
stats("A residuals as shipped in targets.csv", res_a_given)
stats("B EST-H cubic (no warp)", resB)
print()
print("lba        radiusA   radiusB   resA     resB   (deg)")
rA = np.sqrt(r0A**2 + 2*bA*L_of_lba(lbas))
rB = np.interp(L_of_lba(lbas), L_grid, rgrid)
for i in range(len(lbas)):
    print(f"{int(lbas[i]):>8}  {rA[i]:8.3f}  {rB[i]:8.3f}  {resA[i]:+.3f}  {resB[i]:+.3f}")
