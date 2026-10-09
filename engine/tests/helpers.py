"""Test yardımcıları: ağ erişimi olmayan çözümleyici ve sahte gönderici."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from etkilesim import people
from etkilesim.notify import SendError


def public_resolver(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


def make_user(
    conn: sqlite3.Connection,
    name: str = "Ahmet",
    team: str | None = "Marketing A",
    telegram: str | None = "111222",
    now: datetime | None = None,
) -> int:
    team_id = None
    if team is not None:
        row = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()
        team_id = int(row["id"]) if row else people.create_team(conn, team, None, "t", now)
    return people.create_user(conn, name, team_id, "member", telegram, "t", now)


class FakeSender:
    def __init__(self, fail: list[SendError] | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = list(fail or [])

    def send(self, target: str, text: str) -> None:
        if self.fail:
            raise self.fail.pop(0)
        self.sent.append((target, text))
