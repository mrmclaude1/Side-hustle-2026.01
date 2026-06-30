"""FastAPI app: JSON analytics API + a static dashboard.

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, analytics, sources

app = FastAPI(title="Perp Radar", version=__version__)

_STATIC = Path(__file__).parent / "static"


@app.get("/api/health")
def health() -> dict:
    snap = sources.get_tickers()
    return {
        "status": "ok",
        "version": __version__,
        "data_source": snap["source"],
        "instruments": len(snap["data"]),
    }


@app.get("/api/scan")
def api_scan(
    quote: str = Query("USD", description="Preferred spot quote currency"),
    min_volume_usd: float = Query(0.0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    demo: bool = Query(False, description="Force the bundled snapshot"),
) -> JSONResponse:
    snap = sources.get_tickers(force_demo=True if demo else None)
    result = analytics.scan(
        snap["data"],
        quote=quote,
        min_volume_usd=min_volume_usd,
        limit=limit,
    )
    result["meta"] = {
        "data_source": snap["source"],
        "cache_age_s": snap["age"],
        "version": __version__,
    }
    return JSONResponse(result)


@app.get("/api/asset/{base}")
def api_asset(base: str, demo: bool = False) -> JSONResponse:
    snap = sources.get_tickers(force_demo=True if demo else None)
    result = analytics.scan(snap["data"], limit=None)
    base_u = base.upper()
    match = next((a for a in result["assets"] if a["base"] == base_u), None)
    if match is None:
        return JSONResponse({"error": f"unknown asset {base_u}"}, status_code=404)
    return JSONResponse({"asset": match, "meta": {"data_source": snap["source"]}})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


# Serve CSS/JS. Mounted last so it doesn't shadow the API routes above.
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
