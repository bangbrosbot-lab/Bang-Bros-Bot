"""Bot sozlamalari (barchasi Railway Variables / .env orqali)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} butun son bo‘lishi kerak, hozir: {raw!r}") from None


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = _int_env("ADMIN_ID", 0)
DB_PATH = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"

# Asosiy kanal havolasi (avval kod ichiga qattiq yozilgan edi)
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/Bangbros_studio").strip()

MIN_TOPUP = _int_env("MIN_TOPUP", 3000)
MAX_TOPUP = _int_env("MAX_TOPUP", 50_000_000)
MAX_PENDING_TOPUPS = _int_env("MAX_PENDING_TOPUPS", 3)

# Bazaning avtomatik zaxira nusxasi (soat). 0 = o‘chirilgan.
BACKUP_INTERVAL_HOURS = _int_env("BACKUP_INTERVAL_HOURS", 24)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN Railway Variables ichida kiritilishi kerak.")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID Railway Variables ichida kiritilishi kerak.")
