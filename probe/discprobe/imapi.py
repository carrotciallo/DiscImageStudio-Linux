"""Windows IMAPI2 transport: the same CDBs as spti.py, without administrator rights.

SPTI opens \\\\.\\E: for read and write, which Windows often grants only to an elevated
process (it depends on the device's security settings: a USB HP BU20N opened fine for a
standard user). IMAPI2's recorder object reaches the same drive through
IDiscRecorder2Ex::SendCommand*, which a standard user may call once it holds the recorder
with AcquireExclusiveAccess. While it is held, media-change notification (MCN) is
disabled, so Explorer's polling does not interleave with the timed reads.

ImapiDevice has the interface of SptiDevice: execute() returns a ScsiResult whose
timestamps are taken with time.perf_counter_ns() immediately around the COM call, the
opcode allowlist in scsi.py is enforced first, and data-out commands are refused.

Only the standard library is used (ctypes):
- MsftDiscMaster2 and MsftDiscRecorder2 are reached through IDispatch (GetIDsOfNames +
  Invoke), so nothing depends on the order of their vtables;
- IDiscRecorder2Ex derives from IUnknown; its first three methods after IUnknown are
  SendCommandNoData, SendCommandSendDataToDevice and SendCommandGetDataFromDevice.

IMAPI2 reports a CHECK CONDITION as the success code S_IMAPI_COMMAND_HAS_SENSE_DATA
(0x00AA0200) with the sense bytes in the caller's buffer; that becomes a ScsiResult with
status 0x02. A failing HRESULT means the command never ran and raises OSError, as a
failing DeviceIoControl does in spti.py.
"""

from __future__ import annotations

import ctypes
import string
import time
from ctypes import wintypes

from .scsi import DATA_IN, DATA_NONE, DATA_OUT, ScsiResult, check_allowed, parse_sense

BUFFER_BYTES = 128 * 1024
SENSE_BYTES = 18                      # IDiscRecorder2Ex takes exactly 18 bytes of sense
CHECK_CONDITION = 0x02
S_IMAPI_COMMAND_HAS_SENSE_DATA = 0x00AA0200
CLIENT_NAME = "discprobe"

CLSID_MSFT_DISC_MASTER2 = "{2735412E-7F64-5B0F-8F00-5D77AFBE261E}"
CLSID_MSFT_DISC_RECORDER2 = "{2735412D-7F64-5B0F-8F00-5D77AFBE261E}"
IID_IDISPATCH = "{00020400-0000-0000-C000-000000000046}"
IID_IDISC_RECORDER2_EX = "{27354132-7F64-5B0F-8F00-5D77AFBE261E}"

COINIT_APARTMENTTHREADED = 0x2
CLSCTX_ALL = 0x17
RPC_E_CHANGED_MODE = 0x80010106 - (1 << 32)
DISPATCH_METHOD, DISPATCH_PROPERTYGET = 1, 2
DISP_E_EXCEPTION = 0x80020009 - (1 << 32)
VT_EMPTY, VT_I4, VT_BSTR, VT_BOOL, VT_VARIANT, VT_ARRAY = 0, 3, 8, 11, 12, 0x2000
LOCALE_USER_DEFAULT = 0x0400
MEM_COMMIT_RESERVE = 0x3000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _VariantValue(ctypes.Union):
    _fields_ = [("llVal", ctypes.c_longlong), ("lVal", ctypes.c_long), ("boolVal", ctypes.c_short),
                ("bstrVal", ctypes.c_void_p), ("parray", ctypes.c_void_p),
                ("_record", ctypes.c_void_p * 2)]          # BRECORD: sets the size on 64-bit


class VARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("wReserved1", ctypes.c_ushort),
                ("wReserved2", ctypes.c_ushort), ("wReserved3", ctypes.c_ushort),
                ("value", _VariantValue)]


class DISPPARAMS(ctypes.Structure):
    _fields_ = [("rgvarg", ctypes.POINTER(VARIANT)), ("rgdispidNamedArgs", ctypes.POINTER(ctypes.c_long)),
                ("cArgs", ctypes.c_uint), ("cNamedArgs", ctypes.c_uint)]


class EXCEPINFO(ctypes.Structure):
    _fields_ = [("wCode", ctypes.c_ushort), ("wReserved", ctypes.c_ushort),
                ("bstrSource", ctypes.c_void_p), ("bstrDescription", ctypes.c_void_p),
                ("bstrHelpFile", ctypes.c_void_p), ("dwHelpContext", ctypes.c_ulong),
                ("pvReserved", ctypes.c_void_p), ("pfnDeferredFillIn", ctypes.c_void_p),
                ("scode", ctypes.c_long)]


_ole32 = ctypes.WinDLL("ole32")
_oleaut32 = ctypes.WinDLL("oleaut32")
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None
_ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]
_ole32.CLSIDFromString.restype = ctypes.c_long
_ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
_ole32.CoCreateInstance.restype = ctypes.c_long
_oleaut32.SysAllocString.argtypes = [wintypes.LPCWSTR]
_oleaut32.SysAllocString.restype = ctypes.c_void_p
_oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]
_oleaut32.SysFreeString.restype = None
_oleaut32.VariantClear.argtypes = [ctypes.POINTER(VARIANT)]
_oleaut32.VariantClear.restype = ctypes.c_long
_oleaut32.SafeArrayGetLBound.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_long)]
_oleaut32.SafeArrayGetLBound.restype = ctypes.c_long
_oleaut32.SafeArrayGetUBound.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_long)]
_oleaut32.SafeArrayGetUBound.restype = ctypes.c_long
_oleaut32.SafeArrayGetElement.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_long), ctypes.c_void_p]
_oleaut32.SafeArrayGetElement.restype = ctypes.c_long
_kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
_kernel32.VirtualAlloc.restype = ctypes.c_void_p
_kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
_kernel32.VirtualFree.restype = wintypes.BOOL

_HRESULT = ctypes.c_long
# IUnknown / IDispatch slots
_QueryInterface = ctypes.WINFUNCTYPE(_HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_GetIDsOfNames = ctypes.WINFUNCTYPE(_HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID),
                                    ctypes.POINTER(wintypes.LPCWSTR), ctypes.c_uint, ctypes.c_ulong,
                                    ctypes.POINTER(ctypes.c_long))
_Invoke = ctypes.WINFUNCTYPE(_HRESULT, ctypes.c_void_p, ctypes.c_long, ctypes.POINTER(GUID), ctypes.c_ulong,
                             ctypes.c_ushort, ctypes.POINTER(DISPPARAMS), ctypes.POINTER(VARIANT),
                             ctypes.POINTER(EXCEPINFO), ctypes.POINTER(ctypes.c_uint))
# IDiscRecorder2Ex slots 3 and 5 (after IUnknown)
_SendCommandNoData = ctypes.WINFUNCTYPE(_HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                        ctypes.c_void_p, ctypes.c_ulong)
_SendCommandGetDataFromDevice = ctypes.WINFUNCTYPE(_HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                                   ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                                   ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))
SLOT_QUERY_INTERFACE, SLOT_RELEASE, SLOT_GET_IDS_OF_NAMES, SLOT_INVOKE = 0, 2, 5, 6
SLOT_SEND_NO_DATA, SLOT_SEND_GET_DATA = 3, 5


def _guid(text: str) -> GUID:
    g = GUID()
    hr = _ole32.CLSIDFromString(text, ctypes.byref(g))
    if hr < 0:
        raise OSError(hr, f"bad GUID {text}")
    return g


def _hex(hr: int) -> str:
    return f"0x{hr & 0xFFFFFFFF:08X}"


def _method(ptr: int, slot: int, proto):
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
    return proto(ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))[slot])


def _release(ptr) -> None:
    if ptr:
        _method(ptr, SLOT_RELEASE, _Release)(ptr)


class _Dispatch:
    """Late-bound calls on an IDispatch pointer (owns one reference)."""

    def __init__(self, ptr: int):
        self.ptr = ptr

    def _dispid(self, name: str) -> int:
        names = (wintypes.LPCWSTR * 1)(name)
        dispid = ctypes.c_long()
        hr = _method(self.ptr, SLOT_GET_IDS_OF_NAMES, _GetIDsOfNames)(
            self.ptr, ctypes.byref(GUID()), names, 1, LOCALE_USER_DEFAULT, ctypes.byref(dispid))
        if hr < 0:
            raise OSError(hr, f"IMAPI2 has no member {name} ({_hex(hr)})")
        return dispid.value

    def call(self, name: str, *args, get: bool = False) -> VARIANT:
        """Invoke a method (or a property get); args are int, bool or str. The caller owns the result."""
        n = len(args)
        argv = (VARIANT * max(n, 1))()
        bstrs = []
        for i, a in enumerate(reversed(args)):           # IDispatch takes arguments in reverse order
            v = argv[i]
            if isinstance(a, bool):
                v.vt, v.value.boolVal = VT_BOOL, -1 if a else 0
            elif isinstance(a, int):
                v.vt, v.value.lVal = VT_I4, a
            else:
                b = _oleaut32.SysAllocString(a)
                bstrs.append(b)
                v.vt, v.value.bstrVal = VT_BSTR, b
        params = DISPPARAMS(argv if n else None, None, n, 0)
        result, exc, argerr = VARIANT(), EXCEPINFO(), ctypes.c_uint()
        try:
            hr = _method(self.ptr, SLOT_INVOKE, _Invoke)(
                self.ptr, self._dispid(name), ctypes.byref(GUID()), LOCALE_USER_DEFAULT,
                DISPATCH_PROPERTYGET if get else DISPATCH_METHOD, ctypes.byref(params),
                ctypes.byref(result), ctypes.byref(exc), ctypes.byref(argerr))
        finally:
            for b in bstrs:
                _oleaut32.SysFreeString(b)
        if hr < 0:
            code, text = hr, ""
            if hr == DISP_E_EXCEPTION:
                code = exc.scode or hr
                if exc.bstrDescription:
                    text = ctypes.wstring_at(exc.bstrDescription).strip()
            for b in (exc.bstrSource, exc.bstrDescription, exc.bstrHelpFile):
                if b:
                    _oleaut32.SysFreeString(b)
            raise OSError(code, f"IMAPI2 {name} failed: {_hex(code)} {text}".rstrip())
        return result

    def get_str(self, name: str, *args) -> str:
        v = self.call(name, *args, get=True)
        try:
            return ctypes.wstring_at(v.value.bstrVal) if v.vt == VT_BSTR and v.value.bstrVal else ""
        finally:
            _oleaut32.VariantClear(ctypes.byref(v))

    def get_int(self, name: str) -> int:
        v = self.call(name, get=True)
        try:
            return int(v.value.lVal)
        finally:
            _oleaut32.VariantClear(ctypes.byref(v))

    def get_str_array(self, name: str) -> list[str]:
        v = self.call(name, get=True)
        out = []
        try:
            if v.vt == VT_ARRAY | VT_VARIANT and v.value.parray:
                lo, hi = ctypes.c_long(), ctypes.c_long()
                _oleaut32.SafeArrayGetLBound(v.value.parray, 1, ctypes.byref(lo))
                _oleaut32.SafeArrayGetUBound(v.value.parray, 1, ctypes.byref(hi))
                for i in range(lo.value, hi.value + 1):
                    item, idx = VARIANT(), ctypes.c_long(i)
                    if _oleaut32.SafeArrayGetElement(v.value.parray, ctypes.byref(idx), ctypes.byref(item)) >= 0:
                        if item.vt == VT_BSTR and item.value.bstrVal:
                            out.append(ctypes.wstring_at(item.value.bstrVal))
                        _oleaut32.VariantClear(ctypes.byref(item))
        finally:
            _oleaut32.VariantClear(ctypes.byref(v))
        return out

    def release(self) -> None:
        _release(self.ptr)
        self.ptr = None


def _com_init() -> bool:
    hr = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != RPC_E_CHANGED_MODE:
        raise OSError(hr, f"CoInitializeEx failed: {_hex(hr)}")
    return hr >= 0                                       # S_OK or S_FALSE: balance with CoUninitialize


def _create(clsid: str) -> _Dispatch:
    ptr = ctypes.c_void_p()
    hr = _ole32.CoCreateInstance(ctypes.byref(_guid(clsid)), None, CLSCTX_ALL,
                                 ctypes.byref(_guid(IID_IDISPATCH)), ctypes.byref(ptr))
    if hr < 0:
        raise OSError(hr, f"cannot create IMAPI2 object {clsid}: {_hex(hr)} (is the IMAPI2 service available?)")
    return _Dispatch(ptr.value)


def _recorders() -> tuple[list[tuple[str, list[str], _Dispatch]], list[str]]:
    """(unique id, volume paths, initialised recorder) for every IMAPI2 recorder that could be initialised,
    and the errors of those that could not."""
    master = _create(CLSID_MSFT_DISC_MASTER2)
    try:
        ids = [master.get_str("Item", i) for i in range(master.get_int("Count"))]
    finally:
        master.release()
    out, errors = [], []
    for uid in ids:
        rec = _create(CLSID_MSFT_DISC_RECORDER2)
        try:
            v = rec.call("InitializeDiscRecorder", uid)
            _oleaut32.VariantClear(ctypes.byref(v))
            out.append((uid, rec.get_str_array("VolumePathNames"), rec))
        except OSError as e:
            errors.append(e.strerror or str(e))
            rec.release()
    return out, errors


class ImapiDevice:
    def __init__(self, drive: str):
        letter = drive.rstrip(":\\/").upper()
        if len(letter) != 1 or letter not in string.ascii_uppercase:
            raise ValueError(f"expected a drive letter such as E:, got {drive!r}")
        self.name = f"{letter}:"
        self._com = _com_init()
        self._rec = self._ex = self._buf = None
        self._locked = self._mcn_off = False
        try:
            found = None
            recorders, errors = _recorders()
            for _, paths, rec in recorders:
                if found is None and any(p.upper().startswith(f"{letter}:") for p in paths):
                    found = rec
                else:
                    rec.release()
            if found is None:
                why = f"no IMAPI2 recorder at {self.name}"
                if errors:
                    # A recorder that cannot be initialised has no known drive letter; it may be this one.
                    why += (f" ({len(errors)} recorder{'s' if len(errors) > 1 else ''} could not be initialised;"
                            f" last error: {errors[-1]})")
                raise OSError(2, why)
            self._rec = found
            self.model = " ".join(found.get_str(n).strip() for n in ("VendorId", "ProductId", "ProductRevision"))
            v = found.call("AcquireExclusiveAccess", False, CLIENT_NAME)
            _oleaut32.VariantClear(ctypes.byref(v))
            self._locked = True
            v = found.call("DisableMcn")                 # no media-change polling during the timing
            _oleaut32.VariantClear(ctypes.byref(v))
            self._mcn_off = True
            ex = ctypes.c_void_p()
            hr = _method(found.ptr, SLOT_QUERY_INTERFACE, _QueryInterface)(
                found.ptr, ctypes.byref(_guid(IID_IDISC_RECORDER2_EX)), ctypes.byref(ex))
            if hr < 0:
                raise OSError(hr, f"IDiscRecorder2Ex not available: {_hex(hr)}")
            self._ex = ex.value
            self._no_data = _method(self._ex, SLOT_SEND_NO_DATA, _SendCommandNoData)
            self._get_data = _method(self._ex, SLOT_SEND_GET_DATA, _SendCommandGetDataFromDevice)
            # Page-aligned, like spti.py.
            self._buf = _kernel32.VirtualAlloc(None, BUFFER_BYTES, MEM_COMMIT_RESERVE, PAGE_READWRITE)
            if not self._buf:
                raise MemoryError("VirtualAlloc failed")
        except BaseException:
            self.close()
            raise
        self._cdb = (ctypes.c_ubyte * 16)()
        self._sense = (ctypes.c_ubyte * SENSE_BYTES)()
        self._fetched = ctypes.c_ulong()

    def execute(self, cdb: bytes, data_len: int = 0, direction: int = DATA_IN,
                timeout_s: int = 30) -> ScsiResult:
        check_allowed(cdb)
        if direction == DATA_OUT:
            raise PermissionError("data-out commands are not used by this probe")
        if data_len > BUFFER_BYTES:
            raise ValueError(f"transfer of {data_len} bytes exceeds the {BUFFER_BYTES}-byte buffer")
        if not 1 <= len(cdb) <= 16:
            raise ValueError(f"CDB length {len(cdb)} is outside 1..16")
        ctypes.memmove(self._cdb, cdb, len(cdb))
        ctypes.memset(self._sense, 0, SENSE_BYTES)
        self._fetched.value = 0
        if data_len and direction != DATA_NONE:
            t0 = time.perf_counter_ns()
            hr = self._get_data(self._ex, self._cdb, len(cdb), self._sense, timeout_s,
                                self._buf, data_len, ctypes.byref(self._fetched))
            t1 = time.perf_counter_ns()
        else:
            t0 = time.perf_counter_ns()
            hr = self._no_data(self._ex, self._cdb, len(cdb), self._sense, timeout_s)
            t1 = time.perf_counter_ns()
        if hr < 0:
            raise OSError(hr, f"IDiscRecorder2Ex command 0x{cdb[0]:02X} failed: {_hex(hr)}")
        has_sense = hr == S_IMAPI_COMMAND_HAS_SENSE_DATA
        n = min(self._fetched.value, data_len) if data_len else 0
        data = ctypes.string_at(self._buf, n) if n else b""
        sense = parse_sense(bytes(self._sense)) if has_sense else None
        return ScsiResult(CHECK_CONDITION if has_sense else 0, data, sense, t0, t1)

    def close(self) -> None:
        rec = self._rec
        if rec is not None and rec.ptr:
            for name, flag in (("EnableMcn", self._mcn_off), ("ReleaseExclusiveAccess", self._locked)):
                if flag:
                    try:
                        v = rec.call(name)
                        _oleaut32.VariantClear(ctypes.byref(v))
                    except OSError:
                        pass
            self._mcn_off = self._locked = False
        if self._ex:
            _release(self._ex)
            self._ex = None
        if rec is not None and rec.ptr:
            rec.release()
        self._rec = None
        if self._buf:
            _kernel32.VirtualFree(self._buf, 0, MEM_RELEASE)
            self._buf = None
        if self._com:
            _ole32.CoUninitialize()
            self._com = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
