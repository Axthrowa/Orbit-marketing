from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from etkilesim import community, people, posts, settings
from etkilesim.errors import UnsafeUrl, ValidationFailed
from etkilesim.models import CollectResult, Metrics
from etkilesim.sentiment import LexiconEngine

from .helpers import make_user, public_resolver

ENGINE = LexiconEngine()


def add(conn: sqlite3.Connection, uid: int, url: str, t: datetime, **kw: object) -> posts.AddPostResult:
    return posts.add_post(conn, uid, url, now=t, resolver=public_resolver, **kw)  # type: ignore[arg-type]


def test_add_post_detects_platform_and_updates_user(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    res = add(conn, uid, "https://twitter.com/foo/status/77?s=20", t0)
    assert res.created and res.platform == "X"
    post = conn.execute("SELECT * FROM posts WHERE id=?", (res.post_id,)).fetchone()
    assert post["canonical_url"] == "https://x.com/foo/status/77"
    assert post["platform_post_id"] == "77"
    assert post["data_status"] == "PENDING"
    assert post["current_likes"] is None  # bilinmeyen ≠ 0
    assert conn.execute("SELECT last_post_at FROM users").fetchone()[0] == "2026-10-01T12:00:00Z"


def test_duplicate_post_is_idempotent(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    a = add(conn, uid, "https://x.com/foo/status/77", t0)
    b = add(conn, uid, "https://www.twitter.com/foo/status/77/?t=zz", t0)
    assert a.created and not b.created and a.post_id == b.post_id
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 1


@pytest.mark.parametrize("url", ["http://localhost/a", "http://169.254.169.254/", "file:///x"])
def test_add_post_rejects_unsafe_urls(conn: sqlite3.Connection, t0: datetime, url: str) -> None:
    uid = make_user(conn, now=t0)
    with pytest.raises(UnsafeUrl):
        add(conn, uid, url, t0)
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0


def test_future_posted_at_rejected(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    with pytest.raises(ValidationFailed):
        add(conn, uid, "https://x.com/a/status/1", t0, posted_at="2027-01-01")


def test_backdated_old_post_does_not_reset_strikes(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    conn.execute(
        "UPDATE users SET strike_count=2, last_strike_at=? WHERE id=?", ("2026-09-30T00:00:00Z", uid)
    )
    add(conn, uid, "https://x.com/a/status/9", t0, posted_at="2026-08-01")
    assert conn.execute("SELECT strike_count FROM users").fetchone()[0] == 2


def test_metrics_snapshots_are_time_series(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0).post_id
    first = CollectResult("OK", Metrics(likes=10, comments=2, views=500), source="SCRAPE")
    posts.record_collect(conn, pid, first, ENGINE, t0)
    second = CollectResult("OK", Metrics(likes=25, comments=4, views=None), source="SCRAPE")
    posts.record_collect(conn, pid, second, ENGINE, t0 + timedelta(hours=6))
    post = conn.execute("SELECT * FROM posts").fetchone()
    assert post["initial_likes"] == 10 and post["current_likes"] == 25
    assert post["views_count"] == 500  # None yeni ölçümde eski değeri silmez
    assert post["data_status"] == "OK"
    assert conn.execute("SELECT COUNT(*) FROM post_metric_snapshots").fetchone()[0] == 2


def test_same_snapshot_moment_is_not_stored_twice(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0).post_id
    result = CollectResult("OK", Metrics(likes=1), source="SCRAPE")
    posts.record_collect(conn, pid, result, ENGINE, t0)
    posts.record_collect(conn, pid, result, ENGINE, t0)
    assert conn.execute("SELECT COUNT(*) FROM post_metric_snapshots").fetchone()[0] == 1


def test_provider_failure_keeps_post_and_old_values(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0).post_id
    posts.record_collect(conn, pid, CollectResult("OK", Metrics(likes=10)), ENGINE, t0)
    fail = CollectResult("DATA_UNAVAILABLE", error="Sayfa yüklenemedi")
    posts.record_collect(conn, pid, fail, ENGINE, t0 + timedelta(hours=6))
    post = conn.execute("SELECT * FROM posts").fetchone()
    assert post["data_status"] == "DATA_UNAVAILABLE"
    assert post["current_likes"] == 10
    assert post["last_metrics_at"] == "2026-10-01T12:00:00Z"  # son BAŞARILI ölçüm korunur
    assert post["last_attempt_at"] == "2026-10-01T18:00:00Z"


def test_auth_required_status(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://www.instagram.com/p/AbC/", t0).post_id
    posts.record_collect(conn, pid, CollectResult("AUTHORIZATION_REQUIRED", blocked=False), ENGINE, t0)
    assert conn.execute("SELECT data_status FROM posts").fetchone()[0] == "AUTHORIZATION_REQUIRED"


def test_comments_are_deduped_and_analyzed_once(conn: sqlite3.Connection, t0: datetime) -> None:
    calls: list[int] = []

    class Counting:
        name = "counting"

        def analyze(self, texts: list[str]):  # type: ignore[no-untyped-def]
            calls.append(len(texts))
            return LexiconEngine().analyze(texts)

    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0).post_id
    texts = ["Harika oyun!", "berbat", "fiyatı ne kadar", "harika oyun!  ", "follow me for free robux"]
    res = CollectResult("OK", Metrics(likes=1), comment_texts=texts)
    posts.record_collect(conn, pid, res, Counting(), t0)  # type: ignore[arg-type]
    posts.record_collect(conn, pid, res, Counting(), t0 + timedelta(hours=6))  # type: ignore[arg-type]
    assert calls == [4]  # ikinci turda yeniden analiz yok
    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 4
    post = conn.execute("SELECT * FROM posts").fetchone()
    assert post["sentiment_sample"] == 3  # spam hariç
    assert post["positive_sentiment_ratio"] == pytest.approx(1 / 3, abs=0.001)
    assert post["negative_sentiment_ratio"] == pytest.approx(1 / 3, abs=0.001)


def test_comment_mentions_are_masked_in_storage(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0).post_id
    posts.add_manual_comments(conn, pid, ["@ahmet_123 süper oyun"], ENGINE, "u", t0)
    assert "ahmet_123" not in conn.execute("SELECT text FROM comments").fetchone()[0]


def test_manual_metrics_flow(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://www.facebook.com/groups/x/posts/5", t0).post_id
    with pytest.raises(ValidationFailed):
        posts.set_manual_metrics(conn, pid, None, "", None, None, "u", t0)
    with pytest.raises(ValidationFailed):
        posts.set_manual_metrics(conn, pid, -5, None, None, None, "u", t0)
    posts.set_manual_metrics(conn, pid, 12, 3, None, None, "u", t0)
    post = conn.execute("SELECT * FROM posts").fetchone()
    assert (post["current_likes"], post["comments_count"], post["views_count"]) == (12, 3, None)
    assert post["data_status"] == "MANUAL"
    # Otomatik ölçüm sonradan başarısız olsa da elle veri etiketi kalır.
    posts.record_collect(conn, pid, CollectResult("AUTHORIZATION_REQUIRED"), ENGINE, t0)
    assert conn.execute("SELECT data_status FROM posts").fetchone()[0] == "MANUAL"


def test_due_posts_schedule(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0).post_id
    assert [r["id"] for r in posts.due_posts(conn, t0)] == [pid]  # hiç denenmedi → hemen
    posts.record_collect(conn, pid, CollectResult("OK", Metrics(likes=1)), ENGINE, t0)
    assert posts.due_posts(conn, t0 + timedelta(hours=5)) == []
    assert len(posts.due_posts(conn, t0 + timedelta(hours=6))) == 1
    settings.set_value(conn, "metrics_interval_hours", 1, "admin")
    assert len(posts.due_posts(conn, t0 + timedelta(hours=1))) == 1


def test_auth_required_posts_back_off_to_a_day(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://www.instagram.com/p/AbC/", t0).post_id
    posts.record_collect(conn, pid, CollectResult("AUTHORIZATION_REQUIRED"), ENGINE, t0)
    assert posts.due_posts(conn, t0 + timedelta(hours=12)) == []
    assert len(posts.due_posts(conn, t0 + timedelta(hours=24))) == 1


# --- topluluk geçmişi -------------------------------------------------------------------------


def test_unknown_community_is_clean(conn: sqlite3.Connection, t0: datetime) -> None:
    ctx = community.posting_context(conn, name="r/IndieGaming", now=t0)
    assert ctx["recommendation"] == "CLEAN" and ctx["last_post"] is None
    assert "Temiz" in ctx["message"]


def test_posting_context_returns_last_post_details(conn: sqlite3.Connection, t0: datetime) -> None:
    mehmet = make_user(conn, "Mehmet", now=t0)
    ayse = make_user(conn, "Ayşe", "Marketing B", now=t0)
    long_text = "After three years of development " + "x" * 300
    add(
        conn,
        mehmet,
        "https://x.com/m/status/1",
        t0 - timedelta(days=9),
        community_name="r/IndieGaming",
        preview_text=long_text,
    )
    add(
        conn,
        ayse,
        "https://x.com/a/status/2",
        t0 - timedelta(days=4),
        community_name="indiegaming",
        preview_text="Yeni demo yayında",
    )
    ctx = community.posting_context(conn, name="R/IndieGaming ", now=t0)
    assert ctx["previous_posts"] == 2
    assert ctx["days_since_last_post"] == 4
    assert ctx["last_post"]["user"] == "Ayşe"
    assert ctx["last_post"]["team"] == "Marketing B"
    assert ctx["last_post"]["preview"] == "Yeni demo yayında"
    assert ctx["recommendation"] == "RECENTLY_USED"
    assert len(ctx["recent_posts"]) == 2
    older = ctx["recent_posts"][1]["preview"]
    assert len(older) == 150 and older.startswith("After three years")


@pytest.mark.parametrize(
    ("days", "tier"),
    [
        (0, "AVOID"),
        (3, "AVOID"),
        (4, "RECENTLY_USED"),
        (7, "RECENTLY_USED"),
        (8, "CAUTION"),
        (14, "CAUTION"),
        (15, "SAFE"),
        (60, "SAFE"),
    ],
)
def test_recommendation_tiers(conn: sqlite3.Connection, t0: datetime, days: int, tier: str) -> None:
    uid = make_user(conn, now=t0 - timedelta(days=100))
    add(conn, uid, "https://x.com/a/status/1", t0 - timedelta(days=days), community_name="Topluluk")
    assert community.posting_context(conn, name="Topluluk", now=t0)["recommendation"] == tier


def test_thresholds_follow_admin_settings(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0 - timedelta(days=100))
    add(conn, uid, "https://x.com/a/status/1", t0 - timedelta(days=10), community_name="T")
    assert community.posting_context(conn, name="T", now=t0)["recommendation"] == "CAUTION"
    settings.set_value(conn, "community_caution_days", 9, "admin")
    assert community.posting_context(conn, name="T", now=t0)["recommendation"] == "SAFE"


def test_community_search_and_state(conn: sqlite3.Connection, t0: datetime) -> None:
    cid = community.get_or_create(conn, "r/FPS_Games", "Reddit", None, "u", t0)
    assert community.get_or_create(conn, "fps_games", "Reddit", None, "u", t0) == cid
    assert [c["name"] for c in community.search(conn, "fps")] == ["r/FPS_Games"]
    assert community.search(conn, "%") == []  # joker karakter kaçışlı
    community.set_state(conn, cid, "blocked", True, "admin")
    assert community.search(conn, "fps") == []  # engelli topluluk önerilmez


def test_user_name_collision_and_roles(conn: sqlite3.Connection, t0: datetime) -> None:
    make_user(conn, "Ahmet", now=t0)
    with pytest.raises(ValidationFailed):
        people.create_user(conn, "ahmet", None, "member", None, "admin")
    with pytest.raises(ValidationFailed):
        people.create_user(conn, "Veli", None, "root", None, "admin")
    with pytest.raises(ValidationFailed):
        people.create_user(conn, "Veli", None, "member", "abc", "admin")
