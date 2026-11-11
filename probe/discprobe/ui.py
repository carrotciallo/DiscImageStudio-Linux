"""Terminal help for people typing commands: hints, colours and a progress line.

All of it is off unless stdout is a real terminal, so pipes, redirects and agents get the
plain output they always had (DISCPROBE_PLAIN=1 turns it off in a terminal too). 7-bit ASCII is
the default, because a UTF-8 encoding says nothing about the font; DISCPROBE_UNICODE=1 asks for
finer glyphs. Colour needs ANSI, and the progress line needs nothing but a carriage return.
Animation is a function of the clock, never of how often something was drawn, because reads
come at an uneven pace; each animated thing has a still form for --no-animation.
"""

from __future__ import annotations

import atexit
import colorsys
import contextlib
import os
import re
import shutil
import sys
import threading
import time

from . import filldisc, i18n, iso9660, snake
from .i18n import display_width, tr

SPINNER_ASCII = ("(|)", "(/)", "(-)", "(\\)")
SPINNER_UNICODE = ("◐", "◓", "◑", "◒")     # a disc turning
SPINNER_FRAME_S = 0.12
BAR_ASCII = ("=", ">", ".")
BAR_UNICODE = ("━", "╸", "─")
STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "cyan": "36", "flash": "1;36"}
PERCENT_FLASH_S = 0.4
BAR_WIDTH = 20
ANIMATED_FPS = 8.0
PLAIN_FPS = 1.0
# Drawing outside the random pause delays the next command, so keep it rare there.
OUTSIDE_PAUSE_INTERVAL_S = 1.0
SWEEP_S = 1.7
SWEEP_REACH = 4.0
BAR_COLOUR_CELLS = 4        # the bar's rainbow changes in steps, which keeps each frame small
GAMES = (snake.Snake, filldisc.FillDisc)
GAME_GLYPHS = {"field": "..", "snake": "##", "food": "<>",
               "block0": "[]", "block1": "##", "block2": "()", "block3": "{}", "block4": "%%", "block5": "@@"}
GAME_CELLS = {"field": ("48;2;42;46;56", "100"), "snake": ("48;2;86;200;130", "42"), "food": ("48;2;236;96;96", "41"),
              "block0": ("48;2;236;96;96", "41"), "block1": ("48;2;86;200;130", "42"), "block2": ("48;2;250;190;70", "43"),
              "block3": ("48;2;96;124;230", "44"), "block4": ("48;2;200;110;220", "45"), "block5": ("48;2;70;200;220", "46")}


def _windows_ansi(stream) -> bool:
    """Turn on VT escape processing; False on consoles too old to have it."""
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = wintypes.DWORD()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        original = mode.value
        if original & 0x0004:
            return True
        if not k32.SetConsoleMode(handle, original | 0x0004):
            return False

        def restore():      # the shell gets its console back as it was
            stream.flush()
            k32.SetConsoleMode(handle, original)
        atexit.register(restore)
        return True
    except (OSError, ValueError, AttributeError, ImportError):
        return False


def _isatty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


class Term:
    """What this output stream can do. `interactive` gates every extra line we print."""

    def __init__(self, stream=None, env=None, platform=None):
        self.stream = stream if stream is not None else sys.stdout
        env = os.environ if env is None else env
        platform = platform or sys.platform
        self.interactive = _isatty(self.stream) and not env.get("DISCPROBE_PLAIN") and env.get("TERM") != "dumb"
        if not self.interactive:
            self.ansi = False
        elif platform == "win32":
            self.ansi = _windows_ansi(self.stream)
        else:
            self.ansi = bool(env.get("TERM"))
        self.color = self.ansi and not env.get("NO_COLOR")
        self.animate = self.ansi and not env.get("CI") and not env.get("DISCPROBE_NO_ANIMATION")
        self.truecolor = self.color and (env.get("COLORTERM", "") in ("truecolor", "24bit") or bool(env.get("WT_SESSION")))
        # Few terminals say what is behind the text. Told it is dark, use bright green; otherwise
        # the theme's own green, which its author made readable on that theme.
        background = env.get("COLORFGBG", "").rpartition(";")[2]
        self.green = "92" if background.isdigit() and int(background) not in (7, 15) else "32"
        utf8 = (getattr(self.stream, "encoding", None) or "").lower().replace("-", "") == "utf8"
        self.unicode = self.ansi and utf8 and bool(env.get("DISCPROBE_UNICODE"))

    def style(self, text: str, name: str) -> str:
        return f"\x1b[{STYLES[name]}m{text}\x1b[0m" if self.color else text

    def can_prompt(self) -> bool:
        return self.interactive and _isatty(sys.stdin)


_term = None


def term() -> Term:
    global _term
    if _term is None:
        _term = Term()
    return _term


def clock(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 \
        else f"{seconds // 60}:{seconds % 60:02d}"


def say(text: str = "", style: str | None = None) -> None:
    """A line only people at a terminal see."""
    t = term()
    if t.interactive:
        text = tr(text)
        print(t.style(text, style) if style else text, flush=True)


def ask(question: str, default: bool = True) -> bool:
    """Yes or no at the terminal; the default wherever nobody can answer."""
    if not term().can_prompt():
        return default
    try:
        answer = input(f"{tr(question)} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    except EOFError:
        return default
    return answer.startswith("y") if answer else default


def _rainbow(position: float, saturation: float = 0.8) -> str:
    r, g, b = (int(255 * v) for v in colorsys.hsv_to_rgb(position % 1.0, saturation, 0.85))
    return f"38;2;{r};{g};{b}"


def _paint_runs(cells: list[tuple[str, str]]) -> str:
    """(code, text) cells to one string, one escape per run of equal codes."""
    out, run_code, run = [], "", []
    for code, text in cells + [("", "")]:
        if code != run_code:
            joined = "".join(run)
            out.append(f"\x1b[{run_code}m{joined}\x1b[0m" if run_code else joined)
            run_code, run = code, []
        run.append(text)
    out.append("".join(run))
    return "".join(out)


def sweep(text: str, now: float, t: Term, base: str | None = None) -> str:
    """Text with a band of the disc's rainbow crossing it; the band is the only thing that moves.

    Between sweeps the text keeps the terminal's own colour, so it stays readable on any theme.
    """
    if not (t.animate and t.color) or not text:
        return t.style(text, base) if base else text
    columns = display_width(text)
    position = (now % SWEEP_S) / SWEEP_S * (columns + 2 * SWEEP_REACH) - SWEEP_REACH
    rest = STYLES[base] if base else ""
    cells, column = [], 0
    for ch in text:
        light = max(0.0, 1 - abs(column - position) / SWEEP_REACH)
        if light <= 0:
            code = rest
        elif t.truecolor:
            code = _rainbow((column // 2) * 2 / max(columns, 1) * 0.7 + now * 0.08, 0.45 + 0.45 * round(light * 2) / 2)
        else:
            code = "1;36" if light > 0.45 else rest
        cells.append((code, ch))
        column += display_width(ch)
    return _paint_runs(cells)


class Progress:
    """One line that overwrites itself; `status` returns (fraction or None, label, seconds left or None).

    A narrow terminal loses whole parts, least useful first, and never gets a wrapped line.
    With `keys` given, a game can be opened under it.
    """

    def __init__(self, status, t: Term | None = None, keys=None):
        self.t = t or term()
        self.status = status
        self.started = time.monotonic()
        self.last_draw = 0.0
        self.width_shown = 0
        self.line_shown = None
        self.percent_shown = None
        self.percent_lit = set()
        self.percent_changed = 0.0
        self.interval = 1 / (ANIMATED_FPS if self.t.animate else PLAIN_FPS)
        self.closed = False
        self.keys = keys
        self.game = None        # the one on show; `games` keeps each one's board and best score
        self.games = {}
        self.game_kind = 0
        self.playing = False
        self.last_step = 0.0
        self.game_size = None
        if self.t.ansi:
            self.t.stream.write("\x1b[?25l")
        if self.t.ansi or keys:
            atexit.register(self.close)

    def _spinner(self, now: float) -> str:
        frames = SPINNER_UNICODE if self.t.unicode else SPINNER_ASCII
        return frames[int((now - self.started) / SPINNER_FRAME_S) % len(frames)]

    def _bar(self, fraction: float, now: float) -> tuple[str, str]:
        """The bar as plain text and as painted text."""
        fill, head, rest = BAR_UNICODE if self.t.unicode else BAR_ASCII
        filled = int(fraction * BAR_WIDTH)
        tip = head if filled < BAR_WIDTH else ""
        tail = rest * (BAR_WIDTH - filled - len(tip))
        plain = f"[{fill * filled}{tip}{tail}]"
        if not self.t.color:
            return plain, plain
        if self.t.truecolor:
            done = _paint_runs([(_rainbow((i // BAR_COLOUR_CELLS) * BAR_COLOUR_CELLS / BAR_WIDTH * 0.75), fill) for i in range(filled)])
        else:
            done = self.t.style(fill * filled, "cyan")
        return plain, "[" + done + (self.t.style(tip, "cyan") if tip else "") + (self.t.style(tail, "dim") if tail else "") + "]"

    def _percent(self, fraction: float, now: float) -> tuple[str, str]:
        """The percentage as plain and painted text: a digit that just changed flashes, and 100% stays green.

        Rounded down, so it only reads 100% when the work is done.
        """
        text = f"{int(fraction * 100 + 1e-9):3d}%"
        if text != self.percent_shown:
            old = self.percent_shown or text    # the first value is news to nobody
            self.percent_lit = {i for i, (a, b) in enumerate(zip(old, text)) if a != b}
            self.percent_changed = now
            self.percent_shown = text
        if not self.t.color:
            return text, text
        if text == "100%":
            return text, f"\x1b[{self.t.green}m{text}\x1b[0m"
        if self.t.animate and now - self.percent_changed < PERCENT_FLASH_S:
            return text, _paint_runs([(STYLES["flash"] if i in self.percent_lit else "", ch) for i, ch in enumerate(text)])
        return text, text

    def _render(self, columns: int | None = None) -> tuple[str, int]:
        columns = columns if columns is not None else shutil.get_terminal_size((80, 24)).columns
        room = max(10, columns - 1)
        now = time.monotonic()
        fraction, label, left = self.status()
        label = tr(label)
        spin = [(self._spinner(now), self.t.style(self._spinner(now), "cyan"))] if self.t.animate else []
        meter = []
        if fraction is not None:
            fraction = max(0.0, min(1.0, fraction))
            meter = [self._bar(fraction, now), self._percent(fraction, now)]
        percent = meter[1:]
        title = [(label, sweep(label, now, self.t))]
        elapsed = clock(now - self.started)
        spent = [(elapsed, self.t.style(elapsed, "dim"))]
        due = []
        if left is not None:
            text = tr(f"about {clock(left)} left")
            due = [(text, text)]
        stop = tr("Ctrl+C to stop")
        stop_part = [(stop, self.t.style(stop, "dim"))]
        game_part = []
        if self.keys and not self.playing:
            text = tr("g: game")
            game_part = [(text, self.t.style(text, "dim"))]
        for parts in (spin + meter + title + spent + due + stop_part + game_part,
                      spin + meter + title + spent + due + game_part,
                      spin + meter + title + spent + due,
                      spin + meter + title + due,
                      spin + percent + title + due,
                      spin + percent + title,
                      spin + title):
            width = sum(display_width(p[0]) for p in parts) + 2 * (len(parts) - 1)
            if width <= room:
                return "  ".join(p[1] for p in parts), width
        cut = i18n.fit(label, room)
        return cut, display_width(cut)

    def tick(self, force: bool = False, interval: float | None = None) -> None:
        if self.closed:
            return
        now = time.monotonic()
        if not force and now - self.last_draw < (interval if interval is not None else self.interval):
            return
        self.last_draw = now
        line, width = self._render()
        if line == self.line_shown:
            return
        self.line_shown = line
        if self.t.ansi:     # with wrapping off a miscounted glyph is clipped, not pushed to a new row
            self.t.stream.write(f"\r\x1b[?7l{line}\x1b[K\x1b[?7h")
        else:
            self.t.stream.write("\r" + line + " " * max(0, self.width_shown - width))
        self.t.stream.flush()
        self.width_shown = width

    def _wipe(self) -> None:
        self.line_shown = None
        if self.playing:
            self.t.stream.write("\r\x1b[J")
        elif self.t.ansi:
            self.t.stream.write("\r\x1b[K")
        elif self.width_shown:
            self.t.stream.write("\r" + " " * self.width_shown + "\r")
        self.width_shown = 0

    def log(self, *parts) -> None:
        """Print a line above the progress line."""
        self._wipe()
        print(tr(" ".join(str(p) for p in parts)), file=self.t.stream, flush=True)
        if self.playing:
            self._draw_game()
        self.tick(force=True)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._wipe()
        self.playing = False
        if self.keys:
            self.keys.close()
        if self.t.ansi:
            self.t.stream.write("\x1b[?25h")
        for game in self.games.values():
            if game.best:
                print(tr(f"{game.name}: best score {game.best}"), file=self.t.stream)
        self.t.stream.flush()

    # The game below is reached only from `play`, inside the pause before a timed read.

    def play(self) -> None:
        if not self.keys or self.closed:
            return
        for key in self.keys.read():
            self._press(snake.key_name(key))
        if self.playing and shutil.get_terminal_size((80, 24)) != self.game_size:
            self._wipe()        # a resize moves everything: draw it afresh, or close if it no longer fits
            self.playing = False
            self._open_game()
        now = time.monotonic()
        if self.playing and not self.game.over and now - self.last_step >= self.game.step_s:
            self.last_step = now
            self._advance(self.game.step)

    def _advance(self, move) -> None:
        score = self.game.score
        self._draw_cells(move() or [])
        if self.game.score != score or self.game.over:
            self._draw_hint()
        self.t.stream.flush()

    def _press(self, key: str) -> None:
        if not self.playing:
            if key in ("g", "G"):
                self._open_game()
            return
        if key in ("q", "Q"):
            self._wipe()
            self.playing = False
            self.tick(force=True)
        elif key in ("n", "N"):
            self.game_kind = (self.game_kind + 1) % len(GAMES)
            self._wipe()
            self.playing = False
            self._open_game()
        elif key in ("r", "R") and self.game.over:
            self.game.reset()
            self._draw_game()
        elif key in snake.DIRECTIONS:
            self._advance(lambda: self.game.turn(key))

    def _open_game(self) -> None:
        size = shutil.get_terminal_size((80, 24))
        kind = GAMES[self.game_kind]
        cols = min(kind.max_cols, (size.columns - 4) // 2)
        if cols < snake.MIN_COLS or size.lines < snake.ROWS + 4:
            self.log("The window is too small for the game")
            return
        kept = self.games.get(kind)
        if kept is None or kept.cols != cols:
            self.games[kind] = kind(cols)
            self.games[kind].best = kept.best if kept else 0
        self.game = self.games[kind]
        self.playing = True
        self.game_size = size
        self.last_step = time.monotonic()
        self._draw_game()
        self.tick(force=True)

    def _cell(self, kind: str) -> str:
        if not self.t.color:
            return GAME_GLYPHS[kind]
        rgb, ansi16 = GAME_CELLS[kind]
        return f"\x1b[{rgb if self.t.truecolor else ansi16}m  \x1b[0m"

    def _below(self, rows: int, text: str) -> str:
        return f"\x1b[{rows}B{text}\x1b[{rows}A\r"

    def _draw_hint(self) -> None:
        text = i18n.fit(tr(self.game.hint()), self.game_size.columns - 3)
        self.t.stream.write(self._below(1, f"\r\x1b[K  {self.t.style(text, 'dim')}"))

    def _draw_cells(self, changed) -> None:
        for x, y, kind in changed:
            self.t.stream.write(self._below(2 + y, f"\x1b[{3 + 2 * x}G{self._cell(kind)}"))

    def _draw_game(self) -> None:
        """Make room below the progress line (scrolling if at the bottom), then draw all of it."""
        below = snake.ROWS + 1
        self.t.stream.write("\n" * below + f"\x1b[{below}A\r")
        self._draw_hint()
        g = self.game
        for y in range(g.rows):
            row = "".join(self._cell(g.cell(x, y)) for x in range(g.cols))
            self.t.stream.write(self._below(2 + y, f"\r  {row}\x1b[K"))
        self.t.stream.flush()


def open_keys(t: Term | None = None):
    """Keys for the game, where it can be played: it needs motion and someone at the keyboard."""
    t = t or term()
    return snake.open_keys() if t.animate and t.can_prompt() else None


class ProgressDevice:
    """A drive wrapper that draws the progress line from the measuring thread, between reads.

    There is no animation thread on purpose. ctypes drops the GIL during the ioctl, and a thread
    holding it when the read returns delays the completion timestamp by up to the 5 ms switch
    interval, far above the tens of microseconds being measured. Drawing happens in the random
    pause before each timed read instead: that wait is arbitrary by design and the time spent
    drawing is taken off it. Outside it (setup, cache test) it draws at most once a second.
    """

    def __init__(self, dev):
        self._dev = dev
        self.progress: Progress | None = None
        self.pauses = 0     # one per timed read

    def __getattr__(self, name):
        return getattr(self._dev, name)

    def execute(self, *args, **kwargs):
        res = self._dev.execute(*args, **kwargs)
        if self.progress:
            self.progress.tick(interval=OUTSIDE_PAUSE_INTERVAL_S)
        return res

    def idle(self, seconds: float) -> None:
        start = time.perf_counter()
        self.pauses += 1
        if self.progress:
            self.progress.play()
            self.progress.tick()
        if hasattr(self._dev, "idle"):      # the simulator's clock is virtual
            self._dev.idle(seconds)
            return
        rest = seconds - (time.perf_counter() - start)
        if rest > 0:
            time.sleep(rest)


class _Rate:
    """Seconds left from planned work, once enough of it has been timed."""

    MIN_DONE = 8

    def __init__(self):
        self.start = None
        self.done_at_start = 0.0

    def left(self, done: float, total: float) -> float | None:
        now = time.monotonic()
        if self.start is None:
            self.start, self.done_at_start = now, done
            return None
        finished = done - self.done_at_start
        return (now - self.start) / finished * (total - done) if finished >= self.MIN_DONE else None


def timing_status(probe, dev: ProgressDevice):
    """Progress of `timing`. Spin-up has no known length, so the bar counts the timed reads after it."""
    planned = 3 * probe.period_reads + 2 * probe.reps * len(probe.targets)
    names = {"": "starting", "setup": "reading the disc", "warmup": "warming up", "cache": "cache test",
             "settle": "waiting for a steady spindle"}
    marks: dict[str, int] = {}
    rate = _Rate()

    def status():
        stage = probe._experiment
        marks.setdefault(stage, dev.pauses)
        if stage == "phase":    # no line may have been drawn during the rotation test
            marks.setdefault("period", marks["phase"] - 3 * probe.period_reads)
        if stage not in ("period", "phase"):
            return None, names.get(stage, stage), None
        period_done = (marks["phase"] if "phase" in marks else dev.pauses) - marks["period"]
        phase_done = dev.pauses - marks["phase"] if "phase" in marks else 0
        done = period_done + phase_done
        if stage == "period":
            label = f"rotation test, zone {min(period_done // max(probe.period_reads, 1) + 1, 3)}/3"
        else:
            per_target = max(2 * probe.reps, 1)
            label = f"phase test, target {min(phase_done // per_target + 1, len(probe.targets))}/{len(probe.targets)}"
        return done / planned, label, rate.left(done, planned)
    return status


def geo_status(ladder, dev: ProgressDevice):
    """Progress of `geo`, in rungs of the ladder. A retried rung takes longer, so the time left is a guess."""
    per_rung = max(2 * ladder.reps, 1)
    rate = _Rate()
    state = {"rungs": -1, "mark": 0}

    def status():
        rungs = len(ladder.targets)
        if getattr(ladder, "T", None) is None:
            stage = "cache test" if not hasattr(ladder, "ref") else "waiting for a steady spindle"
            done = rungs / max(ladder.max_targets, 1)
            return (done if rungs else None), f"rung {rungs}/{ladder.max_targets}: {stage}" if rungs else stage, None
        if rungs != state["rungs"]:
            state.update(rungs=rungs, mark=dev.pauses)
        current = min((dev.pauses - state["mark"]) / per_rung, 1.0)
        done = (rungs + current) * per_rung
        total = ladder.max_targets * per_rung
        label = f"rung {min(rungs + 1, ladder.max_targets)}/{ladder.max_targets}"
        return done / total, label, rate.left(done, total)
    return status


@contextlib.contextmanager
def _animated(status):
    """A progress line with its own drawing thread, for work where no timing is being measured."""
    t = term()
    progress = Progress(status, t)
    lock = threading.Lock()
    stop = threading.Event()

    def draw():
        while not stop.wait(progress.interval):
            with lock:
                progress.tick()
    thread = threading.Thread(target=draw, daemon=True)
    thread.start()
    with lock:
        progress.tick(force=True)

    def log(*parts):
        with lock:
            progress.log(*parts)
    try:
        yield log, progress
    finally:
        stop.set()
        thread.join(1.0)
        progress.close()


def _file_stamp(path: str):
    try:
        status = os.stat(path)
        return status.st_size, status.st_mtime_ns
    except OSError:
        return None


def _remove(path: str) -> bool:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


@contextlib.contextmanager
def _whole_or_gone(path: str):
    """An image cut short must not pass for a finished one, since it may get burned.

    If the write fails or is stopped, what it left goes. A file it never touched stays: a check can fail before
    the writer opens anything. A killed process or closed window cleans up nothing, so a marker beside the
    image says it isn't whole, for `guide` and for the next write.
    """
    marker = path + iso9660.UNFINISHED
    if os.path.exists(marker) and _remove(path):
        _remove(marker)
    before = _file_stamp(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(marker, "w", encoding="utf-8"):
            pass
    except OSError:
        pass        # the writer will say what is wrong with this folder
    try:
        yield
    except BaseException:
        if _file_stamp(path) == before:
            _remove(marker)
        elif _remove(path):     # if it can't be removed, the marker stays and still says so
            _remove(marker)
            say("The unfinished image was removed.")
        raise
    _remove(marker)


@contextlib.contextmanager
def writing(path: str, sectors: int):
    """`log` for the ISO writers. At a terminal their percentage lines become a progress line.

    The writers report only every 10 or 20 %, so between reports the bar follows the file's real
    size. Only a report can say 100 %. Pipes get the writers' lines as they always did.
    """
    with _whole_or_gone(path):
        if not term().interactive:
            yield print
            return
        with _writing_line(path, sectors) as log:
            yield log


@contextlib.contextmanager
def _writing_line(path: str, sectors: int):
    total = max(sectors * 2048, 1)
    reported = [0.0]
    rate = _Rate()

    def status():
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        fraction = max(reported[0], min(size / total, 0.99))
        return fraction, "writing the image", rate.left(fraction * 1000, 1000)
    with _animated(status) as (show, progress):
        def log(message):
            match = re.search(r"([\d.]+) %", message)
            if match:
                reported[0] = float(match.group(1)) / 100
            else:
                show(message)
        yield log
    say(f"Finished in {clock(time.monotonic() - progress.started)}", "dim")


@contextlib.contextmanager
def busy(label: str):
    """A turning disc and a label for work of unknown length. Pipes see nothing."""
    if not term().interactive:
        yield
        return
    with _animated(lambda: (None, label, None)):
        yield
