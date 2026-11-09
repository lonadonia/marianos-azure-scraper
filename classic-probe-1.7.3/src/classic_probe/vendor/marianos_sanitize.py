"""Sanitise saved or captured Mariano's documents (brief §5.10, §17).

Removes script bodies (except the ``__INITIAL_STATE__`` script), browser-extension artifacts
(``chrome-extension://`` scripts, ``bis_*`` attributes), stylesheet bodies and inlined ``data:`` URIs.
The output keeps every element and attribute the DOM parsers read.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser

from classic_probe.vendor.marianos_initial_state import parse_initial_state

_DATA_URI_ATTRS = ("src", "srcset", "href", "poster", "data-src", "data-srcset")
_CSS_DATA_URI = re.compile(r"url\((['\"]?)data:[^)]*\1\)")
STATE_MARKER = "window.__INITIAL_STATE__"


@dataclass(frozen=True)
class SanitizeReport:
    input_bytes: int
    output_bytes: int
    input_sha256: str
    output_sha256: str
    scripts_removed: int
    extension_scripts_removed: int
    styles_emptied: int
    data_uris_replaced: int
    extension_attrs_removed: int
    state_script_kept: bool


def sanitize_html(html: str) -> tuple[str, SanitizeReport]:
    tree = LexborHTMLParser(html)
    scripts_removed = ext_scripts = styles = data_uris = ext_attrs = 0
    state_kept = False

    for node in tree.css("script"):
        src = node.attributes.get("src") or ""
        if src.startswith("chrome-extension://") or node.attributes.get("bis_use") is not None:
            node.decompose()
            ext_scripts += 1
            continue
        body = node.text(deep=True) or ""
        if STATE_MARKER in body and "JSON.parse" in body:
            state_kept = True
            continue
        if node.attributes.get("type") == "application/ld+json":
            continue  # small, structured and useful (Organization logo, site search)
        node.decompose()
        scripts_removed += 1

    for node in tree.css("style"):
        node.decompose()  # CSS is not needed by any parser
        styles += 1

    for node in tree.root.traverse() if tree.root is not None else ():
        attrs = node.attributes
        if not attrs:
            continue
        for name in list(attrs):
            if name.startswith("bis_") or name == "data-dynamic-id":
                del node.attrs[name]
                ext_attrs += 1
                continue
            value = attrs.get(name) or ""
            if name in _DATA_URI_ATTRS and "data:" in value:
                node.attrs[name] = "data:"
                data_uris += 1
            elif name == "style" and "data:" in value:
                node.attrs[name] = _CSS_DATA_URI.sub("url(data:)", value)
                data_uris += 1

    out = tree.html or ""
    report = SanitizeReport(
        input_bytes=len(html.encode("utf-8")),
        output_bytes=len(out.encode("utf-8")),
        input_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        output_sha256=hashlib.sha256(out.encode("utf-8")).hexdigest(),
        scripts_removed=scripts_removed,
        extension_scripts_removed=ext_scripts,
        styles_emptied=styles,
        data_uris_replaced=data_uris,
        extension_attrs_removed=ext_attrs,
        state_script_kept=state_kept,
    )
    return out, report


def extract_state_json(html: str) -> str:
    """Pretty-printed ``__INITIAL_STATE__`` for fixtures and review."""
    return json.dumps(parse_initial_state(html), ensure_ascii=False, indent=1, sort_keys=False)
