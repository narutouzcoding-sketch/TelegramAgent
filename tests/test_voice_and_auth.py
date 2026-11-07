import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_agent.app import AgentApp, is_owner
from telegram_agent.voice import VoiceSession


@pytest.mark.parametrize(
    "private,sender,out,allowed",
    [
        (True, 42, False, True),
        (False, 42, False, False),
        (True, 99, False, False),
        (True, 42, True, False),
        (True, None, False, False),
    ],
)
def test_allowlist(private, sender, out, allowed):
    event = SimpleNamespace(is_private=private, sender_id=sender, out=out)
    assert is_owner(event, 42) == allowed


async def test_pcm_output_and_barge_in_clear_unheard_audio(brain):
    voice = VoiceSession(brain, AsyncMock(), "hello")
    voice.ws = SimpleNamespace(send_json=AsyncMock())
    await voice.handle(
        {
            "type": "response.output_audio.delta",
            "item_id": "item1",
            "delta": base64.b64encode(bytes(4800)).decode(),
        }
    )
    assert len(voice.output) >= 9
    assert all(len(frame) == 960 for _, frame in voice.output)
    voice.last_item, voice.played_ms = "item1", 30
    await voice.handle({"type": "input_audio_buffer.speech_started"})
    assert not voice.output
    assert not voice.tail
    event = voice.ws.send_json.call_args.args[0]
    assert event == {
        "type": "conversation.item.truncate",
        "item_id": "item1",
        "content_index": 0,
        "audio_end_ms": 30,
    }


async def test_pcm_input_is_downsampled_before_sending(brain):
    voice = VoiceSession(brain, AsyncMock(), "hello")
    sent = []

    async def send(event):
        sent.append(event)

    voice.send = send
    task = asyncio.create_task(voice.feed())
    voice.accept_pcm48(bytes(4800))  # 50ms mono16 at 48k -> 2400 bytes at 24k
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(base64.b64decode(sent[0]["audio"])) == 2400


async def test_realtime_function_call_persists_plan_and_continues(brain):
    voice = VoiceSession(brain, AsyncMock(), "hello")
    voice.ws = SimpleNamespace(send_json=AsyncMock())
    event = {
        "type": "response.done",
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "add_plan",
                    "arguments": '{"title":"Dars","details":"30 daqiqa"}',
                    "call_id": "voice-call-1",
                }
            ],
        },
    }
    await voice.handle(event)
    await voice.handle(event)
    assert len(brain.store.list_plans()) == 1
    assert voice.ws.send_json.call_args.args[0] == {"type": "response.create"}


async def test_unauthorized_message_never_reaches_model(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings = brain.settings
    app.brain = SimpleNamespace(answer=AsyncMock())
    app.send_text = AsyncMock()
    await app.on_message(SimpleNamespace(is_private=True, sender_id=777, out=False))
    app.brain.answer.assert_not_called()
    app.send_text.assert_not_called()


async def test_call_failure_falls_back_to_saved_message(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings = brain.settings
    app.call_lock = asyncio.Lock()
    app.send_text = AsyncMock()
    app.place_call = AsyncMock(side_effect=TimeoutError())
    row = {"id": 1, "title": "Dars", "due": "2030-01-01T04:00:00+00:00", "mode": "call"}
    result = await app.deliver(row, late=False)
    assert result == "message_fallback"
    assert "Dars" in app.send_text.call_args_list[0].args[0]
    assert app.send_text.await_count == 2


async def test_busy_call_delivers_text_without_second_call(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings = brain.settings
    app.call_lock = asyncio.Lock()
    app.send_text = AsyncMock()
    app.place_call = AsyncMock()
    row = {"id": 1, "title": "Dars", "due": "2030-01-01T04:00:00+00:00", "mode": "call"}
    async with app.call_lock:
        assert await app.deliver(row, late=False) == "message_sent"
    app.place_call.assert_not_called()


async def test_connection_releases_scheduler_while_conversation_continues(brain):
    app = AgentApp.__new__(AgentApp)
    app.background_tasks = set()
    app.send_text = AsyncMock()
    finish = asyncio.Event()

    async def long_conversation(introduction, ready):
        ready.set_result(True)
        await finish.wait()

    app.conversation = long_conversation
    assert await asyncio.wait_for(app.place_call("eslatma"), timeout=1) == "call_connected"
    assert len(app.background_tasks) == 1
    finish.set()
    await asyncio.gather(*app.background_tasks)


async def test_speech_after_completed_playback_does_not_truncate_old_item(brain):
    voice = VoiceSession(brain, AsyncMock(), "hello")
    voice.ws = SimpleNamespace(send_json=AsyncMock())
    voice.last_item, voice.played_ms = "old-completed-item", 500
    await voice.handle({"type": "input_audio_buffer.speech_started"})
    voice.ws.send_json.assert_not_called()


async def test_voice_start_uses_current_api_schema_and_restores_history(brain, monkeypatch):
    import json

    import aiohttp

    sent = []
    received = asyncio.Queue()
    await received.put(
        SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data='{"type":"session.created"}')
    )
    await received.put(
        SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data='{"type":"session.updated"}')
    )

    class Socket:
        async def send_json(self, value):
            sent.append(value)

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await received.get()

        async def close(self):
            pass

    class Http:
        def __init__(self, **kwargs):
            pass

        async def ws_connect(self, url, **kwargs):
            assert url == "wss://api.openai.com/v1/realtime"
            assert kwargs["params"]["model"] == "gpt-realtime-2.1"
            return Socket()

        async def close(self):
            pass

    monkeypatch.setattr(aiohttp, "ClientSession", Http)
    brain.store.remember("user", "Salom")
    brain.store.remember("assistant", "Salom, men AI yordamchingizman")
    voice = VoiceSession(brain, AsyncMock(), "Salom bering")
    await voice.start()
    await voice.close()
    session = sent[0]["session"]
    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is True
    assert sent[2]["item"]["content"][0]["type"] == "output_text"
    assert sent[-1]["type"] == "response.create"
    # JSON serialization also catches accidental binary or SDK objects in protocol messages.
    json.dumps(sent)
