# Plan 296 — El perfil del cliente se configura CONVERSANDO, y el runtime se elige con los ojos abiertos

**Estado:** PROPUESTO (v1) · **Fecha:** 2026-08-02 · **Rama:** `docs/plan-279`
**Eje:** perfil de cliente + elección informada de runtime. **NO** toca pipelines (eje 294) ni git (eje 293) ni GitLab (eje 295).

---

## 1. Objetivo y KPI

Hoy, dejar un proyecto con `client_profile` usable exige que una persona **conozca de antemano** nueve secciones del schema (`code_layout`, `language`, `tracker_state_machine` requeridas — `services/client_profile.py:48-52` — más `database`, `build`, `conventions`, `docs_indexes`, `terminology`, `extensions` opcionales — `:54-61`) y las llene a mano en un formulario de **1288 líneas** (`frontend/src/components/ClientProfileEditor.tsx`). El formulario es correcto y completo; el problema es que **presupone el conocimiento que el operador no tiene**.

Este plan agrega, **dentro de esa misma pantalla**, un copiloto **conversacional** que pregunta en castellano, deduce de lo que ya existe, propone el cambio, lo muestra ANTES de aplicarlo, y —con confirmación explícita— **lo ejecuta**, dejando el perfil válido. Y, antes de conversar, obliga a **elegir el runtime a ojos abiertos**: una ficha de 7 campos por cada uno de los 3 runtimes, con disponibilidad REAL medida sin disparar una corrida.

### KPI (medibles, con el test que los mide)

| # | KPI | Hoy | Después | Test que lo mide |
|---|---|---|---|---|
| K1 | Campos de la ficha de runtime, por runtime | **2 de 7** (el punto 3 parcial vía `capabilities_for`; el 7 con sustrato pero sin ficha vía `save_run_preference`) | **7 de 7** para los 3 runtimes | `test_plan296_runtime_profile.py::test_ficha_tiene_los_siete_campos_para_los_tres_runtimes` |
| K2 | Consultar disponibilidad de un runtime | Sólo disparando `run_agent` contra un ticket (`agent_runner.py:180-200`) **y** con `STACKY_RUN_PREFLIGHT_GATE_ENABLED` en ON (`run_preflight.py:76-83`) | Consulta pura, sin ticket, sin corrida, **sin depender de esa flag** | `test_plan296_runtime_profile.py::test_disponibilidad_no_depende_del_gate_de_preflight` |
| K3 | Secciones requeridas presentes tras una sesión que arranca de `{}` | 0 de 3 | **3 de 3** y `validate_client_profile(...).ok is True` | `test_plan296_apply.py::test_de_perfil_vacio_a_perfil_valido_en_una_sesion` |
| K4 | Preguntas repetidas sobre datos ya conocidos | No hay detección | **0** — toda sección ya presente y válida sale del banco de preguntas | `test_plan296_completitud.py::test_seccion_ya_completa_no_genera_pregunta` |
| K5 | Cambios de runtime automáticos ante un fallo | N/A (no hay copiloto) | **0** — el runtime elegido nunca cambia solo | `test_plan296_paridad_runtimes.py::test_fallo_no_cambia_el_runtime_elegido` |

---

## 2. Por qué ahora, y por qué no se superpone con 293/294/295

Los tres planes vecinos son de **otro eje** y de otra sesión:

- **293** — tablero de **git** local para no técnicos (`git_workbench`, verbos git, `create_merge_request`).
- **294** — wizard de **pipelines** sin YAML (`pipeline_session`, `pipeline_copilot`, `PipelineCopilotSection.tsx`).
- **295** — la integración con **GitLab** deja de mentir sobre sí misma (`gitlab_provider`, sync, degradación).

Este plan toca **`client_profile*`** y **`runtime_capabilities` / `run_preflight`**, y su superficie de UI es **`ClientProfileEditor.tsx`**. No hay intersección de archivos con 293/294/295 salvo dos rieles compartidos (`config.py`, `harness_flags.py`, los dos ratchets, `endpoints.ts`), que son de agregado puro.

> **REGLA DURA DE CONVIVENCIA:** `backend/api/pipeline_copilot.py` y `frontend/src/components/devops/PipelineCopilotSection.tsx` están **siendo editados por una sesión paralela viva**. Este plan **REUSA EL PATRÓN** de esos archivos (dataclass frozen + estados cerrados + lógica de UI en `.ts` puro) y **NO ESCRIBE UNA SOLA LÍNEA** en ellos. Los módulos que crea son **hermanos**, con nombres propios.

El gap que cierra: el perfil de cliente ya se **lee** en runtime y se inyecta al agente (`services/context_enrichment.py::build_client_profile_block`, consumido en `api/agents.py:1713-1715` y `:2143-2144`), pero **nadie ayuda a llenarlo**. Un perfil ausente no rompe nada — `load_effective_client_profile` cae al template del tracker (`client_profile.py:388-402`) — pero degrada silenciosamente la calidad de todo lo que el agente hace. Este plan convierte el llenado en una conversación.

---

## 3. Sustrato verificado

### 3.1 Lo que YA EXISTE y este plan REUSA (nada de esto se reescribe)

**Modelo de perfil — `backend/services/client_profile.py` (560 líneas):**

| Símbolo | Línea | Uso en este plan |
|---|---|---|
| `SCHEMA_VERSION = 1` | `:40` | La sesión declara el schema que asume |
| `_SECRET_KEYS` (`pat`, `token`, `password`, `secret`, `auth_header`, `api_key`) | `:42-44` | El copiloto **jamás** propone estas claves (P6) |
| `_REQUIRED_SECTIONS = ("code_layout", "language", "tracker_state_machine")` | `:48-52` | Fuente del banco de preguntas obligatorias (F2) |
| `_OPTIONAL_SECTIONS` (6 secciones) | `:54-61` | Fuente del banco de preguntas opcionales (F2) |
| `class ClientProfileError` | `:66` | Se atrapa en F5 y se traduce a mensaje del copiloto |
| `class ValidationResult` (`ok`, `errors`, `warnings`, `normalized`, `.to_dict()`) | `:71-83` | El copiloto muestra `errors`/`warnings` textuales |
| `get_default_client_profile(tracker_type)` | `:119` | Semilla de la conversación cuando no hay perfil |
| `set_client_profile_state_flow(project, state_flow)` | `:263` | **No se usa**: F5 escribe por `save_client_profile` (un solo camino) |
| `validate_client_profile(profile)` | `:274` | Gate duro antes de aplicar (F5). **Nunca lanza** |
| `_read_project_config_raw(project)` | `:339` | Seam único de disco; el copiloto **no** lo llama directo |
| `load_client_profile(project)` → `dict \| None` | `:358` | Base del diff (F4) |
| `has_client_profile(project)` | `:375` | Distingue "perfil ausente" de "perfil incompleto" |
| `get_project_tracker_type(project)` | `:379` | Adapta las preguntas al tracker |
| `load_effective_client_profile(project)` → **nunca None** | `:388` | Lectura del copiloto (F2) |
| `save_client_profile(project, profile)` | `:407` | **Única escritura** del plan (F5) |
| `_deep_merge` / `merge_with_defaults` | `:454` / `:465` | Merge de la propuesta sobre la base (F4) |
| `complete_client_profile(...)` | `:492` | Prellenado que el copiloto muestra como "ya deducido" |

**Allowlist de PATCH — `backend/services/client_profile_keys.py`:**

- `PATCHABLE_PROFILE_KEYS` (`:14-19`) tiene **EXACTAMENTE 4 keys**, todas DevOps: `devops_pipeline_drafts`, `devops_publication_presets`, `devops_publication_settings`, `devops_environment_settings`.
- `validate_profile_key(key, value)` (`:22`) devuelve literalmente `f"key '{key}' no es parcheable."` para cualquier otra key (`:35`).

> ⚠️ **CORRECCIÓN AL SUPUESTO INICIAL — verificada abriendo el archivo.** `patch_client_profile_key` **NO sirve** para escribir `code_layout`, `language`, `tracker_state_machine` ni ninguna sección del perfil: esas keys **no están** en `PATCHABLE_PROFILE_KEYS`, y el endpoint devuelve `400 {"error": "key_not_patchable"}` (`api/client_profile.py:335-337`). Además el endpoint entero está detrás de `STACKY_DEVOPS_BOOTSTRAP_ENABLED` y hace `abort(404)` si está OFF (`:326-328`).
> **Consecuencia de diseño (obligatoria):** la escritura de F5 va por el riel **GET → merge → validate → `save_client_profile`**, exactamente el mismo riel que ya usa la UI (`ClientProfileEditor.tsx:792` → `ClientProfileApi.save`). **No se agrega ninguna key a `PATCHABLE_PROFILE_KEYS`.**

**API — `backend/api/client_profile.py` (575 líneas), blueprint `client_profile_bp` registrado en `api/__init__.py:10` y `:148`:**

| Endpoint | Línea | Nota |
|---|---|---|
| `GET /api/client-profile/default` | `:156-161` | Devuelve `{ok, tracker_type, template}` |
| `GET /api/projects/<name>/client-profile` | `:166-198` | Devuelve `profile`, `prefilled_profile`, `path_check`, `validation`, `work_item_types`, `valid_states` |
| `PUT /api/projects/<name>/client-profile` | `:203` | Acepta `{"profile": {...}}` o el perfil pelado (`:210`) |
| `PATCH .../client-profile/keys/<key>` | `:324` | **Sólo las 4 keys DevOps**; gate `STACKY_DEVOPS_BOOTSTRAP_ENABLED` |
| `GET .../process-catalog/autodetect` | `:392` | Read-only, nunca escribe (`:373-376`) |
| `DELETE .../client-profile` | `:473` | No se usa acá |
| `POST/GET .../db-readonly-auth` | `:492` / `:554` | **Credenciales — zona prohibida para el copiloto (P6)** |
| `_PROFILE_WRITE_LOCK = threading.Lock()` | `:320` | El apply de F5 lo reusa |
| `record_event(action=..., project=..., result=..., actor=..., ...)` | `:362-369` | Molde exacto de la auditoría de F5 |

**Frontend — `frontend/src/components/ClientProfileEditor.tsx`:**

- `export default function ClientProfileEditor()` en `:609` — **NO recibe props**. El proyecto sale de `activeProject?.name` (`:612`), y los datos de `ClientProfileApi.get(projectName!)` vía react-query con `queryKey: ["client-profile", projectName]` (`:615-617`).
- Guarda con `ClientProfileApi.save(projectName, profileToSave)` (`:792`) e invalida `["client-profile", projectName]` y `["projects"]` (`:799-800`).
- `if (!projectName) { ... }` en `:686` — ya hay estado vacío.
- `ClientProfileApi` vive en `frontend/src/api/endpoints.ts:2245-2263` con `get` / `save` / `clear` / `defaultTemplate`.

> **Por eso el copiloto se ancla ACÁ y no en un tab nuevo.** Un tab nuevo tiene trece patas y sólo dos las exige `tsc`; las otras once fallan mudas. `ClientProfileEditor` ya resuelve proyecto activo, fetch, invalidación de caché y estado vacío.

**Runtimes — `backend/services/runtime_capabilities.py`:**

| Símbolo | Línea | Contenido verificado |
|---|---|---|
| `RUNTIMES` | `:31` | `("claude_code_cli", "codex_cli", "github_copilot")` — vocabulario **CERRADO** |
| `EFFORTS` | `:28` | `("low","medium","high","xhigh","max")` |
| `EFFORT_MODE` | `:34-38` | `claude_code_cli`=`"nativo"`, `codex_cli`=`"presupuesto_turnos"`, `github_copilot`=`"no_aplica"` |
| `capabilities_for(runtime)` | `:70` | Devuelve SIEMPRE 11 claves; **nunca lanza, nunca None** (`:71-77`) |
| `clamp_selection(...)` | `:149` | Normaliza `(runtime, model, effort)` |
| `codex_turn_budget(...)` | `:206` | Presupuesto de turnos de codex |
| `resolve_run_selection(...)` | `:228` | Resolución de la selección efectiva |
| `pref_key_for(project)` | `:306` | `"runSelection." + slug`, ≤128 chars |
| `load_run_preference(project)` | `:316` | `None` si la flag `STACKY_RUN_SELECTION_PREFS_ENABLED` está OFF (`:324`) |
| `save_run_preference(project, sel)` | `:333` | Devuelve **`False` sin lanzar** si la flag está OFF (`:339-340`) |
| `build_model_effort_trace(...)` | `:360` | Traza de modelo/effort |

**Preflight — `backend/services/run_preflight.py`:**

| Símbolo | Línea | Nota |
|---|---|---|
| `_RUNTIMES_REQUIRING_REPO = {"claude_code_cli", "codex_cli"}` | `:28` | `github_copilot` NO exige repo git |
| `_RUNTIME_BINS = {"claude_code_cli": "CLAUDE_CODE_CLI_BIN", "codex_cli": "CODEX_CLI_BIN"}` | `:31-34` | `github_copilot` no tiene binario |
| `class PreflightResult(ok, warnings, failure_check, failure_detail)` | `:37-54` | |
| `check(*, ticket, runtime, project=None)` | `:57` | **Exige un `ticket`** |
| `_get_runtime_bin(env_key, runtime)` | `:263-273` | Defaults `{"CLAUDE_CODE_CLI_BIN": "claude", "CODEX_CLI_BIN": "codex"}` |
| `_binary_resolvable(bin_name)` | `:276-280` | `shutil.which` o ruta absoluta |

> ⚠️ **TRAMPA MEDIDA en `check()`:** `run_preflight.py:76-83` lee `STACKY_RUN_PREFLIGHT_GATE_ENABLED` y, si está OFF, **devuelve `PreflightResult(ok=True)` sin verificar nada** (`:82-83`). Una consulta de disponibilidad que llame a `check()` diría "todo disponible" siempre que esa flag esté apagada. **Por eso F1 NO llama a `check()`**: reusa `_get_runtime_bin` y `_binary_resolvable` (los dos helpers puros) y hace su propio veredicto, sin gate. K2 lo verifica.

**Ejecución — `backend/agent_runner.py`:**

- `def run_agent(*, agent_type, ticket_id, context_blocks, user, ..., runtime: str = "github_copilot", vscode_agent_filename=None, project_name=None, work_item_type="Epic", workspace_root_override=None) -> int` — `:151`.
- Bifurcación: `:319` `if runtime == "codex_cli"` → `services.codex_cli_runner.start_codex_cli_run`; `:398` `elif runtime == "claude_code_cli"` → `services.claude_code_cli_runner.start_claude_code_cli_run`; el default (`github_copilot`) va por `copilot_bridge` + `services/llm_router.py` (`backend == "copilot"` en `:164`, `"copilot"/"vscode_bridge"` en `:296`).
- `_VALID_RUNTIMES = {"github_copilot", "codex_cli", "claude_code_cli"}` — `api/agents.py:337`.
- `codex_cli` y `claude_code_cli` **EXIGEN** `vscode_agent_filename`: `api/agents.py:480`, `:857`, `:1067`, `:1259` rechazan la corrida si falta. `github_copilot` **no** lo exige. Es una diferencia real de contrato y la ficha de F1 la declara (campo `exige_agente_vscode`).

**Seam one-shot de LLM — `backend/copilot_bridge.py`:**

- `def invoke(*, agent_type, system, user, on_log, execution_id=None, model=None, project_name=None, workspace_root=None, bridge_port=None) -> BridgeResponse` — `:145-156`. Usado por `services/ado_pipeline_inference.py:277`.
- **Rutea por `config.LLM_BACKEND`, NO por el runtime elegido** (`:157-174`: `mock` / `vscode_bridge` / `copilot`).

> ⚠️ **Consecuencia dura, y es el corazón del diseño:** `copilot_bridge.invoke` **no honra** `runtime == "codex_cli"` ni `"claude_code_cli"`. Son dos ejes distintos (`LLM_BACKEND` vs. runtime de corrida). El único camino de esos dos runtimes es `run_agent`, que exige `ticket_id` **y** `vscode_agent_filename`. Un copiloto que dependa de un LLM one-shot funcionaría **sólo** con `github_copilot` y mentiría en los otros dos.
> **Por eso el motor conversacional de este plan es DETERMINISTA** (§4, P3). La asistencia por LLM es una capa **opcional y declarada**, no el motor.

**Patrón conversacional a imitar — `backend/services/pipeline_session.py` (198 líneas):**

- `SESSION_VERSION = "1"`, `MAX_SESSION_BYTES = 8192`, `MAX_AUTO_RETRIES = 2` — `:10-12`. Constantes de módulo, **no flags**. Este plan hace lo mismo.
- `PIPELINE_SESSION_STATES` (8 estados, tupla cerrada) — `:15-24`; `TRANSITIONS` — `:27-36`; `TERMINAL_STATES` — `:38`.
- `@dataclass(frozen=True) class PipelineSession` — `:51-64`.
- `can_transition(origen, destino)` — `:67`, **NUNCA lanza** (`:71-73`).
- `advance(session, destino, **campos)` → `(sesion, motivo)` — `:76-93`; filtra campos inventados con `__dataclass_fields__` (`:87-90`) y **nunca lanza** (`:92-93`).
- `session_to_dict(s)` — `:96`, serialización 1:1 sin encoder custom.
- El módulo es **PURO**: "sin flask, sin config, sin IO, sin red, sin modelo" (`:3`).

**Molde de frontend a imitar — `frontend/src/components/devops/pipelineCopilotModel.ts` (251 líneas):**

- Docstring `:3-5`: *"El repo NO tiene RTL ni jsdom, asi que toda la logica testeable vive aca y el .tsx queda como cascaron de presentacion."*
- Exporta tipos + constantes espejo del backend + funciones puras (`stateLabel`, `AVAILABLE_BY_STATE`). Su test es `frontend/src/components/devops/__tests__/pipelineCopilotModel.test.ts`.

**Guardianes de flags (los que este plan toca, verificados):**

1. `backend/config.py` — atributo de clase con `os.getenv("KEY", "true"/"false").lower() in ("1","true","yes")`. Molde exacto: `:1913-1917`.
2. `backend/services/harness_flags.py` — `FlagSpec(key=, type=, label=, description=, group=, env_only=, requires=, default=)`. Molde exacto: `:4216-4234`.
3. `backend/services/harness_flags.py` — `_CATEGORY_KEYS` (`:120`). Nota literal en `:626`: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` (arriba) o el test..."*. Categorías existentes usadas por este plan: **`flujo_funcional`** y **`capacidades_optin`**.
4. `backend/tests/test_harness_flags.py` — `_CURATED_DEFAULTS_ON`. **Sólo para booleanas con `default=True`.**
5. `backend/services/harness_flags_help.py` — `PLAIN_HELP` (`:25`), texto llano de la UI. **No se deriva de `description`.**

### 3.2 Lo que NO EXISTE hoy, y en qué fase se construye

| # | Capacidad ausente | Evidencia de la ausencia | Fase |
|---|---|---|---|
| N1 | Campo **(1) disponible y correctamente configurado** por runtime | `capabilities_for` (`runtime_capabilities.py:70-77`) devuelve 11 claves y ninguna es disponibilidad | **F1** |
| N2 | Campo **(2) para qué tarea se recomienda** | No existe ninguna tabla de recomendación por tarea en `services/` | **F1** |
| N3 | Campo **(4) permisos / credenciales que necesita** | `_RUNTIME_BINS` (`run_preflight.py:31`) sólo nombra variables de binario, no credenciales | **F1** |
| N4 | Campo **(5) local vs. integración externa** | Deducible de `_RUNTIMES_REQUIRING_REPO` y de la bifurcación de `agent_runner.py:319/398`, pero **no declarado en ningún lado** | **F1** |
| N5 | Campo **(6) qué ocurre si la ejecución falla** | No existe | **F1** |
| N6 | **Disponibilidad sin disparar una corrida** | `run_preflight.check` exige `ticket=` (`:57-62`) y se invoca desde `agent_runner.run_agent` (`:180-200`); además se auto-desactiva con la flag (`:82-83`) | **F1** |
| N7 | Cálculo de **completitud** del perfil y **banco de preguntas** derivado de lo que falta | No hay ningún símbolo de completitud en `client_profile*.py` | **F2** |
| N8 | **Sesión conversacional** del perfil (estados, transiciones, runtime pegado) | `pipeline_session.py` es del eje pipelines y no es reusable tal cual | **F3** |
| N9 | **Diff propuesto** del perfil (antes/después por path, con motivo) | `_deep_merge` (`:454`) mergea pero no reporta qué cambió | **F4** |
| N10 | **Aplicación** confirmada del diff sobre el perfil real | Hay `save_client_profile`, pero nadie lo llama desde un flujo conversacional | **F5** |
| N11 | Superficie de UI conversacional del perfil | `ClientProfileEditor.tsx` es puro formulario | **F6** |

### 3.3 Deuda de comentario detectada (no bloquea, se corrige en F7)

`backend/agent_runner.py:317` dice textualmente que `claude_code_cli` está *"bloqueado en endpoint (HTTP 501). Nunca debería llegar aquí."*

**Es FALSO y está desactualizado**, verificado por tres vías independientes:
1. No hay ningún `501` en `api/agents.py`.
2. `_VALID_RUNTIMES` (`api/agents.py:337`) acepta los tres runtimes.
3. `agent_runner.py:398` despacha `claude_code_cli` a `start_claude_code_cli_run` normalmente.

Si alguien planificara sobre ese comentario, escribiría un plan con Claude "bloqueado" — un supuesto de capacidad falso. **F7 corrige el comentario** (una línea, sin cambio de comportamiento) y agrega el test que ancla la verdad.

---

## 4. Principios y guardarraíles

**P1 — El perfil tiene UN solo modelo y UN solo escritor.** El copiloto lee con `load_effective_client_profile`, valida con `validate_client_profile`, y escribe **exclusivamente** con `save_client_profile`. No hay store paralelo, no hay archivo nuevo de perfil, no se toca `PATCHABLE_PROFILE_KEYS`.

**P2 — El usuario elige el runtime ANTES, explícitamente, y con la ficha completa a la vista.** Sin runtime elegido, la sesión no arranca: el estado inicial es `eleccion_runtime` y la única transición legal desde ahí exige un `runtime` de `RUNTIMES`. El sistema **recomienda** (campo `recomendado_para` + un `recomendacion` calculada), pero **nunca elige**.

**P3 — El motor conversacional es DETERMINISTA; el LLM es una capa opcional y declarada.** El banco de preguntas, la detección de faltantes y la construcción del diff se derivan del schema del perfil y de las fuentes deterministas que ya existen (`complete_client_profile`, `get_default_client_profile`, `autodetect_process_catalog`). Esto garantiza **paridad exacta en los 3 runtimes** sin ninguna plumería de LLM nueva. La asistencia por LLM se declara en la ficha como `asistencia_llm` y hoy es `"no_disponible"` para `codex_cli` y `claude_code_cli` (no tienen seam one-shot: su único camino es `run_agent`, que exige `ticket_id` + `vscode_agent_filename`) y `"segun_llm_backend"` para `github_copilot` (`copilot_bridge.invoke` rutea por `config.LLM_BACKEND`, `copilot_bridge.py:157-174`).

**P4 — Fallback de CAPACIDAD sí; fallback de RUNTIME jamás.** (Resolución explícita de la tensión "paridad con fallback" vs. "sin fallback silencioso".)
- **LEGÍTIMO:** si el runtime elegido no puede algo, se **declara** y se degrada **visiblemente** (campo con valor `"no_disponible"` + `motivo` en castellano). El copiloto sigue funcionando en lo que sí puede.
- **PROHIBIDO:** cambiar de runtime por cuenta propia, en cualquier circunstancia, incluida la falla.
- Ante un fallo del runtime elegido, la respuesta **conserva `runtime_elegido` intacto**, informa el error, y expone `cambio_sugerido: {"runtime": ..., "motivo": ...}` **sin aplicarlo**. Cambiar exige un turno nuevo con `cambiar_runtime: true` del usuario.
- Verificado por `test_plan296_paridad_runtimes.py::test_fallo_no_cambia_el_runtime_elegido` y `::test_cambio_de_runtime_exige_bandera_explicita`.

**P5 — Se ve antes de aplicarse, y se confirma antes de guardarse.** El copiloto **siempre** produce un diff (`ProfilePatch`) que enumera cada cambio con `path`, `antes`, `despues`, `motivo` y `sensible`. Aplicar exige `confirm_token` derivado del diff: si el diff cambió, el token no valida y no se escribe nada.

**P6 — El copiloto NO toca credenciales, nunca.** Cualquier propuesta que contenga una key de `_SECRET_KEYS` (`client_profile.py:42-44`) se rechaza **antes** de llegar a `validate_client_profile`, con mensaje propio. Las credenciales de BD siguen yendo por su endpoint dedicado (`api/client_profile.py:492`), manejado por el operador a mano.

**P7 — Rieles de la casa, sin excepción.**
- `services/` **NO importa de `api/`**. Cuando el plan necesita la preferencia de runtime, llama a `runtime_capabilities.save_run_preference` / `load_run_preference` (ese módulo hace su propio import perezoso de `api.preferences`, `runtime_capabilities.py:326` y `:348`); los módulos nuevos de este plan **no importan `api.*` en ningún nivel**.
- **Cero threads nuevos.** `backend/app.py:635-636` dice textual "NO agregar threads nuevos". Este plan no crea ninguno: todo es request/response.
- **Mono-operador sin login/roles.** Ningún `403` de permiso. `403`/`404` sólo significan "flag apagada".
- **Toda flag/config del operador va por UI** (`env_only=False`).

**P8 — Sesión sin persistencia nueva.** La sesión viaja en el request/response (el frontend la devuelve tal cual la recibió), calcada de `PipelineSession` + `session_to_dict`. Tope duro `MAX_SESSION_BYTES = 8192` como constante de módulo, igual que `pipeline_session.py:11`. **No se crea ninguna tabla, ningún archivo de estado, ningún cache global.** La ÚNICA cosa que se persiste es la elección de runtime, y por el riel que ya existe (`save_run_preference`).

**P9 — Cero trabajo extra al operador, y backward-compatible.** Con las flags en su default, el `ClientProfileEditor` de hoy sigue funcionando **exactamente igual**; el copiloto aparece como un panel adicional. Con `STACKY_PROFILE_COPILOT_ENABLED=false`, la UI vuelve byte a byte al comportamiento previo.

---

## 5. Flags

| Flag | Tipo | Default | Categoría | Justificación |
|---|---|---|---|---|
| `STACKY_PROFILE_COPILOT_ENABLED` | bool | **ON** | `flujo_funcional` | Conversa, detecta, recomienda y **muestra** el diff. No escribe nada. No consume tokens en reposo (no hay loop, daemon, barrido, polling ni prefetch: sólo responde a turnos que el operador manda). No cae en (A) ni en (B). |
| `STACKY_PROFILE_COPILOT_APPLY_ENABLED` | bool | **OFF** | `capacidades_optin` | **Causal (B):** escribe la sección `client_profile` en `projects/<NAME>/config.json`, que es la configuración real del proyecto del operador y gobierna el ruteo de agentes (`state_flow`, `tracker_state_machine`) y el contexto que se le inyecta a todo agente (`context_enrichment.build_client_profile_block`). Es escritura en un sistema real del operador. |

**Cableado exacto de cada flag (F0):**

`STACKY_PROFILE_COPILOT_ENABLED` (nace **ON** ⇒ los TRES lugares del default ON):
1. `backend/config.py` — `os.getenv("STACKY_PROFILE_COPILOT_ENABLED", "true").lower() in ("1","true","yes")`
2. `backend/services/harness_flags.py` — `FlagSpec(..., default=True)`
3. `backend/tests/test_harness_flags.py` — la key **en `_CURATED_DEFAULTS_ON`**
4. `backend/services/harness_flags.py` — la key en `_CATEGORY_KEYS["flujo_funcional"]`
5. `backend/services/harness_flags_help.py` — entrada en `PLAIN_HELP`

`STACKY_PROFILE_COPILOT_APPLY_ENABLED` (nace **OFF** ⇒ **NINGÚN `default=`**):
1. `backend/config.py` — `os.getenv("STACKY_PROFILE_COPILOT_APPLY_ENABLED", "false").lower() in ("1","true","yes")`
2. `backend/services/harness_flags.py` — `FlagSpec(...)` **sin `default=`** y con `requires="STACKY_PROFILE_COPILOT_ENABLED"`
3. **NO** va en `_CURATED_DEFAULTS_ON` (ese set es sólo para booleanas con `default=True`)
4. `backend/services/harness_flags.py` — la key en `_CATEGORY_KEYS["capacidades_optin"]`
5. `backend/services/harness_flags_help.py` — entrada en `PLAIN_HELP`

> ⚠️ **Trampa a evitar:** `default_is_known()` es `spec.default is not None`. Poner `default=False` explícito en la FlagSpec de la flag OFF pone en **rojo** `test_default_known_only_for_curated`. El `default=` se OMITE, no se pone en `False`.

---

## 6. Fases

### F0 — Las dos flags nacen bien cableadas

**Objetivo:** registrar las 2 flags con sus 5 guardianes cada una, para que F1..F7 sólo las consuman.
**Valor:** el bloque de flags es atómico; hacerlo aparte evita que un rojo de arnés tumbe una fase de producto.

**Archivos a editar:**
- `Stacky Agents/backend/config.py` — 2 atributos nuevos, junto al bloque DevOps (molde `:1913-1917`).
- `Stacky Agents/backend/services/harness_flags.py` — 2 `FlagSpec` en `FLAG_REGISTRY` (molde `:4216-4234`) + `STACKY_PROFILE_COPILOT_ENABLED` en `_CATEGORY_KEYS["flujo_funcional"]` + `STACKY_PROFILE_COPILOT_APPLY_ENABLED` en `_CATEGORY_KEYS["capacidades_optin"]`.
- `Stacky Agents/backend/services/harness_flags_help.py` — 2 entradas en `PLAIN_HELP` (`:25`).
- `Stacky Agents/backend/tests/test_harness_flags.py` — `STACKY_PROFILE_COPILOT_ENABLED` en `_CURATED_DEFAULTS_ON`.

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

**Casos de test (`test_plan296_flags.py`):**
1. `test_flag_conversacional_nace_on` — `config.STACKY_PROFILE_COPILOT_ENABLED is True` con el entorno limpio.
2. `test_flag_apply_nace_off` — `config.STACKY_PROFILE_COPILOT_APPLY_ENABLED is False`.
3. `test_ambas_flags_estan_en_el_registry` — las dos keys están en `{s.key for s in FLAG_REGISTRY}`.
4. `test_apply_no_declara_default` — `next(s for s in FLAG_REGISTRY if s.key == "STACKY_PROFILE_COPILOT_APPLY_ENABLED").default is None`.
5. `test_conversacional_declara_default_true` — `... .default is True`.
6. `test_apply_requiere_al_master` — `... .requires == "STACKY_PROFILE_COPILOT_ENABLED"`.
7. `test_ambas_son_editables_por_ui` — `spec.env_only is False` en las dos.
8. `test_ambas_tienen_categoria` — cada key aparece en exactamente una tupla de `_CATEGORY_KEYS`.
9. `test_ambas_tienen_ayuda_llana` — las dos keys están en `harness_flags_help.PLAIN_HELP`.

**Comando de test:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_flags.py" -q
```

**Criterio de aceptación BINARIO:**
- `test_plan296_flags.py`: **9 passed, 0 failed**.
- `test_harness_flags.py`: **cero fallos nuevos respecto de la línea base medida en el commit base ANTES de tocar nada.** Se mide con el mismo comando sobre el archivo, se anota el par `(passed, failed)`, y tras F0 el `failed` debe ser **≤** el basal y el `passed` **≥** el basal.
  ```
  "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
  ```
- `test_harness_flags_help.py`: mismo criterio delta. **Este archivo tiene rojos de fábrica: no se exige verde absoluto, se exige `failed` no mayor que el basal.**
  ```
  "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
  ```

**Flag que la protege:** ninguna (es la fase que las crea).
**Impacto por runtime:** ninguno — las flags son transversales; ningún runtime cambia de comportamiento en F0.
**Trabajo del operador: ninguno.**

---

### F1 — La ficha del runtime deja de estar a medias: 7 de 7, y la disponibilidad se consulta sin correr nada

**Objetivo:** un módulo puro que, para cada uno de los 3 runtimes, responda los **siete** puntos que el operador exige, con la disponibilidad medida de verdad y **sin disparar una corrida**.
**Valor:** el usuario elige el runtime sabiendo qué elige. Cierra N1..N6.

**Archivo a crear:** `Stacky Agents/backend/services/runtime_profile.py`
**Archivo a editar:** `Stacky Agents/backend/api/__init__.py` (registrar el blueprint nuevo de F3; en F1 sólo se crea el servicio — ver nota de orden abajo).

> **Nota de orden:** el endpoint de la ficha vive en el blueprint de F3 (`api/profile_copilot.py`) para no crear dos blueprints. F1 entrega **el servicio puro y su test**; F3 lo expone. Esto mantiene F1 sin ninguna dependencia de Flask.

**Símbolos exactos de `services/runtime_profile.py`:**

```python
"""Plan 296 F1 — La ficha COMPLETA de cada runtime.

PURO: sin flask, sin red, sin escritura. Importa `runtime_capabilities` y dos
helpers de `run_preflight` (los únicos dos que son puros). NO importa api.*.
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
        "Primer contacto: es el único que no necesita repo git ni archivo de agente",
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
    "claude_code_cli": "local",              # proceso local sobre tu repositorio
    "codex_cli":       "local",              # proceso local sobre tu repositorio
    "github_copilot":  "integracion_externa",# va por el puente del editor / servicio de GitHub
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

def binary_availability(runtime: str) -> dict: ...
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
- **Nunca lanza.** Cualquier excepción al importar/resolver ⇒ `binario_resoluble = False` y `motivo` en la ficha.
- **NO llama a `run_preflight.check`** (que se auto-desactiva con `STACKY_RUN_PREFLIGHT_GATE_ENABLED`, `run_preflight.py:82-83`). Usa sólo `_get_runtime_bin` (`:263`) y `_binary_resolvable` (`:276`).

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
  "capacidades": {                        # capabilities_for(runtime) tal cual + 2 derivados
      ... las 11 claves de runtime_capabilities.capabilities_for ...,
      "exige_agente_vscode": True,        # api/agents.py:480,857,1067,1259
      "asistencia_llm": "no_disponible",  # ver P3
      "asistencia_llm_motivo": "Este runtime sólo corre asociado a un ticket y a un "
                               "archivo de agente; no tiene un camino de consulta corta.",
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

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_runtime_profile.py`

**Casos:**
1. `test_ficha_tiene_los_siete_campos_para_los_tres_runtimes` — para cada `r` en `RUNTIMES`: `set(FICHA_CAMPOS) <= set(runtime_profile(r))`. **(K1)**
2. `test_disponibilidad_no_depende_del_gate_de_preflight` — con `STACKY_RUN_PREFLIGHT_GATE_ENABLED` monkeypatcheado a `False`, `binary_availability("codex_cli")` **igual** reporta `binario_resoluble` real (se fuerza con `monkeypatch` de `run_preflight._binary_resolvable` a `lambda _: False` y se asserta `disponible is False`). **(K2)**
3. `test_disponibilidad_no_dispara_ninguna_corrida` — se monkeypatchea `agent_runner.run_agent` a una función que hace `raise AssertionError("no debe correrse")`, y se llama `all_runtime_profiles()`: no lanza.
4. `test_copilot_no_requiere_binario_ni_repo` — `binary_availability("github_copilot")["requiere_binario"] is False` y `["requiere_repo_git"] is False`.
5. `test_cli_requieren_repo_git` — para `claude_code_cli` y `codex_cli`, `["requiere_repo_git"] is True`.
6. `test_exige_agente_vscode_es_true_solo_para_los_dos_cli` — `github_copilot` ⇒ `False`; los otros dos ⇒ `True`.
7. `test_asistencia_llm_declarada_por_runtime` — `github_copilot` ⇒ `"segun_llm_backend"`; los otros dos ⇒ `"no_disponible"` **y** `asistencia_llm_motivo` no vacío.
8. `test_runtime_desconocido_devuelve_ficha_completa_y_no_disponible` — `runtime_profile("gpt5_cli")` trae las 7 claves, `conocido is False`, `disponible is False`.
9. `test_binary_availability_nunca_lanza` — con `run_preflight._get_runtime_bin` monkeypatcheado a `raise RuntimeError`, devuelve dict con `binario_resoluble is False`.
10. `test_recomendar_no_devuelve_runtime_no_disponible` — con las 3 fichas forzadas a `disponible=False`, `recomendar_runtime(...)["runtime"] is None`.
11. `test_recomendar_explica_el_motivo` — `motivo` no vacío en los tres escenarios (uno, varios, ninguno).
12. `test_capacidades_conserva_las_once_claves_de_capabilities_for` — `set(capabilities_for(r)) <= set(runtime_profile(r)["capacidades"])`.
13. `test_no_importa_api` — `"api." not in inspect.getsource(runtime_profile_module)` para los imports top-level (assert sobre el **mensaje**: la lista de líneas ofensoras se incluye en el `assert`, no un booleano pelado).

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_runtime_profile.py" -q
```

**Criterio BINARIO:** **13 passed, 0 failed** con el comando de arriba.
**Flag:** ninguna propia (módulo puro). Su exposición HTTP la gatea `STACKY_PROFILE_COPILOT_ENABLED` en F3.
**Impacto por runtime:** los tres reciben ficha de 7 campos. Degradación visible: `claude_code_cli`/`codex_cli` declaran `asistencia_llm="no_disponible"` con motivo; `github_copilot` declara `"segun_llm_backend"`. **Ningún runtime se sustituye por otro.**
**Trabajo del operador: ninguno.**

---

### F2 — Qué falta, qué está mal, cuánto llevamos: la completitud y el banco de preguntas

**Objetivo:** un módulo puro que, dado un proyecto, diga qué secciones del perfil ya están (y no se vuelven a preguntar), cuáles faltan, qué inconsistencias hay, y **cuál es la próxima pregunta**.
**Valor:** cierra N7 y hace posibles los KPI K3 y K4.

**Archivo a crear:** `Stacky Agents/backend/services/profile_completeness.py`

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
def preguntas_pendientes(estado: dict) -> list[Pregunta]: ...
def proxima_pregunta(estado: dict, ya_respondidas: tuple[str, ...]) -> Pregunta | None: ...
def completitud(estado: dict) -> dict: ...
```

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
  "inconsistencias": [ {"seccion": "...", "detalle": "...", "origen": "validacion"|"path_check"} ],
}
```
- Una sección **cuenta como presente** si está en el perfil, es un `dict`, y **no está vacía**. Un `{}` cuenta como AUSENTE (es el caso real de un perfil recién sembrado del template): esto es lo que hace que K4 sea honesto.
- `inconsistencias` se puebla con los `errors` y `warnings` de `validate_client_profile` mapeados a su sección por prefijo del mensaje (`client_profile.<seccion>`), más los que no matcheen bajo `seccion: "general"`.

**Contrato de `completitud(estado) -> dict`:**
```python
{
  "requeridas_ok": 2, "requeridas_total": 3,
  "opcionales_ok": 1, "opcionales_total": 6,
  "porcentaje": 33,           # int, floor(requeridas_ok / requeridas_total * 100). Sólo requeridas.
  "listo_para_usar": False,   # requeridas_ok == requeridas_total AND validacion["ok"] is True
}
```

**Regla anti-repetición (el corazón de K4):** `preguntas_pendientes(estado)` **excluye toda sección presente**. `proxima_pregunta` además excluye los ids en `ya_respondidas` y devuelve primero las obligatorias, en el orden de `SECCIONES_REQUERIDAS`. Si no queda ninguna, devuelve `None`.

**Adaptación por contexto (lo que el operador pide como "preguntas inteligentes"):** el banco se adapta por `tracker_type`. Para `azure_devops` la pregunta de `tracker_state_machine` ofrece como `opciones` los estados reales, tomados del mismo helper que ya usa la UI (`api/client_profile.py::_valid_states_for`, `:132`) — pero **como `services/` no importa `api/`**, F2 recibe las opciones por parámetro: `preguntas_pendientes(estado, *, estados_validos=(), tipos_work_item=())`. El endpoint de F3 (que sí puede importar `api`) las provee. **Con las tuplas vacías la pregunta degrada a `tipo="texto"` — visible, nunca muda.**

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_completitud.py`

**Casos:**
1. `test_perfil_vacio_falta_las_tres_requeridas` — `estado_perfil` sobre un proyecto sin perfil ⇒ `secciones_faltantes_requeridas == list(SECCIONES_REQUERIDAS)`.
2. `test_seccion_ya_completa_no_genera_pregunta` — con `code_layout` poblado, ningún `Pregunta.seccion == "code_layout"` en `preguntas_pendientes`. **(K4)**
3. `test_seccion_vacia_cuenta_como_ausente` — `{"code_layout": {}}` ⇒ `code_layout` en faltantes.
4. `test_completitud_solo_cuenta_requeridas` — 3/3 requeridas y 0/6 opcionales ⇒ `porcentaje == 100`.
5. `test_listo_para_usar_exige_validacion_ok` — con las 3 requeridas presentes pero `validate_client_profile` devolviendo `ok=False` (perfil con una key de `_SECRET_KEYS`), `listo_para_usar is False`.
6. `test_proxima_pregunta_respeta_ya_respondidas` — pasar el id de la primera ⇒ devuelve la segunda.
7. `test_proxima_pregunta_devuelve_none_cuando_no_falta_nada`.
8. `test_obligatorias_van_antes_que_opcionales` — el índice de la última obligatoria < índice de la primera opcional.
9. `test_estados_validos_vacios_degradan_a_texto_libre` — `preguntas_pendientes(estado, estados_validos=())` ⇒ la pregunta de `tracker_state_machine` tiene `tipo == "texto"` y `opciones == ()`.
10. `test_estados_validos_poblados_dan_eleccion` — con `estados_validos=("New","Active","Closed")` ⇒ `tipo == "eleccion"` y `opciones == ("New","Active","Closed")`.
11. `test_inconsistencias_mapean_a_su_seccion` — un perfil con `code_layout` de tipo `list` (error de `_check_section_type`) ⇒ hay una inconsistencia con `seccion == "code_layout"`. El assert compara el **mensaje** (`"code_layout"` dentro de `detalle`), no un conteo.
12. `test_toda_pregunta_tiene_texto_y_motivo_no_vacios` — para las 9 secciones.
13. `test_no_importa_api` — mismo assert-con-mensaje que F1.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_completitud.py" -q
```

**Criterio BINARIO:** **13 passed, 0 failed**.
**Flag:** ninguna propia (módulo puro). Gate en F3.
**Impacto por runtime:** **idéntico en los 3** — es determinista, no consulta ningún modelo. Cero degradación.
**Trabajo del operador: ninguno.**

---

### F3 — La sesión: máquina de estados, el runtime pegado, y el turno

**Objetivo:** la conversación como máquina de estados cerrada, con el runtime elegido pegado a la sesión y una regla explícita que impide cambiarlo solo.
**Valor:** cierra N8 y materializa P2, P4 y P8.

**Archivos a crear:**
- `Stacky Agents/backend/services/profile_copilot_session.py`
- `Stacky Agents/backend/api/profile_copilot.py` (blueprint `profile_copilot_bp`)

**Archivo a editar:** `Stacky Agents/backend/api/__init__.py` — importar y registrar `profile_copilot_bp` siguiendo el molde exacto de `client_profile_bp` (`:10` import, `:148` registro).

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

**`backend/api/profile_copilot.py` — endpoints:**

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/runtimes/profile` | `all_runtime_profiles()` + `recomendar_runtime(...)`. Gate: `STACKY_PROFILE_COPILOT_ENABLED` |
| `GET` | `/api/projects/<name>/client-profile/copilot/state` | `estado_perfil` + `completitud` + `preguntas_pendientes` (con `estados_validos`/`tipos_work_item` de los helpers de `api/client_profile.py`) |
| `POST` | `/api/projects/<name>/client-profile/copilot/turn` | Un turno: recibe `{"session": {...}, "respuesta": "...", "runtime": "...", "cambiar_runtime": false}`; devuelve `{"ok", "session", "mensaje", "pregunta", "completitud", "runtime_elegido", "cambio_sugerido"}` |

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

**Persistencia de la elección:** al pasar a `diagnostico`, el endpoint llama `runtime_capabilities.save_run_preference(project_name, {"runtime": r, "model": None, "effort": None})` y refleja el resultado en `preferencia_persistida: bool`. Si devuelve `False` (flag `STACKY_RUN_SELECTION_PREFS_ENABLED` OFF, `runtime_capabilities.py:339-340`), la respuesta lo dice: `"La elección vale para esta sesión, pero no quedará guardada para la próxima."` **Degradación visible, nunca muda.**

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_session.py`

**Casos:**
1. `test_estado_inicial_es_eleccion_de_runtime`.
2. `test_sin_runtime_no_se_puede_diagnosticar` — `advance(s, "preguntando")` desde `eleccion_runtime` devuelve `motivo == "transicion_ilegal"`.
3. `test_elegir_runtime_valido_pasa_a_diagnostico`.
4. `test_elegir_runtime_desconocido_devuelve_motivo` — `motivo == "runtime_desconocido"` y la sesión **es la misma instancia de valores**.
5. `test_cambio_de_runtime_sin_bandera_no_cambia_nada` — `elegir_runtime(s, "codex_cli", explicito=False)` con `s.runtime_elegido == "claude_code_cli"` ⇒ motivo `"cambio_de_runtime_requiere_confirmacion"` y `s.runtime_elegido` intacto.
6. `test_cambio_de_runtime_con_bandera_explicita_si_cambia`.
7. `test_advance_ignora_campos_inventados` — `advance(s, "preguntando", campo_inventado=1)` no lanza y no agrega el campo.
8. `test_advance_desde_terminal_no_hace_nada` — motivo `"estado_terminal"`.
9. `test_can_transition_nunca_lanza` — con `None`, `123`, `""`.
10. `test_session_from_dict_ignora_claves_desconocidas_y_no_lanza`.
11. `test_round_trip_dict` — `session_from_dict(session_to_dict(s)) == s`.
12. `test_sesion_serializada_entra_en_el_tope` — una sesión con 40 respuestas de 100 chars ⇒ `len(json.dumps(...)) <= MAX_SESSION_BYTES`, o el test falla indicando el tamaño real en el mensaje.
13. `test_endpoint_ficha_404_con_flag_off` — flag en `False` ⇒ `GET /api/runtimes/profile` da `404`.
14. `test_endpoint_ficha_devuelve_tres_fichas_con_flag_on`.
15. `test_endpoint_turn_rechaza_runtime_desconocido_con_400_y_lista_validos` — el assert compara el **mensaje** `"runtime_desconocido"` y que `"claude_code_cli"` esté en `validos`.
16. `test_endpoint_turn_409_al_cambiar_runtime_sin_bandera` — y el body trae `runtime_elegido` igual al original.
17. `test_endpoint_turn_sesion_demasiado_grande_da_400`.
18. `test_endpoint_turn_proyecto_inexistente_da_404`.
19. `test_endpoint_turn_no_escribe_el_perfil` — monkeypatch de `services.client_profile.save_client_profile` a `raise AssertionError`; ninguna cantidad de turnos lo dispara.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_session.py" -q
```

**Criterio BINARIO:** **19 passed, 0 failed**.
**Flag:** `STACKY_PROFILE_COPILOT_ENABLED` (**ON**). Con OFF, los 3 endpoints dan `404` y la UI no monta el panel.
**Impacto por runtime:** el motor es **idéntico en los 3** (determinista). La única diferencia declarada es `asistencia_llm` en la ficha de F1. **Ningún fallback de runtime, en ninguna rama del código.**
**Trabajo del operador: opt-in (default ON)** — el panel aparece; usarlo es voluntario.

---

### F4 — Se ve antes de aplicarse: el diff del perfil

**Objetivo:** convertir las respuestas de la conversación en un diff explícito y legible, que el usuario ve **antes** de que se escriba nada.
**Valor:** cierra N9 y materializa P5. Es la mitad "informar qué cambios realizará ANTES de aplicarlos" del pedido.

**Archivo a crear:** `Stacky Agents/backend/services/profile_patch.py`

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
2. **Rechazo de keys no-dict en secciones tipadas:** si la propuesta pone un no-`dict` en una de las 9 secciones que `validate_client_profile` tipa (`client_profile.py:306-316`) ⇒ `rechazos`.
3. **Sin cambio real, sin entrada:** si `antes == despues`, no se genera `CambioPropuesto`. Esto es lo que hace que "no repetir preguntas" también signifique "no proponer lo ya escrito".
4. `sensible = path[0] in SECCIONES_SENSIBLES`.
5. `confirm_token = sha256(json.dumps(canonico, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]`, donde `canonico` es la lista de `(".".join(path), repr_estable(despues))`. **Determinista y estable entre procesos.**
6. `aplicar_sobre` usa `client_profile._deep_merge` (`:454`) sobre una `copy.deepcopy(base)`. **Nunca muta `base`.**

**Endpoint (en `api/profile_copilot.py`, agregado en esta fase):**
`POST /api/projects/<name>/client-profile/copilot/propose` → `{"ok", "patch": {...}, "validacion_previa": {...}}`, donde `validacion_previa` es `validate_client_profile(aplicar_sobre(base, patch)).to_dict()`. **Read-only: no escribe.**

> Esto es clave: el usuario ve **no sólo el diff, sino el veredicto de validación del resultado**, antes de decidir. Si `validacion_previa["ok"]` es `False`, el copiloto lo dice y ofrece corregir; **el botón de aplicar de F6 queda deshabilitado con el motivo a la vista** (deshabilitar y explicar, nunca esconder).

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_propuesta.py`

**Casos:**
1. `test_diff_lista_path_antes_y_despues`.
2. `test_sin_cambio_real_no_genera_entrada` — `base == propuesta` ⇒ `cambios == ()`.
3. `test_secreto_va_a_rechazos_no_a_cambios` — propuesta con `{"database": {"password": "x"}}` ⇒ `cambios` vacío y `rechazos` con el texto que nombra `password`. Assert sobre el **mensaje**.
4. `test_las_seis_claves_de_secret_keys_se_rechazan` — parametrizado sobre `_SECRET_KEYS`, las 6.
5. `test_seccion_sensible_marca_sensible_true` — `tracker_state_machine`, `state_flow`, `database`.
6. `test_seccion_comun_marca_sensible_false` — `language`.
7. `test_confirm_token_es_estable` — dos llamadas con la misma propuesta dan el mismo token.
8. `test_confirm_token_cambia_si_cambia_un_valor`.
9. `test_confirm_token_no_depende_del_orden_de_las_keys`.
10. `test_aplicar_sobre_no_muta_la_base` — `base` idéntico antes y después (comparación de `json.dumps(sort_keys=True)`).
11. `test_aplicar_sobre_preserva_secciones_no_tocadas`.
12. `test_no_dict_en_seccion_tipada_va_a_rechazos`.
13. `test_endpoint_propose_no_escribe` — monkeypatch de `save_client_profile` a `raise AssertionError`; el endpoint responde `200`.
14. `test_endpoint_propose_devuelve_validacion_previa_del_resultado` — con una propuesta que rompe el tipo, `validacion_previa["ok"] is False` y `errors` menciona la sección.
15. `test_endpoint_propose_404_con_flag_off`.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_propuesta.py" -q
```

**Criterio BINARIO:** **15 passed, 0 failed** (los `parametrize` cuentan: 6 casos del punto 4 + 14 restantes = **20 tests colectados, 20 passed**; el criterio se verifica leyendo la línea final de pytest, no un conteo estimado).
**Flag:** `STACKY_PROFILE_COPILOT_ENABLED` (**ON**) — es lectura y cálculo, no escribe.
**Impacto por runtime:** **idéntico en los 3**. El diff es determinista.
**Trabajo del operador: ninguno.**

---

### F5 — El copiloto EJECUTA: aplicar con confirmación explícita (flag OFF, causal (B))

**Objetivo:** cerrar el círculo — el copiloto no se limita a recopilar: aplica el diff y deja el perfil válido.
**Valor:** cierra N10 y el KPI K3. Es el "debe EJECUTAR las configuraciones" del pedido.

**Archivos a editar:** `Stacky Agents/backend/api/profile_copilot.py` (endpoint nuevo).

**Endpoint:** `POST /api/projects/<name>/client-profile/copilot/apply`

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
10. `record_event(action="profile_copilot_apply", project=<name>, result="applied", actor=_actor(), schema_version=int(normalized.get("schema_version") or 1), detail={"paths": [...], "runtime_elegido": session.runtime_elegido, "sensibles": [...]})` — molde exacto de `api/client_profile.py:362-369`.
11. Sesión ⇒ `advance(s, "aplicado")`. Respuesta `200 {"ok": true, "session": ..., "completitud": ..., "aplicados": N, "profile": normalized}`.

> **Detalle de riel:** el `_PROFILE_WRITE_LOCK` se importa **de `api.client_profile`** (api→api es legal; el que no puede es `services`→`api`). Si se creara un lock nuevo, dos escrituras concurrentes por caminos distintos podrían pisarse.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_apply.py`

**Casos:**
1. `test_apply_404_con_flag_maestra_off`.
2. `test_apply_403_con_flag_de_apply_off_y_nombra_la_flag` — el body trae `"STACKY_PROFILE_COPILOT_APPLY_ENABLED"`. Assert sobre el **mensaje**.
3. `test_apply_con_flag_off_no_escribe` — monkeypatch de `save_client_profile` a `raise AssertionError`; responde `403`.
4. `test_token_desactualizado_da_409_y_no_escribe`.
5. `test_seccion_sensible_sin_confirmar_da_409_y_no_escribe` — y el body lista la sección.
6. `test_seccion_sensible_confirmada_se_aplica`.
7. `test_perfil_invalido_da_400_y_no_escribe` — propuesta que rompe el tipo de `code_layout`.
8. `test_patch_vacio_da_400`.
9. `test_de_perfil_vacio_a_perfil_valido_en_una_sesion` — **(K3)** arranca de `{}`, aplica un patch con las 3 requeridas, y asserta `validate_client_profile(perfil_final).ok is True` **y** `set(_REQUIRED_SECTIONS) <= set(perfil_final)`.
10. `test_apply_preserva_secciones_no_tocadas` — un `devops_pipeline_drafts` preexistente sobrevive al apply.
11. `test_apply_registra_evento_de_auditoria` — se captura `record_event` con monkeypatch y se verifica `action == "profile_copilot_apply"` y que `detail["runtime_elegido"]` sea el de la sesión.
12. `test_apply_nunca_escribe_una_clave_de_secret_keys` — un patch manipulado con `password` ⇒ el rechazo de F4 ya lo sacó; si se fuerza, `validate_client_profile` lo bloquea en el paso 8 (`client_profile.py:285-290`) y el test asserta `400` + el mensaje que menciona `secretos`.
13. `test_apply_deja_la_sesion_en_estado_terminal` — `session["state"] == "aplicado"`.
14. `test_apply_no_cambia_el_runtime_elegido` — `session["runtime_elegido"]` idéntico antes y después.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_apply.py" -q
```

**Criterio BINARIO:** **14 passed, 0 failed**.
**Flag:** `STACKY_PROFILE_COPILOT_APPLY_ENABLED` (**OFF — causal (B)**: escribe `projects/<NAME>/config.json`, la configuración real del proyecto del operador, que gobierna el ruteo de agentes y el contexto inyectado a todo agente).
**Impacto por runtime:** **idéntico en los 3** — la escritura es del backend, no del runtime. El runtime elegido queda **registrado en la auditoría** (`detail["runtime_elegido"]`), lo que da trazabilidad de con qué runtime se configuró el perfil.
**Trabajo del operador: opt-in explícito** — para que el copiloto aplique cambios hay que encender `STACKY_PROFILE_COPILOT_APPLY_ENABLED` desde la UI de flags. Mientras esté apagado, el copiloto conversa, detecta y **muestra** el diff, y el operador lo aplica a mano con el botón Guardar que ya existe.

---

### F6 — El copiloto vive dentro de la pantalla que ya existe

**Objetivo:** montar el copiloto **dentro** de `ClientProfileEditor`, con toda la lógica testeable en `.ts` puro.
**Valor:** cierra N11 sin las trece patas de un tab nuevo.

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/clientProfileCopilotModel.ts` — **lógica PURA, sin DOM, sin red**.
- `Stacky Agents/frontend/src/components/__tests__/clientProfileCopilotModel.test.ts` — vitest.
- `Stacky Agents/frontend/src/components/ClientProfileCopilotPanel.tsx` — cáscara de presentación.
- `Stacky Agents/frontend/src/components/ClientProfileCopilotPanel.module.css`.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — `ProfileCopilotApi` junto a `ClientProfileApi` (`:2245`).
- `Stacky Agents/frontend/src/components/ClientProfileEditor.tsx` — montar `<ClientProfileCopilotPanel />` **arriba del formulario**, dentro del bloque que ya exige `projectName` (después de `:686`), y pasarle `projectName` y el callback de invalidación de caché que ya existe (`qc.invalidateQueries({ queryKey: ["client-profile", projectName] })`, `:799`).

> ⚠️ **PROHIBIDO** tocar `frontend/src/components/devops/PipelineCopilotSection.tsx` ni su `.module.css` ni `pipelineCopilotModel.ts` — sesión paralela viva. El panel nuevo es **hermano**, con nombre propio, en `components/` (no en `components/devops/`).

**`clientProfileCopilotModel.ts` — símbolos exactos (espejo del backend):**
```ts
export type ProfileSessionState =
  | 'eleccion_runtime' | 'diagnostico' | 'preguntando'
  | 'propuesta' | 'confirmando' | 'aplicado' | 'detenido';

/** Espejo de PROFILE_SESSION_STATES. Mismo orden. */
export const PROFILE_SESSION_STATES: ProfileSessionState[] = [...];

/** Espejo LITERAL de runtime_capabilities.RUNTIMES. */
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

export function stateLabel(s: ProfileSessionState): string;
/** Un botón por acción; nunca se esconde: se deshabilita CON motivo. */
export function accionesDisponibles(s: ProfileSessionState, applyHabilitado: boolean)
  : { id: string; habilitado: boolean; motivo: string }[];
export function fichaIncompleta(ficha: Record<string, unknown>): string[]; // campos faltantes
export function progresoTexto(c: { requeridas_ok: number; requeridas_total: number }): string;
export function puedeElegirRuntime(s: ProfileSessionState): boolean;      // sólo antes de ejecutar
export function motivoRuntimeNoDisponible(ficha: Record<string, unknown>): string;
```

**Regla de UI innegociable (viene de un incidente real del repo):** un control que no se puede usar **se deshabilita con el motivo a la vista**; **nunca se esconde**. `accionesDisponibles` devuelve siempre las mismas acciones con `habilitado` + `motivo`; el `.tsx` renderiza todas.
- Aplicar con `STACKY_PROFILE_COPILOT_APPLY_ENABLED` OFF ⇒ `{habilitado: false, motivo: "Aplicar cambios al perfil está apagado. Se puede activar desde Configuración > Arnés."}`.
- Aplicar con `validacion_previa.ok === false` ⇒ `{habilitado: false, motivo: "La propuesta deja el perfil inválido: <primer error>."}`.

**`ProfileCopilotApi` en `endpoints.ts` (molde de `ClientProfileApi`, `:2245-2263`) — usar `rawGet`/`rawPost`:**
> El wrapper `api.*` **lanza** en non-2xx. Este flujo depende de leer los cuerpos de `403`/`409`/`400` (que son estados normales del copiloto, no errores de red), así que **`ProfileCopilotApi` usa `rawGet`/`rawPost`**, no `api.get`/`api.post`.

```ts
export const ProfileCopilotApi = {
  runtimes: () => rawGet('/api/runtimes/profile'),
  state:    (p: string) => rawGet(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/state`),
  turn:     (p: string, body: unknown) => rawPost(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/turn`, body),
  propose:  (p: string, body: unknown) => rawPost(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/propose`, body),
  apply:    (p: string, body: unknown) => rawPost(`/api/projects/${encodeURIComponent(p)}/client-profile/copilot/apply`, body),
};
```

**Archivo de test a crear:** `Stacky Agents/frontend/src/components/__tests__/clientProfileCopilotModel.test.ts`

> ⚠️ **PROHIBIDO** un `.test.tsx` con React Testing Library: RTL/jsdom **no están instalados**; ese archivo reporta "no tests" y **exit 0** — un falso verde. Todo lo testeable vive en el `.ts` puro.

**Casos:**
1. `los siete estados del backend están espejados` — `PROFILE_SESSION_STATES.length === 7` y contiene los 7 ids exactos.
2. `los tres runtimes están espejados con los ids exactos` — `RUNTIMES` igual a `['claude_code_cli','codex_cli','github_copilot']`.
3. `los siete campos de la ficha están espejados`.
4. `stateLabel nunca devuelve vacío` — para los 7 y para un string inventado.
5. `RUNTIME_LABEL cubre los tres`.
6. `aplicar deshabilitado nombra la flag cuando apply está OFF` — el `motivo` contiene `STACKY_PROFILE_COPILOT_APPLY_ENABLED`.
7. `ninguna acción desaparece cuando está deshabilitada` — `accionesDisponibles(s, false).length === accionesDisponibles(s, true).length` para los 7 estados.
8. `toda acción deshabilitada tiene motivo no vacío`.
9. `fichaIncompleta detecta los campos faltantes` — con 5 de 7, devuelve los 2 nombres.
10. `fichaIncompleta devuelve [] con la ficha completa`.
11. `puedeElegirRuntime es true antes de ejecutar y false en terminales` — `true` en `eleccion_runtime`/`diagnostico`/`preguntando`/`propuesta`; `false` en `aplicado`/`detenido`.
12. `progresoTexto muestra el avance de las requeridas` — `"2 de 3"`.
13. `motivoRuntimeNoDisponible devuelve el texto del backend, no uno inventado` — con `disponibilidad_motivo` poblado, lo devuelve tal cual; vacío ⇒ `""`.

**Comandos:**
```
cd "Stacky Agents/frontend" ; npx vitest run src/components/__tests__/clientProfileCopilotModel.test.ts
cd "Stacky Agents/frontend" ; npx tsc --noEmit
```

**Criterio BINARIO:**
- vitest: **13 passed, 0 failed** y la salida **NO** dice `No test files found` (si lo dice, el criterio FALLA aunque el exit sea 0).
- `npx tsc --noEmit`: **0 errores**.

**Flag:** `STACKY_PROFILE_COPILOT_ENABLED` (**ON**). El panel se monta sólo si `GET /api/runtimes/profile` no devolvió `404`; con la flag OFF, `ClientProfileEditor` se renderiza **byte a byte** como hoy.
**Impacto por runtime:** el selector muestra los 3 con su ficha completa. El no disponible se muestra **deshabilitado con el motivo**, nunca oculto, y **nunca se preselecciona otro en su lugar**.
**Trabajo del operador: opt-in (default ON)** — aparece el panel; el formulario de siempre queda intacto debajo.

---

### F7 — Paridad de los 3 runtimes, la deuda del comentario, y los guardianes del arnés

**Objetivo:** dejar probado por test que ningún camino cambia de runtime solo, corregir el comentario falso de `agent_runner.py:317`, y registrar los 7 archivos de test nuevos en los DOS ratchets.
**Valor:** es la fase que impide que el plan se degrade en la próxima pasada.

**Archivos a editar:**
- `Stacky Agents/backend/agent_runner.py` — línea `:317`: reemplazar el comentario falso.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — 7 entradas nuevas (formato `"tests/test_plan296_*.py",` — ver `:1006-1013`).
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — las **MISMAS 7** entradas (formato `tests/test_plan296_*.py` sin comillas ni coma — ver `:1090-1092`).
- `Stacky Agents/backend/tests/harness_ratchet_allowlist.txt` — verificar por grep que ninguno de los 7 esté ahí; si alguno está, sacarlo.

**Corrección del comentario (`agent_runner.py:317`):**
```python
# ANTES (FALSO desde hace varias pasadas):
#   claude_code_cli: bloqueado en endpoint (HTTP 501). Nunca debería llegar aquí.
# DESPUÉS:
#   Plan 296 — los TRES runtimes de _VALID_RUNTIMES (api/agents.py:337) llegan acá.
#   claude_code_cli se despacha más abajo (:398). No hay ningún 501 en api/agents.py.
```
**Cambio de comentario únicamente: cero cambio de comportamiento.**

**Los 7 archivos a registrar en AMBOS ratchets (misma cantidad en cada uno):**
```
tests/test_plan296_flags.py
tests/test_plan296_runtime_profile.py
tests/test_plan296_completitud.py
tests/test_plan296_session.py
tests/test_plan296_propuesta.py
tests/test_plan296_apply.py
tests/test_plan296_paridad_runtimes.py
```
> El test de vitest (`clientProfileCopilotModel.test.ts`) **NO** va en estos scripts: el ratchet del arnés lista archivos `tests/*.py` de pytest.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan296_paridad_runtimes.py`

**Casos:**
1. `test_fallo_no_cambia_el_runtime_elegido` — **(K5)** se simula un fallo del runtime elegido (monkeypatch de `runtime_profile.binary_availability` a `disponible=False` para el elegido) y se corre un turno: la respuesta trae `runtime_elegido` **idéntico** al de la sesión, y `cambio_sugerido` presente **sin haber sido aplicado**.
2. `test_cambio_de_runtime_exige_bandera_explicita` — turno con otro `runtime` y sin `cambiar_runtime` ⇒ `409` y la sesión intacta.
3. `test_la_preferencia_persistida_no_cambia_ante_un_fallo` — se captura `save_run_preference` con monkeypatch; ante el fallo simulado **no se llama** con un runtime distinto.
4. `test_el_motor_conversacional_da_la_misma_pregunta_para_los_tres_runtimes` — parametrizado sobre `RUNTIMES`: mismo proyecto y mismo estado ⇒ mismo `pregunta.id`. **Es la prueba dura de la paridad determinista.**
5. `test_el_diff_es_identico_para_los_tres_runtimes` — parametrizado: mismo `confirm_token` para los 3.
6. `test_ningun_camino_llama_a_run_agent` — monkeypatch de `agent_runner.run_agent` a `raise AssertionError`; se corre la secuencia completa turn→propose→apply.
7. `test_ningun_camino_llama_a_copilot_bridge_invoke` — mismo patrón sobre `copilot_bridge.invoke`. **Ancla P3: el motor no depende de ningún LLM.**
8. `test_no_hay_ningun_501_en_api_agents` — se lee `api/agents.py` y se asserta que no aparece `501`; el mensaje del assert incluye las líneas ofensoras si aparece. Ancla la corrección del comentario.
9. `test_valid_runtimes_de_agents_coincide_con_runtimes_de_capabilities` — `api.agents._VALID_RUNTIMES == set(runtime_capabilities.RUNTIMES)`.
10. `test_los_dos_ratchets_registran_los_mismos_siete_archivos` — se leen los dos scripts, se extraen las líneas `tests/test_plan296_*.py` y se compara **el conjunto** (no el conteo); el assert imprime la diferencia simétrica.
11. `test_ningun_test_del_296_esta_en_el_allowlist` — grep sobre `harness_ratchet_allowlist.txt`; el assert nombra el archivo ofensor.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan296_paridad_runtimes.py" -q
```

**Criterio BINARIO:**
- **13 tests colectados (11 casos + 2 extra por los `parametrize` de 4 y 5 → contar la línea final de pytest), 0 failed.**
- Los 7 archivos aparecen en **ambos** scripts, verificado por:
  ```
  grep -c "test_plan296" "Stacky Agents/backend/scripts/run_harness_tests.ps1"
  grep -c "test_plan296" "Stacky Agents/backend/scripts/run_harness_tests.sh"
  ```
  Los dos deben devolver **7**.
- `grep -c "test_plan296" "Stacky Agents/backend/tests/harness_ratchet_allowlist.txt"` debe devolver **0**.

**Flag:** ninguna nueva.
**Impacto por runtime:** esta fase **es** la garantía de paridad. Los 3 runtimes quedan con el mismo motor, la misma pregunta, el mismo diff, y el candado contra el cambio automático probado.
**Trabajo del operador: ninguno.**

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| R1 | La sesión paralela toca `api/pipeline_copilot.py` o `PipelineCopilotSection.tsx` y se genera conflicto | Alta | Este plan **no escribe** en esos archivos. Todos los módulos son nuevos y hermanos. Antes de commitear: `git status` y pathspec explícito. |
| R2 | Se registra la flag OFF con `default=False` explícito y se pone en rojo `test_default_known_only_for_curated` | Media | F0 lo dice literal: la flag OFF **omite** `default=`. Test 4 de `test_plan296_flags.py` lo asserta (`spec.default is None`). |
| R3 | Se cree que `patch_client_profile_key` sirve para escribir secciones del perfil | Alta (era el supuesto de entrada) | §3.1 lo desmiente con `client_profile_keys.py:14-19`. F5 escribe por `save_client_profile`. |
| R4 | Se implementa el motor conversacional sobre `copilot_bridge.invoke` y funciona sólo con `github_copilot` | Alta | P3 lo prohíbe y el test 7 de F7 lo ancla (`invoke` monkeypatcheado a `raise`). |
| R5 | La consulta de disponibilidad usa `run_preflight.check` y miente cuando `STACKY_RUN_PREFLIGHT_GATE_ENABLED` está OFF | Media | F1 usa sólo `_get_runtime_bin` y `_binary_resolvable`. Test 2 de F1 lo verifica con la flag forzada a `False`. |
| R6 | El apply pisa cambios que el operador hizo en el formulario mientras conversaba | Media | Paso 5 del algoritmo de F5: el `confirm_token` se recalcula; si el patch quedó viejo ⇒ `409` y no se escribe. Además el `_PROFILE_WRITE_LOCK` es el **mismo** de `api/client_profile.py:320`. |
| R7 | El copiloto propone una credencial | Baja | Doble candado: F4 rechaza por `_SECRET_KEYS` antes de armar el cambio, y F5 paso 8 lo bloquea otra vez vía `validate_client_profile` (`client_profile.py:285-290`). Test 12 de F5. |
| R8 | Se escribe un `.test.tsx` con RTL y da falso verde | Media | F6 lo prohíbe explícitamente y el criterio de aceptación exige que la salida de vitest **no** diga `No test files found`. |
| R9 | Los dos ratchets divergen en cantidad | Media | Test 10 de F7 compara **conjuntos** entre los dos scripts, y el criterio pide `grep -c == 7` en ambos. |
| R10 | Un rojo de fábrica de una suite ajena se lee como "el plan rompió algo" | Alta | Ningún criterio de este plan exige verde absoluto en suites ajenas. F0 usa **delta contra línea base medida** para `test_harness_flags.py` y `test_harness_flags_help.py`. |
| R11 | El operador enciende `APPLY` y el copiloto rompe un perfil que funcionaba | Baja | El apply no escribe si el resultado no valida (paso 8), exige confirmación por sección sensible (paso 6), y queda auditado en `record_event` con los paths tocados. |

---

## 8. Fuera de scope

Explícitamente **NO** entra en este plan:

1. **Llamar a un modelo para redactar el perfil.** La capa `asistencia_llm` se **declara** en la ficha pero no se implementa. Cuando exista un seam one-shot para `codex_cli`/`claude_code_cli`, será otro plan.
2. **Configurar credenciales desde el copiloto.** Las de BD siguen por `api/client_profile.py:492`; las de tracker por su propia pantalla.
3. **Ampliar `PATCHABLE_PROFILE_KEYS`.** Se deja en las 4 keys DevOps de hoy.
4. **Un tab nuevo o una ruta nueva del frontend.** El copiloto vive dentro de `ClientProfileEditor`.
5. **Persistir la conversación entre recargas.** La sesión es stateless (P8). Lo único que persiste es la elección de runtime, por el riel existente.
6. **Cambiar `run_preflight.check` o su flag.** F1 sólo reusa dos helpers puros; el `check()` de la corrida real queda intacto.
7. **Tocar el eje pipelines (294), git (293) o GitLab (295).**
8. **Migración de perfiles existentes.** `SCHEMA_VERSION` sigue en 1; los perfiles actuales se leen y escriben igual.
9. **Sugerir el runtime automáticamente en la corrida real de un ticket.** `recomendar_runtime` es sólo del copiloto del perfil.

---

## 9. Glosario

| Término | Significado en este plan |
|---|---|
| **Ficha de runtime** | El dict de 7 campos que `runtime_profile(r)` devuelve para un runtime. |
| **Runtime** | Uno de los 3 ids de `runtime_capabilities.RUNTIMES`. Nunca "modelo", nunca `LLM_BACKEND`. |
| **`LLM_BACKEND`** | Eje **distinto** del runtime: gobierna a dónde va `copilot_bridge.invoke` (`copilot_bridge.py:157`). No confundir. |
| **Sesión** | `ProfileCopilotSession`, dataclass frozen que viaja en el request/response. No se persiste. |
| **Patch / diff** | `ProfilePatch`: lista de `CambioPropuesto` + `confirm_token`. Se ve antes de aplicarse. |
| **Sección sensible** | `tracker_state_machine`, `state_flow`, `database`. Exigen confirmación por-sección para aplicarse. |
| **Degradación visible** | Un campo con valor `"no_disponible"` + `motivo` en castellano. Nunca una ausencia muda. |
| **Fallback de capacidad** | Legítimo: el runtime elegido no puede algo, se dice y se sigue. |
| **Fallback de runtime** | **Prohibido**: cambiar de runtime solo. |
| **Causal (B)** | Justificación de flag OFF: escribe en un sistema real del operador. |

---

## 10. Orden de implementación

```
F0 (flags)
 └─> F1 (ficha de runtime, servicio puro)        ─┐
 └─> F2 (completitud + banco de preguntas)       ─┤
                                                  ├─> F3 (sesión + blueprint + 3 endpoints)
                                                  │     └─> F4 (diff + endpoint propose)
                                                  │           └─> F5 (apply, flag OFF)
                                                  │                 └─> F6 (UI)
                                                  └───────────────────────> F7 (paridad + ratchets + comentario)
```

F1 y F2 son **independientes entre sí** y pueden hacerse en cualquier orden después de F0. F7 se hace **al final**, porque sus tests 10 y 11 verifican el registro de los archivos de las fases anteriores.

**Antes de F0, medir la línea base** (obligatorio, y lo mide quien implementa, no se le cree a nadie):
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
```
Anotar `(passed, failed)` de cada uno. Los criterios de F0 son **delta contra esos números**, no verde absoluto.

---

## 11. Definition of Done

- [ ] Las 2 flags están en los 5 guardianes que les corresponden (la ON en `_CURATED_DEFAULTS_ON`, la OFF **sin** `default=`), y `test_plan296_flags.py` da 9/9.
- [ ] `runtime_profile(r)` devuelve las **7** claves de `FICHA_CAMPOS` para los 3 runtimes (**K1: 2/7 → 7/7**).
- [ ] La disponibilidad se consulta **sin ticket, sin corrida y sin depender de `STACKY_RUN_PREFLIGHT_GATE_ENABLED`** (**K2**).
- [ ] Una sección ya completa **no** genera pregunta (**K4**).
- [ ] Una sesión que arranca de `{}` termina con las 3 secciones requeridas y `validate_client_profile(...).ok is True` (**K3**).
- [ ] Ante fallo del runtime elegido, `runtime_elegido` queda **intacto** y `cambio_sugerido` aparece **sin aplicarse** (**K5**).
- [ ] Cambiar de runtime exige `cambiar_runtime: true`; sin eso, `409` y sesión intacta.
- [ ] Ningún camino del plan llama a `agent_runner.run_agent` ni a `copilot_bridge.invoke` (tests 6 y 7 de F7).
- [ ] El copiloto nunca propone ni escribe una clave de `_SECRET_KEYS` (doble candado F4+F5).
- [ ] Con `STACKY_PROFILE_COPILOT_APPLY_ENABLED` OFF, ninguna ruta escribe el perfil; el botón se muestra **deshabilitado con motivo**, no oculto.
- [ ] Con `STACKY_PROFILE_COPILOT_ENABLED` OFF, los endpoints dan `404` y `ClientProfileEditor` se renderiza como hoy.
- [ ] `npx tsc --noEmit` en `Stacky Agents/frontend`: **0 errores**.
- [ ] `npx vitest run src/components/__tests__/clientProfileCopilotModel.test.ts`: **13 passed** y la salida **no** dice `No test files found`.
- [ ] Los 7 archivos de test nuevos están en **ambos** ratchets (`grep -c "test_plan296"` = **7** en el `.ps1` y en el `.sh`) y en **ninguno** del allowlist (**0**).
- [ ] El comentario de `agent_runner.py:317` ya no afirma que `claude_code_cli` está bloqueado, y `test_no_hay_ningun_501_en_api_agents` lo ancla.
- [ ] `test_harness_flags.py` y `test_harness_flags_help.py`: `failed` **≤** la línea base medida antes de F0.
- [ ] Los 7 archivos de test del 296 corren **por archivo** con `Stacky Agents/backend/.venv/Scripts/python.exe` y dan 0 failed cada uno.

---

## Anexo A — Los 7 requisitos del operador, y dónde los cumple el plan

| # | Requisito textual | Fase | Símbolo / campo |
|---|---|---|---|
| 1 | si está disponible y correctamente configurado | F1 | `disponible` + `disponibilidad_detalle` + `disponibilidad_motivo` |
| 2 | para qué tipo de tarea se recomienda | F1 | `recomendado_para` (`RECOMENDADO_PARA`) |
| 3 | qué capacidades utilizará | F1 | `capacidades` (las 11 de `capabilities_for` + `exige_agente_vscode` + `asistencia_llm`) |
| 4 | qué permisos o credenciales necesita | F1 | `credenciales` (`CREDENCIALES`) — **nombres, nunca valores** |
| 5 | si trabajará localmente o mediante integración externa | F1 | `ejecucion` (`EJECUCION`) |
| 6 | qué ocurrirá si la ejecución falla | F1 | `si_falla` (`SI_FALLA`) |
| 7 | cómo cambiar de runtime antes de ejecutar una acción | F1 + F3 | `como_cambiar` + `elegir_runtime(..., explicito=True)` + `puedeElegirRuntime` |

## Anexo B — Las 12 conductas del copiloto, y dónde viven

| Conducta pedida | Fase | Cómo |
|---|---|---|
| detectar qué información ya está disponible | F2 | `estado_perfil().secciones_presentes` |
| evitar preguntas repetidas | F2 | `preguntas_pendientes` excluye secciones presentes + `ya_respondidas` |
| identificar datos faltantes | F2 | `secciones_faltantes_requeridas` / `_opcionales` |
| identificar inconsistencias | F2 | `inconsistencias` desde `validate_client_profile` |
| adaptar preguntas según tipo de cliente/proyecto | F2 | banco por `tracker_type` + `estados_validos` / `tipos_work_item` |
| recomendar explicando cada decisión | F2 + F4 | `Pregunta.motivo` y `CambioPropuesto.motivo` |
| completar automáticamente campos | F4 | `complete_client_profile` + `get_default_client_profile` como propuesta |
| revisar, corregir o confirmar cada cambio importante | F4 + F5 | `sensible=True` ⇒ `confirmaciones_sensibles` obligatorias |
| aprovechar lo existente antes de pedir a mano | F2 | `load_effective_client_profile` + `autodetect_process_catalog` |
| mostrar progreso y nivel de completitud | F2 + F6 | `completitud()` + `progresoTexto` |
| resumen de lo configurado, pendiente y recomendado | F3 | payload del turno: `completitud` + `pregunta` + `cambio_sugerido` |
| informar los cambios ANTES de aplicarlos | F4 | `ProfilePatch` + `validacion_previa` |
| confirmación explícita antes de guardar lo sensible | F5 | pasos 5 y 6 del algoritmo |
| **EJECUTAR**, no sólo recopilar | F5 | `save_client_profile` tras validar, con auditoría |
