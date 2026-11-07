# Mahalliy tekshiruv natijasi

2026-11-07 kuni Windows muhitida bajarildi.

- Python 3.12.13
- py-tgcalls 3.0.0, NTgCalls 3.0.6, Telethon 1.45.0
- OpenAI SDK 3.46.0, aiohttp 3.14.5
- FFmpeg o'rnatilgan va topildi.
- NTgCalls native DLL importi: muvaffaqiyatli.
- 48 kHz mono PCM jonli jo'natish va qabul qilish konfiguratsiyalari: yaratildi.
- `ruff check telegram_agent tests`: muvaffaqiyatli.
- `python -m pytest -q -W error::RuntimeWarning`: **28 passed**, ogohlantirishsiz.
- `uv lock --check`: muvaffaqiyatli.
- Barcha PowerShell skriptlarining sintaksisi: tekshirildi.

Testlar vaqt zonasi, saqlangan rejalar/eslatmalar, bekor qilish, lease orqali qayta tiklanish,
qayta urinishlar, takroriy jadval, egasining ID si, tool chaqiruvlari, Realtime sessiya ochilishi,
PCM 48/24 kHz almashinuvi, gapni bo'lish va uzun suhbat boshqa eslatmalarni bloklamasligini qamrab oladi.
Tashqi xizmatlar mock bilan almashtirilgan; pulli API so'rovi yuborilmadi.

## Sizning akkauntingiz bilan qolgan tekshiruvlar

Telegram API ID/hash, yordamchi akkaunt login sessiyasi, asosiy akkaunt ID si va OpenAI API kaliti
hali kiritilmagan. `doctor` shu to'rtta sozlama yo'qligini to'g'ri aniqladi. Shu sababli quyidagilar
mahalliy test bilan isbotlanmagan:

1. Haqiqiy Telegram shaxsiy qo'ng'irog'ini ulash va ikki tomonlama ovoz.
2. OpenAI akkauntingizda modellar va billing ishlashi.
3. O'zbekcha talaffuz/transkripsiya sifati va haqiqiy kechikish.
4. Haqiqiy eslatmaning belgilangan vaqtda telefoningizga yetib borishi.
5. Windows login paytida avtomatik boshlash (skript tayyor, vazifa hali o'rnatilmagan).

`README.md` dagi sozlash va ikki daqiqalik haqiqiy sinovni bajaring.
