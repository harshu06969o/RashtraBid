"""
GeM-Guard - Local User Cache
Persists registered users to disk so they survive server restarts.
Used as fallback when MongoDB connection is unavailable/slow.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("gemguard.user_cache")

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "users_cache.json"


def _load() -> Dict[str, dict]:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if _CACHE_PATH.exists():
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load user cache: %s", e)
    return {}


def _save(users: Dict[str, dict]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, default=str)
    except Exception as e:
        logger.warning("Failed to save user cache: %s", e)


def upsert_user(username: str, user_doc: dict) -> None:
    users = _load()
    users[username.lower()] = {k: v for k, v in user_doc.items() if k not in ("_id",)}
    _save(users)


def get_user(username: str) -> Optional[dict]:
    users = _load()
    return users.get(username.lower())


def list_users() -> list:
    return list(_load().values())
