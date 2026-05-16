"""Find PABLO's portfolio - correct column names."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Get RAGEN columns
cur.execute("SELECT TOP 1 * FROM RAGEN")
cols = [d[0] for d in cur.description]
print("RAGEN columns:", cols)

# Search for tables with PABLO as user
cur.execute("SELECT TOP 5 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RCART%'")
for r in cur.fetchall():
    print("Table:", r[0])

# Try RACTUSU
cur.execute("SELECT TOP 1 * FROM RACTUSU")
cols2 = [d[0] for d in cur.description]
print("RACTUSU columns:", cols2)

cn.close()
