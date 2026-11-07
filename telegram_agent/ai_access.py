"""Authorized backup credentials for transient failures, never quota/rate-limit rotation."""

import asyncio
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import aiohttp
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

log = logging.getLogger(__name__)

QUOTA_CODES = {
    "insufficient_quota",
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
    "usage_limit_exceeded",
}


def backup_delay(headers):
    value = (headers or {}).get("retry-after") or (headers or {}).get("Retry-After")
    if not value:
        return 0.5
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = (
                parsedate_to_datetime(value).astimezone(UTC) - datetime.now(UTC)
            ).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 0.5
    # If the provider requests a longer pause, stop this attempt instead of bypassing it.
    return max(0.5, delay) if delay <= 30 else None


def public_ai_error(error=None, *, code=None):
    code = code or getattr(error, "code", None)
    status = getattr(error, "status_code", None)
    if isinstance(error, AIUnavailable):
        return str(error)
    if code in QUOTA_CODES:
        return "OpenAI API krediti, billing yoki foydalanish limiti tugagan. Billing/limitni tekshiring; boshqa kalitga avtomatik o'tilmadi."
    if status == 429 or code in {"rate_limit_exceeded", "rate_limit_error", "slow_down"}:
        return "OpenAI so'rov tezligi limiti vaqtincha to'ldi. Biroz kutib qayta urinib ko'ring; kalit almashtirilmadi."
    if status == 401 or code in {"invalid_api_key", "invalid_api_key_error"}:
        return "OpenAI API kaliti qabul qilinmadi. .env dagi kalitni tekshiring."
    if status == 403:
        return "OpenAI ruxsatni rad etdi. Akkaunt, loyiha va modelga ruxsatlarni tekshiring."
    return "AI xizmatida ulanish yoki vaqtinchalik xizmat xatosi yuz berdi. Qayta urinib ko'ring."


class AIUnavailable(RuntimeError):
    """A deliberately sanitized explanation suitable for the owner."""


class AIClientPool:
    def __init__(self, settings):
        keys = tuple(
            dict.fromkeys(key for key in (settings.openai_key, *settings.backup_openai_keys) if key)
        )
        self.clients = [AsyncOpenAI(api_key=key, timeout=60, max_retries=0) for key in keys]
        self.current = self.clients[0] if self.clients else None
        self.model = settings.realtime_model

    def candidates(self):
        if self.current is None:
            raise AIUnavailable(
                "Bu ovozli funksiya uchun OPENAI_API_KEY kerak. Gemini matnli suhbat va rejalar uchun ulangan."
            )
        return [self.current] + [client for client in self.clients if client is not self.current]

    async def request(self, operation):
        clients = self.candidates()
        for index, client in enumerate(clients):
            try:
                value = await operation(client)
            except (APIConnectionError, APIStatusError) as exc:
                transient = (
                    isinstance(exc, APIConnectionError) or getattr(exc, "status_code", 0) >= 500
                ) and getattr(exc, "code", None) not in QUOTA_CODES
                if not transient or index + 1 == len(clients):
                    raise
                delay = backup_delay(getattr(getattr(exc, "response", None), "headers", None))
                if delay is None:
                    raise
                log.warning("Transient AI failure; trying configured backup index=%s", index + 1)
                await asyncio.sleep(delay)
            else:
                self.current = client
                return value

    async def connect_realtime(self, http):
        clients = self.candidates()
        for index, client in enumerate(clients):
            try:
                socket = await http.ws_connect(
                    "wss://api.openai.com/v1/realtime",
                    params={"model": self.model},
                    headers={"Authorization": f"Bearer {client.api_key}"},
                    heartbeat=20,
                    receive_timeout=90,
                    max_msg_size=8 * 1024 * 1024,
                )
            except aiohttp.WSServerHandshakeError as exc:
                if exc.status < 500 or index + 1 == len(clients):
                    raise AIUnavailable(
                        public_ai_error(
                            code="rate_limit_exceeded"
                            if exc.status == 429
                            else "invalid_api_key"
                            if exc.status == 401
                            else None
                        )
                    ) from None
                delay = backup_delay(exc.headers)
                if delay is None:
                    raise AIUnavailable(public_ai_error()) from None
                await asyncio.sleep(delay)
            except (aiohttp.ClientConnectionError, TimeoutError):
                if index + 1 == len(clients):
                    raise AIUnavailable(public_ai_error()) from None
                await asyncio.sleep(0.5)
            else:
                self.current = client
                return socket

    async def close(self):
        for client in self.clients:
            await client.close()
