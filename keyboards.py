from aiogram.types import ReplyKeyboardMarkup,KeyboardButton,InlineKeyboardMarkup,InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Kabinet'),KeyboardButton(text='Yordam')],[KeyboardButton(text='Bot haqida')]],resize_keyboard=True)
def admin_menu(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Ish stoli'),KeyboardButton(text='Sozlamalar')],[KeyboardButton(text='Statistika')]],resize_keyboard=True)
def limited_admin_menu(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Sozlamalar')]],resize_keyboard=True)
def desk(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Video qo‘shish'),KeyboardButton(text='Video o‘chirish')],[KeyboardButton(text='Reklama jo‘natish'),KeyboardButton(text='Gift o‘tkazish')],[KeyboardButton(text='Bosh menyu')]],resize_keyboard=True)
def settings(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Kanallar'),KeyboardButton(text='Foydalanuvchilar')],[KeyboardButton(text='Karta edit'),KeyboardButton(text='VIP edit'),KeyboardButton(text='Info edit')],[KeyboardButton(text='Referral edit'),KeyboardButton(text='Admin link edit')],[KeyboardButton(text='Bosh menyu')]],resize_keyboard=True)
def inline(rows): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t,callback_data=d)] for t,d in rows])
def channels_kb(channels):
    b=InlineKeyboardBuilder()
    for i,c in enumerate(channels,1): b.button(text=f'Kanal {i} ({c["kind"]})',url=c['join_url']) if c['join_url'] else b.button(text=f'Kanal {i}',callback_data='noop')
    b.button(text='Tekshirish',callback_data='check_sub'); b.adjust(1); return b.as_markup()
def quality_kb(rows):
    b=InlineKeyboardBuilder()
    for r in rows: b.button(text=r['quality'],callback_data=f'quality:{r["quality"]}')
    b.adjust(2); return b.as_markup()
def id_kb(page,total):
    rows=[]
    nav=[]
    if page>1: nav.append(InlineKeyboardButton(text='Orqaga',callback_data=f'idpage:{page-1}'))
    if page<total: nav.append(InlineKeyboardButton(text='Oldinga',callback_data=f'idpage:{page+1}'))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text='Bosh menyu',callback_data='idhome')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def yesno(prefix): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=prefix+':yes'),InlineKeyboardButton(text='Yo‘q',callback_data=prefix+':no')]])
def votes(v): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Yoqdi',callback_data=f'vote:{v}:1'),InlineKeyboardButton(text='Yoqmadi',callback_data=f'vote:{v}:-1')],[InlineKeyboardButton(text='Videoni ko‘rish',url=f'https://t.me/placeholder?start=video_{v}')]])
