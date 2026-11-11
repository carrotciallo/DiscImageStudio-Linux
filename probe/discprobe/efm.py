"""Reference CD EFM modulation and Annex E greedy DSV selection.

ECMA-130 2nd edition, Annexes D/E. This accepts already encoded F3 symbols;
it does not generate CIRC parity/subcode or predict a drive's proprietary
merging-bit choices. Useful for RLL/DSV consistency, not optical brightness.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .efm_tables import EFM

SYNC = "100000000001000000000010"


@dataclass(frozen=True)
class Boundary:
    level: int = 1
    dsv: int = 0
    tail: str = ""


def _advance(bits, state):
    level, dsv, levels = state.level, state.dsv, []
    for bit in bits:
        if bit == "1":
            level = -level
        levels.append(level)
        dsv += level
    return np.array(levels, np.int8), Boundary(level, dsv, (state.tail + bits)[-23:])


def _legal(bits):
    ones = [i for i, bit in enumerate(bits) if bit == "1"]
    return all(3 <= b - a <= 11 for a, b in zip(ones, ones[1:]))


def _choose(word, state, sync_next=False):
    candidates = []
    for merge in (("000", "100") if sync_next else ("000", "001", "010", "100")):
        stream = state.tail + merge + word
        if not _legal(stream):
            continue
        if SYNC in stream and not (sync_next and stream.endswith(SYNC) and stream.count(SYNC) == 1):
            continue
        _, end = _advance(merge + word, state)
        candidates.append((abs(end.dsv), -merge.count("1"), merge))
    if not candidates:
        raise RuntimeError("no legal EFM merging bits")
    return min(candidates)[2]


def encode_frame(symbols, state=Boundary()):
    """33 ordinary F3 symbols -> 588 NRZI levels and next boundary.

    Frame-sync subcode exceptions S0/S1 are outside this diagnostic model.
    Boundaries use signed, unbounded integers; DSV equals sum(NRZI levels).
    """
    if len(symbols) != 33:
        raise ValueError("an F3 frame has 33 symbols")
    if not _legal(state.tail + SYNC):
        raise ValueError("invalid EFM frame boundary")
    levels, state = _advance(SYNC, state)
    output = [levels]
    for symbol in symbols:
        word = f"{EFM[int(symbol)]:014b}"
        merge = _choose(word, state)
        levels, state = _advance(merge + word, state)
        output.append(levels)
    merge = _choose(SYNC, state, sync_next=True)
    levels, state = _advance(merge, state)
    output.append(levels)
    return np.concatenate(output), state
