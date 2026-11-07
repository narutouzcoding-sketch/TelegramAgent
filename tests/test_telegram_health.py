from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telethon.tl.types import User

from telegram_agent.telegram_health import TelegramAccountFrozen, ensure_telegram_account


def account_client(user, values):
    entries = [
        SimpleNamespace(key=key, value=SimpleNamespace(value=value))
        for key, value in values.items()
    ]
    client = AsyncMock(return_value=SimpleNamespace(config=SimpleNamespace(value=entries)))
    client.get_me.return_value = user
    return client


async def test_readable_account_with_freeze_flag_is_not_healthy():
    client = account_client(
        User(id=1, first_name="Assistant", deleted=False),
        {
            "freeze_since_date": 1735689600,
            "freeze_until_date": 1735776000,
            "freeze_appeal_url": "https://t.me/SpamBot?start=private-test-value",
        },
    )
    with pytest.raises(TelegramAccountFrozen) as error:
        await ensure_telegram_account(client, "Asia/Tashkent")
    assert "2025-01-02 05:00" in str(error.value)
    assert "private-test-value" not in str(error.value)
    client.send_message.assert_not_called()


async def test_no_freeze_flags_does_not_treat_generic_user_restrictions_as_a_ban():
    user = User(id=1, first_name="Assistant", restricted=True)
    client = account_client(user, {})
    assert await ensure_telegram_account(client) is user


@pytest.mark.parametrize("user", [None, User(id=1, deleted=True)])
async def test_missing_or_deleted_account_is_not_allowed_to_start(user):
    with pytest.raises(ValueError):
        await ensure_telegram_account(account_client(user, {}))


async def test_frozen_agent_stops_before_call_library_or_message_workers_start(brain, monkeypatch):
    from telegram_agent.app import AgentApp

    app = AgentApp.__new__(AgentApp)
    app.settings = brain.settings
    from telegram_agent.telegram_policy import TelegramPolicy

    app.policy = TelegramPolicy(brain.settings, brain.store)
    app.telegram = account_client(User(id=1), {"freeze_since_date": 1735689600})
    app.telegram.is_user_authorized.return_value = True
    factory = Mock()
    monkeypatch.setattr("pytgcalls.PyTgCalls", factory)
    with pytest.raises(TelegramAccountFrozen):
        await app._run()
    factory.assert_not_called()
    app.telegram.get_input_entity.assert_not_called()
    app.telegram.send_message.assert_not_called()
