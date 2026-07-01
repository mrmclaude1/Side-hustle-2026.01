"""Pure alert-rule evaluation.

A rule fires when a chosen metric of an asset satisfies a comparison against a
threshold (e.g. radar_score >= 80, basis_bps <= -50, abs_change_pct >= 10).
Everything here is pure: rules + a scan in, triggers out. Persistence and
delivery live in store.py / notify.py.
"""

from __future__ import annotations

from typing import Callable, Optional

# Metric name -> how to extract its comparable value from an asset dict.
# Returning None means "not available for this asset" -> the rule can't fire.
_METRICS: dict[str, Callable[[dict], Optional[float]]] = {
    "radar_score": lambda a: a.get("radar_score"),
    "score_delta": lambda a: a.get("score_delta"),
    "basis_bps": lambda a: a.get("basis_bps"),
    "change_pct": lambda a: a.get("change_pct"),
    "abs_change_pct": lambda a: None if a.get("change_pct") is None else abs(a["change_pct"]),
    "abs_basis_bps": lambda a: None if a.get("basis_bps") is None else abs(a["basis_bps"]),
    "range_pct": lambda a: a.get("range_pct"),
    "volume_usd": lambda a: a.get("volume_usd"),
}

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": lambda x, t: x >= t,
    "<=": lambda x, t: x <= t,
    ">": lambda x, t: x > t,
    "<": lambda x, t: x < t,
}

METRICS = tuple(_METRICS)
OPS = tuple(_OPS)


class RuleError(ValueError):
    """Raised when a rule references an unknown metric or operator."""


def validate_rule(metric: str, op: str) -> None:
    if metric not in _METRICS:
        raise RuleError(f"unknown metric {metric!r}; valid: {', '.join(METRICS)}")
    if op not in _OPS:
        raise RuleError(f"unknown op {op!r}; valid: {', '.join(OPS)}")


def evaluate_asset(rule: dict, asset: dict) -> Optional[dict]:
    """Return a trigger dict if `asset` satisfies `rule`, else None."""
    extractor = _METRICS.get(rule["metric"])
    op = _OPS.get(rule["op"])
    if extractor is None or op is None:
        return None
    value = extractor(asset)
    if value is None:
        return None
    if not op(value, rule["threshold"]):
        return None
    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "base": asset.get("base"),
        "metric": rule["metric"],
        "op": rule["op"],
        "threshold": rule["threshold"],
        "value": round(value, 4),
    }


def evaluate_scan(rules: list[dict], scan_result: dict) -> list[dict]:
    """Evaluate all enabled rules against all assets; return triggers.

    Triggers are sorted by how far the value exceeds the threshold (most
    extreme first) so the most notable alerts surface at the top.
    """
    assets = scan_result.get("assets", [])
    triggers: list[dict] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        for a in assets:
            t = evaluate_asset(rule, a)
            if t is not None:
                t["_margin"] = abs(t["value"] - t["threshold"])
                triggers.append(t)
    triggers.sort(key=lambda t: t["_margin"], reverse=True)
    for t in triggers:
        t.pop("_margin", None)
    return triggers
