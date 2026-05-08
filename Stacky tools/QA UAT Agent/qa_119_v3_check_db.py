"""
qa_119_v3_check_db.py — Verifica estado de datos de prueba para ADO-119.
"""
import os, pyodbc, sys
sys.stdout.reconfigure(encoding='utf-8')

user = os.environ.get('RS_QA_DB_USER', '')
pwd  = os.environ.get('RS_QA_DB_PASS', '')
server = 'aisbddev02.cloud.ais-int.net'
cs = (f'DRIVER={{ODBC Driver 17 for SQL Server}};'
      f'SERVER={server};DATABASE=RSPACIFICO;UID={user};PWD={pwd};'
      f'TrustServerCertificate=yes;Connect Timeout=15;')

print(f"Connecting as: {user}")
conn = pyodbc.connect(cs, timeout=15)
cur  = conn.cursor()

# Discover RCLIE columns
cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='RCLIE' ORDER BY ORDINAL_POSITION")
cols_rclie = [r[0] for r in cur.fetchall()]
print(f"RCLIE columns: {cols_rclie}")

# Check CLRIESGOSIS existence
has_riesgosis = 'CLRIESGOSIS' in cols_rclie
print(f"CLRIESGOSIS column exists: {has_riesgosis}")

# MONTEZUMA base data
cur.execute("SELECT * FROM RCLIE WHERE CLCOD = '4127924112345393'")
row = cur.fetchone()
if row:
    col_vals = dict(zip([d[0] for d in cur.description], row))
    print(f"MONTEZUMA RCLIE keys with values: {[(k,v) for k,v in col_vals.items() if v and str(v).strip()]}")
else:
    print("MONTEZUMA RCLIE: NOT FOUND")

# OGCORREDOR obligations for MONTEZUMA
cur.execute("""
    SELECT o.OGCOD, o.OGCORREDOR, o.OGFECMOR, d.DEMORATOT
    FROM ROBLG o
    JOIN RDEUDA d ON d.DEOBLIG = o.OGCOD
    WHERE o.OGLOTE = '4127924112345393'
      AND o.OGCORREDOR IS NOT NULL
      AND LEN(RTRIM(o.OGCORREDOR)) > 0
    ORDER BY d.DEMORATOT DESC, o.OGFECMOR ASC
""")
rows = cur.fetchall()
print(f"MONTEZUMA OGCORREDOR obligations: {[(r[0], r[1], r[2], r[3]) for r in rows]}")

# Any client with CLRIESGOSIS populated (if column exists)
if has_riesgosis:
    cur.execute("""
        SELECT TOP 3 c.CLCOD, c.CLRIESGOSIS
        FROM RCLIE c
        WHERE c.CLRIESGOSIS IS NOT NULL AND LEN(RTRIM(c.CLRIESGOSIS)) > 0
        ORDER BY c.CLCOD
    """)
    rows3 = cur.fetchall()
    print(f"Clients with CLRIESGOSIS: {[(r[0], r[1]) for r in rows3]}")
else:
    print("CLRIESGOSIS column does NOT exist in RCLIE")

# Total lotes available
cur.execute("SELECT COUNT(*) FROM RLOTE")
total = cur.fetchone()[0]
print(f"Total lotes in RLOTE: {total}")

conn.close()
print("DB check OK")
