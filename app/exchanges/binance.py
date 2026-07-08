"""Binance adapter: spot 24h ticker + USDT-M futures 24h ticker.

Endpoints (public, keyless):
  spot   GET https://api.binance.com/api/v3/ticker/24hr
  perp   GET https://fapi.binance.com/fapi/v1/ticker/24hr

The spot ticker carries bid/ask; the futures ticker does not, so bid/ask are
left None for perps. Per-symbol open interest would require one call each, so
OI is left None here (Bybit provides it in bulk — see bybit.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import base

NAME = "binance"
SPOT_URL = "https://api.binance.com/api/v3/ticker/24hr"
PERP_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "binance.json"

# Only surface these quotes; Binance lists hundreds of pairs across many quotes.
_KEEP_QUOTES = ("USDT", "USDC", "FDUSD")


def live_urls() -> dict:
    return {"spot": SPOT_URL, "perp": PERP_URL}


def _normalize(rows: list[dict], kind: str) -> list[dict]:
    out = []
    for t in rows:
        base_sym, quote = base.split_symbol(t.get("symbol", ""))
        if not base_sym or quote not in _KEEP_QUOTES:
            continue
        out.append(
            base.normalized(
                NAME, base_sym, quote, kind,
                price=t.get("lastPrice"),
                change_pct=t.get("priceChangePercent"),  # already a percent
                high=t.get("highPrice"), low=t.get("lowPrice"),
                bid=t.get("bidPrice"), ask=t.get("askPrice"),
                volume_usd=t.get("quoteVolume"),  # quote-denominated volume
            )
        )
    return out


def fetch(timeout: float = 10.0) -> list[dict]:
    spot = base.fetch_json(SPOT_URL, timeout=timeout)
    perp = base.fetch_json(PERP_URL, timeout=timeout)
    return _normalize(spot, "spot") + _normalize(perp, "perp")


def load_fixture() -> list[dict]:
    with _FIXTURE.open() as fh:
        raw = json.load(fh)
    return _normalize(raw["spot"], "spot") + _normalize(raw["perp"], "perp")
