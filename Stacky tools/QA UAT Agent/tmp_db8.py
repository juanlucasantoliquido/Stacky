"""Check if target client exists in search tables."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Check RCLIE columns
cur.execute("SELECT TOP 1 * FROM RCLIE")
cols = [d[0] for d in cur.description]
print("RCLIE columns:", cols[:10])

# Check if 1000326109092054 exists in RS_CLIE
cur.execute("SELECT TOP 1 CODCLIE FROM RS_CLIE WHERE CODCLIE='1000326109092054'")
r = cur.fetchone()
print("RS_CLIE for 1000326109092054:", r)

# Check RCLIE
cur.execute("SELECT TOP 1 * FROM RCLIE WHERE " + cols[0] + "='1000326109092054'")
r2 = cur.fetchone()
print("RCLIE for 1000326109092054:", r2)

# Also check 1000001118137685 
cur.execute("SELECT TOP 1 CODCLIE FROM RS_CLIE WHERE CODCLIE='1000001118137685'")
r3 = cur.fetchone()
print("RS_CLIE for 1000001118137685:", r3)

cn.close()
