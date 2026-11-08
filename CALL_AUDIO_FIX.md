# Qo'ng'iroqda savol berish va javobni eshitish auditi

2026-11-08, Asia/Tashkent.

## Haqiqiy topilma

13:35 dagi 8-vazifa: “Tanladingmi” matni `relay` rejimida yuborilgan. Bu rejim faqat xabar audiosini uzatadi va javobni tinglamaydi. Uning `sent` natijasi savolga javob olinganini anglatmaydi. Ushbu vazifadan keyin yangi kontakt qo'ng'irog'i sinov uchun boshlanmadi.

Yana saqlangan 9.72 soniyalik past ovozli suhbatda eski 150 RMS chegarasi birorta nutq parchasini ajratmagan. Yangi detektor shu yozuvni qayta o'qishda 2.99 va 4.01 soniyalik ikkita parchani ajratdi. Bu faqat nutq chegarasi diagnostikasi: u gap mazmuni to'g'ri tanilgani yoki savolga javob borligini isbotlamaydi.

## Tuzatilgan sabablar

| Oldingi holat | Yangi xatti-harakat |
|---|---|
| Savol bir tomonlama `relay` ga tushib qolgan | Tanish to'g'ridan-to'g'ri savollar `ask` ga o'tadi; saytda yuborishdan oldin rejim va tushuntirish o'zgaradi. Backend ham deduplikatsiyadan oldin bir xil qarorni qo'llaydi. “Javob kutma / faqat ayt” ni saqlaydi. Oddiy xabar, URL va tekshirilgan darak gaplar relay bo'lib qoladi. |
| Savol ovozi odam telefonni ko'targach tayyorlangan | Kirish ovozi qo'ng'iroqdan oldin tayyorlanadi va PCM ga dekodlanadi. TTS tayyor bo'lmasa telefon terilmaydi. |
| Past ovoz butunlay yo'qolgan, fon shovqini gap deb ko'rilgan | Past amplitudaga sezgir va fon shovqinining quyi energiyasini o'rganadigan detektor, 200 ms oldingi audio va suhbat orasidagi 1 soniyalik pauza. Asl signal kuchaytirilmaydi yoki o'zgartirilmaydi. |
| Jimlik paketlari kelmasa oxirgi gap kutilgancha qolgan | Haqiqiy soat bo'yicha pauza nutqni matnga o'tkazishga yuboradi. Qarshi tomon qo'yganda navbatdagi yakuniy nutq ham cheklangan muddatda qayta ishlanadi. |
| Bitta paket ichidagi keyingi gap o'chirilgan | Tayyor nutqdan keyin buferning qolgan qismi saqlanadi. |
| Oxirgi audio paket hali yuborilayotganida savol tugagan deb olingan | Sender natijasini va qisqa media drain ni kutadi. Bu odam eshitganining kafolati emas. |
| Kvota/tarmoq sabab model yuklash telefon ichida boshlanishi mumkin bo'lgan | Mahalliy zaxira faqat cache dan qo'ng'iroq oldidan tayyorlanadi. Jonli ASR: Gemini 8 s, tayyor mahalliy zaxira 6 s; telefon ichida model yuklab olinmaydi. |
| Takroriy savol/javob ovozi 45–75 s jim kutishga olib kelishi mumkin bo'lgan | Jonli TTS tayyorlash 8 s bilan cheklangan, qarshi tomon qo'ysa darhol bekor qilinadi. Olingan haqiqiy javob shu texnik xatoda yo'qotilmaydi. |
| Jim suhbatda faqat umumiy qo'ng'iroq chegarasi ishlagan | Savoldan keyin 10 s jimlikda bir marta qaytaradi, yana javob bo'lmasa “javob olinmadi” bilan tugaydi; avtomatik qayta terilmaydi. |
| Nima sababdan javob olinmagani bilinmagan | Kiruvchi audio, ajratilgan nutq, ASR xatosi/vaqti va navbat tashlanishi mahalliy hisobotda saqlanadi. Natijada ovoz kelmagani bilan matn tanishdagi xato ajratiladi. |
| Savol rejimi moduli ilk kirishda yuklanmagan | Brauzer sinovida topilib tuzatildi; login sahifasidagi barcha scriptlar kirishdan oldin yuklanishini tekshiradigan regressiya qo'shildi. |

## Dalil va sinov chegarasi

Yakuniy to'plam **272 test**, shu jumladan ushbu bosqichning 35 yangi regressiyasi. Mustaqil tester transport, shovqin, deklarativ xabar va TTS uzilishi yo'llarini qayta ko'rdi. Brauzerda alohida, haqiqiy kontaktlarsiz sinov paneli: `relay` + “Tanladingmi” → “Savol berib, javobni aniqlasin”; qo'ng'iroq yuborilmadi.

Real Edge TTS → PCM48 paketlar → real Gemini ASR → javob verifieri zanjiri sun'iy sinovdan o'tdi:

- Sun'iy savol: “Nonushtaga nima olib boray?”
- Sun'iy suhbatdosh ovozi: “Non olib keling.”
- Tanilgan va dalilga kiritilgan matn: “Non olib keling.”
- ASR: 1843 ms; bitta nutq, 0 ASR xatosi, navbatdan tashlangan audio bo'lagi yo'q.
- Natija `completed`, lekin bu haqiqiy kontakt javobi emas. Telegram qo'ng'irog'i yoki xabari yuborilmadi.

Hozirgi bepul rejim navbatli: agentning o'z ovozi ijro bo'layotgan paytdagi ustma-ust nutq ASR ga kiritilmaydi; mustaqil asl yozuv esa uni saqlaydi. To'liq barge-in/echo cancellation bu tuzatishda qo'shilmadi. Shovqinli mikrofon, yomon aloqa, tanish xatosi, Telegram maxfiyligi va bepul xizmat kvotalari bo'yicha mutlaq xatosizlik kafolati berilmaydi. Yangi kod bilan inson qatnashgan native Telegram suhbatining eshitilishi hali qayta tasdiqlanmagan.

Ishchi agent band emasligi tekshirilib, mahalliy zaxira olindi va `panel.ps1` orqali qayta ishga tushirildi. Yakuniy API holati `running`, xato bo'sh, ovoz yoqilgan, kutilayotgan qo'ng'iroq yo'q. Eski vazifalar saqlandi, yangi kontaktga vazifa yuborilmadi. Alohida QA serveri tekshiruvdan so'ng yopildi.

## Rasmiy manbalardan tekshirilgan mezonlar

Gap tugashini kutish bilan umuman gapirmayotgan odam uchun jimlik taymeri alohida masala; kechikish va uzilishlar ham boshqarilishi kerak. [Twilio ConversationRelay best practices](https://www.twilio.com/docs/voice/conversationrelay/best-practices), [uzilish xabarlari](https://www.twilio.com/docs/voice/conversationrelay/websocket-messages).

Audio formati va namunalar chastotasi to'g'ri ko'rsatilishi, clipping va keraksiz signalni qayta ishlashdan saqlanish kerak. ASR ga beriladigan asl amplituda saqlandi. [Google Cloud Speech-to-Text best practices](https://docs.cloud.google.com/speech-to-text/docs/best-practices?hl=en).

PyTgCalls rasmiy misoli PCM16L, belgilangan kanal/chastota va 10 ms paketlarni qo'llaydi; bizdagi mono48k format shu tartibga mos. [Rasmiy frame sending misoli](https://github.com/pytgcalls/pytgcalls/blob/master/example/frame_sending/example_frame_sending.py).
