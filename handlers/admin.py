import os, shutil, tempfile, datetime
from aiogram import Router,F,types,Bot
from aiogram.filters import Command, BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile,InlineKeyboardMarkup,InlineKeyboardButton
from db import Database
from config import ADMIN_ID
from keyboards import admin_menu,limited_admin_menu,desk,settings as settings_kb,id_kb
from states import AddVideo,DeleteVideo,Settings,UserAdmin,Broadcast,Gift
router=Router()
ACTIVE_ADMINS={ADMIN_ID}
def admin(uid): return uid in ACTIVE_ADMINS
async def _db_admin(m):
    try: return await m.bot.get_chat_member(m.chat.id, m.from_user.id) and (m.from_user.id in ACTIVE_ADMINS)
    except Exception: return m.from_user.id in ACTIVE_ADMINS
PERMISSIONS={'edit':'Edit imkoniyatlari','payments':'Chek tasdiqlash','admin_manage':'Admin qilish/olish','users':'Foydalanuvchilarni ko‘rish'}
async def has_permission(db, uid, permission):
    if uid==ADMIN_ID: return True
    perms=await db.admin_permissions(uid)
    return bool(perms is not None and permission in perms)
class AdminOnly(BaseFilter):
    async def __call__(self,event,db:Database):
        return bool(event.from_user and (event.from_user.id==ADMIN_ID or await db.is_admin(event.from_user.id)))
router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())
MENU_TEXTS={'Ish stoli','Sozlamalar','Bosh menyu','Video qo‘shish','Video o‘chirish','Reklama jo‘natish','Gift o‘tkazish','Statistika','Kanallar','Foydalanuvchilar','Karta edit','VIP edit','Info edit','Referral edit','Admin link edit'}
@router.message(StateFilter(AddVideo.cover,AddVideo.caption,AddVideo.teaser,AddVideo.quality,AddVideo.quality_file,AddVideo.finish,DeleteVideo.link,Settings.card,Settings.vip_price,Settings.info,Settings.referral,Settings.admin_link,Settings.mandatory_channel,Settings.special_channel,UserAdmin.user_id,UserAdmin.add_amount,UserAdmin.subtract_amount,UserAdmin.message,UserAdmin.admin_permissions,UserAdmin.reject_reason,UserAdmin.confirm_balance,Broadcast.content, Broadcast.like_layout,Broadcast.button_name,Broadcast.button_url,Broadcast.audience,Gift.gift_type,Gift.tariff,Gift.amount,Gift.winners,Gift.confirm),F.text.in_(MENU_TEXTS))
async def interrupt_admin_action(m:types.Message,state:FSMContext,db:Database):
    await state.clear()
    text=m.text
    if text=='Ish stoli':
        if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return await m.answer('Bu bo‘limdan foydalanish huquqingiz yo‘q.')
        return await m.answer('Ish stoli',reply_markup=desk())
    if text=='Sozlamalar': return await m.answer('Sozlamalar',reply_markup=settings_kb())
    if text=='Bosh menyu': return await m.answer('Admin panel',reply_markup=admin_menu())
    if text=='Video qo‘shish':
        if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return await m.answer('Bu bo‘limdan foydalanish huquqingiz yo‘q.')
        await state.set_state(AddVideo.cover); return await m.answer('Post uchun rasm jo‘nating!')
    if text=='Video o‘chirish':
        if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return await m.answer('Bu bo‘limdan foydalanish huquqingiz yo‘q.')
        await state.set_state(DeleteVideo.link); return await m.answer('O‘chirmoqchi bo‘lgan videoning havolasini yuboring!')
    if text=='Reklama jo‘natish':
        if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return await m.answer('Bu bo‘limdan foydalanish huquqingiz yo‘q.')
        await state.set_state(Broadcast.content); return await m.answer('Reklama matni, rasm, video, GIF yoki audio yuboring.')
    if text=='Gift o‘tkazish':
        if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return await m.answer('Bu bo‘limdan foydalanish huquqingiz yo‘q.')
        await state.set_state(Gift.gift_type); return await m.answer('Gift turini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Pul tarqatish',callback_data='giftkind:money')],[InlineKeyboardButton(text='VIP tarqatish',callback_data='giftkind:vip')]]))
    if text=='Statistika': return await stats(m,db)
    if text=='Kanallar':
        if m.from_user.id!=ADMIN_ID: return await m.answer('Bu bo‘limdan foydalanish huquqingiz yo‘q.')
        return await m.answer('Kanallar bo‘limidasiz.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Majburiy kanal qo‘shish',callback_data='add_mand')],[InlineKeyboardButton(text='Maxsus kanal qo‘shish',callback_data='add_special')],[InlineKeyboardButton(text='Kanal o‘chirish',callback_data='del_channel')]]))
    if text=='Foydalanuvchilar':
        if not await has_permission(db,m.from_user.id,'users'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish')
        await state.set_state(UserAdmin.user_id); return await m.answer('Boshqarish uchun foydalanuvchi ID sini yuboring:')
    if text=='Karta edit':
        if not await has_permission(db,m.from_user.id,'edit'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
        await state.set_state(Settings.card); return await m.answer('Yangi karta raqamini yuboring!')
    if text=='VIP edit': return await vip_edit_full(m,db)
    if text=='Info edit':
        if not await has_permission(db,m.from_user.id,'edit'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
        await state.set_state(Settings.info); return await m.answer('Rasm va matn yoki video va matn yuboring!')
    if text=='Referral edit':
        if not await has_permission(db,m.from_user.id,'edit'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
        await state.set_state(Settings.referral); return await m.answer('Yangi referral bonus miqdorini yuboring!')
    if text=='Admin link edit':
        if not await has_permission(db,m.from_user.id,'edit'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
        await state.set_state(Settings.admin_link); return await m.answer('Yangi admin havolasini yuboring!')

@router.message(Command('data'))
async def data_cmd(m:types.Message,db:Database):
    if m.from_user.id!=ADMIN_ID: return
    # Use SQLite's online backup API so the exported file is a consistent latest snapshot.
    fd,path=tempfile.mkstemp(prefix='bangbros_backup_',suffix='.db'); os.close(fd)
    import aiosqlite
    async with aiosqlite.connect(path) as dst: await db.conn.backup(dst)
    await m.answer_document(FSInputFile(path,filename='Bang_Bros_bot_latest.db'),caption='Bang Bros — bazaning eng so‘nggi nusxasi', protect_content=True)
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
    if edit: await target.edit_text('\n'.join(lines).rstrip(),parse_mode='HTML',reply_markup=markup,protect_content=True)
    else: await target.answer('\n'.join(lines).rstrip(),parse_mode='HTML',reply_markup=markup,protect_content=True)
@router.message(Command('id'))
async def id_cmd(m:types.Message,state:FSMContext,db:Database):
    if not await has_permission(db,m.from_user.id,'users'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish')
    await state.clear(); await send_id_page(m,db,1)
@router.callback_query(F.data.startswith('idpage:'))
async def id_page(c:types.CallbackQuery,db:Database):
    if not await has_permission(db,c.from_user.id,'users'): return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish',show_alert=True)
    await send_id_page(c.message,db,int(c.data.split(':')[1]),True); await c.answer()
@router.callback_query(F.data=='idhome')
async def id_home(c:types.CallbackQuery,db:Database):
    if not await has_permission(db,c.from_user.id,'users'): return await c.answer('Foydalanuvchilarni ko‘rish huquqi kerak.',show_alert=True)
    menu=admin_menu()
    await c.message.delete(); await c.message.answer('Admin panel',reply_markup=menu); await c.answer()
@router.message(F.text=='Ish stoli')
async def desk_menu(m:types.Message,db:Database):
    if m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id): await m.answer('Ish stoli',reply_markup=desk())
@router.message(F.text=='Sozlamalar')
async def settings_menu(m:types.Message,db:Database):
    if m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id): await m.answer('Sozlamalar',reply_markup=settings_kb())
@router.message(F.text=='Statistika')
async def stats(m:types.Message,db:Database):
    if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return
    s=await db.stats(); await m.answer(f'Jami Foydalanuvchilar: {s["users"]}\nBugun qo‘shilganlar: {s["today"]}\nVip Foydalanuvchilar: {s["vip"]}\nReferral orqali kelganlar: {s["ref"]}\nJami tushgan mablag‘: {s["money"]:,} so‘m\nJami qo‘shilgan videolar: {s["videos"]}')
@router.message(F.text=='Bosh menyu')
async def back(m:types.Message,db:Database):
    if m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id): await m.answer('Admin panel',reply_markup=admin_menu())
async def edit_or_send_prompt(target,state,text,reply_markup=None):
    data=await state.get_data(); mid=data.get('prompt_id'); chat_id=data.get('prompt_chat_id')
    if mid and chat_id:
        try:
            msg=await target.bot.edit_message_text(text,chat_id=chat_id,message_id=mid,reply_markup=reply_markup)
            return msg
        except Exception:
            pass
    msg=await target.answer(text,reply_markup=reply_markup)
    await state.update_data(prompt_id=msg.message_id,prompt_chat_id=msg.chat.id)
    return msg

async def delete_user_input(m):
    try: await m.delete()
    except Exception: pass

async def finish_prompt(target,state,text,reply_markup=None):
    data=await state.get_data(); mid=data.get('prompt_id'); chat_id=data.get('prompt_chat_id')
    if mid and chat_id:
        try: await target.bot.edit_message_text(text,chat_id=chat_id,message_id=mid,reply_markup=reply_markup)
        except Exception: await target.answer(text,reply_markup=reply_markup)
    else: await target.answer(text,reply_markup=reply_markup)
    await state.clear()

@router.message(F.text=='Video qo‘shish')
async def add_start(m:types.Message,state:FSMContext,db:Database):
    if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return
    await state.clear(); await state.set_state(AddVideo.cover)
    await edit_or_send_prompt(m,state,'Post uchun rasm jo‘nating!')

@router.message(AddVideo.cover,F.photo)
async def add_cover(m:types.Message,state:FSMContext):
    await state.update_data(cover=m.photo[-1].file_id); await state.set_state(AddVideo.caption); await delete_user_input(m)
    await edit_or_send_prompt(m,state,'Izoh yozing!')

@router.message(AddVideo.caption)
async def add_caption(m:types.Message,state:FSMContext):
    if not (m.text or m.caption): return await m.answer('Izohni matn ko‘rinishida yuboring!')
    caption_text=m.text or m.caption or ''
    if len(caption_text)>900: return await m.answer('Izoh 900 belgidan oshmasligi kerak. Qisqaroq izoh yuboring!')
    await state.update_data(caption=caption_text); await state.set_state(AddVideo.teaser); await delete_user_input(m)
    await edit_or_send_prompt(m,state,'Qisqa videoni jo‘nating!')

@router.message(AddVideo.teaser,F.video)
async def add_teaser(m:types.Message,state:FSMContext):
    await state.update_data(teaser=m.video.file_id,qualities={}); await state.set_state(AddVideo.quality); await delete_user_input(m)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=q,callback_data=f'addq:{q}') for q in ('360p','480p')],[InlineKeyboardButton(text=q,callback_data=f'addq:{q}') for q in ('720p','1080p')]])
    await edit_or_send_prompt(m,state,'Birinchi sifatni tanlang:',kb)

@router.callback_query(F.data.startswith('addq:') & (F.data != 'addq:done'))
async def choose_q(c:types.CallbackQuery,state:FSMContext):
    q=c.data.split(':',1)[1]
    await state.update_data(current_quality=q); await state.set_state(AddVideo.quality_file)
    await edit_or_send_prompt(c.message,state,f'Endi shu sifatdagi ({q}) videoni jo‘nating!')
    await c.answer()

@router.message(AddVideo.quality_file,F.video)
async def quality_file(m:types.Message,state:FSMContext):
    d=await state.get_data(); qs=d.get('qualities',{}); qs[d['current_quality']]=m.video.file_id
    await state.update_data(qualities=qs); await state.set_state(AddVideo.quality); await delete_user_input(m)
    remaining=[q for q in ('360p','480p','720p','1080p') if q not in qs]
    rows=[[InlineKeyboardButton(text=q,callback_data=f'addq:{q}') for q in remaining[i:i+2]] for i in range(0,len(remaining),2)]
    rows.append([InlineKeyboardButton(text='Bo‘ldi',callback_data='addq:done')])
    await edit_or_send_prompt(m,state,'Video qabul qilindi, yana boshqa sifat qo‘shasizmi?',InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data=='addq:done')
async def add_done(c:types.CallbackQuery,state:FSMContext):
    d=await state.get_data()
    if not d.get('qualities'): return await c.answer('Kamida bitta sifat qo‘shing.',show_alert=True)
    await state.set_state(AddVideo.finish)
    await edit_or_send_prompt(c.message,state,'Barcha sifatlar muvaffaqiyatli qo‘shildi. Hammasi tayyormi?',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='video_save'),InlineKeyboardButton(text='Yo‘q',callback_data='video_cancel')]]))
    await c.answer()

@router.callback_query(F.data=='video_cancel')
async def video_cancel(c:types.CallbackQuery,state:FSMContext):
    await state.clear(); await state.update_data(prompt_id=c.message.message_id,prompt_chat_id=c.message.chat.id); await state.set_state(AddVideo.cover)
    await c.message.edit_text('Yangi video qo‘shish boshlandi. Post uchun rasm jo‘nating!'); await c.answer()

@router.callback_query(F.data=='video_save')
async def video_save(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    d=await state.get_data(); special=[x for x in await db.all_channels() if x['kind']=='special']
    if not special: return await c.answer('Avval maxsus kanal qo‘shing.',show_alert=True)
    channel=special[0]['channel_id']; me=await bot.get_me()
    cursor=await db.conn.execute('INSERT INTO videos(cover_id,caption,teaser_id,channel_id) VALUES(?,?,?,?)',(d['cover'],d['caption'],d['teaser'],channel)); await db.conn.commit(); vid=cursor.lastrowid
    for q,f in d['qualities'].items(): await db.add_quality(vid,q,f)
    caption=__import__('html').escape(d['caption'])+'\n\nYoqimli tomosha tilaymiz! Kanalimizdan uzoqlashmang: <a href="https://t.me/Bangbros_studio">Bang Bros</a>'
    markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Yoqdi (0)',callback_data=f'vote:{vid}:1'),InlineKeyboardButton(text='Yoqmadi (0)',callback_data=f'vote:{vid}:-1')],[InlineKeyboardButton(text='Videoni ko‘rish',url=f'https://t.me/{me.username}?start=video_{vid}')]])
    try:
        post=await bot.send_photo(channel,d['cover'],caption=caption,parse_mode='HTML',reply_markup=markup,protect_content=True)
    except Exception as e:
        await db.delete_video(vid)
        return await c.answer(f'Kanalga post yuborilmadi: {e}',show_alert=True)
    await db.conn.execute('UPDATE videos SET channel_message_id=? WHERE id=?',(post.message_id,vid)); await db.conn.commit()
    await state.clear()
    try: await c.message.edit_text('Video muvaffaqiyatli qo‘shildi.')
    except Exception: pass
    await c.message.answer('Ish stoli',reply_markup=desk()); await c.answer()

@router.message(F.text=='Video o‘chirish')
async def delete_start(m:types.Message,state:FSMContext,db:Database):
    if m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id):
        await state.clear(); await state.set_state(DeleteVideo.link); await edit_or_send_prompt(m,state,'O‘chirmoqchi bo‘lgan videoning havolasini yuboring!')
@router.message(DeleteVideo.link)
async def delete_link(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    if not (m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id)): return
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
    if not vid:
        await delete_user_input(m)
        return await finish_prompt(m,state,'Video havolasi noto‘g‘ri yoki bu post bazadan topilmadi. Video o‘chirish bekor qilindi.')
    v=await db.video(vid)
    if not v:
        await delete_user_input(m); return await finish_prompt(m,state,'Video topilmadi.')
    try: await bot.delete_message(v['channel_id'],v['channel_message_id'])
    except Exception: pass
    await db.delete_video(vid); await delete_user_input(m); await finish_prompt(m,state,'Video o‘chirildi.')
# Settings: retain prior behavior for edit forms, but use Bang Bros labels.
@router.message(F.text=='Karta edit')
async def card_edit(m:types.Message,state:FSMContext,db:Database):
    if await has_permission(db,m.from_user.id,'edit'):
        await state.clear(); await state.set_state(Settings.card); await edit_or_send_prompt(m,state,f'Hozirgi karta: {await db.setting("card")}\nYangi karta raqamini yuboring!')
    else: await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
@router.message(Settings.card)
async def card_save(m:types.Message,state:FSMContext,db:Database):
    if not m.text: return await m.answer('Karta raqamini matn ko‘rinishida yuboring!')
    await db.set_setting('card',m.text.strip()); await delete_user_input(m); await finish_prompt(m,state,'Karta raqami yangilandi.')
@router.message(F.text=='Info edit')
async def info_edit(m:types.Message,state:FSMContext,db:Database):
    if await has_permission(db,m.from_user.id,'edit'):
        await state.clear(); await state.set_state(Settings.info); await edit_or_send_prompt(m,state,f'Hozirgi ma’lumot:\n{await db.setting("bot_info")}\n\nRasm va matn yoki video va matn yuboring!')
    else: await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
@router.message(Settings.info)
async def info_save(m:types.Message,state:FSMContext,db:Database):
    if m.photo:
        await db.set_setting('info_type','photo'); await db.set_setting('info_file_id',m.photo[-1].file_id); await db.set_setting('info_caption',m.caption or '')
    elif m.video:
        await db.set_setting('info_type','video'); await db.set_setting('info_file_id',m.video.file_id); await db.set_setting('info_caption',m.caption or '')
    elif m.text:
        await db.set_setting('info_type','text'); await db.set_setting('info_file_id',''); await db.set_setting('info_caption',m.text); await db.set_setting('bot_info',m.text)
    else: return await m.answer('Rasm va matn yoki video va matn yuboring.')
    await delete_user_input(m); await finish_prompt(m,state,'Bot ma’lumoti yangilandi.')
@router.message(F.text=='Referral edit')
async def ref_edit(m:types.Message,state:FSMContext,db:Database):
    if await has_permission(db,m.from_user.id,'edit'):
        await state.clear(); await state.set_state(Settings.referral); await edit_or_send_prompt(m,state,f'Hozirgi referral bonusi: {await db.setting("referral_bonus")} so‘m. Yangi miqdorni yuboring!')
    else: await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
@router.message(Settings.referral)
async def ref_save(m:types.Message,state:FSMContext,db:Database):
    try: n=int(m.text)
    except: return await m.answer('Faqat raqam yuboring.')
    if n<0: return await m.answer('Bonus manfiy bo‘lishi mumkin emas.')
    await db.set_setting('referral_bonus',n); await delete_user_input(m); await finish_prompt(m,state,'Referral bonusi yangilandi.')
@router.message(F.text=='Admin link edit')
async def link_edit(m:types.Message,state:FSMContext,db:Database):
    if await has_permission(db,m.from_user.id,'edit'):
        await state.clear(); await state.set_state(Settings.admin_link); await edit_or_send_prompt(m,state,f'Hozirgi admin havolasi: {await db.setting("admin_link")}\nYangisini yuboring!')
    else: await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
@router.message(Settings.admin_link)
async def link_save(m:types.Message,state:FSMContext,db:Database):
    if not m.text: return await m.answer('Havolani matn ko‘rinishida yuboring!')
    await db.set_setting('admin_link',m.text.strip()); await delete_user_input(m); await finish_prompt(m,state,'Admin havolasi yangilandi.')
@router.message(F.text=='Kanallar')
async def channels(m:types.Message,db:Database):
    if m.from_user.id==ADMIN_ID: await m.answer('Kanallar bo‘limidasiz.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Majburiy kanal qo‘shish',callback_data='add_mand')],[InlineKeyboardButton(text='Maxsus kanal qo‘shish',callback_data='add_special')],[InlineKeyboardButton(text='Kanal o‘chirish',callback_data='del_channel')]]))
@router.callback_query(F.data=='add_mand')
async def add_mand(c:types.CallbackQuery,state:FSMContext):
    await state.clear(); await state.set_state(Settings.mandatory_channel); await edit_or_send_prompt(c.message,state,'Kanal ID sini va qo‘shilish havolasini quyidagi ko‘rinishda yuboring:\nID | https://t.me/...\nMaxfiy kanal uchun invite link yuboring.'); await c.answer()
@router.message(Settings.mandatory_channel)
async def mand_save(m:types.Message,state:FSMContext,db:Database):
    try:
        cid,url=m.text.split('|',1); chat=await m.bot.get_chat(int(cid.strip())); await db.add_channel(int(cid.strip()),'mandatory',url.strip(),chat.title or chat.username or str(cid.strip())); await delete_user_input(m); await finish_prompt(m,state,'Majburiy kanal qo‘shildi.')
    except Exception: await m.answer('Format noto‘g‘ri. ID | havola ko‘rinishida yuboring.')
@router.callback_query(F.data=='add_special')
async def special_start(c:types.CallbackQuery,state:FSMContext):
    await state.clear(); await state.set_state(Settings.special_channel); await edit_or_send_prompt(c.message,state,'Botni kanalga admin qilib tayinlang va kanal ID sini jo‘nating!'); await c.answer()
@router.message(Settings.special_channel)
async def special_save(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    try:
        cid=int(m.text.strip()); chat=await bot.get_chat(cid); me=await bot.get_me(); member=await bot.get_chat_member(cid,me.id)
        if member.status!='administrator': return await m.answer('Bot kanalda admin emas. Avval admin qiling.')
        invite=None
        if not chat.username:
            try: invite=(await bot.create_chat_invite_link(cid)).invite_link
            except Exception: pass
        await db.conn.execute("DELETE FROM channels WHERE kind='special'"); await db.conn.commit()
        await db.add_channel(cid,'special',invite,chat.title or chat.username or str(cid)); await delete_user_input(m); await finish_prompt(m,state,'Maxsus kanal qo‘shildi.')
    except: await m.answer('Kanal ID sini tekshiring va botga admin huquqini bering.')
@router.callback_query(F.data=='del_channel')
async def del_channels(c:types.CallbackQuery,db:Database,bot:Bot):
    ch=await db.all_channels(); rows=[]
    for x in ch:
        title=x['title']
        if not title:
            try:
                chat=await bot.get_chat(x['channel_id']); title=chat.title or chat.username or str(x['channel_id'])
                await db.add_channel(x['channel_id'],x['kind'],x['join_url'],title)
            except Exception: title=str(x['channel_id'])
        rows.append([InlineKeyboardButton(text=title,callback_data=f'delch:{x["channel_id"]}')])
    if not rows: return await c.answer('Kanallar ro‘yxati bo‘sh.',show_alert=True)
    await c.message.answer('O‘chirish uchun kanalni tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()
@router.callback_query(F.data.startswith('delch:'))
async def del_channel_ask(c:types.CallbackQuery):
    cid=int(c.data.split(':')[1]); await c.message.answer(f'{cid} kanalini o‘chirishni xohlaysizmi?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=f'delchyes:{cid}'),InlineKeyboardButton(text='Yo‘q',callback_data='delchno')]])); await c.answer()
@router.callback_query(F.data.startswith('delchyes:'))
async def del_channel_yes(c:types.CallbackQuery,db:Database):
    await db.delete_channel(int(c.data.split(':')[1])); await c.message.edit_text('Kanal o‘chirildi.'); await c.answer('Kanal o‘chirildi.')
@router.callback_query(F.data=='delchno')
async def del_channel_no(c:types.CallbackQuery):
    await c.message.edit_text('Kanal o‘chirish bekor qilindi.')
    await c.message.answer('Kanallar bo‘limidasiz.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Majburiy kanal qo‘shish',callback_data='add_mand')],[InlineKeyboardButton(text='Maxsus kanal qo‘shish',callback_data='add_special')],[InlineKeyboardButton(text='Kanal o‘chirish',callback_data='del_channel')]]))
    await c.answer()

# --- To'lovlarni tasdiqlash ---
@router.callback_query(F.data.startswith('topupok:'))
async def topup_approve(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    if not await has_permission(db,c.from_user.id,'payments'): return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Chek tasdiqlash',show_alert=True)
    await state.clear()
    rid=int(c.data.split(':')[1]); r=await db.approve_topup(rid)
    if not r: return await c.answer('Bu so‘rov avval ko‘rib chiqilgan.',show_alert=True)
    try: await bot.send_message(r['user_id'],f'To‘lov cheki tasdiqlandi, Hisobingiz {r["amount"]:,}'.replace(',', ' ')+' so‘mga to‘ldirildi.')
    except Exception: pass
    try: await c.message.delete()
    except Exception: pass
    await c.message.answer('To‘lov tasdiqlandi.')
    await c.answer('To‘lov tasdiqlandi.')

@router.callback_query(F.data.startswith('topupno:'))
async def topup_reject(c:types.CallbackQuery,state:FSMContext,db:Database):
    if not await has_permission(db,c.from_user.id,'payments'): return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Chek tasdiqlash',show_alert=True)
    rid=int(c.data.split(':')[1]); r=await db.pending_topup(rid)
    if not r: return await c.answer('Bu so‘rov avval ko‘rib chiqilgan.',show_alert=True)
    await state.clear(); await state.update_data(reject_topup_id=rid,reject_admin_chat_id=c.message.chat.id)
    try: await c.message.delete()
    except Exception: pass
    await state.set_state(UserAdmin.reject_reason)
    await c.message.answer('Rad etish sababini yozing!')
    await c.answer()

@router.message(UserAdmin.reject_reason)
async def topup_reject_reason(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    reason=(m.text or '').strip()
    if not reason: return await m.answer('Rad etish sababini matn ko‘rinishida yozing!')
    data=await state.get_data(); rid=data.get('reject_topup_id'); r=await db.reject_topup_with_reason(rid,reason)
    if not r: await state.clear(); return await m.answer('Bu so‘rov avval ko‘rib chiqilgan.')
    try: await bot.send_message(r['user_id'],f'To‘lovingiz rad etildi.\nHisobingizga pul qo‘shilmadi.\nSababi: {reason}')
    except Exception: pass
    await m.answer('To‘lov rad qilindi.\nSababi foydalanuvchiga yetkazildi.')
    await state.clear()

# --- VIP tariflarini tahrirlash ---
@router.message(F.text=='VIP edit')
async def vip_edit_full(m:types.Message,db:Database):
    if not await has_permission(db,m.from_user.id,'edit'): return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari')
    rows=[]
    for d,label in [(1,'1 kunlik'),(7,'1 haftalik'),(30,'1 oylik')]: rows.append([InlineKeyboardButton(text=f'{label}: {int(await db.setting("vip_"+str(d))):,} so‘m',callback_data=f'vipprice:{d}')])
    await m.answer('O‘zgartirmoqchi bo‘lgan VIP tarifini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
@router.callback_query(F.data.startswith('vipprice:'))
async def vipprice_choose(c:types.CallbackQuery,state:FSMContext,db:Database):
    if not await has_permission(db,c.from_user.id,'edit'): return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Edit imkoniyatlari',show_alert=True)
    d=int(c.data.split(':')[1]); await state.clear(); await state.update_data(vip_days=d); await state.set_state(Settings.vip_price); await edit_or_send_prompt(c.message,state,'Yangi narxni so‘mda yuboring:'); await c.answer()
@router.message(Settings.vip_price)
async def vipprice_save(m:types.Message,state:FSMContext,db:Database):
    try: n=int(m.text.strip()); assert n>0
    except: return await m.answer('Narxni musbat raqam bilan yuboring.')
    d=(await state.get_data())['vip_days']; await db.set_setting('vip_'+str(d),n); await delete_user_input(m); await finish_prompt(m,state,'VIP tarifi yangilandi.')

# --- Foydalanuvchilarni boshqarish ---
@router.message(F.text=='Foydalanuvchilar')
async def users_menu(m:types.Message,state:FSMContext,db:Database):
    await state.clear()
    if not await has_permission(db,m.from_user.id,'users'):
        return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish')
    await state.set_state(UserAdmin.user_id); await edit_or_send_prompt(m,state,'Boshqarish uchun foydalanuvchi ID sini yuboring:')

@router.message(UserAdmin.user_id)
async def user_lookup(m:types.Message,state:FSMContext,db:Database):
    if not await has_permission(db,m.from_user.id,'users'):
        await state.clear(); return await m.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish')
    try: uid=int(m.text.strip())
    except: return await m.answer('ID faqat raqamlardan iborat bo‘lishi kerak.')
    u=await db.user(uid)
    if not u: return await m.answer('Foydalanuvchi topilmadi.')
    prompt_data=await state.get_data(); await delete_user_input(m); await state.clear(); await show_user(m,db,u,actor_id=m.from_user.id,prompt_data=prompt_data)

async def show_user(target,db,u,edit=False,actor_id=None,prompt_data=None):
    uid=u['user_id']; vip=await db.vip(uid); friends=await db.referrals_count(uid)
    perms=await db.admin_permissions(uid); is_admin=perms is not None
    if is_admin:
        n=len(perms or [])
        status='Oddiy admin' if n==0 else ('Full admin' if n==len(PERMISSIONS) else "O‘rta admin")
        extra=f'Holati: {status}'
    elif vip:
        status='Vip obunachi'; expiry=u['vip_until']
        try: expiry=datetime.datetime.fromisoformat(expiry).strftime('%d.%m.%Y %H:%M')
        except Exception: pass
        extra=f'Holati: {status}\nMuddati: {expiry}'
    else: extra='Holati: Oddiy obunachi'
    text=(f'Foydalanuvchi ma’lumotlari\n\nIsm: {u["name"] or "Mavjud emas"}\nUsername: {('@'+u['username']) if u['username'] else 'Mavjud emas'}\nID: {uid}\nBalans: {int(u["balance"] or 0)+int(u["referral_balance"] or 0):,} so‘m\n{extra}\nDo‘stlar: {friends}\nBloklangan: {"Ha" if u["blocked"] else "Yo‘q"}')
    rows=[[InlineKeyboardButton(text='Balans qo‘shish',callback_data=f'uadd:{uid}'),InlineKeyboardButton(text='Balans ayirish',callback_data=f'usub:{uid}')]]
    if vip: rows.append([InlineKeyboardButton(text='VIP bekor qilish',callback_data=f'urevoke:{uid}')])
    elif not is_admin: rows.append([InlineKeyboardButton(text='VIP berish',callback_data=f'uvip:{uid}')])
    rows.append([InlineKeyboardButton(text='Blokdan olish' if u['blocked'] else 'Blocklash',callback_data=f'ublock:{uid}')])
    actor_id=actor_id or getattr(getattr(target,'from_user',None),'id',0)
    if uid != ADMIN_ID and await has_permission(db,actor_id,'admin_manage'):
        rows.append([InlineKeyboardButton(text='Adminlikdan olish' if is_admin else 'Admin qilish',callback_data=f'uremoveadmin:{uid}' if is_admin else f'uadmin:{uid}')])
    rows.append([InlineKeyboardButton(text='Xabar yuborish',callback_data=f'umsg:{uid}')])
    kb=InlineKeyboardMarkup(inline_keyboard=rows)
    if prompt_data and prompt_data.get('prompt_id'):
        await target.bot.edit_message_text(text,chat_id=prompt_data.get('prompt_chat_id',target.chat.id),message_id=prompt_data['prompt_id'],reply_markup=kb)
    elif edit: await target.edit_text(text,reply_markup=kb)
    else: await target.answer(text,reply_markup=kb)

@router.callback_query(F.data.regexp(r'^u(add|sub|vip|msg|block|revoke):'))
async def user_action(c:types.CallbackQuery,state:FSMContext,db:Database):
    if not await has_permission(db,c.from_user.id,'users'):
        return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish',show_alert=True)
    await state.clear()
    action_key,uid_raw=c.data.split(':',1)
    action=action_key[1:] if action_key.startswith('u') else action_key
    uid=int(uid_raw)
    await state.update_data(target_uid=uid,action=action,prompt_id=c.message.message_id,prompt_chat_id=c.message.chat.id)
    if action=='revoke':
        await db.revoke_vip(uid)
        try: await c.bot.send_message(uid,'VIP obunangiz administrator tomonidan bekor qilindi.')
        except: pass
        await c.answer('VIP bekor qilindi.'); return await show_user(c.message,db,await db.user(uid),True,c.from_user.id)
    if action=='block':
        u=await db.user(uid); verb='blockdan chiqarmoqchimisiz?' if u['blocked'] else 'blocklamoqchimisiz?'
        return await c.message.edit_text(f'Rostdan ham shu foydalanuvchini {verb}',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=f'ublockconfirm:{uid}:yes'),InlineKeyboardButton(text='Yo‘q',callback_data=f'ublockconfirm:{uid}:no')]]))
    prompts={'add':'Qo‘shiladigan summani yuboring:','sub':'Ayiriladigan summani yuboring:','vip':'VIP muddati: 1, 7 yoki 30 kun yuboring:','msg':'Foydalanuvchiga yuboriladigan xabarni jo‘nating:'}
    await state.set_state(UserAdmin.add_amount if action in ('add','sub','vip') else UserAdmin.message)
    await edit_or_send_prompt(c.message,state,prompts[action]); await c.answer()

@router.callback_query(F.data.startswith('ublockconfirm:'))
async def user_block_confirm(c:types.CallbackQuery,db:Database,bot:Bot):
    _,raw_uid,answer=c.data.split(':'); uid=int(raw_uid)
    if not await has_permission(db,c.from_user.id,'users'): return await c.answer('Foydalanuvchilarni ko‘rish huquqi kerak.',show_alert=True)
    u=await db.user(uid)
    if not u: return await c.answer('Foydalanuvchi topilmadi.',show_alert=True)
    if answer=='no':
        await c.message.edit_text('Amal bekor qilindi.')
        await c.message.answer('Sozlamalar',reply_markup=__import__('keyboards').settings())
        return await c.answer()
    blocking=not bool(u['blocked']); await db.set_user_block(uid,blocking)
    if blocking:
        try: await bot.send_message(uid,'Siz botdan butunlay blocklandingiz. Sababini bilmoqchi bo‘lsangiz Yordam bo‘limidan adminga murojaat qiling.',reply_markup=__import__('keyboards').blocked_menu())
        except Exception: pass
        await c.message.edit_text('Foydalanuvchi bloklandi.')
    else:
        try: await bot.send_message(uid,'Siz blockdan ozod etildingiz, endi erkin foydalanishingiz mumkin.',reply_markup=__import__('keyboards').main_menu())
        except Exception: pass
        await c.message.edit_text('Foydalanuvchi blockdan chiqarildi.')
    await c.answer()

@router.message(UserAdmin.add_amount)
async def user_amount(m:types.Message,state:FSMContext,db:Database,bot:Bot):
    d=await state.get_data(); action=d['action']; uid=d['target_uid']
    try: n=int(m.text.strip()); assert n>0
    except: return await m.answer('Musbat raqam yuboring.')
    if action=='vip':
        if n not in (1,7,30): return await m.answer('Faqat 1, 7 yoki 30 kun kiriting.')
        expiry=await db.set_vip(uid,n); notice=f'Sizga {n} kunlik VIP obuna berildi. Amal qilish muddati: {expiry:%d.%m.%Y %H:%M}'
        try: await bot.send_message(uid,notice)
        except: pass
        await delete_user_input(m); await show_user(m,db,await db.user(uid),actor_id=m.from_user.id,prompt_data=d); await state.clear(); return
    await state.update_data(pending_amount=n); await state.set_state(UserAdmin.confirm_balance); await delete_user_input(m)
    await edit_or_send_prompt(m,state,f'Rostdan ham {n:,} so‘m {"qo‘shilsin" if action=="add" else "ayirilsin"}mi?',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='ubalconfirm:yes'),InlineKeyboardButton(text='Yo‘q',callback_data='ubalconfirm:no')]]))

@router.callback_query(F.data.startswith('ubalconfirm:'))
async def user_balance_confirm(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    d=await state.get_data(); uid=d.get('target_uid'); n=int(d.get('pending_amount',0)); action=d.get('action')
    if not uid or action not in ('add','sub'): return await c.answer('Amal topilmadi.',show_alert=True)
    if c.data.endswith(':yes'):
        delta=n if action=='add' else -n; await db.adjust_balance(uid,delta,'admin_adjust')
        try: await bot.send_message(uid,f'Balansingiz {n:,} so‘mga {"oshirildi" if action=="add" else "kamaytirildi"}.')
        except: pass
    data=d.copy(); await state.clear(); u=await db.user(uid)
    await show_user(c.message,db,u,True,c.from_user.id)
    await c.answer('Balans yangilandi.' if c.data.endswith(':yes') else 'Amal bekor qilindi.')

@router.message(UserAdmin.message)
async def user_message(m:types.Message,state:FSMContext,bot:Bot,db:Database):
    d=await state.get_data(); uid=d['target_uid']; sent=False
    try: await m.copy_to(uid,protect_content=True); sent=True
    except Exception: pass
    await delete_user_input(m)
    await show_user(m,db,await db.user(uid),actor_id=m.from_user.id,prompt_data=d)
    await state.clear()
    try: await bot.send_message(m.chat.id,'Xabar yuborildi.' if sent else 'Xabar yuborilmadi.')
    except Exception: pass

@router.callback_query(F.data.startswith('uadmin:'))
async def user_admin_start(c:types.CallbackQuery,state:FSMContext,db:Database):
    await state.clear()
    if not await has_permission(db,c.from_user.id,'admin_manage'):
        return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Admin qilish/olish',show_alert=True)
    uid=int(c.data.split(':')[1])
    if uid==ADMIN_ID: return await c.answer('Bosh adminni qayta tayinlab bo‘lmaydi.',show_alert=True)
    await state.update_data(admin_target=uid,admin_permissions=[]); await state.set_state(UserAdmin.admin_permissions)
    await show_admin_permissions(c.message,uid,[],edit=False); await c.answer()

async def show_admin_permissions(target,uid,selected,edit=False):
    labels=[('edit','Edit imkoniyatlari'),('payments','Chek tasdiqlash'),('admin_manage','Admin qilish/olish'),('users','Foydalanuvchilarni ko‘rish')]
    rows=[]
    for key,label in labels:
        mark='✅' if key in selected else '❌'
        rows.append([InlineKeyboardButton(text=f'{mark} {label}',callback_data=f'uperm:{uid}:{key}')])
    rows.append([InlineKeyboardButton(text='Bo‘ldi',callback_data=f'upermdone:{uid}')])
    kb=InlineKeyboardMarkup(inline_keyboard=rows); text='Admin imkoniyatlarini belgilang:'
    # The permission selector replaces the existing user profile message.
    try:
        await target.edit_text(text,reply_markup=kb)
    except Exception:
        await target.answer(text,reply_markup=kb)

@router.callback_query(F.data.startswith('uperm:'))
async def permission_toggle(c:types.CallbackQuery,state:FSMContext,db:Database):
    if not await has_permission(db,c.from_user.id,'admin_manage'): return await c.answer('Admin qilish/olish huquqi kerak.',show_alert=True)
    _,uid,key=c.data.split(':'); data=await state.get_data()
    if data.get('admin_target')!=int(uid): return await c.answer('Admin tayinlash jarayoni topilmadi.',show_alert=True)
    selected=set(data.get('admin_permissions',[]))
    if key in selected: selected.remove(key)
    else: selected.add(key)
    await state.update_data(admin_permissions=list(selected)); await show_admin_permissions(c.message,int(uid),selected,True); await c.answer()

@router.callback_query(F.data.startswith('upermdone:'))
async def permission_done(c:types.CallbackQuery,state:FSMContext,db:Database):
    if not await has_permission(db,c.from_user.id,'admin_manage'): return await c.answer('Admin qilish/olish huquqi kerak.',show_alert=True)
    uid=int(c.data.split(':')[1]); data=await state.get_data()
    if data.get('admin_target')!=uid: return await c.answer('Admin tayinlash jarayoni topilmadi.',show_alert=True)
    await c.message.edit_text('Haqiqatdan ham shu foydalanuvchini admin qilib tayinlamoqchimisiz?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=f'uadminconfirm:{uid}:yes'),InlineKeyboardButton(text='Yo‘q',callback_data=f'uadminconfirm:{uid}:no')]])); await c.answer()

@router.callback_query(F.data.startswith('uadminconfirm:'))
async def admin_confirm(c:types.CallbackQuery,state:FSMContext,db:Database):
    _,raw_uid,answer=c.data.split(':'); uid=int(raw_uid)
    if (await state.get_data()).get('admin_target')!=uid: return await c.answer('Admin tayinlash jarayoni topilmadi.',show_alert=True)
    if answer=='no':
        await state.clear(); u=await db.user(uid); await show_user(c.message,db,u,True,c.from_user.id); return await c.answer()
    if not await has_permission(db,c.from_user.id,'admin_manage'): return await c.answer('Admin qilish/olish huquqi kerak.',show_alert=True)
    perms=(await state.get_data()).get('admin_permissions',[]); await db.set_admin(uid,perms); ACTIVE_ADMINS.add(uid); await state.clear()
    level='Oddiy admin' if len(perms)==0 else ('Full admin' if len(perms)==len(PERMISSIONS) else "O‘rta admin")
    try: await c.bot.send_message(uid,f'Siz botga admin etib tayinlandingiz.\nUnvoningiz: {level}',reply_markup=admin_menu())
    except Exception: pass
    await c.message.edit_text('Foydalanuvchi belgilangan huquqlar bilan admin etib tayinlandi.'); await c.answer('Admin tayinlandi.')

@router.callback_query(F.data.startswith('uremoveadmin:'))
async def remove_admin_ask(c:types.CallbackQuery,db:Database):
    uid=int(c.data.split(':')[1])
    if uid==ADMIN_ID: return await c.answer('Bosh adminlikni bekor qilib bo‘lmaydi.',show_alert=True)
    if not await has_permission(db,c.from_user.id,'admin_manage'): return await c.answer('Admin qilish/olish huquqi kerak.',show_alert=True)
    await c.message.edit_text('Haqiqatdan ham shu foydalanuvchining adminlik huquqlarini bekor qilmoqchimisiz?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data=f'uremoveconfirm:{uid}:yes'),InlineKeyboardButton(text='Yo‘q',callback_data=f'uremoveconfirm:{uid}:no')]])); await c.answer()

@router.callback_query(F.data.startswith('uremoveconfirm:'))
async def remove_admin_confirm(c:types.CallbackQuery,db:Database):
    _,raw_uid,answer=c.data.split(':'); uid=int(raw_uid)
    if answer=='no':
        u=await db.user(uid)
        if u: await show_user(c.message,db,u,True,c.from_user.id)
        else: await c.message.edit_text('Foydalanuvchi topilmadi.')
        return await c.answer()
    if uid==ADMIN_ID: return await c.answer('Bosh admin himoyalangan.',show_alert=True)
    if not await has_permission(db,c.from_user.id,'admin_manage'): return await c.answer('Admin qilish/olish huquqi kerak.',show_alert=True)
    await db.remove_admin(uid); ACTIVE_ADMINS.discard(uid)
    try: await c.bot.send_message(uid,'Adminlik huquqingiz bekor qilindi.',reply_markup=__import__('keyboards').main_menu())
    except Exception: pass
    await c.message.edit_text('Adminlik bekor qilindi. Foydalanuvchi oddiy foydalanuvchi holatiga qaytarildi.'); await c.answer()

# --- Reklama yaratish va tarqatish ---
def parse_ad_buttons(raw):
    rows=[]
    for line in raw.splitlines():
        row=[]
        for part in line.split('|'):
            if '-' not in part: raise ValueError('Tugma nomi va havola orasida - belgisi bo‘lishi kerak.')
            label,url=[x.strip() for x in part.split('-',1)]
            if not label or not url or not url.startswith(('https://','http://','tg://')): raise ValueError('Tugma nomi yoki havolasi noto‘g‘ri.')
            row.append({'text':label,'url':url})
        if len(row)>3: raise ValueError('Bir qatorda uchtagacha tugma qo‘shish mumkin.')
        if row: rows.append(row)
    if not rows: raise ValueError('Kamida bitta tugma yuboring.')
    return rows

def parse_like_layout(raw):
    rows=[]; options=[]
    for line in raw.splitlines():
        for row_text in line.split('|'):
            row=[]
            for token in row_text.split('/'):
                token=token.strip()
                if not token: continue
                if len(token)>32: raise ValueError('Tugma matni juda uzun.')
                idx=len(options); options.append(token); row.append({'text':token,'index':idx})
            if row: rows.append(row)
    if not options: raise ValueError('Like tugmalarini kiriting.')
    if len(options)>30: raise ValueError('30 tadan ortiq like tugmasi qo‘shib bo‘lmaydi.')
    return rows,options

def ad_markup(data,campaign_id=None,counts=None):
    rows=[]; counts=counts or {}
    for row in data.get('url_buttons') or []:
        rows.append([InlineKeyboardButton(text=x['text'],url=x['url']) for x in row])
    layout=data.get('like_rows') or []
    if layout:
        for row in layout:
            buttons=[]
            for item in row:
                i=item['index']; label=item['text']; count=counts.get(i,0)
                text=f'{label} ({count})' if campaign_id else label
                buttons.append(InlineKeyboardButton(text=text,callback_data=f'advote:{campaign_id}:{i}' if campaign_id else 'adpreview'))
            rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

async def broadcast_preview(target,state):
    msg=target.message if isinstance(target,types.CallbackQuery) else target
    d=await state.get_data(); markup=ad_markup(d)
    try: await msg.bot.edit_message_reply_markup(chat_id=d['source_chat'],message_id=d['source_message'],reply_markup=markup)
    except Exception: pass
    controls=[]
    controls.append([InlineKeyboardButton(text='Tugmalarni o‘chirish' if d.get('url_buttons') else 'Tugmalar qo‘shish',callback_data='bcurls:remove' if d.get('url_buttons') else 'bcurls:add')])
    controls.append([InlineKeyboardButton(text='Like tugmalarni o‘chirish' if d.get('like_rows') else 'Like tugmalar qo‘shish',callback_data='bclike:remove' if d.get('like_rows') else 'bclike:add')])
    controls.append([InlineKeyboardButton(text='Reklama tayyor',callback_data='bcdone'),InlineKeyboardButton(text='Reklamani bekor qilish',callback_data='bccancel')])
    await edit_or_send_prompt(msg,state,'Reklama ko‘rinishi tayyor. Kerakli tugmalarni qo‘shing yoki reklama tayyor tugmasini bosing.',InlineKeyboardMarkup(inline_keyboard=controls))

@router.message(F.text=='Reklama jo‘natish')
async def broadcast_start(m:types.Message,state:FSMContext,db:Database):
    if m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id):
        await state.clear(); await state.set_state(Broadcast.content); await edit_or_send_prompt(m,state,'Jo‘natmoqchi bo‘lgan reklamangizni yuboring!\n\nReklama rasm + matn, video + matn, GIF, MP3 yoki faqat matn bo‘lishi mumkin.')

@router.message(Broadcast.content)
async def broadcast_content(m:types.Message,state:FSMContext):
    try:
        preview=await m.bot.copy_message(m.chat.id,m.chat.id,m.message_id)
    except Exception:
        return await m.answer('Bu xabarni reklama sifatida qabul qilib bo‘lmadi. Boshqa media yoki matn yuboring.')
    await delete_user_input(m)
    await state.update_data(source_chat=m.chat.id,source_message=preview.message_id,url_buttons=[],like_rows=[],like_options=[])
    await state.set_state(Broadcast.content)
    # A separate controller message is edited throughout the setup.
    await edit_or_send_prompt(m,state,'Reklama ko‘rinishi tayyor. Kerakli tugmalarni qo‘shing yoki reklama tayyor tugmasini bosing.',InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Tugmalar qo‘shish',callback_data='bcurls:add')],
        [InlineKeyboardButton(text='Like tugmalar qo‘shish',callback_data='bclike:add')],
        [InlineKeyboardButton(text='Reklama tayyor',callback_data='bcdone'),InlineKeyboardButton(text='Reklamani bekor qilish',callback_data='bccancel')]]))

@router.callback_query(F.data.startswith('bcurls:'))
async def broadcast_urls(c:types.CallbackQuery,state:FSMContext):
    action=c.data.split(':')[1]; d=await state.get_data()
    if action=='remove':
        await state.update_data(url_buttons=[]); await broadcast_preview(c,state); return await c.answer('URL tugmalar o‘chirildi.')
    await state.set_state(Broadcast.button_url)
    prompt='Menga bitta xabarda URL-tugmalar ro‘yxatini yuboring. Iltimos, quyidagi formatga amal qiling:\n\nTugma 1 - http://example1.com\nTugma 2 - http://example2.com\n\nBitta qatorga uchtagacha tugma qo‘shish uchun | belgisidan foydalaning. Masalan:\n\nTugma 1 - http://example1.com | Tugma 2 - http://example2.com\nTugma 3 - http://example3.com | Tugma 4 - http://example4.com\n\nXabarlar qo‘shishga qaytish uchun "Orqaga" tugmasini bosing.'
    await edit_or_send_prompt(c.message,state,prompt,InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Orqaga',callback_data='bcback')]])); await c.answer()

@router.callback_query(F.data.startswith('bclike:'))
async def broadcast_likes(c:types.CallbackQuery,state:FSMContext):
    action=c.data.split(':')[1]
    if action=='remove':
        await state.update_data(like_rows=[],like_options=[]); await broadcast_preview(c,state); return await c.answer('Like tugmalar o‘chirildi.')
    await state.set_state(Broadcast.like_layout)
    prompt=('Iltimos like tugma ko‘rinishining kiriting!\nNamunalar:\n\n'
      'Stickerli: 😀/😊|🥰/🤭\nMatnli: Ha/Yo‘q|Balkim\n\n'
      'Tugmalarni yonma-yon chiqarish uchun / belgisidan foydalaning. Masalan: 😀/😁 — bitta qatorda 2 ta tugma.\n'
      'Keyingi qatorga tushirish uchun | belgisidan foydalaning. Masalan: 😀/😁|🥰 — yuqorida 2 ta, pastda 1 ta tugma.\n'
      'Shu tartibda xohlagancha qator va tugma qo‘shishingiz mumkin. Matnli tugmalarda ham xuddi shu qoida amal qiladi: Ha/Yo‘q|Balkim.')
    await edit_or_send_prompt(c.message,state,prompt,InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Orqaga',callback_data='bcback')]])); await c.answer()

@router.callback_query(F.data=='bcback')
async def broadcast_back(c:types.CallbackQuery,state:FSMContext):
    await state.set_state(Broadcast.content); await broadcast_preview(c,state); await c.answer()

@router.message(Broadcast.button_url)
async def broadcast_button_url(m:types.Message,state:FSMContext):
    if (m.text or '').strip().lower()=='orqaga':
        await delete_user_input(m); await state.set_state(Broadcast.content); return await edit_or_send_prompt(m,state,'Reklama sozlamalariga qaytdingiz.')
    try: rows=parse_ad_buttons(m.text or '')
    except Exception as e: return await m.answer(str(e))
    await state.update_data(url_buttons=rows); await delete_user_input(m); await state.set_state(Broadcast.content)
    await broadcast_preview(m,state)

@router.message(Broadcast.like_layout)
async def broadcast_like_layout(m:types.Message,state:FSMContext):
    raw=(m.text or (m.sticker.emoji if m.sticker and m.sticker.emoji else ('👍' if m.sticker else '')))
    try: rows,options=parse_like_layout(raw)
    except Exception as e: return await m.answer(str(e))
    await state.update_data(like_rows=rows,like_options=options); await delete_user_input(m); await state.set_state(Broadcast.content)
    await broadcast_preview(m,state)

@router.callback_query(F.data=='bcdone')
async def broadcast_done(c:types.CallbackQuery,state:FSMContext):
    await state.set_state(Broadcast.audience)
    await edit_or_send_prompt(c.message,state,'Auditoriyani tanlang!',InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='VIP foydalanuvchilarga',callback_data='ba:vip')],
        [InlineKeyboardButton(text='Oddiy foydalanuvchilarga',callback_data='ba:ordinary')],
        [InlineKeyboardButton(text='Maxsus kanalga',callback_data='ba:special')],
        [InlineKeyboardButton(text='Hammasiga',callback_data='ba:all')],
        [InlineKeyboardButton(text='Orqaga',callback_data='bcback')]])); await c.answer()

@router.callback_query(F.data=='bccancel')
async def broadcast_cancel(c:types.CallbackQuery,state:FSMContext):
    d=await state.get_data()
    if d.get('source_chat') and d.get('source_message'):
        try: await c.bot.delete_message(d['source_chat'],d['source_message'])
        except Exception: pass
    await finish_prompt(c.message,state,'Reklama bekor qilindi.'); await c.answer()

@router.callback_query(F.data.startswith('ba:'))
async def broadcast_prepare(c:types.CallbackQuery,state:FSMContext):
    mode=c.data.split(':')[1]
    if mode=='cancel': return await broadcast_cancel(c,state)
    await state.update_data(audience=mode)
    await edit_or_send_prompt(c.message,state,'Reklama jo‘natishga tayyor. Jo‘natilsinmi?',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='basend:yes'),InlineKeyboardButton(text='Yo‘q',callback_data='basend:no')]])); await c.answer()

@router.callback_query(F.data.startswith('basend:'))
async def broadcast_send(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    d=await state.get_data()
    if c.data.endswith('no'):
        await state.set_state(Broadcast.content); await broadcast_preview(c,state); return await c.answer('Orqaga qaytdingiz.')
    mode=d.get('audience','all'); campaign_id=None
    if d.get('like_options'):
        campaign_id=await db.create_ad_campaign(d['source_chat'],d['source_message'],d.get('url_buttons',[]),d['like_options'],d.get('like_rows',[]))
    markup=ad_markup(d,campaign_id)
    if mode=='special':
        ch=next((x for x in await db.all_channels() if x['kind']=='special'),None)
        if not ch: await finish_prompt(c.message,state,'Maxsus kanal sozlanmagan.'); return await c.answer('Maxsus kanal sozlanmagan.',show_alert=True)
        try: await bot.copy_message(ch['channel_id'],d['source_chat'],d['source_message'],reply_markup=markup,protect_content=True); sent=1
        except Exception as e: await finish_prompt(c.message,state,f'Yuborilmadi: {e}'); return await c.answer()
        try: await bot.delete_message(d['source_chat'],d['source_message'])
        except Exception: pass
        await finish_prompt(c.message,state,'Reklama maxsus kanalga yuborildi.'); return await c.answer()
    ids=await db.all_user_ids(mode); ok=bad=0
    for uid in ids:
        try: await bot.copy_message(uid,d['source_chat'],d['source_message'],reply_markup=markup,protect_content=True); ok+=1
        except Exception: bad+=1
    try: await bot.delete_message(d['source_chat'],d['source_message'])
    except Exception: pass
    await finish_prompt(c.message,state,f'Reklama tarqatish yakunlandi.\nJami: {len(ids)}\nYuborildi: {ok}\nYuborilmadi: {bad}')
    await c.answer()

# --- Gift tarqatish ---
@router.message(F.text=='Gift o‘tkazish')
async def gift_start(m:types.Message,state:FSMContext,db:Database):
    if m.from_user.id==ADMIN_ID or await db.is_admin(m.from_user.id):
        await state.clear(); await state.set_state(Gift.gift_type); await edit_or_send_prompt(m,state,'Gift turini tanlang:',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Pul tarqatish',callback_data='giftkind:money')],[InlineKeyboardButton(text='VIP tarqatish',callback_data='giftkind:vip')]]))
@router.callback_query(F.data.startswith('giftkind:'))
async def gift_kind(c:types.CallbackQuery,state:FSMContext):
    kind=c.data.split(':')[1]; await state.update_data(gift_kind=kind)
    if kind=='vip':
        await state.set_state(Gift.tariff); await edit_or_send_prompt(c.message,state,'VIP muddatini tanlang:',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='1 kun',callback_data='giftdays:1'),InlineKeyboardButton(text='7 kun',callback_data='giftdays:7'),InlineKeyboardButton(text='30 kun',callback_data='giftdays:30')]]))
    else: await state.set_state(Gift.amount); await edit_or_send_prompt(c.message,state,'Har bir g‘olib oladigan pul miqdorini yuboring (so‘m):')
    await c.answer()
@router.callback_query(F.data.startswith('giftdays:'))
async def gift_days(c:types.CallbackQuery,state:FSMContext):
    await state.update_data(gift_days=int(c.data.split(':')[1])); await state.set_state(Gift.winners); await edit_or_send_prompt(c.message,state,'Nechta g‘olib bo‘lishini yuboring:'); await c.answer()
@router.message(Gift.amount)
async def gift_amount(m:types.Message,state:FSMContext):
    try: n=int(m.text); assert n>0
    except: return await m.answer('Musbat summa kiriting.')
    await state.update_data(gift_amount=n); await state.set_state(Gift.winners); await delete_user_input(m); await edit_or_send_prompt(m,state,'Nechta g‘olib bo‘lishini yuboring:')
@router.message(Gift.winners)
async def gift_winners_count(m:types.Message,state:FSMContext):
    try: n=int(m.text); assert n>0
    except: return await m.answer('Musbat son kiriting.')
    await state.update_data(gift_winners=n); d=await state.get_data(); await state.set_state(Gift.confirm)
    desc=(f'{d.get("gift_amount",0):,} so‘m' if d['gift_kind']=='money' else f'{d["gift_days"]} kunlik VIP')
    await delete_user_input(m); await edit_or_send_prompt(m,state,f'Gift: {desc}\nG‘oliblar: {n} ta\nTasdiqlaysizmi?',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Ha',callback_data='giftconfirm:yes'),InlineKeyboardButton(text='Yo‘q',callback_data='giftconfirm:no')]]))
@router.callback_query(F.data.startswith('giftconfirm:'))
async def gift_confirm(c:types.CallbackQuery,state:FSMContext,db:Database,bot:Bot):
    if c.data.endswith('no'):
        await state.clear(); await state.update_data(prompt_id=c.message.message_id,prompt_chat_id=c.message.chat.id); await state.set_state(Gift.gift_type)
        await edit_or_send_prompt(c.message,state,'Gift turini tanlang:',InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Pul tarqatish',callback_data='giftkind:money')],[InlineKeyboardButton(text='VIP tarqatish',callback_data='giftkind:vip')]]))
        return await c.answer('Gift sozlamalariga qaytdingiz.')
    d=await state.get_data(); kind=d['gift_kind']; gid=await db.create_gift(kind,d.get('gift_amount',0),d.get('gift_days',0),d['gift_winners'])
    if kind=='money': body=f'Adminlar obunachilar uchun tekinga {d["gift_amount"]:,} so‘m pul sovg‘a qilishmoqda. Shoshiling! Sovg‘a faqatgina {d["gift_winners"]} odamga nasib qiladi, omadingizni qo‘ldan chiqarmang!'
    else: body=f'{d["gift_days"]} kunlik VIP sovg‘a! Sovg‘a faqat {d["gift_winners"]} nafar oddiy foydalanuvchiga beriladi. Shoshiling!'
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Sovg‘ani olish',callback_data=f'claimgift:{gid}')]])
    ids=await db.all_user_ids('ordinary' if kind=='vip' else 'all'); ok=0
    for uid in ids:
        try: await bot.send_message(uid,body,reply_markup=kb); ok+=1
        except: pass
    await finish_prompt(c.message,state,f'Gift e’lon qilindi. Yetkazildi: {ok} ta foydalanuvchi.'); await c.answer()

# Non-admin callback for claiming gift is handled by public router registered in main.

@router.callback_query(F.data.startswith('uid:'))
async def id_user_profile(c:types.CallbackQuery,db:Database):
    if not await has_permission(db,c.from_user.id,'users'): return await c.answer('Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\nKerakli huquq: Foydalanuvchilarni ko‘rish',show_alert=True)
    u=await db.user(int(c.data.split(':')[1]))
    if not u: return await c.answer('Foydalanuvchi topilmadi.',show_alert=True)
    await show_user(c.message,db,u,actor_id=c.from_user.id); await c.answer()
