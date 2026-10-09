"""Yol ve ortam yapılandırması. Sırlar burada tutulmaz (bkz. secrets_store)."""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "EtkilesimTakip"


def data_dir() -> Path:
    override = os.environ.get("ETKILESIM_DATA_DIR")
    if override:
        base = Path(override)
    else:
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) / APP_DIR_NAME if local else Path.home() / ".etkilesim-takip"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "etkilesim.db"


def profile_dir() -> Path:
    """Tarayıcı oturum profili (kullanıcının kendi girişi burada kalır)."""
    path = data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return data_dir() / "engine.log"


def lock_path() -> Path:
    return data_dir() / "daemon.lock"
