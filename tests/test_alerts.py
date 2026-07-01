"""Tests for the pure alert engine and its persistence."""

import pytest

from app import alerts, store


def _scan():
    return {"assets": [
        {"base": "BTC", "radar_score": 82.0, "basis_bps": 12.0, "change_pct": 3.0},
        {"base": "DOGE", "radar_score": 40.0, "basis_bps": -70.0, "change_pct": -18.0},
        {"base": "PEPE", "radar_score": 91.0, "basis_bps": None, "change_pct": 22.0},
    ]}


def test_evaluate_asset_basic_ops():
    rule = {"id": 1, "name": "hot", "metric": "radar_score", "op": ">=", "threshold": 80}
    hit = alerts.evaluate_asset(rule, _scan()["assets"][0])
    assert hit["base"] == "BTC" and hit["value"] == 82.0
    miss = alerts.evaluate_asset(rule, _scan()["assets"][1])
    assert miss is None


def test_evaluate_asset_none_metric_skips():
    rule = {"metric": "basis_bps", "op": "<=", "threshold": -50}
    # PEPE has basis None -> cannot fire
    assert alerts.evaluate_asset(rule, _scan()["assets"][2]) is None


def test_abs_metrics():
    rule = {"metric": "abs_change_pct", "op": ">=", "threshold": 15}
    triggers = alerts.evaluate_scan([rule], _scan())
    bases = {t["base"] for t in triggers}
    assert bases == {"DOGE", "PEPE"}  # -18 and +22 both exceed 15


def test_evaluate_scan_sorted_by_margin_and_respects_enabled():
    rules = [
        {"id": 1, "name": "hot", "metric": "radar_score", "op": ">=", "threshold": 80, "enabled": True},
        {"id": 2, "name": "off", "metric": "radar_score", "op": ">=", "threshold": 0, "enabled": False},
    ]
    triggers = alerts.evaluate_scan(rules, _scan())
    # only enabled rule fires; PEPE(91) margin 11 > BTC(82) margin 2
    assert [t["base"] for t in triggers] == ["PEPE", "BTC"]


def test_validate_rule():
    alerts.validate_rule("radar_score", ">=")  # ok
    with pytest.raises(alerts.RuleError):
        alerts.validate_rule("nope", ">=")
    with pytest.raises(alerts.RuleError):
        alerts.validate_rule("radar_score", "==")


def test_rule_persistence_roundtrip():
    conn = store.connect(":memory:")
    r = store.add_rule(conn, "hot", "radar_score", ">=", 80)
    assert r["id"] and r["enabled"] is True
    assert len(store.list_rules(conn)) == 1
    assert store.set_rule_enabled(conn, r["id"], False)
    assert store.list_rules(conn, enabled_only=True) == []
    assert store.delete_rule(conn, r["id"]) is True
    assert store.list_rules(conn) == []


def test_event_persistence():
    conn = store.connect(":memory:")
    triggers = alerts.evaluate_scan(
        [{"id": 1, "name": "hot", "metric": "radar_score", "op": ">=", "threshold": 80}],
        _scan(),
    )
    n = store.record_events(conn, triggers, ts="2026-07-01T00:00:00Z")
    assert n == 2
    events = store.list_events(conn)
    assert len(events) == 2
    assert events[0]["base"] in {"BTC", "PEPE"}
