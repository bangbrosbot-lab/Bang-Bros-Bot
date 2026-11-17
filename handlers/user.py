"""Oddiy foydalanuvchi bo‘limi."""
from __future__ import annotations

import json
import logging

from aiogram import Bot, F, Router, types
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           InputMediaVideo)

from access import (BLOCKED_TEXT, NO_ACCESS, ask_sub, guard_call, guard_message,
                    subscribed)
from config import ADMIN_ID, CHANNEL_URL, MAX_PENDING_TOPUPS, MAX_TOPUP, MIN_TOPUP
from db import Database
from keyboards import (admin_menu, back_kb, blocked_menu, confirm_kb, main_menu,
                       rows_kb)
from states import TopUp
from timeutil import fmt_local
from utils import (delete_quietly, finish_prompt, is_not_modified, money, safe_call,
                   show_prompt, username_text)

log = logging.getLogger(__name__)
router = Router()

TARIFFS = [(1, "1 kunlik"), (7, "1 haftalik"), (30, "1 oylik")]

VIDEO_GONE = "Hozirda ushbu video mavjud emas."
VIP_REQUIRED = "Videoni tomosha qilish uchun VIP obuna sotib oling!"

REF_INTRO = """Pul ishlash uchun botimizga do'stlaringizni taklif qilishingiz kerak bo'ladi.
Sizga havola beriladi, shu havolani do'stingizga jo'natasiz, u shu havoladan o'tib botga start bossa sizga pul beriladi.
Har bir yangi do'st uchun bot sizga 500 so'mdan beradi.
U pullarni faqat bot ichidagi VIP obuna sotib olish uchun ishlatishingiz mumkin.
Havola qoidalar bilan tanishib olgandan keyin beriladi."""
REF_RULES = """Qoidalar

1) Havolani ommaviy kanal yoki guruhlarda tarqatish taqiqlanadi. Faqat shaxsiy xabar orqali, ishonchli do'stlaringizga birma-bir yuborishingiz mumkin.

2) Bitta qurilmadan bir nechta Telegram hisob ochib, o'zingizga o'zingiz referal yig'ish taqiqlanadi. Biz faqat jonli, haqiqiy foydalanuvchilar uchun mukofot beramiz, soxta hisoblar uchun emas.

3) Foydalanuvchilarni yolg'on ma'lumot bilan aldab taklif qilish taqiqlanadi. Bunday holatda taklif qilingan foydalanuvchi botdan ham, sizdan ham norozi bo'ladi va bu ko'plab kelishmovchiliklarni keltirib chiqaradi.

Qoida buzilsa nima bo'ladi?
Tizim buzilishni darhol aniqlaydi va sizni botdan butunlay bloklaydi. Bundan keyin botdan foydalana olmaysiz.

Barcha qoidalarga rioya qilishga rozimisiz? Agar "Ha" tugmasini bossangiz, sizga referal havolangiz taqdim etiladi."""


# ----------------------------------------------------------------- yordamchilar
def parse_start_args(args: str | None) -> tuple[int | None, int | None]:
    """/start parametridan (taklif qiluvchi ID, video ID) ni ajratadi."""
    if not args:
        return None, None
    arg = args.strip()
    if arg.startswith("video_"):
        tail = arg[6:]
        return None, int(tail) if tail.isdigit() else None
    for prefix in ("ref_", "ref"):
        if arg.startswith(prefix):
            tail = arg[len(prefix):]
            return (int(tail) if tail.isdigit() else None), None
    return None, None


async def referral_link(user_id: int, bot: Bot) -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}?start=ref{user_id}"


async def welcome(m, bot, db, user=None):
    user = user or m.from_user
    text = (f"Salom, {user.first_name}! Bang Bros’ga xush kelibsiz!\n\n"
            "Videolarni tomosha qilish uchun maxsus kanalimizga kiring va o‘zingizga yoqqan videoni "
            "tanlab, «Videoni ko‘rish» tugmasini bosing!")
    special = await db.special_channel()
    rows = []
    if special:
        url = special["join_url"]
        if not url:
            try:
                chat = await bot.get_chat(special["channel_id"])
                if chat.username:
                    url = f"https://t.me/{chat.username}"
            except Exception:
                pass
        if url:
            rows.append([InlineKeyboardButton(text="Kanalga kirish", url=url)])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    await m.answer("Asosiy menyu", reply_markup=main_menu())


async def notify_new_user(bot, user, referrer=None):
    username = username_text(user.username)
    if referrer:
        text = ("Referral orqali yangi foydalanuvchi\n\n"
                f"Ismi: {user.full_name}\nUseri: {username}\nIDsi: {user.id}\nTaklif qiluvchi: {referrer}")
    else:
        text = f"Yangi foydalanuvchi\n\nIsmi: {user.full_name}\nUseri: {username}\nIDsi: {user.id}"
    await safe_call(lambda: bot.send_message(ADMIN_ID, text))


async def deliver_teaser(m, db, vid):
    v = await db.video(vid)
    if not v:
        return await m.answer(VIDEO_GONE)
    await m.answer_video(
        v["teaser_id"], caption=v["caption"], protect_content=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="To‘liq video", callback_data=f"full:{vid}")]]))


def video_kb(vid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Video sifatini almashtirish", callback_data=f"change:{vid}")]])


def full_caption(v, quality_name: str, views: int) -> str:
    return f"{v['caption']}\n\nSifati: {quality_name}\nKo‘rishlar: {views}"


async def send_full_video(message, db, v, quality_row, vid):
    views = await db.view_count(vid)
    await message.answer_video(quality_row["file_id"], caption=full_caption(v, quality_row["quality"], views),
                               protect_content=True, reply_markup=video_kb(vid))


async def vote_markup(db, vid, bot_username):
    likes, dislikes = await db.vote_counts(vid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Yoqdi ({likes})", callback_data=f"vote:{vid}:1"),
         InlineKeyboardButton(text=f"Yoqmadi ({dislikes})", callback_data=f"vote:{vid}:-1")],
        [InlineKeyboardButton(text="Videoni ko‘rish", url=f"https://t.me/{bot_username}?start=video_{vid}")]])


async def tariff_rows(db):
    return [(f"{label} — {money(int(await db.setting(f'vip_{days}')))} so‘m", f"vipbuy:{days}")
            for days, label in TARIFFS]


# ------------------------------------------------------------------------ start
@router.message(CommandStart())
async def start(m: types.Message, command: CommandObject, db: Database, bot: Bot, state: FSMContext):
    await state.clear()
    ref, video_id = parse_start_args(command.args)
    uid = m.from_user.id
    is_new = await db.add_user(uid, m.from_user.full_name, m.from_user.username, ref)
    u = await db.user(uid)
    if u["blocked"]:
        return await m.answer(BLOCKED_TEXT, reply_markup=blocked_menu())
    if uid == ADMIN_ID or db.is_admin(uid):
        return await m.answer("Admin panel", reply_markup=admin_menu())

    if is_new:
        valid_ref = ref if ref and ref != uid else None
        credited = False
        if valid_ref:
            bonus = int(await db.setting("referral_bonus") or 500)
            credited = await db.credit_referral(uid, valid_ref, bonus)
            if credited:
                await safe_call(lambda: bot.send_message(
                    valid_ref, f"Do‘stingiz botga qo‘shildi! Referral balansingizga {money(bonus)} so‘m qo‘shildi."))
        await notify_new_user(bot, m.from_user, valid_ref if valid_ref and await db.user(valid_ref) else None)

    if not await subscribed(bot, db, uid):
        if video_id is not None:  # obunadan keyin shu videoga qaytamiz
            await state.update_data(pending_video=video_id, need_menu=is_new)
        return await ask_sub(m, db)
    if video_id is not None:
        await deliver_teaser(m, db, video_id)
        if is_new:  # birinchi tanishuv: pastki menyu hali yo‘q — faqat bir marta
            await m.answer("Asosiy menyu", reply_markup=main_menu())
        return
    await welcome(m, bot, db)


@router.callback_query(F.data == "check_sub")
async def check(call: types.CallbackQuery, db: Database, bot: Bot, state: FSMContext):
    u = await db.user(call.from_user.id)
    if u and u["blocked"]:
        return await call.answer(NO_ACCESS, show_alert=True)
    if not await subscribed(bot, db, call.from_user.id, use_cache=False):
        return await call.answer("Hali barcha kanallarga qo‘shilmadingiz yoki so‘rovingiz qabul qilinmadi.",
                                 show_alert=True)
    await delete_quietly(call.message)
    data = await state.get_data()
    pending = data.get("pending_video")
    if pending is not None:
        await state.update_data(pending_video=None, need_menu=False)
        await deliver_teaser(call.message, db, pending)
        if data.get("need_menu"):  # yangi foydalanuvchi: pastki menyu faqat shu bir marta
            await call.message.answer("Asosiy menyu", reply_markup=main_menu())
    else:
        await welcome(call.message, bot, db, call.from_user)
    await call.answer()


@router.callback_query(F.data == "noop")
async def noop(call: types.CallbackQuery):
    await call.answer()


# ------------------------------------------------------------------------ videolar
@router.callback_query(F.data.startswith("full:"))
async def full(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot):
        return
    vid = int(call.data.split(":")[1])
    if not await db.vip(call.from_user.id):
        return await call.answer(
            "Afsuski, hozircha ushbu videoning to‘liq versiyasini ko‘ra olmaysiz. "
            "To‘liq videolarni tomosha qilish uchun VIP obuna xarid qilishingiz kerak!", show_alert=True)
    v, qs = await db.video(vid), await db.qualities(vid)
    if not v or not qs:
        return await call.answer(VIDEO_GONE, show_alert=True)
    await db.count_view(call.from_user.id, vid)
    await send_full_video(call.message, db, v, qs[0], vid)
    await call.answer()


@router.callback_query(F.data.startswith("change:"))
async def change(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot):
        return
    if not await db.vip(call.from_user.id):
        return await call.answer(VIP_REQUIRED, show_alert=True)
    vid = int(call.data.split(":")[1])
    qs = await db.qualities(vid)
    if not await db.video(vid) or not qs:
        return await call.answer(VIDEO_GONE, show_alert=True)
    rows = [(r["quality"], f"quality:{vid}:{r['quality']}") for r in qs] + [("Orqaga", f"changeback:{vid}")]
    await call.message.edit_reply_markup(reply_markup=rows_kb(rows))  # yangi xabar chiqmaydi
    await call.answer("Kerakli sifatni tanlang!")


@router.callback_query(F.data.startswith("changeback:"))
async def change_back(call: types.CallbackQuery):
    vid = int(call.data.split(":")[1])
    try:
        await call.message.edit_reply_markup(reply_markup=video_kb(vid))
    except Exception as e:
        if not is_not_modified(e):
            raise
    await call.answer()


@router.callback_query(F.data.startswith("quality:"))
async def quality(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot):
        return
    if not await db.vip(call.from_user.id):
        return await call.answer(VIP_REQUIRED, show_alert=True)
    _, raw_vid, q = call.data.split(":", 2)
    vid = int(raw_vid)
    v = await db.video(vid)
    if not v:
        await call.answer(VIDEO_GONE, show_alert=True)
        return await delete_quietly(call.message)
    chosen = next((r for r in await db.qualities(vid) if r["quality"] == q), None)
    if not chosen:
        return await call.answer("Bu sifat mavjud emas.", show_alert=True)
    caption = full_caption(v, chosen["quality"], await db.view_count(vid))
    try:  # videoni o‘sha xabarning o‘zida almashtiramiz — chat to‘lib ketmaydi
        await call.message.edit_media(media=InputMediaVideo(media=chosen["file_id"], caption=caption),
                                      reply_markup=video_kb(vid))
    except Exception as e:
        if is_not_modified(e):
            try:
                await call.message.edit_reply_markup(reply_markup=video_kb(vid))
            except Exception:
                pass
        else:  # zaxira yo‘l: eski usul (o‘chirib, yangisini yuborish)
            log.warning("edit_media ishlamadi (%s), zaxira usul", e)
            await delete_quietly(call.message)
            await send_full_video(call.message, db, v, chosen, vid)
    await call.answer()


@router.callback_query(F.data.startswith("vote:"))
async def vote(call: types.CallbackQuery, db: Database, bot: Bot):
    u = await db.user(call.from_user.id)
    if u and u["blocked"]:
        return await call.answer(NO_ACCESS, show_alert=True)
    try:
        _, raw_vid, raw_vote = call.data.split(":")
        vid, value = int(raw_vid), int(raw_vote)
        if value not in (1, -1):
            raise ValueError
    except ValueError:
        return await call.answer("Ovoz qabul qilinmadi.", show_alert=True)
    if not await db.video(vid):
        return await call.answer(VIDEO_GONE, show_alert=True)
    await db.vote(call.from_user.id, vid, value)
    try:
        me = await bot.me()
        await call.message.edit_reply_markup(reply_markup=await vote_markup(db, vid, me.username))
    except Exception as e:
        if not is_not_modified(e):
            log.warning("Vote markup yangilanmadi: %s", e)
    await call.answer("Ovozingiz saqlandi.")


@router.callback_query(F.data.startswith("advote:"))
async def ad_vote(call: types.CallbackQuery, db: Database):
    u = await db.user(call.from_user.id)
    if u and u["blocked"]:
        return await call.answer(NO_ACCESS, show_alert=True)
    try:
        _, raw_campaign, raw_option = call.data.split(":")
        campaign_id, option = int(raw_campaign), int(raw_option)
        campaign = await db.ad_campaign(campaign_id)
        if not campaign:
            return await call.answer("Reklama ovoz berish muddati tugagan.", show_alert=True)
        options = json.loads(campaign["like_options"] or "[]")
        if option < 0 or option >= len(options):
            return await call.answer("Noto‘g‘ri ovoz.", show_alert=True)
    except ValueError:
        return await call.answer("Ovoz qabul qilinmadi.", show_alert=True)
    await db.ad_vote(campaign_id, call.from_user.id, option)
    counts = await db.ad_vote_counts(campaign_id)
    rows = [[InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row]
            for row in json.loads(campaign["url_buttons"] or "[]")]
    for row in json.loads(campaign["like_layout"] or "[]"):
        rows.append([InlineKeyboardButton(text=f"{i['text']} ({counts.get(i['index'], 0)})",
                                          callback_data=f"advote:{campaign_id}:{i['index']}") for i in row])
    try:
        await call.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception as e:
        if not is_not_modified(e):
            log.warning("Ad markup yangilanmadi: %s", e)
    await call.answer("Ovozingiz qabul qilindi.")


# ------------------------------------------------------------------------ kabinet
async def send_cabinet(target, uid, db):
    u = await db.user(uid)
    if not u:
        return await target.answer("Avval /start buyrug‘ini bosing.")
    is_vip = await db.vip(uid)
    status = f"VIP obunachi\nVIP muddati: {fmt_local(u['vip_until'])}" if is_vip else "Oddiy obunachi"
    total = int(u["balance"] or 0) + int(u["referral_balance"] or 0)
    friends = await db.referrals_count(uid)
    return await target.answer(
        f"Ism: {u['name']}\nUser: {username_text(u['username'])}\nID: {u['user_id']}\n"
        f"Balans: {money(total)} so‘m\nHolati: {status}\nDo‘stlar: {friends}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Hisobni to‘ldirish", callback_data="topup")]
            + ([] if is_vip else [InlineKeyboardButton(text="VIP olish", callback_data="vipmenu")]),
            [InlineKeyboardButton(text="Pul ishlash", callback_data="referral")]]))


# Menyu tugmalari holatdan (state) qat’i nazar ishlaydi — shuning uchun TopUp holatlaridan OLDIN ro‘yxatdan o‘tadi.
@router.message(F.text == "Kabinet")
async def cabinet(m: types.Message, db: Database, bot: Bot, state: FSMContext):
    if not await guard_message(m, db, bot):
        return
    await state.clear()
    await send_cabinet(m, m.from_user.id, db)


@router.message(F.text == "Bot haqida")
async def about(m: types.Message, db: Database, bot: Bot, state: FSMContext):
    if not await guard_message(m, db, bot):
        return
    await state.clear()
    kind, file_id = await db.setting("info_type"), await db.setting("info_file_id")
    caption = await db.setting("info_caption")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Kanalimiz", url=CHANNEL_URL)]])
    if kind == "photo" and file_id:
        await m.answer_photo(file_id, caption=caption or None, reply_markup=kb, protect_content=True)
    elif kind == "video" and file_id:
        await m.answer_video(file_id, caption=caption or None, reply_markup=kb, protect_content=True)
    else:
        body = caption or await db.setting("bot_info") or "Bot haqida ma’lumot hozircha kiritilmagan."
        await m.answer(body, reply_markup=kb)


@router.message(F.text == "Yordam")
async def help_(m: types.Message, db: Database, bot: Bot, state: FSMContext):
    u = await db.user(m.from_user.id)
    if not (u and u["blocked"]) and not await subscribed(bot, db, m.from_user.id):
        return await ask_sub(m, db)
    await state.clear()
    url = (await db.setting("admin_link") or "").strip()
    if url.startswith("@"):
        url = "https://t.me/" + url[1:]
    elif url.startswith("t.me/"):
        url = "https://" + url
    kb = None
    if url.startswith(("https://", "http://", "tg://")):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Bog‘lanish", url=url)]])
    await m.answer("Agar sizda muammolar yoki qanaqadur savollar paydo bo‘lgan bo‘lsa admin bilan bog‘lanishingiz mumkin",
                   reply_markup=kb)


# ------------------------------------------------------------------------ hisobni to‘ldirish
@router.callback_query(F.data == "topup")
async def topup(call: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    if not await guard_call(call, db, bot):
        return
    await state.clear()
    await state.set_state(TopUp.amount)
    await show_prompt(call.message, state, "To‘ldirmoqchi bo‘lgan summangizni yozing! Masalan: 10000",
                      back_kb("topupback"))
    await call.answer()


@router.callback_query(F.data == "topupback")
async def topup_back(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await delete_quietly(call.message)
    await call.answer()


@router.message(TopUp.amount)
async def topup_amount(m: types.Message, state: FSMContext, db: Database):
    try:
        amount = int((m.text or "").replace(" ", "").replace(",", ""))
    except ValueError:
        return await m.answer("Summani raqam bilan kiriting.")
    if amount < MIN_TOPUP:
        return await m.answer(f"Eng kam to‘ldirish summasi {money(MIN_TOPUP)} so‘m. "
                              "Iltimos, bundan kam bo‘lmagan summa kiriting.")
    if amount > MAX_TOPUP:
        return await m.answer(f"Eng ko‘p to‘ldirish summasi {money(MAX_TOPUP)} so‘m. "
                              "Iltimos, kamroq summa kiriting.")
    await state.update_data(amount=amount)
    await state.set_state(TopUp.receipt)
    card = await db.setting("card")
    await delete_quietly(m)
    await show_prompt(m, state, "Quyidagi karta raqamiga kerakli summani o‘tkazing!\n\n"
                                f"Summa: {money(amount)} so‘m\nKarta: {card}\n\n"
                                "To‘lovni amalga oshirgach, to‘lov chek rasmini jo‘nating!", back_kb("topupback"))


@router.message(TopUp.receipt, F.photo)
async def receipt(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    amount = data.get("amount")
    if not amount:
        await state.clear()
        return await m.answer("Seans tugagan. Kabinet orqali qaytadan boshlang.")
    if await db.pending_count(m.from_user.id) >= MAX_PENDING_TOPUPS:
        return await m.answer("Sizda ko‘rib chiqilayotgan to‘lovlar juda ko‘p. "
                              "Iltimos, admin ularni tasdiqlashini kuting.")
    photo = m.photo[-1]
    duplicate = await db.receipt_seen(photo.file_unique_id)
    rid = await db.create_topup(m.from_user.id, amount, photo.file_id, photo.file_unique_id)
    username = username_text(m.from_user.username)
    caption = (f"Hisobni to‘ldirish so‘rovi\n\nIsmi: {m.from_user.full_name}\nUser: {username}\n"
               f"ID: {m.from_user.id}\nSumma: {money(amount)} so‘m")
    if duplicate:
        caption += "\n\n⚠️ Diqqat: bu chek rasmi avval ham yuborilgan!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash", callback_data=f"topupok:{rid}"),
        InlineKeyboardButton(text="Rad etish", callback_data=f"topupno:{rid}")]])
    for admin_id in {ADMIN_ID, *db.admins_with_permission("payments")}:
        await safe_call(lambda a=admin_id: bot.send_photo(
            a, photo.file_id, caption=caption, reply_markup=kb, protect_content=True))
    await delete_quietly(m)
    await finish_prompt(m, state, "To‘lov chekingiz adminga yuborildi.\n"
                                  f"Admin to‘lovni tasdiqlaganidan so‘ng, {money(amount)} so‘m hisobingizga qo‘shiladi.")


@router.message(TopUp.receipt)
async def receipt_wrong_type(m: types.Message):
    await m.answer("Iltimos, to‘lov chekini rasm (skrinshot) ko‘rinishida yuboring.")


# ------------------------------------------------------------------------ VIP
@router.callback_query(F.data == "vipmenu")
async def vipmenu(call: types.CallbackQuery, db: Database, bot: Bot, state: FSMContext):
    if not await guard_call(call, db, bot):
        return
    await state.clear()
    await call.message.answer("VIP tarifini tanlang:", reply_markup=rows_kb(await tariff_rows(db)))
    await call.answer()


@router.callback_query(F.data == "vipnotice")
async def vip_notice_click(call: types.CallbackQuery, db: Database, bot: Bot):
    """«VIP olish» tugmasi (tugash haqidagi eslatmada): eslatma xabarining o‘zi tariflar ro‘yxatiga aylanadi."""
    if not await guard_call(call, db, bot):
        return
    await call.message.edit_text("VIP tarifini tanlang:", reply_markup=rows_kb(await tariff_rows(db)))
    await call.answer()


@router.callback_query(F.data.startswith("vipbuy:"))
async def vipbuy(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot):
        return
    days = int(call.data.split(":")[1])
    if days not in dict(TARIFFS):
        return await call.answer()
    price = int(await db.setting(f"vip_{days}"))
    u = await db.user(call.from_user.id)
    available = int(u["balance"] or 0) + int(u["referral_balance"] or 0)
    if available < price:
        return await call.answer(
            f"Balansingizda yetarli mablag‘ yo‘q.\nKerak: {money(price)} so‘m\nBalansingiz: {money(available)} so‘m\n"
            "Hisobingizni to‘ldirish uchun Kabinetdagi \"Hisobni to‘ldirish\" bo‘limidan foydalaning!",
            show_alert=True)
    await call.message.edit_text(
        f"Tarif: {dict(TARIFFS)[days]}\nNarxi: {money(price)} so‘m\n\n"
        "Haqiqatdan ham ushbu VIP obunani sotib olmoqchimisiz?",
        reply_markup=confirm_kb(f"vipconfirm:{days}", "vipcancel"))
    await call.answer()


@router.callback_query(F.data == "vipcancel")
async def vipcancel(call: types.CallbackQuery, db: Database):
    await call.message.edit_text("VIP tarifini tanlang:", reply_markup=rows_kb(await tariff_rows(db)))
    await call.answer()


@router.callback_query(F.data.startswith("vipconfirm:"))
async def vipconfirm(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot):
        return
    days = int(call.data.split(":")[1])
    if days not in dict(TARIFFS):
        return await call.answer()
    price = int(await db.setting(f"vip_{days}"))
    expiry = await db.purchase_vip(call.from_user.id, days, price)
    if not expiry:
        return await call.answer("Balans yetarli emas yoki xarid amalga oshmadi.", show_alert=True)
    await call.message.edit_text(f"VIP obunangiz faollashtirildi.\nAmal qilish muddati: {fmt_local(expiry)}")
    await call.answer()


# ------------------------------------------------------------------------ referral
async def _send_ref_link(target, uid, bot, db, edit=False):
    link = await referral_link(uid, bot)
    send = target.edit_text if edit else target.answer
    await send(
        f"Sizning shaxsiy referal havolangiz:\n{link}\n\nUshbu havolani ishonchli do‘stlaringizga yuboring. "
        f"Ular havola orqali botga kirib start bossa, hisobingizga {await db.setting('referral_bonus')} so‘m qo‘shiladi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Havolani nusxalash", copy_text=types.CopyTextButton(text=link))]]))


@router.callback_query(F.data == "referral")
async def referral(call: types.CallbackQuery, db: Database, bot: Bot, state: FSMContext):
    if not await guard_call(call, db, bot, sub_alert="Avval majburiy kanallarga obuna bo‘ling."):
        return
    await state.clear()
    u = await db.user(call.from_user.id)
    if not u["rules_accepted"]:
        await call.message.answer(REF_INTRO, reply_markup=rows_kb([("Qoidalar", "ref_rules")]))
    else:
        await _send_ref_link(call.message, call.from_user.id, bot, db)
    await call.answer()


@router.callback_query(F.data == "ref_rules")
async def ref_rules(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot, need_sub=False):
        return
    await call.message.edit_text(REF_RULES, reply_markup=confirm_kb("refaccept", "refdecline"))
    await call.answer()


@router.callback_query(F.data == "refaccept")
async def refaccept(call: types.CallbackQuery, db: Database, bot: Bot):
    if not await guard_call(call, db, bot, need_sub=False):
        return
    await db.accept_rules(call.from_user.id)
    await _send_ref_link(call.message, call.from_user.id, bot, db, edit=True)
    await call.answer()


@router.callback_query(F.data == "refdecline")
async def refdecline(call: types.CallbackQuery, db: Database):
    await delete_quietly(call.message)
    await send_cabinet(call.message, call.from_user.id, db)
    await call.answer()


# ------------------------------------------------------------------------ gift
@router.callback_query(F.data.startswith("claimgift:"))
async def claim_gift(call: types.CallbackQuery, db: Database, bot: Bot):
    u = await db.user(call.from_user.id)
    if u and u["blocked"]:
        return await call.answer(NO_ACCESS, show_alert=True)
    gid = int(call.data.split(":")[1])
    status, g, last = await db.claim_gift(gid, call.from_user.id)
    if status == "won":
        if g["kind"] == "vip":
            msg = f"Tabriklaymiz! Siz {g['days']} kunlik VIP sovg‘ani qo‘lga kiritdingiz."
        else:
            msg = f"Tabriklaymiz! {money(g['amount'])} so‘m sovg‘a balansingizga qo‘shildi."
        await call.answer(msg, show_alert=True)
        if last:
            lines = ["Gift g‘oliblari:"]
            for i, w in enumerate(await db.gift_winners(gid), 1):
                lines.append(f"{i}. {w['name']} | {username_text(w['username'])} | {w['user_id']}")
            await safe_call(lambda: bot.send_message(ADMIN_ID, "\n".join(lines)))
    elif status == "vip":
        await call.answer("Sizda allaqachon faol VIP obuna bor.", show_alert=True)
    elif status == "already":
        await call.answer("Siz allaqachon o‘z sovg‘angizni oldingiz.", show_alert=True)
    elif status == "late":
        await call.answer("Afsuski, siz ulgurmadingiz. Keyingi giftda faolroq bo‘ling!", show_alert=True)
    else:
        await call.answer("Gift faol emas yoki topilmadi.", show_alert=True)


@router.chat_join_request()
async def track_join_request(event: types.ChatJoinRequest, db: Database):
    await db.add_join_request(event.from_user.id, event.chat.id)
