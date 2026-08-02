# Plan 290 — La degradación deja de ser muda (y el switch de GitLab llega a la UI)

- **Estado:** MEJORADO (**v1 -> v2**) — veredicto de la crítica: **RECHAZADO** en v1 (5 bloqueantes), corregido acá
- **Rama de trabajo:** `docs/plan-279`
- **Depende de:** Plan 281 F7 (los ocho guards), Plan 286 (`tracker_efectivo_de_ticket` / `tracker_declarado_del_proyecto`), Plan 289 (`persistir_stats_de_contexto` y la paridad de los 3 runtimes), Plan 218 (`CAPABILITY_MATRIX` y `ParityMatrixPanel`), Plan 257 F4 (`LogLevelPanel`, precedente de configuración que SÍ aplica)
- **Fecha:** 2026-08-02
- **Juez v2: subagente independiente, misma corrida, contexto limpio**

---

## 0. CHANGELOG v1 -> v2

Todas las afirmaciones del v1 fueron **reproducidas ejecutando**, y todos los anclajes **abiertos**. El v1 tenía una precisión de medición altísima (490 `FlagSpec` y las 23 contradicciones salieron **exactas**, línea por línea; los 13 baselines de §5.1 salieron **exactos**; 820/756 entradas de los ratchets, **exactas**) — y aun así fue **RECHAZADO**, porque el defecto no estaba en lo que midió sino en **una plomería que dio por existente**.

| # | Severidad | Qué estaba mal en v1 | Cómo quedó en v2 |
|---|---|---|---|
| **C1** | BLOQUEANTE | F2.1 re-firmaba `evaluate`, pero **el guard del sitio 5 NO vive en `evaluate`**: vive en `_evaluate_functional` (`business_preflight.py:37-44`), que recibe 5 escalares y ningún `execution_id`. El código de F2.2 referenciaba `execution_id` en un scope donde el nombre no existe ⇒ `NameError`. | §F2.1 re-firma **las dos** funciones y ajusta el despacho de `_PREDICATES` (`:191-197`). `site=` pasa a `business_preflight._evaluate_functional`. |
| **C2** | BLOQUEANTE | F2.2 usaba `tracker_efectivo_de_ticket(_ticket)`: **`_ticket` no existe en ningún scope** y en `_evaluate_functional` no hay objeto `Ticket` (evaluate lo descarta al cerrar la sesión, `:180-189`). | Se usa el resolvedor por NOMBRE que ya existe: `tracker_declarado_del_proyecto(project_name)` (`project_context.py:124`, devuelve `str \| None`). |
| **C3** | BLOQUEANTE | `execution_id` **no está** en el scope de `context_enrichment.py:1288` (la función es `_inject_run_directive(*, ticket_id, agent_type, blocks, log)`, `:1261`), y el v1 dejaba la salida "pasá `None` y documentalo". Con esa salida **F2 no escribe NUNCA en producción** y el caso 1 de F0 sólo podía ponerse verde llamando a `evaluate(execution_id=...)` desde el test: **el bloqueante central del Plan 289, reintroducido**. | La salida se **elimina**. §F2.4 traza el `execution_id` por `enrich_blocks` -> `_inject_run_directive` -> `evaluate`, y los **3 runtimes** lo pasan: ya lo tienen en la mano una línea después (`agent_runner.py:819`, `claude_code_cli_runner.py:685`, `codex_cli_runner.py:342`). Verificado abriendo los tres. |
| **C4** | BLOQUEANTE | Par mutuamente insatisfacible **entre F4.1 y F4.3**: F4.1 mete `"tracker.acceptance_criteria"` **dentro** de `ETIQUETAS`, y F4.3 + R4 justifican todo el diseño diciendo que esa key **no** está en `ETIQUETAS` y que por eso "el camino desconocido es el normal desde el día uno". Un modelo menor lo resuelve **borrando la entrada del diccionario** y degrada la interfaz a keys crudas. | §F4.1/§F4.3/§R4 reescritas: la entrada **se queda**, el camino desconocido es un **borde defensivo** (no el normal), y el test lo prueba con una key sintética declarada como tal. |
| **C5** | BLOQUEANTE | §3.1 apoyaba **toda** la decisión de "cero flags nuevas" en apagar `STACKY_TRACKER_STRICT_ROUTING`. Esa key **no existe**: `grep -rn` sobre todo el backend da **0 hits**. | Nombre real: **`STACKY_TRACKER_ROUTING_STRICT_ENABLED`** (`config.py:1455-1456` -> `"true"` = ON; `FlagSpec` en `harness_flags.py:6035`; se lee en `project_context.py:97` con fail-open `True`). La justificación se sostiene; el nombre estaba mal. |
| **C6** | IMPORTANTE | F7 corregía **sólo** `description=`. El `label` de `STACKY_TRACE_PROMPT_TEXT_ENABLED` (`harness_flags.py:2211`) **también** miente ("privacidad OFF" con `default=True`) y es el título que el operador lee. Censado: **exactamente 1** label miente. | §F7.2 corrige `label` **y** `description`; §F7.3 extiende el gate a `label`. Cierra la decisión (b) del encargo sin cambiar conducta. |
| **C7** | IMPORTANTE | F1 declaraba `log=None` en la firma y el pseudocódigo llamaba `log("warn", ...)` en el `except`: con el default, **`TypeError` dentro del manejador** ⇒ el riel "nunca levanta" se rompe justo cuando importa, y R2 queda sin cubrir. | Se agrega `log = log or _noop_log` como **primera línea**, igual que `context_enrichment.py:305`. |
| **C8** | IMPORTANTE | F5.2 decía "dentro de `put_global_config` (`:190`)" sin fijar el punto. Hay un `return 400` previo (`:219-225`) y `_write_env` va en un `try/except OSError` (`:242-245`): un `setattr` mal ubicado deja el singleton ON con el `.env` sin persistir — el **falso verde espejo**, que el test de F5.4 no atrapa. | §F5.2 fija el punto **después** de `_write_env(updates)` y **dentro** del camino en que `persisted is True`, con un test nuevo que simula el `OSError`. |
| **C9** | IMPORTANTE | El v1 "corrigió" `newProjectGitlabModel.ts:37` -> `:39`. **La corrección está mal**: `:37` es `export function normalizeGitlabUrl(...)` (el encargo tenía razón); `:39` es el `.match(...)` de adentro. La corrección de **ruta** (`src/projects/`) sí era correcta. | §9 y §2.5 corrigen la corrección. |
| **C10** | IMPORTANTE | §2.2 presentaba `test_business_preflight.py:233` como el test que congela la degradación en el productor. El `assert result.warnings` **está** en `:233`, pero ese test parchea el cliente con `RuntimeError("timeout")` (`:228`): ejerce el **`except` de red** (`:198-200`), **no** el guard no-ADO de `:94-99`. | §2.2 dice qué prueba realmente y por qué el gap sigue en pie. |
| **C11** | IMPORTANTE | F4 afirmaba "el único gate del frontend es `npx tsc --noEmit`" y acto seguido daba un segundo gate binario con `vitest`. | Se separa: **RTL/jsdom no están** ⇒ prohibido `.test.tsx` de componentes; **vitest sobre `.ts` puro SÍ corre** (medido: `parityMatrixModel.test.ts` -> 6 passed, exit 0). Son **dos** gates y los dos son obligatorios. |
| **C12** | IMPORTANTE | §F8.2 mandaba copiar la base y medir sobre la copia — sin decir que el motor corre en **WAL** (`db.py:42-49`). Medido en esta crítica: una copia del `.db` **sin sus sidecars `-wal`/`-shm`** hace que el arranque falle con `IntegrityError: UNIQUE constraint failed: tickets.stacky_project_name, tickets.tracker_type, tickets.external_id`. La métrica saldría rota o inventada. | §F8.2 exige `VACUUM INTO` (o copiar los tres archivos) y prohíbe el `cp` pelado. |
| **C13** | MENOR | Anclajes desfasados: `<LogLevelPanel />` está en `DiagnosticsPage.tsx:327` (no `:328`); `statusMark` en `parityMatrixModel.ts:83` (no `:81`); el comentario "UN solo escritor" en `global_config.py:89-92` (no `:88-93`); §3.2 decía que `criteria_repair` invoca `review_artifact` "sin fila" cuando en realidad `criteria_repair.py:82` pasa un `execution_id` real. | Corregidos en §9. |
| **C14** | MENOR | §F0.1 encabezaba "Los **6** archivos" y listaba **7**; el criterio de los ratchets decía "delta cero" para los scripts, cuando registrar 7 archivos hace que los scripts corran 7 archivos MÁS. | Encabezado a 7; el criterio del script pasa a "cada archivo nuevo pasa aislado" + delta cero sobre los 820/756 previos. |
| **A1** | ADICIÓN | — | **§F9 — el centinela de los ocho sitios**: convierte la "deuda conocida" de §6 (prosa en un `.md` que nadie vuelve a leer) en un ratchet ejecutable. Detalle abajo. |

**Lo que se verificó y quedó IGUAL porque estaba bien** (no se toca nada de esto): las 8 filas de §2.1; `warnings` en `:27` y poblado en `:94-99`; `context_enrichment.py:1319` leyendo `warnings[0]`; los 490 `FlagSpec` y las **23** contradicciones con sus 23 líneas exactas; `CAPABILITY_KEYS`=71 con ADO 38/8/25 y GitLab **34/14/21/2**; `tracker.comments.list` **sí** es key real y `tracker.acceptance_criteria` **no**; `_MANAGED_KEYS` con `STACKY_GITLAB_ENABLED` en `global_config.py:82`; `_write_env` sin `setattr`; `api/projects.py:141-142` textual; `config.py:1297-1299` en `"false"` y `.env:7` en `true`; `test_self_review.py` inexistente con **exit 4**; los 13 baselines de §5.1 **uno por uno**; `tsc --noEmit` en **0 errores**; 820/756 entradas y la trampa de la coma final del `.ps1`; el allowlist con 207 líneas / 194 efectivas y `tests/test_harness_capabilities.py` en la **97**.

---

## 1. Objetivo y KPI

### 1.1 Objetivo en una frase

Cuando Stacky corre sobre un tracker que no es Azure DevOps y **decide a propósito no hacer algo**, hoy devuelve un valor neutro y no queda rastro para el operador; este plan hace que esa decisión quede **declarada en la metadata de la ejecución y visible en la interfaz**, sin cambiar ni un valor de retorno.

### 1.2 Qué NO es este plan

**No se arregla ninguna degradación.** Las degradaciones del Plan 281 F7 son **correctas y deliberadas**: `Microsoft.VSTS.Common.AcceptanceCriteria` no existe en GitLab, WIQL no existe en GitLab, `System.Rev` no existe en GitLab. Devolver el valor neutro es la conducta **correcta** y **se conserva byte a byte**.

> ⚠️ **AVISO AL IMPLEMENTADOR (leer dos veces).** Si en algún momento te parece que hay que "arreglar" `acceptance_criteria.py:43` o `self_review.py:57` para que traigan los criterios desde GitLab: **NO**. Ese campo no existe en GitLab. Cambiar el `return ""` por otra cosa es un cambio de semántica que rompe `review_artifact` (que espera `""` para devolver `skipped_reason="no_acceptance_criteria"`) y `acceptance_contract._get_criteria_text` (que trata `""` como "sin criterios"). Lo único que este plan agrega es **una línea de declaración antes del `return`**. El `return` no se toca.

### 1.3 KPIs binarios

| # | KPI | Hoy (medido 2026-08-02) | Meta |
|---|---|---|---|
| **K1** | % de ejecuciones que atraviesan un sitio de degradación instrumentado y lo declaran en `metadata["capability_degraded"]` | **0 %** (la clave no existe en el modelo de datos) | **100 %** |
| **K2** | Cantidad de `FlagSpec` cuya **descripción o label** afirma un default y el código tiene el contrario | **24** = 23 descripciones + 1 label (`STACKY_TRACE_PROMPT_TEXT_ENABLED`), medido por AST, §2.4 | **0** |
| **K3** | `STACKY_GITLAB_ENABLED` modificable desde la interfaz, con efecto en caliente verificable | **No** (0 referencias en `frontend/src/`) | **Sí** |
| **K4** | `base_url` de GitLab normalizada server-side igual que en el cliente | **No** (`rstrip("/")` vs. `normalizeGitlabUrl`) | **Sí** |

K1 se mide con el script de §F8.2. K2 se mide con los tests de §F7.3, que son además el guardián permanente.

> ⚠️ **v2 — K1 necesita un denominador cerrado o no es un KPI, es una aspiración.** "% de ejecuciones que atraviesan un sitio instrumentado" no se puede medir mirando la base: no hay forma de saber, a posteriori, si una ejecución *atravesó* el guard. **Denominador congelado, y es el único que el script de §F8.2 puede calcular sin adivinar:**
>
> > **K1 = (ejecuciones con `metadata["capability_degraded"]` no vacío) / (ejecuciones de proyectos NO-ADO, con `metadata["ado_context"]` presente, iniciadas después del commit de F2)**
>
> El `ado_context` del Plan 289 es la prueba de que esa corrida **pasó por `enrich_blocks`**, que es exactamente el camino que F2 instrumenta. Sin ese filtro, el denominador incluye corridas que nunca podían declarar y el KPI baja por construcción. **Meta: ≥ 95 %** (no 100 %: una corrida que muere entre el enriquecimiento y el commit de la fila es un hueco real y honesto, no un defecto a perseguir).

---

## 2. Por qué ahora — el gap, con evidencia

### 2.1 El Plan 281 F7 dejó ocho sitios que deciden en silencio

Censo exacto, por símbolo (`grep -rn "Plan 281 F7 sitio" --include=*.py`, ejecutado 2026-08-02):

| # | Archivo:línea del comentario | Línea del guard | Valor neutro que devuelve |
|---|---|---|---|
| 1 | `backend/api/agents.py:1911` | `:1921` | `sections` (lista vacía) |
| 2 | `backend/api/tickets.py:5102` | `:5111` | `"unknown"` |
| 3 | `backend/api/tickets.py:7763` | `:7762` | `_baseline_rev = None` |
| 4 | `backend/services/acceptance_criteria.py:38` | `:43` | `""` |
| 5 | `backend/services/business_preflight.py:85` | `:94` | `ok=True, mode=None` |
| 6 | `backend/services/self_review.py:50` | `:57` | `""` |
| 7 | `backend/services/similar_tickets.py:113` | `:122` | `[]` |
| 8 | `backend/services/ticket_assigner.py:390` | `:401` | `None` |

El más dañino es el **5**: `BusinessPreflightResult(ok=True, mode=None, ...)`. El operador que mira ese resultado lee **"preflight OK"**. No se validó nada.

> ⚠️ **v2 / C1 — dónde vive DE VERDAD el sitio 5, y por qué esto decidió el rediseño de F2.**
> El guard de `:94` **no está en `evaluate`**. Está en `_evaluate_functional` (`business_preflight.py:37-44`), cuya firma completa es:
>
> ```python
> def _evaluate_functional(*, ado_id: int, work_item_type: str, ado_state: str,
>                          stacky_project_name: str | None, tracker_project: str | None
> ) -> BusinessPreflightResult:
> ```
>
> `evaluate` (`:161`) carga el `Ticket` dentro de un `session_scope` (`:179-189`), **se queda sólo con escalares** y despacha por tabla:
>
> ```python
> return _PREDICATES[agent_type](
>     ado_id=..., work_item_type=..., ado_state=...,
>     stacky_project_name=..., tracker_project=...,
> )   # :191-197
> ```
>
> Consecuencias duras, y las dos las erró el v1: **(1)** re-firmar sólo `evaluate` no le da `execution_id` al guard; hay que re-firmar **las dos** y agregar el kwarg al despacho. **(2)** en ese scope **no hay objeto `Ticket`**, así que `tracker_efectivo_de_ticket(...)` (que hace `getattr(ticket, "tracker_type")`) es inaplicable: el resolvedor correcto es el hermano por nombre, `tracker_declarado_del_proyecto(project_name)`.
>
> Y el guard **no se puede mover** a la cabecera de `evaluate` para simplificar: el propio comentario del 281 lo prohíbe por escrito en `business_preflight.py:89-93` ("DESVÍO DECLARADO... gatear arriba se lo llevaría puesto para GitLab"), y `tests/test_plan281_sitios_ado_only.py` (18 passed) lo vigila.

### 2.2 El dato YA EXISTE en el productor y muere antes del consumidor operativo

Este es el hallazgo central y hay que escribirlo con precisión, porque una versión simplificada ("nadie lee el warning") llevaría al implementador a romper algo que hoy funciona.

`BusinessPreflightResult` **ya declara** el campo (`backend/services/business_preflight.py:27`):

```python
warnings: list[str] = field(default_factory=list)
```

y el sitio 5 **ya lo puebla** (`business_preflight.py:94-99`):

```python
if not tracker_is_azure_devops(project_name) and ruteo_estricto_por_tracker():
    return BusinessPreflightResult(
        ok=True,
        mode=None,
        warnings=["tracker no-ADO: sin cross-check de comentarios"],
    )
```

Quién lo consume hoy, verificado uno por uno:

| Consumidor | Lee `.warnings` | Qué hace |
|---|---|---|
| `backend/services/context_enrichment.py:1319` | **SÍ, pero solo `warnings[0]`** | `_reason = _bp.reason or (_bp.warnings[0] if _bp.warnings else "preflight_off")` → entra al bloque `run-directive` del prompt. **El AGENTE sí se entera.** |
| `backend/api/agents.py:542-561` | **NO** | Lee `.ok`, `.check`, `.reason`. Con `ok=True` sigue de largo y descarta el objeto entero. |
| Cualquier otro módulo de `api/`, `services/`, `harness/` | **NO** | `grep -rn "\.warnings" api/ services/ harness/ agent_runner.py` no devuelve ningún consumidor de `BusinessPreflightResult`. |

**Conclusión precisa del gap:** el dato **llega al agente** (por el prompt) y **no llega nunca al operador** (no hay metadata, no hay interfaz, no hay forma de contar cuántas corridas degradaron). Además `warnings[0]` **descarta del segundo en adelante**.

Y hay una confirmación de que esto es el defecto del 289 repitiéndose: `backend/tests/test_business_preflight.py:233` afirma

```python
assert result.warnings
```

o sea, **hay un test que verifica el campo en el PRODUCTOR y ningún test ni consumidor de producción que lo verifique en el destino**.

> ⚠️ **v2 / C10 — precisión sobre ese test, porque el v1 lo presentó de más.** El `assert` está en `:233`, pero ese caso parchea el cliente con `_patch_client(monkeypatch, raises=RuntimeError("timeout"))` (`:228`): lo que ejerce es el **`except` de red** de `evaluate` (`:198-200`, `warnings=[f"preflight error: {exc}"]`), **no** el guard no-ADO de `:94-99`. O sea: el campo `warnings` tiene un test de productor **para otro camino**, y la degradación por tracker **no tiene ni siquiera eso**. El gap es *peor* de lo que decía el v1, no mejor — pero hay que escribirlo bien, porque un implementador que abra `:233` esperando ver el caso GitLab no lo va a encontrar y va a pensar que el plan miente.

El riel sigue siendo el del Plan 289: *poné el assert en el consumidor, no donde se produce*.

### 2.3 El master switch de GitLab no está en la interfaz — pero el seam del backend YA existe

Verificado el 2026-08-02:

- `backend/config.py:1297-1299` → `os.getenv("STACKY_GITLAB_ENABLED", "false")`. **Default `false` en código.**
- `backend/.env:7` → `STACKY_GITLAB_ENABLED=true`. Está encendido **solo** por el `.env` del operador.
- **No tiene `FlagSpec`.** Y `backend/api/harness_flags.py:134` lo dice explícitamente: *"global_config (STACKY_GITLAB_ENABLED), que NO vive en este registro"*.
- **PERO** `backend/api/global_config.py:82` ya lo tiene en `_MANAGED_KEYS`. O sea: `PUT /api/global-config` **ya acepta la clave hoy**.
- `grep -rn "STACKY_GITLAB_ENABLED" frontend/src/` → **cero resultados**. Tampoco `GITLAB_URL`, ni `STACKY_GITLAB_GROUP`, ni `STACKY_GITLAB_EPICS_NATIVE`. **Ninguna** clave GitLab de `_MANAGED_KEYS` tiene superficie de interfaz.
- Hoy se enciende **de costado**, al crear un proyecto GitLab: `backend/api/projects.py:141-142`.
- Y `backend/services/setup_guides.py:147` ya lo denuncia por escrito: *"STACKY_GITLAB_ENABLED, y hoy no hay ninguna pantalla que la muestre"*.

**Sub-defecto que un modelo menor NO puede inferir y que decide el diseño de F5:** `_write_env` (`global_config.py:136-168`) escribe el `.env` y `os.environ`, **pero nunca hace `setattr` sobre el singleton `config.config`**. Y todos los consumidores leen `config.config.STACKY_GITLAB_ENABLED` (`services/tracker_provider.py:133`, `ci_provider.py:121`, `ci_variables.py:87`, `ci_preflight.py:39`, `ci_logs_provider.py:38`). Por lo tanto: **un panel que solo llame al PUT diría "guardado" y el motor seguiría con el valor viejo hasta reiniciar.** Sería un falso verde nuevo — precisamente el que `LogLevelPanel.tsx:9-11` documenta como razón para no usar el panel de flags.

`backend/api/projects.py:141-142` ya resuelve esto y es el patrón a copiar:

```python
_write_global_env({"STACKY_GITLAB_ENABLED": "true"})   # .env + os.environ
setattr(_config.config, "STACKY_GITLAB_ENABLED", True)  # hot-apply al singleton
```

### 2.4 Veintitrés flags mienten sobre su default (no dos)

El encargo hablaba de 2 flags con anclajes `harness_flags.py:4591` y `:4446`. **Esos dos anclajes son incorrectos** (ver §9, tabla de anclajes). La medición real, por AST sobre `backend/services/harness_flags.py` cruzada contra `backend/config.py`, da **23** sobre **490 `FlagSpec`**:

| # | Flag | Línea del `FlagSpec` | Dice | `default=` | `config.py` |
|---|---|---|---|---|---|
| 1 | `STACKY_TRACE_PROMPT_TEXT_ENABLED` | 2207 | OFF | `True` | `"true"` |
| 2 | `STACKY_RAG_CATALOG_ENABLED` | 2636 | OFF | `True` | (sin entrada) |
| 3 | `STACKY_DOCS_GRAPH_ENABLED` | 2650 | OFF | `True` | `"true"` |
| 4 | `STACKY_DOCS_RAG_HYBRID_ENABLED` | 2679 | OFF | `True` | `"true"` |
| 5 | `STACKY_DOCS_DOCUMENTER_ENABLED` | 2740 | OFF | `True` | `"true"` |
| 6 | `STACKY_DOCS_STALENESS_ENABLED` | 2804 | OFF | `True` | `"true"` |
| 7 | `STACKY_PROCESS_DISCIPLINE_ENABLED` | 3141 | OFF | `True` | `"true"` |
| 8 | `STACKY_PROJECT_AUTOPROFILE_ENABLED` | 3182 | OFF | `True` | (sin entrada) |
| 9 | `STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED` | 3231 | OFF | `True` | (sin entrada) |
| 10 | `INTENT_PREFLIGHT_ENABLED` | 3255 | OFF | `True` | `"true"` |
| 11 | `STACKY_ARTIFACT_RESCUE_ENABLED` | 3287 | OFF | `True` | (sin entrada) |
| 12 | `STACKY_PUSH_REJECTIONS_ENABLED` | 3315 | OFF | `True` | `"true"` |
| 13 | `STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED` | 3354 | OFF | `True` | (sin entrada) |
| 14 | `STACKY_EPIC_CATALOG_GATE_ENABLED` | 3411 | OFF | `True` | (sin entrada) |
| 15 | `STACKY_TASK_GATE_ENABLED` | 3426 | OFF | `True` | (sin entrada) |
| 16 | `STACKY_TASK_GATE_BLOCKING` | 3439 | OFF | `True` | (sin entrada) |
| 17 | `STACKY_DETERMINISTIC_TASK_STATES_ENABLED` | 3454 | OFF | `True` | `"true"` |
| 18 | `STACKY_ADAPTIVE_SELECTOR_ENABLED` | 3566 | OFF | `True` | `"true"` |
| 19 | `STACKY_EPIC_PORTFOLIO_ENABLED` | 3593 | OFF | `True` | (sin entrada) |
| 20 | `STACKY_EPIC_DECOMPOSITION_ENABLED` | 3635 | OFF | `True` | (sin entrada) |
| 21 | `STACKY_ADO_EDIT_LEARNING_ENABLED` | 3672 | OFF | `True` | (sin entrada) |
| 22 | `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` | 4608 | OFF | `True` | `"true"` |
| 23 | `STACKY_GITLAB_DEEP_LINKS_ENABLED` | 4753 | OFF | `True` | `"true"` |

> Las líneas son del `FlagSpec(` (nodo AST), no del texto. **Reproducí la medición antes de editar** (§F7.1): si el número que te da no es 23, las líneas se movieron y hay que re-medir, no adivinar.

Cuatro verificadas a mano contra el texto real:

- `STACKY_TRACE_PROMPT_TEXT_ENABLED` → *"...incluye el texto completo del prompt (JSON de context_blocks) en la metadata. **Privacidad: default OFF.** Solo activar en ambientes controlados donde el contenido del prompt no es sensible."* — y está **ON**. Es la más grave: la descripción promete una garantía de privacidad que el código no cumple.
- `STACKY_ARTIFACT_RESCUE_ENABLED` → *"...lo publica. **Default OFF.**"* — `default=True`, `env_only=True`.
- `STACKY_TASK_GATE_BLOCKING` → *"...impide la creación en ADO (devuelve 400 TASK_GATE_BLOCKED). **Default OFF.**"* — `default=True`, `env_only=True`.
- `STACKY_GITLAB_DEEP_LINKS_ENABLED` → *"...muestra el ID como texto plano. **Default OFF.** Activa cuando..."* — `default=True`.

### 2.5 `base_url` se normaliza solo del lado del cliente

- Cliente: `frontend/src/projects/newProjectGitlabModel.ts:37` → `export function normalizeGitlabUrl(raw: string): string`, cuerpo en `:38-40`: saca barra final, `/api/vN` **y cualquier path** (arreglo del Plan 276 F8.3 al namespace pegado). *(v2 / C9: el v1 "corrigió" `:37` a `:39` y la corrección estaba mal — `:37` era correcto; `:39` es el `.match(...)` interno. Lo que sí estaba mal en el encargo era la **ruta**: es `src/projects/`, no `src/services/`.)*
- Servidor: `backend/project_manager.py:670` → `"base_url": url.rstrip("/")`. **Solo la barra final.**

Cualquier alta que no pase por ese formulario (importación, edición manual del JSON, un cliente futuro) deja `https://host/grupo/proyecto` como base y todas las llamadas salen a `.../grupo/proyecto/api/v4/...` → 404.

### 2.6 Lo que ya existe y hay que reusar (no construir de nuevo)

| Pieza | Dónde | Estado medido |
|---|---|---|
| `CAPABILITY_MATRIX` | `backend/services/provider_capabilities.py:95` | 71 capacidades. ADO: 38 full / 8 partial / 25 absent. GitLab: 34 full / 14 partial / **21** absent / 2 n/a. |
| `capability_status` / `supports` / `capability_loss` | `provider_capabilities.py:344` / `:349` / `:354` | `capability_status` ya es fail-closed: lo desconocido devuelve `"absent"`. |
| Endpoint de paridad | `backend/api/parity.py:15` → `GET /api/parity/matrix` | Gateado por `STACKY_PROVIDER_PARITY_ENABLED`; 404 si está apagada. |
| `ParityMatrixPanel` | `frontend/src/components/ParityMatrixPanel.tsx` | Montado en `DiagnosticsPage.tsx:331`, **sin prop `project`**. |
| `parityMatrixModel.ts` | `frontend/src/services/parityMatrixModel.ts` (`statusLabel` `:75-77`, `statusMark` **`:83`**) | Lógica pura testeable; ya caen a "Ausente"/"✕" en lo desconocido. **`vitest` corre este archivo hoy: 6 passed, exit 0** — es la prueba de que los tests `.ts` de F4/F5 son ejecutables. |
| `persistir_stats_de_contexto` | `backend/services/context_enrichment.py:284` | Idioma de escritura en `metadata_dict`: nunca levanta, idempotente, escribe temprano. Llamada por los 3 runtimes: `agent_runner.py:819`, `claude_code_cli_runner.py:685`, `codex_cli_runner.py:342`. |
| `ruteo_estricto_por_tracker` | `backend/services/project_context.py:78` | Kill-switch de los 8 guards. Se lee del **objeto** `config`, nunca con `os.getenv` (lo vigila `test_flags_env_read_meta.py`). |
| `LogLevelPanel` | `frontend/src/components/LogLevelPanel.tsx` (motivo en `:9-11`) | Precedente exacto de "configuración del operador que SÍ aplica en caliente", montado en **`DiagnosticsPage.tsx:327`** *(v2: el v1 decía `:328`)*. |
| Patrón de aviso en el drawer | `ExecutionDetailDrawer.tsx:74-102` | `metadata.egress_sentinel`, `metadata.local_insight`, `metadata.blocked_downgrade`: cada uno un sub-componente + modelo puro. |

---

## 3. Principios y guardarraíles

1. **El valor neutro no se toca.** Todas las fases agregan una llamada **antes** del `return`. Ningún `return` cambia de valor, de tipo ni de posición. Hay un test dedicado por sitio (§F2.4, §F3.4).
2. **Cero flags nuevas.** Justificación completa en §3.1.
3. **Nunca levanta.** El registro de degradación es telemetría: cualquier excepción se traga y se loguea. Una corrida jamás se cae por no poder anotar un aviso.
4. **Human-in-the-loop.** Nada de esto decide por el operador: declara y muestra. `STACKY_GITLAB_ENABLED` sigue siendo una perilla que el operador mueve a mano.
5. **Mono-operador sin auth.** No hay RBAC. Un `403` acá significaría "flag apagada", nunca "permiso". Ninguna fase agrega chequeos de permiso.
6. **Backward-compatible.** No cambia ninguna firma pública. `metadata["capability_degraded"]` es una clave **nueva**: su ausencia es el estado válido de todas las ejecuciones históricas y de toda corrida que no degrade.
7. **Paridad de 3 runtimes verificada, no asumida.** §3.2.
8. **Trabajo del operador: ninguno** en todas las fases. Se declara explícitamente fase por fase.

### 3.1 Por qué este plan NO registra ninguna flag nueva

El riel dice que toda flag nueva nace ON salvo que queme tokens en reposo o escriba en un sistema real. Registrar una degradación es **solo lectura + una escritura local en la propia fila de la ejecución** ⇒ le correspondería nacer ON. **Pero una flag que nace ON y no apaga nada útil es una flag de más**, y en este repo cuesta caro:

- Una flag nueva es un bloque atómico con **ocho guardianes**, incluido `test_requires_map_is_frozen`, que está indexado **por key de flag**: no se esquiva ni declarando `requires=` ni omitiéndolo.
- Registrarla ON obliga a los TRES lugares: `config.py` con `"true"`, `FlagSpec(default=True)` y la key en `_CURATED_DEFAULTS_ON` de `backend/tests/test_harness_flags.py`.

**Y ya existe el kill-switch correcto.** Los 8 sitios están, sin excepción, dentro de `... and ruteo_estricto_por_tracker()` (verificado en las 8 líneas de §2.1). La declaración de degradación va **dentro de ese mismo `if`**. Por lo tanto:

> Apagar **`STACKY_TRACKER_ROUTING_STRICT_ENABLED`** (la flag que lee `ruteo_estricto_por_tracker`) apaga el guard **y** su declaración, en un solo movimiento, y el rollback es byte-idéntico al estado previo al Plan 281 F7. Una flag nueva sería un segundo interruptor para la misma luz.

> ⚠️ **v2 / C5 — el v1 la llamaba `STACKY_TRACKER_STRICT_ROUTING` y esa key NO EXISTE** (`grep -rn "STACKY_TRACKER_STRICT_ROUTING" --include=*.py` sobre todo el backend = **0 hits**). Como esta flag es el ÚNICO argumento por el que este plan no registra ninguna flag nueva, un nombre inventado acá derribaba una decisión de alcance entera. Los datos reales, verificados:
>
> | Qué | Dónde | Valor |
> |---|---|---|
> | Lectura | `services/project_context.py:97` | `bool(getattr(_cfg, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True))`, fail-open `True` (`:98-99`) |
> | Default efectivo | `backend/config.py:1455-1456` | `os.getenv("STACKY_TRACKER_ROUTING_STRICT_ENABLED", "true")` ⇒ **ON** |
> | Registro | `services/harness_flags.py:6035` (`key=`) y `:605` (categorización) | registrada, con superficie de UI |
>
> **El default se leyó del `os.getenv`, no del comentario** (en este repo los comentarios de default mienten 23 veces, §2.4). Nace ON y es sólo-lectura hacia afuera: cumple el riel. La justificación de "cero flags nuevas" **se sostiene**; lo único que estaba mal era el nombre.

Para F4 (interfaz) el gate ya es `STACKY_PROVIDER_PARITY_ENABLED`: apagada, el endpoint da 404 y `ParityMatrixPanel` no se monta. El aviso nuevo del drawer se alimenta de `metadata`, que simplemente no existe si no hubo degradación: no necesita gate propio.

**Consecuencia operativa para el implementador:** ninguna fase de este plan toca `backend/services/harness_flags.py` para AGREGAR una flag. F7 lo toca **solo para corregir texto de `description=`**, sin tocar `key`, `type`, `default`, `group`, `requires`, `env_only` ni `min/max`.

### 3.2 Paridad de los 3 runtimes — verificada archivo por archivo

El Plan 289 encontró que 2 de 3 runtimes tiraban el stat. Acá se verificó antes de diseñar, y los dos sitios elegidos tienen paridad **por construcción**, cada uno por una vía distinta:

**Sitio `business_preflight`** — se alcanza por dos caminos, ambos comunes a los 3 runtimes, **pero sólo UNO sirve como destino**:

| Camino | Archivo:línea | Cubre | ¿Tiene destino donde anotar? |
|---|---|---|---|
| Lanzamiento (API) | `backend/api/agents.py:542` | Los 3: endpoint de arranque, anterior a la bifurcación de runtime. | **NO.** En ese punto todavía no existe la fila de `AgentExecution`. **Se deja como está.** |
| Enriquecimiento | `backend/services/context_enrichment.py:1288` | Los 3: el armador de bloques que el Plan 289 F6 unificó. | **SÍ, pero hay que traerlo** — ver el recuadro. |

> ⚠️ **v2 / C3 — la plomería que el v1 dio por existente, resuelta y CERRADA (ya no hay "salida documentada").**
>
> Medido: la función que contiene `:1288` es **`_inject_run_directive(*, ticket_id, agent_type, blocks, log)`** (`context_enrichment.py:1261-1334`). **`execution_id` NO está en su scope.** Su único llamador de producción es `context_enrichment.py:133`, dentro de **`enrich_blocks(*, ticket_id, agent_type, raw_blocks, project_ctx, log)`** (`:60-67`) — que **tampoco** lo tiene.
>
> Con la "salida" del v1 (pasar `None`), y sumado a que `api/agents.py:542` queda excluido a propósito, **`declarar()` jamás recibiría un `execution_id` no nulo desde ningún camino de producción**: F2 quedaría construida, verde y muerta, y el caso 1 de F0 sólo podría ponerse verde llamando a `evaluate(execution_id=...)` desde el propio test. Eso es **exactamente** el bloqueante central del Plan 289 reintroducido — assert en el productor, cero consumidores. **Por eso la salida se elimina.**
>
> **Y la plomería es barata, porque el dato ya está a una línea de distancia en los tres runtimes** (verificado abriendo los tres):
>
> | Runtime | Llama a `enrich_blocks` en | Y en la línea siguiente ya usa `execution_id` en |
> |---|---|---|
> | GitHub Copilot Pro | `agent_runner.py:809-815` | `persistir_stats_de_contexto(execution_id=execution_id, ...)` — `:819-821` |
> | Claude Code CLI | `services/claude_code_cli_runner.py:677-683` | `:685-687` |
> | Codex CLI | `services/codex_cli_runner.py:334-340` | `:342-344` |
>
> **La cadena a construir (toda con `execution_id: int | None = None` keyword-only, o sea backward-compatible en cada eslabón):**
>
> ```
> agent_runner.py:809 ─┐
> claude_..._runner:677 ├─► enrich_blocks(..., execution_id=execution_id)
> codex_..._runner:334 ─┘        │
>                                ▼
>                     _inject_run_directive(..., execution_id=execution_id)   # :133
>                                │
>                                ▼
>                     business_preflight.evaluate(..., execution_id=execution_id)  # :1288
>                                │
>                                ▼
>                     _PREDICATES[agent_type](..., execution_id=execution_id)  # :191-197
>                                │
>                                ▼
>                     _evaluate_functional(..., execution_id) ──► declarar(...)   # el guard de :94
> ```
>
> **Los 11 call sites de `enrich_blocks` en `tests/` NO se tocan** (el default `None` los deja idénticos). El único que se re-firma además es `_PREDICATES`, que hoy tiene **un solo** predicado (`"functional"`, `business_preflight.py:156-158`).

**Sitio `self_review`** — se alcanza por `apply_to_execution(execution_id=...)` desde tres call sites distintos, uno por runtime:

| Runtime | Archivo:línea |
|---|---|
| GitHub Copilot Pro (vía `agent_runner`) | `backend/services/agent_completion_internal.py:174` |
| Claude Code CLI | `backend/services/claude_code_cli_runner.py:3227` |
| Codex CLI | `backend/services/codex_cli_runner.py:2008` |

⚠️ **Los tres llaman a `apply_to_execution`, no a `review_artifact`.** `apply_to_execution` llega a `review_artifact` por `self_review.py:168`. La instrumentación va en `review_artifact` (§F3), que es el punto único por el que pasan los tres. **No** hay que instrumentar los tres call sites: sería triplicar el mismo registro.

**Fallback explícito:** si por cualquier motivo `execution_id` es `None` o apunta a una fila inexistente, `declarar()` devuelve `False` y no escribe. No levanta, no cambia el retorno de la función que la llamó.

> *v2 / C13:* el v1 daba como ejemplo de fallback a `harness/criteria_repair.py`. **Ese ejemplo es falso**: `criteria_repair.py:82` llama `review_artifact(execution_id=execution_id, artifact_text=artifact_text)` con un `execution_id` **real**, así que ese camino **sí** declara (y está bien que declare). El fallback real es el de una fila borrada.
>
> **Un tercer camino que hay que conocer y no hay que "arreglar":** `apply_to_execution` puede cortocircuitar por caché (`self_review.py:162-170`, `get_cached_review`) y **no** llamar a `review_artifact`. En esa corrida no se declara — y está bien: la degradación ya se declaró en la corrida que llenó la caché, y el dedup de F1 la haría no-op igual.

---

## 4. Fases

Cada fase es autocontenida y se commitea sola. El orden es de dependencia: F1 antes que F2/F3; F2/F3 antes que F4.

Comando de test, **siempre por archivo, nunca la suite entera**:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q
```

> El intérprete es `backend/.venv` (py3.13.5), **no** `backend/venv` (py3.11.9, sin las dependencias).

---

### F0 — Los dos centinelas en ROJO

**Objetivo:** dejar escrito, en un test que hoy falla, qué significa "la degradación dejó rastro".

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan290_degradacion_declarada.py`

**Casos (los 2 son de EJECUCIÓN, no estáticos):**

1. `test_preflight_no_ado_declara_la_degradacion_en_la_metadata` — crea un `Ticket` de un proyecto no-ADO y un `AgentExecution`, y **entra por `context_enrichment.enrich_blocks(ticket_id=..., agent_type="functional", raw_blocks=[], execution_id=<id>)`**, o sea por el MISMO seam que usan los 3 runtimes. Afirma que `AgentExecution.metadata_dict["capability_degraded"]` contiene una entrada con `capability == "tracker.comments.list"`.
2. `test_self_review_sin_criterios_declara_la_degradacion` — ídem con `self_review.review_artifact(execution_id=..., artifact_text="x")`, afirmando una entrada con `capability == "tracker.acceptance_criteria"`.

> ⚠️ **v2 / C3 — el caso 1 entra por `enrich_blocks`, NO por `business_preflight.evaluate`.** Este es el punto entero del plan y no es negociable. Llamar a `evaluate(execution_id=...)` directo desde el test verifica **el productor**: es el bloqueante central del Plan 289, y un test así se pone verde sin que ningún runtime escriba nunca nada. El test tiene que atravesar la cadena completa de §3.2, que es la que los 3 runtimes ejercen. Si `enrich_blocks` todavía no acepta `execution_id`, el test falla con `TypeError: unexpected keyword argument` — **y ese también es un rojo válido de F0**, porque describe exactamente la plomería que falta (a diferencia de un `ImportError`, que sería una tautología sobre F1).

**Cómo se comprueba el ROJO (obligatorio, y así se reporta):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_degradacion_declarada.py" -q
```

Debe salir **2 failed**. Modos de falla **aceptables**: `KeyError: 'capability_degraded'`, un `assert` sobre un `dict` sin esa clave, o `TypeError: enrich_blocks() got an unexpected keyword argument 'execution_id'` (la plomería de §3.2 todavía no existe). Modo **inaceptable**: `ImportError` / `ModuleNotFoundError` — eso prueba que el módulo de F1 no existe, que es una tautología, no que el comportamiento falta. **Pegá la salida real en el commit de F0.**

> **Trampa de gate (molde b).** Estos dos tests **deben ejecutar** el camino real. Un test que se limite a `grep` el fuente buscando la llamada a `declarar(` pasa igual si la llamada está dentro de una rama muerta. Se verifica el efecto en la fila de la base, no la presencia del símbolo en el archivo.

**Criterio binario:** el comando de arriba sale con **exit code 1** y **2 failed**, y ninguno de los 2 fallos es un error de importación.

**Flag:** ninguna. **Impacto por runtime:** ninguno (solo agrega un archivo de tests). **Trabajo del operador: ninguno.**

**Registro en los ratchets:** ver §F0.1.

#### F0.1 — Registro del archivo de tests en los DOS ratchets

> ⚠️ **Los dos archivos NO tienen "ratchet" en el nombre.** Buscarlos por esa palabra no los encuentra. Son, verificado el 2026-08-02:
>
> | Archivo | Símbolo del array | Entradas |
> |---|---|---|
> | `Stacky Agents/backend/scripts/run_harness_tests.sh` | `HARNESS_TEST_FILES=(` (línea 20) | **820** |
> | `Stacky Agents/backend/scripts/run_harness_tests.ps1` | `$HarnessTestFiles = @(` (línea 13) | **756** |
>
> **Divergen en 64 entradas.** No asumas que lo que está en uno está en el otro.

**Sintaxis exacta de cada uno — son distintas y NO son intercambiables.**

`run_harness_tests.sh` — dos espacios de indent, ruta **cruda sin comillas**, **sin coma**:

```bash
  tests/test_plan288_cuenta_local.py
  # Plan 289 - El agente deja de trabajar a ciegas sobre un ticket de GitLab
  tests/test_plan289_contexto_por_tracker.py
  tests/test_plan289_stat_de_contexto.py
)
```

`run_harness_tests.ps1` — dos espacios de indent, ruta **entre comillas dobles**, **coma al final salvo la última**:

```powershell
  "tests/test_plan288_cuenta_local.py",
  # Plan 289 - El agente deja de trabajar a ciegas sobre un ticket de GitLab
  "tests/test_plan289_contexto_por_tracker.py",
  "tests/test_plan289_stat_de_contexto.py"
)
```

> ⚠️ **Trampa del `.ps1`:** hoy `"tests/test_plan289_stat_de_contexto.py"` es la última y **no lleva coma**. Al agregar entradas nuevas después hay que **agregarle la coma a esa línea**. En el `.sh` no hace falta tocar la línea previa. Olvidarse rompe el array de PowerShell.

**Reglas:**

- El registro va **en el commit que crea el archivo de tests**, no al final del plan: los ratchets son trampa de **commit**, no solo de edición.
- **Anclá por SÍMBOLO, no por línea.** La cola se mueve en horas (pasó de `test_plan287_*` a `test_plan288_*` a `test_plan289_*` en un día). Buscá la última entrada `tests/test_plan28*` o `tests/test_plan29*` y agregá **después**, con un comentario `# Plan 290 - La degradacion deja de ser muda` siguiendo el estilo (sin tildes, igual que los vecinos).
- **Rutas relativas al backend y sin espacios** (`tests/test_plan290_*.py`). Los ratchets no admiten rutas con espacios.
- **Allowlist:** `Stacky Agents/backend/tests/harness_ratchet_allowlist.txt` **existe** (207 líneas, 194 efectivas). Verificado: **no menciona** `self_review` ni `business_preflight`; la única línea con `capability` es `tests/test_harness_capabilities.py  # pendiente-de-triage`, que **no** es ninguno de los archivos de este plan. Por lo tanto **ningún archivo nuevo de este plan necesita salir del allowlist** — pero si al implementar agregás un archivo que sí figure ahí, **hay que sacarlo**: estar en el ratchet y en el allowlist son dos declaraciones contradictorias.

**Los OCHO archivos de tests que este plan debe registrar en AMBOS** *(v2 / C14: el v1 encabezaba "6" y listaba 7; con §F9 son 8)*:

```
tests/test_plan290_degradacion_declarada.py      (F0)
tests/test_plan290_registro_degradacion.py       (F1)
tests/test_plan290_preflight_no_regresion.py     (F2)
tests/test_plan290_self_review_no_regresion.py   (F3)
tests/test_plan290_gitlab_switch_ui.py           (F5)
tests/test_plan290_base_url_normalizada.py       (F6)
tests/test_plan290_defaults_no_mienten.py        (F7)
tests/test_plan290_sitios_clasificados.py        (F9 — ADICIÓN ARQUITECTO)
```

Los archivos de `frontend/src/**/__tests__/*.ts` **no** van a estos ratchets: son de `vitest`, no del arnés de pytest.

**Criterio binario (v2 / C14 — corregido).** "Delta cero sobre los scripts" era un criterio mal planteado: registrar archivos hace que los scripts corran **más** archivos, así que el veredicto puede cambiar legítimamente. Los tres criterios correctos son:

1. `grep -c "^  tests/" scripts/run_harness_tests.sh` pasa de **820** a **828**, y `grep -cE '^\s+"tests/' scripts/run_harness_tests.ps1` de **756** a **764**. Después de cada fase, +1 en cada uno.
2. **Cada archivo nuevo pasa AISLADO** con el comando de su fase (es la condición que el arnés verifica).
3. Los **820/756** que ya estaban **no cambian de veredicto**: el diff de los dos scripts sólo agrega líneas (más la coma del `.ps1`), nunca modifica ni borra una existente. Se comprueba con `git diff -- scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` y contando los `-` (deben ser **1** en el `.ps1`, el de la línea que gana la coma, y **0** en el `.sh`).

---

### F1 — El registro de degradación

**Objetivo:** un único escritor de `metadata["capability_degraded"]`, con la misma disciplina que `persistir_stats_de_contexto`.

**Archivo nuevo:** `Stacky Agents/backend/services/capability_degradation.py`

**Símbolos exactos a crear:**

```python
CLAVE_METADATA = "capability_degraded"

def construir_entrada(*, capability: str, reason: str, provider: str, site: str) -> dict:
    """PURA. Devuelve la forma canónica. Sin I/O, sin base, sin config."""

def declarar(*, execution_id: int | None, capability: str, reason: str,
             provider: str, site: str, session_factory=None,
             log=None) -> bool:
    """Anota la degradación en metadata. NUNCA levanta. Idempotente."""
```

**Forma canónica de la entrada** (contrato congelado; el consumidor de F4 depende de estas cinco claves y de ninguna más):

```python
{
    "capability": "tracker.comments.list",   # key de CAPABILITY_MATRIX, o clave lógica propia
    "reason": "tracker no-ADO: sin cross-check de comentarios",
    "provider": "gitlab",
    "site": "business_preflight.evaluate",   # símbolo, NUNCA archivo:línea (las líneas caducan)
    "at": "2026-08-02T14:05:00+00:00",       # ISO-8601 UTC
}
```

**Pseudocódigo de `declarar` — copiar la disciplina de `context_enrichment.py:284-321`:**

```
log = log or _noop_log     # ⚠️ v2/C7 — PRIMERA línea, antes de todo. Ver recuadro.
si execution_id es None  -> return False           # sin destino, no-op silencioso
si capability vacío       -> return False
try:
    session_factory = session_factory or (from db import session_scope)   # import LOCAL: evita ciclos
    with session_factory() as sesion:
        fila = sesion.get(AgentExecution, execution_id)
        si fila is None -> return False
        md = dict(fila.metadata_dict or {})
        lista = list(md.get(CLAVE_METADATA) or [])
        entrada = construir_entrada(...)
        # DEDUP por (capability, site): la misma degradación en la misma corrida
        # se anota UNA vez. Sin esto, un backlog de 200 tickets escribe 200 veces.
        si existe e en lista con (e["capability"], e["site"]) == (entrada["capability"], entrada["site"]):
            return False
        lista.append(entrada)
        md[CLAVE_METADATA] = lista
        fila.metadata_dict = md      # reasignación COMPLETA del dict
    return True
except Exception as exc:
    log("warn", f"no se pudo declarar la degradación: {exc}")
    return False
```

**Casos borde que el pseudocódigo ya cubre y hay que testear:**

| Caso | Conducta esperada |
|---|---|
| `execution_id=None` | `False`, sin tocar la base, sin excepción. |
| `execution_id` inexistente en la tabla | `False`, sin excepción. |
| `metadata_dict` es `None` | Se crea el dict; la lista arranca vacía. |
| `metadata_dict` ya tiene otras claves (`ado_context`, `egress_sentinel`) | **Se preservan intactas.** |
| Misma `(capability, site)` dos veces | La segunda devuelve `False` y **no** duplica. |
| Distinta `capability`, mismo `site` | Se agregan **las dos**. |
| La sesión revienta (base bloqueada) | `False` + log `warn`. **Nunca propaga.** |
| La sesión revienta **y** el llamador no pasó `log` | `False` + log `warn` al logger no-op. **Nunca propaga.** *(v2 / C7)* |

> ⚠️ **v2 / C7 — el bug que el pseudocódigo del v1 tenía escrito y que rompía su propio riel.** La firma declara `log=None`, y el `except` llamaba `log("warn", ...)`. Con el default, eso es `None("warn", ...)` ⇒ **`TypeError` lanzado DESDE el manejador de excepciones**, o sea: `declarar()` levanta **exactamente** en el escenario que R2 dice cubrir (base bloqueada, sesión rota). Y como los dos call sites de F2/F3 no pasan `log`, el default es el camino normal.
>
> El remedio es el idioma que ya usa el módulo hermano: `context_enrichment.py:305` hace `log = log or _noop_log` como primera línea de `persistir_stats_de_contexto`. **Copialo literal**, definiendo un `_noop_log` propio en `capability_degradation.py` (no lo importes de `context_enrichment`: sería un acoplamiento nuevo entre dos servicios por una función de tres caracteres).
>
> **Y hay un test dedicado, porque este defecto es invisible en el camino feliz:** `test_declarar_sin_log_y_con_sesion_rota_no_levanta` — `session_factory` parcheado para levantar, **sin** pasar `log=`. Debe devolver `False`. Sin este caso, los 7 de la tabla pasan con el bug puesto.

> ⚠️ **`fila.metadata_dict = md` con reasignación completa es obligatorio.** Mutar el dict devuelto por el getter no marca la fila como sucia en SQLAlchemy y el cambio se pierde en silencio. Es el mismo idioma de `persistir_stats_de_contexto` (`context_enrichment.py:315-317`) y hay que respetarlo tal cual.

**Tests (archivo nuevo):** `Stacky Agents/backend/tests/test_plan290_registro_degradacion.py` — un caso por fila de la tabla de bordes (**8** casos, contando el de `log` sin pasar), más uno que verifica que `construir_entrada` es pura (dos llamadas con los mismos argumentos, salvo `at`, dan el mismo dict).

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_registro_degradacion.py" -q
```

**Criterio binario:** **9 passed, 0 failed** *(v2: 8 en el v1 + el caso de C7)*. Y el test de "preserva otras claves" debe afirmar **la PRESENCIA** de `ado_context` después de escribir, no solo la ausencia de errores (un `assert` de ausencia suelto pasa por accidente).

**Flag:** ninguna (§3.1). **Impacto por runtime:** ninguno todavía — nadie lo llama aún. **Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_registro_degradacion.py` en los dos, con las reglas de §F0.1.

---

### F2 — Sitio 1: `business_preflight` declara, y los DOS consumidores consumen

**Objetivo:** que la degradación del preflight quede en la metadata de la ejecución y que el consumidor del prompt deje de tirar los warnings del segundo en adelante.

**Archivo:** `Stacky Agents/backend/services/business_preflight.py`

**F2.1 — Firma: `execution_id` OPCIONAL en las DOS funciones, y en el despacho.** *(v2 / C1: el v1 sólo tocaba `evaluate`, y el guard no vive ahí.)*

```python
# ANTES (línea 161)
def evaluate(*, ticket_id: int, agent_type: str) -> BusinessPreflightResult:

# DESPUÉS
def evaluate(
    *, ticket_id: int, agent_type: str, execution_id: int | None = None
) -> BusinessPreflightResult:
```

```python
# ANTES (líneas 191-197) — el despacho por tabla
return _PREDICATES[agent_type](
    ado_id=ado_id, work_item_type=work_item_type, ado_state=ado_state,
    stacky_project_name=stacky_project_name, tracker_project=tracker_project,
)

# DESPUÉS — se suma el kwarg. Hoy `_PREDICATES` tiene UN solo predicado (:156-158).
return _PREDICATES[agent_type](
    ado_id=ado_id, work_item_type=work_item_type, ado_state=ado_state,
    stacky_project_name=stacky_project_name, tracker_project=tracker_project,
    execution_id=execution_id,
)
```

```python
# ANTES (líneas 37-44)
def _evaluate_functional(*, ado_id: int, work_item_type: str, ado_state: str,
                         stacky_project_name: str | None, tracker_project: str | None
) -> BusinessPreflightResult:

# DESPUÉS
def _evaluate_functional(*, ado_id: int, work_item_type: str, ado_state: str,
                         stacky_project_name: str | None, tracker_project: str | None,
                         execution_id: int | None = None
) -> BusinessPreflightResult:
```

> **Backward-compatible por construcción:** los tres son keyword-only con default `None`. `api/agents.py:542` sigue funcionando sin tocarlo. `tests/test_business_preflight.py` llama a `evaluate` sin el argumento en todos sus casos y **no debe modificarse** (DoD #14).
>
> ⚠️ **El `default=None` en `_evaluate_functional` no es cosmético:** `_PREDICATES` está tipado `dict[str, Callable[..., BusinessPreflightResult]]`. Si mañana entra un segundo predicado sin el kwarg, el despacho revienta con `TypeError` para **todos** los agent_types. Con el default, un predicado que lo ignore sigue andando.

**F2.2 — La declaración, dentro del guard existente** (`business_preflight.py:94-99`, en `_evaluate_functional`). Se agrega **antes** del `return`, el `return` no cambia:

```python
if not tracker_is_azure_devops(project_name) and ruteo_estricto_por_tracker():
    _motivo = "tracker no-ADO: sin cross-check de comentarios"
    # Plan 290 F2 — la degradación deja rastro. NO cambia el retorno.
    from services import capability_degradation
    from services.project_context import tracker_declarado_del_proyecto
    capability_degradation.declarar(
        execution_id=execution_id,
        capability="tracker.comments.list",
        reason=_motivo,
        provider=tracker_declarado_del_proyecto(project_name) or "desconocido",
        site="business_preflight._evaluate_functional",
    )
    return BusinessPreflightResult(ok=True, mode=None, warnings=[_motivo])
```

- `capability="tracker.comments.list"` es una key **real** de `CAPABILITY_MATRIX` — verificado: está en `CAPABILITY_KEYS` (`provider_capabilities.py:16`). Es la capacidad que el Modo B necesita y no tiene.
- ⚠️ **v2 / C2 — el `provider` sale de `tracker_declarado_del_proyecto`, NO de `tracker_efectivo_de_ticket`.** El v1 escribía `tracker_efectivo_de_ticket(_ticket) if _ticket else "desconocido"` y eso es **imposible dos veces**: `_ticket` no existe en ningún scope de este archivo, y en `_evaluate_functional` **no hay ningún objeto `Ticket`** — `evaluate` lo carga en `:180`, extrae escalares en `:183-189` y lo suelta al cerrar la sesión. `tracker_efectivo_de_ticket` hace `getattr(ticket, "tracker_type", None)` (`project_context.py:233`): sin objeto, no sirve.
  El hermano correcto es **`tracker_declarado_del_proyecto(project_name)`** (`project_context.py:124`), del **mismo Plan 286**, misma fuente de verdad (`issue_tracker.type`), que devuelve `str | None` — por eso el `or "desconocido"`. En este scope `project_name` **sí** existe: se calcula en `:58` (`stacky_project_name or tracker_project`) y es el mismo valor que el guard ya le pasa a `tracker_is_azure_devops`.
- `site="business_preflight._evaluate_functional"` — el símbolo **real**. El v1 decía `business_preflight.evaluate`, que es la función de arriba y no la que degrada. Como `site` es parte de la forma canónica congelada de F1 y F4 lo muestra al operador, un símbolo falso manda a leer el archivo equivocado.
- Import **local** dentro de la función, no a nivel de módulo: `_evaluate_functional` ya usa ese idioma en `:45-49` para evitar ciclos y para seguir siendo parcheable con monkeypatch.

**F2.3 — El consumidor del prompt deja de tirar warnings.** `services/context_enrichment.py:1319`:

```python
# ANTES
_reason = _bp.reason or (_bp.warnings[0] if _bp.warnings else "preflight_off")

# DESPUÉS
_reason = _bp.reason or ("; ".join(_bp.warnings) if _bp.warnings else "preflight_off")
```

> Hoy hay **un solo** warning, así que este cambio es un no-op observable en el estado actual. Se hace igual porque el `[0]` es una bomba silenciosa: el día que un sitio agregue el segundo warning, se pierde sin aviso. El test de F2.4 lo fija con **dos** warnings.

**F2.4 — La plomería del `execution_id`, en cuatro ediciones exactas.** *(v2 / C3 — reescrita: la "salida" del v1 dejaba F2 muerta.)*

**Está MEDIDO que `execution_id` NO está en el scope de `context_enrichment.py:1288`**: la función es `_inject_run_directive(*, ticket_id, agent_type, blocks, log)` (`:1261-1334`) y su llamador es `enrich_blocks(*, ticket_id, agent_type, raw_blocks, project_ctx, log)` (`:60-67`, llamada en `:133`). Ninguno lo tiene. **No hay que verificarlo de nuevo ni hay salida alternativa: hay que construir la cadena.**

| # | Archivo | Edición |
|---|---|---|
| 1 | `services/context_enrichment.py:60-67` | `enrich_blocks` suma `execution_id: int \| None = None` (keyword-only, al final). |
| 2 | `services/context_enrichment.py:133` | La llamada a `_inject_run_directive` suma `execution_id=execution_id`. |
| 3 | `services/context_enrichment.py:1261` | `_inject_run_directive` suma `execution_id: int \| None = None`. |
| 4 | `services/context_enrichment.py:1288` | `business_preflight.evaluate(ticket_id=ticket_id, agent_type=agent_type, execution_id=execution_id)`. |

**Y los tres runtimes lo pasan** — el valor ya está en sus manos, lo usan en la línea siguiente:

| Runtime | Editar la llamada a `enrich_blocks` en | Queda al lado de |
|---|---|---|
| GitHub Copilot Pro | `agent_runner.py:809-815` | `persistir_stats_de_contexto(execution_id=execution_id, ...)` en `:819-821` |
| Claude Code CLI | `services/claude_code_cli_runner.py:677-683` | `:685-687` |
| Codex CLI | `services/codex_cli_runner.py:334-340` | `:342-344` |

> **Backward-compatible en cada eslabón.** Los **11 call sites de `enrich_blocks` en `tests/`** (`test_context_enrichment.py` ×5, `test_memory_injection.py` ×5, `test_knowledge_injection.py`, `test_harness_learning_inject.py`, `test_rag_context_enrichment.py`) **no se tocan**: el default `None` los deja idénticos.
>
> ⚠️ **`tests/test_plan289_contexto_por_tracker.py:153-155` inspecciona la FORMA de la llamada** (`a, b = <algo>.enrich_blocks(...)`, para leer el nombre del segundo desempaquetado). Agregar un kwarg **no** cambia el desempaquetado, así que sus 34 passed no se mueven — pero es la suite a mirar primero si algo se pone rojo.
>
> `api/agents.py:542` (lanzamiento) **se deja como está**: en ese punto todavía no hay fila de `AgentExecution`, así que no hay destino donde anotar. Pasarle un `execution_id` inventado sería peor que no anotar. Su `evaluate(...)` sin el kwarg sigue compilando por el default.

**F2.5 — Tests.** En el mismo `test_plan290_degradacion_declarada.py` de F0 (que pasa de rojo a verde en su caso 1), más en un archivo nuevo `Stacky Agents/backend/tests/test_plan290_preflight_no_regresion.py`:

| Caso | Afirma |
|---|---|
| `test_el_valor_neutro_no_cambio` | Con proyecto no-ADO: `result.ok is True`, `result.mode is None`, `result.warnings == ["tracker no-ADO: sin cross-check de comentarios"]`. **Byte a byte lo de hoy.** |
| `test_proyecto_ado_no_declara_nada` | Con proyecto ADO: `metadata` **no** tiene la clave `capability_degraded`. Sentinela negativo. |
| `test_flag_apagada_no_declara_nada` | Con `ruteo_estricto_por_tracker()` falso (monkeypatch sobre el objeto `config`): ni guard ni declaración. |
| `test_sin_execution_id_no_levanta` | `evaluate(ticket_id=..., agent_type=...)` sin el kwarg: devuelve el mismo resultado y no lanza. Cubre `api/agents.py:542`. |
| `test_dos_warnings_llegan_completos_al_prompt` | Con dos warnings, el bloque `run-directive` contiene **los dos**, separados por `; `. Se afirma sobre el `content` del bloque, que es **el consumidor**, no sobre `_bp.warnings`. Hoy ningún camino de producción genera dos: el caso monkeypatchea `business_preflight.evaluate` para devolver un resultado con dos, y **eso es correcto** — lo que se está fijando es el contrato del consumidor, no del productor. |
| `test_los_tres_runtimes_pasan_el_execution_id` *(v2 / C3)* | **Estático y a propósito**, porque es un defecto de cableado, no de ejecución: parsea por **AST** `agent_runner.py`, `claude_code_cli_runner.py` y `codex_cli_runner.py`, encuentra la llamada a `enrich_blocks` de cada uno y afirma que **las tres** tienen un keyword `execution_id`. Además afirma que encontró **exactamente 3** llamadas (si el parser ve 0, el test se cae con mensaje propio en vez de dar verde por vacío). Es el mismo defecto que el Plan 289 tuvo que arreglar en 2 de 3 runtimes: acá se congela para que no vuelva. |

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_preflight_no_regresion.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_business_preflight.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_context_enrichment.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan289_contexto_por_tracker.py" -q
```

**Criterio binario:** el archivo nuevo da **6 passed** *(v2: 5 del v1 + el de paridad de runtimes)*; `test_business_preflight.py` da **exactamente el mismo conteo que en el commit base** (§5.1) **sin haber sido editado** (`git diff --stat` sobre ese archivo debe salir vacío); `test_plan289_contexto_por_tracker.py` sigue en **34 passed**; `test_context_enrichment.py` en delta cero contra su propia medición del commit base (**medila en F0**, no está en la tabla de §5.1 del v1).

**Flag:** ninguna. Kill-switch heredado: `ruteo_estricto_por_tracker()`.
**Impacto por runtime:** los 3, por los dos caminos de §3.2. **Fallback:** sin `execution_id`, `declarar` devuelve `False` y el preflight se comporta idéntico a hoy.
**Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_preflight_no_regresion.py` en los dos (§F0.1).

---

### F3 — Sitio 2: `self_review` declara (con el `execution_id` que ya tiene en la mano)

**Objetivo:** que un self-review omitido por falta de criterios deje de parecer un self-review aprobado.

**Por qué este sitio y no otro:** `review_artifact(*, execution_id: int, artifact_text: str)` (`services/self_review.py:76`) **ya recibe el `execution_id`**. Es el único de los ocho donde el destino está en el scope inmediato, sin plomería nueva. Y el daño es alto: cuando `_resolve_criteria` devuelve `""`, `review_artifact` devuelve `SelfReviewResult(score=1.0, checklist=[], skipped_reason="no_acceptance_criteria")` — un **score de 1.0**, o sea "perfecto", para un artefacto que nadie revisó.

**Archivo:** `Stacky Agents/backend/services/self_review.py`

**F3.1 — La declaración va en `review_artifact`, NO en `_resolve_criteria`.** Razón: `_resolve_criteria(ticket)` no tiene `execution_id` y lo llaman también otros caminos; instrumentarla exigiría cambiarle la firma. En `review_artifact` el dato está a tres líneas.

```python
    criteria_text = _resolve_criteria(ticket)
    if not criteria_text:
        # Plan 290 F3 — el self-review se saltea. Que quede dicho, no solo devuelto.
        # NO cambia el retorno: sigue score=1.0 + skipped_reason.
        from services import capability_degradation
        from services.project_context import (
            ruteo_estricto_por_tracker,
            tracker_efectivo_de_ticket,
            tracker_is_azure_devops,
        )
        if (
            not tracker_is_azure_devops(getattr(ticket, "stacky_project_name", None))
            and ruteo_estricto_por_tracker()
        ):
            capability_degradation.declarar(
                execution_id=execution_id,
                capability="tracker.acceptance_criteria",
                reason=(
                    "el tracker no expone criterios de aceptación "
                    "(Microsoft.VSTS.Common.AcceptanceCriteria es un campo de Azure DevOps): "
                    "el self-review se saltea y NO evaluó el artefacto"
                ),
                provider=tracker_efectivo_de_ticket(ticket),
                site="self_review.review_artifact",
            )
        return SelfReviewResult(score=1.0, checklist=[], skipped_reason="no_acceptance_criteria")
```

> **Por qué se repite el guard `tracker_is_azure_devops(...) and ruteo_estricto_por_tracker()`:** `criteria_text` puede venir vacío por **dos** motivos distintos — el tracker no tiene el campo (degradación declarada, sitio 6) o el ticket ADO simplemente no tiene criterios cargados (que **no** es una degradación de capacidad, es un ticket incompleto). Sin el guard se declararían falsos positivos sobre proyectos ADO y el KPI se inflaría con ruido. **Este guard es obligatorio.**

**F3.2 — `capability="tracker.acceptance_criteria"` no existe hoy en `CAPABILITY_MATRIX`.** Hay dos caminos y hay que elegir **uno** y escribirlo:

- **Elegido:** usar la clave lógica `"tracker.acceptance_criteria"` **sin** agregarla a `CAPABILITY_MATRIX`.
- **Motivo:** agregar una key cambia `len(CAPABILITY_KEYS)` de 71 a 72, y `render_markdown_matrix()` (`provider_capabilities.py:364`) genera el documento de paridad a partir de esa lista, que `test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado` exige idéntico al `.md` versionado. Habría que **regenerar el documento de paridad** dentro de un plan que no es sobre paridad, y además declarar `evidence` para la nueva key en los dos proveedores (lo exige `test_full_y_partial_exigen_evidencia`). **Fuera de scope** (§6).
- ⚠️ **Ojo con el criterio:** `test_plan218_capability_matrix.py` **ya está rojo de fábrica** (**2 failed, 8 passed**, §5.1) y **esos dos rojos son exactamente esos dos tests**. O sea: no se puede usar "el test pasa" como criterio acá. El criterio correcto es **delta cero** — el archivo tiene que seguir en 2 failed / 8 passed. Si al terminar tiene 3 failed, este plan rompió algo.
- **Consecuencia que F4 DEBE manejar:** el aviso de la interfaz va a recibir una `capability` que **no está** en la matriz. Ver §F4.3 — es exactamente el caso "capacidad desconocida" que el plan exige testear.

**F3.3 — Tests.** El caso 2 de `test_plan290_degradacion_declarada.py` (F0) pasa a verde. Más, en `Stacky Agents/backend/tests/test_plan290_self_review_no_regresion.py`:

| Caso | Afirma |
|---|---|
| `test_el_retorno_no_cambio` | `result.score == 1.0`, `result.checklist == []`, `result.skipped_reason == "no_acceptance_criteria"`. |
| `test_proyecto_ado_sin_criterios_no_declara` | Proyecto ADO + criterios vacíos: retorno idéntico y **sin** clave `capability_degraded`. Es el sentinela que impide el falso positivo de F3.1. |
| `test_flag_apagada_no_declara` | `ruteo_estricto_por_tracker()` falso ⇒ no declara. |
| `test_declarar_falla_y_el_review_sigue` | Con `capability_degradation.declarar` parcheado para levantar: `review_artifact` devuelve el resultado normal. Prueba el riel "nunca levanta". |

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_self_review_no_regresion.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_degradacion_declarada.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_u1_self_review.py" -q
```

> ⚠️ El archivo de tests del servicio se llama **`test_u1_self_review.py`**, no `test_self_review.py` (ese **no existe** y `pytest` sale con exit 4, que parece "sin fallos"). Ver §5.1.

**Criterio binario:** archivo nuevo **4 passed**; `test_plan290_degradacion_declarada.py` pasa de **2 failed** (F0) a **2 passed**; `test_u1_self_review.py` en **2 passed** (baseline §5.1), sin editarlo.

**Flag:** ninguna. **Impacto por runtime:** los 3, por el punto único `review_artifact` (§3.2). **Fallback:** `declarar` devuelve `False` y el review sigue igual.
**Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_self_review_no_regresion.py` en los dos (§F0.1).

---

### F4 — El aviso llega a la interfaz

**Objetivo:** que el operador vea, en el detalle de la ejecución, qué capacidad se degradó y por qué.

**Restricción dura (v2 / C11 — el v1 se contradecía consigo mismo dos párrafos después).** Hay que separar dos cosas que el v1 mezcló:

| Qué | Estado real, medido el 2026-08-02 | Consecuencia |
|---|---|---|
| **RTL / jsdom** | **NO instalados.** | **Prohibido** escribir `.test.tsx` de componentes. Un `.test.tsx` con RTL reporta *"no tests"* y sale con **exit 0**: un falso verde perfecto. |
| **`vitest` sobre `.ts` puro** | **SÍ funciona.** Medido: `npx vitest run "src/services/__tests__/parityMatrixModel.test.ts"` → **6 passed**, exit **0**. | **Obligatorio** para toda la lógica de esta fase. |
| **`npx tsc --noEmit`** | **0 errores** hoy (exit 0). | Gate **absoluto** (el único del plan que no es delta). |

O sea: la lógica va en `.ts` puro y el `.tsx` sólo pinta; y el frontend tiene **dos** gates obligatorios (`tsc` y `vitest` sobre el `.ts`), no uno.

**F4.1 — Modelo puro (archivo nuevo):** `Stacky Agents/frontend/src/services/capabilityDegradedModel.ts`

```typescript
export interface DegradacionDeclarada {
  capability: string;
  reason: string;
  provider: string;
  site: string;
  at: string;
}

/** Lee metadata.capability_degraded de forma DEFENSIVA. Nunca lanza.
 *  Una metadata sin la clave, con la clave en null, o con un valor que no es
 *  array, devuelve []. Las entradas que no son objeto se descartan. */
export function leerDegradaciones(metadata: Record<string, unknown> | null | undefined): DegradacionDeclarada[];

/** Etiqueta legible. Una capacidad DESCONOCIDA devuelve la key cruda,
 *  NUNCA undefined ni "". Mismo criterio que statusLabel de parityMatrixModel. */
export function etiquetaDeCapacidad(capability: string): string;

/** Agrupa por provider, preservando orden de llegada. */
export function agruparPorProveedor(items: DegradacionDeclarada[]): Array<[string, DegradacionDeclarada[]]>;
```

**Diccionario de etiquetas — cerrado y con default explícito:**

```typescript
const ETIQUETAS: Record<string, string> = {
  "tracker.comments.list": "Lectura de comentarios del tracker",
  "tracker.acceptance_criteria": "Criterios de aceptación",
};
export function etiquetaDeCapacidad(capability: string): string {
  return ETIQUETAS[capability] ?? capability;   // ?? y NO ||: "" no debe caer al default
}
```

> ⚠️ **v2 / C4 — el par que se contradecía, resuelto: las DOS keys se quedan en `ETIQUETAS`.**
>
> El v1 metía `"tracker.acceptance_criteria"` en este diccionario y **dos subsecciones después** (§F4.3, y otra vez en R4) justificaba todo el diseño diciendo que esa key *"no está... en `ETIQUETAS`"* y que por eso *"el camino desconocido es el camino normal desde el día uno"*. Las dos afirmaciones no pueden ser verdad a la vez, y la salida barata para un modelo menor es **borrar la entrada del diccionario** para que la prosa cierre — degradando la interfaz a mostrar `tracker.acceptance_criteria` en crudo, que es justo lo que la fase viene a evitar.
>
> **Regla, y es final:** las **dos** keys que este plan emite (`tracker.comments.list` de F2 y `tracker.acceptance_criteria` de F3) tienen etiqueta legible. Ninguna cae al default. El `?? capability` es un **borde defensivo** para una key futura, no el camino normal — y se prueba con una key sintética que el test declara como tal (`"tracker.inventada.por.el.test"`). Que la key no esté en `CAPABILITY_MATRIX` (§F3.2) es cierto y sigue siendo cierto; que no esté en `ETIQUETAS` es **falso**, y son dos diccionarios distintos con dos propósitos distintos.

**F4.2 — Componente (archivo nuevo):** `Stacky Agents/frontend/src/components/AvisoDegradacionPanel.tsx`

- Recibe `metadata: Record<string, unknown>` (el drawer ya lo tiene como `Record<string, unknown>` en `ExecutionDetailDrawer.tsx:74`).
- Si `leerDegradaciones(metadata).length === 0` → **devuelve `null`**. No se monta, no ocupa espacio, no cambia el layout de ninguna ejecución existente.
- Sigue el patrón exacto de los vecinos del drawer (`metadata.egress_sentinel` en `:198`, `metadata.local_insight` en `:189`).
- **Estilos:** un `.module.css` propio usando **solo tokens del tema**. Los tokens que existen son `--accent`, `--success`, `--danger`, `--border`, `--text-primary`, `--bg-panel`. **`--color-*` NO existe** y **el ratchet de UI prohíbe hex crudos** — un `#RRGGBB` en el CSS pone el ratchet en rojo.
- **No es solo color:** cada fila lleva un ícono/marca además del color (mismo criterio de accesibilidad que `statusMark` en `parityMatrixModel.ts:81`).

**F4.3 — Montaje:** en `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx`, junto a los otros paneles alimentados por `metadata`, pasando `metadata={metadata}`. **No se toca `DiagnosticsPage.tsx` ni `ParityMatrixPanel.tsx`.**

> ⚠️ **Capacidad desconocida — borde defensivo, NO el camino normal** *(v2 / C4 — corregido)*. Las dos capacidades que este plan emite tienen etiqueta en `ETIQUETAS` (§F4.1), así que el operador **siempre** lee texto en castellano. El default `?? capability` existe para el día en que alguien instrumente un noveno sitio con una key nueva y se olvide de la etiqueta: en ese caso la fila se pinta con la key cruda **y el `reason`**, que igual es informativo. **Un `Record` sin default haría que React renderice vacío y el aviso quedaría mudo — exactamente el defecto que este plan viene a arreglar, reintroducido en la capa de arriba.** Ese es el motivo del default, y alcanza: no hace falta inventar que la key de F3 no está etiquetada.
>
> *(Nota separada, y sigue siendo cierta: `"tracker.acceptance_criteria"` **no** está en `CAPABILITY_MATRIX`, por el motivo de §F3.2. `CAPABILITY_MATRIX` y `ETIQUETAS` son dos diccionarios distintos; no estar en el primero no implica no estar en el segundo.)*

**F4.4 — Tests (lógica pura, con vitest sobre `.ts`):** `Stacky Agents/frontend/src/services/__tests__/capabilityDegradedModel.test.ts`

| Caso | Afirma |
|---|---|
| `metadata` sin la clave | `[]` |
| `capability_degraded: null` | `[]` |
| `capability_degraded: "texto"` (no array) | `[]` |
| array con una entrada válida y una `null` | devuelve **1** entrada |
| **las DOS keys de producción** (`tracker.comments.list` y `tracker.acceptance_criteria`) | etiqueta traducida, **ninguna** devuelve la key cruda. *(v2 / C4: es el sentinela de que nadie borró la entrada del diccionario para "cerrar" la prosa.)* |
| capacidad desconocida (`"tracker.inventada.por.el.test"`) | devuelve la key cruda, no `undefined` ni `""` |
| `etiquetaDeCapacidad("")` | devuelve `""`, no el default (prueba el `??` frente a `\|\|`) |

```
cd "Stacky Agents/frontend" && npx vitest run "src/services/__tests__/capabilityDegradedModel.test.ts"
```

> ⚠️ `npx vitest run <ruta inexistente>` **sale 1 pero pipeado se pierde el exit code**, y un `.test.tsx` con RTL reporta "no tests" con **exit 0**. Verificá que la salida diga explícitamente **7 passed** y que el archivo sea `.ts` (no `.tsx`).

**Criterio binario, dos comandos:**

```
cd "Stacky Agents/frontend" && npx tsc --noEmit          # 0 errores, exit 0
cd "Stacky Agents/frontend" && npx vitest run "src/services/__tests__/capabilityDegradedModel.test.ts"   # 7 passed
```

**Flag:** ninguna. El aviso solo aparece si hay dato; sin dato no se monta.
**Impacto por runtime:** ninguno (es interfaz; lee metadata que los 3 escriben igual).
**Trabajo del operador: ninguno.**

---

### F5 — `STACKY_GITLAB_ENABLED` llega a la interfaz (y aplica de verdad)

**Objetivo:** que el master switch de GitLab sea una perilla de la interfaz con efecto inmediato, sin editar archivos a mano.

**F5.1 — La decisión, con su motivo escrito.**

> **DECISIÓN: `STACKY_GITLAB_ENABLED` NO se registra como `FlagSpec`. Se expone por la interfaz a través del canal que YA lo gestiona: `_MANAGED_KEYS` de `api/global_config.py`.**
>
> **Motivos, en orden de peso:**
> 1. **Ya vive ahí.** `api/global_config.py:82` la tiene en `_MANAGED_KEYS` desde el Plan 65. Registrarla además como `FlagSpec` crearía **dos escritores del mismo valor**, que es el defecto que `api/global_config.py:88-93` documenta para `LOG_LEVEL` con la frase *"UN solo escritor"*.
> 2. **El panel de flags mentiría.** Su hot-apply hace `setattr` sobre `config` y nada más. Para esta clave hace falta además persistir en `.env` (si no, se pierde al reiniciar) — el panel diría "aplicado" con persistencia a medias.
> 3. **Costo desproporcionado.** Una `FlagSpec` nueva arrastra ocho guardianes, incluido `test_requires_map_is_frozen` indexado por key, para una clave que ya tiene endpoint.
> 4. **`api/harness_flags.py:134` ya dejó escrita esta misma decisión** ("NO vive en este registro"). Este plan la respeta, no la revierte.
>
> **Su default en código NO se toca.** `config.py:1298` sigue en `"false"`. Motivo: GitLab exige instancia + token que no existen en una instalación limpia; encenderlo por default haría fallar el arranque de cualquier instalación nueva. **El `.env` del operador, que hoy tiene `STACKY_GITLAB_ENABLED=true` (`backend/.env:7`), no se modifica**: el `.env` gana sobre el default de código y el operador sigue exactamente como está hoy. Este plan **no cambia el comportamiento de ninguna instalación existente**.

**F5.2 — El hot-apply que falta (backend).** Archivo: `Stacky Agents/backend/api/global_config.py`, dentro de `put_global_config`, con el mismo idioma que `api/projects.py:141-142`:

```python
# Plan 290 F5 — `_write_env` actualiza .env y os.environ, pero NO el singleton
# `config.config`, que es de donde leen tracker_provider.py:133, ci_provider.py:121,
# ci_variables.py:87, ci_preflight.py:39 y ci_logs_provider.py:38. Sin este
# setattr la interfaz diría "guardado" y el motor seguiría con el valor viejo
# hasta reiniciar: un falso verde.
if persisted and "STACKY_GITLAB_ENABLED" in updates:
    import config as _config
    setattr(
        _config.config,
        "STACKY_GITLAB_ENABLED",
        updates["STACKY_GITLAB_ENABLED"].strip().lower() in ("1", "true", "yes"),
    )
```

> **v2 / C8 — DÓNDE va, exactamente.** El v1 decía sólo *"dentro de `put_global_config` (`:190`)"* y eso deja tres ubicaciones plausibles con tres conductas distintas. La correcta es **después** del `try/except OSError` que llama a `_write_env(updates)` (`:242-245`), o sea cuando `persisted` ya tiene su valor final — y **guardada por `persisted`**. Anclá por el símbolo `_write_env(updates)`, no por número de línea.
>
> Los dos anclajes que decidieron esta ubicación, verificados:
>
> | Línea | Qué hay | Por qué importa |
> |---|---|---|
> | `:219-225` | `return jsonify({...}), 400` si el `LOG_LEVEL` es inválido | Un `setattr` **antes** de esto encendería GitLab en un pedido que devuelve 400 y no persiste nada. |
> | `:242-245` | `try: _write_env(updates) / except OSError: persisted = False` | Un `setattr` **antes** de esto, con el disco lleno o el `.env` de sólo lectura, deja el motor ON y el archivo sin escribir: al reiniciar vuelve a OFF. Es el **falso verde espejo** del que la fase viene a arreglar. |
>
> El parseo replica **exactamente** el de `config.py:1297-1299` (`.lower() in ("1","true","yes")`). No inventes otro conjunto de valores verdaderos: `"on"` **no** está y agregarlo divergiría del arranque.
>
> ⚠️ **Cuidado con el `""`.** `:203` hace `val = str(data[key] or "").strip()`, así que un `false` booleano o un `null` del cliente llegan como `""`. Con `""`: `_write_env` escribe la línea `STACKY_GITLAB_ENABLED=` **y borra la clave de `os.environ`** (`:164-168`), el `setattr` deja `False`, y al reiniciar `config.py:1297` lee `""` → `False`. Es consistente, pero el modelo puro de F5.3 **debe mandar los strings `"true"`/`"false"`**, nunca un booleano ni `null`, para que el `.env` quede legible.

**F5.3 — El panel (frontend).** Archivo nuevo `Stacky Agents/frontend/src/components/GitlabEngineSwitch.tsx`, **calcado de `LogLevelPanel.tsx`**: `useState` + `useEffect` que lee del GET, un control, y mensajes de ok/error. Se monta en `DiagnosticsPage.tsx` **inmediatamente después de `<LogLevelPanel />`** (hoy en `:328`; anclá por el símbolo `<LogLevelPanel />`, no por el número).

- Lógica pura en `Stacky Agents/frontend/src/services/gitlabEngineModel.ts`: normalización del valor que llega del GET (que es un **string** del `.env`, no un bool) a `boolean`, con la MISMA tabla que el backend.
- Endpoints en `frontend/src/api/endpoints.ts`: reusar `api.get`/`api.put` sobre `/api/global-config` (ya existen en `:3392` y `:2371`).
- **Aviso en la interfaz** cuando se apaga: los proyectos GitLab van a empezar a fallar con `TrackerConfigError`. Texto explícito, no un toggle mudo.

**F5.4 — Tests.**

Backend, archivo nuevo `Stacky Agents/backend/tests/test_plan290_gitlab_switch_ui.py`:

| Caso | Afirma |
|---|---|
| `test_put_enciende_y_aplica_en_caliente` | Tras el PUT con `"true"`, `config.config.STACKY_GITLAB_ENABLED is True` **y** el `.env` de prueba contiene la línea. **Los dos, en el mismo test.** |
| `test_put_apaga_y_aplica_en_caliente` | Ídem con `"false"` → `is False`. |
| `test_get_devuelve_la_clave` | El GET incluye `STACKY_GITLAB_ENABLED`. |
| `test_valor_basura_no_enciende` | `"quizas"` → `is False` (no truthy por ser string no vacío). |
| `test_si_no_persiste_no_aplica_en_caliente` *(v2 / C8)* | Con `_write_env` parcheado para levantar `OSError`: la respuesta trae `persisted: false` **y** `config.config.STACKY_GITLAB_ENABLED` **conserva su valor previo**. Es el sentinela del falso verde espejo. |
| `test_log_level_invalido_no_toca_gitlab` *(v2 / C8)* | PUT con `LOG_LEVEL="TRACE"` (inválido) **y** `STACKY_GITLAB_ENABLED="true"`: sale **400** por `:219-225` y el singleton **no** cambió. |

> ⚠️ El test **debe** apuntar `_ENV_PATH` a un archivo temporal (monkeypatch). **Está prohibido que un test escriba el `.env` real del operador.** Y el `setattr` sobre el singleton hay que **restaurarlo** en teardown (`monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", <previo>)`): dejarlo pisado contamina cualquier test posterior del mismo proceso.

Frontend: `Stacky Agents/frontend/src/services/__tests__/gitlabEngineModel.test.ts` — `"true"`/`"1"`/`"yes"` → `true`; `"false"`/`""`/`"quizas"`/`undefined` → `false`.

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_gitlab_switch_ui.py" -q
cd "Stacky Agents/frontend" && npx vitest run "src/services/__tests__/gitlabEngineModel.test.ts"
cd "Stacky Agents/frontend" && npx tsc --noEmit
```

**Criterio binario:** backend **6 passed** *(v2: 4 del v1 + los 2 de C8)*; frontend **7 passed**; `tsc` **0 errores**.

**Flag:** ninguna nueva. **Impacto por runtime:** ninguno (configuración, no ejecución).
**Trabajo del operador: ninguno.** Su `.env` actual sigue igual y el switch aparece ya reflejando `true`.

**Ratchets:** registrar `tests/test_plan290_gitlab_switch_ui.py` en los dos (§F0.1).

---

### F6 — `base_url` se normaliza también del lado del servidor

**Objetivo:** que un `base_url` con namespace pegado quede normalizado aunque no pase por el formulario.

**Archivo:** `Stacky Agents/backend/project_manager.py` (raíz del backend, **no** `services/`), línea **670**.

```python
# ANTES
"base_url":  url.rstrip("/"),

# DESPUÉS
"base_url":  _normalizar_base_url_gitlab(url),
```

**Función nueva** en el mismo archivo — puerto exacto de `normalizeGitlabUrl` (`frontend/src/projects/newProjectGitlabModel.ts:39`):

```python
_RE_API_V = re.compile(r"/api/v[0-9]+$", re.IGNORECASE)
_RE_ORIGEN = re.compile(r"^(https?://[^/]+)(/.*)?$", re.IGNORECASE)

def _normalizar_base_url_gitlab(raw: str) -> str:
    """Plan 290 F6 — puerto server-side de normalizeGitlabUrl.

    Deja SOLO el origen: saca barras finales, un /api/vN pegado y cualquier path.
    Un valor sin esquema se devuelve limpio de barras finales y nada más: acá no
    corresponde inventar un origen (el formulario ya lo rechaza antes).
    """
    limpio = _RE_API_V.sub("", (raw or "").strip().rstrip("/"))
    m = _RE_ORIGEN.match(limpio)
    return m.group(1) if m else limpio
```

**Tabla de equivalencia obligatoria (mismo input → mismo output que el cliente):**

| Entrada | Salida |
|---|---|
| `https://gitlab.com` | `https://gitlab.com` |
| `https://gitlab.com/` | `https://gitlab.com` |
| `https://gitlab.com///` | `https://gitlab.com` |
| `https://gitlab.com/api/v4` | `https://gitlab.com` |
| `https://gitlab.com/api/v4/` | `https://gitlab.com` |
| `https://git.interno/grupo/proyecto` | `https://git.interno` |
| `https://git.interno:8443/grupo/proyecto` | `https://git.interno:8443` |
| `HTTP://GitLab.com/API/V4` | `HTTP://GitLab.com` |
| `""` | `""` |
| `gitlab.com/grupo` | `gitlab.com/grupo` (sin esquema: no se inventa origen) |

> ⚠️ Ojo con el orden: hay que sacar la barra final **antes** de intentar el `/api/vN`, porque `https://host/api/v4/` no matchea `/api/v[0-9]+$` con la barra puesta. El pseudocódigo de arriba ya lo hace (`.rstrip("/")` dentro del `sub`).

**Tests:** `Stacky Agents/backend/tests/test_plan290_base_url_normalizada.py` — un caso por fila (10 casos), más un caso de **paridad declarada**: un test que lista los mismos 10 pares y afirma que la tabla del test coincide con la del docstring, para que el día que el cliente cambie se vea la divergencia.

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_base_url_normalizada.py" -q
```

**Criterio binario:** **11 passed**.

**Flag:** ninguna. Es una corrección de normalización sin superficie configurable.
**Impacto por runtime:** ninguno (alta/edición de proyecto, no ejecución).
**Trabajo del operador: ninguno.** Los proyectos ya creados **no se migran** (§6): la función solo actúa al escribir.

**Ratchets:** registrar `tests/test_plan290_base_url_normalizada.py` en los dos (§F0.1).

---

### F7 — Las 23 descripciones que mienten, y el guardián que impide la 24

**Objetivo:** que ninguna descripción de flag afirme un default que el código contradice, para siempre.

**F7.1 — Re-medir antes de tocar.** Correr el script de §2.4 (reproducible: AST sobre `harness_flags.py` + regex sobre `config.py`). Si el conteo **no** da 23, las líneas se movieron: re-generá la tabla, **no** edites por número de línea.

**F7.2 — Corregir el TEXTO y solo el texto — en `description=` Y en `label=`.** En `Stacky Agents/backend/services/harness_flags.py`, para cada una de las 23: reemplazar la afirmación falsa (`Default OFF.`, `Privacidad: default OFF.`, etc.) por la verdadera (`Default ON.`).

> ⚠️ **Prohibido cambiar `default=`, `key`, `type`, `group`, `requires`, `env_only`, `min_value`, `max_value`.** Este plan **no** cambia el comportamiento de ninguna flag. Si al leer una descripción te parece que la conducta correcta sería OFF, **no la apagues**: anotalo en el commit y dejalo para el operador. Apagar una flag que hoy está ON es un cambio de comportamiento no solicitado que puede tumbar funcionalidad viva.

> ⚠️ **v2 / C6 — `STACKY_TRACE_PROMPT_TEXT_ENABLED`: son DOS campos que mienten, no uno, y el v1 sólo arreglaba el segundo.** Su `FlagSpec` empieza en `:2207`:
>
> ```python
> default=True,   # :2210 — "promovida a default ON (operador 2026-07-15, ...)"
> label="Texto del prompt en trazabilidad (C0/C1, privacidad OFF)",          # :2211 ← TAMBIÉN MIENTE
> description=("... Privacidad: default OFF. ..."),                          # :2212-2216
> ```
>
> El `label` es el **título** de la perilla — lo primero que el operador lee, y se renderiza junto a la descripción en `HarnessFlagsPanel.tsx:240`. Corregir sólo `description=` deja el KPI K2 en 0 con el operador leyendo *"privacidad OFF"* en el encabezado. **Censado por AST: es el ÚNICO `label` del registro que contradice su `default`** — o sea, cuesta una edición de un string y no hay una segunda camada escondida.
>
> **Las tres ediciones exactas de esta flag** (las tres son texto puro, cero cambio de conducta):
> 1. `label=` → `"Texto del prompt en trazabilidad (C0/C1, privacidad: nace ON)"`.
> 2. `description=` → sacar `Privacidad: default OFF.` y poner `Default ON.`
> 3. Agregar a `description=` la advertencia accionable: *"Hoy nace ON: el texto completo del prompt SÍ queda en la metadata de cada ejecución. Apagala si el contenido de tus prompts es sensible."*
>
> **No la apagues vos** (§5, R6 y §7.4). El comentario de `:2210` deja constancia de que **el propio operador** la promovió a ON el 2026-07-15: apagarla no sería "arreglar un descuido", sería revertir una decisión suya sin pedirle permiso — lo contrario del riel human-in-the-loop. Lo que sí corresponde, y es lo que hace esta fase, es que la perilla **diga la verdad** para que su próxima decisión sea informada.

**F7.3 — El guardián (archivo nuevo):** `Stacky Agents/backend/tests/test_plan290_defaults_no_mienten.py`

```python
def test_ninguna_descripcion_contradice_su_default():
    """KPI K2. Recorre TODAS las FlagSpec por AST y cruza el texto contra el
    default efectivo (FlagSpec.default y la entrada de config.py)."""

def test_ningun_label_contradice_su_default():   # v2 / C6
    """Mismo barrido, sobre `label=`. Hoy hay exactamente UNA contradicción
    (STACKY_TRACE_PROMPT_TEXT_ENABLED, :2211); después de F7.2, cero."""
```

> **v2 / C6 — el gate cubre los DOS campos.** Un gate que sólo mire `description=` deja abierta la puerta por la que ya entró la peor de las 23: la promesa de privacidad estaba **también** en el título. Los dos tests comparten el barrido AST y el mismo guard anti-parser-roto (`>= 400`).
>
> **Lo que este gate NO cubre, y hay que escribirlo para que nadie crea que sí:** la ayuda en lenguaje llano vive en un módulo **separado**, `services/harness_flags_help.py` (`PLAIN_HELP`, con campos `what` / `on_effect` / `off_effect` / `example`), se inyecta en la respuesta del endpoint en `services/harness_flags.py:7469` y se renderiza en `HarnessFlagsPanel.tsx:245-250`. **No** se deriva de `description`. Auditarla es alcance de otro plan (§6) — y su suite, `test_harness_flags_help.py`, ya está roja de fábrica con 4 fallos ajenos. **Consecuencia práctica buena:** como `PLAIN_HELP` es independiente, editar las 23 descripciones **no puede** mover esa suite, lo que hace creíble el delta cero de §F7.4.

**Diseño del gate — los tres moldes de gate muerto, evitados a propósito:**

- **(a) centinela sobre un símbolo que una fase posterior borra** → no aplica: recorre `FlagSpec` genéricamente, no una key concreta. Ninguna fase de este plan borra `FlagSpec`.
- **(b) test estático sobre un defecto de ejecución** → acá el defecto **es** estático (una discrepancia texto↔código), así que un análisis del fuente es la herramienta correcta. Se hace por **AST**, no por regex sobre el archivo entero: una `FlagSpec` alcanzada por alias o con la descripción partida en varias líneas debe contarse igual.
- **(c) `assert` de ausencia suelto** → el test afirma **las dos cosas en la misma función**: que el barrido encontró **≥ 400 `FlagSpec`** (o sea, que efectivamente parseó algo — hoy son 490) **y** que la lista de contradicciones está vacía. Sin la primera mitad, un parser roto que devuelve cero flags daría verde eterno.

```python
    assert len(flags) >= 400, f"el barrido solo vio {len(flags)} FlagSpec: el parser se rompió"
    assert contradicciones == [], f"descripciones que mienten: {contradicciones}"
```

**¿Qué tiene que pasar para que se ponga rojo, y ese escenario sigue existiendo después de la última fase?** Sí: alcanza con que alguien escriba una `FlagSpec` nueva con `default=True` y `"Default OFF"` en la descripción — el caso más común del repo, 23 veces cometido. El gate se prueba **contra el defecto**: antes de F7.2 el test debe dar **1 failed** listando las 23; después, **1 passed**.

```
# ANTES de F7.2 (obligatorio, pegar la salida en el commit):
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_defaults_no_mienten.py" -q   # 2 failed: una con las 23 descripciones, otra con el 1 label
# DESPUÉS de F7.2:
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_defaults_no_mienten.py" -q   # 2 passed
```

> **El censo es reproducible y ya se corrió** (esta crítica lo ejecutó): AST sobre `services/harness_flags.py` buscando `ast.Call` con `func.id == "FlagSpec"`, cruzado contra un regex `os\.getenv\(\s*["'](KEY)["']\s*,\s*["'](VALOR)["']` sobre `config.py`. Resultado: **490** `FlagSpec`, **23** descripciones contradictorias (las 23 de §2.4, con esas 23 líneas), **1** label contradictorio. Si tu corrida da otro número, **las líneas se movieron: re-generá la tabla, no adivines.**

**F7.4 — Las suites que este cambio puede mover.** Editar `harness_flags.py`, aunque sea solo texto, toca un archivo que vigilan varias suites. Correr **cada una por separado** y comparar contra el baseline de §5.1:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flags_env_read_meta.py" -q
```

**Criterio binario:** el guardián en **2 passed**, y las tres suites de arriba con **exactamente el mismo conteo de passed/failed que en el commit base** — criterio **delta cero**, no absoluto: varias están rojas de fábrica por deuda ajena (§5.1). Concretamente y ya medido: `test_harness_flags.py` **59 passed**, `test_harness_flags_help.py` **4 failed / 4 passed**, `test_flags_env_read_meta.py` **1 failed / 1 passed**.

**Flag:** ninguna. **Impacto por runtime:** ninguno (texto de descripciones y de un label).
**Trabajo del operador: ninguno.** (Queda para él **una decisión informada** sobre `STACKY_TRACE_PROMPT_TEXT_ENABLED`, que este plan **declara** pero no ejecuta — §7.)

**Ratchets:** registrar `tests/test_plan290_defaults_no_mienten.py` en los dos (§F0.1).

---

### F9 — [ADICIÓN ARQUITECTO] El centinela de los ocho sitios: la deuda deja de ser prosa

**El problema que resuelve, y por qué es de este plan y no de otro.** Este plan instrumenta **2 de 8** sitios y manda los otros **6** a §6 y a un `.md` de `docs/sistema/` (F8.1). En este repo, eso tiene un final conocido y documentado: *código construido, testeado, verde y jamás cableado*, y *"deuda conocida"* que nadie vuelve a mirar porque vive en un párrafo. Y hay un agravante específico: el día que alguien agregue un **noveno** guard `Plan 281 F7 sitio N`, no existe nada que lo obligue a decidir si declara o no. Nace mudo, como nacieron estos ocho, y el plan 290 se convierte en el 281 con más pasos.

**Un `.md` no es un mecanismo. Un test sí.**

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan290_sitios_clasificados.py`

**Símbolo nuevo** en `Stacky Agents/backend/services/capability_degradation.py` (mismo módulo de F1, ningún archivo extra):

```python
# Plan 290 F9 — los sitios de degradación del Plan 281 F7 que a propósito NO
# declaran, con su motivo. Es un contrato, no un comentario: el test de
# tests/test_plan290_sitios_clasificados.py exige que TODO sitio del censo esté
# instrumentado o esté acá. Agregar un guard nuevo sin clasificarlo pone el
# arnés en rojo. Sacar uno de acá obliga a instrumentarlo.
SITIOS_SIN_DECLARAR: dict[str, str] = {
    "api/agents.py":                  "sin execution_id en el scope ni en su llamador (:1687)",
    "api/tickets.py":                 "closure sin execution_id; guard cosmetico y ya protegido por su except",
    "services/acceptance_criteria.py": "gemelo de self_review; ningun llamador tiene execution_id y F3 ya cubre el hecho",
    "services/similar_tickets.py":    "devuelve [] indistinguible de 'sin coincidencias': ruido de alta frecuencia",
    "services/ticket_assigner.py":    "devuelve None y ya loguea en debug; el ticket sin asignar se ve en el tracker",
}
```

**El test, en tres asserts que se sostienen entre sí:**

```python
def test_todo_sitio_281_esta_instrumentado_o_declarado_como_deuda():
    sitios = _censar_sitios()          # grep de "Plan 281 F7 sitio" sobre backend/**/*.py
    assert len(sitios) >= 8, f"el censo solo vio {len(sitios)} sitios: el parser se rompio"
    sin_clasificar = [
        s for s in sitios
        if not _declara(s.archivo) and s.archivo not in SITIOS_SIN_DECLARAR
    ]
    assert sin_clasificar == [], (
        f"sitios de degradacion sin clasificar: {sin_clasificar}. "
        "O instrumentalos con capability_degradation.declarar(), o agregalos a "
        "SITIOS_SIN_DECLARAR con su motivo."
    )

def test_los_dos_instrumentados_declaran_de_verdad():
    # Sentinela de PRESENCIA, no de ausencia: si alguien borra la llamada de F2 o
    # de F3, el test de arriba seguiria verde (el archivo caeria en "no declara" y
    # nadie lo movio a SITIOS_SIN_DECLARAR... salvo que lo mueva). Este lo impide.
    assert _declara("services/business_preflight.py")
    assert _declara("services/self_review.py")
    assert "services/business_preflight.py" not in SITIOS_SIN_DECLARAR
    assert "services/self_review.py" not in SITIOS_SIN_DECLARAR
```

**Los tres moldes de gate muerto, revisados uno por uno** (la pregunta obligatoria: *¿qué tiene que pasar para que se ponga rojo, y ese escenario existe después de la última fase?*):

| Molde | ¿Aplica? | Por qué |
|---|---|---|
| **(a)** centinela sobre un símbolo que una fase posterior borra | **No.** | Ninguna fase de este plan borra los comentarios `Plan 281 F7 sitio N`; `test_plan281_sitios_ado_only.py` (18 passed) los defiende desde otro plan. |
| **(b)** test estático sobre un defecto de ejecución | **No, y es deliberado.** | Lo que vigila es **cableado**, que es un hecho estático: existe un guard sin decisión escrita. El efecto en la fila lo prueban F0/F2/F3, que **sí** ejecutan. Los dos niveles son complementarios. |
| **(c)** `assert` de ausencia suelto | **Neutralizado por dos vías.** | `len(sitios) >= 8` impide el verde por parser roto (el fallo clásico del censo por subcadena), y el segundo test guarda la **PRESENCIA** de las dos declaraciones para que borrar F2 o F3 no pueda quedar verde. |

**¿Se puede poner rojo, hoy, después de F9?** Sí, y con un escenario que ocurre seguido en este repo: agregar un noveno `Plan 281 F7 sitio 9` en un archivo nuevo. Sin clasificarlo, rojo. **Se prueba contra el defecto**: antes de escribir `SITIOS_SIN_DECLARAR`, el test debe dar **1 failed** listando los 6; después, verde.

⚠️ **La clave del dict es la ruta relativa al backend, con `/`** — no `archivo:línea`. Los ocho anclajes de §2.1 se movieron ya una vez y se van a volver a mover; el archivo, no.

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan290_sitios_clasificados.py" -q
```

**Criterio binario:** **2 passed**, y el censo interno reporta **exactamente 8** sitios (si reporta 9, alguien agregó un guard: clasificalo, no toques el `>= 8`).

**Flag:** ninguna. **Impacto por runtime:** ninguno (es un test + una constante). **Trabajo del operador: ninguno.**

**Ratchets:** registrar `tests/test_plan290_sitios_clasificados.py` en los dos (§F0.1).

**Orden:** después de F3 (necesita que los dos sitios ya declaren) y antes de F8 (que documenta lo que F9 congela).

---

### F8 — Documentación, métrica y barrido de no-regresión

**F8.1 — Documentación del sistema.** Actualizar `Stacky Agents/docs/sistema/` con una sección "Degradación declarada": qué es `metadata["capability_degraded"]`, las cinco claves de la forma canónica, los dos sitios instrumentados, y **la lista explícita de los seis que quedaron fuera y por qué** (§6). Un `.md` en `docs/sistema/` entra al corpus RAG; escribilo pensando en que un agente lo va a recuperar.

**F8.2 — El script de la métrica K1.** `Stacky Agents/backend/scripts/medir_degradacion_declarada.py`, **solo lectura**:

- Cuenta ejecuciones con `metadata["capability_degraded"]` no vacío, sobre el total de ejecuciones de proyectos no-ADO posteriores al despliegue del plan.
- Imprime `declaradas / candidatas = N %`.
- ⚠️ **Abre la base en modo lectura y NUNCA escribe.** La base viva es `Stacky Agents/backend/data/stacky_agents.db` (**194 MB** al 2026-08-02).

> ⚠️ **v2 / C12 — el `cp` pelado del `.db` NO sirve, y esta crítica lo comprobó en carne propia.** El motor corre en **WAL** (`db.py:42-49`, `apply_sqlite_pragmas`), así que las escrituras recientes viven en el sidecar `stacky_agents.db-wal` y **no** en el `.db`. Copiar sólo el `.db` da una foto **inconsistente**: al ejecutar esta crítica, medir sobre esa copia hizo que el arranque de la app se cayera con
>
> ```
> sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint failed:
>   tickets.stacky_project_name, tickets.tracker_type, tickets.external_id
> [SQL: UPDATE tickets SET external_id = COALESCE(external_id, ado_id), ...]
> ```
>
> — una migración de arranque que sobre la base real ya corrió sin problema. Una métrica sacada de ahí no es "aproximada": es **falsa**, y peor, se ve como un bug del plan.
>
> **Las dos formas correctas, en orden de preferencia:**
> 1. `sqlite3 <origen> "VACUUM INTO '<destino>'"` — una foto consistente en un solo archivo, sin tocar el origen. **Esta es la que va en el script.**
> 2. Copiar los **tres** archivos juntos (`.db`, `.db-wal`, `.db-shm`) con el servicio detenido.
>
> Lo que **nunca** va: `cp data/stacky_agents.db /tmp/` a secas, ni medir apuntando `DATABASE_URL` a la base viva.

**F8.3 — Barrido de no-regresión.** Correr, **por archivo**, todas las suites que las fases tocaron o vecinan, y comparar contra §5.1:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_business_preflight.py" -q            # 12 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_u1_self_review.py" -q                # 2 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q                 # 59 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q            # 4 failed, 4 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flags_env_read_meta.py" -q           # 1 failed, 1 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_capability_matrix.py" -q     # 2 failed, 8 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan218_coupling_ratchet.py" -q      # 3 failed, 7 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan289_contexto_por_tracker.py" -q  # 34 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan289_stat_de_contexto.py" -q      # 6 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan281_ruteo_por_tracker.py" -q     # 13 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan281_sitios_ado_only.py" -q       # 18 passed
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan281_ratchet_ado_only.py" -q      # 11 passed
cd "Stacky Agents/frontend" && npx tsc --noEmit                                                                                   # 0 errores
```

> **`pytest tests` entero NO es un veredicto.** La suite completa da miles de errores por contaminación cruzada. Cualquier criterio basado en correrla es inválido.

> **`test_plan281_sitios_ado_only.py` (18 passed) es el más importante de este barrido:** es el que vigila los ocho guards que este plan instrumenta. Si F2 o F3 lo mueven, tocaste el `return` en vez de agregar una línea antes.

**Criterio binario:** cada suite con **exactamente el conteo comentado arriba** (= §5.1) y `tsc` en **0 errores**.

**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

### 5.1 Baselines — hay SEIS suites rojas de fábrica; todo criterio es DELTA

**Regla dura para todas las fases: los criterios se comparan contra el conteo del commit base, nunca contra "0 failed".** Varias suites de este repo están rojas por deuda ajena y una fase que las deje igual de rojas **cumple**.

**Baseline MEDIDO el 2026-08-02** sobre `docs/plan-279`, cada archivo por separado con
`"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q --no-header -p no:cacheprovider`:

| Suite | Baseline medido | Rojo de fábrica | Criterio de este plan |
|---|---|---|---|
| `tests/test_harness_flags.py` | **59 passed** | no | delta cero |
| `tests/test_harness_flags_help.py` | **4 failed, 4 passed** | **sí** | delta cero |
| `tests/test_flags_env_read_meta.py` | **1 failed, 1 passed** | **sí** | delta cero |
| `tests/test_plan218_coupling_ratchet.py` | **3 failed, 7 passed** | **sí** | delta cero |
| `tests/test_plan218_capability_matrix.py` | **2 failed, 8 passed** | **sí** | delta cero |
| `tests/test_business_preflight.py` | **12 passed** | no | delta cero y **sin editar el archivo** |
| `tests/test_u1_self_review.py` | **2 passed** | no | delta cero y **sin editar el archivo** |
| `tests/test_plan289_contexto_por_tracker.py` | **34 passed** | no | delta cero |
| `tests/test_plan289_stat_de_contexto.py` | **6 passed** | no | delta cero |
| `tests/test_plan281_ruteo_por_tracker.py` | **13 passed** | no | delta cero |
| `tests/test_plan281_sitios_ado_only.py` | **18 passed** | no | delta cero |
| `tests/test_plan281_ratchet_ado_only.py` | **11 passed** | no | delta cero |
| `npx tsc --noEmit` (frontend) | **0 errores** | no | **0 errores** (gate absoluto, es el único) |

> ⚠️ **`tests/test_self_review.py` NO EXISTE.** El archivo de tests del servicio `services/self_review.py` es **`tests/test_u1_self_review.py`**. Un `pytest tests/test_self_review.py` sale con **exit 4** (`file or directory not found`), que es fácil de confundir con "no hay fallos". Usá el nombre correcto.

**Los 10 rojos de fábrica, por nombre exacto** (son deuda ajena; **no se arreglan en este plan** y hay que descontarlos del delta):

```
test_harness_flags_help.py::test_plain_help_covers_all_registry_keys
test_harness_flags_help.py::test_plain_help_fields_non_empty_and_bounded
test_harness_flags_help.py::test_plain_help_on_off_start_with_si
test_harness_flags_help.py::test_plain_help_avoids_jargon_denylist
test_flags_env_read_meta.py::test_flags_registradas_no_se_leen_del_entorno_con_default_local
test_plan218_coupling_ratchet.py::test_ratchet_importers_no_crece
test_plan218_coupling_ratchet.py::test_ratchet_literales_no_crece
test_plan218_coupling_ratchet.py::test_ratchet_rutas_ado_no_crece
test_plan218_capability_matrix.py::test_full_y_partial_exigen_evidencia
test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado
```

> **Re-medí igual antes de empezar.** La sesión paralela commitea cada pocos minutos y estos números pueden moverse. Anotá `git rev-parse HEAD` y volvé a correr la tabla; si un conteo difiere, **actualizá la tabla en el commit de F0** y usá ese número como baseline. Lo que no se acepta es comparar contra "0 failed": cuatro de estas suites nunca llegan a cero.

> ✅ **v2 — los 13 baselines fueron RE-MEDIDOS uno por uno en la crítica, con el comando de arriba, y los 13 dieron EXACTAMENTE lo que dice la tabla**, incluidos los 2 fallos nominales de `test_plan218_capability_matrix.py` (`test_full_y_partial_exigen_evidencia` y `test_doc_de_paridad_esta_sincronizado`) y el `tsc --noEmit` en 0 errores / exit 0. La tabla del v1 es de fiar.
>
> ⚠️ **Dos suites que este plan toca y que NO estaban en la tabla del v1 — medilas en F0 y sumalas:** `tests/test_context_enrichment.py` y `tests/test_run_directive_block.py`. La segunda importa: `test_run_directive_block.py:53` llama **directo** a `context_enrichment._inject_run_directive(...)`, cuya firma cambia en §F2.4. El default `None` debería dejarla intacta, pero es la primera que hay que mirar si algo se pone rojo.
>
> ⚠️ **Trampa de medición que esta crítica se comió** (te va a pasar): correr con `DATABASE_URL` apuntando a una **copia pelada** del `.db` hace que `test_u1_self_review.py` dé **2 errors** en vez de 2 passed, por una migración de arranque que choca contra el índice único. No es deuda ni regresión: es la copia sin WAL (§F8.2 / C12). Medí contra la base real en modo lectura, o contra una base **vacía**, o contra un `VACUUM INTO`.

### 5.2 Riesgos, uno por uno

| # | Riesgo | Mitigación |
|---|---|---|
| **R1** | El implementador "arregla" las degradaciones y cambia semántica. | §1.2 con aviso destacado, y un test de no-regresión por sitio que fija el valor neutro exacto (§F2.5, §F3.3). |
| **R2** | `declarar()` levanta y tumba una corrida. | `try/except` total en F1 + `log = log or _noop_log` como primera línea (**v2 / C7**: sin eso el propio manejador lanzaba `TypeError`) + `test_declarar_sin_log_y_con_sesion_rota_no_levanta` (§F1) + `test_declarar_falla_y_el_review_sigue` (§F3.3). |
| **R2b** *(v2)* | El aviso queda escrito en la base y **no llega a la interfaz** — el defecto del 289, una capa más arriba. | **Verificado que el canal está limpio:** `models.py:345` serializa `"metadata": self.metadata_dict` **entero, sin whitelist**, y `api/executions.py:317-327` (`get_execution`) devuelve ese `to_dict(...)` tal cual. No hay filtro que descarte una clave nueva. El drawer ya lee `metadata` completo (`ExecutionDetailDrawer.tsx:74`). **No hay que construir nada en el medio** — pero si alguien agrega un filtro ahí, F4 se queda mudo en silencio. |
| **R3** | Falsos positivos: se declara degradación en proyectos ADO. | El guard `tracker_is_azure_devops(...) and ruteo_estricto_por_tracker()` se repite en F3.1, con sentinela negativo dedicado (`test_proyecto_ado_sin_criterios_no_declara`). |
| **R4** | La interfaz no renderiza una capacidad desconocida. | `etiquetaDeCapacidad` devuelve la key cruda (`?? capability`, nunca `undefined`). **v2 / C4:** las **dos** keys de producción **sí** tienen etiqueta en `ETIQUETAS`; el camino desconocido es un borde defensivo para una key futura, y se prueba con una key sintética. El test de §F4.4 guarda **además** que las dos de producción NO caen al default — sentinela de que nadie borró una entrada del diccionario. |
| **R5** | El toggle de GitLab dice "guardado" y el motor no cambia. | F5.2 agrega el `setattr` sobre el singleton, y el test lo afirma **junto con** la persistencia en el `.env` temporal, en la misma función. |
| **R6** | Apagar por error una de las 23 flags al corregir su texto. | F7.2 prohíbe explícitamente tocar cualquier campo que no sea `description=`. El gate de F7.3 **no** mira los defaults: mira la coherencia texto↔código, así que apagar una flag para "cumplir" el test también lo pondría verde — por eso la prohibición es textual y el revisor debe mirar el `git diff` de `harness_flags.py` y confirmar que **solo** hay cambios dentro de strings de `description`. |
| **R7** | `STACKY_TRACE_PROMPT_TEXT_ENABLED` está ON y filtra prompts completos a la metadata. | Este plan **declara** el hecho en la descripción (F7.2) y **no** cambia la conducta. Queda como decisión del operador (§7), porque apagarla es un cambio de comportamiento fuera del alcance. |
| **R8** | La sesión paralela pisa los mismos archivos. | Está viva y commitea cada pocos minutos; `api/agents.py`, `services/project_context.py` y `frontend/src/pages/*` figuran sucios. **Antes de cada commit: `git status --short`, y commitear con pathspec explícito** (`git commit -- "<ruta>"`). **Nunca** `amend`, `reset`, `rebase`, `stash` ni `checkout`. |
| **R9** | Los ratchets se ponen rojos al agregar 6 archivos de tests. | Registro **por fase, en el commit que crea el archivo** (§F0.1), en **los dos** archivos, anclando por símbolo, sin rutas con espacios, y sacando del allowlist si estuviera. |
| **R10** | ~~`execution_id` no está en el scope de `context_enrichment.py:1288`.~~ **YA NO ES UN RIESGO: ES UN HECHO MEDIDO Y RESUELTO.** | **v2 / C3.** Está confirmado que no está (la función es `_inject_run_directive(*, ticket_id, agent_type, blocks, log)`, `:1261`). La "salida explícita" del v1 (pasar `None`) queda **prohibida**: con ella F2 no escribe nunca en producción y F0 caso 1 sólo se pone verde probando el productor — el bloqueante del 289 de vuelta. §F2.4 da las 4 ediciones de `context_enrichment.py` y las 3 de los runtimes, todas verificadas. Y **se borra la frase "F3 sostiene el KPI por sí solo"**: era el permiso escrito para no construir F2. |
| **R12** *(v2)* | Los 3 runtimes se cablean a medias (2 de 3), que es literalmente lo que pasó en el Plan 289. | `test_los_tres_runtimes_pasan_el_execution_id` (§F2.5): AST sobre los 3 archivos, exige el kwarg en las 3 llamadas **y** que el parser haya visto exactamente 3. |
| **R13** *(v2)* | El barrido de F7 toca `harness_flags.py` y mueve una suite ajena. | Verificado que `PLAIN_HELP` vive en **otro módulo** (`services/harness_flags_help.py`) y no se deriva de `description`, así que `test_harness_flags_help.py` es estructuralmente insensible a esta edición. Igual se corre por separado (§F7.4) con criterio delta cero. |
| **R11** | Un test escribe en la base o el `.env` reales. | F5.4 exige monkeypatch de `_ENV_PATH`; F8.2 exige copia read-only. Un pytest suelto **sí** escribe en la base viva de este repo. |

---

## 6. Fuera de scope (con motivo)

**Los seis sitios de degradación que NO se instrumentan en este plan:**

| Sitio | Motivo de la exclusión |
|---|---|
| `api/agents.py:1921` (`_build_ado_enrichment_sections`) | No tiene `execution_id` en el scope y su llamador (`:1687`) tampoco de forma directa. Requeriría plomería nueva por varias capas — el defecto de alcance que hundió planes anteriores. |
| `api/tickets.py:5111` (`_equivalent_task_status`) | Es un **closure** dentro de un handler, sin `execution_id`, y su propio comentario lo declara *"guard COSMÉTICO para el gate: la función ya está funcionalmente protegida"*. Bajo daño. |
| `api/tickets.py:7762` (`System.Rev`) | Degrada un sellado de aprendizaje bidireccional (Plan 60 F1), no una capacidad que el operador espere. Bajo daño. |
| `services/acceptance_criteria.py:43` | Gemelo funcional de `self_review`, pero **ninguno de sus llamadores tiene `execution_id`**. F3 ya cubre el mismo hecho de negocio ("no hay criterios de aceptación en este tracker") desde el punto donde el dato existe. Instrumentar los dos duplicaría la entrada. |
| `services/similar_tickets.py:122` | Devuelve `[]`, que es indistinguible de "no hubo coincidencias" — un resultado legítimo y frecuente. Declararlo generaría ruido de alta frecuencia y bajo valor. Sin `execution_id` además. |
| `services/ticket_assigner.py:401` | Devuelve `None` y ya loguea en `debug`. Sin `execution_id`. Bajo daño: el ticket queda sin asignar, que es visible en el propio tracker. |

> **Por qué se acotó a dos y no "los 8, y si falta alguno se agrega":** un criterio así es **alcance infinito con forma de criterio binario** y no se puede declarar cumplido. Los dos elegidos son los de mayor daño (`ok=True` que se lee como "validado"; `score=1.0` que se lee como "revisado"). **Los otros seis quedan como deuda declarada — y desde v2 la declaración es EJECUTABLE**: viven en `SITIOS_SIN_DECLARAR` con su motivo, vigilados por §F9, no sólo en un párrafo de F8.1.
>
> ⚠️ **v2 — una corrección al motivo del recorte.** El v1 decía que los dos elegidos "son los únicos donde el destino está al alcance **sin cambiar firmas públicas**". Eso resultó **falso para F2**: `business_preflight` necesita cambiar **tres** firmas (`evaluate`, `_evaluate_functional` y el despacho de `_PREDICATES`) más **dos** de `context_enrichment` (`enrich_blocks`, `_inject_run_directive`) y **tres** call sites de runtime. Son todas backward-compatible (keyword-only con default `None`), pero son cambios de firma. **El único de los ocho donde el `execution_id` ya está en el scope inmediato es `self_review.review_artifact` (`:76`).** Que quede escrito así, porque un implementador que crea que F2 es "una línea antes del return" va a subestimar la fase por 8 ediciones.
>
> **Verificados en la crítica, uno por uno:** `similar_tickets.py:122` (guard; `return []` en `:124`) — su función recibe `project_name`, sin `execution_id`, y `[]` es indistinguible de "sin coincidencias": **exclusión correcta**. `ticket_assigner.py:400-403` (guard; loguea en `debug` en `:404`) — sin `execution_id` y el resultado es visible en el propio tracker: **exclusión correcta**. `api/agents.py:1921` — su llamador es `:1687`, dentro de un armador que tampoco tiene la fila: **exclusión correcta**.

**Otras exclusiones explícitas:**

- **No se agrega `tracker.acceptance_criteria` a `CAPABILITY_MATRIX`** (motivo técnico completo en §F3.2: rompería `test_plan218_capability_matrix.py` y arrastraría regenerar el documento de paridad).
- **No se migran los `base_url` ya guardados.** F6 normaliza al escribir; los proyectos existentes se corrigen solos la próxima vez que se guarden. Una migración masiva sobre configuraciones del operador exige human-in-the-loop y es un plan aparte.
- **No se apaga ninguna flag**, incluida `STACKY_TRACE_PROMPT_TEXT_ENABLED` (§R7).
- **No se toca `ParityMatrixPanel` ni `DiagnosticsPage`** salvo el montaje de una línea en F5.3.
- **No se cambia el default de `STACKY_GITLAB_ENABLED` en `config.py`** (§F5.1).
- **No se muestra `metadata["ado_context"]`** (el stat que persiste el Plan 289) en la interfaz, pese a que se verificó que tiene **cero** consumidores en `frontend/src/`. Es un hallazgo real pero es alcance del 289, no de este plan.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **Degradación** | Stacky decide **a propósito** no ejecutar una capacidad porque el tracker del proyecto no la tiene, y devuelve un valor neutro. **No es un error.** |
| **Valor neutro** | El retorno que la función da cuando degrada (`""`, `[]`, `None`, `"unknown"`, `ok=True/mode=None`). **Nunca se modifica en este plan.** |
| **Sitio** | Uno de los ocho guards del Plan 281 F7. Se identifica por **símbolo** (`business_preflight.evaluate`), nunca por `archivo:línea`. |
| **Declarar** | Anotar la degradación en `metadata["capability_degraded"]` de la fila `AgentExecution`. Solo lectura hacia afuera; una escritura local. |
| **Delta cero** | Criterio de aceptación en el que una suite debe terminar con **el mismo** conteo de passed/failed que en el commit base, no con cero fallos. |
| **Rojo de fábrica** | Suite que ya falla antes de tocar nada, por deuda de otro plan. Se mide, se registra y **no se arregla acá**. |

### 7.2 Orden de implementación

```
F0 (centinelas ROJOS) → F1 (registro) → F2 (business_preflight) → F3 (self_review) → F4 (interfaz)
                                                                        │
                                                                        ├──► F9 (centinela de los 8 sitios)
                                                                        │
F5 (switch GitLab) ── F6 (base_url) ── F7 (23 desc. + 1 label) ── independientes entre sí ──┐
                                                                                           ▼
                                                                                  F8 (docs + métrica)
```

- **F0 → F1 → F2 → F3 → F4** es la cadena obligatoria: F4 no tiene qué mostrar sin F2/F3, y F2/F3 no tienen dónde escribir sin F1.
- **F9 va después de F3** (necesita que los dos sitios ya declaren, si no su segundo test nace rojo) y **antes de F8**.
- **F5, F6 y F7 son independientes** entre sí y del resto: se pueden hacer en cualquier orden, incluso antes que F0. Si el presupuesto se corta, **cada una entrega valor sola**.
- **F8 va última** porque documenta lo que quedó construido y mide el KPI.

> ⚠️ **v2 — F2 ya NO es opcional.** El v1 declaraba en R10 que "F3 sostiene el KPI por sí solo", lo que autorizaba a saltear F2 en silencio. Con la salida de `execution_id=None` eliminada (C3), **F2 es parte de la cadena obligatoria**: si se corta el presupuesto antes de F2, lo que se entrega es F1 sin ningún escritor, o sea código construido y jamás cableado. **Cortar en F1 no es una entrega parcial válida.** Los cortes válidos son: después de F4 (la cadena entera), o cualquier subconjunto de {F5, F6, F7}.

Un commit por fase. Mensaje: `feat(plan-290): F<n> — <qué hace>` (o `test(plan-290): F0 — ...`, `docs(plan-290): F8 — ...`).

### 7.3 Definition of Done

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Los centinelas de F0 se vieron **rojos** antes de F1, con salida pegada en el commit | Salida de pytest en el mensaje del commit de F0, **2 failed**, sin `ImportError` |
| 2 | `test_plan290_degradacion_declarada.py` en **2 passed** tras F3 | comando §F3.3 |
| 3 | `test_plan290_registro_degradacion.py` en **9 passed** | comando §F1 |
| 4 | `test_plan290_preflight_no_regresion.py` en **6 passed** | comando §F2.5 |
| 5 | `test_plan290_self_review_no_regresion.py` en **4 passed** | comando §F3.3 |
| 6 | `test_plan290_gitlab_switch_ui.py` en **6 passed** | comando §F5.4 |
| 7 | `test_plan290_base_url_normalizada.py` en **11 passed** | comando §F6 |
| 8 | `test_plan290_defaults_no_mienten.py`: **2 failed** antes de F7.2 (23 descripciones + 1 label) y **2 passed** después | comandos §F7.3, **ambas salidas** en el commit |
| 9 | **K2 = 0** flags con descripción **o label** contradictorio | ídem #8 |
| 9b | *(v2 / C3)* **La cadena del `execution_id` está completa**: `enrich_blocks` la acepta, `_inject_run_directive` la pasa, `evaluate` la reenvía a `_evaluate_functional`, y **los 3 runtimes** la mandan | `test_los_tres_runtimes_pasan_el_execution_id` (§F2.5) + el caso 1 de F0 entrando por `enrich_blocks` |
| 9c | *(v2 / A1)* `test_plan290_sitios_clasificados.py` en **2 passed**, con el censo reportando **8** sitios | comando §F9 |
| 10 | **K3**: el switch de GitLab aplica en caliente **y** persiste | test `test_put_enciende_y_aplica_en_caliente` (§F5.4) |
| 11 | **K4**: las 10 filas de la tabla de `base_url` coinciden cliente/servidor | §F6 |
| 12 | `npx tsc --noEmit` en **0 errores** | §F8.3 |
| 13 | Todas las suites de §5.1 en **delta cero** contra el baseline medido | §F8.3 |
| 14 | `test_business_preflight.py` (12 passed) y `test_u1_self_review.py` (2 passed) **sin editar** | `git diff --stat <base>..HEAD -- "<ruta>"` vacío para los dos |
| 15 | Los **8** archivos de tests nuevos registrados en **los DOS** scripts: `.sh` de **820 → 828**, `.ps1` de **756 → 764** | §F0.1 |
| 15b | El `.ps1` sigue siendo un array válido: la que era última entrada (`"tests/test_plan289_stat_de_contexto.py"`, hoy **sin** coma) ahora lleva coma. El diff del `.sh` tiene **0** líneas borradas y el del `.ps1` exactamente **1** | inspección del `git diff` de los dos scripts |
| 15c | Cada archivo nuevo **pasa aislado**, y ninguno de los 820/756 previos cambió de veredicto | §F0.1, criterio 2 y 3 |
| 16 | **Cero flags nuevas** en `harness_flags.py`; el único cambio ahí es dentro de strings `description=` y del `label=` de `STACKY_TRACE_PROMPT_TEXT_ENABLED` | `git diff` de `harness_flags.py` revisado a mano |
| 17 | Ningún archivo de la sesión paralela commiteado | `git status --short` antes de cada commit + pathspec explícito |
| 18 | Documentación de F8.1 escrita, con los 6 sitios fuera de scope enumerados | inspección |

### 7.4 Pendiente del operador (no bloquea el DoD)

1. **Decidir sobre `STACKY_TRACE_PROMPT_TEXT_ENABLED`.** Está **ON** y su **título y su descripción** prometían privacidad. Con F7 los dos dicen la verdad y la descripción trae la advertencia accionable; apagarla o no es decisión del operador (human-in-the-loop). Es la única acción que este plan le deja, y es **informativa**, no un trabajo que el plan haya creado.
   > *v2 — por qué NO la apaga el plan, con la evidencia que lo decide:* el comentario de `harness_flags.py:2210` dice literalmente *"promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)"*. **La encendió el operador a propósito.** Apagarla no sería corregir un descuido sino revertir una decisión suya sin consultarlo, y podría vaciar de contenido cualquier herramienta de trazabilidad que hoy dependa del texto del prompt. La conducta correcta es la que hace F7: **corregir los dos textos que mienten** (cambio de cero riesgo) y devolverle la perilla informada.
2. **Smoke visual** del aviso de F4 y del switch de F5 con un proyecto GitLab real.

---

## 8. Restricciones no negociables (recordatorio para el implementador)

1. **3 runtimes con paridad** — verificada archivo por archivo en §3.2, no asumida. Fallback explícito: `declarar()` devuelve `False` sin `execution_id`.
2. **Cero trabajo extra al operador** — declarado fase por fase.
3. **Toda flag nueva nace ON** salvo que queme tokens en reposo o escriba en un sistema real. **Este plan no registra ninguna flag nueva** y explica por qué (§3.1).
4. **Human-in-the-loop** — nada decide por el operador.
5. **Mono-operador sin auth real** — no hay RBAC; `403` = flag apagada, no permiso.
6. **No degradar** performance, seguridad, estabilidad ni DX. Backward-compatible.
7. **Reusar lo existente** — `CAPABILITY_MATRIX`, `ParityMatrixPanel`, `persistir_stats_de_contexto` (como idioma), `tracker_efectivo_de_ticket`, `LogLevelPanel` (como patrón), `_MANAGED_KEYS`.
8. **Nada de vaguedad.** Si al implementar encontrás una ambigüedad que este documento no resuelve, **paralo y reportala** — no la resuelvas inventando.

---

## 9. Tabla de anclajes verificados (2026-08-02)

### 9.0 — Re-verificación del juez (v2): lo que el v1 corrigió MAL, y lo que quedó desfasado

Todos los anclajes del v1 fueron **abiertos de nuevo**. El v1 acertó en casi todo; estas son las excepciones, y una de ellas es una **corrección incorrecta**, que es peor que no haber corregido:

| Anclaje del v1 | Veredicto E1 | Real, verificado |
|---|---|---|
| `newProjectGitlabModel.ts:39` = `normalizeGitlabUrl` — el v1 "corrigió" el `:37` del encargo | **CORRECCIÓN INCORRECTA** | **`:37`** es `export function normalizeGitlabUrl(raw: string): string {` — el encargo tenía razón. `:38` es el `const limpio`, `:39` el `.match(...)`. La corrección de **ruta** (`src/projects/`, no `src/services/`) **sí** era correcta. |
| `STACKY_TRACKER_STRICT_ROUTING` (§3.1) | **INEXISTENTE** ⇒ era BLOQUEANTE (sostenía la decisión de alcance "cero flags nuevas") | **`STACKY_TRACKER_ROUTING_STRICT_ENABLED`**. `config.py:1455-1456` (`"true"` ⇒ ON), `FlagSpec` en `harness_flags.py:6035`, lectura en `project_context.py:97`. |
| "el guard del sitio 5 está en `evaluate`" (implícito en F2.1) | **INEXISTENTE** ⇒ BLOQUEANTE | Está en **`_evaluate_functional`** (`business_preflight.py:37-44`). `evaluate` es `:161` y despacha por `_PREDICATES` en `:191-197`. |
| `_ticket` en `business_preflight` (F2.2) | **INEXISTENTE** ⇒ BLOQUEANTE | No existe en ningún scope del archivo. Usar `tracker_declarado_del_proyecto(project_name)` (`project_context.py:124`). |
| "`execution_id` en el scope de `context_enrichment.py:1288`" (F2.4, como incertidumbre) | **INEXISTENTE — resuelto** ⇒ era BLOQUEANTE por la salida que habilitaba | La función es `_inject_run_directive(*, ticket_id, agent_type, blocks, log)` (`:1261-1334`); su llamador es `enrich_blocks` (`:60-67`, llamada en `:133`). Ninguno lo tiene. §F2.4 construye la cadena. |
| `DiagnosticsPage.tsx:328` = `<LogLevelPanel />` | **DESFASADO** | **`:327`**. (`<ParityMatrixPanel />` en `:331` **sí** es correcto.) |
| `parityMatrixModel.ts:81` = `statusMark` | **DESFASADO** | **`:83`** es el `export function statusMark`; `:79-82` es su comentario. |
| `api/global_config.py:88-93` = "UN solo escritor" (LOG_LEVEL) | **DESFASADO** | El comentario es `:89-92` y `"LOG_LEVEL"` es `:93`. `:88` es `"STACKY_GITLAB_CA_BUNDLE"`. |
| `test_business_preflight.py:233` como test del guard no-ADO | **DESFASADO EN SENTIDO** (la línea es correcta) | El `assert result.warnings` **está** en `:233`, pero el caso parchea el cliente con `RuntimeError` (`:228`): prueba el `except` de red (`:198-200`), **no** el guard de `:94-99`. |
| "`review_artifact` desde `criteria_repair` en un contexto sin fila" (§3.2) | **AFIRMACIÓN FALSA** | `harness/criteria_repair.py:82` pasa un `execution_id` **real**. |
| `business_preflight.py:27` / `:94-99` / `:161` | **OK exacto** | `warnings: list[str] = field(default_factory=list)` en `:27`; el guard y su `return` ocupan `:94-99`; `def evaluate` en `:161`. |
| `context_enrichment.py:1319` / `:284` | **OK exacto** | El `warnings[0]` en `:1319`; `persistir_stats_de_contexto` en `:284` (idioma de reasignación en `:315-317`). |
| `self_review.py:76` / `:168` y los 3 call sites de `apply_to_execution` | **OK exacto** | `:76`, `:168`, y `agent_completion_internal.py:174`, `claude_code_cli_runner.py:3227`, `codex_cli_runner.py:2008`. |
| Los 8 sitios de §2.1 | **OK** (comentario y guard, ±1 donde el `if` es multilínea) | Censo `grep -rn "Plan 281 F7 sitio"` reproducido: 8/8, mismos archivos y mismas líneas. |
| 490 `FlagSpec` / 23 contradicciones / las 23 líneas de §2.4 | **OK exacto** | Censo AST re-ejecutado: 490 y 23, con las 23 líneas idénticas. |
| `CAPABILITY_KEYS`=71; ADO 38/8/25; GitLab 34/14/21/2 | **OK exacto** | Reproducido importando el módulo. `tracker.comments.list` **está** en `CAPABILITY_KEYS`; `tracker.acceptance_criteria` **no**. |
| 820 / 756 entradas de los ratchets, y la coma final del `.ps1` | **OK exacto** | 820 y 756. La última del `.ps1` (línea 987) es `"tests/test_plan289_stat_de_contexto.py"` **sin coma**. |
| Allowlist: 207 líneas / 194 efectivas / `test_harness_capabilities.py` | **OK exacto** | 207 / 194; la línea de `capability` es la **97**. |
| `global_config.py:82`, `:136-168`; `projects.py:141-142`; `config.py:1297-1299`; `.env:7`; `parity.py:15`; `harness_flags.py:134`; `setup_guides.py:147`; `endpoints.ts:2371` y `:3392`; `ExecutionDetailDrawer.tsx:74`/`:189`/`:198`; `LogLevelPanel.tsx:9-11`; `project_manager.py:670`; `provider_capabilities.py:95`/`:344`/`:349`/`:354`/`:364`; `agents.py:542`/`:1687`/`:1921` | **OK exacto (los 22)** | Abiertos uno por uno. |
| `test_self_review.py` inexistente / **exit 4** | **OK — reproducido** | `ls` falla; `pytest tests/test_self_review.py` sale con **4**. |
| Los 13 baselines de §5.1 y `tsc --noEmit` = 0 | **OK — los 13 reproducidos** | Ver el recuadro de §5.1. |

### 9.1 — Tabla del v1 (anclajes del encargo original)

Los que llegaron en el encargo y estaban mal, corregidos:

| Anclaje del encargo | Estado | Anclaje real verificado |
|---|---|---|
| `services/business_preflight.py:94` | **OK** | `:94` — el `if` del guard |
| `services/similar_tickets.py:122` | **OK** | `:122` |
| `services/ticket_assigner.py:400` | **OK (±1)** | `:400` abre el `if`, `:401` la condición |
| `services/acceptance_criteria.py:42` | **OK (±1)** | `:42` abre el `if`, `:43` la condición |
| `services/self_review.py:56` | **OK (±1)** | `:56` abre el `if`, `:57` la condición |
| `api/agents.py:1920` | **±1** | `:1921` (comentario del sitio en `:1911`) |
| `api/tickets.py:4944` | **INCORRECTO** | El sitio real es **`:5111`**. `:4944` es validación de esquema de `pending-task.json`, nada que ver. |
| `api/tickets.py:7595` | **INCORRECTO** | El sitio real es **`:7762`**. `:7595` es el rescate de artefactos (`artifact_rescue`). |
| `config.py:1297-1299` | **OK** | `os.getenv("STACKY_GITLAB_ENABLED", "false")` |
| `backend/.env:7` | **OK** | `STACKY_GITLAB_ENABLED=true` |
| `api/projects.py:141-142` | **OK** | `_write_global_env` + `setattr` |
| `harness_flags.py:4591` ("miente sobre el default") | **INCORRECTO** | `:4591` es `default=True` de `STACKY_PIPELINE_*`, cuya descripción **no** afirma OFF. Las que sí mienten son **23** y están tabuladas en §2.4. |
| `harness_flags.py:4446` ("miente sobre el default") | **INCORRECTO** | `:4446` es el `FlagSpec` de `STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC`, un `int` sin afirmación de default booleano. |
| `frontend/.../newProjectGitlabModel.ts:37` | **OK** *(v2 corrige al v1)* | `:37` **era correcto**: `export function normalizeGitlabUrl(...)`. Lo único mal era la **ruta**: es `frontend/src/projects/newProjectGitlabModel.ts`, **no** `frontend/src/services/`. |
| `project_manager.py:670` | **OK** | `"base_url": url.rstrip("/")`. Ruta real: `backend/project_manager.py` (raíz del backend, **no** `services/`). |
| `services/provider_capabilities.py:200` | **≈** | `CAPABILITY_MATRIX` se define en **`:95`**; `:200` cae dentro del bloque de `gitlab`. |
| `ParityMatrixPanel.tsx:16` | **OK** | Componente en `frontend/src/components/ParityMatrixPanel.tsx` |
| `DiagnosticsPage.tsx:329` | **±2** | `<ParityMatrixPanel />` está en **`:331`**; `<LogLevelPanel />` en **`:327`** *(v2: el v1 decía `:328`)* |
| Conteo GitLab "34/14/**22**/2" | **CORREGIDO** | Medido en proceso: **34 full / 14 partial / 21 absent / 2 n-a** = 71. ADO 38/8/25 = 71 ✓ |
| `persistir_stats_de_contexto` llamada por los 3 runtimes | **OK** | `agent_runner.py:819`, `claude_code_cli_runner.py:685`, `codex_cli_runner.py:342` |
| `tracker_efectivo_de_ticket` | **OK** | `services/project_context.py:206` |
| "`business_preflight` es mudo" | **MATIZADO** | El campo `warnings` **existe** (`:27`), **se puebla** (`:94-99`) y **`context_enrichment.py:1319` lo lee** (solo `warnings[0]`, hacia el prompt). Lo que falta es el canal hacia el **operador**. Ver §2.2. |
| "el master switch no está en la UI" | **CONFIRMADO, con matiz** | Correcto de cara al operador (**0 referencias** en `frontend/src/`), pero el seam del backend **ya existe**: `api/global_config.py:82` la tiene en `_MANAGED_KEYS`. Eso cambia el diseño de F5: no hace falta `FlagSpec`, hace falta superficie + hot-apply. |
| "`test_self_review.py`" | **NO EXISTE** | El archivo real es **`tests/test_u1_self_review.py`** (2 passed). Un pytest sobre el nombre inexistente sale **exit 4**, no 0. |
| "los ratchets" (por nombre) | **NO se llaman así** | Son `backend/scripts/run_harness_tests.sh` (array `HARNESS_TEST_FILES=(`, 820 entradas) y `run_harness_tests.ps1` (array `$HarnessTestFiles = @(`, 756 entradas). Divergen en 64. |
| "SEIS rojos de fábrica" | **CORREGIDO: son 4 ARCHIVOS / 10 TESTS** | Medidos y nombrados en §5.1. `test_harness_flags.py` **NO** es uno de ellos: da **59 passed** limpio. |
| `test_plan218_capability_matrix.py` (supuesto verde) | **ROJO DE FÁBRICA** | **2 failed, 8 passed**, y los dos rojos son justo los que citaba el argumento de §F3.2. Corregido ahí: el criterio es delta cero, no "pasa". |
| `tests/harness_ratchet_allowlist.txt` | **EXISTE** | 207 líneas (194 efectivas). **No** menciona `self_review` ni `business_preflight`. Única línea con `capability`: `tests/test_harness_capabilities.py  # pendiente-de-triage`, ajena a este plan. |
