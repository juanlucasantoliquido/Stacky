# Plan 254 — Fin del falso ROJO: cierre veraz de las corridas

**Estado:** PROPUESTO v1
**Serie:** Robustez desde los logs (253-258). Plan **#2 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/`.

> Stacky tiene una deuda histórica documentada contra el **falso verde** (declarar éxito sin haberlo). La auditoría de logs encontró el problema **inverso y hoy más caro**: el **falso ROJO** — trabajo terminado, publicado y correcto que Stacky marca como `error`, forzando al operador a retrabajar algo que ya estaba hecho.

---

## 1. Objetivo y KPI

Que el desenlace de una corrida refleje **lo que el agente entregó**, no el exit code del proceso que lo hospedó. Concretamente: (a) prohibir que un estado terminal de éxito se **degrade** a `error` a posteriori, (b) drenar el stream hasta el final antes de clasificar el desenlace, y (c) distinguir en la UI un fallo real de un cierre sucio de sesión.

| KPI | Hoy (medido) | Meta |
|---|---|---|
| Tickets revertidos de `completed` → `error` por exit code | **≥ 2 confirmados el 2026-07-25** (patrón sistemático) | **0** |
| Eventos del stream emitidos DESPUÉS de declarar el run terminado | 1 `tool_use` a +3 s (exec=161) | **0** |
| `claude code cli exited with code 1` que terminan en ticket `error` habiendo trabajo entregado | ~35 candidatos en 8 días | **0** |
| Desenlaces con causa clasificada y visible al operador | No existe la categoría | **100 %** con `outcome_reason` explícito |
| Retrabajo del operador por falso rojo | No medido, reportado | **0** |

---

## 2. Evidencia real (anclaje anti-alucinación)

### E1 — La secuencia del falso rojo, literal

Firma agregada sobre los 14 logs:

```
35 ERROR [stacky_agents.claude_code_cli] [exec=N] claude code cli exited with code 1
```

Serie temporal (líneas por archivo de log) — **está vivo**:

| Log | Ocurrencias |
|---|---|
| `stacky-2026-07-18.log` | 11 |
| `stacky-2026-07-19.log` | 1 |
| `stacky-2026-07-20.log` | 4 |
| `stacky-2026-07-21.log` | 10 |
| `stacky-2026-07-22.log` | 4 |
| `stacky-2026-07-23.log` | 2 |
| `stacky-2026-07-25.log` | 2 |
| `stacky-2026-07-26.log` | 1 |

Y ahora la parte grave. Extracto **literal y contiguo** de `stacky-2026-07-25.log`:

```
11:56:01 INFO  [claude_code_cli] [exec=159] tool_use/Bash: {"command": "cd \"C:\\desarrollo\\GIT\\RS\\RSPACIFICO\" && MSBuild.exe \"trunk/Batch/Soluciones/Inchost.sln\" -p:Configuration=Release -t:Rebuild ...
11:56:02 INFO  [claude_code_cli] [exec=161] assistant: Ahora notifico a Stacky (no a ADO) vía el endpoint local para que Stacky publique el comentario y aplique la transición de estado.
11:56:03 ERROR [claude_code_cli] [exec=161] claude code cli exited with code 1
11:56:03 INFO  [stacky.ticket_status] ticket_id=673: 'completed' → 'error' (exec=161, by=system)
11:56:06 INFO  [claude_code_cli] [exec=161] tool_use/Bash: {"command": "powershell ... PATCH http://localhost:5050/api/tickets/by-ado/402/stacky-status ... status = \"completed\" ... target_ado_state = \"Reviewed by Dev\" ...
11:56:08 INFO  [claude_code_cli] [exec=159] tool_result(ok): ...RSModel -> ...\bin\Release\RSModel.dll  (build OK)
11:57:09 ERROR [claude_code_cli] [exec=159] claude code cli exited with code 1
11:57:09 INFO  [stacky.ticket_status] ticket_id=672: 'completed' → 'error' (exec=159, by=system)
```

Se leen **tres defectos independientes** en esas 8 líneas:

1. **Degradación de un terminal de éxito.** El ticket 673 estaba en `'completed'` y Stacky lo puso en `'error'`. El estado `completed` no lo había puesto el runner: lo había puesto el propio agente vía `PATCH /api/tickets/by-ado/{id}/stacky-status`. Stacky **pisó la verdad con el exit code**.
2. **Clasificación con el stream a medio drenar.** El `exit code 1` de `exec=161` se registró a las `11:56:03`, pero a las `11:56:06` — **3 segundos después** — ese mismo `exec=161` emitió un `tool_use/Bash`. El runner clasificó el desenlace **antes** de terminar de leer los eventos que el CLI ya había producido. Si ese `tool_use` (que es justamente el PATCH de "completado") se hubiera leído antes de clasificar, `result_ok_seen` habría sido `True`.
3. **`exec=159` es aún más claro.** A las `11:56:08` reportó `tool_result(ok)` con el build de `Inchost.sln` en Release **exitoso** (`RSModel -> ...\bin\Release\RSModel.dll`). A las `11:57:09`, un minuto después, `exited with code 1` → ticket 672 a `error`. El trabajo estaba hecho **y verificado por compilación**.

### E2 — El clasificador, y por qué el exit code le gana a la evidencia

`Stacky Agents/backend/services/claude_code_cli_runner.py:398-413`:

```python
def _classify_run_outcome(
    *, stall_fired: bool, result_ok_seen: bool, return_code: int | None
) -> str:
    if stall_fired and not result_ok_seen:
        return "failed_stall"
    if return_code == 0 or result_ok_seen:
        return "success"
    return "error"
```

La lógica **en sí es razonable**: `result_ok_seen` ya intenta rescatar el caso. El defecto es de **timing y de fuentes de verdad**:

- `result_ok_seen` se computa desde el stream, que todavía se está drenando cuando se llama (E1, punto 2).
- El clasificador **no consulta el estado actual del ticket**. Si el ticket ya llegó a `completed` por auto-reporte del agente, esa es evidencia de primera mano de trabajo entregado y el clasificador la ignora.

El mensaje de error se arma en `claude_code_cli_runner.py:275-280`:

```python
def _format_cli_error(return_code: int | None, stderr_excerpt: str) -> str:
    base = f"claude code cli exited with code {return_code}"
```

y el `final_status="error"` se propaga desde, entre otros, `claude_code_cli_runner.py:1859`, `:2034`, `:2090`, `:3031`.

### E3 — Cero guard anti-degradación en el chokepoint de cierre

`Stacky Agents/backend/services/ticket_status.py:231` — `on_execution_end(...)` es **el** chokepoint de "un agente terminó". Su cuerpo, líneas 268-278:

```python
final_status = _coerce_terminal_status(final_status)

set_status(
    ticket_id,
    final_status,
    changed_by="system",
    execution_id=execution_id,
    agent_type=agent_type,
    reason=reason,
    metadata=metadata,
)
```

**No hay ni un chequeo** de qué estado tenía el ticket antes. `set_status` (`ticket_status.py:113`) sobreescribe. El único guard parecido del archivo es un `"reason": "Last execution was already terminal"` en `ticket_status.py:395`, que pertenece a otro flujo y **no** protege este path.

### E4 — Los otros desenlaces sucios que hoy son indistinguibles de un fallo real

Firmas agregadas sobre los 14 logs:

```
 8 result(error): You've hit your session limit · resets 5:Nam (America/Buenos_Aires)   [stacky-2026-07-18.log]
 7 G0.1 preflight gate bloqueó run: ticket=N runtime=claude_code_cli check=repo_missing ...
 6 R1.1 stall watchdog: Ns sin eventos del stream — terminando                          [07-18, 07-20, 07-25]
 1 run terminado por inactividad (Ns) — última señal: result
11 reaper[timeout_guardian]: exec_id=N ticket_id=N timed_out after N min
 8 reaper[manual]: exec_id=N ticket_id=N heartbeat_stale (heartbeat stale (Ns))
 4 reaper[test_reaper]: exec_id=N ticket_id=1 timed_out after N min
```

Seis causas radicalmente distintas — cuota de plan agotada, repo ausente, sesión ociosa tras entregar, timeout del reaper, heartbeat viejo, y **un reaper de test corriendo contra datos reales** (`reaper[test_reaper]` con `ticket_id=1`) — colapsan todas al mismo `error` en la UI. El operador no puede distinguir *"me quedé sin cuota"* de *"el código no compila"*, y **son acciones opuestas**.

Nótese `reaper[test_reaper]: exec_id=1 ticket_id=1` (4 ocurrencias): un reaper de prueba dejó huella en el log de la app. Eso se aborda en el **plan 258** (ledgers contaminados con datos de test).

---

## 3. Principios y guardarraíles (obligatorios)

- **Human-in-the-loop:** este plan **nunca** convierte un rojo en verde por su cuenta. Cuando la evidencia es ambigua, el desenlace es `needs_review` — un estado que **ya existe** en `services/agent_completion.py` — y el operador decide. Jamás se auto-completa un ticket que el agente no completó.
- **No degradar la protección anti-falso-verde:** el guard es **asimétrico por diseño**. Prohíbe `completed → error`; **no** prohíbe `error → completed` ni `completed → needs_review`. Si el agente no entregó nada, el rojo se mantiene rojo.
- **Paridad de 3 runtimes:** F1 y F2 son en el chokepoint compartido `ticket_status.on_execution_end`, así que Codex CLI, Claude Code CLI y Copilot Pro quedan cubiertos por igual. F3 (drenaje del stream) tiene call-site propio por runtime, los tres nombrados explícitamente.
- **Mono-operador sin auth:** nada de permisos ni roles.
- **Cero trabajo extra al operador:** F1-F3 son invisibles. F4 solo agrega información a una pantalla que ya existe.
- **Flags nuevas default ON** — ninguna cae en las 4 excepciones duras.
- **Toda flag configurable desde la UI.**

---

## 4. Fases

### F0 — Tests que reproducen el falso rojo (rojo primero)

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan254_falso_rojo.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh`.

**Casos exactos:**

1. `test_on_execution_end_no_degrada_completed_a_error` — ticket en `completed`; llamar `on_execution_end(final_status="error", error="claude code cli exited with code 1")`. Asserta que el ticket **sigue** en `completed`. **Hoy falla** (queda en `error`).
2. `test_on_execution_end_si_permite_error_desde_running` — ticket en `running` → `error` **sí** se aplica. Blinda que el guard no sea un cheque en blanco.
3. `test_on_execution_end_permite_completed_a_needs_review` — la degradación *a revisión humana* sí está permitida.
4. `test_on_execution_end_registra_outcome_reason` — el `metadata` del cambio de estado incluye la clave nueva `outcome_reason` con uno de los valores del enum de F2.
5. `test_classify_outcome_respeta_estado_terminal_del_ticket` — con `return_code=1`, `result_ok_seen=False`, pero ticket ya en `completed`, el clasificador devuelve `"success_dirty_exit"`, no `"error"`. **Hoy falla** (el símbolo no existe).
6. `test_degradacion_bloqueada_se_audita` — el intento bloqueado deja un `SystemLog` de nivel `warning` con el estado que se quiso escribir. **Un guard silencioso sería un falso verde nuevo.**

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan254_falso_rojo.py -v
```

**Criterio binario:** los 6 tests existen; 1, 4, 5 y 6 **fallan** antes de F1; 2 y 3 pueden pasar ya (describen el comportamiento a preservar).

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Guard anti-degradación en el chokepoint

**Objetivo:** que ningún desenlace posterior pueda pisar un terminal de éxito ya alcanzado.

**Archivo a editar:** `Stacky Agents/backend/services/ticket_status.py`, en `on_execution_end` (def en `ticket_status.py:231`), **entre** `_coerce_terminal_status` (`:268`) y `set_status` (`:270`).

**Símbolos nuevos exactos:**

```python
# ticket_status.py — módulo-level
_SUCCESS_TERMINALS = frozenset({"completed", "published"})
_NEVER_DOWNGRADE_TO = frozenset({"error", "failed", "cancelled"})

def _would_degrade(current: str | None, incoming: str) -> bool:
    """Plan 254 F1 — ¿`incoming` destruiría un terminal de éxito ya alcanzado?

    Asimétrico A PROPÓSITO: bloquea éxito→fallo, NO bloquea fallo→éxito ni
    éxito→needs_review. Nunca convierte un rojo en verde.
    """
    if not current:
        return False
    return current in _SUCCESS_TERMINALS and incoming in _NEVER_DOWNGRADE_TO
```

**Cambio en `on_execution_end`:**

```python
final_status = _coerce_terminal_status(final_status)

# Plan 254 F1 — no destruir un terminal de éxito ya alcanzado.
current = _current_stacky_status(ticket_id)          # helper nuevo, lectura simple
if config.TICKET_STATUS_NO_DOWNGRADE_ENABLED and _would_degrade(current, final_status):
    metadata = {**(metadata or {}),
                "blocked_downgrade": {"from": current, "to": final_status,
                                      "error": error, "execution_id": execution_id}}
    logger.warning(
        "on_execution_end: degradación BLOQUEADA ticket=%s %s→%s (exec=%s) — "
        "el trabajo ya estaba entregado; se registra sin pisar el estado",
        ticket_id, current, final_status, execution_id)
    stacky_logger.log_event(level="warning", source="ticket_status",
                            message=f"downgrade bloqueado {current}→{final_status}",
                            metadata=metadata)
    final_status = current            # se preserva el estado bueno
    # Los post-hooks SÍ corren: el ciclo de vida del run terminó igual.
```

**Casos borde (todos con test):**
- Ticket sin estado previo (`None`): no hay degradación posible → pasa.
- `completed → needs_review`: **permitido** (es escalar a humano, no destruir).
- `error → completed`: **permitido** (rescate legítimo).
- `completed → completed`: no-op.
- Reaper que cierra un run cuyo ticket ya está `completed`: la degradación se bloquea, y en el log queda constancia. Esto arregla de una las 11 ocurrencias de `reaper[timeout_guardian]` sobre trabajo ya entregado.
- **Los post-hooks siguen corriendo** (`_run_post_hooks`, `ticket_status.py:279`): la ejecución terminó de verdad, y hay hooks de sincronización con ADO que dependen de eso.

**Tests:** casos 1, 2, 3, 6 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_falso_rojo.py -k "degrada or needs_review or audita" -v
```
4 verdes.

**Flag:** `TICKET_STATUS_NO_DOWNGRADE_ENABLED`, **default ON**. Ninguna excepción dura: no bypasea revisión humana (al contrario: preserva lo que el humano/agente ya reportó y **audita** el bloqueo), no es destructiva, sin prerequisito nuevo, no reduce seguridad.
**Configurable desde UI:** sí, categoría `fiabilidad`.

**Impacto por runtime:** Codex CLI, Claude Code CLI y Copilot Pro pasan **todos** por `on_execution_end` → los 3 quedan cubiertos con un solo cambio. Fallback: con la flag OFF, el comportamiento es el de hoy, byte por byte.
**Trabajo del operador: ninguno.**

---

### F2 — Taxonomía de desenlaces: `outcome_reason`

**Objetivo:** que el operador vea **por qué** falló, no solo que falló. Seis causas distintas no pueden verse iguales.

**Archivo a crear:** `Stacky Agents/backend/services/run_outcome.py` — módulo **puro** (sin DB, sin red), testeable solo.

**Símbolos nuevos exactos:**

```python
OUTCOME_REASONS = (
    "clean_exit",          # rc == 0
    "dirty_exit_after_work",  # rc != 0 PERO hubo result ok / ticket ya terminal
    "quota_exhausted",     # "session limit", "rate limit", "quota"
    "stall_after_work",    # watchdog disparó con result ok previo
    "stall_no_work",       # watchdog disparó sin nada entregado  → fallo real
    "preflight_blocked",   # G0.1 gate: repo_missing, etc.
    "reaper_timeout",      # timeout_guardian
    "reaper_heartbeat",    # heartbeat_stale
    "cli_failure",         # rc != 0 sin evidencia de trabajo → fallo real
)

_QUOTA_MARKERS = ("session limit", "rate limit", "quota", "usage limit")

def classify_outcome_reason(
    *, return_code: int | None, result_ok_seen: bool, stall_fired: bool,
    stderr_excerpt: str, last_result_text: str,
    ticket_already_terminal: bool, reaper_kind: str | None,
    preflight_block: str | None,
) -> str:
    """Devuelve exactamente uno de OUTCOME_REASONS. Puro y determinístico."""

def is_operator_actionable(reason: str) -> bool:
    """True si el operador puede hacer algo distinto de reintentar.
    quota_exhausted → False (esperar). cli_failure → True (mirar el error)."""

def outcome_reason_to_status(reason: str) -> str:
    """Mapa reason → estado terminal: 'completed' | 'needs_review' | 'error'.
    dirty_exit_after_work y stall_after_work → 'needs_review', NUNCA 'completed'
    automático: el trabajo existe pero el cierre fue sucio, y eso lo mira un humano.
    """
```

**Regla clave de diseño (esto es lo que impide crear un falso verde nuevo):** `dirty_exit_after_work` mapea a **`needs_review`**, no a `completed`. Stacky no declara éxito por su cuenta; le dice al operador *"hay trabajo entregado y el proceso cerró sucio, revisalo"*. Combinado con F1, si el ticket **ya estaba** `completed` por auto-reporte del agente, el guard preserva ese `completed` y no lo baja ni a `needs_review`.

**Cableado:** `classify_outcome_reason` se llama en los 3 runtimes y su resultado viaja en `metadata_override` de `on_execution_end`:
- `Stacky Agents/backend/services/claude_code_cli_runner.py` — en los sitios de `final_status=` ya existentes: `:1859`, `:2034`, `:2090`, `:3031`.
- `Stacky Agents/backend/services/codex_cli_runner.py` — sitio equivalente de cierre.
- `Stacky Agents/backend/copilot_bridge.py` — sitio equivalente de cierre.

**Tests:** `Stacky Agents/backend/tests/test_plan254_outcome_reason.py` (agregar al ratchet):
- `test_clean_exit` (rc=0)
- `test_quota_exhausted_desde_stderr` — con `"You've hit your session limit"` → `quota_exhausted`. Usar el string **exacto del log del 07-18**.
- `test_dirty_exit_after_work_mapea_a_needs_review` — **no** a `completed`.
- `test_stall_no_work_mapea_a_error`
- `test_preflight_blocked_desde_repo_missing`
- `test_reaper_timeout_y_heartbeat_son_distintos`
- `test_cli_failure_es_actionable_y_quota_no`
- `test_toda_combinacion_devuelve_un_reason_valido` — grilla exhaustiva de las 8 entradas booleanas/enum; asserta que el resultado siempre está en `OUTCOME_REASONS` (nunca `None` ni string libre).

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_outcome_reason.py -v
```
8 verdes. Y `grep -c "outcome_reason" services/claude_code_cli_runner.py services/codex_cli_runner.py copilot_bridge.py` da ≥ 1 en **los tres**.

**Flag:** `RUN_OUTCOME_TAXONOMY_ENABLED`, **default ON**. Sin excepción dura (solo agrega metadata).
**Impacto por runtime:** los 3 emiten `outcome_reason`. Fallback: si un runtime no puede computar alguna entrada, `classify_outcome_reason` la recibe en su default y devuelve `cli_failure` o `clean_exit` según `return_code` — **nunca** explota ni devuelve `None`.
**Trabajo del operador: ninguno.**

---

### F3 — Drenar el stream antes de clasificar

**Objetivo:** matar la causa raíz del punto 2 de E1: dejar de clasificar mientras todavía hay eventos por leer.

**Archivo a editar:** `Stacky Agents/backend/services/claude_code_cli_runner.py`, en la zona de `proc.wait(...)` (`:1434`, `:1464`, `:1467`, `:1478`, `:1481`, `:1500`, `:1503`, `:1523`, `:1526`) y **antes** de la llamada a `_classify_run_outcome` (`:398`).

**Símbolo nuevo exacto:**

```python
def _drain_stream_tail(reader_thread, *, timeout_s: float) -> int:
    """Plan 254 F3 — espera a que el lector del stream termine de drenar.

    El CLI puede tener eventos en buffer del pipe DESPUÉS de que proc.wait()
    retorna. Clasificar antes de drenarlos produce falsos rojos (result_ok
    llega tarde). Devuelve la cantidad de eventos leídos en la cola.
    """
```

**Cambio de secuencia (esto es el corazón de la fase):**

```
ANTES:  proc.wait() → _classify_run_outcome(...) → on_execution_end(...)
DESPUÉS: proc.wait() → _drain_stream_tail(timeout_s=config.CLI_STREAM_DRAIN_TIMEOUT_S)
                     → _classify_run_outcome(...)   # ahora con result_ok_seen completo
                     → on_execution_end(...)
```

**Símbolo nuevo en `config.py`:** `CLI_STREAM_DRAIN_TIMEOUT_S = float(os.getenv("CLI_STREAM_DRAIN_TIMEOUT_S", "10"))`

Los 10 s cubren con margen los **3 s** observados en el log del 07-25 (11:56:03 → 11:56:06).

**Casos borde:**
- El lector nunca termina (pipe colgado): el timeout corta y se clasifica con lo que haya; se agrega `"drain_timed_out": True` al metadata para que quede rastro.
- Eventos leídos durante el drenaje que cambian `result_ok_seen` de `False` a `True`: **ese es exactamente el caso que se quiere arreglar**; el clasificador debe leer el valor **después** del drenaje, no capturarlo antes.
- Cancelación explícita del operador: no se drena (el operador ya decidió); se clasifica como `cancelled` de una.

**Tests:** `Stacky Agents/backend/tests/test_plan254_stream_drain.py` (agregar al ratchet):
- `test_drain_espera_eventos_en_vuelo` — lector que emite un `result ok` 0,5 s después de que el proceso murió; asserta que el clasificador lo vio.
- `test_drain_respeta_timeout` — lector que nunca termina; corta en `timeout_s` y marca `drain_timed_out`.
- `test_drain_no_corre_en_cancelacion_explicita`
- `test_result_ok_tardio_evita_el_falso_rojo` — **test de integración del bug real**: reproduce la secuencia exacta del 07-25 (rc=1 + `result ok` a +3 s) y asserta que el desenlace es `dirty_exit_after_work`, no `error`.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_stream_drain.py -v
```
4 verdes.

**Flag:** `CLI_STREAM_DRAIN_ENABLED`, **default ON**. Sin excepción dura.
**Impacto por runtime:**
- **Claude Code CLI:** aplica plenamente (es donde se midió el bug).
- **Codex CLI:** mismo patrón de stream → aplica; call-site propio en `services/codex_cli_runner.py`.
- **GitHub Copilot Pro:** el bridge (`copilot_bridge.py`) es request/response, no stream de proceso; **no hay cola que drenar**. Fallback declarado: `_drain_stream_tail` devuelve `0` de inmediato y el flujo sigue igual. No se degrada nada.
**Trabajo del operador: ninguno.**

---

### F4 — Que el operador vea la causa

**Objetivo:** exponer el `outcome_reason` de F2 donde el operador ya mira, sin pantallas nuevas.

**Archivos a editar:**
1. `Stacky Agents/backend/api/executions.py` — incluir `outcome_reason` y `outcome_actionable` en el payload de `get_execution` y `list_executions`.
2. Frontend, panel de ejecución existente (`OutputPanel` / detalle de ejecución) — badge con la causa.
3. `Stacky Agents/frontend/src/utils/` — mapa reason → etiqueta en español + tono.

**Etiquetas exactas (español, tono correcto — nada de jerga técnica cruda):**

| `outcome_reason` | Etiqueta UI | Tono | Acción sugerida |
|---|---|---|---|
| `clean_exit` | "Terminó bien" | éxito | — |
| `dirty_exit_after_work` | "Entregó trabajo, cerró sucio" | atención | "Revisá el resultado: el trabajo está, el proceso cerró mal" |
| `quota_exhausted` | "Se agotó la cuota del plan" | espera | "Reintentá cuando se reponga la cuota" |
| `stall_after_work` | "Quedó ocioso tras entregar" | atención | "Revisá el resultado" |
| `stall_no_work` | "Se colgó sin entregar" | error | "Reintentá" |
| `preflight_blocked` | "Bloqueado antes de arrancar" | error | Mostrar el `check` exacto (p. ej. `repo_missing`) |
| `reaper_timeout` | "Excedió el tiempo máximo" | error | "Reintentá o subí el timeout" |
| `reaper_heartbeat` | "Perdió señal de vida" | error | "Reintentá" |
| `cli_failure` | "Falló el runtime" | error | Mostrar el extracto de stderr |

**Requisito de honestidad (anti-falso-verde):** cuando F1 bloqueó una degradación, la UI **debe** mostrarlo — badge "Cierre sucio, estado preservado" con el `blocked_downgrade` del metadata. Si el guard fuera invisible, habríamos cambiado un falso rojo por una mentira silenciosa.

**Tests:** `Stacky Agents/frontend/src/**/__tests__/planN254OutcomeReason.test.ts`:
- `test_mapea_los_9_reasons_a_etiqueta` — los 9 tienen etiqueta; ninguno cae en un default genérico.
- `test_reason_desconocido_no_rompe_la_ui` — un reason futuro renderiza el string crudo, no `undefined`.
- `test_blocked_downgrade_se_muestra`

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/utils/__tests__/planN254OutcomeReason.test.ts
```
(Correr **por archivo**: la corrida completa de vitest tiene contaminación cross-file conocida en este repo.)

**Criterio binario:** 3 verdes + `npx tsc --noEmit` sin errores nuevos.

**Flag:** `UI_OUTCOME_REASON_BADGE_ENABLED`, **default ON**, expuesta en el panel de flags. Sin excepción dura.
**Impacto por runtime:** la UI es común a los 3; el badge se alimenta del `outcome_reason` que los 3 emiten (F2). Si un runtime no lo emitiera, el badge simplemente no se renderiza (sin hueco ni error).
**Trabajo del operador: ninguno** — es información nueva en una pantalla que ya visita.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **El guard tapa fallos reales (falso verde nuevo)** — el riesgo #1 del plan | El guard es **asimétrico**: solo bloquea éxito→fallo. `dirty_exit_after_work` mapea a `needs_review`, **nunca** a `completed` automático. Todo bloqueo se **audita** en `SystemLog` y se **muestra** en la UI (F4). Hay dos tests dedicados (`test_on_execution_end_si_permite_error_desde_running`, `test_degradacion_bloqueada_se_audita`). |
| Un ticket queda `completed` con trabajo a medias porque el agente auto-reportó de más | Ese es un problema del contrato de auto-reporte, no del guard. El contract validator ya existe (`CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED`, visible en los logs) y degrada a `needs_review`. F2 lo respeta. |
| El drenaje agrega 10 s a cada corrida | Solo espera si el lector **todavía tiene** eventos; con el pipe cerrado retorna de inmediato. El timeout es el techo, no el costo típico. Medir el p50 del drenaje y loguearlo. |
| `classify_outcome_reason` con 8 parámetros es propenso a error en el call-site | Es **keyword-only** (`*`), tiene defaults para todo salvo `return_code`, y el test `test_toda_combinacion_devuelve_un_reason_valido` recorre la grilla completa. |
| Copilot Pro no tiene stream y F3 no le aplica | Fallback explícito y declarado: `_drain_stream_tail` devuelve `0`. F1/F2/F4 sí le aplican, que es donde está el valor. |
| La flag OFF deja el bug vivo | Los 3 defaults son ON. La flag existe solo como kill-switch. |

---

## 6. Fuera de scope

- Rediseñar la máquina de estados de tickets. El plan 216 ya centralizó su configuración; acá solo se agrega un guard de degradación.
- Reintento automático de corridas con `quota_exhausted`. Sería autonomía proactiva: viola el riel de human-in-the-loop. Solo se **etiqueta** para que el operador decida.
- Arreglar la causa del exit code 1 del CLI de Claude (es del binario externo, no de Stacky). Este plan hace que Stacky **interprete** bien ese exit code, no que desaparezca.
- El `reaper[test_reaper]` corriendo contra datos reales → **plan 258**.
- Las excepciones tragadas del backend → **plan 255**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Falso verde** | Declarar éxito sin haberlo. Deuda histórica conocida de este repo. |
| **Falso rojo** | Lo inverso: declarar fallo cuando el trabajo se entregó. **Es lo que arregla este plan.** |
| **`on_execution_end`** | Chokepoint único de "un agente terminó" (`services/ticket_status.py:231`). Cubre los 3 runtimes. No confundir con `run_on`. |
| **`result_ok_seen`** | Bandera del runner: el agente emitió un evento `result` terminal exitoso en el stream. |
| **Stall watchdog** | Guardián que mata un run tras N segundos sin eventos del stream. |
| **Reaper** | Barredor que cierra ejecuciones colgadas por timeout o heartbeat viejo. |
| **`needs_review`** | Estado terminal intermedio existente (`services/agent_completion.py`): hay trabajo, lo mira un humano. **No** es éxito ni fallo. |
| **Drenar el stream** | Terminar de leer los eventos que quedaron en el buffer del pipe después de que el proceso murió. |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — 6 tests, rojos. Registrar el archivo en `HARNESS_TEST_FILES`.
2. **F1** — guard `_would_degrade` + `_current_stacky_status` en `on_execution_end`. **Mayor retorno por línea de todo el portafolio**: un cambio, los 3 runtimes.
3. **F2** — módulo puro `services/run_outcome.py` + sus 8 tests, **antes** de cablearlo. Módulo puro primero, cableado después.
4. **F2-bis** — cablear los 3 runtimes (`claude_code_cli_runner.py`, `codex_cli_runner.py`, `copilot_bridge.py`).
5. **F3** — `_drain_stream_tail` + reordenar la secuencia antes de `_classify_run_outcome`.
6. **F4** — payload de `api/executions.py` + badge y etiquetas en la UI.
7. Exponer las 4 flags nuevas en el panel de flags y en `api/global_config.py`.
8. Verificación final: correr un ticket real, matar el CLI con exit≠0 después de que el agente publicó, y confirmar que el ticket **queda** en su estado bueno con badge "Entregó trabajo, cerró sucio".

---

## 9. Definición de Hecho (DoD)

- [ ] Un `on_execution_end(final_status="error")` sobre un ticket `completed` **no** cambia el estado, y deja `SystemLog` de nivel `warning`.
- [ ] `on_execution_end(final_status="error")` sobre un ticket `running` **sí** aplica el error (el guard no es un cheque en blanco).
- [ ] `completed → needs_review` sigue permitido.
- [ ] Los 9 `OUTCOME_REASONS` están cubiertos por test y ninguno cae en un default genérico.
- [ ] `dirty_exit_after_work` mapea a `needs_review`, **nunca** a `completed`.
- [ ] Los **3** runtimes emiten `outcome_reason` (verificable con grep en los 3 archivos).
- [ ] El clasificador corre **después** del drenaje del stream; el test que reproduce la secuencia del 2026-07-25 pasa.
- [ ] La UI muestra la etiqueta de causa y el aviso de degradación bloqueada.
- [ ] Los 3 archivos de test backend nuevos están en `HARNESS_TEST_FILES`.
- [ ] Las 4 flags nuevas se pueden cambiar **desde la UI**.
- [ ] `npx tsc --noEmit` limpio en el frontend.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**).
