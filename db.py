import sqlite3, os
from contextlib import contextmanager
from config import settings

def get_db_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(settings.DATABASE_URL.replace("sqlite:///", ""))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def db_session():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db_session() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE,
            tg_username TEXT, tg_first_name TEXT, role TEXT DEFAULT 'user',
            tier TEXT DEFAULT 'free', is_blocked BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS telegram_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            phone TEXT NOT NULL, session_file TEXT NOT NULL, is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            handle TEXT NOT NULL, source TEXT, language TEXT DEFAULT 'ru',
            status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id), UNIQUE(user_id, handle));
        CREATE TABLE IF NOT EXISTS user_activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            action TEXT NOT NULL, ip_address TEXT, user_agent TEXT,
            device_fingerprint TEXT, details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS sent_messages_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            telegram_account_id INTEGER, recipient_username TEXT, message_text TEXT,
            status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE, ip_address TEXT, user_agent TEXT,
            device_fingerprint TEXT, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS site_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            title TEXT NOT NULL, message TEXT NOT NULL, is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS access_whitelist (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE,
            tg_username TEXT, note TEXT, added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
            tg_id INTEGER, tg_username TEXT, user_id INTEGER,
            ip_address TEXT, user_agent TEXT, detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)
        # Bootstrap whitelist + admin from env on first run.
        _bootstrap_access(conn)

def _bootstrap_access(conn):
    """Seed the whitelist with the configured admin so the owner can always log in."""
    if settings.ADMIN_TELEGRAM_ID:
        conn.execute("INSERT OR IGNORE INTO access_whitelist (tg_id, tg_username, note) VALUES (?,?,?)",
                     (settings.ADMIN_TELEGRAM_ID, settings.ADMIN_TELEGRAM_USERNAME, 'admin (bootstrap)'))

def _norm_username(u):
    return (u or '').lstrip('@').strip().lower()

def log_security_event(event_type, tg_id=None, tg_username=None, user_id=None,
                       ip=None, ua=None, detail=''):
    with db_session() as conn:
        conn.execute("""INSERT INTO security_events
            (event_type, tg_id, tg_username, user_id, ip_address, user_agent, detail)
            VALUES (?,?,?,?,?,?,?)""",
            (event_type, tg_id, tg_username, user_id, ip, ua, detail))

def is_whitelisted(tg_id, username=''):
    admin_u = _norm_username(settings.ADMIN_TELEGRAM_USERNAME)
    if bool(settings.ADMIN_TELEGRAM_ID) and tg_id == settings.ADMIN_TELEGRAM_ID:
        return True
    with db_session() as conn:
        row = conn.execute("SELECT 1 FROM access_whitelist WHERE tg_id=?", (tg_id,)).fetchone()
        if row:
            return True
        if username:
            row = conn.execute("SELECT 1 FROM access_whitelist WHERE lower(tg_username)=?",
                               (_norm_username(username),)).fetchone()
            if row:
                return True
    return bool(admin_u) and _norm_username(username) == admin_u

def list_whitelist():
    with db_session() as conn:
        return conn.execute("SELECT * FROM access_whitelist ORDER BY created_at DESC").fetchall()

def add_to_whitelist(tg_id=None, tg_username=None, note='', added_by=None):
    tg_username = _norm_username(tg_username) if tg_username else None
    with db_session() as conn:
        conn.execute("""INSERT OR IGNORE INTO access_whitelist (tg_id, tg_username, note, added_by)
            VALUES (?,?,?,?)""", (tg_id, tg_username, note, added_by))
        # Un-block any pending user that now matches the whitelist.
        if tg_id:
            conn.execute("UPDATE users SET is_blocked=0 WHERE tg_id=?", (tg_id,))

def remove_from_whitelist(wid):
    with db_session() as conn:
        conn.execute("DELETE FROM access_whitelist WHERE id=?", (wid,))

def get_security_events(limit=100):
    with db_session() as conn:
        return conn.execute("SELECT * FROM security_events ORDER BY created_at DESC LIMIT ?",
                            (limit,)).fetchall()

def find_or_create_tg_user(tg_id, username='', first_name=''):
    admin_u = _norm_username(settings.ADMIN_TELEGRAM_USERNAME)
    is_admin = (bool(admin_u) and _norm_username(username) == admin_u) or \
               (bool(settings.ADMIN_TELEGRAM_ID) and tg_id == settings.ADMIN_TELEGRAM_ID)
    allowed = is_admin or is_whitelisted(tg_id, username)
    with db_session() as conn:
        user = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if user:
            role = 'admin' if is_admin else user['role']
            # Users not on the whitelist stay blocked (revocable access).
            blocked = user['is_blocked'] if allowed else 1
            conn.execute("UPDATE users SET tg_username=?, tg_first_name=?, role=?, is_blocked=? WHERE tg_id=?",
                         (username, first_name, role, blocked, tg_id))
            return conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        # New user: create as pending/blocked unless whitelisted.
        conn.execute("INSERT INTO users (tg_id, tg_username, tg_first_name, role, is_blocked) VALUES (?,?,?,?,?)",
                     (tg_id, username, first_name, 'admin' if is_admin else 'user', 0 if allowed else 1))
        return conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()

def get_user_by_id(uid):
    with db_session() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def get_user_tg_accounts(uid):
    with db_session() as conn:
        return conn.execute("SELECT * FROM telegram_accounts WHERE user_id=? AND is_active=1", (uid,)).fetchall()

def add_tg_account(uid, phone, session_file):
    with db_session() as conn:
        c = conn.execute("SELECT COUNT(*) FROM telegram_accounts WHERE user_id=?", (uid,)).fetchone()[0]
        if c >= settings.MAX_TG_ACCOUNTS:
            return False
        conn.execute("INSERT INTO telegram_accounts (user_id, phone, session_file) VALUES (?,?,?)",
                     (uid, phone, session_file))
        return True

def delete_tg_account(uid, aid):
    with db_session() as conn:
        conn.execute("DELETE FROM telegram_accounts WHERE id=? AND user_id=?", (aid, uid))

def add_leads(uid, handles, source="youtube"):
    with db_session() as conn:
        for h in handles:
            conn.execute("INSERT OR IGNORE INTO leads (user_id, handle, source, language) VALUES (?,?,?,'ru')",
                         (uid, h, source))

def get_pending_leads(uid, limit=100):
    with db_session() as conn:
        return conn.execute("SELECT * FROM leads WHERE user_id=? AND status='pending' LIMIT ?", (uid, limit)).fetchall()

def get_leads_stats(uid):
    with db_session() as conn:
        return conn.execute("""SELECT COUNT(*) total,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pending,
            SUM(CASE WHEN status='verified' THEN 1 ELSE 0 END) verified,
            SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) sent,
            SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
            SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) blocked
            FROM leads WHERE user_id=?""", (uid,)).fetchone()

def update_lead_status(lid, status):
    with db_session() as conn:
        conn.execute("UPDATE leads SET status=? WHERE id=?", (status, lid))

def log_activity(uid, action, ip, ua, fp, details=""):
    with db_session() as conn:
        conn.execute("INSERT INTO user_activity_logs (user_id, action, ip_address, user_agent, device_fingerprint, details) VALUES (?,?,?,?,?,?)",
                     (uid, action, ip, ua, fp, details))

def log_sent_message(uid, accid, recipient, text, status):
    with db_session() as conn:
        conn.execute("INSERT INTO sent_messages_log (user_id, telegram_account_id, recipient_username, message_text, status) VALUES (?,?,?,?,?)",
                     (uid, accid, recipient, text, status))

def log_session(uid, token, ip, ua, fp):
    with db_session() as conn:
        conn.execute("INSERT OR REPLACE INTO user_sessions (user_id, session_token, ip_address, user_agent, device_fingerprint) VALUES (?,?,?,?,?)",
                     (uid, token, ip, ua, fp))

def send_notification(user_id, title, message):
    with db_session() as conn:
        conn.execute("INSERT INTO site_notifications (user_id, title, message) VALUES (?, ?, ?)", (user_id, title, message))

def broadcast_notification(title, message):
    with db_session() as conn:
        users = conn.execute("SELECT id FROM users WHERE is_blocked=0").fetchall()
        for u in users:
            conn.execute("INSERT INTO site_notifications (user_id, title, message) VALUES (?, ?, ?)", (u['id'], title, message))

def get_user_notifications(user_id):
    with db_session() as conn:
        return conn.execute("SELECT * FROM site_notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()

def mark_notification_read(nid, user_id):
    with db_session() as conn:
        conn.execute("UPDATE site_notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, user_id))

def get_unread_notifications_count(user_id):
    with db_session() as conn:
        res = conn.execute("SELECT COUNT(*) FROM site_notifications WHERE user_id=? AND is_read=0", (user_id,)).fetchone()
        return res[0] if res else 0

def get_all_users_stats():
    with db_session() as conn:
        return conn.execute("""SELECT u.id, u.tg_id, u.tg_username, u.tg_first_name, u.tier, u.role, u.is_blocked, u.created_at,
            (SELECT COUNT(*) FROM telegram_accounts WHERE user_id=u.id) tg_count,
            (SELECT COUNT(*) FROM leads WHERE user_id=u.id) leads_count,
            (SELECT COUNT(*) FROM sent_messages_log WHERE user_id=u.id) sent_count,
            (SELECT COUNT(DISTINCT ip_address) FROM user_activity_logs WHERE user_id=u.id) ip_count,
            (SELECT COUNT(DISTINCT device_fingerprint) FROM user_activity_logs WHERE user_id=u.id) device_count,
            (SELECT MAX(created_at) FROM user_activity_logs WHERE user_id=u.id) last_activity
            FROM users u ORDER BY u.created_at DESC""").fetchall()

def get_user_security_insights(uid):
    """Aggregate signals that help detect account sharing / handover.

    Returns unique IPs, devices and user agents (with counts and last-seen),
    plus a simple risk score. Many distinct IPs/devices for one account is the
    main indicator that the account is used by several people.
    """
    with db_session() as conn:
        ips = conn.execute("""SELECT ip_address AS ip, COUNT(*) AS hits,
                MAX(created_at) AS last_seen, MIN(created_at) AS first_seen
            FROM user_activity_logs WHERE user_id=? AND ip_address IS NOT NULL AND ip_address != ''
            GROUP BY ip_address ORDER BY hits DESC LIMIT 50""", (uid,)).fetchall()
        devices = conn.execute("""SELECT device_fingerprint AS fp, COUNT(*) AS hits,
                MAX(created_at) AS last_seen
            FROM user_activity_logs WHERE user_id=? AND device_fingerprint IS NOT NULL AND device_fingerprint != ''
            GROUP BY device_fingerprint ORDER BY hits DESC LIMIT 50""", (uid,)).fetchall()
        agents = conn.execute("""SELECT user_agent AS ua, COUNT(*) AS hits, MAX(created_at) AS last_seen
            FROM user_activity_logs WHERE user_id=? AND user_agent IS NOT NULL AND user_agent != ''
            GROUP BY user_agent ORDER BY hits DESC LIMIT 20""", (uid,)).fetchall()
        span = conn.execute("""SELECT MIN(created_at) AS first_seen, MAX(created_at) AS last_seen,
                COUNT(*) AS total_actions
            FROM user_activity_logs WHERE user_id=?""", (uid,)).fetchone()

    ip_count = len(ips)
    device_count = len(devices)
    ua_count = len(agents)
    # Heuristic risk: more distinct IPs/devices => more likely shared.
    risk = 'low'
    reasons = []
    if ip_count >= 5:
        reasons.append(f'{ip_count} разных IP')
    if device_count >= 3:
        reasons.append(f'{device_count} разных устройств')
    if ua_count >= 4:
        reasons.append(f'{ua_count} разных браузеров')
    if device_count >= 4 or ip_count >= 8:
        risk = 'high'
    elif device_count >= 3 or ip_count >= 5:
        risk = 'medium'

    return {
        "ips": [dict(r) for r in ips],
        "devices": [dict(r) for r in devices],
        "user_agents": [dict(r) for r in agents],
        "ip_count": ip_count,
        "device_count": device_count,
        "ua_count": ua_count,
        "span": dict(span) if span else {},
        "risk": risk,
        "risk_reasons": reasons,
    }

def get_user_offers(uid):
    """Distinct campaign message texts (offers) with how many times each was sent."""
    with db_session() as conn:
        rows = conn.execute("""SELECT message_text AS text, COUNT(*) AS times,
                SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS sent_ok,
                MAX(created_at) AS last_used
            FROM sent_messages_log
            WHERE user_id=? AND message_text IS NOT NULL AND message_text != ''
            GROUP BY message_text ORDER BY times DESC LIMIT 50""", (uid,)).fetchall()
        totals = conn.execute("""SELECT
                COUNT(*) AS total_msgs,
                SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS sent_ok,
                SUM(CASE WHEN status='peer_flood' THEN 1 ELSE 0 END) AS peer_flood,
                SUM(CASE WHEN status LIKE 'error%' THEN 1 ELSE 0 END) AS errors
            FROM sent_messages_log WHERE user_id=?""", (uid,)).fetchone()
    return {"offers": [dict(r) for r in rows], "totals": dict(totals) if totals else {}}

def get_user_details(uid):
    with db_session() as conn:
        user = conn.execute("SELECT id, tg_id, tg_username, tg_first_name, role, tier, is_blocked, created_at FROM users WHERE id=?", (uid,)).fetchone()
        tg = conn.execute("SELECT * FROM telegram_accounts WHERE user_id=?", (uid,)).fetchall()
        acts = conn.execute("SELECT * FROM user_activity_logs WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (uid,)).fetchall()
        msgs = conn.execute("SELECT * FROM sent_messages_log WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (uid,)).fetchall()
        sess = conn.execute("SELECT ip_address, device_fingerprint, last_active, is_active FROM user_sessions WHERE user_id=? AND is_active=1", (uid,)).fetchall()
        return {"user": dict(user) if user else None, "tg_accounts": [dict(a) for a in tg],
                "activities": [dict(a) for a in acts], "messages": [dict(m) for m in msgs],
                "sessions": [dict(s) for s in sess]}

def block_user(uid, blocked=True):
    with db_session() as conn:
        conn.execute("UPDATE users SET is_blocked=? WHERE id=?", (int(blocked), uid))

def get_user_recent_activities(uid, limit=30):
    with db_session() as conn:
        return conn.execute(
            "SELECT action, details, created_at FROM user_activity_logs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)).fetchall()
