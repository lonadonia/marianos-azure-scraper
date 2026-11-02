"""The source revision that collects, recorded with every run.

In a container the revision comes from ``BUILD_INFO.json`` written at image build time (``docker build
--build-arg SOURCE_COMMIT=…``) or from the ``MARIANOS_COLLECTOR_SOURCE_COMMIT`` environment variable; in a
git checkout from git itself. "unknown" when none is available (never guessed).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from marianos_headless.core.paths import PROJECT_ROOT

ENV = "MARIANOS_COLLECTOR_SOURCE_COMMIT"
BUILD_INFO = "BUILD_INFO.json"


def source_version() -> dict[str, Any]:
    env = (os.environ.get(ENV) or "").strip()
    if env:
        return {"commit": env, "source": "environment"}
    for base in (Path.cwd(), PROJECT_ROOT):
        info = base / BUILD_INFO
        if info.is_file():
            try:
                data = json.loads(info.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            commit = str(data.get("commit") or "").strip()
            if commit:
                return {"commit": commit, "source": "build_info", "built_at": data.get("built_at")}
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        commit = out.stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "."],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        return {"commit": commit, "source": "git", "uncommitted_changes": bool(dirty)}
    except (OSError, subprocess.SubprocessError):
        return {"commit": "unknown", "source": "none"}
