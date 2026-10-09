"""Oyunlar ve kampanyalar (master prompt §9–10): hangi oyunu / kampanyayı tanıttı sorusunun temeli."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from typing import Any

from .clock import now_utc, to_iso
from .db import audit
from .errors import NotFound, ValidationFailed
from .platforms import PLATFORMS

GAME_STATUSES = ("active", "archived")
CAMPAIGN_STATUSES = ("planned", "active", "finished", "archived")
_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def _name(value: object, what: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise ValidationFailed(f"{what} adı 1-120 karakter olmalı")
    return " ".join(value.split())


def _tags(value: object, what: str) -> str:
    if value is None:
        return "[]"
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationFailed(f"{what}: metin listesi bekleniyor")
    cleaned = list(dict.fromkeys(v.strip() for v in value if v.strip()))
    if len(cleaned) > 20 or any(len(v) > 60 for v in cleaned):
        raise ValidationFailed(f"{what}: en çok 20 öğe, her biri en çok 60 karakter")
    return json.dumps(cleaned, ensure_ascii=False)


def _url(value: object, what: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 500 or not _URL_RE.match(value.strip()):
        raise ValidationFailed(f"{what}: http(s) ile başlayan geçerli bir adres olmalı")
    return value.strip()


def _date(value: object, what: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValidationFailed(f"{what}: YYYY-AA-GG biçiminde olmalı") from exc


def _exists(conn: sqlite3.Connection, table: str, row_id: int | None, what: str) -> None:
    if (
        row_id is not None
        and conn.execute(
            f"SELECT 1 FROM {table} WHERE id=?",  # noqa: S608 - tablo adı sabit
            (row_id,),
        ).fetchone()
        is None
    ):
        raise NotFound(f"{what} bulunamadı")


def create_game(
    conn: sqlite3.Connection, data: dict[str, Any], actor: str, now: datetime | None = None
) -> int:
    name = _name(data.get("name"), "Oyun")
    if conn.execute("SELECT 1 FROM games WHERE name=?", (name,)).fetchone():
        raise ValidationFailed("Bu adda bir oyun zaten var")
    moment = now or now_utc()
    cur = conn.execute(
        "INSERT INTO games(name,genres_json,keywords_json,languages_json,website,steam_url,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            name,
            _tags(data.get("genres"), "Türler"),
            _tags(data.get("keywords"), "Anahtar kelimeler"),
            _tags(data.get("languages"), "Diller"),
            _url(data.get("website"), "Web sitesi"),
            _url(data.get("steam_url"), "Steam adresi"),
            to_iso(moment),
        ),
    )
    game_id = int(cur.lastrowid or 0)
    audit(conn, actor, "game.create", "game", game_id, {"name": name}, moment)
    return game_id


def update_game(
    conn: sqlite3.Connection, game_id: int, data: dict[str, Any], actor: str, now: datetime | None = None
) -> None:
    _exists(conn, "games", game_id, "Oyun")
    columns: dict[str, Any] = {}
    if "name" in data:
        name = _name(data["name"], "Oyun")
        if conn.execute("SELECT 1 FROM games WHERE name=? AND id<>?", (name, game_id)).fetchone():
            raise ValidationFailed("Bu adda bir oyun zaten var")
        columns["name"] = name
    for key, column, label in (
        ("genres", "genres_json", "Türler"),
        ("keywords", "keywords_json", "Anahtar kelimeler"),
        ("languages", "languages_json", "Diller"),
    ):
        if key in data:
            columns[column] = _tags(data[key], label)
    if "website" in data:
        columns["website"] = _url(data["website"], "Web sitesi")
    if "steam_url" in data:
        columns["steam_url"] = _url(data["steam_url"], "Steam adresi")
    if "status" in data:
        if data["status"] not in GAME_STATUSES:
            raise ValidationFailed("Geçersiz oyun durumu")
        columns["status"] = data["status"]
    for column, value in columns.items():  # sütun adları yukarıdaki sabit listeden gelir
        conn.execute(f"UPDATE games SET {column}=? WHERE id=?", (value, game_id))  # noqa: S608
    audit(conn, actor, "game.update", "game", game_id, {"fields": sorted(columns)}, now)


def create_campaign(
    conn: sqlite3.Connection, data: dict[str, Any], actor: str, now: datetime | None = None
) -> int:
    name = _name(data.get("name"), "Kampanya")
    if conn.execute("SELECT 1 FROM campaigns WHERE name=?", (name,)).fetchone():
        raise ValidationFailed("Bu adda bir kampanya zaten var")
    values = _campaign_values(conn, data)
    moment = now or now_utc()
    cur = conn.execute(
        "INSERT INTO campaigns(game_id,name,description,start_date,end_date,status,keywords_json,"
        "target_platforms_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            values["game_id"],
            name,
            values["description"],
            values["start_date"],
            values["end_date"],
            values["status"],
            values["keywords_json"],
            values["target_platforms_json"],
            to_iso(moment),
        ),
    )
    campaign_id = int(cur.lastrowid or 0)
    audit(conn, actor, "campaign.create", "campaign", campaign_id, {"name": name}, moment)
    return campaign_id


def _campaign_values(
    conn: sqlite3.Connection, data: dict[str, Any], current: sqlite3.Row | None = None
) -> dict[str, Any]:
    def pick(key: str, column: str | None = None) -> Any:
        if key in data:
            return data[key]
        return current[column or key] if current is not None else None

    game_id = pick("game_id")
    if game_id is not None and (isinstance(game_id, bool) or not isinstance(game_id, int)):
        raise ValidationFailed("Oyun kimliği sayı olmalı")
    _exists(conn, "games", game_id, "Oyun")
    description = pick("description")
    if description is not None and (not isinstance(description, str) or len(description) > 1000):
        raise ValidationFailed("Açıklama en çok 1000 karakter olabilir")
    start = _date(pick("start_date"), "Başlangıç tarihi")
    end = _date(pick("end_date"), "Bitiş tarihi")
    if start and end and end < start:
        raise ValidationFailed("Bitiş tarihi başlangıçtan önce olamaz")
    status = pick("status") or "active"
    if status not in CAMPAIGN_STATUSES:
        raise ValidationFailed("Geçersiz kampanya durumu")
    platforms = data.get("target_platforms")
    if platforms is not None and (
        not isinstance(platforms, list) or any(p not in PLATFORMS for p in platforms)
    ):
        raise ValidationFailed("Hedef platformlar geçersiz")
    return {
        "game_id": game_id,
        "description": (description or "").strip() or None,
        "start_date": start,
        "end_date": end,
        "status": status,
        "keywords_json": _tags(data["keywords"], "Anahtar kelimeler")
        if "keywords" in data
        else (current["keywords_json"] if current is not None else "[]"),
        "target_platforms_json": json.dumps(platforms)
        if platforms is not None
        else (current["target_platforms_json"] if current is not None else "[]"),
    }


def update_campaign(
    conn: sqlite3.Connection, campaign_id: int, data: dict[str, Any], actor: str, now: datetime | None = None
) -> None:
    current = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if current is None:
        raise NotFound("Kampanya bulunamadı")
    name = current["name"]
    if "name" in data:
        name = _name(data["name"], "Kampanya")
        if conn.execute("SELECT 1 FROM campaigns WHERE name=? AND id<>?", (name, campaign_id)).fetchone():
            raise ValidationFailed("Bu adda bir kampanya zaten var")
    values = _campaign_values(conn, data, current)
    conn.execute(
        "UPDATE campaigns SET name=?, game_id=?, description=?, start_date=?, end_date=?, status=?,"
        " keywords_json=?, target_platforms_json=? WHERE id=?",
        (
            name,
            values["game_id"],
            values["description"],
            values["start_date"],
            values["end_date"],
            values["status"],
            values["keywords_json"],
            values["target_platforms_json"],
            campaign_id,
        ),
    )
    audit(conn, actor, "campaign.update", "campaign", campaign_id, {"fields": sorted(data)}, now)


def list_games(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT g.*, COUNT(p.id) AS posts FROM games g LEFT JOIN posts p ON p.game_id=g.id"
        " AND p.archived_at IS NULL GROUP BY g.id ORDER BY g.status, g.name COLLATE NOCASE"
    ).fetchall()
    return [_decode(dict(r), ("genres_json", "keywords_json", "languages_json")) for r in rows]


def list_campaigns(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT c.*, g.name AS game_name, COUNT(p.id) AS posts, SUM(p.current_likes) AS likes,"
        " SUM(p.comments_count) AS comments, SUM(p.shares_count) AS shares, SUM(p.views_count) AS views"
        " FROM campaigns c LEFT JOIN games g ON g.id=c.game_id"
        " LEFT JOIN posts p ON p.campaign_id=c.id AND p.archived_at IS NULL"
        " GROUP BY c.id ORDER BY CASE c.status WHEN 'active' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END,"
        " c.name COLLATE NOCASE"
    ).fetchall()
    result = []
    for row in rows:
        item = _decode(dict(row), ("keywords_json", "target_platforms_json"))
        parts = [item["likes"], item["comments"], item["shares"]]
        item["engagement"] = None if all(v is None for v in parts) else sum(v or 0 for v in parts)
        result.append(item)
    return result


def _decode(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        item[key.removesuffix("_json")] = json.loads(item.pop(key) or "[]")
    return item


def resolve_for_post(
    conn: sqlite3.Connection, game_id: int | None, campaign_id: int | None
) -> tuple[int | None, int | None]:
    """Kampanya verilip oyun verilmezse oyun kampanyadan alınır; ikisi çelişirse hata."""
    if campaign_id is not None:
        row = conn.execute("SELECT game_id, status FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if row is None:
            raise NotFound("Kampanya bulunamadı")
        if row["status"] == "archived":
            raise ValidationFailed("Arşivlenmiş kampanyaya paylaşım eklenemez")
        if game_id is None:
            game_id = row["game_id"]
        elif row["game_id"] is not None and row["game_id"] != game_id:
            raise ValidationFailed("Seçilen kampanya başka bir oyuna ait")
    _exists(conn, "games", game_id, "Oyun")
    return game_id, campaign_id
