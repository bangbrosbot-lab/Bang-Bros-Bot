from aiogram.filters import BaseFilter

from config import is_owner
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
    if is_owner(uid):
        return True
    perms = db.admin_permissions(uid)
    return perms is not None and permission in perms


def grantable_permissions(db: Database, uid: int) -> list[str]:
    """Admin boshqalarga faqat o‘zida bor huquqlarni bera oladi (bosh admin — hammasini)."""
    if is_owner(uid):
        return list(PERMISSIONS)
    perms = db.admin_permissions(uid) or []
    return [k for k in PERMISSIONS if k in perms]


def can_remove_admin(db: Database, actor: int, target: int) -> bool:
    """Bosh admin — istalgan adminni; qolganlar faqat o‘zi tayinlagan adminni olishi mumkin."""
    if is_owner(target) or actor == target or not db.is_admin(target):
        return False
    if is_owner(actor):
        return True
    return has_permission(db, actor, "admin_manage") and db.admin_appointed_by(target) == actor


class AdminOnly(BaseFilter):
    async def __call__(self, event, db: Database) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and (is_owner(user.id) or db.is_admin(user.id)))
