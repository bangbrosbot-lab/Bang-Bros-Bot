import aiosqlite, datetime, os

class Database:
    def __init__(self, path='bot.db'):
        self.path=path; self.conn=None
    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        self.conn=await aiosqlite.connect(self.path); self.conn.row_factory=aiosqlite.Row
        await self.conn.execute('PRAGMA foreign_keys=ON')
        await self.conn.execute('PRAGMA journal_mode=WAL')
        await self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,name TEXT,username TEXT,balance INTEGER DEFAULT 0,referral_balance INTEGER DEFAULT 0,vip_until TEXT,referred_by INTEGER,rules_accepted INTEGER DEFAULT 0,blocked INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY AUTOINCREMENT,cover_id TEXT,caption TEXT,teaser_id TEXT,channel_message_id INTEGER,channel_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS qualities(id INTEGER PRIMARY KEY AUTOINCREMENT,video_id INTEGER,quality TEXT,file_id TEXT,UNIQUE(video_id,quality),FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS views(user_id INTEGER,video_id INTEGER,PRIMARY KEY(user_id,video_id));
        CREATE TABLE IF NOT EXISTS votes(user_id INTEGER,video_id INTEGER,vote INTEGER,PRIMARY KEY(user_id,video_id));
        CREATE TABLE IF NOT EXISTS channels(channel_id INTEGER PRIMARY KEY,kind TEXT NOT NULL,join_url TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS topups(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,receipt_id TEXT,status TEXT DEFAULT 'pending',rejection_reason TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,kind TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS referrals(user_id INTEGER PRIMARY KEY,referrer_id INTEGER,bonus INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY,permissions TEXT DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS join_requests(user_id INTEGER,channel_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,channel_id));
        CREATE TABLE IF NOT EXISTS gifts(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,amount INTEGER DEFAULT 0,days INTEGER DEFAULT 0,winners_limit INTEGER,claimed INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS gift_claims(gift_id INTEGER,user_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(gift_id,user_id));
        CREATE TABLE IF NOT EXISTS broadcasts(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,message_id INTEGER,media_type TEXT,caption TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        # Safe migrations for databases created by earlier bot versions.
        for table, column, definition in [
            ('users','referral_balance','INTEGER DEFAULT 0'),
            ('topups','rejection_reason','TEXT'),
            ('admins','permissions',"TEXT DEFAULT '[]'"),
        ]:
            cur=await self.conn.execute(f'PRAGMA table_info({table})')
            cols={r['name'] for r in await cur.fetchall()}
            if column not in cols:
                await self.conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        defaults={'card':'8600 0000 0000 0000','vip_1':'10000','vip_7':'20000','vip_30':'30000','bot_info':'','info_type':'text','info_file_id':'','info_caption':'','admin_link':'@admin','referral_bonus':'500'}
        for k,v in defaults.items(): await self.conn.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(k,v))
        await self.conn.commit()
    async def close(self):
        if self.conn: await self.conn.close()
    async def setting(self,k):
        c=await self.conn.execute('SELECT value FROM settings WHERE key=?',(k,)); r=await c.fetchone(); return r['value'] if r else ''
    async def set_setting(self,k,v): await self.conn.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v))); await self.conn.commit()
    async def add_user(self,u,name,username,ref=None):
        r=await self.user(u)
        if r:
            await self.conn.execute('UPDATE users SET name=?,username=? WHERE user_id=?',(name,username,u)); await self.conn.commit(); return False
        if ref==u: ref=None
        await self.conn.execute('INSERT INTO users(user_id,name,username,referred_by) VALUES(?,?,?,?)',(u,name,username,ref)); await self.conn.commit(); return True
    async def user(self,u):
        c=await self.conn.execute('SELECT * FROM users WHERE user_id=?',(u,)); return await c.fetchone()
    async def vip(self,u):
        r=await self.user(u)
        if not r or not r['vip_until']: return False
        try: return datetime.datetime.fromisoformat(r['vip_until'])>datetime.datetime.now()
        except: return False
    async def set_vip(self,u,days):
        r=await self.user(u); now=datetime.datetime.now(); until=None
        if r and r['vip_until']:
            try: until=datetime.datetime.fromisoformat(r['vip_until'])
            except: pass
        base=until if until and until>now else now; expiry=base+datetime.timedelta(days=days)
        await self.conn.execute('UPDATE users SET vip_until=? WHERE user_id=?',(expiry.isoformat(),u)); await self.conn.commit(); return expiry
    async def revoke_vip(self,u): await self.conn.execute('UPDATE users SET vip_until=NULL WHERE user_id=?',(u,)); await self.conn.commit()
    async def purchase_vip(self, uid, days, price):
        await self.conn.execute('BEGIN IMMEDIATE')
        try:
            c=await self.conn.execute('SELECT balance,referral_balance,vip_until FROM users WHERE user_id=?',(uid,)); u=await c.fetchone()
            if not u:
                await self.conn.rollback(); return None
            normal=int(u['balance'] or 0); referral=int(u['referral_balance'] or 0)
            if normal+referral < price:
                await self.conn.rollback(); return None
            use_ref=min(referral,price); use_normal=price-use_ref
            now=datetime.datetime.now(); until=None
            if u['vip_until']:
                try: until=datetime.datetime.fromisoformat(u['vip_until'])
                except Exception: pass
            base=until if until and until>now else now
            expiry=base+datetime.timedelta(days=days)
            await self.conn.execute('UPDATE users SET balance=balance-?,referral_balance=referral_balance-?,vip_until=? WHERE user_id=?',(use_normal,use_ref,expiry.isoformat(),uid))
            await self.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(uid,-price,'vip_purchase'))
            await self.conn.commit(); return expiry
        except Exception:
            await self.conn.rollback(); raise
    async def count_view(self,u,v):
        c=await self.conn.execute('INSERT OR IGNORE INTO views VALUES(?,?)',(u,v)); await self.conn.commit(); return c.rowcount==1
    async def view_count(self,v):
        c=await self.conn.execute('SELECT COUNT(*) n FROM views WHERE video_id=?',(v,)); return (await c.fetchone())['n']
    async def add_video(self,cover,caption,teaser,channel_id,msg_id):
        c=await self.conn.execute('INSERT INTO videos(cover_id,caption,teaser_id,channel_id,channel_message_id) VALUES(?,?,?,?,?)',(cover,caption,teaser,channel_id,msg_id)); await self.conn.commit(); return c.lastrowid
    async def add_quality(self,v,q,f): await self.conn.execute('INSERT OR REPLACE INTO qualities(video_id,quality,file_id) VALUES(?,?,?)',(v,q,f)); await self.conn.commit()
    async def qualities(self,v):
        c=await self.conn.execute("SELECT quality,file_id FROM qualities WHERE video_id=? ORDER BY CASE quality WHEN '1080p' THEN 1 WHEN '720p' THEN 2 WHEN '480p' THEN 3 ELSE 4 END",(v,)); return await c.fetchall()
    async def video(self,v):
        c=await self.conn.execute('SELECT * FROM videos WHERE id=?',(v,)); return await c.fetchone()
    async def vote(self,u,v,val): await self.conn.execute('INSERT INTO votes VALUES(?,?,?) ON CONFLICT(user_id,video_id) DO UPDATE SET vote=excluded.vote',(u,v,val)); await self.conn.commit()
    async def delete_video(self,v): await self.conn.execute('DELETE FROM videos WHERE id=?',(v,)); await self.conn.commit()
    async def mandatory(self):
        c=await self.conn.execute("SELECT * FROM channels WHERE kind='mandatory'"); return await c.fetchall()
    async def all_channels(self):
        c=await self.conn.execute('SELECT * FROM channels ORDER BY kind,channel_id'); return await c.fetchall()
    async def add_channel(self,cid,kind,url=None): await self.conn.execute('INSERT OR REPLACE INTO channels VALUES(?,?,?)',(cid,kind,url)); await self.conn.commit()
    async def delete_channel(self,cid): await self.conn.execute('DELETE FROM channels WHERE channel_id=?',(cid,)); await self.conn.commit()
    async def add_join_request(self,u,c): await self.conn.execute('INSERT OR IGNORE INTO join_requests(user_id,channel_id) VALUES(?,?)',(u,c)); await self.conn.commit()
    async def has_join_request(self,u,c):
        x=await self.conn.execute('SELECT 1 FROM join_requests WHERE user_id=? AND channel_id=?',(u,c)); return bool(await x.fetchone())
    async def stats(self):
        now=datetime.datetime.now(); today=now.strftime('%Y-%m-%d 00:00:00'); q={}
        sqls={'users':('SELECT COUNT(*) n FROM users',()),'today':('SELECT COUNT(*) n FROM users WHERE created_at>=?',(today,)),'vip':('SELECT COUNT(*) n FROM users WHERE vip_until>?',(now.isoformat(),)),'ref':('SELECT COUNT(*) n FROM referrals',()),'videos':('SELECT COUNT(*) n FROM videos',()),'money':("SELECT COALESCE(SUM(amount),0) n FROM transactions WHERE kind='topup'",())}
        for k,(s,a) in sqls.items():
            c=await self.conn.execute(s,a); q[k]=(await c.fetchone())['n']
        return q
    async def users_page(self,page=1,per=5):
        c=await self.conn.execute('SELECT user_id,name,username FROM users ORDER BY user_id LIMIT ? OFFSET ?',(per,(page-1)*per)); return await c.fetchall()
    async def total_users(self):
        c=await self.conn.execute('SELECT COUNT(*) n FROM users'); return (await c.fetchone())['n']
    async def create_topup(self,u,a,f):
        c=await self.conn.execute('INSERT INTO topups(user_id,amount,receipt_id) VALUES(?,?,?)',(u,a,f)); await self.conn.commit(); return c.lastrowid
    async def pending_topup(self,rid):
        c=await self.conn.execute("SELECT * FROM topups WHERE id=? AND status='pending'",(rid,)); return await c.fetchone()
    async def approve_topup(self,rid):
        await self.conn.execute('BEGIN IMMEDIATE')
        try:
            c=await self.conn.execute("SELECT * FROM topups WHERE id=? AND status='pending'",(rid,)); r=await c.fetchone()
            if not r:
                await self.conn.rollback(); return None
            cur=await self.conn.execute("UPDATE topups SET status='approved' WHERE id=? AND status='pending'",(rid,))
            if cur.rowcount != 1:
                await self.conn.rollback(); return None
            await self.conn.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(r['amount'],r['user_id']))
            await self.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(r['user_id'],r['amount'],'topup'))
            await self.conn.commit(); return r
        except Exception:
            await self.conn.rollback(); raise
    async def reject_topup(self,rid):
        await self.conn.execute('BEGIN IMMEDIATE')
        try:
            c=await self.conn.execute("SELECT * FROM topups WHERE id=? AND status='pending'",(rid,)); r=await c.fetchone()
            if not r:
                await self.conn.rollback(); return None
            cur=await self.conn.execute("UPDATE topups SET status='rejected' WHERE id=? AND status='pending'",(rid,))
            if cur.rowcount != 1:
                await self.conn.rollback(); return None
            await self.conn.commit(); return r
        except Exception:
            await self.conn.rollback(); raise
    async def referrals_count(self,u):
        c=await self.conn.execute('SELECT COUNT(*) n FROM referrals WHERE referrer_id=?',(u,)); return (await c.fetchone())['n']
    async def credit_referral(self,new_user,referrer,bonus):
        if not referrer or referrer==new_user: return False
        await self.conn.execute('BEGIN IMMEDIATE')
        try:
            c=await self.conn.execute('SELECT 1 FROM referrals WHERE user_id=?',(new_user,))
            if await c.fetchone():
                await self.conn.rollback(); return False
            r=await self.user(referrer)
            if not r or r['blocked'] or not r['rules_accepted']:
                await self.conn.rollback(); return False
            await self.conn.execute('INSERT INTO referrals(user_id,referrer_id,bonus) VALUES(?,?,?)',(new_user,referrer,bonus))
            await self.conn.execute('UPDATE users SET referral_balance=COALESCE(referral_balance,0)+? WHERE user_id=?',(bonus,referrer))
            await self.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(referrer,bonus,'referral'))
            await self.conn.commit(); return True
        except Exception:
            await self.conn.rollback()
            return False
    async def vote_counts(self, video_id):
        c=await self.conn.execute('SELECT SUM(CASE WHEN vote=1 THEN 1 ELSE 0 END) likes,SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END) dislikes FROM votes WHERE video_id=?',(video_id,))
        r=await c.fetchone(); return int(r['likes'] or 0),int(r['dislikes'] or 0)
    async def admin_permissions(self, uid):
        if uid == 0: return []
        c=await self.conn.execute('SELECT permissions FROM admins WHERE user_id=?',(uid,)); r=await c.fetchone()
        if not r: return None
        import json
        try: return json.loads(r['permissions'] or '[]')
        except Exception: return []
    async def is_admin(self, uid):
        return await self.admin_permissions(uid) is not None
    async def set_admin(self, uid, permissions):
        import json
        await self.conn.execute('INSERT INTO admins(user_id,permissions) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET permissions=excluded.permissions',(uid,json.dumps(permissions,ensure_ascii=False)))
        await self.conn.commit()
    async def remove_admin(self, uid):
        await self.conn.execute('DELETE FROM admins WHERE user_id=?',(uid,)); await self.conn.commit()
    async def set_user_block(self, uid, blocked):
        await self.conn.execute('UPDATE users SET blocked=? WHERE user_id=?',(int(bool(blocked)),uid)); await self.conn.commit()
    async def adjust_balance(self, uid, amount, kind='admin_adjust'):
        await self.conn.execute('UPDATE users SET balance=MAX(0,balance+?) WHERE user_id=?',(amount,uid))
        await self.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(uid,amount,kind)); await self.conn.commit()
    async def reject_topup_with_reason(self, rid, reason):
        await self.conn.execute('BEGIN IMMEDIATE')
        try:
            c=await self.conn.execute("SELECT * FROM topups WHERE id=? AND status='pending'",(rid,)); r=await c.fetchone()
            if not r:
                await self.conn.rollback(); return None
            cur=await self.conn.execute("UPDATE topups SET status='rejected',rejection_reason=? WHERE id=? AND status='pending'",(reason,rid))
            if cur.rowcount != 1:
                await self.conn.rollback(); return None
            await self.conn.commit(); return r
        except Exception:
            await self.conn.rollback(); raise
    async def create_gift(self,kind,amount,days,limit):
        c=await self.conn.execute('INSERT INTO gifts(kind,amount,days,winners_limit) VALUES(?,?,?,?)',(kind,amount,days,limit)); await self.conn.commit(); return c.lastrowid
    async def claim_gift(self,gid,uid):
        c=await self.conn.execute('SELECT * FROM gifts WHERE id=? AND active=1',(gid,)); g=await c.fetchone()
        if not g: return 'closed',None
        u=await self.user(uid)
        if not u: return 'nouser',g
        if g['kind']=='vip' and await self.vip(uid): return 'vip',g
        c=await self.conn.execute('SELECT 1 FROM gift_claims WHERE gift_id=? AND user_id=?',(gid,uid))
        if await c.fetchone(): return 'already',g
        if g['claimed']>=g['winners_limit']: return 'late',g
        await self.conn.execute('INSERT INTO gift_claims(gift_id,user_id) VALUES(?,?)',(gid,uid))
        await self.conn.execute('UPDATE gifts SET claimed=claimed+1 WHERE id=?',(gid,))
        if g['kind']=='money': await self.conn.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(g['amount'],uid)); await self.conn.execute('INSERT INTO transactions(user_id,amount,kind) VALUES(?,?,?)',(uid,g['amount'],'gift'))
        await self.conn.commit(); return 'won',g
    async def gift_winners(self,gid):
        c=await self.conn.execute('SELECT u.user_id,u.name,u.username FROM gift_claims g JOIN users u ON u.user_id=g.user_id WHERE g.gift_id=? ORDER BY g.created_at',(gid,)); return await c.fetchall()
    async def all_user_ids(self,mode='all'):
        q='SELECT user_id FROM users WHERE blocked=0'; args=()
        if mode=='vip': q+=' AND vip_until>?'; args=(datetime.datetime.now().isoformat(),)
        elif mode=='ordinary': q+=' AND (vip_until IS NULL OR vip_until<=?)'; args=(datetime.datetime.now().isoformat(),)
        c=await self.conn.execute(q,args); return [r['user_id'] for r in await c.fetchall()]
