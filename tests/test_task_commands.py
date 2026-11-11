from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram_agent.store import Store
from telegram_agent.task_commands import task_reply


async def test_local_plan_and_reminder_use_no_ai_and_share_draft(brain):
    create = AsyncMock(side_effect=AssertionError("Unexpected cloud request"))
    brain.gemini = SimpleNamespace(create=create)

    assert "reja saqlandi" in await brain.answer("Rejamga qo‘sh: Kitob o'qish")
    assert "matnini kiriting" in await brain.answer("/xabar")
    assert "Qachon" in await brain.answer("Menga xabar yubor: Suv ichish")
    assert "Kelajakdagi" in await brain.answer("ertaga 29:00")
    assert not brain.store.list_reminders()
    assert brain.store.context(30, 10000) == []
    create.assert_not_awaited()

    database = Path(brain.store.db.execute("PRAGMA database_list").fetchone()["file"])
    second = Store(database, brain.store.timezone)
    try:
        assert task_reply(second, "Boshqa savol") is None
        assert "Asia/Tashkent" in task_reply(second, "15 daqiqadan keyin")
        assert task_reply(brain.store, "15 daqiqadan keyin") is None
        [reminder] = brain.store.list_reminders()
        assert reminder["title"] == "Suv ichish"
        assert reminder["mode"] == "message"
    finally:
        second.close()


def test_one_step_reminder_and_cancellation(store):
    assert "eslatma saqlandi" in task_reply(store, "/eslatma Tayyorlash | ertaga 9:05")
    assert "Qachon" in task_reply(store, "/xabar Tugallanmagan")
    assert "bekor qilindi" in task_reply(store, "/bekor")
    assert task_reply(store, "ertaga 09:00") is None
    assert len(store.list_reminders()) == 1
