"""Resolve explicitly requested recipients and relay a fixed message over Telegram."""

import asyncio
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from openai import APIError
from telethon import functions
from telethon.tl.types import User

from .ai_access import AIUnavailable, public_ai_error
from .config import ROOT
from .setup_inputs import international_phone


class RecipientResolver:
    def __init__(self, client, store, own_id):
        self.client, self.store, self.own_id = client, store, own_id
        self.phone_lock = asyncio.Lock()
        self.last_phone_lookup = None

    async def resolve(self, target):
        target = target.strip()
        saved = [
            row for row in self.store.list_contacts() if row["name"].casefold() == target.casefold()
        ]
        if len(saved) > 1:
            raise ValueError(
                "Bu ism bilan bir nechta kontakt bor. Aniq @username yoki raqam bering."
            )
        if saved:
            target = saved[0]["reference"]
        if target.startswith("+"):
            number = international_phone(target)
            async with self.phone_lock:
                loop = asyncio.get_running_loop()
                if self.last_phone_lookup is not None:
                    await asyncio.sleep(max(0, 3 - (loop.time() - self.last_phone_lookup)))
                self.last_phone_lookup = loop.time()
                result = await self.client(functions.contacts.ResolvePhoneRequest(phone=number[1:]))
            users = [user for user in result.users if user.id == result.peer.user_id]
            if not users:
                raise ValueError("Raqam orqali Telegram akkaunt topilmadi. @username bering.")
            user = users[0]
        elif target.startswith("@"):
            user = await self.client.get_entity(target)
        else:
            result = await self.client(functions.contacts.GetContactsRequest(hash=0))
            users = [
                user
                for user in result.users
                if target.casefold()
                in {
                    (user.first_name or "").casefold(),
                    " ".join(filter(None, [user.first_name, user.last_name])).casefold(),
                    (user.username or "").casefold(),
                }
            ]
            if len(users) != 1:
                raise ValueError(
                    "Kontakt aniq topilmadi. Kontaktini ulashing yoki @username/+raqam bering."
                )
            user = users[0]
        if not isinstance(user, User) or user.bot or user.deleted or user.id == self.own_id:
            raise ValueError(
                "Qabul qiluvchi boshqa, faol oddiy Telegram foydalanuvchisi bo'lishi kerak."
            )
        return user


async def decode_pcm(path):
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-ar",
        "48000",
        "-ac",
        "1",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        async with asyncio.timeout(30):
            audio, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    if process.returncode or not audio:
        raise RuntimeError("Ovoz PCM formatga aylantirilmadi.")
    if len(audio) > 48000 * 2 * 180:
        raise ValueError("Xabar ovozi 3 daqiqadan uzun. Qisqaroq xabar bering.")
    return audio


async def play_relay(app, user, audio):
    from pytgcalls.types import CallConfig, Device, ExternalMedia, MediaStream
    from pytgcalls.types.raw import AudioParameters

    async with app.call_lock:
        app.call_task = asyncio.current_task()
        app.relay_target = user.id
        app.relay_ended = asyncio.Event()
        try:
            async with asyncio.timeout(app.settings.ring_timeout_seconds + 45):
                await app.policy.dial(
                    user.id,
                    lambda: app.calls.play(
                        user.id,
                        MediaStream(
                            ExternalMedia.AUDIO,
                            AudioParameters(bitrate=48000, channels=1),
                            video_flags=MediaStream.Flags.IGNORE,
                        ),
                        config=CallConfig(timeout=app.settings.ring_timeout_seconds),
                    ),
                )
            # Feed only after answer. No recipient audio is recorded or given to the model.
            loop = asyncio.get_running_loop()
            deadline = loop.time()
            for offset in range(0, len(audio), 960):
                if app.relay_ended.is_set():
                    raise ValueError(
                        "Qabul qiluvchi xabar tugashidan oldin qo'ng'iroqni yakunladi."
                    )
                await app.calls.send_frame(
                    user.id, Device.MICROPHONE, audio[offset : offset + 960].ljust(960, b"\0")
                )
                deadline += 0.01
                await asyncio.sleep(max(0, deadline - loop.time()))
                if loop.time() - deadline > 0.1:
                    deadline = loop.time()
            if app.relay_ended.is_set():
                raise ValueError("Qo'ng'iroq xabar tugamasdan uzildi.")
            await asyncio.sleep(0.25)
        finally:
            with suppress(Exception):
                await app.calls.leave_call(user.id)
            app.relay_target = None
            app.relay_ended = None
            app.call_task = None


async def execute_job(app, job):
    try:
        if (
            not app.settings.enable_voice_calls
            or not app.settings.enable_contact_calls
            or not app.settings.allowed_call_user_ids
        ):
            raise ValueError("Kontakt qo'ng'iroqlari o'chirilgan; telefon terilmadi.")
        user = await app.policy.action(lambda: app.recipient_resolver.resolve(job["target"]))
        if user.id not in app.settings.allowed_call_user_ids:
            raise ValueError(
                "Bu foydalanuvchi ruxsat berilgan kontaktlar ro'yxatida yo'q; telefon terilmadi."
            )
        await app.send_text(f"Qo'ng'iroq #{job['id']}: {job['target']} uchun xabar tayyorlanyapti.")
        text = (
            f"Assalomu alaykum. Men {app.owner_name}ning AI yordamchisiman. "
            "U sizga quyidagi xabarni yetkazishimni so'radi. " + job["message"] + ". Rahmat."
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="relay-") as folder:
            path = Path(folder) / "message.ogg"
            await app.brain.speech(text, path)
            audio = await decode_pcm(path)
            await play_relay(app, user, audio)
    except asyncio.CancelledError:
        app.store.finish_contact_call(job["id"], "cancelled", "Qo'ng'iroq to'xtatildi.")
        raise
    except Exception as exc:
        # Only our explicit input/recipient errors are suitable for the owner; SDK bodies stay private.
        reason = (
            public_ai_error(exc)
            if isinstance(exc, (APIError, AIUnavailable))
            else str(exc)
            if isinstance(exc, ValueError)
            else type(exc).__name__
        )
        app.store.finish_contact_call(job["id"], "failed", reason)
        await app.send_text(
            f"Qo'ng'iroq #{job['id']} yakunlanmadi: {reason[:200]}. Qayta terilmadi."
        )
    else:
        app.store.finish_contact_call(
            job["id"], "sent", "Qo'ng'iroq ulandi; xabar audiosi uzatildi."
        )
        await app.send_text(
            f"Qo'ng'iroq #{job['id']}: {job['target']} ga xabar audiosi uzatildi. "
            "Qabul qiluvchi eshitganini alohida tasdiqlamagan."
        )


async def run_queue(app):
    app.store.recover_contact_calls()
    while True:
        if app.call_lock.locked():
            await asyncio.sleep(1)
            continue
        job = app.store.claim_contact_call()
        if not job:
            await asyncio.sleep(1)
            continue
        task = app.spawn(execute_job(app, job))
        app.contact_job_task = task
        app.contact_job_id = job["id"]
        try:
            await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            # /hangup cancels only the active job; the queue remains available.
        finally:
            app.contact_job_task = None
            app.contact_job_id = None
