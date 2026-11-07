"""Local multilingual recognition and keyless online Uzbek synthesis."""

import asyncio
import audioop
import subprocess
import sys
import tempfile
from pathlib import Path

from .ai_access import AIUnavailable
from .config import ROOT


class FreeSpeech:
    def __init__(self, settings):
        self.settings = settings
        self.model = None
        self.lock = asyncio.Lock()

    def _load(self):
        if self.model is None:
            from faster_whisper import WhisperModel

            self.model = WhisperModel(
                self.settings.local_stt_model,
                device="cpu",
                compute_type="int8",
                download_root=str(ROOT / "data" / "models"),
                cpu_threads=4,
            )

    async def prepare(self):
        async with self.lock:
            await asyncio.to_thread(self._load)

    def _recognize(self, audio):
        self._load()
        segments, _ = self.model.transcribe(
            audio,
            language="uz",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(part.text.strip() for part in segments).strip()

    async def transcribe(self, path):
        def recognize_file():
            from faster_whisper.audio import decode_audio

            audio = decode_audio(str(path), sampling_rate=16000)
            if len(audio) > 16000 * 90:
                raise ValueError("Bepul rejimda ovozli xabar 90 soniyadan qisqa bo'lsin.")
            return self._recognize(audio)

        async with self.lock:
            return await asyncio.to_thread(recognize_file)

    async def transcribe_pcm48(self, pcm):
        def recognize_pcm():
            import numpy as np

            converted, _ = audioop.ratecv(pcm, 2, 1, 48000, 16000, None)
            audio = np.frombuffer(converted, dtype="<i2").astype(np.float32) / 32768.0
            return self._recognize(audio)

        async with self.lock:
            return await asyncio.to_thread(recognize_pcm)

    async def speech(self, text, path):
        import edge_tts

        (ROOT / "data").mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="tts-") as folder:
                source = Path(folder) / "speech.mp3"
                async with asyncio.timeout(45):
                    await edge_tts.Communicate(text[:1800], self.settings.free_tts_voice).save(
                        str(source)
                    )
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-c:a",
                    "libopus",
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-f",
                    "ogg",
                    str(path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                try:
                    async with asyncio.timeout(30):
                        code = await process.wait()
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                if code or not Path(path).exists() or not Path(path).stat().st_size:
                    raise RuntimeError("TTS conversion failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            raise AIUnavailable(
                "Bepul ovoz xizmati hozir ishlamadi. Internetni tekshiring; pulli API ishlatilmadi."
            ) from None
