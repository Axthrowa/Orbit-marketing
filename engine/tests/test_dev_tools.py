"""P9: uyarlanabilir takvim, mock sağlayıcı, tohum verisi, metrikler, sözleşme sürümü."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta

import pytest

from etkilesim import cli, dashboard, posts, refresh, settings, system
from etkilesim.errors import ValidationFailed
from etkilesim.models import CollectResult, Metrics
from etkilesim.sentiment import LexiconEngine

from .helpers import make_user, public_resolver


def test_adaptive_ladder() -> None:
    posted = datetime(2026, 10, 1, 12, 0).astimezone()
    steps = []
    last = posted
    for _ in range(7):
        last = posts.next_adaptive_due(posted, last)
        steps.append((last - posted).total_seconds() / 3600)
    assert steps == [1, 3, 6, 12, 24, 48, 72]  # sonra günlük
    assert posts.next_adaptive_due(posted, posted + timedelta(days=10)) == posted + timedelta(
        days=12
    )  # 48 sa
    assert posts.next_adaptive_due(posted, posted + timedelta(days=40)) == posted + timedelta(
        days=47
    )  # haftalık


def test_adaptive_schedule_drives_due_posts(conn: sqlite3.Connection, t0: datetime) -> None:
    settings.set_value(conn, "metrics_schedule", "adaptive", "admin")
    uid = make_user(conn, now=t0)
    pid = posts.add_post(conn, uid, "https://x.com/a/status/1", now=t0, resolver=public_resolver).post_id
    posts.record_collect(conn, pid, CollectResult("OK", Metrics(likes=1)), LexiconEngine(), t0)
    assert posts.due_posts(conn, t0 + timedelta(minutes=59)) == []
    assert len(posts.due_posts(conn, t0 + timedelta(hours=1))) == 1


def test_mock_provider_mode_marks_data(
    conn: sqlite3.Connection, t0: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ETKILESIM_PROVIDER_MODE", "mock")
    uid = make_user(conn, now=t0)
    pid = posts.add_post(conn, uid, "https://x.com/a/status/1", now=t0, resolver=public_resolver).post_id
    summary = asyncio.run(refresh.refresh(conn, now=t0 + timedelta(hours=30), engine=LexiconEngine()))
    assert summary.ok == 1
    state = dashboard.get_state(conn, now=t0 + timedelta(hours=30))
    assert state["provider_mode"] == "mock" and state["posts"][0]["last_source"] == "MOCK"
    assert state["posts"][0]["likes"] is not None
    assert posts.post_detail(conn, pid)["snapshots"][0]["source"] == "MOCK"
    monkeypatch.delenv("ETKILESIM_PROVIDER_MODE")
    assert cli.dispatch("health", {}, conn)["provider_mode"] == "real"


def test_seed_demo_creates_full_dataset_once(conn: sqlite3.Connection, t0: datetime) -> None:
    from etkilesim import seed

    counts = seed.seed_demo(conn, t0)
    assert (counts["teams"], counts["users"], counts["games"], counts["campaigns"]) == (2, 6, 3, 4)
    assert counts["posts"] == 30 and counts["communities"] == 20
    assert counts["snapshots"] > 30 and counts["comments"] > 0
    assert counts["warnings"] > 0 and counts["notifications"] > 0
    assert conn.execute("SELECT COUNT(*) FROM users WHERE status='flagged'").fetchone()[0] >= 1
    assert {r[0] for r in conn.execute("SELECT DISTINCT source FROM post_metric_snapshots")} == {"MOCK"}
    with pytest.raises(ValidationFailed):
        seed.seed_demo(conn, t0)


def test_metrics_text_is_prometheus_format(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    posts.add_post(conn, uid, "https://x.com/a/status/1", now=t0, resolver=public_resolver)
    text = system.metrics_text(conn, t0)
    assert "# TYPE etkilesim_posts gauge" in text
    assert 'etkilesim_posts{platform="X"} 1' in text
    assert "etkilesim_comments_analyzed_total 0" in text


def test_health_reports_contract_version(conn: sqlite3.Connection) -> None:
    health = cli.dispatch("health", {}, conn)
    assert health["api_version"] == "v1" and health["schema_version"] >= 2
