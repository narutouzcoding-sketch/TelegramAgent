TelegramAgent Android ilovasi Android 10 va undan yangi telefonlarda ishlaydi. Ilova agentning boshqaruv paneliga ulanadi. Telegram sessiyasi, AI kalitlari va vazifalarni bajaradigan jarayon kompyuterda yoki serverda saqlanadi.

Hozirgi Wi-Fi sinovi uchun tayyor APK `data/downloads/TelegramAgent.apk` faylida. Kompyuter va telefon bir Wi-Fi tarmog'ida bo'lsin. Telefonda panelning mahalliy IP manzilini ochib, Android ilovasini yuklab olish havolasini bosing. Android o'rnatish tasdig'ini telefon egasi bajaradi.

Birinchi ochilishda APK qurish vaqtida berilgan manzilga ulanadi. Ilova yuqorisidagi “Manzil” tugmasi orqali boshqa manzilni saqlash mumkin. Keyingi ochilishda shu manzil avtomatik yuklanadi. Panelga kirishda “Shu qurilmada 30 kun eslab qolish” belgilansa, kirish sessiyasi qayta ishlatiladi. Parol yangilanishi yoki hisobdan chiqish bu sessiyani bekor qiladi.

Mahalliy HTTP faqat xususiy IP va localhost uchun qabul qilinadi. Internet serveri uchun HTTPS ishlatiladi. Telefon mikrofonidan brauzer orqali yozish HTTPS manzilida ishlaydi. Mahalliy Wi-Fi sinovida tayyor audio faylni tanlab yuklash mumkin. WebView fayl tanlagichini va serverdan fayl yuklab olishni qo'llaydi.

Qayta qurish uchun JDK 17+, Android SDK 35 va Gradle 8.9 kerak. Ushbu kompyuterdagi vositalar foydalanuvchining `AppData/Local/TelegramAgent-build` papkasiga o'rnatilgan.

```powershell
.\android\build.ps1 -DefaultServerUrl 'http://KOMPYUTER_IP:8765/'
```

APK reliz imzosi `data/android-release.p12` va uning sozlamasi `data/android-signing.json` fayllarida saqlanadi. Yangi APK bilan mavjud ilovani yangilash uchun shu imzo kaliti kerak. Bu fayllarni shaxsiy shifrlangan zaxirada saqlang.

Serverga ko'chirganda panelning loopback porti oldida `deploy/Caddyfile.example` asosida HTTPS o'rnatiladi. APK'dagi “Manzil” maydoniga yangi HTTPS manzil kiritiladi.

0.3.1 relizida paneldagi tungi rejim native yuqori panel va tizim ranglariga ham qo‘llanadi. Eski ilovani o‘chirmasdan yangi APK’ni uning ustiga o‘rnating: manzil va kirish ma’lumotlari saqlanadi.
