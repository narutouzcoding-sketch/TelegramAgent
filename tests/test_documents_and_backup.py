import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from telegram_agent.documents import DocumentLibrary
from telegram_agent.maintenance import backup_path, create_backup
from telegram_agent.store import utc_now


async def test_document_cards_read_only_selected_sources_and_keep_notes(store, tmp_path):
    root = tmp_path / "chosen"
    root.mkdir()
    source = root / "plan.txt"
    source.write_text("<script>untrusted document text</script>", encoding="utf-8")
    library = DocumentLibrary(store)
    await library.index(str(root))
    library.add_note("QA note", "Keep locally")
    items = library.status()["items"]
    assert len(items) == 2 and all("body" not in row for row in items)
    file = next(row for row in items if row["kind"] == "file")
    assert library.document(file["id"])["body"].startswith("<script>")
    source.unlink()
    with pytest.raises(ValueError, match="Manba fayli"):
        library.document(file["id"])
    library.disconnect()
    assert len(library.status()["items"]) == 1


async def test_selected_folder_only_supported_text_and_no_escape(store, tmp_path):
    root = tmp_path / "chosen"
    root.mkdir()
    (root / "plan.txt").write_text("Ertaga dars jadvali: soat 9 matematika.", encoding="utf-8")
    (root / "api_keys.md").write_text("Should not index", encoding="utf-8")
    (root / "parollar.txt").write_text("Should not index", encoding="utf-8")
    (root / "photo.jpg").write_bytes(b"not a document")
    other = tmp_path / "outside.txt"
    other.write_text("Forbidden outside needle", encoding="utf-8")
    library = DocumentLibrary(store)
    result = await library.index(str(root))
    assert result["files"] == 1 and result["skipped"] == 3
    assert "matematika" in library.search("jadvali")[0]["snippet"]
    assert not library.search("Forbidden")
    library.disconnect()
    assert not library.search("jadvali") and (root / "plan.txt").is_file()


async def test_docx_is_extracted_without_executing_contents(store, tmp_path):
    root = tmp_path / "chosen"
    root.mkdir()
    with zipfile.ZipFile(root / "test.docx", "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Qaror 123 ABC</w:t></w:r></w:p></w:document>',
        )
    library = DocumentLibrary(store)
    assert (await library.index(str(root)))["files"] == 1
    assert "123" in library.search("Qaror")[0]["snippet"]


async def test_pdf_text_extraction_and_encrypted_pdf_skipped(store, tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    root = tmp_path / "chosen"
    root.mkdir()
    writer = PdfWriter()
    page = writer.add_blank_page(300, 300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 200 Td (Schedule biology 0900) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(root / "schedule.pdf")
    writer.encrypt("do-not-read")
    writer.write(root / "locked.pdf")
    library = DocumentLibrary(store)
    status = await library.index(str(root))
    assert status["files"] == 1 and status["skipped"] == 1
    assert "biology" in library.search("Schedule")[0]["snippet"]


async def test_private_document_answers_never_enter_cloud_history(brain, tmp_path):
    root = tmp_path / "chosen"
    root.mkdir()
    (root / "secret-plan.txt").write_text("LOCAL_SECRET_MARKER meeting at nine", encoding="utf-8")
    # Use a normal filename; secret-like filenames are intentionally excluded.
    (root / "plan.txt").write_text("LOCAL_SECRET_MARKER meeting at nine", encoding="utf-8")
    await brain.documents.index(str(root))
    brain.ai.request = AsyncMock(side_effect=AssertionError("Cloud must not see documents"))
    reply = await brain.answer("Hujjatlardan LOCAL_SECRET_MARKER top")
    assert "LOCAL_SECRET_MARKER" in reply
    assert "LOCAL_SECRET_MARKER" in brain.store.history()[-1]["content"]
    assert not any("LOCAL_SECRET_MARKER" in r["content"] for r in brain.store.context())
    brain.ai.request.assert_not_called()


def test_notes_are_local_and_survive_folder_disconnect(store):
    library = DocumentLibrary(store)
    library.add_note("Afzallik", "Kofe uchun shakar kerak emas")
    library.disconnect()
    assert "shakar" in library.search("Kofe")[0]["snippet"]


def test_folder_validation_does_not_allow_disk_root_or_missing(store, tmp_path):
    library = DocumentLibrary(store)
    for value in ("", str(tmp_path / "missing"), Path(tmp_path.anchor), None):
        with pytest.raises(ValueError):
            library.validate_folder(value)


async def test_backup_contains_data_and_audio_but_never_env_or_sessions(store):
    root = store.root
    (root / ".env").write_text("DO_NOT_COPY=private")
    folder = root / "data"
    folder.mkdir(exist_ok=True)
    (folder / "assistant.session").write_bytes(b"private")
    voices = folder / "voice-assets"
    voices.mkdir()
    (voices / ("a" * 32 + ".ogg")).write_bytes(b"audio")
    store.add_voice_asset("a" * 32, "Synthetic", 1)
    store.add_plan("Saved plan")
    result = await create_backup(store)
    with zipfile.ZipFile(backup_path(root, result["id"])) as z:
        names = z.namelist()
        assert "data/agent.sqlite3" in names and any(n.endswith(".ogg") for n in names)
        assert not any(".env" in n or ".session" in n for n in names)
    with pytest.raises(ValueError):
        backup_path(root, "../outside")


async def test_private_document_answer_is_not_sent_to_online_tts(brain, tmp_path, monkeypatch):
    from telegram_agent.ai_access import AIUnavailable
    from telegram_agent.documents import PrivateReply
    from telegram_agent.free_voice import FreeVoiceSession

    brain.documents.add_note("Test", "PRIVATE_DOC_MARKER should stay out of speech")
    brain.private_delivery = AsyncMock()
    brain.speech = AsyncMock()
    from telegram_agent import free_voice

    monkeypatch.setattr(free_voice, "decode_pcm", AsyncMock(return_value=b"\0" * 960))
    voice = FreeVoiceSession(brain, AsyncMock(), "")

    # Run the real sender loop against a mock transport, including send completion.
    pump = __import__("asyncio").create_task(voice.play())
    try:
        await voice.respond("Hujjatlardan PRIVATE_DOC_MARKER top")
        assert "PRIVATE_DOC_MARKER" in brain.private_delivery.call_args.args[0]
        assert all(
            "PRIVATE_DOC_MARKER" not in str(call.args[0]) for call in brain.speech.await_args_list
        )
    finally:
        pump.cancel()
        await __import__("asyncio").gather(pump, return_exceptions=True)
    from telegram_agent.brain import Brain

    with pytest.raises(AIUnavailable):
        await Brain.speech(brain, PrivateReply("PRIVATE_DOC_MARKER"), tmp_path / "no.ogg")


async def test_backup_disables_restored_outbound_jobs_but_keeps_live_queue(store, tmp_path):
    import sqlite3

    job = store.queue_contact_call("@qa_example", "Original job")
    reminder = store.add_reminder("Call reminder", (utc_now() + timedelta(hours=1)).isoformat())
    result = await create_backup(store)
    with zipfile.ZipFile(backup_path(store.root, result["id"])) as archive:
        snapshot = tmp_path / "snapshot.sqlite3"
        snapshot.write_bytes(archive.read("data/agent.sqlite3"))
    db = sqlite3.connect(snapshot)
    try:
        assert (
            db.execute("SELECT state FROM outbound_calls WHERE id=?", (job["id"],)).fetchone()[0]
            == "interrupted"
        )
        assert db.execute(
            "SELECT state,mode,recovery_message_only FROM reminders WHERE id=?", (reminder["id"],)
        ).fetchone() == ("pending", "call", 1)
    finally:
        db.close()
    assert store.list_contact_calls()[0]["state"] == "queued"
    assert not store.list_reminders()[0]["recovery_message_only"]


async def test_missing_required_audio_refuses_incomplete_backup(store):
    store.add_voice_asset("f" * 32, "Missing", 1)
    with pytest.raises(ValueError, match="audio"):
        await create_backup(store)
    assert not list((store.root / "data" / "backups").glob("*.zip"))


async def test_index_rechecks_each_file_is_inside_selected_root(store, tmp_path, monkeypatch):
    root = tmp_path / "chosen"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE_MUST_NOT_READ")
    library = DocumentLibrary(store)
    monkeypatch.setattr(library, "_paths", lambda _root: ([outside], 0))
    status = await library.index(str(root))
    assert status["files"] == 0 and status["skipped"] == 1


async def test_backup_uses_snapshot_references_during_concurrent_asset_creation(
    store, monkeypatch, tmp_path
):
    import sqlite3

    from telegram_agent import maintenance

    folder = store.root / "data" / "voice-assets"
    folder.mkdir(parents=True)
    old_id, new_id = "a" * 32, "b" * 32
    (folder / (old_id + ".ogg")).write_bytes(b"old")
    store.add_voice_asset(old_id, "Old", 1)
    source_path = store.db.execute("PRAGMA database_list").fetchone()[2]
    connect = sqlite3.connect

    class Source:
        def __init__(self, connection):
            self.connection = connection

        def backup(self, destination):
            self.connection.backup(destination)
            (folder / (new_id + ".ogg")).write_bytes(b"new")
            late = connect(source_path)
            try:
                late.execute(
                    "INSERT INTO voice_assets(id,label,filename,duration,created) VALUES(?,?,?,?,?)",
                    (new_id, "New", new_id + ".ogg", 1, "2026-11-08"),
                )
                late.commit()
            finally:
                late.close()

        def close(self):
            self.connection.close()

    def open_db(path, *args, **kwargs):
        db = connect(path, *args, **kwargs)
        return Source(db) if str(path) == str(source_path) else db

    monkeypatch.setattr(maintenance.sqlite3, "connect", open_db)
    result = await create_backup(store)
    with zipfile.ZipFile(backup_path(store.root, result["id"])) as archive:
        assert "data/voice-assets/" + old_id + ".ogg" in archive.namelist()
        assert "data/voice-assets/" + new_id + ".ogg" not in archive.namelist()
        snapshot = tmp_path / "read-snapshot.sqlite3"
        snapshot.write_bytes(archive.read("data/agent.sqlite3"))
    db = connect(snapshot)
    try:
        assert db.execute("SELECT COUNT(*) FROM voice_assets").fetchone()[0] == 1
    finally:
        db.close()
    assert len(store.voice_assets()) == 2
