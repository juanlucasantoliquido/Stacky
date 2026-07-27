# Plan 255 — Cero fallas mudas: excepciones tragadas y el `resume` muerto

**Estado:** CRITICADO v2
**Versión:** v1 -> v2 (juez adversarial + arquitecto; ver CHANGELOG en §0)
**Serie:** Robustez desde los logs (253-258). Plan **#3 por retorno**.
**Fuente:** auditoría de ~16 MB de logs reales + **censo AST re-medido en v2** (el de v1 estaba mal).

> La auditoría encontró tres bugs que llevan **días o semanas** funcionando mal sin que nadie se enterase, y los tres tienen la misma causa estructural: **una parte enorme de los fallos manejados del backend se reporta por debajo de su gravedad real, o no se reporta en absoluto**. El caso más caro: el mecanismo de `resume` de sesiones está **muerto desde el 2026-07-17** y quema tokens en cada corrida, mientras el log dice solamente `WARNING`.

---

## 0. CHANGELOG v1 -> v2

Todo lo de abajo se corrigió contra el árbol real (comandos re-corridos hoy, no memoria).

- **C1 (BLOQUEANTE) — El censo B1 estaba MAL medido y el baseline de F3 nacía rojo.** v1 decía **97**; la regla AST que el propio plan exige (`ast.ExceptHandler` con `body == [ast.Pass()]`, excluyendo `.venv/venv/tests/__pycache__`) da **165** para `except Exception|BaseException` y **207** contando cualquier handler. La tabla por archivo también estaba mal (`claude_code_cli_runner.py` 14 real vs 9 declarado; `api/tickets.py` 10 vs 6; `codex_cli_runner.py` 10 vs 6) y **omitía** `services/harness_health.py` (7). Corregido en §2/E4 y en la tabla de KPI, con la regla exacta que produjo cada número.
- **C2 (BLOQUEANTE) — F1 gameaba el gate de F3.** Poner `note_swallowed` donde había `pass` hace que `body != [Pass()]` y el sitio **deja de contar**: el ratchet bajaba 12 por instrumentar, sin arreglar nada. F3 ahora clasifica **dos** buckets y congela el total.
- **C3 (BLOQUEANTE) — El test 1 de F0 era un generador de falso verde.** `resolve()` tiene **cuatro** salidas tempranas antes del query roto (una es el gate de flags). Asertar "no se loguea el warning" pasa HOY si el gate corta antes. Reescrito: el criterio es el **valor de retorno**, con fixture literal y un test-guardia que prueba que el rojo de hoy es el rojo correcto.
- **C4 (BLOQUEANTE) — `# silence-ok:` era indetectable con la regla del propio plan.** El AST descarta comentarios. Nombrado el mecanismo exacto: `tokenize.COMMENT` (nivel token, no regex).
- **C5 (BLOQUEANTE) — El paso "dejar corriendo F1 unos días" era inejecutable:** contador en RAM + backend que reinicia varias veces por día. Ahora el reporte declara su ventana y hay una regla anti-conclusión escrita.
- **C6 (BLOQUEANTE) — F0(A) no "recupera tokens": ENCIENDE un camino muerto.** Las flags de resume ya están **default ON** para **todos** los proyectos; lo que nunca corrió en 9 días es el camino de éxito. Agregado rollout escalonado con el kill-switch que **ya existe**, cota al delta y verificación en vivo.
- **C7 (IMPORTANTE) — KPI inalcanzable ("100% → 0%" de arranque en frío)** reemplazado por dos KPIs medibles, uno de ellos la prueba directa de que el camino revivió.
- **C8 (IMPORTANTE) — Faltaba la huella de regresión.** Nueva **F5** que registra las 3 clases en `docs/sistema/error_fingerprints.json` con el contrato real del catálogo.
- **C9 (IMPORTANTE) — Frontera viva con el plan 257 sin declarar** (toca las MISMAS líneas). Nueva §8.1 con el orden obligatorio.
- **C10 (IMPORTANTE) — `TypeError` en `_STRUCTURAL` iba a inundar** y la mitigación citada era un plan inexistente. Sacado de `_STRUCTURAL` con el motivo escrito.
- **C11 (IMPORTANTE) — Anclajes por `archivo:línea` con sesión paralela viva** editando 2 de esos archivos. Todos los sitios reanclados por **función + snippet literal**.
- **C12 (IMPORTANTE) — F3 no decía quién escanea y el baseline era circular.** Reusa el patrón que la casa ya tiene (`provider_coupling_audit` + baseline JSON + ratchet), con comando de regeneración separado.
- **C13 (IMPORTANTE) — El test 7 no era ejecutable** (el `import` vive dentro de una rama condicional). Reescrito con el mecanismo de inyección exacto.
- **C14 (IMPORTANTE) — Alta de flags incompleta.** Nueva **F4** con los 4 lugares reales; `api/global_config.py` **no** es el panel de flags.
- **C15..C19 (MENORES)** — decorador real de `api/diag.py`, rename que no debe ensuciar el ratchet, criterios `grep` frágiles, `caplog` que verdea al vacío, y el prefijo de flags `STACKY_`.
- **[ADICIÓN ARQUITECTO]** — Nueva **F6: canario de features dormidas**. Es la generalización del hallazgo central: el resume estuvo 9 días muerto porque **nadie mide que un camino feliz se haya ejecutado**.

---

## 1. Objetivo y KPI

Convertir el silencio en señal: arreglar los 3 bugs mudos concretos que la auditoría probó, instalar el **gate estructural** que impide que un `except Exception: pass` nuevo entre sin justificación, y dejar un **canario** que avise cuando un mecanismo caro se muere sin ruido.

| KPI | Hoy (medido) | Meta | Cómo se mide |
|---|---|---|---|
| `harness.resume.resolve falló (arranque en frío)` | **50** ocurrencias, 07-17 a 07-26 | **0** | `grep -c` sobre el log del día siguiente al deploy |
| **Corridas con resume EFECTIVO** (`resume …: sesión previa=` en el log) | **0** en 9 días | **≥ 1 en 24 h** | prueba directa de que el camino muerto revivió (C7) |
| `NameError` en producción, por firma de traceback | **5** el 2026-07-26 (2 bugs) | **0** | ver §9, criterio anclado (C17) |
| **B1a** — `except Exception\|BaseException` con `body == [Pass()]` | **165** | **≤ 165 congelado por archivo** | `python -m services.silence_audit` |
| **B1b** — cualquier `except` con `body == [Pass()]` | **207** | informativo (no congelado) | ídem |
| **Mudos totales** = `Pass` **o** solo `note_swallowed` | **165** | **≤ 165** (no baja por instrumentar) | anti-gaming de C2 |
| Fallos estructurales (`ImportError`/`AttributeError`/`NameError`) que llegan a nivel `error` | 0 de los 3 sitios probados | **3 de 3** | test de F2 |
| Clases de error de este plan registradas como huella | **0** | **3** | `tests/test_error_fingerprints_catalog.py` verde con las 3 nuevas |

> **Nota de honestidad (C7):** el KPI de v1 *"corridas que arrancan en frío teniendo sesión previa: 100 % → 0 %"* se **eliminó**. Aunque el query funcione, `resolve` devuelve `(None, None)` de forma legítima cuando el gate de flags está off, cuando `ticket_id` es falsy, o cuando ninguna fila tiene `metadata["runtime"] == runtime` **y** un `session_id` bajo la clave del runtime. Una primera corrida sobre un ticket arranca en frío y está **bien**. Un KPI inalcanzable pudre toda la tabla.

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

**El código culpable — `Stacky Agents/backend/harness/resume.py`, función `resolve` (def en `harness/resume.py:47`), bloque anclado por el snippet `.limit(5)` seguido de `if execution_id is not None:`:**

```python
            query = (
                db_session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == ticket_id)
                .filter(AgentExecution.agent_type == agent_type)
                .filter(AgentExecution.status == "completed")
                .order_by(AgentExecution.id.desc())
                .limit(5)                                        # LIMIT aplicado acá
            )
            if execution_id is not None:
                query = query.filter(AgentExecution.id != execution_id)   # BUG
            rows = query.all()
```

SQLAlchemy 2.0.36 prohíbe `.filter()` después de `.limit()`. **Consecuencia:** cada vez que se pasa `execution_id` — que es el caso normal — el query revienta, lo atrapa el `except Exception as exc` final de `resolve` (anclado por el snippet `logger.warning("harness.resume.resolve falló (arranque en frío): %s", exc)`), y devuelve `None, None`. El runner lo interpreta como "no hay nada que reanudar" y **arranca de cero**.

Los call-sites también lo tragan a nivel warn:
- `Stacky Agents/backend/services/claude_code_cli_runner.py`, función `_resolve_resume`, snippet `log("warn", f"no se pudo resolver --resume (arranque en frío): {exc}")`.
- `Stacky Agents/backend/services/codex_cli_runner.py`, bloque `# H7.1 — Re-run con exec resume`, snippet `log("warn", f"codex resume resolve falló (arranque en frío): {_resume_exc}")`.

#### E1-bis — Lo que de verdad está apagado (medición nueva de v2, corrige C6)

`resolve()` tiene **cuatro salidas tempranas antes del query roto**, y la tercera es un gate de flags:

| # | Guarda | Efecto |
|---|---|---|
| 1 | `runtime not in CAPABILITIES` | `raise ValueError` |
| 2 | `not cap.supports_resume` | `return None, None` |
| 3 | `not _resume_flag_enabled(runtime, project)` | `return None, None` |
| 4 | `not ticket_id` | `return None, None` |

`_resume_flag_enabled` lee el par declarado en `_RESUME_FLAG` de `harness/resume.py`:

```python
_RESUME_FLAG: dict[str, tuple[str, str]] = {
    "claude_code_cli": ("CLAUDE_CODE_CLI_RESUME_ENABLED", "CLAUDE_CODE_CLI_RESUME_PROJECTS"),
    "codex_cli": ("CODEX_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_PROJECTS"),
}
```

y resuelve con `services/cli_feature_flags.project_enabled(enabled=..., projects_csv=..., project_name=...)`, cuyo contrato documentado es: **`enabled` False → siempre False; allowlist vacía → True (master ON aplica a todos)**.

**Medido en `backend/config.py`:** `CODEX_CLI_RESUME_ENABLED` default `"true"`, `CODEX_CLI_RESUME_PROJECTS` default `""`; `CLAUDE_CODE_CLI_RESUME_ENABLED` default `"true"`, `CLAUDE_CODE_CLI_RESUME_PROJECTS` default `""`.

⇒ **Las flags están ON para todos los proyectos, en los dos runtimes.** El gate no corta, el query se alcanza, y explota. Por lo tanto:

- Lo que **NO** está apagado: la feature (está prendida y el operador cree que funciona).
- Lo que **SÍ** lleva 9 días sin ejecutarse ni una vez: el **camino de éxito** — el loop `for row in rows`, la resolución de `prev_session_id`, la construcción del `delta_prefix` vía `services.delta_prompt`, `_build_resume_command(...)` en el runner de codex y el `--resume` en el de claude.

**Esto NO es "recuperar tokens". Es reactivar de golpe tres caminos que nadie ejercitó en 9 días, para todos los proyectos a la vez.** Riesgos concretos: `session_id` caducado del CLI, resume contra una conversación equivocada, `delta_prefix` gigante inyectado al prompt. F0 lo trata como un encendido con rollout, no como un parche cosmético (§4/F0, casos borde y rollout).

**Costo real del bug:** cada corrida que podía reanudar sesión + delta arranca en frío. Son **9 días** de tokens y contexto tirados, en los dos runtimes CLI, y el único síntoma fue un `WARNING` entre miles.

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

**Bug A — `Stacky Agents/backend/api/agents.py`, función `run_incident_dev`**, anclado por el snippet `_inc = _istore.find_by_tracker_id(ado_id)` (hay UNA sola ocurrencia en el archivo):

```python
        # `ado_id` se capturó DENTRO de la sesión; tocar `ticket` acá daría
        # DetachedInstanceError porque la sesión ya está cerrada.
        _inc = _istore.find_by_tracker_id(ado_id)   # NameError
```

El nombre correcto es **`ticket_ado_id`**, asignado en el **mismo cuerpo de función**, snippet `ticket_ado_id = ticket.ado_id`. La única asignación de `ado_id` está en el **cuerpo de una clase** (`class _TicketSnapshot:` → `ado_id = ticket_ado_id`), y los bindings de class-body **no son visibles** desde el scope de la función que la contiene. Verificado en v2: `ticket_ado_id` sí está en scope en la línea del bug.

Lo tapa un `except Exception:  # noqa: BLE001 — best-effort` con **`logger.info`**, y el endpoint **igual devuelve 202**. El operador lanza el resolutor de incidencias, ve "aceptado", y la vinculación con la incidencia nunca ocurrió. Nivel de log de un bug que rompe una feature: `info`.

**Bug B — `Stacky Agents/backend/services/telemetry_harvest.py`, función `_ledger_path`:**

```python
def _ledger_path() -> Path:
    return Path(data_dir()) / "telemetry_harvest.jsonl"   # NameError
```

**Verificado en v2:** el módulo importa `json, logging, os, dataclass, datetime, timezone, Path` y **no importa `data_dir`**; el único import de `runtime_paths` es **local** dentro de otra función y trae `projects_dir, repo_root`. `runtime_paths.data_dir` sí existe. La traza sale bajo `_worker` porque el thread `plan199-harvest` de `app.py` llama `th.append_to_ledger(...)` → `_ledger_path()`.

**Condición de alcance (dato que v1 omitía):** ese `_worker` está gateado por tres guardas en `app.py`: `STACKY_TEST_MODE` (env, no `config`), `config.STACKY_TELEMETRY_HARVEST_ENABLED` y `config.STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED`. **Medido:** ambas flags son **default `"true"`** en `config.py`, así que la ruta se alcanza en la configuración de fábrica y el `NameError` del log lo confirma. La afirmación correcta es: **con la configuración por defecto, el ledger de cosecha nunca se escribe.** Lo traga un `except Exception` + `logger.exception` en `app.py`. Fix: `from runtime_paths import data_dir` a nivel módulo.

Fue el **único** hit del scan AST de nombres indefinidos en todo el backend además del bug A — o sea que el censo es exhaustivo, no muestral.

### E3 — Un `except` que se comió 1016 fallos en dos días

Firma agregada:

```
854 WARNING [stacky_agents.services.ado_edit_learning] sweep_recent_runs: error general:
    cannot import name 'Execution' from 'models' (C:\desa...)
162 WARNING [...mismo...] (N:\GIT\...)
```

**1016 ocurrencias**, en `stacky-2026-07-15.log` (829) y `stacky-2026-07-16.log` (187).

El import **ya está arreglado** en el árbol — `services/ado_edit_learning.py` dice hoy `from models import AgentExecution` (el nombre real). **Pero el mecanismo que lo hizo invisible sigue intacto**, en `sweep_recent_runs`, anclado por el snippet `logger.warning("sweep_recent_runs: error general: %s", exc)`:

```python
    except Exception as exc:
        logger.warning("sweep_recent_runs: error general: %s", exc)

    return new_lessons
```

Un `ImportError` — un fallo **estructural**, no transitorio — cae en ese `except`, se loguea como `warning`, y la función **devuelve `0` lecciones aparentando éxito**. Durante dos días el aprendizaje de ediciones ADO estuvo apagado y el sistema reportaba normalidad. Hay un segundo `except Exception` por work-item en la misma función, anclado por `logger.warning("sweep_recent_runs: error en WI %s (no crítico): %s", ado_id, exc)`, también a `warning`.

**Dato nuevo de v2 (corrige C13):** el `from models import AgentExecution` vive **dentro** de la rama `if _db_runs is None:` del `try`. Un test que pase `_db_runs=[...]` **nunca alcanza el import** y verdea sin probar nada. El mecanismo de inyección está escrito literal en F0, caso 7.

**Este plan no está para re-arreglar el import** (ya está). Está para que la próxima vez el log **grite** en vez de susurrar.

### E4 — El censo: cuánto del backend falla en silencio (RE-MEDIDO en v2)

**Comando exacto que produjo estos números** (script determinista, sin regex, excluyendo `.venv`, `venv`, `tests`, `__pycache__`, `node_modules`, sobre `Stacky Agents/backend`):

```
python -m services.silence_audit          # lo crea F3; mientras tanto, el mismo AST a mano
```

Regla: `ast.walk` → `ast.ExceptHandler` con `len(body) == 1 and isinstance(body[0], ast.Pass)`.

| | Patrón | v1 declaraba | **v2 MEDIDO** |
|---|---|---|---|
| **B1a** | `except Exception\|BaseException` + `body == [Pass()]` | 97 | **165** |
| **B1b** | **cualquier** `except` + `body == [Pass()]` | — | **207** |
| B2 | `except Exception` → `logger.warning/info/debug` | ~100 | ~100 (ventana de 4 líneas, aproximado) |
| B3 | `except Exception` → `logger.error/exception` | ~60 | ~60 (ídem) |
| ref | `except Exception` totales en el backend | 1244 | 1244 |

> **Por qué v1 daba 97:** ese número salió de un grep con ventana de 4 líneas (`except Exception...:` seguido de `pass`), que **pierde** los handlers con un comentario o una línea en blanco intercalada y los de forma tupla/aliasada. **El propio plan prohíbe el regex y exige AST** — o sea que v1 fijaba el baseline con el método que él mismo prohíbe, y `test_baseline_actual_es_verde` habría nacido **rojo** en al menos 4 archivos. B2/B3 quedan marcados como aproximados porque siguen viniendo de la ventana de grep; **no se congelan** y no aparecen en el KPI.

**Ubicaciones B1a más peligrosas — re-medidas y reancladas por FUNCIÓN + snippet (C11).** Los números de línea son **pista, no ancla**: hay una sesión paralela viva editando `claude_code_cli_runner.py` y `codex_cli_runner.py`.

| # | Archivo | Ancla (función / snippet único del `try`) | Por qué importa |
|---|---|---|---|
| 1 | `services/console_log_handler.py` | método `emit`, `try` que hace `session.add(log)` + `session.commit()`; el handler termina en `except Exception:` / `pass  # No propagar errores del handler` | **El sink de logs de la UI traga excepciones.** Ceguera de segundo orden. |
| 2 | `services/acceptance_contract.py` | función `_get_criteria_text`, `try` con `from services.self_review import _resolve_criteria` | **Gate de aceptación** tragando → riesgo de falso verde. |
| 3 | `services/acceptance_gate.py` | bloque `finally:` con `_P(tmp_file).unlink(missing_ok=True)` | Limpieza best-effort. |
| 4-6 | `services/claude_code_cli_runner.py` | **14 sitios** (v1 decía 9) | Camino caliente del runtime. |
| 7 | `services/codex_cli_runner.py` | `try` con `_tobj_cx = _sess_cx.get(Ticket, ticket_id)` (snapshot de título/descripción para el estimador de complejidad) | Está en el mismo bloque de arranque que `resume.resolve`. |
| 8 | `services/codex_cli_runner.py` | **10 sitios en total** (v1 decía 6) | Camino caliente. |
| 9-10 | `api/tickets.py` | **10 sitios** (v1 decía 6) | Endpoint principal. |
| 11 | `api/qa_uat.py` | 8 sitios | Agente QA/UAT. |
| 12 | `api/global_config.py` | 5 sitios | Config del operador. |

**Peores archivos por densidad de B1a (v2, medido):** `services/claude_code_cli_runner.py` **14**, `api/tickets.py` **10**, `services/codex_cli_runner.py` **10**, `api/qa_uat.py` **8**, `services/gitlab_provider.py` **7**, **`services/harness_health.py` 7** (ausente en v1), `project_manager.py` **6**, `api/global_config.py` **5**, `services/mantis_client.py` **5**, `agent_runner.py` **4**, `services/run_preflight.py` **4**.

---

## 3. Principios y guardarraíles (obligatorios)

- **No convertir robustez en fragilidad.** Muchos de esos 165 `pass` son **correctos**: telemetría best-effort, limpieza en `finally`, `proc.kill()` sobre un proceso ya muerto. Este plan **no** los transforma en `raise`. Los hace **contables y visibles**, y sube a `error` solo los del camino caliente donde el silencio ya causó un incidente documentado.
- **Prohibido gamear el propio gate (C2).** Ninguna fase puede bajar la métrica del ratchet por instrumentar. La métrica congelada cuenta el silencio **efectivo**, no la forma sintáctica.
- **Human-in-the-loop:** el gate de F3 **avisa**, no bloquea el trabajo del operador. Es un test del arnés, no un pre-commit hook. El canario de F6 **reporta y nunca arregla**.
- **Paridad de 3 runtimes:** F0(A) arregla Codex CLI y Claude Code CLI, que son los dos con `supports_resume=True`. **Fallback declarado:** GitHub Copilot Pro no tiene sesión reanudable — `resolve` corta en la guarda 2 (`not cap.supports_resume`) y devuelve `(None, None)` **sin loguear nada**, que es el comportamiento correcto y no cambia. F1..F6 son transversales a los 3.
- **Mono-operador sin auth.** Los endpoints nuevos son de solo lectura y no exponen nada que el operador no vea ya en su propio disco.
- **Cero trabajo extra al operador:** todo es invisible salvo dos tarjetas nuevas en el panel de diagnóstico que ya existe.
- **No degradar:** el ratchet de F3 **congela** el número real (165) en vez de exigir bajarlo a 0.
- **Flags default ON**, ninguna en las 4 excepciones duras; y ninguna quema tokens ociosos (el canario de F6 lee **bajo demanda**, no en un loop).
- **Toda flag configurable desde la UI** — con las 4 altas reales de F4, no solo el atributo en `config.py`.
- **Reuso obligatorio:** F3 copia el patrón de `services/provider_coupling_audit.py` + `tests/provider_coupling_baseline.json` + `tests/test_plan218_coupling_ratchet.py`. F5 usa el catálogo y los tests de huellas que ya existen. F6 reusa el tail acotado de `services/error_fingerprints.py`.

---

## 4. Fases

### F0 — Los 3 bugs mudos, con test que los reproduce

**Objetivo:** cerrar hoy los tres defectos probados.

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan255_bugs_mudos.py`
**Registrar en:** `HARNESS_TEST_FILES` de `Stacky Agents/backend/scripts/run_harness_tests.sh` (**y** en la lista equivalente de `scripts/run_harness_tests.ps1`; el meta-test `tests/test_harness_ratchet_meta.py` solo parsea el `.sh`, pero el `.ps1` es el que corre en Windows).

#### Fixture obligatorio del resume (corrige C3 — sin esto los tests 1-3 son falso verde)

`resolve()` tiene cuatro salidas tempranas (§2/E1-bis). Un test que no las satisfaga devuelve `(None, None)` **por el gate, no por el bug**, y una aserción del tipo "no se logueó el warning" **pasa hoy**. El fixture debe, literalmente:

1. `monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_ENABLED", True, raising=False)` y `..._RESUME_PROJECTS`, `""` — sobre la **instancia** `from config import config`, nunca sobre el módulo (gotcha de la casa: `getattr` del módulo devuelve el default y mata el branch).
2. Sembrar en la DB de test filas `AgentExecution` con `ticket_id`, `agent_type`, `status="completed"` y `metadata_json` que contenga **`{"runtime": "claude_code_cli", "session_id": "sess-XXXX"}`** — la clave del session ref depende del runtime (`session_id` para claude, `codex_session_id` para codex, según `_SESSION_KEY`). Sin `metadata["runtime"]` coincidente, el loop no matchea y el resultado es `(None, None)` aunque el query funcione.
3. Pasar `ticket_id` truthy y `runtime="claude_code_cli"`.
4. **No** usar `importlib.reload(config)` (contamina la suite; gotcha de la casa).

**Casos exactos:**

1. `test_resume_resolve_con_execution_id_devuelve_la_sesion_previa` — con el fixture completo y `execution_id` de la corrida actual, `resolve(...)` devuelve **`("sess-XXXX", <str|None>)`**. El criterio binario es el **valor de retorno**, no la ausencia de un log. **Hoy falla.**
2. `test_resume_resolve_falla_hoy_por_la_razon_correcta` — **test-guardia anti-falso-rojo.** Con el fixture completo, antes del fix, `caplog` (a nivel `WARNING` sobre el logger `harness.resume`) contiene el texto `already has LIMIT or OFFSET applied`. Después del fix este test se **elimina en el mismo commit** y se deja constancia en el mensaje. Sirve para probar que el rojo de hoy es el rojo correcto y no un gate cortando antes.
3. `test_resume_resolve_excluye_la_ejecucion_actual` — 3 ejecuciones completadas con session ref distinto; con `execution_id` = la más nueva, el resultado es el session ref de la **segunda** más nueva. Fija la semántica, no solo la excepción.
4. `test_resume_resolve_sin_execution_id_sigue_funcionando` — no romper el path que hoy sí anda.
5. `test_resume_sin_flag_no_loguea_y_devuelve_none` — con `CLAUDE_CODE_CLI_RESUME_ENABLED=False`, `resolve` devuelve `(None, None)` y `caplog` está **vacío**. Blinda la guarda 3 y documenta el kill-switch.
6. `test_run_incident_dev_resuelve_el_ado_id` — invocar `run_incident_dev`; asserta que `find_by_tracker_id` se llamó con el ADO id **correcto** y que `caplog` no contiene `NameError`. **Hoy falla.**
7. `test_telemetry_harvest_ledger_path_resuelve` — `telemetry_harvest._ledger_path()` devuelve un `Path` cuyo `.name == "telemetry_harvest.jsonl"` y cuyo `.parent == runtime_paths.data_dir()`, sin `NameError`. **Hoy falla.**
8. `test_telemetry_harvest_append_escribe_el_ledger` — con `data_dir` monkeypatcheado a un `tmp_path`, tras `append_to_ledger(...)` el archivo existe y tiene 1 línea JSON válida. **Hoy falla.** *(Nota de frontera: el contenido y la higiene del ledger son del **plan 258**; acá solo se prueba que se escribe.)*
9. `test_sweep_recent_runs_loguea_importerror_como_error` — **mecanismo de inyección literal (corrige C13):** llamar `sweep_recent_runs()` **sin** `_db_runs` (para entrar en la rama `if _db_runs is None:`) y `monkeypatch.setattr("db.session_scope", _raise_import_error)` donde `_raise_import_error` levanta `ImportError("cannot import name 'Execution' from 'models'")`. Asserta que `caplog` tiene **exactamente un registro con `levelno == logging.ERROR`** del logger de `ado_edit_learning`. **Hoy falla** (hoy sale a `WARNING`).

**Los fixes exactos (anclados por snippet, no por línea):**

```python
# (A) harness/resume.py, función `resolve`, bloque del `.limit(5)`:
#     mover el filtro condicional ANTES de order_by/limit
q = (db_session.query(AgentExecution)
     .filter(AgentExecution.ticket_id == ticket_id)
     .filter(AgentExecution.agent_type == agent_type)
     .filter(AgentExecution.status == "completed"))
if execution_id is not None:
    q = q.filter(AgentExecution.id != execution_id)     # AHORA, antes del limit
rows = q.order_by(AgentExecution.id.desc()).limit(5).all()

# (B) api/agents.py, función `run_incident_dev`, línea con `find_by_tracker_id(ado_id)`:
_inc = _istore.find_by_tracker_id(ticket_ado_id)        # era: ado_id

# (C) services/telemetry_harvest.py — agregar el import faltante a NIVEL MÓDULO,
#     junto a los otros imports del encabezado:
from runtime_paths import data_dir

# (D) services/ado_edit_learning.py, función `sweep_recent_runs`, el `except` anclado
#     por `logger.warning("sweep_recent_runs: error general: %s", exc)`:
#     ImportError/AttributeError son estructurales, no transitorios.
    except (ImportError, AttributeError) as exc:
        logger.error("sweep_recent_runs: fallo ESTRUCTURAL (el sweep queda "
                     "inerte hasta arreglarlo): %s", exc)
    except Exception as exc:
        logger.warning("sweep_recent_runs: error general: %s", exc)
```

**Casos borde:**
- Fix (A): el `.filter()` condicional cambia el resultado además de evitar la excepción — hoy devuelve `(None, None)`, con el fix devuelve las 5 más recientes **excluyendo** la actual. Eso **es** la intención original; el caso 3 la fija.
- Fix (B): `ticket_ado_id` está verificado en scope en el mismo cuerpo de función. Alternativa válida si el scope cambiara: `_TicketSnapshot.ado_id`.
- Fix (C): sin ciclo de imports — `runtime_paths` no importa `telemetry_harvest`. Confirmar con `python -c "import services.telemetry_harvest"` antes de cerrar la fase.
- Fix (D): el `except` específico va **antes** del genérico o Python nunca lo alcanza.

#### Rollout obligatorio del fix (A) — corrige C6

El fix **enciende** tres caminos que llevan 9 días sin ejecutarse. **No se agrega una flag nueva: el kill-switch ya existe.**

1. **Antes de deployar**, poner `CLAUDE_CODE_CLI_RESUME_PROJECTS` y `CODEX_CLI_RESUME_PROJECTS` en **un solo proyecto** desde la UI de flags. Con la allowlist no vacía, `project_enabled` restringe a ese proyecto (contrato verificado).
2. **Verificación en vivo (obligatoria, no opcional):** correr un ticket dos veces sobre ese proyecto y confirmar en el log **las dos** cosas: (i) que **no** aparece `arranque en frío`, y (ii) que **sí** aparece `resume …: sesión previa=` o `codex resume: sesión previa=`. La ausencia de (ii) significa que el camino sigue muerto aunque el query ya no explote.
3. **Cota al delta:** si `delta_prefix` supera **20 000 caracteres**, descartarlo y arrancar con el prompt completo, logueando a `info` con el largo. Un delta gigante es peor que no reanudar. Se implementa en `harness/resume.py`, justo donde se arma `delta_prefix`.
4. **Recién entonces** vaciar el CSV para volver a "todos los proyectos".
5. **Rollback en un paso:** `CLAUDE_CODE_CLI_RESUME_ENABLED` / `CODEX_CLI_RESUME_ENABLED` a `false` desde la UI. Deja el sistema exactamente en el comportamiento de los últimos 9 días.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan255_bugs_mudos.py -v
```

**Criterio binario:** 9 verdes (8 tras eliminar el test-guardia 2). Y en el log del día siguiente al deploy: cero ocurrencias de `harness.resume.resolve falló`, cero de las dos firmas de traceback de §9, y **≥ 1** de `sesión previa=`.

**Flag:** ninguna nueva. (A) usa el kill-switch existente; (B)(C)(D) son fixes de bug y un fix detrás de flag deja el bug vivo por default.
**Impacto por runtime:** (A) Claude Code CLI y Codex CLI; Copilot Pro corta en `supports_resume` sin loguear → sin cambio, sin degradación. (B)(C)(D) transversales.
**Trabajo del operador:** los 4 pasos de rollout, una sola vez. Es human-in-the-loop deliberado: encender una feature dormida no se hace a espaldas del operador.

---

### F1 — Instrumentar el silencio: contador de fallos tragados

**Objetivo:** antes de cambiar los 165 `pass`, **medir** cuáles se disparan de verdad.

**Archivo a crear:** `Stacky Agents/backend/services/silent_failure_counter.py` — módulo **puro** salvo un dict en memoria. **Verificado en v2: el archivo no existe hoy.**

**Símbolos nuevos exactos:**

```python
def note_swallowed(site: str, exc: BaseException | None = None) -> None:
    """Plan 255 F1 — registra que un except tragó un fallo, SIN loguear.

    `site` es un identificador estable "modulo.funcion" (SIN número de línea:
    las líneas se mueven y el contador perdería continuidad).
    Costo: un incremento de dict. Pensado para llamarse dentro de un
    `except ...: pass` sin cambiar su semántica ni su performance.
    """

def swallowed_report(top: int = 30) -> dict:
    """{'window': {'process_started_at': iso, 'window_seconds': int},
        'rows': [{'site','count','last_exc_type','last_seen'}]}  ordenado por count desc."""

def reset_swallowed() -> None:
    """Solo para tests."""
```

**Aplicación:** en los **12 sitios** de la tabla de E4, el `pass` pasa a:

```python
    except Exception as _e:
        note_swallowed("acceptance_gate.evaluate", _e)   # antes: pass
```

**Reglas duras:**
- `note_swallowed` **jamás** levanta. Su cuerpo entero va en un `try/except BaseException: pass`. Si el contador de fallos falla, no puede tumbar el código que estaba protegiendo.
- **No loguea.** Si logueara, los 12 sitios generarían el mismo ruido que el plan 257 va a combatir.
- **`site` sin número de línea (C11).** Con la sesión paralela editando esos archivos, un site `"...:101"` cambia de identidad en cada edición y el histórico se parte.
- Cota de memoria: máximo 500 sites distintos; al pasarse, deja de agregar claves nuevas.
- **Excepción explícita para `console_log_handler.emit`:** ese es el sink de logs; ahí `note_swallowed` va con el guard reforzado y sin tocar logging en absoluto, para no crear recursión.

#### Ventana honesta (corrige C5)

El contador vive en RAM y el backend del operador **reinicia varias veces por día** (la evidencia del plan 253 lo documenta). Por lo tanto:

- `swallowed_report()` devuelve **siempre** `window.process_started_at` y `window.window_seconds`, y la tarjeta de la UI los muestra en el título: *"Fallos silenciados — ventana: 4 h 12 min (desde el último arranque)"*.
- **Regla anti-conclusión, escrita en el docstring del módulo y en el tooltip de la tarjeta:** `count == 0` **NO** prueba que un sitio sea inerte. Solo prueba que no se disparó en esta ventana. Nunca se retira instrumentación ni se degrada un sitio basándose en un cero.
- El paso "dejar corriendo unos días" **se elimina** del orden de implementación. Se reemplaza por: leer el reporte al final de una sesión de trabajo larga, y usarlo solo para **priorizar** qué sitio investigar, jamás para descartar.
- **No** se persiste a un JSONL: los ledgers en disco son del **plan 258**. Si más adelante hace falta persistencia, es un follow-up de ese plan, no de este.

**Exposición:** `@bp.get("/silent-failures")` en `Stacky Agents/backend/api/diag.py` (**el blueprint real de ese archivo es `bp = Blueprint("diag", __name__, url_prefix="/diag")` y usa `@bp.get(...)`, no `@diag_bp.route(...)` — C15**), y una tarjeta en el panel de diagnóstico existente con las top 10 filas + la ventana.

**Tests:** `Stacky Agents/backend/tests/test_plan255_silent_failures.py` (registrar en `.sh` y `.ps1`):
- `test_note_swallowed_incrementa_por_site`
- `test_note_swallowed_nunca_levanta` — pasarle un objeto cuyo `__repr__` explota; no debe propagarse nada.
- `test_swallowed_report_ordena_por_count`
- `test_swallowed_report_declara_la_ventana` — `window.process_started_at` y `window.window_seconds` presentes y coherentes.
- `test_cota_de_500_sites` — el site 501 no crea clave nueva.
- `test_note_swallowed_no_loguea` — **con `caplog.set_level(logging.DEBUG)`** antes de la llamada (C18: sin eso, `caplog` captura desde `WARNING` y el test verdea al vacío), asserta `caplog.records == []`.
- `test_endpoint_diag_devuelve_el_reporte`

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan255_silent_failures.py -v
```
7 verdes, y `GET /api/diag/silent-failures` responde `200` con `{"window": {...}, "rows": [...]}`.

**Flag:** `STACKY_SILENT_FAILURE_COUNTER_ENABLED`, **default ON** (prefijo `STACKY_` de la casa; v1 la llamaba sin prefijo). Sin excepción dura: es un dict en memoria, no quema tokens ociosos, no toca ninguna base del operador, no reduce seguridad. Alta en la UI: **F4**.
**Impacto por runtime:** transversal, los 3 igual.
**Trabajo del operador: ninguno** (mira la tarjeta si quiere).

---

### F2 — Subir a `error` los `except` que ya causaron un incidente

**Objetivo:** que un fallo **estructural** (import, atributo, nombre) no pueda volver a esconderse detrás de un `warning`.

**Regla de clasificación (determinística, sin criterio del implementador):**

| Tipo de excepción | Nivel | Razón |
|---|---|---|
| `ImportError`, `ModuleNotFoundError`, `AttributeError`, `NameError` | **`error`** | Son **bugs de código**. No se arreglan solos y no son transitorios. E3 probó el costo: 1016 ocurrencias silenciadas. |
| `OperationalError`, `TimeoutError`, `ConnectionError`, `OSError` | `warning` | Transitorios. El reintento del plan 253 los cubre. |
| **`TypeError`** | **`warning` (excluido a propósito — C10)** | Es la excepción más común por **datos malos** del operador o de una API externa, no por un bug. Meterla en `_STRUCTURAL` inunda el log, y v1 delegaba la mitigación al plan 257, que **puede no implementarse**. Queda como el **primer candidato a promover** una vez que 257 esté en el árbol y medido. |
| Todo lo demás | como está hoy | No tocar sin evidencia. |

**Los 6 sitios exactos a modificar** (elegidos porque los logs prueban que tragaron algo real; anclados por función + snippet):

| # | Archivo | Ancla | Cambio |
|---|---|---|---|
| 1 | `services/ado_edit_learning.py` | `sweep_recent_runs`, snippet `"sweep_recent_runs: error general: %s"` | Ya en F0(D). Caso de referencia. |
| 2 | `services/ado_edit_learning.py` | `sweep_recent_runs`, snippet `"sweep_recent_runs: error en WI %s (no crítico): %s"` | Mismo tratamiento vía `log_level_for`. |
| 3 | `api/agents.py` | `run_incident_dev`, snippet `"run_incident_dev: no se pudo linkear exec=%s a una incidencia"` | `logger.info` → nivel según `log_level_for(exc)`. |
| 4 | `app.py` | thread `plan199-harvest`, snippet `"plan199 autoscan: fallo no fatal"` | Ya usa `logger.exception`; **verificar** que no esté anidado en otro `except` que lo re-tragase. Si ya sale a `error`, **no se toca** y se anota. |
| 5 | `harness/resume.py` | `resolve`, snippet `"harness.resume.resolve falló (arranque en frío): %s"` | Nivel según `log_level_for`, y **agregar `note_swallowed("harness.resume.resolve", exc)`** para que el contador lo cuente aunque el nivel bajara. |
| 6 | `services/console_log_handler.py` | `emit`, snippet `pass  # No propagar errores del handler` | **No** se convierte en logging (recursión); solo `note_swallowed` con guard reforzado (viene de F1) y un comentario de 2 líneas explicando por qué acá el silencio es correcto. |

**Helper compartido, símbolo exacto** en `Stacky Agents/backend/services/silent_failure_counter.py`:

```python
# TypeError EXCLUIDO a propósito (plan 255 C10): es la excepción más común por
# datos malos, no por bug. Promoverla requiere el throttle del plan 257 en el árbol.
_STRUCTURAL = (ImportError, ModuleNotFoundError, AttributeError, NameError)

def log_level_for(exc: BaseException) -> str:
    """'error' si es un bug estructural, 'warning' si es transitorio."""
    return "error" if isinstance(exc, _STRUCTURAL) else "warning"

def log_at_level(logger, exc: BaseException, msg: str, *args) -> None:
    """Loguea `msg` al nivel que corresponde a `exc`. Un solo lugar decide."""
```

**Casos borde:**
- `ModuleNotFoundError` es subclase de `ImportError`: figura explícito por legibilidad, `isinstance` ya lo cubría.
- Sitios donde `error` dispararía una alerta al operador por algo que no puede arreglar: no hay sistema de alertas por nivel de log en Stacky, así que el riesgo es nulo hoy.
- El sitio 6 **no** usa `log_at_level` (recursión). Es la excepción escrita.

**Tests:** en `test_plan255_silent_failures.py`:
- `test_log_level_for_estructural_es_error` — los 4 tipos.
- `test_log_level_for_transitorio_es_warning` — `OperationalError`, `TimeoutError`, `ConnectionError`, **y `TypeError`** (fija la exclusión de C10 para que nadie la revierta sin querer).
- `test_resume_importerror_loguea_error_y_cuenta` — sube a `error` **y** aparece en `swallowed_report()["rows"]`.
- `test_console_log_handler_no_loguea_al_tragar` — blinda contra la recursión.

**Criterio binario:** 4 verdes + `log_at_level` o `log_level_for` importado en **≥ 4 archivos** de producción, verificado por un test que hace `ast` sobre los imports de esos archivos (C19: un `grep -c` sobre texto se satisface con prosa; un chequeo de imports por AST, no).

**Flag:** `STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL`, **default ON**. Sin excepción dura. Alta en la UI: **F4**.
**Impacto por runtime:** transversal.
**Trabajo del operador: ninguno.**

---

### F3 — Ratchet de silencio: que no entre uno nuevo

**Objetivo:** congelar la deuda en su nivel **real** (165) y exigir justificación explícita para cada `pass` nuevo.

**Archivos a crear (reusando el patrón que la casa YA tiene — C12):**

1. `Stacky Agents/backend/services/silence_audit.py` — **el escáner**, módulo de producción importable. Espejo de `services/provider_coupling_audit.py`.
2. `Stacky Agents/backend/tests/silence_ratchet_baseline.json` — el baseline congelado. Espejo de `tests/provider_coupling_baseline.json`.
3. `Stacky Agents/backend/tests/test_plan255_silence_ratchet.py` — el meta-test, que **solo compara**. Espejo de `tests/test_plan218_coupling_ratchet.py`.

**El baseline NO se genera desde el test (corrige C12/C1-circularidad).** Se genera con un comando separado y se **commitea**:

```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m services.silence_audit --write-baseline
```

El test **nunca** escribe el baseline. Si el árbol y el baseline divergen hacia arriba, el test se pone rojo y el mensaje dice el comando de regeneración. Un baseline autogenerado por el test que valida contra el baseline pasa siempre por construcción.

**Contrato de `services/silence_audit.py`:**

```python
def scan_silent_handlers() -> dict:
    """{'mudos_totales': {archivo: int},      # Pass  O  solo note_swallowed  <- CONGELADO
        'mudos_sin_contador': {archivo: int}, # solo Pass                     <- puede bajar
        'silence_ok': {archivo: int}}         # excluidos por marca explícita
    Determinista, ordenado, rutas posix relativas a backend/."""
```

#### Anti-gaming: por qué son DOS conteos (corrige C2)

Si el ratchet contara solo `body == [Pass()]`, aplicar F1 a los 12 sitios bajaría la métrica en 12 **sin mejorar nada** — F1 explícitamente no loguea. Instrumentar no es arreglar.

- **`mudos_totales`** cuenta un handler como mudo si su `body` es `[ast.Pass()]` **o** si es exactamente un `ast.Expr` cuyo `value` es un `ast.Call` a `note_swallowed`. **Este es el número que el ratchet congela (165).** F1 lo deja **igual**: un sitio se mueve de bucket, no desaparece.
- **`mudos_sin_contador`** cuenta solo `[ast.Pass()]`. Puede bajar libremente — bajarlo es exactamente el progreso que F1 representa.
- El KPI "0 en `services/` + `api/` críticos" de v1 **se elimina**: era alcanzable por construcción con solo instrumentar.

**Reglas duras (todas son lecciones de ratchets previos de este repo):**
- **Detección por AST, nunca por regex.** `ast.walk` buscando `ast.ExceptHandler`. Un regex sobre `except Exception` es destructivo y da falsos positivos (ya pasó en este repo con un centinela textual de flags).
- **Escape hatch `# silence-ok: <motivo>` — mecanismo exacto (corrige C4).** El módulo `ast` **descarta los comentarios**: no hay forma de verlos con `ast` solo, y caer en un regex reintroduce el gotcha que este plan combate. El mecanismo obligatorio es **`tokenize`**, que es análisis léxico, no textual:
  ```python
  import io, tokenize
  comment_lines = {
      tok.start[0]
      for tok in tokenize.generate_tokens(io.StringIO(src).readline)
      if tok.type == tokenize.COMMENT and tok.string.startswith("# silence-ok:")
  }
  # un handler está exento si alguna línea de handler.lineno..handler.body[0].lineno
  # está en comment_lines
  ```
  Obliga a **escribir el motivo**, que es el punto. Un `# silence-ok:` sin texto después de los dos puntos **no** exime (test dedicado).
- **Baseline por archivo, no global:** si otra rama agrega deuda en un archivo ajeno, tu archivo no se pone rojo.
- **Bajar no exige regenerar:** el test compara `actual <= baseline`, no `actual == baseline`.
- **Exclusiones idénticas a las del censo:** `.venv`, `venv`, `tests`, `__pycache__`, `node_modules`. Copiadas de los tests de exclusión del ratchet 218.
- **El escáner corre sobre los archivos objetivo, nunca sobre sí mismo ni sobre `tests/`** (gotcha recurrente: la prosa de un artefacto choca con su propio gate).

**Baseline inicial:** el producido por `--write-baseline` sobre el árbol de hoy. **Total esperado: 165** para `mudos_totales`. Los archivos con más carga, para que el implementador verifique de un vistazo que el escáner anda: `services/claude_code_cli_runner.py` 14, `api/tickets.py` 10, `services/codex_cli_runner.py` 10, `api/qa_uat.py` 8, `services/gitlab_provider.py` 7, `services/harness_health.py` 7, `project_manager.py` 6, `api/global_config.py` 5, `services/mantis_client.py` 5. **Si el escáner no reproduce estos números, el escáner está mal — no el repo.**

**Casos borde:**
- Archivo nuevo sin entrada en el baseline: su límite implícito es **0**. Un archivo nuevo no puede nacer con deuda muda.
- **Archivo renombrado (corrige C16):** v1 lo declaraba "correcto" que se pusiera rojo, pero eso convierte un rename inocente en deuda ajena — exactamente el gotcha que el plan dice evitar. Regla nueva: si un archivo **desaparece** del árbol y el **total del paquete de primer nivel** (`services/`, `api/`, `harness/`, raíz) **no subió**, el test **pasa** y el mensaje de aserción dice: *"posible rename detectado; regenerá el baseline con `python -m services.silence_audit --write-baseline`"*. Un rename no rompe a nadie; agregar deuda sí.
- `except Exception: pass` en una línea: el AST lo ve igual que la versión multilínea. Test dedicado.
- Un handler con `pass` **y** un comentario dentro del body: el `body` sigue siendo `[Pass()]` — cuenta. Esto es lo que la ventana de grep de v1 perdía.

**Tests del propio ratchet:**
- `test_scan_es_determinista` — `scan_silent_handlers() == scan_silent_handlers()`.
- `test_scan_excluye_tests_y_venv`
- `test_ratchet_detecta_pass_en_una_linea`
- `test_ratchet_respeta_silence_ok`
- `test_ratchet_silence_ok_sin_motivo_no_exime`
- `test_ratchet_note_swallowed_cuenta_como_mudo_total` — **el test anti-gaming de C2**: un handler con solo `note_swallowed(...)` suma en `mudos_totales` y **no** en `mudos_sin_contador`.
- `test_ratchet_archivo_nuevo_arranca_en_cero`
- `test_ratchet_permite_bajar_sin_regenerar`
- `test_ratchet_rename_no_pone_rojo`
- `test_ratchet_no_se_escanea_a_si_mismo`
- `test_baseline_actual_es_verde` — el estado de hoy pasa. **Si esto falla, se corre el comando de regeneración y se revisa el diff a mano; nunca se ajusta el número para que verdee.**

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan255_silence_ratchet.py -v
```
11 verdes **con el repo tal como está**. Y la prueba manual: agregar a mano un `except Exception: pass` en `api/tickets.py` lo pone rojo; agregarle `# silence-ok: proceso ya muerto` lo pone verde de nuevo.

**Flag:** ninguna (es un test del arnés, no runtime).
**Impacto por runtime:** ninguno.
**Trabajo del operador: ninguno.**

---

### F4 — Alta de las flags en la UI (los 4 lugares reales)

**Corrige C14.** v1 decía *"exponer las 2 flags en el panel de flags y en `api/global_config.py`"*. Eso es incorrecto y deja las flags invisibles: **`api/global_config.py` no es el panel de flags.** Verificado: `api/harness_flags.py` lee `FLAG_REGISTRY` / `read_current` / `list_categories` / `apply_updates` de `services/harness_flags.py`. El atributo en `config.py` **no basta** para que la flag salga en la UI.

Para **cada** flag nueva (`STACKY_SILENT_FAILURE_COUNTER_ENABLED`, `STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL`, `STACKY_DORMANT_CANARY_ENABLED` de F6), hacer los **4** pasos:

1. **`Stacky Agents/backend/config.py`** — atributo con el idioma exacto de la casa (**no existe ningún helper `_env_bool` en este archivo**):
   ```python
   STACKY_SILENT_FAILURE_COUNTER_ENABLED: bool = os.getenv(
       "STACKY_SILENT_FAILURE_COUNTER_ENABLED", "true").lower() in ("1", "true", "yes")
   ```
   Los consumidores leen `from config import config` y usan `config.STACKY_...` (la **instancia**, nunca el módulo).
2. **`Stacky Agents/backend/services/harness_flags.py`** — un `FlagSpec` en `FLAG_REGISTRY` con: `key` (idéntica al nombre del atributo/env var), `type="bool"`, `label` y `description` en español, `group="global"`, `default=True`.
3. **`Stacky Agents/backend/services/harness_flags.py`, `_CATEGORY_KEYS`** — agregar la key bajo la categoría **existente `observabilidad_notif`** (verificada en `FLAG_CATEGORIES`). **No crear una categoría nueva:** una flag sin categoría rompe el meta-test.
4. **`Stacky Agents/backend/tests/test_harness_flags.py`, set `_CURATED_DEFAULTS_ON`** — agregar las 3 keys con un comentario `# ── Plan 255 — …`. Toda `FlagSpec` con `default=True` debe estar ahí o `test_default_known_only_for_curated` se pone **rojo**.

**Prohibido:** editar `deployment/harness_defaults.env` a mano (se genera con su script).

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
```
Verde. **Ojo (gotcha de la casa):** `tests/test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**; correr los archivos **por separado** y validar solo la entrada propia. Y `GET /api/harness-flags` debe listar las 3 keys nuevas bajo *Observabilidad y notificaciones*, con el toggle funcionando desde la UI.

---

### F5 — Huella de regresión de las 3 clases de error

**Corrige C8.** Este plan mata tres clases de error concretas y visibles en el log. El registro ya existe y está contractualizado; no registrarlas sería tirar el activo.

- Catálogo: `Stacky Agents/docs/sistema/error_fingerprints.json` (`schema_version: 1`).
- Motor: `Stacky Agents/backend/services/error_fingerprints.py` (`catalog_path`, `load_fingerprints`, `guarded_fingerprints`, `scan_text`, `run_boot_scan`, con tail acotado `_BOOT_SCAN_TAIL_BYTES = 5_000_000`).
- Tests de contrato que hay que dejar verdes: `tests/test_error_fingerprints_catalog.py` y `tests/test_error_fingerprints_scan.py`.

**Campos obligatorios** (los exige `tests/test_error_fingerprints_catalog.py`): `id, title, class, status, log_pattern, log_guarded, killed_by, guard_test, self_test`, con `self_test.matches` y `self_test.clean`.

**Trampa a evitar (la fija `test_self_test_coherente`):** cada muestra de `clean` **no debe** matchear el patrón. Un patrón perezoso como `NameError` es demasiado ancho y hace fallar el test — hay que anclarlo a la firma completa.

**Las 3 entradas a agregar:**

| `id` | `class` | `log_pattern` (anclado, no genérico) | `guard_test` |
|---|---|---|---|
| `resume_resolve_limit_filter` | `harness-resume` | `harness\.resume\.resolve falló \(arranque en frío\)` | `tests/test_plan255_bugs_mudos.py` |
| `run_incident_dev_nameerror_ado_id` | `nameerror-scope` | `NameError: name 'ado_id' is not defined` | `tests/test_plan255_bugs_mudos.py` |
| `telemetry_harvest_nameerror_data_dir` | `nameerror-import` | `NameError: name 'data_dir' is not defined` | `tests/test_plan255_bugs_mudos.py` |

Las tres con `status: "resolved"`, `log_guarded: true`, `killed_by: "plan 255 (cero fallas mudas)"`, `date_resolved` = la fecha real del commit, `killed_commit` = el hash real, y `evidence` con los anclajes por función de §2.

**`self_test` de cada una:** un `matches` copiado **textual** de una línea real de `stacky-2026-07-26.log`, y un `clean` que sea la misma línea con el nombre corregido (p. ej. `ticket_ado_id`), para probar que el patrón es **angosto** y no va a alarmar por cualquier `NameError` futuro.

**Criterio binario:**
```
.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_catalog.py tests/test_error_fingerprints_scan.py -v
```
Verde, con 3 huellas más que antes, y `run_boot_scan()` sobre un log fresco devuelve `[]`.

**Flag:** ninguna (es data de catálogo + tests existentes).
**Trabajo del operador: ninguno.**

---

### F6 — [ADICIÓN ARQUITECTO] Canario de features dormidas

> **Por qué existe.** El hallazgo central de este plan no es que el `resume` tuviera un bug de SQLAlchemy. Es que **estuvo 9 días muerto con las flags en ON y nadie se enteró**, porque Stacky mide que las cosas **fallen**, no que hayan **funcionado**. Las huellas de F5 alarman cuando aparece un patrón malo. Nada alarma cuando un patrón **bueno deja de aparecer**. Los tres mecanismos que esta auditoría encontró rotos —`resume`, cosecha de telemetría, sweep de aprendizaje ADO— tienen exactamente esa forma: caros, gateados por flags que el operador dejó en ON, y **mudos cuando funcionan**. Un canario de ausencia es la generalización barata de todo el plan.

**Archivo a crear:** `Stacky Agents/backend/services/dormant_canary.py`.

**Contrato:**

```python
@dataclass(frozen=True)
class CanarySpec:
    id: str                 # slug estable
    label: str              # texto para la UI, en español
    success_pattern: str    # regex de la línea que SOLO aparece cuando el mecanismo tuvo ÉXITO
    gate_flags: tuple[str, ...]   # flags que deben estar ON para que se espere actividad
    max_silent_days: int    # días sin éxito antes de avisar
    hint: str               # qué mirar; NUNCA una acción automática

CANARIES: tuple[CanarySpec, ...] = (...)

def check_canaries(now=None) -> list[dict]:
    """[{'id','label','status','last_success_at','days_silent','gated_off','hint'}]
    status ∈ {'ok', 'dormido', 'apagado', 'sin_datos'}. NO arregla nada."""
```

**Los 3 canarios sembrados (uno por mecanismo que la auditoría probó que puede morir mudo):**

| `id` | `success_pattern` | `gate_flags` | `max_silent_days` |
|---|---|---|---|
| `resume_efectivo` | `resume .*: sesión=` o `resume: sesión previa=` | `CLAUDE_CODE_CLI_RESUME_ENABLED`, `CODEX_CLI_RESUME_ENABLED` | 3 |
| `telemetry_harvest` | `plan199 autoscan: discovered=\d+ backfilled=\d+` | `STACKY_TELEMETRY_HARVEST_ENABLED`, `STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED` | 3 |
| `ado_edit_learning_sweep` | `ado edit learning: WI .* => lección nueva` | (ninguna) | 7 |

**Reglas duras:**
- **Avisa, nunca arregla.** No reintenta, no re-habilita, no toca config. Human-in-the-loop innegociable: el canario le da al operador un hecho, la decisión es suya.
- **`gated_off` no es una alarma.** Si las `gate_flags` están OFF, el status es `apagado` y se muestra en gris: el operador la apagó a propósito. La alarma (`dormido`) es solo *flag ON + cero éxitos en `max_silent_days`*. Esta distinción es lo que evita que el canario se vuelva ruido.
- **Cero costo ocioso.** Se evalúa **bajo demanda** al pegarle al endpoint, no en un loop. **Reusa el tail acotado** de `services/error_fingerprints.py` (`_latest_log_file`, `_BOOT_SCAN_TAIL_BYTES`) en vez de leer 16 MB. Esto es lo que permite que la flag sea default ON sin violar la regla "nada default-ON quema tokens/CPU ocioso".
- **`sin_datos` ≠ `dormido`.** Si no hay log suficiente para cubrir la ventana, el status es `sin_datos`. Nunca se afirma que algo está muerto sin evidencia.
- **No inventa infraestructura.** Si el plan 253 ya construyó `_maintenance_loop` en `app.py`, el canario puede colgarse ahí para un chequeo diario; si no existe (**verificado hoy: `_maintenance_loop` NO existe en el árbol**), el canario funciona igual bajo demanda. **F6 no depende de 253.**

**Exposición:** `@bp.get("/dormant-canaries")` en `api/diag.py`, y una tarjeta en el panel de diagnóstico: *"Mecanismos dormidos"*, con una fila por canario y su `hint`.

**Tests:** `Stacky Agents/backend/tests/test_plan255_dormant_canary.py` (registrar en `.sh` y `.ps1`):
- `test_canario_con_exito_reciente_es_ok`
- `test_canario_sin_exito_y_flag_on_es_dormido`
- `test_canario_con_flag_off_es_apagado_no_dormido` — la regla que evita el ruido.
- `test_canario_sin_log_suficiente_es_sin_datos`
- `test_check_canaries_no_muta_nada` — asserta que no se escribió ningún archivo ni cambió ninguna config (human-in-the-loop).
- `test_resume_canary_habria_detectado_el_bug_de_e1` — **el test que cierra el círculo:** alimentar un log sintético con las 50 líneas de `arranque en frío` y **cero** de `sesión previa=`; el canario `resume_efectivo` debe salir `dormido`. Prueba que el mecanismo habría atrapado el bug que motivó el plan.
- `test_endpoint_diag_dormant_canaries`

**Criterio binario:** 7 verdes + `GET /api/diag/dormant-canaries` responde `200`.

**Flag:** `STACKY_DORMANT_CANARY_ENABLED`, **default ON**. Sin excepción dura: lectura bajo demanda de un tail acotado del log local, sin red, sin modelo, sin escritura. Alta en la UI: **F4**.
**Impacto por runtime:** transversal; los patrones de los 3 canarios cubren los caminos de claude y codex, y Copilot Pro no tiene mecanismo dormido que vigilar (se declara y no se inventa un canario falso).
**Trabajo del operador: ninguno** (mira la tarjeta si quiere).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Convertir `pass` correctos en `raise` rompe el sistema** — riesgo #1 | Este plan **no convierte ningún `pass` en `raise`**. F1 solo cuenta, F2 sube el **nivel de log** de 5 sitios con incidente documentado (el 6.º explícitamente no loguea), F3 congela. Ni un cambio de flujo de control. |
| **F0(A) enciende un camino que nadie ejercitó en 9 días** — riesgo #2, subestimado en v1 | Rollout escalonado con el kill-switch **existente** (`*_RESUME_PROJECTS` a un proyecto → verificación en vivo de las **dos** firmas → vaciar CSV), cota de 20 000 chars al delta, y rollback de un paso (`*_RESUME_ENABLED=false` desde la UI). |
| Resume contra un `session_id` caducado del CLI | El runner ya envuelve el resume en su propio `try` best-effort; el `log("warn", ...)` del call-site queda como red. El canario de F6 detecta si el éxito **nunca** vuelve a aparecer. |
| Instrumentar baja el ratchet sin arreglar nada | `mudos_totales` cuenta `Pass` **o** `note_swallowed`-solo. Instrumentar mueve el sitio de bucket, no lo saca del total congelado. |
| El baseline nace rojo por estar mal medido | El baseline lo produce el escáner de producción con `--write-baseline`, y el plan publica los números esperados por archivo para verificar de un vistazo que el escáner anda. |
| Subir a `error` inunda el log | `TypeError` **excluido** de `_STRUCTURAL` (C10). Los tipos que quedan son bugs de código: si aparecen seguido, la inundación **es** la señal. El plan 257 (throttle) es complemento, **no** prerrequisito. |
| El ratchet se pone rojo por deuda de otra rama o por un rename | Baseline **por archivo** + comparación `<=` + regla de rename por total de paquete. |
| `note_swallowed` agrega overhead en el camino caliente | Un `dict[str] += 1` en 12 sitios, todos en paths de fallo (no en el happy path). |
| Recursión de logging en `console_log_handler` | Ese sitio **no** loguea nunca; solo `note_swallowed` con guard `BaseException`. Test dedicado. |
| El fix del import en `telemetry_harvest` crea un ciclo | Verificado: `runtime_paths` no importa `telemetry_harvest`. Confirmar con `python -c "import services.telemetry_harvest"` antes de cerrar la fase. |
| Conclusiones falsas desde el contador en RAM | `swallowed_report` declara su ventana y el módulo lleva escrita la regla: `count == 0` no prueba inercia. |
| El canario de F6 se vuelve ruido | `apagado ≠ dormido` y `sin_datos ≠ dormido`. Solo alarma con flag ON + evidencia de ventana suficiente. |

---

## 6. Fuera de scope

- Refactorizar los 1244 `except Exception` del backend. Este plan mide, congela y arregla los que tienen incidente probado.
- Reemplazar `except Exception` por excepciones específicas en todo el repo.
- **Persistir el contador de F1 a disco** — los ledgers JSONL son del **plan 258**.
- Los locks de SQLite que producen `OperationalError` → **plan 253**.
- El ruido de log, el throttle y la retención → **plan 257**.
- La contaminación de los ledgers JSONL con datos de test → **plan 258**.
- El falso rojo del cierre de corridas → **plan 254**.
- La cuarentena del `output_watcher` → **plan 256**.
- El **contenido** del ledger de cosecha (F0 solo prueba que se escribe) → **plan 258**.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **Falla muda** | Un fallo que ocurre, se maneja, y no deja rastro consultable (o lo deja a un nivel que nadie mira). |
| **`except Exception: pass`** | El caso extremo: se atrapa cualquier fallo y no se hace nada. **165** en este backend (medido por AST, no por grep). |
| **Fallo estructural** | Bug de código (import, atributo, nombre). No se arregla solo, no es transitorio → merece `error`. `TypeError` queda **fuera** a propósito. |
| **Fallo transitorio** | Lock, timeout, red. Se arregla reintentando → merece `warning`. |
| **`resume`** | Mecanismo que reanuda una sesión de agente previa en vez de arrancar en frío. `backend/harness/resume.py`. Gateado por `*_RESUME_ENABLED` + `*_RESUME_PROJECTS` por runtime. |
| **Ratchet** | Meta-test que congela una métrica de deuda y falla si empeora. |
| **`mudos_totales` / `mudos_sin_contador`** | Los dos buckets de F3. El primero se congela (anti-gaming), el segundo puede bajar. |
| **`# silence-ok: <motivo>`** | Marca que excluye un `pass` del ratchet obligando a escribir por qué. Se detecta con **`tokenize.COMMENT`**, nunca con regex, porque `ast` no ve comentarios. |
| **Huella de regresión** | Entrada en `docs/sistema/error_fingerprints.json` que alarma si un patrón ya resuelto **reaparece** en un log fresco. |
| **Canario de feature dormida** | Lo inverso a una huella: alarma cuando un patrón **de éxito deja de aparecer**. F6. |

---

## 8. Orden de implementación

1. **F0** — los tests primero, **rojos**, verificando con el caso 2 (test-guardia) que el rojo es el rojo correcto y no un gate cortando antes. Después los 4 fixes (A, B, C, D). **El fix (A) es el de mayor retorno económico del portafolio.**
2. **Rollout de (A)** — los 4 pasos de §4/F0: allowlist a un proyecto → correr un ticket dos veces → confirmar en el log que **no** aparece `arranque en frío` **y que sí aparece** `sesión previa=` → vaciar el CSV.
3. **F1** — `services/silent_failure_counter.py` + los 12 sitios + `@bp.get("/silent-failures")` + tarjeta con la ventana declarada.
4. Leer `swallowed_report()` al final de una sesión de trabajo larga. **Solo para priorizar.** `count == 0` no autoriza a retirar instrumentación. *(v1 pedía "dejar corriendo unos días": inejecutable con un dict en RAM y un backend que reinicia varias veces por día.)*
5. **F2** — nivel por clase en los 6 sitios, usando `log_at_level`. `TypeError` **no** entra.
6. **F3** — `services/silence_audit.py` → `--write-baseline` → commitear el baseline → el meta-test que solo compara.
7. **F4** — alta de las 3 flags en los **4** lugares (`config.py`, `FlagSpec`, `_CATEGORY_KEYS` bajo `observabilidad_notif`, `_CURATED_DEFAULTS_ON`).
8. **F5** — las 3 huellas en `docs/sistema/error_fingerprints.json`, con `self_test` angosto.
9. **F6** — `services/dormant_canary.py` + endpoint + tarjeta + el test que prueba que habría atrapado E1.
10. Registrar los **4** archivos de test nuevos en `HARNESS_TEST_FILES` (`.sh`) **y** en la lista de `run_harness_tests.ps1`.

### 8.1 Frontera viva con el plan 257 (corrige C9 — leer antes de tocar nada)

**Verificado:** el plan 257, en su fase **F1-bis**, quiere cablear `log_throttled` en `services/ado_edit_learning.py` (`sweep_recent_runs: error general`, 1016 ocurrencias) y en `harness/resume.py` (`resolve falló (arranque en frío)`, 50 ocurrencias) — **exactamente las dos líneas** que este plan toca en F0(D) y F2(5). 257 además instala un `logging.Filter` de dedup en el handler.

**Orden obligatorio, no negociable:**

1. **255 va PRIMERO.** Arregla la **causa** (el query roto, el import faltante, el nombre inexistente) y fija el **nivel** correcto por clase de excepción.
2. **257 va DESPUÉS**, y cablea el throttle **sobre el nivel ya corregido**. Si se invierte el orden, 257 le pone throttle a un `warning` que 255 iba a convertir en `error`, y el dedup puede tragarse la señal recién creada.
3. **255 no depende de 257.** Ningún criterio de aceptación de este plan menciona `log_throttled`, y F2 no delega su mitigación de volumen a un plan sin implementar (por eso `TypeError` quedó afuera).
4. **Contrato para el implementador de 257:** después de 255, el sitio de `resume.py` ya tiene `note_swallowed` y sale por `log_at_level`; el de `ado_edit_learning.py` tiene **dos** `except` (uno específico a `error`, uno genérico a `warning`). El throttle va sobre la llamada final, respetando el nivel que decide `log_level_for`.

**No tocar en este plan** (dueños ajenos): `db.py` (253), `services/ticket_status.py` y `run_outcome` (254), la cuarentena de `services/output_watcher.py` (256), `services/local_file_logging.py` (257), los ledgers JSONL (258). El `_maintenance_loop` de `app.py` y `services/confirm_token.py` los crea **253** y **hoy no existen** — este plan **no** los requiere.

---

## 9. Definición de Hecho (DoD)

- [ ] `harness/resume.py` aplica el `.filter()` condicional **antes** de `order_by`/`limit`.
- [ ] `harness/resume.py` acota el `delta_prefix` a 20 000 caracteres y lo loguea a `info` cuando lo descarta.
- [ ] Log del día siguiente al deploy: **0** ocurrencias de `harness.resume.resolve falló`.
- [ ] Log del día siguiente al deploy: **≥ 1** ocurrencia de `sesión previa=` — la prueba de que el camino muerto revivió. *(Sin esto, el fix arregló la excepción pero no la feature.)*
- [ ] `api/agents.py` usa `ticket_ado_id` en `find_by_tracker_id`; `run_incident_dev` vincula la incidencia de verdad.
- [ ] `services/telemetry_harvest.py` importa `data_dir` a nivel módulo y `telemetry_harvest.jsonl` se escribe.
- [ ] Log del día siguiente: **0** ocurrencias de `NameError: name 'ado_id' is not defined` y **0** de `NameError: name 'data_dir' is not defined` (firmas ancladas, no `grep -c NameError` a secas — C17).
- [ ] `ImportError`/`AttributeError` en `sweep_recent_runs` se loguean a **`error`**.
- [ ] `note_swallowed` está en los 12 sitios de la tabla E4, con `site` **sin número de línea**, y **nunca** levanta ni loguea.
- [ ] `swallowed_report()` declara `window.process_started_at` y `window.window_seconds`, y la tarjeta los muestra.
- [ ] `GET /api/diag/silent-failures` responde `200` y la tarjeta se ve en el panel de diagnóstico.
- [ ] `services/silence_audit.py` existe, es determinista, y `--write-baseline` produce `mudos_totales` total = **165**.
- [ ] El baseline está **commiteado** y el test **nunca** lo escribe.
- [ ] `test_ratchet_note_swallowed_cuenta_como_mudo_total` verde: instrumentar **no** baja el número congelado.
- [ ] El ratchet usa **AST** para los handlers y **`tokenize.COMMENT`** para el `# silence-ok:`; cero regex; no se escanea a sí mismo.
- [ ] Un rename no pone rojo el ratchet; agregar un `pass` sin marca, sí.
- [ ] Las **3** flags nuevas están en los **4** lugares (`config.py`, `FlagSpec`, `_CATEGORY_KEYS` → `observabilidad_notif`, `_CURATED_DEFAULTS_ON`) y se cambian **desde la UI**.
- [ ] `deployment/harness_defaults.env` **no** se editó a mano.
- [ ] Las **3** huellas están en `docs/sistema/error_fingerprints.json`, `tests/test_error_fingerprints_catalog.py` verde, y cada `self_test.clean` prueba que el patrón es angosto.
- [ ] `services/dormant_canary.py` existe, `GET /api/diag/dormant-canaries` responde, y `test_resume_canary_habria_detectado_el_bug_de_e1` está **verde**.
- [ ] El canario distingue `apagado` (flag OFF) de `dormido` (flag ON sin éxitos) y de `sin_datos`, y **no muta nada**.
- [ ] Los **4** archivos de test nuevos están en `HARNESS_TEST_FILES` (`.sh`) **y** en `run_harness_tests.ps1`.
- [ ] Ningún `pass` se convirtió en `raise`; cero cambios de flujo de control.
- [ ] Ningún test preexistente pasa a rojo (validar **por archivo**; `tests/test_harness_flags_help.py` tiene 4 fallos ajenos preexistentes que no cuentan).
