# TelegramAgent — foydalanuvchi va barqarorlik auditi

2026-11-08, Asia/Tashkent. Windows, Python 3.12, mahalliy panel.

## Oxirgi qo‘shimchalar

Javob olinmagan suhbatni muvaffaqiyat deb ko‘rsatish tuzatildi: **237 ta test o‘tdi**. Dalil, qisman javob va tasdiqlanmagan ovoz holatlari [ANSWER_FIX.md](ANSWER_FIX.md) da. Asl ovoz, hujjatlar va zaxira bosqichining 204 testli hisoboti [FEATURES.md](FEATURES.md) da. Quyidagi 20 ssenariy matritsasi va 179 testli audit oldingi bosqichning qaydi.

## Natija va sinov chegarasi

20 ta alohida foydalanuvchi ssenariysi avtomatlashtirildi. Birinchi ishga tushirishda **15 o'tdi, 5 yiqildi**; tegishli tuzatishlardan keyin **20/20 o'tdi**. Mustaqil tester kodni o'qib, vaqtinchalik bazalar va sun'iy AI javoblari bilan qo'shimcha nosozliklarni takrorladi. Jami regressiya to'plami: **179 test o'tdi**. Ruff, JavaScript va PowerShell sintaksisi tekshirildi.

Brauzer sinovi alohida `127.0.0.1:8766` panelida bajarildi. U vaqtinchalik baza, soxta AI javobi va sun'iy OGG signalidan foydalanadi. Unda haqiqiy Telegram sessiyasi, foydalanuvchi kontaktlari va API kalitlari ochilmaydi. Bu sinov yangi haqiqiy telefon suhbatini yoki Telegram ovoz transportini isbotlamaydi. Ishchi panel `127.0.0.1:8765` alohida tekshiriladi.

## 20 turdagi tekshiruv

Quyidagi ssenariylar `tests/test_acceptance.py` ichida `test_uat_01`–`test_uat_20` nomlari bilan qayta bajariladi. API ssenariylari haqiqiy aiohttp server va SQLite bilan, tashqi tarmoq xizmatlarisiz ishlaydi.

| # | Foydalanuvchi holati | Tekshirilgan natija | Yakun |
|---|---|---|---|
| 01 | Noto'g'ri parol, kirish va chiqish | Xato parol rad etiladi, logout sessiyani yopadi | O'tdi; brauzerda ham |
| 02 | Kirishsiz maxfiy faylga murojaat | Holat, audio, `.env`, sessiya ochilmaydi | O'tdi |
| 03 | Begona sayt yoki CSRFsiz reja yozish | Yozish rad etiladi, baza o'zgarmaydi | O'tdi |
| 04 | API ga obyekt o'rniga list/null/son yuborish | 500 o'rniga tushunarli 400 | Tuzatildi |
| 05 | O'zbekcha/emoji/HTML matnli reja | Yaratish, tahrirlash, bajarish; HTML bajarilmaydi | O'tdi; brauzerda ham |
| 06 | Bo'sh, noto'g'ri yoki o'tgan sana | Eslatma yaratilmaydi, server yiqilmaydi | Tuzatildi |
| 07 | Toshkent vaqti va takroriy eslatma | Vaqt to'g'ri o'giriladi, keyingi kun saqlanadi | O'tdi |
| 08 | Yetkazilayotgan eslatmani bekor qilish | Keyingi xato/finish uni qayta tiriltirmaydi | O'tdi |
| 09 | Bo'sh va takroriy kontakt | Bo'sh rad etiladi, bir xil reference yangilanadi | O'tdi |
| 10 | Telegram o'chiq paytda kontakt ruxsatini olish | Ruxsat mahalliy bekor bo'ladi, qo'ng'iroq yo'q | O'tdi |
| 11 | Noto'g'ri til, tur yoki davomiylik | Telefon topshirig'i yaratilmaydi | O'tdi |
| 12 | Bir topshiriqni ikki marta yuborish | Bitta navbat yozuvi, bir xil ID | O'tdi |
| 13 | Qo'ng'iroq vaqtida dastur qayta boshlanishi | Oldingi kontaktga avtomatik qayta terilmaydi | O'tdi |
| 14 | Yozilayotgan/yuborilayotgan audioni qayta yuborish | Server band holatni rad etadi | Tuzatildi |
| 15 | Uzilgan yozuvni tiklash va audio autentifikatsiyasi | Tiklash holati saqlanadi, kirishsiz audio berilmaydi | O'tdi |
| 16 | Ovozli AI kvotasi tugashi | Pulli API chaqirilmaydi, yozib olishga o'tiladi | O'tdi |
| 17 | ASR band paytida kelgan asl ovoz | ASR filtri asl PCM yozuvini yo'qotmaydi | O'tdi |
| 18 | Model JSON obyekt o'rniga `[]`/`null` qaytarishi | Suhbat xavfsiz yakunlanadi, AttributeError yo'q | Tuzatildi |
| 19 | Telegram transporti uzilishi | Panel `reconnecting` ko'rsatadi, tayyor deb aytmaydi | Tuzatildi |
| 20 | Birinchi suhbat so'rovida AI xatosi | Keyingi xabar qabul qilinadi, navbat band qolmaydi | O'tdi |

## Topilgan va tuzatilgan kamchiliklar

P1 — muhim ishlash uzilishi. P2 — funksiya, natija yoki holat noto'g'riligi.

| Muammo | Daraja | Takrorlash / dalil | Tuzatish |
|---|---|---|---|
| Chatga qo'ng'iroq natijasini yuborishdagi offline xato butun agentni to'xtatishi | P1 | `send_text` OSError beradi; xato `run_queue` dan chiqadi | Natija oldin mahalliy tarixga yoziladi; vaqtinchalik xabar xatosi ajratildi; Telegram cheklovi hanuz agentni to'xtatadi |
| Faol audio yozuvini retry qilish | P2 | `retry_recording` capturing/sending holatini o'zgartirardi | capturing/captured/sending serverda ham rad etiladi |
| AI `[]`/`null` javobida suhbat uzilishi | P2 | `value.get` AttributeError | JSON obyekt ekanligi tekshiriladi, xavfsiz yakuniy gap ishlatiladi |
| Transport uzilsa panel yashil qolishi | P2 | Faqat oldingi ready Event tekshirilgan | Jonli `is_connected()` va worker holati ajratildi; qayta ulanish ko'rinadi |
| Noto'g'ri JSON API ni 500 ga olib kelishi | P2 | list/null/son bilan plan/chat/contact/login | Obyekt tekshiruvi; 400 |
| Bo'sh sana API ni 500 ga olib kelishi | P2 | due_at=null/list/son | Sana tipi va bo'shligi tekshiriladi |
| Yozish o'chirilgan bo'lsa ham record vazifasi muvaffaqiyat va'da qilishi | P2 | RECORD_CALLS=false + record | Terishdan oldin rad etiladi; boshqa kirish matnlari yozuv bor deb aytmaydi |
| Kvotadan keyingi fallback xulosasi "AI ishlatilmadi" deyishi | P2 | AI/ASR dan keyin record_only=true | Ataylab tokensiz rejim va fallback ajratildi, qisman tanilgan javob saqlanadi |
| Bo'lim almashtirganda chat va qo'ng'iroq qoralamasi yo'qolishi | P2 | Matn yozib Kontaktlar ga o'tish, qaytish | Joriy sahifa xotirasida saqlanadi; logout tozalaydi. Brauzerni reload qilishdan keyin saqlanish va'da qilinmaydi |
| Terminal sandbox yangi suhbat parametrlarini qabul qilmasligi | P2 | mode/language/duration_seconds bilan queue | Parametrlar qo'llanadi; sinov topshirig'i hanuz simulated, haqiqiy navbatga tushmaydi |

Qo'shimcha regressiyalar `tests/test_qa_regressions.py`: muvaffaqiyatli terishdan keyingi xabar xatosi qayta terishga olib kelmasligi, Telegram cheklovini yashirmaslik, yozuv o'chirilgan paytdagi ovoz xabari, kiruvchi boshqa akkaunt/band holat diagnostikasi.

## Brauzer kuzatuvlari

Noto'g'ri va to'g'ri parol, Unicode va HTML matnli reja yaratish, suhbat yuborish, kontakt qidirish, bo'limlararo chat/qo'ng'iroq qoralamasi tekshirildi. Soxta AI javobi ekranda aniq SINOV deb ko'rsatilgan. 0 AI token/English tanlovlari va qo'ng'iroq topshirig'i faqat vaqtinchalik serverga yuborildi. Audio tekshiruvida 2 soniyalik sun'iy OGG ishlatiladi; u suhbatdosh ovozi sifatida ko'rsatilmaydi.

## Hali jonli tasdiq talab qiladigan holatlar

- Egasi → agent haqiqiy Telegram qo'ng'irog'i, ikki tomonlama ovoz, shovqinli o'zbekcha nutq va suhbatdan keyin asl golosning kelishi. Oldingi urinishda yangi call/ASR/recording yozuvi yo'q edi; shu sabab muvaffaqiyat deb hisoblanmaydi. Yangi oxirgi qo'ng'iroq diagnostikasi uni ajratishga yordam beradi.
- Telegram/Google real xizmatlari uzilishi, noutbuk uyqusi va 24–72 soatlik uzluksiz ishlash. Qisqa avtomatik test buning o'rnini bosmaydi.
- Boshqa telefondagi HTTPS/PWA/mikrofon, iOS/Android brauzerlari. Hozir loopback panel shu kompyuter uchun.
- Bepul Gemini limiti, Edge TTS mavjudligi va mahalliy model javobining sifati kafolatlanmaydi. Yozuv rejimi AI tokensiz; internet va Telegram ulanishi baribir kerak.

## Keyingi eng foydali funksiyalar — ustuvor takliflar

1. **Vazifani bajarishdan oldin tushunganini ko'rsatish:** kimga, qaysi tilda, aynan nima, qachon. Ayniqsa noaniq ism yoki ovoz matnida tekshirish oynasi kerak. Bu noto'g'ri kontakt/xabar ehtimolini kamaytiradi.
2. **Bitta tizim holati sahifasi:** Telegram, AI, TTS, disk joyi, yozuv yuborish va oxirgi muvaffaqiyatli tekshiruv. Oxirgi qo'ng'iroq va qayta ulanish indikatori ushbu tuzatishda qo'shildi; qolganlari alohida ish.
3. **Mahalliy zaxira va tiklash:** rejalar, kontaktlar, eslatmalar va yozuvlar uchun SQLite backup va foydalanuvchi boshqaradigan saqlash muddati. Sessiya/API kalitlarini oddiy eksportga qo'shmaslik kerak.
4. **AI sarf byudjeti:** kunlik taxminiy sarf, ovoz davomiyligi va rejim bo'yicha limit; byudjetda avtomatik asl ovoz rejimi. Hozirgi hisoblagichlar jarayon qayta boshlansa nol bo'ladi.
5. **Yetkazilmagan natijalar qutisi:** offline paytda saqlangan matnli natijalarni keyin egasiga yuborish. Hozir ular panel tarixida qoladi, avtomatik matn qayta yuborish qo'shilmagan.
6. **Ovozli boshqaruvni saytdan yozib yuborish:** push-to-talk, yuborishdan oldin matnni tekshirish. Bu Telegram native qo'ng'irog'iga qo'shimcha aloqa yo'li bo'ladi; mikrofon ruxsati va masofadan ishlash uchun HTTPS kerak.
7. **Eslatma tarixi va kechikish sababi:** bajarildi/kechikdi/yuborilmadi holatlari, 5/10 daqiqaga surish, kalendar ko'rinishi. Hozir UI asosan kutilayotgan eslatmalarni ko'rsatadi.
8. **24/7 serverga tayyorlash:** restart, sog'liq tekshiruvi, disk/backup, bitta Telegram session egasi. Bepul hosting doimiy ishlash kafolati degani emas; kompyuter o'chiq paytda hozirgi mahalliy agent ishlamaydi.

Bu takliflar implementatsiya qilingan deb ko'rsatilmaydi. Eng to'g'ri keyingi tartib: haqiqiy qo'ng'iroqni isbotlash → tushunilgan vazifani tekshirish → sog'liq/backup → 24/7 joylashtirish.

## Qayta ishga tushiriladigan tester

```powershell
cd "D:\My Projects\TelegramAgent"
powershell -NoProfile -ExecutionPolicy Bypass -File .\qa.ps1
# Faqat 20 ssenariy:
powershell -NoProfile -ExecutionPolicy Bypass -File .\qa.ps1 -AcceptanceOnly
# Alohida, tashqi tarmoqqa ulanmaydigan UI sinov paneli:
powershell -NoProfile -ExecutionPolicy Bypass -File .\qa.ps1 -Browser
```

XML natija: `data/qa-results.xml`. Sinov paneli: `http://127.0.0.1:8766`, faqat QA paroli `Qa-Sinov-2026!`. Bu ishchi panel paroli emas. Sinov panelini Ctrl+C yoki uning menyusidagi yopish orqali to'xtating.

390×844 o‘lchamda 7 navigatsiya tugmasi ko‘rindi, gorizontal toshish yo‘q. Audio boshqaruvida birinchi avtomatlashtirish urinishi timeout bo‘ldi; qayta ko‘rilgan native Play tugmasi bilan sun’iy signal ijro etildi, davomiylik va oxirgi pozitsiya 2.0065 s, media xatosi yo‘q. Bu dasturdagi audio muvaffaqiyatsizligi deb hisoblanmadi. Qo‘ng‘iroq tarixida faqat QA; terilmadi va Sinov holati tasdiqlandi.
