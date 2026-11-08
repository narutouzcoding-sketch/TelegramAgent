import asyncio
import io
import math
import struct
import wave
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from telegram_agent.contact_calls import decode_pcm, execute_job
from telegram_agent.free_voice import FreeVoiceSession
from telegram_agent.panel import PanelControl, create_panel
from telegram_agent.store import Store, utc_now
from telegram_agent.voice_library import asset_path, prepare_voice_call, save_upload


def wav(duration=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(
            b"".join(
                struct.pack("<h", int(2000 * math.sin(i / 48000 * 440 * 2 * math.pi)))
                for i in range(int(duration * 48000))
            )
        )
    return out.getvalue()


async def test_upload_real_ffmpeg_preserves_audio_and_metadata(store):
    asset = await save_upload(store, wav(), "O'z ovozim 📞")
    path, row = asset_path(store, asset["id"])
    assert path.suffix == ".ogg" and path.stat().st_size > 100
    assert 1 <= row["duration"] < 1.1
    assert len(await decode_pcm(path)) >= 96000
    assert not list(path.parent.glob("*.upload"))


async def test_empty_corrupt_and_oversize_uploads_clean_up(store):
    for data in (b"", b"not audio", b"x" * (12 * 1024 * 1024 + 1)):
        with pytest.raises(ValueError):
            await save_upload(store, data)
    assert not store.voice_assets()
    folder = store.root / "data" / "voice-assets"
    assert not folder.exists() or not list(folder.iterdir())


async def test_voice_job_survives_restart_and_duplicate_submission(store):
    from datetime import timedelta

    asset = await save_upload(store, wav(), "Saved")
    due = utc_now() + timedelta(hours=1)
    first = store.queue_contact_call(
        "@qa_example",
        "Original",
        mode="voice",
        audio_id=asset["id"],
        delivery="call",
        collect_reply=True,
        due_at=due.isoformat(),
    )
    second = store.queue_contact_call(
        "@qa_example",
        "Original",
        mode="voice",
        audio_id=asset["id"],
        delivery="call",
        collect_reply=True,
        due_at=due.isoformat(),
    )
    assert first["id"] == second["id"]
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    other = Store(__import__("pathlib").Path(path))
    try:
        row = other.claim_contact_call(now=due)
        assert (
            row["audio_id"] == asset["id"]
            and row["collect_reply"] == 1
            and row["delivery"] == "call"
        )
        with pytest.raises(ValueError):
            other.archive_voice_asset(asset["id"])
    finally:
        other.close()


async def test_asset_archive_is_reversible_data_preserving_and_missing_asset_rejected(store):
    asset = await save_upload(store, wav(), "Saved")
    path, _ = asset_path(store, asset["id"])
    store.archive_voice_asset(asset["id"])
    assert path.is_file() and not store.voice_assets()
    with pytest.raises(ValueError):
        store.queue_contact_call("@qa_example", "Original", mode="voice", audio_id=asset["id"])
    with pytest.raises(ValueError):
        asset_path(store, "../outside")


async def test_original_pcm_is_appended_without_asr_or_llm(brain):
    asset = await save_upload(brain.store, wav(), "Saved")

    async def speech(text, path, **options):
        path.write_bytes(wav(0.5))

    cfg = replace(brain.settings, voice_provider="free", record_calls=True)
    fake = SimpleNamespace(
        settings=cfg,
        store=brain.store,
        owner_name="QA",
        brain=SimpleNamespace(free_speech=SimpleNamespace(speech=speech)),
    )
    original = await decode_pcm(asset_path(brain.store, asset["id"])[0])
    pcm, intro = await prepare_voice_call(
        fake,
        {"audio_id": asset["id"], "duration_seconds": 60, "collect_reply": True, "language": "en"},
    )
    assert pcm.endswith(original) and "original voice message" in intro
    with pytest.raises(ValueError):
        await prepare_voice_call(
            fake, {"audio_id": asset["id"], "duration_seconds": 1, "collect_reply": True}
        )


async def test_raw_greeting_never_synthesizes_or_transcribes():
    pcm = b"\x10\x02" * 480 * 4
    fake = SimpleNamespace(
        greeting_pcm=pcm,
        record_only=True,
        use_native_asr=True,
        speech=AsyncMock(side_effect=AssertionError("No TTS for original PCM")),
        free_speech=SimpleNamespace(prepare=AsyncMock()),
    )
    sender = AsyncMock()
    voice = FreeVoiceSession(fake, sender, "Not synthesized")
    try:
        await voice.start()
        async with asyncio.timeout(1):
            while not voice.accepting:
                await asyncio.sleep(0.01)
        assert any(c.args == (pcm[:960],) for c in sender.await_args_list)
        fake.speech.assert_not_called()
    finally:
        await voice.close()


async def test_direct_golos_delivery_uses_exact_asset_not_ai_and_never_dials(brain):
    asset = await save_upload(brain.store, wav(), "Saved")
    job = brain.store.queue_contact_call(
        "@qa_example",
        "Original",
        mode="voice",
        audio_id=asset["id"],
        delivery="message",
        recipient_user_id=77,
    )

    async def action(op):
        return await op()

    app = SimpleNamespace(
        settings=replace(
            brain.settings,
            enable_contact_calls=True,
            enable_voice_calls=True,
            allowed_call_user_ids=(77,),
        ),
        store=brain.store,
        owner_name="QA",
        brain=brain,
        recipient_resolver=SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(id=77))),
        policy=SimpleNamespace(action=action, send=action, dial=AsyncMock()),
        telegram=SimpleNamespace(send_file=AsyncMock()),
        send_text=AsyncMock(),
    )
    brain.ai.request = AsyncMock(side_effect=AssertionError("No paid/cloud AI"))
    await execute_job(app, job)
    app.telegram.send_file.assert_awaited_once()
    assert app.telegram.send_file.call_args.args[1] == str(asset_path(brain.store, asset["id"])[0])
    app.policy.dial.assert_not_called()
    brain.ai.request.assert_not_called()
    assert brain.store.list_contact_calls()[0]["state"] == "sent"


async def test_voice_upload_and_playback_require_auth_and_csrf(brain, tmp_path):
    control = PanelControl(brain.settings, root=tmp_path)
    client = TestClient(TestServer(create_panel(control, "qa-password-2026")))
    await client.start_server()
    try:
        assert (
            await client.post(
                "/api/voice-upload", data=wav(), headers={"Content-Type": "audio/wav"}
            )
        ).status == 401
        r = await client.post("/api/login", json={"password": "qa-password-2026"})
        headers = {"X-CSRF-Token": (await r.json())["csrf"], "Content-Type": "audio/wav"}
        assert (
            await client.post(
                "/api/voice-upload", data=wav(), headers={"Content-Type": "audio/wav"}
            )
        ).status == 403
        r = await client.post("/api/voice-upload?label=QA", data=wav(), headers=headers)
        assert r.status == 200
        asset = await r.json()
        audio = await client.get(asset["url"])
        assert audio.status == 200 and audio.headers["Content-Type"] == "audio/ogg"
        await client.post("/api/logout", json={}, headers={"X-CSRF-Token": headers["X-CSRF-Token"]})
        assert (await client.get(asset["url"])).status == 401
    finally:
        await client.close()


def test_recording_notice_follows_actual_recording_even_without_reply():
    from telegram_agent.voice_library import voice_introduction

    assert "recorded" in voice_introduction("QA", "en", False, True)
    assert "recorded" not in voice_introduction("QA", "en", False, False)
