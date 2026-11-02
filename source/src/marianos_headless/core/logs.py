"""Structured, machine-readable logs: one JSON object per line on standard output.

In Azure Container Apps standard output goes to the environment's Log Analytics workspace
(``ContainerAppConsoleLogs_CL``); every line can be queried by its fields. Each line has ``ts`` (UTC),
``level``, ``event``, the collector's name, and the run's fields when there is a run. Secrets are never
passed to the logger (keys are referred to only by a short fingerprint).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

COLLECTOR = "marianos-azure-headless"
_stream: TextIO = sys.stdout
_min_level = 20
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40}


def configure(stream: TextIO | None = None, level: str = "INFO") -> None:
    global _stream, _min_level
    _stream = stream or sys.stdout
    _min_level = _LEVELS.get(level.upper(), 20)


def log(level: str, event: str, **fields: Any) -> None:
    if _LEVELS.get(level.upper(), 20) < _min_level:
        return
    line = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": level.upper(),
        "event": event,
        "collector": COLLECTOR,
        **fields,
    }
    try:
        _stream.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        _stream.flush()
    except (OSError, ValueError):
        pass  # a closed stream never stops a run
