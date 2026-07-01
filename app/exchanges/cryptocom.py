"""Crypto.com adapter. Reuses the bundled full-market snapshot in
app/fixtures/tickers_sample.json and normalises it to the common shape."""

from __future__ import annotations

from pathlib import Path

from . import base

NAME = "cryptocom"
TICKERS_URL = "https://api.crypto.com/exchange/v1/public/get-tickers"
_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "tickers_sample.json"


def live_urls() -> dict:
    return {"tickers": TICKERS_URL}


def _normalize(rows: list[dict]) -> list[dict]:
    out = []
    for t in rows:
        name = t.get("instrument_name", "")
        if name.upper().endswith("PERP"):
            core = name[:-4].rstrip("-_")
            base_sym, quote = base.split_symbol(core)
            kind = "perp"
        else:
            base_sym, quote = base.split_symbol(name)
            kind = "spot"
        if not base_sym:
            continue
        change = t.get("change")
        # Crypto.com reports 24h change as a fraction; convert to percent.
        change_pct = None if change in (None, "") else float(change) * 100.0
        out.append(
            base.normalized(
                NAME, base_sym, quote, kind,
                price=t.get("last"), change_pct=change_pct,
                high=t.get("high"), low=t.get("low"),
                bid=t.get("best_bid"), ask=t.get("best_ask"),
                volume_usd=t.get("volume_value"),
                open_interest=t.get("open_interest"),
            )
        )
    return out


def fetch(timeout: float = 10.0) -> list[dict]:
    payload = base.fetch_json(TICKERS_URL, timeout=timeout)
    rows = payload.get("result", {}).get("data") or payload.get("data") or []
    return _normalize(rows)


def load_fixture() -> list[dict]:
    import json
    with _FIXTURE.open() as fh:
        return _normalize(json.load(fh)["data"])
