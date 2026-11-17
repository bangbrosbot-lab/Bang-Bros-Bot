from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def _menu(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        for row in rows
    ])


def main_menu():
    return _menu([[("Kabinet", "umenu:cabinet"), ("Yordam", "umenu:help")],
                  [("Bot haqida", "umenu:about")]])


def admin_menu():
    return _menu([[("Ish stoli", "amenu:desk"), ("Sozlamalar", "amenu:settings")],
                  [("Statistika", "amenu:stats")]])


def blocked_menu():
    return _menu([[("Yordam", "umenu:help")]])


def desk():
    return _menu([[("Video qo‘shish", "amenu:addvideo"), ("Video o‘chirish", "amenu:delvideo")],
                  [("Reklama jo‘natish", "amenu:broadcast"), ("Gift o‘tkazish", "amenu:gift")],
                  [("Orqaga", "amenu:home")]])


def settings():
    return _menu([[("Kanallar", "amenu:channels"), ("Foydalanuvchilar", "amenu:users")],
                  [("Karta edit", "amenu:card"), ("VIP edit", "amenu:vip"), ("Info edit", "amenu:info")],
                  [("Referral edit", "amenu:referral"), ("Admin link edit", "amenu:adminlink")],
                  [("Orqaga", "amenu:home")]])


def confirm_kb(yes: str, no: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Ha", callback_data=yes),
        InlineKeyboardButton(text="Yo‘q", callback_data=no),
    ]])


def back_kb(data: str, text: str = "Orqaga") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data)]])


def rows_kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d)] for t, d in rows])


def channels_kb(channels):
    b = InlineKeyboardBuilder()
    for i, c in enumerate(channels, 1):
        title = c["title"] or f"Kanal {i}"
        if c["join_url"]:
            b.button(text=title, url=c["join_url"])
        else:
            b.button(text=title, callback_data="noop")
    b.button(text="Tekshirish", callback_data="check_sub")
    b.button(text="Orqaga", callback_data="subback")
    b.adjust(1)
    return b.as_markup()


def id_kb(page: int, total: int) -> InlineKeyboardMarkup:
    rows, nav = [], []
    if page > 1:
        nav.append(InlineKeyboardButton(text="Orqaga", callback_data=f"idpage:{page - 1}"))
    if page < total:
        nav.append(InlineKeyboardButton(text="Oldinga", callback_data=f"idpage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Orqaga", callback_data="idhome")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
