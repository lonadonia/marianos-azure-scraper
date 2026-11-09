"""Whether a process has gone, for the tests that prove a worker or a session left nothing running (1.7.2).

A process that was killed but not yet reaped by its parent (a zombie on Linux) has gone: it runs nothing and
can send nothing.
"""

from __future__ import annotations

import os
import sys
import time

STILL_ACTIVE = 259  # GetExitCodeProcess: the process has not ended
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def gone(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return True  # no such process any more
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value != STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            state = f.read().rsplit(b")", 1)[1].split()[0]
        return state in (b"Z", b"X")  # a zombie runs nothing: it only waits to be reaped
    except FileNotFoundError:
        return True
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def wait_gone(pid: int, seconds: float) -> bool:
    """True once ``pid`` has gone, False if it still runs after ``seconds``."""
    end = time.monotonic() + seconds
    while True:
        if gone(pid):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.02)
