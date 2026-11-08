"""Local backups: SQLite snapshot + durable audio, excludes .env and session files."""

import asyncio
import re
import shutil
import sqlite3
import uuid
import zipfile


def build_backup(root, source_path):
    folder = root / "data" / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    snapshot, output = folder / (token + ".sqlite3"), folder / (token + ".zip")
    try:
        source, destination = sqlite3.connect(source_path), sqlite3.connect(snapshot)
        try:
            source.backup(destination)
            # Derive audio only from this exact snapshot; concurrent new uploads
            # cannot add metadata without their audio to the backup.
            required = [
                ("voice-assets", r[0])
                for r in destination.execute("SELECT filename FROM voice_assets")
            ]
            for row in destination.execute("SELECT filename,incoming_filename FROM recordings"):
                required.extend(("recordings", filename) for filename in row if filename)
            # Restoring a snapshot must never redial a third party automatically.
            destination.execute(
                "UPDATE outbound_calls SET state='interrupted',result='Zaxira nusxa: avtomatik qayta bajarilmadi.' WHERE state IN ('queued','running')"
            )
            destination.execute(
                "UPDATE recordings SET state='failed',last_error='Zaxirada faqat tugallangan OGG yozuvlar bor.' WHERE state IN ('capturing','captured')"
            )
            destination.execute(
                "UPDATE recordings SET state='failed',last_error='Zaxiradan tiklashda avtomatik qayta yuborilmadi.' WHERE state IN ('sending','ready')"
            )
            destination.execute(
                "UPDATE owner_outbox SET state='failed',last_error='Zaxiradan avtomatik qayta yuborilmadi.' WHERE state='pending'"
            )
            destination.commit()
        finally:
            destination.close()
            source.close()
        files = []
        for name, filename in set(required):
            base = (root / "data" / name).resolve()
            path = base / filename
            if not path.is_file() or path.is_symlink() or path.resolve().parent != base:
                raise ValueError(
                    "Bazadagi audio fayli topilmadi. To'liq bo'lmagan zaxira yaratilmaydi."
                )
            files.append(path)
        total = sum(p.stat().st_size for p in files) + snapshot.stat().st_size
        if (
            total > 300 * 1024 * 1024
            or shutil.disk_usage(folder).free < total * 2 + 100 * 1024 * 1024
        ):
            raise ValueError("Zaxira hajmi katta yoki disk joyi kam.")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "data/agent.sqlite3")
            for path in files:
                archive.write(path, "data/" + path.parent.name + "/" + path.name)
            archive.writestr(
                "README.txt",
                "TelegramAgent local backup. Contains private database and saved audio. No .env or Telegram sessions. To restore: stop the agent, keep a copy of current data, then restore data/ into the same project and log in separately. Selected-folder originals are not included; only indexed text is in SQLite.",
            )
        return {
            "id": token,
            "filename": "TelegramAgent-backup-" + token[:8] + ".zip",
            "url": "/api/backups/" + token,
        }
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    finally:
        snapshot.unlink(missing_ok=True)


async def create_backup(store):
    # The source connection belongs to this thread; only the separate-connection
    # snapshot/ZIP work is delegated, with a plain path instead of a SQLite handle.
    source = store.db.execute("PRAGMA database_list").fetchone()[2]
    return await asyncio.to_thread(build_backup, store.root, source)


def backup_path(root, token):
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("Zaxira identifikatori noto'g'ri.")
    folder = (root / "data" / "backups").resolve()
    path = folder / (token + ".zip")
    if not path.is_file() or path.resolve().parent != folder:
        raise ValueError("Zaxira topilmadi.")
    return path
