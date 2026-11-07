"""Turn-based calls: local STT -> existing text brain -> free online TTS."""

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
        loud = audioop.rms(frame, 2) >= 500
        if not self.frames and not loud:
            self.pre.append(frame)
            return None
        if not self.frames:
            self.frames.extend(self.pre)
            self.pre.clear()
        self.frames.append(frame)
        self.voiced += int(loud)
        self.silent = 0 if loud else self.silent + 1
        if self.silent >= 90 or len(self.frames) >= 1500:
            result = b"".join(self.frames) if self.voiced >= 25 else None
            self.frames.clear()
            self.voiced = self.silent = 0
            return result
        return None


class FreeVoiceSession:
    def __init__(self, brain, send_frame, introduction):
        self.brain, self.send_frame, self.introduction = brain, send_frame, introduction
        self.closed = asyncio.Event()
        self.error = None
        self.tasks = []
        self.input = asyncio.Queue(maxsize=300)
        self.output = deque()
        self.busy = True

    async def start(self):
        await self.brain.free_speech.prepare()
        self.tasks = [
            asyncio.create_task(self.guarded(self.play)),
            asyncio.create_task(self.guarded(self.feed)),
        ]
        self.tasks.append(asyncio.create_task(self.guarded(self.greet)))

    def accept_pcm48(self, pcm):
        # This mode takes turns. Drop echo/overlapping speech while thinking or speaking.
        if not self.closed.is_set() and not self.busy:
            if self.input.full():
                self.input.get_nowait()
            self.input.put_nowait(pcm)

    async def greet(self):
        await self.respond("Qo'ng'iroq boshidagi ko'rsatma: " + self.introduction)

    async def respond(self, text):
        self.busy = True
        try:
            reply = await self.brain.answer(text)
            with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="free-call-") as folder:
                path = Path(folder) / "reply.ogg"
                await self.brain.speech(reply, path)
                pcm = await decode_pcm(path)
            self.output.extend(pcm[i : i + 960].ljust(960, b"\0") for i in range(0, len(pcm), 960))
            while self.output and not self.closed.is_set():
                await asyncio.sleep(0.02)
        finally:
            self.busy = False

    async def feed(self):
        segments, pending = SpeechSegments(), bytearray()
        while True:
            pending.extend(await self.input.get())
            while len(pending) >= 960:
                frame = bytes(pending[:960])
                del pending[:960]
                utterance = segments.push(frame)
                if utterance:
                    self.busy = True
                    text = await self.brain.free_speech.transcribe_pcm48(utterance)
                    if text:
                        await self.respond(text)
                    else:
                        self.busy = False
                    # Old audio queued while busy must not produce delayed duplicate turns.
                    pending.clear()
                    while not self.input.empty():
                        self.input.get_nowait()
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
