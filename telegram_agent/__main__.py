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

from .ai_access import AIUnavailable
from .config import ROOT, Settings
from .env_defaults import ensure_env_defaults
from .instance_lock import instance_lock
from .owner_setup import configured_owner, pair_owner
from .setup_inputs import prompt_phone, telegram_credentials
from .telegram_health import ensure_telegram_account


@contextmanager
def process_lock():
    with instance_lock(ROOT / "data" / "agent.lock"):
        yield


async def setup(from_env=False):
    from telethon import TelegramClient
    from telethon.errors import ApiIdInvalidError

    path = ROOT / ".env"
    if not path.exists():
        shutil.copy(ROOT / ".env.example", path)
    ensure_env_defaults(path, ROOT / ".env.example")
    existing = dotenv_values(path)
    print("TelegramAgent sozlash. Maxfiy qiymatlar chatga yuborilmaydi.")
    print("Asosiy akkauntingizdan yordamchi akkauntiga bir marta xabar yuboring.")
    if from_env:
        print("API ma'lumotlari .env faylidan o'qiladi; qayta kiritish shart emas.")
        api_id = existing.get("TELEGRAM_API_ID", "")
        api_hash = existing.get("TELEGRAM_API_HASH", "")
        key = existing.get("OPENAI_API_KEY", "")
    else:
        api_id = input("Telegram API ID: ").strip() or existing.get("TELEGRAM_API_ID") or "0"
        api_hash = getpass.getpass("Telegram API hash (yashirin; bo'sh = avvalgisi): ").strip()
        api_hash = api_hash or existing.get("TELEGRAM_API_HASH", "")
        key = getpass.getpass("OpenAI API key (yashirin; bo'sh = avvalgisi): ").strip()
        key = key or existing.get("OPENAI_API_KEY", "")
    api_id, api_hash = telegram_credentials(api_id, api_hash)
    if not key and not from_env and not existing.get("GEMINI_API_KEY"):
        raise ValueError("OpenAI API key kerak.")
    if not key:
        print(
            "OpenAI API key hali yo'q. Telegram login mumkin. Gemini bilan matnli agent va VOICE_PROVIDER=free orqali bepul ovoz ishlaydi."
        )
    saved_phone = existing.get("TELEGRAM_PHONE", "") if from_env else ""
    if saved_phone:
        from .setup_inputs import international_phone

        saved_phone = international_phone(saved_phone)
    (ROOT / "data").mkdir(exist_ok=True)
    client = TelegramClient(
        str(ROOT / "data" / "assistant"),
        api_id,
        api_hash,
        request_retries=0,
        flood_sleep_threshold=0,
    )
    try:
        await client.start(
            phone=saved_phone or prompt_phone,
            password=lambda: getpass.getpass("Telegram 2FA paroli: "),
            code_callback=lambda: getpass.getpass("Telegram login kodi: "),
        )
        me = await ensure_telegram_account(client, existing.get("TIMEZONE") or "Asia/Tashkent")
        print(f"Yordamchi akkaunt: {me.first_name} (ID: {me.id})")
        if me.bot:
            raise ValueError("Yordamchi oddiy Telegram akkaunti bo'lishi kerak.")
        owner = await configured_owner(
            client,
            me.id,
            existing.get("OWNER_TELEGRAM_USERNAME", ""),
            existing.get("OWNER_TELEGRAM_ID", ""),
        )
        if owner is None:
            print("Asosiy akkaunt sozlamalardan topilmadi. Bir martalik xabar bilan ulaymiz.")
            owner = await pair_owner(client, me.id)
        print(f"Faqat ushbu akkauntga xizmat qiladi: {owner.first_name} (ID: {owner.id})")
        if input("Shu akkaunt sizniki bo'lsa HA yozing: ").strip().upper() != "HA":
            raise ValueError("Sozlash bekor qilindi; egasi tasdiqlanmadi.")
        values = {
            "TELEGRAM_API_ID": str(api_id),
            "TELEGRAM_API_HASH": api_hash,
            "OWNER_TELEGRAM_ID": str(owner.id),
            "OWNER_TELEGRAM_USERNAME": "@" + owner.username if owner.username else "",
        }
        if key:
            values["OPENAI_API_KEY"] = key
        for name, value in values.items():
            set_key(str(path), name, value)
    except ApiIdInvalidError:
        raise ValueError(
            "Telegram API ID yoki API hash ni qabul qilmadi (API_ID_INVALID). "
            "my.telegram.org/apps dagi bir xil ilovadan api_id va api_hash ni qayta nusxalang. "
            "api_hash OpenAI kaliti yoki BotFather tokeni emas. "
            "Telefon raqamini ham + va mamlakat kodi bilan kiriting. "
            "Bu xato OpenAI yoki internet sozlamasi xatosi emas."
        ) from None
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

        # Validate Telegram first: a readable frozen session must not be reported as healthy.
        client = TelegramClient(
            str(ROOT / "data" / "assistant"),
            settings.api_id,
            settings.api_hash,
            request_retries=0,
            flood_sleep_threshold=0,
        )
        try:
            await client.connect()
            me = await ensure_telegram_account(client, settings.timezone)
            if me.bot or me.id == settings.owner_id:
                raise ValueError("Yordamchi uchun alohida oddiy akkaunt kerak.")
            owner = await configured_owner(
                client, me.id, settings.owner_username, str(settings.owner_id)
            )
            if owner is None or owner.id != settings.owner_id:
                raise ValueError(
                    "Asosiy akkaunt topilmadi. login.ps1 orqali /pair xabar bilan qayta ulang."
                )
            print("Telegram avtorizatsiya, freeze holati va egasi: OK")
        finally:
            await client.disconnect()

        if settings.resolved_text_provider == "gemini":
            from .gemini_text import GeminiText

            gemini = GeminiText(settings)
            try:
                models = await gemini.client.models.list()
                if settings.gemini_model not in {model.id.split("/")[-1] for model in models.data}:
                    raise ValueError("GEMINI_MODEL Google qaytargan modellar ro'yxatida topilmadi.")
                print(f"Gemini model ro'yxatda mavjud: {settings.gemini_model}")
            finally:
                await gemini.close()
        if settings.openai_key and settings.voice_provider == "openai":
            async with AsyncOpenAI(api_key=settings.openai_key) as ai:
                models = [settings.realtime_model, settings.transcribe_model, settings.tts_model]
                if settings.resolved_text_provider == "openai":
                    models.insert(0, settings.text_model)
                for model in models:
                    await ai.models.retrieve(model)
                    print(f"OpenAI model mavjud: {model}")
        else:
            print("OpenAI tekshiruvi o'tkazilmadi; bepul yoki Gemini matnli rejimi tanlangan.")
    return 0


async def telegram_status():
    from telethon import TelegramClient

    existing = dotenv_values(ROOT / ".env")
    api_id, api_hash = telegram_credentials(
        existing.get("TELEGRAM_API_ID"), existing.get("TELEGRAM_API_HASH")
    )
    client = TelegramClient(
        str(ROOT / "data" / "assistant"),
        api_id,
        api_hash,
        request_retries=0,
        flood_sleep_threshold=0,
    )
    try:
        await client.connect()
        me = await ensure_telegram_account(client, existing.get("TIMEZONE") or "Asia/Tashkent")
        print(
            f"Yordamchi ID: {me.id}. Username: {'@' + me.username if me.username else 'qo‘yilmagan'}."
        )
        print(
            "Telegram serverida akkauntning freeze belgisi yo'q. Xabar yetkazish alohida tekshiriladi."
        )
    finally:
        await client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Shaxsiy Telegram AI yordamchi")
    parser.add_argument(
        "command",
        choices=[
            "configure",
            "setup",
            "login",
            "doctor",
            "telegram-status",
            "sandbox",
            "free-voice-check",
            "run",
            "panel",
            "supervise",
        ],
    )
    parser.add_argument(
        "--economy",
        action="store_true",
        help="configure: oldingi standart Realtime modelini Mini ga almashtirish",
    )
    parser.add_argument("--online", action="store_true", help="doctor: tashqi API larni tekshirish")
    parser.add_argument(
        "--self-test", action="store_true", help="sandbox: qisqa haqiqiy AI va eslatma sinovi"
    )
    parser.add_argument(
        "--speech", action="store_true", help="sandbox --self-test: ovoz generatsiyasini ham sinash"
    )
    parser.add_argument(
        "--enable-voice",
        action="store_true",
        help="free-voice-check: muvaffaqiyatli sinovdan keyin egasi uchun qo'ng'iroqni yoqish",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        choices=["127.0.0.1", "0.0.0.0"],
        help="panel: localhost yoki LAN",
    )
    parser.add_argument("--port", type=int, default=8765, help="panel: HTTP port")
    args = parser.parse_args()
    try:
        if args.command == "supervise":
            from .supervisor import supervise

            return supervise()
        elif args.command == "panel":
            from .panel import serve_panel

            with process_lock():
                asyncio.run(serve_panel(Settings.load(), args.host, args.port))
        elif args.command == "free-voice-check":
            from .voice_check import check_free_voice

            return asyncio.run(check_free_voice(enable=args.enable_voice))
        elif args.command == "sandbox":
            from .sandbox import console, self_test

            settings = Settings.load(require_telegram=False)
            if args.self_test:
                return 0 if asyncio.run(self_test(settings, speech=args.speech)) else 1
            asyncio.run(console(settings))
        elif args.command == "configure":
            path = ROOT / ".env"
            added = ensure_env_defaults(path, ROOT / ".env.example")
            print("Qo'shilgan sozlama nomlari: " + (", ".join(added) or "yangi sozlama yo'q"))
            if args.economy and dotenv_values(path).get("REALTIME_MODEL") == "gpt-realtime-2.1":
                set_key(str(path), "REALTIME_MODEL", "gpt-realtime-2.1-mini")
                print("REALTIME_MODEL: arzonroq gpt-realtime-2.1-mini tanlandi.")
            print("Mavjud API kalitlari o'zgartirilmadi va chiqarilmadi.")
        elif args.command in {"setup", "login"}:
            with process_lock():
                asyncio.run(setup(from_env=args.command == "login"))
        elif args.command == "doctor":
            with process_lock():
                return asyncio.run(doctor(args.online))
        elif args.command == "telegram-status":
            with process_lock():
                asyncio.run(telegram_status())
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
        if isinstance(exc, (ValueError, AIUnavailable)):
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
