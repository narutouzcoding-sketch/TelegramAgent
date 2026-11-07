from unittest.mock import Mock

import pytest

from telegram_agent.setup_inputs import international_phone, prompt_phone, telegram_credentials


def test_telegram_application_credentials_are_distinct_from_other_keys():
    assert telegram_credentials("12345678", "a" * 32) == (12345678, "a" * 32)
    for identifier, secret in [
        ("not-a-number", "a" * 32),
        ("0", "a" * 32),
        ("12345678", "sk-test-only-key"),
        ("12345678", "a" * 31),
        ("12345678", '"' + "a" * 32 + '"'),
    ]:
        with pytest.raises(ValueError) as error:
            telegram_credentials(identifier, secret)
        assert secret not in str(error.value)


def test_phone_requires_explicit_country_code():
    assert international_phone("+998 (90) 123-45-67") == "+998901234567"
    assert international_phone("+1 202 555 0123") == "+12025550123"
    for value in ["901234567", "", "+0123456789", "+1234567890123456", "+998abc"]:
        with pytest.raises(ValueError):
            international_phone(value)


def test_phone_prompt_retries_without_restarting_setup(monkeypatch, capsys):
    prompt = Mock(side_effect=["901234567", "+998901234567"])
    monkeypatch.setattr("builtins.input", prompt)
    assert prompt_phone() == "+998901234567"
    assert prompt.call_count == 2
    assert "mamlakat kodi" in capsys.readouterr().out
