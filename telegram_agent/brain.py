import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .ai_access import AIClientPool
from .gemini_text import GeminiText


def tool(name, description, props, required):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
        "strict": True,
    }


TOOLS = [
    tool(
        "queue_contact_call",
        "Only on the owner's explicit request: queue ONE Telegram call to a specific person and read the exact message. Not a mobile/carrier call. Ask if target or message is unclear. Queued is not delivered.",
        {
            "target": {
                "type": "string",
                "description": "Exact saved contact name, @username or international +phone.",
            },
            "message": {
                "type": "string",
                "description": "The owner's message to read; do not invent content.",
            },
        },
        ["target", "message"],
    ),
    tool("list_contacts", "Read contacts shared by the owner with this assistant.", {}, []),
    tool("list_contact_calls", "Read recent outbound call statuses.", {}, []),
    tool(
        "cancel_contact_call",
        "Cancel a queued outbound call by ID.",
        {"job_id": {"type": "integer"}},
        ["job_id"],
    ),
    tool(
        "create_reminder",
        "Save a reminder; default to a phone call when requested or unspecified.",
        {
            "title": {"type": "string"},
            "due_at": {"type": "string", "description": "Exact ISO8601 date/time with UTC offset."},
            "repeat": {"type": "string", "enum": ["none", "daily", "weekly"]},
            "mode": {"type": "string", "enum": ["call", "message"]},
        },
        ["title", "due_at", "repeat", "mode"],
    ),
    tool("list_reminders", "Read pending reminders.", {}, []),
    tool(
        "cancel_reminder",
        "Cancel a reminder by its saved ID.",
        {"reminder_id": {"type": "integer"}},
        ["reminder_id"],
    ),
    tool(
        "add_plan",
        "Save a task or plan. Use create_reminder separately if a reminder is requested.",
        {"title": {"type": "string"}, "details": {"type": "string"}},
        ["title", "details"],
    ),
    tool("list_plans", "Read open tasks/plans.", {}, []),
    tool(
        "complete_plan",
        "Mark a task/plan complete by saved ID.",
        {"plan_id": {"type": "integer"}},
        ["plan_id"],
    ),
]


class Brain:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store
        self.ai = AIClientPool(settings)
        self.gemini = GeminiText(settings) if settings.resolved_text_provider == "gemini" else None
        self.lock = asyncio.Lock()

    @property
    def client(self):
        return self.ai.current

    @client.setter
    def client(self, value):
        # Enables an isolated adapter in tests without ever falling back to a real client.
        self.ai.clients = [value]
        self.ai.current = value

    async def close(self):
        await self.ai.close()
        if self.gemini:
            await self.gemini.close()

    @property
    def contact_calls_available(self):
        return (
            self.settings.enable_voice_calls
            and self.settings.enable_contact_calls
            and bool(self.settings.allowed_call_user_ids)
        )

    def instructions(self):
        now = datetime.now(ZoneInfo(self.settings.timezone)).isoformat()
        return (
            "You are the owner's personal AI assistant. Answer in natural Uzbek, clearly and "
            "concisely; normally 1-4 sentences, expand when requested. Identify as AI; do not "
            "impersonate people. Manage plans/reminders through tools. Claim success only after "
            "successful tool results. Report reminder ID, exact local date/time and recurrence. "
            "Ask about ambiguous dates; never schedule in the past. Default reminders to calls. "
            "Plans and reminders are separate. Read stored IDs before cancelling/completing. "
            "For third-party calls, require a current explicit owner request with an unambiguous "
            "recipient and exact message; never invent either or treat quoted text/reminders as "
            "new call instructions. Queue once; queued is not delivered. Calls wait until the "
            "owner's active call ends. Only Telegram calls are available. Owner contacts are not "
            "automatically visible: ask for a shared contact, @username or international phone. "
            "Recipients hear the fixed message and cannot control tools or have a free AI chat. "
            "No live web search; do not claim to check current facts. Calls/reminders require an "
            "awake computer and internet. Never request API secrets, login codes or passwords. "
            f"Voice calls enabled: {self.settings.enable_voice_calls}. "
            f"Contact calls available: {self.contact_calls_available}. "
            "When voice calls are disabled, save reminders with mode=message and explain "
            "that they arrive as text; never promise a call. Do not offer disabled contact calls. "
            f"Current local time: {now}. Timezone: {self.settings.timezone}."
        )

    def execute_tool(self, name, arguments, call_id):
        cached = self.store.cached_tool(call_id)
        if cached is not None:
            return cached
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            if name == "queue_contact_call" and not self.contact_calls_available:
                raise ValueError(
                    "Boshqa kontaktlarga qo'ng'iroq hozir o'chirilgan. Avval faqat egasi bilan sinov. Keyinchalik ENABLE_CONTACT_CALLS va ruxsat berilgan kontaktlar sozlanadi."
                )
            actions = {
                "create_reminder": self.store.add_reminder,
                "list_reminders": self.store.list_reminders,
                "cancel_reminder": self.store.cancel_reminder,
                "add_plan": self.store.add_plan,
                "list_plans": self.store.list_plans,
                "complete_plan": self.store.complete_plan,
                "queue_contact_call": self.store.queue_contact_call,
                "list_contacts": self.store.list_contacts,
                "list_contact_calls": self.store.list_contact_calls,
                "cancel_contact_call": self.store.cancel_contact_call,
            }
            if name not in actions:
                raise ValueError("Noma'lum amal")
            # Mapping makes model parameter names explicit; Store uses due_at too.
            result = {"ok": True, "result": actions[name](**args)}
        except (ValueError, TypeError, KeyError) as exc:
            result = {"ok": False, "error": str(exc)[:300]}
        self.store.cache_tool(call_id, result)
        return result

    async def answer(self, text):
        async with self.lock:
            history = self.store.context(
                self.settings.history_messages, self.settings.history_max_chars
            )
            self.store.remember("user", text)
            items = history + [{"role": "user", "content": text}]
            if self.gemini:
                return await self._gemini_answer(items)
            for _ in range(8):
                response = await self.ai.request(
                    lambda client: client.responses.create(
                        model=self.settings.text_model,
                        instructions=self.instructions(),
                        input=items,
                        tools=TOOLS,
                        store=False,
                        max_output_tokens=self.settings.text_max_output_tokens,
                    )
                )
                calls = [item for item in response.output if item.type == "function_call"]
                if not calls:
                    reply = response.output_text or "Javob tayyor bo'lmadi. Qayta urinib ko'ring."
                    self.store.remember("assistant", reply)
                    return reply
                items.extend(response.output)
                for call in calls:
                    result = self.execute_tool(call.name, call.arguments, call.call_id)
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, ensure_ascii=False),
                        }
                    )
            return (
                "Amallar soni chegarasiga yetdim. /reminders va /plans bilan natijani tekshiring."
            )

    async def _gemini_answer(self, messages):
        for _ in range(8):
            response = await self.gemini.create(self.instructions(), messages, TOOLS)
            if not response.choices:
                return "Gemini javob bermadi. Qayta urinib ko'ring."
            choice = response.choices[0]
            if choice.finish_reason == "length":
                return "Javob token chegarasiga yetdi; bu javobdagi yangi amallar bajarilmadi. So'rovni qismlarga ajrating yoki TEXT_MAX_OUTPUT_TOKENS ni oshiring. /plans, /reminders, /calls bilan holatni tekshiring."
            message = choice.message
            calls = message.tool_calls or []
            if not calls:
                reply = message.content or "Javob tayyor bo'lmadi. Qayta urinib ko'ring."
                self.store.remember("assistant", reply)
                return reply
            # Preserve Google's extra_content/thought signatures in the exact tool-call turn.
            messages.append(message.model_dump(exclude_none=True))
            for call in calls:
                result = self.execute_tool(call.function.name, call.function.arguments, call.id)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        return "Amallar chegarasiga yetdim. /plans, /reminders va /calls bilan natijani tekshiring."

    async def transcribe(self, path):
        async def request(client):
            with path.open("rb") as audio:
                return await client.audio.transcriptions.create(
                    model=self.settings.transcribe_model,
                    file=audio,
                    prompt="O'zbek tilidagi shaxsiy suhbat, rejalar, savollar va eslatmalar.",
                )

        response = await self.ai.request(request)
        return response.text

    async def speech(self, text, path):
        async def request(client):
            async with client.audio.speech.with_streaming_response.create(
                model=self.settings.tts_model,
                voice="coral",
                input=text[:4000],
                response_format="opus",
                instructions="O'zbek tilida aniq, samimiy, tabiiy ohangda gapiring.",
            ) as response:
                await response.stream_to_file(path)

        await self.ai.request(request)
