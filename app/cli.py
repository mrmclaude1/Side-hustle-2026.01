"""Command-line scanner — see the product work without a browser.

    python -m app.cli            # live data (or fixture if offline)
    python -m app.cli --demo     # force bundled snapshot
    python -m app.cli --top 15 --min-volume 1000000
"""

from __future__ import annotations

import argparse

from . import analytics, sources


def _fmt(v, suffix="", width=9):
    if v is None:
        return "-".rjust(width)
    return f"{v:,.2f}{suffix}".rjust(width)


def main() -> None:
    ap = argparse.ArgumentParser(description="BasisPulse CLI scanner")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-volume", type=float, default=0.0)
    ap.add_argument("--quote", default="USD")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    snap = sources.get_tickers(force_demo=True if args.demo else None)
    result = analytics.scan(
        snap["data"],
        quote=args.quote,
        min_volume_usd=args.min_volume,
        limit=args.top,
    )
    s = result["summary"]

    print(f"\nBasisPulse  —  data source: {snap['source']}  "
          f"({s['assets']} assets)")
    print(f"Breadth: {s['advancers']}↑ / {s['decliners']}↓  "
          f"({s['breadth_pct']}% advancing)   "
          f"avg 24h: {s['avg_change_pct']}%   "
          f"avg basis: {s['avg_basis_bps']} bps\n")

    hdr = (f"{'ASSET':<8}{'SCORE':>7}{'PRICE':>13}{'24H%':>9}"
           f"{'BASIS':>9}{'RANGE%':>9}{'SPREAD':>9}{'VOL(USD)':>16}")
    print(hdr)
    print("-" * len(hdr))
    for a in result["assets"]:
        flag = "P" if a["has_perp"] else " "
        print(f"{a['base']:<7}{flag}"
              f"{a['radar_score']:>7.1f}"
              f"{_fmt(a['price'], '', 13)}"
              f"{_fmt(a['change_pct'], '%')}"
              f"{_fmt(a['basis_bps'], '')}"
              f"{_fmt(a['range_pct'], '')}"
              f"{_fmt(a['spread_bps'], '')}"
              f"{_fmt(a['volume_usd'], '', 16)}")
    print("\n'P' = perpetual available. Score is a transparent notability "
          "rank, not investment advice.\n")


if __name__ == "__main__":
    main()
