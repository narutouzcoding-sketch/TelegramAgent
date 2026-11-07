import asyncio
import logging
import tempfile
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events

from .brain import Brain
from .config import ROOT
from .scheduler import Scheduler
from .store import Store

log = logging.getLogger(__name__)

HELP = """Men shaxsiy AI yordamchingizman. O'zbekcha yozing, ovozli xabar yuboring yoki qo'ng'iroq qiling.

/call — sizga qo'ng'iroq qilaman
/hangup — qo'ng'iroqni tugatish
/plans — ochiq rejalar
/reminders — eslatmalar
/status — holat
/help — yordam

Misol: «Ertaga 09:00 da dars qilishimni qo'ng'iroq qilib eslat.»
«Har kuni 20:30 da ingliz tilini o'rganishni eslat.»
«Rejamga kitob o'qishni qo'sh.»

Ovoz AI tomonidan yaratiladi. Suhbatning so'nggi matnlari shu kompyuterda saqlanadi; ovoz va matn OpenAI API ga yuboriladi.
Eslatish uchun dastur, kompyuter va internet ishlashi kerak."""


def is_owner(event, owner_id):
    return event.is_private and event.sender_id == owner_id and not event.out


class AgentApp:
    def __init__(self, settings):
        self.settings = settings
        (ROOT / "data").mkdir(exist_ok=True)
        self.store = Store(ROOT / "data" / "agent.sqlite3", settings.timezone)
        self.brain = Brain(settings, self.store)
        self.telegram = TelegramClient(
            str(ROOT / "data" / "assistant"), settings.api_id, settings.api_hash
        )
        self.calls = None
        self.voice = None
        self.call_lock = asyncio.Lock()
        self.message_lock = asyncio.Lock()
        self.call_task = None
        self.scheduler_task = None
        self.background_tasks = set()
        self.owner = None

    async def send_text(self, text):
        # Plain text prevents model-generated Markdown links from changing message meaning.
        for start in range(0, len(text), 3500):
            await self.telegram.send_message(
                self.owner, text[start : start + 3500], parse_mode=None
            )

    async def run(self):
        try:
            await self._run()
        finally:
            await self.telegram.disconnect()
            await self.brain.client.close()
            self.store.close()

    async def _run(self):
        # Import inside the running loop: PyTgCalls captures this loop in its sync wrappers.
        from pytgcalls import PyTgCalls, filters
        from pytgcalls.types import ChatUpdate, Device, Direction

        await self.telegram.connect()
        if not await self.telegram.is_user_authorized():
            raise ValueError("Telegram sessiya yo'q. Avval setup.ps1 orqali login qiling.")
        me = await self.telegram.get_me()
        if me.bot or me.id == self.settings.owner_id:
            raise ValueError("Yordamchi uchun siznikidan boshqa, oddiy Telegram akkaunti kerak.")
        self.owner = await self.telegram.get_input_entity(self.settings.owner_id)
        self.calls = PyTgCalls(self.telegram)
        self.telegram.add_event_handler(self.on_message, events.NewMessage(incoming=True))

        @self.calls.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def incoming(_, update):
            if update.chat_id != self.settings.owner_id:
                # Reject callers outside the configured owner's account.
                with suppress(Exception):
                    await self.calls.leave_call(update.chat_id)
                return
            self.spawn(self.safe_call("Salom! Men AI yordamchingizman. Suhbatni boshlang."))

        @self.calls.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def ended(_, update):
            if update.chat_id == self.settings.owner_id and self.voice:
                self.voice.closed.set()

        @self.calls.on_update(filters.stream_frame(Direction.INCOMING, Device.MICROPHONE))
        async def audio(_, update):
            if update.chat_id == self.settings.owner_id and self.voice:
                for frame in update.frames:
                    self.voice.accept_pcm48(frame.frame)

        try:
            await self.calls.start()
            scheduler = Scheduler(self.store, self.deliver, self.settings.reminder_grace_hours)
            self.scheduler_task = asyncio.create_task(scheduler.run())
            log.info("Agent started; owner allowlist active")
            print(
                "TelegramAgent ishlayapti. Yordamchi akkauntiga yozing yoki qo'ng'iroq qiling.",
                flush=True,
            )
            # A scheduler crash must not silently disable reminders while chat still works.
            disconnected = asyncio.ensure_future(self.telegram.disconnected)
            done, _ = await asyncio.wait(
                [self.scheduler_task, disconnected], return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
        finally:
            if self.scheduler_task:
                self.scheduler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.scheduler_task
            await self.hangup()
            for task in list(self.background_tasks):
                task.cancel()
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)

        def finished(done):
            self.background_tasks.discard(done)
            if not done.cancelled() and done.exception():
                log.warning("Background task failed type=%s", type(done.exception()).__name__)

        task.add_done_callback(finished)
        return task

    async def place_call(self, introduction):
        """Wait for connection, while the conversation continues independently of the scheduler."""
        ready = asyncio.get_running_loop().create_future()
        task = self.spawn(self.safe_call(introduction, ready))
        try:
            await ready
            return "call_connected"
        except asyncio.CancelledError:
            task.cancel()
            raise

    async def safe_call(self, introduction, ready=None):
        try:
            await self.conversation(introduction, ready)
        except Exception as exc:
            if ready is not None and not ready.done():
                ready.set_exception(ConnectionError("Call did not connect"))
            log.warning("Call failed type=%s", type(exc).__name__)
            await self.send_text(
                "Qo'ng'iroq ulanmagan yoki ovozli xizmatda xato bo'ldi. "
                "Yozishib davom etishingiz mumkin. /call — qayta urinish."
            )
        finally:
            if ready is not None and not ready.done():
                ready.set_exception(ConnectionError("Call ended before connection"))

    async def conversation(self, introduction, ready=None):
        from pytgcalls.types import CallConfig, Device, ExternalMedia, MediaStream, RecordStream
        from pytgcalls.types.raw import AudioParameters

        from .voice import VoiceSession

        if self.call_lock.locked():
            raise RuntimeError("Call already active")
        async with self.call_lock:
            self.call_task = asyncio.current_task()
            parameters = AudioParameters(bitrate=48000, channels=1)

            async def send(frame):
                await self.calls.send_frame(self.settings.owner_id, Device.MICROPHONE, frame)

            voice = VoiceSession(self.brain, send, introduction)
            try:
                # play() returns when the peer has answered and media is connected.
                async with asyncio.timeout(self.settings.ring_timeout_seconds + 45):
                    await self.calls.play(
                        self.settings.owner_id,
                        MediaStream(
                            ExternalMedia.AUDIO, parameters, video_flags=MediaStream.Flags.IGNORE
                        ),
                        config=CallConfig(timeout=self.settings.ring_timeout_seconds),
                    )
                    self.voice = voice
                    await self.calls.record(self.settings.owner_id, RecordStream(True, parameters))
                    await voice.start()
                if ready is not None and not ready.done():
                    ready.set_result(True)
                try:
                    await asyncio.wait_for(voice.closed.wait(), self.settings.max_call_seconds)
                except TimeoutError:
                    await self.send_text(
                        "Qo'ng'iroq vaqti chegarasiga yetdi. /call bilan davom eting."
                    )
                if voice.error:
                    raise RuntimeError("Voice stream failed")
                return "call_connected"
            finally:
                self.voice = None
                await voice.close()
                with suppress(Exception):
                    await self.calls.leave_call(self.settings.owner_id)
                self.call_task = None

    async def hangup(self):
        if self.voice:
            self.voice.closed.set()
        task = self.call_task
        if task and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

    async def deliver(self, row, late):
        when = datetime.fromisoformat(row["due"]).astimezone(ZoneInfo(self.settings.timezone))
        text = f"Eslatma #{row['id']}: {row['title']}\nVaqti: {when:%Y-%m-%d %H:%M}"
        if late:
            text += "\nDastur ishlamay turgani sabab bu eslatma kechikdi."
        # A durable chat copy is useful even when the owner answers the call.
        await self.send_text(text)
        if row["mode"] == "call" and not late and not self.call_lock.locked():
            try:
                return await self.place_call(
                    "O'zingizni AI yordamchi deb tanishtiring va mana bu eslatmani "
                    "foydalanuvchiga ayting. Keyin savollariga javob bering: " + text
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.info("Reminder call unavailable id=%s type=%s", row["id"], type(exc).__name__)
                await self.send_text(
                    "Eslatma qo'ng'irog'i ulanmagan. Yuqoridagi eslatma saqlanib qoldi."
                )
                return "message_fallback"
        return "late_message" if late else "message_sent"

    async def on_message(self, event):
        if not is_owner(event, self.settings.owner_id):
            return
        text = event.raw_text.strip()
        command = text.split(maxsplit=1)[0].lower() if text else ""
        # These controls remain responsive during a long model request.
        if command == "/hangup":
            await self.hangup()
            await self.send_text("Qo'ng'iroq tugatildi.")
            return
        if command == "/call":
            if self.call_lock.locked():
                await self.send_text("Qo'ng'iroq allaqachon faol.")
            else:
                self.spawn(self.safe_call("Salom! Men AI yordamchingizman. Qanday yordam beray?"))
            return
        if command in {"/help", "/start"}:
            await self.send_text(HELP)
            return
        if command == "/status":
            await self.send_text(
                f"Agent ishlayapti. Zona: {self.settings.timezone}. "
                f"Qo'ng'iroq: {'faol' if self.call_lock.locked() else 'bo‘sh'}. "
                f"Eslatmalar: {len(self.store.list_reminders())}. "
                f"Rejalar: {len(self.store.list_plans())}."
            )
            return
        if command == "/plans":
            rows = self.store.list_plans()
            await self.send_text(
                "\n".join(f"#{r['id']} {r['title']} — {r['details']}" for r in rows)
                or "Ochiq reja yo'q."
            )
            return
        if command == "/reminders":
            rows = self.store.list_reminders()
            await self.send_text(
                "\n".join(
                    f"#{r['id']} {r['title']} — {r['due_local']} ({r['repeat']}, {r['mode']})"
                    for r in rows
                )
                or "Kutilayotgan eslatma yo'q."
            )
            return
        if self.message_lock.locked():
            await self.send_text("Oldingi xabaringizni ko'rib chiqyapman. Birozdan keyin yuboring.")
            return
        async with self.message_lock:
            try:
                if event.message.voice:
                    if (event.message.file.size or 0) > 20 * 1024 * 1024:
                        await self.send_text("Ovozli xabar 20 MB dan kichik bo'lishi kerak.")
                        return
                    with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="voice-") as folder:
                        path = Path(
                            await event.message.download_media(file=str(Path(folder) / "in.ogg"))
                        )
                        text = await self.brain.transcribe(path)
                        if not text.strip():
                            await self.send_text("Ovozni tushunmadim. Qayta yuboring.")
                            return
                        await self.send_text("Eshitdim: " + text)
                        reply = await self.brain.answer(text)
                        await self.send_text(reply)
                        try:
                            out = Path(folder) / "reply.ogg"
                            await self.brain.speech(reply, out)
                            await self.telegram.send_file(self.owner, out, voice_note=True)
                        except Exception as exc:
                            log.info("Voice note synthesis failed type=%s", type(exc).__name__)
                elif text:
                    await self.send_text(await self.brain.answer(text[:12000]))
                else:
                    await self.send_text("Matn yoki ovozli xabar yuboring. /help — yordam.")
            except Exception as exc:
                log.warning("Message handling failed type=%s", type(exc).__name__)
                await self.send_text(
                    "So'rovni yakunlay olmadim. /reminders va /plans bilan "
                    "saqlangan amallarni tekshiring, keyin qayta urinib ko'ring."
                )
