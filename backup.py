"""backup.py — ZIP backup/restore of all bot state."""
import os
import json
import io
import zipfile
from config import (
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    API_ENDPOINTS_FILE, GC_CONFIG_FILE, KEYS_FILE,
)

_ADMIN_FILE = os.path.join(os.path.dirname(__file__), 'admin.json')

BACKUP_FILES = [
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    API_ENDPOINTS_FILE, GC_CONFIG_FILE, KEYS_FILE,
]
BACKUP_FILES_FULL = BACKUP_FILES + [_ADMIN_FILE]


def create_backup_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in BACKUP_FILES_FULL:
            if os.path.exists(f):
                zf.write(f, arcname=os.path.basename(f))
    return buf.getvalue()


def _count_lines(path):
    try:
        with open(path) as fp:
            return len([l for l in fp if l.strip()])
    except:
        return 0


def backup_stats() -> dict:
    keys_total = keys_unused = 0
    try:
        with open(KEYS_FILE) as fp:
            keys = json.load(fp)
            keys_total = len(keys)
            keys_unused = sum(1 for v in keys.values() if not v.get('used'))
    except:
        pass

    gc_links = 0
    try:
        with open(GC_CONFIG_FILE) as fp:
            gc = json.load(fp)
            gc_links = sum(1 for k in ('private_gc', 'public_gc', 'log_gc', 'public_channel') if gc.get(k))
            gc_links += len(gc.get('required_channels', []))
    except:
        pass

    eps = 0
    try:
        with open(API_ENDPOINTS_FILE) as fp:
            eps = len(json.load(fp).get('endpoints', []))
    except:
        eps = 1

    return {
        'users': _count_lines(PREMIUM_FILE),
        'sites': _count_lines(SITES_FILE),
        'proxies': _count_lines(PROXY_FILE),
        'api_endpoints': eps,
        'keys_total': keys_total,
        'keys_unused': keys_unused,
        'gc_links': gc_links,
    }


def restore_backup_zip(data: bytes):
    """Returns (ok: bool, message: str, restored: list, skipped: list)."""
    restored, skipped = [], []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            valid = {os.path.basename(f) for f in BACKUP_FILES_FULL}
            for name in zf.namelist():
                base = os.path.basename(name)
                if base not in valid:
                    skipped.append(base)
                    continue
                target = _ADMIN_FILE if base == 'admin.json' else base
                with open(target, 'wb') as out:
                    out.write(zf.read(name))
                restored.append(base)
        if not restored:
            return False, "No valid files in backup", [], skipped
        return True, f"{len(restored)} file(s) restored", restored, skipped
    except Exception as e:
        return False, f"Restore failed: {str(e)[:80]}", [], skipped
