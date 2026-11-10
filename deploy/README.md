# Kompyuter o'chiq bo'lganda ishlash

Bu papka tayyorlash yo'riqnomasi va systemd xizmatini beradi. Hozir hech qanday cloud server yaratilmagan yoki joylashtirilmagan. SSH manzili, server hisobi yoki bank kartasi loyihada yo'q.

## Mos host

Uyquga ketmaydigan Linux x86_64 yoki ARM64 VM, Python 3.12, FFmpeg, doimiy yoziladigan disk va tashqi HTTPS/Telegram/UDP ulanishi kerak. Lock faylda NTgCalls va CTranslate2 uchun Linux ARM64 paketlari ham bor; native import va jonli audio aynan tanlangan serverda tekshiriladi. Jarayon blokirovkasi Windows va Linux uchun moslangan.

Gemini matn modeli va mahalliy Whisper `small` uchun dastlab 2 vCPU/4 GB RAM tavsiya etiladi; bu qat'iy o'lchangan minimum emas. 1 GB bepul VM da xotira va kechikish alohida tekshiriladi. Qo'shimcha Ollama4B uchun amalda kamida 8 GB RAM va yetarli disk ma'qul. Joriy tejamkor rejim yangi Ollama o'rnatishni talab qilmaydi. Bepul PaaS ning sleep/ephemeral disk cheklovlari doimiy Telegram sessiyasi uchun tekshirilishi kerak. [Sarfni kamaytirish](../QUOTA_ECONOMY.md).

## Joylashtirish ketma-ketligi

1. Windows agentini va autostartni to'xtating. Bitta Telegram `.session` faylini ikki mashinada bir vaqtda ishlatmang.
2. Serverda `telegram-agent` nomli oddiy tizim foydalanuvchisi, `/opt/telegram-agent` papkasi, Python3.12 virtual muhiti va FFmpeg tayyorlang. Repozitoriyni klonlab, `uv sync --frozen --no-dev --python 3.12` bilan bog'liqliklarni o'rnating. Native NTgCalls importi aynan shu serverda tekshirilishi kerak; tayyor ARM paketining mavjudligi jonli audio muvaffaqiyatini o'zi tasdiqlamaydi.
3. `.env` va `data/` ni faqat shaxsiy SSH/SFTP orqali ko'chiring, fayl egasini `telegram-agent` qiling, sessiya/kalitlarni GitHub'ga yubormang. Yoki server terminalida Telegram loginini o'zingiz bajaring. Kalit/parollarni chatga yozmang.
4. Windows dagi `D:\Drive` serverda mavjud bo'lmaydi. Hujjatlar katalogini serverga alohida ruxsat bilan ko'chirish va panelda yangi Linux yo'lini tanlash kerak. Ko'chirilmagan hujjatlarni bor deb ko'rsatmaymiz.
5. `deploy/telegram-agent.service` ni `/etc/systemd/system/telegram-agent.service` ga o'rnating; server administratori `systemctl daemon-reload` va `systemctl enable --now telegram-agent` bajaradi.
6. Panel faqat loopbackda: o'z kompyuteringizda `ssh -L 8765:127.0.0.1:8765 USER@SERVER` tunnel ochib, localhost panelidan foydalaning. Unit parolni, API kalitlarini yoki panelni ommaga chiqarmaydi.
7. `systemctl status telegram-agent`, `journalctl -u telegram-agent`, panel holati, saqlangan eslatma va foydalanuvchi ishtirokidagi bitta jonli qo'ng'iroqni tekshiring. Native audio, server UDP va real nutq sifati faqat hostda tasdiqlanadi.

Xizmatda texnik uzilishdan tiklanish bor. Telegram taqiqi, noto'g'ri kalit yoki qo'lda to'xtatish avtomatik qo'ng'iroq qayta terishiga aylantirilmaydi. `systemctl stop telegram-agent` xizmatni to'xtatadi. Serverning bepul tarifi, kvotasi va uzluksizligi hosting shartlariga bog'liq; bu fayllar bepul24/7 host ajratilganini bildirmaydi.
