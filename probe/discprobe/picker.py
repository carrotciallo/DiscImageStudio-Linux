"""Choose a past geo result: first by disc and drive, then by precision or date.

`results --pick` and `--geo pick` open it. It only reads the results folder and never touches a drive.
At a terminal it follows the keys, without keys it asks for a number, and in a pipe `results --pick` prints the
same lists, so a script sees what a person would.
"""

from __future__ import annotations

import shutil
import time

from . import guide, i18n, snake, ui
from .i18n import tr

SORTS = ("precision", "date")
POLL_S = 0.03


class Group:
    def __init__(self, disc: str, drive: str, media: str, inferred: bool):
        self.disc, self.drive, self.media, self.inferred = disc, drive, media, inferred
        self.runs: list = []

    def best(self):
        sigmas = [r.sigma for r in self.runs if r.sigma is not None and r.geo_complete()]
        return min(sigmas) if sigmas else None

    def latest(self):
        return max(r.when for r in self.runs)


def geo_runs(media: str | None = None, out: str = "results") -> list:
    """Measurements of real discs that reached a fit."""
    return [r for r in guide.scan(out) if r.kind == "geo" and not r.simulated and "u" in r.fit and (media is None or r.media == media)]


def groups(runs: list, out: str = "results") -> list[Group]:
    """One group per disc and drive, the most recently measured first."""
    infos = guide.info_runs(out)
    found: dict = {}
    for r in runs:
        who = guide.identity_of(r, infos)
        key = (who["disc"], who["drive"], r.media)
        if key not in found:
            found[key] = Group(who["disc"], who["drive"], r.media, who["inferred"])
        found[key].inferred = found[key].inferred and who["inferred"]
        found[key].runs.append(r)
    return sorted(found.values(), key=Group.latest, reverse=True)


def sort_runs(runs: list, key: str = "precision", reverse: bool = False) -> list:
    """Best or newest first; `reverse` turns that round. Runs stopped early always go last, as they can't be compared."""
    if key == "date":
        ordered = sorted(runs, key=lambda r: r.when, reverse=not reverse)
    else:
        ordered = sorted(runs, key=lambda r: (r.sigma is None, r.sigma or 0.0, -r.when.timestamp()), reverse=False)
        if reverse:
            ordered.reverse()
    return [r for r in ordered if r.geo_complete()] + [r for r in ordered if not r.geo_complete()]


def _degrees(value) -> str:
    return "?" if value is None else f"+/-{value:.2f} deg"


def group_row(g: Group) -> str:
    mark = "~" if g.inferred else " "
    runs = f"{len(g.runs)} " + tr("runs")
    return (f"{mark}{i18n.pad(i18n.fit(g.disc, 22), 22)}  {i18n.pad(i18n.fit(g.drive, 28), 28)}  {g.media.upper():3s}  "
            f"{i18n.pad(runs, 8)}  {tr('best')} {i18n.pad(_degrees(g.best()), 14)}  {g.latest():%Y-%m-%d}")


def run_row(r) -> str:
    span = r.fit.get("measured_span_mm") or ["?", "?"]
    speed = (r.summary.get("set_cd_speed") or {}).get("requested_kBps")
    return (f"{r.when:%Y-%m-%d %H:%M}  {i18n.pad(_degrees(r.sigma), 14)}  rms {r.fit.get('residual_rms_deg', 0):5.2f} deg  "
            f"{span[0]}-{span[1]} mm  {r.rungs():2d} {i18n.pad(tr('points'), 6)}  "
            f"{i18n.pad(str(speed) if speed else tr('default'), 7)}  {tr(r.quality())}")


def sort_title(key: str, reverse: bool) -> str:
    if key == "date":
        return tr("oldest first") if reverse else tr("newest first")
    return tr("least precise first") if reverse else tr("most precise first")


def plain_lists(found: list[Group], key: str = "precision", reverse: bool = False) -> list[str]:
    lines = []
    for g in found:
        lines.append(group_row(g).rstrip())
        for r in sort_runs(g.runs, key, reverse):
            lines += ["  " + run_row(r), "    " + r.path]
        lines.append("")
    if any(g.inferred for g in found):
        lines.append(tr(INFERRED))
    return lines


INFERRED = "~ matched from an info run near the same time, as older results didn't record the disc"


class Picker:
    """What is on screen and what each key does, with no terminal in it."""

    def __init__(self, found: list[Group], key: str = "precision", reverse: bool = False):
        self.found, self.key, self.reverse = found, key, reverse
        self.group = found[0] if len(found) == 1 else None      # one disc has nothing to choose between
        self.row, self.result, self.done = 0, None, False

    def _runs(self) -> list:
        return sort_runs(self.group.runs, self.key, self.reverse)

    def handle(self, key: str) -> None:
        count = len(self._runs()) if self.group else len(self.found)
        if key in ("up", "k"):
            self.row = (self.row - 1) % count
        elif key in ("down", "j"):
            self.row = (self.row + 1) % count
        elif key in ("q", "Q", "\x1b", "\x03"):
            self.done = True
        elif self.group is None:
            if key in ("\r", "\n", "right"):
                self.group, self.row = self.found[self.row], 0
        elif key in ("\r", "\n"):
            self.result, self.done = self._runs()[self.row], True
        elif key in ("s", "S"):
            self.key, self.reverse, self.row = SORTS[(SORTS.index(self.key) + 1) % len(SORTS)], False, 0
        elif key in ("r", "R"):
            self.reverse, self.row = not self.reverse, 0
        elif key in ("left", "\x08", "\x7f"):
            if len(self.found) == 1:
                self.done = True
            else:
                self.row = self.found.index(self.group)
                self.group = None

    def lines(self, height: int) -> list[str]:
        if self.group is None:
            head = [tr("Choose a disc (arrows move, Enter opens, q quits)"), ""]
            rows = [group_row(g) for g in self.found]
            foot = [tr(INFERRED)] if any(g.inferred for g in self.found) else []
        else:
            head = [group_row(self.group).strip(), f"{sort_title(self.key, self.reverse)}  " + tr("(s sort, r reverse, Enter chooses, left goes back, q quits)"), ""]
            rows = [run_row(r) for r in self._runs()]
            foot = []
        room = max(1, height - len(head) - len(foot) - 1)
        top = max(0, min(self.row - room // 2, len(rows) - room))
        shown = [("> " if i == self.row else "  ") + rows[i] for i in range(top, min(top + room, len(rows)))]
        return head + shown + foot


def _draw(p: Picker, t: ui.Term) -> None:
    size = shutil.get_terminal_size((100, 24))
    width = max(10, size.columns - 1)
    out = []
    for line in p.lines(size.lines):
        line = i18n.fit(line, width)
        out.append(t.style(line, "bold") if line.startswith("> ") else line)
    t.stream.write("\x1b[H\x1b[J" + "\n".join(out))
    t.stream.flush()


def _by_keys(p: Picker, t: ui.Term, keys, pause) -> None:
    t.stream.write("\x1b[?1049h\x1b[?25l")      # its own screen, so the commands above are still there afterwards
    try:
        _draw(p, t)
        while not p.done:
            pressed = keys.read()
            for key in pressed:
                p.handle(key)
            if pressed and not p.done:
                _draw(p, t)
            pause(POLL_S)
    finally:
        t.stream.write("\x1b[?25h\x1b[?1049l")
        t.stream.flush()
        keys.close()


def _by_number(p: Picker) -> None:
    """Where keys can't be polled: type a number."""
    if p.group is None:
        for i, g in enumerate(p.found, 1):
            print(f"{i:3d} {group_row(g)}")
        p.group = _answer(p.found)
        if p.group is None:
            p.done = True
            return
    runs = sort_runs(p.group.runs, p.key, p.reverse)
    for i, r in enumerate(runs, 1):
        print(f"{i:3d}  {run_row(r)}")
    p.result, p.done = _answer(runs), True


def _answer(items: list):
    text = input(tr("Which number? Enter alone cancels: ")).strip()
    return items[int(text) - 1] if text.isdigit() and 1 <= int(text) <= len(items) else None


def choose(media: str | None = None, out: str = "results", key: str = "precision", reverse: bool = False, t: ui.Term | None = None, keys=None, pause=time.sleep):
    """The chosen result, or None if nothing was chosen. Raises ValueError where nobody can answer."""
    t = t or ui.term()
    found = groups(geo_runs(media, out), out)
    if not found:
        raise ValueError(f"There are no geo results to choose from in {out}. Run geo first.")
    if not t.can_prompt():
        raise ValueError("--geo pick needs a terminal. Give a result's folder, or see them with: results --pick")
    p = Picker(found, key, reverse)
    keys = keys or (snake.open_keys() if t.ansi else None)
    if keys:
        _by_keys(p, t, keys, pause)
    else:
        _by_number(p)
    return p.result
