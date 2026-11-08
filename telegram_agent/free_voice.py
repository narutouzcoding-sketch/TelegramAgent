"""Turn-based calls with native/local ASR and independent original-audio capture."""

import asyncio
import audioop
import logging
import tempfile
from collections import deque
from pathlib import Path

from .ai_access import AIUnavailable
from .config import ROOT
from .contact_calls import decode_pcm

log = logging.getLogger(__name__)


class SpeechSegments:
    """Segment 10ms mono PCM48 frames; ignore short clicks and retain leading audio."""

    def __init__(self):
        self.pre = deque(maxlen=20)
        self.frames = []
        self.voiced = self.silent = 0

    def push(self, frame):
        loud = audioop.rms(frame, 2) >= 150
        if not self.frames and not loud:
            self.pre.append(frame)
            return None
        if not self.frames:
            self.frames.extend(self.pre)
            self.pre.clear()
        self.frames.append(frame)
        self.voiced += int(loud)
        self.silent = 0 if loud else self.silent + 1
        if self.silent >= 65 or len(self.frames) >= 1500:
            result = b"".join(self.frames) if self.voiced >= 10 else None
            self.frames.clear()
            self.voiced = self.silent = 0
            return result
        return None


class RecordedReplyPause:
    """End a voice memo on a real pause, never at the ASR chunk's 15s boundary."""

    def __init__(self):
        self.voiced = self.silent = 0

    def push(self, frame):
        if audioop.rms(frame, 2) >= 150:
            self.voiced += 1
            self.silent = 0
        elif self.voiced:
            self.silent += 1
        if self.silent >= 150:
            ready = self.voiced >= 10
            self.voiced = self.silent = 0
            return b"recorded" if ready else None
        return None


class FreeVoiceSession:
    def __init__(self, brain, send_frame, introduction):
        self.brain, self.send_frame, self.introduction = brain, send_frame, introduction
        self.closed = asyncio.Event()
        self.error = None
        self.tasks = []
        self.input = asyncio.Queue(maxsize=1800)
        self.output = deque()
        self.busy = True
        self.speaking = False
        self.accepting = False
        self.record_only = getattr(brain, "record_only", False)
        self.recording_enabled = getattr(
            brain,
            "recording_enabled",
            getattr(getattr(brain, "settings", None), "record_calls", True),
        )
        self.misses = 0

    async def start(self):
        if not getattr(self.brain, "use_native_asr", False):
            await self.brain.free_speech.prepare()
        self.tasks = [
            asyncio.create_task(self.guarded(self.play)),
            asyncio.create_task(self.guarded(self.feed)),
        ]
        self.tasks.append(asyncio.create_task(self.guarded(self.greet)))

    def accept_pcm48(self, pcm):
        # Keep speech arriving while AI is thinking. Only playback echo is excluded
        # from ASR; the independent recorder still captures every incoming packet.
        if not self.closed.is_set() and self.accepting and not self.speaking:
            if self.input.full():
                self.input.get_nowait()
            self.input.put_nowait(pcm)

    async def greet(self):
        # A greeting is speech to deliver, not a new owner instruction to the text agent.
        await self.speak(self.introduction)
        self.accepting = True

    async def respond(self, text):
        try:
            answer = getattr(self.brain, "answer_voice", self.brain.answer)
            reply = await answer(text)
        except AIUnavailable:
            self.record_only = True
            if hasattr(self.brain, "record_only"):
                self.brain.record_only = True
                if any(row.get("role") == "user" for row in getattr(self.brain, "transcript", [])):
                    self.brain.recorded_answer = self.brain.finished = True
            language = getattr(self.brain, "language", "uz")
            reply = {
                "uz": "AI hozir javob bera olmadi. Asl ovozingiz yoziladi va chatga yuboriladi.",
                "en": "The AI is temporarily unavailable. Your original voice is recorded and will be sent to the owner.",
                "ru": "ИИ временно недоступен. Ваш голос записывается и будет передан владельцу.",
            }[language]
            if not self.recording_enabled:
                reply = {
                    "uz": "AI hozir javob bera olmadi. Ovoz yozish o'chirilgan. Chatda davom eting.",
                    "en": "The AI is unavailable. Recording is disabled. Please continue in chat.",
                    "ru": "ИИ недоступен. Запись отключена. Продолжите в чате.",
                }[language]
        await self.speak(reply)
        if getattr(self.brain, "finished", False) or (
            self.record_only and not self.recording_enabled
        ):
            self.closed.set()

    async def speak(self, reply):
        self.busy = True
        try:
            with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="free-call-") as folder:
                path = Path(folder) / "reply.ogg"
                await self.brain.speech(reply, path)
                pcm = await decode_pcm(path)
            self.output.extend(pcm[i : i + 960].ljust(960, b"\0") for i in range(0, len(pcm), 960))
            self.speaking = True
            while self.output and not self.closed.is_set():
                await asyncio.sleep(0.02)
        finally:
            self.speaking = False
            self.busy = False

    async def feed(self):
        segments, pending = SpeechSegments(), bytearray()
        while True:
            pending.extend(await self.input.get())
            while len(pending) >= 960:
                if self.record_only and not isinstance(segments, RecordedReplyPause):
                    segments = RecordedReplyPause()
                frame = bytes(pending[:960])
                del pending[:960]
                utterance = segments.push(frame)
                if utterance:
                    self.busy = True
                    if self.record_only:
                        if hasattr(self.brain, "recorded_answer"):
                            await self.respond(None)
                        else:
                            await self.speak("Rahmat. Ovoz yozuvi chatga yuboriladi.")
                            self.closed.set()
                    else:
                        try:
                            async with asyncio.timeout(45):
                                transcribe = getattr(
                                    self.brain,
                                    "transcribe_pcm48",
                                    self.brain.free_speech.transcribe_pcm48,
                                )
                                text = await transcribe(utterance)
                        except (ValueError, TimeoutError):
                            text = ""
                        if text:
                            self.misses = 0
                            await self.respond(text)
                        else:
                            self.misses += 1
                            if self.misses >= 2:
                                self.record_only = True
                                if hasattr(self.brain, "record_only"):
                                    self.brain.record_only = True
                            language = getattr(self.brain, "language", "uz")
                            await self.speak(
                                {
                                    "uz": "Aniq tushunmadim. Qisqaroq va ravshanroq ayting. Asl ovozingiz saqlanadi.",
                                    "en": "I could not understand clearly. Please say it again briefly. Your original voice is saved.",
                                    "ru": "Не удалось разобрать речь. Повторите коротко и чётко. Ваш голос сохраняется.",
                                }[language]
                            )
                    pending.clear()
                    break

    async def play(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            await self.send_frame(self.output.popleft() if self.output else bytes(960))
            deadline += 0.01
            await asyncio.sleep(max(0, deadline - loop.time()))
            if loop.time() - deadline > 0.1:
                deadline = loop.time()

    async def guarded(self, operation):
        try:
            await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if type(exc).__name__ == "NotInCallError":
                self.closed.set()
                return
            log.warning("Free voice failed type=%s", type(exc).__name__)
            self.error = (
                str(exc)
                if isinstance(exc, AIUnavailable)
                else "Bepul ovozli suhbatda xato. Matnli suhbatdan foydalaning."
            )
            self.closed.set()

    async def close(self):
        self.closed.set()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        self.output.clear()
