import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from openai import RateLimitError
from openai.types.chat import ChatCompletion

from telegram_agent.ai_access import AIProviderUnavailable, AIUnavailable
from telegram_agent.brain import Brain
from telegram_agent.gemini_text import GeminiText


def completion(message, finish_reason="stop"):
    return ChatCompletion.model_validate(
        {
            "id": "gemini-test",
            "object": "chat.completion",
            "created": 1,
            "model": "gemini-3.1-flash-lite",
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        }
    )


async def test_gemini_tool_round_trip_preserves_google_thought_signature(brain):
    signature = {"google": {"thought_signature": "test-signature"}}
    first = completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "gemini-call-1",
                    "type": "function",
                    "extra_content": signature,
                    "function": {
                        "name": "add_plan",
                        "arguments": '{"title":"Dars","details":"30 daqiqa"}',
                    },
                }
            ],
        },
        "tool_calls",
    )
    last = completion({"role": "assistant", "content": "Reja #1 saqlandi."})
    create = AsyncMock(side_effect=[first, last])
    brain.gemini = SimpleNamespace(create=create)
    assert await brain.answer("Dars qilishni rejamga qo'sh") == "Reja #1 saqlandi."
    assert brain.store.list_plans()[0]["title"] == "Dars"
    messages = create.call_args.args[1]
    assert messages[-2]["tool_calls"][0]["extra_content"] == signature
    assert json.loads(messages[-1]["content"])["ok"]


async def test_truncated_gemini_tool_output_does_not_execute_side_effects(brain):
    result = completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "incomplete",
                    "type": "function",
                    "function": {
                        "name": "add_plan",
                        "arguments": '{"title":"Dars","details":"30 daqiqa"}',
                    },
                }
            ],
        },
        "length",
    )
    brain.gemini = SimpleNamespace(create=AsyncMock(return_value=result))
    assert "token chegarasiga" in await brain.answer("Reja qo'sh")
    assert brain.store.list_plans() == []


async def test_gemini_uses_google_endpoint_and_budgeted_chat_api(brain):
    settings = replace(brain.settings, text_provider="gemini", gemini_key="gemini-test-only")
    adapter = GeminiText(settings)
    assert (
        str(adapter.client.base_url) == "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    await adapter.client.close()
    create = AsyncMock(return_value=completion({"role": "assistant", "content": "Salom"}))
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    from telegram_agent.brain import TOOLS

    await adapter.create("system", [{"role": "user", "content": "Salom"}], TOOLS)
    args = create.call_args.kwargs
    assert args["model"] == "gemini-3.1-flash-lite"
    assert args["reasoning_effort"] == "minimal"
    assert args["max_tokens"] == 1200
    assert args["tools"][0]["function"]["name"] == "queue_contact_call"


async def test_gemini_quota_failure_is_clear_and_does_not_rotate_accounts(brain):
    adapter = GeminiText(replace(brain.settings, gemini_key="gemini-test-only"))
    await adapter.client.close()
    failure = RateLimitError(
        "private-body-with-secret",
        response=Mock(status_code=429, headers={}, request=Mock()),
        body={"code": "RESOURCE_EXHAUSTED"},
    )
    create = AsyncMock(side_effect=failure)
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    with pytest.raises(AIUnavailable, match="Gemini API kvotasi") as error:
        await adapter.create("system", [], [])
    assert "private-body-with-secret" not in str(error.value)
    assert create.await_count == 1


async def test_text_fallback_skips_gemini_cooldown_across_restarts_and_recovers(brain):
    from datetime import UTC, datetime, timedelta

    cfg = replace(
        brain.settings,
        gemini_key="gemini-test-only",
        groq_key="groq-test-only",
        text_fallbacks=("groq",),
        local_fallback_enabled=False,
    )
    primary_error = RateLimitError(
        "test limit",
        response=Mock(status_code=429, headers={"retry-after": "120"}, request=Mock()),
        body={},
    )
    reply = completion({"role": "assistant", "content": "Sinov"})
    reply.usage = SimpleNamespace(prompt_tokens=20, completion_tokens=5)
    worker = Brain(cfg, brain.store)
    restarted = Brain(cfg, brain.store)
    try:
        primary = AsyncMock(side_effect=primary_error)
        groq = AsyncMock(return_value=reply)
        worker.gemini.client.chat.completions.create = primary
        worker.text_backups["groq"].client.chat.completions.create = groq
        assert await worker.answer("Salom") == "Sinov"
        assert primary.await_count == 1
        assert worker.gemini.cooldown_remaining() > 110
        assert groq.call_args.kwargs["max_completion_tokens"] == cfg.text_max_output_tokens
        assert groq.call_args.kwargs["model"] == "openai/gpt-oss-20b"

        recover = AsyncMock(return_value=reply)
        restarted.gemini.client.chat.completions.create = recover
        restarted.text_backups["groq"].client.chat.completions.create = groq
        assert await restarted.answer("Yana salom") == "Sinov"
        recover.assert_not_awaited()
        usage = restarted.gemini.ledger.summary()["providers"]
        assert usage["groq"]["requests"] == 2
        assert usage["groq"]["input_tokens"] == 40
        assert usage["gemini"]["unknown_usage"] == 1
        assert "openai" not in restarted.text_backups

        wait_until = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
        brain.store.set_telegram_state("groq_cooldown_until", wait_until)
        with pytest.raises(AIProviderUnavailable, match="AI xizmatlari vaqtincha band"):
            await restarted.answer("Band bo'lgan paytdagi savol")
        assert groq.await_count == 2
        recover.assert_not_awaited()

        brain.store.set_telegram_state("gemini_cooldown_until", datetime.now(UTC).isoformat())
        assert await restarted.answer("Tiklandimi?") == "Sinov"
        recover.assert_awaited_once()
    finally:
        await worker.close()
        await restarted.close()


async def test_text_fallback_keeps_tool_conversation_on_its_initial_provider(brain):
    read_plans = completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "gemini-plans",
                    "type": "function",
                    "function": {"name": "list_plans", "arguments": "{}"},
                }
            ],
        },
        "tool_calls",
    )
    failure = AIProviderUnavailable("Gemini kutish vaqti")
    brain.gemini = SimpleNamespace(create=AsyncMock(side_effect=[read_plans, failure]))
    groq = AsyncMock()
    brain.text_backups = {"groq": SimpleNamespace(create=groq)}
    with pytest.raises(AIProviderUnavailable, match="Gemini kutish vaqti"):
        await brain.answer("Rejamni ko'rib bugun qaysi ishni boshlashni tavsiya qil")
    groq.assert_not_awaited()


async def test_gemini_only_mode_rejects_live_call_before_dialling(brain):
    from telegram_agent.app import AgentApp

    app = AgentApp.__new__(AgentApp)
    app.settings = replace(
        brain.settings,
        openai_key="",
        text_provider="gemini",
        gemini_key="test",
        enable_voice_calls=True,
    )
    app.calls = SimpleNamespace(play=AsyncMock())
    with pytest.raises(AIUnavailable, match="OPENAI_API_KEY"):
        await app.conversation("hello")
    app.calls.play.assert_not_called()
