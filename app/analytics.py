"""Pure, deterministic analytics over Crypto.com ticker snapshots.

Every function here is a pure transformation of plain dicts -> plain dicts.
No network, no clock, no globals. That makes the signal logic fully testable
against a fixed fixture (see tests/test_analytics.py).

Data source shape (one element of the `data` array returned by
https://api.crypto.com/exchange/v1/public/get-tickers):

    {
      "instrument_name": "BTC_USDT",   # spot pair, or e.g. "BTCUSDPERP" for a perp
      "last": "58589.01",
      "high": "60294.23",
      "low":  "58186.01",
      "change": "-0.0281",             # 24h change as a FRACTION (-2.81%)
      "best_bid": "58587.37",
      "best_ask": "58587.38",
      "volume": "3768.47",             # base-asset volume
      "volume_value": "221654137.71",  # quote (USD) volume
      "open_interest": "0",            # nonzero on perps
      "timestamp": "2026-06-30T23:39:14.610Z"
    }

The headline derived metric is the **basis**: how far a perpetual future
trades above (or below) its spot price. Persistent positive basis means longs
are paying to hold the position (crowded-long / bullish positioning); negative
basis means shorts are paying (crowded-short / bearish). It is a widely-watched,
legitimate market-structure indicator — not a profit guarantee.
"""

from __future__ import annotations

from typing import Iterable, Optional

# Quote currencies we recognise when splitting a concatenated perp symbol like
# "BTCUSDPERP" -> base "BTC", quote "USD". Ordered longest-first so "USDT"
# matches before "USD".
_QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH", "EUR", "GBP")


def to_float(value: object) -> Optional[float]:
    """Best-effort float parse; returns None for missing/blank/garbage."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # Guard against NaN/inf sneaking in from upstream.
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def parse_instrument(name: str) -> dict:
    """Classify an instrument name into {base, quote, kind}.

    kind is "perp" for perpetual futures (names ending in PERP), otherwise
    "spot". Returns base="" when the symbol can't be confidently parsed.
    """
    raw = (name or "").upper()
    if raw.endswith("PERP"):
        core = raw[: -len("PERP")].rstrip("-_")
        for q in _QUOTES:
            if core.endswith(q) and len(core) > len(q):
                return {"base": core[: -len(q)], "quote": q, "kind": "perp"}
        return {"base": core, "quote": "", "kind": "perp"}
    # Spot pairs use a separator: BTC_USDT, BTC-USDT.
    for sep in ("_", "-"):
        if sep in raw:
            base, _, quote = raw.partition(sep)
            return {"base": base, "quote": quote, "kind": "spot"}
    # Fallback: concatenated spot symbol like BTCUSD.
    for q in _QUOTES:
        if raw.endswith(q) and len(raw) > len(q):
            return {"base": raw[: -len(q)], "quote": q, "kind": "spot"}
    return {"base": raw, "quote": "", "kind": "spot"}


def _metrics(t: dict) -> dict:
    """Per-ticker microstructure metrics derived from a single snapshot."""
    last = to_float(t.get("last"))
    high = to_float(t.get("high"))
    low = to_float(t.get("low"))
    bid = to_float(t.get("best_bid"))
    ask = to_float(t.get("best_ask"))

    # Intraday range as a volatility proxy: (high - low) / last, in percent.
    range_pct = None
    if last and high is not None and low is not None and last > 0:
        range_pct = (high - low) / last * 100.0

    # Bid/ask spread in basis points: a cheap liquidity gauge.
    spread_bps = None
    if bid and ask and bid > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        if mid > 0:
            spread_bps = (ask - bid) / mid * 10000.0

    change = to_float(t.get("change"))
    return {
        "last": last,
        "range_pct": range_pct,
        "spread_bps": spread_bps,
        "change_pct": change * 100.0 if change is not None else None,
        "volume_usd": to_float(t.get("volume_value")),
        "open_interest": to_float(t.get("open_interest")),
    }


def build_assets(tickers: Iterable[dict], quote: str = "USD") -> list[dict]:
    """Merge spot + perp snapshots per base asset and compute signals.

    For each base symbol we look for a perp and a matching spot quote (USD,
    falling back to USDT) and compute the basis between them when both exist.
    """
    spots: dict[tuple[str, str], dict] = {}
    perps: dict[str, dict] = {}

    for t in tickers:
        p = parse_instrument(t.get("instrument_name", ""))
        if not p["base"]:
            continue
        if p["kind"] == "perp":
            # Keep the highest-volume perp if several map to one base.
            cur = perps.get(p["base"])
            m = _metrics(t)
            if cur is None or (m["volume_usd"] or 0) > (cur["_m"]["volume_usd"] or 0):
                perps[p["base"]] = {"ticker": t, "parsed": p, "_m": m}
        else:
            spots[(p["base"], p["quote"])] = {"ticker": t, "_m": _metrics(t)}

    assets: list[dict] = []
    quote_prefs = (quote, "USDT", "USDC", "USD")

    bases = set(perps) | {b for (b, _q) in spots}
    for base in bases:
        perp = perps.get(base)
        spot = None
        for q in quote_prefs:
            if (base, q) in spots:
                spot = spots[(base, q)]
                break

        perp_m = perp["_m"] if perp else None
        spot_m = spot["_m"] if spot else None
        ref = perp_m or spot_m
        if ref is None:
            continue

        basis_bps = None
        spot_px = spot_m["last"] if spot_m else None
        perp_px = perp_m["last"] if perp_m else None
        if spot_px and perp_px and spot_px > 0:
            basis_bps = (perp_px - spot_px) / spot_px * 10000.0

        assets.append(
            {
                "base": base,
                "has_perp": perp is not None,
                "has_spot": spot is not None,
                "price": perp_px or spot_px,
                "change_pct": ref["change_pct"],
                "range_pct": ref["range_pct"],
                "spread_bps": (perp_m or spot_m)["spread_bps"],
                "volume_usd": (perp_m["volume_usd"] if perp_m else None)
                or (spot_m["volume_usd"] if spot_m else None),
                "open_interest": perp_m["open_interest"] if perp_m else None,
                "basis_bps": basis_bps,
            }
        )
    return assets


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def radar_score(asset: dict) -> float:
    """A transparent 0-100 "notability" score.

    This is NOT a buy/sell recommendation and makes no claim about future
    returns. It simply ranks how *unusual* an asset looks right now by blending
    four normalised, independently-meaningful components:

      - momentum:   magnitude of 24h move
      - basis:      magnitude of perp/spot dislocation (positioning stress)
      - volatility: intraday high-low range
      - liquidity:  tighter spreads score higher (more tradable)

    The weights and caps are deliberately explicit so a user can audit exactly
    why something surfaced.
    """
    momentum = _clamp(abs(asset.get("change_pct") or 0.0) / 15.0, 0, 1)  # 15% -> max
    basis = _clamp(abs(asset.get("basis_bps") or 0.0) / 50.0, 0, 1)      # 50bps -> max
    vol = _clamp((asset.get("range_pct") or 0.0) / 20.0, 0, 1)           # 20% -> max
    spread = asset.get("spread_bps")
    liquidity = 0.0 if spread is None else _clamp(1.0 - spread / 25.0, 0, 1)  # <=0bps best

    score = 100.0 * (
        0.35 * momentum + 0.30 * basis + 0.20 * vol + 0.15 * liquidity
    )
    return round(score, 1)


def market_summary(assets: list[dict]) -> dict:
    """Aggregate breadth/sentiment stats across all assets."""
    changes = [a["change_pct"] for a in assets if a["change_pct"] is not None]
    bases = [a["basis_bps"] for a in assets if a["basis_bps"] is not None]
    advancers = sum(1 for c in changes if c > 0)
    decliners = sum(1 for c in changes if c < 0)
    total_vol = sum(a["volume_usd"] or 0.0 for a in assets)
    return {
        "assets": len(assets),
        "with_basis": len(bases),
        "advancers": advancers,
        "decliners": decliners,
        "breadth_pct": round(advancers / len(changes) * 100.0, 1) if changes else None,
        "avg_change_pct": round(sum(changes) / len(changes), 2) if changes else None,
        "avg_basis_bps": round(sum(bases) / len(bases), 2) if bases else None,
        "total_volume_usd": round(total_vol, 2),
    }


def scan(
    tickers: Iterable[dict],
    quote: str = "USD",
    min_volume_usd: float = 0.0,
    limit: Optional[int] = None,
) -> dict:
    """End-to-end: tickers -> scored, ranked assets + a market summary."""
    assets = build_assets(tickers, quote=quote)
    if min_volume_usd:
        assets = [a for a in assets if (a["volume_usd"] or 0.0) >= min_volume_usd]
    for a in assets:
        a["radar_score"] = radar_score(a)
    assets.sort(key=lambda a: a["radar_score"], reverse=True)
    summary = market_summary(assets)
    if limit is not None:
        assets = assets[:limit]
    return {"summary": summary, "assets": assets}
