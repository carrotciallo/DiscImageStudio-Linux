"""Read beacon target tiles (beacondisc) from one photo, with no whole-disc fit.

Bullseyes are found by matched filtering of the edge strength of log colour, so a ring's
brightness and colour do not matter, only that neighbouring rings differ. Three bullseyes that
fit a tile's L shape give a local map from the tile to the image, and the code bits are read by
comparing each cell pair with the tile's own reference pair.

The local map treats the tile as flat, an affine fit from three points, which is enough for
the size of one tile. Accurate positions for pose work should come from
refining the bullseye centres afterwards.
"""

from __future__ import annotations

import math

import numpy as np

from . import beacondisc as bd

EPS = 2.0                       # added to 8-bit values before the log, sets the darkest usable signal
MAX_ERRORS = 1                  # accepted hard errors out of 16; a random pattern passes with p = 0.7 %
MIN_CONTRAST = 0.15             # reference contrast (log units) below which a pair counts as unreadable
MIN_BIT = 0.35                  # |soft value| below which a bit counts as unread: noise must not pass as a bit


def edge_map(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Edge strength of log colour, and the log colour image (float, H x W x 3)."""
    from scipy.ndimage import gaussian_filter
    lg = np.log(rgb.astype(np.float32) + EPS)
    e = np.zeros(lg.shape[:2], np.float32)
    for c in range(3):
        s = gaussian_filter(lg[..., c], 1.0)
        e += np.hypot(np.gradient(s, axis=0), np.gradient(s, axis=1))
    return np.minimum(e, 1.5), lg


def _ring_kernel(radii_px, width=1.5, ring_gain=1.0):
    n = int(radii_px[-1] + 3 * width + 2)
    y, x = np.mgrid[-n:n + 1, -n:n + 1]
    d = np.hypot(x, y)
    k = np.zeros(d.shape, np.float32)
    for r in radii_px:
        ring = np.exp(-0.5 * ((d - r) / width) ** 2)
        k += ring_gain * ring / ring.sum()
    # Between and beyond the edges should be quiet: this rejects textured areas, which also score on the edges.
    mids = [radii_px[0] / 2] + [(a + b) / 2 for a, b in zip(radii_px, radii_px[1:])] + [radii_px[-1] + 2.5 * width]
    for r in mids:
        ring = np.exp(-0.5 * ((d - r) / max(width * 0.8, 1.0)) ** 2)
        k -= ring / ring.sum() * len(radii_px) / len(mids)
    return k


def find_bullseyes(edges: np.ndarray, px_per_mm: float, radii_mm=bd.FINDER_RADII_MM, min_score: float = 0.12,
                   max_peaks: int = 400) -> list[tuple[float, float, float]]:
    """(x, y, score) of candidate bullseyes, strongest first."""
    from scipy.ndimage import maximum_filter
    from scipy.signal import fftconvolve
    k = _ring_kernel([r * px_per_mm for r in radii_mm], width=max(1.2, 0.05 * px_per_mm))
    resp = fftconvolve(edges, k[::-1, ::-1], mode="same")
    near = int(1.5 * radii_mm[-1] * px_per_mm) | 1
    peaks = np.argwhere((resp == maximum_filter(resp, size=near)) & (resp > min_score))
    out = sorted(((float(x), float(y), float(resp[y, x])) for y, x in peaks), key=lambda t: -t[2])
    return out[:max_peaks]


def _local_mm(ring: int) -> dict[str, np.ndarray]:
    """Bullseyes of a sector in a flat frame (x along the arc, y outward), with A at the origin."""
    f = bd.finder_centres(ring, 0)
    a0 = (f["A"][1] + f["C"][1]) / 2
    out = {}
    for name, (r, a) in f.items():
        out[name] = np.array([r * math.sin(a - a0), r * math.cos(a - a0)])
    return out


def _cell_mm(ring: int, row: float, col: float) -> np.ndarray:
    f = bd.finder_centres(ring, 0)
    a0 = (f["A"][1] + f["C"][1]) / 2
    r, a = bd.id_point(ring, 0, row, col)
    return np.array([r * math.sin(a - a0), r * math.cos(a - a0)])


def _affine(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    return np.linalg.solve(np.column_stack([src, np.ones(3)]), dst)      # 3 x 2, row-vector convention


def _patch(lg, xy, half):
    x, y = int(round(xy[0])), int(round(xy[1]))
    p = lg[max(y - half, 0):y + half + 1, max(x - half, 0):x + half + 1]
    return np.median(p.reshape(-1, 3), axis=0) if p.size else np.zeros(3)


def _read(lg, ring, A):
    """Soft values of the 16 bits under a map A, and the reference contrast of each pair."""
    px_per_mm = math.sqrt(abs(np.linalg.det(A[:2])))
    half = max(1, int(0.3 * px_per_mm))
    diffs = []
    for row, col in bd.slots():
        inner = _patch(lg, np.append(_cell_mm(ring, row + 0.5, col + 0.5), 1) @ A, half)
        outer = _patch(lg, np.append(_cell_mm(ring, row + 1.5, col + 0.5), 1) @ A, half)
        diffs.append(inner - outer)
    refs = {pair: diffs[s] for s, pair in bd.REFERENCE_SLOTS.items()}
    power = {p: float(refs[p] @ refs[p]) for p in refs}
    bits = [s for s in range(len(diffs)) if s not in bd.REFERENCE_SLOTS]
    soft = np.zeros(16)
    for i, s in enumerate(bits):
        p = bd.BIT_PAIR[i]
        if math.sqrt(power[p]) >= MIN_CONTRAST:
            v = float(diffs[s] @ refs[p]) / power[p]
            soft[i] = v if abs(v) >= MIN_BIT else 0.0
    return soft, {p: math.sqrt(power[p]) for p in power}


def _best_id(soft):
    """Best ID, its hard errors, bits read, score, and how far the runner-up's score is behind."""
    scored = []
    for tid in range(sum(bd.sectors_per_ring())):
        w = bd.codeword(tid) * 2 - 1
        scored.append((float(np.clip(soft * w, -1, 1).sum()), tid, int(((soft * w) < 0).sum())))
    scored.sort(reverse=True)
    return scored[0][1], scored[0][2], int((soft != 0).sum()), scored[0][0], scored[0][0] - scored[1][0]


def read_tiles(rgb: np.ndarray, px_per_mm: float, max_candidates: int = 150) -> list[dict]:
    """Decoded tiles: id, ring, sector, errors, bits read, bullseye pixels. px_per_mm may be rough (about +-25 %)."""
    edges, lg = edge_map(rgb)
    peaks = find_bullseyes(edges, px_per_mm)[:max_candidates]
    pts = np.array([p[:2] for p in peaks]) if peaks else np.zeros((0, 2))
    found: dict[int, dict] = {}
    for ring in range(len(bd.RING_EDGES_MM) - 1):
        f = _local_mm(ring)
        ab, bc = np.linalg.norm(f["B"] - f["A"]), np.linalg.norm(f["C"] - f["B"])
        for ib, b in enumerate(pts):
            d = np.linalg.norm(pts - b, axis=1) / px_per_mm
            near_a = np.nonzero((d > ab * 0.65) & (d < ab * 1.35))[0]
            near_c = np.nonzero((d > bc * 0.65) & (d < bc * 1.35))[0]
            for ia in near_a:
                for ic in near_c:
                    if ia == ic:
                        continue
                    u, v = pts[ia] - b, pts[ic] - b
                    # Seen from the data side, B->A is inward and B->C goes counter-clockwise: with
                    # image y down, that makes the cross product positive whatever the rotation.
                    cross = (u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v))
                    if cross < 0.65:
                        continue
                    A = _affine(np.array([f["A"], f["B"], f["C"]]), pts[[ia, ib, ic]])
                    soft, contrast = _read(lg, ring, A)
                    tid, errors, known, score, margin = _best_id(soft)
                    # All 16 bits confirm an ID by themselves. One pair alone keeps distance 2 at
                    # best, so its reads are only "weak" and need another check, e.g. the rim fit.
                    strong = known == 16 and errors <= MAX_ERRORS
                    weak = known == 8 and errors == 0 and margin >= 1.0
                    if not (strong or weak):
                        continue
                    rs = bd.ring_sector(tid)
                    if rs[0] != ring:
                        continue
                    rec = {"id": tid, "ring": rs[0], "sector": rs[1], "strong": strong, "errors": errors, "bits_read": known,
                           "score": round(score, 2), "contrast": {str(k): round(v, 3) for k, v in contrast.items()},
                           "finders_px": {"A": pts[ia].round(1).tolist(), "B": b.round(1).tolist(), "C": pts[ic].round(1).tolist()}}
                    old = found.get(tid)
                    if old is None or (strong, score) > (old["strong"], old["score"]):
                        found[tid] = rec
    return sorted(found.values(), key=lambda r: r["id"])


def fit_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares homography (DLT) from disc mm to image pixels."""
    a = []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    return np.linalg.svd(np.array(a, float))[2][-1].reshape(3, 3)


def project(H: np.ndarray, x, y) -> np.ndarray:
    q = H @ np.stack([np.asarray(x, float), np.asarray(y, float), np.ones_like(np.asarray(x, float))])
    return (q[:2] / q[2]).T


def _xy(r, a):
    return r * math.cos(a), r * math.sin(a)


def read_guided(lg: np.ndarray, H: np.ndarray) -> list[dict]:
    """Read every tile where a whole-disc map says it is. A tile counts only if the code read there is
    that tile's own, which is an independent check: with 16 bits at most 1 may differ, with 8 none."""
    out = []
    for tid in range(sum(bd.sectors_per_ring())):
        ring, sector = bd.ring_sector(tid)
        f, fc = _local_mm(ring), bd.finder_centres(ring, sector)
        px = {k: project(H, *_xy(*fc[k])) for k in "ABC"}
        A = _affine(np.array([f["A"], f["B"], f["C"]]), np.array([px["A"], px["B"], px["C"]]))
        soft, contrast = _read(lg, ring, A)
        w = bd.codeword(tid) * 2 - 1
        known, errors = int((soft != 0).sum()), int(((soft * w) < 0).sum())
        best = _best_id(soft)
        ok = (known == 16 and errors <= MAX_ERRORS) or (known >= 8 and errors == 0)
        out.append({"id": tid, "ring": ring, "sector": sector, "read": bool(ok and best[0] == tid), "errors": errors,
                    "bits_read": known, "contrast": {str(k): round(v, 3) for k, v in contrast.items()},
                    "finders_px": {k: px[k].round(1).tolist() for k in "ABC"}})
    return out


def read_disc(rgb: np.ndarray, px_per_mm: float, passes: int = 3) -> dict:
    """Strong tiles fix a whole-disc map, the map reads the other tiles, and each pass refits on what was
    read, snapping predicted bullseyes to detected ones within 1 mm."""
    first = [t for t in read_tiles(rgb, px_per_mm) if t["strong"]]
    if len(first) < 2:
        return {"seed_tiles": len(first), "H": None, "tiles": []}
    edges, lg = edge_map(rgb)
    peaks = np.array([p[:2] for p in find_bullseyes(edges, px_per_mm)]).reshape(-1, 2)
    src, dst = [], []
    for t in first:
        fc = bd.finder_centres(t["ring"], t["sector"])
        for k in "ABC":
            src.append(_xy(*fc[k]))
            dst.append(t["finders_px"][k])
    H = fit_homography(np.array(src), np.array(dst))
    tiles = []
    for _ in range(passes):
        tiles = read_guided(lg, H)
        src, dst = [], []
        for t in tiles:
            if not t["read"]:
                continue
            fc = bd.finder_centres(t["ring"], t["sector"])
            for k in "ABC":
                d = np.linalg.norm(peaks - np.array(t["finders_px"][k]), axis=1)
                if d.size and d.min() < px_per_mm:
                    src.append(_xy(*fc[k]))
                    dst.append(peaks[int(d.argmin())])
        if len(src) >= 6:
            H = fit_homography(np.array(src), np.array(dst))
    if not src:  # strong tiles seeded the map, but no bullseye was found near any tile that was read
        return {"seed_tiles": len(first), "H": H.tolist(), "tiles": tiles, "fit_points": 0}
    pred = project(H, *np.array(src).T)
    return {"seed_tiles": len(first), "H": H.tolist(), "tiles": tiles, "fit_points": len(src),
            "fit_rms_mm": float(np.sqrt(np.mean(np.sum((pred - np.array(dst)) ** 2, axis=1))) / px_per_mm)}

