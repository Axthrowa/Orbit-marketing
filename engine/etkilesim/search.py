"""Genel arama (master prompt §67): kişiler, paylaşımlar, topluluklar, kampanyalar, oyunlar.

Yerel veri boyutu için LIKE yeterlidir; joker karakterler kaçışlanır. Kullanıcı görünümünde
(`user_id`) paylaşımlar yalnızca o kişiye aittir ve kişi listesi döndürülmez.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .errors import ValidationFailed

PER_GROUP = 8

_POSTS = (
    "SELECT p.id, p.platform, p.url, u.name AS user_name, c.name AS community_name, p.note"
    " FROM posts p JOIN users u ON u.id=p.user_id LEFT JOIN communities c ON c.id=p.community_id"
    " WHERE p.archived_at IS NULL AND (p.url LIKE :q ESCAPE '\\' OR p.note LIKE :q ESCAPE '\\'"
    " OR p.preview_text LIKE :q ESCAPE '\\' OR c.name LIKE :q ESCAPE '\\' OR u.name LIKE :q ESCAPE '\\')"
    " AND (:user_id IS NULL OR p.user_id = :user_id) ORDER BY p.posted_at DESC LIMIT :limit"
)
_PEOPLE = (
    "SELECT u.id, u.name, t.name AS team_name FROM users u LEFT JOIN teams t ON t.id=u.team_id"
    " WHERE u.name LIKE :q ESCAPE '\\' ORDER BY u.name LIMIT :limit"
)
_COMMUNITIES = (
    "SELECT id, name, platform FROM communities WHERE status <> 'blocked'"
    " AND (name LIKE :q ESCAPE '\\' OR description LIKE :q ESCAPE '\\') ORDER BY name_key LIMIT :limit"
)
_CAMPAIGNS = (
    "SELECT id, name, status FROM campaigns WHERE name LIKE :q ESCAPE '\\' OR description LIKE :q ESCAPE '\\'"
    " ORDER BY name LIMIT :limit"
)
_GAMES = "SELECT id, name, status FROM games WHERE name LIKE :q ESCAPE '\\' ORDER BY name LIMIT :limit"


def _like(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(
    conn: sqlite3.Connection, query: str, user_id: int | None = None
) -> dict[str, list[dict[str, Any]]]:
    text = " ".join(query.split())
    if len(text) < 2:
        raise ValidationFailed("Arama için en az 2 karakter yazın")
    if len(text) > 100:
        raise ValidationFailed("Arama en çok 100 karakter olabilir")
    params = {"q": _like(text), "user_id": user_id, "limit": PER_GROUP}

    def run(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    return {
        "posts": run(_POSTS),
        "people": run(_PEOPLE) if user_id is None else [],
        "communities": run(_COMMUNITIES),
        "campaigns": run(_CAMPAIGNS),
        "games": run(_GAMES),
    }
