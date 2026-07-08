"""Alert delivery payload: one JSON body that both Slack ("text") and
Discord ("content", <=2000 chars) accept."""

from app import notify


def _trigger(base="BTC"):
    return {"base": base, "metric": "radar_score", "op": ">=",
            "threshold": 80, "value": 91.2, "rule_name": "hot"}


def test_payload_has_slack_and_discord_fields():
    p = notify.format_payload([_trigger()], ts="2026-01-01T00:00:00Z")
    assert p["text"].startswith("🚨 BasisPulse alerts")
    assert p["content"].startswith("🚨 BasisPulse alerts")
    assert p["count"] == 1 and p["source"] == "basispulse"


def test_discord_content_capped_at_2000():
    many = [_trigger(f"COIN{i}") for i in range(200)]
    p = notify.format_payload(many, ts="t")
    assert len(p["content"]) <= 2000
    assert p["count"] == 200  # full data still in the payload


def test_deliver_noop_without_webhook(monkeypatch):
    monkeypatch.delenv("BASISPULSE_WEBHOOK_URL", raising=False)
    assert notify.deliver([_trigger()], ts="t") == 0
