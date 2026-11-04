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
DEV_LINE       = f'💻 <b>Dev</b>  »  <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'

MASS_WORKERS = int(os.environ.get('MASS_WORKERS', '20'))

# Persistent storage root — set DATA_DIR=/var/data on Render (mounted disk).
# Locally it just falls back to the project directory, no change in behaviour.
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)

def _data(name: str) -> str:
    return os.path.join(DATA_DIR, name)

_ADMIN_FILE         = _data('admin.json')
PREMIUM_FILE        = _data('premium.txt')
SITES_FILE          = _data('sites.txt')
PROXY_FILE          = _data('proxy.txt')
USER_PROXY_FILE     = _data('user_proxies.json')
USER_POOL_FILE      = _data('user_pool.json')
API_ENDPOINTS_FILE  = _data('api_endpoints.json')
API_SELECTED_FILE   = _data('api_selected.json')
GC_CONFIG_FILE      = _data('gc_config.json')
KEYS_FILE           = _data('keys.json')

# Two supported provider flavours.
API_YZIO_BASE   = "https://check.yzio.app"
API_SHOPII_BASE = "http://62.169.23.129:8080"

DEFAULT_API_PROVIDER = "yzio"

KEY_PREFIX = "OGGY-PROO"
LIMITS     = {"admin": 10000, "premium": 5000}

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


# ══════════════════════════════════════════════════════════════
# API provider selection (admin-switchable, persisted)
# ══════════════════════════════════════════════════════════════
def load_api_provider() -> str:
    try:
        with open(API_SELECTED_FILE) as f:
            p = json.load(f).get('provider', DEFAULT_API_PROVIDER)
            return p if p in ("yzio", "shopii") else DEFAULT_API_PROVIDER
    except Exception:
        return DEFAULT_API_PROVIDER

def save_api_provider(provider: str):
    if provider not in ("yzio", "shopii"):
        return
    with open(API_SELECTED_FILE, 'w') as f:
        json.dump({'provider': provider}, f, indent=2)

def current_api_base() -> str:
    return API_SHOPII_BASE if load_api_provider() == "shopii" else API_YZIO_BASE
