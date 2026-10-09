"""Yerel yönetici kapısı: scrypt ile saklanan PIN + yanlış denemede geçici kilit.

Not: Bu yerel bir masaüstü uygulamasıdır; PIN, uygulama arayüzü üzerinden yapılan
yönetici işlemlerini korur, disk erişimi olan birine karşı güvenlik sınırı DEĞİLDİR.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta

from .clock import from_iso, now_utc, to_iso
from .db import audit
from .errors import PermissionDenied, ValidationFailed

_N, _R, _P = 2**14, 8, 1
MAX_FAILURES = 5
LOCKOUT = timedelta(minutes=5)
MIN_PIN_LENGTH = 6


def _hash(pin: str, salt: bytes) -> str:
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _read(conn: sqlite3.Connection, key: str) -> object | None:
    row = conn.execute("SELECT value_json FROM settings WHERE scope='secure' AND key=?", (key,)).fetchone()
    return None if row is None else json.loads(row["value_json"])


def _write(conn: sqlite3.Connection, key: str, value: object, now: datetime) -> None:
    conn.execute(
        "INSERT INTO settings(scope,key,value_json,updated_at) VALUES ('secure',?,?,?)"
        " ON CONFLICT(scope,key) DO UPDATE SET value_json=excluded.value_json,"
        " updated_at=excluded.updated_at",
        (key, json.dumps(value), to_iso(now)),
    )


def pin_is_set(conn: sqlite3.Connection) -> bool:
    return isinstance(_read(conn, "admin_pin"), str)


def set_pin(
    conn: sqlite3.Connection, new_pin: str, current_pin: str | None, now: datetime | None = None
) -> None:
    moment = now or now_utc()
    if len(new_pin) < MIN_PIN_LENGTH:
        raise ValidationFailed(f"PIN en az {MIN_PIN_LENGTH} karakter olmalı")
    if pin_is_set(conn):
        verify_pin(conn, current_pin or "", moment)
    _write(conn, "admin_pin", _hash(new_pin, secrets.token_bytes(16)), moment)
    _write(conn, "pin_failures", {"count": 0, "locked_until": None}, moment)
    audit(conn, "admin", "auth.set_pin", None, None, None, moment)


def verify_pin(conn: sqlite3.Connection, pin: str, now: datetime | None = None) -> None:
    moment = now or now_utc()
    stored = _read(conn, "admin_pin")
    if not isinstance(stored, str):
        raise PermissionDenied("Yönetici PIN'i henüz belirlenmedi")
    state = _read(conn, "pin_failures")
    failures = state if isinstance(state, dict) else {"count": 0, "locked_until": None}
    locked_until = failures.get("locked_until")
    if isinstance(locked_until, str) and from_iso(locked_until) > moment:
        raise PermissionDenied("Çok fazla hatalı deneme; bir süre sonra tekrar deneyin")
    _, salt_hex, digest_hex = stored.split("$")
    candidate = _hash(pin, bytes.fromhex(salt_hex)).split("$")[2]
    if hmac.compare_digest(candidate, digest_hex):
        _write(conn, "pin_failures", {"count": 0, "locked_until": None}, moment)
        return
    previous = failures.get("count", 0)
    count = (previous if isinstance(previous, int) else 0) + 1
    lock = to_iso(moment + LOCKOUT) if count >= MAX_FAILURES else None
    _write(conn, "pin_failures", {"count": 0 if lock else count, "locked_until": lock}, moment)
    audit(conn, "unknown", "auth.pin_failed", None, None, {"count": count}, moment)
    raise PermissionDenied("Yönetici PIN'i hatalı")


def require_admin(conn: sqlite3.Connection, pin: str | None, now: datetime | None = None) -> None:
    if not pin:
        raise PermissionDenied("Bu işlem için yönetici PIN'i gerekir")
    verify_pin(conn, pin, now)
