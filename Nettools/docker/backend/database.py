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

    # Default settings
    defaults = {
        'auto_speed_test': 'true',
        'speed_test_frequency': '60',
        'speed_test_retention': '30',
        'auto_network_scan': 'true',
        'network_scan_frequency': '15',
        'network_range': '192.168.1.0/24',
        'notify_new_devices': 'true',
        'telegram_enabled': 'false',
        'telegram_bot_token': '',
        'telegram_chat_id': '',
        'timezone': '1',
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


def clear_speed_tests():
    conn = get_db()
    conn.execute("DELETE FROM speed_tests")
    conn.commit()
    conn.close()


# --- Devices ---
def get_devices(status_filter: str = None) -> list:
    conn = get_db()
    query = "SELECT * FROM devices"
    params = []

    if status_filter:
        query += " WHERE status = ?"
        params.append(status_filter)

    query += " ORDER BY is_online DESC, custom_name ASC, hostname ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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

    if existing:
        existing = dict(existing)
        ts = now_local()
        # Update IP, hostname, brand (if empty), device_type (if 'other'), mark online
        conn.execute("""
            UPDATE devices SET
                ip_address = ?,
                hostname = COALESCE(?, hostname),
                brand = CASE WHEN brand IS NULL OR brand = '' THEN ? ELSE brand END,
                device_type = CASE WHEN device_type IS NULL OR device_type = 'other' THEN ? ELSE device_type END,
                is_online = 1,
                last_seen = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            data.get('ip_address'),
            data.get('hostname'),
            data.get('brand', ''),
            data.get('device_type', 'other'),
            ts, ts,
            existing['id']
        ))
        conn.commit()
        result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (existing['id'],)).fetchone())
    else:
        cursor = conn.cursor()
        ts = now_local()
        cursor.execute("""
            INSERT INTO devices (ip_address, mac_address, hostname, brand, device_type, status, is_online,
                                 first_seen, last_seen, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'new', 1, ?, ?, ?, ?)
        """, (
            data.get('ip_address'),
            data.get('mac_address'),
            data.get('hostname'),
            data.get('brand', ''),
            data.get('device_type', 'other'),
            ts, ts, ts, ts,
        ))
        conn.commit()
        result = dict(conn.execute("SELECT * FROM devices WHERE id = ?", (cursor.lastrowid,)).fetchone())

    conn.close()
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


def clear_devices():
    conn = get_db()
    conn.execute("DELETE FROM devices")
    conn.commit()
    conn.close()


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


def get_all_data() -> dict:
    """Export all data."""
    return {
        'exported_at': datetime.now().isoformat(),
        'speed_tests': get_speed_tests(range_filter='all', limit=10000),
        'devices': get_devices(),
        'settings': get_settings(),
    }
