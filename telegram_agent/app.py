import asyncio
import json
import logging
import tempfile
import unicodedata
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import APIError
from telethon import TelegramClient, events
from telethon.errors import RandomIdDuplicateError
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import UpdatePhoneCall, UpdatePhoneCallSignalingData

from .ai_access import AIUnavailable, public_ai_error
from .brain import Brain
from .config import ROOT
from .owner_setup import configured_owner
from .scheduler import Scheduler
from .store import Store, utc_now
from .telegram_health import ensure_telegram_account
from .telegram_policy import TelegramPaused, TelegramPolicy

log = logging.getLogger(__name__)

HELP = """Men shaxsiy AI yordamchingizman. O'zbekcha yozing, ovozli xabar yuboring yoki qo'ng'iroq qiling.

/call — sizga qo'ng'iroq qilaman
/hangup — qo'ng'iroqni tugatish
/plans — ochiq rejalar
/bugun — kunlik ishlar va e'tibor talab qiladigan vazifalar
/qidir MATN — saqlangan ma'lumotlardan qidirish
/bajarildi ID — rejani bajarildi deb belgilash
/reminders — eslatmalar
/keyin ID 15 daqiqa — xabar bilan keyinroq yana eslatish
/reja Kitob o'qish — AI so'rovisiz reja saqlash
/eslatma Suv ichish | 15 daqiqa — o'zingizga vaqtli Telegram xabari
/xabar Matn — o'zingizga yuboriladigan xabar vaqtini alohida kiritish
/bekor — tugallanmagan eslatmani bekor qilish
/contacts — ulashilgan kontaktlar
/callto en @username | xabar — tanlangan tilda aytish
/sendto @username | xabar — Telegram orqali matn yuborish
/askto en @username | savol — javob olib kelish
/recordto en @username | English question — asl ovoz, AI tokensiz
/voicecall @username — o'z golosingizga reply qilib, qo'ng'iroqda eshittirish
/voiceask @username — o'z golosingizni eshittirib javobini yozib olish
/voicesend @username — o'z golosingizga reply qilib, chatga yuborish
/talkto en @username | vazifa — qisqa suhbat
/contacts ism — kontaktlardan qidirish
/calls — topshirilgan qo'ng'iroqlar holati
/cancelcall ID — navbatdagi qo'ng'iroqni bekor qilish
/status — holat
/limits — qo'ng'iroq urinishlari va kutish vaqti
/usage — bugungi AI so'rovlari, token sarfi va kutish vaqti
/help — yordam

Misol: «Ertaga 09:00 da dars qilishimni qo'ng'iroq qilib eslat.»
«Har kuni 20:30 da ingliz tilini o'rganishni eslat.»
«Rejamga kitob o'qishni qo'sh.»

Ovoz AI tomonidan yaratiladi. Suhbatning so'nggi matnlari shu kompyuterda saqlanadi. Matn tanlangan Gemini/OpenAI xizmatiga yuboriladi. Bepul ovoz rejimida qisqa nutq Gemini orqali taniladi; kvotada mahalliy Whisper ishlaydi. Asl ovoz yozuvi egasiga yuboriladi. Javob matni Edge ovoz xizmatiga yuboriladi; OpenAI rejimida ovoz OpenAI ga yuboriladi.
Eslatish uchun dastur, kompyuter va internet ishlashi kerak."""


def is_owner(event, owner_id):
    return event.is_private and event.sender_id == owner_id and not event.out


class AgentApp:
    def __init__(self, settings):
        self.settings = settings
        (ROOT / "data").mkdir(exist_ok=True)
        self.store = Store(ROOT / "data" / "agent.sqlite3", settings.timezone)
        self.brain = Brain(settings, self.store)
        self.brain.private_delivery = self.send_text
        self.policy = TelegramPolicy(settings, self.store)
        self.telegram = TelegramClient(
            str(ROOT / "data" / "assistant"),
            settings.api_id,
            settings.api_hash,
            request_retries=0,
            flood_sleep_threshold=0,
        )
        from .call_signals import forward_exported_updates

        forward_exported_updates(
            self.telegram,
            lambda dc: (
                self.call_signals.exported(dc) if getattr(self, "call_signals", None) else None
            ),
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
        self.relay_voice = None
        self.active_recording = None

    async def send_text(self, text, *, random_id=None):
        if random_id is not None:
            request = SendMessageRequest(self.owner, text, random_id=random_id)
            # A previous delivery may have reached Telegram before our local commit.
            with suppress(RandomIdDuplicateError):
                await self.policy.send(lambda: self.telegram(request))
            return
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
            self.ready.clear()
            if self.calls is not None:
                with suppress(Exception):
                    await self.calls.stop()
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
        from .contact_sync import telegram_contacts

        self.store.import_contacts(
            await self.policy.action(lambda: telegram_contacts(self.telegram, me.id)),
            "helper-telegram",
        )
        from .contact_calls import RecipientResolver, run_queue

        self.recipient_resolver = RecipientResolver(self.telegram, self.store, me.id)
        self.brain.contact_request = self.queue_requested_call
        self.telegram.add_event_handler(self.on_message, events.NewMessage(incoming=True))

        try:
            if self.settings.enable_voice_calls:
                await self._start_call_transport(me.id)
            scheduler = Scheduler(self.store, self.deliver, self.settings.reminder_grace_hours)
            self.store.recover_reminders(all_inflight=True)
            self.scheduler_task = asyncio.create_task(scheduler.run())
            from .recordings import run_recordings

            recordings_task = asyncio.create_task(run_recordings(self))
            from .notifications import run_notifications

            notifications_task = asyncio.create_task(run_notifications(self))
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
                        recordings_task,
                        notifications_task,
                        disconnected,
                        restricted,
                    ]
                    if task is not None
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                try:
                    task.result()
                except TelegramPaused:
                    raise
                except Exception as exc:
                    raise ConnectionError(
                        "Yetkazish jarayoni uzildi: " + type(exc).__name__
                    ) from None
            if restricted in done:
                raise TelegramPaused(self.policy.reason)
            raise ConnectionError("Telegram ulanishi yoki yetkazish jarayoni to'xtadi.")
        finally:
            workers = [
                task for task in [self.scheduler_task, self.contact_queue_task] if task is not None
            ]
            if "restricted" in locals():
                workers.append(restricted)
            for name in ("recordings_task", "notifications_task"):
                if name in locals():
                    workers.append(locals()[name])
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

        from .call_signals import CallSignals, trace_phone_rpc

        self.call_signals = CallSignals(own_id)
        # Observe before the bridge, so an adapter failure cannot hide acceptance.
        self.telegram.add_event_handler(
            self.call_signals.observe,
            events.Raw(types=(UpdatePhoneCall, UpdatePhoneCallSignalingData)),
        )

        self.calls = PyTgCalls(self.telegram)
        trace_phone_rpc(self.calls, self.call_signals)

        @self.calls.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def incoming(_, update):
            await self.on_incoming_call(update.chat_id)

        @self.calls.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def ended(_, update):
            if update.chat_id == self.settings.owner_id and self.voice:
                if hasattr(self.voice, "remote_end"):
                    self.voice.remote_end()
                else:
                    self.voice.closed.set()
            if update.chat_id == self.relay_target and self.relay_ended:
                self.relay_ended.set()
                if self.relay_voice:
                    self.relay_voice.remote_end()

        @self.calls.on_update(filters.stream_frame(Direction.INCOMING, Device.MICROPHONE))
        async def audio(_, update):
            self.receive_audio(update)

        await self.calls.start()

    def call_event(self, status):
        self.store.set_telegram_state(
            "last_call_event", json.dumps({"status": status, "at": utc_now().isoformat()})
        )

    async def on_incoming_call(self, chat_id):
        if chat_id != self.settings.owner_id or self.call_lock.locked():
            self.call_event(
                "other_account_rejected" if chat_id != self.settings.owner_id else "busy"
            )
            with suppress(Exception):
                await self.calls.leave_call(chat_id)
            return
        self.call_event("incoming_received")
        self.spawn(self.safe_call("Salom, eshitaman."))

    def receive_audio(self, update):
        signals = getattr(self, "call_signals", None)
        if signals is not None and signals.peer_id == update.chat_id:
            if not signals.metrics.get("incoming_packets"):
                signals.mark("first_incoming_packet")
            signals.metrics["incoming_packets"] = signals.metrics.get("incoming_packets", 0) + len(
                update.frames
            )
        recording = getattr(self, "active_recording", None)
        if recording is not None and update.chat_id == recording.peer_id:
            recording.write("incoming", b"".join(frame.frame for frame in update.frames))
        voice = (
            self.voice
            if update.chat_id == self.settings.owner_id
            else self.relay_voice
            if update.chat_id == self.relay_target
            else None
        )
        if voice:
            for frame in update.frames:
                voice.accept_pcm48(frame.frame)

    async def queue_requested_call(self, target, message, *, expected_recipient_id=None, **options):
        from dataclasses import replace

        options.setdefault("fallback_to_message", True)
        user = await self.policy.action(lambda: self.recipient_resolver.resolve(target))
        if expected_recipient_id is not None and user.id != expected_recipient_id:
            raise ValueError("Kontaktning Telegram akkaunti o'zgargan. Uni qayta tekshiring.")
        if user.id == self.settings.owner_id:
            raise ValueError("O'zingizga qo'ng'iroq qilish uchun /call ishlating.")
        reference = "@" + user.username if user.username else target
        name = " ".join(filter(None, (user.first_name, user.last_name))) or reference
        self.store.save_contact(name, reference)
        row = next(c for c in self.store.list_contacts() if c["reference"] == reference)
        self.store.set_contact_permission(row["id"], user.id, True)
        self.settings = replace(
            self.settings,
            enable_contact_calls=True,
            allowed_call_user_ids=tuple(
                dict.fromkeys((*self.settings.allowed_call_user_ids, user.id))
            ),
        )
        self.policy.settings = self.brain.settings = self.settings
        return self.store.queue_contact_call(
            reference,
            message,
            recipient_user_id=user.id,
            call_limits=(self.settings.call_cooldown_seconds, self.settings.max_calls_per_hour),
            **options,
        )

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
            self.call_event("connecting")
            await self.conversation(introduction, ready)
        except Exception as exc:
            self.call_event("failed:" + type(exc).__name__)
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
            from .recordings import begin_recording, end_recording

            recording = None

            async def send(frame):
                await self.calls.send_frame(self.settings.owner_id, Device.MICROPHONE, frame)
                if signals and any(frame) and not metrics.get("first_outgoing_audio"):
                    metrics["first_outgoing_audio"] = True
                    signals.mark("first_outgoing_audio")
                if recording is not None:
                    recording.write("outgoing", frame)

            voice = VoiceSession(self.brain, send, introduction)
            signals = getattr(self, "call_signals", None)
            metrics = getattr(voice, "metrics", {})
            if signals:
                signals.begin(self.settings.owner_id, metrics)
            try:
                if self.settings.voice_provider == "free":
                    await voice.prepare_introduction()
                if self.settings.voice_provider == "free" and not self.brain.use_native_asr:
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
                    metrics["connected"] = True
                    if signals:
                        signals.mark("media_connected")
                    recording = begin_recording(
                        self, self.settings.owner_id, "Yordamchi bilan suhbat"
                    )
                    metrics["recording_started"] = recording is not None
                    self.voice = voice
                    await self.calls.record(self.settings.owner_id, RecordStream(True, parameters))
                    await voice.start()
                    self.call_event("connected")
                if ready is not None and not ready.done():
                    ready.set_result(True)
                try:
                    await asyncio.wait_for(voice.closed.wait(), self.settings.max_call_seconds)
                except TimeoutError:
                    if hasattr(voice, "finish_input"):
                        await voice.finish_input()
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
                end_recording(self, recording)
                if signals:
                    signals.end()
                    self.store.set_telegram_state(
                        "last_call_transport", json.dumps(signals.snapshot(), ensure_ascii=False)
                    )
                self.call_task = None
                self.call_event("ended")

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
        text += f"\nKeyinroq eslatish uchun /keyin {row['id']} 15 daqiqa"
        if late:
            text += "\nDastur ishlamay turgani sabab bu eslatma kechikdi."
        if row.get("recovery_message_only"):
            text += "\nTiklash rejimi: eslatma xabar bilan yetkazildi. Qayta qo'ng'iroq qilinmadi."
        # A durable chat copy is useful even when the owner answers the call.
        if not row.get("message_confirmed"):
            if random_id := row.get("message_random_id"):
                await self.send_text(text, random_id=random_id)
                if not self.store.confirm_reminder_message(row):
                    return "claim_released"
            else:
                await self.send_text(text)
        if (
            self.settings.enable_voice_calls
            and row["mode"] == "call"
            and not row.get("recovery_message_only")
            and not late
            and not self.call_lock.locked()
        ):
            try:
                return await self.place_call(
                    "Salom! Men AI yordamchingizman. " + text + ". Savolingiz bo'lsa, ayting."
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.info("Reminder call unavailable id=%s type=%s", row["id"], type(exc).__name__)
                # The reminder already reached Telegram. An optional status message
                # must not make the scheduler send the same reminder again.
                try:
                    await self.send_text(
                        "Eslatma qo'ng'irog'i ulanmagan. Yuqoridagi eslatma saqlanib qoldi."
                    )
                except Exception as notice_error:
                    log.warning(
                        "Reminder call status unavailable id=%s type=%s",
                        row["id"],
                        type(notice_error).__name__,
                    )
                return "message_fallback"
        return "late_message" if late else "message_sent"

    async def on_message(self, event):
        if not is_owner(event, self.settings.owner_id):
            if (
                getattr(event, "is_private", False)
                and not getattr(event, "out", True)
                and getattr(event, "sender_id", None) in self.settings.allowed_call_user_ids
                and getattr(event, "reply_to_msg_id", None)
                and getattr(event, "raw_text", "").strip()
            ):
                self.store.capture_contact_text_reply(
                    event.sender_id,
                    event.reply_to_msg_id,
                    event.id,
                    event.raw_text.strip(),
                    self.settings.owner_id,
                )
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
                self.spawn(self.safe_call("Salom, eshitaman."))
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
            budget = self.store.call_budget(
                self.settings.call_cooldown_seconds, self.settings.max_calls_per_hour
            )
            await self.send_text(
                f"Agent ishlayapti. Zona: {self.settings.timezone}. "
                f"Qo'ng'iroq: {'faol' if self.call_lock.locked() else 'bo‘sh'}. "
                f"Eslatmalar: {len(self.store.list_reminders())}. "
                f"Rejalar: {len(self.store.list_plans())}. "
                f"Matn AI: {self.settings.resolved_text_provider}. "
                f"Ovoz xizmati: {self.settings.voice_provider}. "
                f"Ovozli qo'ng'iroq: {'yoqilgan' if self.settings.enable_voice_calls else 'o‘chirilgan'}. "
                f"Kontaktlarga qo'ng'iroq: {'yoqilgan' if self.settings.enable_contact_calls else 'o‘chirilgan'}.\n"
                + budget["text"]
            )
            return
        if command in {"/voicecall", "/voiceask", "/voicesend"}:
            try:
                from .voice_library import MAX_UPLOAD, save_upload

                target = text[len(command) :].strip()
                language = "uz"
                if target.split(maxsplit=1)[:1] and target.split(maxsplit=1)[0] in {
                    "uz",
                    "en",
                    "ru",
                }:
                    language, target = target.split(maxsplit=1)
                if not target:
                    raise ValueError("O'z golosingizga reply qilib /voiceask @username yuboring.")
                message = await event.get_reply_message()
                if not message or not message.voice or message.sender_id != self.settings.owner_id:
                    raise ValueError("O'zingiz yuborgan golosga reply qiling va kontaktni yozing.")
                if (message.file.size or 0) > MAX_UPLOAD:
                    raise ValueError("Golos 12 MB dan kichik bo'lsin.")
                payload = await self.policy.action(lambda: message.download_media(file=bytes))
                asset = await save_upload(self.store, payload, "Telegramdan olingan ovozim")
                result = await self.queue_requested_call(
                    target,
                    "Asl ovozli xabar",
                    mode="voice",
                    audio_id=asset["id"],
                    delivery="message" if command == "/voicesend" else "call",
                    collect_reply=command == "/voiceask",
                    language=language,
                )
                await self.send_text(
                    f"Vazifa #{result['id']} navbatga saqlandi. Asl ovozingiz ishlatiladi; hali yetkazilmadi."
                )
            except (ValueError, TypeError) as exc:
                await self.send_text(str(exc))
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
                    f"#{r['id']} {r['title']} — {r['due_local']} ({r['repeat']}, {r['mode']}, {r['state']})"
                    for r in rows
                )
                or "Kutilayotgan eslatma yo'q."
            )
            return
        if command == "/contacts":
            query = text[len(command) :].strip()
            contacts = (
                self.store.search_contacts(query) if query else self.store.list_contacts()[:50]
            )
            await self.send_text(
                "\n".join(f"{row['name']} — {row['reference']}" for row in contacts)
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
        if command in {"/callto", "/askto", "/talkto", "/recordto", "/sendto", "/cancelcall"}:
            try:
                arguments = text[len(command) :].strip()
                if command in {"/callto", "/askto", "/talkto", "/recordto", "/sendto"}:
                    target, separator, message = arguments.partition("|")
                    if not separator:
                        raise ValueError(
                            "Misol: /callto @username | Bugun soat 18:00 da uchrashamiz."
                        )
                    if not target.strip() or not message.strip():
                        raise ValueError("Kontakt va savol/xabarni kiriting.")
                    language = "uz"
                    if target.split(maxsplit=1)[0].strip() in {"uz", "en", "ru"}:
                        language, target = target.strip().split(maxsplit=1)
                    result = await self.queue_requested_call(
                        target.strip(),
                        message.strip(),
                        mode={
                            "/callto": "relay",
                            "/askto": "ask",
                            "/talkto": "conversation",
                            "/recordto": "record",
                            "/sendto": "text",
                        }[command],
                        language=language,
                    )
                    await self.send_text(
                        Brain.write_reply("queue_contact_call", {"ok": True, "result": result})
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
        if getattr(self, "pending_messages", 0) >= 4:
            await self.send_text(
                "Navbatda 4 ta xabar bor. Bu xabar qabul qilinmadi; birozdan keyin yuboring."
            )
            return
        self.pending_messages = getattr(self, "pending_messages", 0) + 1
        try:
            async with self.message_lock:
                await self.process_message(event, text)
        finally:
            self.pending_messages -= 1

    async def process_message(self, event, text):
        try:
            if event.message.voice:
                if (event.message.file.size or 0) > 20 * 1024 * 1024:
                    await self.send_text("Ovozli xabar 20 MB dan kichik bo'lishi kerak.")
                    return
                with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="voice-") as folder:
                    path = Path(
                        await self.policy.action(
                            lambda: event.message.download_media(file=str(Path(folder) / "in.ogg"))
                        )
                    )
                    text = await self.brain.transcribe(path)
                    if not text.strip():
                        await self.send_text("Ovozni tushunmadim. Qayta yuboring.")
                        return
                    await self.send_text("Eshitdim: " + text)
                    reply = await self.brain.answer(text)
                    await self.send_text(reply)
                    from .documents import PrivateReply

                    if isinstance(reply, PrivateReply):
                        return
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
