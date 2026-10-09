from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from etkilesim import analytics, posts, topics
from etkilesim.sentiment import LexiconEngine, analyze_text

from .helpers import make_user, public_resolver


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Oyun sürekli çöküyor, bug dolu", {"bug"}),
        ("Fiyatı çok pahalı olmuş", {"price"}),
        ("FPS drop var, optimizasyon berbat", {"performance"}),
        ("Sunucu ping çok yüksek", {"server"}),
        ("Oynanış harika, çok eğlenceli", {"gameplay_praise"}),
        ("Graphics look amazing!", {"graphics_praise"}),
        ("Keşke co-op modu eklenmeli", {"feature_request"}),
        ("Beta ne zaman açılacak?", {"release_question"}),
        ("Merhaba", set()),
    ],
)
def test_detect(text: str, expected: set[str]) -> None:
    assert set(topics.detect(text, analyze_text(text).label)) == expected


def test_praise_topics_need_positive_sentiment() -> None:
    assert "graphics_praise" not in topics.detect("grafikler berbat", "NEGATIVE")
    assert "graphics_praise" in topics.detect("grafikler harika", "POSITIVE")


def test_topics_are_stored_and_aggregated(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = posts.add_post(conn, uid, "https://x.com/a/status/1", now=t0, resolver=public_resolver).post_id
    posts.add_manual_comments(
        conn,
        pid,
        ["Sunucu çöktü bug var", "Oynanış harika", "Server lag berbat", "Beta ne zaman?"],
        LexiconEngine(),
        "u",
        t0,
    )
    detail = posts.post_detail(conn, pid)
    assert {t for c in detail["comments"] for t in c["topics"]} >= {"server", "bug", "gameplay_praise"}
    assert detail["topic_labels"]["server"] == "Sunucu / bağlantı"
    counts = {c["key"]: c for c in analytics.topic_counts(conn, analytics.Filters(days=None), t0)}
    assert counts["server"]["count"] == 2 and counts["server"]["negative"] >= 1
    assert analytics.overview(conn, analytics.Filters(days=None), t0)["topics"][0]["key"] == "server"
