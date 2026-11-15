import asyncio,logging
from aiogram import Bot,Dispatcher
from aiogram.client.default import DefaultBotProperties
from db import Database
from config import BOT_TOKEN,DB_PATH
from handlers.user import router as user_router
from handlers.admin import router as admin_router

async def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=None))
    dp=Dispatcher(); db=Database(DB_PATH); await db.connect(); dp['db']=db
    dp.include_router(admin_router); dp.include_router(user_router)
    try:
        await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close(); await bot.session.close()
if __name__=='__main__': asyncio.run(main())
