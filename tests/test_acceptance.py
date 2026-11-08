"""20 user acceptance scenarios; isolated databases, no real Telegram calls or paid APIs."""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from telegram_agent.contact_conversation import ContactConversation
from telegram_agent.panel import PanelControl, create_panel
from telegram_agent.store import utc_now


@pytest.fixture
async def ui(brain, tmp_path):
    control = PanelControl(brain.settings, root=tmp_path)
    client = TestClient(TestServer(create_panel(control, "qa-password-2026")))
    await client.start_server()
    response = await client.post("/api/login", json={"password": "qa-password-2026"})
    headers = {"X-CSRF-Token": (await response.json())["csrf"]}
    yield control, client, headers
    await client.close()


async def test_uat_01_wrong_password_then_login_and_logout(ui):
    _, client, headers = ui
    assert (await client.post("/api/login", json={"password": "wrong"})).status == 401
    assert (await (await client.get("/api/session")).json())["authenticated"]
    assert (await client.post("/api/logout", json={}, headers=headers)).status == 200
    assert (await client.get("/api/state")).status == 401


async def test_uat_02_private_files_never_public(ui):
    _, client, headers = ui
    await client.post("/api/logout", json={}, headers=headers)
    for path in ("/api/state", "/.env", "/data/assistant.session", "/api/audio/unknown"):
        assert (await client.get(path)).status in {401, 404}


async def test_uat_03_cross_origin_and_csrf_cannot_write(ui):
    control, client, headers = ui
    assert (await client.post("/api/plan", json={"title": "wrong"})).status == 403
    assert (
        await client.post(
            "/api/plan",
            json={"title": "wrong"},
            headers=headers | {"Origin": "https://example.invalid"},
        )
    ).status == 403
    assert not control.store.list_plans()


async def test_uat_04_nonobject_json_is_client_error_not_crash(ui):
    _, client, headers = ui
    for value in ([], None, "hello", 123):
        for action in ("plan", "chat", "contact", "login"):
            response = await client.post(
                "/api/" + action,
                data=json.dumps(value),
                headers=headers | {"Content-Type": "application/json"},
            )
            assert response.status == 400, (action, value, response.status)


async def test_uat_05_unicode_plan_create_edit_and_finish(ui):
    control, client, headers = ui
    response = await client.post("/api/plan", json={"title": "Kitob o‘qish 📚"}, headers=headers)
    row = await response.json()
    assert row["saved"]
    response = await client.post(
        "/api/plan",
        json={"id": row["id"], "title": "Yangilandi", "details": "<script>test</script>"},
        headers=headers,
    )
    assert response.status == 200
    assert control.store.list_plans()[0]["details"] == "<script>test</script>"
    await client.post("/api/complete-plan", json={"id": row["id"]}, headers=headers)
    assert not control.store.list_plans()


async def test_uat_06_invalid_dates_are_rejected_without_server_error(ui):
    control, client, headers = ui
    for value in (None, [], 12, "yesterday", (utc_now() - timedelta(days=1)).isoformat()):
        response = await client.post(
            "/api/reminder",
            json={"title": "Suv", "due_at": value, "repeat": "none", "mode": "message"},
            headers=headers,
        )
        assert response.status == 400, (value, response.status)
    assert not control.store.list_reminders()


def test_uat_07_tashkent_time_and_repeating_delivery(store):
    from telegram_agent.store import parse_due

    local = (
        (utc_now() + timedelta(days=2))
        .astimezone(__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
        .replace(microsecond=0)
    )
    due = parse_due(local.replace(tzinfo=None).isoformat(), store.timezone)
    assert due == local
    row = store.add_reminder("Suv", due.isoformat(), "daily", "message")
    claimed = store.claim_due(now=due + timedelta(seconds=1))
    assert claimed["id"] == row["id"]
    store.finish(claimed, now=due + timedelta(seconds=2))
    assert store.list_reminders()[0]["state"] == "pending"
    assert store.claim_due(now=due + timedelta(hours=1)) is None


def test_uat_08_cancelled_reminder_cannot_be_resurrected(store):
    due = utc_now() + timedelta(seconds=5)
    row = store.add_reminder("Bekor", due.isoformat())
    claimed = store.claim_due(now=due + timedelta(seconds=1))
    store.cancel_reminder(row["id"])
    store.finish(claimed, error="offline")
    assert store.claim_due(now=due + timedelta(days=1)) is None


async def test_uat_09_empty_contact_and_duplicate_contact(ui):
    control, client, headers = ui
    for reference in (None, "", "  "):
        assert (
            await client.post(
                "/api/contact", json={"name": "Do‘st", "reference": reference}, headers=headers
            )
        ).status == 400
    for name in ("Birinchi", "Yangilangan"):
        assert (
            await client.post(
                "/api/contact", json={"name": name, "reference": "@qa_example"}, headers=headers
            )
        ).status == 200
    assert len(control.store.list_contacts()) == 1
    assert control.store.list_contacts()[0]["name"] == "Yangilangan"


async def test_uat_10_permission_revoke_does_not_need_telegram(ui):
    control, client, headers = ui
    control.store.save_contact("Do‘st", "@qa_example")
    row = control.store.list_contacts()[0]
    control.store.set_contact_permission(row["id"], 77, True)
    response = await client.post(
        "/api/verify-contact", json={"id": row["id"], "allow": False}, headers=headers
    )
    assert response.status == 200 and not control.store.approved_contact_ids()
    assert not control.store.list_contact_calls()


def test_uat_11_invalid_call_options_never_queue(store):
    for options in (
        {"language": "xx"},
        {"mode": "bad"},
        {"duration_seconds": 0},
        {"max_turns": 20},
    ):
        with pytest.raises(ValueError):
            store.queue_contact_call("@qa_example", "Savol?", **options)
    assert not store.list_contact_calls()


def test_uat_12_double_submit_is_one_call(store):
    first = store.queue_contact_call("@qa_example", "Savol?", mode="record")
    second = store.queue_contact_call("@qa_example", "Savol?", mode="record")
    assert first["id"] == second["id"] and second["duplicate_suppressed"]
    assert len(store.list_contact_calls()) == 1


def test_uat_13_restart_never_redials_interrupted_call(store):
    store.queue_contact_call("@qa_example", "Savol?")
    store.claim_contact_call()
    store.recover_contact_calls()
    assert store.claim_contact_call() is None
    assert store.list_contact_calls()[0]["state"] == "interrupted"


def test_uat_14_recording_busy_retry_is_rejected(store):
    for state in ("capturing", "sending"):
        rid = ("a" if state == "capturing" else "b") * 32
        store.start_recording(rid, 42, "QA", None)
        store.db.execute("UPDATE recordings SET state=? WHERE id=?", (state, rid))
        store.db.commit()
        with pytest.raises(ValueError):
            store.retry_recording(rid)
        assert next(r for r in store.list_recordings() if r["id"] == rid)["state"] == state


async def test_uat_15_recording_auth_and_recovery(ui):
    control, client, headers = ui
    rid = "c" * 32
    control.store.start_recording(rid, 42, "QA", None)
    control.store.recover_recordings()
    assert control.store.list_recordings()[0]["state"] == "captured"
    assert (await client.get(f"/api/recordings/{rid}/audio")).status == 404
    await client.post("/api/logout", json={}, headers=headers)
    assert (await client.get(f"/api/recordings/{rid}/audio")).status == 401


async def test_uat_16_quota_fallback_never_uses_paid_voice(brain):
    from telegram_agent.ai_access import AIUnavailable
    from telegram_agent.free_voice import FreeVoiceSession

    fake = SimpleNamespace(
        answer=AsyncMock(), answer_voice=AsyncMock(side_effect=AIUnavailable("quota"))
    )
    voice = FreeVoiceSession(fake, None, "")
    voice.speak = AsyncMock()
    await voice.respond("Savol")
    assert voice.record_only and not voice.error
    fake.answer.assert_not_called()


def test_uat_17_original_audio_survives_busy_asr(brain):
    from telegram_agent.app import AgentApp

    app = AgentApp.__new__(AgentApp)
    app.settings = brain.settings
    app.active_recording = SimpleNamespace(peer_id=42, write=lambda *args: captured.append(args))
    app.voice = SimpleNamespace(accept_pcm48=lambda frame: None)
    captured = []
    app.receive_audio(
        SimpleNamespace(chat_id=42, frames=[SimpleNamespace(frame=b"\x01\x00" * 480)])
    )
    assert captured == [("incoming", b"\x01\x00" * 480)]


async def test_uat_18_unexpected_model_json_finishes_safely():
    for raw in ("[]", "null", '"text"', "12"):
        fake = SimpleNamespace(free_speech=SimpleNamespace(), use_native_asr=True)
        task = ContactConversation(
            fake, "Owner", {"message": "Savol?", "mode": "conversation", "language": "uz"}
        )
        task.generate = AsyncMock(return_value=raw)
        assert "Rahmat" in await task.answer("Javob")
        assert task.finished


async def test_uat_19_transport_disconnect_visible_to_user(ui):
    control, _, _ = ui
    ready = asyncio.Event()
    ready.set()
    control.agent = SimpleNamespace(
        ready=ready,
        settings=control.settings,
        brain=SimpleNamespace(),
        owner_name="QA",
        call_lock=asyncio.Lock(),
        telegram=SimpleNamespace(is_connected=lambda: False),
    )
    control.task = asyncio.create_task(asyncio.Event().wait())
    assert control.state()["agent"]["phase"] == "reconnecting"
    assert not control.state()["agent"]["running"]


async def test_uat_20_failed_chat_does_not_block_next_message(ui):
    from telegram_agent.ai_access import AIUnavailable

    control, client, headers = ui
    control.idle_brain = SimpleNamespace(
        answer=AsyncMock(side_effect=[AIUnavailable("quota"), "Salom"]), close=AsyncMock()
    )
    assert (
        await client.post("/api/chat", json={"text": "Birinchi"}, headers=headers)
    ).status == 502
    response = await client.post("/api/chat", json={"text": "Ikkinchi"}, headers=headers)
    assert response.status == 200 and (await response.json())["reply"] == "Salom"
    assert control.chat_waiters == 0
