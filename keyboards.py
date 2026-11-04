import asyncio, json, threading, requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import BOT_TOKEN, OWNER_USERNAME, OWNER_ID
from emojis import BUTTON_CUSTOM_EMOJIS, _btn_icon_id, _clean_btn_text

_BTN_STYLES = ["primary", "success", "danger"]
_style_idx  = 0
_style_lock = threading.Lock()

def _next_style() -> str:
    global _style_idx
    with _style_lock:
        s = _BTN_STYLES[_style_idx % len(_BTN_STYLES)]
        _style_idx += 1
        return s

def _color_kb(rows: list) -> dict:
    colored = []
    for row in rows:
        colored_row = []
        for btn in row:
            b = dict(btn)
            cb       = b.get("callback_data", "")
            has_copy = "copy_text" in b
            has_url  = "url" in b
            if ((cb and cb != "noop") or has_copy or has_url) and "style" not in b:
                b["style"] = _next_style()
            if cb == "noop" and has_copy:
                b.pop("callback_data", None)
            raw_text = b.get("text", "")
            if "icon_custom_emoji_id" not in b:
                icon_id = _btn_icon_id(raw_text)
                if icon_id:
                    b["icon_custom_emoji_id"] = icon_id
            b["text"] = _clean_btn_text(raw_text)
            colored_row.append(b)
        colored.append(colored_row)
    return {"inline_keyboard": colored}

def _strip_styles(markup: dict) -> dict:
    import copy
    m = copy.deepcopy(markup)
    for row in m.get("inline_keyboard", []):
        for btn in row:
            btn.pop("style", None)
    return m

def _strip_icons(markup: dict) -> dict:
    import copy
    m = copy.deepcopy(markup)
    for row in m.get("inline_keyboard", []):
        for btn in row:
            btn.pop("icon_custom_emoji_id", None)
    return m

_http_session = requests.Session()
_http_session.verify = False
_http_adapter = requests.adapters.HTTPAdapter(
    pool_connections=8, pool_maxsize=32, max_retries=1
)
_http_session.mount("https://", _http_adapter)
_http_session.mount("http://",  _http_adapter)

def _raw_post(url, payload):
    p = dict(payload)
    if "reply_markup" in p and isinstance(p["reply_markup"], dict):
        p["reply_markup"] = json.dumps(p["reply_markup"], ensure_ascii=False)
    try:
        return _http_session.post(url, json=p, timeout=8).json()
    except Exception:
        return {"ok": False}

async def raw_send(chat_id, text, kb_rows, parse_mode="HTML", reply_to=None):
    kb  = _color_kb(kb_rows)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id, "text": text,
        "parse_mode": parse_mode, "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    payload["reply_markup"] = _strip_icons(kb)
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    payload["reply_markup"] = _strip_styles(_strip_icons(kb))
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    return None

async def raw_edit(chat_id, message_id, text, kb_rows, parse_mode="HTML"):
    kb  = _color_kb(kb_rows)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id, "message_id": message_id,
        "text": text, "parse_mode": parse_mode, "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp
    payload["reply_markup"] = _strip_icons(kb)
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp
    payload["reply_markup"] = _strip_styles(_strip_icons(kb))
    resp = await asyncio.to_thread(_raw_post, url, payload)
    return resp

async def nav_edit(chat_id, message_id, text, kb_rows, parse_mode="HTML"):
    kb = _color_kb(kb_rows)
    cap_payload = {
        "chat_id": chat_id, "message_id": message_id,
        "caption": text, "parse_mode": parse_mode, "reply_markup": kb,
    }
    resp = await asyncio.to_thread(_raw_post,
        f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption", cap_payload)
    if resp.get("ok"):
        return resp
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    txt_payload = {
        "chat_id": chat_id, "message_id": message_id,
        "text": text, "parse_mode": parse_mode, "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    resp = await asyncio.to_thread(_raw_post, url, txt_payload)
    if resp.get("ok"):
        return resp
    txt_payload["reply_markup"] = _strip_icons(kb)
    resp = await asyncio.to_thread(_raw_post, url, txt_payload)
    if resp.get("ok"):
        return resp
    txt_payload["reply_markup"] = _strip_styles(_strip_icons(kb))
    resp = await asyncio.to_thread(_raw_post, url, txt_payload)
    return resp

def rows_main():
    return [
        [{"text": "💳  Checker",        "callback_data": "gates"}],
        [{"text": "🔑  Redeem Key",      "callback_data": "redeem_info"}],
        [{"text": "💻  Contact",        "url": f"https://t.me/{OWNER_USERNAME}"},
         {"text": "❌  Close",          "callback_data": "close"}],
    ]

def rows_gates():
    return [
        [{"text": "💳  Shopify",         "callback_data": "gate_shopify"}],
        [{"text": "🔥  Stripe 1$",       "callback_data": "gate_st1"},
         {"text": "💎  Stripe 5$",       "callback_data": "gate_st5"}],
        [{"text": "✅  Stripe Auth2 $0", "callback_data": "gate_auth"}],
        [{"text": "🔑  Manage Proxy",    "callback_data": "manage_proxy"}],
        [{"text": "↪️  Back",            "callback_data": "back_start"}],
    ]

def rows_proxy(uid: int):
    from storage import user_pool_enabled
    pool_on    = user_pool_enabled.get(uid, True) if uid else True
    pool_label = "✅  Proxy Pool  ON" if pool_on else "⚡  Proxy Pool  OFF"
    return [
        [{"text": pool_label,           "callback_data": "toggle_pool"}],
        [{"text": "✅  Test Proxy",     "callback_data": "test_proxy_btn"},
         {"text": "❌  Remove Proxy",   "callback_data": "remove_proxy_btn"}],
        [{"text": "↪️  Back",           "callback_data": "gates"}],
    ]

def rows_admin(uid: int = 0):
    from config import load_api_provider
    prov = load_api_provider()
    api_label = f"🌐  API  »  {'shopii' if prov == 'shopii' else 'yzio'}"
    rows = [
        [{"text": "👑  Users",          "callback_data": "admin_users"},
         {"text": "🌐  Sites",          "callback_data": "admin_sites"}],
        [{"text": "📡  Broadcast",      "callback_data": "admin_broadcast_info"},
         {"text": "⚙️  Proxy Pool",    "callback_data": "admin_proxy_pool"}],
        [{"text": api_label,            "callback_data": "admin_api_panel"}],
        [{"text": "📦  Backup",         "callback_data": "admin_backup"},
         {"text": "♻️  Restore",        "callback_data": "admin_restore_info"}],
    ]
    if uid == OWNER_ID:
        rows.append([{"text": "🔌  API Endpoints", "callback_data": "owner_api_eps"},
                     {"text": "🔑  Keys",          "callback_data": "owner_keys"}])
        rows.append([{"text": "🛡  GC / Channels",  "callback_data": "owner_gc"}])
    rows.append([{"text": "❌  Close",              "callback_data": "close"}])
    return rows

def rows_admin_api():
    from config import load_api_provider
    prov = load_api_provider()
    yz_mark = "✅" if prov == "yzio" else "○"
    sh_mark = "✅" if prov == "shopii" else "○"
    return [
        [{"text": f"{yz_mark}  yzio  (check.yzio.app)",   "callback_data": "api_pick_yzio"}],
        [{"text": f"{sh_mark}  shopii  (62.169.23.129)",  "callback_data": "api_pick_shopii"}],
        [{"text": "↪️  Back",                             "callback_data": "admin_panel"}],
    ]

def rows_admin_users():
    return [
        [{"text": "📋  Premium List",   "callback_data": "admin_list_users"}],
        [{"text": "✅  Add User",       "callback_data": "admin_add_user_info"},
         {"text": "❌  Remove User",    "callback_data": "admin_rm_user_info"}],
        [{"text": "↪️  Back",           "callback_data": "admin_panel"}],
    ]

def rows_admin_sites():
    return [
        [{"text": "📋  Site List",      "callback_data": "admin_list_sites_cb"}],
        [{"text": "✅  Add Site",       "callback_data": "admin_add_site_info"},
         {"text": "❌  Remove Site",    "callback_data": "admin_rm_site_info"}],
        [{"text": "↪️  Back",           "callback_data": "admin_panel"}],
    ]

def rows_admin_proxy_pool():
    return [
        [{"text": "📋  View Pool",      "callback_data": "admin_list_proxy_cb"}],
        [{"text": "✅  Add Proxies",    "callback_data": "admin_add_proxy_info"},
         {"text": "🔥  Clear Pool",     "callback_data": "admin_clear_proxy_cb"}],
        [{"text": "↪️  Back",           "callback_data": "admin_panel"}],
    ]

def rows_owner_api_eps():
    return [
        [{"text": "📋  List",           "callback_data": "owner_api_list"},
         {"text": "✅  Add",            "callback_data": "owner_api_add_info"}],
        [{"text": "❌  Remove",         "callback_data": "owner_api_rm_info"}],
        [{"text": "↪️  Back",           "callback_data": "admin_panel"}],
    ]

def rows_owner_keys():
    return [
        [{"text": "📋  List",           "callback_data": "owner_key_list"},
         {"text": "✅  Generate",       "callback_data": "owner_key_gen_info"}],
        [{"text": "↪️  Back",           "callback_data": "admin_panel"}],
    ]

def rows_owner_gc():
    return [
        [{"text": "🔒  Private GC",     "callback_data": "owner_gc_private"},
         {"text": "🌐  Public GC",      "callback_data": "owner_gc_public"}],
        [{"text": "📝  Log GC",         "callback_data": "owner_gc_log"},
         {"text": "📢  Public Channel", "callback_data": "owner_gc_channel"}],
        [{"text": "🔗  Required Channels", "callback_data": "owner_gc_req"}],
        [{"text": "↪️  Back",           "callback_data": "admin_panel"}],
    ]

def rows_stop():
    return [[{"text": "✋  Stop",        "callback_data": "stop_mass"}]]

def _send_notification(chat_id, text) -> int | None:
    try:
        r = _raw_post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", {
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if r.get("ok"):
            return r["result"]["message_id"]
    except Exception:
        pass
    return None

def _pin_message_botapi(chat_id, message_id):
    try:
        _raw_post(f"https://api.telegram.org/bot{BOT_TOKEN}/pinChatMessage", {
            "chat_id": chat_id, "message_id": message_id,
            "disable_notification": False,
        })
    except Exception:
        pass

def _to_chat_id(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.lstrip('-').isdigit():
        return int(val)
    return val

def _get_chat_info(chat_ref):
    try:
        r = _raw_post(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat", {
            "chat_id": _to_chat_id(chat_ref)
        })
        if r.get("ok"):
            return r["result"]
        print(f"[getChat] {chat_ref}: {r.get('description', 'unknown')}")
    except Exception as e:
        print(f"[getChat] {chat_ref}: {e}")
    return None

def _get_join_link(chat_ref):
    info = _get_chat_info(chat_ref)
    if info:
        if info.get("username"):
            return f"https://t.me/{info['username']}"
        if info.get("invite_link"):
            return info["invite_link"]
    try:
        r = _raw_post(f"https://api.telegram.org/bot{BOT_TOKEN}/exportChatInviteLink", {
            "chat_id": _to_chat_id(chat_ref)
        })
        if r.get("ok"):
            return r["result"]
    except Exception:
        pass
    return None

def _get_chat_member(chat_ref, user_id) -> bool:
    try:
        r = _raw_post(f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember", {
            "chat_id": _to_chat_id(chat_ref), "user_id": user_id
        })
        if r.get("ok"):
            status = r["result"].get("status")
            return status in ("creator", "administrator", "member")
        print(f"[getChatMember] {chat_ref}/{user_id}: {r.get('description', 'unknown')}")
    except Exception as e:
        print(f"[getChatMember] {chat_ref}/{user_id}: {e}")
    return False
