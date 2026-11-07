import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from .env_defaults import ensure_env_defaults
from .setup_inputs import telegram_credentials

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str = field(repr=False)
    owner_id: int
    openai_key: str = field(repr=False)
    backup_openai_keys: tuple[str, ...] = field(default=(), repr=False)
    owner_username: str = ""
    text_provider: str = "auto"
    gemini_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_reasoning_effort: str = "minimal"
    text_max_output_tokens: int = 1200
    history_messages: int = 10
    history_max_chars: int = 10000
    voice_max_output_tokens: int = 768
    voice_context_tokens: int = 6000
    timezone: str = "Asia/Tashkent"
    text_model: str = "gpt-4.1-mini"
    realtime_model: str = "gpt-realtime-2.1-mini"
    transcribe_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    voice: str = "marin"
    max_call_seconds: int = 900
    ring_timeout_seconds: int = 35
    reminder_grace_hours: int = 24
    enable_contact_calls: bool = False
    enable_voice_calls: bool = False
    allowed_call_user_ids: tuple[int, ...] = ()
    min_message_interval_seconds: float = 2
    call_cooldown_seconds: int = 60
    max_calls_per_hour: int = 3

    @classmethod
    def load(cls, require_telegram=True):
        ensure_env_defaults(ROOT / ".env", ROOT / ".env.example")
        load_dotenv(ROOT / ".env", override=False)
        required = (
            ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "OWNER_TELEGRAM_ID"]
            if require_telegram
            else []
        )
        missing = [key for key in required if not os.getenv(key, "").strip()]
        if missing:
            raise ValueError(
                "Yetishmayapti: "
                + ", ".join(missing)
                + ". OWNER_TELEGRAM_ID ni login.ps1 asosiy akkauntingizdan /pair xabari orqali topadi."
            )
        api_id, api_hash = (
            telegram_credentials(os.environ["TELEGRAM_API_ID"], os.environ["TELEGRAM_API_HASH"])
            if require_telegram
            else (0, "")
        )
        result = cls(
            api_id=api_id,
            api_hash=api_hash,
            owner_id=int(os.environ["OWNER_TELEGRAM_ID"]) if require_telegram else 0,
            openai_key=os.getenv("OPENAI_API_KEY", "").strip(),
            backup_openai_keys=tuple(
                key.strip()
                for key in os.getenv("OPENAI_BACKUP_API_KEYS", "").split(",")
                if key.strip()
            ),
            owner_username=os.getenv("OWNER_TELEGRAM_USERNAME", "").strip(),
            text_provider=os.getenv("TEXT_PROVIDER", "auto").strip().lower() or "auto",
            gemini_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
            gemini_reasoning_effort=os.getenv("GEMINI_REASONING_EFFORT", "minimal"),
            text_max_output_tokens=int(os.getenv("TEXT_MAX_OUTPUT_TOKENS", "1200")),
            history_messages=int(os.getenv("HISTORY_MESSAGES", "10")),
            history_max_chars=int(os.getenv("HISTORY_MAX_CHARS", "10000")),
            voice_max_output_tokens=int(os.getenv("VOICE_MAX_OUTPUT_TOKENS", "768")),
            voice_context_tokens=int(os.getenv("VOICE_CONTEXT_TOKENS", "6000")),
            timezone=os.getenv("TIMEZONE", "Asia/Tashkent"),
            text_model=os.getenv("TEXT_MODEL", "gpt-4.1-mini"),
            realtime_model=os.getenv("REALTIME_MODEL", "gpt-realtime-2.1-mini"),
            transcribe_model=os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
            tts_model=os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.getenv("VOICE", "marin"),
            max_call_seconds=int(os.getenv("MAX_CALL_SECONDS", "900")),
            ring_timeout_seconds=int(os.getenv("RING_TIMEOUT_SECONDS", "35")),
            reminder_grace_hours=int(os.getenv("REMINDER_GRACE_HOURS", "24")),
            enable_contact_calls=os.getenv("ENABLE_CONTACT_CALLS", "false").strip().lower()
            == "true",
            enable_voice_calls=os.getenv("ENABLE_VOICE_CALLS", "false").strip().lower() == "true",
            allowed_call_user_ids=tuple(
                int(value.strip())
                for value in os.getenv("ALLOWED_CALL_USER_IDS", "").split(",")
                if value.strip().isdecimal()
            ),
            min_message_interval_seconds=float(os.getenv("MIN_MESSAGE_INTERVAL_SECONDS", "2")),
            call_cooldown_seconds=int(os.getenv("CALL_COOLDOWN_SECONDS", "60")),
            max_calls_per_hour=int(os.getenv("MAX_CALLS_PER_HOUR", "3")),
        )
        ZoneInfo(result.timezone)
        if result.text_provider not in {"auto", "openai", "gemini"}:
            raise ValueError("TEXT_PROVIDER auto, openai yoki gemini bo'lishi kerak.")
        if result.text_provider == "gemini" and not result.gemini_key:
            raise ValueError("TEXT_PROVIDER=gemini uchun GEMINI_API_KEY ni kiriting.")
        if result.text_provider == "openai" and not result.openai_key:
            raise ValueError("TEXT_PROVIDER=openai uchun OPENAI_API_KEY ni kiriting.")
        if not result.openai_key and not result.gemini_key:
            raise ValueError(
                "GEMINI_API_KEY yoki OPENAI_API_KEY kerak. Jonli ovoz uchun OPENAI_API_KEY ham zarur."
            )
        if result.gemini_reasoning_effort not in {"minimal", "low", "medium", "high"}:
            raise ValueError("GEMINI_REASONING_EFFORT: minimal, low, medium yoki high.")
        if (
            not 256 <= result.text_max_output_tokens <= 8192
            or not 128 <= result.voice_max_output_tokens <= 4096
        ):
            raise ValueError(
                "TEXT_MAX_OUTPUT_TOKENS 256..8192, VOICE_MAX_OUTPUT_TOKENS 128..4096 bo'lishi kerak."
            )
        if not 2 <= result.history_messages <= 50 or not 2000 <= result.history_max_chars <= 60000:
            raise ValueError(
                "HISTORY_MESSAGES 2..50, HISTORY_MAX_CHARS 2000..60000 bo'lishi kerak."
            )
        if not 2048 <= result.voice_context_tokens <= 16000:
            raise ValueError("VOICE_CONTEXT_TOKENS 2048..16000 bo'lishi kerak.")
        if require_telegram and (result.api_id <= 0 or result.owner_id <= 0):
            raise ValueError("Telegram API ID va OWNER_TELEGRAM_ID musbat son bo'lishi kerak.")
        if not 30 <= result.max_call_seconds <= 3300:
            raise ValueError("MAX_CALL_SECONDS 30..3300 oralig'ida bo'lishi kerak.")
        if not 5 <= result.ring_timeout_seconds <= 90:
            raise ValueError("RING_TIMEOUT_SECONDS 5..90 oralig'ida bo'lishi kerak.")
        if result.reminder_grace_hours < 1:
            raise ValueError("REMINDER_GRACE_HOURS kamida 1 bo'lishi kerak.")
        if len(result.backup_openai_keys) > 3:
            raise ValueError(
                "OPENAI_BACKUP_API_KEYS da ko'pi bilan 3 ta zaxira kalit bo'lishi mumkin."
            )
        if not 0.5 <= result.min_message_interval_seconds <= 60:
            raise ValueError("MIN_MESSAGE_INTERVAL_SECONDS 0.5..60 oralig'ida bo'lishi kerak.")
        if (
            not 10 <= result.call_cooldown_seconds <= 3600
            or not 1 <= result.max_calls_per_hour <= 20
        ):
            raise ValueError(
                "CALL_COOLDOWN_SECONDS 10..3600, MAX_CALLS_PER_HOUR 1..20 oralig'ida bo'lishi kerak."
            )
        return result

    @property
    def resolved_text_provider(self):
        if self.text_provider == "auto":
            return "gemini" if self.gemini_key else "openai"
        return self.text_provider
