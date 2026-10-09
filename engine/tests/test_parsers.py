"""Sentetik fikstürler: alan adları belgelenmiş/bilinen yapıya göre kurgulanmıştır, gerçek
platform yanıtı DEĞİLDİR. Gerçek sayfalarla doğrulama ayrıca yapılmalıdır."""

from __future__ import annotations

import json

import pytest

from etkilesim import parsers
from etkilesim.models import Metrics


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (150, 150),
        ("150", 150),
        ("1.234", 1234),
        ("1,234", 1234),
        ("1.234.567", 1234567),
        ("1.2K", 1200),
        ("1,2 B", 1200),
        ("3,4 Mn", 3_400_000),
        ("2M", 2_000_000),
        ("12K", 12000),
        (None, None),
        ("", None),
        ("abc", None),
        (-1, None),
        (True, None),
        ("1.2x", None),
        ("0", 0),
    ],
)
def test_parse_count(raw: object, expected: int | None) -> None:
    assert parsers.parse_count(raw) == expected


def test_x_graphql_payload_selects_target_tweet_not_related() -> None:
    payload = {
        "data": {
            "threaded_conversation": {
                "instructions": [
                    {
                        "entries": [
                            {
                                "rest_id": "999",
                                "legacy": {
                                    "favorite_count": 5,
                                    "reply_count": 1,
                                    "retweet_count": 0,
                                    "quote_count": 0,
                                    "full_text": "ilgisiz başka tweet",
                                },
                            },
                            {
                                "rest_id": "123",
                                "views": {"count": "6800"},
                                "legacy": {
                                    "favorite_count": 150,
                                    "reply_count": 22,
                                    "retweet_count": 10,
                                    "quote_count": 4,
                                    "full_text": "Yeni oyunumuz çıktı!",
                                },
                            },
                            {
                                "rest_id": "124",
                                "legacy": {
                                    "favorite_count": 1,
                                    "reply_count": 0,
                                    "retweet_count": 0,
                                    "quote_count": 0,
                                    "full_text": "harika görünüyor",
                                    "in_reply_to_status_id_str": "123",
                                },
                            },
                        ]
                    }
                ]
            }
        }
    }
    out = parsers.extract("X", "123", "", [payload])
    assert out.metrics == Metrics(likes=150, comments=22, shares=14, views=6800)
    assert out.preview == "Yeni oyunumuz çıktı!"
    assert out.comments == ["harika görünüyor"]


def test_x_without_views_leaves_views_unknown() -> None:
    payload = {
        "rest_id": "1",
        "legacy": {"favorite_count": 3, "reply_count": 0, "retweet_count": 0, "quote_count": 0},
    }
    out = parsers.extract("X", "1", "", [payload])
    assert out.metrics.views is None and out.metrics.likes == 3 and out.metrics.comments == 0


def test_instagram_shared_data_in_html() -> None:
    state = {
        "shortcode": "AbC",
        "edge_media_preview_like": {"count": 321},
        "edge_media_to_parent_comment": {
            "count": 12,
            "edges": [{"node": {"text": "Çok güzel olmuş"}}, {"node": {"text": "Love it"}}],
        },
        "video_view_count": 9000,
        "edge_media_to_caption": {"edges": [{"node": {"text": "Demo yayında"}}]},
    }
    page = f"<html><script>window._sharedData = {json.dumps({'x': state})};</script></html>"
    out = parsers.extract("Instagram", "AbC", page)
    assert out.metrics == Metrics(likes=321, comments=12, shares=None, views=9000)
    assert out.comments == ["Çok güzel olmuş", "Love it"]
    assert out.preview == "Demo yayında"


def test_threads_payload() -> None:
    payload = {
        "post": {
            "code": "XyZ",
            "like_count": 40,
            "caption": {"text": "merhaba"},
            "text_post_app_info": {"direct_reply_count": 7, "repost_count": 3, "quote_count": 1},
        }
    }
    out = parsers.extract("Threads", "XyZ", "", [payload])
    assert out.metrics == Metrics(likes=40, comments=7, shares=4, views=None)


def test_facebook_feedback_block() -> None:
    payload = {
        "feedback": {
            "reaction_count": {"count": 88},
            "comment_count": {"total_count": 9},
            "share_count": {"count": 4},
        },
        "c": {"__typename": "Comment", "body": {"text": "tebrikler"}},
    }
    out = parsers.extract("Facebook", None, "", [payload])
    assert out.metrics == Metrics(likes=88, comments=9, shares=4, views=None)
    assert out.comments == ["tebrikler"]


def test_reddit_listing_json() -> None:
    payload = [
        {
            "data": {
                "children": [
                    {"data": {"score": 321, "num_comments": 18, "title": "Demo", "selftext": "Üç yıl sonra"}}
                ]
            }
        },
        {"data": {"children": [{"data": {"body": "Harika!"}}, {"data": {"body": "[deleted]"}}]}},
    ]
    out = parsers.extract("Reddit", None, "", [payload])
    assert out.metrics == Metrics(likes=321, comments=18, shares=None, views=None)
    assert out.comments == ["Harika!"]
    assert out.preview is not None and out.preview.startswith("Demo")


def test_discourse_topic_json() -> None:
    payload = {
        "title": "Oyun duyurusu",
        "views": 480,
        "like_count": 14,
        "reply_count": 2,
        "post_stream": {"posts": [{"cooked": "<p>ilk</p>"}, {"cooked": "<p>süper <b>oyun</b></p>"}]},
    }
    out = parsers.extract("Forum", None, "", [payload])
    assert out.metrics == Metrics(likes=14, comments=2, shares=None, views=480)
    assert out.comments == ["süper oyun"]


def test_json_ld_interaction_statistics_and_og() -> None:
    ld = {
        "@type": "VideoObject",
        "interactionStatistic": [
            {
                "@type": "InteractionCounter",
                "interactionType": {"@type": "http://schema.org/WatchAction"},
                "userInteractionCount": "5000",
            },
            {
                "@type": "InteractionCounter",
                "interactionType": "https://schema.org/LikeAction",
                "userInteractionCount": 120,
            },
        ],
        "commentCount": 17,
        "comment": [{"text": "güzel video"}],
    }
    page = (
        '<head><meta property="og:description" content="Oynanış videosu"></head>'
        f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    )
    out = parsers.extract("Other", None, page)
    assert out.metrics == Metrics(likes=120, comments=17, shares=None, views=5000)
    assert out.comments == ["güzel video"]
    assert out.preview == "Oynanış videosu" or out.preview is not None


def test_aria_label_fallback_is_last_resort() -> None:
    page = (
        '<div aria-label="1,2 B beğeni"></div><div aria-label="34 replies"></div>'
        '<div aria-label="2.5K views"></div>'
    )
    out = parsers.extract("X", "1", page)
    assert out.metrics == Metrics(likes=1200, comments=34, shares=None, views=2500)


def test_json_state_wins_over_aria() -> None:
    page = '<div aria-label="999 likes"></div>'
    payload = {
        "rest_id": "1",
        "legacy": {"favorite_count": 5, "reply_count": 1, "retweet_count": 0, "quote_count": 0},
    }
    assert parsers.extract("X", "1", page, [payload]).metrics.likes == 5


def test_nothing_found_returns_unknown_not_zero() -> None:
    out = parsers.extract("X", "1", "<html>boş</html>", [])
    assert out.metrics == Metrics() and not out.metrics.known()


def test_malformed_embedded_json_is_ignored() -> None:
    page = (
        '<script type="application/json">{bozuk</script><script>window.__INITIAL_STATE__ = {broken;</script>'
    )
    assert parsers.embedded_json(page) == []


def test_deeply_nested_json_does_not_blow_the_stack() -> None:
    node: dict[str, object] = {}
    cursor = node
    for _ in range(5000):
        child: dict[str, object] = {}
        cursor["a"] = child
        cursor = child
    assert sum(1 for _ in parsers.iter_dicts(node)) <= parsers.MAX_DEPTH + 2


@pytest.mark.parametrize(
    ("url", "title", "body", "status", "expected"),
    [
        ("https://www.instagram.com/accounts/login/?next=/p/x", "Login • Instagram", "", 200, "LOGIN"),
        ("https://x.com/i/flow/login", "X", "", 200, "LOGIN"),
        ("https://x.com/a/status/1", "Log in to X", "", 200, "LOGIN"),
        ("https://www.facebook.com/checkpoint/?next", "Security check", "", 200, "CHALLENGE"),
        ("https://x.com/a/status/1", "X", "", 429, "CHALLENGE"),
        ("https://x.com/a/status/1", "X", "", 403, "CHALLENGE"),
        ("https://site.com/p", "Just a moment", "We detected unusual traffic", 200, "CHALLENGE"),
        ("https://x.com/a/status/1", "Tweet", "<html>normal</html>", 200, None),
    ],
)
def test_block_detection(url: str, title: str, body: str, status: int, expected: str | None) -> None:
    assert parsers.detect_block(url, title, body, status) == expected


def test_captcha_word_in_huge_normal_page_is_not_a_block() -> None:
    body = "<html>" + "x" * 60_000 + " unusual traffic </html>"
    assert parsers.detect_block("https://www.facebook.com/a/posts/1", "Post", body, 200) is None
