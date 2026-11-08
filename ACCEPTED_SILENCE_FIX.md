# Telefon qabul qilinib agent jim qolishi: VoIP signallari

2026-11-08, Asia/Tashkent.

Foydalanuvchi 9-vazifada telefon qabul qilinganini, lekin agent jim qolganini tasdiqladi. Oldingi audit faqat agentda media boshlanmaganini ko'rsatgan edi; endi bu hodisani foydalanuvchi telefonni ko'tarmagan deb talqin qilmaymiz. Tarixda foydalanuvchining xabari `owner_reported_accepted=true` sifatida saqlandi; bu Telegramdan xayolan olingan signal emas.

## Topilgan aniq kutubxona nuqsoni

O'rnatilgan PyTgCalls3.0.0 adapteri `CALL_MIGRATE_N` paytida Telethon1.45.0 ning boshqa DC uchun exported sender ulanishidan foydalanadi. Telethon uni `updates_queue=None` bilan yaratadi. Shu senderga `PhoneCallAccepted` kelganda receiver `None.put_nowait` xatosi bilan signalni yo'qotishi mumkin. Natijada boshqa tomonda telefon ko'tarilgan bo'lsa ham PyTgCalls qabul tasdig'ini kutib qoladi.

Bu yo'l o'rnatilgan haqiqiy Telethon receiveri va haqiqiy `PhoneCallAccepted/UpdateShort` obyektlari bilan mahalliy sinovda takrorlandi: oldingi yo'l `AttributeError`, tuzatilgan yo'l aynan shu signalni client navbatiga yetkazdi. PyTgCalls ning haqiqiy Telethon adapteri ham sun'iy qabul signalini handshake future ga yetkazishi tekshirildi. Ushbu sinovlar tarmoqqa yoki Telegram akkauntiga ulanmagan.

## Tuzatish

- Faqat shu loyihaning Telethon client instance ida exported sender qaytganda yetishmayotgan update navbati ulanadi. Yangi sessiya/login, kalit almashtirish, qayta terish yoki kutubxona faylini qo'lda o'zgartirish yo'q.
- Mavjud navbat bo'lsa u almashtirilmaydi; hook takroriy o'rnatilmaydi. Client klassi o'zgarmaydi, PyTgCalls uni Telethon sifatida tanishda davom etadi.
- Telefon qabul signali, tasdiqlash RPC si, DC yo'nalishi, native media holati va birinchi kiruvchi/chiquvchi audio alohida kuzatiladi.
- Qabul qilingan, ammo media ochilmagan holat `connection_failed`; uni javob bermagan odam deb ko'rsatmaydi.
- Diagnostikada crypto material, access hash, signaling payload, RTC parol/IP yoki suhbat mazmuni saqlanmaydi.

Bu moslik tuzatishi Telethon ning ichki `_borrow_exported_sender/_updates_queue` API siga tegadi. Uv lock dagi o'rnatilgan versiyalarda tekshirildi; kutubxonalarni yangilaganda shu regressiya testlari qayta bajarilishi kerak.

## Dalil chegarasi

To'liq to'plam **314 test o'tdi**, 7 yangi VoIP regressiyasi. Bitta kutubxona DeprecationWarning bor, test xatosi yoki RuntimeWarning yo'q. Asosiy clientda `GetState` yo'qligi, call-ID xatosi yoki dastur lock deadlocki isbotlanmadi; ularni taxminiy asosiy sabab qilib ko'rsatmadik.

9-vazifa vaqtida DC/accepted signali qayd etilmagan. Shu sabab aynan o'sha hodisani `CALL_MIGRATE` nuqsoni keltirib chiqarganini hozircha qat'iy aytib bo'lmaydi. Tuzatish o'rnatildi; egasining o'z akkauntiga bitta boshqariladigan jonli sinov uchun tayyorligi so'raldi. Boshqa kontaktga yangi qo'ng'iroq yuborilmadi. Jonli eshitish natijasi hali olinmagan.

Telegramning qabul qilish va media ulanishi bosqichlari: [Telegram calls](https://core.telegram.org/api/calls). Adapter va kutish zanjiri: [PyTgCalls connect_call](https://github.com/pytgcalls/pytgcalls/blob/master/pytgcalls/methods/internal/connect_call.py), [Telethon adapter](https://github.com/pytgcalls/pytgcalls/blob/master/pytgcalls/mtproto/telethon_client.py). Telethon clientning allaqachon faol update loopi bo'lishi mumkinligi [rasmiy client hujjatida](https://docs.telethon.dev/en/stable/modules/client.html) tekshirildi.
