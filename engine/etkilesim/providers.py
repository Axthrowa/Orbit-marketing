"""Platform sağlık durumu ve devre kesici: bot koruması görülürse platform duraklatılır.

Meydan okuma (CAPTCHA/hız sınırı) ATLATILMAZ; platform bir süre dinlendirilir ve gönderiler
'DATA_UNAVAILABLE' olarak işaretlenir (elle giriş mümkündür).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .clock import from_iso, now_utc, to_iso

FIRST_BLOCK_PAUSE = timedelta(minutes=30)
REPEATED_BLOCK_PAUSE = timedelta(hours=6)
LONG_BLOCK_PAUSE = timedelta(hours=24)


def _ensure(conn: sqlite3.Connection, platform: str) -> None:
    conn.execute("INSERT OR IGNORE INTO provider_state(platform) VALUES (?)", (platform,))


def is_paused(conn: sqlite3.Connection, platform: str, now: datetime | None = None) -> bool:
    row = conn.execute("SELECT paused_until FROM provider_state WHERE platform=?", (platform,)).fetchone()
    if row is None or row["paused_until"] is None:
        return False
    return from_iso(row["paused_until"]) > (now or now_utc())


def record_success(conn: sqlite3.Connection, platform: str, now: datetime | None = None) -> None:
    _ensure(conn, platform)
    conn.execute(
        "UPDATE provider_state SET consecutive_blocks=0, paused_until=NULL, last_error=NULL,"
        " last_success_at=? WHERE platform=?",
        (to_iso(now or now_utc()), platform),
    )


def record_failure(
    conn: sqlite3.Connection, platform: str, error: str, blocked: bool, now: datetime | None = None
) -> None:
    """`blocked=True` bot koruması/hız sınırı demektir ve platformu duraklatır."""
    moment = now or now_utc()
    _ensure(conn, platform)
    row = conn.execute(
        "SELECT consecutive_blocks FROM provider_state WHERE platform=?", (platform,)
    ).fetchone()
    blocks = int(row["consecutive_blocks"]) + (1 if blocked else 0)
    paused_until: str | None = None
    if blocked:
        pause = (
            FIRST_BLOCK_PAUSE if blocks < 2 else (REPEATED_BLOCK_PAUSE if blocks < 4 else LONG_BLOCK_PAUSE)
        )
        paused_until = to_iso(moment + pause)
    conn.execute(
        "UPDATE provider_state SET consecutive_blocks=?, paused_until=COALESCE(?, paused_until),"
        " last_failure_at=?, last_error=? WHERE platform=?",
        (blocks, paused_until, to_iso(moment), error[:300], platform),
    )


def list_states(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict[str, Any]]:
    moment = now or now_utc()
    rows = conn.execute("SELECT * FROM provider_state ORDER BY platform").fetchall()
    states: list[dict[str, Any]] = []
    for row in rows:
        paused = row["paused_until"] is not None and from_iso(row["paused_until"]) > moment
        states.append({**dict(row), "paused": paused})
    return states
