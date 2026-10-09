from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from etkilesim import posts, radar, refresh, settings
from etkilesim.collectors import HttpCollector, PostRef
from etkilesim.httpclient import FetchResult
from etkilesim.models import CollectResult, Metrics
from etkilesim.sentiment import LexiconEngine

from .helpers import make_user, public_resolver


class FakeBrowser:
    def __init__(self, results: list[CollectResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def collect(self, ref: PostRef, _limit: int) -> CollectResult:
        self.calls.append(ref.url)
        return self.results.pop(0)


def factory_for(browser: FakeBrowser, opened: list[int]) -> Any:
    @asynccontextmanager
    async def make() -> AsyncIterator[FakeBrowser]:
        opened.append(1)
        yield browser

    return make


async def no_sleep(_s: float) -> None:
    return None


def add(conn: sqlite3.Connection, uid: int, url: str, t: datetime) -> int:
    return posts.add_post(conn, uid, url, now=t, resolver=public_resolver).post_id


def run_refresh(conn: sqlite3.Connection, t: datetime, **kw: Any) -> refresh.RefreshSummary:
    return asyncio.run(refresh.refresh(conn, now=t, engine=LexiconEngine(), sleep=no_sleep, **kw))


REDDIT_URL = "https://www.reddit.com/r/x/comments/abc/t/"
REDDIT_JSON = "https://www.reddit.com/comments/abc.json?limit=50&raw_json=1"
LISTING = json.dumps(
    [
        {"data": {"children": [{"data": {"score": 9, "num_comments": 2, "title": "T"}}]}},
        {"data": {"children": [{"data": {"body": "harika"}}]}},
    ]
)


def test_refresh_mixes_http_and_browser(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    reddit = add(conn, uid, REDDIT_URL, t0)
    x_post = add(conn, uid, "https://x.com/a/status/5", t0)
    browser = FakeBrowser([CollectResult("OK", Metrics(likes=7, views=100), source="SCRAPE")])
    opened: list[int] = []
    http = HttpCollector(
        lambda u: FetchResult(200, LISTING, u) if u == REDDIT_JSON else FetchResult(404, "", u)
    )
    summary = run_refresh(conn, t0, http=http, browser_factory=factory_for(browser, opened))
    assert (summary.checked, summary.ok) == (2, 2) and opened == [1]
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM posts")}
    assert rows[reddit]["current_likes"] == 9 and rows[reddit]["sentiment_sample"] == 1
    assert rows[x_post]["current_likes"] == 7 and rows[x_post]["views_count"] == 100
    states = {r["platform"]: r for r in conn.execute("SELECT * FROM provider_state")}
    assert set(states) == {"Reddit", "X"} and states["X"]["last_success_at"]


def test_browser_is_not_opened_when_only_http_posts_are_due(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add(conn, uid, REDDIT_URL, t0)
    opened: list[int] = []
    http = HttpCollector(lambda u: FetchResult(200, LISTING, u))
    run_refresh(conn, t0, http=http, browser_factory=factory_for(FakeBrowser([]), opened))
    assert opened == []


def test_challenge_pauses_platform_and_skips_rest(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    first = add(conn, uid, "https://x.com/a/status/1", t0)
    second = add(conn, uid, "https://x.com/a/status/2", t0)
    blocked = CollectResult("DATA_UNAVAILABLE", blocked=True, source="SCRAPE", error="Bot koruması")
    browser = FakeBrowser([blocked])
    summary = run_refresh(conn, t0, browser_factory=factory_for(browser, []))
    assert summary.unavailable == 1 and summary.skipped_paused == 1
    assert len(browser.calls) == 1  # ikinci gönderi için hiç deneme yapılmadı
    state = conn.execute("SELECT * FROM provider_state WHERE platform='X'").fetchone()
    assert state["paused_until"] is not None and state["consecutive_blocks"] == 1
    statuses = {r["id"]: r["data_status"] for r in conn.execute("SELECT id, data_status FROM posts")}
    assert statuses[first] == "DATA_UNAVAILABLE" and statuses[second] == "PENDING"  # silinmedi
    again = run_refresh(conn, t0 + timedelta(minutes=10), browser_factory=factory_for(FakeBrowser([]), []))
    assert again.skipped_paused >= 1  # duraklatma sürüyor


def test_pause_expires_and_success_resets(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add(conn, uid, "https://x.com/a/status/1", t0)
    blocked = CollectResult("DATA_UNAVAILABLE", blocked=True, error="b")
    run_refresh(conn, t0, browser_factory=factory_for(FakeBrowser([blocked]), []))
    later = t0 + timedelta(hours=7)
    ok = FakeBrowser([CollectResult("OK", Metrics(likes=1), source="SCRAPE")])
    summary = run_refresh(conn, later, browser_factory=factory_for(ok, []))
    assert summary.ok == 1
    state = conn.execute("SELECT * FROM provider_state WHERE platform='X'").fetchone()
    assert state["consecutive_blocks"] == 0 and state["paused_until"] is None


def test_scrape_disabled_keeps_browser_closed(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "scrape_enabled", False, "admin")
    uid = make_user(conn, now=t0)
    add(conn, uid, "https://x.com/a/status/1", t0)
    opened: list[int] = []
    summary = run_refresh(conn, t0, browser_factory=factory_for(FakeBrowser([]), opened))
    assert opened == [] and summary.unavailable == 1


def test_unexpected_collector_error_does_not_abort_the_run(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    add(conn, uid, REDDIT_URL, t0)
    add(conn, uid, "https://forum.example.com/t/1", t0)

    def flaky(url: str) -> FetchResult:
        if "reddit" in url:
            raise RuntimeError("beklenmedik")
        return FetchResult(404, "", url)

    summary = run_refresh(conn, t0, http=HttpCollector(flaky))
    assert summary.checked == 2 and conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 2


def test_refresh_specific_posts_only(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    a = add(conn, uid, REDDIT_URL, t0)
    add(conn, uid, "https://forum.example.com/t/1", t0)
    http = HttpCollector(lambda u: FetchResult(200, LISTING, u))
    summary = run_refresh(conn, t0, post_ids=[a], http=http)
    assert summary.checked == 1


# ----- radar ----------------------------------------------------------------------------------


def reddit_search(*items: dict[str, Any]) -> str:
    return json.dumps({"data": {"children": [{"data": i} for i in items]}})


def sub(name: str, subs: int | None, desc: str, **extra: Any) -> dict[str, Any]:
    return {
        "display_name_prefixed": f"r/{name}",
        "url": f"/r/{name}/",
        "subscribers": subs,
        "public_description": desc,
        "subreddit_type": "public",
        **extra,
    }


def test_build_queries_variants() -> None:
    queries = radar.build_queries("FPS")
    assert (
        queries[0] == "FPS"
        and "FPS community" in queries
        and len(queries) == len(set(q.lower() for q in queries))
    )
    assert radar.build_queries("   ") == []


def test_discover_scores_and_filters(conn: sqlite3.Connection, t0: datetime) -> None:
    body = reddit_search(
        sub("FPS_Games", 250_000, "Best FPS games community"),
        sub("Cooking", 900_000, "Recipes and food"),
        sub("NsfwFps", 10_000, "fps games", over18=True),
        sub("PrivateFps", 10_000, "fps games", subreddit_type="private"),
        sub("TinyFps", None, "fps games"),
    )
    report = radar.discover(conn, ["FPS games"], t0, fetch_fn=lambda u: FetchResult(200, body, u))
    names = [r["name"] for r in conn.execute("SELECT name FROM communities ORDER BY name")]
    assert names == ["r/FPS_Games", "r/TinyFps"]
    assert report.added == 2 and report.unavailable == []
    row = conn.execute("SELECT * FROM communities WHERE name='r/FPS_Games'").fetchone()
    assert row["status"] == "discovered" and row["member_count"] == 250_000
    assert row["relevance_score"] > 50 and "250.000" in row["reason"]
    tiny = conn.execute("SELECT * FROM communities WHERE name='r/TinyFps'").fetchone()
    assert tiny["member_count"] is None and "bilinmiyor" in tiny["reason"]


def test_rediscovery_keeps_user_decisions(conn: sqlite3.Connection, t0: datetime) -> None:
    body = reddit_search(sub("FPS_Games", 250_000, "fps games community"))
    fetch = lambda u: FetchResult(200, body, u)  # noqa: E731
    radar.discover(conn, ["fps games"], t0, fetch_fn=fetch)
    conn.execute("UPDATE communities SET status='blocked', favorite=1")
    again = radar.discover(conn, ["fps games"], t0, fetch_fn=fetch)
    assert again.added == 0
    row = conn.execute("SELECT status, favorite FROM communities").fetchone()
    assert (row["status"], row["favorite"]) == ("blocked", 1)
    assert radar.ranked(conn) == []  # engelli topluluk radarda görünmez


def test_discovery_degrades_gracefully(conn: sqlite3.Connection, t0: datetime) -> None:
    report = radar.discover(conn, ["fps"], t0, fetch_fn=lambda u: FetchResult(429, "", u))
    assert report.added == 0 and "429" in report.unavailable[0]
    bad = radar.discover(conn, ["fps"], t0, fetch_fn=lambda u: FetchResult(200, "not json", u))
    assert bad.added == 0 and bad.unavailable


def test_ranked_shows_last_use_info(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    posts.add_post(
        conn, uid, "https://x.com/a/status/1", community_name="r/FPS_Games", now=t0, resolver=public_resolver
    )
    entry = radar.ranked(conn)[0]
    assert entry["previous_posts"] == 1 and entry["last_used"] == "2026-10-01T12:00:00Z"
