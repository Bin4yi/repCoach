"""MongoDB (Motor) connection + helpers. `mongomock://` gives an in-memory DB for demos and tests."""
from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Any

from .config import Settings


def new_id() -> str:
    return uuid.uuid4().hex


def new_token() -> str:
    return secrets.token_urlsafe(24)  # ~192 bits: unguessable private client link


def now() -> datetime:
    return datetime.now(timezone.utc)


async def init_db(settings: Settings):
    """Return (client, db). Collections: clients, weight_log, sessions, plans."""
    uri = settings.mongodb_uri
    if uri.startswith("mongomock"):
        from mongomock_motor import AsyncMongoMockClient
        client = AsyncMongoMockClient(tz_aware=True)
    else:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    db = client[settings.mongodb_db]
    await ensure_indexes(db)
    return client, db


async def ensure_indexes(db) -> None:
    await db.clients.create_index("token", unique=True)
    await db.sessions.create_index([("client_id", 1), ("created_at", -1)])
    await db.weight_log.create_index([("client_id", 1), ("date", -1)])
    await db.plans.create_index([("client_id", 1), ("created_at", -1)])


def serialize(obj: Any) -> Any:
    """Make a Mongo document JSON-friendly: _id -> id, datetimes -> ISO strings (UTC)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out["id" if k == "_id" else k] = serialize(v)
        return out
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(obj, date):
        return obj.isoformat()
    return obj
