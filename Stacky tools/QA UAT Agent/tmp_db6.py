"""Find PABLO portfolio via RS_CLIE_ASIG."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Get RS_CLIE_ASIG columns
cur.execute("SELECT TOP 1 * FROM RS_CLIE_ASIG")
cols = [d[0] for d in cur.description]
print("RS_CLIE_ASIG columns:", cols)

# Find PABLO clients
cur.execute("SELECT TOP 5 * FROM RS_CLIE_ASIG WHERE " + 
    [f"'{c}'" for c in cols if 'USU' in c or 'USER' in c.upper()][0] + " = 'PABLO'")
for r in cur.fetchall():
    print(r)

cn.close()
