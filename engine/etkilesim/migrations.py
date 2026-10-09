"""Sürümlü şema geçişleri. `schema.sql` sürüm 1 temelidir ve DEĞİŞTİRİLMEZ.

Yeni kurulum da var olan veritabanı da aynı zincirden geçer (v1 → v2 → …), böylece iki yol asla
ayrışmaz. CHECK kısıtı değişen tablolar SQLite'ın önerdiği yöntemle yeniden kurulur:
yeni tablo → veriyi kopyala → eskiyi sil → yeniden adlandır (yabancı anahtarlar kapalıyken), ardından
`PRAGMA foreign_key_check` ile bütünlük doğrulanır.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

Migration = Callable[[sqlite3.Connection], None]


def _v2(conn: sqlite3.Connection) -> None:
    statements = [
        # --- Oyunlar ve kampanyalar (master prompt §9–10) ---
        """CREATE TABLE games (
          id             INTEGER PRIMARY KEY,
          name           TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) BETWEEN 1 AND 120),
          genres_json    TEXT NOT NULL DEFAULT '[]',
          keywords_json  TEXT NOT NULL DEFAULT '[]',
          languages_json TEXT NOT NULL DEFAULT '[]',
          website        TEXT,
          steam_url      TEXT,
          status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
          created_at     TEXT NOT NULL
        )""",
        """CREATE TABLE campaigns (
          id                    INTEGER PRIMARY KEY,
          game_id               INTEGER REFERENCES games(id) ON DELETE SET NULL,
          name                  TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) BETWEEN 1 AND 120),
          description           TEXT,
          start_date            TEXT,
          end_date              TEXT,
          status                TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('planned','active','finished','archived')),
          keywords_json         TEXT NOT NULL DEFAULT '[]',
          target_platforms_json TEXT NOT NULL DEFAULT '[]',
          created_at            TEXT NOT NULL
        )""",
        "CREATE INDEX campaigns_game ON campaigns(game_id)",
        # --- Gönderi: oyun, kampanya, içerik türü, arşiv (soft delete) ---
        "ALTER TABLE posts ADD COLUMN game_id INTEGER REFERENCES games(id) ON DELETE SET NULL",
        "ALTER TABLE posts ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL",
        "ALTER TABLE posts ADD COLUMN content_type TEXT NOT NULL DEFAULT 'post'"
        " CHECK (content_type IN ('post','video','image','poll','event','other'))",
        "ALTER TABLE posts ADD COLUMN archived_at TEXT",
        "CREATE INDEX posts_campaign ON posts(campaign_id)",
        "CREATE INDEX posts_game ON posts(game_id)",
        # --- Kullanıcı: e-posta + 'viewer' rolü (CHECK değiştiği için yeniden kurulur) ---
        """CREATE TABLE users_v2 (
          id             INTEGER PRIMARY KEY,
          team_id        INTEGER REFERENCES teams(id) ON DELETE SET NULL,
          name           TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) BETWEEN 1 AND 80),
          role           TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin','manager','member','viewer')),
          telegram_id    TEXT,
          email          TEXT,
          strike_count   INTEGER NOT NULL DEFAULT 0 CHECK (strike_count >= 0),
          total_strikes  INTEGER NOT NULL DEFAULT 0,
          last_post_at   TEXT,
          last_strike_at TEXT,
          status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','flagged','inactive')),
          flagged_at     TEXT,
          created_at     TEXT NOT NULL
        )""",
        "INSERT INTO users_v2(id,team_id,name,role,telegram_id,strike_count,total_strikes,last_post_at,"
        "last_strike_at,status,flagged_at,created_at) SELECT id,team_id,name,role,telegram_id,strike_count,"
        "total_strikes,last_post_at,last_strike_at,status,flagged_at,created_at FROM users",
        "DROP TABLE users",
        "ALTER TABLE users_v2 RENAME TO users",
        # --- Topluluk: dil, spam riski, son tarama ---
        "ALTER TABLE communities ADD COLUMN language TEXT",
        "ALTER TABLE communities ADD COLUMN spam_risk REAL",
        "ALTER TABLE communities ADD COLUMN last_scanned_at TEXT",
        "ALTER TABLE communities ADD COLUMN description TEXT",
        # --- Yorum konuları (master prompt §28) ---
        "ALTER TABLE comments ADD COLUMN topics_json TEXT NOT NULL DEFAULT '[]'",
        # --- Metrik kaynağına MOCK (geliştirme sağlayıcısı, §89) ---
        """CREATE TABLE post_metric_snapshots_v2 (
          id          INTEGER PRIMARY KEY,
          post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
          likes       INTEGER,
          comments    INTEGER,
          shares      INTEGER,
          views       INTEGER,
          source      TEXT NOT NULL CHECK (source IN ('SCRAPE','HTTP','MANUAL','MOCK')),
          captured_at TEXT NOT NULL,
          UNIQUE (post_id, captured_at)
        )""",
        "INSERT INTO post_metric_snapshots_v2 SELECT id,post_id,likes,comments,shares,views,source,captured_at"
        " FROM post_metric_snapshots",
        "DROP TABLE post_metric_snapshots",
        "ALTER TABLE post_metric_snapshots_v2 RENAME TO post_metric_snapshots",
        "CREATE INDEX snapshots_post_time ON post_metric_snapshots(post_id, captured_at)",
        # --- Bildirim kanalı + uygulama içi gelen kutusu (§39–42) ---
        "ALTER TABLE notifications ADD COLUMN channel TEXT NOT NULL DEFAULT 'TELEGRAM'"
        " CHECK (channel IN ('TELEGRAM','EMAIL','TEAMS'))",
        """CREATE TABLE inbox (
          id         INTEGER PRIMARY KEY,
          user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
          audience   TEXT NOT NULL DEFAULT 'user' CHECK (audience IN ('user','admin')),
          kind       TEXT NOT NULL,
          title      TEXT NOT NULL,
          body       TEXT NOT NULL,
          dedupe_key TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL,
          read_at    TEXT
        )""",
        "CREATE INDEX inbox_user_read ON inbox(user_id, read_at)",
        "CREATE INDEX inbox_audience_read ON inbox(audience, read_at)",
        # --- İş kayıtları: tetikleyici (zamanlayıcı / elle) ---
        "ALTER TABLE job_runs ADD COLUMN trigger TEXT NOT NULL DEFAULT 'schedule'"
        " CHECK (trigger IN ('schedule','manual'))",
        "CREATE INDEX job_runs_name_time ON job_runs(name, started_at)",
    ]
    for statement in statements:
        conn.execute(statement)


MIGRATIONS: dict[int, Migration] = {2: _v2}
LATEST = max(MIGRATIONS)


def apply_pending(conn: sqlite3.Connection) -> list[int]:
    """Bekleyen geçişleri sırayla uygular; uygulanan sürümleri döndürür. Her sürüm tek işlemdir."""
    applied: list[int] = []
    while True:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        target = current + 1
        if target not in MIGRATIONS:
            return applied
        conn.execute("PRAGMA foreign_keys=OFF")  # işlem dışında ayarlanmalı
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Başka bir süreç bu arada geçirdiyse tekrar etme.
                if int(conn.execute("PRAGMA user_version").fetchone()[0]) != current:
                    conn.execute("ROLLBACK")
                    continue
                MIGRATIONS[target](conn)
                problems = conn.execute("PRAGMA foreign_key_check").fetchall()
                if problems:
                    raise sqlite3.IntegrityError(f"v{target} geçişi yabancı anahtar bütünlüğünü bozdu")
                conn.execute(f"PRAGMA user_version={target}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        applied.append(target)
