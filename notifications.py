"""VIP tugashidan oldin eslatma: 1 kunlik obuna — 1 soat, 1 haftalik/1 oylik/gift — 1 kun oldin."""
import asyncio
import logging

from db import Database
from keyboards import rows_kb
from pushes import push
from timeutil import fmt_local
from utils import safe_call

log = logging.getLogger(__name__)

CHECK_INTERVAL = 5 * 60  # soniya (1 soatlik eslatma aniq vaqtda ketishi uchun tez-tez tekshiriladi)


async def send_vip_expiry_notices(bot, db: Database) -> int:
    """Eslatma har bir VIP muddati uchun faqat bir marta yuboriladi (obuna uzaytirilsa, yangi muddat uchun yana)."""
    sent = 0
    for r in await db.vip_expiring():
        left = "1 soat" if r["lead"] == 1 else "1 kun"
        text = (f"Diqqat! VIP obunangiz tugashiga {left} qoldi.\n"
                f"Tugash vaqti: {fmt_local(r['vip_until'])}\n\n"
                "Videolarni uzilishsiz tomosha qilish uchun obunani hozirdan uzaytiring.")
        await safe_call(lambda uid=r["user_id"]: push(bot, 
            uid, text, reply_markup=rows_kb([("VIP olish", "vipnotice")])))
        await db.mark_vip_notified(r["user_id"], r["vip_until"])  # yetkazilmasa ham qayta urinmaymiz
        sent += 1
        await asyncio.sleep(0.05)
    return sent


async def vip_notice_loop(bot, db: Database) -> None:
    await asyncio.sleep(30)
    while True:
        try:
            await send_vip_expiry_notices(bot, db)
        except Exception:
            log.exception("VIP eslatmalarini yuborishda xato")
        await asyncio.sleep(CHECK_INTERVAL)
