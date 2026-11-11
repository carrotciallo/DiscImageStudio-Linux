"""Self-test of the terminal layer: when it switches on, that it leaves measurements alone, and its advice."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from . import filldisc, guide, i18n, snake, timing, ui
from .sim import SimDrive


class FakeTty(io.StringIO):
    def isatty(self):
        return True

    def fileno(self):
        raise ValueError("not a real console")


class Utf8Tty(FakeTty):
    encoding = "utf-8"


class Keys:
    """Pressed keys for the game, one list per poll."""

    def __init__(self, *polls):
        self.polls = list(polls)
        self.closed = False

    def read(self):
        return self.polls.pop(0) if self.polls else []

    def close(self):
        self.closed = True


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LONG_ENGLISH = re.compile(r"[A-Za-z]{3,}(?: [A-Za-z]{2,}){3,}")


def _term_matrix(c) -> None:
    pipe = ui.Term(io.StringIO(), env={"TERM": "xterm"}, platform="linux")
    c.check(not (pipe.interactive or pipe.ansi or pipe.color or pipe.animate), "a pipe gets nothing extra")
    tty = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    c.check(tty.interactive and tty.ansi and tty.color and tty.animate, "a terminal gets colour and animation")
    no_color = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux")
    c.check(no_color.interactive and not no_color.color and no_color.animate, "NO_COLOR drops colour only")
    c.check(not ui.Term(FakeTty(), env={"TERM": "dumb"}, platform="linux").interactive, "TERM=dumb counts as a pipe")
    c.check(not ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_PLAIN": "1"}, platform="linux").interactive,
            "DISCPROBE_PLAIN=1 counts as a pipe")
    old = ui.Term(FakeTty(), env={}, platform="win32")      # GetConsoleMode cannot work on this stream
    c.check(old.interactive and not old.ansi and not old.color and not old.animate, "a console without ANSI falls back to plain text")
    still = ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
    c.check(still.color and not still.animate, "DISCPROBE_NO_ANIMATION=1 keeps colour, drops motion")
    c.check(not ui.Term(Utf8Tty(), env={"TERM": "xterm"}, platform="linux").unicode, "ASCII by default, even on UTF-8")
    c.check(ui.Term(Utf8Tty(), env={"TERM": "xterm", "DISCPROBE_UNICODE": "1"}, platform="linux").unicode, "DISCPROBE_UNICODE=1 asks for finer glyphs")
    c.check(not ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_UNICODE": "1"}, platform="linux").unicode, "finer glyphs need UTF-8")


def _progress_line(c) -> None:
    status = lambda: (0.25, "rung 6/22", 40.0)
    for name, env, wants_escape, wants_spinner in (
            ("colour", {"TERM": "xterm"}, True, True), ("NO_COLOR", {"TERM": "xterm", "NO_COLOR": "1"}, True, False)):
        s = FakeTty()
        p = ui.Progress(status, ui.Term(s, env=env, platform="linux"))
        p.tick(force=True)
        p.log("a line")
        p.close()
        text = s.getvalue()
        shown = ANSI.sub("", text)
        c.check("rung 6/22" in shown and "0:40 left" in shown and "a line\n" in shown, f"{name}: progress line and log line")
        c.check(("\x1b[36m" in text) == wants_spinner, f"{name}: colour {'on' if wants_spinner else 'off'}")
        c.check(any(f in shown for f in ui.SPINNER_ASCII), f"{name}: the spinner turns")
        c.check(not wants_escape or text.endswith("\x1b[?25h"), f"{name}: the cursor comes back")
    s = FakeTty()
    p = ui.Progress(status, ui.Term(s, env={}, platform="win32"))
    p.tick(force=True)
    p.close()
    c.check("\x1b" not in s.getvalue() and "rung 6/22" in s.getvalue() and s.getvalue().isascii(),
            "no ANSI: plain ASCII with carriage returns only")


def _layout(c) -> None:
    status = lambda: (0.25, "rotation test, zone 2/3", 40.0)
    tty = ui.Term(FakeTty(), env={"TERM": "xterm", "COLORTERM": "truecolor"}, platform="linux")
    plain = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux")
    for lang in ("en", "zh"):
        i18n.use(lang)
        try:
            for t in (tty, plain):
                p = ui.Progress(status, t, keys=Keys())
                for columns in (200, 100, 80, 60, 40, 24, 12):
                    line, width = p._render(columns)
                    shown = ANSI.sub("", line)
                    c.check(i18n.display_width(shown) == width <= max(10, columns - 1), f"{lang}, {columns} columns: the line fits ({width})")
                wide, narrow = ANSI.sub("", p._render(200)[0]), ANSI.sub("", p._render(40)[0])
                c.check(i18n.tr("Ctrl+C to stop") in wide and i18n.tr("g: game") in wide, f"{lang}: a wide line offers stop and the games")
                c.check("[" not in narrow and "25%" in narrow, f"{lang}: a narrow line drops the bar, keeps the percentage")
                p.keys = None
                p.close()
        finally:
            i18n.use("en")
    p = ui.Progress(status, tty)
    p.started = 100.0
    c.check(p._spinner(100.13) == p._spinner(100.13) == ui.SPINNER_ASCII[1], "the spinner follows the clock, not the draws")
    p.close()
    painted = ui.sweep("reading the disc", 0.8, tty)
    c.check("38;2;" in painted and ANSI.sub("", painted) == "reading the disc", "the light sweep only adds colour")
    sixteen = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    c.check("1;36" in ui.sweep("reading the disc", 0.8, sixteen), "16 colours: the sweep is a bold band")
    c.check(ui.sweep("reading the disc", 0.8, plain) == "reading the disc", "no colour: plain text")
    still = ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
    c.check(ui.sweep("reading the disc", 0.8, still) == "reading the disc", "no motion: still text")
    p = ui.Progress(status, still)
    c.check(not any(f in ANSI.sub("", p._render(100)[0]) for f in ui.SPINNER_ASCII), "no motion: no spinner, the numbers stay")
    s = FakeTty()
    p = ui.Progress(lambda: (0.5, "same", None), ui.Term(s, env={"TERM": "xterm", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux"))
    p.tick(force=True)
    size = len(s.getvalue())
    p.tick(force=True)
    c.check(len(s.getvalue()) == size, "an unchanged frame is not written again")
    p.close()
    level = [0.25]
    for term_used, flashes, name in ((sixteen, True, "colour"), (plain, False, "NO_COLOR"), (still, False, "no motion")):
        level[0] = 0.25
        p = ui.Progress(lambda: (level[0], "rung 3/22", None), term_used)
        c.check("\x1b[" not in p._percent(0.25, 1000.0)[1], f"{name}: the first percentage does not flash")
        level[0] = 0.26
        c.check((" 2\x1b[1;36m6\x1b[0m%" in p._render(100)[0]) == flashes, f"{name}: {'only the digit that changed flashes' if flashes else 'a new digit stays plain'}")
        p.percent_changed -= ui.PERCENT_FLASH_S
        c.check(" 26%" in p._render(100)[0], f"{name}: it goes back to the terminal's colour")
        level[0] = 0.30
        c.check(("\x1b[1;36m30\x1b[0m%" in p._render(100)[0]) == flashes, f"{name}: two digits that change both flash")
        level[0] = 0.996
        c.check(" 99%" in ANSI.sub("", p._render(100)[0]), f"{name}: 99.6% does not read as done")
        level[0] = 1.0
        full = p._render(100)[0]
        c.check(("\x1b[32m100%\x1b[0m" in full) == (term_used is not plain), f"{name}: 100% is green where there is colour")
        p.percent_changed -= ui.PERCENT_FLASH_S
        c.check(("\x1b[32m100%" in p._render(100)[0]) == (term_used is not plain), f"{name}: and stays green")
        p.close()
    for env, wanted in (({}, "32"), ({"COLORFGBG": "15;0"}, "92"), ({"COLORFGBG": "0;15"}, "32"), ({"COLORFGBG": "0;default;7"}, "32"), ({"COLORFGBG": "bad"}, "32")):
        c.check(ui.Term(FakeTty(), env={"TERM": "xterm", **env}, platform="linux").green == wanted, f"green for {env}: {wanted}")
    frame_bytes = len(ui.Progress(status, tty)._render(100)[0].encode())
    c.check(frame_bytes < 420, f"a true-colour frame stays small ({frame_bytes} bytes)")


def _fill_disc(c) -> None:
    import random

    def game(shape):
        g = filldisc.FillDisc(12, 8, rng=random.Random(1))
        g.shape = shape
        g.x, g.y = g.cols - 1 - max(x for x, _ in shape), 2
        return g
    bar = filldisc.SHAPES[3]
    g = game(bar)
    x = g.x
    g.step()
    c.check(g.x == x - 1 and not g.burned, "a block moves left at each step")
    g.turn("up")
    g.turn("up")
    g.turn("up")
    c.check(g.y == 0, "up moves it, and the edge stops it")
    g.turn("right")
    c.check({(x, y) for x, y in g.shape} == {(i, 0) for i in range(4)}, "right spins it")
    g = game(bar)
    g.turn("right")
    c.check(g._fits(g._cells()) and g.x + 3 == g.cols - 1, "a block spun at the edge is nudged back inside")
    g = game(bar)
    while not g.burned:
        g.turn("left")
    c.check({(0, y) for y in range(2, 6)} == set(g.burned) and g.x >= g.cols - 2, "at the left it lands, and the next block comes in on the right")
    g = game(bar)
    g.burned = dict.fromkeys([(0, 0), (0, 1), (0, 6), (0, 7), (1, 0)], "block1") | {(3, 0): "block2"}
    while not g.score:
        g.turn("left")
    c.check(g.score == 1 and g.best == 1 and g.burned == {(0, 0): "block1", (2, 0): "block2"}, "a full column clears, scores, and what was right of it moves left, colours and all")
    g = game(bar)
    g.burned = dict.fromkeys([(g.cols - 2, y) for y in range(7)], "block0")
    g.best = 4
    g.step()
    c.check(g.over and g.best == 4, "a stack that reaches the right edge ends the game")
    best = g.best
    c.check(g.step() == [] and g.turn("left") == [], "a finished game does not move")
    c.check(sum(g.cell(x, y) != "field" for x in range(g.cols) for y in range(8)) == len(g.burned), "a finished game shows only what landed")
    g.reset()
    c.check(not g.over and g.score == 0 and g.best == best and not g.burned, "a new game starts clean and keeps the best score")
    g = filldisc.FillDisc(14, 8, rng=random.Random(3))
    kinds = [g.kind]
    for _ in range(40):
        kind = g.kind
        while g.kind == kind:
            g.turn("left")
        g.burned.clear()
        kinds.append(g.kind)
    c.check(all(a != b for a, b in zip(kinds, kinds[1:])) and set(kinds) == set(filldisc.BLOCK_KINDS), "every block gets a colour, never the same as the last one")
    c.check(all(k in ui.GAME_CELLS and k in ui.GAME_GLYPHS for k in filldisc.BLOCK_KINDS), "every colour can be drawn, with and without colour")
    g = filldisc.FillDisc(14, 8, rng=random.Random(7))
    moves = random.Random(9)
    drawn = {(x, y): g.cell(x, y) for x in range(14) for y in range(8)}
    played = 0
    while not g.over and played < 4000:
        changed = g.turn(moves.choice(("up", "down", "left", "right"))) if played % 3 else g.step()
        drawn.update({(x, y): kind for x, y, kind in changed})
        played += 1
        if drawn != {(x, y): g.cell(x, y) for x in range(14) for y in range(8)}:
            break
    c.check(drawn == {(x, y): g.cell(x, y) for x in range(14) for y in range(8)} and played > 50, "drawing only the changed cells always gives the true board")
    c.check(filldisc.FillDisc().step_s == filldisc.SLOWEST_STEP_S, "the first blocks are slow")
    fast = filldisc.FillDisc()
    fast.score = 1000
    c.check(fast.step_s == filldisc.FASTEST_STEP_S, "it speeds up with the score, to a limit")


def _snake(c) -> None:
    import random as shared_random
    before = shared_random.getstate()
    g = snake.Snake(10, 6)
    g.food = (5, g.body[0][1])
    head, length = g.body[0], len(g.body)
    g.step()
    c.check(g.body[0] == (head[0] + 1, head[1]) and len(g.body) == length and not g.over, "the snake moves")
    g.turn("left")
    c.check(not g.queued, "the snake cannot reverse into itself")
    g.step()
    c.check(g.score == 1 and len(g.body) == length + 1 and g.food not in g.body, "eating grows it and places new food")
    g.turn("up")
    g.turn("left")
    g.step()
    g.step()
    c.check(g.heading == (-1, 0), "two quick turns are both kept")
    for _ in range(20):
        g.step()
    best = g.score      # it may have eaten again on the way to the wall
    c.check(g.over and best >= 1 and g.best == best, "a wall ends the game and keeps the best score")
    g.reset()
    c.check(not g.over and g.score == 0 and g.best == best, "a new game starts clean")
    g = snake.Snake(10, 6)
    g.body = [(5, 2), (4, 2), (4, 3), (5, 3), (6, 3), (6, 2)]
    g.heading = (0, 1)
    g.step()
    c.check(g.over, "biting itself ends the game")
    _fill_disc(c)
    c.check(shared_random.getstate() == before, "the games leave the shared random generator alone")
    c.check(snake.parse_posix("\x1b[Ag\x1bOB") == ["up", "g", "down"], "arrow keys from a POSIX terminal")

    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="80", LINES="24")
    try:
        s = FakeTty()
        keys = Keys(["x"], ["g"], ["d"], [], ["q"], ["g"])
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=keys)
        p.play()
        c.check(not p.playing, "no game until g is pressed")
        p.play()
        c.check(p.playing and "best 0" in s.getvalue(), "g opens the game below the progress line")
        p.last_step = 0.0
        p.play()
        c.check(p.game.heading == (1, 0) and p.game.body[0][0] == 4, "the game steps during a pause")
        p.log("a measured line")
        text = s.getvalue()
        c.check("a measured line\n" in text and text.rindex("a measured line") < text.rindex("best 0"),
                "a log line prints above the game, and the game is redrawn under it")
        p.play()
        p.play()
        c.check(not p.playing, "q closes the game")
        p.play()
        c.check(p.playing, "g opens it again")
        p.close()
        tail = s.getvalue()
        c.check(keys.closed and tail.endswith("\x1b[?25h") or tail.rstrip().endswith("\x1b[?25h"), "closing restores keys and cursor")
        s = FakeTty()
        keys = Keys(["g"], [])
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=keys)
        p.play()
        os.environ.update(COLUMNS="44")
        p.play()
        c.check(p.playing and p.game.cols == 20, "a resized window redraws the game to fit")
        os.environ.update(COLUMNS="20")
        keys.polls = [[]]
        p.play()
        c.check(not p.playing and "too small" in s.getvalue(), "a window too small after resizing closes the game")
        p.close()
        os.environ.update(COLUMNS="80")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux"), keys=Keys(["g"]))
        p.play()
        c.check(p.playing and "##" in s.getvalue() and not re.search(r"\x1b\[[0-9;]*m", s.getvalue()), "NO_COLOR: the game is drawn with glyphs")
        p.close()
        os.environ.update(LINES="6")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=Keys(["g"]))
        p.play()
        c.check(not p.playing and "too small" in s.getvalue(), "a low window says so instead of drawing over text")
        p.close()
        os.environ.update(LINES="24")
        s = FakeTty()
        keys = Keys(["g"], ["n"], ["up"], ["n"], ["n"])
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=keys)
        p.play()
        snake_game = p.game
        snake_game.best = 7
        p.play()
        c.check(p.playing and isinstance(p.game, filldisc.FillDisc) and "Fill the Disc 0" in s.getvalue(), "n changes to the other game")
        y = p.game.y
        before = s.getvalue()
        p.play()
        c.check(p.game.y == y - 1 and len(s.getvalue()) > len(before), "a key moves the block at once, not at the next step")
        filled = p.game
        filled.best = 3
        p.play()
        c.check(p.game is snake_game, "n changes back, and each game keeps its board")
        p.play()
        c.check(p.game is filled, "and again")
        p.close()
        c.check("Snake: best score 7" in s.getvalue() and "Fill the Disc: best score 3" in s.getvalue(), "both best scores are printed at the end, for the log")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux"), keys=Keys(["g"], ["n"]))
        p.play()
        p.play()
        c.check(ui.GAME_GLYPHS[p.game.kind] in s.getvalue() and not re.search(r"\x1b\[[0-9;]*m", s.getvalue()), "NO_COLOR: Fill the Disc is drawn with glyphs")
        p.close()
        os.environ.update(COLUMNS="30")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=Keys(["g"]))
        p.play()
        c.check(p.playing and "closes" not in s.getvalue() and "Snake 0" in s.getvalue(), "a narrow window cuts the hint and never wraps it")
        p.close()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _chinese(c) -> None:
    from . import __main__ as cli, zh
    yes, no = (lambda: True), (lambda: False)
    term_env = {"TERM": "xterm"}
    for flag, tty, env, encodable, system, wanted, name in (
            ("zh", False, {}, True, no, "zh", "--lang zh works in a pipe"),
            ("en", True, {"DISCPROBE_LANG": "zh"}, True, yes, "en", "--lang en beats everything"),
            (None, False, {"DISCPROBE_LANG": "zh"}, True, yes, "en", "a pipe ignores DISCPROBE_LANG and the system"),
            (None, True, {"DISCPROBE_LANG": "zh"}, True, no, "zh", "DISCPROBE_LANG=zh at a terminal"),
            (None, True, {"DISCPROBE_LANG": "en"}, True, yes, "en", "DISCPROBE_LANG=en at a terminal"),
            (None, True, term_env, True, yes, "zh", "a Chinese system gets Chinese"),
            (None, True, term_env, True, no, "en", "other systems get English"),
            (None, True, term_env, False, yes, "en", "a code page without Chinese gets English"),
            (None, True, {"TERM": "linux"}, True, yes, "en", "the Linux console has no Chinese font")):
        c.check(i18n.decide(flag, tty, env, encodable, system) == wanted, name)
    for env, wanted in (({"LANG": "zh_CN.UTF-8"}, True), ({"LANG": "zh_TW.UTF-8"}, True), ({"LANG": "en_US.UTF-8"}, False),
                        ({"LANG": "C"}, False), ({"LC_ALL": "en_GB.UTF-8", "LANG": "zh_CN.UTF-8"}, False)):
        c.check(i18n.system_is_chinese(env, "linux") == wanted, f"system language from {env}")
    c.check(i18n.take_flag(["timing", "--lang", "zh", "--sim", "cav"]) == ("zh", ["timing", "--sim", "cav"]), "--lang can sit anywhere")
    c.check(i18n.take_flag(["--lang=EN", "list"]) == ("en", ["list"]) and i18n.take_flag(["list"]) == (None, ["list"]), "--lang=en, and none")
    try:
        i18n.take_flag(["--lang", "fr"])
        c.check(False, "an unknown language is refused")
    except ValueError as e:
        c.check("zh or en" in str(e), "an unknown language is refused")

    placeholder = re.compile(r"\{(\w+)\}")
    bad = [k for k, v in zh.TEXT.items() if not set(placeholder.findall(v)) <= set(placeholder.findall(k))]
    c.check(not bad, f"every Chinese placeholder exists in its English key {bad[:2]}")
    loose = [k for k in zh.TEXT if "{" in k and len(placeholder.sub("", k).strip()) < 3]
    c.check(not loose, f"no key is so loose that it matches anything {loose[:2]}")
    c.check(i18n.tr("Rotation: CAV") == "Rotation: CAV", "English: lookups do nothing")
    c.check(sys.stdout.__class__.__name__ != "_Lines", "English: the output streams are untouched")
    i18n.use("zh")
    try:
        c.check(i18n.tr("Rotation: CAV") == "转速方式：恒定转速 (CAV)", "values are looked up again")
        c.check(i18n.tr("  rung  3: LBA   123456 (+1.0 turns) phase   12.345 +/- 0.123 deg").startswith("  测量点  3："), "indents and padding survive")
        c.check(i18n.tr("something new on /some/path") == "something new on /some/path", "a line with no entry stays English")
        for words in ("python -m discprobe geo --drive E:", "C:\\results\\geo-E-20260101-100000", "12.5 %"):
            c.check(i18n.tr(words) == words, f"left alone: {words}")
        stream = io.StringIO()
        lines = i18n._Lines(stream)
        lines.write("Next:")
        lines.write("\nRotation: C")
        lines.write("LV\npartial")
        lines.flush()
        c.check(stream.getvalue() == "下一步：\n转速方式：恒定线速度 (CLV)\npartial", "lines are translated whole, however they were written")
        c.check(all(i18n.display_width(x) <= 20 for x in i18n.wrap("每次计时读之前随机等待 0 到 N 毫秒，避免 repeated reads 都跨过相同圈数", 20)), "Chinese help wraps by columns")
        c.check(i18n.display_width("光盘a") == 5 and i18n.display_width(i18n.fit("光盘光盘光盘", 7)) <= 7, "width and cutting count columns")

        p, sub, _ = cli._build_parser()
        untranslated = [a.help for parser in [p, *sub.choices.values()] for a in parser._actions
                        if a.help and a.help != "==SUPPRESS==" and not re.search("[\u4e00-\u9fff]", a.help)]
        c.check(not untranslated, f"every option's help has Chinese (add it to zh.py): {untranslated[:2]}")
        c.check(all(re.search("[\u4e00-\u9fff]", x.description or "") for x in sub.choices.values()), "every command's description has Chinese")
    finally:
        i18n.use("en")
    command = re.compile(r"python -m discprobe [^`\n]*?(?=  |`|$)", re.M)
    pairs = [("workflow", cli.WORKFLOW)] + list(cli.EXAMPLES.items())
    drifted = [name for name, english in pairs if name not in zh.BLOCKS
               or {x.strip() for x in command.findall(english)} != {x.strip() for x in command.findall(zh.BLOCKS[name])}]
    c.check(not drifted, f"Chinese help paragraphs show the same commands as the English {drifted}")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def run(*argv, **env):
        full = {k: v for k, v in os.environ.items() if k not in ("DISCPROBE_LANG", "DISCPROBE_PLAIN")}
        full.update(env)
        done = subprocess.run([sys.executable, "-m", "discprobe", *argv], capture_output=True, cwd=root, env=full)
        return done.returncode, done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")

    with tempfile.TemporaryDirectory() as d:
        en_dir, zh_dir, env_dir = (os.path.join(d, x) for x in ("en", "zh", "env"))
        quick = ("--sim", "cav", "--reps", "4", "--period-reads", "20")
        code_en, text_en = run("timing", *quick, "--out", en_dir)
        code_zh, text_zh = run("timing", *quick, "--out", zh_dir, "--lang", "zh")
        code_env, text_env = run("timing", *quick, "--out", env_dir, DISCPROBE_LANG="zh", LANG="zh_CN.UTF-8")
        c.check(code_en == code_zh == code_env == 0, "timing runs in both languages")
        c.check("Rotation: CAV" in text_en and "恒定转速" not in text_en, "the default in a pipe is English")
        c.check("Rotation: CAV" in text_env and "恒定转速" not in text_env, "DISCPROBE_LANG does not reach a pipe")
        c.check("转速方式：恒定转速 (CAV)" in text_zh, "--lang zh translates measuring output")
        left = [x for x in text_zh.splitlines() if LONG_ENGLISH.search(x) and "python -m" not in x]
        c.check(not left, f"timing has no English sentence left in Chinese {left[:2]}")

        def summary(folder):
            with open(os.path.join(guide.scan(folder)[0].path, "summary.json"), encoding="utf-8") as f:
                data = json.load(f)
            data["args"].pop("out")
            return data
        c.check(summary(en_dir) == summary(zh_dir), "the language never reaches summary.json")
        for argv in (["-h"], ["timing", "-h"], ["guide"], ["results", "--out", zh_dir], ["image"], ["timming"], ["info", "--sim", "cav", "--out", zh_dir]):
            code, text = run(*argv, "--lang", "zh")
            left = [x for x in text.splitlines() if LONG_ENGLISH.search(x) and "python -m" not in x and "docs/" not in x]
            c.check(re.search("[\u4e00-\u9fff]", text) and not left, f"Chinese: {' '.join(argv)} {left[:2]}")
        no_motion = os.path.join(d, "still")
        code, text = run("timing", *quick, "--no-animation", "--out", no_motion)
        c.check(code == 0 and "no_animation" not in json.dumps(summary(no_motion)), "--no-animation never reaches summary.json")
        code, text = run("-h")
        c.check(code == 0 and "--lang" not in text and "Start here" in text, "piped help stays as it was")
        code, text = run("-h", DISCPROBE_PLAIN="1", DISCPROBE_LANG="zh", LANG="zh_CN.UTF-8")
        c.check("Start here" in text and "--lang" not in text, "DISCPROBE_PLAIN=1 stays English")


def _completion(c) -> None:
    import shutil
    from . import __main__ as cli, completion
    rows = completion.table(cli._build_parser)
    p, sub, _ = cli._build_parser()
    c.check(set(sub.choices) <= {e[0] for e in rows[""]} and "completion" in {e[0] for e in rows[""]}, "completion knows every command")
    missing = [f for name, parser in sub.choices.items() for a in parser._actions for f in a.option_strings
               if f not in {e[0] for e in rows[name]}]
    c.check(not missing, f"completion knows every option {missing[:3]}")
    speed = next(e for e in rows["timing"] if e[0] == "--speed")
    media = next(e for e in rows["timing"] if e[0] == "--media")
    cav = next(e for e in rows["timing"] if e[0] == "--cav")
    out_flag = next(e for e in rows["timing"] if e[0] == "--out")
    c.check(speed[1] == "v" and speed[3] == "kB/s or 4x" and media[2] == ("dvd", "cd") and cav[1] == "f" and out_flag[1] == "p", "options say what their value is")
    scripts = {shell: completion.script(shell, cli._build_parser) for shell in completion.SHELLS}
    c.check(all("--along-track-frames" in text for text in scripts.values()), "every script holds the options")
    c.check("discprobe.__main__" not in "".join(scripts.values()) and not any(
        re.search(r"(?m)^[^#'\n]*\bpython -m discprobe\b", text) for text in scripts.values()), "a script never starts Python")
    i18n.use("zh")
    try:
        chinese = completion.script("powershell", cli._build_parser)
    finally:
        i18n.use("en")
    c.check(chinese.isascii() and "\\u8bfb" in chinese, "the PowerShell script is ASCII whatever the language")
    code, text = _run_cli("completion", "nope")
    c.check(code == 2 and "powershell" in text, "an unknown shell shows the usage")
    code, text = _run_cli("completion", "bash", "--lang", "zh")
    c.check(code == 0 and "_discprobe_complete" in text and "\r" not in text, "bash script: LF line ends, --lang accepted")

    with tempfile.TemporaryDirectory() as d:
        if sys.platform == "win32" and shutil.which("powershell"):
            path = os.path.join(d, "c.ps1")
            with open(path, "w", encoding="ascii") as f:
                f.write(scripts["powershell"])
            checks = (("python -m discprobe timing --sp", "--speed"), ("python -m discprobe ti", "timing tiles tilescan"),
                      ("python -m discprobe timing --media ", "dvd cd"), ("python -m discprobe --lang zh geo --ref", "--ref-lba"),
                      ("python C:\\Windows\\win.in", "C:\\Windows\\win.ini"), ("python -m d", "discprobe"), ("python -m ", "discprobe"),
                      ("python -m discprobe xyz", "xyz"), ("python -m discprobe timing --xyz", "--xyz"), ("python -m discprobe timing --reps 1", "1"))
            probe = ". '" + path + "'\n" + "".join(
                f"(TabExpansion2 -inputScript '{line}' -cursorColumn {len(line)}).CompletionMatches.CompletionText -join ' '\n" for line, _ in checks)
            done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", probe], capture_output=True, text=True)
            got = done.stdout.splitlines()
            c.check(len(got) == len(checks) and all(g == want for g, (_, want) in zip(got, checks)), f"PowerShell: Tab completes as intended {got}")
        elif sys.platform != "win32" and shutil.which("bash"):
            path = os.path.join(d, "c.bash")
            with open(path, "w", encoding="utf-8") as f:
                f.write(scripts["bash"])
            checks = (("python -m discprobe timing --sp", "--speed"), ("python -m discprobe ti", "timing tiles tilescan"),
                      ("python -m discprobe timing --media ''", "dvd cd"), ("python -m discprobe --lang zh geo --ref", "--ref-lba"),
                      ("python script.py ''", ""), ("python -m d", "discprobe"), ("python -", "-m"))
            probe = "source " + path + "\n" + "".join(
                f"COMP_WORDS=({line}); COMP_CWORD=$((${{#COMP_WORDS[@]}} - 1)); _discprobe_complete; echo \"${{COMPREPLY[*]}}\"\n" for line, _ in checks)
            done = subprocess.run(["bash", "--norc", "-c", probe], capture_output=True, text=True)
            got = done.stdout.split("\n")[:len(checks)]
            c.check(all(g == want for g, (_, want) in zip(got, checks)) and len(got) == len(checks), f"bash: Tab completes as intended {got}")


def _install(c) -> None:
    from . import __main__ as cli, completion
    with tempfile.TemporaryDirectory() as home:
        startup = os.path.join(home, "sub", "profile.ps1")
        lines = completion.install("powershell", cli._build_parser, home, [(startup, "RemoteSigned")])
        script = completion.script_path("powershell", home)
        with open(startup, encoding="utf-8") as f:
            text = f.read()
        c.check(os.path.exists(script) and completion.load_line("powershell") in text and completion.installed(home), "install writes the script and one startup line")
        c.check(any("press Tab" in x for x in lines) and any("does not have it yet" in x for x in lines), "install says this window needs a step, and how to try it")
        completion.install("powershell", cli._build_parser, home, [(startup, "RemoteSigned")])
        with open(startup, encoding="utf-8") as f:
            c.check(f.read() == text, "installing twice adds nothing")
        with open(startup, "wb") as f:
            f.write("# mine\n".encode("utf-16"))
        completion.add_to_startup(startup, "line")
        with open(startup, "rb") as f:
            c.check(f.read().decode("utf-16") == f"# mine\n{completion.MARKER}\nline\n", "a UTF-16 startup file stays UTF-16")
        with open(startup, "w", encoding="utf-8") as f:
            f.write(f"{completion.MARKER}\n")
        c.check(completion.add_to_startup(startup, "line"), "a marker with its line gone is not called installed")
        with open(startup, encoding="utf-8") as f:
            c.check(f.read() == f"{completion.MARKER}\nline\n", "the line comes back without a second marker")
        with open(startup, "wb") as f:
            f.write(b"# \xd6\xd0\xce\xc4 keep\n")
        completion.add_to_startup(startup, completion.load_line("powershell"))
        completion.uninstall("powershell", home, [(startup, "")])
        with open(startup, "rb") as f:
            c.check(f.read() == b"# \xd6\xd0\xce\xc4 keep\n", "uninstall restores other people's bytes exactly")
        c.check(not os.path.exists(script) and not completion.installed(home), "uninstall deletes the script")
        c.check(completion.uninstall("powershell", home, [(startup, "")]) == ["Tab completion was not installed."], "uninstalling twice is harmless")
        untouched = os.path.join(home, "other.ps1")
        lines = completion.install("powershell", cli._build_parser, home, [(untouched, "Restricted")])
        c.check(not os.path.exists(untouched) and any("Set-ExecutionPolicy" in x for x in lines), "a blocking policy is reported, never changed")
    for env, platform, wanted in (({}, "win32", "powershell"), ({"MSYSTEM": "MINGW64", "SHELL": "/usr/bin/bash"}, "win32", "bash"),
                                  ({"SHELL": "/bin/zsh"}, "darwin", "zsh"), ({"SHELL": "/usr/bin/fish"}, "linux", None)):
        c.check(completion.default_shell(env, platform) == wanted, f"default shell for {platform} {env}: {wanted}")


def _writing(c) -> None:
    real_term = ui._term
    try:
        ui._term = ui.Term(io.StringIO(), env={})
        with ui.writing("x", 10) as log:
            c.check(log is print, "a pipe gets the writers' lines as before")
        with ui.busy("x"):
            pass
        c.check(ui._term.stream.getvalue() == "", "a pipe sees nothing of the busy line")
        s = FakeTty()
        ui._term = ui.Term(s, env={"TERM": "xterm"}, platform="linux")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.iso")
            with open(path, "wb") as f:
                f.write(bytes(512 * 2048))
            with contextlib.redirect_stdout(io.StringIO()) as printed, ui.writing(path, 1024) as log:
                ui.time.sleep(0.3)
                halfway = ANSI.sub("", s.getvalue())
                c.check(" 50%" in halfway, "between reports the bar follows the file's size")
                log("  20.0 %")
                log("a note")
                with open(path, "wb") as f:
                    f.write(bytes(2048 * 1024))
                ui.time.sleep(0.3)
                c.check(" 99%" in ANSI.sub("", s.getvalue()) and "100%" not in ANSI.sub("", s.getvalue()), "only a report can say 100%")
                log("  100.0 %")
                ui.time.sleep(0.3)
            text = ANSI.sub("", s.getvalue())
            c.check("100%" in text and "a note\n" in text and "20.0 %" not in text and "Finished in" in printed.getvalue(), "percentage lines become the bar; other lines still print")
            c.check("\x1b[?25h" in s.getvalue(), "the cursor comes back")
        try:
            with ui.writing("no such file", 10):
                raise ValueError("stop")
        except ValueError:
            c.check(s.getvalue().count("\x1b[?25l") == s.getvalue().count("\x1b[?25h"), "an error mid-write still restores the cursor")
    finally:
        ui._term = real_term


def _run_cli(*argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, "-m", "discprobe", *argv], capture_output=True, cwd=root)
    return done.returncode, done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")


def _reader_changes_nothing(c) -> None:
    def run(wrap, keys=None):
        sim = SimDrive(mode="cav", seed=7)
        dev = sim
        if wrap:
            dev = ui.ProgressDevice(sim)
        probe = timing.TimingProbe(dev, log=lambda *_: None, reps=8, period_reads=20)
        if wrap:
            dev.progress = ui.Progress(ui.timing_status(probe, dev), ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"), keys=keys)
        s = probe.run()
        if wrap:
            dev.progress.close()
        return s, probe.events_as_rows()
    from argparse import Namespace
    skipped = Namespace(_experiment="period", period_reads=10, reps=4, targets=[1, 2])
    pauses = Namespace(pauses=100)
    status = ui.timing_status(skipped, pauses)
    skipped._experiment = "phase"
    c.check(abs(status()[0] - 30 / 46) < 1e-9, "a rotation test the progress line never saw is counted as done, not a crash")
    plain, wrapped = run(False), run(True)
    c.check(plain == wrapped, "the progress wrapper leaves summary and events identical (same seed)")
    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="80", LINES="24")
    try:
        playing = run(True, Keys(["g"], ["w"], [], ["a"], [], ["s"], ["d"], ["r"], ["n"], ["w"], [], ["a"], ["d"], ["s"], ["r"]))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    c.check(plain == playing, "playing both games leaves summary and events identical (same seed)")

    class NoIdle:
        """A real drive has no idle(): the wrapper must sleep the pause itself, minus drawing."""
        name = "X:"
        slept: list[float] = []

    dev = ui.ProgressDevice(NoIdle())
    real_sleep = ui.time.sleep
    ui.time.sleep = NoIdle.slept.append
    try:
        dev.idle(0.02)
    finally:
        ui.time.sleep = real_sleep
    c.check(len(NoIdle.slept) == 1 and 0 < NoIdle.slept[0] <= 0.02 and dev.pauses == 1, "a real drive still waits out the pause")


def _status_counts(c) -> None:
    dev = ui.ProgressDevice(SimDrive(mode="cav", seed=7))
    probe = timing.TimingProbe(dev, log=lambda *_: None, reps=8, period_reads=20)
    seen = []
    dev.progress = ui.Progress(lambda: seen.append(status()) or (None, "", None), ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"))
    dev.progress.interval = 0.0
    status = ui.timing_status(probe, dev)
    probe.run()
    dev.progress.close()
    fractions = [f for f, _, _ in seen if f is not None]
    labels = {label.split(",")[0] for _, label, _ in seen}
    c.check(fractions == sorted(fractions) and 0.9 < fractions[-1] <= 1.0, f"timing progress rises to the end ({fractions[-1]:.3f})")
    c.check({"rotation test", "phase test"} <= labels, "timing progress names its stages")


def _results(c) -> None:
    from .__main__ import main
    with tempfile.TemporaryDirectory() as d:
        def geo(name, rungs, chi2=1.0, media=None):
            folder = os.path.join(d, name)
            os.makedirs(folder)
            fit = {"u": 180000.0, "v": 5.5, "bit_nm_assumed": 133.3, "chi2_per_dof": chi2, "residual_rms_deg": 0.1,
                   "measured_span_mm": [26.0, 54.0]}
            if media:
                fit["media"] = media
            with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
                json.dump({"fit": fit, "setup": {"last_lba": 2295103}}, f)
            with open(os.path.join(folder, "targets.csv"), "w", encoding="utf-8") as f:
                f.write("header\n" + "row\n" * rungs)
            return folder
        good = geo("geo-H-20260101-100000", 22)
        cd_run = geo("geo-H-20260101-110000", 36, media="cd")
        geo("geo-H-20260101-120000", 3)                     # stopped early
        geo("geo-H-20260101-130000", 20, chi2=300.0)        # stopped by the whole-turn check
        geo("geo-SIM-cav-20260101-140000", 22)              # never burn from a simulation
        os.makedirs(os.path.join(d, "not a result"))
        c.check(guide.latest_geo("dvd", d).path == good, "latest skips stopped, simulated and other-media runs")
        c.check(guide.latest_geo("cd", d).path == cd_run, "latest honours the media")
        c.check(guide.resolve_geo("latest", "dvd", d) == os.path.join(good, "summary.json"), "--geo latest")
        c.check(guide.resolve_geo(good) == os.path.join(good, "summary.json"), "--geo accepts a result folder")
        c.check(guide.resolve_geo("x/summary.json") == "x/summary.json", "--geo keeps a file path as it is")
        empty = os.path.join(d, "none")
        try:
            guide.resolve_geo("latest", None, empty)
            c.check(False, "--geo latest with no results is refused")
        except ValueError as e:
            c.check("no geo result yet" in str(e), "--geo latest with no results is refused")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            main(["results", "geo", "--latest", "--out", d])
        c.check(printed.getvalue().strip() == cd_run, "results --latest prints the newest complete real folder")
    report = {"track_1": {"parsed": {"blank": True, "track_start": 0, "free_blocks": 2298496}},
              "atip": {"parsed": {"last_leadout_start_lba": 359849}}, "capacity": {"parsed": {"last_lba": 100}}}
    c.check(guide.sectors_from_info(report)[0] == 2298496, "--sectors from a blank DVD's free space")
    del report["track_1"]
    c.check(guide.sectors_from_info(report)[0] == 359849, "--sectors from a CD's ATIP")
    c.check("closer count" in guide.sectors_from_info(report)[1], "the ATIP count says a blank disc gives a closer one")
    del report["atip"]
    c.check(guide.sectors_from_info(report)[0] == 101, "--sectors from the last LBA")
    c.check(guide.sectors_from_info({}) is None, "--sectors unknown says nothing")


def _advice(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli
    parsers = cli._build_parser()[1].choices
    args = Namespace(drive="H:", sim=None, media="dvd", speed=None, sectors=1, transport="auto", out="results")
    def timed(mode, jitter):
        return {"period": {"rotation": {"mode": mode}, "zones": [{"jitter_deg": j} for j in jitter]}}
    good = "\n".join(guide.after_timing(args, timed("CAV", [0.4, 0.6])))
    c.check("usable" in good and f"{guide.PROG} geo --drive H:" in good, "a good drive is sent on to geo")
    clv = "\n".join(guide.after_timing(args, timed("CLV", [0.4])))
    c.check("not CAV" in clv and "--speed" in clv and " geo " not in clv, "a CLV drive is sent back with another speed")
    noisy = "\n".join(guide.after_timing(args, timed("CAV", [9.0])))
    c.check("too high" in noisy, "very high jitter is called out")
    cd_args = Namespace(**{**vars(args), "media": "cd", "speed": 1411})
    c.check("--media cd" in guide.after_timing(cd_args, timed("CAV", [0.4]))[-1], "next commands keep --media cd")
    c.check("--speed 1411" not in guide.after_timing(cd_args, timed("CAV", [0.4]))[-1], "next commands leave out the default speed")
    fit = {"chi2_per_dof": 5.2, "measured_span_mm": [25.8, 54.4], "residual_rms_deg": 0.9, "angle_sigma_measured_span_deg": 0.33}
    geo_args = Namespace(**{**vars(args), "speed": 5540})
    real_compare = guide.compare_pitch
    try:
        guide.compare_pitch = lambda out: (5.2, 5.6)
        noisy_fit = "\n".join(guide.after_geo(geo_args, fit, os.path.join("results", "geo-H-20260101-100000")))
        c.check("does not fit better" in noisy_fit and "--speed 3324" in noisy_fit and "--correction" not in noisy_fit,
                "no gain from a varying pitch: geo says carry on, no correction")
        guide.compare_pitch = lambda out: (20.0, 1.5)
        pitch_fit = guide.after_geo(geo_args, fit, os.path.join("results", "geo-H-20260101-100000"))
        c.check(any("--write-correction" in x for x in pitch_fit) and all("--correction correction.json" in x for x in pitch_fit if f"{guide.PROG} image" in x or f"{guide.PROG} disexport" in x),
                "a clear gain: geo writes the correction into the next commands")
        guide.compare_pitch = lambda out: None
        c.check(any("geo_polyfit" in x for x in guide.after_geo(geo_args, fit, "x")), "no comparison possible: geo says how to run it")
    finally:
        guide.compare_pitch = real_compare
    c.check(guide.compare_pitch("no such folder") is None, "a comparison that cannot run is not an error")
    c.check("0.33 deg" in guide.geo_summary(fit, 22) and "22 points" in guide.geo_summary(fit, 22), "geo opens with a plain summary")
    clean = {**fit, "chi2_per_dof": 1.62, "angle_sigma_measured_span_deg": 0.152}
    verdict = guide.after_geo(geo_args, clean, os.path.join("results", "geo-H-20260101-100000"))
    c.check(verdict[0].startswith("Verdict: good") and "0.15 deg" in verdict[0] and "0.13 mm" in verdict[0], "a clean geo gets a verdict in plain terms")
    i18n.use("zh")
    try:
        c.check(i18n.tr(verdict[0]).startswith("结论"), "the verdict has Chinese")
    finally:
        i18n.use("en")
    real_compare = guide.compare_pitch
    try:
        for ratio, word in (((20.0, 1.5), "good once corrected"), ((5.2, 5.6), "usable, but noisy"), (None, "not settled")):
            guide.compare_pitch = lambda out, ratio=ratio: ratio
            c.check(word in guide.after_geo(geo_args, fit, os.path.join("results", "geo-H-20260101-100000"))[0], f"a noisy geo: {word}")
    finally:
        guide.compare_pitch = real_compare
    geo_out = os.path.join("results", "geo-H-20260101-100000")
    def verdict_on(sigma, chi2=1.0):
        return guide.after_geo(geo_args, {**fit, "chi2_per_dof": chi2, "angle_sigma_measured_span_deg": sigma}, geo_out)
    c.check(verdict_on(0.25)[0].startswith("Verdict: good"), "the limit itself is still good")
    noisy_run = verdict_on(0.4)
    c.check("usable, but noisy" in noisy_run[0] and "good" not in noisy_run[0] and "0.35 mm" in noisy_run[0]
            and any("--speed 3324" in x for x in noisy_run), "wide error bars with a clean fit are not called good, and geo says what to try")
    bad_run = verdict_on(3.0)
    c.check("too noisy" in bad_run[0] and "2.62 mm" in bad_run[0] and "another drive" in bad_run[1], "very wide error bars are called out")
    real_compare = guide.compare_pitch
    i18n.use("zh")
    try:
        c.check(all(i18n.tr(x) != x for x in (noisy_run[0], noisy_run[1], bad_run[0])), "the noisy verdicts have Chinese")
        try:
            guide.compare_pitch = lambda out: (30.0, 10.0)
            helps = verdict_on(2.0, 30.0)
            c.check("a correction helps" in helps[0] and "good" not in helps[0] and "1.15 deg" in helps[0] and i18n.tr(helps[0]) != helps[0]
                    and any("--write-correction" in x for x in helps) and any("--speed 3324" in x for x in helps),
                    "a correction that leaves wide error bars is not called good")
            guide.compare_pitch = lambda out: (5.0, 5.2)
            lost = verdict_on(2.0, 5.0)
            c.check("too noisy" in lost[0] and not any("You can carry on" in x for x in lost) and any(i18n.tr(x) != x and "does not fit better" in x for x in lost),
                    "read noise this large does not say carry on")
        finally:
            guide.compare_pitch = real_compare
    finally:
        i18n.use("en")
    measured = {"setup": {"last_lba": 359751}, "fit": {"media": "cd"}}
    c.check("how much was burned" in guide._sectors_for(measured, "no such folder")[1], "--sectors from the measured disc says it may be less than a blank holds")
    def blank(profile, count):
        return {"configuration": {"parsed": {"current_profile": profile}}, "track_1": {"parsed": {"blank": True, "track_start": 0, "free_blocks": count}}}
    c.check("--sectors 699648" in guide._random_for_blank(blank(0x11, 713936))[1], "a miniDVD gets a random disc that fits, with room to close")
    usual_size = guide._random_for_blank(blank(0x11, 2295104))
    c.check("--sectors" not in usual_size[1] and "would not fit" not in usual_size[0], "a 2295104-sector DVD keeps the usual size, which has burned many times")
    c.check("--sectors" not in guide._random_for_blank(blank(0x11, 2298496))[1], "a 2298496-sector DVD keeps the usual size")
    full_cd = guide._random_for_blank(blank(0x09, 359847))[1]
    c.check("--sectors" not in full_cd and "--media cd" in full_cd, "a blank CD is told --media cd")
    i18n.use("zh")
    try:
        said = [guide.sectors_hint("no such file"), "Enter the same number in DiscImageStudio. A blank disc's `info` is the count to go by: one user found read-from-disc there too high."]
        c.check(all(i18n.tr(x) != x for x in said) and "`info`" in said[0], "the --sectors advice goes by `info` on a blank disc, in both languages")
    finally:
        i18n.use("en")
    helps = [a.help for name in ("timing", "geo", "random", "disexport") for a in parsers[name]._actions if "--sectors" in a.option_strings]
    c.check(len(helps) == 4 and all("not " in x for x in helps), "each --sectors help says what it is not")
    whole = Namespace(**{**vars(args), "sectors": 16})
    c.check(any("geo" in x and "--sectors 16" in x for x in guide.after_timing(whole, timed("CAV", [0.5]))), "timing with --sectors 16 carries it to the geo command")
    c.check("--media cd --sectors 326336" in guide._random_for_blank(blank(0x09, 333000))[1], "a 74-minute CD gets a random disc that fits")
    c.check("--media cd" in "".join(guide.after_info(Namespace(**vars(args)), blank(0x09, 359847))), "info on a blank CD offers the CD command")
    bd = {"setup": {"family": "bd"}, **timed("mixed", [0.4])}
    bd_lines = guide.after_timing(args, bd)
    c.check("constant linear speed" in bd_lines[1] and "8990" in bd_lines[2] and "3324" not in "".join(bd_lines), "on Blu-ray a non-CAV result does not promise another speed helps, and offers a BD speed")
    bd_good = guide.after_timing(args, {"setup": {"family": "bd"}, **timed("CAV", [9.0])})
    c.check(any("8990" in x for x in bd_good) and not any("--sectors 16" in x or " geo " in x for x in bd_good), "a noisy Blu-ray stays with BD speeds and is not sent on to geo")
    i18n.use("zh")
    try:
        c.check(all(i18n.tr(x) != x for x in (bd_lines[1], bd_good[-1], *guide.after_random(Namespace(**vars(args)))[:3], *guide.after_disexport(True))), "the new advice has Chinese")
    finally:
        i18n.use("en")
    c.check(len(guide.after_disexport(True)) == 3 and len(guide.after_disexport()) == 2, "a CD preset without the constant says the route settles it")
    cd_next = guide.after_geo(cd_args, clean, os.path.join("results", "geo-H-20260101-100000"))
    c.check(any("disexport" in x for x in cd_next[:6]) and "README.md" in "".join(cd_next) and
            next(i for i, x in enumerate(cd_next) if "disexport" in x) < next(i for i, x in enumerate(cd_next) if " image" in x),
            "a CD geo offers the preset before a picture ISO")
    with tempfile.TemporaryDirectory() as d:
        for name, profile, last in (("info-H-20260101-100000", 0x11, 2295103), ("info-H-20260102-100000", 0x09, 359847)):
            os.makedirs(os.path.join(d, name))
            with open(os.path.join(d, name, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"configuration": {"parsed": {"current_profile": profile}}, "capacity": {"parsed": {"last_lba": last}}}, f)
        c.check(guide._sectors_for({"fit": {}}, d)[0] == "2295104" and guide._sectors_for({"fit": {"media": "cd"}}, d)[0] == "359848",
                "the --sectors suggestion comes from an `info` of the same kind of disc")
    stop = "\n".join(guide.after_geo_stop(args, "the spindle speed never settled; is the read speed fixed (--speed)?"))
    c.check("timing" in stop and "--speed" in stop, "a geo that never settled gets a next step")

    def retry_at(speed, media="dvd"):
        at = Namespace(**{**vars(args), "speed": speed, "media": media})
        lines = guide.after_geo_stop(at, "a whole-turn count went wrong") + guide.after_geo_stop(at, "the spindle speed never settled")
        return lines + guide.after_geo(at, {**fit, "chi2_per_dof": 1.0}, os.path.join("results", "geo-H-20260101-100000"))
    lowest, usual, cd = (retry_at(3324), retry_at(5540), retry_at(1411, "cd"))
    c.check(not any("lower speed" in x for x in lowest) and sum("a different speed" in x for x in lowest) == 3 and any("--speed 5540" in x for x in lowest),
            "already at the lowest speed: geo does not call the next one lower")
    c.check(any("--ranges" in x for x in lowest), "already at the lowest speed: geo still offers --ranges")
    c.check(sum("a lower speed" in x for x in usual) == 3 and any("--speed 3324" in x for x in usual), "with a lower speed to try, geo says lower")
    c.check(not any("lower speed" in x for x in cd) and any("--speed 2822" in x for x in cd), "CD at its default speed: the next one is not called lower")
    i18n.use("zh")
    try:
        said = [i18n.tr(x) for x in lowest + usual]
        c.check(not any(x.isascii() for x in said if "peed" in x and "--speed" not in x) and any("换一个速度" in x for x in said) and any("降速" in x for x in said),
                "the retry advice is in both languages")
    finally:
        i18n.use("en")
    hint = guide.parser_hint("argument <command>: invalid choice: 'timming' (choose from a)", ["timming"], ["timing", "geo"])
    c.check("timing" in (hint or ""), "a mistyped command gets a suggestion")
    hint = guide.parser_hint("the following arguments are required: --geo", ["image"], ["image"])
    c.check(hint == f"Use your last measurement: {guide.PROG} image --geo latest", "a missing --geo offers latest")
    c.check(all(line.isascii() for line in guide.guide_lines("dvd", "no such folder")), "guide text is ASCII")
    finished = guide.after_image("iso/p.iso", "iso/p.preview.png", os.path.join("results", "geo-H-20260101-100000", "summary.json"))
    c.check("preview" in finished[0] and any("burn" in x and "p.iso" in x for x in finished), "a finished picture says: check the preview, then burn")
    fake = guide.after_image("iso/p.iso", "iso/p.preview.png", os.path.join("results", "geo-SIM-cav-20260101-100000", "summary.json"))
    c.check(any("do not burn" in x for x in fake) and not any("If it looks right" in x for x in fake), "a picture from a simulated run must not be burned")
    sim_args = Namespace(**{**vars(args), "sim": "cav", "drive": None})
    c.check("simulated drive" in guide.after_timing(sim_args, timed("CAV", [0.4]))[0] and "simulated drive" in guide.after_timing(sim_args, timed("CLV", [0.4]))[0],
            "a verdict on the simulated drive says so")
    c.check(not any("simulated" in x for x in guide.after_timing(args, timed("CAV", [0.4]))), "a real drive's verdict does not")
    real_missing = guide.missing_packages
    try:
        guide.missing_packages = lambda: ["numpy", "scipy"]
        c.check("numpy, scipy" in guide.after_selftest()[0] and guide.INSTALL in guide.after_selftest()[1], "a self-test that skipped checks says so")
        guide.missing_packages = lambda: []
        c.check("guide" in guide.after_selftest()[0], "a complete self-test points to guide")
    finally:
        guide.missing_packages = real_missing
    with tempfile.TemporaryDirectory() as d:
        here = os.getcwd()
        os.chdir(d)
        try:
            os.makedirs("iso")
            with open(os.path.join("iso", "random.iso"), "wb"):
                pass
            piped, shown = guide.guide_lines("dvd"), guide.guide_lines("dvd", notes=True)
            c.check(any(x.startswith("  [x] Random-data disc") for x in piped), "a script keeps the tick it always saw")
            c.check(any(x.startswith("  [ ] Random-data disc") for x in shown), "at a terminal a written file is not yet a disc")
        finally:
            os.chdir(here)
    plain, noted = guide.guide_lines("dvd", "no such folder"), guide.guide_lines("dvd", "no such folder", notes=True)
    # The ticked row depends on the folder this runs in, and has its own check above.
    plain, noted = [x for x in plain if "Random-data disc" not in x], [x for x in noted if "Random-data disc" not in x]
    c.check(len(noted) == len(plain) + 1 and set(plain) < set(noted), "at a terminal the next command says what it does; a pipe gets the same lines as before")
    i18n.use("zh")
    try:
        untranslated = [x for x in set(noted) - set(plain) if i18n.tr(x) == x]
    finally:
        i18n.use("en")
    c.check(not untranslated, f"the note has Chinese {untranslated}")


def _command_line(c) -> None:
    import shutil
    from . import __main__ as cli

    def code_and_stderr(*argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            try:
                cli.main(list(argv))
                return 0, ""
            except SystemExit as e:
                text = err.getvalue() + (e.code if isinstance(e.code, str) else "")
                return (e.code if isinstance(e.code, int) else 1), text
    real_term = ui._term
    ui._term = ui.Term(io.StringIO(), env={})   # what a script sees, also when the self-test runs at a terminal
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "r")
        code, _ = code_and_stderr("timing", "--sim", "cav", "--speed", "4x", "--reps", "4", "--period-reads", "20", "--out", out)
        run = guide.scan(out)[0]
        c.check(code == 0 and run.summary["args"]["speed"] == 5540, "--speed 4x is 5540 kB/s on DVD")
        code, text = code_and_stderr("geo", "--sim", "cav", "--speed", "fast")
        c.check(code == 2 and "not a speed" in text, "a bad --speed is an argument error")
        code, _ = code_and_stderr()
        c.check(code == 2, "no command in a pipe is still an argument error")
        if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("scipy") is None:
            print("--geo and --ranges error checks skipped (need numpy and scipy)")
        else:
            code, _ = code_and_stderr("timing", "--sim", "cav", "--media", "cd", "--speed", "8x", "--reps", "4", "--period-reads", "20", "--out", out)
            speeds = sorted(r.summary["args"]["speed"] for r in guide.scan(out))
            c.check(code == 0 and speeds == [1411, 5540], "--speed 8x is 1411 kB/s on CD")
            for given, wanted, name in ((["--sp", "4x"], 706, "--sp 4x"), (["--speed=8x"], 1411, "--speed=8x"), ([], 1411, "no --speed")):
                shortened = os.path.join(d, "short")
                shutil.rmtree(shortened, ignore_errors=True)
                code, _ = code_and_stderr("timing", "--sim", "cav", "--media", "cd", *given, "--reps", "4", "--period-reads", "20", "--out", shortened)
                c.check(code == 0 and guide.scan(shortened)[0].summary["args"]["speed"] == wanted, f"with --media cd: {name} gives {wanted} kB/s")
            code, text = code_and_stderr("geo", "--sim", "cav", "--ranges", "5-1")
            c.check(code == 1 and "start-end" in text, "a backwards --ranges says how to write it")
            code, text = code_and_stderr("image", "--geo", os.path.join(d, "missing.json"))
            c.check(code == 1 and "no such geo result" in text, "a missing --geo file is a plain error")
            geo_cd = os.path.join(d, "cd.json")
            with open(geo_cd, "w", encoding="utf-8") as f:
                json.dump({"fit": {"u": 150000.0, "v": 9.0, "bit_nm_assumed": 277.0, "media": "cd"}}, f)
            code, text = code_and_stderr("disexport", "--geo", geo_cd, "--media", "dvd", "--output", os.path.join(d, "p.json"))
            c.check(code == 1 and "does not match" in text, "disexport --media checks the fit")
            code, text = code_and_stderr("disexport", "--geo", geo_cd, "--output", os.path.join(d, "p.json"))
            c.check(code == 1 and "needs --sectors" in text, "a CD preset without --sectors is refused")
            geo_dvd = os.path.join(d, "dvd.json")
            with open(geo_dvd, "w", encoding="utf-8") as f:
                json.dump({"fit": {"u": 120000.0, "v": 3.0, "bit_nm_assumed": 133.3}}, f)
            code, text = code_and_stderr("disexport", "--geo", geo_dvd, "--output", os.path.join(d, "p.json"))
            c.check(code == 1 and "needs --sectors" in text and not os.path.exists(os.path.join(d, "p.json")),
                    "a DVD preset without --sectors is refused too, with no file written")
            not_geo = os.path.join(d, "t.json")
            with open(not_geo, "w", encoding="utf-8") as f:
                json.dump({"cache": {}}, f)
            code, text = code_and_stderr("disexport", "--geo", not_geo)
            c.check(code == 1 and "not the summary.json" in text, "a summary without a fit is a plain error")

    class Stopped:
        name = "SIM"

        def __init__(self):
            self.sim = SimDrive(mode="cav", seed=7)
            self.left = 50

        def execute(self, *a, **k):
            self.left -= 1
            if self.left <= 0:
                raise KeyboardInterrupt
            return self.sim.execute(*a, **k)

        def __getattr__(self, name):
            return getattr(self.sim, name)
    real_open = cli._open
    cli._open = lambda args: Stopped()
    try:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r")
            code, text = code_and_stderr("timing", "--sim", "cav", "--out", out)
            kept = os.path.exists(os.path.join(guide.scan(out)[0].path, "summary.json"))
            c.check(code == 130 and "Ctrl+C" in text and kept, "Ctrl+C says so and keeps the partial results")
            c.check(guide.scan(out)[0].stopped == "interrupted", "and they say they are partial")
    finally:
        cli._open = real_open
        cli._Parser.last_out = None
        ui._term = real_term


def _picture(c) -> None:
    if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("PIL") is None:
        print("picture checks skipped (need numpy and pillow)")
        return
    import numpy as np
    from PIL import Image
    from . import imagedisc

    def extent(design):
        rows, cols = np.flatnonzero(design.any(axis=1)), np.flatnonzero(design.any(axis=0))
        return int(rows[0]), int(rows[-1] - rows[0] + 1), int(cols[0]), int(cols[-1] - cols[0] + 1)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "picture.png")
        Image.fromarray((np.add.outer(np.arange(300), np.arange(300)) * 255 // 598).astype(np.uint8)).save(path)
        with Image.open(path) as im:
            before = np.asarray(im.convert("L").resize((5800, 5800)), dtype=np.float32) / 255 < 0.5
        square = np.zeros((imagedisc.SIZE, imagedisc.SIZE), bool)
        square[100:5900, 100:5900] = before
        c.check(np.array_equal(imagedisc.picture_design(path), square), "a square picture comes out exactly as it did before")
        Image.new("L", (300, 150), 0).save(path)
        wide = imagedisc.picture_design(path)
        c.check(extent(wide) == (1550, 2900, 100, 5800), "a wide dark picture keeps its shape, centred, with its long side on the diameter")
        cleared = imagedisc.clear_inside(wide, 26.0)
        c.check(extent(cleared) == extent(wide) and not cleared[3000, 3000], "and on CD it only loses the middle")
        Image.new("L", (150, 300), 0).save(path)
        c.check(extent(imagedisc.picture_design(path)) == (100, 5800, 1550, 2900), "a tall one too")
        limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = 1000       # 300 x 150 is more than twice this, which is when Pillow refuses
        try:
            imagedisc.picture_design(path)
            c.check(Image.MAX_IMAGE_PIXELS == 1000, "a picture above Pillow's size limit loads, and the limit stays for everything else")
            try:
                Image.open(path).close()
                c.check(False, "other code still gets Pillow's refusal")
            except Image.DecompressionBombError:
                c.check(True, "other code still gets Pillow's refusal")
            try:
                imagedisc.picture_design(os.path.join(d, "missing.png"))
            except OSError:
                c.check(Image.MAX_IMAGE_PIXELS == 1000, "a picture that fails to load leaves the limit alone too")
        finally:
            Image.MAX_IMAGE_PIXELS = limit


def _blu_ray(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli
    from .scsi import ScsiResult

    class Disc:
        def __init__(self, profile):
            self.profile, self.commands = profile, 0

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            self.commands += 1
            return ScsiResult(0, bytes([0, 0, 0, 4, 0, 0, 0, self.profile]), None, 0, 1000)

    def run(profile, speed, sim=None):
        args = Namespace(speed=speed, sim=sim)
        disc = Disc(profile)
        with contextlib.redirect_stdout(io.StringIO()):
            cli._blu_ray_speed(disc, args)
        return args.speed, disc.commands
    eight = cli._SpeedKbs(11080)
    eight.multiple = 8.0
    c.check(run(0x41, eight)[0] == 35960, "8x on a Blu-ray disc is 35960 kB/s")
    c.check(run(0x11, eight)[0] == 11080, "8x on a DVD stays 11080 kB/s")
    c.check(run(0x41, 5540) == (5540, 0), "a speed in kB/s is left alone and asks the drive nothing")
    c.check(run(0x41, eight, sim="cav") == (eight, 0), "the simulated drive is not asked")
    c.check(json.loads(json.dumps({"speed": eight}))["speed"] == 11080, "the speed still saves as a plain number")


def _no_disc(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli, info, mmc
    from .scsi import ScsiResult, Sense

    class Empty:
        """A drive that answers everything with the same Not Ready sense."""
        name = "SIM"

        def __init__(self, asc, ascq=None):
            self.sense = Sense(2, asc, ascq if ascq is not None else 2 if asc == 0x3A else 1)

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            return ScsiResult(2, b"", self.sense, 0, 1000)

    c.check(mmc.not_ready(Sense(2, 0x3A, 2)) == mmc.TRAY_OPEN and mmc.not_ready("2/3A/02") == mmc.TRAY_OPEN, "sense 3A/02 means the tray is open")
    c.check(mmc.not_ready(Sense(2, 0x3A, 1)) == mmc.NOT_RECOGNISED and mmc.not_ready("2/3A/01") == mmc.NOT_RECOGNISED, "sense 3A/01 means the tray is closed and no disc was recognised")
    c.check(mmc.not_ready(Sense(2, 0x3A, 0)) == mmc.NO_DISC and mmc.not_ready("2/3A/03") == mmc.NO_DISC, "other 3A answers say no disc, without guessing at the tray")
    c.check(mmc.not_ready(Sense(2, 0x04, 1)) == mmc.LOADING, "sense 04 means still loading")
    c.check(mmc.not_ready(None) is None and mmc.not_ready(Sense(2, 0x30, 0)) is None and mmc.not_ready(Sense(3, 0x3A, 0)) is None,
            "other answers are not taken for an empty tray")
    report = info.collect(Empty(0x3A))
    shown = info.summarize(report)
    c.check(mmc.TRAY_OPEN in shown and not any("unknown" in x or "3A" in x for x in shown), "info says the tray is open, once")
    c.check(mmc.NOT_RECOGNISED in info.summarize(info.collect(Empty(0x3A, 1))), "info says a closed tray has no disc it can read")
    args = Namespace(drive="H:", sim=None, media="cd", speed=1411, transport="auto", out="results")
    c.check(guide.after_info(args, report) == [], "info does not send an empty drive off to burn a disc")
    c.check(all(guide.after_geo_stop(args, x) == [] and guide.after_timing_stop(args, x) == [] for x in mmc.NOT_READY), "no other advice on top of it")
    i18n.use("zh")
    try:
        c.check(all(i18n.tr(x) != x for x in mmc.NOT_READY), "all these messages have Chinese")
    finally:
        i18n.use("en")

    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            try:
                cli.main(list(argv))
                code = 0
            except SystemExit as e:
                err.write(e.code if isinstance(e.code, str) else "")
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue() + err.getvalue()
    real_term, real_open = ui._term, cli._open
    ui._term = ui.Term(io.StringIO(), env={})   # what a script sees: the tester's pipe got the misleading text
    try:
        with tempfile.TemporaryDirectory() as d:
            cli._open = lambda args: Empty(0x3A)
            code, text = run("timing", "--sim", "cav", "--out", d)
            c.check(code == 1 and mmc.TRAY_OPEN in text and "burn a test disc" not in text, "timing on an open tray says so")
            if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("scipy") is None:
                print("CD and geo open-tray checks skipped (need numpy and scipy)")
            else:
                code, text = run("timing", "--sim", "cav", "--media", "cd", "--out", d)
                c.check(code == 1 and mmc.TRAY_OPEN in text and "Mode 1" not in text, "timing --media cd on an open tray says so")
                for media in ("cd", "dvd"):
                    code, text = run("geo", "--sim", "cav", "--media", media, "--out", d)
                    c.check(mmc.TRAY_OPEN in text and "how noisy" not in text, f"geo --media {media} on an open tray says so")
            cli._open = lambda args: Empty(0x3A, 1)
            code, text = run("timing", "--sim", "cav", "--out", d)
            c.check(code == 1 and mmc.NOT_RECOGNISED in text and "burn a test disc" not in text, "timing on a disc the drive can't recognise says so")
            cli._open = lambda args: Empty(0x04)
            code, text = run("timing", "--sim", "cav", "--out", d)
            c.check(code == 1 and mmc.LOADING in text, "timing while the disc is loading says to wait")
    finally:
        ui._term, cli._open = real_term, real_open
        cli._Parser.last_out = None


def _stopped_part_way(c) -> None:
    """The tray opens or the disc changes during a run. On a real GH70N every read then answers 2/3A/02 in about 5 ms,
    so without a stop the run used up all its reads in seconds and blamed the speed or the drive."""
    from . import __main__ as cli, mmc
    from .scsi import ScsiResult, Sense

    class Goes:
        """The simulated drive, until the disc goes after some commands; for only `lasting` commands if given."""
        name = "SIM"

        def __init__(self, sense, after, lasting=None, then=None):
            self.sim = SimDrive(mode="cav", seed=7)
            self.sense, self.after, self.lasting, self.then = sense, after, lasting, then
            self.count = 0

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            self.count += 1
            if self.count > self.after and (self.lasting is None or self.count <= self.after + self.lasting):
                if self.then and self.count == self.after + self.lasting:
                    raise self.then
                return ScsiResult(2, b"", self.sense, 0, 1000)
            return self.sim.execute(cdb, data_len, direction, timeout_s)

        def __getattr__(self, name):
            return getattr(self.sim, name)

    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            try:
                cli.main(list(argv))
                code = 0
            except SystemExit as e:
                err.write(e.code if isinstance(e.code, str) else "")
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue() + err.getvalue()

    def failed_reads(result):
        import csv
        with open(os.path.join(result.path, "events.csv"), newline="", encoding="utf-8") as f:
            return sum(row["status"] != "0" for row in csv.DictReader(f))

    def real(result):
        """The same result as if from a real drive, which `latest` would consider."""
        path = result.path.replace("-SIM-cav-", "-H-")
        os.rename(result.path, path)
        return path

    tray, gone_disc, changed, loading = Sense(2, 0x3A, 2), Sense(2, 0x3A, 1), Sense(6, 0x28, 0), Sense(2, 0x04, 1)
    c.check(mmc.disc_gone(tray) == mmc.TRAY_OPEN and mmc.disc_gone(gone_disc) == mmc.NOT_RECOGNISED and mmc.disc_gone(changed) == mmc.DISC_CHANGED, "a read answering these means the disc has gone")
    c.check(mmc.disc_gone(loading) is None and mmc.disc_gone(Sense(3, 0x11, 0)) is None and mmc.disc_gone(None) is None, "others do not, on their own")
    real_term, real_open = ui._term, cli._open
    ui._term = ui.Term(io.StringIO(), env={})
    try:
        with tempfile.TemporaryDirectory() as d:
            for name, after in (("before the rotation test ends", 150), ("during the phase test", 480)):
                out = os.path.join(d, f"timing{after}")
                cli._open = lambda args: Goes(tray, after)
                code, text = run("timing", "--sim", "cav", "--out", out)
                result = guide.scan(out)[0]
                c.check(code == 1 and mmc.TRAY_OPEN in text and "another --speed" not in text, f"timing, tray opened {name}: stops and says why")
                c.check(failed_reads(result) == 1 and result.stopped == mmc.TRAY_OPEN, f"after one failed read, and the result says so ({name})")
                c.check("not enough usable reads" not in text and "Verdict" not in text, f"no verdict on what is left ({name})")
            cli._open = lambda args: Goes(changed, 150)
            out = os.path.join(d, "changed")
            code, text = run("timing", "--sim", "cav", "--out", out)
            c.check(code == 1 and mmc.DISC_CHANGED in text and guide.scan(out)[0].stopped == mmc.DISC_CHANGED, "a changed disc stops it too")
            cli._open = lambda args: Goes(loading, 150, 5)
            out = os.path.join(d, "blip")
            code, text = run("timing", "--sim", "cav", "--out", out)
            c.check(code == 0 and not guide.scan(out)[0].stopped and failed_reads(guide.scan(out)[0]) == 5, "a moment of not ready passes, as it always did")
            cli._open = lambda args: Goes(loading, 150)
            out = os.path.join(d, "loading")
            code, text = run("timing", "--sim", "cav", "--out", out)
            c.check(code == 1 and mmc.LOADING in text and failed_reads(guide.scan(out)[0]) == timing.MAX_LOADING_READS, "not ready that lasts stops it, after a while")
            out = os.path.join(d, "whole")
            cli._open = real_open
            code, text = run("timing", "--sim", "cav", "--out", out)
            c.check(code == 0 and guide.scan(out)[0].stopped is None, "a run that finishes says nothing about stopping")
            stopped_folder = os.path.join(d, "timing480")
            path = real(guide.scan(stopped_folder)[0])
            rows = [x for x in guide.guide_lines("dvd", stopped_folder, notes=True) if "(timing)" in x]
            c.check(rows and rows[0].startswith("  [ ]"), "guide does not tick a drive check that stopped part way")
            result = next(r for r in guide.scan(stopped_folder) if r.path == path)
            c.check("stopped early" in result.describe(), "and `results` says it stopped early")

            if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("scipy") is None:
                print("geo part-way checks skipped (need numpy and scipy)")
                return
            out = os.path.join(d, "geo")
            cli._open = lambda args: Goes(tray, 700)
            code, text = run("geo", "--sim", "cav", "--out", out)
            result = guide.scan(out)[0]
            c.check(code == 1 and mmc.TRAY_OPEN in text and "never settled" not in text and "hold one speed" not in text, "geo, tray opened: stops, says why and exits 1")
            c.check(result.stopped == mmc.TRAY_OPEN and result.rungs() >= guide.MIN_RUNGS and "u" in result.fit, "its rungs are kept, with enough to fit")
            c.check(not result.geo_complete() and "won't use these" in text, "but it is not taken for complete, and it says so")
            real(result)
            c.check(guide.latest_geo("dvd", out) is None, "so --geo latest will not burn from it")
            c.check(next(r for r in guide.scan(out)).describe().endswith("(stopped early)"), "and `results` says it stopped early")
            rows = [x for x in guide.guide_lines("dvd", out, notes=True) if "(geo)" in x]
            c.check(rows and rows[0].startswith("  [ ]"), "guide does not tick it either")
            for name, thrown in (("Ctrl+C", KeyboardInterrupt()), ("a drive that vanishes", OSError(433, "gone"))):
                out = os.path.join(d, f"geo-{type(thrown).__name__}")
                cli._open = lambda args: Goes(tray, 700, 1, thrown)
                code, text = run("geo", "--sim", "cav", "--out", out)
                result = guide.scan(out)[0]
                c.check(code != 0 and result.stopped == "interrupted" and not result.geo_complete(), f"{name} during geo is not complete either")
            out = os.path.join(d, "geo-whole")
            cli._open = real_open
            code, text = run("geo", "--sim", "cav", "--out", out)
            result = guide.scan(out)[0]
            c.check(code == 0 and not result.stopped and result.geo_complete(), "a geo that finishes is complete")
            real(result)
            c.check(guide.latest_geo("dvd", out) is not None, "and --geo latest takes it")
            from . import picker
            partial, whole = guide.scan(os.path.join(d, "geo"))[0], guide.scan(out)[0]
            partial.summary["fit"]["angle_sigma_measured_span_deg"] = 0.001     # a good-looking fit is what makes these dangerous
            c.check(partial.quality() == "stopped early" and not partial.reliable(), "the list of results calls a stopped run what it is")
            c.check(picker.sort_runs([partial, whole])[0] is whole, "and however precise it looks, it sorts after a finished one")
            group = picker.Group("disc", "drive", "dvd", False)
            group.runs = [partial, whole]
            c.check(group.best() == whole.sigma, "and is not its disc's best")
    finally:
        ui._term, cli._open = real_term, real_open
        cli._Parser.last_out = None


def _image_cut_short(c) -> None:
    from . import iso9660
    real_term = ui._term
    here = os.getcwd()
    ui._term = ui.Term(io.StringIO(), env={})

    class Stop(Exception):
        pass
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            os.chdir(d)
            path = os.path.join("iso", "x.iso")
            marker = path + iso9660.UNFINISHED
            with ui.writing(path, 10) as log:
                c.check(os.path.exists(marker), "while an image is written, a marker says so")
                with open(path, "wb") as f:
                    f.write(b"all of it")
            c.check(os.path.exists(path) and not os.path.exists(marker), "a whole image stays, without the marker")
            good = open(path, "rb").read()
            try:
                with ui.writing(path, 10):
                    raise Stop
            except Stop:
                pass
            c.check(open(path, "rb").read() == good and not os.path.exists(marker), "a check failing before the write leaves the old image alone")
            for name, thrown in (("an error", Stop()), ("Ctrl+C", KeyboardInterrupt()), ("a full disk", OSError(28, "no space"))):
                try:
                    with ui.writing(path, 10):
                        with open(path, "wb") as f:
                            f.write(b"part")
                        raise thrown
                except (Stop, KeyboardInterrupt, OSError):
                    pass
                c.check(not os.path.exists(path) and not os.path.exists(marker), f"{name} part way removes what it left")
                with open(path, "wb") as f:
                    f.write(b"all of it")
            try:
                from . import randomdisc

                def stop(message):
                    raise KeyboardInterrupt
                random_path = os.path.join("iso", "random.iso")
                try:
                    with ui.writing(random_path, 100000):
                        randomdisc.write_iso(random_path, 100000, log=stop)
                except KeyboardInterrupt:
                    pass
                c.check(not os.path.exists(random_path), "the real random image, stopped part way, is gone")
                c.check(not any("written; burn it" in x for x in guide.guide_lines("dvd", notes=True)), "and guide does not say to burn it")
                # A closed window: nothing got to clean up.
                with open(random_path, "wb") as f:
                    f.write(b"part")
                open(random_path + iso9660.UNFINISHED, "w").close()
                lines = guide.guide_lines("dvd", notes=True)
                c.check(not any("written; burn it" in x for x in lines) and any("random --output" in x for x in lines), "a marker left by a killed run: guide says make it again")
                with ui.writing(random_path, 10):
                    c.check(not os.path.exists(random_path), "and the next write starts clean")
                    with open(random_path, "wb") as f:
                        f.write(b"all of it")
                c.check(os.path.exists(random_path) and not os.path.exists(random_path + iso9660.UNFINISHED), "and ends whole")
                lines = guide.guide_lines("dvd", notes=True)
                c.check(any("written; burn it" in x for x in lines), "guide then says to burn it")
            except ModuleNotFoundError:
                print("random image checks skipped (need numpy)")
            os.chdir(here)
    finally:
        os.chdir(here)
        ui._term = real_term


def _greetings(c) -> None:
    import datetime
    from . import __main__ as cli, greetings
    week = [entry for day in greetings.WEEK for entry in day]
    every = list(greetings.FIRST_TIME) + week
    c.check(len(greetings.WEEK) == 7 and all(len(day) == 5 for day in greetings.WEEK), "a line for every day and time of day")
    c.check(len({en for en, _ in every}) == len(every) and len({zh for _, zh in every}) == len(every), "no line is used twice")
    c.check(all(en.isascii() and re.search("[\u4e00-\u9fff]", zh) and i18n.display_width(zh) < 50 and len(en) < 60 for en, zh in every),
            "every greeting has both languages and fits a narrow window")
    claims = re.compile(r"steady|settled|ready to|\d+ ?rpm|\u7a33\u5b9a|\u5df2\u5c31\u7eea", re.I)
    c.check(not any(claims.search(en + zh) for en, zh in every), "no greeting reads like a measurement")
    monday = datetime.date(2026, 11, 2)     # a Monday

    def at(day, hour):
        return greetings.pick(now=datetime.datetime(monday.year, monday.month, monday.day + day, hour, 30))
    for hour, slot in ((0, 0), (4, 0), (5, 1), (8, 1), (9, 2), (11, 2), (12, 3), (17, 3), (18, 4), (21, 4), (22, 0), (23, 0)):
        c.check(at(0, hour) == greetings.WEEK[0][slot][0], f"{hour}:30 falls in the right part of the day")
    c.check(at(4, 19) == greetings.WEEK[4][4][0] and at(6, 10) == greetings.WEEK[6][2][0], "each day has its own lines")
    c.check(greetings.pick(True) in [en for en, _ in greetings.FIRST_TIME], "a first run is welcomed")
    i18n.use("zh")
    try:
        c.check(at(0, 10) == greetings.WEEK[0][2][1] and greetings.pick(True) in [zh for _, zh in greetings.FIRST_TIME], "the greeting follows the language")
    finally:
        i18n.use("en")
    real_term = ui._term
    try:
        ui._term = ui.Term(io.StringIO(), env={})
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            cli.cmd_guide(type("Args", (), {"guide_media": "dvd"})())
        c.check(not any(en in printed.getvalue() for en, _ in every), "a pipe gets no greeting")
    finally:
        ui._term = real_term


def _priority(c) -> None:
    """In a process of its own, so the rest of the self-test keeps its normal priority."""
    if sys.platform != "win32":
        return
    code = ("import ctypes; from ctypes import wintypes; from discprobe import spti; ok = spti.raise_priority(); "
            "k = spti._kernel32; k.GetPriorityClass.argtypes = [wintypes.HANDLE]; k.GetThreadPriority.argtypes = [wintypes.HANDLE]; "
            "print(ok, k.GetPriorityClass(spti._GetCurrentProcess()), k.GetThreadPriority(spti._GetCurrentThread()))")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root)
    c.check(done.stdout.split() == ["True", "128", "2"], f"measuring really runs at high priority {done.stdout.split()}")


def _plain_errors(c) -> None:
    from . import __main__ as cli
    missing = FileNotFoundError(2, "No such file or directory", "nope.png")
    stopped = OSError(5, "The system cannot locate the file specified.")
    chinese = OSError(2, "\u7cfb\u7edf\u627e\u4e0d\u5230\u6307\u5b9a\u7684\u6587\u4ef6\u3002")
    real_term = ui._term
    try:
        ui._term = ui.Term(io.StringIO(), env={})
        c.check(cli._os_error(missing) == f"error: {missing}" and cli._reason(stopped) == stopped.strerror, "a script sees system errors as it always did")
        ui._term = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
        c.check(cli._os_error(missing) == "no such file: nope.png", "at a terminal a missing file is said plainly")
        c.check(cli._os_error(stopped) == f"error: {stopped}", "other system errors keep their text")
        c.check(cli._reason(stopped) == "The system cannot locate the file specified" and not cli._reason(chinese).endswith("\u3002"), "no doubled full stop")
    finally:
        ui._term = real_term


def _missing_package(c) -> None:
    import subprocess
    import sys
    code = ("import sys; sys.modules['scipy'] = None; from discprobe.__main__ import main; "
            "main(['disexport', '--geo', sys.argv[1]])")
    with tempfile.TemporaryDirectory() as d:
        geo = os.path.join(d, "s.json")
        with open(geo, "w", encoding="utf-8") as f:
            json.dump({"fit": {"u": 180000.0, "v": 5.5, "bit_nm_assumed": 133.3}}, f)
        done = subprocess.run([sys.executable, "-c", code, geo], capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    c.check(done.returncode == 1 and "pip install" in done.stderr and "Traceback" not in done.stderr,
            "a missing package says what to install")


def _preflight(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli
    from .scsi import ScsiResult, Sense

    class Drive:
        name = "X:"

        def __init__(self, profile=None, tray_empty=False):
            self.profile, self.tray_empty = profile, tray_empty

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            if cdb[0] == 0x00:      # TEST UNIT READY
                return ScsiResult(2, b"", Sense(2, 0x3A, 0), 0, 1) if self.tray_empty else ScsiResult(0, b"", None, 0, 1)
            data = bytes(6) + self.profile.to_bytes(2, "big") + bytes(4)
            return ScsiResult(0, data, None, 0, 1)

    args = Namespace(media="dvd", func=cli.cmd_geo, drive=None, sim=None)
    real_term, real_ask, real_drives, real_platform = ui._term, ui.ask, guide.optical_drives, cli.sys.platform
    ui._term = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    try:
        ui.ask = lambda *a, **k: True
        try:
            cli._check_disc(Drive(profile=0x09), args)
            c.check(False, "a CD with DVD settings offers --media cd")
        except cli._Rerun as again:
            c.check(again.extra == ["--media", "cd"], "a CD with DVD settings offers --media cd")
        ui.ask = lambda *a, **k: False
        cli._check_disc(Drive(profile=0x09), args)
        c.check(True, "declining keeps the command as typed")
        cli._check_disc(Drive(profile=0x11), args)
        c.check(True, "a DVD with DVD settings passes")
        try:
            cli._check_disc(Drive(tray_empty=True), args)
            c.check(False, "an empty tray is reported")
        except SystemExit as e:
            c.check(str(e.code) == cli.mmc.NO_DISC, "an empty tray is reported")
        cli.sys.platform = "win32"
        guide.optical_drives = lambda: ["H:"]
        with contextlib.redirect_stdout(io.StringIO()):
            cli._choose_drive(args)
        c.check(args.drive == "H:", "the only drive is used when --drive is left out")
        guide.optical_drives = lambda: []
        args.drive = None
        try:
            cli._choose_drive(args)
            c.check(False, "no drive at all is reported")
        except SystemExit as e:
            c.check("--sim" in str(e.code), "no drive at all is reported")
    finally:
        ui._term, ui.ask, guide.optical_drives, cli.sys.platform = real_term, real_ask, real_drives, real_platform


def _banner(c) -> None:
    from . import banner
    ansi = ANSI
    modes = {"true colour": ui.Term(FakeTty(), env={"TERM": "xterm", "COLORTERM": "truecolor"}, platform="linux"),
             "16 colours": ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"),
             "NO_COLOR": ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux"),
             "no ANSI": ui.Term(FakeTty(), env={}, platform="win32")}
    for name, t in modes.items():
        for columns in (120, 60, 20):
            rows = banner.frame(1.0, t, columns)
            plain = [ansi.sub("", r) for r in rows]
            c.check(all(p.isascii() for p in plain) and all(len(p) < columns for p in plain),
                    f"{name}, {columns} columns: ASCII and fits")
            c.check(("\x1b" in "".join(rows)) == t.color, f"{name}, {columns} columns: escapes only with colour")
    colour = "".join(banner.frame(1.0, modes["true colour"], 120))
    c.check("\x1b[48;2;" in colour and any(g in ansi.sub("", colour) for g in "/\\"), "the disc is coloured spaces with slashes on top")
    c.check("\x1b[4" in "".join(banner.frame(1.0, modes["16 colours"], 120)), "16 colours: the disc uses background colours")
    i18n.use("zh")
    try:
        for columns in (120, 60, 20):
            plain = [ansi.sub("", r) for r in banner.frame(1.0, modes["NO_COLOR"], columns)]
            c.check(all(i18n.display_width(p) < columns for p in plain), f"Chinese, {columns} columns: the screen fits")
    finally:
        i18n.use("en")
    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="100", LINES="30")
    try:
        moved = modes["16 colours"]
        clock = [0.0]
        waits = []

        def wait(seconds):
            waits.append(seconds)
            clock[0] += seconds
        banner.show(moved, pause=wait, now=lambda: clock[0])
        text = moved.stream.getvalue()
        c.check(0 < len(waits) <= banner.SHOW_S / banner.FRAME_S + 1 and text.endswith("\x1b[?25h\n\n"), "the animation runs and gives the cursor back")
        clock[0], waits = 0.0, []

        def slow(seconds):
            waits.append(seconds)
            clock[0] += 0.5
        banner.show(ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"), pause=slow, now=lambda: clock[0])
        c.check(len(waits) == 2, "a slow terminal skips frames and takes no longer")
        turning = modes["NO_COLOR"]
        waits = []
        banner.show(turning, pause=wait, now=lambda: clock[0])
        c.check(waits and not re.search(r"\x1b\[[0-9;]*m", turning.stream.getvalue()), "NO_COLOR: the disc still turns, without colour")
        still = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
        waits = []
        banner.show(still, pause=wait, now=lambda: clock[0])
        c.check(not waits and "\x1b" not in still.stream.getvalue(), "no colour, no motion: one still frame, no escapes")
        os.environ.update(LINES="8")
        low = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
        waits = []
        banner.show(low, pause=wait, now=lambda: clock[0])
        c.check(not waits and "| |__" in low.stream.getvalue() and "\x1b[48" not in low.stream.getvalue(), "a low window gets the title alone")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    pipe = ui.Term(io.StringIO(), env={"TERM": "xterm"}, platform="linux")
    banner.show(pipe)
    c.check(pipe.stream.getvalue() == "", "a pipe gets no banner")


def _picker(c) -> None:
    import contextlib
    import datetime
    import io
    import json
    import os
    import tempfile
    from . import guide, info, picker
    from .sim import SimDrive
    print("results: choosing a geo run")
    with tempfile.TemporaryDirectory() as d:
        def geo(name, sigma, rungs=22, who=None, chi2=1.0, last_lba=2295103):
            folder = os.path.join(d, name)
            os.makedirs(folder)
            fit = {"u": 180000.0, "v": 5.5, "bit_nm_assumed": 133.3, "chi2_per_dof": chi2, "residual_rms_deg": 1.0, "measured_span_mm": [26.0, 54.0]}
            if sigma is not None:
                fit["angle_sigma_measured_span_deg"] = sigma
            with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
                json.dump({"fit": fit, "setup": {"last_lba": last_lba}, "identity": who}, f)
            with open(os.path.join(folder, "targets.csv"), "w", encoding="utf-8") as f:
                f.write("header\n" + "row\n" * rungs)
            return folder
        ritek = {"disc": "RITEKF1", "drive": "HL-DT-ST GH70N", "firmware": "NYA2"}
        mcc = {"disc": "MCC 03RG20", "drive": "HL-DT-ST GH70N", "firmware": "NYA2"}
        best = geo("geo-H-20260101-100000", 0.20, who=ritek)
        fine = geo("geo-H-20260101-110000", 0.48, who=ritek, chi2=3.1)
        noisy = geo("geo-H-20260101-120000", 0.70, who=ritek)
        short = geo("geo-H-20260101-130000", 0.05, rungs=3, who=ritek)
        other = geo("geo-H-20260101-090000", 0.30, who=mcc)
        c.check(guide.latest_geo("dvd", d).path == fine, "--geo latest leaves out a newer run judged too noisy")
        chosen = guide.latest_geo("dvd", d)
        c.check(guide.passed_over(chosen, "dvd", d) == 1, "and counts what it left out, not the stopped one")
        lone = os.path.join(d, "alone")
        os.makedirs(lone)
        only = os.path.join(lone, "geo-H-20260101-100000")
        os.makedirs(only)
        with open(os.path.join(only, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"fit": {"u": 1.0, "v": 1.0, "chi2_per_dof": 1.0, "angle_sigma_measured_span_deg": 0.9}}, f)
        with open(os.path.join(only, "targets.csv"), "w", encoding="utf-8") as f:
            f.write("header\n" + "row\n" * 22)
        c.check(guide.latest_geo("dvd", lone).path == only, "with nothing better, latest still gives the noisy run")
        c.check(guide.scan(d)[1].quality() == "too noisy" and guide.scan(d)[0].quality() == "stopped early", "a run says what it is")

        found = picker.groups(picker.geo_runs(None, d), d)
        c.check([g.disc for g in found] == ["RITEKF1", "MCC 03RG20"], "one group per disc, the most recently measured first")
        c.check(found[0].best() == 0.20, "a group's best leaves out stopped runs")
        runs = found[0].runs
        by = lambda key, rev=False: [r.path for r in picker.sort_runs(runs, key, rev)]
        c.check(by("precision") == [best, fine, noisy, short], "precision: best first, a stopped run last whatever its number")
        c.check(by("precision", True) == [noisy, fine, best, short], "precision the other way, the stopped run still last")
        c.check(by("date") == [noisy, fine, best, short], "date: newest first")
        c.check(by("date", True) == [best, fine, noisy, short], "date the other way")

        p = picker.Picker(found)
        c.check(p.group is None and "RITEKF1" in p.lines(24)[2], "it opens on the list of discs")
        for key in ("down", "up", "\r"):
            p.handle(key)
        c.check(p.group is found[0], "Enter goes into a disc")
        c.check("most precise first" in p.lines(24)[1], "and says how it is sorted")
        p.handle("s")
        c.check(p.key == "date" and p.row == 0 and "newest first" in p.lines(24)[1], "s changes the sort")
        p.handle("r")
        c.check(p.reverse and "oldest first" in p.lines(24)[1], "r turns it round")
        p.handle("s")
        c.check(p.key == "precision" and not p.reverse, "and changing the sort starts from its usual order")
        p.handle("left")
        c.check(p.group is None and p.row == 0, "left goes back to the discs")
        p.handle("\r")
        p.handle("down")
        p.handle("\r")
        c.check(p.done and p.result.path == fine, "Enter chooses the run under the cursor")
        q = picker.Picker(found)
        q.handle("\x1b")
        c.check(q.done and q.result is None, "Esc leaves with nothing chosen")
        single = picker.Picker(found[1:])
        c.check(single.group is found[1], "one disc goes straight to its runs")
        single.handle("left")
        c.check(single.done and single.result is None, "and going back from there leaves")
        tall = picker.Picker(found)
        tall.handle("\r")
        lines = tall.lines(5)
        c.check(len(lines) <= 5 and any(x.startswith("> ") for x in lines), "a short window still shows the cursor")

        plain = "\n".join(picker.plain_lists(found))
        c.check("RITEKF1" in plain and fine in plain and plain.index(best) < plain.index(fine), "without a terminal it prints the same lists")
        try:
            picker.choose(None, d, t=types_term())
            c.check(False, "--geo pick in a pipe is refused")
        except ValueError as e:
            c.check("needs a terminal" in str(e), "--geo pick in a pipe is refused")

        class Keys:
            closed = False

            def __init__(self, presses):
                self.presses = list(presses)

            def read(self):
                return [self.presses.pop(0)] if self.presses else ["q"]

            def close(self):
                Keys.closed = True

        class Screen:
            ansi = True
            stream = io.StringIO()

            def can_prompt(self):
                return True

            def style(self, text, name):
                return text

        screen = Screen()
        got = picker.choose(None, d, t=screen, keys=Keys(["\r", "down", "\r"]), pause=lambda s: None)
        drawn = screen.stream.getvalue()
        c.check(got.path == fine, "scripted keys reach the same run on a terminal")
        c.check(Keys.closed and drawn.startswith("\x1b[?1049h") and drawn.endswith("\x1b[?25h\x1b[?1049l"), "it uses its own screen and restores the cursor")
        c.check(picker.choose(None, d, t=screen, keys=Keys(["q"]), pause=lambda s: None) is None, "q leaves with nothing chosen")
        wide = geo("geo-H-20260103-100000", 0.1, who=mcc)
        with open(os.path.join(wide, "summary.json"), "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["fit"]["measured_span_mm"] = [33.0, 45.0]
            f.seek(0)
            json.dump(data, f)
            f.truncate()
        c.check(guide.scan(d)[0].quality() == "narrow span", "a run over a small part of the disc says so, not good")

        old = os.path.join(d, "old")
        os.makedirs(old)
        run = os.path.join(old, "geo-H-20260102-100000")
        os.makedirs(run)
        with open(os.path.join(run, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"fit": {"u": 1.0, "v": 1.0, "chi2_per_dof": 1.0}, "setup": {"last_lba": 100}}, f)
        for name, last, mid in (("info-H-20260102-090000", 100, "RITEKF1"), ("info-H-20260102-095900", 999, "OTHER"), ("info-H-20260101-090000", 100, "TOOOLD")):
            folder = os.path.join(old, name)
            os.makedirs(folder)
            with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"inquiry": {"parsed": {"vendor": "HL-DT-ST", "product": "GH70N"}}, "capacity": {"parsed": {"last_lba": last}},
                           "dvd_prerecorded_0e": {"parsed": {"manufacturer_id": mid + "\x00\x00"}}}, f)
        who = guide.identity_of(guide.scan(old)[0], guide.info_runs(old))
        c.check(who == {"disc": "RITEKF1", "drive": "HL-DT-ST GH70N", "inferred": True}, "an old run takes the disc from the nearest info with the same length")
        none = guide.identity_of(guide.Result(run, "geo", "Z", "20260102-100000"), guide.info_runs(old))
        c.check(none["disc"] == "unknown disc" and none["drive"] == "drive Z:", "and says so when nothing matches")

    sim = SimDrive("cav")
    got = info.identify(sim, "dvd")
    c.check(set(got) == {"drive", "firmware", "disc"}, "identifying a disc reports drive, firmware and disc")
    args = type("A", (), {"sim": "cav", "media": "dvd"})()
    from .__main__ import _identity
    c.check(_identity(args, sim) is None, "a simulated run records no drive or disc")
    args.sim = None
    c.check(set(_identity(args, sim)) == {"drive", "firmware", "disc"}, "a real one does, before the measuring starts")


def types_term():
    class NoPrompt:
        def can_prompt(self):
            return False
    return NoPrompt()


def run(c) -> None:
    print("terminal layer: capabilities, progress line, games, advice, opening screen, Chinese")
    _preflight(c)
    _banner(c)
    _term_matrix(c)
    _progress_line(c)
    _layout(c)
    _snake(c)
    _reader_changes_nothing(c)
    _status_counts(c)
    _results(c)
    _picker(c)
    _advice(c)
    _command_line(c)
    _missing_package(c)
    _plain_errors(c)
    _no_disc(c)
    _stopped_part_way(c)
    _image_cut_short(c)
    _picture(c)
    _blu_ray(c)
    _priority(c)
    _greetings(c)
    _chinese(c)
    _completion(c)
    _install(c)
    _writing(c)
