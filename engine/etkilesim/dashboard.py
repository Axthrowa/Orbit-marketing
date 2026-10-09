"""Arayüz için tek çağrıda pano durumu. Bilinmeyen sayaçlar None kalır (0 gösterilmez).

`user_id` verilirse kullanıcı hesabı görünümüdür: yalnızca o kişinin paylaşımları, sayaçları ve
bildirimleri döner. Ekip/topluluk adları ve hesap listesi (yalnızca ad + ekip) her iki görünümde de vardır.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from . import auth, catalog, inbox, mockprovider, notify, providers, radar, secrets_store, settings
from .clock import days_between, from_iso, now_utc, to_iso

POST_LIMIT = 300


def _where(conditions: list[str]) -> str:
    return ("WHERE " + " AND ".join(conditions)) if conditions else ""


def _sum(conn: sqlite3.Connection, column: str, where: str, args: tuple[Any, ...]) -> int | None:
    row = conn.execute(
        f"SELECT SUM({column}) AS s FROM posts p JOIN users u ON u.id=p.user_id {where}",  # noqa: S608
        args,
    ).fetchone()
    return None if row["s"] is None else int(row["s"])


def get_state(
    conn: sqlite3.Connection,
    team_id: int | None = None,
    now: datetime | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    moment = now or now_utc()
    # Koşullar yalnızca sabit metinlerden kurulur; değerler parametre olarak gider.
    post_conditions: list[str] = ["p.archived_at IS NULL"]
    user_conditions: list[str] = []
    args_list: list[Any] = []
    if team_id is not None:
        post_conditions.append("u.team_id=?")
        user_conditions.append("u.team_id=?")
        args_list.append(team_id)
    if user_id is not None:
        post_conditions.append("u.id=?")
        user_conditions.append("u.id=?")
        args_list.append(user_id)
    args = tuple(args_list)
    where = _where(post_conditions)
    user_where = _where(user_conditions)

    stats = conn.execute(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN p.current_likes IS NULL AND p.views_count IS NULL"  # noqa: S608 - where sabit parçalardır
        " AND p.comments_count IS NULL AND p.shares_count IS NULL THEN 1 ELSE 0 END) AS unknown,"
        " AVG(p.positive_sentiment_ratio) AS pos, AVG(p.negative_sentiment_ratio) AS neg"
        " FROM posts p JOIN users u ON u.id=p.user_id " + where,
        args,
    ).fetchone()
    users = conn.execute(
        f"SELECT u.status, COUNT(*) AS n FROM users u {user_where} GROUP BY u.status",  # noqa: S608 - sabit parça
        args,
    ).fetchall()
    by_status = {r["status"]: int(r["n"]) for r in users}
    kpis = {
        "posts": int(stats["n"]),
        "posts_without_metrics": int(stats["unknown"] or 0),
        "users_total": sum(by_status.values()),
        "users_active": by_status.get("active", 0),
        "users_flagged": by_status.get("flagged", 0),
        "likes": _sum(conn, "p.current_likes", where, args),
        "comments": _sum(conn, "p.comments_count", where, args),
        "shares": _sum(conn, "p.shares_count", where, args),
        "views": _sum(conn, "p.views_count", where, args),
        "avg_positive": None if stats["pos"] is None else round(float(stats["pos"]), 4),
        "avg_negative": None if stats["neg"] is None else round(float(stats["neg"]), 4),
    }
    post_rows = conn.execute(
        "SELECT p.id, p.platform, p.url, p.current_likes AS likes, p.comments_count AS comments,"  # noqa: S608 - where sabit parçalardır
        " p.shares_count AS shares, p.views_count AS views, p.initial_likes,"
        " p.positive_sentiment_ratio AS positive, p.negative_sentiment_ratio AS negative,"
        " p.sentiment_sample, p.data_status, p.last_error, p.last_metrics_at, p.last_attempt_at,"
        " p.posted_at, p.preview_text, p.note, p.content_type, p.game_id, p.campaign_id,"
        " u.id AS user_id, u.name AS user_name, t.name AS team_name, c.name AS community_name,"
        " g.name AS game_name, k.name AS campaign_name,"
        " (SELECT s.source FROM post_metric_snapshots s WHERE s.post_id=p.id"
        " ORDER BY s.captured_at DESC LIMIT 1)"
        " AS last_source FROM posts p JOIN users u ON u.id=p.user_id"
        " LEFT JOIN teams t ON t.id=u.team_id LEFT JOIN communities c ON c.id=p.community_id"
        " LEFT JOIN games g ON g.id=p.game_id LEFT JOIN campaigns k ON k.id=p.campaign_id "
        + where
        + " ORDER BY p.created_at DESC, p.id DESC LIMIT ?",
        (*args, POST_LIMIT),
    ).fetchall()
    people_rows = conn.execute(
        "SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name, u.telegram_id IS NOT NULL"  # noqa: S608 - sabit parçalar
        " AS has_telegram, u.email IS NOT NULL AS has_email, u.strike_count, u.total_strikes, u.status,"
        " u.last_post_at, u.flagged_at,"
        " COUNT(p.id) AS posts, SUM(p.current_likes) AS likes, SUM(p.comments_count) AS comments,"
        " SUM(p.shares_count) AS shares, SUM(p.views_count) AS views FROM users u"
        " LEFT JOIN teams t ON t.id=u.team_id LEFT JOIN posts p ON p.user_id=u.id AND p.archived_at IS NULL "
        + user_where
        + " GROUP BY u.id ORDER BY u.name COLLATE NOCASE",
        args,
    ).fetchall()
    team_people = []
    for row in people_rows:
        item = dict(row)
        item["has_telegram"] = bool(item["has_telegram"])
        item["has_email"] = bool(item["has_email"])
        item["max_strikes"] = int(settings.get(conn, "max_strikes", row["team_id"]))
        item["inactivity_days"] = int(settings.get(conn, "inactivity_days", row["team_id"]))
        item["days_since_last_post"] = (
            days_between(from_iso(row["last_post_at"]), moment) if row["last_post_at"] else None
        )
        parts = [row["likes"], row["comments"], row["shares"]]
        item["engagement"] = None if all(v is None for v in parts) else sum(v or 0 for v in parts)
        team_people.append(item)
    teams = [
        dict(r)
        for r in conn.execute(
            "SELECT t.id, t.name, t.chat_id, COUNT(DISTINCT u.id) AS members,"
            " COUNT(DISTINCT CASE WHEN u.status='flagged' THEN u.id END) AS flagged FROM teams t"
            " LEFT JOIN users u ON u.team_id=t.id GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
        ).fetchall()
    ]
    accounts = [
        dict(r)
        for r in conn.execute(
            "SELECT u.id, u.name, u.role, u.team_id, t.name AS team_name FROM users u"
            " LEFT JOIN teams t ON t.id=u.team_id"
            " WHERE u.status <> 'inactive' ORDER BY u.name COLLATE NOCASE"
        ).fetchall()
    ]
    notice_where = "WHERE n.user_id=?" if user_id is not None else ""
    notices = [
        dict(r)
        for r in conn.execute(
            "SELECT n.id, n.kind, n.status, n.attempts, n.last_error, n.created_at, n.sent_at,"  # noqa: S608 - sabit parça
            " u.name AS user_name FROM notifications n LEFT JOIN users u ON u.id=n.user_id "
            + notice_where
            + " ORDER BY n.id DESC LIMIT 25",
            (user_id,) if user_id is not None else (),
        ).fetchall()
    ]
    return {
        "generated_at": to_iso(moment),
        "team_filter": team_id,
        "user_filter": user_id,
        "kpis": kpis,
        "posts": [dict(r) for r in post_rows],
        "people": team_people,
        "accounts": accounts,
        "teams": teams,
        "games": catalog.list_games(conn),
        "campaigns": catalog.list_campaigns(conn),
        "communities": radar.ranked(conn),
        "providers": providers.list_states(conn, moment),
        "notifications": notices,
        "notification_summary": notify.due_summary(conn, user_id),
        "settings": {"values": settings.effective(conn), "spec": settings.describe()},
        "inbox_unread": inbox.unread(conn, user_id),
        "provider_mode": mockprovider.provider_mode(),
        "security": {
            "pin_set": auth.pin_is_set(conn),
            "telegram_token_set": secrets_store.has_token(),
            "secrets": secrets_store.status(),
        },
    }
