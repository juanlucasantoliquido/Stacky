# Plan 255 — Cero fallas mudas: excepciones tragadas y el `resume` muerto

**Estado:** PROPUESTO v1
**Serie:** Robustez desde los logs (253-258). Plan **#3 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales + censo AST del backend.

> La auditoría encontró tres bugs que llevan **días o semanas** funcionando mal sin que nadie se enterase, y los tres tienen la misma causa estructural: **el 77 % de los fallos manejados del backend se reporta por debajo de su gravedad real, o no se reporta en absoluto**. El caso más caro: el mecanismo de `resume` de sesiones está **muerto desde el 2026-07-17** y quema tokens en cada corrida, mientras el log dice solamente `WARNING`.

---

## 1. Objetivo y KPI

Convertir el silencio en señal: arreglar los 3 bugs mudos concretos que la auditoría probó, y después instalar el **gate estructural** que impide que un `except Exception: pass` nuevo entre al repo sin justificación.

| KPI | Hoy (medido) | Meta |
|---|---|---|
| `harness.resume.resolve falló (arranque en frío)` | **50** ocurrencias, del 07-17 al 07-26 | **0** |
| Corridas que arrancan en frío teniendo sesión previa reutilizable | **100 %** cuando se pasa `execution_id` | **0 %** |
| `NameError` en producción | **5** el 2026-07-26 (2 bugs distintos) | **0** |
| `except Exception` + `pass` sin logging (0 rastro) | **97** | **≤ 97 congelado por ratchet**, y 0 en `services/` + `api/` críticos |
| Proporción de fallos manejados que llegan a nivel `error` | **23 %** (60 de 257) | **≥ 50 %** en los módulos del camino caliente |
| Bugs que sobreviven ≥ 24 h sin que el log lo grite | 3 confirmados | **0** (los `except` mudos del camino caliente pasan a `error` + contador) |

---

## 2. Evidencia real (anclaje anti-alucinación)

### E1 — El `resume` está muerto desde el 2026-07-17 (y el log solo susurra)

Firma en los logs, con serie temporal — **vivo hoy**:

```
50 WARNING [harness.resume] harness.resume.resolve falló (arranque en frío):
   Query.filter() being called on a Query which already has LIMIT or OFFSET applied
```

| Log | Ocurrencias |
|---|---|
| `stacky-2026-07-17.log` | 1 |
| `stacky-2026-07-18.log` | 12 |
| `stacky-2026-07-19.log` | 1 |
| `stacky-2026-07-20.log` | 8 |
| `stacky-2026-07-21.log` | 11 |
| `stacky-2026-07-22.log` | 5 |
| `stacky-2026-07-23.log` | 6 |
| `stacky-2026-07-25.log` | 4 |
| **`stacky-2026-07-26.log`** | **2** (última: `2026-07-26 15:17:54`) |

Aparece además **9 veces** en `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-07-20.log`: el bug está también en el binario que usa el operador.

**El código culpable — `Stacky Agents/backend/harness/resume.py:92-102`** (función `resolve`, def en `harness/resume.py:47`):

```python
 92            query = (
 93                db_session.query(AgentExecution)
 94                .filter(AgentExecution.ticket_id == ticket_id)
 95                .filter(AgentExecution.agent_type == agent_type)
 96                .filter(AgentExecution.status == "completed")
 97                .order_by(AgentExecution.id.desc())
 98                .limit(5)                                        # LIMIT aplicado acá
 99            )
100            if execution_id is not None:
101                query = query.filter(AgentExecution.id != execution_id)   # BUG
102            rows = query.all()
```

SQLAlchemy prohíbe `.filter()` después de `.limit()`. **Consecuencia:** cada vez que se pasa `execution_id` — que es el caso normal — el query revienta, el `except` de `harness/resume.py:136` lo atrapa, `harness/resume.py:137` loguea un `warning`, y `harness/resume.py:138` hace `return None, None`. El runner interpreta eso como "no hay nada que reanudar" y **arranca de cero**.

Los call-sites también lo tragan a nivel warn: `Stacky Agents/backend/services/claude_code_cli_runner.py:2457` y `Stacky Agents/backend/services/codex_cli_runner.py:507`.

**Costo real:** cada corrida que podía reanudar sesión + delta de prompt arranca en frío. Son **9 días** de tokens y contexto tirados, en los dos runtimes CLI, y el único síntoma fue un `WARNING` entre miles. Es el falso verde perfecto: el sistema "funciona", solo que gastando el doble.

### E2 — Dos `NameError` vivos hoy, ambos tragados

Tipos de excepción de `stacky-2026-07-26.log` (agregado):

```
4 NameError: name 'ado_id' is not defined
1 NameError: name 'data_dir' is not defined
```

Tracebacks agregados del mismo log:

```
4  File "...\backend\api\agents.py", line N, in run_incident_dev
1  File "...\backend\app.py", line N, in _worker
```

**Bug A — `Stacky Agents/backend/api/agents.py:1253`:**

```python
1251:        # `ado_id` se capturó DENTRO de la sesión; tocar `ticket` acá daría
1252:        # DetachedInstanceError porque la sesión ya está cerrada.
1253:        _inc = _istore.find_by_tracker_id(ado_id)   # NameError
```

El nombre correcto es **`ticket_ado_id`** (`api/agents.py:1130`). La única asignación de `ado_id` está en el **cuerpo de una clase** (`api/agents.py:1135`), y los bindings de class-body **no son visibles** desde el scope de la función que la contiene:

```python
1130:        ticket_ado_id = ticket.ado_id
1134:    class _TicketSnapshot:
1135:        ado_id = ticket_ado_id      # atributo de clase, NO local de run_incident_dev
```

Lo tapa el `except Exception` de `api/agents.py:1256` con **`logger.info`**, y el endpoint **igual devuelve 202**. El operador lanza el resolutor de incidencias, ve "aceptado", y la vinculación con la incidencia nunca ocurrió. Nivel de log de un bug que rompe una feature: `info`.

**Bug B — `Stacky Agents/backend/services/telemetry_harvest.py:503`:**

```python
502: def _ledger_path() -> Path:
503:     return Path(data_dir()) / "telemetry_harvest.jsonl"   # NameError
```

El módulo nunca importa `data_dir` (los imports son `json, logging, os, dataclass, datetime, Path`, líneas 23-28; el único import de `runtime_paths` es local en la línea 538 y trae `projects_dir, repo_root`). La traza sale bajo `_worker` porque `app.py:246-259` llama `th.append_to_ledger(...)` → `_ledger_path()` (usado en `telemetry_harvest.py:588`, `:606`, y `read_ledger_keys` en `:508`). Lo traga `except Exception` + `logger.exception` en `app.py:263-264`. **El ledger de cosecha de telemetría nunca se escribe.** Fix: `from runtime_paths import data_dir`.

Fue el **único** hit del scan AST de nombres indefinidos en todo el backend además del bug A — o sea que el censo es exhaustivo, no muestral.

### E3 — Un `except` que se comió 1016 fallos en dos días

Firma agregada:

```
854 WARNING [stacky_agents.services.ado_edit_learning] sweep_recent_runs: error general:
    cannot import name 'Execution' from 'models' (C:\desa...)
162 WARNING [...mismo...] (N:\GIT\...)
```

**1016 ocurrencias**, en `stacky-2026-07-15.log` (829) y `stacky-2026-07-16.log` (187).

El import **ya está arreglado** en el árbol — `Stacky Agents/backend/services/ado_edit_learning.py:259` dice hoy `from models import AgentExecution` (el nombre real, `models.py:248`). **Pero el mecanismo que lo hizo invisible sigue intacto:**

```python
# services/ado_edit_learning.py:322-325
    except Exception as exc:
        logger.warning("sweep_recent_runs: error general: %s", exc)

    return new_lessons
```

Un `ImportError` — un fallo **estructural**, no transitorio — cae en ese `except`, se loguea como `warning`, y la función **devuelve `0` lecciones aparentando éxito**. Durante dos días el aprendizaje de ediciones ADO estuvo apagado y el sistema reportaba normalidad. Hay un segundo `except Exception` por work-item en `ado_edit_learning.py:319-320`, también a `warning`.

**Este plan no está para re-arreglar el import** (ya está). Está para que la próxima vez el log **grite** en vez de susurrar.

### E4 — El censo: cuánto del backend falla en silencio

Medido sobre `Stacky Agents/backend`, excluyendo `.venv`, `venv`, `tests`, `__pycache__`:

| | Patrón | Conteo |
|---|---|---|
| **B1** | `except Exception[...]:` seguido de `pass` — **cero** logging | **97** |
| **B2** | `except Exception` → `logger.warning` / `info` / `debug` | **~100** |
| **B3** | `except Exception` → `logger.error` / `exception` | **~60** |
| ref | `except Exception` totales en el backend | **1244** |

Relación **B1 : B2 : B3 = 97 : 100 : 60** → de los 257 bloques con disposición identificable, **el 77 % falla en silencio o subreportado**; solo **1 de cada 4** llega a `error`. Y de los 1244 `except Exception` totales, ~79 % no matchea ninguno de los tres patrones en 4 líneas: el techo real de opacidad es **peor** que 97.

**Las 12 ubicaciones B1 más peligrosas** (todas `archivo:línea` verificadas):

| # | Ubicación | Por qué importa |
|---|---|---|
| 1 | `services/console_log_handler.py:72` | **El sink de logs de la UI traga excepciones.** Ceguera de segundo orden: si el logging falla, no hay log de que el logging falló. |
| 2 | `services/acceptance_contract.py:303` | **Gate de aceptación** tragando → riesgo directo de falso verde. |
| 3 | `services/acceptance_gate.py:101` | Ídem. |
| 4 | `services/claude_code_cli_runner.py:242` | Camino caliente del runtime. |
| 5 | `services/claude_code_cli_runner.py:1913` | Ídem. |
| 6 | `services/claude_code_cli_runner.py:2079` | Ídem. |
| 7 | `services/codex_cli_runner.py:455` | A **33 líneas** del `resume.resolve` de E1. |
| 8 | `services/codex_cli_runner.py:1561` | Camino caliente. |
| 9 | `api/tickets.py:4334` | Endpoint principal. |
| 10 | `api/tickets.py:5048` | Ídem. |
| 11 | `api/qa_uat.py:1283` | Agente QA/UAT. |
| 12 | `api/global_config.py:574` | Config del operador. |

Peores archivos por densidad de B1: `services/claude_code_cli_runner.py` (9), `api/qa_uat.py` (8), `services/gitlab_provider.py` (7), `services/codex_cli_runner.py` (6), `project_manager.py` (6), `api/tickets.py` (6), `services/mantis_client.py` (5), `api/global_config.py` (5).

---

## 3. Principios y guardarraíles (obligatorios)

- **No convertir robustez en fragilidad.** Muchos de esos 97 `pass` son **correctos**: telemetría best-effort, limpieza en `finally`, `proc.kill()` sobre un proceso ya muerto. Este plan **no** los transforma en `raise`. Los hace **contables y visibles**, y sube a `error` solo los del camino caliente donde el silencio ya causó un incidente documentado.
- **Human-in-the-loop:** el gate de F4 **avisa**, no bloquea el trabajo del operador. Es un test del arnés, no un pre-commit hook que le trabe un commit.
- **Paridad de 3 runtimes:** F1 (resume) arregla Codex CLI y Claude Code CLI, que son los dos que usan resume; Copilot Pro no tiene sesión reanudable y se declara su fallback. F3 y F4 son transversales.
- **Mono-operador sin auth.**
- **Cero trabajo extra al operador:** todo es invisible salvo un contador nuevo en el panel de diagnóstico que ya existe.
- **No degradar:** el ratchet de F4 **congela** el número actual (97) en vez de exigir bajarlo a 0. No se rompe el repo por deuda preexistente. Gotcha conocido de este repo: un ratchet que exige más de lo alcanzable queda rojo por deuda ajena y se vuelve ruido que nadie mira.
- **Flags default ON**, ninguna en las 4 excepciones duras.
- **Toda flag configurable desde la UI.**

---

## 4. Fases

### F0 — Los 3 bugs mudos, con test que los reproduce

**Objetivo:** cerrar hoy los tres defectos probados. Es el fix chico y evidente; va como F0 y no como plan aparte.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan255_bugs_mudos.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh`.

**Casos exactos:**

1. `test_resume_resolve_con_execution_id_no_explota` — llamar `harness.resume.resolve(...)` **pasando** `execution_id`; asserta que **no** se loguea el warning de arranque en frío y que devuelve la sesión previa. **Hoy falla.**
2. `test_resume_resolve_excluye_la_ejecucion_actual` — con 3 ejecuciones completadas y `execution_id` = la más nueva, el resultado corresponde a la **segunda** más nueva. Verifica que el fix además arregla la **semántica**, no solo la excepción.
3. `test_resume_resolve_sin_execution_id_sigue_funcionando` — no romper el path que hoy sí anda.
4. `test_run_incident_dev_resuelve_el_ado_id` — `POST` al endpoint de `run_incident_dev`; asserta que `find_by_tracker_id` se llamó con el ADO id **correcto** y que no hubo `NameError`. **Hoy falla.**
5. `test_telemetry_harvest_ledger_path_resuelve` — `telemetry_harvest._ledger_path()` devuelve un `Path` bajo `data_dir()` sin `NameError`. **Hoy falla.**
6. `test_telemetry_harvest_append_escribe_el_ledger` — tras `append_to_ledger`, el archivo `telemetry_harvest.jsonl` existe y tiene 1 línea JSON válida. **Hoy falla** (el ledger nunca se escribió).
7. `test_sweep_recent_runs_loguea_importerror_como_error` — inyectar un `ImportError` en `sweep_recent_runs`; asserta que se loguea a nivel **`error`**, no `warning`. **Hoy falla.**

**Los fixes exactos:**

```python
# (A) harness/resume.py:92-102 — mover el filtro condicional ANTES de order_by/limit
q = (db_session.query(AgentExecution)
     .filter(AgentExecution.ticket_id == ticket_id)
     .filter(AgentExecution.agent_type == agent_type)
     .filter(AgentExecution.status == "completed"))
if execution_id is not None:
    q = q.filter(AgentExecution.id != execution_id)     # AHORA, antes del limit
rows = q.order_by(AgentExecution.id.desc()).limit(5).all()

# (B) api/agents.py:1253 — usar el nombre que sí existe en el scope
_inc = _istore.find_by_tracker_id(ticket_ado_id)        # era: ado_id

# (C) services/telemetry_harvest.py — agregar el import faltante (nivel módulo)
from runtime_paths import data_dir

# (D) services/ado_edit_learning.py:322-323 — ImportError/AttributeError son
#     estructurales, no transitorios: van a error, no a warning
    except (ImportError, AttributeError) as exc:
        logger.error("sweep_recent_runs: fallo ESTRUCTURAL (el sweep queda "
                     "inerte hasta arreglarlo): %s", exc)
    except Exception as exc:
        logger.warning("sweep_recent_runs: error general: %s", exc)
```

**Casos borde:**
- Fix (A): el `.filter()` condicional cambia el resultado además de evitar la excepción — hoy devuelve `(None, None)`, con el fix devuelve las 5 más recientes **excluyendo** la actual. Eso **es** la intención original; el test 2 la fija.
- Fix (B): verificar que `ticket_ado_id` esté realmente en scope en la línea 1253 (se asigna en 1130, mismo cuerpo de función). Alternativa válida si el scope cambiara: `_TicketSnapshot.ado_id`.
- Fix (C): cuidado con importaciones circulares — `runtime_paths` no importa `telemetry_harvest`, así que el import a nivel módulo es seguro. Confirmar antes de mover.
- Fix (D): el `except` específico va **antes** del genérico o Python nunca lo alcanza.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan255_bugs_mudos.py -v
```

**Criterio binario:** 7 verdes. Y, en el log del día siguiente al deploy: `grep -c "harness.resume.resolve falló"` = **0**, `grep -c "NameError"` = **0**.

**Flag:** ninguna — son bugs, no features. Un fix de bug detrás de una flag deja el bug vivo por default.
**Impacto por runtime:** (A) beneficia a Claude Code CLI y Codex CLI (los dos con resume). Copilot Pro no usa resume → sin cambio, sin degradación. (B), (C), (D) son transversales.
**Trabajo del operador: ninguno.**

---

### F1 — Instrumentar el silencio: contador de fallos tragados

**Objetivo:** antes de cambiar los 97 `pass`, **medir** cuáles se disparan de verdad. Cambiar a ciegas 97 bloques es cómo se rompe un sistema que funciona.

**Archivo a crear:** `Stacky Agents/backend/services/silent_failure_counter.py` — módulo **puro** salvo un dict en memoria.

**Símbolos nuevos exactos:**

```python
def note_swallowed(site: str, exc: BaseException | None = None) -> None:
    """Plan 255 F1 — registra que un except tragó un fallo, SIN loguear.

    `site` es un identificador estable "modulo.funcion:linea".
    Costo: un incremento de dict. Pensado para llamarse dentro de un
    `except ...: pass` sin cambiar su semántica ni su performance.
    """

def swallowed_report(top: int = 30) -> list[dict]:
    """[{'site','count','last_exc_type','last_seen'}] ordenado por count desc."""

def reset_swallowed() -> None:
    """Solo para tests."""
```

**Aplicación:** en los **12 sitios de la tabla de E4**, el `pass` pasa a:

```python
    except Exception as _e:
        note_swallowed("acceptance_gate.evaluate:101", _e)   # antes: pass
```

**Reglas duras:**
- `note_swallowed` **jamás** levanta. Su cuerpo entero va en un `try/except BaseException: pass`. Si el contador de fallos falla, no puede tumbar el código que estaba protegiendo.
- **No loguea.** Si logueara, los 12 sitios generarían el mismo ruido que el plan 257 va a combatir. Es un contador, se consulta cuando se quiere.
- Cota de memoria: máximo 500 sites distintos; al pasarse, deja de agregar claves nuevas (no crece sin límite).
- **Excepción explícita para el sitio 1** (`services/console_log_handler.py:72`): ese es el sink de logs; ahí `note_swallowed` va con el guard reforzado y sin tocar logging en absoluto, para no crear recursión.

**Exposición:** `GET /api/diag/silent-failures` en `Stacky Agents/backend/api/diag.py`, y una tarjeta en el panel de diagnóstico existente: *"Fallos silenciados (últimas 24 h)"* con las top 10 filas.

**Tests:** `Stacky Agents/backend/tests/test_plan255_silent_failures.py` (agregar al ratchet):
- `test_note_swallowed_incrementa_por_site`
- `test_note_swallowed_nunca_levanta` — pasarle un objeto cuyo `__repr__` explota; no debe propagarse nada.
- `test_swallowed_report_ordena_por_count`
- `test_cota_de_500_sites` — el site 501 no crea clave nueva.
- `test_note_swallowed_no_loguea` — capturar el logger raíz y asserta 0 registros.
- `test_endpoint_diag_devuelve_el_reporte`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan255_silent_failures.py -v
```
6 verdes, y `GET /api/diag/silent-failures` responde `200` con una lista.

**Flag:** `SILENT_FAILURE_COUNTER_ENABLED`, **default ON**. Sin excepción dura: es un dict en memoria, no quema tokens, no toca ninguna base del operador, no reduce seguridad.
**Impacto por runtime:** transversal, los 3 igual.
**Trabajo del operador: ninguno** (mira la tarjeta si quiere).

---

### F2 — Subir a `error` los `except` que ya causaron un incidente

**Objetivo:** que un fallo **estructural** (import, atributo, tipo) no pueda volver a esconderse detrás de un `warning`.

**Regla de clasificación (determinística, sin criterio del implementador):**

| Tipo de excepción | Nivel | Razón |
|---|---|---|
| `ImportError`, `ModuleNotFoundError`, `AttributeError`, `NameError`, `TypeError` | **`error`** | Son **bugs de código**. No se arreglan solos y no son transitorios. E3 probó el costo: 1016 ocurrencias silenciadas. |
| `OperationalError`, `TimeoutError`, `ConnectionError`, `OSError` | `warning` | Transitorios. El reintento del plan 253 los cubre. |
| Todo lo demás | como está hoy | No tocar sin evidencia. |

**Los 6 sitios exactos a modificar** (elegidos porque los logs prueban que tragaron algo real):

1. `services/ado_edit_learning.py:322-323` — ya en F0 (D). Es el caso de referencia.
2. `services/ado_edit_learning.py:319-320` — el `except` por work-item, mismo tratamiento.
3. `api/agents.py:1256` — el que tragó el `NameError` de F0 (B) con `logger.info`. Pasa a `logger.error` para `NameError`/`AttributeError`.
4. `app.py:263-264` — el que tragó el `NameError` de F0 (C). Ya usa `logger.exception`; **verificar** que no esté anidado en otro `except` que lo re-tragase.
5. `harness/resume.py:136-138` — el del resume muerto. `logger.warning` → `error` para `InvalidRequestError`/`AttributeError`, y **agregar `note_swallowed`** para que el contador lo cuente incluso si el nivel bajara.
6. `services/console_log_handler.py:72` — el `pass` del sink de logs. **No** se convierte en logging (recursión); se le pone `note_swallowed` con guard reforzado (ya viene de F1) y se documenta con un comentario de 2 líneas explicando por qué acá el silencio es correcto.

**Helper compartido, símbolo exacto** en `Stacky Agents/backend/services/silent_failure_counter.py`:

```python
_STRUCTURAL = (ImportError, ModuleNotFoundError, AttributeError, NameError, TypeError)

def log_level_for(exc: BaseException) -> str:
    """'error' si es un bug estructural, 'warning' si es transitorio."""
    return "error" if isinstance(exc, _STRUCTURAL) else "warning"
```

**Casos borde:**
- Un `TypeError` que viene de datos malos del operador (no de un bug) subiría a `error` incorrectamente. Aceptable: es mejor un `error` de más que 1016 `warning` invisibles. Y el plan 257 le pone throttle al volumen.
- Sitios donde `error` dispararía una alerta al operador por algo que no puede arreglar: no hay sistema de alertas al operador por nivel de log en Stacky, así que el riesgo es nulo hoy.

**Tests:** en `test_plan255_silent_failures.py`:
- `test_log_level_for_estructural_es_error` — los 5 tipos.
- `test_log_level_for_transitorio_es_warning` — `OperationalError`, `TimeoutError`, `ConnectionError`.
- `test_resume_importerror_loguea_error_y_cuenta` — sube a `error` **y** aparece en `swallowed_report`.
- `test_console_log_handler_no_loguea_al_tragar` — blinda contra la recursión.

**Criterio binario:** 4 verdes + `grep -c "log_level_for" services/ api/ harness/` ≥ 5.

**Flag:** `STRUCTURAL_ERRORS_TO_ERROR_LEVEL`, **default ON**. Sin excepción dura.
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F3 — Ratchet de silencio: que no entre uno nuevo

**Objetivo:** congelar la deuda en su nivel actual y exigir justificación explícita para cada `pass` nuevo.

**Archivos a crear:**
1. `Stacky Agents/backend/tests/test_plan255_silence_ratchet.py` — el meta-test.
2. `Stacky Agents/backend/tests/silence_ratchet_baseline.json` — el baseline congelado.

**Diseño (con las lecciones de los ratchets que este repo ya tiene):**

```python
# El baseline es un DICT archivo → conteo, no un número global.
# {"services/claude_code_cli_runner.py": 9, "api/qa_uat.py": 8, ...}
#
# El test falla SOLO si un archivo SUBE su conteo respecto del baseline.
# Bajar está permitido y NO exige regenerar (evita el gotcha de ratchets
# que se ponen rojos por deuda ajena de otra rama).
```

**Reglas duras (todas son lecciones de ratchets previos de este repo):**
- **Detección por AST, nunca por regex.** Un regex sobre `except Exception` es destructivo y da falsos positivos (ya pasó en este repo con un centinela textual de flags). Usar `ast.walk` buscando `ast.ExceptHandler` cuyo `body` sea exactamente `[ast.Pass()]`.
- **Escape hatch explícito:** un `# silence-ok: <motivo>` en la línea del `except` lo excluye del conteo. Obliga a **escribir el motivo**, que es el punto.
- **Baseline por archivo, no global:** si otra rama agrega deuda en un archivo ajeno, tu archivo no se pone rojo.
- **Bajar no exige regenerar:** el test compara `actual <= baseline`, no `actual == baseline`.
- **El propio archivo de test se autoexcluye** del escaneo, y `tests/` completo también.
- **Cuidado con el auto-gate:** el archivo del test contiene el string `except Exception` en su documentación; el escaneo debe correr sobre el AST de los archivos **objetivo**, nunca sobre sí mismo (gotcha recurrente de este repo: la prosa de un plan choca con su propio grep-gate).

**Baseline inicial exacto:** el conteo medido hoy, **97 total** distribuido por archivo, con los peores ya conocidos: `services/claude_code_cli_runner.py`: 9, `api/qa_uat.py`: 8, `services/gitlab_provider.py`: 7, `services/codex_cli_runner.py`: 6, `project_manager.py`: 6, `api/tickets.py`: 6, `services/mantis_client.py`: 5, `api/global_config.py`: 5. Generar el resto con el script del propio test.

**Casos borde:**
- Archivo nuevo sin entrada en el baseline: su límite implícito es **0**. Un archivo nuevo no puede nacer con deuda muda.
- Archivo renombrado: el baseline pierde la entrada y el archivo nuevo arranca en 0 → el test se pone rojo. **Es correcto**: renombrar es una oportunidad de limpiar. Documentar cómo regenerar.
- `except Exception: pass` en una línea (`except Exception: pass`): el AST lo ve igual que la versión multilínea. Verificar con un test.

**Tests del propio ratchet** (dentro del mismo archivo):
- `test_ratchet_detecta_pass_en_una_linea`
- `test_ratchet_respeta_silence_ok`
- `test_ratchet_archivo_nuevo_arranca_en_cero`
- `test_ratchet_permite_bajar_sin_regenerar`
- `test_ratchet_no_se_escanea_a_si_mismo`
- `test_baseline_actual_es_verde` — el estado de hoy pasa. **Si esto falla, el baseline está mal generado, no el repo mal.**

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan255_silence_ratchet.py -v
```
6 verdes **con el repo tal como está**. Y agregar a mano un `except Exception: pass` en `api/tickets.py` lo pone rojo; agregarle `# silence-ok: proceso ya muerto` lo pone verde de nuevo.

**Flag:** ninguna (es un test del arnés, no runtime).
**Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Convertir `pass` correctos en `raise` rompe el sistema** — riesgo #1 | Este plan **no convierte ningún `pass` en `raise`**. F1 solo cuenta, F2 sube el **nivel de log** de 6 sitios con incidente documentado, F3 congela. Ni un cambio de flujo de control. |
| El fix del resume (F0-A) cambia la semántica del query, no solo la excepción | Es intencional y está fijado por `test_resume_resolve_excluye_la_ejecucion_actual`. Documentar en el commit: antes devolvía `(None, None)`, ahora devuelve las 5 excluyendo la actual. |
| Subir a `error` inunda el log | El plan 257 (throttle + dedup) es el complemento. Implementar 255 **antes** de 257 y medir; si el volumen sube, 257 lo absorbe. Se acepta el orden porque un `error` visible es mejor que un bug invisible. |
| El ratchet se pone rojo por deuda de otra rama | Baseline **por archivo** + comparación `<=`. Es exactamente el gotcha que este repo ya sufrió con otros ratchets. |
| `note_swallowed` agrega overhead en el camino caliente | Un `dict[str] += 1`. Está solo en 12 sitios, todos en paths de fallo (no en el happy path). |
| Recursión de logging en `console_log_handler` | Ese sitio **no** loguea nunca; solo `note_swallowed` con guard `BaseException`. Test dedicado. |
| El fix del import en `telemetry_harvest` crea un ciclo | Verificado: `runtime_paths` no importa `telemetry_harvest`. Confirmar con `python -c "import telemetry_harvest"` antes de cerrar la fase. |

---

## 6. Fuera de scope

- Refactorizar los 1244 `except Exception` del backend. Este plan mide, congela y arregla los 6 con incidente probado.
- Reemplazar `except Exception` por excepciones específicas en todo el repo. Trabajo enorme, retorno difuso.
- Los locks de SQLite que producen `OperationalError` → **plan 253**.
- El ruido de log y el throttle → **plan 257**.
- La contaminación de los ledgers JSONL con datos de test → **plan 258**.
- El falso rojo del cierre de corridas → **plan 254**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Falla muda** | Un fallo que ocurre, se maneja, y no deja rastro consultable (o lo deja a un nivel que nadie mira). |
| **`except Exception: pass`** | El caso extremo: se atrapa cualquier fallo y no se hace nada. 97 en este backend. |
| **Fallo estructural** | Bug de código (import, atributo, nombre, tipo). No se arregla solo, no es transitorio → merece `error`. |
| **Fallo transitorio** | Lock, timeout, red. Se arregla reintentando → merece `warning`. |
| **`resume`** | Mecanismo que reanuda una sesión de agente previa en vez de arrancar en frío, ahorrando tokens y contexto. `backend/harness/resume.py`. |
| **Ratchet** | Meta-test que congela una métrica de deuda y falla si empeora. Este repo ya tiene varios (`uiDebtRatchet`, ratchet de cobertura del arnés). |
| **Baseline por archivo** | El ratchet guarda un conteo por archivo, no un total, para que la deuda de otra rama no ponga rojo tu archivo. |
| **AST** | *Abstract Syntax Tree*. Analizar código parseándolo, no con regex. Obligatorio acá: un regex sobre `except` da falsos positivos. |
| **`# silence-ok: <motivo>`** | Marca que excluye un `pass` del ratchet obligando a escribir por qué el silencio es correcto ahí. |

---

## 8. Orden de implementación

1. **F0** — los 7 tests, rojos; después los 4 fixes (A, B, C, D). **El fix (A) del resume es el de mayor retorno económico del portafolio**: devuelve el ahorro de tokens de cada corrida.
2. Verificar en vivo: correr un ticket con `execution_id` y confirmar que el log **no** dice `arranque en frío`.
3. **F1** — `services/silent_failure_counter.py` + los 12 sitios + endpoint de diagnóstico + tarjeta en la UI.
4. **Dejar corriendo F1 unos días** y leer `swallowed_report`. Los sitios con `count == 0` no necesitan nada más: son `pass` legítimamente inertes.
5. **F2** — subir a `error` los 6 sitios, usando `log_level_for`.
6. **F3** — ratchet por AST + baseline por archivo generado del estado real.
7. Exponer las 2 flags nuevas en el panel de flags y en `api/global_config.py`.
8. Registrar los 3 archivos de test nuevos en `HARNESS_TEST_FILES`.

---

## 9. Definición de Hecho (DoD)

- [ ] `harness/resume.py` aplica el `.filter()` condicional **antes** de `order_by`/`limit`.
- [ ] `grep -c "harness.resume.resolve falló"` sobre el log del día = **0**.
- [ ] `api/agents.py:1253` usa `ticket_ado_id`; `run_incident_dev` vincula la incidencia de verdad.
- [ ] `services/telemetry_harvest.py` importa `data_dir` y `telemetry_harvest.jsonl` se escribe.
- [ ] `grep -c "NameError"` sobre el log del día = **0**.
- [ ] `ImportError`/`AttributeError` en `sweep_recent_runs` se loguean a **`error`**.
- [ ] `note_swallowed` está en los 12 sitios de la tabla E4 y **nunca** levanta ni loguea.
- [ ] `GET /api/diag/silent-failures` responde y la tarjeta se ve en el panel de diagnóstico.
- [ ] El ratchet de silencio está **verde con el repo como está** y se pone rojo al agregar un `pass` sin `# silence-ok`.
- [ ] El ratchet usa **AST**, no regex, y no se escanea a sí mismo.
- [ ] Los 3 archivos de test nuevos están en `HARNESS_TEST_FILES`.
- [ ] Las 2 flags nuevas se cambian **desde la UI**.
- [ ] Ningún `pass` se convirtió en `raise`; cero cambios de flujo de control.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**).
