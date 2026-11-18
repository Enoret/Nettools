"""Usage: python merge_dev_into_prod.py dev.db prod.db out.db

Build the new prod DB: dev data (devices, inventory, ports, settings...) +
prod speed test history, device history and Telegram settings."""
import shutil, sqlite3, sys
dev, prod, out = sys.argv[1:4]
shutil.copyfile(dev, out)
c = sqlite3.connect(out)
c.execute("PRAGMA journal_mode=DELETE")
c.execute("ATTACH ? AS prod", (prod,))
def cols(schema, table):
    return [r[1] for r in c.execute(f"PRAGMA {schema}.table_info({table})")]
for table in ('speed_tests', 'device_snapshots'):
    common = [x for x in cols('main', table) if x in cols('prod', table)]
    before = c.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
    c.execute(f"DELETE FROM main.{table}")
    cl = ', '.join(common)
    c.execute(f"INSERT INTO main.{table} ({cl}) SELECT {cl} FROM prod.{table}")
    after = c.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
    print(f"{table}: dev {before} -> prod {after}")
for key in ('telegram_enabled', 'telegram_bot_token', 'telegram_chat_id'):
    row = c.execute("SELECT value FROM prod.settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        c.execute("INSERT INTO main.settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, row[0]))
        print(f"setting {key}: from prod" + (f" = {row[0]}" if key == 'telegram_enabled' else ''))
c.commit()
c.execute("DETACH prod")
print("devices", c.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
      "inventory", c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
      "ports", c.execute("SELECT COUNT(*) FROM device_ports").fetchone()[0])
print("integrity", c.execute("PRAGMA integrity_check").fetchone()[0])
c.close()
