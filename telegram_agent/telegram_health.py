"""Read Telegram's account freeze state before enabling assistant activity."""

from datetime import datetime
from zoneinfo import ZoneInfo

from telethon import errors, functions


class TelegramAccountFrozen(ValueError):
    def __init__(self, since=None, until=None, timezone="Asia/Tashkent"):
        self.since = since
        self.until = until
        when = (
            datetime.fromtimestamp(until, ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
            if until
            else "ko'rsatilmagan"
        )
        super().__init__(
            "Telegram yordamchi akkauntni MUZLATGAN (frozen/read-only). Login ishlashi mumkin, "
            "ammo agent yozisha va qo'ng'iroq qila olmaydi. "
            f"Server ko'rsatgan o'chirish muddati: {when} ({timezone}). "
            "Yordamchi akkauntga rasmiy Telegram ilovasida kirib, Appeal/Apellyatsiya orqali "
            "cheklovni ko'rib chiqishni so'rang. Agent to'xtatildi; sessiya va kalitlar saqlangan."
        )


async def ensure_telegram_account(client, timezone="Asia/Tashkent"):
    try:
        me = await client.get_me()
    except (errors.UserDeactivatedError, errors.UserDeactivatedBanError):
        raise ValueError(
            "Telegram yordamchi akkauntni o'chirilgan yoki bloklangan deb qaytardi. Rasmiy ilovada akkaunt holati va apellyatsiyani tekshiring; qayta-qayta login qilinmadi."
        ) from None
    if me is None:
        raise ValueError(
            "Telegram sessiya avtorizatsiyadan o'tmagan. login.ps1 ni ishga tushiring."
        )
    if getattr(me, "deleted", False):
        raise ValueError(
            "Telegram yordamchi akkauntni o'chirilgan deb belgilagan. Sessiya va API kalitlari o'zgartirilmadi."
        )
    try:
        result = await client(functions.help.GetAppConfigRequest(hash=0))
    except (errors.FrozenMethodInvalidError, errors.FrozenParticipantMissingError):
        raise TelegramAccountFrozen(timezone=timezone) from None
    config = getattr(result, "config", None)
    if config is None:
        raise ValueError(
            "Telegram akkaunt cheklovlari haqida to'liq holat qaytarmadi. Ishga tushirish bekor qilindi; tekshiruvni qaytaring."
        )
    values = {
        item.key: getattr(item.value, "value", None)
        for item in config.value
        if item.key in {"freeze_since_date", "freeze_until_date"}
    }
    since, until = values.get("freeze_since_date"), values.get("freeze_until_date")
    if since and int(since) > 0:
        raise TelegramAccountFrozen(int(since), int(until) if until else None, timezone)
    return me
