# Plan 200 — Consola por incidencia + marcado de despliegue SQL + ejecucion HITL por ambiente + bitacora de trazabilidad

- **Version:** v1 (PROPUESTO — pendiente de `criticar-y-mejorar-plan`)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8)
- **Serie:** Incidencias + DB Compare (une el ciclo de incidencias 131/166/177 con el comparador de BD 122-128/178-184 y la receta de bitacora del 198)
- **Runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro — paridad total (backend + UI puros; el unico punto sensible al runtime es el transcript, que degrada al log crudo — ver F2).

> **Nota de arranque para el modelo implementador (leer antes de tocar nada).** Este
> documento cita simbolos y `archivo:linea` verificados el 2026-07-18 en la rama
> `docs/plan-166-ciclo-incidencias`. **Confirma cada `archivo:linea` con grep/lectura
> antes de editar** (las lineas pueden haberse corrido). Dos aclaraciones criticas que ya
> se verificaron y que NO debes revertir por inercia:
> 1. **`services/secret_masking.py` NO existe en esta rama** (grep vacio). Los planes 181/188/195
>    lo nombran, pero aca el masking REAL a reusar es `dbcompare_engine._scrub(msg, password)`
>    (`services/dbcompare_engine.py:80`), `dbcompare_config_import._mask` + `preview_dict`
>    (`services/dbcompare_config_import.py:114/193`) y `services/pii_masker.py`. **No crees un
>    modulo `secret_masking` nuevo**; reusa estos.
> 2. **`services/env_apply_ledger.py` (plan 198) NO existe en esta rama** (grep vacio: solo esta
>    su DOC en `docs/198_PLAN_*.md`). La RECETA de ledger JSONL append-only esta CONGELADA en ese
>    doc (F0) y este plan la CALCA. Los ledgers que SI existen aca son `services/publish_ledger.py`
>    y `services/ado_edit_ledger.py` (variante tabla SQL); para el ledger JSONL de R4 seguimos la
>    receta del 198, no la de tabla.

---

## 1. Titulo, objetivo y KPI

**Objetivo (1 parrafo).** Cerrar el ciclo operativo "incidencia -> fix con SQL -> despliegue verificado
por ambiente" con cuatro capacidades que hoy no existen o estan desconectadas: (R1) desde CADA
incidencia, **recuperar la consola/transcript de lo que respondio el agente**; (R2) que CADA ticket
y CADA incidencia **avisen con un badge cuando implican desplegar scripts SQL en otros ambientes**,
listando que scripts y sugiriendo en que ambientes; (R3) en la seccion de BD, por ticket/incidencia,
**un boton para ejecutar cada script SQL en el ambiente que el operador elija** (la capacidad mas
peligrosa del producto: corre DDL/DML contra una BD real, por eso va detras de flag OFF + HITL por
corrida); y (R4) una **bitacora append-only, tamper-evident, de que scripts ya se ejecutaron en cada
ambiente** (cuando, resultado, filas afectadas, que corrida), para no re-ejecutar a ciegas y ver el
estado por ambiente. Todo reusa sustrato existente: la consola de ejecuciones (`api/executions.py` +
`log_streamer.py`), el linkage incidencia->ejecucion que ya persiste el store (`incident_store.py`),
el motor de conexion por alias del comparador (`dbcompare_engine.open_engine`), el registro de
ambientes (`dbcompare_registry`), el masking real (`_scrub` / `pii_masker`) y la receta de ledger
del 198.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Criterio binario |
|-----|------------------|
| KPI-1 (R1) | Incidencia con ejecucion de analisis Y de dev-resolutor linkeadas -> `GET /api/incidents/<id>/console` devuelve AMBOS `execution_id` con su `kind`; con `STACKY_INCIDENT_CONSOLE_ENABLED` OFF -> 404. El front pinta el transcript reusando `GET /api/executions/<id>/logs` (sin endpoint de transcript nuevo). |
| KPI-2 (R2) | `detect_for_incident` sobre una incidencia con adjunto `.sql` -> `requires=True`, lista exacta de scripts (`name`+`sha256`) y `suggested_environments == aliases registrados`; sin `.sql` ni keywords -> `requires=False`. `detect_for_ticket` con un `.sql` en `Output/tickets/<ado_id>/` -> `requires=True`. Determinista (misma entrada, misma salida). |
| KPI-3 (R3) | `execute_script`: flag `STACKY_SQL_EXEC_ENABLED` OFF -> 404; ambiente sin `exec_allowed` -> 403; `dry_run=True` -> devuelve plan de statements y NO muta; ejecucion real contra sqlite sandbox con `confirm=True` + `fingerprint` correcto -> `rows_affected` + commit; `fingerprint` incorrecto -> 409; el password JAMAS aparece en `output`/`error` (assert sobre el string). |
| KPI-4 (R4) | Tras 1 ejecucion real -> 1 entry en `sql_exec_ledger.jsonl` con cadena de hash valida; `find_executed(alias, sha)` la encuentra; re-ejecutar el mismo `sha` sin `force=True` -> bloqueo "ya ejecutado"; `verify_chain()` True; alterar 1 linea -> `verify_chain()` False; `list_execs` DESC por `executed_at`, filtra por `alias`/`ticket_ref`; 301 appends -> quedan 300. |
| KPI-5 (UI) | Helpers puros de R1/R2/R3/R4 testeados en vitest POR ARCHIVO + `npx tsc --noEmit` sin errores nuevos; ratchet UI sin `style={{}}` nuevos. |

**Ganancia robusta:** el operador deja de tener incidencias "ciegas" (no sabe que respondio el agente),
deja de descubrir a mano que un cambio implica tocar BD en otros ambientes, ejecuta el SQL con un click
guardado en el ambiente correcto, y nunca re-corre un script ya aplicado. Cierra el hueco entre
"el agente propuso un fix" y "el fix quedo desplegado y auditado por ambiente".

**Onboarding casi nulo:** R1/R2/R4 son read-only y aparecen solos dentro de las pantallas existentes
(detalle de incidencia, board de tickets, seccion BD) con flags default ON; R3 es el unico opt-in
(flag OFF) y ademas exige confirmacion humana por corrida.

---

## 2. Por que ahora / gap que cierra

Evidencia del estado actual (verificada en el repo, 2026-07-18):

- **R1 — la consola por incidencia NO se ofrece hoy.** El linkage YA existe a medias:
  `incident_store.create_incident` inicializa `"execution_id": None` (`services/incident_store.py:165`),
  `api/agents.py:1053` lo setea al lanzar el **agente de analisis**
  (`incident_store.update_incident(incident_id, status="analizando", execution_id=execution_id)`), y
  `incident_store.find_by_execution` (`services/incident_store.py:237`) permite el camino inverso.
  PERO: (a) el **dev-resolutor** (`agents/incident_dev.py`, plan 166/177) NO linkea su ejecucion a la
  incidencia (grep de `execution_id` en `agents/incident_dev.py` y `services/incident_dev_context.py`
  = 0 matches), y (b) el detalle de incidencia en el front (`components/IncidentResolverModal.tsx`) no
  tiene ninguna vista que muestre el transcript. La consola de ejecuciones existe y es reusable:
  `GET /executions/<id>/logs` (`api/executions.py:168`), `GET /executions/<id>/logs/stream`
  (`api/executions.py:202`), respaldados por `log_streamer.snapshot` (`log_streamer.py:123`) que cae a
  la tabla `execution_logs` cuando el buffer in-memory ya se cerro. **Gap R1:** conectar TODAS las
  ejecuciones de una incidencia y exponerlas en su detalle.

- **R2 — no hay marcado de "esto implica desplegar SQL en otros ambientes".** El intake ya clasifica
  adjuntos y `TEXT_EXTENSIONS` incluye `.sql` (`services/incident_store.py:28`); cada file guarda
  `ext`, `kind` y `sha256` (`:149-156`). Los tickets guardan artefactos en `Output/tickets/<ado_id>/`
  (resoluble con `_resolve_ticket_output_dir_ws1`, `api/executions.py:643`). Nada consume esto para
  avisar "hay scripts SQL para desplegar". El puente `RepoScriptIndex` del plan 180 es **solo-doc**
  (no implementado). **Gap R2:** un detector determinista sobre adjuntos/outputs `.sql` + keywords.

- **R3 — no existe ejecucion de SQL de escritura.** Lo unico que corre SQL hoy es `live_db.execute_select`
  (`services/live_db.py:67`), **read-only por diseno** (rechaza INSERT/UPDATE/DELETE/DDL,
  `_validate_query` `:56`). El comparador conecta a ambientes por alias con
  `dbcompare_engine.open_engine(alias)` (`services/dbcompare_engine.py:88`), resolviendo credenciales
  con `dbcompare_registry.get_credential` (`services/dbcompare_registry.py:203`) sobre el registro
  `data_dir()/db_compare/environments.json` (`dbcompare_registry.py:27`). El patron HITL mas fuerte de
  la casa (confirm + fingerprint) esta en `api/devops.py:271` (`environment_apply_route`). **Gap R3:**
  un ejecutor de escritura, detras de flag OFF, que reuse `open_engine` + el patron HITL + masking.

- **R4 — no hay traza de que se ejecuto en cada ambiente.** La tríada de efectos remotos con registro
  la cerro el 198 para "applies de carpetas" (deploys 120 y CI 191 ya tenian ledger). La BD queda sin
  bitacora de ejecucion. La RECETA de ledger JSONL append-only esta CONGELADA en `docs/198_PLAN_*.md`
  (F0). **Gap R4:** un ledger JSONL tamper-evident de ejecuciones SQL por ambiente + chequeo de
  idempotencia.

**Por que ahora:** los cuatro huecos son el mismo flujo partido en cuatro. Con 166 (ciclo de
incidencias) y 177 (auto-PR del dev-resolutor) ya implementados, el operador tiene el fix pero no
puede (a) ver que respondio el agente, (b) saber que tiene que ir a BD, (c) ejecutarlo con control, ni
(d) auditarlo. Este plan los une reusando todo el sustrato, sin reinventar nada.

**Vecinos que NO se pisan:** 131/166/177 (incidencias — este plan SOLO agrega lectura + linkage),
122-128 (comparador — se reusa `open_engine`/`dbcompare_registry`, no se cambia su semantica de
comparacion), 157 (import de web.config — se reusa su masking), 178-184 (DB Compare avanzado — otro
dominio), 198 (applies de carpetas — se calca su receta de ledger, otro dominio).

---

## 3. Principios y guardarrailes (no negociables)

1. **Paridad de 3 runtimes por construccion.** R1/R2/R3/R4 son backend + UI sin LLM. El unico punto
   sensible al runtime es el **contenido del transcript** (R1): los eventos los empujan todos los
   runtimes via `logger_for`/`on_log` a `log_streamer`; si un runtime no produjo eventos estructurados,
   `snapshot` cae a la tabla `execution_logs` (log crudo). **Fallback explicito:** consola siempre
   disponible; si no hay eventos ricos, se muestra el log crudo. Nada atado a Codex/Claude/Copilot.
2. **Cero trabajo extra al operador.**
   - R1 (`STACKY_INCIDENT_CONSOLE_ENABLED`): read-only -> **default ON**.
   - R2 (`STACKY_SQL_DEPLOY_DETECT_ENABLED`): read-only (deteccion + badge) -> **default ON**.
   - R4 (`STACKY_SQL_EXEC_LEDGER_ENABLED`): append-only, no ejecuta nada, la vista de traza es
     read-only -> **default ON**.
   - R3 (`STACKY_SQL_EXEC_ENABLED`): **default OFF**, citando **EXCEPCION 2** (accion
     destructiva/irreversible: correr DDL/DML contra una BD real) **y EXCEPCION 3** (prerequisito no
     garantizado: las credenciales/conexion a ambientes no-default NO vienen en la instalacion
     default). Ademas **HITL por corrida** (confirm + fingerprint del SQL exacto): el flag ON no basta.
3. **Human-in-the-loop innegociable (R3).** El operador dispara cada ejecucion con boton + confirm;
   jamas hay auto-ejecucion. Amplificar, no reemplazar.
4. **Mono-operador sin auth real.** Nada de RBAC/roles. `executed_by` es el `current_user()` header sin
   validar (solo para la traza, no como control de acceso).
5. **No degradar.** Backward-compatible: campos aditivos en `intake.json` (`executions` nuevo,
   `execution_id` intacto), endpoints nuevos, flags. El apply/compare/ciclo de incidencias existentes
   responden byte-identico con las flags nuevas OFF.
6. **Reusar, no reinventar.** `log_streamer`/`api/executions` (consola), `incident_store` (linkage),
   `dbcompare_engine.open_engine` + `dbcompare_registry` (conexion/ambientes), `_scrub`/`pii_masker`
   (masking), receta de ledger del 198 (R4).
7. **Gotchas de la casa (encodados por fase):** flag ON requiere wiring en 5 lugares
   (FlagSpec `default=True` + `_CATEGORY_KEYS` + `config.py` + `_CURATED_DEFAULTS_ON` + arista en
   `_REQUIRES_MAP_FROZEN`); flag OFF NO va en `_CURATED_DEFAULTS_ON` pero SI en `_CATEGORY_KEYS` +
   `config.py` + arista requires; usar `config.config` (instancia), nunca `getattr` del modulo;
   registrar cada `test_*.py` nuevo en `HARNESS_TEST_FILES` (`scripts/run_harness_tests.sh`); tests
   backend POR ARCHIVO con `.venv` py3.13; front vitest POR ARCHIVO sin `@testing-library`/`jsdom`
   (solo funciones puras); ratchet UI sin `style={{}}` nuevos; egress sentinel dispara ante
   `password=<4+ chars>` (`dbcompare_config_import.py:196`) -> ninguna salida puede contener eso.

---

## 4. Fases

> **Entorno de ejecucion (todas las fases).** Backend: cwd `Stacky Agents\backend`, interprete
> `.venv\Scripts\python.exe` (py3.13; **nunca** `venv\`). Front: cwd `Stacky Agents\frontend`,
> `npx vitest run <archivo>` + `npx tsc --noEmit`. Cada fase se commitea sola con sus tests verdes
> antes de la siguiente.

---

### F0 — Flags + superficie de config UI + contrato de reuso de masking

**Objetivo (1 frase):** declarar las 4 flags (3 ON read-only, 1 OFF ejecucion) bien cableadas y fijar
por escrito que masking se reusa, sin tocar comportamiento aun.
**Valor:** sustrato de configuracion; todo lo demas se gatea contra estas flags.

**Archivos a EDITAR:**
- `Stacky Agents\backend\services\harness_flags.py` (4 `FlagSpec` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` + `_REQUIRES_MAP_FROZEN`)
- `Stacky Agents\backend\config.py` (4 atributos con su default efectivo)
- `Stacky Agents\backend\tests\test_harness_flags_requires.py` (4 aristas requires)
- `Stacky Agents\backend\scripts\run_harness_tests.sh` (registrar el test nuevo)

**Archivo a CREAR:**
- `Stacky Agents\backend\tests\test_plan200_flags.py`

**Cambios exactos:**

1. En `harness_flags.py`, 4 `FlagSpec` nuevos (ubicarlos: los 2 de incidencias junto al bloque
   `STACKY_INCIDENT_*`; los 2 de BD junto al bloque `STACKY_DB_COMPARE_*`, ~`:3163`). Copiar el estilo
   EXACTO de un FlagSpec vecino de cada bloque. Valores:

```python
# --- R1: consola por incidencia (read-only) ---
FlagSpec(
    key="STACKY_INCIDENT_CONSOLE_ENABLED",
    type="bool", default=True, group="global",
    label="Consola del agente por incidencia",
    description="Muestra en el detalle de cada incidencia el transcript de lo que respondio el "
                "agente (analisis y dev-resolutor). Read-only: reusa la consola de ejecuciones.",
    requires="STACKY_INCIDENT_RESOLVER_ENABLED",
),
# --- R2: marcado de despliegue SQL (read-only) ---
FlagSpec(
    key="STACKY_SQL_DEPLOY_DETECT_ENABLED",
    type="bool", default=True, group="global",
    label="Marcado de despliegue SQL en tickets e incidencias",
    description="Detecta de forma determinista cuando un ticket o incidencia implica desplegar "
                "scripts SQL en otros ambientes y lo avisa con un badge. Read-only.",
    requires="STACKY_INCIDENT_RESOLVER_ENABLED",
),
# --- R4: bitacora de ejecuciones SQL (append-only, read-only para el operador) ---
FlagSpec(
    key="STACKY_SQL_EXEC_LEDGER_ENABLED",
    type="bool", default=True, group="global",
    label="Bitacora de ejecuciones SQL por ambiente",
    description="Registra localmente cada ejecucion SQL (que script, en que ambiente, cuando, "
                "resultado) con cadena de hash, y avisa si un script ya se ejecuto. Solo metadata "
                "local; sin connection strings.",
    requires="STACKY_DB_COMPARE_ENABLED",
),
# --- R3: ejecucion SQL contra un ambiente real (DEFAULT OFF — excepciones 2 y 3) ---
FlagSpec(
    key="STACKY_SQL_EXEC_ENABLED",
    type="bool", default=False, group="global",
    label="Ejecutar scripts SQL en ambientes (PELIGROSO)",
    description="Habilita ejecutar DDL/DML contra una BD real desde Stacky. OFF por default: es una "
                "accion destructiva/irreversible y requiere credenciales de ambientes que no vienen "
                "en la instalacion default. Cada ejecucion exige confirmacion humana explicita.",
    requires="STACKY_DB_COMPARE_ENABLED",
),
```

2. `_CATEGORY_KEYS`: agregar las **4** keys (todas categorizadas o `test_every_registry_flag_is_categorized`
   se pone rojo). `_CURATED_DEFAULTS_ON`: agregar SOLO las **3** keys ON
   (`STACKY_INCIDENT_CONSOLE_ENABLED`, `STACKY_SQL_DEPLOY_DETECT_ENABLED`, `STACKY_SQL_EXEC_LEDGER_ENABLED`);
   **NO** agregar `STACKY_SQL_EXEC_ENABLED` (default OFF: agregarla romperia
   `test_default_known_only_for_curated`). `_REQUIRES_MAP_FROZEN`: agregar las **4** aristas
   (profundidad 1) exactamente como el `requires=` de cada FlagSpec.

3. `config.py`: agregar los 4 atributos con su default efectivo (`True`x3, `False`x1), copiando el
   patron de un flag vecino ya presente (grep `STACKY_DB_COMPARE_DATA_DIFF_ENABLED` en `config.py` y
   espejar).

4. `test_harness_flags_requires.py`: agregar las 4 aristas al set esperado del test.

**Contrato de reuso de masking (documentar en el docstring del modulo de F5 y F6, no en codigo suelto):**
- Scrub de password conocido en strings de error/salida -> `dbcompare_engine._scrub(text, password)`.
- Redaccion de connection strings / campos sensibles -> `dbcompare_config_import._mask` +
  `preview_dict` (dict seguro sin password) + `SENSITIVE_KEYS`.
- PII en filas de resultado -> `services.pii_masker` (mismo uso que `live_db.py:24`).
- **Prohibido** crear un modulo `secret_masking` nuevo.

**Tests PRIMERO — `tests\test_plan200_flags.py`:**
- `test_r1_r2_r4_declaradas_default_on` — las 3 flags existen, `type=="bool"`, `default is True`.
- `test_r3_declarada_default_off` — `STACKY_SQL_EXEC_ENABLED` existe, `default is False`.
- `test_r1_r2_r4_en_curated_on` — las 3 ON estan en `_CURATED_DEFAULTS_ON`.
- `test_r3_no_en_curated_on` — la OFF NO esta en `_CURATED_DEFAULTS_ON`.
- `test_cuatro_categorizadas` — las 4 estan en `_CATEGORY_KEYS`.
- `test_cuatro_aristas_requires` — las 4 aristas estan en `_REQUIRES_MAP_FROZEN` con el parent correcto.
- Registrar `test_plan200_flags.py` en `HARNESS_TEST_FILES`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan200_flags.py -q`
(cwd `Stacky Agents\backend`).

**Criterio de aceptacion (binario):** los 6 tests pasan Y
`.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py tests\test_harness_flags_requires.py -q`
verde (curated + requires + categorizacion sin regresion).

**Flag que protege:** ella misma (esta fase declara las flags).
**Impacto por runtime:** identico en los 3 (config pura). **Fallback:** N/A.
**Trabajo del operador:** ninguno (las 3 ON aparecen activas; la OFF queda visible/toggleable en la
UI de flags para cuando quiera habilitar ejecucion).

---

### F1 — Backend: asociar incidencia<->TODAS sus ejecuciones + endpoint de consola (R1)

**Objetivo (1 frase):** que cada incidencia conozca todas sus ejecuciones (analisis + dev-resolutor) y
exponerlas para recuperar el transcript.
**Valor:** habilita R1 reusando la consola de ejecuciones existente (cero endpoint de transcript nuevo).

**Archivos a EDITAR:**
- `Stacky Agents\backend\services\incident_store.py` (helper `add_execution` + campo `executions`)
- `Stacky Agents\backend\api\agents.py` (~`:1053`, tambien registrar en la lista `executions`)
- El call-site del **dev-resolutor** (localizar con: `grep -rn "STACKY_INCIDENT_DEV_RESOLVER_ENABLED"
  backend/api backend/services` y `grep -rn "incident_dev" backend/api` — es el handler del boton
  "Resolver con agente", plan 166 F5 / plan 177) para linkear su `execution_id` a la incidencia
- `Stacky Agents\backend\api\incidents.py` (endpoint nuevo `GET /<incident_id>/console`)
- `Stacky Agents\backend\scripts\run_harness_tests.sh`

**Archivo a CREAR:**
- `Stacky Agents\backend\tests\test_plan200_incident_console.py`

**Cambios exactos:**

1. En `incident_store.py`, helper aditivo (NO rompe `create_incident`/`update_incident`; `executions`
   se inicializa lazily):

```python
def add_execution(incident_id: str, execution_id: int, kind: str) -> dict:
    """Plan 200 R1 — agrega (idempotente) una ejecucion linkeada a la incidencia.
    kind in {"analysis", "dev_resolver"}. Mantiene `execution_id` (el de analisis)
    intacto para back-compat; `executions` es la lista completa."""
    incident = get_incident(incident_id)
    if incident is None:
        raise ValueError(f"incident_not_found:{incident_id}")
    execs = list(incident.get("executions") or [])
    if not any(int(e.get("execution_id", -1)) == int(execution_id) for e in execs):
        execs.append({
            "execution_id": int(execution_id),
            "kind": kind,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        })
    return update_incident(incident_id, executions=execs)
```

2. En `api/agents.py:1053`, JUSTO despues del `update_incident(..., execution_id=execution_id)`
   existente, agregar `incident_store.add_execution(incident_id, execution_id, kind="analysis")`
   (mantener el `update_incident` de `execution_id` para back-compat).

3. En el call-site del dev-resolutor: tras crear la ejecucion del dev-resolutor y tener su
   `execution_id`, llamar `incident_store.add_execution(incident_id, execution_id, kind="dev_resolver")`.
   Si ese call-site no conoce el `incident_id` (porque hoy el dev-resolutor arranca desde un ticket),
   resolverlo por el `ticket_id`/`tracker_id` de la incidencia (buscar en el ledger la incidencia cuyo
   `tracker_id` coincide) — implementar `incident_store.find_by_tracker_id(tracker_id) -> dict | None`
   (mismo patron O(n) que `find_by_execution`, `services/incident_store.py:237`). Si no hay incidencia
   asociada, no-op silencioso (un dev-resolutor lanzado sobre un ticket sin incidencia no linkea nada).

4. En `api/incidents.py`, endpoint read-only (calcar el guard de las rutas existentes, `:96-98`):

```python
@bp.get("/<incident_id>/console")
def get_incident_console(incident_id: str):
    from config import config as _cfg
    if not _cfg.STACKY_INCIDENT_RESOLVER_ENABLED:
        return _feature_disabled_response()
    if not getattr(_cfg, "STACKY_INCIDENT_CONSOLE_ENABLED", True):
        return _feature_disabled_response()
    from services import incident_store
    incident = incident_store.get_incident(incident_id)
    if incident is None:
        return jsonify({"ok": False, "error": "not_found"}), 404
    execs = list(incident.get("executions") or [])
    # back-compat: si solo hay `execution_id` legacy y no `executions`, sintetizar la lista.
    if not execs and incident.get("execution_id") is not None:
        execs = [{"execution_id": int(incident["execution_id"]), "kind": "analysis", "linked_at": None}]
    return jsonify({
        "ok": True,
        "incident_id": incident_id,
        "primary_execution_id": incident.get("execution_id"),
        "executions": execs,  # el front pide /api/executions/<id>/logs por cada uno
    })
```

**Tests PRIMERO — `tests\test_plan200_incident_console.py`** (monkeypatch `runtime_paths.data_dir` a
`tmp_path`; usar Flask test client de la app o llamar el store directo, espejando
`tests\test_plan131_incident_store.py`):
- `test_add_execution_idempotente` — 2 llamadas con el mismo `execution_id` -> 1 sola entrada.
- `test_add_execution_dos_kinds` — analysis + dev_resolver -> lista de 2, `execution_id` legacy intacto.
- `test_console_endpoint_lista_executions` — endpoint devuelve ambas.
- `test_console_backcompat_solo_legacy` — incidencia con `execution_id` y sin `executions` ->
  endpoint sintetiza 1 entry `kind="analysis"`.
- `test_console_404_flag_off` — `STACKY_INCIDENT_CONSOLE_ENABLED` OFF -> 404 `feature_disabled`.
- `test_console_404_incidente_inexistente`.
- Registrar en `HARNESS_TEST_FILES`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan200_incident_console.py -q`

**Criterio de aceptacion (binario):** los 6 tests pasan; `grep -n "add_execution" backend/api/agents.py`
devuelve el call-site nuevo; el linkage del dev-resolutor existe (grep del `add_execution` con
`kind="dev_resolver"` en el call-site localizado).

**Flag que protege:** `STACKY_INCIDENT_CONSOLE_ENABLED` (default ON) + master `STACKY_INCIDENT_RESOLVER_ENABLED`.
**Impacto por runtime:** identico; el `execution_id` se guarda igual sea codex/claude/copilot.
**Fallback:** flag OFF -> 404 y el front no muestra la pestana.
**Trabajo del operador:** ninguno.

---

### F2 — Frontend: pestana "Consola del agente" en el detalle de incidencia (R1)

**Objetivo (1 frase):** ver el transcript de cada ejecucion de la incidencia dentro de su detalle.
**Valor:** materializa R1 para el operador.

**Archivos a CREAR:**
- `Stacky Agents\frontend\src\components\incidentConsole.ts` (helpers puros)
- `Stacky Agents\frontend\src\components\incidentConsole.test.ts`

**Archivo a EDITAR:**
- `Stacky Agents\frontend\src\components\IncidentResolverModal.tsx` (agregar la seccion/pestana)

**Comportamiento exacto:**

1. `incidentConsole.ts` (puro, testeable sin DOM):

```typescript
export interface IncidentExecRef { execution_id: number; kind: string; linked_at: string | null; }
export interface ConsoleResponse { ok: boolean; executions: IncidentExecRef[]; primary_execution_id: number | null; }

export function execLabel(e: IncidentExecRef): string {
  const k = e.kind === "dev_resolver" ? "Dev-resolutor" : e.kind === "analysis" ? "Analisis" : e.kind;
  return `#${e.execution_id} · ${k}`;
}
// Ordena: analysis primero, luego dev_resolver, luego por id asc. Determinista.
export function orderExecs(execs: IncidentExecRef[]): IncidentExecRef[] { /* ... */ }
// Shape para render de una linea de log (reusa el contrato de /api/executions/<id>/logs).
export function logLineText(ev: { timestamp?: string; level?: string; message?: string }): string { /* ... */ }
```

2. En `IncidentResolverModal.tsx`: cuando la incidencia esta abierta y tiene ejecuciones, agregar una
   pestana/`<details>` "Consola del agente" que:
   - hace `GET /api/incidents/<id>/console` (404 -> no renderiza nada; flag OFF o sin ejecuciones);
   - lista las ejecuciones con `execLabel` (ordenadas con `orderExecs`);
   - al seleccionar una, hace `GET /api/executions/<execution_id>/logs` (endpoint EXISTENTE,
     `api/executions.py:168`) y pinta las lineas con `logLineText`;
   - **fallback de runtime:** si `logs` viene vacio o sin `message` estructurado, mostrar el aviso
     "Transcript no estructurado para este runtime — mostrando log crudo" y volcar tal cual lo que
     devuelva `snapshot`. (No hay endpoint nuevo: si mas adelante se quiere streaming en vivo, reusar
     `GET /api/executions/<id>/logs/stream`, `api/executions.py:202`.)
   - Clases del CSS module existente del modal (**gotcha ratchet:** sin `style={{}}` nuevos).

**Tests PRIMERO — `incidentConsole.test.ts`** (vitest, sin `@testing-library`):
- `execLabel` — mapea analysis/dev_resolver/otro correctamente.
- `orderExecs` — analysis antes que dev_resolver; dentro del mismo kind, id asc; entrada vacia -> [].
- `logLineText` — arma la linea con timestamp+level+message; tolera campos faltantes.

**Comando:** `npx vitest run src/components/incidentConsole.test.ts` (cwd `Stacky Agents\frontend`).

**Criterio de aceptacion (binario):** los 3 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Flag que protege:** `STACKY_INCIDENT_CONSOLE_ENABLED` (404 -> modal identico a hoy).
**Impacto por runtime:** UI pura; el fallback de log crudo cubre el runtime que no emita eventos ricos.
**Trabajo del operador:** ninguno.

---

### F3 — Backend: detector determinista de "requiere despliegue SQL en ambientes" (R2)

**Objetivo (1 frase):** dado un ticket o incidencia, decidir de forma determinista si implica desplegar
scripts SQL y listar cuales + en que ambientes sugeridos.
**Valor:** habilita el badge de R2 sin heuristica difusa.

**Archivos a CREAR:**
- `Stacky Agents\backend\services\sql_deploy_detector.py`
- `Stacky Agents\backend\tests\test_plan200_sql_deploy_detector.py`

**Archivos a EDITAR:**
- `Stacky Agents\backend\api\incidents.py` (endpoint `GET /<incident_id>/sql-deploy`)
- `Stacky Agents\backend\api\tickets.py` (endpoint `GET /tickets/<ticket_id>/sql-deploy` — ubicar junto
  a las rutas de ticket existentes; confirmar el `url_prefix` real del blueprint de tickets con grep)
- `Stacky Agents\backend\scripts\run_harness_tests.sh`

**Contrato del detector (`sql_deploy_detector.py`, PURO y determinista):**

```python
from dataclasses import dataclass, field

_DEPLOY_KEYWORDS = (  # deteccion de intencion en texto (case-insensitive, palabra completa)
    r"desplegar", r"despliegue", r"deploy", r"ambiente", r"entorno",
    r"producci[oó]n", r"\bQA\b", r"\bUAT\b", r"staging", r"script\s+SQL",
)

@dataclass
class DeployNeed:
    requires: bool
    confidence: str                 # "alta" (hay .sql) | "posible" (solo keywords) | "no"
    scripts: list = field(default_factory=list)   # [{"name","sha256","source"}]
    suggested_environments: list = field(default_factory=list)  # aliases de dbcompare_registry
    reason: str = ""

def _suggested_envs() -> list[str]:
    from services import dbcompare_registry
    return [e["alias"] for e in dbcompare_registry.list_environments()]

def detect_for_incident(incident: dict) -> DeployNeed:
    # 1) adjuntos .sql del intake (incident["files"] con ext==".sql", ya trae name+sha256).
    # 2) señal debil: keywords en incident["text"].
    # requires = (hay .sql) OR (keywords). confidence = "alta" si hay .sql, "posible" si solo keywords.
    ...

def detect_for_ticket(ticket, output_dir) -> DeployNeed:
    # 1) *.sql bajo output_dir (Output/tickets/<ado_id>/, resuelto por el caller con
    #    _resolve_ticket_output_dir_ws1); sha256 leido del archivo.
    # 2) keywords en ticket.title + ticket.description.
    ...
```

Reglas duras (nada difuso):
- `.sql` presente -> `requires=True`, `confidence="alta"`. Solo keywords -> `requires=True`,
  `confidence="posible"`. Ninguno -> `requires=False`, `confidence="no"`, listas vacias.
- `scripts[i].source` = `"incident_attachment"` o `"ticket_output"`.
- `sha256` de incidencia sale del `files_meta` ya calculado (`incident_store.py:155`); el de ticket se
  computa leyendo el archivo (`hashlib.sha256`).
- `suggested_environments` = TODOS los aliases registrados (el operador elige; el detector no adivina el
  ambiente correcto — eso seria inventar).

**Endpoints (read-only, gated `STACKY_SQL_DEPLOY_DETECT_ENABLED`):**
- `GET /api/incidents/<incident_id>/sql-deploy` -> `jsonify(asdict(detect_for_incident(incident)))`.
- `GET /api/tickets/<ticket_id>/sql-deploy` -> resuelve el ticket + su `output_dir` con
  `_resolve_ticket_output_dir_ws1` (reusar; si no hay dir, pasar `None`) -> `detect_for_ticket`.
- Ambos: flag OFF -> 404; entidad inexistente -> 404.

**Tests PRIMERO — `tests\test_plan200_sql_deploy_detector.py`:**
- `test_incidencia_con_sql_requires_alta` — incidencia con 1 adjunto `.sql` -> `requires True`,
  `confidence "alta"`, 1 script con su `sha256`.
- `test_incidencia_solo_keywords_posible` — texto "hay que desplegar en produccion", sin `.sql` ->
  `requires True`, `confidence "posible"`, `scripts == []`.
- `test_incidencia_sin_nada_no_requiere` — sin `.sql` ni keywords -> `requires False`.
- `test_ticket_con_sql_en_output` — `.sql` en `output_dir` (tmp) -> `requires True`, `confidence "alta"`.
- `test_suggested_envs_son_los_registrados` — monkeypatch `dbcompare_registry.list_environments` con 2
  aliases -> `suggested_environments` == esos 2.
- `test_determinista` — misma entrada 2 veces -> salida identica.
- `test_endpoint_404_flag_off` (incidencia) y `test_endpoint_404_flag_off_ticket`.
- Registrar en `HARNESS_TEST_FILES`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan200_sql_deploy_detector.py -q`

**Criterio de aceptacion (binario):** los 8 tests pasan; el detector no importa red/LLM
(`grep -nE "requests|http|llm|invoke" backend/services/sql_deploy_detector.py` -> 0 matches).

**Flag que protege:** `STACKY_SQL_DEPLOY_DETECT_ENABLED` (default ON) + master de incidencias/tickets.
**Impacto por runtime:** identico (funcion pura, sin runtime).
**Trabajo del operador:** ninguno.

---

### F4 — Frontend: badge/seccion "Despliegue SQL requerido" en ticket e incidencia (R2)

**Objetivo (1 frase):** avisar visualmente, en ticket e incidencia, que hay scripts SQL para desplegar.
**Valor:** el operador ve el aviso sin leer el detalle.

**Archivos a CREAR:**
- `Stacky Agents\frontend\src\components\sqlDeployBadge.ts` (helpers puros)
- `Stacky Agents\frontend\src\components\sqlDeployBadge.test.ts`

**Archivos a EDITAR:**
- `Stacky Agents\frontend\src\components\IncidentResolverModal.tsx` (badge + seccion en el detalle de incidencia)
- `Stacky Agents\frontend\src\pages\TicketBoard.tsx` (badge en la tarjeta/detalle del ticket)

**Comportamiento exacto:**

1. `sqlDeployBadge.ts` (puro):

```typescript
export interface DeployNeed {
  requires: boolean; confidence: "alta" | "posible" | "no";
  scripts: { name: string; sha256: string; source: string }[];
  suggested_environments: string[]; reason: string;
}
export function badge(need: DeployNeed): { show: boolean; tone: "warn" | "info"; text: string } {
  if (!need.requires) return { show: false, tone: "info", text: "" };
  return need.confidence === "alta"
    ? { show: true, tone: "warn", text: `Despliegue SQL requerido — ${need.scripts.length} script(s)` }
    : { show: true, tone: "info", text: "Posible despliegue SQL (revisar)" };
}
export function scriptsSummary(need: DeployNeed): string { /* "a.sql, b.sql en QA, PROD" o "" */ }
```

2. Incidencia (`IncidentResolverModal.tsx`) y ticket (`TicketBoard.tsx`): al abrir el detalle, hacer
   `GET /api/incidents/<id>/sql-deploy` o `GET /api/tickets/<id>/sql-deploy`; si `badge(need).show`,
   pintar el badge (tono `warn`/`info`) y, en el detalle, una seccion "Despliegue SQL requerido" que
   lista los scripts (`name`) y los `suggested_environments`. 404 -> no renderiza nada. Clases del CSS
   module existente (**gotcha ratchet:** sin `style={{}}` nuevos).
   - **Puente a R3/F7:** cada script de la lista lleva el boton "Ejecutar en ambiente" que F7 conecta.
     En F4, ese boton puede quedar deshabilitado con tooltip "Habilita STACKY_SQL_EXEC_ENABLED" si el
     status dice que R3 esta OFF (leer `enabled` del status de BD — ver F7).

**Tests PRIMERO — `sqlDeployBadge.test.ts`:**
- `badge` — `requires false` -> `show false`; `confidence "alta"` -> warn con el conteo; `"posible"` ->
  info.
- `scriptsSummary` — arma "a.sql, b.sql" + ambientes; vacio si no requiere.

**Comando:** `npx vitest run src/components/sqlDeployBadge.test.ts`

**Criterio de aceptacion (binario):** los 2 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Flag que protege:** `STACKY_SQL_DEPLOY_DETECT_ENABLED` (404 -> ticket/incidencia identicos a hoy).
**Impacto por runtime:** UI pura. **Trabajo del operador:** ninguno.

---

### F5 — Backend: motor de ejecucion de un script contra un ambiente elegido (R3, DEFAULT OFF, HITL)

**Objetivo (1 frase):** ejecutar un script SQL contra un ambiente elegido, detras de flag OFF + HITL,
con dry-run, transaccion, allow-list y masking.
**Valor:** materializa R3 — la capacidad mas peligrosa — con todas las guardas.

**Archivos a CREAR:**
- `Stacky Agents\backend\services\sql_exec_engine.py`
- `Stacky Agents\backend\tests\test_plan200_sql_exec_engine.py`

**Archivos a EDITAR:**
- `Stacky Agents\backend\services\dbcompare_registry.py` (campo opt-in `exec_allowed` por ambiente)
- `Stacky Agents\backend\api\db_compare.py` (endpoint HITL `POST /environments/<alias>/execute-script`
  + endpoint para togglear `exec_allowed`; `url_prefix="/db-compare"`, `api/db_compare.py:33`)
- `Stacky Agents\backend\scripts\run_harness_tests.sh`

**Cambios exactos:**

1. `dbcompare_registry.py`: en `upsert_environment` (`:114`) y `_public` (`:74`) sumar el campo
   `exec_allowed: bool` (default `False`). Helper `set_exec_allowed(alias: str, allowed: bool) -> bool`
   y `exec_allowed(alias: str) -> bool`. **Registrar un ambiente para comparar (lectura) NO habilita
   ejecucion (escritura):** son opt-ins separados.

2. `sql_exec_engine.py`:

```python
from dataclasses import dataclass, field
import hashlib, re, time

@dataclass
class ExecResult:
    ok: bool
    dry_run: bool
    statement_count: int
    rows_affected: int | None
    error: str | None
    duration_ms: int
    statements: list = field(default_factory=list)   # solo en dry_run: los statements detectados (sin ejecutar)

def script_fingerprint(sql_text: str) -> str:
    """sha256 del texto EXACTO del script — el HITL exige que coincida con lo que el operador vio."""
    return hashlib.sha256(sql_text.encode("utf-8")).hexdigest()

def _split_statements(sql_text: str) -> list[str]:
    """Split determinista por ';' de nivel superior, ignorando ';' dentro de strings/comentarios.
    Documentar la limitacion: NO parsea PL/SQL con bloques BEGIN..END (para eso, statement unico)."""
    ...

def execute_script(*, alias: str, sql_text: str, dry_run: bool,
                   ticket_ref: str | None, incident_id: str | None,
                   confirm_fingerprint: str, executed_by: str,
                   force: bool = False) -> ExecResult:
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_SQL_EXEC_ENABLED", False):
        raise PermissionError("sql_exec_disabled")            # -> 404 en la ruta
    from services import dbcompare_registry
    if not dbcompare_registry.exec_allowed(alias):
        raise PermissionError("env_not_exec_allowed")          # -> 403 en la ruta
    if confirm_fingerprint != script_fingerprint(sql_text):
        raise ValueError("fingerprint_mismatch")               # -> 409 en la ruta
    # idempotencia (R4): si ya se ejecuto este sha en este alias y no viene force -> bloquear
    from services import sql_exec_ledger
    prev = sql_exec_ledger.find_executed(alias, script_fingerprint(sql_text))
    if prev is not None and prev.get("result_ok") and not prev.get("dry_run") and not force:
        raise RuntimeError("already_executed")                 # -> 409 con detalle en la ruta
    from services import dbcompare_engine
    cred = dbcompare_registry.get_credential(alias)             # para _scrub del password
    password = (cred or {}).get("password") or ""
    statements = _split_statements(sql_text)
    if dry_run:
        return ExecResult(ok=True, dry_run=True, statement_count=len(statements),
                          rows_affected=None, error=None, duration_ms=0, statements=statements)
    engine = dbcompare_engine.open_engine(alias)               # REUSO
    started = time.monotonic()
    total_rows = 0
    try:
        with engine.begin() as conn:                           # transaccion: commit al salir OK, rollback si lanza
            from sqlalchemy import text as _sql_text
            for stmt in statements:
                res = conn.execute(_sql_text(stmt))
                total_rows += (res.rowcount if res.rowcount is not None and res.rowcount >= 0 else 0)
        dur = int((time.monotonic() - started) * 1000)
        result = ExecResult(ok=True, dry_run=False, statement_count=len(statements),
                            rows_affected=total_rows, error=None, duration_ms=dur)
    except Exception as exc:                                    # noqa: BLE001
        dur = int((time.monotonic() - started) * 1000)
        msg = dbcompare_engine._scrub(str(exc), password) if password else str(exc)   # MASKING
        result = ExecResult(ok=False, dry_run=False, statement_count=len(statements),
                            rows_affected=None, error=msg[:1000], duration_ms=dur)
    finally:
        engine.dispose()
    # R4: registrar SIEMPRE (ok o error) — no es best-effort, es parte del contrato
    sql_exec_ledger.append_exec({
        "alias": alias, "engine": (cred or {}).get("engine"),
        "ticket_ref": ticket_ref, "incident_id": incident_id,
        "script_sha256": script_fingerprint(sql_text),
        "statement_count": len(statements), "dry_run": False,
        "result_ok": result.ok, "rows_affected": result.rows_affected,
        "error": result.error, "duration_ms": result.duration_ms,
        "executed_by": executed_by,
    })
    return result
```

3. `api/db_compare.py`, endpoint HITL (calcar el patron confirm+fingerprint de `devops.py:271`):

```python
@bp.post("/environments/<alias>/execute-script")
def db_compare_execute_script(alias: str):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_DB_COMPARE_ENABLED", False):
        abort(404)
    if not getattr(_cfg, "STACKY_SQL_EXEC_ENABLED", False):
        abort(404)                                    # flag OFF = feature inexistente
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    sql_text = body.get("sql") or ""
    fp = body.get("fingerprint") or ""
    if not sql_text or not fp:
        return jsonify({"error": "sql y fingerprint son obligatorios"}), 400
    from services import sql_exec_engine
    try:
        res = sql_exec_engine.execute_script(
            alias=alias, sql_text=sql_text, dry_run=bool(body.get("dry_run", False)),
            ticket_ref=body.get("ticket_ref"), incident_id=body.get("incident_id"),
            confirm_fingerprint=fp, executed_by=current_user() or "operator",
            force=bool(body.get("force", False)),
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), (404 if str(exc) == "sql_exec_disabled" else 403)
    except ValueError as exc:                          # fingerprint_mismatch
        return jsonify({"error": str(exc), "kind": "fingerprint_mismatch"}), 409
    except RuntimeError as exc:                         # already_executed
        return jsonify({"error": str(exc), "kind": "already_executed"}), 409
    from dataclasses import asdict
    return jsonify(asdict(res))
```
   Ademas: `POST /environments/<alias>/exec-allowed` (body `{"allowed": true|false}`) que llama
   `dbcompare_registry.set_exec_allowed`; gated por `STACKY_DB_COMPARE_ENABLED` (el opt-in de escritura
   se puede togglear aunque `STACKY_SQL_EXEC_ENABLED` este OFF — asi el operador prepara el ambiente
   antes de habilitar el master).

**Seguridad dura (todas con test):**
- **allow-list doble:** el alias debe existir en el registro (`dbcompare_registry`) Y tener
  `exec_allowed=True`.
- **flag OFF -> 404** (la feature no existe si el master esta OFF).
- **HITL:** `confirm=True` + `fingerprint` que coincide con el sha del SQL exacto (evita ejecutar algo
  distinto de lo que el operador vio; 409 si difiere).
- **dry-run:** `dry_run=True` NO abre engine ni ejecuta; devuelve los statements detectados.
- **transaccion:** `engine.begin()` commitea al salir OK y hace rollback ante excepcion.
- **masking:** el `error` pasa por `_scrub(msg, password)`; el password JAMAS viaja en la respuesta;
  el connection string nunca se loguea (open_engine ya lo maneja).
- **idempotencia:** `find_executed` bloquea re-ejecucion del mismo sha en el mismo alias salvo `force`.

**Tests PRIMERO — `tests\test_plan200_sql_exec_engine.py`** (usar sqlite: registrar un ambiente
`engine="sqlite"` en `tmp_path` via `dbcompare_registry` con password dummy — recordar que
`open_engine` exige credencial aun para sqlite, memoria plan 183; monkeypatch `data_dir`):
- `test_flag_off_lanza_permission` — `STACKY_SQL_EXEC_ENABLED` OFF -> `PermissionError("sql_exec_disabled")`.
- `test_env_no_exec_allowed_lanza` — alias sin `exec_allowed` -> `PermissionError("env_not_exec_allowed")`.
- `test_fingerprint_mismatch` — `confirm_fingerprint` distinto del sha -> `ValueError`.
- `test_dry_run_no_muta` — `dry_run=True` sobre `CREATE TABLE ...` -> `ExecResult.dry_run True`,
  `statement_count` correcto, y la tabla NO existe despues (query de verificacion).
- `test_ejecucion_real_crea_y_commitea` — `CREATE TABLE t(...); INSERT ...` con fingerprint correcto ->
  `ok True`, `rows_affected>=1`, la tabla existe y tiene la fila (nueva conexion).
- `test_error_hace_rollback_y_scrub` — SQL invalido -> `ok False`, `error` sin el password
  (assert password NOT in error), y ningun efecto parcial persistido.
- `test_idempotencia_bloquea_sin_force` — ejecutar el mismo sha 2 veces -> la 2da lanza
  `RuntimeError("already_executed")`; con `force=True` -> corre.
- `test_ledger_registra_ok_y_error` — tras ok y tras error hay 2 entries en el ledger.
- Registrar en `HARNESS_TEST_FILES`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan200_sql_exec_engine.py -q`

**Criterio de aceptacion (binario):** los 8 tests pasan; `grep -n "password" ExecResult` no expone el
password en el shape de respuesta (revision manual del `asdict`); `python -m compileall
backend/services/sql_exec_engine.py` limpio.

**Flag que protege:** `STACKY_SQL_EXEC_ENABLED` **default OFF** (EXCEPCION 2 destructiva/irreversible +
EXCEPCION 3 prerequisito no garantizado) + master `STACKY_DB_COMPARE_ENABLED` + `exec_allowed` por ambiente.
**Impacto por runtime:** identico en los 3 (no hay LLM/runtime; es acceso a BD).
**Fallback:** flag OFF -> 404; ambiente sin credencial -> `open_engine` ya devuelve error claro.
**Trabajo del operador:** **opt-in default OFF por excepciones 2+3, y HITL por ejecucion** (habilitar
el master en la UI de flags + marcar el ambiente `exec_allowed` + confirmar cada corrida).

---

### F6 — Backend: bitacora `sql_exec_ledger` append-only tamper-evident + traza + idempotencia (R4)

**Objetivo (1 frase):** registrar cada ejecucion SQL por ambiente en un ledger JSONL con cadena de
hash, exponer la traza y sostener el chequeo de idempotencia de F5.
**Valor:** materializa R4 — ver que corrio donde, sin re-ejecutar a ciegas.

**Archivos a CREAR:**
- `Stacky Agents\backend\services\sql_exec_ledger.py`
- `Stacky Agents\backend\tests\test_plan200_sql_exec_ledger.py`

**Archivos a EDITAR:**
- `Stacky Agents\backend\api\db_compare.py` (endpoint `GET /sql-exec-ledger`)
- `Stacky Agents\backend\scripts\run_harness_tests.sh`

**Contrato (`sql_exec_ledger.py`, CALCA la receta congelada del 198 F0 + cadena de hash):**

```python
import json, hashlib, threading
from datetime import datetime, timezone
from pathlib import Path
import runtime_paths

_LOCK = threading.Lock()
MAX_ROWS = 500
_LEDGER_REL = "db_compare/sql_exec_ledger.jsonl"     # JSONL append-only en data_dir()

# ALLOWLIST estricta: cualquier clave fuera de esta lista se DESCARTA (jamas un secreto por accidente).
ENTRY_FIELDS = (
    "alias", "engine", "ticket_ref", "incident_id", "script_sha256", "statement_count",
    "dry_run", "result_ok", "rows_affected", "error", "duration_ms", "executed_by",
    "executed_at", "source", "prev_hash", "entry_hash",
)

def _path() -> Path: return runtime_paths.data_dir() / _LEDGER_REL

def _canonical(entry: dict) -> str:
    # serializacion estable (sin entry_hash) para el hash: sorted keys, separators fijos.
    body = {k: entry.get(k) for k in ENTRY_FIELDS if k != "entry_hash"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def _hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(entry)).encode("utf-8")).hexdigest()

def append_exec(entry: dict) -> None:
    with _LOCK:
        rows = _read_all()                                    # tolera lineas corruptas (las saltea)
        prev_hash = rows[-1]["entry_hash"] if rows else "GENESIS"
        clean = {k: entry.get(k) for k in ENTRY_FIELDS if k not in ("prev_hash", "entry_hash")}
        clean["executed_at"] = entry.get("executed_at") or datetime.now(timezone.utc).isoformat()
        clean["source"] = entry.get("source") or "stacky"
        clean["dry_run"] = bool(entry.get("dry_run", False))
        clean["prev_hash"] = prev_hash
        clean["entry_hash"] = _hash(prev_hash, clean)
        rows.append(clean)
        rows = rows[-MAX_ROWS:]                                # retencion
        _write_all(rows)                                      # tmp + Path.replace (atomico)

def list_execs(alias=None, ticket_ref=None, script_sha256=None, limit=50) -> list[dict]:
    rows = _read_all()
    if alias is not None:       rows = [r for r in rows if r.get("alias") == alias]
    if ticket_ref is not None:  rows = [r for r in rows if r.get("ticket_ref") == ticket_ref]
    if script_sha256 is not None: rows = [r for r in rows if r.get("script_sha256") == script_sha256]
    rows.sort(key=lambda r: r.get("executed_at") or "", reverse=True)   # DESC explicito
    return rows[: max(1, min(limit, MAX_ROWS))]

def find_executed(alias: str, script_sha256: str) -> dict | None:
    # el mas reciente ok/no-dry-run para ese (alias, sha); None si no hay.
    for r in list_execs(alias=alias, script_sha256=script_sha256, limit=MAX_ROWS):
        if r.get("result_ok") and not r.get("dry_run"):
            return r
    return None

def verify_chain() -> bool:
    rows = _read_all()
    prev = "GENESIS"
    for r in rows:
        body = {k: r.get(k) for k in ENTRY_FIELDS if k != "entry_hash"}
        body["prev_hash"] = prev
        if _hash(prev, body) != r.get("entry_hash"):
            return False
        prev = r.get("entry_hash")
    return True
```
(`_read_all`/`_write_all` con el patron del 198: leer linea a linea saltando corruptas; escribir a
`.tmp` y `Path.replace`. NO importar red/providers.)

**Endpoint de traza (read-only, gated `STACKY_SQL_EXEC_LEDGER_ENABLED`):**

```python
@bp.get("/sql-exec-ledger")
def db_compare_sql_exec_ledger():
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_DB_COMPARE_ENABLED", False): abort(404)
    if not getattr(_cfg, "STACKY_SQL_EXEC_LEDGER_ENABLED", True): abort(404)
    from services import sql_exec_ledger
    alias = request.args.get("alias") or None
    ticket_ref = request.args.get("ticket_ref") or None
    return jsonify({
        "entries": sql_exec_ledger.list_execs(alias=alias, ticket_ref=ticket_ref, limit=50),
        "chain_ok": sql_exec_ledger.verify_chain(),
    })
```

**Tests PRIMERO — `tests\test_plan200_sql_exec_ledger.py`** (monkeypatch `runtime_paths.data_dir`):
- `test_append_y_cadena_valida` — 3 appends -> `verify_chain() True`; cada entry tiene `prev_hash`
  encadenado.
- `test_tamper_detectado` — alterar el `alias` de una linea a mano -> `verify_chain() False`.
- `test_allowlist_descarta_extra` — entry con `password` extra -> la clave NO aparece en el JSONL.
- `test_find_executed` — tras un `result_ok True`/`dry_run False` -> `find_executed` lo encuentra; un
  dry-run NO cuenta.
- `test_retencion_500` — 501 appends -> quedan 500.
- `test_orden_desc` — 3 sembrados en desorden -> `list_execs` DESC por `executed_at`.
- `test_filtros_alias_ticket` — entries de 2 alias / 2 ticket_ref -> filtros exactos.
- `test_lineas_corruptas_no_rompen` — linea basura intercalada -> `list_execs` la saltea.
- Registrar en `HARNESS_TEST_FILES`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_plan200_sql_exec_ledger.py -q`

**Criterio de aceptacion (binario):** los 8 tests pasan; `grep -nE "requests|http|providers|environment_remote"
backend/services/sql_exec_ledger.py` -> 0 matches (ledger PURO).

**Flag que protege:** `STACKY_SQL_EXEC_LEDGER_ENABLED` (default ON) + master `STACKY_DB_COMPARE_ENABLED`.
**Impacto por runtime:** identico (funcion pura). **Fallback:** flag OFF -> 404 en la traza; el
`append_exec` de F5 solo corre cuando R3 ejecuta (R3 OFF por default -> ledger vacio, sin efecto).
**Trabajo del operador:** ninguno (la traza aparece sola cuando haya ejecuciones).

---

### F7 — Frontend: seccion BD por ticket/incidencia — scripts + boton "Ejecutar en ambiente" + confirm + traza (R3+R4)

**Objetivo (1 frase):** en la seccion de BD, por ticket/incidencia, listar los scripts, ejecutarlos en
el ambiente elegido con confirmacion, y ver la traza por ambiente.
**Valor:** cierra el ciclo visible de R3+R4 para el operador.

**Archivos a CREAR:**
- `Stacky Agents\frontend\src\components\dbcompare\sqlExecPanelLogic.ts` (helpers puros)
- `Stacky Agents\frontend\src\components\dbcompare\sqlExecPanelLogic.test.ts`
- `Stacky Agents\frontend\src\components\dbcompare\SqlExecPanel.tsx` (seccion; wireable en ticket/incidencia y en la pagina BD)

**Archivos a EDITAR:**
- `Stacky Agents\frontend\src\components\dbcompare\DbComparePage.tsx` (montar `SqlExecPanel` como sub-seccion)
- `Stacky Agents\frontend\src\components\IncidentResolverModal.tsx` y
  `Stacky Agents\frontend\src\pages\TicketBoard.tsx` (enganchar el boton de la seccion R2/F4 hacia `SqlExecPanel`)

**Comportamiento exacto:**

1. `sqlExecPanelLogic.ts` (puro):

```typescript
export interface EnvOption { alias: string; engine: string; exec_allowed: boolean; has_password: boolean; }
export interface LedgerEntry {
  alias: string; ticket_ref: string | null; script_sha256: string; result_ok: boolean;
  rows_affected: number | null; dry_run: boolean; executed_at: string; executed_by: string; error: string | null;
}
// Ambientes elegibles para ejecutar: registrados + exec_allowed + con password. Determinista.
export function executableEnvs(envs: EnvOption[]): EnvOption[] { /* filter */ }
// Aviso de idempotencia: si el sha ya figura ok/no-dry-run para ese alias -> texto de advertencia.
export function idempotencyWarning(entries: LedgerEntry[], alias: string, sha: string): string { /* "" o "Ya ejecutado el <fecha>" */ }
// Fila de traza legible.
export function ledgerRow(e: LedgerEntry): string { /* "<fecha> · <alias> · OK/FALLO · N filas" */ }
```

2. `SqlExecPanel.tsx`:
   - Recibe `scripts` (de F4/R2) y el `ticket_ref`/`incident_id`.
   - Dropdown de ambiente: `GET /api/db-compare/environments` (endpoint existente del comparador; si el
     nombre difiere, confirmar con grep en `api/db_compare.py`), filtrado con `executableEnvs`.
   - Boton "Ejecutar en ambiente ▼": abre un **modal de confirmacion** (reusar la primitiva `Dialog`
     del plan 164 — `grep -rn "useConfirm\|Dialog" frontend/src/components` para el import real) que
     muestra: script, ambiente elegido, y el `idempotencyWarning` (consultando
     `GET /api/db-compare/sql-exec-ledger?alias=<alias>`); ofrece "Dry-run" y "Ejecutar de verdad".
   - Al confirmar: `POST /api/db-compare/environments/<alias>/execute-script` con
     `{confirm:true, sql, fingerprint: sha256(sql), dry_run, ticket_ref, incident_id, force?}`.
     - **El fingerprint se computa en el front sobre el MISMO texto que se envia** (usar la Web Crypto
       API `crypto.subtle.digest('SHA-256', ...)`; helper async en `sqlExecPanelLogic.ts` con test que
       verifica el hash de un texto conocido contra un valor esperado fijo).
     - 409 `already_executed` -> re-preguntar con "Ya se ejecuto; forzar" (setea `force:true`).
     - 409 `fingerprint_mismatch` -> refrescar el script y reintentar (no forzar).
   - Traza por ambiente: `GET /api/db-compare/sql-exec-ledger?alias=<alias>` -> lista con `ledgerRow` +
     badge `chain_ok` (si `false`, aviso "bitacora alterada").
   - **api wrapper (gotcha):** usar `rawPost`/`rawGet` para poder leer el body de 4xx/409 (el wrapper
     `api.post` de `client.ts` LANZA en non-2xx — memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx`).
   - Si `STACKY_SQL_EXEC_ENABLED` esta OFF (status de BD dice feature off / 404 del endpoint), el panel
     muestra los scripts y la traza pero el boton "Ejecutar" queda deshabilitado con tooltip
     "Habilita ejecucion SQL en Configuracion > Flags". (R4 read-only sigue visible.)
   - Clases del CSS module `dbcompare.module.css` (**gotcha ratchet:** sin `style={{}}` nuevos).

**Tests PRIMERO — `sqlExecPanelLogic.test.ts`:**
- `executableEnvs` — filtra fuera los sin `exec_allowed` o sin `has_password`.
- `idempotencyWarning` — hay entry ok/no-dry-run del mismo sha+alias -> texto; caso contrario -> "".
- `ledgerRow` — formato exacto OK y FALLO.
- `sha256Hex` (helper de fingerprint) — hash de "SELECT 1" == valor esperado fijo (vector de prueba).

**Comando:** `npx vitest run src/components/dbcompare/sqlExecPanelLogic.test.ts`

**Criterio de aceptacion (binario):** los 4 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Flag que protege:** `STACKY_SQL_EXEC_ENABLED` (boton deshabilitado si OFF) +
`STACKY_SQL_EXEC_LEDGER_ENABLED` (traza) + master `STACKY_DB_COMPARE_ENABLED`.
**Impacto por runtime:** UI pura. **Fallback:** flags OFF -> panel read-only o ausente.
**Trabajo del operador:** para R4/traza ninguno; para R3 **opt-in default OFF + HITL por ejecucion**
(elegir ambiente + confirmar el modal).

---

## 5. Riesgos y mitigaciones

| Riesgo | Severidad | Mitigacion |
|--------|-----------|------------|
| **Ejecucion SQL destructiva/irreversible contra la BD equivocada (R3)** | **CRITICA** | Flag master OFF por default (excepciones 2+3); allow-list doble (alias registrado + `exec_allowed` opt-in separado del registro de lectura); HITL con `confirm=True` + `fingerprint` del SQL exacto (409 si difiere); dry-run obligatoriamente disponible antes de ejecutar; transaccion (`engine.begin()`, rollback ante error); idempotencia que bloquea re-ejecucion sin `force`; ledger tamper-evident de todo intento. **Fuera de scope: rollback/undo de un script ya ejecutado (imposible en general).** |
| Password/connection string filtrado en salida o logs | Alta | `_scrub(msg, password)` en errores; el password nunca viaja en `ExecResult`; `open_engine` ya oculta el string; egress sentinel dispara ante `password=<4+>` (`dbcompare_config_import.py:196`) -> ninguna respuesta lo contiene. Test `test_error_hace_rollback_y_scrub`. |
| Split de statements rompe PL/SQL con `BEGIN..END` | Media | `_split_statements` documenta la limitacion; para bloques anonimos el operador manda 1 statement; test cubre el split simple; NO se intenta un parser SQL completo (fuera de scope). |
| Ledger corrupto/alterado da falsa confianza | Media | Cadena de hash + `verify_chain()`; la traza muestra `chain_ok`; ALLOWLIST evita claves inesperadas; tolerancia a lineas corruptas (se saltean, no tumban). |
| Detector R2 marca falsos positivos/negativos | Baja | Determinista y explicable: `.sql` presente -> "alta"; solo keywords -> "posible" (aviso suave); el operador decide. Sin LLM. |
| Dev-resolutor no linkea su ejecucion (R1) | Baja | F1 agrega `add_execution(kind="dev_resolver")` en su call-site; si no hay incidencia asociada, no-op; back-compat con `execution_id` legacy sintetizado en el endpoint. |
| Sesion paralela toca `api/db_compare.py` / `harness_flags.py` (series activas) | Media | Cambios ADITIVOS (endpoints y FlagSpec nuevos al final del bloque); correr `git worktree list` + `git log --all --grep=plan-200` antes de implementar (memoria `parallel-session-confirmed-live`); pathspec explicito al commitear. |
| `secret_masking`/`env_apply_ledger` citados por otros planes no existen aca | Baja | Ya resuelto: se reusan los modulos REALES (`_scrub`/`pii_masker`) y se calca la receta del DOC 198; el implementador confirma con grep (nota de arranque). |

## 6. Fuera de scope

- **Rollback/undo de un script SQL ya ejecutado** (destructivo/irreversible; jamas desde Stacky).
- Parser SQL completo / soporte de bloques PL/SQL `BEGIN..END` multi-statement (statement unico para eso).
- Elegir automaticamente el ambiente correcto (el detector sugiere TODOS los registrados; el operador elige).
- Orquestar despliegues multi-ambiente en cadena o con dependencias (una ejecucion = un script, un ambiente, un click).
- Editar el SQL dentro de Stacky (se ejecuta lo que viene del adjunto/output; editar es otro flujo).
- Consolidar un `jsonl_ledger.py` comun con 191/198 (refactor futuro anotado, no aca).
- RBAC/multiusuario sobre quien puede ejecutar (mono-operador; `executed_by` es solo traza).
- Streaming en vivo del transcript en el modal de incidencia (F2 usa snapshot; el stream existente
  `/logs/stream` queda disponible para un follow-up si se pide).

## 7. Glosario (para modelos menores)

- **Incidencia:** captura del operador (texto + adjuntos) en `data_dir()/incidents/<id>/intake.json`;
  la resuelve un agente. Store: `services/incident_store.py`.
- **Ticket:** work item del tracker (ADO/GitLab); modelo `Ticket` en `models.py`; artefactos en
  `Output/tickets/<ado_id>/`.
- **Ejecucion (execution):** una corrida de agente; fila `AgentExecution`; su consola/transcript vive en
  `log_streamer` + tabla `execution_logs`, servida por `api/executions.py`.
- **Consola / transcript (R1):** los eventos de log de una ejecucion (`snapshot`/`stream`), lo que
  "respondio el agente".
- **Ambiente (R3/R4):** una BD registrada por **alias** en `dbcompare_registry`
  (`data_dir()/db_compare/environments.json`); se conecta con `dbcompare_engine.open_engine(alias)`.
- **`exec_allowed` (opt-in):** flag por-ambiente que habilita ESCRITURA en ese alias; separado de
  registrarlo para comparar (lectura).
- **Fingerprint del script:** sha256 del texto SQL exacto; el HITL exige que coincida con lo que el
  operador vio (evita ejecutar algo distinto).
- **Ledger / bitacora (R4):** archivo JSONL append-only en `data_dir()` con una entrada por ejecucion;
  aca con **cadena de hash** (cada entry encadena el hash del anterior -> tamper-evident).
- **Idempotencia (R4):** antes de ejecutar un sha en un alias, se consulta el ledger; si ya corrio ok,
  se bloquea salvo `force`.
- **HITL:** human-in-the-loop; el operador confirma cada ejecucion (`confirm=True`), nunca automatica.
- **Masking:** ocultar secretos; aca `_scrub`/`_mask`/`preview_dict`/`pii_masker` (no existe
  `secret_masking` en esta rama).
- **Harness flag / curated ON / requires / `_CATEGORY_KEYS`:** sistema de flags; ON efectivo requiere
  wiring en 5 lugares; requires es una arista profundidad-1 en `_REQUIRES_MAP_FROZEN`.
- **Runtime:** motor de agente (Codex CLI / Claude Code CLI / GitHub Copilot Pro); este plan es
  runtime-agnostico salvo el contenido del transcript (fallback a log crudo).

## 8. Orden de implementacion

1. **F0** — 4 flags + config UI + contrato de masking + `test_plan200_flags.py`.
2. **F1** — linkage incidencia<->ejecuciones + endpoint `/incidents/<id>/console` + tests.
3. **F2** — pestana "Consola del agente" en `IncidentResolverModal` + `incidentConsole.test.ts` + `tsc`.
4. **F3** — `sql_deploy_detector.py` + endpoints `/sql-deploy` + tests.
5. **F4** — badge/seccion "Despliegue SQL requerido" en incidencia y ticket + `sqlDeployBadge.test.ts` + `tsc`.
6. **F6** — `sql_exec_ledger.py` + endpoint de traza + tests. **(F6 antes de F5: F5 depende del ledger para idempotencia y registro.)**
7. **F5** — `sql_exec_engine.py` + `exec_allowed` en el registro + endpoints de ejecucion + tests.
8. **F7** — `SqlExecPanel` + `sqlExecPanelLogic.test.ts` + wiring + `tsc`.

> Nota de dependencia: R1 (F1-F2), R2 (F3-F4) y R4 (F6) son independientes entre si y pueden ir en
> cualquier orden tras F0. R3 (F5) DEBE ir despues de F6 (usa el ledger). F7 va al final (consume F4,
> F5, F6). Cada fase se commitea sola con sus tests verdes.

## 9. Definicion de Hecho (DoD) global

- [ ] Los 8 archivos de test (`test_plan200_flags.py`, `test_plan200_incident_console.py`,
      `test_plan200_sql_deploy_detector.py`, `test_plan200_sql_exec_engine.py`,
      `test_plan200_sql_exec_ledger.py`, `incidentConsole.test.ts`, `sqlDeployBadge.test.ts`,
      `sqlExecPanelLogic.test.ts`) pasan POR ARCHIVO con el interprete correcto (`.venv` py3.13 / vitest).
- [ ] `test_harness_flags.py`, `test_harness_flags_requires.py`,
      `test_default_known_only_for_curated`, `test_every_registry_flag_is_categorized` verdes.
- [ ] KPI-1..KPI-5 verificados por los tests nombrados.
- [ ] `python -m compileall backend` limpio; `npx tsc --noEmit` sin errores nuevos; ratchet UI sin
      `style={{}}` nuevos (criterio NO-EMPEORAR para ratchets ajenos ya rojos).
- [ ] Las 4 flags visibles/toggleables en la UI de flags (R1/R2/R4 ON, R3 OFF).
- [ ] Con `STACKY_INCIDENT_CONSOLE_ENABLED` / `STACKY_SQL_DEPLOY_DETECT_ENABLED` /
      `STACKY_SQL_EXEC_LEDGER_ENABLED` / `STACKY_SQL_EXEC_ENABLED` OFF: cero diferencias vs. hoy
      (404 en endpoints nuevos; pantallas identicas).
- [ ] R3: con flag ON pero `exec_allowed` OFF -> 403; dry-run no muta; ejecucion real commitea y queda
      en el ledger con cadena valida; re-ejecucion sin `force` bloqueada; password nunca en la respuesta.
- [ ] Ningun modulo nuevo importa red/LLM salvo `sql_exec_engine` (que solo abre engine via
      `open_engine` para R3).
- [ ] Cada `test_*.py` nuevo registrado en `HARNESS_TEST_FILES`; los 4 endpoints nuevos montados en sus
      blueprints existentes.
- [ ] Smoke E2E manual (opcional, 1 pasada): incidencia con adjunto `.sql` -> badge "Despliegue SQL
      requerido" -> pestana "Consola del agente" muestra el transcript -> (con R3 ON + ambiente sqlite
      sandbox `exec_allowed`) ejecutar el script -> aparece en la traza por ambiente con `chain_ok`.
