from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from etkilesim import notify, posts, settings, strikes
from etkilesim.clock import to_iso

from .helpers import FakeSender, make_user, public_resolver


def add_post(conn: sqlite3.Connection, user_id: int, n: int, now: datetime) -> posts.AddPostResult:
    return posts.add_post(conn, user_id, f"https://x.com/a/status/{n}", now=now, resolver=public_resolver)


def notifications(conn: sqlite3.Connection, kind: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM notifications WHERE kind=? ORDER BY id", (kind,)).fetchall()


def user_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()  # type: ignore[no-any-return]


def test_no_strike_before_threshold(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    assert strikes.run_inactivity_check(conn, t0 + timedelta(days=2, hours=23)) == []


def test_three_strike_flow_with_test_clock(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "admin_chat_id", "-100999", "admin")
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)

    first = strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    assert [(o.strike_number, o.flagged) for o in first] == [(1, False)]
    second = strikes.run_inactivity_check(conn, t0 + timedelta(days=4))
    assert [(o.strike_number, o.flagged) for o in second] == [(2, False)]
    third = strikes.run_inactivity_check(conn, t0 + timedelta(days=5))
    assert [(o.strike_number, o.flagged) for o in third] == [(3, True)]

    user = user_row(conn, uid)
    assert user["status"] == "flagged"
    assert user["strike_count"] == 3
    assert user["flagged_at"] is not None
    assert len(notifications(conn, "strike")) == 3
    flags = notifications(conn, "flag")
    assert {f["target"] for f in flags} == {"-100999"}
    assert "YÖNETİCİ İNCELEMESİ" in flags[0]["message"]
    assert "Marketing A" in flags[0]["message"]
    # Bayraklı kullanıcıya daha fazla uyarı verilmez.
    assert strikes.run_inactivity_check(conn, t0 + timedelta(days=6)) == []


def test_same_check_twice_does_not_double_count(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    moment = t0 + timedelta(days=3)
    assert len(strikes.run_inactivity_check(conn, moment)) == 1
    assert strikes.run_inactivity_check(conn, moment) == []
    assert strikes.run_inactivity_check(conn, moment + timedelta(hours=1)) == []
    assert user_row(conn, uid)["strike_count"] == 1
    assert conn.execute("SELECT COUNT(*) FROM strike_events").fetchone()[0] == 1


def test_nightly_checks_tolerate_seconds_of_drift(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    drifted = t0 + timedelta(days=4) - timedelta(seconds=2)
    assert [o.strike_number for o in strikes.run_inactivity_check(conn, drifted)] == [2]


def test_new_post_resets_strikes_but_keeps_history(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    for day in (3, 4, 5):
        strikes.run_inactivity_check(conn, t0 + timedelta(days=day))
    assert user_row(conn, uid)["status"] == "flagged"

    back = t0 + timedelta(days=5, hours=2)
    add_post(conn, uid, 2, back)
    user = user_row(conn, uid)
    assert (user["strike_count"], user["status"], user["flagged_at"]) == (0, "active", None)
    assert user["total_strikes"] == 3  # geçmiş korunur
    events = conn.execute("SELECT resolved_at FROM strike_events").fetchall()
    assert len(events) == 3
    assert all(e["resolved_at"] is not None for e in events)
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='strike.reset'").fetchone()[0] == 1


def test_reset_cancels_unsent_strike_notifications(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    add_post(conn, uid, 2, t0 + timedelta(days=3, hours=1))
    assert notifications(conn, "strike")[0]["status"] == "suppressed"


def test_new_cycle_after_reset_can_strike_again(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    add_post(conn, uid, 2, t0 + timedelta(days=3, hours=1))
    later = t0 + timedelta(days=7)
    out = strikes.run_inactivity_check(conn, later)
    assert [o.strike_number for o in out] == [1]
    assert len(notifications(conn, "strike")) == 2  # farklı döngü anahtarı → ayrı bildirim


def test_user_who_never_posted_is_measured_from_creation(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    assert strikes.run_inactivity_check(conn, t0 + timedelta(days=2)) == []
    out = strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    assert [o.user_id for o in out] == [uid]


def test_admin_settings_change_behavior(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "inactivity_days", 1, "admin")
    settings.set_value(conn, "strike_interval_hours", 12, "admin")
    settings.set_value(conn, "max_strikes", 2, "admin")
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    assert [o.strike_number for o in strikes.run_inactivity_check(conn, t0 + timedelta(days=1))] == [1]
    assert strikes.run_inactivity_check(conn, t0 + timedelta(days=1, hours=6)) == []
    out = strikes.run_inactivity_check(conn, t0 + timedelta(days=1, hours=12))
    assert [(o.strike_number, o.flagged) for o in out] == [(2, True)]


def test_team_override_applies_only_to_that_team(conn: sqlite3.Connection, t0: datetime) -> None:
    a = make_user(conn, "Ayşe", "Marketing A", now=t0)
    b = make_user(conn, "Burak", "Marketing B", now=t0)
    add_post(conn, a, 1, t0)
    add_post(conn, b, 2, t0)
    team_a = int(user_row(conn, a)["team_id"])
    settings.set_value(conn, "inactivity_days", 1, "admin", team_id=team_a)
    out = strikes.run_inactivity_check(conn, t0 + timedelta(days=1))
    assert [o.user_id for o in out] == [a]


def test_inactive_users_are_skipped(conn: sqlite3.Connection, t0: datetime) -> None:
    from etkilesim import people

    uid = make_user(conn, now=t0)
    people.update_user(conn, uid, {"status": "inactive"}, "admin")
    assert strikes.run_inactivity_check(conn, t0 + timedelta(days=30)) == []


def test_user_without_telegram_gets_no_target_notification(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, telegram=None, now=t0)
    add_post(conn, uid, 1, t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    assert notifications(conn, "strike")[0]["status"] == "no_target"


def test_flag_without_any_chat_still_recorded(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "max_strikes", 1, "admin")
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    assert user_row(conn, uid)["status"] == "flagged"
    assert notifications(conn, "flag")[0]["status"] == "no_target"


def test_end_to_end_delivery_respects_enable_switch(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add_post(conn, uid, 1, t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    sender = FakeSender()
    held = notify.flush(conn, sender, t0 + timedelta(days=3))
    assert held.held and sender.sent == []
    # Etkinleştirmeden ÖNCE oluşan bildirim toplu gönderilmez.
    settings.set_value(conn, "notifications_enabled", True, "admin", now=t0 + timedelta(days=3, hours=1))
    summary = notify.flush(conn, sender, t0 + timedelta(days=3, hours=1))
    assert summary.suppressed == 1 and sender.sent == []
    # Etkinleştirmeden SONRA oluşan bildirim gider.
    strikes.run_inactivity_check(conn, t0 + timedelta(days=4, hours=1))
    summary = notify.flush(conn, sender, t0 + timedelta(days=4, hours=1))
    assert summary.sent == 1
    assert sender.sent[0][0] == "111222"
    assert "Uyarı 2/3" in sender.sent[0][1]
    assert to_iso(t0)  # saat yardımcısı kullanılabilir
