from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from etkilesim import analytics, catalog, cli, posts, settings
from etkilesim.errors import ValidationFailed
from etkilesim.models import CollectResult, Metrics
from etkilesim.sentiment import LexiconEngine

from .helpers import make_user, public_resolver

ENGINE = LexiconEngine()


def add(conn: sqlite3.Connection, uid: int, url: str, t: datetime, **kw: object) -> int:
    return posts.add_post(conn, uid, url, now=t, resolver=public_resolver, **kw).post_id  # type: ignore[arg-type]


def measure(
    conn: sqlite3.Connection, pid: int, t: datetime, likes: int, comments: int = 0, views: int | None = None
) -> None:
    posts.record_collect(
        conn, pid, CollectResult("OK", Metrics(likes=likes, comments=comments, views=views)), ENGINE, t
    )


def test_post_velocity_growth_and_rate(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0)
    measure(conn, pid, t0 + timedelta(minutes=50), 10, 2, 400)
    measure(conn, pid, t0 + timedelta(hours=5), 40, 8, 1000)
    measure(conn, pid, t0 + timedelta(hours=20), 100, 20, 4000)
    m = analytics.post_metrics(conn, pid)
    assert m["velocity_1h"] == 12.0  # 12 etkileşim / 1 saat
    assert m["velocity_6h"] == 8.0  # 48 / 6
    assert m["velocity_24h"] == 5.0  # 120 / 24
    assert (m["likes_growth"], m["views_growth"]) == (90, 3600)
    assert m["engagement_total"] == 120 and m["engagement_rate"] == 0.03


def test_unknown_metrics_stay_unknown(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0)
    m = analytics.post_metrics(conn, pid)
    assert m["velocity_24h"] is None and m["engagement_total"] is None and m["likes_growth"] is None


def test_leaderboard_normalizes_big_accounts(conn: sqlite3.Connection, t0: datetime) -> None:
    big = make_user(conn, "Büyük", now=t0 - timedelta(days=30))
    steady = make_user(conn, "Düzenli", now=t0 - timedelta(days=30))
    # Büyük hesap: tek paylaşım, çok etkileşim, tek topluluk
    pid = add(conn, big, "https://x.com/b/status/1", t0 - timedelta(days=20), community_name="A")
    measure(conn, pid, t0 - timedelta(days=20) + timedelta(hours=2), 10_000)
    # Düzenli hesap: 10 gün, farklı topluluklar, makul etkileşim
    for day in range(10):
        p = add(
            conn,
            steady,
            f"https://x.com/s/status/{day}",
            t0 - timedelta(days=day * 3),
            community_name=f"T{day}",
        )
        measure(conn, p, t0 - timedelta(days=day * 3) + timedelta(hours=2), 300)
    board = analytics.leaderboard(conn, analytics.Filters(days=30), t0)
    assert [row["name"] for row in board] == ["Düzenli", "Büyük"]
    assert board[0]["rank"] == 1 and board[0]["posts"] == 10 and board[0]["community_count"] == 10
    assert 0 < board[1]["performance_score"] < board[0]["performance_score"] <= 100


def test_admin_weights_change_the_ranking(conn: sqlite3.Connection, t0: datetime) -> None:
    test_leaderboard_normalizes_big_accounts(conn, t0)
    for key in (
        "perf_weight_consistency",
        "perf_weight_sentiment",
        "perf_weight_diversity",
        "perf_weight_velocity",
        "perf_weight_campaign",
    ):
        settings.set_value(conn, key, 0, "admin")
    settings.set_value(conn, "perf_weight_engagement", 100, "admin")
    board = analytics.leaderboard(conn, analytics.Filters(days=30), t0)
    assert board[0]["name"] == "Büyük"  # yalnız etkileşim önemliyse büyük hesap öne geçer


def test_people_without_posts_score_zero(conn: sqlite3.Connection, t0: datetime) -> None:
    make_user(conn, "Sessiz", now=t0)
    row = analytics.leaderboard(conn, analytics.Filters(days=7), t0)[0]
    assert row["performance_score"] == 0 and row["posts"] == 0 and row["engagement"] is None


def test_filters_and_breakdowns(conn: sqlite3.Connection, t0: datetime) -> None:
    gid = catalog.create_game(conn, {"name": "Nova"}, "admin", t0)
    cid = catalog.create_campaign(conn, {"name": "Beta", "game_id": gid}, "admin", t0)
    uid = make_user(conn, now=t0 - timedelta(days=60))
    a = add(
        conn, uid, "https://x.com/a/status/1", t0 - timedelta(days=1), campaign_id=cid, content_type="video"
    )
    b = add(conn, uid, "https://www.reddit.com/r/x/comments/abc/t/", t0 - timedelta(days=2))
    old = add(conn, uid, "https://x.com/a/status/9", t0 - timedelta(days=50))
    for pid, likes in ((a, 50), (b, 10), (old, 999)):
        measure(conn, pid, t0, likes)
    week = analytics.overview(conn, analytics.Filters(days=7), t0)
    assert week["totals"]["posts"] == 2 and week["totals"]["likes"] == 60
    assert {p["key"] for p in week["platforms"]} == {"X", "Reddit"}
    assert {c["key"] for c in week["content_types"]} == {"video", "post"}
    assert week["campaigns"][0]["name"] == "Beta" and week["games"][0]["name"] == "Nova"
    only_campaign = analytics.overview(conn, analytics.Filters(days=None, campaign_id=cid), t0)
    assert only_campaign["totals"]["posts"] == 1
    only_reddit = analytics.overview(conn, analytics.Filters(days=None, platform="Reddit"), t0)
    assert only_reddit["totals"]["likes"] == 10


def test_analytics_command_validates_period(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValidationFailed):
        cli.dispatch("analytics", {"days": 12}, conn)
    assert "leaderboard" in cli.dispatch("analytics", {"days": 30}, conn)


def test_post_detail_includes_derived_metrics(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0)
    measure(conn, pid, t0 + timedelta(minutes=30), 6)
    assert posts.post_detail(conn, pid)["analytics"]["velocity_1h"] == 6.0
