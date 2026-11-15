from aiogram import Router,F,types,Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton
from db import Database
from config import ADMIN_ID
from keyboards import main_menu,channels_kb,admin_menu
from states import TopUp
router=Router()

async def subscribed(bot,db,uid):
    for ch in await db.mandatory():
        try:
            member=await bot.get_chat_member(ch['channel_id'],uid)
            if member.status in ('left','kicked'):
                if await db.has_join_request(uid,ch['channel_id']): continue
                return False
            if member.status=='restricted' and not getattr(member,'is_member',False): return False
        except Exception:
            # A private channel join request is accepted only if the bot observed it.
            if not await db.has_join_request(uid,ch['channel_id']): return False
    return True
async def ask_sub(m,db):
    ch=await db.mandatory()
    await m.answer('Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling!',reply_markup=channels_kb(ch))
async def welcome(m,bot,db):
    text=f'Salom, {m.from_user.first_name}! Bang Bros’ga xush kelibsiz!\n\nVideolarni tomosha qilish uchun maxsus kanalimizga kiring va o‘zingizga yoqqan videoni tanlab, videoni ko‘rish tugmasini bosing!'
    rows=[]
    special=next((x for x in await db.all_channels() if x['kind']=='special'),None)
    if special:
        try:
            chat=await bot.get_chat(special['channel_id'])
            if chat.username: rows.append([InlineKeyboardButton(text='Kanalga kirish',url=f'https://t.me/{chat.username}')])
        except: pass
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    await m.answer('Asosiy menyu',reply_markup=main_menu())
async def deliver_teaser(m,db,vid):
    v=await db.video(vid)
    if not v: return await m.answer('Video topilmadi.')
    await db.count_view(m.from_user.id,vid)
    await m.answer_video(v['teaser_id'],caption=v['caption'],reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='To‘liq video',callback_data=f'full:{vid}')]]))

@router.message(CommandStart())
async def start(m:types.Message,command:CommandStart,db:Database,bot:Bot):
    ref=None
    if command.args and command.args.startswith('ref_'):
        try: ref=int(command.args[4:])
        except: pass
    is_new=await db.add_user(m.from_user.id,m.from_user.full_name,m.from_user.username,ref)
    u=await db.user(m.from_user.id)
    if u['blocked']: return await m.answer('Botdan foydalanish huquqingiz cheklangan.')
    if m.from_user.id==ADMIN_ID:
        await m.answer('Admin panel',reply_markup=admin_menu()); return
    if is_new and ref and ref!=m.from_user.id:
        bonus=int(await db.setting('referral_bonus') or 0)
        await db.credit_referral(m.from_user.id,ref,bonus)
    if not await subscribed(bot,db,m.from_user.id): return await ask_sub(m,db)
    if command.args and command.args.startswith('video_'):
        try: return await deliver_teaser(m,db,int(command.args.split('_',1)[1]))
        except: pass
    await welcome(m,bot,db)

@router.callback_query(F.data=='check_sub')
async def check(call:types.CallbackQuery,db:Database,bot:Bot):
    u=await db.user(call.from_user.id)
    if u and u['blocked']: return await call.answer('Botdan foydalanish huquqingiz cheklangan.',show_alert=True)
    if await subscribed(bot,db,call.from_user.id):
        await call.message.delete(); await welcome(call.message,bot,db)
    else: await call.answer('Hali barcha kanallarga qo‘shilmadingiz yoki so‘rovingiz qabul qilinmadi.',show_alert=True)

@router.callback_query(F.data.startswith('full:'))
async def full(call:types.CallbackQuery,db:Database):
    u=await db.user(call.from_user.id)
    if not u or u['blocked']: return await call.answer('Botdan foydalanish huquqingiz cheklangan.',show_alert=True)
    vid=int(call.data.split(':')[1])
    if not await db.vip(call.from_user.id): return await call.answer('Afsuski, hozircha ushbu videoning to‘liq versiyasini ko‘ra olmaysiz. To‘liq videolarni tomosha qilish uchun VIP obuna xarid qilishingiz kerak!',show_alert=True)
    v=await db.video(vid); qs=await db.qualities(vid)
    if not v or not qs: return await call.answer('Video yoki uning sifati topilmadi.',show_alert=True)
    q=qs[0]; views=await db.view_count(vid)
    await call.message.answer_video(q['file_id'],caption=f'{v["caption"]}\n\nSifati: {q["quality"]}\nKo‘rishlar: {views}',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Video sifatini almashtirish',callback_data=f'change:{vid}')]]))
    await call.answer()
@router.callback_query(F.data.startswith('change:'))
async def change(call:types.CallbackQuery,db:Database):
    vid=int(call.data.split(':')[1]); qs=await db.qualities(vid)
    if not await db.vip(call.from_user.id): return await call.answer('VIP obuna talab qilinadi.',show_alert=True)
    try: await call.message.delete()
    except: pass
    b=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=r['quality'],callback_data=f'quality:{vid}:{r["quality"]}')] for r in qs])
    await call.message.answer('Kerakli sifatni tanlang!',reply_markup=b); await call.answer()
@router.callback_query(F.data.startswith('quality:'))
async def quality(call:types.CallbackQuery,db:Database):
    _,vid,q=call.data.split(':',2); vid=int(vid)
    if not await db.vip(call.from_user.id): return await call.answer('VIP obuna talab qilinadi.',show_alert=True)
    rows=await db.qualities(vid); chosen=next((r for r in rows if r['quality']==q),None); v=await db.video(vid)
    if not chosen or not v: return await call.answer('Bu sifat mavjud emas.',show_alert=True)
    views=await db.view_count(vid)
    await call.message.answer_video(chosen['file_id'],caption=f'{v["caption"]}\n\nSifati: {q}\nKo‘rishlar: {views}',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Video sifatini almashtirish',callback_data=f'change:{vid}')]])); await call.answer()
@router.callback_query(F.data.startswith('vote:'))
async def vote(call:types.CallbackQuery,db:Database):
    try: _,v,val=call.data.split(':'); await db.vote(call.from_user.id,int(v),int(val)); await call.answer('Ovozingiz saqlandi.')
    except: await call.answer('Ovoz qabul qilinmadi.',show_alert=True)

@router.message(F.text=='Kabinet')
async def cabinet(m:types.Message,db:Database):
    u=await db.user(m.from_user.id)
    if not u: return await m.answer('Avval /start buyrug‘ini bosing.')
    vip=await db.vip(m.from_user.id); friends=await db.referrals_count(m.from_user.id)
    status='VIP obunachi' if vip else 'Oddiy obunachi'
    await m.answer(f'Ism: {u["name"]}\nUser: @{u["username"] or "mavjud emas"}\nID: {u["user_id"]}\nBalans: {u["balance"]:,} so‘m\nHolati: {status}\nDo‘stlar: {friends}',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Hisobni to‘ldirish',callback_data='topup'),InlineKeyboardButton(text='VIP olish',callback_data='vipmenu')],[InlineKeyboardButton(text='Pul ishlash',callback_data='referral')]]))
@router.callback_query(F.data=='topup')
async def topup(call:types.CallbackQuery,state:FSMContext): await state.set_state(TopUp.amount); await call.message.answer('To‘ldirmoqchi bo‘lgan summangizni yozing! Masalan: 10000'); await call.answer()
@router.message(TopUp.amount)
async def topup_amount(m:types.Message,state:FSMContext,db:Database):
    try: amount=int(m.text)
    except: return await m.answer('Summani raqam bilan kiriting.')
    if amount<5000 or amount>900000: return await m.answer('Eng kam summa 5 000, eng ko‘p summa 900 000 so‘m.')
    await state.update_data(amount=amount); await state.set_state(TopUp.receipt)
    await m.answer(f'Quyidagi karta raqamiga kerakli summani o‘tkazing!\nSumma: {amount:,} so‘m\nKarta: {await db.setting("card")}\nTo‘lovni amalga oshirgach, to‘lov chek rasmini jo‘nating!')
@router.message(TopUp.receipt,F.photo)
async def receipt(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    data=await state.get_data(); rid=await db.create_topup(m.from_user.id,data['amount'],m.photo[-1].file_id); await state.clear()
    await bot.send_photo(ADMIN_ID,m.photo[-1].file_id,caption=f'Hisob to‘ldirish so‘rovi #{rid}\nFoydalanuvchi: {m.from_user.full_name}\nID: {m.from_user.id}\nSumma: {data["amount"]:,} so‘m',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Tasdiqlash',callback_data=f'topupok:{rid}'),InlineKeyboardButton(text='Rad qilish',callback_data=f'topupno:{rid}')]]))
    await m.answer('Chek adminga yuborildi. Tekshiruv natijasini kuting.')

@router.callback_query(F.data=='vipmenu')
async def vipmenu(call:types.CallbackQuery,db:Database):
    rows=[]
    for days,label in [(1,'1 kunlik'),(7,'1 haftalik'),(30,'1 oylik')]: rows.append([InlineKeyboardButton(text=f'{label} — {int(await db.setting("vip_"+str(days))):,} so‘m',callback_data=f'vipbuy:{days}')])
    await call.message.answer('VIP tarifini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await call.answer()
@router.callback_query(F.data.startswith('vipbuy:'))
async def vipbuy(call:types.CallbackQuery,db:Database):
    days=int(call.data.split(':')[1]); price=int(await db.setting('vip_'+str(days))); u=await db.user(call.from_user.id)
    if u['balance']<price: return await call.answer(f'Balansingizda yetarli mablag‘ yo‘q.\nKerak: {price:,} so‘m\nBalansingiz: {u["balance"]:,} so‘m\nHisobingizni to‘ldirish uchun Kabinetdagi "Hisobni to‘ldirish" bo‘limidan foydalaning!',show_alert=True)
    await call.message.answer(f'Tarif: { {1:"1 kunlik",7:"1 haftalik",30:"1 oylik"}[days] }\nNarxi: {price:,} so‘m\n\nHaqiqatdan ham ushbu VIP obunani sotib olmoqchimisiz?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=f'vipconfirm:{days}'),InlineKeyboardButton(text='Yo‘q',callback_data='vipcancel')]])); await call.answer()
@router.callback_query(F.data=='vipcancel')
async def vipcancel(c:types.CallbackQuery): await c.message.edit_text('VIP xaridi bekor qilindi.'); await c.answer()
@router.callback_query(F.data.startswith('vipconfirm:'))
async def vipconfirm(c:types.CallbackQuery,db:Database):
    days=int(c.data.split(':')[1]); price=int(await db.setting('vip_'+str(days))); u=await db.user(c.from_user.id)
    if not u or u['balance']<price: return await c.answer('Balans yetarli emas.',show_alert=True)
    await db.conn.execute('UPDATE users SET balance=balance-? WHERE user_id=?',(price,c.from_user.id)); await db.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(c.from_user.id,-price,'vip_purchase')); await db.conn.commit(); expiry=await db.set_vip(c.from_user.id,days)
    await c.message.edit_text(f'VIP obunangiz faollashtirildi.\nAmal qilish muddati: {expiry:%d.%m.%Y %H:%M}'); await c.answer()

@router.callback_query(F.data=='referral')
async def referral(call:types.CallbackQuery,bot:Bot,db:Database):
    u=await db.user(call.from_user.id)
    if not u['rules_accepted']:
        rules=('Referal dasturi qoidalari:\n\n1. Havolani faqat ishonchli do‘stlaringizga shaxsiy yuboring. Ommaviy guruh va kanallarga tarqatmang.\n2. O‘zingiz uchun soxta yoki qo‘shimcha akkauntlar yaratmang. Bonus faqat haqiqiy yangi foydalanuvchi uchun beriladi.\n3. Taklif qilayotgan insoningizni chalg‘itmang.\n\nQoidabuzarlik aniqlansa, akkauntingiz bloklanishi mumkin.\n\nBarcha qoidalarga rioya qilishga rozimisiz?')
        await call.message.answer(rules,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='refaccept'),InlineKeyboardButton(text='Yo‘q',callback_data='refdecline')]])); return await call.answer()
    me=await bot.get_me(); await call.message.answer(f'Referal havolangiz: https://t.me/{me.username}?start=ref_{call.from_user.id}\nHar bir haqiqiy yangi foydalanuvchi uchun bonus: {await db.setting("referral_bonus")} so‘m.'); await call.answer()
@router.callback_query(F.data=='refaccept')
async def refaccept(c:types.CallbackQuery,db:Database,bot:Bot):
    await db.conn.execute('UPDATE users SET rules_accepted=1 WHERE user_id=?',(c.from_user.id,)); await db.conn.commit(); me=await bot.get_me()
    await c.message.answer(f'Referal havolangiz: https://t.me/{me.username}?start=ref_{c.from_user.id}\nHar bir haqiqiy yangi foydalanuvchi uchun bonus: {await db.setting("referral_bonus")} so‘m.'); await c.answer()
@router.callback_query(F.data=='refdecline')
async def refdecline(c:types.CallbackQuery): await c.answer('Referal havolasi berilmadi.')

@router.callback_query(F.data.startswith('claimgift:'))
async def claim_gift(c:types.CallbackQuery,db:Database):
    gid=int(c.data.split(':')[1]); status,g=await db.claim_gift(gid,c.from_user.id)
    if status=='won':
        if g['kind']=='vip': await db.set_vip(c.from_user.id,g['days']); msg=f'Tabriklaymiz! Siz {g["days"]} kunlik VIP sovg‘ani qo‘lga kiritdingiz.'
        else: msg=f'Tabriklaymiz! {g["amount"]:,} so‘m sovg‘a balansingizga qo‘shildi.'
        await c.answer(msg,show_alert=True)
        if g['claimed']+1>=g['winners_limit']:
            winners=await db.gift_winners(gid); lines=['Gift g‘oliblari:']
            for i,w in enumerate(winners,1): lines.append(f'{i}. {w["name"]} | @{w["username"] or "yo‘q"} | {w["user_id"]}')
            await c.bot.send_message(ADMIN_ID,'\n'.join(lines))
    elif status=='vip': await c.answer('Sizda allaqachon faol VIP obuna bor.',show_alert=True)
    elif status=='already': await c.answer('Siz allaqachon o‘z sovg‘angizni oldingiz.',show_alert=True)
    elif status=='late': await c.answer('Afsuski, siz ulgurmadingiz. Keyingi giftda faolroq bo‘ling!',show_alert=True)
    else: await c.answer('Gift faol emas yoki topilmadi.',show_alert=True)

@router.message(F.text=='Bot haqida')
async def about(m:types.Message,db:Database): await m.answer(await db.setting('bot_info'))
@router.message(F.text=='Yordam')
async def help_(m:types.Message,db:Database): await m.answer(f'Yordam uchun: {await db.setting("admin_link")}')

@router.chat_join_request()
async def track_join_request(event:types.ChatJoinRequest,db:Database):
    # Track private-channel join requests made after the bot was added as an admin.
    await db.add_join_request(event.from_user.id,event.chat.id)
