"""Release 1.10.0rc6: a run's row order and its named product pages from the command line, as overrides
recorded with the run (``--rows-first``, ``--term-upc``). Fails on 1.10.0rc5, which has neither."""

from __future__ import annotations

from marianos_headless import operations
from marianos_headless.cli import build_parser
from marianos_headless.config_file import StoreCollection


def test_rc6_run_takes_a_row_order_and_named_product_pages() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--store",
            "marianos-53100502-pickup",
            "--rows-first",
            "22,27,22,15",
            "--term-upc",
            "0001780014939",
            "--term-upc",
            "0003980014995",
        ]
    )
    assert args.rows_first == [22, 27, 15]
    assert args.term_upc == ["0001780014939", "0003980014995"]


def test_rc6_the_overrides_reach_the_runs_collection_settings() -> None:
    coll = operations._overrides(
        StoreCollection(), {"rows_first": [22, 27], "product_term_upcs": ["0001780014939"]}
    )
    assert coll.rows_first == [22, 27] and coll.categories == []
    assert coll.limits.product_term_upcs == ["0001780014939"] and not coll.limits.bounded()
