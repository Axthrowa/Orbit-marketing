from __future__ import annotations

import pytest

from etkilesim.errors import UnsafeUrl
from etkilesim.platforms import canonicalize, detect_platform, extract_post_id
from etkilesim.security import validate_public_url


def public(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://127.0.0.1/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://172.16.5.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::ffff:127.0.0.1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "javascript:alert(1)",
        "data:text/html,hi",
        "https://user:pw@example.com/",
        "https://example.com:8080/",
        "https://printer.local/",
        "",
    ],
)
def test_blocks_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeUrl):
        validate_public_url(url, resolver=public)


def test_blocks_dns_that_resolves_to_private_address() -> None:
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://evil.example.com/", resolver=lambda *_: ["10.0.0.5"])


def test_blocks_if_any_resolved_address_is_private() -> None:
    with pytest.raises(UnsafeUrl):
        validate_public_url("https://rebind.example.com/", resolver=lambda *_: ["93.184.216.34", "127.0.0.1"])


def test_allows_public_url_and_strips_fragment() -> None:
    assert validate_public_url("HTTPS://Example.com/a?b=1#frag", resolver=public) == (
        "https://example.com/a?b=1"
    )


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://x.com/a/status/1", "X"),
        ("https://twitter.com/a/status/1", "X"),
        ("https://www.instagram.com/p/AbC/", "Instagram"),
        ("https://www.threads.net/@a/post/xyz", "Threads"),
        ("https://www.facebook.com/a/posts/123", "Facebook"),
        ("https://www.reddit.com/r/x/comments/abc/t/", "Reddit"),
        ("https://youtu.be/dQw4w9WgXcQ", "YouTube"),
        ("https://forum.example.com/t/1", "Forum"),
        ("https://example.org/", "Other"),
        ("https://notx.com/a", "Other"),
    ],
)
def test_detect_platform(url: str, platform: str) -> None:
    assert detect_platform(url) == platform


def test_canonicalization_merges_variants() -> None:
    a = canonicalize("https://twitter.com/Foo/status/99?s=20&t=abc")
    b = canonicalize("https://www.x.com/Foo/status/99/")
    assert a == b == "https://x.com/Foo/status/99"


def test_canonicalization_keeps_meaningful_forum_params() -> None:
    url = canonicalize("https://forum.example.com/viewtopic.php?t=123&utm_source=a")
    assert url.endswith("viewtopic.php?t=123")


def test_post_id_extraction() -> None:
    assert extract_post_id("https://x.com/a/status/12345", "X") == "12345"
    assert extract_post_id("https://www.instagram.com/reel/Cx_1-z/", "Instagram") == "Cx_1-z"
    assert extract_post_id("https://www.threads.net/@a/post/AbC9", "Threads") == "AbC9"
    assert extract_post_id("https://youtu.be/dQw4w9WgXcQ", "YouTube") == "dQw4w9WgXcQ"
    assert extract_post_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube") == "dQw4w9WgXcQ"
    assert extract_post_id("https://x.com/a", "X") is None
