"""v1 → güncel şema geçişi: veri korunur, bütünlük bozulmaz, yeni kısıtlar çalışır."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etkilesim import db, migrations

FIXTURE = Path(__file__).parent / "fixtures" / "schema_v1.sql"


def make_v1(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(FIXTURE.read_text(encoding="utf-8"))
    conn.executescript(
        """
        PRAGMA user_version=1;
        INSERT INTO teams(id,name,created_at) VALUES (1,'Marketing A','2026-01-01T00:00:00Z');
        INSERT INTO users(id,team_id,name,role,telegram_id,strike_count,status,created_at)
          VALUES (1,1,'Ayşe','member','111',2,'active','2026-01-01T00:00:00Z');
        INSERT INTO posts(id,user_id,platform,url,canonical_url,posted_at,created_at,updated_at)
          VALUES (1,1,'X','https://x.com/a/status/1','https://x.com/a/status/1',
                  '2026-01-02T00:00:00Z','2026-01-02T00:00:00Z','2026-01-02T00:00:00Z');
        INSERT INTO post_metric_snapshots(post_id,likes,source,captured_at)
          VALUES (1,5,'SCRAPE','2026-01-02T01:00:00Z');
        INSERT INTO notifications(user_id,kind,target,message,dedupe_key,created_at)
          VALUES (1,'strike','111','m','k1','2026-01-03T00:00:00Z');
        """
    )
    conn.commit()
    conn.close()


def test_v1_database_is_upgraded_without_losing_data(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    make_v1(path)
    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.LATEST
    user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    assert (user["name"], user["strike_count"], user["telegram_id"], user["email"]) == (
        "Ayşe",
        2,
        "111",
        None,
    )
    post = conn.execute("SELECT * FROM posts WHERE id=1").fetchone()
    assert post["content_type"] == "post" and post["campaign_id"] is None and post["archived_at"] is None
    assert conn.execute("SELECT likes FROM post_metric_snapshots").fetchone()[0] == 5
    assert conn.execute("SELECT channel FROM notifications").fetchone()[0] == "TELEGRAM"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_new_constraints_apply_after_upgrade(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    make_v1(path)
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO users(team_id,name,role,created_at) VALUES (1,'Gözlemci','viewer','2026-01-01T00:00:00Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO users(name,role,created_at) VALUES ('X','root','2026-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO post_metric_snapshots(post_id,likes,source,captured_at) VALUES (1,1,'MOCK','t')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE posts SET content_type='story' WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError):  # yabancı anahtarlar geçişten sonra yine açık
        conn.execute("UPDATE posts SET user_id=999 WHERE id=1")
    conn.close()


def test_fresh_and_upgraded_schemas_are_identical(tmp_path: Path) -> None:
    def shape(conn: sqlite3.Connection) -> list[tuple[str, str]]:
        rows = conn.execute(
            "SELECT m.name, p.name FROM sqlite_master m JOIN pragma_table_info(m.name) p"
            " WHERE m.type='table' ORDER BY m.name, p.cid"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    old = tmp_path / "old.db"
    make_v1(old)
    upgraded = db.connect(old)
    fresh = db.connect(tmp_path / "fresh.db")
    assert shape(upgraded) == shape(fresh)
    indexes = "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    assert [r[0] for r in upgraded.execute(indexes)] == [r[0] for r in fresh.execute(indexes)]


def test_reconnecting_does_not_reapply(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    db.connect(path).close()
    conn = sqlite3.connect(path)
    assert migrations.apply_pending(conn) == []
