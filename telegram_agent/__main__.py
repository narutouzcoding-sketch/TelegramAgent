import argparse
import asyncio
import getpass
import importlib.metadata
import logging
import shutil
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

from dotenv import dotenv_values, set_key

from .config import ROOT, Settings


@contextmanager
def process_lock():
    import msvcrt

    (ROOT / "data").mkdir(exist_ok=True)
    with (ROOT / "data" / "agent.lock").open("a+b") as handle:
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise ValueError(
                "TelegramAgent allaqachon ishlayapti. Ikkinchi nusxa ochilmadi."
            ) from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


async def setup():
    from telethon import TelegramClient
    from telethon.tl.types import User

    path = ROOT / ".env"
    if not path.exists():
        shutil.copy(ROOT / ".env.example", path)
    existing = dotenv_values(path)
    print("TelegramAgent sozlash. Maxfiy qiymatlar chatga yuborilmaydi.")
    print("1. https://my.telegram.org/apps dan api_id va api_hash oling.")
    print("2. Yordamchi uchun alohida Telegram akkauntiga kiring.")
    print("3. Asosiy akkauntingizdan yordamchi akkauntiga bir marta xabar yuboring.")
    api_id = int(input("Telegram API ID: ").strip() or existing.get("TELEGRAM_API_ID") or "0")
    api_hash = getpass.getpass("Telegram API hash (yashirin; bo'sh = avvalgisi): ").strip()
    api_hash = api_hash or existing.get("TELEGRAM_API_HASH", "")
    key = getpass.getpass("OpenAI API key (yashirin; bo'sh = avvalgisi): ").strip()
    key = key or existing.get("OPENAI_API_KEY", "")
    if api_id <= 0 or not api_hash or not key:
        raise ValueError("API ID, hash va OpenAI API key kerak.")
    (ROOT / "data").mkdir(exist_ok=True)
    client = TelegramClient(str(ROOT / "data" / "assistant"), api_id, api_hash)
    try:
        await client.start(
            phone=lambda: input("Yordamchi akkaunt telefon raqami (+998...): ").strip(),
            password=lambda: getpass.getpass("Telegram 2FA paroli: "),
            code_callback=lambda: getpass.getpass("Telegram login kodi: "),
        )
        me = await client.get_me()
        print(f"Yordamchi akkaunt: {me.first_name} (ID: {me.id})")
        owner_ref = input("SIZNING asosiy Telegram @username yoki raqamli ID: ").strip()
        # Populate the entity cache from existing dialogs for numeric owner IDs.
        if owner_ref.isdecimal():
            await client.get_dialogs(limit=200)
            owner_ref = int(owner_ref)
        owner = await client.get_entity(owner_ref)
        if not isinstance(owner, User) or owner.bot or owner.id == me.id:
            raise ValueError("Asosiy akkaunt alohida inson akkaunti bo'lishi kerak.")
        print(f"Faqat ushbu akkauntga xizmat qiladi: {owner.first_name} (ID: {owner.id})")
        if input("Shu akkaunt sizniki bo'lsa HA yozing: ").strip().upper() != "HA":
            raise ValueError("Sozlash bekor qilindi; egasi tasdiqlanmadi.")
        for name, value in {
            "TELEGRAM_API_ID": str(api_id),
            "TELEGRAM_API_HASH": api_hash,
            "OPENAI_API_KEY": key,
            "OWNER_TELEGRAM_ID": str(owner.id),
        }.items():
            set_key(str(path), name, value)
    finally:
        await client.disconnect()
    print("Sozlandi. start.ps1 ni ishga tushiring. Kalitlar .env da, Telegram sessiya data/ da.")


async def doctor(online=False):
    print("Python:", sys.version.split()[0])
    for package in ["telethon", "py-tgcalls", "ntgcalls", "openai", "aiohttp"]:
        print(f"{package}: {importlib.metadata.version(package)}")
    print("FFmpeg:", shutil.which("ffmpeg") or "TOPILMADI")
    # Native imports detect missing Windows runtime/DLLs before Telegram login.
    import ntgcalls  # noqa: F401
    from pytgcalls.types import ExternalMedia, MediaStream, RecordStream
    from pytgcalls.types.raw import AudioParameters

    params = AudioParameters(bitrate=48000, channels=1)
    MediaStream(ExternalMedia.AUDIO, params, video_flags=MediaStream.Flags.IGNORE)
    RecordStream(True, params)
    print("Native qo'ng'iroq kutubxonasi va PCM48 konfiguratsiyasi: OK")
    try:
        settings = Settings.load()
    except ValueError as exc:
        print(str(exc))
        return 2
    print("Sozlamalar: OK (maxfiy qiymatlar chiqarilmadi)")
    print("Telegram sessiya:", "bor" if (ROOT / "data" / "assistant.session").exists() else "YO'Q")
    if online:
        from openai import AsyncOpenAI
        from telethon import TelegramClient

        async with AsyncOpenAI(api_key=settings.openai_key) as ai:
            for model in [
                settings.text_model,
                settings.realtime_model,
                settings.transcribe_model,
                settings.tts_model,
            ]:
                await ai.models.retrieve(model)
                print(f"Model mavjud: {model}")
        client = TelegramClient(
            str(ROOT / "data" / "assistant"), settings.api_id, settings.api_hash
        )
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ValueError("Telegram login zarur. setup.ps1 ni ishga tushiring.")
            me = await client.get_me()
            if me.bot or me.id == settings.owner_id:
                raise ValueError("Yordamchi uchun alohida oddiy akkaunt kerak.")
            await client.get_input_entity(settings.owner_id)
            print("Telegram avtorizatsiya va egasi: OK")
        finally:
            await client.disconnect()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Shaxsiy Telegram AI yordamchi")
    parser.add_argument("command", choices=["setup", "doctor", "run"])
    parser.add_argument("--online", action="store_true", help="doctor: tashqi API larni tekshirish")
    args = parser.parse_args()
    try:
        if args.command == "setup":
            with process_lock():
                asyncio.run(setup())
        elif args.command == "doctor":
            with process_lock():
                return asyncio.run(doctor(args.online))
        else:
            from .app import AgentApp

            (ROOT / "logs").mkdir(exist_ok=True)
            handler = RotatingFileHandler(
                ROOT / "logs" / "agent.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            logging.basicConfig(
                level=logging.WARNING,
                handlers=[handler, logging.StreamHandler()],
                format="%(asctime)s %(levelname)s %(name)s %(message)s",
            )
            with process_lock():
                asyncio.run(AgentApp(Settings.load()).run())
    except KeyboardInterrupt:
        print("\nAgent to'xtatildi.")
    except Exception as exc:
        # Never print SDK exception bodies; they can contain credentials or request data.
        if isinstance(exc, ValueError):
            print("Xato:", exc, file=sys.stderr)
        else:
            print(
                f"Xato turi: {type(exc).__name__}. Sozlamalar va internetni tekshiring.",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
