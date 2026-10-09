"""Gönderi kaydı, ölçüm kaydı (zaman serisi), yorum + duygu işleme."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from . import analytics, catalog, community, settings, strikes, topics
from .clock import from_iso, now_utc, to_iso
from .db import audit, transaction
from .errors import NotFound, PermissionDenied, ValidationFailed
from .models import CollectResult, Metrics
from .platforms import canonicalize, detect_platform, extract_post_id
from .security import Resolver, validate_public_url
from .sentiment import SentimentEngine, aggregate_labels, mask_for_storage, normalize, text_hash

MAX_NOTE = 500
CONTENT_TYPES = ("post", "video", "image", "poll", "event", "other")
AUTH_RETRY_HOURS = 24
OLD_POST_DAYS = 30
OLD_POST_FACTOR = 4


@dataclass(frozen=True)
class AddPostResult:
    post_id: int
    created: bool
    platform: str


def _parse_posted_at(value: str | None, now: datetime) -> datetime:
    if not value:
        return now
    try:
        if len(value) == 10:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time(), UTC)
            parsed = parsed.replace(hour=12)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValidationFailed("Paylaşım tarihi geçersiz (YYYY-AA-GG)") from exc
    parsed = parsed.astimezone(UTC).replace(microsecond=0)
    if parsed > now + timedelta(minutes=5):
        raise ValidationFailed("Paylaşım tarihi gelecekte olamaz")
    return parsed


def add_post(
    conn: sqlite3.Connection,
    user_id: int,
    url: str,
    community_name: str | None = None,
    community_url: str | None = None,
    preview_text: str | None = None,
    note: str | None = None,
    posted_at: str | None = None,
    actor: str = "user",
    now: datetime | None = None,
    resolver: Resolver | None = None,
    game_id: int | None = None,
    campaign_id: int | None = None,
    content_type: str = "post",
) -> AddPostResult:
    moment = now or now_utc()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        raise NotFound("Kullanıcı bulunamadı")
    if user["status"] == "inactive":
        raise ValidationFailed("Pasif kullanıcı için paylaşım eklenemez")
    if user["role"] == "viewer":
        raise PermissionDenied("İzleyici (viewer) rolündeki hesaplar paylaşım ekleyemez")
    if content_type not in CONTENT_TYPES:
        raise ValidationFailed("Geçersiz içerik türü")
    safe_url = validate_public_url(url, resolver)
    safe_community_url = validate_public_url(community_url, resolver) if community_url else None
    platform = detect_platform(safe_url)
    canonical = canonicalize(safe_url, platform)
    posted = _parse_posted_at(posted_at, moment)
    clean_note = (note or "").strip()[:MAX_NOTE] or None
    with transaction(conn):
        existing = conn.execute(
            "SELECT id FROM posts WHERE user_id=? AND canonical_url=?", (user_id, canonical)
        ).fetchone()
        if existing is not None:
            return AddPostResult(int(existing["id"]), False, platform)
        game_id, campaign_id = catalog.resolve_for_post(conn, game_id, campaign_id)
        community_id = (
            community.get_or_create(
                conn,
                community_name,
                platform if community_name else "Other",
                safe_community_url,
                actor,
                moment,
            )
            if community_name and community_name.strip()
            else None
        )
        created = conn.execute(
            "INSERT INTO posts(user_id,community_id,platform,url,canonical_url,platform_post_id,"
            "note,preview_text,posted_at,created_at,updated_at,game_id,campaign_id,content_type)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                community_id,
                platform,
                safe_url,
                canonical,
                extract_post_id(safe_url, platform),
                clean_note,
                community.preview(preview_text) or None,
                to_iso(posted),
                to_iso(moment),
                to_iso(moment),
                game_id,
                campaign_id,
                content_type,
            ),
        )
        post_id = int(created.lastrowid or 0)
        if community_id is not None:
            community.log_post(conn, community_id, user_id, post_id, safe_url, preview_text, posted)
        _register_activity(conn, user, posted, moment, actor)
        audit(conn, actor, "post.create", "post", post_id, {"platform": platform}, moment)
    return AddPostResult(post_id, True, platform)


def _register_activity(
    conn: sqlite3.Connection, user: sqlite3.Row, posted: datetime, now: datetime, actor: str
) -> None:
    previous = from_iso(user["last_post_at"]) if user["last_post_at"] else None
    latest = posted if previous is None or posted > previous else previous
    conn.execute("UPDATE users SET last_post_at=? WHERE id=?", (to_iso(latest), user["id"]))
    threshold = timedelta(days=int(settings.get(conn, "inactivity_days", user["team_id"])))
    # Yalnızca hareketsizliği gerçekten bitiren (güncel) paylaşım uyarıları sıfırlar.
    if now - latest < threshold:
        strikes.reset_user(conn, int(user["id"]), now, actor)


ADAPTIVE_STEPS_HOURS = (1, 3, 6, 12, 24)  # paylaşımdan sonraki ölçüm basamakları (master prompt §21)


def next_adaptive_due(posted: datetime, last_attempt: datetime) -> datetime:
    """Uyarlanabilir takvim: +1/+3/+6/+12/+24 sa, sonra günlük.

    7 günden eski paylaşım 48 saatte, 30 günden eski paylaşım haftada bir ölçülür.
    """
    for hours in ADAPTIVE_STEPS_HOURS:
        step = posted + timedelta(hours=hours)
        if last_attempt < step:
            return step
    age = last_attempt - posted
    if age > timedelta(days=OLD_POST_DAYS):
        return last_attempt + timedelta(days=7)
    if age > timedelta(days=7):
        return last_attempt + timedelta(hours=48)
    return last_attempt + timedelta(hours=24)


def due_posts(conn: sqlite3.Connection, now: datetime, limit: int = 50) -> list[sqlite3.Row]:
    base_interval = timedelta(hours=int(settings.get(conn, "metrics_interval_hours")))
    adaptive = settings.get(conn, "metrics_schedule") == "adaptive"
    rows = conn.execute(
        "SELECT p.*, u.team_id FROM posts p JOIN users u ON u.id=p.user_id WHERE p.archived_at IS NULL"
        " ORDER BY p.last_attempt_at IS NOT NULL, p.last_attempt_at, p.id"
    ).fetchall()
    due: list[sqlite3.Row] = []
    for row in rows:
        if row["last_attempt_at"] is None:
            due.append(row)
        else:
            last = from_iso(row["last_attempt_at"])
            if adaptive:
                next_at = next_adaptive_due(from_iso(row["posted_at"]), last)
                if row["data_status"] == "AUTHORIZATION_REQUIRED":
                    next_at = max(next_at, last + timedelta(hours=AUTH_RETRY_HOURS))
                if now >= next_at:
                    due.append(row)
            else:
                interval = base_interval
                if row["data_status"] == "AUTHORIZATION_REQUIRED":
                    interval = max(interval, timedelta(hours=AUTH_RETRY_HOURS))
                if now - from_iso(row["posted_at"]) > timedelta(days=OLD_POST_DAYS):
                    interval *= OLD_POST_FACTOR
                if now - last >= interval:
                    due.append(row)
        if len(due) >= limit:
            break
    return due


def record_collect(
    conn: sqlite3.Connection,
    post_id: int,
    result: CollectResult,
    engine: SentimentEngine,
    now: datetime | None = None,
    comment_limit: int | None = None,
) -> None:
    """Ölçüm sonucunu işler. Hata durumunda gönderi ve eski değerler asla silinmez."""
    moment = now or now_utc()
    post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if post is None:
        raise NotFound("Gönderi bulunamadı")
    limit = comment_limit or int(settings.get(conn, "comment_limit"))
    with transaction(conn):
        if result.status != "OK":
            # Elle girilmiş veri varsa etiket 'MANUAL' kalır; otomatik hata yalnızca not edilir.
            status = "MANUAL" if post["data_status"] == "MANUAL" else result.status
            conn.execute(
                "UPDATE posts SET data_status=?, last_error=?, last_attempt_at=?, updated_at=? WHERE id=?",
                (status, (result.error or "")[:300] or None, to_iso(moment), to_iso(moment), post_id),
            )
            return
        _store_metrics(conn, post, result.metrics, result.source, moment)
        if result.preview_text and not post["preview_text"]:
            preview = community.preview(result.preview_text)
            conn.execute("UPDATE posts SET preview_text=? WHERE id=?", (preview, post_id))
            conn.execute(
                "UPDATE community_logs SET post_preview_text=? WHERE post_id=? AND post_preview_text=''",
                (preview, post_id),
            )
        if result.comment_texts:
            _store_comments(conn, post_id, result.comment_texts[:limit], engine, moment)
        conn.execute(
            "UPDATE posts SET data_status='OK', last_error=NULL, last_metrics_at=?,"
            " last_attempt_at=?, updated_at=? WHERE id=?",
            (to_iso(moment), to_iso(moment), to_iso(moment), post_id),
        )


def _store_metrics(
    conn: sqlite3.Connection, post: sqlite3.Row, metrics: Metrics, source: str, moment: datetime
) -> None:
    # None = bilinmiyor: mevcut değeri silmez.
    likes = metrics.likes if metrics.likes is not None else post["current_likes"]
    comments = metrics.comments if metrics.comments is not None else post["comments_count"]
    shares = metrics.shares if metrics.shares is not None else post["shares_count"]
    views = metrics.views if metrics.views is not None else post["views_count"]
    initial = post["initial_likes"] if post["initial_likes"] is not None else metrics.likes
    conn.execute(
        "UPDATE posts SET current_likes=?, comments_count=?, shares_count=?, views_count=?,"
        " initial_likes=? WHERE id=?",
        (likes, comments, shares, views, initial, post["id"]),
    )
    conn.execute(
        "INSERT OR IGNORE INTO post_metric_snapshots(post_id,likes,comments,shares,views,source,"
        "captured_at) VALUES (?,?,?,?,?,?,?)",
        (post["id"], metrics.likes, metrics.comments, metrics.shares, metrics.views, source, to_iso(moment)),
    )


def _store_comments(
    conn: sqlite3.Connection,
    post_id: int,
    texts: list[str],
    engine: SentimentEngine,
    moment: datetime,
) -> int:
    """Yalnızca yeni yorumlar analiz edilir (aynı yorum yeniden analiz edilmez)."""
    fresh: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in texts:
        if not normalize(raw):
            continue
        digest = text_hash(raw)
        if digest in seen:
            continue
        seen.add(digest)
        known = conn.execute(
            "SELECT 1 FROM comments WHERE post_id=? AND text_hash=?", (post_id, digest)
        ).fetchone()
        if known is None:
            fresh.append((digest, raw))
    if fresh:
        results = engine.analyze([raw for _, raw in fresh])
        for (digest, raw), res in zip(fresh, results, strict=True):
            conn.execute(
                "INSERT OR IGNORE INTO comments(post_id,text_hash,text,language,label,positive,"
                "neutral,negative,engine,collected_at,topics_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    post_id,
                    digest,
                    mask_for_storage(raw),
                    res.language,
                    res.label,
                    res.positive,
                    res.neutral,
                    res.negative,
                    engine.name,
                    to_iso(moment),
                    json.dumps(topics.detect(raw, res.label)),
                ),
            )
    recompute_sentiment(conn, post_id)
    return len(fresh)


def recompute_sentiment(conn: sqlite3.Connection, post_id: int) -> None:
    rows = conn.execute("SELECT label FROM comments WHERE post_id=?", (post_id,)).fetchall()
    ratios = aggregate_labels([str(r["label"]) for r in rows])
    if ratios is None:
        conn.execute(
            "UPDATE posts SET positive_sentiment_ratio=NULL, negative_sentiment_ratio=NULL,"
            " neutral_sentiment_ratio=NULL, sentiment_sample=0 WHERE id=?",
            (post_id,),
        )
        return
    conn.execute(
        "UPDATE posts SET positive_sentiment_ratio=?, negative_sentiment_ratio=?,"
        " neutral_sentiment_ratio=?, sentiment_sample=? WHERE id=?",
        (ratios.positive, ratios.negative, ratios.neutral, ratios.sample, post_id),
    )


def _count(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValidationFailed(f"{name}: tam sayı bekleniyor")
    try:
        number = int(value)
    except ValueError as exc:
        raise ValidationFailed(f"{name}: tam sayı bekleniyor") from exc
    if not 0 <= number <= 10**12:
        raise ValidationFailed(f"{name}: geçersiz değer")
    return number


def set_archived(
    conn: sqlite3.Connection, post_id: int, archived: bool, actor: str, now: datetime | None = None
) -> None:
    """Soft delete: yanlış eklenen link arşivlenir; ölçülmez, panolarda görünmez, silinmez."""
    moment = now or now_utc()
    with transaction(conn):
        cur = conn.execute(
            "UPDATE posts SET archived_at=?, updated_at=? WHERE id=?",
            (to_iso(moment) if archived else None, to_iso(moment), post_id),
        )
        if not cur.rowcount:
            raise NotFound("Gönderi bulunamadı")
        audit(conn, actor, "post.archive" if archived else "post.restore", "post", post_id, None, moment)


def update_note(
    conn: sqlite3.Connection, post_id: int, note: str | None, actor: str, now: datetime | None = None
) -> str | None:
    """Paylaşan kişinin sayfa/topluluk hakkındaki notu (kurallar, tepkiler, dikkat edilecekler)."""
    moment = now or now_utc()
    clean = (note or "").strip()
    if len(clean) > MAX_NOTE:
        raise ValidationFailed(f"Not en çok {MAX_NOTE} karakter olabilir")
    with transaction(conn):
        cur = conn.execute(
            "UPDATE posts SET note=?, updated_at=? WHERE id=?", (clean or None, to_iso(moment), post_id)
        )
        if not cur.rowcount:
            raise NotFound("Gönderi bulunamadı")
        audit(conn, actor, "post.note", "post", post_id, {"length": len(clean)}, moment)
    return clean or None


def set_manual_metrics(
    conn: sqlite3.Connection,
    post_id: int,
    likes: Any,
    comments: Any,
    shares: Any,
    views: Any,
    actor: str,
    now: datetime | None = None,
) -> None:
    """Otomatik ölçülemeyen bağlantılar için elle giriş; 'MANUAL' etiketiyle gösterilir."""
    moment = now or now_utc()
    metrics = Metrics(
        _count(likes, "beğeni"),
        _count(comments, "yorum"),
        _count(shares, "paylaşım"),
        _count(views, "görüntülenme"),
    )
    if not metrics.known():
        raise ValidationFailed("En az bir sayaç girilmeli")
    post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if post is None:
        raise NotFound("Gönderi bulunamadı")
    with transaction(conn):
        _store_metrics(conn, post, metrics, "MANUAL", moment)
        conn.execute(
            "UPDATE posts SET data_status='MANUAL', last_error=NULL, last_metrics_at=?,"
            " updated_at=? WHERE id=?",
            (to_iso(moment), to_iso(moment), post_id),
        )
        audit(conn, actor, "post.manual_metrics", "post", post_id, None, moment)


def add_manual_comments(
    conn: sqlite3.Connection,
    post_id: int,
    texts: list[str],
    engine: SentimentEngine,
    actor: str,
    now: datetime | None = None,
) -> int:
    moment = now or now_utc()
    if conn.execute("SELECT 1 FROM posts WHERE id=?", (post_id,)).fetchone() is None:
        raise NotFound("Gönderi bulunamadı")
    cleaned = [t.strip() for t in texts if isinstance(t, str) and t.strip()][:500]
    with transaction(conn):
        added = _store_comments(conn, post_id, cleaned, engine, moment)
        audit(conn, actor, "post.manual_comments", "post", post_id, {"added": added}, moment)
    return added


def post_detail(conn: sqlite3.Connection, post_id: int) -> dict[str, Any]:
    post = conn.execute(
        "SELECT p.*, u.name AS user_name, t.name AS team_name, c.name AS community_name,"
        " g.name AS game_name, k.name AS campaign_name FROM posts p"
        " JOIN users u ON u.id=p.user_id LEFT JOIN teams t ON t.id=u.team_id"
        " LEFT JOIN communities c ON c.id=p.community_id"
        " LEFT JOIN games g ON g.id=p.game_id LEFT JOIN campaigns k ON k.id=p.campaign_id"
        " WHERE p.id=?",
        (post_id,),
    ).fetchone()
    if post is None:
        raise NotFound("Gönderi bulunamadı")
    snapshots = conn.execute(
        "SELECT likes, comments, shares, views, source, captured_at FROM post_metric_snapshots"
        " WHERE post_id=? ORDER BY captured_at",
        (post_id,),
    ).fetchall()
    comment_rows = conn.execute(
        "SELECT text, language, label, positive, negative, topics_json FROM comments WHERE post_id=?"
        " ORDER BY id DESC LIMIT 200",
        (post_id,),
    ).fetchall()
    return {
        "post": dict(post),
        "analytics": analytics.post_metrics(conn, post_id),
        "snapshots": [dict(r) for r in snapshots],
        "comments": [
            {
                **{k: v for k, v in dict(r).items() if k != "topics_json"},
                "topics": json.loads(r["topics_json"]),
            }
            for r in comment_rows
        ],
        "topic_labels": topics.labels(),
    }
