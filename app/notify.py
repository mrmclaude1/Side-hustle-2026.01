"""Alert delivery.

If PERP_RADAR_WEBHOOK_URL is set, triggered alerts are POSTed there as JSON.
This is intentionally generic — it works with Discord/Slack incoming webhooks,
a Telegram relay, or any HTTP endpoint — and needs no secret baked into the
code. When the env var is unset, delivery is a no-op (returns 0) so the app
runs fine without any external integration.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional


def webhook_url() -> Optional[str]:
    url = os.environ.get("PERP_RADAR_WEBHOOK_URL", "").strip()
    return url or None


def format_payload(triggers: list[dict], ts: str) -> dict:
    lines = [
        f"{t['base']}: {t['metric']} {t['op']} {t['threshold']} "
        f"(value {t['value']}) [{t.get('rule_name')}]"
        for t in triggers
    ]
    return {
        "source": "perp-radar",
        "ts": ts,
        "count": len(triggers),
        "text": "🚨 Perp Radar alerts\n" + "\n".join(lines),
        "triggers": triggers,
    }


def deliver(triggers: list[dict], ts: str, timeout: float = 8.0) -> int:
    """POST triggers to the configured webhook. Returns number delivered
    (0 if no webhook configured or nothing to send). Never raises: delivery
    failures are swallowed so a bad webhook can't break the scan pipeline."""
    url = webhook_url()
    if not url or not triggers:
        return 0
    body = json.dumps(format_payload(triggers, ts)).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return len(triggers)
    except Exception:
        return 0
