"""Yönetici sistem ekranı (master prompt §56–60): işler, sağlayıcı sağlığı, denetim günlüğü, uyarı geçmişi.

Devre kesici durumları: OPEN = platform duraklatıldı; HALF_OPEN = duraklatma bitti, ilk deneme
bekleniyor (art arda engel sayacı sıfırlanmadı); CLOSED = normal.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from . import posts
from .clock import from_iso, now_utc, to_iso
from .db import audit
from .errors import ValidationFailed

JOB_NAMES = ("refresh", "strike_check", "discovery", "flush", "retention", "backup")
JOB_LABELS = {
    "refresh": "Etkileşim ölçümü",
    "strike_check": "Hareketsizlik kontrolü",
    "discovery": "Topluluk keşfi",
    "flush": "Bildirim gönderimi",
    "retention": "Saklama süresi temizliği",
    "backup": "Veritabanı yedeği",
}


def record_job(
    conn: sqlite3.Connection,
    name: str,
    trigger: str,
    work: Callable[[], str],
    now: Callable[[], datetime] = now_utc,
) -> dict[str, Any]:
    """İşi çalıştırır ve sonucu job_runs'a yazar; hata yutulmaz, kaydedilip yeniden fırlatılır."""
    if name not in JOB_NAMES:
        raise ValidationFailed("Bilinmeyen iş")
    cur = conn.execute(
        "INSERT INTO job_runs(name, started_at, trigger) VALUES (?,?,?)", (name, to_iso(now()), trigger)
    )
    job_id = int(cur.lastrowid or 0)
    try:
        detail = work()
    except Exception as exc:
        conn.execute(
            "UPDATE job_runs SET status='error', finished_at=?, detail=? WHERE id=?",
            (to_iso(now()), f"{exc.__class__.__name__}: {exc}"[:500], job_id),
        )
        raise
    conn.execute(
        "UPDATE job_runs SET status='ok', finished_at=?, detail=? WHERE id=?",
        (to_iso(now()), detail[:500], job_id),
    )
    return {"job_id": job_id, "detail": detail}


def jobs(conn: sqlite3.Connection, limit: int = 100) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    summary = {
        r["status"]: int(r["n"])
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM job_runs GROUP BY status").fetchall()
    }
    latest = {}
    for name in JOB_NAMES:
        row = conn.execute(
            "SELECT status, started_at, finished_at, detail, trigger FROM job_runs WHERE name=?"
            " ORDER BY id DESC LIMIT 1",
            (name,),
        ).fetchone()
        latest[name] = {"label": JOB_LABELS[name], **(dict(row) if row else {"status": None})}
    return {"items": [dict(r) for r in rows], "summary": summary, "latest": latest}


def provider_health(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict[str, Any]]:
    moment = now or now_utc()
    since = to_iso(moment - timedelta(days=7))
    stats = {
        r["platform"]: dict(r)
        for r in conn.execute(
            "SELECT platform, COUNT(*) AS attempts,"
            " SUM(CASE WHEN data_status IN ('OK','MANUAL') THEN 1 ELSE 0 END) AS ok"
            " FROM posts WHERE archived_at IS NULL AND last_attempt_at >= ? GROUP BY platform",
            (since,),
        ).fetchall()
    }
    due: dict[str, int] = {}
    for row in posts.due_posts(conn, moment, limit=10_000):
        due[row["platform"]] = due.get(row["platform"], 0) + 1
    states = {r["platform"]: dict(r) for r in conn.execute("SELECT * FROM provider_state").fetchall()}
    platforms = sorted(set(states) | set(stats) | set(due))
    result = []
    for platform in platforms:
        state = states.get(platform, {})
        paused_until = state.get("paused_until")
        paused = bool(paused_until) and from_iso(str(paused_until)) > moment
        blocks = int(state.get("consecutive_blocks") or 0)
        circuit = "OPEN" if paused else ("HALF_OPEN" if blocks > 0 else "CLOSED")
        attempts = int(stats.get(platform, {}).get("attempts") or 0)
        ok = int(stats.get(platform, {}).get("ok") or 0)
        result.append(
            {
                "platform": platform,
                "circuit": circuit,
                "paused_until": paused_until if paused else None,
                "consecutive_blocks": blocks,
                "success_rate": round(ok / attempts, 3) if attempts else None,
                "attempts_7d": attempts,
                "queue": due.get(platform, 0),
                "last_success_at": state.get("last_success_at"),
                "last_failure_at": state.get("last_failure_at"),
                "last_error": state.get("last_error"),
            }
        )
    return result


def audit_log(conn: sqlite3.Connection, limit: int = 200, action: str | None = None) -> list[dict[str, Any]]:
    if action:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE action LIKE ? ORDER BY id DESC LIMIT ?", (f"{action}%", limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["detail"] = json.loads(item.pop("detail_json") or "null")
        items.append(item)
    return items


def warning_history(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT e.id, e.strike_number, e.reason, e.triggered_at, e.resolved_at, u.name AS user_name,"
        " t.name AS team_name FROM strike_events e JOIN users u ON u.id=e.user_id"
        " LEFT JOIN teams t ON t.id=u.team_id ORDER BY e.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def metrics_text(conn: sqlite3.Connection, now: datetime | None = None) -> str:
    """Prometheus metin biçimi (master prompt §77): sayaçlar yerel veritabanından türetilir."""
    lines: list[str] = []

    def metric(name: str, help_text: str, kind: str, samples: list[tuple[dict[str, str], float]]) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            rendered = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{rendered}}} {value:g}" if rendered else f"{name} {value:g}")

    rows = conn.execute(
        "SELECT platform, COUNT(*) FROM posts WHERE archived_at IS NULL GROUP BY platform"
    ).fetchall()
    metric(
        "etkilesim_posts", "Takip edilen paylaşım sayısı", "gauge", [({"platform": r[0]}, r[1]) for r in rows]
    )
    rows = conn.execute("SELECT name, status, COUNT(*) FROM job_runs GROUP BY name, status").fetchall()
    job_samples: list[tuple[dict[str, str], float]] = [({"job": r[0], "status": r[1]}, r[2]) for r in rows]
    metric("etkilesim_job_runs_total", "İş çalıştırmaları", "counter", job_samples)
    rows = conn.execute(
        "SELECT channel, status, COUNT(*) FROM notifications GROUP BY channel, status"
    ).fetchall()
    metric(
        "etkilesim_notifications_total",
        "Bildirimler (kanal/durum)",
        "counter",
        [({"channel": r[0], "status": r[1]}, r[2]) for r in rows],
    )
    comments = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    metric("etkilesim_comments_analyzed_total", "Duygu analizi yapılan yorumlar", "counter", [({}, comments)])
    health = provider_health(conn, now)
    metric(
        "etkilesim_provider_circuit_open",
        "Platform devre kesici açık mı (1=OPEN)",
        "gauge",
        [({"platform": p["platform"]}, 1.0 if p["circuit"] == "OPEN" else 0.0) for p in health],
    )
    return "\n".join(lines) + "\n"


def retry_failed(conn: sqlite3.Connection, actor: str, now: datetime | None = None) -> dict[str, int]:
    """Başarısız bildirimleri yeniden kuyruğa alır; veri alınamayan gönderileri hemen ölçülecek yapar.

    Duraklatılmış (bot koruması) platformlar duraklatma bitene kadar yine denenmez.
    """
    moment = now or now_utc()
    notices = conn.execute(
        "UPDATE notifications SET status='pending', attempts=0, next_attempt_at=NULL WHERE status='failed'"
    ).rowcount
    measured = conn.execute(
        "UPDATE posts SET last_attempt_at=NULL WHERE archived_at IS NULL AND data_status='DATA_UNAVAILABLE'"
    ).rowcount
    audit(
        conn, actor, "system.retry_failed", None, None, {"notifications": notices, "posts": measured}, moment
    )
    return {"notifications": notices, "posts": measured}
