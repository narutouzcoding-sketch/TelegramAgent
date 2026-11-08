# TelegramAgent: to'liq ishlash, sarf va uzluksizlik auditi

2026-11-08, Asia/Tashkent. Windows, Python 3.12.13. Ushbu hisobot aynan mavjud loyiha va sozlangan bepul Gemini/mahalliy ovoz zanjiriga tegishli.

## Yakuniy holat

- **298 test o'tdi**, shu jumladan ushbu auditdagi **26 yangi regressiya**. Ruff, JavaScript sintaksisi va 16 ta Windows PowerShell 5.1 fayli parserdan o'tdi.
- Agent **Windows Task Scheduler** orqali yashirin ishlayapti: `TelegramAgent`, `Running`, `-m telegram_agent supervise`, `MultipleInstances=IgnoreNew`. Terminal oynasiga bog'liq emas. Windows loginida avtomatik boshlanadi.
- Ishchi API: `running`, xato bo'sh, ovoz yoqilgan, qayta ulanish 0, kutilayotgan vazifa 0. Oldingi eng oxirgi qo'ng'iroq raqami 8 saqlangan; ushbu audit yangi kontakt qo'ng'irog'i yoki xabari yubormadi.
- Foydalanuvchi papkasi va sessiyasi saqlandi, yangilashdan oldin mahalliy zaxira olindi. Maxfiy kalitlar, sessiya, bazalar va yozuvlar GitHub'ga chiqarilmaydi.

## Topilgan va tuzatilgan kamchiliklar

| Muammo | Tuzatish / tekshirilgan natija |
|---|---|
| Token hisoblagichi qayta ishga tushganda yo'qolgan | Gemini va mahalliy so'rovlar kunlik SQLite jurnalida saqlanadi. Agent to'xtaganida ham paneldan ko'rinadi. |
| Timeout yoki crash dan keyingi sarf0 deb ko'rinishi mumkin bo'lgan | API sarfni bermagan so'rov alohida noma'lum hisoblanadi; rejalashtirilgan rezerv ham saqlanadi. Bu provayder billing hisobi emas. |
| Bir nechta panel/worker ulanishi kunlik chegarani birga o'tishi mumkin bo'lgan | Ixtiyoriy lokal so'rov/token chegarasi SQLite `BEGIN IMMEDIATE` rezervi bilan tekshiriladi. Mahalliy model alohida hisoblanadi. |
| 429 kutish muddati qayta ishga tushirish bilan yo'qolgan | Gemini kutish muddati saqlanadi. Restart kvotani chetlab o'tish uchun ishlatilmaydi. |
| Javob verifieriga eski uzun suhbat qayta-qayta ketgan | Joriy nutq, so'nggi savol va ilgari tasdiqlangan qisqa javoblar beriladi; boshqa eski transkript yuborilmaydi. |
| Sarfni ko'rish ham AI so'rovini talab qilgan | `/usage` yoki “token sarfi” bazadan olinadi; yangi cloud so'rovi yo'q. |
| Kundalik/haftalik eslatma 3 xatodan keyin butunlay yo'qolgan | Xato o'sha bajarilish uchun qayd etiladi, keyingi kun/hafta saqlanadi. |
| Yetkazilmagan bir martalik eslatma ro'yxatdan yashirilgan | “Yetkazilmadi” holati va xabar bilan qayta eslatish tugmasi bor; boshqa vaqtga tahrirlash yoki bekor qilish mumkin. |
| Crash/lease tugashi/qo'lda to'xtatishdan keyin noaniq eslatma qayta telefon qilishi mumkin bo'lgan | O'sha eslatish xabar bilan tiklanadi. Kundalik rejaning kelgusi asl qo'ng'iroq rejimi o'zgarib ketmaydi. |
| Uchinchi audio yuborishda crash yozuvni abadiy `ready` holatida qoldirgan | “Tasdiqlanmagan/failed” deb ko'rsatiladi; aniq qayta yuborish amali mavjud. |
| Audio yoki natija yetkazuvchi worker jimgina o'lishi mumkin bo'lgan | Asosiy agent ularni kuzatadi. Ishlamayotgan worker bilan “hammasi ishlab turibdi” holati qoldirilmaydi. |
| Yakuniy tarmoq uzilishi agentni to'xtatib qo'ygan | Faqat texnik xatolarda2/5/15/30/60 soniyalik oraliqlar bilan yangi worker ochiladi. Eski native transport yopiladi. Kontaktga avval bajarilgan vazifa qayta terilmaydi. |
| Telegram cheklovi xotirada qolib, restartda unutilgan | Cheklov bazaga saqlanadi. Avtomatik restart uni o'chirmaydi. Qo'lda Start yangi account-health tekshiruvini boshlaydi; cheklov qolsa yana to'xtaydi. |
| Foydalanuvchining Stop qarori panel crashidan keyin yo'qolgan | Ishlash/to'xtash istagi bazada saqlanadi; qayta ishga tushish uni hurmat qiladi. |
| Autostart alohida `run` agentini boshlagan va panel bilan ziddiyatlashgan | Bitta panel+worker va crash nazoratchisi ishlatiladi; lock/IgnoreNew dublikat sessiyani to'sadi. Toza chiqish qayta boshlatilmaydi. 5 ketma-ket process-start xatosi cheksiz aylantirilmaydi. |

## Token bo'yicha haqiqiy dalil

Haqiqiy Gemini API ga **sun'iy** “Nonushtaga nima olib boray?” vazifasi va “Non olib keling.” javobi berildi. Natija tasdiqlandi; API **401 kirish + 28 chiqish tokeni**, 1 so'rov qaytardi. Bu aniq bitta sun'iy matn verifieri o'lchovi; o'rtacha haqiqiy qo'ng'iroq narxi yoki kontaktning javobi emas. Yangi adapterda hisob saqlandi; “token sarfi” uni o'qiganda0 qo'shimcha so'rov bo'ldi.

Hozirgi sozlama: `gemini-3.1-flash-lite`, history 10 xabar / 10000 belgi, matn chiqishi 1200 token, bepul Edge TTS, mahalliy `qwen3:4b-instruct` zaxirasi. Oddiy savol qo'ng'irog'ida har bir nutqni tanish va mazmunini tekshirish alohida so'rov bo'lishi mumkin; demak bir qo'ng'iroq doim 1 so'rov degani emas. Bepul mahalliy model CPU da sekinroq; jonli kontakt verifieri kvota tugaganda muvaffaqiyatni to'qimaydi.

`AI_DAILY_MAX_REQUESTS` va `AI_DAILY_MAX_TOKENS` `.env` ga qo'shildi. Hozir 0: mahalliy cap o'chirilgan. Bu o'zboshimcha past chegara bilan topshiriqlarni to'xtatmaslik uchun; kerak bo'lsa egasi o'zi belgilaydi. Rezerv taxminiy, provider usage aniq bo'lsa haqiqiy token bilan almashtiriladi. Ushbu sozlama billing kafolati emas. Oldingi yo'qolgan RAM hisoblarini tiklab bo'lmaydi; yangi jurnal ushbu yangilanishdan boshlab yig'iladi. OpenAI billing/Realtime sarfi ushbu Gemini jurnalining universal qamrovi emas; joriy bepul rejim OpenAI ni chaqirmaydi.

Google limitlari loyiha/model darajasida qo'llanadi; haqiqiy qolgan kvota bizning lokal hisoblagichdan hisoblanmaydi. [Rasmiy limitlar](https://ai.google.dev/gemini-api/docs/rate-limits?hl=en), [rasmiy narxlar](https://ai.google.dev/gemini-api/docs/pricing). Audio rezerv taxmini uchun [audio tokenlash hujjati](https://ai.google.dev/gemini-api/docs/audio) ishlatildi; servis qaytargan usage ustuvor.

## Tekshirilgan imkoniyatlar

Avvalgi 272 va yangi 26 regressiya: owner autentifikatsiyasi/pairing; begona buyruqlarni rad etish; kontakt topish va noaniq ismni aniqlashtirish; matn savoli; asl golos; savol+javob/verifier; qisman/rad/javobsiz holatlar; past ovoz/pauza/uzilish; eslatma va takroriy reja; bekor qilish/tahrirlash; token kvotasi/timeout/mahalliy zaxira; idempotent navbat; ovoz va natija yetkazish; restart/Stop; faqat tanlangan hujjat papkasi; path escape; shaxsiy hujjatning cloud/TTS ga chiqmasligi; backup; login/CSRF; brauzer formasi va mavjud audio pleyerining saqlanishi.

Brauzer QA paneli haqiqiy Telegram va shaxsiy ma'lumotlarni ochmadi. Kunlik token kartasi va failed eslatmaning “Xabar bilan qayta eslatish” → “Xabar bilan tiklash” holati tekshirildi. Bu mock serverda xabar yuborilganini bildirmaydi.

## Hali kafolatlanmagan joylar

1. **Kompyuter o'chiq/uyquda yoki Windows akkaunti tizimdan chiqqan bo'lsa mahalliy agent ishlamaydi.** Autostart server o'rnini bosmaydi. [Serverga o'tkazish fayllari](deploy/README.md) tayyor; Linux hostda ishga tushirilmagan, haqiqiy bepul 24/7 VM ajratilmagan. Server hisobi/SSH kirishi yo'q.
2. Inson bilan yangi native Telegram qo'ng'irog'i ushbu auditda bajarilmadi. Oldingi real TTS/ASR sun'iy audio dalili [CALL_AUDIO_FIX.md](CALL_AUDIO_FIX.md) da; yangi compressed verifier/API usage yuqorida.
3. Bepul rejim navbatli. Agent gapirayotganda ustma-ust nutqni to'liq barge-in/echo cancellation bilan tushunish qo'shilmagan; mustaqil yozuv saqlaydi.
4. ASR/model xato eshitishi mumkin. Asl golos saqlanadi, javob tasdiqlanmasa ochiq aytiladi. Birov javob bermasa uning o'rniga javob yaratib bo'lmaydi.
5. Tarmoq, Telegram maxfiyligi/ban, bepul API kvotasi va tashqi TTS uzluksizligi biz boshqaradigan koddan tashqarida. Xizmat qaytmaguncha yangi mazmuniy natija kafolatlanmaydi.
6. Tashqi send bilan SQLite yozuvi o'rtasidagi hard-crashda egaga xabar nusxasi kelishi mumkin. “Mutlaq exactly-once” da'vosi yo'q; noaniq eslatma qayta telefon qilinmaydi va kontakt vazifasi restartda qayta terilmaydi.
7. Disk/audio original yozuvlarini egasining ruxsatisiz avtomatik o'chirish qo'shilmadi. Zaxirada `.env` va Telegram sessiyasi yo'q; hostga ko'chirish uchun ularni alohida shaxsiy uzatish kerak.

Windows sozlamalari [Microsoft ScheduledTasks](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset?view=windowsserver2025-ps) asosida; faqat joriy foydalanuvchi darajasi, Windows paroli saqlanmaydi.
