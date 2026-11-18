import logging
import os
import tempfile

from aiogram.types import FSInputFile

log = logging.getLogger(__name__)


async def send_backup(bot, db, chat_id: int, caption: str = "Bang Bros — bazaning eng so‘nggi nusxasi") -> None:
    fd, path = tempfile.mkstemp(prefix="bangbros_backup_", suffix=".db")
    os.close(fd)
    try:
        await db.backup_to(path)
        await bot.send_document(chat_id, FSInputFile(path, filename="bot.db"),
                                caption=caption, protect_content=False)
    finally:
        os.remove(path)
