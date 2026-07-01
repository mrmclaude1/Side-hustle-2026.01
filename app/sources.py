"""Ticker data source: live Crypto.com public API with an offline fixture
fallback and a small in-process TTL cache.

The live endpoint is free and keyless:
    https://api.crypto.com/exchange/v1/public/get-tickers

We use stdlib urllib so there are no extra runtime dependencies and so the
system HTTPS proxy (HTTPS_PROXY) is honoured automatically. When the network
is unavailable (e.g. a locked-down CI sandbox) we transparently fall back to a
bundled snapshot so the app — and its demo — always runs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

CRYPTO_COM_TICKERS_URL = (
    "https://api.crypto.com/exchange/v1/public/get-tickers"
)
_FIXTURE = Path(__file__).parent / "fixtures" / "tickers_sample.json"

# Module-level cache: {"ts": epoch, "data": [...], "source": "live"|"fixture"}
_cache: dict = {}


def load_fixture() -> list[dict]:
    """Return the bundled ticker snapshot (used for demo / offline / tests)."""
    with _FIXTURE.open() as fh:
        return json.load(fh)["data"]


def fetch_live(timeout: float = 10.0) -> list[dict]:
    """Fetch a fresh ticker snapshot from Crypto.com. Raises on failure."""
    req = urllib.request.Request(
        CRYPTO_COM_TICKERS_URL,
        headers={"User-Agent": "perp-radar/0.1 (+https://github.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = payload.get("result", {}).get("data") or payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("unexpected ticker payload shape")
    return data


def get_tickers(
    ttl: float = 30.0,
    force_demo: Optional[bool] = None,
) -> dict:
    """Return {"data", "source", "age"} using cache -> live -> fixture order.

    force_demo=True always uses the fixture (handy for deterministic demos).
    The PERP_RADAR_DEMO=1 env var has the same effect.
    """
    if force_demo is None:
        force_demo = os.environ.get("PERP_RADAR_DEMO") == "1"

    now = time.time()
    if _cache and (now - _cache["ts"]) < ttl:
        return {
            "data": _cache["data"],
            "source": _cache["source"],
            "age": round(now - _cache["ts"], 1),
        }

    if force_demo:
        data, source = load_fixture(), "fixture"
    else:
        try:
            data, source = fetch_live(), "live"
        except Exception:
            # Network blocked / API down -> degrade gracefully to the snapshot.
            data, source = load_fixture(), "fixture"

    _cache.update(ts=now, data=data, source=source)
    return {"data": data, "source": source, "age": 0.0}


# --- Multi-exchange normalized records ------------------------------------

_records_cache: dict = {}


def get_records(
    exchanges=None,
    ttl: float = 30.0,
    force_demo: Optional[bool] = None,
) -> dict:
    """Return {"records", "sources", "age"} of normalized ticker records
    aggregated across exchanges. Each adapter degrades to its bundled fixture
    independently, so one venue being unreachable never breaks the rest.
    """
    # Imported lazily to avoid a circular import at module load.
    from .exchanges import ADAPTERS, DEFAULT_EXCHANGES

    if force_demo is None:
        force_demo = os.environ.get("PERP_RADAR_DEMO") == "1"
    names = tuple(exchanges) if exchanges else DEFAULT_EXCHANGES
    key = ",".join(sorted(names)) + ("|demo" if force_demo else "")

    now = time.time()
    cached = _records_cache.get(key)
    if cached and (now - cached["ts"]) < ttl:
        return {
            "records": cached["records"],
            "sources": cached["sources"],
            "age": round(now - cached["ts"], 1),
        }

    records: list[dict] = []
    src: dict[str, str] = {}
    for name in names:
        adapter = ADAPTERS.get(name)
        if adapter is None:
            continue
        if force_demo:
            recs, s = adapter.load_fixture(), "fixture"
        else:
            try:
                recs, s = adapter.fetch(), "live"
            except Exception:
                recs, s = adapter.load_fixture(), "fixture"
        records.extend(recs)
        src[name] = s

    _records_cache[key] = {"ts": now, "records": records, "sources": src}
    return {"records": records, "sources": src, "age": 0.0}
