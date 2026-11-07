"""Exercise the free speech pipeline without opening a Telegram session."""

import tempfile
from dataclasses import replace
from pathlib import Path

from dotenv import set_key

from .config import ROOT, Settings
from .contact_calls import decode_pcm
from .sandbox import session


async def check_free_voice(enable=False):
    settings = replace(
        Settings.load(require_telegram=False), voice_provider="free", text_provider="gemini"
    )
    if not settings.gemini_key:
        raise ValueError("Bepul rejim uchun GEMINI_API_KEY kerak.")
    print("Bepul ovoz sinovi: Telegramga ulanmaydi, OpenAI so'rovi yuborilmaydi.", flush=True)
    async with session(settings) as (brain, store):
        await brain.free_speech.prepare()
        print("Mahalliy Whisper modeli: OK", flush=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="voice-check-") as folder:
            path = Path(folder) / "sample.ogg"
            await brain.speech("Assalomu alaykum. Bugungi rejalaringiz qanday?", path)
            print("O'zbekcha bepul ovoz va Opus format: OK", flush=True)
            text = await brain.transcribe(path)
            if not text.strip():
                raise ValueError("Sinov ovozi tanilmadi; qo'ng'iroqlar yoqilmadi.")
            print("Sintetik ovoz tanildi: " + text, flush=True)
            reply = await brain.answer(text + "\nBitta qisqa jumla bilan javob bering.")
            await brain.speech(reply, path)
            pcm = await decode_pcm(path)
            if len(pcm) < 960:
                raise ValueError("Telegram uchun ovoz yaratilmagan; qo'ng'iroqlar yoqilmadi.")
            print("Gemini javobi -> bepul ovoz -> Telegram PCM48: OK", flush=True)
    if enable:
        # No credentials or owner ID are rewritten. The running app needs a restart.
        for key, value in {
            "VOICE_PROVIDER": "free",
            "TEXT_PROVIDER": "gemini",
            "ENABLE_VOICE_CALLS": "true",
            "ENABLE_CONTACT_CALLS": "false",
        }.items():
            set_key(str(ROOT / ".env"), key, value)
        print("Bepul qo'ng'iroq rejimi egasi uchun yoqildi. Agentni qayta ishga tushiring.")
    print("Bu sinov jonli Telegram qo'ng'irog'ini tekshirmaydi; keyin /call yuboring.")
    return 0
