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
| `GET /api/health` | Liveness + data source |
| `GET /api/scan?min_volume_usd=&limit=&quote=USD&demo=` | Ranked, scored assets + market summary |
| `GET /api/asset/{base}` | Single asset detail (e.g. `/api/asset/BTC`) |

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

## Architecture

```
app/
  analytics.py   Pure signal functions (no network/clock) — fully unit-tested
  sources.py     Live fetch (stdlib urllib) + TTL cache + offline fixture fallback
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
