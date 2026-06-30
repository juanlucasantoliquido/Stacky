# Plan 79 — Estados de tarea DETERMINISTAS y CONFIGURABLES por el operador

> **Estado:** PROPUESTO (sin implementar) · **Autor:** StackyArchitectaUltraEficientCode · **Fecha:** 2026-06-30
> **Versión:** v2 (criticado v1→v2, juez adversarial) · **Siguiente número libre verificado:** el doc de mayor `NN_` en `Stacky Agents/docs/` es `78_PLAN_...` → este es **79**.

> ## Changelog v1 → v2 (crítica adversarial, pasada 1)
> - **C1 (BLOQUEANTE) resuelto** — paridad de 3 runtimes + ambigüedad en F2: el "estado-en-progreso al
>   iniciar" NO se cablea en `tickets.py` con "grep". El arranque crea `AgentExecution(status="running")`
>   en **3 sitios distintos por runtime**: `api/agents.py:1213` (github_copilot/open_chat),
>   `services/claude_code_cli_runner.py:119` (Claude CLI), `services/codex_cli_runner.py:99` (Codex CLI).
>   F2 reescrita: el gancho se inserta en los **3 runners** (archivo:línea exactos) reusando el helper único
>   `apply_task_start_state`, garantizando paridad. Si solo se engancha uno, dispara para un runtime y rompe
>   los otros.
> - **C2 (IMPORTANTE) resuelto** — categoría de flag inexistente: v1 decía `"tickets_tracker"` (no existe en
>   `_CATEGORY_KEYS`). Id real para estados de tarea = **`"flujo_funcional"`** (`harness_flags.py:160`, junto
>   a `STACKY_TASK_GATE_ENABLED`). F0 corregida con el id literal.
> - **C3 (IMPORTANTE) resuelto** — reuso explícito: el plan ahora cita el precedente exacto
>   `_resolve_agent_block_states` (`tickets.py:491-513`) que YA lee
>   `profile["tracker_state_machine"][agent_type]`, y exige reusar `load_effective_client_profile` (mismo
>   costo de I/O ya presente).
> - **C4 (IMPORTANTE) resuelto** — lectura del flag: v1 mezclaba `os.getenv` (patrón de `_task_gate_enabled`)
>   con `env_only=False`. Como `env_only=False` ⇒ existe como atributo de `Config`, el lector DEBE leer de
>   `Config` (no `os.getenv`), si no la edición por UI no surte efecto sin reiniciar/recargar el entorno.
>   F0 fija el lector vía `Config`.
> - **C5 (MENOR) resuelto** — F2 ahora separa el helper `apply_task_start_state` (runner-side, sin
>   `correlation_id` de HTTP) del `_apply_task_state` HTTP de F3, evitando acoplar el runner a objetos de
>   request.
> - **[ADICIÓN ARQUITECTO]** — F8 nueva: **idempotencia + no-regresión de estado**. El helper consulta el
>   estado actual del work item (vía `provider.get_item`) y **omite** la transición si el ítem ya está en el
>   estado objetivo (evita writes redundantes al tracker y ruido de auditoría en re-arranques / reintentos
>   de run, caso real con runs zombie/reintentos). Defensivo: si `get_item` falla, igual intenta la
>   transición (best-effort, comportamiento de F2/F3).

## 1. Título, objetivo y KPI

**Estados de tarea deterministas y configurables.** El operador configura, por proyecto y por tipo de
agente, **dos** estados del work item: (a) el **estado-en-progreso** que Stacky pone cuando una tarea
**arranca**, y (b) el **estado-final** que Stacky pone cuando el agente **completa** la tarea. La
transición la ejecuta **el código de Stacky de forma determinista**, NUNCA el LLM/agente. Se garantiza —
con un centinela/test — que solo se usan esos dos estados configurados (más el `blocked_state` ya
existente, reservado a acción humana): ningún otro estado ni transición alucinada por el agente.

**KPI / impacto esperado:**
- **100 % de las transiciones de estado bajo el flag activo provienen de la config** (cero estados
  derivados del `target_ado_state` que escribe el agente). Medible por el test centinela `SD-CENT`.
- **0 transiciones a estados inexistentes en el tracker** (validación contra `fetch_states()` al guardar).
- El estado-en-progreso pasa a aplicarse **al iniciar** (hoy NO ocurre: solo se setea estado al completar).
- Reducción a **0** de los casos "el agente puso el ticket en un estado raro / mal interpolado": el
  agente deja de ser fuente de verdad del estado.

## 2. Por qué ahora / gap que cierra (anclado en el código real)

Hoy el mecanismo de transición **existe pero NO es determinista ni configurable de punta a punta**:

- El puerto `TrackerProvider` ya expone `update_item_state(item_id, logical_state)` y `fetch_states()`
  (`backend/services/tracker_provider.py:64-65`, en `PORT_METHODS:85-86`), implementados por
  `ado_provider.py:81-82` (→ `ado_client.update_work_item_state` → PATCH `System.State`,
  `ado_client.py:899-910`) y `gitlab_provider.py:216-238` (mapea lógico→label+close).
- **Pero la decisión del estado la toma el AGENTE/LLM**: las transiciones reales en
  `backend/api/tickets.py` (call sites `:1343`, `:1931`, `:4518`) dependen de un `target_ado_state` /
  `target_state` que **viene en el body/payload que escribe el agente** (leído en `:1146` y `:4415`,
  default `None` = "no tocar"). El comentario del propio endpoint lo dice: *"permite que TechnicalAnalyst
  **delegue** la transición… sin tocar ADO"* (`tickets.py:1128-1129`). Los `.agent.md` instruyen al LLM a
  interpolar placeholders como `{client_profile.tracker_state_machine.<rol>.next_state_ok}`
  (`FunctionalAnalyst.agent.md:252`, `Developer.agent.md:244`, `TechnicalAnalyst.v2.agent.md:194`). Un
  modelo menor puede **alucinar**, **no interpolar**, o **inventar** un estado.
- La config **ya tiene casa**: `client_profile.tracker_state_machine.<agent_type>` es un dict por agente
  con `input_states`, `in_progress`, `blocked_state`, `next_state_ok` (visible en
  `tickets.py:_resolve_agent_block_states:491-513` que lee `profile["tracker_state_machine"][agent_type]`,
  y en `tests/test_client_profile_endpoints.py:116`). **Pero `in_progress` hoy no se aplica al iniciar**, y
  `next_state_ok` solo se usa si el agente lo copia al body.

**Gap real (alto valor, cero trabajo extra):** convertir esa máquina de estados — que hoy es un
*placeholder que el LLM debe respetar de palabra* — en una transición **ejecutada por el código**,
**validada** contra los estados reales del tracker, y **blindada** para que solo se usen los dos estados
configurados. Es la continuación natural del patrón de gate determinista del **Plan 61**
(`harness/task_gate.py`, vocabulario congelado con `_ALL_CODES` + `test_defect_vocabulary_is_frozen`) y
respeta el puerto del **Plan 65/70** (`TrackerProvider`), sin hardcodear estados de un solo tracker.

## 3. Principios y guardarraíles (no negociables)

- **Determinismo:** el estado lo decide y aplica el código (`harness/task_states.py` puro +
  wiring en `tickets.py`). El `target_ado_state` que escriba el agente se **ignora** cuando el flag está ON.
- **Anti-alucinación de estados:** un único resolver puro es la fuente; un test centinela garantiza que el
  conjunto de estados que el wiring puede aplicar ⊆ `{in_progress, next_state_ok}` de la config (más el
  `blocked_state` existente, que sigue siendo SOLO acción humana — ver Plan B7, nunca autónomo del agente).
- **Validación por tracker:** la config se valida contra `provider.fetch_states()` del tracker activo al
  guardar el profile. ADO usa estados nativos del proceso; GitLab usa estados lógicos
  (`functional/accepted/rejected/in_progress`, `gitlab_provider.py:86-89`). No se hardcodea ninguno.
- **Config por UI:** editable en `ClientProfileEditor` (mismo patrón que `process_catalog`) + flag maestro
  en `HarnessFlagsPanel`. Regla `operator-config-always-via-ui`.
- **Cero trabajo extra / backward-compatible:** **flag maestro default OFF**. Con OFF, comportamiento
  byte-idéntico al actual (el agente sigue mandando `target_ado_state` y Stacky lo respeta como hoy).
- **Human-in-the-loop:** no se agrega ninguna decisión autónoma nueva; al contrario, se **quita** una
  decisión al LLM y se la da a la config del operador. `blocked_state` sigue reservado a acción humana.
- **Mono-operador, sin auth:** sin RBAC ni multiusuario.
- **3 runtimes:** el cambio vive en backend (`tickets.py` + servicios), aguas abajo de los 3 runtimes.
  Funciona idéntico para Codex CLI, Claude Code CLI y GitHub Copilot Pro (ver §"Impacto por runtime" en
  cada fase). Los `.agent.md` se ajustan para los 3 (texto compartido).

## 4. Fases

> **Convención de tests:** intérprete del repo = venv en `Stacky Agents/backend/.venv`. Comando base
> (PowerShell): `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest <archivo> -q`.
> Comando base (bash): `cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest <archivo> -q`.
> Los tests se escriben **antes** del código de cada fase (TDD).

---

### F0 — Flag maestro + lectores (gate de todo el plan)

**Objetivo:** declarar el flag que gobierna el plan, editable por UI, default OFF.
**Valor:** sin él, el plan no puede activarse; con OFF garantiza backward-compat byte-idéntico.

**Archivos a editar:**
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/harness_defaults.env`
- `Stacky Agents/backend/.env.example` (si existe la entrada de flags; si no, omitir y anotarlo)

**Cambios exactos:**
1. En `harness_flags.py`, agregar al `FLAG_REGISTRY` un `FlagSpec` nuevo (estructura confirmada en
   `harness_flags.py:18-27`: `key, type, label, description, group, pair=None, env_only=False, default=None`):
   ```python
   FlagSpec(
       key="STACKY_DETERMINISTIC_TASK_STATES_ENABLED",
       type="bool",
       label="Estados de tarea deterministas",
       description="Stacky aplica el estado-en-progreso (al iniciar) y el estado-final (al completar) "
                   "desde la config del proyecto, ignorando el estado que proponga el agente.",
       group="global",
       env_only=False,   # DEBE ser False → existe como atributo de Config y es editable por UI
       default=False,
   ),
   ```
2. En `harness_flags.py`, **registrar la key en `_CATEGORY_KEYS`** (confirmado `:91-208`; si no se hace,
   `test_every_registry_flag_is_categorized` rompe CI). Agregarla a la tupla de la categoría existente con
   id **`"flujo_funcional"`** (`harness_flags.py:160`), que ya agrupa `STACKY_TASK_GATE_ENABLED` y
   `STACKY_TASK_GATE_BLOCKING` — es el hogar semántico correcto (gates deterministas del flujo de tareas).
   Agregar la key literal `"STACKY_DETERMINISTIC_TASK_STATES_ENABLED"` dentro de la tupla `"flujo_funcional"`.
3. En `config.py`, agregar el atributo de `Config` siguiendo el patrón inline **exacto** de
   `STACKY_TICKETS_PROVIDER_ENABLED` (confirmado `config.py:807-809`):
   ```python
   STACKY_DETERMINISTIC_TASK_STATES_ENABLED = (
       os.getenv("STACKY_DETERMINISTIC_TASK_STATES_ENABLED", "false").lower() in ("1", "true", "yes")
   )
   ```
4. En `harness_defaults.env`, agregar la línea `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false`.
5. **Lector compartido** (lo usan tickets.py Y los 3 runners). Para no duplicarlo, definirlo en
   `Stacky Agents/backend/harness/task_states.py` (módulo de F1) y reexportarlo donde se use:
   ```python
   # en harness/task_states.py
   def deterministic_task_states_enabled() -> bool:
       """Lee del atributo de Config (env_only=False ⇒ editable por UI sin reiniciar el proceso).
       NO usar os.getenv: rompería la edición por UI que actualiza Config en caliente."""
       try:
           from config import Config
           return bool(getattr(Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", False))
       except Exception:
           return False
   ```
   En `tickets.py`, importar `from harness.task_states import deterministic_task_states_enabled` (no
   redefinir un `_deterministic_task_states_enabled` con `os.getenv`: eso quedaría desincronizado de la UI).

**Test primero:** `Stacky Agents/backend/tests/test_plan79_flag.py`
- `test_flag_registered_in_registry`: el `key` está en `FLAG_REGISTRY` con `type=="bool"`, `env_only is False`.
- `test_flag_categorized_in_flujo_funcional`: `categorize("STACKY_DETERMINISTIC_TASK_STATES_ENABLED") == "flujo_funcional"` (id literal, no solo "≠ otros").
- `test_flag_default_off`: con la env var ausente, `Config.STACKY_DETERMINISTIC_TASK_STATES_ENABLED is False`.
- `test_reader_reads_from_config_not_env`: `deterministic_task_states_enabled()` refleja el atributo de
  `Config` (monkeypatch `Config.STACKY_DETERMINISTIC_TASK_STATES_ENABLED=True` → la función devuelve True
  **sin** tocar `os.environ`). Garantiza que la edición por UI surte efecto.

**Comando:** `... -m pytest tests/test_plan79_flag.py -q`
**Criterio binario:** 4 tests verdes.
**Flag:** este ES el flag. Default OFF.
**Impacto por runtime:** ninguno (solo declaración). **Trabajo del operador:** ninguno (default OFF).

---

### F1 — Resolver puro de estados (núcleo determinista + vocabulario congelado)

**Objetivo:** función pura que, dado el `client_profile` efectivo y el `agent_type`, devuelve los DOS
estados aplicables (`in_progress`, `final_ok`) y la lista cerrada de estados que el wiring podrá aplicar.
**Valor:** fuente única de verdad; base del centinela anti-alucinación.

**Archivo a crear:** `Stacky Agents/backend/harness/task_states.py`
(espeja el estilo de `harness/task_gate.py:11-37`).

**Contenido (firmas EXACTAS, todo puro, nunca lanza):**
```python
from __future__ import annotations
from typing import NamedTuple, Optional

# Claves del dict tracker_state_machine.<agent> que este módulo lee/aplica.
# CONGELADO: el wiring NO puede aplicar un estado que no provenga de estas claves.
_APPLICABLE_KEYS: frozenset[str] = frozenset({"in_progress", "next_state_ok"})
# blocked_state queda FUERA a propósito: es acción humana (Plan B7), nunca la aplica este flujo.

class TaskStatePlan(NamedTuple):
    in_progress: Optional[str]   # estado a aplicar AL INICIAR; None = no aplicar
    final_ok: Optional[str]      # estado a aplicar al COMPLETAR OK; None = no aplicar
    source: str                  # "config" | "absent" | "no_agent_type"

def _machine_for(profile: dict, agent_type: Optional[str]) -> dict:
    """Devuelve tracker_state_machine[agent_type] o {} defensivo."""
    if not isinstance(profile, dict) or not agent_type:
        return {}
    machine = (profile.get("tracker_state_machine") or {}).get(agent_type)
    return machine if isinstance(machine, dict) else {}

def resolve_task_state_plan(profile: dict, agent_type: Optional[str]) -> TaskStatePlan:
    """Fuente ÚNICA de los estados deterministas. Pura, nunca lanza.
    - in_progress = machine['in_progress'] (str no vacío) o None
    - final_ok    = machine['next_state_ok'] (str no vacío) o None
    - source: 'no_agent_type' si falta agent_type; 'absent' si la máquina no define ninguno; 'config' si define ≥1.
    """
    if not agent_type:
        return TaskStatePlan(None, None, "no_agent_type")
    m = _machine_for(profile, agent_type)
    ip = (m.get("in_progress") or "").strip() or None
    fk = (m.get("next_state_ok") or "").strip() or None
    if ip is None and fk is None:
        return TaskStatePlan(None, None, "absent")
    return TaskStatePlan(ip, fk, "config")

def applicable_states(plan: TaskStatePlan) -> frozenset[str]:
    """Conjunto CERRADO de estados que el wiring puede aplicar para este plan."""
    return frozenset(s for s in (plan.in_progress, plan.final_ok) if s)
```

**Test primero:** `Stacky Agents/backend/tests/test_plan79_resolver.py`
- `test_resolves_both_states`: profile con `tracker_state_machine.developer = {"in_progress":"Active","next_state_ok":"Done"}` → `(Active, Done, "config")`.
- `test_missing_agent_type`: `agent_type=None` → `(None, None, "no_agent_type")`.
- `test_machine_absent`: profile sin la entrada → `(None, None, "absent")`.
- `test_empty_strings_become_none`: `{"in_progress":"  ","next_state_ok":""}` → `(None, None, "absent")`.
- `test_applicable_states_excludes_blocked`: aunque la máquina tenga `blocked_state`, `applicable_states` NO lo incluye.
- `test_pure_never_raises`: pasar basura (`None`, `123`, `{"tracker_state_machine": "x"}`) nunca lanza.
- `test_applicable_vocabulary_frozen`: `_APPLICABLE_KEYS == frozenset({"in_progress","next_state_ok"})` literal (congela el vocabulario, espeja `test_defect_vocabulary_is_frozen`).

**Comando:** `... -m pytest tests/test_plan79_resolver.py -q`
**Criterio binario:** 7 tests verdes.
**Flag:** N/A (módulo puro inerte hasta cablearse). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — Aplicar estado-en-progreso AL INICIAR la tarea (determinista, PARIDAD 3 runtimes)

**Objetivo:** cuando arranca el run de una tarea (con `agent_type` + ticket con `ado_id`) y el flag está
ON, Stacky aplica `plan.in_progress` vía el provider, determinísticamente, **en los 3 runtimes**.
**Valor:** cubre el requerimiento (a); hoy NO se setea estado al iniciar.

**Punto de arranque por runtime (VERIFICADO, archivo:línea exactos — NO usar grep, ya está localizado):**
El run se materializa creando `AgentExecution(status="running")` en **3 sitios distintos**, uno por runtime.
El gancho va en los 3, inmediatamente **después** de crear/recuperar el `AgentExecution` y conocer
`ticket_id`/`agent_type`:
- **GitHub Copilot:** `Stacky Agents/backend/api/agents.py:1213-1230` (función `open_chat`; tras
  `created_new_execution = True`). Variables disponibles: `local_ticket_id`, `inferred_type`,
  `project_ctx.stacky_project_name`.
- **Claude Code CLI:** `Stacky Agents/backend/services/claude_code_cli_runner.py:119` (donde se crea
  `exec_row = AgentExecution(...)`). Tomar `ticket_id` y `agent_type` del propio `exec_row`/contexto del runner.
- **Codex CLI:** `Stacky Agents/backend/services/codex_cli_runner.py:99` (donde se crea
  `exec_row = AgentExecution(...)`). Idem.

> Si los 3 sitios comparten un punto común aguas arriba que el implementador confirme por lectura (p. ej.
> un orquestador único que los 3 atraviesan), se permite UN solo gancho ahí en vez de 3 — **pero solo si se
> verifica por lectura que los 3 runtimes pasan por ese punto**. Si hay duda, van los 3 ganchos. La paridad
> es el criterio binario, no la cantidad de ganchos.

**Helper de arranque (runner-side, en `harness/task_states.py` para no acoplar runners a HTTP):**
```python
def apply_task_start_state(*, project_name, agent_type, ado_id, provider) -> dict:
    """Aplica el estado-en-progreso de la config. Pura respecto de HTTP (sin request/correlation_id).
    `provider` = TrackerProvider ya resuelto para el proyecto (o None). Nunca lanza."""
    from harness.task_states import resolve_task_state_plan, applicable_states, deterministic_task_states_enabled
    if not deterministic_task_states_enabled():
        return {"skipped": True, "reason": "flag_off"}
    try:
        from services.client_profile import load_effective_client_profile
        profile = load_effective_client_profile(project_name) or {}
    except Exception:
        profile = {}
    plan = resolve_task_state_plan(profile, agent_type)
    target = plan.in_progress
    if not target or target not in applicable_states(plan) or not ado_id or provider is None:
        return {"skipped": True, "reason": "no_in_progress_or_no_target"}
    return _safe_transition(provider, ado_id, target, phase="start")  # ver F8 (idempotencia)
```
Cada runner llama, dentro de un `try/except` que NO rompe el arranque:
```python
try:
    from harness.task_states import apply_task_start_state
    apply_task_start_state(project_name=<proj>, agent_type=<type>, ado_id=<ado_id>, provider=<prov>)
except Exception:
    logger.debug("apply_task_start_state falló (no crítico)", exc_info=True)
```
(El runner resuelve `provider` con `get_tracker_provider(project_name)` de `services.tracker_provider`; si
el runner no tiene `ado_id` a mano, lo deriva del `Ticket` por `ticket_id`. El `_safe_transition` y la
idempotencia se definen en F8.)

**Casos borde:** sin `agent_type` → no-op; `in_progress is None` → no-op; ticket sin `ado_id` → no-op;
provider None o sin soporte → no-op; fallo del provider → log + **no romper el arranque del run**.

**Test primero:** `Stacky Agents/backend/tests/test_plan79_apply_start.py`
- `test_start_applies_in_progress_when_enabled`: flag ON + profile `in_progress="Active"` + provider mock
  → `provider.update_item_state(ado_id,"Active")` exactamente 1 vez.
- `test_start_noop_when_flag_off`: flag OFF → `update_item_state` NO se llama (byte-idéntico al actual).
- `test_start_noop_without_in_progress`: profile sin `in_progress` → no se llama.
- `test_start_provider_failure_does_not_break`: provider lanza → `apply_task_start_state` retorna dict de
  error sin propagar (assert no excepción).
- `test_start_parity_helper_is_runner_agnostic`: llamar `apply_task_start_state` con los kwargs de cada
  runtime (3 sets de args simulados) → se comporta idéntico (mismo provider mock recibe la misma llamada).
  Esto prueba la PARIDAD a nivel de contrato del helper (sin levantar los 3 runners reales).

**Comando:** `... -m pytest tests/test_plan79_apply_start.py -q`
**Criterio binario:** 5 tests verdes.
**Flag:** `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` (OFF → helper retorna `flag_off`, gancho inerte).
**Impacto por runtime:** los **3 runners** invocan el MISMO helper → paridad garantizada por contrato
(`test_start_parity_helper_is_runner_agnostic`). Fallback: provider sin soporte / falla → `try/except` lo
absorbe y el run continúa en los 3. **Trabajo del operador:** ninguno (opt-in, default OFF).

---

### F3 — Aplicar estado-final AL COMPLETAR (determinista, ignora el del agente)

**Objetivo:** en la completion (`set_stacky_status_by_ado`, `tickets.py:~1098+`), cuando el flag está ON y
el run completó OK, Stacky aplica `plan.final_ok` **de la config**, **ignorando** el `target_ado_state`
que mandó el agente. "Respetar a rajatabla" el estado-final configurado.
**Valor:** cubre el requerimiento (b) + el determinismo duro (el LLM deja de decidir el estado de cierre).

**Archivo a editar:** `Stacky Agents/backend/api/tickets.py` (función `set_stacky_status_by_ado`, bloque de
transición `:1325-1361`) + crear el helper compartido `_apply_task_state`.

**Cambio exacto (sobre el bloque `:1325-1361`):**
1. Crear helper compartido (usado por F2 y F3):
   ```python
   def _apply_task_state(*, ticket, agent_type, phase, correlation_id, publish_ok=True) -> dict:
       """phase ∈ {"start","final"}. Aplica el estado determinista de la config.
       Devuelve un dict de telemetría {skipped|ok|error,...}. Nunca lanza."""
       from harness.task_states import resolve_task_state_plan, applicable_states
       from services.client_profile import load_effective_client_profile
       try:
           profile = load_effective_client_profile(getattr(ticket, "stacky_project_name", None)) or {}
       except Exception:
           profile = {}
       plan = resolve_task_state_plan(profile, agent_type)
       target = plan.in_progress if phase == "start" else plan.final_ok
       if not target:
           return {"skipped": True, "reason": f"no_{phase}_state", "source": plan.source}
       # CENTINELA EN RUNTIME: jamás aplicar un estado fuera del conjunto cerrado.
       if target not in applicable_states(plan):
           return {"skipped": True, "reason": "state_not_applicable"}  # defensa imposible-por-construcción
       ado_id = getattr(ticket, "ado_id", None)
       if ado_id is None:
           return {"skipped": True, "reason": "no_ado_id"}
       if phase == "final" and not publish_ok:
           return {"skipped": True, "reason": "publish_not_ok"}
       prov = _provider_for_ticket(ticket=ticket)
       # _safe_transition centraliza idempotencia (F8) + try/except + fallback al ado_client legacy.
       return _safe_transition(prov, ado_id, target, phase=phase,
                               legacy_client_fn=lambda: _ado_client_for_ticket(ticket=ticket),
                               correlation_id=correlation_id)
   ```
   (`_safe_transition` se define en F8; es la ÚNICA función que llama a `update_item_state` /
   `update_work_item_state`, de modo que idempotencia y manejo de error viven en un solo lugar para start y
   final.)
2. En `set_stacky_status_by_ado`, **antes** del bloque `:1330 if target_ado_state:`, anteponer la rama
   determinista que tiene prioridad:
   ```python
   if _deterministic_task_states_enabled() and new_status == "completed":
       # Determinista: el estado-final sale de la config, NO del body del agente.
       state_change_result = _apply_task_state(
           ticket=t, agent_type=agent_type, phase="final",
           correlation_id=correlation_id, publish_ok=publish_result.get("ok", False),
       )
       # El target_ado_state del agente se IGNORA a rajatabla cuando el flag está ON.
   else:
       # … bloque actual intacto (:1330-1361), comportamiento legacy byte-idéntico.
   ```
   (El `block_guard` de `:1313-1323` solo aplica en la rama legacy, donde el estado lo propone el agente;
   en la rama determinista no hay estado del agente que bloquear, así que no se evalúa.)

**Casos borde:** `new_status != "completed"` → rama determinista no corre (errores/cancel siguen legacy);
`final_ok is None` → skip con `no_final_state` (la config no definió cierre → no se fuerza nada);
`publish_ok False` → skip `publish_not_ok` (no cerrar sin comentario, igual que hoy `:1333`).

**Test primero:** `Stacky Agents/backend/tests/test_plan79_apply_final.py`
- `test_final_uses_config_not_agent_target`: flag ON, profile `next_state_ok="Done"`, body trae `target_ado_state="Algo Inventado"`, publish OK → `update_item_state(ado_id,"Done")` 1 vez; **nunca** con `"Algo Inventado"`.
- `test_final_ignores_hallucinated_state`: body `target_ado_state="EstadoQueNoExiste"` → el provider jamás recibe ese valor.
- `test_final_noop_when_flag_off`: flag OFF + body `target_ado_state="Done"` → comportamiento legacy (usa el del body).
- `test_final_skips_when_publish_failed`: publish_ok False → no se llama `update_item_state`.
- `test_final_skips_without_config`: profile sin `next_state_ok` → skip, no se fuerza nada.
- `test_final_provider_failure_returns_200`: provider lanza → endpoint responde 200 (no rompe al agente).

**Comando:** `... -m pytest tests/test_plan79_apply_final.py -q`
**Criterio binario:** 6 tests verdes.
**Flag:** `STACKY_DETERMINISTIC_TASK_STATES_ENABLED`.
**Impacto por runtime:** idéntico en los 3 (completion es el mismo endpoint server-side). Fallback: provider
sin soporte → `try/except` absorbe, 200. **Trabajo del operador:** ninguno (opt-in, default OFF).

---

### F4 — Centinela anti-alucinación de estados (test duro)

**Objetivo:** garantizar por test que, con el flag ON, el conjunto de estados que el wiring puede aplicar
está **estrictamente contenido** en `{in_progress, next_state_ok}` de la config — jamás un estado del
agente ni inventado.
**Valor:** este es el requisito DURO "corroborar que solo se usan esos dos estados". Sin esto el plan no
cumple.

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan79_centinela_estados.py` (`SD-CENT`).

**Casos (todos con provider mockeado que CAPTURA cada `update_item_state(id, state)`):**
- `test_only_configured_states_are_applied`: para una matriz de combinaciones (start+final, distintos
  `agent_type`, body con `target_ado_state` arbitrario/alucinado), recolectar TODOS los `state` que el
  provider recibió y assert `captured_states <= {in_progress, next_state_ok}` de la config usada.
- `test_agent_target_never_reaches_provider_when_enabled`: con flag ON, ningún valor de `target_ado_state`
  del body llega al provider salvo que coincida con la config.
- `test_blocked_state_never_auto_applied`: aunque la máquina defina `blocked_state`, este flujo nunca lo
  aplica (sigue siendo acción humana, Plan B7).
- `test_vocabulary_frozen_guard`: importar `harness.task_states._APPLICABLE_KEYS` y assert == literal
  `{"in_progress","next_state_ok"}` (si alguien agrega una clave aplicable sin actualizar este test, rompe).

**Comando:** `... -m pytest tests/test_plan79_centinela_estados.py -q`
**Criterio binario:** 4 tests verdes. **Este test es bloqueante del DoD.**
**Flag:** valida ambos estados del flag. **Impacto por runtime:** N/A (test). **Trabajo del operador:** ninguno.

---

### F5 — Validación de la config contra los estados reales del tracker (al guardar)

**Objetivo:** al guardar el `client_profile` por UI, si `tracker_state_machine.<agent>.in_progress` o
`.next_state_ok` no existen en `provider.fetch_states()` del tracker activo, devolver un **warning no
bloqueante** en el response (no impedir guardar, pero avisar) — para que el operador no configure un estado
inexistente.
**Valor:** cero transiciones a estados inexistentes; feedback inmediato en la UI.

**Archivos a editar:**
- `Stacky Agents/backend/api/client_profile.py` (handler `PUT /projects/<name>/client-profile`, el que
  llama `save_client_profile`; el GET valida en `:107`).
- (reuso) `Stacky Agents/backend/services/tracker_provider.py` (`get_tracker_provider(project)` →
  `fetch_states()`).

**Cambio (función pura + wiring):**
1. Crear helper puro en `harness/task_states.py`:
   ```python
   def validate_states_against_tracker(profile: dict, valid_states: list[str]) -> list[dict]:
       """Devuelve warnings [{agent_type, field, value, reason:'state_not_in_tracker'}].
       valid_states vacío → no valida (devuelve []), para no romper si el tracker no expone estados."""
       out = []
       if not valid_states:
           return out
       valid = {s.strip().lower() for s in valid_states if isinstance(s, str)}
       machines = (profile.get("tracker_state_machine") or {}) if isinstance(profile, dict) else {}
       for agent_type, m in machines.items():
           if not isinstance(m, dict):
               continue
           for field in ("in_progress", "next_state_ok"):
               val = (m.get(field) or "").strip()
               if val and val.lower() not in valid:
                   out.append({"agent_type": agent_type, "field": field, "value": val,
                               "reason": "state_not_in_tracker"})
       return out
   ```
2. En el `PUT` de `client_profile.py`, tras validar y antes/junto al response, llamar (defensivo,
   best-effort; si `fetch_states` falla, devolver `[]`):
   ```python
   state_warnings = []
   try:
       prov = get_tracker_provider(project_name)
       valid_states = prov.fetch_states() if prov else []
       from harness.task_states import validate_states_against_tracker
       state_warnings = validate_states_against_tracker(profile, valid_states)
   except Exception:
       state_warnings = []
   # incluir en el response: {"ok": True, ..., "state_warnings": state_warnings}
   ```

**Casos borde:** GitLab → `fetch_states()` devuelve estados lógicos
(`functional/accepted/rejected/in_progress`, `gitlab_provider.py:212`); ADO → estados del proceso
(`ado_client.py:381`). La comparación es case-insensitive. `fetch_states` vacío/falla → sin warnings (no
romper el guardado).

**Test primero:** `Stacky Agents/backend/tests/test_plan79_validate_states.py`
- `test_warns_on_unknown_ado_state`: valid=["New","Active","Done"], profile con `next_state_ok="Finiquitado"` → 1 warning.
- `test_no_warning_when_valid`: todos los estados ∈ valid → `[]`.
- `test_gitlab_logical_states_ok`: valid=["functional","accepted","in_progress"], profile `in_progress="in_progress"` → `[]`.
- `test_empty_valid_states_no_validation`: `valid_states=[]` → `[]` (no rompe).
- `test_pure_never_raises`: basura → `[]`.

**Comando:** `... -m pytest tests/test_plan79_validate_states.py -q`
**Criterio binario:** 5 tests verdes.
**Flag:** independiente del flag maestro (la validación al guardar siempre ayuda; no cambia comportamiento
de runtime). **Impacto por runtime:** N/A (es config-time, no run-time). **Trabajo del operador:** ninguno
(solo ve un warning si configuró mal).

---

### F6 — UI: editar estados por agente + flag maestro

**Objetivo:** que el operador edite `in_progress` y `next_state_ok` por `agent_type` en
`ClientProfileEditor` y vea/active el flag maestro en `HarnessFlagsPanel`, **sin tocar `.env`**.
**Valor:** cumple `operator-config-always-via-ui`.

**Archivos a editar:**
- `Stacky Agents/frontend/src/components/ClientProfileEditor.tsx` (ya edita `process_catalog` `:989-990`;
  agregar una sección "Estados de tarea por agente" que lea/escriba `profile.tracker_state_machine[agent].in_progress`
  y `.next_state_ok`). Mostrar los `state_warnings` del response del PUT (F5) si vienen.
- (sin cambios de código nuevo) `HarnessFlagsPanel.tsx` ya renderiza cualquier flag del registry → el flag
  de F0 aparece automáticamente en su categoría. Verificar que aparece; **no** hace falta código a medida.

**Cambio (pseudocódigo de UI):** por cada `agent_type` presente en `tracker_state_machine`, dos inputs de
texto controlados (`in_progress`, `next_state_ok`) atados al objeto del perfil; al guardar, PUT del profile
completo (mismo flujo que `process_catalog`). Si el response trae `state_warnings`, render de una alerta no
bloqueante por warning (`{agent_type}.{field}: "{value}" no existe en el tracker`).

**Test primero:** **build TS** (no hay runner de vitest instalado, confirmado en memoria del entorno). El
criterio es `tsc` sin errores:
- Comando: `cd "Stacky Agents/frontend" && npx tsc --noEmit` (o `npm run build` si está configurado).
**Criterio binario:** `tsc --noEmit` exit 0; al abrir la UI, la sección "Estados de tarea por agente" se
ve y persiste (verificación manual mínima del operador opcional, no parte del DoD automatizado).
**Flag:** el flag maestro se ve en HarnessFlagsPanel. **Impacto por runtime:** N/A (frontend).
**Trabajo del operador:** ninguno obligatorio; opcional editar los estados (default = lo que ya tenga el
profile; si no tiene, el flag OFF deja todo como hoy).

---

### F7 — Alinear los `.agent.md` (los 3 runtimes) + telemetría + ratchet

**Objetivo:** (a) ajustar el texto de los `.agent.md` para que, cuando el operador active el flag, el
agente sepa que **NO** debe mandar `target_ado_state` (Stacky decide); (b) registrar telemetría de la
transición; (c) registrar los tests nuevos en el ratchet.
**Valor:** coherencia entre prompt y código en los 3 runtimes; observabilidad; blindaje del plan.

**Archivos a editar:**
- `Stacky Agents/backend/Stacky/agents/FunctionalAnalyst.agent.md`,
  `.../TechnicalAnalyst.v2.agent.md`, `.../Developer.agent.md` (y sus copias en `backend/agents/` si
  existen — verificar duplicados con grep). Agregar una nota corta: *"Si Stacky tiene estados
  deterministas activos, NO incluyas `target_state`/`target_ado_state`: Stacky aplica el estado-en-progreso
  y el estado-final desde la config del proyecto. El `blocked_state` sigue siendo SOLO decisión humana."*
  (Texto compartido = paridad de los 3 runtimes; el contenido del `.agent.md` lo consumen los 3.)
- `Stacky Agents/backend/api/tickets.py`: incluir `state_change_result` en el `SystemLog`/respuesta de la
  completion (ya hay `state_change_result` en `:1346`; reusar el campo, ahora con `"source":"config"`).
- `Stacky Agents/backend/run_harness_tests.sh` **y** `run_harness_tests.ps1`: agregar los **6** archivos de
  test nuevos a `HARNESS_TEST_FILES` (`test_plan79_flag.py`, `test_plan79_resolver.py`,
  `test_plan79_safe_transition.py`, `test_plan79_apply_start.py`, `test_plan79_apply_final.py`,
  `test_plan79_centinela_estados.py`, `test_plan79_validate_states.py`, `test_plan79_ratchet.py`,
  `test_plan79_agent_md_note.py` — todos los `test_plan79_*.py`). Regla `ratchet-obliga-registrar-tests`;
  si no se agregan, el meta-test del Plan 49 F4 falla.

**Test primero / criterio:**
- `Stacky Agents/backend/tests/test_plan79_ratchet.py`: assert que **todos** los archivos `test_plan79_*.py`
  presentes en `tests/` están listados en `run_harness_tests.sh` (lee el archivo, busca cada nombre).
  (Espeja el meta-test del Plan 49.)
- Verificación de los `.agent.md`: un test de texto opcional `test_plan79_agent_md_note.py` que assert que
  cada `.agent.md` editado contiene el substring `"estados deterministas"` (anti-drift de la nota).

**Comando:** `... -m pytest tests/test_plan79_ratchet.py tests/test_plan79_agent_md_note.py -q`
**Criterio binario:** tests verdes + el meta-ratchet del Plan 49 sigue verde.
**Flag:** N/A. **Impacto por runtime:** los 3 leen el mismo `.agent.md` (paridad). **Trabajo del operador:** ninguno.

---

### F8 — [ADICIÓN ARQUITECTO] `_safe_transition`: idempotencia + no-regresión de estado

**Objetivo:** centralizar TODA escritura de estado en una única función que (1) omite la transición si el
work item ya está en el estado objetivo (idempotencia), y (2) maneja error + fallback legacy en un solo
lugar. Es la única función del plan que invoca `update_item_state`/`update_work_item_state`.
**Valor:** evita writes redundantes y ruido de auditoría en re-arranques / reintentos de run (caso real con
runs zombie y reintentos, ver memoria `claude-cli-zombie-sessions`); un solo punto = el centinela F4 tiene
una sola superficie que vigilar.

**Archivo a editar:** `Stacky Agents/backend/harness/task_states.py` (agregar `_safe_transition`).

**Contenido (firma EXACTA):**
```python
def _safe_transition(provider, ado_id, target, *, phase, legacy_client_fn=None, correlation_id=None) -> dict:
    """ÚNICA función que escribe estado. Idempotente y defensiva; nunca lanza.
    - Si provider expone get_item, lee el estado actual; si ya == target (case-insensitive) → skip 'already_in_state'.
    - Aplica via provider.update_item_state(str(ado_id), target); si provider es None y hay legacy_client_fn,
      usa legacy_client_fn().update_work_item_state(int(ado_id), target).
    - Devuelve {ok|skipped|error, to, phase, ...}."""
    import logging as _lg
    log = _lg.getLogger("stacky_agents.task_states")
    if not target or ado_id is None:
        return {"skipped": True, "reason": "no_target_or_id", "phase": phase}
    # Idempotencia (best-effort: si get_item falla, seguimos a la transición).
    try:
        if provider is not None and hasattr(provider, "get_item"):
            current = (provider.get_item(str(ado_id)) or {}).get("state")
            if isinstance(current, str) and current.strip().lower() == target.strip().lower():
                return {"skipped": True, "reason": "already_in_state", "to": target, "phase": phase}
    except Exception:
        log.debug("get_item falló en _safe_transition (no crítico)", exc_info=True)
    try:
        if provider is not None:
            provider.update_item_state(str(ado_id), target)
        elif legacy_client_fn is not None:
            legacy_client_fn().update_work_item_state(int(ado_id), target)
        else:
            return {"skipped": True, "reason": "no_provider", "phase": phase}
        return {"ok": True, "to": target, "phase": phase, "source": "config"}
    except Exception as exc:  # noqa: BLE001
        log.exception("_safe_transition(%s) falló ADO-%s corr=%s", phase, ado_id, correlation_id)
        return {"ok": False, "to": target, "error": str(exc), "type": type(exc).__name__, "phase": phase}
```

> Nota de contrato: el dict que devuelve `provider.get_item` ya usa la clave `"state"` (ver `TrackerItem`
> en `tracker_provider.py:23` con `state: str = "open"` y los providers que la pueblan). Si un provider no
> la expone, la rama de idempotencia simplemente no aplica (best-effort).

**Test primero:** `Stacky Agents/backend/tests/test_plan79_safe_transition.py`
- `test_skips_when_already_in_target`: `get_item` devuelve `{"state":"Done"}` y target="Done" → skip
  `already_in_state`; `update_item_state` NO se llama.
- `test_applies_when_state_differs`: `get_item` devuelve `{"state":"Active"}`, target="Done" → llama
  `update_item_state(ado_id,"Done")` 1 vez.
- `test_get_item_failure_still_transitions`: `get_item` lanza → igual llama `update_item_state` (best-effort).
- `test_provider_none_uses_legacy`: provider None + `legacy_client_fn` provisto → usa
  `update_work_item_state` legacy.
- `test_never_raises_on_update_failure`: `update_item_state` lanza → devuelve dict de error, no propaga.
- `test_case_insensitive_idempotence`: `get_item` "done" vs target "Done" → skip (no re-escribe por
  diferencia de mayúsculas).

**Comando:** `... -m pytest tests/test_plan79_safe_transition.py -q`
**Criterio binario:** 6 tests verdes.
**Flag:** N/A (la idempotencia siempre aplica cuando se transiciona; no agrega comportamiento bajo OFF
porque con OFF nadie llama a `_safe_transition`). **Impacto por runtime:** idéntico en los 3 (es el helper
común). **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | **Asimetría de vocabulario ADO (estados nativos) vs GitLab (lógicos)**: el operador configura "Done" pero GitLab espera "accepted". | F5 valida contra `fetch_states()` del tracker activo y avisa por UI. La config es **por proyecto**, y cada proyecto tiene un solo tracker → el operador configura los estados de SU tracker. |
| R2 | Romper el flujo legacy donde el agente manda `target_ado_state`. | Flag default **OFF** + rama `else` que deja el bloque `:1330-1361` **intacto**. Tests `*_noop_when_flag_off` lo prueban. |
| R3 | El provider de un proyecto no soporta `update_item_state`. | `try/except` en `_apply_task_state` → log + skip; el run/completion no se rompe (tests de fallo del provider devuelven 200/continúan). |
| R4 | El gancho de inicio (F2) se inserta en el lugar equivocado (duplica transición o no dispara). | F2 obliga a **reconciliar con grep** el punto de arranque del run; helper único compartido con F3 (no duplica lógica). Idempotente: re-aplicar el mismo estado es no-dañino. |
| R5 | Alguien agrega una 3ª clave "aplicable" y rompe el determinismo. | `_APPLICABLE_KEYS` congelado + `test_vocabulary_frozen_guard` (F4) rompe CI si cambia sin actualizar el test. |
| R6 | El agente sigue mandando `target_ado_state` por costumbre aun con flag ON. | Con flag ON el código lo **ignora** (no es un fallback: es "a rajatabla"). Tests `test_final_uses_config_not_agent_target` lo garantizan. La nota en `.agent.md` (F7) reduce ruido. |
| R7 | `load_effective_client_profile` agrega latencia en cada inicio/completion. | Es la misma función que ya usa el `block_guard` (`tickets.py:505`); costo ya presente en el flujo. Sin nueva fuente de I/O. |

## 6. Fuera de scope

- Cambiar el `blocked_state` o su semántica (sigue siendo acción humana, Plan B7). No se toca.
- Estados **por tipo de tarea** distintos del `agent_type` (la granularidad elegida es por `agent_type`,
  que es como ya está modelado `tracker_state_machine`). Ver §"Decisión de granularidad".
- Transiciones intermedias adicionales (p. ej. "in_review" entre inicio y fin). El requerimiento son DOS
  estados; agregar más sería violar "solo se usan esos dos estados".
- Editor visual de máquina de estados / drag-and-drop. Inputs de texto simples por agente alcanzan.
- Migrar los `.agent.md` a "nunca mandar target_state" de forma incondicional (rompería el modo legacy con
  flag OFF). Solo se agrega una nota condicional.

## 7. Glosario, granularidad, orden e DoD

**Glosario (términos Stacky para un modelo menor):**
- **work item / ticket:** unidad de trabajo en el tracker (ADO work item o GitLab issue).
- **tracker:** Azure DevOps (ADO) o GitLab; cada proyecto usa uno (`issue_tracker.type`).
- **TrackerProvider:** puerto (Protocol) que abstrae el tracker; métodos `fetch_states()` y
  `update_item_state(item_id, logical_state)` (`tracker_provider.py:64-65`).
- **client_profile:** config JSON por proyecto (editable por UI). Contiene `tracker_state_machine`.
- **tracker_state_machine.<agent_type>:** dict con `input_states`, `in_progress`, `next_state_ok`,
  `blocked_state` para cada rol de agente (developer/technical/functional/...).
- **estado-en-progreso (`in_progress`):** estado que Stacky pone al **iniciar** la tarea.
- **estado-final (`next_state_ok`):** estado que Stacky pone al **completar OK**.
- **blocked_state:** estado de bloqueo; SOLO lo aplica un humano (Plan B7), nunca el flujo automático.
- **flag maestro:** `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` (default OFF).
- **centinela:** test que garantiza una invariante dura (aquí: solo se aplican los 2 estados configurados).
- **ratchet:** meta-test (Plan 49) que exige que todo test nuevo esté listado en `run_harness_tests.{sh,ps1}`.

**Decisión de granularidad (resuelta con criterio, sin preguntar trade-offs mecánicos):**
La config es **por proyecto + por `agent_type`**, no global ni per-tarea individual. Razón: (1) el estado
del work item es propiedad del **workflow del proyecto/tracker**, no del agente individual; (2) ya está
modelado así en `tracker_state_machine.<agent_type>` — reusar evita un sistema paralelo; (3) per-tarea
individual sería sobre-ingeniería para un sistema **mono-operador** y violaría "solo dos estados". El
`agent_type` da el override necesario (un developer cierra en "Reviewed by Dev", un functional en otro
estado) sin inventar dimensiones nuevas. **Global con override** = el default del profile por tracker
provee el valor base; cada `agent_type` puede sobreescribir.

**Orden de implementación (estricto, por dependencia):**
1. **F0** — flag + lector compartido `deterministic_task_states_enabled` (todo lo demás lo referencia).
2. **F1** — resolver puro (`resolve_task_state_plan` / `applicable_states`; núcleo, fuente de verdad).
3. **F8** — `_safe_transition` (idempotencia + única escritura de estado). **Va antes de F2/F3 porque ambos
   lo invocan.**
4. **F3** — `_apply_task_state` (HTTP) + estado-final en completion (`set_stacky_status_by_ado`).
5. **F2** — `apply_task_start_state` (runner-side) + ganchos en los 3 runners (reusan `_safe_transition`).
6. **F4** — centinela anti-alucinación (depende de F2+F3 cableados).
7. **F5** — validación contra tracker al guardar (independiente; puede ir en paralelo a F2-F4).
8. **F6** — UI (depende de F0 visible + F5 para mostrar warnings).
9. **F7** — `.agent.md` + telemetría + ratchet (cierre; el ratchet registra los **6** archivos de test).

**Definición de Hecho (DoD) global:**
- [ ] F0–F7 implementadas; todos los tests `test_plan79_*.py` verdes con el venv del repo.
- [ ] **Centinela F4 verde** (invariante "solo dos estados configurados" probada).
- [ ] Con flag **OFF**: comportamiento byte-idéntico al actual (tests `*_noop_when_flag_off`).
- [ ] Con flag **ON**: el `target_ado_state` del agente se ignora; estado-inicio y estado-final salen de
      la config (tests `test_final_uses_config_not_agent_target`, `test_start_applies_in_progress_when_enabled`).
- [ ] `tsc --noEmit` del frontend exit 0; sección "Estados de tarea por agente" visible en
      `ClientProfileEditor`; flag visible en `HarnessFlagsPanel`.
- [ ] Los 5 archivos de test registrados en `run_harness_tests.sh` y `.ps1`; meta-ratchet (Plan 49) verde.
- [ ] Validación F5 devuelve `state_warnings` para estados inexistentes en el tracker activo.
- [ ] Paridad 3 runtimes: el cambio es server-side + `.agent.md` compartido; Codex/Claude/Copilot idénticos.
- [ ] Trabajo del operador: ninguno obligatorio (opt-in, default OFF).
