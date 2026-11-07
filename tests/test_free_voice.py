import asyncio
import struct
import wave
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram_agent.free_speech import FreeSpeech
from telegram_agent.free_voice import FreeVoiceSession, SpeechSegments

LOUD = struct.pack("<h", 3000) * 480
SILENCE = bytes(960)


def test_segmenter_ignores_silence_and_clicks_but_keeps_full_utterance():
    segmenter = SpeechSegments()
    assert all(segmenter.push(SILENCE) is None for _ in range(100))
    segmenter.push(LOUD)
    assert all(segmenter.push(SILENCE) is None for _ in range(90))
    for _ in range(30):
        assert segmenter.push(LOUD) is None
    results = [segmenter.push(SILENCE) for _ in range(90)]
    assert results[-1] and LOUD * 30 in results[-1]
    assert not segmenter.frames


def test_continuous_speech_is_bounded():
    segmenter = SpeechSegments()
    utterance = None
    for _ in range(1500):
        utterance = segmenter.push(LOUD)
    assert utterance is not None and len(utterance) == 1500 * 960


async def test_free_audio_never_calls_openai(brain, tmp_path):
    brain.ai.request = AsyncMock(side_effect=AssertionError("Paid API must not be used"))
    brain.free_speech = SimpleNamespace(
        transcribe=AsyncMock(return_value="Salom"), speech=AsyncMock()
    )
    path = tmp_path / "sample.ogg"
    assert await brain.transcribe(path) == "Salom"
    await brain.speech("Salom", path)
    brain.ai.request.assert_not_called()


async def test_local_decoder_accepts_real_wav_without_network(brain, tmp_path):
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(bytes(32000))
    speech = FreeSpeech(brain.settings)
    seen = []
    speech._recognize = lambda audio: seen.append(len(audio)) or "local"
    assert await speech.transcribe(path) == "local"
    assert seen == [16000]


async def test_free_call_captures_next_turn_after_reply_and_closes_tasks(monkeypatch):
    from telegram_agent import free_voice

    monkeypatch.setattr(free_voice, "decode_pcm", AsyncMock(return_value=LOUD * 2))
    brain = SimpleNamespace(
        free_speech=SimpleNamespace(
            prepare=AsyncMock(), transcribe_pcm48=AsyncMock(return_value="Rejalarim qanday?")
        ),
        answer=AsyncMock(return_value="Javob"),
        speech=AsyncMock(),
    )
    sender = AsyncMock()
    voice = FreeVoiceSession(brain, sender, "Salom")
    try:
        await voice.start()
        async with asyncio.timeout(2):
            while voice.busy:
                await asyncio.sleep(0.01)
        for frame in [LOUD] * 30 + [SILENCE] * 90:
            voice.accept_pcm48(frame)
        async with asyncio.timeout(2):
            while brain.answer.await_count < 2 or voice.busy:
                await asyncio.sleep(0.01)
        brain.free_speech.transcribe_pcm48.assert_awaited_once()
        assert brain.answer.call_args.args == ("Rejalarim qanday?",)
        assert any(call.args == (LOUD,) for call in sender.call_args_list)
    finally:
        await voice.close()
    assert not voice.tasks
    assert voice.closed.is_set()


async def test_echo_and_overlapping_audio_are_dropped_and_errors_close_session():
    brain = SimpleNamespace(
        free_speech=SimpleNamespace(prepare=AsyncMock()),
        answer=AsyncMock(side_effect=RuntimeError("private payload")),
    )
    voice = FreeVoiceSession(brain, AsyncMock(), "Salom")
    voice.accept_pcm48(LOUD)
    assert voice.input.empty()
    await voice.start()
    await asyncio.wait_for(voice.closed.wait(), 1)
    assert "private payload" not in voice.error
    await voice.close()


def test_free_settings_can_run_without_openai_key(brain):
    from telegram_agent.brain import Brain

    settings = replace(
        brain.settings,
        openai_key="",
        voice_provider="free",
        text_provider="gemini",
        gemini_key="test",
    )
    free = Brain(settings, brain.store)
    assert free.free_speech is not None
    assert free.ai.clients == []
