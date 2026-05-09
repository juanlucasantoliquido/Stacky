import pyodbc

user = "RSPACIFICOREAD"
pwd  = "RSPACIFICOREAD_ai$2007"
server = "aisbddev02.cloud.ais-int.net"
db = "RSPACIFICO"

conn_str = (f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};'
            f'DATABASE={db};UID={user};PWD={pwd};Connection Timeout=15')
conn = pyodbc.connect(conn_str, timeout=15)
cur = conn.cursor()

# 1. MONTEZUMA raw OGCORREDOR
cur.execute("SELECT ob.OGCORREDOR, ob.OGCOD FROM ROBLG ob INNER JOIN ROBCL bcl ON bcl.OCOBLIG = ob.OGCOD WHERE bcl.OCRAIZ = '4127924112345393' AND ob.OGCORREDOR IS NOT NULL")
rows = cur.fetchall()
print(f"MONTEZUMA OGCORREDOR raw: {rows}")

# 2. MONTEZUMA CLRIESGOSIS
cur.execute("SELECT CLRIESGOSIS FROM RCLIE WHERE CLCOD='4127924112345393'")
print(f"MONTEZUMA CLRIESGOSIS: {cur.fetchall()}")

# 3. GetCorredorPrincipal SPs
cur.execute("SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES WHERE ROUTINE_NAME LIKE '%Corredor%'")
print(f"Procs with Corredor: {cur.fetchall()}")

# 4. Verify client 8868788139968904 exists in FrmBusqueda (GetPersonas chain)
cur.execute("SELECT TOP 1 c.CLCOD, c.CLNOMBRE, c.CLRIESGOSIS, ob.OGCORREDOR FROM RCLIE c INNER JOIN ROBCL bcl ON c.CLCOD = bcl.OCRAIZ INNER JOIN ROBLG ob ON bcl.OCOBLIG = ob.OGCOD WHERE c.CLCOD='8868788139968904'")
print(f"CLCOD_SIN_DATOS client: {cur.fetchall()}")

# 5. Verify GetConsolidado chain for 8868788139968904
cur.execute("SELECT TOP 1 ob.OGCOD, ob.OGCORREDOR FROM RCLIE c INNER JOIN ROBCL bcl ON c.CLCOD = bcl.OCRAIZ INNER JOIN ROBLG ob ON bcl.OCOBLIG = ob.OGCOD INNER JOIN RLOTE lo ON ob.OGLOTE = lo.LOCOD INNER JOIN RDEUDA de ON ob.OGCOD = de.DEOBLIG WHERE c.CLCOD='8868788139968904'")
print(f"GetConsolidado chain for SIN_DATOS: {cur.fetchall()}")

conn.close()
