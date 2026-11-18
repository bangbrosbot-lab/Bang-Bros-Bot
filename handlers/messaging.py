"""Admin ↔ foydalanuvchi xabarlari: «Sizga xabar keldi» + «Javob yozish | Bosh menyu» zanjiri."""
from __future__ import annotations

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import is_owner
from db import Database
from pushes import clear_previous
from states import Reply
from utils import delete_quietly, safe_call, username_text

router = Router()

INCOMING = "Sizga xabar keldi."


def home_callback(db: Database, uid: int) -> str:
    """Adminga — admin paneli, oddiy foydalanuvchiga — asosiy menyu."""
    return "amenu:home" if (is_owner(uid) or db.is_admin(uid)) else "umenu:home"


async def deliver_message(bot: Bot, db: Database, m: types.Message, to_uid: int) -> bool:
    """`m` ni (matn/rasm/video...) `to_uid` ga «Sizga xabar keldi.» + [Javob yozish | Bosh menyu] bilan yuboradi."""
    sender = m.from_user
    await clear_previous(bot, to_uid)  # yangi xabar eskilarini o‘chiradi
    header = INCOMING
    if is_owner(to_uid) or db.is_admin(to_uid):
        header += (f"\n\nKimdan: {sender.full_name}\nUser: {username_text(sender.username)}\nID: {sender.id}")
    try:
        head = await bot.send_message(to_uid, header)
    except TelegramAPIError:
        return False
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Javob yozish", callback_data=f"msgreply:{sender.id}:{head.message_id}"),
        InlineKeyboardButton(text="Bosh menyu", callback_data=home_callback(db, to_uid))]])
    try:
        await m.copy_to(to_uid, reply_markup=markup, protect_content=True)
        return True
    except TelegramAPIError:
        await safe_call(lambda: bot.delete_message(to_uid, head.message_id))
        return False


@router.callback_query(F.data.startswith("msgreply:"))
async def reply_start(c: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    parts = c.data.split(":")
    try:
        target, header_id = int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        return await c.answer()
    await state.clear()
    chat_id = c.message.chat.id
    await delete_quietly(c.message)  # kelgan xabar
    if header_id:
        await safe_call(lambda: bot.delete_message(chat_id, header_id))  # «Sizga xabar keldi.»
    home = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Bosh menyu", callback_data=home_callback(db, c.from_user.id))]])
    prompt = await bot.send_message(chat_id, "Jo‘natmoqchi bo‘lgan javobingizni yozing!", reply_markup=home)
    await state.set_state(Reply.text)
    await state.update_data(reply_to=target, prompt_id=prompt.message_id, prompt_chat_id=chat_id,
                            ui_message_id=prompt.message_id, ui_chat_id=chat_id)
    await c.answer()


@router.message(Reply.text)
async def reply_send(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    d = await state.get_data()
    target = d.get("reply_to")
    if not target:
        await state.clear()
        return
    sent = await deliver_message(bot, db, m, target)
    await delete_quietly(m)  # yuborilgan javob chatdan o‘chadi
    await state.clear()
    home = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Bosh menyu", callback_data=home_callback(db, m.from_user.id))]])
    text = "Javob jo‘natildi." if sent else "Javob yuborilmadi (foydalanuvchi botni to‘xtatgan bo‘lishi mumkin)."
    pid, pchat = d.get("prompt_id"), d.get("prompt_chat_id", m.chat.id)
    try:
        if not pid:
            raise ValueError
        await bot.edit_message_text(text, chat_id=pchat, message_id=pid, reply_markup=home)
    except Exception:
        await m.answer(text, reply_markup=home)
