"""Ölçüm toplayıcıları.

* `HttpCollector`: herkese açık uç noktalar (Reddit JSON, Discourse JSON, JSON-LD/OpenGraph sayfaları).
* `BrowserCollector`: gerçek bir Edge/Chrome penceresi + KULLANICININ KENDİ giriş oturumu.

Bilinçli sınırlar: `playwright-stealth`, parmak izi taklidi, otomasyon bayrağı gizleme,
CAPTCHA çözme veya giriş duvarı aşma YOKTUR. Giriş istenirse AUTHORIZATION_REQUIRED,
bot koruması/hız sınırı görülürse DATA_UNAVAILABLE + platform duraklatma uygulanır.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import parsers
from .errors import ProviderUnavailable, UnsafeUrl
from .httpclient import FetchResult, fetch
from .models import CollectResult
from .platforms import BROWSER_PLATFORMS, Platform, registrable_matches
from .security import Resolver, validate_public_url

FetchFn = Callable[[str], FetchResult]
Sleeper = Callable[[float], Awaitable[None]]
Jitter = Callable[[float, float], float]

NAV_TIMEOUT_MS = 30_000
SCROLL_ROUNDS = 3
RESPONSE_LIMIT = 2_000_000
_BLOCKED_RESOURCES = {"image", "media", "font"}

LOGIN_URLS: dict[str, str] = {
    "X": "https://x.com/i/flow/login",
    "Instagram": "https://www.instagram.com/accounts/login/",
    "Facebook": "https://www.facebook.com/login/",
    "Threads": "https://www.threads.net/login",
}

# Yedek DOM seçicileri (JSON durumu bulunamazsa). Sık değişir; doğrulanmamıştır.
COMMENT_SELECTORS: dict[str, str] = {
    "X": 'article[data-testid="tweet"] div[data-testid="tweetText"]',
    "Facebook": 'div[role="article"] div[dir="auto"]',
}


@dataclass(frozen=True)
class PostRef:
    id: int
    url: str
    platform: Platform
    post_id: str | None


def _result_from(extracted: parsers.Extracted, source: str, limit: int) -> CollectResult:
    if not extracted.metrics.known() and not extracted.comments:
        return CollectResult("DATA_UNAVAILABLE", error="Sayfada ölçülebilir sayaç bulunamadı", source=source)  # type: ignore[arg-type]
    return CollectResult("OK", extracted.metrics, extracted.comments[:limit], extracted.preview, source)  # type: ignore[arg-type]


class HttpCollector:
    def __init__(self, fetch_fn: FetchFn = fetch) -> None:
        self._fetch = fetch_fn

    def collect(self, ref: PostRef, comment_limit: int) -> CollectResult:
        try:
            return self._collect(ref, comment_limit)
        except UnsafeUrl as exc:
            return CollectResult(
                "DATA_UNAVAILABLE", error=f"Güvensiz yönlendirme: {exc.message}", source="HTTP"
            )
        except ProviderUnavailable as exc:
            return CollectResult("DATA_UNAVAILABLE", error=exc.message, source="HTTP")

    def _collect(self, ref: PostRef, limit: int) -> CollectResult:
        if ref.platform in BROWSER_PLATFORMS:
            return CollectResult(
                "AUTHORIZATION_REQUIRED", error="Bu platform için tarayıcı ölçümü gerekir", source="HTTP"
            )
        for url in self._candidate_urls(ref, limit):
            response = self._fetch(url)
            block = parsers.detect_block(response.final_url, "", response.text, response.status)
            if response.status in (404, 410):
                return CollectResult(
                    "DATA_UNAVAILABLE", error="Gönderi bulunamadı veya silinmiş", source="HTTP"
                )
            if block == "CHALLENGE":
                return CollectResult(
                    "DATA_UNAVAILABLE",
                    error=f"Hız sınırı/bot koruması (HTTP {response.status})",
                    source="HTTP",
                    blocked=True,
                )
            if response.status >= 400:
                continue
            payloads: list[Any] = []
            html = ""
            if url.endswith(".json") or "/.json" in url or ".json?" in url:
                try:
                    payloads.append(json.loads(response.text))
                except ValueError:
                    continue
            else:
                html = response.text
            extracted = parsers.extract(ref.platform, ref.post_id, html, payloads)
            result = _result_from(extracted, "HTTP", limit)
            if result.status == "OK":
                return result
        return CollectResult("DATA_UNAVAILABLE", error="Herkese açık veri alınamadı", source="HTTP")

    @staticmethod
    def _candidate_urls(ref: PostRef, limit: int) -> list[str]:
        if ref.platform == "Reddit" and ref.post_id:
            return [f"https://www.reddit.com/comments/{ref.post_id}.json?limit={limit}&raw_json=1"]
        parts = urlsplit(ref.url)
        urls = []
        if re.search(r"/t/(?:[^/]+/)?\d+", parts.path):  # Discourse konu adresi
            urls.append(f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}.json")
        urls.append(ref.url)
        return urls


# --------------------------------------------------------------------------------- tarayıcı


async def _human_pause(sleep: Sleeper, jitter: Jitter, low: float = 2.0, high: float = 5.0) -> None:
    """Sayfa yüklemeleri arasında nazik bekleme (sunucuyu yormamak için)."""
    await sleep(jitter(low, high))


class BrowserCollector:
    """Kullanıcının kalıcı tarayıcı profilini kullanır; giriş yalnızca kullanıcı tarafından yapılır."""

    def __init__(
        self,
        profile_dir: Path,
        headless: bool = True,
        sleep: Sleeper = asyncio.sleep,
        jitter: Jitter = random.uniform,
        channels: tuple[str, ...] = ("msedge", "chrome"),
        resolver: Resolver | None = None,
    ) -> None:
        self._profile = profile_dir
        self._headless = headless
        self._sleep = sleep
        self._jitter = jitter
        self._channels = channels
        self._resolver = resolver
        self._playwright: Any = None
        self._context: Any = None

    async def __aenter__(self) -> BrowserCollector:
        await self._open(headless=self._headless)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _open(self, headless: bool) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ProviderUnavailable("playwright kurulu değil (pip install playwright)") from exc
        self._playwright = await async_playwright().start()
        last_error: Exception | None = None
        for channel in self._channels:
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(self._profile),
                    channel=channel,
                    headless=headless,
                    viewport={"width": 1280, "height": 900},
                    locale="tr-TR",
                )
                return
            except Exception as exc:  # noqa: BLE001 - sıradaki tarayıcıyı dene
                last_error = exc
        await self._playwright.stop()
        self._playwright = None
        raise ProviderUnavailable(
            f"Edge/Chrome başlatılamadı: {last_error.__class__.__name__ if last_error else '?'}"
        )

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def collect(self, ref: PostRef, comment_limit: int) -> CollectResult:
        if self._context is None:
            raise ProviderUnavailable("Tarayıcı açık değil")
        try:
            validate_public_url(ref.url, self._resolver)
        except UnsafeUrl as exc:
            return CollectResult("DATA_UNAVAILABLE", error=exc.message, source="SCRAPE")
        page = await self._context.new_page()
        payloads: list[Any] = []
        tasks: list[asyncio.Task[None]] = []

        async def capture(response: Any) -> None:
            try:
                kind = (await response.all_headers()).get("content-type", "")
                if "json" not in kind or not registrable_matches(response.url, ref.platform):
                    return
                body = await response.body()
                if len(body) <= RESPONSE_LIMIT:
                    payloads.append(json.loads(body))
            except Exception:  # noqa: BLE001 - kapanan/okunamayan yanıtlar yok sayılır
                return

        async def block_heavy(route: Any) -> None:
            if route.request.resource_type in _BLOCKED_RESOURCES:
                await route.abort()
            else:
                await route.continue_()

        try:
            await page.route("**/*", block_heavy)
            page.on("response", lambda r: tasks.append(asyncio.create_task(capture(r))))
            response = await page.goto(ref.url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            await _human_pause(self._sleep, self._jitter)
            status = response.status if response else None
            final_url = page.url
            try:
                validate_public_url(final_url, self._resolver)
            except UnsafeUrl as exc:
                return CollectResult(
                    "DATA_UNAVAILABLE", error=f"Güvensiz yönlendirme: {exc.message}", source="SCRAPE"
                )
            title = await page.title()
            html = await page.content()
            block = parsers.detect_block(final_url, title, html, status)
            if block == "LOGIN":
                return CollectResult(
                    "AUTHORIZATION_REQUIRED",
                    error=f"{ref.platform} giriş istiyor; Ayarlar'dan oturum açın",
                    source="SCRAPE",
                )
            if block == "CHALLENGE":
                return CollectResult(
                    "DATA_UNAVAILABLE",
                    blocked=True,
                    source="SCRAPE",
                    error="Bot koruması/hız sınırı görüldü; platform duraklatıldı",
                )
            if not registrable_matches(final_url, ref.platform):
                return CollectResult(
                    "DATA_UNAVAILABLE", error="Beklenmeyen sayfaya yönlendirildi", source="SCRAPE"
                )
            for _ in range(SCROLL_ROUNDS):  # yorumların yüklenmesi için ölçülü kaydırma
                await page.mouse.wheel(0, 700)
                await self._sleep(self._jitter(1.0, 2.0))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            html = await page.content()
            extracted = parsers.extract(ref.platform, ref.post_id, html, payloads)
            if len(extracted.comments) < 3 and ref.platform in COMMENT_SELECTORS:
                extracted.comments.extend(await self._dom_comments(page, ref.platform))
            return _result_from(extracted, "SCRAPE", comment_limit)
        except ProviderUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - Playwright zaman aşımı/kapanma vb.
            return CollectResult(
                "DATA_UNAVAILABLE", source="SCRAPE", error=f"Sayfa okunamadı: {exc.__class__.__name__}"
            )
        finally:
            await page.close()

    @staticmethod
    async def _dom_comments(page: Any, platform: str) -> list[str]:
        try:
            texts = await page.locator(COMMENT_SELECTORS[platform]).all_inner_texts()
        except Exception:  # noqa: BLE001
            return []
        return [t.strip() for t in texts[1:] if t.strip()]  # ilki gönderinin kendisi

    async def interactive_login(self, platform: str, timeout_s: float = 600) -> None:
        """Görünür pencere açar; kullanıcı kendi hesabıyla girip pencereyi kapatır."""
        url = LOGIN_URLS.get(platform)
        if url is None:
            raise ProviderUnavailable("Bu platform için oturum açma gerekmez")
        await self.close()
        await self._open(headless=False)
        page = await self._context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        closed = asyncio.Event()
        page.on("close", lambda _p: closed.set())
        try:
            await asyncio.wait_for(closed.wait(), timeout=timeout_s)
        except TimeoutError:
            pass
        finally:
            await self.close()


async def collect_ref(
    ref: PostRef,
    comment_limit: int,
    http: HttpCollector,
    browser: BrowserCollector | None,
) -> CollectResult:
    if ref.platform in BROWSER_PLATFORMS:
        if browser is None:
            return CollectResult(
                "DATA_UNAVAILABLE", source="SCRAPE", error="Tarayıcı ölçümü kapalı veya kullanılamıyor"
            )
        return await browser.collect(ref, comment_limit)
    return await asyncio.to_thread(http.collect, ref, comment_limit)
