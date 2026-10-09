"""Zaman yardımcıları. Tüm saklanan zamanlar UTC ISO-8601; test saati `now` parametresiyle verilir."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def to_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("Saat dilimi olmayan zaman kabul edilmez")
    return moment.astimezone(UTC).strftime(ISO_FORMAT)


def from_iso(text: str) -> datetime:
    parsed = datetime.strptime(text, ISO_FORMAT)
    return parsed.replace(tzinfo=UTC)


def days_between(earlier: datetime, later: datetime) -> int:
    """Tam gün farkı (aşağı yuvarlanır, negatif olmaz)."""
    return max(0, (later - earlier).days)


def hours(count: float) -> timedelta:
    return timedelta(hours=count)
