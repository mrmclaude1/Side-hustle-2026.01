"""Deterministic tests for the analytics engine, run against the bundled
fixture so they pass with zero network access."""

import math

from app import analytics, sources


def test_fixture_loads():
    data = sources.load_fixture()
    assert isinstance(data, list) and len(data) > 50
    assert "instrument_name" in data[0]


def test_to_float_handles_garbage():
    assert analytics.to_float("12.5") == 12.5
    assert analytics.to_float(None) is None
    assert analytics.to_float("") is None
    assert analytics.to_float("abc") is None
    assert analytics.to_float("nan") is None
    assert analytics.to_float("inf") is None


def test_parse_instrument_spot_and_perp():
    assert analytics.parse_instrument("BTC_USDT") == {
        "base": "BTC", "quote": "USDT", "kind": "spot"
    }
    assert analytics.parse_instrument("BTCUSDPERP") == {
        "base": "BTC", "quote": "USD", "kind": "perp"
    }
    assert analytics.parse_instrument("ETHUSDTPERP")["quote"] == "USDT"
    assert analytics.parse_instrument("ETHUSDTPERP")["base"] == "ETH"
    # concatenated spot fallback
    assert analytics.parse_instrument("SOLUSD") == {
        "base": "SOL", "quote": "USD", "kind": "spot"
    }


def test_metrics_basis_and_spread_sign():
    tickers = [
        {"instrument_name": "AAA_USD", "last": "100", "high": "110",
         "low": "90", "best_bid": "99", "best_ask": "101",
         "change": "0.05", "volume_value": "1000", "open_interest": "0"},
        {"instrument_name": "AAAUSDPERP", "last": "101", "high": "112",
         "low": "91", "best_bid": "100.9", "best_ask": "101.1",
         "change": "0.06", "volume_value": "2000", "open_interest": "500"},
    ]
    assets = analytics.build_assets(tickers)
    a = next(x for x in assets if x["base"] == "AAA")
    assert a["has_perp"] and a["has_spot"]
    # perp 101 vs spot 100 -> +100 bps basis
    assert math.isclose(a["basis_bps"], 100.0, rel_tol=1e-6)
    # perp metrics are the reference; range = (112-91)/101*100
    assert math.isclose(a["range_pct"], (112 - 91) / 101 * 100, rel_tol=1e-6)
    assert a["open_interest"] == 500.0


def test_radar_score_bounds_and_monotonicity():
    calm = {"change_pct": 0.1, "basis_bps": 0.5, "range_pct": 0.2, "spread_bps": 2}
    wild = {"change_pct": 18, "basis_bps": 80, "range_pct": 25, "spread_bps": 1}
    sc, sw = analytics.radar_score(calm), analytics.radar_score(wild)
    assert 0 <= sc <= 100 and 0 <= sw <= 100
    assert sw > sc


def test_radar_score_handles_missing_fields():
    assert 0 <= analytics.radar_score({}) <= 100


def test_scan_end_to_end_on_fixture():
    data = sources.load_fixture()
    result = analytics.scan(data, limit=10)
    assert len(result["assets"]) == 10
    # sorted descending by score
    scores = [a["radar_score"] for a in result["assets"]]
    assert scores == sorted(scores, reverse=True)
    s = result["summary"]
    assert s["assets"] >= 10
    assert s["advancers"] + s["decliners"] <= s["assets"]
    assert s["total_volume_usd"] >= 0


def test_scan_min_volume_filter():
    data = sources.load_fixture()
    big = analytics.scan(data, min_volume_usd=1e9)
    for a in big["assets"]:
        assert (a["volume_usd"] or 0) >= 1e9


def test_demo_source_is_fixture():
    snap = sources.get_tickers(force_demo=True)
    assert snap["source"] == "fixture"
    assert len(snap["data"]) > 50
