from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from etkilesim import auth, cli, dashboard, posts, scheduler, settings
from etkilesim.errors import NotFound, PermissionDenied, ValidationFailed

from .helpers import make_user, public_resolver

PIN = "246810"


def add(conn: sqlite3.Connection, uid: int, url: str, t: datetime, **kw: Any) -> int:
    return posts.add_post(conn, uid, url, now=t, resolver=public_resolver, **kw).post_id


# ----- pano -----------------------------------------------------------------------------------


def test_unknown_metrics_are_none_not_zero(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add(conn, uid, "https://x.com/a/status/1", t0)
    state = dashboard.get_state(conn, now=t0)
    assert state["kpis"]["posts"] == 1 and state["kpis"]["posts_without_metrics"] == 1
    assert state["kpis"]["likes"] is None and state["kpis"]["views"] is None
    assert state["posts"][0]["likes"] is None and state["posts"][0]["positive"] is None
    assert state["people"][0]["engagement"] is None


def test_totals_and_team_filter(conn: sqlite3.Connection, t0: datetime) -> None:
    a = make_user(conn, "Ayşe", "Marketing A", now=t0)
    b = make_user(conn, "Burak", "Marketing B", now=t0)
    pa = add(conn, a, "https://x.com/a/status/1", t0)
    pb = add(conn, b, "https://x.com/b/status/2", t0)
    posts.set_manual_metrics(conn, pa, 10, 2, 1, 100, "u", t0)
    posts.set_manual_metrics(conn, pb, 5, 1, None, None, "u", t0)
    everyone = dashboard.get_state(conn, now=t0)
    assert (everyone["kpis"]["likes"], everyone["kpis"]["views"]) == (15, 100)
    team_a = int(conn.execute("SELECT team_id FROM users WHERE id=?", (a,)).fetchone()[0])
    only_a = dashboard.get_state(conn, team_id=team_a, now=t0)
    assert only_a["kpis"]["posts"] == 1 and only_a["kpis"]["likes"] == 10
    assert [p["user_name"] for p in only_a["posts"]] == ["Ayşe"]
    assert {t["name"] for t in only_a["teams"]} == {"Marketing A", "Marketing B"}
    ayse = next(p for p in everyone["people"] if p["name"] == "Ayşe")
    assert ayse["engagement"] == 13 and ayse["days_since_last_post"] == 0


def test_state_contains_settings_and_security(conn: sqlite3.Connection, t0: datetime) -> None:
    state = dashboard.get_state(conn, now=t0)
    assert state["settings"]["values"]["inactivity_days"] == 3
    assert any(s["key"] == "max_strikes" for s in state["settings"]["spec"])
    assert state["security"]["pin_set"] is False
    auth.set_pin(conn, PIN, None, t0)
    assert dashboard.get_state(conn, now=t0)["security"]["pin_set"] is True


# ----- CLI dispatch ---------------------------------------------------------------------------


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cli.PIN_ENV, PIN)


def test_admin_commands_need_pin(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cli.PIN_ENV, raising=False)
    with pytest.raises(PermissionDenied):
        cli.dispatch("add-team", {"name": "A"}, conn)
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)  # ilk kurulum: PIN belirlemek serbest
    with pytest.raises(PermissionDenied):
        cli.dispatch("add-team", {"name": "A"}, conn)
    monkeypatch.setenv(cli.PIN_ENV, "wrong-pin")
    with pytest.raises(PermissionDenied):
        cli.dispatch("add-team", {"name": "A"}, conn)
    monkeypatch.setenv(cli.PIN_ENV, PIN)
    assert cli.dispatch("add-team", {"name": "A"}, conn)["team_id"] > 0


def test_changing_pin_requires_current(conn: sqlite3.Connection, admin_env: None) -> None:
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)
    with pytest.raises(PermissionDenied):
        cli.dispatch("set-pin", {"new_pin": "999999"}, conn)
    cli.dispatch("set-pin", {"new_pin": "999999", "current_pin": PIN}, conn)


def test_full_flow_through_dispatch(
    conn: sqlite3.Connection, admin_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("etkilesim.security._default_resolver", lambda *_: ["93.184.216.34"])
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)
    team = cli.dispatch("add-team", {"name": "Marketing A", "chat_id": "-100123"}, conn)["team_id"]
    user = cli.dispatch(
        "add-user", {"name": "Ayşe", "team_id": team, "role": "member", "telegram_id": "555111"}, conn
    )["user_id"]
    created = cli.dispatch(
        "add-post",
        {
            "user_id": user,
            "url": "https://x.com/a/status/9?s=20",
            "community_name": "r/IndieGaming",
            "preview_text": "Üç yıllık emeğimiz",
        },
        conn,
    )
    assert created["created"] and created["platform"] == "X"
    again = cli.dispatch("add-post", {"user_id": user, "url": "https://x.com/a/status/9"}, conn)
    assert not again["created"] and again["post_id"] == created["post_id"]
    ctx = cli.dispatch("posting-context", {"name": "indiegaming"}, conn)
    assert ctx["recommendation"] == "AVOID" and ctx["last_post"]["user"] == "Ayşe"
    cli.dispatch("manual-metrics", {"post_id": created["post_id"], "likes": "12", "views": 340}, conn)
    cli.dispatch("manual-comments", {"post_id": created["post_id"], "texts": ["harika", "berbat"]}, conn)
    detail = cli.dispatch("post-detail", {"post_id": created["post_id"]}, conn)
    assert detail["post"]["current_likes"] == 12 and len(detail["comments"]) == 2
    assert len(detail["snapshots"]) == 1 and detail["snapshots"][0]["source"] == "MANUAL"
    state = cli.dispatch("state", {}, conn)
    assert state["kpis"]["likes"] == 12 and state["posts"][0]["sentiment_sample"] == 2


def test_settings_roundtrip_and_team_override(conn: sqlite3.Connection, admin_env: None) -> None:
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)
    team = cli.dispatch("add-team", {"name": "A"}, conn)["team_id"]
    cli.dispatch("settings-set", {"changes": {"inactivity_days": 5, "max_strikes": 4}}, conn)
    cli.dispatch("settings-set", {"team_id": team, "changes": {"inactivity_days": 2}}, conn)
    got = cli.dispatch("settings-get", {"team_id": team}, conn)
    assert got["values"]["inactivity_days"] == 2 and got["values"]["max_strikes"] == 4
    assert got["overrides"] == {"inactivity_days": 2}
    with pytest.raises(ValidationFailed):
        cli.dispatch("settings-set", {"changes": {"inactivity_days": 0}}, conn)
    cli.dispatch("settings-clear-override", {"team_id": team, "key": "inactivity_days"}, conn)
    assert cli.dispatch("settings-get", {"team_id": team}, conn)["values"]["inactivity_days"] == 5


def test_settings_set_is_atomic(conn: sqlite3.Connection, admin_env: None) -> None:
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)
    with pytest.raises(ValidationFailed):
        cli.dispatch("settings-set", {"changes": {"inactivity_days": 9, "max_strikes": 99}}, conn)
    assert settings.get(conn, "inactivity_days") == 3  # ilk değişiklik de geri alındı


def test_strike_check_with_test_clock_via_cli(
    conn: sqlite3.Connection, admin_env: None, t0: datetime
) -> None:
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)
    uid = make_user(conn, now=t0)
    add(conn, uid, "https://x.com/a/status/1", t0)
    later = (t0 + timedelta(days=3)).isoformat()
    out = cli.dispatch("strike-check", {"now": later}, conn)
    assert out["strikes"] == [{"user": "Ahmet", "number": 1, "flagged": False}]


def test_community_blocking_needs_admin_but_favorite_does_not(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    cid = cli.dispatch("add-community", {"name": "r/Test", "platform": "Reddit"}, conn)["community_id"]
    cli.dispatch("community-state", {"community_id": cid, "favorite": True}, conn)
    monkeypatch.delenv(cli.PIN_ENV, raising=False)
    with pytest.raises(PermissionDenied):
        cli.dispatch("community-state", {"community_id": cid, "status": "blocked"}, conn)


def test_validation_and_unknown_command(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFound):
        cli.dispatch("nope", {}, conn)
    with pytest.raises(ValidationFailed):
        cli.dispatch("post-detail", {}, conn)
    with pytest.raises(ValidationFailed):
        cli.dispatch("post-detail", {"post_id": "abc"}, conn)


def test_no_command_leaks_secret_values(conn: sqlite3.Connection, admin_env: None) -> None:
    cli.dispatch("set-pin", {"new_pin": PIN}, conn)
    dump = json.dumps(cli.dispatch("state", {}, conn))
    assert "scrypt" not in dump and PIN not in dump


def run_cli(tmp_path: Path, command: str, payload: dict[str, Any], pin: str | None = None) -> dict[str, Any]:
    env = {**os.environ, "ETKILESIM_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "cp1252"}
    env.pop("ETKILESIM_ADMIN_PIN", None)
    if pin:
        env["ETKILESIM_ADMIN_PIN"] = pin
    proc = subprocess.run(
        [sys.executable, "-m", "etkilesim", command],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    return json.loads(proc.stdout.decode("utf-8"))  # type: ignore[no-any-return]


def test_subprocess_contract_utf8_and_errors(tmp_path: Path) -> None:
    health = run_cli(tmp_path, "health", {})
    assert health["ok"] and health["data"]["author"] == "axthrowa"
    assert run_cli(tmp_path, "set-pin", {"new_pin": PIN})["ok"]
    denied = run_cli(tmp_path, "add-team", {"name": "Çok Ekip"})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED"
    created = run_cli(tmp_path, "add-team", {"name": "Çok Ekip"}, pin=PIN)
    assert created["ok"]
    state = run_cli(tmp_path, "state", {})
    assert state["data"]["teams"][0]["name"] == "Çok Ekip"  # Türkçe karakter bozulmadan geçti
    assert run_cli(tmp_path, "bogus", {})["error"]["code"] == "NOT_FOUND"


def test_subprocess_rejects_bad_json(tmp_path: Path) -> None:
    env = {**os.environ, "ETKILESIM_DATA_DIR": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "etkilesim", "state"],
        input=b"{broken",
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    out = json.loads(proc.stdout.decode("utf-8"))
    assert not out["ok"] and out["error"]["code"] == "VALIDATION" and proc.returncode == 1


# ----- zamanlayıcı ----------------------------------------------------------------------------


def test_last_scheduled_picks_most_recent_past_time() -> None:
    now = datetime(2026, 10, 5, 0, 30).astimezone()
    assert scheduler.last_scheduled(now, "00:00") == now.replace(hour=0, minute=0)
    assert scheduler.last_scheduled(now, "03:00") == now.replace(hour=3, minute=0) - timedelta(days=1)


def test_missed_nightly_check_is_detected_and_catch_up_recorded(conn: sqlite3.Connection) -> None:
    local = datetime.now().astimezone()
    assert scheduler.strike_check_overdue(conn, local) is True
    job = scheduler._job_started(conn, "strike_check", datetime.now().astimezone())
    scheduler._job_finished(conn, job, True, "0 uyarı", datetime.now().astimezone())
    assert scheduler.strike_check_overdue(conn, local) is False


def test_failed_check_does_not_count_as_done(conn: sqlite3.Connection) -> None:
    job = scheduler._job_started(conn, "strike_check", datetime.now().astimezone())
    scheduler._job_finished(conn, job, False, "boom", datetime.now().astimezone())
    assert scheduler.strike_check_overdue(conn, datetime.now().astimezone()) is True


def test_reconcile_follows_admin_settings(tmp_path: Path) -> None:
    from etkilesim import db

    db_file = tmp_path / "s.db"
    conn = db.connect(db_file)
    engine = scheduler.EngineScheduler(db_file)
    engine.reconcile()
    assert engine._applied["refresh"] == ("interval", 6)
    assert engine._applied["strike_check"] == ("cron", "00:00")
    settings.set_value(conn, "metrics_interval_hours", 2, "admin")
    settings.set_value(conn, "strike_check_time", "03:30", "admin")
    engine.reconcile()
    assert engine._applied["refresh"] == ("interval", 2)
    assert engine._applied["strike_check"] == ("cron", "03:30")
    conn.close()


def test_single_instance_lock(tmp_path: Path) -> None:
    path = tmp_path / "daemon.lock"
    first = scheduler.acquire_lock(path)
    assert first is not None
    assert scheduler.acquire_lock(path) is None
    first.close()
    again = scheduler.acquire_lock(path)
    assert again is not None
    again.close()


def test_people_rows_carry_team_specific_limits(conn: sqlite3.Connection, t0: datetime) -> None:
    a = make_user(conn, "Ayşe", "Marketing A", now=t0)
    make_user(conn, "Burak", "Marketing B", now=t0)
    team_a = int(conn.execute("SELECT team_id FROM users WHERE id=?", (a,)).fetchone()[0])
    settings.set_value(conn, "max_strikes", 5, "admin", team_id=team_a)
    settings.set_value(conn, "inactivity_days", 2, "admin", team_id=team_a)
    people = {p["name"]: p for p in dashboard.get_state(conn, now=t0)["people"]}
    assert (people["Ayşe"]["max_strikes"], people["Ayşe"]["inactivity_days"]) == (5, 2)
    assert (people["Burak"]["max_strikes"], people["Burak"]["inactivity_days"]) == (3, 3)


def test_process_alive_detects_self_and_dead_processes() -> None:
    assert scheduler.process_alive(os.getpid()) is True
    assert scheduler.process_alive(0) is False
    finished = subprocess.run([sys.executable, "-c", "pass"], check=True)
    assert finished.returncode == 0
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert scheduler.process_alive(child.pid) is False


def test_watchdog_stops_daemon_when_parent_exits() -> None:
    import asyncio

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])

    async def scenario() -> bool:
        stop = asyncio.Event()
        await asyncio.wait_for(scheduler.watch_parent(child.pid, stop, interval=0.05), timeout=10)
        return stop.is_set()

    assert asyncio.run(scenario()) is True
    child.wait()


def test_user_view_shows_only_own_records(conn: sqlite3.Connection, t0: datetime) -> None:
    a = make_user(conn, "Ayşe", "Marketing A", now=t0)
    b = make_user(conn, "Burak", "Marketing A", now=t0)
    pa = add(conn, a, "https://x.com/a/status/1", t0)
    add(conn, b, "https://x.com/b/status/2", t0)
    posts.set_manual_metrics(conn, pa, 10, 1, None, None, "u", t0)
    state = dashboard.get_state(conn, user_id=a, now=t0)
    assert [p["user_name"] for p in state["posts"]] == ["Ayşe"]
    assert state["kpis"]["posts"] == 1 and state["kpis"]["likes"] == 10
    assert [p["name"] for p in state["people"]] == ["Ayşe"]
    assert {acc["name"] for acc in state["accounts"]} == {"Ayşe", "Burak"}  # hesap seçimi için yalnızca ad
    assert "telegram_id" not in state["accounts"][0]
    assert state["user_filter"] == a


def test_user_view_filters_notifications(conn: sqlite3.Connection, t0: datetime) -> None:
    from etkilesim import strikes

    a = make_user(conn, "Ayşe", now=t0)
    make_user(conn, "Burak", now=t0)
    strikes.run_inactivity_check(conn, t0 + timedelta(days=3))
    mine = dashboard.get_state(conn, user_id=a, now=t0)
    assert {n["user_name"] for n in mine["notifications"]} == {"Ayşe"}
    assert sum(mine["notification_summary"].values()) == 1
    assert sum(dashboard.get_state(conn, now=t0)["notification_summary"].values()) == 2


def test_page_note_is_saved_shown_in_history_and_editable(conn: sqlite3.Connection, t0: datetime) -> None:
    from etkilesim import community

    uid = make_user(conn, now=t0)
    pid = add(
        conn,
        uid,
        "https://x.com/a/status/1",
        t0,
        community_name="r/IndieGaming",
        note="Moderatörler link sevmiyor",
    )
    ctx = community.posting_context(conn, name="r/IndieGaming", now=t0)
    assert ctx["last_post"]["note"] == "Moderatörler link sevmiyor"
    assert dashboard.get_state(conn, now=t0)["posts"][0]["note"] == "Moderatörler link sevmiyor"
    cli.dispatch("update-note", {"post_id": pid, "note": "  Cuma günleri daha aktif  "}, conn)
    assert (
        community.posting_context(conn, name="r/IndieGaming", now=t0)["last_post"]["note"]
        == "Cuma günleri daha aktif"
    )
    cli.dispatch("update-note", {"post_id": pid, "note": ""}, conn)
    assert posts.post_detail(conn, pid)["post"]["note"] is None
    with pytest.raises(ValidationFailed):
        cli.dispatch("update-note", {"post_id": pid, "note": "x" * 501}, conn)
    with pytest.raises(NotFound):
        cli.dispatch("update-note", {"post_id": 9999, "note": "a"}, conn)
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='post.note'").fetchone()[0] == 2
