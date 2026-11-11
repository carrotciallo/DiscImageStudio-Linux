"""Colour lookup table from flash photos of a tile palette target (tiles / LUT v2 disc).

Each photo is fitted with discprobe.tilephoto. With the flash next to the lens, the
along-track diffraction condition depends only on the camera position C (from the
homography and the EXIF focal length): delta = 2 c.t, with c the unit vector from the tile
to the camera and t the track tangent.

Off-axis flash photos leave most of the disc dark, so A5/92 contrast is too weak to fix the
rotation. When the disc stayed put and only the phone moved, the disc's rotation in the
image is shared by the whole series: photos that decode fewer than MIN_IDS tile IDs are
refitted with the rotation of the best photo as a prior. Tiles are then marked "verified"
(ID decoded) or "anchored" (prior fit only); the charts are drawn for both.

Per swatch (layouts read by the current tilescan carry swatch centres) the table also gives
the tangential and radial components of l + c at the swatch centre, <name>_dt and <name>_dr,
with l the unit vector to the flash. --flash DX DY places the flash DX, DY mm from the lens
in the camera's image axes (x right, y down); the default 0 0 gives dt = 2 c.t as before.

Usage: python tools/flash_lut_tiles.py [--flash DX DY] LAYOUT.json IMG_a.jpeg IMG_b.jpeg ...
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe import tilephoto  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
import flash_lut  # noqa: E402

MIN_IDS = 10
PRIOR_TOL_DEG = 12.0


def _components(C, L, r_mm, a_deg):
    """(l + c).t and (l + c).r at a point of the disc."""
    a = math.radians(a_deg)
    p = np.array([r_mm * math.cos(a), r_mm * math.sin(a), 0.0])
    s = (C - p) / np.linalg.norm(C - p) + (L - p) / np.linalg.norm(L - p)
    return float(s @ np.array([-math.sin(a), math.cos(a), 0.0])), float(s @ np.array([math.cos(a), math.sin(a), 0.0]))


def main(layout_path, photos, out_dir=os.path.join("results", "flash_lut_tiles"), flash_offset_mm=(0.0, 0.0)):
    with open(layout_path, encoding="utf-8") as f:
        palette = json.load(f)["palette"]
    summaries = {}
    for p in photos:
        name = os.path.splitext(os.path.basename(p))[0]
        path = os.path.join(out_dir, name, "summary.json")
        if os.path.exists(path):                       # reuse an earlier first pass
            with open(path, encoding="utf-8") as f:
                summaries[p] = json.load(f)
        else:
            summaries[p] = tilephoto.analyse(p, layout_path, os.path.join(out_dir, name), mirrors=(False,))
    best = max(summaries, key=lambda p: summaries[p]["ids_ok"])
    ref = tilephoto.image_angle(np.array(summaries[best]["homography_disc_mm_to_px"]))
    print(f"reference rotation from {os.path.basename(best)} ({summaries[best]['ids_ok']} IDs): {ref:.1f} deg")
    anchored = set()
    for p, s in list(summaries.items()):
        if s["ids_ok"] < MIN_IDS and not s.get("angle_prior"):
            name = os.path.splitext(os.path.basename(p))[0]
            summaries[p] = tilephoto.analyse(p, layout_path, os.path.join(out_dir, name), mirrors=(False,),
                                             angle_prior=(ref, PRIOR_TOL_DEG))
        if summaries[p].get("angle_prior"):
            anchored.add(p)

    rows = []
    for p, s in summaries.items():
        name = os.path.splitext(os.path.basename(p))[0]
        H = np.array(s["homography_disc_mm_to_px"])
        rgb = tilephoto.load_photo(p)
        C, R = flash_lut.pose(H, flash_lut.focal_px(p, rgb.shape[1], rgb.shape[0]), rgb.shape[1] / 2,
                              rgb.shape[0] / 2, with_rotation=True)
        L = C + R.T @ np.array([flash_offset_mm[0], flash_offset_mm[1], 0.0])
        print(f"{name}: {s['ids_ok']} IDs{' (rotation prior)' if p in anchored else ''}, "
              f"camera at ({C[0]:.0f}, {C[1]:.0f}, {C[2]:.0f}) mm", flush=True)
        with open(os.path.join(out_dir, name, "tiles.csv"), encoding="utf-8") as f:
            for t in csv.DictReader(f):
                verified = t["id_ok"] == "1"
                if not verified and p not in anchored:
                    continue
                a, r = math.radians(float(t["design_angle_deg"])), float(t["radius_mm"])
                pt = np.array([r * math.cos(a), r * math.sin(a), 0.0])
                c = (C - pt) / np.linalg.norm(C - pt)
                row = {"photo": name, "ring": t["ring"], "sector": t["sector"], "verified": int(verified),
                       "delta": round(_components(C, L, r, float(t["design_angle_deg"]))[0], 4),
                       "view_tilt_deg": round(math.degrees(math.acos(c[2])), 1)}
                row.update({n: t[f"{n}_rgb"] for n in palette})
                if f"{palette[0]}_r_mm" in t:
                    for n in palette:
                        dt, dr = _components(C, L, float(t[f"{n}_r_mm"]), float(t[f"{n}_a_deg"]))
                        row[f"{n}_dt"], row[f"{n}_dr"] = round(dt, 4), round(dr, 4)
                rows.append(row)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "swatch_colours_vs_delta.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    flash_lut.NAMES = palette
    ver = [r for r in rows if r["verified"]]
    flash_lut.chart(ver, os.path.join(out_dir, "lut_chart_verified.png"))
    flash_lut.chart(rows, os.path.join(out_dir, "lut_chart_all.png"))
    for label, rr in (("verified", ver), ("verified + anchored", rows)):
        d = [r["delta"] for r in rr]
        print(f"{label}: {len(rr)} tile observations, delta {min(d):.2f} .. {max(d):.2f}")


if __name__ == "__main__":
    argv, offset = sys.argv[1:], (0.0, 0.0)
    if argv and argv[0] == "--flash":
        offset, argv = (float(argv[1]), float(argv[2])), argv[3:]
    main(argv[0], argv[1:], flash_offset_mm=offset)
