"""Exchange adapters.

Each adapter normalises one venue's public ticker data into a common record
shape (see `base.normalized`) so the cross-exchange analytics in
`app.xexchange` can compare the same asset across venues.

Adapters are deliberately import-light (stdlib only) and expose:
    NAME
    live_urls() -> dict            # for docs/debugging
    fetch(timeout) -> list[dict]   # normalized records (raises on network error)
    load_fixture() -> list[dict]   # normalized records from a bundled snapshot
"""

from . import binance, bybit, cryptocom

ADAPTERS = {
    cryptocom.NAME: cryptocom,
    binance.NAME: binance,
    bybit.NAME: bybit,
}

DEFAULT_EXCHANGES = tuple(ADAPTERS)
