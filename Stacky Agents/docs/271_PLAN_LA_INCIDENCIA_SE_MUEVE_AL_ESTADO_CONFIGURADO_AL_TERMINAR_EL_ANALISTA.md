# Plan 271 — La incidencia se mueve al estado configurado al terminar el analista

**Estado:** CRITICADO v2 (veredicto v1: **RECHAZADO**, 8 bloqueantes)
**Fecha:** 2026-07-28
**Juez v2: subagente independiente, misma corrida, contexto limpio**
**Reserva de números:** este plan usa **271**. Los huecos **261** y **262** siguen libres. El **272** queda reservado para "un solo escritor de estado" (§6.1).
**Depende de:** nada. **Coordina con:** 79 (`_apply_task_state` + `_safe_transition`), 208 (matriz), 210 (gate de build), 216 (UI de estados), 254 (`_with_outcome`), 270 (cierre real ADO+GitLab).

---

## CHANGELOG v1 → v2

Anclajes verificados abriendo los archivos: **~70 citas**. La mayoría (config, flags, `agent_completion_internal`, `api/executions`, frontend) estaban **EXACTAS**. Lo que falló fue el **censo** y las **costuras entre fases**.

- **C1 (BLOQ)** — §2.1 decía "conviven **dos** motores". Son **CUATRO**: faltaban el **Motor C** `api/tickets.py:531 _apply_task_state` (plan 79, llamado desde `set_stacky_status_by_ado` `:1473`), que **ya honra el `next_state_ok` de nivel rol** porque toma `plan.final_ok` sin exigir `source=="matrix"`, y el **Motor D** inline `api/tickets.py:1489-1491`, sin plan dueño. §2 reescrita entera; KPI corregido; agregada la **hipótesis del deploy** (`harness_defaults.env:33`); alcance del Motor D declarado en §2.1bis.
- **C2 (BLOQ)** — F2 podía **pisar el gate de build del plan 210**: `_apply_task_state` aplica `dev_build_verify.gate_final_state` (`api/tickets.py:576-582`) y `completion_state.py` tiene **0** apariciones de `dev_build_verify`. Nueva **F2-bis** obligatoria.
- **C3 (BLOQ)** — el criterio de F0 (`0 passed, 4 failed`) era insatisfacible: `test_rc1_razon_del_skip_nunca_es_silenciosa` nacía **VERDE** (`completion_state.py:50` y `:53` ya devuelven `reason`). Test reemplazado.
- **C4 (BLOQ)** — F0-test4 ("el archivo no debe contener `from services.ado_client import AdoClient`") era **mutuamente insatisfacible** con F3, que conserva a propósito el camino legacy y agrega `_legacy_ado_client()`. Test reescrito en forma **positiva** y acotado a la función.
- **C5 (BLOQ)** — F3 declaraba `test_output_watcher.py` verde como criterio binario, pero lo **rompe**: el doble del test (`:359-361`) no acepta los kwargs con que `build_ado_client` construye `AdoClient`. F3 ahora especifica la adaptación exacta del doble (sin borrar asserts).
- **C6 (BLOQ)** — F3 no definía `project_name=None`: `get_tracker_provider(None)` resuelve el **proyecto activo** y podía escribir en el tracker equivocado. Regla explícita agregada.
- **C7 (BLOQ)** — F5 exigía `source="role"` pero `_safe_transition` hardcodea `"source": "config"` (`harness/task_states.py:178`). Firma del helper y contrato de `source` corregidos; el `setdefault("source", ...)` de `:280` también quedaba roto por F3.
- **C8 (BLOQ)** — las "12 razones" de §2.4 y las 12 del mapa de F6 eran **conjuntos distintos** (intersección: 7). Catálogo único de **23** razones, congelado en Python y verificado contra el `.ts` por un test real.
- **C9..C17 (IMPORTANTES)** — anclaje falso de RC-3 (`api/tickets.py:1520` serializa otra variable); `set_stacky_status_by_ado` declarado fuera de scope pero tocado de hecho (arranca en **:1205**, no `:1487`); R3 "no lo empeora" era falso (carrera daemon vs inline); el "resolutor único" nacía con 2 de 4 ramas sin productor; agujero de **celda de matriz parcial**; F5 gateado por una flag **ajena** (`STACKY_UI_OUTCOME_REASON_BADGE_ENABLED`, `api/executions.py:75-76`); F0 no ejecutable ("los helpers los escribís vos"); `on_failure_state` sin una línea; anclajes desfasados corregidos con la línea real.
- **C18..C22 (MENORES)** — límites reales de `PlainHelp`; `styles.toneEspera` **sí existe**; huella de regresión; ambigüedad `.venv`/`venv`; renombre silencioso `no_final_state`→`no_config`.
- **`[ADICIÓN ARQUITECTO]`** — **F8: censo ejecutable de escritores de estado** (`test_plan271_censo_escritores.py`). Es exactamente el defecto que hizo caer al v1: nadie podía saber cuántos motores escriben estado. Ahora el repo lo sabe y se rompe solo si aparece un cuarto.
- **`[ADICIÓN ARQUITECTO]`** — **F2-bis: árbitro anti-doble-escritura por `execution_id`**, que resuelve C2 y C11 sin fusionar los motores.

---

## 1. Objetivo, KPI e impacto

El operador configuró, en la pantalla que Stacky le dio para eso, que al terminar el **Analista Técnico** la incidencia pase a `To Do`. Stacky corre el agente, lo cierra en verde… y la incidencia se queda exactamente en el estado en el que llegó. Sin error, sin aviso, sin razón visible en ningún lado.

Este plan hace cuatro cosas, en este orden: **(1)** diagnostica **cuál de los cuatro motores** debía moverla y no lo hizo; **(2)** repara esa causa sin romper las guardias que otros planes ya pusieron; **(3)** elimina el *skip mudo* — todo no-cambio de estado deja una razón que el operador ve donde ya mira; **(4)** deja la escritura de estado en paridad ADO ↔ GitLab y **censada**, que hoy no lo está.

No es una feature nueva. Es **reparar un comportamiento que el operador ya configuró y que Stacky prometió aplicar**.

### KPI (medibles, sin instrumentación nueva)

| KPI | Hoy | Después |
|---|---|---|
| Incidencias que quedan en el estado de entrada tras un cierre por **post-hook** (los 3 runtimes) con `next_state_ok` a nivel rol | **100 %** (skip `no_matrix_cell`, `completion_state.py:90-92`) | **0 %** |
| Incidencias que quedan en el estado de entrada tras un cierre por `PATCH /by-ado/<id>/stacky-status` con la flag del 79 **apagada en deploy** (`harness_defaults.env:33`) | **100 %** | **0 %** (lo cubre el post-hook, que no depende de esa flag) |
| Razones de no-transición visibles para el operador | **0 de 23** (mueren en `CloseResult.ado_state_change` y en `SystemLog`) | **23 de 23** en el drawer de la ejecución |
| Trackers soportados por el escritor de estado del chokepoint | **1** (ADO; `agent_completion_internal.py:527,536`) | **2** (ADO + GitLab, vía `tracker_provider`) |
| Motores de estado conocidos y verificados por un test | **0** (el propio v1 contó 2 donde hay 4) | **4/4 motores censados** (A, B, C, D), en un allow-list de 6 entradas; un **quinto motor** rompe CI |
| Clics del operador para arreglarlo | N/A (hoy no puede: no sabe que pasó) | **0** |

> **KPI corregido (C1).** El v1 afirmaba "100 % con `next_state_ok` a nivel rol" a secas. Es falso en general: por el camino `set_stacky_status_by_ado` (`api/tickets.py:1205`), con `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` **ON** (default de `config.py:1245-1246`), `_apply_task_state` **sí** aplica el nivel rol. El 100 % vale para el camino del post-hook, y para el camino del 79 **solo cuando la flag está apagada**, que es exactamente lo que hace el deploy (`harness_defaults.env:33` fuerza `=false`).

### Impacto esperado

El operador deja de tener que mover incidencias a mano después de cada corrida del analista técnico, y — más importante — deja de tener que *adivinar por qué* no se movieron. El tablero vuelve a decir la verdad sin intervención.

---

## 2. Por qué ahora, y la causa raíz diagnosticada

### 2.1 Los CUATRO motores que hoy pueden mover el `System.State` (leído, no supuesto)

Ninguno sabe que los otros existen.

**Motor A — "matriz" (plan 208), asíncrono.**
`app.py:997-1000` registra `completion_dispatcher` en `ticket_status.register_post_hook` y arranca su daemon. Al terminar **cualquier** agente en **cualquiera de los 3 runtimes**, `ticket_status.on_execution_end` (`services/ticket_status.py:293`) llama `_run_post_hooks` (`:349-355`), el hook encola O(1) (`completion_dispatcher.py:51-57` → `:28-48`) y el **daemon de fondo** `_drain_loop` (`completion_dispatcher.py:98-120`) llama `completion_state.maybe_apply_state_transition(ev)` en **`:117`**. Escribe vía `harness/task_states.py:146 _safe_transition`, provider-aware (`:171-177`). Flag `STACKY_ADO_STATE_MATRIX_ENABLED` **ON** (`config.py:1404-1406`; `harness_flags.py:2795-2807 default=True`; **ausente** de `harness_defaults.env`, o sea que el default del código manda también en deploy).

**Motor B — "employee_config" (B2 / plan 216), síncrono.**
`services/agent_completion_internal.py:66 close_execution_with_publish` es el chokepoint de `api/tickets.py:1386`, `api/qa_browser.py:373`, `api/qa_uat.py:394`, `services/output_watcher.py:412` y `:618`. Paso 3.5 (`:242-258`) resuelve `transition_state` con `_resolve_transition_state_from_config` (`:321-386`); Paso 4 (`:260-280`) escribe con `_attempt_state_change` (`:502-553`).

**Motor C — "determinista" (plan 79 + gate del 210), síncrono. ⟵ EL QUE EL v1 NO VIO.**
`api/tickets.py:531 _apply_task_state`, llamado **solo** desde `set_stacky_status_by_ado` en `api/tickets.py:1473`, gateado por `deterministic_task_states_enabled()` (`harness/task_states.py:19-28`, lee el atributo de **clase** `Config`). Su código relevante:

```python
# api/tickets.py:545-551
plan = resolve_task_state_plan(profile, agent_type, getattr(ticket, "work_item_type", None))
target = plan.in_progress if phase == "start" else plan.final_ok   # ← NO exige source=="matrix"
if not target:
    return {"skipped": True, "reason": f"no_{phase}_state", "source": plan.source}
if target not in applicable_states(plan):
    return {"skipped": True, "reason": "state_not_applicable"}
```

y antes de escribir aplica el **gate de build del plan 210** (`api/tickets.py:576-582`), que puede **degradar** el target cuando el Developer no tiene veredicto de máquina fresco.

**Motor D — escritor inline (sin plan dueño).**
`api/tickets.py:1489-1491`, dentro del mismo `set_stacky_status_by_ado`, rama `elif target_ado_state:`: llama `_provider.update_item_state(...)` o `_ado_client_for_ticket(...).update_work_item_state(...)` directo, sin `_safe_transition`.

> **Corolario (C1).** La frase del v1 "el plan 208 eligió no honrar el nivel de rol" es cierta **solo para el motor A**. El motor C sí lo honra. Por eso el síntoma reportado no puede explicarse sin decir **por qué camino se cerró la ejecución**.

### 2.1bis Alcance de cada motor en ESTE plan (tabla vinculante)

Esta tabla manda. Si alguna fase parece contradecirla, gana la tabla.

| Motor | ¿Este plan lo **modifica**? | ¿Lo **censa** (F8)? | ¿Lo cubre el **árbitro** (F2-bis guardia 2)? |
|---|---|---|---|
| **A** `completion_state.maybe_apply_state_transition` | **SÍ** — F2, F2-bis, F5 | SÍ | **SÍ** (es quien consulta el árbitro) |
| **B** `_attempt_state_change` | **SÍ** — F3, F4, F5 | SÍ | **SÍ** (es quien escribe la marca que el árbitro lee) |
| **C** `api/tickets.py:531 _apply_task_state` | **NO** (§6.6) | **SÍ** | **NO** |
| **D** inline `api/tickets.py:1489-1491` | **NO** (§6.6) | **SÍ** | **NO** |

**Decisión explícita sobre el Motor D, en una frase:** *el 271 lo **censa** en el allow-list de F8 (entrada `api/tickets.py::set_stacky_status_by_ado`) para que quede nombrado y no vuelva a desaparecer de un censo, pero **no lo modifica ni lo arbitra**, y difiere su unificación al **plan 272**.*

**Por qué el árbitro no cubre C ni D (y no es un olvido):** la guardia 2 de F2-bis se apoya en la key `final_state_outcome` del `metadata_json` de la ejecución, que **solo F5 escribe**, y F5 solo toca los motores A y B. Los motores C y D viven en `api/tickets.py`, que §6.6 declara intocable en este plan (territorio del 270 y del 272). **Consecuencia aceptada y declarada:** un cierre por `PATCH /by-ado/<id>/stacky-status` puede seguir produciendo dos escrituras (C o D, más A por el post-hook). Eso **ya pasa hoy** y este plan no lo empeora en ese camino concreto, porque no toca ninguno de los dos. Lo que sí cierra es la carrera **A vs B**, que es la que F2 sí agrava. Extender el árbitro a C/D es alcance del 272.

### 2.2 CAUSA RAÍZ PRIMARIA (RC-1) — la única UI que el operador tiene escribe en una clave que el motor A se niega a leer

Cuatro anclajes, los cuatro **verificados**:

**(a) Dónde escribe el operador.** La pantalla "Estados del tracker" (plan 216, montada en `SettingsPage.tsx:246` bajo el sub-tab `flow`) es la única que dice literalmente *"Por cada rol: en qué estados actúa y **a cuál mueve el ticket al terminar**"* (`frontend/src/pages/StatesConfigPage.tsx:100-103`) y se presenta como *"Una sola fuente"* (`:84-88`). Su guardado es:

```ts
// frontend/src/pages/StatesConfigPage.tsx:76-78
function actualizarRol(rol: StateRole, parche: Partial<RoleStateMachine>) {
  guardar.mutate({ ...maquina, [rol]: { ...(maquina[rol] ?? {}), ...parche } });
}
```

y el campo del estado final es `next_state_ok` **a nivel de rol** (`:196-202`, `onChange={(v) => onChange({ next_state_ok: v })}` en `:201`). Escribe, por tanto, `tracker_state_machine.technical.next_state_ok = "To Do"`. **Nunca** escribe `by_work_item_type`.

**(b) Qué exige el motor A.** `services/completion_state.py:88-92`:

```python
plan = resolve_task_state_plan(profile, agent_type, work_item_type)
ctx["source"] = plan.source
if plan.source != "matrix":
    # Backward-compat DURA: sin cell configurado, los paths de runner NO transicionan.
    return _logged(ctx, ev, {"skipped": True, "reason": "no_matrix_cell", "source": plan.source})
```

**(c) Cuándo `source == "matrix"`.** `backend/harness/task_states.py:104-113`:

```python
cell = _matrix_cell(m, work_item_type)          # m["by_work_item_type"][<wit>]
ip_m = (cell.get("in_progress") or "").strip() or None
fk_m = (cell.get("next_state_ok") or "").strip() or None
if ip_m is not None or fk_m is not None:        # ← BASTA in_progress para ganar "matrix"
    return TaskStatePlan(ip_m, fk_m, "matrix")
ip = (m.get("in_progress") or "").strip() or None   # ← nivel ROL
fk = (m.get("next_state_ok") or "").strip() or None # ← lo que escribió el operador
if ip is None and fk is None:
    return TaskStatePlan(None, None, "absent")
return TaskStatePlan(ip, fk, "config")              # ← "config", NO "matrix"
```

Lo que el operador configuró produce `source="config"`, y `completion_state.py:90` lo descarta.

**(d) El propio código lo admite y nadie lo cerró.** `config.py:1401-1403` dice textualmente: *"NO-OP hasta que el operador configure la matriz (`tracker_state_machine.<rol>.by_work_item_type`) desde la UI"*, y el texto de la flag repite lo mismo (`harness_flags.py:2800-2802`). Pero la UI de "Estados" no ofrece `by_work_item_type`: solo lo hace `ClientProfileEditor.tsx:467-477`, en otro sub-tab (`SettingsPage.tsx:248`, sub `client-profile`), que es el editor crudo del perfil.

**Agravante 1 (`work_item_type` NULL).** Aun con la matriz configurada, si el ticket tiene `work_item_type` en NULL (`models.py:55`, columna nullable), `_matrix_cell` devuelve `{}` (`task_states.py:70-72`) y se cae al mismo skip.

**Agravante 2 (celda parcial) — NUEVO, C13.** Si el operador escribió en `by_work_item_type` **solo** `in_progress` (sin `next_state_ok`), `resolve_task_state_plan` devuelve `source="matrix"` con `final_ok=None` (`task_states.py:107-108`). El motor A entra al camino "matriz", no encuentra estado final, y **el `next_state_ok` de rol queda inalcanzable para siempre**. Es el mismo síntoma. F2 tiene que cubrirlo explícitamente.

### 2.3 CAUSA RAÍZ SECUNDARIA (RC-2) — el motor B ata el cambio de estado al éxito del publish

`services/agent_completion_internal.py:265-278`:

```python
if not effective_target:
    state_result = {"skipped": True, "reason": "not_requested"}
elif final_status == "completed" and not publish_result.get("ok"):
    state_result = {"skipped": True, "reason": "publish_not_ok", ...}
else:
    state_result = _attempt_state_change(...)
```

`publish_result` no es `ok` en cuatro escenarios normales, ninguno de los cuales es un fallo real de publicación:

| Origen | Ancla | ¿Hubo algo que publicar? |
|---|---|---|
| `html_output_path_missing` | `:228-234` | **No** |
| `already_terminal_no_html` | `:228-234` (rama `already_terminal`) | **No** |
| `auto_publish_disabled` | `:236-238` (`_should_auto_publish`, `:389-397`) | **No** |
| `ado_publisher_unavailable` | `:617-626` | **No** |
| `review_mode_hold` (early-return, ni llega al Paso 4) | `:210-224` | **No** (publicación diferida a decisión humana) |

En los cuatro primeros el gate es **espurio**: bloquea la transición "para no dejar un ticket en Done sin comentario publicado" (`:261-263`) cuando nunca hubo comentario que publicar.

### 2.4 CAUSA RAÍZ TERCIARIA (RC-3) — el skip es mudo

`CloseResult.ado_state_change` (`agent_completion_internal.py:50,61,297`) se serializa y se devuelve… y **no lo consume nadie en el frontend**: `grep -rn "ado_state_change" frontend/src` ⇒ **0 hits** (verificado).

> **Corrección de anclaje (C9).** El v1 decía "el único caller que lo expone por HTTP es `api/tickets.py:1520`". **FALSO**: en `:1520` se serializa la variable **local** `state_change_result`, calculada en `:1466-1503` por los motores C y D — no el campo del `CloseResult`. La conclusión (nadie lo mira) se refuerza: `CloseResult.ado_state_change` **no se expone por HTTP en ninguna parte**.

Del lado del motor A, `completion_state._logged` (`:164-191`) escribe una fila `SystemLog action="completion.matrix_transition"` (`:176`) con la razón — pero no hay endpoint ni componente que la muestre.

**Catálogo canónico de razones (23) — C8.** El v1 listaba 12 en §2.4 y otras 12 distintas en F6 (intersección: 7). Estas son **todas** las que el código puede emitir hoy, con su ancla:

| # | Razón | Ancla real | Motor |
|---|---|---|---|
| 1 | `ok` | (éxito de `_safe_transition`, `task_states.py:178`) | A/B |
| 2 | `flag_off` | `completion_state.py:50` | A |
| 3 | `not_ok_status` | `completion_state.py:53` | A |
| 4 | `no_ticket` | `completion_state.py:62` | A |
| 5 | `no_ado_id_or_stacky_project` | `completion_state.py:78` | A |
| 6 | `no_matrix_cell` | `completion_state.py:92` (**legacy tras F2**) | A |
| 7 | `no_final_state` | `completion_state.py:96` (**legacy tras F2**) | A |
| 8 | `state_not_applicable` | `completion_state.py:99` | A |
| 9 | `human_moved_out_of_flow` | `completion_state.py:156` | A |
| 10 | `exception` | `completion_state.py:118` | A |
| 11 | `no_config` | **nueva, F1** | A |
| 12 | `no_agent_type` | **nueva, F1** | A |
| 13 | `no_target_or_id` | `task_states.py:162` | A/B |
| 14 | `already_in_state` | `task_states.py:168` | A/B |
| 15 | `no_provider` | `task_states.py:177` | A/B |
| 16 | `not_requested` | `agent_completion_internal.py:266,466` | B |
| 17 | `publish_not_ok` | `agent_completion_internal.py:270` | B |
| 18 | `review_mode_hold` | `agent_completion_internal.py:222-223` | B |
| 19 | `no_ticket_id` | `agent_completion_internal.py:510` | B |
| 20 | `ticket_lookup_failed` | `agent_completion_internal.py:521` | B |
| 21 | `no_ado_id` | `agent_completion_internal.py:524` | B |
| 22 | `ado_client_unavailable` | `agent_completion_internal.py:533` | B |
| 23 | `provider_unavailable` | **nueva, F3** | B |

> El bug de fondo no es que el ticket no se mueva. Es que **no se mueve y no dice por qué**. Familia "cero fallas mudas" del plan 255.

### 2.5 Hueco de paridad (E-3) — el escritor del motor B es ADO-only

`services/agent_completion_internal.py:526-541`:

```python
try:
    from services.ado_client import AdoClient
except ImportError as exc: ...
try:
    AdoClient().update_work_item_state(int(ado_id), target_state)
```

Sin `tracker_provider`, sin `_safe_transition`, sin guardia de idempotencia, sin guardia de origen. En un proyecto GitLab esto intenta escribir en ADO usando el `iid` de GitLab.

> **Corrección (C1).** El v1 decía que *"el plan 79 nunca censó este call site"* y listaba a `_attempt_state_change` como "tierra de nadie en los planes 79, 208, 216 y 270". El censo del propio v1 era peor: **no vio los motores C ni D**. El docstring *"ÚNICA función que escribe estado"* está en `harness/task_states.py:155` (no `:146`, que es la línea del `def`), y de los cuatro escritores solo A y C lo respetan. Por eso F8 construye un **censo ejecutable**.

### 2.6 Hipótesis del deploy — obligatoria de descartar antes de construir (NUEVA, C1)

`backend/harness_defaults.env:33` fuerza `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false` mientras `config.py:1245-1246` declara `"true"`. Ese archivo es el snapshot que `deployment/build_release.ps1` hornea en cada deploy.

Consecuencia: **en el deploy del operador, el motor C está APAGADO**. Si el operador cerró la incidencia por `PATCH /by-ado/<id>/stacky-status`, el síntoma se explica enteramente por esa línea, y la reparación más barata sería una línea de env — no seis fases.

**Esto NO invalida el plan**, porque el motor A (post-hook) es el camino común de los 3 runtimes y está roto **independientemente** de esa flag. Pero F0 tiene que decirlo con evidencia, no suponerlo. Ver **F0-D**.

### 2.7 Candidatos descartados, con el porqué

| Cand. | Veredicto | Evidencia |
|---|---|---|
| **C-a** | **CONFIRMADO** = RC-2 | `agent_completion_internal.py:267-272` |
| **C-b** (`review_mode_hold`) | **Real pero NO es el caso reportado** | `:210-224` solo dispara con `publish_mode=="review"` (`_resolve_publish_mode`, `:400-416`), opt-in por proyecto y default `auto` (`:405-406`). Se documenta como razón visible en F5; su semántica NO cambia: es HITL deliberado. |
| **C-c** (`target_source="caller"`) | **Real, condicional, NO es la causa** | `:247-248`. Solo aplica si `output_watcher._read_target_state_from_meta` (`:705-729`) encontró `target_ado_state` en `comment.meta.json` (`:406,421`). Precedencia caller > config, explícita en F1. |
| **C-d** (falta `agent_filename`) | **Fragilidad, no causa** | `:355-364`; si falta, cae al fallback `:368-384`, que para `technical` acierta. |
| **C-e** (fallback no determinista) | **Fragilidad real, no causa** | `:373-382` recorre `configs.items()` y devuelve el primero que matchea; con dos archivos técnicos el resultado depende del orden del dict. Se hace determinista en F1. |
| **C-f** (heurística triplicada) | **Duplicación real, NO causó el síntoma** | `agent_completion_internal.py:304-318`, `api/agents.py:1766-1767`, `services/agent_history.py:54-55`. Las tres mapean `"technical" in filename → "technical"` igual. **Fuera de scope** (§6). |
| **C-g** (la UI escribe en otra clave) | **DESCARTADO para `transition_state`** | `api/projects.py:883` escribe `transition_state` en el payload que `project_manager.set_agent_workflow_config` (`:409-422`) guarda en `agent_workflow_configs[<filename>]`, y `get_agent_workflow_config` (`:392-406`) lo lee de ahí. La persistencia es correcta. **CONFIRMADO para `next_state_ok`**: ver RC-1. |
| **C-h** (motor C apagado en deploy) | **PLAUSIBLE, se mide en F0-D** | `harness_defaults.env:33` vs `config.py:1245-1246`. Ver §2.6. |

---

## 3. Principios y guardarraíles (aplican a TODAS las fases)

1. **Diagnóstico antes que fix.** F0 no toca una línea de producción. Escribe el rojo que prueba el bug **y** mide qué motor estaba activo. Ninguna fase posterior se escribe sin ese rojo.
2. **Reparar ≠ inventar.** Este plan solo hace que se aplique lo que el operador **ya configuró**. No inventa estados, no infiere destinos.
3. **Human-in-the-loop innegociable.** `completion_state._origin_guard` (`:121-161`) se conserva intacto. `review_mode_hold` (`:210-224`) se conserva intacto. El **gate de build del plan 210** se conserva y se **extiende** al motor A (F2-bis).
4. **Cero skip mudo.** Toda rama que decida NO cambiar el estado produce una razón del catálogo de §2.4, persistida y visible. Un `return {"skipped": True}` sin `reason` es un defecto de este plan.
5. **Paridad de 3 runtimes por construcción.** Codex CLI, Claude Code CLI y Copilot Pro cierran todos por `ticket_status.on_execution_end` (`completion_dispatcher.py:8-10` lo declara literal) y/o por `close_execution_with_publish`. Ninguna fase toca un runner.
6. **Paridad ADO ↔ GitLab.** Toda escritura de estado nueva o corregida pasa por `services/tracker_provider.get_tracker_provider` (`:125`). Nada de `AdoClient()` directo **salvo** en el camino legacy que protege una flag OFF.
7. **Backward-compatible.** Con las 4 flags apagadas, el comportamiento es byte-idéntico al de hoy.
8. **Cero trabajo del operador.** Todas las flags nacen **ON**. Ninguna fase agrega un campo, un clic ni una configuración nueva.
9. **Tests por archivo.** Los tests que tocan la DB son flaky bajo pytest con shared-cache (`SQLITE_LOCKED`). **Nunca** correr la suite completa: siempre `pytest <archivo>`, hasta 3 reintentos del mismo archivo.
10. **Todo `test_*.py` nuevo se registra en los DOS scripts** — `backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES`, líneas con dos espacios de indentación y **sin** comillas) **y** `backend/scripts/run_harness_tests.ps1` (`$HarnessTestFiles`, elementos **entre comillas dobles**). Omitir uno deja el meta-test rojo.
11. **Nunca borrar un assert para poner algo en verde.** Si un criterio binario de este plan choca con la realidad, se **detiene la fase y se reporta**; no se relaja el test. (El v1 tenía dos criterios que solo podían "cumplirse" borrando asserts: C3 y C4.)
12. **El intérprete es `backend\.venv\Scripts\python.exe`.** OJO: en este repo existen **`backend/.venv` y `backend/venv`**, ambos reales. Usá siempre el primero, con la ruta completa entre comillas.

### 3.1 Receta completa de una flag nueva (7 patas — el "patrón triple" es un mito)

| # | Archivo | Qué se agrega |
|---|---|---|
| 1 | `backend/config.py` | `KEY: bool = os.getenv("KEY", "true").lower() in ("1","true","yes")` — copiar el patrón exacto de `config.py:1404-1406`. |
| 2 | `backend/services/harness_flags.py` | Un `FlagSpec(key=..., type="bool", default=True, label=..., description=..., group="global", env_only=False)` en `FLAG_REGISTRY` (empieza en `:490`). |
| 3 | `backend/services/harness_flags.py` | La key en `_CATEGORY_KEYS["flujo_funcional"]` (`:268-273`). Sin esto, `tests/test_harness_flags.py` queda **rojo** (nota explícita en `harness_flags.py:488`). |
| 4 | `backend/services/harness_flags_help.py` | Un `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)`. **Restricciones duras REALES** (`tests/test_harness_flags_help.py:44-52,63-70`): `what` entre **10 y 200** chars; `on_effect`/`off_effect` ≤ **240** y deben empezar con `"Si "`; `example` ≤ **300**; ningún campo vacío; **sin** las palabras de `JARGON_DENYLIST` (`:17-20`: MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime); **sin** identificadores `SCREAMING_SNAKE` (`_KEY_RE`, `:22`) y **sin** referencias a fases tipo `F1` (`_PHASE_RE`, `:23`). |
| 5 | `backend/harness_defaults.env` | Línea `KEY=true`, en **orden alfabético**. Obligatorio: este archivo es el snapshot que `deployment/build_release.ps1` hornea en cada deploy. Precedente vivo: `harness_defaults.env:33` fuerza `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false` mientras `config.py:1245-1246` dice `true`. |
| 6 | `backend/tests/test_plan271_flags.py` | Test que afirma que las 4 keys están en `FLAG_REGISTRY` con `default is True`, en `_CATEGORY_KEYS["flujo_funcional"]`, y con línea `=true` en `harness_defaults.env`. |
| 7 | `backend/scripts/run_harness_tests.sh` **y** `.ps1` | Registrar todo archivo de test nuevo. |

> **NO tocar `deployment/harness_defaults.env`.** Es un snapshot derivado de un deploy vivo (docstring de `deployment/export_harness_defaults.py:1-21`) y **ya diverge** del versionado. Fuera de scope.

### 3.2 Las 4 flags de este plan y su default

| Flag | Fases | Default | Justificación de la categoría |
|---|---|---|---|
| `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` | F1, F2, F2-bis | **ON** | Repara lo ya configurado. El operador tipeó `To Do` en `StatesConfigPage.tsx:196-202`, en una pantalla que le prometió *"a cuál mueve el ticket al terminar"*. Aplicarlo no es una escritura nueva: es cumplir la promesa. Dejarla OFF **dejaría el bug vivo**, que es lo que la regla de flags prohíbe. |
| `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED` | F3 | **ON** | Corrige el **destino** de una escritura que ya ocurre, no agrega escrituras. Hoy `agent_completion_internal.py:536` escribe siempre en ADO; con la flag ON escribe en el tracker que el proyecto declara. En un proyecto ADO el comportamiento es idéntico; en uno GitLab deja de escribir en el lugar equivocado. |
| `STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED` | F4 | **ON** | *El único caso que roza la categoría (B) y merece precisión.* Con la flag ON, Stacky transiciona tickets que hoy no transiciona ⇒ **sí produce escrituras nuevas en el sistema real del operador**. Va **ON igual**, porque: (i) el estado destino salió íntegramente de la config del operador, no de una inferencia; (ii) el gate que se afina nunca fue una decisión del operador sino una heurística interna documentada en `:261-263`; (iii) se afina **solo** para los cuatro casos en que no había nada que publicar — el caso en que la publicación **se intentó y falló** (`event == "publish.failed"`), el `publish.idempotent_replay` y el `review_mode_hold` **conservan el gate**. La parte que podría dejar un ticket cerrado sin evidencia sigue bloqueada. |
| `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` | F5, F6 | **ON** | Solo lectura: persiste y muestra una razón que ya se calcula. No escribe en ningún sistema del operador. Solo-lectura nunca es excepción. |

**Ninguna flag de este plan nace OFF.** No aplica la categoría (A) — no hay loop, daemon nuevo, barrido, polling ni llamada a modelo en reposo — ni (B) en su forma pura, por lo argumentado arriba.

> **F2-bis y F8 no llevan flag propia.** F2-bis es una **guardia** que solo puede reducir escrituras (nunca agregarlas) y va cableada dentro del camino que ya protege `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED`. F8 es un test.

---

## 4. Fases

### F0 — Caracterización: el rojo que prueba el bug + medición del motor activo

**Objetivo (1 frase):** dejar escrito, en tests que hoy fallan, el comportamiento que el operador espera, y **medir** cuál de los cuatro motores estaba activo en el deploy.
**Valor:** ninguna fase posterior puede escribirse "de fe". Si F0 pasa en verde antes de tocar producción, el diagnóstico está mal.

**Archivos a crear:**
- `backend/tests/test_plan271_caracterizacion.py`
- `backend/tests/plan271_helpers.py` — **los helpers son parte del plan, no "los escribís vos"** (C15).

**Archivos a editar:** los dos scripts de arnés (§3-10).

#### F0-A — helpers exactos (`backend/tests/plan271_helpers.py`)

**Por qué un módulo aparte:** los cuatro tests y las fases F2/F4/F5 los reusan. **No toques `conftest.py`.**

**Contrato exacto de `plan271_helpers.py` (implementalo literal):**

```python
"""Plan 271 — dobles compartidos. Sin red, sin ADO real, sin GitLab real."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeProvider:
    """Doble de TrackerProvider. Registra escrituras; get_item devuelve el estado
    que le sembrés (o {} para simular 'no se pudo leer')."""

    def __init__(self, current_state: str | None = None):
        self.current_state = current_state
        self.writes: list[tuple[str, str]] = []

    def get_item(self, item_id: str) -> dict:
        return {"state": self.current_state} if self.current_state else {}

    def update_item_state(self, item_id: str, logical_state: str) -> dict:
        self.writes.append((str(item_id), logical_state))
        return {"ok": True}


def patch_motor_a(monkeypatch, *, profile: dict, ado_id=4242, project="P271",
                  work_item_type=None, provider: FakeProvider | None = None):
    """Parchea TODO lo que `completion_state.maybe_apply_state_transition` importa
    DENTRO de la función. Ojo: son imports locales, así que hay que parchear el
    MÓDULO ORIGEN, no `completion_state`.

    Parchea exactamente:
      - db.session_scope                                   (completion_state.py:56)
      - services.client_profile.load_effective_client_profile   (:85)
      - services.tracker_provider.get_tracker_provider          (:101)
      - services.completion_dispatcher.emit_completion_log      (:171)  -> no-op
    Devuelve el FakeProvider usado (para inspeccionar `.writes`).
    """
    ...


def close_sin_html(monkeypatch, *, transition_state: str = "To Do"):
    """Crea execution+ticket en la DB de test y llama close_execution_with_publish
    con html_output_path=None, final_status='completed'.

    Modelalo sobre `backend/tests/test_u2_publish_review_mode.py:150-162`, que ya
    siembra una execution y monkeypatchea `_attempt_publish` /
    `_resolve_transition_state_from_config` / `_attempt_state_change` sobre el
    módulo `services.agent_completion_internal` (esos SÍ se resuelven por atributo
    de módulo). Devuelve el CloseResult.
    """
    ...
```

> **Detalle que un modelo menor no puede inferir y por eso está escrito:** `completion_state.maybe_apply_state_transition` hace todos sus imports **dentro** de la función (`:56-57`, `:80-85`, `:101`). `monkeypatch.setattr(completion_state, "get_tracker_provider", ...)` **no hace nada**. Hay que parchear `services.tracker_provider.get_tracker_provider`. En cambio `agent_completion_internal` llama a sus helpers por atributo de módulo, así que ahí sí se parchea el propio módulo.

#### F0-B — los 4 tests de caracterización

```python
# backend/tests/test_plan271_caracterizacion.py
"""Plan 271 F0 — Caracterización del bug reportado.

Describen el comportamiento ESPERADO por el operador. Al escribirlos (antes de
F1..F8) DEBEN FALLAR LOS CUATRO. Si alguno pasa en verde acá, el diagnóstico del
plan está equivocado y hay que rehacerlo antes de tocar producción.
"""
from __future__ import annotations
import inspect

from tests.plan271_helpers import FakeProvider, close_sin_html, patch_motor_a


PERFIL_SOLO_ROL = {"tracker_state_machine": {"technical": {
    "input_states": ["New"], "in_progress": "Doing", "next_state_ok": "To Do",
}}}


def test_rc1_rol_sin_matriz_deberia_transicionar(monkeypatch):
    """RC-1: el operador configuró tracker_state_machine.technical.next_state_ok
    = 'To Do' desde StatesConfigPage (nivel ROL, sin by_work_item_type).
    Hoy completion_state devuelve skipped/no_matrix_cell. Debe transicionar."""
    from services import completion_state
    prov = patch_motor_a(monkeypatch, profile=PERFIL_SOLO_ROL, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"esperaba transición, obtuve {out}"
    assert out.get("to") == "To Do"
    assert prov.writes == [("4242", "To Do")]


def test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol(monkeypatch):
    """RC-1 agravante 2: by_work_item_type['Bug'] con SOLO in_progress hace que
    resolve_task_state_plan devuelva source='matrix' y final_ok=None
    (task_states.py:107-108). El next_state_ok de rol queda inalcanzable."""
    from services import completion_state
    perfil = {"tracker_state_machine": {"technical": {
        "next_state_ok": "To Do",
        "by_work_item_type": {"Bug": {"in_progress": "Doing"}},
    }}}
    prov = patch_motor_a(monkeypatch, profile=perfil, work_item_type="Bug")
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"la celda parcial enterró el nivel rol: {out}"
    assert prov.writes == [("4242", "To Do")]


def test_rc2_sin_html_no_debe_bloquear_la_transicion(monkeypatch):
    """RC-2: cierre completed sin html_output_path (nada que publicar) NO debe
    impedir el cambio de estado configurado."""
    res = close_sin_html(monkeypatch, transition_state="To Do")
    assert res.ado_state_change.get("ok") is True, \
        f"publish sin nada que publicar no debe gatear el estado: {res.ado_state_change}"


def test_e3_el_escritor_rutea_por_provider():
    """E-3: _attempt_state_change debe rutear por tracker_provider para tener
    paridad ADO/GitLab. Forma POSITIVA a propósito: el camino legacy con la flag
    OFF conserva el import de AdoClient y NO puede prohibirse."""
    from services import agent_completion_internal as aci
    src = inspect.getsource(aci._attempt_state_change)
    assert "get_tracker_provider" in src, "el escritor de estado sigue siendo ADO-only"
```

> **Por qué cambiaron dos tests respecto del v1 (C3, C4).**
> - El viejo `test_rc1_razon_del_skip_nunca_es_silenciosa` **nacía verde**: `maybe_apply_state_transition({"final_status": "error"})` devuelve `{"skipped": True, "reason": "not_ok_status"}` (`completion_state.py:52-53`) — o `"flag_off"` (`:50`) —, así que `out.get("reason")` siempre es truthy. Se reemplazó por el caso de **celda parcial**, que sí está rojo y cubre un agujero real.
> - El viejo `test_e3_el_escritor_no_puede_ser_ado_only` prohibía el import de `AdoClient` en todo el archivo, lo que **contradice F3**, que conserva el camino legacy y agrega `_legacy_ado_client()`. Se pasó a forma positiva y acotada a la función con `inspect.getsource`.

#### F0-C — F0 y el DoD: cuándo un test de F0 se vuelve verde

| Test de F0 | Se vuelve VERDE en |
|---|---|
| `test_rc1_rol_sin_matriz_deberia_transicionar` | **F2** |
| `test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol` | **F2** |
| `test_rc2_sin_html_no_debe_bloquear_la_transicion` | **F4** |
| `test_e3_el_escritor_rutea_por_provider` | **F3** |

#### F0-D — medición del motor activo (5 minutos, sin tocar código)

Corré estos 4 comandos y **pegá la salida en el PR**. No es opcional: decide si el plan sigue completo o se recorta.

```powershell
# 1. ¿El motor C está apagado en el snapshot de deploy?
Select-String -Path "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\harness_defaults.env" -Pattern "STACKY_DETERMINISTIC_TASK_STATES_ENABLED"
# 2. ¿Y el motor A?
Select-String -Path "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\harness_defaults.env" -Pattern "STACKY_ADO_STATE_MATRIX_ENABLED"
# 3. ¿Hay .env del operador que pise cualquiera de las dos?
Select-String -Path "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.env" -Pattern "STACKY_(DETERMINISTIC_TASK_STATES|ADO_STATE_MATRIX)_ENABLED" -ErrorAction SilentlyContinue
# 4. ¿Qué dicen los SystemLog del motor A en la base viva?
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sqlite3,sys,json,glob; p=glob.glob(r'N:\GIT\RS\STACKY\DeployStackyAgents\data\*.db'); print(p); c=sqlite3.connect(p[0]) if p else sys.exit('sin db'); print(list(c.execute(\"select json_extract(context,'$.reason'), count(*) from system_logs where action='completion.matrix_transition' group by 1\")))"
```

**Interpretación (escribila en el PR, una línea):**
- Si (1) da `=false` **y** el operador cerró por `PATCH /by-ado/<id>/stacky-status` ⇒ el motor C estaba apagado; la reparación mínima sería esa línea, **pero el motor A sigue roto** y las fases F1/F2/F2-bis se justifican igual.
- Si (4) devuelve mayoría `no_matrix_cell` ⇒ **RC-1 confirmado con datos de producción**.
- Si (4) no devuelve nada ⇒ el motor A ni siquiera se disparó; revisar `app.py:997-1000` **antes** de seguir.

**Comando exacto de los tests:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_caracterizacion.py" -v
```

**Criterio de aceptación (BINARIO):** `0 passed, 4 failed`. **Y** la salida de los 4 comandos de F0-D pegada en el PR con su interpretación en una línea. Cualquier otro conteo = el diagnóstico está mal, se detiene el plan y se reabre §2. **Prohibido relajar un test para llegar al conteo** (§3-11).

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F1 — Resolver único del estado final (módulo puro)

**Objetivo (1 frase):** una sola función pura que, dados el perfil y la config del empleado, diga **qué estado aplicar y por qué**, con precedencia declarada y determinista.
**Valor:** cierra C-e (no determinismo) y da la base para RC-1.

**Archivo a crear:** `backend/services/final_state_resolver.py`

```python
# backend/services/final_state_resolver.py
"""Plan 271 F1 — Resolutor ÚNICO del estado final al terminar un agente.

Puro: sin DB, sin red, sin config global mutable salvo la lectura de la flag.
Nunca lanza. Siempre devuelve una FinalStateDecision con `reason` no vacío.
"""
from __future__ import annotations
from typing import NamedTuple, Optional

# Precedencia CONGELADA, de mayor a menor. El primero que produce un estado gana.
PRECEDENCE: tuple[str, ...] = ("caller", "matrix", "role", "employee_config")

# Razones que ESTE módulo puede devolver.
REASONS: frozenset[str] = frozenset({
    "ok", "not_ok_status", "no_agent_type", "no_config", "flag_off",
})

# Catálogo COMPLETO de razones que cualquier escritor de estado puede emitir
# (§2.4 del plan 271). Fuente única para el mapa de la UI (F6) y para el test
# de cobertura. Agregar una razón nueva sin agregarla acá deja el test rojo.
ALL_FINAL_STATE_REASONS: frozenset[str] = frozenset({
    "ok", "flag_off", "not_ok_status", "no_ticket",
    "no_ado_id_or_stacky_project", "no_matrix_cell", "no_final_state",
    "state_not_applicable", "human_moved_out_of_flow", "exception",
    "no_config", "no_agent_type", "no_target_or_id", "already_in_state",
    "no_provider", "not_requested", "publish_not_ok", "review_mode_hold",
    "no_ticket_id", "ticket_lookup_failed", "no_ado_id",
    "ado_client_unavailable", "provider_unavailable",
})


class FinalStateDecision(NamedTuple):
    state: Optional[str]   # estado a aplicar; None = no aplicar
    source: str            # uno de PRECEDENCE, o "none"
    reason: str            # uno de REASONS. NUNCA vacío.


def role_fallback_enabled() -> bool:
    """Lee la INSTANCIA config.config (NO el atributo de clase Config): con la
    clase, monkeypatch.setattr(config.config, ...) del test no voltea el branch.
    Mismo patrón que completion_state.matrix_enabled (completion_state.py:32-35)."""
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def resolve_final_state(
    *,
    caller_state: Optional[str] = None,
    matrix_state: Optional[str] = None,
    role_state: Optional[str] = None,
    employee_state: Optional[str] = None,
    agent_type: Optional[str] = None,
    final_status: str = "completed",
) -> FinalStateDecision:
    """Aplica PRECEDENCE. Pura. Nunca lanza."""
    ...
```

**Tabla de verdad exacta:**

| `final_status` | `agent_type` | `caller` | `matrix` | `role` | `employee` | flag rol | → `state` | `source` | `reason` |
|---|---|---|---|---|---|---|---|---|---|
| `"completed"` | `"technical"` | `"X"` | `"A"` | `"B"` | `"C"` | ON | `"X"` | `caller` | `ok` |
| `"completed"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | ON | `"A"` | `matrix` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `"B"` | `"C"` | ON | `"B"` | `role` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `"B"` | `"C"` | **OFF** | `None` | `none` | `flag_off` |
| `"completed"` | `"technical"` | `None` | `None` | `None` | `"C"` | ON | `"C"` | `employee_config` | `ok` |
| `"completed"` | `"technical"` | `None` | `None` | `None` | `None` | ON | `None` | `none` | `no_config` |
| `"completed"` | `None` | `None` | `"A"` | `None` | `None` | ON | `None` | `none` | `no_agent_type` |
| `"error"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | ON | `None` | `none` | `not_ok_status` |
| `"needs_review"` | `"technical"` | `None` | `"A"` | `"B"` | `"C"` | ON | `None` | `none` | `not_ok_status` |
| `"completed"` | `"technical"` | `"X"` | `None` | `None` | `None` | **OFF** | `"X"` | `caller` | `ok` |

**Casos borde obligatorios:** strings `""` y `"   "` se tratan como `None` (`.strip()` antes de evaluar). El `caller_state` **ignora la flag** (última fila: es una decisión explícita de quien llama, no del fallback). `final_status` se compara en minúsculas y `strip()`.

> **Por qué `needs_review` NO transiciona:** exige revisión humana; auto-transicionar violaría HITL. Mismo criterio que `completion_state.py:16-25`.

> **Sinceramiento de alcance (C12).** En este plan **solo F2/F2-bis** consumen el resolver, y le pasan `matrix_state` y `role_state`. `caller` y `employee_config` existen porque el motor B ya los tiene (`agent_completion_internal.py:247-258`), y quedan **preparados pero sin productor** hasta el plan 272. No se los describe como "unificados": están **declarados**. Esto es deuda consciente, no un descuido.
>
> **`on_failure_state` (C16):** `_resolve_transition_state_from_config` también resuelve `on_failure_state` para `final_status in {"error","needs_review"}` (`agent_completion_internal.py:249,352`). El resolver de F1 **no lo modela** y devuelve `not_ok_status` para todo lo que no sea `completed`. Mientras el motor B no use el resolver (o sea, en todo este plan), no hay pérdida. **Cablear el resolver en el motor B sin modelar `on_failure_state` sería una regresión**: queda escrito acá para el 272.

**Archivo de test a crear:** `backend/tests/test_plan271_final_state_resolver.py`
**Casos:** las **10** filas de la tabla, una por test, + 2 de casos borde (`""` y `"  "`), + 1 que afirma `PRECEDENCE == ("caller","matrix","role","employee_config")`, + 1 que afirma `REASONS ⊆ ALL_FINAL_STATE_REASONS`. Total: **14 tests**.

**Flag que la protege:** `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` — **default ON**. Las 7 patas de §3.1 se cablean **en esta fase**:
1. `backend/config.py` — junto al bloque `STACKY_ADO_STATE_MATRIX_ENABLED` (`:1401-1406`).
2. `backend/services/harness_flags.py` — `FlagSpec` inmediatamente después del de `STACKY_ADO_STATE_MATRIX_ENABLED` (`:2795-2807`).
3. `backend/services/harness_flags.py` — key en `_CATEGORY_KEYS["flujo_funcional"]` (`:268-273`).
4. `backend/services/harness_flags_help.py` — `PlainHelp` junto al de `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` (`:893-898`).
5. `backend/harness_defaults.env` — `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED=true` (orden alfabético).
6. `backend/tests/test_plan271_flags.py` (crear acá; se completa con las otras 3 keys en F3/F4/F5).
7. Registrar `test_plan271_final_state_resolver.py` y `test_plan271_flags.py` en `run_harness_tests.sh` **y** `.ps1`.

**Texto del `PlainHelp` (verificado contra las restricciones REALES de §3.1 pata 4):**
```python
"STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED": PlainHelp(
    what="Hace que el estado al que configuraste que pase la incidencia cuando el empleado termina se aplique de verdad.",
    on_effect="Si la activás: al terminar el empleado, la incidencia pasa al estado que elegiste en la pantalla de Estados.",
    off_effect="Si la apagás: la incidencia se queda en el estado en que estaba y la tenés que mover a mano.",
    example="Como que el trámite avance solo de ventanilla cuando el funcionario lo termina, en vez de quedarse en el mostrador.",
),
```
> Chequeado: `what`=113 chars (10..200 ✔), `on_effect`=116 (≤240 ✔, empieza con `"Si "` ✔), `off_effect`=104 ✔, `example`=121 (≤300 ✔). Sin palabras de la denylist, sin `SCREAMING_SNAKE`, sin `F\d`.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_final_state_resolver.py" -v
```

**Criterio de aceptación (BINARIO):** `14 passed`. **Y** `test_harness_flags.py` y `test_harness_flags_help.py` verdes (dos comandos, **por archivo**). Si alguno de esos dos ya venía rojo, se prueba con un worktree en el commit base y se declara como rojo ajeno (§4-F7).

**Impacto por runtime:** ninguno — módulo puro sin consumidores todavía. **Trabajo del operador: ninguno.**

---

### F2 — Cablear el resolver en el motor A (cierra RC-1)

**Objetivo (1 frase):** que `completion_state.maybe_apply_state_transition` honre el `next_state_ok` de nivel rol cuando la matriz no define estado final, en lugar de descartarlo.
**Valor:** **cierra la causa raíz primaria** por el camino común a los 3 runtimes.

**Archivo a editar:** `backend/services/completion_state.py`

**Diff — reemplazar `:88-99`:**

```python
# ANTES (completion_state.py:88-99)
plan = resolve_task_state_plan(profile, agent_type, work_item_type)
ctx["source"] = plan.source
if plan.source != "matrix":
    return _logged(ctx, ev, {"skipped": True, "reason": "no_matrix_cell", "source": plan.source})
target = plan.final_ok
ctx["target"] = target
if not target:
    return _logged(ctx, ev, {"skipped": True, "reason": "no_final_state"})
if target not in applicable_states(plan):
    return _logged(ctx, ev, {"skipped": True, "reason": "state_not_applicable"})

# DESPUÉS
plan = resolve_task_state_plan(profile, agent_type, work_item_type)
from services.final_state_resolver import resolve_final_state

# La matriz sigue mandando cuando DEFINE ESTADO FINAL (comportamiento 208 intacto).
matrix_state = plan.final_ok if plan.source == "matrix" else None
# C13 — celda PARCIAL: source=="matrix" con final_ok=None (task_states.py:107-108).
# El nivel de rol NO puede quedar enterrado por una celda que solo trae in_progress.
role_machine = (profile.get("tracker_state_machine") or {}).get(agent_type) or {}
role_state = (role_machine.get("next_state_ok") or "").strip() or None
decision = resolve_final_state(
    matrix_state=matrix_state,
    role_state=role_state,
    agent_type=agent_type,
    final_status=final_status,
)
ctx["source"] = decision.source
ctx["target"] = decision.state
ctx["plan_source"] = plan.source
if decision.state is None:
    # Nunca mudo: `reason` viene del conjunto cerrado REASONS.
    return _logged(ctx, ev, {"skipped": True, "reason": decision.reason,
                             "source": decision.source, "plan_source": plan.source})
target = decision.state
# CENTINELA EN RUNTIME: conjunto cerrado = lo aplicable del plan MÁS el nivel rol,
# porque `role_state` puede no estar en applicable_states(plan) cuando el plan vino
# de una celda parcial (plan.final_ok is None ⇒ applicable_states no lo contiene).
permitidos = set(applicable_states(plan))
if role_state:
    permitidos.add(role_state)
if target not in permitidos:
    return _logged(ctx, ev, {"skipped": True, "reason": "state_not_applicable",
                             "target": target})
```

> **Por qué `role_state` se lee del perfil y no de `plan.final_ok` (C13).** El v1 hacía `role_state = plan.final_ok if plan.source == "config" else None`. Eso funciona para el caso simple, pero deja el agujero de celda parcial: cuando `source=="matrix"` con `final_ok=None`, `plan.final_ok` es `None` y el rol nunca se consulta. Leer `tracker_state_machine[agent_type]["next_state_ok"]` directo del perfil cierra los dos casos con una sola línea. `_machine_for` (`task_states.py:50-55`) hace lo mismo, pero es privado: replicar las dos líneas es más barato que exportarlo.

**Lo que NO se toca en esta fase (invariantes duros):**
- `_origin_guard` (`:121-161`) se llama **antes** de `_safe_transition`, igual que hoy (`:108-111`). Es la guardia HITL.
- `_OK_STATUSES` (`:24-25`) queda en `{"completed"}`. `needs_review` sigue sin transicionar.
- `matrix_enabled()` (`:28-37`) sigue siendo el gate maestro del motor A.

**Cambio de contrato de log — declarado (C22).** Tras F2, el motor A deja de emitir `no_matrix_cell` y `no_final_state` y pasa a emitir `no_config`/`no_agent_type`/`flag_off`. Las dos legacy **se conservan en `ALL_FINAL_STATE_REASONS`** para que las filas históricas de `SystemLog action="completion.matrix_transition"` sigan teniendo etiqueta en la UI. Escribilo en el docstring del módulo.

**Archivo de test a crear:** `backend/tests/test_plan271_role_fallback.py`
**Casos (9):**
1. Rol con `next_state_ok="To Do"`, sin `by_work_item_type` ⇒ `ok=True`, `to="To Do"`, `ctx.source="role"`. **(El bug reportado.)**
2. Matriz con celda **completa** para `work_item_type="Bug"` y rol distinto ⇒ gana la matriz, `source="matrix"`.
3. Matriz configurada pero `ticket.work_item_type` NULL ⇒ cae a rol, `source="role"`, transiciona.
4. **Celda PARCIAL** (`by_work_item_type["Bug"] = {"in_progress": "Doing"}`) + rol con `next_state_ok` ⇒ transiciona al de rol, `source="role"`. **(C13.)**
5. Ni matriz ni rol ⇒ `skipped`, `reason="no_config"`, `reason` no vacío.
6. Flag `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED=False` + solo rol ⇒ `skipped`, `reason="flag_off"` (byte-idéntico a hoy).
7. `_origin_guard` sigue bloqueando: `FakeProvider(current_state="Cerrado a mano")` fuera del flujo ⇒ `reason="human_moved_out_of_flow"`, **`prov.writes == []`**.
8. `final_status="needs_review"` ⇒ `skipped`, `reason="not_ok_status"`, sin escritura.
9. `role_state` no vacío pero distinto de todo lo aplicable **y sin rol en el perfil** (perfil manipulado) ⇒ `state_not_applicable`, sin escritura.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_role_fallback.py" -v
```

**Criterio de aceptación (BINARIO):**
- `9 passed`.
- **Y** de `test_plan271_caracterizacion.py`: `test_rc1_rol_sin_matriz_deberia_transicionar` y `test_rc1_celda_parcial_no_debe_enterrar_el_nivel_rol` pasan a **VERDE**; los otros 2 siguen rojos. Conteo esperado: `2 passed, 2 failed`.
- **Y** `pytest backend/tests/test_plan79_apply_final.py` y `pytest backend/tests/test_plan79_centinela_estados.py` siguen verdes (**por archivo**): usan `resolve_task_state_plan`/`applicable_states`, que esta fase **no** modifica.

**Flag:** `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` (cableada en F1). **Default ON.**
**Impacto por runtime:** los 3 cierran por `ticket_status.on_execution_end` → post-hook (`completion_dispatcher.py:8-10`), así que la corrección aplica a Codex CLI, Claude Code CLI y Copilot **por construcción**. Fallback: flag OFF ⇒ los 3 vuelven al comportamiento de hoy.
**Trabajo del operador: ninguno.**

---

### F2-bis — `[ADICIÓN ARQUITECTO]` Árbitro anti-doble-escritura y respeto del gate de build

**Objetivo (1 frase):** que activar F2 no convierta al motor A en un pisador del motor C (gate del plan 210) ni del motor B.
**Valor:** cierra **C2** (regresión del plan 210) y **C11** (carrera daemon vs inline). Sin esta fase, F2 es una regresión disfrazada de fix.

#### El problema, con evidencia

1. **Gate de build (C2).** El motor C aplica `dev_build_verify.gate_final_state` antes de escribir (`api/tickets.py:576-582`): cuando el Developer no tiene veredicto de máquina fresco, **degrada** el `target` o lo anula. `grep -c dev_build_verify backend/services/completion_state.py` ⇒ **0**. Hoy da igual porque el motor A nunca transiciona sin matriz. **Con F2 sí transiciona**, y puede sobrescribir la degradación que el 210 acaba de aplicar. Eso reabre el "falso Build OK" que los planes 210/211 cerraron.
2. **Carrera (C11).** `close_execution_with_publish` encola el motor A en el Paso 2 (`agent_completion_internal.py:183`) y escribe con el motor B en el Paso 4 (`:274`), **en el mismo hilo**. El motor A lo drena un **daemon de fondo** (`completion_dispatcher.py:98-120`). El orden no está definido, y los targets pueden diferir: el motor A usa `tracker_state_machine.<rol>.next_state_ok` y el motor B usa `agent_workflow_configs[<filename>].transition_state`. La idempotencia de `_safe_transition` (`task_states.py:164-168`) solo salva si los targets **coinciden**.

#### Lo que se construye

**Archivo a editar:** `backend/services/completion_state.py`. Dos guardias, ambas **antes** de `_safe_transition` y **después** de `_origin_guard`:

```python
# GUARDIA 1 (C2) — respetar el gate de build del plan 210, igual que api/tickets.py:576-582.
try:
    from services import dev_build_verify as _dbv
    _ws = _dbv.workspace_root_for_ado(int(ado_id))
    _exec_id = ev.get("execution_id") or _dbv.latest_execution_id_for_ado(int(ado_id))
    target, _gate = _dbv.gate_final_state(
        project_name=stacky_project, agent_type=agent_type, ado_id=int(ado_id),
        workspace_root=_ws, proposed_state=target, execution_id=_exec_id,
    )
    if target is None:
        return _logged(ctx, ev, {"skipped": True, "reason": "dev_build_gate_no_state",
                                 "gate_reason": _gate.get("reason")})
    ctx["target"] = target
except Exception:  # noqa: BLE001 — el gate jamás rompe el cierre
    logger.debug("gate_final_state falló en motor A (no crítico)", exc_info=True)

# GUARDIA 2 (C11) — árbitro por execution_id: si el MOTOR B ya escribió el estado
# final de esta misma ejecución, no volvemos a escribir.
# ALCANCE (§2.1bis): cubre A vs B, que es la carrera que F2 agrava. NO cubre los
# motores C ni D (viven en api/tickets.py, intocable acá) — eso es del plan 272.
if _final_state_already_written(ev.get("execution_id")):
    return _logged(ctx, ev, {"skipped": True, "reason": "already_written_by_other_engine"})
```

**Helper `_final_state_already_written(execution_id) -> bool`:** lee `AgentExecution.metadata_dict.get("final_state_outcome")` (la key que **F5** persiste) y devuelve `True` si existe con `applied is True`. Best-effort: si no puede leer, devuelve `False` (fail-open, nunca bloquea).

> **Orden de fases (importante).** F2-bis **depende de F5** para que la key exista. Por eso se implementa **después** de F5 aunque su número sea "2-bis": ver §7.2. Mientras F5 no exista, `_final_state_already_written` devuelve siempre `False` y la guardia 2 es un no-op inofensivo. **No es un ciclo**: la guardia 1 (la que evita la regresión del 210) es independiente y se implementa junto con F2.

**Razones nuevas al catálogo:** `dev_build_gate_no_state` y `already_written_by_other_engine`. **Agregalas a `ALL_FINAL_STATE_REASONS` (F1) y al mapa de F6** ⇒ el catálogo pasa de 23 a **25**.

**Archivo de test a crear:** `backend/tests/test_plan271_arbitro.py`
**Casos (5):**
1. `gate_final_state` devuelve `(None, {"reason": "build_stale"})` ⇒ `skipped`, `reason="dev_build_gate_no_state"`, **`prov.writes == []`**.
2. `gate_final_state` devuelve `("En revisión", {...})` (degradación) ⇒ se escribe **"En revisión"**, no el `next_state_ok` crudo.
3. `gate_final_state` lanza ⇒ el cierre sigue y se escribe el target original (fail-open).
4. `metadata_dict` ya trae `final_state_outcome.applied=True` ⇒ `skipped`, `reason="already_written_by_other_engine"`, sin escritura.
5. `metadata_dict` trae `final_state_outcome.applied=False` ⇒ **sí** escribe (un skip previo no bloquea el reintento).

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_arbitro.py" -v
```

**Criterio de aceptación (BINARIO):**
- `5 passed`.
- **Y** `pytest backend/tests/test_plan210_state_gate.py` sigue verde (**por archivo**). Si ya venía rojo, probalo con un worktree en el commit base y declaralo.
- **Y** `test_plan271_role_fallback.py` sigue en `9 passed` (la guardia no debe cambiar ningún caso feliz).

**Flag:** ninguna propia (vive dentro del camino de `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED`). Una guardia que solo **reduce** escrituras no necesita interruptor: apagarla sería pedir el bug.
**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F3 — El escritor del chokepoint rutea por provider (paridad ADO ↔ GitLab)

**Objetivo (1 frase):** que `_attempt_state_change` deje de ser ADO-only y escriba en el tracker que **el proyecto del ticket** declara.
**Valor:** cierra E-3. En un proyecto GitLab, hoy este camino escribe en ADO con un `iid` de GitLab.

**Archivo a editar:** `backend/services/agent_completion_internal.py`. Esta fase toca **cuatro** puntos (el v1 decía "solo el cuerpo" y a la vez pedía tres cambios más — contradicción corregida):
1. La firma de `_attempt_state_change` (`:502-504`).
2. Su cuerpo (`:526-553`).
3. El call site del Paso 4 (`:274-278`).
4. El call site de `publish_execution_from_review` (`:476-480`).
Más dos helpers nuevos al final del bloque de helpers.

**Firma nueva:**
```python
def _attempt_state_change(
    *, ticket_id: int | None, target_state: str, execution_id: int,
    project_name: str | None = None,
) -> dict:
```
Los dos call sites lo pasan: `:274-278` usa `stacky_project_name` (ya leído en `:135`) y `:476-480` usa `project_name` (ya leído en `:461`).

**Diff — reemplazar `:526-553`:**

```python
# ANTES (:526-541)
try:
    from services.ado_client import AdoClient
except ImportError as exc:
    return {"skipped": True, "reason": "ado_client_unavailable"}
try:
    AdoClient().update_work_item_state(int(ado_id), target_state)
    return {"ok": True, "to": target_state, "ado_id": ado_id}
except Exception as exc: ...

# DESPUÉS
# C6 — REGLA DURA: sin project_name NO se rutea. get_tracker_provider(None)
# resuelve el proyecto ACTIVO (tracker_provider.py:127), que puede ser GitLab
# mientras el ticket es de ADO: eso sería exactamente el bug que esta fase cierra.
if _writer_routed_enabled() and project_name:
    try:
        from services.tracker_provider import get_tracker_provider
        provider = get_tracker_provider(project_name)
    except Exception as exc:  # noqa: BLE001 — tracker mal configurado, GitLab off, etc.
        logger.warning("[exec=%s] provider no disponible: %s", execution_id, exc)
        return {"skipped": True, "reason": "provider_unavailable", "error": str(exc)}
    from harness.task_states import _safe_transition
    result = _safe_transition(
        provider, ado_id, target_state,
        phase="final_config", legacy_client_fn=_legacy_ado_client,
    )
    result.setdefault("ado_id", ado_id)
    # C7 — `_safe_transition` hardcodea {"source": "config"} en el éxito
    # (task_states.py:178). Ese valor NO es el origen de la decisión y rompería
    # el `setdefault("source", target_source)` del Paso 4. Se saca acá.
    if result.pop("source", None) is not None:
        result["writer"] = "safe_transition"
    return result
# Camino legacy byte-idéntico (flag OFF, o sin project_name): ver bloque ANTES.
```

**Helpers nuevos (al final del bloque de helpers):**
```python
def _writer_routed_enabled() -> bool:
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def _legacy_ado_client():
    from services.ado_client import AdoClient
    return AdoClient()
```

**Por qué `_safe_transition` y no una función nueva:** el plan 79 lo declara *"ÚNICA función que escribe estado"* (`harness/task_states.py:155`, docstring; el `def` está en `:146`). Ya trae idempotencia (`:164-168`) y ya es provider-agnóstica (`:171-177`). Escribir otra sería crear un **quinto** escritor.

> **Gotcha real de GitLab:** los write viven en `services/gitlab_provider.py`, **no** en el client. `update_item_state` está en `gitlab_provider.py:228`. `get_tracker_provider` (`tracker_provider.py:125-157`) exige `STACKY_GITLAB_ENABLED` y lanza `TrackerConfigError` si está OFF (`:133-136`) — por eso el `except` devuelve `provider_unavailable` en vez de romper el cierre.

#### F3-bis — adaptación OBLIGATORIA del doble de `test_output_watcher.py` (C5)

**Esto NO es opcional y NO es relajar un test.** El v1 declaraba `test_output_watcher.py` verde como criterio binario, y **F3 lo rompe**. La cadena real:

`_attempt_state_change` → `get_tracker_provider(project)` → `AdoTrackerProvider.__init__` (`ado_provider.py:34-36`) → `build_ado_client(project_name=project)` (`services/project_context.py`, que hace `from services.ado_client import AdoClient` **dentro** de la función ⇒ el monkeypatch del test **sí** aplica) → `AdoClient(org=..., project=..., auth_path=...)`.

Pero el doble del test es (`backend/tests/test_output_watcher.py:359-361`):
```python
class _FakeAdoClient:
    def update_work_item_state(self, ado_id, state):
        calls.append((ado_id, state))
```
**No acepta kwargs en el constructor** ⇒ `TypeError` ⇒ el `except` de F3 devuelve `provider_unavailable` ⇒ `assert calls == [(40109, "Reviewed by Dev")]` (`:370-371`) **falla**. Y además `_safe_transition` llama `provider.get_item(...)` → `self._client.get_work_item(int(item_id))` (`ado_provider.py:66-67`), que el doble tampoco tiene.

**Cambio exacto y mínimo (el assert NO se toca):** en los **tres** dobles de ese archivo (`:359-361`, `:385-387`, `:412-414`) agregar:
```python
    def __init__(self, *args, **kwargs):
        pass

    def get_work_item(self, ado_id):
        return {"fields": {"System.State": "Doing"}}
```
`"Doing"` a propósito: distinto del target, para que la idempotencia de `_safe_transition` **no** saltee la escritura y `calls` se llene igual que hoy. El doble ahora modela el constructor real de `AdoClient`; eso es **corregir un doble incompleto**, no aflojar la prueba.

**Archivo de test a crear:** `backend/tests/test_plan271_writer_routed.py`
**Casos (8):**
1. Proyecto ADO ⇒ `get_tracker_provider` devuelve `AdoTrackerProvider`; `provider.update_item_state("4242", "To Do")` exactamente una vez.
2. Proyecto GitLab ⇒ se llama `update_item_state` del `GitLabTrackerProvider`, **y no** `AdoClient`.
3. `get_tracker_provider` lanza ⇒ `{"skipped": True, "reason": "provider_unavailable"}` y `close_execution_with_publish` **no** lanza.
4. Idempotencia: `provider.get_item` devuelve el estado ya igual al target ⇒ `{"skipped": True, "reason": "already_in_state"}` sin escribir.
5. Flag OFF ⇒ camino legacy: `AdoClient().update_work_item_state(4242, "To Do")` (byte-idéntico a hoy).
6. `ado_id` es `None` ⇒ `{"skipped": True, "reason": "no_ado_id"}` (`:523-524`, preservado).
7. **`project_name=None` con la flag ON ⇒ camino legacy `AdoClient`, NUNCA `get_tracker_provider`.** (C6.)
8. Éxito ruteado ⇒ el dict devuelto **no** trae `source` (para que `setdefault("source", target_source)` del Paso 4 siga funcionando) y sí trae `writer="safe_transition"`. (C7.)

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_writer_routed.py" -v
```

**Criterio de aceptación (BINARIO):**
- `8 passed`.
- **Y** `test_e3_el_escritor_rutea_por_provider` de F0 pasa a **VERDE** (conteo de F0: `3 passed, 1 failed`).
- **Y** `pytest backend/tests/test_output_watcher.py` verde **después** de F3-bis — **por archivo, hasta 3 reintentos si aparece `SQLITE_LOCKED`**. Si sigue rojo con F3-bis aplicado, **se detiene la fase y se reporta**; no se borra el assert.
- **Y** `pytest backend/tests/test_u2_publish_review_mode.py` verde: su doble es `lambda **_kwargs: {...}` (`:158-162`), que acepta el kwarg nuevo `project_name` sin cambios.

**Flag:** `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED` — **default ON**. Cablear las 7 patas; agregar la key a `test_plan271_flags.py`.
**Impacto por runtime:** ninguno específico — el chokepoint es común a los 3. Fallback: flag OFF ⇒ `AdoClient` directo, idéntico a hoy.
**Trabajo del operador: ninguno.**

---

### F4 — Gate de publish preciso (cierra RC-2)

**Objetivo (1 frase):** que el estado deje de bloquearse cuando no había nada que publicar, conservando el bloqueo cuando la publicación se intentó y falló.
**Valor:** cierra la causa raíz secundaria. Va **después** de F3 para que la escritura que se desbloquea ya vaya al tracker correcto.

**Archivo a editar:** `backend/services/agent_completion_internal.py` — el bloque `:260-280` (Paso 4) y un helper nuevo.

```python
# Razones de publish que significan "no había nada que publicar" ⇒ el gate es espurio.
_PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR: frozenset[str] = frozenset({
    "html_output_path_missing",     # :228-234
    "already_terminal_no_html",     # :228-234 (rama already_terminal)
    "auto_publish_disabled",        # :236-238
    "ado_publisher_unavailable",    # :617-626
})


def _publish_gate_blocks(publish_result: dict) -> bool:
    """True si el gate de publish debe seguir bloqueando el cambio de estado."""
    if publish_result.get("ok"):
        return False                      # publicó bien: nunca bloquea
    if not _publish_gate_precise_enabled():
        return True                       # legacy: cualquier no-ok bloquea
    return publish_result.get("reason") not in _PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR
```

**Diff — reemplazar `:265-280`:**

```python
# DESPUÉS
if not effective_target:
    state_result = {"skipped": True, "reason": "not_requested"}
elif final_status == "completed" and _publish_gate_blocks(publish_result):
    state_result = {"skipped": True, "reason": "publish_not_ok",
                    "publish_status": publish_result.get("reason") or publish_result.get("event")}
else:
    state_result = _attempt_state_change(
        ticket_id=ticket_id, target_state=effective_target,
        execution_id=execution_id, project_name=stacky_project_name,   # ← F3
    )
    # C7 — asignación EXPLÍCITA, no setdefault: `target_source` es el origen de la
    # DECISIÓN y debe ganar. `_attempt_state_change` ya no devuelve `source` (F3).
    if isinstance(state_result, dict) and target_source:
        state_result["source"] = target_source
```

**Lo que NO se toca (invariantes duros):**
- El early-return de `review_mode_hold` (`:210-224`) **queda igual**. Es HITL deliberado. Su razón se vuelve visible en F5; su semántica no cambia.
- `publish.failed` y `publish.idempotent_replay` **siguen bloqueando**: ahí sí hubo un intento de publicación que no llegó.

**Archivo de test a crear:** `backend/tests/test_plan271_publish_gate.py`
**Casos (8) — tabla de verdad, uno por fila:**

| # | `publish_result` | flag | `_publish_gate_blocks` | `ado_state_change` esperado |
|---|---|---|---|---|
| 1 | `{"ok": True, ...}` | ON | `False` | `ok=True` |
| 2 | `{"skipped": True, "reason": "html_output_path_missing"}` | ON | `False` | `ok=True` ← **el bug** |
| 3 | `{"skipped": True, "reason": "auto_publish_disabled"}` | ON | `False` | `ok=True` |
| 4 | `{"skipped": True, "reason": "ado_publisher_unavailable"}` | ON | `False` | `ok=True` |
| 5 | `{"skipped": True, "reason": "already_terminal_no_html"}` | ON | `False` | `ok=True` |
| 6 | `{"ok": False, "event": "publish.failed", "reason": "ADO 400"}` | ON | `True` | `skipped`, `reason="publish_not_ok"` |
| 7 | `{"ok": False, "event": "publish.idempotent_replay"}` | ON | `True` | `skipped`, `reason="publish_not_ok"` |
| 8 | `{"skipped": True, "reason": "html_output_path_missing"}` | **OFF** | `True` | `skipped`, `reason="publish_not_ok"` (byte-idéntico a hoy) |

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_publish_gate.py" -v
```

**Criterio de aceptación (BINARIO):**
- `8 passed`.
- **Y** `test_rc2_sin_html_no_debe_bloquear_la_transicion` de F0 pasa a **VERDE** ⇒ los **4 de F0 quedan verdes**.
- **Y** `pytest backend/tests/test_b2_transition_from_config.py` verde (5 tests, `:28,42,63,73,83`) — **y registralo en `run_harness_tests.sh` y `.ps1`: hoy NO está registrado** (verificado: `grep -c` devuelve `0` en ambos).
- **Y** `pytest backend/tests/test_u2_publish_review_mode.py` verde.
- **Y** `pytest backend/tests/test_output_watcher.py` verde: F4 desbloquea el modo A (`:618` cierra con `html_output_path=None`), así que si algún test asumía "modo A nunca cambia estado", **se detiene la fase y se reporta** — el comportamiento nuevo es el correcto, pero el cambio de expectativa se documenta explícitamente, no se silencia.

**Flag:** `STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED` — **default ON**, justificación en §3.2. Cablear las 7 patas.
**Impacto por runtime:** el chokepoint es común a los 3. En Copilot/vscode_bridge el cierre suele venir por `output_watcher` (`:412`) con `html_output_path` presente ⇒ el caso 2 casi no aplica; en Codex/Claude CLI el cierre por `api/tickets.py:1386` puede venir sin HTML ⇒ ahí el fix se nota. Fallback: flag OFF ⇒ comportamiento actual, idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F5 — La razón del no-cambio se persiste (backend)

**Objetivo (1 frase):** que la razón por la que un ticket no se movió quede escrita en el `metadata_json` de la ejecución y se promueva en el payload de `/api/executions/<id>`.
**Valor:** cierra RC-3 del lado backend. Hoy la razón muere en `CloseResult` y en `SystemLog`.

**Archivos a editar:**
1. `backend/services/agent_completion_internal.py` — persistir antes del `return CloseResult(...)` (`:290-298`).
2. `backend/services/completion_state.py` — persistir dentro de `_logged` (`:164-191`).
3. `backend/api/executions.py` — promover la key en `_with_outcome` (`:65-92`).

**Nombres exactos:**
- Key en `metadata_json`: **`final_state_outcome`**.
- Forma congelada: `{"applied": bool, "to": str|None, "source": str, "reason": str, "at": "<iso8601>Z"}`.
- Key promovida en el payload HTTP: **`final_state_outcome`** (mismo nombre, nivel superior).
- Helper en `agent_completion_internal.py`: `_persist_final_state_outcome(*, execution_id, result, source=None) -> None` — best-effort, nunca lanza, modelado sobre `_set_publish_hold` (`:419-431`), que ya hace este patrón de merge en `metadata_dict`.
- `completion_state.py` lo **importa** (import local dentro de `_logged`, para no acoplar el daemon).

```python
def _persist_final_state_outcome(*, execution_id: int, result: dict,
                                 source: str | None = None) -> None:
    """Plan 271 F5 — deja la razón del cambio (o del no-cambio) donde la UI ya mira.
    Best-effort: nunca lanza, nunca bloquea el cierre."""
    if not _reason_visible_enabled() or not execution_id:
        return
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            md = dict(row.metadata_dict or {})
            md["final_state_outcome"] = {
                "applied": bool(result.get("ok")),
                "to": result.get("to"),
                # C7 — el `source` EXPLÍCITO gana. `_safe_transition` hardcodea
                # {"source": "config"} en el éxito (task_states.py:178) y ese valor
                # NO es el origen de la decisión.
                "source": source or result.get("source") or "none",
                "reason": result.get("reason") or ("ok" if result.get("ok") else "unknown"),
                "at": _utc_now_iso(),
            }
            row.metadata_dict = md
    except Exception:  # noqa: BLE001
        logger.debug("[exec=%s] persistir final_state_outcome falló (no crítico)",
                     execution_id, exc_info=True)
```

**Puntos de llamada exactos (4), con el `source` que le corresponde a cada uno:**

| # | Dónde | `result` | `source` |
|---|---|---|---|
| 1 | `agent_completion_internal.py`, antes del `return CloseResult(...)` de `:290` | `state_result` | `target_source` |
| 2 | `agent_completion_internal.py`, en el early-return de `review_mode_hold` (`:216-224`) | `{"skipped": True, "reason": "review_mode_hold"}` | `"none"` |
| 3 | `agent_completion_internal.py`, en `publish_execution_from_review` antes del `return` de `:493` | `state_result` | `"employee_config"` |
| 4 | `completion_state.py`, en `_logged` antes del `return result` de `:191` | `result` | `ctx.get("source")` |

**Edición en `api/executions.py` — C14, LEER ANTES DE ESCRIBIR.**
`_with_outcome` corta arriba de todo con `if not _outcome_badge_enabled(): return d` (`:75-76`), y esa flag es **ajena** (`STACKY_UI_OUTCOME_REASON_BADGE_ENABLED`, plan 254, default `True` en `config.py:2070-2071`). Si insertás la promoción después de ese corte, tu feature queda gateada por una flag que este plan no controla. **Insertá antes del corte:**

```python
def _with_outcome(d: dict, dirty_ids: set[int] | None = None) -> dict:
    # Plan 271 F5 — la razón del cambio de estado NO depende de la flag del 254.
    meta_271 = d.get("metadata") or {}
    if _reason_visible_enabled() and isinstance(meta_271, dict):
        fso = meta_271.get("final_state_outcome")
        if isinstance(fso, dict):
            d["final_state_outcome"] = fso
    if not _outcome_badge_enabled():
        return d
    ...  # resto sin cambios
```
Agregá `_reason_visible_enabled()` en `api/executions.py` con el mismo patrón de instancia que `_outcome_badge_enabled` (`:28-32`).

> `AgentExecution.to_dict` incluye `"metadata": self.metadata_dict` (`models.py:331`), así que `d.get("metadata")` funciona tanto en el listado como en el detalle (`get_execution`, `:232-242`).

> **Por qué acá y no un endpoint nuevo:** `_with_outcome` ya es el promotor canónico del plan 254, se aplica al listado y al detalle, y `ExecutionDetailDrawer.tsx:79-88` ya consume ese payload. Endpoint nuevo = superficie nueva sin necesidad.

**Archivo de test a crear:** `backend/tests/test_plan271_reason_persisted.py`
**Casos (8):**
1. Cierre con transición OK por el motor A ⇒ `metadata["final_state_outcome"] == {"applied": True, "to": "To Do", "source": "role", "reason": "ok", "at": <iso>}`. **(C7: `source` debe ser `"role"`, no `"config"`.)**
2. Cierre con `publish_not_ok` ⇒ `applied=False`, `reason="publish_not_ok"`.
3. Cierre en `review_mode_hold` ⇒ `applied=False`, `reason="review_mode_hold"`, `source="none"`.
4. Skip del motor A con `no_config` ⇒ `applied=False`, `reason="no_config"`.
5. Flag `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED=False` ⇒ la key **no** se agrega al metadata **ni** al payload (sin hueco ni error).
6. `GET /api/executions/<id>` devuelve `final_state_outcome` con la forma exacta.
7. **`STACKY_UI_OUTCOME_REASON_BADGE_ENABLED=False` + `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED=True` ⇒ `final_state_outcome` SIGUE presente** en el payload. **(C14.)**
8. `execution_id=None` ⇒ el helper no lanza y no escribe nada.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_reason_persisted.py" -v
```
> Este archivo toca la DB. Si aparece `SQLITE_LOCKED`, **volvé a correr el mismo archivo** (hasta 3 intentos). No corras la suite completa.

**Criterio de aceptación (BINARIO):**
- `8 passed`.
- **Y** `pytest backend/tests/test_plan254_*.py` — **cada archivo por separado** — sigue verde.

**Flag:** `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` — **default ON** (solo lectura). Cablear las 7 patas; `test_plan271_flags.py` ahora cubre **las 4**.
**Impacto por runtime:** ninguno. Fallback: flag OFF ⇒ ninguna key nueva, la UI no dibuja nada.
**Trabajo del operador: ninguno.**

---

### F6 — La razón se ve donde el operador ya mira (frontend)

**Objetivo (1 frase):** mostrar en el drawer de la ejecución, en castellano y con acción sugerida, por qué la incidencia se movió o por qué no.
**Valor:** cierra RC-3. El operador deja de necesitar leer logs.

**Archivos a crear:**
- `frontend/src/utils/finalStateOutcome.ts` — módulo **puro**.
- `frontend/src/utils/__tests__/plan271FinalStateOutcome.test.ts` — vitest sobre el módulo puro.
- `backend/tests/test_plan271_reason_catalog.py` — **el puente entre los dos idiomas (C8)**.

**Archivos a editar:**
- `frontend/src/types.ts` — campo opcional junto a `dirty_close_pending_review` (`:161`).
- `frontend/src/components/ExecutionDetailDrawer.tsx` — consumir el módulo y renderizar, junto al bloque `:79-88`.

> **Por qué un módulo `.ts` puro y no un test de render:** `@testing-library/react` y `jsdom` **no están instalados**. Mismo razonamiento que `frontend/src/utils/outcomeReason.ts:1-10` ya dejó escrito. **Copiá esa estructura.**

**Contenido del módulo — las 25 razones del catálogo (§2.4 + F2-bis), ni una más ni una menos:**

```ts
// frontend/src/utils/finalStateOutcome.ts
// Plan 271 F6 — mapa puro `final_state_outcome.reason` → etiqueta + tono + acción.
// El catálogo canónico vive en backend/services/final_state_resolver.py
// (ALL_FINAL_STATE_REASONS). `test_plan271_reason_catalog.py` verifica que este
// archivo cubra TODAS las razones de ese conjunto: agregar una allá sin agregarla
// acá deja el test rojo. NO cambies las keys sin cambiar el conjunto de Python.

export type FinalStateTone = "exito" | "atencion" | "espera" | "error";

export interface FinalStateLabel { label: string; tone: FinalStateTone; action: string; }

export interface FinalStateOutcome {
  applied?: boolean; to?: string | null; source?: string; reason?: string; at?: string;
}

export const FINAL_STATE_REASON_LABELS: Record<string, FinalStateLabel> = {
  // ── se movió ────────────────────────────────────────────────────────────
  ok:                 { label: "Movida al estado configurado", tone: "exito", action: "" },
  already_in_state:   { label: "Ya estaba en ese estado", tone: "exito", action: "" },
  // ── falta configurar (acción del operador) ──────────────────────────────
  no_config:          { label: "Nadie configuró a qué estado mover", tone: "atencion", action: "Configuralo en Ajustes → Estados, en la tarjeta del rol" },
  no_final_state:     { label: "El rol no tiene estado de salida", tone: "atencion", action: "Elegí 'Al terminar OK, mover a' en Ajustes → Estados" },
  no_matrix_cell:     { label: "Sin regla para este tipo de incidencia", tone: "atencion", action: "Configuralo en Ajustes → Estados, en la tarjeta del rol" },
  not_requested:      { label: "Sin estado destino para este cierre", tone: "atencion", action: "Configuralo en Ajustes → Estados" },
  state_not_applicable: { label: "El estado configurado no aplica a este rol", tone: "atencion", action: "Revisá los estados del rol en Ajustes → Estados" },
  flag_off:           { label: "El movimiento automático está apagado", tone: "atencion", action: "Prendé 'estado final del empleado' en Ajustes → Arnés" },
  // ── decisión humana / espera (no hay nada que arreglar) ─────────────────
  review_mode_hold:   { label: "En espera de tu revisión", tone: "espera", action: "Aprobá la publicación para que se mueva" },
  human_moved_out_of_flow: { label: "La moviste vos: Stacky no la pisó", tone: "espera", action: "" },
  not_ok_status:      { label: "No terminó bien: no se movió", tone: "espera", action: "Revisá el resultado antes de moverla" },
  dev_build_gate_no_state: { label: "Sin compilación verde reciente: no se movió", tone: "espera", action: "Corré el build y volvé a intentar" },
  already_written_by_other_engine: { label: "Ya la había movido otro paso del cierre", tone: "espera", action: "" },
  // ── error operable ──────────────────────────────────────────────────────
  publish_not_ok:     { label: "No se publicó el comentario: no se movió", tone: "error", action: "Mirá el error de publicación y reintentá" },
  no_ado_id:          { label: "La incidencia no tiene id en el tablero", tone: "error", action: "Vinculala al tablero" },
  no_ado_id_or_stacky_project: { label: "Falta el id en el tablero o el proyecto", tone: "error", action: "Revisá que la incidencia esté vinculada a un proyecto" },
  no_ticket:          { label: "No se encontró la incidencia", tone: "error", action: "Refrescá el tablero" },
  no_ticket_id:       { label: "La ejecución no está atada a una incidencia", tone: "error", action: "Revisá cómo se lanzó el empleado" },
  ticket_lookup_failed: { label: "No se pudo leer la incidencia", tone: "error", action: "Reintentá el cierre" },
  no_agent_type:      { label: "No se pudo saber qué rol terminó", tone: "error", action: "Revisá el empleado asignado a la incidencia" },
  no_target_or_id:    { label: "Faltó el estado destino o el id", tone: "error", action: "Configuralo en Ajustes → Estados" },
  // ── conexión con el tablero ─────────────────────────────────────────────
  provider_unavailable: { label: "No se pudo hablar con el tablero", tone: "error", action: "Revisá la conexión del tablero en Ajustes" },
  no_provider:        { label: "Sin conexión configurada al tablero", tone: "error", action: "Configurá la conexión en Ajustes" },
  ado_client_unavailable: { label: "Falta el conector del tablero", tone: "error", action: "Revisá la instalación" },
  exception:          { label: "Error inesperado al mover la incidencia", tone: "error", action: "Mirá el detalle de la ejecución" },
};

/** Un reason futuro NO rompe la UI: string crudo, tono neutro, nunca `undefined`. */
export function describeFinalState(o: FinalStateOutcome | null | undefined): FinalStateLabel | null {
  if (!o || !o.reason) return null;
  const known = FINAL_STATE_REASON_LABELS[o.reason];
  if (known) {
    if (o.reason === "ok" && o.to) return { ...known, label: `Movida a "${o.to}"` };
    return known;
  }
  return { label: o.reason, tone: "atencion", action: "" };
}
```

**Edición en `ExecutionDetailDrawer.tsx`** — junto al bloque de `:79-88`:
```tsx
// Plan 271 F6 — POR QUÉ la incidencia se movió (o no) al terminar.
const finalState = describeFinalState(
  content?.final_state_outcome ?? (metadata.final_state_outcome as FinalStateOutcome | undefined),
);
```
y renderizalo con las **cuatro** clases de tono. **C19:** `styles.toneEspera` **sí existe** (`ExecutionDetailDrawer.module.css:151`, comparte regla con `.toneAtencion`); el v1 mandaba usar solo tres. Extendé el patrón de `outcomeToneClass` (`:90-95`) a una cuarta rama para `espera`.

> **Ratchet de deuda UI (obligatorio):** en esta fase no se crea ningún `.tsx` nuevo, así que alcanza con **no introducir `style={{}}` inline** en el drawer. Usá clases del `.module.css`.

**Test de vitest (`plan271FinalStateOutcome.test.ts`) — 6 casos:**
1. `describeFinalState(null)` ⇒ `null`.
2. `describeFinalState({})` ⇒ `null`.
3. `describeFinalState({reason: "ok", to: "To Do"})` ⇒ `label` contiene `"To Do"`, `tone === "exito"`.
4. `describeFinalState({reason: "no_config"})` ⇒ `tone === "atencion"` y `action` **no vacío**.
5. `describeFinalState({reason: "inventado_futuro"})` ⇒ `label === "inventado_futuro"`, `tone === "atencion"`, no lanza.
6. **Estructural, no numérico:** toda entrada tiene `label` no vacío y `tone` en `{"exito","atencion","espera","error"}`. **(El v1 congelaba `length === 12`, que era el número equivocado.)**

**Test puente (`backend/tests/test_plan271_reason_catalog.py`) — 2 casos. `[ADICIÓN ARQUITECTO]` menor:**
```python
def test_toda_razon_del_backend_tiene_etiqueta_en_el_frontend():
    from pathlib import Path
    from services.final_state_resolver import ALL_FINAL_STATE_REASONS
    ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils"
          / "finalStateOutcome.ts").read_text(encoding="utf-8")
    faltan = sorted(r for r in ALL_FINAL_STATE_REASONS if f"\n  {r}:" not in ts
                    and f" {r}:" not in ts)
    assert faltan == [], f"razones sin etiqueta en la UI: {faltan}"
```
más un test simétrico que afirma que el `.ts` no tiene keys huérfanas fuera de `ALL_FINAL_STATE_REASONS`. **Esto es lo que impide que vuelva a pasar C8.**

**Comandos exactos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/utils/__tests__/plan271FinalStateOutcome.test.ts
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_reason_catalog.py" -v
```
> **Correr vitest por archivo.** La corrida completa tiene contaminación cross-file conocida en este repo.

**Criterio de aceptación (BINARIO):**
- `6 passed` en vitest, `2 passed` en `test_plan271_reason_catalog.py`, `tsc --noEmit` con **0 errores**.
- **Y** los ratchets de UI siguen verdes: correr **por archivo** los tests bajo `frontend/src/**/__tests__/` cuyo nombre contenga `ratchet` o `uiDebt`. Si alguno ya venía rojo por deuda ajena, se prueba con un worktree en el commit base y se declara.

**Flag:** `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` (cableada en F5). El frontend no lee la flag: si el backend no manda la key, `describeFinalState` devuelve `null` y no se dibuja nada. **Sin hueco ni error.**
**Impacto por runtime:** ninguno — es UI, común a los 3. **Trabajo del operador: ninguno.**

---

### F7 — Cierre: meta-tests, registro y huella de regresión

**Objetivo (1 frase):** garantizar que nada de lo agregado deja un meta-test rojo, que las 4 flags están completas en sus 7 patas, y que esta clase de error queda registrada.
**Valor:** evita el falso verde clásico (test nuevo que nadie corre porque no está en `HARNESS_TEST_FILES`).

**Checklist de archivos que DEBEN estar en AMBOS scripts al terminar (10):**
1. `tests/test_plan271_caracterizacion.py`
2. `tests/test_plan271_final_state_resolver.py`
3. `tests/test_plan271_flags.py`
4. `tests/test_plan271_role_fallback.py`
5. `tests/test_plan271_arbitro.py`
6. `tests/test_plan271_writer_routed.py`
7. `tests/test_plan271_publish_gate.py`
8. `tests/test_plan271_reason_persisted.py`
9. `tests/test_plan271_reason_catalog.py`
10. `tests/test_plan271_censo_escritores.py` (F8)
11. `tests/test_b2_transition_from_config.py` — **preexistente y hoy NO registrado**; este plan lo adopta.

> `backend/tests/plan271_helpers.py` **NO** se registra: no es un `test_*.py`.
> Formato: `.sh` ⇒ línea con dos espacios y **sin** comillas; `.ps1` ⇒ `"tests/..."` **con** comillas dobles dentro de `$HarnessTestFiles`.

**Huella de regresión (C20).** Si existe `Stacky Agents/docs/sistema/error_fingerprints.json`, agregá una entrada:
`{"id": "FS-271-NO-MATRIX-CELL", "patron": "completion.matrix_transition reason=no_matrix_cell con next_state_ok de rol configurado", "plan": 271, "fecha": "2026-07-28", "guard_test": "backend/tests/test_plan271_role_fallback.py::test_rol_sin_matriz_transiciona"}`.
Si el archivo **no** existe, no lo crees: dejá la línea en el PR y seguí.

**Comandos de verificación (corré los 5, uno por uno):**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_harness_flags.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_harness_flags_help.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_flags.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_caracterizacion.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m compileall -q "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\harness"
```

**Criterio de aceptación (BINARIO):**
- Los 4 archivos de pytest en verde y `compileall` sin salida.
- **Y** un `grep` de cada uno de los **11** nombres del checklist devuelve **≥1 hit en `.sh` y ≥1 hit en `.ps1`** (11 × 2 = **22 hits**, ni uno menos).
- **Y** los **4** tests de `test_plan271_caracterizacion.py` en **verde** (de `0 passed, 4 failed` en F0 a `4 passed` acá).

> **Alcance acotado a propósito.** El corpus es exactamente esos 11 archivos y esas 4 flags. Un rojo preexistente ajeno **no** es alcance de este plan: si aparece, se prueba que ya estaba rojo con un worktree en el commit base y se declara. Este criterio **no** dice "y si algo más queda rojo se arregla".

**Flag:** ninguna. **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

### F8 — `[ADICIÓN ARQUITECTO]` Censo ejecutable de escritores de estado

**Objetivo (1 frase):** que el repo sepa, y verifique en cada corrida, **cuántas** funciones escriben el estado de un work item y **quién es su plan dueño**.

**Por qué esta fase existe.** El v1 de este plan afirmó, con cuatro anclajes exactos, que *"conviven dos motores independientes"*. Había **cuatro**. Ese error casi hace que F2 pisara el gate de build del plan 210 (C2) sin que nadie lo notara. Ningún test podía atraparlo porque **el censo vivía en la cabeza de quien escribía el plan**. Esta fase lo mueve al repo. Es barata (un test AST, sin infraestructura nueva), determinista, idéntica en los 3 runtimes, y no agrega ni un clic al operador.

**Archivo a crear:** `backend/tests/test_plan271_censo_escritores.py`

**Qué hace, exactamente:**
1. Recorre con `ast` todos los `.py` bajo `backend/` **excluyendo** `backend/tests/`, `backend/.venv/` y `backend/venv/`.
2. Marca todo `ast.Call` cuyo `func` sea un `Attribute` con `attr in {"update_item_state", "update_work_item_state"}`, más toda llamada a `_safe_transition`.
3. Atribuye cada hallazgo a la **función que lo contiene** (`archivo::funcion`).
4. Compara el conjunto contra un allow-list **congelado en el propio test**, con el plan dueño de cada entrada:

```python
# 6 entradas = los CUATRO motores de §2.1 (A, B, C, D) más los dos helpers de
# plan 79 que ellos usan. La letra del motor va escrita a propósito: el v1 de este
# plan contó dos motores donde había cuatro, y nada en el repo lo desmentía.
ESCRITORES_CENSADOS: dict[str, str] = {
    "harness/task_states.py::_safe_transition":            "plan 79 — el escritor canónico (lo usan A, B y C)",
    "harness/task_states.py::apply_task_start_state":      "plan 79 — estado al INICIAR (fuera del alcance del 271)",
    "api/tickets.py::_apply_task_state":                   "MOTOR C — plan 79 + gate del 210 (el 271 NO lo modifica, §6.6)",
    "api/tickets.py::set_stacky_status_by_ado":            "MOTOR D — inline sin plan dueño (el 271 NO lo modifica; unificación en el 272)",
    "services/completion_state.py::maybe_apply_state_transition": "MOTOR A — plan 208 + 271 F2/F2-bis",
    "services/agent_completion_internal.py::_attempt_state_change": "MOTOR B — plan 271 F3",
}
```
5. Asserts:
   - `hallados - ESCRITORES_CENSADOS == set()` con el mensaje: *"Escritor de estado NUEVO sin censar: <x>. Agregalo al censo con su plan dueño, o rutealo por `_safe_transition`."*
   - `ESCRITORES_CENSADOS - hallados == set()` con el mensaje: *"Escritor censado que ya no existe: <x>. Sacalo del censo."*
6. Un tercer test afirma que **`services/completion_state.py` importa `dev_build_verify`** — el invariante concreto de C2: si alguien vuelve a sacar el gate de build del motor A, el test se pone rojo con el nombre del plan que se rompe (210).

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_censo_escritores.py" -v
```

**Criterio de aceptación (BINARIO):** `3 passed` con el allow-list en **exactamente 6 entradas** = los 4 motores de §2.1 más los 2 helpers de plan 79. Si el censo encuentra una **séptima entrada** que este plan no vio, **eso es el resultado**: se la agrega al allow-list con su plan dueño **en el mismo commit**, se dice si es un **quinto motor** o solo un helper, y se anota en §6 si merece su propio plan. **No se relaja el assert.**

> **AST, nunca regex.** Precedente del repo: un centinela textual sobre flags rompió el motor entero. El AST no confunde un string en un comentario con una llamada real.

**Flag:** ninguna (es un test). **Impacto por runtime:** ninguno. **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en el plan) |
|---|---|---|---|
| R1 | **Proyectos que hoy dependen de que el nivel de rol NO transicione** cambian de comportamiento al prender F2 (lo que el 208 quiso evitar). | Media | El destino sale de una UI cuyo texto literal es *"a cuál mueve el ticket al terminar"* (`StatesConfigPage.tsx:102`). `_origin_guard` (`completion_state.py:121-161`) sigue impidiendo pisar un ticket movido a mano, y la flag permite volver atrás sin redeploy. |
| R2 | F4 provoca transiciones que hoy no ocurren ⇒ escritura nueva en el tracker real. | Media | Acotado a **4 razones enumeradas** en `_PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR`. `publish.failed`, `publish.idempotent_replay` y `review_mode_hold` **siguen bloqueando**. Los casos 6/7/8 de F4 lo prueban. |
| R3 | **Doble transición / carrera A vs B.** El motor B escribe **inline** (`agent_completion_internal.py:274`) y el motor A lo hace desde un **daemon** (`completion_dispatcher.py:98-120`) encolado en `:183`. Con F2 el motor A pasa a escribir en el caso común, así que la superposición **aumenta**, no queda igual. | **Alta** (el v1 la declaraba Media y decía "no lo empeora" — **falso**) | **F2-bis guardia 2**: árbitro por `execution_id` que corta la segunda escritura. Más `_safe_transition` idempotente (`task_states.py:164-168`) cuando los targets coinciden, y `final_state_outcome.source` que hace visible cualquier discrepancia. |
| R3-bis | **Doble transición A vs C/D**, en el camino `PATCH /by-ado/<id>/stacky-status`. El árbitro **no** los cubre (§2.1bis). | Media | **Aceptada y declarada, no mitigada.** Ya ocurre hoy y este plan no toca `api/tickets.py` (§6.6), así que no la agrava en ese camino. F8 la deja **censada y visible**; extender el árbitro a C y D es alcance del **plan 272** (§6.1). |
| R4 | **Regresión del gate de build del plan 210**: el motor A pisa la degradación que el motor C acaba de aplicar. | **Alta sin F2-bis** | **F2-bis guardia 1** replica `dev_build_verify.gate_final_state` en el motor A, y **F8 test 3** deja rojo el repo si alguien lo saca. |
| R5 | `get_tracker_provider` lanza `TrackerConfigError` en un proyecto GitLab con `STACKY_GITLAB_ENABLED=false` y rompe el cierre. | Baja | F3 lo envuelve en `try/except` ⇒ `{"skipped": True, "reason": "provider_unavailable"}`. El cierre nunca falla (caso 3 de F3) y la razón se muestra (F6). |
| R6 | **F3 rompe `test_output_watcher.py`** porque el doble no modela el constructor real de `AdoClient`. | **Confirmada** (no es hipótesis) | **F3-bis** especifica el cambio exacto de los tres dobles sin tocar un solo assert, y el criterio dice explícitamente que si sigue rojo **se detiene y se reporta**. |
| R7 | `SQLITE_LOCKED` hace flaky a F5 y F2-bis. | Alta | §3-9 y repetido en cada fase: correr **por archivo**, reintentar hasta 3 veces el mismo archivo, nunca la suite completa. |
| R8 | El implementador toca `run_harness_tests.ps1` con la sintaxis del `.sh`. | Media | §3-10 y F7 dan la diferencia literal. El criterio de F7 exige **22 hits**, 11 por script. |
| R9 | El texto del `PlainHelp` rompe uno de los meta-tests. | Media | §3.1 pata 4 enumera las restricciones **reales** (verificadas en `test_harness_flags_help.py:44-52,63-70`), y F1 trae un texto ya medido campo por campo. |
| R10 | **Colisión con el plan 270.** El 270 no menciona `agent_completion_internal.py` ni `completion_state.py` (verificado: 0 hits) **pero su C3 declara que su F4 se cablea en `set_stacky_status_by_ado`**, que es la misma función que contiene el caller `api/tickets.py:1386` que este plan afecta vía F4. | **Media** (el v1 la declaraba Baja) | Frontera explícita: **este plan no edita ni una línea de `api/tickets.py`** (§6.6). Lo único que cambia de esa función es el **contenido** del `publish`/`ado_state_change` que devuelve `close_execution_with_publish`, y esa función serializa la variable local `state_change_result` (`:1466-1503`), no el `CloseResult`. Los nombres nuevos (`final_state_resolver.py`, `final_state_outcome`, `finalStateOutcome.ts`, las 4 flags `STACKY_FINAL_STATE_*`) **no existen hoy en el repo** (verificado: 0 hits) y no colisionan. **Merge: hacer el del 270 primero si ambos están listos.** |
| R11 | El diagnóstico está errado y el problema real era `harness_defaults.env:33`. | Media | **F0-D** lo mide antes de escribir una línea de producción, y su salida va al PR. Aun si se confirma, el motor A sigue roto y F1/F2/F2-bis se justifican. |

---

## 6. Fuera de scope (explícito, para que nadie lo agregue "de paso")

1. **Unificar los CUATRO escritores (motores A, B, C y D de §2.1) en uno solo.** Es el arreglo estructural correcto y ahora los cuatro están **censados** (F8), pero es una migración con riesgo propio: **plan 272**. Este plan deja **A y B** coherentes, arbitrados y observables, y **C y D** censados pero intactos (§2.1bis). El 272 debe: (a) extender el árbitro de F2-bis a C y D, (b) modelar `on_failure_state` (§F1) antes de cablear el resolver en el motor B, y (c) darle plan dueño al motor D o eliminarlo.
2. **Deduplicar `_infer_agent_type_from_filename`** (`agent_completion_internal.py:304-318`, `api/agents.py:1766-1767`, `services/agent_history.py:54-55`). Las tres copias coinciden para `technical`; no causó el bug.
3. **Construir la UI de la matriz `by_work_item_type` dentro de `StatesConfigPage`.** Es alcance del 208. Este plan hace que **no haga falta**.
4. **Cambiar la semántica de `review_mode_hold`.** HITL deliberado. Solo se hace visible.
5. **Transicionar en `needs_review`.** Exige revisión humana.
6. **`api/tickets.py` en cualquiera de sus formas** — `set_stacky_status_by_ado` (**empieza en `:1205`**, no en `:1487` como decía el v1), `_apply_task_state:531`, el escritor inline `:1489-1491`, `finish_work:1751`. Territorio del 270 y del 272. **Este plan no edita ni una línea de ese archivo**, solo lo cita.
7. **`deployment/harness_defaults.env`.** Snapshot derivado, ya divergente.
8. **Migrar `agent_workflow_configs.transition_state` al perfil del cliente.** El 216 lo declaró fuera de scope.
9. **Cambiar `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` en `harness_defaults.env:33`.** F0-D lo **mide** y lo reporta; cambiarlo es una decisión del operador, no de este plan.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **Motor A / "matriz"** | `completion_state.maybe_apply_state_transition`, disparado por post-hook del `completion_dispatcher`, **asíncrono** (daemon). Lee `tracker_state_machine`. |
| **Motor B / "employee_config"** | `agent_completion_internal.close_execution_with_publish`, Pasos 3.5 y 4, **síncrono**. Lee `agent_workflow_configs[<filename>].transition_state`. |
| **Motor C / "determinista"** | `api/tickets.py:531 _apply_task_state` (plan 79 + gate del 210), **síncrono**, solo desde `set_stacky_status_by_ado:1473`. **Ya honra el nivel rol.** |
| **Motor D / "inline"** | `api/tickets.py:1489-1491`, sin plan dueño. Este plan lo **censa** (F8) pero **no** lo modifica ni lo arbitra (§2.1bis); su unificación es del **272**. |
| **Nivel rol** | `tracker_state_machine.<agent_type>.next_state_ok`. Lo que `StatesConfigPage.tsx` sabe escribir. |
| **Celda de matriz** | `tracker_state_machine.<agent_type>.by_work_item_type.<tipo>`. Solo `ClientProfileEditor.tsx:467-477` la escribe. **Celda parcial** = celda con `in_progress` pero sin `next_state_ok`. |
| **Chokepoint** | `close_execution_with_publish` (`agent_completion_internal.py:66`). |
| **Gate espurio** | Un `if` que bloquea una acción por una condición que no aplica al caso. |
| **Skip mudo** | Un `return {"skipped": True}` cuya razón no llega a ninguna superficie que el operador mire. |
| **7 patas** | Los 7 lugares que toca una flag nueva (§3.1). El "patrón triple" es un mito. |
| **Censo** | El allow-list ejecutable de F8. Un escritor nuevo sin censar deja el repo rojo. |

### 7.2 Orden de implementación (estricto, por dependencia)

```
F0 (rojo 0/4 + medición F0-D, sin prod)
 └─> F1 (resolver puro + flag 1)
      └─> F2 (cablear motor A)              ← cierra RC-1  [F0 pasa a 2/4]
           └─> F2-bis GUARDIA 1 (gate 210)  ← cierra C2/R4  [va JUNTO con F2]
 └─> F3 (writer ruteado + flag 2 + F3-bis)  ← cierra E-3    [F0 pasa a 3/4]
      └─> F4 (gate preciso + flag 3)        ← cierra RC-2   [F0 pasa a 4/4]
           └─> F5 (persistir razón + flag 4)
                └─> F2-bis GUARDIA 2 (árbitro por execution_id)  ← necesita la key de F5
                     └─> F6 (mostrar razón + puente de catálogo) ← cierra RC-3
                          └─> F8 (censo ejecutable)
                               └─> F7 (cierre y registro)
```

**Verificación ítem por ítem de que ninguna fase depende de algo posterior:**
- F2 usa solo `final_state_resolver` (F1). ✔
- **F2-bis guardia 1** usa `dev_build_verify`, **preexistente** (`api/tickets.py:576-582` ya lo llama). ✔
- F3 usa `tracker_provider` y `_safe_transition`, ambos **preexistentes**. ✔
- F4 usa el kwarg `project_name` que **F3 ya agregó**. ✔
- F5 usa las razones que F2/F3/F4 ya producen. ✔
- **F2-bis guardia 2** usa la key `final_state_outcome` que **F5 ya persiste** ⇒ por eso va después de F5. Mientras tanto es un no-op fail-open. ✔ **(Corrige el orden del v1, que declaraba el DAG satisfecho sin haber detectado esta arista.)**
- F6 usa la key de F5 y `ALL_FINAL_STATE_REASONS` de F1. ✔
- F8 solo lee código. ✔ · F7 solo verifica. ✔

**F1+F2+F2-bis(guardia 1) se pueden entregar solas** y ya cierran el bug reportado sin regresionar el plan 210. F3..F8 son el resto de la deuda.

### 7.3 Definition of Done

- [ ] **F0-D**: salida de los 4 comandos de medición pegada en el PR, con una línea de interpretación.
- [ ] `test_plan271_caracterizacion.py`: `0 passed, 4 failed` al terminar F0 → **`4 passed`** al terminar F7.
- [ ] `test_plan271_final_state_resolver.py`: 14 passed.
- [ ] `test_plan271_role_fallback.py`: 9 passed.
- [ ] `test_plan271_arbitro.py`: 5 passed.
- [ ] `test_plan271_writer_routed.py`: 8 passed.
- [ ] `test_plan271_publish_gate.py`: 8 passed.
- [ ] `test_plan271_reason_persisted.py`: 8 passed.
- [ ] `test_plan271_reason_catalog.py`: 2 passed.
- [ ] `test_plan271_censo_escritores.py`: 3 passed, con el allow-list de **6 entradas** (o el que el censo encuentre, actualizado en el mismo commit).
- [ ] `test_plan271_flags.py`: las 4 keys con `default is True`, en `_CATEGORY_KEYS["flujo_funcional"]`, y con línea `=true` en `harness_defaults.env`.
- [ ] `plan271FinalStateOutcome.test.ts`: 6 passed. `npx tsc --noEmit`: 0 errores.
- [ ] `test_harness_flags.py` y `test_harness_flags_help.py`: verdes (por archivo).
- [ ] `test_b2_transition_from_config.py`, `test_u2_publish_review_mode.py`, `test_output_watcher.py`, `test_plan79_apply_final.py`, `test_plan79_centinela_estados.py`, `test_plan210_state_gate.py`: verdes (por archivo). Cualquier rojo se prueba preexistente con un worktree en el commit base **o se arregla**; no se borra el assert.
- [ ] Los 11 archivos del checklist de F7 registrados en **ambos** scripts (**22 hits**).
- [ ] `compileall` de `services/`, `api/` y `harness/` sin salida.
- [ ] Las 4 flags con línea `=true` en `backend/harness_defaults.env`. (Verificable: `grep "STACKY_FINAL_STATE_" backend/harness_defaults.env` ⇒ **4 líneas, todas `=true`**.)
- [ ] Huella de regresión registrada (o declarada como "archivo inexistente" en el PR).
- [ ] **Smoke manual (una vez, el operador o el implementador):** con un proyecto que tenga `tracker_state_machine.technical.next_state_ok = "To Do"` y **sin** `by_work_item_type`, correr el Analista Técnico sobre una incidencia y verificar (a) en el tracker que quedó en `To Do`, (b) en el drawer que dice **“Movida a "To Do"”**, y (c) que el `System.State` **no** cambió dos veces (una sola escritura, comprobable en el historial del work item).
