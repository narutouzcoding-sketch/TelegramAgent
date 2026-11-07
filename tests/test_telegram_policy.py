import asyncio
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon import errors
from telethon.tl.types import User

from telegram_agent.app import AgentApp
from telegram_agent.contact_calls import execute_job
from telegram_agent.store import Store, utc_now
from telegram_agent.telegram_policy import TelegramPaused, TelegramPolicy


async def test_default_denies_calls_before_telegram_and_ai_work(brain):
    operation = AsyncMock()
    with pytest.raises(TelegramPaused, match="o'chirilgan"):
        await TelegramPolicy(brain.settings, brain.store).dial(brain.settings.owner_id, operation)
    operation.assert_not_called()
    result = brain.execute_tool(
        "queue_contact_call", {"target": "@friend", "message": "Salom"}, "denied"
    )
    assert not result["ok"]
    assert not brain.store.list_contact_calls()


async def test_contact_allowlist_is_checked_before_speech_or_dial(brain):
    settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
    )
    job = brain.store.queue_contact_call("@other", "Salom")
    app = SimpleNamespace(
        settings=settings,
        store=brain.store,
        policy=TelegramPolicy(settings, brain.store),
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=User(id=88))),
        brain=SimpleNamespace(speech=AsyncMock()),
        send_text=AsyncMock(),
    )
    await execute_job(app, job)
    app.brain.speech.assert_not_called()
    assert brain.store.list_contact_calls()[0]["state"] == "failed"


async def test_flood_wait_persists_and_never_retries_after_restart(brain, tmp_path):
    path = tmp_path / "pause.sqlite3"
    store = Store(path)
    operation = AsyncMock(side_effect=errors.FloodWaitError(request=None, capture=120))
    policy = TelegramPolicy(brain.settings, store)
    with pytest.raises(TelegramPaused, match="120"):
        await policy.send(operation)
    assert policy.stopped.is_set()
    store.close()
    reopened = Store(path)
    # A new policy reads SQLite state rather than relying on the first policy's event.
    try:
        new_policy = TelegramPolicy(brain.settings, reopened)
        with pytest.raises(TelegramPaused, match="kutish"):
            await new_policy.send(operation)
    finally:
        reopened.close()
    operation.assert_awaited_once()


@pytest.mark.parametrize("error", [errors.PeerFloodError, errors.FrozenMethodInvalidError])
async def test_account_restriction_stops_other_actions(brain, error):
    policy = TelegramPolicy(brain.settings, brain.store)
    operation = AsyncMock(side_effect=error(request=None))
    with pytest.raises(TelegramPaused):
        await policy.action(operation)
    with pytest.raises(TelegramPaused):
        await policy.action(operation)
    operation.assert_awaited_once()


async def test_messages_are_serialized_and_spaced(brain):
    policy = TelegramPolicy(replace(brain.settings, min_message_interval_seconds=0.02), brain.store)
    times = []

    async def operation():
        times.append(asyncio.get_running_loop().time())

    await asyncio.gather(policy.send(operation), policy.send(operation), policy.send(operation))
    assert len(times) == 3
    assert all(right - left >= 0.018 for left, right in zip(times, times[1:]))


def test_call_limits_survive_store_reopen(tmp_path):
    path = tmp_path / "calls.sqlite3"
    now = utc_now()
    store = Store(path)
    assert store.reserve_call(42, now=now)
    store.close()
    store = Store(path)
    try:
        assert not store.reserve_call(77, now=now + timedelta(seconds=30))
        assert store.reserve_call(42, now=now + timedelta(seconds=61))
        assert store.reserve_call(42, now=now + timedelta(seconds=122))
        assert not store.reserve_call(42, now=now + timedelta(seconds=183))
    finally:
        store.close()


async def test_text_mode_starts_without_call_transport(brain, monkeypatch):
    from telegram_agent import app as module

    app = AgentApp.__new__(AgentApp)
    app.settings, app.store = brain.settings, brain.store
    app.policy = TelegramPolicy(brain.settings, brain.store)
    app.telegram = SimpleNamespace(
        connect=AsyncMock(),
        get_input_entity=AsyncMock(),
        add_event_handler=lambda *args: None,
        disconnected=asyncio.get_running_loop().create_future(),
    )
    app.telegram.disconnected.set_result(None)
    monkeypatch.setattr(module, "ensure_telegram_account", AsyncMock(return_value=User(id=1)))
    monkeypatch.setattr(module, "configured_owner", AsyncMock(return_value=User(id=42)))
    app._start_call_transport = AsyncMock()
    app.scheduler_task = app.contact_queue_task = None
    app.background_tasks = set()
    app.hangup = AsyncMock()
    await app._run()
    app._start_call_transport.assert_not_called()
    assert app.contact_queue_task is None
