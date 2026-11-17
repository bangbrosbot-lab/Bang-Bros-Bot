import asyncio
import logging
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ErrorEvent

from backup import send_backup
from config import ADMIN_ID, BACKUP_INTERVAL_HOURS, BOT_TOKEN, DB_PATH, LOG_LEVEL
from db import Database
from handlers.admin import menu_router, router as admin_router
from handlers.ads import router as ads_router
from handlers.user import router as user_router
from middlewares import ThrottleMiddleware, WorkflowCleanupMiddleware
from notifications import vip_notice_loop

log = logging.getLogger("bot")
_error_alerts: dict[str, float] = {}


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    """Kutilmagan xatolar: logga yoziladi, foydalanuvchiga xabar beriladi, bosh adminga (soatiga 1 marta) ogohlantiriladi."""
    exc = event.exception
    log.error("Handlerda xato: %r", exc, exc_info=exc)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer("Xatolik yuz berdi. Birozdan so‘ng qayta urinib ko‘ring.", show_alert=True)
        elif update.message:
            await update.message.answer("Xatolik yuz berdi. Birozdan so‘ng qayta urinib ko‘ring.")
    except Exception:
        pass
    signature = f"{type(exc).__name__}:{exc}"[:200]
    last = _error_alerts.get(signature)
    if last is None or time.monotonic() - last > 3600:
        if len(_error_alerts) > 200:
            _error_alerts.clear()
        _error_alerts[signature] = time.monotonic()
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ Botda xatolik: {signature}")
        except Exception:
            pass
    return True


async def backup_loop(bot: Bot, db: Database) -> None:
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
        try:
            await send_backup(bot, db, ADMIN_ID, "Avtomatik zaxira nusxa")
        except Exception:
            log.exception("Avtomatik zaxira yuborilmadi")


async def main() -> None:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    db = Database(DB_PATH)
    await db.connect()

    dp = Dispatcher()
    dp["db"] = db
    throttle = ThrottleMiddleware()
    dp.message.outer_middleware(throttle)
    dp.message.outer_middleware(WorkflowCleanupMiddleware())
    dp.callback_query.outer_middleware(throttle)
    # Tartib muhim: avval menyu tugmalari, keyin admin, reklama/gift, oxirida oddiy foydalanuvchi
    for router in (menu_router, admin_router, ads_router, user_router):
        dp.include_router(router)
    dp.errors.register(on_error)

    backup_task = None
    notice_task = asyncio.create_task(vip_notice_loop(bot, db))
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        if BACKUP_INTERVAL_HOURS > 0:
            backup_task = asyncio.create_task(backup_loop(bot, db))
        log.info("Bot ishga tushdi (baza: %s)", DB_PATH)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        notice_task.cancel()
        if backup_task:
            backup_task.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
