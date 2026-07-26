import pyodbc, os, sys

with open(r'N:\GIT\RS\RSPacifico\Tools\Stacky\.secrets\qa_db.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            os.environ[k.strip()] = v.strip()

u = os.environ['RS_QA_DB_USER']
p = os.environ['RS_QA_DB_PASS']
conn = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=aisbddev02.cloud.ais-int.net;DATABASE=RSPACIFICO;UID={u};PWD={p}', timeout=10)
cur = conn.cursor()

cur.execute("""
SELECT ICCONTROL, ICTEXTO FROM RCONTROLES
WHERE ICFORM='AgendaWeb.FORMAGENDA'
AND ICCONTROL IN ('GridAgendaUsu#CLNUMDOC','GridAgendaUsu#OGCORREDOR','GridAgendaUsu#OGDEBAUT',
                  'GridAgendaAut#CLNUMDOC','GridAgendaAut#OGCORREDOR','GridAgendaAut#OGDEBAUT')
ORDER BY ICCONTROL
""")
for r in cur.fetchall():
    print(f'{r[0]} => {r[1]!r}')

print('---IDIOMA---')
cur.execute("SELECT IDIDIOMA, IDTEXTO, IDDESCRIPCION FROM RIDIOMA WHERE IDTEXTO IN (9298, 9300, 9301) ORDER BY IDIDIOMA, IDTEXTO")
for r in cur.fetchall():
    print(f'IDIOMA={r[0]}  ID={r[1]}  TEXTO={r[2]!r}')

print('---PENDING_RECORDS---')
cur.execute("""
SELECT TOP 5 A.AGLOTE, C.CLNUMDOC, O.OGCORREDOR, O.OGTIENEDEBITOAUTO
FROM RAGEN A
JOIN RLOTE L ON L.LOCOD=A.AGLOTE
JOIN RCLIE C ON C.CLCOD=L.LOCOD
JOIN ROBLG O ON O.OGLOTE=L.LOCOD AND O.OGLIDER='1'
WHERE A.AGHECHO='P'
ORDER BY A.AGFECREC DESC
""")
for r in cur.fetchall():
    print(f'  LOTE={r[0]} RUC={r[1]!r} CORREDOR={r[2]!r} DEBITO={r[3]!r}')

print('---DIST---')
cur.execute("""
SELECT COUNT(1), SUM(CASE WHEN O.OGTIENEDEBITOAUTO='S' THEN 1 ELSE 0 END),
       SUM(CASE WHEN O.OGTIENEDEBITOAUTO IS NULL THEN 1 ELSE 0 END),
       SUM(CASE WHEN ISNULL(LTRIM(RTRIM(O.OGCORREDOR)),'')!='' THEN 1 ELSE 0 END)
FROM RAGEN A
JOIN RLOTE L ON L.LOCOD=A.AGLOTE
JOIN ROBLG O ON O.OGLOTE=L.LOCOD AND O.OGLIDER='1'
WHERE A.AGHECHO='P'
""")
r = cur.fetchone()
print(f'Total={r[0]} DebitoSi={r[1]} DebitoNull={r[2]} ConCorredor={r[3]}')
conn.close()
