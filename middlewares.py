import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from access import ask_sub, subscribed
from config import is_owner
from utils import delete_quietly


class ThrottleMiddleware(BaseMiddleware):
    """Bir foydalanuvchidan juda tez kelgan takroriy bosishlarni (double-click, spam) tashlab yuboradi."""

    def __init__(self, interval: float = 0.3):
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not is_owner(user.id):
            now = time.monotonic()
            if now - self._last.get(user.id, 0.0) < self.interval:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except Exception:
                        pass
                return None
            if len(self._last) > 20000:
                self._last.clear()
            self._last[user.id] = now
        return await handler(event, data)


class WorkflowCleanupMiddleware(BaseMiddleware):
    """FSM jarayonida foydalanuvchi yuborgan vaqtinchalik xabarlarni handlerdan keyin o‘chiradi."""

    async def __call__(self, handler, event, data):
        state = data.get("state")
        active = False
        if isinstance(event, Message) and state is not None:
            try:
                active = bool(await state.get_state())
            except Exception:
                active = False
        # Oddiy /start (video havolasisiz) hech qachon o‘chirilmaydi
        is_plain_start = (isinstance(event, Message) and (event.text or "").startswith("/start")
                          and "video_" not in (event.text or ""))
        try:
            return await handler(event, data)
        finally:
            if active and isinstance(event, Message) and event.from_user and not is_plain_start:
                await delete_quietly(event)


# Obuna tekshirilmaydigan callbacklar (ularning o‘zi tekshiradi)
_SUB_EXEMPT_CALLBACKS = {"check_sub", "noop"}


class SubscriptionMiddleware(BaseMiddleware):
    """Majburiy a’zolikni HAR BIR amalda tekshiradi.

    Foydalanuvchi bir marta tasdiqlagach kanaldan chiqib ketsa, keyingi har qanday tugma/xabarda
    qaytadan «Majburiy a’zolik» chiqadi. Adminlar, bloklanganlar (ularga alohida xabar chiqadi),
    ro‘yxatdan o‘tmaganlar, /start (o‘zi tekshiradi), «Tekshirish» tugmasi va shaxsiy chatdan tashqari
    xabarlar (masalan kanal postidagi «Yoqdi» tugmasi) bundan mustasno.
    """

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        db = data.get("db")
        bot = data.get("bot")
        if not user or user.is_bot or db is None or bot is None:
            return await handler(event, data)
        if is_owner(user.id) or db.is_admin(user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            if event.chat.type != "private" or (event.text or "").startswith("/start"):
                return await handler(event, data)
            target = event
        elif isinstance(event, CallbackQuery):
            if (event.data or "") in _SUB_EXEMPT_CALLBACKS or event.message is None \
                    or event.message.chat.type != "private":
                return await handler(event, data)
            target = event.message
        else:
            return await handler(event, data)

        u = await db.user(user.id)
        if not u or u["blocked"]:
            return await handler(event, data)
        if await subscribed(bot, db, user.id):
            return await handler(event, data)

        # A’zo emas: jarayonni to‘xtatib, majburiy a’zolik oynasini ko‘rsatamiz
        state = data.get("state")
        if state is not None:
            try:
                await state.set_state(None)
            except Exception:
                pass
        prompt = await ask_sub(target, db)
        if state is not None and prompt:
            try:
                await state.update_data(ui_message_id=prompt.message_id, ui_chat_id=prompt.chat.id)
            except Exception:
                pass
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        return None
