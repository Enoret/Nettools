"""
NetTools - MAC vendor (OUI) lookup

Uses Wireshark's `manuf` database (downloaded at image build time, it is
updated much more often than the one bundled with arp-scan) and falls back to
arp-scan's ieee-oui.txt. Supports MA-L (/24), MA-M (/28) and MA-S (/36)
assignments.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

MANUF_PATHS = [
    os.environ.get('NETTOOLS_MANUF_PATH', '/usr/share/nettools/manuf'),
]
ARPSCAN_OUI_PATHS = [
    '/usr/share/arp-scan/ieee-oui.txt',
    '/usr/local/share/arp-scan/ieee-oui.txt',
]

# {bits: {hex_prefix: vendor}}
_db = None


def _load():
    global _db
    db = {24: {}, 28: {}, 36: {}}
    loaded_from = None

    for path in MANUF_PATHS:
        if os.path.exists(path):
            with open(path, encoding='utf-8', errors='replace') as f:
                for line in f:
                    if not line.strip() or line.startswith('#'):
                        continue
                    parts = line.rstrip('\n').split('\t')
                    if len(parts) < 2:
                        continue
                    prefix = parts[0].strip()
                    vendor = (parts[2] if len(parts) > 2 and parts[2].strip() else parts[1]).strip()
                    bits = 24
                    if '/' in prefix:
                        prefix, b = prefix.split('/', 1)
                        bits = int(b)
                    hexp = re.sub(r'[^0-9A-Fa-f]', '', prefix).upper()
                    if bits not in db:
                        continue
                    db[bits][hexp[:bits // 4]] = vendor
            loaded_from = path
            break

    if loaded_from is None:
        for path in ARPSCAN_OUI_PATHS:
            if os.path.exists(path):
                with open(path, encoding='utf-8', errors='replace') as f:
                    for line in f:
                        if not line.strip() or line.startswith('#'):
                            continue
                        parts = line.rstrip('\n').split('\t', 1)
                        if len(parts) != 2:
                            continue
                        hexp = parts[0].strip().upper()
                        bits = len(hexp) * 4
                        if bits in db:
                            db[bits][hexp] = parts[1].strip()
                loaded_from = path
                break

    total = sum(len(v) for v in db.values())
    logger.info(f"OUI database: {total} entries from {loaded_from or 'nowhere (no vendor lookup)'}")
    _db = db


def _mac_hex(mac: str) -> str:
    return re.sub(r'[^0-9A-Fa-f]', '', mac or '').upper()


def normalize_mac(mac: str) -> str:
    """'aa-bb-cc-dd-ee-ff' / 'aabb.ccdd.eeff' -> 'AA:BB:CC:DD:EE:FF'. Returns '' if invalid."""
    h = _mac_hex(mac)
    if len(h) != 12:
        return ''
    return ':'.join(h[i:i + 2] for i in range(0, 12, 2))


def is_private_mac(mac: str) -> bool:
    """True for locally administered (randomized / private) MAC addresses,
    e.g. Apple/Android/Windows private Wi-Fi addresses, VMs, containers."""
    h = _mac_hex(mac)
    if len(h) < 2:
        return False
    return bool(int(h[:2], 16) & 0x02)


def lookup_vendor(mac: str) -> str:
    """Return the vendor for a MAC, or '' if unknown or private."""
    h = _mac_hex(mac)
    if len(h) != 12 or is_private_mac(mac):
        return ''
    if _db is None:
        _load()
    for bits in (36, 28, 24):
        vendor = _db[bits].get(h[:bits // 4])
        if vendor:
            return vendor
    return ''


def clean_scanner_vendor(vendor: str) -> str:
    """Drop placeholder vendors reported by arp-scan/nmap such as
    '(Unknown)' or '(Unknown: locally administered)'."""
    vendor = (vendor or '').strip()
    if not vendor or vendor.startswith('(') or vendor.lower() == 'unknown':
        return ''
    return vendor


def resolve_vendor(mac: str, scanner_vendor: str = '') -> str:
    """Best vendor for a MAC: our OUI database first, then what the scanner said."""
    return lookup_vendor(mac) or clean_scanner_vendor(scanner_vendor)
