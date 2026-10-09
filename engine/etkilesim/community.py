"""Topluluk kayıtları ve paylaşım hafızası (mükerrer/yakın zamanlı paylaşım uyarısı)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any

from . import settings
from .clock import days_between, from_iso, now_utc, to_iso
from .db import audit
from .errors import NotFound, ValidationFailed

PREVIEW_LENGTH = 150


def name_key(name: str) -> str:
    """'r/IndieGaming', '/r/indiegaming ' → 'indiegaming'."""
    value = re.sub(r"\s+", " ", name.strip()).lower()
    return re.sub(r"^/?r/", "", value)


def preview(text: str | None) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    return cleaned[:PREVIEW_LENGTH]


def find(conn: sqlite3.Connection, name: str | None = None, url: str | None = None) -> sqlite3.Row | None:
    if url:
        row = conn.execute("SELECT * FROM communities WHERE url=?", (url,)).fetchone()
        if row is not None:
            return row  # type: ignore[no-any-return]
    if name:
        return conn.execute(  # type: ignore[no-any-return]
            "SELECT * FROM communities WHERE name_key=? ORDER BY id LIMIT 1", (name_key(name),)
        ).fetchone()
    return None


def get_or_create(
    conn: sqlite3.Connection,
    name: str,
    platform: str,
    url: str | None,
    actor: str,
    now: datetime | None = None,
) -> int:
    clean = " ".join(name.split())
    if not 1 <= len(clean) <= 160:
        raise ValidationFailed("Topluluk adı 1-160 karakter olmalı")
    existing = find(conn, name=clean, url=url)
    if existing is not None:
        return int(existing["id"])
    moment = now or now_utc()
    created = conn.execute(
        "INSERT INTO communities(name, name_key, platform, url, status, discovered_at)"
        " VALUES (?,?,?,?, 'approved', ?)",
        (clean, name_key(clean), platform, url, to_iso(moment)),
    )
    community_id = int(created.lastrowid or 0)
    audit(conn, actor, "community.create", "community", community_id, {"name": clean}, moment)
    return community_id


def search(conn: sqlite3.Connection, query: str, limit: int = 8) -> list[dict[str, Any]]:
    key = name_key(query)
    rows = conn.execute(
        "SELECT id, name, platform, url, status FROM communities"
        " WHERE name_key LIKE ? ESCAPE '\\' AND status <> 'blocked' ORDER BY name_key LIMIT ?",
        ("%" + key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def set_state(
    conn: sqlite3.Connection,
    community_id: int,
    status: str | None,
    favorite: bool | None,
    actor: str,
    now: datetime | None = None,
) -> None:
    if conn.execute("SELECT 1 FROM communities WHERE id=?", (community_id,)).fetchone() is None:
        raise NotFound("Topluluk bulunamadı")
    if status is not None:
        if status not in ("discovered", "approved", "blocked"):
            raise ValidationFailed("Geçersiz topluluk durumu")
        conn.execute("UPDATE communities SET status=? WHERE id=?", (status, community_id))
    if favorite is not None:
        conn.execute("UPDATE communities SET favorite=? WHERE id=?", (1 if favorite else 0, community_id))
    audit(
        conn,
        actor,
        "community.update",
        "community",
        community_id,
        {"status": status, "favorite": favorite},
        now,
    )


def log_post(
    conn: sqlite3.Connection,
    community_id: int,
    user_id: int,
    post_id: int | None,
    post_url: str,
    preview_text: str | None,
    posted_at: datetime,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO community_logs(community_id,user_id,post_id,post_url,"
        "post_preview_text,posted_at) VALUES (?,?,?,?,?,?)",
        (community_id, user_id, post_id, post_url, preview(preview_text), to_iso(posted_at)),
    )


def _tier(days: int, avoid: int, recent: int, caution: int) -> str:
    if days <= avoid:
        return "AVOID"
    if days <= recent:
        return "RECENTLY_USED"
    if days <= caution:
        return "CAUTION"
    return "SAFE"


_TIER_MESSAGES = {
    "AVOID": "Çok yakın zamanda paylaşım yapılmış — şimdi paylaşmaktan kaçının.",
    "RECENTLY_USED": "Yakın zamanda kullanılmış bir topluluk.",
    "CAUTION": "Bir süre önce paylaşım yapılmış, dikkatli olun.",
    "SAFE": "Son paylaşımın üzerinden yeterince zaman geçmiş.",
}


def posting_context(
    conn: sqlite3.Connection,
    name: str | None = None,
    url: str | None = None,
    community_id: int | None = None,
    team_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Topluluk seçildiğinde gösterilecek geçmiş: son paylaşım tarihi, paylaşan, 150 karakter."""
    moment = now or now_utc()
    if community_id is not None:
        community = conn.execute("SELECT * FROM communities WHERE id=?", (community_id,)).fetchone()
    else:
        community = find(conn, name=name, url=url)
    base: dict[str, Any] = {
        "known": community is not None,
        "community": None
        if community is None
        else {
            "id": community["id"],
            "name": community["name"],
            "platform": community["platform"],
            "status": community["status"],
        },
        "previous_posts": 0,
        "last_post": None,
        "days_since_last_post": None,
        "recent_posts": [],
    }
    if community is None:
        return {
            **base,
            "recommendation": "CLEAN",
            "message": "Bu toplulukta henüz paylaşım yapılmadı (Temiz)",
        }
    rows = conn.execute(
        "SELECT l.posted_at, l.post_url, l.post_preview_text, u.name AS user_name,"
        " t.name AS team_name, p.note AS note, k.name AS campaign_name FROM community_logs l"
        " JOIN users u ON u.id=l.user_id LEFT JOIN teams t ON t.id=u.team_id"
        " LEFT JOIN posts p ON p.id=l.post_id LEFT JOIN campaigns k ON k.id=p.campaign_id"
        " WHERE l.community_id=? AND (p.id IS NULL OR p.archived_at IS NULL)"
        " ORDER BY l.posted_at DESC, l.id DESC",
        (community["id"],),
    ).fetchall()
    if not rows:
        return {
            **base,
            "recommendation": "CLEAN",
            "message": "Bu toplulukta henüz paylaşım yapılmadı (Temiz)",
        }
    entries = [
        {
            "posted_at": r["posted_at"],
            "user": r["user_name"],
            "team": r["team_name"],
            "preview": r["post_preview_text"],
            "url": r["post_url"],
            "note": r["note"],
            "campaign": r["campaign_name"],
        }
        for r in rows
    ]
    last = entries[0]
    days = days_between(from_iso(last["posted_at"]), moment)
    avoid = int(settings.get(conn, "community_avoid_days", team_id))
    recent = int(settings.get(conn, "community_recent_days", team_id))
    caution = int(settings.get(conn, "community_caution_days", team_id))
    tier = _tier(days, avoid, recent, caution)
    return {
        **base,
        "previous_posts": len(entries),
        "last_post": last,
        "days_since_last_post": days,
        "recent_posts": entries[:5],
        "recommendation": tier,
        "message": _TIER_MESSAGES[tier],
    }
