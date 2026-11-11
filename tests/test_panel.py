import asyncio
import hashlib
import re
import sqlite3
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from telegram_agent.panel import PanelControl, create_panel
from telegram_agent.store import Store, utc_now


@pytest.fixture
async def panel(brain, tmp_path):
    control = PanelControl(brain.settings, root=tmp_path)
    client = TestClient(TestServer(create_panel(control, "test-panel-password")))
    await client.start_server()
    yield control, client
    await client.close()


async def login(client):
    response = await client.post("/api/login", json={"password": "test-panel-password"})
    assert response.status == 200
    return {"X-CSRF-Token": (await response.json())["csrf"]}


async def test_login_page_scripts_load_before_authentication(panel):
    _, client = panel
    response = await client.get("/")
    scripts = re.findall(r'<script src="([^"]+)"', await response.text())
    assert "/call-intent.js" in scripts
    for path in scripts:
        asset = await client.get(path)
        assert asset.status == 200, path
        assert "javascript" in asset.content_type


async def test_phone_apk_download_is_public_and_serves_only_the_built_apk(panel):
    control, client = panel
    assert (await client.get("/TelegramAgent.apk")).status == 404
    folder = control.root / "data" / "downloads"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "TelegramAgent.apk").write_bytes(b"QA-APK")
    response = await client.get("/TelegramAgent.apk")
    assert response.status == 200
    assert await response.read() == b"QA-APK"
    assert response.content_type == "application/vnd.android.package-archive"


@pytest.mark.parametrize(
    "action,payload",
    [
        ("plan", {"title": "QA retry"}),
        (
            "reminder",
            {
                "title": "QA retry",
                "due_at": "2030-01-15T10:00",
                "repeat": "none",
                "mode": "message",
            },
        ),
        ("library-note", {"title": "QA retry", "body": "Local only"}),
    ],
)
async def test_creation_retry_returns_original_receipt_without_duplicate(panel, action, payload):
    control, client = panel
    headers = await login(client)
    payload = {**payload, "request_id": "network-retry-test-12345"}
    first = await client.post("/api/" + action, json=payload, headers=headers)
    assert first.status == 200
    receipt = await first.json()
    retry = await client.post("/api/" + action, json=payload, headers=headers)
    assert retry.status == 200 and await retry.json() == receipt
    conflict = await client.post(
        "/api/" + action, json={**payload, "title": "Different"}, headers=headers
    )
    assert conflict.status == 400
    table = {"plan": "plans", "reminder": "reminders", "library-note": "documents"}[action]
    assert control.store.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 1


async def test_concurrent_completed_call_retry_queues_once_and_receipt_survives_agent_stop(panel):
    control, client = panel
    await connected(control)
    headers = await login(client)

    async def queue(target, message, **options):
        await asyncio.sleep(0.03)
        row = control.store.queue_contact_call(target, message, **options)
        control.store.finish_contact_call(row["id"], "text_sent", "QA only")
        return row

    control.agent.queue_requested_call = AsyncMock(side_effect=queue)
    payload = {
        "target": "@synthetic",
        "message": "QA",
        "mode": "text",
        "request_id": "concurrent-request-12345",
    }
    responses = await asyncio.gather(
        *(client.post("/api/call", json=payload, headers=headers) for _ in range(2))
    )
    assert all(response.status == 200 for response in responses)
    assert (await responses[0].json())["id"] == (await responses[1].json())["id"]
    control.agent.queue_requested_call.assert_awaited_once()
    await control.stop()
    assert (await client.post("/api/call", json=payload, headers=headers)).status == 200
    assert len(control.store.list_contact_calls()) == 1


def test_old_active_task_cannot_disappear_behind_twenty_completed_tasks(store):
    active = store.queue_contact_call("@synthetic_old", "QA", "2030-01-15T10:00", mode="text")
    for index in range(22):
        row = store.queue_contact_call("@synthetic_" + str(index), "QA", mode="text")
        store.finish_contact_call(row["id"], "text_sent", "QA only")
    assert active["id"] not in {row["id"] for row in store.list_contact_calls()}
    assert active["id"] in {row["id"] for row in store.list_contact_calls(include_active=True)}


async def test_retried_chat_does_not_spend_ai_or_repeat_tools(panel):
    control, client = panel
    await connected(control)
    headers = await login(client)

    async def answer(text):
        await asyncio.sleep(0.02)
        control.store.add_plan("QA one AI side effect")
        return "QA reply"

    control.agent.brain.answer = AsyncMock(side_effect=answer)
    payload = {"text": "QA message", "request_id": "chat-network-retry-12345"}
    responses = await asyncio.gather(
        *(client.post("/api/chat", json=payload, headers=headers) for _ in range(2))
    )
    assert all(response.status == 200 for response in responses)
    receipts = [await response.json() for response in responses]
    assert all(receipt["reply"] == "QA reply" for receipt in receipts)
    control.agent.brain.answer.assert_awaited_once()
    assert len(control.store.list_plans()) == 1
    assert (
        await client.post("/api/chat", json={**payload, "text": "Changed"}, headers=headers)
    ).status == 400


async def test_panel_separates_connection_from_a_telegram_wait_or_restriction(panel):
    control, client = panel
    await connected(control)
    await login(client)
    control.store.set_telegram_state("pause_until", (utc_now() + timedelta(minutes=5)).isoformat())
    data = await (await client.get("/api/state")).json()
    assert data["agent"]["running"] and data["agent"]["telegram_paused"]
    assert data["agent"]["telegram_pause_until"]
    control.store.set_telegram_state("restriction_latch", "PeerFloodError")
    data = await (await client.get("/api/state")).json()
    assert data["agent"]["telegram_restricted"]
    assert data["agent"]["telegram_restriction_reason"] == "PeerFloodError"


async def connected(control):
    settings = replace(control.settings, enable_voice_calls=True)
    ready = asyncio.Event()
    ready.set()
    control.agent = SimpleNamespace(
        ready=ready,
        settings=settings,
        owner_name="Test Owner",
        call_lock=asyncio.Lock(),
        brain=SimpleNamespace(settings=settings),
        policy=SimpleNamespace(settings=settings, ensure_active=lambda: None),
    )
    control.settings = settings
    control.task = asyncio.create_task(asyncio.Event().wait())


async def test_private_state_requires_login_and_writes_require_csrf(panel):
    control, client = panel
    assert (await client.get("/api/state")).status == 401
    assert (await client.post("/api/start", json={})).status == 401
    headers = await login(client)
    assert (await client.post("/api/plan", json={"title": "Private"})).status == 403
    assert not control.store.list_plans()
    assert (
        await client.post("/api/plan", json={"title": "Private"}, headers=headers)
    ).status == 200
    assert len(control.store.list_plans()) == 1
    assert (await client.get("/api/stop")).status == 405


async def test_password_change_during_login_rejects_old_password(brain, tmp_path, monkeypatch):
    password_path = tmp_path / "password.txt"
    old, new = "old-test-password", "new-test-password"
    password_path.write_text(old, encoding="utf-8")
    control = PanelControl(brain.settings, root=tmp_path)
    began, resume = asyncio.Event(), asyncio.Event()
    to_thread = asyncio.to_thread

    async def delayed_hash(func, *args, **kwargs):
        if func is hashlib.pbkdf2_hmac and args[1] == old.encode():
            began.set()
            await resume.wait()
        return await to_thread(func, *args, **kwargs)

    async with TestClient(TestServer(create_panel(control, old, password_path))) as client:
        monkeypatch.setattr(asyncio, "to_thread", delayed_hash)
        request = asyncio.create_task(client.post("/api/login", json={"password": old}))
        try:
            await asyncio.wait_for(began.wait(), 3)
            password_path.write_text(new, encoding="utf-8")
        finally:
            resume.set()
        assert (await request).status == 401
        assert not (await (await client.get("/api/session")).json())["authenticated"]
        assert (await client.post("/api/login", json={"password": new})).status == 200


async def test_opening_panel_starts_one_telegram_worker_and_shutdown_closes_it(
    brain, tmp_path, monkeypatch
):
    from telegram_agent import panel as module

    started, stopped = asyncio.Event(), asyncio.Event()

    class Worker:
        def __init__(self, settings):
            self.ready = asyncio.Event()

        async def run(self):
            self.ready.set()
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    control = PanelControl(brain.settings, root=tmp_path, agent_factory=Worker)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PanelControl", lambda _: control)
    server = asyncio.create_task(module.serve_panel(brain.settings, port=0))
    try:
        await asyncio.wait_for(started.wait(), 5)
        assert control.connected
        task = control.task
        assert (await control.start())["already_running"]
        assert control.task is task
    finally:
        control.shutdown.set()
        await asyncio.wait_for(server, 5)
    assert stopped.is_set()


async def test_cross_origin_commands_and_login_are_denied(panel):
    control, client = panel
    response = await client.post(
        "/api/login",
        json={"password": "test-panel-password"},
        headers={"Origin": "https://untrusted.example"},
    )
    assert response.status == 403
    headers = await login(client)
    headers["Origin"] = "https://untrusted.example"
    assert (
        await client.post("/api/plan", json={"title": "Injected"}, headers=headers)
    ).status == 403
    assert not control.store.list_plans()


async def test_login_throttle_and_logout_invalidate_session(panel):
    _, client = panel
    headers = await login(client)
    assert (await client.post("/api/logout", json={}, headers=headers)).status == 200
    assert (await client.get("/api/state")).status == 401
    for _ in range(8):
        assert (await client.post("/api/login", json={"password": "wrong"})).status == 401
    assert (await client.post("/api/login", json={"password": "test-panel-password"})).status == 429


async def test_state_never_exposes_settings_credentials_or_local_files(panel):
    _, client = panel
    await login(client)
    response = await client.get("/api/state")
    text = await response.text()
    assert "test-only" not in text
    assert "api_hash" not in text and "openai_key" not in text
    assert response.headers["Cache-Control"] == "no-store"
    assert (await client.get("/data/assistant.session")).status == 404
    assert (await client.get("/.env")).status == 404


async def test_plans_and_reminders_can_be_created_edited_and_cancelled(panel):
    control, client = panel
    headers = await login(client)
    response = await client.post(
        "/api/plan", json={"title": "Read", "details": "10 min"}, headers=headers
    )
    plan_id = (await response.json())["id"]
    await client.post(
        "/api/plan", json={"id": plan_id, "title": "Study", "details": "20 min"}, headers=headers
    )
    assert control.store.list_plans()[0]["title"] == "Study"
    due = (utc_now() + timedelta(hours=2)).isoformat()
    data = {"title": "Water", "due_at": due, "repeat": "none", "mode": "message"}
    response = await client.post("/api/reminder", json=data, headers=headers)
    reminder_id = (await response.json())["id"]
    response = await client.post(
        "/api/reminder", json={**data, "id": reminder_id, "title": "Tea"}, headers=headers
    )
    assert response.status == 200
    assert control.store.list_reminders()[0]["title"] == "Tea"
    await client.post("/api/cancel-reminder", json={"id": reminder_id}, headers=headers)
    assert not control.store.list_reminders()


async def test_unverified_contacts_resolve_before_queue_and_duplicate_requests_do_not_requeue(
    panel,
):
    control, client = panel
    await connected(control)
    headers = await login(client)
    control.store.save_contact("Friend", "@friend")
    contact_id = control.store.list_contacts()[0]["id"]
    data = {"contact_id": contact_id, "message": "Hello", "request_id": "unique-request-12345"}
    control.agent.queue_requested_call = AsyncMock(side_effect=ValueError("Kontakt topilmadi"))
    assert (await client.post("/api/call", json=data, headers=headers)).status == 400
    assert not control.store.list_contact_calls()
    control.agent.queue_requested_call.assert_awaited_once_with(
        "@friend",
        "Hello",
        expected_recipient_id=None,
        due_at=None,
        mode="relay",
        language="uz",
        max_turns=4,
        duration_seconds=180,
        audio_id=None,
        delivery="call",
        collect_reply=False,
        fallback_to_message=True,
    )
    control.store.set_contact_permission(contact_id, 77, True)
    response = await client.post("/api/call", json=data, headers=headers)
    assert response.status == 200
    job_id = (await response.json())["id"]
    control.store.finish_contact_call(job_id, "sent", "test only")
    assert (await client.post("/api/call", json=data, headers=headers)).status == 200
    assert len(control.store.list_contact_calls()) == 1
    assert control.store.list_contact_calls()[0]["recipient_user_id"] == 77
    assert (
        await client.post("/api/call", json={**data, "message": "Changed"}, headers=headers)
    ).status == 400


async def test_contact_permission_can_be_revoked_without_telegram_lookup(panel):
    control, client = panel
    headers = await login(client)
    control.store.save_contact("Friend", "@friend")
    contact_id = control.store.list_contacts()[0]["id"]
    control.store.set_contact_permission(contact_id, 77, True)
    response = await client.post(
        "/api/verify-contact", json={"id": contact_id, "allow": False}, headers=headers
    )
    assert response.status == 200
    assert control.store.approved_contact_ids() == ()


async def test_contact_verification_updates_running_agent_allowlist(panel):
    control, client = panel
    await connected(control)
    headers = await login(client)
    control.store.save_contact("Friend", "@friend")
    contact_id = control.store.list_contacts()[0]["id"]
    resolver = SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=77)))
    control.agent.recipient_resolver = resolver

    async def action(operation):
        return await operation()

    control.agent.policy.action = action
    response = await client.post(
        "/api/verify-contact", json={"id": contact_id, "allow": True}, headers=headers
    )
    assert response.status == 200
    assert control.agent.settings.allowed_call_user_ids == (77,)
    assert control.agent.settings.enable_contact_calls
    assert not control.store.list_contact_calls()


async def test_panel_chats_through_brain_and_sanitizes_provider_errors(panel):
    control, client = panel
    headers = await login(client)
    control.ask = AsyncMock(return_value={"reply": "Salom"})
    response = await client.post("/api/chat", json={"text": "Hello"}, headers=headers)
    assert (await response.json())["reply"] == "Salom"
    control.ask.assert_awaited_once_with("Hello", None)


async def test_panel_queues_written_message_with_voice_disabled_and_no_duplicate(panel):
    control, client = panel
    await connected(control)
    control.settings = replace(control.settings, enable_voice_calls=False)
    control.agent.settings = control.settings
    control.store.save_contact("QA", "@qa_example")
    contact = control.store.list_contacts()[0]
    control.store.set_contact_permission(contact["id"], 77, True)
    headers = await login(client)
    payload = {
        "contact_id": contact["id"],
        "message": "Hozir qayerdasiz?",
        "mode": "text",
        "request_id": "text-panel-request-1",
        "fallback_to_message": False,
    }
    for _ in range(2):
        response = await client.post("/api/call", json=payload, headers=headers)
        assert response.status == 200
        assert (await response.json())["delivery"] == "message"
    [job] = control.store.list_contact_calls()
    assert job["mode"] == "text" and not job["fallback_to_message"]


async def test_private_search_and_idempotent_snooze_work_through_panel(panel):
    control, client = panel
    assert (await client.post("/api/search", json={"query": "private"})).status == 401
    saved = control.store.add_reminder("Private dars", (utc_now() + timedelta(hours=1)).isoformat())
    headers = await login(client)
    response = await client.post("/api/search", json={"query": "private"}, headers=headers)
    assert (await response.json())["results"][0]["kind"] == "reminder"
    payload = {"id": saved["id"], "minutes": 15, "request_id": "organizer-test-request"}
    one = await client.post("/api/snooze-reminder", json=payload, headers=headers)
    two = await client.post("/api/snooze-reminder", json=payload, headers=headers)
    assert one.status == two.status == 200
    assert await one.json() == await two.json()
    snapshot = await (await client.get("/api/state")).json()
    assert "today" in snapshot
    assert len(control.store.list_reminders()) == 1


def test_scheduled_calls_survive_restart_but_do_not_run_early(tmp_path):
    path = tmp_path / "scheduled.sqlite3"
    store = Store(path)
    now = utc_now()
    due = now + timedelta(hours=1)
    job = store.queue_contact_call("@friend", "Hello", due.isoformat(), 77)
    with store.db:
        store.db.execute(
            "UPDATE outbound_calls SET created=? WHERE id=?",
            ((now - timedelta(hours=2)).isoformat(), job["id"]),
        )
    store.close()
    store = Store(path)
    try:
        store.recover_contact_calls()
        assert store.claim_contact_call(now=now) is None
        row = store.claim_contact_call(now=due + timedelta(seconds=1))
        assert row["id"] == job["id"] and row["recipient_user_id"] == 77
        assert store.claim_contact_call(now=due + timedelta(seconds=2)) is None
    finally:
        store.close()


def test_scheduled_call_more_than_five_minutes_late_is_not_dialled(store):
    due = utc_now() + timedelta(hours=1)
    store.queue_contact_call("@friend", "Hello", due.isoformat(), 77)
    assert store.claim_contact_call(now=due + timedelta(minutes=6)) is None
    assert store.list_contact_calls()[0]["state"] == "cancelled"


def test_existing_database_migrates_without_losing_contacts_and_calls(tmp_path):
    path = tmp_path / "old.sqlite3"
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE contacts (id INTEGER PRIMARY KEY,name TEXT,reference TEXT UNIQUE); INSERT INTO contacts VALUES(1,'Friend','@friend'); CREATE TABLE outbound_calls (id INTEGER PRIMARY KEY,target TEXT,message TEXT,state TEXT DEFAULT 'queued',result TEXT,created TEXT); INSERT INTO outbound_calls VALUES(1,'@friend','Hello','sent','Old result','2026-01-01T00:00:00+00:00');"
    )
    db.close()
    store = Store(path)
    try:
        assert store.list_contacts()[0]["name"] == "Friend"
        assert store.list_contacts()[0]["call_allowed"] == 0
        assert store.list_contact_calls()[0]["state"] == "sent"
    finally:
        store.close()


async def test_changed_recipient_is_rejected_before_synthesis(brain):
    from telegram_agent.contact_calls import execute_job

    settings = replace(
        brain.settings,
        enable_voice_calls=True,
        enable_contact_calls=True,
        allowed_call_user_ids=(77, 88),
    )
    job = brain.store.queue_contact_call("@friend", "Hello", recipient_user_id=77)

    async def action(operation):
        return await operation()

    app = SimpleNamespace(
        settings=settings,
        store=brain.store,
        policy=SimpleNamespace(action=action),
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=88))),
        brain=SimpleNamespace(speech=AsyncMock()),
        send_text=AsyncMock(),
    )
    await execute_job(app, job)
    app.brain.speech.assert_not_called()
    assert brain.store.list_contact_calls()[0]["state"] == "failed"
