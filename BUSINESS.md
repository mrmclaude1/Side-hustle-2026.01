# The Plan: $500 → ? (read this honestly)

You asked to turn **$500 into $100,000 in a year**. I'm not going to pretend
that's a realistic, reliable target — being straight with you is worth more than
being agreeable.

## The math, plainly

$500 → $100,000 is a **200× return in 12 months**. For reference:

| Benchmark | Annual return |
|---|---|
| S&P 500 (historical avg) | ~1.1× |
| A great hedge fund | ~1.3× |
| Warren Buffett (lifetime) | ~1.2× |
| **This target** | **200×** |

The only "strategies" that mathematically reach 200× in a year are
high-leverage bets that have a ~99% chance of zeroing the $500 first. Anyone —
human or AI — promising a *guaranteed* 200× is describing a scam or a lottery
ticket. I won't sell you that.

What I **can** do is build you a **real, owned asset** with genuine (if smaller)
upside, and hand you the controls. That asset is **Perp Radar** — the market
analytics tool in this repo.

## Why this concept

You picked "crypto data/analytics tool." That's a smart pick because:

1. **The product sells the picks and shovels, not the gamble.** You're not
   betting $500 on a coin. You're building a tool that *other traders pay for*.
   Data/analytics services (Coinglass, CryptoQuant, Glassnode, TradingView) are
   proven, profitable businesses. The risk is your time, not your principal.
2. **Free data, near-zero marginal cost.** Crypto.com's public API is free and
   keyless. Hosting a small app is a few dollars a month.
3. **Clear upgrade ladder.** Start free → add a paid tier → add alerts/API
   access. Each step is a real, buildable increment (see Roadmap).

## What's already built (this repo)

A working MVP you can run today:

- Live scanner across ~900 markets with a transparent **Radar Score**
- Perp/spot **basis**, momentum, volatility, liquidity, OI, volume
- Web dashboard + JSON API + CLI
- Offline demo mode, full test suite, Docker deploy

## The $500 budget

| Item | Cost | Notes |
|---|---|---|
| Domain (`.com`) | ~$12/yr | Brand it |
| Hosting (Render/Railway/Fly small instance) | ~$5–7/mo (~$80/yr) | Scales later |
| Email + landing page tooling | $0–15/mo | Start free |
| Launch ads (optional, small tests) | ~$150 | $5–10/day micro-tests on X/Reddit |
| Reserve | remainder | Don't spend it all; iterate on what converts |

You can launch for well under $100 and keep the rest as runway. **Do not** put
the $500 into a leveraged trade.

## Monetization ladder

1. **Free** — top movers + basic scan (acquisition + SEO traffic).
2. **Pro ($9–19/mo)** — full scanner, custom score weights, more history,
   CSV export, no rate limits.
3. **Alerts ($+)** — Telegram/Discord/email alerts on basis or score thresholds.
4. **API access ($+)** — let other builders pull your computed signals.

**Honest revenue picture:** a niche tool like this might realistically reach
tens to a few hundred paying users in a year *if* it's marketed consistently.
At ~100 Pro subs × $12/mo that's ~$14k/yr recurring — a real side income, not
$100k, and not guaranteed. Most of the outcome depends on distribution
(content, SEO, community), which is the work that comes after the code.

## Roadmap (build order)

- [x] **MVP** — scanner, score, dashboard, API, CLI, tests
- [x] **Historical storage + sparklines** (SQLite) so scores have trend — Δ score
      column, `/api/snapshot`, `/api/history/{base}`
- [ ] Multi-exchange data (add Binance/Bybit public APIs) for cross-exchange basis
- [ ] User accounts + Stripe + the Pro tier gate
- [ ] Alerts (Telegram bot is the cheapest, highest-retention channel)
- [ ] Landing page + 1 piece of SEO content per week (the actual growth engine)
- [ ] Public API with keys/quotas

## What I need from you (minimal)

Nothing to keep building features — I can execute the roadmap. The things only
**you** can do, when you're ready:

1. Pick a name/domain and point me at it.
2. Create the hosting + Stripe accounts (they need your identity/payment).
3. Decide the price point.

Until then I'll keep advancing the product and the deploy setup.

---

*Bottom line: I traded you a fake shot at $100k for a real shot at a real
business. That's the honest deal, and it's the one worth taking.*
