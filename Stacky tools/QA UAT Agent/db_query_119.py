import os, sys, pyodbc
sys.stdout.reconfigure(encoding='utf-8')
user = os.environ.get('RS_QA_DB_USER', '')
pwd = os.environ.get('RS_QA_DB_PASS', '')
server = 'aisbddev02.cloud.ais-int.net'
cs = 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=' + server + ';DATABASE=RSPACIFICO;UID=' + user + ';PWD=' + pwd + ';TrustServerCertificate=yes;'
conn = pyodbc.connect(cs, timeout=15)
cur = conn.cursor()

cur.execute('SELECT TOP 5 LOCOD FROM RLOTE ORDER BY LOCOD')
print('RLOTE:', [r[0] for r in cur.fetchall()])

cur.execute("""
SELECT TOP 5 o.OGLOTE, o.OGCORREDOR 
FROM ROBLG o 
WHERE o.OGCORREDOR IS NOT NULL AND LEN(RTRIM(o.OGCORREDOR)) > 0
ORDER BY o.OGLOTE
""")
rows2 = cur.fetchall()
print('Lotes con OGCORREDOR:', [(r[0], r[1]) for r in rows2])

cur.execute("""
SELECT TOP 5 c.CLCOD, c.CLRIESGOENT
FROM RCLIE c
WHERE c.CLRIESGOENT IS NOT NULL AND LEN(RTRIM(c.CLRIESGOENT)) > 0
ORDER BY c.CLCOD
""")
rows3 = cur.fetchall()
print('Clientes con CLRIESGOENT:', [(r[0], r[1]) for r in rows3])

conn.close()
print('OK')