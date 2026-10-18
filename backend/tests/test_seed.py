"""Seed script produces a believable year of demo data."""
from mongomock_motor import AsyncMongoMockClient

from app.analysis.activity import build_activity
from scripts import seed_demo_data as sd


async def test_seed_builds_year_of_data(monkeypatch):
    spec = dict(sd.DEMO_CLIENTS[0], start_weeks_ago=12)
    monkeypatch.setattr(sd, "DEMO_CLIENTS", [spec])
    db = AsyncMongoMockClient(tz_aware=True)["seed"]
    tokens = await sd.seed(db)
    assert tokens == {"nimali": "demo-nimali"}
    c = await db.clients.find_one({"token": "demo-nimali"})
    assert c["demo"] is True and c["profile_complete"]
    ss = await db.sessions.find({"client_id": c["_id"]}).to_list(500)
    assert len(ss) > 15 and all(s["demo"] for s in ss)
    assert sum(1 for s in ss if s["status"] == "ready_for_review") == 2
    a = build_activity(ss, tz="Asia/Colombo", training_days_per_week=3)
    assert sum(1 for d in a["days"] if d["level"] > 0) > 15 and a["streaks"]["longest"] >= 7
    assert await db.weight_log.count_documents({"client_id": c["_id"]}) >= 5
    assert await sd.seed(db) == tokens                                  # idempotent
    assert await db.clients.count_documents({}) == 1
    await sd.seed(db, reset=True)
    assert await db.sessions.count_documents({}) > 0 and await db.clients.count_documents({}) == 1
