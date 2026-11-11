"""Reference-EFM half-frame diagnostics; parity/subcode are random placeholders.

No prediction of whole-track periods or the hardware encoder is made.
Run: python -X utf8 tools/check_cd_periods.py <new-output.json>
"""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discprobe import cdimage, efm

rng = np.random.default_rng(8)
report = {"model": "ECMA-130 Annex E reference EFM, random parity/subcode placeholders",
          "hardware_verified": False, "samples_per_texture": 60, "textures": {}}
for texture in ["0D", "AA", "10", "63", "0DAA", "00FF", "1063", "0D10AA"]:
    state, periods = efm.Boundary(), []
    for frame in range(30):
        symbols = rng.integers(0, 256, 33, dtype=np.uint8)
        slots = np.r_[0:12, 16:28]
        symbols[slots + 1] = cdimage.texture_bytes(texture, np.full(24, frame), slots, np.zeros(24, np.uint8))
        levels, state = efm.encode_frame(symbols, state)
        for start in [44, 316]:
            body = levels[start + 17:start + 187]
            periods.append(next((p for p in range(3, 86) if np.array_equal(body[p:], body[:-p])), None))
    report["textures"][texture] = {str(p): periods.count(p) for p in sorted(set(periods), key=lambda x: x or 0)}
with open(sys.argv[1], "x", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report, indent=2))
