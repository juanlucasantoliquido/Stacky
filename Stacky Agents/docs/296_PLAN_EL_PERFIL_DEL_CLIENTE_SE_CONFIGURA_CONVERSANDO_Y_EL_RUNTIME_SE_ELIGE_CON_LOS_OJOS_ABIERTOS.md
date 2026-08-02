# Plan 296 — El perfil del cliente se configura CONVERSANDO, y el runtime se elige con los ojos abiertos

**Estado:** MEJORADO (**v1 -> v2**) · **Fecha:** 2026-08-02 · **Rama:** `docs/plan-279`
**Juez v2: subagente independiente, misma corrida, contexto limpio**
**Eje:** perfil de cliente + elección informada de runtime. **NO** toca pipelines (eje 294) ni git (eje 293) ni GitLab (eje 295).

VEREDICTO v1: **RECHAZADO** — 8 BLOQUEANTES (C1..C8), 10 IMPORTANTES (C9..C18), 2 MENORES (C19..C20). Anclajes: **90 OK / 4 DESFASADOS / 0 INEXISTENTES / 3 OK-de-línea-con-contenido-mal-descrito**, sobre **97** verificados abriendo los archivos. Esta v2 resuelve los 8 bloqueantes (una entrada de changelog por cada uno) y queda **APROBADO-CON-CAMBIOS** para implementar.

---

## CHANGELOG v1 -> v2

**Bloqueantes resueltos (uno por línea, con el mecanismo, no con una reformulación):**

- **C1 — `autodetect_process_catalog` NO es un servicio, es una RUTA Flask (`api/client_profile.py:393`).** §4 P3 y el Anexo B lo daban por usable desde F2, que es un módulo `services/` puro y por P7 no puede importar `api/`. **Resolución (a) del protocolo E3: se construye la capacidad.** F2 recibe los candidatos **por parámetro** (`procesos_detectados=()`), igual que ya hacía con `estados_validos`; el endpoint de F3 —que sí puede importar `api`— los arma llamando a las **mismas dos fuentes** que usa la ruta (`services.project_autoprofile` y `grounding_observatory`). Caso de test nombrado en F2 (`test_procesos_detectados_vacios_no_generan_pregunta_muda`) y en F3 (`test_state_pasa_los_procesos_detectados_al_banco`).
- **C2 — `exige_agente_vscode: True` era falso en 3 de sus 4 anclajes.** Medido: `api/agents.py:480` **rechaza** (`"missing_vscode_agent_filename"`, `:488`), pero `:857`, `:1067` y `:1259` **auto-rellenan** (`"BusinessAgent.agent.md"` `:858`, `"IncidentAnalyst.agent.md"` `:1069`, `"IncidentDevResolver.agent.md"` `:1261`). El campo se **parte en dos medidos**: `exige_agente_vscode` (solo el camino que rechaza) y `agente_vscode_por_defecto` (el mapa de los 3 autorellenos), con `AGENTE_VSCODE_POR_DEFECTO` como constante y dos casos de test que los anclan contra las 4 líneas reales.
- **C3 — faltaba el guardián #6 de la flag OFF: `_REQUIRES_MAP_FROZEN`.** La FlagSpec OFF declara `requires=`, y `tests/test_harness_flags_requires.py:405::test_requires_map_is_frozen` hace `assert actual == _REQUIRES_MAP_FROZEN` (`:120`): sin la entrada nueva esa suite queda ROJA y el criterio de F0 —que solo medía `test_harness_flags.py` y `test_harness_flags_help.py`— era **ciego a su propio rojo**. F0 pasa a **6 lugares de cableado**, con caso de test propio y comando de verificación delta.
- **C4 — dos criterios binarios aritméticamente imposibles.** F4 decía "15 passed" y "20 passed" en la misma línea; F7 decía "13 colectados (11 casos + 2 extra)" cuando los dos `parametrize` son sobre `RUNTIMES` (3). Se fijan los números reales **con la aritmética escrita**: F4 = **20 colectados**, F7 = **16 colectados**. Ningún caso se borró: se corrigió el número, no el test.
- **C5 — `test_no_importa_api` fallaba contra el docstring del propio módulo que testea.** El plan especificaba el docstring literal `NO importa api.*` y, en el mismo bloque, `"api." not in inspect.getsource(...)`: `getsource` de un módulo devuelve el archivo entero, docstring incluido ⇒ assert **False por construcción** (el gotcha de la casa "un comentario que NOMBRA el patrón rompe el gate por grep", 7 ocurrencias registradas). El gate pasa a **AST** (`ast.parse` + solo nodos `Import`/`ImportFrom` de nivel superior), con el mensaje listando los módulos ofensores. Aplica a F1 y F2.
- **C6 — los tests de F3/F5/F7 escribían en los PROYECTOS y en la DATA REALES del operador.** `save_client_profile` no pasa por el seam de lectura: escribe directo en `projects_dir()/<NAME>/config.json` (`client_profile.py:415`) y **exige que ese archivo ya exista** (`:416-417`); `record_event` anexa a `data/config_transfer_events.jsonl`. Se agrega la **fixture de aislamiento obligatoria** calcada de `tests/test_client_profile.py:18-32` (los DOS setattr: `client_profile.projects_dir` **y** `project_manager.PROJECTS_DIR`) más el monkeypatch de `record_event`, y dos casos que prueban el aislamiento.
- **C7 — las rutas del plan llevaban `/api` y `api_bp` YA lo pone.** `api/__init__.py:97` es `Blueprint("api", __name__, url_prefix="/api")`, `api/client_profile.py:54` es `url_prefix=""`, y `api/__init__.py:140` lo advierte textual (`NUNCA "/api/...": api_bp ya lo pone`). Las tablas de F3/F4/F5 pasan a **dos columnas — decorador vs URL final** — con la advertencia literal y un caso de test que asserta la URL final.
- **C8 — F7 casos 6 y 7 eran un gate sin contraste.** Corrían "turn→propose→apply" con `STACKY_PROFILE_COPILOT_APPLY_ENABLED` OFF: el paso 2 de F5 corta con 403 antes de tocar nada, así que pasaban **por ausencia de camino**. Ahora los dos encienden explícitamente las dos flags, y se agrega un **caso negativo de contraste** que prueba que el arnés del test SÍ caza la llamada cuando existe.

**Importantes resueltos:**

- **C9/C10/C11/C19 — anclajes desfasados corregidos con la línea real, sin borrarlos:** `api/__init__.py:148 → :152`; `app.py:635-636 → :641`; `harness_flags.py:626 → :629` (y se agregan `:315` `flujo_funcional` / `:467` `capacidades_optin`, las tuplas concretas); `pipelineCopilotModel.ts:3-5 → :4-5`.
- **C12 — K3 se apoyaba en un assert que pasa por accidente.** `validate_client_profile({})` devuelve **ok=True**: las secciones requeridas ausentes generan **warnings**, no errors (`client_profile.py:302-304`). El KPI y el DoD pasan a exigir las 3 secciones presentes **y** que desaparezcan los warnings `client_profile.<seccion> ausente` — eso sí cambia con el plan.
- **C13 — el mapeo de inconsistencias cubría 1 de las 4 formas reales de mensaje.** Se documentan las cuatro medidas y se agrega un caso por forma.
- **C14 — F6 no corría ni un ratchet del frontend, y son trampa de COMMIT.** Se declara la regla dura **CERO `#hex` en el `.module.css` y CERO `style={{` en el `.tsx`** (tokens verificados: `--accent`, `--bg-panel`, `--bg-elev`, `--border`, `--danger`, `--text-primary`; **`--color-*` NO existe**) y se agrega el comando del ratchet como criterio delta.
- **C15 — F0..F6 dejaban `test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` en rojo.** Cada fase registra **su** archivo en los DOS scripts **en la misma fase**; F7 pasa a verificar el conjunto, no a crearlo.
- **C16 — el monkeypatch de F1 dependía del estilo de import.** Se obliga `from services import run_preflight` + llamada calificada.
- **C17 — no se decía cómo se construye la app Flask del test.** Se cita el molde real `tests/test_plan93_preflight_endpoint.py:25-45`.
- **C18 — K2 describía mal el hoy:** `STACKY_RUN_PREFLIGHT_GATE_ENABLED` nace **ON** (`config.py:1058-1059`). El diseño no cambia; cambia el porqué: el riesgo es que alguien la apague y la ficha empiece a mentir.
- **`copilot_bridge.invoke` tiene MÁS ramas que las 3 enumeradas** (hay `claude_cli` en `:176`). `asistencia_llm` deja de estar hardcodeada por runtime —contradecía el propio glosario del plan, que dice que `LLM_BACKEND` es un eje distinto— y pasa a **derivarse de `config.LLM_BACKEND`**, igual para los 3.

**Adiciones:**

- **`[ADICIÓN ARQUITECTO]` en F1 — `FICHA_ANCLAJES` + `test_cada_campo_declarativo_tiene_su_anclaje_vivo`.** Ver §6/F1. Es el antídoto directo al defecto que hundió a C2.
- **Sin cambio en la cantidad de fases: siguen siendo 8 (F0..F7).** Ningún criterio, test nombrado ni assert fue borrado ni debilitado; los que eran insatisfacibles se **acotaron con el número medido**.

---

## 1. Objetivo y KPI

Hoy, dejar un proyecto con `client_profile` usable exige que una persona **conozca de antemano** nueve secciones del schema (`code_layout`, `language`, `tracker_state_machine` requeridas — `services/client_profile.py:48-52` — más `database`, `build`, `conventions`, `docs_indexes`, `terminology`, `extensions` opcionales — `:54-61`) y las llene a mano en un formulario de **1288 líneas** (`frontend/src/components/ClientProfileEditor.tsx`). El formulario es correcto y completo; el problema es que **presupone el conocimiento que el operador no tiene**.

Este plan agrega, **dentro de esa misma pantalla**, un copiloto **conversacional** que pregunta en castellano, deduce de lo que ya existe, propone el cambio, lo muestra ANTES de aplicarlo, y —con confirmación explícita— **lo ejecuta**, dejando el perfil válido. Y, antes de conversar, obliga a **elegir el runtime a ojos abiertos**: una ficha de 7 campos por cada uno de los 3 runtimes, con disponibilidad REAL medida sin disparar una corrida.

### KPI (medibles, con el test que los mide)

| # | KPI | Hoy | Después | Test que lo mide |
|---|---|---|---|---|
| K1 | Campos de la ficha de runtime, por runtime | **2 de 7** (el punto 3 parcial vía `capabilities_for`; el 7 con sustrato pero sin ficha vía `save_run_preference`) | **7 de 7** para los 3 runtimes | `test_plan296_runtime_profile.py::test_ficha_tiene_los_siete_campos_para_los_tres_runtimes` |
| K2 | Consultar disponibilidad de un runtime | Sólo disparando `run_agent` contra un ticket (`agent_runner.py:180-200`). El gate `STACKY_RUN_PREFLIGHT_GATE_ENABLED` **nace ON** (`config.py:1058-1059`), así que hoy corre — **pero si el operador lo apaga, `check()` devuelve `ok=True` sin verificar nada** (`run_preflight.py:82-83`) y cualquier lectura de disponibilidad basada en `check()` mentiría | Consulta pura, sin ticket, sin corrida, **con veredicto propio que no depende de esa flag en ninguno de sus dos estados** | `test_plan296_runtime_profile.py::test_disponibilidad_no_depende_del_gate_de_preflight` (parametrizado sobre `True` y `False` — **C18/C4**) |
| K3 | Secciones requeridas presentes tras una sesión que arranca de `{}` | 0 de 3, y `validate_client_profile({}).ok` **ya es `True`** (las requeridas ausentes son *warnings*, `client_profile.py:302-304`) | **3 de 3**, `validate_client_profile(...).ok is True` **y cero warnings de la forma `client_profile.<seccion> ausente`** — este último es el único assert que discrimina (**C12**) | `test_plan296_apply.py::test_de_perfil_vacio_a_perfil_valido_en_una_sesion` |
| K4 | Preguntas repetidas sobre datos ya conocidos | No hay detección | **0** — toda sección ya presente y válida sale del banco de preguntas | `test_plan296_completitud.py::test_seccion_ya_completa_no_genera_pregunta` |
| K5 | Cambios de runtime automáticos ante un fallo | N/A (no hay copiloto) | **0** — el runtime elegido nunca cambia solo | `test_plan296_paridad_runtimes.py::test_fallo_no_cambia_el_runtime_elegido` |

---

## 2. Por qué ahora, y por qué no se superpone con 293/294/295

Los tres planes vecinos son de **otro eje** y de otra sesión:

- **293** — tablero de **git** local para no técnicos (`git_workbench`, verbos git, `create_merge_request`).
- **294** — wizard de **pipelines** sin YAML (`pipeline_session`, `pipeline_copilot`, `PipelineCopilotSection.tsx`).
- **295** — la integración con **GitLab** deja de mentir sobre sí misma (`gitlab_provider`, sync, degradación).

Este plan toca **`client_profile*`** y **`runtime_capabilities` / `run_preflight`**, y su superficie de UI es **`ClientProfileEditor.tsx`**. No hay intersección de archivos con 293/294/295 salvo cinco rieles compartidos (`config.py`, `harness_flags.py`, `harness_flags_help.py`, los dos ratchets, `endpoints.ts`), que son de agregado puro.

> **REGLA DURA DE CONVIVENCIA:** `backend/api/pipeline_copilot.py` y `frontend/src/components/devops/PipelineCopilotSection.tsx` están **siendo editados por una sesión paralela viva**. Este plan **REUSA EL PATRÓN** de esos archivos (dataclass frozen + estados cerrados + lógica de UI en `.ts` puro) y **NO ESCRIBE UNA SOLA LÍNEA** en ellos. Los módulos que crea son **hermanos**, con nombres propios.

El gap que cierra: el perfil de cliente ya se **lee** en runtime y se inyecta al agente (`services/context_enrichment.py::build_client_profile_block`, `:631`, consumido en `api/agents.py:1713-1715` y `:2143-2144`), pero **nadie ayuda a llenarlo**. Un perfil ausente no rompe nada — `load_effective_client_profile` cae al template del tracker (`client_profile.py:388-402`) — pero degrada silenciosamente la calidad de todo lo que el agente hace. Este plan convierte el llenado en una conversación.

---

## 3. Sustrato verificado

> Todos los anclajes de esta sección fueron reverificados **abriendo los archivos** en la crítica v1→v2. Los cuatro que estaban desfasados están corregidos y marcados **(corregido v2)**.

### 3.1 Lo que YA EXISTE y este plan REUSA (nada de esto se reescribe)

**Modelo de perfil — `backend/services/client_profile.py` (560 líneas):**

| Símbolo | Línea | Uso en este plan |
|---|---|---|
| `SCHEMA_VERSION = 1` | `:40` | La sesión declara el schema que asume |
| `_SECRET_KEYS` (`pat`, `token`, `password`, `secret`, `auth_header`, `api_key` — **6, verificadas**) | `:42-44` | El copiloto **jamás** propone estas claves (P6) |
| `_REQUIRED_SECTIONS = ("code_layout", "language", "tracker_state_machine")` | `:48-52` | Fuente del banco de preguntas obligatorias (F2) |
| `_OPTIONAL_SECTIONS` (6 secciones) | `:54-61` | Fuente del banco de preguntas opcionales (F2) |
| `_contains_secret_keys(value)` — **recursivo sobre dicts y listas** | `:196-211` | Explica por qué basta una key anidada para forzar `ok=False` (F2 caso 5) |
| `class ClientProfileError` | `:66` | Se atrapa en F5 y se traduce a mensaje del copiloto |
| `class ValidationResult` (`ok`, `errors`, `warnings`, `normalized`, `.to_dict()`) | `:71-83` (decorador en `:70`) | El copiloto muestra `errors`/`warnings` textuales |
| `get_default_client_profile(tracker_type)` | `:119` | Semilla de la conversación cuando no hay perfil |
| `set_client_profile_state_flow(project, state_flow)` | `:263` | **No se usa**: F5 escribe por `save_client_profile` (un solo camino) |
| `validate_client_profile(profile)` | `:274` | Gate duro antes de aplicar (F5). **Nunca lanza** |
| — bloqueo de secretos | `:285-290` | Segundo candado de P6 |
| — las **9** secciones tipadas a `dict` | `:306-316` | Regla 2 del patch (F4) |
| — **las requeridas ausentes son WARNINGS, no errors** | `:302-304` | **Por eso `validate({}).ok` ya es `True` hoy** (C12) |
| `_read_project_config_raw(project)` | `:339` | Seam único de **lectura**; el copiloto **no** lo llama directo |
| `load_client_profile(project)` → `dict \| None` | `:358` | Base del diff (F4) |
| `has_client_profile(project)` | `:375` | Distingue "perfil ausente" de "perfil incompleto" |
| `get_project_tracker_type(project)` | `:379` | Adapta las preguntas al tracker |
| `load_effective_client_profile(project)` → **nunca None** | `:388-402` | Lectura del copiloto (F2) |
| `save_client_profile(project, profile)` | `:407` | **Única escritura** del plan (F5) |
| — **escribe en `projects_dir()/<NAME>/config.json` SIN pasar por el seam de lectura, y exige que el archivo YA exista** | `:415-417` | **Origen de la fixture obligatoria de aislamiento (C6)** |
| `_deep_merge` / `merge_with_defaults` | `:454` / `:465` | Merge de la propuesta sobre la base (F4) |
| `complete_client_profile(...)` | `:492` | Prellenado que el copiloto muestra como "ya deducido" |

**Allowlist de PATCH — `backend/services/client_profile_keys.py`:**

- `PATCHABLE_PROFILE_KEYS` (`:14-19`) tiene **EXACTAMENTE 4 keys**, todas DevOps: `devops_pipeline_drafts`, `devops_publication_presets`, `devops_publication_settings`, `devops_environment_settings`.
- `validate_profile_key(key, value)` (`:22`) devuelve literalmente `f"key '{key}' no es parcheable."` para cualquier otra key (`:35`).

> ⚠️ **CORRECCIÓN AL SUPUESTO INICIAL — verificada abriendo el archivo.** `patch_client_profile_key` **NO sirve** para escribir `code_layout`, `language`, `tracker_state_machine` ni ninguna sección del perfil: esas keys **no están** en `PATCHABLE_PROFILE_KEYS`, y el endpoint devuelve `400 {"error": "key_not_patchable"}` (`api/client_profile.py:335-337`). Además el endpoint entero está detrás de `STACKY_DEVOPS_BOOTSTRAP_ENABLED` y hace `abort(404)` si está OFF (`:326-328`).
> **Consecuencia de diseño (obligatoria):** la escritura de F5 va por el riel **GET → merge → validate → `save_client_profile`**, exactamente el mismo riel que ya usa la UI (`ClientProfileEditor.tsx:792` → `ClientProfileApi.save`). **No se agrega ninguna key a `PATCHABLE_PROFILE_KEYS`.**

**API — `backend/api/client_profile.py` (575 líneas), blueprint `client_profile_bp` importado en `api/__init__.py:10` y registrado en `api/__init__.py:152` (corregido v2 — el v1 decía `:148`):**

| Endpoint / símbolo | Línea | Nota |
|---|---|---|
| `bp = Blueprint("client_profile", __name__, url_prefix="")` | `:54` | **El blueprint NO pone prefijo**; `api_bp` pone `/api` (ver C7) |
| `record_event` importado de `services.config_transfer` | `:45` | |
| `_valid_states_for(project)` | `:132` | Opciones reales de estado para el banco de preguntas |
| `_work_item_types_for(project)` | `:102` | Ídem, tipos de work item |
| `GET /client-profile/default` | `:156-161` | Devuelve `{ok, tracker_type, template}` |
| `GET /projects/<name>/client-profile` | `:166-198` | Devuelve `profile`, `prefilled_profile`, `path_check`, `validation`, `work_item_types`, `valid_states` |
| — texto del 404 de proyecto inexistente | `:170` | `f"Proyecto '{project_name}' no encontrado"` |
| `PUT /projects/<name>/client-profile` | `:203` | Acepta `{"profile": {...}}` o el perfil pelado (`:210`) |
| `PATCH .../client-profile/keys/<key>` | `:324` | **Sólo las 4 keys DevOps**; gate `STACKY_DEVOPS_BOOTSTRAP_ENABLED` (`:326-328`) |
| `GET .../process-catalog/autodetect` | `:392` (ruta) / `:393` (función) | **Es una RUTA FLASK, no un servicio** — ver C1. Read-only (`:373-376`) |
| `DELETE .../client-profile` | `:473` | No se usa acá |
| `POST/GET .../db-readonly-auth` | `:492` / `:554` | **Credenciales — zona prohibida para el copiloto (P6)** |
| `_PROFILE_WRITE_LOCK = threading.Lock()` | `:320` | El apply de F5 lo reusa |
| `record_event(action=, project=, result=, actor=, schema_version=, detail=)` | `:362-369` | Molde exacto de la auditoría de F5. **Firma verificada** en `services/config_transfer.py:1042-1054`: los 6 kwargs existen |

> ⚠️ **`record_event` ESCRIBE en disco:** anexa a `data/config_transfer_events.jsonl` (`config_transfer.py:1055+`). En los tests **se monkeypatchea** (C6).

**Frontend — `frontend/src/components/ClientProfileEditor.tsx` (1288 líneas):**

- `export default function ClientProfileEditor()` en `:609` — **NO recibe props**. El proyecto sale de `activeProject?.name` (`:612`), y los datos de `ClientProfileApi.get(projectName!)` vía react-query con `queryKey: ["client-profile", projectName]` (`:615`).
- Guarda con `ClientProfileApi.save(projectName, profileToSave)` (`:792`) e invalida `["client-profile", projectName]` y `["projects"]` (`:799-800`).
- `if (!projectName) { ... }` en `:686` — ya hay estado vacío (early return).
- `ClientProfileApi` vive en `frontend/src/api/endpoints.ts:2245` con `get` / `save` / `clear` / `defaultTemplate`, todos con el wrapper `api.*`.
- `rawGet` / `rawPost` / `rawPut` se importan en `endpoints.ts:1` desde `./client` — **existen y están disponibles** (verificado; 20 usos de `rawGet` en el archivo).

> **Por eso el copiloto se ancla ACÁ y no en un tab nuevo.** Un tab nuevo tiene trece patas y sólo dos las exige `tsc`; las otras once fallan mudas. `ClientProfileEditor` ya resuelve proyecto activo, fetch, invalidación de caché y estado vacío.

**Runtimes — `backend/services/runtime_capabilities.py` (423 líneas):**

| Símbolo | Línea | Contenido verificado |
|---|---|---|
| `EFFORTS` | `:28` | `("low","medium","high","xhigh","max")` |
| `RUNTIMES` | `:31` | `("claude_code_cli", "codex_cli", "github_copilot")` — vocabulario **CERRADO** |
| `EFFORT_MODE` | `:34-38` | `claude_code_cli`=`"nativo"`, `codex_cli`=`"presupuesto_turnos"`, `github_copilot`=`"no_aplica"` |
| `capabilities_for(runtime)` | `:70` (docstring `:71-77`) | Devuelve SIEMPRE **11 claves** (verificadas en el `return` de `:134-146`): `runtime, known, effort_mode, effort_effective_now, supports_model, supports_effort, models, efforts, default_model, default_effort, effort_note`. **Nunca lanza, nunca None** |
| `clamp_selection(...)` | `:149` | Normaliza `(runtime, model, effort)` |
| `codex_turn_budget(...)` | `:206` | Presupuesto de turnos de codex |
| `resolve_run_selection(...)` | `:228` | Resolución de la selección efectiva |
| `pref_key_for(project)` | `:306` | `"runSelection." + slug`, ≤128 chars |
| `load_run_preference(project)` | `:316` | `None` si `STACKY_RUN_SELECTION_PREFS_ENABLED` está OFF (`:324`); import perezoso de `api.preferences` en `:326` |
| `save_run_preference(project, sel)` | `:333` | Devuelve **`False` sin lanzar** si la flag está OFF (`:339-340`); import perezoso en `:348` |
| `build_model_effort_trace(...)` | `:360` | Traza de modelo/effort |

> `STACKY_RUN_SELECTION_PREFS_ENABLED` nace **ON** (`config.py:1533-1534`), así que la persistencia de la elección funciona de fábrica. El camino OFF igual se declara (F3).

**Preflight — `backend/services/run_preflight.py` (280 líneas):**

| Símbolo | Línea | Nota |
|---|---|---|
| `_RUNTIMES_REQUIRING_REPO = {"claude_code_cli", "codex_cli"}` | `:28` | `github_copilot` NO exige repo git |
| `_RUNTIME_BINS = {"claude_code_cli": "CLAUDE_CODE_CLI_BIN", "codex_cli": "CODEX_CLI_BIN"}` | `:31-34` | `github_copilot` no tiene binario |
| `class PreflightResult(ok, warnings, failure_check, failure_detail)` | `:37-54` | |
| `check(*, ticket, runtime, project=None)` | `:57` | **Exige un `ticket`** (`:59`) |
| `_get_runtime_bin(env_key, runtime)` | `:263-273` | Defaults `{"CLAUDE_CODE_CLI_BIN": "claude", "CODEX_CLI_BIN": "codex"}` |
| `_binary_resolvable(bin_name)` | `:276-280` | `shutil.which` o ruta absoluta |

> ⚠️ **TRAMPA MEDIDA en `check()`:** `run_preflight.py:74-83` lee `STACKY_RUN_PREFLIGHT_GATE_ENABLED` y, si está OFF, **devuelve `PreflightResult(ok=True)` sin verificar nada** (`:82-83`). Hoy la flag nace **ON** (`config.py:1058-1059`), pero es editable por el operador: una consulta de disponibilidad que llame a `check()` diría "todo disponible" en cuanto alguien la apague. **Por eso F1 NO llama a `check()`**: reusa `_get_runtime_bin` y `_binary_resolvable` (los dos helpers puros) y hace su propio veredicto, sin gate. K2 lo verifica **en los dos estados de la flag**.

**Ejecución — `backend/agent_runner.py` (1278 líneas):**

- `def run_agent(*, agent_type, ticket_id, context_blocks, user, ..., runtime: str = "github_copilot", vscode_agent_filename=None, project_name=None, work_item_type="Epic", workspace_root_override=None) -> int` — `:151`. Llama al preflight en `:182` (`from services.run_preflight import check as _preflight_check`), dentro del bloque `:180-200`.
- Bifurcación: `:319` `if runtime == "codex_cli"` → `services.codex_cli_runner.start_codex_cli_run`; `:398` `elif runtime == "claude_code_cli"` → `services.claude_code_cli_runner.start_claude_code_cli_run`; el default (`github_copilot`) va por `copilot_bridge` + `services/llm_router.py`.
- `_VALID_RUNTIMES = {"github_copilot", "codex_cli", "claude_code_cli"}` — `api/agents.py:337`.

> ⚠️ **CORRECCIÓN v2 (C2) — el contrato de `vscode_agent_filename` NO es uniforme, y el v1 lo describía al revés en 3 de 4 anclajes:**
>
> | Camino | Línea | Qué hace REALMENTE |
> |---|---|---|
> | `POST /api/agents/run` | `:480` | **RECHAZA**: `{"error": "missing_vscode_agent_filename"}` (`:488`) si falta y el runtime es `codex_cli`/`claude_code_cli` |
> | Épica desde brief | `:857` | **AUTO-RELLENA** con `"BusinessAgent.agent.md"` (`:858`) |
> | Análisis de incidencia | `:1067` | **AUTO-RELLENA** con `"IncidentAnalyst.agent.md"` (`:1069`) |
> | Resolución dev de incidencia | `:1259` | **AUTO-RELLENA** con `"IncidentDevResolver.agent.md"` (`:1261`) |
>
> La ficha de F1 declara **dos campos medidos**, no uno: `exige_agente_vscode` (sólo el camino que rechaza) y `agente_vscode_por_defecto` (el mapa de los tres autorellenos). Un plan cuyo título es *"el runtime se elige con los ojos abiertos"* no puede permitirse que su ficha exagere una exigencia.

**Seam one-shot de LLM — `backend/copilot_bridge.py` (1131 líneas):**

- `def invoke(*, agent_type, system, user, on_log, execution_id=None, model=None, project_name=None, workspace_root=None, bridge_port=None) -> BridgeResponse` — `:145-156`. Usado por `services/ado_pipeline_inference.py:277`.
- **Rutea por `config.LLM_BACKEND`, NO por el runtime elegido** — `:157` `backend = config.LLM_BACKEND.lower()`, con ramas `mock` (`:158`), `vscode_bridge` (`:160`), `copilot` (`:172`) **y al menos una cuarta, `claude_cli` (`:176`)** (corregido v2: el v1 enumeraba sólo 3).

> ⚠️ **Consecuencia dura, y es el corazón del diseño:** `copilot_bridge.invoke` **no honra** `runtime == "codex_cli"` ni `"claude_code_cli"`. Son dos ejes distintos (`LLM_BACKEND` vs. runtime de corrida). El único camino de esos dos runtimes es `run_agent`, que exige `ticket_id`.
> **Por eso el motor conversacional de este plan es DETERMINISTA** (§4, P3). La asistencia por LLM es una capa **opcional y declarada**, y —corregido v2— **se declara sobre el eje correcto**: `asistencia_llm` se deriva de `config.LLM_BACKEND` y es **igual para los 3 runtimes**, porque el runtime elegido no la cambia.

**Patrón conversacional a imitar — `backend/services/pipeline_session.py` (198 líneas):**

- `SESSION_VERSION = "1"`, `MAX_SESSION_BYTES = 8192`, `MAX_AUTO_RETRIES = 2` — `:10-12`. Constantes de módulo, **no flags**. Este plan hace lo mismo.
- `PIPELINE_SESSION_STATES` (8 estados, tupla cerrada) — `:15-24`; `TRANSITIONS` — `:27-36`; `TERMINAL_STATES` — `:38`.
- `@dataclass(frozen=True) class PipelineSession` — `:51-64`.
- `can_transition(origen, destino)` — `:67`, **NUNCA lanza** (`:71-73`).
- `advance(session, destino, **campos)` → `(sesion, motivo)` — `:76-93`; filtra campos inventados con `__dataclass_fields__` (`:87-90`) y **nunca lanza** (`:92-93`). Motivos reales: `"estado_terminal"`, `"transicion_ilegal"`, `"error_interno"`.
- `session_to_dict(s)` — `:96`, serialización 1:1 sin encoder custom.
- El módulo es **PURO**: "sin flask, sin config, sin IO, sin red, sin modelo" (`:3`).

**Molde de frontend a imitar — `frontend/src/components/devops/pipelineCopilotModel.ts` (251 líneas):**

- Docstring `:4-5` (corregido v2 — el v1 decía `:3-5`): *"El repo NO tiene RTL ni jsdom, asi que toda la logica testeable vive aca y el .tsx queda como cascaron de presentacion."*
- Exporta tipos + constantes espejo del backend + funciones puras. Su test es `frontend/src/components/devops/__tests__/pipelineCopilotModel.test.ts`.

**Molde de test de endpoint — `backend/tests/test_plan93_preflight_endpoint.py:25-45` (agregado v2, C17):** no hay fixture `app`/`client` en `tests/conftest.py`; cada archivo construye la suya con `create_app()` + flip de flag + `app.config["TESTING"] = True` + restauración en el `yield`.

**Guardianes de flags (los SEIS que este plan toca, verificados):**

1. `backend/config.py` — atributo de clase con `os.getenv("KEY", "true"/"false").lower() in ("1","true","yes")`. Molde exacto: `:1913-1917`.
2. `backend/services/harness_flags.py` — `FlagSpec(key=, type=, label=, description=, group=, env_only=, requires=, default=)`. Molde exacto: `:4216-4234`.
3. `backend/services/harness_flags.py` — `_CATEGORY_KEYS` (`:120`). Nota literal en **`:629`** (corregido v2 — el v1 decía `:626`): *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` (arriba) o el test..."*. Las tuplas concretas que este plan toca: **`"flujo_funcional"` en `:315`** y **`"capacidades_optin"` en `:467`**.
4. `backend/tests/test_harness_flags.py` — `_CURATED_DEFAULTS_ON` (`:467`). **Sólo para booleanas con `default=True`.** El meta-test es `test_default_known_only_for_curated` (`:1224`), que compara **conjuntos** (`assert known_keys == _CURATED_DEFAULTS_ON`), no cantidades.
5. `backend/services/harness_flags_help.py` — `PLAIN_HELP` (`:25`), texto llano de la UI. **No se deriva de `description`.**
6. **`backend/tests/test_harness_flags_requires.py` — `_REQUIRES_MAP_FROZEN` (`:120`) + `test_requires_map_is_frozen` (`:405`)** (agregado v2, **C3**). El test hace `actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}` y `assert actual == _REQUIRES_MAP_FROZEN`. **Toda FlagSpec nueva que declare `requires=` debe agregar su entrada, o esa suite se pone ROJA.**

> `test_flag_wiring.py::test_every_non_reserved_flag_is_wired` **no** se rompe con F0 sola: su corpus de "código productivo" **incluye `config.py`** (verificado en `tests/test_flag_wiring.py:29-53`), así que la key literal ya cuenta como consumo desde la primera fase.

**Guardianes de ratchet (verificados, y por qué cambia el orden de registro — C15):**

- `backend/tests/test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` (`:43-53`): **todo** archivo `tests/*.py` debe estar en el ratchet **o** en `tests/harness_ratchet_allowlist.txt`. Un archivo de test nuevo sin registrar pone esa suite en rojo **desde el commit que lo crea**.
- `::test_allowlist_no_se_solapa_con_ratchet` (`:56`) y `::test_ratchet_no_referencia_archivos_inexistentes` (`:79`): no se puede registrar un archivo que todavía no existe, ni tenerlo en los dos lados.
- `backend/tests/test_plan259_ratchet_script_parity.py`: `_PS1_LAG_MAX = 64` (`:46`) — el `.ps1` puede ir hasta 64 archivos detrás del `.sh`. **Registrar la misma cantidad en los dos deja el lag intacto.**
- Formato: `.ps1` con comillas y coma (`"tests/test_planNNN_x.py",`, molde `scripts/run_harness_tests.ps1:1006-1013`); `.sh` sin comillas ni coma (molde `scripts/run_harness_tests.sh:1090-1092`).

**Guardianes de ratchet del FRONTEND (agregado v2, C14) — son trampa de COMMIT y el v1 no los nombraba:**

`frontend/src/__tests__/` tiene una batería de ratchets con baseline congelado por archivo. Los que barren **todo** `src/` y por lo tanto alcanzan a los archivos nuevos de F6:

| Ratchet | Qué congela |
|---|---|
| `uiDebtRatchet.test.ts` | **por archivo**, la cantidad de `#hex` en `*.module.css` y de `style={{` en `*.tsx` (`:3-4`). La deuda **sólo puede BAJAR** |
| `a11yCss.test.ts`, `copyDebtRatchet.test.ts`, `formDebtRatchet.test.ts`, `formatDebtRatchet.test.ts`, `motionDebtRatchet.test.ts`, `adhocModalRatchet.test.ts`, `undoConfirmRatchet.test.ts`, `densityTokens.test.ts` | idem, cada uno sobre su eje |

**Regla dura derivada, y es binaria:** los archivos nuevos de F6 nacen con **CERO `#hex` en el `.module.css`** y **CERO `style={{` en el `.tsx`**. Tokens que **sí existen** (verificados barriendo los `--*:` declarados en `frontend/src/**/*.css`): `--accent`, `--accent-active`, `--bg-base`, `--bg-elev`, `--bg-panel`, `--border`, `--border-muted`, `--danger`, `--text-primary`, `--focus-ring`, `--card-radius`. **`--color-*` NO existe: no lo uses.**

### 3.2 Lo que NO EXISTE hoy, y en qué fase se construye

| # | Capacidad ausente | Evidencia de la ausencia | Fase |
|---|---|---|---|
| N1 | Campo **(1) disponible y correctamente configurado** por runtime | `capabilities_for` (`runtime_capabilities.py:70`, return `:134-146`) devuelve 11 claves y ninguna es disponibilidad | **F1** |
| N2 | Campo **(2) para qué tarea se recomienda** | No existe ninguna tabla de recomendación por tarea en `services/` | **F1** |
| N3 | Campo **(4) permisos / credenciales que necesita** | `_RUNTIME_BINS` (`run_preflight.py:31-34`) sólo nombra variables de binario, no credenciales | **F1** |
| N4 | Campo **(5) local vs. integración externa** | Deducible de `_RUNTIMES_REQUIRING_REPO` y de la bifurcación de `agent_runner.py:319/398`, pero **no declarado en ningún lado** | **F1** |
| N5 | Campo **(6) qué ocurre si la ejecución falla** | No existe | **F1** |
| N6 | **Disponibilidad sin disparar una corrida** | `run_preflight.check` exige `ticket=` (`:57-62`) y se invoca desde `agent_runner.run_agent` (`:182`); además se auto-desactiva con la flag (`:82-83`) | **F1** |
| N7 | **Anclaje vivo de los campos declarativos de la ficha** *(nuevo v2 — `[ADICIÓN ARQUITECTO]`)* | Ningún test hoy relaciona un texto declarativo con el código que describe: por eso el v1 pudo afirmar que `:857/:1067/:1259` rechazaban cuando auto-rellenan | **F1** |
| N8 | Cálculo de **completitud** del perfil y **banco de preguntas** derivado de lo que falta | No hay ningún símbolo de completitud en `client_profile*.py` | **F2** |
| N9 | **Lectura de procesos detectados desde `services/`** | `autodetect_process_catalog` **sólo existe como ruta Flask** (`api/client_profile.py:393`); no hay función de servicio equivalente (verificado: único match en todo el backend) — **C1** | **F2 (por parámetro) + F3 (el proveedor)** |
| N10 | **Sesión conversacional** del perfil (estados, transiciones, runtime pegado) | `pipeline_session.py` es del eje pipelines y no es reusable tal cual | **F3** |
| N11 | **Diff propuesto** del perfil (antes/después por path, con motivo) | `_deep_merge` (`:454`) mergea pero no reporta qué cambió | **F4** |
| N12 | **Aplicación** confirmada del diff sobre el perfil real | Hay `save_client_profile`, pero nadie lo llama desde un flujo conversacional | **F5** |
| N13 | Superficie de UI conversacional del perfil | `ClientProfileEditor.tsx` es puro formulario | **F6** |

### 3.3 Deuda de comentario detectada (no bloquea, se corrige en F7)

`backend/agent_runner.py:317` dice textualmente que `claude_code_cli` está *"bloqueado en endpoint (HTTP 501). Nunca debería llegar aquí."*

**Es FALSO y está desactualizado**, verificado por tres vías independientes:
1. **No hay ningún `501` en `api/agents.py`** (grep con cero coincidencias).
2. `_VALID_RUNTIMES` (`api/agents.py:337`) acepta los tres runtimes.
3. `agent_runner.py:398` despacha `claude_code_cli` a `start_claude_code_cli_run` normalmente.

Si alguien planificara sobre ese comentario, escribiría un plan con Claude "bloqueado" — un supuesto de capacidad falso. **F7 corrige el comentario** (una línea, sin cambio de comportamiento) y agrega el test que ancla la verdad.

---

## 4. Principios y guardarraíles

**P1 — El perfil tiene UN solo modelo y UN solo escritor.** El copiloto lee con `load_effective_client_profile`, valida con `validate_client_profile`, y escribe **exclusivamente** con `save_client_profile`. No hay store paralelo, no hay archivo nuevo de perfil, no se toca `PATCHABLE_PROFILE_KEYS`.

**P2 — El usuario elige el runtime ANTES, explícitamente, y con la ficha completa a la vista.** Sin runtime elegido, la sesión no arranca: el estado inicial es `eleccion_runtime` y la única transición legal desde ahí exige un `runtime` de `RUNTIMES`. El sistema **recomienda** (campo `recomendado_para` + una `recomendacion` calculada), pero **nunca elige**.

**P3 — El motor conversacional es DETERMINISTA; el LLM es una capa opcional y declarada.** El banco de preguntas, la detección de faltantes y la construcción del diff se derivan del schema del perfil y de fuentes deterministas que ya existen (`complete_client_profile`, `get_default_client_profile`) **más los candidatos que el endpoint le pasa por parámetro** (C1). Esto garantiza **paridad exacta en los 3 runtimes** sin ninguna plumería de LLM nueva.

> **Corrección v2 (C1):** el v1 listaba `autodetect_process_catalog` como fuente directa del motor. **No lo es**: es una ruta Flask (`api/client_profile.py:393`) y `services/` no importa `api/`. El motor **no la llama**; recibe `procesos_detectados: tuple[str, ...]` por parámetro, y el endpoint de F3 lo puebla usando las **mismas dos fuentes que usa la ruta** (`services.project_autoprofile` y `grounding_observatory`, ambas en `services/`). Con la tupla vacía la pregunta correspondiente degrada a texto libre — **visible, nunca muda**.

> **Corrección v2 (`asistencia_llm`):** el v1 hardcodeaba `"no_disponible"` para los dos CLI y `"segun_llm_backend"` para copilot, lo que contradice el glosario del propio plan (`LLM_BACKEND` es un eje **distinto** del runtime). Ahora `asistencia_llm` se **deriva de `config.LLM_BACKEND`** y es **igual para los 3 runtimes**, con `asistencia_llm_motivo` explicando que la asistencia por modelo no depende del runtime elegido sino del backend de LLM configurado.

**P4 — Fallback de CAPACIDAD sí; fallback de RUNTIME jamás.** (Resolución explícita de la tensión "paridad con fallback" vs. "sin fallback silencioso".)
- **LEGÍTIMO:** si el runtime elegido no puede algo, se **declara** y se degrada **visiblemente** (campo con valor `"no_disponible"` + `motivo` en castellano). El copiloto sigue funcionando en lo que sí puede.
- **PROHIBIDO:** cambiar de runtime por cuenta propia, en cualquier circunstancia, incluida la falla.
- Ante un fallo del runtime elegido, la respuesta **conserva `runtime_elegido` intacto**, informa el error, y expone `cambio_sugerido: {"runtime": ..., "motivo": ...}` **sin aplicarlo**. Cambiar exige un turno nuevo con `cambiar_runtime: true` del usuario.
- Verificado por `test_plan296_paridad_runtimes.py::test_fallo_no_cambia_el_runtime_elegido` y `::test_cambio_de_runtime_exige_bandera_explicita`.

**P5 — Se ve antes de aplicarse, y se confirma antes de guardarse.** El copiloto **siempre** produce un diff (`ProfilePatch`) que enumera cada cambio con `path`, `antes`, `despues`, `motivo` y `sensible`. Aplicar exige `confirm_token` derivado del diff: si el diff cambió, el token no valida y no se escribe nada.

**P6 — El copiloto NO toca credenciales, nunca.** Cualquier propuesta que contenga una key de `_SECRET_KEYS` (`client_profile.py:42-44`) se rechaza **antes** de llegar a `validate_client_profile`, con mensaje propio. Segundo candado: `_contains_secret_keys` es **recursivo** (`:196-211`), así que una key anidada también fuerza `ok=False` en el paso 8 de F5. Las credenciales de BD siguen yendo por su endpoint dedicado (`api/client_profile.py:492`), manejado por el operador a mano.

**P7 — Rieles de la casa, sin excepción.**
- `services/` **NO importa de `api/`**, en ningún nivel, ni perezosamente. El gate es por **AST**, no por grep (C5). Cuando el plan necesita la preferencia de runtime, llama a `runtime_capabilities.save_run_preference` / `load_run_preference` (ese módulo hace su propio import perezoso de `api.preferences`, `runtime_capabilities.py:326` y `:348`).
- **Cero threads nuevos.** `backend/app.py:641` dice textual "NO agregar threads nuevos" (corregido v2 — el v1 decía `:635-636`, donde está `mark_startup_writes_done()`); el patrón es `services.maintenance.register_maintenance_task()`. Este plan no crea ninguno: todo es request/response.
- **Mono-operador sin login/roles.** Ningún `403` de permiso. `403`/`404` sólo significan "flag apagada".
- **Toda flag/config del operador va por UI** (`env_only=False`).
- **`api_bp` ya pone `/api`.** Los blueprints se declaran con rutas **sin** el prefijo (C7).

**P8 — Sesión sin persistencia nueva.** La sesión viaja en el request/response (el frontend la devuelve tal cual la recibió), calcada de `PipelineSession` + `session_to_dict`. Tope duro `MAX_SESSION_BYTES = 8192` como constante de módulo, igual que `pipeline_session.py:11`. **No se crea ninguna tabla, ningún archivo de estado, ningún cache global.** La ÚNICA cosa que se persiste es la elección de runtime, y por el riel que ya existe (`save_run_preference`).

**P9 — Cero trabajo extra al operador, y backward-compatible.** Con las flags en su default, el `ClientProfileEditor` de hoy sigue funcionando **exactamente igual**; el copiloto aparece como un panel adicional. Con `STACKY_PROFILE_COPILOT_ENABLED=false`, la UI vuelve byte a byte al comportamiento previo.

**P10 — Los tests de este plan no tocan el sistema real del operador** *(nuevo v2, C6)*. Todo archivo de test que llegue a `save_client_profile`, `get_project_config` o `record_event` usa la fixture de aislamiento de §6/F5. **Ningún test escribe fuera de `tmp_path`.**

---

## 5. Flags

| Flag | Tipo | Default | Categoría | Justificación |
|---|---|---|---|---|
| `STACKY_PROFILE_COPILOT_ENABLED` | bool | **ON** | `flujo_funcional` | Conversa, detecta, recomienda y **muestra** el diff. No escribe nada. No consume tokens en reposo (no hay loop, daemon, barrido, polling ni prefetch: sólo responde a turnos que el operador manda). No cae en (A) ni en (B). |
| `STACKY_PROFILE_COPILOT_APPLY_ENABLED` | bool | **OFF** | `capacidades_optin` | **Causal (B):** escribe la sección `client_profile` en `projects/<NAME>/config.json`, que es la configuración real del proyecto del operador y gobierna el ruteo de agentes (`state_flow`, `tracker_state_machine`) y el contexto que se le inyecta a todo agente (`context_enrichment.build_client_profile_block`). Es escritura en un sistema real del operador. |

**Cableado exacto de cada flag (F0) — SEIS lugares, no cinco (C3):**

`STACKY_PROFILE_COPILOT_ENABLED` (nace **ON** ⇒ los TRES lugares del default ON):
1. `backend/config.py` — `os.getenv("STACKY_PROFILE_COPILOT_ENABLED", "true").lower() in ("1","true","yes")`
2. `backend/services/harness_flags.py` — `FlagSpec(..., default=True)`
3. `backend/tests/test_harness_flags.py` — la key **en `_CURATED_DEFAULTS_ON`** (`:467`)
4. `backend/services/harness_flags.py` — la key en `_CATEGORY_KEYS["flujo_funcional"]` (`:315`)
5. `backend/services/harness_flags_help.py` — entrada en `PLAIN_HELP` (`:25`)
6. **`_REQUIRES_MAP_FROZEN`: NO aplica** — esta flag **no declara `requires=`** (es el master).

`STACKY_PROFILE_COPILOT_APPLY_ENABLED` (nace **OFF** ⇒ **NINGÚN `default=`**):
1. `backend/config.py` — `os.getenv("STACKY_PROFILE_COPILOT_APPLY_ENABLED", "false").lower() in ("1","true","yes")`
2. `backend/services/harness_flags.py` — `FlagSpec(...)` **sin `default=`** y con `requires="STACKY_PROFILE_COPILOT_ENABLED"`
3. **NO** va en `_CURATED_DEFAULTS_ON` (ese set es sólo para booleanas con `default=True`)
4. `backend/services/harness_flags.py` — la key en `_CATEGORY_KEYS["capacidades_optin"]` (`:467`)
5. `backend/services/harness_flags_help.py` — entrada en `PLAIN_HELP`
6. **`backend/tests/test_harness_flags_requires.py` — entrada `"STACKY_PROFILE_COPILOT_APPLY_ENABLED": "STACKY_PROFILE_COPILOT_ENABLED"` en `_REQUIRES_MAP_FROZEN` (`:120-402`).** Sin esto, `test_requires_map_is_frozen` (`:405`) queda ROJO con `Extras: ['STACKY_PROFILE_COPILOT_APPLY_ENABLED']`.

> ⚠️ **Trampa a evitar:** `default_is_known()` es `spec.default is not None`. Poner `default=False` explícito en la FlagSpec de la flag OFF pone en **rojo** `test_default_known_only_for_curated` (`test_harness_flags.py:1224`). El `default=` se OMITE, no se pone en `False`.

---

## 6. Fases

> **Regla transversal nueva (C15):** **cada fase que crea un archivo `tests/test_plan296_*.py` lo registra en los DOS ratchets EN ESA MISMA FASE** (`.ps1` con comillas y coma, `.sh` sin comillas ni coma). F7 ya no los crea: los **verifica**. Motivo: `test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` (`:43-53`) se pone rojo desde el commit que crea un test no clasificado, y los ratchets son trampa de **commit**, no sólo de edición.

### F0 — Las dos flags nacen bien cableadas

**Objetivo:** registrar las 2 flags con sus guardianes (5 para la ON, 6 para la OFF), para que F1..F7 sólo las consuman.
**Valor:** el bloque de flags es atómico; hacerlo aparte evita que un rojo de arnés tumbe una fase de producto.

**Archivos a editar:**
- `Stacky Agents/backend/config.py` — 2 atributos nuevos, junto al bloque DevOps (molde `:1913-1917`).
- `Stacky Agents/backend/services/harness_flags.py` — 2 `FlagSpec` en `FLAG_REGISTRY` (molde `:4216-4234`) + `STACKY_PROFILE_COPILOT_ENABLED` en `_CATEGORY_KEYS["flujo_funcional"]` (`:315`) + `STACKY_PROFILE_COPILOT_APPLY_ENABLED` en `_CATEGORY_KEYS["capacidades_optin"]` (`:467`).
- `Stacky Agents/backend/services/harness_flags_help.py` — 2 entradas en `PLAIN_HELP` (`:25`).
- `Stacky Agents/backend/tests/test_harness_flags.py` — `STACKY_PROFILE_COPILOT_ENABLED` en `_CURATED_DEFAULTS_ON` (`:467`).
- **`Stacky Agents/backend/tests/test_harness_flags_requires.py` — entrada nueva en `_REQUIRES_MAP_FROZEN` (`:120-402`). (C3)**
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.sh` — registrar `tests/test_plan296_flags.py` en **los dos** (C15).

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan296_flags.py`

**Diff ilustrativo (`config.py`):**
```python
    # Plan 296 — Copiloto conversacional del perfil de cliente.
    # Default ON: conversa, detecta faltantes, recomienda y MUESTRA el diff.
    # No escribe nada y no consume tokens en reposo (no hay loop ni daemon).
    STACKY_PROFILE_COPILOT_ENABLED: bool = os.getenv(
        "STACKY_PROFILE_COPILOT_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 296 — Aplicar el diff propuesto sobre el client_profile real.
    # Default OFF — causal (B): escribe projects/<NAME>/config.json, la config
    # real del proyecto del operador (gobierna ruteo de agentes y el contexto
    # inyectado). NO va en _CURATED_DEFAULTS_ON (sólo default ON).
    STACKY_PROFILE_COPILOT_APPLY_ENABLED: bool = os.getenv(
        "STACKY_PROFILE_COPILOT_APPLY_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
```

**Casos de test (`test_plan296_flags.py`) — 10 (C3 suma el #10):**
1. `test_flag_conversacional_nace_on` — `config.STACKY_PROFILE_COPILOT_ENABLED is True` con el entorno limpio.
2. `test_flag_apply_nace_off` — `config.STACKY_PROFILE_COPILOT_APPLY_ENABLED is False`.
3. `test_ambas_flags_estan_en_el_registry` — las dos keys están en `{s.key for s in FLAG_REGISTRY}`.
4. `test_apply_no_declara_default` — `next(s for s in FLAG_REGISTRY if s.key == "STACKY_PROFILE_COPILOT_APPLY_ENABLED").default is None`.
5. `test_conversacional_declara_default_true` — `... .default is True`.
6. `test_apply_requiere_al_master` — `... .requires == "STACKY_PROFILE_COPILOT_ENABLED"`.
7. `test_ambas_son_editables_por_ui` — `spec.env_only is False` en las dos.
8. `test_ambas_tienen_categoria` — cada key aparece en exactamente una tupla de `_CATEGORY_KEYS`; el assert imprime las categorías encontradas.
9. `test_ambas_tienen_ayuda_llana` — las dos keys están en `harness_flags_help.PLAIN_HELP`.
10. **`test_apply_esta_en_el_mapa_requires_congelado` (C3)** — `from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN`; `assert _REQUIRES_MAP_FROZEN.get("STACKY_PROFILE_COPILOT_APPLY_ENABLED") == "STACKY_PROFILE_COPILOT_ENABLED"`. El assert imprime el valor real encontrado. (Molde: `tests/test_fitness_flags.py:10,69`.)

**Comando de test:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_flags.py" -q
```

**Criterio de aceptación BINARIO:**
- `test_plan296_flags.py`: **10 passed, 0 failed**.
- **Línea base + delta sobre TRES suites ajenas** (el v1 medía dos; C3 agrega la tercera, que era justamente la que el plan iba a romper). Se mide `(passed, failed)` en el commit base ANTES de tocar nada; tras F0 el `failed` debe ser **≤** el basal y el `passed` **≥** el basal:
  ```
  "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
  "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
  "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
  ```
  **`test_harness_flags_help.py` tiene rojos de fábrica: no se exige verde absoluto, se exige `failed` no mayor que el basal.** Lo mismo vale para las otras dos.
- `grep -c "test_plan296_flags" scripts/run_harness_tests.ps1` = **1** y lo mismo en el `.sh`.

**Flag que la protege:** ninguna (es la fase que las crea).
**Impacto por runtime:** ninguno — las flags son transversales; ningún runtime cambia de comportamiento en F0.
**Trabajo del operador: ninguno.**

---

### F1 — La ficha del runtime deja de estar a medias: 7 de 7, y la disponibilidad se consulta sin correr nada

**Objetivo:** un módulo puro que, para cada uno de los 3 runtimes, responda los **siete** puntos que el operador exige, con la disponibilidad medida de verdad, **sin disparar una corrida** y **sin exagerar ninguna exigencia**.
**Valor:** el usuario elige el runtime sabiendo qué elige. Cierra N1..N7.

**Archivo a crear:** `Stacky Agents/backend/services/runtime_profile.py`
**Archivos a editar:** los dos ratchets (registrar `tests/test_plan296_runtime_profile.py`).

> **Nota de orden:** el endpoint de la ficha vive en el blueprint de F3 (`api/profile_copilot.py`) para no crear dos blueprints. F1 entrega **el servicio puro y su test**; F3 lo expone. Esto mantiene F1 sin ninguna dependencia de Flask.

**Regla de import obligatoria (C16):** el módulo hace `from services import run_preflight` y llama **calificado** (`run_preflight._binary_resolvable(...)`, `run_preflight._get_runtime_bin(...)`). **PROHIBIDO** `from services.run_preflight import _binary_resolvable`: eso liga el nombre en tiempo de import y el `monkeypatch.setattr(run_preflight, ...)` del caso 2 **no tendría efecto**, con lo que el test pasaría por la razón equivocada.

**Símbolos exactos de `services/runtime_profile.py`:**

```python
"""Plan 296 F1 - La ficha COMPLETA de cada runtime.

PURO: sin flask, sin red, sin escritura. Importa `runtime_capabilities` y el
modulo `run_preflight` (para sus dos helpers puros). El gate de "no importa la
capa web" NO se verifica por texto sino por AST en el test: ver C5.
"""
from __future__ import annotations

FICHA_VERSION = "1"

#: Las 7 claves que el operador exige, en orden. Cerrado.
FICHA_CAMPOS: tuple[str, ...] = (
    "disponible",          # (1) ¿está y está bien configurado?
    "recomendado_para",    # (2) ¿para qué tarea conviene?
    "capacidades",         # (3) ¿qué va a usar?
    "credenciales",        # (4) ¿qué permisos/credenciales pide?
    "ejecucion",           # (5) ¿local o integración externa?
    "si_falla",            # (6) ¿qué pasa si la ejecución falla?
    "como_cambiar",        # (7) ¿cómo cambio de runtime antes de ejecutar?
)

#: (2) Para qué tarea se recomienda. Declarativo, cerrado sobre RUNTIMES.
RECOMENDADO_PARA: dict[str, tuple[str, ...]] = {
    "claude_code_cli": (
        "Cambios que cruzan varios archivos del repositorio",
        "Trabajo que necesita razonar sobre el código antes de escribirlo",
        "Tareas donde el nivel de esfuerzo importa (es el único con esfuerzo nativo)",
    ),
    "codex_cli": (
        "Cambios acotados a pocos archivos",
        "Tareas repetitivas con un patrón claro",
        "Corridas donde interesa acotar el gasto por presupuesto de turnos",
    ),
    "github_copilot": (
        "Consultas y redacción sin repositorio local",
        "Primer contacto: es el único que no necesita repo git",
        "Tareas cortas dentro del editor",
    ),
}

#: (4) Qué necesita para funcionar. NUNCA se muestran valores, sólo nombres.
CREDENCIALES: dict[str, tuple[str, ...]] = {
    "claude_code_cli": ("Binario `claude` en el PATH (o ruta absoluta en CLAUDE_CODE_CLI_BIN)",
                        "Sesión iniciada en el CLI de Claude, fuera de Stacky"),
    "codex_cli":       ("Binario `codex` en el PATH (o ruta absoluta en CODEX_CLI_BIN)",
                        "Sesión iniciada en el CLI de Codex, fuera de Stacky"),
    "github_copilot":  ("Suscripción activa de GitHub Copilot",
                        "El puente del editor levantado (LLM_BACKEND en copilot o vscode_bridge)"),
}

#: (5) Dónde corre. Derivado de agent_runner.py:319/398 y de _RUNTIMES_REQUIRING_REPO.
EJECUCION: dict[str, str] = {
    "claude_code_cli": "local",
    "codex_cli":       "local",
    "github_copilot":  "integracion_externa",
}

#: (6) Qué ocurre si falla. Texto en castellano, sin jerga.
SI_FALLA: dict[str, str] = {
    "claude_code_cli": ("La corrida queda marcada como fallida con el motivo. No se cambia "
                        "de runtime: Stacky te ofrece reintentar o elegir otro vos mismo."),
    "codex_cli":       ("La corrida queda marcada como fallida con el motivo. Si se agotó el "
                        "presupuesto de turnos se dice explícitamente. No se cambia de runtime."),
    "github_copilot":  ("Si el puente del editor no responde, la corrida falla con el motivo. "
                        "No se cambia de runtime."),
}

#: (7) Cómo cambiar. Único texto, igual para los 3: es una propiedad del flujo.
COMO_CAMBIAR = ("Antes de ejecutar cualquier acción podés cambiar el runtime desde el "
                "selector del copiloto. El cambio exige una acción tuya: Stacky nunca "
                "lo cambia solo, ni siquiera cuando el runtime elegido falla.")

#: C2 — MEDIDO, no supuesto. Solo UN camino rechaza por falta de archivo de agente.
#: api/agents.py:480 (rechaza con "missing_vscode_agent_filename", :488).
EXIGE_AGENTE_VSCODE: dict[str, bool] = {
    "claude_code_cli": True,   # solo en POST /agents/run
    "codex_cli":       True,   # solo en POST /agents/run
    "github_copilot":  False,
}

#: C2 — los OTROS tres caminos AUTO-RELLENAN en vez de rechazar.
#: api/agents.py:858, :1069, :1261.
AGENTE_VSCODE_POR_DEFECTO: dict[str, str] = {
    "epica_desde_brief":        "BusinessAgent.agent.md",
    "analisis_de_incidencia":   "IncidentAnalyst.agent.md",
    "resolucion_dev_incidencia": "IncidentDevResolver.agent.md",
}

def binary_availability(runtime: str) -> dict: ...
def asistencia_llm() -> dict: ...          # C-corrección: por LLM_BACKEND, no por runtime
def runtime_profile(runtime: str, *, project_name: str | None = None) -> dict: ...
def all_runtime_profiles(*, project_name: str | None = None) -> list[dict]: ...
def recomendar_runtime(fichas: list[dict]) -> dict: ...
```

**Contrato de `binary_availability(runtime) -> dict`:**
```python
{
  "runtime": str,
  "requiere_binario": bool,           # runtime in run_preflight._RUNTIME_BINS
  "binario": str | None,              # nombre resuelto por _get_runtime_bin, o None
  "binario_resoluble": bool | None,   # _binary_resolvable(...), o None si no aplica
  "requiere_repo_git": bool,          # runtime in run_preflight._RUNTIMES_REQUIRING_REPO
}
```
- **Nunca lanza.** Cualquier excepción al resolver ⇒ `binario_resoluble = False` y `motivo` en la ficha.
- **NO llama a `run_preflight.check`** (que se auto-desactiva con `STACKY_RUN_PREFLIGHT_GATE_ENABLED`, `run_preflight.py:82-83`). Usa sólo `run_preflight._get_runtime_bin` (`:263`) y `run_preflight._binary_resolvable` (`:276`), **calificados** (C16).

**Contrato de `asistencia_llm() -> dict` (corrección v2 — se deriva del eje correcto):**
```python
{
  "modo": "segun_llm_backend",
  "llm_backend": "<config.LLM_BACKEND en minúsculas>",
  "motivo": ("La asistencia por modelo NO depende del runtime que elijas: depende de "
             "LLM_BACKEND, que es otro eje. El copiloto del perfil no la usa: su motor "
             "es determinista y da el mismo resultado con los tres runtimes."),
}
```
El mismo dict para los 3 runtimes. **Nunca lanza**: si `config` no se puede leer, `llm_backend = "desconocido"`.

**Contrato de `runtime_profile(runtime, *, project_name=None) -> dict`:**
```python
{
  "runtime": "claude_code_cli",
  "conocido": True,                       # runtime in runtime_capabilities.RUNTIMES
  "version_ficha": "1",
  # (1)
  "disponible": True,
  "disponibilidad_detalle": {...},        # binary_availability(...)
  "disponibilidad_motivo": "",            # "" si disponible; texto en castellano si no
  # (2)
  "recomendado_para": [...],
  # (3)
  "capacidades": {                        # capabilities_for(runtime) tal cual + 3 derivados
      ... las 11 claves de runtime_capabilities.capabilities_for ...,
      "exige_agente_vscode": True,             # C2 — SOLO api/agents.py:480
      "exige_agente_vscode_alcance": "Sólo al lanzar un agente desde el tablero. "
                                     "En épicas desde brief y en incidencias, Stacky "
                                     "elige el archivo de agente por vos.",
      "agente_vscode_por_defecto": {...},      # C2 — AGENTE_VSCODE_POR_DEFECTO
      "asistencia_llm": {...},                 # asistencia_llm(), igual para los 3
  },
  # (4)
  "credenciales": [...],
  # (5)
  "ejecucion": "local",
  # (6)
  "si_falla": "...",
  # (7)
  "como_cambiar": "...",
}
```

**Regla de `disponible` (binaria, sin ambigüedad):**
- `github_copilot` ⇒ `disponible = True` siempre (no tiene binario que resolver); `disponibilidad_motivo = ""`.
- `claude_code_cli` / `codex_cli` ⇒ `disponible = binario_resoluble`. Si `False`, `disponibilidad_motivo = f"No encontré el programa '{binario}'. Instalalo o indicá su ruta completa."`.
- Runtime desconocido ⇒ `conocido = False`, `disponible = False`, motivo `"Runtime desconocido."`, y **las 7 claves presentes igual** (nunca un dict incompleto).

**Regla de `recomendar_runtime(fichas)`:** determinista y explicada.
```python
{"runtime": "github_copilot", "motivo": "Es el único disponible ahora mismo."}
```
Orden: (a) si hay exactamente uno con `disponible=True`, ése, motivo `"Es el único disponible ahora mismo."`; (b) si hay varios, el primero en el orden `("claude_code_cli", "codex_cli", "github_copilot")` que esté disponible, motivo `"Está disponible y es el que más capacidades declara para trabajo sobre el repositorio."`; (c) si ninguno, `{"runtime": None, "motivo": "Ninguno está disponible: revisá la ficha de cada uno."}`.
**`recomendar_runtime` NUNCA decide: sólo sugiere. El caller no la aplica.**

#### `[ADICIÓN ARQUITECTO]` — `FICHA_ANCLAJES`: la ficha no puede envejecer mintiendo

**El problema que resuelve (medido, no hipotético):** el v1 de este plan afirmó que `api/agents.py:857/:1067/:1259` *rechazaban* la corrida cuando en realidad *auto-rellenan*. Los tres anclajes **existían y estaban en la línea correcta** — lo falso era la descripción. Ningún test del repo puede hoy detectar eso, porque nada relaciona un texto declarativo con el código que describe. Cinco planes seguidos (286-292) cayeron por esta misma forma de defecto.

**El mecanismo:** el módulo declara, junto a cada campo declarativo, el **literal exacto que debe seguir existiendo** en el archivo que lo sostiene. Un test abre esos archivos y lo verifica. Si alguien renombra el error, cambia el default o borra la rama, **la ficha se pone roja en vez de mentir**.

```python
#: [ADICIÓN ARQUITECTO] Cada campo declarativo, atado al literal que lo sostiene.
#: (ruta relativa a backend/, literal que DEBE seguir existiendo, campo que respalda)
FICHA_ANCLAJES: tuple[tuple[str, str, str], ...] = (
    ("api/agents.py",                    "missing_vscode_agent_filename", "exige_agente_vscode"),
    ("api/agents.py",                    "BusinessAgent.agent.md",        "agente_vscode_por_defecto"),
    ("api/agents.py",                    "IncidentAnalyst.agent.md",      "agente_vscode_por_defecto"),
    ("api/agents.py",                    "IncidentDevResolver.agent.md",  "agente_vscode_por_defecto"),
    ("services/run_preflight.py",        "_RUNTIMES_REQUIRING_REPO",      "disponible"),
    ("services/run_preflight.py",        "CLAUDE_CODE_CLI_BIN",           "credenciales"),
    ("services/run_preflight.py",        "CODEX_CLI_BIN",                 "credenciales"),
    ("services/runtime_capabilities.py", "RUNTIMES",                      "runtime"),
    ("agent_runner.py",                  "start_codex_cli_run",           "ejecucion"),
    ("agent_runner.py",                  "start_claude_code_cli_run",     "ejecucion"),
)
```

Restricciones respetadas: sin flag nueva, sin trabajo del operador, sin red, determinista, **idéntico en los 3 runtimes**, y no toca ningún archivo de la sesión paralela.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_runtime_profile.py`

**Casos — 17 declarados, 18 colectados (el caso 2 está parametrizado sobre los dos estados de la flag: 17 − 1 + 2 = 18):**
1. `test_ficha_tiene_los_siete_campos_para_los_tres_runtimes` — para cada `r` en `RUNTIMES`: `set(FICHA_CAMPOS) <= set(runtime_profile(r))`. **(K1)**
2. `test_disponibilidad_no_depende_del_gate_de_preflight` — **`@pytest.mark.parametrize("gate", [True, False])`** (C4/C18): con `config.STACKY_RUN_PREFLIGHT_GATE_ENABLED` forzada a `gate` y `run_preflight._binary_resolvable` monkeypatcheado a `lambda _: False`, `runtime_profile("codex_cli")["disponible"] is False` **en los dos estados**. **(K2)**
3. `test_disponibilidad_no_dispara_ninguna_corrida` — `agent_runner.run_agent` monkeypatcheado a `raise AssertionError("no debe correrse")`; `all_runtime_profiles()` no lanza.
4. `test_copilot_no_requiere_binario_ni_repo` — `binary_availability("github_copilot")["requiere_binario"] is False` y `["requiere_repo_git"] is False`.
5. `test_cli_requieren_repo_git` — para `claude_code_cli` y `codex_cli`, `["requiere_repo_git"] is True`.
6. `test_exige_agente_vscode_es_true_solo_para_los_dos_cli` — `github_copilot` ⇒ `False`; los otros dos ⇒ `True`. **(C2)**
7. **`test_exige_agente_vscode_declara_su_alcance` (nuevo, C2)** — `capacidades["exige_agente_vscode_alcance"]` no vacío **y** menciona que en épicas e incidencias Stacky lo elige solo. Assert sobre el **mensaje**.
8. **`test_agente_vscode_por_defecto_trae_los_tres_caminos` (nuevo, C2)** — `set(AGENTE_VSCODE_POR_DEFECTO.values()) == {"BusinessAgent.agent.md", "IncidentAnalyst.agent.md", "IncidentDevResolver.agent.md"}`.
9. `test_asistencia_llm_es_la_misma_para_los_tres` — `runtime_profile(r)["capacidades"]["asistencia_llm"]` idéntico para los 3, con `motivo` no vacío que nombra `LLM_BACKEND`. **(corrección v2)**
10. `test_asistencia_llm_nunca_lanza_sin_config` — con `config.LLM_BACKEND` inaccesible, `llm_backend == "desconocido"`.
11. `test_runtime_desconocido_devuelve_ficha_completa_y_no_disponible` — `runtime_profile("gpt5_cli")` trae las 7 claves, `conocido is False`, `disponible is False`.
12. `test_binary_availability_nunca_lanza` — con `run_preflight._get_runtime_bin` monkeypatcheado a `raise RuntimeError`, devuelve dict con `binario_resoluble is False`.
13. `test_recomendar_no_devuelve_runtime_no_disponible` — con las 3 fichas forzadas a `disponible=False`, `recomendar_runtime(...)["runtime"] is None`.
14. `test_recomendar_explica_el_motivo` — `motivo` no vacío en los tres escenarios (uno, varios, ninguno).
15. `test_capacidades_conserva_las_once_claves_de_capabilities_for` — `set(capabilities_for(r)) <= set(runtime_profile(r)["capacidades"])`.
16. **`test_no_importa_la_capa_web` (reescrito, C5)** — **por AST, no por texto**:
    ```python
    import ast, pathlib
    src = pathlib.Path(runtime_profile.__file__).read_text(encoding="utf-8")
    arbol = ast.parse(src)
    ofensores = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            ofensores += [a.name for a in nodo.names if a.name.split(".")[0] == "api"]
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] == "api":
                ofensores.append(nodo.module)
    assert ofensores == [], f"services/ no puede importar api/. Ofensores: {ofensores}"
    ```
    **Motivo del cambio:** el gate por `"api." not in inspect.getsource(...)` era **False por construcción**, porque el docstring del propio módulo nombra el patrón. Es el gotcha "un comentario que NOMBRA el patrón rompe el gate por grep".
17. **`test_cada_campo_declarativo_tiene_su_anclaje_vivo` `[ADICIÓN ARQUITECTO]`** — para cada `(ruta, literal, campo)` de `FICHA_ANCLAJES`: el archivo existe y contiene el literal. El assert imprime **la lista de anclajes muertos con su campo**, no un booleano pelado:
    ```
    assert muertos == [], f"Anclajes de la ficha que ya no existen en el codigo: {muertos}"
    ```

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_runtime_profile.py" -q
```

**Criterio BINARIO:** **18 passed, 0 failed** (17 casos, el #2 parametrizado ×2 ⇒ 17 − 1 + 2 = 18). El número se lee de la línea final de pytest, no se estima.
**Registro en ratchets (C15):** `tests/test_plan296_runtime_profile.py` en el `.ps1` **y** en el `.sh`.
**Flag:** ninguna propia (módulo puro). Su exposición HTTP la gatea `STACKY_PROFILE_COPILOT_ENABLED` en F3.
**Impacto por runtime:** los tres reciben ficha de 7 campos. Degradación visible: el que no tiene binario resoluble sale `disponible=False` **con motivo**. `asistencia_llm` es idéntica para los tres porque depende de otro eje. **Ningún runtime se sustituye por otro.**
**Trabajo del operador: ninguno.**

---

### F2 — Qué falta, qué está mal, cuánto llevamos: la completitud y el banco de preguntas

**Objetivo:** un módulo puro que, dado un proyecto, diga qué secciones del perfil ya están (y no se vuelven a preguntar), cuáles faltan, qué inconsistencias hay, y **cuál es la próxima pregunta**.
**Valor:** cierra N8 y N9 (mitad de servicio) y hace posibles los KPI K3 y K4.

**Archivo a crear:** `Stacky Agents/backend/services/profile_completeness.py`
**Archivos a editar:** los dos ratchets (registrar `tests/test_plan296_completitud.py`).

**Símbolos exactos:**
```python
SECCIONES_REQUERIDAS = ("code_layout", "language", "tracker_state_machine")   # espejo de client_profile._REQUIRED_SECTIONS
SECCIONES_OPCIONALES = ("database", "build", "conventions", "docs_indexes",
                        "terminology", "extensions")                          # espejo de _OPTIONAL_SECTIONS
SECCIONES_SENSIBLES = ("tracker_state_machine", "state_flow", "database")

@dataclass(frozen=True)
class Pregunta:
    id: str            # "code_layout.roots"
    seccion: str       # "code_layout"
    texto: str         # castellano, sin jerga
    tipo: str          # "texto" | "lista" | "eleccion" | "si_no"
    opciones: tuple[str, ...] = ()   # sólo para tipo "eleccion"
    obligatoria: bool = True
    motivo: str = ""   # por qué se pregunta, en una frase

def estado_perfil(project_name: str) -> dict: ...
def preguntas_pendientes(estado: dict, *, estados_validos: tuple[str, ...] = (),
                         tipos_work_item: tuple[str, ...] = (),
                         procesos_detectados: tuple[str, ...] = ()) -> list[Pregunta]: ...
def proxima_pregunta(estado: dict, ya_respondidas: tuple[str, ...], **kw) -> Pregunta | None: ...
def completitud(estado: dict) -> dict: ...
```

> **C1 — `procesos_detectados` es un PARÁMETRO, no una llamada.** `autodetect_process_catalog` **es una ruta Flask** (`api/client_profile.py:393`), no un servicio, y `services/` no importa `api/`. El endpoint de F3 arma la tupla desde las **mismas dos fuentes que usa esa ruta**, ambas en `services/` (`services.project_autoprofile` y `grounding_observatory`), y se la pasa. **Con la tupla vacía la pregunta de procesos degrada a `tipo="texto"` — visible, nunca muda.** Es la misma disciplina que ya se aplicaba a `estados_validos`.

**Contrato de `estado_perfil(project_name) -> dict`:**
```python
{
  "proyecto": "RIPLEY",
  "tracker_type": "azure_devops",            # get_project_tracker_type(project_name)
  "tiene_perfil": True,                      # has_client_profile(project_name)
  "perfil": {...},                           # load_effective_client_profile(project_name)
  "secciones_presentes": ["code_layout", ...],
  "secciones_faltantes_requeridas": ["tracker_state_machine"],
  "secciones_faltantes_opcionales": ["database", ...],
  "validacion": {"ok": True, "errors": [], "warnings": [...], "normalized": {...}},  # ValidationResult.to_dict()
  "warnings_de_seccion_ausente": ["tracker_state_machine"],   # C12 — el único indicador que cambia
  "inconsistencias": [ {"seccion": "...", "detalle": "...", "origen": "validacion"|"path_check"} ],
}
```
- Una sección **cuenta como presente** si está en el perfil, es un `dict`, y **no está vacía**. Un `{}` cuenta como AUSENTE (es el caso real de un perfil recién sembrado del template): esto es lo que hace que K4 sea honesto.
- **`warnings_de_seccion_ausente` (nuevo v2, C12):** se extrae de los warnings con la forma exacta `f"client_profile.{seccion} ausente — el agente preguntará al operador."` (`client_profile.py:304`). **Es el indicador que discrimina**, porque `validate_client_profile({}).ok` ya es `True` hoy.

**Mapeo de `inconsistencias` — las CUATRO formas reales de mensaje (corregido v2, C13).** El v1 decía "por prefijo `client_profile.<seccion>`", que cubre sólo la primera. Medidas abriendo el archivo:

| # | Forma real del mensaje | Origen | Sección asignada |
|---|---|---|---|
| 1 | `client_profile.<seccion> debe ser <tipo>, recibí <tipo>` | `_check_section_type`, `:140` | `<seccion>` (segundo componente tras el punto) |
| 2 | `tracker_state_machine.<rol>[...] debe ser ...` | `_check_tracker_state_machine` `:148,:156,:160,:163` y `_check_by_work_item_type` `:180-192` | `"tracker_state_machine"` (primer componente) |
| 3 | `client_profile no debe contener secretos. Claves detectadas: ...` | `:287-290` | `"general"` con `sensible=True` |
| 4 | cualquier otra (p. ej. `_check_state_flow`, `:322`; `schema_version ...`, `:297-300`) | varias | `"general"` |

**Regla determinista:** tomar el primer token hasta el primer espacio; si empieza con `client_profile.` ⇒ sección = lo que sigue hasta el siguiente `.`; si el primer componente está en `SECCIONES_REQUERIDAS + SECCIONES_OPCIONALES + ("state_flow",)` ⇒ ésa; si no ⇒ `"general"`. **Nunca se pierde un mensaje: todo error o warning termina en alguna entrada.**

**Contrato de `completitud(estado) -> dict`:**
```python
{
  "requeridas_ok": 2, "requeridas_total": 3,
  "opcionales_ok": 1, "opcionales_total": 6,
  "porcentaje": 66,           # int, floor(requeridas_ok / requeridas_total * 100). Sólo requeridas.
  "listo_para_usar": False,   # requeridas_ok == requeridas_total AND validacion["ok"] is True
                              #                AND warnings_de_seccion_ausente == []   (C12)
}
```

**Regla anti-repetición (el corazón de K4):** `preguntas_pendientes(estado, ...)` **excluye toda sección presente**. `proxima_pregunta` además excluye los ids en `ya_respondidas` y devuelve primero las obligatorias, en el orden de `SECCIONES_REQUERIDAS`. Si no queda ninguna, devuelve `None`.

**Adaptación por contexto ("preguntas inteligentes"):** el banco se adapta por `tracker_type` y por los tres parámetros de contexto. Para `azure_devops`, la pregunta de `tracker_state_machine` ofrece como `opciones` los estados reales que el endpoint obtiene de `api/client_profile.py::_valid_states_for` (`:132`) y los tipos de `_work_item_types_for` (`:102`). **Con las tuplas vacías la pregunta degrada a `tipo="texto"` — visible, nunca muda.**

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_completitud.py`

**Casos — 16 declarados, 16 colectados (sin `parametrize`):**
1. `test_perfil_vacio_falta_las_tres_requeridas` — `estado_perfil` sobre un proyecto sin perfil ⇒ `secciones_faltantes_requeridas == list(SECCIONES_REQUERIDAS)`.
2. `test_seccion_ya_completa_no_genera_pregunta` — con `code_layout` poblado, ningún `Pregunta.seccion == "code_layout"` en `preguntas_pendientes`. **(K4)**
3. `test_seccion_vacia_cuenta_como_ausente` — `{"code_layout": {}}` ⇒ `code_layout` en faltantes.
4. `test_completitud_solo_cuenta_requeridas` — 3/3 requeridas y 0/6 opcionales ⇒ `porcentaje == 100`.
5. `test_listo_para_usar_exige_validacion_ok` — con las 3 requeridas presentes pero `validate_client_profile` devolviendo `ok=False` (perfil con una key **anidada** de `_SECRET_KEYS`, que `_contains_secret_keys` detecta por ser recursivo, `:196-211`), `listo_para_usar is False`.
6. **`test_listo_para_usar_exige_cero_warnings_de_seccion_ausente` (nuevo, C12)** — con las 3 secciones presentes pero un warning de la forma `client_profile.<seccion> ausente`, `listo_para_usar is False`. El assert nombra el warning.
7. `test_proxima_pregunta_respeta_ya_respondidas` — pasar el id de la primera ⇒ devuelve la segunda.
8. `test_proxima_pregunta_devuelve_none_cuando_no_falta_nada`.
9. `test_obligatorias_van_antes_que_opcionales` — el índice de la última obligatoria < índice de la primera opcional.
10. `test_estados_validos_vacios_degradan_a_texto_libre` — `preguntas_pendientes(estado, estados_validos=())` ⇒ la pregunta de `tracker_state_machine` tiene `tipo == "texto"` y `opciones == ()`.
11. `test_estados_validos_poblados_dan_eleccion` — con `estados_validos=("New","Active","Closed")` ⇒ `tipo == "eleccion"` y `opciones == ("New","Active","Closed")`.
12. **`test_procesos_detectados_vacios_no_generan_pregunta_muda` (nuevo, C1)** — `preguntas_pendientes(estado, procesos_detectados=())` ⇒ la pregunta de procesos existe, tiene `tipo == "texto"`, `opciones == ()` y `texto` no vacío.
13. **`test_procesos_detectados_poblados_dan_eleccion` (nuevo, C1)** — con `procesos_detectados=("Mul2Bane","RSCore")` ⇒ `tipo == "eleccion"` y esas dos opciones.
14. **`test_inconsistencias_cubren_las_cuatro_formas` (reforzado, C13)** — cuatro sub-asserts en un solo test, uno por forma de la tabla: (1) `code_layout` como `list` ⇒ sección `code_layout`; (2) `tracker_state_machine.functional` como `list` ⇒ sección `tracker_state_machine`; (3) perfil con `password` ⇒ sección `general` y `sensible is True`; (4) `schema_version` = 99 ⇒ sección `general`. **Cada assert compara el MENSAJE** (`detalle` contiene el texto real), nunca un conteo.
15. `test_toda_pregunta_tiene_texto_y_motivo_no_vacios` — para las 9 secciones + la de procesos.
16. **`test_no_importa_la_capa_web` (reescrito, C5)** — mismo gate por **AST** que F1 caso 16, aplicado a `services/profile_completeness.py`.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_completitud.py" -q
```

**Criterio BINARIO:** **16 passed, 0 failed**.
**Registro en ratchets (C15):** `tests/test_plan296_completitud.py` en el `.ps1` **y** en el `.sh`.
**Flag:** ninguna propia (módulo puro). Gate en F3.
**Impacto por runtime:** **idéntico en los 3** — es determinista, no consulta ningún modelo. Cero degradación.
**Trabajo del operador: ninguno.**

---

### F3 — La sesión: máquina de estados, el runtime pegado, y el turno

**Objetivo:** la conversación como máquina de estados cerrada, con el runtime elegido pegado a la sesión y una regla explícita que impide cambiarlo solo.
**Valor:** cierra N10, la mitad de endpoint de N9, y materializa P2, P4 y P8.

**Archivos a crear:**
- `Stacky Agents/backend/services/profile_copilot_session.py`
- `Stacky Agents/backend/api/profile_copilot.py` (blueprint `profile_copilot_bp`)

**Archivos a editar:**
- `Stacky Agents/backend/api/__init__.py` — importar y registrar `profile_copilot_bp` siguiendo el molde exacto de `client_profile_bp`: **import en `:10`**, **registro en `:152`** (corregido v2 — el v1 decía `:148`). Ver también los moldes comentados de `:133` (pipeline_copilot) y `:140` (workbench).
- los dos ratchets (registrar `tests/test_plan296_session.py`).

**`services/profile_copilot_session.py` (PURO: sin flask, sin config, sin IO, sin red, sin modelo):**
```python
SESSION_VERSION = "1"
MAX_SESSION_BYTES = 8192          # espejo de pipeline_session.py:11
MAX_PREGUNTAS = 40                # tope duro de turnos de una sesión

#: Los 7 estados. Cerrado.
PROFILE_SESSION_STATES = (
    "eleccion_runtime",  # 1. todavía no eligió runtime — NADA arranca antes
    "diagnostico",       # 2. runtime elegido; se leyó el perfil y se sabe qué falta
    "preguntando",       # 3. hay una pregunta abierta
    "propuesta",         # 4. hay un diff armado y visible
    "confirmando",       # 5. esperando confirmación explícita
    "aplicado",          # 6. terminal — el perfil quedó escrito
    "detenido",          # 7. terminal — con causa declarada
)

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "eleccion_runtime": ("diagnostico", "detenido"),
    "diagnostico":      ("preguntando", "propuesta", "detenido"),
    "preguntando":      ("preguntando", "propuesta", "detenido"),
    "propuesta":        ("confirmando", "preguntando", "detenido"),
    "confirmando":      ("aplicado", "propuesta", "detenido"),
    "aplicado":         (),
    "detenido":         (),
}
TERMINAL_STATES = ("aplicado", "detenido")

@dataclass(frozen=True)
class ProfileCopilotSession:
    state: str = "eleccion_runtime"
    proyecto: str = ""
    runtime_elegido: str = ""              # uno de runtime_capabilities.RUNTIMES
    tracker_type: str = ""
    pregunta_actual: str = ""              # id de Pregunta
    respondidas: tuple[str, ...] = ()
    respuestas: tuple[tuple[str, str], ...] = ()   # (id_pregunta, texto) — serializable
    patch_ref: str = ""                    # hash del diff, NUNCA el diff entero
    turnos: int = 0
    motivo_detencion: str = ""
    version: str = SESSION_VERSION

def can_transition(origen: str, destino: str) -> bool: ...          # NUNCA lanza
def advance(s, destino, **campos) -> tuple[ProfileCopilotSession, str]: ...  # NUNCA lanza
def session_to_dict(s) -> dict: ...
def session_from_dict(d: dict) -> ProfileCopilotSession: ...        # NUNCA lanza; ignora claves desconocidas
def elegir_runtime(s, runtime: str, *, explicito: bool) -> tuple[ProfileCopilotSession, str]: ...
```

> Los motivos de `advance` son los **mismos literales** que ya usa `pipeline_session.advance` (`:76-93`): `""` (ok), `"estado_terminal"`, `"transicion_ilegal"`, `"error_interno"`. No se inventan strings nuevos.

**`elegir_runtime` — la regla que materializa P4 (pseudocódigo, sin ambigüedad):**
```python
def elegir_runtime(s, runtime, *, explicito):
    if runtime not in RUNTIMES:
        return s, "runtime_desconocido"
    if s.runtime_elegido and s.runtime_elegido != runtime and not explicito:
        # ← el candado. Sin bandera explícita del usuario, NO se cambia. Ni en fallo.
        return s, "cambio_de_runtime_requiere_confirmacion"
    if s.state == "eleccion_runtime":
        return advance(s, "diagnostico", runtime_elegido=runtime)
    return replace(s, runtime_elegido=runtime), ""
```

**`backend/api/profile_copilot.py` — endpoints (C7: dos columnas, porque `api_bp` YA pone `/api`):**

> ⚠️ **`api/__init__.py:97` es `Blueprint("api", __name__, url_prefix="/api")`, y `api/__init__.py:140` lo dice textual: `NUNCA "/api/...": api_bp ya lo pone`.** El blueprint nuevo se declara con `url_prefix=""` (igual que `client_profile.py:54`) y **las rutas del decorador NO llevan `/api`**. Copiar la URL final al decorador produce `/api/api/...` y todos los tests de endpoint fallan sin explicación.

| Método | **Ruta en el decorador** | **URL final** | Qué hace |
|---|---|---|---|
| `GET` | `/runtimes/profile` | `/api/runtimes/profile` | `all_runtime_profiles()` + `recomendar_runtime(...)` |
| `GET` | `/projects/<string:project_name>/client-profile/copilot/state` | `/api/projects/<name>/client-profile/copilot/state` | `estado_perfil` + `completitud` + `preguntas_pendientes` con `estados_validos` / `tipos_work_item` / **`procesos_detectados`** |
| `POST` | `/projects/<string:project_name>/client-profile/copilot/turn` | `/api/projects/<name>/client-profile/copilot/turn` | Un turno |

Las tres bajo `STACKY_PROFILE_COPILOT_ENABLED`.

**Proveedor de `procesos_detectados` (C1):** el endpoint `state` arma la tupla llamando a las **mismas dos fuentes deterministas que usa la ruta `autodetect_process_catalog`** (`api/client_profile.py:393-...`), ambas en `services/`: `services.project_autoprofile` (headings reales de los docs) y `grounding_observatory` (procesos citados en épicas publicadas). **Nunca inventa nombres.** Si cualquiera de las dos falla o devuelve vacío, la tupla queda vacía y la pregunta degrada a texto libre (F2 caso 12).

**Contrato del turno:** recibe `{"session": {...}, "respuesta": "...", "runtime": "...", "cambiar_runtime": false}`; devuelve `{"ok", "session", "mensaje", "pregunta", "completitud", "runtime_elegido", "cambio_sugerido", "preferencia_persistida", "advertencia"}`.

**Guard de flag (molde exacto de `api/client_profile.py:326-328`):**
```python
def _flag_off() -> bool:
    import config as _config
    return not getattr(_config.config, "STACKY_PROFILE_COPILOT_ENABLED", False)
# ...en cada ruta:
if _flag_off():
    from flask import abort
    abort(404)     # 404 = flag apagada, NO permiso (mono-operador sin roles)
```

**Casos borde del turno (todos, sin excepción):**
- `session` ausente ⇒ se crea una nueva en `eleccion_runtime` con `proyecto=<name>`.
- `session` con `json.dumps(...)` > `MAX_SESSION_BYTES` ⇒ `400 {"error": "sesion_demasiado_grande"}`, sin escribir nada.
- `session` en estado terminal ⇒ `200` con `mensaje` explicando que la sesión terminó y `session` **sin modificar**.
- `turnos >= MAX_PREGUNTAS` ⇒ transición a `detenido` con `motivo_detencion="tope_de_turnos"`.
- `runtime` fuera de `RUNTIMES` ⇒ `400 {"error": "runtime_desconocido", "validos": [...]}`.
- `runtime` distinto del de la sesión **sin** `cambiar_runtime: true` ⇒ `409 {"error": "cambio_de_runtime_requiere_confirmacion", "runtime_elegido": <el de la sesión>}` — **la sesión no cambia**.
- Runtime elegido con `disponible = False` ⇒ la sesión **arranca igual** (el motor es determinista, P3) pero la respuesta trae `advertencia` con el `disponibilidad_motivo` de la ficha. **Nunca se sustituye el runtime.**
- Proyecto inexistente ⇒ `404 {"error": "Proyecto '<name>' no encontrado"}` (mismo texto que `api/client_profile.py:170`).

**Persistencia de la elección:** al pasar a `diagnostico`, el endpoint llama `runtime_capabilities.save_run_preference(project_name, {"runtime": r, "model": None, "effort": None})` y refleja el resultado en `preferencia_persistida: bool`. `STACKY_RUN_SELECTION_PREFS_ENABLED` nace **ON** (`config.py:1533-1534`), así que de fábrica persiste; si alguien la apaga, `save_run_preference` devuelve **`False` sin lanzar** (`runtime_capabilities.py:339-340`) y la respuesta lo dice: `"La elección vale para esta sesión, pero no quedará guardada para la próxima."` **Degradación visible, nunca muda.**

**Fixture obligatoria (C6/C17):** este archivo usa la fixture de aislamiento de §6/F5 **y** el molde de app de `tests/test_plan93_preflight_endpoint.py:25-45` (`create_app()` + flip de flag + `app.config["TESTING"] = True` + restauración).

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_session.py`

**Casos — 21 declarados, 21 colectados (sin `parametrize`):**
1. `test_estado_inicial_es_eleccion_de_runtime`.
2. `test_sin_runtime_no_se_puede_diagnosticar` — `advance(s, "preguntando")` desde `eleccion_runtime` devuelve `motivo == "transicion_ilegal"`.
3. `test_elegir_runtime_valido_pasa_a_diagnostico`.
4. `test_elegir_runtime_desconocido_devuelve_motivo` — `motivo == "runtime_desconocido"` y la sesión conserva sus valores.
5. `test_cambio_de_runtime_sin_bandera_no_cambia_nada` — `elegir_runtime(s, "codex_cli", explicito=False)` con `s.runtime_elegido == "claude_code_cli"` ⇒ motivo `"cambio_de_runtime_requiere_confirmacion"` y `s.runtime_elegido` intacto.
6. `test_cambio_de_runtime_con_bandera_explicita_si_cambia`.
7. `test_advance_ignora_campos_inventados` — `advance(s, "preguntando", campo_inventado=1)` no lanza y no agrega el campo.
8. `test_advance_desde_terminal_no_hace_nada` — motivo `"estado_terminal"`.
9. `test_can_transition_nunca_lanza` — con `None`, `123`, `""`.
10. `test_session_from_dict_ignora_claves_desconocidas_y_no_lanza`.
11. `test_round_trip_dict` — `session_from_dict(session_to_dict(s)) == s`.
12. `test_sesion_serializada_entra_en_el_tope` — una sesión con 40 respuestas de 100 chars ⇒ `len(json.dumps(...)) <= MAX_SESSION_BYTES`, o el test falla indicando el **tamaño real** en el mensaje.
13. `test_endpoint_ficha_404_con_flag_off` — flag en `False` ⇒ `GET /api/runtimes/profile` da `404`.
14. `test_endpoint_ficha_devuelve_tres_fichas_con_flag_on`.
15. **`test_las_rutas_finales_son_las_declaradas` (nuevo, C7)** — se recorre `app.url_map` y se asserta que existen **exactamente** `/api/runtimes/profile`, `/api/projects/<project_name>/client-profile/copilot/state` y `/api/projects/<project_name>/client-profile/copilot/turn`, **y que NO existe ninguna regla que empiece con `/api/api/`**. El assert imprime las reglas encontradas.
16. `test_endpoint_turn_rechaza_runtime_desconocido_con_400_y_lista_validos` — el assert compara el **mensaje** `"runtime_desconocido"` y que `"claude_code_cli"` esté en `validos`.
17. `test_endpoint_turn_409_al_cambiar_runtime_sin_bandera` — y el body trae `runtime_elegido` igual al original.
18. `test_endpoint_turn_sesion_demasiado_grande_da_400`.
19. `test_endpoint_turn_proyecto_inexistente_da_404`.
20. `test_endpoint_turn_no_escribe_el_perfil` — monkeypatch de `services.client_profile.save_client_profile` a `raise AssertionError`; ninguna cantidad de turnos lo dispara.
21. **`test_state_pasa_los_procesos_detectados_al_banco` (nuevo, C1)** — se monkeypatchean las dos fuentes (`services.project_autoprofile` y `grounding_observatory`) para devolver `("Mul2Bane",)`, y la respuesta de `state` trae la pregunta de procesos con `tipo == "eleccion"` y esa opción. Con las fuentes lanzando, la misma pregunta sale `tipo == "texto"` y el endpoint responde `200`.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_session.py" -q
```

**Criterio BINARIO:** **21 passed, 0 failed**.
**Registro en ratchets (C15):** `tests/test_plan296_session.py` en el `.ps1` **y** en el `.sh`.
**Flag:** `STACKY_PROFILE_COPILOT_ENABLED` (**ON**). Con OFF, los 3 endpoints dan `404` y la UI no monta el panel.
**Impacto por runtime:** el motor es **idéntico en los 3** (determinista). La única diferencia declarada vive en la ficha de F1. **Ningún fallback de runtime, en ninguna rama del código.**
**Trabajo del operador: opt-in (default ON)** — el panel aparece; usarlo es voluntario.

---

### F4 — Se ve antes de aplicarse: el diff del perfil

**Objetivo:** convertir las respuestas de la conversación en un diff explícito y legible, que el usuario ve **antes** de que se escriba nada.
**Valor:** cierra N11 y materializa P5. Es la mitad "informar qué cambios realizará ANTES de aplicarlos" del pedido.

**Archivo a crear:** `Stacky Agents/backend/services/profile_patch.py`
**Archivos a editar:** `Stacky Agents/backend/api/profile_copilot.py` (endpoint nuevo) y los dos ratchets (registrar `tests/test_plan296_propuesta.py`).

**Símbolos exactos:**
```python
PATCH_VERSION = "1"

@dataclass(frozen=True)
class CambioPropuesto:
    path: tuple[str, ...]     # ("code_layout", "roots")
    antes: object
    despues: object
    motivo: str               # una frase, en castellano
    sensible: bool            # path[0] in profile_completeness.SECCIONES_SENSIBLES

@dataclass(frozen=True)
class ProfilePatch:
    proyecto: str
    cambios: tuple[CambioPropuesto, ...]
    rechazos: tuple[str, ...]      # propuestas descartadas, con su motivo
    confirm_token: str             # sha256 del patch canónico
    version: str = PATCH_VERSION

def build_profile_patch(*, proyecto: str, base: dict, propuesta: dict) -> ProfilePatch: ...
def patch_to_dict(p: ProfilePatch) -> dict: ...
def confirm_token_for(cambios) -> str: ...
def aplicar_sobre(base: dict, p: ProfilePatch) -> dict: ...   # PURO, devuelve copia; NO escribe
```

**Reglas de `build_profile_patch` (todas, en orden):**
1. **Rechazo de secretos (P6):** cualquier `path` cuyo último componente (en minúsculas) esté en `client_profile._SECRET_KEYS` ⇒ va a `rechazos` con el texto `f"No propongo '{'.'.join(path)}': el perfil nunca guarda credenciales."`, **no** a `cambios`.
2. **Rechazo de no-dict en secciones tipadas:** si la propuesta pone un no-`dict` en una de las **9** secciones que `validate_client_profile` tipa (`client_profile.py:306-316`) ⇒ `rechazos`.
3. **Sin cambio real, sin entrada:** si `antes == despues`, no se genera `CambioPropuesto`. Esto es lo que hace que "no repetir preguntas" también signifique "no proponer lo ya escrito".
4. `sensible = path[0] in SECCIONES_SENSIBLES`.
5. `confirm_token = sha256(json.dumps(canonico, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]`, donde `canonico` es la lista **ordenada** de `(".".join(path), repr_estable(despues))`. **Determinista y estable entre procesos.**
6. `aplicar_sobre` usa `client_profile._deep_merge` (`:454`) sobre una `copy.deepcopy(base)`. **Nunca muta `base`.**

**Endpoint (en `api/profile_copilot.py`) — C7, dos columnas:**

| Método | **Ruta en el decorador** | **URL final** |
|---|---|---|
| `POST` | `/projects/<string:project_name>/client-profile/copilot/propose` | `/api/projects/<name>/client-profile/copilot/propose` |

Devuelve `{"ok", "patch": {...}, "validacion_previa": {...}}`, donde `validacion_previa` es `validate_client_profile(aplicar_sobre(base, patch)).to_dict()`. **Read-only: no escribe.**

> Esto es clave: el usuario ve **no sólo el diff, sino el veredicto de validación del resultado**, antes de decidir. Si `validacion_previa["ok"]` es `False`, el copiloto lo dice y ofrece corregir; **el botón de aplicar de F6 queda deshabilitado con el motivo a la vista** (deshabilitar y explicar, nunca esconder).

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_propuesta.py`

**Casos — 15 declarados, y el #4 está parametrizado sobre las 6 keys de `_SECRET_KEYS` ⇒ `14 + 6 = 20 colectados` (C4: el v1 decía "15 passed" y "20 passed" en la misma línea; el número real es 20):**
1. `test_diff_lista_path_antes_y_despues`.
2. `test_sin_cambio_real_no_genera_entrada` — `base == propuesta` ⇒ `cambios == ()`.
3. `test_secreto_va_a_rechazos_no_a_cambios` — propuesta con `{"database": {"password": "x"}}` ⇒ `cambios` vacío y `rechazos` con el texto que nombra `password`. Assert sobre el **mensaje**.
4. `test_las_seis_claves_de_secret_keys_se_rechazan` — **`@pytest.mark.parametrize` sobre `sorted(_SECRET_KEYS)`, que son exactamente 6 (verificadas: `api_key`, `auth_header`, `password`, `pat`, `secret`, `token`)** ⇒ **6 casos colectados**.
5. `test_seccion_sensible_marca_sensible_true` — `tracker_state_machine`, `state_flow`, `database`.
6. `test_seccion_comun_marca_sensible_false` — `language`.
7. `test_confirm_token_es_estable` — dos llamadas con la misma propuesta dan el mismo token.
8. `test_confirm_token_cambia_si_cambia_un_valor`.
9. `test_confirm_token_no_depende_del_orden_de_las_keys`.
10. `test_aplicar_sobre_no_muta_la_base` — `base` idéntico antes y después (comparación de `json.dumps(sort_keys=True)`).
11. `test_aplicar_sobre_preserva_secciones_no_tocadas`.
12. `test_no_dict_en_seccion_tipada_va_a_rechazos`.
13. `test_endpoint_propose_no_escribe` — monkeypatch de `save_client_profile` a `raise AssertionError`; el endpoint responde `200`.
14. `test_endpoint_propose_devuelve_validacion_previa_del_resultado` — con una propuesta que rompe el tipo, `validacion_previa["ok"] is False` y `errors` menciona la sección. Assert sobre el **mensaje**.
15. `test_endpoint_propose_404_con_flag_off`.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_propuesta.py" -q
```

**Criterio BINARIO (corregido, C4):** **20 tests colectados, 20 passed, 0 failed.** Aritmética declarada: 15 casos, uno de ellos parametrizado ×6 ⇒ `15 − 1 + 6 = 20`. **El número se lee de la línea final de pytest.** Si el conteo real difiere, se corrige el número del plan — **nunca se borra un caso ni se saca el `parametrize`**.
**Registro en ratchets (C15):** `tests/test_plan296_propuesta.py` en el `.ps1` **y** en el `.sh`.
**Fixture:** la de aislamiento de §6/F5 (C6) — el endpoint toca `get_project_config`.
**Flag:** `STACKY_PROFILE_COPILOT_ENABLED` (**ON**) — es lectura y cálculo, no escribe.
**Impacto por runtime:** **idéntico en los 3**. El diff es determinista.
**Trabajo del operador: ninguno.**

---

### F5 — El copiloto EJECUTA: aplicar con confirmación explícita (flag OFF, causal (B))

**Objetivo:** cerrar el círculo — el copiloto no se limita a recopilar: aplica el diff y deja el perfil válido.
**Valor:** cierra N12 y el KPI K3. Es el "debe EJECUTAR las configuraciones" del pedido.

**Archivos a editar:** `Stacky Agents/backend/api/profile_copilot.py` (endpoint nuevo) y los dos ratchets (registrar `tests/test_plan296_apply.py`).

**Endpoint — C7, dos columnas:**

| Método | **Ruta en el decorador** | **URL final** |
|---|---|---|
| `POST` | `/projects/<string:project_name>/client-profile/copilot/apply` | `/api/projects/<name>/client-profile/copilot/apply` |

**Body:**
```json
{
  "session": {...},
  "patch": {...},
  "confirm_token": "…",
  "confirmaciones_sensibles": ["tracker_state_machine", "database"]
}
```

**Algoritmo (sin ambigüedad, en orden; el primer fallo corta y NO escribe):**
1. `STACKY_PROFILE_COPILOT_ENABLED` OFF ⇒ `abort(404)`.
2. `STACKY_PROFILE_COPILOT_APPLY_ENABLED` OFF ⇒ `403 {"error": "apply_deshabilitado", "flag": "STACKY_PROFILE_COPILOT_APPLY_ENABLED", "mensaje": "Aplicar cambios al perfil está apagado. Se puede activar desde Configuración > Arnés."}` — **403 = flag apagada, no permiso** (mono-operador).
3. Proyecto inexistente ⇒ `404` con el texto de `api/client_profile.py:170`.
4. `patch` ausente o sin `cambios` ⇒ `400 {"error": "patch_vacio"}`.
5. **Recalcular** el `confirm_token` desde el `patch` recibido. Si difiere del enviado ⇒ `409 {"error": "patch_desactualizado", "mensaje": "La propuesta cambió desde que la viste. Volvé a revisarla."}` — **no se escribe nada.**
6. Todo `CambioPropuesto` con `sensible=True` cuyo `path[0]` no esté en `confirmaciones_sensibles` ⇒ `409 {"error": "confirmacion_faltante", "secciones": [...]}` — **no se escribe nada.**
7. `base = load_client_profile(project) or {}`; `resultado = aplicar_sobre(base, patch)`.
8. `v = validate_client_profile(resultado)`; si `not v.ok` ⇒ `400 {"error": "perfil_invalido", "errors": v.errors}` — **no se escribe nada.**
9. Dentro de `with _PROFILE_WRITE_LOCK:` (el mismo `threading.Lock()` de `api/client_profile.py:320`, importado desde ahí — **el candado es uno solo para todo el perfil**): `normalized = save_client_profile(project, resultado)`. `ClientProfileError` ⇒ `400`; cualquier otra ⇒ `500` con `logger.exception`.
10. `record_event(action="profile_copilot_apply", project=<name>, result="applied", actor=_actor(), schema_version=int(normalized.get("schema_version") or 1), detail={"paths": [...], "runtime_elegido": session.runtime_elegido, "sensibles": [...]})` — molde exacto de `api/client_profile.py:362-369`. **Firma verificada** en `services/config_transfer.py:1042-1054`: los seis kwargs existen.
11. Sesión ⇒ `advance(s, "aplicado")`. Respuesta `200 {"ok": true, "session": ..., "completitud": ..., "aplicados": N, "profile": normalized}`.

> **Detalle de riel:** el `_PROFILE_WRITE_LOCK` se importa **de `api.client_profile`** (api→api es legal; el que no puede es `services`→`api`). Si se creara un lock nuevo, dos escrituras concurrentes por caminos distintos podrían pisarse.

#### Fixture de aislamiento OBLIGATORIA (nuevo v2 — C6). La usan F3, F4, F5 y F7.

**El problema medido:** `save_client_profile` **no** pasa por el seam de lectura `_read_project_config_raw`. Escribe directo en `projects_dir() / project_name.upper() / "config.json"` (`client_profile.py:415`) y **exige que ese archivo ya exista** (`:416-417`). Además `record_event` anexa a `data/config_transfer_events.jsonl`. Sin aislar, `test_plan296_apply.py` o bien da `404` (no hay proyecto) o **pisa el `config.json` real de un proyecto del operador**, y deja rastro en su `data/`.

**El molde exacto ya existe en el repo — `tests/test_client_profile.py:18-32`. Se calca:**

```python
@pytest.fixture()
def env(tmp_path, monkeypatch):
    import services.client_profile as cp
    import project_manager
    pdir = tmp_path / "projects"
    pdir.mkdir(parents=True, exist_ok=True)
    # LOS DOS: la escritura sale de projects_dir(); el 404 del endpoint sale de
    # get_project_config(), que mira project_manager.PROJECTS_DIR.
    monkeypatch.setattr(cp, "projects_dir", lambda: pdir)
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", pdir)
    # La auditoria no debe tocar el data/ del operador.
    eventos = []
    monkeypatch.setattr("api.profile_copilot.record_event",
                        lambda **kw: eventos.append(kw) or {})
    return {"projects_dir": pdir, "eventos": eventos}
```

Y el proyecto de prueba se siembra a mano: `(pdir / "DEMO").mkdir()` + `config.json` con `{"issue_tracker": {"type": "azure_devops"}}`.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_apply.py`

**Casos — 17 declarados, 17 colectados (los 14 del v1 + 3 nuevos por C6/C12):**
1. `test_apply_404_con_flag_maestra_off`.
2. `test_apply_403_con_flag_de_apply_off_y_nombra_la_flag` — el body trae `"STACKY_PROFILE_COPILOT_APPLY_ENABLED"`. Assert sobre el **mensaje**.
3. `test_apply_con_flag_off_no_escribe` — monkeypatch de `save_client_profile` a `raise AssertionError`; responde `403`.
4. `test_token_desactualizado_da_409_y_no_escribe`.
5. `test_seccion_sensible_sin_confirmar_da_409_y_no_escribe` — y el body lista la sección.
6. `test_seccion_sensible_confirmada_se_aplica`.
7. `test_perfil_invalido_da_400_y_no_escribe` — propuesta que rompe el tipo de `code_layout`.
8. `test_patch_vacio_da_400`.
9. `test_de_perfil_vacio_a_perfil_valido_en_una_sesion` — **(K3, reforzado por C12)** arranca de `{}`, aplica un patch con las 3 requeridas, y asserta **las tres cosas**: (a) `set(_REQUIRED_SECTIONS) <= set(perfil_final)`; (b) `validate_client_profile(perfil_final).ok is True`; (c) **`[w for w in validate_client_profile(perfil_final).warnings if " ausente" in w and w.startswith("client_profile.")] == []`** — este tercero es el único que **no** pasaba antes del cambio, y el mensaje del assert imprime los warnings sobrevivientes.
10. `test_apply_preserva_secciones_no_tocadas` — un `devops_pipeline_drafts` preexistente sobrevive al apply.
11. `test_apply_registra_evento_de_auditoria` — se lee la lista `eventos` de la fixture y se verifica `action == "profile_copilot_apply"` y que `detail["runtime_elegido"]` sea el de la sesión.
12. `test_apply_nunca_escribe_una_clave_de_secret_keys` — un patch manipulado con `password` ⇒ el rechazo de F4 ya lo sacó; si se fuerza, `validate_client_profile` lo bloquea en el paso 8 (`client_profile.py:285-290`) y el test asserta `400` + el mensaje que menciona `secretos`.
13. `test_apply_deja_la_sesion_en_estado_terminal` — `session["state"] == "aplicado"`.
14. `test_apply_no_cambia_el_runtime_elegido` — `session["runtime_elegido"]` idéntico antes y después.
15. **`test_el_apply_escribe_dentro_de_tmp_path_y_no_fuera` (nuevo, C6)** — tras un apply exitoso, `(tmp_path/"projects"/"DEMO"/"config.json")` contiene la sección nueva, **y** `services.client_profile.projects_dir()` devuelve una ruta que es `tmp_path`-relativa. El assert imprime la ruta real resuelta.
16. **`test_la_auditoria_no_toca_el_data_real` (nuevo, C6)** — `record_event` está monkeypatcheado y la lista `eventos` tiene exactamente 1 entrada; ningún archivo nuevo aparece bajo el `data/` del repo (se compara el listado antes/después).
17. **`test_sin_la_fixture_el_proyecto_no_existe` (nuevo, C6 — prueba de contraste)** — sin sembrar `DEMO`, el apply devuelve `404` con el texto de `api/client_profile.py:170`. Prueba que el aislamiento es efectivo y que el 404 no viene de otra rama.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_apply.py" -q
```

**Criterio BINARIO:** **17 passed, 0 failed**.
**Registro en ratchets (C15):** `tests/test_plan296_apply.py` en el `.ps1` **y** en el `.sh`.
**Flag:** `STACKY_PROFILE_COPILOT_APPLY_ENABLED` (**OFF — causal (B)**: escribe `projects/<NAME>/config.json`, la configuración real del proyecto del operador, que gobierna el ruteo de agentes y el contexto inyectado a todo agente).
**Impacto por runtime:** **idéntico en los 3** — la escritura es del backend, no del runtime. El runtime elegido queda **registrado en la auditoría** (`detail["runtime_elegido"]`), lo que da trazabilidad de con qué runtime se configuró el perfil.
**Trabajo del operador: opt-in explícito** — para que el copiloto aplique cambios hay que encender `STACKY_PROFILE_COPILOT_APPLY_ENABLED` desde la UI de flags. Mientras esté apagado, el copiloto conversa, detecta y **muestra** el diff, y el operador lo aplica a mano con el botón Guardar que ya existe.

---

### F6 — El copiloto vive dentro de la pantalla que ya existe

**Objetivo:** montar el copiloto **dentro** de `ClientProfileEditor`, con toda la lógica testeable en `.ts` puro y **sin sumar deuda a ningún ratchet del frontend**.
**Valor:** cierra N13 sin las trece patas de un tab nuevo.

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/clientProfileCopilotModel.ts` — **lógica PURA, sin DOM, sin red**.
- `Stacky Agents/frontend/src/components/__tests__/clientProfileCopilotModel.test.ts` — vitest (`vitest ^4.1.9` está en `frontend/package.json:30`).
- `Stacky Agents/frontend/src/components/ClientProfileCopilotPanel.tsx` — cáscara de presentación.
- `Stacky Agents/frontend/src/components/ClientProfileCopilotPanel.module.css`.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — `ProfileCopilotApi` junto a `ClientProfileApi` (`:2245`).
- `Stacky Agents/frontend/src/components/ClientProfileEditor.tsx` — montar `<ClientProfileCopilotPanel />` **arriba del formulario**, después del early return de `:686` (o sea dentro del camino en que `projectName` no es `null`), pasándole `projectName` y el callback de invalidación que ya existe (`qc.invalidateQueries({ queryKey: ["client-profile", projectName] })`, `:799`).

> ⚠️ **PROHIBIDO** tocar `frontend/src/components/devops/PipelineCopilotSection.tsx` ni su `.module.css` ni `pipelineCopilotModel.ts` — sesión paralela viva. El panel nuevo es **hermano**, con nombre propio, en `components/` (no en `components/devops/`).

#### Regla dura de deuda visual (nuevo v2 — C14). Es binaria y verificable.

`frontend/src/__tests__/uiDebtRatchet.test.ts` congela **por archivo** la cantidad de `#hex` en `*.module.css` y de `style={{` en `*.tsx` bajo `src/`, y **la deuda sólo puede BAJAR** (`:2-4`). Hay además `a11yCss`, `copyDebtRatchet`, `formDebtRatchet`, `formatDebtRatchet`, `motionDebtRatchet`, `adhocModalRatchet`, `undoConfirmRatchet`, `densityTokens` y `devopsDesignTokens`, todos con baseline congelado. **Son trampa de COMMIT**: no fallan al editar, fallan al commitear.

**Por eso los dos archivos nuevos nacen con deuda CERO:**
- `ClientProfileCopilotPanel.module.css`: **cero `#hex`**. Sólo `var(--...)`. Tokens verificados que existen: `--accent`, `--accent-active`, `--bg-base`, `--bg-elev`, `--bg-panel`, `--border`, `--border-muted`, `--danger`, `--text-primary`, `--focus-ring`, `--card-radius`. **`--color-*` NO existe en el tema: usarlo deja el estilo mudo.**
- `ClientProfileCopilotPanel.tsx`: **cero `style={{`**. Todo por `className` desde el `.module.css`.

**`clientProfileCopilotModel.ts` — símbolos exactos (espejo del backend):**
```ts
export type ProfileSessionState =
  | 'eleccion_runtime' | 'diagnostico' | 'preguntando'
  | 'propuesta' | 'confirmando' | 'aplicado' | 'detenido';

/** Espejo de PROFILE_SESSION_STATES. Mismo orden. */
export const PROFILE_SESSION_STATES: ProfileSessionState[] = [...];

/** Espejo LITERAL de runtime_capabilities.RUNTIMES (services/runtime_capabilities.py:31). */
export const RUNTIMES = ['claude_code_cli', 'codex_cli', 'github_copilot'] as const;
export type RuntimeId = typeof RUNTIMES[number];

/** Espejo de runtime_profile.FICHA_CAMPOS. */
export const FICHA_CAMPOS = ['disponible','recomendado_para','capacidades',
                             'credenciales','ejecucion','si_falla','como_cambiar'] as const;

export const RUNTIME_LABEL: Record<RuntimeId, string> = {
  claude_code_cli: 'Claude',
  codex_cli: 'Codex',
  github_copilot: 'GitHub Copilot',
};

export function stateLabel(s: ProfileSessionState | string): string;
/** Un botón por acción; nunca se esconde: se deshabilita CON motivo. */
export function accionesDisponibles(s: ProfileSessionState | string, applyHabilitado: boolean)
  : { id: string; habilitado: boolean; motivo: string }[];
export function fichaIncompleta(ficha: Record<string, unknown>): string[]; // campos faltantes
export function progresoTexto(c: { requeridas_ok: number; requeridas_total: number }): string;
export function puedeElegirRuntime(s: ProfileSessionState | string): boolean; // sólo antes de ejecutar
export function motivoRuntimeNoDisponible(ficha: Record<string, unknown>): string;
export function runtimeLabel(id: string): string;   // nunca inventa: id desconocido → el id crudo
```

**Regla de UI innegociable (viene de un incidente real del repo):** un control que no se puede usar **se deshabilita con el motivo a la vista**; **nunca se esconde**. `accionesDisponibles` devuelve siempre las mismas acciones con `habilitado` + `motivo`; el `.tsx` renderiza todas.
- Aplicar con `STACKY_PROFILE_COPILOT_APPLY_ENABLED` OFF ⇒ `{habilitado: false, motivo: "Aplicar cambios al perfil está apagado. Se puede activar desde Configuración > Arnés (STACKY_PROFILE_COPILOT_APPLY_ENABLED)."}`.
- Aplicar con `validacion_previa.ok === false` ⇒ `{habilitado: false, motivo: "La propuesta deja el perfil inválido: <primer error>."}`.

**`ProfileCopilotApi` en `endpoints.ts` (molde de `ClientProfileApi`, `:2245`) — usar `rawGet`/`rawPost`:**
> El wrapper `api.*` **lanza** en non-2xx. Este flujo depende de leer los cuerpos de `403`/`409`/`400` (que son estados normales del copiloto, no errores de red), así que **`ProfileCopilotApi` usa `rawGet`/`rawPost`**, no `api.get`/`api.post`. Ambos ya están importados en `endpoints.ts:1` desde `./client`.

```ts
export const ProfileCopilotApi = {
  runtimes: () => rawGet('/api/runtimes/profile'),
  state:    (p: string) => rawGet(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/state`),
  turn:     (p: string, body: unknown) => rawPost(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/turn`, body),
  propose:  (p: string, body: unknown) => rawPost(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/propose`, body),
  apply:    (p: string, body: unknown) => rawPost(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/apply`, body),
};
```
> Acá **sí** van las URL finales con `/api`: es el cliente HTTP, no el decorador de Flask (C7).

**Descubrimiento del panel (C20):** `ProfileCopilotApi.runtimes()` se consume con react-query usando `staleTime: 5 * 60 * 1000` y `retry: false`, para que la flag OFF cueste **un** request por sesión de pantalla y no uno por render.

**Archivo de test a crear:** `Stacky Agents/frontend/src/components/__tests__/clientProfileCopilotModel.test.ts`

> ⚠️ **PROHIBIDO** un `.test.tsx` con React Testing Library: RTL/jsdom **no están instalados**; ese archivo reporta "no tests" y **exit 0** — un falso verde. Todo lo testeable vive en el `.ts` puro. (El directorio ya contiene `.test.tsx` heredados — no son referencia a imitar.)

**Casos — 15 declarados, 15 colectados:**
1. `los siete estados del backend están espejados` — `PROFILE_SESSION_STATES.length === 7` y contiene los 7 ids exactos.
2. `los tres runtimes están espejados con los ids exactos` — `RUNTIMES` igual a `['claude_code_cli','codex_cli','github_copilot']`.
3. `los siete campos de la ficha están espejados`.
4. `stateLabel nunca devuelve vacío` — para los 7 y para un string inventado.
5. `RUNTIME_LABEL cubre los tres`.
6. **`runtimeLabel no inventa etiquetas para ids desconocidos` (nuevo)** — `runtimeLabel('gpt5_cli') === 'gpt5_cli'`.
7. `aplicar deshabilitado nombra la flag cuando apply está OFF` — el `motivo` contiene `STACKY_PROFILE_COPILOT_APPLY_ENABLED`.
8. `ninguna acción desaparece cuando está deshabilitada` — `accionesDisponibles(s, false).length === accionesDisponibles(s, true).length` para los 7 estados.
9. `toda acción deshabilitada tiene motivo no vacío`.
10. **`accionesDisponibles no lanza con un estado desconocido` (nuevo)** — devuelve un array (posiblemente con todo deshabilitado), nunca lanza.
11. `fichaIncompleta detecta los campos faltantes` — con 5 de 7, devuelve los 2 nombres.
12. `fichaIncompleta devuelve [] con la ficha completa`.
13. `puedeElegirRuntime es true antes de ejecutar y false en terminales` — `true` en `eleccion_runtime`/`diagnostico`/`preguntando`/`propuesta`; `false` en `aplicado`/`detenido`.
14. `progresoTexto muestra el avance de las requeridas` — `"2 de 3"`.
15. `motivoRuntimeNoDisponible devuelve el texto del backend, no uno inventado` — con `disponibilidad_motivo` poblado, lo devuelve tal cual; vacío ⇒ `""`.

**Comandos:**
```
cd "Stacky Agents/frontend" ; npx vitest run src/components/__tests__/clientProfileCopilotModel.test.ts
cd "Stacky Agents/frontend" ; npx tsc --noEmit
cd "Stacky Agents/frontend" ; npx vitest run src/__tests__/uiDebtRatchet.test.ts src/__tests__/a11yCss.test.ts src/__tests__/formDebtRatchet.test.ts src/__tests__/formatDebtRatchet.test.ts src/__tests__/motionDebtRatchet.test.ts src/__tests__/copyDebtRatchet.test.ts src/__tests__/adhocModalRatchet.test.ts src/__tests__/undoConfirmRatchet.test.ts
```

**Criterio BINARIO:**
- vitest del modelo: **15 passed, 0 failed** y la salida **NO** dice `No test files found` (si lo dice, el criterio FALLA aunque el exit sea 0).
- `npx tsc --noEmit`: **0 errores**.
- **Ratchets del frontend (C14): `failed` ≤ la línea base medida ANTES de F6** con el mismo comando. Además, dos verificaciones directas y binarias sobre los archivos nuevos:
  ```
  grep -c "#" "Stacky Agents/frontend/src/components/ClientProfileCopilotPanel.module.css"   # los que sean color hex: 0
  grep -c "style={{" "Stacky Agents/frontend/src/components/ClientProfileCopilotPanel.tsx"   # 0
  ```
  (el primero se afina con el mismo regex del ratchet, `/#[0-9a-fA-F]{3,8}\b/g`, para no contar `#` de comentarios).

**Flag:** `STACKY_PROFILE_COPILOT_ENABLED` (**ON**). El panel se monta sólo si `GET /api/runtimes/profile` no devolvió `404`; con la flag OFF, `ClientProfileEditor` se renderiza **byte a byte** como hoy.
**Impacto por runtime:** el selector muestra los 3 con su ficha completa. El no disponible se muestra **deshabilitado con el motivo**, nunca oculto, y **nunca se preselecciona otro en su lugar**.
**Trabajo del operador: opt-in (default ON)** — aparece el panel; el formulario de siempre queda intacto debajo.

---

### F7 — Paridad de los 3 runtimes, la deuda del comentario, y la verificación de los guardianes

**Objetivo:** dejar probado por test que ningún camino cambia de runtime solo, corregir el comentario falso de `agent_runner.py:317`, y **verificar** (ya no crear — C15) que los 7 archivos de test están en los DOS ratchets.
**Valor:** es la fase que impide que el plan se degrade en la próxima pasada.

**Archivos a editar:**
- `Stacky Agents/backend/agent_runner.py` — línea `:317`: reemplazar el comentario falso.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — registrar `tests/test_plan296_paridad_runtimes.py` (el séptimo; los otros seis ya los registraron F0..F5 y F6 no aporta ninguno de pytest).
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — el **mismo** archivo, formato sin comillas ni coma.
- `Stacky Agents/backend/tests/harness_ratchet_allowlist.txt` — verificar por grep que ninguno de los 7 esté ahí; si alguno está, sacarlo (`test_allowlist_no_se_solapa_con_ratchet`, `test_harness_ratchet_meta.py:56`).

**Corrección del comentario (`agent_runner.py:317`):**
```python
# ANTES (FALSO desde hace varias pasadas):
#   claude_code_cli: bloqueado en endpoint (HTTP 501). Nunca debería llegar aquí.
# DESPUÉS:
#   Plan 296 — los TRES runtimes de _VALID_RUNTIMES (api/agents.py:337) llegan acá.
#   claude_code_cli se despacha más abajo (:398). No hay ningún 501 en api/agents.py.
```
**Cambio de comentario únicamente: cero cambio de comportamiento.**

**Los 7 archivos que deben estar en AMBOS ratchets (misma cantidad en cada uno):**
```
tests/test_plan296_flags.py              (registrado en F0)
tests/test_plan296_runtime_profile.py    (registrado en F1)
tests/test_plan296_completitud.py        (registrado en F2)
tests/test_plan296_session.py            (registrado en F3)
tests/test_plan296_propuesta.py          (registrado en F4)
tests/test_plan296_apply.py              (registrado en F5)
tests/test_plan296_paridad_runtimes.py   (registrado en F7)
```
> El test de vitest (`clientProfileCopilotModel.test.ts`) **NO** va en estos scripts: el ratchet del arnés lista archivos `tests/*.py` de pytest.
> Registrar los 7 en los dos scripts **deja intacto** `_PS1_LAG_MAX = 64` de `tests/test_plan259_ratchet_script_parity.py:46`.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_paridad_runtimes.py`

**Fixture:** la de aislamiento de §6/F5 (C6) — los casos 6 y 7 recorren `apply`.

**Casos — 13 declarados; los #4 y #5 están parametrizados sobre `RUNTIMES` (3 cada uno) ⇒ `13 − 2 + 6 = 17 colectados` (C4: el v1 decía "13 colectados (11 casos + 2 extra)", aritmética incorrecta):**
1. `test_fallo_no_cambia_el_runtime_elegido` — **(K5)** se simula un fallo del runtime elegido (monkeypatch de `runtime_profile.binary_availability` a `disponible=False` para el elegido) y se corre un turno: la respuesta trae `runtime_elegido` **idéntico** al de la sesión, y `cambio_sugerido` presente **sin haber sido aplicado**.
2. `test_cambio_de_runtime_exige_bandera_explicita` — turno con otro `runtime` y sin `cambiar_runtime` ⇒ `409` y la sesión intacta.
3. `test_la_preferencia_persistida_no_cambia_ante_un_fallo` — se captura `save_run_preference` con monkeypatch; ante el fallo simulado **no se llama** con un runtime distinto.
4. `test_el_motor_conversacional_da_la_misma_pregunta_para_los_tres_runtimes` — **`parametrize` sobre `RUNTIMES` (3 casos)**: mismo proyecto y mismo estado ⇒ mismo `pregunta.id`. **Es la prueba dura de la paridad determinista.**
5. `test_el_diff_es_identico_para_los_tres_runtimes` — **`parametrize` sobre `RUNTIMES` (3 casos)**: mismo `confirm_token` para los 3.
6. **`test_ningun_camino_llama_a_run_agent` (corregido, C8)** — **las DOS flags se encienden explícitamente** (`STACKY_PROFILE_COPILOT_ENABLED=True` y `STACKY_PROFILE_COPILOT_APPLY_ENABLED=True`), se monkeypatchea `agent_runner.run_agent` a `raise AssertionError`, y se corre la secuencia completa `turn → propose → apply`. **El test asserta además que el `apply` devolvió `200`** — si devolviera `403`, el gate no probó nada.
7. **`test_ningun_camino_llama_a_copilot_bridge_invoke` (corregido, C8)** — mismo patrón sobre `copilot_bridge.invoke`, con las dos flags ON y el mismo assert de `200` sobre el `apply`. **Ancla P3: el motor no depende de ningún LLM.**
8. **`test_el_guard_de_llamadas_si_detecta_una_llamada_real` (nuevo, C8 — contraste negativo)** — se instala el mismo guard y se llama a `agent_runner.run_agent` **a propósito** desde el test; se verifica que el guard **lanza**. Prueba que los casos 6 y 7 pueden fallar, o sea que no son adorno.
9. `test_no_hay_ningun_501_en_api_agents` — se lee `api/agents.py` y se asserta que no aparece `501`; el mensaje del assert incluye las líneas ofensoras si aparece. Ancla la corrección del comentario.
10. `test_valid_runtimes_de_agents_coincide_con_runtimes_de_capabilities` — `api.agents._VALID_RUNTIMES == set(runtime_capabilities.RUNTIMES)`.
11. `test_los_dos_ratchets_registran_los_mismos_siete_archivos` — se leen los dos scripts, se extraen las líneas `tests/test_plan296_*.py` y se compara **el conjunto** (no el conteo); el assert imprime la diferencia simétrica.
12. `test_ningun_test_del_296_esta_en_el_allowlist` — grep sobre `harness_ratchet_allowlist.txt`; el assert nombra el archivo ofensor.
13. **`test_el_comentario_de_agent_runner_ya_no_dice_bloqueado` (nuevo)** — se lee `agent_runner.py` y se asserta que la subcadena `"bloqueado en endpoint"` **no** aparece; el mensaje imprime la línea si sobrevive.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_paridad_runtimes.py" -q
```

**Criterio BINARIO (corregido, C4):**
- **17 tests colectados, 17 passed, 0 failed.** Aritmética declarada: 13 casos, dos de ellos parametrizados ×3 ⇒ `13 − 2 + 6 = 17`. **Se lee de la línea final de pytest.**
- Los 7 archivos aparecen en **ambos** scripts:
  ```
  grep -c "test_plan296" "Stacky Agents/backend/scripts/run_harness_tests.ps1"
  grep -c "test_plan296" "Stacky Agents/backend/scripts/run_harness_tests.sh"
  ```
  Los dos deben devolver **7**.
- `grep -c "test_plan296" "Stacky Agents/backend/tests/harness_ratchet_allowlist.txt"` debe devolver **0**.
- `test_harness_ratchet_meta.py` y `test_plan259_ratchet_script_parity.py`: **`failed` ≤ la línea base medida antes de F0** (delta, no verde absoluto).

**Flag:** ninguna nueva.
**Impacto por runtime:** esta fase **es** la garantía de paridad. Los 3 runtimes quedan con el mismo motor, la misma pregunta, el mismo diff, y el candado contra el cambio automático probado **con contraste**.
**Trabajo del operador: ninguno.**

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| R1 | La sesión paralela toca `api/pipeline_copilot.py` o `PipelineCopilotSection.tsx` y se genera conflicto | Alta | Este plan **no escribe** en esos archivos. Todos los módulos son nuevos y hermanos. Antes de commitear: `git status` y pathspec explícito. |
| R2 | Se registra la flag OFF con `default=False` explícito y se pone en rojo `test_default_known_only_for_curated` | Media | F0 lo dice literal: la flag OFF **omite** `default=`. Caso 4 de `test_plan296_flags.py` lo asserta (`spec.default is None`). |
| R3 | Se cree que `patch_client_profile_key` sirve para escribir secciones del perfil | Alta (era el supuesto de entrada) | §3.1 lo desmiente con `client_profile_keys.py:14-19`. F5 escribe por `save_client_profile`. |
| R4 | Se implementa el motor conversacional sobre `copilot_bridge.invoke` y funciona sólo con `github_copilot` | Alta | P3 lo prohíbe y el caso 7 de F7 lo ancla (`invoke` monkeypatcheado a `raise`) **con las flags encendidas**, más el contraste del caso 8. |
| R5 | La consulta de disponibilidad usa `run_preflight.check` y miente cuando el gate está OFF | Media | F1 usa sólo `_get_runtime_bin` y `_binary_resolvable`, **calificados**. Caso 2 de F1 lo verifica **parametrizado sobre los dos estados de la flag**. |
| R6 | El apply pisa cambios que el operador hizo en el formulario mientras conversaba | Media | Paso 5 del algoritmo de F5: el `confirm_token` se recalcula; si el patch quedó viejo ⇒ `409` y no se escribe. Además el `_PROFILE_WRITE_LOCK` es el **mismo** de `api/client_profile.py:320`. |
| R7 | El copiloto propone una credencial | Baja | Doble candado: F4 rechaza por `_SECRET_KEYS` antes de armar el cambio, y F5 paso 8 lo bloquea otra vez vía `validate_client_profile` (`client_profile.py:285-290`), que usa `_contains_secret_keys` **recursivo** (`:196-211`). Caso 12 de F5. |
| R8 | Se escribe un `.test.tsx` con RTL y da falso verde | Media | F6 lo prohíbe explícitamente y el criterio exige que la salida de vitest **no** diga `No test files found`. |
| R9 | Los dos ratchets divergen en cantidad | Media | Cada fase registra su archivo en los **dos**; caso 11 de F7 compara **conjuntos**; el criterio pide `grep -c == 7` en ambos; `_PS1_LAG_MAX = 64` queda intacto. |
| R10 | Un rojo de fábrica de una suite ajena se lee como "el plan rompió algo" | Alta | Ningún criterio de este plan exige verde absoluto en suites ajenas. F0 usa **delta contra línea base medida** sobre las TRES suites de flags; F6 y F7 hacen lo mismo con los ratchets. |
| R11 | El operador enciende `APPLY` y el copiloto rompe un perfil que funcionaba | Baja | El apply no escribe si el resultado no valida (paso 8), exige confirmación por sección sensible (paso 6), y queda auditado en `record_event` con los paths tocados. |
| **R12** | **Un test del plan escribe en un proyecto real del operador o en su `data/`** | **Alta si no se aísla** | **Fixture obligatoria de §6/F5 (C6): los DOS `setattr` (`projects_dir` y `PROJECTS_DIR`) más el monkeypatch de `record_event`. Casos 15, 16 y 17 de F5 lo prueban, incluido el contraste.** |
| **R13** | **Se copian las URL finales al decorador de Flask y todo queda en `/api/api/...`** | **Alta** | **C7: tabla de dos columnas en F3/F4/F5 + caso 15 de F3, que recorre `app.url_map` y asserta que NO existe ninguna regla que empiece con `/api/api/`.** |
| **R14** | **El panel nuevo suma deuda visual y bloquea el commit por un ratchet del frontend** | **Media** | **C14: los archivos nuevos nacen con CERO `#hex` y CERO `style={{`; F6 corre los 8 ratchets como criterio delta y hace dos grep binarios sobre los archivos nuevos.** |

---

## 8. Fuera de scope

Explícitamente **NO** entra en este plan:

1. **Llamar a un modelo para redactar el perfil.** `asistencia_llm` se **declara** (derivada de `config.LLM_BACKEND`) pero no se implementa. Cuando exista un seam one-shot ruteado por runtime, será otro plan.
2. **Configurar credenciales desde el copiloto.** Las de BD siguen por `api/client_profile.py:492`; las de tracker por su propia pantalla.
3. **Ampliar `PATCHABLE_PROFILE_KEYS`.** Se deja en las 4 keys DevOps de hoy.
4. **Un tab nuevo o una ruta nueva del frontend.** El copiloto vive dentro de `ClientProfileEditor`.
5. **Persistir la conversación entre recargas.** La sesión es stateless (P8). Lo único que persiste es la elección de runtime, por el riel existente.
6. **Cambiar `run_preflight.check` o su flag.** F1 sólo reusa dos helpers puros; el `check()` de la corrida real queda intacto.
7. **Convertir `autodetect_process_catalog` en un servicio.** F3 llama a las dos fuentes de `services/` directamente; **la ruta Flask no se toca, no se mueve y no se refactoriza** (C1).
8. **Uniformar el contrato de `vscode_agent_filename` entre los 4 caminos de `api/agents.py`.** Este plan **lo declara con precisión** (C2), no lo cambia: tocar `:857/:1067/:1259` sería un cambio de comportamiento fuera de eje.
9. **Tocar el eje pipelines (294), git (293) o GitLab (295).**
10. **Migración de perfiles existentes.** `SCHEMA_VERSION` sigue en 1; los perfiles actuales se leen y escriben igual.
11. **Sugerir el runtime automáticamente en la corrida real de un ticket.** `recomendar_runtime` es sólo del copiloto del perfil.

---

## 9. Glosario

| Término | Significado en este plan |
|---|---|
| **Ficha de runtime** | El dict de 7 campos que `runtime_profile(r)` devuelve para un runtime. |
| **Runtime** | Uno de los 3 ids de `runtime_capabilities.RUNTIMES` (`:31`). Nunca "modelo", nunca `LLM_BACKEND`. |
| **`LLM_BACKEND`** | Eje **distinto** del runtime: gobierna a dónde va `copilot_bridge.invoke` (`copilot_bridge.py:157`, con ramas `mock`/`vscode_bridge`/`copilot`/`claude_cli` y posiblemente más). Por eso `asistencia_llm` **no** se declara por runtime. |
| **Sesión** | `ProfileCopilotSession`, dataclass frozen que viaja en el request/response. No se persiste. |
| **Patch / diff** | `ProfilePatch`: lista de `CambioPropuesto` + `confirm_token`. Se ve antes de aplicarse. |
| **Sección sensible** | `tracker_state_machine`, `state_flow`, `database`. Exigen confirmación por-sección para aplicarse. |
| **Degradación visible** | Un campo con valor `"no_disponible"` + `motivo` en castellano. Nunca una ausencia muda. |
| **Fallback de capacidad** | Legítimo: el runtime elegido no puede algo, se dice y se sigue. |
| **Fallback de runtime** | **Prohibido**: cambiar de runtime solo. |
| **Causal (B)** | Justificación de flag OFF: escribe en un sistema real del operador. |
| **Anclaje vivo** | Entrada de `FICHA_ANCLAJES`: literal del código que respalda un campo declarativo. Si muere, la ficha se pone roja en vez de mentir. |

---

## 10. Orden de implementación

```
F0 (flags: 6 guardianes)
 └─> F1 (ficha de runtime, servicio puro + FICHA_ANCLAJES)  ─┐
 └─> F2 (completitud + banco de preguntas)                   ─┤
                                                              ├─> F3 (sesión + blueprint + 3 endpoints)
                                                              │     └─> F4 (diff + endpoint propose)
                                                              │           └─> F5 (apply, flag OFF)
                                                              │                 └─> F6 (UI)
                                                              └───────────────────────> F7 (paridad + comentario + verificación de ratchets)
```

F1 y F2 son **independientes entre sí** y pueden hacerse en cualquier orden después de F0. F7 se hace **al final**, porque sus casos 11 y 12 **verifican** el registro que hicieron las fases anteriores (C15: ya no lo crean todo junto).

**Antes de F0, medir la línea base** (obligatorio, y lo mide quien implementa, no se le cree a nadie):
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_ratchet_meta.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py" -q
```
Y antes de F6:
```
cd "Stacky Agents/frontend" ; npx vitest run src/__tests__/uiDebtRatchet.test.ts src/__tests__/a11yCss.test.ts src/__tests__/formDebtRatchet.test.ts src/__tests__/formatDebtRatchet.test.ts src/__tests__/motionDebtRatchet.test.ts src/__tests__/copyDebtRatchet.test.ts src/__tests__/adhocModalRatchet.test.ts src/__tests__/undoConfirmRatchet.test.ts
```
Anotar `(passed, failed)` de cada uno. Los criterios de este plan sobre suites ajenas son **delta contra esos números**, nunca verde absoluto: **el backend tiene rojos de fábrica y exigirles verde sería un criterio insatisfacible.**

---

## 11. Definition of Done

- [ ] Las 2 flags están en sus guardianes (la ON en 5 lugares incluido `_CURATED_DEFAULTS_ON`; la OFF en 6, **sin `default=` y CON su entrada en `_REQUIRES_MAP_FROZEN`**), y `test_plan296_flags.py` da **10/10**.
- [ ] `runtime_profile(r)` devuelve las **7** claves de `FICHA_CAMPOS` para los 3 runtimes (**K1: 2/7 → 7/7**).
- [ ] La disponibilidad se consulta **sin ticket, sin corrida y sin depender de `STACKY_RUN_PREFLIGHT_GATE_ENABLED` en ninguno de sus dos estados** (**K2**).
- [ ] `exige_agente_vscode` describe **sólo** el camino que rechaza (`api/agents.py:480`) y `agente_vscode_por_defecto` declara los tres autorellenos (**C2**).
- [ ] `test_cada_campo_declarativo_tiene_su_anclaje_vivo` pasa: los 10 anclajes de `FICHA_ANCLAJES` siguen vivos (**`[ADICIÓN ARQUITECTO]`**).
- [ ] Una sección ya completa **no** genera pregunta (**K4**).
- [ ] Una sesión que arranca de `{}` termina con las 3 secciones requeridas, `validate_client_profile(...).ok is True` **y cero warnings `client_profile.<seccion> ausente`** (**K3**, el tercero es el que discrimina — C12).
- [ ] Ante fallo del runtime elegido, `runtime_elegido` queda **intacto** y `cambio_sugerido` aparece **sin aplicarse** (**K5**).
- [ ] Cambiar de runtime exige `cambiar_runtime: true`; sin eso, `409` y sesión intacta.
- [ ] Ningún camino del plan llama a `agent_runner.run_agent` ni a `copilot_bridge.invoke`, **probado con las dos flags ENCENDIDAS y con el caso de contraste que demuestra que el guard puede fallar** (casos 6, 7 y 8 de F7 — C8).
- [ ] El copiloto nunca propone ni escribe una clave de `_SECRET_KEYS` (doble candado F4+F5).
- [ ] Con `STACKY_PROFILE_COPILOT_APPLY_ENABLED` OFF, ninguna ruta escribe el perfil; el botón se muestra **deshabilitado con motivo**, no oculto.
- [ ] Con `STACKY_PROFILE_COPILOT_ENABLED` OFF, los endpoints dan `404` y `ClientProfileEditor` se renderiza como hoy.
- [ ] `app.url_map` no tiene **ninguna** regla que empiece con `/api/api/` (**C7**).
- [ ] **Ningún test del plan escribe fuera de `tmp_path`**: los archivos que tocan `save_client_profile`/`get_project_config`/`record_event` usan la fixture de §6/F5 (**C6**, casos 15-17).
- [ ] `npx tsc --noEmit` en `Stacky Agents/frontend`: **0 errores**.
- [ ] `npx vitest run src/components/__tests__/clientProfileCopilotModel.test.ts`: **15 passed** y la salida **no** dice `No test files found`.
- [ ] `ClientProfileCopilotPanel.module.css` tiene **0** colores `#hex` y `ClientProfileCopilotPanel.tsx` tiene **0** `style={{`; los 8 ratchets del frontend quedan con `failed` **≤** la línea base (**C14**).
- [ ] Los 7 archivos de test nuevos están en **ambos** ratchets (`grep -c "test_plan296"` = **7** en el `.ps1` y en el `.sh`) y en **ninguno** del allowlist (**0**), **y cada uno se registró en la fase que lo creó** (**C15**).
- [ ] El comentario de `agent_runner.py:317` ya no afirma que `claude_code_cli` está bloqueado; `test_no_hay_ningun_501_en_api_agents` y `test_el_comentario_de_agent_runner_ya_no_dice_bloqueado` lo anclan.
- [ ] Las cinco suites de línea base del backend y las ocho del frontend: `failed` **≤** el basal medido antes de F0/F6.
- [ ] Conteos binarios por archivo, con la aritmética declarada: **F0 10 · F1 18 · F2 16 · F3 21 · F4 20 · F5 17 · F6 15 (vitest) · F7 17**. Se leen de la línea final de la corrida; si alguno difiere, **se corrige el número del plan, nunca se borra un caso ni un `parametrize`**.

---

## Anexo A — Los 7 requisitos del operador, y dónde los cumple el plan

| # | Requisito textual | Fase | Símbolo / campo |
|---|---|---|---|
| 1 | si está disponible y correctamente configurado | F1 | `disponible` + `disponibilidad_detalle` + `disponibilidad_motivo` |
| 2 | para qué tipo de tarea se recomienda | F1 | `recomendado_para` (`RECOMENDADO_PARA`) |
| 3 | qué capacidades utilizará | F1 | `capacidades` (las 11 de `capabilities_for` + `exige_agente_vscode` + `exige_agente_vscode_alcance` + `agente_vscode_por_defecto` + `asistencia_llm`) |
| 4 | qué permisos o credenciales necesita | F1 | `credenciales` (`CREDENCIALES`) — **nombres, nunca valores** |
| 5 | si trabajará localmente o mediante integración externa | F1 | `ejecucion` (`EJECUCION`) |
| 6 | qué ocurrirá si la ejecución falla | F1 | `si_falla` (`SI_FALLA`) |
| 7 | cómo cambiar de runtime antes de ejecutar una acción | F1 + F3 + F6 | `como_cambiar` + `elegir_runtime(..., explicito=True)` + `puedeElegirRuntime` |

## Anexo B — Las 14 conductas del copiloto, y dónde viven

| Conducta pedida | Fase | Cómo |
|---|---|---|
| detectar qué información ya está disponible | F2 | `estado_perfil().secciones_presentes` |
| evitar preguntas repetidas | F2 | `preguntas_pendientes` excluye secciones presentes + `ya_respondidas` |
| identificar datos faltantes | F2 | `secciones_faltantes_requeridas` / `_opcionales` + `warnings_de_seccion_ausente` |
| identificar inconsistencias | F2 | `inconsistencias` desde `validate_client_profile`, con las **4 formas de mensaje** mapeadas (C13) |
| adaptar preguntas según tipo de cliente/proyecto | F2 + **F3** | banco por `tracker_type` + `estados_validos` / `tipos_work_item` / **`procesos_detectados`, provistos por el endpoint** (C1) |
| recomendar explicando cada decisión | F2 + F4 | `Pregunta.motivo` y `CambioPropuesto.motivo` |
| completar automáticamente campos | F4 | `complete_client_profile` + `get_default_client_profile` como propuesta |
| revisar, corregir o confirmar cada cambio importante | F4 + F5 | `sensible=True` ⇒ `confirmaciones_sensibles` obligatorias |
| aprovechar lo existente antes de pedir a mano | **F3 (proveedor) + F2 (consumo)** | `load_effective_client_profile` en F2; `services.project_autoprofile` + `grounding_observatory` desde el endpoint de F3 — **NO desde `services/profile_completeness.py`, que no puede importar `api/`** (C1) |
| mostrar progreso y nivel de completitud | F2 + F6 | `completitud()` + `progresoTexto` |
| resumen de lo configurado, pendiente y recomendado | F3 | payload del turno: `completitud` + `pregunta` + `cambio_sugerido` |
| informar los cambios ANTES de aplicarlos | F4 | `ProfilePatch` + `validacion_previa` |
| confirmación explícita antes de guardar lo sensible | F5 | pasos 5 y 6 del algoritmo |
| **EJECUTAR**, no sólo recopilar | F5 | `save_client_profile` tras validar, con auditoría y con el lock compartido |

---

## Anexo C — E1: anclajes verificados en la crítica v1 → v2

**Método:** cada cita se verificó **abriendo el archivo real**, no de memoria. Total **97**. Resultado: **90 OK · 4 DESFASADOS (corregidos con la línea real, no borrados) · 0 INEXISTENTES · 3 OK-de-línea con el CONTENIDO mal descrito (elevados a bloqueante C2)**.

**Los 4 desfasados, con su línea real:**

| Anclaje del v1 | Real | Impacto |
|---|---|---|
| `api/__init__.py:148` (registro del blueprint) | **`:152`** | Molde de F3. Corregido. |
| `app.py:635-636` ("NO agregar threads nuevos") | **`:641`** (en `:635` está `mark_startup_writes_done()`) | Riel P7. Corregido. |
| `harness_flags.py:626` (nota de `_CATEGORY_KEYS`) | **`:629`** | Guardián 3 de F0. Corregido, y se agregan `:315` / `:467`. |
| `pipelineCopilotModel.ts:3-5` (nota de RTL/jsdom) | **`:4-5`** | Molde de F6. Corregido. |

**Los 3 con contenido mal descrito (existen en la línea citada, pero hacen lo contrario):** `api/agents.py:857`, `:1067`, `:1259` — **auto-rellenan** el archivo de agente (`:858`, `:1069`, `:1261`), no rechazan. Ver **C2** y el `[ADICIÓN ARQUITECTO]` de F1, que existe justamente para que este tipo de defecto se vuelva detectable por test.

**Verificados OK (muestra representativa de los 90):** `client_profile.py` `:40 :42-44 :48-52 :54-61 :66 :71-83 :119 :140 :196-211 :263 :274 :285-290 :302-304 :306-316 :339 :358 :375 :379 :388-402 :407 :415-417 :454 :465 :492` · `client_profile_keys.py` `:14-19 :22 :35` · `api/client_profile.py` `:45 :54 :102 :132 :156-161 :166-198 :170 :203 :210 :320 :324 :326-328 :335-337 :362-369 :373-376 :392 :473 :492 :554` · `api/__init__.py:10 :97 :133 :140` · `runtime_capabilities.py` `:28 :31 :34-38 :70 :71-77 :134-146 :149 :206 :228 :306 :316 :324 :326 :333 :339-340 :348 :360` · `run_preflight.py` `:28 :31-34 :37-54 :57 :74-83 :82-83 :263-273 :276-280` · `agent_runner.py` `:151 :182 :317 :319 :398` · `api/agents.py` `:337 :480 :488 :1713-1715 :2143-2144` + "cero `501`" · `copilot_bridge.py:145-156 :157` · `ado_pipeline_inference.py:277` · `pipeline_session.py` `:3 :10-12 :15-24 :27-36 :38 :51-64 :67 :71-73 :76-93 :87-90 :92-93 :96` + 198 líneas · `context_enrichment.py:631` · `config.py` `:1058-1059 :1533-1534 :1913-1917` · `harness_flags.py` `:120 :315 :467 :4216-4234` · `harness_flags_help.py:25` · `test_harness_flags.py` `:467 :1224` · `test_harness_flags_requires.py` `:120 :405` · `test_harness_ratchet_meta.py` `:43 :56 :79` · `test_plan259_ratchet_script_parity.py:46` · `test_flag_wiring.py:29-53` · `test_client_profile.py:18-32` · `test_plan93_preflight_endpoint.py:25-45` · `ClientProfileEditor.tsx` `:609 :612 :615 :686 :792 :799-800` + 1288 líneas · `endpoints.ts` `:1 :2245` · `uiDebtRatchet.test.ts:2-4` · `package.json:30` · `run_harness_tests.ps1:1006-1013` · `run_harness_tests.sh:1090-1092` · `harness_ratchet_allowlist.txt`.





