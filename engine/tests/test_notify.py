from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from etkilesim import notify, secrets_store, settings
from etkilesim.notify import SendError, TelegramSender

from .helpers import FakeSender

FAKE_TOKEN = "123456789:" + "A" * 35


def enable(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "notifications_enabled", True, "admin", now=t0 - timedelta(hours=1))


def test_dedupe_key_is_idempotent(conn: sqlite3.Connection, t0: datetime) -> None:
    first = notify.queue(conn, "strike", "1", "m", "k1", None, t0)
    second = notify.queue(conn, "strike", "1", "m", "k1", None, t0)
    assert first is not None and second is None
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 1


def test_retry_with_backoff_then_success(conn: sqlite3.Connection, t0: datetime) -> None:
    enable(conn, t0)
    notify.queue(conn, "strike", "1", "m", "k", None, t0)
    sender = FakeSender([SendError("geçici")])
    assert notify.flush(conn, sender, t0).retrying == 1
    row = conn.execute("SELECT * FROM notifications").fetchone()
    assert row["attempts"] == 1 and row["status"] == "pending"
    assert notify.flush(conn, sender, t0 + timedelta(seconds=30)).sent == 0  # henüz erken
    assert notify.flush(conn, sender, t0 + timedelta(minutes=2)).sent == 1
    assert conn.execute("SELECT status FROM notifications").fetchone()["status"] == "sent"


def test_permanent_failure_stops_immediately(conn: sqlite3.Connection, t0: datetime) -> None:
    enable(conn, t0)
    notify.queue(conn, "strike", "1", "m", "k", None, t0)
    summary = notify.flush(conn, FakeSender([SendError("chat not found", permanent=True)]), t0)
    assert summary.failed == 1
    assert conn.execute("SELECT status FROM notifications").fetchone()["status"] == "failed"


def test_gives_up_after_max_attempts(conn: sqlite3.Connection, t0: datetime) -> None:
    enable(conn, t0)
    notify.queue(conn, "strike", "1", "m", "k", None, t0)
    sender = FakeSender([SendError("x")] * notify.MAX_ATTEMPTS)
    moment = t0
    for _ in range(notify.MAX_ATTEMPTS):
        notify.flush(conn, sender, moment)
        moment += timedelta(hours=5)
    assert conn.execute("SELECT status FROM notifications").fetchone()["status"] == "failed"


def test_retry_after_is_honored(conn: sqlite3.Connection, t0: datetime) -> None:
    enable(conn, t0)
    notify.queue(conn, "strike", "1", "m", "k", None, t0)
    notify.flush(conn, FakeSender([SendError("429", retry_after=600)]), t0)
    assert notify.flush(conn, FakeSender(), t0 + timedelta(minutes=9)).sent == 0
    assert notify.flush(conn, FakeSender(), t0 + timedelta(minutes=10)).sent == 1


def test_error_text_is_redacted(conn: sqlite3.Connection, t0: datetime) -> None:
    enable(conn, t0)
    notify.queue(conn, "strike", "1", "m", "k", None, t0)
    notify.flush(conn, FakeSender([SendError(f"POST /bot{FAKE_TOKEN}/sendMessage failed")]), t0)
    error = conn.execute("SELECT last_error FROM notifications").fetchone()["last_error"]
    assert FAKE_TOKEN not in error and "GİZLİ" in error


def test_telegram_sender_maps_responses() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def ok(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        calls.append((url, payload))
        return 200, {"ok": True}

    TelegramSender(FAKE_TOKEN, ok).send("42", "merhaba")
    assert calls[0][0].endswith("/sendMessage") and calls[0][1]["chat_id"] == "42"
    assert "parse_mode" not in calls[0][1]  # düz metin: biçim enjeksiyonu yok

    def limited(_u: str, _p: dict[str, object]) -> tuple[int, dict[str, object]]:
        return 429, {"description": "Too Many", "parameters": {"retry_after": 7}}

    try:
        TelegramSender(FAKE_TOKEN, limited).send("42", "x")
    except SendError as exc:
        assert exc.retry_after == 7 and not exc.permanent

    def bad(_u: str, _p: dict[str, object]) -> tuple[int, dict[str, object]]:
        return 403, {"description": "bot was blocked"}

    try:
        TelegramSender(FAKE_TOKEN, bad).send("42", "x")
    except SendError as exc:
        assert exc.permanent


def test_missing_token_is_permanent_error(monkeypatch: object) -> None:
    import pytest

    mp = pytest.MonkeyPatch()
    mp.delenv("ETKILESIM_TELEGRAM_TOKEN", raising=False)
    mp.setattr(secrets_store, "get_token", lambda: None)
    try:
        TelegramSender().send("1", "x")
    except SendError as exc:
        assert exc.permanent
    finally:
        mp.undo()


def test_token_format_validation() -> None:
    import pytest

    from etkilesim.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        secrets_store.set_token("not-a-token")
