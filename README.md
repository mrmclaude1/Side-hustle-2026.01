# Perp Radar

A crypto **market-structure scanner**. It pulls a live snapshot of every
market on the Crypto.com public exchange and, in one view, ranks assets by:

- **Perp/spot basis** — how far a perpetual future trades above/below spot
  (a real positioning/sentiment signal)
- **Momentum** — 24h price change
- **Volatility** — intraday high-low range
- **Liquidity** — bid/ask spread
- **Open interest & volume**

It distills these into a transparent **Radar Score** (0–100) that surfaces the
most *unusual* assets right now — so you spend your attention where something is
actually happening instead of scrolling 900 tickers.

> ⚠️ **Educational analytics, not investment advice.** The score ranks how
> unusual a market looks; it does **not** predict returns. Crypto is volatile
> and you can lose your entire stake. See [`BUSINESS.md`](BUSINESS.md) for the
> honest plan and expectations behind this project.

---

## Quick start

```bash
./run.sh              # creates venv, installs deps, serves http://127.0.0.1:8000
```

Or manually:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

No API key required — the data source is Crypto.com's free public endpoint.
If the network is unavailable, the app automatically falls back to a bundled
snapshot so it always runs (a `DEMO SNAPSHOT` pill shows when this happens).

### CLI (no browser)

```bash
python -m app.cli --top 20 --min-volume 1000000   # live
python -m app.cli --demo                           # bundled snapshot
```

### Demo mode

Force the bundled snapshot anywhere:

```bash
PERP_RADAR_DEMO=1 uvicorn app.main:app
```

---

## API

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard UI |
| `GET /api/health` | Liveness + data source + history size |
| `GET /api/scan?min_volume_usd=&limit=&quote=USD&demo=` | Ranked, scored assets + market summary (each asset includes `score_delta` vs the last snapshot) |
| `GET /api/snapshot` | Record a full scan into history. Call on a schedule to build trends. |
| `GET /api/history/{base}` | Score/price time series for one asset (e.g. `/api/history/BTC`) |
| `GET /api/asset/{base}` | Single asset detail + its history |
| `GET /api/alerts` | List alert rules + valid metrics/operators |
| `POST /api/alerts` | Create a rule `{name, metric, op, threshold, enabled}` |
| `DELETE /api/alerts/{id}` | Delete a rule |
| `GET /api/alerts/events` | Recent triggered alerts |
| `GET /api/exchanges` | Configured venues + their live endpoints |
| `GET /api/cross?min_venues=2&limit=` | Cross-exchange price dispersion + arb per asset |

Example:

```bash
curl 'http://127.0.0.1:8000/api/scan?limit=5&min_volume_usd=1000000' | jq '.summary'
```

---

## How the Radar Score works

It is a deliberately **simple, auditable** weighted blend of four normalised
components (see [`app/analytics.py`](app/analytics.py) — `radar_score`):

| Component | Weight | Reaches max at |
|---|---|---|
| Momentum (\|24h %\|) | 0.35 | 15% |
| Basis (\|perp−spot\|) | 0.30 | 50 bps |
| Volatility (range %) | 0.20 | 20% |
| Liquidity (tight spread) | 0.15 | ≤0 bps |

No machine learning, no hidden state, no lookahead — so you can always explain
exactly why an asset surfaced. Tune the weights to your own strategy.

---

## History & trends

A single score is noise; a *rising* score is signal. Scan snapshots are
persisted to SQLite so the dashboard can show a **Δ score** column and
click-to-expand **sparklines**.

- DB location: `PERP_RADAR_DB` env var (default `perp_radar.db`; use `:memory:`
  to disable on-disk persistence).
- Build history by hitting `GET /api/snapshot` on a schedule. For example, a
  cron entry every 15 minutes:

  ```cron
  */15 * * * * curl -s http://localhost:8000/api/snapshot >/dev/null
  ```

  Old snapshots are pruned automatically (keeps the most recent ~2000).

## Cross-exchange

Adapters normalise **Crypto.com, Binance, and Bybit** public tickers into one
shape (`app/exchanges/`), and `app/xexchange.py` groups them by asset to expose:

- **price_spread_bps** — how far the same asset is priced across venues
  (dislocation), compared within the USD-stable quote family only
- **arb** — best bid vs best ask across venues; a positive `edge_bps` is a
  crossed book (theoretical arbitrage before fees/withdrawal constraints)
- aggregate volume, open interest, and average momentum across venues

Each adapter falls back to its own bundled fixture independently, so one venue
being unreachable never breaks the others. The dashboard's *Cross-Exchange
dislocation* table ranks assets by spread.

> Note: Binance/Bybit adapters are written to their documented public API
> shapes and validated against fixtures; they activate against live endpoints
> wherever outbound access to those hosts is allowed.

## Alerts

Define rules like `radar_score >= 80`, `basis_bps <= -50`, or
`abs_change_pct >= 10`. Each recorded snapshot evaluates all enabled rules and
records the triggers; manage rules from the dashboard's Alerts panel or the API.

Available metrics: `radar_score`, `score_delta`, `basis_bps`, `abs_basis_bps`,
`change_pct`, `abs_change_pct`, `range_pct`, `volume_usd`.
Operators: `>=`, `<=`, `>`, `<`.

To push triggers to Discord/Slack/Telegram, set an incoming-webhook URL:

```bash
export PERP_RADAR_WEBHOOK_URL="https://discord.com/api/webhooks/…"
```

Delivery is a no-op when unset, so the app runs fine without any integration.

## Architecture

```
app/
  analytics.py   Pure signal functions (no network/clock) — fully unit-tested
  sources.py     Live fetch (stdlib urllib) + TTL cache + offline fixture fallback
  store.py       SQLite store: history snapshots + alert rules/events — tested
  alerts.py      Pure alert-rule evaluation — tested
  notify.py      Generic webhook delivery (Discord/Slack/Telegram/any)
  exchanges/     Per-venue adapters (cryptocom/binance/bybit) + fixtures — tested
  xexchange.py   Cross-exchange dispersion & arb analytics — tested
  main.py        FastAPI: JSON API + static dashboard
  cli.py         Terminal scanner
  static/        Zero-build dashboard (HTML/CSS/vanilla JS)
  fixtures/      Real captured market snapshot (demo + tests)
tests/           pytest suite (runs offline)
```

The analytics layer is pure data-in / data-out, which is why the whole signal
engine is testable with **zero network access**.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## Deploy

Any container host works. A `Dockerfile` is included:

```bash
docker build -t perp-radar .
docker run -p 8000:8000 perp-radar
```

For Render/Railway/Fly: build the image (or use `requirements.txt`) and run
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## License

MIT — see [`LICENSE`](LICENSE).
