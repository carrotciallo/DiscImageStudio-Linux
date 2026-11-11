import sys, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
sys.stdout.reconfigure(encoding='utf-8')
PX = 600 / 25.4; K = 3.237
seeds = {'left': ((80, 478), (320, 497)), 'right': ((670, 528), (918, 550))}
def trace(g, p0, p1):
    p0, p1 = np.array(p0, float) * K, np.array(p1, float) * K
    L = np.hypot(*(p1 - p0)); u = (p1 - p0) / L; n = np.array([-u[1], u[0]])
    out = []
    for it in range(3):
        pts = []
        for s in np.arange(0, L, 0.6 * PX):
            ss = s + np.arange(-7, 7.1, 1.0); tt = np.arange(-30, 30.1, 0.5)
            X = p0[0] + ss[None] * u[0] + tt[:, None] * n[0]; Y = p0[1] + ss[None] * u[1] + tt[:, None] * n[1]
            prof = map_coordinates(g, [Y, X], order=1).mean(1); prof = prof - np.median(prof)
            sm = gaussian_filter(prof, 2)
            j = int(np.argmax(sm))
            snr = sm[j] / (1.4826 * np.median(np.abs(sm - np.median(sm))) + 1e-6)
            if 2 < j < len(tt) - 3:
                y0, y1, y2 = sm[j - 1], sm[j], sm[j + 1]; d = tt[j] + 0.5 * 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)
                pts.append((s, d, snr))
        P = np.array(pts); good = P[:, 2] > 2.5
        for _ in range(5):
            c = np.polyfit(P[good, 0], P[good, 1], 1); e = P[:, 1] - np.polyval(c, P[:, 0]); good = (P[:, 2] > 2.5) & (np.abs(e) < max(3, 2.5 * e[good].std()))
        # refine the frame
        a = p0 + u * 0 + n * np.polyval(c, 0); b = p0 + u * L + n * np.polyval(c, L); p0, p1 = a, b
        L = np.hypot(*(p1 - p0)); u = (p1 - p0) / L; n = np.array([-u[1], u[0]])
    return p0, u, n, P, e, good
for name in ('dvd1', 'dvd2'):
    im = np.asarray(Image.open(sys.argv[1] + '/' + name + '.bin').convert('RGB')).astype(np.float32).mean(2)
    g = im - gaussian_filter(im, 18)
    res = {}
    for k, (a, b) in seeds.items():
        res[k] = trace(g, a, b)
    (pa, ua, na, Pa, ea, ga), (pb, ub, nb, Pb, eb, gb) = res['left'], res['right']
    # centre of the disc approximated by the middle of the two inner ends; r is measured from there
    ang = np.degrees(np.arccos(abs(ua @ ub)))
    mid = (pa + ua * Pa[-1, 0] + pb) / 2
    gap = abs((pb - pa) @ na) / PX
    print(name, 'left/right direction differ', round(float(ang), 3), 'deg; gap of right start from left line', round(float(gap), 3), 'mm')
    for k, (p0, u, n, P, e, good) in res.items():
        xy = p0[None] + P[:, 0][:, None] * u[None]; r = np.hypot(*(xy - mid).T) / PX
        print(f'  {k}: {good.sum()} of {len(good)} points, r {r[good].min():.1f}-{r[good].max():.1f} mm, rms {e[good].std() / PX:.3f} mm')
        for a_, b_ in ((25, 30), (30, 35), (35, 40), (40, 45), (45, 50), (50, 55), (55, 60)):
            m = good & (r >= a_) & (r < b_)
            print(f'     {a_}-{b_}: {np.median(e[m]) / PX:+.3f} (n {int(m.sum())})' if m.any() else f'     {a_}-{b_}: -')
