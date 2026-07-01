"""Bybit v5 adapter: spot + linear (USDT perpetual) tickers.

Endpoints (public, keyless):
  spot    GET https://api.bybit.com/v5/market/tickers?category=spot
  linear  GET https://api.bybit.com/v5/market/tickers?category=linear

Both return {"result": {"list": [ ... ]}}. `price24hPcnt` is a fraction; the
linear category also carries `openInterest` and `turnover24h` (USD volume).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import base

NAME = "bybit"
SPOT_URL = "https://api.bybit.com/v5/market/tickers?category=spot"
LINEAR_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bybit.json"

_KEEP_QUOTES = ("USDT", "USDC")


def live_urls() -> dict:
    return {"spot": SPOT_URL, "perp": LINEAR_URL}


def _normalize(rows: list[dict], kind: str) -> list[dict]:
    out = []
    for t in rows:
        base_sym, quote = base.split_symbol(t.get("symbol", ""))
        if not base_sym or quote not in _KEEP_QUOTES:
            continue
        pcnt = t.get("price24hPcnt")
        change_pct = None if pcnt in (None, "") else float(pcnt) * 100.0
        out.append(
            base.normalized(
                NAME, base_sym, quote, kind,
                price=t.get("lastPrice"),
                change_pct=change_pct,
                high=t.get("highPrice24h"), low=t.get("lowPrice24h"),
                bid=t.get("bid1Price"), ask=t.get("ask1Price"),
                volume_usd=t.get("turnover24h"),
                open_interest=t.get("openInterest") if kind == "perp" else None,
            )
        )
    return out


def _extract(payload: dict) -> list[dict]:
    return payload.get("result", {}).get("list", []) or []


def fetch(timeout: float = 10.0) -> list[dict]:
    spot = _extract(base.fetch_json(SPOT_URL, timeout=timeout))
    linear = _extract(base.fetch_json(LINEAR_URL, timeout=timeout))
    return _normalize(spot, "spot") + _normalize(linear, "perp")


def load_fixture() -> list[dict]:
    with _FIXTURE.open() as fh:
        raw = json.load(fh)
    return _normalize(_extract(raw["spot"]), "spot") + _normalize(_extract(raw["linear"]), "perp")
