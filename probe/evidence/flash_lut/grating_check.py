"""Do the single-period textures follow the grating equation in the flash photos?

The EFMPlus channel pattern of a repeated byte is close to one along-track grating: a large
share of its AC power sits within 5 % of one period P (A5 0.85 um, 66 1.07 um, B9 1.42 um,
92 2.13 um; computed here with the exact encoder). With the flash at the lens, first order
sends lambda = |delta| * P back to the camera. For every verified tile observation where
that lambda is visible (400-700 nm) and no other order of the same texture is, this
compares the measured hue of the swatch (relative to the tile's mean swatch colour, which
removes the global cast) with the hue of lambda; a shuffle of the predictions within the
same texture gives the chance level. It also compares brightness (swatch / tile median)
inside and outside the visible first-order band.

    python evidence/flash_lut/grating_check.py > evidence/flash_lut/grating_check.txt
"""

import colorsys
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "evidence", "coverage"))
import discprobe.efmplus as E  # noqa: E402
from lut_scatter import wavelength_rgb  # noqa: E402
from period_search_v2 import STARTS, rows_for  # noqa: E402

T_UM = 0.1333
TEXTURES = ["A5", "66", "B9", "92"]
META = ("photo", "ring", "sector", "verified", "delta", "view_tilt_deg")


def main_period(spec, nrows=11):
    acc = None
    for seed, (dsv, land) in enumerate(STARTS):
        b, xs = E.Boundary(1, dsv, land), []
        for i, row in enumerate(rows_for(spec, nrows, seed)):
            for h in range(2):
                lv, b = E.encode_frame(row[91 * h:91 * (h + 1)], E.ROW_SYNC[i % 13][h], b)
                xs.append(lv)
        x = 2.0 * np.concatenate(xs) - 1
        x -= x.mean()
        p = np.abs(np.fft.rfft(x)) ** 2
        acc = p if acc is None else acc + p
    f = np.fft.rfftfreq(x.size, d=T_UM)
    k = int(np.argmax(acc[1:])) + 1
    near = np.abs(f - f[k]) < 0.05 * f[k]                  # the line broadened by syncs and DSV choices
    return 1 / f[k], acc[near].sum() / acc[1:].sum()


def hue_of(rgb):
    rgb = np.asarray(rgb, float)
    return colorsys.rgb_to_hsv(*np.clip(rgb / max(rgb.max(), 1e-3), 0, 1))[0] * 360


def visible(lam):
    return 0.40 <= lam <= 0.70


def main(path=os.path.join(HERE, "swatch_colours_vs_delta.csv")):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["verified"] == "1"]
    rng = np.random.default_rng(0)
    err = lambda m, p: np.median(np.abs((m - p + 180) % 360 - 180))
    print(f"{len(rows)} verified tile observations, |delta| up to {max(abs(float(r['delta'])) for r in rows):.2f}")
    for name in TEXTURES:
        P, share = main_period(name)
        pairs, rel_in, rel_out = [], [], []
        for r in rows:
            d = abs(float(r["delta"]))
            sw = np.array([[float(v) for v in r[k].split()] for k in r if k not in META])
            c = np.array([float(v) for v in r[name].split()])
            rel = c.sum() / np.median(sw.sum(1))
            orders = [d * P / m for m in (1, 2, 3)]
            if visible(orders[0]) and not any(visible(o) for o in orders[1:]):
                pairs.append((hue_of(c / (sw.mean(0) + 1e-3)), hue_of(wavelength_rgb(orders[0] * 1000))))
                rel_in.append(rel)
            elif not any(visible(o) for o in orders):
                rel_out.append(rel)
        line = f"{name:3s} P {P:.2f} um ({share * 100:.0f} % of power)  first order visible for |delta| " \
               f"{0.40 / P:.2f}-{0.70 / P:.2f}"
        if len(pairs) >= 5:
            v = np.array(pairs)
            e = err(v[:, 0], v[:, 1])
            null = np.array([err(v[:, 0], rng.permutation(v[:, 1])) for _ in range(2000)])
            line += f"\n    hue: n {len(v):3d}  median error {e:5.1f} deg  shuffled {np.median(null):5.1f}  " \
                    f"p = {np.mean(null <= e):.3f}"
        else:
            line += f"\n    hue: n {len(pairs)} (too few)"
        if rel_in and rel_out:
            line += f"\n    brightness / tile median: in band {np.median(rel_in):.2f} (n {len(rel_in)}), " \
                    f"no visible order {np.median(rel_out):.2f} (n {len(rel_out)})"
        print(line)


if __name__ == "__main__":
    main(*sys.argv[1:])
