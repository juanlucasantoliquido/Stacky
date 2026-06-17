# 28 — Plan Mejoras de Alto Impacto Invisibles: que ningún run quede zombie, pierda su trabajo, ni falle en silencio

**Fecha:** 2026-06-14
**Estado:** IMPLEMENTADO COMPLETO (2026-06-14) — 52 tests verdes (8 archivos)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 propuestos), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (implementado salvo UI U2.1), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto), `docs/26_PLAN_MEMORIA_CONFIGURABLE_Y_DIRECTIVAS.md` (**implementado completo** al 2026-06-14: backend verde + frontend tsc limpio) y `docs/27_PLAN_MEJORAS_INVISIBLES_MOTOR.md` (ver relación abajo).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia `file:line`, diseño con archivos exactos, criterios de aceptación, tests TDD, salvaguarda de calidad y complejidad.

**Tesis (innegociable):** los docs 22-27 hicieron que el motor **piense mejor** (mejor contexto, routing por dificultad, dedup de tokens, caché de contenido). Este plan ataca el problema de al lado, que el 27 NO toca: que el motor **no se ahogue ni pierda trabajo**. Hoy un run del runtime Claude/Codex CLI puede quedar **zombie** (proceso vivo con `exit_code None`, ocupando un slot de concurrencia y potencialmente coste, mientras la ejecución figura cerrada en la DB), **perder sus logs** ante una terminación anormal, **colgarse para siempre** (timeout 0), y la creación de tasks/comentarios en ADO puede **fallar en silencio** (cuarentena sin telemetría, persistencia tragada). Nada de eso lo ve el operador hasta que algo "anda raro". Este plan lo resuelve **sin pedirle nada al operador**: el mismo run que lanzó termina limpio, conserva sus logs, libera su slot, crea la task con mayor tasa de éxito, y los fallos que antes eran invisibles ahora se cuentan en la telemetría que ya existe. El TRABAJO es invisible; el RESULTADO se nota: menos runs colgados, menos procesos acumulados, menos tasks fantasma, menos reintentos manuales.

**"Invisible" NO significa "autónomo" (frontera dura, regla 11):** invisible quiere decir que el operador no configura ni ve el mecanismo. NO quiere decir que el sistema decida por él. **Cada run lo inició el operador**; nada se publica a ADO sin el verdict humano; ningún aprendizaje muta prompts/memoria/goldens. Las acciones de este plan son **higiene de ciclo de vida sobre runs que el operador ya lanzó**: matar el proceso de un run **ya terminado**, cerrar un run **colgado/muerto** con diagnóstico, validar la **estructura** (no el contenido) de un artefacto antes de escribir, y **contar** los fallos para que dejen de ser invisibles. Ninguna decide sobre el producto del trabajo. Cada ítem trae su línea explícita **"Por qué NO viola rule 11"**.

---

## Relación con el Plan 27 (qué se subsume, qué se reemplaza, qué queda fuera)

> **Corrección de estado verificada el 2026-06-14 contra el código** (`codex/subida-cambios-pendientes`): el header del doc 27 dice "propuesto, ningún ítem implementado", pero eso quedó **desactualizado** (mismo patrón que los docs 23 y 26, cuyos headers quedaron "propuesto" tras implementarse). En realidad ya están **IMPLEMENTADOS**: **I0.1** (dedup léxico — `services/context_enrichment.py::_dedup_blocks`, flags `STACKY_CONTEXT_DEDUP_*`, `tests/test_context_dedup.py`), **I0.2** (`harness/complexity.py::estimate_complexity`, flag `STACKY_COMPLEXITY_ESTIMATION_ENABLED`), **I1.1** (`harness/run_repair.py`, flag `STACKY_RUN_REPAIR_ENABLED`, `tests/test_run_repair.py`) y **I1.2** (routing por dificultad en `services/llm_router.py`, flag `STACKY_DIFFICULTY_ROUTING_ENABLED`, `tests/test_difficulty_routing.py`). Quedan **propuestos** del 27: I0.3 (prewarm ADO), I2.1 (rerank por relevancia), I2.2 (prompt-prefix cache claude), I2.3 (expansión de query), I3.1 (paralelizar injectors), I3.2 (caché de lecturas ADO), I3.3 (caps advisor).

- **SUBSUME:** nada. Este plan **no re-especifica ningún ítem del 27**. Ocupa el espacio que el 27 deja vacío: el **ciclo de vida del proceso** (lifecycle/zombie), la **fiabilidad de la escritura** a ADO y la **telemetría de fallos silenciosos**. El 27 optimiza *lo que entra al modelo y cómo se cobra*; el 28 optimiza *que el run llegue a destino sin colgarse ni perder trabajo*.
- **REEMPLAZA:** nada. Los ítems pendientes del 27 (I0.3, I2.x, I3.x) siguen vigentes y **no se tocan**. El 28 no modifica `context_enrichment` (ensamblado/ranking/retrieval), ni el prompt-prefix-cache, ni la caché de **lecturas** ADO.
- **QUEDA FUERA (se delega al 27):** toda optimización de **contexto/retrieval/caché de contenido**. Si una mejora es "ensamblar mejor el prompt", "recuperar mejor la memoria" o "cachear lo que ya se pensó", es del 27, no de acá.
- **Frontera compartida declarada (para que no colisionen):** tres puntos del ciclo de vida que parecen el mismo pero son distintos —
  1. **27/I1.1 (`run_repair`)** repara un run que **terminó** con output vacío/malformado (un solo reintento intra-run).
  2. **28/R1.1 (stall watchdog)** cierra un run que **nunca termina** (colgado/sin actividad).
  3. **28/R0.1 (reap)** mata el **proceso** de un run que el watcher **ya cerró** en la DB.
  Son tres instantes disjuntos del lifecycle; ningún ítem de este plan re-implementa `run_repair`.
- **Frontera de ADO:** el 27/I3.2 cachea **lecturas** caras de ADO; el 28/R1.x endurece las **escrituras** (creación de task/comentario). Reads vs writes: sin solape.

---

## 1. Punto de partida: el sustrato de lifecycle/escritura/telemetría que YA existe (no re-implementar)

Verificado contra el código el 2026-06-14. La lectura central: **la maquinaria de cierre y escritura existe pero está incompleta en los bordes** — cierra la ejecución pero no reapea el proceso; persiste logs solo al final; valida el artefacto solo detrás de un flag; cuenta los fallos en tablas pero no los agrega. El mayor valor de este plan es **cerrar esos bordes**, no inventar.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Registro central de subprocesos vivos por `execution_id` | claude `services/claude_code_cli_runner.py:856` (`_PROCESSES`/`_PROCESSES_LOCK`, `.pop` al cerrar `:857`); codex `services/codex_cli_runner.py:555` | OK — es el **seam para un reap externo**, hoy nadie lo usa desde afuera (D-R1) |
| Cierre de ejecución por el watcher (marca status/exit en DB) | `services/output_watcher.py:379` (`close_execution_with_publish`), terminal en runner `claude_code_cli_runner.py:1036` (`_mark_terminal`) | OK — **cierra la execution pero NO mata el subproceso** (D-R1) |
| Kill del proceso (terminate→kill con gracia) | `services/claude_code_cli_runner.py:827,831` (terminate/kill), disparado solo por runaway `:804` o `session_deadline` `:834` | OK pero **solo intra-runner**; con timeout 0, `session_deadline=None` (`:795`) → el único kill posible es por runaway (D-R1/D-R2) |
| Timeout de sesión del CLI | `config.py:162` (`CLAUDE_CODE_CLI_TIMEOUT`, **default 0 = sin límite**) | Default 0 → un run colgado **nunca** se cierra solo (D-R2) |
| Espera del proceso en codex | `services/codex_cli_runner.py:548` (`proc.wait()` **sin timeout**, sin kill fallback) | **Peor que claude**: cuelgue indefinido sin salida (D-R2) |
| Streaming + persistencia de logs | `log_streamer.py` (`open`/`close`, persistencia en `close()` dentro de `finally` ~`:1214`), output a disco `claude_code_cli_runner.py:868` | OK — **persiste solo al cerrar**; terminación anormal antes del `finally` → buffers en memoria perdidos (D-R3) |
| Polling del watcher / heartbeat | `services/output_watcher.py:189` (`while not evt.wait(timeout=3.0)`), poll configurable `:106`, heartbeat `claude_code_cli_runner.py:694` (`wait(30)`) | OK — usa `Event.wait()`, **no busy-sleep**. **NO es palanca** (ver §2.6) |
| Detección de runs huérfanos | `services/local_diagnostics.py:352` (`_check_orphan_runs`, cuenta `running` > `STACKY_RUNNING_ALERT_MINUTES`) | OK pero **solo diagnostica, no reconcilia** (D-R4) |
| Intake/validación del pending-task | `services/output_watcher.py:942-970` (`artifact_intake.validate_and_normalize`, **gated** por `STACKY_ARTIFACT_INTAKE_ENABLED`), cuarentena `:990` (`_quarantine_pending_once`) | OK pero **la validación fuerte es opt-in**; con flag OFF se POSTea sin validar y la cuarentena es **silenciosa** (D-R5) |
| Auto-create de task desde el watcher | `services/output_watcher.py:998-1015` (arma `body` y `POST` a create-child-task) | OK — **sin validación estructural del body** cuando intake está OFF (D-R5) |
| Outbox de escritura ADO (retry/backoff + dedup idempotente) | `services/ado_write_outbox.py` (`MAX_ATTEMPTS=6` `:67`, dead_letter `:382`, `list_operations(status="attention")` `:465`) | OK — el WRITE es robusto; el dead_letter es **visible en tabla pero no agregado** (D-R7) |
| Persistencia post-publicación de comentario | `services/ado_publisher.py:865` (re-propaga `IntegrityError` → idempotent_replay), `:868-869` (**traga cualquier otro fallo de persistencia** "no crítico") | OK para el caso unique-constraint; un fallo transitorio de persistencia deja **comentario posteado sin registro local** (D-R6) |
| Telemetría de run (turnos/costo/tokens/cache_read) | `harness/telemetry.py:122` (`metadata["harness_telemetry"]`) | OK — **no incluye señales de lifecycle** (zombie, stall, reaped) (D-R7) |
| Harness-health (H8) + DiagnosticsPage | `services/harness_health.py`, `frontend/.../DiagnosticsPage` (`HarnessHealthCard`) | OK — **el seam para exponer fiabilidad sin UI nueva** (R2.x) |
| Capacidades por runtime (resume/stdin/...) | `harness/capabilities.py:21` (`CAPABILITIES`) | OK — seam para decidir por-runtime sin `if` dispersos |
| Cap de concurrencia (slots) | `services/run_slots.py:28` (`try_acquire`) | OK — **un zombie retiene su slot** → throttling injustificado (D-R1) |

**Restricciones vinculantes (idénticas a docs 22-27, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable); "solo Stacky escribe en ADO" = todo por `ado_write_outbox`/el path de publicación existente (este plan **no agrega caminos de escritura**, solo los hace más confiables e idempotentes); mono-operador **sin RBAC** (`current_user()` es un header sin validar); claves de metadata existentes son contrato (**agregar, nunca renombrar**); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR, default **OFF/0**, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → **validar por archivo de test**; **sin fallback silencioso entre runtimes** (codex y claude tienen lifecycle distinto — se cablea cada uno explícito); **sin deps npm/py nuevas** sin justificación escrita (todo con stdlib: `subprocess`, `threading`, `os`); el build congelado no tiene FTS5 verificado (no introducirlo).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Las acciones de este plan son **higiene sobre runs ya lanzados por el operador**: reapear el proceso de un run **terminal**, cerrar un run **muerto**, validar **estructura** (no criterio), contar fallos. Ninguna publica a ADO por su cuenta, ninguna re-lanza trabajo, ninguna decide sobre el contenido. El verdict humano y el path de publicación (U1.3/U2.2 del doc 23) quedan **intactos**.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía ni auto-intake.** Ningún run nace sin el operador; nada "agarra trabajo solo". Matar un proceso huérfano o cerrar un run colgado no es decidir trabajo: es reclamar un recurso de un run que el operador ya terminó o que ya está muerto. (Descartado en doc 24 §2; se respeta al pie.)
2. **No agrega caminos de escritura a ADO ni cambia QUÉ/CUÁNDO se publica.** Las escrituras siguen pasando por el outbox/publicador existente; este plan las hace **idempotentes y validadas**, no nuevas. El verdict humano no se toca.
3. **No expone perillas nuevas al operador.** Todos los flags son **internos** (los administra quien opera el arnés vía la pantalla de flags genérica que ya existe). El operador del día a día no ve nada nuevo. La única superficie que cambia es la **DiagnosticsPage existente** (H8), que muestra *más* información de fiabilidad sin pedir acción.
4. **No re-implementa el motor de contexto del doc 27.** No toca `context_enrichment` (ensamblado/ranking/retrieval), ni `run_repair` (I1.1), ni el prompt-prefix-cache, ni la caché de lecturas ADO. Frontera declarada arriba.
5. **No introduce FTS5 ni deps nuevas.** Todo con stdlib (`subprocess`, `threading`, `os`, `time`).
6. **No "optimiza" el polling.** Se verificó (`output_watcher.py:189`, `claude_code_cli_runner.py:694`) que el watcher y el heartbeat usan `Event.wait(timeout=...)` — **no hay busy-sleep**. Cambiarlo no daría rendimiento y agregaría riesgo. Se documenta como **no-palanca** para no perseguir una optimización falsa.

---

## 3. Diagnóstico: dónde el motor pierde trabajo, recursos y tasa de éxito (con evidencia)

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-R1** | **El watcher cierra la ejecución pero no reapea el subproceso → zombie.** `close_execution_with_publish` (`output_watcher.py:379`) marca la execution cerrada en DB, pero el kill del proceso vive solo dentro del loop del runner (`claude_code_cli_runner.py:827,831`) y solo dispara por runaway (`:804`) o `session_deadline` (`:834`). Con `CLAUDE_CODE_CLI_TIMEOUT=0`, `session_deadline=None` (`:795`) → si el watcher cierra primero (o el thread del runner muere), el proceso queda **vivo con `exit_code None`**, reteniendo su slot (`run_slots.try_acquire:28`). Existe el registro `_PROCESSES` (`:856`) pero **nadie lo usa desde afuera para matar**. | `output_watcher.py:379`, `claude_code_cli_runner.py:795,827,856`, `run_slots.py:28` | Procesos acumulados en la máquina del operador; slots ocupados → runs legítimos throttleados (429 del cap de concurrencia); coste de sesiones colgadas. Invisible hasta que "se llena". |
| **D-R2** | **Timeout 0 por default + codex sin timeout → un run colgado nunca cierra solo.** `CLAUDE_CODE_CLI_TIMEOUT` default **0** (`config.py:162`) = sin tope de sesión; codex hace `proc.wait()` **sin timeout ni kill fallback** (`codex_cli_runner.py:548`). Un CLI que se cuelga (red caída, modelo que no responde, stdin esperando) queda esperando indefinidamente. | `config.py:162`, `codex_cli_runner.py:548`, `claude_code_cli_runner.py:834` | Runs colgados que el operador tiene que matar a mano; latencia percibida infinita; combinado con D-R1, se vuelven zombies permanentes. |
| **D-R3** | **Los logs se persisten solo en `close()` (finally) → terminación anormal los pierde.** El `log_streamer` acumula eventos en buffers en memoria y persiste a `ExecutionLog` recién en `close()` (`log_streamer.py` ~`:1214`, en `finally`); el output a disco es al final (`claude_code_cli_runner.py:868`). Si el proceso muere antes del `finally` (thread killed, backend reiniciado, OOM) → buffers perdidos. | `log_streamer.py:~1214`, `claude_code_cli_runner.py:868` | Runs con `exit_code None` y **sin logs** → el operador no puede diagnosticar qué pasó; el loop de mejora queda ciego. |
| **D-R4** | **No hay reconciliación de huérfanos; el detector solo reporta.** `_check_orphan_runs` (`local_diagnostics.py:352`) cuenta executions `running` más viejas que el umbral, pero **no actúa**: no mata procesos, no cierra executions, no persiste logs. Al reiniciar el backend, los `cmd/claude.exe`/`codex.exe` viejos quedan vivos para siempre. | `local_diagnostics.py:352` | Acumulación de procesos entre reinicios; el operador limpia a mano con el Administrador de tareas. |
| **D-R5** | **El pending-task se POSTea sin validación estructural cuando el intake está OFF; la cuarentena es silenciosa.** La validación fuerte (`artifact_intake.validate_and_normalize`, `output_watcher.py:942-970`) está **gated** por `STACKY_ARTIFACT_INTAKE_ENABLED`. Con el flag OFF, el path va por `:987-992` (solo `json.loads`) y luego `:998-1015` arma el `body` y POSTea **sin validar campos requeridos ni coherencia ordinal/parent-id**. Un parse fallido cae en `_quarantine_pending_once` (`:990`) **sin telemetría** → el operador no se entera de que la task no se creó. Esta es exactamente la causa raíz documentada ("crea archivos pero no la task" = mismatch ordinal vs ADO id + JSON inválido). | `output_watcher.py:942-970,988-1015,990` | Tasks fantasma (archivos creados, task no); fallo silencioso que el operador descubre tarde; tasa de éxito efectiva de creación por debajo de lo posible. |
| **D-R6** | **La persistencia post-publicación traga fallos no-Integrity → comentario en ADO sin registro local.** `ado_publisher.py:865` re-propaga `IntegrityError` (maneja idempotent_replay por unique-constraint), pero `:868-869` **absorbe cualquier otro fallo de persistencia** ("no crítico"). Un fallo transitorio (DB lockeada, disco lleno) tras un POST exitoso deja el comentario **posteado pero no registrado** → un reintento posterior puede **re-postear**. | `ado_publisher.py:865-869` | Comentarios duplicados en ADO (ruido para el equipo) en el camino de fallo transitorio; el caso unique-constraint ya está cubierto, este no. |
| **D-R7** | **Los fallos silenciosos no se agregan ni se exponen → el loop de mejora no cierra.** El dead_letter del outbox es visible en tabla (`ado_write_outbox.py:382,465`) pero **no agregado**; las cuarentenas (`output_watcher.py:990`) no emiten métrica; los zombies/stalls no se cuentan en la telemetría (`harness/telemetry.py:122` no tiene señales de lifecycle). La `harness_health` (H8) no cubre nada de esto. | `ado_write_outbox.py:382`, `output_watcher.py:990`, `harness/telemetry.py:122`, `services/harness_health.py` | Sin un número agregado, los fallos son invisibles: nadie sabe cuántas tasks no se crearon ni cuántos runs quedaron zombie. No se puede afinar lo que no se mide. |

**Lectura estratégica:** el doc 27 exprime el motor *por dentro del razonamiento*. Este plan exprime el motor *por los bordes del ciclo de vida*: que el proceso muera cuando debe, que los logs sobrevivan, que el run colgado se cierre con diagnóstico, que la task se cree con validación, que el comentario no se duplique, y que todo lo que falla se **cuente**. El operador no toca nada: ve menos runs colgados, menos procesos acumulados, más tasks creadas a la primera, y una DiagnosticsPage que por fin dice la verdad sobre la fiabilidad.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo** y por riesgo. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: **R0** (higiene de procesos — el dolor más reportado, mayor leverage) → **R1** (fiabilidad de cierre y escritura) → **R2** (cerrar el loop con telemetría). Todos los flags default **OFF**; con todo en default, el motor se comporta **byte-idéntico** a hoy.

### FASE R0 — Higiene de procesos: que ningún run quede zombie ni pierda su trabajo

---

#### R0.1 Reaping del subproceso al cerrar la ejecución — el ítem de mayor leverage

- **Ataca:** D-R1.
- **Problema + evidencia:** el watcher cierra la execution en DB (`output_watcher.py:379`) pero no mata el proceso; el kill solo existe dentro del runner (`claude_code_cli_runner.py:827,831`) y solo dispara por runaway/`session_deadline` (que es `None` con timeout 0, `:795`). Resultado: proceso vivo con `exit_code None`, slot retenido (`run_slots.py:28`). El registro `_PROCESSES` (`:856`) ya existe pero nadie lo usa desde afuera.
- **Propuesta (mínima):** exponer en cada runner un helper `reap(execution_id) -> bool` que, bajo `_PROCESSES_LOCK`, busque el `Popen` registrado para ese `execution_id` y haga `terminate()` → `wait(grace)` → `kill()` best-effort (reusa la secuencia que ya vive en `:827-832`). Invocarlo desde `close_execution_with_publish` (`output_watcher.py:379`) y desde `_mark_terminal` (`claude_code_cli_runner.py:1036`) **después** de marcar el estado en DB. Sin fallback entre runtimes: claude reapea su `_PROCESSES`, codex el suyo (`codex_cli_runner.py:555`); un `runtime` desconocido → no-op.
- **Impacto esperado:** procesos huérfanos por cierre externo → **~0**; slots liberados al instante (menos 429 del cap de concurrencia); coste de sesiones colgadas eliminado. Métrica: nº de procesos `claude.exe`/`codex.exe` vivos sin execution activa (R2.1), tiempo medio de retención de slot tras cierre.
- **Garantía de invisibilidad:** el cierre ya ocurre hoy; solo se le agrega el reap. El operador no hace nada nuevo; nota que los procesos ya no se acumulan.
- **Salvaguarda de calidad (y cómo se mide):** **nunca** mata por nombre de proceso; solo el `pid` exacto registrado en `_PROCESSES[execution_id]` (cero riesgo de matar un proceso ajeno o de otra execution). Si el proceso ya murió → no-op idempotente. **Nunca** se invoca sobre una execution en estado activo (solo desde el path de cierre/terminal). Flag OFF → byte-idéntico. Se mide con un test que verifica que reap solo toca el pid registrado y que no se llama en runs activos.
- **Por qué NO viola rule 11:** matar el proceso de un run que el watcher **ya cerró** no decide nada sobre el trabajo ni publica nada; es reclamar un recurso muerto. Es lo que el operador haría con el Administrador de tareas, sin obligarlo.
- **Flag:** `STACKY_RUNNER_REAP_ON_CLOSE_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`.
- **TDD (`tests/test_runner_reap.py`):** execution cerrada con `Popen` vivo (mock) → `reap` llama terminate/kill y devuelve `True`; proceso ya muerto → no-op `False`; pid de otra execution → intacto; flag OFF → reap no se invoca; runtime desconocido → no-op. Mock de `Popen` (sin binarios reales).
- **Complejidad:** M (toca el path de cierre de ambos runners + el watcher; partible: PR1 claude, PR2 codex).

---

#### R0.2 Persistencia garantizada de logs ante terminación anormal

- **Ataca:** D-R3.
- **Problema + evidencia:** el `log_streamer` persiste a `ExecutionLog` recién en `close()` dentro de `finally` (`log_streamer.py:~1214`); el output a disco es al final (`claude_code_cli_runner.py:868`). Terminación anormal antes del `finally` (thread killed, reinicio, OOM) → buffers en memoria perdidos.
- **Propuesta (mínima):** flush incremental — persistir los eventos del buffer a `ExecutionLog` en lotes cortos (cada N eventos o cada T segundos vía el heartbeat que ya existe, `claude_code_cli_runner.py:694`), no solo en `close()`. Como salvavidas adicional, el `reap` de R0.1 invoca un `flush()` final **antes** de matar. Append idempotente: cada evento lleva un índice/secuencia; un re-flush no duplica lo ya persistido.
- **Impacto esperado:** runs con `exit_code None` **sin** logs → ~0. Métrica: % de executions terminadas con al menos un `ExecutionLog` persistido (objetivo ~100%).
- **Garantía de invisibilidad:** el operador ve, en la pantalla de logs que ya usa, los logs que antes se perdían. Cero acción nueva.
- **Salvaguarda de calidad (y cómo se mide):** el flush es **append idempotente** por secuencia → un evento no aparece dos veces aunque se flushee en lote y de nuevo en `close()`. Flag OFF → persiste solo en `close()` como hoy (byte-idéntico). Se mide con un test que mata el run sin `close()` y verifica que los logs hasta el último flush están persistidos y sin duplicados.
- **Por qué NO viola rule 11:** persistir logs es trazabilidad pura; no decide ni publica nada.
- **Flag:** `STACKY_LOG_FLUSH_INCREMENTAL_ENABLED` (bool, default **false**).
- **TDD (`tests/test_log_incremental_flush.py`):** matar el run sin `close()` → logs persistidos hasta el último flush; doble flush → sin duplicados (idempotencia por secuencia); flag OFF → solo en `close()`.
- **Complejidad:** M.

---

#### R0.3 Barrido de huérfanos en arranque + watchdog reconciliador (promueve el detector existente)

- **Ataca:** D-R4 (y combina R0.1 + R0.2 para reconciliar).
- **Problema + evidencia:** `_check_orphan_runs` (`local_diagnostics.py:352`) solo **cuenta** executions `running` viejas; no mata procesos ni cierra executions. Al reiniciar el backend, los procesos viejos quedan vivos.
- **Propuesta (mínima):** promover el detector de "reportar" a "reconciliar". Un reaper que corre (a) **al arrancar el backend** y (b) periódicamente cada `STACKY_ORPHAN_REAPER_INTERVAL_SEC` (default **0 = off**): para cada execution en estado **terminal** cuyo `pid` registrado siga vivo (o, tras reinicio, cuyo `pid` persistido en metadata corresponda a un `claude.exe`/`codex.exe` vivo), persiste logs (R0.2) → reapea (R0.1) → sella `metadata["reaped"] = {by, at, reason}` (clave **nueva**, aditiva). Para executions que quedaron `running` tras un reinicio (sin thread que las atienda), primero se reconcilian a `failed(reason="orphaned_on_restart")` y luego se reapea el proceso.
- **Impacto esperado:** cero acumulación de procesos entre reinicios; la máquina del operador estable. Métrica: nº de procesos huérfanos al arrancar (objetivo 0 tras el barrido).
- **Garantía de invisibilidad:** corre en background; el operador no lo ve ni lo dispara.
- **Salvaguarda de calidad (y cómo se mide):** **solo** toca executions en estado terminal (o `running` huérfanas confirmadas por edad + ausencia de thread); **nunca** un run activo con heartbeat reciente; **solo** mata pids que Stacky registró/persistió (no procesos ajenos del sistema). Flag OFF → comportamiento actual (solo diagnostica). Se mide con tests que verifican intangibilidad de runs activos y que no se matan pids no-registrados.
- **Por qué NO viola rule 11:** higiene sobre runs ya terminados o muertos; no decide trabajo ni publica.
- **Flag:** `STACKY_ORPHAN_REAPER_ENABLED` (bool, default **false**) + `STACKY_ORPHAN_REAPER_INTERVAL_SEC` (int, default 0).
- **TDD (`tests/test_orphan_reaper.py`):** execution terminal + pid vivo (mock) → reaped + `metadata["reaped"]`; execution activa con heartbeat reciente → intacta; pid no-registrado → no se toca; `running` huérfana tras "reinicio" → reconciliada a `failed` + reaped; flag OFF → solo cuenta (comportamiento de `_check_orphan_runs` actual).
- **Complejidad:** M.

---

### FASE R1 — Fiabilidad de cierre y de escritura: menos runs colgados, más tasks/comentarios creados con éxito

---

#### R1.1 Watchdog de inactividad con cierre limpio + timeout/kill en codex

- **Ataca:** D-R2.
- **Problema + evidencia:** `CLAUDE_CODE_CLI_TIMEOUT` default **0** (`config.py:162`) = sin tope; codex `proc.wait()` **sin timeout** (`codex_cli_runner.py:548`). Un CLI colgado espera para siempre.
- **Propuesta (mínima):** un **watchdog de inactividad** (NO de duración total — para no cortar runs largos legítimos): si el stream no emite eventos nuevos por `STACKY_STALL_WATCHDOG_SECONDS` (default **0 = off**), disparar un **cierre limpio** = persistir logs (R0.2) → reap (R0.1) → `_mark_terminal(status="failed", reason="stalled")` con `metadata["stall"]={detected_at, last_event_at}`. Reusa el heartbeat existente (`claude_code_cli_runner.py:694`) como reloj de inactividad. En codex, reemplazar `proc.wait()` (`:548`) por una espera acotada con `terminate→kill` espejando la secuencia de claude (`:827-832`), gobernada por el mismo flag.
- **Impacto esperado:** runs colgados se cierran solos con diagnóstico en vez de quedar zombie; latencia percibida acotada. Métrica: nº de runs `running` > umbral (debe caer a ~0), tiempo medio hasta cierre de un run colgado.
- **Garantía de invisibilidad:** el operador ve "failed: stalled" con logs en vez de un run colgado eterno. No configura nada (flag interno).
- **Salvaguarda de calidad (y cómo se mide):** dispara por **inactividad del stream**, no por reloj de pared → un run largo que **sigue emitiendo** eventos **nunca** se corta (cero falsos positivos sobre trabajo real). El `reason="stalled"` lo distingue de un fallo de criterio (que sigue yendo a `needs_review`). Default 0 → comportamiento actual exacto. Se mide con un test de stream activo que verifica que NO se corta, y uno de stream inactivo que verifica el cierre con reason.
- **Por qué NO viola rule 11:** cerrar un run **muerto** (sin actividad) no decide sobre el trabajo ni publica; es liberar al operador de matarlo a mano. El run lo lanzó él; esto solo lo cierra cuando ya no produce nada.
- **Flag:** `STACKY_STALL_WATCHDOG_SECONDS` (int, default **0**).
- **TDD (`tests/test_stall_watchdog.py`):** stream sin eventos > umbral → cierre `failed/stalled` + logs persistidos + reap; stream que sigue emitiendo → NO se corta aunque dure mucho; default 0 → nunca dispara; codex `wait` con timeout → terminate/kill. Mock de stream (sin binarios reales).
- **Complejidad:** M/L (toca el loop de espera de ambos runners; partible: PR1 codex bounded-wait, PR2 watchdog de inactividad claude).

---

#### R1.2 Validación estructural always-on del pending-task + telemetría de cuarentena

- **Ataca:** D-R5. Extiende `artifact_intake`; NO lo re-implementa.
- **Problema + evidencia:** la validación fuerte (`output_watcher.py:942-970`) está gated por `STACKY_ARTIFACT_INTAKE_ENABLED`; con el flag OFF, el watcher POSTea el `body` (`:998-1015`) **sin validar campos requeridos ni coherencia ordinal/parent-id**, y un parse fallido cuarentena en silencio (`:990`). Es la causa raíz documentada del "crea archivos pero no la task".
- **Propuesta (mínima):** (a) una **validación estructural mínima determinística** que corre **siempre** antes del POST (campos requeridos presentes, tipos correctos, coherencia ordinal vs parent ADO id) — reusa la lógica de `artifact_intake.validate_and_normalize` pero como **gate barato e independiente del flag de normalización**: si la estructura es inválida → no POST, cuarentena. (b) **Telemetría en cada cuarentena**: emitir un contador/evento (`metadata` del run o un `ExecutionLog` de nivel WARN clasificado) para que el fallo deje de ser silencioso y alimente R2.1. El POST solo se dispara con un `body` estructuralmente válido.
- **Impacto esperado:** **+tasa de tasks creadas con éxito**; -tasks fantasma. Métrica: `created_ok / intentos` (R2.2), nº de cuarentenas visibles (antes: invisible).
- **Garantía de invisibilidad:** el operador no valida nada; el sistema rechaza el `body` malo antes de gastar el POST, y la cuarentena aparece en la DiagnosticsPage existente (no en una UI nueva).
- **Salvaguarda de calidad (y cómo se mide):** la validación es **estructural**, no de **contenido** — un `body` válido con mal contenido **sigue** yendo a su flujo normal (needs_review / revisión humana). Solo bloquea lo estructuralmente roto (lo que de todos modos ADO rechazaría o crearía mal). Flag OFF → comportamiento actual (POST sin gate). Se mide con tests: campo faltante → no POST + cuarentena con telemetría; ordinal/id incoherente → bloqueado; body estructuralmente válido → POST como hoy.
- **Por qué NO viola rule 11:** validar estructura no decide sobre el trabajo; previene una escritura malformada y **avisa** (telemetría) para que el humano actúe. No publica ni descarta trabajo: cuarentena = reversible.
- **Flag:** `STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED` (bool, default **false**).
- **TDD (`tests/test_pending_task_validation.py`):** campo requerido faltante → no POST + cuarentena + telemetría; mismatch ordinal/parent-id → bloqueado; JSON válido y coherente → POST; flag OFF → byte-idéntico (POST sin gate); la cuarentena emite el contador.
- **Complejidad:** M.

---

#### R1.3 Publicación idempotente robusta ante fallo de persistencia local

- **Ataca:** D-R6.
- **Problema + evidencia:** `ado_publisher.py:865` re-propaga `IntegrityError` (idempotent_replay por unique-constraint), pero `:868-869` **traga cualquier otro fallo de persistencia** ("no crítico"). Un fallo transitorio (DB lockeada, disco lleno) tras un POST exitoso deja el comentario **posteado sin registro local** → un reintento puede **re-postear**.
- **Propuesta (mínima):** persistir una **intención de publicación** (idempotency_key) **antes** del POST (reusa el patrón de `idempotency_key` del outbox, `ado_write_outbox` dedup `:248`); ante un reintento, si el comentario ya tiene marker/idempotency_key registrado, **no re-postear** (devolver idempotent_replay). Alternativa equivalente y declarada: ante el path de reintento, consultar `comment_exists_fn` antes de re-postear. El objetivo es que un persist fallido **no** produzca un comentario duplicado.
- **Impacto esperado:** comentarios duplicados en ADO → ~0 en el camino de fallo transitorio. Métrica: nº de re-publicaciones detectadas (debe caer), nº de persist-failures registrados (R2.1).
- **Garantía de invisibilidad:** el equipo en ADO no ve comentarios duplicados; el operador no hace nada.
- **Salvaguarda de calidad (y cómo se mide):** si el check de idempotencia/existencia falla, se cae al **comportamiento actual** (no empeora). El caso `IntegrityError` ya cubierto no se toca. Flag OFF → byte-idéntico. Se mide con un test: POST ok + persist falla (no-Integrity) → segundo intento detecta la intención previa y **no** re-postea.
- **Por qué NO viola rule 11:** es robustez de una escritura que el operador **ya aprobó** publicar; no agrega publicaciones ni decide nada nuevo, solo evita duplicar.
- **Flag:** `STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED` (bool, default **false**).
- **TDD (`tests/test_publish_idempotent_guard.py`):** POST ok + persist no-Integrity falla → reintento no re-postea (detecta intención/marker); IntegrityError → idempotent_replay como hoy; check de existencia falla → fallback a comportamiento actual; flag OFF → byte-idéntico.
- **Complejidad:** M.

---

### FASE R2 — Cerrar el loop sin tocar al operador: telemetría de fallos silenciosos

---

#### R2.1 Agregado de fiabilidad en harness-health (zombies, stalls, cuarentenas, dead_letter)

- **Ataca:** D-R7. Extiende `harness_health` (H8); NO crea UI nueva.
- **Problema + evidencia:** el dead_letter del outbox es visible solo en tabla (`ado_write_outbox.py:382,465`); las cuarentenas no emiten métrica (`output_watcher.py:990`); zombies/stalls no se cuentan (`harness/telemetry.py:122`). La `harness_health` no cubre nada de esto.
- **Propuesta (mínima):** agregar a `services/harness_health.py` (y por ende a la `HarnessHealthCard` de la DiagnosticsPage que ya existe) un bloque de **fiabilidad**: contadores agregados de `dead_letter` del outbox, cuarentenas de pending-task (R1.2), runs `reaped` (R0.1/R0.3), runs `stalled` (R1.1) y persist-failures de publicación (R1.3) — por proyecto y ventana temporal, leyendo de la metadata/tablas que esos ítems ya pueblan. Read-only.
- **Impacto esperado:** los fallos silenciosos se vuelven un **número visible** en la pantalla que el operador ya consulta → el loop de mejora cierra sin pedirle nada. Métrica: el propio dashboard.
- **Garantía de invisibilidad:** se agrega a una card existente; cero pasos nuevos, cero workflow nuevo. El operador lo ve si entra a Diagnostics (como hoy), no se le obliga.
- **Salvaguarda de calidad (y cómo se mide):** read-only puro; no muta nada; si una fuente falta, degrada con gracia (la card muestra "—"). Flag OFF → la card no agrega el bloque (byte-idéntico). Se mide con un test del endpoint que verifica los contadores con datos sintéticos.
- **Por qué NO viola rule 11:** mostrar números no decide nada; es observabilidad.
- **Flag:** `STACKY_RELIABILITY_KPIS_ENABLED` (bool, default **false**).
- **TDD (`tests/test_harness_health_reliability.py`):** con dead_letter/cuarentenas/reaped/stalled sintéticos → los contadores correctos por proyecto/ventana; fuente ausente → degrada; flag OFF → sin bloque nuevo.
- **Complejidad:** M.

---

#### R2.2 KPI de tasa de éxito efectiva de creación + saneamiento de latencia

- **Ataca:** D-R7 (cierre, lado management). Deriva de R2.1.
- **Problema + evidencia:** no existe un número de "qué porcentaje de las creaciones de task/comentario que se intentaron realmente llegaron a ADO con éxito", ni una latencia de run **saneada** (excluyendo el tiempo que un run estuvo zombie/stalled). Las señales existen dispersas (`ado_write_outbox`, cuarentenas, `harness_telemetry`).
- **Propuesta (mínima):** un KPI derivado en `harness_health`: `tasa_exito_creacion = created_ok / intentos` (intentos = enqueues + auto-creates; created_ok = succeeded confirmados) y `duracion_saneada` (duración del run menos el tiempo en estado zombie/stalled, usando `metadata["reaped"]`/`metadata["stall"]`). Read-only, mismo bloque que R2.1.
- **Impacto esperado:** management ve el ahorro y la mejora de fiabilidad **en un número** (más tasks creadas a la primera, menos tiempo perdido en zombies) sin sumar trabajo operativo. Métrica: el propio KPI a lo largo del tiempo.
- **Garantía de invisibilidad:** mismo dashboard existente; cero acción del operador.
- **Salvaguarda de calidad (y cómo se mide):** definiciones explícitas y testeadas (qué cuenta como intento/éxito) para que el KPI no mienta; read-only. Flag compartido con R2.1. Se mide con un test que arma intentos/éxitos sintéticos y verifica el ratio.
- **Por qué NO viola rule 11:** es una métrica; no decide ni publica.
- **Flag:** `STACKY_RELIABILITY_KPIS_ENABLED` (compartido con R2.1).
- **TDD (`tests/test_creation_success_kpi.py`):** ratio correcto con éxitos/fallos sintéticos; `duracion_saneada` descuenta el tiempo zombie; sin datos → degrada.
- **Complejidad:** S/M.

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | **R0.1** Reaping al cerrar | M | **Muy alto (procesos/slots/coste)** | Bajo (solo pid registrado, flag OFF) | — |
| 2 | **R0.2** Persistencia incremental de logs | M | Alto (diagnóstico) | Bajo (append idempotente) | — |
| 3 | **R0.3** Reaper de huérfanos + watchdog | M | Alto (estabilidad máquina) | Bajo (solo terminales) | R0.1, R0.2 |
| 4 | **R1.1** Stall watchdog + codex timeout/kill | M/L | **Muy alto (runs colgados)** | Medio (cortar runs → por inactividad, no reloj) | R0.1, R0.2 |
| 5 | **R1.2** Validación estructural del pending-task | M | **Muy alto (tasa de éxito)** | Medio (no bloquear válidos → solo estructura) | `artifact_intake` (en código) |
| 6 | **R1.3** Publicación idempotente robusta | M | Alto (sin duplicados) | Bajo (fallback a actual) | outbox idempotency (en código) |
| 7 | **R2.1** Fiabilidad en harness-health | M | Alto (cierra el loop) | Bajo (read-only) | R0/R1 pueblan datos |
| 8 | **R2.2** KPI de éxito + latencia saneada | S/M | Medio/alto (management) | Bajo (read-only) | R2.1 |

**Reglas de implementación (las 7 del doc 22 + las de frontend del doc 23 aplican íntegras):** TDD; validar por archivo de test (suite contaminada); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves nuevas (`reaped`, `stall`, y los contadores de fiabilidad); default **OFF/0** (retro-compat **byte-idéntica** — con todos los flags en default, el lifecycle se comporta EXACTAMENTE como hoy, runtime por runtime); ADO solo por los caminos de escritura existentes (este plan los hace idempotentes/validados, no nuevos); **sin fallback silencioso entre runtimes** (claude y codex se cablean por separado, cada uno con su `_PROCESSES`); sin deps npm/py nuevas (solo `subprocess`/`threading`/`os`); UI (DiagnosticsPage) degrada con gracia.

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Resumen de la doctrina: (a) todas las acciones son **higiene sobre runs ya lanzados por el operador** (reapear un proceso terminal, cerrar un run muerto, validar estructura, contar fallos); (b) nada se publica a ADO por su cuenta (el verdict humano y el path de publicación U1.3/U2.2 quedan intactos; R1.3 solo evita **duplicar** una publicación ya aprobada); (c) lo único que "decide" es matar un proceso **muerto/terminal** o bloquear una escritura **estructuralmente inválida** — ninguna decisión sobre el producto del trabajo. Cada ítem trae su línea "Por qué NO viola rule 11".

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (que NO configura ni ve estos mecanismos)
- **Hoy:** a veces un run queda "running" para siempre y lo tiene que matar a mano; el Administrador de tareas se llena de `claude.exe`/`codex.exe` viejos; un run que murió no tiene logs para diagnosticar; a veces "crea los archivos pero no la task" y se entera tarde.
- **Después (sin tocar nada):** los runs colgados se cierran solos con un "failed: stalled" que **sí** tiene logs; los procesos no se acumulan (se reapean al cerrar y al arrancar); las tasks se crean con mayor tasa de éxito (validación estructural antes del POST); los comentarios no se duplican. No ve ninguna perilla nueva: solo nota que Stacky "no se cuelga ni pierde cosas".

### Desarrollador / equipo (que vive en ADO)
- **Hoy:** a veces faltan tasks que el agente "completó", o aparece un comentario duplicado.
- **Después:** menos tasks faltantes (validación + telemetría de cuarentena) y sin comentarios duplicados (publicación idempotente) — sin cambios en cómo Stacky escribe, solo más confiable.

### Management
- **Hoy:** no hay un número de fiabilidad; los fallos son anecdóticos ("a veces falla").
- **Después:** una tasa de éxito efectiva de creación y una latencia saneada (R2.2) en la DiagnosticsPage que ya existe, más contadores de zombies/stalls/cuarentenas/dead_letter (R2.1) — el ahorro y la fiabilidad se vuelven medibles sin sumar trabajo operativo.

---

## 7. Ventaja competitiva: por qué la higiene invisible gana

1. **Un CLI suelto deja zombies; el arnés los limpia.** Lanzar Claude/Codex CLI a mano deja procesos colgados, slots ocupados y logs perdidos que el humano tiene que reclamar. Stacky lo hace solo, dentro de los límites que el humano fijó, sin cruzar la línea de la autonomía (no decide trabajo, solo recupera recursos muertos).
2. **La tasa de éxito efectiva es la métrica que importa.** No alcanza con que el agente "complete"; lo que cuenta es que la task/comentario **llegue** a ADO. Validar la estructura antes de escribir y contar lo que se cuarentena convierte fallos silenciosos en una métrica accionable — algo que un CLI suelto no tiene.
3. **Confiabilidad invisible: el cuelgue no llega al humano.** El watchdog de inactividad y el reaper cierran lo muerto antes de que el operador lo note, con cero pérdida de control — el centauro sigue firmando cada verdict, pero ya no tiene que ser, además, el administrador de procesos.

---

## 8. Métricas y telemetría para cerrar el loop (sin tocar al operador)

Todo se apoya en seams existentes (metadata de run, tablas del outbox, `harness_telemetry`, `harness_health`/DiagnosticsPage de H8). Cero UI nueva obligatoria.

| Métrica | Hoy | Objetivo | Fuente |
|---|---|---|---|
| Procesos `claude.exe`/`codex.exe` vivos sin execution activa | acumulan | ~0 | reap (R0.1/R0.3) + contador (R2.1) |
| Runs terminados **sin** logs persistidos | ocurre en terminación anormal | ~0 | flush incremental (R0.2) |
| Runs `running` más viejos que el umbral (colgados) | quedan zombie | ~0 (cierre `stalled`) | stall watchdog (R1.1) |
| Tasa de éxito efectiva de creación (`created_ok / intentos`) | no medida | medible y creciente | R2.2 sobre outbox + auto-create |
| Tasks cuarentenadas (no creadas) | invisibles | visibles y contadas | validación + telemetría (R1.2/R2.1) |
| Comentarios duplicados en ADO | posibles en fallo transitorio | ~0 | publicación idempotente (R1.3) |
| Latencia de run saneada (sin tiempo zombie/stalled) | contaminada por colgados | limpia | `metadata["reaped"]`/`["stall"]` (R2.2) |
| Slots retenidos por zombies (→ 429 injustificados) | ocurre | ~0 | reap libera el slot (R0.1) |
| Perillas nuevas que el operador debe tocar | — | **cero** (todos los flags internos, default OFF) | — |

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El reap mata un proceso equivocado | Solo el `pid` exacto registrado en `_PROCESSES[execution_id]`; nunca por nombre. Test de aislamiento por pid. |
| El reaper de arranque mata un run legítimo que sobrevivió un reinicio | Solo executions en estado **terminal**, o `running` huérfanas confirmadas por edad + ausencia de thread con heartbeat reciente; reconcilia a `failed` antes de matar. |
| El stall watchdog corta un run largo pero **vivo** | Dispara por **inactividad del stream** (no reloj de pared); un run que sigue emitiendo nunca se corta. Default 0 (off). `reason="stalled"` distingue de fallo de criterio. |
| El flush incremental duplica eventos de log | Append idempotente por índice/secuencia; test de doble flush sin duplicados. |
| La validación estructural rechaza un pending-task válido pero inusual | Valida **estructura/coherencia ordinal-id**, no contenido; lo válido pasa; lo rechazado va a cuarentena **reversible** + telemetría. Flag OFF = comportamiento actual. |
| El guard idempotente agrega un read extra a ADO | Solo en el path de **reintento tras persist-failure**, no en el camino feliz; fallback a comportamiento actual si el check falla. |
| Concurrencia en el reap (race entre runner y watcher) | Toda operación sobre `_PROCESSES` bajo `_PROCESSES_LOCK`; reap idempotente (proceso ya muerto → no-op). |
| Diferencias de lifecycle claude vs codex | Sin fallback silencioso: cada runtime se cablea por separado con su propio `_PROCESSES`; `harness/capabilities.py` declara las diferencias. |

---

## 10. Roadmap por fases (estado)

| Fase | Ítem | Estado |
|---|---|---|
| R0 | R0.1 Reaping del subproceso al cerrar | PROPUESTO |
| R0 | R0.2 Persistencia incremental de logs | PROPUESTO |
| R0 | R0.3 Reaper de huérfanos + watchdog reconciliador | PROPUESTO |
| R1 | R1.1 Stall watchdog + codex timeout/kill | PROPUESTO |
| R1 | R1.2 Validación estructural del pending-task + telemetría | PROPUESTO |
| R1 | R1.3 Publicación idempotente robusta | PROPUESTO |
| R2 | R2.1 Fiabilidad en harness-health | PROPUESTO |
| R2 | R2.2 KPI de éxito efectiva + latencia saneada | PROPUESTO |

**Estado global:** PROPUESTO (0/8 implementado al 2026-06-14). Con todos los flags en default OFF/0, el comportamiento es **byte-idéntico** al actual, runtime por runtime.
