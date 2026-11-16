from aiogram.filters import BaseFilter

from config import ADMIN_ID
from db import Database

PERMISSIONS = {
    "edit": "Edit imkoniyatlari",
    "payments": "Chek tasdiqlash",
    "admin_manage": "Admin qilish/olish",
    "users": "Foydalanuvchilarni ko‘rish",
}


def no_perm_text(permission: str) -> str:
    return ("Afsuski sizni adminlik huquqlaringiz bulardan foydalanishga yetmaydi.\n"
            f"Kerakli huquq: {PERMISSIONS[permission]}")


def has_permission(db: Database, uid: int, permission: str) -> bool:
    if uid == ADMIN_ID:
        return True
    perms = db.admin_permissions(uid)
    return perms is not None and permission in perms


class AdminOnly(BaseFilter):
    async def __call__(self, event, db: Database) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and (user.id == ADMIN_ID or db.is_admin(user.id)))
