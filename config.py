import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
DB_PATH = os.getenv('DB_PATH', 'bot.db')
if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN Railway Variables ichida kiritilishi kerak.')
if not ADMIN_ID:
    raise RuntimeError('ADMIN_ID Railway Variables ichida kiritilishi kerak.')
