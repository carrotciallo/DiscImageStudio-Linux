"""The opening screen of `guide`: a small disc catching the light.

The disc is built from coloured spaces, with slashes and a few symbols on top: two rainbow wedges
sweep round like the light on a real disc, a streak of / and \\ marks their centre, and small
sparks flash where they pass. A frame is built off screen and sent in one write, and the frame
shown follows the clock, so a slow terminal skips frames instead of running long. It falls back
step by step: true colour, 16 colours, then plain ASCII, which still turns unless motion is off.
A window too small for the disc gets the title alone. Only `guide` shows it, never a measuring command.
"""

from __future__ import annotations

import colorsys
import math
import shutil
import sys
import time

from . import i18n, ui

DISC_W, DISC_H = 25, 11
HOLE, HUB, RIM = 0.14, 0.27, 0.95
SHOW_S = 1.0
FRAME_S = 0.04
STILL_ANGLE = 0.7
TITLE = (r"     _ _                                _",
         r"  __| (_)___  ___       _ __  _ __ ___ | |__   ___",
         r" / _` | / __|/ __|_____| '_ \| '__/ _ \| '_ \ / _ \ ",
         r"| (_| | \__ \ (_|_____| |_) | | | (_) | |_) |  __/",
         r" \__,_|_|___/\___|    | .__/|_|  \___/|_.__/ \___|",
         r"                      |_|")
TAGLINE = "read timing -> disc geometry -> pictures on discs"
TITLE_W = max(len(line) for line in TITLE)
GAP = 2
ANSI16_BG = ("41", "43", "42", "46", "44", "45")   # a rainbow in six steps
SPARKS = "*+."


def _streak(theta: float) -> str:
    """The glyph running outward along this direction; y grows downward on screen."""
    step = int(((theta % math.pi) + math.pi / 8) / (math.pi / 4)) % 4
    return ("-", "\\", "|", "/")[step]


def _cell(x: float, y: float, angle: float):
    """(glyph, hue, light, part) of one character cell, or None outside the disc and in its hole."""
    radius = math.hypot(x, y)
    if radius > 1 or radius < HOLE:
        return None
    if radius < HUB:
        return " ", 0.0, 0.0, "hub"
    theta = math.atan2(y, x)
    light = abs(math.cos(theta - angle)) ** 10
    hue = (radius * 1.4 + theta / math.tau) % 1.0
    if radius > RIM:
        return " ", hue, max(light, 0.25), "rim"
    glyph = " "
    if light > 0.72:
        glyph = _streak(theta)
    elif light > 0.25 and (int(radius * 47) * 7 + int((theta + math.pi) * 13)) % 11 == 0:
        glyph = SPARKS[int(radius * 17) % len(SPARKS)]
    return glyph, hue, light, "body"


def _paint(glyph: str, hue: float, light: float, part: str, t: ui.Term) -> str:
    if not t.color:
        if part == "hub":
            return "."
        if part == "rim":
            return "o"
        return glyph if glyph != " " else ":"
    if t.truecolor:
        if part == "hub":
            r, g, b = 70, 74, 84
        else:
            r, g, b = (int(255 * v) for v in colorsys.hsv_to_rgb(hue, 0.25 + 0.65 * light, 0.3 + 0.65 * light))
        return f"\x1b[48;2;{r};{g};{b};97m{glyph}\x1b[0m"
    if part == "hub" or light < 0.2:
        return f"\x1b[100;97m{glyph}\x1b[0m"
    return f"\x1b[{ANSI16_BG[int(hue * len(ANSI16_BG)) % len(ANSI16_BG)]};97m{glyph}\x1b[0m"


def disc_rows(angle: float, t: ui.Term) -> list[str]:
    rows = []
    for row in range(DISC_H):
        y = (row - (DISC_H - 1) / 2) / (DISC_H / 2)
        out = []
        for col in range(DISC_W):
            cell = _cell((col - (DISC_W - 1) / 2) / (DISC_W / 2), y, angle)
            out.append(" " if cell is None else _paint(*cell, t))
        rows.append("".join(out))
    return rows


def _title_rows(t: ui.Term, height: int, now: float | None) -> list[str]:
    def paint(line):
        return t.style(line, "cyan") if now is None else ui.sweep(line, now, t, "cyan")
    lines = [paint(line.ljust(TITLE_W)) for line in TITLE] + [t.style(i18n.pad(i18n.tr(TAGLINE), TITLE_W), "dim")]
    top = max(0, (height - len(lines)) // 2)
    blank = " " * TITLE_W
    return ([blank] * top + lines + [blank] * height)[:height]


def frame(angle: float, t: ui.Term, columns: int, now: float | None = None) -> list[str]:
    """The screen for one angle, shaped to the terminal width."""
    if columns > DISC_W + GAP + TITLE_W:
        return [d + " " * GAP + title for d, title in zip(disc_rows(angle, t), _title_rows(t, DISC_H, now))]
    tagline = i18n.tr(TAGLINE)
    if columns > TITLE_W:
        return [t.style(line, "cyan") for line in TITLE] + [t.style(tagline, "dim")]
    return [t.style("disc-probe", "cyan"), t.style(i18n.fit(tagline, max(columns - 1, 10)), "dim")]


def show(t: ui.Term | None = None, pause=time.sleep, now=time.monotonic) -> None:
    """Draw the opening screen. Only at a terminal; only moves if the terminal can."""
    t = t or ui.term()
    if not t.interactive:
        return
    size = shutil.get_terminal_size((80, 24))
    write = t.stream.write
    roomy = size.columns > DISC_W + GAP + TITLE_W and size.lines > DISC_H + 2
    if not roomy and size.columns > DISC_W + GAP + TITLE_W:     # too low for the disc: the title alone
        write("\n".join(frame(STILL_ANGLE, t, DISC_W + GAP + TITLE_W)) + "\n\n")
        t.stream.flush()
        return
    if t.animate and roomy:
        write("\x1b[?25l")
        try:
            write("\n" * (DISC_H - 1))
            start = now()
            while True:
                spent = now() - start
                eased = 1 - (1 - min(spent / SHOW_S, 1.0)) ** 2     # sweeps fast, settles soft
                angle = STILL_ANGLE + math.pi * (eased - 1)
                settled = spent >= SHOW_S
                write(f"\r\x1b[{DISC_H - 1}A" + "\n".join(frame(angle, t, size.columns, None if settled else spent)))
                t.stream.flush()
                if settled:
                    break
                pause(FRAME_S)
        except KeyboardInterrupt:
            pass        # Ctrl+C only skips the show
        finally:
            write("\x1b[?25h\n\n")
            t.stream.flush()
        return
    write("\n".join(frame(STILL_ANGLE, t, size.columns)) + "\n\n")
    t.stream.flush()


if __name__ == "__main__":
    show(ui.Term(sys.stdout))
