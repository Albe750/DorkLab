"""Percorsi standard XDG usati dall'applicazione."""

from __future__ import annotations

import os
from pathlib import Path

from . import APP_ID

_PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = _PKG_DIR / "data"


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    base = Path(value) if value else Path.home() / default
    return base / APP_ID


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache")


def default_download_dir() -> Path:
    return data_dir() / "downloads"


def ensure_dirs() -> None:
    for path in (config_dir(), data_dir(), cache_dir(), default_download_dir()):
        path.mkdir(parents=True, exist_ok=True)
