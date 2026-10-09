"""Bakım işleri (master prompt §63, §69, §93): saklama süresi, dışa aktarım, yedekleme.

- Saklama: yorum METNİ süresi dolunca silinir (duygu etiketi ve sayılar kalır); denetim kayıtları,
  okunmuş gelen kutusu ve iş geçmişi süreyle temizlenir. Metrikler süresiz saklanır.
- Dışa aktarım: CSV / XLSX / JSON. Hücreler formül enjeksiyonuna karşı korunur (=, +, -, @ önüne ').
- Yedekleme: SQLite çevrimiçi yedekleme API'si (WAL ile güvenli); en yeni N yedek tutulur.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import analytics, config, settings
from .clock import now_utc, to_iso
from .db import audit
from .errors import ValidationFailed

FORMATS = ("csv", "xlsx", "json")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
REDACTED_TEXT = "[saklama süresi doldu]"


def apply_retention(
    conn: sqlite3.Connection, now: datetime | None = None, actor: str = "system"
) -> dict[str, int]:
    moment = now or now_utc()
    result: dict[str, int] = {}
    comment_days = int(settings.get(conn, "comment_retention_days"))
    if comment_days > 0:
        cutoff = to_iso(moment - timedelta(days=comment_days))
        result["comment_texts"] = conn.execute(
            "UPDATE comments SET text=? WHERE collected_at < ? AND text <> ?",
            (REDACTED_TEXT, cutoff, REDACTED_TEXT),
        ).rowcount
    audit_days = int(settings.get(conn, "audit_retention_days"))
    if audit_days > 0:
        cutoff = to_iso(moment - timedelta(days=audit_days))
        result["audit"] = conn.execute("DELETE FROM audit_log WHERE at < ?", (cutoff,)).rowcount
    housekeeping = to_iso(moment - timedelta(days=90))
    result["inbox"] = conn.execute(
        "DELETE FROM inbox WHERE read_at IS NOT NULL AND read_at < ?", (housekeeping,)
    ).rowcount
    result["job_runs"] = conn.execute("DELETE FROM job_runs WHERE started_at < ?", (housekeeping,)).rowcount
    audit(conn, actor, "maintenance.retention", None, None, dict(result), moment)
    return result


# ------------------------------------------------------------------------------------ dışa aktarım


def _safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _datasets(conn: sqlite3.Connection, now: datetime) -> dict[str, list[dict[str, Any]]]:
    post_rows = conn.execute(
        "SELECT p.id, u.name AS kisi, t.name AS ekip, p.platform, p.content_type AS icerik_turu, p.url,"
        " c.name AS topluluk, g.name AS oyun, k.name AS kampanya, p.posted_at AS paylasim_tarihi,"
        " p.current_likes AS begeni, p.comments_count AS yorum, p.shares_count AS paylasim,"
        " p.views_count AS izlenme, p.positive_sentiment_ratio AS olumlu_oran,"
        " p.negative_sentiment_ratio AS olumsuz_oran, p.data_status AS veri_durumu, p.note AS sayfa_notu"
        " FROM posts p JOIN users u ON u.id=p.user_id LEFT JOIN teams t ON t.id=u.team_id"
        " LEFT JOIN communities c ON c.id=p.community_id LEFT JOIN games g ON g.id=p.game_id"
        " LEFT JOIN campaigns k ON k.id=p.campaign_id WHERE p.archived_at IS NULL ORDER BY p.posted_at DESC"
    ).fetchall()
    board = analytics.leaderboard(conn, analytics.Filters(days=30), now)
    communities = conn.execute(
        "SELECT name AS topluluk, platform, url, member_count AS uye, language AS dil, status AS durum,"
        " relevance_score AS skor FROM communities ORDER BY name_key"
    ).fetchall()
    return {
        "paylasimlar": [dict(r) for r in post_rows],
        "liderlik_30_gun": [
            {k: v for k, v in row.items() if k != "components"}
            | {"bilesenler": json.dumps(row["components"])}
            for row in board
        ],
        "topluluklar": [dict(r) for r in communities],
    }


def export(
    conn: sqlite3.Connection,
    fmt: str,
    out_dir: Path | None = None,
    now: datetime | None = None,
    actor: str = "admin",
) -> dict[str, Any]:
    if fmt not in FORMATS:
        raise ValidationFailed("Biçim csv, xlsx veya json olmalı")
    moment = now or now_utc()
    directory = out_dir or (Path.home() / "Downloads")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = moment.astimezone().strftime("%Y%m%d-%H%M%S")
    data = _datasets(conn, moment)
    path = directory / f"etkilesim-takip-{stamp}.{fmt}"
    if fmt == "json":
        meta = {"olusturuldu": to_iso(moment), "uygulama": "Etkileşim Takip", "created_by": "axthrowa"}
        path.write_text(json.dumps({"meta": meta, **data}, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        rows = data["paylasimlar"]
        # Excel'in Türkçe karakterleri doğru açması için BOM'lu UTF-8, ayırıcı noktalı virgül.
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["id"], delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _safe(v) for k, v in row.items()})
    else:
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.remove(workbook.active)
        for name, rows in data.items():
            sheet = workbook.create_sheet(title=name[:31])
            headers = list(rows[0]) if rows else ["(boş)"]
            sheet.append(headers)
            for row in rows:
                sheet.append([_safe(row.get(h)) for h in headers])
        workbook.properties.creator = "created by axthrowa"
        workbook.save(path)
    counts = {k: len(v) for k, v in data.items()}
    audit(conn, actor, "maintenance.export", None, None, {"format": fmt, **counts}, moment)
    return {"path": str(path), "rows": counts}


# --------------------------------------------------------------------------------------- yedekleme


def backup(
    conn: sqlite3.Connection, dest_dir: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    moment = now or now_utc()
    directory = dest_dir or (config.data_dir() / "backups")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"etkilesim-{moment.astimezone().strftime('%Y%m%d-%H%M%S')}.db"
    target = sqlite3.connect(path)
    try:
        conn.backup(target)
    finally:
        target.close()
    keep = int(settings.get(conn, "backup_keep"))
    removed = 0
    for old in sorted(directory.glob("etkilesim-*.db"))[:-keep]:
        old.unlink()
        removed += 1
    return {
        "path": str(path),
        "removed": removed,
        "kept": min(keep, len(list(directory.glob("etkilesim-*.db")))),
    }
