"""Owner-recorded audio assets. No ASR, translation or LLM is used here."""

import asyncio
import json
import subprocess
import sys
import tempfile
import uuid

MAX_UPLOAD = 12 * 1024 * 1024
FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def asset_path(store, asset_id):
    if (
        not isinstance(asset_id, str)
        or len(asset_id) != 32
        or any(c not in "0123456789abcdef" for c in asset_id)
    ):
        raise ValueError("Ovoz identifikatori noto'g'ri.")
    row = store.voice_asset(asset_id)
    folder = (store.root / "data" / "voice-assets").resolve()
    path = folder / (asset_id + ".ogg")
    if row is None or not path.is_file() or path.resolve().parent != folder:
        raise ValueError("Ovoz yozuvi topilmadi. Qayta yuklang.")
    return path, row


async def convert_upload(source, output):
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        "matroska,webm,ogg,wav,mp3,mov,flac,aac",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-t",
        "181",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        str(output),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=FLAGS,
    )
    try:
        async with asyncio.timeout(35):
            await process.wait()
        if process.returncode or not output.exists():
            raise ValueError("Audio o'qilmadi. WAV, OGG, WebM, MP3 yoki M4A faylini tanlang.")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    probe = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=FLAGS,
    )
    try:
        async with asyncio.timeout(10):
            raw, _ = await probe.communicate()
        duration = float(json.loads(raw)["format"]["duration"])
        if probe.returncode or not 0.3 <= duration <= 180.05:
            raise ValueError(
                "Ovoz 0.3 soniyadan 3 daqiqagacha bo'lsin. Yozuv kesib yuborilmadi; qabul qilinmadi."
            )
        return duration
    finally:
        if probe.returncode is None:
            probe.kill()
            await probe.wait()


async def save_upload(store, data, label="Mening ovozli xabarim"):
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Ovoz fayli bo'sh yoki 12 MB dan katta.")
    label = store._title(label)
    if len(store.voice_assets()) >= 100:
        raise ValueError("Kutubxonada 100 ta ovoz bor. Avval keraksiz yozuvlarni arxivlang.")
    folder = store.root / "data" / "voice-assets"
    folder.mkdir(parents=True, exist_ok=True)
    asset_id = uuid.uuid4().hex
    source, output = folder / (asset_id + ".upload"), folder / (asset_id + ".ogg")
    try:
        source.write_bytes(data)
        duration = await convert_upload(source, output)
        store.add_voice_asset(asset_id, label, duration)
        return {
            "id": asset_id,
            "label": label,
            "duration": duration,
            "url": "/api/voice-assets/" + asset_id,
        }
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    finally:
        source.unlink(missing_ok=True)


def voice_introduction(owner_name, language, collect_reply, record_calls=True):
    prompts = {
        "uz": f"Assalomu alaykum. Men {owner_name}ning AI yordamchisiman. Hozir u yuborgan asl ovozli xabarni eshittiraman. ",
        "en": f"Hello. I am {owner_name}'s AI assistant. I will play their original voice message now. ",
        "ru": f"Здравствуйте. Я ИИ помощник {owner_name}. Сейчас прозвучит оригинальное голосовое сообщение. ",
    }
    notices = {
        "uz": "Xabardan keyin javobingizni ayting. Suhbat yozilib, egasiga yuboriladi.",
        "en": "Please reply after the message. This call is recorded and sent to the owner.",
        "ru": "Ответьте после сообщения. Разговор записывается и передается владельцу.",
    }
    recording_notice = {
        "uz": "Suhbat ovozi yozilib, egasiga yuboriladi. ",
        "en": "This call is recorded and sent to the owner. ",
        "ru": "Разговор записывается и передается владельцу. ",
    }
    return prompts[language] + (
        notices[language] if collect_reply else recording_notice[language] if record_calls else ""
    )


async def prepare_voice_call(app, job):
    from .contact_calls import decode_pcm

    if app.settings.voice_provider != "free":
        raise ValueError("Asl ovozli qo'ng'iroq uchun bepul ovoz rejimini tanlang.")
    path, row = asset_path(app.store, job["audio_id"])
    if job.get("collect_reply") and not app.settings.record_calls:
        raise ValueError("Javobni olish uchun RECORD_CALLS=true bo'lsin.")
    original = await decode_pcm(path)
    intro = voice_introduction(
        app.owner_name,
        job.get("language", "uz"),
        bool(job.get("collect_reply")),
        app.settings.record_calls,
    )
    with tempfile.TemporaryDirectory(dir=app.store.root / "data", prefix="voice-intro-") as folder:
        from pathlib import Path

        speech = Path(folder) / "intro.ogg"
        await app.brain.free_speech.speech(intro, speech, language=job.get("language", "uz"))
        introduction = await decode_pcm(speech)
    pcm = introduction + bytes(48000) + original
    if len(pcm) / 96000 + (3 if job.get("collect_reply") else 0) > job.get("duration_seconds", 180):
        raise ValueError(
            "Tanlangan davomiylik ovoz uchun qisqa. 5 yoki 10 daqiqani tanlang; qo'ng'iroq qilinmadi."
        )
    return pcm, intro


def original_voice_task(brain, owner_name, job, pcm, introduction):
    from .contact_conversation import ContactConversation

    task = ContactConversation(brain, owner_name, {**job, "mode": "record"})
    task.greeting_pcm = pcm

    async def intro():
        return introduction

    task.introduction = intro
    return task
