"""Fill the Disc, the second game for the wait: blocks of sectors fly in from the right and stack on the left.

A full column is a written track and clears. It runs exactly as snake does, see `snake.py`: no thread,
only inside the random pause before a timed read, its own random generator, only changed cells drawn.
"""

from __future__ import annotations

import random

from .snake import DIRECTIONS, ROWS

MAX_COLS = 18
SLOWEST_STEP_S = 0.4
FASTEST_STEP_S = 0.12
SPEED_UP_PER_POINT_S = 0.01
SHAPES = (
    ((0, 0), (0, 1)),
    ((0, 0), (0, 1), (0, 2)),
    ((0, 0), (1, 0), (0, 1)),
    ((0, 0), (0, 1), (0, 2), (0, 3)),
    ((0, 0), (1, 0), (0, 1), (1, 1)),
    ((0, 0), (0, 1), (0, 2), (1, 2)),
    ((0, 0), (0, 1), (0, 2), (1, 1)),
)
BLOCK_KINDS = tuple(f"block{i}" for i in range(6))
# When a turned block no longer fits where it is, the nearest place it does fit.
TURN_NUDGES = ((0, 0), (0, -1), (0, 1), (0, -2), (0, 2), (-1, 0), (-2, 0), (-3, 0))


def _turned(shape) -> tuple:
    cells = [(y, -x) for x, y in shape]
    low_x, low_y = min(x for x, _ in cells), min(y for _, y in cells)
    return tuple((x - low_x, y - low_y) for x, y in cells)


class FillDisc:
    name = "Fill the Disc"
    max_cols = MAX_COLS

    def __init__(self, cols: int = MAX_COLS, rows: int = ROWS, rng=None):
        self.cols, self.rows = cols, rows
        self.rng = rng or random.Random()
        self.best = 0
        self.reset()

    def reset(self) -> None:
        self.burned: dict[tuple[int, int], str] = {}
        self.kind = None
        self.score = 0
        self.over = False
        self._next_block()

    @property
    def step_s(self) -> float:
        return max(FASTEST_STEP_S, SLOWEST_STEP_S - SPEED_UP_PER_POINT_S * self.score)

    def hint(self) -> str:
        if self.over:
            return f"Fill the Disc {self.score}  best {self.best}  disc full: r plays again, n next, q closes"
        return f"Fill the Disc {self.score}  best {self.best}  up/down, right spin, left drop, n next, q closes"

    def _cells(self, shape=None, x=None, y=None) -> list[tuple[int, int]]:
        shape, x, y = shape or self.shape, self.x if x is None else x, self.y if y is None else y
        return [(x + dx, y + dy) for dx, dy in shape]

    def _fits(self, cells) -> bool:
        return all(0 <= x < self.cols and 0 <= y < self.rows and (x, y) not in self.burned for x, y in cells)

    def _next_block(self) -> None:
        self.shape = self.rng.choice(SHAPES)
        self.kind = self.rng.choice([k for k in BLOCK_KINDS if k != self.kind])     # two in a row never look alike
        self.x = self.cols - 1 - max(x for x, _ in self.shape)
        self.y = (self.rows - 1 - max(y for _, y in self.shape)) // 2
        if not self._fits(self._cells()):
            self.over = True
            self.best = max(self.best, self.score)

    def _land(self) -> None:
        self.burned.update(dict.fromkeys(self._cells(), self.kind))
        full = [x for x in range(self.cols) if all((x, y) in self.burned for y in range(self.rows))]
        self.burned = {(x - sum(f < x for f in full), y): kind for (x, y), kind in self.burned.items() if x not in full}
        self.score += len(full)
        self.best = max(self.best, self.score)
        self._next_block()

    def _fall(self) -> None:
        if self._fits(self._cells(x=self.x - 1)):
            self.x -= 1
        else:
            self._land()

    def _shift(self, dy: int) -> None:
        if self._fits(self._cells(y=self.y + dy)):
            self.y += dy

    def _spin(self) -> None:
        shape = _turned(self.shape)
        for dx, dy in TURN_NUDGES:
            if self._fits(self._cells(shape, self.x + dx, self.y + dy)):
                self.shape, self.x, self.y = shape, self.x + dx, self.y + dy
                return

    def _changes(self, move) -> list[tuple[int, int, str]]:
        """Run `move` and return the cells it changed as (x, y, a block kind or "field")."""
        before = {(x, y): self.cell(x, y) for x in range(self.cols) for y in range(self.rows)}
        move()
        return [(x, y, self.cell(x, y)) for (x, y), kind in before.items() if self.cell(x, y) != kind]

    def step(self) -> list[tuple[int, int, str]]:
        return [] if self.over else self._changes(self._fall)

    def turn(self, name: str) -> list[tuple[int, int, str]]:
        """Up and down move the block, left drops it a column, right spins it. It shows at once, unlike a step."""
        if self.over:
            return []
        if name == "left":
            return self._changes(self._fall)
        if name == "right":
            return self._changes(self._spin)
        return self._changes(lambda: self._shift(DIRECTIONS[name][1]))

    def cell(self, x: int, y: int) -> str:
        if (x, y) in self.burned:
            return self.burned[(x, y)]
        return self.kind if not self.over and (x, y) in self._cells() else "field"
