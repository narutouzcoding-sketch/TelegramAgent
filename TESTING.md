# Mahalliy tekshiruv natijasi

2026-11-07 kuni Windows muhitida bajarildi.

- Python 3.12.13
- py-tgcalls 3.0.0, NTgCalls 3.0.6, Telethon 1.45.0
- OpenAI SDK 3.46.0, aiohttp 3.14.5
- FFmpeg o'rnatilgan va topildi.
- NTgCalls native DLL importi: muvaffaqiyatli.
- 48 kHz mono PCM jonli jo'natish va qabul qilish konfiguratsiyalari: yaratildi.
- `ruff check telegram_agent tests`: muvaffaqiyatli.
- `python -m pytest -q -W error::RuntimeWarning`: **67 passed**, ogohlantirishsiz.
- `uv lock --check`: muvaffaqiyatli.
- Barcha PowerShell skriptlarining sintaksisi: tekshirildi.

Testlar vaqt zonasi, saqlangan rejalar/eslatmalar, bekor qilish, lease orqali qayta tiklanish,
qayta urinishlar, takroriy jadval, egasining ID si, tool chaqiruvlari, Realtime sessiya ochilishi,
PCM 48/24 kHz almashinuvi, gapni bo'lish va uzun suhbat boshqa eslatmalarni bloklamasligini qamrab oladi.
Qo'shimcha tekshiruvlar: `.env` dan maxfiy qiymatlarni qayta so'ramasdan login, API juftligi va xalqaro
raqam shaklini tekshirish, API_ID_INVALID izohi, kontakt nomi noaniqligida qo'ng'iroqni rad etish,
faqat egasidan topshiriq olish, qo'ng'iroq navbati/idempotensiya/bekor qilish/qayta boshlash va
qabul qiluvchi qo'ng'iroqni erta uzganda xabar to'liq yetkazilgan deb belgilamaslik.
Mahalliy WAV faylini FFmpeg orqali haqiqiy PCM48 formatga aylantirish ham tekshirildi.
Bir martalik `/pair` bilan boshqaruvchi akkauntni aniqlash, bot/guruh/yordamchining o'zidan
kelgan ulash xabarini rad etish, Unicode xabarlarini xavfsiz qabul qilish, noto'g'ri owner ID
dan keyin loginni takrorlamasdan davom ettirish, username ning eski ID dan ustunligi tekshirildi.
AI zaxira kaliti tarmoq/5xx xatosida ishlashi, 429/kvota/billing/401/403 holatlarida kalit
aylanmasligi, Retry-After talabini aylanib o'tmaslik, audio faylni qayta urinishda boshidan
o'qish va Realtime kvota xatosining tushunarli izohi tekshirildi.
Tashqi xizmatlar mock bilan almashtirilgan; pulli API so'rovi yuborilmadi.

## Sizning akkauntingiz bilan qolgan tekshiruvlar

Avtomatlashtirilgan testlar haqiqiy akkauntlaringizga ulanmaydi. Mahalliy `.env` qiymatlari ushbu
hisobotga ko'chirilmaydi. Quyidagilar mahalliy test bilan isbotlanmagan:

1. Haqiqiy Telegram shaxsiy qo'ng'irog'ini ulash va ikki tomonlama ovoz.
2. OpenAI akkauntingizda modellar va billing ishlashi.
3. O'zbekcha talaffuz/transkripsiya sifati va haqiqiy kechikish.
4. Haqiqiy eslatmaning belgilangan vaqtda telefoningizga yetib borishi.
5. Windows login paytida avtomatik boshlash (skript tayyor, vazifa hali o'rnatilmagan).
6. Boshqa haqiqiy Telegram foydalanuvchisiga xabarni qo'ng'iroq bilan yetkazish.

`README.md` dagi sozlash va ikki daqiqalik haqiqiy sinovni bajaring.
