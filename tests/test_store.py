"""Tests for the SQLite history store — deterministic, in-memory, no clock."""

from app import store


def _scan(scores: dict) -> dict:
    return {"assets": [{"base": b, "radar_score": s, "price": 1.0} for b, s in scores.items()]}


def test_record_and_history_roundtrip():
    conn = store.connect(":memory:")
    store.record_scan(conn, _scan({"BTC": 50.0}), ts="2026-06-30T00:00:00Z")
    store.record_scan(conn, _scan({"BTC": 55.0}), ts="2026-06-30T01:00:00Z")
    hist = store.history(conn, "btc")  # case-insensitive
    assert [p["radar_score"] for p in hist] == [50.0, 55.0]  # oldest-first
    assert hist[0]["ts"] == "2026-06-30T00:00:00Z"


def test_previous_scores_latest():
    conn = store.connect(":memory:")
    store.record_scan(conn, _scan({"BTC": 10.0, "ETH": 20.0}), ts="t1")
    store.record_scan(conn, _scan({"BTC": 30.0}), ts="t2")
    prev = store.previous_scores(conn)
    assert prev == {"BTC": 30.0}


def test_annotate_trend_uses_prior_snapshot():
    conn = store.connect(":memory:")
    store.record_scan(conn, _scan({"BTC": 40.0}), ts="t1")
    new = _scan({"BTC": 47.5, "DOGE": 12.0})
    # Capture baseline BEFORE recording the new scan (mirrors the endpoint).
    baseline = store.previous_scores(conn)
    store.record_scan(conn, new, ts="t2")
    store.annotate_trend(conn, new, baseline=baseline)
    by = {a["base"]: a for a in new["assets"]}
    assert by["BTC"]["score_delta"] == 7.5
    assert by["DOGE"]["score_delta"] is None  # no prior point


def test_annotate_trend_empty_history():
    conn = store.connect(":memory:")
    scan = _scan({"BTC": 50.0})
    store.annotate_trend(conn, scan)
    assert scan["assets"][0]["score_delta"] is None


def test_prune_keeps_most_recent():
    conn = store.connect(":memory:")
    for i in range(5):
        store.record_scan(conn, _scan({"BTC": float(i)}), ts=f"t{i}")
    deleted = store.prune(conn, keep_snapshots=2)
    assert deleted == 3
    remaining = conn.execute("SELECT COUNT(*) AS c FROM snapshots").fetchone()["c"]
    assert remaining == 2
    # The two newest survive.
    hist = store.history(conn, "BTC")
    assert [p["radar_score"] for p in hist] == [3.0, 4.0]


def test_prune_noop_when_under_limit():
    conn = store.connect(":memory:")
    store.record_scan(conn, _scan({"BTC": 1.0}), ts="t1")
    assert store.prune(conn, keep_snapshots=10) == 0
