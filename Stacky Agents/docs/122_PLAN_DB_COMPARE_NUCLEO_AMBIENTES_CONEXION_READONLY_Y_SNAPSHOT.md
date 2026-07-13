# Plan 122 — Comparador de BD entre ambientes (serie 122–126, parte 1/5): núcleo de ambientes, conexión read-only real y snapshot de esquema

**Estado:** PROPUESTO (v1.1, 2026-07-12 — integra prior art de campo: scripts RSPACIFICO del operador, ver §2-bis)
**Serie:** 122 (núcleo) → 123 (motor de diff) → 124 (UI inmersiva) → 125 (scripts de paridad + backups) → 126 (paridad de datos)
**Dependencias:** ninguna (abre la serie). Reusa el patrón de registro con keyring del Plan 91 (`services/server_registry.py`) y el sustrato de validación SELECT-only de `services/db_query.py`.
**Ortogonal a:** Plan 116 (doctor conexiones DevOps), Plan 119 (rediseño dashboard DevOps), Plan 120 (Centro de Despliegues), Plan 121 (centinela de egreso).

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-12 sobre el working tree (rama `main`,
> HEAD `427f2df5`). Prohibido desviarse de los nombres exactos.

---

## 1. Objetivo + KPI

El operador administra el MISMO producto RS en varios ambientes (desarrollo / testing /
producción) y hoy no tiene forma de saber, sin trabajo manual, en qué difieren las bases
entre ambientes. La serie 122–126 construye la sección **"Comparador de BD"**: una vista
inmersiva que compara el esquema (y luego los datos de tablas de parámetros) entre dos
ambientes, muestra un resumen detallado y genera scripts de paridad **junto con scripts
de backup pareados 1:1** de cada tabla que se vaya a pisar o modificar. Stacky **genera,
nunca ejecuta**: human-in-the-loop innegociable.

Este plan (1/5) entrega el cimiento sin el cual nada del resto existe:

1. **Registro de ambientes de BD** con alias + credencial en keyring (patrón Plan 91).
2. **Conexión real read-only** vía SQLAlchemy (ya es dependencia, `backend/requirements.txt:3`)
   con drivers opcionales lazy: `pyodbc` (SQL Server / Pacífico) y `oracledb` thin
   (Oracle / Ripley). Hoy `services/db_query.py:310` es un stub que NO conecta
   ("Stub fase 1 … NO se ejecutó contra la BD") y su propio docstring anticipa este paso
   (`services/db_query.py:272-274`: "Cuando se enchufe el driver real (sqlalchemy/pyodbc…)").
3. **Snapshot canónico de esquema** (tablas, columnas, PK, FKs, índices, uniques, checks,
   vistas, secuencias) determinista, persistido y hasheado — el insumo del diff (Plan 123).
4. **Tab nueva "Comparador BD"** en la UI, gateada por flag master default OFF, con la
   gestión de ambientes 100% desde la UI (regla de la casa: config del operador vía UI).

**KPIs (binarios):**

- **KPI-1:** con la flag ON, `POST /api/db-compare/environments` + password + test contra
  una BD accesible devuelve `{"ok": true}` con versión del motor y latencia (test F4 con
  SQLite; en vivo con SQL Server/Oracle reales).
- **KPI-2:** `take_snapshot()` sobre la misma BD dos veces seguidas (sin cambios) produce
  el MISMO `content_hash` (determinismo, test F3).
- **KPI-3:** con la flag OFF (default), NADA cambia: ni tab visible, ni endpoints activos
  (403), ni imports de drivers ejecutados (test F4 + F5).

## 2. Por qué ahora / gap que cierra

- El stub `services/db_query.py:256-347` valida y audita SELECTs pero **no conecta**
  (`would_execute=True`), y guarda UNA credencial por proyecto
  (`_resolve_db_readonly`, `services/db_query.py:194-222`, `auth/db_readonly.json` DPAPI).
  Para comparar ambientes hacen falta **N conexiones nombradas** (dev/test/prod), que ese
  mecanismo no modela.
- Ya existen todas las piezas para no reinventar: `keyring==25.6.0`
  (`backend/requirements.txt:11`) con patrón probado en `services/server_registry.py:28`
  (`KEYRING_SERVICE = "stacky-devops"`), `SQLAlchemy==2.0.36` (`backend/requirements.txt:3`),
  validadores `validate_alias`/`validate_host` (`services/server_registry.py:47,51`),
  persistencia JSON en `data_dir()` (`services/db_query.py:161-162`).
- La revisión E2E DevOps y los planes 87–120 cubrieron pipelines, servidores y deploys;
  la BASE DE DATOS — donde vive la paridad real del producto RS — quedó sin cobertura.
  Este es el gap de mayor valor operativo que queda abierto.

## 2-bis. Prior art operativo (obligatorio leer antes de implementar la serie)

El operador ya corrió a mano este flujo completo el 2026-07-12 en el repo RSPACIFICO;
esos scripts son la referencia de campo VALIDADA de la serie (leerlos antes de codear):

- `N:\GIT\RS\RSPACIFICO\pipelines\scripts\Compare-DevTestDatabase.ps1` — snapshot dual
  (DEV on-prem + TEST Azure SQL Managed Instance SIN conectividad entre sí → compara
  snapshots en memoria, misma arquitectura de esta serie), estructura completa por
  INFORMATION_SCHEMA/sys.* + datos de RCONTROLES/RMODULOS/RIDIOMA por PK real.
- `N:\GIT\RS\RSPACIFICO\pipelines\scripts\Backup-TestTables.ps1` — backup aditivo
  `SELECT * INTO dbo.<t>_BAK_<ts>` con verificación de COUNT(*) origen=backup y manifest.
- `N:\GIT\RS\RSPACIFICO\pipelines\scripts\Invoke-DevTestParityReplay.ps1` — orquestador
  del replay con paso 0 = backup (aborta TODO si un backup no verifica), gates read-only
  antes de ALTERs riesgosos, e idempotencia por ítem.

Doctrina extraída (se cablea en los planes 123/125/126, ya incorporada en sus v1.1):
constraints/índices se matchean por FIRMA ESTRUCTURAL y no por nombre (los nombres
autogenerados difieren entre BDs → falsos positivos); backups con verificación de counts
embebida; INSERTs de datos idempotentes con guarda por fila.

Contexto de ambientes reales (para el registro del operador, NO hardcodear en código):
DEV `aisbddev02.cloud.ais-int.net` (credencial canónica en `trunk\Batch\XMLConfig.xml`
del repo RSPACIFICO); TEST `sqlmi-rspacifbra-test...database.windows.net` (endpoint
PRIVADO de Azure: un timeout casi siempre es VPN/VNet ausente, no credencial mala).

## 3. Principios y guardarraíles

1. **Read-only por construcción (4 capas):**
   a. Stacky solo emite reflection de catálogo del Inspector de SQLAlchemy y probes `SELECT 1`;
   b. no existe NINGÚN endpoint que ejecute DDL/DML contra una BD registrada;
   c. la UI recomienda registrar credenciales de solo-lectura (texto fijo en el form);
   d. los planes 125/126 GENERAN scripts como artefactos; ejecutarlos es siempre del operador.
2. **Drivers opcionales y lazy:** sin `pyodbc`/`oracledb` instalados, Stacky arranca y
   funciona igual; el health del comparador reporta qué driver falta y el comando exacto
   para instalarlo. Ningún `import pyodbc`/`import oracledb` a nivel módulo.
3. **Flags por UI, default OFF:** master `STACKY_DB_COMPARE_ENABLED` en la categoría
   `capacidades_optin` (regla de la casa para masters opt-in, ver nota en
   `services/harness_flags.py:180`), knobs en categoría nueva `comparador_bd`.
   **Gotcha obligatorio:** NO pasar `default=False` explícito en `FlagSpec` nuevas
   (`default: object | None = None` = type-zero, `services/harness_flags.py:29`); pasar
   `default=False` rompe `test_default_known_only_for_curated` (aprendizaje Plan 63).
4. **Mono-operador, sin auth nueva; cero trabajo extra:** todo es opt-in con default OFF;
   sin pasos manuales obligatorios; backward-compatible al 100%.
5. **Paridad de 3 runtimes (Codex CLI / Claude Code CLI / Copilot Pro):** esta serie es
   una feature de PANEL (backend Flask + React) servida por el backend; no toca los
   runtimes de agentes ni depende de cuál esté activo. Impacto por runtime: idéntico
   (N/A activo) — se declara por fase igualmente.
6. **Mismo motor entre ambientes:** se comparan ambientes del MISMO engine
   (sqlserver↔sqlserver, oracle↔oracle). Comparación cross-engine queda fuera de scope
   de toda la serie (sin valor para paridad de ambientes y llena de falsos positivos).

## 4. Fases

### F0 — Flags del arnés + config

**Objetivo:** declarar las flags del núcleo, visibles y editables desde la UI de flags, default OFF.

**Archivos a editar:**
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/config.py`

**Cambios exactos:**

1. En `FLAG_CATEGORIES` (`services/harness_flags.py:53`), agregar al final de la tupla:
```python
CategorySpec("comparador_bd", "Comparador de BD entre ambientes",
    "Serie 122-126 — comparación de esquema/datos entre ambientes, snapshots, scripts de paridad y backups.",
    tier="simple", intent="Comparar bases entre ambientes y generar scripts de paridad"),
```
2. Declarar 2 `FlagSpec` nuevas (mismo estilo que `services/harness_flags.py:782-784`),
   SIN `default=` en la bool (gotcha §3.3):
```python
FlagSpec(
    key="STACKY_DB_COMPARE_ENABLED",
    type="bool",
    label="Comparador de BD entre ambientes",
    description="Master del comparador (serie 122-126): tab UI, registro de ambientes, snapshots y comparaciones. OFF = invisible.",
    group="global",
),
FlagSpec(
    key="STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",
    type="int",
    label="Comparador BD: timeout de conexión (seg)",
    description="Timeout de login/TCP al abrir conexión read-only a un ambiente registrado.",
    group="global",
    default=10,
    requires="STACKY_DB_COMPARE_ENABLED",
    min_value=1,
    max_value=120,
),
```
3. En el mapa categoría→keys (dict cuyo literal `"base_datos": (` está en
   `services/harness_flags.py:251`): agregar `"STACKY_DB_COMPARE_ENABLED"` a la tupla de
   `"capacidades_optin"` y crear la entrada `"comparador_bd": ("STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",)`.
4. En `config.py`, junto a los otros getters (idiomas de referencia: bool
   `config.py:964-965`, int `config.py:591-592`):
```python
STACKY_DB_COMPARE_ENABLED: bool = os.getenv("STACKY_DB_COMPARE_ENABLED", "false")\
    .strip().lower() in ("1", "true", "yes", "on")   # ← copiar el idioma EXACTO del bool de config.py:964
STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC: int = int(os.getenv("STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC", "10"))
```
   (Si el idioma bool real de `config.py:964` difiere del pseudocódigo, copiar el real.)

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan122_dbcompare_flags.py`
- `test_master_flag_declared_default_off` — la spec existe, `type=="bool"`, y
  `Config.STACKY_DB_COMPARE_ENABLED is False` sin env var.
- `test_timeout_flag_bounds` — spec int con `min_value==1`, `max_value==120`, `requires=="STACKY_DB_COMPARE_ENABLED"`, `default==10`.
- `test_category_comparador_bd_exists` — `"comparador_bd"` está en `FLAG_CATEGORIES` y el mapa
  categoría→keys contiene la key del timeout; el master está en `"capacidades_optin"`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_flags.py tests/test_harness_flags.py -q`

**Criterio binario:** ambos archivos de test en verde y `tests/test_harness_flags.py` (suite
preexistente de flags) sin regresión.

**Flag:** las declaradas acá. **Runtimes:** N/A (panel). **Trabajo del operador:** ninguno (todo OFF).

### F1 — Registro de ambientes: `services/dbcompare_registry.py`

**Objetivo:** CRUD de ambientes de BD con password EXCLUSIVAMENTE en keyring, espejo del patrón Plan 91.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_registry.py`

**Símbolos exactos (firma y contrato):**
```python
KEYRING_SERVICE_DBCOMPARE = "stacky-dbcompare"
_REGISTRY_FILENAME = "db_compare/environments.json"   # bajo runtime_paths.data_dir()
ENGINES = ("sqlserver", "oracle")                      # sqlite se acepta SOLO si alias empieza con "test-" (para tests/demo)

def keyring_available() -> bool            # idéntico contrato a services/server_registry.py:43
def list_environments() -> list[dict]      # cada dict pasado por _public() (SIN password)
def get_environment(alias: str) -> dict | None
def upsert_environment(alias, engine, host, port, database, username,
                       odbc_driver="ODBC Driver 17 for SQL Server",
                       schema_filter=None, notes="") -> dict
def delete_environment(alias: str) -> bool  # borra registro + keyring.delete_password best-effort
def set_password(alias: str, password: str) -> None
def clear_password(alias: str) -> None
def has_password(alias: str) -> bool
def get_credential(alias: str) -> dict | None   # {**env, "password": str} SOLO para uso interno del engine; None si falta
def touch_last_used(alias: str) -> None
```

**Reglas:**
- Validación: REUSAR `validate_alias` y `validate_host` importándolos de
  `services.server_registry` (`services/server_registry.py:47,51`). Alias inválido o
  host inválido → `ValueError` con mensaje en español.
- `engine` debe estar en `ENGINES` (o `"sqlite"` si `alias.startswith("test-")`); si no → `ValueError`.
- `port`: int en [1, 65535]; defaults sugeridos por engine en la UI (sqlserver 1433, oracle 1521), NO en el backend.
- `schema_filter`: lista de schemas a incluir (strings); `None`/`[]` = default del motor
  (lo resuelve F3). Persistir tal cual.
- Registro JSON: lista de dicts con keys `alias, engine, host, port, database, username,
  odbc_driver, schema_filter, notes, created_at, last_used_at` (timestamps ISO UTC con
  sufijo `Z`, mismo formato que `services/db_query.py:177`).
- `_public(env)` devuelve el dict SIN password y agrega `"has_password": has_password(alias)`.
- El password NUNCA se escribe al JSON ni a logs (regla dura heredada de Plan 91 C1).

**Tests PRIMERO:** `tests/test_plan122_dbcompare_registry.py`
- Fixture `fake_keyring` (monkeypatch de `keyring.set_password/get_password/delete_password`
  sobre un dict en memoria) — mismo enfoque que los tests del Plan 91.
- `test_upsert_and_list_public_sin_password`
- `test_engine_invalido_rechaza` / `test_alias_invalido_rechaza`
- `test_password_roundtrip_y_clear` (set → has → get_credential trae password → clear → None)
- `test_delete_borra_registro_y_password`
- `test_sqlite_solo_para_alias_test`

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_registry.py -q`

**Criterio binario:** todos verdes; `grep -n "password" data/db_compare/environments.json` de un
registro de prueba no encuentra nada (el test lo asegura leyendo el archivo).

**Flag:** ninguna (módulo puro; el gate es del API F4). **Runtimes:** N/A. **Operador:** ninguno.

### F2 — Motor de conexión read-only: `services/dbcompare_engine.py`

**Objetivo:** abrir engines SQLAlchemy read-only por alias con drivers lazy y test de conexión accionable.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_engine.py`

**Símbolos exactos:**
```python
class DbCompareEngineError(RuntimeError): ...

_PROBE_SQL = {"sqlserver": "SELECT 1", "oracle": "SELECT 1 FROM DUAL", "sqlite": "SELECT 1"}

def driver_status() -> dict
    # {"sqlserver": {"module": "pyodbc",   "available": bool, "install_hint": "cd \"Stacky Agents/backend\" && .venv\\Scripts\\pip install pyodbc"},
    #  "oracle":    {"module": "oracledb", "available": bool, "install_hint": "cd \"Stacky Agents/backend\" && .venv\\Scripts\\pip install oracledb"}}
    # available via importlib.util.find_spec(module) is not None — SIN importar el módulo.

def build_sqlalchemy_url(env: dict, password: str) -> "sqlalchemy.engine.URL"
    # sqlserver: URL.create("mssql+pyodbc", username=env["username"], password=password,
    #            host=env["host"], port=env["port"], database=env["database"],
    #            query={"driver": env["odbc_driver"], "TrustServerCertificate": "yes"})
    # oracle:    URL.create("oracle+oracledb", username=..., password=..., host=..., port=...,
    #            query={"service_name": env["database"]})
    # sqlite:    URL.create("sqlite", database=env["database"])   # database = ruta del archivo
    # URL.create escapa password con caracteres especiales (por eso NO se arma string a mano).

def open_engine(alias: str, *, timeout_sec: int | None = None) -> "sqlalchemy.engine.Engine"
    # 1) env = dbcompare_registry.get_credential(alias); si None → DbCompareEngineError("credencial faltante: …")
    # 2) chequear driver_status() del engine; si no disponible → DbCompareEngineError con install_hint
    # 3) timeout = timeout_sec or Config.STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
    #    connect_args: sqlserver {"timeout": timeout} | oracle {"tcp_connect_timeout": timeout} | sqlite {}
    # 4) create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0, future=True, connect_args=...)
    # 5) touch_last_used(alias); return engine  (el caller hace engine.dispose() en finally)

def test_connection(alias: str) -> dict
    # abre engine, ejecuta _PROBE_SQL del dialecto, mide latencia:
    # ok → {"ok": True, "engine": env["engine"], "server_version": str(eng.dialect.server_version_info or ""), "latency_ms": int}
    # error → {"ok": False, "error": <mensaje SIN password>, "install_hint": <si aplica>,
    #          "likely_network": bool}
    # likely_network (doctrina Compare-DevTestDatabase.ps1: LikelyNetworkIssue): True si el
    # mensaje matchea re.search(r"timeout|network-related|could not be found|no such host|actively refused|unreachable", msg, re.I)
    # → la UI muestra "Probable problema de red/VPN (el TEST real es un endpoint privado de Azure), no necesariamente credencial incorrecta."
    # Scrub: si str(exc) contiene el password, reemplazarlo por "***" antes de devolver.
```

**Reglas:**
- Ningún import de `pyodbc`/`oracledb` a nivel módulo (los importa SQLAlchemy al conectar).
- `test_connection` NUNCA lanza: siempre devuelve dict con `ok`.
- Toda conexión se cierra en `finally` (`engine.dispose()`).

**Tests PRIMERO:** `tests/test_plan122_dbcompare_engine.py`
- `test_build_url_sqlserver_exacta` / `test_build_url_oracle_exacta` — comparar
  `str(url)` (SQLAlchemy enmascara password en repr: usar `url.render_as_string(hide_password=False)`).
- `test_driver_status_reporta_hint` — monkeypatch `importlib.util.find_spec` → None y validar hint exacto.
- `test_open_engine_sin_credencial_error_claro`
- `test_test_connection_sqlite_ok` — ambiente `test-sqlite` apuntando a un archivo sqlite tmp
  creado por el test: `ok==True`, `latency_ms >= 0`.
- `test_error_no_filtra_password` — forzar excepción cuyo texto contiene el password → respuesta lo enmascara.
- `test_likely_network_clasifica` — mensajes "Timeout expired" y "network-related" → `likely_network=True`; "Login failed" → `False`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_engine.py -q`

**Criterio binario:** todos verdes SIN pyodbc/oracledb instalados (CI-safe: sqlite + mocks).

**Flag:** consume `STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC`. **Runtimes:** N/A. **Operador:** ninguno.

### F3 — Snapshot canónico de esquema: `services/dbcompare_snapshot.py`

**Objetivo:** producir y persistir un snapshot determinista, hasheable y comparable del esquema de un ambiente.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_snapshot.py`

**Símbolos exactos:**
```python
SNAPSHOT_VERSION = 1
_SNAPSHOTS_DIRNAME = "db_compare/snapshots"     # data_dir()/db_compare/snapshots/<alias>/<snapshot_id>.json
_MAX_SNAPSHOTS_PER_ALIAS = 20                   # prune FIFO por fecha
_VIEW_DEF_MAX_CHARS = 100_000

def default_schemas(engine_kind: str, username: str) -> list[str]
    # sqlserver → ["dbo"] ; oracle → [username.upper()] ; sqlite → ["main"]

def take_snapshot(alias: str, *, engine=None) -> dict
    # engine inyectable SOLO para tests (sqlite). Si None → dbcompare_engine.open_engine(alias).
    # insp = sqlalchemy.inspect(engine)
    # schemas = env["schema_filter"] or default_schemas(...)
    # por schema: insp.get_table_names(schema=s) y por tabla:
    #   columns: insp.get_columns → [{"name", "type": str(col["type"]).upper(), "nullable": bool,
    #             "default": (str|None), "autoincrement": bool(col.get("autoincrement") or False)}]  (orden ordinal tal cual llega)
    #   primary_key: insp.get_pk_constraint → {"name": str|None, "columns": [...]}
    #   foreign_keys: insp.get_foreign_keys → [{"name","columns","referred_schema","referred_table","referred_columns"}] ordenadas por (name or "")
    #   indexes: insp.get_indexes → [{"name","columns","unique": bool}] ordenadas por name
    #   unique_constraints: insp.get_unique_constraints → [{"name","columns"}] ordenadas por name
    #   check_constraints: insp.get_check_constraints → [{"name","sqltext": str}] ordenadas por name (try/except NotImplementedError → [])
    # views: insp.get_view_names(schema=s); por vista get_view_definition (try/except → None):
    #   {"definition": texto[: _VIEW_DEF_MAX_CHARS] | None, "definition_sha256": sha256(texto) | None, "error": str|None}
    # sequences: insp.get_sequence_names(schema=s) dentro de try/except NotImplementedError → []
    # counts: {"tables": n, "views": n, "sequences": n, "columns": n_total}
    # content_hash = sha256(json.dumps(cuerpo_sin_metadatos, sort_keys=True, ensure_ascii=False))
    #   donde cuerpo_sin_metadatos EXCLUYE: id, taken_at, duration_ms (para que 2 tomas idénticas hasheen igual).
    # persistir y devolver el dict completo.

def list_snapshots(alias: str) -> list[dict]    # metadatos: id, taken_at, duration_ms, counts, content_hash (SIN schemas)
def load_snapshot(snapshot_id: str) -> dict | None
def latest_snapshot(alias: str) -> dict | None
def prune_snapshots(alias: str) -> int          # borra los más viejos que excedan _MAX_SNAPSHOTS_PER_ALIAS; retorna borrados
```

**Estructura EXACTA del snapshot (contrato v1, congelado para la serie):**
```json
{
  "version": 1,
  "id": "<alias>_<yyyymmddTHHMMSSZ>",
  "alias": "...", "engine": "sqlserver|oracle|sqlite",
  "taken_at": "2026-07-12T14:00:00Z", "duration_ms": 1234,
  "schemas": {
    "<schema>": {
      "tables": { "<tabla>": { "columns": [...], "primary_key": {...}, "foreign_keys": [...],
                    "indexes": [...], "unique_constraints": [...], "check_constraints": [...] } },
      "views": { "<vista>": { "definition": "...|null", "definition_sha256": "...|null", "error": null } },
      "sequences": ["..."]
    }
  },
  "counts": { "tables": 0, "views": 0, "sequences": 0, "columns": 0 },
  "content_hash": "<sha256 hex>"
}
```

**Tests PRIMERO:** `tests/test_plan122_dbcompare_snapshot.py`
- Fixture sqlite real en tmp_path con DDL:
  `CREATE TABLE padre (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL);`
  `CREATE TABLE hija (id INTEGER PRIMARY KEY, padre_id INTEGER REFERENCES padre(id), valor REAL DEFAULT 0);`
  `CREATE INDEX ix_hija_padre ON hija(padre_id);`
  `CREATE VIEW v_padre AS SELECT id, nombre FROM padre;`
- `test_snapshot_estructura_v1` — keys exactas del contrato, counts correctos (2 tablas, 1 vista).
- `test_snapshot_determinista` — dos tomas sobre la misma BD → mismo `content_hash`, distinto `id`.
- `test_snapshot_detecta_cambio` — `ALTER TABLE padre ADD COLUMN extra TEXT` → `content_hash` distinto.
- `test_prune_mantiene_max` — crear 22 snapshots → `prune` deja 20 (los más nuevos).
- `test_view_definition_error_no_rompe` — monkeypatch `get_view_definition` que lanza → vista con `error` y snapshot ok.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_snapshot.py -q`

**Criterio binario:** todos verdes con sqlite puro (sin drivers externos ni red).

**Flag:** ninguna directa (gate en API). **Runtimes:** N/A. **Operador:** ninguno.

### F4 — API: `api/db_compare.py` + registro del blueprint

**Objetivo:** exponer el núcleo por HTTP con gate estricto de flag.

**Archivos:** crear `Stacky Agents/backend/api/db_compare.py`; editar `Stacky Agents/backend/api/__init__.py`.

**Blueprint (mismo patrón que `api/db_query.py:34` y `api/__init__.py:96-110`):**
```python
bp = Blueprint("db_compare", __name__, url_prefix="/db-compare")
```
Registro en `api/__init__.py`: `from .db_compare import bp as db_compare_bp  # Plan 122 — comparador de BD`
junto a los imports (~línea 55) y `api_bp.register_blueprint(db_compare_bp)  # Plan 122 — url_prefix="/db-compare" → /api/db-compare/...`
junto a los registers (~línea 110).

**Gate:** helper module-level
```python
def _require_enabled():
    from config import Config
    if not Config.STACKY_DB_COMPARE_ENABLED:
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    return None
```
Todos los endpoints EXCEPTO `/health` empiezan con `gate = _require_enabled();` / `if gate: return gate`.

**Endpoints exactos:**
| Método y ruta (bajo `/api/db-compare`) | Comportamiento |
|---|---|
| `GET /health` | SIEMPRE 200: `{ok: true, flag_enabled: bool, keyring_available: bool, drivers: driver_status()}` (espejo de `/api/devops/health` que consume App.tsx:91-94) |
| `GET /environments` | `{ok, environments: [_public...], keyring_available}` |
| `POST /environments` | body `{alias, engine, host, port, database, username, odbc_driver?, schema_filter?, notes?}` → upsert; `ValueError` → 400 `{ok:false, error}` |
| `DELETE /environments/<alias>` | 200 `{ok}` / 404 |
| `POST /environments/<alias>/password` | body `{password}`; keyring no disponible → 503 con mensaje (patrón `api/devops_servers.py:35-40`) |
| `DELETE /environments/<alias>/password` | clear |
| `POST /environments/<alias>/test` | `test_connection(alias)`; ok→200, error→200 con `{ok:false,...}` (el error de conexión es dato, no fallo HTTP) |
| `POST /environments/<alias>/snapshot` | `take_snapshot(alias)` SÍNCRONO → 200 metadatos (id, counts, content_hash, duration_ms). Limitación documentada: para BDs grandes la corrida threaded llega en Plan 123 y es el camino que usará la UI 124. |
| `GET /environments/<alias>/snapshots` | `list_snapshots` |
| `GET /snapshots/<snapshot_id>` | `load_snapshot` completo / 404 |

**Tests PRIMERO:** `tests/test_plan122_dbcompare_api.py` (Flask test client, patrón de los tests API existentes)
- `test_flag_off_todos_403_salvo_health`
- `test_health_reporta_drivers_y_flag`
- `test_crud_ambiente_roundtrip` (flag ON vía monkeypatch de Config + fake_keyring)
- `test_snapshot_endpoint_sqlite`
- `test_password_endpoint_sin_keyring_503`

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_api.py -q`

**Criterio binario:** todos verdes; con flag OFF ningún endpoint (salvo health) responde 200.

**Flag:** `STACKY_DB_COMPARE_ENABLED` (gate). **Runtimes:** N/A. **Operador:** ninguno.

### F5 — UI mínima: tab "Comparador BD" + gestión de ambientes

**Objetivo:** tab nueva gateada + panel de ambientes 100% operable desde la UI (alta, password, test, snapshot manual). La inmersión visual completa llega en Plan 124; acá la sección nace funcional y sobria.

**Archivos:**
- Editar `Stacky Agents/frontend/src/App.tsx` (5 puntos, espejo EXACTO del patrón devops):
  1. `App.tsx:30` — agregar `"dbcompare"` al union `Tab`.
  2. `App.tsx:62` — `const [dbCompareEnabled, setDbCompareEnabled] = useState(false);`
  3. `App.tsx:91-94` — nuevo fetch `/api/db-compare/health` → `setDbCompareEnabled(d.flag_enabled === true)` con `.catch(() => setDbCompareEnabled(false))`.
  4. `App.tsx:138` — guard: `else if (tab === "dbcompare" && !dbCompareEnabled) selectTab("team");` (y agregar `dbCompareEnabled` al array de deps de `App.tsx:139`).
  5. `App.tsx:231-234 / :253` — botón de nav (label `Comparador BD`) renderizado solo si `dbCompareEnabled`, y `{tab === "dbcompare" && dbCompareEnabled && <DbComparePage />} {/* Plan 122 */}`.
- Editar `Stacky Agents/frontend/src/api/endpoints.ts` — namespace nuevo `DbCompare` con
  funciones tipadas: `health, listEnvironments, upsertEnvironment, deleteEnvironment,
  setPassword, clearPassword, testConnection, takeSnapshot, listSnapshots` (espejar el
  estilo del namespace `DevOps` existente en ese archivo; los tests devops lo importan como
  `import { DevOps } from '../../api/endpoints'`, ver `ConnectionHealthStrip.test.tsx:14`).
- Crear `Stacky Agents/frontend/src/components/dbcompare/`:
  - `DbComparePage.tsx` — layout de la sección: header con título + badges de drivers
    (desde `/health`: driver faltante → card ámbar con `install_hint` copiable), y
    `<EnvironmentsPanel />`.
  - `EnvironmentsPanel.tsx` — grid de cards de ambientes (alias, engine badge SQL Server/Oracle,
    host:puerto/database, `has_password` 🔑, last_used) + botones por card: `Probar conexión`
    (muestra versión+latencia o error con hint), `Snapshot`, `Password`, `Eliminar` (confirm),
    y form de alta/edición (campos = contrato F1; texto fijo bajo username:
    "Usá una credencial de SOLO LECTURA: Stacky solo lee catálogo y datos, jamás escribe.").
  - `envForm.ts` — lógica pura testeable: `validateEnvironmentForm(values) -> {ok, errors: Record<campo,string>}`
    (alias regex `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`, engine en lista, port 1-65535, host/database/username no vacíos)
    y `defaultPortFor(engine) -> 1433 | 1521`.
  - `dbcompareTypes.ts` — interfaces TS: `DbEnvironment, DriverStatus, SnapshotMeta, TestConnectionResult`.
  - `dbcompare.module.css` — estilos de la sección usando las variables existentes de
    `frontend/src/theme.css` (no hardcodear paleta nueva acá; la escala de severidad llega en Plan 124).

**Tests PRIMERO (solo lógica pura — gap preexistente sin RTL/jsdom, ver nota en
`ConnectionHealthStrip.test.tsx:1-8`):** `frontend/src/components/dbcompare/__tests__/envForm.test.ts`
- `valida alias/engine/port/campos vacíos` (5 casos exactos), `defaultPortFor` (2 casos).

**Comando:** `cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/envForm.test.ts`
y typecheck: `cd "Stacky Agents/frontend" && npx tsc --noEmit`

**Criterio binario:** vitest verde + `tsc --noEmit` con 0 errores + con flag OFF la tab no aparece (verificación manual de 1 minuto, opcional).

**Flag:** `STACKY_DB_COMPARE_ENABLED` (visibilidad). **Runtimes:** N/A. **Operador:** opt-in (default off).

### F6 — No-regresión y cierre

**Objetivo:** demostrar que nada preexistente se degradó.

**Comandos (todos deben quedar como estaban o mejor):**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan122_dbcompare_flags.py tests/test_plan122_dbcompare_registry.py tests/test_plan122_dbcompare_engine.py tests/test_plan122_dbcompare_snapshot.py tests/test_plan122_dbcompare_api.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py tests/test_smoke.py -q
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio binario:** suites del plan 100% verdes; suites preexistentes sin fallos NUEVOS
(las fallas preexistentes conocidas — p.ej. drift `harness_defaults.env` — se re-demuestran
como preexistentes citando el mismo error antes y después).

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Drivers ausentes en la máquina del operador | Lazy import + `driver_status()` con hint exacto de instalación en UI y API; sqlite para tests. |
| Release frozen (PyInstaller) sin drivers | Fuera de scope consciente: la sección funciona en dev/venv; incluir `pyodbc`/`oracledb` en el build spec es tarea explícita futura (gotcha conocido: ModuleNotFoundError en smoke de "Preparar Publicación" = falta collect del submódulo). Documentado en README de la fase, no silencioso. |
| BDs enormes → reflection lenta | `schema_filter` por ambiente + snapshot síncrono documentado como limitación de F4; el camino threaded llega en Plan 123 y es el que usa la UI. |
| Permisos de catálogo insuficientes (vistas sin definición, checks no legibles) | try/except por capability con campo `error` en el snapshot; nunca rompe la toma. |
| Password filtrado en mensajes de error de conexión | Scrub explícito en `test_connection` (test dedicado `test_error_no_filtra_password`). |
| `ODBC Driver 17` no instalado (distinto de pyodbc) | El error real de pyodbc se devuelve legible en `test_connection`; el form permite elegir `odbc_driver` (p.ej. "ODBC Driver 18 for SQL Server"). |

## 6. Fuera de scope (de este plan; parte llega en la serie)

- Diff de esquemas y corridas comparativas → **Plan 123**.
- UI inmersiva (treemap, gauge, drill-down side-by-side, timeline) → **Plan 124**.
- Scripts de paridad + backups pareados → **Plan 125**.
- Paridad de DATOS de tablas de parámetros → **Plan 126**.
- Stored procedures / functions / triggers / jobs (el Inspector de SQLAlchemy no los cubre;
  extensión futura con queries de catálogo por dialecto, fuera de la serie).
- Comparación cross-engine (oracle vs sqlserver) — sin valor para paridad de ambientes.
- Ejecutar CUALQUIER script contra una BD desde Stacky — prohibido por diseño (HITL).
- Modificar `services/db_query.py` o su mecanismo `auth/db_readonly.json` (conviven; el
  registro nuevo es multi-ambiente y ortogonal).

## 7. Glosario

- **Ambiente:** una BD concreta registrada con alias (p.ej. `PACIFICO-PROD`), no un servidor DevOps.
- **Engine/motor:** `sqlserver` (Pacífico) u `oracle` (Ripley). `sqlite` solo para tests.
- **Inspector / reflection:** API de SQLAlchemy (`sqlalchemy.inspect(engine)`) que lee el
  catálogo del motor con SELECTs internos — no ejecuta DDL/DML.
- **Snapshot canónico:** JSON v1 determinista (listas ordenadas, `sort_keys`) cuyo
  `content_hash` cambia sii el esquema cambia.
- **keyring:** Credential Manager del SO; el password vive ahí bajo service
  `stacky-dbcompare`, nunca en JSON (patrón Plan 91).
- **DPAPI:** cifrado del mecanismo VIEJO por-proyecto (`auth/db_readonly.json`); NO se toca.
- **HITL (human-in-the-loop):** Stacky genera artefactos; ejecutar siempre es del operador.

## 8. Orden de implementación

1. F0 flags + tests.
2. F1 registro + tests.
3. F2 engine + tests.
4. F3 snapshot + tests.
5. F4 API + tests.
6. F5 UI + vitest + tsc.
7. F6 no-regresión y cierre.

## 9. Definición de Hecho (DoD)

- [ ] Las 2 flags existen, editables desde la UI de flags, default OFF/10; master en `capacidades_optin`, knob en `comparador_bd`.
- [ ] CRUD de ambientes con password SOLO en keyring; JSON sin secretos (test lo prueba).
- [ ] `test_connection` funciona con sqlite en tests y reporta hint accionable si falta driver.
- [ ] Snapshot v1 determinista persistido con prune; contrato congelado documentado.
- [ ] Endpoints activos solo con flag ON (health siempre); registrados en `api/__init__.py`.
- [ ] Tab "Comparador BD" visible solo con flag ON; gestión de ambientes completa desde UI.
- [ ] 5 archivos de test backend + 1 vitest verdes con los comandos exactos de cada fase.
- [ ] `tsc --noEmit` 0 errores; suites preexistentes sin fallos nuevos.
- [ ] Ningún endpoint ejecuta DDL/DML contra BDs registradas (revisión por grep: `execute(` solo con `_PROBE_SQL` y reflection).
