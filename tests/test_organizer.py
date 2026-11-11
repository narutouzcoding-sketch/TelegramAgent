from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from telegram_agent.store import Store, utc_now


def test_snooze_delivered_once_is_idempotent_across_store_connections(store):
    saved = store.add_reminder("Suv", (utc_now() + timedelta(minutes=2)).isoformat())
    with store.db:
        store.db.execute(
            "UPDATE reminders SET state='delivered',message_confirmed=1,message_random_id=99 WHERE id=?",
            (saved["id"],),
        )
    now = utc_now()
    result = store.snooze_reminder(saved["id"], 15, request_id="same-request", now=now)
    assert result["id"] == saved["id"]
    database = Path(store.db.execute("PRAGMA database_list").fetchone()["file"])
    second = Store(database)
    try:
        assert (
            second.snooze_reminder(
                saved["id"], 15, request_id="same-request", now=now + timedelta(minutes=1)
            )
            == result
        )
        with pytest.raises(ValueError, match="boshqa"):
            second.snooze_reminder(saved["id"], 30, request_id="same-request")
        [row] = store.list_reminders()
        assert row["mode"] == "message" and row["state"] == "pending"
        assert not row["message_confirmed"] and row["message_random_id"] is None
        assert row["due"] == (now + timedelta(minutes=15)).isoformat()
    finally:
        second.close()


@pytest.mark.parametrize("repeat,days", [("daily", 1), ("weekly", 7)])
def test_snooze_moves_one_occurrence_and_preserves_repeat_time(store, repeat, days):
    now = utc_now()
    original = now + timedelta(minutes=5)
    saved = store.add_reminder("Dars", original.isoformat(), repeat=repeat)
    result = store.snooze_reminder(saved["id"], 15, now=now)
    assert result["id"] != saved["id"]
    rows = {row["id"]: row for row in store.list_reminders()}
    assert rows[saved["id"]]["due"] == (original + timedelta(days=days)).isoformat()
    assert rows[result["id"]]["repeat"] == "none"
    assert rows[result["id"]]["mode"] == "message"
    again = store.snooze_reminder(saved["id"], 30, now=now)
    assert again["id"] == result["id"]
    assert len(store.list_reminders()) == 2


def test_snooze_never_rewrites_active_delivery_or_cancelled_reminders(store):
    due = utc_now() + timedelta(seconds=2)
    saved = store.add_reminder("Dars", due.isoformat())
    store.claim_due(now=due)
    with pytest.raises(ValueError, match="yetkazilmoqda"):
        store.snooze_reminder(saved["id"])
    store.cancel_reminder(saved["id"])
    with pytest.raises(ValueError, match="topilmadi"):
        store.snooze_reminder(saved["id"])


def test_today_uses_tashkent_day_and_includes_overdue_but_excludes_tomorrow(store):
    now = (utc_now() + timedelta(days=2)).replace(hour=19, minute=30, second=0, microsecond=0)
    overdue = store.add_reminder("Kechikkan", (now - timedelta(hours=1)).isoformat())
    today = store.add_reminder("Bugun", (now + timedelta(hours=1)).isoformat())
    store.add_reminder("Ertaga", (now + timedelta(days=1)).isoformat())
    overview = store.daily_overview(now)
    assert overview["date"] == (now + timedelta(hours=5)).date().isoformat()
    assert overview["reminder_counts"] == {"total": 2, "overdue": 1, "failed": 0}
    assert {row["id"] for row in overview["reminders"]} == {overdue["id"], today["id"]}


def test_search_matches_unicode_and_old_history_and_treats_wildcards_literally(store):
    store.save_contact("СЕВИНЧ", "@qa_example")
    assert store.search_local("севинч")[0]["kind"] == "contact"
    store.add_plan("100%_yakun", "Dars")
    assert len(store.search_local("%_")) == 1
    old = store.queue_contact_call("@qa_example", "Qidiriladigan eski xabar")
    store.finish_contact_call(old["id"], "sent", "Done")
    for index in range(22):
        item = store.queue_contact_call("@qa_other", f"Different {index}")
        store.finish_contact_call(item["id"], "sent", "Done")
    assert old["id"] not in {row["id"] for row in store.list_contact_calls()}
    assert store.search_local("Qidiriladigan")[0]["id"] == old["id"]


async def test_organizer_commands_spend_no_ai_and_keep_private_content_out_of_context(brain):
    brain.ai.request = AsyncMock(side_effect=AssertionError("Unexpected cloud request"))
    plan = brain.store.add_plan("Kitob o'qish")
    reminder = brain.store.add_reminder("Dars", (utc_now() + timedelta(minutes=2)).isoformat())
    assert "Ochiq rejalar" in await brain.answer("/bugun")
    assert "Kitob" in await brain.answer("/qidir kitob")
    assert "xabar bilan" in await brain.answer(f"/keyin {reminder['id']} 1 soat")
    assert "bajarildi" in await brain.answer(f"/bajarildi {plan['id']}")
    assert not brain.store.list_plans()
    assert brain.store.context(30, 10000) == []
    brain.ai.request.assert_not_awaited()
