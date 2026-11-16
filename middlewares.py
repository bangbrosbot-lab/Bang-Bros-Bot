import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from config import ADMIN_ID


class ThrottleMiddleware(BaseMiddleware):
    """Bir foydalanuvchidan juda tez kelgan takroriy bosishlarni (double-click, spam) tashlab yuboradi."""

    def __init__(self, interval: float = 0.3):
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id != ADMIN_ID:
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
