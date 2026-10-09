from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from etkilesim import catalog, posts, radar, recommend
from etkilesim.httpclient import FetchResult
from etkilesim.models import CollectResult, Metrics
from etkilesim.sentiment import LexiconEngine

from .helpers import make_user, public_resolver


def community(
    conn: sqlite3.Connection, name: str, desc: str, members: int | None, lang: str | None, spam: float = 0.1
) -> int:
    cur = conn.execute(
        "INSERT INTO communities(name,name_key,platform,url,member_count,activity_score,description,language,"
        "spam_risk,status,discovered_at) VALUES (?,?,?,?,?,?,?,?,?,'discovered','2026-09-01T00:00:00Z')",
        (
            name,
            name.lower(),
            "Reddit",
            f"https://www.reddit.com/r/{name}/",
            members,
            radar.activity(members),
            desc,
            lang,
            spam,
        ),
    )
    return int(cur.lastrowid or 0)


def items(conn: sqlite3.Connection, t0: datetime, **kw: object) -> dict[str, dict[str, object]]:
    result = recommend.recommendations(conn, now=t0, **kw)  # type: ignore[arg-type]
    return {i["name"]: i for i in result["items"]}


def test_game_aware_ranking_and_reasons(conn: sqlite3.Connection, t0: datetime) -> None:
    gid = catalog.create_game(
        conn,
        {"name": "Nova", "genres": ["FPS", "Extraction Shooter"], "keywords": ["pvpve"], "languages": ["en"]},
        "admin",
        t0,
    )
    community(conn, "FPSGames", "FPS games and extraction shooter fans", 250_000, "en")
    community(conn, "Cooking", "Recipes and food", 900_000, "en")
    community(conn, "TurkFPS", "Türk FPS oyuncuları", 5_000, "tr")
    result = items(conn, t0, game_id=gid)
    ordered = list(result)
    assert ordered[0] == "FPSGames" and ordered[-1] == "Cooking"
    texts = [r["text"] for r in result["FPSGames"]["reasons"]]  # type: ignore[index]
    assert any("FPS" in t and "kitlesiyle" in t for t in texts)
    assert any("İngilizce" in t for t in texts)
    assert any("hiç paylaşım" in t for t in texts)
    assert any("uyuşmuyor" in r["text"] for r in result["TurkFPS"]["reasons"])  # type: ignore[index]


def test_recent_use_and_spam_are_penalized(conn: sqlite3.Connection, t0: datetime) -> None:
    gid = catalog.create_game(conn, {"name": "Nova", "genres": ["FPS"]}, "admin", t0)
    community(conn, "FPSA", "fps", 50_000, "en")
    community(conn, "FPSB", "fps", 50_000, "en")
    community(conn, "FPSSpam", "fps giveaway promo", 50_000, "en", spam=0.7)
    uid = make_user(conn, now=t0 - timedelta(days=30))
    posts.add_post(
        conn,
        uid,
        "https://x.com/a/status/1",
        community_name="FPSA",
        now=t0 - timedelta(days=2),
        resolver=public_resolver,
    )
    result = items(conn, t0, game_id=gid)
    assert result["FPSB"]["score"] > result["FPSA"]["score"]  # type: ignore[operator]
    assert result["FPSB"]["score"] > result["FPSSpam"]["score"]  # type: ignore[operator]
    assert result["FPSA"]["penalties"]["recency"] == 30.0  # type: ignore[index]
    assert any("kaçının" in r["text"] for r in result["FPSA"]["reasons"])  # type: ignore[index]
    assert any("Spam" in r["text"] for r in result["FPSSpam"]["reasons"])  # type: ignore[index]


def test_engagement_history_rewards_communities_that_worked(conn: sqlite3.Connection, t0: datetime) -> None:
    community(conn, "Good", "indie games", 10_000, "en")
    community(conn, "Meh", "indie games", 10_000, "en")
    uid = make_user(conn, now=t0 - timedelta(days=90))
    engine = LexiconEngine()
    for name, likes in (("Good", 900), ("Meh", 5)):
        pid = posts.add_post(
            conn,
            uid,
            f"https://x.com/a/status/{likes}",
            community_name=name,
            now=t0 - timedelta(days=60),
            resolver=public_resolver,
        ).post_id
        posts.record_collect(
            conn, pid, CollectResult("OK", Metrics(likes=likes)), engine, t0 - timedelta(days=59)
        )
    result = items(conn, t0)
    assert result["Good"]["components"]["engagement_history"] == 1.0  # type: ignore[index]
    assert result["Good"]["score"] > result["Meh"]["score"]  # type: ignore[operator]


def test_unknowns_are_neutral_and_blocked_are_hidden(conn: sqlite3.Connection, t0: datetime) -> None:
    cid = community(conn, "Unknown", "", None, None)
    blocked = community(conn, "Blocked", "fps", 1000, "en")
    conn.execute("UPDATE communities SET status='blocked' WHERE id=?", (blocked,))
    result = items(conn, t0)
    assert "Blocked" not in result
    comp = result["Unknown"]["components"]  # type: ignore[index]
    assert comp["activity"] is None and comp["language_match"] is None
    assert any("Üye sayısı bilinmiyor" in r["text"] for r in result["Unknown"]["reasons"])  # type: ignore[index]
    assert cid > 0


def test_discovery_stores_language_spam_and_scan_time(conn: sqlite3.Connection, t0: datetime) -> None:
    body = json.dumps(
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "display_name_prefixed": "r/FPS_Games",
                            "url": "/r/FPS_Games/",
                            "subscribers": 250000,
                            "public_description": "FPS games community",
                            "subreddit_type": "public",
                            "lang": "en",
                        }
                    },
                    {
                        "data": {
                            "display_name_prefixed": "r/FreeFPS",
                            "url": "/r/FreeFPS/",
                            "subscribers": 50,
                            "public_description": "FPS giveaway promo codes",
                            "subreddit_type": "public",
                        }
                    },
                ]
            }
        }
    )
    radar.discover(conn, ["FPS games"], t0, fetch_fn=lambda u: FetchResult(200, body, u))
    rows = {r["name"]: r for r in conn.execute("SELECT * FROM communities")}
    assert rows["r/FPS_Games"]["language"] == "en" and rows["r/FPS_Games"]["spam_risk"] < 0.5
    assert rows["r/FreeFPS"]["spam_risk"] >= 0.7
    assert rows["r/FPS_Games"]["last_scanned_at"] == "2026-10-01T12:00:00Z"
    assert "FPS games community" in rows["r/FPS_Games"]["description"]
