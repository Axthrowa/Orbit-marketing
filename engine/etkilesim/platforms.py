"""Bağlantıdan platform tanıma, kanonik URL ve gönderi kimliği çıkarma."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

Platform = Literal["X", "Instagram", "Facebook", "Threads", "Reddit", "YouTube", "Forum", "Other"]

PLATFORMS: tuple[Platform, ...] = (
    "X",
    "Instagram",
    "Facebook",
    "Threads",
    "Reddit",
    "YouTube",
    "Forum",
    "Other",
)

_HOSTS: tuple[tuple[tuple[str, ...], Platform], ...] = (
    (("x.com", "twitter.com", "mobile.twitter.com"), "X"),
    (("instagram.com",), "Instagram"),
    (("threads.net", "threads.com"), "Threads"),
    (("facebook.com", "fb.com", "fb.watch", "m.facebook.com"), "Facebook"),
    (("reddit.com", "redd.it"), "Reddit"),
    (("youtube.com", "youtu.be"), "YouTube"),
)

# Hangi platformlar tarayıcı oturumu (giriş) gerektirebilir.
BROWSER_PLATFORMS: frozenset[Platform] = frozenset({"X", "Instagram", "Facebook", "Threads"})

_GENERIC_TRACKING = re.compile(r"^(utm_.+|igsh|igshid|fbclid|gclid|si|feature|ref|ref_src|ref_url)$")
_X_TRACKING = {"s", "t"}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def detect_platform(url: str) -> Platform:
    host = _host(url)
    for suffixes, platform in _HOSTS:
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return platform
    first_label = host.split(".")[0] if host else ""
    if first_label in {"forum", "forums", "community", "discuss", "board"} or "/forum" in url.lower():
        return "Forum"
    return "Other"


def canonicalize(url: str, platform: Platform | None = None) -> str:
    """Aynı gönderinin farklı yazımlarını tek biçime indirger (mükerrer kaydı önler)."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    detected = platform or detect_platform(url)
    if detected == "X" and host in {"twitter.com", "mobile.twitter.com"}:
        host = "x.com"
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        lowered = key.lower()
        if _GENERIC_TRACKING.match(lowered):
            continue
        if detected == "X" and lowered in _X_TRACKING:
            continue
        kept.append((key, value))
    return urlunsplit(("https", host, path, urlencode(kept), ""))


_ID_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "X": (re.compile(r"/status(?:es)?/(\d+)"),),
    "Instagram": (re.compile(r"/(?:p|reel|reels|tv)/([\w-]+)"),),
    "Threads": (re.compile(r"/post/([\w-]+)"),),
    "Facebook": (
        re.compile(r"/(?:posts|videos|reel|photos?)/([\w.-]+)"),
        re.compile(r"/share/(?:p|v|r)/([\w-]+)"),
        re.compile(r"[?&](?:story_fbid|fbid|v)=(\d+)"),
    ),
    "Reddit": (re.compile(r"/comments/([a-z0-9]+)"),),
    "YouTube": (
        re.compile(r"[?&]v=([\w-]{6,})"),
        re.compile(r"youtu\.be/([\w-]{6,})"),
        re.compile(r"/(?:shorts|live)/([\w-]{6,})"),
    ),
}


def extract_post_id(url: str, platform: Platform) -> str | None:
    target = url if platform == "YouTube" else urlsplit(url).path + "?" + urlsplit(url).query
    for pattern in _ID_PATTERNS.get(platform, ()):
        found = pattern.search(target)
        if found:
            return found.group(1)
    return None


def registrable_matches(url: str, platform: Platform) -> bool:
    """Yönlendirme sonrası adresin hâlâ beklenen platformda olduğunu doğrular."""
    if platform in {"Forum", "Other"}:
        return True
    return detect_platform(url) == platform
