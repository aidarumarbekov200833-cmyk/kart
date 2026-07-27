import subprocess, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import sanitize_keyword

# Precompiled patterns for speed.
_PATTERNS = [re.compile(r'@([a-zA-Z0-9_]{5,32})'),
             re.compile(r't\.me/([a-zA-Z0-9_]{5,32})')]

# Handles that are almost never real leads.
BLACKLIST = {
    'youtube', 'telegram', 'support', 'google', 'twitter', 'instagram',
    'facebook', 'tiktok', 'whatsapp', 'linkedin', 'discord', 'admin',
    'official', 'channel', 'group', 'news', 'bot', 'info', 'contact',
}


def extract_telegram_from_description(desc):
    if not desc:
        return []
    users = set()
    for p in _PATTERNS:
        users.update(p.findall(desc))
    out = []
    for u in users:
        lu = u.lower()
        # Skip blacklist and low-signal handles (e.g. all digits, bots).
        if lu in BLACKLIST or lu.endswith('bot') or lu.isdigit():
            continue
        out.append(u)
    return out


def _search_one(kw, max_results):
    kw = sanitize_keyword(kw)
    if not kw:
        return []
    users = []
    try:
        cmd = ["yt-dlp", f"ytsearch{max_results}:{kw}", "--dump-json",
               "--no-warnings", "--ignore-errors", "--skip-download",
               "--flat-playlist", "--socket-timeout", "15"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        for line in r.stdout.split('\n'):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            users.extend(extract_telegram_from_description(data.get('description', '')))
    except subprocess.TimeoutExpired:
        return users
    except FileNotFoundError:
        print("yt-dlp not found. pip install yt-dlp")
    except Exception as e:
        print(f"Error '{kw}': {e}")
    return users


def search_youtube_channels(keywords, max_results=50):
    """Search multiple keywords in parallel; return a deduplicated list of handles."""
    keywords = [k for k in (keywords or []) if k and k.strip()]
    if not keywords:
        return []
    all_users = set()
    # Bounded parallelism keeps it fast without hammering the network.
    workers = min(4, len(keywords))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_search_one, kw, max_results): kw for kw in keywords}
        for fut in as_completed(futures):
            all_users.update(fut.result())
    return list(all_users)
