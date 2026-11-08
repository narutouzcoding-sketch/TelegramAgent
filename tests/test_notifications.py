from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_agent.notifications import deliver_pending
from telegram_agent.telegram_policy import TelegramPaused


def ready(store):
    store.db.execute("UPDATE owner_outbox SET retry_after=NULL")
    store.db.commit()


async def test_owner_outbox_retries_text_only_never_redials(store):
    store.queue_notification(42, "Saved call result")
    store.queue_notification(42, "Saved call result")
    assert store.notification_status(42) == {"pending": 1}
    assert store.pending_notification(42) is None
    ready(store)
    app = SimpleNamespace(store=store, settings=SimpleNamespace(owner_id=42), send_text=AsyncMock())
    assert await deliver_pending(app)
    app.send_text.assert_awaited_once_with("Saved call result")
    assert not store.notification_status(42) and not store.list_contact_calls()


async def test_outbox_failure_is_bounded_and_owner_is_pinned(store):
    store.queue_notification(42, "Private owner result")
    ready(store)
    wrong = SimpleNamespace(
        store=store, settings=SimpleNamespace(owner_id=77), send_text=AsyncMock()
    )
    assert not await deliver_pending(wrong)
    wrong.send_text.assert_not_called()
    app = SimpleNamespace(
        store=store,
        settings=SimpleNamespace(owner_id=42),
        send_text=AsyncMock(side_effect=OSError("offline")),
    )
    for _ in range(3):
        ready(store)
        assert await deliver_pending(app)
    assert store.notification_status(42) == {"failed": 1}
    assert not await deliver_pending(app)
    assert store.retry_notifications(42) == {"queued": 1}


async def test_outbox_does_not_ignore_telegram_restrictions(store):
    store.queue_notification(42, "Report")
    ready(store)
    app = SimpleNamespace(
        store=store,
        settings=SimpleNamespace(owner_id=42),
        send_text=AsyncMock(side_effect=TelegramPaused("paused")),
    )
    with pytest.raises(TelegramPaused):
        await deliver_pending(app)
