"""Turn-based calls with native/local ASR and independent original-audio capture."""

import asyncio
import audioop
import logging
import tempfile
import time
from collections import deque
from pathlib import Path

from .ai_access import AIUnavailable
from .config import ROOT
from .contact_calls import decode_pcm

log = logging.getLogger(__name__)


class SpeechSegments:
    """Segment 10ms mono PCM48 frames; ignore short clicks and retain leading audio."""

    def __init__(self, silence_frames=65):
        self.pre = deque(maxlen=20)
        self.frames = []
        self.voiced = self.silent = 0
        self.silence_frames = silence_frames
        self.noise = 4.0
        self.levels = deque(maxlen=150)
        self.level_count = 0

    def is_voiced(self, frame):
        level = audioop.rms(frame, 2)
        self.levels.append(level)
        self.level_count += 1
        if len(self.levels) >= 20 and self.level_count % 10 == 0:
            ordered = sorted(self.levels)
            # Learn steady background even if it exceeds the initial threshold.
            # Use the lower tail so syllable peaks do not set the noise floor.
            self.noise = min(48, ordered[len(ordered) // 5])
        threshold = max(12, min(150, self.noise * 3 + 6))
        return level >= threshold

    def flush(self):
        result = b"".join(self.frames) if self.voiced >= 10 else None
        self.frames.clear()
        self.voiced = self.silent = 0
        return result

    def push(self, frame):
        loud = self.is_voiced(frame)
        if not self.frames and not loud:
            self.pre.append(frame)
            return None
        if not self.frames:
            self.frames.extend(self.pre)
            self.pre.clear()
        self.frames.append(frame)
        self.voiced += int(loud)
        self.silent = 0 if loud else self.silent + 1
        if self.silent >= self.silence_frames or len(self.frames) >= 1500:
            return self.flush()
        return None


class RecordedReplyPause:
    """End a voice memo on a real pause, never at the ASR chunk's 15s boundary."""

    def __init__(self):
        self.voiced = self.silent = 0
        self.detector = SpeechSegments()

    def flush(self):
        ready = self.voiced >= 10
        self.voiced = self.silent = 0
        return b"recorded" if ready else None

    def push(self, frame):
        if self.detector.is_voiced(frame):
            self.voiced += 1
            self.silent = 0
        elif self.voiced:
            self.silent += 1
        if self.silent >= 150:
            return self.flush()
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
        self.peer_ended = asyncio.Event()
        self.output_drained = asyncio.Event()
        self.output_drained.set()
        self.sending = False
        self.prepared_intro = getattr(brain, "greeting_pcm", None)
        self.last_input = self.last_activity = time.monotonic()
        self.silence_prompts = 0
        self.metrics = dict(
            input_frames=0,
            low_frames=0,
            playback_frames=0,
            utterances=0,
            asr_errors=0,
            asr_ms=0,
            peak_rms=0,
            queue_dropped=0,
        )
        if brain is not None:
            brain.voice_diagnostics = self.metrics

    async def prepare_introduction(self):
        # Complete network synthesis before the phone rings, not after it is answered.
        if not self.record_only:
            prepare = getattr(self.brain.free_speech, "prepare_live", None)
            if prepare is not None:
                await prepare()
        if self.prepared_intro is None:
            self.prepared_intro = await self.synthesize(self.introduction)

    def remote_end(self):
        self.peer_ended.set()
        self.accepting = False
        self.output.clear()
        if not self.tasks:
            self.closed.set()

    async def finish_input(self):
        self.remote_end()
        try:
            await asyncio.wait_for(self.closed.wait(), 18)
        except TimeoutError:
            self.closed.set()

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
            self.metrics["input_frames"] += len(pcm) // 960
            self.last_input = time.monotonic()
            if self.input.full():
                self.input.get_nowait()
                self.metrics["queue_dropped"] += 1
            self.input.put_nowait(pcm)

    async def greet(self):
        # A greeting is speech to deliver, not a new owner instruction to the text agent.
        if self.prepared_intro is not None:
            await self.speak_pcm(self.prepared_intro)
        else:
            await self.speak(self.introduction)
        if not self.closed.is_set() and not self.peer_ended.is_set():
            self.brain.question_delivered = True
            self.accepting = True
            self.last_activity = time.monotonic()

    async def respond(self, text):
        try:
            answer = getattr(self.brain, "answer_voice", self.brain.answer)
            async with asyncio.timeout(12):
                reply = await answer(text)
        except (AIUnavailable, TimeoutError):
            self.record_only = True
            if hasattr(self.brain, "record_only"):
                self.brain.record_only = True
                self.brain.finished = True
                self.brain.outcome = "answer_unverified"
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
        if not self.peer_ended.is_set():
            await self.speak(reply)
        if getattr(self.brain, "finished", False) or (
            self.record_only and not self.recording_enabled
        ):
            self.closed.set()

    async def speak(self, reply):
        from .documents import PrivateReply

        if isinstance(reply, PrivateReply):
            delivery = getattr(self.brain, "private_delivery", None)
            if delivery is not None:
                await delivery(reply)
            # Speak only a fixed notification. Private excerpts stay out of TTS.
            reply = "Hujjatdan topilgan natija matn ko'rinishida saqlandi. Chat yoki Hujjatlar bo'limida o'qing."
        self.busy = True
        try:
            synthesis = asyncio.create_task(self.synthesize(reply))
            ended = asyncio.create_task(self.peer_ended.wait())
            try:
                async with asyncio.timeout(8):
                    done, _ = await asyncio.wait(
                        (synthesis, ended), return_when=asyncio.FIRST_COMPLETED
                    )
                    if ended in done:
                        return
                    pcm = await synthesis
            except TimeoutError:
                raise AIUnavailable(
                    "Ovoz tayyorlash vaqtida tugamadi. Natija va asl audio saqlanadi."
                ) from None
            finally:
                for task in (synthesis, ended):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(synthesis, ended, return_exceptions=True)
            await self.speak_pcm(pcm)
        finally:
            self.busy = False

    async def synthesize(self, text):
        with tempfile.TemporaryDirectory(dir=ROOT / "data", prefix="free-call-") as folder:
            path = Path(folder) / "reply.ogg"
            await self.brain.speech(text, path)
            return await decode_pcm(path)

    async def speak_pcm(self, pcm):
        self.busy = True
        try:
            self.speaking = True
            self.output_drained.clear()
            self.output.extend(pcm[i : i + 960].ljust(960, b"\0") for i in range(0, len(pcm), 960))
            if not pcm:
                raise ValueError("Savol ovozi bo'sh; qo'ng'iroq boshlanmadi.")
            while (
                not self.output_drained.is_set()
                and not self.closed.is_set()
                and not self.peer_ended.is_set()
            ):
                await asyncio.sleep(0.02)
            # Native send completion is not proof the person heard it, but the last
            # packet must leave the sender before listening or intentionally leaving.
            if not self.closed.is_set() and not self.peer_ended.is_set():
                await asyncio.sleep(0.12)
        finally:
            self.speaking = False
            self.busy = False
            self.last_activity = time.monotonic()

    async def process_utterance(self, utterance):
        self.busy = True
        self.metrics["utterances"] += 1
        self.last_activity = time.monotonic()
        try:
            if self.record_only:
                if hasattr(self.brain, "recorded_answer"):
                    await self.respond(None)
                else:
                    if not self.peer_ended.is_set():
                        await self.speak("Rahmat. Ovoz yozuvi chatga yuboriladi.")
                    self.closed.set()
                return
            started = time.monotonic()
            try:
                transcribe = getattr(self.brain, "transcribe_live_pcm48", None)
                if transcribe is None:
                    transcribe = getattr(self.brain, "transcribe_pcm48", None)
                if transcribe is None:
                    transcribe = self.brain.free_speech.transcribe_pcm48
                async with asyncio.timeout(16):
                    text = await transcribe(utterance)
            except (ValueError, TimeoutError, AIUnavailable):
                self.metrics["asr_errors"] += 1
                text = ""
            finally:
                self.metrics["asr_ms"] += round((time.monotonic() - started) * 1000)
            if text:
                self.misses = 0
                await self.respond(text)
                return
            self.misses += 1
            language = getattr(self.brain, "language", "uz")
            if self.metrics["asr_errors"] or self.misses >= 2:
                if hasattr(self.brain, "outcome"):
                    self.brain.outcome, self.brain.finished = "answer_unverified", True
                if not self.peer_ended.is_set():
                    await self.speak(
                        {
                            "uz": "Ovozni aniq taniy olmadim. Javob tasdiqlanmadi. Xayr.",
                            "en": "I could not recognize the speech. No answer was confirmed. Goodbye.",
                            "ru": "Не удалось распознать речь. Ответ не подтверждён. До свидания.",
                        }[language]
                    )
                self.closed.set()
            elif not self.peer_ended.is_set():
                await self.speak(
                    {
                        "uz": "Aniq tushunmadim. Iltimos, qayta va ravshanroq ayting.",
                        "en": "I could not understand clearly. Please say it again.",
                        "ru": "Не удалось разобрать речь. Пожалуйста, повторите.",
                    }[language]
                )
        finally:
            self.busy = False

    async def check_silence(self, segments):
        if self.busy or not self.accepting or segments.voiced or self.peer_ended.is_set():
            return
        if time.monotonic() - self.last_activity < 10 or not hasattr(
            self.brain, "repeat_or_finish"
        ):
            return
        if not self.silence_prompts and not self.record_only:
            self.silence_prompts += 1
            await self.speak(await self.brain.repeat_or_finish())
        else:
            self.brain.finished = True
            await self.speak(self.brain.no_answer_goodbye())
            self.closed.set()

    async def feed(self):
        segments, pending = SpeechSegments(silence_frames=100), bytearray()
        while not self.closed.is_set():
            try:
                packet = await asyncio.wait_for(self.input.get(), 0.1)
                pending.extend(packet)
            except TimeoutError:
                pass
            if self.record_only and not isinstance(segments, RecordedReplyPause):
                segments = RecordedReplyPause()
            while len(pending) >= 960 and not self.closed.is_set():
                frame = bytes(pending[:960])
                del pending[:960]
                level = audioop.rms(frame, 2)
                self.metrics["peak_rms"] = max(self.metrics["peak_rms"], level)
                self.metrics["low_frames"] += int(level < 150)
                before = segments.voiced
                utterance = segments.push(frame)
                if segments.voiced > before:
                    self.last_activity = time.monotonic()
                if utterance:
                    await self.process_utterance(utterance)
            # Telegram may stop sending packets on mute, network loss or hangup.
            # A real-clock endpoint must flush the final words without silent PCM.
            gap = 1.5 if self.record_only else 1.0
            if self.input.empty() and (
                self.peer_ended.is_set() or time.monotonic() - self.last_input >= gap
            ):
                utterance = segments.flush()
                if utterance and not self.closed.is_set():
                    await self.process_utterance(utterance)
                if self.peer_ended.is_set():
                    self.closed.set()
                    return
            await self.check_silence(segments)

    async def play(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            is_speech = bool(self.output)
            frame = self.output.popleft() if is_speech else bytes(960)
            self.sending = True
            try:
                await self.send_frame(frame)
            finally:
                self.sending = False
            if is_speech:
                self.metrics["playback_frames"] += 1
                if not self.output:
                    self.output_drained.set()
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
                self.remote_end()
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
