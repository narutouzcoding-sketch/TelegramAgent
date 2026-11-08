# Ulanmagan qo'ng'iroqni ovoz tanish xatosi deb ko'rsatishni tuzatish

2026-11-08, Asia/Tashkent.

9-vazifa 14:44 da yaratilgan. Texnik natija `TimedOutAnswer`, savol audiosi yuborilishi 0, kiruvchi audio 0, ASR urinishlari 0, `question_delivered=0`. Shu vazifa uchun `recordings` jadvalida yozuv yo'q. Demak eski “tinglash paytida ovoz olinmadi / mavjud yozuvni tekshiring” xabari noto'g'ri va chalkashtiruvchi bo'lgan.

Bu ma'lumot boshqa tomonda telefon jiringlaganini yoki uning egasi qasddan javob bermaganini isbotlamaydi. PyTgCalls xatosi qabul qilish/ulanish tasdig'i jarayonida chiqariladi. Odam javob bergan bo'lsa ham media handshake muammosini shu kodning o'zidan inkor qilib bo'lmaydi. [Tekshirilgan rasmiy manba](https://github.com/pytgcalls/pytgcalls/blob/master/pytgcalls/methods/internal/connect_call.py).

Tuzatishlar:

- Ulanish tasdiqlanmagan, band, rad etilgan va Telegram maxfiyligi to'sgan holatlar alohida natija. Oddiy ulanish natijasiga “AI texnik xatosi” yorlig'i qo'yilmaydi.
- Qo'ng'iroq ulanmaganda savol aytilmaganini va suhbat yozuvi yaratilmaganini ochiq ko'rsatadi. ASR yoki xayoliy audio bilan izohlamaydi.
- Diagnostikada tayyorlash/terish/ulanish/tinglash bosqichi, `connected` va `recording_started` saqlanadi.
- Saytda faqat tayyorlangan savol matni aytilgan suhbat deb ko'rsatilmaydi.
- Eski `TimedOutAnswer` natijasida ovoz, foydalanuvchi nutqi yoki yozuv bo'lmasa, tarixdagi noto'g'ri izoh tuzatiladi. Mavjud haqiqiy yozuvlar saqlanadi.
- Oldingi standart kutish 35 s → 60 s. O'zgacha qo'lda tanlangan sozlama avtomatik almashtirilmaydi. Kutish uzayishi odamning javob berishini yoki tarmoq ishlashini kafolatlamaydi.
- Avtomatik qayta terish qo'shilmadi; yangi kontaktga qo'ng'iroq yoki xabar yuborilmadi.

Yakuniy to'plam **307 test o'tdi**,9 yangi ulanish regressiyasi; Node va Ruff tekshiruvlari o'tdi. PyTgCalls importida bitta dependency DeprecationWarning bor; RuntimeWarning yoki test xatosi yo'q. Bu yangi inson bilan qo'ng'iroq muvaffaqiyatli o'tgani degani emas.

Odam telefonni ko'tarmasa yoki Telegram ulanishni tasdiqlamasa, dastur suhbatni majburan boshlay olmaydi. Boshqa tomonda qo'ng'iroq haqiqatan qabul qilingan-qilinmaganini foydalanuvchidan so'radik; javob kelmaguncha aniq tashqi sababni taxmin sifatida ham tasdiqlamaymiz.

Ishchi xizmat zaxiradan so‘ng yangilandi: running, xato bo‘sh, kutish 60 s; 9-vazifa unanswered. Yangi kontakt vazifasi yuborilmadi.
