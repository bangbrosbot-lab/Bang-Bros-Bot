"""Umumiy yordamchilar: formatlash, prompt-xabarlar, xavfsiz yuborish, ommaviy jo‘natish."""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Awaitable, Callable, Iterable

from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest,
                                TelegramForbiddenError, TelegramRetryAfter)

log = logging.getLogger(__name__)

_BACKGROUND: set[asyncio.Task] = set()


def money(n) -> str:
    return f"{int(n or 0):,}".replace(",", " ")


def username_text(username) -> str:
    """«@nom» yoki, username bo‘lmasa, «Mavjud emas» (hech qachon «@mavjud emas» emas)."""
    name = (username or "").lstrip("@").strip()
    return f"@{name}" if name else "Mavjud emas"


def esc(value) -> str:
    return html.escape(str(value or ""))


def spawn(coro) -> asyncio.Task:
    """Fon vazifasi (garbage-collector o‘chirib yubormasligi uchun havola saqlanadi)."""
    task = asyncio.create_task(coro)
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return task


def is_not_modified(exc: Exception) -> bool:
    return isinstance(exc, TelegramBadRequest) and "not modified" in str(exc).lower()


async def delete_quietly(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def show_prompt(target, state, text, reply_markup=None):
    """Bitta ‘boshqaruv xabari’ni tahrirlab boradi (chat toza qoladi)."""
    data = await state.get_data()
    mid, chat_id = data.get("prompt_id"), data.get("prompt_chat_id")
    if mid and chat_id:
        try:
            return await target.bot.edit_message_text(text, chat_id=chat_id, message_id=mid,
                                                      reply_markup=reply_markup)
        except Exception as e:
            if is_not_modified(e):
                return None
    # Callback tugmasidan boshlangan yangi amal bo‘lsa, botning avvalgi
    # boshqaruv xabarini tahrirlaymiz; chatda eski prompt yig‘ilib qolmaydi.
    if getattr(getattr(target, "from_user", None), "is_bot", False):
        try:
            msg = await target.edit_text(text, reply_markup=reply_markup)
            await state.update_data(prompt_id=msg.message_id, prompt_chat_id=msg.chat.id)
            return msg
        except Exception as e:
            if is_not_modified(e):
                return target
    msg = await target.answer(text, reply_markup=reply_markup)
    await state.update_data(prompt_id=msg.message_id, prompt_chat_id=msg.chat.id)
    return msg


async def finish_prompt(target, state, text, reply_markup=None):
    data = await state.get_data()
    mid, chat_id = data.get("prompt_id"), data.get("prompt_chat_id")
    ui_mid, ui_chat = data.get("ui_message_id"), data.get("ui_chat_id")
    await state.clear()
    if ui_mid and ui_chat:
        await state.update_data(ui_message_id=ui_mid, ui_chat_id=ui_chat)
    if mid and chat_id:
        try:
            res = await target.bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=reply_markup)
            return res if hasattr(res, "message_id") else None
        except Exception as e:
            if is_not_modified(e):
                return None
    if getattr(getattr(target, "from_user", None), "is_bot", False):
        try:
            return await target.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            if is_not_modified(e):
                return None
    return await target.answer(text, reply_markup=reply_markup)


async def safe_call(factory: Callable[[], Awaitable], retries: int = 2) -> bool:
    """Telegram chaqiruvini bajaradi: flood-limitda kutib qayta urinadi, xatoda False qaytaradi."""
    for _ in range(retries + 1):
        try:
            await factory()
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except TelegramForbiddenError:
            return False
        except TelegramAPIError as e:
            log.debug("Telegram xatosi: %s", e)
            return False
    return False


async def mass_send(ids: Iterable[int], send: Callable[[int], Awaitable], per_second: int = 20) -> tuple[int, int]:
    """Ommaviy jo‘natish (sekundiga ~20 ta — Telegram limitidan past). (yuborildi, yuborilmadi)"""
    ok = bad = 0
    delay = 1 / per_second
    for uid in ids:
        if await safe_call(lambda uid=uid: send(uid)):
            ok += 1
        else:
            bad += 1
        await asyncio.sleep(delay)
    return ok, bad
