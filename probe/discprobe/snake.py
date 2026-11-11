"""A game of snake to pass the wait, opened with a key while a drive is being measured.

It lives under the progress line and never covers text. It has no thread: `ui.Progress.play`
polls the keys and moves the snake only inside the random pause before a timed read, and draws
only the cells that changed. It has its own random generator, so the measurement's stay untouched.
"""

from __future__ import annotations

import os
import random
import sys

ROWS = 8
MAX_COLS = 24
MIN_COLS = 12
STEP_S = 0.15
DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
LETTERS = {"w": "up", "s": "down", "a": "left", "d": "right", "h": "left", "j": "down", "k": "up", "l": "right"}
CSI_ARROWS = {"A": "up", "B": "down", "D": "left", "C": "right"}
WIN_ARROWS = {"H": "up", "P": "down", "K": "left", "M": "right"}


class Snake:
    name = "Snake"
    max_cols = MAX_COLS
    step_s = STEP_S

    def __init__(self, cols: int = MAX_COLS, rows: int = ROWS, rng=None):
        self.cols, self.rows = cols, rows
        self.rng = rng or random.Random()
        self.best = 0
        self.reset()

    def reset(self) -> None:
        y = self.rows // 2
        self.body = [(x, y) for x in range(3, 0, -1)]     # head first
        self.heading = (1, 0)
        self.queued: list[tuple[int, int]] = []
        self.score = 0
        self.over = False
        self.food = None
        self._place_food()

    def hint(self) -> str:
        if self.over:
            return f"Snake {self.score}  best {self.best}  crashed: r plays again, n next, q closes"
        return f"Snake {self.score}  best {self.best}  arrows or WASD steer, n next, q closes"

    def _place_food(self) -> None:
        free = [(x, y) for x in range(self.cols) for y in range(self.rows) if (x, y) not in self.body]
        self.food = self.rng.choice(free) if free else None

    def turn(self, name: str) -> None:
        """Keys pressed between two steps are kept, so a quick U-turn works; a reversal is ignored."""
        new = DIRECTIONS[name]
        last = self.queued[-1] if self.queued else self.heading
        if new != last and new != (-last[0], -last[1]) and len(self.queued) < 2:
            self.queued.append(new)

    def step(self) -> list[tuple[int, int, str]]:
        """Move once; returns the cells that changed as (x, y, "snake" | "food" | "field")."""
        if self.over:
            return []
        if self.queued:
            self.heading = self.queued.pop(0)
        x, y = self.body[0][0] + self.heading[0], self.body[0][1] + self.heading[1]
        eats = (x, y) == self.food
        body = self.body if eats else self.body[:-1]
        if not (0 <= x < self.cols and 0 <= y < self.rows) or (x, y) in body:
            self.over = True
            self.best = max(self.best, self.score)
            return []
        changed = [(x, y, "snake")]
        if eats:
            self.score += 1
            self.best = max(self.best, self.score)
            self.body.insert(0, (x, y))
            self._place_food()
            if self.food:
                changed.append((*self.food, "food"))
        else:
            changed.append((*self.body[-1], "field"))
            self.body = [(x, y)] + body
        return changed

    def cell(self, x: int, y: int) -> str:
        return "snake" if (x, y) in self.body else "food" if (x, y) == self.food else "field"


def parse_posix(data: str) -> list[str]:
    keys, i = [], 0
    while i < len(data):
        if data[i] == "\x1b" and data[i + 1:i + 2] in ("[", "O") and data[i + 2:i + 3] in CSI_ARROWS:
            keys.append(CSI_ARROWS[data[i + 2]])
            i += 3
        else:
            keys.append(data[i])
            i += 1
    return keys


class WindowsKeys:
    def __init__(self):
        import msvcrt
        self.msvcrt = msvcrt

    def read(self) -> list[str]:
        keys = []
        while self.msvcrt.kbhit():
            ch = self.msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                keys.append(WIN_ARROWS.get(self.msvcrt.getwch(), ""))
            else:
                keys.append(ch)
        return keys

    def close(self) -> None:
        pass


class PosixKeys:
    """Keys without Enter or echo. Ctrl+C still raises KeyboardInterrupt; close() restores the terminal."""

    def __init__(self):
        import select
        import termios
        import tty
        self.select, self.termios = select, termios
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def read(self) -> list[str]:
        data = b""
        while self.select.select([self.fd], [], [], 0)[0]:
            chunk = os.read(self.fd, 64)
            if not chunk:
                break
            data += chunk
        return parse_posix(data.decode("ascii", "ignore"))

    def close(self) -> None:
        self.termios.tcsetattr(self.fd, self.termios.TCSANOW, self.saved)


def open_keys():
    """A key reader, or None where keys cannot be polled."""
    try:
        return WindowsKeys() if sys.platform == "win32" else PosixKeys()
    except Exception:       # includes termios.error; the game is never worth stopping a measurement for
        return None


def key_name(key: str) -> str:
    return LETTERS.get(key.lower(), key)
