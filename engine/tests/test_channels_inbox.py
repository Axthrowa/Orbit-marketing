from __future__ import annotations

import smtplib
import sqlite3
from datetime import datetime, timedelta
from typing import Any

import pytest

from etkilesim import cli, dashboard, inbox, notify, people, posts, secrets_store, settings, strikes
from etkilesim.errors import PermissionDenied, ValidationFailed
from etkilesim.notify import EmailSender, SendError, TeamsSender

from .helpers import FakeSender, make_user, public_resolver

WEBHOOK = "https://prod-12.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke?sig=SECRET"


def strike_three(conn: sqlite3.Connection, t0: datetime) -> int:
    settings.set_value(conn, "max_strikes", 1, "admin")
    uid = make_user(conn, now=t0)
    people.update_user(conn, uid, {"email": "Ayse@Example.com"}, "admin")
    posts.add_post(conn, uid, "https://x.com/a/status/1", now=t0, resolver=public_resolver)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    return uid


def test_strikes_land_in_user_and_admin_inboxes(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = strike_three(conn, t0)
    mine = inbox.listing(conn, uid)
    assert mine["unread"] == 1 and mine["items"][0]["title"].startswith("Paylaşım hatırlatması 1/1")
    admin = inbox.listing(conn, None)
    assert admin["unread"] == 1 and "yönetici incelemesi" in admin["items"][0]["title"]
    # Kişi yöneticinin kutusunu okundu yapamaz (kapsam ayrı).
    assert inbox.mark_read(conn, uid, [admin["items"][0]["id"]]) == 0
    assert inbox.mark_read(conn, uid, None) == 1
    assert inbox.unread(conn, uid) == 0 and inbox.unread(conn, None) == 1
    assert dashboard.get_state(conn, user_id=uid)["inbox_unread"] == 0
    assert dashboard.get_state(conn)["inbox_unread"] == 1


def test_inbox_is_idempotent(conn: sqlite3.Connection, t0: datetime) -> None:
    assert inbox.add(conn, "user", None, "x", "t", "b", "k", t0) is not None
    assert inbox.add(conn, "user", None, "x", "t", "b", "k", t0) is None
    with pytest.raises(ValidationFailed):
        inbox.add(conn, "everyone", None, "x", "t", "b", "k2", t0)


def test_enabled_channels_fan_out(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "email_enabled", True, "admin")
    settings.set_value(conn, "teams_enabled", True, "admin")
    settings.set_value(conn, "admin_email", "boss@example.com", "admin")
    strike_three(conn, t0)
    rows = conn.execute("SELECT kind, channel, target FROM notifications ORDER BY id").fetchall()
    got = {(r["kind"], r["channel"], r["target"]) for r in rows}
    assert ("strike", "EMAIL", "ayse@example.com") in got  # e-posta küçük harfe normalize
    assert ("flag", "EMAIL", "boss@example.com") in got
    assert ("flag", "TEAMS", "workflow") in got
    assert ("strike", "TELEGRAM", "111222") in got


def test_disabled_channels_are_not_queued(conn: sqlite3.Connection, t0: datetime) -> None:
    strike_three(conn, t0)
    channels = {r[0] for r in conn.execute("SELECT DISTINCT channel FROM notifications")}
    assert channels == {"TELEGRAM"}


def test_flush_routes_each_channel_to_its_sender(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "notifications_enabled", True, "admin", now=t0 - timedelta(hours=1))
    notify.queue(conn, "strike", "1", "tg", "a", None, t0, "TELEGRAM")
    notify.queue(conn, "strike", "x@y.com", "mail", "b", None, t0, "EMAIL")
    notify.queue(conn, "flag", "workflow", "teams", "c", None, t0, "TEAMS")
    tg, mail = FakeSender(), FakeSender()
    summary = notify.flush(conn, {"TELEGRAM": tg, "EMAIL": mail}, t0)
    assert (summary.sent, summary.failed) == (2, 1)
    assert tg.sent == [("1", "tg")] and mail.sent == [("x@y.com", "mail")]
    failed = conn.execute("SELECT last_error FROM notifications WHERE channel='TEAMS'").fetchone()[0]
    assert "TEAMS kanalı yapılandırılmamış" in failed


class FakeSMTP:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.logged: tuple[str, str] | None = None
        self.messages: list[Any] = []

    def __call__(self, _host: str, _port: int) -> FakeSMTP:
        return self

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        if self.fail:
            raise self.fail
        self.logged = (user, password)

    def send_message(self, message: Any) -> None:
        self.messages.append(message)


def test_email_sender_builds_message_and_maps_errors() -> None:
    smtp = FakeSMTP()
    EmailSender("smtp.example.com", 587, "bot", "bot@example.com", "pw", smtp).send(
        "ayse@example.com", "⚠️ Ayşe: 3 gündür paylaşım yok\nUyarı 1/3"
    )
    message = smtp.messages[0]
    assert smtp.logged == ("bot", "pw")
    assert message["To"] == "ayse@example.com" and "3 gündür" in message["Subject"]
    assert "created by axthrowa" in message.get_content()
    auth_fail = FakeSMTP(smtplib.SMTPAuthenticationError(535, b"no"))
    with pytest.raises(SendError) as auth:
        EmailSender("h", 587, "u", "f@x.com", "pw", auth_fail).send("a@b.c", "x")
    assert auth.value.permanent
    with pytest.raises(SendError) as transient:
        EmailSender("h", 587, "u", "f@x.com", "pw", FakeSMTP(smtplib.SMTPServerDisconnected("x"))).send(
            "a@b.c", "x"
        )
    assert not transient.value.permanent
    with pytest.raises(SendError) as missing:
        EmailSender("", 587, "", "", "pw", FakeSMTP()).send("a@b.c", "x")
    assert missing.value.permanent


def test_teams_sender_posts_adaptive_card_and_hides_url() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def ok(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        calls.append((url, payload))
        return 202, {}

    TeamsSender(WEBHOOK, ok).send("workflow", "🚨 KRİTİK\nKullanıcı: Burak")
    card = calls[0][1]["attachments"][0]
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert [b["text"] for b in card["content"]["body"]] == ["🚨 KRİTİK", "Kullanıcı: Burak"]

    def bad(_u: str, _p: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return 400, {"error": f"invalid {WEBHOOK}"}

    with pytest.raises(SendError) as err:
        TeamsSender(WEBHOOK, bad).send("workflow", "x")
    assert err.value.permanent and "SECRET" not in str(err.value) and "GİZLİ-ADRES" in str(err.value)


def test_secret_validation_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationFailed):
        secrets_store.set_secret("teams_webhook", "http://insecure.example.com")
    with pytest.raises(ValidationFailed):
        secrets_store.set_secret("nope", "x")
    monkeypatch.setenv("ETKILESIM_SMTP_PASSWORD", "env-pass")
    assert secrets_store.get_secret("smtp_password") == "env-pass"
    assert secrets_store.status()["smtp_password"] is True


def test_inbox_commands_and_admin_box_needs_pin(
    conn: sqlite3.Connection, t0: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = strike_three(conn, t0)
    assert cli.dispatch("inbox", {"user_id": uid}, conn)["unread"] == 1
    assert cli.dispatch("inbox-read", {"user_id": uid}, conn)["marked"] == 1
    monkeypatch.delenv(cli.PIN_ENV, raising=False)
    with pytest.raises(PermissionDenied):
        cli.dispatch("inbox", {"admin": True}, conn)
    with pytest.raises(ValidationFailed):
        cli.dispatch("inbox-read", {"user_id": uid, "ids": ["x"]}, conn)


def test_email_validation_on_people(conn: sqlite3.Connection, t0: datetime) -> None:
    with pytest.raises(ValidationFailed):
        people.create_user(conn, "X", None, "member", None, "admin", t0, email="not-an-email")
    uid = people.create_user(conn, "Y", None, "member", None, "admin", t0, email="y@example.com")
    assert dashboard.get_state(conn)["people"][0]["has_email"] is True
    assert uid > 0
