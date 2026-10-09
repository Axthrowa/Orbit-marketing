"""Sırlar: işletim sistemi kimlik deposunda (Windows Kimlik Yöneticisi / macOS Keychain / Secret Service).

Sırlar veritabanına, günlüğe veya arayüze yazılmaz. Her sırrın geliştirme/test için bir ortam
değişkeni geçersiz kılması vardır. Hata ve günlük metinleri `redact` ile temizlenir.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from .errors import EngineError, ValidationFailed

SERVICE = "EtkilesimTakip"
_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
_REDACT_RE = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")
_WEBHOOK_REDACT_RE = re.compile(
    r"https://[^\s\"']*(?:logic\.azure\.com|powerplatform\.com|webhook\.office\.com)[^\s\"']*"
)


def _telegram(value: str) -> None:
    if not _TOKEN_RE.match(value):
        raise ValidationFailed("Telegram bot jetonu biçimi geçersiz (örn. 123456:ABC...)")


def _password(value: str) -> None:
    if not 1 <= len(value) <= 256:
        raise ValidationFailed("Şifre 1-256 karakter olmalı")


def _webhook(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or len(value) > 2048:
        raise ValidationFailed("Teams Workflows adresi https ile başlayan geçerli bir adres olmalı")


@dataclass(frozen=True)
class SecretSpec:
    account: str
    env: str
    validate: Callable[[str], None]
    label: str


SECRETS: dict[str, SecretSpec] = {
    "telegram_bot_token": SecretSpec(
        "telegram_bot_token", "ETKILESIM_TELEGRAM_TOKEN", _telegram, "Telegram bot jetonu"
    ),
    "smtp_password": SecretSpec("smtp_password", "ETKILESIM_SMTP_PASSWORD", _password, "SMTP şifresi"),
    "teams_webhook": SecretSpec(
        "teams_webhook", "ETKILESIM_TEAMS_WEBHOOK", _webhook, "Teams Workflows adresi"
    ),
}


def redact(text: str) -> str:
    return _WEBHOOK_REDACT_RE.sub("[GİZLİ-ADRES]", _REDACT_RE.sub("[GİZLİ]", text))


def _keyring() -> object:
    try:
        import keyring
    except ImportError as exc:  # pragma: no cover - bağımlılık kurulu
        raise EngineError("keyring kurulu değil") from exc
    return keyring


def _spec(name: str) -> SecretSpec:
    spec = SECRETS.get(name)
    if spec is None:
        raise ValidationFailed(f"Bilinmeyen sır: {name}")
    return spec


def get_secret(name: str) -> str | None:
    spec = _spec(name)
    env = os.environ.get(spec.env)
    if env:
        return env
    try:
        value = _keyring().get_password(SERVICE, spec.account)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - anahtarlık erişilemezse "sır yok" say
        return None
    return value if isinstance(value, str) and value else None


def has_secret(name: str) -> bool:
    return get_secret(name) is not None


def set_secret(name: str, value: str) -> None:
    spec = _spec(name)
    clean = value.strip()
    spec.validate(clean)
    try:
        _keyring().set_password(SERVICE, spec.account, clean)  # type: ignore[attr-defined]
    except Exception as exc:
        raise EngineError(f"{spec.label} işletim sistemi kimlik deposuna yazılamadı") from exc


def clear_secret(name: str) -> None:
    spec = _spec(name)
    with contextlib.suppress(Exception):  # zaten yoksa/erişilemezse sorun değil
        _keyring().delete_password(SERVICE, spec.account)  # type: ignore[attr-defined]


def status() -> dict[str, bool]:
    return {name: has_secret(name) for name in SECRETS}


# Geriye uyum: Telegram yardımcıları
def get_token() -> str | None:
    return get_secret("telegram_bot_token")


def has_token() -> bool:
    return has_secret("telegram_bot_token")


def set_token(token: str) -> None:
    set_secret("telegram_bot_token", token)


def clear_token() -> None:
    clear_secret("telegram_bot_token")
