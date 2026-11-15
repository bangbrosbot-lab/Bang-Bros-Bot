import os, shutil, tempfile, datetime
from aiogram import Router,F,types,Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile,InlineKeyboardMarkup,InlineKeyboardButton
from db import Database
from config import ADMIN_ID
from keyboards import admin_menu,desk,settings,id_kb
from states import AddVideo,DeleteVideo,Settings,UserAdmin,Broadcast,Gift
router=Router()
def admin(uid): return uid==ADMIN_ID
class AdminOnly(BaseFilter):
    async def __call__(self,event): return bool(event.from_user and event.from_user.id==ADMIN_ID)
router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())
@router.message(Command('data'))
async def data_cmd(m:types.Message,db:Database):
    if not admin(m.from_user.id): return
    # Use SQLite's online backup API so the exported file is a consistent latest snapshot.
    fd,path=tempfile.mkstemp(prefix='bangbros_backup_',suffix='.db'); os.close(fd)
    import aiosqlite
    async with aiosqlite.connect(path) as dst: await db.conn.backup(dst)
    await m.answer_document(FSInputFile(path,filename='Bang_Bros_bot_latest.db'),caption='Bang Bros — bazaning eng so‘nggi nusxasi')
    os.remove(path)
async def send_id_page(target,db,page,edit=False):
    total=await db.total_users(); pages=max(1,(total+4)//5); page=max(1,min(page,pages)); users=await db.users_page(page,5)
    lines=['Barcha foydalanuvchilar ro‘yxati',f'Jami: {total}','']
    rows=[]
    for u in users:
        lines += [f'Ism: {u["name"] or "Mavjud emas"}',f'User: @{u["username"]}' if u['username'] else 'User: mavjud emas',f'ID: <code>{u["user_id"]}</code>','']
        rows.append([InlineKeyboardButton(text=f'{u["name"] or u["user_id"]} · {u["user_id"]}',callback_data=f'uid:{u["user_id"]}')])
    nav=id_kb(page,pages).inline_keyboard
    rows.extend(nav)
    markup=InlineKeyboardMarkup(inline_keyboard=rows)
    if edit: await target.edit_text('\n'.join(lines).rstrip(),parse_mode='HTML',reply_markup=markup)
    else: await target.answer('\n'.join(lines).rstrip(),parse_mode='HTML',reply_markup=markup)
@router.message(Command('id'))
async def id_cmd(m:types.Message,state:FSMContext,db:Database):
    if not admin(m.from_user.id): return
    await state.clear(); await send_id_page(m,db,1)
@router.callback_query(F.data.startswith('idpage:'))
async def id_page(c:types.CallbackQuery,db:Database):
    if not admin(c.from_user.id): return await c.answer()
    await send_id_page(c.message,db,int(c.data.split(':')[1]),True); await c.answer()
@router.callback_query(F.data=='idhome')
async def id_home(c:types.CallbackQuery):
    if not admin(c.from_user.id): return await c.answer()
    await c.message.delete(); await c.message.answer('Admin panel',reply_markup=admin_menu()); await c.answer()
@router.message(F.text=='Ish stoli')
async def desk_menu(m:types.Message):
    if admin(m.from_user.id): await m.answer('Ish stoli',reply_markup=desk())
@router.message(F.text=='Sozlamalar')
async def settings_menu(m:types.Message):
    if admin(m.from_user.id): await m.answer('Sozlamalar',reply_markup=settings())
@router.message(F.text=='Statistika')
async def stats(m:types.Message,db:Database):
    if not admin(m.from_user.id): return
    s=await db.stats(); await m.answer(f'Jami Foydalanuvchilar: {s["users"]}\nBugun qo‘shilganlar: {s["today"]}\nVip Foydalanuvchilar: {s["vip"]}\nReferral orqali kelganlar: {s["ref"]}\nJami tushgan mablag‘: {s["money"]:,} so‘m\nJami qo‘shilgan videolar: {s["videos"]}')
@router.message(F.text=='Bosh menyu')
async def back(m:types.Message):
    if admin(m.from_user.id): await m.answer('Admin panel',reply_markup=admin_menu())
@router.message(F.text=='Video qo‘shish')
async def add_start(m:types.Message,state:FSMContext):
    if not admin(m.from_user.id): return
    await state.set_state(AddVideo.cover); await m.answer('Post uchun rasm jo‘nating!')
@router.message(AddVideo.cover,F.photo)
async def add_cover(m:types.Message,state:FSMContext): await state.update_data(cover=m.photo[-1].file_id); await state.set_state(AddVideo.caption); await m.answer('Izoh yozing!')
@router.message(AddVideo.caption)
async def add_caption(m:types.Message,state:FSMContext): await state.update_data(caption=m.text or m.caption or ''); await state.set_state(AddVideo.teaser); await m.answer('Qisqa videoni jo‘nating!')
@router.message(AddVideo.teaser,F.video)
async def add_teaser(m:types.Message,state:FSMContext): await state.update_data(teaser=m.video.file_id,qualities={}); await state.set_state(AddVideo.quality); await m.answer('Birinchi sifatni tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=q,callback_data=f'addq:{q}') for q in ('360p','480p')],[InlineKeyboardButton(text=q,callback_data=f'addq:{q}') for q in ('720p','1080p')]]))
@router.callback_query(F.data.startswith('addq:'))
async def choose_q(c:types.CallbackQuery,state:FSMContext): await state.update_data(current_quality=c.data.split(':')[1]); await state.set_state(AddVideo.quality_file); await c.message.answer(f'Endi shu sifatdagi ({c.data.split(":")[1]}) videoni jo‘nating!'); await c.answer()
@router.message(AddVideo.quality_file,F.video)
async def quality_file(m:types.Message,state:FSMContext):
    d=await state.get_data(); qs=d.get('qualities',{}); qs[d['current_quality']]=m.video.file_id; await state.update_data(qualities=qs); await state.set_state(AddVideo.quality)
    remaining=[q for q in ('360p','480p','720p','1080p') if q not in qs]
    rows=[[InlineKeyboardButton(text=q,callback_data=f'addq:{q}') for q in remaining[i:i+2]] for i in range(0,len(remaining),2)]
    rows.append([InlineKeyboardButton(text='Bo‘ldi',callback_data='addq:done')]); await m.answer('Video qabul qilindi, yana boshqa sifat qo‘shasizmi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
@router.callback_query(F.data=='addq:done')
async def add_done(c:types.CallbackQuery,state:FSMContext):
    d=await state.get_data()
    if not d.get('qualities'): return await c.answer('Kamida bitta sifat qo‘shing.',show_alert=True)
    await state.set_state(AddVideo.finish); await c.message.answer('Barcha sifatlar muvaffaqiyatli qo‘shildi. Hammasi tayyormi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='video_save'),InlineKeyboardButton(text='Yo‘q',callback_data='video_cancel')]])); await c.answer()
@router.callback_query(F.data=='video_cancel')
async def video_cancel(c:types.CallbackQuery,state:FSMContext): await state.clear(); await c.message.answer('Video qo‘shish bekor qilindi.',reply_markup=desk()); await c.answer()
@router.callback_query(F.data=='video_save')
async def video_save(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    d=await state.get_data(); special=[x for x in await db.all_channels() if x['kind']=='special']
    if not special: return await c.answer('Avval maxsus kanal qo‘shing.',show_alert=True)
    channel=special[0]['channel_id']; me=await bot.get_me(); cursor=await db.conn.execute('INSERT INTO videos(cover_id,caption,teaser_id,channel_id) VALUES(?,?,?,?)',(d['cover'],d['caption'],d['teaser'],channel)); await db.conn.commit(); vid=cursor.lastrowid
    for q,f in d['qualities'].items(): await db.add_quality(vid,q,f)
    markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Yoqdi',callback_data=f'vote:{vid}:1'),InlineKeyboardButton(text='Yoqmadi',callback_data=f'vote:{vid}:-1')],[InlineKeyboardButton(text='Videoni ko‘rish',url=f'https://t.me/{me.username}?start=video_{vid}')]])
    post=await bot.send_photo(channel,d['cover'],caption=d['caption'],reply_markup=markup); await db.conn.execute('UPDATE videos SET channel_message_id=? WHERE id=?',(post.message_id,vid)); await db.conn.commit()
    await state.clear(); await c.message.answer('Video muvaffaqiyatli qo‘shildi, xo‘jayin.',reply_markup=desk()); await c.answer()
@router.message(F.text=='Video o‘chirish')
async def delete_start(m:types.Message,state:FSMContext):
    if admin(m.from_user.id): await state.set_state(DeleteVideo.link); await m.answer('O‘chirmoqchi bo‘lgan videoning havolasini yuboring!')
@router.message(DeleteVideo.link)
async def delete_link(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    if not admin(m.from_user.id): return
    import re
    text=m.text or ''
    match=re.search(r'start=video_(\d+)',text)
    vid=int(match.group(1)) if match else None
    if vid is None:
        # Telegram channel post URL ends with its message ID, not the bot's video ID.
        post_match=re.search(r't\.me/(?:c/\d+|[A-Za-z0-9_]+)/([0-9]+)',text)
        if post_match:
            post_id=int(post_match.group(1))
            cur=await db.conn.execute('SELECT id FROM videos WHERE channel_message_id=?',(post_id,)); found=await cur.fetchone()
            if found: vid=found['id']
        elif text.strip().isdigit(): vid=int(text.strip())
    if not vid: return await m.answer('Video havolasi noto‘g‘ri yoki bu post bazadan topilmadi.')
    v=await db.video(vid)
    if not v: await state.clear(); return await m.answer('Video topilmadi.')
    try: await bot.delete_message(v['channel_id'],v['channel_message_id'])
    except Exception: pass
    await db.delete_video(vid); await state.clear(); await m.answer('Video o‘chirildi.',reply_markup=desk())
# Settings: retain prior behavior for edit forms, but use Bang Bros labels.
@router.message(F.text=='Karta edit')
async def card_edit(m:types.Message,state:FSMContext,db:Database):
    if admin(m.from_user.id): await state.set_state(Settings.card); await m.answer(f'Hozirgi karta: {await db.setting("card")}\nYangi karta raqamini yuboring!')
@router.message(Settings.card)
async def card_save(m:types.Message,state:FSMContext,db:Database): await db.set_setting('card',m.text.strip()); await state.clear(); await m.answer('Karta raqami yangilandi.')
@router.message(F.text=='Info edit')
async def info_edit(m:types.Message,state:FSMContext,db:Database):
    if admin(m.from_user.id): await state.set_state(Settings.info); await m.answer(f'Hozirgi ma’lumot:\n{await db.setting("bot_info")}\n\nYangi ma’lumotni yuboring!')
@router.message(Settings.info)
async def info_save(m:types.Message,state:FSMContext,db:Database): await db.set_setting('bot_info',m.text); await state.clear(); await m.answer('Bot ma’lumoti yangilandi.')
@router.message(F.text=='Referral edit')
async def ref_edit(m:types.Message,state:FSMContext,db:Database):
    if admin(m.from_user.id): await state.set_state(Settings.referral); await m.answer(f'Hozirgi referral bonusi: {await db.setting("referral_bonus")} so‘m. Yangi miqdorni yuboring!')
@router.message(Settings.referral)
async def ref_save(m:types.Message,state:FSMContext,db:Database):
    try: n=int(m.text)
    except: return await m.answer('Faqat raqam yuboring.')
    await db.set_setting('referral_bonus',n); await state.clear(); await m.answer('Referral bonusi yangilandi.')
@router.message(F.text=='Admin link edit')
async def link_edit(m:types.Message,state:FSMContext,db:Database):
    if admin(m.from_user.id): await state.set_state(Settings.admin_link); await m.answer(f'Hozirgi admin havolasi: {await db.setting("admin_link")}\nYangisini yuboring!')
@router.message(Settings.admin_link)
async def link_save(m:types.Message,state:FSMContext,db:Database): await db.set_setting('admin_link',m.text.strip()); await state.clear(); await m.answer('Admin havolasi yangilandi.')
@router.message(F.text=='Kanallar')
async def channels(m:types.Message):
    if admin(m.from_user.id): await m.answer('Kanallar bo‘limidasiz.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Majburiy kanal qo‘shish',callback_data='add_mand')],[InlineKeyboardButton(text='Maxsus kanal qo‘shish',callback_data='add_special')],[InlineKeyboardButton(text='Kanal o‘chirish',callback_data='del_channel')]]))
@router.callback_query(F.data=='add_mand')
async def add_mand(c:types.CallbackQuery,state:FSMContext): await state.set_state(Settings.mandatory_channel); await c.message.answer('Kanal ID sini va qo‘shilish havolasini quyidagi ko‘rinishda yuboring:\nID | https://t.me/...\nMaxfiy kanal uchun invite link yuboring.'); await c.answer()
@router.message(Settings.mandatory_channel)
async def mand_save(m:types.Message,state:FSMContext,db:Database):
    try: cid,url=m.text.split('|',1); await db.add_channel(int(cid.strip()),'mandatory',url.strip()); await state.clear(); await m.answer('Majburiy kanal qo‘shildi.')
    except: await m.answer('Format noto‘g‘ri. ID | havola ko‘rinishida yuboring.')
@router.callback_query(F.data=='add_special')
async def special_start(c:types.CallbackQuery,state:FSMContext): await state.set_state(Settings.special_channel); await c.message.answer('Botni kanalga admin qilib tayinlang va kanal ID sini jo‘nating!'); await c.answer()
@router.message(Settings.special_channel)
async def special_save(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    try:
        cid=int(m.text.strip()); chat=await bot.get_chat(cid); me=await bot.get_me(); member=await bot.get_chat_member(cid,me.id)
        if member.status!='administrator': return await m.answer('Bot kanalda admin emas. Avval admin qiling.')
        await db.add_channel(cid,'special'); await state.clear(); await m.answer('Maxsus kanal qo‘shildi.')
    except: await m.answer('Kanal ID sini tekshiring va botga admin huquqini bering.')
@router.callback_query(F.data=='del_channel')
async def del_channels(c:types.CallbackQuery,db:Database):
    ch=await db.all_channels(); rows=[[InlineKeyboardButton(text=f'{x["kind"]}: {x["channel_id"]}',callback_data=f'delch:{x["channel_id"]}')] for x in ch]
    if not rows: return await c.answer('Kanallar ro‘yxati bo‘sh.',show_alert=True)
    await c.message.answer('O‘chirish uchun kanalni tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()
@router.callback_query(F.data.startswith('delch:'))
async def del_channel_ask(c:types.CallbackQuery):
    cid=int(c.data.split(':')[1]); await c.message.answer(f'{cid} kanalini o‘chirishni xohlaysizmi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=f'delchyes:{cid}'),InlineKeyboardButton(text='Yo‘q',callback_data='delchno')]])); await c.answer()
@router.callback_query(F.data.startswith('delchyes:'))
async def del_channel_yes(c:types.CallbackQuery,db:Database):
    await db.delete_channel(int(c.data.split(':')[1])); await c.message.edit_text('Kanal o‘chirildi.'); await c.answer('Kanal o‘chirildi.')
@router.callback_query(F.data=='delchno')
async def del_channel_no(c:types.CallbackQuery): await c.message.edit_text('Kanal o‘chirish bekor qilindi.'); await c.answer()

# --- To'lovlarni tasdiqlash ---
@router.callback_query(F.data.startswith('topupok:'))
async def topup_approve(c:types.CallbackQuery,db:Database,bot:Bot):
    rid=int(c.data.split(':')[1]); r=await db.approve_topup(rid)
    if not r: return await c.answer('Bu so‘rov avval ko‘rib chiqilgan.',show_alert=True)
    await bot.send_message(r['user_id'],f'Hisobingiz {r["amount"]:,} so‘mga to‘ldirildi.'); await c.message.edit_caption((c.message.caption or '')+'\n\nTasdiqlandi'); await c.answer('To‘lov tasdiqlandi.')
@router.callback_query(F.data.startswith('topupno:'))
async def topup_reject(c:types.CallbackQuery,db:Database,bot:Bot):
    rid=int(c.data.split(':')[1]); r=await db.reject_topup(rid)
    if not r: return await c.answer('Bu so‘rov avval ko‘rib chiqilgan.',show_alert=True)
    await bot.send_message(r['user_id'],'To‘lov chekingiz rad etildi. Iltimos, chekni tekshirib qayta yuboring.'); await c.message.edit_caption((c.message.caption or '')+'\n\nRad etildi'); await c.answer('So‘rov rad etildi.')

# --- VIP tariflarini tahrirlash ---
@router.message(F.text=='VIP edit')
async def vip_edit_full(m:types.Message,db:Database):
    if not admin(m.from_user.id): return
    rows=[]
    for d,label in [(1,'1 kunlik'),(7,'1 haftalik'),(30,'1 oylik')]: rows.append([InlineKeyboardButton(text=f'{label}: {int(await db.setting("vip_"+str(d))):,} so‘m',callback_data=f'vipprice:{d}')])
    await m.answer('O‘zgartirmoqchi bo‘lgan VIP tarifini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
@router.callback_query(F.data.startswith('vipprice:'))
async def vipprice_choose(c:types.CallbackQuery,state:FSMContext):
    d=int(c.data.split(':')[1]); await state.update_data(vip_days=d); await state.set_state(Settings.vip_price); await c.message.answer('Yangi narxni so‘mda yuboring:'); await c.answer()
@router.message(Settings.vip_price)
async def vipprice_save(m:types.Message,state:FSMContext,db:Database):
    try: n=int(m.text.strip()); assert n>0
    except: return await m.answer('Narxni musbat raqam bilan yuboring.')
    d=(await state.get_data())['vip_days']; await db.set_setting('vip_'+str(d),n); await state.clear(); await m.answer('VIP tarifi yangilandi.')

# --- Foydalanuvchilarni boshqarish ---
@router.message(F.text=='Foydalanuvchilar')
async def users_menu(m:types.Message,state:FSMContext):
    if admin(m.from_user.id): await state.set_state(UserAdmin.user_id); await m.answer('Boshqarish uchun foydalanuvchi ID sini yuboring:')
@router.message(UserAdmin.user_id)
async def user_lookup(m:types.Message,state:FSMContext,db:Database):
    try: uid=int(m.text.strip())
    except: return await m.answer('ID faqat raqamlardan iborat bo‘lishi kerak.')
    u=await db.user(uid)
    if not u: return await m.answer('Foydalanuvchi topilmadi.')
    await state.clear(); await show_user(m,db,u)
async def show_user(target,db,u,edit=False):
    vip=await db.vip(u['user_id']); friends=await db.referrals_count(u['user_id'])
    text=(f'Foydalanuvchi ma’lumotlari\n\nIsm: {u["name"] or "—"}\nUsername: @{u["username"] or "mavjud emas"}\nID: {u["user_id"]}\nBalans: {u["balance"]:,} so‘m\nHolati: {"VIP" if vip else "Oddiy"}\nVIP muddati: {u["vip_until"] or "—"}\nDo‘stlar: {friends}\nBloklangan: {"Ha" if u["blocked"] else "Yo‘q"}')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Balans qo‘shish',callback_data=f'uadd:{u["user_id"]}'),InlineKeyboardButton(text='Balans ayirish',callback_data=f'usub:{u["user_id"]}')],[InlineKeyboardButton(text='VIP berish',callback_data=f'uvip:{u["user_id"]}'),InlineKeyboardButton(text='VIP bekor qilish',callback_data=f'urevoke:{u["user_id"]}')],[InlineKeyboardButton(text='Bloklash' if not u['blocked'] else 'Blokdan chiqarish',callback_data=f'ublock:{u["user_id"]}')],[InlineKeyboardButton(text='Xabar yuborish',callback_data=f'umsg:{u["user_id"]}')]])
    if edit: await target.edit_text(text,reply_markup=kb)
    else: await target.answer(text,reply_markup=kb)
@router.callback_query(F.data.regexp(r'^u(add|sub|vip|msg|block|revoke):'))
async def user_action(c:types.CallbackQuery,state:FSMContext,db:Database):
    action,uid=c.data.split(':'); uid=int(uid); await state.update_data(target_uid=uid,action=action)
    if action=='revoke': await db.revoke_vip(uid); await c.answer('VIP bekor qilindi.'); return await show_user(c.message,db,await db.user(uid),True)
    if action=='block':
        u=await db.user(uid); await db.conn.execute('UPDATE users SET blocked=? WHERE user_id=?',(0 if u['blocked'] else 1,uid)); await db.conn.commit(); await c.answer('Holat o‘zgartirildi.');
        try: await c.bot.send_message(uid,'Botdan foydalanish huquqingiz administrator tomonidan cheklangan.' if not u['blocked'] else 'Blokdan chiqarildingiz.')
        except: pass
        return await show_user(c.message,db,await db.user(uid),True)
    prompts={'add':'Qo‘shiladigan summani yuboring:','sub':'Ayiriladigan summani yuboring:','vip':'VIP muddati: 1, 7 yoki 30 kun yuboring:','msg':'Foydalanuvchiga yuboriladigan xabarni yozing:'}
    await state.set_state(UserAdmin.add_amount if action in ('add','sub','vip') else UserAdmin.message); await c.message.answer(prompts[action]); await c.answer()
@router.message(UserAdmin.add_amount)
async def user_amount(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    d=await state.get_data(); action=d['action']; uid=d['target_uid']
    try: n=int(m.text.strip()); assert n>0
    except: return await m.answer('Musbat raqam yuboring.')
    if action=='vip':
        if n not in (1,7,30): return await m.answer('Faqat 1, 7 yoki 30 kun kiriting.')
        expiry=await db.set_vip(uid,n); notice=f'Sizga {n} kunlik VIP obuna berildi. Amal qilish muddati: {expiry:%d.%m.%Y %H:%M}'
    else:
        delta=n if action=='add' else -n
        await db.conn.execute('UPDATE users SET balance=MAX(0,balance+?) WHERE user_id=?',(delta,uid)); await db.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(uid,delta,'admin_adjust')); await db.conn.commit(); notice=f'Balansingiz {n:,} so‘mga {"oshirildi" if action=="add" else "kamaytirildi"}.'
    try: await bot.send_message(uid,notice)
    except: pass
    await state.clear(); await m.answer('Amal bajarildi.'); await show_user(m,db,await db.user(uid))
@router.message(UserAdmin.message)
async def user_message(m:types.Message,state:FSMContext,bot:Bot):
    uid=(await state.get_data())['target_uid']
    try: await m.copy_to(uid); await m.answer('Xabar yuborildi.')
    except: await m.answer('Xabar yuborilmadi.')
    await state.clear()

# --- Reklama tarqatish: yuborilgan xabar formatini saqlaydi ---
@router.message(F.text=='Reklama jo‘natish')
async def broadcast_start(m:types.Message,state:FSMContext):
    if admin(m.from_user.id): await state.set_state(Broadcast.content); await m.answer('Reklama matni, rasm, video, GIF yoki audio yuboring. Xabar matni/caption va format saqlanadi.')
@router.message(Broadcast.content)
async def broadcast_content(m:types.Message,state:FSMContext):
    await state.update_data(source_chat=m.chat.id,source_message=m.message_id,ad_button=None)
    await m.answer('Reklamaga tugma qo‘shasizmi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Tugma qo‘shish',callback_data='bcadd'),InlineKeyboardButton(text='Reklama tayyor',callback_data='bcdone')],[InlineKeyboardButton(text='Reklamani bekor qilish',callback_data='bccancel')]]))
@router.callback_query(F.data=='bcadd')
async def broadcast_add_button(c:types.CallbackQuery,state:FSMContext):
    await state.set_state(Broadcast.button_name); await c.message.answer('Tugma nomini yuboring:'); await c.answer()
@router.message(Broadcast.button_name)
async def broadcast_button_name(m:types.Message,state:FSMContext):
    if not m.text: return await m.answer('Tugma nomini matn ko‘rinishida yuboring.')
    await state.update_data(button_name=m.text.strip()); await state.set_state(Broadcast.button_url); await m.answer('Tugma ochadigan havolani yuboring (https://...):')
@router.message(Broadcast.button_url)
async def broadcast_button_url(m:types.Message,state:FSMContext):
    url=(m.text or '').strip()
    if not (url.startswith('https://') or url.startswith('http://') or url.startswith('tg://')): return await m.answer('To‘g‘ri havola yuboring.')
    d=await state.get_data(); await state.update_data(ad_button=(d['button_name'],url)); await state.set_state(Broadcast.audience)
    await m.answer('Tugma qo‘shildi. Kimlarga yuborilsin?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Barchaga',callback_data='ba:all')],[InlineKeyboardButton(text='VIP',callback_data='ba:vip'),InlineKeyboardButton(text='Oddiy',callback_data='ba:ordinary')],[InlineKeyboardButton(text='Maxsus kanal',callback_data='ba:special')],[InlineKeyboardButton(text='Bekor qilish',callback_data='ba:cancel')]]))
@router.callback_query(F.data=='bcdone')
async def broadcast_done(c:types.CallbackQuery,state:FSMContext):
    await state.set_state(Broadcast.audience); await c.message.answer('Kimlarga yuborilsin?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Barchaga',callback_data='ba:all')],[InlineKeyboardButton(text='VIP',callback_data='ba:vip'),InlineKeyboardButton(text='Oddiy',callback_data='ba:ordinary')],[InlineKeyboardButton(text='Maxsus kanal',callback_data='ba:special')],[InlineKeyboardButton(text='Bekor qilish',callback_data='ba:cancel')]])); await c.answer()
@router.callback_query(F.data=='bccancel')
async def broadcast_cancel(c:types.CallbackQuery,state:FSMContext):
    await state.clear(); await c.message.answer('Reklama bekor qilindi.',reply_markup=desk()); await c.answer()
@router.callback_query(F.data.startswith('ba:'))
async def broadcast_prepare(c:types.CallbackQuery,state:FSMContext):
    mode=c.data.split(':')[1]
    if mode=='cancel': await state.clear(); return await c.message.answer('Reklama bekor qilindi.',reply_markup=desk())
    await state.update_data(audience=mode)
    await c.message.answer('Reklama jo‘natishga tayyor. Jo‘natilsinmi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='basend:yes'),InlineKeyboardButton(text='Yo‘q',callback_data='basend:no')]]))
    await c.answer()
@router.callback_query(F.data.startswith('basend:'))
async def broadcast_send(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    if c.data.endswith('no'):
        await state.clear(); await c.message.answer('Reklama bekor qilindi.',reply_markup=desk()); return await c.answer()
    d=await state.get_data(); await state.clear(); mode=d.get('audience','all')
    markup=None
    if d.get('ad_button'):
        label,url=d['ad_button']; markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label,url=url)]])
    if mode=='special':
        ch=next((x for x in await db.all_channels() if x['kind']=='special'),None)
        if not ch: return await c.answer('Maxsus kanal sozlanmagan.',show_alert=True)
        try: await bot.copy_message(ch['channel_id'],d['source_chat'],d['source_message'],reply_markup=markup); await c.message.answer('Reklama maxsus kanalga yuborildi.')
        except Exception as e: await c.message.answer(f'Yuborilmadi: {e}')
        return await c.answer()
    ids=await db.all_user_ids(mode); ok=bad=0
    for uid in ids:
        try: await bot.copy_message(uid,d['source_chat'],d['source_message'],reply_markup=markup); ok+=1
        except: bad+=1
    await c.message.answer(f'Reklama tarqatish yakunlandi.\nJami: {len(ids)}\nYuborildi: {ok}\nYuborilmadi: {bad}')
    await c.answer()

# --- Gift tarqatish ---
@router.message(F.text=='Gift o‘tkazish')
async def gift_start(m:types.Message,state:FSMContext):
    if admin(m.from_user.id): await state.set_state(Gift.gift_type); await m.answer('Gift turini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Pul tarqatish',callback_data='giftkind:money')],[InlineKeyboardButton(text='VIP tarqatish',callback_data='giftkind:vip')]]))
@router.callback_query(F.data.startswith('giftkind:'))
async def gift_kind(c:types.CallbackQuery,state:FSMContext):
    kind=c.data.split(':')[1]; await state.update_data(gift_kind=kind)
    if kind=='vip':
        await state.set_state(Gift.tariff); await c.message.answer('VIP muddatini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='1 kun',callback_data='giftdays:1'),InlineKeyboardButton(text='7 kun',callback_data='giftdays:7'),InlineKeyboardButton(text='30 kun',callback_data='giftdays:30')]]))
    else: await state.set_state(Gift.amount); await c.message.answer('Har bir g‘olib oladigan pul miqdorini yuboring (so‘m):')
    await c.answer()
@router.callback_query(F.data.startswith('giftdays:'))
async def gift_days(c:types.CallbackQuery,state:FSMContext):
    await state.update_data(gift_days=int(c.data.split(':')[1])); await state.set_state(Gift.winners); await c.message.answer('Nechta g‘olib bo‘lishini yuboring:'); await c.answer()
@router.message(Gift.amount)
async def gift_amount(m:types.Message,state:FSMContext):
    try: n=int(m.text); assert n>0
    except: return await m.answer('Musbat summa kiriting.')
    await state.update_data(gift_amount=n); await state.set_state(Gift.winners); await m.answer('Nechta g‘olib bo‘lishini yuboring:')
@router.message(Gift.winners)
async def gift_winners_count(m:types.Message,state:FSMContext):
    try: n=int(m.text); assert n>0
    except: return await m.answer('Musbat son kiriting.')
    await state.update_data(gift_winners=n); d=await state.get_data(); await state.set_state(Gift.confirm)
    desc=(f'{d.get("gift_amount",0):,} so‘m' if d['gift_kind']=='money' else f'{d["gift_days"]} kunlik VIP')
    await m.answer(f'Gift: {desc}\nG‘oliblar: {n} ta\nTasdiqlaysizmi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='giftconfirm:yes'),InlineKeyboardButton(text='Yo‘q',callback_data='giftconfirm:no')]]))
@router.callback_query(F.data.startswith('giftconfirm:'))
async def gift_confirm(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    if c.data.endswith('no'): await state.clear(); await c.message.answer('Gift bekor qilindi.',reply_markup=desk()); return await c.answer()
    d=await state.get_data(); kind=d['gift_kind']; gid=await db.create_gift(kind,d.get('gift_amount',0),d.get('gift_days',0),d['gift_winners'])
    if kind=='money': body=f'Adminlar obunachilar uchun tekinga {d["gift_amount"]:,} so‘m pul sovg‘a qilishmoqda. Shoshiling! Sovg‘a faqatgina {d["gift_winners"]} odamga nasib qiladi, omadingizni qo‘ldan chiqarmang!'
    else: body=f'{d["gift_days"]} kunlik VIP sovg‘a! Sovg‘a faqat {d["gift_winners"]} nafar oddiy foydalanuvchiga beriladi. Shoshiling!'
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Sovg‘ani olish',callback_data=f'claimgift:{gid}')]])
    ids=await db.all_user_ids('ordinary' if kind=='vip' else 'all'); ok=0
    for uid in ids:
        try: await bot.send_message(uid,body,reply_markup=kb); ok+=1
        except: pass
    await state.clear(); await c.message.answer(f'Gift e’lon qilindi. Yetkazildi: {ok} ta foydalanuvchi.',reply_markup=desk()); await c.answer()

# Non-admin callback for claiming gift is handled by public router registered in main.

@router.callback_query(F.data.startswith('uid:'))
async def id_user_profile(c:types.CallbackQuery,db:Database):
    u=await db.user(int(c.data.split(':')[1]))
    if not u: return await c.answer('Foydalanuvchi topilmadi.',show_alert=True)
    await show_user(c.message,db,u); await c.answer()
