import asyncio
from datetime import timedelta
from unittest.mock import Mock

import pytest

from telegram_agent import config, sandbox
from telegram_agent.store import utc_now


class FakeBrain:
    def __init__(self, settings, store):
        self.store = store
        self.closed = False

    async def answer(self, text):
        if text == "Kontakt":
            self.store.queue_contact_call("@example", "Sinov")
        elif text == "Tez eslatma":
            self.store.add_reminder(
                "Sinov", (utc_now() + timedelta(seconds=0.01)).isoformat(), mode="message"
            )
        else:
            self.store.add_plan("15 daqiqa kitob o'qish", "sinov")
        return "Faqat sinov bazasiga saqlandi."

    async def close(self):
        self.closed = True


def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    real_db = tmp_path / "data" / "agent.sqlite3"
    real_db.write_bytes(b"existing-real-data-do-not-touch")
    return real_db


async def test_sandbox_data_is_temporary_and_real_database_is_untouched(
    brain, monkeypatch, tmp_path
):
    real_db = isolate(monkeypatch, tmp_path)
    async with sandbox.session(brain.settings, FakeBrain) as (model, store):
        await model.answer("kitob")
        folder = next((tmp_path / "data").glob("sandbox-*"))
        assert folder.exists()
        preview = store.queue_contact_call("@example", "Xabar")
        assert preview["simulated"]
        assert store.claim_contact_call() is None
    assert model.closed
    assert not folder.exists()
    assert real_db.read_bytes() == b"existing-real-data-do-not-touch"


async def test_sandbox_self_test_never_initializes_a_telegram_transport(
    brain, monkeypatch, tmp_path
):
    real_db = isolate(monkeypatch, tmp_path)
    telegram = Mock(side_effect=AssertionError("Telegram must not be initialized"))
    monkeypatch.setattr("telethon.TelegramClient", telegram)
    output = []
    assert await sandbox.self_test(
        brain.settings, write=output.append, delay=0.01, brain_factory=FakeBrain
    )
    assert any("AI + reja sinovi: PASS" in line for line in output)
    assert any("Eslatma vaqti sinovi: PASS" in line for line in output)
    telegram.assert_not_called()
    assert real_db.read_bytes() == b"existing-real-data-do-not-touch"


async def test_console_shows_simulated_calls_and_cleans_up_on_exit(brain, monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    commands = iter(["Reja", "/plans", "Kontakt", "/calls", "/exit"])
    output = []

    async def read(prompt):
        return next(commands)

    await sandbox.console(brain.settings, read=read, write=output.append, brain_factory=FakeBrain)
    assert any("[SIMULYATSIYA]" in line for line in output)
    assert not list((tmp_path / "data").glob("sandbox-*"))


async def test_reminders_arrive_while_console_is_waiting_for_input(brain, monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    fired = asyncio.Event()
    count = 0

    class FastScheduler(sandbox.Scheduler):
        async def run(self):
            await asyncio.sleep(0.03)
            await self.tick()
            await asyncio.Event().wait()

    monkeypatch.setattr(sandbox, "Scheduler", FastScheduler)

    async def read(prompt):
        nonlocal count
        count += 1
        if count == 1:
            return "Tez eslatma"
        await asyncio.wait_for(fired.wait(), 1)
        return "/exit"

    def write(line):
        if "[SINOV ESLATMA]" in line:
            fired.set()

    await sandbox.console(brain.settings, read=read, write=write, brain_factory=FakeBrain)
    assert fired.is_set()


def test_sandbox_settings_require_only_ai_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    for key in [
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "OWNER_TELEGRAM_ID",
        "OPENAI_API_KEY",
        "OPENAI_BACKUP_API_KEYS",
    ]:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("TEXT_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    settings = config.Settings.load(require_telegram=False)
    assert settings.api_id == settings.owner_id == 0
    assert settings.resolved_text_provider == "gemini"
    with pytest.raises(ValueError, match="TELEGRAM_API_ID"):
        config.Settings.load()
