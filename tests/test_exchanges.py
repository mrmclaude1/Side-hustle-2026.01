"""Adapter normalization + cross-exchange analytics, driven by bundled
fixtures (no network)."""

from app import sources, xexchange
from app.exchanges import base, binance, bybit, cryptocom


def test_split_symbol_forms():
    assert base.split_symbol("BTC_USDT") == ("BTC", "USDT")
    assert base.split_symbol("BTCUSDT") == ("BTC", "USDT")
    assert base.split_symbol("ETHBTC") == ("ETH", "BTC")
    assert base.split_symbol("BTC-USD") == ("BTC", "USD")


def test_binance_fixture_normalizes():
    recs = binance.load_fixture()
    btc_spot = [r for r in recs if r["base"] == "BTC" and r["kind"] == "spot"]
    assert btc_spot and btc_spot[0]["exchange"] == "binance"
    assert btc_spot[0]["price"] == 58540.10
    assert btc_spot[0]["change_pct"] == -2.75  # already a percent
    # ETHBTC quote filtered out (only USDT/USDC/FDUSD kept)
    assert not any(r["base"] == "ETH" and r["quote"] == "BTC" for r in recs)
    # perp present, no bid/ask
    btc_perp = [r for r in recs if r["base"] == "BTC" and r["kind"] == "perp"][0]
    assert btc_perp["bid"] is None and btc_perp["price"] == 58525.00


def test_bybit_fixture_normalizes_with_oi():
    recs = bybit.load_fixture()
    btc_perp = [r for r in recs if r["base"] == "BTC" and r["kind"] == "perp"][0]
    assert btc_perp["exchange"] == "bybit"
    assert btc_perp["open_interest"] == 51234.5
    # price24hPcnt fraction -> percent
    assert round(btc_perp["change_pct"], 2) == -2.72


def test_cryptocom_fixture_normalizes():
    recs = cryptocom.load_fixture()
    assert recs and all("exchange" in r for r in recs)
    assert any(r["kind"] == "perp" for r in recs)
    assert any(r["kind"] == "spot" for r in recs)


def test_cross_scan_dispersion_and_arb():
    records = binance.load_fixture() + bybit.load_fixture() + cryptocom.load_fixture()
    result = xexchange.cross_scan(records, min_venues=2)
    assert result["summary"]["assets"] > 0
    assert "binance" in result["summary"]["venues"]
    btc = next(a for a in result["assets"] if a["base"] == "BTC")
    assert btc["venue_count"] >= 2
    # BTC spot prices differ across venues -> positive spread
    assert btc["price_spread_bps"] > 0
    assert set(btc["spot_prices"]) & {"binance", "bybit"}
    # arb object present with a defined direction
    assert btc["arb"]["buy_at"] != btc["arb"]["sell_at"]


def test_cross_scan_min_venues_filter():
    # A single-venue record should be excluded at min_venues=2.
    records = [
        base.normalized("binance", "LONELY", "USDT", "spot", price=1.0),
    ]
    result = xexchange.cross_scan(records, min_venues=2)
    assert all(a["base"] != "LONELY" for a in result["assets"])


def test_get_records_demo_uses_fixtures():
    snap = sources.get_records(force_demo=True)
    assert snap["sources"] == {"cryptocom": "fixture", "binance": "fixture", "bybit": "fixture"}
    assert len(snap["records"]) > 100
