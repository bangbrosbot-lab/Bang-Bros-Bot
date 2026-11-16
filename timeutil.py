"""Vaqt yordamchilari.

Bazada vaqt UTC (naive) ko‘rinishida saqlanadi (Railway serveri UTC da ishlaydi,
shuning uchun eski ma’lumotlar bilan mos). Foydalanuvchiga esa Toshkent vaqti
(UTC+5, yozgi vaqt yo‘q) ko‘rsatiladi.
"""
from __future__ import annotations

import datetime as dt

UZ_OFFSET = dt.timedelta(hours=5)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def iso(value: dt.datetime) -> str:
    return value.isoformat(timespec="seconds")


def parse(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def fmt_local(value: str | dt.datetime | None) -> str:
    if isinstance(value, str):
        value = parse(value)
    if not value:
        return "—"
    return (value + UZ_OFFSET).strftime("%d.%m.%Y %H:%M")


def uz_midnight_as_utc_str() -> str:
    """Toshkentdagi bugungi kun boshlanishi (UTC, CURRENT_TIMESTAMP formatida)."""
    local = utcnow() + UZ_OFFSET
    start = local.replace(hour=0, minute=0, second=0, microsecond=0) - UZ_OFFSET
    return start.strftime("%Y-%m-%d %H:%M:%S")
