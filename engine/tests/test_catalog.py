from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from etkilesim import catalog, cli, community, dashboard, people, posts
from etkilesim.errors import NotFound, PermissionDenied, ValidationFailed

from .helpers import make_user, public_resolver


def add(conn: sqlite3.Connection, uid: int, url: str, t: datetime, **kw: object) -> int:
    return posts.add_post(conn, uid, url, now=t, resolver=public_resolver, **kw).post_id  # type: ignore[arg-type]


def test_game_crud_and_validation(conn: sqlite3.Connection, t0: datetime) -> None:
    gid = catalog.create_game(
        conn,
        {
            "name": "Project Nova",
            "genres": ["FPS", "Extraction Shooter"],
            "keywords": ["pvpve"],
            "steam_url": "https://store.steampowered.com/app/1",
        },
        "admin",
        t0,
    )
    with pytest.raises(ValidationFailed):
        catalog.create_game(conn, {"name": "project nova"}, "admin")
    with pytest.raises(ValidationFailed):
        catalog.create_game(conn, {"name": "B", "steam_url": "javascript:alert(1)"}, "admin")
    with pytest.raises(ValidationFailed):
        catalog.create_game(conn, {"name": "C", "genres": "FPS"}, "admin")
    catalog.update_game(conn, gid, {"status": "archived", "genres": ["FPS"]}, "admin")
    game = catalog.list_games(conn)[0]
    assert game["genres"] == ["FPS"] and game["status"] == "archived" and game["keywords"] == ["pvpve"]
    with pytest.raises(NotFound):
        catalog.update_game(conn, 999, {"status": "active"}, "admin")


def test_campaign_crud_dates_and_platforms(conn: sqlite3.Connection, t0: datetime) -> None:
    gid = catalog.create_game(conn, {"name": "Nova"}, "admin", t0)
    cid = catalog.create_campaign(
        conn,
        {
            "name": "Beta Duyurusu",
            "game_id": gid,
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "target_platforms": ["X", "Reddit"],
        },
        "admin",
        t0,
    )
    with pytest.raises(ValidationFailed):
        catalog.create_campaign(
            conn, {"name": "Ters", "start_date": "2026-10-10", "end_date": "2026-10-01"}, "admin"
        )
    with pytest.raises(ValidationFailed):
        catalog.create_campaign(conn, {"name": "P", "target_platforms": ["MySpace"]}, "admin")
    with pytest.raises(NotFound):
        catalog.create_campaign(conn, {"name": "Q", "game_id": 999}, "admin")
    catalog.update_campaign(conn, cid, {"status": "finished"}, "admin")
    camp = catalog.list_campaigns(conn)[0]
    assert camp["status"] == "finished" and camp["game_name"] == "Nova"
    assert camp["target_platforms"] == ["X", "Reddit"] and camp["end_date"] == "2026-10-31"


def test_post_links_game_campaign_and_content_type(conn: sqlite3.Connection, t0: datetime) -> None:
    gid = catalog.create_game(conn, {"name": "Nova"}, "admin", t0)
    other = catalog.create_game(conn, {"name": "Other"}, "admin", t0)
    cid = catalog.create_campaign(conn, {"name": "Beta", "game_id": gid}, "admin", t0)
    uid = make_user(conn, now=t0)
    pid = add(
        conn,
        uid,
        "https://x.com/a/status/1",
        t0,
        campaign_id=cid,
        content_type="video",
        community_name="r/FPS",
    )
    post = posts.post_detail(conn, pid)["post"]
    assert (post["game_id"], post["campaign_name"], post["game_name"], post["content_type"]) == (
        gid,
        "Beta",
        "Nova",
        "video",
    )
    with pytest.raises(ValidationFailed):
        add(conn, uid, "https://x.com/a/status/2", t0, campaign_id=cid, game_id=other)
    with pytest.raises(ValidationFailed):
        add(conn, uid, "https://x.com/a/status/3", t0, content_type="story")
    assert community.posting_context(conn, name="r/FPS", now=t0)["last_post"]["campaign"] == "Beta"
    camp = catalog.list_campaigns(conn)[0]
    assert camp["posts"] == 1
    state = dashboard.get_state(conn, now=t0)
    assert state["posts"][0]["campaign_name"] == "Beta" and state["campaigns"][0]["name"] == "Beta"


def test_archived_campaign_rejects_new_posts(conn: sqlite3.Connection, t0: datetime) -> None:
    cid = catalog.create_campaign(conn, {"name": "Eski", "status": "archived"}, "admin", t0)
    uid = make_user(conn, now=t0)
    with pytest.raises(ValidationFailed):
        add(conn, uid, "https://x.com/a/status/1", t0, campaign_id=cid)


def test_viewer_role_is_read_only(conn: sqlite3.Connection, t0: datetime) -> None:
    vid = people.create_user(conn, "Gözlemci", None, "viewer", None, "admin", t0)
    with pytest.raises(PermissionDenied):
        add(conn, vid, "https://x.com/a/status/1", t0)


def test_archive_hides_post_everywhere_but_keeps_it(conn: sqlite3.Connection, t0: datetime) -> None:
    uid = make_user(conn, now=t0)
    pid = add(conn, uid, "https://x.com/a/status/1", t0, community_name="r/FPS")
    posts.set_archived(conn, pid, True, "admin", t0)
    assert dashboard.get_state(conn, now=t0)["posts"] == []
    assert dashboard.get_state(conn, now=t0)["kpis"]["posts"] == 0
    assert posts.due_posts(conn, t0 + timedelta(days=1)) == []
    assert community.posting_context(conn, name="r/FPS", now=t0)["recommendation"] == "CLEAN"
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 1  # silinmedi
    posts.set_archived(conn, pid, False, "admin", t0)
    assert len(dashboard.get_state(conn, now=t0)["posts"]) == 1
    with pytest.raises(NotFound):
        posts.set_archived(conn, 999, True, "admin", t0)


def test_catalog_commands_need_admin(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cli.PIN_ENV, raising=False)
    for name in ("add-game", "add-campaign", "update-game", "update-campaign", "archive-post"):
        with pytest.raises(PermissionDenied):
            cli.dispatch(name, {}, conn)
