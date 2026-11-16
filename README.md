# Bang Bros Telegram Bot

## Railway sozlamalari
Railway project -> Variables bo‘limiga quyidagilarni kiriting:

- `BOT_TOKEN` — BotFather bergan token
- `ADMIN_ID` — bosh administrator Telegram ID raqami
- `DB_PATH` — `bot.db` (ixtiyoriy)

`Procfile` worker jarayonini `python main.py` orqali ishga tushiradi.

## GitHub va Railway
Arxivni ochib, ichidagi `Bang_Bros_Bot` papkasining ichidagi fayllarni GitHub repository root qismiga yuklang. `requirements.txt`, `Procfile` va `main.py` rootda bo‘lishi kerak. Railway’da GitHub repository’ni ulang va deploy qiling.

Bot tokenini hech qachon GitHub kodiga yoki chatga joylamang. Uni faqat Railway Variables orqali kiriting.

## /data zaxira nusxasi
Bosh admin `/data` yuborsa, bot SQLite online-backup API orqali joriy bazaning nusxasini `.db` fayl qilib jo‘natadi. Bu zaxira nusxani GitHub repository rootiga `bot.db` nomi bilan qo‘shib, qayta deploy qilinganda boshlang‘ich baza sifatida ishlatish mumkin.

**Muhim:** Railway Volume ulanmagan bo‘lsa, SQLite fayli deploy/restart jarayonida doimiy saqlanishiga kafolat yo‘q. GitHub’ga qo‘shilgan `bot.db` faqat deploy paytidagi boshlang‘ich nusxa bo‘ladi; bot ishlayotgan paytdagi yangi o‘zgarishlar avtomatik GitHub’ga yozilmaydi. Doimiy ma’lumotlar uchun Railway Volume yoki tashqi PostgreSQL kerak bo‘ladi.

## Asosiy funksiyalar
- Majburiy kanallarga obuna tekshirish va join-request kuzatish
- Maxsus kanalga video postlari, like/dislike ovozlari soni va video deep-link
- Teaser, sifatlar, VIP nazorati va foydalanuvchi bo‘yicha yagona ko‘rish hisoblagichi
- Balans, chek yuborish, admin tasdiqlashi/rad etishi va VIP tariflari
- Referral qoidalari, shaxsiy havola, alohida VIP uchun ishlatiladigan referral balansi
- Yangi foydalanuvchi va referral orqali kelgan foydalanuvchi haqida admin xabari
- Bot haqida rasm/video+matn, Yordam va admin bilan bog‘lanish
- Admin panel, foydalanuvchi boshqaruvi, admin huquqlari, reklama va Gift
- `/data` va ruxsatli adminlar uchun `/id`

## Referral balansi
Referral mukofoti alohida saqlanadi va faqat VIP obuna xaridida ishlatiladi. Oddiy hisob to‘ldirish balansi bilan birga VIP uchun hisoblanadi.

## Kontentni himoyalash
Bot yuboradigan video, rasm va boshqa media xabarlarda Telegram `protect_content=True` ishlatiladi. Bu Telegram ichida xabarni forward qilish va media saqlashni cheklaydi. Telegram qurilma va ilova versiyasiga qarab skrinshot/ekran yozuvini ham cheklashi mumkin, ammo barcha qurilmalarda skrinshotni 100% to‘xtatish kafolatlanmaydi.
