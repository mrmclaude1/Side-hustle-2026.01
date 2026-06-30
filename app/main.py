"""FastAPI app: JSON analytics API + a static dashboard.

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000

History: set PERP_RADAR_DB to a file path (default: perp_radar.db) to persist
scan snapshots and unlock score trends + sparklines. Set it to ":memory:" to
disable on-disk persistence. A scheduled GET /api/snapshot records one point;
run it periodically (cron) to build history.
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, analytics, sources, store

app = FastAPI(title="Perp Radar", version=__version__)

_STATIC = Path(__file__).parent / "static"
_DB_PATH = os.environ.get("PERP_RADAR_DB", "perp_radar.db")

# One shared connection. check_same_thread=False is safe here because writes are
# small, serialised by SQLite's own locking, and the app is IO-light.
_conn: sqlite3.Connection = sqlite3.connect(_DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
store.init_db(_conn)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@app.get("/api/health")
def health() -> dict:
    snap = sources.get_tickers()
    snap_count = _conn.execute("SELECT COUNT(*) AS c FROM snapshots").fetchone()["c"]
    return {
        "status": "ok",
        "version": __version__,
        "data_source": snap["source"],
        "instruments": len(snap["data"]),
        "history_snapshots": snap_count,
    }


def _run_scan(
    quote: str, min_volume_usd: float, limit: Optional[int], demo: bool
) -> dict:
    snap = sources.get_tickers(force_demo=True if demo else None)
    result = analytics.scan(
        snap["data"], quote=quote, min_volume_usd=min_volume_usd, limit=limit
    )
    result["meta"] = {
        "data_source": snap["source"],
        "cache_age_s": snap["age"],
        "version": __version__,
    }
    return result


@app.get("/api/scan")
def api_scan(
    quote: str = Query("USD", description="Preferred spot quote currency"),
    min_volume_usd: float = Query(0.0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    demo: bool = Query(False, description="Force the bundled snapshot"),
) -> JSONResponse:
    result = _run_scan(quote, min_volume_usd, limit, demo)
    # Annotate each asset with its score change vs the most recent snapshot.
    store.annotate_trend(_conn, result)
    return JSONResponse(result)


@app.get("/api/snapshot")
def api_snapshot(
    quote: str = Query("USD"),
    min_volume_usd: float = Query(0.0, ge=0),
    demo: bool = Query(False),
) -> JSONResponse:
    """Record a full (unlimited) scan into history. Call on a schedule."""
    result = _run_scan(quote, min_volume_usd, None, demo)
    baseline = store.previous_scores(_conn)  # latest before we insert
    snap_id = store.record_scan(
        _conn, result, ts=_now_iso(), source=result["meta"]["data_source"]
    )
    store.prune(_conn)
    return JSONResponse(
        {
            "recorded_snapshot_id": snap_id,
            "assets_recorded": len(result["assets"]),
            "compared_against_prior": bool(baseline),
        }
    )


@app.get("/api/history/{base}")
def api_history(base: str, limit: int = Query(200, ge=1, le=2000)) -> JSONResponse:
    points = store.history(_conn, base, limit=limit)
    return JSONResponse({"base": base.upper(), "points": points, "count": len(points)})


@app.get("/api/asset/{base}")
def api_asset(base: str, demo: bool = False) -> JSONResponse:
    result = _run_scan("USD", 0.0, None, demo)
    base_u = base.upper()
    match = next((a for a in result["assets"] if a["base"] == base_u), None)
    if match is None:
        return JSONResponse({"error": f"unknown asset {base_u}"}, status_code=404)
    return JSONResponse(
        {
            "asset": match,
            "history": store.history(_conn, base_u, limit=200),
            "meta": result["meta"],
        }
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


# Serve CSS/JS. Mounted last so it doesn't shadow the API routes above.
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
