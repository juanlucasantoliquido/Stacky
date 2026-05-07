import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "data", "stacky_agents.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# All 502 responses ever
cur.execute("SELECT * FROM system_logs WHERE status_code = 502 ORDER BY timestamp DESC LIMIT 20")
rows = cur.fetchall()
print(f"--- 502 responses ({len(rows)} rows) ---")
for r in rows:
    print(r)

# All sync endpoint calls
cur.execute("SELECT id, timestamp, status_code, duration_ms, error_json FROM system_logs WHERE endpoint LIKE '%sync%' ORDER BY timestamp DESC LIMIT 30")
rows = cur.fetchall()
print(f"\n--- Sync endpoint calls ({len(rows)} rows) ---")
for r in rows:
    print(r)

# Error-level logs related to ADO
cur.execute("SELECT * FROM system_logs WHERE level = 'ERROR' OR (error_json IS NOT NULL AND error_json != 'null') ORDER BY timestamp DESC LIMIT 20")
rows = cur.fetchall()
print(f"\n--- Error logs ({len(rows)} rows) ---")
for r in rows:
    print(r[:8])  # first 8 cols to keep readable

conn.close()
