from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def _reply(rows):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,  # pastki menyu yig‘ilib/yo‘qolib qolmaydi
    )


def main_menu():
    return _reply([["Kabinet", "Yordam"], ["Bot haqida"]])


def admin_menu():
    return _reply([["Ish stoli", "Sozlamalar"], ["Statistika"]])


def blocked_menu():
    return _reply([["Yordam"]])


def desk():
    return _reply([
        ["Video qo‘shish", "Video o‘chirish"],
        ["Reklama jo‘natish", "Gift o‘tkazish"],
        ["Bosh menyu"],
    ])


def settings():
    return _reply([
        ["Kanallar", "Foydalanuvchilar"],
        ["Karta edit", "VIP edit", "Info edit"],
        ["Referral edit", "Admin link edit"],
        ["Bosh menyu"],
    ])


def confirm_kb(yes: str, no: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Ha", callback_data=yes),
        InlineKeyboardButton(text="Yo‘q", callback_data=no),
    ]])


def back_kb(data: str, text: str = "Orqaga") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data)]])


def rows_kb(rows) -> InlineKeyboardMarkup:
    """rows: [(matn, callback_data), ...] — har biri alohida qatorda."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d)] for t, d in rows])


def channels_kb(channels):
    b = InlineKeyboardBuilder()
    for i, c in enumerate(channels, 1):
        title = c["title"] or f"Kanal {i}"
        if c["join_url"]:
            b.button(text=title, url=c["join_url"])
        else:
            b.button(text=title, callback_data="noop")
    b.button(text="Tekshirish", callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()


def id_kb(page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="Orqaga", callback_data=f"idpage:{page - 1}"))
    if page < total:
        nav.append(InlineKeyboardButton(text="Oldinga", callback_data=f"idpage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Bosh menyu", callback_data="idhome")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
