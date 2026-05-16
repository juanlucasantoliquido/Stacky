"""Find clients accessible to PABLO that have active domicilios."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Check what columns RDIRE has
cur.execute("SELECT TOP 1 * FROM RDIRE")
cols = [d[0] for d in cur.description]
print("RDIRE columns:", cols)

# Check columns of relevant agenda/portfolio tables
cur.execute("SELECT TOP 1 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RCART%'")
t = cur.fetchone()
print("RCART table:", t)
cur.execute("SELECT TOP 1 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME IN ('RCART', 'RCARTEN', 'RAGDA', 'RAGEN', 'RCLIENT')")
for r in cur.fetchall():
    print("Table:", r[0])

# Try to get PABLO's portfolio table name
cur.execute("SELECT TOP 5 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'R%' ORDER BY TABLE_NAME")
for r in cur.fetchall():
    print("Table:", r[0])
    
cn.close()
