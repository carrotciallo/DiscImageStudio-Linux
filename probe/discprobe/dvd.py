"""DVD main-data scrambling (ECMA-267 section 16), for writing chosen recorded bytes.

The drive XORs the 2048 user bytes of every sector with a scrambling sequence before
EFMPlus modulation. To make the recorded (scrambled-domain) byte equal Q, the host
writes P = Q XOR S. The sequence comes from a 15-bit shift register with feedback
x^15 + x^4 + 1; the low byte of the register is output, then it shifts 8 times. The
preset is chosen by bits 7..4 of the physical sector number, so the 16 sectors of
one ECC block share a sequence and 16 consecutive blocks cycle through all presets.
Same table and register as DiscImageStudio's DvdDataFrameBuilder.
"""

from __future__ import annotations

import numpy as np

SECTOR_BYTES = 2048
BLOCK_SECTORS = 16
DATA_START_PSN = 0x30000  # LBA 0 of a single-layer DVD±R

PRESETS = (0x0001, 0x5500, 0x0002, 0x2A00, 0x0004, 0x5400, 0x0008, 0x2800,
           0x0010, 0x5000, 0x0020, 0x2001, 0x0040, 0x4002, 0x0080, 0x0005)


def _sequence(preset: int) -> np.ndarray:
    reg = preset
    out = np.empty(SECTOR_BYTES, dtype=np.uint8)
    for i in range(SECTOR_BYTES):
        out[i] = reg & 0xFF
        for _ in range(8):
            reg = ((reg << 1) | (((reg >> 14) ^ (reg >> 10)) & 1)) & 0x7FFF
    return out


MASKS = np.stack([_sequence(p) for p in PRESETS])


def preset_index(lba: int) -> int:
    return ((lba + DATA_START_PSN) >> 4) & 0xF


def payload_for(q: int, lba: int) -> np.ndarray:
    """User bytes for one sector whose recorded main data is all Q."""
    return MASKS[preset_index(lba)] ^ np.uint8(q)


def recorded(payload: np.ndarray, lba: int) -> np.ndarray:
    """Scrambled-domain bytes the drive will modulate for this sector's payload."""
    return payload ^ MASKS[preset_index(lba)]


def lfsr_period(preset: int = 1) -> int:
    """Steps until the register returns to its preset; 32767 for a maximal-length x^15 + x^4 + 1."""
    reg, n = preset, 0
    while True:
        reg = ((reg << 1) | (((reg >> 14) ^ (reg >> 10)) & 1)) & 0x7FFF
        n += 1
        if reg == preset or n > 40000:
            return n
