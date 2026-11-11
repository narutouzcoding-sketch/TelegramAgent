from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.tl.types import User

from telegram_agent.app import AgentApp
from telegram_agent.contact_calls import RecipientResolver


@pytest.mark.parametrize(
    "query", ["Sevinch", "sevinch kursdoshga", "SEVINCH KURSDOSH", "synthetic_sevinch"]
)
def test_stylized_names_and_uzbek_case_suffixes_match(store, query):
    store.save_contact("𝑺𝒆𝒗𝒊𝒏𝒄𝒉 kursdosh", "@synthetic_sevinch")
    store.save_contact("Other", "@other")
    assert [c["reference"] for c in store.search_contacts(query)] == ["@synthetic_sevinch"]


def test_phone_punctuation_does_not_hide_contact(store):
    store.save_contact("Friend", "+998901234567")
    assert store.search_contacts("+998 (90) 123-45-67")[0]["name"] == "Friend"


def test_numeric_name_can_match_without_a_phone_number(store):
    store.save_contact("Guruh 2026", "@synthetic_group")
    assert store.search_contacts("2026")[0]["name"] == "Guruh 2026"


async def test_name_search_resolves_only_a_unique_saved_recipient(store):
    store.save_contact("𝑺𝒆𝒗𝒊𝒏𝒄𝒉 kursdosh", "@synthetic_sevinch")
    client = SimpleNamespace(get_entity=AsyncMock(return_value=User(id=77)))
    resolver = RecipientResolver(client, store, own_id=1)
    assert (await resolver.resolve("sevinch kursdoshga")).id == 77
    client.get_entity.assert_awaited_once_with("@synthetic_sevinch")
    client.get_entity.reset_mock()
    store.save_contact("Sevinch kursdosh 2", "@synthetic_other")
    with pytest.raises(ValueError, match="bir nechta"):
        await resolver.resolve("sevinch kursdoshga")
    client.get_entity.assert_not_awaited()


async def test_missing_username_is_a_useful_validation_error(store):
    from telethon import errors

    client = SimpleNamespace(
        get_entity=AsyncMock(side_effect=errors.UsernameNotOccupiedError(request=None))
    )
    with pytest.raises(ValueError, match="username topilmadi"):
        await RecipientResolver(client, store, own_id=1).resolve("@synthetic_missing")


async def test_selected_contact_identity_change_cannot_approve_or_queue_another_person(brain):
    agent = AgentApp.__new__(AgentApp)
    agent.store, agent.settings, agent.brain = brain.store, brain.settings, brain

    async def action(operation):
        return await operation()

    agent.policy = SimpleNamespace(action=action)
    agent.recipient_resolver = SimpleNamespace(resolve=AsyncMock(return_value=User(id=88)))
    with pytest.raises(ValueError, match="o'zgargan"):
        await agent.queue_requested_call("@synthetic_changed", "QA", expected_recipient_id=77)
    assert not brain.store.approved_contact_ids()
    assert not brain.store.list_contact_calls()
