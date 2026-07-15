# 14 — Comparador de BD entre ambientes (DB Compare)

← [INDEX](INDEX.md) · hermanos: [04-api](04-api.md) · [06-servicios-daemons](06-servicios-daemons.md) · [08-configuracion-flags](08-configuracion-flags.md)

Serie 122-126: compara esquema y datos de parámetro entre dos ambientes (p.ej. DEV vs TEST), genera diff con
severidades, corridas persistentes y scripts de paridad/backup pareados. Tab del SPA `dbcompare`, visible solo si
el flag de backend está ON. [V: frontend/src/App.tsx:15,104-107; api/db_compare.py:1-6]

## Superficie API — `/api/db-compare` (blueprint `db_compare`) [V: api/db_compare.py:24,52-410]
| Ruta | Función | Plan |
|------|---------|------|
| GET `/health` | estado + flag | 122 [V: db_compare.py:52] |
| GET/POST/DELETE `/environments[...]` | alta/baja de ambientes (alias, conexión read-only) | 122 [V: db_compare.py:65-101] |
| POST/DELETE `/environments/<alias>/password` | password write-only (nunca sale en respuestas/logs) | 122 [V: db_compare.py:111-132; docstring:4-6] |
| POST `/environments/<alias>/test` | prueba de conexión | 122 [V: db_compare.py:141] |
| POST `/environments/<alias>/snapshot`, GET `/snapshots[...]` | snapshot de esquema | 122 [V: db_compare.py:150-170] |
| POST `/compare` | motor de diff (severidades) | 123 [V: db_compare.py:185] |
| GET `/runs[...]`, `/runs/<id>/export.md` | corridas persistentes + export | 123/124 [V: db_compare.py:205-233] |
| GET/POST `/runs/<id>/scripts[...]`, `/scripts.zip` | scripts de paridad/backup pareados | 125 [V: db_compare.py:260-327] |
| GET `/runs/<id>/data-candidates`, POST `/runs/<id>/data-diff` | paridad de DATOS de tablas parámetro (gate hija) | 126 [V: db_compare.py:372-410] |

## Gate y seguridad [V: api/db_compare.py:1-40]
- **Gate estricto**: todos los endpoints salvo `/health` devuelven 403 si `STACKY_DB_COMPARE_ENABLED` está OFF. [V: db_compare.py:27-30]
- La paridad de datos suma un gate hijo opt-in doble: `STACKY_DB_COMPARE_DATA_DIFF_ENABLED`. [V: db_compare.py:33-40]
- Password de conexión: entra SOLO por `POST …/password` (write-only), JAMÁS sale en respuestas ni logs; `<REDACTADO>`. [V: db_compare.py:4-6]
- SELECT-only: la paridad de datos valida `validate_select_only` (reusa `services/db_query`). [V: db_compare.py:22]

## Servicios [V: ls backend/services | grep dbcompare]
`dbcompare_registry` (ambientes), `dbcompare_snapshot`, `dbcompare_engine`+`dbcompare_diff` (motor/severidades),
`dbcompare_runs` (persistencia), `dbcompare_scripts` (scripts pareados), `dbcompare_data`+`dbcompare_sqlnames`+`dbcompare_sqlvalues` (paridad datos), `dbcompare_deps_preflight`. [V: services/dbcompare_*.py]

## Flags [V: config.py:103-116]
| Flag | Default | Controla |
|------|---------|----------|
| `STACKY_DB_COMPARE_ENABLED` | true | gate general del comparador |
| `STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC` | 10 | timeout de conexión |
| `STACKY_DB_COMPARE_DATA_DIFF_ENABLED` | true | gate hijo de paridad de datos |
| `STACKY_DB_COMPARE_DATA_MAX_ROWS` | 5000 | cota de filas comparadas |

## Límites
- Riesgo latente sin verificar en `dbcompare_diff.py` heredado del plan 123. [INF: MEMORY plan-125-status] → auditar antes de confiar en severidades.
