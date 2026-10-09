"""Toplayıcı akış testleri: sahte sayfa/sunucu; gerçek platformlara istek atılmaz."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from etkilesim.collectors import BrowserCollector, HttpCollector, PostRef, collect_ref
from etkilesim.errors import ProviderUnavailable, UnsafeUrl
from etkilesim.httpclient import FetchResult, _SafeRedirects

from .helpers import public_resolver


async def no_sleep(_seconds: float) -> None:
    return None


class FakeResponse:
    def __init__(self, url: str, payload: object) -> None:
        self.url = url
        self._payload = payload

    async def all_headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    async def body(self) -> bytes:
        return json.dumps(self._payload).encode()


class FakeMouse:
    def __init__(self) -> None:
        self.scrolls = 0

    async def wheel(self, _x: int, _y: int) -> None:
        self.scrolls += 1


class FakePage:
    def __init__(
        self,
        final_url: str,
        html: str = "<html></html>",
        title: str = "Gönderi",
        status: int | None = 200,
        responses: list[FakeResponse] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.url = final_url
        self._html, self._title, self._status = html, title, status
        self._responses = responses or []
        self._fail = fail
        self._handlers: list[Any] = []
        self.mouse = FakeMouse()
        self.closed = False

    async def route(self, _pattern: str, _handler: Any) -> None:
        return None

    def on(self, _event: str, handler: Any) -> None:
        self._handlers.append(handler)

    async def goto(self, _url: str, **_kw: Any) -> Any:
        if self._fail:
            raise self._fail
        for response in self._responses:
            for handler in self._handlers:
                handler(response)
        return type("R", (), {"status": self._status})() if self._status else None

    async def title(self) -> str:
        return self._title

    async def content(self) -> str:
        return self._html

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    async def new_page(self) -> FakePage:
        return self.page


def browser_with(page: FakePage) -> BrowserCollector:
    collector = BrowserCollector(
        Path("unused"), sleep=no_sleep, jitter=lambda a, _b: a, resolver=public_resolver
    )
    collector._context = FakeContext(page)
    return collector


X_REF = PostRef(1, "https://x.com/a/status/123", "X", "123")
X_PAYLOAD = {
    "rest_id": "123",
    "views": {"count": "6800"},
    "legacy": {
        "favorite_count": 150,
        "reply_count": 22,
        "retweet_count": 10,
        "quote_count": 0,
        "full_text": "Yeni demo!",
    },
}


def test_browser_reads_metrics_from_network_json() -> None:
    page = FakePage(X_REF.url, responses=[FakeResponse("https://x.com/i/api/graphql/x", X_PAYLOAD)])
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "OK" and result.source == "SCRAPE"
    assert (result.metrics.likes, result.metrics.comments, result.metrics.shares) == (150, 22, 10)
    assert result.metrics.views == 6800
    assert page.mouse.scrolls == 3 and page.closed


def test_browser_ignores_json_from_other_hosts() -> None:
    page = FakePage(
        X_REF.url,
        html="<html></html>",
        responses=[FakeResponse("https://tracker.example.net/x", X_PAYLOAD)],
    )
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "DATA_UNAVAILABLE"
    assert not result.metrics.known()


def test_login_wall_is_reported_not_bypassed() -> None:
    page = FakePage("https://x.com/i/flow/login", title="Log in to X")
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "AUTHORIZATION_REQUIRED" and not result.blocked


def test_challenge_pauses_instead_of_solving() -> None:
    page = FakePage(X_REF.url, status=429)
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "DATA_UNAVAILABLE" and result.blocked
    assert page.mouse.scrolls == 0  # engel görülünce devam edilmez


def test_redirect_to_private_network_is_refused() -> None:
    page = FakePage("http://192.168.1.1/admin")
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "DATA_UNAVAILABLE" and "Güvensiz" in (result.error or "")


def test_redirect_to_other_site_is_refused() -> None:
    page = FakePage("https://evil.example.com/phish")
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "DATA_UNAVAILABLE" and "yönlendirildi" in (result.error or "")


def test_unsafe_input_url_never_opens_a_page() -> None:
    page = FakePage("http://localhost/")
    ref = PostRef(1, "http://localhost/status/1", "X", None)
    result = asyncio.run(browser_with(page).collect(ref, 50))
    assert result.status == "DATA_UNAVAILABLE" and page.mouse.scrolls == 0


def test_page_errors_become_unavailable_not_crash() -> None:
    page = FakePage(X_REF.url, fail=TimeoutError("nav timeout"))
    result = asyncio.run(browser_with(page).collect(X_REF, 50))
    assert result.status == "DATA_UNAVAILABLE" and "TimeoutError" in (result.error or "")
    assert page.closed


def test_browser_requires_open_context() -> None:
    collector = BrowserCollector(Path("unused"))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(collector.collect(X_REF, 10))


# ----- HTTP toplayıcı -------------------------------------------------------------------------


def http_with(responses: dict[str, FetchResult]) -> tuple[HttpCollector, list[str]]:
    calls: list[str] = []

    def fake(url: str) -> FetchResult:
        calls.append(url)
        return responses.get(url, FetchResult(404, "", url))

    return HttpCollector(fake), calls


def test_reddit_uses_public_json() -> None:
    url = "https://www.reddit.com/comments/abc.json?limit=50&raw_json=1"
    listing = [
        {"data": {"children": [{"data": {"score": 12, "num_comments": 3, "title": "Demo"}}]}},
        {"data": {"children": [{"data": {"body": "süper"}}]}},
    ]
    collector, calls = http_with({url: FetchResult(200, json.dumps(listing), url)})
    ref = PostRef(1, "https://www.reddit.com/r/x/comments/abc/t/", "Reddit", "abc")
    result = collector.collect(ref, 50)
    assert calls == [url]
    assert result.status == "OK" and result.metrics.likes == 12 and result.comment_texts == ["süper"]


def test_discourse_topic_json_is_tried_first() -> None:
    page_url = "https://forum.example.com/t/oyun-duyurusu/42"
    topic = {
        "views": 480,
        "like_count": 14,
        "reply_count": 2,
        "title": "Duyuru",
        "post_stream": {"posts": [{"cooked": "<p>a</p>"}, {"cooked": "<p>güzel</p>"}]},
    }
    collector, calls = http_with({page_url + ".json": FetchResult(200, json.dumps(topic), page_url)})
    result = collector.collect(PostRef(1, page_url, "Forum", None), 50)
    assert calls[0].endswith(".json") and result.metrics.views == 480 and result.status == "OK"


def test_http_collector_maps_rate_limit_to_blocked() -> None:
    url = "https://www.reddit.com/comments/abc.json?limit=50&raw_json=1"
    collector, _ = http_with({url: FetchResult(429, "", url)})
    result = collector.collect(PostRef(1, "https://www.reddit.com/comments/abc", "Reddit", "abc"), 50)
    assert result.status == "DATA_UNAVAILABLE" and result.blocked


def test_http_collector_reports_deleted_post() -> None:
    collector, _ = http_with({})
    result = collector.collect(PostRef(1, "https://forum.example.com/x", "Forum", None), 50)
    assert result.status == "DATA_UNAVAILABLE" and not result.blocked


def test_http_collector_does_not_handle_browser_platforms() -> None:
    collector, calls = http_with({})
    assert collector.collect(X_REF, 10).status == "AUTHORIZATION_REQUIRED" and calls == []


def test_http_collector_converts_unsafe_redirect_to_unavailable() -> None:
    def boom(_url: str) -> FetchResult:
        raise UnsafeUrl("Özel/yerel ağ adresleri kabul edilmez")

    result = HttpCollector(boom).collect(PostRef(1, "https://forum.example.com/x", "Forum", None), 10)
    assert result.status == "DATA_UNAVAILABLE" and "Güvensiz" in (result.error or "")


def test_router_without_browser_marks_unavailable() -> None:
    result = asyncio.run(collect_ref(X_REF, 10, HttpCollector(lambda u: FetchResult(404, "", u)), None))
    assert result.status == "DATA_UNAVAILABLE"


def test_redirect_handler_rechecks_every_hop() -> None:
    handler = _SafeRedirects(public_resolver)
    request = type("Req", (), {})()
    with pytest.raises(UnsafeUrl):
        handler.redirect_request(request, None, 302, "Found", {}, "http://169.254.169.254/latest")  # type: ignore[arg-type]
