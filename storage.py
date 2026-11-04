import os
import re
import json
import time
import secrets
import string
from config import (
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    GC_CONFIG_FILE, KEYS_FILE, KEY_PREFIX,
    ADMIN_IDS, _DEFAULT_ADMINS, LIMITS,
)

# ══════════════════════════════════════════════════════════════
# User proxies
# ══════════════════════════════════════════════════════════════
user_proxies: dict = {}

def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return [p for p in val if p]
    return [val] if val else []

def load_user_proxies():
    global user_proxies
    if os.path.exists(USER_PROXY_FILE):
        try:
            with open(USER_PROXY_FILE, 'r') as f:
                raw = json.load(f)
                user_proxies = {int(k): _to_list(v) for k, v in raw.items()}
        except:
            user_proxies = {}

def save_user_proxies():
    try:
        with open(USER_PROXY_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_proxies.items()}, f)
    except:
        pass

def get_user_proxy_list(uid) -> list:
    return list(user_proxies.get(uid, []))

def set_user_proxies(uid, proxies: list):
    user_proxies[uid] = [p for p in proxies if p]
    save_user_proxies()

def remove_user_proxy(uid):
    user_proxies.pop(uid, None)
    save_user_proxies()

user_pool_enabled: dict = {}

def load_user_pool():
    global user_pool_enabled
    if os.path.exists(USER_POOL_FILE):
        try:
            with open(USER_POOL_FILE, 'r') as f:
                user_pool_enabled = {int(k): v for k, v in json.load(f).items()}
        except:
            user_pool_enabled = {}

def save_user_pool():
    try:
        with open(USER_POOL_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_pool_enabled.items()}, f)
    except:
        pass

# ══════════════════════════════════════════════════════════════
# File lists
# ══════════════════════════════════════════════════════════════
def get_file_lines(fp):
    if not os.path.exists(fp):
        return []
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            return [l.strip() for l in f if l.strip()]
    except:
        return []

def load_premium_users(): return get_file_lines(PREMIUM_FILE)
def load_sites():         return get_file_lines(SITES_FILE)
def load_proxies():       return get_file_lines(PROXY_FILE)

# ══════════════════════════════════════════════════════════════
# Access
# ══════════════════════════════════════════════════════════════
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS or uid in _DEFAULT_ADMINS

def is_premium(uid: int) -> bool:
    if is_admin(uid):
        return True
    return str(uid) in load_premium_users()

def get_user_limit(uid: int) -> int:
    if is_admin(uid):
        return LIMITS["admin"]
    if is_premium(uid):
        return LIMITS["premium"]
    return 0

def get_proxies_for_user(uid: int) -> list:
    """
    Admin:    own proxies + pool (if pool toggle on) — pool is fine.
    Premium:  OWN proxies only. If empty -> returns [] so check refuses.
              Pool is appended only when user_pool_enabled is True AND
              they've set at least one personal proxy.
    """
    user_list = get_user_proxy_list(uid)
    pool      = load_proxies()
    pool_on   = user_pool_enabled.get(uid, True)

    if is_admin(uid):
        if user_list:
            return (user_list + pool) if pool_on else user_list
        return pool

    if not user_list:
        return []
    return (user_list + pool) if pool_on else user_list

# ══════════════════════════════════════════════════════════════
# Cards / progress
# ══════════════════════════════════════════════════════════════
def extract_cc(text: str) -> list:
    matches = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', text)
    cards = []
    for card, month, year, cvv in matches:
        if len(year) == 2:
            year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

def make_progress_bar(current, total, width=20) -> str:
    if total == 0:
        return f"[{'░'*width}] 0/0 (0%)"
    filled = int(width * current / total)
    pct    = int(100 * current / total)
    return f"[{'█'*filled}{'░'*(width-filled)}] {current}/{total} ({pct}%)"

# ══════════════════════════════════════════════════════════════
# GC config
# ══════════════════════════════════════════════════════════════
_GC_DEFAULT = {
    'private_gc': None,
    'public_gc': None,
    'log_gc': None,
    'public_channel': None,
    'required_channels': [],
}

def load_gc_config() -> dict:
    try:
        with open(GC_CONFIG_FILE) as f:
            data = json.load(f)
        return {**_GC_DEFAULT, **data}
    except:
        return dict(_GC_DEFAULT)

def save_gc_config(cfg: dict):
    with open(GC_CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

# ══════════════════════════════════════════════════════════════
# KEYS with expiry
# ══════════════════════════════════════════════════════════════
def load_keys() -> dict:
    try:
        with open(KEYS_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_keys(keys: dict):
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=2)

def generate_key(days: int = 30) -> str:
    keys = load_keys()
    alphabet = string.ascii_uppercase + string.digits
    while True:
        suffix = ''.join(secrets.choice(alphabet) for _ in range(4))
        k = f"{KEY_PREFIX}-{suffix}"
        if k not in keys:
            now = int(time.time())
            keys[k] = {
                'used': False,
                'used_by': None,
                'created': now,
                'expires': (now + days * 86400) if days > 0 else 0,
            }
            save_keys(keys)
            return k

def redeem_key(key: str, user_id: int):
    keys = load_keys()
    k = (key or '').strip().upper()
    if k not in keys:
        return False, "Invalid key"
    info = keys[k]
    if info.get('used'):
        return False, f"Key already used"
    expires = info.get('expires', 0)
    if expires and time.time() > expires:
        return False, "Key expired"
    info['used']    = True
    info['used_by'] = user_id
    info['used_at'] = int(time.time())
    save_keys(keys)
    return True, "OK"

def list_keys(limit: int = 50) -> list:
    return list(load_keys().items())[:limit]

def key_expiry_text(info: dict) -> str:
    expires = info.get('expires', 0)
    if not expires:
        return "never expires"
    left = expires - int(time.time())
    if left <= 0:
        return "expired"
    d = left // 86400
    h = (left % 86400) // 3600
    if d:
        return f"{d}d {h}h left"
    return f"{h}h left"

# ══════════════════════════════════════════════════════════════
# Init
# ══════════════════════════════════════════════════════════════
load_user_proxies()
load_user_pool()
