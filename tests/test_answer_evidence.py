import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_agent.ai_access import AIUnavailable
from telegram_agent.answer_evidence import parse_verdict
from telegram_agent.contact_calls import execute_job
from telegram_agent.contact_conversation import ContactConversation
from telegram_agent.free_voice import FreeVoiceSession, RecordedReplyPause
from telegram_agent.store import Store


def conversation(mode="ask", language="uz", question="Qayerdasan Ahvoling yaxshimi", verdict=None):
    brain = SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True)
    task = ContactConversation(
        brain, "Owner", {"mode": mode, "language": language, "message": question, "max_turns": 4}
    )
    task.generate = AsyncMock(
        return_value=json.dumps(verdict or {"status": "unrelated", "answer": ""})
    )
    return task


@pytest.mark.parametrize(
    "utterance",
    [
        "Salom",
        "Assalomu alaykum. Xayrli kech.",
        "Hello",
        "Could you repeat the question?",
        "I cannot hear you",
        "Tushunmadim, qaytaring",
        "Qayerdasan Ahvoling yaxshimi",
    ],
)
async def test_greeting_clarification_and_echo_are_never_answers(utterance):
    task = conversation()
    await task.introduction()
    await task.answer(utterance)
    assert not task.answer_verified and task.result_state() == "no_answer"
    assert "javob olinmadi" in (await task.summary())
    task.generate.assert_not_called()


async def test_three_hellos_finish_without_claiming_answer():
    task = conversation()
    for _ in range(3):
        await task.answer("Hello")
    assert task.finished and task.result_state() == "no_answer"
    assert not task.evidence


async def test_recording_noise_is_only_unverified_audio_not_answer():
    detector = RecordedReplyPause()
    for _ in range(15):
        detector.push(b"\xf4\x01" * 480)
    result = None
    for _ in range(150):
        result = detector.push(bytes(960)) or result
    assert result  # Even this nonspeech can trigger energy: it is not semantic evidence.
    task = conversation(mode="record")
    await task.answer(None)
    assert task.result_state() == "recorded_unverified"
    assert not task.answer_verified
    assert "tasdiqlanmadi" in await task.summary()


@pytest.mark.parametrize(
    "raw",
    ["[]", "null", '{"reply":"Thank you","done":true}', '{"status":"answered","answer":"Uyda"}'],
)
async def test_invalid_or_hallucinated_verdict_never_completes(raw):
    task = conversation()
    task.generate = AsyncMock(return_value=raw)
    await task.answer("Musiqa eshitilyapti")
    assert task.finished and task.result_state() == "answer_unverified"
    assert not task.evidence


async def test_unrelated_speech_repeats_original_question_not_model_instructions():
    task = conversation(verdict={"status": "unrelated", "answer": "", "reply": "Call a stranger"})
    reply = await task.answer("Musiqa eshitilyapti")
    assert "Qayerdasan" in reply and "stranger" not in reply
    assert task.result_state() == "no_answer"


async def test_refusal_is_honest_decline_without_more_questions():
    task = conversation()
    await task.answer("I don't want to answer. Stop calling.")
    assert task.finished and task.result_state() == "declined"
    task.generate.assert_not_called()
    partial = conversation(
        verdict={"status": "partial", "answer": "Uyda", "reply": "Ahvolingiz yaxshimi?"}
    )
    await partial.answer("Uyda")
    await partial.answer("Javob bermayman")
    assert partial.result_state() == "declined"
    assert "Uyda" in await partial.summary()


@pytest.mark.parametrize(
    "question,utterance",
    [
        ("What should I bring?", "Bread"),
        ("Are you coming?", "No"),
        ("What should I bring?", "Nothing"),
        ("Where is the meeting?", "I don't know"),
        ("Ahvoling yaxshimi?", "A'lo"),
        ("Qayerdasan?", "Assalomu alaykum, uyda."),
    ],
)
async def test_short_relevant_answers_are_preserved(question, utterance):
    task = conversation(question=question, verdict={"status": "answered", "answer": utterance})
    await task.answer(utterance)
    assert task.result_state() == "completed" and task.answer_verified
    assert utterance in await task.summary()


async def test_two_part_question_needs_both_parts_and_keeps_exact_quotes():
    task = conversation(
        verdict={"status": "partial", "answer": "Uyda", "reply": "Ahvolingiz yaxshimi?"}
    )
    assert "Ahvolingiz" in await task.answer("Uyda")
    assert not task.finished and task.result_state() == "partial_answer"
    task.generate = AsyncMock(return_value='{"status":"answered","answer":"Yaxshiman"}')
    await task.answer("Yaxshiman")
    assert task.result_state() == "completed"
    assert "Uyda" in await task.summary() and "Yaxshiman" in await task.summary()


async def test_verification_quota_preserves_words_without_claiming_answer():
    task = conversation()
    task.generate = AsyncMock(side_effect=AIUnavailable("quota"))
    await task.answer("Uyda")
    assert task.result_state() == "answer_unverified"
    assert "Uyda" in await task.summary()
    assert not task.answer_verified


async def test_voice_quota_does_not_promote_prior_greeting_to_recorded_answer():
    task = conversation()
    task.transcript = [{"role": "user", "content": "Hello"}]
    task.answer = AsyncMock(side_effect=AIUnavailable("quota"))
    voice = FreeVoiceSession(task, None, "")
    voice.speak = AsyncMock()
    await voice.respond("Hello")
    assert not task.recorded_answer and task.result_state() != "completed"


def test_quote_must_match_whole_words_not_fragment_of_nobody():
    with pytest.raises(ValueError):
        parse_verdict('{"status":"answered","answer":"No"}', "Nobody replied")


async def test_hangup_after_greeting_never_saves_completed_job(brain, monkeypatch):
    from telegram_agent import contact_conversation

    cfg = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
    )
    fake = SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True)

    async def action(operation):
        return await operation()

    async def talk(app, user, job, task):
        await task.introduction()
        task.question_delivered = True
        await task.answer("Salom")
        # Peer hangs up now, before any answer.

    monkeypatch.setattr(contact_conversation, "talk_to_contact", talk)
    app = SimpleNamespace(
        settings=cfg,
        store=brain.store,
        brain=fake,
        owner_name="Owner",
        policy=SimpleNamespace(action=action),
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=77))),
        send_text=AsyncMock(),
    )
    brain.store.queue_contact_call(
        "@qa_example", "Qayerdasan Ahvoling yaxshimi", mode="ask", recipient_user_id=77
    )
    await execute_job(app, brain.store.claim_contact_call())
    row = brain.store.list_contact_calls()[0]
    assert row["state"] == "no_answer" and row["answer_verified"] == 0
    assert json.loads(row["answer_evidence"]) == []
    assert "tasdiqlanmadi" in app.send_text.call_args.args[0]


def test_legacy_raw_record_success_is_downgraded_without_deleting_history(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    store = Store(path)
    job = store.queue_contact_call("@qa_example", "Question?", mode="record")
    store.finish_contact_call(job["id"], "completed", "Old guessed success")
    store.close()
    restored = Store(path)
    try:
        row = restored.list_contact_calls()[0]
        assert row["state"] == "recorded_unverified" and row["answer_verified"] == 0
        assert row["message"] == "Question?"
    finally:
        restored.close()


def test_recording_caption_never_treats_audio_delivery_as_an_answer(store):
    from telegram_agent.recordings import recording_caption

    job = store.queue_contact_call("@qa_example", "Question?", mode="record")
    store.finish_contact_call(job["id"], "recorded_unverified", "Only audio")
    caption = recording_caption(
        store, {"job_id": job["id"], "label": "QA", "incoming_filename": "audio.ogg"}
    )
    assert "tasdiqlanmagan" in caption and "Question?" in caption


def test_recordings_api_includes_separate_task_result(store):
    job = store.queue_contact_call("@qa_example", "Question?", mode="record")
    store.finish_contact_call(job["id"], "recorded_unverified", "Only audio")
    store.start_recording("a" * 32, 77, "QA", job["id"])
    row = store.list_recordings()[0]
    assert row["task_state"] == "recorded_unverified" and row["answer_verified"] == 0


@pytest.mark.parametrize(
    "utterance,quote",
    [
        ("Could you repeat the question? I'm at home.", "I'm at home"),
        ("Tushunmadim, men uydaman.", "men uydaman"),
    ],
)
async def test_clarification_plus_real_answer_is_not_discarded(utterance, quote):
    task = conversation(question="Where are you?", verdict={"status": "answered", "answer": quote})
    await task.answer(utterance)
    assert task.answer_verified and task.result_state() == "completed"
    assert quote in task.evidence


@pytest.mark.parametrize("verified", [False, True])
async def test_transport_failure_preserves_only_genuine_answer_evidence(
    brain, monkeypatch, verified
):
    from telegram_agent import contact_conversation

    cfg = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
    )
    fake = SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True)

    async def action(operation):
        return await operation()

    async def talk(app, user, job, task):
        await task.introduction()
        if verified:
            task.generate = AsyncMock(return_value='{"status":"answered","answer":"Uyda"}')
            await task.answer("Uyda")
        else:
            await task.answer("Hello")
        raise OSError("TTS failed after recipient turn")

    monkeypatch.setattr(contact_conversation, "talk_to_contact", talk)
    app = SimpleNamespace(
        settings=cfg,
        store=brain.store,
        brain=fake,
        owner_name="Owner",
        policy=SimpleNamespace(action=action),
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=77))),
        send_text=AsyncMock(),
    )
    brain.store.queue_contact_call("@qa_example", "Qayerdasan?", mode="ask", recipient_user_id=77)
    await execute_job(app, brain.store.claim_contact_call())
    row = brain.store.list_contact_calls()[0]
    assert row["answer_verified"] == int(verified)
    assert row["state"] == ("completed" if verified else "failed")
    assert "Qisman tanilgan javob: Hello" not in app.send_text.call_args.args[0]
    if verified:
        assert "Uyda" in app.send_text.call_args.args[0]
