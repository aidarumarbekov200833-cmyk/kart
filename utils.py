import re, random, hashlib, logging, os
from logging.handlers import RotatingFileHandler

def process_spintax(text):
    def rep(m):
        return random.choice(m.group(1).split('|')).strip()
    return re.sub(r'\{([^{}]+)\}', rep, text)

def generate_fingerprint(ua, ip):
    return hashlib.md5(f"{ua}{ip}".encode()).hexdigest()

def setup_logging(app):
    os.makedirs("data/logs", exist_ok=True)
    h = RotatingFileHandler('data/logs/app.log', maxBytes=10*1024*1024, backupCount=5)
    h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    app.logger.addHandler(h)
    app.logger.setLevel(logging.INFO)

def sanitize_keyword(kw):
    return re.sub(r'[^\w\s\-а-яА-Яa-zA-Z0-9]', '', kw).strip()
