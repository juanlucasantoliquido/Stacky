# Plan 242 — Centro de Costos telemétrico, scoring de eficiencia y estimador de USD aprendido

**Estado:** **v2 · CRITICADO (v1 → v2)** — VEREDICTO SOBRE v1: **RECHAZADO** (3 bloqueantes). Estado de v2 tras aplicar los fixes: **APROBADO-CON-CAMBIOS**.
**Autor v1:** StackyArchitectaUltraEficientCode · **Juez v2:** agente independiente que **abrió cada archivo y verificó cada anclaje** (tabla en §0.2).
**Fecha v1:** 2026-07-25 · **Fecha v2:** 2026-07-26
**Depende de:** Plan 142 (Centro de Costos, IMPLEMENTADO) · Plan 158 (paridad telemetría claude_code_cli, IMPLEMENTADO)
**Frontera con:** Plan 171 (telemetría operativa — **IMPLEMENTADO**) · Plan 199 (cosecha histórica + agregadores del Centro de Costos — **IMPLEMENTADO parcial**). ⚠️ v1 daba los dos por pendientes y ésa fue la raíz de 5 defectos en cascada: ver **C1**.
**Numeración:** 242. Los números 219–236 están reservados por el Plan 218. El máximo actual en `Stacky Agents/docs/` es **243**. ⚠️ El **244 ya está reservado** por el corte formal del Plan 243 (`243 = F0..F3.5` / `244 = F4..F9`), así que el corte de este plan (C13) usa el **245**.

---

## 0. Crítica adversarial v1 → v2

> Este bloque es la crítica; el resto del documento es el plan ya corregido. Cada fix aplicado
> aguas abajo está marcado `[v2]` en el punto exacto donde cambia.

### 0.1 CHANGELOG v1 → v2 (22 hallazgos)

**Los 7 bloqueantes salieron de abrir los archivos que v1 citaba de memoria.** El doc lo revisaron **dos jueces por separado**, sin verse entre sí; convergieron de forma independiente en C1, C2 y C4 (lo cual sube mucho la confianza en esos tres) y cada uno encontró bloqueantes que el otro no vio. **Toda afirmación del segundo juez fue re-verificada contra el árbol antes de entrar acá; una no sobrevivió** (ver C21).

- **C1 (BLOQUEANTE, resuelto) — la premisa central del plan era falsa: el Plan 171 YA ESTÁ IMPLEMENTADO.** v1 declaraba en §4 y §2.1 que el 171 estaba *"CRITICADO pero NO implementado"* y construía sobre eso toda su sección de frontera. En el árbol de trabajo existen **`services/run_signals.py`** (16,5 KB), **`services/ops_telemetry.py`**, **`services/run_trace.py`**, **`tests/test_run_signals.py`** y **3 flags registradas** del 171 (`STACKY_OPS_TELEMETRY_ENABLED`, `STACKY_OPS_BASELINE_ENABLED`, `STACKY_OPS_TRACE_ENABLED`, `harness_flags.py:300-302`) **en la misma categoría `observabilidad_notif` donde el 242 quiere meter sus 7**. Resuelto en §2.1, §4, F0 y F1.
- **C2 (BLOQUEANTE, resuelto) — el diff de F0.4 no aplica y rompe el archivo.** `ExecRecord` **ya tiene** `completed_at` (`cost_analytics.py:153`, puesto por el Plan 171) y `load_records` **ya lo pasa** (`:231`). El ancla del diff de v1 (`raw_metadata=md))`) **no existe**: la línea real es `raw_metadata=md, completed_at=ex.completed_at))`. Aplicado literalmente ⇒ **campo duplicado** en el dataclass y **keyword argument repetido** (`SyntaxError`). Resuelto en F0.4.
- **C3 (BLOQUEANTE, resuelto) — dos percentiles incompatibles en el mismo producto.** v1 prometía *"una sola definición de percentil en todo el plan"* mientras el repo **ya tiene** `run_signals.percentile_nearest_rank` (`:102`, *nearest-rank*) y v1 agregaba un segundo `cost_stats.percentile` (*interpolación lineal*). Mismos datos, dos respuestas distintas. Lo mismo con la duración: `run_signals.from_exec_record` (`:64`) calcula `duration_seconds` **sólo si `status == "completed"`** (a propósito: los errores fallan rápido y falsearían la latencia), y v1 la calculaba siempre. Resuelto en F0.3 y F1.3.
- **C4 (IMPORTANTE, resuelto) — el autotrain BLOQUEA el fin de cada 10ª ejecución.** `_run_post_hooks` (`ticket_status.py:325`) es un `for` **síncrono**: `hook(**kwargs)` inline. v1 citaba `ticket_status.py:313` como prueba de que *"los hooks nunca bloquean"*, pero ese docstring dice que **los errores no se propagan**, no que el hook sea asíncrono. Resuelto en F5.5 (thread daemon) y R4.
- **C5 (IMPORTANTE, resuelto) — F5 reinventa un ledger que el repo ya tiene 4 veces, y sin lock.** Existen `ci_run_ledger.py` (Plan 191), `sql_exec_ledger.py`, `env_apply_ledger.py` y `ado_edit_ledger.py`, todos con el mismo patrón de la casa: `_LOCK = threading.Lock()`, `MAX_ROWS = 500` con retención por reescritura, `_read_rows`/`_write_rows` atómicos y **allowlist de campos**. v1 proponía append-only sin lock, cap de 50.000 líneas y emparejamiento en memoria. Resuelto en F5.1/F5.4.
- **C6 (IMPORTANTE, resuelto) — KPI-7 no mide lo que F6.4 afirma que garantiza.** KPI-7 cronometra `fit_ridge` sobre filas sintéticas; F6.4 dice *"Ejecuta `cost_model.train(days)` sincrónicamente (KPI-7 garantiza < 2 s)"*. `train()` incluye además `collect_training_rows` (query de hasta 20.000 filas) y la evaluación. Resuelto en KPI-7 y F6.4.
- **C7 (IMPORTANTE, resuelto) — pseudocódigo y test se contradicen en `_predict_log`.** El comentario y `test_predict_log_usa_la_media_para_continuos_ausentes` afirman que un continuo ausente aporta `(0 - mu[j])/sd[j] * w[j]`; el código itera **sólo** las entradas presentes, así que aporta **0**. Además `mu[j]` se calcula con `valor_en(...)` (ausente = 0,0), o sea con una imputación distinta a la que usa el Gram. Resuelto en F3.4.
- **C8 (IMPORTANTE, resuelto) — `score_ticket` anula su propio componente de mayor peso.** Construye la cohorte con `build_cohorts(records_del_ticket)`; una cohorte de un solo ticket casi siempre tiene `n < 3`, así que `cost_position` (**peso 0,35**) da `None` para todas sus ejecuciones. Y la firma no tiene por dónde recibir la cohorte global. Resuelto en F2.5.
- **C9 (IMPORTANTE, resuelto) — `cost_model_hooks.install()` revienta en la primera llamada.** `global _installed; if _installed:` sobre un nombre **nunca inicializado** a nivel de módulo ⇒ `NameError`. Resuelto en F5.5.
- **C10 (MENOR, resuelto) — 7 anclajes con deriva de +10 a +22 líneas.** Todos los símbolos existen (no hay API alucinada), pero la mitad de atrás de `cost_analytics.py` está uniformemente +22 y `metrics.py` +13. Resuelto en §0.2 y con la regla de anclaje por símbolo.
- **C11 (MENOR, resuelto) — conteos de tests que no cierran.** F3.11/DoD dicen **38** casos donde la tabla lista **37**; F8.6 titula *"los 12 archivos"* y lista **13**. Además varios casos son `parametrize` (`test_load_falta_clave_obligatoria` sobre 8 claves, `test_cost_stats_flag_off` sobre 6 endpoints), así que *"N/N verdes"* es un criterio inalcanzable por construcción. Resuelto en §10.1.
- **C12 (MENOR, resuelto) — ancla de inserción por número de línea.** F6.1 dice *"sólo apéndice después de la línea 723"*: un número que deriva. Resuelto por ancla simbólica.
- **C13 (IMPORTANTE, resuelto) — 10 fases no entran en una corrida.** 8 módulos backend, 13 archivos de test (~246 casos), 6 endpoints y 8 componentes de frontend. Corte formal en §0.3.
- **C14 (BLOQUEANTE, resuelto) — «apéndice después de la línea 723» inserta código DENTRO de una función.** `metrics.py:723` es `**ca.heatmap(ca.load_records(f)),` — está **adentro** del `jsonify({...})` de `/cost-heatmap` (`:712-724`). Meter 6 endpoints ahí es `SyntaxError`. Es la instrucción más literal del plan y la más destructiva. Resuelto en F6.1 con **ancla simbólica** (el bloque nuevo va **antes** del comentario `# ── Plan 171 — Telemetría operativa`).
- **C15 (BLOQUEANTE, resuelto) — F7.2 manda CREAR un componente que ya existe y está montado en pantalla.** `frontend/src/components/costcenter/CostDistributionChart.tsx` (+ `.module.css`) **ya existen** (Plan 199) y `CostCenterPage` los consume contra `GET /api/metrics/cost-distribution`. "CREAR" con el contrato nuevo **pisa el componente vivo y rompe la pestaña Resumen** — exactamente lo que F7.9.6 promete que no pasa. Resuelto en F7.2.
- **C16 (BLOQUEANTE, resuelto) — la promoción del modelo es automática, silenciosa e irreversible.** `should_promote` promueve solo y `save_model` pisa el modelo anterior con `os.replace`: no queda a qué volver. Si un modelo pasa el gate pero es peor en la práctica, `calibration()` lo delata días después y **ya no hay rollback**. Es la única autonomía real del plan y estaba sin candado. Resuelto por la **[ADICIÓN ARQUITECTO] F4.5**.
- **C17 (IMPORTANTE, resuelto) — el 199 TAMBIÉN está implementado, y el inventario de §2.1 quedó corto.** No son 5 endpoints de costo: son **8** (`/cost-burn-stacked`, `/cost-heatmap`, `/cost-distribution` son del 199). No son 6 componentes: son **12**. `CostCenterPage.tsx` no tiene 101 líneas: tiene **175**. `cost_analytics.py` ya tiene `burn_with_comparison` (`:472`), `burn_stacked` (`:615`), `heatmap` (`:653`) y `distribution` (`:681`). Resuelto en §2.1, §4 y F6.
- **C18 (IMPORTANTE, resuelto) — `install()` es la forma equivocada de enganchar el hook.** `app.py` ya registra **5** post-hooks (`:908`, `:910`, `:913`, `:917`, `:925`) con el patrón canónico de la casa `<modulo>.register(ticket_status.register_post_hook)`. v1 decía *"si no hay ninguno registrado en `create_app`…"* — hay cinco. Resuelto en F5.5.
- **C19 (IMPORTANTE, resuelto) — F1 reinventa el histograma que ya existe.** `cost_analytics.distribution(records, bins)` (`:681`, Plan 199) ya hace clamp de bins, "el máximo cae en el último bin" y el caso `max == min`. Resuelto en F1.2 declarando cuál es la canónica y agregando el test que fija que coinciden.
- **C20 (IMPORTANTE, resuelto) — el plan instruye `git stash` tres veces.** §F8.2, §F8.7 y §10.3 lo proponen como "prueba de ajenidad". En este árbol hay **sesiones paralelas vivas** que comparten el índice: `git stash` puede tragarse trabajo ajeno sin commitear. Resuelto reemplazándolo por `git diff --name-only` / `git show HEAD:<archivo>`.
- **C21 (MENOR, corregido en la propia crítica) — una acusación del segundo juez NO se sostuvo.** Afirmó que `group="observabilidad"` *"no existe"* y que las 7 flags quedarían mal agrupadas. **Falso:** `grep -oE 'group="[a-z_]+"' services/harness_flags.py` devuelve **11 usos** de `group="observabilidad"`. Lo que **sí** es cierto y queda como hallazgo MENOR real: las flags **de costo** hermanas usan `group="observabilidad_notif"` (`:2082`, `:2095`, `:2108`), así que por consistencia de agrupación en la UI las del 242 deben usar ése. Se deja registrado porque un juez que se equivoca en una evidencia puede equivocarse en otra: **verificá siempre**.
- **C22 (MENOR, resuelto) — dos evidencias falsas y un tipo mal declarado.** (a) G1 dice *"aunque numpy 1.26.4 aparezca instalado en el venv"*: **no está instalado** (`backend\.venv\Scripts\python.exe -c "import numpy"` ⇒ `ModuleNotFoundError`) — la conclusión de prohibirlo se sostiene, la evidencia no. (b) F7.3 dice que `rawGet` *"puede no existir"*: **existe**, `frontend/src/api/client.ts:93` (Plan 238). (c) F0.4 anota `priority: str | None` pero `models.py:54` lo declara `Mapped[int | None]`.

### 0.2 Anclajes verificados (los que v1 citaba de memoria)

| Anclaje citado por v1 | Real | Veredicto |
|---|---|---|
| `_SUBSCRIPTION_RUNTIMES` `cost_analytics.py:31` | `:31` | ✓ |
| `extract_cost_row` `:77` · `_MAX_ROWS` `:134` · `raw_metadata` `:150` · `input_price_per_mtok` `:46` | idénticos | ✓ |
| `CostRow` `:34` · `ExecRecord` `:137` | `:35` · `:138` | ✓ (±1) |
| `load_records` `:167` | **`:177`** | ✗ +10 |
| `_billable` `:213` · `summarize` `:217` · `burn` `:314` · `_dim_key` `:365` · `breakdown` `:381` | **`:235` · `:239` · `:336` · `:387` · `:403`** | ✗ **+22 uniforme** |
| `_execution_costs` `metrics.py:52` · `_cost_center_enabled` `:565` · `_parse_filters` `:584` | idénticos | ✓ |
| `_filters_or_error` `:614` | **`:627`** | ✗ +13 |
| `_CURATED_DEFAULTS_ON` `test_harness_flags.py:467` | `:467` | ✓ |
| `_CATEGORY_KEYS` `harness_flags.py:120` | `:120` | ✓ |
| categoría `observabilidad_notif` `:269` · nota `:395-396` · comentario `:410` | **`:283` · `:433` · `:448`** | ✗ +14/+38 |
| `register_post_hook` `ticket_status.py:307` y su firma | `:307`, firma **exacta** | ✓ |
| `_run_post_hooks` `:281` | **`:325`** (llamado en `:279`) | ✗ |
| bloque del ratchet `run_harness_tests.sh:390-396` | `:390-396` | ✓ |
| los 6 archivos de no-regresión del 142/158 | los 6 existen | ✓ |
| `AgentExecution` `models.py:248` con `verdict`/`output`/`completed_at`/`completion_source` | `:255`/`:258`/`:265`/`:273` | ✓ |
| `group="observabilidad"` en `FlagSpec` | válido, usado 11× | ✓ |
| `agents.py:1388` `estimate_cost` · `:1405` la llamada · `:1396` `get_json` | **`:1430` · `:1441` · `:1434`** | ✗ +36/+42 |
| `harness_flags.py:397` `FLAG_REGISTRY` | **`:435`** | ✗ +38 |
| `harness_flags.py:1811-1824` flags del 158 | **`:2073-2090`** | ✗ **+262** |
| `config.py:618-620` patrón OFF · `:641-650` flags 158 | **`:632-634` · `:653-664`** | ✗ +12/+14 |
| `cost_analytics.py:182` la query · `:445/:447` `dataclasses.replace` | `:192` · **`:467/:469`** | ✗ +10/+22 |
| `metrics.py:674` `/cost-breakdown` · `:692` `/cost-reconciliation-audit` | **`:746` · `:764`** (`:691` es `/cost-burn-stacked`) | ✗ **+72** |
| `endpoints.ts:1471` `CostCenter` · `:1453` `costFiltersToQuery` | **`:1516` · `:1499`** | ✗ +45/+46 |
| `CostCenterPage.tsx:60-66` EmptyState | **`:92-95`** | ✗ +32 |
| `routes.ts:28` subtab · `:21` `TAB_PATHS` | `:26` · `:20` | ✓ |
| `CostBadge.tsx:18` · `:6` · `CostTable.tsx:125` | idénticos | ✓ |
| `costCenterTypes.ts:156` `isCostCenterEnabled` | `:156` | ✓ |
| `cost_estimator.py:101/:34/:43/:16/:81` | idénticos | ✓ |
| `harness/pricing.py:24` `DEFAULT_PRICES` | `:24` | ✓ |
| `runtime_paths.py:48` `data_dir` · `ado_feedback.py:10` · `ado_identity.py:32` | idénticos | ✓ |
| `requirements.txt` — 14 deps, sin numpy/sklearn | idéntico | ✓ |
| `Ticket.priority` es `str` (anotación de F0.4) | **`Mapped[int \| None]`, `models.py:54`** | ✗ **C22** |
| **`ExecRecord` NO tiene `completed_at`** (premisa de F0.4) | **lo tiene, `:153`** | ✗ **C2** |
| **Plan 171 NO implementado** (premisa de §4) | **implementado** (`run_signals`/`ops_telemetry`/`run_trace` + 3 flags) | ✗ **C1** |
| **Plan 199 NO implementado** (premisa de §4) | **implementado parcial** (`burn_stacked`/`heatmap`/`distribution` + 3 endpoints + 3 componentes) | ✗ **C1/C17** |
| **«los 5 endpoints del 142»** | **8 endpoints de costo** | ✗ **C17** |
| **`CostCenterPage.tsx` 101 líneas · 6 componentes** | **175 líneas · 12 componentes** | ✗ **C17** |
| **`metrics.py:723` es el final del bloque de costo** | **está DENTRO de `cost_heatmap()`** | ✗ **C14** |
| **`CostDistributionChart.tsx` hay que CREARLO** | **ya existe y está montado** | ✗ **C15** |
| **«si no hay ningún post-hook en `create_app`»** | **hay 5** (`app.py:908-925`) | ✗ **C18** |
| **«`rawGet` puede no existir»** | **existe**, `client.ts:93` | ✗ **C22** |
| **«numpy 1.26.4 instalado en el venv»** | **NO instalado** (`ModuleNotFoundError`) | ✗ **C22** |
| **«`group="observabilidad"` no existe»** (acusación del 2º juez) | **sí existe, 11 usos** | ✗ **la acusación, C21** |
| **el máximo en `docs/` es 241** | **243** | ✗ |

**Regla de anclaje para la implementación (nueva en v2):** todo anclaje `archivo:línea` de este documento es **orientativo**. La verdad es el **símbolo**. Antes de editar, localizalo con `grep -n "<simbolo>" <archivo>` y usá la línea que devuelva. Un número que no coincide **no** es permiso para inventar: es la señal de que el archivo se movió.

### 0.3 Corte formal de alcance (C13)

| | Fases | Por qué el corte cae acá |
|---|---|---|
| **242 (este plan)** | **F0, F1, F2, F6-parcial** (`/cost-stats`, `/cost-scores`), **F7-parcial** (sub-tabs Estadísticas y Scoring), **F8-parcial** (2 flags: `STACKY_COST_STATS_ENABLED`, `STACKY_COST_SCORING_ENABLED`) | Es la mitad **estrictamente read-only**: no escribe ni un archivo, no registra ningún hook, no toca `app.py`. Entrega valor completo por sí sola (percentiles, outliers, cache, rework, scoring explicable) y es reversible borrando nada. |
| **245 (plan siguiente)** | **F3, F4, F5, F6-resto, F7-resto, F9** | Todo lo que **escribe en disco** (`cost_model.json`, el ledger), engancha el post-hook y entrena. Depende de F1/F2 ya verdes. **245, no 244:** el 244 ya está reservado por el corte del Plan 243. |

**Regla:** no se arranca el 245 hasta que el DoD del 242 esté verde. Un modelo predictivo montado sobre un motor estadístico sin probar es exactamente el falso verde que este plan dice combatir.

---

## 1. Objetivo

Convertir el Centro de Costos de un **sumador** en un **instrumento de medición y de predicción**: (a) estadística profunda sobre la telemetría de costo ya persistida (percentiles, dispersión, outliers, eficiencia de cache, rework, duración), (b) un **scoring determinista y explicable** de eficiencia económica por ejecución y por ticket, y (c) un **modelo predictivo propio, escrito en Python puro de stdlib**, que aprende del histórico de tickets y ejecuciones y responde —**antes** de lanzar el agente— cuántos USD va a costar resolver esa tarea, con intervalo P10/P50/P90, con nivel de confianza honesto y con **backtesting temporal que puede rechazar al propio modelo**.

Hoy el Centro de Costos responde *"gastaste X"*. Después del 242 responde *"gastaste X, este run costó el p95 de su cohorte por estas 3 razones, y el próximo ticket de este tipo te va a costar entre 0,18 y 0,74 USD (mediana 0,34) con confianza media sobre 148 muestras — y mi último backtest dice que le pego con un error medio de 0,09 USD"*.

### 1.1 KPI / impacto esperado (medibles, binarios)

| # | KPI | Meta numérica | Cómo se mide (comando) |
|---|-----|----------|------------------------|
| **KPI-1** | **Profundidad estadística**: el payload de `/api/metrics/cost-stats` expone p50/p75/p90/p95/p99, media, mediana, desvío, IQR, CV, MAD, min/max, histograma y outliers para **al menos 6 métricas** (`cost_usd`, `tokens_in`, `tokens_out`, `cache_read_tokens`, `duration_s`, `tokens_total`) y **al menos 6 dimensiones** (`runtime`, `model`, `agent_type`, `project`, `work_item_type`, `priority`). | 6 métricas × 6 dimensiones | `.venv/Scripts/python.exe -m pytest tests/test_plan242_cost_stats.py -q` — caso `test_describe_expone_las_13_claves` + `test_by_dimension_cubre_las_6_dimensiones` |
| **KPI-2** | **Scoring explicable**: toda ejecución con datos suficientes recibe `score` 0–100, `grade` A–E y **≥1 razón en español con el número que la justifica**; ninguna razón es genérica. | 100 % de los runs puntuados traen `reasons` no vacío | `.venv/Scripts/python.exe -m pytest tests/test_plan242_cost_scoring.py -q` — caso `test_toda_puntuacion_trae_razones_con_numeros` |
| **KPI-3** | **Determinismo**: mismo input ⇒ mismo output byte a byte, 50 corridas seguidas. | 50/50 idénticas | `test_plan242_cost_scoring.py::test_scoring_es_determinista_50_corridas` |
| **KPI-4** | **Modelo sin dependencias**: cero `import numpy`, cero `import sklearn`, cero `import pandas`, cero `import scipy` en los módulos nuevos. | 0 ocurrencias (verificado por AST, no por regex) | `.venv/Scripts/python.exe -m pytest tests/test_plan242_no_new_deps.py -q` |
| **KPI-5** | **Predicción útil**: sobre el split temporal de test, el MAE del modelo es **estrictamente ≥5 % mejor** que el baseline "mediana global"; si no lo es, el modelo NO se promueve y el sistema sigue con el fallback. | gate binario | `.venv/Scripts/python.exe -m pytest tests/test_plan242_cost_model_eval.py -q` — casos `test_promueve_cuando_gana` y `test_NO_promueve_cuando_pierde` |
| **KPI-6** | **Honestidad del intervalo**: la cobertura empírica del intervalo P10–P90 en el set de test cae en `[0.60, 0.95]`; fuera de ese rango el modelo queda `candidate`. | gate binario | `test_plan242_cost_model_eval.py::test_cobertura_fuera_de_rango_bloquea_promocion` |
| **KPI-7** | **`[v2]` (C6) Entrenamiento barato, medido END-TO-END.** v1 cronometraba **sólo `fit_ridge`** sobre filas sintéticas y de ahí concluía "entrenamiento barato" — mientras F6.4 afirmaba que *"KPI-7 garantiza < 2 s"* para `train()` **completo**, que además hace `collect_training_rows` → `load_records` (query de hasta 20.000 filas con la columna `output` TEXT). Medir la parte barata y declarar barato el todo **es exactamente el falso verde que R6 dice combatir**. Ahora son **dos** mediciones separadas: (a) `cost_model.train()` completo contra una DB de test con 20.000 `AgentExecution` reales ⇒ **< 5,0 s**; (b) `fit_ridge` sobre 20.000 filas sintéticas ⇒ **< 2,0 s**. Ninguna abre red ni invoca LLM. | (a) < 5,0 s · (b) < 2,0 s | `.venv/Scripts/python.exe -m pytest tests/test_plan242_cost_model_perf.py -q` — casos `test_train_end_to_end_20000_filas_en_menos_de_5s` **y** `test_fit_ridge_20000_filas_en_menos_de_2s` |
| **KPI-8** | **Cierre del lazo**: cada predicción mostrada queda registrada y, al terminar la ejecución, se cierra con el costo real; `/api/metrics/cost-calibration` reporta MAE/MAPE/cobertura reales del estimador. | ≥1 par abierto+cerrado por ejecución con forecast | `.venv/Scripts/python.exe -m pytest tests/test_plan242_forecast_ledger.py -q` — caso `test_par_abierto_cerrado_produce_calibracion` |
| **KPI-9** | **Cero regresión del 142/158**: los 6 archivos de test de costo existentes siguen verdes **sin editarlos**. | 6/6 verdes | ver §5.F0 "Aceptación" |
| **KPI-10** | **Paridad de runtimes**: `codex_cli`, `claude_code_cli` y `github_copilot` producen los tres un payload completo; Copilot aparece etiquetado `nominal` / *"no facturable (suscripción plana)"* y **nunca** entra en agregados facturables ni contamina el entrenamiento. | 3/3 | `.venv/Scripts/python.exe -m pytest tests/test_plan242_runtime_parity.py -q` |
| **KPI-11** | **Trabajo del operador: cero.** Ninguna fase pide configurar nada para obtener el valor; todas las flags nuevas nacen ON y son editables desde la UI del Arnés. | 0 pasos manuales | inspección del §5 (línea "Trabajo del operador" en cada fase) |

---

## 2. Por qué ahora / gap que cierra

### 2.1 Lo que YA existe (evidencia real, con `archivo:línea`)

- **Extractor canónico de costo (Plan 142 F0).** `backend/services/cost_analytics.py:77` `extract_cost_row(md)` reconcilia las 3 fuentes (`harness_telemetry` / `claude_telemetry` legacy / `cost_usd` top-level) en una `CostRow` (`cost_analytics.py:34`) con `cost_kind ∈ reported|estimated|nominal|unknown`. `_SUBSCRIPTION_RUNTIMES` (`:31`) marca `github_copilot` como **siempre nominal**, y `_billable()` (`:213`) excluye `nominal`/`unknown` de lo facturable.
- **Motor de agregación (Plan 142 F1).** `load_records(f)` (`:167`) hace **UNA** query con `outerjoin(Ticket)` y cap `_MAX_ROWS = 20000` (`:134`); `summarize` (`:217`), `burn` (`:314`) y `breakdown` (`:381`) son funciones **puras** sobre `list[ExecRecord]` (`:137`).
- **API read-only (Plan 142 F6).** `backend/api/metrics.py:565` `_cost_center_enabled()`, `:569` `/cost-center/health`, `:622` `/cost-summary`, `:655` `/cost-burn`, `:674` `/cost-breakdown`, `:692` `/cost-reconciliation-audit`. El parser de filtros vive en `:584` `_parse_filters(args)` y su envoltorio 400-safe en `:614` `_filters_or_error(args)`.
- **Legacy intocable.** `metrics.py:52` `_execution_costs`, `:77` `/ticket-costs`, `:130` `/project-costs`. El Plan 142 los dejó **intactos a propósito** (R3) y sólo cuantificó su error vía `/cost-reconciliation-audit`. **El Plan 242 tampoco los toca.**
- **Frontend delgado.** `frontend/src/pages/CostCenterPage.tsx` (101 líneas) + 6 componentes en `frontend/src/components/costcenter/` (`CostKpiCards`, `CostBurnChart`, `CostBreakdownBars`, `CostTable`, `CostFiltersBar`, `CostBadge`), tipos en `frontend/src/lib/costCenterTypes.ts`, lógica pura en `frontend/src/lib/costCenter.logic.ts`, cliente en `frontend/src/api/endpoints.ts:1471` (objeto `CostCenter`, helper `costFiltersToQuery` en `:1453`).
- **Estimación pre-run heurística (FA-33).** `backend/services/cost_estimator.py:101` `estimate(agent_type, blocks, model)`; expuesta por `backend/api/agents.py:1388` `def estimate_cost()` (ruta `POST /api/agents/estimate`), que la llama en `agents.py:1405`.
- **`[v2]` **Plan 171, YA IMPLEMENTADO (C1).** Esto v1 lo daba por pendiente y es la corrección más importante de la crítica. Existe y está vivo:
  - **`backend/services/run_signals.py`** — módulo **puro** con `RunPoint` (`:50`), `from_exec_record(r)` (`:64`, duck-typing sobre `ExecRecord`), **`percentile_nearest_rank(values, q)` (`:102`)**, `summarize_groups` (`:127`), `daily_series` (`:193`), `detect_regressions` (`:276`), `evaluate_thresholds` (`:317`).
  - **`backend/services/ops_telemetry.py`** (capa de I/O, `from services import run_signals as rs` en `:19`) y **`backend/services/run_trace.py`** (`:14`).
  - **`backend/tests/test_run_signals.py`**.
  - **3 flags registradas** en la **misma categoría** que quiere usar el 242: `STACKY_OPS_TELEMETRY_ENABLED`, `STACKY_OPS_BASELINE_ENABLED`, `STACKY_OPS_TRACE_ENABLED` (`harness_flags.py:300-302`, specs en `:2037`, `:2049`, `:2060`).
  - Y dejó su huella dentro del archivo que el 242 edita: `ExecRecord.completed_at` (`cost_analytics.py:153`) con el comentario *"Plan 171 (aditivo, default None): fin de la corrida, para duraciones/percentiles en services/run_signals.py"*, ya pasado en `load_records:231`.

  **Consecuencia para este plan:** el 242 **no** es el primero en calcular duraciones ni percentiles sobre `ExecRecord`. Tiene que **reconciliarse** con `run_signals`, no ignorarlo (F0.3, F1.3).

### 2.2 El gap exacto que este plan cierra

1. **El 142 suma, no describe.** `summarize` (`cost_analytics.py:217`) devuelve totales y **tres promedios** (`avg_cost_per_run_usd`, `cost_per_completed_task_usd`, `tokens_out_in_ratio`). No hay **una sola** medida de dispersión en todo el módulo: ni percentil, ni desvío, ni outlier. Un promedio sobre una distribución de costos de cola larga (que es exactamente la forma de los costos de agentes: muchos runs baratos, pocos carísimos) **miente sistemáticamente**. El operador no puede distinguir "gasté 40 USD en 400 runs parejos" de "gasté 40 USD donde 3 runs se comieron 32".
2. **No hay noción de "caro para lo que es".** Un run de 0,80 USD puede ser excelente (épica compleja resuelta de una) o pésimo (typo, tercer reintento). Hoy los dos aparecen idénticos en `top_runs` (`cost_analytics.py:250-259`). Falta la **cohorte** como referencia.
3. **La estimación pre-run está congelada en constantes.** `cost_estimator.py:34` `OUTPUT_RATIO` es un `dict[str, float]` **hardcodeado**, igual que `LATENCY_BASE_MS` (`:43`) y `PRICING` (`:16`). Nunca aprendió nada de las miles de ejecuciones que el sistema ya tiene en `AgentExecution`. Ése es el gap que el modelo del 242 cierra — **sin borrar el módulo**: `cost_estimator` pasa a ser el **último escalón** del fallback jerárquico (§5.F3.5).
4. **No hay lazo de aprendizaje.** Nadie compara lo estimado contra lo real. Sin ledger forecast-vs-real no hay forma de saber si el estimador sirve, y por lo tanto no hay forma honesta de mostrarlo (KPI-8).
5. **El 158 arregló la telemetría de `claude_code_cli`** (`config.py:641-650`, flags `STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED` y `STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED`), lo que significa que **recién ahora** hay datos de calidad comparable en los dos runtimes facturables. El sustrato para aprender existe **desde el 158 y no antes**: por eso este plan es *ahora* y no antes.

---

## 3. Principios y guardarraíles (restricciones DURAS, no negociables)

**G1 · Cero dependencias nuevas.** `backend/requirements.txt` es exactamente: Flask 3.0.3, Flask-Cors 4.0.1, SQLAlchemy 2.0.36, alembic 1.13.3, pydantic 2.9.2, python-dotenv 1.0.1, python-json-logger 2.0.7, requests 2.32.3, truststore 0.10.4, PyYAML 6.0.3, keyring 25.6.0, pytest 8.3.3, pytest-flask 1.3.0, pywin32 307. **NO hay scikit-learn.** **`[v2]` (C22) — evidencia corregida:** v1 decía *"aunque `numpy 1.26.4` aparezca instalado en el venv"*. **numpy NO está instalado**: `backend\.venv\Scripts\python.exe -c "import numpy"` ⇒ `ModuleNotFoundError`. Tampoco está en `requirements.txt`. O sea: no está **ni en desarrollo ni en un deploy limpio** — la prohibición se sostiene con más fuerza que la que le daba v1, pero con la evidencia correcta. Por lo tanto **el modelo predictivo debe ser Python puro de stdlib** (`math`, `statistics`, `json`, `uuid`, `datetime`, `dataclasses`, `logging`, `os`, `time`). Está **PROHIBIDO** escribir `import numpy`, `import sklearn`, `import scipy`, `import pandas` (o cualquier variante `from … import`) en los módulos de este plan, y hay un test que lo verifica **por AST** (§5.F8.3).

**G2 · Read-only sobre la telemetría.** Ninguna fase modifica `AgentExecution.metadata_json`, ni `Ticket`, ni los endpoints legacy `_execution_costs` / `/ticket-costs` / `/project-costs`. Las únicas escrituras del plan son **dos archivos** en el data dir del runtime (`runtime_paths.data_dir()`, definido en `backend/runtime_paths.py:48`): el modelo entrenado y el ledger de forecast. Borrar esos dos archivos revierte el plan al estado del 142 sin perder nada.

**G3 · Sin LLM, sin red, sin shell-out.** Ni el motor estadístico, ni el scoring, ni el modelo, ni el entrenamiento invocan un LLM, abren un socket o ejecutan un proceso. Todo es aritmética sobre filas ya persistidas. Hay test que lo verifica con monkeypatch (§5.F6).

**G4 · Sin dato ⇒ `None`, JAMÁS 0.0 inventado.** Es la regla de oro que ya rige `cost_analytics.py` (docstring `:15`) y se extiende a todo lo nuevo. Un percentil sobre lista vacía es `None`, no 0. Un score sin componentes computables es `None` con `grade="N/D"`, no 0 con grade E.

**G5 · Determinismo y reproducibilidad.** Sin `random`, sin `set` iterado sin ordenar, sin dependencia del orden de `dict` de entrada, sin `datetime.now()` dentro de funciones puras (la fecha entra por parámetro). Mismo input ⇒ mismo output (KPI-3).

**G6 · Estimación ≠ factura.** Todo número producido por el modelo se rotula en la UI y en el payload como **estimación** con su `source`, su `confidence` y su `n_samples`. Nunca se mezcla con `billable_usd`. El campo `cost_kind` de una predicción es **siempre** `"forecast"`, un valor nuevo que **no** entra en `_billable()`.

**G7 · Copilot es suscripción plana.** `github_copilot` sigue produciendo `cost_kind = "nominal"` (`cost_analytics.py:106-108`) y **nunca** es facturable. Su forecast se muestra etiquetado *"costo nominal — no facturable (suscripción plana)"* y **sus filas se excluyen del entrenamiento** (§5.F3.3) para no envenenar el modelo con números que nadie paga.

**G8 · Frontend sin DOM-testing.** El frontend **no** tiene `@testing-library/react` ni `jsdom` configurado para render. Los tests de front de este plan son **vitest sobre lógica pura** en archivos `.logic.ts` / `.test.ts`. **Prohibido** escribir tests que rendericen componentes. El smoke visual es **manual** y está declarado como tal.

**G9 · Ratchet del arnés.** Todo `backend/tests/test_*.py` **nuevo** debe registrarse en el bloque `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` (los tests de costo del 142/158 están en las líneas 390–396) **y** en su gemelo `backend/scripts/run_harness_tests.ps1`, o `tests/test_harness_ratchet_meta.py` queda **ROJO**. Es criterio binario de cada fase.

**G10 · Flags: la instancia, no el módulo.** Leer `getattr(config, "FLAG")` sobre el **módulo** devuelve el default y **mata el branch OFF**. La instancia correcta es `config.config`. En `api/metrics.py` el patrón ya establecido es `getattr(_cfg, "STACKY_...", False)` (`metrics.py:566`), donde `_cfg` es la instancia importada en el módulo — **reusar exactamente ese patrón**.

**G11 · Flags: `default=` explícito ⇒ curada.** Una `FlagSpec` (definida en `backend/services/harness_flags.py`, campos en el bloque `class FlagSpec`) que declara `default=` queda marcada como **curada** y **exige** estar en `_CURATED_DEFAULTS_ON`, que vive en **`backend/tests/test_harness_flags.py:467`** (NO en `harness_flags.py` — ahí sólo hay comentarios que la mencionan, p. ej. `harness_flags.py:410`). Si falta, rompe `test_default_known_only_for_curated`. Flag ON ⇒ `default=True` **+** alta en `_CURATED_DEFAULTS_ON`. Flag OFF por excepción dura ⇒ **NO** declarar `default=` y dejar que el type-zero + `os.getenv(..., "false")` de `config.py` den el OFF (patrón real en `config.py:618-620`).

**G12 · Flags: categoría obligatoria.** Toda flag nueva debe agregarse a `_CATEGORY_KEYS` (`harness_flags.py:120`) o el test `test_every_registry_flag_is_categorized` rompe a propósito (nota explícita en `harness_flags.py:395-396`). Las flags de costo del 142/158 viven en la categoría `"observabilidad_notif"` (`harness_flags.py:269`, claves en `:279-282`). **Las del 242 van ahí mismo.**

**G13 · Flags numéricas: bounds declarativos.** `FlagSpec` tiene `min_value` / `max_value` (Plan 83). Toda flag `type="int"` de este plan **declara ambos**.

**G14 · Tests por archivo, nunca la suite completa.** `importlib.reload(config)` contamina la corrida. El intérprete correcto es **`backend/.venv`** (Python **3.13.5**). ⚠️ `backend/venv` existe y es **Python 3.11.9** — **es la trampa, no lo uses**. Forma exacta del comando, desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_<archivo>.py -q
```

**G15 · Human-in-the-loop.** El modelo **informa**, nunca decide. No cancela runs, no elige modelo, no bloquea ejecuciones, no cambia configuración. Es un número al lado de un botón que el operador aprieta o no.

**G16 · No degradar.** Con **todas** las flags nuevas en OFF, el comportamiento del Centro de Costos es **byte-idéntico** al del Plan 142 + 158. Hay test que lo verifica (§5.F8.4).

---

## 4. Frontera con los Planes 171 y 199 (qué NO hace el 242)

**`[v2]` CORRECCIÓN DE PREMISA (C1 · C17).** v1 decía aquí que *"los planes 171 y 199 están CRITICADOS pero NO implementados"*. Es **falso para los dos**:

- **171 — IMPLEMENTADO.** `run_signals.py`, `ops_telemetry.py`, `run_trace.py`, `tests/test_run_signals.py` y 3 flags registradas (evidencia en §2.1).
- **199 — IMPLEMENTADO parcial (backend).** Sus agregadores ya viven en `cost_analytics.py`: `burn_stacked` (`:615`), `heatmap` (`:653`), `distribution` (`:681`); sus 3 endpoints en `metrics.py` (`/cost-burn-stacked` `:691`, `/cost-heatmap` `:712`, `/cost-distribution` `:727`); y sus 3 componentes en el frontend (`CostStackedBurnChart`, `CostHeatmap`, `CostDistributionChart`). Además amplió `CostFilters` con `runtimes`/`models`/`min_cost_usd`/`max_cost_usd`.

Por lo tanto esta sección deja de ser una declaración de intenciones a futuro y pasa a ser un **contrato de convivencia con código que ya está en el árbol**. Todo lo que sigue se lee así: *"¿quién es dueño de qué?"*, no *"¿quién lo hará?"*.

| Tema | 242 (este plan) | 199 | 171 |
|---|---|---|---|
| **Origen de los datos** | **Sólo** lo que ya está en la DB (`AgentExecution.metadata_json` + columnas). **NO lee transcripts, `.jsonl` de sesión ni directorios de runtime en disco.** | Cosecha desde disco por runtime y **escribe** en DB | consume lo que haya |
| **Dominio** | **Sólo costo/tokens/eficiencia económica**: USD, tokens, cache, duración *como insumo de costo*, rework *como insumo de costo* | ídem costo, pero como *ingesta* | **Salud operativa general**: latencia, tasa de error, colas, baselines de operación |
| **Baselines** | Cohortes **económicas** (percentil de costo dentro de `agent_type`+familia de modelo) y calibración del estimador | — | **Baselines de salud operativa solo-aviso** (el 242 **NO** define ninguno) |
| **Alertas** | **Ninguna.** El 242 no notifica, no alerta, no dispara nada | — | dueño de las alertas solo-aviso |
| **Escrituras** | 2 archivos JSON/JSONL en `data_dir()` | filas/columnas de telemetría en DB | según su plan |

**Puntos de integración declarados (contratos que el 242 deja listos, sin implementarlos por el otro):**

- **Si el 199 se implementa después:** al aumentar la cantidad y calidad de filas con `harness_telemetry`, el 242 **no necesita ningún cambio** — `load_records` ya las levanta. El único efecto es que `n_samples` sube y el modelo mejora solo en el próximo autotrain. El 199 **no debe** escribir en `cost_model.json` ni en `cost_forecast_ledger.jsonl`.
- **`[v2]` El 171 YA ESTÁ (C1/C3) — reglas de convivencia, no de futuro:**
  1. **`run_signals.py` no se toca.** Ni una línea. Es de otro plan, tiene sus tests y sus flags.
  2. **Ninguna de las 7 flags del 242 puede llamarse `STACKY_OPS_*`** (ese prefijo es del 171, `harness_flags.py:300-302`). Las del 242 son `STACKY_COST_*`. Ambas conviven en la categoría `observabilidad_notif`, así que al agregar las del 242 hay que **insertar después** de las del 171, sin reordenar.
  3. **Percentiles (C3):** hay dos definiciones legítimas y **distintas** conviviendo, y eso se declara en vez de ocultarse. `run_signals.percentile_nearest_rank` es **nearest-rank** (salud operativa); `cost_stats.percentile` es **interpolación lineal** (distribuciones de costo). Un mismo dataset da números distintos. Ver F1.3 para la regla de cuál usa cada uno y el test que fija la diferencia.
  4. **Duraciones (C3):** `run_signals.from_exec_record` calcula `duration_seconds` **sólo si `status == "completed"`**; `cost_signals.duration_seconds` la calcula para **cualquier** estado terminal. Son semánticas distintas a propósito y **tienen nombres distintos** para que nadie las confunda. Ver F0.3.
  5. Si el 171 quiere un baseline **de costo**, lo pide a `/api/metrics/cost-stats`; no lo reimplementa.
- **Colisión de archivos a vigilar:** `backend/api/metrics.py` (los tres planes agregan endpoints ahí) y `backend/services/harness_flags.py` (los tres agregan flags). Al mergear, la resolución es **unión aditiva**, y después de CADA merge hay que correr `.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q` y `tests\test_harness_ratchet_meta.py` para atrapar duplicados silenciosos.

---

## 5. Fases

Orden de dependencia estricto: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9**. F9 es opcional y no bloquea el DoD.

### F0 — Señales enriquecidas (aditivo, read-only, 100 % retrocompatible)

**Objetivo (1 frase):** que cada `ExecRecord` traiga, además del costo, las señales que hacen falta para medir eficiencia (cache de escritura, duración, turnos, herramientas, reintentos, veredicto, esfuerzo, tamaño de salida) — sin cambiar una sola línea del contrato del Plan 142.
**Valor:** sin estas señales, F1/F2/F3 no tienen de qué agarrarse. Es el cimiento.

#### F0.1 Decisión de diseño (y su justificación)

Se evaluaron dos caminos:

- **(A)** Extender `extract_cost_row(md)` (`cost_analytics.py:77`) con los campos nuevos.
- **(B)** Un módulo nuevo puro `cost_signals.py` + campos **con default** en `ExecRecord`.

**Se elige (B).** Razones concretas y verificables:
1. `extract_cost_row` recibe **sólo** `md: dict | None`. `duration_s` necesita `completed_at`, y `verdict` / `completion_source` son **columnas** de `AgentExecution`, no metadata. (A) obligaría a cambiar la firma de una función que ya tiene tests propios (`tests/test_cost_analytics_extract.py`), violando "los tests del 142 siguen verdes sin tocarlos".
2. `ExecRecord` **ya tiene el precedente exacto**: el Plan 142 F8 le agregó `raw_metadata: dict | None = None` (`cost_analytics.py:150`) con default, justamente para ser aditivo. F0 repite ese patrón.
3. `CostRow` no se serializa con `dataclasses.asdict` en ningún lado (`cost_analytics.py` sólo usa `dataclasses.replace`, líneas `:445` y `:447`), pero igual **no se toca**: mantenerlo congelado hace que el diff sea trivialmente auditable.

**Regla anti-ciclo:** `cost_signals.py` **NO importa** `cost_analytics`. La dirección es `cost_analytics → cost_signals`, nunca al revés.

**`[v2]` Reconciliación obligatoria con `run_signals.py` del Plan 171 (C1/C3).** v1 escribió esta fase creyendo que el 171 no existía. Existe, y **ya proyecta `ExecRecord` a señales**: `run_signals.from_exec_record(r) -> RunPoint` (`run_signals.py:64`). Antes de escribir una línea de `cost_signals.py`, correr:

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
grep -n "def from_exec_record" -A 40 services/run_signals.py
```

Reglas de convivencia, **no negociables**:

1. **`run_signals.py` no se toca.** Tiene sus tests (`tests/test_run_signals.py`) y sus flags (`STACKY_OPS_*`). Cambiarlo es alcance del 171, no de éste.
2. **`cost_signals.py` NO reemplaza a `run_signals.py`.** Son dominios distintos: `RunPoint` es **salud operativa** (latencia, tasa de error, `billable_usd` colapsado a `0.0` cuando no es facturable); `SignalRow` es **insumo de costo** (cache de escritura, turnos, herramientas, reintentos, esfuerzo) y respeta G4 (`None`, nunca 0). **`run_signals` no tiene ninguno de los 5 campos de `SignalRow`**, así que no hay duplicación de datos: hay duplicación **sólo** en `duration`.
3. **La duración es el punto de choque, y se resuelve nombrándolo:**

| | `run_signals.from_exec_record` (171) | `cost_signals.duration_seconds` (242) |
|---|---|---|
| Cuándo devuelve un número | **sólo si `status == "completed"`** | cualquier par de timestamps con delta ≥ 0 |
| Por qué | los errores fallan rápido y falsearían la latencia "sana" hacia abajo | un run que explotó **igual costó dinero**: su duración es insumo de costo |
| Nombre | `RunPoint.duration_seconds` | `ExecRecord.duration_s` |

   Los nombres son **deliberadamente distintos** (`duration_seconds` vs `duration_s`) para que nadie los tome por intercambiables. Está **PROHIBIDO** hacer que uno llame al otro: darían números distintos para el mismo run y eso es correcto.

#### F0.2 Archivos

| Acción | Ruta exacta |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/cost_signals.py` |
| **EDITAR** | `Stacky Agents/backend/services/cost_analytics.py` (sólo `ExecRecord` y el bloque de construcción dentro de `load_records`) |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_signals.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` (bloque `HARNESS_TEST_FILES`) |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.ps1` (bloque gemelo) |

#### F0.3 `backend/services/cost_signals.py` — contenido exacto

```python
"""Plan 242 F0 — Señales enriquecidas, PURAS (sin DB, sin red, sin LLM).

Regla de oro heredada del Plan 142: dato ausente -> None, JAMAS 0 inventado.
Este modulo NO importa cost_analytics (evita ciclo de imports).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Vocabulario cerrado de esfuerzo declarado por los runtimes.
_EFFORT_VALUES: frozenset[str] = frozenset({"low", "medium", "high", "max"})


@dataclass
class SignalRow:
    cache_creation_tokens: int | None = None  # tokens escritos al cache (costo extra)
    turns: int | None = None                  # num_turns / turns reportado por el runtime
    tool_calls: int | None = None             # cantidad de invocaciones de herramientas
    retries: int | None = None                # reintentos de autocorreccion del contrato
    effort: str | None = None                 # low|medium|high|max o None


def _first_int(*vals) -> int | None:
    """Primer valor convertible a int; None si ninguno lo es. (Copia local
    deliberada de cost_analytics._first_int: mantiene cost_signals sin imports.)"""
    for v in vals:
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def extract_signal_row(md: dict | None) -> SignalRow:
    """Extrae de metadata_dict las senales derivables SOLO de metadata."""
    md = md or {}
    ht = md.get("harness_telemetry") if isinstance(md.get("harness_telemetry"), dict) else {}
    raw = ht.get("raw") if isinstance(ht.get("raw"), dict) else {}
    ct = md.get("claude_telemetry") if isinstance(md.get("claude_telemetry"), dict) else {}
    ct_usage = ct.get("usage") if isinstance(ct.get("usage"), dict) else {}

    cache_creation = _first_int(
        ht.get("cache_creation_tokens"),
        ct_usage.get("cache_creation_input_tokens"),
        raw.get("cache_creation_input_tokens"),
    )
    turns = _first_int(ht.get("num_turns"), ht.get("turns"), raw.get("num_turns"), md.get("turns"))
    tool_calls = _first_int(ht.get("tool_calls"), raw.get("tool_calls"), md.get("tool_calls"))
    retries = _first_int(md.get("autocorrect_retries"), md.get("retries"), ht.get("retries"))

    effort_raw = md.get("effort") or md.get("reasoning_effort") or raw.get("effort")
    effort = None
    if isinstance(effort_raw, str) and effort_raw.strip().lower() in _EFFORT_VALUES:
        effort = effort_raw.strip().lower()

    return SignalRow(cache_creation_tokens=cache_creation, turns=turns,
                     tool_calls=tool_calls, retries=retries, effort=effort)


def duration_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    """Duracion en segundos. None si falta un extremo o si el delta es negativo
    (reloj corrido / fila corrupta): NUNCA devolver un negativo ni un 0 inventado."""
    if started_at is None or completed_at is None:
        return None
    delta = (completed_at - started_at).total_seconds()
    if delta < 0:
        return None
    return round(delta, 3)


def output_chars(output: str | None) -> int | None:
    """Tamano de la salida en caracteres. None si no hay salida; 0 es un valor
    legitimo si el output es la cadena vacia (distinto de 'no hay dato')."""
    if output is None:
        return None
    return len(output)
```

**Casos borde enumerados (todos con test):**
1. `md = None` ⇒ `SignalRow()` con los 5 campos en `None`.
2. `md = {}` ⇒ ídem.
3. `harness_telemetry` presente pero **no** dict (p. ej. `"x"`) ⇒ se ignora, no crashea.
4. `cache_creation_tokens = "1234"` (string) ⇒ `1234` (int).
5. `cache_creation_tokens = "abc"` ⇒ `None` (no 0).
6. `effort = "HIGH"` ⇒ `"high"`. `effort = "turbo"` ⇒ `None` (vocabulario cerrado).
7. `duration_seconds(None, dt)` y `duration_seconds(dt, None)` ⇒ `None`.
8. `completed_at < started_at` ⇒ `None` (nunca negativo).
9. `output_chars(None)` ⇒ `None`; `output_chars("")` ⇒ `0`.

#### F0.4 Diff en `cost_analytics.py`

> **`[v2]` ⚠️ LEER ANTES DE APLICAR (C2).** El diff de v1 **no aplicaba y rompía el archivo**.
> `ExecRecord` **ya tiene** `completed_at` (`cost_analytics.py:153`, lo puso el **Plan 171**) y
> `load_records` **ya lo pasa** (`:231`). La línea que v1 usaba como ancla (`raw_metadata=md))`)
> **no existe**; la real es `raw_metadata=md, completed_at=ex.completed_at))`. Aplicar v1 literalmente
> producía un **campo duplicado** en el dataclass y un **keyword argument repetido** (`SyntaxError:
> keyword argument repeated`). El diff de abajo ya está corregido: **`completed_at` NO se agrega,
> porque ya está.**
>
> **Verificación obligatoria antes de tocar nada:**
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> grep -n "completed_at" services/cost_analytics.py
> ```
> Si aparece en el bloque `class ExecRecord` **y** en el `out.append(ExecRecord(`, el diff de abajo es
> el correcto. Si **no** apareciera (árbol distinto), entonces sí hay que agregarlo — pero **una sola vez**.

```diff
 from harness.pricing import _MTOK, _load_prices, estimate_cost
+from services.cost_signals import SignalRow, extract_signal_row, duration_seconds, output_chars
```

```diff
 @dataclass
 class ExecRecord:
     execution_id: int
     ticket_id: int | None
     ado_id: int | None
     project: str | None
     agent_type: str | None
     status: str | None
     started_at: datetime | None
     row: CostRow
     raw_metadata: dict | None = None
     completed_at: datetime | None = None   # ← YA EXISTE (Plan 171). NO agregarlo de nuevo.
+    # ── Plan 242 F0 — señales enriquecidas. TODAS con default: 100% aditivo.
+    # Ningún caller del Plan 142 las pasa, y todos los tests del 142 siguen verdes.
+    signals: SignalRow | None = None
+    duration_s: float | None = None
+    verdict: str | None = None
+    completion_source: str | None = None
+    output_chars: int | None = None
+    work_item_type: str | None = None      # de Ticket (ya cargado por el outerjoin)
+    priority: str | None = None            # de Ticket
```
**`[v2]`** Son **7** campos nuevos, no 8: `completed_at` ya lo puso el Plan 171.

```diff
             out.append(ExecRecord(
                 execution_id=ex.id, ticket_id=ex.ticket_id,
                 ado_id=getattr(tk, "ado_id", None) if tk else None,
                 project=(tk.stacky_project_name or tk.project) if tk else None,
                 agent_type=ex.agent_type, status=ex.status, started_at=ex.started_at, row=cr,
-                raw_metadata=md, completed_at=ex.completed_at))
+                raw_metadata=md, completed_at=ex.completed_at,
+                # Plan 242 F0 — sin query adicional: ex y tk ya están cargados.
+                signals=extract_signal_row(md),
+                duration_s=duration_seconds(ex.started_at, ex.completed_at),
+                verdict=ex.verdict,
+                completion_source=ex.completion_source,
+                output_chars=output_chars(ex.output),
+                work_item_type=getattr(tk, "work_item_type", None) if tk else None,
+                priority=getattr(tk, "priority", None) if tk else None))
```
**`[v2]`** La línea eliminada es `raw_metadata=md, completed_at=ex.completed_at))` — **con** `completed_at`. Ése es el texto real del archivo; el de v1 (`raw_metadata=md))`) no existe y el `Edit` habría fallado o, peor, un modelo menor habría "arreglado" el ancla duplicando el kwarg.

**Nota de costo de query:** no se agrega **ninguna** query. `session.query(AgentExecution, Ticket)` (`cost_analytics.py:182`) ya carga las entidades completas, así que `ex.completed_at`, `ex.verdict`, `ex.completion_source`, `ex.output`, `tk.work_item_type` y `tk.priority` **ya están en memoria**. Las columnas existen: `AgentExecution` en `backend/models.py:248` (incluye `verdict`, `output`, `completed_at`, `completion_source`) y `Ticket` en `backend/models.py:38` (incluye `work_item_type`, `priority`).

#### F0.5 Tests PRIMERO — `backend/tests/test_plan242_cost_signals.py`

| Caso | Qué verifica |
|---|---|
| `test_metadata_none_devuelve_todo_none` | `extract_signal_row(None)` ⇒ los 5 campos en `None`, no 0 |
| `test_metadata_vacia_devuelve_todo_none` | `extract_signal_row({})` ⇒ ídem |
| `test_harness_telemetry_no_dict_no_crashea` | `{"harness_telemetry": "x"}` ⇒ `SignalRow()` sin excepción |
| `test_cache_creation_desde_harness_telemetry` | lee `harness_telemetry.cache_creation_tokens` |
| `test_cache_creation_desde_claude_usage_legacy` | lee `claude_telemetry.usage.cache_creation_input_tokens` |
| `test_string_numerico_se_convierte_a_int` | `"1234"` ⇒ `1234` |
| `test_string_no_numerico_devuelve_none_no_cero` | `"abc"` ⇒ `None` |
| `test_effort_normaliza_mayusculas` | `"HIGH"` ⇒ `"high"` |
| `test_effort_fuera_de_vocabulario_es_none` | `"turbo"` ⇒ `None` |
| `test_turns_precedencia_num_turns_sobre_turns` | `num_turns` gana sobre `turns` |
| `test_duracion_none_si_falta_un_extremo` | ambos sentidos ⇒ `None` |
| `test_duracion_negativa_devuelve_none` | `completed_at < started_at` ⇒ `None` |
| `test_duracion_redondea_a_3_decimales` | 12,3456 s ⇒ `12.346` |
| `test_output_chars_none_vs_cadena_vacia` | `None`⇒`None`; `""`⇒`0` |
| `test_execrecord_se_construye_sin_los_campos_nuevos` | `ExecRecord(...)` con la firma del Plan 142 sigue funcionando y deja los **7** campos nuevos en `None` |
| `test_cost_signals_no_importa_cost_analytics` | AST del módulo: cero `Import`/`ImportFrom` que mencionen `cost_analytics` |
| **`[v2]`** `test_execrecord_no_declara_completed_at_dos_veces` | **C2**: `[f.name for f in dataclasses.fields(ExecRecord)].count("completed_at") == 1`. Es el test que atrapa el bug que traía el diff de v1 |
| **`[v2]`** `test_duracion_de_costo_difiere_de_la_operativa_en_runs_fallidos` | **C3**: para un run con `status="error"` y ambos timestamps, `cost_signals.duration_seconds(...)` devuelve un `float` y `run_signals.from_exec_record(...).duration_seconds` devuelve `None`. **Fija la divergencia a propósito**, para que nadie la "arregle" después creyendo que es un bug |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_signals.py -q
```

#### F0.6 Aceptación (BINARIA)

1. `.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_signals.py -q` ⇒ **0 failed / 0 errors**, con los **18** casos de F0.5 presentes. **`[v2]` (C11):** el criterio binario es *"0 failed"*, **no** un número exacto de tests: `parametrize` expande casos y cualquier conteo fijo queda mal el día que se parametriza uno.
2. **`[v2]` (C1/C3) — el 171 sigue verde sin tocarlo:**
```powershell
.venv\Scripts\python.exe -m pytest tests\test_run_signals.py -q
```
   y `git diff --stat services/run_signals.py` ⇒ **vacío**.
3. **Cero regresión (KPI-9)** — los 6 archivos del 142/158 verdes **sin editarlos**, uno por uno:
```powershell
.venv\Scripts\python.exe -m pytest tests\test_cost_analytics_extract.py -q
.venv\Scripts\python.exe -m pytest tests\test_cost_analytics_aggregate.py -q
.venv\Scripts\python.exe -m pytest tests\test_cost_center_api.py -q
.venv\Scripts\python.exe -m pytest tests\test_cost_reconciliation_audit.py -q
.venv\Scripts\python.exe -m pytest tests\test_cost_codeburn_import.py -q
.venv\Scripts\python.exe -m pytest tests\test_plan158_claude_cli_cost_parity.py -q
```
3. `git diff --stat` sobre esos 6 archivos de test ⇒ **0 líneas modificadas**.
4. Registro en el ratchet:
```powershell
grep -c "test_plan242_cost_signals.py" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1
```
⇒ **1 en cada uno**, y `.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q` verde.

**Flag que la protege:** ninguna. F0 es puramente aditivo con defaults `None`; con todas las flags del plan en OFF el comportamiento observable es idéntico al del 142 (los campos nuevos existen pero nadie los lee).
**Impacto por runtime:** `codex_cli` → llena `turns`/`tool_calls` cuando el harness los reporta, si no `None`. `claude_code_cli` → llena `cache_creation_tokens` desde `claude_telemetry.usage` (legacy) o desde `harness_telemetry` (post-158); si falta, `None`. `github_copilot` → normalmente sólo `duration_s` y `output_chars`; el resto `None`. **En los tres, la ausencia es `None`, nunca 0.**
**Trabajo del operador: ninguno.**

---

### F1 — Motor estadístico puro (`cost_stats.py`)

**Objetivo (1 frase):** un módulo de estadística descriptiva sin dependencias que convierta una lista de `ExecRecord` en distribuciones, histogramas y outliers, por métrica y por dimensión.
**Valor:** es lo que convierte "gastaste 40 USD" en "gastaste 40 USD, mediana 0,04, p95 0,61, y 3 runs outlier se comieron el 80 %".

#### F1.1 Archivos

| Acción | Ruta exacta |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/cost_stats.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_stats.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` |

#### F1.2 Contratos exactos

```python
"""Plan 242 F1 — Motor estadistico PURO. stdlib only (math, statistics)."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

_METRICS: tuple[str, ...] = (
    "cost_usd", "tokens_in", "tokens_out", "cache_read_tokens",
    "cache_creation_tokens", "duration_s", "tokens_total", "usd_per_ktok_out",
)
_DIMENSIONS: tuple[str, ...] = (
    "runtime", "model", "agent_type", "project", "work_item_type", "priority",
)
_PERCENTILES: tuple[int, ...] = (50, 75, 90, 95, 99)


@dataclass
class Distribution:
    n: int                      # cantidad de valores NO nulos
    n_missing: int              # cantidad de None descartados
    total: float | None         # suma; None si n == 0
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None
    stdev: float | None         # MUESTRAL (n-1); None si n < 2
    q1: float | None
    q3: float | None
    iqr: float | None           # q3 - q1; None si n < 2
    cv: float | None            # stdev / mean; None si n<2 o mean == 0
    mad: float | None           # mediana(|x - mediana|); None si n == 0
    p50: float | None
    p75: float | None
    p90: float | None
    p95: float | None
    p99: float | None


@dataclass
class HistBin:
    lo: float
    hi: float
    count: int


@dataclass
class OutlierReport:
    method: str                 # "tukey" | "mad"
    fence_low: float | None
    fence_high: float | None
    indices: list[int]          # posiciones (en la lista ORIGINAL, incluyendo None)
    n_outliers: int
    applicable: bool            # False si IQR==0 / MAD==0 -> no se declara ningun outlier
    reason: str                 # explicacion en espanol cuando applicable is False
```

**Funciones públicas (firmas exactas):**

```python
def percentile(sorted_values: list[float], q: float) -> float | None: ...
def describe(values) -> Distribution: ...
def histogram(values, bins: int = 10) -> list[HistBin]: ...
# [v2] C19 — REUSO: `cost_analytics.distribution(records, bins)` (cost_analytics.py:681,
# Plan 199) YA implementa esta misma semantica (clamp de bins, "el maximo cae en el ultimo
# bin", caso max == min). v1 la reinventaba sin saberlo, en un plan cuya §4 exige "una sola
# definicion". Decision: `cost_stats.histogram` es la CANONICA porque opera sobre `values`
# (cualquier metrica) y no solo sobre cost_usd. `distribution` NO se toca -- ni su firma, ni
# su payload, ni tests/test_cost_analytics_aggregate.py -- y queda como su envoltorio de
# compatibilidad. Un test fija que ambas coinciden:
# `test_histogram_coincide_con_cost_analytics_distribution`.
def tukey_outliers(values) -> OutlierReport: ...
def mad_outliers(values, threshold: float = 3.5) -> OutlierReport: ...
def metric_value(rec, metric: str) -> float | None: ...
def dimension_key(rec, dimension: str) -> str: ...
def by_dimension(records, dimension: str, metric: str) -> dict[str, Distribution]: ...
def cache_efficiency(records) -> dict: ...
def rework_index(records) -> dict: ...
def stats_payload(records, metrics=_METRICS, dimensions=_DIMENSIONS, bins: int = 10) -> dict: ...
```

#### F1.3 Definiciones SIN ambigüedad (un modelo menor no debe inferir nada)

**`percentile(sorted_values, q)` — interpolación lineal, método "inclusivo" (idéntico a `numpy.percentile` con `interpolation="linear"`), definido a mano:**
```
si sorted_values esta vacia  -> None
n = len(sorted_values)
si n == 1                    -> sorted_values[0]
idx = (q / 100.0) * (n - 1)          # indice real, base 0
lo  = floor(idx); hi = ceil(idx)
si lo == hi                  -> sorted_values[lo]
frac = idx - lo
resultado = sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac
```
`q1 = percentile(v, 25)`, `q3 = percentile(v, 75)`, `p50 = percentile(v, 50)` (que por construcción **coincide** con `median`; se exponen los dos igual, y hay un test que verifica la coincidencia).

> **`[v2]` ⚠️ YA HAY OTRO PERCENTIL EN EL REPO (C3).** v1 afirmaba *"una sola definición de percentil en
> todo el plan"* sin saber que el **Plan 171 ya implementó `run_signals.percentile_nearest_rank(values, q)`**
> (`run_signals.py:102`), que es **nearest-rank**, no interpolación lineal. **Dan números distintos para el
> mismo dataset** (con `[1,2,3,4]` y `q=50`: nearest-rank ⇒ `2`, interpolación lineal ⇒ `2.5`).
>
> **Decisión (y su razón):** se **mantienen las dos**, con dominios separados y declarados.
> - **Costo (este plan)** usa **interpolación lineal**: las distribuciones de costo son continuas y de cola
>   larga; el nearest-rank sobre muestras chicas salta de escalón y hace que el p95 se mueva de golpe.
> - **Salud operativa (Plan 171)** usa **nearest-rank**: devuelve **un valor observado real**, que es lo que
>   corresponde cuando el número se compara contra un umbral de alerta.
>
> **Prohibido** hacer que una llame a la otra, y **prohibido** "unificarlas" en esta fase: sería cambiar el
> comportamiento del 171 desde un plan ajeno. La divergencia queda **fijada por un test** (F1.5,
> `test_percentil_de_costo_difiere_del_operativo_a_proposito`), para que nadie la tome por un bug.
>
> Si algún día se quiere una sola definición, es un plan propio con su propia migración — no un efecto
> colateral de éste.

**`describe(values)`:**
```
limpios = [float(x) for x in values if x is not None]
n_missing = len(values) - len(limpios)
si n == 0 -> Distribution(n=0, n_missing=n_missing, todo lo demas None)
ordenados = sorted(limpios)
mean   = statistics.fmean(limpios)
median = statistics.median(limpios)
stdev  = statistics.stdev(limpios) si n >= 2, si no None      # MUESTRAL, n-1
iqr    = q3 - q1 si n >= 2, si no None
cv     = stdev/mean si (n >= 2 y mean != 0), si no None       # OJO: mean puede ser 0
mad    = statistics.median([abs(x - median) for x in limpios])
todos los floats se redondean a 6 decimales antes de devolver
```

**`histogram(values, bins)`:**
```
limpios como arriba
si vacia            -> []
lo = min, hi = max
si lo == hi         -> [HistBin(lo=lo, hi=hi, count=n)]        # UN solo bin, ancho 0
bins = max(1, min(bins, 100))                                   # clamp duro
ancho = (hi - lo) / bins
para i en 0..bins-1: borde_lo = lo + i*ancho ; borde_hi = borde_lo + ancho
asignacion de x: i = floor((x - lo)/ancho); si i >= bins -> i = bins-1   # el maximo cae en el ultimo bin
```

**`tukey_outliers(values)`:**
```
si n < 4                 -> OutlierReport(applicable=False, reason="menos de 4 muestras", indices=[])
iqr = q3 - q1
si iqr == 0              -> OutlierReport(applicable=False, reason="IQR = 0 (distribucion degenerada)", indices=[])
fence_low  = q1 - 1.5*iqr
fence_high = q3 + 1.5*iqr
indices = posiciones i de la lista ORIGINAL donde values[i] is not None
          y (values[i] < fence_low or values[i] > fence_high)
```

**`mad_outliers(values, threshold=3.5)`:**
```
si n < 4     -> applicable=False, reason="menos de 4 muestras"
median, mad  = de describe
si mad == 0  -> applicable=False, reason="MAD = 0 (mas de la mitad de los valores son identicos)"
z_robusto(x) = 0.6745 * (x - median) / mad      # 0.6745 = constante de consistencia normal
outlier si |z_robusto(x)| > threshold
fence_low  = median - threshold*mad/0.6745 ; fence_high = median + threshold*mad/0.6745
```
**Nunca se divide por MAD sin verificar `mad == 0` antes.**

**`metric_value(rec, metric)`** — mapeo exacto, `None` si falta cualquier insumo:

| `metric` | expresión |
|---|---|
| `cost_usd` | `rec.row.cost_usd` |
| `tokens_in` | `rec.row.tokens_in` |
| `tokens_out` | `rec.row.tokens_out` |
| `cache_read_tokens` | `rec.row.cache_read_tokens` |
| `cache_creation_tokens` | `rec.signals.cache_creation_tokens` si `rec.signals` no es `None`, si no `None` |
| `duration_s` | `rec.duration_s` |
| `tokens_total` | `tokens_in + tokens_out` si **ambos** no son `None`; si sólo uno está, `None` (no sumar contra 0) |
| `usd_per_ktok_out` | `cost_usd / (tokens_out/1000)` si `cost_usd` no es `None` **y** `tokens_out` no es `None` **y** `tokens_out > 0`; si no, `None` |

Cualquier otro valor de `metric` ⇒ `ValueError(f"metrica desconocida: {metric}")`.

**`dimension_key(rec, dimension)`** — string, nunca `None`; el ausente se mapea a `"(sin dato)"`:

| `dimension` | expresión | ausente |
|---|---|---|
| `runtime` | `rec.row.runtime` | `"(sin dato)"` |
| `model` | `rec.row.model` | `"(sin dato)"` |
| `agent_type` | `rec.agent_type` | `"(sin dato)"` |
| `project` | `rec.project` | `"(sin proyecto)"` |
| `work_item_type` | `rec.work_item_type` | `"(sin tipo)"` |
| `priority` | `str(rec.priority)` | `"(sin prioridad)"` |

Cualquier otro valor ⇒ `ValueError`. **No se reusa `cost_analytics._dim_key` (`:365`)** porque aquélla soporta `ticket`/`day` y no soporta `work_item_type`/`priority`; duplicar la tabla acá es más barato y más seguro que cambiar la del 142.

**`cache_efficiency(records)`** — devuelve exactamente:
```python
{
  "cache_read_total": int,             # suma de rec.row.cache_read_tokens (None cuenta 0 en la SUMA,
                                       # pero runs_with_cache_data cuenta cuantos aportaron dato real)
  "cache_creation_total": int,
  "tokens_in_total": int,
  "runs_with_cache_data": int,         # runs con cache_read_tokens is not None
  "cache_read_ratio": float | None,    # cache_read_total / (cache_read_total + tokens_in_total);
                                       # None si el denominador es 0
  "cache_savings_usd_total": float,    # suma de rec.row.cache_savings_usd (ya lo calcula el 142)
  "cache_write_overhead_ratio": float | None,  # cache_creation_total / cache_read_total; None si read==0
}
```

**`rework_index(records)`** — el rework es un costo real y hay que nombrarlo:
```python
{
  "pairs_total": int,        # cantidad de claves distintas (ticket_id, agent_type) con ticket_id != None
  "pairs_with_rework": int,  # claves con mas de 1 ejecucion
  "rework_runs": int,        # suma de (runs_del_par - 1) sobre todos los pares
  "rework_ratio": float | None,   # rework_runs / total_runs_con_ticket; None si 0
  "rework_cost_usd": float,  # suma del cost_usd de los runs que NO son el primero de su par,
                             # contando solo los facturables (reported|estimated)
  "top_rework": [            # top 10, ordenado por runs desc y despues por ticket_id asc (DETERMINISTA)
     {"ticket_id": int, "agent_type": str, "runs": int, "cost_usd": float}
  ],
}
```
"El primero del par" = el de `started_at` más antiguo; empate de `started_at` se rompe por `execution_id` ascendente (**determinismo obligatorio**). Runs con `ticket_id is None` se excluyen del índice y se reportan aparte en `"orphan_runs"`.

**`stats_payload(...)`** — arma el dict que consume el endpoint:
```python
{
  "metrics": { "<metric>": {"overall": Distribution-as-dict,
                            "histogram": [HistBin-as-dict, ...],
                            "outliers_tukey": OutlierReport-as-dict,
                            "outliers_mad": OutlierReport-as-dict } },
  "by_dimension": { "<dimension>": { "<key>": Distribution-as-dict } },
  "cache_efficiency": {...},
  "rework": {...},
  "runs_total": int,
}
```
Las claves de `by_dimension["<dimension>"]` se emiten **ordenadas alfabéticamente** (determinismo). La métrica usada en `by_dimension` es `cost_usd` por defecto y se puede pedir otra por query param (§5.F6).

#### F1.4 Casos borde enumerados

1. `records = []` ⇒ todas las `Distribution` con `n=0` y todo en `None`; `histogram` ⇒ `[]`; outliers `applicable=False`.
2. Un solo elemento ⇒ `stdev=None`, `iqr=None`, `cv=None`, `mad=0.0`, `min=max=mean=median=p50=…=ese valor`.
3. Todos los valores iguales (p. ej. 10 runs de 0,05 USD) ⇒ `stdev=0.0`, `iqr=0.0`, `mad=0.0`, `cv=0.0`, **ambos outlier reports con `applicable=False`** (no inventar outliers).
4. Mezcla con `None` ⇒ los `None` no participan de ningún cálculo y se cuentan en `n_missing`.
5. `mean == 0` (posible si todos los costos son 0,0 reportados) ⇒ `cv=None`, **no** `ZeroDivisionError`.
6. `tokens_out == 0` ⇒ `usd_per_ktok_out = None`.
7. Valor negativo (dato corrupto) ⇒ **se procesa igual**, y aparece como outlier de Tukey por el `fence_low`. No se filtra silenciosamente: filtrar sin avisar es ocultar corrupción.
8. `bins` fuera de rango (0, -1, 5000) ⇒ clamp a `[1, 100]`.

#### F1.5 Tests PRIMERO — `backend/tests/test_plan242_cost_stats.py`

| Caso | Qué verifica |
|---|---|
| `test_percentile_lista_vacia_es_none` | `percentile([], 50)` ⇒ `None` |
| `test_percentile_un_elemento` | `percentile([7.0], 99)` ⇒ `7.0` |
| `test_percentile_interpolacion_lineal_conocida` | `percentile([1,2,3,4], 50)` ⇒ `2.5` exacto |
| `test_percentile_p0_y_p100_son_min_y_max` | bordes |
| `test_p50_coincide_con_median` | invariante sobre 3 datasets distintos |
| `test_describe_expone_las_13_claves` | **KPI-1**: `n, n_missing, total, minimum, maximum, mean, median, stdev, q1, q3, iqr, cv, mad` + p50/p75/p90/p95/p99 presentes |
| `test_describe_lista_vacia_todo_none` | caso borde 1 |
| `test_describe_un_elemento_stdev_none` | caso borde 2 |
| `test_describe_todos_iguales_mad_cero` | caso borde 3 |
| `test_describe_ignora_none_y_cuenta_missing` | caso borde 4 |
| `test_describe_mean_cero_no_divide_por_cero` | caso borde 5, `cv is None` |
| `test_stdev_es_muestral_n_menos_1` | contra un valor calculado a mano |
| `test_histogram_vacio_es_lista_vacia` | |
| `test_histogram_todos_iguales_un_solo_bin` | |
| `test_histogram_el_maximo_cae_en_el_ultimo_bin` | evita el off-by-one del `floor` |
| `test_histogram_bins_se_clampea_1_a_100` | `bins=0` ⇒ 1; `bins=5000` ⇒ 100 |
| `test_tukey_iqr_cero_no_aplica` | `applicable is False` y `indices == []` |
| `test_tukey_detecta_outlier_alto_conocido` | dataset construido a mano con 1 outlier |
| `test_tukey_indices_son_de_la_lista_original_con_nones` | el índice apunta a la posición original |
| `test_mad_cero_no_aplica_y_no_divide` | `applicable is False`, sin excepción |
| `test_mad_detecta_outlier_conocido` | dataset a mano |
| `test_metric_value_tokens_total_none_si_falta_uno` | no suma contra 0 |
| `test_metric_value_usd_por_ktok_none_si_tokens_out_cero` | |
| `test_metric_value_metrica_desconocida_lanza` | `ValueError` |
| `test_dimension_key_ausente_es_sin_dato` | los 6 mapeos |
| `test_by_dimension_cubre_las_6_dimensiones` | **KPI-1** |
| `test_by_dimension_claves_ordenadas_alfabeticamente` | determinismo |
| `test_cache_efficiency_denominador_cero_es_none` | |
| `test_rework_index_desempate_por_execution_id` | determinismo del "primero del par" |
| `test_rework_cost_solo_facturables` | un run `nominal` de copilot no suma a `rework_cost_usd` |
| `test_rework_orphan_runs_se_reportan_aparte` | `ticket_id is None` |
| `test_stats_payload_es_json_serializable` | `json.dumps(payload)` no lanza |
| `test_cost_stats_es_puro_sin_db` | el módulo no importa `db` ni `models` (verificado por AST) |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_stats.py -q
```

#### F1.6 Aceptación (BINARIA)

1. Los 33 casos verdes.
2. `grep -c "test_plan242_cost_stats.py" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` ⇒ **1 y 1**.
3. `.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q` verde.
4. `grep -cE "^(import|from) (numpy|sklearn|scipy|pandas)" services/cost_stats.py` ⇒ **0**.

**Flag que la protege:** `STACKY_COST_STATS_ENABLED`, **default ON** (§5.F8). Ninguna de las 4 excepciones duras aplica: es read-only, sin LLM, sin red, sin acción irreversible y sin bypass de revisión humana.
**Impacto por runtime:** el módulo es agnóstico; opera sobre `ExecRecord` ya normalizado. `codex_cli` y `claude_code_cli` producen distribuciones de `cost_usd` reales; `github_copilot` produce distribuciones con `cost_kind="nominal"` — el endpoint (§5.F6) las **separa** en un bloque `nominal` para que no se mezclen con las facturables. Fallback en los tres: métrica sin dato ⇒ `Distribution(n=0)` explícita, nunca ceros.
**Trabajo del operador: ninguno.**

---

### F2 — Scoring determinista y explicable (`cost_scoring.py`)

**Objetivo (1 frase):** poner un número 0–100 y una letra A–E a cada ejecución y a cada ticket, con las razones en español que lo justifican, sin LLM y sin azar.
**Valor:** responde "¿este gasto estuvo bien?" — que es la pregunta que el operador realmente tiene y que ningún total responde.

#### F2.1 Archivos

| Acción | Ruta exacta |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/cost_scoring.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_scoring.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` |

#### F2.2 Contratos exactos

```python
"""Plan 242 F2 — Scoring de eficiencia economica. PURO, determinista, sin LLM."""
from __future__ import annotations

from dataclasses import dataclass, field

# Pesos: suman EXACTAMENTE 1.00. Hay un test que lo verifica.
W_COST_POSITION = 0.35   # que tan barato fue respecto de su cohorte
W_OUTCOME       = 0.25   # sirvio o no sirvio
W_CACHE         = 0.15   # cuanto reuso de cache logro
W_UNIT_COST     = 0.15   # USD por 1k tokens de salida vs la mediana de la cohorte
W_REWORK        = 0.10   # cuantas veces hubo que repetirlo

_WEIGHTS: dict[str, float] = {
    "cost_position": W_COST_POSITION,
    "outcome": W_OUTCOME,
    "cache": W_CACHE,
    "unit_cost": W_UNIT_COST,
    "rework": W_REWORK,
}

# Cortes de nota. Inclusivos por abajo. Test explicito de los bordes.
_GRADE_CUTS: tuple[tuple[float, str], ...] = (
    (85.0, "A"), (70.0, "B"), (55.0, "C"), (40.0, "D"), (0.0, "E"),
)

_CACHE_TARGET_RATIO = 0.50    # 50% de tokens leidos de cache == componente perfecto


@dataclass
class CohortStats:
    """Referencia contra la que se puntua UNA ejecucion. La arma build_cohorts()."""
    key: str                       # "<agent_type>|<model_family>"
    n: int
    costs_sorted: list[float]      # costos facturables de la cohorte, ORDENADOS asc
    median_unit_cost: float | None  # mediana de usd_per_ktok_out de la cohorte


@dataclass
class ExecutionScore:
    execution_id: int
    ticket_id: int | None
    agent_type: str | None
    runtime: str | None
    model: str | None
    cost_usd: float | None
    cost_kind: str
    score: float | None            # 0..100 redondeado a 2 decimales; None si nada computable
    grade: str                     # "A".."E" o "N/D"
    components: dict[str, float]   # solo los componentes COMPUTADOS, 0..100 c/u
    weights_used: dict[str, float]  # pesos RENORMALIZADOS efectivamente aplicados
    reasons: list[str]             # espanol, cada una con su numero
    cohort_key: str
    cohort_n: int
    confidence: str                # "alta" | "media" | "baja"


@dataclass
class TicketScore:
    ticket_id: int
    ado_id: int | None
    runs: int
    billable_usd: float
    score: float | None
    grade: str
    rework_penalty: float
    reasons: list[str]
    worst_execution_id: int | None
```

**Funciones públicas:**
```python
def model_family(model: str | None) -> str: ...
def build_cohorts(records) -> dict[str, CohortStats]: ...
def percent_rank(sorted_values: list[float], x: float) -> float | None: ...
def score_execution(record, cohorts: dict[str, CohortStats],
                    prev_runs: int = 0) -> ExecutionScore: ...
def score_ticket(records, cohorts: dict[str, CohortStats]) -> TicketScore: ...   # [v2] C8: cohorts es PARAMETRO
def score_payload(records, top_n: int = 50) -> dict: ...
```

#### F2.3 Fórmula EXACTA de cada componente

Cada componente devuelve un número en **[0, 100]** o `None` (no computable). Todos se redondean a 2 decimales.

**(1) `cost_position` (peso 0,35) — ¿fue barato para lo que es?**
```
cohorte = cohorts["<agent_type>|<model_family>"]
si record.row.cost_usd is None            -> None
si record.row.cost_kind == "nominal"      -> None   # G7: copilot no se puntua por precio
si cohorte is None o cohorte.n < 3        -> None   # sin referencia no se inventa
pr = percent_rank(cohorte.costs_sorted, record.row.cost_usd)     # 0..1, midrank
componente = 100.0 * (1.0 - pr)           # el mas barato de la cohorte -> 100
```
**`percent_rank(sorted_values, x)` (midrank, definido sin ambigüedad):**
```
n = len(sorted_values); si n == 0 -> None
menores = cantidad de v en sorted_values con v < x
iguales = cantidad de v en sorted_values con v == x
pr = (menores + 0.5*iguales) / n
```
(Se usa **midrank** y no `menores/n` para que, si todos los valores son iguales, `pr = 0.5` y el componente dé 50 —neutro— en vez de 100 —falso mérito—.)

**(2) `outcome` (peso 0,25) — ¿sirvió?** Tabla cerrada sobre `record.status` en minúsculas:

| `status` | componente |
|---|---|
| `completed` | 100.0 |
| `error`, `failed` | 0.0 |
| `cancelled`, `canceled` | 20.0 |
| `timeout` | 10.0 |
| `running`, `pending`, `queued` | `None` (todavía no se sabe) |
| cualquier otro / `None` | 50.0 |

**Modificador de veredicto (aditivo, aplicado DESPUÉS y clampeado a [0,100]):** si `record.verdict` en minúsculas es `"pass"` ⇒ `+0` (ya está en 100 si completó); si es `"fail"` ⇒ el componente se fuerza a `min(componente, 30.0)`; si es `None` ⇒ sin cambio. Motivo: un run que "completó" pero cuyo contrato dio `fail` **no** es un éxito económico.

**(3) `cache` (peso 0,15) — ¿reusó contexto?**
```
cr = record.row.cache_read_tokens ; ti = record.row.tokens_in
si cr is None o ti is None                -> None
denominador = cr + ti
si denominador == 0                        -> None
ratio = cr / denominador
componente = 100.0 * min(1.0, ratio / 0.50)     # 50% o mas de lectura de cache -> 100
```

**(4) `unit_cost` (peso 0,15) — ¿cuánto costó cada unidad de salida?**
```
si record.row.cost_usd is None o cost_kind == "nominal"   -> None
to = record.row.tokens_out ; si to is None o to <= 0      -> None
unit = record.row.cost_usd / (to / 1000.0)                # USD por 1k tokens de salida
cohorte = cohorts[...] ; si cohorte is None o cohorte.median_unit_cost is None -> None
si cohorte.median_unit_cost <= 0                          -> None
si unit <= 0                                              -> 100.0
componente = 100.0 * min(1.0, cohorte.median_unit_cost / unit)
             # unit == mediana -> 100 ; unit == 2x mediana -> 50 ; unit == 4x -> 25
```

**(5) `rework` (peso 0,10) — ¿fue el primer intento?** Tabla cerrada sobre `prev_runs` (ejecuciones **anteriores** del mismo `(ticket_id, agent_type)`, contadas por `started_at` ascendente):

| `prev_runs` | componente |
|---|---|
| 0 | 100.0 |
| 1 | 60.0 |
| 2 | 30.0 |
| ≥3 | 0.0 |

Si `record.ticket_id is None` ⇒ `None` (huérfana: no hay noción de rework).

**Renormalización (regla única, sin excepciones):**
```
presentes = {nombre: valor for nombre, valor in componentes.items() if valor is not None}
si presentes esta vacio -> ExecutionScore(score=None, grade="N/D",
       reasons=["Sin datos suficientes para puntuar: no hay costo, ni estado terminal, ni tokens."])
peso_total = suma de _WEIGHTS[nombre] para nombre en presentes
weights_used[nombre] = _WEIGHTS[nombre] / peso_total          # suman 1.00 de nuevo
score = round(suma de weights_used[n]*presentes[n], 2)
score = min(100.0, max(0.0, score))                           # clamp defensivo
```

**Grade:** primer corte de `_GRADE_CUTS` cuyo umbral sea `<= score`. Bordes exactos (con test): `85.0 -> "A"`, `84.99 -> "B"`, `70.0 -> "B"`, `69.99 -> "C"`, `55.0 -> "C"`, `54.99 -> "D"`, `40.0 -> "D"`, `39.99 -> "E"`, `0.0 -> "E"`.

**Confidence:**
```
n_comp = len(presentes) ; n_coh = cohorte.n si existe, si no 0
"alta"  si n_comp >= 4 y n_coh >= 20
"media" si n_comp >= 3 y n_coh >= 5
"baja"  en cualquier otro caso
```

**`model_family(model)`** — reusa la misma regla de prefijo más largo que `cost_analytics.input_price_per_mtok` (`:46`): itera `harness.pricing._load_prices()` y devuelve el **prefijo** más largo que matchea; si `model` es `None` ⇒ `"(sin modelo)"`; si ninguno matchea ⇒ `"(otro)"`. Esto mantiene una sola definición de "familia de modelo" para F2 y F3.

#### F2.4 Razones en español (obligatorio: cada una con su número) — plantillas EXACTAS

Se emite **una razón por componente computado**, más las razones especiales. El texto es una f-string literal (nada de generación libre):

| Componente | Plantilla |
|---|---|
| `cost_position` | `f"Costó {cost:.4f} USD: percentil {pr*100:.0f} de su cohorte '{cohort_key}' ({n} runs) — {'más barato' if pr<0.5 else 'más caro'} que la mediana."` |
| `outcome` | `f"Estado final '{status}'{verdicto_txt} → {valor:.0f}/100 en resultado."` donde `verdicto_txt` es `f" con veredicto '{verdict}'"` o `""` |
| `cache` | `f"Leyó {cr} tokens de cache sobre {cr+ti} de entrada ({ratio*100:.1f}%) → {valor:.0f}/100 en reuso."` |
| `unit_cost` | `f"{unit:.4f} USD por 1k tokens de salida vs {mediana:.4f} de su cohorte ({razon_x:.1f}×)."` |
| `rework` | `f"Es el intento #{prev_runs+1} de este ticket con el agente '{agent_type}' → {valor:.0f}/100 en rework."` |

**Razones especiales (se agregan siempre que apliquen):**
- `cost_kind == "nominal"` ⇒ `"Runtime de suscripción plana (github_copilot): el costo es nominal, no facturable — no se puntúa el precio."`
- componente `None` por falta de dato ⇒ `f"Componente '{nombre}' no evaluado: {motivo}."` con `motivo` de tabla cerrada: `"sin costo registrado"`, `"cohorte con menos de 3 runs"`, `"sin tokens de entrada o de cache"`, `"sin tokens de salida"`, `"ejecución sin ticket asociado"`, `"ejecución aún en curso"`.
- `confidence == "baja"` ⇒ `f"Confianza baja: {n_comp} componentes evaluados sobre una cohorte de {n_coh} runs."`

#### F2.5 `score_ticket(records)` — fórmula exacta

```
records_del_ticket = todos los ExecRecord con el mismo ticket_id (el caller ya filtro)
si esta vacio -> ValueError("score_ticket requiere al menos una ejecucion")
# [v2] C8 — la cohorte entra POR PARAMETRO, no se construye local.
# v1 hacia `cohorts = build_cohorts(records_del_ticket)`: una cohorte armada con las
# ejecuciones de UN SOLO ticket casi siempre tiene n < 3, y `cost_position` devuelve None
# por debajo de 3 (§F2.3). Resultado: el componente de MAYOR PESO (0,35) quedaba en None
# para practicamente todos los tickets, y el score del ticket se calculaba sobre los otros
# cuatro renormalizados. El plan anulaba en silencio su propia metrica principal.
# La firma pasa a ser score_ticket(records, cohorts) y el caller (score_payload) le pasa
# la cohorte GLOBAL, que es la unica referencia con sentido: "caro comparado con QUE".
scores  = [score_execution(r, cohorts, prev_runs=k).score for cada r ordenado por started_at]
validos = [s for s in scores if s is not None]
si validos esta vacio -> TicketScore(score=None, grade="N/D", reasons=[...])
base = suma(validos) / len(validos)                          # media aritmetica simple
# Penalidad de rework: 4 puntos por cada run EXTRA del mismo agent_type, tope 20.
runs_extra = suma sobre agent_type de max(0, runs_de_ese_agent_type - 1)
rework_penalty = min(20.0, 4.0 * runs_extra)
score = round(min(100.0, max(0.0, base - rework_penalty)), 2)
billable_usd = suma de cost_usd de los runs con cost_kind en ("reported","estimated")
worst_execution_id = el execution_id del run con menor score (None si no hay validos);
                     empate -> el execution_id mas chico (DETERMINISMO)
```
Razón agregada obligatoria cuando `rework_penalty > 0`:
`f"Penalidad de rework: -{rework_penalty:.0f} puntos por {runs_extra} ejecución(es) repetida(s) del mismo agente."`

#### F2.6 `score_payload(records, top_n=50)` — shape del endpoint

```python
{
  "cohorts": {"<key>": {"n": int, "median_cost_usd": float|None,
                        "median_unit_cost": float|None}},   # claves ORDENADAS alfabeticamente
  "executions": [ExecutionScore-as-dict, ...],   # top_n peores primero (score asc);
                                                  # los score=None van al FINAL, ordenados por execution_id
  "tickets": [TicketScore-as-dict, ...],          # top_n peores primero, mismo criterio
  "grade_distribution": {"A": int, "B": int, "C": int, "D": int, "E": int, "N/D": int},
  "runs_total": int,
  "runs_scored": int,
}
```

#### F2.7 Casos borde enumerados

1. `records = []` ⇒ `score_payload` devuelve todo vacío y `grade_distribution` con los 6 contadores en 0.
2. Ejecución de `github_copilot` ⇒ `cost_position` y `unit_cost` en `None`, se renormaliza sobre `outcome`+`cache`+`rework` (pesos 0,25/0,15/0,10 ⇒ renormalizados a 0,50/0,30/0,20) y aparece la razón especial de suscripción plana.
3. Ejecución sin ningún dato (status `running`, sin costo, sin tokens, sin ticket) ⇒ `score=None`, `grade="N/D"`, una razón explicando por qué.
4. Cohorte de 1 solo run ⇒ `cost_position=None` (n<3) y `confidence="baja"`.
5. Todos los runs de la cohorte con el mismo costo ⇒ `percent_rank = 0.5` ⇒ componente 50 (neutro), no 100.
6. `cost_usd = 0.0` reportado ⇒ es un dato válido: `percent_rank` lo trata como el mínimo; `unit_cost` devuelve 100.0 por la rama `unit <= 0`.
7. Ejecución con `verdict = "fail"` y `status = "completed"` ⇒ `outcome` forzado a `30.0`, con la razón mostrando el veredicto.
8. `tokens_out = 0` ⇒ `unit_cost=None` con motivo `"sin tokens de salida"`.

#### F2.8 Tests PRIMERO — `backend/tests/test_plan242_cost_scoring.py`

| Caso | Qué verifica |
|---|---|
| `test_pesos_suman_exactamente_uno` | `sum(_WEIGHTS.values()) == 1.0` (con `math.isclose`, `rel_tol=1e-9`) |
| `test_percent_rank_midrank_todos_iguales_da_medio` | caso borde 5 |
| `test_percent_rank_minimo_y_maximo` | bordes 0,5/n y 1-0,5/n |
| `test_percent_rank_lista_vacia_es_none` | |
| `test_cost_position_mas_barato_da_100` | dataset a mano |
| `test_cost_position_none_si_cohorte_menor_a_3` | caso borde 4 |
| `test_cost_position_none_para_nominal_copilot` | G7 |
| `test_outcome_tabla_cerrada_los_9_estados` | los 9 mapeos de la tabla |
| `test_outcome_verdict_fail_fuerza_maximo_30` | caso borde 7 |
| `test_outcome_running_es_none` | |
| `test_cache_ratio_50pct_da_100` | `cr=1000, ti=1000` ⇒ ratio 0,5 ⇒ 100 |
| `test_cache_denominador_cero_es_none` | |
| `test_unit_cost_igual_a_mediana_da_100` | |
| `test_unit_cost_doble_de_mediana_da_50` | |
| `test_unit_cost_tokens_out_cero_es_none` | caso borde 8 |
| `test_rework_tabla_cerrada_0_1_2_3` | los 4 valores |
| `test_rework_none_si_no_hay_ticket` | |
| `test_renormalizacion_pesos_suman_uno_cuando_faltan_componentes` | caso borde 2: los 3 presentes suman 1,00 |
| `test_sin_componentes_score_none_y_grade_nd` | caso borde 3 |
| `test_grade_bordes_exactos` | los 9 bordes de §F2.3 |
| `test_score_clampeado_a_0_100` | |
| `test_toda_puntuacion_trae_razones_con_numeros` | **KPI-2**: `reasons` no vacío y ≥1 razón contiene un dígito |
| `test_razon_especial_copilot_menciona_suscripcion_plana` | |
| `test_razon_de_componente_no_evaluado_usa_motivo_de_tabla_cerrada` | el motivo pertenece al set cerrado |
| `test_confidence_alta_media_baja` | los 3 umbrales |
| `test_scoring_es_determinista_50_corridas` | **KPI-3**: `json.dumps(payload, sort_keys=True)` idéntico en 50 corridas |
| `test_scoring_no_depende_del_orden_de_entrada` | mismo set barajado con `random.Random(1234).shuffle` ⇒ mismo payload |
| `test_score_ticket_penalidad_rework_tope_20` | 10 runs del mismo agente ⇒ penalidad exactamente 20 |
| `test_score_ticket_worst_execution_desempata_por_id` | determinismo |
| `test_score_ticket_billable_excluye_nominal` | G7 |
| `test_score_payload_ordena_peores_primero_y_none_al_final` | |
| `test_score_payload_grade_distribution_suma_runs_total` | invariante |
| `test_cost_scoring_no_invoca_llm_ni_red` | AST: sin `requests`, sin `socket`, sin `subprocess`, sin `urllib` |
| `test_cost_scoring_no_usa_random` | AST: sin `import random` |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_scoring.py -q
```

#### F2.9 Aceptación (BINARIA)

1. Los 34 casos verdes.
2. **KPI-2** y **KPI-3** verdes por nombre de caso.
3. `grep -c "test_plan242_cost_scoring.py" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` ⇒ **1 y 1**; ratchet meta verde.
4. `grep -cE "^(import|from) (numpy|sklearn|scipy|pandas|random|requests)" services/cost_scoring.py` ⇒ **0**.

**Flag que la protege:** `STACKY_COST_SCORING_ENABLED`, **default ON** (read-only, determinista, sin red/LLM; ninguna excepción dura aplica).
**Impacto por runtime:** `codex_cli` y `claude_code_cli` puntúan con los 5 componentes (fallback: el componente sin dato se excluye y se renormaliza). `github_copilot` puntúa con 3 componentes (`outcome`, `cache`, `rework`), nunca con precio, y su `ExecutionScore.cost_kind` sigue siendo `"nominal"` — fallback explícito, no silencioso: la razón lo dice.
**Trabajo del operador: ninguno.**

---

### F3 — Modelo predictivo propio (`cost_model.py`) — Python puro, sin numpy, sin sklearn

**Objetivo (1 frase):** aprender del histórico de tickets y ejecuciones para responder, **antes** de correr, cuántos USD va a costar resolver una tarea, con intervalo P10/P50/P90 y confianza honesta.
**Valor:** es el entregable #3 del pedido del operador y lo único que cierra el gap de `cost_estimator.py:34` (`OUTPUT_RATIO` hardcodeado desde FA-33).

#### F3.1 Archivos

| Acción | Ruta exacta |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/cost_model.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_features.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_model.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_model_perf.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` |

#### F3.2 Elección del algoritmo, con justificación

**Se elige: regresión ridge sobre `log1p(cost_usd)`, resuelta por ECUACIONES NORMALES con eliminación gaussiana con pivoteo parcial, implementada a mano.**

Se descarta el descenso de gradiente porque exige elegir tasa de aprendizaje, número de épocas y criterio de parada — tres decisiones que un modelo menor implementando este plan resolvería mal y que introducen no-determinismo práctico. Las ecuaciones normales son **exactas, deterministas y sin hiperparámetros de optimización**; con `λ > 0` la matriz `(ZᵀZ + λI)` es siempre definida positiva, o sea **siempre invertible**, sin importar la colinealidad de los one-hot. Con `d ≈ 40` features, resolver el sistema cuesta `O(d³) ≈ 64.000` operaciones: irrelevante.

**Se usa `log1p(cost_usd)` como objetivo** porque la distribución de costos es de cola larga y estrictamente positiva; en escala log la relación es aproximadamente lineal y los residuos, aproximadamente simétricos — que es exactamente lo que necesita el intervalo conformal de §F3.6.

**Truco de rendimiento obligatorio (sin él no se cumple el KPI-7):** los features one-hot **NO se normalizan** (quedan en 0/1, que ya es una escala comparable) y cada fila se representa **dispersa** como `list[tuple[int, float]]` de entradas no nulas. Sólo los features continuos se z-scorean. Así la acumulación del Gram cuesta `n·k²` con `k ≈ 11` no-nulos por fila, en vez de `n·d²` con `d ≈ 40`: **13 veces menos operaciones**.

#### F3.3 Features — vocabulario, orden y extracción

```python
# Continuos: SE Z-SCOREAN. Orden fijo, indices 0..4.
CONTINUOUS_FEATURES: tuple[str, ...] = (
    "log1p_prompt_tokens_est",   # log(1 + (len(title)+len(description))/4)
    "n_acceptance_criteria",     # criterios detectados en la descripcion
    "prev_executions",           # ejecuciones previas del ticket
    "log1p_project_median_usd",  # log(1 + mediana historica de costo del proyecto)
    "input_price_per_mtok",      # precio de entrada del modelo, USD/Mtok (0.0 si no matchea)
)

# One-hot cerrados (vocabulario FIJO, no depende de los datos):
WORK_ITEM_TYPES: tuple[str, ...] = ("Bug", "Issue", "Task", "User Story", "Feature", "Epic", "otros")
PRIORITIES: tuple[str, ...] = ("1", "2", "3", "4", "otros")
RUNTIMES: tuple[str, ...] = ("codex_cli", "claude_code_cli", "github_copilot", "otros")

# One-hot ABIERTOS (vocabulario aprendido en el entrenamiento y PERSISTIDO en el JSON):
#   agent_type   -> los agent_type vistos, ordenados alfabeticamente, + "otros"
#   model_family -> las familias vistas (via cost_scoring.model_family), ordenadas, + "otros"
```

```python
@dataclass
class FeatureVocab:
    agent_types: tuple[str, ...]     # SIEMPRE termina en "otros"
    model_families: tuple[str, ...]  # SIEMPRE termina en "otros"


@dataclass
class TicketFeaturesInput:
    """Todo lo que build_features necesita. PURO: no toca DB. El caller lo arma."""
    title: str | None
    description: str | None
    work_item_type: str | None
    priority: object | None          # puede venir int o str
    agent_type: str | None
    runtime: str | None
    model: str | None
    prev_executions: int = 0
    project_median_usd: float = 0.0


def feature_names(vocab: FeatureVocab) -> tuple[str, ...]: ...
def build_features(inp: TicketFeaturesInput, vocab: FeatureVocab) -> list[tuple[int, float]]: ...
```

**`feature_names(vocab)`** devuelve, en este orden exacto:
```
CONTINUOUS_FEATURES (5)
+ ("wit=" + t for t in WORK_ITEM_TYPES)        (7)
+ ("prio=" + p for p in PRIORITIES)            (5)
+ ("rt=" + r for r in RUNTIMES)                (4)
+ ("at=" + a for a in vocab.agent_types)       (variable)
+ ("mf=" + m for m in vocab.model_families)    (variable)
```
El índice `i` de `feature_names` corresponde 1-a-1 con la posición del vector. **Los primeros `len(CONTINUOUS_FEATURES)` índices son los continuos** — ésa es la frontera que usa el z-scoring.

**Reglas de extracción, sin ambigüedad:**

1. `prompt_tokens_est = (len(title or "") + len(description or "")) / 4.0` — heurística de 4 caracteres por token, la misma que ya usa `cost_estimator._approx_tokens` (`cost_estimator.py:81`). Feature = `math.log1p(prompt_tokens_est)`.
2. `n_acceptance_criteria` = cantidad de líneas de `description` (separadas por `\n`) que, tras `strip()`, **empiezan** con `-`, `*`, `•`, o con un dígito seguido de `.` o `)`. Cap duro a **50** (una descripción patológica no debe dominar el feature). Si `description` es `None` ⇒ `0.0`.
3. `prev_executions` = valor pasado por el caller, cap duro a **20**.
4. `log1p_project_median_usd = math.log1p(max(0.0, project_median_usd))`.
5. `input_price_per_mtok` = `cost_analytics.input_price_per_mtok(model)`; si es `None` ⇒ `0.0`. (Éste **sí** puede ser 0 legítimamente: significa "modelo desconocido para la tabla de precios", que es información.)
6. `work_item_type`: match **exacto y sensible a mayúsculas** contra `WORK_ITEM_TYPES`; si no matchea o es `None` ⇒ `"otros"`.
7. `priority`: `str(priority).strip()` y match exacto contra `PRIORITIES`; si no ⇒ `"otros"`.
8. `runtime`: match exacto contra `RUNTIMES`; si no ⇒ `"otros"`.
9. `agent_type`: match exacto contra `vocab.agent_types`; si no ⇒ `"otros"`.
10. `model_family`: `cost_scoring.model_family(model)`; match exacto contra `vocab.model_families`; si no ⇒ `"otros"`.

**`build_features` devuelve la fila DISPERSA:** una lista de `(indice, valor)` con **sólo** las entradas no nulas. Los 5 continuos se emiten **siempre** (aunque valgan 0,0, porque después se centran y dejan de ser 0); los one-hot emiten **exactamente uno** por bloque, con valor `1.0`.

**Exclusiones del entrenamiento (G7 + higiene), en `collect_training_rows`:**
- Filas con `cost_kind` **distinto** de `"reported"` (se entrena **sólo** con costo realmente reportado; `estimated` es salida de `pricing.estimate_cost`, o sea aprender de sí mismo, y `nominal`/`unknown` no son dinero).
- Filas de `github_copilot` (quedan excluidas automáticamente por la regla anterior, porque siempre son `nominal`) — se declara igual de forma explícita para que quede documentado.
- Filas con `cost_usd is None` o `< 0`.
- Filas con `started_at is None` (no se puede ubicar en el split temporal).

#### F3.4 Pseudocódigo COMPLETO del entrenamiento

```python
_LAMBDA = 1.0                  # regularizacion ridge
_TRAIN_MAX_ROWS = 20000        # cap duro; si hay mas, se toman las MAS RECIENTES
_SCHEMA_VERSION = 1
_MODEL_FILENAME = "cost_model.json"
_SINGULAR_EPS = 1e-12


class SingularMatrixError(Exception):
    """El sistema no se pudo resolver. El caller cae al fallback, NO crashea."""


def fit_ridge(rows_sparse, y, n_features, n_continuous, lam=_LAMBDA):
    """rows_sparse: list[list[tuple[int,float]]]  ; y: list[float]
    Devuelve (mu, sd, weights, intercept). NO usa numpy."""
    n = len(rows_sparse)
    # ---- 1) media y desvio POBLACIONAL de las columnas CONTINUAS ---------------
    #      (poblacional, no muestral: es una normalizacion, no una inferencia)
    mu = [0.0]*n_features
    sd = [1.0]*n_features
    for j in range(n_continuous):
        col = [valor_en(rows_sparse[i], j) for i in range(n)]   # 0.0 si no esta
        mu[j] = sum(col)/n
        var = sum((x-mu[j])**2 for x in col)/n
        s = math.sqrt(var)
        sd[j] = s if s > 1e-12 else 1.0        # columna constante -> sd 1.0 (queda en 0 tras centrar)
    # los one-hot (j >= n_continuous) conservan mu=0.0, sd=1.0 -> NO se tocan (sparsidad intacta)

    # ---- 2) centrar y ---------------------------------------------------------
    y_mean = sum(y)/n
    yc = [v - y_mean for v in y]

    # ---- 3) fila normalizada (sigue dispersa: solo cambian los continuos) -----
    def znorm(fila):
        return [(j, (v - mu[j])/sd[j] if j < n_continuous else v) for (j, v) in fila]

    # ---- 4) Gram: A = Z^T Z + lam*I   (d x d, simetrica)  y  b = Z^T yc -------
    A = [[0.0]*n_features for _ in range(n_features)]
    b = [0.0]*n_features
    for i in range(n):
        z = znorm(rows_sparse[i])
        for (j, vj) in z:
            b[j] += vj * yc[i]
            for (k, vk) in z:          # solo sobre los NO NULOS -> n*k^2, no n*d^2
                A[j][k] += vj * vk
    for j in range(n_features):
        A[j][j] += lam

    # ---- 5) resolver A w = b --------------------------------------------------
    w = solve_linear(A, b)
    return mu, sd, w, y_mean          # intercept == y_mean porque yc esta centrado y Z tambien
                                      # en sus columnas continuas


def solve_linear(A, b):
    """Eliminacion gaussiana con pivoteo parcial + sustitucion hacia atras.
    A: list[list[float]] d x d (se copia, no se muta el argumento). b: list[float] d."""
    d = len(b)
    M = [list(A[i]) + [b[i]] for i in range(d)]      # matriz aumentada d x (d+1)
    for col in range(d):
        # 5a) pivoteo parcial: fila con |valor| maximo en esta columna, de col hacia abajo
        piv = col
        for r in range(col+1, d):
            if abs(M[r][col]) > abs(M[piv][col]):
                piv = r
        if abs(M[piv][col]) < _SINGULAR_EPS:
            raise SingularMatrixError(f"columna {col} sin pivote utilizable")
        M[col], M[piv] = M[piv], M[col]
        # 5b) normalizar la fila pivote
        p = M[col][col]
        for c in range(col, d+1):
            M[col][c] /= p
        # 5c) eliminar la columna en TODAS las demas filas (Gauss-Jordan: evita la
        #     sustitucion hacia atras y es mas simple de implementar sin errores)
        for r in range(d):
            if r == col:
                continue
            factor = M[r][col]
            if factor == 0.0:
                continue
            for c in range(col, d+1):
                M[r][c] -= factor * M[col][c]
    return [M[i][d] for i in range(d)]
```

**`valor_en(fila_dispersa, j)`**: recorre la lista de tuplas y devuelve el valor de la primera con índice `j`, o `0.0`. (Con ≤ 12 no-nulos por fila, la búsqueda lineal es más rápida que construir un dict.)

**Predicción puntual en escala log:**
```python
def _predict_log(fila_dispersa, mu, sd, w, intercept, n_continuous) -> float:
    acc = intercept
    for (j, v) in fila_dispersa:
        z = (v - mu[j])/sd[j] if j < n_continuous else v
        acc += w[j] * z
    # [v2] C7 — COMENTARIO CORREGIDO. v1 decia aca: "los continuos AUSENTES contribuyen
    # (0 - mu[j])/sd[j] * w[j]". Es FALSO y contradecia al propio codigo: el `for` recorre
    # SOLO las entradas presentes, asi que un continuo ausente aporta EXACTAMENTE 0.
    # (Y v1 ademas pedia un test que afirmaba lo falso: habria quedado rojo sin arreglo posible.)
    #
    # Lo que SI es cierto, y por eso importa:
    #   - En ENTRENAMIENTO, znorm() tambien mapea solo las entradas presentes => el Gram se
    #     acumula con la misma convencion "ausente = aporte 0". Entrenamiento y prediccion
    #     son CONSISTENTES entre si.
    #   - Pero mu[j] se calcula con valor_en(fila, j), que devuelve 0.0 si el feature falta:
    #     o sea la media se estima imputando 0, mientras el diseño trata al ausente como
    #     "igual a la media". Son dos imputaciones distintas.
    #   - Esa inconsistencia NO se manifiesta porque build_features emite SIEMPRE los 5
    #     continuos (aunque valgan 0.0). Es un invariante del que depende la correccion del
    #     modelo, no una comodidad: si alguien alguna vez omite un continuo, el modelo se
    #     desalinea en silencio. Por eso el test que lo fija es OBLIGATORIO.
    return acc
```

#### F3.5 Fallback jerárquico (4 niveles, obligatorio)

`_MIN_SAMPLES` viene de la flag `STACKY_COST_MODEL_MIN_SAMPLES` (default **30**, bounds 10..5000).

```python
@dataclass
class CostPrediction:
    p10_usd: float
    p50_usd: float
    p90_usd: float
    source: str          # "model" | "cohort_median" | "global_median" | "heuristic"
    confidence: str      # "alta" | "media" | "baja" | "muy_baja"
    n_samples: int
    cost_kind: str       # SIEMPRE "forecast" (G6). Nunca entra en _billable().
    billable: bool       # False si runtime == "github_copilot" (G7)
    explanation: list[str]
    model_trained_at: str | None
    model_status: str | None    # "active" | "candidate" | None
```

| Nivel | Condición para usarlo | `source` | `confidence` |
|---|---|---|---|
| **L1** | hay `cost_model.json` cargado **y** `status == "active"` **y** `n_samples >= _MIN_SAMPLES` | `"model"` | `"alta"` si `n_samples >= 200`; `"media"` si `>= 60`; `"baja"` si no |
| **L2** | existe la cohorte `"<agent_type>|<model_family>"` en `cohort_medians` con `n >= 5` | `"cohort_median"` | `"media"` si `n >= 20`, si no `"baja"` |
| **L3** | hay `global_median` (o sea, al menos 1 fila facturable histórica) | `"global_median"` | `"baja"` |
| **L4** | nada de lo anterior | `"heuristic"` | `"muy_baja"` |

**L2 y L3** producen el intervalo con un **multiplicador fijo y declarado**: `p10 = p50 * 0.40`, `p90 = p50 * 2.50`. (Elegido para reflejar la dispersión típica de cola larga sin pretender rigor estadístico; la `confidence` ya avisa que es grueso, y la razón lo dice textualmente.)

**L4** llama, en este orden: `harness.pricing.estimate_cost(model, tokens_in_est, tokens_out_est)` donde `tokens_in_est = prompt_tokens_est` y `tokens_out_est = prompt_tokens_est * cost_estimator.OUTPUT_RATIO.get(agent_type, 0.5)`; si eso devuelve `None`, se usa `cost_estimator.estimate(agent_type=..., blocks=[], model=...)` y se toma su costo. Si **también** falla, `CostPrediction` con los tres valores en `0.0`, `confidence="muy_baja"` y la explicación `"Sin histórico y sin tabla de precios para este modelo: no hay base para estimar."`. **Nunca se lanza excepción al caller.**

**`explanation: list[str]`** — para L1, las **5** features de mayor `|w[j] * z[j]|`, con signo y magnitud, en plantilla literal:
```
f"{nombre_feature}: {'sube' if aporte > 0 else 'baja'} la estimación en {abs(aporte):.3f} (escala log)."
```
más una línea de contexto: `f"Modelo entrenado el {trained_at} con {n_samples} ejecuciones reportadas."`
Para L2: `f"Sin modelo activo: se usa la mediana de la cohorte '{key}' ({n} runs) = {mediana:.4f} USD."`
Para L3: `f"Cohorte insuficiente: se usa la mediana global de {n} ejecuciones = {mediana:.4f} USD."`
Para L4: `f"Sin histórico: estimación heurística por tokens y tabla de precios ({modelo})."`
Y si `runtime == "github_copilot"`, se **antepone** siempre: `"Costo nominal — no facturable (suscripción plana). El número es referencial."`

#### F3.6 Intervalo de predicción — conformal simple, paso a paso

1. Del set de entrenamiento se aparta un **set de calibración** (§F4: el 15 % intermedio del split temporal). El modelo se ajusta **sólo** con el 70 % de entrenamiento.
2. Para cada fila `i` del set de calibración se calcula el residuo **en escala log**: `r_i = log1p(cost_real_i) - _predict_log(fila_i)`.
3. Se ordenan los residuos y se toman `q10 = percentile(res, 10)`, `q50 = percentile(res, 50)`, `q90 = percentile(res, 90)` usando **la misma** `cost_stats.percentile` de F1 (una sola definición de percentil en todo el plan).
4. Al predecir: `p = _predict_log(fila)`, y
   `p10 = max(0.0, math.expm1(p + q10))`, `p50 = max(0.0, math.expm1(p + q50))`, `p90 = max(0.0, math.expm1(p + q90))`.
5. **Monotonicidad forzada:** `p10, p50, p90 = sorted([p10, p50, p90])`. (Si el modelo está mal calibrado los cuantiles podrían cruzarse; se ordena en vez de devolver un intervalo inválido.)
6. Si el set de calibración tiene **menos de 10 filas**, los tres cuantiles se fijan en `q10=-0.9, q50=0.0, q90=0.9` (constantes declaradas `_FALLBACK_RESIDUAL_QUANTILES`) y el modelo queda forzado a `status="candidate"` (o sea, no se usa).

#### F3.7 Persistencia versionada

Ruta: `runtime_paths.data_dir() / "cost_model.json"` — se importa con `from runtime_paths import data_dir`, que es el patrón real del repo (p. ej. `backend/services/ado_feedback.py:10` y `backend/services/ado_identity.py:32`).

```json
{
  "schema_version": 1,
  "trained_at": "2026-07-25T14:03:11Z",
  "status": "active",
  "n_samples": 412,
  "n_train": 288, "n_calib": 62, "n_test": 62,
  "lambda": 1.0,
  "n_continuous": 5,
  "feature_names": ["log1p_prompt_tokens_est", "...", "mf=otros"],
  "vocab": {"agent_types": ["...", "otros"], "model_families": ["...", "otros"]},
  "mu": [0.0], "sd": [1.0], "weights": [0.0], "intercept": -3.21,
  "residual_q10": -0.42, "residual_q50": 0.01, "residual_q90": 0.55,
  "eval": {"mae": 0.0912, "mape": 0.38, "rmsle": 0.44, "coverage": 0.79,
            "baseline_mae": 0.1477, "n_test": 62},
  "cohort_medians": {"developer|claude-sonnet": {"n": 87, "median_usd": 0.2140,
                                                   "median_unit_cost": 0.0031}},
  "global_median_usd": 0.0932,
  "global_n": 412
}
```

**Escritura atómica obligatoria:** escribir en `cost_model.json.tmp` y luego `os.replace(tmp, final)`. Un corte de luz a mitad de escritura no debe dejar un JSON truncado.

**Carga tolerante — `load_model() -> TrainedModel | None`. Devuelve `None` (con `logger.warning`) y NUNCA lanza, en TODOS estos casos:**
1. El archivo no existe.
2. `json.JSONDecodeError` al parsear.
3. Falta cualquier clave obligatoria (`schema_version`, `weights`, `feature_names`, `mu`, `sd`, `intercept`, `n_continuous`, `vocab`).
4. `schema_version != _SCHEMA_VERSION`.
5. `len(weights) != len(feature_names)` o `len(mu) != len(weights)` o `len(sd) != len(weights)`.
6. Cualquier valor de `weights`/`mu`/`sd`/`intercept` es `NaN` o `inf` (verificado con `math.isfinite`).
7. `OSError`/`PermissionError` al leer.

Log exacto: `logger.warning("cost_model: modelo descartado (%s); se usa el fallback", motivo)`.

**Nota:** `cohort_medians` y `global_median_usd` se guardan **siempre**, incluso si el modelo queda `candidate` — porque son los niveles L2 y L3 del fallback y valen por sí solos.

#### F3.8 API pública del módulo

```python
def collect_training_rows(days: int = 365) -> list[TrainingRow]: ...     # UNICA funcion que toca DB
def build_vocab(rows) -> FeatureVocab: ...
def train(days: int = 365, min_samples: int | None = None) -> TrainResult: ...
def load_model() -> TrainedModel | None: ...
def save_model(model: TrainedModel) -> None: ...
def predict(inp: TicketFeaturesInput, model: TrainedModel | None = None) -> CostPrediction: ...
def model_status() -> dict: ...
```
`collect_training_rows` reusa `cost_analytics.load_records(CostFilters(days=days))` — **no** escribe su propia query, para que haya una sola definición de "qué filas cuentan".

#### F3.9 Casos borde enumerados

1. `n_samples < _MIN_SAMPLES` ⇒ `train()` devuelve `TrainResult(trained=False, reason="muestras insuficientes: 12 < 30")`, **igual persiste** `cohort_medians` y `global_median_usd` para L2/L3, y `status="candidate"`.
2. Todos los `cost_usd` idénticos ⇒ `yc` todo cero ⇒ `w` todo cero ⇒ predicción = `expm1(y_mean)` = la constante. Correcto, no es un bug.
3. `SingularMatrixError` ⇒ se captura en `train()`, se loguea, `TrainResult(trained=False, reason="sistema singular")` y el modelo queda `candidate`.
4. Una sola fila (`n=1`) ⇒ `var=0` ⇒ `sd=1.0` para todos ⇒ no divide por cero; igual cae por el gate de `_MIN_SAMPLES`.
5. `agent_type` nuevo, no visto en el entrenamiento ⇒ cae en `"at=otros"`; el modelo sigue prediciendo.
6. `model` nuevo ⇒ `"mf=otros"` + `input_price_per_mtok = 0.0`.
7. `description` de 500.000 caracteres ⇒ `log1p` la comprime; `n_acceptance_criteria` capeado en 50.
8. `cost_usd = 0.0` reportado ⇒ `log1p(0) = 0`, válido, entra al entrenamiento.
9. Archivo del modelo corrupto ⇒ `load_model()` ⇒ `None` ⇒ `predict()` cae a L2/L3/L4. **La UI sigue mostrando un número, con confianza degradada y la razón visible.**

#### F3.10 Tests PRIMERO

**`backend/tests/test_plan242_cost_features.py`** (features puras, sin DB):

| Caso | Qué verifica |
|---|---|
| `test_feature_names_orden_y_longitud` | 5 continuos + 7 + 5 + 4 + `len(at)` + `len(mf)` |
| `test_continuos_son_los_primeros_5` | frontera del z-scoring |
| `test_build_features_emite_siempre_los_5_continuos` | aunque valgan 0,0 |
| `test_build_features_un_solo_onehot_por_bloque` | exactamente 4 one-hot activos |
| `test_prompt_tokens_est_cuatro_chars_por_token` | 400 chars ⇒ 100 tokens ⇒ `log1p(100)` |
| `test_criterios_de_aceptacion_cuenta_guiones_asteriscos_vinetas_y_numeros` | los 4 marcadores |
| `test_criterios_capeado_en_50` | 200 líneas con guion ⇒ 50 |
| `test_prev_executions_capeado_en_20` | |
| `test_work_item_type_desconocido_cae_en_otros` | |
| `test_priority_int_o_str_matchea_igual` | `priority=2` y `"2"` dan el mismo vector |
| `test_runtime_desconocido_cae_en_otros` | |
| `test_agent_type_no_visto_cae_en_otros` | caso borde 5 |
| `test_model_family_usa_prefijo_mas_largo` | consistencia con `cost_scoring.model_family` |
| `test_input_price_none_es_cero_explicito` | |
| `test_description_none_no_crashea` | |
| `test_build_features_es_determinista` | mismo input ⇒ misma lista de tuplas |

**`backend/tests/test_plan242_cost_model.py`** (álgebra + persistencia + predicción, sin DB):

| Caso | Qué verifica |
|---|---|
| `test_solve_linear_sistema_2x2_conocido` | contra solución calculada a mano |
| `test_solve_linear_requiere_pivoteo` | matriz con 0 en la diagonal que sin pivoteo fallaría |
| `test_solve_linear_matriz_singular_lanza` | `SingularMatrixError` |
| `test_solve_linear_no_muta_el_argumento` | `A` y `b` intactos después de llamar |
| `test_fit_ridge_recupera_relacion_lineal_sintetica` | `y = 2*x1 + 3*x2` con λ pequeño ⇒ pesos ≈ (2,3) con `rel_tol=0.05` |
| `test_fit_ridge_lambda_grande_encoge_pesos` | λ=1000 ⇒ `|w|` menor que con λ=1 |
| `test_fit_ridge_columna_constante_sd_uno` | caso borde 4, sin `ZeroDivisionError` |
| `test_fit_ridge_no_normaliza_los_onehot` | `mu[j]==0.0` y `sd[j]==1.0` para `j >= n_continuous` |
| **`[v2]`** `test_continuo_ausente_aporta_cero_no_la_media` | **C7**: el caso que v1 tenía al revés. Verifica el comportamiento **real** de `_predict_log` (ausente ⇒ aporte 0), no el del comentario equivocado. El caso de v1 (`test_predict_log_usa_la_media_para_continuos_ausentes`) habría quedado **rojo sin arreglo posible** |
| **`[v2]`** `test_build_features_emite_siempre_los_5_continuos_invariante_del_modelo` | **C7**: fija el invariante del que depende la corrección del modelo — si alguien omite un continuo, el modelo se desalinea **en silencio** |
| `test_intervalo_conformal_ordena_p10_p50_p90` | punto 5 de §F3.6 |
| `test_intervalo_nunca_negativo` | `max(0.0, ...)` |
| `test_calibracion_menor_a_10_filas_usa_fallback_y_marca_candidate` | punto 6 de §F3.6 |
| `test_save_load_roundtrip` | los 4 vectores y los 3 cuantiles vuelven idénticos |
| `test_save_es_atomico_usa_replace` | monkeypatch de `os.replace`: se llama exactamente 1 vez |
| `test_load_archivo_inexistente_devuelve_none` | caso 1 de §F3.7 |
| `test_load_json_corrupto_devuelve_none_y_loguea` | caso 2 |
| `test_load_falta_clave_obligatoria_devuelve_none` | caso 3 (parametrizado sobre las 8 claves) |
| `test_load_schema_version_desconocida_devuelve_none` | caso 4 |
| `test_load_longitudes_inconsistentes_devuelve_none` | caso 5 |
| `test_load_nan_o_inf_devuelve_none` | caso 6 |
| `test_load_nunca_lanza_excepcion` | los 7 casos, ninguno propaga |
| `test_fallback_L1_cuando_modelo_activo_y_muestras_suficientes` | `source == "model"` |
| `test_fallback_L2_cuando_modelo_candidate` | `source == "cohort_median"` |
| `test_fallback_L3_cuando_cohorte_menor_a_5` | `source == "global_median"` |
| `test_fallback_L4_cuando_no_hay_nada` | `source == "heuristic"` |
| `test_fallback_L4_sin_precios_devuelve_ceros_sin_lanzar` | último recurso |
| `test_confidence_por_n_samples_200_60_menos` | los 3 umbrales de L1 |
| `test_prediccion_copilot_es_no_facturable_y_lo_dice` | **G7**: `billable is False` y la 1ª explicación menciona "suscripción plana" |
| `test_cost_kind_de_una_prediccion_es_siempre_forecast` | **G6** |
| `test_forecast_no_entra_en_billable` | `cost_analytics._billable("forecast") is False` |
| `test_explanation_L1_trae_5_features_con_signo` | |
| `test_train_con_pocas_muestras_persiste_medianas_igual` | caso borde 1 |
| `test_train_captura_singular_y_no_crashea` | caso borde 3 |
| `test_entrenamiento_excluye_estimated_nominal_y_unknown` | sólo `reported` entra |
| `test_entrenamiento_excluye_github_copilot` | **G7** explícito |
| `test_train_no_abre_red_ni_llm` | monkeypatch que revienta si se llama `requests`/`socket`/`subprocess` |
| `test_prediccion_es_determinista_50_corridas` | |

**`backend/tests/test_plan242_cost_model_perf.py`**:

| Caso | Qué verifica |
|---|---|
| `test_entrena_20000_filas_en_menos_de_2s` | **KPI-7**: 20.000 filas sintéticas con vocabulario de 10 `agent_type` y 6 `model_family`; `time.perf_counter()` alrededor de `fit_ridge` ⇒ **< 2,0 s** |
| `test_predice_1000_veces_en_menos_de_1s` | la predicción no puede ser el cuello de botella de la UI |

**Escape hatch declarado — es una regla cerrada, no una licencia para improvisar:** si en la máquina del operador `test_entrena_20000_filas_en_menos_de_2s` supera los 2,0 s, la implementación debe bajar `_TRAIN_MAX_ROWS` de `20000` a `8000` (tomando las **8000 filas más recientes** por `started_at` descendente) y **dejar el test tal cual, con el mismo umbral de 2,0 s pero generando 8000 filas**. No se relaja el umbral: se reduce la carga, y el cambio queda visible en una constante con nombre.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_features.py -q
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_model.py -q
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_model_perf.py -q
```

#### F3.11 Aceptación (BINARIA)

1. Los 3 archivos de test en **0 failed** (**`[v2]`** cobertura: 16 + **37** + **3** casos — v1 decía 38 donde la tabla lista 37, y perf pasa de 2 a 3 casos por el desdoble del KPI-7).
2. **KPI-7** verde (`test_entrena_20000_filas_en_menos_de_2s`).
3. `grep -cE "^(import|from) (numpy|sklearn|scipy|pandas)" services/cost_model.py` ⇒ **0** (y el test AST de §F8.3 en verde).
4. Los 3 archivos registrados en `run_harness_tests.sh` y `.ps1`; ratchet meta verde.

**Flag que la protege:** `STACKY_COST_FORECAST_ENABLED`, **default ON**; y `STACKY_COST_MODEL_MIN_SAMPLES` (int, default 30). Ninguna excepción dura aplica: el entrenamiento no invoca LLM, no abre red, no consume tokens ociosos (sólo corre on-demand o con debounce, §F5) y no es irreversible (borrar `cost_model.json` revierte todo).
**Impacto por runtime:** `codex_cli` y `claude_code_cli` son las **únicas** fuentes de entrenamiento (son las que reportan costo real). `github_copilot` **no entrena** y su predicción se emite igual, marcada `billable=False` con el rótulo de suscripción plana. Fallback por runtime: si un runtime no tiene ninguna fila `reported`, su cohorte no existe y sus predicciones caen a L3 (mediana global) o L4 (heurística), siempre con la razón visible.
**Trabajo del operador: ninguno** (el primer entrenamiento se dispara solo por el post-hook de F5; también hay un botón manual en F7).

---

### F4 — Backtesting honesto y gate de promoción (`cost_model_eval.py`) — el corazón anti-falso-verde

**Objetivo (1 frase):** medir el modelo contra el futuro que no vio y **rechazarlo** si no le gana al baseline trivial.
**Valor:** sin este gate, el plan entrega un número inventado con cara de ciencia. Con él, el sistema prefiere decir "uso la mediana" antes que mentir.

#### F4.1 Archivos

| Acción | Ruta exacta |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/cost_model_eval.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_model_eval.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` |

#### F4.2 Split TEMPORAL (jamás aleatorio) — definición exacta

```python
_TRAIN_FRAC = 0.70
_CALIB_FRAC = 0.15
# el resto (0.15) es TEST
_MIN_SPLIT_ROWS = 5      # minimo por particion
_MIN_TEST_ROWS = 10      # minimo para que el gate de promocion pueda opinar


def temporal_split(rows) -> tuple[list, list, list] | None:
    """rows: list[TrainingRow] con .started_at no nulo.
    Devuelve (train, calib, test) o None si alguna particion es demasiado chica.

    NUNCA se baraja. Entrenar con lo viejo, calibrar con lo del medio, evaluar
    con lo MAS NUEVO: es la unica forma de simular el uso real (predecir el
    futuro). Un split aleatorio filtraria informacion del futuro al pasado y
    daria un MAE optimista y FALSO.
    """
    ordenadas = sorted(rows, key=lambda r: (r.started_at, r.execution_id))  # desempate DETERMINISTA
    n = len(ordenadas)
    n_train = int(n * _TRAIN_FRAC)
    n_calib = int(n * _CALIB_FRAC)
    train = ordenadas[:n_train]
    calib = ordenadas[n_train:n_train + n_calib]
    test  = ordenadas[n_train + n_calib:]
    if len(train) < _MIN_SPLIT_ROWS or len(calib) < _MIN_SPLIT_ROWS or len(test) < _MIN_SPLIT_ROWS:
        return None
    return train, calib, test
```

#### F4.3 Métricas — fórmulas exactas con sus guardas

```python
@dataclass
class EvalReport:
    n_test: int
    mae: float                  # USD
    mape: float | None          # fraccion (0.38 == 38%); None si no hay filas evaluables
    mape_skipped: int           # filas descartadas por y_true demasiado chico
    rmsle: float
    coverage: float             # fraccion de y_true dentro de [p10, p90]
    baseline_mae: float         # MAE de predecir SIEMPRE la mediana global del train
    improvement: float          # (baseline_mae - mae) / baseline_mae ; negativo si es peor
    promoted: bool
    reject_reasons: list[str]   # vacio si promoted is True
```

**`mae(y_true, y_pred)`** = `sum(abs(t - p)) / n`. Si `n == 0` ⇒ `float("inf")` (nunca 0: un MAE de 0 con 0 filas sería el falso verde perfecto).

**`mape(y_true, y_pred, eps=1e-6)`** — guarda de división por cero explícita:
```
pares = [(t, p) for t, p in zip(y_true, y_pred) if abs(t) >= eps]
skipped = n - len(pares)
si pares esta vacio -> (None, skipped)
mape = sum(abs(t - p)/abs(t) for t, p in pares) / len(pares)
```

**`rmsle(y_true, y_pred)`** = `sqrt( mean( (log1p(max(0,t)) - log1p(max(0,p)))**2 ) )`. Los `max(0, ·)` evitan `log1p` de negativos (dato corrupto).

**`interval_coverage(y_true, p10s, p90s)`** = `sum(1 for t, lo, hi in zip(...) if lo <= t <= hi) / n`. Bordes **inclusivos**. Si `n == 0` ⇒ `0.0`.

**`baseline_median_mae(train, test)`** = `mae([r.cost_usd for r in test], [mediana_del_train] * len(test))`, donde `mediana_del_train = statistics.median([r.cost_usd for r in train])`.

#### F4.4 Gate de promoción — la regla que puede matar al modelo

```python
_MIN_IMPROVEMENT = 0.05      # el modelo debe ganarle al baseline por al menos 5%
_COVERAGE_MIN = 0.60
_COVERAGE_MAX = 0.95


def should_promote(report: EvalReport) -> tuple[bool, list[str]]:
    razones = []
    if report.n_test < _MIN_TEST_ROWS:
        razones.append(f"set de test insuficiente: {report.n_test} < {_MIN_TEST_ROWS} filas")
    if not math.isfinite(report.mae):
        razones.append("MAE no finito")
    if report.improvement < _MIN_IMPROVEMENT:
        razones.append(
            f"no le gana al baseline por margen suficiente: MAE {report.mae:.4f} vs "
            f"baseline {report.baseline_mae:.4f} (mejora {report.improvement*100:.1f}%, "
            f"se exige >= {_MIN_IMPROVEMENT*100:.0f}%)")
    if not (_COVERAGE_MIN <= report.coverage <= _COVERAGE_MAX):
        razones.append(
            f"cobertura P10-P90 fuera de rango: {report.coverage:.2f} "
            f"(se exige entre {_COVERAGE_MIN} y {_COVERAGE_MAX})")
    return (len(razones) == 0), razones
```

**Consecuencia operativa, no negociable:** si `should_promote` devuelve `False`, `train()` guarda el JSON con `status="candidate"` y `predict()` **NUNCA** usa L1 con ese modelo — cae directo a L2. El operador ve en `/api/metrics/cost-model-status` el estado `candidate` **con las razones de rechazo textuales**. Un modelo malo es visible, no invisible.

**Por qué se exige 5 % y no "mejor que":** con `n_test` chico, una mejora del 1 % es ruido. El margen del 5 % convierte el gate en una decisión y no en un sorteo.

**Por qué la cobertura tiene tope superior (0,95) y no sólo piso:** un intervalo que cubre el 99 % es un intervalo inútilmente ancho (`p10=0.001, p90=50`) que técnicamente "acierta siempre". El tope castiga la falsa seguridad tanto como el piso castiga la falsa precisión.

#### F4.5 [ADICIÓN ARQUITECTO] Modelo anterior recuperable — snapshot, comparación y rollback HITL

**Resuelve C16.** El gate de §F4.4 es una regla estadística, no una decisión humana. Un modelo puede pasarlo y aun así ser peor en producción (deriva de cohortes, un mes atípico, un runtime que dominó el histórico reciente). Y sin snapshot, **promover es destruir**: `save_model` pisa el vigente con `os.replace` y no queda a qué volver. Eso convierte al 242 en el único componente del sistema que **reemplaza algo sin que el operador pueda verlo, compararlo ni deshacerlo** — justo lo que G15 prohíbe en espíritu. Las tres piezas son **reuso puro** de lo que F3/F4 ya construyen: cero queries nuevas, cero álgebra nueva.

**(1) Snapshot antes de pisar.** `save_model()` gana un paso previo dentro de la misma escritura atómica:
```python
_PREV_MODEL_FILENAME = "cost_model.prev.json"

def save_model(model, *, keep_previous: bool = True) -> None:
    ruta = data_dir() / _MODEL_FILENAME
    if keep_previous and ruta.exists():
        try:
            os.replace(ruta, data_dir() / _PREV_MODEL_FILENAME)
        except OSError:      # disco lleno / archivo abierto por el operador en Windows
            logger.warning("cost_model: sin snapshot previo; se promueve igual")
    # ... escritura atomica .tmp -> os.replace(tmp, ruta), EXACTAMENTE como en F3.7
```
**Un** nivel de historia, no N: un archivo extra de decenas de KB, y borrarlo revierte. `load_model()` no cambia; se agrega `load_previous_model()` con **las mismas 7 guardas** de §F3.7 (devuelve `None`, nunca lanza).

**(2) Comparar contra el vigente, no sólo contra el baseline.** `EvalReport` gana dos campos **con default** (100 % aditivo):
```python
    incumbent_mae: float | None = None    # MAE del modelo VIGENTE sobre EL MISMO set de test
    beats_incumbent: bool | None = None   # None si no habia vigente (primera promocion)
```
Se calcula corriendo `_predict_log` del modelo previo sobre el **mismo** `test` del split de §F4.2 — no se re-parte, no se re-entrena, no hay query nueva. `should_promote` **no cambia su regla** (sigue siendo 5 % contra el baseline + cobertura en rango), pero si `beats_incumbent is False` agrega a `reject_reasons`:
```
f"le gana al baseline pero PIERDE contra el modelo vigente: MAE {mae:.4f} vs {incumbent_mae:.4f}"
```
y **no promueve**. Un modelo que empeora respecto del que ya está no entra jamás, aunque supere al baseline trivial.

**(3) La palanca del operador.** Una flag más (la **octava**) y un endpoint hermano de los 6 de §F6.2:

| Key | Tipo | Default | Justificación del default |
|---|---|---|---|
| `STACKY_COST_MODEL_AUTOPROMOTE_ENABLED` | bool | **ON** | Read-only sobre datos ya persistidos; escribe **un** JSON reversible **con snapshot**. Ninguna de las 4 excepciones duras aplica. En **OFF**, todo entrenamiento queda en `candidate` y **promueve el operador a mano** — la variante más conservadora, disponible sin tocar código. |

| Método | Ruta | Función Python | Flag |
|---|---|---|---|
| POST | `/api/metrics/cost-model-promote` | `def cost_model_promote()` | `STACKY_COST_FORECAST_ENABLED` |

Body: `{"action": "promote"}` (fuerza `candidate` → `active`, **sólo** si el modelo existe y carga sin error) o `{"action": "rollback"}` (restaura `cost_model.prev.json`, con el mismo `.tmp` + `os.replace`). Otro `action` ⇒ `{"ok": false, "error": "invalid_action"}, 400`. Sin `.prev.json` ⇒ `{"ok": false, "error": "no_previous_model"}, 200` — no es un error HTTP, es el estado legítimo del día 1.

`/api/metrics/cost-model-status` gana, aditivos: `"previous_present"`, `"previous_trained_at"`, `"previous_eval"`, `"beats_incumbent"`, `"autopromote_enabled"`.

**UI — dentro de `CostForecastPanel`, sin componente nuevo:** una línea y dos botones. `"Modelo vigente: entrenado el {trained_at}, MAE {mae} USD. Anterior: {previous_trained_at}, MAE {incumbent_mae} USD."` + `[Promover el candidato]` (habilitado sólo si `status === "candidate"`) + `[Volver al anterior]` (sólo si `previous_present`). Si `beats_incumbent === false`, promover pide confirmación con el **`Dialog` canónico (Plan 164)** — nunca `window.confirm`.

**Tests — +6 casos en `test_plan242_cost_model_eval.py` (22 ⇒ 28):**

| Caso | Qué verifica |
|---|---|
| `test_save_model_guarda_snapshot_previo` | tras 2 `save_model`, existen `cost_model.json` y `cost_model.prev.json`, con contenidos distintos |
| `test_primera_promocion_sin_previo_no_falla` | `beats_incumbent is None`; no se inventa un `.prev` |
| `test_no_promueve_si_pierde_contra_el_vigente` | gana al baseline pero pierde al vigente ⇒ `promoted is False` y la razón menciona "modelo vigente" |
| `test_rollback_restaura_el_anterior_byte_a_byte` | `json.load` del restaurado == `json.load` del previo |
| `test_rollback_sin_previo_devuelve_no_previous_model` | no escribe nada |
| `test_previous_corrupto_no_rompe_status` | `.prev.json` truncado ⇒ `previous_present: false` y `/cost-model-status` sigue 200 |

**Cumplimiento de los rieles duros:**
- **3 runtimes:** es un archivo JSON; no toca ningún runtime. Copilot sigue fuera del entrenamiento (G7) y su forecast sigue `billable=False` con cualquiera de los dos modelos. Fallback explícito: sin `.prev`, los campos van en `null` y el botón queda deshabilitado — nunca un cero disfrazado de dato.
- **Cero trabajo del operador:** snapshot automático, flag ON, comparación calculada sola. Los dos botones son **opt-in**: si nunca los mira, el sistema se comporta igual que sin esta adición, sólo que con respaldo.
- **Human-in-the-loop:** es justamente la pieza que le devuelve la decisión. Amplifica (le muestra una comparación que hoy no existe) sin reemplazarlo, y con la flag en OFF el humano es el **único** que promueve.
- **Mono-operador sin auth:** ningún rol, ningún 403. Un botón, un endpoint.
- **No degradar:** un `os.replace` extra por entrenamiento (microsegundos) y un archivo del tamaño del modelo. Con la flag en OFF, el comportamiento es el del F4 original.
- **Backward-compatible:** los 2 campos de `EvalReport` tienen default `None`; `save_model` gana un kwarg con default; el endpoint es apéndice; `/cost-model-status` sólo agrega claves.
- **Reuso:** `save_model` / `load_model` / `_predict_log` / `temporal_split` / `EvalReport` / `Dialog` canónico. No inventa nada.

**`[ADICIÓN ARQUITECTO] bis` — brazo de control permanente (una línea, alto retorno).** En §F5.4, `calibration()` debe calcular **siempre** el nivel **L4** en paralelo, aunque se muestre el resultado de L1, y registrarlo en la línea de apertura del ledger como `"heuristic_p50_usd"`. Sin ese brazo, la calibración dice *"el modelo se equivoca 0,09 USD"* sin poder responder la única pregunta que importa: **"¿y la heurística de FA-33 que ya teníamos se equivocaba más o menos?"**. El payload de `by_source` ya tiene la clave `heuristic`; sólo falta declarar que se computa siempre. Es lo que hace que el 242 pueda **probar** que valió la pena, en vez de afirmarlo.

**Huella de regresión** — se registra en `Stacky Agents/docs/sistema/error_fingerprints.json` (C19 del checklist; el archivo existe y tiene 23 entradas):
`"modelo de costo promovido con n_test chico ⇒ MAE optimista y estimador peor que el anterior, sin forma de volver"` · **síntoma:** `calibration().by_source["model"].mae_usd` sube mientras `/cost-model-status` dice `active` · **detección:** `beats_incumbent is False` · **guard_test:** `test_no_promueve_si_pierde_contra_el_vigente` · **remedio:** `POST /api/metrics/cost-model-promote {"action":"rollback"}`.

---

#### F4.6 Casos borde enumerados

1. `rows` con menos de `_MIN_SPLIT_ROWS * 3` filas ⇒ `temporal_split` ⇒ `None` ⇒ `train()` no promueve, razón `"histórico insuficiente para hacer un split temporal"`.
2. Todos los `cost_usd` del test iguales a 0 ⇒ `mape` ⇒ `(None, n)` con `mape_skipped = n`; el gate **no** usa MAPE, así que no bloquea.
3. `baseline_mae == 0` (test con un solo valor idéntico a la mediana del train) ⇒ `improvement` sería división por cero: se define `improvement = 0.0` cuando `baseline_mae == 0` (y por lo tanto **no promueve**, porque `0.0 < 0.05`). Comportamiento conservador y explícito.
4. Modelo perfecto (`mae == 0`) ⇒ `improvement == 1.0` ⇒ promueve, **si además** la cobertura cae en rango.
5. Modelo peor que el baseline ⇒ `improvement` negativo ⇒ **no promueve** (test dedicado).

#### F4.7 Tests PRIMERO — `backend/tests/test_plan242_cost_model_eval.py`

> **`[v2]`** A los 22 casos de abajo se suman los **6** de la [ADICIÓN ARQUITECTO] §F4.5 ⇒ **28** en total.

| Caso | Qué verifica |
|---|---|
| `test_split_es_temporal_no_aleatorio` | las filas de `test` tienen `started_at` **todas** ≥ que las de `train` |
| `test_split_desempata_por_execution_id` | determinismo con `started_at` repetido |
| `test_split_proporciones_70_15_15` | tamaños exactos con n=100 |
| `test_split_devuelve_none_si_alguna_particion_es_chica` | caso borde 1 |
| `test_mae_conocido_a_mano` | valor calculado manualmente |
| `test_mae_lista_vacia_es_infinito_no_cero` | anti-falso-verde |
| `test_mape_salta_y_true_cercanos_a_cero` | caso borde 2, reporta `mape_skipped` |
| `test_mape_todas_salteadas_devuelve_none` | |
| `test_rmsle_conocido_a_mano` | |
| `test_rmsle_tolera_negativos_con_max_cero` | |
| `test_coverage_bordes_inclusivos` | `t == p10` y `t == p90` cuentan como cubiertos |
| `test_coverage_lista_vacia_es_cero` | |
| `test_baseline_es_la_mediana_del_train` | no del test (eso sería filtrar el futuro) |
| `test_improvement_baseline_cero_es_cero_no_lanza` | caso borde 3 |
| `test_promueve_cuando_gana` | **KPI-5**: datos sintéticos donde `y = 2*x + ruido pequeño`; el modelo gana ⇒ `promoted is True` |
| `test_NO_promueve_cuando_pierde` | **KPI-5**: `y` es ruido puro **sin relación** con las features ⇒ `promoted is False` y `reject_reasons` menciona el baseline |
| `test_NO_promueve_con_test_menor_a_10_filas` | |
| `test_cobertura_fuera_de_rango_bloquea_promocion` | **KPI-6**: cobertura 0,99 ⇒ rechaza; cobertura 0,30 ⇒ rechaza |
| `test_reject_reasons_vacio_solo_si_promoted` | invariante |
| `test_modelo_candidate_no_se_usa_en_predict` | integración con F3: `predict()` ⇒ `source != "model"` |
| `test_modelo_candidate_igual_persiste_cohort_medians` | L2 sigue disponible |
| `test_eval_es_determinista` | 20 corridas ⇒ mismo `EvalReport` |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_model_eval.py -q
```

#### F4.8 Aceptación (BINARIA)

1. **`[v2]`** `0 failed`, con los **28** casos de cobertura (22 de v1 + 6 de la ADICIÓN §F4.5).
2. **KPI-5** y **KPI-6** verdes por nombre de caso — en particular `test_NO_promueve_cuando_pierde`, que es el que impide el falso verde.
3. Registrado en `run_harness_tests.sh` y `.ps1`; ratchet meta verde.

**Flag que la protege:** la misma `STACKY_COST_FORECAST_ENABLED` (el evaluador no tiene flag propia: es parte inseparable del entrenamiento; un modelo sin gate **no debe poder existir**).
**Impacto por runtime:** el evaluador opera sobre filas ya filtradas a `reported` (o sea `codex_cli` y `claude_code_cli`). Si un solo runtime tiene datos, el split se hace igual y el modelo aprendido será específico de ese runtime — lo cual es correcto y queda reflejado en `n_samples`. `github_copilot` no participa. Fallback en los tres: sin split posible ⇒ `candidate` ⇒ L2/L3/L4.
**Trabajo del operador: ninguno.**

---

### F5 — Ledger forecast-vs-real (cierre del lazo de aprendizaje)

**Objetivo (1 frase):** registrar cada predicción mostrada y cerrarla con el costo real al terminar la ejecución, para poder medir —y mostrar— qué tan bien estima el estimador.
**Valor:** es lo que convierte "hicimos un modelo" en "sabemos si el modelo sirve". Sin esto, el KPI-8 no existe y el sistema no aprende de verdad.

#### F5.1 Decisión: JSONL en el data dir, NO tabla nueva

| Criterio | JSONL en `data_dir()` | Tabla nueva + alembic |
|---|---|---|
| Reversibilidad | borrar 1 archivo | migración de bajada, riesgo real |
| Migración | **ninguna** | `alembic` obligatorio |
| Volumen esperado | mono-operador, ~decenas de filas/día | sobredimensionado |
| Patrón de acceso | **append-only** + lectura completa esporádica | innecesario para esto |
| Precedente en el repo | `data_dir()` ya se usa así (`services/ado_feedback.py:10`, `services/ado_identity.py:32`) | — |

**Se elige JSONL.** Ruta: `runtime_paths.data_dir() / "cost_forecast_ledger.jsonl"`.

> **`[v2]` RESUELTO (C5, verificado 2026-07-26) — hay patrón de la casa y hay que calcarlo.** v1 dejaba esto
> como *"A VERIFICAR: … conviene seguir su estilo"*. La respuesta es **sí, y son cuatro**:
> `services/ci_run_ledger.py` (Plan 191), `services/sql_exec_ledger.py`, `services/env_apply_ledger.py`,
> `services/ado_edit_ledger.py` — todos declarados como *"patrón de la casa: `deploy_store.py:98-158`"*.
> El molde es **idéntico en los cuatro** y el diseño de v1 se apartaba de él en tres puntos, los tres a peor:
>
> | | Patrón de la casa (`ci_run_ledger.py`) | v1 del 242 | Veredicto |
> |---|---|---|---|
> | Concurrencia | **`_LOCK = threading.Lock()`** (`:19`) alrededor de toda lectura y escritura | **sin lock** | ✗ `record_forecast` corre en el hilo HTTP y `close_forecast` en el del post-hook: **escriben al mismo archivo a la vez** |
> | Retención | `MAX_ROWS = 500` (`:18`), se conservan las **más nuevas** por reescritura atómica | 50.000 líneas + rotación a `.1` | ✗ 100× más grande, y `calibration` lee **sólo** el activo ⇒ al rotar se pierde la ventana de golpe |
> | Cerrar un registro | **`update_run_status`** (`:103`): actualiza **en su lugar** bajo `_LOCK`, con `_write_rows` atómico | segunda línea `"actual"` + emparejamiento en memoria | ✗ obliga a releer y parsear **todo** el ledger en **cada** fin de ejecución |
> | Contra fuga de secretos | **allowlist `ENTRY_FIELDS`** (`:22-27`): las claves fuera del contrato **se descartan al escribir** | sin allowlist | ✗ |
>
> **Decisión: `cost_forecast_ledger.py` calca `ci_run_ledger.py`.** Mismo `_LOCK`, mismo `MAX_ROWS = 500`
> (un mono-operador hace decenas de forecasts por día: 500 cubre semanas y hace que `calibration` sea
> O(500) en vez de O(50.000)), mismos `_read_rows`/`_write_rows` con `tmp.replace(path)`, misma allowlist
> `ENTRY_FIELDS`, y **una fila por forecast que se actualiza al cerrar** — no dos líneas que hay que
> emparejar. Esto elimina de un saque la rotación, el `skipped_lines` como mecanismo de supervivencia y el
> rescan por ejecución. Leer primero:
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> sed -n '1,130p' services/ci_run_ledger.py
> ```
> No se agrega ninguna dependencia ni ninguna tabla, igual que en v1.

#### F5.2 Archivos

| Acción | Ruta exacta |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/cost_forecast_ledger.py` |
| **CREAR** | `Stacky Agents/backend/services/cost_model_hooks.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_forecast_ledger.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_hooks.py` |
| **EDITAR** | `Stacky Agents/backend/app.py` (una línea: registrar el hook en `create_app`) |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` |

#### F5.3 Formato del ledger (append-only, 2 tipos de línea)

**Línea de apertura** (se escribe cuando se produce una predicción):
```json
{"kind":"forecast","forecast_id":"9f2c…","ts":"2026-07-25T14:03:11Z","ticket_id":812,
 "execution_id":null,"agent_type":"developer","runtime":"claude_code_cli",
 "model":"claude-sonnet-5","p10_usd":0.18,"p50_usd":0.34,"p90_usd":0.74,
 "source":"model","confidence":"media","n_samples":148,"billable":true}
```

**Línea de cierre** (se escribe en el post-hook, al terminar la ejecución):
```json
{"kind":"actual","forecast_id":"9f2c…","ts":"2026-07-25T14:19:02Z",
 "execution_id":4471,"actual_usd":0.41,"actual_cost_kind":"reported",
 "final_status":"completed","abs_error_usd":0.07,"inside_interval":true}
```

**Nunca se reescribe una línea.** El cierre es una línea nueva. El emparejamiento se hace en memoria por `forecast_id`.

#### F5.4 API del módulo

```python
_LEDGER_FILENAME = "cost_forecast_ledger.jsonl"
# [v2] C5 — calca ci_run_ledger.py (patron de la casa, Plan 191):
MAX_ROWS = 500                   # retencion dura: se conservan las 500 MAS NUEVAS
_LOCK = threading.Lock()         # record_forecast corre en el hilo HTTP y close_forecast
                                 # en el del post-hook: SIN esto escriben a la vez.
ENTRY_FIELDS: tuple[str, ...] = (   # allowlist: lo que no este aca NO se persiste
    "forecast_id", "ts", "ticket_id", "execution_id", "agent_type", "runtime", "model",
    "p10_usd", "p50_usd", "p90_usd", "heuristic_p50_usd", "source", "confidence",
    "n_samples", "billable", "actual_usd", "actual_cost_kind", "final_status",
    "abs_error_usd", "inside_interval", "closed_at",
)
# NO hay _MAX_LEDGER_LINES ni _ROTATED_SUFFIX: v1 proponia 50.000 lineas con rotacion a
# ".1", 100x el cap de la casa, y ademas `calibration` leia solo el archivo activo => al
# rotar se perdia la ventana entera de golpe. Con 500 filas no hace falta rotar nada.


def record_forecast(*, ticket_id: int | None, agent_type: str | None,
                    runtime: str | None, model: str | None,
                    prediction) -> str: ...
    # Devuelve forecast_id (uuid4().hex, stdlib). Si la escritura falla (OSError),
    # loguea warning y devuelve "" — NUNCA propaga: una prediccion no puede
    # romper la pantalla por un problema de disco.

def bind_execution(forecast_id: str, execution_id: int) -> bool: ...
    # Escribe una linea {"kind":"bind","forecast_id":...,"execution_id":...}
    # para asociar una prediccion previa a la ejecucion que finalmente se lanzo.

def close_forecast(*, execution_id: int, actual_usd: float | None,
                   actual_cost_kind: str, final_status: str) -> bool: ...
    # Busca el forecast_id ligado a ese execution_id (por linea "bind" o por la
    # linea de apertura si ya traia execution_id). Si no hay ninguno, devuelve
    # False SIN escribir (no se inventan pares).

def calibration(days: int = 30) -> dict: ...
def _rotate_if_needed() -> None: ...
```

**`calibration(days)` devuelve exactamente:**
```python
{
  "n_forecasts": int,          # aperturas dentro de la ventana
  "n_pairs": int,              # aperturas CON cierre
  "n_open": int,               # aperturas sin cierre (todavia corriendo o abandonadas)
  "mae_usd": float | None,     # None si n_pairs == 0
  "mape": float | None,        # misma guarda de eps que F4
  "coverage": float | None,    # fraccion de reales dentro de [p10, p90]
  "bias_usd": float | None,    # media de (real - p50): positivo = subestimamos
  "by_source": {"model": {"n": int, "mae_usd": float|None, "coverage": float|None},
                 "cohort_median": {...}, "global_median": {...}, "heuristic": {...}},
  "skipped_lines": int,        # lineas corruptas salteadas
  "window_days": int,
}
```

**Robustez obligatoria:**
- Línea que no parsea como JSON ⇒ se saltea y suma a `skipped_lines`. **Nunca** aborta la lectura.
- Línea sin `kind` o con `kind` desconocido ⇒ ídem.
- Archivo inexistente ⇒ payload con todos los contadores en 0 y `mae_usd=None`.
- `_rotate_if_needed()`: si el archivo supera `_MAX_LEDGER_LINES`, se renombra a `cost_forecast_ledger.jsonl.1` (pisando el anterior si existe) y se empieza uno nuevo. La rotación es **determinista** y sólo se evalúa en `record_forecast`, nunca en lectura.
- Cierres con `actual_usd is None` (ejecución sin costo registrado) ⇒ **se escribe la línea igual** con `abs_error_usd: null` e `inside_interval: null`, y `calibration` los cuenta en `n_pairs` pero los excluye de MAE/MAPE/coverage. Ocultarlos sería sesgar la calibración a favor.

#### F5.5 `cost_model_hooks.py` — el chokepoint correcto

El punto de enganche runtime-agnóstico verificado es **`services/ticket_status.on_execution_end`** (`backend/services/ticket_status.py:231`), que al final ejecuta `_run_post_hooks(...)` (`:281`). Los hooks se registran con **`register_post_hook(fn)`** (`backend/services/ticket_status.py:307`) y la firma esperada, documentada en su docstring, es:

```python
fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)
```

**NO se usa `agent_completion.run_on`.**

> **`[v2]` ⛔ CORRECCIÓN CRÍTICA (C4) — "no bloquea" era una mala lectura del docstring.** v1 escribía acá
> *"Los hooks nunca bloquean la ejecución principal: los errores se loguean (`ticket_status.py:313`)"*,
> mezclando dos cosas distintas. `_run_post_hooks` (**`ticket_status.py:325`**, llamado desde `:279`) es un
> `for` **síncrono**:
> ```python
> for hook in _POST_HOOKS:
>     try:
>         hook(**kwargs)          # ← EN LÍNEA, en el hilo del runner
>     except Exception as exc:
>         logger.warning(...)     # ← esto es lo ÚNICO que garantiza :313/:330
> ```
> O sea: **los errores no se propagan, pero el tiempo sí se paga.**
>
> Y la regla de la casa es explícita y está escrita — `services/completion_dispatcher.py:3-6` (Plan 208 F0):
> > *"El post-hook que se registra en `ticket_status.register_post_hook` **SOLO encola (O(1)) y retorna**:
> > todo el trabajo real (red, DB) corre en un daemon de fondo, para que una falla o lentitud jamás demore
> > la completación ni la respuesta HTTP."*
>
> `cost_model.train()` arranca con `collect_training_rows` → `load_records(CostFilters(days=365))`, que es
> **una query de hasta 20.000 filas de `AgentExecution` con la columna `output` (TEXT) completa**. Correrlo
> en línea viola la regla frontalmente. Ver el fix en el código de abajo.

```python
"""Plan 242 F5 — Cierre del lazo: post-hook de fin de ejecucion."""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("stacky.services.cost_model_hooks")

_AUTOTRAIN_MIN_INTERVAL_S = 1800.0     # debounce duro: como mucho 1 entrenamiento cada 30 min
_lock = threading.Lock()
_runs_since_train = 0
_last_train_ts = 0.0
_installed = False        # [v2] C9 — OBLIGATORIO: register() hace `global _installed`.
                          # v1 nunca lo inicializaba => NameError en la PRIMERA llamada.
_training = False         # [v2] C4 — evita dos entrenamientos en paralelo.


def _on_execution_end_cost(*, ticket_id=None, execution_id=None, final_status=None,
                           agent_type=None, error=None, **kwargs) -> None:
    """NUNCA propaga una excepcion: si algo falla, se loguea y se sigue."""
    try:
        _close_forecast_for(execution_id, final_status)
    except Exception:
        logger.exception("cost hooks: fallo al cerrar el forecast de %s", execution_id)
    try:
        _maybe_autotrain()
    except Exception:
        logger.exception("cost hooks: fallo el autotrain")


def _maybe_autotrain() -> None:
    global _runs_since_train, _last_train_ts
    from config import config as cfg
    if not getattr(cfg, "STACKY_COST_MODEL_AUTOTRAIN_ENABLED", False):
        return
    every_n = int(getattr(cfg, "STACKY_COST_MODEL_AUTOTRAIN_EVERY_N", 10) or 10)
    with _lock:
        _runs_since_train += 1
        if _runs_since_train < every_n:
            return
        ahora = time.monotonic()
        if ahora - _last_train_ts < _AUTOTRAIN_MIN_INTERVAL_S:
            return                    # debounce: NO se resetea el contador, se reintenta luego
        _runs_since_train = 0
        _last_train_ts = ahora
    # [v2] C4 — REGLA DE LA CASA (services/completion_dispatcher.py:3-6, Plan 208 F0):
    # el post-hook SOLO encola (O(1)) y retorna. train() hace UNA query de hasta
    # 20.000 filas de AgentExecution (columna `output` TEXT completa) + el ajuste.
    # JAMAS en linea: se despacha a un daemon y el hook vuelve enseguida.
    threading.Thread(target=_train_in_background, name="cost-autotrain",
                     daemon=True).start()


def _train_in_background() -> None:
    """Corre FUERA del hilo del runner. Nunca propaga. Nunca se solapa consigo mismo."""
    global _training
    with _lock:
        if _training:
            logger.info("cost hooks: ya hay un autotrain en curso; se omite")
            return
        _training = True
    try:
        from services import cost_model
        resultado = cost_model.train()
        logger.info("cost hooks: autotrain -> trained=%s status=%s n=%s",
                    resultado.trained, resultado.status, resultado.n_samples)
    except Exception:
        logger.exception("cost hooks: fallo el autotrain en background")
    finally:
        with _lock:
            _training = False


def register(register_fn) -> None:
    """[v2] C18 — MISMA FORMA que los 5 hooks hermanos de app.py:908-925.
    Idempotente: registrar dos veces no duplica el hook."""
    global _installed
    if _installed:
        return
    register_fn(_on_execution_end_cost)
    _installed = True
```

> **`[v2]` (C18) La forma del enganche también estaba mal.** v1 exponía `install()` y decía *"si no hay
> ninguno registrado en `create_app`, va al final de la función"*. **Hay cinco**, todos con el mismo patrón
> canónico (`app.py:908`, `:910`, `:913`, `:917`, `:925`):
> ```python
> incident_autopublish.register(ticket_status.register_post_hook)
> incident_dev_autocommit.register(ticket_status.register_post_hook)
> completion_dispatcher.register(ticket_status.register_post_hook)
> _vp.register(ticket_status.register_post_hook)
> qa_uat_enqueue.register(ticket_status.register_post_hook)
> ```
> Por eso `cost_model_hooks` expone **`register(register_fn)`**, no `install()`, y la línea que se agrega a
> `app.py` va **junto a esas cinco**, no al final:
> ```python
>     cost_model_hooks.register(ticket_status.register_post_hook)
> ```

**Nota de concurrencia:** `_lock` protege los dos contadores; el entrenamiento en sí corre **fuera** del lock (`cost_model.train()` puede tardar ~1 s y no debe bloquear otros hooks). El doble decremento no es posible porque el contador se resetea dentro del lock antes de soltar.

**Nota sobre `getattr(cfg, ...)` (G10):** se importa `from config import config as cfg`, o sea la **instancia**, no el módulo. Leer del módulo devolvería el default y mataría el branch OFF.

**Registro en `app.py`:** una sola línea dentro de `create_app`, junto al resto de la inicialización de servicios.
*A VERIFICAR EN IMPLEMENTACIÓN* — ubicación exacta donde se registran otros post-hooks:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
grep -n "register_post_hook\|register_pre_hook" app.py api/*.py services/*.py
```
La línea a agregar es:
```python
    cost_model_hooks.register(ticket_status.register_post_hook)
```
**`[v2]` (C18)** Va **junto a las otras 5** (`app.py:908-925`), no al final de `create_app`. El import se agrega al bloque de imports de servicios que ya existe ahí.
Debe ir **después** de que la DB esté inicializada y **dentro** del mismo bloque donde ya se registran otros hooks; si no hay ninguno registrado en `create_app`, va al final de la función, antes del `return app`.

⚠️ **Gotcha conocido del repo:** `create_app()` fuera de pytest dispara daemons y sync reales. El test de este hook **no** debe llamar `create_app()`: debe llamar **`cost_model_hooks.register(ticket_status.register_post_hook)`** directamente y luego `ticket_status.on_execution_end(...)` con una DB de test.

#### F5.6 Casos borde enumerados

1. Se muestra una predicción y el operador **nunca** lanza el agente ⇒ la apertura queda sin cierre; `calibration` la cuenta en `n_open` y no contamina el MAE.
2. Se lanza una ejecución **sin** haber pedido predicción ⇒ `close_forecast` no encuentra `forecast_id` ⇒ devuelve `False` sin escribir.
3. Dos predicciones para el mismo ticket antes de lanzar ⇒ se cierra **la ligada por `bind_execution`**; si hay varias ligadas al mismo `execution_id`, se cierra la **más reciente por `ts`** (regla determinista declarada).
4. Ejecución que termina en `error` ⇒ se cierra igual, con `final_status="error"`; `calibration` la incluye (un forecast que subestimó porque el run explotó **es** un error de estimación y debe verse).
5. Disco lleno / permisos ⇒ `record_forecast` devuelve `""`, loguea warning, y **la UI muestra la predicción igual** (sin ledger).
6. Ledger con 50.001 líneas ⇒ rotación a `.1`; `calibration` lee **sólo** el archivo activo (declarado: la ventana por defecto es de 30 días, muy por debajo del cap).

#### F5.7 Tests PRIMERO

**`backend/tests/test_plan242_forecast_ledger.py`** (usa `tmp_path` + monkeypatch de `data_dir`):

| Caso | Qué verifica |
|---|---|
| `test_record_forecast_devuelve_id_y_escribe_una_linea` | |
| `test_record_forecast_es_append_only` | 3 llamadas ⇒ 3 líneas, ninguna reescrita |
| `test_close_sin_apertura_devuelve_false_y_no_escribe` | caso borde 2 |
| `test_par_abierto_cerrado_produce_calibracion` | **KPI-8**: `n_pairs == 1`, `mae_usd` correcto |
| `test_calibracion_archivo_inexistente_todo_en_cero` | |
| `test_linea_corrupta_se_saltea_y_cuenta` | `skipped_lines == 1`, no lanza |
| `test_linea_sin_kind_se_saltea` | |
| `test_apertura_sin_cierre_cuenta_en_n_open` | caso borde 1 |
| `test_cierre_sin_costo_real_no_contamina_el_mae` | caso borde: `actual_usd is None` |
| `test_coverage_cuenta_bordes_inclusivos` | |
| `test_bias_positivo_significa_subestimacion` | signo verificado con datos a mano |
| `test_by_source_separa_los_4_niveles` | `model`/`cohort_median`/`global_median`/`heuristic` |
| `test_rotacion_al_superar_el_cap` | 50.001 líneas ⇒ existe el `.1` y el activo tiene 1 |
| `test_error_de_disco_devuelve_string_vacio_sin_lanzar` | monkeypatch de `open` que lanza `OSError` |
| `test_dos_forecasts_mismo_execution_cierra_el_mas_reciente` | caso borde 3 |
| `test_ledger_no_toca_la_db` | AST: sin `import db`, sin `import models` |

**`backend/tests/test_plan242_cost_hooks.py`**:

| Caso | Qué verifica |
|---|---|
| **`[v2]`** `test_register_es_idempotente` | **C18**: 2 llamadas a `register(...)` ⇒ 1 sola entrada en `ticket_status._POST_HOOKS` |
| **`[v2]`** `test_autotrain_no_corre_en_el_hilo_del_hook` | **C4**: el hook retorna **antes** de que `train()` termine — se monkeypatchea `cost_model.train` con uno que duerme y se verifica que `on_execution_end` ya volvió. Es el test que impide que vuelva el `train()` en línea |
| **`[v2]`** `test_dos_autotrains_no_se_solapan` | **C4**: con `_training` en curso, la segunda tanda no lanza un segundo entrenamiento |
| `test_hook_cierra_el_forecast_al_terminar` | integración con el ledger |
| `test_hook_no_propaga_excepciones` | el ledger lanza a propósito ⇒ `on_execution_end` no rompe |
| `test_autotrain_off_no_entrena` | flag OFF ⇒ `cost_model.train` no se llama (monkeypatch contador) |
| `test_autotrain_dispara_cada_n_ejecuciones` | `every_n=3` ⇒ entrena en la 3ª, no en la 1ª ni la 2ª |
| `test_autotrain_debounce_bloquea_dentro_de_30_min` | 2 tandas de 3 ⇒ 1 solo entrenamiento |
| `test_autotrain_no_resetea_contador_al_bloquear_por_debounce` | el contador sigue disponible para el próximo intento |
| `test_hook_lee_la_flag_de_la_instancia_no_del_modulo` | **G10**: con `config.config.X=False` el branch OFF se toma de verdad |
| `test_hook_no_llama_create_app` | AST del test: no aparece `create_app` |

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_forecast_ledger.py -q
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_hooks.py -q
```

#### F5.8 Aceptación (BINARIA)

1. **`[v2]`** `0 failed` en los dos archivos, con **16 + 12** casos de cobertura (9 de v1 + 3 nuevos de C4/C18).
2. **KPI-8** verde (`test_par_abierto_cerrado_produce_calibracion`).
3. `grep -c "register_post_hook" services/cost_model_hooks.py` ⇒ **≥1**; `grep -c "agent_completion" services/cost_model_hooks.py` ⇒ **0** (no se usa el chokepoint equivocado).
4. `grep -c "cost_model_hooks" app.py` ⇒ **1**.
5. Ambos archivos registrados en `run_harness_tests.sh` y `.ps1`; ratchet meta verde.
6. Regresión del ciclo de vida: `.venv\Scripts\python.exe -m pytest tests\test_ticket_status.py -q` verde.
   *A VERIFICAR EN IMPLEMENTACIÓN* — nombre real del archivo de test del ciclo de vida:
   ```powershell
   ls tests/ | grep -i "ticket_status\|lifecycle"
   ```

**Flag que la protege:** `STACKY_COST_FORECAST_LEDGER_ENABLED` (default ON) para el registro, y `STACKY_COST_MODEL_AUTOTRAIN_ENABLED` (default ON) + `STACKY_COST_MODEL_AUTOTRAIN_EVERY_N` (int, default 10, bounds 1..1000) para el reentrenamiento.
**Justificación del default ON del autotrain frente a la excepción dura "quema tokens ocioso":** el entrenamiento **no consume ni un token de LLM** (es aritmética local), no abre red, y está doblemente acotado (cada N ejecuciones **y** como mucho 1 cada 30 min). No aplica ninguna de las 4 excepciones duras.
**Impacto por runtime:** el hook es runtime-agnóstico por construcción — `on_execution_end` es el único punto por el que pasan las tres. `codex_cli` y `claude_code_cli` cierran con `actual_cost_kind="reported"`; `github_copilot` cierra con `"nominal"` y **queda excluido del MAE facturable** de `calibration` (se reporta aparte). Fallback: ejecución sin costo ⇒ cierre con `actual_usd: null`, contado pero no promediado.
**Trabajo del operador: ninguno.**

---

### F6 — API (aditiva, misma convención del Plan 142)

**Objetivo (1 frase):** exponer estadística, scoring, estado del modelo, entrenamiento, forecast y calibración como 6 endpoints nuevos que reusan el parser de filtros existente.
**Valor:** sin API no hay UI, y sin reusar `_parse_filters` habría dos definiciones de "filtro de costo" divergiendo.

#### F6.1 Archivos

| Acción | Ruta exacta |
|---|---|
| **EDITAR** | `Stacky Agents/backend/api/metrics.py` (**sólo apéndice**, ver el punto de inserción de abajo) |

> **`[v2]` ⛔ PUNTO DE INSERCIÓN — NO USAR NÚMERO DE LÍNEA (C14).** v1 decía *"sólo apéndice después de la
> línea 723"*. **`metrics.py:723` es `**ca.heatmap(ca.load_records(f)),`, que está DENTRO del `jsonify({...})`
> de `/cost-heatmap` (`:712-724`).** Insertar 6 endpoints ahí es un `SyntaxError` inmediato. Era la
> instrucción más literal del plan y la más destructiva.
>
> El bloque nuevo va **inmediatamente ANTES** de esta línea, que abre el bloque del Plan 171:
> ```python
> # ── Plan 171 — Telemetría operativa (read-only, on-read; espejo patrones Plan 142) ──
> ```
> Localizala así, y usá lo que devuelva:
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> grep -n "Plan 171 — Telemetría operativa" api/metrics.py
> ```
| **CREAR** | `Stacky Agents/backend/tests/test_plan242_cost_api.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` |

**Nada de lo existente se modifica.** **`[v2]` (C17):** quedan intactos `_execution_costs` (`:52`), `/ticket-costs` (`:77`), `/project-costs` (`:130`), `_cost_center_enabled` (`:565`), `_parse_date` (`:576`), `_parse_filters` (`:584`), `_filters_or_error` (**`:627`**, no `:614`) y **los 8 endpoints de costo que ya existen** — no 5, como decía v1:

| Endpoint | Línea | Plan |
|---|---|---|
| `/cost-center/health` | `:569` | 142 |
| `/cost-summary` | `:635` | 142 |
| `/cost-burn` | `:668` | 142 |
| `/cost-burn-stacked` | `:691` | **199** |
| `/cost-heatmap` | `:712` | **199** |
| `/cost-distribution` | `:727` | **199** |
| `/cost-breakdown` | `:746` | 142 |
| `/cost-reconciliation-audit` | `:764` | 142 |

Más los `/ops-*` y `/run-trace/<id>` del Plan 171. El bloque de costo **termina en `:797`**.

#### F6.2 Endpoints — ruta, método y **nombre exacto de la función Python**

| Método | Ruta | Función Python | Flag que lo gatea |
|---|---|---|---|
| GET | `/api/metrics/cost-stats` | `def cost_stats()` | `STACKY_COST_STATS_ENABLED` |
| GET | `/api/metrics/cost-scores` | `def cost_scores()` | `STACKY_COST_SCORING_ENABLED` |
| GET | `/api/metrics/cost-model-status` | `def cost_model_status()` | `STACKY_COST_FORECAST_ENABLED` |
| POST | `/api/metrics/cost-model-train` | `def cost_model_train()` | `STACKY_COST_FORECAST_ENABLED` |
| POST | `/api/metrics/cost-forecast` | `def cost_forecast()` | `STACKY_COST_FORECAST_ENABLED` |
| GET | `/api/metrics/cost-calibration` | `def cost_calibration()` | `STACKY_COST_FORECAST_LEDGER_ENABLED` |

**Los 6 respetan las dos reglas del 142:**
1. Si su flag está OFF ⇒ `return jsonify({"enabled": False}), 200` (mismo patrón que `metrics.py:625`). **Nunca 404, nunca 500.**
2. Todos exigen además `_cost_center_enabled()`: si el Centro de Costos entero está apagado, ninguna sub-función se enciende. Regla: `if not (_cost_center_enabled() and _cost_stats_enabled()): return jsonify({"enabled": False}), 200`.

#### F6.3 Helpers nuevos (junto a `_cost_center_enabled`, mismo patrón `getattr(_cfg, ...)`)

```python
# ── Plan 242 — Centro de Costos telemetrico: stats + scoring + forecast ──────
# Aditivo y read-only (salvo cost-model-train, que escribe UN json en data_dir).
# NO modifica ticket-costs/project-costs/_execution_costs (legacy intactos).

def _cost_stats_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_COST_STATS_ENABLED", False))


def _cost_scoring_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_COST_SCORING_ENABLED", False))


def _cost_forecast_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_COST_FORECAST_ENABLED", False))


def _cost_ledger_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_COST_FORECAST_LEDGER_ENABLED", False))
```

#### F6.4 Contratos de request/response, uno por uno

**`GET /api/metrics/cost-stats`**
Query: los mismos de `/cost-summary` (via `_filters_or_error(request.args)`) más:
- `metric` (str, opcional): una de las 8 de `cost_stats._METRICS`; default `"cost_usd"`. Valor inválido ⇒ `{"ok": false, "error": "invalid_metric"}, 400`.
- `bins` (int, opcional): default 10, clamp 1..100 (el clamp lo hace `histogram`, pero el endpoint también parsea defensivamente).
Respuesta:
```json
{"ok":true,"enabled":true,"generated_at":"…Z","filters_echo":{…},"capped":false,
 "metric":"cost_usd","billable_only":{…stats_payload…},"nominal_only":{…stats_payload…}}
```
**`billable_only`** agrega **sólo** los records con `cost_kind` en `("reported","estimated")`; **`nominal_only`** agrega **sólo** los `nominal`. **G7:** nunca se mezclan. Si un bloque no tiene records, su `runs_total` es 0 y sus distribuciones tienen `n=0` (nunca se omite la clave: omitirla obligaría a la UI a adivinar).

**`GET /api/metrics/cost-scores`**
Query: los de `_parse_filters` + `top_n` (int, default 50, clamp 1..200).
Respuesta: `{"ok":true,"enabled":true,"generated_at":"…Z","filters_echo":{…},"capped":bool, **score_payload(records, top_n)}`.

**`GET /api/metrics/cost-model-status`**
Sin query params. Respuesta:
```json
{"ok":true,"enabled":true,"generated_at":"…Z",
 "model_present":true,"status":"active","schema_version":1,
 "trained_at":"…Z","n_samples":412,"n_train":288,"n_calib":62,"n_test":62,
 "feature_count":38,"eval":{…},"reject_reasons":[],
 "min_samples":30,"autotrain_enabled":true,"autotrain_every_n":10,
 "global_median_usd":0.0932,"cohorts":12}
```
Si no hay archivo o está corrupto ⇒ `"model_present": false`, `"status": null`, y `"reason"` con el motivo textual de `load_model`. **200 siempre.**

**`POST /api/metrics/cost-model-train`**
Body JSON opcional: `{"days": 365}` (int, clamp 1..3650, default 365).
Ejecuta `cost_model.train(days=days)` **sincrónicamente** (KPI-7 garantiza < 2 s).
Respuesta: `{"ok":true,"enabled":true,"trained":bool,"status":"active"|"candidate","n_samples":int,"reason":str|null,"eval":{…},"reject_reasons":[…],"elapsed_ms":int}`.
**Es la única escritura del plan disparada por HTTP**, y sólo escribe `cost_model.json`. Es idempotente en el sentido de que re-entrenar con los mismos datos produce el mismo modelo (determinismo de F3).

**`POST /api/metrics/cost-forecast`**
Body JSON, **dos formas aceptadas** (si vienen las dos, `ticket_id` gana y los campos sueltos se ignoran):
- Forma A: `{"ticket_id": 812, "agent_type": "developer", "runtime": "claude_code_cli", "model": "claude-sonnet-5"}` — el endpoint lee el `Ticket` de la DB para sacar `title`, `description`, `work_item_type`, `priority`, cuenta `prev_executions` y calcula `project_median_usd`.
- Forma B: `{"title": "...", "description": "...", "work_item_type": "Bug", "priority": "2", "agent_type": "...", "runtime": "...", "model": "..."}` — sin tocar la DB para el ticket (igual consulta las medianas del modelo persistido).
Validación: `agent_type` es **obligatorio** en ambas formas ⇒ si falta, `{"ok": false, "error": "agent_type_required"}, 400`. `ticket_id` inexistente ⇒ `{"ok": false, "error": "ticket_not_found"}, 404`.
Respuesta: `{"ok":true,"enabled":true,"generated_at":"…Z", **CostPrediction-as-dict, "forecast_id":"9f2c…"}`.
El `forecast_id` viene de `cost_forecast_ledger.record_forecast(...)`; si el ledger está OFF o falló, la clave vale `null` y la predicción se devuelve igual.

**`GET /api/metrics/cost-calibration`**
Query: `days` (int, default 30, clamp 1..365).
Respuesta: `{"ok":true,"enabled":true,"generated_at":"…Z", **calibration(days)}`.

#### F6.5 Casos borde enumerados

1. Flag del sub-feature ON pero `STACKY_COST_CENTER_ENABLED` OFF ⇒ `{"enabled": false}` (regla 2 de §F6.2).
2. Fecha malformada ⇒ `{"ok": false, "error": "invalid_date"}, 400` (heredado de `_filters_or_error`).
3. `metric` desconocida ⇒ 400 `invalid_metric` (**no** se deja explotar el `ValueError` de `cost_stats.metric_value`).
4. Sin records en la ventana ⇒ 200 con payload vacío bien formado, **no** 404.
5. `POST /cost-model-train` cuando no hay muestras suficientes ⇒ 200 con `"trained": false` y `"reason"` textual. **No es un error HTTP**: es una respuesta legítima.
6. Body no-JSON en los POST ⇒ `request.get_json(force=True, silent=True) or {}` (mismo patrón que `api/agents.py:1396`), y sigue la validación normal.

#### F6.6 Tests PRIMERO — `backend/tests/test_plan242_cost_api.py`

Usa el `app` fixture de pytest-flask ya usado por `tests/test_cost_center_api.py`.
*A VERIFICAR EN IMPLEMENTACIÓN* — nombre exacto de la fixture:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
grep -n "def app\|@pytest.fixture" tests/test_cost_center_api.py | head
```

| Caso | Qué verifica |
|---|---|
| `test_cost_stats_flag_off_devuelve_enabled_false_200` | los 6 endpoints, parametrizado |
| `test_cost_center_off_apaga_los_seis` | caso borde 1 |
| `test_cost_stats_fecha_invalida_400` | caso borde 2 |
| `test_cost_stats_metric_invalida_400` | caso borde 3 |
| `test_cost_stats_separa_billable_de_nominal` | **G7**: un run de copilot no aparece en `billable_only` |
| `test_cost_stats_ambas_claves_siempre_presentes` | caso borde 4 |
| `test_cost_scores_top_n_clampeado_1_200` | |
| `test_cost_model_status_sin_archivo_model_present_false_200` | |
| `test_cost_model_status_archivo_corrupto_no_500` | |
| `test_cost_model_train_pocas_muestras_200_trained_false` | caso borde 5 |
| `test_cost_model_train_devuelve_elapsed_ms` | |
| `test_cost_forecast_sin_agent_type_400` | |
| `test_cost_forecast_ticket_inexistente_404` | |
| `test_cost_forecast_forma_A_lee_el_ticket` | |
| `test_cost_forecast_forma_B_no_toca_la_db_del_ticket` | |
| `test_cost_forecast_ticket_id_gana_sobre_campos_sueltos` | |
| `test_cost_forecast_devuelve_forecast_id` | |
| `test_cost_forecast_ledger_off_forecast_id_null_pero_prediccion_ok` | |
| `test_cost_forecast_copilot_marca_no_facturable` | **G7** |
| `test_cost_calibration_sin_ledger_200_contadores_en_cero` | |
| `test_body_no_json_no_rompe_los_post` | caso borde 6 |
| `test_ningun_endpoint_nuevo_abre_red_ni_llm` | **G3**: monkeypatch que revienta si se llama `requests.get/post`, `socket.socket`, `subprocess.Popen` — se golpean los 6 endpoints |
| `test_endpoints_legacy_siguen_intactos` | `/ticket-costs` y `/project-costs` responden igual que antes del plan |
| **`[v2]`** `test_los_8_endpoints_de_costo_siguen_iguales` | **C17**: smoke de no-regresión **parametrizado sobre los 8** (`/cost-center/health`, `/cost-summary`, `/cost-burn`, `/cost-burn-stacked`, `/cost-heatmap`, `/cost-distribution`, `/cost-breakdown`, `/cost-reconciliation-audit`). v1 cubría 5 y dejaba afuera justo los 3 del Plan 199, que son los vecinos inmediatos del punto de inserción |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_cost_api.py -q
```

#### F6.7 Aceptación (BINARIA)

1. Los 24 casos verdes.
2. `.venv\Scripts\python.exe -m pytest tests\test_cost_center_api.py -q` verde **sin editar el archivo**.
3. `grep -cE "def (cost_stats|cost_scores|cost_model_status|cost_model_train|cost_forecast|cost_calibration)\(" api/metrics.py` ⇒ **6**.
4. `git diff api/metrics.py | grep "^-" | grep -v "^---"` ⇒ **0 líneas eliminadas** (el cambio es puro apéndice).

**Flag que la protege:** las 4 de la tabla §F6.2, todas **default ON**.
**Impacto por runtime:** los endpoints son agnósticos; la separación `billable_only` / `nominal_only` es lo que le da a Copilot su lugar propio sin contaminar. Fallback: runtime sin datos ⇒ bloque con `runs_total: 0` y distribuciones `n=0`, nunca clave ausente.
**Trabajo del operador: ninguno.**

---

### F7 — Frontend: sub-tabs del Centro de Costos

**Objetivo (1 frase):** que el operador vea la estadística, el scoring y la predicción sin perder la pantalla que ya conoce.
**Valor:** todo lo anterior es invisible hasta esta fase.

#### F7.1 Contrato de navegación (deep-link)

`frontend/src/services/routes.ts:28` ya define `RouteState.subtab?: string` como **el segundo segmento del path** (hoy sólo lo usa Settings), y `TAB_PATHS.costcenter = "/costcenter"` (`routes.ts:21`). Por lo tanto los deep-links del 242 son:

| Sub-tab | URL | Constante |
|---|---|---|
| Resumen (**default**, comportamiento actual) | `/costcenter` **y** `/costcenter/resumen` | `"resumen"` |
| Estadísticas | `/costcenter/estadisticas` | `"estadisticas"` |
| Scoring | `/costcenter/scoring` | `"scoring"` |
| Predicción | `/costcenter/prediccion` | `"prediccion"` |

**Backward compatible por construcción:** `/costcenter` sin segundo segmento ⇒ `subtab === undefined` ⇒ se resuelve a `"resumen"` ⇒ **la pantalla actual, sin cambios**. Un `subtab` desconocido (`/costcenter/pepe`) también cae en `"resumen"` (nunca pantalla en blanco).

*A VERIFICAR EN IMPLEMENTACIÓN* — cómo `App.tsx` pasa el `subtab` a la página:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
grep -n "subtab" src/App.tsx src/services/routes.ts
grep -n "CostCenterPage" src/App.tsx
```
Si `App.tsx` ya pasa `subtab` como prop a alguna página (patrón de Settings), **usar ese mismo patrón**. Si no, `CostCenterPage` recibe una prop nueva `subtab?: string` y `App.tsx` se la pasa desde el `RouteState` que ya calcula. **No** inventar un router propio ni leer `window.location` dentro del componente.

#### F7.2 Archivos

| Acción | Ruta exacta |
|---|---|
| **EDITAR** | `Stacky Agents/frontend/src/pages/CostCenterPage.tsx` |
| **EDITAR** | `Stacky Agents/frontend/src/pages/CostCenterPage.module.css` |
| **EDITAR** | `Stacky Agents/frontend/src/lib/costCenterTypes.ts` (tipos nuevos, aditivo) |
| **EDITAR** | `Stacky Agents/frontend/src/api/endpoints.ts` (métodos nuevos en el objeto `CostCenter`) |
| **CREAR** | `Stacky Agents/frontend/src/lib/costForecast.logic.ts` |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostSubTabs.tsx` + `.module.css` |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostStatsPanel.tsx` + `.module.css` |
| **`[v2]` EDITAR** (⚠️ **YA EXISTE** — C15) | `Stacky Agents/frontend/src/components/costcenter/CostDistributionChart.tsx` + `.module.css`. Lo creó el **Plan 199** y `CostCenterPage` lo consume hoy contra `GET /api/metrics/cost-distribution`. **PROHIBIDO recrearlo:** "CREAR" con el contrato nuevo pisa el componente vivo y rompe la pestaña Resumen, que F7.9.6 promete dejar idéntica. Se le agrega una prop **opcional** `bins?: HistBin[]`: cuando viene, dibuja el histograma de `cost_stats`; cuando no viene, el render es **byte-idéntico** al actual. |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostBoxPlot.tsx` + `.module.css` (el box plot sí es nuevo) |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostScoreTable.tsx` + `.module.css` |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostScoreBadge.tsx` + `.module.css` |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostForecastPanel.tsx` + `.module.css` |
| **CREAR** | `Stacky Agents/frontend/src/components/costcenter/CostCalibrationCard.tsx` + `.module.css` |
| **CREAR** | `Stacky Agents/frontend/src/lib/__tests__/costForecast.logic.test.ts` |

#### F7.3 Cliente API — métodos nuevos en el objeto `CostCenter` (`endpoints.ts:1471`)

Se **agregan** al objeto existente (no se crea otro), reusando `costFiltersToQuery` (`endpoints.ts:1453`):

```ts
  stats: (params?: CostFiltersParams & { metric?: string; bins?: number }) => {
    const p = costFiltersToQuery(params);
    if (params?.metric) p.set("metric", params.metric);
    if (params?.bins) p.set("bins", String(params.bins));
    const qs = p.toString();
    return api.get<CostStatsResponse>(`/api/metrics/cost-stats${qs ? `?${qs}` : ""}`);
  },
  scores: (params?: CostFiltersParams) => {
    const qs = costFiltersToQuery(params).toString();
    return api.get<CostScoresResponse>(`/api/metrics/cost-scores${qs ? `?${qs}` : ""}`);
  },
  modelStatus: () => api.get<CostModelStatusResponse>("/api/metrics/cost-model-status"),
  trainModel: (days?: number) =>
    api.post<CostModelTrainResponse>("/api/metrics/cost-model-train", days ? { days } : {}),
  forecast: (body: CostForecastRequest) =>
    api.post<CostForecastResponse>("/api/metrics/cost-forecast", body),
  calibration: (days?: number) => {
    const qs = days ? `?days=${days}` : "";
    return api.get<CostCalibrationResponse>(`/api/metrics/cost-calibration${qs}`);
  },
```

⚠️ **Gotcha del wrapper:** `api.get` / `api.post` **lanzan excepción** en respuestas non-2xx; leer el body del error dentro de un `.then()` es código muerto. Como **los 6 endpoints devuelven 200 incluso apagados o sin datos** (§F6.2), el flujo normal nunca necesita `rawGet`/`rawPost`. El único 4xx esperable es la validación de `cost-forecast` (400/404), y ahí se maneja con `catch` de react-query, mostrando el mensaje del error.
**`[v2]` RESUELTO (C22, verificado 2026-07-26):** `rawGet` **SÍ existe** — `frontend/src/api/client.ts:93`, gemelo de lectura de `rawPost` que agregó el Plan 238. v1 decía que "puede no existir". Como los 6 endpoints devuelven 200 siempre, **este plan no lo usa**; se deja anotado para que nadie lo re-cree. Comando de re-verificación:
```powershell
grep -n "export function rawGet\|export function rawPost\|rawGet\b" src/api/client.ts src/api/endpoints.ts
```
Si hiciera falta leer un body de error, usar `rawPost` para los POST y, para los GET, apoyarse en el `error` de react-query. **No** crear `rawGet` en este plan.

#### F7.4 Tipos nuevos en `costCenterTypes.ts` (aditivos, ninguno modifica los existentes)

```ts
export interface Distribution {
  n: number; n_missing: number; total: number | null;
  minimum: number | null; maximum: number | null;
  mean: number | null; median: number | null; stdev: number | null;
  q1: number | null; q3: number | null; iqr: number | null;
  cv: number | null; mad: number | null;
  p50: number | null; p75: number | null; p90: number | null;
  p95: number | null; p99: number | null;
}
export interface HistBin { lo: number; hi: number; count: number }
export interface OutlierReport {
  method: "tukey" | "mad"; fence_low: number | null; fence_high: number | null;
  indices: number[]; n_outliers: number; applicable: boolean; reason: string;
}
export interface MetricStats {
  overall: Distribution; histogram: HistBin[];
  outliers_tukey: OutlierReport; outliers_mad: OutlierReport;
}
export interface StatsBlock {
  metrics: Record<string, MetricStats>;
  by_dimension: Record<string, Record<string, Distribution>>;
  cache_efficiency: Record<string, number | null>;
  rework: Record<string, unknown>;
  runs_total: number;
}
export interface CostStats {
  ok: true; enabled: true; generated_at: string;
  filters_echo: FiltersEcho; capped: boolean; metric: string;
  billable_only: StatsBlock; nominal_only: StatsBlock;
}
export type CostStatsResponse = CostCenterDisabled | CostStats;

export type Grade = "A" | "B" | "C" | "D" | "E" | "N/D";
export interface ExecutionScore {
  execution_id: number; ticket_id: number | null; agent_type: string | null;
  runtime: string | null; model: string | null;
  cost_usd: number | null; cost_kind: CostKind;
  score: number | null; grade: Grade;
  components: Record<string, number>; weights_used: Record<string, number>;
  reasons: string[]; cohort_key: string; cohort_n: number;
  confidence: "alta" | "media" | "baja";
}
export interface TicketScore {
  ticket_id: number; ado_id: number | null; runs: number; billable_usd: number;
  score: number | null; grade: Grade; rework_penalty: number;
  reasons: string[]; worst_execution_id: number | null;
}
export interface CostScores {
  ok: true; enabled: true; generated_at: string;
  filters_echo: FiltersEcho; capped: boolean;
  cohorts: Record<string, { n: number; median_cost_usd: number | null; median_unit_cost: number | null }>;
  executions: ExecutionScore[]; tickets: TicketScore[];
  grade_distribution: Record<Grade, number>;
  runs_total: number; runs_scored: number;
}
export type CostScoresResponse = CostCenterDisabled | CostScores;

export type ForecastSource = "model" | "cohort_median" | "global_median" | "heuristic";
export type ForecastConfidence = "alta" | "media" | "baja" | "muy_baja";
export interface CostPrediction {
  p10_usd: number; p50_usd: number; p90_usd: number;
  source: ForecastSource; confidence: ForecastConfidence;
  n_samples: number; cost_kind: "forecast"; billable: boolean;
  explanation: string[];
  model_trained_at: string | null; model_status: "active" | "candidate" | null;
}
export interface CostForecastRequest {
  ticket_id?: number; title?: string; description?: string;
  work_item_type?: string; priority?: string;
  agent_type: string; runtime?: string; model?: string;
}
export interface CostForecast extends CostPrediction {
  ok: true; enabled: true; generated_at: string; forecast_id: string | null;
}
export type CostForecastResponse = CostCenterDisabled | CostForecast;

export interface CostModelStatus {
  ok: true; enabled: true; generated_at: string;
  model_present: boolean; status: "active" | "candidate" | null;
  schema_version: number | null; trained_at: string | null;
  n_samples: number; n_train: number; n_calib: number; n_test: number;
  feature_count: number;
  eval: Record<string, number> | null; reject_reasons: string[];
  min_samples: number; autotrain_enabled: boolean; autotrain_every_n: number;
  global_median_usd: number | null; cohorts: number; reason?: string;
}
export type CostModelStatusResponse = CostCenterDisabled | CostModelStatus;
export interface CostModelTrain {
  ok: true; enabled: true; trained: boolean;
  status: "active" | "candidate"; n_samples: number;
  reason: string | null; eval: Record<string, number> | null;
  reject_reasons: string[]; elapsed_ms: number;
}
export type CostModelTrainResponse = CostCenterDisabled | CostModelTrain;

export interface CostCalibration {
  ok: true; enabled: true; generated_at: string;
  n_forecasts: number; n_pairs: number; n_open: number;
  mae_usd: number | null; mape: number | null; coverage: number | null;
  bias_usd: number | null;
  by_source: Record<ForecastSource, { n: number; mae_usd: number | null; coverage: number | null }>;
  skipped_lines: number; window_days: number;
}
export type CostCalibrationResponse = CostCenterDisabled | CostCalibration;
```

El type guard `isCostCenterEnabled` ya existe (`costCenterTypes.ts:156`) y sirve para los 6 nuevos sin cambios.

#### F7.5 `costForecast.logic.ts` — lógica PURA (lo único con test automático, G8)

```ts
/** Plan 242 F7 — logica PURA del Centro de Costos telemetrico.
 *  Sin React, sin DOM, sin fetch: 100% testeable con vitest. */

export function formatUsdRange(p10: number, p50: number, p90: number): string
// -> "0,18 – 0,74 USD (mediana 0,34)"; 4 decimales si p90 < 0.01; separador decimal coma.

export function gradeTokenVar(grade: Grade): string
// A->"--color-success" B->"--color-success-soft" C->"--color-warning"
// D->"--color-danger-soft" E->"--color-danger" N/D->"--color-text-muted"
// (nombres de token A VERIFICAR contra el CSS del repo; ver F7.8)

export function confidenceLabel(c: ForecastConfidence): string
// alta->"Confianza alta"  media->"Confianza media"
// baja->"Confianza baja"  muy_baja->"Sin histórico — estimación gruesa"

export function sourceLabel(s: ForecastSource): string
// model->"Modelo aprendido"  cohort_median->"Mediana de tareas parecidas"
// global_median->"Mediana global"  heuristic->"Heurística por tokens"

export function histogramBars(bins: HistBin[], maxHeightPx: number): {x: number; w: number; h: number; count: number; label: string}[]
// Escala lineal por count; count 0 -> h 0. bins vacio -> []. maxCount 0 -> todas h 0
// (NO dividir por cero).

export function boxPlotGeometry(d: Distribution, widthPx: number): {q1: number; median: number; q3: number; whiskerLo: number; whiskerHi: number} | null
// null si d.n < 2 o si minimum/maximum son null. Escala [minimum, maximum] -> [0, widthPx].
// Si minimum === maximum, todo cae en 0 (ancho degenerado, sin dividir por cero).

export function formatPercentileSummary(d: Distribution): string
// "p50 0,0412 · p90 0,2130 · p99 0,8800 (n=412)"; si d.n === 0 -> "Sin datos".

export function coverageVerdict(coverage: number | null): {label: string; ok: boolean}
// null -> {"Sin pares suficientes", false}
// 0.60..0.95 -> {"Intervalo bien calibrado", true}
// <0.60 -> {"Intervalo demasiado angosto", false}
// >0.95 -> {"Intervalo demasiado ancho", false}
// (mismos cortes que _COVERAGE_MIN/_COVERAGE_MAX de F4: una sola verdad)

export function outlierSummary(o: OutlierReport): string
// !applicable -> o.reason ; si no -> "3 outliers (fuera de 0,0010 – 0,4200)"
```

#### F7.6 Componentes — responsabilidad de cada uno (sin test automático, G8)

- **`CostSubTabs.tsx`** — 4 botones; recibe `value: SubTab` y `onChange`; emite el cambio de URL vía la prop `onNavigate` que le pase la página (no toca `window`).
- **`CostStatsPanel.tsx`** — sub-tab "Estadísticas": selector de métrica (8 opciones) y de dimensión (6), tarjeta de percentiles, `CostDistributionChart`, tabla por dimensión, tarjetas de `cache_efficiency` y `rework`. Muestra **dos bloques separados y rotulados**: "Facturable" y "Nominal (suscripción plana)".
- **`CostDistributionChart.tsx`** — histograma + box plot en **SVG inline** usando `histogramBars` y `boxPlotGeometry`. Sin librería de gráficos (no hay ninguna nueva permitida). Marca los outliers con un color distinto y un `title` con el valor.
- **`CostScoreTable.tsx`** — sub-tab "Scoring": tabla ordenable de ejecuciones y de tickets, con `CostScoreBadge`, columna de razones expandible (las `reasons` del backend, tal cual, sin reinterpretar).
- **`CostScoreBadge.tsx`** — la letra A–E con el token de color de `gradeTokenVar` + el score numérico + `title` con la confianza.
- **`CostForecastPanel.tsx`** — sub-tab "Predicción": estado del modelo (`modelStatus`), botón **"Entrenar ahora"** (llama `trainModel`), formulario de simulación (ticket_id o campos sueltos) que llama `forecast`, y el resultado como rango P10–P90 con la explicación línea por línea. Si `status === "candidate"`, muestra un aviso con las `reject_reasons` textuales.
- **`CostCalibrationCard.tsx`** — MAE/MAPE/cobertura/bias del ledger + `coverageVerdict` + desglose `by_source`. Si `n_pairs === 0`, muestra "Todavía no hay predicciones cerradas" (no un 0 que parezca perfecto).

**Regla de deuda de UI del repo:** los archivos `.tsx` **nuevos** deben tener **cero** `style={{ }}` inline y **cero** literales HEX en su CSS (usar `var(--token)`), porque el ratchet de deuda de UI mide alcance 0 en archivos nuevos. Para geometría dinámica de SVG, usar atributos SVG (`x`, `width`, `height`) o `ref` + `setProperty`, **no** `style={{}}`.

#### F7.7 Tests PRIMERO — `frontend/src/lib/__tests__/costForecast.logic.test.ts`

| Caso | Qué verifica |
|---|---|
| `formatUsdRange usa coma decimal y 2 decimales` | |
| `formatUsdRange usa 4 decimales cuando p90 < 0,01` | |
| `gradeTokenVar cubre las 6 notas` | incluida `N/D` |
| `confidenceLabel cubre los 4 niveles` | |
| `sourceLabel cubre los 4 orígenes` | |
| `histogramBars con bins vacío devuelve []` | |
| `histogramBars con maxCount 0 no divide por cero` | todas `h === 0` |
| `histogramBars escala proporcional al count` | count doble ⇒ alto doble |
| `boxPlotGeometry devuelve null si n < 2` | |
| `boxPlotGeometry con min === max no divide por cero` | |
| `boxPlotGeometry ordena q1 <= median <= q3` | |
| `formatPercentileSummary con n=0 dice Sin datos` | |
| `coverageVerdict null es no-ok` | |
| `coverageVerdict 0,79 es ok` | |
| `coverageVerdict 0,50 dice demasiado angosto` | |
| `coverageVerdict 0,99 dice demasiado ancho` | |
| `coverageVerdict usa los mismos cortes que el backend` | 0,60 y 0,95 inclusive |
| `outlierSummary no aplicable devuelve el reason del backend` | |
| `outlierSummary aplicable menciona la cantidad y las vallas` | |

**Comando (desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`):**
```powershell
npx vitest run src/lib/__tests__/costForecast.logic.test.ts
```
⚠️ **Correr por archivo.** La corrida completa de vitest contamina entre archivos (gotcha conocido del repo).

#### F7.8 Casos borde enumerados

1. `{"enabled": false}` en cualquiera de los 6 ⇒ el sub-tab muestra el `EmptyState` "activá la flag en Arnés" (mismo patrón que `CostCenterPage.tsx:60-66`), nunca pantalla en blanco.
2. `subtab` desconocido ⇒ "resumen".
3. `model_present: false` ⇒ el panel de Predicción muestra "Todavía no hay modelo entrenado" + el botón "Entrenar ahora" habilitado.
4. `status: "candidate"` ⇒ aviso amarillo con `reject_reasons`, y el rango se muestra igual **etiquetado con su `source` real** (que no será `"model"`).
5. `billable: false` (Copilot) ⇒ el rango se muestra con el rótulo "costo nominal — no facturable (suscripción plana)" y **sin** signo de dólar destacado.
6. `n_pairs: 0` en calibración ⇒ "Todavía no hay predicciones cerradas", **no** MAE 0,00.
7. Histograma de una distribución degenerada (1 bin) ⇒ se dibuja 1 barra ancha, no se rompe.

*A VERIFICAR EN IMPLEMENTACIÓN* — nombres reales de los tokens de color:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
grep -rn "color-success\|color-danger\|color-warning" src/styles/ src/index.css | head -20
```
Usar los que existan. **Prohibido** inventar un token nuevo o escribir un HEX.

#### F7.9 Aceptación (BINARIA)

1. `npx vitest run src/lib/__tests__/costForecast.logic.test.ts` ⇒ **19/19 verdes**.
2. `npx tsc --noEmit` ⇒ **0 errores**.
3. `npx vitest run src/lib/__tests__/costCenter.logic.test.ts` ⇒ verde **sin editar el archivo** (no-regresión del 142).
4. `grep -c "style={{" src/components/costcenter/CostStatsPanel.tsx src/components/costcenter/CostDistributionChart.tsx src/components/costcenter/CostScoreTable.tsx src/components/costcenter/CostScoreBadge.tsx src/components/costcenter/CostForecastPanel.tsx src/components/costcenter/CostCalibrationCard.tsx src/components/costcenter/CostSubTabs.tsx` ⇒ **0 en los 7**.
5. `grep -cE "#[0-9a-fA-F]{3,8}" src/components/costcenter/*.module.css` ⇒ **0** en los 7 archivos nuevos.
6. **Smoke visual MANUAL** (declarado como manual, G8): abrir `/costcenter`, verificar que la pantalla es idéntica a la de antes del plan; navegar a `/costcenter/estadisticas`, `/costcenter/scoring`, `/costcenter/prediccion`; apretar "Entrenar ahora" y ver el resultado; recargar con F5 en cada sub-tab y confirmar que aterriza en el mismo lugar (deep-link).

**Flag que la protege:** las 4 del backend. La página **no** agrega flag propia de UI: cada sub-tab se apaga solo cuando su endpoint responde `{"enabled": false}`, y si los 3 nuevos están OFF, el `CostSubTabs` no se renderiza y la página es exactamente la del 142.
**Impacto por runtime:** la UI separa visualmente "Facturable" (Codex + Claude) de "Nominal (suscripción plana)" (Copilot) en Estadísticas, y rotula cada predicción de Copilot como no facturable. Fallback: bloque sin datos ⇒ `EmptyState` con el motivo, nunca 0 disfrazado de dato.
**Trabajo del operador: ninguno** (opt-in de mirar los sub-tabs; el default es la pantalla de siempre).

---

### F8 — Flags, paridad de runtimes, ratchet de tests y no-degradación

**Objetivo (1 frase):** que las 7 flags nuevas nazcan ON, sean editables desde la UI del Arnés, estén categorizadas y acotadas, y que con todo en OFF el sistema sea byte-idéntico al del Plan 142+158.
**Valor:** es lo que hace que el plan sea reversible y que el operador no tenga que configurar nada.

#### F8.1 Las 7 flags — nombre exacto, tipo, default y justificación

| # | Key | Tipo | Default | Bounds | Justificación del default |
|---|---|---|---|---|---|
| 1 | `STACKY_COST_STATS_ENABLED` | bool | **ON** | — | Read-only, sin LLM, sin red, sin acción irreversible, sin bypass humano ⇒ **ninguna de las 4 excepciones duras aplica**. |
| 2 | `STACKY_COST_SCORING_ENABLED` | bool | **ON** | — | Ídem: aritmética determinista sobre datos ya persistidos. |
| 3 | `STACKY_COST_FORECAST_ENABLED` | bool | **ON** | — | Ídem. El entrenamiento no consume tokens de LLM ni abre red; escribe **un** JSON reversible. |
| 4 | `STACKY_COST_MODEL_AUTOTRAIN_ENABLED` | bool | **ON** | — | El único candidato plausible a "quema tokens ocioso" (excepción #1) — pero **no consume ni un token**: es aritmética local, disparada por un evento real (fin de ejecución), con doble cota (cada N runs **y** máx. 1 cada 30 min). **No aplica.** |
| 5 | `STACKY_COST_MODEL_MIN_SAMPLES` | int | **30** | `min_value=10`, `max_value=5000` | Umbral mínimo para que L1 se active. |
| 6 | `STACKY_COST_MODEL_AUTOTRAIN_EVERY_N` | int | **10** | `min_value=1`, `max_value=1000` | Cada cuántas ejecuciones se evalúa reentrenar. |
| 7 | `STACKY_COST_FORECAST_LEDGER_ENABLED` | bool | **ON** | — | Escribe un JSONL acotado (500 filas, patrón `ci_run_ledger`) en el data dir; borrarlo revierte. Read-mostly, sin red, sin LLM. |
| **8 `[v2]`** | `STACKY_COST_MODEL_AUTOPROMOTE_ENABLED` | bool | **ON** | — | **[ADICIÓN ARQUITECTO] §F4.5 (C16).** Escribe **un** JSON reversible **y con snapshot del anterior**. En OFF, todo entrenamiento queda `candidate` y promueve el operador a mano. Ninguna de las 4 excepciones duras aplica. |

**Ninguna flag de este plan es OFF por excepción dura.** Se revisaron las 4 y ninguna aplica: (1) no quema tokens ociosos, (2) no hace acciones irreversibles, (3) no depende de un prerequisito no garantizado en una instalación default —a diferencia de `STACKY_COST_CODEBURN_IMPORT_ENABLED` (`config.py:618`), que sí—, (4) no saltea revisión humana (G15: el modelo informa, no decide).

#### F8.2 Los 5 lugares donde va CADA flag (receta completa)

**(1) `Stacky Agents/backend/config.py`** — apéndice al bloque de costo (después de la línea 650), siguiendo el patrón literal del 142/158:

```python
    # ── Plan 242 — Centro de Costos telemétrico + scoring + estimador ─────────
    # Todas read-only o reversibles; default ON (ninguna de las 4 excepciones duras).
    STACKY_COST_STATS_ENABLED: bool = os.getenv(
        "STACKY_COST_STATS_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_COST_SCORING_ENABLED: bool = os.getenv(
        "STACKY_COST_SCORING_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_COST_FORECAST_ENABLED: bool = os.getenv(
        "STACKY_COST_FORECAST_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_COST_FORECAST_LEDGER_ENABLED: bool = os.getenv(
        "STACKY_COST_FORECAST_LEDGER_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_COST_MODEL_AUTOTRAIN_ENABLED: bool = os.getenv(
        "STACKY_COST_MODEL_AUTOTRAIN_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_COST_MODEL_MIN_SAMPLES: int = int(
        os.getenv("STACKY_COST_MODEL_MIN_SAMPLES", "30") or 30
    )
    STACKY_COST_MODEL_AUTOTRAIN_EVERY_N: int = int(
        os.getenv("STACKY_COST_MODEL_AUTOTRAIN_EVERY_N", "10") or 10
    )
```

**(2) `backend/services/harness_flags.py` → `_CATEGORY_KEYS`** (G12). Se agregan las 7 keys a la tupla de la categoría `"observabilidad_notif"` (`harness_flags.py:269`), justo después de las del 158 (`:281-282`):

```python
        "STACKY_COST_STATS_ENABLED",                  # Plan 242
        "STACKY_COST_SCORING_ENABLED",                # Plan 242
        "STACKY_COST_FORECAST_ENABLED",               # Plan 242
        "STACKY_COST_FORECAST_LEDGER_ENABLED",        # Plan 242
        "STACKY_COST_MODEL_AUTOTRAIN_ENABLED",        # Plan 242
        "STACKY_COST_MODEL_MIN_SAMPLES",              # Plan 242
        "STACKY_COST_MODEL_AUTOTRAIN_EVERY_N",        # Plan 242
```

**(3) `backend/services/harness_flags.py` → `FLAG_REGISTRY`** (`:397`). Se agregan 7 `FlagSpec` después de las del 158 (`:1811-1824`). Ejemplos exactos de los dos tipos:

```python
    # ── Plan 242 — Centro de Costos telemétrico ────────────────────────────────
    FlagSpec(
        key="STACKY_COST_STATS_ENABLED",
        type="bool",
        default=True,   # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        label="Centro de Costos: estadística profunda",
        description=(
            "Plan 242 — Habilita GET /api/metrics/cost-stats: percentiles, desvío, IQR, "
            "MAD, histograma y outliers por métrica y por dimensión. Read-only, sin LLM "
            "y sin red. OFF = el endpoint responde {\"enabled\": false} y la UI oculta "
            "el sub-tab Estadísticas."
        ),
        group="observabilidad_notif",   # [v2] C21 — usar el MISMO valor que las flags de
                                        # costo hermanas (harness_flags.py:2082/:2095/:2108).
                                        # OJO: group="observabilidad" a secas SÍ existe (11 usos),
                                        # así que esto NO rompe ningún test: es consistencia de
                                        # agrupación en la UI del Arnés, y ningún test la valida.
    ),
    FlagSpec(
        key="STACKY_COST_MODEL_MIN_SAMPLES",
        type="int",
        default=30,
        min_value=10,
        max_value=5000,
        label="Centro de Costos: muestras mínimas para usar el modelo",
        description=(
            "Plan 242 — Cantidad mínima de ejecuciones con costo reportado para que el "
            "modelo aprendido se use. Por debajo, el sistema cae a la mediana de la "
            "cohorte. Subirlo hace la estimación más conservadora."
        ),
        group="observabilidad_notif",   # [v2] C21 — usar el MISMO valor que las flags de
                                        # costo hermanas (harness_flags.py:2082/:2095/:2108).
                                        # OJO: group="observabilidad" a secas SÍ existe (11 usos),
                                        # así que esto NO rompe ningún test: es consistencia de
                                        # agrupación en la UI del Arnés, y ningún test la valida.
        requires="STACKY_COST_FORECAST_ENABLED",
    ),
```
Las otras 5 siguen el mismo molde. `STACKY_COST_MODEL_AUTOTRAIN_EVERY_N` y `STACKY_COST_MODEL_AUTOTRAIN_ENABLED` declaran `requires="STACKY_COST_FORECAST_ENABLED"`.

⚠️ **Gotcha `requires` (Plan 82/83, R4 profundidad 1):** `requires` **no admite cadenas**. Una flag no puede apuntar a otra que a su vez tenga `requires`. Como `STACKY_COST_FORECAST_ENABLED` **no** declara `requires`, la profundidad es 1 y es válido. Además hay que agregar la arista correspondiente al mapa congelado.
*A VERIFICAR EN IMPLEMENTACIÓN* — nombre y ubicación exactos del mapa de aristas:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
grep -rn "_REQUIRES_MAP_FROZEN\|_FROZEN_BOUNDS" tests/ services/ | head
```
Agregar **sólo** las aristas del 242. ⚠️ Esos mapas suelen estar **ya rojos por deuda ajena** (flags de otros planes sin registrar): **no** intentar arreglar las ajenas; verificar que **tu** entrada esté y que el fallo restante sea preexistente. **`[v2]` ⛔ (C20) PROHIBIDO `git stash` / `reset` / `rebase` / `checkout` en este árbol:** hay **sesiones paralelas vivas** que comparten el índice, y un `stash` puede tragarse trabajo ajeno sin commitear. v1 lo instruía tres veces como "prueba de ajenidad". La prueba **segura** es no tocar el árbol: `git diff --name-only` ⇒ si el archivo del fallo **no** aparece en tu diff, el fallo es preexistente. Si necesitás correr el test contra la base: `git show HEAD:backend/tests/test_harness_flags.py > "$env:TEMP\base_flags.py"` y corré sobre esa copia.

**(4) `backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON`** (`:467`) (G11). Las **7** declaran `default=` ⇒ las **7** van acá. Sin esto, `test_default_known_only_for_curated` queda rojo.

**(5) `deployment/export_harness_defaults.py` → `harness_defaults.env`.** ⚠️ **PROHIBIDO editar `harness_defaults.env` a mano**: se genera. Además está **congelado desde 2026-07-18 y ya rojo por deuda ajena** (le faltan flags de planes previos, p. ej. las de `db_compare`). Regla para este plan: **NO regenerarlo** (regenerarlo arrastraría deuda ajena a tu diff). Declarar en el PR que las 7 flags del 242 no están en el `.env` exportado por la misma razón que las de los planes 176–241.
*A VERIFICAR EN IMPLEMENTACIÓN:*
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
ls deployment/export_harness_defaults.py
grep -c "STACKY_COST_" deployment/harness_defaults.env
```

**Configurabilidad desde la UI (requisito duro del repo):** al estar en `FLAG_REGISTRY` con `label` y `description` en español y una `group`/categoría válida, las 7 aparecen automáticamente en **Configuración → Arnés → Observabilidad** y se editan desde ahí. No hace falta ningún código de UI adicional. **Ninguna es `env_only`.**

#### F8.3 Test anti-dependencias (por AST, no por regex) — `backend/tests/test_plan242_no_new_deps.py`

```python
"""Plan 242 KPI-4 — ningun modulo nuevo importa numpy/sklearn/scipy/pandas.
Se verifica por AST y NO por regex: un regex sobre texto da falsos positivos
(un comentario o un string que diga 'numpy') y falsos negativos (un import
dentro de una funcion, indentado). El AST ve los imports REALES, esten donde
esten."""
import ast
from pathlib import Path

_PROHIBIDOS = {"numpy", "sklearn", "scipy", "pandas", "torch", "statsmodels"}
_MODULOS = (
    "services/cost_signals.py", "services/cost_stats.py", "services/cost_scoring.py",
    "services/cost_model.py", "services/cost_model_eval.py",
    "services/cost_forecast_ledger.py", "services/cost_model_hooks.py",
)


def _imports_de(path: Path) -> set[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                nombres.add(a.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                nombres.add(nodo.module.split(".")[0])
    return nombres
```

| Caso | Qué verifica |
|---|---|
| `test_ningun_modulo_nuevo_importa_dependencia_prohibida` | **KPI-4**, parametrizado sobre los 7 módulos |
| `test_los_7_modulos_existen` | que el test no pase por archivo faltante (anti-falso-verde) |
| `test_cost_signals_no_importa_cost_analytics` | anti-ciclo (F0.1) |
| `test_cost_stats_no_importa_db_ni_models` | pureza de F1 |
| `test_cost_scoring_no_importa_random_ni_red` | determinismo de F2 |
| `test_ningun_modulo_nuevo_importa_requests_socket_subprocess` | **G3** |
| `test_requirements_txt_no_cambio` | el archivo tiene exactamente las 14 líneas de dependencia previas |

#### F8.4 Test de no-degradación — `backend/tests/test_plan242_flags_off.py`

| Caso | Qué verifica |
|---|---|
| `test_las_7_flags_estan_en_el_registry` | las 7 keys presentes en `FLAG_REGISTRY` |
| `test_las_7_flags_estan_categorizadas` | **G12**, en `_CATEGORY_KEYS["observabilidad_notif"]` |
| `test_las_7_flags_estan_en_curated_defaults_on` | **G11** |
| `test_las_2_flags_int_declaran_bounds` | **G13**, `min_value` y `max_value` no nulos |
| `test_default_efectivo_es_on_para_las_5_bool` | leyendo de `config.config`, **no** del módulo (**G10**) |
| `test_ninguna_flag_es_env_only` | configurable desde la UI |
| `test_todas_las_flags_tienen_label_y_description_en_espanol` | |
| `test_con_todas_off_los_6_endpoints_devuelven_enabled_false` | **G16** |
| `test_con_todas_off_cost_summary_es_identico_al_142` | **G16**: se compara el JSON de `/cost-summary` con y sin el plan (fixture de records fija) ⇒ **idéntico** |
| `test_con_todas_off_no_se_escribe_ningun_archivo` | monkeypatch de `open` en modo escritura sobre `data_dir()` ⇒ 0 llamadas |
| `test_con_todas_off_el_post_hook_no_entrena` | |
| `test_flag_leida_del_modulo_daria_el_default` | **G10** documentado como test: prueba que `getattr(config_module, K)` ≠ `getattr(config.config, K)` cuando la instancia se cambió — el test que impide el bug clásico |

#### F8.5 Test de paridad de runtimes — `backend/tests/test_plan242_runtime_parity.py`

Fixture con **3 ejecuciones sintéticas**, una por runtime, con metadata realista.

| Caso | Qué verifica |
|---|---|
| `test_los_3_runtimes_producen_signal_row` | F0 en los 3 |
| `test_los_3_runtimes_aparecen_en_stats` | F1: `by_dimension["runtime"]` tiene 3 claves |
| `test_copilot_va_a_nominal_only_y_no_a_billable_only` | **G7**, **KPI-10** |
| `test_los_3_runtimes_reciben_score` | F2 en los 3 |
| `test_copilot_score_excluye_componentes_de_precio` | `cost_position` y `unit_cost` en `None` |
| `test_copilot_no_entra_al_entrenamiento` | **G7**: `collect_training_rows` no lo devuelve |
| `test_los_3_runtimes_reciben_forecast` | F3 en los 3 |
| `test_forecast_copilot_billable_false_y_rotulado` | **KPI-10** |
| `test_fallback_declarado_por_runtime_sin_telemetria` | un runtime sin `harness_telemetry` ⇒ señales `None`, forecast por L3/L4, **nunca** ceros inventados |
| `test_calibracion_separa_copilot_del_mae_facturable` | F5 |

#### F8.6 Ratchet — registro obligatorio de los **13** archivos de test (G9)

> **`[v2]` (C11 · C13):** v1 titulaba *"los 12 archivos"* y a renglón seguido listaba **13** y exigía
> `grep -c` ⇒ 13. Son **13**. Y con el corte de §0.3, **5** se registran en el 242
> (`cost_signals`, `cost_stats`, `cost_scoring`, `cost_api`, `flags_off`) y los **8** restantes en el plan
> siguiente. El `grep -c` del DoD se ajusta a la mitad que corresponda: **5** ahora, 13 cuando ambos
> planes estén.

Se agregan al bloque `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` (junto a las líneas 390–396) **y** al bloque gemelo de `backend/scripts/run_harness_tests.ps1`:

```
  tests/test_plan242_cost_signals.py
  tests/test_plan242_cost_stats.py
  tests/test_plan242_cost_scoring.py
  tests/test_plan242_cost_features.py
  tests/test_plan242_cost_model.py
  tests/test_plan242_cost_model_perf.py
  tests/test_plan242_cost_model_eval.py
  tests/test_plan242_forecast_ledger.py
  tests/test_plan242_cost_hooks.py
  tests/test_plan242_cost_api.py
  tests/test_plan242_no_new_deps.py
  tests/test_plan242_flags_off.py
  tests/test_plan242_runtime_parity.py
```
(13 archivos.)

#### F8.7 Aceptación (BINARIA)

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_plan242_no_new_deps.py -q
.venv\Scripts\python.exe -m pytest tests\test_plan242_flags_off.py -q
.venv\Scripts\python.exe -m pytest tests\test_plan242_runtime_parity.py -q
.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests\test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q
```
Y:
```powershell
grep -c "test_plan242" scripts/run_harness_tests.sh
grep -c "test_plan242" scripts/run_harness_tests.ps1
```
⇒ **13 en cada uno**.

⚠️ **Deuda ajena esperada:** `tests/test_harness_flags_help.py` tiene **4 fallos preexistentes ajenos**. Regla: verificá **tu** entrada por separado (las 7 flags del 242 deben pasar su validación individual de ayuda) y **no** intentes arreglar las 4 ajenas. **`[v2]`** Prueba de ajenidad **segura** (⛔ **nunca** `git stash` acá — C20): `git diff --name-only` no incluye `tests/test_harness_flags_help.py` ⇒ los 4 fallos son preexistentes.

**Flag que la protege:** las 7 se protegen a sí mismas.
**Impacto por runtime:** ninguno (es cableado).
**Trabajo del operador: ninguno** (todo nace ON y editable desde la UI).

---

### F9 — (OPCIONAL, no bloquea el DoD) Badge de estimación pre-run donde se lanza el agente

**Objetivo (1 frase):** mostrar el rango P10–P90 al lado del botón que lanza el agente, para que el operador decida con el número a la vista.
**Valor:** es donde la predicción deja de ser un panel y se vuelve una decisión. Se aísla en su propia fase **porque el punto de integración exacto no está verificado** y no debe bloquear las 8 fases anteriores.

#### F9.1 Lo que SÍ está verificado

- Ya existe una estimación pre-run: `POST /api/agents/estimate` ⇒ `backend/api/agents.py:1388` `def estimate_cost()`, que llama `cost_estimator.estimate(...)` en `agents.py:1405` y devuelve además `cache_hit`.
- `CostBadge` (`frontend/src/components/costcenter/CostBadge.tsx:18`) recibe **sólo** `{ kind: CostKind }` (`CostBadgeProps` en `:6`) y hoy se usa en un único lugar: `CostTable.tsx:125`.

**Consecuencia:** `CostBadge` **no** sirve tal cual para mostrar un rango en USD. La forma correcta es un componente nuevo `CostForecastBadge.tsx` que **reusa** `CostBadge` internamente para el chip de tipo y agrega el rango, la confianza y el origen.

#### F9.2 Lo que NO está verificado — **A VERIFICAR EN IMPLEMENTACIÓN**

Dónde exactamente el operador lanza un agente en la UI, y si esa pantalla ya consume `/api/agents/estimate`:
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
grep -rn "agents/estimate\|/estimate" src/api/endpoints.ts src/pages/ src/components/
grep -rln "Ejecutar\|Lanzar\|Run agente\|runAgent" src/components/ src/pages/ | head -20
```
**Prohibido inventar la ruta del archivo.** La implementación debe (1) correr esos dos comandos, (2) elegir **el** call-site real donde el operador confirma el lanzamiento, (3) anotarlo en este documento antes de tocar código.

#### F9.3 Trabajo de la fase, una vez identificado el call-site

| Acción | Ruta |
|---|---|
| **CREAR** | `frontend/src/components/costcenter/CostForecastBadge.tsx` + `.module.css` |
| **EDITAR** | el call-site identificado en F9.2 (una sola inserción del componente) |
| **EDITAR** | `frontend/src/lib/costForecast.logic.ts` (agregar `forecastBadgeText(p: CostPrediction): string`) |
| **EDITAR** | `frontend/src/lib/__tests__/costForecast.logic.test.ts` (4 casos nuevos) |

El componente llama `CostCenter.forecast({ ticket_id, agent_type, runtime, model })` con react-query, muestra `formatUsdRange(...)` + `confidenceLabel(...)` + `sourceLabel(...)`, y guarda el `forecast_id` para que, al lanzar, se llame `bind_execution`.

*A VERIFICAR EN IMPLEMENTACIÓN* — cómo el frontend obtiene el `execution_id` recién creado para poder ligarlo:
```powershell
grep -rn "execution_id" src/api/endpoints.ts | head -20
```
Si la respuesta de lanzamiento **no** devuelve `execution_id`, esta parte del lazo queda pendiente y se declara así en el doc; el ledger sigue registrando la apertura (que ya sirve para `n_forecasts` y `n_open`), sólo que sin cierre automático para esos casos.

#### F9.4 Casos borde

1. Endpoint apagado ⇒ el badge **no se renderiza** (nada roto, nada vacío).
2. Error de red ⇒ el badge no se renderiza; **jamás** bloquea el botón de lanzar (**G15**).
3. `confidence === "muy_baja"` ⇒ se muestra "estimación gruesa" en vez de un número con falsa precisión.
4. Copilot ⇒ "nominal — no facturable".

#### F9.5 Aceptación (BINARIA)

1. `npx vitest run src/lib/__tests__/costForecast.logic.test.ts` ⇒ **23/23** (19 de F7 + 4 nuevos).
2. `npx tsc --noEmit` ⇒ 0 errores.
3. `grep -c "style={{" src/components/costcenter/CostForecastBadge.tsx` ⇒ **0**.
4. Smoke visual **manual**: abrir el call-site, ver el rango, lanzar el agente, y confirmar en `/costcenter/prediccion` que la calibración sumó un par.

**Flag que la protege:** `STACKY_COST_FORECAST_ENABLED` (la misma; no se agrega una octava flag).
**Impacto por runtime:** los 3 muestran badge; Copilot con el rótulo de no facturable.
**Trabajo del operador: ninguno** (el badge aparece solo).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Por qué es real acá | Mitigación **concreta** (y dónde vive) |
|---|---|---|---|
| **R1** | **Sobreajuste del modelo.** Con pocas muestras y ~40 features, el ridge puede memorizar el ruido y dar un MAE de entrenamiento excelente y un MAE real pésimo. | 40 features contra 50 filas es sobreajuste garantizado. | (a) **Split temporal** obligatorio: el MAE reportado se mide **sólo** sobre datos que el modelo nunca vio (§F4.2). (b) **Ridge con λ=1,0** encoge los pesos. (c) **Gate de promoción** al 5 % de margen: si no le gana al baseline trivial, no se usa (§F4.4). (d) `_MIN_SAMPLES=30` como piso duro. (e) Vocabulario de one-hot con bucket `"otros"`, para que categorías raras no generen columnas de 1 sola fila. |
| **R2** | **Deriva de precios.** Los proveedores cambian tarifas; un modelo entrenado con precios viejos predice barato para siempre. | `harness/pricing.py:24` `DEFAULT_PRICES` es una tabla estática (override por `STACKY_PRICING_JSON`). | (a) `input_price_per_mtok` es **un feature del modelo**: si el precio cambia, el feature cambia y la predicción se mueve **sin reentrenar**. (b) El autotrain (cada 10 runs, máx. 1 cada 30 min) hace que el modelo absorba la deriva en horas, no en meses. (c) `trained_at` se muestra en la UI: un modelo viejo es **visible**. (d) `cohort_medians` se recalculan en cada entrenamiento. |
| **R3** | **Datos escasos al inicio.** Una instalación nueva no tiene histórico y el estimador no tiene nada que decir. | Es el estado del día 1 de cualquier deploy. | El **fallback jerárquico de 4 niveles** (§F3.5) es exactamente la respuesta: L4 (heurística de `pricing`/`cost_estimator`) funciona con 0 filas. La UI muestra `confidence="muy_baja"` y el texto "Sin histórico — estimación gruesa": el sistema **dice que no sabe** en vez de inventar precisión. |
| **R4** | **Costo computacional del entrenamiento.** Un entrenamiento lento en el post-hook degradaría el fin de cada ejecución. | Python puro sobre 20.000 filas puede ser lento si se implementa denso. | (a) **KPI-7** con test de pared (< 2,0 s). (b) **Representación dispersa** obligatoria + one-hot sin z-score (§F3.2): 13× menos operaciones. (c) **Debounce doble**: cada N ejecuciones **y** máx. 1 cada 30 min (`_AUTOTRAIN_MIN_INTERVAL_S=1800`). (d) El hook **nunca propaga excepciones** ni bloquea (`ticket_status.py:313`). (e) Escape hatch declarado: si el test falla, `_TRAIN_MAX_ROWS` baja a 8000 (§F3.10) — regla, no improvisación. |
| **R5** | **El operador confunde estimación con factura.** Ve "0,34 USD" y lo trata como un cargo real. | Es el riesgo de producto más caro del plan: erosiona la confianza en TODO el Centro de Costos. | (a) **G6**: `cost_kind` de una predicción es **siempre** `"forecast"`, un valor que `_billable()` no reconoce ⇒ **nunca** puede sumarse a `billable_usd`, ni por accidente. (b) La UI muestra **rango**, no punto: "0,18 – 0,74 USD (mediana 0,34)" — un rango no se lee como una factura. (c) `confidence` y `source` visibles siempre. (d) Las predicciones viven en un **sub-tab propio** ("Predicción"), separadas del resumen histórico. (e) Test dedicado: `test_forecast_no_entra_en_billable`. |
| **R6** | **Falso verde del backtesting.** El propio evaluador podría estar mal y aprobar cualquier cosa. | Es el riesgo clásico de "escribí el test y el código, los dos con el mismo error". | Test **negativo obligatorio**: `test_NO_promueve_cuando_pierde` genera datos donde `y` es **ruido puro sin relación con las features** y verifica que el gate **rechaza**. Un evaluador roto que aprueba todo hace fallar ese test. Complementado por `test_cobertura_fuera_de_rango_bloquea_promocion` (§F4.6). |
| **R7** | **Copilot envenena las métricas.** Su costo nominal, sumado a los reales, infla los totales y sesga el modelo hacia abajo. | `github_copilot` **siempre** produce un número (`cost_analytics.py:106-108`), aunque nadie lo pague. | (a) **G7** codificado en 4 lugares: excluido de `_billable`, separado en `nominal_only` (§F6.4), excluido del entrenamiento (§F3.3), y `billable=False` en su `CostPrediction`. (b) `test_plan242_runtime_parity.py` verifica los 4. |
| **R8** | **Colisión de merge con los planes 171/199.** Los tres tocan `api/metrics.py` y `harness_flags.py`. | Ya pasó en este repo: un merge 3-way **no marca conflicto** si dos ramas agregan la misma línea de cierre, dejando un duplicado silencioso. | (a) §4 declara la frontera. (b) Los endpoints del 242 son **apéndice puro** (criterio de aceptación: 0 líneas eliminadas en `metrics.py`, §F6.7). (c) Después de CADA merge: `pytest tests/test_harness_flags.py -q`, `tests/test_harness_ratchet_meta.py -q` y `python -m compileall backend/api/metrics.py`. |
| **R9** | **`[v2]` (C5) El ledger crece sin control, se corrompe, o dos hilos escriben a la vez.** v1 no tenía lock: `record_forecast` corre en el hilo HTTP y `close_forecast` en el del post-hook. | Escritura en cada predicción y en cada fin de ejecución, desde **dos hilos distintos**. | (a) **`_LOCK = threading.Lock()`** alrededor de toda lectura/escritura, como en `ci_run_ledger.py:19`. (b) Cap **`MAX_ROWS = 500`** con reescritura atómica (`tmp.replace(path)`) conservando las más nuevas — **sin rotación**, que en v1 hacía perder la ventana de 30 días de un saque. (c) **Allowlist `ENTRY_FIELDS`**: una clave fuera del contrato no se persiste, así no se filtra un secreto por accidente. (d) Línea corrupta ⇒ se saltea y se **reporta** en `skipped_lines`. (e) Fallo de disco ⇒ warning y la UI sigue funcionando. (f) Tests dedicados (§F5.7). |
| **R10** | **Un modelo menor implementa mal el álgebra.** Eliminación gaussiana escrita a mano es el lugar clásico de los errores silenciosos. | El plan lo pide explícitamente en Python puro. | (a) Pseudocódigo **completo**, línea por línea, con pivoteo parcial y Gauss-Jordan (§F3.4) — sin sustitución hacia atrás, que es donde más se equivoca. (b) Tests con **soluciones calculadas a mano** (`test_solve_linear_sistema_2x2_conocido`) y un caso que **exige** pivoteo. (c) `test_fit_ridge_recupera_relacion_lineal_sintetica`: si el álgebra está mal, no recupera (2, 3). (d) `SingularMatrixError` capturada ⇒ el sistema cae al fallback en vez de romper. |
| **R11** | **Escritura del modelo interrumpida deja un JSON truncado.** | Corte de energía / kill del proceso durante `save_model`. | Escritura atómica obligatoria (`.tmp` + `os.replace`), con test que verifica que `os.replace` se llama exactamente una vez. Y `load_model` tolera JSON corrupto devolviendo `None` (§F3.7). |
| **R12** | **El scoring se percibe como arbitrario.** Un número 0–100 sin explicación genera desconfianza y se ignora. | Es lo que le pasa a todo "health score" mal hecho. | (a) **KPI-2**: toda puntuación trae razones **con el número que la justifica**. (b) Pesos publicados, explícitos y sumando 1,00, con test. (c) `weights_used` expone la renormalización real aplicada. (d) `confidence` avisa cuando la cohorte es chica. (e) Cero LLM: la explicación es la fórmula, no una narración generada. |

---

## 7. Fuera de scope (lo que este plan NO hace, a propósito)

1. **No cosecha telemetría desde disco.** Nada de leer transcripts, `.jsonl` de sesión ni directorios de runtime. Eso es del **Plan 199** (§4).
2. **No define baselines de salud operativa** (latencia, tasa de error, colas) ni alertas. Eso es del **Plan 171** (§4).
3. **No toca el legacy.** `_execution_costs` (`metrics.py:52`), `/ticket-costs` (`:77`) y `/project-costs` (`:130`) quedan **exactamente** como están, igual que en el Plan 142.
4. **No borra `cost_estimator.py`.** Sigue vivo como nivel L4 del fallback y como motor de `POST /api/agents/estimate` (`api/agents.py:1388`).
5. **No agrega tablas ni migraciones alembic.** Las dos escrituras son archivos en `data_dir()` (§F5.1).
6. **No usa LLM para nada.** Ni para el scoring, ni para las explicaciones, ni para el modelo. Todo es aritmética determinista.
7. **No optimiza automáticamente nada.** No elige modelo, no cancela runs caros, no cambia `effort`, no bloquea ejecuciones. **G15**: el modelo informa, el operador decide.
8. **No hace clasificación ni predicción de éxito/fracaso.** Sólo estima **costo en USD**.
9. **No implementa redes neuronales, boosting, ni validación cruzada k-fold.** Un ridge lineal con split temporal y gate de promoción es lo que corresponde al volumen de datos de un sistema mono-operador; cualquier cosa más compleja sería sobreajuste con más pasos.
10. **No corrige la deuda ajena** de `harness_defaults.env`, `test_harness_flags_help.py` ni los mapas congelados de bounds/requires (§F8.2, §F8.7).
11. **No genera tests de render de componentes React.** El frontend no tiene jsdom/@testing-library configurados (**G8**); el smoke visual es **manual** y está declarado como tal.
12. **No cambia el contrato de `CostRow`** (Plan 142 F0). Las señales nuevas viven en `SignalRow` y en campos con default de `ExecRecord`.

---

## 8. Glosario

**Términos del dominio Stacky:**

- **Runtime** — el ejecutor del agente: `codex_cli`, `claude_code_cli` o `github_copilot`. **No** es lo mismo que `LLM_BACKEND`.
- **`cost_kind`** — clasificación del origen del número de costo: `reported` (lo dijo el runtime), `estimated` (lo calculó `pricing.estimate_cost` desde tokens), `nominal` (suscripción plana, no se paga por uso), `unknown` (no hay dato). Este plan agrega un quinto valor **sólo para predicciones**: `forecast`.
- **Billable** — `reported` + `estimated`. `nominal` y `unknown` **nunca** son facturables (`cost_analytics.py:213`).
- **Cohorte** — grupo de ejecuciones comparables entre sí: en este plan, `"<agent_type>|<familia de modelo>"`. Es la referencia contra la que se dice si un run fue caro o barato.
- **Rework** — ejecutar el mismo agente sobre el mismo ticket más de una vez. Cuesta dinero real y este plan lo mide.
- **Familia de modelo** — el prefijo más largo de `harness/pricing.py:24` `DEFAULT_PRICES` que matchea el nombre del modelo (p. ej. `claude-sonnet`). Agrupa versiones del mismo modelo.
- **Flag curada** — `FlagSpec` que declara `default=` explícito y por eso debe estar en `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`).
- **Ratchet del arnés** — meta-test que exige que todo archivo de test nuevo esté registrado en `HARNESS_TEST_FILES`.
- **Post-hook de fin de ejecución** — callable registrado con `ticket_status.register_post_hook` (`backend/services/ticket_status.py:307`), que corre al terminar cualquier agente en cualquier runtime. Es **el** chokepoint runtime-agnóstico.

**Términos estadísticos (uno por línea, para que un modelo menor no tenga que inferir nada):**

- **Percentil p90** — el valor por debajo del cual cae el 90 % de las observaciones; acá se calcula por interpolación lineal sobre la lista ordenada (fórmula exacta en §F1.3).
- **Mediana (p50)** — el valor del medio: la mitad de los datos está por debajo. Resiste los extremos mucho mejor que el promedio.
- **Desvío estándar muestral** — cuánto se dispersan los datos alrededor del promedio, dividiendo por `n-1` (no por `n`); indefinido con menos de 2 datos.
- **IQR (rango intercuartílico)** — `Q3 - Q1`, o sea el ancho del 50 % central de los datos. Medida de dispersión que ignora las colas.
- **Valla de Tukey** — regla para marcar outliers: todo lo que cae fuera de `[Q1 - 1,5·IQR, Q3 + 1,5·IQR]`. Si `IQR = 0` la regla **no aplica** (no se declara ningún outlier).
- **MAD (desvío absoluto mediano)** — la mediana de `|x − mediana|`. Es la alternativa robusta al desvío estándar: un solo valor extremo no la mueve. Si `MAD = 0`, **no se divide** por ella.
- **CV (coeficiente de variación)** — `desvío / promedio`. Dispersión relativa, comparable entre magnitudes distintas. Indefinido si el promedio es 0.
- **Ridge (regresión con regularización L2)** — regresión lineal que penaliza pesos grandes sumando `λ·‖w‖²`. Sirve para dos cosas: evita el sobreajuste y garantiza que el sistema `(ZᵀZ + λI)w = Zᵀy` **siempre** tenga solución.
- **λ (lambda)** — la fuerza de esa penalización. Más grande ⇒ pesos más chicos ⇒ modelo más conservador. Acá vale `1.0`.
- **`log1p` / `expm1`** — `log(1+x)` y su inversa `e^x − 1`. Se usan para trabajar en escala logarítmica sin romperse con `x = 0`, que es lo que pasaría con `log(0)`.
- **Eliminación gaussiana con pivoteo parcial** — método exacto para resolver `A·w = b`: en cada columna se elige como pivote la fila con el valor absoluto más grande (eso es el "pivoteo parcial", y evita dividir por números casi cero), y se eliminan las demás filas.
- **Z-score (normalización)** — restar la media y dividir por el desvío, para que todas las features estén en la misma escala. Acá se aplica **sólo** a las 5 continuas; los one-hot ya están en 0/1.
- **One-hot** — codificar una categoría como un vector de ceros con un único 1 en la posición de esa categoría. Una categoría no vista cae en el bucket `"otros"`.
- **Feature disperso (sparse)** — representar una fila guardando **sólo** las posiciones distintas de cero, como `[(0, 4.6), (7, 1.0)]`. Es lo que hace que el entrenamiento en Python puro sea viable.
- **RMSLE (raíz del error cuadrático medio logarítmico)** — `sqrt(mean((log1p(real) − log1p(predicho))²))`. Castiga el error **relativo**: errarle por 0,10 USD en algo de 0,05 es gravísimo; en algo de 10 USD, no.
- **MAE (error absoluto medio)** — promedio de `|real − predicho|`, en USD. Es la métrica del gate de promoción porque se lee directo en dinero.
- **MAPE (error porcentual absoluto medio)** — promedio de `|real − predicho| / |real|`. Explota cuando `real ≈ 0`, por eso se saltean esas filas y se reporta cuántas se saltearon.
- **Cobertura del intervalo** — fracción de los valores reales que cayeron entre P10 y P90. Debería acercarse a 0,80. Muy por debajo ⇒ el intervalo miente por angosto; muy por encima ⇒ miente por ancho.
- **Predicción conformal (simple)** — construir el intervalo a partir de los **residuos empíricos** medidos en un set de calibración, en vez de asumir una distribución teórica. Concretamente: se toman los percentiles 10/50/90 de los residuos y se suman a la predicción puntual (§F3.6).
- **Split temporal** — partir los datos por **fecha**, no al azar: entrenar con lo viejo y evaluar con lo nuevo. Un split aleatorio filtraría información del futuro al pasado y daría un error falsamente bajo.
- **Baseline** — la predicción más tonta posible que igual es razonable; acá, "siempre la mediana global del entrenamiento". Si el modelo no le gana a esto, el modelo no sirve.
- **Gate de promoción** — la regla binaria que decide si el modelo entrenado pasa a `active` (se usa) o queda en `candidate` (no se usa). Acá exige ≥5 % de mejora de MAE **y** cobertura en `[0,60, 0,95]`.
- **Debounce** — limitar cuántas veces se dispara una acción en una ventana de tiempo. Acá: reentrenar como mucho 1 vez cada 30 minutos, sin importar cuántas ejecuciones terminen.

---

## 9. Orden de implementación

1. **F0** — `cost_signals.py` + campos con default en `ExecRecord` + `test_plan242_cost_signals.py`. **Gate:** los 6 archivos de test del 142/158 verdes **sin editarlos**.
2. **F1** — `cost_stats.py` + `test_plan242_cost_stats.py`.
3. **F2** — `cost_scoring.py` + `test_plan242_cost_scoring.py`. (Depende de F1: usa `percentile`.)
4. **F3** — `cost_model.py` + `test_plan242_cost_features.py` + `test_plan242_cost_model.py` + `test_plan242_cost_model_perf.py`. (Depende de F1 por `percentile` y de F2 por `model_family`.)
5. **F4** — `cost_model_eval.py` + `test_plan242_cost_model_eval.py`, y **recién acá** se cablea el gate dentro de `cost_model.train()`. **Gate:** `test_NO_promueve_cuando_pierde` verde.
6. **F5** — `cost_forecast_ledger.py` + `cost_model_hooks.py` + 2 archivos de test + 1 línea en `app.py`.
7. **F6** — 6 endpoints como apéndice de `api/metrics.py` + `test_plan242_cost_api.py`. **Gate:** `git diff api/metrics.py` sin líneas eliminadas.
8. **F8 (adelantada, antes que el frontend)** — las 7 flags en los 5 lugares + `test_plan242_no_new_deps.py` + `test_plan242_flags_off.py` + `test_plan242_runtime_parity.py` + registro de los 13 archivos en el ratchet. Se hace **antes** de F7 porque el frontend necesita que los endpoints estén encendidos por default para poder probarse a mano.
9. **F7** — sub-tabs, componentes, tipos, cliente API y `costForecast.logic.ts` + su test vitest. **Gate:** `tsc --noEmit` en 0 y el smoke visual manual.
10. **F9 (opcional)** — badge pre-run, **sólo después** de verificar el call-site real con los comandos de §F9.2.

**Regla de corte:** si en cualquier punto un gate no da verde, **no se avanza a la fase siguiente**. Un plan a medias con tests rojos es peor que un plan a medias con tests verdes y menos fases.

---

## 10. Definición de Hecho (DoD) global

### 10.1 Tests (todos por archivo, con `backend\.venv\Scripts\python.exe`)

> **`[v2]` DOS CORRECCIONES AL DoD (C11 · C13).**
>
> **(a) El criterio binario es «0 failed / 0 errors», no un conteo exacto.** Varios casos son
> `parametrize` (`test_load_falta_clave_obligatoria` sobre 8 claves, `test_cost_stats_flag_off` sobre 6
> endpoints, `test_los_8_endpoints_de_costo_siguen_iguales` sobre 8): pytest reporta **más** tests que
> filas tiene la tabla, así que un `N/N` fijo es inalcanzable por construcción y se vuelve rojo el día
> que alguien parametriza uno más. Los números de abajo son **la cantidad de casos que la tabla de la
> fase debe listar** (cobertura), no el conteo de pytest.
>
> **(b) Este DoD es del plan COMPLETO (F0..F9).** Con el corte de §0.3, el DoD del **242** son
> **sólo** las 5 primeras filas + el vitest; las 8 restantes son del plan siguiente.

**DoD del 242 (tras el corte):**

- [ ] `tests\test_plan242_cost_signals.py` — 18 casos (16 de v1 + 2 nuevos de C2/C3)
- [ ] `tests\test_plan242_cost_stats.py` — 33/33 verdes
- [ ] `tests\test_plan242_cost_scoring.py` — 34/34 verdes
- [ ] `tests\test_plan242_cost_features.py` — 16/16 verdes
- [ ] `tests\test_plan242_cost_model.py` — **37** casos (**`[v2]` C11:** v1 decía 38; la tabla de §F3.10 lista 37) *(plan siguiente)*
- [ ] `tests\test_plan242_cost_model_perf.py` — 2/2 verdes
- [ ] `tests\test_plan242_cost_model_eval.py` — 22/22 verdes
- [ ] `tests\test_plan242_forecast_ledger.py` — 16/16 verdes
- [ ] `tests\test_plan242_cost_hooks.py` — 9/9 verdes
- [ ] `tests\test_plan242_cost_api.py` — 24/24 verdes
- [ ] `tests\test_plan242_no_new_deps.py` — 7/7 verdes
- [ ] `tests\test_plan242_flags_off.py` — 12/12 verdes
- [ ] `tests\test_plan242_runtime_parity.py` — 10/10 verdes
- [ ] `npx vitest run src/lib/__tests__/costForecast.logic.test.ts` — 19/19 verdes (23/23 si se hizo F9)

### 10.2 No-regresión (verdes **sin editar los archivos**)

- [ ] `tests\test_cost_analytics_extract.py`
- [ ] `tests\test_cost_analytics_aggregate.py`
- [ ] `tests\test_cost_center_api.py`
- [ ] `tests\test_cost_reconciliation_audit.py`
- [ ] `tests\test_cost_codeburn_import.py`
- [ ] `tests\test_plan158_claude_cli_cost_parity.py`
- [ ] `npx vitest run src/lib/__tests__/costCenter.logic.test.ts`
- [ ] `git diff --stat` sobre esos 7 archivos ⇒ **0 líneas modificadas**

### 10.3 Arnés de flags y ratchet

- [ ] `tests\test_harness_flags.py` verde (o el único delta rojo es deuda ajena demostrada con `git diff --name-only` — **`[v2]`** ⛔ **nunca** con `git stash`, C20)
- [ ] `tests\test_harness_flags_requires.py` verde
- [ ] `tests\test_harness_ratchet_meta.py` verde
- [ ] `grep -c "test_plan242" scripts/run_harness_tests.sh` ⇒ **13**
- [ ] `grep -c "test_plan242" scripts/run_harness_tests.ps1` ⇒ **13**
- [ ] Las 7 flags aparecen en **Configuración → Arnés → Observabilidad** y se editan desde ahí (verificación visual manual)
- [ ] `harness_defaults.env` **NO** fue regenerado (deuda ajena congelada)

### 10.4 Guardarraíles duros

- [ ] `grep -cE "^(import|from) (numpy|sklearn|scipy|pandas)" services/cost_*.py` ⇒ **0**
- [ ] `backend/requirements.txt` sin cambios (`git diff --stat backend/requirements.txt` ⇒ vacío)
- [ ] `git diff backend/api/metrics.py | grep "^-" | grep -v "^---"` ⇒ **0 líneas eliminadas**
- [ ] `grep -cE "def (_execution_costs|ticket_costs|project_costs)" backend/api/metrics.py` ⇒ **3** (legacy intacto)
- [ ] `grep -c "agent_completion" backend/services/cost_model_hooks.py` ⇒ **0** (chokepoint correcto)
- [ ] `grep -c "style={{" ` sobre los `.tsx` nuevos de `components/costcenter/` ⇒ **0** en todos
- [ ] `grep -cE "#[0-9a-fA-F]{3,8}"` sobre los `.module.css` nuevos ⇒ **0** en todos
- [ ] `npx tsc --noEmit` ⇒ 0 errores
- [ ] `python -m compileall backend/services backend/api` ⇒ sin errores

### 10.5 KPIs

- [ ] **KPI-1** 6 métricas × 6 dimensiones
- [ ] **KPI-2** toda puntuación con razones numéricas
- [ ] **KPI-3** determinismo 50/50
- [ ] **KPI-4** cero dependencias nuevas (por AST)
- [ ] **KPI-5** el gate promueve cuando gana y **rechaza cuando pierde**
- [ ] **KPI-6** cobertura fuera de `[0,60; 0,95]` bloquea la promoción
- [ ] **KPI-7** entrenamiento de 20.000 filas en < 2,0 s
- [ ] **KPI-8** par abierto+cerrado produce calibración real
- [ ] **KPI-9** cero regresión del 142/158
- [ ] **KPI-10** los 3 runtimes con payload completo y Copilot correctamente segregado
- [ ] **KPI-11** cero pasos manuales para el operador

### 10.6 Smoke visual **manual** (declarado como manual, no automatizable — G8)

- [ ] `/costcenter` se ve **idéntico** a antes del plan
- [ ] `/costcenter/estadisticas` muestra percentiles, histograma, box plot, outliers, cache y rework, con los bloques "Facturable" y "Nominal" separados
- [ ] `/costcenter/scoring` muestra notas A–E con razones legibles en español
- [ ] `/costcenter/prediccion` muestra el estado del modelo; el botón "Entrenar ahora" responde en < 3 s y actualiza `trained_at`
- [ ] Un forecast sobre un ticket real devuelve un rango con su origen y su confianza
- [ ] F5 en cada sub-tab aterriza en el mismo sub-tab (deep-link del contrato del Plan 165)
- [ ] Con las 7 flags en OFF desde la UI, el Centro de Costos vuelve a ser exactamente el del Plan 142

### 10.7 Documentación

- [ ] El encabezado **de este documento** se actualiza a `**Estado:** IMPLEMENTADO` con la fecha y el commit
- [ ] Cada fase F0..F9 queda marcada `[HECHA]` o `[PENDIENTE]` dentro del propio documento
- [ ] Los puntos marcados **A VERIFICAR EN IMPLEMENTACIÓN** quedan **resueltos y anotados** con la respuesta real (ruta, símbolo o "no existe"), no borrados

---

**Fin del Plan 242.**


---
