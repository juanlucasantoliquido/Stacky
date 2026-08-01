# Plan 280 — El desenlace mira el trabajo entregado: un solo veredicto

**Estado:** v1 — PROPUESTO, 2026-08-01
**Rama:** `docs/plan-279` (rama de trabajo vigente; el plan 280 no abre rama nueva)

---

## 1. Objetivo y KPI

**Objetivo:** que Stacky deje de reportar como fallo un trabajo que efectivamente entregó, unificando en **un solo motor** la decisión del desenlace de los 4 runtimes, y haciendo que ese motor consulte **el artefacto real** y no solo proxies del proceso.

**La tesis, en una frase:** *nadie mira el trabajo*. Cuatro runtimes deciden el desenlace con proxies del proceso — exit code, evento `result`, watchdog — y **ninguno consulta el artefacto que el agente escribió**, aunque ese artefacto está en una variable en scope 214 líneas antes de la decisión.

### KPI binarios

| # | KPI | Medición | Estado hoy (medido) |
|---|---|---|---|
| **K1** | `outcome_reason_to_status` deja de ser código muerto | censo AST de referencias en producción | **0** → debe quedar **≥ 3** |
| **K2** | Motores que deciden el estado terminal | censo AST de clasificadores | **4 ciegos entre sí** → **1** compartido en los 3 runtimes de agentes (`qa_browser` = deuda declarada, ver F3) |
| **K3** | Una corrida con trabajo entregado y cierre sucio nunca cae en `error` | test sobre `classify_outcome_reason` | hoy cae en `cli_failure` → `error` |
| **K4** | Los 4 call-sites pasan el juego COMPLETO de señales | censo AST de kwargs por call-site | **2 / 3 / 4 / 4 de 8** → **8 de 8** |
| **K5** | Ningún falso rojo se convierte en verde automático | test de invariante | debe ser `needs_review`, **nunca** `completed` |
| **K6** | Un webhook no puede pintar de rojo una corrida exitosa | test que reproduce el `TypeError` | hoy lo pinta: 4 corridas medidas |
| **K7** | Un cierre sucio con trabajo no termina en `completed` | simulación contra las 15 corridas con taxonomía | hoy **2 falsos verdes vivos** (execs 190 y 213) |

**K5 es un guardarraíl, no una métrica de mejora.** El plan corrige un falso ROJO; no se le permite crear un falso VERDE. Human-in-the-loop es riel duro: Stacky no declara éxito por su cuenta.

---

## 2. Evidencia real (anclaje anti-alucinación)

Toda la evidencia sale de la **BD viva** (`backend/data/stacky_agents.db`, 193 MB, leída con `mode=ro`) y del código en `HEAD = ea027933`.

### E1 — La magnitud: 44 corridas con trabajo, reportadas como fallo

```sql
SELECT COUNT(*), SUM(length(output)) FROM agent_executions
WHERE status IN ('error','failed') AND length(COALESCE(output,''))>200;
-- (44, 93447)
```

**44 ejecuciones y 93.447 caracteres de trabajo real** viven bajo un estado `error`. Sobre 217 ejecuciones totales, 109 son no-exitosas (50,2 %); **40,4 % de esas fallas produjeron trabajo**.

### E2 — El caso del operador: la ejecución 212

```
exec 212 | agent=technical | status=error | output=19593 chars
         | error_message="claude code cli exited with code 1"
         | outcome_reason="cli_failure"   <-- metadata REAL en la BD
```

`cli_failure` está definido en `services/run_outcome.py:22` como *"rc != 0 **sin evidencia de trabajo** → fallo real"*. La 212 tiene **19.593 caracteres de evidencia de trabajo** y aun así recibió esa etiqueta. Es el análisis técnico que el operador vio generarse, validarse y no publicarse.

### E3 — La secuencia literal del falso rojo (ejecución 211, logs de la BD)

```
15:52:30.428  info   tool_result(ok): File created successfully at ...analisis-funcional.md
15:52:34.421  warn   254-F3 drenaje del stream VENCIÓ tras 15.0s — puede haber eventos
                     leídos después de clasificar el desenlace
15:52:34.451  error  claude code cli exited with code 1
```

El agente **terminó de escribir el archivo** y 4 segundos después la corrida se clasificó como error. El `warn` intermedio es el instrumento que el plan 254 F3 dejó puesto: **mide** la carrera y no actúa sobre ella.

Ocho ejecuciones tienen ese `warn`; **cinco terminaron en `error`, todas con output > 0**:

```
185 qa        needs_review  3884     190 qa        completed  4031
186 qa        error          612     211 functional error       474
187 qa        error         2055     212 technical  error     19593
189 qa        error         1212     216 technical  needs_review 4211
```

### E4 — El defecto 1: la regla 8 recibe el trabajo y no lo mira

`services/run_outcome.py:55-101`. La firma **recibe `last_result_text`** (línea 61) — es decir, el output real:

```python
    if _has_quota_marker(stderr_excerpt, last_result_text):   # :91  ← único uso
        return "quota_exhausted"
    ...
    if result_ok_seen or ticket_already_terminal:             # :99  ← regla 8
        return "dirty_exit_after_work"
    return "cli_failure"                                      # :101
```

`last_result_text` se usa **exclusivamente** para buscar marcadores de cuota (`:91`). La regla 8 (`:99`), la que decide "hubo trabajo pese al cierre sucio", **no lo consulta**. Por eso la 212 cae a `:101`.

### E5 — El defecto 2: el mapa correcto existe, está testeado, y está MUERTO

`services/run_outcome.py:34-45` define el mapa correcto, y `:113-121` la función que lo aplica:

```python
_REASON_TO_STATUS = {
    "dirty_exit_after_work": "needs_review",   # ← la respuesta correcta, ya escrita
    "stall_after_work":      "needs_review",
    ...
}
def outcome_reason_to_status(reason: str) -> str:   # :113
    return _REASON_TO_STATUS.get(reason, "needs_review")
```

**Censo por AST de referencias (no de llamadas — cuenta `Name`, `Attribute` e `ImportFrom`, para no dar cero si va por alias):**

```
=== REFERENCIAS EN PRODUCCION (excluye la definicion y los tests) ===
  _classify_run_outcome:    1  → services\claude_code_cli_runner.py
  classify_outcome_reason:  4  → agent_runner.py, services\agent_completion.py,
                                 services\claude_code_cli_runner.py, services\codex_cli_runner.py
  is_operator_actionable:   1  → api\executions.py
  outcome_reason_to_status: 0          <-- CODIGO MUERTO
=== REFERENCIAS EN TESTS ===
  outcome_reason_to_status: 2
```

El plan 254 **construyó la respuesta correcta, la testeó, quedó verde, y nunca la cableó**.

**Baseline REAL medido, por archivo** (`DATABASE_URL="sqlite:///:memory:"`, venv `backend/venv`):

```
tests/test_plan254_outcome_reason.py  -> 11 passed
tests/test_plan254_stream_drain.py    ->  6 passed
tests/test_plan254_reconciliation.py  -> 10 passed
tests/test_plan254_falso_rojo.py      ->  9 passed
tests/test_stall_watchdog.py          -> 16 passed
```

Los 11 de `outcome_reason` verifican una función que **producción no invoca**. (Nota: correr los dos primeros archivos juntos reporta `17 passed`, que es la SUMA `11+6` — no el conteo del primero. Los gates de este plan usan los conteos **por archivo**.)

### E6 — El defecto 3: cuatro motores ciegos entre sí

| Runtime | Quién decide el estado | Señales | ¿Mira el trabajo? |
|---|---|---|---|
| `claude_code_cli` | `_classify_run_outcome` (`claude_code_cli_runner.py:399-414`), llamada en `:1788` | `stall_fired`, `result_ok_seen`, `return_code` | **No** — `output` está en scope desde `:1574`, la firma `:400` ni lo recibe |
| `codex_cli` | `if/elif` inline (`codex_cli_runner.py:816`, `:884`, `:1156`) | `return_code`, `_codex_stall_fired` | **No** — `output` leído en `:746` |
| `github_copilot` | `agent_runner.py:977`, `:1037-1043`, `:1069-1099` | excepción Python | **No** — `result.output` existe en `:929` |
| `qa_browser` | `_mark_terminal_if_needed` (`qa_browser_runner.py:240-275`) | ninguna: `:272` pone `"error"` **incondicional**, incluso con `rc==0` | **No** |

Los tres `_mark_terminal` (`claude:3091`, `codex:1962`, `agent_runner:1135`) son **funciones homónimas distintas con firmas distintas**.

### E7 — El defecto 4: los call-sites llaman con juegos de señales distintos

`classify_outcome_reason` acepta 8 parámetros. Cada call-site pasa un subconjunto **diferente**:

| Call-site | Pasa | De 8 |
|---|---|---|
| `agent_runner.py:1125` | `return_code`, `stderr_excerpt` | **2** |
| `services/agent_completion.py:67` | `return_code`, `result_ok_seen`, `last_result_text` — y `result_ok_seen` es **circular** (`payload.status=="completed"`) | **3** |
| `services/codex_cli_runner.py:804` | `return_code`, `stall_fired`, `stderr_excerpt`, `last_result_text` | **4** |
| `services/claude_code_cli_runner.py:1801` | `return_code`, `result_ok_seen`, `stall_fired`, `stderr_excerpt`, `last_result_text` | **5** |

**Consecuencia dura y verificable:** codex **nunca** pasa `result_ok_seen` (queda en el default `False` de `run_outcome.py:58`), por lo que **codex no puede producir `dirty_exit_after_work` jamás**. Todo `rc != 0` con trabajo entregado cae en `cli_failure` → `error`.

Además, `reaper_kind` y `preflight_block` (`:63-64`) **no tienen ningún productor de producción**: los reasons `preflight_blocked`, `reaper_timeout` y `reaper_heartbeat` son **inalcanzables en runtime**.

### E8 — Stacky ya sabe detectar el falso rojo… en modo lectura

`services/run_reconciliation.py:84-92`:

```python
    entrego_trabajo = bool(evidence.result_ok_seen) or evidence.return_code == 0   # :84
    if evidence.ticket_status == "error" and entrego_trabajo:                       # :87
        _add("red_with_delivered_work", ...)
```

El detector existe y nombra el defecto (`red_with_delivered_work`). Pero:
1. es **read-only post-mortem** (`scan_recent`, `:168-171`: "no escribe una sola fila"), y
2. su propia definición de "entregó trabajo" (`:84`) **también es un proxy** (`result_ok_seen or rc==0`) — **no mira el artefacto**. Con `rc!=0` y `result_ok_seen=False`, la ejecución 212 y sus 19.593 caracteres **son invisibles hasta para el detector**.

### E10 — El otro falso rojo: un webhook rompe y pinta de rojo una corrida exitosa

Segundo defecto, **independiente del anterior y con la misma tesis**: el trabajo se hizo, el reporte miente. Reproducido byte a byte.

**`models.py:330` — `duration_ms` es un MÉTODO, no una property:**

```python
    @contract_result.setter                 # :326  ← el vecino SÍ es property
    def contract_result(self, value): ...
    def duration_ms(self) -> int | None:    # :330  ← SIN @property
```

**`services/webhooks.py:219` lo consume como si fuera un campo:**

```python
"duration_s": round((row.duration_ms or 0) / 1000, 3) if row.duration_ms else None,
```

La cadena de fallo, verificada ejecutando el código real:

```
duration_ms es       : method
truthy (guard pasa)  : True          <-- un bound method es SIEMPRE truthy
llamado correctamente: 49308
MENSAJE REAL         : unsupported operand type(s) for /: 'method' and 'int'
COINCIDE CON LA BD   : True
```

El mensaje coincide **carácter por carácter** con el `error_message` de las ejecuciones **164, 165, 166 y 167** (2026-07-26, agente `incident_dev`, outputs de 7382 / 5621 / 3999 / 4859 caracteres, `contract_result` = `passed:true, score:100`).

**Por qué explota solo en el path Copilot:** `agent_runner.py:797`, `:1011` y `:1072` llaman `webhooks.fire_for_execution(execution_id)` **desnudo**, mientras que `claude_code_cli_runner.py:82` y `codex_cli_runner.py:72` lo envuelven en `try/except`. La excepción del webhook cae en el `except Exception` de `agent_runner.py:1069`, que marca `status="error"` — y la llamada de `:1072` **vuelve a explotar desde dentro del `except`**, lo que explica el `completion_source="recovery"` de las 4 corridas: el run nunca cerró su propio ciclo.

**Por qué nunca lo atrapó CI:** `_compact_execution_payload` (`webhooks.py:201`) **no tiene un solo test**. La rama legacy (`webhooks.py:181`) usa `row.to_dict()`, que sí invoca `self.duration_ms()` **con paréntesis**; el bug vive únicamente en la rama V2, activada por `STACKY_WEBHOOKS_V2_ENABLED` (`config.py:497`, default **ON**).

Introducido el 2026-06-17 y **nunca tocado**: `git log --all -S"duration_ms /"` devuelve **cero commits**. Vivo en `HEAD`, en `main` y en `origin/main`.

### E9 — Divergencia colateral en el path copilot

`agent_runner.py:977` marca la fila `needs_review` por sobrecarga de supuestos, pero `:1037-1043` llama a `on_execution_end(final_status="completed")` **hardcodeado**: la ejecución queda `needs_review` y el ticket `completed`. Dos verdades para el mismo hecho.

---

## 3. Principios y guardarraíles

1. **G1 — El falso rojo se corrige hacia `needs_review`, NUNCA hacia `completed`.** Human-in-the-loop es riel duro. Trabajo entregado + cierre sucio = *lo mira un humano*.
2. **G2 — "Trabajo entregado" es evidencia OBJETIVA**, no auto-reporte del agente. Un agente que dice "terminé" sin artefacto no entregó nada.
3. **G3 — El motor del desenlace es PURO** (sin DB, sin red, sin imports de `db`/`models`), como ya lo es `run_outcome.py`. Se testea solo.
4. **G4 — Cero regresión de estados válidos.** Solo se emiten estados de `status_vocabulary.VALID_TICKET_STATUSES`.
5. **G5 — El guard anti-degradación del plan 254 F1 (`ticket_status.py:175-198`) NO se toca.** Es aguas abajo y sigue siendo la última defensa.
6. **G6 — Flag nueva default ON**, con assert de igualdad, registrada en los 6 lugares.
7. **G7 — No se toca la sesión paralela.** `epic_autopublish.py`, `api/tickets.py`, `uiGuards.ts`, `EpicFromBriefModal.tsx`, `test_epic_from_brief_idempotencia.py` y `test_plan276_gitlab_sync.py` están siendo modificados por otra sesión viva: **fuera de alcance de este plan**.

---

## 4. Decisiones de diseño

### D1 — "Trabajo entregado" se define por umbral de artefacto, no por señal de proceso

Función pura nueva en `run_outcome.py`:

```python
WORK_EVIDENCE_MIN_CHARS = 200

def has_delivered_work(*, output: str = "", artifact_count: int = 0,
                       result_ok_seen: bool = False,
                       ticket_already_terminal: bool = False) -> bool:
    """Evidencia OBJETIVA de trabajo entregado (G2)."""
    if result_ok_seen or ticket_already_terminal:
        return True
    if artifact_count > 0:
        return True
    return len((output or "").strip()) >= WORK_EVIDENCE_MIN_CHARS
```

El umbral de 200 caracteres **no es arbitrario**: es el mismo que usa la consulta de E1, y separa un output real de un eco de error. Se declara como constante para que el gate lo pueda asertar.

### D2 — La regla 8 pasa a consultar el trabajo

`classify_outcome_reason` recibe `work_delivered: bool = False` y las reglas 5 y 8 lo consultan:

```
  5. stall_fired y (result_ok o ticket terminal o WORK_DELIVERED)  → stall_after_work
  8. result_ok_seen o ticket_already_terminal o WORK_DELIVERED     → dirty_exit_after_work
```

El default `False` preserva el comportamiento de cualquier call-site no migrado (C9 del plan 254).

### D3 — `outcome_reason_to_status` se cablea como ÚNICO traductor razón→estado

Los runners dejan de decidir el estado con lógica propia y lo piden al motor compartido. `_classify_run_outcome` **no se borra** (romper su contrato rompe `test_stall_watchdog.py`): se convierte en un **envoltorio delgado** que delega en el motor compartido, de modo que K2 baja a 1 motor sin romper a sus consumidores.

### D4 — Paridad de señales obligatoria y verificada por AST

Los 4 call-sites pasan el juego completo. El gate cuenta los kwargs **por AST** (`ast.keyword`), no por grep.

### D5 — Una sola flag, default ON

`STACKY_OUTCOME_WORK_EVIDENCE_ENABLED`. OFF = comportamiento byte-idéntico al de hoy. No se agrega sección DevOps nueva (evita arrastrar sus dos gates).

### D5-bis — CERO cambio de frontend (verificado)

La capa de visualización **ya existe y ya está cableada**: el plan 254 F4 construyó `frontend/src/utils/outcomeReason.ts` (mapa puro `outcome_reason` → etiqueta + tono + acción), consumido por `ExecutionDetailDrawer.tsx:18,87`, con el campo declarado en `types.ts:163` y tests en `utils/__tests__/plan254OutcomeReason.test.ts`. El estado `needs_review` ya es ciudadano de primera en **8 componentes** (`OutputPanel.tsx`, `HarnessHealthCard.tsx`, `reconciliationActions.ts`, …).

Este plan cambia **qué estado se emite**, no cómo se muestra. **No se toca un solo archivo de frontend**, y por lo tanto no corre `tsc` como gate. Es otra instancia de la misma patología: las piezas existen, faltaba conectarlas.

### D6 — Fuera de alcance explícito

- No se toca `qa_browser_runner.py:272` (el `error` incondicional). Es un defecto real pero de otro subsistema; se documenta como pendiente.
- No se corrige `agent_runner.py:1037` (el `completed` hardcodeado de E9). Se documenta.
- No se crean productores para `reaper_kind`/`preflight_block`.
- No se re-clasifican retroactivamente las 44 ejecuciones históricas: **no se escribe en la BD del operador**.

---

## 5. Fases

### F0 — Censo congelado y tests que reproducen el defecto (ROJO PRIMERO)

**Objetivo:** dejar la foto vieja medida y los tests que fallan **por la razón correcta** antes de tocar producción.

**Archivo host: `backend/tests/test_plan254_falso_rojo.py` — NO se crea archivo nuevo.**

Razón (decisión de implementación, no cosmética): el arnés **no barre directorios**, es una **lista explícita de 788 archivos** iterada en `scripts/run_harness_tests.sh:1039`. Un archivo nuevo obliga a editar **los dos** ratchets (`.sh` y `.ps1`), y ambos están **modificados sin commitear por una sesión paralela viva**. Commitearlos con pathspec arrastraría el trabajo ajeno al commit de este plan (gotcha del índice compartido).

`tests/test_plan254_falso_rojo.py` **ya está registrado en los dos ratchets** (verificado: `sh=1 ps=1`), trata literalmente el mismo defecto (el falso rojo), y ya trae la fixture de DB con `sqlite:///:memory:`. **Cero fricción, cero trámite de ratchet.**

**F0.1 — El censo AST reproduce la foto vieja.** Test que corre el censo de referencias y asserta la foto de HOY:

```python
def test_censo_reproduce_la_foto_vieja():
    refs = censo_referencias_produccion()
    # Guarda primero la PRESENCIA (un assert de ausencia pasa por accidente):
    assert refs["classify_outcome_reason"] >= 4, "el censo no ve lo que sí existe"
    assert refs["outcome_reason_to_status"] == 0, "F2 ya cableó el traductor"
```

El primer assert es obligatorio: sin él, un censo roto que devuelve todo cero pasaría el segundo por accidente.

**F0.2 — El defecto de la regla 8, reproducido con el caso REAL de la 212:**

```python
def test_regla8_ignora_el_trabajo_entregado():
    """Rojo hasta F1. Reproduce exec 212: rc=1, sin result ok, 19593 chars."""
    reason = classify_outcome_reason(
        return_code=1, result_ok_seen=False, stall_fired=False,
        last_result_text="x" * 19593,
    )
    assert reason == "dirty_exit_after_work", (
        f"19593 chars de trabajo clasificados como {reason!r}"
    )
```

**F0.3 — Invariante G1 (nunca verde automático):**

```python
def test_trabajo_entregado_nunca_va_a_completed():
    for reason in ("dirty_exit_after_work", "stall_after_work"):
        assert outcome_reason_to_status(reason) == "needs_review"
        assert outcome_reason_to_status(reason) != "completed"
```

**F0.4 — Paridad de señales, foto vieja:** censo AST de kwargs por call-site que asserta `{2, 3, 4, 5}` hoy.

**Gate F0:** el archivo corre y **falla** en F0.2 (y en F0.4 tras F4). Comando:
`pytest tests/test_plan254_falso_rojo.py -q` → debe reportar **≥1 failed** ANTES de F1.

---

### F1 — `has_delivered_work` + la regla 8 mira el trabajo

**Archivos:** `services/run_outcome.py` (único).

1. Agregar `WORK_EVIDENCE_MIN_CHARS = 200` y `has_delivered_work(...)` (D1).
2. Agregar el kwarg `work_delivered: bool = False` a `classify_outcome_reason`.
3. Modificar **solo** las reglas 5 y 8 (líneas `:93` y `:99`), sin tocar el orden de precedencia.
4. Actualizar el docstring de precedencia (`:71-83`) — el orden es contrato.

**Gate F1:** F0.2 pasa a verde. Por archivo, con los conteos reales de E5:

```
pytest tests/test_plan254_outcome_reason.py -q   -> 11 passed  (SIN CAMBIO)
pytest tests/test_plan254_falso_rojo.py -q       ->  9 + N passed
```

Los 11 del 254 **no se mueven**: el default `work_delivered=False` los preserva. Verificado en particular contra `test_cli_failure_es_actionable_y_quota_no` (`tests/test_plan254_outcome_reason.py:82-84`), que llama `classify_outcome_reason(return_code=1)` **sin** `last_result_text` ni `work_delivered` — sigue devolviendo `cli_failure`.

---

### F1-bis — El webhook deja de pintar de rojo una corrida exitosa (K6)

**Independiente de F1..F6.** Se puede implementar sola; es el cambio más chico y de mayor certeza del plan.

**Test primero** (en `tests/test_plan254_falso_rojo.py`), reproduciendo el `TypeError` con un `AgentExecution` real:

```python
def test_payload_del_webhook_no_revienta_con_duration_ms():
    row = AgentExecution()
    row.started_at = datetime(2026, 7, 26, 17, 12, 0)
    row.completed_at = row.started_at + timedelta(seconds=49.308)
    # Guarda de PRESENCIA: si duration_ms dejara de ser método, el test debe
    # avisar en vez de pasar por accidente.
    assert callable(row.duration_ms), "duration_ms dejó de ser método: revisar el fix"
    payload = _compact_execution_payload(row)          # hoy: TypeError
    assert payload["duration_s"] == 49.308
```

**Fix 1 — `services/webhooks.py:219`.** Llamar al método una sola vez y cachear:

```python
_dms = row.duration_ms()
...
"duration_s": round(_dms / 1000, 3) if _dms else None,
```

**Fix 2 — defensa en profundidad.** Envolver `agent_runner.py:797`, `:1011` y `:1072` en `try/except Exception` con `logger.debug(..., exc_info=True)`, replicando literalmente el patrón que **ya existe** en `claude_code_cli_runner.py:81-84` y `codex_cli_runner.py:71-74`. *Un webhook no puede decidir el estado de una corrida.*

**Fix 3 — anti-recurrencia.** NO se convierte `models.py:330` en `@property`: rompería `AgentExecution.to_dict` y `ado_publisher.py:60`, que ya lo llaman con paréntesis. En su lugar se deja un comentario de una línea en `models.py:330` advirtiendo que es método, y el test de F1-bis congela esa verdad.

**Bomba latente relacionada (se documenta, no se toca):** `services/ado_publisher.py:60` tiene el mismo patrón (`md.get("duration_ms") or execution.duration_ms`), hoy inofensivo porque `md["duration_ms"]` existe y porque `:62-66` lo envuelve en `try/except`.

**Gate F1-bis:** el test nace ROJO con `TypeError` y queda verde tras el fix.
`pytest tests/test_plan254_falso_rojo.py -k webhook -q` → exigir el **conteo de seleccionados** (`-k` sin match da exit 0).

---

### F2 — Cablear `outcome_reason_to_status` (K1: 0 → ≥3)

**Objetivo:** que el traductor deje de ser código muerto.

En `claude_code_cli_runner.py`, `codex_cli_runner.py` y `agent_runner.py`, el estado terminal se obtiene del motor compartido cuando la flag está ON:

```python
if config.STACKY_OUTCOME_WORK_EVIDENCE_ENABLED:
    from services.run_outcome import outcome_reason_to_status
    _status_taxonomia = outcome_reason_to_status(_outcome_meta["outcome_reason"])
```

**Regla de aplicación — la taxonomía es un TECHO, nunca un ascenso (G1 + G5):**

```python
def reconciliar_estado(actual: str, taxonomia: str) -> str:
    """La taxonomía solo puede BAJAR a 'needs_review'. Jamás asciende nada.

    - error     + needs_review → needs_review  (rescata el falso ROJO)
    - completed + needs_review → needs_review  (tapa el falso VERDE)
    - needs_review + completed → needs_review  (NO asciende: preserva el gate
      de calidad de `_evaluate_output_quality`)
    """
    if taxonomia == "needs_review" and actual in ("error", "completed"):
        return "needs_review"
    return actual
```

**Por qué un techo y no una sustitución.** Verificado contra las 15 ejecuciones reales que hoy tienen `outcome_reason` en la BD: la ejecución **210** tiene `reason=clean_exit` (la taxonomía diría `completed`) pero su estado real es `needs_review` porque `_evaluate_output_quality` la degradó por contrato. Una sustitución la **ascendería de vuelta a `completed`, destruyendo el gate de calidad**. El techo la deja intacta.

**Simulación del diseño contra los datos reales de producción** (15 ejecuciones con taxonomía activa):

```
  exec  186 out=   612 cli_failure  -> dirty_exit_after_work  error     => needs_review
  exec  187 out=  2055 cli_failure  -> dirty_exit_after_work  error     => needs_review
  exec  188 out=   294 cli_failure  -> dirty_exit_after_work  error     => needs_review
  exec  189 out=  1212 cli_failure  -> dirty_exit_after_work  error     => needs_review
  exec  190 out=  4031 dirty_exit_after_work                  completed => needs_review
  exec  211 out=   474 cli_failure  -> dirty_exit_after_work  error     => needs_review
  exec  212 out= 19593 cli_failure  -> dirty_exit_after_work  error     => needs_review
  exec  213 out= 23390 stall_after_work                       completed => needs_review

CAMBIAN 8 de 15 — 6 falsos ROJOS rescatados, 2 falsos VERDES tapados.
La 210 NO cambia (gate de calidad preservado). CERO ascensos a 'completed'.
```

**Hallazgo colateral que esto corrige:** las ejecuciones **190** y **213** son **falsos VERDES vivos en producción** — `dirty_exit_after_work` y `stall_after_work` que terminaron en `completed`, exactamente lo que `run_outcome.py:117-119` declara que **nunca** debe pasar. El plan 254 escribió la regla; el runner nunca la aplicó. El techo la hace cumplir en las dos direcciones.

**Gate F2:** el censo de F0.1 se invierte — `outcome_reason_to_status` pasa de **0 a ≥3** referencias de producción. El test se actualiza en la misma fase **conservando el guard de presencia** (`classify_outcome_reason >= 4`), para que un censo roto que devuelva todo cero no lo haga pasar por accidente.

---

### F3 — Un solo motor (K2: 4 → 1)

`_classify_run_outcome` (`claude_code_cli_runner.py:399-414`) se convierte en envoltorio que delega en el motor compartido (D3).

**El contrato se preserva agregando un kwarg con default, no cambiando los existentes:**

```python
def _classify_run_outcome(*, stall_fired, result_ok_seen, return_code,
                          work_delivered: bool = False) -> str:
    reason = classify_outcome_reason(
        return_code=return_code, result_ok_seen=result_ok_seen,
        stall_fired=stall_fired, work_delivered=work_delivered,
    )
    return _REASON_TO_RUN_KIND[reason]
```

**Mapa de los 9 reasons a los 3 valores** (obligatorio y explícito, para que un modelo menor no lo resuelva de dos maneras):

| reason | valor | ¿por qué |
|---|---|---|
| `stall_no_work` | `failed_stall` | cuelgue real |
| `stall_after_work` | `success` | fija el test `:163` |
| `clean_exit` | `success` | fija el test `:172` |
| `dirty_exit_after_work` | `success` | fija el test `:181` — y el **techo de F2** le pone `needs_review` después |
| `cli_failure`, `quota_exhausted`, `preflight_blocked`, `reaper_timeout`, `reaper_heartbeat` | `error` | fija el test `:190` |

**Por qué el default `False` es imprescindible:** los 5 tests fijados en `tests/test_stall_watchdog.py:148-192` llaman a la función **sin** `work_delivered`. En particular `test_classify_outcome_nonzero_without_result_is_error` (`:186-192`) asserta que `rc=1, result_ok=False` → `"error"` — que es **exactamente el caso de la ejecución 212**. Ese test **fija el comportamiento defectuoso** y NO se toca: la corrección no vive en la función pura sino en el call-site (`:1788`), que sí pasa `work_delivered` computado desde `output` (en scope desde `:1574`).

**Nota de honestidad sobre K2.** Con F3 y F4 el sistema queda con **un solo motor de razón** (`classify_outcome_reason`) y **un solo traductor a estado** (`outcome_reason_to_status`) para `claude_code_cli`, `codex_cli` y `github_copilot` — **3 de 4 runtimes**. `qa_browser_runner.py:272` queda fuera (D6) porque su `error` es incondicional y no depende de estas señales. **K2 se declara como "4 → 1 en los 3 runtimes de agentes; `qa_browser` documentado como deuda"**, no como un 4→1 absoluto.

En `codex_cli_runner.py`, la cadena inline `:816/:884/:1156` consulta `reconciliar_estado` antes de escribir `error`.

**Gate F3:** `pytest tests/test_stall_watchdog.py -q` → **16 passed, 0 failed** (los 5 tests fijados siguen verdes: el contrato se preservó).

---

### F4 — Paridad de señales en los 4 call-sites (K4)

- `agent_runner.py:1125` — de 2 a 8 kwargs (agrega `work_delivered` desde `result.output`).
- `agent_completion.py:67` — quita la circularidad de `result_ok_seen` y agrega `work_delivered`.
- `codex_cli_runner.py:804` — agrega `result_ok_seen` y `work_delivered`. **Este es el arreglo que desbloquea `dirty_exit_after_work` en codex** (E7).
- `claude_code_cli_runner.py:1801` — agrega `work_delivered` desde `output` (ya en scope desde `:1574`).

**Gate F4:** el censo AST de kwargs de F0.4 pasa de `{2,3,4,5}` a que **los 4 pasen `work_delivered`**.

---

### F5 — La flag, en los 6 lugares

`STACKY_OUTCOME_WORK_EVIDENCE_ENABLED`, default **ON**:
1. `config.py` — `os.getenv(..., "true")` (el default EFECTIVO vive acá).
2. `services/harness_flags.py` — `FlagSpec` (hay 447 hoy, contadas por AST).
3. `services/harness_flags_help.py` — `on_effect` / `off_effect`.
4. `_CATEGORY_KEYS` — categorización obligatoria.
5. Allowlist del panel.
6. `deployment/harness_defaults.env` vía su generador.

**Gate F5:** `pytest tests/test_harness_flags_help.py -q` — **criterio DELTA**: el conteo de fallos no debe crecer respecto del baseline medido en F0 (esa suite tiene rojos ajenos de fábrica). Assert de igualdad del default:
`assert config.STACKY_OUTCOME_WORK_EVIDENCE_ENABLED is True`.

---

### F6 — Huella de regresión

Test que congela los invariantes: G1 (nunca verde automático), el orden de precedencia de los 9 reasons, y que `reconciliar_estado` jamás devuelva `completed` si el actual no lo era.

Los tests nuevos van **todos** en `tests/test_plan254_falso_rojo.py`, que **ya está registrado en los dos ratchets** (F0). No se toca `scripts/run_harness_tests.sh` ni `.ps1`.

---

## 6. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Convertir el falso rojo en falso verde | G1 + `reconciliar_estado` solo `error`→`needs_review`; test de invariante F0.3 |
| R2 | El umbral de 200 chars deja pasar un eco de error como "trabajo" | El resultado es `needs_review` (revisión humana), no `completed`. El costo de un falso positivo es que un humano mire de más |
| R3 | Romper `test_stall_watchdog.py` al tocar `_classify_run_outcome` | D3: envoltorio, contrato intacto; gate F3 lo verifica |
| R4 | Colisión con la sesión paralela | G7: lista explícita de archivos prohibidos |
| R5 | `test_harness_flags_help.py` rojo de fábrica confunde el veredicto | Criterio DELTA contra baseline medido en F0 |

---

## 7. Fuera de alcance (declarado)

- `qa_browser_runner.py:272` — `error` incondicional aun con `rc==0`.
- `agent_runner.py:1037` — `final_status="completed"` hardcodeado divergiendo de `:977` (E9).
- Productores para `reaper_kind` / `preflight_block` (3 reasons inalcanzables).
- Re-clasificación retroactiva de las 44 ejecuciones históricas.
- Todo el frente de idempotencia de `epics/from-brief` (sesión paralela).
