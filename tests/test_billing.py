"""Stripe signature verification + event application (no live account)."""

import hashlib
import hmac

from app import billing, store


def _sign(payload: bytes, secret: str, t: int = 1700000000) -> str:
    signed = f"{t}.".encode() + payload
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def test_verify_signature_ok_and_tamper():
    secret = "whsec_test"
    payload = b'{"hello":"world"}'
    header = _sign(payload, secret)
    assert billing.verify_signature(payload, header, secret) is True
    # tampered payload fails
    assert billing.verify_signature(payload + b"x", header, secret) is False
    # wrong secret fails
    assert billing.verify_signature(payload, header, "whsec_other") is False
    # malformed header fails
    assert billing.verify_signature(payload, "garbage", secret) is False


def test_verify_signature_timestamp_tolerance():
    secret = "whsec_test"
    payload = b"{}"
    header = _sign(payload, secret, t=1000)
    # now far from t -> outside tolerance
    assert billing.verify_signature(payload, header, secret, now=1000 + 10_000) is False
    # within tolerance
    assert billing.verify_signature(payload, header, secret, now=1000 + 10) is True


def test_apply_event_upgrades_by_key_hint():
    conn = store.connect(":memory:")
    free = store.create_key(conn, plan="free")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "customer": "cus_123",
            "client_reference_id": free["key"],
        }},
    }
    res = billing.apply_stripe_event(conn, event)
    assert res["action"] == "upgraded" and res["plan"] == "pro"
    assert store.resolve_plan(conn, free["key"]) == "pro"


def test_apply_event_upserts_by_customer_and_downgrades():
    conn = store.connect(":memory:")
    up = billing.apply_stripe_event(conn, {
        "type": "customer.subscription.created",
        "data": {"object": {"customer": "cus_999", "status": "active"}},
    })
    assert up["plan"] == "pro"
    key = up["key"]
    assert store.resolve_plan(conn, key) == "pro"

    down = billing.apply_stripe_event(conn, {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_999"}},
    })
    assert down["plan"] == "free"
    assert store.resolve_plan(conn, key) == "free"


def test_apply_event_ignores_unknown_types():
    conn = store.connect(":memory:")
    res = billing.apply_stripe_event(conn, {"type": "invoice.paid", "data": {"object": {}}})
    assert res["action"] == "ignored"
