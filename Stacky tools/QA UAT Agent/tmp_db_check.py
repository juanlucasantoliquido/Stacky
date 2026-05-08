import os, pyodbc, sys
sys.stdout.reconfigure(encoding='utf-8')
u=os.environ['RS_QA_DB_USER']
pw=os.environ['RS_QA_DB_PASS']
cs=f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=aisbddev02.cloud.ais-int.net;DATABASE=RSPACIFICO;UID={u};PWD={pw};TrustServerCertificate=yes;'
cn=pyodbc.connect(cs,timeout=15); cur=cn.cursor()

cur.execute("SELECT COUNT(*) FROM RAGENDA WHERE UPUSUARIO='PACIFICO'")
print('RAGENDA PACIFICO:', cur.fetchone()[0])

cur.execute("SELECT TOP 5 UPUSUARIO, COUNT(*) as cnt FROM RAGENDA GROUP BY UPUSUARIO ORDER BY cnt DESC")
print('Top users in RAGENDA:')
for r in cur: print(f'  {r[0]}: {r[1]}')

cur.execute("SELECT TOP 5 LOCOD, LOEST FROM RLOTE ORDER BY LOCOD")
print('RLOTE sample:')
for r in cur: print(f'  {r[0]} LOEST={r[1]}')

cur.execute("SELECT TOP 5 o.OGLOTE, o.OGCORREDOR FROM ROBLG o WHERE o.OGCORREDOR IS NOT NULL AND LEN(RTRIM(o.OGCORREDOR)) > 0 ORDER BY o.OGLOTE")
rows = cur.fetchall()
print(f'ROBLG con OGCORREDOR: {len(rows)} rows')
for r in rows: print(f'  OGLOTE={r[0]} OGCORREDOR={r[1]}')

cur.execute("SELECT TOP 5 c.CLCOD, c.CLRIESGOSIS FROM RCLIE c WHERE c.CLRIESGOSIS IS NOT NULL AND LEN(RTRIM(c.CLRIESGOSIS)) > 0 ORDER BY c.CLCOD")
rows = cur.fetchall()
print(f'RCLIE con CLRIESGOSIS: {len(rows)} rows')
for r in rows: print(f'  CLCOD={r[0]} CLRIESGOSIS={r[1]}')

cn.close(); print('DB OK')
