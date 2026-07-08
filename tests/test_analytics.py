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


def test_v1_short_key_payload_scans():
    """Crypto.com's v1 API returns short field names and dashed perp symbols;
    the key normalizer must make them scannable (live bug: LIVE + 0 assets)."""
    from app import sources

    rows = [
        {"i": "BTC_USD", "a": "58501.2", "b": "58500.4", "k": "58500.5",
         "h": "60218.3", "l": "58094.3", "v": "8309", "vv": "488644688",
         "oi": "0", "c": "-0.0283", "t": 1751326745524},
        {"i": "BTCUSD-PERP", "a": "58490.0", "b": "58489.0", "k": "58491.0",
         "h": "60200.0", "l": "58080.0", "v": "9000", "vv": "500000000",
         "oi": "6069", "c": "-0.0280", "t": 1751326745524},
        {"i": "1INCHUSD", "a": "0.07024", "b": "0.07031", "k": "0.07035",
         "h": "0.07281", "l": "0.07002", "v": "50137", "vv": "3562.40",
         "oi": "0", "c": "-0.0232", "t": 1751326745524},
    ]
    data = sources.normalize_ticker_keys(rows)
    assert all("instrument_name" in t for t in data)
    result = analytics.scan(data, quote="USD")
    assert result["summary"]["assets"] == 2
    btc = next(a for a in result["assets"] if a["base"] == "BTC")
    assert btc["has_perp"] is True and btc["basis_bps"] is not None


def test_fetch_live_rejects_unusable_payload(monkeypatch):
    """A 'successful' fetch with no usable records must raise so get_tickers
    degrades to the fixture instead of rendering an empty LIVE dashboard."""
    import io
    import urllib.request
    from app import sources

    body = b'{"result": {"data": [{"x": 1}, {"y": 2}]}}'
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: __import__("contextlib").nullcontext(io.BytesIO(body)),
    )
    import pytest
    with pytest.raises(ValueError):
        sources.fetch_live()
