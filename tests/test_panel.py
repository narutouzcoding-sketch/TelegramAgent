import asyncio
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


async def test_contact_calls_need_approval_and_duplicate_requests_do_not_requeue(panel):
    control, client = panel
    await connected(control)
    headers = await login(client)
    control.store.save_contact("Friend", "@friend")
    contact_id = control.store.list_contacts()[0]["id"]
    data = {"contact_id": contact_id, "message": "Hello", "request_id": "unique-request-12345"}
    assert (await client.post("/api/call", json=data, headers=headers)).status == 400
    assert not control.store.list_contact_calls()
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
    control.ask.assert_awaited_once_with("Hello")


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
