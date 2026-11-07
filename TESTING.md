# Mahalliy tekshiruv natijasi

2026-11-07 kuni Windows muhitida bajarildi.

- Python 3.12.13
- py-tgcalls 3.0.0, NTgCalls 3.0.6, Telethon 1.45.0
- OpenAI SDK 3.46.0, aiohttp 3.14.5
- FFmpeg o'rnatilgan va topildi.
- NTgCalls native DLL importi: muvaffaqiyatli.
- 48 kHz mono PCM jonli jo'natish va qabul qilish konfiguratsiyalari: yaratildi.
- `ruff check telegram_agent tests`: muvaffaqiyatli.
- `python -m pytest -q -W error::RuntimeWarning`: **101 passed**, ogohlantirishsiz.
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
Gemini tool round-trip, Google thought signature larining saqlanishi, minimal reasoning va
generatsiya chegarasi, Gemini kvotasida profil almashtirmaslik, token chegarasida uzilgan tool
amalini bajarmaslik, OpenAI kalitisiz ovozli qo'ng'iroqni terishdan oldin rad etish tekshirildi.
Yangi `.env` maydonlarini qo'shishda oldingi maxfiy qiymatlar saqlanishi, Gemini-only matn
konfiguratsiyasi va suhbat kontekstini qisqartirish saqlangan rejalarni o'chirmasligi tekshirildi.
Telegram sessiyasi o'qishga yaroqli bo'lsa ham `freeze_since_date` mavjudligida login/start
bloklanishi, oddiy `restricted` bayrog'ini freeze deb adashtirmaslik, o'chirilgan/mavjud bo'lmagan
akkauntni ishga tushirmaslik va freeze aniqlanganda qo'ng'iroq/message worker larini yaratmaslik tekshirildi.
101 avtomatlashtirilgan testda tashqi xizmatlar mock bilan almashtirilgan. Yangi testlar vaqtinchalik sandbox bazasi haqiqiy bazani o'zgartirmasligini, terminal kiritish kutilayotganda eslatmalar ishlashini, qo'ng'iroqlar standart holatda o'chiqligini, ruxsatsiz kontakt uchun ovoz yaratilmasligini, FLOOD_WAIT muddati SQLite qayta ochilgach ham amal qilishini, cheklovdan keyin qayta so'rov bo'lmasligini, xabarlar oralig'ini, qo'ng'iroq chegaralarini va matnli rejimda native qo'ng'iroq transporti boshlanmasligini tekshiradi.

Alohida haqiqiy mahalliy sinov: Gemini javobi va reja tool chaqiruvi muvaffaqiyatli, qisqa terminal eslatmasi va faqat simulyatsiyadagi qo'ng'iroq muvaffaqiyatli. Telegramga xabar yoki qo'ng'iroq yuborilmadi, ishchi baza ishlatilmadi. OpenAI qisqa ovoz generatsiyasi billing/kvota xatosi bilan rad etildi; kalit/profil aylantirilmadi. Model ro'yxatda mavjudligi generatsiya uchun billing ishlashini tasdiqlamaydi.

## Sizning akkauntingiz bilan qolgan tekshiruvlar

Avtomatlashtirilgan testlar haqiqiy akkauntlaringizga ulanmaydi. Mahalliy `.env` qiymatlari ushbu
hisobotga ko'chirilmaydi. Quyidagilar mahalliy test bilan isbotlanmagan:

1. Haqiqiy Telegram shaxsiy qo'ng'irog'ini ulash va ikki tomonlama ovoz.
2. OpenAI akkauntingizda modellar va billing ishlashi.
3. O'zbekcha talaffuz/transkripsiya sifati va haqiqiy kechikish.
4. Haqiqiy eslatmaning belgilangan vaqtda telefoningizga yetib borishi.
5. Windows login paytida avtomatik boshlash (skript tayyor, vazifa hali o'rnatilmagan).
6. Boshqa haqiqiy Telegram foydalanuvchisiga xabarni qo'ng'iroq bilan yetkazish.
7. Gemini bilan uzoq suhbat sifati va real foydalanishdagi kvota sarfi; bitta generatsiya va reja tool sinovi o'tgan.

`README.md` dagi sozlash va ikki daqiqalik haqiqiy sinovni bajaring.

2026-11-07 kuni foydalanuvchi ruxsati bilan agent to'xtatilgach, haqiqiy Telegram sessiyasida
faqat o'qish tekshiruvi bajarildi. Server `get_me` orqali o'chirilmagan foydalanuvchini qaytardi,
ammo `help.getAppConfig` akkaunt muzlatilganini bildirdi. Yangilangan `telegram-status` shu holatni
to'g'ri aniqlab, ishni davom ettirmadi. Xabar/qo'ng'iroq yuborilmadi, apellyatsiya topshirilmadi,
sessiya va API kalitlari o'zgartirilmadi. Bu Telegram cheklovidan keyingi generatsiya yoki
qo'ng'iroq funksiyalarining muvaffaqiyatli ishlaganini anglatmaydi.

Foydalanuvchi apellyatsiyadan keyin akkaunt ochilganini bildirdi. Keyingi faqat o'qish tekshiruvida eski sessiya avtorizatsiyasiz bo'lib chiqdi. Bu qayta bloklanganlikni isbotlamaydi; normal mahalliy login kerak. Tiklangan akkauntdan jonli yuborish hali sinovdan o'tmagan. `.env` ga ehtiyot sozlamalari eski qiymatlarni o'zgartirmasdan qo'shildi; ovozli va kontakt qo'ng'iroqlari o'chiq.

## Bepul ovozli rejim tekshiruvi

OpenAI ning qisqa ovoz sinovida aniq HTTP 429, `credit_balance_exhausted`, `insufficient_quota` qaytdi. Foydalanuvchi faqat bepul yechimni tanladi; shundan keyin OpenAI so'rovi yuborilmadi.

`faster-whisper 1.2.1`, `ctranslate2 4.8.5`, `edge-tts 7.3.1`, `av 16.1.0` o'rnatildi. PyAV 19 bilan decoder mos kelmagani real sinovda topilib, `av>=11,<17` bilan tuzatildi; WAV decode testi bu moslikni tekshiradi. Multilingual Whisper `small` modeli `data/models/` ga yuklandi va CPU/int8 da ishga tushdi.

Haqiqiy mahalliy sinovda Edge o'zbekcha Madina ovozi yaratildi, Whisper ovozni matnga aylantirdi, Gemini javobi qaytdi va ovoz Telegram uchun PCM48 ga aylantirildi. Tanish taxminiy: sintetik namunada ayrim o'zbekcha so'zlar imlosi buzildi; jonli ovoz, ism va vaqtlar sifati tekshirilishi kerak. Telegram sessiyasi ochilmadi, xabar/qo'ng'iroq yuborilmadi, ishchi bazaga sinov rejalari yozilmadi.

Sinovdan keyin `.env` da `VOICE_PROVIDER=free`, `TEXT_PROVIDER=gemini`, `ENABLE_VOICE_CALLS=true`, `ENABLE_CONTACT_CALLS=false` saqlandi. Kalitlar va owner ID o'zgartirilmadi. Joriy agent sozlamalarni restartdan keyin oladi.

Yangi testlar: sukut/qisqa shovqinni tashlash, gap bo'lagining davomiyligi, bepul ovozda OpenAI ga murojaat qilmaslik, haqiqiy WAV decoder mosligi, navbatdagi ovozli javobni PCM bilan jo'natish, echo/ustma-ust ovozni tashlash va xatoda tasklarni tozalash. Jonli Telegram qo'ng'irog'i hali foydalanuvchi bilan sinovdan o'tishi kerak.
