from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from openai import RateLimitError

from telegram_agent.ai_access import AIUnavailable
from telegram_agent.free_voice import FreeVoiceSession
from telegram_agent.gemini_text import GeminiText


async def test_live_voice_does_not_wait_for_cpu_model_on_cloud_quota(brain):
    adapter = GeminiText(replace(brain.settings, gemini_key="test", local_fallback_enabled=True))
    await adapter.client.close()
    error = RateLimitError(
        "private", response=Mock(status_code=429, headers={}, request=Mock()), body={}
    )
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=error))),
        close=AsyncMock(),
    )
    adapter.local = SimpleNamespace(create=AsyncMock(), available=True, close=AsyncMock())
    brain.gemini = adapter
    try:
        with pytest.raises(AIUnavailable):
            await brain.answer_voice("Salom")
        adapter.local.create.assert_not_called()
    finally:
        await adapter.close()


async def test_unavailable_voice_ai_continues_as_original_recording():
    brain = SimpleNamespace(
        answer=AsyncMock(), answer_voice=AsyncMock(side_effect=AIUnavailable("quota"))
    )
    voice = FreeVoiceSession(brain, None, "")
    voice.speak = AsyncMock()
    await voice.respond("Savol")
    assert voice.record_only and voice.error is None
    voice.speak.assert_awaited_once()
    assert "ovoz" in voice.speak.call_args.args[0]
