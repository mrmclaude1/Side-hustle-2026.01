"""Plans, feature gating, and rate limiting.

Two tiers: `free` (what anonymous/browser users get) and `pro` (paid). The
policy here is pure data + pure functions so it is fully unit-testable; the
FastAPI layer in main.py just consults it.
"""

from __future__ import annotations

from typing import Optional

# Feature flags a plan may unlock. Endpoints check membership before serving.
PLANS: dict[str, dict] = {
    "free": {
        "rate_per_min": 120,      # generous enough for the browser dashboard
        "max_scan_limit": 50,     # deep scans are a paid feature
        "max_rules": 3,           # alert rules cap
        "features": {"scan", "cross", "history", "alerts"},
    },
    "pro": {
        "rate_per_min": 1200,
        "max_scan_limit": 1000,
        "max_rules": 1000,
        "features": {
            "scan", "cross", "history", "alerts",
            "pro_signals", "export", "alerts_unlimited",
        },
    },
}

DEFAULT_PLAN = "free"


def plan_config(plan: Optional[str]) -> dict:
    return PLANS.get(plan or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])


def has_feature(plan: Optional[str], feature: str) -> bool:
    return feature in plan_config(plan)["features"]


def clamp_scan_limit(plan: Optional[str], requested: int) -> int:
    return min(requested, plan_config(plan)["max_scan_limit"])


def max_rules(plan: Optional[str]) -> int:
    return plan_config(plan)["max_rules"]


class RateLimiter:
    """Fixed-window per-identity counter. `now` is injected so the logic is
    deterministic under test; main.py passes time.time()."""

    def __init__(self) -> None:
        # identity -> [window_index, count]
        self._hits: dict[str, list] = {}

    def allow(self, identity: str, limit: int, now: float, window: float = 60.0) -> bool:
        w = int(now // window)
        cur = self._hits.get(identity)
        if cur is not None and cur[0] == w:
            if cur[1] >= limit:
                return False
            cur[1] += 1
            return True
        self._hits[identity] = [w, 1]
        return True

    def reset(self) -> None:
        self._hits.clear()
