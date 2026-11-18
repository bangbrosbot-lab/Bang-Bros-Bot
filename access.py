"""Kirish nazorati: bloklanganlik va majburiy kanallarga obuna."""
from __future__ import annotations

import asyncio
import logging
import time

from keyboards import blocked_menu, channels_kb
from utils import delete_quietly

log = logging.getLogger(__name__)

BLOCKED_TEXT = ("Siz botdan butunlay blocklandingiz. Sababini bilmoqchi bo‘lsangiz "
                "Yordam bo‘limidan adminga murojaat qiling.")
NO_ACCESS = "Botdan foydalanish huquqingiz cheklangan."

_SUB_TTL = 3  # soniya: faqat MUVAFFAQIYATLI tekshiruv eslab qolinadi (kanaldan chiqsa, deyarli darrov seziladi)
_sub_ok: dict[int, float] = {}


def invalidate_sub_cache() -> None:
    _sub_ok.clear()


async def _in_channel(bot, db, channel, uid) -> bool:
    cid = channel["channel_id"]
    try:
        member = await bot.get_chat_member(cid, uid)
    except Exception as e:
        log.warning("get_chat_member(%s, %s) xatosi: %s", cid, uid, e)
        return await db.has_join_request(uid, cid)
    if member.status in ("left", "kicked"):
        return await db.has_join_request(uid, cid)
    if member.status == "restricted" and not getattr(member, "is_member", False):
        return False
    # Haqiqiy a’zo: eski ‘so‘rov’ izini tozalaymiz (keyin chiqib ketsa, aylanib o‘ta olmasin)
    await db.clear_join_request(uid, cid)
    return True


async def subscribed(bot, db, uid: int, use_cache: bool = True) -> bool:
    now = time.monotonic()
    if use_cache and _sub_ok.get(uid, 0) > now:
        return True
    channels = await db.mandatory()
    if channels:
        results = await asyncio.gather(*(_in_channel(bot, db, ch, uid) for ch in channels))
        if not all(results):
            _sub_ok.pop(uid, None)
            return False
        if len(_sub_ok) > 20000:
            _sub_ok.clear()
        _sub_ok[uid] = now + _SUB_TTL
    return True


async def ask_sub(m, db):
    for ch in await db.mandatory():
        if not ch["title"]:
            try:
                chat = await m.bot.get_chat(ch["channel_id"])
                title = chat.title or chat.username or str(ch["channel_id"])
                await db.add_channel(ch["channel_id"], ch["kind"], ch["join_url"], title)
            except Exception:
                pass
    channels = await db.mandatory()
    text = "Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling!"
    markup = channels_kb(channels)
    # Callbackdan kelgan bot xabarini tahrirlaymiz, media bo‘lsa avval o‘chiramiz.
    if getattr(getattr(m, "from_user", None), "is_bot", False):
        if m.video or m.photo or m.animation or m.document or m.audio:
            await delete_quietly(m)
            return await m.answer(text, reply_markup=markup)
        try:
            return await m.edit_text(text, reply_markup=markup)
        except Exception:
            await delete_quietly(m)
    return await m.answer(text, reply_markup=markup)


async def guard_message(m, db, bot, need_sub: bool = True) -> bool:
    u = await db.user(m.from_user.id)
    if u and u["blocked"]:
        await m.answer(BLOCKED_TEXT, reply_markup=blocked_menu())
        return False
    if need_sub and not await subscribed(bot, db, m.from_user.id):
        await ask_sub(m, db)
        return False
    return True


async def guard_call(call, db, bot, need_sub: bool = True, sub_alert: str | None = None,
                     need_user: bool = True) -> bool:
    u = await db.user(call.from_user.id)
    if (need_user and not u) or (u and u["blocked"]):
        await call.answer(NO_ACCESS, show_alert=True)
        return False
    if need_sub and not await subscribed(bot, db, call.from_user.id):
        if sub_alert:
            await call.answer(sub_alert, show_alert=True)
        else:
            await ask_sub(call.message, db)
            await call.answer()
        return False
    return True
