# Plan 254 — Fin del falso ROJO: cierre veraz de las corridas

**Estado:** CRITICADO v2 (`v1 -> v2`)
**Serie:** Robustez desde los logs (253-258). Plan **#2 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales de `Stacky Agents/backend/data/logs/`.

> Stacky tiene una deuda histórica documentada contra el **falso verde** (declarar éxito sin haberlo). La auditoría de logs encontró el problema **inverso y hoy más caro**: el **falso ROJO** — trabajo terminado, publicado y correcto que Stacky marca como `error`, forzando al operador a retrabajar algo que ya estaba hecho.

---

## 0. CHANGELOG v1 → v2

La crítica adversarial verificó **cada símbolo, estado y archivo** del v1 contra el árbol. Cinco anclajes centrales estaban mal y el v1 fue **RECHAZADO**. Correcciones aplicadas:

- **C1 (BLOQUEANTE) — F3 partía de un diagnóstico falso: el drenaje YA EXISTE.** El v1 afirmaba que la secuencia actual era `proc.wait() → _classify_run_outcome()`. **Es falsa.** `claude_code_cli_runner.py:1531-1533` ya hace `for reader in readers: reader.join(timeout=5)` apenas sale del bucle de `proc.wait()`, y `_classify_run_outcome` recién se invoca en `:1830` — ~300 líneas **después**. F3 se reescribió: ya no inventa un drenaje, **instrumenta y endurece el join existente** (que es el que puede vencer).
- **C2 (BLOQUEANTE) — el cableado de F2 apuntaba a archivos que no cierran runs.** **Ningún runner llama a `on_execution_end`.** Los call-sites reales son `agent_runner.py:725/1015/1040/1067`, `services/agent_completion.py:1200` y `api/executions.py:572`. `copilot_bridge.py` **no tiene sitio de cierre** (solo devuelve `BridgeResponse`). El DoD "los 3 runtimes emiten `outcome_reason`, verificable con grep en los 3 archivos" era **inalcanzable y gameable con un comentario**. Reemplazado por el seam real.
- **C3 (BLOQUEANTE) — 2 de los 5 literales de estado no existen, y bloquear `cancelled` era un bug.** El vocabulario real (`services/status_vocabulary.py:11-18`) es `{idle, running, completed, error, cancelled, needs_review}`. `"published"` y `"failed"` **no existen** → el guard traía literales muertos. Y `cancelled` en `_NEVER_DOWNGRADE_TO` **le sacaba al operador la capacidad de cancelar** un run sobre un ticket `completed`: violación directa de human-in-the-loop. Corregido y cubierto con un test de contrato contra el vocabulario.
- **C4 (BLOQUEANTE) — `final_status = current` podía hacer explotar el cierre y saltear los post-hooks.** `set_status` **lanza `ValueError`** si el estado no está en `VALID_STATUSES` (`ticket_status.py:130`). El v1 asignaba `final_status = current` **después** de `_coerce_terminal_status`, sin re-coercionar: un `stacky_status` legado en la columna propagaba la excepción fuera de `on_execution_end` y **`_run_post_hooks` (:279) nunca corría** — justo lo contrario de lo que el v1 prometía. Corregido por construcción (ver C5).
- **C5 (BLOQUEANTE) — reinventaba `get_current_status`, que ya existe, y creaba una carrera.** El helper `_current_stacky_status` del v1 duplicaba `ticket_status.py:170`, y al abrir **su propio `session_scope()`** dejaba la lectura y la escritura en **dos transacciones distintas** (carrera real: el agente sigue vivo y PATCHea entremedio) y **sumaba una transacción al camino caliente**, en colisión frontal con el plan 253 (concurrencia SQLite). **Fix estructural:** el guard se mueve **adentro de `set_status`**, donde `old_status` ya se lee dentro de la misma sesión (`ticket_status.py:136`). Cero queries nuevas, cero carrera, atómico.
- **C6 (BLOQUEANTE) — el guard fabricaba un falso VERDE nuevo.** Si el agente auto-reporta `completed` y después el CLI muere de verdad, el v1 preservaba `completed` y solo lo "auditaba": el estado seguía verde. Nueva **F1-bis**: marca de **cierre sucio pendiente de revisión** (sin cambiar el estado, sin sacar al humano del lazo) + conteo consultable.
- **C15 (IMPORTANTE) — el v1 usaba en `ticket_status.py` dos símbolos que ese archivo no importa, y una API de logger inexistente.** `grep -n "stacky_logger\|import config" services/ticket_status.py` da **0 hits**: el snippet del v1 reventaba con `NameError` en la primera línea del guard. Peor, llamaba `stacky_logger.log_event(level=…, message=…, metadata=…)`, que **no existe**: el objeto real es `logger = _StackyLogger()` (`services/stacky_logger.py:475`) con métodos `warning(source, action, **kwargs)` (`:187`), y el idioma de import de la casa es `from services.stacky_logger import logger as stacky_logger`. Corregido con los imports explícitos y la llamada real. *(Este defecto sobrevivió a la primera pasada de la propia crítica y se cazó verificando el archivo: los anclajes se comprueban de a uno, incluso los propios.)*
- **C7 (IMPORTANTE) — el conteo de flags mentía:** decía "4 flags nuevas" e introducía 5. Ahora son **5, declaradas como 5**, y `CLI_STREAM_DRAIN_ENABLED` se eliminó (no se puede "desactivar" un drenaje que ya existe; el knob real es el timeout).
- **C8 (IMPORTANTE) — la categoría `fiabilidad` NO EXISTE** y declarar el atributo en `config.py` **no** hace aparecer la flag en la UI. La categoría real es **`fiabilidad_ciclo_vida`**. Nueva **F6** con la receta completa de 5 lugares, incluida el alta en `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`), que el v1 no mencionaba y que pone **rojo** `test_default_known_only_for_curated`.
- **C9 (IMPORTANTE) — contradicción interna:** la tabla de riesgos decía que `classify_outcome_reason` "tiene defaults para todo salvo `return_code`", pero la firma escrita **no tenía ni un default**. Firma corregida con defaults reales.
- **C10 (IMPORTANTE) — el ratchet se da de alta en DOS archivos**, no en uno: `scripts/run_harness_tests.sh` **y** `scripts/run_harness_tests.ps1`, con **sintaxis distinta**. El v1 solo nombraba el `.sh`.
- **C11 (IMPORTANTE) — F4 era inejecutable como estaba escrita:** el path `src/**/__tests__/...` con glob no expande en PowerShell y no coincidía con el comando (`src/utils/__tests__/`). Path único y literal.
- **C12 (IMPORTANTE) — la causalidad de E1 no está probada.** El v1 afirmaba la causa; con C1 encima, la hipótesis "clasificó antes de drenar" es la **menos** probable. El plan ahora **declara la incertidumbre** y F3 incluye un test que **discrimina** las hipótesis en vez de asumir una.
- **C13 (IMPORTANTE) — KPI no medible** ("Retrabajo del operador: No medido → 0"). Reemplazado por un KPI que la **F5** hace consultable.
- **C14 (MENOR) — huella de regresión.** Se agrega la firma a `services/error_fingerprints.py`.
- **[ADICIÓN ARQUITECTO]** Nueva **F5 — Reconciliación post-cierre**: chequeo determinista y read-only que compara, para cada run terminado, el estado del ticket contra la evidencia objetiva del run, y **lista las discrepancias**. Convierte "creemos que arreglamos el falso rojo" en un número que el operador mira. No cambia ningún estado por su cuenta.

---

## 1. Objetivo y KPI

Que el desenlace de una corrida refleje **lo que el agente entregó**, no el exit code del proceso que lo hospedó. Concretamente: (a) prohibir que un estado terminal de éxito se **degrade** a `error` a posteriori, (b) endurecer y medir el drenaje del stream antes de clasificar, (c) distinguir en la UI un fallo real de un cierre sucio, y (d) **poder contar** cuántos cierres quedaron inconsistentes.

| KPI | Hoy (medido) | Meta | Cómo se mide (v2) |
|---|---|---|---|
| Tickets revertidos de `completed` → `error` por exit code | **≥ 2 confirmados el 2026-07-25** (patrón sistemático) | **0** | Query de `TicketStatusEvent` con `old_status='completed' AND new_status='error'` |
| Joins de lectores que **vencen** el timeout antes de clasificar | No medido (el join existe con `timeout=5` fijo) | **Visible y acotado** | Contador `drain_timed_out` en metadata (F3) |
| `claude code cli exited with code 1` que terminan en ticket `error` habiendo trabajo entregado | ~35 candidatos en 8 días | **0** | Panel de reconciliación (F5) |
| Desenlaces con causa clasificada y visible al operador | No existe la categoría | **100 %** con `outcome_reason` explícito | F2 + F4 |
| ~~Retrabajo del operador por falso rojo~~ **[C13 — reemplazado]** | ~~No medido~~ | — | — |
| **Discrepancias estado-vs-evidencia** (KPI nuevo, sí medible) | Desconocido (no hay chequeo) | **Tendencia a 0, visible** | Endpoint de reconciliación (**F5**) |

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

Se leen **dos defectos probados** y **una anomalía sin causa confirmada**:

1. **PROBADO — Degradación de un terminal de éxito.** El ticket 673 estaba en `'completed'` y Stacky lo puso en `'error'`. El estado `completed` no lo había puesto el runner: lo había puesto el propio agente vía `PATCH /api/tickets/by-ado/{id}/stacky-status`. Stacky **pisó la verdad con el exit code**. Esto **no depende de ninguna hipótesis de timing** y lo arregla F1.
2. **PROBADO — `exec=159` es aún más claro.** A las `11:56:08` reportó `tool_result(ok)` con el build de `Inchost.sln` en Release **exitoso** (`RSModel -> ...\bin\Release\RSModel.dll`). A las `11:57:09`, un minuto después, `exited with code 1` → ticket 672 a `error`. El trabajo estaba hecho **y verificado por compilación**.
3. **NO PROBADO (C12) — eventos del stream después del cierre.** El `exit code 1` de `exec=161` se registró a las `11:56:03` y a las `11:56:06` ese mismo `exec=161` emitió un `tool_use/Bash`. El v1 concluía "el runner clasificó antes de drenar". **Esa conclusión no se sostiene contra el código** (ver E2-bis): el drenaje ocurre ~300 líneas antes de la clasificación. Hipótesis **vivas y no discriminadas**:
   - **H-a:** el `join(timeout=5)` de `:1533` **venció** y los lectores, que son `daemon=True`, siguieron logueando después. Compatible con el código.
   - **H-b:** las líneas son del stream **ya bufferizado y volcado tarde** por el log streamer; el orden del archivo no refleja el orden de ocurrencia.
   - **H-c:** dos procesos/reintentos comparten el mismo `exec id`.
   F3 **no asume ninguna**: agrega la instrumentación que las **discrimina** y endurece el único punto que puede fallar (H-a).

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

La lógica **en sí es razonable**: `result_ok_seen` ya intenta rescatar el caso. El defecto **confirmado** es de **fuentes de verdad**: el clasificador **no consulta el estado actual del ticket**. Si el ticket ya llegó a `completed` por auto-reporte del agente, esa es evidencia de primera mano de trabajo entregado y el clasificador la ignora.

El mensaje de error se arma en `claude_code_cli_runner.py:275-280`:

```python
def _format_cli_error(return_code: int | None, stderr_excerpt: str) -> str:
    base = f"claude code cli exited with code {return_code}"
```

### E2-bis — [C1] La secuencia REAL del runner (verificada, contradice al v1)

`claude_code_cli_runner.py`, orden textual de ejecución:

| Línea | Qué pasa |
|---|---|
| `:1408-1420` | `readers = [Thread(_read_stream, proc.stdout, …), Thread(_read_stream, proc.stderr, …)]` — **dos** threads, ambos `daemon=True` |
| `:1421-1422` | `for reader in readers: reader.start()` |
| `:1432-1529` | bucle `while True:` con `return_code = proc.wait(timeout=5)` y las salidas por runaway / cap de sesión / one-shot / stall watchdog |
| `:1531` | `heartbeat_stop.set()` |
| `:1532-1533` | **`for reader in readers: reader.join(timeout=5)`** ← **el drenaje ya existe** |
| `:1830` | `_outcome_kind = _classify_run_outcome(...)` ← **~300 líneas después** |

⇒ **No hay que crear un drenaje.** Hay que **medir y endurecer el que existe**, que es el único punto donde el sistema puede perder cola: `join(timeout=5)` con un valor **hardcodeado** y **sin detección de vencimiento**.

### E2-ter — [C2] Quién cierra realmente un run (verificado)

Call-sites reales de `ticket_status.on_execution_end` (fuera de `tests/`):

| Archivo:línea | Rol |
|---|---|
| `services/claude_code_cli_runner.py:679, 1767, 1856, 1963, 2031, 2087, 3028, 3062` | **8 sitios** — el runner de Claude Code SÍ cierra sus runs |
| `services/codex_cli_runner.py:358, 764, 797, 887, 1052, 1103, 1158, 1832` | **8 sitios** — ídem Codex |
| `agent_runner.py:725` | cierre genérico |
| `agent_runner.py:1015` | **Copilot** — `final_status="completed"` hardcodeado |
| `agent_runner.py:1040` | **Copilot** — `final_status="cancelled"` |
| `agent_runner.py:1067` | **Copilot** — `final_status="error"` |
| `services/agent_completion.py:1200` | camino de completion |
| `services/agent_completion_internal.py:183` | completion interno |
| `api/executions.py:572` | **cancelación explícita del operador** |
| `services/manifest_watcher.py:293`, `services/pipeline_orchestrator.py:223`, `services/qa_browser_runner.py:180, 205` | otros cierres |
| `scripts/rescue_execution.py:497` | rescate manual |

**Lectura correcta (corregida contra el árbol):** los **dos runners CLI sí llaman** a `on_execution_end` — 16 sitios entre ambos —, así que F2 debe cablearse **también ahí**, no solo en `agent_runner.py`. Lo que NO existe es un sitio de cierre en **`copilot_bridge.py`**: sus cinco `return` son `BridgeResponse` (`:339`, `:560`, `:602`, `:809`, `:1009`) y el archivo **no menciona `final_status` ni una sola vez** (`grep -c final_status copilot_bridge.py` = **0**). El dueño del desenlace de Copilot es `agent_runner.py:1015/1040/1067`.

> **Corrección de la v2 (verificada por el orquestador):** una versión previa de esta tabla afirmaba que *"ninguno de los tres runners llama a `on_execution_end`"*. Es **falso** para los dos runners CLI y sería un error caro: un implementador que lo creyera cablearía solo `agent_runner.py` y dejaría los 16 call-sites reales sin `outcome_reason`. El único enunciado que se sostiene es el de `copilot_bridge.py`.

### E3 — Cero guard anti-degradación en el chokepoint de cierre

`Stacky Agents/backend/services/ticket_status.py:231` — `on_execution_end(...)` es **el** chokepoint de "un agente terminó". Su cuerpo, líneas 268-285:

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
_run_post_hooks(
    ticket_id=ticket_id,
    execution_id=execution_id,
    final_status=final_status,
    agent_type=agent_type,
    error=error,
)
```

**No hay ni un chequeo** de qué estado tenía el ticket antes. El único guard parecido del archivo es un `"reason": "Last execution was already terminal"` en `ticket_status.py:395`, que pertenece a otro flujo y **no** protege este path.

### E3-bis — [C3/C4/C5] El sustrato real de estados y de `set_status` (verificado)

**Vocabulario único** — `services/status_vocabulary.py:11-18`:

```python
TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "needs_review"})
NON_TERMINAL_TICKET_STATUSES = frozenset({"idle", "running"})
VALID_TICKET_STATUSES = NON_TERMINAL_TICKET_STATUSES | TERMINAL_STATUSES
```

`ticket_status.py:37` hace `VALID_STATUSES = VALID_TICKET_STATUSES`. Por lo tanto:

- **`"published"` NO es un estado de ticket.** El `_SUCCESS_TERMINALS` del v1 traía un literal muerto.
- **`"failed"` NO es un estado de ticket.** El `_NEVER_DOWNGRADE_TO` del v1 traía otro literal muerto.
- **`"cancelled"` SÍ existe** y lo escribe `api/executions.py:572` cuando **el operador cancela**. Bloquearlo era quitarle al operador el control de su propia corrida.

**`set_status` lanza y ya lee el estado previo dentro de la transacción** — `ticket_status.py:113-170`:

```python
if new_status not in VALID_STATUSES:
    raise ValueError(f"Estado inválido: '{new_status}'. Válidos: {sorted(VALID_STATUSES)}")

with session_scope() as session:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        logger.warning("set_status: ticket_id=%d no encontrado — ignorado", ticket_id)
        return None
    old_status = getattr(ticket, "stacky_status", None)      # ← YA se lee acá, en la misma sesión
    ...
    ticket.stacky_status = new_status
```

Dos consecuencias que reescriben F1:

1. El `raise ValueError` explica **C4**: cualquier asignación de un estado no válido **aborta `on_execution_end` y saltea `_run_post_hooks`**.
2. `old_status` **ya está leído dentro del `session_scope`** de la escritura. Poner el guard **acá** elimina la carrera de **C5** y la query extra, sin tocar el camino caliente que el plan 253 está protegiendo. Además `get_current_status` **ya existe** en `ticket_status.py:170` — no hay que crear `_current_stacky_status`.

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

- **Human-in-the-loop:** este plan **nunca** convierte un rojo en verde por su cuenta, y **nunca** le saca al operador una acción que hoy tiene. En particular, **cancelar siempre gana** (C3): si el operador cancela, el guard no se interpone. Cuando la evidencia es ambigua, el desenlace es `needs_review` — estado que **ya existe** en `services/status_vocabulary.py:11` — y decide el humano.
- **No degradar la protección anti-falso-verde:** el guard es **asimétrico por diseño**. Prohíbe `completed → error`; **no** prohíbe `error → completed`, ni `completed → needs_review`, ni `completed → cancelled`. Si el agente no entregó nada, el rojo se mantiene rojo. Y todo `completed` preservado sobre un cierre sucio queda **marcado como pendiente de revisión** (F1-bis) y **contado** (F5).
- **Paridad de 3 runtimes:** F1, F1-bis y F5 viven en el chokepoint compartido `ticket_status`, así que los tres quedan cubiertos por igual. F2 se cablea en el seam **real** (`agent_completion.py` + `agent_runner.py`), no en `copilot_bridge.py`, que no cierra runs (C2). F3 aplica solo a los runners con stream de proceso, con **fallback declarado** para Copilot.
- **Mono-operador sin auth:** nada de permisos ni roles.
- **Cero trabajo extra al operador:** F1-F3 y F5 son invisibles salvo cuando hay algo que mirar. F4 solo agrega información a una pantalla que ya existe.
- **Backward-compatible:** el parámetro nuevo de `set_status` nace con default que **preserva el comportamiento actual**; ningún call-site existente cambia de conducta.
- **Flags nuevas default ON** — ninguna cae en las 4 excepciones duras. Prefijo `STACKY_` como el resto de la casa.
- **Toda flag configurable desde la UI**, con la receta completa de 5 lugares (F6), no solo el atributo en `config.py`.

---

## 4. Fases

### F0 — Tests que reproducen el falso rojo (rojo primero)

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan254_falso_rojo.py`

**Registrar en LOS DOS ratchets** (C10) — sintaxis distinta en cada uno:
- `Stacky Agents/backend/scripts/run_harness_tests.sh` → línea sin comillas, dentro de `HARNESS_TEST_FILES`.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` → línea **con comillas y coma**: `  "tests/test_plan254_falso_rojo.py",`
- **No** agregar a `tests/harness_ratchet_allowlist.txt` (esa lista es para lo que queda deliberadamente fuera).

**Casos exactos:**

1. `test_on_execution_end_no_degrada_completed_a_error` — ticket en `completed`; llamar `on_execution_end(final_status="error", error="claude code cli exited with code 1")`. Asserta que el ticket **sigue** en `completed`. **Hoy falla** (queda en `error`).
2. `test_on_execution_end_si_permite_error_desde_running` — ticket en `running` → `error` **sí** se aplica. Blinda que el guard no sea un cheque en blanco.
3. `test_on_execution_end_permite_completed_a_needs_review` — la degradación *a revisión humana* sí está permitida.
4. `test_on_execution_end_permite_completed_a_cancelled` — **(C3)** el operador cancela un ticket ya `completed` y la cancelación **se aplica**. Este test es el que impide que el guard le saque control al humano.
5. `test_on_execution_end_registra_outcome_reason` — el `metadata` del cambio de estado incluye la clave nueva `outcome_reason` con uno de los valores de `OUTCOME_REASONS` (F2).
6. `test_degradacion_bloqueada_se_audita` — el intento bloqueado deja un `SystemLog` de nivel `warning` con el estado que se quiso escribir. **Un guard silencioso sería un falso verde nuevo.**
7. `test_degradacion_bloqueada_corre_los_post_hooks` — **(C4)** registrar un post-hook espía con `ticket_status.register_post_hook`, disparar una degradación bloqueada y assertar que el hook **corrió** y recibió `final_status="completed"` (el efectivo, no el pedido). Este test es el que atrapa la regresión de sync con ADO.
8. `test_guard_solo_usa_estados_del_vocabulario` — **(C3)** test de contrato: `_SUCCESS_TERMINALS | _NEVER_DOWNGRADE_TO ⊆ status_vocabulary.VALID_TICKET_STATUSES`. Sin esto, un literal inventado deja el guard **inerte** sin que nadie se entere.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan254_falso_rojo.py -v
```

**Criterio binario:** los 8 tests existen; **1, 5, 6, 7 y 8 fallan** antes de F1; **2, 3 y 4 pasan ya** (describen el comportamiento a preservar — si alguno de esos tres falla antes de tocar nada, el diagnóstico está mal y hay que frenar).

**Flag:** ninguna. **Trabajo del operador: ninguno.**

---

### F1 — Guard anti-degradación, ATÓMICO, dentro de `set_status`

**Objetivo:** que ningún desenlace posterior pueda pisar un terminal de éxito ya alcanzado, **sin** una query extra y **sin** carrera (C5).

**Decisión de diseño (cambio respecto del v1):** el guard **no** va en `on_execution_end` leyendo con un helper nuevo. Va **adentro de `set_status`**, que ya lee `old_status` dentro del mismo `session_scope` de la escritura (`ticket_status.py:136`). Esto da atomicidad gratis, cero transacciones nuevas en el camino caliente (respeta al plan 253) y reutiliza lo que existe.

**Archivo a editar:** `Stacky Agents/backend/services/ticket_status.py`.

**Imports que HAY QUE AGREGAR (verificado: `ticket_status.py` hoy NO importa ninguno de los dos):**

```python
import config                                            # se lee config.config.<FLAG>
from services.stacky_logger import logger as stacky_logger   # idioma real de la casa
```

> Verificado contra el árbol: `grep -n "stacky_logger\|import config" services/ticket_status.py` devuelve **0 hits** hoy. Sin estos dos imports, el guard revienta con `NameError`. `ticket_status.py` ya importa `db`, que a su vez importa `config`, así que **no hay ciclo**.
>
> **API real del logger (no inventar):** el objeto expuesto es `logger = _StackyLogger()` (`services/stacky_logger.py:475`) y sus métodos son `debug/info/warning/error/critical(source: str, action: str, **kwargs)` (`:181-193`). **NO existe `log_event(...)`.**

**Símbolos nuevos exactos (módulo-level, junto a `VALID_STATUSES` en `:37`):**

```python
from services.status_vocabulary import VALID_TICKET_STATUSES  # ya importado en :35

# Plan 254 F1 — estados REALES del vocabulario (status_vocabulary.py:11-18).
# NO existen "published" ni "failed": no inventar literales, el guard quedaría inerte.
_SUCCESS_TERMINALS = frozenset({"completed"})

# Solo se bloquea la degradación a 'error'.
# 'cancelled' NO se bloquea a propósito: cancelar es una acción del OPERADOR
# (api/executions.py:572) y el guard jamás le saca control al humano.
# 'needs_review' NO se bloquea: escalar a revisión humana no destruye trabajo.
_NEVER_DOWNGRADE_TO = frozenset({"error"})

# Invariante verificado por test_guard_solo_usa_estados_del_vocabulario.
assert (_SUCCESS_TERMINALS | _NEVER_DOWNGRADE_TO) <= VALID_TICKET_STATUSES


def _would_degrade(current: str | None, incoming: str) -> bool:
    """Plan 254 F1 — ¿`incoming` destruiría un terminal de éxito ya alcanzado?

    Asimétrico A PROPÓSITO: bloquea completed→error, y NADA MÁS.
    No bloquea error→completed, ni completed→needs_review, ni completed→cancelled.
    Nunca convierte un rojo en verde.
    """
    if not current:
        return False
    return current in _SUCCESS_TERMINALS and incoming in _NEVER_DOWNGRADE_TO
```

**Cambio en `set_status`** — nuevo parámetro keyword-only con default que **preserva el comportamiento de hoy** (backward-compatible):

```python
def set_status(
    ticket_id: int,
    new_status: str,
    *,
    changed_by: str,
    execution_id: int | None = None,
    agent_type: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
    guard_downgrade: bool = False,      # Plan 254 F1 — solo on_execution_end lo activa
) -> TicketStatusEvent:
```

Dentro del `with session_scope() as session:`, **inmediatamente después** de `old_status = getattr(ticket, "stacky_status", None)` (`:136`):

```python
        # Plan 254 F1 — no destruir un terminal de éxito ya alcanzado.
        # Atómico: `old_status` se leyó en ESTA sesión, no hay carrera con el
        # PATCH del agente ni una transacción extra en el camino caliente.
        if guard_downgrade and _would_degrade(old_status, new_status):
            blocked = {"from": old_status, "to": new_status,
                       "execution_id": execution_id, "reason": reason}
            metadata = {**(metadata or {}), "blocked_downgrade": blocked}
            reason = f"[254-F1] degradación bloqueada {old_status}→{new_status}; {reason or ''}".strip()
            logger.warning(
                "set_status: degradación BLOQUEADA ticket=%s %s→%s (exec=%s) — "
                "el trabajo ya estaba entregado; se registra sin pisar el estado",
                ticket_id, old_status, new_status, execution_id,
            )
            try:
                # API REAL (stacky_logger.py:187): warning(source, action, **kwargs).
                stacky_logger.warning(
                    "ticket_status", "downgrade_blocked",
                    ticket_id=ticket_id, **blocked,
                )
            except Exception:  # noqa: BLE001 — auditar nunca puede romper el cierre
                logger.debug("stacky_logger.warning falló en guard 254", exc_info=True)
            new_status = old_status      # se preserva el estado bueno, YA validado
```

**Por qué esto cierra C4:** `new_status = old_status` toma un valor que **ya está en la columna**, y la validación `new_status not in VALID_STATUSES` ocurrió **antes** de entrar al `session_scope`, sobre el valor entrante. Para blindar el caso de una columna con basura legada, el guard solo se activa si `old_status in _SUCCESS_TERMINALS`, que **por construcción** es un subconjunto del vocabulario. No hay camino por el que se asigne un estado inválido.

**Cambio en `on_execution_end`** (`ticket_status.py:268-285`) — pasar la flag y usar el estado **efectivo** para los post-hooks:

```python
final_status = _coerce_terminal_status(final_status)

event = set_status(
    ticket_id,
    final_status,
    changed_by="system",
    execution_id=execution_id,
    agent_type=agent_type,
    reason=reason,
    metadata=metadata,
    guard_downgrade=config.config.STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED,
)
# Plan 254 F1 — los post-hooks reciben el estado EFECTIVO (puede diferir del
# pedido si el guard preservó un terminal de éxito). `set_status` devuelve None
# si el ticket no existe: en ese caso se cae al pedido, como hoy.
effective_status = getattr(event, "new_status", None) or final_status

_run_post_hooks(
    ticket_id=ticket_id,
    execution_id=execution_id,
    final_status=effective_status,
    agent_type=agent_type,
    error=error,
)
```

> **Import obligatorio:** `import config` y leer **`config.config.<FLAG>`** (la *instancia*), nunca `config.<FLAG>` del módulo — leer el módulo devuelve el default y **mata la rama OFF**, gotcha conocido de la casa.

**Casos borde (todos con test):**
- Ticket sin estado previo (`None`): no hay degradación posible → pasa.
- Ticket inexistente: `set_status` ya devuelve `None` con warning; `effective_status` cae al pedido. Sin cambio de conducta.
- `completed → needs_review`: **permitido** (escalar a humano, no destruir).
- `completed → cancelled`: **permitido** (C3 — soberanía del operador).
- `error → completed`: **permitido** (rescate legítimo).
- `completed → completed`: no-op, como hoy.
- Reaper que cierra un run cuyo ticket ya está `completed`: la degradación se bloquea y queda constancia. Esto cubre las 11 ocurrencias de `reaper[timeout_guardian]` sobre trabajo ya entregado.
- **Los post-hooks siguen corriendo** con el estado efectivo: hay hooks de sincronización con ADO que dependen de eso.

**Tests:** casos 1, 2, 3, 4, 6, 7, 8 de F0 a verde.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_falso_rojo.py -v
```
7 de 8 verdes (el 5 queda para F2). Y: `.venv\Scripts\python.exe -m pytest tests/test_ticket_status.py -v` sin regresiones (validar **por archivo**).

**Flag:** `STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED`, **default ON**. Ninguna excepción dura: no bypasea revisión humana (al contrario: preserva lo que el agente reportó, **audita** el bloqueo y lo **marca** para revisión), no es destructiva, sin prerequisito nuevo, no reduce seguridad.
**Alta en UI:** ver **F6** (no alcanza con el atributo en `config.py`).

**Impacto por runtime:** los 3 pasan por `ticket_status.set_status` → cubiertos con un solo cambio. Fallback: con la flag OFF, `guard_downgrade=False` y el comportamiento es el de hoy, byte por byte.
**Trabajo del operador: ninguno.**

---

### F1-bis — [C6] Marca de cierre sucio: que el verde preservado no sea una mentira

**El riesgo #1 del plan, resuelto con un mecanismo, no con una fila en una tabla.**

**El problema:** el agente auto-reporta `completed` vía `PATCH /api/tickets/by-ado/{id}/stacky-status` **antes** de terminar. Si después el CLI muere de verdad (build roto, crash), F1 preserva `completed` y el operador nunca se entera. El v1 lo "mitigaba" auditando — pero **el estado seguía verde**. Eso es cambiar un falso rojo por un falso verde, que es exactamente la deuda histórica que este repo combate.

**El fix (sin sacar al humano del lazo y sin cambiar ningún estado):** cuando F1 bloquea una degradación, el evento se sella con una marca explícita de **cierre sucio pendiente de revisión**. El estado sigue siendo `completed` — Stacky **no** decide por el operador — pero el run queda **marcado y contable**, y F5 lo lista.

**Símbolo nuevo exacto** (en el mismo bloque del guard de F1, dentro de `blocked`):

```python
            blocked = {
                "from": old_status, "to": new_status,
                "execution_id": execution_id, "reason": reason,
                # Plan 254 F1-bis — el verde preservado NO es un verde limpio.
                "pending_review": True,
                "kind": "dirty_close_preserved_success",
            }
```

**Regla de honestidad, no negociable:** un `completed` con `blocked_downgrade.pending_review == True` **no puede** presentarse en la UI como un éxito limpio. F4 lo renderiza con el badge "Cierre sucio, estado preservado" y F5 lo cuenta como discrepancia hasta que el operador lo mire. Si esta marca no se muestra, **el plan empeora el sistema** — por eso el test 3 de F4 y el criterio de F5 son bloqueantes, no cosméticos.

**Por qué no degradar automáticamente a `needs_review`:** porque el ticket llegó a `completed` por una acción deliberada del agente que el operador puede haber visto y aceptado. Bajarlo por su cuenta sería Stacky decidiendo. Se marca, se muestra, se cuenta — y decide el humano.

**Tests:** agregar a `tests/test_plan254_falso_rojo.py`:
- `test_bloqueo_sella_pending_review` — tras una degradación bloqueada, el `metadata_json` del `TicketStatusEvent` contiene `blocked_downgrade.pending_review is True` y `kind == "dirty_close_preserved_success"`.

**Criterio binario:** el test pasa, y `grep -c "pending_review" services/ticket_status.py` ≥ 1.

**Flag:** ninguna propia (viaja con `STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED`).
**Trabajo del operador: ninguno** hasta que haya algo real que revisar.

---

### F2 — Taxonomía de desenlaces: `outcome_reason`

**Objetivo:** que el operador vea **por qué** falló, no solo que falló. Seis causas distintas no pueden verse iguales.

**Archivo a crear:** `Stacky Agents/backend/services/run_outcome.py` — módulo **puro** (sin DB, sin red, sin imports de `db`/`models`), testeable solo.

**Símbolos nuevos exactos** — firma con defaults reales (C9 corregido):

```python
from __future__ import annotations

OUTCOME_REASONS = (
    "clean_exit",             # rc == 0
    "dirty_exit_after_work",  # rc != 0 PERO hubo result ok / ticket ya terminal
    "quota_exhausted",        # "session limit", "rate limit", "quota"
    "stall_after_work",       # watchdog disparó con result ok previo
    "stall_no_work",          # watchdog disparó sin nada entregado  → fallo real
    "preflight_blocked",      # G0.1 gate: repo_missing, etc.
    "reaper_timeout",         # timeout_guardian
    "reaper_heartbeat",       # heartbeat_stale
    "cli_failure",            # rc != 0 sin evidencia de trabajo → fallo real
)

_QUOTA_MARKERS = ("session limit", "rate limit", "quota", "usage limit")


def classify_outcome_reason(
    *,
    return_code: int | None,
    result_ok_seen: bool = False,
    stall_fired: bool = False,
    stderr_excerpt: str = "",
    last_result_text: str = "",
    ticket_already_terminal: bool = False,
    reaper_kind: str | None = None,
    preflight_block: str | None = None,
) -> str:
    """Devuelve exactamente uno de OUTCOME_REASONS. Puro y determinístico.

    Todo parámetro salvo `return_code` tiene default, para que un call-site que
    no puede computar una entrada NO rompa (C9). Nunca devuelve None.
    """


def is_operator_actionable(reason: str) -> bool:
    """True si el operador puede hacer algo distinto de reintentar.
    quota_exhausted → False (esperar). cli_failure → True (mirar el error).
    Un `reason` desconocido devuelve True (mejor molestar que ocultar)."""


def outcome_reason_to_status(reason: str) -> str:
    """Mapa reason → estado terminal: 'completed' | 'needs_review' | 'error'.
    Solo devuelve estados de status_vocabulary.VALID_TICKET_STATUSES.
    dirty_exit_after_work y stall_after_work → 'needs_review', NUNCA 'completed'
    automático: el trabajo existe pero el cierre fue sucio, y eso lo mira un humano.
    """
```

**Orden de precedencia obligatorio** (sin esto, dos reglas pueden matchear y el resultado es ambiguo para un modelo menor). Evaluar **en este orden y devolver en el primer match**:

1. `preflight_block` no vacío → `preflight_blocked`
2. `reaper_kind == "timeout_guardian"` → `reaper_timeout`
3. `reaper_kind` no vacío (cualquier otro, incl. `manual`/`heartbeat_stale`) → `reaper_heartbeat`
4. algún marcador de `_QUOTA_MARKERS` en `stderr_excerpt.lower()` o `last_result_text.lower()` → `quota_exhausted`
5. `stall_fired and (result_ok_seen or ticket_already_terminal)` → `stall_after_work`
6. `stall_fired` → `stall_no_work`
7. `return_code == 0` → `clean_exit`
8. `result_ok_seen or ticket_already_terminal` → `dirty_exit_after_work`
9. resto → `cli_failure`

**Regla clave de diseño (esto es lo que impide crear un falso verde nuevo):** `dirty_exit_after_work` mapea a **`needs_review`**, no a `completed`. Stacky no declara éxito por su cuenta; le dice al operador *"hay trabajo entregado y el proceso cerró sucio, revisalo"*. Combinado con F1, si el ticket **ya estaba** `completed`, el guard preserva ese `completed` y lo marca con `pending_review` (F1-bis).

**Cableado — [C2] en el seam REAL, no en los runners:**

El v1 mandaba cablear `copilot_bridge.py`, que **no cierra runs**. El cableado correcto:

| Archivo | Dónde | Qué |
|---|---|---|
| `services/claude_code_cli_runner.py` | junto a `_classify_run_outcome` (`:1830`), con `return_code`, `_result_ok_seen[0]`, `_stall_fired[0]`, `stderr_excerpt` | computa el `reason` y lo mete en el dict de metadata del run |
| `services/codex_cli_runner.py` | en el bloque de cierre, junto a `return_code` (`:661`) y a los `final_status=` de `:766`, `:799`, `:889`, `:977-980` | ídem |
| **`agent_runner.py`** (**no** `copilot_bridge.py`) | en los 3 `on_execution_end` de Copilot (`:1015`, `:1040`, `:1067`) | Copilot no tiene stream ni `return_code`: se llama con `return_code=0` en el camino `completed` y `return_code=1` en el `except` → `clean_exit` / `cli_failure`. **Fallback explícito y suficiente**, sin inventar telemetría que el bridge no produce |
| `services/agent_completion.py:1200` | el `ts.on_execution_end(...)` del camino de completion | pasa el `reason` en `metadata_override` |

**El `reason` viaja en `metadata_override` de `on_execution_end`** (parámetro que **ya existe** en la firma, `ticket_status.py:231`), y de ahí cae en el `metadata` del `TicketStatusEvent`, que ya se persiste como `metadata_json` (`ticket_status.py:154`). **No hace falta ninguna columna nueva.**

**Tests:** `Stacky Agents/backend/tests/test_plan254_outcome_reason.py` (alta en **los dos** ratchets, C10):
- `test_clean_exit` (rc=0)
- `test_quota_exhausted_desde_stderr` — con `"You've hit your session limit"` → `quota_exhausted`. Usar el string **exacto del log del 07-18**.
- `test_dirty_exit_after_work_mapea_a_needs_review` — **no** a `completed`.
- `test_stall_no_work_mapea_a_error`
- `test_preflight_blocked_desde_repo_missing`
- `test_reaper_timeout_y_heartbeat_son_distintos`
- `test_cli_failure_es_actionable_y_quota_no`
- `test_precedencia_preflight_gana_a_reaper_y_a_quota` — **(nuevo)** con `preflight_block` **y** `reaper_kind` **y** marcador de cuota a la vez, el resultado es `preflight_blocked`. Sin este test, el orden de las reglas queda librado al implementador.
- `test_toda_combinacion_devuelve_un_reason_valido` — grilla exhaustiva de las 8 entradas; asserta que el resultado siempre está en `OUTCOME_REASONS` (nunca `None` ni string libre).
- `test_outcome_reason_to_status_solo_devuelve_estados_validos` — **(nuevo, C3)** para los 9 reasons, el estado devuelto ∈ `status_vocabulary.VALID_TICKET_STATUSES`. Impide que el mapa devuelva un `"published"` fantasma.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_outcome_reason.py -v
```
10 verdes. Y **grep de cableado real** (reemplaza al grep gameable del v1):
```
grep -c "classify_outcome_reason" services/claude_code_cli_runner.py services/codex_cli_runner.py agent_runner.py
```
≥ 1 en **los tres**. `copilot_bridge.py` **no** se toca y **no** se cuenta: su desenlace lo emite `agent_runner.py`.

**Flag:** `STACKY_RUN_OUTCOME_TAXONOMY_ENABLED`, **default ON**. Sin excepción dura (solo agrega metadata).
**Impacto por runtime:** los 3 emiten `outcome_reason` — Claude y Codex con telemetría de stream completa; Copilot con el fallback `clean_exit`/`cli_failure` declarado arriba. Con la flag OFF, no se agrega la clave y nada más cambia.
**Trabajo del operador: ninguno.**

---

### F3 — [C1/C12] Endurecer y MEDIR el drenaje que ya existe

**Objetivo corregido:** el v1 quería crear un drenaje que **ya existe** (E2-bis). Lo que falta no es drenar: es que el drenaje **tenga un timeout configurable, detecte cuándo vence y deje rastro**. Y de paso, que la anomalía del punto 3 de E1 quede **discriminada** en vez de asumida.

**Archivo a editar:** `Stacky Agents/backend/services/claude_code_cli_runner.py`, **exactamente** en `:1532-1533`:

```python
        heartbeat_stop.set()
        for reader in readers:
            reader.join(timeout=5)
```

**Cambio exacto (reemplaza esas dos líneas):**

```python
        heartbeat_stop.set()
        # Plan 254 F3 — el join YA drenaba; lo que faltaba era medirlo.
        # `readers` es una LISTA de 2 threads daemon (stdout y stderr, :1408-1420).
        # Si el join vence, los threads siguen vivos y pueden loguear DESPUÉS del
        # cierre: esa es la hipótesis H-a de E1 y acá queda registrada.
        _drain_deadline = _time.monotonic() + config.config.STACKY_CLI_STREAM_DRAIN_TIMEOUT_S
        _drain_timed_out = False
        for reader in readers:
            _remaining = max(0.0, _drain_deadline - _time.monotonic())
            reader.join(timeout=_remaining)
            if reader.is_alive():
                _drain_timed_out = True
        if _drain_timed_out:
            log("warn",
                f"254-F3 drenaje del stream VENCIÓ tras "
                f"{config.config.STACKY_CLI_STREAM_DRAIN_TIMEOUT_S}s — "
                f"puede haber eventos leídos después de clasificar el desenlace")
```

`_drain_timed_out` se propaga al metadata del run como `"drain_timed_out": True` junto al `outcome_reason` de F2.

**Notas de implementación que un modelo menor necesita:**
- `_time` ya está importado como `import time as _time` en `:1427`. **No** re-importar.
- **No** crear `_drain_stream_tail(reader_thread, ...)`: no existe un `reader_thread` singular. La variable es `readers` (lista de 2).
- El deadline es **compartido** entre los dos joins (no 15 s por thread): el techo total del cierre no cambia de orden de magnitud.
- `_classify_run_outcome` ya corre después (`:1830`). **No hay que reordenar nada** — el v1 se equivocaba.

**Símbolo nuevo en `config.py`** (idioma real de la casa, sin `_env_bool`, que **no existe** en este repo):

```python
    STACKY_CLI_STREAM_DRAIN_TIMEOUT_S: float = float(
        os.getenv("STACKY_CLI_STREAM_DRAIN_TIMEOUT_S", "15")
    )
```

15 s (antes 5 fijos) cubre con margen los 3 s observados el 07-25 y deja aire para pipes lentos. Es un **techo**, no un costo: con el pipe cerrado el join retorna de inmediato.

**Casos borde:**
- El lector nunca termina (pipe colgado, nietos con el pipe abierto): el deadline corta, `drain_timed_out=True` queda en metadata y los threads —que son `daemon=True`— no bloquean el proceso.
- Eventos leídos durante el drenaje que cambian `result_ok_seen` de `False` a `True`: **es exactamente el caso a arreglar**; `_classify_run_outcome` lee `_result_ok_seen[0]` en `:1830`, después del join, así que ya toma el valor actualizado.
- Cancelación explícita del operador: el camino de cancelación (`api/executions.py:572`) no pasa por este bloque. Sin cambio.

**Tests:** `Stacky Agents/backend/tests/test_plan254_stream_drain.py` (alta en **los dos** ratchets):
- `test_drain_espera_eventos_en_vuelo` — lector fake que emite un `result ok` 0,5 s después de que el proceso murió; asserta que el clasificador lo vio.
- `test_drain_respeta_timeout_y_marca_drain_timed_out` — lector que nunca termina; corta en el timeout configurado y marca `drain_timed_out`.
- `test_drain_deadline_es_compartido_entre_los_dos_readers` — con 2 lectores colgados y `timeout=2`, el bloque completo tarda **~2 s, no ~4** (asserta el techo total).
- `test_result_ok_tardio_evita_el_falso_rojo` — **test de integración del bug real**: reproduce la secuencia del 07-25 (rc=1 + `result ok` a +3 s) y asserta que el desenlace es `dirty_exit_after_work`, no `error`.
- `test_discrimina_h_a_de_h_b` — **(C12)** dos escenarios: (H-a) lector vivo tras vencer el join → `drain_timed_out is True`; (H-b) lector que terminó **antes** del join pero cuyo log se volcó tarde → `drain_timed_out is False`. Asserta que los dos casos son **distinguibles por metadata**. Este test es el que convierte una hipótesis en un dato.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_stream_drain.py -v
```
5 verdes.

**Flag:** `STACKY_CLI_STREAM_DRAIN_TIMEOUT_S` (numérica, default **15**, `min_value=1`, `max_value=120`). **No** hay flag booleana de encendido: el drenaje ya existe y no se puede "apagar" sin regresionar; el knob es el timeout. (Esto corrige el conteo de C7.)
**Impacto por runtime:**
- **Claude Code CLI:** aplica plenamente (es donde se midió).
- **Codex CLI:** mismo patrón de stream (`codex_cli_runner.py:661`); aplicar el mismo tratamiento a su bloque de cierre.
- **GitHub Copilot Pro:** `copilot_bridge.py` es request/response y **no tiene readers ni proceso hijo** (verificado: 5 `return BridgeResponse`, cero `final_status`). **Fallback declarado: F3 no le aplica y no se le agrega nada.** No se degrada: F1, F1-bis, F2, F4 y F5 sí lo cubren, y ahí está el valor.
**Trabajo del operador: ninguno.**

---

### F4 — Que el operador vea la causa

**Objetivo:** exponer el `outcome_reason` de F2 y la marca de F1-bis donde el operador ya mira, sin pantallas nuevas.

**Archivos a editar:**
1. `Stacky Agents/backend/api/executions.py` — incluir `outcome_reason` y `outcome_actionable` en el payload de `get_execution` (`:160`) y `list_executions` (`:29`). Ambos ya serializan desde `metadata_json`, que es donde F2 dejó el dato: **no hace falta columna nueva**.
2. Frontend, panel de ejecución existente (`OutputPanel` / detalle de ejecución) — badge con la causa.
3. `Stacky Agents/frontend/src/utils/outcomeReason.ts` — **módulo puro** con el mapa reason → etiqueta + tono.

> **Por qué un módulo puro y no un test de render (C11):** `@testing-library/react` y `jsdom` **no están instalados** en este repo. Un test de vitest que renderice un componente React **no es ejecutable acá**. Los tests de UI de la casa prueban módulos `.ts` puros. El mapa vive en `outcomeReason.ts` y el componente solo lo consume.

**Etiquetas exactas (español, tono correcto — nada de jerga técnica cruda). Los 9 de `OUTCOME_REASONS`, ni uno más ni uno menos:**

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

**Requisito de honestidad (anti-falso-verde) — bloqueante, no cosmético:** cuando F1 bloqueó una degradación, la UI **debe** mostrarlo — badge **"Cierre sucio, estado preservado"** alimentado por `blocked_downgrade.pending_review` (F1-bis). Si el guard fuera invisible, habríamos cambiado un falso rojo por una mentira silenciosa.

**Tests:** `Stacky Agents/frontend/src/utils/__tests__/plan254OutcomeReason.test.ts` — **path único y literal**, sin glob (C11):
- `mapea los 9 reasons a etiqueta` — los 9 tienen etiqueta y tono; ninguno cae en un default genérico. Asserta también que el mapa **no tiene claves de más** (que su tamaño sea exactamente 9).
- `reason desconocido no rompe la ui` — un reason futuro renderiza el string crudo, no `undefined`.
- `blocked_downgrade con pending_review produce el badge de cierre sucio`

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/utils/__tests__/plan254OutcomeReason.test.ts
```
(Correr **por archivo**: la corrida completa de vitest tiene contaminación cross-file conocida en este repo.)

**Criterio binario:** 3 verdes + `npx tsc --noEmit` sin errores nuevos.

> **Nota de frontend:** si hace falta leer un endpoint que puede responder non-2xx, usar `rawGet`/`rawPost` — `api.get`/`api.post` **lanzan excepción** en non-2xx en este repo.

**Flag:** `STACKY_UI_OUTCOME_REASON_BADGE_ENABLED`, **default ON**, expuesta en el panel de flags (F6). Sin excepción dura.
**Impacto por runtime:** la UI es común a los 3; el badge se alimenta del `outcome_reason` que los 3 emiten (F2). Si faltara, el badge simplemente no se renderiza (sin hueco ni error).
**Trabajo del operador: ninguno** — es información nueva en una pantalla que ya visita.

---

### F5 — [ADICIÓN ARQUITECTO] Reconciliación post-cierre: el falso rojo, medido

**El problema que resuelve:** F1-F4 **creen** haber arreglado el falso rojo. Nada en el sistema lo **prueba**. Sin un número, dentro de dos semanas nadie sabe si el bug volvió por otro camino — y el KPI "retrabajo del operador: 0" del v1 era humo porque no era medible (C13).

**Qué es:** un chequeo **determinista, read-only y consultable** que, para cada run terminado, compara el **estado del ticket** contra la **evidencia objetiva del run**, y lista las **discrepancias**. **No cambia ningún estado.** No decide. Solo cuenta y muestra, para que el operador mire una lista corta en vez de auditar 16 MB de logs.

**Archivo a crear:** `Stacky Agents/backend/services/run_reconciliation.py`.

**Símbolos nuevos exactos:**

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RunEvidence:
    """Los hechos objetivos de un run. Los arma el caller desde la BD;
    la función de veredicto es PURA y se testea sin base."""
    execution_id: int
    ticket_id: int
    ticket_status: str            # stacky_status actual
    return_code: int | None
    result_ok_seen: bool
    outcome_reason: str | None
    self_reported_completed: bool  # el agente PATCHeó stacky-status
    blocked_downgrade: bool        # F1 preservó un terminal de éxito
    drain_timed_out: bool          # F3

@dataclass(frozen=True)
class Discrepancy:
    execution_id: int
    ticket_id: int
    kind: str                     # ∈ DISCREPANCY_KINDS
    detail: str

DISCREPANCY_KINDS = (
    "red_with_delivered_work",    # ticket 'error' pero hubo result ok / rc==0  → EL FALSO ROJO
    "green_with_dirty_close",     # ticket 'completed' con blocked_downgrade    → F1-bis sin revisar
    "green_self_reported_only",   # 'completed' solo por auto-reporte, rc!=0 y sin result ok
    "unclassified_outcome",       # run terminado sin outcome_reason            → F2 no cableada
    "drain_timeout",              # el stream no terminó de drenar              → F3
)

def evaluate(evidence: RunEvidence) -> list[Discrepancy]:
    """PURA. Devuelve 0..n discrepancias para un run. Sin DB, sin red."""

def scan_recent(limit: int = 200) -> list[Discrepancy]:
    """Lee los últimos `limit` runs terminados y aplica `evaluate`.
    READ-ONLY: no escribe una sola fila. Sin efectos secundarios."""
```

**Dónde se ve:** endpoint nuevo `GET /api/diag/run-reconciliation` en `Stacky Agents/backend/api/diag.py` (módulo que **ya existe** y ya hospeda `metrics`, `health` y `local_diagnostics`). Devuelve `{"total": N, "by_kind": {...}, "items": [...]}`. Se pinta en el panel de diagnóstico existente.

**Por qué respeta los rieles:**
- **Human-in-the-loop:** no cambia estados, no reintenta, no publica. **Lista**. El operador decide qué hacer con cada línea.
- **Cero trabajo extra:** si no hay discrepancias, el panel muestra `0` y no pide nada. Solo aparece trabajo cuando hay algo realmente inconsistente.
- **Sin autonomía proactiva:** es un `GET`. **No corre en un loop ni dispara nada por su cuenta.** Si más adelante se quisiera un barrido periódico, se engancha al `_maintenance_loop` compartido que crea el **plan 253 F4** — **no** se inventa otro loop.
- **Mono-operador:** sin auth, como todo el resto.
- **Paridad de runtimes:** trabaja sobre `AgentExecution` + `TicketStatusEvent`, comunes a los 3.

**Tests:** `Stacky Agents/backend/tests/test_plan254_reconciliation.py` (alta en **los dos** ratchets):
- `test_red_with_delivered_work_se_detecta` — `ticket_status="error"`, `result_ok_seen=True` → 1 discrepancia `red_with_delivered_work`. **Este es el test que prueba que el KPI mide el bug real.**
- `test_run_sano_no_produce_discrepancias` — rc=0, `completed`, `clean_exit` → lista vacía. **Control negativo obligatorio**: sin esto, una función que devuelve siempre una discrepancia pasaría el test anterior.
- `test_green_with_dirty_close_se_detecta` — el caso de F1-bis.
- `test_green_self_reported_only_se_detecta`
- `test_unclassified_outcome_se_detecta` — `outcome_reason=None`.
- `test_evaluate_es_pura_y_no_toca_la_base` — llamar `evaluate` sin `session_scope` activo no lanza.
- `test_scan_recent_es_read_only` — tras `scan_recent`, el conteo de filas de `TicketStatusEvent` y el `stacky_status` de los tickets son **idénticos** a antes. Blinda el riel "no cambia nada".

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan254_reconciliation.py -v
```
7 verdes. Y `GET /api/diag/run-reconciliation` responde `200` con las claves `total`, `by_kind`, `items`.

**Flag:** `STACKY_RUN_RECONCILIATION_ENABLED`, **default ON**. Sin excepción dura: es read-only, no dispara trabajo ni costo por su cuenta (es un `GET` bajo demanda, no un loop), y no bypasea nada.
**Trabajo del operador: ninguno** — un número más en un panel que ya visita, que solo pide atención cuando hay algo roto.

---

### F6 — [C8] Alta REAL de las 5 flags en la UI (los 5 lugares)

**Por qué esta fase existe:** el v1 decía "configurable desde UI, categoría `fiabilidad`". **Las dos mitades estaban mal.** La UI de flags **no se alimenta de `config.py`**: `api/harness_flags.py` lee `FLAG_REGISTRY` de `services/harness_flags.py`. Y **la categoría `fiabilidad` no existe**. Declarar el atributo en `Config` y nada más deja la flag **invisible** para el operador — incumpliendo el riel "toda flag configurable desde la UI".

**Las 5 flags (conteo honesto, C7):**

| Key | Tipo | Default | Categoría (EXISTENTE) | Fase |
|---|---|---|---|---|
| `STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED` | bool | **ON** | `fiabilidad_ciclo_vida` | F1 |
| `STACKY_RUN_OUTCOME_TAXONOMY_ENABLED` | bool | **ON** | `fiabilidad_ciclo_vida` | F2 |
| `STACKY_CLI_STREAM_DRAIN_TIMEOUT_S` | int | **15** (`min_value=1`, `max_value=120`) | `fiabilidad_ciclo_vida` | F3 |
| `STACKY_UI_OUTCOME_REASON_BADGE_ENABLED` | bool | **ON** | `observabilidad_notif` | F4 |
| `STACKY_RUN_RECONCILIATION_ENABLED` | bool | **ON** | `observabilidad_notif` | F5 |

`fiabilidad_ciclo_vida` ("Fiabilidad y ciclo de vida del run — higiene de procesos: reaping, watchdog, validación pending-task, idempotencia, retries, runaway guard, auto-reparación, intake") es la categoría **existente** que describe exactamente este plan. `observabilidad_notif` es la que corresponde a lo que solo se **ve**.

**Los 5 lugares, en orden. Omitir cualquiera deja un test rojo:**

1. **`Stacky Agents/backend/config.py`** — el atributo en la clase `Config`, con el idioma real de la casa (**no existe `_env_bool` en este repo**):
   ```python
   STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED: bool = os.getenv(
       "STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED", "true").lower() in ("1", "true", "yes")
   ```
   Ídem las otras booleanas. La numérica usa `float(os.getenv(...))` / `int(os.getenv(...))`.
   > El default **efectivo** lo fija `config.py`. Y los consumidores leen **`config.config.<FLAG>`** (la instancia), nunca el módulo.
2. **`Stacky Agents/backend/services/harness_flags.py`** — una `FlagSpec` por flag en `FLAG_REGISTRY`, con `key`, `type`, `label`, `description`, `group="global"`, `default`, y `min_value`/`max_value` en la numérica.
3. **`Stacky Agents/backend/services/harness_flags.py`** — agregar cada `key` a `_CATEGORY_KEYS` bajo la categoría de la tabla. **Sin esto el meta-test de categorización se pone rojo** (`otros` debe quedar vacío).
4. **`Stacky Agents/backend/tests/test_harness_flags.py:467`** — agregar las **4 booleanas default ON** a `_CURATED_DEFAULTS_ON`. **Toda `FlagSpec` con `default=True` debe estar ahí** o `test_default_known_only_for_curated` (`:901`) se pone **rojo**. La numérica no va (no es `default=True`).
5. **`Stacky Agents/backend/services/harness_flags_help.py`** — la ayuda de cada flag nueva.

> **`harness_defaults.env`:** **NO editar a mano.** Se regenera con `deployment/export_harness_defaults.py`.

**Tests:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -v
```

**Criterio binario:** `tests/test_harness_flags.py` **verde** (hoy está 56/0 verde: cualquier rojo acá es **de este plan**). `GET /api/harness-flags` devuelve las 5 keys con su categoría, y ninguna cae en `otros`.

> **Aviso de rojo ajeno:** `tests/test_harness_flags_help.py` tiene **4 fallos preexistentes ajenos**. Validá **tu** entrada aparte (`-k "254"`) y no lo tomes como regresión propia.

**Trabajo del operador: ninguno** — las 5 nacen ON y funcionando; la UI es para poder apagarlas, no para tener que encenderlas.

---

### F7 — [C14] Huella de regresión

**Archivo a editar:** `Stacky Agents/backend/services/error_fingerprints.py` — agregar la firma del falso rojo para que, si vuelve, el sistema la reconozca por nombre:

- patrón: `claude code cli exited with code \d+` correlacionado con un `TicketStatusEvent` `completed → error`.
- etiqueta: `falso_rojo_downgrade_por_exit_code` con puntero a este plan.

**Criterio binario:** `grep -c "falso_rojo_downgrade" services/error_fingerprints.py` ≥ 1 y el archivo de tests de fingerprints sigue verde.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **El guard tapa fallos reales (falso verde nuevo)** — el riesgo #1 del plan | **(C6)** Ya no se mitiga solo "auditando". El guard es **asimétrico** (solo `completed → error`); `dirty_exit_after_work` mapea a `needs_review`, **nunca** a `completed` automático; todo bloqueo se sella con `pending_review=True` (**F1-bis**), se **muestra** en la UI (F4, test bloqueante) y se **cuenta** como discrepancia `green_with_dirty_close` (**F5**) hasta que un humano lo mire. |
| **El guard le saca al operador la cancelación** | **(C3)** `cancelled` **no** está en `_NEVER_DOWNGRADE_TO`. Test dedicado `test_on_execution_end_permite_completed_a_cancelled`. |
| **El guard rompe el cierre y saltea los post-hooks** | **(C4)** El guard vive dentro de `set_status` y solo puede asignar un `old_status` que ya está en la columna y es subconjunto del vocabulario. `on_execution_end` usa el estado **efectivo** para `_run_post_hooks`. Test dedicado `test_degradacion_bloqueada_corre_los_post_hooks`. |
| **Carrera entre leer el estado y escribirlo** | **(C5)** Eliminada por construcción: la lectura (`old_status`, `ticket_status.py:136`) y la escritura ocurren en **la misma sesión**. Además no se agrega ninguna transacción al camino caliente que el plan 253 está protegiendo. |
| Un ticket queda `completed` con trabajo a medias porque el agente auto-reportó de más | Es un problema del contrato de auto-reporte, no del guard. El contract validator ya existe (`CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED`) y degrada a `needs_review`. F2 lo respeta, y F5 lo lista como `green_self_reported_only`. |
| El drenaje agrega latencia a cada corrida | El deadline es **compartido** entre los 2 readers y es un **techo**, no un costo: con el pipe cerrado el join retorna de inmediato. Hoy ya se esperan 5 s fijos; el cambio es de 5 → 15 **como máximo**, e instrumentado. |
| **La causa de la anomalía del stream no está probada** | **(C12)** El plan **declara la incertidumbre** (E1 punto 3, hipótesis H-a/H-b/H-c) y `test_discrimina_h_a_de_h_b` produce el dato en vez de asumirlo. F1 —que es donde está el 80 % del valor— **no depende** de ninguna de las hipótesis. |
| `classify_outcome_reason` con 8 parámetros es propenso a error en el call-site | **(C9)** Es **keyword-only** (`*`) y **todos** los parámetros salvo `return_code` **tienen default real en la firma**. Precedencia de reglas explícita y numerada, con test dedicado. `test_toda_combinacion_devuelve_un_reason_valido` recorre la grilla. |
| Copilot Pro no tiene stream ni sitio de cierre | **(C2)** Verificado: `copilot_bridge.py` no menciona `final_status`. Su desenlace lo emite `agent_runner.py:1015/1040/1067` con el fallback `clean_exit`/`cli_failure`. F3 no le aplica y **se declara**; F1, F1-bis, F2, F4 y F5 sí. |
| La flag OFF deja el bug vivo | Los defaults son ON. Las flags son kill-switches, no interruptores de alta. |
| **El plan se "cierra" sin poder demostrar que el bug murió** | **(C13/F5)** La reconciliación da un número consultable. `red_with_delivered_work` es literalmente el contador del falso rojo. |

---

## 6. Fuera de scope

- Rediseñar la máquina de estados de tickets. El plan 216 ya centralizó su configuración y `services/status_vocabulary.py` es la fuente única; acá solo se agrega un guard de degradación.
- Reintento automático de corridas con `quota_exhausted`. Sería autonomía proactiva: viola el riel de human-in-the-loop. Solo se **etiqueta** para que el operador decida.
- Arreglar la causa del exit code 1 del CLI de Claude (es del binario externo, no de Stacky). Este plan hace que Stacky **interprete** bien ese exit code, no que desaparezca.
- **Barrido periódico** de la reconciliación de F5. Si se quisiera, se engancha al **`_maintenance_loop`** que crea el **plan 253 F4** — no se inventa otro loop.
- Confirmación HITL sobre las discrepancias. Si hiciera falta, se reusa `backend/services/confirm_token.py` del **plan 253 F5** — no se reimplementa.
- Concurrencia/locking de SQLite → **plan 253** (dueño de `db.py`).
- Las excepciones tragadas y el resume muerto → **plan 255**.
- El `reaper[test_reaper]` corriendo contra datos reales y los ledgers con fixtures → **plan 258**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Falso verde** | Declarar éxito sin haberlo. Deuda histórica conocida de este repo. |
| **Falso rojo** | Lo inverso: declarar fallo cuando el trabajo se entregó. **Es lo que arregla este plan.** |
| **Cierre sucio** | El agente entregó trabajo pero el proceso terminó con exit ≠ 0. **No** es éxito limpio ni fallo: se marca (`pending_review`) y lo mira un humano. |
| **`on_execution_end`** | Chokepoint único de "un agente terminó" (`services/ticket_status.py:231`). Lo llaman `agent_runner.py`, `agent_completion.py` y `api/executions.py` — **no** los runners. No confundir con `run_on`. |
| **`result_ok_seen`** | Bandera del runner: el agente emitió un evento `result` terminal exitoso en el stream. En `claude_code_cli_runner.py` es `_result_ok_seen[0]`. |
| **`readers`** | La **lista de 2 threads daemon** (stdout y stderr) que leen el stream del CLI (`claude_code_cli_runner.py:1408-1420`). No existe un `reader_thread` singular. |
| **Stall watchdog** | Guardián que mata un run tras N segundos sin eventos del stream (`:1505-1528`). |
| **Reaper** | Barredor que cierra ejecuciones colgadas por timeout o heartbeat viejo. |
| **`needs_review`** | Estado terminal intermedio existente (`services/status_vocabulary.py:11`): hay trabajo, lo mira un humano. **No** es éxito ni fallo. |
| **Drenar el stream** | Terminar de leer los eventos que quedaron en el buffer del pipe después de que el proceso murió. **Ya ocurre** en `:1532-1533`; F3 lo mide y le da timeout configurable. |
| **Reconciliación** | Comparar el estado del ticket contra la evidencia objetiva del run y listar las diferencias, **sin cambiar nada** (F5). |
| **Excepción dura** | Una de las 4 razones para que una flag nazca OFF: bypasea revisión humana, destructiva, prerequisito no garantizado, reduce seguridad. |

---

## 8. Orden de implementación

1. **F0** — 8 tests, con 5 rojos y 3 verdes esperados. Registrar el archivo en **los dos** ratchets (`.sh` y `.ps1`). Si alguno de los 3 que deben pasar falla, **frenar**: el diagnóstico está mal.
2. **F1** — `_would_degrade` + `guard_downgrade` **dentro de `set_status`** + estado efectivo en `_run_post_hooks`. **Mayor retorno por línea de todo el portafolio**: un cambio, los 3 runtimes, sin query nueva y sin carrera.
3. **F1-bis** — sello `pending_review` en el bloqueo. Va inmediatamente después de F1: sin esto, F1 fabrica un falso verde.
4. **F2** — módulo puro `services/run_outcome.py` + sus 10 tests, **antes** de cablearlo.
5. **F2-bis** — cablear el seam **real**: `claude_code_cli_runner.py:1830`, `codex_cli_runner.py` (bloque de cierre), `agent_runner.py:1015/1040/1067` (Copilot) y `agent_completion.py:1200`. **`copilot_bridge.py` no se toca.**
6. **F3** — endurecer el `join` de `:1532-1533` con deadline compartido + `drain_timed_out`. **No** reordenar la clasificación: ya está después.
7. **F6** — alta de las 5 flags en los 5 lugares. **Antes de F4/F5**, porque ambas leen flags.
8. **F4** — payload de `api/executions.py` + `outcomeReason.ts` + badge.
9. **F5** — `services/run_reconciliation.py` + `GET /api/diag/run-reconciliation` + panel.
10. **F7** — huella en `error_fingerprints.py`.
11. **Verificación final (manual, HITL):** correr un ticket real, matar el CLI con exit ≠ 0 después de que el agente publicó, y confirmar que el ticket **queda** en su estado bueno, con badge "Entregó trabajo, cerró sucio" y una línea en la reconciliación.

---

## 9. Definición de Hecho (DoD)

- [ ] Un `on_execution_end(final_status="error")` sobre un ticket `completed` **no** cambia el estado, y deja `SystemLog` de nivel `warning`.
- [ ] `on_execution_end(final_status="error")` sobre un ticket `running` **sí** aplica el error (el guard no es un cheque en blanco).
- [ ] `completed → needs_review` sigue permitido.
- [ ] **`completed → cancelled` sigue permitido** — el operador nunca pierde la cancelación. *(C3)*
- [ ] **Los post-hooks corren igual cuando el guard bloquea**, y reciben el estado **efectivo**. *(C4)*
- [ ] **El guard solo usa estados de `status_vocabulary.VALID_TICKET_STATUSES`** — test de contrato verde. *(C3)*
- [ ] **La lectura del estado previo ocurre en la MISMA sesión que la escritura** — cero queries nuevas en el camino caliente. *(C5)*
- [ ] **Todo `completed` preservado sobre un cierre sucio queda sellado con `pending_review=True` y visible en la UI.** *(C6)*
- [ ] Los 9 `OUTCOME_REASONS` están cubiertos por test y ninguno cae en un default genérico; el mapa de la UI tiene **exactamente 9** entradas.
- [ ] `outcome_reason_to_status` devuelve **solo** estados del vocabulario real.
- [ ] `dirty_exit_after_work` mapea a `needs_review`, **nunca** a `completed`.
- [ ] Los **3 runtimes** tienen su desenlace clasificado: Claude y Codex en su runner, **Copilot en `agent_runner.py`** con fallback declarado. Verificable con `grep -c "classify_outcome_reason"` ≥ 1 en `claude_code_cli_runner.py`, `codex_cli_runner.py` y `agent_runner.py`. *(C2)*
- [ ] **El drenaje existente (`:1532-1533`) tiene timeout configurable, deadline compartido y marca `drain_timed_out`**; el test que discrimina H-a de H-b pasa. *(C1/C12)*
- [ ] La UI muestra la etiqueta de causa y el aviso de degradación bloqueada.
- [ ] **`GET /api/diag/run-reconciliation` responde 200 y `red_with_delivered_work` es un número que el operador puede mirar.** *(C13)*
- [ ] **`scan_recent` no escribe una sola fila** — test read-only verde.
- [ ] Los **4** archivos de test backend nuevos están en `run_harness_tests.sh` **y** en `run_harness_tests.ps1`. *(C10)*
- [ ] Las **5** flags (no 4) se pueden cambiar **desde la UI**, con categoría **existente**, y las 4 booleanas ON están en `_CURATED_DEFAULTS_ON`. *(C7/C8)*
- [ ] `tests/test_harness_flags.py` verde.
- [ ] `npx tsc --noEmit` limpio en el frontend.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**; `test_harness_flags_help.py` tiene 4 rojos **ajenos** preexistentes).
