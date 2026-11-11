import sys, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates
f = sys.argv[1]; out = sys.argv[2]
im = np.asarray(Image.open(f).convert('RGB')).astype(np.float32).mean(2)
cx, cy = 2200., 1640.
for it in range(4):
    th = np.radians(np.arange(0, 360, 1.0)); rr = np.arange(1050, 1500, 1.0)
    xx = cx + rr[None, :] * np.cos(th)[:, None]; yy = cy + rr[None, :] * np.sin(th)[:, None]
    P = map_coordinates(gaussian_filter(im, 2), [yy, xx], order=1, mode='nearest')
    G = np.gradient(P, axis=1)            # the disc rim: dark inside to bright thin edge, take the strongest ridge
    R = P - gaussian_filter1d(P, 12, axis=1)
    idx = R.argmax(1); r = rr[idx]
    x = cx + r * np.cos(th); y = cy + r * np.sin(th)
    keep = np.ones_like(x, bool)
    for _ in range(6):
        A = np.c_[x[keep]**2, x[keep]*y[keep], y[keep]**2, x[keep], y[keep], np.ones(keep.sum())]
        _, _, Vt = np.linalg.svd(A / A.std(0).clip(1e-9) if False else A - 0, full_matrices=False)
        c = Vt[-1]; a_, b_, c_, d_, e_, f_ = c
        M = np.array([[a_, b_/2], [b_/2, c_]]); ctr = np.linalg.solve(-2*M, [d_, e_])
        val = np.c_[x**2, x*y, y**2, x, y, np.ones_like(x)] @ c
        s = np.median(np.abs(val[keep])); keep = np.abs(val) < 3 * s
    cx, cy = ctr
w, V = np.linalg.eigh(M); k = c_ + 0
k = -(a_*cx*cx + b_*cx*cy + c_*cy*cy + d_*cx + e_*cy + f_)
ax = np.sqrt(k / w); print('centre', round(cx, 1), round(cy, 1), 'semi axes', np.round(ax, 1), 'axis ratio', round(float(ax.min() / ax.max()), 4), 'kept', int(keep.sum()), 'of', keep.size)
B = V @ np.diag(ax)                       # unit circle -> ellipse
np.savez(out + '.npz', centre=[cx, cy], B=B)
a = np.radians(np.arange(0, 360, 0.1)); rho = np.arange(0.28, 1.0, 0.0005)
u = rho[None, :] * np.cos(a)[:, None]; v = rho[None, :] * np.sin(a)[:, None]
X = cx + B[0, 0] * u + B[0, 1] * v; Y = cy + B[1, 0] * u + B[1, 1] * v
U = map_coordinates(im, [Y, X], order=1, mode='nearest')
np.save(out + '_U.npy', U.astype(np.float32))
hp = U - gaussian_filter(U, (60, 60))
lo, hi = np.percentile(hp, [1, 99])
Image.fromarray((np.clip((hp - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)).resize((1440, 720)).save(out + '_unrolled.png')
