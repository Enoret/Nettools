"""
NetTools - Manufacturer logos

Logo for a brand string (e.g. 'Beijing Xiaomi Mobile Software Co., Ltd'):
  1. a logo uploaded by the user for that brand,
  2. Simple Icons (https://simpleicons.org, colored SVG from its CDN),
  3. the favicon of the brand's website (Google favicon service).
Downloaded logos are cached in the data volume, so each brand is fetched once;
misses are remembered for a week.
"""

import base64
import logging
import os
import re
import threading
import time

import requests

logger = logging.getLogger(__name__)

LOGO_DIR = os.path.join(os.path.dirname(os.environ.get('NETTOOLS_DB_PATH', '/data/nettools.db')), 'logos')
AUTO_DIR = os.path.join(LOGO_DIR, 'auto')
CUSTOM_DIR = os.path.join(LOGO_DIR, 'custom')
MISS_TTL = 7 * 86400
MAX_BYTES = 300 * 1024
TIMEOUT = 6

EXT_TYPES = {'.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp'}

# substring of the (lowercase) brand -> (simple-icons slug or None, website domain or None)
ALIASES = [
    ('hewlett packard enterprise', ('hpe', 'hpe.com')),
    ('hewlett', ('hp', 'hp.com')),
    ('hp inc', ('hp', 'hp.com')),
    ('raspberry', ('raspberrypi', 'raspberrypi.com')),
    ('tp-link', ('tplink', 'tp-link.com')),
    ('tplink', ('tplink', 'tp-link.com')),
    ('asustek', ('asus', 'asus.com')),
    ('giga-byte', (None, 'gigabyte.com')),
    ('gigabyte', (None, 'gigabyte.com')),
    ('xiaomi', ('xiaomi', 'mi.com')),
    ('hikvision', (None, 'hikvision.com')),
    ('hualai', (None, 'wyze.com')),
    ('wyze', (None, 'wyze.com')),
    ('ezviz', (None, 'ezviz.com')),
    ('roborock', (None, 'roborock.com')),
    ('tuya', (None, 'tuya.com')),
    ('ugreen', (None, 'ugreen.com')),
    ('nintendo', (None, 'nintendo.com')),
    ('amazon', (None, 'amazon.com')),
    ('philips', (None, 'philips.com')),
    ('signify', (None, 'philips-hue.com')),
    ('d-link', (None, 'dlink.com')),
    ('canon', (None, 'canon.com')),
    ('brother', (None, 'brother.com')),
    ('microsoft', (None, 'microsoft.com')),
    ('ubiquiti', ('ubiquiti', 'ui.com')),
    ('unifi', ('ubiquiti', 'ui.com')),
    ('proxmox', ('proxmox', 'proxmox.com')),
    ('espressif', ('espressif', 'espressif.com')),
    ('synology', ('synology', 'synology.com')),
    ('apple', ('apple', 'apple.com')),
    ('google', ('google', 'google.com')),
    ('samsung', ('samsung', 'samsung.com')),
    ('lg electronics', ('lg', 'lg.com')),
    ('lg innotek', ('lg', 'lg.com')),
    ('sony', ('sony', 'sony.com')),
    ('intel', ('intel', 'intel.com')),
    ('dell', ('dell', 'dell.com')),
    ('lenovo', ('lenovo', 'lenovo.com')),
    ('huawei', ('huawei', 'huawei.com')),
    ('netgear', ('netgear', 'netgear.com')),
    ('cisco', ('cisco', 'cisco.com')),
    ('mikrotik', ('mikrotik', 'mikrotik.com')),
    ('qnap', ('qnap', 'qnap.com')),
    ('sonos', ('sonos', 'sonos.com')),
    ('shelly', ('shelly', 'shelly.com')),
    ('tado', ('tado', 'tado.com')),
    ('oneplus', ('oneplus', 'oneplus.com')),
    ('nvidia', ('nvidia', 'nvidia.com')),
    ('micro-star', ('msi', 'msi.com')),
    ('epson', ('epson', 'epson.com')),
    ('seiko epson', ('epson', 'epson.com')),
]

# Words that are not the brand in OUI vendor names
GENERIC_PREFIXES = {
    'shenzhen', 'beijing', 'hangzhou', 'guangdong', 'guangzhou', 'tianjin', 'shanghai',
    'zhejiang', 'jiangsu', 'xiamen', 'dongguan', 'chongqing', 'nanjing', 'suzhou', 'wuhan',
    'the', 'web',
}

_locks = {}
_locks_guard = threading.Lock()


def brand_key(brand: str) -> str:
    """Stable file-name-safe key for a brand: 'Apple, Inc.' -> 'apple'."""
    b = (brand or '').strip().lower()
    if not b:
        return ''
    for needle, (slug, domain) in ALIASES:
        if needle in b:
            return re.sub(r'[^a-z0-9]', '', slug or domain.split('.')[0])
    m = re.search(r'([a-z0-9-]+\.(?:com|net|org|io|es|de|eu|co|tv))\b', b)
    if m:
        return re.sub(r'[^a-z0-9]', '', m.group(1).rsplit('.', 1)[0])
    words = [w for w in re.split(r'[^a-z0-9]+', b) if w]
    words = [w for w in words if w not in GENERIC_PREFIXES] or words
    return words[0] if words else ''


def _candidates(brand: str):
    """(simple-icons slug, domain) to try for a brand."""
    b = (brand or '').strip().lower()
    for needle, (slug, domain) in ALIASES:
        if needle in b:
            return slug, domain
    m = re.search(r'([a-z0-9-]+\.(?:com|net|org|io|es|de|eu|co|tv))\b', b)
    if m:
        return None, m.group(1)
    key = brand_key(brand)
    return (key or None), (f"{key}.com" if len(key) >= 4 else None)


def _find(directory: str, key: str):
    for ext in EXT_TYPES:
        path = os.path.join(directory, key + ext)
        if os.path.exists(path):
            return path
    return None


def _lock_for(key):
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _download(url: str, expect: tuple):
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={'User-Agent': 'NetTools'})
    except requests.RequestException as e:
        logger.debug(f"Logo download failed {url}: {e}")
        return None, None
    ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip()
    if r.status_code != 200 or ctype not in expect or not r.content or len(r.content) > MAX_BYTES:
        return None, None
    return r.content, ctype


def get_logo(brand: str):
    """Path of the logo file for `brand`, or None."""
    key = brand_key(brand)
    if not key:
        return None
    custom = _find(CUSTOM_DIR, key)
    if custom:
        return custom
    cached = _find(AUTO_DIR, key)
    if cached:
        return cached

    miss = os.path.join(AUTO_DIR, key + '.none')
    with _lock_for(key):
        cached = _find(AUTO_DIR, key)
        if cached:
            return cached
        if os.path.exists(miss) and time.time() - os.path.getmtime(miss) < MISS_TTL:
            return None

        os.makedirs(AUTO_DIR, exist_ok=True)
        slug, domain = _candidates(brand)
        data = ext = None
        if slug:
            data, _ = _download(f"https://cdn.simpleicons.org/{slug}", ('image/svg+xml',))
            ext = '.svg'
        if not data and domain:
            data, _ = _download(f"https://www.google.com/s2/favicons?domain={domain}&sz=128", ('image/png',))
            ext = '.png'
        if not data:
            with open(miss, 'w') as f:
                f.write(brand or '')
            return None
        path = os.path.join(AUTO_DIR, key + ext)
        with open(path, 'wb') as f:
            f.write(data)
        if os.path.exists(miss):
            os.remove(miss)
        logger.info(f"Logo for '{brand}' ({key}) downloaded: {os.path.basename(path)}")
        return path


def content_type(path: str) -> str:
    return EXT_TYPES.get(os.path.splitext(path)[1], 'application/octet-stream')


def save_custom_logo(brand: str, data_url: str) -> str:
    """Store a user-provided raster logo (data URL: png / jpeg / webp)."""
    key = brand_key(brand)
    if not key:
        raise ValueError("Falta la marca")
    m = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)', (data_url or '').strip())
    if not m:
        raise ValueError("Formato de imagen no valido (usa PNG, JPG o WebP)")
    raw = base64.b64decode(m.group(2))
    if len(raw) > MAX_BYTES:
        raise ValueError("La imagen es demasiado grande (maximo 300 KB)")
    ext = {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}[m.group(1)]
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    delete_custom_logo(brand)
    path = os.path.join(CUSTOM_DIR, key + ext)
    with open(path, 'wb') as f:
        f.write(raw)
    return key


def delete_custom_logo(brand: str) -> bool:
    key = brand_key(brand)
    found = False
    while key:
        path = _find(CUSTOM_DIR, key)
        if not path:
            break
        os.remove(path)
        found = True
    return found


def has_custom_logo(brand: str) -> bool:
    key = brand_key(brand)
    return bool(key and _find(CUSTOM_DIR, key))
