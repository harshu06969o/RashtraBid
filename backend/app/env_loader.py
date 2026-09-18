"""Shared environment loading for the GeM-Guard backend."""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parent.parent
_BACKEND_ENV = _BACKEND / ".env"

if _BACKEND_ENV.exists():
    load_dotenv(_BACKEND_ENV, override=True)


def get_port() -> int:
    return int(os.getenv("PORT", "8001"))


def get_mongo_uri() -> str:
    return (
        os.getenv("MONGO_URI")
        or os.getenv("MONGODB_URL")
        or "mongodb://localhost:27017/gem_guard"
    )


def get_mongo_db_name() -> str:
    explicit = os.getenv("MONGODB_DB_NAME")
    if explicit:
        return explicit

    path = urlparse(get_mongo_uri()).path.lstrip("/")
    if path:
        return path.split("/")[0]
    return "gem_guard"
