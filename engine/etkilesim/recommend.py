"""Topluluk öneri skoru ve "Önerilme nedeni" (master prompt §31–32).

    skor = ilgi·0.30 + aktivite·0.20 + geçmiş etkileşim·0.20 + tazelik·0.10 + dil·0.10 + kitle·0.10
           − spam cezası − yakın zamanda kullanım cezası − ilgisizlik cezası (hiç eşleşme yoksa)

Oyun veya kampanya seçilirse ilgi ve kitle uyumu onun tür/anahtar kelimelerine göre hesaplanır
("hangi topluluğa hangi oyun"). Bilinmeyen bileşenler nötr (0.5) sayılır ve gerekçede belirtilir.
Bu yalnızca öneridir; hiçbir topluluğa otomatik paylaşım yapılmaz.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from typing import Any

from . import settings
from .clock import days_between, from_iso, now_utc
from .radar import tokens

WEIGHTS = {
    "relevance": 0.30,
    "activity": 0.20,
    "engagement_history": 0.20,
    "freshness": 0.10,
    "language_match": 0.10,
    "audience_match": 0.10,
}
SPAM_PENALTY = 25.0
IRRELEVANCE_PENALTY = 20.0  # hiç konu/kitle eşleşmesi yoksa: büyüklük tek başına öne geçirmesin
NEUTRAL = 0.5
LANG_NAMES = {"tr": "Türkçe", "en": "İngilizce", "de": "Almanca", "es": "İspanyolca", "fr": "Fransızca"}


def _overlap(wanted: set[str], haystack: set[str]) -> float:
    return len(wanted & haystack) / len(wanted) if wanted else 0.0


def _target(conn: sqlite3.Connection, game_id: int | None, campaign_id: int | None) -> dict[str, Any]:
    keywords: list[str] = []
    genres: list[str] = []
    languages: list[str] = []
    label = None
    if campaign_id is not None:
        row = conn.execute(
            "SELECT name, game_id, keywords_json FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        if row is not None:
            label = row["name"]
            keywords += json.loads(row["keywords_json"])
            game_id = game_id or row["game_id"]
    if game_id is not None:
        row = conn.execute(
            "SELECT name, genres_json, keywords_json, languages_json FROM games WHERE id=?", (game_id,)
        ).fetchone()
        if row is not None:
            label = label or row["name"]
            genres = json.loads(row["genres_json"])
            keywords += json.loads(row["keywords_json"]) + genres
            languages = [lang.lower() for lang in json.loads(row["languages_json"])]
    if not keywords:
        keywords = list(settings.get(conn, "discovery_keywords"))
    if not languages:
        languages = [str(lang).lower() for lang in settings.get(conn, "target_languages")]
    return {"label": label, "keywords": keywords, "genres": genres, "languages": [x for x in languages if x]}


def recommendations(
    conn: sqlite3.Connection,
    game_id: int | None = None,
    campaign_id: int | None = None,
    team_id: int | None = None,
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    moment = now or now_utc()
    target = _target(conn, game_id, campaign_id)
    wanted = set().union(*(tokens(k) for k in target["keywords"])) if target["keywords"] else set()
    genre_tokens = set().union(*(tokens(g) for g in target["genres"])) if target["genres"] else set()
    avoid = int(settings.get(conn, "community_avoid_days", team_id))
    recent = int(settings.get(conn, "community_recent_days", team_id))
    caution = int(settings.get(conn, "community_caution_days", team_id))

    rows = conn.execute(
        "SELECT c.*, (SELECT MAX(l.posted_at) FROM community_logs l LEFT JOIN posts p ON p.id=l.post_id"
        "  WHERE l.community_id=c.id AND (p.id IS NULL OR p.archived_at IS NULL)) AS last_used,"
        " (SELECT COUNT(*) FROM community_logs l LEFT JOIN posts p ON p.id=l.post_id"
        "  WHERE l.community_id=c.id AND (p.id IS NULL OR p.archived_at IS NULL)) AS previous_posts,"
        " (SELECT AVG(COALESCE(p.current_likes,0)+COALESCE(p.comments_count,0)+COALESCE(p.shares_count,0))"
        "  FROM posts p WHERE p.community_id=c.id AND p.archived_at IS NULL AND (p.current_likes IS NOT NULL"
        "  OR p.comments_count IS NOT NULL OR p.shares_count IS NOT NULL)) AS avg_engagement"
        " FROM communities c WHERE c.status <> 'blocked'"
    ).fetchall()
    best_history = max((float(r["avg_engagement"] or 0) for r in rows), default=0.0)

    scored: list[dict[str, Any]] = []
    for row in rows:
        text_tokens = tokens(f"{row['name']} {row['description'] or ''} {row['category'] or ''}")
        relevance = _overlap(wanted, text_tokens)
        # Üye sayısı bilinmiyorsa aktivite de bilinmiyor (0 değil).
        activity = None if row["member_count"] is None else float(row["activity_score"] or 0)
        avg_eng = float(row["avg_engagement"]) if row["avg_engagement"] is not None else None
        history = (
            None
            if avg_eng is None or best_history <= 0
            else min(1.0, math.log1p(avg_eng) / math.log1p(best_history))
        )
        days = days_between(from_iso(row["last_used"]), moment) if row["last_used"] else None
        freshness = 1.0 if days is None else (0.0 if days <= avoid else min(1.0, days / max(1, 2 * caution)))
        lang = (row["language"] or "").lower() or None
        language_match = (
            None if lang is None or not target["languages"] else (1.0 if lang in target["languages"] else 0.0)
        )
        audience = _overlap(genre_tokens, text_tokens) if genre_tokens else None
        components = {
            "relevance": relevance,
            "activity": activity,
            "engagement_history": history,
            "freshness": freshness,
            "language_match": language_match,
            "audience_match": audience,
        }
        base = 100 * sum(WEIGHTS[k] * (NEUTRAL if v is None else v) for k, v in components.items())
        spam = float(row["spam_risk"] or 0)
        if days is None or days > caution:
            recency_penalty = 0.0
        else:
            recency_penalty = 30.0 if days <= avoid else 15.0 if days <= recent else 5.0
        irrelevance_penalty = IRRELEVANCE_PENALTY if relevance == 0 and not audience else 0.0
        score = max(0.0, min(100.0, base - spam * SPAM_PENALTY - recency_penalty - irrelevance_penalty))
        scored.append(
            {
                "id": row["id"],
                "name": row["name"],
                "platform": row["platform"],
                "url": row["url"],
                "member_count": row["member_count"],
                "language": lang,
                "status": row["status"],
                "favorite": row["favorite"],
                "last_used": row["last_used"],
                "previous_posts": row["previous_posts"],
                "days_since_last_post": days,
                "score": round(score, 1),
                "components": {k: (None if v is None else round(v, 3)) for k, v in components.items()},
                "penalties": {
                    "spam": round(spam * SPAM_PENALTY, 1),
                    "recency": recency_penalty,
                    "irrelevance": irrelevance_penalty,
                },
                "reasons": _reasons(components, row, days, lang, target, avoid, recent, spam),
            }
        )
    scored.sort(key=lambda item: (-item["favorite"], -item["score"], item["name"].casefold()))
    return {"target": target["label"], "keywords": target["keywords"], "items": scored[:limit]}


def _reasons(
    c: dict[str, float | None],
    row: sqlite3.Row,
    days: int | None,
    lang: str | None,
    target: dict[str, Any],
    avoid: int,
    recent: int,
    spam: float,
) -> list[dict[str, str]]:
    """Türkçe gerekçe maddeleri; tone: 'plus' (lehine) / 'minus' (aleyhine) / 'info'."""
    items: list[dict[str, str]] = []

    def add(tone: str, text: str) -> None:
        items.append({"tone": tone, "text": text})

    audience = c["audience_match"]
    if audience is not None and audience >= 0.5 and target["genres"]:
        add("plus", f"{', '.join(target['genres'][:2])} oyuncu kitlesiyle yüksek eşleşme")
    if (c["relevance"] or 0) >= 0.5:
        percent = round((c["relevance"] or 0) * 100)
        add("plus", f"{target['label'] or 'Anahtar kelimeler'} ile güçlü konu uyumu (%{percent})")
    elif (c["relevance"] or 0) == 0:
        add("minus", "Hedef anahtar kelimelerle eşleşme yok")
    if c["activity"] is not None and c["activity"] >= 0.6 and row["member_count"]:
        add("plus", f"Büyük ve aktif topluluk ({row['member_count']:,} üye)".replace(",", "."))
    elif c["activity"] is None:
        add("info", "Üye sayısı bilinmiyor")
    previous = int(row["previous_posts"] or 0)
    if previous == 0:
        add("plus", "Daha önce hiç paylaşım yapılmamış")
    elif previous <= 2:
        add("info", f"Daha önce yalnızca {previous} paylaşım yapılmış")
    if days is not None:
        if days <= avoid:
            add("minus", f"Son paylaşım {days} gün önce — şimdi kaçının")
        elif days <= recent:
            add("minus", f"Yakın zamanda kullanıldı ({days} gün önce)")
        else:
            add("plus", f"Son paylaşımın üzerinden {days} gün geçmiş")
    if c["engagement_history"] is not None and c["engagement_history"] >= 0.6:
        add("plus", "Ekibin önceki paylaşımları burada iyi etkileşim aldı")
    if c["language_match"] == 1.0 and lang:
        add("plus", f"{LANG_NAMES.get(lang, lang)} hedef kitlenizle uyumlu")
    elif c["language_match"] == 0.0 and lang:
        add("minus", f"Topluluk dili ({LANG_NAMES.get(lang, lang)}) hedef dille uyuşmuyor")
    if spam >= 0.5:
        add("minus", "Spam/tanıtım riski yüksek")
    return items
