"""Stripe billing seam.

Everything here works without the `stripe` SDK and without a live account so it
is fully testable. When you go live you set two env vars and point a Stripe
webhook at POST /api/billing/webhook:

    STRIPE_WEBHOOK_SECRET   # verifies incoming webhooks (whsec_...)
    BASISPULSE_ADMIN_TOKEN  # protects manual key provisioning

Upgrade flow (no code changes needed):
  1. A user creates a free API key (POST /api/keys or the dashboard).
  2. They subscribe via a Stripe Checkout link that carries their key in
     `client_reference_id` (or metadata.basispulse_key).
  3. Stripe fires `checkout.session.completed` / subscription events →
     apply_stripe_event upgrades that key to `pro` and maps it to the customer.
  4. `customer.subscription.deleted` (or a canceled status) downgrades to free.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from . import store


def webhook_secret() -> Optional[str]:
    s = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    return s or None


def _parse_sig_header(header: str) -> dict:
    """Parse a `t=...,v1=...` Stripe-Signature header into {t, v1:[...]}."""
    out: dict = {"t": None, "v1": []}
    for part in (header or "").split(","):
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k == "t":
            out["t"] = v.strip()
        elif k == "v1":
            out["v1"].append(v.strip())
    return out


def verify_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    now: Optional[float] = None,
    tolerance: float = 300.0,
) -> bool:
    """Verify a Stripe webhook signature (the v1 scheme).

    signed_payload = f"{t}.{payload}"; expected = HMAC-SHA256(secret, ...).
    When `now` is given, also enforce the timestamp tolerance (replay guard).
    """
    parsed = _parse_sig_header(sig_header)
    t, v1s = parsed["t"], parsed["v1"]
    if not t or not v1s:
        return False
    try:
        ts = int(t)
    except ValueError:
        return False
    if now is not None and abs(now - ts) > tolerance:
        return False
    signed = f"{t}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in v1s)


def _extract_key_hint(obj: dict) -> Optional[str]:
    """Pull an existing API key out of a Stripe object if the checkout carried
    one (client_reference_id or metadata.basispulse_key)."""
    ref = obj.get("client_reference_id")
    if isinstance(ref, str) and ref.startswith("bp_"):
        return ref
    meta = obj.get("metadata") or {}
    k = meta.get("basispulse_key")
    return k if isinstance(k, str) and k.startswith("bp_") else None


# Statuses that mean "no longer entitled".
_INACTIVE_STATUSES = {"canceled", "unpaid", "incomplete_expired", "past_due"}


def apply_stripe_event(conn, event: dict, ts: Optional[str] = None) -> dict:
    """Apply a Stripe event to the key store. Returns a summary of the action.

    Handles checkout completion and subscription lifecycle events. Unknown event
    types are acknowledged as no-ops (Stripe sends many).
    """
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    customer = obj.get("customer")
    key_hint = _extract_key_hint(obj)

    def _target_pro() -> dict:
        # Prefer upgrading the specific key the checkout referenced.
        if key_hint and store.key_is_known(conn, key_hint):
            store.set_key_plan(conn, key_hint, "pro")
            if customer:
                store.map_key_to_customer(conn, key_hint, customer)
            return {"action": "upgraded", "key": key_hint, "plan": "pro"}
        if customer:
            rec = store.upsert_key_for_customer(conn, customer, "pro", ts=ts)
            return {"action": "upgraded", "key": rec["key"], "plan": "pro"}
        return {"action": "noop", "reason": "no customer or key"}

    def _downgrade() -> dict:
        if customer:
            rec = store.upsert_key_for_customer(conn, customer, "free", ts=ts)
            return {"action": "downgraded", "key": rec["key"], "plan": "free"}
        if key_hint and store.key_is_known(conn, key_hint):
            store.set_key_plan(conn, key_hint, "free")
            return {"action": "downgraded", "key": key_hint, "plan": "free"}
        return {"action": "noop", "reason": "no customer or key"}

    if etype in ("checkout.session.completed",
                 "customer.subscription.created",
                 "customer.subscription.updated"):
        status = obj.get("status")
        if status in _INACTIVE_STATUSES:
            return {"type": etype, **_downgrade()}
        return {"type": etype, **_target_pro()}

    if etype == "customer.subscription.deleted":
        return {"type": etype, **_downgrade()}

    return {"type": etype, "action": "ignored"}
