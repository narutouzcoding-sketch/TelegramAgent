"""Durable PCM capture independent of STT/AI; deliver original audio to the owner."""

import asyncio
import logging
import math
import subprocess
import sys
import time
import uuid

from .config import ROOT

log = logging.getLogger(__name__)
RATE = 48000 * 2


class CallRecording:
    def __init__(self, store, peer_id, label, job_id=None, root=ROOT):
        self.store, self.peer_id, self.root = store, peer_id, root
        self.id = uuid.uuid4().hex
        self.folder = root / "data" / "recordings"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.tracks = {
            name: (self.folder / f"{self.id}.{name}.pcm").open("wb")
            for name in ("incoming", "outgoing")
        }
        self.positions = {name: 0 for name in self.tracks}
        self.flushed = self.started
        self.closed = False
        store.start_recording(self.id, peer_id, label, job_id)

    def write(self, track, pcm):
        if self.closed or not pcm:
            return
        # Preserve pauses and overlap. Do not apply ASR's echo/busy filters to recordings.
        pcm = pcm[: len(pcm) // 2 * 2]
        position = min(
            1200 * RATE,
            max(
                self.positions[track],
                int((time.monotonic() - self.started) * RATE) // 2 * 2 - len(pcm),
            ),
        )
        if position >= 1200 * RATE:
            return
        stream = self.tracks[track]
        if position > self.positions[track]:
            stream.seek(position)
        stream.write(pcm[: 1200 * RATE - position])
        self.positions[track] = position + min(len(pcm), 1200 * RATE - position)
        if time.monotonic() - self.flushed >= 1:
            for file in self.tracks.values():
                file.flush()
            self.flushed = time.monotonic()

    def close(self):
        if not self.closed:
            self.closed = True
            for file in self.tracks.values():
                file.close()
            self.store.recording_captured(self.id, max(self.positions.values()) / RATE)


def begin_recording(app, peer_id, label, job_id=None):
    if not getattr(app.settings, "record_calls", False):
        return None
    recording = CallRecording(app.store, peer_id, label, job_id, root=app.store.root)
    app.active_recording = recording
    return recording


def end_recording(app, recording):
    if recording is not None:
        if getattr(app, "active_recording", None) is recording:
            app.active_recording = None
        recording.close()


async def convert_recording(store, row, root=ROOT):
    folder = root / "data" / "recordings"
    incoming, outgoing = (folder / f"{row['id']}.{kind}.pcm" for kind in ("incoming", "outgoing"))
    sources = [p for p in (incoming, outgoing) if p.exists() and p.stat().st_size > 0]
    if not sources:
        store.recording_failed(row["id"], "Ovoz paketi olinmadi; yozuv bo'sh.")
        return
    mixed = folder / f"{row['id']}.ogg"
    original = folder / f"{row['id']}.incoming.ogg"

    async def encode(inputs, output):
        args = ["ffmpeg", "-v", "error", "-y"]
        for path in inputs:
            args += ["-f", "s16le", "-ar", "48000", "-ac", "1", "-i", str(path)]
        if len(inputs) == 2:
            args += [
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest:normalize=1[a]",
                "-map",
                "[a]",
            ]
        args += ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000", "-ac", "1", str(output)]
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            async with asyncio.timeout(90):
                code = await process.wait()
            if code or not output.exists() or output.stat().st_size < 100:
                raise RuntimeError("Audio conversion failed")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    try:
        await encode(sources, mixed)
        if incoming in sources:
            await encode([incoming], original)
        duration = max(p.stat().st_size for p in sources) / RATE
        store.recording_ready(
            row["id"], mixed.name, original.name if original.exists() else "", duration
        )
        for path in (incoming, outgoing):
            path.unlink(missing_ok=True)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Keep PCM sources for recovery instead of losing a call on an encoder error.
        store.recording_failed(row["id"], "Ovoz saqlandi, formatlashda xato: " + type(exc).__name__)


async def run_recordings(app):
    from telethon.tl.types import DocumentAttributeAudio

    app.store.recover_recordings()
    while True:
        for row in app.store.pending_recordings("captured"):
            await convert_recording(app.store, row, app.store.root)
        row = app.store.claim_recording()
        if row:
            path = (
                app.store.root
                / "data"
                / "recordings"
                / (row["incoming_filename"] or row["filename"])
            )
            try:
                caption = recording_caption(app.store, row)
                await app.policy.send(
                    lambda: app.telegram.send_file(
                        app.owner,
                        str(path),
                        voice_note=True,
                        caption=caption,
                        parse_mode=None,
                        attributes=[
                            DocumentAttributeAudio(
                                duration=max(1, math.ceil(row["duration"])), voice=True
                            )
                        ],
                    )
                )
                app.store.recording_sent(row["id"])
            except asyncio.CancelledError:
                app.store.recording_retry(row["id"], "Yuborish to'xtatildi.")
                raise
            except Exception as exc:
                app.store.recording_retry(
                    row["id"], "Telegramga yuborilmadi: " + type(exc).__name__
                )
                log.warning("Recording delivery failed type=%s", type(exc).__name__)
        await asyncio.sleep(1)


def recording_caption(store, row):
    caption = f"Qo'ng'iroq yozuvi: {row['label']}\n"
    if row.get("job_id"):
        task = store.db.execute(
            "SELECT state,message,answer_verified FROM outbound_calls WHERE id=?", (row["job_id"],)
        ).fetchone()
        if task:
            caption += "Savol/vazifa: " + task["message"][:250] + "\n"
            if task["state"] == "running":
                caption += "Javob holati hali tekshirilmoqda.\n"
            elif task["state"] == "partial_answer":
                caption += "Faqat qisman javob aniqlandi.\n"
            elif task["state"] == "declined":
                caption += "Suhbatdosh javob berishni rad etdi.\n"
            elif task["answer_verified"]:
                caption += "Savolga tegishli tanilgan javob aniqlandi.\n"
            else:
                caption += "Savolga javob olingani tasdiqlanmagan. Bu faqat audio yozuv.\n"
    caption += (
        "Kiruvchi kanalning asl yozuvi; matn tanishda xato bo'lishi mumkin."
        if row["incoming_filename"]
        else "Faqat agent ovozi; suhbatdosh ovozi olinmagan."
    )
    return caption[:950]
