"""Resolve per-device after-sales paths without machine-specific constants."""

from __future__ import annotations

import json
import os
from pathlib import Path


def support_home() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "AfterSalesSupport"
    return Path.home() / ".after-sales-support"


def config_path() -> Path:
    override = os.environ.get("AFTERSALES_CONFIG_PATH")
    return Path(override) if override else support_home() / "config" / "settings.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def cache_root() -> Path:
    override = os.environ.get("AFTERSALES_CACHE_DIR") or os.environ.get("KB_CACHE_BASE")
    if override:
        return Path(override)
    configured = load_config().get("cache_root")
    if configured:
        return Path(configured)
    legacy = Path.cwd() / "_售后模板缓存"
    if legacy.exists():
        return legacy
    return support_home() / "cache"


def data_root() -> Path:
    override = os.environ.get("AFTERSALES_DATA_ROOT")
    if override:
        return Path(override)
    configured = load_config().get("data_root")
    if configured:
        return Path(configured)
    cache = cache_root()
    if cache.name == "_售后模板缓存":
        return cache.parent
    return Path.cwd()
