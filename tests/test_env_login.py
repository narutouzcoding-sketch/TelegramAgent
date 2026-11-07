from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from dotenv import dotenv_values
from telethon.errors import ApiIdInvalidError
from telethon.tl.types import User

from telegram_agent import __main__ as cli


def prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "TELEGRAM_API_ID=12345678\nTELEGRAM_API_HASH=" + "a" * 32 + "\n"
        "TELEGRAM_PHONE=+998901234567\nOWNER_TELEGRAM_USERNAME=@owner\n",
        encoding="utf-8",
    )
    client = AsyncMock(return_value=SimpleNamespace(config=SimpleNamespace(value=[])))
    client.start = AsyncMock()
    client.get_me = AsyncMock(return_value=User(id=1, first_name="Assistant"))
    client.get_entity = AsyncMock(return_value=User(id=42, first_name="Owner"))
    client.disconnect = AsyncMock()
    monkeypatch.setattr("telethon.TelegramClient", Mock(return_value=client))
    return client


async def test_manual_env_login_does_not_prompt_for_keys(monkeypatch, tmp_path):
    client = prepare(monkeypatch, tmp_path)
    prompt = Mock(return_value="HA")
    monkeypatch.setattr("builtins.input", prompt)
    monkeypatch.setattr("getpass.getpass", Mock(side_effect=AssertionError("No credential prompt")))
    await cli.setup(from_env=True)
    assert client.start.call_args.kwargs["phone"] == "+998901234567"
    assert prompt.call_count == 1
    assert "HA" in prompt.call_args.args[0]
    assert dotenv_values(tmp_path / ".env")["OWNER_TELEGRAM_ID"] == "42"
    client.disconnect.assert_awaited_once()


async def test_invalid_application_error_explains_pair_without_leaking_hash(monkeypatch, tmp_path):
    client = prepare(monkeypatch, tmp_path)
    client.start.side_effect = ApiIdInvalidError(request=None)
    with pytest.raises(ValueError, match="API_ID_INVALID") as error:
        await cli.setup(from_env=True)
    assert "a" * 32 not in str(error.value)
    client.disconnect.assert_awaited_once()


async def test_unknown_owner_id_uses_pairing_without_repeating_telegram_sign_in(
    monkeypatch, tmp_path
):
    client = prepare(monkeypatch, tmp_path)
    with (tmp_path / ".env").open("a", encoding="utf-8") as file:
        file.write("OWNER_TELEGRAM_USERNAME=@asosiy_akkauntingiz\nOWNER_TELEGRAM_ID=12345678\n")
    client.get_dialogs = AsyncMock()
    client.get_entity = AsyncMock(side_effect=ValueError("Could not find input entity"))
    pair = AsyncMock(return_value=User(id=42, first_name="Owner", username="real_owner"))
    monkeypatch.setattr(cli, "pair_owner", pair)
    monkeypatch.setattr("builtins.input", Mock(return_value="HA"))
    await cli.setup(from_env=True)
    pair.assert_awaited_once_with(client, 1)
    values = dotenv_values(tmp_path / ".env")
    assert values["OWNER_TELEGRAM_ID"] == "42"
    assert values["OWNER_TELEGRAM_USERNAME"] == "@real_owner"
    client.start.assert_awaited_once()
