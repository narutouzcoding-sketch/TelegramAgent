"""Authenticated control panel sharing one running Telegram agent process."""

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import replace
from pathlib import Path

from aiohttp import web
from openai import APIError
from telethon import errors

from .ai_access import AIUnavailable, public_ai_error
from .app import AgentApp
from .brain import Brain
from .config import ROOT
from .contact_calls import RecipientResolver, relay_text
from .store import Store

log = logging.getLogger(__name__)
ASSETS = Path(__file__).with_name("panel_web")
SESSION_KEY = web.RequestKey("panel_session", dict)


class PanelControl:
    def __init__(self, settings, root=ROOT, agent_factory=AgentApp):
        self.settings, self.root, self.agent_factory = settings, root, agent_factory
        (root / "data").mkdir(parents=True, exist_ok=True)
        self.store = Store(root / "data" / "agent.sqlite3", settings.timezone)
        self.idle_brain = None
        self.agent = self.task = None
        self.phase, self.last_error = "stopped", ""
        self.chat_lock = asyncio.Lock()
        self.control_lock = asyncio.Lock()
        self.audio = {}
        self.shutdown = asyncio.Event()

    @property
    def running(self):
        return self.task is not None and not self.task.done()

    @property
    def connected(self):
        return self.running and self.agent.ready.is_set()

    def runtime_settings(self):
        ids = tuple(
            dict.fromkeys(
                (*self.settings.allowed_call_user_ids, *self.store.approved_contact_ids())
            )
        )
        return replace(self.settings, allowed_call_user_ids=ids, enable_contact_calls=bool(ids))

    def refresh_settings(self):
        if self.running:
            cfg = self.runtime_settings()
            self.agent.settings = self.agent.policy.settings = self.agent.brain.settings = cfg

    async def start(self):
        async with self.control_lock:
            if self.running:
                return {"started": False, "already_running": True}
            self.agent = self.agent_factory(self.runtime_settings())
            self.phase, self.last_error = "connecting", ""
            self.task = asyncio.create_task(self._run_agent())
            return {"started": True}

    async def _run_agent(self):
        try:
            await self.agent.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.phase = "error"
            self.last_error = (
                str(exc)
                if isinstance(exc, (ValueError, AIUnavailable))
                else "Agent ishga tushmadi: " + type(exc).__name__
            )
            log.warning("Panel agent failed type=%s", type(exc).__name__)
        else:
            self.phase = "stopped"

    async def stop(self):
        async with self.control_lock:
            if self.running:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self.task = self.agent = None
            self.phase = "stopped"
            return {"stopped": True}

    def require_agent(self):
        if not self.connected:
            raise ValueError("Avval agentni ishga tushiring va Telegram ulanishini kuting.")
        self.agent.policy.ensure_active()
        return self.agent

    async def ask(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError("Xabar 1..12000 belgidan iborat bo'lsin.")
        if self.chat_lock.locked():
            raise ValueError("Oldingi javob tayyorlanyapti. Biroz kuting.")
        async with self.chat_lock:
            if self.connected:
                brain = self.agent.brain
            else:
                if self.idle_brain is None:
                    self.idle_brain = Brain(
                        replace(
                            self.settings, enable_voice_calls=False, enable_contact_calls=False
                        ),
                        self.store,
                    )
                brain = self.idle_brain
            return {"reply": await brain.answer(text.strip())}

    def contact(self, contact_id):
        row = next((c for c in self.store.list_contacts() if c["id"] == int(contact_id)), None)
        if row is None:
            raise ValueError("Kontakt topilmadi.")
        return row

    async def verify_contact(self, contact_id, allow):
        row = self.contact(contact_id)
        if not allow:
            result = self.store.set_contact_permission(row["id"], row["telegram_id"], False)
        else:
            agent = self.require_agent()
            me = (
                await agent.policy.action(agent.telegram.get_me)
                if agent.recipient_resolver is None
                else None
            )
            resolver = agent.recipient_resolver or RecipientResolver(
                agent.telegram, self.store, me.id
            )
            try:
                user = await agent.policy.action(lambda: resolver.resolve(row["reference"]))
            except errors.PhoneNotOccupiedError:
                raise ValueError(
                    "Telegram bu raqamdan akkaunt topmadi. @username ishlating."
                ) from None
            except (errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
                raise ValueError(
                    "Telegram username topilmadi. To'g'ri @username kiriting."
                ) from None
            if user.id == self.settings.owner_id:
                raise ValueError("O'zingizga qo'ng'iroq qilish uchun alohida tugmadan foydalaning.")
            result = self.store.set_contact_permission(row["id"], user.id, True)
        self.refresh_settings()
        return result

    def call_contact(self, contact_id, message, due_at, request_id):
        agent = self.require_agent()
        if not agent.settings.enable_voice_calls:
            raise ValueError("Ovozli rejim sozlanmagan. free-voice.ps1 orqali avval ovozni sinang.")
        if not isinstance(message, str) or not message.strip() or len(message) > 1500:
            raise ValueError("Aytiladigan xabar 1..1500 belgidan iborat bo'lsin.")
        row = self.contact(contact_id)
        if not row["call_allowed"] or not row["telegram_id"]:
            raise ValueError("Avval kontaktning Telegram akkauntini tekshirib, ruxsat bering.")
        if not isinstance(request_id, str) or not 16 <= len(request_id) <= 100:
            raise ValueError("So'rov identifikatori yo'q. Sahifani yangilang.")
        fingerprint = hashlib.sha256(f"{row['id']}|{message}|{due_at}".encode()).hexdigest()
        key = "panel-call:" + request_id
        cached = self.store.cached_tool(key)
        if cached:
            if cached["fingerprint"] != fingerprint:
                raise ValueError("Bu identifikator boshqa so'rovga tegishli.")
            return cached["result"]
        self.refresh_settings()
        result = self.store.queue_contact_call(
            row["reference"], message, due_at or None, row["telegram_id"]
        )
        self.store.cache_tool(key, {"fingerprint": fingerprint, "result": result})
        return result

    async def preview(self, message):
        agent = self.require_agent()
        if self.settings.voice_provider != "free":
            raise ValueError("Paneldagi ovoz sinovi uchun avval bepul ovoz rejimini tanlang.")
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 1500:
            raise ValueError("Avval aytiladigan xabarni kiriting (1500 belgigacha).")
        now = time.monotonic()
        for token, (path, created) in list(self.audio.items()):
            if now - created > 1800:
                path.unlink(missing_ok=True)
                del self.audio[token]
        if len(self.audio) >= 10:
            raise ValueError("Ovoz sinovlari chegarasiga yetildi. Keyinroq yana sinang.")
        folder = self.root / "data" / "panel-audio"
        folder.mkdir(exist_ok=True)
        token = secrets.token_urlsafe(20)
        path = folder / (token + ".ogg")
        await agent.brain.speech(relay_text(agent.owner_name, message.strip()), path)
        self.audio[token] = (path, now)
        return {"url": "/api/audio/" + token}

    def state(self):
        phase = "running" if self.connected else self.phase
        cfg = self.runtime_settings()
        return {
            "agent": {
                "phase": phase,
                "running": self.connected,
                "error": self.last_error,
                "owner_name": self.agent.owner_name if self.connected else "",
                "timezone": cfg.timezone,
                "text_provider": cfg.resolved_text_provider,
                "voice_provider": cfg.voice_provider,
                "voice_enabled": cfg.enable_voice_calls,
                "active_call": bool(self.connected and self.agent.call_lock.locked()),
                "max_calls_per_hour": cfg.max_calls_per_hour,
            },
            "plans": self.store.list_plans(),
            "reminders": self.store.list_reminders(),
            "contacts": self.store.list_contacts(),
            "calls": self.store.list_contact_calls(),
            "messages": self.store.history(40),
        }

    async def close(self):
        await self.stop()
        if self.idle_brain:
            await self.idle_brain.close()
        for path, _ in self.audio.values():
            path.unlink(missing_ok=True)
        self.store.close()


def create_panel(control, password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
    sessions, attempts = {}, {}

    @web.middleware
    async def guard(request, handler):
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("Origin")
            if origin and origin != f"{request.scheme}://{request.host}":
                raise web.HTTPForbidden(text="Origin rejected")
            if request.content_type != "application/json":
                raise web.HTTPBadRequest(text="JSON required")
        token = request.cookies.get("ta_session", "")
        session = sessions.get(token)
        if session and session["expires"] < time.monotonic():
            del sessions[token]
            session = None
        public = request.path in {
            "/",
            "/app.js",
            "/style.css",
            "/icon.svg",
            "/icon-192.png",
            "/icon-512.png",
            "/manifest.webmanifest",
            "/sw.js",
            "/api/login",
            "/api/session",
        }
        if not public:
            if session is None:
                return web.json_response({"error": "Panelga qayta kiring."}, status=401)
            if request.method not in {"GET", "HEAD"} and not hmac.compare_digest(
                request.headers.get("X-CSRF-Token", ""), session["csrf"]
            ):
                raise web.HTTPForbidden(text="CSRF rejected")
        request[SESSION_KEY] = session
        try:
            response = await handler(request)
        except (ValueError, KeyError, TypeError) as exc:
            response = web.json_response(
                {"error": str(exc) if isinstance(exc, ValueError) else "Maydonlarni tekshiring."},
                status=400,
            )
        except (APIError, AIUnavailable) as exc:
            response = web.json_response({"error": public_ai_error(exc)}, status=502)
        except web.HTTPException:
            raise
        except Exception as exc:
            log.warning("Panel request failed type=%s", type(exc).__name__)
            response = web.json_response(
                {"error": "Amal bajarilmadi. Agent holatini tekshiring."}, status=500
            )
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
            }
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    app = web.Application(middlewares=[guard], client_max_size=32000)

    async def static(request):
        name = request.path.lstrip("/") or "index.html"
        return web.FileResponse(ASSETS / name)

    async def session_status(request):
        value = request[SESSION_KEY]
        return web.json_response(
            {"authenticated": bool(value), "csrf": value["csrf"] if value else None}
        )

    async def login(request):
        now = time.monotonic()
        ip = request.remote or "unknown"
        recent = [stamp for stamp in attempts.get(ip, []) if now - stamp < 300]
        if len(recent) >= 8:
            return web.json_response({"error": "Ko'p urinish. 5 daqiqa kuting."}, status=429)
        attempts[ip] = recent + [now]
        data = await request.json()
        supplied = data.get("password", "")
        if not isinstance(supplied, str) or len(supplied) > 256:
            raise ValueError("Parol noto'g'ri.")
        check = await asyncio.to_thread(
            hashlib.pbkdf2_hmac, "sha256", supplied.encode(), salt, 200000
        )
        if not hmac.compare_digest(check, digest):
            return web.json_response({"error": "Parol noto'g'ri."}, status=401)
        attempts.pop(ip, None)
        for key, value in list(sessions.items()):
            if value["expires"] < now:
                del sessions[key]
        if len(sessions) >= 20:
            sessions.pop(next(iter(sessions)))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        sessions[token] = {"csrf": csrf, "expires": now + 8 * 3600}
        response = web.json_response({"authenticated": True, "csrf": csrf})
        response.set_cookie(
            "ta_session",
            token,
            httponly=True,
            samesite="Strict",
            secure=request.secure,
            max_age=8 * 3600,
        )
        return response

    async def dispatch(request):
        action = request.match_info["action"]
        data = await request.json() if request.method == "POST" else {}
        if action == "state" and request.method == "GET":
            result = control.state()
        elif action == "logout":
            sessions.pop(request.cookies.get("ta_session", ""), None)
            response = web.json_response({"ok": True})
            response.del_cookie("ta_session")
            return response
        elif action == "start":
            result = await control.start()
        elif action == "stop":
            result = await control.stop()
        elif action == "shutdown":
            result = await control.stop()
            control.shutdown.set()
        elif action == "chat":
            result = await control.ask(data.get("text"))
        elif action == "plan":
            result = (
                control.store.update_plan(int(data["id"]), data["title"], data.get("details", ""))
                if data.get("id")
                else control.store.add_plan(data["title"], data.get("details", ""))
            )
        elif action == "complete-plan":
            result = control.store.complete_plan(int(data["id"]))
        elif action == "reminder":
            args = {k: data[k] for k in ("title", "due_at", "repeat", "mode")}
            result = (
                control.store.update_reminder(int(data["id"]), **args)
                if data.get("id")
                else control.store.add_reminder(**args)
            )
        elif action == "cancel-reminder":
            result = control.store.cancel_reminder(int(data["id"]))
        elif action == "contact":
            result = control.store.save_contact(data["name"], data["reference"])
        elif action == "verify-contact":
            result = await control.verify_contact(data["id"], data.get("allow") is True)
        elif action == "delete-contact":
            result = control.store.delete_contact(int(data["id"]))
            control.refresh_settings()
        elif action == "call":
            result = control.call_contact(
                data["contact_id"], data.get("message"), data.get("due_at"), data.get("request_id")
            )
        elif action == "preview":
            result = await control.preview(data.get("message"))
        elif action == "cancel-call":
            result = control.store.cancel_contact_call(int(data["id"]))
        elif action == "call-owner":
            agent = control.require_agent()
            if not agent.settings.enable_voice_calls:
                raise ValueError("Ovozli rejim hozir o'chirilgan.")
            if agent.call_lock.locked():
                raise ValueError("Hozir qo'ng'iroq faol.")
            agent.spawn(agent.safe_call("Salom! Men AI yordamchingizman. Qanday yordam beray?"))
            result = {"started": True}
        elif action == "hangup":
            await control.require_agent().hangup()
            result = {"stopped": True}
        else:
            raise web.HTTPNotFound()
        return web.json_response(result)

    async def audio(request):
        entry = control.audio.get(request.match_info["token"])
        if not entry or not entry[0].exists():
            raise web.HTTPNotFound()
        return web.FileResponse(entry[0], headers={"Content-Type": "audio/ogg"})

    for route in (
        "/",
        "/app.js",
        "/style.css",
        "/icon.svg",
        "/icon-192.png",
        "/icon-512.png",
        "/manifest.webmanifest",
        "/sw.js",
    ):
        app.router.add_get(route, static)
    app.router.add_get("/api/session", session_status)
    app.router.add_post("/api/login", login)
    app.router.add_get("/api/{action:state}", dispatch)
    app.router.add_post("/api/{action}", dispatch)
    app.router.add_get("/api/audio/{token}", audio)

    async def cleanup(_):
        await control.close()

    app.on_cleanup.append(cleanup)
    return app


async def serve_panel(settings, host="127.0.0.1", port=8765):
    (ROOT / "data").mkdir(exist_ok=True)
    path = ROOT / "data" / "panel-password.txt"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(18), encoding="utf-8")
        path.chmod(0o600)
    password = path.read_text(encoding="utf-8").strip()
    if len(password) < 12:
        raise ValueError("Panel paroli kamida 12 belgili bo'lsin: data/panel-password.txt")
    control = PanelControl(settings)
    runner = web.AppRunner(create_panel(control, password), access_log=None)
    try:
        await runner.setup()
        await web.TCPSite(runner, host, port).start()
        # Opening the control panel should also bring the Telegram worker online.
        # Keep the HTTP server available even if Telegram login needs attention.
        await control.start()
        print(f"Boshqaruv paneli: http://127.0.0.1:{port}", flush=True)
        print(
            "Panel paroli: data/panel-password.txt faylida. API kalitlari panelga chiqarilmaydi.",
            flush=True,
        )
        if host == "0.0.0.0":
            print(
                f"LAN: http://KOMPYUTER_IP:{port} (bir xil tarmoq). HTTPS serverga ko'chirganda sozlanadi.",
                flush=True,
            )
        await control.shutdown.wait()
    finally:
        await runner.cleanup()
