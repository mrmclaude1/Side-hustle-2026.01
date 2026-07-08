"""Pro-tier API: gating, key provisioning, and the billing webhook end-to-end.
conftest sets BASISPULSE_ADMIN_TOKEN=test-admin and disables rate limiting."""

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN = {"X-Admin-Token": "test-admin"}


def _mint_pro_key() -> str:
    r = client.post("/api/keys", headers=ADMIN, json={"plan": "pro", "label": "t"})
    assert r.status_code == 201
    return r.json()["key"]["key"]


def test_pricing_and_me():
    pricing = client.get("/api/pricing").json()["plans"]
    assert "free" in pricing and "pro" in pricing
    # Pro card price is surfaced for the landing/dashboard pricing cards.
    assert pricing["pro"]["price_usd_month"]
    me = client.get("/api/me").json()
    assert me["plan"] == "free" and me["authenticated"] is False


def test_invalid_key_rejected():
    assert client.get("/api/me", headers={"X-API-Key": "bp_bogus"}).status_code == 401


def test_free_scan_limit_capped():
    body = client.get("/api/scan?limit=500").json()
    assert len(body["assets"]) <= 50
    assert body["meta"]["limit_capped_to"] == 50


def test_pro_signals_gated_then_allowed():
    assert client.get("/api/pro/signals").status_code == 402  # anonymous/free
    key = _mint_pro_key()
    r = client.get("/api/pro/signals?limit=5", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert "score_percentile" in r.json()["assets"][0]
    assert r.json()["meta"]["plan"] == "pro"


def test_pro_scan_not_capped():
    key = _mint_pro_key()
    body = client.get("/api/scan?limit=200", headers={"X-API-Key": key}).json()
    assert "limit_capped_to" not in body["meta"]


def test_csv_export_gated():
    assert client.get("/api/export.csv").status_code == 402
    key = _mint_pro_key()
    r = client.get("/api/export.csv", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("base,radar_score")


def test_self_serve_key_is_free_only():
    # Without admin token, requesting "pro" still yields a free key.
    r = client.post("/api/keys", json={"plan": "pro"})
    assert r.status_code == 201
    assert r.json()["key"]["plan"] == "free"


def test_webhook_upgrade_flow():
    # 1. user self-serves a free key
    key = client.post("/api/keys", json={}).json()["key"]["key"]
    assert client.get("/api/me", headers={"X-API-Key": key}).json()["plan"] == "free"
    # 2. Stripe checkout completes carrying that key (no signing secret in tests)
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_flow", "client_reference_id": key}},
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event))
    assert res.status_code == 200 and res.json()["plan"] == "pro"
    # 3. the key is now Pro
    assert client.get("/api/me", headers={"X-API-Key": key}).json()["plan"] == "pro"
    # 4. cancellation downgrades
    cancel = {"type": "customer.subscription.deleted",
              "data": {"object": {"customer": "cus_flow"}}}
    client.post("/api/billing/webhook", content=json.dumps(cancel))
    assert client.get("/api/me", headers={"X-API-Key": key}).json()["plan"] == "free"
