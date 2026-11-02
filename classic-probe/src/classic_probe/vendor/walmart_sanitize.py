"""Sanitise saved Walmart documents before they are stored as evidence.

Kept: the page data every Walmart parser reads (``<script id="__NEXT_DATA__">``) and JSON-LD. Removed:
every other script body, stylesheet bodies and inlined ``data:`` URIs (as for Mariano's pages).

Inside the page data, values that could identify the browsing session or a person are replaced with
``"[REDACTED]"``: keys that name tokens, CSRF values, secrets, cookies, sessions (any key ending in
``session`` or ``session id``, camelCase included: ``isomorphicSessionId`` and ``adSessionId``, which
release 1.3.0 kept), request trace IDs (``traceId``, ``spanId``, ``renderViewId``), customer, account,
device or visitor IDs, IP addresses, e-mail addresses or phone numbers (:data:`REDACT_KEY`), and any
string value that is an IP address. Hidden form inputs and ``<meta>`` tags with such names lose their
values too. Product, price, store and fulfillment data are not touched. The page data is written back
as compact JSON with ``<``, ``>`` and ``&`` escaped (as Next.js serves it), so it stays a valid script.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any

from selectolax.lexbor import LexborHTMLParser

REDACTED = "[REDACTED]"
REDACT_KEY = re.compile(
    r"^(?:.*(?:token|csrf|xsrf|secret|password|passwd|cookie|authorization|bearer|api[_-]?key).*"
    r"|.*session(?:[_-]?id)?|sid|acid|cid|vid|uid|pxvid|pxcts|pxhd"
    r"|(?:customer|cust|account|device|visitor|user|guest|shopper|member|profile)[_-]?id"
    r"|(?:trace|span|render[_-]?view)[_-]?id"
    r"|ip|ip[_-]?addr(?:ess)?|client[_-]?ip|remote[_-]?addr(?:ess)?|x[_-]?forwarded[_-]?for"
    r"|e[_-]?mail(?:[_-]?address)?|phone(?:[_-]?number)?)$",
    re.I,
)
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
# Third-party API keys the site embeds for its own browser use (e.g. Google Maps keys): not needed by any
# parser and not to be redistributed in evidence.
API_KEY_VALUE = re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")
_IPV6 = re.compile(r"^(?=(?:[^:]*:){3})[0-9a-fA-F:]{6,39}$|^[0-9a-fA-F]*::[0-9a-fA-F:]*$")
_NEXT_DATA = re.compile(
    r"(<script[^>]*\bid=[\"']__NEXT_DATA__[\"'][^>]*>)(?P<json>.*?)(</script>)", re.S | re.I
)
_DATA_URI_ATTRS = ("src", "srcset", "href", "poster", "data-src", "data-srcset")
_CSS_DATA_URI = re.compile(r"url\((['\"]?)data:[^)]*\1\)")


@dataclass(frozen=True)
class SanitizeReport:
    input_bytes: int
    output_bytes: int
    input_sha256: str
    output_sha256: str
    scripts_removed: int
    styles_removed: int
    data_uris_replaced: int
    page_data_kept: bool
    page_data_values_redacted: int
    other_values_redacted: int


def _is_ip(value: str) -> bool:
    if _IPV4.match(value):
        return True
    if not _IPV6.match(value):
        return False
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return False  # e.g. a category path "0:976759:976793:9756351" (groups longer than four digits)
    return True


def redact(obj: Any) -> int:
    """Redact identifying values in place; returns how many were replaced."""
    n = 0
    if isinstance(obj, dict):
        for key in list(obj):
            value = obj[key]
            named = bool(REDACT_KEY.match(str(key))) and value not in (None, "", [], {}, REDACTED)
            if named or (isinstance(value, str) and (_is_ip(value.strip()) or API_KEY_VALUE.search(value))):
                obj[key] = REDACTED
                n += 1
            else:
                n += redact(value)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            if isinstance(value, str) and (_is_ip(value.strip()) or API_KEY_VALUE.search(value)):
                obj[i] = REDACTED
                n += 1
            else:
                n += redact(value)
    return n


def page_data_json(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def redact_page_data(html: str) -> tuple[str, bool, int]:
    """(html, page data kept, values redacted). Unreadable page data is dropped, never kept unredacted."""
    m = _NEXT_DATA.search(html)
    if m is None:
        return html, False, 0
    try:
        data = json.loads(m.group("json"))
    except ValueError:
        return html[: m.start("json")] + html[m.end("json") :], False, 0
    n = redact(data)
    return html[: m.start("json")] + page_data_json(data) + html[m.end("json") :], True, n


def sanitize_html(html: str) -> tuple[str, SanitizeReport]:
    redacted, kept, page_n = redact_page_data(html)
    tree = LexborHTMLParser(redacted)
    scripts = styles = data_uris = other_n = 0
    for node in tree.css("script"):
        if node.attributes.get("id") == "__NEXT_DATA__" and kept:
            continue
        if node.attributes.get("type") == "application/ld+json":
            continue
        node.decompose()
        scripts += 1
    for node in tree.css("style"):
        node.decompose()
        styles += 1
    for node in tree.css("input[type=hidden], meta"):
        name = node.attributes.get("name") or node.attributes.get("id") or ""
        attr = "content" if node.tag == "meta" else "value"
        if name and REDACT_KEY.match(name) and node.attributes.get(attr):
            node.attrs[attr] = REDACTED
            other_n += 1
    for node in tree.root.traverse() if tree.root is not None else ():
        attrs = node.attributes
        if not attrs:
            continue
        for name in list(attrs):
            value = attrs.get(name) or ""
            if name in _DATA_URI_ATTRS and "data:" in value:
                node.attrs[name] = "data:"
                data_uris += 1
            elif name == "style" and "data:" in value:
                node.attrs[name] = _CSS_DATA_URI.sub("url(data:)", value)
                data_uris += 1
    out = tree.html or ""
    out, n_keys = API_KEY_VALUE.subn(REDACTED, out)  # any left in attributes or kept text
    other_n += n_keys
    return out, SanitizeReport(
        input_bytes=len(html.encode("utf-8")),
        output_bytes=len(out.encode("utf-8")),
        input_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        output_sha256=hashlib.sha256(out.encode("utf-8")).hexdigest(),
        scripts_removed=scripts,
        styles_removed=styles,
        data_uris_replaced=data_uris,
        page_data_kept=kept,
        page_data_values_redacted=page_n,
        other_values_redacted=other_n,
    )
