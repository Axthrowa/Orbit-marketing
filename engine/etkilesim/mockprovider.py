"""Geliştirme sağlayıcısı (master prompt §89): `ETKILESIM_PROVIDER_MODE=mock`.

Ağ ve tarayıcı kullanılmaz; gönderi kimliğinden türetilen, zamanla doygunluğa giden gerçekçi
sayılar üretilir. Kaynak her zaman `MOCK` yazılır ve arayüz "MOCK DATA" rozeti gösterir — üretimde
gerçek veri gibi görünmez.
"""

from __future__ import annotations

import math
import os
import random
from datetime import datetime

from .models import CollectResult, Metrics

ENV = "ETKILESIM_PROVIDER_MODE"
_BASE = {"X": 180, "Instagram": 420, "Facebook": 90, "Threads": 120, "Reddit": 260, "YouTube": 900}
_SAMPLE_COMMENTS = (
    "Harika görünüyor, wishlist'e ekledim!",
    "Fiyatı ne kadar olacak?",
    "Bug dolu görünüyor, optimizasyon şart",
    "Can't wait to play this",
    "Grafikler çok güzel olmuş",
    "Sunucu ping çok yüksekti betada",
    "Keşke co-op modu eklenmeli",
    "This looks like a cash grab",
)


def provider_mode() -> str:
    return "mock" if os.environ.get(ENV, "").strip().lower() == "mock" else "real"


def collect(
    post_id: int, platform: str, posted_at: datetime, now: datetime, comment_limit: int
) -> CollectResult:
    rng = random.Random(post_id)  # noqa: S311 - kriptografik değil; tekrarlanabilir sahte veri
    scale = _BASE.get(platform, 60) * rng.uniform(0.4, 1.8)
    hours = max(0.0, (now - posted_at).total_seconds() / 3600)
    growth = 1 - math.exp(-hours / 30)
    likes = int(scale * growth)
    comments = int(likes * rng.uniform(0.05, 0.18))
    shares = int(likes * rng.uniform(0.02, 0.1))
    views = int(likes * rng.uniform(12, 40)) if platform in {"X", "YouTube", "Instagram", "Threads"} else None
    count = min(comment_limit, max(0, comments // 3), len(_SAMPLE_COMMENTS))
    texts = rng.sample(_SAMPLE_COMMENTS, count)
    return CollectResult("OK", Metrics(likes, comments, shares, views), texts, None, "MOCK")
