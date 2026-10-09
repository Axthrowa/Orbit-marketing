"""Ekip ve kullanıcı yönetimi (çok ekipli yapı)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any

from .clock import now_utc, to_iso
from .db import audit
from .errors import NotFound, ValidationFailed

ROLES = ("admin", "manager", "member", "viewer")
_CHAT_ID_RE = re.compile(r"^-?\d{3,20}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email(value: object) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if len(text) > 254 or not _EMAIL_RE.match(text):
        raise ValidationFailed("E-posta adresi geçersiz")
    return text.lower()


def _clean_name(name: object, what: str) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValidationFailed(f"{what} adı 1-80 karakter olmalı")
    return " ".join(name.split())


def _clean_chat_id(value: object) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not _CHAT_ID_RE.match(text):
        raise ValidationFailed("Telegram kimliği sayısal olmalı (grup kimlikleri '-' ile başlar)")
    return text


def create_team(
    conn: sqlite3.Connection,
    name: object,
    chat_id: object,
    actor: str,
    now: datetime | None = None,
) -> int:
    clean = _clean_name(name, "Ekip")
    cur = conn.execute("SELECT 1 FROM teams WHERE name=?", (clean,)).fetchone()
    if cur is not None:
        raise ValidationFailed("Bu adda bir ekip zaten var")
    moment = now or now_utc()
    created = conn.execute(
        "INSERT INTO teams(name, chat_id, created_at) VALUES (?,?,?)",
        (clean, _clean_chat_id(chat_id), to_iso(moment)),
    )
    team_id = int(created.lastrowid or 0)
    audit(conn, actor, "team.create", "team", team_id, {"name": clean}, moment)
    return team_id


def update_team(
    conn: sqlite3.Connection,
    team_id: int,
    fields: dict[str, Any],
    actor: str,
    now: datetime | None = None,
) -> None:
    if conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone() is None:
        raise NotFound("Ekip bulunamadı")
    if "name" in fields:
        clean = _clean_name(fields["name"], "Ekip")
        clash = conn.execute("SELECT 1 FROM teams WHERE name=? AND id<>?", (clean, team_id)).fetchone()
        if clash is not None:
            raise ValidationFailed("Bu adda bir ekip zaten var")
        conn.execute("UPDATE teams SET name=? WHERE id=?", (clean, team_id))
    if "chat_id" in fields:
        conn.execute("UPDATE teams SET chat_id=? WHERE id=?", (_clean_chat_id(fields["chat_id"]), team_id))
    audit(conn, actor, "team.update", "team", team_id, {"fields": sorted(fields)}, now)


def create_user(
    conn: sqlite3.Connection,
    name: object,
    team_id: int | None,
    role: str,
    telegram_id: object,
    actor: str,
    now: datetime | None = None,
    email: object = None,
) -> int:
    clean = _clean_name(name, "Kullanıcı")
    if role not in ROLES:
        raise ValidationFailed("Geçersiz rol")
    if team_id is not None and conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone() is None:
        raise NotFound("Ekip bulunamadı")
    if conn.execute("SELECT 1 FROM users WHERE name=?", (clean,)).fetchone() is not None:
        raise ValidationFailed("Bu adda bir kullanıcı zaten var")
    moment = now or now_utc()
    created = conn.execute(
        "INSERT INTO users(team_id, name, role, telegram_id, email, created_at) VALUES (?,?,?,?,?,?)",
        (team_id, clean, role, _clean_chat_id(telegram_id), clean_email(email), to_iso(moment)),
    )
    user_id = int(created.lastrowid or 0)
    audit(conn, actor, "user.create", "user", user_id, {"name": clean, "role": role}, moment)
    return user_id


def update_user(
    conn: sqlite3.Connection,
    user_id: int,
    fields: dict[str, Any],
    actor: str,
    now: datetime | None = None,
) -> None:
    if conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
        raise NotFound("Kullanıcı bulunamadı")
    if "name" in fields:
        clean = _clean_name(fields["name"], "Kullanıcı")
        clash = conn.execute("SELECT 1 FROM users WHERE name=? AND id<>?", (clean, user_id)).fetchone()
        if clash is not None:
            raise ValidationFailed("Bu adda bir kullanıcı zaten var")
        conn.execute("UPDATE users SET name=? WHERE id=?", (clean, user_id))
    if "role" in fields:
        if fields["role"] not in ROLES:
            raise ValidationFailed("Geçersiz rol")
        conn.execute("UPDATE users SET role=? WHERE id=?", (fields["role"], user_id))
    if "team_id" in fields:
        team_id = fields["team_id"]
        if (
            team_id is not None
            and conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone() is None
        ):
            raise NotFound("Ekip bulunamadı")
        conn.execute("UPDATE users SET team_id=? WHERE id=?", (team_id, user_id))
    if "telegram_id" in fields:
        conn.execute(
            "UPDATE users SET telegram_id=? WHERE id=?", (_clean_chat_id(fields["telegram_id"]), user_id)
        )
    if "email" in fields:
        conn.execute("UPDATE users SET email=? WHERE id=?", (clean_email(fields["email"]), user_id))
    if "status" in fields:
        if fields["status"] not in ("active", "inactive"):
            raise ValidationFailed("Durum yalnızca 'active' veya 'inactive' olabilir")
        conn.execute("UPDATE users SET status=? WHERE id=?", (fields["status"], user_id))
    audit(conn, actor, "user.update", "user", user_id, {"fields": sorted(fields)}, now)
