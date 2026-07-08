"""FastAPI app: JSON analytics API + a static dashboard.

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000

History: set BASISPULSE_DB to a file path (default: basispulse.db) to persist
scan snapshots and unlock score trends + sparklines. Set it to ":memory:" to
disable on-disk persistence. A scheduled GET /api/snapshot records one point;
run it periodically (cron) to build history.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (
    __version__, access, alerts, analytics, billing, notify, sources, store,
    xexchange,
)
from .exchanges import ADAPTERS, DEFAULT_EXCHANGES

app = FastAPI(title="BasisPulse", version=__version__)

_STATIC = Path(__file__).parent / "static"
_DB_PATH = os.environ.get("BASISPULSE_DB", "basispulse.db")

# One shared connection. check_same_thread=False is safe here because writes are
# small, serialised by SQLite's own locking, and the app is IO-light.
_conn: sqlite3.Connection = sqlite3.connect(_DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
store.init_db(_conn)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


_rate = access.RateLimiter()


def caller(
    request: Request, x_api_key: Optional[str] = Header(default=None)
) -> dict:
    """Resolve the caller's plan from an API key (header or ?api_key=), enforce
    the per-plan rate limit, and return {plan, key, identity}.

    Missing key -> anonymous free tier. A supplied-but-unknown key -> 401.
    """
    key = x_api_key or request.query_params.get("api_key")
    if key and not store.key_is_known(_conn, key):
        raise HTTPException(status_code=401, detail="invalid API key")
    plan = store.resolve_plan(_conn, key) or access.DEFAULT_PLAN
    identity = key or (request.client.host if request.client else "anon")
    if os.environ.get("BASISPULSE_DISABLE_RATELIMIT") != "1":
        limit = access.plan_config(plan)["rate_per_min"]
        if not _rate.allow(identity, limit, time.time()):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    return {"plan": plan, "key": key, "identity": identity}


def _require(ctx: dict, feature: str) -> None:
    if not access.has_feature(ctx["plan"], feature):
        raise HTTPException(
            status_code=402,
            detail=f"'{feature}' requires the Pro plan — see /api/pricing",
        )


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


@app.get("/api/pricing")
def api_pricing() -> JSONResponse:
    pro_price = os.environ.get("BASISPULSE_PRO_PRICE", "19").strip()
    plans = {
        name: {
            "rate_per_min": cfg["rate_per_min"],
            "max_scan_limit": cfg["max_scan_limit"],
            "max_alert_rules": cfg["max_rules"],
            "features": sorted(cfg["features"]),
        }
        for name, cfg in access.PLANS.items()
    }
    if "pro" in plans:
        plans["pro"]["price_usd_month"] = pro_price
    return JSONResponse(
        {
            "plans": plans,
            # Set BASISPULSE_CHECKOUT_URL to your Stripe Checkout link to wire
            # the landing page's "Get Pro" button. Empty until configured.
            "checkout_url": os.environ.get("BASISPULSE_CHECKOUT_URL", "").strip(),
        }
    )


@app.get("/api/me")
def api_me(ctx: dict = Depends(caller)) -> JSONResponse:
    cfg = access.plan_config(ctx["plan"])
    return JSONResponse(
        {
            "plan": ctx["plan"],
            "authenticated": bool(ctx["key"]),
            "limits": {
                "rate_per_min": cfg["rate_per_min"],
                "max_scan_limit": cfg["max_scan_limit"],
                "max_alert_rules": cfg["max_rules"],
            },
            "features": sorted(cfg["features"]),
        }
    )


@app.get("/api/scan")
def api_scan(
    quote: str = Query("USD", description="Preferred spot quote currency"),
    min_volume_usd: float = Query(0.0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    demo: bool = Query(False, description="Force the bundled snapshot"),
    ctx: dict = Depends(caller),
) -> JSONResponse:
    capped = access.clamp_scan_limit(ctx["plan"], limit)
    result = _run_scan(quote, min_volume_usd, capped, demo)
    # Annotate each asset with its score change vs the most recent snapshot.
    store.annotate_trend(_conn, result)
    result["meta"]["plan"] = ctx["plan"]
    if capped < limit:
        result["meta"]["limit_capped_to"] = capped
        result["meta"]["upgrade"] = "Pro unlocks deeper scans — see /api/pricing"
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
    ts = _now_iso()
    snap_id = store.record_scan(
        _conn, result, ts=ts, source=result["meta"]["data_source"]
    )
    store.prune(_conn)

    # Evaluate alert rules against the fresh (trend-annotated) scan.
    store.annotate_trend(_conn, result, baseline=baseline)
    rules = store.list_rules(_conn, enabled_only=True)
    triggers = alerts.evaluate_scan(rules, result)
    store.record_events(_conn, triggers, ts=ts)
    delivered = notify.deliver(triggers, ts=ts)

    return JSONResponse(
        {
            "recorded_snapshot_id": snap_id,
            "assets_recorded": len(result["assets"]),
            "compared_against_prior": bool(baseline),
            "alerts_triggered": len(triggers),
            "alerts_delivered": delivered,
        }
    )


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    metric: str
    op: str
    threshold: float
    enabled: bool = True


@app.get("/api/alerts")
def api_list_alerts() -> JSONResponse:
    return JSONResponse(
        {
            "rules": store.list_rules(_conn),
            "metrics": list(alerts.METRICS),
            "ops": list(alerts.OPS),
        }
    )


@app.post("/api/alerts")
def api_create_alert(rule: RuleIn, ctx: dict = Depends(caller)) -> JSONResponse:
    try:
        alerts.validate_rule(rule.metric, rule.op)
    except alerts.RuleError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not access.has_feature(ctx["plan"], "alerts_unlimited"):
        if len(store.list_rules(_conn)) >= access.max_rules(ctx["plan"]):
            raise HTTPException(
                status_code=402,
                detail=(f"Free plan is limited to {access.max_rules(ctx['plan'])} "
                        f"alert rules — upgrade to Pro for unlimited. See /api/pricing"),
            )
    created = store.add_rule(
        _conn, rule.name, rule.metric, rule.op, rule.threshold, rule.enabled
    )
    return JSONResponse({"rule": created}, status_code=201)


@app.delete("/api/alerts/{rule_id}")
def api_delete_alert(rule_id: int) -> JSONResponse:
    ok = store.delete_rule(_conn, rule_id)
    if not ok:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"deleted": rule_id})


@app.get("/api/alerts/events")
def api_alert_events(limit: int = Query(100, ge=1, le=1000)) -> JSONResponse:
    return JSONResponse({"events": store.list_events(_conn, limit=limit)})


@app.get("/api/history/{base}")
def api_history(base: str, limit: int = Query(200, ge=1, le=2000)) -> JSONResponse:
    points = store.history(_conn, base, limit=limit)
    return JSONResponse({"base": base.upper(), "points": points, "count": len(points)})


@app.get("/api/pro/signals")
def api_pro_signals(
    limit: int = Query(100, ge=1, le=1000),
    demo: bool = Query(False),
    ctx: dict = Depends(caller),
) -> JSONResponse:
    """Premium: full-depth scan enriched with score percentile ranking."""
    _require(ctx, "pro_signals")
    result = _run_scan("USD", 0.0, None, demo)
    store.annotate_trend(_conn, result)
    n = len(result["assets"])
    for i, a in enumerate(result["assets"]):
        # assets are score-sorted desc; percentile of remaining rank
        a["score_percentile"] = round(100.0 * (n - i) / n, 1) if n else None
    result["assets"] = result["assets"][:limit]
    result["meta"]["plan"] = ctx["plan"]
    return JSONResponse(result)


@app.get("/api/export.csv")
def api_export_csv(
    demo: bool = Query(False), ctx: dict = Depends(caller)
) -> PlainTextResponse:
    """Premium: export the current scan as CSV."""
    _require(ctx, "export")
    result = _run_scan("USD", 0.0, None, demo)
    store.annotate_trend(_conn, result)
    cols = ["base", "radar_score", "score_delta", "price", "change_pct",
            "basis_bps", "range_pct", "spread_bps", "open_interest", "volume_usd"]
    lines = [",".join(cols)]
    for a in result["assets"]:
        lines.append(",".join("" if a.get(c) is None else str(a.get(c)) for c in cols))
    return PlainTextResponse("\n".join(lines), media_type="text/csv")


class KeyIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=80)
    plan: str = "free"


@app.post("/api/keys")
def api_create_key(
    body: KeyIn, x_admin_token: Optional[str] = Header(default=None)
) -> JSONResponse:
    """Provision an API key. Self-service yields a free key; supplying a valid
    admin token (BASISPULSE_ADMIN_TOKEN) allows minting Pro keys (comps/manual)."""
    admin = os.environ.get("BASISPULSE_ADMIN_TOKEN", "").strip()
    is_admin = bool(admin) and x_admin_token == admin
    plan = body.plan if (is_admin and body.plan in access.PLANS) else "free"
    rec = store.create_key(
        _conn, plan=plan, label=body.label or ("admin" if is_admin else "self-serve"),
        ts=_now_iso(),
    )
    return JSONResponse({"key": rec}, status_code=201)


@app.post("/api/billing/webhook")
async def billing_webhook(
    request: Request, stripe_signature: Optional[str] = Header(default=None)
) -> JSONResponse:
    raw = await request.body()
    secret = billing.webhook_secret()
    if secret:
        if not billing.verify_signature(raw, stripe_signature or "", secret, now=time.time()):
            raise HTTPException(status_code=400, detail="invalid signature")
    # No secret configured => dev/demo mode: accept unverified (documented).
    try:
        event = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON payload")
    result = billing.apply_stripe_event(_conn, event, ts=_now_iso())
    return JSONResponse(result)


@app.get("/api/exchanges")
def api_exchanges() -> JSONResponse:
    return JSONResponse(
        {
            "exchanges": [
                {"name": n, "urls": ADAPTERS[n].live_urls()} for n in DEFAULT_EXCHANGES
            ]
        }
    )


@app.get("/api/cross")
def api_cross(
    min_venues: int = Query(2, ge=1, le=10),
    limit: int = Query(100, ge=1, le=1000),
    demo: bool = Query(False),
) -> JSONResponse:
    snap = sources.get_records(force_demo=True if demo else None)
    result = xexchange.cross_scan(
        snap["records"], min_venues=min_venues, limit=limit
    )
    result["meta"] = {"sources": snap["sources"], "cache_age_s": snap["age"]}
    return JSONResponse(result)


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


# Cache-buster for CSS/JS: changes on every server (re)start, so a pull +
# restart always reaches the browser without a hard refresh.
_ASSET_V = str(int(time.time()))


def _stamp_assets(html: str) -> str:
    for name in ("styles.css", "landing.css", "app.js", "landing.js"):
        html = html.replace(f"/static/{name}", f"/static/{name}?v={_ASSET_V}")
    return html


@app.get("/")
def landing(request: Request) -> HTMLResponse:
    # OG/Twitter scrapers require absolute URLs, so template the request host
    # into the share metadata and canonical link.
    base = str(request.base_url)  # e.g. "https://basispulse.example.com/"
    html = (_STATIC / "landing.html").read_text(encoding="utf-8")
    html = html.replace('content="/static/og.png"', f'content="{base}static/og.png"')
    html = html.replace('<link rel="canonical" href="/" />',
                        f'<link rel="canonical" href="{base}" />')
    return HTMLResponse(_stamp_assets(html))


@app.get("/app")
def dashboard() -> HTMLResponse:
    html = (_STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(_stamp_assets(html))


# Serve CSS/JS. Mounted last so it doesn't shadow the API routes above.
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
