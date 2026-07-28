# Plan 271 — La incidencia se mueve al estado configurado al terminar el analista

**Estado:** PROPUESTO v1 (sin criticar)
**Fecha:** 2026-07-28
**Reserva de números:** este plan usa **271**. Los huecos **261** y **262** siguen libres.
**Depende de:** nada. **Coordina con:** 208 (matriz), 216 (UI de estados), 270 (cierre real ADO+GitLab), 79 (`_safe_transition`).

---

## 1. Objetivo, KPI e impacto

El operador configuró, en la pantalla que Stacky le dio para eso, que al terminar el **Analista Técnico** la incidencia pase a `To Do`. Stacky corre el agente, lo cierra en verde… y la incidencia se queda exactamente en el estado en el que llegó. Sin error, sin aviso, sin razón visible en ningún lado.

Este plan hace tres cosas, en este orden: **(1)** diagnostica y repara la causa por la que la transición configurada no se aplica; **(2)** elimina el *skip mudo* — todo no-cambio de estado deja una razón que el operador ve donde ya mira; **(3)** deja la escritura de estado en paridad ADO ↔ GitLab, que hoy no lo está.

No es una feature nueva. Es **reparar un comportamiento que el operador ya configuró y que Stacky prometió aplicar**.

### KPI (medibles, sin instrumentación nueva)

| KPI | Hoy | Después |
|---|---|---|
| Incidencias que quedan en el estado de entrada tras un cierre OK con `next_state_ok` configurado a nivel rol | **100 %** (skip `no_matrix_cell`, `completion_state.py:90-92`) | **0 %** |
| Razones de no-transición visibles para el operador | **0 de 12** (mueren en `CloseResult.ado_state_change` y en `SystemLog`) | **12 de 12** en el drawer de la ejecución |
| Trackers soportados por el escritor de estado del cierre por config | **1** (ADO; `agent_completion_internal.py:527,536`) | **2** (ADO + GitLab, vía `tracker_provider`) |
| Clics del operador para arreglarlo | N/A (hoy no puede: no sabe que pasó) | **0** |

### Impacto esperado

El operador deja de tener que mover incidencias a mano después de cada corrida del analista técnico, y — más importante — deja de tener que *adivinar por qué* no se movieron. El tablero vuelve a decir la verdad sin intervención.

---

## 2. Por qué ahora, y la causa raíz diagnosticada

### 2.1 Lo que ya existe (leído, no supuesto)

Hoy conviven **dos motores independientes** que pueden mover el `System.State` al terminar un agente. Ninguno de los dos sabe que el otro existe.

**Motor A — “matriz” (plan 208).**
`app.py:998-1000` registra `completion_dispatcher._post_hook` en `ticket_status.register_post_hook` y arranca su daemon. Al terminar cualquier agente, `ticket_status.on_execution_end` (`services/ticket_status.py:293`) llama `_run_post_hooks` (`:348-353`), el hook encola O(1) (`completion_dispatcher.py:53-59` → `:30-50`), y el daemon (`completion_dispatcher.py:100-122`) llama `completion_state.maybe_apply_state_transition(ev)` en `:119`. Ese motor lee `tracker_state_machine` del perfil del cliente y escribe vía `harness/task_states.py:146 _safe_transition`, que **sí** es provider-aware (ADO y GitLab, `:171-177`). Su flag `STACKY_ADO_STATE_MATRIX_ENABLED` está **ON** (`config.py:1404-1406`, `services/harness_flags.py:2795-2807 default=True`).

**Motor B — “employee_config” (B2 / plan 216).**
`services/agent_completion_internal.py:66 close_execution_with_publish` es el chokepoint que usan `api/tickets.py:1386`, `api/qa_browser.py:373`, `api/qa_uat.py:394` y `services/output_watcher.py:412` y `:618`. En su Paso 3.5 (`:242-258`) resuelve `transition_state` con `_resolve_transition_state_from_config` (`:321-386`), y en el Paso 4 (`:260-280`) escribe con `_attempt_state_change` (`:502-553`).

### 2.2 CAUSA RAÍZ PRIMARIA (RC-1) — la única UI que el operador tiene escribe en una clave que el motor se niega a leer

Esto es un match exacto con el síntoma reportado, y está probado con cuatro anclajes:

**(a) Dónde escribe el operador.** La pantalla “Estados del tracker” (plan 216) es la única que dice literalmente *“Por cada rol: en qué estados actúa y **a cuál mueve el ticket al terminar**”* (`frontend/src/pages/StatesConfigPage.tsx:100-103`) y se presenta como *“Una sola fuente”* (`:85-88`). Su guardado es:

```ts
// frontend/src/pages/StatesConfigPage.tsx:76-78
function actualizarRol(rol: StateRole, parche: Partial<RoleStateMachine>) {
  guardar.mutate({ ...maquina, [rol]: { ...(maquina[rol] ?? {}), ...parche } });
}
```

y el campo del estado final es `next_state_ok` **a nivel de rol** (`:198-201`). Escribe, por tanto, `tracker_state_machine.technical.next_state_ok = "To Do"`. **Nunca** escribe `by_work_item_type`.

**(b) Qué exige el motor.** `services/completion_state.py:88-92`:

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
if ip_m is not None or fk_m is not None:
    return TaskStatePlan(ip_m, fk_m, "matrix")
ip = (m.get("in_progress") or "").strip() or None   # ← nivel ROL
fk = (m.get("next_state_ok") or "").strip() or None # ← lo que escribió el operador
if ip is None and fk is None:
    return TaskStatePlan(None, None, "absent")
return TaskStatePlan(ip, fk, "config")              # ← "config", NO "matrix"
```

Es decir: lo que el operador configuró produce `source="config"`, y `completion_state.py:90` lo descarta.

**(d) El propio código lo admite y nadie lo cerró.** `config.py:1401-1403` dice textualmente: *“NO-OP hasta que el operador configure la matriz (`tracker_state_machine.<rol>.by_work_item_type`) desde la UI”*, y el texto de la flag repite lo mismo (`harness_flags.py:2800-2802`). Pero la UI que el plan 216 construyó y llamó “Estados” no ofrece `by_work_item_type` — solo `ClientProfileEditor.tsx:467-477` lo hace, en otro sub-tab (`SettingsPage.tsx:248`, sub `client-profile`), que es el editor crudo del perfil, no la pantalla de estados.

**Agravante silencioso adicional:** aun con la matriz configurada, si el ticket local tiene `work_item_type` en NULL (`models.py:55`, columna nullable), `_matrix_cell` devuelve `{}` (`task_states.py:70-72`) y se cae al mismo skip.

> **Conclusión RC-1:** el plan 208 eligió a propósito no honrar el nivel de rol (“para no cambiar el comportamiento de proyectos que hoy tienen `next_state_ok` a nivel rol”), y el plan 216 construyó después la única UI de estados escribiendo exactamente ese nivel de rol. La costura entre ambos planes es el bug.

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
| `auto_publish_disabled` | `:236-238` (`_should_auto_publish`, `:389-397`) | **No** |
| `ado_publisher_unavailable` | `:617-626` | **No** |
| `review_mode_hold` (early-return, ni llega al Paso 4) | `:210-224` | **No** (publicación diferida a decisión humana) |

En los tres primeros el gate es **espurio**: bloquea la transición “para no dejar un ticket en Done sin comentario publicado” (`:261-263`) cuando nunca hubo comentario que publicar. Resultado: la incidencia se queda como estaba. Es el candidato **C-a** del reconocimiento, y está vivo.

### 2.4 CAUSA RAÍZ TERCIARIA (RC-3) — el skip es mudo

`CloseResult.ado_state_change` (`agent_completion_internal.py:50,61,297`) se serializa y se devuelve… y **no lo consume nadie en el frontend**: `grep -rn "ado_state_change" frontend/src` ⇒ **0 hits**. El único caller que lo expone por HTTP es `api/tickets.py:1520`, y ningún componente lo lee.

Del lado del motor A, `completion_state._logged` (`:164-191`) escribe una fila `SystemLog action="completion.matrix_transition"` (`:176`) con la razón — pero no hay endpoint ni componente que la muestre; es una aguja en el pajar del log.

Las **12 razones** hoy invisibles: `flag_off`, `not_ok_status`, `no_ticket`, `no_ado_id_or_stacky_project`, `no_matrix_cell`, `no_final_state`, `state_not_applicable`, `human_moved_out_of_flow`, `not_requested`, `publish_not_ok`, `review_mode_hold`, `no_ado_id`.

> El bug de fondo no es que el ticket no se mueva. Es que **no se mueve y no dice por qué**. Eso es exactamente la familia “cero fallas mudas” del plan 255.

### 2.5 Hueco de paridad (E-3) — el escritor del motor B es ADO-only

`services/agent_completion_internal.py:526-541`:

```python
try:
    from services.ado_client import AdoClient
except ImportError as exc: ...
try:
    AdoClient().update_work_item_state(int(ado_id), target_state)
```

Sin `tracker_provider`, sin `_safe_transition`, sin guardia de idempotencia, sin guardia de origen. En un proyecto GitLab esto intenta escribir en ADO usando el `iid` de GitLab. El plan 79 declara que `_safe_transition` es *“la ÚNICA función que escribe estado”* (`harness/task_states.py:146`, docstring), pero su inventario nunca censó este call site: **`_attempt_state_change` es tierra de nadie en los planes 79, 208, 216 y 270**.

### 2.6 Candidatos descartados, con el porqué

| Cand. | Veredicto | Evidencia |
|---|---|---|
| **C-a** | **CONFIRMADO** = RC-2 | `agent_completion_internal.py:267-272` |
| **C-b** (`review_mode_hold`) | **Real pero NO es el caso reportado** | `:210-224` solo dispara con `publish_mode=="review"` (`_resolve_publish_mode`, `:400-416`), que es opt-in por proyecto y default `auto` (`:406`). Se documenta como razón visible en F5, no se cambia su semántica: es HITL deliberado. |
| **C-c** (`target_source="caller"`) | **Real, condicional, NO es la causa** | `:247-248`. Solo aplica si `output_watcher._read_target_state_from_meta` (`:705-726`) encontró `target_ado_state` en `comment.meta.json` (`:406,421`). Se mantiene la precedencia caller > config y se hace explícita en F1. |
| **C-d** (falta `agent_filename`) | **Fragilidad, no causa** | `:355-364`; si falta, cae al fallback `:368-384`, que para `technical` acierta. Se endurece en F1. |
| **C-e** (fallback no determinista) | **Fragilidad real, no causa** | `:373-382` recorre `configs.items()` y devuelve el primero que matchea; con dos archivos técnicos el resultado depende del orden del dict. Se hace determinista en F1. |
| **C-f** (heurística triplicada) | **Duplicación real, NO causó el síntoma** | `agent_completion_internal.py:304-318`, `api/agents.py:1766-1767`, `services/agent_history.py:54-55`. Las tres mapean `"technical" in filename → "technical"` igual. Queda **fuera de scope** (§6). |
| **C-g** (la UI escribe en otra clave) | **DESCARTADO para `transition_state`** | `api/projects.py:883` escribe `transition_state` en el payload que `project_manager.set_agent_workflow_config` (`:408-419`) guarda en `agent_workflow_configs[<filename>]`, y `get_agent_workflow_config` (`:392-405`) lo lee de ahí mismo. La persistencia es correcta. **CONFIRMADO para `next_state_ok`**: ver RC-1 — ahí sí la UI escribe en un nivel que el consumidor ignora. |

---

## 3. Principios y guardarraíles (aplican a TODAS las fases)

1. **Diagnóstico antes que fix.** F0 no toca una línea de producción. Escribe el rojo que prueba el bug. Ninguna fase posterior se escribe sin ese rojo.
2. **Reparar ≠ inventar.** Este plan solo hace que se aplique lo que el operador **ya configuró**. No inventa estados, no infiere destinos, no escribe nada que el operador no haya tipeado en una UI.
3. **Human-in-the-loop innegociable.** La guardia de origen (`completion_state._origin_guard`, `:121-161`) que impide pisar un ticket que el humano movió a mano **se conserva intacta**. El `review_mode_hold` (`:210-224`) se conserva intacto.
4. **Cero skip mudo.** Toda rama que decida NO cambiar el estado debe producir una razón enumerada, persistida y visible. Un `return {"skipped": True}` sin `reason` es un defecto de este plan.
5. **Paridad de 3 runtimes por construcción.** Codex CLI, Claude Code CLI y Copilot Pro cierran todos por `ticket_status.on_execution_end` (`completion_dispatcher.py:8-10`) y/o por `close_execution_with_publish`. Ninguna fase toca un runner: se trabaja aguas abajo del punto común.
6. **Paridad ADO ↔ GitLab.** Toda escritura de estado nueva o corregida pasa por `services/tracker_provider.get_tracker_provider` (`:125-150`). Nada de `AdoClient()` directo.
7. **Backward-compatible.** Con las 4 flags apagadas, el comportamiento es byte-idéntico al de hoy.
8. **Cero trabajo del operador.** Todas las flags nacen **ON**. Ninguna fase agrega un campo, un clic o una configuración nueva.
9. **Tests por archivo.** Los tests que tocan la DB son flaky bajo pytest con shared-cache (`SQLITE_LOCKED`). **Nunca** correr la suite completa: siempre `pytest <archivo>`.
10. **Todo `test_*.py` nuevo se registra en los DOS scripts** — `backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES`) **y** `backend/scripts/run_harness_tests.ps1` (`$HarnessTestFiles`, sintaxis distinta: elementos entre comillas dobles). Omitir uno deja el meta-test rojo.

### 3.1 Receta completa de una flag nueva (7 patas — el “patrón triple” es un mito)

Toda flag de este plan toca exactamente estos lugares. **Enumerados por fase más abajo; esta es la plantilla.**

| # | Archivo | Qué se agrega |
|---|---|---|
| 1 | `backend/config.py` | Atributo `KEY: bool = os.getenv("KEY", "true").lower() in ("1","true","yes")` — copiar el patrón exacto de `config.py:1404-1406`. |
| 2 | `backend/services/harness_flags.py` | Un `FlagSpec(key=..., type="bool", default=True, label=..., description=..., group="global", env_only=False)` en `FLAG_REGISTRY`. |
| 3 | `backend/services/harness_flags.py` | La key en `_CATEGORY_KEYS["flujo_funcional"]` (`:268-273`). Sin esto, `tests/test_harness_flags.py` queda **rojo** (nota explícita en `harness_flags.py:488`). |
| 4 | `backend/services/harness_flags_help.py` | Un `PlainHelp(what=..., on_effect=..., off_effect=..., example=...)`. **Restricciones duras** verificadas por `tests/test_harness_flags_help.py`: `on_effect`/`off_effect` deben empezar con `"Si "` (`test_plain_help_on_off_start_with_si`), sin jerga técnica (`test_plain_help_avoids_jargon_denylist`), y cada campo ≤ **240** caracteres (`test_plain_help_fields_non_empty_and_bounded`). |
| 5 | `backend/harness_defaults.env` | Línea `KEY=true`. **Obligatorio aunque el default de `config.py` ya sea `true`**: este archivo es el snapshot que `deployment/build_release.ps1` hornea en cada deploy y **pisa** el default del código. Precedente vivo: `harness_defaults.env:33` fuerza `STACKY_DETERMINISTIC_TASK_STATES_ENABLED=false` mientras `config.py:1245-1246` dice `true`. |
| 6 | `backend/tests/test_plan271_flags.py` | Un test que afirma que las 4 keys están en `FLAG_REGISTRY` con `default is True` y en `_CATEGORY_KEYS`. |
| 7 | `backend/scripts/run_harness_tests.sh` **y** `.ps1` | Registrar todo archivo de test nuevo. |

> **NO tocar `deployment/harness_defaults.env`.** Es un snapshot derivado de un deploy vivo (ver docstring de `deployment/export_harness_defaults.py:1-21`) y **ya diverge** del versionado. Está fuera de scope.

### 3.2 Las 4 flags de este plan y su default

| Flag | Fases | Default | Justificación de la categoría |
|---|---|---|---|
| `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` | F1, F2 | **ON** | Repara lo ya configurado. El operador tipeó `To Do` en `StatesConfigPage.tsx:198-201`, en una pantalla que le prometió *“a cuál mueve el ticket al terminar”*. Aplicarlo no es una escritura nueva: es cumplir la promesa. Dejarla OFF **dejaría el bug vivo**, que es precisamente lo que la regla de flags prohíbe. |
| `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED` | F3 | **ON** | Corrige el **destino** de una escritura que ya ocurre, no agrega escrituras. Hoy `agent_completion_internal.py:536` escribe siempre en ADO; con la flag ON escribe en el tracker que el proyecto declara. En un proyecto ADO el comportamiento es idéntico; en uno GitLab deja de escribir en el lugar equivocado. |
| `STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED` | F4 | **ON** | *Este es el único caso que roza la categoría (B) y merece precisión.* Con la flag ON, Stacky transiciona tickets que hoy no transiciona ⇒ **sí produce escrituras nuevas en el sistema real del operador**. Va **ON igual**, porque: (i) el estado destino salió íntegramente de la config del operador, no de una inferencia; (ii) el gate que se afina nunca fue una decisión del operador sino una heurística interna documentada en `:261-263`; (iii) se afina **solo** para los tres casos en que no había nada que publicar (`html_output_path_missing`, `auto_publish_disabled`, `ado_publisher_unavailable`) — el caso en que la publicación **se intentó y falló** (`event == "publish.failed"`) y el `review_mode_hold` **conservan el gate**. Es decir: la parte que podría dejar un ticket cerrado sin evidencia sigue bloqueada. |
| `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` | F5, F6 | **ON** | Solo lectura: persiste y muestra una razón que ya se calcula. No escribe en ningún sistema del operador. Solo-lectura nunca es excepción. |

**Ninguna flag de este plan nace OFF.** No aplica ninguna de las categorías (A) — no hay loop, daemon, barrido, polling ni llamada a modelo en reposo — ni (B) en su forma pura, por lo argumentado arriba.

---

## 4. Fases

### F0 — Caracterización: el rojo que prueba el bug

**Objetivo (1 frase):** dejar escrito, en tests que hoy fallan, el comportamiento que el operador espera y que Stacky no entrega.
**Valor:** ninguna fase posterior puede escribirse “de fe”. Si F0 pasa en verde antes de tocar producción, el diagnóstico está mal y hay que rehacerlo.

**Archivos a crear:**
- `backend/tests/test_plan271_caracterizacion.py`

**Archivos a editar:**
- `backend/scripts/run_harness_tests.sh` — agregar `  tests/test_plan271_caracterizacion.py` a `HARNESS_TEST_FILES` (formato: dos espacios de indentación, sin comillas).
- `backend/scripts/run_harness_tests.ps1` — agregar `  "tests/test_plan271_caracterizacion.py"` a `$HarnessTestFiles` (formato: **con comillas dobles**).

**Contenido exacto de los tests (4 casos, todos deben arrancar ROJO):**

```python
# backend/tests/test_plan271_caracterizacion.py
"""Plan 271 F0 — Caracterización del bug reportado.

Estos tests describen el comportamiento ESPERADO por el operador. Al escribirlos
(antes de F1..F6) DEBEN FALLAR. Si alguno pasa en verde acá, el diagnóstico del
plan está equivocado y hay que rehacerlo antes de tocar producción.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_rc1_rol_sin_matriz_deberia_transicionar(monkeypatch):
    """RC-1: el operador configuró tracker_state_machine.technical.next_state_ok
    = 'To Do' desde StatesConfigPage (nivel ROL, sin by_work_item_type).
    Hoy completion_state devuelve skipped/no_matrix_cell. Debe transicionar."""
    from services import completion_state

    perfil = {"tracker_state_machine": {"technical": {
        "input_states": ["New"], "in_progress": "Doing", "next_state_ok": "To Do",
    }}}
    # monkeypatch: load_effective_client_profile -> perfil; ticket con ado_id=4242,
    # stacky_project_name="P", work_item_type=None; provider fake que registra
    # las llamadas a update_item_state.
    # ... (armado del fake abajo en el helper _fake_env)
    escrito = _fake_env(monkeypatch, perfil, work_item_type=None)
    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": 1, "execution_id": 9, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True, f"esperaba transición, obtuve {out}"
    assert out.get("to") == "To Do"
    assert escrito == [("4242", "To Do")]


def test_rc1_razon_del_skip_nunca_es_silenciosa():
    """RC-3: toda rama de no-transición debe traer una razón enumerada."""
    from services import completion_state
    out = completion_state.maybe_apply_state_transition({"final_status": "error"})
    assert out.get("reason"), "un skip sin reason es un defecto"


def test_rc2_sin_html_no_debe_bloquear_la_transicion(monkeypatch):
    """RC-2: cierre completed sin html_output_path (nada que publicar) NO debe
    impedir el cambio de estado configurado."""
    from services import agent_completion_internal as aci
    # Fake de _resolve_transition_state_from_config -> "To Do"
    # Fake de _attempt_state_change que registra la llamada
    llamadas = []
    monkeypatch.setattr(aci, "_resolve_transition_state_from_config",
                        lambda **kw: "To Do")
    monkeypatch.setattr(aci, "_attempt_state_change",
                        lambda **kw: llamadas.append(kw) or {"ok": True, "to": "To Do"})
    # ... crear execution+ticket en la DB de test y llamar close_execution_with_publish
    #     con html_output_path=None, final_status="completed"
    res = _close_sin_html(monkeypatch)
    assert res.ado_state_change.get("ok") is True, \
        f"publish sin nada que publicar no debe gatear el estado: {res.ado_state_change}"


def test_e3_el_escritor_no_puede_ser_ado_only():
    """E-3: _attempt_state_change no debe importar AdoClient directo; debe rutear
    por tracker_provider para tener paridad ADO/GitLab."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "services" / "agent_completion_internal.py"
    texto = src.read_text(encoding="utf-8")
    assert "from services.ado_client import AdoClient" not in texto, \
        "el escritor de estado sigue siendo ADO-only"
```

> **Nota para el implementador:** los helpers `_fake_env` y `_close_sin_html` los escribís vos en el mismo archivo. Modelalos sobre `backend/tests/test_b2_transition_from_config.py` (que ya monkeypatchea `project_manager`) y sobre `backend/tests/test_output_watcher.py:356-370` (que ya stubea `AdoClient.update_work_item_state` sin red). **No inventes fixtures nuevas ni toques `conftest.py`.**

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_caracterizacion.py" -v
```

**Criterio de aceptación (BINARIO):** los **4** tests corren y **los 4 fallan**. `0 passed, 4 failed`. Cualquier otro conteo = el diagnóstico está mal, se detiene el plan y se reabre §2.

**Flag:** ninguna (fase de solo tests).
**Impacto por runtime:** ninguno (no toca producción). Codex / Claude Code / Copilot: idéntico.
**Trabajo del operador: ninguno.**

---

### F1 — Resolver único del estado final (módulo puro)

**Objetivo (1 frase):** una sola función pura que, dados el perfil y la config del empleado, diga **qué estado aplicar y por qué**, con precedencia declarada y determinista.
**Valor:** cierra C-e (no determinismo) y da la base para RC-1 sin duplicar lógica en dos motores.

**Archivo a crear:** `backend/services/final_state_resolver.py`

**Nombres exactos:**

```python
# backend/services/final_state_resolver.py
"""Plan 271 F1 — Resolutor ÚNICO del estado final al terminar un agente.

Puro: sin DB, sin red, sin config global mutable. Recibe todo por parámetro.
Nunca lanza. Siempre devuelve una FinalStateDecision con `reason` no vacío.
"""
from __future__ import annotations
from typing import NamedTuple, Optional

# Precedencia CONGELADA, de mayor a menor. El primero que produce un estado gana.
PRECEDENCE: tuple[str, ...] = ("caller", "matrix", "role", "employee_config")

# Conjunto CERRADO de razones. `reason` jamás puede salir de acá.
REASONS: frozenset[str] = frozenset({
    "ok",                  # se resolvió un estado
    "not_ok_status",       # el cierre no fue exitoso
    "no_agent_type",       # falta el tipo de agente
    "no_config",           # ni matriz, ni rol, ni employee_config definen destino
    "flag_off",            # STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED apagada y solo había rol
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

**Tabla de verdad exacta que debe implementar `resolve_final_state`:**

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

**Casos borde obligatorios:** strings `""` y `"   "` se tratan como `None` (`.strip()` antes de evaluar). El `caller_state` **ignora la flag** (es una decisión explícita de quien llama, no del fallback). `final_status` se compara en minúsculas y `strip()`.

> **Por qué `needs_review` NO transiciona:** exige revisión humana. Auto-transicionar violaría HITL. Es el mismo criterio que `completion_state.py:16-25` ya congeló.

**Archivo de test a crear:** `backend/tests/test_plan271_final_state_resolver.py`
**Casos:** las **9** filas de la tabla de verdad, una por test, más 2 de casos borde (`""` y `"  "`), más 1 que afirma `set(REASONS) == {…}` congelado, más 1 que afirma `PRECEDENCE == ("caller","matrix","role","employee_config")`. Total: **13 tests**.

**Flag que la protege:** `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` — **default ON**. Las 7 patas de §3.1 se cablean **en esta fase**:
1. `backend/config.py` — junto al bloque `STACKY_ADO_STATE_MATRIX_ENABLED` (`:1401-1406`).
2. `backend/services/harness_flags.py` — `FlagSpec` inmediatamente después del de `STACKY_ADO_STATE_MATRIX_ENABLED` (`:2795-2807`).
3. `backend/services/harness_flags.py` — key en `_CATEGORY_KEYS["flujo_funcional"]` (`:268-273`).
4. `backend/services/harness_flags_help.py` — `PlainHelp` junto al de `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` (`:893-898`).
5. `backend/harness_defaults.env` — `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED=true`.
6. `backend/tests/test_plan271_flags.py` (crear en esta fase; se completa con las otras 3 keys en F3/F4/F5).
7. Registrar `test_plan271_final_state_resolver.py` y `test_plan271_flags.py` en `run_harness_tests.sh` **y** `.ps1`.

**Texto sugerido del `PlainHelp` (respeta las 3 restricciones duras):**
```python
"STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED": PlainHelp(
    what="Hace que el estado al que configuraste que pase la incidencia cuando el empleado termina se aplique de verdad.",
    on_effect="Si la activás: al terminar el empleado, la incidencia pasa al estado que elegiste en la pantalla de Estados.",
    off_effect="Si la apagás: la incidencia se queda en el estado en que estaba y la tenés que mover a mano.",
    example="Como que el trámite avance solo de ventanilla cuando el funcionario lo termina, en vez de quedarse en el mostrador.",
),
```

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_final_state_resolver.py" -v
```

**Criterio de aceptación (BINARIO):** `13 passed`. Y `pytest backend/tests/test_harness_flags.py backend/tests/test_harness_flags_help.py` (por archivo, dos comandos) queda **verde**.

**Impacto por runtime:** ninguno — módulo puro sin consumidores todavía. Codex / Claude Code / Copilot: idéntico. Fallback: N/A.
**Trabajo del operador: ninguno.**

---

### F2 — Cablear el resolver en el motor de matriz (cierra RC-1)

**Objetivo (1 frase):** que `completion_state.maybe_apply_state_transition` honre el `next_state_ok` de nivel rol cuando no hay celda de matriz, en lugar de descartarlo.
**Valor:** **cierra la causa raíz primaria.** El bug reportado desaparece.

**Archivo a editar:** `backend/services/completion_state.py`

**Diff ilustrativo — reemplazar `:88-99`:**

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
from services.final_state_resolver import resolve_final_state, role_fallback_enabled

# La matriz sigue mandando cuando existe (comportamiento 208 intacto).
matrix_state = plan.final_ok if plan.source == "matrix" else None
# NUEVO: el nivel de rol es lo ÚNICO que StatesConfigPage.tsx:76-78 sabe escribir.
role_state = None
if plan.source == "config":
    role_state = plan.final_ok
decision = resolve_final_state(
    matrix_state=matrix_state,
    role_state=role_state,
    agent_type=agent_type,
    final_status=final_status,
)
ctx["source"] = decision.source
ctx["target"] = decision.state
if decision.state is None:
    # Nunca mudo: `reason` viene del conjunto cerrado REASONS.
    return _logged(ctx, ev, {"skipped": True, "reason": decision.reason,
                             "source": decision.source, "plan_source": plan.source})
target = decision.state
# CENTINELA EN RUNTIME: el conjunto aplicable se amplía para incluir el nivel rol.
if target not in applicable_states(plan):
    return _logged(ctx, ev, {"skipped": True, "reason": "state_not_applicable",
                             "target": target})
```

> **Ojo, trampa real:** `applicable_states(plan)` (`harness/task_states.py:119-122`) devuelve `frozenset(s for s in (plan.in_progress, plan.final_ok) if s)`. Cuando `plan.source == "config"`, `plan.final_ok` **ya es** el `next_state_ok` de rol, así que el centinela sigue cerrando bien sin tocarlo. **Verificá esto corriendo el test, no leyendo.** Si el centinela rechaza, el bug está en cómo armaste `role_state`, no en `applicable_states`.

**Lo que NO se toca en esta fase (invariantes duros):**
- `_origin_guard` (`:121-161`) se llama **antes** de `_safe_transition`, igual que hoy (`:108-111`). Es la guardia HITL: si el humano movió el ticket fuera del flujo, no se pisa.
- `_OK_STATUSES` (`:24-25`) queda en `{"completed"}`. `needs_review` sigue sin transicionar.
- `matrix_enabled()` (`:28-37`) sigue siendo el gate maestro del motor A. Si `STACKY_ADO_STATE_MATRIX_ENABLED` está OFF, no pasa nada — pero está ON por default (`config.py:1404-1406`).

**Archivo de test a crear:** `backend/tests/test_plan271_role_fallback.py`
**Casos (7):**
1. Rol con `next_state_ok="To Do"`, sin `by_work_item_type` ⇒ `ok=True`, `to="To Do"`, `source="role"`. **(Este es el bug reportado.)**
2. Matriz con celda para `work_item_type="Bug"` **y** rol distinto ⇒ gana la matriz, `source="matrix"`.
3. Matriz configurada pero `ticket.work_item_type` NULL ⇒ cae a rol, `source="role"`, transiciona igual.
4. Ni matriz ni rol ⇒ `skipped`, `reason="no_config"`, y **`reason` no vacío**.
5. Flag `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED=False` + solo rol ⇒ `skipped`, `reason="flag_off"` (comportamiento byte-idéntico al de hoy).
6. `_origin_guard` sigue bloqueando: estado actual del tracker fuera del flujo esperado ⇒ `reason="human_moved_out_of_flow"`, **sin** llamar a `update_item_state`.
7. `final_status="needs_review"` ⇒ `skipped`, `reason="not_ok_status"`, sin escritura.

Registrar el archivo en `run_harness_tests.sh` **y** `.ps1`.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_role_fallback.py" -v
```

**Criterio de aceptación (BINARIO):**
- `7 passed` en `test_plan271_role_fallback.py`.
- **Y** el test `test_rc1_rol_sin_matriz_deberia_transicionar` de F0 pasa de ROJO a **VERDE** (correr `test_plan271_caracterizacion.py` y verificar que ese caso concreto pasó; los otros 3 siguen rojos hasta F3/F4).
- **Y** `pytest backend/tests/test_plan208_completion_state.py` (si existe; si no existe, omitir y decirlo) sigue verde — **correr por archivo**.

**Flag:** `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` (ya cableada en F1). **Default ON.**
**Impacto por runtime:** los 3 cierran por `ticket_status.on_execution_end` → post-hook (`completion_dispatcher.py:8-10` lo declara explícito), así que la corrección aplica a Codex CLI, Claude Code CLI y Copilot **por construcción, sin código por runtime**. Fallback: con la flag OFF, los 3 vuelven al comportamiento de hoy, idéntico.
**Trabajo del operador: ninguno.**

---

### F3 — El escritor de estado del chokepoint rutea por provider (paridad ADO ↔ GitLab)

**Objetivo (1 frase):** que `_attempt_state_change` deje de ser ADO-only y escriba en el tracker que el proyecto declara.
**Valor:** cierra E-3. En un proyecto GitLab, hoy este camino escribe en ADO con un `iid` de GitLab.

**Archivo a editar:** `backend/services/agent_completion_internal.py` — **solo** el cuerpo de `_attempt_state_change` (`:502-553`). Ninguna otra parte del archivo se toca en esta fase.

**Diff ilustrativo — reemplazar `:526-553`:**

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
if _writer_routed_enabled():
    # Ruteo por provider: mismo seam que completion_state.py:101-114 usa.
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
    return result
# Camino legacy byte-idéntico (flag OFF): ver bloque ANTES.
```

**Cambios de firma necesarios (hacelos exactamente así):**
- `_attempt_state_change` gana el kwarg **`project_name: str | None = None`**. Los dos call sites internos lo pasan: `:274-278` (usa `stacky_project_name`, ya leído en `:135`) y `:476-480` dentro de `publish_execution_from_review` (usa `project_name`, ya leído en `:461`).
- Agregar el helper `_writer_routed_enabled()` al final del bloque de helpers, con el patrón de instancia:
```python
def _writer_routed_enabled() -> bool:
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False
```
- Agregar `def _legacy_ado_client(): from services.ado_client import AdoClient; return AdoClient()` — es el `legacy_client_fn` que `_safe_transition` (`harness/task_states.py:171-177`) usa cuando `provider is None`.

**Por qué `_safe_transition` y no una función nueva:** el plan 79 lo declara *“la ÚNICA función que escribe estado”* (`harness/task_states.py:146` docstring). Ya trae idempotencia (`:161-168`, lee el estado actual y saltea si ya coincide) y ya es provider-agnóstica (`:171-177`). Escribir otra sería crear un cuarto escritor.

> **Gotcha real de GitLab:** los write viven en `services/gitlab_provider.py`, **no** en el client. `update_item_state` está en `gitlab_provider.py:228`. `get_tracker_provider` (`tracker_provider.py:130-148`) exige `STACKY_GITLAB_ENABLED` y lanza `TrackerConfigError` si está OFF — por eso el `except` de arriba devuelve `provider_unavailable` en vez de romper el cierre.

**Archivo de test a crear:** `backend/tests/test_plan271_writer_routed.py`
**Casos (6):**
1. Proyecto ADO ⇒ `get_tracker_provider` devuelve `AdoTrackerProvider`; se llama `provider.update_item_state("4242", "To Do")` exactamente una vez.
2. Proyecto GitLab ⇒ se llama `provider.update_item_state` del `GitLabTrackerProvider`, **y no** `AdoClient`.
3. `get_tracker_provider` lanza ⇒ `{"skipped": True, "reason": "provider_unavailable"}`, y `close_execution_with_publish` **no** lanza.
4. Idempotencia: `provider.get_item` devuelve el estado ya igual al target ⇒ `{"skipped": True, "reason": "already_in_state"}` sin escribir.
5. Flag OFF ⇒ camino legacy: se llama `AdoClient().update_work_item_state(4242, "To Do")` (byte-idéntico a hoy).
6. `ado_id` es `None` ⇒ `{"skipped": True, "reason": "no_ado_id"}` (`:523-524`, comportamiento preservado).

Registrar en `run_harness_tests.sh` **y** `.ps1`.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_writer_routed.py" -v
```

**Criterio de aceptación (BINARIO):**
- `6 passed`.
- **Y** el test `test_e3_el_escritor_no_puede_ser_ado_only` de F0 pasa a **VERDE**.
- **Y** `pytest backend/tests/test_output_watcher.py` sigue verde (tiene 3 stubs de `update_work_item_state` en `:356-370`, `:386`, `:413` que dependen de este camino) — **correr por archivo, y hasta 3 veces si aparece `SQLITE_LOCKED`**.

**Flag:** `STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED` — **default ON**. Cablear las 7 patas de §3.1 en esta fase; agregar la key a `test_plan271_flags.py`.
**Impacto por runtime:** ninguno específico — el chokepoint es común a los 3. Fallback: flag OFF ⇒ `AdoClient` directo, idéntico a hoy.
**Trabajo del operador: ninguno.**

---

### F4 — Gate de publish preciso (cierra RC-2)

**Objetivo (1 frase):** que el estado deje de bloquearse cuando no había nada que publicar, conservando el bloqueo cuando la publicación se intentó y falló.
**Valor:** cierra la causa raíz secundaria. Va **después** de F3 para que la escritura que se desbloquea ya vaya al tracker correcto.

**Archivo a editar:** `backend/services/agent_completion_internal.py` — **solo** el bloque `:260-280` (Paso 4).

**Regla exacta (implementala literal, es una tabla, no un criterio):**

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

**Diff ilustrativo — reemplazar `:265-280`:**

```python
# ANTES
if not effective_target:
    state_result = {"skipped": True, "reason": "not_requested"}
elif final_status == "completed" and not publish_result.get("ok"):
    state_result = {"skipped": True, "reason": "publish_not_ok",
                    "publish_status": publish_result.get("reason") or publish_result.get("event")}
else:
    state_result = _attempt_state_change(...)

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
    if isinstance(state_result, dict):
        state_result.setdefault("source", target_source)
```

**Lo que NO se toca (invariantes duros, escritos para que no te tiente):**
- El early-return de `review_mode_hold` (`:210-224`) **queda igual**. Es HITL deliberado: el operador eligió revisar antes de publicar. Su razón se vuelve visible en F5, pero su semántica no cambia.
- `publish.failed` y `publish.idempotent_replay` **siguen bloqueando**: ahí sí hubo un intento de publicación que no llegó, y un ticket cerrado sin su evidencia sería una mentira.

**Archivo de test a crear:** `backend/tests/test_plan271_publish_gate.py`
**Casos (8) — es una tabla de verdad, uno por fila:**

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

Registrar en `run_harness_tests.sh` **y** `.ps1`.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_publish_gate.py" -v
```

**Criterio de aceptación (BINARIO):**
- `8 passed`.
- **Y** el test `test_rc2_sin_html_no_debe_bloquear_la_transicion` de F0 pasa a **VERDE**.
- **Y** `pytest backend/tests/test_b2_transition_from_config.py` sigue verde (5 tests, `:28,42,63,73,83`) — **y de paso registralo en `run_harness_tests.sh` y `.ps1`: hoy NO está registrado** (`grep -c test_b2_transition_from_config` en ambos scripts devuelve `0`).
- **Y** `pytest backend/tests/test_u2_publish_review_mode.py` sigue verde (monkeypatchea el resolver en `:157`).

**Flag:** `STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED` — **default ON**, justificación completa en §3.2. Cablear las 7 patas; agregar la key a `test_plan271_flags.py`.
**Impacto por runtime:** el chokepoint es común a los 3. En Copilot/vscode_bridge el cierre suele venir por `output_watcher` (`:412`) con `html_output_path` presente ⇒ el caso 2 casi no aplica; en Codex/Claude CLI el cierre por `api/tickets.py:1386` puede venir sin HTML ⇒ ahí el fix se nota. Fallback: flag OFF ⇒ comportamiento actual, idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F5 — La razón del no-cambio se persiste (backend)

**Objetivo (1 frase):** que la razón por la que un ticket no se movió quede escrita en el `metadata_json` de la ejecución y se promueva en el payload de `/api/executions/<id>`.
**Valor:** cierra E-2 del lado backend. Hoy la razón muere en `CloseResult` y en `SystemLog`.

**Archivos a editar:**
1. `backend/services/agent_completion_internal.py` — persistir `state_result` en metadata antes del `return` (`:290-298`).
2. `backend/services/completion_state.py` — persistir el resultado de `maybe_apply_state_transition` en metadata dentro de `_logged` (`:164-191`), además del `SystemLog` que ya escribe.
3. `backend/api/executions.py` — promover la key en `_with_outcome` (`:65-92`).

**Nombres exactos:**
- Key en `metadata_json`: **`final_state_outcome`**.
- Forma congelada: `{"applied": bool, "to": str|None, "source": str, "reason": str, "at": "<iso8601>Z"}`.
- Key promovida en el payload HTTP: **`final_state_outcome`** (mismo nombre, nivel superior).
- Helper nuevo en `agent_completion_internal.py`: `_persist_final_state_outcome(*, execution_id: int, result: dict, source: str | None) -> None` — best-effort, nunca lanza, modelado sobre `_set_publish_hold` (`:419-431`), que ya hace exactamente este patrón de merge en `metadata_dict`.
- Helper nuevo en `completion_state.py`: reusar el mismo `_persist_final_state_outcome` importándolo (import local dentro de `_logged` para no acoplar el daemon).
- Gate: `_reason_visible_enabled()` con el patrón de instancia (`from config import config as _cfg`).

**Pseudocódigo del helper:**

```python
def _persist_final_state_outcome(*, execution_id: int, result: dict, source: str | None) -> None:
    """Plan 271 F5 — deja la razón del cambio (o del no-cambio) donde la UI ya mira.
    Best-effort: nunca lanza, nunca bloquea el cierre."""
    if not _reason_visible_enabled():
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
                "source": result.get("source") or source or "none",
                "reason": result.get("reason") or ("ok" if result.get("ok") else "unknown"),
                "at": _utc_now_iso(),
            }
            row.metadata_dict = md
    except Exception:  # noqa: BLE001
        logger.debug("[exec=%s] persistir final_state_outcome falló (no crítico)",
                     execution_id, exc_info=True)
```

**Puntos de llamada exactos (4):**
- `agent_completion_internal.py`, justo antes del `return CloseResult(...)` de `:290`, con `result=state_result`.
- `agent_completion_internal.py`, en el early-return de `review_mode_hold` (`:216-224`), con `result={"skipped": True, "reason": "review_mode_hold"}`.
- `agent_completion_internal.py`, dentro de `publish_execution_from_review` antes del `return` de `:493`, con `result=state_result`.
- `completion_state.py`, dentro de `_logged` (`:164-191`), justo antes del `return result` de `:191`, tomando `execution_id=ev.get("execution_id")`.

**Edición en `api/executions.py`** — dentro de `_with_outcome` (`:65-92`), después del bloque de `outcome_reason` (`:77-87`) y antes del `dirty_ids` (`:88-91`):

```python
if _reason_visible_enabled():
    fso = meta.get("final_state_outcome") if isinstance(meta, dict) else None
    if isinstance(fso, dict):
        d["final_state_outcome"] = fso
```

> **Por qué acá y no un endpoint nuevo:** `_with_outcome` ya es el promotor canónico de causas del plan 254, se aplica tanto al listado como al detalle (`get_execution`, `:232-242`), y `ExecutionDetailDrawer.tsx:79-88` ya consume ese payload. Endpoint nuevo = superficie nueva sin necesidad.

**Archivo de test a crear:** `backend/tests/test_plan271_reason_persisted.py`
**Casos (6):**
1. Cierre con transición OK ⇒ `metadata["final_state_outcome"] == {"applied": True, "to": "To Do", "source": "role", "reason": "ok", "at": <iso>}`.
2. Cierre con `publish_not_ok` ⇒ `applied=False`, `reason="publish_not_ok"`.
3. Cierre en `review_mode_hold` ⇒ `applied=False`, `reason="review_mode_hold"`.
4. Skip del motor matriz con `no_config` ⇒ `applied=False`, `reason="no_config"`.
5. Flag `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED=False` ⇒ la key **no** se agrega al metadata **ni** al payload de `/api/executions/<id>` (sin hueco ni error, igual que `_outcome_badge_enabled` en `:75-76`).
6. `GET /api/executions/<id>` devuelve `final_state_outcome` con la forma exacta cuando existe.

Registrar en `run_harness_tests.sh` **y** `.ps1`.

**Comando exacto:**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_reason_persisted.py" -v
```
> Este archivo toca la DB. Si aparece `SQLITE_LOCKED`, **volvé a correr el mismo archivo** (hasta 3 intentos). No corras la suite completa.

**Criterio de aceptación (BINARIO):**
- `6 passed`.
- **Y** el test `test_rc1_razon_del_skip_nunca_es_silenciosa` de F0 pasa a **VERDE** (con lo que **los 4 de F0 quedan verdes**).
- **Y** `pytest backend/tests/test_plan254_*.py` — correr **cada archivo por separado** — sigue verde.

**Flag:** `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` — **default ON** (solo lectura). Cablear las 7 patas; agregar la key a `test_plan271_flags.py`, que ahora debe cubrir **las 4**.
**Impacto por runtime:** ninguno — se persiste aguas abajo de los 3. Fallback: flag OFF ⇒ ninguna key nueva, la UI no dibuja nada.
**Trabajo del operador: ninguno.**

---

### F6 — La razón se ve donde el operador ya mira (frontend)

**Objetivo (1 frase):** mostrar en el drawer de la ejecución, en castellano y con acción sugerida, por qué la incidencia se movió o por qué no.
**Valor:** cierra E-2. El operador deja de necesitar leer logs para entender un ticket que no se movió.

**Archivos a crear:**
- `frontend/src/utils/finalStateOutcome.ts` — módulo **puro** (mapa razón → etiqueta/tono/acción).
- `frontend/src/utils/__tests__/plan271FinalStateOutcome.test.ts` — vitest sobre el módulo puro.

**Archivos a editar:**
- `frontend/src/types.ts` — agregar el campo opcional al tipo de la ejecución, junto a `dirty_close_pending_review` (`:161`).
- `frontend/src/components/ExecutionDetailDrawer.tsx` — consumir el módulo y renderizar, junto al bloque de `outcome`/`dirtyClose` (`:79-88`).

> **Por qué un módulo `.ts` puro y no un test de render:** `@testing-library/react` y `jsdom` **no están instalados** en este repo. Un test de vitest que renderice React no es ejecutable acá. Es exactamente el mismo razonamiento que `frontend/src/utils/outcomeReason.ts:1-10` ya dejó escrito. **Copiá esa estructura.**

**Contenido exacto del módulo:**

```ts
// frontend/src/utils/finalStateOutcome.ts
// Plan 271 F6 — mapa puro `final_state_outcome.reason` → etiqueta + tono + acción.
// Doce razones distintas hoy colapsan a "no pasó nada". El operador no puede
// distinguir "falta configurar" de "el humano lo movió a mano", y son acciones OPUESTAS.

export type FinalStateTone = "exito" | "atencion" | "espera" | "error";

export interface FinalStateLabel {
  label: string;
  tone: FinalStateTone;
  /** Acción sugerida en una línea. Vacío = no hay nada que hacer. */
  action: string;
}

export interface FinalStateOutcome {
  applied?: boolean;
  to?: string | null;
  source?: string;
  reason?: string;
  at?: string;
}

/** Las 12 razones del backend, ni una más ni una menos. */
export const FINAL_STATE_REASON_LABELS: Record<string, FinalStateLabel> = {
  ok:                 { label: "Movida al estado configurado", tone: "exito",    action: "" },
  no_config:          { label: "Nadie configuró a qué estado mover",  tone: "atencion", action: "Configuralo en Ajustes → Estados, en la tarjeta del rol" },
  flag_off:           { label: "El movimiento automático está apagado", tone: "atencion", action: "Prendé 'estado final del empleado' en Ajustes → Arnés" },
  no_agent_type:      { label: "No se pudo saber qué rol terminó",  tone: "error",    action: "Revisá el empleado asignado a la incidencia" },
  not_ok_status:      { label: "No terminó bien: no se movió",      tone: "atencion", action: "Revisá el resultado antes de moverla" },
  not_requested:      { label: "Sin estado destino para este cierre", tone: "atencion", action: "Configuralo en Ajustes → Estados" },
  publish_not_ok:     { label: "No se publicó el comentario: no se movió", tone: "error", action: "Mirá el error de publicación y reintentá" },
  review_mode_hold:   { label: "En espera de tu revisión",          tone: "espera",   action: "Aprobá la publicación para que se mueva" },
  human_moved_out_of_flow: { label: "La moviste vos: Stacky no la pisó", tone: "espera", action: "" },
  already_in_state:   { label: "Ya estaba en ese estado",           tone: "exito",    action: "" },
  no_ado_id:          { label: "La incidencia no tiene id en el tracker", tone: "error", action: "Vinculala al tracker" },
  provider_unavailable: { label: "No se pudo hablar con el tracker", tone: "error",   action: "Revisá la conexión del tracker en Ajustes" },
};

/** Un reason futuro NO rompe la UI: string crudo, tono neutro, nunca `undefined`. */
export function describeFinalState(o: FinalStateOutcome | null | undefined): FinalStateLabel | null {
  if (!o || !o.reason) return null;
  const known = FINAL_STATE_REASON_LABELS[o.reason];
  if (known) {
    if (o.reason === "ok" && o.to) {
      return { ...known, label: `Movida a "${o.to}"` };
    }
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
y renderizarlo con la misma estructura de clases de tono que ya usa `outcomeToneClass` (`:91-97`): reusá `styles.toneExito` / `styles.toneError` / `styles.toneAtencion`.

> **Ratchet de deuda UI (obligatorio):** este archivo es existente, pero **cualquier `.tsx` nuevo debe tener CERO `style={{}}` inline** — usá clases del `.module.css` o `ref`+`effect`. En esta fase no se crea ningún `.tsx` nuevo, así que alcanza con no introducir inline-style en el drawer.

**Casos del test de vitest (`plan271FinalStateOutcome.test.ts`) — 6:**
1. `describeFinalState(null)` ⇒ `null`.
2. `describeFinalState({})` ⇒ `null`.
3. `describeFinalState({reason: "ok", to: "To Do"})` ⇒ `label` contiene `"To Do"`, `tone === "exito"`.
4. `describeFinalState({reason: "no_config"})` ⇒ `tone === "atencion"` y `action` **no vacío**.
5. `describeFinalState({reason: "inventado_futuro"})` ⇒ `label === "inventado_futuro"`, `tone === "atencion"`, no lanza.
6. `Object.keys(FINAL_STATE_REASON_LABELS).length === 12` y **todas** las entradas tienen `label` no vacío.

**Comando exacto:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/utils/__tests__/plan271FinalStateOutcome.test.ts
```
> **Correr por archivo.** La corrida completa de vitest tiene contaminación cross-file conocida en este repo.

**Criterio de aceptación (BINARIO):**
- `6 passed` en el archivo de vitest.
- **Y** `npx tsc --noEmit` desde `frontend/` termina con **0 errores**.
- **Y** los ratchets de UI siguen verdes: correr los archivos de test de ratchet que ya existen bajo `frontend/src/**/__tests__/` cuyo nombre contenga `ratchet` o `uiDebt` — **por archivo**.

**Flag:** `STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED` (ya cableada en F5). El frontend no lee la flag: si el backend no manda la key, `describeFinalState` devuelve `null` y no se dibuja nada. **Sin hueco ni error.**
**Impacto por runtime:** ninguno — es UI, común a los 3. Fallback: sin la key, no se dibuja.
**Trabajo del operador: ninguno.**

---

### F7 — Cierre: meta-tests, registro y consistencia

**Objetivo (1 frase):** garantizar que nada de lo agregado deja un meta-test rojo y que las 4 flags están completas en sus 7 patas.
**Valor:** evita el falso verde clásico (test nuevo que nadie corre porque no está en `HARNESS_TEST_FILES`).

**Archivos a editar:** solo los dos scripts, si quedó algo sin registrar.
- `backend/scripts/run_harness_tests.sh` — `HARNESS_TEST_FILES`
- `backend/scripts/run_harness_tests.ps1` — `$HarnessTestFiles`

**Checklist de archivos que DEBEN estar en ambos scripts al terminar (7):**
1. `tests/test_plan271_caracterizacion.py`
2. `tests/test_plan271_final_state_resolver.py`
3. `tests/test_plan271_flags.py`
4. `tests/test_plan271_role_fallback.py`
5. `tests/test_plan271_writer_routed.py`
6. `tests/test_plan271_publish_gate.py`
7. `tests/test_plan271_reason_persisted.py`
8. `tests/test_b2_transition_from_config.py` — **preexistente y hoy NO registrado**; este plan lo adopta.

**Comandos de verificación (corré los 4, uno por uno):**
```powershell
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_harness_flags.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_harness_flags_help.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_plan271_flags.py" -v
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m compileall -q "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\services" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\api" "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\harness"
```

**Criterio de aceptación (BINARIO):**
- Los 3 archivos de pytest en verde y `compileall` sin salida.
- **Y** un `grep` de cada uno de los **8** nombres del checklist devuelve **≥1 hit en `.sh` y ≥1 hit en `.ps1`** (8 × 2 = **16 hits**, ni uno menos).
- **Y** los **4** tests de `test_plan271_caracterizacion.py` están en **verde** (de `0 passed, 4 failed` en F0 a `4 passed` acá).

> **Alcance acotado a propósito:** este criterio NO dice “y si algo más queda rojo se arregla”. El corpus es exactamente esos 8 archivos y esas 4 flags. Un rojo preexistente ajeno (por ejemplo, los 4 fallos conocidos de `test_harness_flags_help.py`) **no** es alcance de este plan: si aparece, se prueba que ya estaba rojo antes con un worktree en el commit base y se declara.

**Flag:** ninguna.
**Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en el plan) |
|---|---|---|---|
| R1 | **Proyectos que hoy dependen de que el nivel de rol NO transicione** cambian de comportamiento al prender F2. Es exactamente lo que el plan 208 quiso evitar (`208 §5 R-EXCEPCION`). | Media | El estado destino sale de una UI cuyo texto literal es *“a cuál mueve el ticket al terminar”* (`StatesConfigPage.tsx:102`): si está cargado, es porque el operador lo quiso. Además `_origin_guard` (`completion_state.py:121-161`) sigue impidiendo pisar un ticket que el humano movió a mano, y la flag `STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED` permite volver atrás sin redeploy. |
| R2 | F4 provoca transiciones que hoy no ocurren ⇒ escritura nueva en el tracker real del operador. | Media | Acotado a **4 razones enumeradas** en `_PUBLISH_REASONS_SIN_NADA_QUE_PUBLICAR`. `publish.failed`, `publish.idempotent_replay` y `review_mode_hold` **siguen bloqueando**. La lista es un `frozenset` congelado y el test 6/7/8 de F4 lo prueba. |
| R3 | **Doble transición**: los motores A y B pueden apuntar al mismo ticket con destinos distintos. | Media | Ya pasa hoy y este plan no lo empeora, pero lo hace **visible**: `final_state_outcome` guarda `source`, así que una discrepancia se ve en el drawer. Además `_safe_transition` es idempotente (`task_states.py:161-168`): si el primero ya dejó el ticket en el destino, el segundo devuelve `already_in_state` sin escribir. **Unificar los dos motores queda fuera de scope** (§6). |
| R4 | `get_tracker_provider` lanza `TrackerConfigError` en un proyecto GitLab con `STACKY_GITLAB_ENABLED=false` y rompe el cierre. | Baja | F3 envuelve la llamada en `try/except` y devuelve `{"skipped": True, "reason": "provider_unavailable"}`. El cierre nunca falla por esto (test 3 de F3), y la razón se muestra al operador (F6). |
| R5 | `SQLITE_LOCKED` hace flaky a F5. | Alta | Regla escrita en §3.9 y repetida en F5: correr **por archivo**, reintentar hasta 3 veces el mismo archivo, nunca la suite completa. |
| R6 | El implementador toca `run_harness_tests.ps1` con la sintaxis del `.sh`. | Media | §3.10 y F0/F7 dicen la diferencia literal: `.sh` usa líneas con dos espacios y sin comillas; `.ps1` usa `"tests/..."` con comillas dobles dentro de `$HarnessTestFiles`. El criterio de F7 exige 16 hits, 8 por script. |
| R7 | El texto del `PlainHelp` rompe uno de los 3 meta-tests de `harness_flags_help.py`. | Media | §3.1 pata 4 enumera las 3 restricciones exactas (empezar con `"Si "`, sin jerga, ≤240 chars) y F1 trae un texto de ejemplo que ya las cumple. |
| R8 | Colisión con el plan 270, que también trabaja el cierre. | Baja | El 270 declara literal que no toca `agent_completion_internal.py` ni `completion_state.py` (0 menciones en su doc), y su F3 se acota a `api/tickets.py:2073-2094`. **Este plan no toca `api/tickets.py`.** Los nombres nuevos (`final_state_resolver.py`, `final_state_outcome`, `finalStateOutcome.ts`, las 4 flags `STACKY_FINAL_STATE_*`) no colisionan con ninguno de los símbolos que el 270 reserva. |

---

## 6. Fuera de scope (explícito, para que nadie lo agregue “de paso”)

1. **Unificar los motores A y B en uno solo.** Es el arreglo estructural correcto, pero es una migración con riesgo propio y merece su plan (sugerido: **272**). Este plan los deja coherentes y observables, no fusionados.
2. **Deduplicar `_infer_agent_type_from_filename`** (C-f: `agent_completion_internal.py:304-318`, `api/agents.py:1766-1767`, `services/agent_history.py:54-55`). Las tres copias hoy coinciden para `technical`; no causó el bug.
3. **Construir la UI de la matriz `by_work_item_type` dentro de `StatesConfigPage`.** El plan 216 dejó el ancla (`{/* PLAN-208: matriz by_work_item_type va aquí */}`) y es alcance del 208. Este plan hace que **no haga falta** para que la transición funcione.
4. **Cambiar la semántica de `review_mode_hold`.** Es HITL deliberado. Solo se hace visible.
5. **Transicionar en `needs_review`.** Exige revisión humana; auto-transicionar violaría HITL.
6. **`api/tickets.py`** en cualquiera de sus formas (`set_stacky_status_by_ado:1487-1520`, `finish_work:2073-2094`, `:4781`). Es territorio del 270.
7. **`deployment/harness_defaults.env`.** Snapshot derivado, ya divergente.
8. **Migrar `agent_workflow_configs.transition_state` al perfil del cliente.** El 216 lo declaró fuera de scope y sigue estándolo.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **Motor A / “matriz”** | `completion_state.maybe_apply_state_transition`, disparado por post-hook del `completion_dispatcher`. Lee `tracker_state_machine`. |
| **Motor B / “employee_config”** | `agent_completion_internal.close_execution_with_publish`, Pasos 3.5 y 4. Lee `agent_workflow_configs[<filename>].transition_state`. |
| **Nivel rol** | `tracker_state_machine.<agent_type>.next_state_ok`. Lo que `StatesConfigPage.tsx` sabe escribir. |
| **Celda de matriz** | `tracker_state_machine.<agent_type>.by_work_item_type.<tipo>.next_state_ok`. Solo `ClientProfileEditor.tsx:467-477` la escribe. |
| **Chokepoint** | `close_execution_with_publish` (`agent_completion_internal.py:66`). |
| **Gate espurio** | Un `if` que bloquea una acción por una condición que no aplica al caso. Acá: bloquear el estado por un publish que nunca tuvo nada que publicar. |
| **Skip mudo** | Un `return {"skipped": True}` cuya razón no llega a ninguna superficie que el operador mire. |
| **7 patas** | Los 7 lugares que toca una flag nueva (§3.1). El “patrón triple” es un mito. |

### 7.2 Orden de implementación (estricto, por dependencia)

```
F0 (rojo, sin prod)
 └─> F1 (resolver puro + flag 1)
      └─> F2 (cablear motor A)          ← cierra RC-1, el bug reportado
 └─> F3 (writer ruteado + flag 2)       ← cierra E-3 (paridad)
      └─> F4 (gate preciso + flag 3)    ← cierra RC-2  [DESPUÉS de F3 a propósito]
           └─> F5 (persistir razón + flag 4)
                └─> F6 (mostrar razón)  ← cierra E-2
                     └─> F7 (cierre)
```

**Ninguna fase Fk depende de algo que se construye en Fk+1.** Verificado ítem por ítem:
- F2 usa solo `final_state_resolver` (F1). ✔
- F3 usa solo `tracker_provider` y `_safe_transition`, ambos **preexistentes**. ✔
- F4 usa el kwarg `project_name` que **F3 ya agregó**. ✔
- F5 usa las razones que F2/F3/F4 ya producen. ✔
- F6 usa la key que F5 ya promueve. ✔
- F7 solo verifica lo de F0..F6. ✔

**F1+F2 se pueden entregar solas** y ya cierran el bug reportado. F3..F7 son el resto de la deuda.

### 7.3 Definition of Done

- [ ] `test_plan271_caracterizacion.py`: `0 passed, 4 failed` al terminar F0 → **`4 passed`** al terminar F7.
- [ ] `test_plan271_final_state_resolver.py`: 13 passed.
- [ ] `test_plan271_role_fallback.py`: 7 passed.
- [ ] `test_plan271_writer_routed.py`: 6 passed.
- [ ] `test_plan271_publish_gate.py`: 8 passed.
- [ ] `test_plan271_reason_persisted.py`: 6 passed.
- [ ] `test_plan271_flags.py`: las 4 keys con `default is True` y presentes en `_CATEGORY_KEYS["flujo_funcional"]`.
- [ ] `plan271FinalStateOutcome.test.ts`: 6 passed. `npx tsc --noEmit`: 0 errores.
- [ ] `test_harness_flags.py` y `test_harness_flags_help.py`: verdes (por archivo).
- [ ] `test_b2_transition_from_config.py`, `test_u2_publish_review_mode.py`, `test_output_watcher.py`: verdes (por archivo).
- [ ] Los 8 archivos del checklist de F7 registrados en **ambos** scripts (16 hits).
- [ ] `compileall` de `services/`, `api/` y `harness/` sin salida.
- [ ] Las 4 flags con línea `=true` en `backend/harness_defaults.env`.
- [ ] Ninguna flag nueva nace OFF. (Verificable: `grep "STACKY_FINAL_STATE_" backend/harness_defaults.env` ⇒ 4 líneas, todas `=true`.)
- [ ] Smoke manual (una vez, el operador o el implementador): con un proyecto que tenga `tracker_state_machine.technical.next_state_ok = "To Do"` y **sin** `by_work_item_type`, correr el Analista Técnico sobre una incidencia y verificar en el tracker que quedó en `To Do`, y en el drawer de la ejecución que dice **“Movida a "To Do"”**.
