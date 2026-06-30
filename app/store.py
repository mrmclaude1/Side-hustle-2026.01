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
