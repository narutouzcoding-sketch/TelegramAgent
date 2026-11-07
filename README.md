# TelegramAgent

Telegram ichida yozishadigan, ovozli xabarga javob beradigan, shaxsiy qo'ng'iroqlarni qabul qiladigan, sizga eslatish uchun qo'ng'iroq qiladigan va aniq topshirig'ingiz bo'yicha boshqa Telegram foydalanuvchisiga xabaringizni ovoz bilan yetkazadigan AI yordamchi.

## Hozirgi holat

Kod, Python 3.12 virtual muhiti, kutubxonalar, `uv.lock`, sozlash skriptlari va mahalliy testlar tayyor. Dastlab faqat egasi bilan yozishish, rejalar va matnli eslatmalar ishlaydi. Qo'ng'iroqlar standart holatda o'chirilgan. Haqiqiy Gemini generatsiyasi va reja tool chaqiruvi sinovdan o'tdi; OpenAI ovoz sinovi billing/kvota xatosi bilan tugadi. Jonli Telegram qo'ng'iroqlari hali tasdiqlanmagan.

### Bepul ovozli rejim

`VOICE_PROVIDER=free` va `TEXT_PROVIDER=gemini` tanlanganda OpenAI API ishlatilmaydi. Ovoz shu kompyuterda [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `small` modeli, CPU/int8 orqali taniladi. Javob matni mavjud Gemini kaliti orqali olinadi. [edge-tts](https://github.com/rany2/edge-tts) o'zbekcha `uz-UZ-MadinaNeural` yoki `uz-UZ-SardorNeural` bilan ovoz yaratadi; javob matni Edge onlayn xizmatiga yuboriladi. Bu to'liq oflayn tizim emas. Edge TTS kafolatlangan rasmiy pulli API o'rnini bosmaydi va xizmat o'zgarishi mumkin. Gemini bepul kvotasi tugasa, pulli provayderga avtomatik o'tilmaydi.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\free-voice.ps1 -EnableCalls
```

Buyruq birinchi marta modelni `data/models/` ga yuklaydi (taxminan 0.5 GB), vaqtinchalik bazada ovoz -> matn -> Gemini -> ovoz -> PCM48 ni sinaydi. Haqiqiy Telegram sessiyasi va bazasi ochilmaydi. Barcha bosqichlar o'tgach, egasi uchun qo'ng'iroqlar yoqiladi; kontakt qo'ng'iroqlari o'chiq qoladi. Agent ishlayotgan oynada `Ctrl+C`, keyin `start.ps1` ni qayta bajaring. Telegramda `/status` ovoz xizmati `free` ekanini ko'rsatishi kerak; keyin `/call` yuboring.

Bepul jonli rejim **navbat bilan** ishlaydi: gapiring, taxminan 1 soniya to'xtang va agent javobini kuting. Agent o'ylayotgan yoki gapirayotgan paytda kiruvchi ovoz tashlab yuboriladi; gapini bo'lib boshqarish bu rejimda yo'q. Bitta gap bo'lagi 15 soniyagacha, ovozli xabar 90 soniyagacha. Talaffuz va tanish sifati o'zgaradi, ayniqsa ism, raqam va aniq vaqtlarni qayta tekshiring. Gemini/Edge uchun internet, model uchun protsessor va xotira kerak. Ushbu kompyuterda mahalliy pipeline ishladi; haqiqiy ikki tomonlama Telegram ovozi foydalanuvchi bilan hali tekshiriladi.

### Cheklovdan keyin boshlash

Akkaunt ochilgach, eski sessiya avtorizatsiyadan chiqqan bo'lsa `login.ps1` ni bir marta bajaring, keyin `start.ps1` ni ishga tushiring. Login kodi va 2FA parolini faqat mahalliy terminalga kiriting. Asosiy akkauntingizdan `/status`, so'ng `Salom` yuboring. Dastur avtomatik boshqa odamlarga yozmaydi. Boshqaruvchi ID siga mos kelmagan xabarlar AI ga yuborilmaydi.

Quyidagi mahalliy ehtiyot choralari `.env` ga qo'shiladi:

```dotenv
ENABLE_VOICE_CALLS=false
ENABLE_CONTACT_CALLS=false
ALLOWED_CALL_USER_IDS=
MIN_MESSAGE_INTERVAL_SECONDS=2
CALL_COOLDOWN_SECONDS=60
MAX_CALLS_PER_HOUR=3
```

Matnli javob bo'laklari orasida kamida 2 soniya kutish bor. Qo'ng'iroq keyinchalik yoqilsa, urinishlar orasida kamida 60 soniya, soatiga ko'pi bilan 3 urinish bor; bu holat qayta ishga tushirganda ham bazada saqlanadi. Bular Telegram tasdiqlagan xavfsiz sonlar emas, mahalliy ehtiyot chegaralaridir. Bloklanmaslikka kafolat yo'q. Telegram norasmiy API mijozlarini kuzatishini bildiradi; faqat xabar yoki qo'ng'iroqni kutayotgan odamlarga murojaat qiling. Manbalar: [Telegram API](https://core.telegram.org/api/obtaining_api_id), [Spam FAQ](https://telegram.org/faq_spam).

`FLOOD_WAIT` kelsa kutish muddati saqlanadi va agent to'xtaydi; uni erta qayta ochish yuborishni davom ettirmaydi. `PEER_FLOOD`, freeze yoki akkaunt bloklanishi xatolari ham faol ishni to'xtatadi. Avtomatik qayta terish va RPC ni cheklovdan keyin qayta yuborish o'chirilgan. Manba: [Telegram RPC errors](https://core.telegram.org/api/errors).

Bepul ovoz sinovi o'tgach yoki OpenAI billing/kvotasi ishlagach, avval faqat o'zingiz bilan ovozni sinash uchun `ENABLE_VOICE_CALLS=true` qo'yiladi. Boshqalarga qo'ng'iroq keyinchalik `ENABLE_CONTACT_CALLS=true` va `ALLOWED_CALL_USER_IDS` ichida ularning Telegram raqamli ID si ko'rsatilgandagina ishlaydi. Kontakt oldindan rozilik bildirgan bo'lishi kerak; aniq topshirig'ingizsiz agent o'zi qo'ng'iroq qilmaydi. Oddiy SIM raqamiga mobil qo'ng'iroq bu loyihada mavjud emas.

### Telegramsiz mahalliy sinov

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\sandbox.ps1
# Qisqa avtomatik AI, reja, terminal eslatmasi va qo'ng'iroq oldindan ko'rish sinovi:
powershell -NoProfile -ExecutionPolicy Bypass -File .\sandbox.ps1 -SelfTest
```

Bu rejim Telegram sessiyasini ochmaydi va haqiqiy bazaga tegmaydi. Vaqtinchalik sinov ma'lumotlari chiqishda o'chiriladi. `/demo` 3 soniyadan so'ng terminalda eslatadi. AI so'rovi tanlangan xizmat kvotasini ishlatadi. `/say MATN` yoki `-SelfTest -Speech` tanlangan ovoz xizmatini ishlatadi (OpenAI rejimida pulli); ovoz sinovi standart holatda bajarilmaydi. Mahalliy sinov jonli Telegram ovozini isbotlamaydi.

## Nima kerak?

1. **Yordamchi uchun alohida oddiy Telegram akkaunti.** O'zingizning asosiy akkauntingizdan shu akkauntga qo'ng'iroq qilasiz. Agent shu alohida akkauntga kiradi. BotFather tokeni kerak emas. Telegram `phone.requestCall` usulini faqat foydalanuvchi akkauntlariga beradi: [rasmiy Telegram API](https://core.telegram.org/method/phone.requestCall).
2. [my.telegram.org/apps](https://my.telegram.org/apps) sahifasidan `api_id` va `api_hash`.
3. Matn va reja uchun [Gemini API key](https://aistudio.google.com/apikey) yoki [OpenAI API key](https://platform.openai.com/api-keys). `VOICE_PROVIDER=free` rejimida Gemini kaliti va mahalliy model yetarli. `VOICE_PROVIDER=openai` rejimida jonli qo'ng'iroq va ovoz uchun OpenAI API kaliti ham kerak. Tegishli model ruxsati va billing/kvota ishlashi lozim. Chatdagi obunangiz yoki shu suhbat API kaliti vazifasini bajarmaydi.
4. Asosiy Telegram akkauntingizdan yordamchiga bir martalik `/pair` xabarini yuborish imkoniyati. Username yoki ID ni oldindan bilish shart emas. Agent faqat tasdiqlangan raqamli ID bilan ishlaydi.
5. Kompyuter yoqilgan, uyqu holatiga kirmagan va internetga ulangan bo'lishi kerak. FFmpeg bu kompyuterda mavjud. Windows uchun NTgCalls native kutubxonasi o'rnatilgan.

Kalit, login kodi, 2FA paroli va Telegram sessiyasini chatga yubormang. Ularni faqat mahalliy sozlash oynasida kiriting.

## Boshlash

### `.env` ni qo'lda to'ldirish

`D:\My Projects\TelegramAgent\.env` faylida quyidagilarni o'zingiz kiriting:

```dotenv
TELEGRAM_API_ID=my_telegram_org_dagi_son
TELEGRAM_API_HASH=my_telegram_org_dagi_32_belgili_hash
TELEGRAM_PHONE=+mamlakat_kodi_va_yordamchi_raqami
OWNER_TELEGRAM_USERNAME=
OWNER_TELEGRAM_ID=
OPENAI_API_KEY=sizning_openai_api_kalitingiz
OPENAI_BACKUP_API_KEYS=
GEMINI_API_KEY=sizning_gemini_api_kalitingiz
TEXT_PROVIDER=auto
```

Bu yuqoridagi qiymatlar namuna; API va telefon qiymatlarini o'zingiznikiga almashtiring. API ID va API hash aynan bitta `my.telegram.org/apps` ilovasidan olinadi. API hash BotFather tokeni yoki OpenAI API kaliti emas. `TELEGRAM_PHONE` yangi yordamchi akkauntning raqami. Ikki `OWNER_...` maydonini avval bo'sh qoldiring.

**OWNER kim?** Bu yordamchini boshqaradigan sizning asosiy, avvaldan ishlatadigan shaxsiy Telegram akkauntingiz. Yangi `Telegram Agent` akkaunti OWNER emas. `OWNER_TELEGRAM_ID` Telegramdagi foydalanuvchi ID si; `TELEGRAM_API_ID` ilova ID si. Ular boshqa-boshqa qiymatlar. `@asosiy_akkauntingiz` oldingi namunadagi o'rinbosar matn edi, haqiqiy username emas.

```powershell
cd 'D:\My Projects\TelegramAgent'
powershell -NoProfile -ExecutionPolicy Bypass -File .\login.ps1
```

Login API ID/hash ni qayta so'ramaydi. Telegram kodi yoki 2FA paroli kerak bo'lsa mahalliy oynada so'raydi. Ko'rsatilgan asosiy akkaunt sizniki ekanini tekshiring. OpenAI kaliti hali bo'lmasa ham Telegram sessiyasini tayyorlash mumkin; agentni boshlashdan oldin kamida Gemini yoki OpenAI kalitini `.env` ga kiriting. Login kodi SMS o'rniga yangi akkaunt ochiq turgan Telegram ilovasiga kelishi mumkin.

Yangi versiyada qo'shilgan `.env.example` maydonlari mavjud `.env` ga o'z-o'zidan ko'chiriladi: eski qiymatlar ustidan yozilmaydi. Buni alohida bajarish uchun `python -m telegram_agent configure` ishlating. `python -m telegram_agent configure --economy` oldingi standart `gpt-realtime-2.1` modelini arzonroq `gpt-realtime-2.1-mini` ga almashtiradi; boshqa maxsus model tanlovlarini o'zgartirmaydi. API kalitlari terminalga chiqarilmaydi.

Yordamchi akkauntga kirilgach, dastur bir martalik `/pair ...` buyrug'ini ko'rsatadi. Uni **asosiy shaxsiy akkauntingizdan yangi yordamchi akkauntiga** xabar qilib yuboring. Terminal ko'rsatgan asosiy akkaunt sizniki bo'lsa `HA` deb tasdiqlang. ID va mavjud bo'lsa username avtomatik saqlanadi. Ulash kodi 5 daqiqa amal qiladi; uni chat yoki boshqa odamlarga ulashmang.

Avval asosiy akkauntingizning haqiqiy username/ID si kiritilgan bo'lsa dastur undan foydalanadi. Username eski numeric ID dan ustun turadi. Noto'g'ri ID, namunadagi username yoki `Could not find the input entity` holatida sozlash bir martalik `/pair` usuliga o'tadi. Username va ID ni bo'shatish kerakli akkauntni boshidan ulashga imkon beradi. Bu yordamchi Telegram sessiyasini o'chirmaydi: kirish muvaffaqiyatli bo'lgan bo'lsa, kod va 2FA parolini qayta kiritish odatda kerak bo'lmaydi.

`ApiIdInvalidError` / `API_ID_INVALID` chiqsa, Telegram API ID yoki API hash ni qabul qilmagan. Ularni bir xil ilova sahifasidan qayta nusxalang. Telefon raqami ham to'liq xalqaro formatda bo'lishi kerak, masalan O'zbekiston uchun `+998` va keyin 9 raqam. Dastur noto'g'ri shakldagi hash yoki mamlakat kodisiz raqamni tarmoqqa chiqishdan oldin aniqlaydi. Shakli to'g'ri bo'lishi juftlik Telegram tomonidan qabul qilinishini kafolatlamaydi.

### Savol-javob orqali sozlash

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

### Telegramda `Deleted Account` yoki qor parchasi belgisi ko'rinsa

Login muvaffaqiyatli bo'lishi akkaunt yozisha olishini tasdiqlamaydi. Telegram **frozen** akkauntlarga sessiya orqali o'qishga ruxsat berishi mumkin; `User.deleted=false` va `User.restricted=false` ham freeze yo'qligini kafolatlamaydi. Dastur endi `help.getAppConfig` dagi `freeze_since_date` ni login, online tekshiruv va ishga tushishdan oldin tekshiradi. Muzlatilgan akkauntda ish boshlamaydi va server ko'rsatgan o'chirish muddatini mahalliy vaqt bilan ko'rsatadi.

Agent ishlayotgan bo'lsa avval `Ctrl+C` bilan to'xtating. Faqat Telegram holatini, AI xizmatlariga chiqmasdan tekshirish:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\telegram-status.ps1
```

Freeze bo'lsa, yordamchi akkauntga rasmiy Telegram ilovasida kirib, **Appeal / Apellyatsiya** orqali cheklovni ko'rib chiqishni so'rang. Akkauntni faqat Telegram muzlatishdan chiqaradi. Kod, API kaliti, AI modeli yoki qayta-qayta login qilish bu cheklovni olib tashlamaydi. Dastur sessiya va kalitlarni o'chirmaydi, apellyatsiyani avtomatik yubormaydi va cheklovni aylanib o'tishga urinmaydi. Apellyatsiya matnini shaxsan ko'rib chiqib yuboring. Manbalar: [Telegram frozen accounts](https://core.telegram.org/api/auth#frozen-accounts) va [Telegram Support](https://telegram.org/support).

## Telegramda foydalanish

Yordamchi akkauntiga `/help` yozing. Avval matnli suhbatni sinang. Ovozli rejim alohida yoqilgach, `/call` agentning sizga qo'ng'iroq qilishini boshlaydi. Javob bergach, AI bilan gaplashasiz. Bepul rejimda javob tugashini kuting; gapini bo'lib savol berish faqat Realtime rejimida mavjud.

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
| `/contacts` | Agentga ulashilgan kontaktlar |
| `/callto @username \| aytiladigan gap` | Bir kishiga xabarni qo'ng'iroq bilan yetkazish |
| `/calls` | Topshirilgan qo'ng'iroqlar va natijalar |
| `/cancelcall ID` | Navbatdagi yoki hozir bajarilayotgan kontakt qo'ng'irog'ini to'xtatish |
| `/status` | Agent holati |
| `/help` | Yordam |

Reja qo'shishning o'zi eslatma yaratmaydi. Eslatishni ham ayting. Bir martalik, kunlik va haftalik eslatmalar bor. Murakkab takrorlash (masalan, oyning har uchinchi kuni) hali qo'llanmaydi. Internetdan jonli qidirish qo'shilmagan; joriy yangilik yoki narxni tekshirgan deb hisoblamang.

## Boshqa kishiga qo'ng'iroq qilish

Masalan: «@username ga qo'ng'iroq qilib, bugun soat 18:00 da uchrashishimizni ayt». Yoki aniq buyruq:

```text
/callto @username | Bugun soat 18:00 da uchrashamiz.
/callto +998901234567 | Uchrashuv ertaga qoldirildi.
```

Tabiiy matn yoki ovozli suhbatda ham shunday topshiriq berish mumkin. Agent faqat sizning aniq ko'rsatmangiz asosida bitta kishiga berilgan xabarni yetkazish topshirig'ini yaratadi. Siz bilan qo'ng'iroq faol bo'lsa, u tugashini kutadi. Navbatga qo'yish hali xabar yetkazilganini anglatmaydi; `/calls` dan natijani ko'ring. `/hangup` faol qo'ng'iroqni yoki hozir tayyorlanayotgan kontakt topshirig'ini to'xtatadi. `/cancelcall ID` bilan alohida topshiriqni bekor qilish mumkin.

Qo'ng'iroq **Telegram orqali** bo'ladi: oddiy mobil/GSM tarmog'iga qo'ng'iroq integratsiyasi yo'q. Telefon raqami Telegram akkauntiga tegishli bo'lishi, qabul qiluvchining privacy sozlamalari topish va qo'ng'iroqni ruxsat qilishi kerak. Aks holda `@username` dan foydalaning yoki kerakli sozlamani qabul qiluvchi bilan tekshiring.

Asosiy akkauntingizning kontaktlari yordamchiga avtomatik ko'chmaydi. Kerakli kontaktni Telegramda **kontakt sifatida ulashing**; agent ism va raqamni mahalliy bazada saqlaydi. Keyin ism bilan topshiriq berishingiz mumkin. Yordamchi akkauntning o'z Telegram kontaktlari ham ism orqali qidiriladi. Bir ism bir nechta kishiga tegishli bo'lsa, dastur taxmin qilmaydi: aniq username yoki raqam so'raydi. Kontakt yuborishning o'zi qo'ng'iroq qilish buyrug'i emas.

Qabul qiluvchi javob bergach, tayyor xabar o'qiladi: agent o'zini egasining **AI yordamchisi** deb tanishtiradi. Qabul qiluvchining ovozi yozilmaydi, OpenAI ga uzatilmaydi va u agentning reja yoki eslatmalarini boshqara olmaydi. Bu usulda qabul qiluvchi bilan erkin AI suhbat qo'llanmaydi; siz bergan xabar ovoz bilan yetkaziladi.

Xabar 1500 belgigacha, tayyor ovoz 3 daqiqagacha. Bir vaqtda 10 tagacha navbatdagi topshiriq saqlanadi. Javob berilmasa yoki qo'ng'iroq uzilsa qayta-qayta terilmaydi. Dastur o'rtada to'xtab qolgan topshiriq qayta ishga tushganda avtomatik takrorlanmaydi; 10 daqiqadan eski navbatlar qayta ishga tushishda bekor qilinadi. `sent` holati qo'ng'iroqqa javob berilib audio uzatilganini bildiradi; inson eshitgani yoki tushunganini alohida tasdiqlamaydi.

## Eslatish qanday ishlaydi?

Eslatma SQLite bazasiga yoziladi va har ikki soniyada tekshiriladi. Vaqti kelganda avval Telegram matnli xabar, keyin `call` usuli uchun qo'ng'iroq yuboriladi. Qo'ng'iroq ulangach AI eslatmani o'qib, suhbatni davom ettiradi. Boshqa qo'ng'iroq faol bo'lsa xabar yetkaziladi. Javob bermasangiz yoki qo'ng'iroq ulanmasa, matnli nusxa qoladi. Bir eslatma uchun ketma-ket qayta qo'ng'iroqlar qilinmaydi.

Internet yoki Telegram xabari yetkazilishida xato bo'lsa uch martagacha, ortib boruvchi tanaffus bilan qayta urinadi. Dastur 24 soatdan ortiq kechikib ishga tushsa, eski eslatma faqat xabar bilan yuboriladi. Takroriy eslatmalarning o'tkazib yuborilgan barcha nusxalari yuborilmaydi; keyingi kelajakdagi vaqt hisoblanadi. Jarayon uzilishi bilan yetkazish holatini yozish orasidagi juda qisqa oraliqda xabar takrorlanishi mumkin: tashqi Telegram amali va mahalliy baza uchun yagona atomar tranzaksiya yo'q. `delivered` holati inson eshitganini tasdiqlamaydi; `delivery_status` aloqa usulini qayd etadi.

Standart qo'ng'iroq 15 daqiqa, jiringlash 35 soniya bilan cheklangan. `.env` dagi `MAX_CALL_SECONDS` va `RING_TIMEOUT_SECONDS` orqali o'zgartirish mumkin. Bu cheklovlar xizmatdan foydalanishni nazorat qilishga yordam beradi; ular umumiy pul limiti emas.

## Saqlash va sozlamalar

- `.env` — mahalliy API kalitlari va egasining Telegram ID si. Gitga kiritilmaydi.
- `data/assistant.session` — yordamchi akkaunt Telegram sessiyasi. Bu fayl akkauntga kirish huquqiga ega; ulashmang.
- `data/agent.sqlite3` — rejalar, eslatmalar, oxirgi 200 ta suhbat matni va tool natijalari. Kiruvchi jonli qo'ng'iroq audiosi diskka saqlanmaydi; bepul TTS javobi va ovozli xabarlar vaqtinchalik fayllar bilan qayta ishlanib o'chiriladi.
- `logs/agent.log` — xato turi va texnik holat. Kod suhbat matnini yoki API kalitini logga yozmaydi.
- `uv.lock` — tekshirilgan dependency versiyalari.

Matn tanlangan Gemini/OpenAI xizmatiga, Telegram xabarlari Telegramga uzatiladi. Bepul rejimda ovoz mahalliy taniladi va javob matni Edge ovoz xizmatiga yuboriladi; OpenAI rejimida ovoz OpenAI ga yuboriladi. Mahalliy ma'lumotlar shifrlanmagan; Windows foydalanuvchi akkauntingiz orqali himoyalanadi. Loyiha papkasiga kiradigan odamlardan kalit va sessiyani himoya qiling.

Model nomlari `.env` orqali o'zgaradi: `TEXT_MODEL`, `GEMINI_MODEL`, `REALTIME_MODEL`, `TRANSCRIBE_MODEL`, `TTS_MODEL`, `VOICE`. OpenAI matn modeli `gpt-4.1-mini`, Gemini matn modeli `gemini-3.1-flash-lite`, qo'ng'iroq `gpt-realtime-2.1-mini`. Rasmiy manbalar: [Realtime suhbatlar](https://developers.openai.com/api/docs/guides/realtime-conversations), [function calling](https://developers.openai.com/api/docs/guides/function-calling), [text to speech](https://developers.openai.com/api/docs/guides/text-to-speech), [PyTgCalls](https://github.com/pytgcalls/pytgcalls).

## Gemini va tejamkor sozlamalar

`GEMINI_API_KEY` ni Google AI Studio dan olib faqat mahalliy `.env` ga yozing. `TEXT_PROVIDER=auto` bo'lsa, Gemini kaliti mavjudligida matnli suhbat, reja/eslatma yaratish va kontaktga qo'ng'iroq topshiriqlarini tushunish Gemini orqali ishlaydi. Aks holda OpenAI matn modeli ishlaydi. `TEXT_PROVIDER=gemini` yoki `openai` bilan provayderni qat'iy tanlash mumkin. Bir xizmatdagi kvota tugaganda boshqa xizmatga yashirin o'tish yo'q. `/status` tanlangan matn provayderini ko'rsatadi.

Standart Gemini modeli **`gemini-3.1-flash-lite`**, fikrlash darajasi **`minimal`**. 2026-11-07 kungi tekshiruvda u function calling ni qo'llaydi va 3.5 Flash-Lite dan arzonroq. Eski 2.5 Flash-Lite ga kirish yangi foydalanuvchilar uchun cheklangani sabab yangi ulanishda u tanlanmadi. Google model mavjudligi va kvotalarini akkauntingiz uchun `check.ps1 -Online` bilan tekshiring. Bu tekshiruv model ro'yxatini tekshiradi; haqiqiy javob sifatini yoki billing ishlashini isbotlamaydi. Manbalar: [Gemini modellari](https://ai.google.dev/gemini-api/docs/models), [narxlar](https://ai.google.dev/gemini-api/docs/pricing), [OpenAI-compatible API](https://ai.google.dev/gemini-api/docs/openai).

| Sozlama | Standart | Ta'siri |
|---|---|---|
| `GEMINI_REASONING_EFFORT` | `minimal` | Oddiy topshiriqlarda ichki fikrlashni kamaytiradi |
| `TEXT_MAX_OUTPUT_TOKENS` | `1200` | Bir matn javobining maksimal generatsiya hajmi |
| `HISTORY_MESSAGES` | `10` | Modelga yuboriladigan oxirgi matnlar soni |
| `HISTORY_MAX_CHARS` | `10000` | Shu eski matnlarning umumiy belgilar chegarasi |
| `VOICE_MAX_OUTPUT_TOKENS` | `768` | Bir jonli ovozli javob chegarasi |
| `VOICE_CONTEXT_TOKENS` | `6000` | Jonli suhbat kontekstining chegarasi |

Ushbu chegaralar umumiy pul limiti yoki barcha so'rovlar uchun yagona token budjeti emas: tizim ko'rsatmalari, tool sxemalari, joriy xabar va ko'p bosqichli tool javoblari ham input hisoblanadi. Past narx bilan yaxshi natijani muvozanatlash uchun javoblar odatda qisqa; batafsil javobni alohida so'rashingiz mumkin. Murakkab savollarda `GEMINI_REASONING_EFFORT=low` yoki `medium`, uzun javoblar uchun kattaroq `TEXT_MAX_OUTPUT_TOKENS` tanlash mumkin. Natija sifati va real token sarfi haqiqiy so'rovlaringiz bilan baholanadi; eng yaxshi sifat yoki eng kam token kafolatlanmaydi.

Eski suhbat konteksti qisqarsa ham rejalar va eslatmalar SQLite bazasidan o'chirilmaydi. Gemini tool chaqiruvining thought signature ma'lumotlari shu so'rov davomida saqlanadi. Token chegarasida uzilgan Gemini tool javobi bajarilmaydi; foydalanuvchiga tekshirish kerakligi bildiriladi. Oddiy `/plans`, `/reminders`, `/calls`, `/status` buyruqlari modelga so'rov yubormaydi.

`VOICE_PROVIDER=free` rejimida ovoz Whisper bilan mahalliy taniladi, suhbat va tools Gemini orqali, TTS esa Edge orqali bajariladi. OpenAI kaliti talab qilinmaydi. `VOICE_PROVIDER=openai` rejimida jonli suhbat OpenAI Realtime, transkripsiya/TTS OpenAI orqali ishlaydi. Gemini Flash-Lite ushbu loyihada to'g'ridan-to'g'ri jonli audio modeli emas. Google bepul va pulli rejalarining ma'lumotlardan foydalanish shartlari farqlanishi mumkin; tafsilotlar Google narxlar sahifasida.

## AI kalitlari va zaxira ulanish

Asosiy kalit `OPENAI_API_KEY` da. Qo'shimcha, ishlatishga ruxsatingiz bo'lgan ko'pi bilan 3 ta zaxira kalitni `OPENAI_BACKUP_API_KEYS` maydoniga vergul bilan ajratib yozish mumkin. Maydon bo'sh bo'lsa bitta kalit bilan ishlaydi. Kalitlar log yoki holat xabarlariga chiqarilmaydi.

Vaqtinchalik tarmoq/timeout yoki `5xx` server xatosida keyingi sozlangan kalit bilan so'rov qayta bajariladi. Server `Retry-After` talab qilsa u hurmat qilinadi; juda uzun kutish talabida bu urinish to'xtaydi. Muvaffaqiyatli ishlagan kalit keyingi so'rovlarga ham tanlanadi. Bu matn, ovoz transkripsiyasi, TTS va Realtime ulanishining dastlabki WebSocket bosqichiga tegishli. Faol Realtime suhbat o'rtasida socket uzilsa sessiya boshqa akkauntda avtomatik davom ettirilmaydi; `/call` bilan yangi qo'ng'iroq kerak bo'ladi.

`429` tezlik cheklovi, kredit/kvota tugashi, billing/spend/usage limiti yoki `401/403` avtorizatsiya/ruxsat xatosida boshqa profilga avtomatik o'tilmaydi. Dastur sababini bildiradi. Kalit almashtirishning o'zi kredit qo'shmaydi: OpenAI limitlari tashkilot va loyiha darajasida bo'lishi mumkin. Kredit tugasa billingni to'ldirish, limit xatosida tegishli limit/ruxsatni tekshirish kerak. Bir so'rovdagi token/context chegarasi ham boshqa kalit qo'yish bilan kattalashmaydi. Manbalar: OpenAI Docs [rate limits](https://developers.openai.com/api/docs/guides/rate-limits) va [error codes](https://developers.openai.com/api/docs/guides/error-codes).

## Tekshirish

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\test.ps1
```

Mahalliy testlar tashqi API ga chiqmaydi va pul sarflamaydi. Ular vaqt zonasi, bazaning qayta ochilishi, eslatmalarni olish/qayta urinish/takrorlash, egasi tekshiruvi, tool bajarilishi va ovoz oqimi voqealarini tekshiradi. Native NTgCalls importi va oqim konfiguratsiyasi `check.ps1` bilan tekshiriladi.

Haqiqiy tekshiruv: `/call` → qo'ng'iroqqa javob bering → o'zbekcha savol bering → «2 daqiqadan keyin tekshiruvni eslat» deng → `/reminders` bilan aniq vaqtni ko'ring → qo'ng'iroqni tugating → belgilangan vaqtda xabar va qo'ng'iroq kelishini kuzating. Begona akkauntdan agentga kirish rad etilishini ham tekshiring. Telegram privacy sozlamalarida yordamchi akkaunt sizga qo'ng'iroq qila olishi kerak.

## Avtomatik ishga tushirish

Haqiqiy sinov muvaffaqiyatli o'tgach, xohlasangiz `install-autostart.ps1` ni ishga tushiring. U faqat joriy foydalanuvchining Windows login paytida boshlanadigan `TelegramAgent` vazifasini yaratadi. Administrator huquqi so'ralmaydi. `remove-autostart.ps1` uni olib tashlaydi. Avtomatik ishga tushirish hali yoqilmagan.

24/7 ishlashi uchun keyinchalik doimiy Windows kompyuter yoki serverga ko'chirish kerak. Ushbu tayyor ishga tushirish va jarayon blokirovkasi Windows uchun yozilgan.
