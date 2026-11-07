# TelegramAgent

Telegram ichida yozishadigan, ovozli xabarga javob beradigan, haqiqiy shaxsiy qo'ng'iroqlarni qabul qiladigan va eslatish uchun sizga qo'ng'iroq qiladigan AI yordamchi.

## Hozirgi holat

Kod, Python 3.12 virtual muhiti, o'rnatilgan kutubxonalar, qat'iy versiyalar yozilgan `uv.lock`, sozlash skriptlari va mahalliy testlar tayyor. Haqiqiy Telegram login va OpenAI API kaliti kiritilmaguncha agent faol emas. Jonli qo'ng'iroq va AI ovoz sifati sizning akkauntlaringiz bilan tekshirilishi kerak.

## Nima kerak?

1. **Yordamchi uchun alohida oddiy Telegram akkaunti.** O'zingizning asosiy akkauntingizdan shu akkauntga qo'ng'iroq qilasiz. Agent shu alohida akkauntga kiradi. BotFather tokeni kerak emas. Telegram `phone.requestCall` usulini faqat foydalanuvchi akkauntlariga beradi: [rasmiy Telegram API](https://core.telegram.org/method/phone.requestCall).
2. [my.telegram.org/apps](https://my.telegram.org/apps) sahifasidan `api_id` va `api_hash`.
3. [OpenAI API key](https://platform.openai.com/api-keys), tegishli modelga ruxsat va API uchun ishlaydigan billing. Chatdagi obunangiz yoki shu suhbat agent uchun API kaliti vazifasini bajarmaydi. API foydalanish xarajatlari akkauntingizda hisoblanadi; platforma hisobingizdagi billing/ruxsatlarni tekshiring.
4. Asosiy Telegram akkauntingizning `@username` yoki raqamli ID si. Agent faqat tasdiqlangan raqamli ID bilan ishlaydi.
5. Kompyuter yoqilgan, uyqu holatiga kirmagan va internetga ulangan bo'lishi kerak. FFmpeg bu kompyuterda mavjud. Windows uchun NTgCalls native kutubxonasi o'rnatilgan.

Kalit, login kodi, 2FA paroli va Telegram sessiyasini chatga yubormang. Ularni faqat mahalliy sozlash oynasida kiriting.

## Boshlash

PowerShell oching:

```powershell
cd 'D:\My Projects\TelegramAgent'
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Sozlash yashirin maydonlarda API hash va OpenAI kalitini so'raydi. Yordamchi akkaunt raqami, Telegram login kodi va zarur bo'lsa 2FA parolini kiriting. Asosiy akkauntingizdan yordamchi akkauntiga oldindan bir marta xabar yuboring; egasini topish osonlashadi. Sozlashda ko'rsatilgan egasi aynan siz ekanini tekshiring. Bu paytda agent hech kimga xabar yubormaydi va qo'ng'iroq qilmaydi.

Keyin:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check.ps1 -Online
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

`check.ps1 -Online` Telegram sessiyasini va model nomlarining API orqali mavjudligini tekshiradi; model javob generatsiyasi yoki qo'ng'iroqni sinamaydi. `start.ps1` ochiq tursin. `Ctrl+C` agentni to'xtatadi. Skriptlar PowerShell execution policy ni kompyuter bo'yicha o'zgartirmaydi; `Bypass` faqat ushbu jarayon uchun ishlatiladi.

## Telegramda foydalanish

Yordamchi akkauntiga `/help` yozing. Matn, ovozli xabar yoki oddiy Telegram shaxsiy qo'ng'irog'idan foydalaning. `/call` yuborsangiz, agent sizga qo'ng'iroq qiladi. Javob bergach, AI bilan gaplashasiz; gapini bo'lib savol berish mumkin.

- «Ertaga 09:00 da dars qilishimni qo'ng'iroq qilib eslat.»
- «10 daqiqadan keyin dam olishni eslat.»
- «Har kuni 20:30 da ingliz tilini o'rganishni eslat.»
- «Rejamga hafta oxirida kitob o'qishni qo'sh.»
- «Qaysi rejalarim bor?»
- «3-raqamli eslatmani bekor qil.»

Vaqt zonasi: `Asia/Tashkent`. Agent muvaffaqiyatli saqlangan eslatmaning ID si va aniq vaqtini aytishi kerak. Vaqt noaniq bo'lsa aniqlashtiradi. O'zbekcha ovoz va transkripsiya sifati modelga bog'liq; sana-vaqtni qaytarib aytganida tekshiring.

| Buyruq | Vazifasi |
|---|---|
| `/call` | Sizga qo'ng'iroq qiladi |
| `/hangup` | Qo'ng'iroqni tugatadi |
| `/plans` | Ochiq rejalarni ko'rsatadi |
| `/reminders` | Kutilayotgan eslatmalarni ko'rsatadi |
| `/status` | Agent holati |
| `/help` | Yordam |

Reja qo'shishning o'zi eslatma yaratmaydi. Eslatishni ham ayting. Bir martalik, kunlik va haftalik eslatmalar bor. Murakkab takrorlash (masalan, oyning har uchinchi kuni) hali qo'llanmaydi. Internetdan jonli qidirish qo'shilmagan; joriy yangilik yoki narxni tekshirgan deb hisoblamang.

## Eslatish qanday ishlaydi?

Eslatma SQLite bazasiga yoziladi va har ikki soniyada tekshiriladi. Vaqti kelganda avval Telegram matnli xabar, keyin `call` usuli uchun qo'ng'iroq yuboriladi. Qo'ng'iroq ulangach AI eslatmani o'qib, suhbatni davom ettiradi. Boshqa qo'ng'iroq faol bo'lsa xabar yetkaziladi. Javob bermasangiz yoki qo'ng'iroq ulanmasa, matnli nusxa qoladi. Bir eslatma uchun ketma-ket qayta qo'ng'iroqlar qilinmaydi.

Internet yoki Telegram xabari yetkazilishida xato bo'lsa uch martagacha, ortib boruvchi tanaffus bilan qayta urinadi. Dastur 24 soatdan ortiq kechikib ishga tushsa, eski eslatma faqat xabar bilan yuboriladi. Takroriy eslatmalarning o'tkazib yuborilgan barcha nusxalari yuborilmaydi; keyingi kelajakdagi vaqt hisoblanadi. Jarayon uzilishi bilan yetkazish holatini yozish orasidagi juda qisqa oraliqda xabar takrorlanishi mumkin: tashqi Telegram amali va mahalliy baza uchun yagona atomar tranzaksiya yo'q. `delivered` holati inson eshitganini tasdiqlamaydi; `delivery_status` aloqa usulini qayd etadi.

Standart qo'ng'iroq 15 daqiqa, jiringlash 35 soniya bilan cheklangan. `.env` dagi `MAX_CALL_SECONDS` va `RING_TIMEOUT_SECONDS` orqali o'zgartirish mumkin. Bu cheklovlar xizmatdan foydalanishni nazorat qilishga yordam beradi; ular umumiy pul limiti emas.

## Saqlash va sozlamalar

- `.env` — mahalliy API kalitlari va egasining Telegram ID si. Gitga kiritilmaydi.
- `data/assistant.session` — yordamchi akkaunt Telegram sessiyasi. Bu fayl akkauntga kirish huquqiga ega; ulashmang.
- `data/agent.sqlite3` — rejalar, eslatmalar, oxirgi 200 ta suhbat matni va tool natijalari. Jonli qo'ng'iroq audiosi diskka yozilmaydi; ovozli xabarlar vaqtinchalik fayl bilan qayta ishlanadi va keyin o'chiriladi.
- `logs/agent.log` — xato turi va texnik holat. Kod suhbat matnini yoki API kalitini logga yozmaydi.
- `uv.lock` — tekshirilgan dependency versiyalari.

Matn va ovoz javob olish uchun OpenAI xizmatiga, Telegram xabarlari Telegramga uzatiladi. Mahalliy ma'lumotlar shifrlanmagan; Windows foydalanuvchi akkauntingiz orqali himoyalanadi. Loyiha papkasiga kiradigan odamlardan kalit va sessiyani himoya qiling.

Model nomlari `.env` orqali o'zgaradi: `TEXT_MODEL`, `REALTIME_MODEL`, `TRANSCRIBE_MODEL`, `TTS_MODEL`, `VOICE`. Standart matn modeli `gpt-4.1-mini`, qo'ng'iroq `gpt-realtime-2.1`. Rasmiy manbalar: [Realtime suhbatlar](https://developers.openai.com/api/docs/guides/realtime-conversations), [function calling](https://developers.openai.com/api/docs/guides/function-calling), [text to speech](https://developers.openai.com/api/docs/guides/text-to-speech), [PyTgCalls](https://github.com/pytgcalls/pytgcalls).

## Tekshirish

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\test.ps1
```

Mahalliy testlar tashqi API ga chiqmaydi va pul sarflamaydi. Ular vaqt zonasi, bazaning qayta ochilishi, eslatmalarni olish/qayta urinish/takrorlash, egasi tekshiruvi, tool bajarilishi va ovoz oqimi voqealarini tekshiradi. Native NTgCalls importi va oqim konfiguratsiyasi `check.ps1` bilan tekshiriladi.

Haqiqiy tekshiruv: `/call` → qo'ng'iroqqa javob bering → o'zbekcha savol bering → «2 daqiqadan keyin tekshiruvni eslat» deng → `/reminders` bilan aniq vaqtni ko'ring → qo'ng'iroqni tugating → belgilangan vaqtda xabar va qo'ng'iroq kelishini kuzating. Begona akkauntdan agentga kirish rad etilishini ham tekshiring. Telegram privacy sozlamalarida yordamchi akkaunt sizga qo'ng'iroq qila olishi kerak.

## Avtomatik ishga tushirish

Haqiqiy sinov muvaffaqiyatli o'tgach, xohlasangiz `install-autostart.ps1` ni ishga tushiring. U faqat joriy foydalanuvchining Windows login paytida boshlanadigan `TelegramAgent` vazifasini yaratadi. Administrator huquqi so'ralmaydi. `remove-autostart.ps1` uni olib tashlaydi. Avtomatik ishga tushirish hali yoqilmagan.

24/7 ishlashi uchun keyinchalik doimiy Windows kompyuter yoki serverga ko'chirish kerak. Ushbu tayyor ishga tushirish va jarayon blokirovkasi Windows uchun yozilgan.
