from datetime import UTC, datetime, timedelta

import pytest

from telegram_agent.store import Store, parse_due, utc_now


def test_tashkent_conversion_and_past_rejection():
    now = datetime(2030, 1, 1, tzinfo=UTC)
    assert parse_due("2030-01-02T09:00:00", "Asia/Tashkent", now) == datetime(
        2030, 1, 2, 4, tzinfo=UTC
    )
    assert parse_due("2030-01-02T09:00:00+05:00", "Asia/Tashkent", now).hour == 4
    with pytest.raises(ValueError):
        parse_due("2029-12-31T09:00:00+05:00", "Asia/Tashkent", now)


def test_persistence_and_plans_survive_restart(tmp_path):
    path = tmp_path / "agent.sqlite3"
    first = Store(path)
    first.add_plan("Kitob", "10 bet")
    reminder = first.add_reminder("Dars", (utc_now() + timedelta(days=1)).isoformat())
    first.close()
    reopened = Store(path)
    assert reopened.list_plans()[0]["title"] == "Kitob"
    assert reopened.list_reminders()[0]["id"] == reminder["id"]
    assert reopened.complete_plan(1)["completed"] is True
    assert reopened.complete_plan(1)["completed"] is False
    assert reopened.cancel_reminder(reminder["id"])["cancelled"] is True
    assert reopened.list_reminders() == []
    reopened.close()


def test_claim_once_and_recover_expired_lease(store):
    due = utc_now() + timedelta(minutes=1)
    store.add_reminder("Dars", due.isoformat())
    assert store.claim_due(now=due - timedelta(seconds=1)) is None
    row = store.claim_due(now=due)
    assert row["title"] == "Dars"
    assert store.claim_due(now=due + timedelta(minutes=1)) is None
    recovered = store.claim_due(now=due + timedelta(minutes=66))
    assert recovered["id"] == row["id"]


def test_retry_keeps_original_time_and_weekly_cadence(store):
    due = utc_now() + timedelta(minutes=1)
    store.add_reminder("Dars", due.isoformat(), repeat="weekly")
    row = store.claim_due(now=due)
    store.finish(row, error="network", now=due)
    assert store.claim_due(now=due + timedelta(seconds=30)) is None
    retry = store.claim_due(now=due + timedelta(minutes=3))
    assert datetime.fromisoformat(retry["due"]) == due
    store.finish(retry, now=due + timedelta(minutes=3), delivery_status="message_sent")
    future = store.list_reminders()[0]
    assert datetime.fromisoformat(future["due"]) == due + timedelta(days=7)
    assert future["attempts"] == 0


def test_recurring_reminder_skips_missed_instances(store):
    due = utc_now() + timedelta(minutes=1)
    store.add_reminder("Dars", due.isoformat(), repeat="daily")
    now = due + timedelta(days=5, hours=1)
    row = store.claim_due(now=now)
    store.finish(row, now=now)
    assert datetime.fromisoformat(store.list_reminders()[0]["due"]) == due + timedelta(days=6)


def test_three_failures_become_failed(store):
    due = utc_now() + timedelta(minutes=1)
    store.add_reminder("Dars", due.isoformat())
    for step in [0, 3, 10]:
        now = due + timedelta(minutes=step)
        row = store.claim_due(now=now)
        store.finish(row, error="network", now=now)
    assert store.list_reminders() == []
    assert store.db.execute("SELECT state FROM reminders").fetchone()[0] == "failed"


def test_cancellation_during_delivery_is_preserved(store):
    due = utc_now() + timedelta(seconds=1)
    saved = store.add_reminder("Dars", due.isoformat())
    row = store.claim_due(now=due)
    store.cancel_reminder(saved["id"])
    store.finish(row, now=due)
    assert store.db.execute("SELECT state FROM reminders").fetchone()[0] == "cancelled"


def test_invalid_reminders_are_not_saved(store):
    due = (utc_now() + timedelta(days=1)).isoformat()
    for title, repeat, mode in [
        ("", "none", "call"),
        ("Dars", "monthly", "call"),
        ("Dars", "none", "email"),
    ]:
        with pytest.raises(ValueError):
            store.add_reminder(title, due, repeat, mode)
    assert store.list_reminders() == []
