"""Yönetici ayarları: genel + ekip bazlı geçersiz kılma, doğrulamalı, denetim kayıtlı."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .clock import now_utc, to_iso
from .db import audit
from .errors import ValidationFailed

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class Spec:
    kind: str  # int | bool | time | str | list | enum
    default: Any
    low: int = 0
    high: int = 0
    choices: tuple[str, ...] = ()
    team_overridable: bool = False
    label: str = ""


SPECS: dict[str, Spec] = {
    "inactivity_days": Spec("int", 3, 1, 60, team_overridable=True, label="Hareketsizlik eşiği (gün)"),
    "strike_interval_hours": Spec(
        "int", 24, 1, 168, team_overridable=True, label="Uyarılar arası süre (saat)"
    ),
    "max_strikes": Spec("int", 3, 1, 10, team_overridable=True, label="İşaretlenmeden önce uyarı sayısı"),
    "strike_check_time": Spec("time", "00:00", label="Günlük kontrol saati (HH:MM)"),
    "metrics_interval_hours": Spec("int", 6, 1, 168, label="Ölçüm aralığı (saat)"),
    "comment_limit": Spec("int", 50, 5, 500, label="Gönderi başına yorum sınırı"),
    "community_avoid_days": Spec("int", 3, 0, 365, label="Topluluk: KAÇIN (≤ gün)"),
    "community_recent_days": Spec("int", 7, 0, 365, label="Topluluk: YAKIN ZAMANDA (≤ gün)"),
    "community_caution_days": Spec("int", 14, 0, 365, label="Topluluk: DİKKAT (≤ gün)"),
    "scrape_enabled": Spec("bool", True, label="Tarayıcı ile ölçüm açık"),
    "scrape_headless": Spec("bool", True, label="Tarayıcı arka planda çalışsın"),
    "discovery_enabled": Spec("bool", True, label="Topluluk keşfi açık"),
    "discovery_interval_hours": Spec("int", 24, 1, 720, label="Keşif aralığı (saat)"),
    "discovery_keywords": Spec("list", ["FPS oyunları", "Indie Games"], label="Keşif anahtar kelimeleri"),
    "sentiment_engine": Spec(
        "enum", "lexicon", choices=("lexicon", "transformer"), label="Duygu analizi motoru"
    ),
    "comment_retention_days": Spec(
        "int", 180, 0, 3650, label="Yorum metni saklama süresi (gün, 0 = süresiz)"
    ),
    "audit_retention_days": Spec(
        "int", 365, 0, 3650, label="Denetim günlüğü saklama süresi (gün, 0 = süresiz)"
    ),
    "backup_keep": Spec("int", 14, 1, 365, label="Tutulacak günlük yedek sayısı"),
    "metrics_schedule": Spec(
        "enum", "fixed", choices=("fixed", "adaptive"), label="Ölçüm takvimi (sabit / uyarlanabilir)"
    ),
    "target_languages": Spec("list", ["tr", "en"], label="Hedef kitle dilleri (tr, en, …)"),
    "perf_weight_consistency": Spec("int", 20, 0, 100, label="Performans ağırlığı: düzenli paylaşım"),
    "perf_weight_engagement": Spec("int", 30, 0, 100, label="Performans ağırlığı: etkileşim"),
    "perf_weight_sentiment": Spec("int", 15, 0, 100, label="Performans ağırlığı: oyuncu tepkisi"),
    "perf_weight_diversity": Spec("int", 10, 0, 100, label="Performans ağırlığı: topluluk çeşitliliği"),
    "perf_weight_velocity": Spec("int", 15, 0, 100, label="Performans ağırlığı: etkileşim hızı"),
    "perf_weight_campaign": Spec("int", 10, 0, 100, label="Performans ağırlığı: kampanya katkısı"),
    "notifications_enabled": Spec("bool", False, label="Telegram bildirimleri açık"),
    "admin_chat_id": Spec("str", "", label="Yönetici Telegram sohbet kimliği"),
    "email_enabled": Spec("bool", False, label="E-posta bildirimleri açık"),
    "smtp_host": Spec("str", "", label="SMTP sunucusu (örn. smtp.gmail.com)"),
    "smtp_port": Spec("int", 587, 1, 65535, label="SMTP portu (465 SSL, 587 STARTTLS)"),
    "smtp_user": Spec("str", "", label="SMTP kullanıcı adı"),
    "smtp_from": Spec("str", "", label="Gönderen e-posta adresi"),
    "admin_email": Spec("str", "", label="Yönetici e-posta adresi"),
    "teams_enabled": Spec("bool", False, label="Microsoft Teams bildirimleri açık"),
}


def _coerce(key: str, value: Any) -> Any:
    spec = SPECS.get(key)
    if spec is None:
        raise ValidationFailed(f"Bilinmeyen ayar: {key}")
    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise ValidationFailed(f"{key}: sayı bekleniyor")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(f"{key}: sayı bekleniyor") from exc
        if not spec.low <= number <= spec.high:
            raise ValidationFailed(f"{key}: {spec.low}-{spec.high} aralığında olmalı")
        return number
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValidationFailed(f"{key}: doğru/yanlış bekleniyor")
        return value
    if spec.kind == "time":
        if not isinstance(value, str) or not _TIME_RE.match(value):
            raise ValidationFailed(f"{key}: HH:MM biçiminde olmalı")
        return value
    if spec.kind == "enum":
        if value not in spec.choices:
            raise ValidationFailed(f"{key}: {', '.join(spec.choices)} değerlerinden biri olmalı")
        return value
    if spec.kind == "list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValidationFailed(f"{key}: metin listesi bekleniyor")
        cleaned = [v.strip() for v in value if v.strip()]
        if len(cleaned) > 30 or any(len(v) > 80 for v in cleaned):
            raise ValidationFailed(f"{key}: en çok 30 öğe, her biri en çok 80 karakter")
        return cleaned
    if not isinstance(value, str) or len(value) > 200:
        raise ValidationFailed(f"{key}: en çok 200 karakterlik metin")
    return value.strip()


def _scope(team_id: int | None) -> str:
    return "global" if team_id is None else f"team:{team_id}"


def _read(conn: sqlite3.Connection, scope: str, key: str) -> Any | None:
    row = conn.execute("SELECT value_json FROM settings WHERE scope=? AND key=?", (scope, key)).fetchone()
    return None if row is None else json.loads(row["value_json"])


def get(conn: sqlite3.Connection, key: str, team_id: int | None = None) -> Any:
    """Etkin değer: ekip geçersiz kılması → genel → varsayılan."""
    spec = SPECS[key]
    if team_id is not None and spec.team_overridable:
        override = _read(conn, _scope(team_id), key)
        if override is not None:
            return override
    stored = _read(conn, "global", key)
    return spec.default if stored is None else stored


def effective(conn: sqlite3.Connection, team_id: int | None = None) -> dict[str, Any]:
    return {key: get(conn, key, team_id) for key in SPECS}


def describe() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "kind": spec.kind,
            "label": spec.label,
            "default": spec.default,
            "low": spec.low,
            "high": spec.high,
            "choices": list(spec.choices),
            "team_overridable": spec.team_overridable,
        }
        for key, spec in SPECS.items()
    ]


def set_value(
    conn: sqlite3.Connection,
    key: str,
    value: Any,
    actor: str,
    team_id: int | None = None,
    now: datetime | None = None,
) -> Any:
    spec = SPECS.get(key)
    if spec is None:
        raise ValidationFailed(f"Bilinmeyen ayar: {key}")
    if team_id is not None and not spec.team_overridable:
        raise ValidationFailed(f"{key} ekip bazında değiştirilemez")
    coerced = _coerce(key, value)
    _check_cross_field(conn, key, coerced, team_id)
    moment = now or now_utc()
    previous = get(conn, key, team_id)
    conn.execute(
        "INSERT INTO settings(scope,key,value_json,updated_at) VALUES (?,?,?,?)"
        " ON CONFLICT(scope,key) DO UPDATE SET value_json=excluded.value_json,"
        " updated_at=excluded.updated_at",
        (_scope(team_id), key, json.dumps(coerced, ensure_ascii=False), to_iso(moment)),
    )
    if key == "notifications_enabled" and coerced and not previous:
        # Etkinleştirmeden önce biriken bildirimler toplu gitmesin.
        conn.execute(
            "INSERT INTO settings(scope,key,value_json,updated_at) VALUES ('global',"
            "'notifications_active_since',?,?) ON CONFLICT(scope,key) DO UPDATE SET"
            " value_json=excluded.value_json, updated_at=excluded.updated_at",
            (json.dumps(to_iso(moment)), to_iso(moment)),
        )
    audit(
        conn,
        actor,
        "settings.set",
        "setting",
        f"{_scope(team_id)}:{key}",
        {"old": previous, "new": coerced},
        moment,
    )
    return coerced


def clear_team_override(
    conn: sqlite3.Connection, key: str, team_id: int, actor: str, now: datetime | None = None
) -> None:
    conn.execute("DELETE FROM settings WHERE scope=? AND key=?", (_scope(team_id), key))
    audit(conn, actor, "settings.clear_override", "setting", f"{_scope(team_id)}:{key}", None, now)


def _check_cross_field(conn: sqlite3.Connection, key: str, value: Any, team_id: int | None) -> None:
    order = ("community_avoid_days", "community_recent_days", "community_caution_days")
    if key not in order:
        return
    values = {k: (value if k == key else get(conn, k, team_id)) for k in order}
    if not values[order[0]] <= values[order[1]] <= values[order[2]]:
        raise ValidationFailed("Topluluk eşikleri artan sırada olmalı: kaçın ≤ yakın zamanda ≤ dikkat")


def notifications_active_since(conn: sqlite3.Connection) -> str | None:
    value = _read(conn, "global", "notifications_active_since")
    return value if isinstance(value, str) else None
