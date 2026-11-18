"""
NetTools - Database Manager (SQLite)
"""

import sqlite3
import os
import json
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get('NETTOOLS_DB_PATH', '/data/nettools.db')


def _get_timezone():
    """Get configured timezone offset. Returns a timezone object."""
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT value FROM settings WHERE key = 'timezone'").fetchone()
            conn.close()
            if row and row['value']:
                offset_hours = int(row['value'])
                return timezone(timedelta(hours=offset_hours))
    except Exception:
        pass
    # Default: UTC+1 (CET)
    return timezone(timedelta(hours=1))


def now_local():
    """Get current datetime in configured timezone, formatted for SQLite."""
    tz = _get_timezone()
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')


def get_db():
    """Get database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS speed_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            download_speed REAL,
            upload_speed REAL,
            ping REAL,
            jitter REAL,
            server_name TEXT,
            server_id TEXT,
            server_location TEXT,
            isp TEXT,
            external_ip TEXT,
            raw_data TEXT
        );

        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            mac_address TEXT,
            hostname TEXT,
            custom_name TEXT,
            description TEXT,
            brand TEXT,
            location TEXT,
            device_type TEXT DEFAULT 'other',
            ip_type TEXT DEFAULT 'dhcp',
            status TEXT DEFAULT 'new',
            is_online INTEGER DEFAULT 0,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ping_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            ip_address TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            latency REAL,
            is_reachable INTEGER DEFAULT 0,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS device_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_devices INTEGER DEFAULT 0,
            online_devices INTEGER DEFAULT 0,
            offline_devices INTEGER DEFAULT 0,
            new_devices INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS device_ports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            port INTEGER NOT NULL,
            protocol TEXT NOT NULL DEFAULT 'tcp',
            service TEXT,
            product TEXT,
            version TEXT,
            tunnel TEXT,
            first_seen DATETIME,
            last_seen DATETIME,
            UNIQUE (device_id, port, protocol),
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER UNIQUE,
            name TEXT,
            device_type TEXT DEFAULT 'other',
            brand TEXT,
            model TEXT,
            serial_number TEXT,
            mac_address TEXT,
            ip_address TEXT,
            location TEXT,
            description TEXT,
            purchase_date TEXT,
            purchase_price REAL,
            warranty_until TEXT,
            supplier TEXT,
            notes TEXT,
            asset_status TEXT DEFAULT 'active',
            asset_kind TEXT DEFAULT 'physical',
            host TEXT,
            hidden INTEGER DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME,
            type TEXT NOT NULL,          -- new_devices | speed_test | speed_test_failed | port_changes
            level TEXT DEFAULT 'info',   -- info | warning | error
            data TEXT,                   -- JSON, rendered by the UI in its language
            read INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);

        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            username TEXT,
            method TEXT,
            created_at DATETIME,
            expires_at DATETIME,
            last_seen DATETIME,
            display_name TEXT,
            avatar TEXT
        );

        CREATE TABLE IF NOT EXISTS oidc_states (
            state TEXT PRIMARY KEY,
            verifier TEXT,
            nonce TEXT,
            next TEXT,
            redirect_uri TEXT,
            created_at REAL
        );

        CREATE TABLE IF NOT EXISTS connectivity_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            gateway_ok INTEGER,          -- NULL if no gateway was found
            internet_ok INTEGER,
            latency REAL
        );
        CREATE INDEX IF NOT EXISTS idx_connectivity_ts ON connectivity_checks(timestamp);

        CREATE TABLE IF NOT EXISTS outages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT,                   -- internet | gateway
            start DATETIME,
            end DATETIME,
            last_seen DATETIME,
            duration INTEGER             -- seconds, when closed
        );
        CREATE INDEX IF NOT EXISTS idx_outages_start ON outages(start);
        CREATE INDEX IF NOT EXISTS idx_device_ports_device ON device_ports(device_id);
        CREATE INDEX IF NOT EXISTS idx_speed_tests_timestamp ON speed_tests(timestamp);
        CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip_address);
        CREATE INDEX IF NOT EXISTS idx_devices_mac ON devices(mac_address);
        CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
        CREATE INDEX IF NOT EXISTS idx_ping_results_timestamp ON ping_results(timestamp);
        CREATE INDEX IF NOT EXISTS idx_device_snapshots_timestamp ON device_snapshots(timestamp);
    """)

    # Migrations: add columns if they don't exist (for upgrades)
    try:
        cursor.execute("SELECT ip_type FROM devices LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE devices ADD COLUMN ip_type TEXT DEFAULT 'dhcp'")

    try:
        cursor.execute("SELECT last_port_scan FROM devices LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE devices ADD COLUMN last_port_scan DATETIME")

    try:
        cursor.execute("SELECT last_ip FROM devices LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE devices ADD COLUMN last_ip TEXT")

    for col, ddl in (('asset_kind', "TEXT DEFAULT 'physical'"), ('host', 'TEXT')):
        try:
            cursor.execute(f"SELECT {col} FROM inventory LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE inventory ADD COLUMN {col} {ddl}")

    for col in ('display_name', 'avatar'):
        try:
            cursor.execute(f"SELECT {col} FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT")

    try:
        cursor.execute("SELECT description_auto FROM devices LIMIT 1")
    except sqlite3.OperationalError:
        # NULL = never set, 1 = NetTools hint (replaceable), 0 = written/cleared by the user
        cursor.execute("ALTER TABLE devices ADD COLUMN description_auto INTEGER")

    try:
        cursor.execute("SELECT network_name FROM devices LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE devices ADD COLUMN network_name TEXT")

    # Migration: retention was not enforced before purge_old_data() existed.
    # On existing installs, switch retention to "keep forever" (0) once, so
    # upgrading never deletes historical data. The user can lower it later.
    is_existing_install = cursor.execute("SELECT COUNT(*) FROM settings").fetchone()[0] > 0
    retention_migrated = cursor.execute(
        "SELECT 1 FROM settings WHERE key = 'retention_migrated'"
    ).fetchone()
    if is_existing_install and not retention_migrated:
        cursor.execute(
            "UPDATE settings SET value = '0' WHERE key = 'speed_test_retention'"
        )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('retention_migrated', 'true')"
    )

    # Language: installs from before the English UI were always used in Spanish
    if is_existing_install:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ui_language', 'es')")

    # Default settings
    defaults = {
        'auto_speed_test': 'true',
        'speed_test_frequency': '60',
        'speed_test_retention': '30',
        'auto_network_scan': 'true',
        'network_scan_frequency': '15',
        'network_range': '192.168.1.0/24',  # legacy, unused (see network_ranges)
        'scan_local_networks': 'true',
        'network_ranges': '',
        'notify_new_devices': 'true',
        'telegram_enabled': 'false',
        'telegram_bot_token': '',
        'telegram_chat_id': '',
        'timezone': '1',
        'notify_speed_tests': 'false',
        'speed_test_alert_threshold': '0',
        'purge_stale_devices': 'true',
        'stale_device_days': '10',
        'auto_port_scan': 'false',
        'port_scan_hour': '3',
        'port_scan_profile': 'quick',
        'port_scan_scope': 'online',
        'notify_new_ports': 'true',
        'language': 'auto',        # auto (browser) | es | en
        'ui_language': '',         # language reported by the UI when 'auto'
        'connectivity_enabled': 'true',
        'connectivity_interval': '60',
        'connectivity_targets': '1.1.1.1,8.8.8.8',
        'connectivity_threshold': '2',
        'notify_outages': 'true',
        'auth_enabled': 'false',
        'auth_session_days': '7',
        'auth_local_enabled': 'true',
        'auth_local_username': 'admin',
        'auth_local_password_hash': '',
        'auth_ldap_enabled': 'false',
        'auth_ldap_url': '',
        'auth_ldap_bind_dn': '',
        'auth_ldap_bind_password': '',
        'auth_ldap_base_dn': '',
        'auth_ldap_user_filter': '(&(objectClass=person)(uid={username}))',
        'auth_ldap_user_dn_template': '',
        'auth_ldap_group': '',
        'auth_ldap_verify_ssl': 'false',
        'auth_oidc_enabled': 'false',
        'auth_oidc_name': 'SSO',
        'auth_oidc_issuer': '',
        'auth_oidc_client_id': '',
        'auth_oidc_client_secret': '',
        'auth_oidc_scopes': 'openid profile email groups',
        'auth_oidc_group': '',
        'auth_oidc_redirect_uri': '',
        'auth_oidc_verify_ssl': 'true',
        'unifi_enabled': 'false',
        'unifi_url': '',
        'unifi_auth': 'api_key',
        'unifi_api_key': '',
        'unifi_username': '',
        'unifi_password': '',
        'unifi_site': 'default',
        'unifi_verify_ssl': 'false',
    }

    for key, value in defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    conn.commit()
    conn.close()


# --- Speed Tests ---
def save_speed_test(data: dict) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO speed_tests (timestamp, download_speed, upload_speed, ping, jitter,
                                  server_name, server_id, server_location, isp, external_ip, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_local(),
        data.get('download_speed'),
        data.get('upload_speed'),
        data.get('ping'),
        data.get('jitter'),
        data.get('server_name'),
        data.get('server_id'),
        data.get('server_location'),
        data.get('isp'),
        data.get('external_ip'),
        json.dumps(data.get('raw_data', {})),
    ))
    conn.commit()
    row_id = cursor.lastrowid
    result = dict(conn.execute("SELECT * FROM speed_tests WHERE id = ?", (row_id,)).fetchone())
    conn.close()
    return result


def get_speed_tests(range_filter: str = '24h', limit: int = 500) -> list:
    conn = get_db()
    time_filter = _get_time_filter(range_filter)
    query = "SELECT * FROM speed_tests"
    params = []

    if time_filter:
        query += f" WHERE timestamp >= datetime(?, ?)"
        params.append(now_local())
        params.append(time_filter)

    query += " ORDER BY timestamp ASC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_speed_test() -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM speed_tests ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_speed_test_stats() -> dict:
    conn = get_db()
    row = conn.execute("""
        SELECT
            MAX(download_speed) as best_download,
            MAX(upload_speed) as best_upload,
            MIN(ping) as best_ping,
            AVG(download_speed) as avg_download,
            AVG(upload_speed) as avg_upload,
            AVG(ping) as avg_ping,
            COUNT(*) as total_tests
        FROM speed_tests
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_speed_test_averages(days: int = 7, exclude_id: int = None) -> dict:
    """Average download/upload/ping over the last `days` days (optionally
    excluding one test, e.g. the one just run)."""
    conn = get_db()
    row = conn.execute("""
        SELECT AVG(download_speed) AS download, AVG(upload_speed) AS upload,
               AVG(ping) AS ping, COUNT(*) AS count
        FROM speed_tests
        WHERE timestamp >= datetime(?, ?) AND id != ?
    """, (now_local(), f'-{int(days)} days', exclude_id or -1)).fetchone()
    conn.close()
    return dict(row) if row else {'count': 0}


def clear_speed_tests():
    conn = get_db()
    conn.execute("DELETE FROM speed_tests")
    conn.commit()
    conn.close()


# --- Devices ---
def get_devices(status_filter: str = None) -> list:
    conn = get_db()
    query = ("SELECT devices.*, "
             "(SELECT COUNT(*) FROM device_ports p WHERE p.device_id = devices.id) AS open_ports, "
             "(SELECT GROUP_CONCAT(p.port || ':' || COALESCE(p.service, '') || ':' || COALESCE(p.tunnel, ''), ',') "
             " FROM device_ports p WHERE p.device_id = devices.id) AS port_summary "
             "FROM devices")
    params = []

    if status_filter:
        query += " WHERE status = ?"
        params.append(status_filter)

    query += " ORDER BY is_online DESC, custom_name ASC, hostname ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    devices = [dict(r) for r in rows]
    for d in devices:
        d['mac_private'] = _is_private_mac(d.get('mac_address'))
    return devices


def _is_private_mac(mac) -> bool:
    try:
        return bool(int((mac or '').replace('-', ':').split(':')[0], 16) & 0x02)
    except ValueError:
        return False


def get_device(device_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_device(data: dict) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    ts = now_local()
    cursor.execute("""
        INSERT INTO devices (ip_address, mac_address, hostname, custom_name,
                             description, brand, location, device_type, ip_type, status, is_online,
                             first_seen, last_seen, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('ip_address'),
        data.get('mac_address'),
        data.get('hostname'),
        data.get('custom_name'),
        data.get('description'),
        data.get('brand'),
        data.get('location'),
        data.get('device_type', 'other'),
        data.get('ip_type', 'dhcp'),
        data.get('status', 'manual'),
        data.get('is_online', 0),
        ts, ts, ts, ts,
    ))
    conn.commit()
    row_id = cursor.lastrowid
    result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (row_id,)).fetchone())
    conn.close()
    return result


def update_device(device_id: int, data: dict) -> dict:
    conn = get_db()
    fields = []
    values = []
    if data.get('description') is not None:
        current = conn.execute("SELECT description FROM devices WHERE id = ?", (device_id,)).fetchone()
        if current is not None and (current['description'] or '') != data['description']:
            fields.append("description_auto = 0")  # the user wrote it: never replace it
    for key in ['ip_address', 'mac_address', 'hostname', 'custom_name',
                'description', 'brand', 'location', 'device_type', 'ip_type', 'status', 'is_online']:
        if key in data and data[key] is not None:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if not fields:
        conn.close()
        return get_device(device_id)

    fields.append("updated_at = ?")
    values.append(now_local())
    values.append(device_id)

    conn.execute(f"UPDATE devices SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone())
    conn.close()
    return result


def upsert_device_by_mac(data: dict) -> dict:
    """Insert or update device by MAC address (used during scans)."""
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM devices WHERE mac_address = ?",
        (data.get('mac_address'),)
    ).fetchone()
    created = False
    if not existing and data.get('ip_address'):
        # A device known only by its IP (routed VLAN / manual entry) whose MAC
        # is now known (e.g. from UniFi): give it the MAC instead of duplicating.
        existing = conn.execute("""
            SELECT * FROM devices
            WHERE ip_address = ? AND (mac_address IS NULL OR mac_address = '')
            ORDER BY id LIMIT 1
        """, (data.get('ip_address'),)).fetchone()
        if existing:
            conn.execute("UPDATE devices SET mac_address = ? WHERE id = ?",
                         (data.get('mac_address'), existing['id']))

    if existing:
        existing = dict(existing)
        ts = now_local()
        # Update IP, hostname, brand (if empty), device_type (if 'other'), mark online
        conn.execute("""
            UPDATE devices SET
                ip_address = ?,
                hostname = COALESCE(NULLIF(?, ''), hostname),
                brand = CASE WHEN brand IS NULL OR brand = '' OR brand LIKE '(%' THEN ? ELSE brand END,
                device_type = CASE WHEN device_type IS NULL OR device_type = 'other' THEN ? ELSE device_type END,
                network_name = COALESCE(NULLIF(?, ''), network_name),
                is_online = 1,
                last_seen = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            data.get('ip_address'),
            data.get('hostname'),
            data.get('brand', ''),
            data.get('device_type', 'other'),
            data.get('network_name', ''),
            ts, ts,
            existing['id']
        ))
        _release_ip(conn, data.get('ip_address'), existing['id'], ts)
        conn.commit()
        result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (existing['id'],)).fetchone())
    else:
        cursor = conn.cursor()
        ts = now_local()
        cursor.execute("""
            INSERT INTO devices (ip_address, mac_address, hostname, brand, device_type, network_name,
                                 status, is_online, first_seen, last_seen, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'new', 1, ?, ?, ?, ?)
        """, (
            data.get('ip_address'),
            data.get('mac_address'),
            data.get('hostname'),
            data.get('brand', ''),
            data.get('device_type', 'other'),
            data.get('network_name') or None,
            ts, ts, ts, ts,
        ))
        created = True
        _release_ip(conn, data.get('ip_address'), cursor.lastrowid, ts)
        conn.commit()
        result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (cursor.lastrowid,)).fetchone())

    conn.close()
    result['_created'] = created
    return result


def _release_ip(conn, ip: str, owner_id: int, ts: str):
    """`owner_id` now holds `ip`: free it on any other device identified by a
    MAC (the old IP is kept in last_ip). Manual devices without a MAC are
    identified only by their IP, so they are never touched."""
    if not ip:
        return
    conn.execute("""
        UPDATE devices SET last_ip = ip_address, ip_address = NULL, updated_at = ?
        WHERE ip_address = ? AND id != ?
          AND mac_address IS NOT NULL AND mac_address != ''
    """, (ts, ip, owner_id))


def server_language(settings: dict = None) -> str:
    """Language of the texts generated by the server (Telegram, hints):
    the configured one, or the one the UI reported when it is 'auto'."""
    s = settings if settings is not None else get_settings()
    lang = s.get('language') or 'auto'
    if lang in ('es', 'en'):
        return lang
    return s.get('ui_language') if s.get('ui_language') in ('es', 'en') else 'en'


def refresh_hints(guess, lang: str = None) -> int:
    """Fill / update the description hint of 'new' devices whose description
    is empty or was written by NetTools. `guess(device, ports) -> str`."""
    if lang is None:
        lang = server_language()
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM devices
        WHERE status = 'new'
          AND (description_auto = 1
               OR (description_auto IS NULL AND (description IS NULL OR description = '')))
    """).fetchall()
    changed = 0
    for r in rows:
        d = dict(r)
        ports = [dict(p) for p in conn.execute(
            "SELECT port, service FROM device_ports WHERE device_id = ?", (d['id'],))]
        hint = guess(d, ports, lang) or ''
        if hint != (d['description'] or ''):
            conn.execute("UPDATE devices SET description = ?, description_auto = ? WHERE id = ?",
                         (hint or None, 1 if hint else None, d['id']))
            changed += 1
    conn.commit()
    conn.close()
    return changed


def fix_ip_conflicts() -> int:
    """One-off cleanup for data created before IPs were released: when several
    MAC-identified devices share an IP, keep it on the most recently seen one."""
    conn = get_db()
    ts = now_local()
    fixed = 0
    rows = conn.execute("""
        SELECT ip_address FROM devices
        WHERE ip_address IS NOT NULL AND ip_address != ''
          AND mac_address IS NOT NULL AND mac_address != ''
        GROUP BY ip_address HAVING COUNT(*) > 1
    """).fetchall()
    for r in rows:
        owner = conn.execute("""
            SELECT id FROM devices
            WHERE ip_address = ? AND mac_address IS NOT NULL AND mac_address != ''
            ORDER BY is_online DESC, last_seen DESC LIMIT 1
        """, (r['ip_address'],)).fetchone()
        cur = conn.execute("""
            UPDATE devices SET last_ip = ip_address, ip_address = NULL, updated_at = ?
            WHERE ip_address = ? AND id != ? AND mac_address IS NOT NULL AND mac_address != ''
        """, (ts, r['ip_address'], owner['id']))
        fixed += cur.rowcount
    conn.commit()
    conn.close()
    return fixed


def backfill_vendors(resolve) -> int:
    """Fill empty / placeholder brands using `resolve(mac) -> vendor`."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, mac_address, brand FROM devices
        WHERE mac_address IS NOT NULL AND mac_address != ''
          AND (brand IS NULL OR brand = '' OR brand LIKE '(%')
    """).fetchall()
    updated = 0
    for r in rows:
        vendor = resolve(r['mac_address'])
        if vendor != (r['brand'] or ''):
            conn.execute("UPDATE devices SET brand = ? WHERE id = ?", (vendor, r['id']))
            updated += 1
    conn.commit()
    conn.close()
    return updated


def merge_devices(target_id: int, source_id: int) -> dict:
    """Merge `source` into `target`.

    The target keeps its identity (name, description, type, location, IP type,
    status) and adopts the source's network identity (MAC, IP, online state).
    Ports and ping results move to the target; the source is deleted.
    Typical use: a phone/laptop reappears with a new private MAC.
    """
    if target_id == source_id:
        raise ValueError("No se puede fusionar un dispositivo consigo mismo")
    conn = get_db()
    target = conn.execute("SELECT * FROM devices WHERE id = ?", (target_id,)).fetchone()
    source = conn.execute("SELECT * FROM devices WHERE id = ?", (source_id,)).fetchone()
    if not target or not source:
        conn.close()
        raise LookupError("Dispositivo no encontrado")
    target, source = dict(target), dict(source)
    ts = now_local()

    def first(*vals):
        for v in vals:
            if v not in (None, ''):
                return v
        return None

    # Current IP: the source's (it is the device's current network identity);
    # if it has none, keep the target's only while the target is online.
    if source['ip_address']:
        new_ip = source['ip_address']
    elif target['is_online']:
        new_ip = target['ip_address']
    else:
        new_ip = None
    new_last_ip = first(
        target['ip_address'] if target['ip_address'] != new_ip else None,
        source['last_ip'], target['last_ip'],
    )
    if new_last_ip == new_ip:
        new_last_ip = None
    conn.execute("""
        UPDATE devices SET
            mac_address = ?, ip_address = ?, last_ip = ?,
            hostname = ?, brand = ?,
            is_online = ?,
            first_seen = ?, last_seen = ?,
            last_port_scan = ?,
            status = CASE WHEN status = 'new' THEN 'saved' ELSE status END,
            updated_at = ?
        WHERE id = ?
    """, (
        first(source['mac_address'], target['mac_address']),
        new_ip,
        new_last_ip,
        first(source['hostname'], target['hostname']),
        first(target['brand'] if not (target['brand'] or '').startswith('(') else None, source['brand']) or '',
        1 if (source['is_online'] or target['is_online']) else 0,
        min(x for x in (source['first_seen'], target['first_seen']) if x) if (source['first_seen'] or target['first_seen']) else None,
        max(x for x in (source['last_seen'], target['last_seen']) if x) if (source['last_seen'] or target['last_seen']) else None,
        max(x for x in (source['last_port_scan'], target['last_port_scan']) if x) if (source['last_port_scan'] or target['last_port_scan']) else None,
        ts,
        target_id,
    ))
    # Ports: the source reflects the current host; keep target ports it doesn't have
    conn.execute("""
        DELETE FROM device_ports WHERE device_id = ? AND (port, protocol) IN
            (SELECT port, protocol FROM device_ports WHERE device_id = ?)
    """, (target_id, source_id))
    conn.execute("UPDATE device_ports SET device_id = ? WHERE device_id = ?", (target_id, source_id))
    conn.execute("UPDATE ping_results SET device_id = ? WHERE device_id = ?", (target_id, source_id))
    conn.execute("""
        UPDATE inventory SET device_id = ? WHERE device_id = ?
          AND NOT EXISTS (SELECT 1 FROM inventory WHERE device_id = ?)
    """, (target_id, source_id, target_id))
    conn.execute("DELETE FROM devices WHERE id = ?", (source_id,))
    _release_ip(conn, new_ip, target_id, ts)
    conn.commit()
    result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (target_id,)).fetchone())
    conn.close()
    return result


def upsert_device_by_ip(data: dict) -> dict:
    """Insert or update a device without a visible MAC (found on a routed
    network / VLAN), identified by its IP."""
    conn = get_db()
    ts = now_local()
    existing = conn.execute("""
        SELECT * FROM devices
        WHERE ip_address = ? AND (mac_address IS NULL OR mac_address = '')
        ORDER BY id LIMIT 1
    """, (data.get('ip_address'),)).fetchone()
    if existing:
        conn.execute("""
            UPDATE devices SET
                hostname = COALESCE(NULLIF(?, ''), hostname),
                device_type = CASE WHEN device_type IS NULL OR device_type = 'other' THEN ? ELSE device_type END,
                is_online = 1, last_seen = ?, updated_at = ?
            WHERE id = ?
        """, (data.get('hostname'), data.get('device_type', 'other'), ts, ts, existing['id']))
        row_id = existing['id']
        created = False
    else:
        cur = conn.execute("""
            INSERT INTO devices (ip_address, mac_address, hostname, brand, device_type, status, is_online,
                                 first_seen, last_seen, created_at, updated_at)
            VALUES (?, NULL, ?, '', ?, 'new', 1, ?, ?, ?, ?)
        """, (data.get('ip_address'), data.get('hostname'), data.get('device_type', 'other'), ts, ts, ts, ts))
        row_id = cur.lastrowid
        created = True
    conn.commit()
    result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (row_id,)).fetchone())
    conn.close()
    result['_created'] = created
    return result


def get_all_mac_addresses() -> set:
    """Return a set of all known MAC addresses."""
    conn = get_db()
    rows = conn.execute("SELECT mac_address FROM devices WHERE mac_address IS NOT NULL AND mac_address != ''").fetchall()
    conn.close()
    return {row['mac_address'] for row in rows}


def mark_all_offline():
    """Mark all devices as offline before scan."""
    conn = get_db()
    conn.execute("UPDATE devices SET is_online = 0 WHERE status != 'manual'")
    conn.commit()
    conn.close()


def delete_device(device_id: int):
    conn = get_db()
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()


def bulk_delete_devices(ids: list) -> int:
    if not ids:
        return 0
    conn = get_db()
    q = ','.join('?' * len(ids))
    cur = conn.execute(f"DELETE FROM devices WHERE id IN ({q})", ids)
    conn.commit()
    conn.close()
    return cur.rowcount


def bulk_update_devices(ids: list, status: str = None, device_type: str = None, location: str = None) -> int:
    """Apply the same change to several devices. status 'saved' only promotes
    'new' devices (manual ones stay manual); 'new' only demotes saved ones."""
    if not ids:
        return 0
    sets, params = [], []
    if status == 'saved':
        sets.append("status = CASE WHEN status = 'new' THEN 'saved' ELSE status END")
    elif status == 'new':
        sets.append("status = CASE WHEN status = 'saved' THEN 'new' ELSE status END")
    if device_type is not None:
        sets.append("device_type = ?")
        params.append(device_type)
    if location is not None:
        sets.append("location = ?")
        params.append(location)
    if not sets:
        return 0
    sets.append("updated_at = ?")
    params.append(now_local())
    conn = get_db()
    q = ','.join('?' * len(ids))
    cur = conn.execute(f"UPDATE devices SET {', '.join(sets)} WHERE id IN ({q})", params + list(ids))
    conn.commit()
    conn.close()
    return cur.rowcount


def clear_devices():
    conn = get_db()
    conn.execute("DELETE FROM devices")
    conn.commit()
    conn.close()


# --- Device Ports ---
def get_port_scan_targets(scope: str = 'online') -> list:
    """Devices to include in the bulk port scan: online with an IP;
    scope 'saved' limits it to saved/manual devices."""
    conn = get_db()
    query = ("SELECT id, ip_address, mac_address, hostname, custom_name, status FROM devices "
             "WHERE is_online = 1 AND ip_address IS NOT NULL AND ip_address != ''")
    if scope == 'saved':
        query += " AND status IN ('saved', 'manual')"
    rows = conn.execute(query + " ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_device_ports(device_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM device_ports WHERE device_id = ? ORDER BY port ASC", (device_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_port_scan(device_id: int, scan: dict) -> dict:
    """Merge a port scan result into device_ports.

    - Ports open now: inserted (first_seen = now) or refreshed (last_seen = now).
    - Known ports that were probed in this scan and are no longer open: removed.
      Known ports outside the probed range (e.g. found by a previous full scan
      and not covered by a quick scan) are kept untouched.

    Returns {first_scan, new_ports, closed_ports, scanned_at}.
    """
    conn = get_db()
    ts = now_local()
    device = conn.execute("SELECT last_port_scan FROM devices WHERE id = ?", (device_id,)).fetchone()
    first_scan = device is None or device['last_port_scan'] is None

    known = {
        (r['port'], r['protocol']): dict(r)
        for r in conn.execute("SELECT * FROM device_ports WHERE device_id = ?", (device_id,))
    }
    open_now = {(p['port'], p['protocol']): p for p in scan['open_ports']}
    scanned = scan.get('scanned_ports') or set()

    new_ports = []
    for key, p in open_now.items():
        if key in known:
            conn.execute("""
                UPDATE device_ports SET last_seen = ?,
                    service = COALESCE(NULLIF(?, ''), service),
                    product = COALESCE(NULLIF(?, ''), product),
                    version = COALESCE(NULLIF(?, ''), version),
                    tunnel = COALESCE(NULLIF(?, ''), tunnel)
                WHERE id = ?
            """, (ts, p['service'], p['product'], p['version'], p.get('tunnel', ''), known[key]['id']))
        else:
            conn.execute("""
                INSERT INTO device_ports (device_id, port, protocol, service, product, version, tunnel, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (device_id, p['port'], p['protocol'], p['service'], p['product'], p['version'],
                  p.get('tunnel', ''), ts, ts))
            new_ports.append(p)

    closed_ports = []
    for key, row in known.items():
        if key not in open_now and key[1] == 'tcp' and key[0] in scanned:
            conn.execute("DELETE FROM device_ports WHERE id = ?", (row['id'],))
            closed_ports.append(row)

    conn.execute("UPDATE devices SET last_port_scan = ? WHERE id = ?", (ts, device_id))
    conn.commit()
    conn.close()
    return {
        'first_scan': first_scan,
        'new_ports': new_ports,
        'closed_ports': closed_ports,
        'scanned_at': ts,
    }


# --- Ping Results ---
def save_ping_result(data: dict) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ping_results (timestamp, device_id, ip_address, latency, is_reachable)
        VALUES (?, ?, ?, ?, ?)
    """, (
        now_local(),
        data.get('device_id'),
        data.get('ip_address'),
        data.get('latency'),
        data.get('is_reachable', 0),
    ))
    conn.commit()
    conn.close()


# --- Device Snapshots (history) ---
def save_device_snapshot():
    """Save a snapshot of current device counts (called after each scan)."""
    conn = get_db()
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_online = 1 THEN 1 ELSE 0 END) as online,
            SUM(CASE WHEN is_online = 0 THEN 1 ELSE 0 END) as offline,
            SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_devices
        FROM devices
    """).fetchone()

    conn.execute("""
        INSERT INTO device_snapshots (timestamp, total_devices, online_devices, offline_devices, new_devices)
        VALUES (?, ?, ?, ?, ?)
    """, (
        now_local(),
        row['total'] or 0,
        row['online'] or 0,
        row['offline'] or 0,
        row['new_devices'] or 0,
    ))
    conn.commit()
    conn.close()


def get_device_snapshots(range_filter: str = '24h', limit: int = 500) -> list:
    """Get device snapshot history."""
    conn = get_db()
    time_filter = _get_time_filter(range_filter)
    query = "SELECT * FROM device_snapshots"
    params = []

    if time_filter:
        query += " WHERE timestamp >= datetime(?, ?)"
        params.append(now_local())
        params.append(time_filter)

    query += " ORDER BY timestamp ASC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Settings ---
def get_settings() -> dict:
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    settings = {}
    for row in rows:
        key, value = row['key'], row['value']
        if value == 'true':
            settings[key] = True
        elif value == 'false':
            settings[key] = False
        else:
            settings[key] = value
    return settings


# Settings that are never sent back to the browser (only "<key>_set": bool)
SECRET_SETTINGS = ('telegram_bot_token', 'unifi_api_key', 'unifi_password',
                   'auth_local_password_hash', 'auth_ldap_bind_password', 'auth_oidc_client_secret')


def get_public_settings() -> dict:
    s = get_settings()
    for k in SECRET_SETTINGS:
        s[f'{k}_set'] = bool(s.get(k))
        s[k] = ''
    return s


# --- Sessions (login) ---
def _hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(token: str, username: str, method: str, days: int,
                   display_name: str = None, avatar: str = None) -> None:
    now = now_local()
    expires = (_ts(now) + timedelta(days=max(1, days))).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    conn.execute("INSERT INTO sessions (token_hash, username, method, created_at, expires_at, last_seen, display_name, avatar) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (_hash_token(token), username, method, now, expires, now, display_name, avatar))
    conn.commit()
    conn.close()


def get_session(token: str):
    if not token:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM sessions WHERE token_hash = ? AND expires_at > ?",
                       (_hash_token(token), now_local())).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token or ''),))
    conn.commit()
    conn.close()


def delete_all_sessions():
    conn = get_db()
    conn.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()


def save_oidc_state(state, verifier, nonce, next_url, redirect_uri):
    import time as _time
    conn = get_db()
    conn.execute("DELETE FROM oidc_states WHERE created_at < ?", (_time.time() - 600,))
    conn.execute("INSERT INTO oidc_states VALUES (?, ?, ?, ?, ?, ?)",
                 (state, verifier, nonce, next_url, redirect_uri, _time.time()))
    conn.commit()
    conn.close()


def pop_oidc_state(state):
    import time as _time
    conn = get_db()
    row = conn.execute("SELECT * FROM oidc_states WHERE state = ? AND created_at > ?",
                       (state or '', _time.time() - 600)).fetchone()
    conn.execute("DELETE FROM oidc_states WHERE state = ?", (state or '',))
    conn.commit()
    conn.close()
    return dict(row) if row else None


def update_settings(data: dict):
    conn = get_db()
    ts = now_local()
    for key, value in data.items():
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
        """, (key, str(value), ts, str(value), ts))
    conn.commit()
    conn.close()


# --- Retention ---
def purge_old_data(retention_days: int) -> dict:
    """Delete speed tests, ping results and device snapshots older than
    `retention_days`. 0 (or less) means keep everything."""
    if not retention_days or retention_days <= 0:
        return {}
    conn = get_db()
    cutoff_params = (now_local(), f'-{int(retention_days)} days')
    deleted = {}
    for table in ('speed_tests', 'ping_results', 'device_snapshots', 'connectivity_checks'):
        cur = conn.execute(
            f"DELETE FROM {table} WHERE timestamp < datetime(?, ?)", cutoff_params
        )
        deleted[table] = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def purge_stale_devices(days: int) -> list:
    """Delete devices that were never saved by the user (status 'new'), have
    no current IP (it was released to another device) and have not been seen
    for more than `days` days. Saved and manual devices are never deleted.
    Returns the deleted rows."""
    if not days or days <= 0:
        return []
    conn = get_db()
    where = """
        status = 'new' AND is_online = 0
        AND (ip_address IS NULL OR ip_address = '')
        AND last_seen < datetime(?, ?)
    """
    params = (now_local(), f'-{int(days)} days')
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM devices WHERE {where}", params)]
    if rows:
        conn.execute(f"DELETE FROM devices WHERE {where}", params)
        conn.commit()
    conn.close()
    return rows


# --- Connectivity / outages ---
def _ts(s: str) -> datetime:
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')


def save_connectivity_check(gateway_ok, internet_ok, latency):
    conn = get_db()
    conn.execute(
        "INSERT INTO connectivity_checks (timestamp, gateway_ok, internet_ok, latency) VALUES (?, ?, ?, ?)",
        (now_local(), None if gateway_ok is None else int(bool(gateway_ok)), int(bool(internet_ok)), latency))
    conn.commit()
    conn.close()


def get_open_outage():
    conn = get_db()
    row = conn.execute("SELECT * FROM outages WHERE end IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def open_outage(kind: str, failed_checks: int = 1, interval: int = 60) -> dict:
    """Start an outage, back-dated to the first failed check."""
    now = now_local()
    start = (_ts(now) - timedelta(seconds=max(0, failed_checks - 1) * interval)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cur = conn.execute("INSERT INTO outages (kind, start, last_seen) VALUES (?, ?, ?)", (kind, start, now))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM outages WHERE id = ?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


def touch_outage(outage_id: int):
    conn = get_db()
    conn.execute("UPDATE outages SET last_seen = ? WHERE id = ?", (now_local(), outage_id))
    conn.commit()
    conn.close()


def close_outage(outage_id: int, end: str = None) -> dict:
    conn = get_db()
    row = dict(conn.execute("SELECT * FROM outages WHERE id = ?", (outage_id,)).fetchone())
    end = end or now_local()
    duration = max(0, int((_ts(end) - _ts(row['start'])).total_seconds()))
    conn.execute("UPDATE outages SET end = ?, duration = ? WHERE id = ?", (end, duration, outage_id))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM outages WHERE id = ?", (outage_id,)).fetchone())
    conn.close()
    return row


def close_stale_outages() -> int:
    """At startup: an outage left open when NetTools stopped ends at the last
    failed check that was seen (we don't know what happened afterwards)."""
    n = 0
    for o in [dict(r) for r in _rows("SELECT * FROM outages WHERE end IS NULL")]:
        close_outage(o['id'], o['last_seen'] or o['start'])
        n += 1
    return n


def _rows(query, params=()):
    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_connectivity(range_filter: str = '24h') -> dict:
    """Availability summary, timeline buckets and outages for a range."""
    ranges = {'24h': (24 * 3600, 600), '7d': (7 * 86400, 3600), '30d': (30 * 86400, 6 * 3600)}
    span, bucket = ranges.get(range_filter, ranges['24h'])
    now = _ts(now_local())
    since = (now - timedelta(seconds=span)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    buckets = [dict(r) for r in conn.execute(f"""
        SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / {bucket}) * {bucket} AS b,
               COUNT(*) AS total,
               SUM(internet_ok) AS internet_ok,
               SUM(CASE WHEN gateway_ok = 0 THEN 1 ELSE 0 END) AS gateway_down,
               AVG(latency) AS latency
        FROM connectivity_checks WHERE timestamp >= ?
        GROUP BY b ORDER BY b
    """, (since,))]
    totals = conn.execute(
        "SELECT COUNT(*), SUM(internet_ok) FROM connectivity_checks WHERE timestamp >= ?", (since,)).fetchone()
    last = conn.execute("SELECT * FROM connectivity_checks ORDER BY id DESC LIMIT 1").fetchone()
    outages = [dict(r) for r in conn.execute(
        "SELECT * FROM outages WHERE COALESCE(end, last_seen, start) >= ? ORDER BY start DESC LIMIT 100", (since,))]
    conn.close()
    for b in buckets:
        b['time'] = datetime.utcfromtimestamp(b.pop('b')).strftime('%Y-%m-%d %H:%M:%S')
    total, ok = totals[0] or 0, totals[1] or 0
    open_ev = next((o for o in outages if o['end'] is None), None)
    return {
        'range': range_filter,
        'bucket_seconds': bucket,
        'since': since,
        'now': now.strftime('%Y-%m-%d %H:%M:%S'),
        'checks': total,
        'uptime': round(ok / total * 100, 2) if total else None,
        'buckets': buckets,
        'outages': outages,
        'outage_count': len(outages),
        'downtime': sum((o['duration'] or 0) for o in outages if o['end']),
        'last_check': dict(last) if last else None,
        'current_outage': open_ev,
    }


# --- Notifications (bell panel) ---
MAX_NOTIFICATIONS = 500


def add_notification(type_: str, data: dict, level: str = 'info') -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO notifications (created_at, type, level, data, read) VALUES (?, ?, ?, ?, 0)",
        (now_local(), type_, level, json.dumps(data, default=str)))
    conn.execute("""
        DELETE FROM notifications WHERE id NOT IN
            (SELECT id FROM notifications ORDER BY id DESC LIMIT ?)
    """, (MAX_NOTIFICATIONS,))
    conn.commit()
    conn.close()
    return cur.lastrowid


def get_notifications(limit: int = 50) -> dict:
    conn = get_db()
    rows = conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE read = 0").fetchone()[0]
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d['data'] = json.loads(d['data'] or '{}')
        except ValueError:
            d['data'] = {}
        d['read'] = bool(d['read'])
        items.append(d)
    return {'items': items, 'unread': unread}


def mark_notifications_read(notification_id: int = None) -> int:
    conn = get_db()
    if notification_id is None:
        cur = conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    else:
        cur = conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()
    return cur.rowcount


# --- Inventory ---
# Fields mirrored from the linked Net Alert device (the device is the source
# of truth while linked; the inventory keeps the last copy if it is deleted).
INVENTORY_DEVICE_FIELDS = ('name', 'device_type', 'brand', 'location', 'description')
INVENTORY_ASSET_FIELDS = ('model', 'serial_number', 'purchase_date', 'purchase_price',
                          'warranty_until', 'supplier', 'notes', 'asset_status',
                          'asset_kind', 'host')


def sync_inventory():
    """Make sure every saved/manual device has an inventory entry and copy
    the device data into the linked entries."""
    conn = get_db()
    ts = now_local()
    missing = conn.execute("""
        SELECT * FROM devices d
        WHERE d.status IN ('saved', 'manual')
          AND NOT EXISTS (SELECT 1 FROM inventory i WHERE i.device_id = d.id)
    """).fetchall()
    for d in missing:
        relink = None
        if d['mac_address']:
            # Entry left behind when the device was deleted / reset: relink it
            relink = conn.execute("""
                SELECT id FROM inventory WHERE device_id IS NULL AND UPPER(mac_address) = UPPER(?)
                ORDER BY hidden, id LIMIT 1
            """, (d['mac_address'],)).fetchone()
        if relink:
            conn.execute("UPDATE inventory SET device_id = ?, hidden = 0, updated_at = ? WHERE id = ?",
                         (d['id'], ts, relink['id']))
            # The rediscovered device gets back the name/location/... kept in the inventory
            conn.execute("""
                UPDATE devices SET
                    custom_name = COALESCE(NULLIF(custom_name, ''), (SELECT name FROM inventory WHERE id = ?)),
                    location = COALESCE(NULLIF(location, ''), (SELECT location FROM inventory WHERE id = ?)),
                    description = COALESCE(NULLIF(description, ''), (SELECT description FROM inventory WHERE id = ?)),
                    device_type = CASE WHEN device_type IS NULL OR device_type = 'other'
                                       THEN COALESCE((SELECT device_type FROM inventory WHERE id = ?), device_type)
                                       ELSE device_type END
                WHERE id = ?
            """, (relink['id'],) * 4 + (d['id'],))
        else:
            conn.execute("""
                INSERT INTO inventory (device_id, asset_status, created_at, updated_at)
                VALUES (?, 'active', ?, ?)
            """, (d['id'], ts, ts))
    # Mirror device data into linked entries
    conn.execute("""
        UPDATE inventory SET
            name = (SELECT COALESCE(NULLIF(d.custom_name, ''), NULLIF(d.hostname, ''),
                                    d.ip_address, d.last_ip, inventory.name)
                    FROM devices d WHERE d.id = inventory.device_id),
            device_type = (SELECT COALESCE(d.device_type, inventory.device_type) FROM devices d WHERE d.id = inventory.device_id),
            brand = (SELECT COALESCE(d.brand, inventory.brand) FROM devices d WHERE d.id = inventory.device_id),
            location = (SELECT COALESCE(d.location, inventory.location) FROM devices d WHERE d.id = inventory.device_id),
            description = (SELECT COALESCE(d.description, inventory.description) FROM devices d WHERE d.id = inventory.device_id),
            mac_address = (SELECT COALESCE(NULLIF(d.mac_address, ''), inventory.mac_address) FROM devices d WHERE d.id = inventory.device_id),
            ip_address = (SELECT COALESCE(NULLIF(d.ip_address, ''), NULLIF(d.last_ip, ''), inventory.ip_address)
                          FROM devices d WHERE d.id = inventory.device_id)
        WHERE device_id IS NOT NULL
    """)
    conn.commit()
    conn.close()


def get_inventory(include_hidden: bool = False) -> list:
    sync_inventory()
    conn = get_db()
    rows = conn.execute(f"""
        SELECT i.*, d.is_online, d.status AS device_status, d.last_seen,
               d.ip_address AS current_ip, d.network_name
        FROM inventory i LEFT JOIN devices d ON d.id = i.device_id
        {'' if include_hidden else 'WHERE i.hidden = 0'}
        ORDER BY i.asset_status, LOWER(COALESCE(i.name, ''))
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory_item(item_id: int) -> dict:
    conn = get_db()
    row = conn.execute("""
        SELECT i.*, d.is_online, d.status AS device_status, d.last_seen,
               d.ip_address AS current_ip, d.network_name
        FROM inventory i LEFT JOIN devices d ON d.id = i.device_id WHERE i.id = ?
    """, (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_inventory_item(data: dict) -> dict:
    """Item that is not on the network (or not in Net Alert)."""
    conn = get_db()
    ts = now_local()
    fields = INVENTORY_DEVICE_FIELDS + INVENTORY_ASSET_FIELDS + ('mac_address', 'ip_address')
    values = {k: data.get(k) for k in fields if data.get(k) is not None}
    values.setdefault('asset_status', 'active')
    cols = list(values) + ['created_at', 'updated_at']
    cur = conn.execute(
        f"INSERT INTO inventory ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        list(values.values()) + [ts, ts])
    conn.commit()
    conn.close()
    return get_inventory_item(cur.lastrowid)


def update_inventory_item(item_id: int, data: dict) -> dict:
    item = get_inventory_item(item_id)
    if not item:
        raise LookupError("Elemento de inventario no encontrado")
    linked = item['device_id'] is not None
    ts = now_local()
    editable = INVENTORY_DEVICE_FIELDS + INVENTORY_ASSET_FIELDS
    if not linked:
        editable += ('mac_address', 'ip_address')
    # None is ignored, except for the price (null clears it)
    values = {k: data[k] for k in editable
              if k in data and (data[k] is not None or k == 'purchase_price')}
    if linked:
        # Shared fields are the device's: write them to Net Alert too
        dev = {('custom_name' if k == 'name' else k): values[k]
               for k in INVENTORY_DEVICE_FIELDS if k in values}
        if dev:
            update_device(item['device_id'], dev)
    if values:
        conn = get_db()
        sets = ', '.join(f"{k} = ?" for k in values)
        conn.execute(f"UPDATE inventory SET {sets}, updated_at = ? WHERE id = ?",
                     list(values.values()) + [ts, item_id])
        conn.commit()
        conn.close()
    return get_inventory_item(item_id)


def delete_inventory_item(item_id: int) -> bool:
    """Remove from the inventory. An entry still linked to a saved device is
    only hidden (otherwise the next sync would add it again)."""
    item = get_inventory_item(item_id)
    if not item:
        return False
    conn = get_db()
    if item['device_id'] is not None and item['device_status'] in ('saved', 'manual'):
        conn.execute("UPDATE inventory SET hidden = 1, updated_at = ? WHERE id = ?", (now_local(), item_id))
    else:
        conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return True


# --- Helpers ---
def _get_time_filter(range_str: str) -> str:
    filters = {
        '1h': '-1 hours',
        '6h': '-6 hours',
        '24h': '-24 hours',
        '7d': '-7 days',
        '30d': '-30 days',
        '90d': '-90 days',
        '365d': '-365 days',
    }
    return filters.get(range_str)


def _all_device_ports() -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM device_ports ORDER BY device_id, port").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_data() -> dict:
    """Export all data."""
    return {
        'exported_at': datetime.now().isoformat(),
        'speed_tests': get_speed_tests(range_filter='all', limit=10000),
        'devices': get_devices(),
        'device_ports': _all_device_ports(),
        'inventory': get_inventory(),
        'settings': get_public_settings(),
    }
