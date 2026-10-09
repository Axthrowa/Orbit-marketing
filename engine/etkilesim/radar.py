"""Topluluk Radarı: anahtar kelimelerden açık topluluk keşfi. Yalnızca KEŞİF/ÖNERİ yapar.

Hiçbir topluluğa otomatik paylaşım yapılmaz. Kaynak: Reddit'in herkese açık arama JSON'u
(anahtarsız). Erişim reddedilirse (429/403) sessizce 'kaynak kullanılamıyor' bildirilir;
topluluklar elle de eklenebilir.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from . import community
from .clock import now_utc, to_iso
from .db import audit, transaction
from .errors import ProviderUnavailable
from .httpclient import FetchResult, fetch
from .sentiment import tr_lower

FetchFn = Callable[[str], FetchResult]
MAX_PER_QUERY = 25
MIN_RELEVANCE = 0.15
_STOP = {"ve", "ile", "için", "oyunları", "oyunlari", "games", "game", "the", "a", "of"}


def build_queries(keyword: str) -> list[str]:
    """'FPS' → fps community, fps gaming forum, ... (arama varyasyonları)."""
    base = " ".join(keyword.split())
    if not base:
        return []
    variants = [base, f"{base} community", f"{base} gaming", f"{base} forum", f"{base} oyuncu"]
    unique: list[str] = []
    for variant in variants:
        if variant.lower() not in {u.lower() for u in unique}:
            unique.append(variant)
    return unique


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\wğüşıöç]+", tr_lower(text)) if len(t) > 2 and t not in _STOP}


def relevance(keywords: list[str], name: str, description: str) -> float:
    wanted = set().union(*(tokens(k) for k in keywords)) if keywords else set()
    if not wanted:
        return 0.0
    haystack = tokens(name) | tokens(description)
    return len(wanted & haystack) / len(wanted)


def activity(members: int | None) -> float:
    """0..1: üye sayısının logaritmik ölçeği (1M+ → 1). Bilinmiyorsa 0."""
    if not members or members <= 0:
        return 0.0
    return min(1.0, math.log10(members) / 6)


def score(rel: float, act: float) -> float:
    return round(100 * (0.7 * rel + 0.3 * act), 1)


@dataclass
class Candidate:
    name: str
    platform: str
    url: str
    members: int | None
    description: str
    relevance: float
    activity: float
    reason: str
    language: str | None = None
    spam_risk: float = 0.1


@dataclass
class DiscoveryReport:
    found: int = 0
    added: int = 0
    queries: int = 0
    unavailable: list[str] = field(default_factory=list)


def _parse_reddit(payload: Any, keywords: list[str]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for child in payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []:
        data = child.get("data", {}) if isinstance(child, dict) else {}
        if data.get("over18") or data.get("subreddit_type") not in (None, "public"):
            continue
        name = str(data.get("display_name_prefixed") or "")
        path = str(data.get("url") or "")
        if not name or not path.startswith("/r/"):
            continue
        members = data.get("subscribers")
        members = int(members) if isinstance(members, int) and members >= 0 else None
        description = str(data.get("public_description") or data.get("title") or "")
        rel, act = relevance(keywords, name, description), activity(members)
        if rel < MIN_RELEVANCE:
            continue
        lang = data.get("lang")
        language = lang.lower()[:5] if isinstance(lang, str) and lang else None
        reason = f"Anahtar kelime eşleşmesi %{round(rel * 100)}" + (
            f", {members:,} üye".replace(",", ".") if members else ", üye sayısı bilinmiyor"
        )
        candidates.append(
            Candidate(
                name,
                "Reddit",
                f"https://www.reddit.com{path.rstrip('/')}/",
                members,
                description[:300],
                rel,
                act,
                reason,
                language,
                spam_risk(name, description, members),
            )
        )
    return candidates


_SPAM_HINTS = re.compile(
    r"giveaway|free\s|promo|promote your|self[- ]?promo|sub4sub|follow4follow|çekiliş|reklam yap",
    re.IGNORECASE,
)


def spam_risk(name: str, description: str, members: int | None) -> float:
    """0..1 kaba spam/düşük kalite riski: tanıtım kalıpları ve çok küçük/tanımsız topluluk."""
    risk = 0.1
    if _SPAM_HINTS.search(f"{name} {description}"):
        risk += 0.5
    if members is not None and members < 100:
        risk += 0.2
    if not description.strip():
        risk += 0.1
    return round(min(1.0, risk), 2)


def discover(
    conn: sqlite3.Connection,
    keywords: list[str],
    now: datetime | None = None,
    fetch_fn: FetchFn = fetch,
    actor: str = "system",
) -> DiscoveryReport:
    moment = now or now_utc()
    report = DiscoveryReport()
    best: dict[str, Candidate] = {}
    for keyword in keywords:
        for query in build_queries(keyword)[:3]:
            report.queries += 1
            url = (
                "https://www.reddit.com/subreddits/search.json?"
                f"q={quote_plus(query)}&limit={MAX_PER_QUERY}&raw_json=1"
            )
            try:
                response = fetch_fn(url)
            except ProviderUnavailable as exc:
                report.unavailable.append(exc.message)
                continue
            if response.status != 200:
                report.unavailable.append(f"Reddit araması kullanılamıyor (HTTP {response.status})")
                break
            try:
                payload = json.loads(response.text)
            except ValueError:
                report.unavailable.append("Reddit yanıtı okunamadı")
                continue
            for cand in _parse_reddit(payload, keywords):
                current = best.get(cand.url)
                if current is None or cand.relevance > current.relevance:
                    best[cand.url] = cand
    report.found = len(best)
    with transaction(conn):
        for cand in best.values():
            existing = conn.execute("SELECT id FROM communities WHERE url=?", (cand.url,)).fetchone()
            values = (score(cand.relevance, cand.activity), cand.activity, cand.reason, cand.members)
            if existing is None:
                created = conn.execute(
                    "INSERT INTO communities(name,name_key,platform,url,member_count,status,"
                    "relevance_score,activity_score,reason,discovered_at,description,language,spam_risk,"
                    "last_scanned_at) VALUES (?,?,?,?,?,'discovered',?,?,?,?,?,?,?,?)",
                    (
                        cand.name,
                        community.name_key(cand.name),
                        cand.platform,
                        cand.url,
                        cand.members,
                        values[0],
                        values[1],
                        cand.reason,
                        to_iso(moment),
                        cand.description,
                        cand.language,
                        cand.spam_risk,
                        to_iso(moment),
                    ),
                )
                report.added += 1
                audit(
                    conn,
                    actor,
                    "community.discovered",
                    "community",
                    created.lastrowid,
                    {"name": cand.name},
                    moment,
                )
            else:  # kullanıcı durumu (onay/engel/favori) korunur, yalnızca skorlar güncellenir
                conn.execute(
                    "UPDATE communities SET relevance_score=?, activity_score=?, reason=?,"
                    " member_count=COALESCE(?, member_count), description=?, language=COALESCE(?, language),"
                    " spam_risk=?, last_scanned_at=? WHERE id=?",
                    (
                        *values,
                        cand.description,
                        cand.language,
                        cand.spam_risk,
                        to_iso(moment),
                        existing["id"],
                    ),
                )
    return report


def ranked(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Radar listesi: skor + son kullanım bilgisi (engelliler hariç)."""
    rows = conn.execute(
        "SELECT c.*, (SELECT MAX(l.posted_at) FROM community_logs l LEFT JOIN posts p ON p.id=l.post_id"
        " WHERE l.community_id=c.id AND (p.id IS NULL OR p.archived_at IS NULL)) AS last_used,"
        " (SELECT COUNT(*) FROM community_logs l LEFT JOIN posts p ON p.id=l.post_id"
        " WHERE l.community_id=c.id AND (p.id IS NULL OR p.archived_at IS NULL)) AS previous_posts"
        " FROM communities c WHERE c.status <> 'blocked'"
        " ORDER BY c.favorite DESC, COALESCE(c.relevance_score, 0) DESC, c.name_key LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
