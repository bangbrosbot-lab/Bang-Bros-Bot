# Bang Bros Telegram Bot

## Railway sozlamalari
Railway project -> Variables bo‘limiga quyidagilarni kiriting:

- `BOT_TOKEN` — BotFather bergan token
- `ADMIN_ID` — administrator Telegram ID raqami
- `DB_PATH` — `bot.db` (ixtiyoriy)

`Procfile` worker jarayonini `python main.py` orqali ishga tushiradi.

## GitHub
Arxivni ochib, ichidagi fayllarni GitHub repository root qismiga yuklang. `requirements.txt` va `Procfile` rootda bo‘lishi kerak. Railway’da GitHub repository’ni ulang va deploy qiling.

## /data zaxira nusxasi
Admin `/data` yuborsa, bot SQLite online-backup API orqali joriy bazaning nusxasini `.db` fayl qilib jo‘natadi. Bu zaxira nusxani GitHub repository rootiga `bot.db` nomi bilan qo‘shib, qayta deploy qilinganda boshlang‘ich baza sifatida ishlatish mumkin.

**Muhim:** Railway Volume ulanmagan bo‘lsa, SQLite fayli deploy/restart jarayonida doimiy saqlanishiga kafolat yo‘q. GitHub’ga qo‘shilgan `bot.db` faqat deploy paytidagi boshlang‘ich nusxa bo‘ladi; bot ishlayotgan paytdagi yangi o‘zgarishlar avtomatik GitHub’ga yozilmaydi. Doimiy ma’lumotlar uchun Railway Volume yoki tashqi PostgreSQL kerak bo‘ladi.

## Funksiyalar
- Majburiy kanallarga obuna tekshirish va join-request kuzatish
- Video teaser, 360p/480p/720p/1080p sifatlari, VIP nazorati va ko‘rishlar
- Balans, chek orqali hisob to‘ldirish, VIP tariflari, referral
- Admin panel, video qo‘shish/o‘chirish, foydalanuvchi boshqaruvi, reklama tarqatish, Gift
- `/data` va `/id`

Bot tokenini hech qachon GitHub kodiga yoki chatga joylamang. Uni faqat Railway Variables orqali kiriting.
