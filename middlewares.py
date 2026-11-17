import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from utils import delete_quietly

from config import is_owner


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
        try:
            return await handler(event, data)
        finally:
            if active and isinstance(event, Message) and event.from_user:
                await delete_quietly(event)
