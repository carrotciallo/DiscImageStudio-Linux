# usage: make_figures.py PHOTO LINES.csv OUTDIR  (the photo itself is not kept here)
import sys, csv, numpy as np
from PIL import Image, ImageDraw
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
photo, lines, out = sys.argv[1:4]
rows = list(csv.DictReader(open(lines)))
L = {i: [r for r in rows if int(r['line']) == i] for i in (1, 2, 3, 4)}
INK, MUTED, GRID, LINE = '#2b2b2b', '#6b6b6b', '#e4e4e4', '#2f6db5'
# 1. the photo, disc only, with the fitted centre of each traced point
im = Image.open(photo).convert('RGB'); cx, cy, R = 2226, 1633, 1345
mask = Image.new('L', im.size, 0); ImageDraw.Draw(mask).ellipse((cx - R, cy - R, cx + R, cy + R), fill=255)
disc = Image.composite(im, Image.new('RGB', im.size, (255, 255, 255)), mask).crop((cx - R, cy - R, cx + R, cy + R))
d = ImageDraw.Draw(disc)
for i, rs in L.items():
    for r in rs:
        if int(r['used']):
            x, y = float(r['x_px']) - (cx - R), float(r['y_px']) - (cy - R)
            d.ellipse((x - 9, y - 9, x + 9, y + 9), outline=(255, 255, 255), width=4)
disc.resize((1100, 1100), Image.LANCZOS).save(out + '/traced_lines.jpg', quality=88)
# 2. deviation from a straight line, one panel per half line, on one scale
fig, ax = plt.subplots(1, 4, figsize=(11, 2.9), sharey=True, sharex=True, dpi=130)
for a, (i, rs) in zip(ax, L.items()):
    r = np.array([float(x['r_mm']) for x in rs if int(x['used'])]); dv = np.array([float(x['deviation_mm']) for x in rs if int(x['used'])])
    o = np.argsort(r); a.axhline(0, color=MUTED, lw=0.8); a.plot(r[o], dv[o], color=LINE, lw=2)
    a.set_title(f'Half line {i}: rms {dv.std():.3f} mm', fontsize=10, color=INK, loc='left')
    a.set_xlim(25, 58); a.set_ylim(-0.25, 0.25); a.grid(axis='y', color=GRID, lw=0.8); a.tick_params(colors=MUTED, labelsize=9, length=0)
    a.set_xlabel('radius (mm)', fontsize=9, color=MUTED)
    for s in ('top', 'right', 'left'): a.spines[s].set_visible(False)
    a.spines['bottom'].set_color(GRID)
ax[0].set_ylabel('deviation (mm)', fontsize=9, color=MUTED)
fig.tight_layout(); fig.savefig(out + '/deviation.png')
