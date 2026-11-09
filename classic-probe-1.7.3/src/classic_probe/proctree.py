"""A process and every process it starts, ended together (1.7.2, the client's review of 1.7.1, finding C2).

A session's command may start other processes (a request worker, or anything a broken session leaves
behind). 1.7.1 killed the session's tree only when the session overran its time: a session that exited by
itself left its children running, and one of them could still send a request after the supervisor had
returned. A :class:`ProcessTree` is ended whole whenever the session ends, by itself or not:

- on Linux and macOS the command leads a new session and process group; :meth:`ProcessTree.end` sends
  SIGKILL to the whole group, reaps the leader, and waits (bounded) until no process of the group is left.
  A process that left the group on purpose (a new session of its own) is outside this bound; the probe's own
  processes never do that;
- on Windows the command starts suspended, is put into a job object (which every process it starts then
  joins) and is only then resumed, so nothing it starts escapes the job. :meth:`ProcessTree.end` terminates
  the job and waits (bounded) until it has no active process. The job is also closed with the
  kill-on-close flag, so a supervisor that dies takes the tree with it. If the job cannot be made (an old
  Windows, or a parent job that forbids it), the tree falls back to ``taskkill /T``, and says so.

Every wait is bounded by the seconds the caller gives: nothing here can hold a supervisor past its end.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any

POLL_S = 0.01

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    CREATE_SUSPENDED = 0x00000004
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION_CLASS = 1
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _Accounting(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_int64),
            ("TotalKernelTime", ctypes.c_int64),
            ("ThisPeriodTotalUserTime", ctypes.c_int64),
            ("ThisPeriodTotalKernelTime", ctypes.c_int64),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    def _kernel32() -> Any:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.SetInformationJobObject.restype = wintypes.BOOL
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.AssignProcessToJobObject.restype = wintypes.BOOL
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.QueryInformationJobObject.restype = wintypes.BOOL
        k.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k.TerminateJobObject.restype = wintypes.BOOL
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        return k

    def _resume(proc: subprocess.Popen[bytes]) -> None:
        """Resume a process started suspended (``NtResumeProcess``, as psutil's ``resume`` does)."""
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.restype = ctypes.c_long
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        status = ntdll.NtResumeProcess(int(getattr(proc, "_handle")))  # noqa: B009 - Popen's process handle
        if status != 0:
            raise OSError(f"NtResumeProcess failed with status {status & 0xFFFFFFFF:#010x}")

    class _Job:
        def __init__(self, k: Any, handle: int) -> None:
            self.k, self.handle = k, handle

        @classmethod
        def make(cls) -> _Job | None:
            k = _kernel32()
            handle = k.CreateJobObjectW(None, None)
            if not handle:
                return None
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k.SetInformationJobObject(
                handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ):
                k.CloseHandle(handle)
                return None
            return cls(k, handle)

        def assign(self, proc: subprocess.Popen[bytes]) -> bool:
            return bool(self.k.AssignProcessToJobObject(self.handle, int(getattr(proc, "_handle"))))  # noqa: B009

        def active(self) -> int | None:
            info = _Accounting()
            if not self.k.QueryInformationJobObject(
                self.handle,
                JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION_CLASS,
                ctypes.byref(info),
                ctypes.sizeof(info),
                None,
            ):
                return None
            return int(info.ActiveProcesses)

        def terminate(self) -> bool:
            return bool(self.k.TerminateJobObject(self.handle, 1))

        def close(self) -> None:
            if self.handle:
                self.k.CloseHandle(self.handle)
                self.handle = 0


class ProcessTree:
    """A command's process and everything it starts. Use :meth:`start`; end it with :meth:`end`."""

    def __init__(self, proc: subprocess.Popen[bytes], job: Any = None, note: str = "") -> None:
        self.proc = proc
        self._job = job
        self.note = note  # how the tree is held: "process group", "job object", or the fallback and why

    @classmethod
    def start(
        cls,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdout: IO[bytes] | int | None = None,
    ) -> ProcessTree:
        common: dict[str, Any] = {
            "cwd": cwd,
            "env": None if env is None else dict(env),
            "stdin": subprocess.DEVNULL,
            "stdout": stdout,
            "stderr": subprocess.STDOUT if stdout is not None else None,
        }
        if sys.platform == "win32":
            job = _Job.make()
            if job is None:
                return cls(
                    subprocess.Popen(list(args), **common), note="taskkill /T (no job object could be made)"
                )
            proc = subprocess.Popen(list(args), creationflags=CREATE_SUSPENDED, **common)
            assigned = job.assign(proc)
            try:
                _resume(proc)
            except OSError:
                proc.kill()
                proc.wait(5)
                job.close()
                raise
            if not assigned:
                job.close()
                return cls(proc, note="taskkill /T (the process could not join a job object)")
            return cls(proc, job, note="job object")
        return cls(subprocess.Popen(list(args), start_new_session=True, **common), note="process group")

    @property
    def pid(self) -> int:
        return self.proc.pid

    def wait(self, timeout: float) -> int | None:
        """The leading process's exit code once it has exited, or None when ``timeout`` ran out first."""
        try:
            return self.proc.wait(max(0.0, timeout))
        except subprocess.TimeoutExpired:
            return None

    def members_left(self) -> bool | None:
        """Whether any process of the tree still exists (None: this cannot be told)."""
        if sys.platform == "win32":
            if self._job is None:
                return self.proc.poll() is None or None
            active = self._job.active()
            return None if active is None else active > 0
        try:
            os.killpg(self.proc.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def end(self, seconds: float) -> dict[str, Any]:
        """Kill every process of the tree, reap the leader and wait until none is left, all within
        ``seconds``. Returns what happened: whether processes were still there (``left_running``), whether
        the tree is gone (``gone``: None when it cannot be told), and any problem."""
        until = time.monotonic() + max(0.0, seconds)
        problems: list[str] = []
        before = self.members_left()
        if sys.platform == "win32":
            if self._job is not None:
                if not self._job.terminate() and self.members_left():
                    problems.append("the job object could not be terminated")
            else:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                        capture_output=True,
                        timeout=max(0.05, until - time.monotonic()),
                        check=False,
                    )
                except (subprocess.TimeoutExpired, OSError) as exc:
                    problems.append(f"taskkill did not finish in time ({type(exc).__name__})")
                if self.proc.poll() is None:
                    try:
                        self.proc.kill()
                    except OSError as exc:
                        problems.append(f"the process could not be killed: {type(exc).__name__}")
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)  # the command leads its own process group
            except ProcessLookupError:
                pass
            except OSError as exc:
                problems.append(f"the process group could not be killed: {type(exc).__name__}")
        reaped = self.wait(until - time.monotonic()) is not None
        if not reaped:
            problems.append("the leading process had not exited when the time to reap it ran out")
        gone = self.members_left() is False
        while not gone and time.monotonic() < until:
            time.sleep(POLL_S)
            gone = self.members_left() is False
        state = self.members_left()
        if state:
            problems.append("a process of the tree was still running when the time to end it ran out")
        return {
            "held_by": self.note,
            "left_running": bool(before),
            "reaped": reaped,
            "gone": None if state is None else not state,
            "problems": problems,
        }

    def close(self) -> None:
        if self._job is not None:
            self._job.close()
            self._job = None
