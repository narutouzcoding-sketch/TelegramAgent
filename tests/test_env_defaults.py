from dataclasses import replace

from telegram_agent import config
from telegram_agent.env_defaults import ensure_env_defaults


def test_appending_new_defaults_preserves_existing_secret_bytes(tmp_path):
    path, template = tmp_path / ".env", tmp_path / ".env.example"
    original = b"# my settings\r\nOPENAI_API_KEY='keep-this-private'\r\nTEXT_MODEL=my-choice"
    path.write_bytes(original)
    template.write_text(
        "OPENAI_API_KEY=\nTEXT_MODEL=default\nOPENAI_BACKUP_API_KEYS=\nGEMINI_API_KEY=\n",
        encoding="utf-8",
    )
    assert ensure_env_defaults(path, template) == ["OPENAI_BACKUP_API_KEYS", "GEMINI_API_KEY"]
    assert path.read_bytes().startswith(original)
    assert ensure_env_defaults(path, template) == []


def test_auto_provider_prefers_gemini_when_its_key_is_present(brain):
    assert replace(brain.settings, gemini_key="test").resolved_text_provider == "gemini"
    assert brain.settings.resolved_text_provider == "openai"
    assert (
        replace(brain.settings, gemini_key="test", text_provider="openai").resolved_text_provider
        == "openai"
    )


def test_gemini_only_configuration_does_not_require_an_openai_key(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    values = {
        "TELEGRAM_API_ID": "12345678",
        "TELEGRAM_API_HASH": "a" * 32,
        "OWNER_TELEGRAM_ID": "42",
        "TEXT_PROVIDER": "gemini",
        "GEMINI_API_KEY": "test-gemini",
        "OPENAI_API_KEY": "",
        "OPENAI_BACKUP_API_KEYS": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    result = config.Settings.load()
    assert result.resolved_text_provider == "gemini"
    assert result.openai_key == ""
    assert "test-gemini" not in repr(result)
