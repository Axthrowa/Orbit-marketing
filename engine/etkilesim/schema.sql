-- Etkileşim Takip şeması (SQLite, WAL). created by axthrowa
-- Zamanlar UTC ISO-8601 ("YYYY-MM-DDTHH:MM:SSZ"). Bilinmeyen sayaç = NULL (0 DEĞİL).

CREATE TABLE teams (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) BETWEEN 1 AND 80),
  chat_id     TEXT,                       -- ekip yöneticilerinin Telegram sohbeti (opsiyonel)
  created_at  TEXT NOT NULL
);

CREATE TABLE users (
  id             INTEGER PRIMARY KEY,
  team_id        INTEGER REFERENCES teams(id) ON DELETE SET NULL,
  name           TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) BETWEEN 1 AND 80),
  role           TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin','manager','member')),
  telegram_id    TEXT,
  strike_count   INTEGER NOT NULL DEFAULT 0 CHECK (strike_count >= 0),
  total_strikes  INTEGER NOT NULL DEFAULT 0,
  last_post_at   TEXT,
  last_strike_at TEXT,
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','flagged','inactive')),
  flagged_at     TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE communities (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 160),
  name_key        TEXT NOT NULL,          -- normalize edilmiş ad (r/ öneki atılmış, küçük harf)
  platform        TEXT NOT NULL DEFAULT 'Other',
  url             TEXT UNIQUE,
  category        TEXT,
  member_count    INTEGER,                -- bilinmiyorsa NULL
  status          TEXT NOT NULL DEFAULT 'discovered'
                  CHECK (status IN ('discovered','approved','blocked')),
  favorite        INTEGER NOT NULL DEFAULT 0,
  relevance_score REAL,
  activity_score  REAL,
  reason          TEXT,
  discovered_at   TEXT NOT NULL
);
CREATE INDEX communities_name_key ON communities(name_key);

CREATE TABLE posts (
  id                       INTEGER PRIMARY KEY,
  user_id                  INTEGER NOT NULL REFERENCES users(id),
  community_id             INTEGER REFERENCES communities(id) ON DELETE SET NULL,
  platform                 TEXT NOT NULL
                           CHECK (platform IN ('X','Instagram','Facebook','Threads','Reddit',
                                               'YouTube','Forum','Other')),
  url                      TEXT NOT NULL,
  canonical_url            TEXT NOT NULL,
  platform_post_id         TEXT,
  initial_likes            INTEGER,
  current_likes            INTEGER,
  comments_count           INTEGER,
  shares_count             INTEGER,
  views_count              INTEGER,
  positive_sentiment_ratio REAL,
  negative_sentiment_ratio REAL,
  neutral_sentiment_ratio  REAL,
  sentiment_sample         INTEGER NOT NULL DEFAULT 0,
  data_status              TEXT NOT NULL DEFAULT 'PENDING'
                           CHECK (data_status IN ('PENDING','OK','DATA_UNAVAILABLE',
                                                  'AUTHORIZATION_REQUIRED','MANUAL')),
  last_error               TEXT,
  note                     TEXT,
  preview_text             TEXT,
  last_metrics_at          TEXT,                   -- son BAŞARILI ölçüm
  last_attempt_at          TEXT,                   -- son deneme (başarısız dahil)
  posted_at                TEXT NOT NULL,
  created_at               TEXT NOT NULL,
  updated_at               TEXT NOT NULL,
  UNIQUE (user_id, canonical_url)
);
CREATE INDEX posts_user ON posts(user_id);
CREATE INDEX posts_platform ON posts(platform);
CREATE INDEX posts_created ON posts(created_at);
CREATE INDEX posts_due ON posts(data_status, last_attempt_at);

-- Zaman serisi: ölçümler asla üzerine yazılmaz.
CREATE TABLE post_metric_snapshots (
  id          INTEGER PRIMARY KEY,
  post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  likes       INTEGER,
  comments    INTEGER,
  shares      INTEGER,
  views       INTEGER,
  source      TEXT NOT NULL CHECK (source IN ('SCRAPE','HTTP','MANUAL')),
  captured_at TEXT NOT NULL,
  UNIQUE (post_id, captured_at)
);
CREATE INDEX snapshots_post_time ON post_metric_snapshots(post_id, captured_at);

-- Yorum yazarı bilerek SAKLANMAZ (gizlilik); yalnızca metin + duygu sonucu.
CREATE TABLE comments (
  id           INTEGER PRIMARY KEY,
  post_id      INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  text_hash    TEXT NOT NULL,
  text         TEXT NOT NULL,
  language     TEXT,
  label        TEXT NOT NULL CHECK (label IN ('POSITIVE','NEUTRAL','NEGATIVE','MIXED','UNKNOWN')),
  positive     REAL NOT NULL,
  neutral      REAL NOT NULL,
  negative     REAL NOT NULL,
  engine       TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  UNIQUE (post_id, text_hash)
);
CREATE INDEX comments_post ON comments(post_id);

CREATE TABLE community_logs (
  id                INTEGER PRIMARY KEY,
  community_id      INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
  user_id           INTEGER NOT NULL REFERENCES users(id),
  post_id           INTEGER REFERENCES posts(id) ON DELETE SET NULL,
  post_url          TEXT NOT NULL,
  post_preview_text TEXT NOT NULL DEFAULT '',
  posted_at         TEXT NOT NULL,
  UNIQUE (post_id)
);
CREATE INDEX community_logs_time ON community_logs(community_id, posted_at);

-- Aynı uyarı iki kez sayılmaz: (kullanıcı, döngü anahtarı, uyarı no) tekil.
CREATE TABLE strike_events (
  id              INTEGER PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id),
  strike_number   INTEGER NOT NULL,
  cycle_key       TEXT NOT NULL,          -- ilgili hareketsizlik döngüsünün başlangıcı (son paylaşım)
  reason          TEXT NOT NULL,
  triggered_at    TEXT NOT NULL,
  resolved_at     TEXT,
  UNIQUE (user_id, cycle_key, strike_number)
);

CREATE TABLE notifications (
  id              INTEGER PRIMARY KEY,
  user_id         INTEGER REFERENCES users(id),
  kind            TEXT NOT NULL,
  target          TEXT,                   -- Telegram chat id; NULL = hedef tanımsız
  message         TEXT NOT NULL,
  dedupe_key      TEXT NOT NULL UNIQUE,
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','sent','failed','suppressed','no_target')),
  attempts        INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error      TEXT,
  created_at      TEXT NOT NULL,
  sent_at         TEXT
);
CREATE INDEX notifications_status ON notifications(status, next_attempt_at);

CREATE TABLE provider_state (
  platform            TEXT PRIMARY KEY,
  consecutive_blocks  INTEGER NOT NULL DEFAULT 0,
  paused_until        TEXT,
  last_success_at     TEXT,
  last_failure_at     TEXT,
  last_error          TEXT
);

CREATE TABLE settings (
  scope      TEXT NOT NULL,               -- 'global' | 'team:<id>' | 'secure'
  key        TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (scope, key)
);

CREATE TABLE job_runs (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  status      TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','error')),
  detail      TEXT
);

CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  entity      TEXT,
  entity_id   TEXT,
  detail_json TEXT,
  at          TEXT NOT NULL
);
