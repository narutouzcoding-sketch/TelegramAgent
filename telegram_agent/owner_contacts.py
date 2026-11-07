"""One-time local owner login to copy their address book, without reading chats."""

import asyncio
from getpass import getpass

from telethon import TelegramClient

from .config import ROOT, Settings
from .contact_sync import telegram_contacts
from .store import Store
from .telegram_health import ensure_telegram_account


async def sync():
    settings = Settings.load()
    print(
        "Asosiy akkauntingiz kontaktlari mahalliy agentga olinadi. Xabarlar o'qilmaydi yoki yuborilmaydi."
    )
    print("Kod va 2FA parolini faqat shu oynada kiriting; chatga yubormang.")
    client = TelegramClient(
        str(ROOT / "data" / "owner-contacts"),
        settings.api_id,
        settings.api_hash,
        request_retries=0,
        flood_sleep_threshold=0,
    )
    try:
        await client.start(
            phone=lambda: input("Asosiy Telegram telefoningiz (+998...): ").strip(),
            code_callback=lambda: getpass("Telegram kodi (yashirin): "),
            password=lambda: getpass("Telegram 2FA paroli (yashirin): "),
        )
        me = await ensure_telegram_account(client, settings.timezone)
        if me.id != settings.owner_id:
            print(
                "Bu akkaunt faqat kontakt manbasi sifatida ulanadi. Agentni boshqarish huquqi berilmaydi."
            )
        rows = await telegram_contacts(client, me.id)
        store = Store(ROOT / "data" / "agent.sqlite3", settings.timezone)
        try:
            result = store.import_contacts(
                rows, "owner-telegram" if me.id == settings.owner_id else "linked-telegram"
            )
        finally:
            store.close()
        print(
            f"Tayyor. Yangi kontaktlar: {result['imported']}. Jami: {result['total']}. Saytdagi Kontaktlar bo'limini yangilang."
        )
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(sync())
    except (KeyboardInterrupt, EOFError):
        print("Kontakt ulash to'xtatildi.")
        raise SystemExit(1)
    except Exception as exc:
        print(
            str(exc)
            if isinstance(exc, ValueError)
            else "Kontaktlar olinmadi: " + type(exc).__name__
        )
        raise SystemExit(1)
