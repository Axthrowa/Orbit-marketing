"""SSRF korumalı, boyut/süre sınırlı, host başına yavaşlatılmış HTTP istemcisi (yalnızca stdlib)."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import Any
from urllib.parse import urlsplit

from .errors import ProviderUnavailable
from .security import Resolver, validate_public_url

USER_AGENT = "EtkilesimTakip/0.1 (masaüstü uygulaması; created by axthrowa)"
MAX_BYTES = 2_000_000
MIN_HOST_INTERVAL = 2.0
MAX_REDIRECTS = 5


@dataclass(frozen=True)
class FetchResult:
    status: int
    text: str
    final_url: str


class Throttle:
    """Aynı sunucuya art arda istekleri en az `interval` saniye aralıkla gönderir."""

    def __init__(
        self,
        interval: float = MIN_HOST_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._sleep = sleeper
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        previous = self._last.get(host)
        if previous is not None:
            remaining = self._interval - (self._clock() - previous)
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()


DEFAULT_THROTTLE = Throttle()


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, resolver: Resolver | None) -> None:
        self._resolver = resolver

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        validate_public_url(newurl, self._resolver)  # her yönlendirmede yeniden denetim
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    resolver: Resolver | None = None,
    throttle: Throttle | None = DEFAULT_THROTTLE,
) -> FetchResult:
    """Güvenli adrese GET. HTTP 4xx/5xx istisna DEĞİL, durum koduyla döner (429 tespiti için)."""
    safe = validate_public_url(url, resolver)
    if throttle is not None:
        throttle.wait(urlsplit(safe).netloc)
    opener = urllib.request.build_opener(_SafeRedirects(resolver))
    request = urllib.request.Request(  # noqa: S310 - şema validate_public_url ile http(s)'e kısıtlı
        safe,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
            "Accept-Language": "tr,en;q=0.8",
            **(headers or {}),
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            return FetchResult(
                response.status, body[:MAX_BYTES].decode("utf-8", "replace"), response.geturl()
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BYTES) if exc.fp else b""
        return FetchResult(exc.code, body.decode("utf-8", "replace"), exc.geturl() or safe)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable(f"Ağ hatası: {exc.__class__.__name__}") from exc
