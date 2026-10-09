"""Sayfa kaynağı / JSON yanıtlarından metrik ve yorum çıkarma. Saf fonksiyonlar, ağ yok.

Öncelik: (1) ağ yanıtlarındaki ve sayfaya gömülü JSON durumları, (2) schema.org JSON-LD /
OpenGraph, (3) yedek olarak `aria-label` metinleri. Platform yapıları sık değişir; alan adları
en iyi bilgiyle yazılmıştır ve gerçek hesaplarla DOĞRULANMAMIŞTIR. Bulunamayan sayaç None
kalır (0 değildir) ve kullanıcı elle girebilir.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .models import Metrics
from .platforms import Platform

MAX_DEPTH = 40
MAX_NODES = 200_000

_SUFFIX = {"k": 1e3, "b": 1e3, "bin": 1e3, "m": 1e6, "mn": 1e6, "mio": 1e6, "g": 1e9}
_COUNT_RE = re.compile(r"^\s*([\d.,]+)\s*([a-zA-Z]*)\s*$")
_THOUSANDS_RE = re.compile(r"^\d{1,3}([.,]\d{3})+$")


def parse_count(value: object) -> int | None:
    """1234, '1.234', '1,234', '1.2K', '3,4 Mn', '2 B' (bin) → tam sayı; anlamsızsa None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    match = _COUNT_RE.match(value)
    if not match:
        return None
    number, suffix = match.group(1), match.group(2).lower()
    if suffix:
        factor = _SUFFIX.get(suffix)
        if factor is None:
            return None
        try:
            return round(float(number.replace(",", ".")) * factor)
        except ValueError:
            return None
    if _THOUSANDS_RE.match(number):
        return int(re.sub(r"[.,]", "", number))
    if re.fullmatch(r"\d+", number):
        return int(number)
    return None


def iter_dicts(root: Any) -> Iterator[dict[str, Any]]:
    """Derinlik/düğüm sınırlı, özyinelemesiz gezinti (kötü niyetli dev JSON'a karşı)."""
    stack: list[tuple[Any, int]] = [(root, 0)]
    visited = 0
    while stack:
        node, depth = stack.pop()
        visited += 1
        if visited > MAX_NODES or depth > MAX_DEPTH:
            return
        if isinstance(node, dict):
            yield node
            stack.extend((v, depth + 1) for v in node.values() if isinstance(v, dict | list))
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node if isinstance(v, dict | list))


def _dig(node: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _first_count(node: dict[str, Any], *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        found = parse_count(_dig(node, *path))
        if found is not None:
            return found
    return None


def _sum_known(*values: int | None) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


@dataclass
class Extracted:
    metrics: Metrics = field(default_factory=Metrics)
    comments: list[str] = field(default_factory=list)
    preview: str | None = None


# ----------------------------------------------------------------------- JSON durum ayrıştırıcıları


def _x_from_json(payloads: list[Any], post_id: str | None) -> Extracted:
    best: Extracted | None = None
    for payload in payloads:
        for node in iter_dicts(payload):
            legacy = node.get("legacy") if isinstance(node.get("legacy"), dict) else node
            if not isinstance(legacy, dict) or "favorite_count" not in legacy:
                continue
            ident = str(node.get("rest_id") or legacy.get("id_str") or "")
            if post_id and ident != post_id:
                continue
            retweets = parse_count(legacy.get("retweet_count"))
            quotes = parse_count(legacy.get("quote_count"))
            metrics = Metrics(
                likes=parse_count(legacy.get("favorite_count")),
                comments=parse_count(legacy.get("reply_count")),
                shares=_sum_known(retweets, quotes),
                views=parse_count(_dig(node, "views", "count")),
            )
            text = legacy.get("full_text") if isinstance(legacy.get("full_text"), str) else None
            if best is None or (metrics.views is not None and best.metrics.views is None):
                best = Extracted(metrics, [], text)
    if best is None:
        return Extracted()
    if post_id:
        for payload in payloads:
            for node in iter_dicts(payload):
                legacy = node.get("legacy") if isinstance(node.get("legacy"), dict) else node
                if (
                    isinstance(legacy, dict)
                    and isinstance(legacy.get("full_text"), str)
                    and str(legacy.get("in_reply_to_status_id_str") or "") == post_id
                ):
                    best.comments.append(legacy["full_text"])
    return best


def _instagram_from_json(payloads: list[Any], post_id: str | None) -> Extracted:
    for payload in payloads:
        for node in iter_dicts(payload):
            matches = post_id and node.get("shortcode") == post_id
            has_counts = any(k in node for k in ("edge_media_preview_like", "like_count"))
            if not (matches or (not post_id and has_counts)):
                continue
            metrics = Metrics(
                likes=_first_count(
                    node, ("edge_media_preview_like", "count"), ("like_count",), ("edge_liked_by", "count")
                ),
                comments=_first_count(
                    node,
                    ("edge_media_to_parent_comment", "count"),
                    ("edge_media_to_comment", "count"),
                    ("comment_count",),
                ),
                shares=None,
                views=_first_count(node, ("video_view_count",), ("play_count",), ("view_count",)),
            )
            comments: list[str] = []
            for key in ("edge_media_to_parent_comment", "edge_media_to_comment"):
                for edge in _dig(node, key, "edges") or []:
                    text = _dig(edge, "node", "text")
                    if isinstance(text, str):
                        comments.append(text)
            caption = _dig(node, "edge_media_to_caption", "edges")
            preview = _dig(caption[0], "node", "text") if isinstance(caption, list) and caption else None
            return Extracted(metrics, comments, preview if isinstance(preview, str) else None)
    return Extracted()


def _threads_from_json(payloads: list[Any], post_id: str | None) -> Extracted:
    for payload in payloads:
        for node in iter_dicts(payload):
            info = node.get("text_post_app_info")
            if not isinstance(info, dict):
                continue
            if post_id and node.get("code") not in (post_id, None) and node.get("pk") != post_id:
                continue
            caption = _dig(node, "caption", "text")
            metrics = Metrics(
                likes=parse_count(node.get("like_count")),
                comments=parse_count(info.get("direct_reply_count")),
                shares=_sum_known(
                    parse_count(info.get("repost_count")), parse_count(info.get("quote_count"))
                ),
                views=parse_count(node.get("view_count")),
            )
            if metrics.known():
                return Extracted(metrics, [], caption if isinstance(caption, str) else None)
    return Extracted()


def _facebook_from_json(payloads: list[Any], post_id: str | None) -> Extracted:
    del post_id  # Facebook JSON'u gönderi kimliğini tutarlı vermez; ilk geri bildirim bloğu alınır
    for payload in payloads:
        for node in iter_dicts(payload):
            feedback = node.get("feedback") if isinstance(node.get("feedback"), dict) else node
            if not isinstance(feedback, dict):
                continue
            likes = _first_count(
                feedback, ("reaction_count", "count"), ("i18n_reaction_count",), ("reactors", "count")
            )
            comments = _first_count(
                feedback,
                ("comment_count", "total_count"),
                ("comments", "total_count"),
                ("total_comment_count",),
            )
            shares = _first_count(feedback, ("share_count", "count"), ("reshares", "count"))
            if likes is None and comments is None and shares is None:
                continue
            texts = [
                t
                for n in iter_dicts(payload)
                if n.get("__typename") == "Comment" and isinstance(t := _dig(n, "body", "text"), str)
            ]
            return Extracted(
                Metrics(likes, comments, shares, _first_count(node, ("video_view_count",))), texts, None
            )
    return Extracted()


def _reddit_from_json(payloads: list[Any], post_id: str | None) -> Extracted:
    del post_id
    for payload in payloads:
        if not (isinstance(payload, list) and payload):
            continue
        children = _dig(payload[0], "data", "children")
        if not (isinstance(children, list) and children):
            continue
        data = children[0].get("data") if isinstance(children[0], dict) else None
        if not isinstance(data, dict):
            continue
        comments: list[str] = []
        if len(payload) > 1:
            for child in _dig(payload[1], "data", "children") or []:
                body = _dig(child, "data", "body")
                if isinstance(body, str) and body not in ("[deleted]", "[removed]"):
                    comments.append(body)
        title = data.get("title") if isinstance(data.get("title"), str) else None
        selftext = data.get("selftext") if isinstance(data.get("selftext"), str) else ""
        return Extracted(
            Metrics(
                likes=parse_count(data.get("score")),
                comments=parse_count(data.get("num_comments")),
                shares=None,
                views=None,
            ),
            comments,
            ((title or "") + (" — " + selftext if selftext else "")).strip() or None,
        )
    return Extracted()


def _discourse_from_json(payloads: list[Any], post_id: str | None) -> Extracted:
    del post_id
    for payload in payloads:
        if not (isinstance(payload, dict) and "post_stream" in payload and "views" in payload):
            continue
        posts = _dig(payload, "post_stream", "posts") or []
        comments = [strip_html(p.get("cooked", "")) for p in posts[1:] if isinstance(p, dict)]
        title = payload.get("title") if isinstance(payload.get("title"), str) else None
        return Extracted(
            Metrics(
                parse_count(payload.get("like_count")),
                parse_count(payload.get("reply_count")),
                None,
                parse_count(payload.get("views")),
            ),
            [c for c in comments if c],
            title,
        )
    return Extracted()


_JSON_PARSERS = {
    "X": _x_from_json,
    "Instagram": _instagram_from_json,
    "Threads": _threads_from_json,
    "Facebook": _facebook_from_json,
    "Reddit": _reddit_from_json,
    "Forum": _discourse_from_json,
    "Other": _discourse_from_json,
}


def strip_html(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


# ----------------------------------------------------------------------- gömülü JSON, JSON-LD, meta

_SCRIPT_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/(?:ld\+)?json[\"'][^>]*>(.*?)</script>", re.S | re.I
)
_STATE_MARKER_RE = re.compile(
    r"(?:window\.)?(__INITIAL_STATE__|__additionalData\w*|_sharedData|__NEXT_DATA__|__APOLLO_STATE__)"
    r"\s*[=(]\s*",
)


def embedded_json(page_html: str) -> list[Any]:
    """<script type=application/json> blokları ve `__INITIAL_STATE__ = {...}` tarzı atamalar."""
    found: list[Any] = []
    for block in _SCRIPT_JSON_RE.findall(page_html):
        try:
            found.append(json.loads(html_lib.unescape(block)))
        except ValueError:
            continue
    decoder = json.JSONDecoder()
    for marker in _STATE_MARKER_RE.finditer(page_html):
        start = marker.end()
        if start < len(page_html) and page_html[start] in "{[":
            try:
                value, _ = decoder.raw_decode(page_html, start)
            except ValueError:
                continue
            found.append(value)
    return found


_LD_ACTIONS = {
    "likeaction": "likes",
    "commentaction": "comments",
    "shareaction": "shares",
    "watchaction": "views",
    "viewaction": "views",
}


def _ld_metrics(payloads: list[Any]) -> Extracted:
    values: dict[str, int | None] = {"likes": None, "comments": None, "shares": None, "views": None}
    comments: list[str] = []
    preview: str | None = None
    for payload in payloads:
        for node in iter_dicts(payload):
            stats = node.get("interactionStatistic")
            for stat in stats if isinstance(stats, list) else ([stats] if stats else []):
                if not isinstance(stat, dict):
                    continue
                kind = str(_dig(stat, "interactionType", "@type") or stat.get("interactionType") or "")
                key = _LD_ACTIONS.get(kind.rsplit("/", 1)[-1].lower())
                count = parse_count(stat.get("userInteractionCount"))
                if key and count is not None and values[key] is None:
                    values[key] = count
            if values["comments"] is None and parse_count(node.get("commentCount")) is not None:
                values["comments"] = parse_count(node.get("commentCount"))
            raw_comments = node.get("comment")
            for item in raw_comments if isinstance(raw_comments, list) else []:
                text = item.get("text") if isinstance(item, dict) else None
                if isinstance(text, str):
                    comments.append(text)
            if preview is None:
                head = node.get("articleBody") or node.get("description") or node.get("headline")
                if isinstance(head, str) and head.strip():
                    preview = head
    return Extracted(
        Metrics(values["likes"], values["comments"], values["shares"], values["views"]), comments, preview
    )


_META_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']([^\"']+)[\"'][^>]*content=[\"']([^\"']*)[\"']", re.I
)
_ITEMPROP_VIEWS_RE = re.compile(
    r"<meta[^>]+itemprop=[\"']interactionCount[\"'][^>]*content=[\"'](\d+)[\"']", re.I
)


def _meta(page_html: str) -> tuple[dict[str, str], int | None]:
    meta = {k.lower(): html_lib.unescape(v) for k, v in _META_RE.findall(page_html)}
    views = _ITEMPROP_VIEWS_RE.search(page_html)
    return meta, int(views.group(1)) if views else None


_ARIA_PATTERNS = {
    "likes": re.compile(
        r"([\d.,]+\s*[kKmMbB]?(?:\s?(?:bin|Mn))?)\s+(?:likes?|beğeni|reactions?|tepki)", re.I
    ),
    "comments": re.compile(r"([\d.,]+\s*[kKmMbB]?)\s+(?:repl(?:y|ies)|comments?|yanıt|yorum)", re.I),
    "shares": re.compile(r"([\d.,]+\s*[kKmMbB]?)\s+(?:reposts?|retweets?|shares?|paylaşım|yeniden)", re.I),
    "views": re.compile(r"([\d.,]+\s*[kKmMbB]?)\s+(?:views?|görüntüleme|izlenme|plays?)", re.I),
}
_ARIA_ATTR_RE = re.compile(r"aria-label=[\"']([^\"']{3,120})[\"']", re.I)


def _aria_fallback(page_html: str) -> Metrics:
    found: dict[str, int | None] = {"likes": None, "comments": None, "shares": None, "views": None}
    for label in _ARIA_ATTR_RE.findall(page_html):
        for key, pattern in _ARIA_PATTERNS.items():
            if found[key] is None and (m := pattern.search(label)):
                found[key] = parse_count(m.group(1).replace(" ", ""))
    return Metrics(found["likes"], found["comments"], found["shares"], found["views"])


# ----------------------------------------------------------------------------------- birleştirme


def extract(
    platform: Platform, post_id: str | None, page_html: str = "", json_payloads: list[Any] | None = None
) -> Extracted:
    """JSON durumu → JSON-LD/meta → aria-label sırasıyla doldurur; ilk bulunan değer korunur."""
    payloads = list(json_payloads or [])
    payloads.extend(embedded_json(page_html))
    parser = _JSON_PARSERS.get(platform)
    result = parser(payloads, post_id) if parser else Extracted()
    metrics = result.metrics
    comments = list(result.comments)
    preview = result.preview
    if page_html:
        ld = _ld_metrics(payloads)
        metrics = metrics.merged_with(ld.metrics)
        comments.extend(ld.comments)
        preview = preview or ld.preview
        meta, item_views = _meta(page_html)
        if metrics.views is None and item_views is not None:
            metrics = Metrics(metrics.likes, metrics.comments, metrics.shares, item_views)
        preview = preview or meta.get("og:description") or meta.get("og:title")
        if not metrics.known():
            metrics = _aria_fallback(page_html)
    return Extracted(metrics, _dedupe(comments), preview)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


# ------------------------------------------------------------------------------ engel tespiti

_LOGIN_URL_RE = re.compile(r"/(?:accounts/)?login|/i/flow/login|/signin|/log_in|/checkpoint/?\?next", re.I)
_LOGIN_TITLE_RE = re.compile(r"^(?:log in|login|sign in|giriş yap|oturum aç)", re.I)
_CHALLENGE_URL_RE = re.compile(r"/challenge|/checkpoint|captcha|/sorry/", re.I)
_CHALLENGE_BODY_RE = re.compile(
    r"unusual traffic|are you a robot|verify you are human|challenge_required|captcha-delivery|"
    r"çok fazla istek|olağandışı trafik",
    re.I,
)
SMALL_PAGE = 30_000


def detect_block(final_url: str, title: str, page_html: str, status: int | None) -> str | None:
    """'CHALLENGE' (bot koruması/hız sınırı), 'LOGIN' (giriş duvarı) ya da None.

    Bu sinyaller ATLATILMAZ: CHALLENGE → platform duraklatılır, LOGIN → kullanıcıdan giriş istenir.
    """
    if status in (403, 429) or _CHALLENGE_URL_RE.search(final_url):
        return "CHALLENGE"
    if title and _CHALLENGE_BODY_RE.search(title):
        return "CHALLENGE"
    if len(page_html) < SMALL_PAGE and _CHALLENGE_BODY_RE.search(page_html):
        return "CHALLENGE"
    if _LOGIN_URL_RE.search(final_url) or (title and _LOGIN_TITLE_RE.match(title.strip())):
        return "LOGIN"
    return None
