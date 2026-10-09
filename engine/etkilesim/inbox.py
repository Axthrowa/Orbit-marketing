"""Uygulama içi gelen kutusu (master prompt §42): okunmamış rozeti, okundu, tümünü okundu yap.

Kullanıcı kutusu: o kişiye ait hatırlatmalar. Yönetici kutusu (`audience='admin'`): eskalasyonlar.
Kayıtlar `dedupe_key` ile tekildir; dış kanal (Telegram/e-posta/Teams) gönderiminden bağımsızdır,
yani dış bildirimler kapalı olsa da uygulama içinde görünür.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from .clock import now_utc, to_iso
from .errors import ValidationFailed


def add(
    conn: sqlite3.Connection,
    audience: str,
    user_id: int | None,
    kind: str,
    title: str,
    body: str,
    dedupe_key: str,
    now: datetime | None = None,
) -> int | None:
    if audience not in ("user", "admin"):
        raise ValidationFailed("Geçersiz bildirim hedefi")
    cur = conn.execute(
        "INSERT OR IGNORE INTO inbox(user_id,audience,kind,title,body,dedupe_key,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (user_id, audience, kind, title[:200], body[:2000], dedupe_key, to_iso(now or now_utc())),
    )
    return (cur.lastrowid or 0) if cur.rowcount else None


def _scope(user_id: int | None) -> tuple[str, tuple[Any, ...]]:
    if user_id is None:
        return "audience='admin'", ()
    return "audience='user' AND user_id=?", (user_id,)


def listing(conn: sqlite3.Connection, user_id: int | None, limit: int = 50) -> dict[str, Any]:
    where, args = _scope(user_id)
    rows = conn.execute(
        "SELECT i.id, i.kind, i.title, i.body, i.created_at, i.read_at, i.user_id, u.name AS user_name"  # noqa: S608 - sabit
        " FROM inbox i LEFT JOIN users u ON u.id=i.user_id WHERE " + where + " ORDER BY i.id DESC LIMIT ?",
        (*args, max(1, min(limit, 200))),
    ).fetchall()
    return {"items": [dict(r) for r in rows], "unread": unread(conn, user_id)}


def unread(conn: sqlite3.Connection, user_id: int | None) -> int:
    where, args = _scope(user_id)
    row = conn.execute(f"SELECT COUNT(*) FROM inbox WHERE {where} AND read_at IS NULL", args).fetchone()  # noqa: S608
    return int(row[0])


def mark_read(
    conn: sqlite3.Connection, user_id: int | None, ids: list[int] | None, now: datetime | None = None
) -> int:
    """`ids` None ise o kutudaki tümü. Başkasının kutusundaki kayıtlar işaretlenemez."""
    where, args = _scope(user_id)
    params: list[Any] = [to_iso(now or now_utc()), *args]
    sql = f"UPDATE inbox SET read_at=? WHERE {where} AND read_at IS NULL"  # noqa: S608 - sabit parçalar
    if ids is not None:
        clean = [int(i) for i in ids][:500]
        if not clean:
            return 0
        sql += f" AND id IN ({','.join('?' for _ in clean)})"
        params.extend(clean)
    return conn.execute(sql, params).rowcount
