"""Endpoint tests via FastAPI TestClient. conftest.py forces in-memory DB +
fixture data source before app import."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["data_source"] == "fixture"
    assert "history_snapshots" in body


def test_scan_shape_and_sorted():
    r = client.get("/api/scan?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["assets"]) == 5
    scores = [a["radar_score"] for a in body["assets"]]
    assert scores == sorted(scores, reverse=True)
    # trend annotation present (None until history exists)
    assert "score_delta" in body["assets"][0]


def test_snapshot_then_trend_and_history():
    # First snapshot: no prior -> deltas None.
    s1 = client.get("/api/snapshot").json()
    assert s1["assets_recorded"] > 0
    assert s1["compared_against_prior"] is False
    # Second snapshot: now there is a prior.
    s2 = client.get("/api/snapshot").json()
    assert s2["compared_against_prior"] is True
    # A scan should now carry score_delta values (0.0 since fixture is static).
    body = client.get("/api/scan?limit=3").json()
    deltas = [a["score_delta"] for a in body["assets"]]
    assert any(d is not None for d in deltas)
    # History endpoint returns the recorded points for a known asset.
    base = body["assets"][0]["base"]
    h = client.get(f"/api/history/{base}").json()
    assert h["base"] == base
    assert h["count"] >= 2


def test_asset_lookup_and_404():
    ok = client.get("/api/asset/BTC")
    assert ok.status_code == 200
    assert ok.json()["asset"]["base"] == "BTC"
    assert "history" in ok.json()
    nf = client.get("/api/asset/NOTACOIN")
    assert nf.status_code == 404


def test_landing_dashboard_and_static():
    # "/" is the marketing landing page; the app lives at "/app".
    landing = client.get("/")
    assert landing.status_code == 200
    assert "BasisPulse" in landing.text and "Pricing" in landing.text
    app_page = client.get("/app")
    assert app_page.status_code == 200 and 'id="cross"' in app_page.text
    # "Start here" onboarding tour ships with the dashboard.
    assert 'id="tour"' in app_page.text and "60-second tour" in app_page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/landing.js").status_code == 200


def test_pricing_exposes_checkout_url_field():
    body = client.get("/api/pricing").json()
    assert "checkout_url" in body  # empty until BASISPULSE_CHECKOUT_URL is set


def test_alert_rule_crud_and_validation():
    # metadata endpoint exposes valid metrics/ops
    meta = client.get("/api/alerts").json()
    assert "radar_score" in meta["metrics"] and ">=" in meta["ops"]

    # invalid metric rejected
    bad = client.post("/api/alerts", json={
        "name": "bad", "metric": "nope", "op": ">=", "threshold": 1})
    assert bad.status_code == 400

    # create a valid rule
    created = client.post("/api/alerts", json={
        "name": "hot", "metric": "radar_score", "op": ">=", "threshold": 50})
    assert created.status_code == 201
    rid = created.json()["rule"]["id"]

    # it shows up in the list
    assert any(r["id"] == rid for r in client.get("/api/alerts").json()["rules"])

    # deleting unknown -> 404; deleting real -> ok
    assert client.delete("/api/alerts/999999").status_code == 404
    assert client.delete(f"/api/alerts/{rid}").status_code == 200


def test_exchanges_and_cross():
    ex = client.get("/api/exchanges").json()["exchanges"]
    names = {e["name"] for e in ex}
    assert {"cryptocom", "binance", "bybit"} <= names

    cross = client.get("/api/cross?limit=10").json()
    assert cross["summary"]["assets"] > 0
    assert "binance" in cross["meta"]["sources"]
    btc = next((a for a in cross["assets"] if a["base"] == "BTC"), None)
    assert btc is not None and btc["venue_count"] >= 2
    assert btc["price_spread_bps"] is not None


def test_snapshot_triggers_and_lists_events():
    # A permissive rule guarantees triggers against the fixture.
    r = client.post("/api/alerts", json={
        "name": "any", "metric": "radar_score", "op": ">=", "threshold": 0})
    assert r.status_code == 201
    rid = r.json()["rule"]["id"]

    snap = client.get("/api/snapshot").json()
    assert snap["alerts_triggered"] > 0
    assert snap["alerts_delivered"] == 0  # no webhook configured in tests

    events = client.get("/api/alerts/events?limit=5").json()["events"]
    assert len(events) > 0
    assert "base" in events[0]

    client.delete(f"/api/alerts/{rid}")
