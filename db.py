"""SQLite qatlami.

Muhim: bitta ulanish (connection) ishlatiladi, shuning uchun BARCHA so‘rovlar
bitta asyncio.Lock orqali ketma-ket bajariladi. Ko‘p bosqichli amallar
(`tx()`) esa BEGIN IMMEDIATE ... COMMIT ichida atomik ishlaydi.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from contextlib import asynccontextmanager, suppress

import aiosqlite

from timeutil import iso, parse, utcnow, uz_midnight_as_utc_str

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,name TEXT,username TEXT,balance INTEGER DEFAULT 0,referral_balance INTEGER DEFAULT 0,vip_until TEXT,referred_by INTEGER,rules_accepted INTEGER DEFAULT 0,blocked INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY AUTOINCREMENT,cover_id TEXT,caption TEXT,teaser_id TEXT,channel_message_id INTEGER,channel_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS qualities(id INTEGER PRIMARY KEY AUTOINCREMENT,video_id INTEGER,quality TEXT,file_id TEXT,UNIQUE(video_id,quality),FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS views(user_id INTEGER,video_id INTEGER,PRIMARY KEY(user_id,video_id));
CREATE TABLE IF NOT EXISTS votes(user_id INTEGER,video_id INTEGER,vote INTEGER,PRIMARY KEY(user_id,video_id));
CREATE TABLE IF NOT EXISTS channels(channel_id INTEGER PRIMARY KEY,kind TEXT NOT NULL,join_url TEXT,title TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS topups(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,receipt_id TEXT,status TEXT DEFAULT 'pending',rejection_reason TEXT,user_notice_chat INTEGER,user_notice_msg INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,kind TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS referrals(user_id INTEGER PRIMARY KEY,referrer_id INTEGER,bonus INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY,permissions TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS join_requests(user_id INTEGER,channel_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,channel_id));
CREATE TABLE IF NOT EXISTS gifts(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,amount INTEGER DEFAULT 0,days INTEGER DEFAULT 0,winners_limit INTEGER,claimed INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS gift_claims(gift_id INTEGER,user_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(gift_id,user_id));
CREATE TABLE IF NOT EXISTS broadcasts(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,message_id INTEGER,media_type TEXT,caption TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ad_campaigns(id INTEGER PRIMARY KEY AUTOINCREMENT,source_chat INTEGER,source_message INTEGER,url_buttons TEXT,like_options TEXT,like_layout TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ad_votes(campaign_id INTEGER,user_id INTEGER,option_index INTEGER,PRIMARY KEY(campaign_id,user_id));
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_views_video ON views(video_id);
CREATE INDEX IF NOT EXISTS idx_votes_video ON votes(video_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_topups_user_status ON topups(user_id,status);
CREATE INDEX IF NOT EXISTS idx_topups_unique ON topups(receipt_unique);
CREATE INDEX IF NOT EXISTS idx_videos_msg ON videos(channel_message_id);
CREATE INDEX IF NOT EXISTS idx_users_vip ON users(vip_until);
"""

# (jadval, ustun, ta’rif) — eski bazalar uchun xavfsiz migratsiya
MIGRATIONS = [
    ("users", "referral_balance", "INTEGER DEFAULT 0"),
    ("topups", "rejection_reason", "TEXT"),
    ("topups", "receipt_unique", "TEXT"),
    ("topups", "user_notice_chat", "INTEGER"),
    ("topups", "user_notice_msg", "INTEGER"),
    ("admins", "permissions", "TEXT DEFAULT '[]'"),
    ("channels", "title", "TEXT"),
    ("users", "vip_notified", "TEXT"),  # qaysi vip_until uchun eslatma yuborilgan
    ("users", "vip_notify_hours", "INTEGER"),  # tugashidan necha soat oldin eslatish (1 yoki 24)
]

# VIP tugashidan oldingi eslatma: qisqa (≈1 kunlik) obuna — 1 soat, qolganlari — 1 kun oldin
NOTIFY_SHORT_HOURS = 1
NOTIFY_LONG_HOURS = 24
SHORT_PLAN_MAX = dt.timedelta(hours=36)

DEFAULT_SETTINGS = {
    "card": "8600 0000 0000 0000", "vip_1": "10000", "vip_7": "20000", "vip_30": "30000",
    "bot_info": "", "info_type": "text", "info_file_id": "", "info_caption": "",
    "admin_link": "@admin", "referral_bonus": "500",
}


class Database:
    def __init__(self, path: str = "bot.db"):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._admins: dict[int, list[str]] = {}

    # ------------------------------------------------------------------ infra
    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # isolation_level=None: tranzaksiyalarni faqat o‘zimiz (tx) boshqaramiz
        self.conn = await aiosqlite.connect(self.path, isolation_level=None)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA synchronous=NORMAL")
        await self.conn.execute("PRAGMA busy_timeout=5000")
        await self.conn.executescript(SCHEMA)
        notify_col_added = False
        for table, column, definition in MIGRATIONS:
            cur = await self.conn.execute(f"PRAGMA table_info({table})")
            cols = {r["name"] for r in await cur.fetchall()}
            if column not in cols:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                if column == "vip_notify_hours":
                    notify_col_added = True
        if notify_col_added:
            await self._backfill_notify_hours()
        await self.conn.executescript(INDEXES)
        for k, v in DEFAULT_SETTINGS.items():
            await self.conn.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
        await self._load_admins()

    async def _backfill_notify_hours(self):
        """Eski bazada hozir faol VIPlar uchun eslatma muddatini belgilaydi (bir martalik)."""
        now = utcnow()
        cur = await self.conn.execute("SELECT user_id,vip_until FROM users WHERE vip_until>?", (iso(now),))
        for r in await cur.fetchall():
            until = parse(r["vip_until"])
            if not until:
                continue
            hours = self._notify_hours(until)
            if hours == NOTIFY_SHORT_HOURS:
                # eski kod qisqa obunalarga eslatmani butunlay o‘tkazib yuborgan edi — endi 1 soat oldin yuboriladi
                await self.conn.execute("UPDATE users SET vip_notify_hours=?,vip_notified=NULL WHERE user_id=?",
                                        (hours, r["user_id"]))
            else:
                await self.conn.execute("UPDATE users SET vip_notify_hours=? WHERE user_id=?",
                                        (hours, r["user_id"]))

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

    @asynccontextmanager
    async def tx(self):
        """Atomik tranzaksiya. Ichida faqat `c` (ulanish) bilan ishlang."""
        async with self._lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                with suppress(Exception):
                    await self.conn.execute("ROLLBACK")
                raise
            else:
                await self.conn.execute("COMMIT")

    async def _exec(self, sql, args=()):
        async with self._lock:
            return await self.conn.execute(sql, args)

    async def _one(self, sql, args=()):
        async with self._lock:
            cur = await self.conn.execute(sql, args)
            return await cur.fetchone()

    async def _all(self, sql, args=()):
        async with self._lock:
            cur = await self.conn.execute(sql, args)
            return await cur.fetchall()

    async def backup_to(self, path: str):
        """SQLite online-backup: izchil nusxa (bot ishlayotgan paytda ham)."""
        async with self._lock:
            async with aiosqlite.connect(path) as dst:
                await self.conn.backup(dst)

    # --------------------------------------------------------------- settings
    async def setting(self, k):
        r = await self._one("SELECT value FROM settings WHERE key=?", (k,))
        return r["value"] if r else ""

    async def set_setting(self, k, v):
        await self._exec(
            "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)))

    # ------------------------------------------------------------------ users
    async def add_user(self, uid, name, username, ref=None) -> bool:
        """Yangi foydalanuvchi bo‘lsa True. Ikki marta /start bossa ham xato bermaydi."""
        if ref == uid:
            ref = None
        async with self.tx() as c:
            cur = await c.execute(
                "INSERT OR IGNORE INTO users(user_id,name,username,referred_by) VALUES(?,?,?,?)",
                (uid, name, username, ref))
            created = cur.rowcount == 1
            if not created:
                await c.execute("UPDATE users SET name=?,username=? WHERE user_id=?",
                                (name, username, uid))
        return created

    async def user(self, uid):
        return await self._one("SELECT * FROM users WHERE user_id=?", (uid,))

    async def accept_rules(self, uid):
        await self._exec("UPDATE users SET rules_accepted=1 WHERE user_id=?", (uid,))

    async def set_user_block(self, uid, blocked):
        await self._exec("UPDATE users SET blocked=? WHERE user_id=?", (int(bool(blocked)), uid))

    async def users_page(self, page=1, per=5):
        return await self._all("SELECT user_id,name,username FROM users ORDER BY user_id LIMIT ? OFFSET ?",
                               (per, (page - 1) * per))

    async def total_users(self):
        return (await self._one("SELECT COUNT(*) n FROM users"))["n"]

    async def all_user_ids(self, mode="all"):
        q, args = "SELECT user_id FROM users WHERE blocked=0", ()
        now = iso(utcnow())
        if mode == "vip":
            q += " AND vip_until>?"; args = (now,)
        elif mode == "ordinary":
            q += " AND (vip_until IS NULL OR vip_until<=?)"; args = (now,)
        return [r["user_id"] for r in await self._all(q, args)]

    # -------------------------------------------------------------------- VIP
    @staticmethod
    def _notify_hours(expiry) -> int:
        """Eslatma tugashidan necha soat oldin yuboriladi.
        VIP berilgan paytdagi umumiy qolgan muddat ≈1 kun bo‘lsa (1 kunlik obuna yoki gift) — 1 soat oldin,
        aks holda (1 haftalik, 1 oylik va h.k.) — 1 kun oldin."""
        return NOTIFY_SHORT_HOURS if expiry - utcnow() <= SHORT_PLAN_MAX else NOTIFY_LONG_HOURS

    @staticmethod
    def _vip_expiry(vip_until, days):
        now = utcnow()
        until = parse(vip_until)
        base = until if until and until > now else now
        return base + dt.timedelta(days=days)

    async def vip(self, uid) -> bool:
        r = await self.user(uid)
        until = parse(r["vip_until"]) if r else None
        return bool(until and until > utcnow())

    async def set_vip(self, uid, days):
        async with self.tx() as c:
            cur = await c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
            r = await cur.fetchone()
            expiry = self._vip_expiry(r["vip_until"] if r else None, days)
            await c.execute("UPDATE users SET vip_until=?,vip_notified=NULL,vip_notify_hours=? WHERE user_id=?",
                            (iso(expiry), self._notify_hours(expiry), uid))
        return expiry

    async def revoke_vip(self, uid):
        await self._exec("UPDATE users SET vip_until=NULL,vip_notified=NULL,vip_notify_hours=NULL WHERE user_id=?", (uid,))

    async def vip_expiring(self):
        """Eslatma vaqti kelgan (har birining o‘z muddati: 1 soat yoki 24 soat) va hali eslatma
        yuborilmagan VIP foydalanuvchilar. Har bir qatorda `lead` — eslatma muddati (soat)."""
        now = utcnow()
        rows = await self._all(
            "SELECT user_id,vip_until,vip_notify_hours FROM users WHERE blocked=0 AND vip_until>? "
            "AND (vip_notified IS NULL OR vip_notified!=vip_until)", (iso(now),))
        due = []
        for r in rows:
            until = parse(r["vip_until"])
            lead = int(r["vip_notify_hours"] or NOTIFY_LONG_HOURS)
            if until and until - now <= dt.timedelta(hours=lead):
                due.append({"user_id": r["user_id"], "vip_until": r["vip_until"], "lead": lead})
        return due

    async def mark_vip_notified(self, uid, vip_until):
        await self._exec("UPDATE users SET vip_notified=? WHERE user_id=? AND vip_until=?", (vip_until, uid, vip_until))

    async def purchase_vip(self, uid, days, price):
        """Balansdan (avval referral, so‘ng oddiy) yechib VIP beradi. Yetmasa None."""
        async with self.tx() as c:
            cur = await c.execute(
                "SELECT balance,referral_balance,vip_until FROM users WHERE user_id=?", (uid,))
            u = await cur.fetchone()
            if not u:
                return None
            normal, referral = int(u["balance"] or 0), int(u["referral_balance"] or 0)
            if normal + referral < price:
                return None
            use_ref = min(referral, price)
            use_normal = price - use_ref
            expiry = self._vip_expiry(u["vip_until"], days)
            await c.execute(
                "UPDATE users SET balance=balance-?,referral_balance=referral_balance-?,vip_until=?,"
                "vip_notified=NULL,vip_notify_hours=? WHERE user_id=?",
                (use_normal, use_ref, iso(expiry), self._notify_hours(expiry), uid))
            await c.execute("INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)",
                            (uid, -price, "vip_purchase"))
        return expiry

    async def adjust_balance(self, uid, amount, kind="admin_adjust") -> int:
        """Balansni o‘zgartiradi va HAQIQATDA o‘zgargan miqdorni qaytaradi.
        Ayirishda avval oddiy, keyin referral balansdan olinadi; manfiyga tushmaydi."""
        async with self.tx() as c:
            cur = await c.execute("SELECT balance,referral_balance FROM users WHERE user_id=?", (uid,))
            u = await cur.fetchone()
            if not u:
                return 0
            bal, ref = int(u["balance"] or 0), int(u["referral_balance"] or 0)
            if amount >= 0:
                new_bal, new_ref, actual = bal + amount, ref, amount
            else:
                need = -amount
                take_bal = min(bal, need)
                take_ref = min(ref, need - take_bal)
                new_bal, new_ref, actual = bal - take_bal, ref - take_ref, -(take_bal + take_ref)
            if actual:
                await c.execute("UPDATE users SET balance=?,referral_balance=? WHERE user_id=?",
                                (new_bal, new_ref, uid))
                await c.execute("INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)",
                                (uid, actual, kind))
        return actual

    # ----------------------------------------------------------------- videos
    async def create_video(self, cover, caption, teaser, channel_id, qualities: dict) -> int:
        async with self.tx() as c:
            cur = await c.execute(
                "INSERT INTO videos(cover_id,caption,teaser_id,channel_id) VALUES(?,?,?,?)",
                (cover, caption, teaser, channel_id))
            vid = cur.lastrowid
            for q, f in qualities.items():
                await c.execute("INSERT OR REPLACE INTO qualities(video_id,quality,file_id) VALUES(?,?,?)",
                                (vid, q, f))
        return vid

    async def set_channel_message(self, vid, msg_id):
        await self._exec("UPDATE videos SET channel_message_id=? WHERE id=?", (msg_id, vid))

    async def video(self, vid):
        return await self._one("SELECT * FROM videos WHERE id=?", (vid,))

    async def video_by_message(self, msg_id):
        return await self._one("SELECT * FROM videos WHERE channel_message_id=?", (msg_id,))

    async def qualities(self, vid):
        return await self._all(
            "SELECT quality,file_id FROM qualities WHERE video_id=? ORDER BY CASE quality "
            "WHEN '1080p' THEN 1 WHEN '720p' THEN 2 WHEN '480p' THEN 3 ELSE 4 END", (vid,))

    async def delete_video(self, vid):
        async with self.tx() as c:  # views/votes da FK yo‘q — qo‘lda tozalaymiz
            await c.execute("DELETE FROM votes WHERE video_id=?", (vid,))
            await c.execute("DELETE FROM views WHERE video_id=?", (vid,))
            await c.execute("DELETE FROM videos WHERE id=?", (vid,))

    async def count_view(self, uid, vid) -> bool:
        cur = await self._exec("INSERT OR IGNORE INTO views VALUES(?,?)", (uid, vid))
        return cur.rowcount == 1

    async def view_count(self, vid):
        return (await self._one("SELECT COUNT(*) n FROM views WHERE video_id=?", (vid,)))["n"]

    async def vote(self, uid, vid, val):
        await self._exec(
            "INSERT INTO votes VALUES(?,?,?) ON CONFLICT(user_id,video_id) DO UPDATE SET vote=excluded.vote",
            (uid, vid, val))

    async def vote_counts(self, vid):
        r = await self._one(
            "SELECT SUM(CASE WHEN vote=1 THEN 1 ELSE 0 END) likes,"
            "SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END) dislikes FROM votes WHERE video_id=?", (vid,))
        return int(r["likes"] or 0), int(r["dislikes"] or 0)

    # --------------------------------------------------------------- channels
    async def mandatory(self):
        return await self._all("SELECT * FROM channels WHERE kind='mandatory'")

    async def special_channel(self):
        return await self._one("SELECT * FROM channels WHERE kind='special' LIMIT 1")

    async def all_channels(self):
        return await self._all("SELECT * FROM channels ORDER BY kind,channel_id")

    async def add_channel(self, cid, kind, url=None, title=None):
        await self._exec("INSERT OR REPLACE INTO channels(channel_id,kind,join_url,title) VALUES(?,?,?,?)",
                         (cid, kind, url, title))

    async def set_special_channel(self, cid, url, title):
        async with self.tx() as c:
            await c.execute("DELETE FROM channels WHERE kind='special'")
            await c.execute("INSERT OR REPLACE INTO channels(channel_id,kind,join_url,title) VALUES(?,?,?,?)",
                            (cid, "special", url, title))

    async def delete_channel(self, cid):
        await self._exec("DELETE FROM channels WHERE channel_id=?", (cid,))

    async def add_join_request(self, uid, cid):
        await self._exec("INSERT OR IGNORE INTO join_requests(user_id,channel_id) VALUES(?,?)", (uid, cid))

    async def has_join_request(self, uid, cid):
        return bool(await self._one("SELECT 1 FROM join_requests WHERE user_id=? AND channel_id=?", (uid, cid)))

    async def clear_join_request(self, uid, cid):
        await self._exec("DELETE FROM join_requests WHERE user_id=? AND channel_id=?", (uid, cid))

    # ----------------------------------------------------------------- topups
    async def create_topup(self, uid, amount, file_id, unique_id=None):
        cur = await self._exec(
            "INSERT INTO topups(user_id,amount,receipt_id,receipt_unique) VALUES(?,?,?,?)",
            (uid, amount, file_id, unique_id))
        return cur.lastrowid

    async def set_topup_notice(self, rid, chat_id, message_id):
        await self._exec("UPDATE topups SET user_notice_chat=?,user_notice_msg=? WHERE id=?",
                         (chat_id, message_id, rid))

    async def receipt_seen(self, unique_id) -> bool:
        if not unique_id:
            return False
        return bool(await self._one("SELECT 1 FROM topups WHERE receipt_unique=? LIMIT 1", (unique_id,)))

    async def pending_count(self, uid):
        return (await self._one("SELECT COUNT(*) n FROM topups WHERE user_id=? AND status='pending'", (uid,)))["n"]

    async def topup(self, rid):
        return await self._one("SELECT * FROM topups WHERE id=?", (rid,))

    async def pending_topup(self, rid):
        return await self._one("SELECT * FROM topups WHERE id=? AND status='pending'", (rid,))

    async def approve_topup(self, rid):
        async with self.tx() as c:
            cur = await c.execute("SELECT * FROM topups WHERE id=? AND status='pending'", (rid,))
            r = await cur.fetchone()
            if not r:
                return None
            await c.execute("UPDATE topups SET status='approved' WHERE id=?", (rid,))
            await c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r["amount"], r["user_id"]))
            await c.execute("INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)",
                            (r["user_id"], r["amount"], "topup"))
        return r

    async def reject_topup(self, rid, reason=None):
        async with self.tx() as c:
            cur = await c.execute("SELECT * FROM topups WHERE id=? AND status='pending'", (rid,))
            r = await cur.fetchone()
            if not r:
                return None
            await c.execute("UPDATE topups SET status='rejected',rejection_reason=? WHERE id=?", (reason, rid))
        return r

    # -------------------------------------------------------------- referrals
    async def referrals_count(self, uid):
        return (await self._one("SELECT COUNT(*) n FROM referrals WHERE referrer_id=?", (uid,)))["n"]

    async def credit_referral(self, new_user, referrer, bonus) -> bool:
        if not referrer or referrer == new_user:
            return False
        try:
            async with self.tx() as c:
                cur = await c.execute("SELECT 1 FROM referrals WHERE user_id=?", (new_user,))
                if await cur.fetchone():
                    return False
                cur = await c.execute("SELECT blocked,rules_accepted FROM users WHERE user_id=?", (referrer,))
                r = await cur.fetchone()
                if not r or r["blocked"] or not r["rules_accepted"]:
                    return False
                await c.execute("INSERT INTO referrals(user_id,referrer_id,bonus) VALUES(?,?,?)",
                                (new_user, referrer, bonus))
                await c.execute(
                    "UPDATE users SET referral_balance=COALESCE(referral_balance,0)+? WHERE user_id=?",
                    (bonus, referrer))
                await c.execute("INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)",
                                (referrer, bonus, "referral"))
            return True
        except Exception:
            log.exception("Referral hisoblashda xato (new=%s, referrer=%s)", new_user, referrer)
            return False

    # ----------------------------------------------------------------- admins
    async def _load_admins(self):
        self._admins = {}
        for r in await self._all("SELECT user_id,permissions FROM admins"):
            self._admins[r["user_id"]] = self._parse_perms(r["permissions"])

    @staticmethod
    def _parse_perms(raw):
        try:
            data = json.loads(raw or "[]")
            return list(data) if isinstance(data, list) else []
        except Exception:
            return []

    def admin_permissions(self, uid):
        """Admin bo‘lmasa None, aks holda huquqlar ro‘yxati (xotiradan — tezkor)."""
        return self._admins.get(uid)

    def is_admin(self, uid) -> bool:
        return uid in self._admins

    def admins_with_permission(self, permission):
        return [u for u, p in self._admins.items() if permission in p]

    async def set_admin(self, uid, permissions):
        await self._exec(
            "INSERT INTO admins(user_id,permissions) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET permissions=excluded.permissions",
            (uid, json.dumps(list(permissions), ensure_ascii=False)))
        self._admins[uid] = list(permissions)

    async def remove_admin(self, uid):
        await self._exec("DELETE FROM admins WHERE user_id=?", (uid,))
        self._admins.pop(uid, None)

    # ------------------------------------------------------------------ gifts
    async def create_gift(self, kind, amount, days, limit):
        cur = await self._exec("INSERT INTO gifts(kind,amount,days,winners_limit) VALUES(?,?,?,?)",
                               (kind, amount, days, limit))
        return cur.lastrowid

    async def claim_gift(self, gid, uid):
        """(status, gift, last) — status: won/closed/nouser/vip/already/late.
        Hammasi bitta tranzaksiyada: limitdan ortiq g‘olib bo‘lmaydi, sovg‘a darhol beriladi."""
        async with self.tx() as c:
            cur = await c.execute("SELECT * FROM gifts WHERE id=? AND active=1", (gid,))
            g = await cur.fetchone()
            if not g:
                return "closed", None, False
            cur = await c.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,))
            u = await cur.fetchone()
            if not u:
                return "nouser", g, False
            until = parse(u["vip_until"])
            if g["kind"] == "vip" and until and until > utcnow():
                return "vip", g, False
            cur = await c.execute("SELECT 1 FROM gift_claims WHERE gift_id=? AND user_id=?", (gid, uid))
            if await cur.fetchone():
                return "already", g, False
            if g["claimed"] >= g["winners_limit"]:
                return "late", g, False
            await c.execute("INSERT INTO gift_claims(gift_id,user_id) VALUES(?,?)", (gid, uid))
            await c.execute("UPDATE gifts SET claimed=claimed+1 WHERE id=?", (gid,))
            if g["kind"] == "money":
                await c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (g["amount"], uid))
                await c.execute("INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)",
                                (uid, g["amount"], "gift"))
            else:
                expiry = self._vip_expiry(u["vip_until"], g["days"])
                await c.execute("UPDATE users SET vip_until=?,vip_notified=NULL,vip_notify_hours=? WHERE user_id=?",
                                (iso(expiry), self._notify_hours(expiry), uid))
            last = g["claimed"] + 1 >= g["winners_limit"]
        return "won", g, last

    async def gift_winners(self, gid):
        return await self._all(
            "SELECT u.user_id,u.name,u.username FROM gift_claims g JOIN users u ON u.user_id=g.user_id "
            "WHERE g.gift_id=? ORDER BY g.created_at", (gid,))

    # -------------------------------------------------------------------- ads
    async def create_ad_campaign(self, source_chat, source_message, url_buttons, like_options, like_layout):
        dump = lambda x: json.dumps(x, ensure_ascii=False)  # noqa: E731
        cur = await self._exec(
            "INSERT INTO ad_campaigns(source_chat,source_message,url_buttons,like_options,like_layout) VALUES(?,?,?,?,?)",
            (source_chat, source_message, dump(url_buttons), dump(like_options), dump(like_layout)))
        return cur.lastrowid

    async def ad_campaign(self, cid):
        return await self._one("SELECT * FROM ad_campaigns WHERE id=?", (cid,))

    async def ad_vote(self, cid, uid, option):
        await self._exec(
            "INSERT INTO ad_votes(campaign_id,user_id,option_index) VALUES(?,?,?) "
            "ON CONFLICT(campaign_id,user_id) DO UPDATE SET option_index=excluded.option_index",
            (cid, uid, option))

    async def ad_vote_counts(self, cid):
        rows = await self._all(
            "SELECT option_index,COUNT(*) n FROM ad_votes WHERE campaign_id=? GROUP BY option_index", (cid,))
        return {r["option_index"]: r["n"] for r in rows}

    # ------------------------------------------------------------------ stats
    async def stats(self):
        now = iso(utcnow())
        sqls = {
            "users": ("SELECT COUNT(*) n FROM users", ()),
            "today": ("SELECT COUNT(*) n FROM users WHERE created_at>=?", (uz_midnight_as_utc_str(),)),
            "vip": ("SELECT COUNT(*) n FROM users WHERE vip_until>?", (now,)),
            "ref": ("SELECT COUNT(*) n FROM referrals", ()),
            "videos": ("SELECT COUNT(*) n FROM videos", ()),
            "money": ("SELECT COALESCE(SUM(amount),0) n FROM transactions WHERE kind='topup'", ()),
        }
        return {k: (await self._one(s, a))["n"] for k, (s, a) in sqls.items()}
