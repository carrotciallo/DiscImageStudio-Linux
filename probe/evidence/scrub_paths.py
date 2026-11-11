"""Replace absolute local paths in the evidence JSON files with bare file names."""

import glob
import json
import os
import re

DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def scrub(v):
    if isinstance(v, str) and (DRIVE_PATH.match(v) or "Administrator" in v or "ADMINI~1" in v):
        return os.path.basename(v.replace("\\", "/"))
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items()}
    return v


here = os.path.dirname(os.path.abspath(__file__))
changed = 0
for p in glob.glob(os.path.join(here, "**", "*.json"), recursive=True):
    if "blind" in p.lower():
        continue
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    s = scrub(d)
    if s != d:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        changed += 1
leftover = []
for p in glob.glob(os.path.join(here, "**", "*.*"), recursive=True):
    if "blind" in p.lower() or p.endswith((".py", ".png", ".jpg")):
        continue
    with open(p, encoding="utf-8", errors="ignore") as f:
        if re.search(r"Administrator|ADMINI~1|[A-Za-z]:[\\/]", f.read()):
            leftover.append(os.path.relpath(p, here))
print(f"scrubbed {changed} files; still containing local paths: {leftover}")
