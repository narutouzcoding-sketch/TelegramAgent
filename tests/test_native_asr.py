import base64
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from openai import RateLimitError
from test_gemini import completion

from telegram_agent.ai_access import AIUnavailable
from telegram_agent.gemini_text import GeminiText
from telegram_agent.speech_input import pcm48_to_wav


async def test_native_audio_uses_short_wav_budget_and_never_exposes_tools(brain):
    adapter = GeminiText(replace(brain.settings, gemini_key="test"))
    await adapter.client.close()
    create = AsyncMock(
        return_value=completion({"role": "assistant", "content": "Nonushtaga nima olib boray?"})
    )
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    wav = pcm48_to_wav(bytes(9600))
    assert await adapter.transcribe_audio(wav) == "Nonushtaga nima olib boray?"
    args = create.call_args.kwargs
    content = args["messages"][-1]["content"][0]["input_audio"]
    assert base64.b64decode(content["data"]).startswith(b"RIFF")
    assert content["format"] == "wav"
    assert "tools" not in args and args["max_tokens"] == 384


async def test_audio_quota_never_sends_audio_to_text_only_local_model(brain):
    adapter = GeminiText(replace(brain.settings, gemini_key="test", local_fallback_enabled=True))
    await adapter.client.close()
    error = RateLimitError(
        "private", response=Mock(status_code=429, headers={}, request=Mock()), body={}
    )
    cloud = AsyncMock(side_effect=error)
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=cloud)), close=AsyncMock()
    )
    adapter.local = SimpleNamespace(create=AsyncMock(), available=True, close=AsyncMock())
    try:
        with pytest.raises(AIUnavailable):
            await adapter.transcribe_audio(pcm48_to_wav(bytes(9600)))
        with pytest.raises(AIUnavailable):
            await adapter.transcribe_audio(pcm48_to_wav(bytes(9600)))
        cloud.assert_awaited_once()
        adapter.local.create.assert_not_called()
    finally:
        await adapter.close()


async def test_native_asr_failure_falls_back_to_local_recognition(brain):
    brain.use_native_asr = True
    brain.gemini = SimpleNamespace(transcribe_audio=AsyncMock(side_effect=AIUnavailable("quota")))
    brain.free_speech = SimpleNamespace(transcribe_pcm48=AsyncMock(return_value="Mahalliy matn"))
    assert await brain.transcribe_pcm48(bytes(9600)) == "Mahalliy matn"
    brain.free_speech.transcribe_pcm48.assert_awaited_once()


async def test_unintelligible_native_audio_never_invents_an_answer(brain):
    adapter = GeminiText(replace(brain.settings, gemini_key="test"))
    await adapter.client.close()
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(
                    return_value=completion({"role": "assistant", "content": "[UNINTELLIGIBLE]"})
                )
            )
        )
    )
    assert await adapter.transcribe_audio(pcm48_to_wav(bytes(9600))) == ""
