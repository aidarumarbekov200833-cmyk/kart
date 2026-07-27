from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from functools import wraps
import os, secrets, hashlib, hmac, time, re
from config import settings
from content import PLATFORM_RULES, AI_ANSWERS, AI_FALLBACK
from ai import answer as ai_answer

PHONE_RE = re.compile(r'^\+?\d{7,15}$')
from db import (init_db, find_or_create_tg_user, get_user_by_id, get_user_tg_accounts,
    add_tg_account, delete_tg_account, add_leads, get_pending_leads, get_leads_stats,
    log_activity, log_session, get_all_users_stats, get_user_details, block_user, get_user_recent_activities,
    send_notification, broadcast_notification, get_user_notifications, mark_notification_read, get_unread_notifications_count,
    get_user_security_insights, get_user_offers,
    is_whitelisted, list_whitelist, add_to_whitelist, remove_from_whitelist,
    log_security_event, get_security_events)
from utils import generate_fingerprint, setup_logging
from extractor import search_youtube_channels
from resolver import verify_leads
from mailer import send_campaign
import threading

app = Flask(__name__)
app.secret_key = settings.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=not settings.DEV_MODE,
    WTF_CSRF_TIME_LIMIT=None,
)
setup_logging(app)

csrf = CSRFProtect(app)
# Telegram calls this endpoint via GET redirect; it is verified by HMAC, so exempt from CSRF.

@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return resp

@app.context_processor
def inject_csrf_token():
    return {'csrf_token': generate_csrf}
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])
init_db()

def _client_ip():
    xff = request.headers.get('X-Forwarded-For', '')
    return xff.split(',')[0].strip() if xff else request.remote_addr

def _is_owner(u):
    """Admin access is bound to the immutable Telegram ID (preferred) or the
    configured admin username. Username can be reassigned in Telegram, so tg_id
    is the primary check."""
    if not u:
        return False
    if settings.ADMIN_TELEGRAM_ID and u['tg_id'] == settings.ADMIN_TELEGRAM_ID:
        return True
    admin_u = (settings.ADMIN_TELEGRAM_USERNAME or '').lstrip('@').lower()
    return u['role'] == 'admin' and bool(admin_u) and (u['tg_username'] or '').lstrip('@').lower() == admin_u

def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if 'user_id' not in session:
            if request.path.startswith('/api') or request.path.startswith('/admin'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        # Revoke access instantly if the user was blocked / removed from whitelist.
        u = get_user_by_id(session['user_id'])
        if not u or u['is_blocked']:
            session.clear()
            if request.path.startswith('/api') or request.path.startswith('/admin'):
                return jsonify({"error": "Forbidden"}), 403
            return redirect(url_for('login'))
        return f(*a, **k)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        u = get_user_by_id(session['user_id'])
        if not _is_owner(u):
            log_security_event('admin_access_denied', tg_id=(u['tg_id'] if u else None),
                               tg_username=(u['tg_username'] if u else None),
                               user_id=session.get('user_id'), ip=_client_ip(),
                               ua=request.headers.get('User-Agent', ''),
                               detail=f'path={request.path}')
            return jsonify({"error": "Forbidden"}), 403
        return f(*a, **k)
    return wrap

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html', bot_username=settings.TELEGRAM_BOT_USERNAME,
                           admin_username=settings.ADMIN_TELEGRAM_USERNAME)

@app.route('/terms')
def terms():
    return render_template('terms.html', rules=PLATFORM_RULES,
                           admin_username=settings.ADMIN_TELEGRAM_USERNAME)

@app.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    auth_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/tg_auth/callback"
    return render_template('login.html', bot_username=settings.TELEGRAM_BOT_USERNAME,
                           auth_url=auth_url)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
@admin_required
def admin():
    return render_template('admin.html')

@app.route('/api/tg_auth/callback', methods=['GET'])
@csrf.exempt
def tg_auth_callback():
    data = request.args.to_dict()
    if not data or 'hash' not in data:
        return redirect(url_for('login'))
    
    check_hash = data.pop('hash')
    # Spec-compliant: include ALL received fields (except hash), sorted by key.
    data_check_arr = [f"{k}={v}" for k, v in sorted(data.items())]
    data_check_string = "\n".join(data_check_arr)
    
    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(hmac_hash, check_hash):
        return "Ошибка авторизации: неверная подпись Telegram", 400
    
    if time.time() - int(data.get('auth_date', 0)) > 86400:
        return "Срок действия авторизации истек", 400
        
    tg_id = int(data['id'])
    username = data.get('username', '')
    first_name = data.get('first_name', '')
    ip = _client_ip()
    ua = request.headers.get('User-Agent', '')

    # Whitelist gate: only explicitly allowed accounts may enter.
    if not is_whitelisted(tg_id, username):
        find_or_create_tg_user(tg_id, username, first_name)  # record as pending/blocked
        log_security_event('login_denied_not_whitelisted', tg_id=tg_id, tg_username=username,
                           ip=ip, ua=ua, detail='not in whitelist')
        return ("Доступ закрыт: ваш аккаунт не в белом списке. "
                f"Обратитесь к администратору: @{settings.ADMIN_TELEGRAM_USERNAME}", 403)

    user = find_or_create_tg_user(tg_id, username, first_name)
    if user['is_blocked']:
        log_security_event('login_denied_blocked', tg_id=tg_id, tg_username=username,
                           user_id=user['id'], ip=ip, ua=ua, detail='blocked')
        return "Ваш аккаунт заблокирован администратором.", 403

    session['user_id'] = user['id']
    session['role'] = user['role']

    log_session(user['id'], secrets.token_hex(16), ip, ua, generate_fingerprint(ua, ip))
    log_activity(user['id'], 'login_telegram_widget', ip, ua, generate_fingerprint(ua, ip))
    log_security_event('login_success', tg_id=tg_id, tg_username=username,
                       user_id=user['id'], ip=ip, ua=ua, detail=f'role={user["role"]}')

    return redirect(url_for('dashboard'))

@app.route('/api/ai/ask', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def ai_ask():
    data = request.json or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({"error": "Пустой вопрос"}), 400
    result = ai_answer(question)
    return jsonify(result)

@app.route('/api/notifications', methods=['GET'])
@login_required
def api_get_notifications():
    uid = session['user_id']
    notifs = get_user_notifications(uid)
    unread = get_unread_notifications_count(uid)
    return jsonify({"notifications": [dict(n) for n in notifs], "unread_count": unread})

@app.route('/api/notifications/<int:nid>/read', methods=['POST'])
@login_required
def api_mark_notification_read(nid):
    mark_notification_read(nid, session['user_id'])
    return jsonify({"success": True})

@app.route('/admin/api/notifications/send', methods=['POST'])
@admin_required
def admin_send_notification():
    data = request.json or {}
    target = data.get('target', 'all')
    title = data.get('title', '').strip()
    message = data.get('message', '').strip()
    if not title or not message:
        return jsonify({"error": "Заполните заголовок и текст"}), 400
    
    if target == 'all':
        broadcast_notification(title, message)
    else:
        try:
            uid = int(target)
            send_notification(uid, title, message)
        except ValueError:
            return jsonify({"error": "Неверный ID пользователя"}), 400
    return jsonify({"success": True, "message": "Уведомление успешно отправлено"})

@app.route('/api/parse', methods=['POST'])
@login_required
def api_parse():
    data = request.json or {}
    kws = data.get('keywords', [])
    mr = min(data.get('max_results', 50), 100)
    uid = session['user_id']
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = request.headers.get('User-Agent', '')
    fp = generate_fingerprint(ua, ip)
    log_activity(uid, f'parse_youtube_started ({len(kws)} keywords, max_results={mr})', ip, ua, fp)

    def _run():
        st = time.time()
        try:
            results = search_youtube_channels(kws, mr)
            add_leads(uid, results)
            elapsed = time.time() - st
            log_activity(uid, f'parse_youtube_completed: {len(results)} leads found ({elapsed:.1f}s)', ip, ua, fp)
        except Exception as e:
            log_activity(uid, f'parse_youtube_error: {str(e)}', ip, ua, fp)

    threading.Thread(target=_run).start()
    return jsonify({"success": True, "message": "Парсинг запущен"})

@app.route('/api/verify', methods=['POST'])
@login_required
def api_verify():
    uid = session['user_id']
    accs = get_user_tg_accounts(uid)
    if not accs:
        return jsonify({"error": "Нет TG-аккаунтов"}), 400
    leads = get_pending_leads(uid, 100)
    if not leads:
        return jsonify({"error": "Нет лидов"}), 400
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = request.headers.get('User-Agent', '')
    fp = generate_fingerprint(ua, ip)
    log_activity(uid, f'verify_leads_started ({len(leads)} pending)', ip, ua, fp)

    def _run():
        st = time.time()
        try:
            verify_leads(leads, accs[0]['session_file'])
            elapsed = time.time() - st
            log_activity(uid, f'verify_leads_completed ({elapsed:.1f}s)', ip, ua, fp)
        except Exception as e:
            log_activity(uid, f'verify_leads_error: {str(e)}', ip, ua, fp)

    threading.Thread(target=_run).start()
    return jsonify({"success": True, "message": "Верификация запущена"})

@app.route('/api/campaign/start', methods=['POST'])
@login_required
def api_campaign_start():
    data = request.json or {}
    text = data.get('message_text','').strip()
    sp = data.get('use_spintax', False)
    if not text:
        return jsonify({"error": "Нужен текст"}), 400
    uid = session['user_id']
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = request.headers.get('User-Agent', '')
    fp = generate_fingerprint(ua, ip)
    log_activity(uid, f'campaign_started (spintax={sp})', ip, ua, fp)

    def _run():
        st = time.time()
        try:
            send_campaign(uid, text, sp)
            elapsed = time.time() - st
            log_activity(uid, f'campaign_completed ({elapsed:.1f}s)', ip, ua, fp)
        except Exception as e:
            log_activity(uid, f'campaign_error: {str(e)}', ip, ua, fp)

    threading.Thread(target=_run).start()
    return jsonify({"success": True, "message": "Рассылка запущена"})

@app.route('/api/telegram-accounts', methods=['GET'])
@login_required
def api_tg_accounts():
    return jsonify([dict(a) for a in get_user_tg_accounts(session['user_id'])])

@app.route('/api/telegram-accounts/add', methods=['POST'])
@login_required
def api_tg_add():
    phone = (request.json or {}).get('phone','').strip()
    if not phone:
        return jsonify({"error": "Нужен номер"}), 400
    if not PHONE_RE.match(phone):
        return jsonify({"error": "Неверный формат номера. Пример: +79001234567"}), 400
    safe_phone = phone.lstrip('+')
    sf = f"data/sessions/{session['user_id']}_{safe_phone}.session"
    if add_tg_account(session['user_id'], phone, sf):
        return jsonify({"success": True})
    return jsonify({"error": f"Лимит {settings.MAX_TG_ACCOUNTS}"}), 403

@app.route('/api/telegram-accounts/<int:aid>', methods=['DELETE'])
@login_required
def api_tg_delete(aid):
    delete_tg_account(session['user_id'], aid)
    return jsonify({"success": True})

@app.route('/api/stats', methods=['GET'])
@login_required
def api_stats():
    return jsonify(dict(get_leads_stats(session['user_id'])))

@app.route('/api/activity', methods=['GET'])
@login_required
def api_activity():
    activities = get_user_recent_activities(session['user_id'], 20)
    result = []
    prev_time = None
    for a in activities:
        created_at = a['created_at']
        duration = ''
        if prev_time:
            try:
                t1 = time.strptime(prev_time, '%Y-%m-%d %H:%M:%S')
                t2 = time.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                diff = abs(time.mktime(t1) - time.mktime(t2))
                if diff < 60:
                    duration = f'{int(diff)}с'
                elif diff < 3600:
                    duration = f'{int(diff/60)}м {int(diff%60)}с'
                else:
                    duration = f'{int(diff/3600)}ч {int((diff%3600)/60)}м'
            except:
                pass
        result.append({
            'action': a['action'],
            'details': a.get('details', ''),
            'created_at': created_at,
            'duration': duration
        })
        prev_time = created_at
    return jsonify({'activities': result})

@app.route('/admin/api/users', methods=['GET'])
@admin_required
def admin_api_users():
    return jsonify([dict(u) for u in get_all_users_stats()])

@app.route('/admin/api/users/<int:uid>', methods=['GET'])
@admin_required
def admin_api_user_details(uid):
    details = get_user_details(uid)
    details['security'] = get_user_security_insights(uid)
    details['offers'] = get_user_offers(uid)
    return jsonify(details)

@app.route('/admin/api/users/<int:uid>/block', methods=['POST'])
@admin_required
def admin_api_block(uid):
    block_user(uid, (request.json or {}).get('blocked', True))
    return jsonify({"success": True})

@app.route('/admin/api/whitelist', methods=['GET'])
@admin_required
def admin_whitelist_list():
    return jsonify([dict(w) for w in list_whitelist()])

@app.route('/admin/api/whitelist', methods=['POST'])
@admin_required
def admin_whitelist_add():
    data = request.json or {}
    raw_id = str(data.get('tg_id', '')).strip()
    username = (data.get('tg_username', '') or '').strip()
    note = (data.get('note', '') or '').strip()
    tg_id = None
    if raw_id:
        if not raw_id.isdigit():
            return jsonify({"error": "tg_id должен быть числом"}), 400
        tg_id = int(raw_id)
    if not tg_id and not username:
        return jsonify({"error": "Укажите tg_id или username"}), 400
    add_to_whitelist(tg_id=tg_id, tg_username=username or None, note=note, added_by=session['user_id'])
    log_security_event('whitelist_add', tg_id=tg_id, tg_username=username,
                       user_id=session['user_id'], ip=_client_ip(),
                       ua=request.headers.get('User-Agent', ''), detail=note)
    return jsonify({"success": True})

@app.route('/admin/api/whitelist/<int:wid>', methods=['DELETE'])
@admin_required
def admin_whitelist_remove(wid):
    remove_from_whitelist(wid)
    log_security_event('whitelist_remove', user_id=session['user_id'], ip=_client_ip(),
                       ua=request.headers.get('User-Agent', ''), detail=f'wid={wid}')
    return jsonify({"success": True})

@app.route('/admin/api/security-events', methods=['GET'])
@admin_required
def admin_security_events():
    return jsonify([dict(e) for e in get_security_events(150)])

@app.route('/health')
@csrf.exempt
@limiter.exempt
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=settings.DEV_MODE)
