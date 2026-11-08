# Mahalliy tekshiruv natijasi


Eng so‘nggi to‘liq tekshiruv: **298 test**, 26 yangi regressiya; mahalliy autostart va yashirin xizmat ishga tushdi. [PROFESSIONAL_AUDIT.md](PROFESSIONAL_AUDIT.md). Quyidagi qaydlar avvalgi bosqichlarga tegishli.

2026-11-07–08 kunlari Windows muhitida bajarildi.

## Qo‘ng‘iroq audio zanjiri — 2026-11-08

272 test; yangi 35 regressiya, brauzerda savol rejimi, real TTS/ASR bilan sun’iy ovoz zanjiri. Kontaktga yangi qo‘ng‘iroq qilinmadi. [Dalil va chegaralar](CALL_AUDIO_FIX.md).

## Savolga javobni tekshirish — 2026-11-08

237 ta testli yakuniy to‘plam; yangi 33 ta javob/natija regressiyasi. Real Gemini bilan sun’iy misolda salom → javobsiz, bitta qism → qisman, qolgan qism → dalilli javob holatlari tasdiqlandi. Bu haqiqiy kontakt javobi emas. [Batafsil](ANSWER_FIX.md).

## Asl ovoz va hujjatlar — yakuniy tekshiruv

`qa.ps1`: **204 passed**, 0 failure/error/skipped. Yangi 25 ta regressiya, shu jumladan 5 ta mikrofon holatining Node sinovi, haqiqiy FFmpeg OGG, private hujjatning cloud/TTS ga chiqmasligi, PDF/DOCX, backup poygasi va owner outbox tekshirildi. Brauzerda sintetik audio yuklash/saqlash/topshiriq, mahalliy qidiruv/qayd va backup havolasi ishladi. Haqiqiy qurilma mikrofoni va inson bilan native Telegram qo‘ng‘irog‘i bu natijaga kirmaydi. Tafsilotlar [FEATURES.md](FEATURES.md).

## Professional QA — 2026-11-08

179 ta test o‘tdi. Yangi 20 ta foydalanuvchi ssenariysining dastlabki ishga tushirishida 5 ta nosozlik takrorlandi; tuzatishdan keyin 20/20 o‘tdi. Qo‘shimcha 10 ta regressiya testi mustaqil tester va audit topilmalarini qamraydi. Batafsil matritsa, topilgan 10 kamchilik, brauzer kuzatuvlari va jonli tekshiruv chegaralari [QA.md](QA.md) da.

## Avvalgi barqarorlik tekshiruvi — 2026-11-08

149 ta test o'tdi (`-W error::RuntimeWarning`), Ruff, JavaScript, PowerShell parser va lock tekshiruvlari o'tdi. Yangi testlar asl PCM yozuvini AI dan ajratish, uzilgan yozuvni tiklash, haqiqiy FFmpeg OGG/Opus kodlash, faqat egasiga voice_note yuborish, fayllarni autentifikatsiya bilan berish, katalogdan tashqariga chiqishni rad etish, tokensiz yozib olish, past ovozdagi qisqa javob, 15 soniyadan uzun ovozni kesmaslik, oddiy hangup ni AI xatosi demaslik, navbatdagi xabarni yo'qotmaslik, to'liq transkriptlarni qayta tool kontekstiga yubormaslik, bitta yozish amali uchun bitta AI so'rovi, Gemini 429 da mahalliy model va Retry-After, ovozli sessiyada CPU modelni kutmaslik, native ASR va kvotada mahalliy zaxirani tekshiradi.

Haqiqiy ovoz sifati tekshiruvida Whisper `small` sintetik o'zbekcha ikki jumlani buzib tanidi. Shu audio Gemini native audio orqali “Nonushtaga nima olib boray?” va “Ertaga soat 9 da menga kitob oqishni eslat.” deb tanildi (3.78 va 1.53 soniya). Bu ikki sintetik namuna; shovqinli haqiqiy telefon nutqining barcha holatlari isbotlanmagan.

Ollama rasmiy winget paketi o'rnatildi. Birinchi `qwen3:4b` tegi thinking model bo'lib chiqdi; u ortiqcha reasoning sabab sekin yoki tugallanmagan javob berdi. Mos `qwen3:4b-instruct` tanlandi, rasmiy qatlamlar IPv4 orqali yuklanib SHA-256 tekshirildi. Yakuniy mahalliy sinovda “Salom!” 9.52 soniyada, reja qo'shish 10.69 soniyada bajarildi; Google so'rovi soni nol, vaqtinchalik bazada reja saqlandi. Tajriba thinking modeli tozalandi. Mahalliy fallback bepul, lekin CPU sabab sekinroq.

Haqiqiy Telegram yetkazish sinovida “SINOV — haqiqiy qo'ng'iroq emas” deb belgilangan sintetik 9 soniyalik golos egasining chatiga yuborildi va baza `sent` holatini qayd etdi. U haqiqiy suhbatdoshning ovozi sifatida ko'rsatilmagan. Brauzerda shu fayl audio/ogg sifatida yuklandi, ijro etildi va 9.3905 soniya davomiylik ko'rsatdi. Har 5 soniyalik yangilash pleyerni yopib yuborishi topilib tuzatildi; tafsilotlar ochiq va ijro pozitsiyasi saqlangani tekshirildi.

Yordamchi akkaunti Telegramga ulangan. Asl ovoz yozuvi, yangi ASR va mahalliy instruct modeli yoqilgan. Kalitlar, owner ID va mavjud kontaktlar saqlangan. Foydalanuvchidan yangi haqiqiy qo'ng'iroq bilan sinab ko'rish so'ralgan; bu yozuv tayyorlanayotganida tasdiq hali kelmagan. Quyidagi eski qaydlar o'z davridagi holatni tasvirlaydi.

## Web boshqaruv paneli

128 ta test o'tdi. Panel testlari autentifikatsiya, CSRF, boshqa origin'dan yozishni rad etish, login urinishlarini cheklash, logout, maxfiy fayllarni bermaslik, reja/eslatma tahrirlash, kontaktni tekshirish va jonli ruxsat ro'yxatini yangilash, ruxsatni Telegramsiz bekor qilish, takroriy qo'ng'iroqni bostirish, keyingi vaqtga saqlash, kechikkan topshiriqni bekor qilish va eski bazaga ma'lumot yo'qotmasdan yangi ustunlar qo'shishni qamraydi. Username boshqa ID ga o'tsa ovoz yaratilishidan oldin rad etilishi tekshirildi.

`ruff check .`, JavaScript fayllarida `node --check`, PowerShell parser tekshiruvi, `uv lock --check` va `git diff --check` o'tdi. Haqiqiy Gemini bilan o'zgartirilgan tool sxemasi bitta qisqa suhbatda qabul qilindi; haqiqiy reja yoki qo'ng'iroq topshirig'i yaratilmagan.

Izolyatsiyalangan sinov bazasi bilan brauzerda parol orqali kirish, reja yaratish va suhbat yuborish tekshirildi. 1440px kompyuter va 390px telefon ko'rinishlari ko'rib chiqildi; telefon ko'rinishi gorizontal chiqib ketmadi. Ko'rinish rasmlarida sinov ma'lumotlari bor. Asosiy ma'lumotlar bazasiga sinov rejalari yoki kontaktlar qo'shilmadi.

Haqiqiy mahalliy panel `127.0.0.1:8765` da ochildi. Navbat va kutilayotgan eslatmalar bo'sh ekanligi tekshirilgach, API orqali haqiqiy Telegram agenti ishga tushirildi: holati `running` bo'ldi. Keyin `stop` muvaffaqiyatli qaytib, holati `stopped` bo'ldi. Ushbu tekshiruvda kontaktga qo'ng'iroq yoki Telegram xabari yuborilmadi. Manifest va ikki PNG ikoni HTTP 200 qaytardi. Haqiqiy panelga brauzerdan kirildi va foydalanuvchi uchun ochiq qoldirildi. Keyingi tuzatishda panel ochilishi bilan Telegram worker ham avtomatik boshlanadi; 14-panel testi qayta start takroriy worker yaratmasligini va panel yopilganda worker ham yopilishini tekshiradi.

LAN'dagi boshqa telefon, HTTPS, PWA o'rnatish va server deployment bu sinovga kirmaydi. Quyidagi eski tekshiruv qaydlari o'zlari bajarilgan bosqichni tasvirlaydi; joriy panel tekshiruvi yuqorida.

Panel avtomatik start tuzatishidan keyin haqiqiy brauzerda `Agent ishlayapti` holati ko'rindi. Suhbat formasidan yuborilgan savolga haqiqiy Gemini javobi qaytdi; mock ishlatilmadi. Telegram agenti tekshiruv oxirida ishlayotgan holatda qoldirildi. Ushbu tekshiruvda ovozli qo'ng'iroq boshlanmadi.

- Python 3.12.13
- py-tgcalls 3.0.0, NTgCalls 3.0.6, Telethon 1.45.0
- OpenAI SDK 3.46.0, aiohttp 3.14.5
- FFmpeg o'rnatilgan va topildi.
- NTgCalls native DLL importi: muvaffaqiyatli.
- 48 kHz mono PCM jonli jo'natish va qabul qilish konfiguratsiyalari: yaratildi.
- `ruff check telegram_agent tests`: muvaffaqiyatli.
- `python -m pytest -q`: **149 passed**. Panelning 14 ta testi `-W error` bilan ham o'tdi.
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

## Kontakt bilan savol-javob va ko'p tilli ovoz

128 ta test o'tdi (`-W error::RuntimeWarning`). Yangi testlar: inglizcha savol, bitta javobdan keyin tugash, qisqa suhbat chegarasi, qabul qiluvchi matnidan egasi amallarini chaqirmaslik, faqat tanlangan peer'dan ovoz olish, transportni yopish, haqiqiy javobni sayt xotirasi va egasi xabariga qaytarish, to'g'ridan-to'g'ri username topshirig'ining idempotensiyasi, katta suhbat JSON saqlanishi, kontakt import/deduplikatsiya/o'chirilganni qayta olmaslik, 200 tadan ortiq kontaktni saqlash, faqat kontakt API sini o'qish va parol fayli o'zgarganda eski sessiyalarni bekor qilish.

Haqiqiy mahalliy integratsiya: Gemini nonushta savolini inglizchaga o'tkazdi va AI ekanini aytadigan kirish matnini yaratdi; Edge inglizcha ovoz yaratdi; shu ovoz Whisper orqali “Please bring bread and eggs for breakfast.” deb to'g'ri tanildi; Gemini egasiga o'zbekcha xulosa tayyorladi. Izolyatsiyalangan bazada barcha owner tool deklaratsiyalari bilan haqiqiy qisqa javob olindi. Pulli OpenAI API ishlatilmadi.

Haqiqiy panel avtomatik Telegramga ulandi. Yordamchi akkauntining 198 ta kontakti mahalliy bazaga olindi; avval o'chirilgan akkaunt qayta qo'shilmadi. Keyin foydalanuvchi alohida mahalliy oynada boshqa akkauntga muvaffaqiyatli kirdi. Dastlab ID mos kelmasligi importni to'xtatgan edi; kontakt manbasi va boshqaruvchi roli ajratilib tuzatildi. Shu sessiyadan 27 yangi kontakt olindi, jami 225 ta bo'ldi. Boshqaruvchi ID o'zgartirilmadi. Qo'shimcha testlar kontakt manbasi boshqaruv huquqi olmasligini, sessiya yo'qligida login boshlanmasligini va ovoz uzilganda ham tanilgan qisman javob egasiga qaytarilishini tekshiradi. Dasturchi sinovida boshqa odamga qo'ng'iroq qilinmadi. Shaxsiy jonli qo'ng'iroqdagi ikki tomonlama ovoz, Telegram maxfiylik ruxsatlari va haqiqiy kechikish avtomatlashtirilgan mock orqali to'liq isbotlanmaydi.
