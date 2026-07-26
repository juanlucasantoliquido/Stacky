"""Find a client accessible to PABLO that has domicilios."""
import pyodbc

cn = pyodbc.connect(
    "Driver={SQL Server};Server=aisbddev02.cloud.ais-int.net;"
    "Database=RSPACIFICO;UID=RSPACIFICOREAD;PWD=RSPACIFICOREAD_ai$2007;"
)
cur = cn.cursor()

# Find clients assigned to PABLO with domicilios
query = """
SELECT TOP 5 d.DTCOD, d.DTCODDOM, d.DTCALLE, d.DTCIUDAD, d.DTVALIDO
FROM RDIRE d
WHERE d.DTVALIDO = '1'
AND EXISTS (
    SELECT 1 FROM ROBLG o
    WHERE o.OGCLCOD = d.DTCOD
    AND EXISTS (
        SELECT 1 FROM RCGST g
        WHERE g.GCUSUARIO = 'PABLO'
        AND g.GCCOD = o.OGCOD
    )
)
ORDER BY d.DTFECMODIF DESC
"""
try:
    cur.execute(query)
    rows = cur.fetchall()
    print("Clients with domicilios accessible to PABLO:")
    for r in rows:
        print(r)
except Exception as e:
    print("Query failed:", e)
    # Try simpler approach - get any active domicilios
    cur.execute("SELECT TOP 5 DTCOD, DTCODDOM, DTCALLE, DTCIUDAD FROM RDIRE WHERE DTVALIDO='1'")
    print("Fallback - any active domicilios:")
    for r in cur.fetchall():
        print(r)

# Also check what PABLO can access via obligations
query2 = """
SELECT TOP 5 o.OGCLCOD, o.OGCOD
FROM ROBLG o
WHERE EXISTS (
    SELECT 1 FROM RCGST g
    WHERE g.GCUSUARIO = 'PABLO' AND g.GCCOD = o.OGCOD
)
"""
try:
    cur.execute(query2)
    rows2 = cur.fetchall()
    print("\nObligations assigned to PABLO:")
    for r in rows2:
        print(r)
except Exception as e:
    print("Query2 failed:", e)

cn.close()
