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


---

# 2-yangilanish (qulaylik va chatni tozalash)

## Chat toza bo‘lishi
* **Obuna matni endi bitta xabar:** «Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling!» va ostida kanal tugmalari (avval ikkita xabar edi). Pastki menyu (Kabinet / Yordam / Bot haqida) endi olib tashlanmaydi.
* **«Asosiy menyu» xabari** teaser va har sifat almashtirishdan keyin chiqmaydi. Faqat butunlay yangi foydalanuvchi video havolasi orqali birinchi marta kirganda (unda pastki menyu hali yo‘q) **bir marta** chiqadi.
* **Pastki bo‘limlar yo‘qolmasligi:** menyu «doimiy» (`is_persistent`) qilindi — yig‘ilib qolmaydi; obuna so‘ralganda ham olib tashlanmaydi. `/start` bosilsa menyu qayta tiklanadi.
* **Sifatni almashtirish** endi yangi xabar yubormaydi: «Video sifatini almashtirish» bosilganda tugmalar videoning o‘z xabarida chiqadi (**Orqaga** tugmasi bilan), sifat tanlansa video o‘sha xabarda almashadi. Biror sabab bilan Telegram buni qabul qilmasa, eski usulga (o‘chirib qayta yuborish) avtomatik qaytadi.
* VIP tariflari, referral qoidalari, to‘lov va kanal bo‘limlarida yangi xabar o‘rniga mavjud xabar tahrirlanadi.

## Video o‘chirilgan yoki VIP tugagan holatlar
* Video bazadan o‘chirilgan bo‘lsa, eski xabardagi sifat/to‘liq video/ovoz tugmalari: **«Hozirda ushbu video mavjud emas.»** (bo‘sh «Sifatni tanlang» chiqmaydi).
* VIP muddati tugagan bo‘lsa, eski xabardagi sifat almashtirish: **«Videoni tomosha qilish uchun VIP obuna sotib oling!»** — hech qanday video yoki tugma chiqmaydi.

## Kabinet va VIP eslatmasi
* VIP foydalanuvchi kabinetida **«VIP muddati: …»** (Toshkent vaqti) ko‘rinadi, **«VIP olish» tugmasi chiqmaydi**.
* **VIP tugashiga 1 kun qolganda** bot eslatma yuboradi («VIP olish» tugmasi bilan). Tugma bosilsa eslatmaning o‘zi VIP tariflariga aylanadi.
  Har bir muddat uchun eslatma faqat bir marta; obuna uzaytirilsa yangi muddat uchun yana. 1 kunlik tarif olganda darhol eslatma kelmaydi. Tekshiruv har 30 daqiqada.

## «Orqaga» tugmalari (admin)
* **Admin tayinlash:** huquqlar oynasida «Orqaga» — hech narsa saqlanmay foydalanuvchi profiliga qaytadi.
* VIP narxini o‘zgartirish, Kanallar (qo‘shish/o‘chirish), foydalanuvchi amallari (balans/VIP/xabar), video qo‘shishda sifat tanlash, Gift (tur → tarif/summa → g‘oliblar) bo‘limlarida ham «Orqaga».
* Foydalanuvchi tomonida: hisobni to‘ldirish bosqichlarida «Orqaga» (kabinetga qaytish).

## Sinovlar
92 ta stsenariy (yangi xatti-harakatlarning hammasi) va 17 ta baza testi o‘tdi. Eslatma: `edit_media` ishlashi faqat haqiqiy Telegramda to‘liq tasdiqlanadi (zaxira yo‘li bor).

---

# 2-versiya: chatni toza saqlash va qulayliklar

## Chatdagi ortiqcha xabarlar
* **Majburiy obuna xabari endi bitta:** «Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling!» (kanal tugmalari shu xabarning o‘zida).
* **«Asosiy menyu» xabari** teaserdan keyin va har sifat almashtirganda chiqmaydi. Pastki menyu faqat bir marta — mutlaqo yangi foydalanuvchi birinchi marta video havolasi orqali kirganda (menyusi hali yo‘q) yuboriladi; `/start` bosilganda ham tiklanadi.
* **Sifat almashtirish** endi yangi xabar yaratmaydi: tugmalar video xabarning o‘zida chiqadi, tanlangach video o‘sha xabarning o‘zida almashadi (sarlavhada yangi sifat). «Orqaga» tugmasi asl holatni qaytaradi. Agar Telegram xabarni tahrirlashga ruxsat bermasa (masalan, juda eski xabar), eski usulga (o‘chirib, qayta yuborish) o‘tadi.
* Hisob to‘ldirish, VIP tarif tasdig‘i va referral qoidalari yangi xabar yaratmasdan, mavjud xabarni tahrirlaydi.

## Pastki bo‘limlar (Kabinet / Yordam / Bot haqida)
Klaviatura endi «doimiy» (`is_persistent`) — yig‘ilib yoki yo‘qolib qolmaydi; obuna so‘ralganda ham olib tashlanmaydi.

## O‘chirilgan video va muddati tugagan VIP
* Video bazadan o‘chirilgan bo‘lsa, foydalanuvchidagi eski xabarlarda tugmalar bosilganda «Hozirda ushbu video mavjud emas.» deb chiqadi (bo‘sh «sifatni tanlang» xabari chiqmaydi).
* VIP muddati tugagan foydalanuvchi eski videodagi «Video sifatini almashtirish»ni bossa: «Videoni tomosha qilish uchun VIP obuna sotib oling!» — hech qanday video yoki tanlov chiqmaydi.
* Tekshiruv tartibi: avval VIP, keyin video mavjudligi.

## Kabinet va VIP
* VIP foydalanuvchi kabinetida **VIP tugash muddati** ko‘rinadi, «VIP olish» tugmasi esa yo‘q.
* **Tugashiga 1 kun qolganda** avtomatik xabar yuboriladi, ostida «VIP olish» tugmasi; bossa shu xabarning o‘zi tariflar ro‘yxatiga aylanadi. Har bir muddat uchun faqat bir marta yuboriladi (uzaytirilsa, yangi muddat uchun yana eslatiladi); 1 kunlik tarif olinganda darhol eslatma kelmaydi. Bot har 30 daqiqada tekshiradi.

## «Orqaga» tugmalari
Admin huquqlarini belgilash (`Orqaga` + `Bo‘ldi`), kanallar bo‘limi (qo‘shish/o‘chirish), VIP narxini o‘zgartirish, foydalanuvchi amallari (summa/kun/xabar kiritish), video qo‘shishda sifat tanlash, Gift (tur → tarif/summa → g‘oliblar soni), foydalanuvchining hisob to‘ldirish bosqichlari.

## Sinovlar
`tests/test_db.py` — 17 ta test; handlerlar bo‘yicha soxta Telegram bilan 92 ta stsenariy — hammasi o‘tdi. Eski bazadan migratsiya (yangi `vip_notified` ustuni) tekshirildi.
**Eslatma:** sinovlar oflayn muhitda o‘tkazilgan; sifatni xabar ichida almashtirish (`editMessageMedia`) haqiqiy Telegramda test botda bir marta tekshirib ko‘rilsin.

## 3-versiya: username ko‘rinishi
Username bo‘lmasa «@mavjud emas» emas, faqat «Mavjud emas» yoziladi; bor bo‘lsa «@nom». Barcha joyda yagona `username_text()` ishlatiladi: kabinet, admin profili, `/id` ro‘yxati, yangi foydalanuvchi xabari, to‘lov cheki xabari va gift g‘oliblari ro‘yxati.


## 4-yangilanish: admin huquqlari, orqaga navigatsiya va like ko‘rinishi
* Bot egasining ID si mavjud `ADMIN_ID` o‘zgaruvchisidan olinadi; shu ID egasi barcha ruxsatlarga avtomatik ega bo‘ladi. Menyu callbackidan ishga tushgan sozlama handlerlarida bot xabari `from_user` ID si emas, shaxsiy chat ID si tekshiriladi — shu sababli bosh admin endi «huquqingiz yetmaydi» xabarini olmaydi.
* Admin va foydalanuvchi bo‘limlaridagi kerakli bosqichlarga «Orqaga» tugmalari qo‘shildi.
* FSM jarayonida yuborilgan foydalanuvchi xabarlari handlerdan keyin o‘chiriladi; xato javoblari mavjud prompt xabarini tahrirlaydi. Menyu almashganda reklama preview kabi vaqtinchalik nusxalar ham tozalanadi.
* Foydalanuvchi menyusidagi bo‘limlar bir xil xabarni tahrirlab ochiladi; `/start` qayta bosilganda avvalgi vaqtinchalik prompt o‘chiriladi.
* Like/dislike va reklama ovozlarida boshlang‘ich `0` ko‘rsatilmaydi. Birinchi ovozdan keyingina tegishli tugmada `(1)` ko‘rinadi; nolga qaytsa raqam yana yashiriladi.

## 7. Oxirgi tuzatishlar
1. **/start:** faqat video havolasi (`?start=video_…`) orqali kelgan /start o‘chiriladi; oddiy /start (birinchi marta ham) o‘chirilmaydi.
2. **Majburiy a’zolik:** `SubscriptionMiddleware` har bir xabar/tugmada obunani qayta tekshiradi (avval Orqaga/Kabinet/ovoz/gift/chek bosqichlari tekshirilmasdi). Kesh 90 s → 3 s. Kanaldan chiqqan foydalanuvchining eski «qo‘shilish so‘rovi» izi `chat_member` hodisasida tozalanadi.
3. **VIP eslatma:** 1 kunlik obuna (va 1 kunlik gift) — tugashiga 1 soat qolganda; 1 haftalik/1 oylik/uzoq gift — 1 kun qolganda. Olingan zahoti eslatma ketmaydi. Tekshiruv har 5 daqiqada.
4. **Chek bir nechta adminda:** chek faqat «Chek tasdiqlash» huquqi bor adminlarga (va bosh adminga) boradi. Birinchi admin qaror qilgach, boshqa adminlar tugma bossa, chek rasmi/matni o‘chiriladi va «Chek allaqachon ko‘rildi va tasdiqlandi/rad etildi.» + «Asosiy menyu» tugmasi chiqadi.
5. **Foydalanuvchi qidiruvi:** bosh admin / o‘zi / boshqa admin uchun alohida kartalar; admin faqat o‘zida bor huquqlarni bera oladi va faqat o‘zi tayinlagan adminni oladi (`admins.appointed_by`).
6. **Xabar yuborish (`handlers/messaging.py`):** «Sizga xabar keldi.» + [Javob yozish | Bosh menyu]; javob zanjiri har ikki tomonda ishlaydi.
7. **Bildirishnomalar:** admin/VIP/balans xabarlariga «Bosh menyu», bekor qilish xabarlariga «Yordam | Bosh menyu» tugmalari. Bloklanganlar uchun «Yordam» tugmasi ishlaydi.
8. **Chek:** «To‘lov chekingiz adminga yuborildi» xabari tasdiq/rad etilgach o‘chadi. **Gift:** olingach asosiy menyu ochiladi.
9. **Gift:** faqat oddiy foydalanuvchilarga (adminlar, bosh admin ham, chiqarib tashlangan; adminlar qatnasha ham olmaydi); yangi xabar matni.
10. **Eski xabarlarni o‘chirish (`pushes.py`):** botdan kelgan yangi xabar shu chatdagi botning eski matnli xabarlarini o‘chiradi. Rasm/video/chek rasmlari o‘chmaydi.
11. **«Sizga xabar keldi»:** bitta xabar ichida (matn: «Xabar: …», rasm/video: shu media tagida; adminga Ism/Id/User ham). Stiker kabi izohsiz turlarda sarlavha alohida chiqadi.
12. **Bosh menyu yagona:** chatda yangi bosh menyu (foydalanuvchi yoki admin paneli) ochilsa, oldingisi o‘chiriladi (`pushes.py`).
