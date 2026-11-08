import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytgcalls.exceptions import CallBusy, CallDeclined, CallDiscarded, TimedOutAnswer
from telethon.errors import UserPrivacyRestrictedError

from telegram_agent.call_outcomes import connection_outcome
from telegram_agent.contact_calls import execute_job
from telegram_agent.contact_conversation import ContactConversation
from telegram_agent.store import Store


@pytest.mark.parametrize(
    "error,state",
    [
        (TimedOutAnswer(), "unanswered"),
        (CallBusy(77), "busy"),
        (CallDeclined(77), "rejected"),
        (CallDiscarded(77), "unanswered"),
        (UserPrivacyRestrictedError(request=None), "privacy_blocked"),
    ],
)
def test_unconnected_call_outcomes_never_claim_asr_failure_or_existing_recording(error, state):
    result, report = connection_outcome(error, 60)
    assert result == state
    assert "Savol eshittirilmadi" in report and "yozuvi yaratilmagan" in report
    assert "tinglash paytida" not in report and "Mavjud asl ovoz" not in report


def test_connection_timeout_code_is_not_used_to_overwrite_connected_call_evidence():
    assert connection_outcome(TimedOutAnswer(), 60, connected=True) is None


async def test_timeout_reports_one_connection_outcome_without_retrying_or_using_asr(
    brain, monkeypatch
):
    from telegram_agent import contact_conversation

    cfg = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
        ring_timeout_seconds=60,
    )
    fake = SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True)

    async def action(op):
        return await op()

    async def timed_out(app, user, job, task):
        await task.introduction()
        task.voice_diagnostics = {
            "connected": False,
            "recording_started": False,
            "input_frames": 0,
            "playback_frames": 0,
            "stage": "dialing",
        }
        raise TimedOutAnswer()

    talk = AsyncMock(side_effect=timed_out)
    monkeypatch.setattr(contact_conversation, "talk_to_contact", talk)
    app = SimpleNamespace(
        settings=cfg,
        store=brain.store,
        brain=fake,
        owner_name="QA",
        policy=SimpleNamespace(action=action),
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=77))),
        send_text=AsyncMock(),
    )
    brain.store.queue_contact_call("@qa_example", "Qayerdasan?", mode="ask", recipient_user_id=77)
    await execute_job(app, brain.store.claim_contact_call())
    row = brain.store.list_contact_calls()[0]
    assert row["state"] == "unanswered" and not row["question_delivered"]
    assert json.loads(row["diagnostics"])["error_code"] == "TimedOutAnswer"
    report = app.send_text.call_args.args[0]
    assert "60 soniya" in report and "texnik holat" not in report and "Mavjud" not in report
    talk.assert_awaited_once()
    assert not brain.store.list_recordings()


async def test_connected_silence_remains_different_from_unconnected_call():
    task = ContactConversation(
        SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True),
        "QA",
        {"mode": "ask", "message": "Question?"},
    )
    task.question_delivered = True
    task.voice_diagnostics = {
        "connected": True,
        "recording_started": False,
        "input_frames": 0,
        "playback_frames": 40,
    }
    report = await task.summary()
    assert "tinglash paytida" in report and "ulanishi tasdiqlanmadi" not in report


def test_legacy_timeout_without_media_is_repaired_but_real_recordings_are_preserved(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    store = Store(path)
    first = store.queue_contact_call("@qa_example", "Question?", mode="ask")
    store.finish_contact_call(first["id"], "failed", "TimedOutAnswer")
    second = store.queue_contact_call("@qa_other", "Question?", mode="ask")
    store.start_recording("a" * 32, 77, "QA", second["id"])
    store.finish_contact_call(second["id"], "failed", "TimedOutAnswer")
    store.close()
    store = Store(path)
    try:
        rows = {r["id"]: r for r in store.list_contact_calls()}
        assert rows[first["id"]]["state"] == "unanswered"
        assert "yozuvi yaratilmagan" in rows[first["id"]]["summary"]
        assert rows[second["id"]]["state"] == "failed"
        assert len(store.list_recordings()) == 1
    finally:
        store.close()
