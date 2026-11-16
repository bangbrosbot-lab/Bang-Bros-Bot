# Bang Bros Bot — kod auditi va yaxshilanishlar hisoboti

Ish tamoyili, tugmalar, matnlar va foydalanuvchi oqimlari **o‘zgarmagan**. Eski `bot.db` yangi kod bilan
to‘liq mos (migratsiya sinab ko‘rilgan: balans, VIP, adminlar, kanallar, videolar, ovozlar, chek so‘rovlari saqlanadi).

## 1. KRITIK xatolar (pul, ma’lumot yoki ishlashga ta’sir qilgan)

| # | Muammo (eski kod) | Oqibat | Tuzatish |
|---|---|---|---|
| 1 | Bitta DB ulanishida bir nechta `BEGIN IMMEDIATE` parallel ishlagan | Bir vaqtda 2+ kishi VIP olsa/chek tasdiqlansa `cannot start a transaction within a transaction` xatosi. **Sinovda 5 tadan 4 tasi yiqildi** | Barcha DB amallari bitta qulf (`asyncio.Lock`) ostida; ko‘p bosqichli amallar `tx()` kontekstida |
| 2 | Gift olish tranzaksiyasiz edi | Limit 2 bo‘lsa 5 kishi yutdi (**sinovda tasdiqlandi**), VIP/pul alohida bosqichda berilgani uchun yo‘qolish xavfi | `claim_gift` atomik: limit, yutuq va VIP/pul bitta tranzaksiyada |
| 3 | `add_user` poygasi | Ikki marta `/start` bosilsa `IntegrityError` (**sinovda tasdiqlandi**) | `INSERT OR IGNORE` + tranzaksiya |
| 4 | `show_user` ichida f-string ichida bir xil qo‘shtirnoq (`f'...{'@'+...}'`) | `runtime.txt` dagi **Python 3.11 da SyntaxError** — bot umuman ishga tushmasligi mumkin edi | Qayta yozildi (3.10+ da ishlaydi) |
| 5 | Chekni rad etishda xabar o‘chirilgan, sabab kutilgan | Admin sababni yozmasa (yoki menyu bossa) to‘lov abadiy «pending» bo‘lib, tugmalari yo‘qolgan | Xabar o‘chirilmaydi; «Bekor qilish» tugmasi; qaror chiqqach chek xabari holat bilan yopiladi (✅/❌) |
| 6 | `/id` sahifasida ism HTML-escape qilinmagan | Ismida `<`/`&` bo‘lgan foydalanuvchi ro‘yxatni buzgan (xato) | `html.escape` |
| 7 | `edit_text(..., protect_content=True)` | Sahifalash tugmalarida noto‘g‘ri parametr | Olib tashlandi |
| 8 | Bosh adminni bloklash mumkin edi | Bosh admin o‘z botidan «bloklangan» bo‘lib qolishi | Bosh admin bloklanmaydi |

## 2. MUHIM kamchiliklar

* **Qayta bosishdagi soxta xato:** like/dislike yoki reklama ovozini takror bosganda «Ovoz qabul qilinmadi» chiqardi (aslida saqlangan). Endi «message is not modified» to‘g‘ri e’tiborga olinmaydi.
* **Mavjud bo‘lmagan videoga ovoz** bazada yetim yozuv yaratardi → tekshiriladi.
* **Video o‘chirilganda** `views`/`votes` yozuvlari qolib ketardi → tozalanadi.
* **Bloklanganlar** gift olishi, ovoz berishi, referral qoidasini qabul qilishi mumkin edi → endi yo‘q (yagona `guard_*` tekshiruvi).
* **Obunadan keyin video yo‘qolishi:** video havolasi orqali kirgan, obuna bo‘lmagan foydalanuvchi «Tekshirish»dan keyin umumiy menyuga tushardi → endi aynan o‘sha videoning teaseri keladi.
* **Join-request «aylanib o‘tish»:** bir marta so‘rov yuborgan foydalanuvchi keyin kanaldan chiqib ketsa ham abadiy obuna hisoblanardi → haqiqiy a’zo ekani aniqlanganda eski iz tozalanadi.
* **Majburiy kanal qo‘shishda** bot admin emasligi tekshirilmasdi (keyin hamma foydalanuvchi qulflanib qolardi) → endi aniq xabar bilan rad etiladi.
* **Reklama/Gift tarqatish** ketma-ket, throttlesiz va flood-limitni hisobga olmay yuborilardi; xatolar jimgina yutilardi; «Ha» ikki marta bosilsa ikki marta ketardi → fon rejimida, sekundiga ~20 xabar, `RetryAfter` kutiladi, natija hisoboti beriladi, takroriy bosishdan himoya.
* **Balans ayirish:** summa balansdan ko‘p bo‘lsa jimgina 0 ga tushib, tranzaksiyaga to‘liq summa yozilardi, referral balans e’tiborga olinmasdi → haqiqiy o‘zgargan summa yoziladi va xabar qilinadi; avval oddiy, keyin referral balansdan yechiladi (kabinetda ko‘rinadigan umumiy balansga mos).
* **Sessiya tugaganda** (bot qayta ishga tushgach) eski tugmalar `KeyError` bilan «osilib» qolardi → tushunarli xabar.
* **Reklama tugma formati:** nomida `-` bo‘lgan tugma («Yo‘l-yo‘riq - https://…») xato berardi → regex bilan to‘g‘ri ajratiladi. Reklama namunasidagi like tugmalari (`adpreview`) javobsiz qolardi.
* `noop` tugmasi (havolasiz kanal) cheksiz «yuklanardi» → javob beradi.
* Chek bosqichida rasm o‘rniga matn yuborilsa bot jim turardi → tushuntirish beriladi. Video qo‘shishda noto‘g‘ri turdagi fayl uchun ham.

## 3. Xavfsizlik va ishonchlilik

* **Huquqlar:** barcha kanal amallari (`add_mand`, `delch`, …) bosh admin tekshiruvi bilan; hisob/xabar/rad etish bosqichlarida ham huquq qayta tekshiriladi (faqat «holat»ga tayanilmaydi).
* **Anti-fraud:** bir foydalanuvchining kutilayotgan cheklari soni cheklangan (`MAX_PENDING_TOPUPS`); summa chegaralari (`MIN_TOPUP`/`MAX_TOPUP`); chek rasmi avval yuborilgan bo‘lsa (`file_unique_id`) adminga ⚠️ ogohlantirish.
* **Takroriy bosishdan himoya** (`ThrottleMiddleware`, 0,3 s) — VIP/to‘lov tugmalarini «double-click»dan asraydi (baza darajasida ham atomik).
* **Global xatolik handleri:** foydalanuvchiga tushunarli xabar, logga to‘liq iz, bosh adminga (har xil xato uchun soatiga 1 marta) ogohlantirish.
* Bare `except:` lar (ular `CancelledError` ni ham yutardi) → aniq `except Exception`/`ValueError`.
* Webhook qolib ketgan bo‘lsa polling to‘qnashmasligi uchun start paytida `delete_webhook`.
* Temp fayl `/data` da `finally` ichida o‘chiriladi.

## 4. Tezlik

* Admin tekshiruvi (`AdminOnly`) avval **har bir foydalanuvchi xabari** uchun bazaga so‘rov berardi → endi xotiradagi kesh.
* Obuna tekshiruvi kanallar bo‘yicha **parallel** va muvaffaqiyatli natija 90 soniya eslab qolinadi (Telegram API yukini kamaytiradi; «Tekshirish» tugmasi keshni chetlab o‘tadi).
* `bot.get_me()` har ovozda chaqirilardi → keshlangan `bot.me()`.
* Indekslar qo‘shildi (`views`, `votes`, `referrals`, `topups`, `videos`, `users.vip_until`); `WAL` + `synchronous=NORMAL`.

## 5. Vaqt zonasi
Eski kod server vaqtini ko‘rsatardi (Railway = UTC), «Bugun qo‘shilganlar» esa UTC yarim tunidan sanalardi. Endi bazada UTC, foydalanuvchiga **Toshkent vaqti**, «bugun» — Toshkent kuni bo‘yicha.
*Eslatma:* agar eski VIP muddatlari UTC bo‘lmagan serverda yozilgan bo‘lsa, ular ±5 soatga siljishi mumkin (Railway uchun siljish yo‘q).

## 6. Yangi qulayliklar (ishlash tamoyilini o‘zgartirmaydi)
* Referral mukofoti berilganda taklif qiluvchiga xabar.
* Avtomatik zaxira nusxa (`BACKUP_INTERVAL_HOURS`, standart 24 soat) — Railway Volume bo‘lmagan holatdagi ma’lumot yo‘qolish xavfiga qarshi.
* Video o‘chirishda tasdiqlash bosqichi.
* Admin profilida «Bosh admin» holati; xabarlarda yagona pul formati (`10 000 so‘m`).
* Asosiy kanal havolasi (`CHANNEL_URL`) kod ichidan sozlamaga ko‘chirildi.

## 7. Kod sifati
Bir qatorga sig‘dirilgan `;` li kod to‘liq qayta yozildi; takrorlanuvchi mantiq (`user_prompt`/`edit_or_send_prompt`/`finish_prompt`, har handlerdagi 6 qatorli blok/obuna tekshiruvi, admin menyusidagi ikki nusxa mantiq) yagona joyga olindi; o‘lik kod olib tashlandi (`ACTIVE_ADMINS`, `_db_admin`, `votes()`, `quality_kb`, `yesno`, `inline`, ishlatilmagan holatlar). Modullarga bo‘lindi (`access`, `utils`, `handlers/ads`, …). Bog‘liqliklar yuqori chegara bilan qotirildi.

## 8. Sinovlar
* `tests/test_db.py` — 14 ta test (parallel xaridlar, ikki marta sarflash, gift limiti, referral qoidalari, tx rollback, zaxira…) — **hammasi o‘tdi**.
* Alohida: asl kodning poyga xatolari qayta ishlab chiqarildi va yangi kodda yo‘qolgani tasdiqlandi.
* Haqiqiy handler kodi soxta Telegram bilan 62 stsenariy bo‘yicha ishga tushirildi (start/referral/obuna, to‘lov, VIP, gift, video qo‘shish-o‘chirish, admin oqimlari, reklama, xatolik handleri) — **hammasi o‘tdi**.
* Eski bazadan yangi kodga migratsiya tekshirildi.

**Chegara:** sinovlar oflayn muhitda (haqiqiy `aiogram`/Telegram serveri bo‘lmagan) o‘tkazildi. Shuning uchun deploydan oldin **alohida test bot** bilan asosiy oqimlarni (start, to‘lov, VIP, video qo‘shish, reklama) qo‘lda bir marta tekshirib chiqing.

## 9. Ataylab o‘zgartirilmagan (xohlasangiz, alohida kelishamiz)
* Referral mukofoti obunadan oldin ham beriladi (eski mantiq saqlandi; firibgarlikka qarshi «obunadan keyin berish» variantini qo‘shish mumkin).
* FSM holati xotirada (qayta ishga tushganda jarayon tugaydi — endi xato emas, tushunarli xabar chiqadi).
* VIP tugashi haqida eslatma yo‘q.
* Kontent 18+ bo‘lsa, yoshni tasdiqlash bosqichi tavsiya etiladi.
