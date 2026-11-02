"""Deterministic JSON serialisation (UTF-8, ``ensure_ascii=False``, ``\\n`` line endings on every OS)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dumps_bytes(obj: Any, *, indent: int | None = 2, sort_keys: bool = False) -> bytes:
    text = json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=sort_keys)
    return (text + "\n").encode("utf-8")


def write_json(path: Path, obj: Any, *, indent: int | None = 2, sort_keys: bool = False) -> bytes:
    data = dumps_bytes(obj, indent=indent, sort_keys=sort_keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)  # bytes: no newline translation on Windows
    return data


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8"))
