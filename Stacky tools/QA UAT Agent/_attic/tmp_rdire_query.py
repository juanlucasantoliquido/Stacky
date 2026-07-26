import pyodbc
cn = pyodbc.connect(
    'Driver={SQL Server};'
    'Server=aisbddev02.cloud.ais-int.net;'
    'Database=RSPACIFICO;'
    'UID=RSPACIFICOREAD;'
    'PWD=RSPACIFICOREAD_ai$2007;'
)
cur = cn.cursor()
cur.execute(
    "SELECT TOP 5 DTCOD, DTCODDOM, DTTIPDOM, DTCALLE, DTCIUDAD, DTPROVINCIA, DTESTADO "
    "FROM RDIRE WHERE DTVALIDO='1' ORDER BY DTFECMODIF DESC"
)
for r in cur.fetchall():
    print(r)

# Also check catalog 42 (Provincias)
print("\n--- Catalogo 42 (Provincias) ---")
cur.execute("SELECT TBNUME, TBCODE, TBTEXT FROM RTABL WHERE TBNUME='42' ORDER BY TBCODE")
for r in cur.fetchall():
    print(r)
cn.close()
