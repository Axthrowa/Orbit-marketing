from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from etkilesim import auth, settings
from etkilesim.errors import PermissionDenied, ValidationFailed


def make_team(conn: sqlite3.Connection, name: str = "A") -> int:
    cur = conn.execute("INSERT INTO teams(name, created_at) VALUES (?, '2026-01-01T00:00:00Z')", (name,))
    assert cur.lastrowid is not None
    return cur.lastrowid


def test_defaults(conn: sqlite3.Connection) -> None:
    assert settings.get(conn, "inactivity_days") == 3
    assert settings.get(conn, "max_strikes") == 3
    assert settings.get(conn, "strike_interval_hours") == 24
    assert settings.get(conn, "notifications_enabled") is False


def test_set_and_audit(conn: sqlite3.Connection) -> None:
    settings.set_value(conn, "inactivity_days", 5, "admin")
    assert settings.get(conn, "inactivity_days") == 5
    row = conn.execute("SELECT detail_json FROM audit_log WHERE action='settings.set'").fetchone()
    assert '"old": 3' in row["detail_json"]
    assert '"new": 5' in row["detail_json"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("inactivity_days", 0),
        ("inactivity_days", 999),
        ("inactivity_days", "abc"),
        ("inactivity_days", True),
        ("strike_check_time", "25:00"),
        ("strike_check_time", "0:00"),
        ("notifications_enabled", "yes"),
        ("sentiment_engine", "gpt"),
        ("nope", 1),
        ("discovery_keywords", "not a list"),
    ],
)
def test_validation_rejects(conn: sqlite3.Connection, key: str, value: object) -> None:
    with pytest.raises(ValidationFailed):
        settings.set_value(conn, key, value, "admin")


def test_team_override_precedence(conn: sqlite3.Connection) -> None:
    team = make_team(conn)
    other = make_team(conn, "B")
    settings.set_value(conn, "inactivity_days", 7, "admin")
    settings.set_value(conn, "inactivity_days", 2, "admin", team_id=team)
    assert settings.get(conn, "inactivity_days", team) == 2
    assert settings.get(conn, "inactivity_days", other) == 7
    assert settings.get(conn, "inactivity_days") == 7
    settings.clear_team_override(conn, "inactivity_days", team, "admin")
    assert settings.get(conn, "inactivity_days", team) == 7


def test_non_overridable_key_rejected_for_team(conn: sqlite3.Connection) -> None:
    team = make_team(conn)
    with pytest.raises(ValidationFailed):
        settings.set_value(conn, "metrics_interval_hours", 2, "admin", team_id=team)


def test_community_thresholds_must_be_ascending(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValidationFailed):
        settings.set_value(conn, "community_avoid_days", 10, "admin")  # recent=7 < 10


def test_enabling_notifications_records_active_since(conn: sqlite3.Connection, t0: datetime) -> None:
    assert settings.notifications_active_since(conn) is None
    settings.set_value(conn, "notifications_enabled", True, "admin", now=t0)
    assert settings.notifications_active_since(conn) == "2026-10-01T12:00:00Z"


def test_pin_lifecycle(conn: sqlite3.Connection, t0: datetime) -> None:
    assert not auth.pin_is_set(conn)
    with pytest.raises(PermissionDenied):
        auth.require_admin(conn, "123456", t0)
    with pytest.raises(ValidationFailed):
        auth.set_pin(conn, "123", None, t0)
    auth.set_pin(conn, "246810", None, t0)
    auth.require_admin(conn, "246810", t0)
    with pytest.raises(PermissionDenied):
        auth.require_admin(conn, None, t0)
    with pytest.raises(PermissionDenied):
        auth.set_pin(conn, "135790", "wrong-pin", t0)
    auth.set_pin(conn, "135790", "246810", t0)
    auth.require_admin(conn, "135790", t0)


def test_pin_is_not_stored_in_clear(conn: sqlite3.Connection, t0: datetime) -> None:
    auth.set_pin(conn, "246810", None, t0)
    stored = conn.execute("SELECT value_json FROM settings WHERE key='admin_pin'").fetchone()
    assert "246810" not in stored["value_json"]
    assert "scrypt" in stored["value_json"]


def test_lockout_after_repeated_failures(conn: sqlite3.Connection, t0: datetime) -> None:
    auth.set_pin(conn, "246810", None, t0)
    for _ in range(auth.MAX_FAILURES):
        with pytest.raises(PermissionDenied):
            auth.verify_pin(conn, "000000", t0)
    with pytest.raises(PermissionDenied, match="Çok fazla"):
        auth.verify_pin(conn, "246810", t0 + timedelta(minutes=1))  # doğru PIN bile kilitli
    auth.verify_pin(conn, "246810", t0 + auth.LOCKOUT + timedelta(seconds=1))
