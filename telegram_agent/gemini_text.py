"""Gemini text/tool adapter using Google's documented OpenAI-compatible endpoint."""

from openai import APIError, AsyncOpenAI

from .ai_access import AIUnavailable


class GeminiText:
    def __init__(self, settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=60,
            max_retries=0,
        )

    async def create(self, instructions, messages, tools):
        declarations = []
        for tool in tools:
            parameters = {
                key: value
                for key, value in tool["parameters"].items()
                if key != "additionalProperties"
            }
            declarations.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": parameters,
                    },
                }
            )
        try:
            return await self.client.chat.completions.create(
                model=self.settings.gemini_model,
                messages=[{"role": "system", "content": instructions}, *messages],
                tools=declarations,
                tool_choice="auto",
                max_tokens=self.settings.text_max_output_tokens,
                reasoning_effort=self.settings.gemini_reasoning_effort,
            )
        except APIError as error:
            status = getattr(error, "status_code", None)
            if status == 429:
                explanation = "Gemini API kvotasi yoki so'rov tezligi limiti to'ldi. Google AI Studio dagi kvota/billingni tekshiring; kalit/profil almashtirilmadi."
            elif status in {401, 403}:
                explanation = "Gemini API kaliti yoki ruxsati qabul qilinmadi. GEMINI_API_KEY va loyiha ruxsatlarini tekshiring."
            elif status == 404:
                explanation = "Gemini modeli akkauntingizda mavjud emas. GEMINI_MODEL va Google AI Studio ruxsatlarini tekshiring."
            elif status == 400:
                explanation = "Gemini so'rov sozlamasini qabul qilmadi. Model va reasoning sozlamasini tekshiring."
            else:
                explanation = (
                    "Gemini xizmatida vaqtinchalik ulanish xatosi yuz berdi. Qayta urinib ko'ring."
                )
            raise AIUnavailable(explanation) from None

    async def close(self):
        await self.client.close()
