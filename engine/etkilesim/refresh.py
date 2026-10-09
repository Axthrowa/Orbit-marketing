"""Zamanı gelen gönderileri ölçer: toplayıcı → kayıt → sağlayıcı durumu. Hata olsa da kayıt silinmez."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import mockprovider, posts, providers, settings
from .clock import from_iso, now_utc
from .collectors import BrowserCollector, HttpCollector, PostRef, collect_ref
from .errors import ProviderUnavailable
from .models import CollectResult
from .platforms import BROWSER_PLATFORMS, Platform
from .sentiment import SentimentEngine, get_engine

BrowserFactory = Callable[[], AbstractAsyncContextManager[BrowserCollector]]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass
class RefreshSummary:
    checked: int = 0
    ok: int = 0
    unavailable: int = 0
    auth_required: int = 0
    skipped_paused: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "ok": self.ok,
            "unavailable": self.unavailable,
            "auth_required": self.auth_required,
            "skipped_paused": self.skipped_paused,
            "errors": self.errors,
        }


async def refresh(
    conn: Any,
    now: datetime | None = None,
    post_ids: list[int] | None = None,
    limit: int = 50,
    http: HttpCollector | None = None,
    browser_factory: BrowserFactory | None = None,
    engine: SentimentEngine | None = None,
    sleep: Sleeper = asyncio.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> RefreshSummary:
    moment = now or now_utc()
    summary = RefreshSummary()
    if post_ids:
        marks = ",".join("?" for _ in post_ids)
        rows = conn.execute(f"SELECT * FROM posts WHERE id IN ({marks})", post_ids).fetchall()  # noqa: S608
    else:
        rows = posts.due_posts(conn, moment, limit)
    if not rows:
        return summary
    sentiment = engine or get_engine(str(settings.get(conn, "sentiment_engine")))
    collector = http or HttpCollector()
    comment_limit = int(settings.get(conn, "comment_limit"))
    if mockprovider.provider_mode() == "mock":
        for row in rows:  # geliştirme: ağ/tarayıcı yok, kaynak MOCK olarak işaretlenir
            result = mockprovider.collect(
                int(row["id"]), str(row["platform"]), from_iso(row["posted_at"]), moment, comment_limit
            )
            posts.record_collect(conn, int(row["id"]), result, sentiment, moment, comment_limit)
            summary.checked += 1
            summary.ok += 1
        return summary
    scrape_enabled = bool(settings.get(conn, "scrape_enabled"))
    needs_browser = scrape_enabled and any(r["platform"] in BROWSER_PLATFORMS for r in rows)
    async with AsyncExitStack() as stack:
        browser: BrowserCollector | None = None
        if needs_browser and browser_factory is not None:
            try:
                browser = await stack.enter_async_context(browser_factory())
            except ProviderUnavailable as exc:
                summary.errors.append(exc.message)
        previous_browser_fetch = False
        for row in rows:
            platform: Platform = row["platform"]
            if providers.is_paused(conn, platform, moment):
                summary.skipped_paused += 1
                continue
            uses_browser = platform in BROWSER_PLATFORMS
            if uses_browser and previous_browser_fetch:
                await sleep(jitter(2.0, 5.0))  # tarayıcı sayfa yüklemeleri arasında nazik bekleme
            ref = PostRef(int(row["id"]), str(row["url"]), platform, row["platform_post_id"])
            result = await _safe_collect(
                ref, comment_limit, collector, browser if scrape_enabled else None, summary
            )
            previous_browser_fetch = uses_browser and result.status != "DATA_UNAVAILABLE"
            posts.record_collect(conn, ref.id, result, sentiment, moment, comment_limit)
            summary.checked += 1
            _track(conn, platform, result, moment, summary)
    return summary


async def _safe_collect(
    ref: PostRef,
    limit: int,
    http: HttpCollector,
    browser: BrowserCollector | None,
    summary: RefreshSummary,
) -> CollectResult:
    try:
        return await collect_ref(ref, limit, http, browser)
    except ProviderUnavailable as exc:
        summary.errors.append(exc.message)
        return CollectResult("DATA_UNAVAILABLE", error=exc.message)
    except Exception as exc:  # noqa: BLE001 - tek gönderideki beklenmedik hata turu durdurmasın
        summary.errors.append(f"{exc.__class__.__name__}")
        return CollectResult("DATA_UNAVAILABLE", error=f"Beklenmeyen hata: {exc.__class__.__name__}")


def _track(
    conn: Any, platform: Platform, result: CollectResult, moment: datetime, summary: RefreshSummary
) -> None:
    if result.status == "OK":
        providers.record_success(conn, platform, moment)
        summary.ok += 1
    elif result.status == "AUTHORIZATION_REQUIRED":
        providers.record_failure(conn, platform, result.error or "Giriş gerekli", False, moment)
        summary.auth_required += 1
    else:
        providers.record_failure(conn, platform, result.error or "Veri alınamadı", result.blocked, moment)
        summary.unavailable += 1
