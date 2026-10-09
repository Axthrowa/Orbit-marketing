"""Komut satırı: `python -m etkilesim <komut>` — stdin'den JSON yükü, stdout'a JSON yanıtı.

Yanıt: {"ok": true, "data": ...} veya {"ok": false, "error": {"code", "message"}}.
Yönetici işlemleri PIN ister; PIN yalnızca `ETKILESIM_ADMIN_PIN` ortam değişkeniyle gelir
(argv'de görünmez). Telegram jetonu stdin yükünden alınır ve işletim sistemi kimlik deposuna yazılır.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from . import (
    __version__,
    analytics,
    auth,
    catalog,
    community,
    config,
    dashboard,
    db,
    inbox,
    logging_setup,
    maintenance,
    mockprovider,
    notify,
    people,
    posts,
    radar,
    recommend,
    refresh,
    scheduler,
    search,
    secrets_store,
    settings,
    strikes,
    system,
)
from .clock import now_utc
from .collectors import LOGIN_URLS, BrowserCollector
from .errors import EngineError, NotFound, ValidationFailed
from .sentiment import get_engine

log = logging.getLogger("etkilesim.cli")
Handler = Callable[[sqlite3.Connection, dict[str, Any]], Any]
COMMANDS: dict[str, tuple[Handler, bool]] = {}  # ad → (işleyici, yönetici_gerekli)
PIN_ENV = "ETKILESIM_ADMIN_PIN"
API_VERSION = "v1"  # Tauri ↔ motor komut sözleşmesi sürümü (master prompt §64)


def command(name: str, admin: bool = False) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        COMMANDS[name] = (handler, admin)
        return handler

    return register


def _int(payload: dict[str, Any], key: str, required: bool = True) -> int | None:
    value = payload.get(key)
    if value is None or value == "":
        if required:
            raise ValidationFailed(f"'{key}' gerekli")
        return None
    if isinstance(value, bool):
        raise ValidationFailed(f"'{key}' sayı olmalı")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(f"'{key}' sayı olmalı") from exc


def _str(payload: dict[str, Any], key: str, required: bool = True) -> str | None:
    value = payload.get(key)
    if value is None or value == "":
        if required:
            raise ValidationFailed(f"'{key}' gerekli")
        return None
    if not isinstance(value, str):
        raise ValidationFailed(f"'{key}' metin olmalı")
    return value


def _need_int(payload: dict[str, Any], key: str) -> int:
    value = _int(payload, key)
    assert value is not None
    return value


def _need_str(payload: dict[str, Any], key: str) -> str:
    value = _str(payload, key)
    assert value is not None
    return value


@command("health")
def health(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    try:
        import playwright  # noqa: F401

        browser_ready = True
    except ImportError:
        browser_ready = False
    return {
        "api_version": API_VERSION,
        "provider_mode": mockprovider.provider_mode(),
        "version": __version__,
        "author": "axthrowa",
        "db": str(config.db_path()),
        "pin_set": auth.pin_is_set(conn),
        "telegram_token_set": secrets_store.has_token(),
        "playwright_installed": browser_ready,
        "schema_version": conn.execute("PRAGMA user_version").fetchone()[0],
    }


@command("state")
def state(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return dashboard.get_state(conn, _int(p, "team_id", required=False), user_id=_int(p, "user_id", False))


@command("update-note")
def update_note(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    note = p.get("note")
    if note is not None and not isinstance(note, str):
        raise ValidationFailed("'note' metin olmalı")
    return {"note": posts.update_note(conn, _need_int(p, "post_id"), note, "user")}


@command("post-detail")
def post_detail(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return posts.post_detail(conn, _need_int(p, "post_id"))


@command("add-team", admin=True)
def add_team(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    team_id = people.create_team(conn, p.get("name"), p.get("chat_id"), "admin")
    return {"team_id": team_id}


@command("update-team", admin=True)
def update_team(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    fields = p.get("fields")
    if not isinstance(fields, dict):
        raise ValidationFailed("'fields' gerekli")
    people.update_team(conn, _need_int(p, "team_id"), fields, "admin")
    return {}


@command("add-user", admin=True)
def add_user(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    user_id = people.create_user(
        conn,
        p.get("name"),
        _int(p, "team_id", required=False),
        str(p.get("role") or "member"),
        p.get("telegram_id"),
        "admin",
        email=p.get("email"),
    )
    return {"user_id": user_id}


@command("update-user", admin=True)
def update_user(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    fields = p.get("fields")
    if not isinstance(fields, dict):
        raise ValidationFailed("'fields' gerekli")
    people.update_user(conn, _need_int(p, "user_id"), fields, "admin")
    return {}


@command("add-post")
def add_post(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    user_id = _need_int(p, "user_id")
    actor = conn.execute("SELECT name FROM users WHERE id=?", (user_id,)).fetchone()
    result = posts.add_post(
        conn,
        user_id,
        _need_str(p, "url"),
        _str(p, "community_name", False),
        _str(p, "community_url", False),
        _str(p, "preview_text", False),
        _str(p, "note", False),
        _str(p, "posted_at", False),
        actor["name"] if actor else "user",
        game_id=_int(p, "game_id", False),
        campaign_id=_int(p, "campaign_id", False),
        content_type=str(p.get("content_type") or "post"),
    )
    return {"post_id": result.post_id, "created": result.created, "platform": result.platform}


@command("analytics")
def analytics_command(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    days = _int(p, "days", False)
    if days is not None and days not in analytics.PERIODS:
        raise ValidationFailed("Dönem 1, 7, 30, 90 veya 365 gün olmalı")
    platform = _str(p, "platform", False)
    filters = analytics.Filters(
        days=days,
        campaign_id=_int(p, "campaign_id", False),
        game_id=_int(p, "game_id", False),
        platform=platform,
        team_id=_int(p, "team_id", False),
        user_id=_int(p, "user_id", False),
        community_id=_int(p, "community_id", False),
    )
    return analytics.overview(conn, filters)


@command("community-recommendations")
def community_recommendations(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return recommend.recommendations(
        conn,
        game_id=_int(p, "game_id", False),
        campaign_id=_int(p, "campaign_id", False),
        team_id=_int(p, "team_id", False),
    )


@command("inbox")
def inbox_list(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    if p.get("admin") is True:
        auth.require_admin(conn, os.environ.get(PIN_ENV))  # yönetici kutusu
        return inbox.listing(conn, None)
    return inbox.listing(conn, _need_int(p, "user_id"))


@command("inbox-read")
def inbox_read(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    ids = p.get("ids")
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, int) for i in ids)):
        raise ValidationFailed("'ids' sayı listesi olmalı")
    if p.get("admin") is True:
        auth.require_admin(conn, os.environ.get(PIN_ENV))
        return {"marked": inbox.mark_read(conn, None, ids)}
    return {"marked": inbox.mark_read(conn, _need_int(p, "user_id"), ids)}


@command("set-secret", admin=True)
def set_secret(_conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    secrets_store.set_secret(_need_str(p, "name"), _need_str(p, "value"))
    return secrets_store.status()


@command("clear-secret", admin=True)
def clear_secret(_conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    secrets_store.clear_secret(_need_str(p, "name"))
    return secrets_store.status()


@command("test-email", admin=True)
def test_email(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    from .people import clean_email

    target = clean_email(_need_str(p, "to"))
    assert target is not None
    try:
        notify.build_senders(conn)["EMAIL"].send(
            target, "Test e-postası\nEtkileşim Takip bildirimleri çalışıyor."
        )
    except notify.SendError as exc:
        raise EngineError(secrets_store.redact(str(exc))) from exc
    return {"sent": True}


@command("test-teams", admin=True)
def test_teams(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    try:
        notify.build_senders(conn)["TEAMS"].send(
            "workflow", "✅ Etkileşim Takip test mesajı\ncreated by axthrowa"
        )
    except notify.SendError as exc:
        raise EngineError(secrets_store.redact(str(exc))) from exc
    return {"sent": True}


@command("add-game", admin=True)
def add_game(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return {"game_id": catalog.create_game(conn, p, "admin")}


@command("update-game", admin=True)
def update_game(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    fields = p.get("fields")
    if not isinstance(fields, dict):
        raise ValidationFailed("'fields' gerekli")
    catalog.update_game(conn, _need_int(p, "game_id"), fields, "admin")
    return {}


@command("add-campaign", admin=True)
def add_campaign(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return {"campaign_id": catalog.create_campaign(conn, p, "admin")}


@command("update-campaign", admin=True)
def update_campaign(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    fields = p.get("fields")
    if not isinstance(fields, dict):
        raise ValidationFailed("'fields' gerekli")
    catalog.update_campaign(conn, _need_int(p, "campaign_id"), fields, "admin")
    return {}


@command("archive-post", admin=True)
def archive_post(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    archived = p.get("archived", True)
    if not isinstance(archived, bool):
        raise ValidationFailed("'archived' doğru/yanlış olmalı")
    posts.set_archived(conn, _need_int(p, "post_id"), archived, "admin")
    return {"archived": archived}


@command("manual-metrics")
def manual_metrics(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    posts.set_manual_metrics(
        conn,
        _need_int(p, "post_id"),
        p.get("likes"),
        p.get("comments"),
        p.get("shares"),
        p.get("views"),
        "user",
    )
    return {}


@command("manual-comments")
def manual_comments(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    texts = p.get("texts")
    if not isinstance(texts, list):
        raise ValidationFailed("'texts' liste olmalı")
    engine = get_engine(str(settings.get(conn, "sentiment_engine")))
    return {"added": posts.add_manual_comments(conn, _need_int(p, "post_id"), texts, engine, "user")}


@command("posting-context")
def posting_context(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return community.posting_context(
        conn,
        name=_str(p, "name", False),
        url=_str(p, "url", False),
        community_id=_int(p, "community_id", False),
        team_id=_int(p, "team_id", False),
    )


@command("find-communities")
def find_communities(conn: sqlite3.Connection, p: dict[str, Any]) -> list[dict[str, Any]]:
    return community.search(conn, str(p.get("query") or ""))


@command("add-community")
def add_community(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    cid = community.get_or_create(
        conn, _need_str(p, "name"), str(p.get("platform") or "Other"), _str(p, "url", False), "user"
    )
    return {"community_id": cid}


@command("community-state")
def community_state(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    status = _str(p, "status", False)
    if status is not None:
        auth.require_admin(conn, os.environ.get(PIN_ENV))  # engelleme/onay yönetici işidir
    favorite = p.get("favorite")
    community.set_state(
        conn, _need_int(p, "community_id"), status, favorite if isinstance(favorite, bool) else None, "user"
    )
    return {}


@command("refresh")
def refresh_command(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    ids = p.get("post_ids")
    post_ids = [int(i) for i in ids] if isinstance(ids, list) else None
    headless = bool(settings.get(conn, "scrape_headless"))

    def work() -> dict[str, Any]:
        summary = asyncio.run(
            refresh.refresh(
                conn,
                post_ids=post_ids,
                browser_factory=lambda: BrowserCollector(config.profile_dir(), headless=headless),
            )
        )
        return summary.as_dict()

    return work() if post_ids else _manual(conn, "refresh", work)


@command("discover", admin=True)
def discover(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    keywords = list(settings.get(conn, "discovery_keywords"))

    def work() -> dict[str, Any]:
        report = radar.discover(conn, keywords, actor="admin")
        return {
            "found": report.found,
            "added": report.added,
            "queries": report.queries,
            "unavailable": sorted(set(report.unavailable)),
        }

    return _manual(conn, "discovery", work)


@command("strike-check", admin=True)
def strike_check(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    raw = _str(p, "now", False)  # test saati (yalnızca yönetici)
    moment = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC) if raw else now_utc()

    def work() -> dict[str, Any]:
        outcomes = strikes.run_inactivity_check(conn, moment)
        return {
            "strikes": [
                {"user": o.user_name, "number": o.strike_number, "flagged": o.flagged} for o in outcomes
            ]
        }

    return _manual(conn, "strike_check", work)


@command("flush", admin=True)
def flush(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        s = notify.flush(conn, notify.build_senders(conn))
        return {
            "sent": s.sent,
            "failed": s.failed,
            "retrying": s.retrying,
            "suppressed": s.suppressed,
            "held": s.held,
        }

    return _manual(conn, "flush", work)


@command("settings-get")
def settings_get(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    team_id = _int(p, "team_id", False)
    overrides: dict[str, Any] = {}
    if team_id is not None:
        for row in conn.execute("SELECT key, value_json FROM settings WHERE scope=?", (f"team:{team_id}",)):
            overrides[row["key"]] = json.loads(row["value_json"])
    return {"values": settings.effective(conn, team_id), "spec": settings.describe(), "overrides": overrides}


@command("settings-set", admin=True)
def settings_set(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    changes = p.get("changes")
    team_id = _int(p, "team_id", False)
    if not isinstance(changes, dict) or not changes:
        raise ValidationFailed("'changes' gerekli")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for key, value in changes.items():
            settings.set_value(conn, str(key), value, "admin", team_id)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"values": settings.effective(conn, team_id)}


@command("settings-clear-override", admin=True)
def settings_clear(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    settings.clear_team_override(conn, _need_str(p, "key"), _need_int(p, "team_id"), "admin")
    return {}


@command("set-pin")
def set_pin(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    auth.set_pin(conn, _need_str(p, "new_pin"), _str(p, "current_pin", False))
    return {}


@command("verify-pin", admin=True)
def verify_pin(_conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    return {"admin": True}  # admin=True kapısı PIN'i zaten doğruladı


@command("set-telegram-token", admin=True)
def set_telegram_token(_conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    secrets_store.set_token(_need_str(p, "token"))
    return {"telegram_token_set": True}


@command("clear-telegram-token", admin=True)
def clear_telegram_token(_conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    secrets_store.clear_token()
    return {"telegram_token_set": False}


@command("test-telegram", admin=True)
def test_telegram(_conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    try:
        notify.TelegramSender().send(
            _need_str(p, "chat_id"), "✅ Etkileşim Takip test mesajı (created by axthrowa)"
        )
    except notify.SendError as exc:
        raise EngineError(secrets_store.redact(str(exc))) from exc
    return {"sent": True}


@command("login-session", admin=True)
def login_session(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    platform = _need_str(p, "platform")
    if platform not in LOGIN_URLS:
        raise ValidationFailed("Geçersiz platform")
    del conn
    asyncio.run(BrowserCollector(config.profile_dir(), headless=False).interactive_login(platform))
    return {"platform": platform}


def _manual(conn: sqlite3.Connection, name: str, work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Elle tetiklenen işi iş geçmişine 'manual' olarak kaydeder."""
    holder: dict[str, Any] = {}

    def run() -> str:
        holder.update(work())
        return json.dumps(holder, ensure_ascii=False)[:500]

    system.record_job(conn, name, "manual", run)
    return holder


@command("system-overview", admin=True)
def system_overview(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobs": system.jobs(conn),
        "providers": system.provider_health(conn),
        "audit": system.audit_log(conn, action=_str(p, "action", False)),
        "warnings": system.warning_history(conn),
    }


@command("run-job", admin=True)
def run_job(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    name = _need_str(p, "name")
    handlers: dict[str, Callable[[], dict[str, Any]]] = {
        "refresh": lambda: refresh_command(conn, {}),
        "strike_check": lambda: strike_check(conn, {}),
        "discovery": lambda: discover(conn, {}),
        "flush": lambda: flush(conn, {}),
        "retention": lambda: retention(conn, {}),
        "backup": lambda: backup(conn, {}),
    }
    if name not in handlers:
        raise ValidationFailed("Bilinmeyen iş")
    return handlers[name]()


@command("retention", admin=True)
def retention(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    return _manual(conn, "retention", lambda: maintenance.apply_retention(conn, actor="admin"))


@command("backup", admin=True)
def backup(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    return _manual(conn, "backup", lambda: maintenance.backup(conn))


@command("export", admin=True)
def export(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return maintenance.export(conn, _need_str(p, "format"))


@command("search")
def search_command(conn: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    return search.search(conn, _need_str(p, "query"), _int(p, "user_id", False))


@command("seed-demo", admin=True)
def seed_demo(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    from . import seed

    conn.execute("BEGIN IMMEDIATE")
    try:
        counts = seed.seed_demo(conn)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return counts


@command("metrics")
def metrics(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    return {"content_type": "text/plain; version=0.0.4", "text": system.metrics_text(conn)}


@command("retry-failed", admin=True)
def retry_failed(conn: sqlite3.Connection, _p: dict[str, Any]) -> dict[str, Any]:
    return system.retry_failed(conn, "admin")


def dispatch(name: str, payload: dict[str, Any], conn: sqlite3.Connection) -> Any:
    entry = COMMANDS.get(name)
    if entry is None:
        raise NotFound(f"Bilinmeyen komut: {name}")
    handler, needs_admin = entry
    if needs_admin:
        auth.require_admin(conn, os.environ.get(PIN_ENV))
    return handler(conn, payload)


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        _emit({"ok": False, "error": {"code": "USAGE", "message": "Kullanım: etkilesim <komut>"}})
        return 2
    name = args[0]
    if name == "daemon":
        logging_setup.configure(to_stderr=True)
        return asyncio.run(scheduler.run_daemon())
    logging_setup.configure()
    try:
        raw = sys.stdin.buffer.read().decode("utf-8") if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValidationFailed("Yük bir JSON nesnesi olmalı")
        conn = db.connect(config.db_path())
        try:
            data = dispatch(name, payload, conn)
        finally:
            conn.close()
    except EngineError as exc:
        log.warning("komut reddedildi: %s (%s)", name, exc.code)
        _emit({"ok": False, "error": {"code": exc.code, "message": exc.message}})
        return 1
    except json.JSONDecodeError:
        _emit({"ok": False, "error": {"code": "VALIDATION", "message": "Geçersiz JSON yükü"}})
        return 1
    except Exception as exc:
        log.exception("komut başarısız: %s", name)
        _emit(
            {
                "ok": False,
                "error": {"code": "INTERNAL", "message": f"Beklenmeyen hata ({exc.__class__.__name__})"},
            }
        )
        return 1
    _emit({"ok": True, "data": data})
    return 0
