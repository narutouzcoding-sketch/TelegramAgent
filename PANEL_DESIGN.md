# Panel va Android — 2026-11-10

Foydalanuvchi bergan HTML maketlardagi Inter shrifti, ranglar, o‘lchamlar va sahifa tuzilmalari panelga moslashtirildi. Statistika haqiqiy bazadan olinadi. Namunadagi uydirma aniqlik, tezlik, uptime, shifrlash va OAuth/QR kirish da’volari funksional deb ko‘rsatilmaydi.

Kontaktlar: ism/username/raqam, bezatilgan Unicode ismlar va o‘zbekcha kelishik qo‘shimchalari bo‘yicha qidirish; 9 tadan sahifalash; ruxsat va so‘nggi faollik filtrlari. Android WebView uchun native `datalist` o‘rniga alohida qidiruv ro‘yxati ishlatiladi. Tanlangan kontakt identifikatori yuboriladi; akkaunt o‘zgargan bo‘lsa boshqa odamga vazifa navbatlanmaydi. Bir nechta mos ism topilsa tizim taxmin qilmaydi.

Rejalar: ochiq/yakunlangan/bugun qo‘shilgan filtrlari, haqiqiy bajarilish foizi, tezkor yaratish. Eslatmalar: faol/bugun/qo‘ng‘iroq/takroriy/tarix filtrlari va tezkor yaratish. Qo‘ng‘iroqlar: kontakt kartasidan oldindan to‘ldirish, ixcham qo‘shimcha sozlamalar, vazifa tarixidan qidirish va holat filtri.

Yozuvlar: qidiruv, yetkazish holati filtrlari, audio, saqlangan xulosa va transkript. Transkript bo‘lmasa, bu ochiq aytiladi. Hujjatlar: kartalar, nom/manba filtri, mahalliy matnni ko‘rish, manbadan qidirish, qayd, tanlangan papka va zaxira. Alohida fayl yuklash, OCR va semantik vektor qidiruvi hozir qo‘shilmagan; mavjud ishlaydigan mahalliy hujjat imkoniyatlari ko‘rsatiladi.

Tungi rejim yuqoridagi oy/quyosh tugmasidan o‘zgaradi va shu qurilmada saqlanadi. APK 0.3.1 panel mavzusini yuqoridagi native panel va tizim ranglariga ham qo‘llaydi. Eski APK veb panel yangiliklarini qayta yuklaganda oladi; native o‘zgarishlar uchun yangi APK mavjud ilovaning ustiga o‘rnatiladi. Imzo kaliti o‘zgarmagan.

Panel CSS/JS/shriftlarni mahalliy fayllardan beradi. `design.css` tayyor holda repoda saqlanadi. Maket sinflari o‘zgartirilganda loyiha ildizidan qayta yig‘ing:

```powershell
npx --yes tailwindcss@3.4.17 -c tailwind.config.cjs -i telegram_agent/panel_web/design.input.css -o telegram_agent/panel_web/design.css --minify
```

Tekshiruv: 366 pytest testi o‘tdi. Alohida vaqtinchalik QA panelda 8 sahifa × 4 ekran eni (320/390/768/1440) × 2 mavzu tekshirildi. Qidiruv, kontakt tanlash, simulyatsion matn vazifasi, reja/eslatma yaratish, hujjat ko‘rish/qidirish, audio, suhbat va TXT eksporti ishladi. JavaScript yoki HTTP xatosi va gorizontal overflow aniqlanmadi. Haqiqiy panelda 233 kontakt, bir ma’noli qidiruv, kontaktni kompozitorga o‘tkazish, mavzu/sessiya saqlanishi va LAN ulanishi faqat o‘qish orqali tekshirildi. Begona odamlarga sinov xabari yoki qo‘ng‘iroq yuborilmadi. Android reliz yig‘ildi va APK v2 imzosi tekshirildi; qurilmadagi yakuniy sinov telefon egasida bajariladi.
