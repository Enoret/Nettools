"""
Load a NetTools JSON export (GET /api/export) into a NetTools SQLite database.

Used to seed a development instance with a copy of production data.
Telegram is disabled in the target unless --keep-telegram is given, so a dev
instance does not send duplicate alerts.

Usage:
    python3 import_export.py export.json /path/to/nettools.db [--keep-telegram]

The target DB must not be in use (stop the container first) or be new.
"""

import json
import sqlite3
import sys

SPEED_COLS = ['id', 'timestamp', 'download_speed', 'upload_speed', 'ping', 'jitter',
              'server_name', 'server_id', 'server_location', 'isp', 'external_ip', 'raw_data']
DEVICE_COLS = ['id', 'ip_address', 'mac_address', 'hostname', 'custom_name', 'description',
               'brand', 'location', 'device_type', 'ip_type', 'status', 'is_online',
               'first_seen', 'last_seen', 'created_at', 'updated_at']


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    export_path, db_path = sys.argv[1], sys.argv[2]
    keep_telegram = '--keep-telegram' in sys.argv

    with open(export_path) as f:
        data = json.load(f)

    # Create schema using the backend's own init_db
    import os
    os.environ['NETTOOLS_DB_PATH'] = db_path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'docker', 'backend'))
    import database
    database.DB_PATH = db_path
    database.init_db()

    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM speed_tests")
    conn.execute("DELETE FROM devices")

    for t in data.get('speed_tests', []):
        conn.execute(
            f"INSERT INTO speed_tests ({', '.join(SPEED_COLS)}) VALUES ({', '.join('?' * len(SPEED_COLS))})",
            [t.get(c) for c in SPEED_COLS],
        )
    for d in data.get('devices', []):
        conn.execute(
            f"INSERT INTO devices ({', '.join(DEVICE_COLS)}) VALUES ({', '.join('?' * len(DEVICE_COLS))})",
            [d.get(c) for c in DEVICE_COLS],
        )

    settings = dict(data.get('settings', {}))
    if not keep_telegram:
        settings['telegram_enabled'] = False
    # Exports from versions without enforced retention: keep all history,
    # same rule as the init_db() migration.
    if 'retention_migrated' not in settings:
        settings['speed_test_retention'] = '0'
        settings['retention_migrated'] = True
    for key, value in settings.items():
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    conn.commit()
    n_tests = conn.execute("SELECT COUNT(*) FROM speed_tests").fetchone()[0]
    n_devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    conn.close()
    print(f"Imported {n_tests} speed tests, {n_devices} devices, {len(settings)} settings "
          f"(telegram {'kept' if keep_telegram else 'disabled'})")


if __name__ == '__main__':
    main()
