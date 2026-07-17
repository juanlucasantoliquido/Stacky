# Plan 155 — Comparador de BD: configuración de ambientes en contexto, import automático desde `web.config` (agente local) y Panel de Migración siempre visible

**Estado:** PROPUESTO (v1, 2026-07-17, autor `StackyArchitectaUltraEficientCode`)
**Serie previa:** 122 (núcleo/ambientes) → 123 (motor diff) → 124 (UI inmersiva) → 125 (scripts + backups) → 126 (paridad de datos). **TODA la serie 122-126 está IMPLEMENTADA en `main`.** Este plan es la **capa de UX/configuración** encima de ese comparador; NO reimplementa nada de la serie.
**Dependencias:** serie 122-126 IMPLEMENTADA (verificado en `main`: `backend/services/dbcompare_registry.py`, `backend/api/db_compare.py`, `frontend/src/components/dbcompare/DbComparePage.tsx` y hermanos existen). Master `STACKY_DB_COMPARE_ENABLED` ya está ON por default (`backend/config.py:119-121`).
**Ortogonal a:** Plan 74 (Migrador ADO→GitLab — es OTRA cosa, ver Glosario y F6), Planes 116/119/120/121.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-17 sobre el working tree (rama `main`).
> Rutas de código relativas a `Stacky Agents/`. Prohibido desviarse de los nombres exactos.

---

## 1. Objetivo + KPI

El operador administra el mismo producto RS en varios ambientes (dev/test/prod) y hoy,
para comparar bases, primero tiene que **registrar cada conexión de BD**. Ese registro
existe (`EnvironmentsPanel.tsx`) pero:
1. Está **al fondo** de `DbComparePage.tsx` (renderizado en `frontend/src/components/dbcompare/DbComparePage.tsx:200`, después de resultados y timeline) → el operador no lo encuentra y termina yendo a "otra pantalla".
2. Pide **6 campos técnicos** (alias, engine, host, port, database, username) + password aparte (`frontend/src/components/dbcompare/envForm.ts:9-16`, `EnvironmentsPanel.tsx:7-14`) → "no se entiende nada".
3. Los datos de conexión de esos ambientes ya viven, escritos por humanos, en archivos `web.config` / `XMLConfig.xml` del producto RS (el propio Plan 122 §2-bis cita `trunk\Batch\XMLConfig.xml` de RSPACIFICO como fuente canónica de credenciales) → **hoy el operador los transcribe a mano**, con riesgo de error y de exponer credenciales.
4. La "migración entre BDs" (los scripts de paridad + backups del Plan 125) está escondida detrás de un input de "pegá el `run_id`" (`DbComparePage.tsx:203-230`) → no es un panel accionable, es un rincón.

Este plan cierra esas 4 brechas SIN tocar el motor de comparación:

- **P1 — Configurar y guardar BDs desde el propio Comparador**, en contexto, sin ir a otra pantalla.
- **P2 — Setup de ambientes guiado y clarísimo** (wizard de 1-3 pasos, no un formulario crudo de 6 campos).
- **P3 — "Solo el datasource" + agente local que lee un `web.config`** (u otro archivo de config), **autodetecta** las connection strings y **autoconfigura** el ambiente. El parseo es **100% local y determinista** (sin LLM, sin red): la credencial nunca sale de la máquina del operador.
- **P4 — Panel de Migración de BD SIEMPRE VISIBLE** dentro del Comparador, con todas las acciones (generar/ver/descargar scripts de paridad + backups) a mano, sin pegar `run_id`.

**KPIs (binarios):**

- **KPI-1:** con `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` ON, subir/elegir un `web.config` con N connection strings devuelve N previews con host/engine/database/username detectados y la contraseña **enmascarada** (`****`), y confirmar UNA de ellas crea el ambiente con su password guardada en keyring — todo sin que la contraseña en claro aparezca NUNCA en la respuesta HTTP ni en los logs (tests F1/F2/F3).
- **KPI-2:** con `STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED` ON, un operador sin ningún ambiente registrado ve, en el tope del Comparador, un CTA "Agregar base de datos" que abre el wizard guiado; puede crear un ambiente pegando **solo un datasource** y Stacky deriva engine/host/port/database/username (test F4/F5).
- **KPI-3:** con `STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED` ON, el Panel de Migración de BD es visible de forma persistente y lista las corridas `done` con botón directo "Generar/ver scripts" y "Descargar bundle", sin input manual de `run_id` (test F6).
- **KPI-4 (seguridad, no negociable):** `grep` sobre los logs del backend tras un import completo NO contiene ninguna contraseña en claro; el detector de egreso (`services/egress_policies.py`) marca cualquier connection string con `password=` como clase `secrets`; el parseo del archivo no realiza ninguna llamada de red (test F3).
- **KPI-5:** con las 3 flags OFF, NADA cambia respecto de `main` (comparador funciona igual; ni endpoints nuevos activos —403—, ni UI nueva) (tests por fase).

## 2. Por qué ahora / gap que cierra

- La serie 122-126 dejó el motor completo pero la **puerta de entrada** (registrar ambientes) quedó técnica y escondida. El propio Plan 125 documentó como deuda que la sección de scripts se opera "pegando el `run_id`" por falta de selector visual (`DbComparePage.tsx:207-209`). Este plan salda esa deuda.
- El substrato de seguridad para hacer P3 sin riesgo **ya existe** y no hay que inventarlo: keyring (`services/dbcompare_registry.py:26`, `set_password` :179, `get_credential` :203, `_save` bloquea persistir password :65-71), cifrado DPAPI (`services/secrets_store.py:151` `encrypt_secret`), masking (`services/egress_sentinel.py:23` `mask_excerpt`), y detector de egreso determinista (`services/egress_policies.py:64` `_DETECTORS`, con clase `secrets` que ya matchea `password=` y connection strings, `detect_classes` :96, `check` :126).
- El operador lo pidió textualmente. Es UX de altísimo valor operativo con costo bajo (capa sobre lo existente).

## 3. Principios y guardarraíles (obligatorios en TODO el plan)

1. **Human-in-the-loop innegociable.** Autodetectar NO es autoconfigurar sin confirmar: el import muestra previews y el operador **elige y confirma** qué ambiente crear. Stacky nunca crea/pisa un ambiente ni ejecuta un script sin acción explícita del operador. El comparador sigue generando scripts, **jamás ejecutándolos** (doctrina serie 122-126, `api/db_compare.py` no tiene endpoint de ejecución).
2. **Datos personales / secretos (instrucción de la organización: "Informar de los riesgos al tratar datos personales").** P3 lee connection strings con credenciales. Reglas DURAS (fase F3 dedicada + tests):
   - (a) **Nunca loguear** la credencial en claro (ni `logger.info`, ni `print`, ni excepción con el valor). Los logs solo ven valores pasados por `mask_excerpt`.
   - (b) **Enmascarar en la UI**: la contraseña detectada se muestra `****` (input `type="password"` / texto `••••`), nunca en claro.
   - (c) **Almacenar sin texto plano expuesto**: la password va a keyring (patrón existente), nunca al JSON en disco (`environments.json`) ni a la respuesta HTTP.
   - (d) **Advertir explícitamente** al operador con un banner fijo en el wizard de import: "Estás manejando credenciales de base de datos. Se guardan cifradas en el Administrador de credenciales de Windows y no se registran en logs."
   - (e) **Parseo 100% local, sin egreso**: el parser es una función pura de stdlib (`xml.etree.ElementTree` + regex), **sin LLM y sin red**. Ninguna credencial se envía a ningún servicio externo. (Esto es más seguro que usar un modelo: la credencial jamás toca un prompt.)
3. **Config del operador SIEMPRE por UI (regla dura de la casa).** Las 3 flags nuevas se registran en `_CATEGORY_KEYS` bajo la categoría `comparador_bd` (ya existe, `services/harness_flags.py:106,314`) → aparecen y se togglean desde el panel de flags del arnés. Nada es "solo env var".
4. **Cero trabajo extra al operador / opt-in default ON.** Las 3 flags nacen **default ON** (mejoras de UX bajo un master —`STACKY_DB_COMPARE_ENABLED`— que el operador ya activó). Ninguna de las 4 excepciones duras aplica: no bypassean revisión humana (el operador confirma cada import), no son destructivas (crear un registro de ambiente es reversible con "Eliminar", `EnvironmentsPanel.tsx:57`), no requieren prerequisito no garantizado (el parser usa solo stdlib; si `keyring` falta ya hay degradación 503 existente), y no reducen seguridad por default (la reducen a cero: menos transcripción manual = menos exposición). Backward-compatible al 100%.
5. **Paridad de 3 runtimes.** Es una feature de PANEL (backend Flask + React). El "agente local" es un módulo Python del backend que corre en el proceso local del backend — **no depende de Codex/Claude/Copilot**; funciona idéntico en los 3. Fallback declarado por fase.
6. **No reinventar.** Reusar keyring, `mask_excerpt`, `egress_policies`, el registro de ambientes y los endpoints de scripts ya existentes.

---

## 4. Fases

### F0 — Flags del arnés + config (fundación)

**Objetivo (1 frase):** declarar las 3 flags nuevas, visibles/editables desde la UI de flags, default ON, gateadas por el master del comparador.
**Valor:** habilita el resto del plan de forma togglable por UI y reversible.

**Archivos a editar:**
- `backend/services/harness_flags.py`
- `backend/config.py`
- `backend/tests/test_harness_flags_requires.py` (mapa congelado de aristas `requires`)
- `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1` (registrar el test nuevo en el ratchet)

**Flags nuevas (nombres EXACTOS, todas `type="bool"`, `default=True`, `requires="STACKY_DB_COMPARE_ENABLED"`):**
1. `STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED` — setup de ambientes guiado y en contexto (P1+P2).
2. `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` — import automático desde `web.config`/datasource (P3, agente local).
3. `STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED` — Panel de Migración de BD siempre visible (P4).

**Cambios exactos:**

1. En `backend/config.py`, junto al bloque `STACKY_DB_COMPARE_*` (después de `config.py:132`), agregar 3 atributos:
```python
    STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED", "true"
    ).strip().lower() == "true"
```
   (copiar EXACTAMENTE el idioma de `config.py:119-121`; verificar el operador `.strip().lower() == "true"` real en esa línea y replicarlo literal.)

2. En `backend/services/harness_flags.py`, dentro de `FLAG_REGISTRY` (después del último `FlagSpec` de `comparador_bd`, cerca de `harness_flags.py:3166`), agregar 3 `FlagSpec`:
```python
    FlagSpec(
        key="STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED",
        type="bool", default=True, requires="STACKY_DB_COMPARE_ENABLED",
        label="Configurar ambientes desde el propio Comparador",
        description="Muestra el alta/edición guiada de ambientes de BD dentro del Comparador (arriba de todo), no en una pantalla aparte.",
        group="comparador_bd",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED",
        type="bool", default=True, requires="STACKY_DB_COMPARE_ENABLED",
        label="Autodetectar conexión desde web.config",
        description="Permite elegir un archivo web.config/XMLConfig y autodetectar las connection strings para precargar el ambiente. El parseo es local; la contraseña se enmascara y se guarda en el Administrador de credenciales de Windows.",
        group="comparador_bd",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED",
        type="bool", default=True, requires="STACKY_DB_COMPARE_ENABLED",
        label="Panel de Migración de BD siempre visible",
        description="Muestra un panel persistente de scripts de paridad + backups por corrida, sin pegar el run_id a mano.",
        group="comparador_bd",
    ),
```
   **Gotcha obligatorio (Plan 63/122):** para `type="bool"` con `default=True` está BIEN pasar `default=True` (el ratchet `_CURATED_DEFAULTS_ON` es la vía canónica para bools ON; ver `harness_flags.py:328-335`). NO pasar `default=False` explícito en flags nuevas.

3. En `backend/services/harness_flags.py`, en `_CATEGORY_KEYS["comparador_bd"]` (tupla que arranca en `harness_flags.py:314`), agregar las 3 keys nuevas al final de la tupla. **Criterio:** `test_every_registry_flag_is_categorized` (nota `harness_flags.py:325-326`) debe seguir verde.

4. En `backend/tests/test_harness_flags_requires.py`, en el diccionario `_REQUIRES_MAP_FROZEN`, agregar 3 entradas:
```python
    "STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED": "STACKY_DB_COMPARE_ENABLED",
```
   **Motivo (aprendizaje C1 planes 122/126):** `test_requires_map_is_frozen` compara el mapa por igualdad EXACTA; declarar `requires=` sin dar de alta la arista rompe el test. La arista es de profundidad 1 (child → master directo), coherente con la regla `requires` R4 (no encadenar a flag hija).

**Test PRIMERO (TDD):** `backend/tests/test_plan155_dbcompare_ux_flags.py`
Casos:
- `test_las_tres_flags_existen_en_registry` — las 3 keys están en `FLAG_REGISTRY`.
- `test_las_tres_flags_default_on` — `flag_default("<key>") is True` para las 3.
- `test_las_tres_flags_requieren_master` — cada una tiene `requires == "STACKY_DB_COMPARE_ENABLED"`.
- `test_las_tres_flags_categorizadas_en_comparador_bd` — las 3 están en `_CATEGORY_KEYS["comparador_bd"]`.
Comando (venv del repo, por archivo):
```
cd "Stacky Agents/backend" && ./.venv/Scripts/python.exe -m pytest tests/test_plan155_dbcompare_ux_flags.py tests/test_harness_flags_requires.py tests/test_harness_flags.py -q
```
(usar el intérprete real del repo: `backend/.venv` según memoria de entorno; si no existe, `../venv`.)

**Criterio de aceptación BINARIO:** los 3 archivos de test arriba pasan (exit 0) y `test_requires_map_is_frozen` + `test_every_registry_flag_is_categorized` verdes.
**Flag que la protege:** N/A (esta fase ES las flags).
**Impacto por runtime:** idéntico (config de backend). Fallback: N/A.
**Trabajo del operador:** ninguno (default ON, togglable por UI de flags).

**Registro en ratchet:** agregar `tests/test_plan155_dbcompare_ux_flags.py` (y los de F1/F2/F3) al array `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh:20` y su espejo `.ps1`. **Criterio:** `test_harness_ratchet_meta.py` verde.

---

### F1 — Agente local: parser determinista de `web.config` y de datasource (backend, sin red, sin LLM)

**Objetivo (1 frase):** una función pura que recibe texto (XML de `web.config` o un datasource suelto) y devuelve conexiones detectadas con la contraseña separada y enmascarable, sin I/O ni red.
**Valor:** núcleo del "agente local"; convierte transcripción manual en autodetección.

**Archivo a crear:** `backend/services/dbcompare_config_import.py`

**Símbolos EXACTOS a crear:**
- `@dataclass class ParsedConnection` con campos: `name: str`, `engine: str` (`"sqlserver"` | `"oracle"` | `""` si no se pudo inferir), `host: str`, `port: int | None`, `database: str`, `username: str`, `integrated_security: bool`, `has_password: bool`, `masked_raw: str` (connection string original con la password reemplazada por `****`).
- `SENSITIVE_KEYS = ("password", "pwd")` (case-insensitive).
- `def parse_connection_string(raw: str) -> tuple[ParsedConnection, str | None]` — devuelve `(ParsedConnection, password_o_None)`. La password en claro se retorna **por separado**, NUNCA dentro de `ParsedConnection`.
- `def parse_webconfig(xml_text: str) -> list[tuple[ParsedConnection, str | None]]` — parsea `<connectionStrings><add name= connectionString= providerName=/>`; degrada a `[]` si el XML es inválido (nunca lanza).
- `def _infer_engine(provider_name: str, keys: dict) -> str` — reglas literales abajo.
- `def _split_kv(raw: str) -> dict[str, str]` — parte por `;`, cada par por el primer `=`; keys normalizadas a lower y trim.

**Reglas de parseo (LITERALES, un modelo menor las implementa sin inferir):**
- Separar la connection string por `;`. Cada segmento `k=v` → key = lower(trim) antes del primer `=`, value = trim después.
- **Host/puerto (SQL Server):** tomar `data source` o `server` o `addr` o `address`. Si contiene `,` → `host = parte antes de la coma`, `port = int(parte después)`. Si contiene `\` (instancia nombrada) → `host = string completo`, `port = None`. Si no hay puerto → `port = None`.
- **Database (SQL Server):** `initial catalog` o `database`.
- **Username:** `user id` o `uid` o `user`.
- **Password:** `password` o `pwd` → va al segundo elemento de la tupla; `has_password = bool(valor no vacío)`.
- **Integrated Security:** `integrated security` in (`sspi`, `true`, `yes`) → `integrated_security = True`, `has_password = False` aunque no haya user/pass.
- **Engine (`_infer_engine`):** si `provider_name` (lower) contiene `oracle` → `"oracle"`; si contiene `sqlclient` o `sqlserver` o `system.data.sqlclient` → `"sqlserver"`. Si no hay provider: si la conn string tiene `initial catalog` o `integrated security` → `"sqlserver"`; si `data source` parece TNS/EZConnect (`/` o `:` con `service`) → `"oracle"`; si no se puede decidir → `""` (el operador elige en la UI).
- **Oracle host/port/db:** de `data source` EZConnect `host:port/service` → host, port, database=service; si es TNS alias (sin `:`), `host = alias`, `port = None`, `database = ""`.
- **`masked_raw`:** reconstruir la conn string original reemplazando el value de cualquier key en `SENSITIVE_KEYS` por `****`. Este es el ÚNICO string que puede ir a logs/UI.

**Regla de seguridad DURA en este módulo:** el módulo NO importa `logging` para loguear values; NO hace `requests`/`urllib`/socket; NO importa nada de LLM. La password en claro existe solo como valor de retorno de las funciones, nunca como atributo de `ParsedConnection` ni en `masked_raw`.

**Test PRIMERO (TDD):** `backend/tests/test_plan155_dbcompare_webconfig_parse.py`
Casos (fixtures string inline, sin archivos):
- `test_sqlserver_user_pass` — `Server=srv,1433;Database=RS;User ID=rs;Password=Secr3t;` → engine sqlserver, host srv, port 1433, database RS, username rs, has_password True; password devuelto = `"Secr3t"`; `masked_raw` contiene `Password=****` y NO contiene `Secr3t`.
- `test_sqlserver_integrated_security` — `Data Source=srv\SQLEXPRESS;Initial Catalog=RS;Integrated Security=SSPI;` → integrated_security True, host `srv\SQLEXPRESS`, port None, has_password False.
- `test_oracle_ezconnect` — provider `Oracle.ManagedDataAccess.Client`, `Data Source=host1:1521/ORCL;User Id=u;Password=p;` → engine oracle, host host1, port 1521, database ORCL.
- `test_webconfig_multiples_conn` — XML con 2 `<add>` → lista de 2.
- `test_webconfig_xml_invalido_no_crashea` — texto no-XML → `[]`.
- `test_password_nunca_en_parsedconnection` — para todos los casos: serializar `ParsedConnection` a dict y afirmar que ningún value contiene la password en claro.
Comando:
```
cd "Stacky Agents/backend" && ./.venv/Scripts/python.exe -m pytest tests/test_plan155_dbcompare_webconfig_parse.py -q
```
**Criterio BINARIO:** todos los casos pasan; en especial `test_password_nunca_en_parsedconnection` y `masked_raw` sin secreto.
**Flag:** `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` (el módulo es puro; la fase se prueba sin flag). 
**Impacto por runtime:** idéntico (stdlib). Fallback: N/A (sin dependencias externas).
**Trabajo del operador:** ninguno.

---

### F2 — Endpoints de import local + confirmación a keyring (backend)

**Objetivo (1 frase):** exponer el agente local por HTTP: parsear un archivo/texto local, devolver **previews enmascarados**, y —tras confirmación humana— crear el ambiente y escribir la password directo a keyring, sin que la password en claro viaje al browser.
**Valor:** cablea F1 al comparador respetando human-in-the-loop y secretos.

**Archivo a editar:** `backend/api/db_compare.py` (mismo blueprint `bp` de `api/db_compare.py:24`; NO crear blueprint nuevo).
**Archivo a editar (cache transitoria):** `backend/services/dbcompare_config_import.py` (agregar cache en memoria).

**Símbolos EXACTOS:**
- En `dbcompare_config_import.py`: `_IMPORT_CACHE: dict[str, dict]` (in-memory, protegido por `threading.Lock`), `def stash_parsed(conns_with_pw) -> str` (genera `import_id` uuid4, guarda `[(ParsedConnection, password)]` con timestamp), `def pop_parsed(import_id, index) -> tuple[ParsedConnection, str | None]` (recupera y descarta), `def sweep_expired(ttl_sec=600)` (borra entradas viejas). El password vive SOLO en este cache de proceso, con TTL, nunca en disco.
- En `api/db_compare.py`:
  - `POST /environments/import-config` → `import_config_route()`. Body: `{"path": "<ruta local>"}` **o** `{"content": "<texto xml/datasource>"}`. Gate `_require_enabled()` (`api/db_compare.py:27`) **y** nueva `_require_webconfig_import_enabled()` (403 si `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` OFF). Devuelve `{"import_id": str, "connections": [preview...]}` donde cada `preview` = `ParsedConnection` a dict **sin password** + `index`.
  - `POST /environments/import-config/confirm` → `confirm_import_route()`. Body: `{"import_id": str, "index": int, "alias": str, "overrides": {...}}`. Recupera del cache, hace `upsert_environment(...)` (`services/dbcompare_registry.py`) con los campos, y si había password llama `set_password(alias, password)` (`dbcompare_registry.py:179`). Devuelve `{"ok": true, "alias": ...}`. NUNCA devuelve la password.

**Lectura de archivo local segura (reglas DURAS, en `import_config_route`):**
- Si viene `path`: `os.path.realpath`, rechazar si no existe (404), si es directorio (400), si tamaño > `1_000_000` bytes (413), o si extensión no ∈ (`.config`, `.xml`) (415). El backend corre **local** (mono-operador) → leer el archivo del FS del operador es local, sin egreso.
- Si viene `content`: cap de `1_000_000` chars.
- **Nunca** loguear `path` con su contenido ni el `content`; a lo sumo `logger.info("import-config: %d conexiones detectadas", n)` (solo el conteo).

**Pseudocódigo `import_config_route`:**
```
enabled? no -> 403
body = request.get_json()
raw = leer_de_path_o_content(body)   # con las validaciones de arriba
conns = parse_webconfig(raw) if parece_xml else [parse_connection_string(raw)]
import_id = stash_parsed(conns)
previews = [ {**asdict(pc), "index": i}  # asdict NO tiene password (F1 garantiza)
            for i,(pc,_pw) in enumerate(conns) ]
return {"import_id": import_id, "connections": previews}
```

**Test PRIMERO (TDD):** `backend/tests/test_plan155_dbcompare_import_api.py` (usar `app.test_client()`, monkeypatch de `keyring` como los tests plan122)
Casos:
- `test_import_403_si_flag_off` — con `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` OFF → 403.
- `test_import_content_devuelve_previews_sin_password` — POST content con password → 200, ningún value del JSON contiene la password en claro; `has_password True`.
- `test_import_path_inexistente_404`, `test_import_path_directorio_400`, `test_import_extension_no_permitida_415`, `test_import_oversize_413`.
- `test_confirm_crea_ambiente_y_setea_keyring` — confirm → `upsert_environment` llamado + `set_password` llamado con la password correcta (mock keyring); respuesta sin password.
- `test_confirm_import_id_inexistente_404`.
- `test_logs_no_contienen_password` — capturar logs (`caplog`) durante import+confirm y afirmar que la password en claro no aparece.
Comando:
```
cd "Stacky Agents/backend" && ./.venv/Scripts/python.exe -m pytest tests/test_plan155_dbcompare_import_api.py -q
```
**Criterio BINARIO:** todos pasan; `test_import_content_devuelve_previews_sin_password`, `test_confirm_crea_ambiente_y_setea_keyring` y `test_logs_no_contienen_password` son bloqueantes.
**Flag:** `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` (default ON). Con OFF, los 2 endpoints devuelven 403 y no se registran en la UI.
**Impacto por runtime:** idéntico (endpoints Flask locales). Fallback: si `keyring` no está → `set_password` ya devuelve 503 con hint (patrón `api/db_compare.py:120-127`); el ambiente se crea igual y el operador setea la password manual después.
**Trabajo del operador:** ninguno para tener la capacidad; al usarla, elige archivo y confirma (human-in-the-loop obligatorio).

**Endpoint del cliente (frontend `api/endpoints.ts`, namespace `DbCompare`):** agregar `DbCompare.importConfig(payload)` y `DbCompare.confirmImport(payload)` siguiendo el patrón existente de `DbCompare.upsertEnvironment` (importado en `DbComparePage.tsx:2`).

---

### F3 — Guardarraíles de datos personales y secretos (FASE EXPLÍCITA, instrucción de la organización)

**Objetivo (1 frase):** consolidar y **testear** los 5 requisitos (a-e) de manejo de credenciales como invariantes del sistema, no como buenas intenciones.
**Valor:** cumple la instrucción de la organización "Informar de los riesgos al tratar datos personales" con evidencia binaria.

**Archivos a editar/crear:**
- `backend/services/egress_policies.py` — verificar (y, si falta, agregar) que la clase `secrets` de `_DETECTORS` (`egress_policies.py:81-92`) matchea el patrón `password\s*=` y `connection string` (ya lo hace según evidencia; si el regex no cubre `pwd=`, agregarlo).
- `backend/tests/test_plan155_dbcompare_secret_guardrails.py` (nuevo).
- `frontend/src/components/dbcompare/CredentialWarningBanner.tsx` (nuevo, punto d — ver F4 para el montaje).

**Invariantes testeadas (mapa requisito → test):**
- (a) **No loguear en claro:** `test_a_import_no_loguea_password_en_claro` — corre import+confirm con `caplog` y afirma que ningún record contiene la password.
- (b) **Enmascarar en UI:** `test_b_masked_raw_sin_secreto` (reusa F1) + verificación en F4 (input `type="password"`, criterio de F4).
- (c) **Sin texto plano en disco/respuesta:** `test_c_environments_json_sin_password` — tras confirm, leer `data_dir()/db_compare/environments.json` y afirmar que no contiene la password ni la key `password` (el `_save` de `dbcompare_registry.py:65-71` ya lo bloquea; el test lo certifica end-to-end) + `test_c_respuesta_confirm_sin_password`.
- (d) **Advertencia explícita:** cubierto por F4 (banner presente); acá se documenta el texto exacto del banner (§3.2.d).
- (e) **Parseo local sin egreso:** `test_e_parser_no_hace_red` — monkeypatch de `socket.socket` / `urllib.request.urlopen` para que lancen si se invocan, y correr `parse_webconfig` sobre un fixture grande → no se invoca ninguna → sin excepción; y `test_e_detector_egreso_marca_connstring` — `egress_policies.detect_classes("...Password=x;...")` incluye `"secrets"`.

Comando:
```
cd "Stacky Agents/backend" && ./.venv/Scripts/python.exe -m pytest tests/test_plan155_dbcompare_secret_guardrails.py -q
```
**Criterio BINARIO:** los 6 tests (a,c×2,e×2 + reuso b) pasan.
**Flag:** protegida por `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` (los guardarraíles aplican cuando el import está activo).
**Impacto por runtime:** idéntico. Fallback: N/A (invariantes de seguridad, no degradan).
**Trabajo del operador:** ninguno.

---

### F4 — Wizard guiado de ambientes en contexto (frontend, P1+P2+P3 UI)

**Objetivo (1 frase):** reemplazar el formulario crudo de 6 campos por un wizard de 1-3 pasos con 3 modos —"Pegar datasource", "Elegir web.config", "Manual (avanzado)"— y el banner de credenciales.
**Valor:** el operador configura una BD en contexto, entendiendo cada paso, pidiendo solo lo mínimo.

**Archivos a crear:**
- `frontend/src/components/dbcompare/EnvSetupWizard.tsx`
- `frontend/src/components/dbcompare/CredentialWarningBanner.tsx`
- `frontend/src/components/dbcompare/envSetupLogic.ts` (lógica pura testeable con vitest — gap RTL/jsdom conocido, ver `envForm.ts:1-3`)
**Archivos a editar:**
- `frontend/src/components/dbcompare/EnvironmentsPanel.tsx` (montar el wizard como forma primaria de alta; conservar el form actual bajo el modo "Manual").
- `frontend/src/components/dbcompare/dbcompare.module.css` (estilos del wizard usando variables ya existentes; **cero hex nuevos en .tsx**, DoD serie 124).

**Diseño de UX (literal):**
- Paso 1 — "¿Cómo querés cargar la base?": 3 botones/radio: **(A) Pegar datasource** (default), **(B) Desde web.config**, **(C) Manual**. Si `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` OFF, ocultar (B). Si `STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED` OFF, no renderizar el wizard (fallback al form actual).
- Modo A: un `<textarea>` "Pegá tu datasource / connection string" + botón "Detectar". Llama `DbCompare.importConfig({content})`, muestra el preview (engine/host/port/database/username) editable + campo alias + password `type="password"`; **el banner de credenciales visible**. "Guardar" → `DbCompare.confirmImport(...)`.
- Modo B: input `type="file"` (accept `.config,.xml`) → lee el archivo en el browser (`FileReader`) y manda `content` (evita depender de rutas del SO); o campo "ruta del archivo" que manda `path`. Muestra **lista** de conexiones detectadas (radio para elegir 1), cada una con host/engine/database/username y password `••••`. Banner visible. Elegir + alias + "Guardar" → confirm.
- Modo C: el form actual de `envForm.ts` (fallback, sin cambios de validación).
- **Banner (`CredentialWarningBanner.tsx`, texto EXACTO):** "⚠️ Estás manejando credenciales de base de datos. Stacky las guarda cifradas en el Administrador de credenciales de Windows y nunca las escribe en logs ni en disco en texto plano. El archivo se lee localmente; nada se envía a servicios externos."

**Lógica pura (`envSetupLogic.ts`):**
- `mapPreviewToForm(preview): EnvironmentFormValues` — arma los `EnvironmentFormValues` (`envForm.ts:9`) desde un preview; si `engine===""` deja el default `sqlserver`; si `port===null` usa `defaultPortFor(engine)` (`envForm.ts` export).
- `chooseInitialMode(flags): "datasource"|"webconfig"|"manual"`.

**Test PRIMERO (TDD, vitest puro):** `frontend/src/components/dbcompare/__tests__/envSetupLogic.test.ts`
Casos: `mapPreviewToForm` completa port default cuando null; usa engine detectado; `chooseInitialMode` respeta flags (webconfig oculto si flag off). 
Comando:
```
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/envSetupLogic.test.ts
```
**Criterio BINARIO:** vitest de ese archivo verde + `npx tsc --noEmit` 0 errores. Verificación visual (F7): el input de password es `type="password"` y el banner aparece en modos A y B.
**Flag:** `STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED` (modos A/C) + `STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED` (modo B). Con ambas OFF, se renderiza el `EnvironmentsPanel` actual sin cambios.
**Impacto por runtime:** idéntico (UI servida por backend). Fallback: modo Manual siempre disponible aunque el import falle.
**Trabajo del operador:** ninguno (mejora automática); al usar, elige modo y confirma.

---

### F5 — Elevar la gestión de ambientes al tope del Comparador (frontend, P1)

**Objetivo (1 frase):** que el registro de ambientes deje de estar al fondo y aparezca arriba, con CTA de estado vacío, sin salir del Comparador.
**Valor:** el operador ya no "va a otra pantalla"; encuentra el alta al instante.

**Archivo a editar:** `frontend/src/components/dbcompare/DbComparePage.tsx`
**Cambios exactos:**
- Mover el render de `<EnvironmentsPanel .../>` (hoy en `DbComparePage.tsx:200`, al fondo) a **arriba**, justo debajo del header/driverWarning (antes de `RunsTimeline`), envuelto en un `<details open={environments.length===0}>` o sección colapsable "Bases de datos configuradas" para no molestar cuando ya hay ambientes.
- Estado vacío: si `environments.length === 0`, mostrar un CTA prominente "➕ Agregar una base de datos para empezar" que abre el `EnvSetupWizard` (F4). El `CompareWizard` (`CompareWizard.tsx`) ya recibe `environments`; si hay <2, mostrar inline "Necesitás al menos 2 ambientes para comparar — agregá otro" con botón al wizard.
- Gate: todo el bloque nuevo bajo `STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED`. Con OFF, la página queda EXACTAMENTE como en `main` (EnvironmentsPanel al fondo).

**Test PRIMERO (TDD, lógica pura):** `frontend/src/components/dbcompare/__tests__/envPlacement.test.ts` (nuevo helper `envPlacementLogic.ts` con `shouldShowEmptyCta(envs, flagOn): boolean` y `shouldNudgeAddMore(envs): boolean`).
Comando:
```
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/envPlacement.test.ts
```
**Criterio BINARIO:** vitest verde + `tsc --noEmit` 0. Visual (F7): sin ambientes → CTA arriba; con flag OFF → layout de `main`.
**Flag:** `STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED`.
**Impacto por runtime:** idéntico. Fallback: layout previo.
**Trabajo del operador:** ninguno.

---

### F6 — Panel de Migración de BD siempre visible (frontend, P4)

**Objetivo (1 frase):** convertir la sección de scripts —hoy detrás de "pegá el run_id" (`DbComparePage.tsx:203-230`)— en un panel persistente con selector de corridas y todas las acciones a mano.
**Valor:** la migración (scripts de paridad + backups pareados) se acciona en 1 click, sin conocer IDs.

**Archivo a crear:** `frontend/src/components/dbcompare/MigrationPanel.tsx` + `migrationPanelLogic.ts`.
**Archivo a editar:** `frontend/src/components/dbcompare/DbComparePage.tsx` (reemplazar el bloque `<section className={styles.scriptsSection}>` de `:203-230` por `<MigrationPanel runs={runs} .../>`).

**Diseño (literal):**
- Panel persistente titulado **"Migración de BD (scripts de paridad + backups)"** — visible siempre que la flag esté ON, no colapsado tras un input.
- Selector visual: lista de corridas `done` (de `runs`, ya cargadas en `DbComparePage.tsx:33` vía `DbCompare.listRuns`), cada fila con par `source_alias → target_alias`, fecha (usar `relativeTime.ts` existente) y botones **"Generar/ver scripts"** (llama `DbCompare.generateScripts(run_id)` / muestra `ScriptsPanel` existente inline) y **"Descargar bundle .zip"** (endpoint existente `GET /api/db-compare/runs/<run_id>/scripts.zip`, `api/db_compare.py:328`).
- Reusa el `ScriptsPanel.tsx` existente como sub-render (no reescribir el visor); el panel solo le pasa el `run_id` elegido por click en vez de por input manual.
- **Disambiguación obligatoria (Glosario):** este panel NO es el tab "Migrador" (ADO→GitLab, Plan 74, `pages/MigratorPage.tsx`). Es la migración de ESQUEMA/DATOS entre ambientes de BD, materializada como scripts que el operador ejecuta (Stacky nunca ejecuta). No renombrar ni tocar el tab Migrador existente.

**Lógica pura (`migrationPanelLogic.ts`):** `selectableRuns(runs): CompareRun[]` (filtra `status==="done"`), `zipUrlFor(run_id): string`.
**Test PRIMERO (TDD, vitest):** `frontend/src/components/dbcompare/__tests__/migrationPanelLogic.test.ts` — `selectableRuns` filtra solo done; `zipUrlFor` arma la URL correcta.
Comando:
```
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/migrationPanelLogic.test.ts
```
**Criterio BINARIO:** vitest verde + `tsc --noEmit` 0. Visual (F7): panel visible sin pegar run_id; click en corrida done muestra scripts.
**Flag:** `STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED`. Con OFF, se conserva el bloque actual de "pegá el run_id" (backward-compatible).
**Impacto por runtime:** idéntico. Fallback: input manual de run_id (comportamiento de `main`).
**Trabajo del operador:** ninguno.

---

### F7 — Integración, smoke y Definición de Hecho

**Objetivo (1 frase):** verificar el flujo end-to-end y dejar la regresión dentro del arnés.
**Archivos a editar:** `backend/scripts/run_harness_tests.sh` + `.ps1` (confirmar que los 4 tests backend de este plan están en `HARNESS_TEST_FILES`).
**Pasos:**
1. Backend: correr los 4 archivos de test del plan (F0-F3) por archivo con el venv real; pegar el output.
2. Frontend: `npx vitest run` de los 4 archivos nuevos + `npx tsc --noEmit`.
3. Smoke manual (documentado, human-in-the-loop): con las 3 flags ON, en la UI del Comparador: (i) estado vacío muestra CTA; (ii) modo "Pegar datasource" crea un ambiente `test-sqlite` con un datasource de prueba; (iii) modo "web.config" sobre un `web.config` de ejemplo detecta ≥1 conexión con password `••••`; (iv) el Panel de Migración lista una corrida done y descarga el zip. Con las 3 flags OFF: la página es idéntica a `main`.
4. Ratchet: `test_harness_ratchet_meta.py` verde.
**Criterio BINARIO:** todos los tests de F0-F6 verdes por archivo + `tsc` 0 + ratchet meta verde. El smoke manual (3) queda como checklist para el operador (no bloquea el merge de código, pero se documenta su resultado).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| 1 | Fuga de credencial (log/UI/disco/red) | F3 dedicada con 6 tests binarios (a-e); parser puro sin red/LLM; keyring; `mask_excerpt`; detector de egreso. |
| 2 | Parser falla con un `web.config` real raro | `parse_webconfig` degrada a `[]` sin crashear; modo Manual siempre disponible; el operador ve y edita el preview antes de confirmar (HITL). |
| 3 | Colisión conceptual con el tab "Migrador" (ADO→GitLab) | Nombre distinto ("Migración de BD"), Glosario explícito, no se toca `MigratorPage.tsx` ni su flag. |
| 4 | `keyring` no instalado | Degradación 503 existente (`api/db_compare.py:120-127`); ambiente se crea, password se setea manual luego. |
| 5 | Cache de password en memoria con TTL retiene secreto | `pop_parsed` descarta al confirmar; `sweep_expired` (TTL 600s); proceso local mono-operador; nunca persiste a disco. |
| 6 | Regresión silenciosa del comparador (sus tests no estaban en el ratchet) | F0/F7 agregan los 4 tests nuevos a `HARNESS_TEST_FILES`. |
| 7 | Datos productivos con PII en diff de datos (Plan 126) | Fuera de scope de este plan; se deja anotado para un plan futuro de masking de PII en el export de datos. |

## 6. Fuera de scope

- Ejecutar scripts contra una BD (doctrina serie 122-126: Stacky genera, nunca ejecuta).
- Masking de PII en el diff de DATOS del Plan 126 (solo se anota como riesgo #7).
- Unificar el registro de ambientes de BD con el de servidores DevOps (`server_registry.py`) — son modelos distintos a propósito.
- Comparación cross-engine (fuera de scope de toda la serie).
- Soporte de formatos de config distintos de `web.config`/`.xml`/.NET connection strings (p.ej. `appsettings.json`, `.env`) — extensión futura; el parser queda con punto de extensión pero este plan solo entrega XML/.NET.

## 7. Glosario + Orden de implementación + DoD

**Glosario (términos del dominio que un modelo menor podría no conocer):**
- **Ambiente (del Comparador):** una conexión de BD nombrada (alias) registrada en `data_dir()/db_compare/environments.json`; password en keyring. Distinto del "servidor DevOps" (`server_registry.py`).
- **datasource / connection string:** string tipo `Server=host,1433;Database=RS;User ID=u;Password=p;` (SQL Server) o EZConnect Oracle `host:1521/ORCL`.
- **web.config / XMLConfig.xml:** archivo de configuración .NET del producto RS que contiene, en `<connectionStrings>`, las credenciales de conexión.
- **Agente local:** aquí = módulo Python del backend (`dbcompare_config_import.py`) que parsea el archivo **en el proceso local**, sin LLM ni red. No es un agente de runtime (Codex/Claude/Copilot).
- **keyring:** Administrador de credenciales de Windows; guarda passwords cifradas (patrón `KEYRING_SERVICE_DBCOMPARE`).
- **Migración de BD (este plan):** generación de scripts de paridad + backups (Plan 125) para llevar una BD al estado de otra. NO es el "Migrador" ADO→GitLab (Plan 74).
- **Master flag:** `STACKY_DB_COMPARE_ENABLED` (ya ON); las flags de este plan cuelgan de ella vía `requires`.
- **Ratchet de tests:** `HARNESS_TEST_FILES` en `run_harness_tests.sh`, lista que solo crece; un test nuevo debe registrarse ahí.

**Orden de implementación (numerado, por dependencia):**
1. F0 (flags + config + registro ratchet).
2. F1 (parser puro backend).
3. F2 (endpoints import/confirm).
4. F3 (guardarraíles de secretos + tests).
5. F4 (wizard guiado frontend).
6. F5 (elevar gestión de ambientes).
7. F6 (Panel de Migración de BD).
8. F7 (integración + smoke + DoD).

**Definición de Hecho (DoD) global:**
- Las 3 flags existen, default ON, categorizadas en `comparador_bd`, con arista `requires` congelada; `test_requires_map_is_frozen` y `test_every_registry_flag_is_categorized` verdes.
- Parser F1 con `masked_raw` sin secreto y password fuera de `ParsedConnection`.
- Endpoints import/confirm: 403 con flag OFF; previews sin password; confirm setea keyring; logs sin secreto (tests F2/F3 verdes).
- Wizard con modos A/B/C, banner de credenciales, input password `type="password"`.
- Gestión de ambientes visible arriba con CTA de estado vacío.
- Panel de Migración de BD persistente, con selector de corridas y descarga de bundle, sin pegar run_id.
- Con las 3 flags OFF, la UI y la API son idénticas a `main` (backward-compatible).
- Los 4 tests backend nuevos están en `HARNESS_TEST_FILES`; ratchet meta verde. `tsc --noEmit` 0. Vitest de los 4 archivos nuevos verde.
- Ninguna credencial en claro en logs, disco (`environments.json`) ni respuestas HTTP.
