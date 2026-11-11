"""Pick the SCSI pass-through backend for this OS.

Windows drives SCSI pass-through via SPTI (spti.py); Linux via SG_IO (sg.py).
Raw CDB access is the only platform-specific part of the codebase: everything
else builds SCSI commands and parses responses the same way on every OS.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .spti import SptiDevice as Device, list_optical_drives, raise_priority  # noqa: F401
elif sys.platform.startswith("linux"):
    from .sg import SgDevice as Device, list_optical_drives, raise_priority  # noqa: F401
else:
    raise ImportError(
        f"no SCSI pass-through backend for platform {sys.platform!r}; "
        "disc-probe currently supports Windows and Linux")
