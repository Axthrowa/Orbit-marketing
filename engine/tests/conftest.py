from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from etkilesim import db

T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def t0() -> datetime:
    return T0
