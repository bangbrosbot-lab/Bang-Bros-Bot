"""Reklama tarqatish va Gift o‘tkazish (admin)."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import keyboards as kb
from db import Database
from handlers.filters import AdminOnly
from states import Broadcast, Gift
from utils import (delete_quietly, finish_prompt, is_not_modified, mass_send, money,
                   safe_call, show_prompt, spawn)

log = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())

URL_BUTTON_RE = re.compile(r"^(.+?)\s*-\s*((?:https?|tg)://\S+)$")


# ===================================================================== REKLAMA
def parse_ad_buttons(raw: str):
    rows = []
    for line in raw.splitlines():
        row = []
        for part in line.split("|"):
            part = part.strip()
            if not part:
                continue
            match = URL_BUTTON_RE.match(part)
            if not match:
                raise ValueError("Tugma nomi va havola orasida - belgisi bo‘lishi, havola esa http(s):// bilan boshlanishi kerak.")
            row.append({"text": match.group(1).strip(), "url": match.group(2)})
        if len(row) > 3:
            raise ValueError("Bir qatorda uchtagacha tugma qo‘shish mumkin.")
        if row:
            rows.append(row)
    if not rows:
        raise ValueError("Kamida bitta tugma yuboring.")
    return rows


def parse_like_layout(raw: str):
    rows, options = [], []
    for line in raw.splitlines():
        for row_text in line.split("|"):
            row = []
            for token in row_text.split("/"):
                token = token.strip()
                if not token:
                    continue
                if len(token) > 32:
                    raise ValueError("Tugma matni juda uzun.")
                row.append({"text": token, "index": len(options)})
                options.append(token)
            if row:
                rows.append(row)
    if not options:
        raise ValueError("Like tugmalarini kiriting.")
    if len(options) > 30:
        raise ValueError("30 tadan ortiq like tugmasi qo‘shib bo‘lmaydi.")
    return rows, options


def ad_markup(data, campaign_id=None, counts=None):
    rows, counts = [], counts or {}
    for row in data.get("url_buttons") or []:
        rows.append([InlineKeyboardButton(text=x["text"], url=x["url"]) for x in row])
    for row in data.get("like_rows") or []:
        buttons = []
        for item in row:
            i, label = item["index"], item["text"]
            buttons.append(InlineKeyboardButton(
                text=f"{label} ({counts.get(i, 0)})" if campaign_id else label,
                callback_data=f"advote:{campaign_id}:{i}" if campaign_id else "adpreview"))
        rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def broadcast_preview(target, state):
    msg = target.message if isinstance(target, types.CallbackQuery) else target
    d = await state.get_data()
    try:
        await msg.bot.edit_message_reply_markup(chat_id=d["source_chat"], message_id=d["source_message"],
                                                reply_markup=ad_markup(d))
    except Exception as e:
        if not is_not_modified(e):
            log.debug("Preview markup: %s", e)
    controls = [
        [InlineKeyboardButton(text="Tugmalarni o‘chirish" if d.get("url_buttons") else "Tugmalar qo‘shish",
                              callback_data="bcurls:remove" if d.get("url_buttons") else "bcurls:add")],
        [InlineKeyboardButton(text="Like tugmalarni o‘chirish" if d.get("like_rows") else "Like tugmalar qo‘shish",
                              callback_data="bclike:remove" if d.get("like_rows") else "bclike:add")],
        [InlineKeyboardButton(text="Reklama tayyor", callback_data="bcdone"),
         InlineKeyboardButton(text="Reklamani bekor qilish", callback_data="bccancel")]]
    await show_prompt(msg, state, "Reklama ko‘rinishi tayyor. Kerakli tugmalarni qo‘shing yoki reklama tayyor tugmasini bosing.",
                      InlineKeyboardMarkup(inline_keyboard=controls))


async def start_broadcast(m, state, db):
    await state.set_state(Broadcast.content)
    await show_prompt(m, state, "Jo‘natmoqchi bo‘lgan reklamangizni yuboring!\n\n"
                                "Reklama rasm + matn, video + matn, GIF, MP3 yoki faqat matn bo‘lishi mumkin.")


@router.message(Broadcast.content)
async def broadcast_content(m: types.Message, state: FSMContext):
    try:
        preview = await m.bot.copy_message(m.chat.id, m.chat.id, m.message_id)
    except Exception:
        return await m.answer("Bu xabarni reklama sifatida qabul qilib bo‘lmadi. Boshqa media yoki matn yuboring.")
    await delete_quietly(m)
    await state.update_data(source_chat=m.chat.id, source_message=preview.message_id,
                            url_buttons=[], like_rows=[], like_options=[])
    await broadcast_preview(m, state)


@router.callback_query(F.data == "adpreview")
async def ad_preview_click(c: types.CallbackQuery):
    await c.answer("Bu faqat ko‘rinish namunasi.")


@router.callback_query(F.data.startswith("bcurls:"))
async def broadcast_urls(c: types.CallbackQuery, state: FSMContext):
    if c.data.split(":")[1] == "remove":
        await state.update_data(url_buttons=[])
        await broadcast_preview(c, state)
        return await c.answer("URL tugmalar o‘chirildi.")
    await state.set_state(Broadcast.button_url)
    await show_prompt(c.message, state,
                      "Menga bitta xabarda URL-tugmalar ro‘yxatini yuboring. Iltimos, quyidagi formatga amal qiling:\n\n"
                      "Tugma 1 - http://example1.com\nTugma 2 - http://example2.com\n\n"
                      "Bitta qatorga uchtagacha tugma qo‘shish uchun | belgisidan foydalaning. Masalan:\n\n"
                      "Tugma 1 - http://example1.com | Tugma 2 - http://example2.com\n"
                      "Tugma 3 - http://example3.com | Tugma 4 - http://example4.com\n\n"
                      "Xabarlar qo‘shishga qaytish uchun \"Orqaga\" tugmasini bosing.",
                      kb.rows_kb([("Orqaga", "bcback")]))
    await c.answer()


@router.callback_query(F.data.startswith("bclike:"))
async def broadcast_likes(c: types.CallbackQuery, state: FSMContext):
    if c.data.split(":")[1] == "remove":
        await state.update_data(like_rows=[], like_options=[])
        await broadcast_preview(c, state)
        return await c.answer("Like tugmalar o‘chirildi.")
    await state.set_state(Broadcast.like_layout)
    await show_prompt(c.message, state,
                      "Iltimos like tugma ko‘rinishining kiriting!\nNamunalar:\n\n"
                      "Stickerli: 😀/😊|🥰/🤭\nMatnli: Ha/Yo‘q|Balkim\n\n"
                      "Tugmalarni yonma-yon chiqarish uchun / belgisidan foydalaning. Masalan: 😀/😁 — bitta qatorda 2 ta tugma.\n"
                      "Keyingi qatorga tushirish uchun | belgisidan foydalaning. Masalan: 😀/😁|🥰 — yuqorida 2 ta, pastda 1 ta tugma.\n"
                      "Shu tartibda xohlagancha qator va tugma qo‘shishingiz mumkin. Matnli tugmalarda ham xuddi shu qoida amal qiladi: Ha/Yo‘q|Balkim.",
                      kb.rows_kb([("Orqaga", "bcback")]))
    await c.answer()


@router.callback_query(F.data == "bcback")
async def broadcast_back(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.content)
    await broadcast_preview(c, state)
    await c.answer()


@router.message(Broadcast.button_url)
async def broadcast_button_url(m: types.Message, state: FSMContext):
    if (m.text or "").strip().lower() == "orqaga":
        await delete_quietly(m)
        await state.set_state(Broadcast.content)
        return await broadcast_preview(m, state)
    try:
        rows = parse_ad_buttons(m.text or "")
    except ValueError as e:
        return await m.answer(str(e))
    await state.update_data(url_buttons=rows)
    await delete_quietly(m)
    await state.set_state(Broadcast.content)
    await broadcast_preview(m, state)


@router.message(Broadcast.like_layout)
async def broadcast_like_layout(m: types.Message, state: FSMContext):
    raw = m.text or (m.sticker.emoji if m.sticker and m.sticker.emoji else ("👍" if m.sticker else ""))
    try:
        rows, options = parse_like_layout(raw)
    except ValueError as e:
        return await m.answer(str(e))
    await state.update_data(like_rows=rows, like_options=options)
    await delete_quietly(m)
    await state.set_state(Broadcast.content)
    await broadcast_preview(m, state)


@router.callback_query(F.data == "bcdone")
async def broadcast_done(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.audience)
    await show_prompt(c.message, state, "Auditoriyani tanlang!", kb.rows_kb([
        ("VIP foydalanuvchilarga", "ba:vip"), ("Oddiy foydalanuvchilarga", "ba:ordinary"),
        ("Maxsus kanalga", "ba:special"), ("Hammasiga", "ba:all"), ("Orqaga", "bcback")]))
    await c.answer()


@router.callback_query(F.data == "bccancel")
async def broadcast_cancel(c: types.CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if d.get("source_chat") and d.get("source_message"):
        await safe_call(lambda: c.bot.delete_message(d["source_chat"], d["source_message"]))
    await finish_prompt(c.message, state, "Reklama bekor qilindi.")
    await c.answer()


@router.callback_query(F.data.startswith("ba:"))
async def broadcast_prepare(c: types.CallbackQuery, state: FSMContext):
    mode = c.data.split(":")[1]
    if mode not in ("vip", "ordinary", "special", "all"):
        return await c.answer()
    await state.update_data(audience=mode)
    await show_prompt(c.message, state, "Reklama jo‘natishga tayyor. Jo‘natilsinmi?",
                      kb.confirm_kb("basend:yes", "basend:no"))
    await c.answer()


async def _run_broadcast(bot, ids, src_chat, src_msg, markup, report_chat, report_msg):
    ok, bad = await mass_send(ids, lambda uid: bot.copy_message(
        uid, src_chat, src_msg, reply_markup=markup, protect_content=True))
    await safe_call(lambda: bot.delete_message(src_chat, src_msg))
    await safe_call(lambda: bot.edit_message_text(
        f"Reklama tarqatish yakunlandi.\nJami: {len(ids)}\nYuborildi: {ok}\nYuborilmadi: {bad}",
        chat_id=report_chat, message_id=report_msg))


@router.callback_query(F.data.startswith("basend:"))
async def broadcast_send(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    d = await state.get_data()
    if c.data.endswith("no"):
        await state.set_state(Broadcast.content)
        await broadcast_preview(c, state)
        return await c.answer("Orqaga qaytdingiz.")
    if not d.get("source_message"):
        await state.clear()
        return await c.answer("Seans tugagan. Reklamani qaytadan boshlang.", show_alert=True)
    mode = d.get("audience", "all")
    src_chat, src_msg = d["source_chat"], d["source_message"]
    campaign_id = None
    if d.get("like_options"):
        campaign_id = await db.create_ad_campaign(src_chat, src_msg, d.get("url_buttons", []),
                                                  d["like_options"], d.get("like_rows", []))
    markup = ad_markup(d, campaign_id)
    if mode == "special":
        ch = await db.special_channel()
        if not ch:
            await finish_prompt(c.message, state, "Maxsus kanal sozlanmagan.")
            return await c.answer("Maxsus kanal sozlanmagan.", show_alert=True)
        await state.clear()
        try:
            await bot.copy_message(ch["channel_id"], src_chat, src_msg, reply_markup=markup, protect_content=True)
        except Exception as e:
            await c.message.edit_text(f"Yuborilmadi: {e}")
            return await c.answer()
        await safe_call(lambda: bot.delete_message(src_chat, src_msg))
        await c.message.edit_text("Reklama maxsus kanalga yuborildi.")
        return await c.answer()
    ids = await db.all_user_ids(mode)
    await state.clear()  # ikki marta bosilsa, ikki marta ketmasligi uchun
    await c.message.edit_text(f"Reklama tarqatilmoqda… Jami: {len(ids)}. Tugagach shu yerda natija chiqadi.")
    spawn(_run_broadcast(bot, ids, src_chat, src_msg, markup, c.message.chat.id, c.message.message_id))
    await c.answer()


# ===================================================================== GIFT
def gift_kind_kb():
    return kb.rows_kb([("Pul tarqatish", "giftkind:money"), ("VIP tarqatish", "giftkind:vip")])


async def start_gift(m, state, db):
    await state.set_state(Gift.gift_type)
    await show_prompt(m, state, "Gift turini tanlang:", gift_kind_kb())


@router.callback_query(F.data.startswith("giftkind:"))
async def gift_kind(c: types.CallbackQuery, state: FSMContext):
    kind = c.data.split(":")[1]
    if kind not in ("money", "vip"):
        return await c.answer()
    await state.update_data(gift_kind=kind)
    if kind == "vip":
        await state.set_state(Gift.tariff)
        await show_prompt(c.message, state, "VIP muddatini tanlang:", InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="1 kun", callback_data="giftdays:1"),
            InlineKeyboardButton(text="7 kun", callback_data="giftdays:7"),
            InlineKeyboardButton(text="30 kun", callback_data="giftdays:30")]]))
    else:
        await state.set_state(Gift.amount)
        await show_prompt(c.message, state, "Har bir g‘olib oladigan pul miqdorini yuboring (so‘m):")
    await c.answer()


@router.callback_query(F.data.startswith("giftdays:"))
async def gift_days(c: types.CallbackQuery, state: FSMContext):
    days = int(c.data.split(":")[1])
    if days not in (1, 7, 30):
        return await c.answer()
    await state.update_data(gift_days=days)
    await state.set_state(Gift.winners)
    await show_prompt(c.message, state, "Nechta g‘olib bo‘lishini yuboring:")
    await c.answer()


def _positive_int(text):
    try:
        n = int((text or "").strip().replace(" ", ""))
    except ValueError:
        return None
    return n if n > 0 else None


@router.message(Gift.amount)
async def gift_amount(m: types.Message, state: FSMContext):
    n = _positive_int(m.text)
    if not n:
        return await m.answer("Musbat summa kiriting.")
    await state.update_data(gift_amount=n)
    await state.set_state(Gift.winners)
    await delete_quietly(m)
    await show_prompt(m, state, "Nechta g‘olib bo‘lishini yuboring:")


@router.message(Gift.winners)
async def gift_winners_count(m: types.Message, state: FSMContext):
    n = _positive_int(m.text)
    if not n:
        return await m.answer("Musbat son kiriting.")
    await state.update_data(gift_winners=n)
    d = await state.get_data()
    await state.set_state(Gift.confirm)
    desc = f"{money(d.get('gift_amount', 0))} so‘m" if d.get("gift_kind") == "money" else f"{d.get('gift_days')} kunlik VIP"
    await delete_quietly(m)
    await show_prompt(m, state, f"Gift: {desc}\nG‘oliblar: {n} ta\nTasdiqlaysizmi?",
                      kb.confirm_kb("giftconfirm:yes", "giftconfirm:no"))


async def _run_gift(bot, ids, body, markup, report_chat, report_msg):
    ok, _ = await mass_send(ids, lambda uid: bot.send_message(uid, body, reply_markup=markup))
    await safe_call(lambda: bot.edit_message_text(
        f"Gift e’lon qilindi. Yetkazildi: {ok} ta foydalanuvchi.", chat_id=report_chat, message_id=report_msg))


@router.callback_query(F.data.startswith("giftconfirm:"))
async def gift_confirm(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    if c.data.endswith("no"):
        await state.clear()
        await state.update_data(prompt_id=c.message.message_id, prompt_chat_id=c.message.chat.id)
        await state.set_state(Gift.gift_type)
        await show_prompt(c.message, state, "Gift turini tanlang:", gift_kind_kb())
        return await c.answer("Gift sozlamalariga qaytdingiz.")
    d = await state.get_data()
    kind, winners = d.get("gift_kind"), d.get("gift_winners")
    if kind not in ("money", "vip") or not winners:
        await state.clear()
        return await c.answer("Seans tugagan. Giftni qaytadan boshlang.", show_alert=True)
    await state.clear()  # takroriy bosishdan himoya
    gid = await db.create_gift(kind, d.get("gift_amount", 0), d.get("gift_days", 0), winners)
    if kind == "money":
        body = (f"Adminlar obunachilar uchun tekinga {money(d['gift_amount'])} so‘m pul sovg‘a qilishmoqda. Shoshiling! "
                f"Sovg‘a faqatgina {winners} odamga nasib qiladi, omadingizni qo‘ldan chiqarmang!")
    else:
        body = f"{d['gift_days']} kunlik VIP sovg‘a! Sovg‘a faqat {winners} nafar oddiy foydalanuvchiga beriladi. Shoshiling!"
    markup = kb.rows_kb([("Sovg‘ani olish", f"claimgift:{gid}")])
    ids = await db.all_user_ids("ordinary" if kind == "vip" else "all")
    await c.message.edit_text(f"Gift e’lon qilinmoqda… Jami: {len(ids)}. Tugagach shu yerda natija chiqadi.")
    spawn(_run_gift(bot, ids, body, markup, c.message.chat.id, c.message.message_id))
    await c.answer()
