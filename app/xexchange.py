"""Cross-exchange analytics.

Given normalized ticker records from several venues (see app.exchanges), group
by base asset and quantify *dislocation*:

- price_spread_bps: how far apart the same asset is priced across venues — the
  headline cross-exchange signal.
- arb: best bid vs best ask across venues; a crossed book (bid > ask on
  different venues) is a theoretical arbitrage (before fees/withdrawal limits).
- aggregate volume / open interest / average momentum across venues.

Pure functions only: records in, analytics out.
"""

from __future__ import annotations

from typing import Optional

# Treat these quotes as one comparable "USD" bucket. Comparing a BTC_USDT price
# against a BTC_EUR or BTC_BTC price would be meaningless, so non-USD quotes are
# excluded from cross-exchange comparison.
USD_QUOTES = {"USDT", "USDC", "USD", "FDUSD", "TUSD", "DAI", "USDD"}


def _median(xs: list[float]) -> Optional[float]:
    ys = sorted(v for v in xs if v is not None)
    if not ys:
        return None
    n = len(ys)
    mid = n // 2
    return ys[mid] if n % 2 else (ys[mid - 1] + ys[mid]) / 2.0


def _group(records: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in records:
        if r.get("base"):
            groups.setdefault(r["base"], []).append(r)
    return groups


def _representatives(recs: list[dict], kind: str) -> dict[str, dict]:
    """One record per exchange for the given kind: the highest-volume USD-quote
    pair (so BTC_USDT wins over a thin BTC_USDC book on the same venue)."""
    best: dict[str, dict] = {}
    for r in recs:
        if r["kind"] != kind or not r.get("price") or r["quote"] not in USD_QUOTES:
            continue
        ex = r["exchange"]
        if ex not in best or (r["volume_usd"] or 0) > (best[ex]["volume_usd"] or 0):
            best[ex] = r
    return best


def _best_arb(reps: dict[str, dict]) -> Optional[dict]:
    """Highest bid vs lowest ask across the per-venue representative records.

    Returns the buy/sell venues and the crossed-book edge in bps (negative when
    there is no arbitrage, i.e. the normal case). None if fewer than two venues
    provide a two-sided quote.
    """
    quoted = [r for r in reps.values() if r.get("bid") and r.get("ask")]
    if len(quoted) < 2:
        return None
    best_bid = max(quoted, key=lambda r: r["bid"])
    best_ask = min(quoted, key=lambda r: r["ask"])
    if best_bid["exchange"] == best_ask["exchange"]:
        return None
    edge_bps = (best_bid["bid"] - best_ask["ask"]) / best_ask["ask"] * 10000.0
    return {
        "buy_at": best_ask["exchange"],
        "buy_price": best_ask["ask"],
        "sell_at": best_bid["exchange"],
        "sell_price": best_bid["bid"],
        "edge_bps": round(edge_bps, 2),  # negative = no crossed book (normal)
    }


def _asset(base: str, recs: list[dict]) -> dict:
    spot_reps = _representatives(recs, "spot")
    perp_reps = _representatives(recs, "perp")
    spot_prices = {ex: r["price"] for ex, r in spot_reps.items()}
    perp_prices = {ex: r["price"] for ex, r in perp_reps.items()}
    all_prices = list(spot_prices.values()) + list(perp_prices.values())

    # Price spread: prefer comparing spot-to-spot; fall back to all prices.
    price_set = list(spot_prices.values())
    if len(price_set) < 2:
        price_set = all_prices
    spread_bps = None
    if len(price_set) >= 2:
        lo, hi = min(price_set), max(price_set)
        if lo > 0:
            spread_bps = (hi - lo) / lo * 10000.0

    # Aggregate only over the representative USD-quote records to avoid
    # double-counting duplicate pairs / mixing non-USD quotes.
    reps = list(spot_reps.values()) + list(perp_reps.values())
    changes = [r["change_pct"] for r in reps if r["change_pct"] is not None]
    venues = sorted(set(spot_reps) | set(perp_reps))
    arb = _best_arb(spot_reps if len([r for r in spot_reps.values()
                                      if r.get("bid") and r.get("ask")]) >= 2
                    else perp_reps)
    return {
        "base": base,
        "venues": venues,
        "venue_count": len(venues),
        "reference_price": _median(all_prices),
        "price_spread_bps": round(spread_bps, 2) if spread_bps is not None else None,
        "spot_prices": {k: round(v, 8) for k, v in spot_prices.items()},
        "perp_prices": {k: round(v, 8) for k, v in perp_prices.items()},
        "avg_change_pct": round(sum(changes) / len(changes), 2) if changes else None,
        "total_volume_usd": round(sum(r["volume_usd"] or 0.0 for r in reps), 2),
        "total_open_interest": round(
            sum(r["open_interest"] or 0.0 for r in perp_reps.values()), 4
        ),
        "arb": arb,
    }


def cross_scan(
    records: list[dict], min_venues: int = 2, limit: Optional[int] = None
) -> dict:
    """Group records by asset, keep those on >= min_venues venues, rank by
    cross-exchange price spread (widest dislocation first)."""
    assets = [_asset(b, recs) for b, recs in _group(records).items()]
    assets = [a for a in assets if a["venue_count"] >= min_venues]
    assets.sort(key=lambda a: (a["price_spread_bps"] or -1.0), reverse=True)

    spreads = [a["price_spread_bps"] for a in assets if a["price_spread_bps"] is not None]
    arbs = [a for a in assets if a["arb"] and a["arb"]["edge_bps"] > 0]
    summary = {
        "assets": len(assets),
        "venues": sorted({v for a in assets for v in a["venues"]}),
        "max_spread_bps": max(spreads) if spreads else None,
        "avg_spread_bps": round(sum(spreads) / len(spreads), 2) if spreads else None,
        "crossed_book_count": len(arbs),
    }
    if limit is not None:
        assets = assets[:limit]
    return {"summary": summary, "assets": assets}
