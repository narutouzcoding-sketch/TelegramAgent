import sqlite3
import zipfile

from aiohttp.test_utils import TestClient, TestServer

from telegram_agent.maintenance import backup_path, create_backup
from telegram_agent.panel import PanelControl, create_panel
from telegram_agent.panel_auth import PanelSessions


def test_device_session_is_hashed_persistent_and_revoked_on_password_change(store):
    sessions = PanelSessions(store)
    token, csrf, lifetime = sessions.issue("test-panel-password", remember=True)
    assert lifetime == 30 * 86400
    assert token not in str(
        [tuple(row) for row in store.db.execute("SELECT * FROM panel_sessions")]
    )
    restored = PanelSessions(store)
    assert restored.get(token, "test-panel-password")["csrf"] == csrf
    assert restored.get(token, "new-test-password") is None
    restored.revoke(token)
    assert sessions.get(token, "test-panel-password") is None


async def test_remembered_login_survives_panel_restart_and_logout_revokes_it(brain, tmp_path):
    first = PanelControl(brain.settings, root=tmp_path)
    async with TestClient(TestServer(create_panel(first, "test-panel-password"))) as client:
        response = await client.post(
            "/api/login", json={"password": "test-panel-password", "remember": True}
        )
        assert response.status == 200
        token = response.cookies["ta_session"].value
        assert response.cookies["ta_session"]["max-age"] == str(30 * 86400)
        assert response.cookies["ta_session"]["httponly"]
    second = PanelControl(brain.settings, root=tmp_path)
    async with TestClient(TestServer(create_panel(second, "test-panel-password"))) as client:
        client.session.cookie_jar.update_cookies(
            {"ta_session": token}, response_url=client.make_url("/")
        )
        saved = await (await client.get("/api/session")).json()
        assert saved["authenticated"]
        assert (
            await client.post("/api/logout", json={}, headers={"X-CSRF-Token": saved["csrf"]})
        ).status == 200
        client.session.cookie_jar.update_cookies(
            {"ta_session": token}, response_url=client.make_url("/")
        )
        assert not (await (await client.get("/api/session")).json())["authenticated"]


async def test_https_reverse_proxy_uses_secure_cookie_and_correct_origin(brain, tmp_path):
    control = PanelControl(brain.settings, root=tmp_path)
    async with TestClient(TestServer(create_panel(control, "test-panel-password"))) as client:
        origin = str(client.make_url("/")).replace("http://", "https://").rstrip("/")
        response = await client.post(
            "/api/login",
            json={"password": "test-panel-password", "remember": True},
            headers={"Origin": origin, "X-Forwarded-Proto": "https"},
        )
        assert response.status == 200
        assert response.cookies["ta_session"]["secure"]


async def test_backup_excludes_active_device_sessions(store, tmp_path):
    PanelSessions(store).issue("test-panel-password", remember=True)
    result = await create_backup(store)
    with zipfile.ZipFile(backup_path(store.root, result["id"])) as archive:
        target = tmp_path / "snapshot.sqlite3"
        target.write_bytes(archive.read("data/agent.sqlite3"))
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM panel_sessions").fetchone()[0] == 0
