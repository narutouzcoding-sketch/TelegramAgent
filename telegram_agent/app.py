import asyncio
import logging
import tempfile
import unicodedata
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import APIError
from telethon import TelegramClient, events

from .ai_access import AIUnavailable, public_ai_error
from .brain import Brain
from .config import ROOT
from .owner_setup import configured_owner
from .scheduler import Scheduler
from .store import Store
from .telegram_health import ensure_telegram_account
from .telegram_policy import TelegramPaused, TelegramPolicy

log = logging.getLogger(__name__)

HELP = """Men shaxsiy AI yordamchingizman. O'zbekcha yozing, ovozli xabar yuboring yoki qo'ng'iroq qiling.

/call — sizga qo'ng'iroq qilaman
/hangup — qo'ng'iroqni tugatish
/plans — ochiq rejalar
/reminders — eslatmalar
/contacts — ulashilgan kontaktlar
/callto @username | aytiladigan gap — kontaktga qo'ng'iroq
/calls — topshirilgan qo'ng'iroqlar holati
/cancelcall ID — navbatdagi qo'ng'iroqni bekor qilish
/status — holat
/help — yordam

Misol: «Ertaga 09:00 da dars qilishimni qo'ng'iroq qilib eslat.»
«Har kuni 20:30 da ingliz tilini o'rganishni eslat.»
«Rejamga kitob o'qishni qo'sh.»

Ovoz AI tomonidan yaratiladi. Suhbatning so'nggi matnlari shu kompyuterda saqlanadi. Matn tanlangan Gemini/OpenAI xizmatiga yuboriladi. Bepul rejimda ovoz shu kompyuterda taniladi, javob matni Edge ovoz xizmatiga yuboriladi; OpenAI rejimida ovoz OpenAI ga yuboriladi.
Eslatish uchun dastur, kompyuter va internet ishlashi kerak."""


def is_owner(event, owner_id):
    return event.is_private and event.sender_id == owner_id and not event.out


class AgentApp:
    def __init__(self, settings):
        self.settings = settings
        (ROOT / "data").mkdir(exist_ok=True)
        self.store = Store(ROOT / "data" / "agent.sqlite3", settings.timezone)
        self.brain = Brain(settings, self.store)
        self.policy = TelegramPolicy(settings, self.store)
        self.telegram = TelegramClient(
            str(ROOT / "data" / "assistant"),
            settings.api_id,
            settings.api_hash,
            request_retries=0,
            flood_sleep_threshold=0,
        )
        self.calls = None
        self.voice = None
        self.call_lock = asyncio.Lock()
        self.message_lock = asyncio.Lock()
        self.call_task = None
        self.scheduler_task = None
        self.contact_queue_task = None
        self.contact_job_task = None
        self.contact_job_id = None
        self.background_tasks = set()
        self.owner = None
        self.ready = asyncio.Event()
        self.owner_name = "foydalanuvchi"
        self.recipient_resolver = None
        self.relay_target = None
        self.relay_ended = None

    async def send_text(self, text):
        # Plain text prevents model-generated Markdown links from changing message meaning.
        for start in range(0, len(text), 3500):
            chunk = text[start : start + 3500]
            await self.policy.send(
                lambda: self.telegram.send_message(self.owner, chunk, parse_mode=None)
            )

    async def run(self):
        try:
            self.policy.ensure_active()
            await self._run()
        finally:
            await self.telegram.disconnect()
            await self.brain.close()
            self.store.close()

    async def _run(self):
        self.ready = asyncio.Event()
        await self.telegram.connect()
        me = await self.policy.action(
            lambda: ensure_telegram_account(self.telegram, self.settings.timezone)
        )
        if me.bot or me.id == self.settings.owner_id:
            raise ValueError("Yordamchi uchun siznikidan boshqa, oddiy Telegram akkaunti kerak.")
        owner_user = await self.policy.action(
            lambda: configured_owner(
                self.telegram, me.id, self.settings.owner_username, str(self.settings.owner_id)
            )
        )
        if owner_user is None or owner_user.id != self.settings.owner_id:
            raise ValueError(
                "Asosiy boshqaruvchi akkaunt topilmadi yoki username/ID mos emas. login.ps1 orqali qayta ulang; sessiya o'chirilmaydi."
            )
        self.owner = await self.telegram.get_input_entity(owner_user)
        self.owner_name = unicodedata.normalize("NFKC", owner_user.first_name or "foydalanuvchi")
        from .contact_calls import run_queue

        self.telegram.add_event_handler(self.on_message, events.NewMessage(incoming=True))

        try:
            if self.settings.enable_voice_calls:
                await self._start_call_transport(me.id)
            scheduler = Scheduler(self.store, self.deliver, self.settings.reminder_grace_hours)
            self.scheduler_task = asyncio.create_task(scheduler.run())
            if self.settings.enable_voice_calls:
                self.contact_queue_task = asyncio.create_task(run_queue(self))
            log.info("Agent started; owner allowlist active")
            self.ready.set()
            print(
                "TelegramAgent ishlayapti. "
                + (
                    "Ovozli rejim yoqilgan."
                    if self.settings.enable_voice_calls
                    else "Hozir faqat egasi bilan matnli rejim; qo'ng'iroqlar o'chirilgan."
                ),
                flush=True,
            )
            # A scheduler crash must not silently disable reminders while chat still works.
            disconnected = asyncio.ensure_future(self.telegram.disconnected)
            restricted = asyncio.create_task(self.policy.stopped.wait())
            done, _ = await asyncio.wait(
                [
                    task
                    for task in [
                        self.scheduler_task,
                        self.contact_queue_task,
                        disconnected,
                        restricted,
                    ]
                    if task is not None
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
            if restricted in done:
                raise TelegramPaused(self.policy.reason)
        finally:
            workers = [
                task for task in [self.scheduler_task, self.contact_queue_task] if task is not None
            ]
            if "restricted" in locals():
                workers.append(restricted)
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            await self.hangup()
            for task in list(self.background_tasks):
                task.cancel()
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

    async def _start_call_transport(self, own_id):
        from pytgcalls import PyTgCalls, filters
        from pytgcalls.types import ChatUpdate, Device, Direction

        from .contact_calls import RecipientResolver

        self.recipient_resolver = RecipientResolver(self.telegram, self.store, own_id)
        self.calls = PyTgCalls(self.telegram)

        @self.calls.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def incoming(_, update):
            if update.chat_id != self.settings.owner_id or self.call_lock.locked():
                with suppress(Exception):
                    await self.calls.leave_call(update.chat_id)
                return
            self.spawn(self.safe_call("Salom! Men AI yordamchingizman. Suhbatni boshlang."))

        @self.calls.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def ended(_, update):
            if update.chat_id == self.settings.owner_id and self.voice:
                self.voice.closed.set()
            if update.chat_id == self.relay_target and self.relay_ended:
                self.relay_ended.set()

        @self.calls.on_update(filters.stream_frame(Direction.INCOMING, Device.MICROPHONE))
        async def audio(_, update):
            if update.chat_id == self.settings.owner_id and self.voice:
                for frame in update.frames:
                    self.voice.accept_pcm48(frame.frame)

        await self.calls.start()

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
                (
                    public_ai_error(exc)
                    if isinstance(exc, (APIError, AIUnavailable))
                    else str(exc)
                    if isinstance(exc, TelegramPaused)
                    else "Qo'ng'iroq ulanmagan yoki ovozli xizmatda xato bo'ldi. "
                )
                + " "
                "Yozishib davom etishingiz mumkin. /call — qayta urinish."
            )
        finally:
            if ready is not None and not ready.done():
                ready.set_exception(ConnectionError("Call ended before connection"))

    async def conversation(self, introduction, ready=None):
        if not self.settings.enable_voice_calls:
            raise TelegramPaused(
                "Ovozli qo'ng'iroqlar hozir o'chirilgan. Avval matnli sinov va AI billing tekshiruvi yakunlanadi."
            )
        if self.settings.voice_provider == "openai" and not self.settings.openai_key:
            raise AIUnavailable(
                "Jonli ovozli qo'ng'iroq uchun OPENAI_API_KEY kerak. Gemini matnli suhbat va rejalarga ulangan."
            )
        from pytgcalls.types import CallConfig, Device, ExternalMedia, MediaStream, RecordStream
        from pytgcalls.types.raw import AudioParameters

        if self.settings.voice_provider == "free":
            from .free_voice import FreeVoiceSession as VoiceSession
        else:
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
                if self.settings.voice_provider == "free":
                    await self.brain.free_speech.prepare()
                # play() returns when the peer has answered and media is connected.
                async with asyncio.timeout(self.settings.ring_timeout_seconds + 45):
                    await self.policy.dial(
                        self.settings.owner_id,
                        lambda: self.calls.play(
                            self.settings.owner_id,
                            MediaStream(
                                ExternalMedia.AUDIO,
                                parameters,
                                video_flags=MediaStream.Flags.IGNORE,
                            ),
                            config=CallConfig(timeout=self.settings.ring_timeout_seconds),
                        ),
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
                    raise AIUnavailable(voice.error)
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
        task = self.call_task or getattr(self, "contact_job_task", None)
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
        if (
            self.settings.enable_voice_calls
            and row["mode"] == "call"
            and not late
            and not self.call_lock.locked()
        ):
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
            if not self.settings.enable_voice_calls:
                await self.send_text(
                    "Ovozli qo'ng'iroqlar hozir o'chirilgan. Matnli suhbat, rejalar va eslatmalar ishlaydi."
                )
                return
            if self.call_lock.locked():
                await self.send_text("Qo'ng'iroq allaqachon faol.")
            else:
                self.spawn(self.safe_call("Salom! Men AI yordamchingizman. Qanday yordam beray?"))
            return
        if command in {"/help", "/start"}:
            await self.send_text(
                (
                    "Hozir qo'ng'iroqlar o'chirilgan; eslatmalar matn bilan yuboriladi.\n\n"
                    if not self.settings.enable_voice_calls
                    else ""
                )
                + HELP
            )
            return
        if command == "/status":
            await self.send_text(
                f"Agent ishlayapti. Zona: {self.settings.timezone}. "
                f"Qo'ng'iroq: {'faol' if self.call_lock.locked() else 'bo‘sh'}. "
                f"Eslatmalar: {len(self.store.list_reminders())}. "
                f"Rejalar: {len(self.store.list_plans())}. "
                f"Matn AI: {self.settings.resolved_text_provider}. "
                f"Ovoz xizmati: {self.settings.voice_provider}. "
                f"Ovozli qo'ng'iroq: {'yoqilgan' if self.settings.enable_voice_calls else 'o‘chirilgan'}. "
                f"Kontaktlarga qo'ng'iroq: {'yoqilgan' if self.settings.enable_contact_calls else 'o‘chirilgan'}."
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
        if command == "/contacts":
            await self.send_text(
                "\n".join(
                    f"{row['name']} — {row['reference']}" for row in self.store.list_contacts()
                )
                or "Kontaktlar yo'q. Telegram orqali kontaktni menga ulashing yoki @username bering."
            )
            return
        if command == "/calls":
            await self.send_text(
                "\n".join(
                    f"#{row['id']} {row['target']} — {row['state']}: {row['result'] or row['message']}"
                    for row in self.store.list_contact_calls()
                )
                or "Qo'ng'iroq topshiriqlari yo'q."
            )
            return
        if command in {"/callto", "/cancelcall"}:
            try:
                arguments = text[len(command) :].strip()
                if command == "/callto":
                    if (
                        not self.settings.enable_voice_calls
                        or not self.settings.enable_contact_calls
                        or not self.settings.allowed_call_user_ids
                    ):
                        raise ValueError(
                            "Kontaktlarga qo'ng'iroq hozir o'chirilgan. Avval faqat egasi bilan sinov qilinadi."
                        )
                    target, separator, message = arguments.partition("|")
                    if not separator:
                        raise ValueError(
                            "Misol: /callto @username | Bugun soat 18:00 da uchrashamiz."
                        )
                    result = self.store.queue_contact_call(target, message)
                    await self.send_text(
                        f"Qo'ng'iroq #{result['id']} navbatga qo'yildi: "
                        f"{result['target']}\nAytiladi: {result['message']}\n"
                        "Faol suhbat tugagach bajariladi. /calls — holat."
                    )
                else:
                    job_id = int(arguments)
                    result = self.store.cancel_contact_call(job_id)
                    if (
                        not result["cancelled"]
                        and job_id == self.contact_job_id
                        and self.contact_job_task
                    ):
                        self.contact_job_task.cancel()
                        await asyncio.gather(self.contact_job_task, return_exceptions=True)
                        result["cancelled"] = True
                    await self.send_text(
                        "Navbatdagi qo'ng'iroq bekor qilindi."
                        if result["cancelled"]
                        else "Kutilayotgan ID topilmadi. Faol qo'ng'iroq uchun /hangup."
                    )
            except ValueError as exc:
                await self.send_text(str(exc))
            return
        contact = getattr(event.message, "contact", None)
        if contact:
            from .setup_inputs import international_phone

            try:
                number = contact.phone_number
                if not number.startswith("+"):
                    if len(number) < 10:
                        raise ValueError(
                            "Kontakt raqamida mamlakat kodi yetishmayapti. To'liq +raqam yoki @username bering."
                        )
                    number = "+" + number
                number = international_phone(number)
                name = " ".join(filter(None, [contact.first_name, contact.last_name]))
                self.store.save_contact(name or number, number)
                await self.send_text(
                    f"Kontakt saqlandi: {name or number}. "
                    "Endi unga qanday gapni yetkazishni ayting."
                )
            except ValueError as exc:
                await self.send_text(str(exc))
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
                            await self.policy.action(
                                lambda: event.message.download_media(
                                    file=str(Path(folder) / "in.ogg")
                                )
                            )
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
                            await self.policy.send(
                                lambda: self.telegram.send_file(self.owner, out, voice_note=True)
                            )
                        except Exception as exc:
                            log.info("Voice note synthesis failed type=%s", type(exc).__name__)
                elif text:
                    await self.send_text(await self.brain.answer(text[:12000]))
                else:
                    await self.send_text("Matn yoki ovozli xabar yuboring. /help — yordam.")
            except Exception as exc:
                log.warning("Message handling failed type=%s", type(exc).__name__)
                await self.send_text(
                    (
                        public_ai_error(exc)
                        if isinstance(exc, (APIError, AIUnavailable))
                        else "So'rovni yakunlay olmadim."
                    )
                    + " /reminders va /plans bilan "
                    "saqlangan amallarni tekshiring, keyin qayta urinib ko'ring."
                )
