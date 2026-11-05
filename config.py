import os
import json

API_ID    = int(os.environ.get('API_ID',    '0'))
API_HASH  =     os.environ.get('API_HASH',  '')
BOT_TOKEN =     os.environ.get('BOT_TOKEN', '')
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}"

BOT_BRAND      = "𝑶𝑮𝑮𝒀'𝑺 𝑷𝑹𝑰𝑴𝑬 𝑩𝑶𝑻"
OWNER_NAME     = '𝑶𝑮𝑮𝒀 𝑷𝑹𝑶𝑶'
OWNER_USERNAME = 'oggyproo'
OWNER_ID       = 8919487892
BOT_USERNAME   = 'OGGYsPRIME_BOT'
DEV_LINE       = f'💻 <b>Dev</b>  »  <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'

MASS_WORKERS = int(os.environ.get('MASS_WORKERS', '20'))

_ADMIN_FILE         = os.path.join(os.path.dirname(__file__), 'admin.json')
PREMIUM_FILE        = 'premium.txt'
SITES_FILE          = 'sites.txt'
PROXY_FILE          = 'proxy.txt'
USER_PROXY_FILE     = 'user_proxies.json'
USER_POOL_FILE      = 'user_pool.json'
API_ENDPOINTS_FILE  = 'api_endpoints.json'
GC_CONFIG_FILE      = 'gc_config.json'
KEYS_FILE           = 'keys.json'
FEEDBACK_FILE       = 'feedback_pending.json'
SETTINGS_FILE       = 'settings.json'

DEFAULT_API_ENDPOINTS = [
    {"url": "http://62.169.23.129:8080/shopii",   "key": None},
    {"url": "http://5.83.136.102:8136/shopify",   "key": "CHIRAG"},
    {"url": "http://5.83.136.102:8137/shopify",   "key": "CHIRAG"},
    {"url": "https://check.yzio.app/shopify",     "key": None},
]
DEFAULT_MAX_SITE_PRICE = 3.0

KEY_PREFIX = "OGGY-PROO"

LIMITS = {"admin": 10000, "premium": 5000}

_DEFAULT_ADMINS = (
    {int(x.strip()) for x in os.environ.get('ADMIN_ID', '').split(',') if x.strip().isdigit()}
    | ({OWNER_ID} if OWNER_ID else set())
)

def _load_admin_ids() -> set:
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
            ids  = data.get('admin_ids', [])
            return (set(ids) | _DEFAULT_ADMINS) if ids else _DEFAULT_ADMINS
    except Exception:
        return _DEFAULT_ADMINS

def _save_admin_ids(ids: set):
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data['admin_ids'] = list(ids)
    with open(_ADMIN_FILE, 'w') as f:
        json.dump(data, f)

ADMIN_IDS = _load_admin_ids()
ADMIN_ID  = OWNER_ID
