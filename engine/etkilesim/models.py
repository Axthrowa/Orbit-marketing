"""Ölçüm sonucu veri modelleri. Bilinmeyen sayaç None'dır; 0 ile karıştırılmaz."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DataStatus = Literal["OK", "DATA_UNAVAILABLE", "AUTHORIZATION_REQUIRED"]
SourceKind = Literal["SCRAPE", "HTTP", "MANUAL", "MOCK"]


@dataclass(frozen=True)
class Metrics:
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    views: int | None = None

    def known(self) -> bool:
        return any(v is not None for v in (self.likes, self.comments, self.shares, self.views))

    def merged_with(self, other: Metrics) -> Metrics:
        """Alanları `other`'dan doldurur; mevcut (None olmayan) değerler korunur."""
        return Metrics(
            likes=self.likes if self.likes is not None else other.likes,
            comments=self.comments if self.comments is not None else other.comments,
            shares=self.shares if self.shares is not None else other.shares,
            views=self.views if self.views is not None else other.views,
        )


@dataclass
class CollectResult:
    status: DataStatus
    metrics: Metrics = field(default_factory=Metrics)
    comment_texts: list[str] = field(default_factory=list)
    preview_text: str | None = None
    source: SourceKind = "HTTP"
    error: str | None = None
    blocked: bool = False  # bot koruması / meydan okuma görüldü → platform duraklatılır
