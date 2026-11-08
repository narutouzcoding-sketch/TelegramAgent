# Asl ovoz, shaxsiy hujjatlar va barqarorlik — yakuniy tekshiruv

2026-11-08, Asia/Tashkent. Bu bosqich mavjud mahalliy TelegramAgent va bitta boshqaruv paneliga qo'shildi; yangi server yoki akkaunt tizimi yaratilmadi.

## Ishlaydigan yangi imkoniyatlar

| Imkoniyat | Qanday ishlatiladi |
|---|---|
| O'z ovozingizni yozish | Qo'ng'iroqlar → Vazifa turi → Mening asl ovozimni yetkazish → mikrofon. Tugatib eshiting va kutubxonaga saqlang |
| Tayyor audio yuklash | Shu joydagi Audio fayl tanlash. WAV/OGG/WebM/MP3/M4A; 12 MB va 3 daqiqagacha |
| Qo'ng'iroqda asl ovozni qo'yish | Saqlangan yozuv, kontakt va vaqtni tanlang. Agent avval AI yordamchi ekanini aytadi, keyin yozuvni eshittiradi |
| Asl javobni olish | Xabardan keyin javobini ham yozib olish belgisini yoqing. Matn tanishsiz, AI xulosasisiz asl javob yoziladi |
| Chatga golos yuborish | Yetkazish turi → Telegram chatga golos. Qo'ng'iroq qilinmaydi |
| Telegram ichidan topshirish | O'zingiz yuborgan golosga reply: `/voicecall @username`, `/voiceask @username`, `/voicesend @username`. Kirish tili uchun `en` yoki `ru` ni username oldiga yozish mumkin |
| Vaqtga belgilash | Saytda Qachon? → Vaqtini belgilash. Audio ID va parametrlar SQLite da saqlanadi; takroriy topshiriq bostiriladi |
| Shaxsiy hujjatlar | Hujjatlar bo'limida tanlangan mahalliy papkani ulash/yangilash/uzish va manba parchasini qidirish |
| Mahalliy qaydlar | Hujjatlar bo'limida sarlavha va matnni o'zingiz qo'shing; keyin qidiring |
| Zaxira | Hujjatlar → Zaxira tayyorlash → yuklab olish. SQLite va unga tegishli saqlangan audio; `.env` va Telegram sessiya fayllari kiritilmaydi |
| Yetkazilmagan natijalar | Kontakt bilan ish tugab, egasiga natija yuborilmasa, matnli natija mahalliy navbatga saqlanadi. Faqat egasiga, cheklangan urinishlar bilan yuboriladi; kontaktga qayta terilmaydi |

Asl ovozli yo'l ASR, tarjima va matn AI ni chaqirmaydi. Audio Telegram uchun OGG/Opus ga mahalliy o'giriladi; ovoz AI tomonidan qayta yaratilmaydi. Qo'ng'iroqdagi qisqa kirish va rahmat gapi mavjud bepul Edge TTS orqali aytiladi, shu sabab internet va ovoz xizmati mavjudligi kerak. Boshqa tilda yuborish tanlovi asl yozuvni tarjima qilmaydi; til faqat agentning kirish gapiga tegishli.

## Shaxsiy ma'lumotlar chegarasi

Foydalanuvchi tanlagan papka mahalliy bazaga ulandi. Asl fayllar tahrirlanmaydi yoki o'chirilmaydi. Disk ildizi, UNC/tarmoq manzili, tashqi symlink/junction orqali boshqa manbaga chiqish qabul qilinmaydi. Odatdagi yashirin, parol/kalit/sessiya nomli fayllar o'tkaziladi. Bu filtr maxfiy ma'lumotni fayl mazmunidan avtomatik topib tozalaydi degani emas; tanlangan papkani foydalanuvchi boshqaradi.

TXT, MD, PDF va DOCX qo'llanadi. Fayl 5 MB gacha, PDF 50 sahifagacha; 200 hujjat, jami matn chegarasi mavjud. Ajratish alohida, 15 soniyalik muddat bilan boshqariladigan jarayonda bajariladi. Yomon yoki katta hujjat asosiy agentning ishini to'xtatmasligi uchun o'tkaziladi.

Ishchi papkada **2 ta mos hujjat** indekslandi. Taxminan **55 MB PDF** hajm chegarasi sabab o'tkazildi. Qolgan ko'p fayllar qo'llanadigan hujjat formatiga kirmaydi. Hujjat javoblari hozir **kalit so'z bo'yicha manba parchalari**, to'liq semantik AI tahlili emas. Masalan: `Hujjatlardan jadval top`.

Hujjat so'rovi/javobi bazada private sifatida saqlanadi va odatiy Gemini/OpenAI kontekstiga kirmaydi. Ovozli suhbatda hujjat parchasi tashqi TTS ga yuborilmaydi: faqat tayyor, umumiy bildirish ovozga aylantiriladi. Hujjat natijasi matnda o'qiladi; egasi Telegram orqali so'raganida natija egasining chatiga yuborilishi mumkin. Kontakt suhbatlari egasining hujjatlari, xabarlari yoki toollariga kira olmaydi.

## Sinov dalillari

Yakuniy `qa.ps1`: **204 passed**, failure=0, error=0, skipped=0. Ruff, JavaScript sintaksisi va `uv lock --check` o'tdi. Oldingi 179 ta testga quyidagilar uchun 25 ta regressiya qo'shildi:

- Haqiqiy FFmpeg bilan WAV→OGG, davomiylik, PCM va asl yozuv oxirining saqlanishi; bo'sh/buzuq/katta faylni rad etish.
- Audio ID, arxivlangan/mavjud bo'lmagan yozuv, belgilangan vaqt va takroriy topshiriq.
- Golos yuborish aynan tanlangan fayldan foydalanishi; TTS/ASR/LLM va telefon transporti chaqirilmasligi.
- Private hujjatning cloud kontekst va TTS ga chiqmasligi, tanlangan papka tashqarisidagi faylni qayta tekshirish.
- TXT/DOCX va sintetik PDF matni, parollangan PDF, mahalliy qayd va ulanishni uzish.
- Snapshot va audio mosligi, bir vaqtda yangi audio paydo bo'lishi, yo'q audio bo'lsa noto'liq backup ni rad etish. Zaxira ichidagi uchinchi tomonga yuborish navbati tiklanganda avtomatik bajarilmaydigan holatga o'tkaziladi; ishchi navbatga tegilmaydi.
- Natija navbatining owner ID ga bog'lanishi, takroriy xabarni bostirish, urinish chegarasi va Telegram chekloviga rioya.
- Node komponent sinovi: **5 ta mikrofon holati** — yozish paytida fayl tanlash, kech kelgan onstop, ruxsat kutilayotganda chiqish, ikki marta bosish va boshqa rejimga o'tish. Haqiqiy mikrofon ochilmadi.

Brauzerning alohida QA panelida sun'iy WAV tanlash, blob audio oldindan yuklanishi (2 soniya, media xatosi yo'q), OGG kutubxonaga saqlanishi, aynan shu audio bilan soxta yetkazish vazifasi, shaxsiy qayd/hujjat qidiruvi va haqiqiy backup ZIP havolasi tekshirildi. Bu panelda hech bir real kontaktga qo'ng'iroq yoki xabar yuborilmadi.

Mustaqil tester topgan va tuzatilgan muammolar: private hujjatning TTS ga ketishi, javob olinmaydigan relay da yozuv e'lonining yo'qligi, backup va upload orasidagi poyga, mikrofon onstop ning tanlangan faylni almashtirishi va yashirin rejimda mikrofon davom etishi.

## Jonli tekshiruv va keyingi ishlar

Ishchi agent yangi versiyada ishga tushirildi; lokal API orqali holati tekshiriladi. Boshqaruvchi ID, kalitlar, sessiya va mavjud kontaktlar saqlanadi. Barcha 225 ta boshqa kontakt uchun avval berilgan mahalliy ruxsat saqlanadi; qo'ng'iroq/xabar faqat egasining topshirig'idan yaratiladi. Qabul qiluvchining Telegram maxfiylik sozlamalari amal qiladi.

Quyidagilar ushbu test bilan isbotlanmagan:

- Haqiqiy qurilma mikrofonining sifati va Telegram orqali inson bilan ikki tomonlama native qo'ng'iroq. Qurilma ruxsati va qisqa jonli sinov kerak; sun'iy PCM testini inson suhbati deb ko'rsatmaymiz.
- Katta/skanerlangan PDF uchun OCR, Excel/rasm/eskirgan Word formatlari va barcha fayllarning to'liq matnli tahlili.
- Kalendar/email ulanishi, 24/7 server, kunlik AI xarajatining doimiy byudjeti va avtomatik ertalabki sharh. Ular uchun alohida manba/vaqt/joylashtirish tanlovi kerak; hozir ulangan deb ko'rsatilmaydi.

Barqarorlikning keyingi ustuvor tekshiruvi: egasining qisqa real ovozini saqlab eshitish → egasi aniq tanlagan kontaktga yetkazish sinovi → native qo'ng'iroq va asl javob yozuvi. 24–72 soatlik uyqu/internet uzilishlari bilan uzoq muddatli sinov alohida bajariladi.

## Foydalanilgan texnik manbalar

[MDN — getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia): mikrofon ruxsati va localhost/HTTPS talabi. [MDN — MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder): qo'llanadigan formatni aniqlash va yozuv hodisalari. [pypdf — matn ajratish](https://pypdf.readthedocs.io/en/latest/user/extract-text.html): matnli PDF bilan skanerlangan rasm PDF farqi va resurs chegaralari.
