"""EFMPlus modulation with DSV control, one 91-byte sync frame at a time.

A port of DiscImageStudio's EfmPlusEncoder (GPL-3.0-or-later, commit 46fa699), which
implements ECMA-267: SYNC primary/secondary choice, main/substitution choice for bytes
0..87, state 1/4 alternatives for bytes 88..255, and the smaller-|DSV| stream wins
(ties go to stream 1). Levels are 1 = land, 0 = pit; DSV counts land +1, pit -1.

Used to predict what a burner records for given scrambled-domain bytes Q, in particular
how far pit/land coverage can be pushed away from 50 % before DSV control pulls it back.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .efmplus_tables import MAIN_NEXT, MAIN_WORDS, SUB_NEXT, SUB_WORDS

BYTES_PER_FRAME = 91
BITS_PER_FRAME = 1488

# [state group (1/2 -> 0, 3/4 -> 1)][primary -> 0, secondary -> 1][category SY0..SY7]
SYNC = (
    ((0x12440011, 0x04040011, 0x10040011, 0x08040011, 0x20040011, 0x22440011, 0x24840011, 0x24440011),
     (0x12040011, 0x04440011, 0x10440011, 0x08440011, 0x20440011, 0x22040011, 0x20840011, 0x24040011)),
    ((0x92040011, 0x84440011, 0x90440011, 0x82440011, 0x88440011, 0x89040011, 0x90840011, 0x88840011),
     (0x92440011, 0x84040011, 0x90040011, 0x82040011, 0x88040011, 0x81040011, 0x80440011, 0x80840011)),
)

# Sync categories of the two sync frames in each of a sector's 13 rows (ECMA-267).
ROW_SYNC = ((0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (1, 6), (2, 6), (3, 6), (4, 6),
            (1, 7), (2, 7), (3, 7), (4, 7))


@dataclass(frozen=True)
class Boundary:
    state: int = 1
    dsv: int = 0
    land: bool = True


def main(value: int, state: int) -> tuple[int, int]:
    i = value * 4 + state - 1
    return MAIN_WORDS[i], MAIN_NEXT[i]


def sub(value: int, state: int) -> tuple[int, int]:
    i = value * 4 + state - 1
    return SUB_WORDS[i], SUB_NEXT[i]


def sync_word(state: int, category: int, primary: bool) -> int:
    return SYNC[0 if state <= 2 else 1][0 if primary else 1][category]


class _Stream:
    __slots__ = ("bits", "state", "dsv", "land", "primary", "zeros")

    def __init__(self, b: Boundary, sync: int, primary: bool):
        self.bits: list[int] = []
        self.state, self.dsv, self.land, self.primary, self.zeros = b.state, b.dsv, b.land, primary, 0
        self._put(sync, 32)
        self.state = 1  # every SYNC code ends in a one

    def copy_from(self, o: "_Stream") -> None:
        self.bits = list(o.bits)
        self.state, self.dsv, self.land, self.primary, self.zeros = o.state, o.dsv, o.land, o.primary, o.zeros

    def _put(self, word: int, n: int) -> None:
        for k in range(n - 1, -1, -1):
            t = (word >> k) & 1
            self.bits.append(t)
            if t:
                self.land = not self.land
                self.zeros = 0
            else:
                self.zeros += 1
            self.dsv += 1 if self.land else -1

    def can(self, word: int) -> bool:
        lead = 16 - word.bit_length()
        return 2 <= self.zeros + lead <= 10

    def append(self, wn: tuple[int, int]) -> None:
        if not self.can(wn[0]):
            raise ValueError("EFMPlus word would violate RLL(2,10)")
        self._put(wn[0], 16)
        self.state = wn[1]


def _select(a: _Stream, b: _Stream) -> _Stream:
    return a if abs(a.dsv) <= abs(b.dsv) else b


def _two_reps(value: int, s: _Stream) -> bool:
    return s.state in (1, 4) and s.can(main(value, 1)[0]) and s.can(main(value, 4)[0])


def _replay(bits, b: Boundary) -> tuple[np.ndarray, int, bool]:
    t = np.asarray(bits, dtype=np.uint8)
    level = (np.cumsum(t) + (1 if b.land else 0)) % 2  # 1 = land; each one toggles
    dsv = b.dsv + 2 * int(level.sum()) - int(level.size)
    return level.astype(np.uint8), dsv, bool(level[-1])


def encode_frame(data: bytes | np.ndarray, category: int, b: Boundary) -> tuple[np.ndarray, Boundary]:
    """Encode one sync frame; returns its 1488 channel levels (1 = land) and the end boundary."""
    if len(data) != BYTES_PER_FRAME:
        raise ValueError("a sync frame has 91 bytes")
    s1 = _Stream(b, sync_word(b.state, category, True), True)
    s2 = _Stream(b, sync_word(b.state, category, False), False)
    for value in (int(v) for v in data):
        if value <= 87:
            sel = _select(s1, s2)
            s1.copy_from(sel)
            s2.copy_from(sel)
            st = sel.state
            s1.append(main(value, st))
            s2.append(sub(value, st))
            continue
        c1, c2 = _two_reps(value, s1), _two_reps(value, s2)
        if c1 and c2:
            sel = _select(s1, s2)
            s1.copy_from(sel)
            s2.copy_from(sel)
            s1.append(main(value, 1))
            s2.append(main(value, 4))
        elif c1 or c2:
            el, other = (s1, s2) if c1 else (s2, s1)
            if abs(el.dsv) < abs(other.dsv) or (abs(el.dsv) == abs(other.dsv) and el is s1):
                s1.copy_from(el)
                s2.copy_from(el)
                s1.append(main(value, 1))
                s2.append(main(value, 4))
            else:
                s1.append(main(value, s1.state))
                s2.append(main(value, s2.state))
        else:
            s1.append(main(value, s1.state))
            s2.append(main(value, s2.state))
    win = _select(s1, s2)
    bits = win.bits
    if not -64 <= win.dsv <= 63:
        alt = list(bits)
        w = sync_word(b.state, category, not win.primary)
        alt[:32] = [(w >> k) & 1 for k in range(31, -1, -1)]
        _, alt_dsv, _ = _replay(alt, b)
        if abs(alt_dsv) < abs(win.dsv):
            bits = alt
    level, dsv, land = _replay(bits, b)
    return level, Boundary(win.state, dsv, land)


def encode_rows(rows: np.ndarray, b: Boundary = Boundary(), first_row: int = 0) -> tuple[np.ndarray, Boundary]:
    """Encode recording-frame rows (N x 182 bytes); row i uses ROW_SYNC[(first_row + i) % 13]."""
    out = []
    for i, row in enumerate(np.asarray(rows, dtype=np.uint8)):
        cats = ROW_SYNC[(first_row + i) % 13]
        for half in range(2):
            lv, b = encode_frame(row[91 * half:91 * (half + 1)], cats[half], b)
            out.append(lv)
    return np.concatenate(out), b
