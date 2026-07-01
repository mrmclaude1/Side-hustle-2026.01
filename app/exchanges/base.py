"""Shared helpers for exchange adapters: the normalized record shape, a symbol
splitter, and a JSON fetch over stdlib urllib (honours HTTPS_PROXY)."""

from __future__ import annotations

import json
import urllib.request
from typing import Optional

from ..analytics import to_float

# Longest-first so USDT matches before USD when splitting "BTCUSDT".
QUOTES = ("USDT", "USDC", "USD", "FDUSD", "TUSD", "DAI", "BTC", "ETH", "EUR", "GBP")


def split_symbol(symbol: str, sep: Optional[str] = None) -> tuple[str, str]:
    """Split an exchange symbol into (base, quote).

    Handles separated ("BTC_USDT", "BTC-USDT") and concatenated ("BTCUSDT")
    forms. Returns (symbol, "") when no known quote can be identified.
    """
    s = (symbol or "").upper()
    if sep and sep in s:
        base, _, quote = s.partition(sep)
        return base, quote
    for ch in ("_", "-", "/"):
        if ch in s:
            base, _, quote = s.partition(ch)
            return base, quote
    for q in QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)], q
    return s, ""


def normalized(
    exchange: str,
    base: str,
    quote: str,
    kind: str,
    price=None,
    change_pct=None,
    high=None,
    low=None,
    bid=None,
    ask=None,
    volume_usd=None,
    open_interest=None,
) -> dict:
    """Build one normalized ticker record. Numeric fields are coerced safely."""
    return {
        "exchange": exchange,
        "base": base.upper(),
        "quote": quote.upper(),
        "kind": kind,  # "spot" | "perp"
        "price": to_float(price),
        "change_pct": to_float(change_pct),
        "high": to_float(high),
        "low": to_float(low),
        "bid": to_float(bid),
        "ask": to_float(ask),
        "volume_usd": to_float(volume_usd),
        "open_interest": to_float(open_interest),
    }


def fetch_json(url: str, timeout: float = 10.0):
    req = urllib.request.Request(
        url, headers={"User-Agent": "marketsonar/0.1 (+https://github.com)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
