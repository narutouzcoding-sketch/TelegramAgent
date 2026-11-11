"""Pace legitimate user-requested actions and stop on Telegram restrictions."""

import asyncio
from datetime import datetime, timedelta

from telethon import errors

from .store import utc_now


class TelegramPaused(ValueError):
    """A local pause or server restriction, with no automatic retry."""


class CallRateLimited(TelegramPaused):
    """The local budget blocked this request before Telegram dialing."""


class TelegramPolicy:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.send_lock = asyncio.Lock()
        self.last_send = None
        self.stopped = asyncio.Event()
        self.reason = ""

    def ensure_active(self):
        if self.stopped.is_set():
            raise TelegramPaused(self.reason)
        restriction = self.store.telegram_state("restriction_latch")
        if restriction:
            raise TelegramPaused(
                "Telegram cheklovi saqlangan. Akkauntni tekshirib, paneldagi qayta tekshirish orqali davom eting; avtomatik urinish yuborilmadi."
            )
        value = self.store.telegram_state("pause_until")
        if value and datetime.fromisoformat(value) > utc_now():
            raise TelegramPaused(
                "Telegram talab qilgan kutish muddati tugamagan. Keyinroq ishga tushiring; qayta urinish yuborilmadi."
            )

    def stop_for(self, error):
        if isinstance(error, errors.FloodWaitError):
            seconds = max(1, error.seconds)
            self.store.set_telegram_state(
                "pause_until", (utc_now() + timedelta(seconds=seconds)).isoformat()
            )
            self.reason = f"Telegram {seconds} soniya kutishni talab qildi. Agent to'xtatildi; avtomatik qayta urinilmaydi."
        else:
            self.store.set_telegram_state("restriction_latch", type(error).__name__)
            self.reason = "Telegram akkaunt/faoliyat cheklovini qaytardi. Agent to'xtatildi; ruxsat yoki cheklov aniqlanmaguncha qayta urinilmaydi."
        self.stopped.set()
        raise TelegramPaused(self.reason) from None

    async def action(self, operation):
        self.ensure_active()
        try:
            return await operation()
        except (
            errors.FloodWaitError,
            errors.PeerFloodError,
            errors.FrozenMethodInvalidError,
            errors.FrozenParticipantMissingError,
            errors.UserDeactivatedError,
            errors.UserDeactivatedBanError,
        ) as error:
            self.stop_for(error)

    async def send(self, operation):
        async with self.send_lock:
            self.ensure_active()
            loop = asyncio.get_running_loop()
            if self.last_send is not None:
                deadline = self.last_send + self.settings.min_message_interval_seconds
                while (remaining := deadline - loop.time()) > 0:
                    await asyncio.sleep(remaining)
            try:
                return await self.action(operation)
            finally:
                self.last_send = loop.time()

    async def dial(self, user_id, operation):
        self.ensure_active()
        if not self.settings.enable_voice_calls:
            raise TelegramPaused("Ovozli qo'ng'iroqlar o'chirilgan; telefon terilmadi.")
        if user_id != self.settings.owner_id and (
            not self.settings.enable_contact_calls
            or user_id not in self.settings.allowed_call_user_ids
        ):
            raise TelegramPaused("Bu kontaktga qo'ng'iroq ruxsat etilmagan; telefon terilmadi.")
        if retry_at := self.store.reserve_call_slot(
            user_id, self.settings.call_cooldown_seconds, self.settings.max_calls_per_hour
        ):
            raise CallRateLimited(self.store.call_limit_message(retry_at))
        return await self.action(operation)
