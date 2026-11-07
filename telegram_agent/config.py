import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    owner_id: int
    openai_key: str
    timezone: str = "Asia/Tashkent"
    text_model: str = "gpt-4.1-mini"
    realtime_model: str = "gpt-realtime-2.1"
    transcribe_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    voice: str = "marin"
    max_call_seconds: int = 900
    ring_timeout_seconds: int = 35
    reminder_grace_hours: int = 24

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        required = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "OWNER_TELEGRAM_ID", "OPENAI_API_KEY"]
        missing = [key for key in required if not os.getenv(key, "").strip()]
        if missing:
            raise ValueError(
                "Avval setup.ps1 ni ishga tushiring. Yetishmayapti: " + ", ".join(missing)
            )
        result = cls(
            api_id=int(os.environ["TELEGRAM_API_ID"]),
            api_hash=os.environ["TELEGRAM_API_HASH"].strip(),
            owner_id=int(os.environ["OWNER_TELEGRAM_ID"]),
            openai_key=os.environ["OPENAI_API_KEY"].strip(),
            timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
            text_model=os.getenv("TEXT_MODEL", "gpt-4.1-mini"),
            realtime_model=os.getenv("REALTIME_MODEL", "gpt-realtime-2.1"),
            transcribe_model=os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
            tts_model=os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.getenv("VOICE", "marin"),
            max_call_seconds=int(os.getenv("MAX_CALL_SECONDS", "900")),
            ring_timeout_seconds=int(os.getenv("RING_TIMEOUT_SECONDS", "35")),
            reminder_grace_hours=int(os.getenv("REMINDER_GRACE_HOURS", "24")),
        )
        ZoneInfo(result.timezone)
        if result.api_id <= 0 or result.owner_id <= 0:
            raise ValueError("Telegram API ID va OWNER_TELEGRAM_ID musbat son bo'lishi kerak.")
        if not 30 <= result.max_call_seconds <= 3300:
            raise ValueError("MAX_CALL_SECONDS 30..3300 oralig'ida bo'lishi kerak.")
        if not 5 <= result.ring_timeout_seconds <= 90:
            raise ValueError("RING_TIMEOUT_SECONDS 5..90 oralig'ida bo'lishi kerak.")
        if result.reminder_grace_hours < 1:
            raise ValueError("REMINDER_GRACE_HOURS kamida 1 bo'lishi kerak.")
        return result
