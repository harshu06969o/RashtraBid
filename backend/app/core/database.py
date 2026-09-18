"""
GeM-Guard — Core Database Module
Configures Motor (AsyncIOMotorClient) with robust connection pooling.
Supports seamless fallback to mongomock_motor for offline hackathon environments.
"""

import logging
import os
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.env_loader import get_mongo_db_name, get_mongo_uri

logger = logging.getLogger("gemguard.database")

# Configuration & Pool Parameters
MONGODB_URL = get_mongo_uri()
MONGODB_DB_NAME = get_mongo_db_name()
def is_real_mongo_preferred() -> bool:
    env_val = os.getenv("USE_REAL_MONGO")
    if env_val is not None:
        return env_val.strip().lower() in ("1", "true", "yes")
    uri = get_mongo_uri()
    return bool(uri and ("mongodb://" in uri or "mongodb+srv://" in uri))

USE_REAL_MONGO = is_real_mongo_preferred()

# Connection Pool Defaults (Configurable via ENV)
MAX_POOL_SIZE = int(os.getenv("MONGO_MAX_POOL_SIZE", "50"))
MIN_POOL_SIZE = int(os.getenv("MONGO_MIN_POOL_SIZE", "10"))
MAX_IDLE_TIME_MS = int(os.getenv("MONGO_MAX_IDLE_TIME_MS", "45000"))
SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))
CONNECT_TIMEOUT_MS = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "10000"))
SOCKET_TIMEOUT_MS = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "20000"))


class MongoManager:
    """Manages the lifecycle and connection pooling of Motor Async MongoDB client."""

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.is_mock: bool = False

    async def connect(self) -> AsyncIOMotorDatabase:
        """Initialize Motor client with connection pool and test connection."""
        if self.db is not None:
            return self.db

        if USE_REAL_MONGO:
            try:
                logger.info(
                    "Connecting to real MongoDB at %s (pool: %d-%d)...",
                    MONGODB_URL.split("@")[-1] if "@" in MONGODB_URL else MONGODB_URL,
                    MIN_POOL_SIZE,
                    MAX_POOL_SIZE,
                )
                self.client = AsyncIOMotorClient(
                    MONGODB_URL,
                    maxPoolSize=MAX_POOL_SIZE,
                    minPoolSize=MIN_POOL_SIZE,
                    maxIdleTimeMS=MAX_IDLE_TIME_MS,
                    serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
                    connectTimeoutMS=CONNECT_TIMEOUT_MS,
                    socketTimeoutMS=SOCKET_TIMEOUT_MS,
                    uuidRepresentation="standard",
                )
                self.db = self.client[MONGODB_DB_NAME]
                # Test connection
                await self.client.admin.command("ping")
                self.is_mock = False
                logger.info("Successfully connected to MongoDB database '%s'.", MONGODB_DB_NAME)
                await self._create_indexes()
                return self.db
            except Exception as exc:
                logger.warning(
                    "Real MongoDB connection failed (%s). Falling back to in-memory mongomock_motor for offline resilience.",
                    exc,
                )

        # Fallback to mongomock_motor
        try:
            from mongomock_motor import AsyncMongoMockClient
            self.client = AsyncMongoMockClient()
            self.db = self.client[MONGODB_DB_NAME]
            self.is_mock = True
            logger.info("Using in-memory MongoDB (mongomock_motor) for offline hackathon reliability.")
            await self._create_indexes()
            return self.db
        except Exception as mock_exc:
            logger.error("Failed to initialize mongomock_motor: %s", mock_exc)
            raise

    async def _create_indexes(self):
        """Create essential indexes for performance and data integrity."""
        if self.db is None:
            return
        try:
            # Tenders: unique tender number
            await self.db["tenders"].create_index("tender_no", unique=True, sparse=True)
            # Users: unique username
            await self.db["users"].create_index("username", unique=True, sparse=True)
            # Bids: tender_id and bidder_id
            await self.db["bids"].create_index([("tender_id", 1), ("bidder_id", 1)])
            # Rules: tender_id
            await self.db["rules"].create_index("tender_id")
            # Evidence: document_id
            await self.db["evidence"].create_index("document_id")
            # Audit log: timestamp
            await self.db["audit"].create_index("timestamp")
            logger.info("Ensured core database indexes.")
        except Exception as idx_err:
            logger.debug("Index creation note: %s", idx_err)

    async def close(self):
        """Close client connection pool cleanly."""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB client connections.")
        self.client = None
        self.db = None


# Singleton instance
db_manager = MongoManager()


async def connect_to_mongo() -> AsyncIOMotorDatabase:
    """Connect to MongoDB on app startup."""
    return await db_manager.connect()


async def close_mongo_connection():
    """Disconnect from MongoDB on app shutdown."""
    await db_manager.close()


async def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency for accessing the database."""
    if db_manager.db is None:
        await db_manager.connect()
    return db_manager.db


async def get_db() -> AsyncIOMotorDatabase:
    """FastAPI dependency alias for get_database."""
    return await get_database()


# ── MongoDB Document Utilities ────────────────────────────────────────────────

import hashlib
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException


def utcnow_str() -> str:
    """Return ISO format string of current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def sha256(data: str) -> str:
    """Return SHA-256 hex digest of string data."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def doc_to_dict(d: Any) -> Any:
    """Recursively convert MongoDB BSON document to clean JSON serializable dictionary."""
    if d is None:
        return {}
    if isinstance(d, ObjectId):
        return str(d)
    if isinstance(d, datetime):
        return d.isoformat()
    if isinstance(d, list):
        return [doc_to_dict(item) for item in d]
    if isinstance(d, dict):
        res = dict(d)
        if "_id" in res:
            res["id"] = str(res.pop("_id"))
        for k, v in list(res.items()):
            res[k] = doc_to_dict(v)
        return res
    return d


def safe_oid(val: Any) -> Optional[ObjectId]:
    """Convert value to ObjectId if valid 24-hex characters, otherwise return None without raising 422."""
    if not val:
        return None
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str):
        val_str = val.strip()
        if len(val_str) == 24 and ObjectId.is_valid(val_str):
            try:
                return ObjectId(val_str)
            except Exception:
                return None
    return None


def to_oid(id_str: str) -> ObjectId:
    """Convert string to ObjectId, raising 422 if invalid."""
    oid = safe_oid(id_str)
    if oid is not None:
        return oid
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid ID format: {id_str}")


