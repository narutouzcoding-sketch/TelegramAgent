import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telethon.tl.types import User

from telegram_agent import owner_setup


async def test_real_username_wins_over_stale_numeric_owner_id():
    user = User(id=42, username="owner", first_name="Owner")
    client = SimpleNamespace(get_entity=AsyncMock(return_value=user), get_dialogs=AsyncMock())
    assert await owner_setup.configured_owner(client, 1, "@owner", "12345678") is user
    client.get_entity.assert_awaited_once_with("@owner")
    client.get_dialogs.assert_not_called()


async def test_placeholder_and_unknown_id_are_recoverable():
    client = SimpleNamespace(
        get_entity=AsyncMock(side_effect=ValueError("uncached ID")), get_dialogs=AsyncMock()
    )
    assert await owner_setup.configured_owner(client, 1, "@asosiy_akkauntingiz", "12345678") is None
    client.get_entity.assert_awaited_once_with(12345678)


async def test_pairing_accepts_only_private_matching_message_from_another_human(monkeypatch):
    monkeypatch.setattr(owner_setup.secrets, "token_hex", lambda _: "abcd0123abcd0123")
    client = Mock()
    task = asyncio.create_task(owner_setup.pair_owner(client, own_id=1, timeout=1))
    await asyncio.sleep(0)
    handler = client.add_event_handler.call_args.args[0]
    event = SimpleNamespace(
        is_private=True,
        out=False,
        sender_id=42,
        raw_text="O'zbekcha oddiy xabar: salom oʻrtoq",
        get_sender=AsyncMock(return_value=User(id=42, first_name="Owner")),
    )
    await handler(event)
    assert not task.done()
    event.raw_text = "/pair abcd0123abcd0123"
    event.is_private = False
    await handler(event)
    assert not task.done()
    event.is_private = True
    event.sender_id = 1
    await handler(event)
    assert not task.done()
    event.sender_id = 42
    event.get_sender.return_value = User(id=42, bot=True)
    await handler(event)
    assert not task.done()
    event.get_sender.return_value = User(id=42, first_name="Owner")
    await handler(event)
    assert (await task).id == 42
    client.remove_event_handler.assert_called_once_with(handler)


async def test_pairing_timeout_keeps_session_and_removes_temporary_handler():
    client = Mock()
    with pytest.raises(ValueError, match="sessiya saqlangan"):
        await owner_setup.pair_owner(client, own_id=1, timeout=0.01)
    client.remove_event_handler.assert_called_once()
