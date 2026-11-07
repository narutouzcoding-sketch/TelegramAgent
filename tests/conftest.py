import pytest

from telegram_agent.brain import Brain
from telegram_agent.config import Settings
from telegram_agent.store import Store


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "agent.sqlite3")
    yield db
    db.close()


@pytest.fixture
def brain(store):
    return Brain(Settings(api_id=1, api_hash="test", owner_id=42, openai_key="test-only"), store)
