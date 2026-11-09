"""Files that survive a crash (1.7.1, finding C4).

A file is written whole or not at all: the bytes go to a ``.part`` file that is flushed and synced, and the
``.part`` file is then renamed into place in a way that is itself durable. On Linux and macOS the rename is
made durable by syncing the directory. On Windows a directory cannot be synced: the rename is made with
``MoveFileExW(..., MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)``, which returns only once the move is
on the disk.

A private file is created readable and writable by its owner only (mode 0600, in a 0700 directory) on Linux
and macOS. On Windows a new file takes the access rules of its folder, which for the probe's working folders
is the user's own profile; nothing here widens them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_WRITE_THROUGH = 0x8


def private_dir(path: Path) -> Path:
    """``path`` made if missing, private to its owner on Linux and macOS."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(path, 0o700)
    return path


def sync_dir(path: Path) -> None:
    """Make a rename or a new entry in ``path`` durable (Linux and macOS; nothing to do on Windows)."""
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace(src: Path, dst: Path) -> None:
    """Rename ``src`` to ``dst`` (replacing it), durably."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # looked up at each call: the tests patch it
        ok = kernel32.MoveFileExW(
            os.fspath(src), os.fspath(dst), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
        )
        if not ok:
            raise ctypes.WinError()
        return
    os.replace(src, dst)
    sync_dir(dst.parent)


def write(path: Path, data: bytes, *, private: bool = False) -> None:
    """``path`` holds ``data`` whole or not at all, durably."""
    part = path.with_name(path.name + ".part")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(part, flags, 0o600 if private else 0o644)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    replace(part, path)
