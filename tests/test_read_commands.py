from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_agent.read_commands import read_reply


@pytest.mark.parametrize("text", ["Rejalarim", "Rejalarni ko‘rsat!", "/plans"])
async def test_read_requests_work_when_cloud_is_unavailable(brain, text):
    brain.store.add_plan("Dars", "10 bet")
    cloud = AsyncMock(side_effect=RuntimeError("No cloud request expected"))
    brain.gemini = SimpleNamespace(create=cloud)
    result = await brain.answer(text)
    assert "Dars" in result and "#1" in result
    cloud.assert_not_awaited()
    assert brain.store.context() == []


def test_saved_state_is_read_fresh_and_action_requests_are_not_intercepted(store):
    assert read_reply(store, "Rejalarim") == "Ochiq reja yo'q."
    row = store.add_plan("Yangi reja", "")
    assert "Yangi reja" in read_reply(store, "Rejalarim")
    assert read_reply(store, "Rejalarimga yangi vazifa qo'sh") is None
    store.complete_plan(row["id"])
    assert read_reply(store, "Rejalarim") == "Ochiq reja yo'q."


async def test_contact_lookup_uses_local_data_without_cloud(brain):
    brain.store.save_contact("Ali", "@ali_test")
    brain.store.save_contact("Vali", "@vali_test")
    cloud = AsyncMock(side_effect=RuntimeError("No cloud request expected"))
    brain.gemini = SimpleNamespace(create=cloud)
    reply = await brain.answer("/contacts Ali")
    assert "@ali_test" in reply
    cloud.assert_not_awaited()
    assert brain.store.context() == []
