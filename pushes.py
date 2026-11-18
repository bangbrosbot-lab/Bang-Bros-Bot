"""Botdan kelgan yangi xabar chatdagi eski bot xabarlarini o‘chiradi (menyular to‘planib qolmasin).

* `TrackingBot` — botning shaxsiy chatlarga yuborgan MATN xabarlarini (va nusxa xabarlarni) eslab boradi.
  Rasm/video/fayl (video, chek rasmlari va h.k.) eslab qolinmaydi, shuning uchun ular hech qachon o‘chmaydi.
* `push*` funksiyalari — yangi xabarni yuborishdan oldin shu chatdagi eski xabarlarni o‘chiradi.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.methods import CopyMessage, SendMessage
from aiogram.types import Message

log = logging.getLogger(__name__)

_MAX_PER_CHAT = 60
_MAX_CHATS = 50000
_tracked: dict[int, list[int]] = {}
_menus: dict[int, int] = {}  # chat_id -> hozir ochiq turgan bosh menyu xabari (har chatda faqat bitta)
_MENU_MARKERS = {"umenu:cabinet", "amenu:desk"}  # foydalanuvchi / admin bosh menyusini aniqlash belgilari


def is_menu_markup(markup) -> bool:
    try:
        return any(getattr(b, "callback_data", None) in _MENU_MARKERS
                   for row in markup.inline_keyboard for b in row)
    except Exception:
        return False


def track(chat_id: int, message_id: int) -> None:
    if len(_tracked) > _MAX_CHATS:
        _tracked.clear()
    ids = _tracked.setdefault(chat_id, [])
    ids.append(message_id)
    if len(ids) > _MAX_PER_CHAT:
        del ids[: len(ids) - _MAX_PER_CHAT]


def forget(chat_id: int, message_id: int) -> None:
    ids = _tracked.get(chat_id)
    if ids and message_id in ids:
        ids.remove(message_id)


class TrackingBot(Bot):
    async def _register_menu(self, chat_id: int, message_id: int) -> None:
        """Yangi bosh menyu ochilsa, oldingisi o‘chiriladi."""
        old = _menus.get(chat_id)
        _menus[chat_id] = message_id
        if old and old != message_id:
            try:
                await self.delete_message(chat_id, old)
            except Exception:
                pass
            forget(chat_id, old)

    async def __call__(self, method, *args, **kwargs):
        result = await super().__call__(method, *args, **kwargs)
        try:
            markup = getattr(method, "reply_markup", None)
            if markup is not None and is_menu_markup(markup):
                if isinstance(result, Message) and result.chat.type == "private":
                    await self._register_menu(result.chat.id, result.message_id)  # yuborilgan/tahrirlangan
            if isinstance(method, SendMessage) and isinstance(result, Message) and result.chat.type == "private":
                track(result.chat.id, result.message_id)
            elif isinstance(method, CopyMessage) and isinstance(method.chat_id, int) and method.chat_id > 0:
                mid = getattr(result, "message_id", None)
                if mid:
                    track(method.chat_id, mid)
        except Exception:  # kuzatuv hech qachon asosiy ishni to‘xtatmasin
            log.debug("Xabarni kuzatishda xato", exc_info=True)
        return result


async def clear_previous(bot: Bot, chat_id: int) -> None:
    """Shu chatdagi botning avval yuborgan (kuzatilgan) xabarlarini o‘chiradi."""
    ids = _tracked.pop(chat_id, None)
    if not ids:
        return
    if _menus.get(chat_id) in ids:
        _menus.pop(chat_id, None)
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id, chunk)
        except Exception:
            for mid in chunk:  # ommaviy o‘chirish bo‘lmasa, birma-bir
                try:
                    await bot.delete_message(chat_id, mid)
                except Exception:
                    pass


async def push(bot: Bot, chat_id: int, text: str, **kwargs):
    """Yangi matnli xabar: avval eski xabarlar o‘chiriladi."""
    await clear_previous(bot, chat_id)
    return await bot.send_message(chat_id, text, **kwargs)


async def push_copy(bot: Bot, chat_id: int, from_chat_id: int, message_id: int, **kwargs):
    """Yangi nusxa (reklama): avval eski xabarlar o‘chiriladi."""
    await clear_previous(bot, chat_id)
    return await bot.copy_message(chat_id, from_chat_id, message_id, **kwargs)
