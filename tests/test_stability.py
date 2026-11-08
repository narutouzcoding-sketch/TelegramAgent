import asyncio
import json
import struct
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp.test_utils import TestClient, TestServer
from openai import RateLimitError
from test_gemini import completion

from telegram_agent.app import AgentApp
from telegram_agent.contact_conversation import ContactConversation
from telegram_agent.free_voice import FreeVoiceSession, SpeechSegments
from telegram_agent.gemini_text import GeminiText
from telegram_agent.panel import PanelControl, create_panel
from telegram_agent.recordings import CallRecording, convert_recording, run_recordings

PCM = struct.pack("<h", 2000) * 480


async def test_original_audio_survives_crash_and_is_encoded_without_ai(store, tmp_path):
    rec = CallRecording(store, 77, "Friend", root=tmp_path)
    rec.write("incoming", PCM * 30)
    rec.write("outgoing", bytes(960) * 30)
    # Simulate an unclean exit: PCM is durable even without an encoder/AI result.
    for track in rec.tracks.values():
        track.close()
    store.recover_recordings()
    row = store.pending_recordings("captured")[0]
    await convert_recording(store, row, tmp_path)
    row = store.list_recordings()[0]
    assert row["state"] == "ready"
    assert row["incoming_filename"]
    assert (
        (tmp_path / "data" / "recordings" / row["incoming_filename"])
        .read_bytes()
        .startswith(b"OggS")
    )
    assert not list((tmp_path / "data" / "recordings").glob("*.pcm"))


async def test_recording_worker_sends_original_voice_only_to_owner(store, tmp_path):
    rec = CallRecording(store, 77, "Friend", root=tmp_path)
    rec.write("incoming", PCM * 20)
    rec.close()

    async def send(action):
        return await action()

    app = SimpleNamespace(
        store=store,
        policy=SimpleNamespace(send=send),
        telegram=SimpleNamespace(send_file=AsyncMock()),
        owner=42,
    )
    worker = asyncio.create_task(run_recordings(app))
    try:
        async with asyncio.timeout(5):
            while store.list_recordings()[0]["state"] != "sent":
                await asyncio.sleep(0.02)
        args = app.telegram.send_file.call_args
        assert args.args[0] == 42
        assert args.args[1].endswith(".incoming.ogg")
        assert args.kwargs["voice_note"] is True
        assert args.kwargs["attributes"][0].duration >= 1
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_recordings_are_authenticated_and_paths_cannot_escape_data(brain, tmp_path):
    control = PanelControl(brain.settings, root=tmp_path)
    rid = "a" * 32
    control.store.start_recording(rid, 77, "Friend", None)
    folder = tmp_path / "data" / "recordings"
    folder.mkdir()
    (folder / "sample.ogg").write_bytes(b"OggS original sample")
    control.store.recording_ready(rid, "sample.ogg", "sample.ogg", 1)
    client = TestClient(TestServer(create_panel(control, "test-password-123")))
    await client.start_server()
    try:
        url = f"/api/recordings/{rid}/incoming"
        assert (await client.get(url)).status == 401
        await client.post("/api/login", json={"password": "test-password-123"})
        r = await client.get(url)
        assert r.status == 200 and (await r.read()).startswith(b"OggS")
        assert r.headers["Cache-Control"] == "no-store"
        control.store.recording_ready(rid, "../../outside", "../../outside", 1)
        assert (await client.get(url)).status == 404
    finally:
        await client.close()


async def test_record_mode_never_calls_gemini_or_whisper(monkeypatch):
    from telegram_agent import free_voice

    monkeypatch.setattr(free_voice, "decode_pcm", AsyncMock(return_value=PCM * 2))
    speech = SimpleNamespace(prepare=AsyncMock(), transcribe_pcm48=AsyncMock(), speech=AsyncMock())
    brain = SimpleNamespace(free_speech=speech, gemini=SimpleNamespace(create=AsyncMock()))
    task = ContactConversation(
        brain,
        "Owner",
        {"mode": "record", "language": "en", "message": "What should I bring for breakfast?"},
    )
    voice = FreeVoiceSession(task, AsyncMock(), await task.introduction())
    try:
        await voice.start()
        async with asyncio.timeout(3):
            while not voice.accepting:
                await asyncio.sleep(0.01)
        for frame in [PCM] * 20 + [bytes(960)] * 150:
            voice.accept_pcm48(frame)
        await asyncio.wait_for(voice.closed.wait(), 3)
        assert task.recorded_answer and task.finished
        assert "tasdiqlanmadi" in await task.summary()
        assert task.result_state() == "recorded_unverified"
        brain.gemini.create.assert_not_called()
        speech.prepare.assert_not_called()
        speech.transcribe_pcm48.assert_not_called()
    finally:
        await voice.close()


def test_quiet_short_answer_is_detected_and_thinking_does_not_discard_input():
    segments = SpeechSegments()
    quiet = struct.pack("<h", 200) * 480
    chunks = [segments.push(frame) for frame in [quiet] * 12 + [bytes(960)] * 65]
    assert any(chunks)
    voice = FreeVoiceSession(None, None, "")
    voice.accepting = True
    voice.busy = True
    voice.speaking = False
    voice.accept_pcm48(quiet)
    assert not voice.input.empty()
    voice.speaking = True
    voice.accept_pcm48(quiet)
    assert voice.input.qsize() == 1


def test_recording_capture_is_independent_of_voice_busy_state(store, tmp_path):
    rec = CallRecording(store, 77, "Friend", root=tmp_path)
    app = AgentApp.__new__(AgentApp)
    app.settings = SimpleNamespace(owner_id=42)
    app.active_recording = rec
    app.voice = None
    app.relay_target = 77
    app.relay_voice = SimpleNamespace(accept_pcm48=lambda _: None)
    app.receive_audio(SimpleNamespace(chat_id=77, frames=[SimpleNamespace(frame=PCM)]))
    assert rec.positions["incoming"] >= 960
    rec.close()


async def test_normal_remote_hangup_is_not_reported_as_ai_error():
    class NotInCallError(Exception):
        pass

    async def ended():
        raise NotInCallError()

    voice = FreeVoiceSession(None, None, "")
    await voice.guarded(ended)
    assert voice.closed.is_set() and voice.error is None


async def test_greeting_does_not_receive_tool_schemas_and_write_uses_one_request(brain):
    brain.gemini = SimpleNamespace(
        create=AsyncMock(return_value=completion({"role": "assistant", "content": "Salom"}))
    )
    await brain.answer("Salom")
    assert brain.gemini.create.call_args.args[2] == []
    tool = completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "one-write",
                    "type": "function",
                    "function": {
                        "name": "add_plan",
                        "arguments": '{"title":"Kitob","details":"10 bet"}',
                    },
                }
            ],
        },
        "tool_calls",
    )
    brain.gemini.create = AsyncMock(return_value=tool)
    assert await brain.answer("Rejamga kitob o‘qishni qo‘sh") == "Reja #1 saqlandi."
    brain.gemini.create.assert_awaited_once()


async def test_truncated_plain_text_is_kept_but_incomplete_actions_never_execute(brain):
    brain.gemini = SimpleNamespace(
        create=AsyncMock(
            return_value=completion({"role": "assistant", "content": "Foydali javob"}, "length")
        )
    )
    assert "Foydali javob" in await brain.answer("Tushuntir")
    assert not brain.store.list_plans()


async def test_quota_uses_local_engine_and_honors_cooldown_without_key_rotation(brain):
    adapter = GeminiText(replace(brain.settings, gemini_key="test", local_fallback_enabled=True))
    await adapter.client.close()
    failure = RateLimitError(
        "private error",
        response=Mock(status_code=429, headers={"retry-after": "90"}, request=Mock()),
        body={},
    )
    cloud = AsyncMock(side_effect=failure)
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=cloud)), close=AsyncMock()
    )
    adapter.local = SimpleNamespace(
        create=AsyncMock(return_value=completion({"role": "assistant", "content": "Local reply"})),
        available=True,
        close=AsyncMock(),
    )
    try:
        await adapter.create("system", [], [])
        await adapter.create("system", [], [])
        cloud.assert_awaited_once()
        assert adapter.local.create.await_count == 2
        assert adapter.status()["cooldown_seconds"] >= 89
        assert adapter.status()["last_provider"] == "local"
    finally:
        await adapter.close()


async def test_preview_question_is_reused_and_greeting_is_not_mistaken_for_answer():
    create = AsyncMock(
        return_value=completion(
            {
                "role": "assistant",
                "content": "Hello. I am AI and this call is recorded. What should Owner bring?",
            }
        )
    )
    brain = SimpleNamespace(
        free_speech=SimpleNamespace(prepare=AsyncMock()), gemini=SimpleNamespace(create=create)
    )
    job = {"message": "Nonushta uchun nima kerak?", "language": "en", "mode": "ask"}
    first = ContactConversation(brain, "Owner", job)
    await first.introduction()
    second = ContactConversation(brain, "Owner", job)
    await second.introduction()
    await second.answer("Hello")
    assert not second.finished
    create.assert_awaited_once()


def test_tool_history_never_resends_full_call_transcripts():
    from telegram_agent.brain import Brain

    value = Brain.compact_result(
        "list_contact_calls",
        {
            "ok": True,
            "result": [
                {
                    "id": 1,
                    "target": "@friend",
                    "state": "completed",
                    "summary": "Summary",
                    "transcript": "x" * 20000,
                }
            ],
        },
    )
    assert len(json.dumps(value)) < 1000 and "transcript" not in value["result"][0]


def test_long_recorded_answer_is_not_cut_at_asr_fifteen_second_boundary():
    from telegram_agent.free_voice import RecordedReplyPause

    segmenter = RecordedReplyPause()
    assert all(segmenter.push(PCM) is None for _ in range(2200))
    replies = [segmenter.push(bytes(960)) for _ in range(150)]
    assert replies[-1] == b"recorded"
