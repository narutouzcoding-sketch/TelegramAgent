"""Telegram PCM48 <-> OpenAI Realtime PCM24; no audio files for live calls."""

import asyncio
import audioop
import base64
import json
from collections import deque
from contextlib import suppress

import aiohttp

from .ai_access import AIUnavailable, public_ai_error
from .brain import TOOLS


class VoiceSession:
    def __init__(self, brain, send_frame, introduction):
        self.brain = brain
        self.send_frame = send_frame
        self.introduction = introduction
        self.input_queue = asyncio.Queue(maxsize=300)
        self.output = deque()
        self.tail = b""
        self.input_resampler = None
        self.output_resampler = None
        self.ws = None
        self.tasks = []
        self.http = None
        self.last_item = None
        self.played_ms = 0
        self.generating_item = None
        self.interrupted_items = set()
        self.pending_transcripts = {}
        self.error = None
        self.closed = asyncio.Event()

    async def start(self):
        cfg = self.brain.settings
        self.http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=15)
        )
        try:
            self.ws = await self.brain.ai.connect_realtime(self.http)
            await self.send(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "instructions": self.brain.instructions(),
                        "output_modalities": ["audio"],
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "transcription": {"model": cfg.transcribe_model},
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.5,
                                    "silence_duration_ms": 650,
                                    "create_response": True,
                                    "interrupt_response": True,
                                },
                            },
                            "output": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "voice": cfg.voice,
                            },
                        },
                        "tools": [{k: v for k, v in t.items() if k != "strict"} for t in TOOLS],
                        "tool_choice": "auto",
                        "max_output_tokens": cfg.voice_max_output_tokens,
                        "truncation": {
                            "type": "retention_ratio",
                            "retention_ratio": 0.8,
                            "token_limits": {"post_instructions": cfg.voice_context_tokens},
                        },
                    },
                }
            )
            async with asyncio.timeout(20):
                async for message in self.ws:
                    event = self.decode(message)
                    if event.get("type") == "error":
                        raise AIUnavailable(
                            public_ai_error(code=event.get("error", {}).get("code"))
                        )
                    if event.get("type") == "session.updated":
                        break
                else:
                    raise RuntimeError("Realtime session closed during configuration")
            # Restore recent text context; never resend historical audio.
            for entry in self.brain.store.context(cfg.history_messages, cfg.history_max_chars):
                await self.send(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": entry["role"],
                            "content": [
                                {
                                    "type": "input_text"
                                    if entry["role"] == "user"
                                    else "output_text",
                                    "text": entry["content"],
                                }
                            ],
                        },
                    }
                )
            self.tasks = [
                asyncio.create_task(self.guarded(self.receive)),
                asyncio.create_task(self.guarded(self.feed)),
                asyncio.create_task(self.guarded(self.play)),
            ]
            await self.say(self.introduction)
        except BaseException:
            await self.close()
            raise

    def accept_pcm48(self, pcm):
        if not self.closed.is_set():
            if self.input_queue.full():
                self.input_queue.get_nowait()
            self.input_queue.put_nowait(pcm)

    async def send(self, event):
        await self.ws.send_json(event)

    async def say(self, instructions):
        await self.send(
            {
                "type": "response.create",
                "response": {"instructions": self.brain.instructions() + "\n" + instructions},
            }
        )

    async def feed(self):
        pending = bytearray()
        while True:
            pcm = await self.input_queue.get()
            converted, self.input_resampler = audioop.ratecv(
                pcm, 2, 1, 48000, 24000, self.input_resampler
            )
            pending.extend(converted)
            if len(pending) >= 2400:  # 50ms at 24kHz, batch socket traffic
                await self.send(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pending).decode("ascii"),
                    }
                )
                pending.clear()

    async def play(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            if self.output:
                item, frame = self.output.popleft()
                if item != self.last_item:
                    self.last_item, self.played_ms = item, 0
                await self.send_frame(frame)
                self.played_ms += 10
            else:
                await self.send_frame(bytes(960))
            self.flush_transcripts()
            deadline += 0.01
            await asyncio.sleep(max(0, deadline - loop.time()))
            if loop.time() - deadline > 0.1:
                deadline = loop.time()

    def add_output(self, item_id, pcm24):
        pcm48, self.output_resampler = audioop.ratecv(
            pcm24, 2, 1, 24000, 48000, self.output_resampler
        )
        data = self.tail + pcm48
        end = len(data) // 960 * 960
        for i in range(0, end, 960):
            self.output.append((item_id, data[i : i + 960]))
        self.tail = data[end:]
        if len(self.output) > 6000:
            raise RuntimeError("Audio playback buffer exceeded 60 seconds")

    async def receive(self):
        async for message in self.ws:
            await self.handle(self.decode(message))
        raise ConnectionError("Realtime connection closed")

    async def handle(self, event):
        kind = event.get("type")
        if kind == "response.output_audio.delta":
            if event["item_id"] in self.interrupted_items:
                return
            self.generating_item = event["item_id"]
            self.add_output(event["item_id"], base64.b64decode(event["delta"]))
        elif kind == "response.output_audio.done":
            if event["item_id"] in self.interrupted_items:
                return
            if self.tail:
                self.output.append((event["item_id"], self.tail.ljust(960, b"\0")))
                self.tail = b""
            self.output_resampler = None
            self.generating_item = None
        elif kind == "input_audio_buffer.speech_started":
            # Drop unplayed audio immediately, then remove that unheard text from model context.
            item = self.output[0][0] if self.output else self.generating_item
            self.output.clear()
            self.tail = b""
            self.output_resampler = None
            self.generating_item = None
            if item:
                self.interrupted_items.add(item)
                self.pending_transcripts.pop(item, None)
                await self.send(
                    {
                        "type": "conversation.item.truncate",
                        "item_id": item,
                        "content_index": 0,
                        "audio_end_ms": self.played_ms if item == self.last_item else 0,
                    }
                )
            self.last_item = None
            self.played_ms = 0
        elif kind == "input_audio_buffer.speech_stopped":
            await self.send(
                {
                    "type": "session.update",
                    "session": {"type": "realtime", "instructions": self.brain.instructions()},
                }
            )
        elif kind == "conversation.item.input_audio_transcription.completed":
            self.brain.store.remember("user", event.get("transcript", ""))
        elif kind == "response.output_audio_transcript.done":
            item = event.get("item_id")
            if item and item not in self.interrupted_items:
                self.pending_transcripts[item] = event.get("transcript", "")
                self.flush_transcripts()
        elif kind == "response.done":
            response = event.get("response", {})
            if response.get("status") == "failed":
                raise AIUnavailable(
                    public_ai_error(
                        code=((response.get("status_details") or {}).get("error") or {}).get("code")
                    )
                )
            calls = [
                item for item in response.get("output", []) if item.get("type") == "function_call"
            ]
            for call in calls:
                result = self.brain.execute_tool(call["name"], call["arguments"], call["call_id"])
                await self.send(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps(result, ensure_ascii=False),
                        },
                    }
                )
            if calls:
                await self.send({"type": "response.create"})
        elif kind == "error":
            # Do not log the event payload, which may contain user input.
            code = event.get("error", {}).get("code", "unknown")
            if code not in {
                "response_cancel_not_active",
                "conversation_already_has_active_response",
            }:
                raise AIUnavailable(public_ai_error(code=code))

    @staticmethod
    def decode(message):
        if message.type == aiohttp.WSMsgType.TEXT:
            return json.loads(message.data)
        if message.type in {
            aiohttp.WSMsgType.CLOSE,
            aiohttp.WSMsgType.CLOSED,
            aiohttp.WSMsgType.ERROR,
        }:
            raise ConnectionError("Realtime websocket disconnected")
        return {}

    def flush_transcripts(self):
        queued_items = {item for item, _ in self.output}
        for item in list(self.pending_transcripts):
            if item not in queued_items and item != self.generating_item:
                self.brain.store.remember("assistant", self.pending_transcripts.pop(item))

    async def guarded(self, coroutine_factory):
        try:
            await coroutine_factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = public_ai_error(exc)
            self.closed.set()

    async def close(self):
        self.closed.set()
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self.tasks.clear()
        if self.ws:
            await self.ws.close()
        if self.http:
            await self.http.close()
