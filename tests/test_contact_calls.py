import asyncio
import json
import shutil
import wave
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.tl.types import Chat, User

from telegram_agent.app import AgentApp
from telegram_agent.contact_calls import RecipientResolver, decode_pcm, play_relay
from telegram_agent.store import utc_now
from telegram_agent.telegram_policy import TelegramPolicy


def test_contact_call_tool_queues_once_and_never_claims_delivery(brain):
    brain.settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
        record_calls=False,
    )
    arguments = json.dumps({"target": "@friend", "message": "Soat 18 da uchrashamiz."})
    first = brain.execute_tool("queue_contact_call", arguments, "relay-1")
    assert brain.execute_tool("queue_contact_call", arguments, "relay-1") == first
    assert first["result"]["status"] == "queued"
    assert brain.execute_tool("queue_contact_call", arguments, "relay-retried")["result"][
        "duplicate_suppressed"
    ]
    assert len(brain.store.list_contact_calls()) == 1
    assert brain.store.list_contact_calls()[0]["state"] == "queued"


def test_job_cancel_and_restart_do_not_redial(store):
    job = store.queue_contact_call("@friend", "Salom")
    assert store.cancel_contact_call(job["id"])["cancelled"]
    assert store.claim_contact_call() is None
    store.queue_contact_call("@other", "Salom")
    assert store.claim_contact_call()["target"] == "@other"
    store.recover_contact_calls()
    assert store.claim_contact_call() is None
    assert store.list_contact_calls()[0]["state"] == "interrupted"


def test_stale_queued_calls_are_not_started_on_restart(store):
    job = store.queue_contact_call("@friend", "Salom")
    with store.db:
        store.db.execute(
            "UPDATE outbound_calls SET created=? WHERE id=?",
            ((utc_now() - timedelta(minutes=11)).isoformat(), job["id"]),
        )
    store.recover_contact_calls()
    assert store.claim_contact_call() is None


async def test_shared_contact_name_resolves_to_exact_telegram_user(store):
    store.save_contact("Ali", "+998901234567")
    person = User(id=77, first_name="Ali")
    client = AsyncMock(
        return_value=SimpleNamespace(users=[person], peer=SimpleNamespace(user_id=77))
    )
    resolver = RecipientResolver(client, store, own_id=1)
    assert (await resolver.resolve("ali")).id == 77
    assert client.call_args.args[0].phone == "998901234567"


async def test_ambiguous_names_do_not_call_or_guess(store):
    store.save_contact("Ali", "+998901234567")
    store.save_contact("Ali", "+998901234568")
    client = AsyncMock()
    with pytest.raises(ValueError, match="bir nechta"):
        await RecipientResolver(client, store, own_id=1).resolve("Ali")
    client.assert_not_called()


@pytest.mark.parametrize(
    "entity",
    [
        User(id=1),
        User(id=77, bot=True),
        Chat(id=77, title="Group", photo=None, participants_count=0, date=None, version=1),
    ],
)
async def test_bots_groups_and_assistant_account_cannot_be_recipients(store, entity):
    client = SimpleNamespace(get_entity=AsyncMock(return_value=entity))
    with pytest.raises(ValueError):
        await RecipientResolver(client, store, own_id=1).resolve("@target")


async def test_relay_only_sends_after_answer_and_can_disable_recording(brain):
    brain.settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
        record_calls=False,
    )
    calls = SimpleNamespace(play=AsyncMock(), send_frame=AsyncMock(), leave_call=AsyncMock())
    app = SimpleNamespace(
        call_lock=asyncio.Lock(),
        calls=calls,
        settings=brain.settings,
        policy=TelegramPolicy(brain.settings, brain.store),
        call_task=None,
        relay_target=None,
        relay_ended=None,
    )
    await play_relay(app, User(id=77, first_name="Ali"), bytes(960))
    calls.play.assert_awaited_once()
    calls.send_frame.assert_awaited_once()
    calls.leave_call.assert_awaited_once_with(77)
    assert app.relay_target is None
    assert not app.call_lock.locked()


async def test_recipient_hangup_is_not_marked_as_complete_message(brain):
    brain.settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
        record_calls=False,
    )
    calls = SimpleNamespace(play=AsyncMock(), send_frame=AsyncMock(), leave_call=AsyncMock())
    app = SimpleNamespace(
        call_lock=asyncio.Lock(),
        calls=calls,
        settings=brain.settings,
        policy=TelegramPolicy(brain.settings, brain.store),
        call_task=None,
        relay_target=None,
        relay_ended=None,
    )

    async def answer_then_leave(*args, **kwargs):
        app.relay_ended.set()

    calls.play.side_effect = answer_then_leave
    with pytest.raises(ValueError, match="oldin"):
        await play_relay(app, User(id=77, first_name="Ali"), bytes(960))
    calls.send_frame.assert_not_called()
    calls.leave_call.assert_awaited_once_with(77)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
async def test_real_ffmpeg_converts_local_audio_to_telegram_pcm(tmp_path):
    path = tmp_path / "test.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(bytes(2400))
    audio = await decode_pcm(path)
    assert len(audio) == 4800


async def test_explicit_call_command_is_restricted_to_owner(brain):
    app = AgentApp.__new__(AgentApp)
    app.settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77,),
        record_calls=False,
    )
    app.store = brain.store
    app.send_text = AsyncMock()
    app.queue_requested_call = AsyncMock(
        side_effect=lambda target, message, **options: brain.store.queue_contact_call(
            target, message, **options
        )
    )
    event = SimpleNamespace(
        is_private=True, sender_id=99, out=False, raw_text="/callto @friend | Soat 18 da kel."
    )
    await app.on_message(event)
    assert not app.store.list_contact_calls()
    event.sender_id = brain.settings.owner_id
    await app.on_message(event)
    assert app.store.list_contact_calls()[0]["message"] == "Soat 18 da kel."


async def test_cancelling_one_job_does_not_stop_queue(store, monkeypatch):
    from telegram_agent import contact_calls

    started = asyncio.Queue()

    async def job(app, row):
        await started.put(row["id"])
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            app.store.finish_contact_call(row["id"], "cancelled", "cancelled")
            raise

    monkeypatch.setattr(contact_calls, "execute_job", job)
    app = SimpleNamespace(
        store=store,
        settings=SimpleNamespace(enable_contact_calls=True, allowed_call_user_ids=(77,)),
        call_lock=asyncio.Lock(),
        spawn=asyncio.create_task,
        contact_job_task=None,
        contact_job_id=None,
    )
    first = store.queue_contact_call("@friend", "Birinchi")
    second = store.queue_contact_call("@other", "Ikkinchi")
    worker = asyncio.create_task(contact_calls.run_queue(app))
    try:
        assert await asyncio.wait_for(started.get(), 1) == first["id"]
        app.contact_job_task.cancel()
        assert await asyncio.wait_for(started.get(), 1) == second["id"]
        assert not worker.done()
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
