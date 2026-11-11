"""Linux SCSI pass-through (SG_IO) for optical drives.

Same contract as spti.py: open an optical drive, send a raw SCSI CDB with one
ioctl, and timestamp with time.perf_counter_ns() immediately around that ioctl.
SG_IO works on both /dev/srN (the sr driver's generic SCSI ioctl) and /dev/sgN
(the raw sg driver); the open tries the given path and, when it is an sr device
that is mounted (EBUSY), its matching sg device.
"""

from __future__ import annotations

import ctypes
import os
import time

from .scsi import DATA_IN, DATA_OUT, ScsiResult, check_allowed, parse_sense

SG_IO = 0x2285
SG_DXFER_NONE = -1
SG_DXFER_FROM_DEV = -3

BUFFER_BYTES = 128 * 1024
SENSE_BYTES = 32

_libc = ctypes.CDLL(None, use_errno=True)
_libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
_libc.ioctl.restype = ctypes.c_int


class _SGIOHeader(ctypes.Structure):
    # struct sg_io_hdr from <scsi/sg.h>; field order and types must match, ctypes
    # applies the same natural alignment as the C compiler.
    _fields_ = [
        ("interface_id", ctypes.c_int),        # 'S'
        ("dxfer_direction", ctypes.c_int),     # SG_DXFER_* above
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),            # milliseconds
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]


def list_optical_drives() -> list[str]:
    """Return the sr device nodes that are optical drives, e.g. ['/dev/sr0']."""
    drives = []
    try:
        names = os.listdir("/sys/block")
    except OSError:
        return drives
    for name in sorted(names):
        if not name.startswith("sr"):
            continue
        path = f"/dev/{name}"
        if not os.path.exists(path):
            continue
        type_path = f"/sys/block/{name}/device/type"
        try:
            with open(type_path) as f:
                if f.read().strip() != "5":  # TYPE_ROM = optical
                    continue
        except OSError:
            pass  # sr* is already optical by construction; keep it
        drives.append(path)
    return drives


def _resolve(drive: str) -> str:
    d = drive.strip()
    if d.startswith("/dev/"):
        return d
    name = os.path.basename(d.rstrip("/"))
    if name.startswith(("sr", "sg")) and "/" not in name:
        return f"/dev/{name}"
    return d


def _sg_for_sr(sr_path: str) -> str | None:
    """Map /dev/srN to its /dev/sgN via the shared SCSI device in sysfs."""
    name = os.path.basename(sr_path)
    dev = os.path.realpath(f"/sys/block/{name}/device")
    if not os.path.isdir(dev):
        return None
    try:
        entries = os.listdir("/sys/class/scsi_generic")
    except OSError:
        return None
    for sg in sorted(entries):
        if os.path.realpath(f"/sys/class/scsi_generic/{sg}/device") == dev:
            return f"/dev/{sg}"
    return None


def raise_priority() -> bool:
    # Real-time scheduling removes preemption while the process waits on each SG_IO,
    # which is the dominant Linux-specific timing jitter; pin to one CPU so the loop
    # never migrates, and fall back to a high nice value (Windows SPTI uses its own
    # SetPriorityClass path for the same effect).
    ok = False
    try:
        lo = os.sched_get_priority_min(os.SCHED_FIFO)
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(lo))
        ok = True
    except (OSError, AttributeError):
        pass
    try:
        cpu = min(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {cpu})
    except (OSError, AttributeError):
        pass
    if ok:
        return True
    try:
        os.nice(-20)
        return True
    except OSError:
        return False


class SgDevice:
    def __init__(self, drive: str):
        self.path = _resolve(drive)
        self.name = os.path.basename(self.path)
        self._fd = None
        self._buf = ctypes.create_string_buffer(BUFFER_BYTES)
        self._sense = ctypes.create_string_buffer(SENSE_BYTES)
        self._cdb = ctypes.create_string_buffer(16)
        self._hdr = _SGIOHeader()

        candidates = [self.path]
        if self.name.startswith("sr"):
            sg = _sg_for_sr(self.path)
            if sg:
                candidates.append(sg)
        last = None
        for cand in candidates:
            try:
                # O_RDWR so SET CD SPEED clears the kernel's read-only command
                # filter; O_NONBLOCK so a bare sg open never hangs.
                self._fd = os.open(cand, os.O_RDWR | os.O_NONBLOCK)
                self.path, self.name = cand, os.path.basename(cand)
                break
            except OSError as e:
                last = e
        if self._fd is None:
            self._raise_open_error(last)

    def _raise_open_error(self, err: OSError):
        hint = ""
        if err is not None:
            if err.errno in (1, 13):  # EPERM, EACCES
                hint = " (add your user to the cdrom/disk group, or run as root)"
            elif err.errno == 16:  # EBUSY
                hint = " (the disc is mounted: unmount it, e.g. udisksctl unmount -b /dev/sr0, or pass /dev/sgN)"
        msg = f"cannot open {self.path}"
        if err is not None:
            msg += f": {err.strerror}"
        raise OSError(err.errno, msg + hint) from err

    def execute(self, cdb: bytes, data_len: int = 0, direction: int = DATA_IN,
                timeout_s: int = 30) -> ScsiResult:
        check_allowed(cdb)
        if direction == DATA_OUT:
            raise PermissionError("data-out commands are not used by this probe")
        if data_len > BUFFER_BYTES:
            raise ValueError(f"transfer of {data_len} bytes exceeds the {BUFFER_BYTES}-byte buffer")

        hdr = self._hdr
        ctypes.memset(ctypes.byref(hdr), 0, ctypes.sizeof(hdr))
        ctypes.memset(self._cdb, 0, 16)
        ctypes.memmove(self._cdb, cdb, len(cdb))
        ctypes.memset(self._sense, 0, SENSE_BYTES)

        hdr.interface_id = ord("S")
        hdr.dxfer_direction = SG_DXFER_FROM_DEV if data_len else SG_DXFER_NONE
        hdr.cmd_len = len(cdb)
        hdr.mx_sb_len = SENSE_BYTES
        hdr.dxfer_len = data_len
        hdr.dxferp = ctypes.addressof(self._buf) if data_len else None
        hdr.cmdp = ctypes.addressof(self._cdb)
        hdr.sbp = ctypes.addressof(self._sense)
        hdr.timeout = max(1, int(timeout_s * 1000))

        t0 = time.perf_counter_ns()
        rc = _libc.ioctl(self._fd, SG_IO, ctypes.byref(hdr))
        t1 = time.perf_counter_ns()
        if rc != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"SG_IO on {self.path} failed: {os.strerror(err)}")

        data = ctypes.string_at(ctypes.addressof(self._buf), data_len) if data_len else b""
        sense = parse_sense(bytes(self._sense)) if hdr.status else None
        return ScsiResult(hdr.status, data, sense, t0, t1)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
