# Gemini sarfini kamaytirish

2026-11-10 kuni joriy kompyuterda tejamkor sozlama qo'llandi:

| Sozlama | Qiymat |
|---|---|
| `GEMINI_AUDIO_ASR` | `false` — ovozni mavjud Whisper small taniydi |
| `TEXT_MAX_OUTPUT_TOKENS` | `768` |
| `HISTORY_MESSAGES` | `6` |
| `HISTORY_MAX_CHARS` | `6000` |
| `VOICE_MAX_OUTPUT_TOKENS` | `384` |
| `VOICE_CONTEXT_TOKENS` | `4000` |

Whisper CPU/int8 bilan ikki ishchi oqimdan foydalanadi. Bu Google'ga ovoz tanish so'rovlarini kamaytiradi, ammo ovoz tanish kompyuter yoki server resursini ishlatadi. Jonli nutqning aniqligi va kechikishi tanlangan qurilmada tekshiriladi.

Panel suhbatida ham `/plans`, `/reminders`, `/contacts`, `/contacts ISM`, `/calls`, shuningdek `Rejalarim`, `Eslatmalarim`, `Kontaktlarim` kabi aniq ro'yxat so'rovlari mahalliy bazadan javob oladi. Bunday javoblar keyingi AI so'roviga qayta yuborilmaydi. Reja yaratish, eslatma qo'shish va boshqa erkin matnli ko'rsatmalar odatdagi tekshiriladigan AI yo'lidan o'tadi.

Tekshiruvda ikkita jonli panel ro'yxat so'rovi **0 qo'shimcha Gemini so'rovi** ishlatdi. Mavjud 7.6 soniyali sinov audiosi ham **0 Gemini so'rovi** bilan matnga aylantirildi. Bu barcha foydalanish holatlari uchun bir xil foiz tejalishini anglatmaydi.

`/usage` dastur hisoblagan kunlik sarfni ko'rsatadi. Bu Google hisobidagi qolgan kvota emas; dasturdan tashqaridagi diagnostika yoki boshqa ilovalar so'rovlari unga kirmaydi.

Google limitlari loyiha bo'yicha qo'llanadi, API kaliti bo'yicha emas. Bir loyihaning qo'shimcha kalitlari uning kvotasini oshirmaydi. Alohida loyihalarning limitlari va foydalanish shartlari alohida tekshiriladi; ko'p hisob doimiy yoki cheksiz xizmat kafolati bermaydi. [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits?hl=en).

Yanada ko'proq mustaqillik uchun yetarli resursli serverda mahalliy matn modeli qo'shilishi mumkin. Bunday model provayderning token kvotasini ishlatmaydi, lekin server CPU/RAM va ishlash tezligiga bog'liq. Hozir yangi Ollama modeli o'rnatilmadi. Server hali ajratilmagan.
