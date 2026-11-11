import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from openai import RateLimitError
from telethon import errors
from telethon.tl.types import User

from telegram_agent.ai_access import AIUnavailable
from telegram_agent.app import AgentApp
from telegram_agent.contact_conversation import ContactConversation
from telegram_agent.gemini_text import GeminiText
from telegram_agent.panel import PanelControl
from telegram_agent.store import Store, utc_now
from telegram_agent.supervisor import supervise
from telegram_agent.telegram_policy import TelegramPaused, TelegramPolicy
from telegram_agent.usage import UsageLedger


def completion():
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45),
        choices=[SimpleNamespace(finish_reason="stop")],
    )


def test_daily_usage_survives_restart_and_keeps_unknown_requests_honest(brain, tmp_path):
    path = tmp_path / "usage.sqlite3"
    s = Store(path)
    ledger = UsageLedger(s, brain.settings)
    key = ledger.reserve("gemini", "test-model", "asr", 300)
    ledger.finish(key, completion())
    ledger.reserve("gemini", "test-model", "text", 500)  # Simulate process death mid-request.
    s.close()
    s = Store(path)
    try:
        used = UsageLedger(s, brain.settings).summary()["providers"]["gemini"]
        assert (
            used["requests"],
            used["input_tokens"],
            used["output_tokens"],
            used["unknown_usage"],
        ) == (2, 123, 45, 1)
        assert used["unconfirmed_reserved"] == 500
        assert "prompt" not in [r[1] for r in s.db.execute("PRAGMA table_info(ai_usage)")]
    finally:
        s.close()


def test_budget_reservations_are_shared_across_connections(brain, tmp_path):
    path = tmp_path / "limits.sqlite3"
    cfg = replace(brain.settings, ai_daily_max_requests=1)
    left, right = Store(path), Store(path)
    try:
        UsageLedger(left, cfg).reserve("gemini", "model", "text", 100)
        with pytest.raises(AIUnavailable):
            UsageLedger(right, cfg).reserve("gemini", "model", "text", 100)
        UsageLedger(right, cfg).reserve("local", "model", "text", 0)
    finally:
        left.close()
        right.close()


def test_daily_budget_uses_tashkent_midnight_and_preserves_previous_day(brain, store):
    cfg = replace(brain.settings, ai_daily_max_requests=1)
    ledger = UsageLedger(store, cfg)
    before = datetime(2026, 11, 8, 18, 59, tzinfo=timezone.utc)
    after = before + timedelta(minutes=2)
    assert ledger.day(before) == "2026-11-08" and ledger.day(after) == "2026-11-09"
    ledger.reserve("gemini", "model", "text", 100, before)
    ledger.reserve("gemini", "model", "text", 100, after)
    assert store.db.execute("SELECT COUNT(DISTINCT day) FROM ai_usage").fetchone()[0] == 2


def test_token_cap_counts_unconfirmed_reservations(brain, store):
    ledger = UsageLedger(store, replace(brain.settings, ai_daily_max_tokens=600))
    ledger.reserve("gemini", "model", "text", 500)
    with pytest.raises(AIUnavailable):
        ledger.reserve("gemini", "model", "text", 101)


async def test_gemini_real_usage_is_written_without_prompt_data(brain):
    cfg = replace(brain.settings, gemini_key="test", local_fallback_enabled=False)
    adapter = GeminiText(cfg, brain.store)
    await adapter.client.close()
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=completion()))
        ),
        close=AsyncMock(),
    )
    try:
        await adapter.create(
            "PRIVATE_PROMPT_MARKER", [{"role": "user", "content": "PRIVATE_CONTACT_MARKER"}], []
        )
        used = adapter.status()["daily"]["providers"]["gemini"]
        assert used["input_tokens"] == 123 and used["unknown_usage"] == 0
        rows = [dict(r) for r in brain.store.db.execute("SELECT * FROM ai_usage")]
        assert "PRIVATE_" not in json.dumps(rows)
    finally:
        await adapter.close()


async def test_quota_cooldown_survives_adapter_restart(brain):
    cfg = replace(brain.settings, gemini_key="test", local_fallback_enabled=False)
    adapter = GeminiText(cfg, brain.store)
    await adapter.client.close()
    cloud = AsyncMock(
        side_effect=RateLimitError(
            "private",
            response=Mock(status_code=429, headers={"retry-after": "90"}, request=Mock()),
            body={},
        )
    )
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=cloud)), close=AsyncMock()
    )
    with pytest.raises(AIUnavailable):
        await adapter.create("test", [], [])
    await adapter.close()
    fresh = GeminiText(cfg, brain.store)
    try:
        assert fresh.status()["cooldown_seconds"] >= 88
        with pytest.raises(AIUnavailable):
            await fresh.create("test", [], [])
        cloud.assert_awaited_once()
    finally:
        await fresh.close()


async def test_active_adapters_share_cooldown_across_store_connections(brain, tmp_path):
    cfg = replace(brain.settings, gemini_key="test", local_fallback_enabled=False)
    path = tmp_path / "shared.sqlite3"
    store = Store(path)
    other_store = Store(path)
    agent = GeminiText(cfg, store)
    panel = GeminiText(cfg, other_store)
    error = RateLimitError(
        "private",
        response=Mock(status_code=429, headers={"retry-after": "90"}, request=Mock()),
        body={},
    )
    try:
        agent.client.chat.completions.create = AsyncMock(side_effect=error)
        panel.client.chat.completions.create = AsyncMock()
        with pytest.raises(AIUnavailable):
            await agent.create("test", [], [])
        with pytest.raises(AIUnavailable, match="kutish vaqti"):
            await panel.create("test", [], [])
        panel.client.chat.completions.create.assert_not_awaited()
        assert panel.status()["cooldown_seconds"] >= 88
    finally:
        await agent.close()
        await panel.close()
        store.close()
        other_store.close()


async def test_cancelled_provider_request_remains_unknown_not_zero_tokens(brain):
    cfg = replace(brain.settings, gemini_key="test", local_fallback_enabled=False)
    adapter = GeminiText(cfg, brain.store)
    await adapter.client.close()
    began = asyncio.Event()

    async def wait(**kwargs):
        began.set()
        await asyncio.Event().wait()

    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=wait)), close=AsyncMock()
    )
    operation = asyncio.create_task(adapter.create("test", [], []))
    await began.wait()
    operation.cancel()
    await asyncio.gather(operation, return_exceptions=True)
    assert adapter.status()["daily"]["providers"]["gemini"]["unknown_usage"] == 1
    assert brain.store.db.execute("SELECT state FROM ai_usage").fetchone()[0] == "interrupted"
    await adapter.close()


async def test_contact_verifier_does_not_resend_long_conversation_history():
    task = ContactConversation(
        SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True),
        "QA",
        {"mode": "ask", "message": "Qayerdasiz?", "max_turns": 4},
    )
    task.transcript = [{"role": "user", "content": "OLD_UNVERIFIED_TEXT " * 500} for _ in range(8)]
    task.transcript.append({"role": "assistant", "content": "Qayerdasiz?"})
    task.generate = AsyncMock(return_value='{"status":"answered","answer":"Uyda"}')
    await task.answer("Uyda")
    context = json.dumps(task.generate.call_args.args[1])
    assert len(context) < 700 and "OLD_UNVERIFIED_TEXT" not in context
    assert task.answer_verified


async def test_usage_read_does_not_call_cloud(brain):
    adapter = GeminiText(
        replace(brain.settings, gemini_key="test", local_fallback_enabled=False), brain.store
    )
    brain.gemini = adapter
    adapter.create = AsyncMock(side_effect=AssertionError("cloud forbidden"))
    try:
        assert "Bugungi Gemini" in await brain.answer("token sarfi")
        adapter.create.assert_not_called()
    finally:
        await adapter.close()


@pytest.mark.parametrize("repeat,days", [("daily", 1), ("weekly", 7)])
def test_repeating_reminder_survives_three_occurrence_failures(store, repeat, days):
    now = utc_now()
    row = store.add_reminder("Test", (now + timedelta(hours=1)).isoformat(), repeat, "call")
    due = now - timedelta(seconds=1)
    with store.db:
        store.db.execute("UPDATE reminders SET due=? WHERE id=?", (due.isoformat(), row["id"]))
    for offset in (0, 3, 8):
        at = now + timedelta(minutes=offset)
        claimed = store.claim_due(at)
        assert claimed
        store.finish(claimed, error="offline", now=at)
    saved = store.list_reminders()[0]
    assert saved["state"] == "pending" and saved["attempts"] == 0
    assert datetime.fromisoformat(saved["due"]) == due + timedelta(days=days)
    assert saved["delivery_status"] == "previous_occurrence_failed"
    assert store.db.execute("SELECT COUNT(*) FROM reminder_failures").fetchone()[0] == 1


def test_failed_once_reminder_is_visible_and_can_retry_as_message(store):
    now = utc_now()
    row = store.add_reminder("Test", (now + timedelta(hours=1)).isoformat(), mode="call")
    with store.db:
        store.db.execute(
            "UPDATE reminders SET due=? WHERE id=?",
            ((now - timedelta(seconds=1)).isoformat(), row["id"]),
        )
    for offset in (0, 3, 8):
        at = now + timedelta(minutes=offset)
        claimed = store.claim_due(at)
        store.finish(claimed, error="offline", now=at)
    assert store.list_reminders()[0]["state"] == "failed"
    assert store.retry_reminder(row["id"])["mode"] == "message"
    assert store.list_reminders()[0]["state"] == "pending"
    assert store.list_reminders()[0]["recovery_message_only"] == 1
    store.update_reminder(
        row["id"], "Rescheduled", (now + timedelta(days=1)).isoformat(), mode="call"
    )
    assert store.list_reminders()[0]["recovery_message_only"] == 0


async def test_manual_stop_intent_survives_panel_process_restart(brain, tmp_path):
    first = PanelControl(brain.settings, tmp_path)
    await first.stop()
    await first.close()
    factory = Mock(return_value=SimpleNamespace(ready=asyncio.Event(), run=AsyncMock()))
    fresh = PanelControl(brain.settings, tmp_path, agent_factory=factory)
    try:
        assert (await fresh.start(manual=False))["manual_stop"]
        factory.assert_not_called()
        await fresh.start(manual=True)
        await fresh.task
        assert factory.call_count == 1
    finally:
        await fresh.close()


@pytest.mark.parametrize("interrupted", [False, True])
async def test_uncertain_owner_reminder_recovery_never_redials_and_keeps_future_mode(
    store, interrupted
):
    now = utc_now()
    saved = store.add_reminder("QA", (now + timedelta(hours=1)).isoformat(), "daily", "call")
    with store.db:
        store.db.execute(
            "UPDATE reminders SET due=? WHERE id=?",
            ((now - timedelta(seconds=1)).isoformat(), saved["id"]),
        )
    claimed = store.claim_due(now)
    if interrupted:
        store.finish(claimed, error="interrupted", now=now)
        now += timedelta(minutes=3)
    store.recover_reminders(now, all_inflight=True)
    row = store.claim_due(now)
    assert row["mode"] == "call" and row["recovery_message_only"] == 1
    app = AgentApp.__new__(AgentApp)
    app.settings = SimpleNamespace(timezone="Asia/Tashkent", enable_voice_calls=True)
    app.store = store
    app.call_lock = asyncio.Lock()
    app.send_text = AsyncMock()
    app.place_call = AsyncMock()
    await app.deliver(row, False)
    app.place_call.assert_not_called()
    assert "Qayta qo" in app.send_text.call_args.args[0]
    store.finish(row, now=now, delivery_status="message_sent")
    following = store.list_reminders()[0]
    assert following["mode"] == "call" and not following["recovery_message_only"]


async def test_reminder_recovery_uses_same_message_id_and_skips_confirmed_sends(store):
    now = utc_now()
    due = now + timedelta(minutes=1)
    store.add_reminder("Test", due.isoformat(), "daily", "call")
    first = store.claim_due(due)
    store.recover_reminders(due, all_inflight=True)
    retry = store.claim_due(due)
    assert first["message_random_id"] == retry["message_random_id"]
    assert not store.confirm_reminder_message(first)
    store.finish(first, now=due)

    app = AgentApp.__new__(AgentApp)
    app.settings = SimpleNamespace(timezone="Asia/Tashkent", enable_voice_calls=True)
    app.store = store
    app.send_text = AsyncMock()
    app.place_call = AsyncMock()
    assert await app.deliver(retry, False) == "message_sent"
    assert app.send_text.call_args.kwargs == {"random_id": first["message_random_id"]}

    store.recover_reminders(due, all_inflight=True)
    confirmed = store.claim_due(due)
    assert await app.deliver(confirmed, False) == "message_sent"
    app.send_text.assert_awaited_once()
    app.place_call.assert_not_awaited()
    store.finish(confirmed, now=due)
    following = store.claim_due(due + timedelta(days=1))
    assert following["message_random_id"] != first["message_random_id"]
    assert not following["message_confirmed"]


async def test_delivered_reminder_is_not_retried_when_call_status_fails():
    app = AgentApp.__new__(AgentApp)
    app.settings = SimpleNamespace(timezone="Asia/Tashkent", enable_voice_calls=True)
    app.call_lock = asyncio.Lock()
    app.send_text = AsyncMock(side_effect=[None, OSError()])
    app.place_call = AsyncMock(side_effect=TimeoutError())
    reminder = {"id": 1, "title": "QA", "due": utc_now().isoformat(), "mode": "call"}
    assert await app.deliver(reminder, False) == "message_fallback"
    assert app.send_text.await_count == 2
    app.place_call.assert_awaited_once()


def test_third_recording_send_crash_is_not_misleading_ready_forever(store):
    store.start_recording("a" * 32, 77, "QA", None)
    store.recording_ready("a" * 32, "a.ogg", "a.incoming.ogg", 2)
    with store.db:
        store.db.execute("UPDATE recordings SET state='sending',attempts=3")
    store.recover_recordings()
    row = store.list_recordings()[0]
    assert row["state"] == "failed" and "tasdiqlanmagan" in row["last_error"]
    assert store.claim_recording() is None
    store.retry_recording(row["id"])
    assert store.claim_recording() is not None


async def test_restriction_latch_survives_policy_restart(brain):
    first = TelegramPolicy(brain.settings, brain.store)
    with pytest.raises(TelegramPaused):
        await first.action(AsyncMock(side_effect=errors.PeerFloodError(request=None)))
    operation = AsyncMock()
    with pytest.raises(TelegramPaused):
        await TelegramPolicy(brain.settings, brain.store).action(operation)
    operation.assert_not_called()


async def test_network_reconnect_recovers_but_manual_stop_stays_stopped(brain, tmp_path):
    created = []

    def factory(settings):
        obj = SimpleNamespace(ready=asyncio.Event())
        index = len(created)
        created.append(obj)

        async def run():
            if index == 0:
                raise ConnectionError("offline")
            obj.ready.set()
            await asyncio.Event().wait()

        obj.run = run
        return obj

    control = PanelControl(brain.settings, tmp_path, agent_factory=factory)
    control.retry_delays = (0,)
    try:
        await control.start()
        async with asyncio.timeout(1):
            while len(created) < 2 or not created[1].ready.is_set():
                await asyncio.sleep(0.001)
        assert control.connected
        await control.stop()
        await asyncio.sleep(0.01)
        assert len(created) == 2 and not control.running and control.phase == "stopped"
    finally:
        await control.close()


@pytest.mark.parametrize("error", [TelegramPaused("restricted"), ValueError("invalid config")])
async def test_account_and_config_errors_never_enter_reconnect_loop(brain, tmp_path, error):
    factory = Mock(
        return_value=SimpleNamespace(ready=asyncio.Event(), run=AsyncMock(side_effect=error))
    )
    control = PanelControl(brain.settings, tmp_path, agent_factory=factory)
    try:
        await control.start()
        await control.task
        assert control.phase == "error" and factory.call_count == 1
    finally:
        await control.close()


@pytest.mark.parametrize("worker", ["recordings", "notifications"])
async def test_critical_delivery_worker_crash_is_not_silently_healthy(brain, monkeypatch, worker):
    from telegram_agent import app as module
    from telegram_agent import contact_sync, notifications, recordings, scheduler

    async def pending(*args):
        await asyncio.Event().wait()

    async def fail(*args):
        raise RuntimeError("test worker failure")

    monkeypatch.setattr(recordings, "run_recordings", fail if worker == "recordings" else pending)
    monkeypatch.setattr(
        notifications, "run_notifications", fail if worker == "notifications" else pending
    )
    monkeypatch.setattr(scheduler.Scheduler, "run", pending)
    monkeypatch.setattr(contact_sync, "telegram_contacts", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "ensure_telegram_account", AsyncMock(return_value=User(id=1)))
    monkeypatch.setattr(module, "configured_owner", AsyncMock(return_value=User(id=42)))
    app = AgentApp.__new__(AgentApp)
    app.settings, app.store = brain.settings, brain.store
    app.brain = brain
    app.policy = TelegramPolicy(brain.settings, brain.store)
    app.telegram = SimpleNamespace(
        connect=AsyncMock(),
        get_input_entity=AsyncMock(),
        add_event_handler=lambda *a: None,
        disconnected=asyncio.get_running_loop().create_future(),
    )
    app.scheduler_task = app.contact_queue_task = None
    app.background_tasks = set()
    app.hangup = AsyncMock()
    with pytest.raises(ConnectionError, match="Yetkazish"):
        await asyncio.wait_for(app._run(), 1)
    assert app.scheduler_task.cancelled()


@pytest.mark.parametrize("codes,expected", [([0], 1), ([1, 0], 2), ([1, 1, 1, 1, 1], 5)])
def test_process_supervisor_respects_clean_shutdown_and_bounds_crash_retry(
    tmp_path, codes, expected
):
    results = iter(codes)
    launch = Mock(side_effect=lambda *a, **k: SimpleNamespace(wait=lambda: next(results)))
    waits = []
    assert (
        supervise(tmp_path, process_factory=launch, pause=waits.append, available=lambda: False)
        == 0
    )
    assert launch.call_count == expected and len(waits) == expected - 1


def test_supervisor_does_not_open_duplicate_telegram_session(tmp_path):
    launch = Mock()
    assert supervise(tmp_path, process_factory=launch, available=lambda: True) == 0
    launch.assert_not_called()
