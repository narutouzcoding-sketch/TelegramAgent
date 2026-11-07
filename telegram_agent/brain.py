import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI


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
        self.client = AsyncOpenAI(api_key=settings.openai_key, timeout=60, max_retries=1)
        self.lock = asyncio.Lock()

    def instructions(self):
        now = datetime.now(ZoneInfo(self.settings.timezone)).isoformat()
        return (
            "Siz foydalanuvchining shaxsiy AI yordamchisisiz. Asosan tabiiy o'zbek tilida, "
            "qisqa va tushunarli gapiring. O'zingizni AI sifatida tanishtiring. "
            "Savollarga javob bering, rejalarni yuriting va eslatmalar saqlang. "
            f"Hozirgi vaqt: {now}; vaqt zonasi: {self.settings.timezone}. "
            "Bugun/ertaga va n daqiqadan keyin degan vaqtlarni shu soatdan hisoblang. "
            "Vaqt yoki sana noaniq bo'lsa savol bering. O'tgan vaqtga eslatma yaratmang. "
            "Eslatish usuli aytilmasa call ni tanlang. Reja va eslatma alohida obyektlar. "
            "Faqat tool muvaffaqiyatli natija qaytarganidan keyin saqlandi/bajarildi deb ayting. "
            "Saqlandi desa ID, aniq sana-vaqt va takrorlanishni ayting. "
            "Bekor qilishdan oldin obyekt ID sini ro'yxatdan tekshiring. "
            "Internetdan jonli qidirish funksiyangiz yo'q; yangiliklarni tekshirdim demang. "
            "Kompyuter o'chsa yoki uxlab qolsa qo'ng'iroq qila olmaysiz. "
            "Qo'ng'iroqda suhbatni tabiiy davom ettiring; inson ovoziga taqlid qilmang. "
            "Maxfiy kalit yoki Telegram login kodini so'ramang."
        )

    def execute_tool(self, name, arguments, call_id):
        cached = self.store.cached_tool(call_id)
        if cached is not None:
            return cached
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            actions = {
                "create_reminder": self.store.add_reminder,
                "list_reminders": self.store.list_reminders,
                "cancel_reminder": self.store.cancel_reminder,
                "add_plan": self.store.add_plan,
                "list_plans": self.store.list_plans,
                "complete_plan": self.store.complete_plan,
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
            history = self.store.history()
            self.store.remember("user", text)
            items = history + [{"role": "user", "content": text}]
            for _ in range(8):
                response = await self.client.responses.create(
                    model=self.settings.text_model,
                    instructions=self.instructions(),
                    input=items,
                    tools=TOOLS,
                    store=False,
                    max_output_tokens=1800,
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

    async def transcribe(self, path):
        with path.open("rb") as audio:
            response = await self.client.audio.transcriptions.create(
                model=self.settings.transcribe_model,
                file=audio,
                prompt="O'zbek tilidagi shaxsiy suhbat, rejalar, savollar va eslatmalar.",
            )
        return response.text

    async def speech(self, text, path):
        async with self.client.audio.speech.with_streaming_response.create(
            model=self.settings.tts_model,
            voice="coral",
            input=text[:4000],
            response_format="opus",
            instructions="O'zbek tilida aniq, samimiy, tabiiy ohangda gapiring.",
        ) as response:
            await response.stream_to_file(path)
