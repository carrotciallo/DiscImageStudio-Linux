"""Compare where READ(12) and READ CD complete on a CD-ROM Mode 1 disc.

Both commands are timed against the same reference sector, target by target (READ(12) with
FUA, then READ CD with any expected sector type and user data only; READ CD has no FUA bit,
so the cache is bypassed with whatever the cache test finds: flush or eviction). If the two
read paths complete a fixed along-track length dL apart, the phase difference across radius is

    dphi(r) = C + dL / r          (C absorbs the reference term and fixed time delays)

108 frames (17.6 mm at 1.2 m/s) would show as about 23 deg between 25 and 58 mm, 3 frames as
about 0.6 deg. A difference that doesn't follow 1/r means the paths differ in some other way.
Only a relative check: it cannot fix the absolute along-track origin both paths share.

    python tools/cd_readcmd_compare.py --drive H: --geo results/geo-H-.../summary.json
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe import mmc  # noqa: E402
from discprobe.geo import Ladder  # noqa: E402
from discprobe.device import Device, raise_priority  # noqa: E402
from discprobe.timing import TimingProbe  # noqa: E402

ANY_TYPE = 0  # READ CD expected sector type; IMAPI writes CD data as Mode 2 Form 1, so "Mode 1" (2) is refused


class ReadCdProbe(TimingProbe):
    """TimingProbe whose timed reads are READ CD (any sector type, 2048 user bytes)."""

    def _read(self, lba, count=1, fua=False, label=""):
        if getattr(self, "method", None) != "readcd":
            return super()._read(lba, count, fua, label)
        res = self._cmd(mmc.read_cd(lba, count, sector_type=ANY_TYPE), 2048 * count)
        self._record(label, lba, "readcd", False, res)
        return res


def ladder(dev, fit, speed, readcd):
    L = Ladder(dev, media="cd", ref_lba=fit["reference_lba"], speed_kbs=speed, log=print)
    if readcd:
        old = L.tp
        L.tp = ReadCdProbe(dev, log=lambda *_: None, reps=old.reps, speed_kbs=speed,
                           host_delay_ms=old.host_delay_s * 1e3, media="cd")
    tp = L.tp
    tp.setup()
    if readcd:
        tp.method = "readcd"
        if not tp._read(fit["reference_lba"], label="probe").ok:
            raise SystemExit("READ CD (user data) is refused on this drive/disc")
    tp.cache_test()
    print(f"{'READ CD' if readcd else 'READ(12)'}: cache strategy {tp.strategy}")
    L.u, L.v, L.c = fit["u"], fit["v"], math.radians(fit["c_deg"])
    L.ranges = [(0, tp.last_lba + 1)]
    L.ref = fit["reference_lba"]
    L.n_ref = L._n_end(L.ref)
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--drive", required=True)
    ap.add_argument("--geo", required=True, help="summary.json of a CD geo run on this disc")
    ap.add_argument("--speed", type=int, default=2822)
    ap.add_argument("--lbas", type=int, nargs="+",
                    default=[5000, 30000, 60000, 90000, 120000, 150000, 210000, 240000,
                             270000, 300000, 330000, 352000])
    ap.add_argument("--out", help="write the per-target results here (JSON)")
    a = ap.parse_args()
    fit = json.load(open(a.geo))["fit"]
    b = fit["bit_nm_assumed"] * 1e-6
    raise_priority()
    rows = []
    with Device(a.drive) as dev:
        A = ladder(dev, fit, a.speed, readcd=False)
        B = ladder(dev, fit, a.speed, readcd=True)
        t0 = time.time()
        while time.time() - t0 < 10:
            A.tp._measure(A.ref, "warm")
        A.settle()
        B.T = A.T
        for lba in a.lbas:
            try:
                ma = A._measure_retry(lba)
                B.T = A.T
                mb = B._measure_retry(lba)
            except RuntimeError as e:
                print(lba, e)
                A.settle()
                continue
            if ma is None or mb is None:
                print(lba, "failed")
                continue
            r = b * math.sqrt(fit["u"] ** 2 + fit["v"] * ma["n"] / math.pi)
            d = (mb["phase_deg"] - ma["phase_deg"] + 180) % 360 - 180
            s = math.hypot(ma["sigma_deg"], mb["sigma_deg"])
            rows.append(dict(lba=lba, r_mm=r, read12_deg=ma["phase_deg"], readcd_deg=mb["phase_deg"],
                             diff_deg=d, sigma_deg=s, readcd_std_deg=mb["std_deg"], readcd_used=mb["used"]))
            print(f"lba {lba:7d}  r {r:6.2f} mm  READ CD - READ(12) {d:+8.3f} deg  +/- {s:.2f}"
                  f"  (READ CD std {mb['std_deg']:.2f}, n {mb['used']})", flush=True)
    if len(rows) >= 3:
        r = np.array([x["r_mm"] for x in rows])
        d = np.array([x["diff_deg"] for x in rows])
        w = 1 / np.array([x["sigma_deg"] for x in rows])
        X = np.c_[np.ones_like(r), np.degrees(1 / r)] * w[:, None]  # dL in mm -> deg via 1/r rad
        coef, *_ = np.linalg.lstsq(X, d * w, rcond=None)
        cov = np.linalg.inv(X.T @ X)
        res = d - (np.c_[np.ones_like(r), np.degrees(1 / r)] @ coef)
        chi2 = float(np.sum((res * w) ** 2))
        scale = math.sqrt(max(1.0, chi2 / max(1, len(r) - 2)))
        dL, sdL = coef[1], math.sqrt(cov[1, 1]) * scale
        frame_mm = 588 * b
        print(f"\nfit dphi = C + dL/r: C {coef[0]:+.3f} deg, dL {dL:+.3f} +/- {sdL:.3f} mm "
              f"= {dL / frame_mm:+.2f} +/- {sdL / frame_mm:.2f} frames; chi2/dof {chi2 / max(1, len(r) - 2):.2f}, "
              f"rms after fit {np.sqrt(np.mean(res ** 2)):.3f} deg")
        if a.out:
            json.dump(dict(rows=rows, C_deg=coef[0], dL_mm=dL, dL_sigma_mm=sdL,
                           dL_frames=dL / frame_mm, chi2_dof=chi2 / max(1, len(r) - 2)),
                      open(a.out, "w"), indent=2)


if __name__ == "__main__":
    sys.exit(main())
