from datetime import timedelta

from telegram_agent.scheduler import Scheduler
from telegram_agent.store import utc_now


def make_due(store, age=timedelta(seconds=1)):
    saved = store.add_reminder("Tekshiruv", (utc_now() + timedelta(hours=1)).isoformat())
    with store.db:
        store.db.execute(
            "UPDATE reminders SET due=? WHERE id=?", ((utc_now() - age).isoformat(), saved["id"])
        )


async def test_delivery_runs_once_and_records_result(store):
    make_due(store)
    seen = []

    async def deliver(row, late):
        seen.append((row["title"], late))
        return "call_connected"

    scheduler = Scheduler(store, deliver)
    assert await scheduler.tick()
    assert not await scheduler.tick()
    assert seen == [("Tekshiruv", False)]
    row = store.db.execute("SELECT state,delivery_status FROM reminders").fetchone()
    assert tuple(row) == ("delivered", "call_connected")


async def test_old_reminder_is_marked_late(store):
    make_due(store, timedelta(days=2))
    received = []

    async def deliver(row, late):
        received.append(late)
        return "late_message"

    await Scheduler(store, deliver, grace_hours=24).tick()
    assert received == [True]


async def test_failure_is_not_marked_delivered(store):
    make_due(store)

    async def fail(row, late):
        raise ConnectionError("offline")

    await Scheduler(store, fail).tick()
    row = store.db.execute("SELECT state,last_error,attempts FROM reminders").fetchone()
    assert tuple(row) == ("pending", "ConnectionError", 1)
