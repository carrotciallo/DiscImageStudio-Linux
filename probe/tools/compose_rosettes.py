"""Colour test: four-petal rosettes tiled over the disc, one texture per petal.

Within one rosette all petals share the light and viewing angle, so if along-track period
and run length give distinct colours, every rosette shows several colours side by side.
Textures (most mutually distinct in the palette-target photos, evidence/tilephoto):
petals A5 (3.2T), 92 (16T), 66 (4T), ED00 (64T); centre 2AE304 (48T); background the
aperiodic 8T mix (least saturated). Each ring rotates the petal order by one, so texture
and petal direction (relative to the track) are not tied together.

Usage: python tools/compose_rosettes.py  ->  iso/rosettes_design.npy, iso/rosettes_preview.png, textures in
the printed command line.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe.imagedisc import CELL_MM, HALF_MM, SIZE  # noqa: E402

TEXTURES = ["MIX:92,87,83,8D,60", "A5", "92", "66", "ED00", "2AE304"]   # label 0 = background
PETALS = [1, 2, 3, 4]
CENTRE = 5
RINGS_MM = (28.5, 36.0, 43.5, 51.0)
SCALE_MM = (55.2, 57.5)            # angle scale: A5 band, 92 ticks every 10 deg and numbers every 30 deg
FONT = r"C:\Windows\Fonts\msyhbd.ttc"
PITCH_MM = 8.6                    # rosette spacing along the arc
PETAL_LEN, PETAL_W, PETAL_OFF, CORE_R = 3.3, 1.9, 1.95, 0.85
R_MIN, R_MAX = 24.6, 57.6


def _stamp(labels, mask, cx_mm, cy_mm, up_deg, value):
    """Paste a glyph mask (True = ink) centred at (cx, cy) mm with its top pointing up_deg."""
    from PIL import Image
    im = Image.fromarray((mask * 255).astype(np.uint8)).rotate(up_deg - 90.0, resample=Image.BILINEAR, expand=True)
    m = np.asarray(im) > 127
    h, w = m.shape
    x0 = round((cx_mm + HALF_MM) / CELL_MM - w / 2)
    y0 = round((HALF_MM - cy_mm) / CELL_MM - h / 2)
    labels[y0:y0 + h, x0:x0 + w][m] = value


def _numbers(labels):
    """Numbers every 30 deg just inside the ticks, and a 0-deg arrow, all in 92 on the A5 band."""
    from PIL import Image, ImageDraw, ImageFont
    size = round(1.3 / CELL_MM)
    try:
        font = ImageFont.truetype(FONT, size)
    except OSError:                 # not on Windows; the numbers only label the scale, so any font will do
        font = ImageFont.load_default(size)
    r_txt = SCALE_MM[0] + 0.55 * (SCALE_MM[1] - SCALE_MM[0]) + 0.35
    for a in range(0, 360, 30):
        text = str(a)
        im = Image.new("L", (size * len(text), round(size * 1.3)), 0)
        ImageDraw.Draw(im).text((0, 0), text, font=font, fill=255)
        m = np.asarray(im) > 127
        m = m[:, m.any(0)]
        off = math.radians(a + math.degrees(1.6 / r_txt))          # beside the long tick, counter-clockwise side
        _stamp(labels, m, r_txt * math.cos(off), r_txt * math.sin(off), math.degrees(off), 2)
    # arrow at 0 deg pointing outward, inside the band
    n = round(1.6 / CELL_MM)
    yy, xx = np.mgrid[0:n, 0:n]
    tri = np.abs(xx - n / 2) < (yy + 1) / 2
    _stamp(labels, tri, (SCALE_MM[0] + 1.0) * math.cos(math.radians(-2.2)),
           (SCALE_MM[0] + 1.0) * math.sin(math.radians(-2.2)), -2.2, 2)


def _quoted(text):
    """Quote an argument with commas, which PowerShell would otherwise split."""
    return f'"{text}"' if "," in text else text


def main(out_dir="iso"):
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    labels = np.zeros((SIZE, SIZE), np.uint8)
    for y0 in range(0, SIZE, 500):
        x = c[None, :]
        y = -c[y0:y0 + 500, None]
        r = np.hypot(x, y)
        th = np.arctan2(y, x)
        out = np.zeros(r.shape, np.uint8)
        for k, rc in enumerate(RINGS_MM):
            n = int(2 * math.pi * rc // PITCH_MM)
            step = 2 * math.pi / n
            j = np.round((th - step * 0.5 * (k % 2)) / step)
            a = j * step + step * 0.5 * (k % 2)                    # rosette centre angle
            cx, cy = rc * np.cos(a), rc * np.sin(a)
            # local frame: u along the radius (outward), w along the track (counter-clockwise)
            dx, dy = x - cx, y - cy
            u = dx * np.cos(a) + dy * np.sin(a)
            w = -dx * np.sin(a) + dy * np.cos(a)
            near = np.hypot(u, w) < PETAL_OFF + PETAL_LEN / 2 + 0.2
            for p in range(4):
                phi = math.radians(45 + 90 * p)
                pu, pw = u - PETAL_OFF * math.cos(phi), w - PETAL_OFF * math.sin(phi)
                lu = pu * math.cos(phi) + pw * math.sin(phi)
                lw = -pu * math.sin(phi) + pw * math.cos(phi)
                inside = near & ((lu / (PETAL_LEN / 2)) ** 2 + (lw / (PETAL_W / 2)) ** 2 <= 1)
                out[inside] = PETALS[(p + k) % 4]
            out[near & (np.hypot(u, w) <= CORE_R)] = CENTRE
        # Angle scale (counter-clockwise from +x in the data-side view, as everywhere in discprobe).
        band = (r >= SCALE_MM[0]) & (r <= SCALE_MM[1])
        out[band] = 1
        deg = np.degrees(th) % 360
        d10 = np.abs((deg + 5) % 10 - 5)
        tick_len = np.where(np.abs((deg + 15) % 30 - 15) < 0.5, 1.0, 0.45)
        out[band & (np.radians(d10) * r < 0.09) & (r <= SCALE_MM[0] + tick_len * (SCALE_MM[1] - SCALE_MM[0]))] = 2
        out[(r < R_MIN) | (r > R_MAX)] = 0
        labels[y0:y0 + 500] = out
    _numbers(labels)
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "rosettes_design.npy"), labels)
    colours = np.array([(120, 120, 120), (40, 40, 110), (235, 220, 150), (200, 90, 90), (90, 190, 120), (230, 230, 230)],
                       np.uint8)
    Image.fromarray(colours[labels]).resize((1600, 1600), Image.BOX).save(os.path.join(out_dir, "rosettes_preview.png"))
    Image.fromarray(colours[labels[2300:3700, 4300:5900]]).save(os.path.join(out_dir, "rosettes_zoom.png"))
    print("labels:", " ".join(f"{i}={t}" for i, t in enumerate(TEXTURES)))
    print("The preview colours only tell the textures apart; the colours on the disc depend on the angle.")
    print("Next, with your own geo result (latest, or the path to its summary.json):")
    print("python -m discprobe image --geo latest "
          f"--design-npy {out_dir}/rosettes_design.npy --textures {' '.join(_quoted(t) for t in TEXTURES)} --r-max 57.6 "
          f"--output {out_dir}/rosettes.iso")


if __name__ == "__main__":
    main()
