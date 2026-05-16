"""Find if PABLO can access client 1000326109092054 and find alternative with domicilios."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Check if the client exists at all
cur.execute("SELECT TOP 1 * FROM RDIRE WHERE DTCOD='1000326109092054'")
r = cur.fetchone()
print("RDIRE for 1000326109092054:", r)

# Check client 1000001118137685 domicilios with provincia
cur.execute("SELECT DTCOD, DTCODDOM, DTCALLE, DTPROVINCIA, DTVALIDO FROM RDIRE WHERE DTCOD='1000001118137685'")
for r in cur.fetchall():
    print("Domicilio:", r)

# Check RAGEN - the portfolio/cartera table
cur.execute("SELECT TOP 1 * FROM RAGEN")
cols = [d[0] for d in cur.description]
print("\nRAGEN columns:", cols[:15])

# Find client accessible to PABLO with domicilios
cur.execute("""
SELECT TOP 5 g.GNCLCOD 
FROM RAGEN g
WHERE g.GNUSUARIO = 'PABLO'
AND EXISTS (SELECT 1 FROM RDIRE d WHERE d.DTCOD = g.GNCLCOD AND d.DTVALIDO='1')
""")
rows = cur.fetchall()
print("\nPABLO clients with domicilios:")
for r in rows:
    print(r[0])

cn.close()
