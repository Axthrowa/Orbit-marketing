"""Bildirim kuyruğu (outbox) + Telegram / e-posta (SMTP) / Microsoft Teams göndericileri.

- Her bildirim `dedupe_key` ile tekildir: aynı olay iki kez kuyruğa girmez.
- Bildirimler kapalıyken hiçbir şey gönderilmez; açıldığında önceden birikenler
  toplu gönderilmez ('suppressed').
- Gönderim hataları üstel geri çekilmeyle yeniden denenir; jeton hata metninden temizlenir.
"""

from __future__ import annotations

import json
import smtplib
import sqlite3
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Protocol

from . import secrets_store, settings
from .clock import now_utc, to_iso

MAX_ATTEMPTS = 5
BACKOFF_MINUTES = (1, 5, 15, 60, 240)
TELEGRAM_TIMEOUT = 15
CHANNELS = ("TELEGRAM", "EMAIL", "TEAMS")


class SendError(Exception):
    def __init__(self, message: str, permanent: bool = False, retry_after: int | None = None):
        super().__init__(message)
        self.permanent = permanent
        self.retry_after = retry_after


class Sender(Protocol):
    def send(self, target: str, text: str) -> None: ...


def queue(
    conn: sqlite3.Connection,
    kind: str,
    target: str | None,
    message: str,
    dedupe_key: str,
    user_id: int | None = None,
    now: datetime | None = None,
    channel: str = "TELEGRAM",
) -> int | None:
    """Kuyruğa ekler; aynı dedupe_key varsa None döner (idempotent)."""
    status = "pending" if target else "no_target"
    cur = conn.execute(
        "INSERT OR IGNORE INTO notifications(user_id,kind,target,message,dedupe_key,status,"
        "created_at,channel) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, kind, target, message, dedupe_key, status, to_iso(now or now_utc()), channel),
    )
    return (cur.lastrowid or 0) if cur.rowcount else None


def fan_out(
    conn: sqlite3.Connection,
    kind: str,
    message: str,
    dedupe_base: str,
    user_id: int | None,
    targets: list[tuple[str, str | None]],
    now: datetime | None = None,
) -> None:
    """Bir olayı açık kanallara dağıtır. Telegram anahtarı geriye uyum için önsüz tutulur."""
    for channel, target in targets:
        key = dedupe_base if channel == "TELEGRAM" else f"{channel.lower()}:{dedupe_base}"
        queue(conn, kind, target, message, key, user_id, now, channel)


def enabled_channels(conn: sqlite3.Connection) -> set[str]:
    channels = {"TELEGRAM"}
    if settings.get(conn, "email_enabled"):
        channels.add("EMAIL")
    if settings.get(conn, "teams_enabled"):
        channels.add("TEAMS")
    return channels


def cancel_pending(conn: sqlite3.Connection, user_id: int, kinds: tuple[str, ...], reason: str) -> int:
    marks = ",".join("?" for _ in kinds)
    cur = conn.execute(
        f"UPDATE notifications SET status='suppressed', last_error=? WHERE user_id=?"  # noqa: S608
        f" AND kind IN ({marks}) AND status IN ('pending','no_target')",
        (reason, user_id, *kinds),
    )
    return cur.rowcount


@dataclass
class FlushSummary:
    sent: int = 0
    failed: int = 0
    retrying: int = 0
    suppressed: int = 0
    held: bool = False


def flush(
    conn: sqlite3.Connection,
    sender: Sender | Mapping[str, Sender],
    now: datetime | None = None,
    limit: int = 25,
) -> FlushSummary:
    """Tek gönderici verilirse tüm kanallar için kullanılır (testler); yoksa kanal → gönderici eşlemesi."""
    moment = now or now_utc()
    summary = FlushSummary()
    if not settings.get(conn, "notifications_enabled"):
        summary.held = True
        return summary
    since = settings.notifications_active_since(conn)
    if since:
        cur = conn.execute(
            "UPDATE notifications SET status='suppressed',"
            " last_error='Bildirimler açılmadan önce oluştu' WHERE status='pending'"
            " AND created_at < ?",
            (since,),
        )
        summary.suppressed = cur.rowcount
    rows = conn.execute(
        "SELECT * FROM notifications WHERE status='pending' AND attempts < ?"
        " AND (next_attempt_at IS NULL OR next_attempt_at <= ?) ORDER BY id LIMIT ?",
        (MAX_ATTEMPTS, to_iso(moment), limit),
    ).fetchall()
    for row in rows:
        attempts = int(row["attempts"]) + 1
        channel = str(row["channel"])
        chosen = sender.get(channel) if isinstance(sender, Mapping) else sender
        try:
            if chosen is None:
                raise SendError(f"{channel} kanalı yapılandırılmamış", permanent=True)
            chosen.send(str(row["target"]), str(row["message"]))
        except SendError as exc:
            message = secrets_store.redact(str(exc))[:300]
            if exc.permanent or attempts >= MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE notifications SET status='failed', attempts=?, last_error=? WHERE id=?",
                    (attempts, message, row["id"]),
                )
                summary.failed += 1
                continue
            delay = (
                timedelta(seconds=exc.retry_after)
                if exc.retry_after
                else timedelta(minutes=BACKOFF_MINUTES[min(attempts - 1, len(BACKOFF_MINUTES) - 1)])
            )
            conn.execute(
                "UPDATE notifications SET attempts=?, last_error=?, next_attempt_at=? WHERE id=?",
                (attempts, message, to_iso(moment + delay), row["id"]),
            )
            summary.retrying += 1
            continue
        conn.execute(
            "UPDATE notifications SET status='sent', attempts=?, sent_at=?, last_error=NULL WHERE id=?",
            (attempts, to_iso(moment), row["id"]),
        )
        summary.sent += 1
    return summary


PostFunc = Callable[[str, dict[str, Any]], tuple[int, dict[str, Any]]]


def _http_post(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 - sabit https://api.telegram.org
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_TIMEOUT) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            body = {}
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SendError(f"Ağ hatası: {exc.__class__.__name__}") from exc


class TelegramSender:
    def __init__(self, token: str | None = None, post: PostFunc | None = None) -> None:
        self._token = token
        self._post = post or _http_post

    def send(self, target: str, text: str) -> None:
        token = self._token or secrets_store.get_token()
        if not token:
            raise SendError("Telegram bot jetonu tanımlı değil", permanent=True)
        status, body = self._post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": target, "text": text[:4000], "disable_web_page_preview": True},
        )
        if status == 200 and body.get("ok"):
            return
        description = str(body.get("description", f"HTTP {status}"))
        if status == 429:
            retry = body.get("parameters", {}).get("retry_after")
            raise SendError(description, retry_after=int(retry) if retry else 60)
        if 400 <= status < 500:
            raise SendError(description, permanent=True)
        raise SendError(description)


class EmailSender:
    """SMTP: 465 → SSL, diğer portlar → STARTTLS. Şifre kimlik deposundan okunur."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        from_addr: str,
        password: str | None = None,
        smtp_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._host, self._port, self._user, self._from = host, port, user, from_addr or user
        self._password = password
        self._factory = smtp_factory

    def send(self, target: str, text: str) -> None:
        if not self._host or not self._from:
            raise SendError("SMTP sunucusu veya gönderen adresi ayarlanmamış", permanent=True)
        password = self._password or secrets_store.get_secret("smtp_password")
        message = EmailMessage()
        first_line = text.strip().splitlines()[0] if text.strip() else "Etkileşim Takip bildirimi"
        message["Subject"] = f"Etkileşim Takip · {first_line[:120]}"
        message["From"] = self._from
        message["To"] = target
        message.set_content(f"{text}\n\n— Etkileşim Takip (created by axthrowa)")
        context = ssl.create_default_context()
        try:
            if self._factory is not None:
                client = self._factory(self._host, self._port)
            elif self._port == 465:
                client = smtplib.SMTP_SSL(self._host, self._port, timeout=20, context=context)
            else:
                client = smtplib.SMTP(self._host, self._port, timeout=20)
            with client:
                if self._factory is None and self._port != 465:
                    client.starttls(context=context)
                if self._user and password:
                    client.login(self._user, password)
                client.send_message(message)
        except (
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused,
        ) as exc:
            raise SendError(f"SMTP reddetti: {exc.__class__.__name__}", permanent=True) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(f"SMTP hatası: {exc.__class__.__name__}") from exc


class TeamsSender:
    """Microsoft Teams Workflows ("webhook isteği alındığında") akışına Adaptive Card gönderir."""

    def __init__(self, url: str | None = None, post: PostFunc | None = None) -> None:
        self._url = url
        self._post = post or _http_post

    def send(self, target: str, text: str) -> None:
        del target  # hedef akışın kendisidir (kanal/sohbet Teams tarafında seçilir)
        url = self._url or secrets_store.get_secret("teams_webhook")
        if not url:
            raise SendError("Teams Workflows adresi tanımlı değil", permanent=True)
        lines = text.strip().splitlines() or ["Etkileşim Takip bildirimi"]
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": lines[0], "weight": "Bolder", "size": "Medium", "wrap": True},
                *(
                    {"type": "TextBlock", "text": line, "wrap": True, "spacing": "Small"}
                    for line in lines[1:]
                ),
            ],
        }
        payload = {
            "type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
        }
        status, body = self._post(url, payload)
        if status in (200, 202):
            return
        description = secrets_store.redact(str(body.get("error", f"HTTP {status}")))
        if status == 429:
            raise SendError(description, retry_after=60)
        if 400 <= status < 500:
            raise SendError(description, permanent=True)
        raise SendError(description)


def build_senders(conn: sqlite3.Connection) -> dict[str, Sender]:
    return {
        "TELEGRAM": TelegramSender(),
        "EMAIL": EmailSender(
            str(settings.get(conn, "smtp_host")),
            int(settings.get(conn, "smtp_port")),
            str(settings.get(conn, "smtp_user")),
            str(settings.get(conn, "smtp_from")),
        ),
        "TEAMS": TeamsSender(),
    }


def due_summary(conn: sqlite3.Connection, user_id: int | None = None) -> dict[str, int]:
    if user_id is None:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM notifications GROUP BY status").fetchall()
    else:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM notifications WHERE user_id=? GROUP BY status", (user_id,)
        ).fetchall()
    return {r["status"]: int(r["n"]) for r in rows}
