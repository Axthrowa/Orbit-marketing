"""Hareketsizlik motoru: eşik → uyarı 1..N → işaretle (flagged) + yönetici bildirimi.

Tüm eşikler yönetici ayarıdır (genel veya ekip bazlı). Aynı kontrol iki kez çalışsa da
aynı uyarı iki kez oluşmaz: (kullanıcı, döngü anahtarı, uyarı no) tekildir ve uyarılar
arası süre `strike_interval_hours` ile denetlenir. Test saati `now` parametresidir.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import inbox, notify, settings
from .clock import from_iso, now_utc, to_iso
from .db import audit, transaction

# Gece 00:00 kontrolü ile 24 saatlik aralık arasındaki saniye sapmalarını tolere eder.
INTERVAL_TOLERANCE = timedelta(minutes=5)
STRIKE_KINDS = ("strike", "flag")


@dataclass(frozen=True)
class StrikeOutcome:
    user_id: int
    user_name: str
    strike_number: int
    flagged: bool


def _idle_text(idle: timedelta) -> str:
    days = idle.days
    hours = idle.seconds // 3600
    return f"{days} gün {hours} saat" if hours else f"{days} gün"


def run_inactivity_check(conn: sqlite3.Connection, now: datetime | None = None) -> list[StrikeOutcome]:
    moment = now or now_utc()
    outcomes: list[StrikeOutcome] = []
    users = conn.execute(
        "SELECT u.*, t.name AS team_name, t.chat_id AS team_chat FROM users u"
        " LEFT JOIN teams t ON t.id=u.team_id WHERE u.status='active' ORDER BY u.id"
    ).fetchall()
    admin_chat = str(settings.get(conn, "admin_chat_id") or "")
    for user in users:
        team_id = user["team_id"]
        threshold = timedelta(days=int(settings.get(conn, "inactivity_days", team_id)))
        interval = timedelta(hours=int(settings.get(conn, "strike_interval_hours", team_id)))
        max_strikes = int(settings.get(conn, "max_strikes", team_id))
        cycle_key = str(user["last_post_at"] or user["created_at"])
        idle = moment - from_iso(cycle_key)
        if idle < threshold:
            continue
        last_strike = user["last_strike_at"]
        if last_strike and moment - from_iso(last_strike) < interval - INTERVAL_TOLERANCE:
            continue
        number = int(user["strike_count"]) + 1
        if number > max_strikes:
            continue
        with transaction(conn):
            inserted = conn.execute(
                "INSERT OR IGNORE INTO strike_events(user_id,strike_number,cycle_key,reason,"
                "triggered_at) VALUES (?,?,?,?,?)",
                (user["id"], number, cycle_key, f"{_idle_text(idle)} paylaşım yok", to_iso(moment)),
            )
            if not inserted.rowcount:
                continue
            flagged = number >= max_strikes
            conn.execute(
                "UPDATE users SET strike_count=?, total_strikes=total_strikes+1,"
                " last_strike_at=?, status=?, flagged_at=? WHERE id=?",
                (
                    number,
                    to_iso(moment),
                    "flagged" if flagged else "active",
                    to_iso(moment) if flagged else None,
                    user["id"],
                ),
            )
            message = (
                f"⚠️ {user['name']}: {_idle_text(idle)}dir yeni paylaşım linki eklemedin. "
                f"Uyarı {number}/{max_strikes}."
            )
            base = f"strike:{user['id']}:{cycle_key}:{number}"
            targets: list[tuple[str, str | None]] = [("TELEGRAM", user["telegram_id"])]
            if "EMAIL" in notify.enabled_channels(conn):
                targets.append(("EMAIL", user["email"]))
            notify.fan_out(conn, "strike", message, base, user["id"], targets, moment)
            inbox.add(
                conn,
                "user",
                user["id"],
                "strike",
                f"Paylaşım hatırlatması {number}/{max_strikes}",
                message,
                f"inbox:{base}",
                moment,
            )
            if flagged:
                _escalate(conn, user, idle, max_strikes, admin_chat, cycle_key, moment)
            audit(
                conn,
                "system",
                "strike.issued",
                "user",
                user["id"],
                {"number": number, "flagged": flagged},
                moment,
            )
        outcomes.append(StrikeOutcome(int(user["id"]), str(user["name"]), number, flagged))
    return outcomes


def _escalate(
    conn: sqlite3.Connection,
    user: sqlite3.Row,
    idle: timedelta,
    max_strikes: int,
    admin_chat: str,
    cycle_key: str,
    moment: datetime,
) -> None:
    team = user["team_name"] or "Ekipsiz"
    text = (
        "🚨 KRİTİK AKTİVİTE UYARISI\n"
        f"Kullanıcı: {user['name']}\nEkip: {team}\n"
        f"Son paylaşım: {_idle_text(idle)} önce\n"
        f"Gönderilen uyarılar: {max_strikes}/{max_strikes}\n"
        "Durum: YÖNETİCİ İNCELEMESİ GEREKİYOR"
    )
    targets = {t for t in (admin_chat, str(user["team_chat"] or "")) if t}
    if not targets:
        notify.queue(conn, "flag", None, text, f"flag:{user['id']}:{cycle_key}:none", user["id"], moment)
    for target in sorted(targets):
        notify.queue(
            conn, "flag", target, text, f"flag:{user['id']}:{cycle_key}:{target}", user["id"], moment
        )
    channels = notify.enabled_channels(conn)
    extra: list[tuple[str, str | None]] = []
    if "EMAIL" in channels:
        extra.append(("EMAIL", str(settings.get(conn, "admin_email")) or None))
    if "TEAMS" in channels:
        extra.append(("TEAMS", "workflow"))
    notify.fan_out(conn, "flag", text, f"flag:{user['id']}:{cycle_key}", user["id"], extra, moment)
    inbox.add(
        conn,
        "admin",
        user["id"],
        "flag",
        f"{user['name']} yönetici incelemesi bekliyor",
        text,
        f"inbox:flag:{user['id']}:{cycle_key}",
        moment,
    )


def reset_user(
    conn: sqlite3.Connection, user_id: int, now: datetime | None = None, actor: str = "system"
) -> None:
    """Yeni geçerli paylaşımda: sayaç ve işaret sıfırlanır; geçmiş kayıtlar SİLİNMEZ."""
    moment = now or now_utc()
    pending = conn.execute(
        "SELECT (SELECT strike_count > 0 OR status = 'flagged' FROM users WHERE id=?)"
        " OR EXISTS(SELECT 1 FROM strike_events WHERE user_id=? AND resolved_at IS NULL)",
        (user_id, user_id),
    ).fetchone()[0]
    if not pending:
        return  # sıfırlanacak bir şey yok; gürültülü denetim kaydı yazma
    conn.execute(
        "UPDATE users SET strike_count=0, status='active', flagged_at=NULL, last_strike_at=NULL"
        " WHERE id=? AND status IN ('active','flagged')",
        (user_id,),
    )
    conn.execute(
        "UPDATE strike_events SET resolved_at=? WHERE user_id=? AND resolved_at IS NULL",
        (to_iso(moment), user_id),
    )
    cancelled = notify.cancel_pending(conn, user_id, STRIKE_KINDS, "Kullanıcı yeniden paylaşım yaptı")
    audit(conn, actor, "strike.reset", "user", user_id, {"cancelled_notifications": cancelled}, moment)
