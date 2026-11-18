# Bang Bros Telegram Bot

## Railway sozlamalari
Railway project → Variables bo‘limiga kiriting:

| O‘zgaruvchi | Majburiy | Izoh |
|---|---|---|
| `BOT_TOKEN` | ha | BotFather bergan token |
| `ADMIN_ID` | ha | Bosh administrator Telegram ID si; barcha huquqlar avtomatik beriladi |
| `DB_PATH` | yo‘q | Standart `bot.db`. **Volume ulansa: `/data/bot.db`** |
| `CHANNEL_URL` | yo‘q | Asosiy kanal havolasi (standart: eski havola) |
| `MIN_TOPUP` / `MAX_TOPUP` | yo‘q | Hisob to‘ldirish chegaralari (3 000 / 50 000 000) |
| `MAX_PENDING_TOPUPS` | yo‘q | Bitta foydalanuvchining kutilayotgan cheklari soni (3) |
| `BACKUP_INTERVAL_HOURS` | yo‘q | Bazaning avtomatik zaxirasi, soat (24). `0` = o‘chirilgan |
| `LOG_LEVEL` | yo‘q | `INFO` / `DEBUG` |

`Procfile` worker jarayonini `python main.py` orqali ishga tushiradi. Python 3.10+ kerak.

## GitHub va Railway
Arxivni ochib, `Bang_Bros_Bot` ichidagi fayllarni (papkalarni ham) GitHub repository rootiga yuklang.
`requirements.txt`, `Procfile`, `main.py` rootda bo‘lishi kerak. Tokenni hech qachon kodga yozmang.

## Ma’lumotlar xavfsizligi
* `/data` (faqat bosh admin) — bazaning izchil nusxasini yuboradi.
* **Avtomatik zaxira:** bot har `BACKUP_INTERVAL_HOURS` soatda bazani bosh adminga yuboradi.
* **Muhim:** Railway Volume ulanmagan bo‘lsa SQLite fayli qayta deploy qilinganda o‘chib ketishi mumkin.
  Volume yarating (mount path `/data`) va `DB_PATH=/data/bot.db` qo‘ying.
* Vaqt bazada UTC da saqlanadi, foydalanuvchiga Toshkent vaqti (UTC+5) ko‘rsatiladi.

## Asosiy funksiyalar
- Majburiy kanallarga obuna tekshirish va join-request kuzatish
- Maxsus kanalga video postlari, like/dislike, video deep-link
- Teaser, sifatlar, VIP nazorati, foydalanuvchi bo‘yicha yagona ko‘rish hisoblagichi
- Balans, chek yuborish, admin tasdiqlashi/rad etishi, VIP tariflari
- Referral (alohida referral balans, faqat VIP uchun)
- Admin panel, foydalanuvchi boshqaruvi, admin huquqlari, reklama va Gift
- `/data` va ruxsatli adminlar uchun `/id`

## Kontentni himoyalash
Bot yuboradigan media xabarlarda `protect_content=True` ishlatiladi (forward va saqlashni cheklaydi).
Skrinshotni barcha qurilmalarda 100% to‘xtatish kafolatlanmaydi.

## Loyiha tuzilishi
```
main.py            ishga tushirish, xatolik handleri, avtomatik zaxira, VIP eslatma sikli
notifications.py   VIP eslatma: 1 kunlik — 1 soat oldin, 1 haftalik/1 oylik/gift — 1 kun oldin
config.py          sozlamalar (env)
db.py              SQLite qatlami (qulf + atomik tranzaksiyalar)
access.py          bloklanganlik va obuna nazorati (3 soniyalik kesh); middlewares.py — har amalda obunani qayta tekshiradi
utils.py           formatlash, prompt-xabarlar, xavfsiz/ommaviy yuborish
middlewares.py     takroriy bosishdan himoya
timeutil.py        vaqt (UTC/Toshkent)
keyboards.py, states.py, backup.py
handlers/
  user.py          foydalanuvchi bo‘limi
  admin.py         admin paneli
  ads.py           reklama va gift
  filters.py       admin filtri va huquqlar
tests/test_db.py   baza testlari
```

## Testlar
```
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
