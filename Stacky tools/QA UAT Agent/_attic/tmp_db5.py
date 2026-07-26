"""Find PABLO portfolio via RCARTERA."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Get RCARTERA columns
cur.execute("SELECT TOP 1 * FROM RCARTERA")
cols = [d[0] for d in cur.description]
print("RCARTERA columns:", cols)

# Try to search FrmBusqueda's logic - find what table it queries
# Check if there's a view that powers the search
cur.execute("SELECT TOP 5 TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME LIKE '%BUSQ%' OR TABLE_NAME LIKE '%CLIE%'")
for r in cur.fetchall():
    print("View:", r[0])

cn.close()
