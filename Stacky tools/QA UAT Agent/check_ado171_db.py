import pyodbc

cn = pyodbc.connect(
    'Driver={SQL Server};'
    'Server=aisbddev02.cloud.ais-int.net;'
    'Database=RSPACIFICO;'
    'UID=RSPACIFICOREAD;'
    'PWD=RSPACIFICOREAD_ai$2007;'
)
cur = cn.cursor()

print('=== P01: INFORMATION_SCHEMA.COLUMNS EMOFICIAL en RMAILS ===')
cur.execute(
    "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE "
    "FROM INFORMATION_SCHEMA.COLUMNS "
    "WHERE TABLE_NAME='RMAILS' AND COLUMN_NAME='EMOFICIAL'"
)
rows = cur.fetchall()
print(f'Filas encontradas: {len(rows)}')
for r in rows:
    print(r)

print()
print('=== P09: COUNT NULLs y total RMAILS ===')
try:
    cur.execute('SELECT COUNT(*) FROM RMAILS WHERE EMOFICIAL IS NULL')
    print('NULLs en EMOFICIAL:', cur.fetchone()[0])
    cur.execute('SELECT COUNT(*) FROM RMAILS')
    print('Total registros RMAILS:', cur.fetchone()[0])
except Exception as e:
    print('ERROR (columna puede no existir):', e)

print()
print('=== Emails del cliente de prueba EMCOD=1000001118137685 ===')
try:
    cur.execute(
        "SELECT EMCOD, EMCODMAIL, EMTIPO, EMMAIL, EMVALIDO "
        "FROM RMAILS WHERE EMCOD='1000001118137685' ORDER BY EMCODMAIL"
    )
    rows = cur.fetchall()
    print(f'Emails encontrados: {len(rows)}')
    for r in rows:
        print(r)
except Exception as e:
    print('ERROR al consultar emails:', e)

print()
print('=== EMOFICIAL values sample (top 10) ===')
try:
    cur.execute(
        "SELECT TOP 10 EMCOD, EMCODMAIL, EMVALIDO, EMOFICIAL "
        "FROM RMAILS WHERE EMOFICIAL IS NOT NULL ORDER BY EMFECMODIF DESC"
    )
    rows = cur.fetchall()
    for r in rows:
        print(r)
except Exception as e:
    print('ERROR (columna no existe o sin datos):', e)

cn.close()
print()
print('Done.')
