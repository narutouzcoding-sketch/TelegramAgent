"""Loopback-only Ollama adapter: no external key, billing or account rotation."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import aiohttp
from openai.types.chat import ChatCompletion

from .ai_access import AIUnavailable


async def ensure_local_server(url="http://127.0.0.1:11434"):
    if url.rstrip("/") not in {"http://127.0.0.1:11434", "http://localhost:11434"}:
        return False
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as client:

        async def ready():
            try:
                async with client.get(url + "/api/version") as response:
                    return response.status == 200
            except (aiohttp.ClientError, TimeoutError):
                return False

        if await ready():
            return True
        binary = shutil.which("ollama")
        if not binary and sys.platform == "win32":
            candidate = (
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
            )
            if candidate.is_file():
                binary = str(candidate)
        if not binary:
            return False
        env = dict(os.environ)
        env["OLLAMA_HOST"] = "127.0.0.1:11434"
        for key in (
            "GEMINI_API_KEY",
            "GROQ_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_BACKUP_API_KEYS",
            "TELEGRAM_API_HASH",
        ):
            env.pop(key, None)
        subprocess.Popen(
            [binary, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for _ in range(20):
            if await ready():
                return True
            await asyncio.sleep(0.2)
        return False


class LocalText:
    def __init__(self, settings):
        self.settings = settings
        self.lock = asyncio.Lock()
        self.http = None
        self.available = False

    async def create(self, instructions, messages, tools, max_output_tokens=768):
        async with self.lock:
            await ensure_local_server(self.settings.local_ai_url)
            if self.http is None:
                self.http = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=75, connect=3)
                )
            declarations = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"],
                    },
                }
                for t in tools
            ]
            prepared = []
            for original in messages:
                message = dict(original)
                if message.get("tool_calls"):
                    calls = []
                    for call in message["tool_calls"]:
                        fn = dict(call["function"])
                        if isinstance(fn.get("arguments"), str):
                            fn["arguments"] = json.loads(fn["arguments"])
                        calls.append({"function": fn})
                    message["tool_calls"] = calls
                prepared.append(message)
            body = {
                "model": self.settings.local_model,
                "messages": [{"role": "system", "content": instructions}, *prepared],
                "stream": False,
                "keep_alive": "15m",
                "options": {
                    "num_ctx": 4096,
                    "num_predict": min(max_output_tokens, 256),
                    "temperature": 0.2,
                    "num_thread": 6,
                    "num_gpu": 0,
                },
            }
            if declarations:
                body["tools"] = declarations
            try:
                async with self.http.post(
                    self.settings.local_ai_url.rstrip("/") + "/api/chat", json=body
                ) as response:
                    if response.status != 200:
                        raise AIUnavailable(
                            "Mahalliy AI modeli tayyor emas. local-ai.ps1 ni ishga tushiring."
                        )
                    value = await response.json()
            except (aiohttp.ClientError, TimeoutError):
                self.available = False
                raise AIUnavailable(
                    "Mahalliy AI ulanmagan yoki javob muddati tugadi. Ovoz yozuvi va saqlangan rejalar saqlanadi."
                ) from None
            self.available = True
            message = value.get("message", {})
            calls = [
                {
                    "id": "local-" + uuid.uuid4().hex,
                    "type": "function",
                    "function": {
                        "name": c["function"]["name"],
                        "arguments": c["function"]["arguments"]
                        if isinstance(c["function"].get("arguments"), str)
                        else json.dumps(c["function"].get("arguments", {}), ensure_ascii=False),
                    },
                }
                for c in message.get("tool_calls", [])
            ]
            return ChatCompletion.model_validate(
                {
                    "id": "local-" + uuid.uuid4().hex,
                    "object": "chat.completion",
                    "created": 0,
                    "model": self.settings.local_model,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "length"
                            if value.get("done_reason") == "length"
                            else "tool_calls"
                            if calls
                            else "stop",
                            "message": {
                                "role": "assistant",
                                "content": message.get("content", ""),
                                **({"tool_calls": calls} if calls else {}),
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": value.get("prompt_eval_count", 0),
                        "completion_tokens": value.get("eval_count", 0),
                        "total_tokens": value.get("prompt_eval_count", 0)
                        + value.get("eval_count", 0),
                    },
                }
            )

    async def close(self):
        if self.http is not None:
            await self.http.close()
