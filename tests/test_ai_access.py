from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from openai import APIConnectionError, APIStatusError, RateLimitError

from telegram_agent.ai_access import AIClientPool, AIUnavailable, public_ai_error


def pool():
    access = AIClientPool.__new__(AIClientPool)
    access.clients = [
        SimpleNamespace(api_key="primary-test", close=AsyncMock()),
        SimpleNamespace(api_key="backup-test", close=AsyncMock()),
    ]
    access.current = access.clients[0]
    access.model = "gpt-realtime-2.1"
    return access


def api_error(status, code, error_type=APIStatusError):
    response = Mock(status_code=status, headers={}, request=Mock())
    return error_type("private provider body", response=response, body={"code": code})


@pytest.mark.parametrize(
    "failure", [APIConnectionError(request=Mock()), api_error(503, "server_error")]
)
async def test_transient_errors_use_authorized_backup_and_keep_it_active(failure):
    access = pool()
    operation = AsyncMock(side_effect=[failure, "success"])
    assert await access.request(operation) == "success"
    assert access.current is access.clients[1]
    operation = AsyncMock(return_value="again")
    assert await access.request(operation) == "again"
    operation.assert_awaited_once_with(access.clients[1])


@pytest.mark.parametrize(
    "code",
    [
        "insufficient_quota",
        "credit_balance_exhausted",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "rate_limit_exceeded",
    ],
)
async def test_quota_spend_and_rate_limits_never_rotate_keys(code):
    access = pool()
    failure = api_error(429, code, RateLimitError)
    operation = AsyncMock(side_effect=failure)
    with pytest.raises(RateLimitError):
        await access.request(operation)
    operation.assert_awaited_once_with(access.clients[0])
    assert access.current is access.clients[0]
    assert "private provider body" not in public_ai_error(failure)


@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_and_permission_failures_do_not_rotate(status):
    access = pool()
    operation = AsyncMock(side_effect=api_error(status, "invalid_api_key"))
    with pytest.raises(APIStatusError):
        await access.request(operation)
    assert operation.await_count == 1


async def test_websocket_server_error_can_use_backup():
    access = pool()
    socket = object()
    http = SimpleNamespace(
        ws_connect=AsyncMock(
            side_effect=[aiohttp.WSServerHandshakeError(Mock(), (), status=503), socket]
        )
    )
    assert await access.connect_realtime(http) is socket
    assert http.ws_connect.await_count == 2
    assert access.current is access.clients[1]


@pytest.mark.parametrize("status", [401, 403, 429])
async def test_websocket_auth_or_quota_failure_does_not_rotate(status):
    access = pool()
    http = SimpleNamespace(
        ws_connect=AsyncMock(side_effect=aiohttp.WSServerHandshakeError(Mock(), (), status=status))
    )
    with pytest.raises(AIUnavailable):
        await access.connect_realtime(http)
    assert http.ws_connect.await_count == 1


async def test_transcription_backup_reopens_audio_instead_of_reusing_consumed_file(brain, tmp_path):
    path = tmp_path / "voice.ogg"
    path.write_bytes(b"test-audio")
    seen = []

    async def primary(**kwargs):
        seen.append(kwargs["file"].read())
        raise APIConnectionError(request=Mock())

    async def backup(**kwargs):
        seen.append(kwargs["file"].read())
        return SimpleNamespace(text="Salom")

    brain.ai.clients = [
        SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=primary))),
        SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=backup))),
    ]
    brain.ai.current = brain.ai.clients[0]
    assert await brain.transcribe(path) == "Salom"
    assert seen == [b"test-audio", b"test-audio"]


async def test_long_retry_after_is_not_bypassed_by_switching_to_backup():
    access = pool()
    failure = api_error(503, "server_error")
    failure.response.headers["Retry-After"] = "120"
    operation = AsyncMock(side_effect=failure)
    with pytest.raises(APIStatusError):
        await access.request(operation)
    assert operation.await_count == 1


async def test_realtime_quota_event_produces_clear_billing_error_without_key_rotation(brain):
    from telegram_agent.voice import VoiceSession

    voice = VoiceSession(brain, AsyncMock(), "salom")
    original_client = brain.client
    with pytest.raises(AIUnavailable, match="krediti"):
        await voice.handle({"type": "error", "error": {"code": "insufficient_quota"}})
    assert brain.client is original_client
