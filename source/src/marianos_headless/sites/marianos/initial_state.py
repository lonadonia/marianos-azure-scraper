"""Extract and decode ``window.__INITIAL_STATE__ = JSON.parse('…')`` from a Mariano's document.

The site serialises its server-rendered Redux state as a JSON document wrapped in a single-quoted
JavaScript string literal. JS string escapes (``\\uXXXX``, ``\\'``, ``\\\\`` …) must be decoded
before the result is valid JSON (brief Appendix B).
"""

from __future__ import annotations

import json
import re
from typing import Any

_MARKER = re.compile(r"window\.__INITIAL_STATE__\s*=\s*JSON\.parse\('")

_SIMPLE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
    "'": "'",
    '"': '"',
    "\\": "\\",
    "/": "/",
    "\n": "",  # line continuation
}


class InitialStateNotFound(ValueError):
    """The document has no ``__INITIAL_STATE__`` assignment (a challenge page, shell or wrong page)."""


def extract_js_literal(html: str) -> str:
    """Return the raw (still escaped) contents of the ``JSON.parse('…')`` string literal."""
    m = _MARKER.search(html)
    if m is None:
        raise InitialStateNotFound("window.__INITIAL_STATE__ = JSON.parse('…') not found")
    start = m.end()
    i = start
    n = len(html)
    while i < n:
        ch = html[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            return html[start:i]
        i += 1
    raise InitialStateNotFound("unterminated __INITIAL_STATE__ string literal")


def decode_js_single_quoted(raw: str) -> str:
    """Decode the escapes of a JavaScript string literal body into a Python ``str``."""
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\":
            j = raw.find("\\", i)
            if j == -1:
                out.append(raw[i:])
                break
            out.append(raw[i:j])
            i = j
            continue
        if i + 1 >= n:
            raise ValueError("dangling backslash at end of JS string literal")
        esc = raw[i + 1]
        if esc == "u":
            if i + 2 < n and raw[i + 2] == "{":
                close = raw.index("}", i + 3)
                out.append(chr(int(raw[i + 3 : close], 16)))
                i = close + 1
                continue
            code = int(raw[i + 2 : i + 6], 16)
            i += 6
            if 0xD800 <= code <= 0xDBFF and raw.startswith("\\u", i):
                low = int(raw[i + 2 : i + 6], 16)
                if 0xDC00 <= low <= 0xDFFF:
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                    i += 6
            out.append(chr(code))
            continue
        if esc == "x":
            out.append(chr(int(raw[i + 2 : i + 4], 16)))
            i += 4
            continue
        out.append(_SIMPLE_ESCAPES.get(esc, esc))
        i += 2
    return "".join(out)


def parse_initial_state(html: str) -> dict[str, Any]:
    """Return the decoded ``__INITIAL_STATE__`` object."""
    decoded = decode_js_single_quoted(extract_js_literal(html))
    state = json.loads(decoded)
    if not isinstance(state, dict):
        raise InitialStateNotFound("__INITIAL_STATE__ is not a JSON object")
    return state


def dig(obj: Any, *path: str | int, default: Any = None) -> Any:
    """Safe nested lookup: ``dig(state, "meta", "siteVersion")``."""
    cur = obj
    for key in path:
        if isinstance(key, int):
            if not isinstance(cur, list) or key >= len(cur) or key < -len(cur):
                return default
            cur = cur[key]
        else:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
    return cur
