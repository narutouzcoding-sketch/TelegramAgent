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
from telegram_agent.telegram_policy import CallRateLimited, TelegramPaused, TelegramPolicy


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
        assert store.next_call_at(60, 3, now + timedelta(seconds=183)) == now + timedelta(hours=1)
        assert store.reserve_call(42, now=now + timedelta(hours=1))
    finally:
        store.close()


async def test_owner_call_request_rejected_before_queue_when_hourly_budget_is_full(brain):
    settings = replace(brain.settings, enable_voice_calls=True, max_calls_per_hour=1)
    assert brain.store.reserve_call(77, now=utc_now() - timedelta(minutes=2))
    agent = AgentApp.__new__(AgentApp)
    agent.brain, agent.settings, agent.store = brain, settings, brain.store
    agent.policy = TelegramPolicy(settings, brain.store)
    agent.recipient_resolver = SimpleNamespace(
        resolve=AsyncMock(return_value=User(id=88, first_name="QA", username="qa_example"))
    )
    brain.contact_request = agent.queue_requested_call
    result = await brain.execute_async_tool(
        "queue_contact_call",
        {"target": "@qa_example", "message": "Qayerdasan?", "fallback_to_message": False},
        "limit-test",
    )
    assert not result["ok"]
    assert "Telefon terilmadi" in result["error"] and "Asia/Tashkent" in result["error"]
    assert brain.store.list_contact_calls() == []
    operation = AsyncMock()
    with pytest.raises(CallRateLimited):
        await agent.policy.dial(88, operation)
    operation.assert_not_awaited()


async def test_budget_used_after_queueing_reports_no_attempt_without_preparing_audio(brain):
    settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
        max_calls_per_hour=1,
    )
    brain.store.queue_contact_call("@qa_example", "Qayerdasan?", mode="ask")
    job = brain.store.claim_contact_call()
    assert brain.store.reserve_call(77)
    app = SimpleNamespace(
        settings=settings,
        store=brain.store,
        recipient_resolver=SimpleNamespace(resolve=AsyncMock()),
        send_text=AsyncMock(),
    )
    await execute_job(app, job)
    assert brain.store.list_contact_calls()[0]["state"] == "rate_limited"
    app.recipient_resolver.resolve.assert_not_awaited()
    app.send_text.assert_awaited_once()
    report = app.send_text.call_args.args[0]
    assert "Telefon terilmadi" in report and "Asia/Tashkent" in report
    assert "texnik holat" not in report and "ulanishi" not in report


async def test_limits_and_status_report_shared_budget_without_ai_or_new_reservations(brain):
    brain.settings = replace(brain.settings, max_calls_per_hour=1)
    now = utc_now()
    assert brain.store.reserve_call(77, now=now)
    brain.ai.request = AsyncMock(side_effect=AssertionError("No cloud request expected"))
    report = await brain.answer("/limits")
    assert "1/1" in report and "Asia/Tashkent" in report
    budget = brain.store.call_budget(60, 1, now + timedelta(seconds=20))
    assert budget["used"] == 1 and budget["remaining"] == 0
    assert budget["retry_at"] == (now + timedelta(hours=1)).isoformat()

    app = AgentApp.__new__(AgentApp)
    app.settings, app.store = brain.settings, brain.store
    app.call_lock = asyncio.Lock()
    app.send_text = AsyncMock()
    await app.on_message(
        SimpleNamespace(
            is_private=True, sender_id=brain.settings.owner_id, out=False, raw_text="/status"
        )
    )
    assert "1/1" in app.send_text.call_args.args[0]
    assert brain.store.call_budget(60, 1, now)["used"] == 1
    brain.ai.request.assert_not_awaited()


async def test_text_mode_starts_without_call_transport(brain, monkeypatch):
    from telegram_agent import app as module
    from telegram_agent import contact_sync

    monkeypatch.setattr(contact_sync, "telegram_contacts", AsyncMock(return_value=[]))

    app = AgentApp.__new__(AgentApp)
    app.settings, app.store = brain.settings, brain.store
    app.brain = brain
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
    with pytest.raises(ConnectionError, match="ulanishi"):
        await app._run()
    app._start_call_transport.assert_not_called()
    assert app.contact_queue_task.done()
    assert app.recipient_resolver is not None
    assert brain.contact_request == app.queue_requested_call
