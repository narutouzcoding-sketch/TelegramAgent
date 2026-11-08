# Savolga javob olinmaganida noto'g'ri muvaffaqiyat ko'rsatilishini tuzatish

2026-11-08, Asia/Tashkent.

## Aniqlangan sabab

Oldingi dastur ovoz energiyasi yoki transkriptda istalgan bitta suhbatdosh xabari borligini javob olingani deb hisoblagan. Shu sabab salomlashuv, qaytarishni so'rash, shovqin yoki faqat yozuv rejimi ham `completed` bo'lib, sayt “Javob olindi” ko'rsatgan. Bu mezon noto'g'ri edi. Tekshirilgan oxirgi yozuvdan salomlashuv tanildi; savolga tegishli javob aniqlanmadi.

## Yangi xatti-harakat

- Salomlashuv yoki “qaytaring/eshitmadim” bo'lsa, agent savolni qaytaradi; bu javob deb olinmaydi. Urinishlar chegaralangan, yangi qo'ng'iroq avtomatik terilmaydi.
- Savol ikki qismli bo'lsa, bitta qism javobi `partial_answer`; qolgan qismi so'raladi. Tasdiqlangan parcha yo'qotilmaydi, hatto keyin suhbatdosh rad etsa ham.
- Modelning “answered” degan so'zi yetarli emas: aynan suhbatdoshning joriy tanilgan nutqidan so'z chegaralari bilan mos keladigan iqtibos talab qilinadi. To'qilgan, boshqa tildagi yoki nutqda yo'q javob qabul qilinmaydi.
- “No”, “Nothing”, “I don't know”, “A'lo” kabi qisqa, tegishli javoblar rad etilmaydi. Salom yoki aniqlashtirish bilan birga aytilgan haqiqiy javob ham tekshiriladi.
- AI kvotasi tugasa yoki JSON buzilsa, natija tasdiqlanmagan bo'ladi; ovoz yozuvi saqlanadi. Xato muvaffaqiyatga aylantirilmaydi.
- Javob berishni rad etish `declined`; jimlik/noaniq javob `no_answer` yoki `answer_unverified`. Faqat audio yozish `recorded_unverified`; u hech qachon savolga tekshirilgan javob degani emas.
- Javob haqiqatan aniqlangach, yakundagi TTS/tarmoq xatosi olingan javobni yo'qotmaydi. Tasdiqlanmagan salomlashuv esa texnik xato paytida ham “qisman javob” deb ko'rsatilmaydi.
- Sayt, yuboriladigan golos izohi va matnli natija ushbu holatlarni ajratadi. Golos yuborilgani uning ichida savolga javob bor degani emas.
- Eski, dalilsiz `completed` natijalar o'chirilmaydi; “javob tasdiqlanmagan” yoki “faqat audio yozilgan” holatiga o'tkaziladi.

## Tekshiruv

Yangi 33 ta regressiya holati qo'shildi: salom, salomdan keyin uzilish, uch marta salom, qaytarish so'rovi, o'z savolining aks-sadosi, shovqin, bog'liq bo'lmagan gap, rad etish, kvota, buzilgan verdict, to'qilgan iqtibos, qisqa haqiqiy javob, ikki qismli savol, aralash aniqlashtirish+javob, texnik xatodan keyingi natija, eski natijalar va golos izohlari.

Yakuniy to'plam: **237 test**. Tegishli qismlar alohida ham qayta bajarildi. Mustaqil tester asosiy noto'g'ri muvaffaqiyat yo'llarini takrorlab, tuzatishlarni qayta ko'rdi.

Haqiqiy Gemini xizmatiga faqat SUN'IY misollar berilgan alohida tekshiruv:

1. “Assalomu alaykum. Xayrli kech.” → `no_answer`.
2. Ikki qismli savolga sun'iy “Uyda” → `partial_answer`, qolgan qism so'raldi.
3. Sun'iy “Ahvolim yaxshi” → `completed`, ikkala asl iqtibos saqlandi.

Bu joylashuv yoki ahvol haqidagi haqiqiy kontakt javobi emas. Ushbu ta'mirlashda hech bir kontaktga qayta qo'ng'iroq qilinmadi va xabar yuborilmadi. Asl yozuv tekshiruvi va model kontrakti sinovi yangi jonli suhbatni almashtirmaydi. Telefonni ko'targan odam javob bermasa, agent javobni to'qimaydi; tasdiqlanmagan natijani ochiq ko'rsatadi.

## Ishlayotgan agentda qo'llash

Faol qo'ng'iroq va kutilayotgan vazifa yo'qligi tekshirildi, mahalliy zaxira olindi va agent odatiy `panel.ps1` orqali qayta ishga tushirildi. API: `running`, xato bo'sh. Oldingi 7-vazifa `recorded_unverified`, `answer_verified=0`; ikkala asl audio fayli saqlangan. Brauzerda shu vazifa “Faqat ovoz yozildi — javob tekshirilmagan” deb ko'rindi. Yangi forma odatiy tanlovi “Savol berib, javobni aniqlasin”. Sinov davomida yangi qo'ng'iroq topshirilmadi.
