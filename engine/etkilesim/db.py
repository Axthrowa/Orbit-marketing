"""SQLite bağlantısı (WAL), şema başlatma ve denetim kaydı."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from importlib import resources
from pathlib import Path

from . import migrations
from .clock import now_utc, to_iso

BASE_VERSION = 1  # schema.sql
SCHEMA_VERSION = migrations.LATEST


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Boş veritabanına v1 temelini kurar, ardından bekleyen tüm geçişleri uygular."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version >= SCHEMA_VERSION:
        return
    if version < BASE_VERSION:
        script = resources.files("etkilesim").joinpath("schema.sql").read_text(encoding="utf-8")
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Başka bir süreç bu arada kurduysa tekrar kurma.
            if int(conn.execute("PRAGMA user_version").fetchone()[0]) < BASE_VERSION:
                for statement in _split_statements(script):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version={BASE_VERSION}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    migrations.apply_pending(conn)


def _split_statements(script: str) -> list[str]:
    """Satır satır biriktirir; yorumlardaki ';' ifadeyi bölmez."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines():
        if not buffer and (not line.strip() or line.strip().startswith("--")):
            continue
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError("schema.sql: tamamlanmamış ifade")
    return statements


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE: yazma yarışlarını (daemon + arayüz) sıraya sokar.

    Zaten açık bir işlem varsa (ör. tohum verisi) iç içe açmaz; dıştaki işlemin parçası olur ve
    hata dışarı yayılıp dıştaki işlemi geri alır.
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    entity: str | None = None,
    entity_id: str | int | None = None,
    detail: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor, action, entity, entity_id, detail_json, at) VALUES (?,?,?,?,?,?)",
        (
            actor,
            action,
            entity,
            None if entity_id is None else str(entity_id),
            json.dumps(dict(detail), ensure_ascii=False) if detail else None,
            to_iso(now or now_utc()),
        ),
    )
