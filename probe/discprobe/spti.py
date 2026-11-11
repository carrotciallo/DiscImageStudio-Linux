"""Windows SCSI pass-through (SPTI) for optical drives.

Timestamps are taken with time.perf_counter_ns() immediately around DeviceIoControl,
so they include the OS storage stack and the SATA link but nothing from Python
beyond the ctypes call itself.
"""

from __future__ import annotations

import ctypes
import string
import time
from ctypes import wintypes

from .scsi import DATA_IN, DATA_NONE, DATA_OUT, ScsiResult, check_allowed, parse_sense

IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MEM_COMMIT_RESERVE = 0x3000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
DRIVE_CDROM = 5
HIGH_PRIORITY_CLASS = 0x80
THREAD_PRIORITY_HIGHEST = 2

BUFFER_BYTES = 128 * 1024
SENSE_BYTES = 32


class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_ushort),
        ("ScsiStatus", ctypes.c_ubyte),
        ("PathId", ctypes.c_ubyte),
        ("TargetId", ctypes.c_ubyte),
        ("Lun", ctypes.c_ubyte),
        ("CdbLength", ctypes.c_ubyte),
        ("SenseInfoLength", ctypes.c_ubyte),
        ("DataIn", ctypes.c_ubyte),
        ("DataTransferLength", ctypes.c_ulong),
        ("TimeOutValue", ctypes.c_ulong),
        ("DataBuffer", ctypes.c_void_p),
        ("SenseInfoOffset", ctypes.c_ulong),
        ("Cdb", ctypes.c_ubyte * 16),
    ]


class SPTD_WITH_SENSE(ctypes.Structure):
    _fields_ = [
        ("sptd", SCSI_PASS_THROUGH_DIRECT),
        ("filler", ctypes.c_ulong),
        ("sense", ctypes.c_ubyte * SENSE_BYTES),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_CreateFileW = _kernel32.CreateFileW
_CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_CreateFileW.restype = wintypes.HANDLE

_DeviceIoControl = _kernel32.DeviceIoControl
_DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                             ctypes.c_void_p]
_DeviceIoControl.restype = wintypes.BOOL

_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]

_VirtualAlloc = _kernel32.VirtualAlloc
_VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
_VirtualAlloc.restype = ctypes.c_void_p

_VirtualFree = _kernel32.VirtualFree
_VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]

_GetDriveTypeW = _kernel32.GetDriveTypeW
_GetDriveTypeW.argtypes = [wintypes.LPCWSTR]

# Without these types the pseudo-handles reach the calls cut to 32 bits, and on 64-bit Python they fail.
_GetCurrentProcess = _kernel32.GetCurrentProcess
_GetCurrentProcess.restype = wintypes.HANDLE
_GetCurrentThread = _kernel32.GetCurrentThread
_GetCurrentThread.restype = wintypes.HANDLE
_SetPriorityClass = _kernel32.SetPriorityClass
_SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_SetPriorityClass.restype = wintypes.BOOL
_SetThreadPriority = _kernel32.SetThreadPriority
_SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
_SetThreadPriority.restype = wintypes.BOOL


def list_optical_drives() -> list[str]:
    mask = _kernel32.GetLogicalDrives()
    drives = []
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i) and _GetDriveTypeW(f"{letter}:\\") == DRIVE_CDROM:
            drives.append(f"{letter}:")
    return drives


def raise_priority() -> bool:
    process_ok = _SetPriorityClass(_GetCurrentProcess(), HIGH_PRIORITY_CLASS)
    thread_ok = _SetThreadPriority(_GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
    return bool(process_ok and thread_ok)


class SptiDevice:
    def __init__(self, drive: str):
        letter = drive.rstrip(":\\/").upper()
        if len(letter) != 1 or letter not in string.ascii_uppercase:
            raise ValueError(f"expected a drive letter such as E:, got {drive!r}")
        self.name = f"{letter}:"
        handle = _CreateFileW(f"\\\\.\\{letter}:", GENERIC_READ | GENERIC_WRITE,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if handle == INVALID_HANDLE_VALUE or handle is None:
            err = ctypes.get_last_error()
            hint = " (run the terminal as Administrator, or use --transport imapi)" if err == 5 else ""
            raise OSError(err, f"cannot open {letter}: {ctypes.FormatError(err)}{hint}")
        self._handle = handle
        # Page-aligned, so it satisfies any adapter AlignmentMask.
        self._buf = _VirtualAlloc(None, BUFFER_BYTES, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not self._buf:
            _CloseHandle(handle)
            raise MemoryError("VirtualAlloc failed")
        self._req = SPTD_WITH_SENSE()
        self._returned = wintypes.DWORD()

    def execute(self, cdb: bytes, data_len: int = 0, direction: int = DATA_IN,
                timeout_s: int = 30) -> ScsiResult:
        check_allowed(cdb)
        if direction == DATA_OUT:
            raise PermissionError("data-out commands are not used by this probe")
        if data_len > BUFFER_BYTES:
            raise ValueError(f"transfer of {data_len} bytes exceeds the {BUFFER_BYTES}-byte buffer")
        req = self._req
        ctypes.memset(ctypes.byref(req), 0, ctypes.sizeof(req))
        sptd = req.sptd
        sptd.Length = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
        sptd.CdbLength = len(cdb)
        sptd.SenseInfoLength = SENSE_BYTES
        sptd.SenseInfoOffset = SPTD_WITH_SENSE.sense.offset
        sptd.DataIn = DATA_IN if data_len else DATA_NONE
        sptd.DataTransferLength = data_len
        sptd.DataBuffer = self._buf if data_len else None
        sptd.TimeOutValue = timeout_s
        for i, b in enumerate(cdb):
            sptd.Cdb[i] = b
        size = ctypes.sizeof(req)
        t0 = time.perf_counter_ns()
        ok = _DeviceIoControl(self._handle, IOCTL_SCSI_PASS_THROUGH_DIRECT, ctypes.byref(req), size,
                              ctypes.byref(req), size, ctypes.byref(self._returned), None)
        t1 = time.perf_counter_ns()
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(err, f"DeviceIoControl failed: {ctypes.FormatError(err)}")
        data = ctypes.string_at(self._buf, min(sptd.DataTransferLength, data_len)) if data_len else b""
        sense = parse_sense(bytes(req.sense)) if sptd.ScsiStatus else None
        return ScsiResult(sptd.ScsiStatus, data, sense, t0, t1)

    def close(self) -> None:
        if self._buf:
            _VirtualFree(self._buf, 0, MEM_RELEASE)
            self._buf = None
        if self._handle:
            _CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
