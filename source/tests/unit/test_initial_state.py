from __future__ import annotations

import pytest

from marianos_headless.sites.marianos.initial_state import (
    InitialStateNotFound,
    decode_js_single_quoted,
    dig,
    parse_initial_state,
)


def test_decode_js_escapes() -> None:
    # Inputs spell JS escapes with a doubled backslash so tools cannot fold them into literals.
    assert decode_js_single_quoted("Mariano\\u2019s") == "Mariano\N{RIGHT SINGLE QUOTATION MARK}s"
    assert decode_js_single_quoted(r"it\'s") == "it's"
    assert decode_js_single_quoted(r'a\\"b') == 'a\\"b'
    assert decode_js_single_quoted("\\ud83d\\ude00") == "\N{GRINNING FACE}"  # surrogate pair
    assert decode_js_single_quoted(r"\x41\n") == "A\n"


def test_parse_initial_state_roundtrip() -> None:
    html = (
        '<script>window.__INITIAL_STATE__ = JSON.parse(\'{"head":{"title":"Mariano\\u2019s"},'
        '"q":"a\\\\"b","s":"it\\\'s"}\')\n window.__BANNER_NAME__ = "x"</script>'
    )
    state = parse_initial_state(html)
    assert state["head"]["title"] == "Mariano’s"
    assert state["q"] == 'a"b'
    assert state["s"] == "it's"
    assert dig(state, "head", "title") == "Mariano’s"
    assert dig(state, "head", "missing", default="d") == "d"


def test_missing_state_is_an_error() -> None:
    with pytest.raises(InitialStateNotFound):
        parse_initial_state("<html><body>Access Denied Reference #18.abc</body></html>")
