"""Analitik (master prompt §13, §44–48, §68): türetilmiş gönderi metrikleri, normalize performans skoru,
liderlik tablosu ve platform / içerik türü / kampanya / oyun / topluluk kırılımları.

Büyük hesapların herkesi geçmemesi için etkileşim logaritmik ölçeklenir ve göreli normalize edilir.
Bileşen ağırlıkları yönetici ayarıdır; toplamları 100 olmak zorunda değildir (oranlanır).
Bilinmeyen sayaçlar hesaba 0 olarak katılmaz; hiç bilinen sayaç yoksa sonuç None'dır.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from . import settings, topics
from .clock import from_iso, now_utc, to_iso

WEIGHT_KEYS = {
    "post_consistency": "perf_weight_consistency",
    "engagement_score": "perf_weight_engagement",
    "sentiment_score": "perf_weight_sentiment",
    "community_diversity": "perf_weight_diversity",
    "engagement_velocity": "perf_weight_velocity",
    "campaign_contribution": "perf_weight_campaign",
}
PERIODS = (1, 7, 30, 90, 365)


def engagement(likes: int | None, comments: int | None, shares: int | None) -> int | None:
    if likes is None and comments is None and shares is None:
        return None
    return (likes or 0) + (comments or 0) + (shares or 0)


# ------------------------------------------------------------------------------ gönderi metrikleri


def post_metrics(conn: sqlite3.Connection, post_id: int) -> dict[str, Any]:
    """velocity_1h/6h/24h: paylaşımdan sonraki ilk N saatte saat başına etkileşim; growth: ilk→son ölçüm."""
    post = conn.execute("SELECT posted_at FROM posts WHERE id=?", (post_id,)).fetchone()
    if post is None:
        return {}
    posted = from_iso(post["posted_at"])
    snaps = conn.execute(
        "SELECT likes, comments, shares, views, captured_at FROM post_metric_snapshots"
        " WHERE post_id=? ORDER BY captured_at",
        (post_id,),
    ).fetchall()
    result: dict[str, Any] = {}
    for hours in (1, 6, 24):
        limit = posted + timedelta(hours=hours)
        inside = [s for s in snaps if from_iso(s["captured_at"]) <= limit]
        value = (
            engagement(inside[-1]["likes"], inside[-1]["comments"], inside[-1]["shares"]) if inside else None
        )
        result[f"velocity_{hours}h"] = None if value is None else round(value / hours, 2)
    for key in ("likes", "comments", "shares", "views"):
        known = [s[key] for s in snaps if s[key] is not None]
        result[f"{key}_growth"] = (known[-1] - known[0]) if len(known) >= 2 else None
    total = engagement(snaps[-1]["likes"], snaps[-1]["comments"], snaps[-1]["shares"]) if snaps else None
    views = next((s["views"] for s in reversed(snaps) if s["views"] is not None), None)
    result["engagement_total"] = total
    result["engagement_rate"] = round(total / views, 4) if total is not None and views else None
    return result


# ------------------------------------------------------------------------------------- filtreler


@dataclass(frozen=True)
class Filters:
    days: int | None = 30
    campaign_id: int | None = None
    game_id: int | None = None
    platform: str | None = None
    team_id: int | None = None
    user_id: int | None = None
    community_id: int | None = None

    def clause(self, now: datetime) -> tuple[str, tuple[Any, ...]]:
        conditions = ["p.archived_at IS NULL"]
        args: list[Any] = []
        if self.days is not None:
            conditions.append("p.posted_at >= ?")
            args.append(to_iso(now - timedelta(days=self.days)))
        for column, value in (
            ("p.campaign_id", self.campaign_id),
            ("p.game_id", self.game_id),
            ("p.platform", self.platform),
            ("u.team_id", self.team_id),
            ("u.id", self.user_id),
            ("p.community_id", self.community_id),
        ):
            if value is not None:
                conditions.append(f"{column}=?")
                args.append(value)
        return "WHERE " + " AND ".join(conditions), tuple(args)


def _posts(conn: sqlite3.Connection, filters: Filters, now: datetime) -> list[sqlite3.Row]:
    where, args = filters.clause(now)
    return conn.execute(
        "SELECT p.id, p.user_id, p.platform, p.content_type, p.campaign_id, p.game_id, p.community_id,"  # noqa: S608 - where sabit parçalardan
        " p.posted_at, p.current_likes AS likes, p.comments_count AS comments, p.shares_count AS shares,"
        " p.views_count AS views, p.positive_sentiment_ratio AS positive,"
        " p.negative_sentiment_ratio AS negative,"
        " p.sentiment_sample, k.status AS campaign_status FROM posts p JOIN users u ON u.id=p.user_id"
        " LEFT JOIN campaigns k ON k.id=p.campaign_id " + where,
        args,
    ).fetchall()


# --------------------------------------------------------------------------------- performans


@dataclass
class _Acc:
    posts: int = 0
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    views: int | None = None
    engagements: list[int] = field(default_factory=list)
    sentiments: list[float] = field(default_factory=list)
    velocities: list[float] = field(default_factory=list)
    communities: set[int] = field(default_factory=set)
    days: set[str] = field(default_factory=set)
    campaign_posts: int = 0

    def add(self, row: sqlite3.Row, velocity: float | None) -> None:
        self.posts += 1
        for key in ("likes", "comments", "shares", "views"):
            value = row[key]
            if value is not None:
                setattr(self, key, (getattr(self, key) or 0) + value)
        total = engagement(row["likes"], row["comments"], row["shares"])
        if total is not None:
            self.engagements.append(total)
        if row["positive"] is not None and row["negative"] is not None and row["sentiment_sample"]:
            self.sentiments.append(float(row["positive"]) - float(row["negative"]))
        if velocity is not None:
            self.velocities.append(velocity)
        if row["community_id"] is not None:
            self.communities.add(int(row["community_id"]))
        self.days.add(str(row["posted_at"])[:10])
        if row["campaign_id"] is not None:
            self.campaign_posts += 1

    def summary(self) -> dict[str, Any]:
        avg_eng = sum(self.engagements) / len(self.engagements) if self.engagements else None
        return {
            "posts": self.posts,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "views": self.views,
            "engagement": sum(self.engagements) if self.engagements else None,
            "avg_engagement": None if avg_eng is None else round(avg_eng, 1),
            "avg_sentiment": round(sum(self.sentiments) / len(self.sentiments), 4)
            if self.sentiments
            else None,
            "community_count": len(self.communities),
            "active_days": len(self.days),
        }


def _log_ratio(value: float | None, best: float) -> float:
    if value is None or value <= 0 or best <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(best))


def weights(conn: sqlite3.Connection) -> dict[str, float]:
    raw = {component: float(settings.get(conn, key)) for component, key in WEIGHT_KEYS.items()}
    total = sum(raw.values()) or 1.0
    return {component: value / total for component, value in raw.items()}


def leaderboard(
    conn: sqlite3.Connection, filters: Filters, now: datetime | None = None
) -> list[dict[str, Any]]:
    moment = now or now_utc()
    rows = _posts(conn, filters, moment)
    velocity = {r["id"]: post_metrics(conn, int(r["id"])).get("velocity_24h") for r in rows}
    people_where = ["u.status <> 'inactive'"]
    args: list[Any] = []
    if filters.team_id is not None:
        people_where.append("u.team_id=?")
        args.append(filters.team_id)
    if filters.user_id is not None:
        people_where.append("u.id=?")
        args.append(filters.user_id)
    people = conn.execute(
        "SELECT u.id, u.name, u.team_id, u.total_strikes, u.strike_count, u.last_post_at, t.name AS team_name"  # noqa: S608 - sabit parçalar
        " FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE " + " AND ".join(people_where),
        tuple(args),
    ).fetchall()
    accs: dict[int, _Acc] = {int(p["id"]): _Acc() for p in people}
    for row in rows:
        if int(row["user_id"]) in accs:
            accs[int(row["user_id"])].add(row, velocity.get(row["id"]))
    period_days = filters.days or max(1, (moment - _first_post_time(conn, moment)).days)
    best_eng = max((a.summary()["avg_engagement"] or 0 for a in accs.values()), default=0)
    best_vel = max((sum(a.velocities) / len(a.velocities) for a in accs.values() if a.velocities), default=0)
    best_diversity = max((len(a.communities) for a in accs.values()), default=0)
    w = weights(conn)
    board: list[dict[str, Any]] = []
    for person in people:
        acc = accs[int(person["id"])]
        summary = acc.summary()
        inactivity = int(settings.get(conn, "inactivity_days", person["team_id"]))
        expected_days = max(1.0, period_days / max(1, inactivity))
        avg_vel = sum(acc.velocities) / len(acc.velocities) if acc.velocities else None
        components = {
            "post_consistency": min(1.0, len(acc.days) / expected_days),
            "engagement_score": _log_ratio(summary["avg_engagement"], best_eng),
            "sentiment_score": 0.5
            if summary["avg_sentiment"] is None
            else (summary["avg_sentiment"] + 1) / 2,
            # Farklı topluluk sayısı ekipteki en çeşitli kişiye göre: tek paylaşım tam puan almaz.
            "community_diversity": len(acc.communities) / best_diversity if best_diversity else 0.0,
            "engagement_velocity": _log_ratio(avg_vel, best_vel),
            "campaign_contribution": acc.campaign_posts / acc.posts if acc.posts else 0.0,
        }
        if acc.posts == 0:
            components = dict.fromkeys(components, 0.0)
        score = round(100 * sum(w[k] * v for k, v in components.items()), 1)
        board.append(
            {
                "user_id": person["id"],
                "name": person["name"],
                "team_name": person["team_name"],
                **summary,
                "posts_per_week": round(acc.posts / (period_days / 7), 2) if period_days else None,
                "warnings": int(person["total_strikes"]),
                "current_warnings": int(person["strike_count"]),
                "last_activity": person["last_post_at"],
                "components": {k: round(v, 3) for k, v in components.items()},
                "performance_score": score,
            }
        )
    board.sort(key=lambda item: (-item["performance_score"], item["name"].casefold()))
    for rank, item in enumerate(board, start=1):
        item["rank"] = rank
    return board


def _first_post_time(conn: sqlite3.Connection, now: datetime) -> datetime:
    row = conn.execute("SELECT MIN(posted_at) FROM posts WHERE archived_at IS NULL").fetchone()
    return from_iso(row[0]) if row and row[0] else now - timedelta(days=1)


# --------------------------------------------------------------------------------- kırılımlar


def _breakdown(rows: list[sqlite3.Row], key: str) -> list[dict[str, Any]]:
    groups: dict[Any, _Acc] = {}
    for row in rows:
        groups.setdefault(row[key], _Acc()).add(row, None)
    result = [{"key": k, **acc.summary()} for k, acc in groups.items()]
    result.sort(key=lambda item: -(item["avg_engagement"] or -1))
    return result


def topic_counts(conn: sqlite3.Connection, filters: Filters, now: datetime) -> list[dict[str, Any]]:
    """Filtrelenen paylaşımların yorumlarında konu dağılımı (en çok geçen önce)."""
    where, args = filters.clause(now)
    rows = conn.execute(
        "SELECT cm.topics_json, cm.label FROM comments cm JOIN posts p ON p.id=cm.post_id"  # noqa: S608 - where sabit
        " JOIN users u ON u.id=p.user_id " + where,
        args,
    ).fetchall()
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        for key in json.loads(row["topics_json"] or "[]"):
            bucket = counts.setdefault(key, {"count": 0, "negative": 0, "positive": 0})
            bucket["count"] += 1
            if row["label"] == "NEGATIVE":
                bucket["negative"] += 1
            elif row["label"] == "POSITIVE":
                bucket["positive"] += 1
    labels = topics.labels()
    result: list[dict[str, Any]] = [{"key": k, "label": labels.get(k, k), **v} for k, v in counts.items()]
    result.sort(key=lambda item: -item["count"])
    return result


def overview(conn: sqlite3.Connection, filters: Filters, now: datetime | None = None) -> dict[str, Any]:
    moment = now or now_utc()
    rows = _posts(conn, filters, moment)
    names = {
        "campaign_id": dict(conn.execute("SELECT id, name FROM campaigns").fetchall()),
        "game_id": dict(conn.execute("SELECT id, name FROM games").fetchall()),
        "community_id": dict(conn.execute("SELECT id, name FROM communities").fetchall()),
    }

    def named(key: str) -> list[dict[str, Any]]:
        items = _breakdown([r for r in rows if r[key] is not None], key)
        for item in items:
            item["name"] = names[key].get(item["key"], "—")
        return items

    totals = _Acc()
    for row in rows:
        totals.add(row, None)
    return {
        "topics": topic_counts(conn, filters, moment),
        "topic_labels": topics.labels(),
        "filters": filters.__dict__,
        "generated_at": to_iso(moment),
        "totals": totals.summary(),
        "weights": weights(conn),
        "leaderboard": leaderboard(conn, filters, moment),
        "platforms": _breakdown(rows, "platform"),
        "content_types": _breakdown(rows, "content_type"),
        "campaigns": named("campaign_id"),
        "games": named("game_id"),
        "communities": named("community_id")[:15],
    }
