# Plan 110 — Revisor de PRs con Claude Haiku (solo-lectura) y con Modelo Local

- **Estado:** PROPUESTO v2 — 2026-07-09 (juez adversarial: APROBADO-CON-CAMBIOS)
- **Enmienda v1→v1.1 (operador, 2026-07-09):** la flag maestra `STACKY_PR_REVIEWER_ENABLED` pasa de **default OFF → default ON** por decisión explícita del operador ("deben ser siempre default on"). Es una excepción consciente al patrón "opt-in default OFF" de las flags devops previas. Cambios acoplados: `config.py` fallback `"true"`; `FlagSpec` con `default=True`; alta en `_CURATED_DEFAULTS_ON` (única vía canónica sin romper los meta-tests de defaults); KPI-1, guardarraíl 2, DoD y Riesgo #1 reformulados; nuevo test `test_reviewer_default_on`. El gate sigue siendo reversible con un click. **Advertencia de privacidad reforzada** (Riesgo #1): con el revisor activo por default, el camino que puede enviar el diff a un servicio externo (Haiku) queda a un click sin opt-in explícito → el aviso de la UI es obligatorio.
- **CHANGELOG v1.1 → v2 (juez adversarial StackyArchitectaUltraEficientCode, perfil normal heredado de Opus 4.8):**
  - **C1 [privacidad/PII, IMPORTANTE]:** el saneo ahora redacta también **PII básica (email)** además de secretos técnicos; y el camino **Haiku (externo)** exige un **preview del payload EXACTO que sale de la máquina + confirmación** antes de enviar (reusa `/detail`, human-in-the-loop; compensa el default ON sin revertirlo). Ver §3 guardarraíl 7, F3 (módulo saneo), F7, §6 Riesgo #1. **[ADICIÓN ARQUITECTO]**
  - **C2 [flag fantasma, IMPORTANTE]:** `STACKY_PR_REVIEW_TIMEOUT_SEC` deja de ser decorativa: se **cablea de verdad** agregando un kwarg opcional `timeout` (default 120, backward-compatible) a `_invoke_copilot` (hoy `timeout=120` hardcodeado en `copilot_bridge.py:664`) y pasándolo desde `invoke_haiku`. Ver F4.
  - **C3 [contradicción §2.2 vs F7, IMPORTANTE]:** se agrega endpoint mínimo **`GET /api/pr-review/models`** (gateado) que llama a `list_copilot_models` (independiente de `LLM_BACKEND`, como `invoke_haiku`; el de `pm.py` sólo sirve Copilot si `LLM_BACKEND=="copilot"` y el default es `vscode_bridge`); §2.2 (b) y F7 quedan consistentes. Ver F4bis.
  - **C4 [`provider.name`, DESCARTADO]:** verificado que GitLab (`name="gitlab"`, `gitlab_provider.py:31`) y ADO (`name="azure_devops"`, `ado_provider.py:32`) exponen el atributo — sin cambios.
  - **C5 [helpers de path, DESCARTADO]:** verificado que `_project_path()`, `_base_proj` y `_resolve_repo_id` existen y son usados por los métodos hermanos (`create/get/merge_merge_request`); el código nuevo los espeja. Refinamiento MENOR aplicado: GitLab `list_merge_requests` usa `params=` en vez de query embebida en el path. Ver F1.
  - **C6 [ratchet, MENOR]:** los tests del ratchet se listan en **orden alfabético real** en F8.
  - **C7 [drift de nombres de test, MENOR]:** el mapa KPI→test (§5) y §1.3 usan los nombres EXACTOS de los tests declarados en cada fase.
- **Autor:** StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8) + enmienda del orquestador + juez adversarial v2
- **Serie:** DevOps (sección nueva del panel, hereda contrato de extensión §3.12 del Plan 87)
- **Depende de:** Plan 87 (panel DevOps + `DEVOPS_SECTIONS`), Plan 95 (`MergeRequestProvider` + `devops_production`), Plan 106 (`invoke_local_llm` + `api/local_llm_analysis.py`)
- **Flag maestra:** `STACKY_PR_REVIEWER_ENABLED` (**default ON** — decisión explícita del operador 2026-07-09; editable 100% desde el panel del Arnés, categoría `devops`). Ver §3 guardarraíl 2 para la implicación (la sección aparece out-of-the-box porque su master `STACKY_DEVOPS_PANEL_ENABLED` también es default ON, `config.py:873`).

---

## 1. Título, objetivo, KPIs

### 1.1 Pedido textual del operador (transcrito literal)

> "NECESITO QUE HAGAS UN DASHBOARD DE ESTO: Hacer una sección de revisor de PRs donde te cargue todas las PR y te permita revisar las PRs con un claude haiku EXCLUSIVAMENTE pero que sea extremadamente seguro y solo haga lo que se le pide, como por ejemplo que la revise, dé un resumen de lo que piensa y luego te recomiende ejecutar alguna opción y que sea fácil con un botón ejecutar la acción y listo. Y QUE TAMBIÉN TENGA LA POSIBILIDAD DE REVISARLO CON LOS MODELOS LOCALES QUE TENGO pero que le dé toda la información necesaria en un solo prompt para hacer pregunta-respuesta."

### 1.2 Objetivo (1 párrafo)

Agregar al panel DevOps una sección **"Revisor de PRs"** que: (a) lista TODAS las Pull/Merge Requests del tracker del proyecto activo (GitLab o Azure DevOps); (b) permite pedir una **revisión solo-lectura con Claude Haiku EXCLUSIVAMENTE**, que devuelve un resumen + hallazgos + **una acción recomendada** de un conjunto CERRADO y seguro, sin ejecutar jamás nada por su cuenta; (c) permite ejecutar esa acción con **un solo botón "Ejecutar"** que aprieta el humano (human-in-the-loop), con confirmación fuerte para operaciones destructivas como el merge; y (d) permite alternativamente revisar la PR con el **modelo local** (Ollama/LM Studio/vLLM, Plan 106) armando **un único prompt autocontenido** con toda la información de la PR para pregunta-respuesta en una sola pasada.

### 1.3 KPIs (todos binarios y verificables por test)

- **KPI-1 (ON por default + gate reversible):** la flag `STACKY_PR_REVIEWER_ENABLED` nace en **ON** (default del operador), por lo que la sección está disponible out-of-the-box (sujeta a que su master `STACKY_DEVOPS_PANEL_ENABLED` esté ON — lo está por default). El gate sigue siendo **reversible desde la UI**: si el operador la apaga (`STACKY_PR_REVIEWER_ENABLED=false`), `GET /api/pr-review/list`, `POST /api/pr-review/review/haiku`, `POST /api/pr-review/review/local` y `POST /api/pr-review/execute` devuelven **404** y la sub-tab muestra el banner de activación. Verifica el default: `test_plan110_pr_review_flags.py::test_reviewer_default_on`; verifica el gate reversible: el `test_*_404_when_flag_off` de cada archivo de endpoint (`test_plan110_pr_review_list_endpoint.py::test_list_404_when_flag_off`, `test_plan110_pr_review_detail_diff.py::test_detail_404_when_flag_off`, `test_plan110_pr_review_haiku.py::test_review_haiku_404_when_flag_off`, `test_plan110_pr_review_local.py::test_review_local_404_when_reviewer_flag_off`, `test_plan110_pr_review_execute.py::test_execute_404_when_flag_off`).
- **KPI-2 (listado real, nunca 500):** `GET /api/pr-review/list?project=X` con flag ON devuelve la lista normalizada de PRs abiertas del tracker activo; con el tracker caído devuelve error descriptivo con hint (status 400/502), **nunca 500**. Verifica: `test_plan110_pr_review_list_endpoint.py`.
- **KPI-3 (Haiku EXCLUSIVAMENTE + sin tools):** la revisión Haiku resuelve el modelo desde `STACKY_PR_REVIEW_HAIKU_MODEL` y **rechaza (400)** si el id no contiene `"haiku"`; la invocación es una completion de chat pura (sin herramientas). Verifica: `test_plan110_pr_review_haiku.py::test_rejects_non_haiku_model` y `::test_haiku_review_is_toolless_chat`.
- **KPI-4 (un solo prompt local para Q&A):** la revisión local arma UN único prompt autocontenido (título, descripción, ramas, estado de pipeline, diff saneado, pregunta opcional) y responde vía `invoke_local_llm`. Verifica: `test_plan110_pr_review_local.py::test_local_review_single_self_contained_prompt`.
- **KPI-5 (saneo + no fuga de datos):** el diff se trunca a `STACKY_PR_REVIEW_DIFF_MAX_CHARS`, se redactan secretos evidentes, y el diff crudo **nunca** se persiste en `AgentExecution.input_context_json`. Verifica: `test_plan110_pr_review_detail_diff.py::test_sanitize_diff_redacts_then_truncates` (+ `::test_redacts_email_pii`, C1) y `test_plan110_pr_review_haiku.py::test_execution_row_never_stores_raw_diff`.
- **KPI-6 (HITL fuerte en merge):** `POST /api/pr-review/execute` con `action="merge"` exige `confirm=true` **Y** `confirm_merge=true`; faltando cualquiera → **400** y **no** llama a `merge_merge_request`. Verifica: `test_plan110_pr_review_execute.py::test_merge_requires_double_confirm`.
- **KPI-7 (config 100% por UI + ayuda llana):** las 4 flags nuevas están en categoría `devops`, son editables por el panel del Arnés y tienen ayuda en lenguaje llano sin jerga. Verifica: `test_harness_flags_help.py::test_plain_help_covers_all_registry_keys` y `::test_plain_help_avoids_jargon_denylist` (ya existentes, deben seguir verdes).
- **KPI-8 (extensibilidad + tsc):** sumar la sección = **1 entrada** en `DEVOPS_SECTIONS` + **1 componente** nuevo + **1 objeto** en `endpoints.ts`, cero cambios en otras secciones; `npx tsc --noEmit` = 0 errores. Verifica: F7 (vitest + tsc).

---

## 2. Por qué ahora / gap que cierra

El Plan 95 dio a Stacky la infraestructura MR/PR pero **solo para crear/consultar/mergear** una PR puntual (flujo "llevar a producción"). No existe forma de **listar** las PRs abiertas ni de **revisarlas con IA**. El Plan 106 dejó listo el motor de modelo local (`invoke_local_llm`) y el patrón de endpoints IA solo-lectura con HITL. Este plan une ambos: reusa el puerto MR/PR (agregándole `list_merge_requests` y `get_merge_request_diff`), reusa el patrón de `api/local_llm_analysis.py` para el modelo local, y agrega un camino Haiku solo-lectura runtime-agnóstico.

### 2.1 Tabla de hechos verificados (archivo:línea, rama `codex/subida-cambios-pendientes`, 2026-07-09)

| # | Hecho verificado | Evidencia (archivo:línea) |
|---|---|---|
| H1 | `MergeRequestProvider` Protocol tiene SOLO `create_merge_request`/`get_merge_request`/`merge_merge_request`. **No hay `list_merge_requests` ni `get_merge_request_diff`.** | `backend/services/merge_request_provider.py:7,25,33,41` |
| H2 | Fábrica `get_merge_request_provider(project)` resuelve el writer activo vía `get_repo_writer` y valida `isinstance(..., MergeRequestProvider)`. | `backend/services/merge_request_provider.py:44-56` |
| H3 | GitLab: `get_merge_request` (GET `/projects/:id/merge_requests/:iid`, normaliza `opened→open`) en :649; `merge_merge_request` (PUT `.../merge`) en :690; `create_merge_request` en :624. | `backend/services/gitlab_provider.py:624,649,690` |
| H4 | GitLab `post_comment` apunta a **issues** (`/projects/:id/issues/:iid/notes`), **NO** a MRs. Para comentar una MR hace falta un método nuevo (`/merge_requests/:iid/notes`). | `backend/services/gitlab_provider.py:295-303` |
| H5 | ADO: `get_merge_request` (GET `.../pullrequests/:id` + builds) en :301; `merge_merge_request` (PATCH `status=completed`) en :362; `create_merge_request` en :270. | `backend/services/ado_provider.py:270,301,362` |
| H6 | ADO `post_comment` apunta a work items (`self._client.post_comment(int(item_id), ...)`), **NO** a PRs. Para comentar un PR hace falta un método nuevo (`/pullrequests/:id/threads`). | `backend/services/ado_provider.py:92-93` |
| H7 | `invoke_local_llm(*, agent_type, system, user, on_log, execution_id=None, model=None)` va SIEMPRE al servidor local ignorando `LLM_BACKEND`; error accionable si no responde. | `backend/copilot_bridge.py:190-260` |
| H8 | Patrón de endpoints IA solo-lectura: blueprint `bp` con `url_prefix="/llm"`, `_guard()` (404 si flag OFF, 400 si POST sin JSON), `_HITL_RULES`, ticket interno `ado_id=-5`, `_ensure_internal_ticket`/`_create_execution`/`_finish_execution`. | `backend/api/local_llm_analysis.py:24,30,44,55,84,102` |
| H9 | `copilot_bridge.invoke()` despacha por `LLM_BACKEND` a `_invoke_copilot` (HTTP OpenAI-compatible) o `_invoke_claude_cli` (CLI `claude -p` one-shot). Ambos aceptan `model`. | `backend/copilot_bridge.py:145,172-179,603,780` |
| H10 | `_invoke_copilot` es una completion de chat pura (HTTP), sin herramientas; toma el token vía `_get_copilot_token()`. | `backend/copilot_bridge.py:603-621` |
| H11 | Ya existe el clamp que trata "haiku" como caso especial: `m = model_id.lower(); if "haiku" in m: ...`. Reusamos ese criterio de detección. | `backend/api/agents.py:544,554-556` |
| H12 | Health del panel se arma en `_health_payload()` (dict de keys aditivas) y `GET /devops/health` SIEMPRE 200. | `backend/api/devops.py:28-62,65-68` |
| H13 | `devops_production` (Plan 95) ya implementa el merge con HITL: `_guard()` (404 si flag OFF), `_call_provider` (HTTPException se re-lanza, nunca cae al 500 genérico), `merge_mr` exige `confirm is True`. | `backend/api/devops_production.py:12-34,97-113` |
| H14 | Contrato de extensión del panel: agregar sección = 1 entrada en `DEVOPS_SECTIONS` + 1 componente + 1 health key; gate declarativo con `FlagGateBanner`. | `frontend/src/pages/DevOpsPage.tsx:48-57,77-139,238-263` |
| H15 | `FlagGateBanner` reusa `HarnessFlags.update({[flagKey]: true})` para activar la flag desde la UI con un click. | `frontend/src/components/devops/FlagGateBanner.tsx:21-50` |
| H16 | Registro de blueprints: todos los `devops_*` se registran en `api/__init__.py` con `url_prefix` sin `/api`. | `backend/api/__init__.py:98-106` |
| H17 | `FlagSpec` real: `key,type∈{bool,int,str,csv},label,description,group∈{claude_code_cli,global,...},requires,default,min_value,max_value,env_only,pair,restart_required`. Devops flags usan `group="global"`, `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`. | `backend/services/harness_flags.py:2028-2043` |
| H18 | Gotcha default: NO poner `default=` explícito en flags nuevas (el default efectivo vive en `config.py`); solo bools curados en `_CURATED_DEFAULTS_ON` pueden llevar `default=`. | `backend/services/harness_flags.py:2345-2372` (LOCAL_LLM_* sin `default=`) |
| H19 | Gotcha R4 profundidad-1: `requires` debe apuntar a un master SIN `requires` propio. Todas las devops apuntan a `STACKY_DEVOPS_PANEL_ENABLED`; encadenar a una flag que ya tiene `requires` rompe el test (precedente Plan 104). | `backend/tests/test_harness_flags_requires.py:129-147,138-142` |
| H20 | Ayuda llana: `PLAIN_HELP[key] = PlainHelp(what, on_effect, off_effect, example)`; denylist prohíbe MCP/LLM/prompt/token/endpoint/backend/frontend/etc., keys SCREAMING_SNAKE y "F\d". | `backend/services/harness_flags_help.py:17-25`, `backend/tests/test_harness_flags_help.py:17-23` |
| H21 | Ratchet de tests: todo test backend nuevo se agrega a `HARNESS_TEST_FILES` en `run_harness_tests.sh` y `.ps1`. | `backend/scripts/run_harness_tests.sh:20,180` |
| H22 | Cliente API frontend: objetos `XxxApi` con `api.get/post` en `endpoints.ts` (`DevOps`, `DevOpsProduction`, `DevOpsServers`). | `frontend/src/api/endpoints.ts:3074,3223,3324` |
| H23 | `LLM_BACKEND` default = `"vscode_bridge"`; flags `LOCAL_LLM_ENABLED/ENDPOINT/MODEL/TIMEOUT_SEC` ya existen en `config.py`. | `backend/config.py:75,81-88` |
| H24 | venv de tests: `Stacky Agents/backend/.venv/Scripts/python.exe` (verificado existente; NO `backend/venv`). | filesystem 2026-07-09 |

### 2.2 Decisión de arquitectura del camino Haiku (con justificación de evidencia)

**Decisión:** la revisión Haiku se hace con un **endpoint backend HTTP** que invoca una función nueva `copilot_bridge.invoke_haiku(...)`, la cual **fuerza el engine Copilot** (`_invoke_copilot`, H10) ignorando `LLM_BACKEND` — exactamente como `invoke_local_llm` fuerza el engine local ignorando `LLM_BACKEND` (H7). El modelo se resuelve desde la flag `STACKY_PR_REVIEW_HAIKU_MODEL` y se **valida server-side** que su id contenga `"haiku"` (criterio de H11); si no, 400.

**Por qué este camino y no `agent_runner.run_agent(model_override=...)`:** el runner de agente spawnea un binario de runtime con herramientas (Read/Bash/Edit); eso contradice "extremadamente seguro / solo-lectura". Una **completion de chat HTTP no tiene superficie de herramientas**: el modelo devuelve texto y es estructuralmente incapaz de ejecutar, editar o mergear nada. Esa es la garantía de seguridad más fuerte posible y además es runtime-agnóstica (no depende de cuál runtime —Codex/Claude Code/Copilot— esté activo).

**Por qué el engine Copilot y no `_invoke_claude_cli`:** `_invoke_claude_cli` (H9) usa `claude -p --dangerously-skip-permissions`, que en modo print habilita herramientas por defecto (superficie de ejecución) y spawnea un subproceso difícil de mockear. El engine Copilot HTTP es solo-texto, mockeable de forma trivial (`requests.post`) para TDD, y no spawnea nada. **Alternativa explícitamente descartada:** `_invoke_claude_cli` — motivo: superficie de herramientas + subproceso.

**SUPUESTO EXPLÍCITO (a validar por el operador, no inventado):** el catálogo de modelos que expone el token de Copilot/GitHub Models incluye un id de Claude Haiku (p. ej. `claude-3.5-haiku`). Mitigación: (a) el id es una flag editable por UI; (b) el panel ofrece un botón "Ver modelos disponibles" que llama a `list_copilot_models` (H9, `copilot_bridge.py:65`) **a través del endpoint gateado `GET /api/pr-review/models` (F4bis, C3)** para que el operador elija el id exacto; (c) si el modelo no existe o el token no está, el endpoint devuelve **502 con hint accionable**, nunca 500. Si el entorno del operador no tiene un Haiku en Copilot, la revisión Haiku degrada de forma controlada (mensaje claro) y el camino de modelo local sigue funcionando.

---

## 3. Principios y guardarraíles (no negociables)

1. **Paridad de 3 runtimes con degradación explícita.** La revisión Haiku y la local son endpoints HTTP backend (`invoke_haiku` / `invoke_local_llm`) que NO dependen del runtime del agente activo → funcionan idénticamente con Codex CLI, Claude Code CLI y GitHub Copilot Pro. Fallback: si el engine Copilot no tiene token/modelo Haiku → 502 con hint; si el servidor local no responde → 502 con hint (reusa los errores de `invoke_local_llm`).
2. **Cero trabajo extra para el operador — default ON (decisión explícita del operador).** `STACKY_PR_REVIEWER_ENABLED` nace en **ON**: el operador NO tiene que activar nada, la sección aparece disponible out-of-the-box dentro del panel DevOps. Esto es una excepción consciente al patrón "opt-in default OFF" de las flags devops previas (planes 93-107, todas OFF): la pidió el operador. **Implicación de compatibilidad:** en un deploy con el panel DevOps ON (default, `config.py:873`), al actualizar aparece la sub-tab "Revisor de PRs" sin intervención — NO es byte-idéntico al comportamiento previo (aparece una capacidad nueva), pero es aditivo y no altera ninguna sección existente. El gate sigue siendo **reversible con un click** desde `FlagGateBanner`/`HarnessFlagsPanel`: apagar la flag ⇒ 404 en los endpoints + sub-tab sin contenido, restaurando el comportamiento anterior. **Ver §6 Riesgo #1:** el default ON expone el camino de revisión (que puede enviar el diff a un servicio externo) sin un opt-in explícito — el aviso de privacidad de la UI (guardarraíl 7) es por eso obligatorio y siempre visible.
3. **Config 100% desde la UI del Arnés.** Las 4 flags nuevas (`STACKY_PR_REVIEWER_ENABLED`, `STACKY_PR_REVIEW_HAIKU_MODEL`, `STACKY_PR_REVIEW_DIFF_MAX_CHARS`, `STACKY_PR_REVIEW_TIMEOUT_SEC`) son `env_only=False` (categoría `devops`), editables desde `HarnessFlagsPanel`. Nada requiere tocar `.env` a mano.
4. **Human-in-the-loop innegociable.** El modelo SOLO propone (endpoint de review = solo-lectura, sin tools). El botón "Ejecutar" lo aprieta el humano y dispara `POST /api/pr-review/execute`. Ninguna ruta de review llama a `execute`. Merge = HITL fuerte: checkbox literal (`confirm_merge=true`) + `confirm=true` server-side, espejando la asimetría del Plan 95 (H13).
5. **Mono-operador sin auth real.** Nada de RBAC/roles. Se reusan los patrones `current_user` sin validar existentes.
6. **Nunca 500.** Todos los endpoints reusan el patrón `_call_provider` de `devops_production` (H13): `TrackerConfigError→400`, `TrackerApiError→status`, `HTTPException` se re-lanza, `Exception→500` solo como último recurso con mensaje genérico (no vuelca stack ni secretos). Timeout configurable (`STACKY_PR_REVIEW_TIMEOUT_SEC` para Haiku; `LOCAL_LLM_TIMEOUT_SEC` para el local).
7. **Seguridad de datos personales/secretos en el diff (riesgo real).** El diff de una PR puede contener secretos o datos personales. Medidas obligatorias: (a) **truncado** a `STACKY_PR_REVIEW_DIFF_MAX_CHARS`; (b) **redacción** de secretos evidentes **y de PII básica (email)** antes de enviar al modelo (C1); (c) **advertencia explícita en la UI** de que el diff se envía al modelo (local = queda en la máquina del operador; Haiku = viaja al backend de Copilot/GitHub); (c-bis) **[ADICIÓN ARQUITECTO / C1] preview obligatorio del payload EXACTO que sale de la máquina en el camino Haiku (externo):** antes de llamar a `/review/haiku`, la UI muestra el diff SANEADO (el mismo que devuelve `/detail`) y exige una confirmación explícita del operador — así el default ON no envía nada a un tercero sin que el humano vea qué sale (human-in-the-loop, sin trabajo recurrente); (d) el diff crudo **NUNCA** se persiste en `AgentExecution.input_context_json` (solo se guardan metadatos: mr_id, conteo de chars, flag truncated) ni se loguea en claro. Ver §6 Riesgos.
8. **Reusar, no reinventar.** Se reusan: `get_merge_request_provider` (H2), el patrón de `local_llm_analysis.py` (H8), `_call_provider` (H13), `DEVOPS_SECTIONS`/`FlagGateBanner` (H14/H15), `invoke_local_llm` (H7), el clamp haiku (H11).

---

## 4. Fases F0..F8

> **Comando de test backend (todas las fases):** desde el directorio `Stacky Agents/backend`,
> `".venv/Scripts/python.exe" -m pytest tests/<archivo>.py -q`
> (correr **por archivo**; el venv verificado es `.venv`, H24). Los ejemplos de comando abajo usan rutas relativas a `Stacky Agents/backend`.
>
> **Regla TDD dura:** escribir el test primero, verlo fallar por la razón correcta, luego implementar hasta verde. No pasar a la fase siguiente con la anterior en rojo.

---

### F0 — Flags, config y ayuda llana (base de todo lo demás)

**Objetivo (1 frase):** declarar y hacer editables por UI las 4 flags que gobiernan la sección, con default seguro (OFF) y ayuda en lenguaje llano.

**Valor:** sin esto, nada es configurable desde el Arnés (rompe el guardarraíl 3) ni se puede gatear (rompe el guardarraíl 2).

**Archivos a editar:**
- `backend/config.py` — agregar 4 atributos (bloque cerca de las `LOCAL_LLM_*`, H23):
  ```python
  # ── Plan 110 — Revisor de PRs (Haiku solo-lectura + modelo local) ──────────
  # DEFAULT ON (decisión explícita del operador 2026-07-09): el fallback del getenv es "true".
  STACKY_PR_REVIEWER_ENABLED = os.getenv("STACKY_PR_REVIEWER_ENABLED", "true").lower() in ("1", "true", "yes", "on")
  # SUPUESTO: id del modelo Haiku en el catálogo de Copilot/GitHub Models. El operador
  # lo confirma con "Ver modelos disponibles" en el panel. Ver §2.2.
  STACKY_PR_REVIEW_HAIKU_MODEL = os.getenv("STACKY_PR_REVIEW_HAIKU_MODEL", "claude-3.5-haiku")
  STACKY_PR_REVIEW_DIFF_MAX_CHARS = int(os.getenv("STACKY_PR_REVIEW_DIFF_MAX_CHARS", "60000"))
  STACKY_PR_REVIEW_TIMEOUT_SEC = int(os.getenv("STACKY_PR_REVIEW_TIMEOUT_SEC", "120"))
  ```
- `backend/services/harness_flags.py`:
  1. En `_CATEGORY_KEYS["devops"]` (tupla que empieza en `harness_flags.py:177`) agregar las 4 keys nuevas:
     ```python
     "STACKY_PR_REVIEWER_ENABLED",       # Plan 110 — revisor de PRs
     "STACKY_PR_REVIEW_HAIKU_MODEL",     # Plan 110 — modelo Haiku para la revisión
     "STACKY_PR_REVIEW_DIFF_MAX_CHARS",  # Plan 110 — tope de tamaño del diff
     "STACKY_PR_REVIEW_TIMEOUT_SEC",     # Plan 110 — timeout de la revisión Haiku
     ```
  2. En `FLAG_REGISTRY` agregar 4 `FlagSpec` (mismo patrón que H17; **SIN `default=`**, H18):
     ```python
     # ── Plan 110 — Revisor de PRs ──────────────────────────────────────────────
     FlagSpec(
         key="STACKY_PR_REVIEWER_ENABLED",
         type="bool",
         label="Revisor de PRs (Plan 110)",
         description=(
             "Plan 110 — Sección 'Revisor de PRs' del panel DevOps: lista las PRs "
             "abiertas del tracker activo y permite revisarlas con Claude Haiku "
             "(solo-lectura, recomienda una acción) o con el modelo local. "
             "Default ON: la sección aparece; apagala si /api/pr-review/* debe dar 404."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # H19: master sin requires propio
         default=True,  # DEFAULT ON (operador). OBLIGATORIO agregar la key a
                        # _CURATED_DEFAULTS_ON en tests/test_harness_flags.py (ver abajo):
                        # es la ÚNICA vía canónica de promover un default a ON sin romper
                        # test_default_known_only_for_curated / test_declared_default_true_set.
     ),
     FlagSpec(
         key="STACKY_PR_REVIEW_HAIKU_MODEL",
         type="str",
         label="Modelo Haiku para revisar PRs",
         description=(
             "Plan 110 — Id del modelo Claude Haiku que usa la revisión de PRs "
             "(se valida que contenga 'haiku'). Elegilo con 'Ver modelos "
             "disponibles' en la sección. Default: claude-3.5-haiku."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # H19: NO encadenar a STACKY_PR_REVIEWER_ENABLED
     ),
     FlagSpec(
         key="STACKY_PR_REVIEW_DIFF_MAX_CHARS",
         type="int",
         label="Tope de tamaño del diff (caracteres)",
         description=(
             "Plan 110 — Máximo de caracteres del diff que se le manda al modelo. "
             "Diffs más grandes se truncan (protege privacidad y velocidad). "
             "Default 60000."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",
         min_value=1000,
         max_value=500000,
     ),
     FlagSpec(
         key="STACKY_PR_REVIEW_TIMEOUT_SEC",
         type="int",
         label="Timeout de la revisión Haiku (segundos)",
         description=(
             "Plan 110 — Tiempo máximo de espera por la respuesta de Haiku. "
             "Default 120."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",
         min_value=10,
         max_value=600,
     ),
     ```
- `backend/services/harness_flags_help.py` — agregar 4 entradas a `PLAIN_HELP` (H20). **Prohibido** usar: `LLM`, `prompt`, `token`, `endpoint`, `backend`, `frontend`, `gate`, `hook`, `runtime`, `MCP`, keys en mayúsculas, o "F1/F2..." (denylist H20). Ejemplo para la maestra:
  ```python
  "STACKY_PR_REVIEWER_ENABLED": PlainHelp(
      what="Una sección para revisar los pedidos de cambios (PRs) de tu repositorio con ayuda de un asistente que solo mira y opina.",
      on_effect="Si la activás: aparece la sección 'Revisor de PRs' con la lista de PRs abiertas y botones para pedir una revisión.",
      off_effect="Si la apagás: la sección no aparece y el revisor queda desactivado.",
      example="Como tener un colega que lee el cambio y te deja un resumen, pero vos decidís qué hacer.",
  ),
  ```
  (Redactar las otras 3 con el mismo estilo, sin jerga.)
- `backend/tests/test_harness_flags_requires.py` — agregar al `_REQUIRES_MAP_FROZEN` (H19) las 4 aristas → todas a `"STACKY_DEVOPS_PANEL_ENABLED"`:
  ```python
  "STACKY_PR_REVIEWER_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",       # Plan 110
  "STACKY_PR_REVIEW_HAIKU_MODEL": "STACKY_DEVOPS_PANEL_ENABLED",     # Plan 110
  "STACKY_PR_REVIEW_DIFF_MAX_CHARS": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 110
  "STACKY_PR_REVIEW_TIMEOUT_SEC": "STACKY_DEVOPS_PANEL_ENABLED",     # Plan 110
  ```
- `backend/tests/test_harness_flags.py` — **(OBLIGATORIO por el default ON)** agregar la key **solo del master bool** al set `_CURATED_DEFAULTS_ON` (definido ~línea 465; es la lista curada de defaults ON — su comentario dice que agregar una key acá es la vía canónica para promover un default, "nunca se toca el meta-test"):
  ```python
  "STACKY_PR_REVIEWER_ENABLED",  # Plan 110 — default ON pedido por el operador
  ```
  > **Importante (H18 revisado con evidencia):** `default_is_known(spec)` es `spec.default is not None` (`harness_flags.py:2404-2406`) y el meta-test `test_default_known_only_for_curated` (`test_harness_flags.py:593-599`) exige `{keys con default explícito} == _CURATED_DEFAULTS_ON`; además `test_declared_default_true_set` (`:582-590`) exige que TODA key del set tenga `declared_default is True`. Por eso: (a) el master lleva `default=True` **y** entra al set; (b) las 3 flags **str/int** (`_HAIKU_MODEL`, `_DIFF_MAX_CHARS`, `_TIMEOUT_SEC`) van **SIN `default=`** y **NO** entran al set (su "default" es un valor, no un ON/OFF; su default efectivo vive en `config.py`). Meter una str en el set rompería `test_declared_default_true_set`.

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_flags.py`):**
- `test_flags_registered_and_categorized`: las 4 keys están en `FLAG_REGISTRY` y en `_CATEGORY_KEYS["devops"]`.
- `test_flags_editable_by_ui`: las 4 tienen `env_only == False`.
- `test_reviewer_default_on`: **default ON** — con entorno limpio, `config.STACKY_PR_REVIEWER_ENABLED is True`; la `FlagSpec` del master tiene `default is True`; y `"STACKY_PR_REVIEWER_ENABLED" in _CURATED_DEFAULTS_ON` (import desde `tests.test_harness_flags`). (Este test es el candado del pedido del operador.)
- `test_subconfig_flags_no_explicit_default`: las 3 flags **str/int** (`_HAIKU_MODEL`, `_DIFF_MAX_CHARS`, `_TIMEOUT_SEC`) traen `default is None` en su `FlagSpec` (su default efectivo vive en `config.py`); NO están en `_CURATED_DEFAULTS_ON`.
- `test_requires_all_point_to_panel_master`: las 4 tienen `requires == "STACKY_DEVOPS_PANEL_ENABLED"`.

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_harness_flags_help.py -q` → todo verde.

**Flag que protege:** las flags SON el objeto de esta fase; el master `STACKY_PR_REVIEWER_ENABLED` es **default ON** (`config.py` = `"true"` + `default=True` + entrada en `_CURATED_DEFAULTS_ON`).

**Impacto por runtime:** ninguno (solo declaración). **Fallback:** N/A.

**Trabajo del operador:** ninguno (nace activada; el operador puede apagarla con un click si no la quiere).

---

### F1 — `list_merge_requests` + `get_merge_request_diff` en el puerto MR/PR + GitLab + ADO

**Objetivo (1 frase):** que el puerto `MergeRequestProvider` sepa listar las PRs abiertas y traer el diff de una PR, en GitLab y ADO, con shape normalizado.

**Valor:** es el sustrato de datos de toda la sección; sin esto no hay lista ni diff que revisar.

**Archivos a editar:**
- `backend/services/merge_request_provider.py` — agregar al `Protocol` (H1) las firmas y extender `MR_PORT_METHODS`:
  ```python
  def list_merge_requests(self, state: str = "open") -> list[dict]:
      """Lista PRs/MRs. state ∈ {"open","merged","closed","all"} (default "open").
      Retorna lista de: {'id': str, 'title': str, 'state': 'open'|'merged'|'closed',
                         'source_branch': str, 'target_branch': str,
                         'author': str, 'web_url': str,
                         'pipeline_status': str}  # mismo vocabulario que get_merge_request
      """
      ...

  def get_merge_request_diff(self, mr_id: str) -> dict:
      """Detalle + diff de una PR/MR (crudo, SIN sanear — el saneo lo hace la capa API).
      Retorna: {'id': str,
                'files': [{'path': str, 'change_type': 'added'|'modified'|'deleted'|'renamed'}],
                'diff_text': str,        # unified diff concatenado (GitLab); '' si no disponible
                'diff_available': bool,  # False en ADO v1 (degradación controlada)
                'note': str}             # hint humano si diff_available=False
      """
      ...
  ```
  ```python
  MR_PORT_METHODS = (
      "create_merge_request", "get_merge_request", "merge_merge_request",
      "list_merge_requests", "get_merge_request_diff",  # Plan 110
  )
  ```
  > **Nota de compatibilidad:** `get_merge_request_provider` hace `isinstance(writer, MergeRequestProvider)` (H2, Protocol `runtime_checkable`). Al sumar métodos al Protocol, **ambos** writers reales (GitLab, ADO) deben implementarlos (esta fase lo hace) o el `isinstance` fallará. Cualquier fake de test debe implementarlos también (los tests de este plan usan los providers reales con `_client._request` mockeado, así que ya los tienen).

- `backend/services/gitlab_provider.py` — agregar los dos métodos cerca de `get_merge_request` (:649):
  ```python
  def list_merge_requests(self, state: str = "open") -> list[dict]:
      """GET /projects/:id/merge_requests?state=<opened|merged|closed|all>&scope=all."""
      proj_path = self._client._project_path()
      gl_state = {"open": "opened", "merged": "merged", "closed": "closed", "all": "all"}.get(state, "opened")
      # C5: query vía params= (firma real _request(..., params=...)), no embebida en el path.
      body, _ = self._client._request(
          "GET",
          f"/projects/{proj_path}/merge_requests",
          params={"state": gl_state, "scope": "all", "per_page": 50, "order_by": "updated_at"},
      )
      rows = body if isinstance(body, list) else []
      state_map = {"opened": "open", "merged": "merged", "closed": "closed"}
      out = []
      for mr in rows:
          hp = mr.get("head_pipeline") or {}
          ps_map = {"created": "created", "pending": "pending", "running": "running",
                    "success": "success", "failed": "failed", "canceled": "canceled",
                    "skipped": "canceled"}
          out.append({
              "id": str(mr.get("iid") or ""),
              "title": mr.get("title") or "",
              "state": state_map.get(mr.get("state") or "", "open"),
              "source_branch": mr.get("source_branch") or "",
              "target_branch": mr.get("target_branch") or "",
              "author": ((mr.get("author") or {}).get("name")) or "",
              "web_url": mr.get("web_url") or "",
              "pipeline_status": ps_map.get(hp.get("status") or "", "none"),
          })
      return out

  def get_merge_request_diff(self, mr_id: str) -> dict:
      """GET /projects/:id/merge_requests/:iid/changes."""
      proj_path = self._client._project_path()
      body, _ = self._client._request(
          "GET", f"/projects/{proj_path}/merge_requests/{mr_id}/changes",
      )
      changes = (body.get("changes") if isinstance(body, dict) else None) or []
      files, parts = [], []
      for ch in changes:
          if ch.get("new_file"):
              ct = "added"
          elif ch.get("deleted_file"):
              ct = "deleted"
          elif ch.get("renamed_file"):
              ct = "renamed"
          else:
              ct = "modified"
          path = ch.get("new_path") or ch.get("old_path") or ""
          files.append({"path": path, "change_type": ct})
          if ch.get("diff"):
              parts.append(f"--- {path} ({ct}) ---\n{ch['diff']}")
      return {
          "id": str(mr_id),
          "files": files,
          "diff_text": "\n".join(parts),
          "diff_available": True,
          "note": "",
      }
  ```
- `backend/services/ado_provider.py` — agregar los dos métodos cerca de `get_merge_request` (:301):
  ```python
  def list_merge_requests(self, state: str = "open") -> list[dict]:
      """GET .../pullrequests?searchCriteria.status=<active|completed|abandoned|all>."""
      from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
      repo_id = _resolve_repo_id(self._project)
      ado_status = {"open": "active", "merged": "completed", "closed": "abandoned", "all": "all"}.get(state, "active")
      url = (f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests"
             f"?searchCriteria.status={ado_status}&$top=50&api-version=7.1")
      resp = self._client._request("GET", url)
      rows = resp.get("value", []) if isinstance(resp, dict) else []
      state_map = {"active": "open", "completed": "merged", "abandoned": "closed"}
      out = []
      for pr in rows:
          out.append({
              "id": str(pr.get("pullRequestId") or ""),
              "title": pr.get("title") or "",
              "state": state_map.get(pr.get("status") or "", "open"),
              "source_branch": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
              "target_branch": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
              "author": ((pr.get("createdBy") or {}).get("displayName")) or "",
              "web_url": pr.get("_links", {}).get("web", {}).get("href", ""),
              "pipeline_status": "none",  # v1: no consultamos builds en el listado (barato)
          })
      return out

  def get_merge_request_diff(self, mr_id: str) -> dict:
      """Degradación controlada (v1): lista de archivos cambiados de la última iteración.
      El diff línea a línea de ADO requiere varias llamadas por archivo; NO se incluye en v1.
      """
      from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
      repo_id = _resolve_repo_id(self._project)
      base = f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullRequests/{mr_id}"
      files = []
      try:
          iters = self._client._request("GET", f"{base}/iterations?api-version=7.1")
          it_list = iters.get("value", []) if isinstance(iters, dict) else []
          if it_list:
              last = it_list[-1].get("id")
              changes = self._client._request("GET", f"{base}/iterations/{last}/changes?api-version=7.1")
              ct_map = {"add": "added", "edit": "modified", "delete": "deleted", "rename": "renamed"}
              for c in (changes.get("changeEntries", []) if isinstance(changes, dict) else []):
                  item = c.get("item") or {}
                  files.append({
                      "path": item.get("path") or "",
                      "change_type": ct_map.get((c.get("changeType") or "").lower().split(",")[0], "modified"),
                  })
      except Exception:
          files = []
      return {
          "id": str(mr_id),
          "files": files,
          "diff_text": "",
          "diff_available": False,
          "note": "Azure DevOps: en esta versión se listan los archivos cambiados, no el detalle línea a línea.",
      }
  ```

**Tests primero (archivo nuevo `backend/tests/test_plan110_list_merge_requests.py`):**
- `test_gitlab_list_normalizes_state_and_pipeline`: mockeando `GitLabProvider._client._request` con una respuesta de lista, verifica el shape y `opened→open`.
- `test_gitlab_get_diff_builds_files_and_text`: verifica `files`, `diff_text`, `diff_available=True`.
- `test_ado_list_normalizes_status_and_refs`: `active→open`, `refs/heads/x→x`.
- `test_ado_get_diff_degrades_gracefully`: `diff_available=False`, `note` no vacío, `files` de las changeEntries.
- `test_protocol_surface_includes_new_methods`: `"list_merge_requests" in MR_PORT_METHODS and "get_merge_request_diff" in MR_PORT_METHODS`.

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_list_merge_requests.py -q` → verde.
- No-regresión: `".venv/Scripts/python.exe" -m pytest tests/test_plan95_production.py -q` (o el nombre real de los tests del Plan 95; buscar con `Glob tests/test_plan95*.py`) → sigue verde.

**Flag que protege:** ninguna en esta capa (es puramente el provider); el gate vive en F2+.

**Impacto por runtime:** ninguno (capa de tracker, agnóstica al runtime). **Fallback:** ADO degrada a lista-de-archivos (documentado).

**Trabajo del operador:** ninguno.

---

### F2 — Endpoint de LISTADO de PRs (`GET /api/pr-review/list`)

**Objetivo (1 frase):** exponer la lista de PRs del tracker/proyecto activo, gateada por la flag y a prueba de 500.

**Valor:** el dashboard necesita "cargar todas las PR" (pedido literal del operador).

**Archivos a crear/editar:**
- `backend/api/pr_review.py` (NUEVO) — blueprint `bp = Blueprint("pr_review", __name__, url_prefix="/pr-review")`. Reusar el patrón de guard + `_call_provider` de `devops_production` (H13):
  ```python
  """api/pr_review.py — Plan 110. Revisor de PRs (Haiku solo-lectura + modelo local).
  url_prefix SIN /api (patrón devops_production.py:2)."""
  from flask import Blueprint, abort, request, jsonify
  from werkzeug.exceptions import HTTPException
  import config as _config
  from services.merge_request_provider import get_merge_request_provider
  from services.tracker_provider import TrackerConfigError, TrackerApiError

  bp = Blueprint("pr_review", __name__, url_prefix="/pr-review")

  def _flag_off() -> bool:
      return not getattr(_config.config, "STACKY_PR_REVIEWER_ENABLED", False)

  def _guard():
      if _flag_off():
          abort(404)
      if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
          abort(400, description="Content-Type application/json requerido")

  def _call_provider(fn):
      try:
          return fn()
      except TrackerConfigError as e:
          return {"error": str(e), "kind": "tracker_config"}, 400
      except TrackerApiError as e:
          return {"error": str(e), "kind": e.kind}, e.status or 502
      except HTTPException:
          raise
      except Exception:
          return {"error": "error interno del revisor de PRs"}, 500

  @bp.get("/list")
  def list_prs():
      """GET /pr-review/list?project=<name>&state=<open|merged|closed|all>."""
      _guard()
      def _do():
          project = request.args.get("project")
          state = request.args.get("state", "open")
          provider = get_merge_request_provider(project)
          return {"provider": provider.name, "merge_requests": provider.list_merge_requests(state)}
      return _call_provider(_do)
  ```
- `backend/api/__init__.py` — importar y registrar (patrón H16):
  ```python
  from .pr_review import bp as pr_review_bp  # Plan 110 — revisor de PRs
  # ... y junto a los devops_* :
  api_bp.register_blueprint(pr_review_bp)  # Plan 110 — url_prefix="/pr-review" → /api/pr-review/...
  ```

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_list_endpoint.py`):**
- `test_list_404_when_flag_off`: con flag OFF → 404.
- `test_list_ok_with_flag_on`: con flag ON y `get_merge_request_provider` mockeado devolviendo un provider fake con `list_merge_requests` → 200 y shape `{provider, merge_requests:[...]}`.
- `test_list_tracker_error_is_not_500`: si el provider lanza `TrackerApiError(status=502,...)` → respuesta 502 con `error`/`kind`, no 500.
- `test_list_config_error_400`: `TrackerConfigError` → 400.

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_list_endpoint.py -q` → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED` (404 si OFF).

**Impacto por runtime:** ninguno (HTTP + tracker). **Fallback:** error descriptivo, nunca 500.

**Trabajo del operador:** ninguno (opt-in default off).

---

### F3 — Endpoint de DETALLE + DIFF saneado (`GET /api/pr-review/detail`)

**Objetivo (1 frase):** devolver el detalle de una PR y su diff **saneado** (truncado + secretos redactados), listo para alimentar al modelo, sin persistir el diff crudo.

**Valor:** es el payload central de la revisión; el saneo es el guardarraíl de privacidad (7).

**Archivos a crear/editar:**
- `backend/services/pr_review_sanitize.py` (NUEVO, módulo PURO sin flask/IO):
  ```python
  """pr_review_sanitize.py — Plan 110. Saneo de diffs antes de mandarlos a un modelo
  (secretos técnicos + PII básica: email, C1).
  PURO: sin flask, sin IO, sin config. Determinístico y testeable."""
  from __future__ import annotations
  import re

  _TRUNCATION_MARKER = "\n\n[... diff truncado por tamaño; ver la PR completa en el tracker ...]"

  _SECRET_PATTERNS = [
      re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._\-]+"),
      re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                 # AWS access key id
      re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),             # GitHub PAT
      re.compile(r"\bglpat-[A-Za-z0-9\-_]{20,}\b"),        # GitLab PAT
      re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),    # Slack token
      re.compile(r"(?i)(password\s*[=:]\s*)\S+"),
      re.compile(r"(?i)(secret\s*[=:]\s*)\S+"),
      re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)\S+"),
      re.compile(r"://[^:@/\s]+:([^@/\s]+)@"),             # user:pass@host
      re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
      re.compile(r"(?i)\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),  # PII: email (C1) — se enmascara completo
  ]
  _MASK = "***REDACTED***"

  def redact_secrets(text: str) -> str:
      if not text:
          return text
      out = text
      for pat in _SECRET_PATTERNS:
          if pat.groups >= 1:
              out = pat.sub(lambda m: m.group(1) + _MASK, out)
          else:
              out = pat.sub(_MASK, out)
      return out

  def truncate(text: str, max_chars: int) -> tuple[str, bool]:
      if text is None:
          return "", False
      if max_chars <= 0 or len(text) <= max_chars:
          return text, False
      return text[:max_chars] + _TRUNCATION_MARKER, True

  def sanitize_diff(text: str, max_chars: int) -> tuple[str, bool]:
      """Redacta secretos y luego trunca. Retorna (texto_saneado, truncated)."""
      return truncate(redact_secrets(text or ""), max_chars)
  ```
- `backend/api/pr_review.py` — agregar la ruta:
  ```python
  from services.pr_review_sanitize import sanitize_diff

  @bp.get("/detail")
  def detail_pr():
      """GET /pr-review/detail?project=<name>&mr_id=<id>. Devuelve meta + diff saneado."""
      _guard()
      def _do():
          project = request.args.get("project")
          mr_id = request.args.get("mr_id")
          if not mr_id:
              abort(400, description="mr_id requerido")
          provider = get_merge_request_provider(project)
          meta = provider.get_merge_request(mr_id)          # H3/H5 (state, pipeline_status, mergeable)
          diff = provider.get_merge_request_diff(mr_id)     # F1
          cap = int(getattr(_config.config, "STACKY_PR_REVIEW_DIFF_MAX_CHARS", 60000))
          sanitized, truncated = sanitize_diff(diff.get("diff_text", ""), cap)
          return {
              "id": str(mr_id),
              "meta": meta,
              "files": diff.get("files", []),
              "diff_text": sanitized,          # SANEADO
              "diff_truncated": truncated,
              "diff_available": diff.get("diff_available", False),
              "note": diff.get("note", ""),
          }
      return _call_provider(_do)
  ```
  > **Privacidad (guardarraíl 7):** este endpoint NO crea `AgentExecution` ni persiste el diff; solo lo devuelve saneado a la UI. La persistencia (solo metadatos) ocurre en F4/F5.

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_detail_diff.py`):**
- Sobre el módulo puro:
  - `test_truncate_marks_and_caps`: texto > cap → truncado + marker + `True`.
  - `test_redacts_bearer_password_pat_privatekey`: cada patrón queda enmascarado; el prefijo (`password=`) se conserva y el valor se enmascara.
  - `test_redacts_email_pii` (C1): un email (`juan.perez@empresa.com`) en el diff queda enmascarado a `***REDACTED***` y NO aparece el original.
  - `test_sanitize_diff_redacts_then_truncates`: un secreto dentro de los primeros N chars queda redactado aunque haya truncado.
- Sobre el endpoint:
  - `test_detail_404_when_flag_off`.
  - `test_detail_requires_mr_id` → 400.
  - `test_detail_returns_sanitized_diff`: provider fake devuelve un diff con un `ghp_...` → la respuesta trae `***REDACTED***` y NO el secreto.
  - `test_detail_ado_degraded_note`: `diff_available=False` propaga `note`.

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_detail_diff.py -q` → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED`.

**Impacto por runtime:** ninguno. **Fallback:** ADO sin diff línea a línea → `note`.

**Trabajo del operador:** ninguno.

---

### F4 — Revisión con Claude Haiku (solo-lectura, sin herramientas) (`POST /api/pr-review/review/haiku`)

**Objetivo (1 frase):** que Haiku (y solo Haiku) revise la PR y devuelva `{summary, findings[], recommended_action, confidence}` en JSON, sin poder ejecutar nada.

**Valor:** el corazón del pedido: "revisar con claude haiku EXCLUSIVAMENTE... dé un resumen... recomiende ejecutar alguna opción".

**Archivos a crear/editar:**
- `backend/copilot_bridge.py` — **(C2, PRE-REQUISITO del timeout real)** cablear `STACKY_PR_REVIEW_TIMEOUT_SEC`: hoy `_invoke_copilot` (`copilot_bridge.py:603`) tiene `timeout=120` **hardcodeado** en su `requests.post` (`:664`) y su firma NO acepta timeout. Agregar un kwarg **opcional** `timeout: int = 120` a `_invoke_copilot` (backward-compatible: el default 120 replica el valor actual, ningún caller existente cambia) y usarlo en `requests.post(config.COPILOT_ENDPOINT, ..., timeout=timeout)`.
- `backend/copilot_bridge.py` — agregar función pública `invoke_haiku` (espejo de `invoke_local_llm`, H7; fuerza engine Copilot H10; propaga el `timeout` de la flag, C2):
  ```python
  def invoke_haiku(
      *,
      agent_type: str,
      system: str,
      user: str,
      on_log: LogFn,
      execution_id: int | None = None,
      model: str,
      timeout: int = 120,
  ) -> BridgeResponse:
      """Revisión Haiku solo-lectura: completion de chat pura vía el engine Copilot,
      IGNORANDO LLM_BACKEND (espejo de invoke_local_llm). SIN herramientas.
      Exige que `model` contenga 'haiku' (criterio de api/agents.py:554).
      `timeout` proviene de STACKY_PR_REVIEW_TIMEOUT_SEC (C2)."""
      if "haiku" not in (model or "").lower():
          raise ValueError(f"invoke_haiku exige un modelo Haiku, recibido: {model!r}")
      return _invoke_copilot(
          agent_type=agent_type, system=system, user=user,
          on_log=on_log, execution_id=execution_id, model=model, timeout=timeout,
      )
  ```
- `backend/api/pr_review.py` — agregar la ruta y helpers de persistencia (reusar el patrón de ticket interno de `local_llm_analysis.py`, H8; **NO** usar el mismo `ado_id=-5`: elegir `_PR_REVIEW_ADO_ID = -6` para no colisionar):
  ```python
  import json
  from datetime import datetime
  from db import session_scope
  from models import AgentExecution, Ticket

  _PR_REVIEW_ADO_ID = -6  # discriminador de ticket interno (patrón local_llm_analysis.py:28)

  _REVIEW_HITL = (
      "\n\nREGLA ABSOLUTA (solo-lectura):\n"
      "- NUNCA ejecutes comandos, no edites archivos, no commitees, no mergees.\n"
      "- Vos SOLO analizás y recomendás UNA acción; el humano decide y aprieta el botón.\n"
      "- La acción recomendada DEBE ser una de: approve, comment, request_changes, merge, close, none.\n"
  )

  def _ensure_internal_ticket(session, project: str) -> Ticket:
      # copia EXACTA del patrón local_llm_analysis.py:55-81 pero con _PR_REVIEW_ADO_ID
      ...

  def _create_execution(session, ticket_id, agent_type, payload) -> int:
      # copia de local_llm_analysis.py:84-99 — payload SOLO metadatos, NUNCA el diff crudo
      ...

  def _finish_execution(execution_id, *, status, output="", error=""):
      # copia de local_llm_analysis.py:102-112
      ...

  def _build_review_context(meta: dict, files: list, diff_text: str, title: str, description: str) -> str:
      lines = [
          f"Título: {title}",
          f"Descripción: {description or '(sin descripción)'}",
          f"Rama origen → destino: {meta.get('source_branch','?')} → {meta.get('target_branch','?')}",
          f"Estado: {meta.get('state','?')} | Pipeline: {meta.get('pipeline_status','?')} | Mergeable: {meta.get('mergeable', '?')}",
          "Archivos cambiados:",
      ] + [f"  - {f['path']} ({f['change_type']})" for f in files]
      lines.append("\n== DIFF (saneado, puede estar truncado) ==\n" + (diff_text or "(no disponible)"))
      return "\n".join(lines)

  @bp.post("/review/haiku")
  def review_haiku():
      """POST /pr-review/review/haiku  Body: {project, mr_id}."""
      _guard()
      body = request.get_json(silent=True) or {}
      project = body.get("project")
      mr_id = body.get("mr_id")
      if not mr_id:
          return jsonify({"error": "mr_id_required"}), 400

      model = getattr(_config.config, "STACKY_PR_REVIEW_HAIKU_MODEL", "")
      if "haiku" not in (model or "").lower():
          return jsonify({"error": "model_not_haiku",
                          "message": "El modelo configurado no es un Haiku. Corregilo en el panel del Arnés."}), 400

      # 1) Traer meta + diff saneado (reusa la lógica de F3, sin persistir el diff)
      def _fetch():
          provider = get_merge_request_provider(project)
          meta = provider.get_merge_request(mr_id)
          diff = provider.get_merge_request_diff(mr_id)
          cap = int(getattr(_config.config, "STACKY_PR_REVIEW_DIFF_MAX_CHARS", 60000))
          sanitized, truncated = sanitize_diff(diff.get("diff_text", ""), cap)
          return meta, diff, sanitized, truncated
      fetched = _call_provider(_fetch)
      if isinstance(fetched, tuple) and len(fetched) == 2 and isinstance(fetched[1], int):
          return fetched  # (error_dict, status) devuelto por _call_provider
      meta, diff, sanitized, truncated = fetched

      system = (
          "Sos un revisor de código senior. Tu ÚNICA tarea es revisar el pedido de "
          "cambios y responder EXCLUSIVAMENTE con un objeto JSON (sin markdown)." + _REVIEW_HITL +
          '\nFormato EXACTO: {"summary": str, '
          '"findings": [{"severity": "info"|"warning"|"critical", "title": str, "detail": str}], '
          '"recommended_action": {"type": "approve"|"comment"|"request_changes"|"merge"|"close"|"none", '
          '"label": str, "params": {}}, "confidence": 0..1}'
      )
      user = _build_review_context(meta, diff.get("files", []), sanitized,
                                   body.get("title") or "", body.get("description") or "")

      # 2) Persistir SOLO metadatos (guardarraíl 7: nunca el diff crudo)
      with session_scope() as session:
          ticket = _ensure_internal_ticket(session, project or "__pr_review__")
          execution_id = _create_execution(session, ticket.id, "pr_review_haiku",
              {"mr_id": str(mr_id), "diff_chars": len(sanitized), "diff_truncated": truncated, "model": model})

      # 3) Invocar Haiku (sin tools)
      from copilot_bridge import invoke_haiku
      try:
          _timeout = int(getattr(_config.config, "STACKY_PR_REVIEW_TIMEOUT_SEC", 120))
          resp = invoke_haiku(agent_type="pr_review_haiku", system=system, user=user,
                              on_log=lambda level, msg: None, execution_id=execution_id,
                              model=model, timeout=_timeout)
      except Exception as e:
          _finish_execution(execution_id, status="error", error=str(e))
          return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502

      review = _parse_review_json(resp.text)  # helper defensivo (strip ```), coerce action inválida→"none"
      _finish_execution(execution_id, status="completed", output=json.dumps(review, ensure_ascii=False))
      return jsonify({"ok": True, "review": review, "model": model,
                      "diff_truncated": truncated, "diff_available": diff.get("diff_available", False),
                      "execution_id": execution_id})
  ```
  - `_parse_review_json(text)`: reusa la técnica de `local_llm_analysis.py:323-338` (quita fence ```); si `recommended_action.type` no está en el set cerrado, lo fuerza a `"none"`; si el JSON no parsea, devuelve `{"summary": text[:2000], "findings": [], "recommended_action": {"type":"none","label":"Revisar manualmente","params":{}}, "confidence": 0.0}`.

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_haiku.py`):**
- `test_review_haiku_404_when_flag_off`.
- `test_rejects_non_haiku_model`: con `STACKY_PR_REVIEW_HAIKU_MODEL="gpt-4o"` → 400 `model_not_haiku`, y **no** se llama a `invoke_haiku`.
- `test_haiku_review_is_toolless_chat`: monkeypatch `copilot_bridge.invoke_haiku` para capturar args → se llama con el `model` haiku y SIN ningún parámetro de herramientas (la firma no las tiene); `_invoke_copilot` interno mockeado a un `requests.post` fake.
- `test_review_json_parsed_and_action_coerced`: respuesta del modelo con `recommended_action.type="rm -rf"` → coercionada a `"none"`.
- `test_execution_row_never_stores_raw_diff`: el `input_context_json` del `AgentExecution` creado NO contiene el texto del diff (solo `diff_chars`/`diff_truncated`).
- `test_invoke_haiku_raises_on_non_haiku`: unit sobre `copilot_bridge.invoke_haiku` con model no-haiku → `ValueError`.
- `test_timeout_flag_is_wired` (C2): con `STACKY_PR_REVIEW_TIMEOUT_SEC=45`, monkeypatch `copilot_bridge.invoke_haiku` captura kwargs → recibe `timeout=45`; y unit: `_invoke_copilot` acepta `timeout` y lo propaga a `requests.post` (mock de `requests.post` verifica `timeout=45`).

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_haiku.py -q` → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED`; modelo por `STACKY_PR_REVIEW_HAIKU_MODEL`; **timeout REAL por `STACKY_PR_REVIEW_TIMEOUT_SEC` (C2):** se lee en el endpoint y se pasa como kwarg `timeout` a `invoke_haiku` → `_invoke_copilot` → `requests.post(timeout=...)`. La flag NO es fantasma: cambia el tiempo máximo de espera efectivo de la revisión Haiku. Test: `test_plan110_pr_review_haiku.py::test_timeout_flag_is_wired`.

**Impacto por runtime:** idéntico en Codex/Claude/Copilot (no spawnea runtime; usa `_invoke_copilot` HTTP). **Fallback:** sin token/modelo Haiku → 502 con hint.

**Trabajo del operador:** ninguno más que activar la flag y confirmar el id del modelo (opt-in).

---

### F4bis — Endpoint de MODELOS Copilot disponibles (`GET /api/pr-review/models`) — C3

**Objetivo (1 frase):** exponer, gateado, el catálogo de modelos que ve el token de Copilot/GitHub para que el operador elija el id Haiku exacto, resolviendo la contradicción §2.2(b) ↔ F7.

**Por qué un endpoint propio y no reusar el de `api/pm.py`:** el endpoint de modelos de `pm.py` (:645-679) sólo lista modelos Copilot cuando `LLM_BACKEND=="copilot"`, y el default es `"vscode_bridge"` (H23). `invoke_haiku` fuerza el engine Copilot **ignorando `LLM_BACKEND`**; el listado debe seguir la MISMA semántica. Por eso llama directo a `copilot_bridge.list_copilot_models()`.

**Archivos a editar:**
- `backend/api/pr_review.py` — agregar la ruta:
  ```python
  @bp.get("/models")
  def copilot_models():
      """GET /pr-review/models — catálogo de modelos Copilot (para elegir el id Haiku). Gateado."""
      _guard()
      def _do():
          import copilot_bridge  # import diferido (patrón pm.py:660)
          try:
              raw = copilot_bridge.list_copilot_models()
          except Exception as e:  # noqa: BLE001
              return {"error": "copilot_models_unavailable",
                      "message": f"No se pudo listar modelos de Copilot: {e}"}, 502
          models = [{"id": m.get("id") or "",
                     "name": m.get("name") or (m.get("id") or ""),
                     "is_haiku": "haiku" in (m.get("id") or "").lower()}
                    for m in (raw or []) if m.get("id")]
          return {"models": models,
                  "configured": getattr(_config.config, "STACKY_PR_REVIEW_HAIKU_MODEL", "")}
      return _call_provider(_do)
  ```

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_models.py`):**
- `test_models_404_when_flag_off`.
- `test_models_lists_and_flags_haiku`: monkeypatch `copilot_bridge.list_copilot_models` → la respuesta marca `is_haiku=True` en los ids con "haiku" y devuelve `configured`.
- `test_models_502_when_copilot_unavailable`: `list_copilot_models` lanza → 502 con hint, nunca 500.

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_models.py -q` → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED`. **Impacto por runtime:** ninguno (HTTP). **Fallback:** Copilot sin token/catálogo → 502 con hint. **Trabajo del operador:** ninguno.

---

### F5 — Revisión con MODELO LOCAL (un solo prompt autocontenido para Q&A) (`POST /api/pr-review/review/local`)

**Objetivo (1 frase):** revisar la PR con el modelo local reusando `invoke_local_llm`, armando UN único prompt con toda la info + una pregunta opcional del operador.

**Valor:** el segundo pedido literal: "revisarlo con los modelos locales... toda la información necesaria en un solo prompt para pregunta-respuesta".

**Archivos a editar:**
- `backend/api/pr_review.py` — agregar la ruta. Reusa `invoke_local_llm` (H7) y el mismo `_build_review_context` de F4. La flag del modelo local (`LOCAL_LLM_ENABLED`, H23) ya existe; si está OFF, el endpoint devuelve 400 con hint (no 404: la sección sigue siendo del revisor de PRs, pero el motor local está apagado).
  ```python
  @bp.post("/review/local")
  def review_local():
      """POST /pr-review/review/local  Body: {project, mr_id, question?}."""
      _guard()
      if not getattr(_config.config, "LOCAL_LLM_ENABLED", False):
          return jsonify({"error": "local_llm_disabled",
                          "message": "Activá el modelo local en el panel del Arnés para usar esta revisión."}), 400
      body = request.get_json(silent=True) or {}
      project = body.get("project")
      mr_id = body.get("mr_id")
      if not mr_id:
          return jsonify({"error": "mr_id_required"}), 400
      question = (body.get("question") or "").strip()

      def _fetch():
          provider = get_merge_request_provider(project)
          meta = provider.get_merge_request(mr_id)
          diff = provider.get_merge_request_diff(mr_id)
          cap = int(getattr(_config.config, "STACKY_PR_REVIEW_DIFF_MAX_CHARS", 60000))
          sanitized, truncated = sanitize_diff(diff.get("diff_text", ""), cap)
          return meta, diff, sanitized, truncated
      fetched = _call_provider(_fetch)
      if isinstance(fetched, tuple) and len(fetched) == 2 and isinstance(fetched[1], int):
          return fetched
      meta, diff, sanitized, truncated = fetched

      system = ("Sos un revisor de código senior. Analizá el pedido de cambios y respondé "
                "en markdown claro." + _REVIEW_HITL)
      context = _build_review_context(meta, diff.get("files", []), sanitized,
                                      body.get("title") or "", body.get("description") or "")
      user = (context + "\n\n== PREGUNTA DEL OPERADOR ==\n" +
              (question or "Dame un resumen de lo que hace esta PR, riesgos y qué acción recomendás (approve/comment/request_changes/merge/close/none)."))

      with session_scope() as session:
          ticket = _ensure_internal_ticket(session, project or "__pr_review__")
          execution_id = _create_execution(session, ticket.id, "pr_review_local",
              {"mr_id": str(mr_id), "diff_chars": len(sanitized), "diff_truncated": truncated,
               "has_question": bool(question)})

      from copilot_bridge import invoke_local_llm
      try:
          resp = invoke_local_llm(agent_type="pr_review_local", system=system, user=user,
                                  on_log=lambda level, msg: None, execution_id=execution_id,
                                  model=body.get("model"))
      except Exception as e:
          _finish_execution(execution_id, status="error", error=str(e))
          return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502
      _finish_execution(execution_id, status="completed", output=resp.text)
      return jsonify({"ok": True, "answer": resp.text,
                      "model": (resp.metadata or {}).get("model") or getattr(_config.config, "LOCAL_LLM_MODEL", ""),
                      "diff_truncated": truncated, "diff_available": diff.get("diff_available", False),
                      "execution_id": execution_id})
  ```

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_local.py`):**
- `test_review_local_404_when_reviewer_flag_off`.
- `test_review_local_400_when_local_llm_off`.
- `test_local_review_single_self_contained_prompt`: monkeypatch `copilot_bridge.invoke_local_llm` para capturar `user` → contiene título, ramas, estado de pipeline, "== DIFF" y "== PREGUNTA DEL OPERADOR ==" en UN solo string.
- `test_local_review_uses_operator_question`: si `question="¿por qué toca el schema?"`, aparece literal en el prompt.
- `test_local_review_never_stores_raw_diff`: `input_context_json` sin el diff.

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_local.py -q` → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED` (404) + `LOCAL_LLM_ENABLED` (400 si el motor local está OFF).

**Impacto por runtime:** ninguno (usa el motor local, agnóstico). **Fallback:** servidor local caído → 502 con hint (reusa errores de `invoke_local_llm`).

**Trabajo del operador:** ninguno más que tener el modelo local prendido (opt-in, ya existente del Plan 106).

---

### F6 — Ejecutar la acción recomendada (`POST /api/pr-review/execute`) con conjunto CERRADO + HITL

**Objetivo (1 frase):** ejecutar SOLO la acción que el humano confirmó, de un conjunto cerrado que mapea a métodos de provider existentes/definidos, con HITL fuerte para merge.

**Valor:** "que sea fácil con un botón ejecutar la acción y listo" — pero seguro.

**Conjunto CERRADO de acciones ejecutables:**

| action | método provider | disponibilidad | HITL |
|---|---|---|---|
| `none` | (ninguno) | siempre | ninguno (no-op) |
| `comment` | `comment_merge_request(mr_id, body)` (NUEVO) | siempre | `confirm=true` + `body` requerido |
| `request_changes` | `comment_merge_request(mr_id, "Cambios solicitados:\n"+body)` | siempre | `confirm=true` + `body` requerido |
| `merge` | `merge_merge_request(mr_id)` (EXISTE, H3/H5) | solo si `state=open` y `mergeable` | **`confirm=true` Y `confirm_merge=true`** |
| `close` | `close_merge_request(mr_id)` (NUEVO) | solo si `state=open` | `confirm=true` |
| `approve` | `approve_merge_request(mr_id)` (NUEVO, OPCIONAL) | solo si `hasattr(provider,"approve_merge_request")` (GitLab sí; ADO no en v1) | `confirm=true` |

**Archivos a editar:**
- `backend/services/merge_request_provider.py` — agregar al Protocol `comment_merge_request` y `close_merge_request` (NO agregar `approve_merge_request` al Protocol — es opcional por capability, se detecta con `hasattr`). Extender `MR_PORT_METHODS` con esos dos.
- `backend/services/gitlab_provider.py`:
  ```python
  def comment_merge_request(self, mr_id: str, body: str) -> dict:
      """POST /projects/:id/merge_requests/:iid/notes."""
      proj_path = self._client._project_path()
      result, _ = self._client._request(
          "POST", f"/projects/{proj_path}/merge_requests/{mr_id}/notes",
          json_body={"body": body})
      return {"ok": True, "id": str((result or {}).get("id") or "")}

  def close_merge_request(self, mr_id: str) -> dict:
      """PUT /projects/:id/merge_requests/:iid con state_event=close."""
      proj_path = self._client._project_path()
      self._client._request("PUT", f"/projects/{proj_path}/merge_requests/{mr_id}",
                            json_body={"state_event": "close"})
      return {"ok": True, "id": str(mr_id), "state": "closed"}

  def approve_merge_request(self, mr_id: str) -> dict:
      """POST /projects/:id/merge_requests/:iid/approve (OPCIONAL, capability)."""
      proj_path = self._client._project_path()
      self._client._request("POST", f"/projects/{proj_path}/merge_requests/{mr_id}/approve")
      return {"ok": True, "id": str(mr_id), "approved": True}
  ```
- `backend/services/ado_provider.py`:
  ```python
  def comment_merge_request(self, mr_id: str, body: str) -> dict:
      """POST .../pullRequests/:id/threads (comentario en el PR)."""
      from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
      repo_id = _resolve_repo_id(self._project)
      url = f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullRequests/{mr_id}/threads?api-version=7.1"
      payload = {"comments": [{"parentCommentId": 0, "content": body, "commentType": 1}], "status": 1}
      resp = self._client._request("POST", url, body=payload)
      return {"ok": True, "id": str((resp or {}).get("id") or "")}

  def close_merge_request(self, mr_id: str) -> dict:
      """PATCH .../pullrequests/:id con status=abandoned."""
      from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
      repo_id = _resolve_repo_id(self._project)
      url = f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests/{mr_id}?api-version=7.1"
      self._client._request("PATCH", url, body={"status": "abandoned"})
      return {"ok": True, "id": str(mr_id), "state": "closed"}
  # (ADO NO define approve_merge_request en v1 → capability False)
  ```
- `backend/api/pr_review.py` — ruta `execute` + capability en un GET de acciones disponibles:
  ```python
  _ALWAYS_ACTIONS = ("none", "comment", "request_changes", "merge", "close")

  @bp.get("/actions")
  def available_actions():
      """GET /pr-review/actions?project= — qué acciones soporta el tracker activo (capability)."""
      _guard()
      def _do():
          provider = get_merge_request_provider(request.args.get("project"))
          actions = list(_ALWAYS_ACTIONS)
          if hasattr(provider, "approve_merge_request"):
              actions.append("approve")
          return {"provider": provider.name, "actions": actions}
      return _call_provider(_do)

  @bp.post("/execute")
  def execute_action():
      """POST /pr-review/execute Body: {project, mr_id, action, body?, confirm, confirm_merge?}."""
      _guard()
      body = request.get_json(silent=True) or {}
      project = body.get("project")
      mr_id = body.get("mr_id")
      action = body.get("action")
      if not mr_id:
          return jsonify({"error": "mr_id_required"}), 400
      if action == "none":
          return jsonify({"ok": True, "action": "none", "result": {"noop": True}})
      if action not in ("comment", "request_changes", "merge", "close", "approve"):
          return jsonify({"error": "action_not_allowed", "message": f"Acción no permitida: {action}"}), 400
      if body.get("confirm") is not True:
          return jsonify({"error": "confirm_required", "message": "confirm=true requerido"}), 400
      if action == "merge" and body.get("confirm_merge") is not True:
          return jsonify({"error": "confirm_merge_required",
                          "message": "Para mergear tenés que marcar la casilla de confirmación fuerte."}), 400
      if action in ("comment", "request_changes") and not (body.get("body") or "").strip():
          return jsonify({"error": "body_required", "message": "El comentario no puede estar vacío"}), 400

      def _do():
          provider = get_merge_request_provider(project)
          if action == "comment":
              return {"ok": True, "action": action, "result": provider.comment_merge_request(mr_id, body["body"])}
          if action == "request_changes":
              return {"ok": True, "action": action,
                      "result": provider.comment_merge_request(mr_id, "Cambios solicitados:\n" + body["body"])}
          if action == "merge":
              return {"ok": True, "action": action, "result": provider.merge_merge_request(mr_id)}
          if action == "close":
              return {"ok": True, "action": action, "result": provider.close_merge_request(mr_id)}
          if action == "approve":
              if not hasattr(provider, "approve_merge_request"):
                  abort(400, description="El tracker activo no soporta aprobar PRs")
              return {"ok": True, "action": action, "result": provider.approve_merge_request(mr_id)}
          abort(400, description="acción no soportada")
      return _call_provider(_do)
  ```

**Tests primero (archivo nuevo `backend/tests/test_plan110_pr_review_execute.py`):**
- `test_execute_404_when_flag_off`.
- `test_none_is_noop`: `action="none"` → 200, no toca provider.
- `test_unknown_action_400`.
- `test_comment_requires_confirm_and_body`: falta `confirm`→400; falta `body`→400; con ambos → llama `comment_merge_request`.
- `test_merge_requires_double_confirm`: `confirm=true` pero sin `confirm_merge` → 400 y **no** llama `merge_merge_request`; con ambos → llama.
- `test_close_calls_close_merge_request`.
- `test_approve_capability_gated`: provider fake sin `approve_merge_request` → `action="approve"` da 400; provider con el método → llama.
- `test_actions_endpoint_reports_capability`: GitLab-fake (con approve) lista `"approve"`; ADO-fake (sin approve) no.
- Unit provider: `test_gitlab_comment_close_approve_urls` y `test_ado_comment_close_urls` (mock `_client._request`, verificar método/URL/payload).

**Criterio de aceptación (binario) + comando:**
- `".venv/Scripts/python.exe" -m pytest tests/test_plan110_pr_review_execute.py -q` → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED`.

**Impacto por runtime:** ninguno. **Fallback:** approve no soportado (ADO) → 400 claro + botón oculto en UI (F7).

**Trabajo del operador:** confirmar cada acción; merge exige checkbox literal.

---

### F7 — Frontend: sección `PrReviewerSection.tsx` + cliente API + integración

**Objetivo (1 frase):** UI de la sección con lista de PRs, botones "Revisar con Haiku" / "Revisar con modelo local" (+ pregunta), panel de resumen/hallazgos, badge de acción recomendada y botón "Ejecutar" (HITL).

**Valor:** el dashboard en sí (pedido literal).

**Archivos a crear/editar:**
- `frontend/src/api/endpoints.ts` — agregar el objeto `PrReview` (patrón H22) e interfaces:
  ```typescript
  export interface PrSummary {
    id: string; title: string; state: "open" | "merged" | "closed";
    source_branch: string; target_branch: string; author: string;
    web_url: string; pipeline_status: string;
  }
  export interface PrReviewFinding { severity: "info" | "warning" | "critical"; title: string; detail: string; }
  export interface PrRecommendedAction {
    type: "approve" | "comment" | "request_changes" | "merge" | "close" | "none";
    label: string; params: Record<string, unknown>;
  }
  export interface PrHaikuReview {
    summary: string; findings: PrReviewFinding[];
    recommended_action: PrRecommendedAction; confidence: number;
  }
  export const PrReview = {
    list: (project: string, state = "open") =>
      api.get<{ provider: string; merge_requests: PrSummary[] }>(
        `/api/pr-review/list?project=${encodeURIComponent(project)}&state=${state}`),
    detail: (project: string, mrId: string) =>
      api.get<{ id: string; meta: MrInfo; files: {path:string;change_type:string}[];
                diff_text: string; diff_truncated: boolean; diff_available: boolean; note: string }>(
        `/api/pr-review/detail?project=${encodeURIComponent(project)}&mr_id=${encodeURIComponent(mrId)}`),
    reviewHaiku: (project: string, mrId: string) =>
      api.post<{ ok: boolean; review: PrHaikuReview; model: string; diff_truncated: boolean; execution_id: number }>(
        "/api/pr-review/review/haiku", { project, mr_id: mrId }),
    reviewLocal: (project: string, mrId: string, question?: string) =>
      api.post<{ ok: boolean; answer: string; model: string; diff_truncated: boolean; execution_id: number }>(
        "/api/pr-review/review/local", { project, mr_id: mrId, question }),
    actions: (project: string) =>
      api.get<{ provider: string; actions: string[] }>(
        `/api/pr-review/actions?project=${encodeURIComponent(project)}`),
    models: () =>  // C3 — catálogo Copilot para elegir el id Haiku
      api.get<{ models: { id: string; name: string; is_haiku: boolean }[]; configured: string }>(
        "/api/pr-review/models"),
    execute: (b: { project: string; mr_id: string; action: string; body?: string; confirm?: boolean; confirm_merge?: boolean }) =>
      api.post<{ ok: boolean; action: string; result: unknown }>("/api/pr-review/execute", b),
  };
  ```
  (Reusar la interfaz `MrInfo` que ya existe en `endpoints.ts:3312`.)
- `frontend/src/pages/DevOpsPage.tsx`:
  1. En `interface DevOpsHealth` (H14, línea ~36) agregar: `pr_reviewer_enabled?: boolean; // Plan 110`.
  2. Importar: `import { PrReviewerSection } from '../components/devops/PrReviewerSection';`
  3. Agregar UNA entrada a `DEVOPS_SECTIONS` (H14):
     ```tsx
     {
       id: 'pr-review',
       label: 'Revisor de PRs',
       icon: '🔎',
       healthKey: 'pr_reviewer_enabled',
       gateFlagKey: 'STACKY_PR_REVIEWER_ENABLED',
       gateMessage: 'La sección Revisor de PRs necesita la flag STACKY_PR_REVIEWER_ENABLED (Configuración → Arnés, categoría DevOps).',
       render: (ctx) => <PrReviewerSection ctx={ctx} />,
     },
     ```
- `backend/api/devops.py` — en `_health_payload()` (H12) agregar la key:
  ```python
  "pr_reviewer_enabled": bool(getattr(cfg, "STACKY_PR_REVIEWER_ENABLED", False)),  # Plan 110
  ```
- `frontend/src/api/endpoints.ts` — en el tipo de retorno de `DevOps.health` (H22, línea ~3077) agregar `pr_reviewer_enabled?: boolean; // Plan 110`.
- `frontend/src/components/devops/PrReviewerSection.tsx` (NUEVO). Props: `{ ctx: DevOpsSectionContext }`. Comportamiento mínimo (sin ambigüedad):
  - `project` = proyecto activo (usar el mismo mecanismo que otras secciones para el proyecto activo; si otras secciones toman `project` de un contexto global, reusarlo; si no, un input de texto con el nombre del proyecto). **Verificar** cómo `PipelineBuilderSection`/`VariablesSection` obtienen `project` y reusar ese patrón exacto.
  - Al montar (o al apretar "Cargar PRs"): `PrReview.list(project)` → tabla con `title`, `source→target`, `state`, `pipeline_status`, link `web_url`, y botones por fila.
  - Botón "Revisar con Haiku" → `PrReview.reviewHaiku(project, id)` → muestra `review.summary`, lista `findings` (con color por `severity`), badge con `recommended_action.label`, y botón "Ejecutar" que abre el flujo HITL.
  - Botón "Revisar con modelo local" + `<textarea>` de pregunta opcional → `PrReview.reviewLocal(project, id, question)` → muestra `answer` (markdown) para Q&A. Botón "Preguntar de nuevo" reusa el mismo `mr_id`.
  - Aviso de privacidad SIEMPRE visible antes de revisar: "El contenido del cambio (diff) se envía al modelo. Con el modelo local queda en tu máquina; con Haiku viaja al servicio de Copilot/GitHub. Los secretos evidentes se ocultan, pero revisá que no haya datos sensibles." (guardarraíl 7).
  - Botón "Ejecutar": según `recommended_action.type`:
    - `none` → deshabilitado con tooltip "El revisor no recomienda ninguna acción".
    - `comment`/`request_changes` → `<textarea>` con el comentario prellenado (editable) + botón "Ejecutar" (envía `confirm:true, body`).
    - `merge` → **checkbox literal** "Confirmo que quiero mergear esta PR a `<target_branch>`" + botón "Ejecutar" habilitado solo con el checkbox tildado (envía `confirm:true, confirm_merge:true`). Espeja Plan 95 (H13).
    - `close` → confirm simple.
    - `approve` → mostrar solo si `PrReview.actions(project).actions` incluye `"approve"`.
  - "Ver modelos disponibles" (C3, ayuda al SUPUESTO §2.2): botón que llama a `PrReview.models()` (`GET /api/pr-review/models`, F4bis) y muestra la lista resaltando los `is_haiku`, junto al id `configured` actual; al elegir uno, el operador lo pega en `STACKY_PR_REVIEW_HAIKU_MODEL` en el panel del Arnés. Si el endpoint devuelve 502, mostrar el id configurado + hint (degradación controlada).
  - **[ADICIÓN ARQUITECTO / C1] Preview del payload que sale de la máquina (obligatorio en el camino Haiku externo):** antes de habilitar "Revisar con Haiku", la UI muestra el diff SANEADO que devuelve `PrReview.detail(project, id)` en un panel colapsable "Ver exactamente qué se envía a Copilot/GitHub" y un checkbox "Reviso el contenido y confirmo el envío". El botón "Revisar con Haiku" queda deshabilitado hasta tildarlo. El camino de modelo local NO requiere este checkbox (el diff no sale de la máquina), pero muestra igual el aviso de privacidad. Esta es la compensación del default ON (human-in-the-loop).
  - Manejo de error: cualquier `!ok`/excepción → banner rojo con el `message`/`error` del backend (nunca romper la UI).
- `frontend/src/components/devops/PrReviewerSection.module.css` (NUEVO, opcional) o reusar `devops.module.css`.

**Tests primero (vitest, archivo nuevo `frontend/src/components/devops/__tests__/PrReviewerSection.test.tsx`):**
- `renders PR list from PrReview.list` (mock del cliente).
- `Haiku review shows summary and findings and recommended action badge`.
- `merge action requires the literal checkbox before Ejecutar is enabled`.
- `local review sends the operator question`.
- `approve button hidden when actions does not include approve`.
- `Haiku button disabled until the "confirmo el envío" checkbox is checked` (C1 — preview del payload externo).
- Comando: desde `Stacky Agents/frontend`, `npx vitest run src/components/devops/__tests__/PrReviewerSection.test.tsx`.

**Criterio de aceptación (binario) + comando:**
- `cd "Stacky Agents/frontend" && npx tsc --noEmit` → 0 errores.
- vitest del archivo → verde.

**Flag que protege:** `STACKY_PR_REVIEWER_ENABLED` (sub-tab gateada por `FlagGateBanner`, H14/H15).

**Impacto por runtime:** ninguno (UI). **Fallback:** health sin `pr_reviewer_enabled` (deploy viejo) → key ausente → banner de activación (comportamiento correcto).

**Trabajo del operador:** un click para activar la flag (opt-in).

---

### F8 — Cierre: ratchet de tests, no-regresión dirigida, encabezado de estado

**Objetivo (1 frase):** dejar la suite registrada (ratchet), demostrar no-regresión y actualizar el estado del doc.

**Archivos a editar:**
- `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1` (H21) — agregar al array/lista `HARNESS_TEST_FILES` los 8 archivos **en orden alfabético real** (C6):
  ```
  tests/test_plan110_list_merge_requests.py
  tests/test_plan110_pr_review_detail_diff.py
  tests/test_plan110_pr_review_execute.py
  tests/test_plan110_pr_review_flags.py
  tests/test_plan110_pr_review_haiku.py
  tests/test_plan110_pr_review_list_endpoint.py
  tests/test_plan110_pr_review_local.py
  tests/test_plan110_pr_review_models.py
  ```
  (Los 8 archivos, en AMBOS scripts; deben quedar idénticos entre sh y ps1.)
- Encabezado de este documento: pasar `Estado: PROPUESTO v1` → `IMPLEMENTADO <fecha> (<hash>)` cuando se cierre.

**Tests primero:** N/A (fase de cierre). El "test" es correr la suite completa.

**Criterio de aceptación (binario) + comandos:**
- Desde `Stacky Agents/backend`: `bash scripts/run_harness_tests.sh` → `FAIL=0 MISSING=0` (o al menos: los 7 nuevos aparecen y pasan; cualquier fallo preexistente ajeno se declara explícitamente y se demuestra con `git stash` que no lo causó este plan).
- No-regresión dirigida (los que este plan toca): `".venv/Scripts/python.exe" -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_harness_flags_help.py tests/test_plan95_*.py tests/test_plan106_playground_api.py -q` → verde (usar `Glob tests/test_plan95*.py` para el nombre real).
- `cd "Stacky Agents/frontend" && npx tsc --noEmit` → 0 errores.

**Flag que protege:** N/A. **Impacto por runtime:** N/A. **Trabajo del operador:** ninguno.

---

## 5. Cómo se honran los KPIs (mapa KPI → mecanismo → test)

| KPI | Mecanismo | Test |
|---|---|---|
| KPI-1 | `_guard()` → `abort(404)` con flag OFF en `pr_review.py`; sub-tab con `FlagGateBanner` | `test_plan110_pr_review_list_endpoint.py::test_list_404_when_flag_off` (+ el `test_*_404_when_flag_off` de detail/haiku/local/execute) |
| KPI-2 | `list_merge_requests` normaliza; `_call_provider` mapea errores | `test_plan110_list_merge_requests.py`, `test_plan110_pr_review_list_endpoint.py::test_list_tracker_error_is_not_500` |
| KPI-3 | `invoke_haiku` exige `"haiku" in model`; endpoint valida flag y usa `_invoke_copilot` (sin tools) | `test_plan110_pr_review_haiku.py::test_rejects_non_haiku_model`, `::test_haiku_review_is_toolless_chat`, `::test_invoke_haiku_raises_on_non_haiku` |
| KPI-4 | `_build_review_context` + `invoke_local_llm` con un solo `user` | `test_plan110_pr_review_local.py::test_local_review_single_self_contained_prompt` |
| KPI-5 | `pr_review_sanitize.sanitize_diff` (redact secretos+PII+truncate); `_create_execution` guarda solo metadatos | `test_plan110_pr_review_detail_diff.py::test_sanitize_diff_redacts_then_truncates`, `::test_redacts_email_pii` (C1), `test_plan110_pr_review_haiku.py::test_execution_row_never_stores_raw_diff` |
| KPI-6 | `execute` exige `confirm` + `confirm_merge` para merge | `test_plan110_pr_review_execute.py::test_merge_requires_double_confirm` |
| KPI-7 | FlagSpec `env_only=False` + PLAIN_HELP sin jerga | `test_harness_flags_help.py::test_plain_help_covers_all_registry_keys`, `::test_plain_help_avoids_jargon_denylist` |
| KPI-8 | 1 entrada `DEVOPS_SECTIONS` + 1 componente + 1 objeto `endpoints.ts`; tsc | `npx tsc --noEmit`; vitest de F7 |

---

## 6. Riesgos y mitigaciones

1. **[ALTO] Datos personales / secretos en el diff — agravado por el default ON.** El diff puede contener credenciales, tokens o datos personales. Al revisar con Haiku, el diff **sale de la máquina** hacia el servicio de Copilot/GitHub; con el modelo local queda en la máquina del operador. **El default ON (decisión del operador) aumenta la superficie de exposición:** la sección queda disponible out-of-the-box, sin un gesto de opt-in explícito que "avise" al operador de que hay un camino que puede exfiltrar el diff a un tercero. Ninguna revisión ocurre sin que el humano apriete un botón (no hay auto-review), pero la capacidad está a un click de distancia por default. **Mitigación:** (a) redacción de patrones de secreto **y de PII básica (email)** (`pr_review_sanitize.redact_secrets`, C1); (b) truncado a `STACKY_PR_REVIEW_DIFF_MAX_CHARS`; (c) **aviso de privacidad + preview del payload EXACTO que sale de la máquina (el diff saneado de `/detail`) + checkbox de confirmación, SIEMPRE visible en la UI ANTES de revisar con Haiku** (F7, [ADICIÓN ARQUITECTO] C1) — obligatorio, es la compensación directa del default ON; (d) el diff crudo **nunca** se persiste en la DB (`input_context_json` solo lleva metadatos) ni se loguea en claro (`on_log=lambda ...: None`); (e) el operador puede apagar la sección con un click (gate reversible). **Residual:** la redacción por patrones no es exhaustiva y con el default ON el revisor está activo sin opt-in; el aviso de la UI traslada la decisión final al operador (human-in-the-loop). Documentar este residual en la ayuda de la sección. **Si el operador maneja repos con datos personales/regulados, evaluar apagar la revisión Haiku (externa) y usar solo el modelo local, que no saca el diff de la máquina.**
2. **[MEDIO] SUPUESTO del id de modelo Haiku en Copilot.** Si el catálogo del operador no expone un Haiku, la revisión Haiku no funciona. **Mitigación:** flag editable + validación `"haiku"` + 502 con hint + camino local independiente que sí funciona. Ver §2.2.
3. **[MEDIO] Tightening del Protocol MR/PR.** Sumar métodos al `Protocol` `runtime_checkable` endurece el `isinstance` de la fábrica (H2). **Mitigación:** implementar los métodos en AMBOS providers reales en la misma fase (F1/F6) y correr los tests del Plan 95 como no-regresión (F8). Los tests de este plan usan providers reales con `_client._request` mockeado.
4. **[BAJO] ADO sin diff línea a línea (v1).** La revisión ADO recibe solo la lista de archivos + metadatos. **Mitigación:** degradación explícita (`diff_available=False` + `note`), la UI lo muestra; la revisión sigue siendo útil (título/descripción/ramas/pipeline/archivos). Full diff ADO = fuera de scope v1 (§7).
5. **[BAJO] Acción `merge`/`close`/`approve` es destructiva/irreversible.** **Mitigación:** conjunto cerrado; el modelo NUNCA ejecuta (endpoint de review sin tools); merge exige doble confirmación; approve capability-gated; `_call_provider` nunca 500.
6. **[BAJO] Colisión de ticket interno.** `_PR_REVIEW_ADO_ID=-6` distinto del `-5` del Plan 106 y del `-1` (brief). **Mitigación:** verificar que `-6` no esté usado (grep `ado_id == -6` / `_ADO_ID = -6`) antes de fijarlo; si estuviera, usar el siguiente negativo libre.

---

## 7. Fuera de scope (v1)

- Diff unificado línea a línea para ADO (se lista archivos; el detalle textual queda para una fase futura).
- Comentarios *inline* sobre líneas específicas del diff (solo comentario a nivel PR).
- Revisión en lote / cola de revisiones automáticas (esto es a demanda, un PR por vez).
- Aprobación (`approve`) en ADO (capability False en v1; solo GitLab).
- Persistencia/histórico navegable de revisiones más allá del `AgentExecution` que ya se crea.
- Integración con webhooks para revisar automáticamente al abrir una PR (rompería "el humano dispara").
- Selección de modelo Haiku distinto por-request desde la UI (el modelo lo fija la flag; server-side se valida "haiku").

---

## 8. Glosario + Orden de implementación + DoD

### 8.1 Glosario

- **PR / MR:** Pull Request (ADO) / Merge Request (GitLab) — un pedido de fusionar una rama en otra. En el código el puerto se llama `MergeRequestProvider` y ambos comparten el vocabulario de estado `open|merged|closed`.
- **Tracker provider:** implementación concreta del puerto (GitLab o ADO) resuelta por `get_merge_request_provider(project)`.
- **Haiku vía engine Copilot (`invoke_haiku`):** completion de chat HTTP contra el servicio de Copilot/GitHub Models, forzando el modelo Haiku, sin herramientas. Runtime-agnóstica (no spawnea CLIs).
- **Modelo local (`invoke_local_llm`):** cliente HTTP a un servidor local OpenAI-compatible (Ollama/LM Studio/vLLM), Plan 106; el contenido no sale de la máquina del operador.
- **HITL (human-in-the-loop):** el modelo solo propone; toda mutación la dispara el humano con el botón "Ejecutar" (merge con confirmación fuerte).
- **Acción cerrada:** una de `{none, comment, request_changes, merge, close, approve}`; cada una mapea a un método de provider existente o definido en este plan; no hay acciones libres.
- **Saneo de diff:** redacción de secretos + truncado antes de mandar el diff a cualquier modelo, y no persistirlo crudo.

### 8.2 Orden de implementación (numerado, por dependencia)

1. **F0** — flags + config + ayuda llana + requires (base).
2. **F1** — `list_merge_requests` + `get_merge_request_diff` en Protocol + GitLab + ADO.
3. **F2** — `GET /api/pr-review/list` + registrar blueprint.
4. **F3** — módulo `pr_review_sanitize` + `GET /api/pr-review/detail`.
5. **F4** — `copilot_bridge.invoke_haiku` (+ cableado real del timeout en `_invoke_copilot`, C2) + `POST /api/pr-review/review/haiku`.
6. **F4bis** — `GET /api/pr-review/models` (catálogo Copilot para elegir el id Haiku, C3).
7. **F5** — `POST /api/pr-review/review/local` (reusa `invoke_local_llm`).
8. **F6** — métodos `comment/close/approve` en providers + `POST /api/pr-review/execute` + `GET /api/pr-review/actions`.
9. **F7** — frontend: `endpoints.ts` + `DevOpsPage` + health key + `PrReviewerSection.tsx` + vitest + tsc.
10. **F8** — ratchet (sh+ps1) + no-regresión + encabezado de estado.

### 8.3 Definición de Hecho (DoD) global

- [ ] Las 4 flags nuevas existen, están categorizadas en `devops`, son `env_only=False`, tienen `requires="STACKY_DEVOPS_PANEL_ENABLED"` y ayuda llana sin jerga; `test_harness_flags*.py` verdes.
- [ ] **Default ON del master:** con entorno limpio `config.STACKY_PR_REVIEWER_ENABLED is True`, la `FlagSpec` tiene `default=True`, y `STACKY_PR_REVIEWER_ENABLED ∈ _CURATED_DEFAULTS_ON`; `test_default_known_only_for_curated` y `test_declared_default_true_set` verdes. Las 3 str/int quedan `default=None` y fuera del set.
- [ ] **Gate reversible:** con `STACKY_PR_REVIEWER_ENABLED=false` (apagada por el operador): los 7 endpoints (`list`, `detail`, `review/haiku`, `review/local`, `execute`, `actions`, `models`) dan 404 y la sub-tab muestra el banner de activación (restaura el comportamiento previo a este plan).
- [ ] `GET /api/pr-review/list` devuelve PRs normalizadas de GitLab y ADO; tracker caído → error descriptivo, nunca 500.
- [ ] `GET /api/pr-review/detail` devuelve el diff **saneado** (redactado + truncado) y `diff_available` honesto por tracker.
- [ ] La revisión Haiku usa EXCLUSIVAMENTE un modelo con `"haiku"` en el id, es una completion sin herramientas, devuelve `{summary, findings[], recommended_action∈set cerrado, confidence}`, y no persiste el diff crudo.
- [ ] La revisión local arma UN solo prompt autocontenido con todo + pregunta opcional y responde vía `invoke_local_llm`.
- [ ] `POST /api/pr-review/execute` ejecuta solo acciones del set cerrado; merge exige `confirm` + `confirm_merge`; approve es capability-gated; nunca 500.
- [ ] Frontend: sección integrada con 1 entrada en `DEVOPS_SECTIONS`, botones Haiku/local, panel de resumen/hallazgos, badge de acción, botón Ejecutar con HITL (checkbox literal para merge), aviso de privacidad; `npx tsc --noEmit` = 0; vitest de la sección verde.
- [ ] Los 8 archivos de test backend están en `HARNESS_TEST_FILES` (sh y ps1, orden alfabético) y pasan aislados con `.venv`.
- [ ] No-regresión: tests de Planes 95 y 106 y de flags siguen verdes; cualquier fallo preexistente ajeno se declara y se demuestra con `git stash` que no lo causó este plan.
- [ ] Paridad de runtimes: los caminos Haiku y local son HTTP backend, sin spawn de runtime → funcionan igual bajo Codex/Claude Code/Copilot; fallbacks (Copilot sin Haiku / local caído) devuelven 502 con hint.
- [ ] Encabezado de estado del doc actualizado a IMPLEMENTADO con fecha y hash al cerrar.
