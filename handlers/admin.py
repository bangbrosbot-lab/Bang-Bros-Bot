"""Admin paneli: menyu, video, sozlamalar, kanallar, to‘lovlar, foydalanuvchilar va adminlar."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import keyboards as kb
from access import invalidate_sub_cache
from backup import send_backup
from config import ADMIN_ID, CHANNEL_URL
from db import Database
from handlers import ads
from handlers.filters import PERMISSIONS, AdminOnly, has_permission, no_perm_text
from states import AddVideo, DeleteVideo, Settings, UserAdmin
from timeutil import fmt_local
from utils import (delete_quietly, esc, finish_prompt, is_not_modified, money,
                   safe_call, show_prompt, username_text)

log = logging.getLogger(__name__)

router = Router()
menu_router = Router()  # menyu tugmalari: boshqa barcha handlerlardan OLDIN tekshiriladi
for _r in (router, menu_router):
    _r.message.filter(AdminOnly())
    _r.callback_query.filter(AdminOnly())

DENIED = "Bu bo‘limdan foydalanish huquqingiz yo‘q."
ALREADY = "Bu so‘rov avval ko‘rib chiqilgan."


async def require(event, db: Database, permission: str, alert: bool = False) -> bool:
    if has_permission(db, event.from_user.id, permission):
        return True
    if alert:
        await event.answer(no_perm_text(permission), show_alert=True)
    else:
        await event.answer(no_perm_text(permission))
    return False


def admin_level(perms) -> str:
    n = len(perms or [])
    return "Oddiy admin" if n == 0 else ("Full admin" if n == len(PERMISSIONS) else "O‘rta admin")


# ===================================================================== MENYU
async def open_desk(m, state, db):
    await m.edit_text("Ish stoli", reply_markup=kb.desk())


async def open_settings(m, state, db):
    await m.edit_text("Sozlamalar", reply_markup=kb.settings())


async def back_home(m, state, db):
    await m.edit_text("Admin panel", reply_markup=kb.admin_menu())


async def show_stats(m, state, db):
    s = await db.stats()
    await m.edit_text(f"Jami Foydalanuvchilar: {s['users']}\nBugun qo‘shilganlar: {s['today']}\n"
                   f"Vip Foydalanuvchilar: {s['vip']}\nReferral orqali kelganlar: {s['ref']}\n"
                   f"Jami tushgan mablag‘: {money(s['money'])} so‘m\nJami qo‘shilgan videolar: {s['videos']}")


def channels_kb():
    return kb.rows_kb([("Majburiy kanal qo‘shish", "add_mand"), ("Maxsus kanal qo‘shish", "add_special"),
                       ("Kanal o‘chirish", "del_channel")])


async def open_channels(m, state, db):
    await m.edit_text("Kanallar bo‘limidasiz.", reply_markup=channels_kb())


async def open_users(m, state, db):
    if not await require(m, db, "users"):
        return
    await state.set_state(UserAdmin.user_id)
    await show_prompt(m, state, "Boshqarish uchun foydalanuvchi ID sini yuboring:")


async def edit_card(m, state, db):
    if not await require(m, db, "edit"):
        return
    await state.set_state(Settings.card)
    await show_prompt(m, state, f"Hozirgi karta: {await db.setting('card')}\nYangi karta raqamini yuboring!")


async def vip_tariff_markup(db):
    rows = [(f"{label}: {money(int(await db.setting(f'vip_{d}')))} so‘m", f"vipprice:{d}")
            for d, label in [(1, "1 kunlik"), (7, "1 haftalik"), (30, "1 oylik")]]
    return kb.rows_kb(rows)


async def edit_vip(m, state, db):
    if not await require(m, db, "edit"):
        return
    await m.edit_text("O‘zgartirmoqchi bo‘lgan VIP tarifini tanlang:", reply_markup=await vip_tariff_markup(db))


async def edit_info(m, state, db):
    if not await require(m, db, "edit"):
        return
    await state.set_state(Settings.info)
    await show_prompt(m, state, f"Hozirgi ma’lumot:\n{await db.setting('bot_info')}\n\nRasm va matn yoki video va matn yuboring!")


async def edit_referral(m, state, db):
    if not await require(m, db, "edit"):
        return
    await state.set_state(Settings.referral)
    await show_prompt(m, state, f"Hozirgi referral bonusi: {await db.setting('referral_bonus')} so‘m. Yangi miqdorni yuboring!")


async def edit_admin_link(m, state, db):
    if not await require(m, db, "edit"):
        return
    await state.set_state(Settings.admin_link)
    await show_prompt(m, state, f"Hozirgi admin havolasi: {await db.setting('admin_link')}\nYangisini yuboring!")


async def start_add_video(m, state, db):
    await state.set_state(AddVideo.cover)
    await show_prompt(m, state, "Post uchun rasm jo‘nating!")


async def start_delete_video(m, state, db):
    await state.set_state(DeleteVideo.link)
    await show_prompt(m, state, "O‘chirmoqchi bo‘lgan videoning havolasini yuboring!")


MENU_ACTIONS = {
    "Ish stoli": open_desk, "Sozlamalar": open_settings, "Bosh menyu": back_home, "Statistika": show_stats,
    "Kanallar": open_channels, "Foydalanuvchilar": open_users,
    "Karta edit": edit_card, "VIP edit": edit_vip, "Info edit": edit_info,
    "Referral edit": edit_referral, "Admin link edit": edit_admin_link,
    "Video qo‘shish": start_add_video, "Video o‘chirish": start_delete_video,
    "Reklama jo‘natish": ads.start_broadcast, "Gift o‘tkazish": ads.start_gift,
}


@menu_router.callback_query(F.data.startswith("amenu:"))
async def on_menu(c: types.CallbackQuery, state: FSMContext, db: Database):
    """Inline menyu: eski jarayonni to‘xtatib, bitta boshqaruv xabarida yangi bo‘limni ochadi."""
    if c.from_user.id != ADMIN_ID and not db.is_admin(c.from_user.id):
        return await c.answer(DENIED, show_alert=True)
    key = c.data.split(":", 1)[1]
    actions = {
        "desk": open_desk, "settings": open_settings, "home": back_home, "stats": show_stats,
        "channels": open_channels, "users": open_users, "card": edit_card, "vip": edit_vip,
        "info": edit_info, "referral": edit_referral, "adminlink": edit_admin_link,
        "addvideo": start_add_video, "delvideo": start_delete_video,
        "broadcast": ads.start_broadcast, "gift": ads.start_gift,
    }
    action = actions.get(key)
    if not action:
        return await c.answer()
    if key == "channels" and c.from_user.id != ADMIN_ID:
        return await c.answer(DENIED, show_alert=True)
    await state.clear()
    await state.update_data(prompt_id=c.message.message_id, prompt_chat_id=c.message.chat.id)
    await c.answer()
    await action(c.message, state, db)


# ===================================================================== /data, /id
@router.message(Command("data"))
async def data_cmd(m: types.Message, bot: Bot, db: Database):
    if m.from_user.id != ADMIN_ID:
        return
    await send_backup(bot, db, m.chat.id)


async def send_id_page(target, db, page, edit=False):
    total = await db.total_users()
    pages = max(1, (total + 4) // 5)
    page = max(1, min(page, pages))
    lines, rows = ["Barcha foydalanuvchilar ro‘yxati", f"Jami: {total}", ""], []
    for u in await db.users_page(page, 5):
        lines += [f"Ism: {esc(u['name']) or 'Mavjud emas'}",
                  f"User: {esc(username_text(u['username']))}",
                  f"ID: <code>{u['user_id']}</code>", ""]
        rows.append([InlineKeyboardButton(text=f"{u['name'] or u['user_id']} · {u['user_id']}",
                                          callback_data=f"uid:{u['user_id']}")])
    rows.extend(kb.id_kb(page, pages).inline_keyboard)
    text, markup = "\n".join(lines).rstrip(), InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        try:
            await target.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            if not is_not_modified(e):
                raise
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup, protect_content=True)


@router.message(Command("id"))
async def id_cmd(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "users"):
        return
    await state.clear()
    await send_id_page(m, db, 1)


@router.callback_query(F.data.startswith("idpage:"))
async def id_page(c: types.CallbackQuery, db: Database):
    if not await require(c, db, "users", alert=True):
        return
    await send_id_page(c.message, db, int(c.data.split(":")[1]), True)
    await c.answer()


@router.callback_query(F.data == "idhome")
async def id_home(c: types.CallbackQuery, db: Database):
    if not await require(c, db, "users", alert=True):
        return
    await c.message.edit_text("Admin panel", reply_markup=kb.admin_menu())
    await c.answer()


@router.callback_query(F.data.startswith("uid:"))
async def id_user_profile(c: types.CallbackQuery, db: Database):
    if not await require(c, db, "users", alert=True):
        return
    u = await db.user(int(c.data.split(":")[1]))
    if not u:
        return await c.answer("Foydalanuvchi topilmadi.", show_alert=True)
    await show_user(c.message, db, u, actor_id=c.from_user.id)
    await c.answer()


# ===================================================================== VIDEO QO‘SHISH
QUALITIES = ("360p", "480p", "720p", "1080p")


def quality_kb(remaining, with_done=False):
    rows = [[InlineKeyboardButton(text=q, callback_data=f"addq:{q}") for q in remaining[i:i + 2]]
            for i in range(0, len(remaining), 2)]
    if with_done:
        rows.append([InlineKeyboardButton(text="Bo‘ldi", callback_data="addq:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(AddVideo.cover, F.photo)
async def add_cover(m: types.Message, state: FSMContext):
    await state.update_data(cover=m.photo[-1].file_id)
    await state.set_state(AddVideo.caption)
    await delete_quietly(m)
    await show_prompt(m, state, "Izoh yozing!")


@router.message(AddVideo.cover)
async def add_cover_wrong(m: types.Message):
    await m.answer("Iltimos, post uchun rasm yuboring!")


@router.message(AddVideo.caption)
async def add_caption(m: types.Message, state: FSMContext):
    text = m.text or m.caption
    if not text:
        return await m.answer("Izohni matn ko‘rinishida yuboring!")
    if len(text) > 900:
        return await m.answer("Izoh 900 belgidan oshmasligi kerak. Qisqaroq izoh yuboring!")
    await state.update_data(caption=text)
    await state.set_state(AddVideo.teaser)
    await delete_quietly(m)
    await show_prompt(m, state, "Qisqa videoni jo‘nating!")


@router.message(AddVideo.teaser, F.video)
async def add_teaser(m: types.Message, state: FSMContext):
    await state.update_data(teaser=m.video.file_id, qualities={})
    await state.set_state(AddVideo.quality)
    await delete_quietly(m)
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=q, callback_data=f"addq:{q}") for q in ("360p", "480p")],
        [InlineKeyboardButton(text=q, callback_data=f"addq:{q}") for q in ("720p", "1080p")]])
    await show_prompt(m, state, "Birinchi sifatni tanlang:", kbd)


@router.message(AddVideo.teaser, ~F.video)
@router.message(AddVideo.quality_file, ~F.video)
async def add_video_wrong(m: types.Message):
    await m.answer("Iltimos, videoni fayl emas, oddiy video ko‘rinishida yuboring!")


@router.callback_query(F.data.startswith("addq:") & (F.data != "addq:done"))
async def choose_q(c: types.CallbackQuery, state: FSMContext):
    q = c.data.split(":", 1)[1]
    if q not in QUALITIES:
        return await c.answer()
    await state.update_data(current_quality=q)
    await state.set_state(AddVideo.quality_file)
    await show_prompt(c.message, state, f"Endi shu sifatdagi ({q}) videoni jo‘nating!", kb.back_kb("addqback"))
    await c.answer()


@router.callback_query(F.data == "addqback")
async def choose_q_back(c: types.CallbackQuery, state: FSMContext):
    qs = (await state.get_data()).get("qualities", {})
    await state.set_state(AddVideo.quality)
    await show_prompt(c.message, state,
                      "Video qabul qilindi, yana boshqa sifat qo‘shasizmi?" if qs else "Birinchi sifatni tanlang:",
                      quality_kb([q for q in QUALITIES if q not in qs], with_done=bool(qs)))
    await c.answer()


@router.message(AddVideo.quality_file, F.video)
async def quality_file(m: types.Message, state: FSMContext):
    d = await state.get_data()
    qs = d.get("qualities", {})
    qs[d["current_quality"]] = m.video.file_id
    await state.update_data(qualities=qs)
    await state.set_state(AddVideo.quality)
    await delete_quietly(m)
    await show_prompt(m, state, "Video qabul qilindi, yana boshqa sifat qo‘shasizmi?",
                      quality_kb([q for q in QUALITIES if q not in qs], with_done=True))


@router.callback_query(F.data == "addq:done")
async def add_done(c: types.CallbackQuery, state: FSMContext):
    if not (await state.get_data()).get("qualities"):
        return await c.answer("Kamida bitta sifat qo‘shing.", show_alert=True)
    await state.set_state(AddVideo.finish)
    await show_prompt(c.message, state, "Barcha sifatlar muvaffaqiyatli qo‘shildi. Hammasi tayyormi?",
                      kb.confirm_kb("video_save", "video_cancel"))
    await c.answer()


@router.callback_query(F.data == "video_cancel")
async def video_cancel(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(prompt_id=c.message.message_id, prompt_chat_id=c.message.chat.id)
    await state.set_state(AddVideo.cover)
    await c.message.edit_text("Yangi video qo‘shish boshlandi. Post uchun rasm jo‘nating!")
    await c.answer()


@router.callback_query(F.data == "video_save")
async def video_save(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    d = await state.get_data()
    if not (d.get("cover") and d.get("qualities") and d.get("teaser")):
        return await c.answer("Seans tugagan. «Video qo‘shish» orqali qaytadan boshlang.", show_alert=True)
    special = await db.special_channel()
    if not special:
        return await c.answer("Avval maxsus kanal qo‘shing.", show_alert=True)
    await state.clear()  # ikki marta bosilsa, ikkita post chiqmasligi uchun
    channel = special["channel_id"]
    me = await bot.me()
    vid = await db.create_video(d["cover"], d["caption"], d["teaser"], channel, d["qualities"])
    caption = (f"{esc(d['caption'])}\n\nYoqimli tomosha tilaymiz! Kanalimizdan uzoqlashmang: "
               f'<a href="{esc(CHANNEL_URL)}">Bang Bros</a>')
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yoqdi (0)", callback_data=f"vote:{vid}:1"),
         InlineKeyboardButton(text="Yoqmadi (0)", callback_data=f"vote:{vid}:-1")],
        [InlineKeyboardButton(text="Videoni ko‘rish", url=f"https://t.me/{me.username}?start=video_{vid}")]])
    try:
        post = await bot.send_photo(channel, d["cover"], caption=caption, parse_mode="HTML",
                                    reply_markup=markup, protect_content=True)
    except Exception as e:
        await db.delete_video(vid)
        await state.set_data(d)  # admin qayta urinib ko‘ra olishi uchun
        await state.set_state(AddVideo.finish)
        return await c.answer(f"Kanalga post yuborilmadi: {e}", show_alert=True)
    await db.set_channel_message(vid, post.message_id)
    await c.message.edit_text("Video muvaffaqiyatli qo‘shildi.", reply_markup=kb.desk())
    await c.answer()


# ===================================================================== VIDEO O‘CHIRISH
@router.message(DeleteVideo.link)
async def delete_link(m: types.Message, state: FSMContext, db: Database):
    text = m.text or ""
    vid = None
    match = re.search(r"start=video_(\d+)", text)
    if match:
        vid = int(match.group(1))
    else:
        post_match = re.search(r"t\.me/(?:c/\d+|[A-Za-z0-9_]+)/(\d+)", text)
        if post_match:  # kanal posti havolasi oxiridagi raqam — xabar ID si, video ID emas
            found = await db.video_by_message(int(post_match.group(1)))
            vid = found["id"] if found else None
        elif text.strip().isdigit():
            vid = int(text.strip())
    await delete_quietly(m)
    if not vid:
        return await finish_prompt(m, state, "Video havolasi noto‘g‘ri yoki bu post bazadan topilmadi. "
                                             "Video o‘chirish bekor qilindi.")
    if not await db.video(vid):
        return await finish_prompt(m, state, "Video topilmadi.")
    await state.update_data(delete_vid=vid)
    await state.set_state(DeleteVideo.confirm)
    await show_prompt(m, state, f"Video №{vid} butunlay o‘chiriladi (kanaldagi post ham). Tasdiqlaysizmi?",
                      kb.confirm_kb("delvid:yes", "delvid:no"))


@router.callback_query(F.data.startswith("delvid:"))
async def delete_confirm(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    d = await state.get_data()
    vid = d.get("delete_vid")
    if c.data.endswith("no") or not vid:
        await finish_prompt(c.message, state, "Video o‘chirish bekor qilindi.")
        return await c.answer()
    v = await db.video(vid)
    if v and v["channel_id"] and v["channel_message_id"]:
        await safe_call(lambda: bot.delete_message(v["channel_id"], v["channel_message_id"]))
    await db.delete_video(vid)
    await finish_prompt(c.message, state, "Video o‘chirildi.")
    await c.answer()


# ===================================================================== SOZLAMALAR
@router.message(Settings.card)
async def card_save(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "edit"):
        return
    if not m.text:
        return await m.answer("Karta raqamini matn ko‘rinishida yuboring!")
    await db.set_setting("card", m.text.strip())
    await delete_quietly(m)
    await finish_prompt(m, state, "Karta raqami yangilandi.")


@router.message(Settings.info)
async def info_save(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "edit"):
        return
    if m.photo or m.video:
        await db.set_setting("info_type", "photo" if m.photo else "video")
        await db.set_setting("info_file_id", m.photo[-1].file_id if m.photo else m.video.file_id)
        await db.set_setting("info_caption", m.caption or "")
    elif m.text:
        await db.set_setting("info_type", "text")
        await db.set_setting("info_file_id", "")
        await db.set_setting("info_caption", m.text)
        await db.set_setting("bot_info", m.text)
    else:
        return await m.answer("Rasm va matn yoki video va matn yuboring.")
    await delete_quietly(m)
    await finish_prompt(m, state, "Bot ma’lumoti yangilandi.")


@router.message(Settings.referral)
async def ref_save(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "edit"):
        return
    try:
        n = int((m.text or "").strip())
    except ValueError:
        return await m.answer("Faqat raqam yuboring.")
    if n < 0:
        return await m.answer("Bonus manfiy bo‘lishi mumkin emas.")
    await db.set_setting("referral_bonus", n)
    await delete_quietly(m)
    await finish_prompt(m, state, "Referral bonusi yangilandi.")


@router.message(Settings.admin_link)
async def link_save(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "edit"):
        return
    if not m.text:
        return await m.answer("Havolani matn ko‘rinishida yuboring!")
    await db.set_setting("admin_link", m.text.strip())
    await delete_quietly(m)
    await finish_prompt(m, state, "Admin havolasi yangilandi.")


@router.callback_query(F.data.startswith("vipprice:"))
async def vipprice_choose(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "edit", alert=True):
        return
    days = int(c.data.split(":")[1])
    if days not in (1, 7, 30):
        return await c.answer()
    await state.clear()
    await state.update_data(vip_days=days, prompt_id=c.message.message_id, prompt_chat_id=c.message.chat.id)
    await state.set_state(Settings.vip_price)
    await show_prompt(c.message, state, "Yangi narxni so‘mda yuboring:", kb.back_kb("vipback"))
    await c.answer()


@router.callback_query(F.data == "vipback")
async def vipprice_back(c: types.CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    await c.message.edit_text("O‘zgartirmoqchi bo‘lgan VIP tarifini tanlang:", reply_markup=await vip_tariff_markup(db))
    await c.answer()


@router.message(Settings.vip_price)
async def vipprice_save(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "edit"):
        return
    try:
        n = int((m.text or "").strip().replace(" ", ""))
        if n <= 0:
            raise ValueError
    except ValueError:
        return await m.answer("Narxni musbat raqam bilan yuboring.")
    days = (await state.get_data()).get("vip_days")
    if days not in (1, 7, 30):
        await state.clear()
        return await m.answer("Seans tugagan. «VIP edit» orqali qaytadan boshlang.")
    await db.set_setting(f"vip_{days}", n)
    await delete_quietly(m)
    await finish_prompt(m, state, "VIP tarifi yangilandi.")


# ===================================================================== KANALLAR (faqat bosh admin)
async def _main_only(c: types.CallbackQuery) -> bool:
    if c.from_user.id != ADMIN_ID:
        await c.answer(DENIED, show_alert=True)
        return False
    return True


@router.callback_query(F.data == "add_mand")
async def add_mand(c: types.CallbackQuery, state: FSMContext):
    if not await _main_only(c):
        return
    await state.clear()
    await state.update_data(prompt_id=c.message.message_id, prompt_chat_id=c.message.chat.id)
    await state.set_state(Settings.mandatory_channel)
    await show_prompt(c.message, state, "Kanal ID sini va qo‘shilish havolasini quyidagi ko‘rinishda yuboring:\n"
                                        "ID | https://t.me/...\nMaxfiy kanal uchun invite link yuboring.",
                      kb.back_kb("chback"))
    await c.answer()


@router.message(Settings.mandatory_channel)
async def mand_save(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        raw_id, url = (m.text or "").split("|", 1)
        cid, url = int(raw_id.strip()), url.strip()
        if not url.startswith(("https://", "http://", "tg://")):
            raise ValueError
    except ValueError:
        return await m.answer("Format noto‘g‘ri. ID | havola ko‘rinishida yuboring.")
    try:
        chat = await bot.get_chat(cid)
        me = await bot.me()
        member = await bot.get_chat_member(cid, me.id)
    except Exception:
        return await m.answer("Kanal topilmadi yoki bot unga qo‘shilmagan. ID ni tekshiring va botni kanalga admin qiling.")
    if member.status not in ("administrator", "creator"):
        return await m.answer("Bot bu kanalda admin emas. Aks holda obunani tekshira olmaydi — avval botni admin qiling.")
    await db.add_channel(cid, "mandatory", url, chat.title or chat.username or str(cid))
    invalidate_sub_cache()
    await delete_quietly(m)
    await finish_prompt(m, state, "Majburiy kanal qo‘shildi.")


@router.callback_query(F.data == "add_special")
async def special_start(c: types.CallbackQuery, state: FSMContext):
    if not await _main_only(c):
        return
    await state.clear()
    await state.update_data(prompt_id=c.message.message_id, prompt_chat_id=c.message.chat.id)
    await state.set_state(Settings.special_channel)
    await show_prompt(c.message, state, "Botni kanalga admin qilib tayinlang va kanal ID sini jo‘nating!",
                      kb.back_kb("chback"))
    await c.answer()


@router.callback_query(F.data == "chback")
async def channels_back(c: types.CallbackQuery, state: FSMContext):
    if not await _main_only(c):
        return
    await state.clear()
    await c.message.edit_text("Kanallar bo‘limidasiz.", reply_markup=channels_kb())
    await c.answer()


@router.message(Settings.special_channel)
async def special_save(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        cid = int((m.text or "").strip())
        chat = await bot.get_chat(cid)
        me = await bot.me()
        member = await bot.get_chat_member(cid, me.id)
    except Exception:
        return await m.answer("Kanal ID sini tekshiring va botga admin huquqini bering.")
    if member.status != "administrator":
        return await m.answer("Bot kanalda admin emas. Avval admin qiling.")
    url = f"https://t.me/{chat.username}" if chat.username else None
    if not url:
        try:
            url = (await bot.create_chat_invite_link(cid)).invite_link
        except Exception:
            pass
    await db.set_special_channel(cid, url, chat.title or chat.username or str(cid))
    await delete_quietly(m)
    await finish_prompt(m, state, "Maxsus kanal qo‘shildi.")


@router.callback_query(F.data == "del_channel")
async def del_channels(c: types.CallbackQuery, db: Database, bot: Bot):
    if not await _main_only(c):
        return
    rows = []
    for x in await db.all_channels():
        title = x["title"]
        if not title:
            try:
                chat = await bot.get_chat(x["channel_id"])
                title = chat.title or chat.username or str(x["channel_id"])
                await db.add_channel(x["channel_id"], x["kind"], x["join_url"], title)
            except Exception:
                title = str(x["channel_id"])
        rows.append((title, f"delch:{x['channel_id']}"))
    if not rows:
        return await c.answer("Kanallar ro‘yxati bo‘sh.", show_alert=True)
    await c.message.edit_text("O‘chirish uchun kanalni tanlang:", reply_markup=kb.rows_kb(rows + [("Orqaga", "chback")]))
    await c.answer()


@router.callback_query(F.data.startswith("delch:"))
async def del_channel_ask(c: types.CallbackQuery):
    if not await _main_only(c):
        return
    cid = int(c.data.split(":")[1])
    await c.message.edit_text(f"{cid} kanalini o‘chirishni xohlaysizmi?",
                              reply_markup=kb.confirm_kb(f"delchyes:{cid}", "delchno"))
    await c.answer()


@router.callback_query(F.data.startswith("delchyes:"))
async def del_channel_yes(c: types.CallbackQuery, db: Database):
    if not await _main_only(c):
        return
    await db.delete_channel(int(c.data.split(":")[1]))
    invalidate_sub_cache()
    await c.message.edit_text("Kanal o‘chirildi.")
    await c.answer("Kanal o‘chirildi.")


@router.callback_query(F.data == "delchno")
async def del_channel_no(c: types.CallbackQuery):
    await c.message.edit_text("Kanallar bo‘limidasiz.", reply_markup=channels_kb())
    await c.answer("Kanal o‘chirish bekor qilindi.")


# ===================================================================== TO‘LOVLAR
async def _close_receipt(bot, chat_id, message_id, caption, status):
    """Chek xabaridan tugmalarni olib, holatini yozib qo‘yadi (xabarning o‘zi saqlanadi)."""
    await safe_call(lambda: bot.edit_message_caption(
        chat_id=chat_id, message_id=message_id, caption=f"{caption or ''}\n\n{status}", reply_markup=None))


@router.callback_query(F.data.startswith("topupok:"))
async def topup_approve(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    if not await require(c, db, "payments", alert=True):
        return
    await state.clear()
    r = await db.approve_topup(int(c.data.split(":")[1]))
    if not r:
        return await c.answer(ALREADY, show_alert=True)
    await safe_call(lambda: bot.send_message(
        r["user_id"], f"To‘lov cheki tasdiqlandi, Hisobingiz {money(r['amount'])} so‘mga to‘ldirildi."))
    await _close_receipt(bot, c.message.chat.id, c.message.message_id, c.message.caption,
                         f"✅ Tasdiqlandi ({c.from_user.full_name})")
    await c.answer("To‘lov tasdiqlandi.")


@router.callback_query(F.data.startswith("topupno:"))
async def topup_reject(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "payments", alert=True):
        return
    rid = int(c.data.split(":")[1])
    if not await db.pending_topup(rid):
        return await c.answer(ALREADY, show_alert=True)
    await state.clear()
    prompt = await c.message.answer("Rad etish sababini yozing!",
                                    reply_markup=kb.rows_kb([("Bekor qilish", "topupcancel")]))
    await state.update_data(reject_topup_id=rid, reject_chat=c.message.chat.id, reject_msg=c.message.message_id,
                            reject_caption=c.message.caption, prompt_id=prompt.message_id,
                            prompt_chat_id=prompt.chat.id)
    await state.set_state(UserAdmin.reject_reason)
    await c.answer()


@router.callback_query(F.data == "topupcancel")
async def topup_reject_cancel(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await delete_quietly(c.message)
    await c.answer("Bekor qilindi. Chek hali ham kutilmoqda.")


@router.message(UserAdmin.reject_reason)
async def topup_reject_reason(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    if not await require(m, db, "payments"):
        return await state.clear()
    reason = (m.text or "").strip()
    if not reason:
        return await m.answer("Rad etish sababini matn ko‘rinishida yozing!")
    d = await state.get_data()
    r = await db.reject_topup(d.get("reject_topup_id"), reason)
    if not r:
        await state.clear()
        return await m.answer(ALREADY)
    await safe_call(lambda: bot.send_message(
        r["user_id"], f"To‘lovingiz rad etildi.\nHisobingizga pul qo‘shilmadi.\nSababi: {reason}"))
    await _close_receipt(bot, d["reject_chat"], d["reject_msg"], d.get("reject_caption"),
                         f"❌ Rad etildi ({m.from_user.full_name}): {reason}")
    await finish_prompt(m, state, "To‘lov rad qilindi.\nSababi foydalanuvchiga yetkazildi.")


# ===================================================================== FOYDALANUVCHILAR
@router.message(UserAdmin.user_id)
async def user_lookup(m: types.Message, state: FSMContext, db: Database):
    if not await require(m, db, "users"):
        return await state.clear()
    try:
        uid = int((m.text or "").strip())
    except ValueError:
        return await m.answer("ID faqat raqamlardan iborat bo‘lishi kerak.")
    u = await db.user(uid)
    if not u:
        return await m.answer("Foydalanuvchi topilmadi.")
    prompt_data = await state.get_data()
    await delete_quietly(m)
    await state.clear()
    await show_user(m, db, u, actor_id=m.from_user.id, prompt_data=prompt_data)


async def show_user(target, db, u, edit=False, actor_id=None, prompt_data=None):
    uid = u["user_id"]
    vip, friends = await db.vip(uid), await db.referrals_count(uid)
    perms = db.admin_permissions(uid)
    is_admin = perms is not None
    if uid == ADMIN_ID:
        extra = "Holati: Bosh admin"
    elif is_admin:
        extra = f"Holati: {admin_level(perms)}"
    elif vip:
        extra = f"Holati: Vip obunachi\nMuddati: {fmt_local(u['vip_until'])}"
    else:
        extra = "Holati: Oddiy obunachi"
    username = username_text(u["username"])
    balance = int(u["balance"] or 0) + int(u["referral_balance"] or 0)
    text = (f"Foydalanuvchi ma’lumotlari\n\nIsm: {u['name'] or 'Mavjud emas'}\nUsername: {username}\nID: {uid}\n"
            f"Balans: {money(balance)} so‘m\n{extra}\nDo‘stlar: {friends}\n"
            f"Bloklangan: {'Ha' if u['blocked'] else 'Yo‘q'}")
    cb = lambda t, d: InlineKeyboardButton(text=t, callback_data=d)  # noqa: E731
    rows = [[cb("Balans qo‘shish", f"uadd:{uid}"), cb("Balans ayirish", f"usub:{uid}")]]
    if vip:
        rows.append([cb("VIP bekor qilish", f"urevoke:{uid}")])
    elif not is_admin:
        rows.append([cb("VIP berish", f"uvip:{uid}")])
    if uid != ADMIN_ID:
        rows.append([cb("Blokdan olish" if u["blocked"] else "Blocklash", f"ublock:{uid}")])
        actor_id = actor_id or getattr(getattr(target, "from_user", None), "id", 0)
        if has_permission(db, actor_id, "admin_manage"):
            rows.append([cb("Adminlikdan olish", f"uremoveadmin:{uid}") if is_admin
                         else cb("Admin qilish", f"uadmin:{uid}")])
    rows.append([cb("Xabar yuborish", f"umsg:{uid}")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        if prompt_data and prompt_data.get("prompt_id"):
            await target.bot.edit_message_text(
                text, chat_id=prompt_data.get("prompt_chat_id", target.chat.id),
                message_id=prompt_data["prompt_id"], reply_markup=markup)
        elif edit:
            await target.edit_text(text, reply_markup=markup)
        else:
            await target.answer(text, reply_markup=markup)
    except Exception as e:
        if not is_not_modified(e):
            raise


@router.callback_query(F.data.regexp(r"^u(add|sub|vip|msg|block|revoke):"))
async def user_action(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "users", alert=True):
        return
    await state.clear()
    key, uid_raw = c.data.split(":", 1)
    action, uid = key[1:], int(uid_raw)
    await state.update_data(target_uid=uid, action=action, prompt_id=c.message.message_id,
                            prompt_chat_id=c.message.chat.id)
    if action == "revoke":
        await db.revoke_vip(uid)
        await safe_call(lambda: c.bot.send_message(uid, "VIP obunangiz administrator tomonidan bekor qilindi."))
        await c.answer("VIP bekor qilindi.")
        return await show_user(c.message, db, await db.user(uid), True, c.from_user.id)
    if action == "block":
        if uid == ADMIN_ID:
            return await c.answer("Bosh adminni bloklab bo‘lmaydi.", show_alert=True)
        u = await db.user(uid)
        verb = "blockdan chiqarmoqchimisiz?" if u["blocked"] else "blocklamoqchimisiz?"
        return await c.message.edit_text(f"Rostdan ham shu foydalanuvchini {verb}",
                                         reply_markup=kb.confirm_kb(f"ublockconfirm:{uid}:yes", f"ublockconfirm:{uid}:no"))
    if action == "vip":
        await state.set_state(UserAdmin.add_amount)
        rows = [(label, f"uvipdays:{uid}:{days}") for days, label in
                [(1, "1 kunlik VIP"), (7, "1 haftalik VIP"), (30, "1 oylik VIP")]]
        await show_prompt(c.message, state, "Beriladigan VIP muddatini tanlang:",
                          kb.rows_kb(rows + [("Orqaga", f"uback:{uid}")]))
        return await c.answer()
    prompts = {"add": "Qo‘shiladigan summani yuboring:", "sub": "Ayiriladigan summani yuboring:",
               "msg": "Foydalanuvchiga yuboriladigan xabarni jo‘nating:"}
    await state.set_state(UserAdmin.add_amount if action in ("add", "sub") else UserAdmin.message)
    await show_prompt(c.message, state, prompts[action], kb.back_kb(f"uback:{uid}"))
    await c.answer()


@router.callback_query(F.data.startswith("uvipdays:"))
async def user_vip_days(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    if not await require(c, db, "users", alert=True):
        return
    _, raw_uid, raw_days = c.data.split(":")
    uid, days = int(raw_uid), int(raw_days)
    if days not in (1, 7, 30):
        return await c.answer("Noto‘g‘ri tarif.", show_alert=True)
    u = await db.user(uid)
    if not u:
        return await c.answer("Foydalanuvchi topilmadi.", show_alert=True)
    expiry = await db.set_vip(uid, days)
    await safe_call(lambda: bot.send_message(
        uid, f"Sizga {days} kunlik VIP obuna berildi. Amal qilish muddati: {fmt_local(expiry)}"))
    await state.clear()
    await c.message.edit_text(f"Foydalanuvchiga {days} kunlik VIP berildi.")
    await show_user(c.message, db, await db.user(uid), True, c.from_user.id)
    await c.answer("VIP berildi.")


@router.callback_query(F.data.startswith("uback:"))
async def user_back(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "users", alert=True):
        return
    await state.clear()
    u = await db.user(int(c.data.split(":")[1]))
    if not u:
        return await c.answer("Foydalanuvchi topilmadi.", show_alert=True)
    await show_user(c.message, db, u, True, c.from_user.id)
    await c.answer()


@router.callback_query(F.data.startswith("ublockconfirm:"))
async def user_block_confirm(c: types.CallbackQuery, db: Database, bot: Bot):
    if not await require(c, db, "users", alert=True):
        return
    _, raw_uid, answer = c.data.split(":")
    uid = int(raw_uid)
    u = await db.user(uid)
    if not u:
        return await c.answer("Foydalanuvchi topilmadi.", show_alert=True)
    if answer == "no" or uid == ADMIN_ID:
        await c.answer("Amal bekor qilindi.")
        return await show_user(c.message, db, u, True, c.from_user.id)
    blocking = not bool(u["blocked"])
    await db.set_user_block(uid, blocking)
    if blocking:
        await safe_call(lambda: bot.send_message(
            uid, "Siz botdan butunlay blocklandingiz. Sababini bilmoqchi bo‘lsangiz Yordam bo‘limidan adminga murojaat qiling.",
            reply_markup=kb.blocked_menu()))
        await c.message.edit_text("Foydalanuvchi bloklandi.")
    else:
        await safe_call(lambda: bot.send_message(
            uid, "Siz blockdan ozod etildingiz, endi erkin foydalanishingiz mumkin.", reply_markup=kb.main_menu()))
        await c.message.edit_text("Foydalanuvchi blockdan chiqarildi.")
    await c.answer()


@router.message(UserAdmin.add_amount)
async def user_amount(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    if not await require(m, db, "users"):
        return await state.clear()
    d = await state.get_data()
    action, uid = d.get("action"), d.get("target_uid")
    try:
        n = int((m.text or "").strip().replace(" ", ""))
        if n <= 0:
            raise ValueError
    except ValueError:
        return await m.answer("Musbat raqam yuboring.")
    if action == "vip":
        if n not in (1, 7, 30):
            return await m.answer("Faqat 1, 7 yoki 30 kun kiriting.")
        expiry = await db.set_vip(uid, n)
        await safe_call(lambda: bot.send_message(
            uid, f"Sizga {n} kunlik VIP obuna berildi. Amal qilish muddati: {fmt_local(expiry)}"))
        await delete_quietly(m)
        await state.clear()
        return await show_user(m, db, await db.user(uid), actor_id=m.from_user.id, prompt_data=d)
    await state.update_data(pending_amount=n)
    await state.set_state(UserAdmin.confirm_balance)
    await delete_quietly(m)
    await show_prompt(m, state, f"Rostdan ham {money(n)} so‘m {'qo‘shilsin' if action == 'add' else 'ayirilsin'}mi?",
                      kb.confirm_kb("ubalconfirm:yes", "ubalconfirm:no"))


@router.callback_query(F.data.startswith("ubalconfirm:"))
async def user_balance_confirm(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    if not await require(c, db, "users", alert=True):
        return
    d = await state.get_data()
    uid, n, action = d.get("target_uid"), int(d.get("pending_amount", 0)), d.get("action")
    if not uid or action not in ("add", "sub"):
        return await c.answer("Amal topilmadi.", show_alert=True)
    note = "Amal bekor qilindi."
    if c.data.endswith(":yes"):
        actual = await db.adjust_balance(uid, n if action == "add" else -n, "admin_adjust")
        if actual:
            await safe_call(lambda: bot.send_message(
                uid, f"Balansingiz {money(abs(actual))} so‘mga {'oshirildi' if actual > 0 else 'kamaytirildi'}."))
            note = "Balans yangilandi." if abs(actual) == n else f"Balans yangilandi ({money(abs(actual))} so‘m — mavjud mablag‘ shuncha edi)."
        else:
            note = "Balans o‘zgarmadi (mablag‘ yo‘q)."
    await state.clear()
    await show_user(c.message, db, await db.user(uid), True, c.from_user.id)
    await c.answer(note, show_alert=len(note) > 30)


@router.message(UserAdmin.message)
async def user_message(m: types.Message, state: FSMContext, bot: Bot, db: Database):
    if not await require(m, db, "users"):
        return await state.clear()
    d = await state.get_data()
    uid = d["target_uid"]
    sent = await safe_call(lambda: m.copy_to(uid, protect_content=True))
    await delete_quietly(m)
    await state.clear()
    await show_user(m, db, await db.user(uid), actor_id=m.from_user.id, prompt_data=d)
    await safe_call(lambda: bot.send_message(m.chat.id, "Xabar yuborildi." if sent else "Xabar yuborilmadi."))


# ===================================================================== ADMIN TAYINLASH
async def show_admin_permissions(target, uid, selected):
    rows = [[InlineKeyboardButton(text=f"{'✅' if key in selected else '❌'} {label}",
                                  callback_data=f"uperm:{uid}:{key}")] for key, label in PERMISSIONS.items()]
    rows.append([InlineKeyboardButton(text="Orqaga", callback_data=f"uadminback:{uid}"),
                 InlineKeyboardButton(text="Bo‘ldi", callback_data=f"upermdone:{uid}")])
    markup, text = InlineKeyboardMarkup(inline_keyboard=rows), "Admin imkoniyatlarini belgilang:"
    try:
        await target.edit_text(text, reply_markup=markup)
    except Exception:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("uadmin:"))
async def user_admin_start(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "admin_manage", alert=True):
        return
    await state.clear()
    uid = int(c.data.split(":")[1])
    if uid == ADMIN_ID:
        return await c.answer("Bosh adminni qayta tayinlab bo‘lmaydi.", show_alert=True)
    await state.update_data(admin_target=uid, admin_permissions=[])
    await state.set_state(UserAdmin.admin_permissions)
    await show_admin_permissions(c.message, uid, [])
    await c.answer()


@router.callback_query(F.data.startswith("uadminback:"))
async def admin_perm_back(c: types.CallbackQuery, state: FSMContext, db: Database):
    """Admin tayinlashdan voz kechish: hech narsa saqlanmaydi, foydalanuvchi profiliga qaytiladi."""
    if not await require(c, db, "admin_manage", alert=True):
        return
    await state.clear()
    u = await db.user(int(c.data.split(":")[1]))
    await c.answer("Admin tayinlash bekor qilindi.")
    if u:
        await show_user(c.message, db, u, True, c.from_user.id)


@router.callback_query(F.data.startswith("uperm:"))
async def permission_toggle(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "admin_manage", alert=True):
        return
    _, uid, key = c.data.split(":")
    data = await state.get_data()
    if data.get("admin_target") != int(uid) or key not in PERMISSIONS:
        return await c.answer("Admin tayinlash jarayoni topilmadi.", show_alert=True)
    selected = set(data.get("admin_permissions", []))
    selected.symmetric_difference_update({key})
    await state.update_data(admin_permissions=list(selected))
    await show_admin_permissions(c.message, int(uid), selected)
    await c.answer()


@router.callback_query(F.data.startswith("upermdone:"))
async def permission_done(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "admin_manage", alert=True):
        return
    uid = int(c.data.split(":")[1])
    if (await state.get_data()).get("admin_target") != uid:
        return await c.answer("Admin tayinlash jarayoni topilmadi.", show_alert=True)
    await c.message.edit_text("Haqiqatdan ham shu foydalanuvchini admin qilib tayinlamoqchimisiz?",
                              reply_markup=kb.confirm_kb(f"uadminconfirm:{uid}:yes", f"uadminconfirm:{uid}:no"))
    await c.answer()


@router.callback_query(F.data.startswith("uadminconfirm:"))
async def admin_confirm(c: types.CallbackQuery, state: FSMContext, db: Database):
    if not await require(c, db, "admin_manage", alert=True):
        return
    _, raw_uid, answer = c.data.split(":")
    uid = int(raw_uid)
    data = await state.get_data()
    if data.get("admin_target") != uid:
        return await c.answer("Admin tayinlash jarayoni topilmadi.", show_alert=True)
    if answer == "no":
        await state.clear()
        await c.answer()
        return await show_user(c.message, db, await db.user(uid), True, c.from_user.id)
    perms = data.get("admin_permissions", [])
    await db.set_admin(uid, perms)
    await state.clear()
    await safe_call(lambda: c.bot.send_message(
        uid, f"Siz botga admin etib tayinlandingiz.\nUnvoningiz: {admin_level(perms)}", reply_markup=kb.admin_menu()))
    await c.message.edit_text("Foydalanuvchi belgilangan huquqlar bilan admin etib tayinlandi.")
    await c.answer("Admin tayinlandi.")


@router.callback_query(F.data.startswith("uremoveadmin:"))
async def remove_admin_ask(c: types.CallbackQuery, db: Database):
    if not await require(c, db, "admin_manage", alert=True):
        return
    uid = int(c.data.split(":")[1])
    if uid == ADMIN_ID:
        return await c.answer("Bosh adminlikni bekor qilib bo‘lmaydi.", show_alert=True)
    await c.message.edit_text("Haqiqatdan ham shu foydalanuvchining adminlik huquqlarini bekor qilmoqchimisiz?",
                              reply_markup=kb.confirm_kb(f"uremoveconfirm:{uid}:yes", f"uremoveconfirm:{uid}:no"))
    await c.answer()


@router.callback_query(F.data.startswith("uremoveconfirm:"))
async def remove_admin_confirm(c: types.CallbackQuery, db: Database):
    if not await require(c, db, "admin_manage", alert=True):
        return
    _, raw_uid, answer = c.data.split(":")
    uid = int(raw_uid)
    if answer == "no" or uid == ADMIN_ID:
        u = await db.user(uid)
        await c.answer("Bosh admin himoyalangan." if uid == ADMIN_ID else None, show_alert=uid == ADMIN_ID)
        return await (show_user(c.message, db, u, True, c.from_user.id) if u
                      else c.message.edit_text("Foydalanuvchi topilmadi."))
    await db.remove_admin(uid)
    await safe_call(lambda: c.bot.send_message(uid, "Adminlik huquqingiz bekor qilindi.", reply_markup=kb.main_menu()))
    await c.message.edit_text("Adminlik bekor qilindi. Foydalanuvchi oddiy foydalanuvchi holatiga qaytarildi.")
    await c.answer()
