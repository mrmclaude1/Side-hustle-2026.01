"""SQLite-backed history store for scan snapshots.

A single-point-in-time Radar Score is mostly noise; a score that is *rising*
across snapshots is the actual signal. This module persists each scan so we can
compute per-asset trends and serve sparklines.

Design notes:
- Uses stdlib `sqlite3` (no extra dependency).
- All functions take a `conn` and any timestamp explicitly — no hidden clock —
  so the whole module is deterministic and unit-testable against `:memory:`.
- The DB path is resolved by the caller (see `app.main`); tests pass ":memory:".
"""

from __future__ import annotations

import secrets
import sqlite3
from typing import Optional

# Columns we persist per asset, in order. Keeping this list in one place keeps
# the INSERT and the row->dict mapping in sync.
_ASSET_COLS = (
    "base",
    "radar_score",
    "price",
    "change_pct",
    "basis_bps",
    "range_pct",
    "spread_bps",
    "open_interest",
    "volume_usd",
)


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            ts     TEXT NOT NULL,
            source TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS asset_points (
            snapshot_id  INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
            base         TEXT NOT NULL,
            radar_score  REAL,
            price        REAL,
            change_pct   REAL,
            basis_bps    REAL,
            range_pct    REAL,
            spread_bps   REAL,
            open_interest REAL,
            volume_usd   REAL
        );
        CREATE INDEX IF NOT EXISTS idx_points_base ON asset_points(base);
        CREATE INDEX IF NOT EXISTS idx_points_snap ON asset_points(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);

        CREATE TABLE IF NOT EXISTS alert_rules (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            metric    TEXT NOT NULL,
            op        TEXT NOT NULL,
            threshold REAL NOT NULL,
            enabled   INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS alert_events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            rule_id   INTEGER,
            rule_name TEXT,
            base      TEXT,
            metric    TEXT,
            op        TEXT,
            threshold REAL,
            value     REAL
        );
        CREATE INDEX IF NOT EXISTS idx_events_ts ON alert_events(ts);

        CREATE TABLE IF NOT EXISTS api_keys (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            key                TEXT UNIQUE NOT NULL,
            plan               TEXT NOT NULL DEFAULT 'free',
            label              TEXT,
            active             INTEGER NOT NULL DEFAULT 1,
            stripe_customer_id TEXT,
            created_ts         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_keys_customer ON api_keys(stripe_customer_id);
        """
    )
    conn.commit()


def record_scan(
    conn: sqlite3.Connection,
    scan_result: dict,
    ts: str,
    source: str = "live",
) -> int:
    """Persist one scan. `ts` is an ISO8601 string supplied by the caller.

    Returns the new snapshot id.
    """
    cur = conn.execute(
        "INSERT INTO snapshots (ts, source) VALUES (?, ?)", (ts, source)
    )
    snap_id = cur.lastrowid
    rows = [
        (snap_id,) + tuple(a.get(c) for c in _ASSET_COLS)
        for a in scan_result.get("assets", [])
    ]
    placeholders = ", ".join(["?"] * (len(_ASSET_COLS) + 1))
    conn.executemany(
        f"INSERT INTO asset_points (snapshot_id, {', '.join(_ASSET_COLS)}) "
        f"VALUES ({placeholders})",
        rows,
    )
    conn.commit()
    return snap_id


def history(conn: sqlite3.Connection, base: str, limit: int = 100) -> list[dict]:
    """Return the most recent `limit` points for `base`, oldest-first."""
    rows = conn.execute(
        """
        SELECT s.ts AS ts, p.radar_score, p.price, p.change_pct,
               p.basis_bps, p.volume_usd
        FROM asset_points p
        JOIN snapshots s ON s.id = p.snapshot_id
        WHERE p.base = ?
        ORDER BY s.id DESC
        LIMIT ?
        """,
        (base.upper(), limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def previous_scores(
    conn: sqlite3.Connection, before_snapshot_id: Optional[int] = None
) -> dict[str, float]:
    """Map base -> radar_score from the latest snapshot.

    If `before_snapshot_id` is given, use the latest snapshot strictly older
    than it (so a freshly-recorded scan can compare against the prior one).
    """
    if before_snapshot_id is None:
        row = conn.execute("SELECT MAX(id) AS m FROM snapshots").fetchone()
    else:
        row = conn.execute(
            "SELECT MAX(id) AS m FROM snapshots WHERE id < ?",
            (before_snapshot_id,),
        ).fetchone()
    snap_id = row["m"] if row else None
    if snap_id is None:
        return {}
    rows = conn.execute(
        "SELECT base, radar_score FROM asset_points WHERE snapshot_id = ?",
        (snap_id,),
    ).fetchall()
    return {r["base"]: r["radar_score"] for r in rows if r["radar_score"] is not None}


def annotate_trend(
    conn: sqlite3.Connection, scan_result: dict, baseline: Optional[dict] = None
) -> dict:
    """Add `score_delta` (vs the previous snapshot) to each asset in-place.

    `baseline` lets the caller pass a pre-fetched base->score map (e.g. the
    snapshot just before the one they recorded); otherwise the latest snapshot
    is used. Assets with no prior point get score_delta = None.
    """
    prev = baseline if baseline is not None else previous_scores(conn)
    for a in scan_result.get("assets", []):
        p = prev.get(a["base"])
        cur = a.get("radar_score")
        a["score_delta"] = (
            round(cur - p, 1) if (p is not None and cur is not None) else None
        )
    return scan_result


# --- Alert rules & events -------------------------------------------------

def add_rule(
    conn: sqlite3.Connection,
    name: str,
    metric: str,
    op: str,
    threshold: float,
    enabled: bool = True,
) -> dict:
    cur = conn.execute(
        "INSERT INTO alert_rules (name, metric, op, threshold, enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, metric, op, threshold, 1 if enabled else 0),
    )
    conn.commit()
    return get_rule(conn, cur.lastrowid)


def get_rule(conn: sqlite3.Connection, rule_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
    return _rule_to_dict(row) if row else None


def list_rules(conn: sqlite3.Connection, enabled_only: bool = False) -> list[dict]:
    q = "SELECT * FROM alert_rules"
    if enabled_only:
        q += " WHERE enabled = 1"
    q += " ORDER BY id"
    return [_rule_to_dict(r) for r in conn.execute(q).fetchall()]


def set_rule_enabled(conn: sqlite3.Connection, rule_id: int, enabled: bool) -> bool:
    cur = conn.execute(
        "UPDATE alert_rules SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, rule_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> bool:
    cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    conn.commit()
    return cur.rowcount > 0


def _rule_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "metric": row["metric"],
        "op": row["op"],
        "threshold": row["threshold"],
        "enabled": bool(row["enabled"]),
    }


def record_events(conn: sqlite3.Connection, triggers: list[dict], ts: str) -> int:
    if not triggers:
        return 0
    conn.executemany(
        "INSERT INTO alert_events "
        "(ts, rule_id, rule_name, base, metric, op, threshold, value) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (ts, t.get("rule_id"), t.get("rule_name"), t.get("base"),
             t.get("metric"), t.get("op"), t.get("threshold"), t.get("value"))
            for t in triggers
        ],
    )
    conn.commit()
    return len(triggers)


def list_events(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM alert_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- API keys / plans -----------------------------------------------------

def generate_key_string() -> str:
    return "ms_" + secrets.token_urlsafe(24)


def _key_to_dict(row: sqlite3.Row) -> dict:
    return {
        "key": row["key"],
        "plan": row["plan"],
        "label": row["label"],
        "active": bool(row["active"]),
        "stripe_customer_id": row["stripe_customer_id"],
        "created_ts": row["created_ts"],
    }


def create_key(
    conn: sqlite3.Connection,
    plan: str = "free",
    label: Optional[str] = None,
    ts: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    key: Optional[str] = None,
) -> dict:
    key = key or generate_key_string()
    conn.execute(
        "INSERT INTO api_keys (key, plan, label, stripe_customer_id, created_ts) "
        "VALUES (?, ?, ?, ?, ?)",
        (key, plan, label, stripe_customer_id, ts),
    )
    conn.commit()
    return get_key(conn, key)


def get_key(conn: sqlite3.Connection, key: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM api_keys WHERE key = ?", (key,)).fetchone()
    return _key_to_dict(row) if row else None


def resolve_plan(conn: sqlite3.Connection, key: Optional[str]) -> Optional[str]:
    """Return the plan for an active key, or None if the key is missing/invalid/
    inactive. Callers treat None as 'anonymous' (free)."""
    if not key:
        return None
    row = conn.execute(
        "SELECT plan FROM api_keys WHERE key = ? AND active = 1", (key,)
    ).fetchone()
    return row["plan"] if row else None


def key_is_known(conn: sqlite3.Connection, key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM api_keys WHERE key = ?", (key,)
    ).fetchone() is not None


def set_key_plan(conn: sqlite3.Connection, key: str, plan: str) -> bool:
    cur = conn.execute("UPDATE api_keys SET plan = ? WHERE key = ?", (plan, key))
    conn.commit()
    return cur.rowcount > 0


def deactivate_key(conn: sqlite3.Connection, key: str) -> bool:
    cur = conn.execute("UPDATE api_keys SET active = 0 WHERE key = ?", (key,))
    conn.commit()
    return cur.rowcount > 0


def list_keys(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM api_keys ORDER BY id").fetchall()
    return [_key_to_dict(r) for r in rows]


def upsert_key_for_customer(
    conn: sqlite3.Connection,
    stripe_customer_id: str,
    plan: str,
    ts: Optional[str] = None,
) -> dict:
    """Find the key mapped to a Stripe customer and set its plan; create one if
    none exists. Used by the billing webhook."""
    row = conn.execute(
        "SELECT * FROM api_keys WHERE stripe_customer_id = ? ORDER BY id LIMIT 1",
        (stripe_customer_id,),
    ).fetchone()
    if row:
        conn.execute("UPDATE api_keys SET plan = ? WHERE id = ?", (plan, row["id"]))
        conn.commit()
        return get_key(conn, row["key"])
    return create_key(conn, plan=plan, ts=ts, stripe_customer_id=stripe_customer_id,
                       label="via stripe")


def map_key_to_customer(
    conn: sqlite3.Connection, key: str, stripe_customer_id: str
) -> bool:
    cur = conn.execute(
        "UPDATE api_keys SET stripe_customer_id = ? WHERE key = ?",
        (stripe_customer_id, key),
    )
    conn.commit()
    return cur.rowcount > 0


def prune(conn: sqlite3.Connection, keep_snapshots: int = 2000) -> int:
    """Delete oldest snapshots beyond `keep_snapshots`. Returns rows deleted."""
    row = conn.execute("SELECT COUNT(*) AS c FROM snapshots").fetchone()
    total = row["c"]
    if total <= keep_snapshots:
        return 0
    cutoff = conn.execute(
        "SELECT id FROM snapshots ORDER BY id DESC LIMIT 1 OFFSET ?",
        (keep_snapshots - 1,),
    ).fetchone()["id"]
    conn.execute("DELETE FROM asset_points WHERE snapshot_id < ?", (cutoff,))
    cur = conn.execute("DELETE FROM snapshots WHERE id < ?", (cutoff,))
    conn.commit()
    return cur.rowcount
