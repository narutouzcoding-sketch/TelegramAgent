import asyncio
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.tl.types import User

from telegram_agent.ai_access import AIUnavailable
from telegram_agent.call_intent import effective_call_mode
from telegram_agent.contact_conversation import ContactConversation, talk_to_contact
from telegram_agent.free_voice import FreeVoiceSession, SpeechSegments


def tone(amplitude=1200):
    return struct.pack(
        "<480h", *(round(amplitude * math.sin(2 * math.pi * 220 * i / 48000)) for i in range(480))
    )


SPEECH = tone()
SILENCE = bytes(960)


@pytest.mark.parametrize(
    "message,mode,expected",
    [
        ("Tanladingmi", "relay", "ask"),
        ("Tanladingmi?", "relay", "ask"),
        ("Qayerdasan Ahvoling yaxshimi", "relay", "ask"),
        ("Nonushtaga nima olib boray, deb so‘ra", "relay", "ask"),
        ("Are you coming", "relay", "ask"),
        ("Где ты", "relay", "ask"),
        ("Bugun soat 20:00 da uchrashamiz", "relay", "relay"),
        ("Faqat “Tanladingmi?” deb ayt, javob kutma", "relay", "relay"),
        ("Just say: Are you coming? No answer needed", "relay", "relay"),
        ("Havola https://example.com/?nima=1", "relay", "relay"),
        ("Sami bilan uchrashamiz", "relay", "relay"),
        ("U nima deganini bilmayman", "relay", "relay"),
        ("Qayerda ekanimni keyin aytaman", "relay", "relay"),
        ("Nima bo'lganini keyin tushuntiraman", "relay", "relay"),
        ("Tanladingmi?", "record", "record"),
        ("Tanladingmi?", "voice", "voice"),
        ("Tanladingmi?", "conversation", "conversation"),
    ],
)
def test_question_guard_preserves_explicit_one_way_intent(message, mode, expected):
    assert effective_call_mode(message, mode) == expected


def test_question_guard_is_applied_before_deduplication(store):
    first = store.queue_contact_call("@qa_example", "Tanladingmi", mode="relay")
    again = store.queue_contact_call("@qa_example", "Tanladingmi", mode="ask")
    assert first["mode"] == again["mode"] == "ask"
    assert first["id"] == again["id"] and again["duplicate_suppressed"]
    row = store.queue_contact_call("@qa_other", "Bugun uchrashamiz", mode="relay")
    assert row["mode"] == "relay"


def test_browser_preview_and_backend_agree_on_question_intent():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node required for browser intent contract")
    cases = [
        "Tanladingmi",
        "Nonushtaga nima olib boray, deb so‘ra",
        "Где ты",
        "U nima deganini bilmayman",
        "Qayerda ekanimni keyin aytaman",
        "Nima bo'lganini keyin tushuntiraman",
        "Sami bilan uchrashamiz",
        "Faqat ayt: Qayerdasan? Javob kutma",
        "https://example.com/?nima=1",
    ]
    script = "const fs=require('fs'),vm=require('vm');const box={window:{}};vm.createContext(box);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),box);const items=JSON.parse(process.argv[2]);process.stdout.write(JSON.stringify(items.map(x=>box.window.AgentCallIntent.effective(x,'relay'))));"
    result = subprocess.check_output(
        [
            node,
            "-e",
            script,
            str(Path("telegram_agent/panel_web/call-intent.js")),
            json.dumps(cases),
        ],
        text=True,
    )
    assert json.loads(result) == [effective_call_mode(c, "relay") for c in cases]


def test_quiet_voice_below_old_threshold_is_not_discarded():
    detector = SpeechSegments(silence_frames=100)
    quiet = tone(45)  # RMS ~31; the previous fixed cutoff of150 lost this completely.
    for frame in [SILENCE] * 20 + [quiet] * 40:
        assert detector.push(frame) is None
    result = None
    for _ in range(100):
        result = detector.push(SILENCE) or result
    assert result and quiet * 40 in result


def test_short_thinking_pause_does_not_split_the_answer():
    detector = SpeechSegments(silence_frames=100)
    for frame in [SPEECH] * 30 + [SILENCE] * 80 + [SPEECH] * 30:
        assert detector.push(frame) is None
    utterance = detector.flush()
    assert utterance.count(SPEECH) == 60


def test_stationary_background_is_learned_and_does_not_keep_turn_open():
    detector = SpeechSegments(silence_frames=100)
    background = tone(45)
    for frame in [background] * 50 + [SPEECH] * 40:
        detector.push(frame)
    utterances = [detector.push(background) for _ in range(110)]
    assert any(utterances)
    assert detector.voiced == 0


async def test_peer_hangup_cancels_pending_followup_synthesis():
    brain = voice_brain()
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def stalled_speech(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    brain.speech = stalled_speech
    voice = FreeVoiceSession(brain, AsyncMock(), "")
    operation = asyncio.create_task(voice.speak("Savolni qaytaraman"))
    await started.wait()
    voice.remote_end()
    await asyncio.wait_for(operation, 1)
    assert cancelled.is_set() and not voice.output


def voice_brain():
    result = SimpleNamespace(
        use_native_asr=True,
        free_speech=SimpleNamespace(
            prepare=AsyncMock(), transcribe_pcm48=AsyncMock(return_value="Uyda")
        ),
        answer=AsyncMock(return_value="Rahmat"),
        speech=AsyncMock(),
    )
    result.free_speech.speech = result.speech
    return result


async def wait_until(predicate, timeout=2):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


async def test_wall_clock_flush_recognizes_reply_when_silent_packets_stop():
    brain = voice_brain()
    voice = FreeVoiceSession(brain, AsyncMock(), "")
    voice.accepting, voice.busy = True, False
    voice.speak = AsyncMock()
    worker = asyncio.create_task(voice.feed())
    try:
        for _ in range(40):
            voice.accept_pcm48(SPEECH)
        await wait_until(lambda: brain.answer.await_count == 1)
        assert brain.answer.call_args.args == ("Uyda",)
        assert voice.metrics["utterances"] == 1
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await voice.close()


async def test_remote_end_flushes_final_reply_without_speaking_to_disconnected_peer():
    brain = voice_brain()
    voice = FreeVoiceSession(brain, AsyncMock(), "")
    voice.accepting, voice.busy = True, False
    voice.speak = AsyncMock()
    worker = asyncio.create_task(voice.feed())
    voice.tasks = [worker]
    for _ in range(40):
        voice.accept_pcm48(SPEECH)
    voice.remote_end()
    await asyncio.wait_for(voice.closed.wait(), 2)
    brain.answer.assert_awaited_once_with("Uyda")
    voice.speak.assert_not_called()
    await voice.close()


async def test_sender_must_finish_last_packet_before_question_is_delivered():
    brain = voice_brain()
    brain.greeting_pcm = SPEECH
    last_frame_started, release = asyncio.Event(), asyncio.Event()

    async def sender(frame):
        if frame == SPEECH:
            last_frame_started.set()
            await release.wait()

    voice = FreeVoiceSession(brain, sender, "")
    try:
        await voice.start()
        await asyncio.wait_for(last_frame_started.wait(), 1)
        await asyncio.sleep(0.06)
        assert not getattr(brain, "question_delivered", False)
        assert not voice.accepting
        release.set()
        await wait_until(lambda: voice.accepting)
        assert brain.question_delivered
    finally:
        await voice.close()


async def test_batched_audio_after_first_turn_is_not_cleared():
    brain = voice_brain()
    voice = FreeVoiceSession(brain, AsyncMock(), "")
    voice.accepting, voice.busy = True, False
    voice.speak = AsyncMock()
    worker = asyncio.create_task(voice.feed())
    try:
        voice.accept_pcm48((SPEECH * 40 + SILENCE * 100) * 2)
        await wait_until(lambda: brain.answer.await_count == 2)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await voice.close()


async def test_tts_failure_prevents_dialing():
    brain = voice_brain()
    brain.speech = AsyncMock(side_effect=AIUnavailable("TTS unavailable"))
    brain.free_speech.speech = brain.speech
    task = ContactConversation(brain, "QA", {"mode": "ask", "message": "Qayerdasan?"})
    app = SimpleNamespace(
        call_lock=asyncio.Lock(),
        calls=SimpleNamespace(leave_call=AsyncMock()),
        policy=SimpleNamespace(dial=AsyncMock()),
    )
    with pytest.raises(AIUnavailable):
        await talk_to_contact(app, User(id=77), {"id": 1}, task)
    app.policy.dial.assert_not_called()


async def test_introduction_is_synthesized_and_decoded_before_dial(monkeypatch):
    from telegram_agent import free_voice

    brain = voice_brain()
    task = ContactConversation(brain, "QA", {"mode": "ask", "message": "Qayerdasan?"})
    decode = AsyncMock(return_value=SPEECH)
    monkeypatch.setattr(free_voice, "decode_pcm", decode)

    async def dial(*args):
        brain.speech.assert_awaited_once()
        decode.assert_awaited_once()
        raise ValueError("test ends before any real call")

    app = SimpleNamespace(
        call_lock=asyncio.Lock(),
        calls=SimpleNamespace(leave_call=AsyncMock()),
        policy=SimpleNamespace(dial=dial),
        settings=SimpleNamespace(ring_timeout_seconds=1),
    )
    with pytest.raises(ValueError, match="test ends"):
        await talk_to_contact(app, User(id=77), {"id": 1}, task)


async def test_live_quota_failure_does_not_initialize_or_download_local_model(brain):
    brain.use_native_asr = True
    brain.gemini = SimpleNamespace(transcribe_audio=AsyncMock(side_effect=AIUnavailable("quota")))
    brain.free_speech = SimpleNamespace(
        model=None, prepare=AsyncMock(), transcribe_pcm48=AsyncMock()
    )
    with pytest.raises(AIUnavailable, match="tayyor mahalliy model"):
        await brain.transcribe_live_pcm48(SPEECH)
    brain.free_speech.prepare.assert_not_called()
    brain.free_speech.transcribe_pcm48.assert_not_called()


async def test_live_quota_can_use_already_loaded_fallback(brain):
    brain.use_native_asr = True
    brain.gemini = SimpleNamespace(transcribe_audio=AsyncMock(side_effect=AIUnavailable("quota")))
    brain.free_speech = SimpleNamespace(
        model=object(), transcribe_pcm48=AsyncMock(return_value="Uyda")
    )
    assert await brain.transcribe_live_pcm48(SPEECH) == "Uyda"


async def test_asr_service_failure_is_not_a_silent_wait_or_a_success():
    brain = voice_brain()
    brain.outcome, brain.finished = "no_answer", False
    brain.free_speech.transcribe_pcm48.side_effect = AIUnavailable("quota")
    voice = FreeVoiceSession(brain, AsyncMock(), "")
    voice.speak = AsyncMock()
    await voice.process_utterance(SPEECH * 40)
    assert voice.closed.is_set() and brain.outcome == "answer_unverified"
    brain.answer.assert_not_called()
    assert voice.metrics["asr_errors"] == 1


async def test_silence_watchdog_repeats_once_then_reports_no_answer():
    brain = voice_brain()
    task = ContactConversation(brain, "QA", {"mode": "ask", "message": "Qayerdasan?"})
    voice = FreeVoiceSession(task, AsyncMock(), "")
    voice.accepting, voice.busy = True, False
    voice.speak = AsyncMock()
    voice.last_activity -= 11
    await voice.check_silence(SpeechSegments())
    assert "Qayerdasan" in voice.speak.call_args.args[0]
    await voice.check_silence(SpeechSegments())
    assert voice.closed.is_set() and task.result_state() == "no_answer"


async def test_failure_report_and_database_keep_audio_stage_diagnostics(store):
    brain = voice_brain()
    task = ContactConversation(brain, "QA", {"mode": "ask", "message": "Qayerdasan?"})
    task.voice_diagnostics = {"input_frames": 40, "utterances": 1, "asr_errors": 1}
    summary = await task.summary()
    assert "ovozni matnga" in summary
    job = store.queue_contact_call("@qa_example", "Qayerdasan?", mode="ask")
    store.save_contact_report(
        job["id"], task.transcript, summary, diagnostics=task.voice_diagnostics
    )
    assert json.loads(store.list_contact_calls()[0]["diagnostics"])["asr_errors"] == 1
