import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from telegram_agent.app import AgentApp
from telegram_agent.contact_calls import execute_job, notify_owner, relay_text
from telegram_agent.contact_conversation import ContactConversation
from telegram_agent.telegram_policy import TelegramPaused


async def test_offline_report_saved_and_job_worker_does_not_crash(brain):
    cfg = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
    )

    async def action(operation):
        return await operation()

    app = SimpleNamespace(
        settings=cfg,
        store=brain.store,
        brain=brain,
        owner_name="QA",
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=88))),
        policy=SimpleNamespace(action=action),
        send_text=AsyncMock(side_effect=OSError("offline")),
    )
    row = brain.store.queue_contact_call("@qa_example", "Savol?", recipient_user_id=77)
    await execute_job(app, row)
    assert brain.store.list_contact_calls()[0]["state"] == "failed"
    assert "Qayta terilmadi" in brain.store.history()[-1]["content"]


async def test_notification_still_stops_on_telegram_restriction(brain):
    app = SimpleNamespace(
        store=brain.store, send_text=AsyncMock(side_effect=TelegramPaused("paused"))
    )
    with pytest.raises(TelegramPaused):
        await notify_owner(app, "QA")


async def test_quota_fallback_summary_preserves_partial_answer_and_does_not_claim_zero_ai():
    fake = SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True)
    task = ContactConversation(
        fake, "QA", {"mode": "conversation", "language": "uz", "message": "Savol?"}
    )
    task.transcript = [{"role": "user", "content": "Non olib keling"}]
    task.record_only = True
    summary = await task.summary()
    assert "Non olib keling" in summary
    assert "AI ishlatilmadi" not in summary


def test_record_mode_disabled_is_rejected_before_dial(brain):
    fake = SimpleNamespace(
        settings=replace(brain.settings, record_calls=False),
        free_speech=SimpleNamespace(),
        use_native_asr=True,
    )
    with pytest.raises(ValueError, match="RECORD_CALLS"):
        ContactConversation(fake, "QA", {"mode": "record", "message": "Savol?"})
    assert "yozilib" not in relay_text("QA", "Xabar", record_calls=False)


async def test_disabled_recording_introduction_does_not_promise_audio(brain):
    fake = SimpleNamespace(
        settings=replace(brain.settings, record_calls=False),
        free_speech=SimpleNamespace(),
        use_native_asr=True,
    )
    task = ContactConversation(fake, "QA", {"mode": "ask", "message": "Savol?"})
    assert "yozil" not in await task.introduction()
    assert "Audio recording is disabled" in task.instructions()


async def test_incoming_other_account_has_diagnostic_and_never_starts(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings, app.store = brain.settings, brain.store
    app.call_lock = asyncio.Lock()
    app.calls = SimpleNamespace(leave_call=AsyncMock())
    app.spawn = Mock()
    await app.on_incoming_call(99)
    app.calls.leave_call.assert_awaited_once_with(99)
    app.spawn.assert_not_called()
    assert "other_account_rejected" in app.store.telegram_state("last_call_event")


async def test_incoming_busy_owner_has_diagnostic_and_never_starts(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings, app.store = brain.settings, brain.store
    app.call_lock = asyncio.Lock()
    await app.call_lock.acquire()
    app.calls = SimpleNamespace(leave_call=AsyncMock())
    app.spawn = Mock()
    await app.on_incoming_call(42)
    assert '"busy"' in app.store.telegram_state("last_call_event")
    app.spawn.assert_not_called()


async def test_notification_failure_after_success_never_repeats_call(brain, monkeypatch):
    from telegram_agent import contact_calls

    cfg = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
    )

    async def action(operation):
        return await operation()

    brain.speech = AsyncMock()
    monkeypatch.setattr(contact_calls, "decode_pcm", AsyncMock(return_value=b"audio"))
    transport = AsyncMock()
    monkeypatch.setattr(contact_calls, "play_relay", transport)
    app = SimpleNamespace(
        settings=cfg,
        store=brain.store,
        brain=brain,
        owner_name="QA",
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=77))),
        policy=SimpleNamespace(action=action),
        send_text=AsyncMock(side_effect=[None, OSError("offline")]),
    )
    job = brain.store.queue_contact_call("@qa_example", "Xabar", recipient_user_id=77)
    brain.store.claim_contact_call()
    await execute_job(app, job)
    transport.assert_awaited_once()
    assert brain.store.list_contact_calls()[0]["state"] == "sent"
    assert brain.store.claim_contact_call() is None


def test_sandbox_accepts_current_call_options_without_real_queue(tmp_path):
    from telegram_agent.sandbox import SandboxStore

    store = SandboxStore(tmp_path / "qa.sqlite3")
    try:
        result = store.queue_contact_call(
            "@qa_example", "Question?", mode="record", language="en", duration_seconds=60
        )
        assert result["simulated"] and store.claim_contact_call() is None
        assert store.list_contact_calls()[0]["language"] == "en"
    finally:
        store.close()


async def test_voice_quota_with_recording_disabled_does_not_claim_saved_audio():
    from telegram_agent.ai_access import AIUnavailable
    from telegram_agent.free_voice import FreeVoiceSession

    brain = SimpleNamespace(
        answer=AsyncMock(),
        answer_voice=AsyncMock(side_effect=AIUnavailable("quota")),
        recording_enabled=False,
    )
    voice = FreeVoiceSession(brain, None, "")
    voice.speak = AsyncMock()
    await voice.respond("Savol")
    assert voice.closed.is_set()
    assert "yozish o'chirilgan" in voice.speak.call_args.args[0]
