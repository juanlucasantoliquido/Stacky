# Plan 208 — Sincronización ADO al completar un agente + Matriz de estados por (tipo de ticket x tipo de agente)

> Estado: CRITICADO v2 — APROBADO-CON-CAMBIOS (2026-07-21)
> Autor: StackyArchitectaUltraEficientCode (perfil normal, Opus 4.8)
> Plan hermano: **209** (guía de validación para el operador) — se escribe en paralelo; este plan NO lo diseña, solo lo cita donde corresponde.
> Numeración: 208 (los NN 203-207 están reservados a la serie "Fragua Nocturna" 202-207; para no fragmentarla, esta línea de trabajo arranca en 208).

---

## 0. Historial de versiones — v1 -> v2 (2026-07-21)

Revisión adversarial (juez + arquitecto). Veredicto: **APROBADO-CON-CAMBIOS** (sin bloqueantes; IMPORTANTES corregidos). El diseño base se sostiene y quedó re-verificado contra código: el chokepoint runtime-agnóstico correcto ES `ticket_status.on_execution_end`; la firma con la que `_run_post_hooks` invoca los hooks (`ticket_id, execution_id, final_status, agent_type, error`) coincide EXACTAMENTE con el `_post_hook` propuesto (`ticket_status.py:279-285,310`); y `_safe_transition(provider, ado_id, target, *, phase, legacy_client_fn=None, correlation_id=None)` coincide con las llamadas (`task_states.py:104-141`). Cambios aplicados:

- **C1 (IMPORTANTE):** F2/F3 leían la flag del ATRIBUTO DE CLASE `Config` (`from config import Config; getattr(Config, ...)`) en vez de la INSTANCIA `config.config`. Rompía el branch OFF de los tests nombrados (`monkeypatch.setattr(config.config, ..., False)` no voltea el atributo de clase) => falso verde + inconsistente con el hermano 209 y con todo el repo. Fix: `from config import config as _cfg; bool(getattr(_cfg, ...))` en `matrix_enabled()` y `sync_on_completion_enabled()`.
- **C2 (IMPORTANTE, arista HITL):** `_OK_STATUSES = {"completed","done","success"}  # ajustar al set real` era un "según corresponda" encubierto con valores MUERTOS. El `final_status` que llega al post-hook YA pasó por `_coerce_terminal_status` (`ticket_status.py:268`), que solo produce estados de `status_vocabulary.VALID_TICKET_STATUSES = {idle,running,completed,error,cancelled,needs_review}` (`status_vocabulary.py:11-18`). "done"/"success" NUNCA matchean. El único terminal de éxito es **"completed"**. Riesgo HITL: si el implementador "ajustaba" e incluía `needs_review`, R3 transicionaría a estado final tickets que EXIGEN revisión humana. Fix: set exacto resuelto e importado del vocabulario canónico, sin instrucción de "grep/ajustar".
- **C3 (IMPORTANTE):** identidad de proyecto colapsada (`stacky_project_name or project`). `stacky_project_name` (workspace Stacky) y `project` (proyecto en el tracker) son columnas DISTINTAS (`models.py:47-48`). `_startup_sync` deriva la key del breaker con `ado_breaker_project(active)` y construye el cliente con `build_ado_client(project_name=active)` usando el nombre STACKY (`app.py:196,203`). Caer al nombre del tracker divergía la key del breaker (rompía P4/R-BREAKER) y podía devolver profile/provider vacío. Fix: `stacky_project_name` como fuente canónica única; si es None -> skip, nunca usar el nombre del tracker para profile/provider/breaker.
- **C4 (IMPORTANTE):** F3 tenía DOS instrucciones contradictorias para construir el cliente ADO (cuerpo: `from api.tickets import _ado_client_for_ticket`; nota: usar `build_ado_client`). El import service->api acopla y arriesga ciclo al arrancar el daemon. Fix único: `from services.project_context import build_ado_client` (firma en `project_context.py:208`, ya usada así en `app.py:203`).
- **C5 (MENOR):** el test de regresión de Plan 79 no se llama `test_plan79_task_states.py` (no existe); el real es **`tests/test_plan79_resolver.py`**. Fijado el comando exacto, sin "grep el nombre".
- **C6 (MENOR):** F6 podía loguear `source` desde el resultado de `_safe_transition`, que devuelve `"source":"config"` HARDCODEADO (`task_states.py:136`) aun cuando la resolución fue por matriz. Fix: F6 loguea `plan.source` (="matrix").
- **C7 (MENOR):** el racional "el sync captura el estado nuevo" solo aplica al path de sync inmediato; bajo coalescing el sync se difiere. Aclarado que la convergencia es EVENTUAL (el próximo pull captura el `System.State` que R3 escribió).
- **[ADICIÓN ARQUITECTO] Guardia de origen esperado (anti-pisada del humano):** ver F2/P11. R3 ya no re-empuja `next_state_ok` si el humano movió el ticket, en el tracker, fuera del flujo de trabajo esperado (p.ej. lo devolvió a "In Progress" a propósito tras un `needs_review`). Cierra un agujero HITL real que v1 no cubría (v1 solo tenía idempotencia "ya en target", no "el humano lo movió a otro lado"). Determinista, reusa `input_states`/`in_progress`/`blocked_state` del perfil que el operador YA llena, runtime-agnóstico, sin flag nueva ni trabajo extra.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Cerrar dos brechas que hoy obligan al operador a refrescar a mano y a que el estado en Azure DevOps quede desincronizado del trabajo real de los agentes. **(R2)** Que la sincronización de tickets ADO -> base local se dispare **automáticamente cada vez que cualquier agente termina un trabajo, en cualquiera de los 3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro), de forma **best-effort, no bloqueante y coalescida** (sin tormenta de syncs). **(R3)** Que el operador pueda **configurar, por (tipo de work item x tipo de agente), a qué estado ADO se transiciona el ticket cuando ese agente termina** — una matriz editable desde la UI, con estados poblados desde el tracker real (nunca texto libre alucinado), aplicada por **código determinista de Stacky** (jamás por el LLM), **vacía por default** (cero cambios de comportamiento hasta que el operador la configure). Ambos requisitos comparten el mismo punto de integración runtime-agnóstico (el cierre de ejecución), por eso van en un solo plan con fases separadas y **cada mitad activable por su propia flag**.

**KPI / impacto medible.**
- **Frescura de datos:** tiempo entre "agente termina" y "ticket local refleja el nuevo estado ADO" pasa de *hasta el próximo sync manual/arranque* (indeterminado, minutos-horas) a **<= 1 ventana de coalescing (30 s por default)**.
- **Trabajo manual eliminado:** 0 clics de "Sincronizar" tras cada corrida (hoy es un botón manual en `POST /api/tickets/sync`, `backend/api/tickets.py:700`).
- **Consistencia ADO:** % de tickets cuyo `System.State` en ADO refleja el fin del agente sube de ~0% en los paths de runner (hoy el runner NO transiciona estado ADO) a **100% de los (tipo x agente) que el operador configure en la matriz**.
- **Cero regresión de latencia de completación:** el p95 del tiempo de `on_execution_end` no aumenta (el trabajo de sync/transición corre fuera del hilo de completación).
- **Cero tormenta:** N agentes que terminan casi juntos en un proyecto producen **<= 1 sync masivo por proyecto por ventana**, no N.

---

## 2. Por qué ahora / gap (anclado en código verificado)

Verifiqué cada archivo:línea releyendo el repo (no cito de memoria):

1. **Hoy NO existe auto-sync al completar.** Los únicos disparadores de `sync_tickets` son: (a) arranque, `backend/app.py:99` `_startup_sync` (que despacha por tracker con breaker: Jira `:116-138`, Mantis `:151`, ADO `:196-217`); y (b) manual, endpoint `POST /api/tickets/sync` en `backend/api/tickets.py:700` -> `_sync_via_provider_or_ado` (`backend/api/tickets.py:677`). No hay ningún gancho en el cierre de ejecución. Confirmado por grep de `sync_tickets(`/`on_execution_end`.

2. **El chokepoint universal de "un agente terminó" es `ticket_status.on_execution_end`, NO el gateway `run_on`.** Los 3 runners lo llaman **directamente**:
   - `backend/services/claude_code_cli_runner.py`: `:613,:1660,:1749,:1849,:1917,:1973,:2907,:2941`
   - `backend/services/codex_cli_runner.py`: `:358,:763`
   - `backend/agent_runner.py` (runtime in-proc / Copilot bridge): `:725,:1005,:1030,:1057`
   `run_on` (`backend/services/agent_completion.py:968`) se invoca **solo** desde el endpoint HTTP `backend/api/tickets.py:1580` (y `run_shadow` desde `:1553`). Además `run_on` **también** llama a `on_execution_end` (`backend/services/agent_completion.py:1200`). Conclusión dura: **enganchar R2/R3 al final de `run_on` perdería todas las completaciones directas de runner.** El punto correcto es `on_execution_end`, que ya tiene un **registro de post-hooks runtime-agnóstico** (`backend/services/ticket_status.py:307` `register_post_hook`, `:325` `_run_post_hooks` — captura excepciones, nunca bloquea) usado exactamente para esto en `backend/app.py:852-855` (`incident_autopublish.register(ticket_status.register_post_hook)` y `incident_dev_autocommit`).

3. **`on_execution_end` NO escribe estado ADO hoy.** `backend/services/ticket_status.py:231` solo hace `set_status(...)` (estado LOCAL `stacky_status`, `:270`) + post-hooks. No toca `System.State`. Por tanto R3 no colisiona con `on_execution_end`: son planos distintos (local vs remoto).

4. **La transición declarativa del gateway es un NO-OP permanente.** `backend/services/agent_completion.py:859` `_apply_workflow_transition` hace `from services import ado_workflow` dentro de `try/except ImportError` (`:875`), y **`backend/services/ado_workflow.py` NO EXISTE** (verificado por Glob vacío). Cae siempre en el `except ImportError` (`:895`) y loguea "ado_workflow not available — transition skipped". Es decir: el gateway declara una transición que nunca ocurre.

5. **La maquinaria de transición determinista YA existe y está probada, pero solo cableada en el path manual.** `backend/api/tickets.py:530` `_apply_task_state(*, ticket, agent_type, phase, correlation_id, publish_ok)` resuelve el estado con `resolve_task_state_plan` (`backend/harness/task_states.py:56`) y lo aplica con `_safe_transition` (`backend/harness/task_states.py:104`, **única** función que escribe estado: idempotente, tolerante a shape ADO/GitLab, nunca lanza). `_apply_task_state` se invoca **solo** en el path manual de finish (`backend/api/tickets.py:1381`). Resuelve el provider con `_provider_for_ticket` (`backend/api/tickets.py:408`). **Los paths de runner no llaman a `_apply_task_state` -> hoy una corrida de agente que termina por runner NO transiciona el estado ADO.** Ese es el vacío que R3 llena.

6. **La clave de R3 (`work_item_type`) ya está poblada y es columna real.** `sync_tickets` mapea `fields["System.WorkItemType"]` a `ticket.work_item_type` (`backend/services/ado_sync.py:136,:174,:205`; `upsert_single_work_item` `:271`). Es columna consultable (`backend/api/adoption.py:59,:229`). Valores ADO típicos: "Epic","Task","Issue","User Story","Bug","Product Backlog Item". Hay un validador canónico reutilizable: `validate_brief_work_item_type` (usado en `backend/api/agents.py:632-636`).

7. **El resolver R3 hoy solo indexa por `agent_type`.** `resolve_task_state_plan(profile, agent_type)` lee `profile["tracker_state_machine"][agent_type]` claves `in_progress`/`next_state_ok` (`backend/harness/task_states.py:56-71`). El conjunto cerrado aplicable está congelado en `_APPLICABLE_KEYS` (`:37`) y `applicable_states` (`:77`). Falta la dimensión `work_item_type`.

8. **El editor de la matriz ya existe en la UI.** `frontend/src/components/ClientProfileEditor.tsx` renderiza por rol el sub-componente `TrackerRoleField` (`:404-438`: `input_states`, `in_progress`, `blocked_state`, `next_state_ok`) y lo mapea por rol en `:999-1000` (`tracker_state_machine[role]`). Es el lugar exacto a extender. Los estados válidos ya se obtienen del tracker real vía `provider.fetch_states()` en el PUT del perfil (`backend/api/client_profile.py:230-235`, provider de `backend/services/tracker_provider.py:105` `get_tracker_provider`, protocolo con `fetch_states`/`update_item_state`/`get_item` en `:56-65`).

9. **El circuit breaker que R2 debe respetar ya existe (Plan 148).** `backend/services/integration_breaker.py`: `should_skip(integration, project)` `:79`, `record_failure` `:85`, `record_success` `:107`, `ado_breaker_project(project_name)` `:40` (deriva la parte "project" de la key — TODOS los productores/consumidores del breaker ADO deben usarla), `classify_ado_error` `:141`. Es exactamente el que usa `_startup_sync` y el sync manual (`backend/api/tickets.py:5739-5779`).

10. **Multi-tracker con misma firma.** `backend/services/ado_sync.py`, `backend/services/jira_sync.py`, `backend/services/mantis_sync.py` exponen `sync_tickets(...)`. `upsert_single_work_item` (`backend/services/ado_sync.py:235`) es el GET puntual barato. R2 debe resolver el sync correcto por tracker del proyecto, no cablear ADO duro.

**Gap en una frase:** el sistema tiene todas las piezas (post-hooks runtime-agnósticos, `sync_tickets`/`upsert_single`, `resolve_task_state_plan`/`_safe_transition`, breaker, editor de perfil, estados reales del tracker) pero **ninguna las conecta en el cierre de ejecución**; y la única dimensión de la matriz de estados es `agent_type`. Este plan las conecta con dos flags independientes y una dimensión nueva `work_item_type`, reutilizando todo, sin reinventar nada.

---

## 3. Principios y guardarraíles (codificados en las fases)

- **P1 — Un solo punto de integración runtime-agnóstico:** un único post-hook registrado en `ticket_status.register_post_hook`. Paridad de los 3 runtimes por construcción (todos llaman `on_execution_end`). Fallback declarado por runtime (§5, R-PARIDAD).
- **P2 — No bloqueante y best-effort:** el post-hook solo **encola** (O(1)) y retorna; un daemon de fondo hace el trabajo real (sync y transición). Una falla o lentitud **jamás** puede fallar ni demorar la completación ni la respuesta HTTP. Los post-hooks ya capturan toda excepción (`ticket_status.py:325`).
- **P3 — Coalescing / debounce:** N completaciones casi simultáneas en un proyecto producen **<= 1 sync masivo por proyecto por ventana T** (constante interna `_COALESCE_WINDOW_SEC = 30`, espejo del patrón de constantes internas del breaker `integration_breaker.py:22-23`). Más `upsert_single_work_item` inmediato del ticket puntual para reflejarlo ya.
- **P4 — Respeta el breaker existente:** antes de tocar la red, `integration_breaker.should_skip(...)`; registra `record_success`/`record_failure`. Reusa `ado_breaker_project` para la key.
- **P5 — Backward-compatible / matriz vacía = no-op:** con la matriz `by_work_item_type` vacía (default), R3 no aplica **ninguna** transición nueva en ningún path. Solo un cell configurado por el operador (acto HITL explícito) activa la transición en los paths de runner/gateway. Byte-comportamiento idéntico al de hoy hasta que el operador configure.
- **P6 — El estado lo decide el operador, nunca el LLM:** la transición sale de la matriz (config del cliente); el agente jamás propone el estado. Reusa el centinela de conjunto cerrado (`applicable_states`, `task_states.py:77`).
- **P7 — Estados reales, no alucinados:** los dropdowns de la UI se pueblan de `provider.fetch_states()` (tracker real) y de los `work_item_type` distintos ya sincronizados; nunca texto libre. Validación no bloqueante contra el tracker (`validate_states_against_tracker`, `task_states.py:171`).
- **P8 — Mono-operador sin auth:** nada de RBAC/multiusuario. La config va por el editor de perfil existente.
- **P9 — Reusar, no reinventar:** breaker (148), `task_states` (79), `_safe_transition`, `sync_tickets`/`upsert_single`, `get_tracker_provider`, `ClientProfileEditor`, `SystemLog`. Cero módulos nuevos salvo el dispatcher de completación y (opcional) el resolver de sync por tracker.
- **P10 — TDD y sin falsos verdes:** cada fase con su test nombrado, corrido por archivo con el venv del repo; el criterio de aceptación es binario y verificable por comando.
- **P11 — [ADICIÓN ARQUITECTO] No pisar la decisión humana:** R3 solo aplica `next_state_ok` si el ticket, en el tracker, sigue dentro del flujo esperado del rol (`input_states`/`in_progress`/`blocked_state`/`next_state_ok`, que el operador ya configura). Si el humano lo movió fuera a propósito, R3 hace skip `human_moved_out_of_flow`. La idempotencia "ya en target" NO alcanza: sin esto, un reintento/zombie re-empujaría un ticket que el humano devolvió a trabajo. Determinista, reusa el perfil, runtime-agnóstico, sin flag ni trabajo extra. Best-effort: si no se puede leer el estado, no bloquea.

---

## 4. Fases

> Orden de dependencia: **F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6**. F1 es puro y puede hacerse en paralelo a F0. F4 (UI) depende de F1 (schema). F2 y F3 dependen de F0 (dispatcher).

### Nomenclatura fija (usar EXACTAMENTE estos nombres)

- Flag R2: `STACKY_ADO_SYNC_ON_COMPLETION_ENABLED` (bool, default **True**, categoría `fiabilidad_ciclo_vida`).
- Flag R3: `STACKY_ADO_STATE_MATRIX_ENABLED` (bool, default **True**, categoría `flujo_funcional`).
- Módulo dispatcher: `backend/services/completion_dispatcher.py`.
- Módulo transición R3: `backend/services/completion_state.py`.
- Módulo sync R2: `backend/services/completion_sync.py`.
- Clave nueva del perfil: `tracker_state_machine.<agent_type>.by_work_item_type` (dict `{<WorkItemType>: {in_progress?, next_state_ok?}}`).
- Constante interna: `_COALESCE_WINDOW_SEC = 30` (en `completion_sync.py`).

---

### F0 — Flags + dispatcher de completación (infra compartida, no-op con flags off)

**Objetivo (1 frase):** crear el único punto de integración (post-hook + daemon de fondo) por el que pasarán R2 y R3, con ambas flags declaradas y default ON, sin cambiar comportamiento observable mientras nadie configure nada.

**Archivos a crear:**
- `backend/services/completion_dispatcher.py`

**Archivos a editar:**
- `backend/services/harness_flags.py` (FlagSpec x2 + `_CATEGORY_KEYS`)
- `backend/config.py` (2 atributos de `Config`)
- `backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON` += 2)
- `backend/app.py` (arrancar daemon + registrar post-hook en `create_app`)
- `backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES` += test nuevo)

**Contrato de `completion_dispatcher.py`:**
```python
# completion_dispatcher.py
import queue, threading, logging
logger = logging.getLogger("stacky_agents.completion_dispatcher")

# Evento mínimo (post-hook lo arma O(1), sin tocar DB):
#   {"ticket_id": int, "execution_id": int|None, "final_status": str, "agent_type": str|None}
_Q: "queue.Queue[dict]" = queue.Queue(maxsize=10000)
_started = False
_lock = threading.Lock()

def enqueue_completion(*, ticket_id, execution_id, final_status, agent_type=None) -> None:
    """O(1), nunca lanza, nunca bloquea. Se llama desde el post-hook."""
    try:
        # Gate hot: si ambas mitades están off, ni encolar.
        from services.completion_state import matrix_enabled
        from services.completion_sync import sync_on_completion_enabled
        if not (matrix_enabled() or sync_on_completion_enabled()):
            return
        _Q.put_nowait({"ticket_id": ticket_id, "execution_id": execution_id,
                       "final_status": final_status, "agent_type": agent_type})
    except queue.Full:
        logger.warning("completion_dispatcher: cola llena, evento descartado (best-effort)")
    except Exception:
        logger.debug("enqueue_completion falló (no crítico)", exc_info=True)

def _post_hook(*, ticket_id, execution_id, final_status, agent_type=None, error=None, **kwargs) -> None:
    enqueue_completion(ticket_id=ticket_id, execution_id=execution_id,
                       final_status=final_status, agent_type=agent_type)

def register(register_fn) -> None:
    """Espeja incident_autopublish.register: register_fn == ticket_status.register_post_hook."""
    register_fn(_post_hook)

def _drain_loop() -> None:
    from services.completion_state import maybe_apply_state_transition
    from services.completion_sync import maybe_coalesced_sync, flush_pending_syncs, coalesce_window_sec
    while True:
        try:
            try:
                ev = _Q.get(timeout=coalesce_window_sec())
            except queue.Empty:
                flush_pending_syncs()   # vencer ventana de coalescing sin segundo hilo
                continue
            # Orden: R3 (transiciona ADO) ANTES que R2 (pull ADO->local). C7: esto solo optimiza
            # el caso de sync INMEDIATO; bajo coalescing el sync puede diferirse a flush_pending_syncs,
            # y la convergencia es EVENTUAL igual (el próximo pull captura el System.State que R3 escribió).
            maybe_apply_state_transition(ev)   # gated por STACKY_ADO_STATE_MATRIX_ENABLED (no-op si off/sin matriz)
            maybe_coalesced_sync(ev)           # gated por STACKY_ADO_SYNC_ON_COMPLETION_ENABLED (coalesce por proyecto)
        except Exception:
            logger.debug("completion_dispatcher drain: iteración falló (no crítico)", exc_info=True)

def start(logger_=None) -> None:
    """Arranca el daemon una sola vez. Idempotente. Se llama en create_app."""
    global _started
    with _lock:
        if _started:
            return
        t = threading.Thread(target=_drain_loop, name="completion-dispatcher", daemon=True)
        t.start()
        _started = True
```
Notas de diseño:
- El daemon arranca **siempre** (barato: bloquea en `Queue.get`), así ambas flags son **hot** (sin `restart_required`). Con ambas off, `enqueue_completion` ni siquiera encola.
- `maybe_apply_state_transition` y `maybe_coalesced_sync` los definen F2 y F3; en F0 se crean como stubs no-op (`def maybe_...(ev): return None`) para que el daemon compile y el test de F0 pase con ambas mitades inertes.

**Wiring en `backend/app.py` (dentro de `create_app`, junto a `:852-855`):**
```python
from services import ticket_status, incident_autopublish, incident_dev_autocommit, completion_dispatcher
incident_autopublish.register(ticket_status.register_post_hook)
incident_dev_autocommit.register(ticket_status.register_post_hook)
# Plan 208 — auto-sync + matriz de estados al completar (runtime-agnóstico).
completion_dispatcher.register(ticket_status.register_post_hook)
completion_dispatcher.start(app.logger)
```

**Flags — `backend/services/harness_flags.py`:** agregar 2 `FlagSpec` a `FLAG_REGISTRY` (`:379`), espejando el estilo existente:
```python
FlagSpec(key="STACKY_ADO_SYNC_ON_COMPLETION_ENABLED", type="bool", group="global",
    label="Auto-sync ADO al completar",
    description="Al terminar cualquier agente, refresca los tickets del proyecto desde el tracker (pull read-only, coalescido, respeta el circuit breaker). Default ON.",
    default=True),
FlagSpec(key="STACKY_ADO_STATE_MATRIX_ENABLED", type="bool", group="global",
    label="Matriz de estados por tipo de ticket",
    description="Aplica el estado ADO configurado por (tipo de work item x tipo de agente) cuando el agente termina. No-op hasta que el operador configure la matriz en el perfil del proyecto. Default ON.",
    default=True),
```
Y agregar ambas keys a `_CATEGORY_KEYS` (`:117`): `STACKY_ADO_STATE_MATRIX_ENABLED` bajo `flujo_funcional` (`:238`), `STACKY_ADO_SYNC_ON_COMPLETION_ENABLED` bajo `fiabilidad_ciclo_vida`. (Sin categorizar, `test_every_registry_flag_is_categorized` queda rojo — ver memoria del ratchet.)

**Config — `backend/config.py`** (espejo de `STACKY_DETERMINISTIC_TASK_STATES_ENABLED:1192`):
```python
STACKY_ADO_SYNC_ON_COMPLETION_ENABLED: bool = os.getenv("STACKY_ADO_SYNC_ON_COMPLETION_ENABLED", "true").lower() in ("1","true","yes","on")
STACKY_ADO_STATE_MATRIX_ENABLED: bool = os.getenv("STACKY_ADO_STATE_MATRIX_ENABLED", "true").lower() in ("1","true","yes","on")
```
(Usar exactamente el mismo parser booleano que usan las otras flags bool de `config.py`; si el archivo ya tiene un helper `_env_bool`, usarlo — grep `_env_bool` en `config.py` antes de escribir.)

**`_CURATED_DEFAULTS_ON`** (`backend/tests/test_harness_flags.py`): agregar ambas keys al set (son bools default ON; sin esto `test_default_known_only_for_curated` queda rojo — ver memoria harness-flags-default-explicit).

**Tests (TDD) — crear `backend/tests/test_plan208_dispatcher.py`:**
- `test_flags_registradas_y_default_on`: ambas keys están en `FLAG_REGISTRY`, en `_CATEGORY_KEYS`, en `_CURATED_DEFAULTS_ON`, y `Config.STACKY_ADO_SYNC_ON_COMPLETION_ENABLED is True` / `..._MATRIX_ENABLED is True`.
- `test_enqueue_no_lanza_con_flags_off`: monkeypatch ambas a False -> `enqueue_completion(...)` no encola (cola vacía) y no lanza.
- `test_register_agrega_post_hook`: `register(fake_register)` invoca `fake_register` con un callable cuyo `__name__ == "_post_hook"`.
- `test_post_hook_encola_evento`: con una flag ON, `_post_hook(ticket_id=1, execution_id=2, final_status="completed", agent_type="developer")` deja 1 item en `_Q` con esos campos.
- `test_start_idempotente`: dos `start()` seguidos no arrancan 2 threads (contar por `threading.enumerate()` con name "completion-dispatcher").

**Comando exacto:** `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan208_dispatcher.py -q`
Registrar `test_plan208_dispatcher.py` en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh`).

**Criterio de aceptación (binario):** el comando de arriba pasa 5/5; `grep -n "completion_dispatcher.start" backend/app.py` devuelve >=1; `grep -c "STACKY_ADO_SYNC_ON_COMPLETION_ENABLED\|STACKY_ADO_STATE_MATRIX_ENABLED" backend/config.py` devuelve 2.

**Flag que protege:** las dos (ambas default ON; ver §5 R-EXCEPCION para la justificación de default ON de R3).
**Impacto por runtime:** ninguno directo en F0 (infra inerte). El post-hook queda registrado para los 3.
**Trabajo del operador:** ninguno.

---

### F1 — Resolver de matriz por (work_item_type x agent_type) con fallback (puro, TDD)

**Objetivo (1 frase):** extender `resolve_task_state_plan` para aceptar `work_item_type` y resolver el estado desde `by_work_item_type`, con fallback exacto al comportamiento actual y una fuente (`source`) que distinga matriz de legacy.

**Archivos a editar:**
- `backend/harness/task_states.py`

**Cambio de contrato (retrocompatible):**
```python
class TaskStatePlan(NamedTuple):
    in_progress: Optional[str]
    final_ok: Optional[str]
    source: str   # "matrix" | "config" | "absent" | "no_agent_type"  (NUEVO valor: "matrix")

def _normalize_wit(raw: Optional[str]) -> Optional[str]:
    """Normaliza un WorkItemType para lookup: strip; None/'' -> None. Case se compara aparte."""
    s = (raw or "").strip()
    return s or None

def _matrix_cell(machine: dict, work_item_type: Optional[str]) -> dict:
    """Devuelve by_work_item_type[<tipo>] con match case-insensitive; {} si no hay override."""
    wit = _normalize_wit(work_item_type)
    if not wit or not isinstance(machine, dict):
        return {}
    by = machine.get("by_work_item_type")
    if not isinstance(by, dict):
        return {}
    # match exacto primero; luego case-insensitive.
    if wit in by and isinstance(by[wit], dict):
        return by[wit]
    low = wit.casefold()
    for k, v in by.items():
        if isinstance(k, str) and k.strip().casefold() == low and isinstance(v, dict):
            return v
    return {}

def resolve_task_state_plan(profile: dict, agent_type: Optional[str],
                            work_item_type: Optional[str] = None) -> TaskStatePlan:
    """Fuente ÚNICA. Pura, nunca lanza. Retrocompatible: work_item_type=None => comportamiento actual.
    - Si hay override en by_work_item_type[<tipo>] con >=1 valor no vacío -> source="matrix".
    - Si no -> cae a machine.in_progress/next_state_ok (comportamiento actual) -> source="config"/"absent".
    """
    try:
        if not agent_type:
            return TaskStatePlan(None, None, "no_agent_type")
        m = _machine_for(profile, agent_type)
        cell = _matrix_cell(m, work_item_type)
        ip_m = (cell.get("in_progress") or "").strip() or None
        fk_m = (cell.get("next_state_ok") or "").strip() or None
        if ip_m is not None or fk_m is not None:
            return TaskStatePlan(ip_m, fk_m, "matrix")
        ip = (m.get("in_progress") or "").strip() or None
        fk = (m.get("next_state_ok") or "").strip() or None
        if ip is None and fk is None:
            return TaskStatePlan(None, None, "absent")
        return TaskStatePlan(ip, fk, "config")
    except Exception:
        logger.debug("resolve_task_state_plan falló (no crítico)", exc_info=True)
        return TaskStatePlan(None, None, "absent")
```
`applicable_states` (`:77`) queda igual (opera sobre el plan resuelto -> ya cubre el estado de la matriz). `_APPLICABLE_KEYS` (`:37`) queda igual (las claves internas del cell siguen siendo `in_progress`/`next_state_ok`).

**Casos borde a cubrir (todos en el test):**
- matriz vacía / sin `by_work_item_type` -> `source != "matrix"` (idéntico a hoy).
- `work_item_type=None` -> idéntico a hoy (los callers actuales, `tickets.py:541` y `task_states.py:160`, no rompen).
- `work_item_type="task"` vs key "Task" -> match case-insensitive -> `source="matrix"`.
- `work_item_type` desconocido ("Feature") sin cell -> fallback a agent-level (`source="config"`), no "matrix".
- cell presente pero vacío (`{"Task": {}}`) -> fallback a agent-level.
- cell solo con `in_progress` -> `final_ok=None`, `source="matrix"`.
- `agent_type=None` -> `no_agent_type`.
- profile no-dict / machine no-dict -> defensivo, no lanza.

**Tests (TDD) — crear `backend/tests/test_plan208_matrix_resolver.py`** con los 8 casos anteriores + un test parametrizado `test_backcompat_sin_work_item_type_identico` que compara el resultado sin `work_item_type` contra el resultado del comportamiento previo (mismos in_progress/final_ok para un profile legacy).

**Comando exacto:** `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan208_matrix_resolver.py -q`
Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación (binario):** el comando pasa (>=9 casos); `grep -n "by_work_item_type" backend/harness/task_states.py` devuelve >=1; los tests existentes de Plan 79 siguen verdes con el archivo REAL (C5): `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan79_resolver.py -q`.

**Flag:** ninguna (módulo puro; la aplicación se gatea en F2). **Impacto por runtime:** ninguno (puro). **Trabajo del operador:** ninguno.

---

### F2 — Aplicación determinista de la transición en el punto de completación (reusa `_safe_transition`)

**Objetivo (1 frase):** que cuando un agente termina OK, Stacky transicione el `System.State` del ticket al estado de la matriz — **solo** cuando el operador configuró el cell (`source=="matrix"`), reutilizando `_safe_transition`, sin bloquear la completación.

**Archivos a crear:**
- `backend/services/completion_state.py`

**Archivos a editar:**
- `backend/services/completion_dispatcher.py` (reemplazar el stub `maybe_apply_state_transition`)
- `backend/api/tickets.py` (`_apply_task_state`: hacerlo matrix-aware pasando `work_item_type`)

**Contrato de `completion_state.py`:**
```python
import logging
logger = logging.getLogger("stacky_agents.completion_state")

# C2 (RESUELTO — set exacto, NO "ajustar"): el final_status que llega al post-hook YA pasó por
# _coerce_terminal_status (ticket_status.py:268), que SOLO produce valores de
# status_vocabulary.VALID_TICKET_STATUSES = {idle, running, completed, error, cancelled, needs_review}.
# El ÚNICO terminal de éxito es "completed". PROHIBIDO incluir "needs_review" (exige revisión humana
# -> auto-transicionar violaría HITL) y "error"/"cancelled" (fallo).
from services.status_vocabulary import TERMINAL_STATUSES  # ancla/invariante: "completed" in TERMINAL_STATUSES
_OK_STATUSES = frozenset({"completed"})

def matrix_enabled() -> bool:
    # C1: leer la INSTANCIA config.config (NO el atributo de clase Config), igual que todo el repo
    # y el hermano 209. Con la clase, monkeypatch.setattr(config.config, ..., False) del test OFF-path
    # no voltea el branch -> falso verde.
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_ADO_STATE_MATRIX_ENABLED", False))
    except Exception:
        return False

def maybe_apply_state_transition(ev: dict) -> dict:
    """Aplica next_state_ok de la MATRIZ para (work_item_type x agent_type) si el operador lo configuró.
    Best-effort, idempotente, nunca lanza. Solo transiciona si:
      - flag ON
      - final_status es OK
      - resolve_task_state_plan(..., work_item_type).source == 'matrix' (backward-compat: sin matriz, no-op)
    """
    try:
        if not matrix_enabled():
            return {"skipped": True, "reason": "flag_off"}
        final_status = (ev.get("final_status") or "").strip().lower()
        if final_status not in _OK_STATUSES:
            return {"skipped": True, "reason": "not_ok_status"}
        ticket_id = ev.get("ticket_id")
        # Cargar ticket (project, ado_id, work_item_type, agent_type) en sesión propia.
        from db import session_scope           # grep import real de session_scope
        from models import Ticket
        with session_scope() as s:
            t = s.get(Ticket, ticket_id) if ticket_id else None
            if t is None:
                return {"skipped": True, "reason": "no_ticket"}
            ado_id = getattr(t, "ado_id", None)
            # C3: stacky_project_name (workspace Stacky) es la clave canónica para profile/provider/breaker.
            # NO caer a t.project (nombre del tracker): divergiría de _startup_sync (app.py:196,203).
            stacky_project = getattr(t, "stacky_project_name", None)
            work_item_type = getattr(t, "work_item_type", None)
        agent_type = ev.get("agent_type")
        if not ado_id or not stacky_project:
            return {"skipped": True, "reason": "no_ado_id_or_stacky_project"}
        from services.client_profile import load_effective_client_profile
        from harness.task_states import resolve_task_state_plan, applicable_states, _safe_transition
        profile = load_effective_client_profile(stacky_project) or {}
        plan = resolve_task_state_plan(profile, agent_type, work_item_type)
        if plan.source != "matrix":
            # Backward-compat DURA: sin cell configurado, los paths de runner NO transicionan.
            return {"skipped": True, "reason": "no_matrix_cell", "source": plan.source}
        target = plan.final_ok
        if not target or target not in applicable_states(plan):
            return {"skipped": True, "reason": "no_final_or_not_applicable"}
        from services.tracker_provider import get_tracker_provider
        try:
            provider = get_tracker_provider(stacky_project)
        except Exception:
            provider = None
        # [ADICIÓN ARQUITECTO] Guardia de origen esperado (anti-pisada del humano, P11): si el humano
        # movió el ticket, en el tracker, fuera del flujo esperado del rol, NO re-empujar next_state_ok.
        guard = _origin_guard(provider, ado_id, plan, profile, agent_type, target)
        if guard is not None:
            return guard
        return _safe_transition(provider, ado_id, target, phase="final_matrix",
                                legacy_client_fn=None)
    except Exception:
        logger.debug("maybe_apply_state_transition falló (no crítico)", exc_info=True)
        return {"skipped": True, "reason": "exception"}


def _origin_guard(provider, ado_id, plan, profile: dict, agent_type, target) -> dict | None:
    """[ADICIÓN ARQUITECTO / P11] Devuelve un dict-skip si el estado ACTUAL en el tracker cayó
    FUERA del flujo esperado del rol (el humano lo movió a propósito) -> no pisar. Devuelve None
    para 'seguir' (deja que _safe_transition haga su idempotencia habitual). Best-effort: si no se
    puede leer el estado, NO bloquea (return None). Reusa _extract_current_state de task_states."""
    try:
        if provider is None or not hasattr(provider, "get_item"):
            return None  # sin lectura -> no bloqueamos; _safe_transition decide
        from harness.task_states import _extract_current_state
        current = _extract_current_state(provider.get_item(str(ado_id)) or {})
        if not current:
            return None
        cl = current.strip().lower()
        if cl == (target or "").strip().lower():
            return None  # ya está en target: idempotencia la maneja _safe_transition
        # Estados de origen legítimos = los que el propio flujo produce/espera para el rol.
        machine = (profile.get("tracker_state_machine") or {}).get(agent_type) or {}
        expected = set()
        for k in ("in_progress", "blocked_state", "next_state_ok"):
            v = (machine.get(k) or "").strip()
            if v:
                expected.add(v.lower())
        for st in (machine.get("input_states") or []):
            if isinstance(st, str) and st.strip():
                expected.add(st.strip().lower())
        if expected and cl not in expected:
            return {"skipped": True, "reason": "human_moved_out_of_flow", "current": current, "to": target}
        return None
    except Exception:
        logger.debug("_origin_guard falló (no crítico) -> no bloquea", exc_info=True)
        return None
```
Notas:
- **No bloquea la completación:** corre en el hilo del daemon, no en el de `on_execution_end`.
- **Idempotente:** `_safe_transition` lee el estado actual y hace skip si ya está en target (`task_states.py:121-126`).
- **`get_tracker_provider` None-safe:** si el provider no se resuelve, `_safe_transition` con `provider=None` y sin `legacy_client_fn` devuelve `{"skipped": ..., "reason": "no_provider"}` (`task_states.py:135`). Documentar que para ADO conviene pasar `legacy_client_fn` si el provider ADO no está disponible; para v1, `get_tracker_provider` cubre ADO/GitLab (`tracker_provider.py:118-120`).
- **`_OK_STATUSES` (RESUELTO, no "ajustar"):** el `final_status` del post-hook ya está coercionado por `_coerce_terminal_status` (`ticket_status.py:268`) al vocabulario `status_vocabulary.VALID_TICKET_STATUSES = {idle,running,completed,error,cancelled,needs_review}`. El único terminal de éxito es **"completed"** -> `_OK_STATUSES = frozenset({"completed"})`, importando `TERMINAL_STATUSES` del vocabulario canónico como ancla. **Prohibido** incluir `needs_review` (requiere revisión humana; auto-transicionar violaría HITL) o `error`/`cancelled` (fallo).
- **Guardia de origen (`_origin_guard`, [ADICIÓN ARQUITECTO] / P11):** corre entre la resolución del plan y `_safe_transition`. Lee el estado actual del tracker (reusa `_extract_current_state`) y, si cayó fuera de `{input_states, in_progress, blocked_state, next_state_ok}` del rol (el humano lo movió), hace skip `human_moved_out_of_flow`. Trade-off honesto: en el peor caso son 2 GET (`_origin_guard` + la idempotencia de `_safe_transition`); es daemon best-effort y solo con cell configurado (path raro, nunca en el hilo de completación). Follow-up opcional (fuera de v1): pasar `expected_from` a `_safe_transition` para un único GET.

**Edit en `_apply_task_state` (`backend/api/tickets.py:530`)** — hacerlo matrix-aware sin cambiar su comportamiento legacy:
```python
plan = resolve_task_state_plan(profile, agent_type, getattr(ticket, "work_item_type", None))
```
(Con esto el path manual de finish ya respeta la matriz cuando hay cell; si no, sigue usando el agent-level de hoy. No se toca el resto de `_apply_task_state`.)

**Casos borde (todos en el test):** flag off; status de fallo (no transiciona); `needs_review` (no transiciona — exige humano, C2); ticket sin `ado_id`; ticket sin `stacky_project_name`; `source != "matrix"` (no-op); target fuera de `applicable_states` (skip por centinela); provider None (skip `no_provider`); estado ya == target (skip `already_in_state`); **estado movido por el humano fuera del flujo (skip `human_moved_out_of_flow`, P11);** shadow mode (ver nota abajo).

**Paridad shadow:** `run_shadow` (`agent_completion.py:473`) NO llama `on_execution_end` (solo simula/lee) -> **no encola eventos** -> R3 no transiciona en shadow. Correcto y sin trabajo extra: el modo simulación no muta ADO. Documentar como test `test_shadow_no_transiciona` (invocar `run_shadow` con mocks y verificar que `_Q` queda vacío / `maybe_apply_state_transition` no se llama).

**Tests (TDD) — crear `backend/tests/test_plan208_state_transition.py`** con provider fake (implementa `get_item`/`update_item_state`/`name`) y `resolve_task_state_plan` real:
- transiciona a `next_state_ok` de la matriz cuando cell configurado + status OK (estado actual dentro del flujo).
- no-op cuando `source != "matrix"` (solo agent-level configurado).
- idempotente (segundo llamado -> skip `already_in_state`).
- flag off -> skip (con `monkeypatch.setattr(config.config, "STACKY_ADO_STATE_MATRIX_ENABLED", False)` — C1: sobre la INSTANCIA).
- status de fallo -> skip; `test_needs_review_no_transiciona` (C2): `final_status="needs_review"` -> skip `not_ok_status`.
- provider None -> skip `no_provider`.
- **[ADICIÓN ARQUITECTO]** `test_no_pisa_estado_movido_por_humano` (P11): cell configurado + status OK, pero `get_item` devuelve un estado FUERA de `input_states/in_progress/blocked_state/next_state_ok` (p.ej. "On Hold") -> skip `human_moved_out_of_flow` y `update_item_state` NO se llama.

**Comando exacto:** `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan208_state_transition.py -q`
Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación (binario):** el comando pasa; `grep -n "maybe_apply_state_transition" backend/services/completion_dispatcher.py backend/services/completion_state.py` devuelve >=2; un smoke con provider fake muestra `update_item_state` llamado exactamente 1 vez para cell configurado y 0 veces sin cell.

**Flag:** `STACKY_ADO_STATE_MATRIX_ENABLED` (default ON; no-op sin matriz — ver §5 R-EXCEPCION). **Impacto por runtime:** los 3 (todos pasan por `on_execution_end` -> dispatcher). **Fallback por runtime:** ver §5 R-PARIDAD. **Trabajo del operador:** opt-in (default ON; configura la matriz por UI en F4 cuando quiera; sin config, cero transiciones nuevas).

---

### F3 — Auto-sync best-effort, no bloqueante, coalescido, con breaker (R2)

**Objetivo (1 frase):** que al terminar un agente se refresquen los tickets del proyecto desde el tracker, coalescido por proyecto, respetando el breaker, sin bloquear ni demorar la completación.

**Archivos a crear:**
- `backend/services/completion_sync.py`

**Archivos a editar:**
- `backend/services/completion_dispatcher.py` (reemplazar stubs `maybe_coalesced_sync`, `flush_pending_syncs`, `coalesce_window_sec`)

**Contrato de `completion_sync.py`:**
```python
import time, logging, threading
logger = logging.getLogger("stacky_agents.completion_sync")

_COALESCE_WINDOW_SEC = 30            # constante interna (espejo integration_breaker._BACKOFF_BASE_SEC)
_last_sync_ts: dict[str, float] = {} # project -> epoch del último sync masivo
_pending: dict[str, dict] = {}       # project -> último evento visto en la ventana (para flush)
_mutex = threading.Lock()

def sync_on_completion_enabled() -> bool:
    # C1: INSTANCIA config.config, no el atributo de clase (ver F2/matrix_enabled y gotcha config.config).
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_ADO_SYNC_ON_COMPLETION_ENABLED", False))
    except Exception:
        return False

def coalesce_window_sec() -> float:
    return float(_COALESCE_WINDOW_SEC)

def _resolve_sync_and_project(ticket) -> tuple:
    """Devuelve (sync_callable, project_name, tracker_type). project_name es SIEMPRE el
    stacky_project_name (workspace Stacky): clave canónica de breaker/cliente, coherente con
    _startup_sync (app.py:196,203). Multi-tracker: azure_devops -> ado_sync.sync_tickets ;
    jira -> jira_sync.sync_tickets ; mantis -> mantis_sync.sync_tickets. Fallback: azure_devops."""
    tracker_type = (getattr(ticket, "tracker_type", None) or "azure_devops").strip().lower()
    # C3: NO caer a ticket.project (nombre del tracker) -> divergiría la key del breaker.
    project = getattr(ticket, "stacky_project_name", None)
    if tracker_type == "jira":
        from services.jira_sync import sync_tickets as fn
    elif tracker_type == "mantis":
        from services.mantis_sync import sync_tickets as fn
    else:
        from services.ado_sync import sync_tickets as fn
    return fn, project, tracker_type

def _do_project_sync(project: str, tracker_type: str, ado_id=None) -> None:
    """Sync masivo + upsert puntual. Respeta breaker. Best-effort, nunca lanza."""
    from services import integration_breaker as brk
    integ = "ado_sync" if tracker_type == "azure_devops" else f"{tracker_type}_sync"
    bkey = brk.ado_breaker_project(project) if tracker_type == "azure_devops" else project
    if brk.should_skip(integ, bkey):
        logger.debug("completion_sync: breaker abierto para %s/%s, skip", integ, bkey)
        return
    try:
        if tracker_type == "azure_devops":
            from services.ado_sync import sync_tickets, upsert_single_work_item
            # C4: construir el cliente desde services (NO importar api.tickets: acopla service->api y
            # arriesga import circular al arrancar el daemon). build_ado_client(project_name=<stacky>) es
            # la firma canónica (project_context.py:208), ya usada así en _startup_sync (app.py:203).
            from services.project_context import build_ado_client
            client = build_ado_client(project_name=project)
            if ado_id:
                try: upsert_single_work_item(client, int(ado_id))   # refleja el ticket puntual YA
                except Exception: logger.debug("upsert_single best-effort falló", exc_info=True)
            sync_tickets(client=client, project_name=project)
        else:
            from importlib import import_module
            import_module(f"services.{tracker_type}_sync").sync_tickets(project_name=project)
        brk.record_success(integ, bkey)
        _last_sync_ts[project] = time.time()
    except Exception as exc:
        try:
            from services.integration_breaker import classify_ado_error
            reason, message = classify_ado_error(exc) if tracker_type == "azure_devops" else ("unknown", str(exc)[:200])
            brk.record_failure(integ, bkey, reason, message)
        except Exception:
            logger.debug("record_failure falló", exc_info=True)
        logger.warning("completion_sync: sync de %s falló (best-effort): %s", project, exc)

def maybe_coalesced_sync(ev: dict) -> None:
    """Coalesce por proyecto: sync inmediato si pasó la ventana desde el último; si no, marca pending."""
    if not sync_on_completion_enabled():
        return
    try:
        from db import session_scope
        from models import Ticket
        ticket_id = ev.get("ticket_id")
        with session_scope() as s:
            t = s.get(Ticket, ticket_id) if ticket_id else None
            if t is None:
                return
            _, project, tracker_type = _resolve_sync_and_project(t)
            ado_id = getattr(t, "ado_id", None)
        if not project:
            return
        now = time.time()
        with _mutex:
            last = _last_sync_ts.get(project, 0.0)
            if now - last >= _COALESCE_WINDOW_SEC:
                _pending.pop(project, None)
                do_now = True
            else:
                _pending[project] = {"tracker_type": tracker_type, "ado_id": ado_id}
                do_now = False
        if do_now:
            _do_project_sync(project, tracker_type, ado_id)
    except Exception:
        logger.debug("maybe_coalesced_sync falló (no crítico)", exc_info=True)

def flush_pending_syncs() -> None:
    """Se llama cuando la cola queda vacía por >= ventana: drena proyectos pendientes (1 sync c/u)."""
    if not sync_on_completion_enabled():
        with _mutex: _pending.clear()
        return
    with _mutex:
        items = list(_pending.items()); _pending.clear()
    for project, meta in items:
        _do_project_sync(project, meta.get("tracker_type", "azure_devops"), meta.get("ado_id"))
```
Notas:
- **No bloqueante:** todo corre en el hilo del daemon; la completación solo hizo `put_nowait`.
- **Coalescing real:** primer evento de un proyecto sincroniza y sella `_last_sync_ts`; eventos dentro de la ventana solo marcan `_pending`; al vaciarse la cola por >= ventana, `flush_pending_syncs` hace **1** sync por proyecto pendiente. N completaciones -> <= 2 syncs por proyecto por ventana (1 inmediato + 1 flush), no N.
- **Breaker:** `should_skip` antes de la red; `record_success`/`record_failure` con la MISMA key (`ado_breaker_project`) que `_startup_sync` y el sync manual, para que las ventanas de backoff coincidan.
- **Cliente ADO (RESUELTO, C4):** usar SIEMPRE `from services.project_context import build_ado_client; client = build_ado_client(project_name=<stacky_project>)` (`project_context.py:208`, ya usado por `_startup_sync` en `app.py:203`). NO importar `api.tickets._ado_client_for_ticket` desde un service (acople service->api + riesgo de import circular al arrancar el daemon). `sync_tickets(client=None, project_name=<stacky>)` también construye el cliente solo (`ado_sync.py:108-112`), pero para `upsert_single_work_item(client, ado_id)` necesitamos el `client` explícito.

**Casos borde (todos en el test):** flag off (no sync); breaker abierto (skip sin tocar red); 5 eventos del mismo proyecto en < ventana -> 1 sola llamada a `sync_tickets` inmediata + a lo sumo 1 en flush; proyecto None (skip); tracker jira/mantis (despacha al sync correcto); excepción de `sync_tickets` -> `record_failure` llamado, no propaga.

**Tests (TDD) — crear `backend/tests/test_plan208_auto_sync.py`** con `sync_tickets`/`upsert_single_work_item`/breaker mockeados:
- `test_flag_off_no_sync`; `test_breaker_abierto_skip`; `test_coalescing_una_sola_llamada`; `test_multitracker_despacha_jira`; `test_falla_registra_breaker_no_propaga`; `test_upsert_single_se_invoca_para_ado`.

**Comando exacto:** `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan208_auto_sync.py -q`
Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación (binario):** el comando pasa; con 5 eventos simulados del mismo proyecto en < 30 s, el mock de `sync_tickets` se llamó **1** vez (no 5); con breaker abierto, `sync_tickets` se llamó 0 veces.

**Flag:** `STACKY_ADO_SYNC_ON_COMPLETION_ENABLED` (default ON; ver §5 R-EXCEPCION: pull read-only, no dispara ninguna excepción dura). **Impacto por runtime:** los 3. **Fallback:** el `_startup_sync` y el sync manual siguen como red de seguridad. **Trabajo del operador:** ninguno (invisible y automático).

---

### F4 — Editor de la matriz en la UI + validación de esquema (regla dura: config por UI)

**Objetivo (1 frase):** que el operador configure `by_work_item_type` desde el editor de perfil existente, con estados poblados por `fetch_states()` y tipos de work item poblados por datos reales, y que el backend valide/persista el esquema nuevo.

**Archivos a editar (backend):**
- `backend/services/client_profile.py` (`_check_tracker_state_machine:144` — aceptar/validar `by_work_item_type`)
- `backend/harness/task_states.py` (`validate_states_against_tracker:171` — incluir estados de `by_work_item_type` en la validación no bloqueante)
- `backend/api/client_profile.py` (exponer al GET los `work_item_type` distintos del proyecto para poblar el selector — ver abajo)

**Archivos a editar (frontend):**
- `frontend/src/components/ClientProfileEditor.tsx` (`TrackerRoleField:404-438` — agregar sección "Estados por tipo de ticket")
- `frontend/src/types.ts` (tipo del profile: agregar `by_work_item_type?`)

**Esquema nuevo (retrocompatible) del perfil:**
```json
"tracker_state_machine": {
  "developer": {
    "input_states": ["Ready for Dev"],
    "in_progress": "In Progress",
    "blocked_state": "Blocked",
    "next_state_ok": "Code Review",
    "by_work_item_type": {
      "Epic":  { "in_progress": "Active",      "next_state_ok": "Resolved" },
      "Task":  { "in_progress": "In Progress", "next_state_ok": "Code Review" },
      "Issue": { "in_progress": "Active",      "next_state_ok": "Ready for QA" }
    }
  }
}
```

**Validación backend — `_check_tracker_state_machine` (`client_profile.py:144`):** agregar, sin romper lo existente:
- si `by_work_item_type` presente: debe ser dict; cada valor dict; cada `in_progress`/`next_state_ok` (si presentes) string. Errores -> `errors` (bloqueantes). Tipos no en el tracker -> `warnings` (no bloqueantes, vía `validate_states_against_tracker`).
- `validate_states_against_tracker` (`task_states.py:171`): además de `in_progress`/`next_state_ok` a nivel agente, recorrer `by_work_item_type[*].{in_progress,next_state_ok}` y emitir warnings `state_not_in_tracker` para valores que no estén en `valid_states` (poblados de `fetch_states()` como ya hace `client_profile.py:234`).

**Fuente de tipos para el selector (sin alucinar):** en `GET /api/projects/<name>/client-profile` (`api/client_profile.py:114`), agregar al JSON `"work_item_types"`: unión de (a) los `work_item_type` distintos ya sincronizados para el proyecto (query `Ticket.work_item_type` distinct filtrado por `stacky_project_name`, patrón de `api/adoption.py:229`) y (b) el set canónico ADO (`["Epic","Task","Issue","User Story","Bug","Product Backlog Item"]`; reutilizar el que valida `validate_brief_work_item_type`, grep en `api/tickets.py`). El frontend usa esa lista para el selector de tipo; los estados salen de `fetch_states()` (agregar `"valid_states"` al mismo GET si no está ya, reutilizando `get_tracker_provider(project).fetch_states()`).

**UI — `TrackerRoleField` (`ClientProfileEditor.tsx:404-438`):** debajo de los campos actuales, agregar un bloque plegable "Estados por tipo de ticket (opcional)":
- Un selector para elegir un `work_item_type` (de `work_item_types` del GET) y un botón "Agregar tipo" que crea la entrada en `value.by_work_item_type[<tipo>]`.
- Por cada tipo agregado, dos dropdowns (`in_progress`, `next_state_ok`) poblados por `valid_states` (nunca `<input>` de texto libre) + un botón "Quitar".
- `onChange` mergea en `value.by_work_item_type` respetando el riel GET->merge->PUT existente (`ClientProfileEditor` ya persiste por `PUT /api/projects/<name>/client-profile`, `api/client_profile.py:147`). Human-in-the-loop: nada se guarda hasta que el operador aprieta guardar.
- Copy: "Vacío = usar el estado general del rol. Configurá solo los tipos que quieras tratar distinto."

**Tests (TDD):**
- Backend `backend/tests/test_plan208_profile_schema.py`: `test_valida_by_work_item_type_ok`; `test_rechaza_by_work_item_type_no_dict`; `test_warning_estado_fuera_de_tracker`; `test_get_devuelve_work_item_types_y_valid_states`. Comando: `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan208_profile_schema.py -q`. Registrar en `HARNESS_TEST_FILES`.
- Frontend: si el repo tiene vitest para componentes (grep `vitest` en `frontend/package.json`; ver memoria RTL/jsdom gap), agregar `frontend/src/components/__tests__/ClientProfileEditor.matrix.test.tsx`; **si RTL/jsdom no están instalados, NO inventar el harness** — el gate frontend es `tsc --noEmit` + smoke manual (documentarlo como en planes UX previos). Criterio: `cd "Stacky Agents/frontend" && npx tsc --noEmit` sin errores nuevos.

**Criterio de aceptación (binario):** test backend pasa; `grep -n "by_work_item_type" frontend/src/components/ClientProfileEditor.tsx` >=1; `tsc --noEmit` verde; un PUT con `by_work_item_type` válido persiste y reaparece en el GET.

**Flag:** `STACKY_ADO_STATE_MATRIX_ENABLED` (la matriz se lee siempre; su aplicación se gatea en F2). **Impacto por runtime:** N/A (config). **Trabajo del operador:** opt-in — configura los tipos que quiera; el resto sigue con el estado general del rol.

---

### F5 — Validación de estados contra el tracker + centinela anti-alucinación

**Objetivo (1 frase):** garantizar que ningún estado aplicado provenga de fuera de la matriz configurada por el operador y advertir (sin bloquear) cuando un estado no existe en el tracker.

**Archivos a editar:**
- `backend/harness/task_states.py` (ya cubierto por `applicable_states` — agregar test de centinela para la ruta matriz)
- (validación de warnings ya extendida en F4)

**Centinela (ya existe por construcción):** `maybe_apply_state_transition` (F2) exige `target in applicable_states(plan)` antes de `_safe_transition`; y `_safe_transition` no aplica estados fuera del target. Como el `plan` con `source=="matrix"` deriva `final_ok` **solo** de `by_work_item_type[<tipo>].next_state_ok`, es imposible aplicar un estado que el operador no puso en la matriz. F5 lo blinda con tests explícitos y con la validación de F4.

**Tests (TDD) — agregar a `backend/tests/test_plan208_state_transition.py`:**
- `test_centinela_estado_fuera_de_matriz_no_se_aplica`: inyectar un `resolve_task_state_plan` que devuelva un target que no esté en `applicable_states` (construyendo un plan inconsistente) -> `_safe_transition` no se llama / skip `state_not_applicable`.
- `test_validacion_marca_estado_inexistente`: `validate_states_against_tracker(profile_con_matriz, valid_states)` incluye el warning `state_not_in_tracker` para un estado de `by_work_item_type` ausente en `valid_states`.

**Criterio de aceptación (binario):** ambos tests verdes; grep `applicable_states` en `completion_state.py` >=1 (el centinela está en la ruta caliente).

**Flag:** `STACKY_ADO_STATE_MATRIX_ENABLED`. **Trabajo del operador:** ninguno.

---

### F6 — Observabilidad y telemetría (reusa SystemLog)

**Objetivo (1 frase):** dejar traza auditable de cada auto-sync y cada transición de matriz, sin nuevas tablas.

**Archivos a editar:**
- `backend/services/completion_state.py` y `backend/services/completion_sync.py` (emitir `SystemLog`)

**Qué loguear (reusar el emisor de SystemLog que usan estos flujos; grep `SystemLog` / `_emit_system_log` en `services/agent_completion.py:1240` como patrón):**
- R3: `action="completion.matrix_transition"`, context `{ado_id, project, work_item_type, agent_type, target, result: ok|skipped|error, reason, source}`. **C6:** `source` = `plan.source` (="matrix"), NUNCA el `source` del dict de `_safe_transition` (hardcodeado a "config" en `task_states.py:136`). El `reason` incluye el nuevo `human_moved_out_of_flow` de la guardia de origen (P11). tags `["plan208","matrix"]`.
- R2: `action="completion.auto_sync"`, context `{project, tracker_type, coalesced: bool, breaker_open: bool, fetched, created, updated, removed}`, tags `["plan208","auto_sync"]`.
- Nivel INFO en éxito/skip esperado; WARNING en fallo de red/transición.

**Tests (TDD) — `backend/tests/test_plan208_observability.py`:** con SystemLog mockeado/capturado, verificar que una transición aplicada emite `completion.matrix_transition` con `result="ok"` y que un sync coalescido emite `completion.auto_sync`. Comando: `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_plan208_observability.py -q`. Registrar en `HARNESS_TEST_FILES`.

**Criterio de aceptación (binario):** el comando pasa; los dos `action` aparecen en los logs capturados.

**Flag:** ambas. **Trabajo del operador:** ninguno (telemetría visible en el Centro de Notificaciones/Actividad existente).

---

## 5. Riesgos y mitigaciones

- **R-TORMENTA (tormenta de syncs).** N agentes terminan juntos -> N syncs masivos. *Mitigación:* coalescing por proyecto con `_COALESCE_WINDOW_SEC` (F3): <= 1 sync inmediato + <= 1 flush por proyecto por ventana. Test `test_coalescing_una_sola_llamada`. Además `upsert_single_work_item` refleja el ticket puntual sin esperar el masivo.
- **R-BLOQUEO (degradar latencia de completación).** *Mitigación:* el post-hook solo `put_nowait` (O(1)); todo el trabajo corre en el daemon. Los post-hooks capturan excepciones (`ticket_status.py:325`). Test: el post-hook no llama red.
- **R-ESTADO-INCORRECTO (transición a estado equivocado).** *Mitigación:* estado sale **solo** de la matriz del operador (`source=="matrix"`), centinela `applicable_states` (F5), idempotencia de `_safe_transition`, validación no bloqueante contra `fetch_states` (F4), y dropdowns sin texto libre. El operador elige estados conservadores (ej. "Ready for QA", no "Closed").
- **R-COLISION-on_execution_end.** No hay colisión: `on_execution_end` escribe estado **local** (`set_status`), R3 escribe estado **remoto** (System.State). Planos distintos.
- **R-COLISION-ado_workflow (no-op).** `_apply_workflow_transition` (`agent_completion.py:859`) seguirá siendo no-op (no existe `ado_workflow.py`). **Decisión explícita: NO materializar `ado_workflow.py`** para no crear un segundo mecanismo de transición que compita con `task_states`/matriz. R3 usa exclusivamente `resolve_task_state_plan` + `_safe_transition`. (Opcional de higiene, fuera de scope: bajar el log de `:898` a DEBUG para no ensuciar; no es necesario.)
- **R-DOBLE-TRANSICION (manual + post-hook).** En una completación manual, `_apply_task_state(final)` (`tickets.py:1381`) y el post-hook de F2 podrían transicionar ambos. *Mitigación:* `_safe_transition` es idempotente (skip si ya está en target); el segundo es no-op. Documentado y testeado.
- **R-IDEMPOTENCIA-REINTENTOS/ZOMBIES.** Reintentos de completación o ejecuciones zombie que re-disparan `on_execution_end` -> múltiples eventos. *Mitigación:* transición idempotente + sync coalescido; el peor caso es un sync extra dentro de la ventana. No hay efecto acumulativo.
- **R-PISADA-HUMANA ([ADICIÓN ARQUITECTO] / P11).** Un reintento/zombie que re-dispara `on_execution_end` podría re-empujar `next_state_ok` DESPUÉS de que el humano movió el ticket a otro estado a propósito (p.ej. lo devolvió a "In Progress" tras un `needs_review`). La idempotencia sola NO cubría esto (solo "ya en target"). *Mitigación:* `_origin_guard` (F2) hace skip `human_moved_out_of_flow` si el estado actual del tracker cayó fuera del flujo esperado del rol (`input_states/in_progress/blocked_state/next_state_ok`). Best-effort: si no se puede leer el estado, no bloquea (delega en `_safe_transition`). Reusa datos del perfil que el operador ya llena; determinista; runtime-agnóstico. Test `test_no_pisa_estado_movido_por_humano`.
- **R-BREAKER.** Si ADO está caído, no golpear la red en loop. *Mitigación:* `should_skip` antes de cada intento, con la MISMA key (`ado_breaker_project`) que los otros consumidores, respetando el backoff exponencial existente.
- **R-PARIDAD (3 runtimes).** Los 3 runners llaman `on_execution_end` directamente (evidencia en §2.2), y `run_on` también. *Fallback por runtime:* si un runtime futuro completara sin llamar `on_execution_end`, R2/R3 no se dispararían para él; la red de seguridad es (a) el `_startup_sync` periódico para R2, y (b) el path manual `_apply_task_state`/`finish-work` para R3. Documentar que **todo runtime nuevo debe llamar `ticket_status.on_execution_end` al terminar** (ya es la convención; ver `docs/25_CHECKLIST_NUEVO_RUNTIME.md`). Shadow mode no dispara nada (no llama `on_execution_end`).
- **R-EXCEPCION (¿default ON viola alguna de las 4 excepciones duras?).** Análisis riguroso, no cosmético:
  - **R2 (auto-sync): default ON, sin reservas.** Es un **PULL read-only** de ADO -> DB local (`sync_tickets`/`upsert_single` GET+upsert; `ado_sync.py:102,:235`). No escribe en ADO, no bypassa revisión humana, no es destructivo (los tickets con ejecuciones nunca se borran, `ado_sync.py:105-106`), no baja seguridad, no requiere prerequisito nuevo, no quema tokens ociosos (no invoca LLM). No dispara ninguna de las 4 excepciones. Default ON correcto.
  - **R3 (matriz): default ON, defendible por inercia + HITL explícito.** Escribir `System.State` en ADO **es** una mutación externa. ¿Es "bypass de revisión humana"? **No**, y esta es la clave: (1) la matriz está **vacía por default** y el post-hook exige `source=="matrix"` -> **con la config default no ocurre ninguna transición nueva en ningún path** (backward-compat dura, P5); (2) cuando el operador llena un cell, está **pre-autorizando explícitamente** (acto HITL en la UI) qué estado usar por (tipo x agente) — la transición es amplificación **determinista** de su intención declarada, no una decisión del LLM (P6); (3) hay **precedente default-ON** para escrituras deterministas de estado ADO: `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` ya es default ON (`config.py:1192`) y ya escribe `System.State` vía `_apply_task_state` en el path manual. R3 extiende ese mecanismo ya-default-ON agregando la dimensión `work_item_type` y cerrando la asimetría (runner no transicionaba). El operador elige estados conservadores; el centinela impide estados fuera de la matriz. **Conclusión:** default ON no matchea ninguna de las 4 excepciones **porque el flag ON no es la mutación** — la mutación la habilita el operador al configurar la matriz. Si un revisor insistiera en gate, el candidato sería "bypass de revisión humana", pero se refuta con P5+P6 (no hay bypass: hay pre-autorización explícita y no hay agente decidiendo). Se documenta el matiz honesto: el comportamiento nuevo (transicionar en paths de runner) se activa **solo** con la dimensión de matriz configurada, no con el legacy agent-level, para no cambiar el comportamiento de proyectos que hoy tienen `next_state_ok` a nivel rol. **La solidez de este default ON depende de dos guardas incorporadas en v2:** (a) C2 — `_OK_STATUSES == {"completed"}`, que EXCLUYE `needs_review` (jamás se auto-transiciona un ticket que pide revisión humana); (b) P11 — la guardia de origen, que no pisa un estado que el humano movió a propósito. Sin C2+P11 el default ON sí tendría una arista HITL; con ellas, la mutación externa queda estrictamente acotada a la intención declarada del operador.

---

## 6. Fuera de scope

- Estado ADO en **fallo** (transición a un "error/blocked state" cuando el agente falla). v1 solo transiciona en éxito; `blocked_state` es acción humana (comentario en `task_states.py:38-39`). Se puede sumar después como `by_work_item_type[*].next_state_fail`.
- Materializar `services/ado_workflow.py` (rechazado explícitamente, R-COLISION-ado_workflow).
- Sync de trackers no-ADO no soportados aún por el path provider (`_sync_via_provider_or_ado` lanza `NotImplementedError` para GitLab, `tickets.py:692`). R2 usa el `sync_tickets` por tracker (ADO/Jira/Mantis) que ya existe; GitLab queda como estaba (Plan 71).
- Webhooks ADO -> Stacky (push en vez de pull). Este plan es pull disparado por completación.
- Cambiar la ventana de coalescing por UI (queda como constante interna; se puede promover a flag int con bounds después — ver memoria `_FROZEN_BOUNDS`).
- Plan hermano **209** (guía de validación al operador) — lo escribe otro arquitecto.

---

## 7. Glosario, orden de implementación y DoD

### Glosario (términos Stacky)
- **work item / ticket:** ítem del tracker (Epic/Task/Issue/...). Su tipo vive en `ticket.work_item_type` (de `System.WorkItemType`).
- **tracker_state_machine:** sub-objeto del `client_profile` por rol/agente con `input_states`/`in_progress`/`blocked_state`/`next_state_ok` (+ nuevo `by_work_item_type`).
- **gateway de completación:** `run_on`/`run_shadow` (`agent_completion.py`), el path HTTP de cierre. **No** es el único punto de completación: los runners cierran llamando `on_execution_end` directo.
- **on_execution_end:** hook post-ejecución runtime-agnóstico (`ticket_status.py:231`) con `register_post_hook`. Punto de integración de este plan.
- **provider:** adaptador de tracker (`TrackerProvider`, `tracker_provider.py:56`) con `fetch_states`/`update_item_state`/`get_item`. Se resuelve con `get_tracker_provider(project)`.
- **breaker:** circuit-breaker persistido de integraciones (`integration_breaker.py`, Plan 148). R2 lo respeta.
- **runtime:** motor del agente (Codex CLI / Claude Code CLI / GitHub Copilot Pro). Todos cierran vía `on_execution_end`.
- **coalescing:** agrupar N disparos en <= 1 sync por proyecto por ventana T.

### Orden de implementación (numerado)
1. **F0** — flags + `completion_dispatcher.py` (con stubs no-op) + wiring en `app.py` + tests. (Sistema queda inerte, verde.)
2. **F1** — resolver matrix-aware en `task_states.py` + tests (puro).
3. **F2** — `completion_state.py` + reemplazo del stub de transición + `_apply_task_state` matrix-aware + tests.
4. **F3** — `completion_sync.py` + reemplazo de stubs de sync/coalescing + tests.
5. **F4** — validación de esquema backend + GET con `work_item_types`/`valid_states` + UI `ClientProfileEditor` + tests + `tsc`.
6. **F5** — centinela + validación de estados + tests.
7. **F6** — SystemLog en ambos módulos + tests.
8. Registrar **todos** los `test_plan208_*.py` en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh`) y, si el meta-test lo pide, en `backend/tests/harness_ratchet_allowlist.txt` (ver `backend/tests/test_harness_ratchet_meta.py`).

### Definición de Hecho (DoD) global
- [ ] Ambas flags en `FLAG_REGISTRY` + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` + `config.py`; default ON verificado.
- [ ] `completion_dispatcher.start` en `create_app`; post-hook registrado; con ambas flags off el sistema es byte-inerte (ningún sync, ninguna transición).
- [ ] `resolve_task_state_plan(profile, agent_type, work_item_type)` retrocompatible (sin `work_item_type` = comportamiento previo) y `source=="matrix"` solo con cell configurado.
- [ ] Transición ADO aplicada por los 3 runtimes cuando el operador configura un cell + status OK; idempotente; nunca en fallo/shadow/`needs_review`; centinela activo; **guardia de origen (P11) activa: no re-empuja si el humano movió el ticket fuera del flujo (`human_moved_out_of_flow`).**
- [ ] Auto-sync coalescido (<= 1 sync/proyecto/ventana), no bloqueante, respeta breaker, multi-tracker (ADO/Jira/Mantis).
- [ ] Editor de matriz en `ClientProfileEditor` con dropdowns de estados reales (`fetch_states`) y tipos reales; PUT persiste; validación no bloqueante.
- [ ] SystemLog `completion.matrix_transition` y `completion.auto_sync` emitidos.
- [ ] Cada `test_plan208_*.py` corre y pasa **por archivo** con `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`; todos registrados en `HARNESS_TEST_FILES`; `tsc --noEmit` verde.
- [ ] Sin regresión: `test_plan79_*`, `test_plan148_*ado_sync_breaker`, `test_client_profile_endpoints`, `test_harness_flags` verdes (por archivo).
- [ ] "Trabajo del operador": R2 = ninguno; R3 = opt-in (default ON, no-op hasta configurar la matriz por UI).
```
