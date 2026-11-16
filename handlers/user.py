import html
from aiogram import Router, F, types, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import Database
from config import ADMIN_ID
from keyboards import main_menu, channels_kb
from states import TopUp

router = Router()

async def user_prompt(target,state,text,reply_markup=None):
    data=await state.get_data(); mid=data.get('prompt_id'); chat_id=data.get('prompt_chat_id')
    if mid and chat_id:
        try: return await target.bot.edit_message_text(text,chat_id=chat_id,message_id=mid,reply_markup=reply_markup)
        except Exception: pass
    msg=await target.answer(text,reply_markup=reply_markup)
    await state.update_data(prompt_id=msg.message_id,prompt_chat_id=msg.chat.id)
    return msg

async def user_finish(target,state,text,reply_markup=None):
    data=await state.get_data(); mid=data.get('prompt_id'); chat_id=data.get('prompt_chat_id')
    if mid and chat_id:
        try: await target.bot.edit_message_text(text,chat_id=chat_id,message_id=mid,reply_markup=reply_markup)
        except Exception: await target.answer(text,reply_markup=reply_markup)
    else: await target.answer(text,reply_markup=reply_markup)
    await state.clear()

async def remove_incoming(m):
    try: await m.delete()
    except Exception: pass

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

async def subscribed(bot, db, uid):
    for ch in await db.mandatory():
        try:
            member = await bot.get_chat_member(ch['channel_id'], uid)
            if member.status in ('left', 'kicked'):
                if await db.has_join_request(uid, ch['channel_id']):
                    continue
                return False
            if member.status == 'restricted' and not getattr(member, 'is_member', False):
                return False
        except Exception:
            if not await db.has_join_request(uid, ch['channel_id']):
                return False
    return True

async def ask_sub(m, db):
    channels = await db.mandatory()
    await m.answer('Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling!', reply_markup=channels_kb(channels))

async def welcome(m, bot, db, user=None):
    user = user or m.from_user
    text = (f"Salom, {user.first_name}! Bang Bros’ga xush kelibsiz!\n\n"
            "Videolarni tomosha qilish uchun maxsus kanalimizga kiring va o‘zingizga yoqqan videoni tanlab, videoni ko‘rish tugmasini bosing!")
    special = next((x for x in await db.all_channels() if x['kind'] == 'special'), None)
    rows = []
    if special:
        url = special['join_url']
        if not url:
            try:
                chat = await bot.get_chat(special['channel_id'])
                if chat.username:
                    url = f'https://t.me/{chat.username}'
            except Exception:
                pass
        if url:
            rows.append([InlineKeyboardButton(text='Kanalga kirish', url=url)])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    await m.answer('Asosiy menyu', reply_markup=main_menu())

async def referral_link(user_id, bot):
    me = await bot.get_me()
    return f'https://t.me/{me.username}?start=ref{user_id}'

async def notify_new_user(bot, user, referrer=None):
    username = f'@{user.username}' if user.username else 'Mavjud emas'
    if referrer:
        text = ("Referral orqali yangi foydalanuvchi\n\n"
                f"Ismi: {user.full_name}\nUseri: {username}\nIDsi: {user.id}\nTaklif qiluvchi: {referrer}")
    else:
        text = ("Yangi foydalanuvchi\n\n"
                f"Ismi: {user.full_name}\nUseri: {username}\nIDsi: {user.id}")
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception:
        pass

async def vote_markup(db, vid, bot_username):
    likes, dislikes = await db.vote_counts(vid)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'Yoqdi ({likes})', callback_data=f'vote:{vid}:1'),
         InlineKeyboardButton(text=f'Yoqmadi ({dislikes})', callback_data=f'vote:{vid}:-1')],
        [InlineKeyboardButton(text='Videoni ko‘rish', url=f'https://t.me/{bot_username}?start=video_{vid}')]
    ])

async def deliver_teaser(m, db, vid):
    v = await db.video(vid)
    if not v:
        return await m.answer('Video topilmadi.')
    await m.answer_video(v['teaser_id'], caption=v['caption'], reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='To‘liq video', callback_data=f'full:{vid}')]]), protect_content=True)

@router.message(CommandStart())
async def start(m: types.Message, command: CommandStart, db: Database, bot: Bot, state:FSMContext):
    await state.clear()
    ref = None
    if command.args:
        arg = command.args.strip()
        if arg.startswith('ref_'):
            arg = arg[4:]
        elif arg.startswith('ref'):
            arg = arg[3:]
        try:
            ref = int(arg)
        except Exception:
            ref = None
    is_new = await db.add_user(m.from_user.id, m.from_user.full_name, m.from_user.username, ref)
    u = await db.user(m.from_user.id)
    if u['blocked']:
        return await m.answer('Botdan foydalanish huquqingiz cheklangan.')
    if m.from_user.id == ADMIN_ID or await db.is_admin(m.from_user.id):
        from keyboards import admin_menu, limited_admin_menu
        menu=admin_menu() if m.from_user.id==ADMIN_ID else limited_admin_menu()
        return await m.answer('Admin panel', reply_markup=menu)
    if is_new:
        valid_ref = ref if ref and ref != m.from_user.id else None
        credited = False
        if valid_ref:
            bonus = int(await db.setting('referral_bonus') or 500)
            credited = await db.credit_referral(m.from_user.id, valid_ref, bonus)
        await notify_new_user(bot, m.from_user, valid_ref if credited else None)
    if not await subscribed(bot, db, m.from_user.id):
        return await ask_sub(m, db)
    if command.args and command.args.startswith('video_'):
        try:
            return await deliver_teaser(m, db, int(command.args.split('_', 1)[1]))
        except Exception:
            pass
    await welcome(m, bot, db)

@router.callback_query(F.data == 'check_sub')
async def check(call: types.CallbackQuery, db: Database, bot: Bot):
    u = await db.user(call.from_user.id)
    if u and u['blocked']:
        return await call.answer('Botdan foydalanish huquqingiz cheklangan.', show_alert=True)
    if await subscribed(bot, db, call.from_user.id):
        try: await call.message.delete()
        except Exception: pass
        await welcome(call.message, bot, db, call.from_user)
    else:
        await call.answer('Hali barcha kanallarga qo‘shilmadingiz yoki so‘rovingiz qabul qilinmadi.', show_alert=True)

@router.callback_query(F.data.startswith('full:'))
async def full(call: types.CallbackQuery, db: Database):
    u = await db.user(call.from_user.id)
    if not u or u['blocked']:
        return await call.answer('Botdan foydalanish huquqingiz cheklangan.', show_alert=True)
    vid = int(call.data.split(':')[1])
    if not await db.vip(call.from_user.id):
        return await call.answer('Afsuski, hozircha ushbu videoning to‘liq versiyasini ko‘ra olmaysiz. To‘liq videolarni tomosha qilish uchun VIP obuna xarid qilishingiz kerak!', show_alert=True)
    v = await db.video(vid); qs = await db.qualities(vid)
    if not v or not qs:
        return await call.answer('Video yoki uning sifati topilmadi.', show_alert=True)
    await db.count_view(call.from_user.id, vid)
    q = qs[0]; views = await db.view_count(vid)
    await call.message.answer_video(q['file_id'], caption=f'{v["caption"]}\n\nSifati: {q["quality"]}\nKo‘rishlar: {views}', reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='Video sifatini almashtirish', callback_data=f'change:{vid}')]]), protect_content=True)
    await call.answer()

@router.callback_query(F.data.startswith('change:'))
async def change(call: types.CallbackQuery, db: Database):
    vid = int(call.data.split(':')[1]); qs = await db.qualities(vid)
    if not await db.vip(call.from_user.id):
        return await call.answer('VIP obuna talab qilinadi.', show_alert=True)
    try: await call.message.delete()
    except Exception: pass
    rows = [[InlineKeyboardButton(text=r['quality'], callback_data=f'quality:{vid}:{r["quality"]}')] for r in qs]
    await call.message.answer('Kerakli sifatni tanlang!', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith('quality:'))
async def quality(call: types.CallbackQuery, db: Database):
    _, vid, q = call.data.split(':', 2); vid = int(vid)
    if not await db.vip(call.from_user.id):
        return await call.answer('VIP obuna talab qilinadi.', show_alert=True)
    rows = await db.qualities(vid); chosen = next((r for r in rows if r['quality'] == q), None); v = await db.video(vid)
    if not chosen or not v:
        return await call.answer('Bu sifat mavjud emas.', show_alert=True)
    views = await db.view_count(vid)
    try: await call.message.delete()
    except Exception: pass
    await call.message.answer_video(chosen['file_id'], caption=f'{v["caption"]}\n\nSifati: {q}\nKo‘rishlar: {views}', reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='Video sifatini almashtirish', callback_data=f'change:{vid}')]]), protect_content=True)
    await call.answer()

@router.callback_query(F.data.startswith('vote:'))
async def vote(call: types.CallbackQuery, db: Database, bot: Bot):
    try:
        _, raw_vid, raw_vote = call.data.split(':'); vid = int(raw_vid); value = int(raw_vote)
        if value not in (1, -1): raise ValueError
        await db.vote(call.from_user.id, vid, value)
        me = await bot.get_me()
        await call.message.edit_reply_markup(reply_markup=await vote_markup(db, vid, me.username))
        await call.answer('Ovozingiz saqlandi.')
    except Exception:
        await call.answer('Ovoz qabul qilinmadi.', show_alert=True)

@router.message(F.text == 'Kabinet')
async def cabinet(m: types.Message, db: Database, state:FSMContext):
    await state.clear()
    u = await db.user(m.from_user.id)
    if not u: return await m.answer('Avval /start buyrug‘ini bosing.')
    vip = await db.vip(m.from_user.id); friends = await db.referrals_count(m.from_user.id)
    status = 'VIP obunachi' if vip else 'Oddiy obunachi'
    total_balance = int(u['balance'] or 0) + int(u['referral_balance'] or 0)
    await m.answer(f'Ism: {u["name"]}\nUser: @{u["username"] or "mavjud emas"}\nID: {u["user_id"]}\nBalans: {total_balance:,} so‘m\nHolati: {status}\nDo‘stlar: {friends}', reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Hisobni to‘ldirish', callback_data='topup'), InlineKeyboardButton(text='VIP olish', callback_data='vipmenu')],
        [InlineKeyboardButton(text='Pul ishlash', callback_data='referral')]]))

@router.callback_query(F.data == 'topup')
async def topup(call: types.CallbackQuery, state: FSMContext):
    await state.clear(); await state.set_state(TopUp.amount); await user_prompt(call.message,state,'To‘ldirmoqchi bo‘lgan summangizni yozing! Masalan: 10000'); await call.answer()

@router.message(TopUp.amount, F.text.in_({'Kabinet','Yordam','Bot haqida'}))
async def interrupt_topup(m:types.Message,state:FSMContext,db:Database):
    await state.clear()
    if m.text=='Kabinet': return await cabinet(m,db,state)
    if m.text=='Yordam': return await help_(m,db,state)
    if m.text=='Bot haqida': return await about(m,db,state)

@router.message(TopUp.amount)
async def topup_amount(m: types.Message, state: FSMContext, db: Database):
    try: amount = int((m.text or '').replace(' ', '').replace(',', ''))
    except Exception: return await m.answer('Summani raqam bilan kiriting.')
    if amount < 5000 or amount > 900000:
        return await m.answer('Eng kam summa 5 000, eng ko‘p summa 900 000 so‘m.')
    await state.update_data(amount=amount); await state.set_state(TopUp.receipt)
    card = await db.setting('card')
    amount_text=f'{amount:,}'.replace(',', ' ')
    await remove_incoming(m)
    await user_prompt(m,state,f'Quyidagi karta raqamiga kerakli summani o‘tkazing!\n\nSumma: {amount_text} so‘m\nKarta: {card}\n\nTo‘lovni amalga oshirgach, to‘lov chek rasmini jo‘nating!')

@router.message(TopUp.receipt, F.photo)
async def receipt(m: types.Message, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data(); rid = await db.create_topup(m.from_user.id, data['amount'], m.photo[-1].file_id)
    username = f'@{m.from_user.username}' if m.from_user.username else 'Mavjud emas'
    await bot.send_photo(ADMIN_ID, m.photo[-1].file_id,
        caption=(f'Hisobni to‘ldirish so‘rovi\n\nIsmi: {m.from_user.full_name}\nUser: {username}\nID: {m.from_user.id}\nSumma: {data["amount"]:,}'.replace(',', ' ')+' so‘m'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Tasdiqlash', callback_data=f'topupok:{rid}'), InlineKeyboardButton(text='Rad etish', callback_data=f'topupno:{rid}')]]), protect_content=True)
    await remove_incoming(m)
    await user_finish(m,state,f'To‘lov chekingiz adminga yuborildi.\nAdmin to‘lovni tasdiqlaganidan so‘ng, {data["amount"]:,}'.replace(',', ' ')+ ' so‘m hisobingizga qo‘shiladi.')

@router.callback_query(F.data == 'vipmenu')
async def vipmenu(call: types.CallbackQuery, db: Database, state:FSMContext):
    await state.clear()
    rows = []
    for days, label in [(1, '1 kunlik'), (7, '1 haftalik'), (30, '1 oylik')]:
        rows.append([InlineKeyboardButton(text=f'{label} — {int(await db.setting("vip_" + str(days))):,} so‘m', callback_data=f'vipbuy:{days}')])
    await call.message.answer('VIP tarifini tanlang:', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await call.answer()

@router.callback_query(F.data.startswith('vipbuy:'))
async def vipbuy(call: types.CallbackQuery, db: Database):
    days = int(call.data.split(':')[1]); price = int(await db.setting('vip_' + str(days))); u = await db.user(call.from_user.id)
    available = int(u['balance'] or 0) + int(u['referral_balance'] or 0)
    if available < price:
        return await call.answer(f'Balansingizda yetarli mablag‘ yo‘q.\nKerak: {price:,} so‘m\nBalansingiz: {available:,} so‘m\nHisobingizni to‘ldirish uchun Kabinetdagi "Hisobni to‘ldirish" bo‘limidan foydalaning!', show_alert=True)
    label = {1: '1 kunlik', 7: '1 haftalik', 30: '1 oylik'}[days]
    await call.message.answer(f'Tarif: {label}\nNarxi: {price:,} so‘m\n\nHaqiqatdan ham ushbu VIP obunani sotib olmoqchimisiz?', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha', callback_data=f'vipconfirm:{days}'), InlineKeyboardButton(text='Yo‘q', callback_data='vipcancel')]])); await call.answer()

@router.callback_query(F.data == 'vipcancel')
async def vipcancel(c: types.CallbackQuery):
    await c.message.edit_text('VIP xaridi bekor qilindi.'); await c.answer()

@router.callback_query(F.data.startswith('vipconfirm:'))
async def vipconfirm(c: types.CallbackQuery, db: Database):
    days = int(c.data.split(':')[1]); price = int(await db.setting('vip_' + str(days))); u = await db.user(c.from_user.id)
    if not u: return await c.answer('Foydalanuvchi topilmadi.', show_alert=True)
    expiry = await db.purchase_vip(c.from_user.id,days,price)
    if not expiry: return await c.answer('Balans yetarli emas yoki xarid amalga oshmadi.', show_alert=True)
    await c.message.edit_text(f'VIP obunangiz faollashtirildi.\nAmal qilish muddati: {expiry:%d.%m.%Y %H:%M}'); await c.answer()

@router.callback_query(F.data == 'referral')
async def referral(call: types.CallbackQuery, db: Database, state:FSMContext):
    await state.clear()
    u = await db.user(call.from_user.id)
    if not u['rules_accepted']:
        await call.message.answer(REF_INTRO.replace('500', str(await db.setting('referral_bonus') or 500)), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Qoidalar', callback_data='ref_rules')]]))
    else:
        link = await referral_link(call.from_user.id, call.bot)
        await call.message.answer(f'Sizning shaxsiy referal havolangiz:\n{link}\n\nUshbu havolani ishonchli do‘stlaringizga yuboring. Ular havola orqali botga kirib start bossa, hisobingizga {await db.setting("referral_bonus")} so‘m qo‘shiladi.')
    await call.answer()

@router.callback_query(F.data == 'ref_rules')
async def ref_rules(c: types.CallbackQuery):
    await c.message.answer(REF_RULES, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha', callback_data='refaccept'), InlineKeyboardButton(text='Yo‘q', callback_data='refdecline')]])); await c.answer()

@router.callback_query(F.data == 'refaccept')
async def refaccept(c: types.CallbackQuery, db: Database):
    await db.conn.execute('UPDATE users SET rules_accepted=1 WHERE user_id=?', (c.from_user.id,)); await db.conn.commit()
    link = await referral_link(c.from_user.id, c.bot)
    await c.message.answer(f'Sizning shaxsiy referal havolangiz:\n{link}\n\nUshbu havolani ishonchli do‘stlaringizga yuboring. Ular havola orqali botga kirib start bossa, hisobingizga {await db.setting("referral_bonus")} so‘m qo‘shiladi.')
    await c.answer()

@router.callback_query(F.data == 'refdecline')
async def refdecline(c: types.CallbackQuery):
    await c.answer('Referal havolasi berilmadi.')

@router.callback_query(F.data.startswith('claimgift:'))
async def claim_gift(c: types.CallbackQuery, db: Database):
    gid = int(c.data.split(':')[1]); status, g = await db.claim_gift(gid, c.from_user.id)
    if status == 'won':
        if g['kind'] == 'vip': await db.set_vip(c.from_user.id, g['days']); msg = f'Tabriklaymiz! Siz {g["days"]} kunlik VIP sovg‘ani qo‘lga kiritdingiz.'
        else: msg = f'Tabriklaymiz! {g["amount"]:,} so‘m sovg‘a balansingizga qo‘shildi.'
        await c.answer(msg, show_alert=True)
        if g['claimed'] + 1 >= g['winners_limit']:
            winners = await db.gift_winners(gid); lines = ['Gift g‘oliblari:']
            for i, w in enumerate(winners, 1): lines.append(f'{i}. {w["name"]} | @{w["username"] or "yo‘q"} | {w["user_id"]}')
            await c.bot.send_message(ADMIN_ID, '\n'.join(lines))
    elif status == 'vip': await c.answer('Sizda allaqachon faol VIP obuna bor.', show_alert=True)
    elif status == 'already': await c.answer('Siz allaqachon o‘z sovg‘angizni oldingiz.', show_alert=True)
    elif status == 'late': await c.answer('Afsuski, siz ulgurmadingiz. Keyingi giftda faolroq bo‘ling!', show_alert=True)
    else: await c.answer('Gift faol emas yoki topilmadi.', show_alert=True)

@router.message(F.text == 'Bot haqida')
async def about(m: types.Message, db: Database, state:FSMContext):
    await state.clear()
    kind = await db.setting('info_type'); file_id = await db.setting('info_file_id'); caption = await db.setting('info_caption')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Kanalimiz', url='https://t.me/Bangbros_studio')]])
    if kind == 'photo' and file_id: await m.answer_photo(file_id, caption=caption or None, reply_markup=kb, protect_content=True)
    elif kind == 'video' and file_id: await m.answer_video(file_id, caption=caption or None, reply_markup=kb, protect_content=True)
    else:
        body=caption or await db.setting('bot_info') or 'Bot haqida ma’lumot hozircha kiritilmagan.'
        await m.answer(body, reply_markup=kb)

@router.message(F.text == 'Yordam')
async def help_(m: types.Message, db: Database, state:FSMContext):
    await state.clear()
    url = (await db.setting('admin_link') or '').strip()
    text = 'Agar sizda muammolar yoki qanaqadur savollar paydo bo‘lgan bo‘lsa admin bilan bog‘lanishingiz mumkin'
    if url.startswith('@'): url = 'https://t.me/' + url[1:]
    elif url.startswith('t.me/'): url = 'https://' + url
    if url.startswith(('https://', 'http://', 'tg://')):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Bog‘lanish', url=url)]])
    else: kb = None
    await m.answer(text, reply_markup=kb)

@router.chat_join_request()
async def track_join_request(event: types.ChatJoinRequest, db: Database):
    await db.add_join_request(event.from_user.id, event.chat.id)
