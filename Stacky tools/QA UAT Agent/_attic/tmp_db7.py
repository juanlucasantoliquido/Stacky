"""Find PABLO accessible clients using various approaches."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Look at FrmBusqueda's search - it probably uses RUSUA (user assignments) or similar
# Try the main client table
cur.execute("SELECT TOP 5 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RCLIEN%' OR TABLE_NAME LIKE 'RCLIE%'")
for r in cur.fetchall(): print("Table:", r[0])

# Check RUSUA or similar user assignment
cur.execute("SELECT TOP 5 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RUSUA%' OR TABLE_NAME LIKE 'RUSU%'")
for r in cur.fetchall(): print("Table:", r[0])

# Try RCODIGESTOR
cur.execute("SELECT TOP 5 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'RGEST%' OR TABLE_NAME LIKE 'RCOD%'")
for r in cur.fetchall(): print("Table:", r[0])

# Check what FrmBusqueda actually searches by looking at RSCLIE tables 
cur.execute("SELECT TOP 1 * FROM RS_CLIE")
cols = [d[0] for d in cur.description]
print("RS_CLIE columns:", cols[:20])

# Get top clients in RS_CLIE
cur.execute("SELECT TOP 5 * FROM RS_CLIE")
for r in cur.fetchall(): print("RS_CLIE:", r[:5])

cn.close()
