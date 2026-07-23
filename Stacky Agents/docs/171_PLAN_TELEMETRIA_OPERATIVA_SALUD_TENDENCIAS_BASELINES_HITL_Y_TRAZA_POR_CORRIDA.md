# Plan 171 — Telemetría operativa: salud y tendencias por agente/runtime/modelo, baselines deterministas con avisos HITL y traza por corrida

**Estado:** CRITICADO v2 — APROBADO-CON-CAMBIOS — 2026-07-23 (v1 PROPUESTO 2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode · **Juez v2:** StackyArchitectaUltraEficientCode

### CHANGELOG v1 -> v2 (crítica adversarial 2026-07-23)

- **C1 (staleness post-consolidación 2026-07-20):** el v1 declaraba 158 "sin implementar", serie RSI 167-170 "SOLO PROPUESTA" y 152-156/163-165 "pendientes". HOY: **158 IMPLEMENTADO+AUDITADO** (evidencia: `services/cost_analytics.py:547` `_BACKFILL_MAX_ROWS` + flags Plan 158 en `harness_flags.py:272-273`), **RSI 167-170 MERGEADA** (`services/evolution_cycle.py`), 152/153/154/156/163/164/165 mergeados. Reescritos: intro, deps, "Ortogonal a", §2, §4.1, §8.1, §8.3, F7, tabla KPI.
- **C2 (contrato RSI muerto → consumidor real):** `evolution_signals()` ya tiene consumidor vivo: `evolution_cycle.collect_signals()` (`:57`). Nueva **F2b [ADICIÓN ARQUITECTO]**: `signals["ops"]` aditivo con try/except + test.
- **C3 (group= contradictorio y falso):** el v1 hardcodeaba `group="observabilidad_notif"` "verificado"; el real de `STACKY_COST_CENTER_ENABLED` es `group="observabilidad"` (`harness_flags.py:1681`) y el 199 ya unificó ahí (su C2). Corregidos los 3 FlagSpec de F0. La tupla de `_CATEGORY_KEYS` del ancla sigue siendo la de `"observabilidad_notif"` (divergencia categoría/grupo PREEXISTENTE del sustrato; no se corrige acá).
- **C4 (reuso ignorado — Plan 46):** existe `services/operational_health.py` + `/api/diag/operational-health` (`api/diag.py:623`) con detección de zombies cuyo default es `EXECUTION_TIMEOUT_MINUTES` (fuente única). R-O4 ahora hereda ese default (`stall_minutes: null` = default del sistema) y se delimita el prior art.
- **C5 (colisión de merge con 199):** nueva §8.4 con la frontera espejo del 199 §9-10: orden de inserción determinista en `CostCenterPage.tsx`, rebase aditivo de `ExecRecord`/`CostFilters`, delimitación de gráficos.
- **C6 (naming near-collision):** notas de desambiguación vs `STACKY_EXECUTION_TRACE_ENABLED` (captura runner-side), `STACKY_LIVE_TELEMETRY_ENABLED` y `STACKY_OPERATIONAL_HEALTH_ENABLED` en F0.
- **C7 (anclas numéricas drifteadas):** refrescadas a lo verificado 2026-07-23 (`endpoints.ts:1464`, drawer `:108`, `harness_flags.py:270-271/:1672-1681`).
- **C8 (`datetime.utcnow()` deprecado py3.13):** helper congelado `_utcnow()` naive-UTC en `run_signals.py`, usado en todo el plan (el sustrato es naive-UTC: `cost_analytics.py:173`).
- **C9 [ADICIÓN ARQUITECTO] (traza más rica gratis):** §4.9 surfacea `agent_name`/`prompt_sha` que los runners YA persisten (`agent_runner.py:33` `_build_trace_metadata`, gated `STACKY_EXECUTION_TRACE_ENABLED`).
**Directiva del operador (2026-07-18):** telemetría avanzada que MEJORE EL USO de la
herramienta y sea una EVOLUCIÓN, no un fix puntual. Recorte elegido: convertir la
telemetría que YA existe (y hoy solo alimenta costos, Plan 142) en **señal operativa
determinista**: salud y tendencias por agente×runtime×modelo (tasas de fallo, percentiles
de duración, series diarias), **detección determinista de regresiones contra baseline**,
**umbrales/presupuestos que AVISAN (jamás actúan)** y una **traza estructurada por
corrida** — más el aporte aditivo `signals["ops"]` al Centro de Evolución (Plan 167,
IMPLEMENTADO y mergeado 2026-07-20), que su `collect_signals()` ya existente incorpora
con degradación graciosa (F2b).

> Este documento está redactado para que un **MODELO MENOR** (Haiku, Codex CLI o
> GitHub Copilot Pro) lo implemente **SIN inferir nada**. Los nombres de símbolos,
> rutas, shapes JSON, literales de mensajes y comandos son **LITERALES**: prohibido
> desviarse de los nombres exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya
> fue decidido acá. Cada afirmación sobre código existente está anclada a
> `archivo:línea` **re-verificada el 2026-07-23** (post-consolidación de 158 commits a
> main del 2026-07-20); este repo tiene sesiones paralelas con
> WIP ajeno vivo (p. ej. `runtime_paths.py` y `scripts/run_harness_tests.sh` aparecen
> modificados hoy), así que TODA edición se ancla por el CONTENIDO/símbolo citado,
> nunca solo por el número de línea. Los comandos con `&&` se ejecutan en **Git Bash**
> (en PowerShell 5.1 `&&` es error de parser).

**Dependencias (re-verificadas 2026-07-23 post-consolidación; ninguna dura — el plan reusa, no bloquea):**

| Sustrato | Anclaje verificado | Rol en el 171 |
|---|---|---|
| Extractor canónico de costos (Plan 142, IMPLEMENTADO) | `backend/services/cost_analytics.py:31` (`_SUBSCRIPTION_RUNTIMES`), `:34-43` (`CostRow`: `runtime/model/tokens_in/tokens_out/cache_read_tokens/cost_usd/cost_kind/cache_savings_usd`), `:77-127` (`extract_cost_row`, `model` en `:86`), `:134` (`_MAX_ROWS=20000`), `:137-150` (`ExecRecord`, campo opcional-aditivo precedente `raw_metadata` `:147-150`), `:153-164` (`CostFilters`), `:167-210` (`load_records`: UNA query acotada por `started_at`), `:213` (`_billable`) | F1: fuente ÚNICA de registros; F1 agrega el campo aditivo `completed_at` a `ExecRecord` (mismo patrón que `raw_metadata`) |
| Blueprint de métricas | `backend/api/metrics.py:31` (`bp = Blueprint("metrics", __name__, url_prefix="/metrics")`), `:52` (`_execution_costs` LEGACY — NO tocar), `:352` (`/harness-health`), `:565-566` (`_cost_center_enabled` con `getattr(_cfg, ...)`), `:569-573` (`/cost-center/health` SIEMPRE 200), `:576-619` (`_parse_date`/`_parse_filters`/`_filters_or_error` — se REUSAN tal cual), `:622-625` (`/cost-summary`; flag OFF → `{"enabled": False}, 200`) | F4: los endpoints nuevos viven en este MISMO blueprint y espejan sus patrones |
| Salud agregada existente (prior art) | `backend/services/harness_health.py:25` (`_ALL_RUNTIMES`), `:26` (`_TERMINAL = {"completed", "needs_review", "error"}`), `:30-75` (`RuntimeStats`: tasas por runtime, SIN duraciones/percentiles/series/baselines), `:210` (`compute_health`) | Delimitación §2: el 171 NO toca `compute_health`; agrega la dimensión que falta (tiempo, tendencia, baseline, traza) |
| Estados de ejecución | `backend/agent_runner.py:479` (`row.status = "running"`), `:580` (`{"preparing", "running"}`) | §4.2: `ACTIVE_STATUSES` congelado |
| Modelo de datos | `backend/models.py:207` (`class AgentExecution`), `:211-224` (`ticket_id/agent_type/metadata_json/started_at/completed_at`), `:240` (índice `ix_exec_status_started`), `:260-265` (property `metadata_dict`) | F1/F3 |
| Telemetría de harness | `backend/harness/telemetry.py:28-50` (`RunTelemetry.to_dict` SIN `raw`), `:5` (persist escribe `metadata["harness_telemetry"]`) | Solo LECTURA vía `extract_cost_row`; el 171 NO escribe telemetría |
| Incidencias (Plan 166, IMPLEMENTADO) | `backend/services/incident_store.py:230` (`list_incidents`), `:237` (`find_by_execution(execution_id)`) | F3: la traza enlaza el incidente de la corrida (si existe) |
| Persistencia runtime | `backend/runtime_paths.py:48` (`def data_dir()`; archivo con WIP ajeno hoy → anclar por símbolo) | F2: `data_dir()/telemetry/ops_thresholds.json` |
| Flags patrón triple | `backend/services/harness_flags.py:117` (`_CATEGORY_KEYS`), `:270-271` (tupla `"observabilidad_notif"` que contiene `"STACKY_COST_CENTER_ENABLED"` y `"STACKY_COST_CODEBURN_IMPORT_PATH",  # Plan 142` — ancla de inserción de CATEGORÍA), `:377` (nota "toda flag nueva…"), `:1672-1681` (FlagSpec `STACKY_COST_CENTER_ENABLED`, bloque Plan 142 en `FLAG_REGISTRY` — ancla de inserción; su `group=` REAL es **`"observabilidad"`** en `:1681` — C3: NO `observabilidad_notif`; mismo grupo que unificó el 199 en su C2) | F0 |
| Triage operativo existente (Plan 46, IMPLEMENTADO — prior art de stalls) | `backend/api/diag.py:623` (`/operational-health`, gated `STACKY_OPERATIONAL_HEALTH_ENABLED`), `backend/services/operational_health.py` (`aggregate_operational_health`), `api/diag.py:644` (`zombie_minutes` default = `EXECUTION_TIMEOUT_MINUTES` de `services/ticket_status.py` — fuente ÚNICA del timeout) | C4: R-O4 hereda ese default (§4.2/§4.8); delimitación en "Ortogonal a" |
| Ciclo de evolución (serie RSI 167-170, MERGEADA 2026-07-20) | `backend/services/evolution_cycle.py:57` (`collect_signals()` — ya agrega `executions/costs/incidents/plans` vía `cost_analytics`, cada clave en su propio try/except) | F2b: clave aditiva `signals["ops"]` (C2) |
| Trazabilidad runner-side ya persistida | `backend/agent_runner.py:33` (`_build_trace_metadata`: `prompt_sha/prompt_len/agent_type/agent_name`, fusionado con `setdefault` en metadata; gated `STACKY_EXECUTION_TRACE_ENABLED`, `config.py:1130`) | C9: §4.9 la surfacea read-only (`agent_name`, `prompt_sha`) |
| Meta-tests de flags | `backend/tests/test_harness_flags.py` (set `_CURATED_DEFAULTS_ON`; ubicar por el literal del símbolo), `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`) | F0 |
| Ayuda llana de flags | `backend/services/harness_flags_help.py` (entradas `PlainHelp`; espejo de las del Plan 142/166) | F0 |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh` (`HARNESS_TEST_FILES=(` en `:20`; últimas entradas hoy `:459-462` — la `:462` es WIP local de otra sesión, NO tocarla), `backend/scripts/run_harness_tests.ps1` (`$HarnessTestFiles`, últimas entradas `:412-414`); el meta-test parsea SOLO el `.sh` (`tests/test_harness_ratchet_meta.py:13,21`, verificado por el Plan 117 C4a) — ambos se editan igual | F8 |
| conftest de tests | `backend/tests/conftest.py:11` (`os.environ.setdefault("STACKY_TEST_MODE", "1")`) | Todos los tests: cero egress, cero logs sucios |
| Patrón de test de endpoints | `backend/tests/test_cost_center_api.py:23-37` (fixture module-scope `create_app()` + `test_client`), `:42-80` (helper `_seed_exec` con `Ticket`+`AgentExecution`) | F4: espejo EXACTO |
| Frontend — página de costos (Plan 142) | `frontend/src/pages/CostCenterPage.tsx:1-14` (imports), `:26-37` (`useQuery` on-mount, SIN `refetchInterval`), `:93-98` (`<CostTable …/>` — ancla de inserción de las secciones nuevas), `CostCenterPage.module.css` | F6 |
| Frontend — namespace HTTP | `frontend/src/api/endpoints.ts` (`costFiltersToQuery`; `export const CostCenter = {` hoy `:1464` — el namespace `Ops` nuevo se inserta inmediatamente DESPUÉS de cerrar este objeto) | F5 |
| Frontend — tipos de costos | `frontend/src/lib/costCenterTypes.ts:139` (`CostFiltersParams`) | F5: se IMPORTA; los tipos nuevos van a archivo propio |
| Primitivas UI (Planes 138+162) | `frontend/src/components/ui/index.ts:7-34` (barrel: `Button/IconButton/StatusChip(StatusTone)/Card/SectionHeader/Tabs/Skeleton/Spinner/Field/Input/Select/Textarea/Checkbox`, `firstErrorFieldId`) | F6/F7 |
| Estados universales (Plan 140) | `frontend/src/components/EmptyState.tsx` y `frontend/src/components/LoadErrorState.tsx` (usados por `CostCenterPage.tsx:12-13`; NO están en el barrel) | F6 |
| Formato humano (Plan 161) | `frontend/src/services/format.ts:40-118` (`formatDate/formatTime/formatDateTime/formatDuration/formatCostUsd/formatTokens/formatInt/formatBytes/formatPercent/formatDurationBetween`) — PROHIBIDO `Intl` directo (ratchet 161) | F5/F6/F7 |
| Drawer de detalle de ejecución | `frontend/src/components/ExecutionDetailDrawer.tsx:6` (import `ExecutionInsightBlock`), mount de `<ExecutionInsightBlock` hoy `:108` — anclar SIEMPRE por el nombre del componente | F7: `RunTraceBlock` se monta inmediatamente después del bloque de Insight |
| Toast (Plan 135) | `frontend/src/components/Toast.tsx` (patrón component-local) | F6: feedback del guardado de umbrales |
| venv backend REAL (verificado hoy corriendo `--version`) | `backend/.venv/Scripts/python.exe` → Python 3.13.5, pytest 8.3.3 ✔ (canónico). OJO: hoy TAMBIÉN existe `backend/venv/` (Python 3.11.9, untracked, WIP de sesión paralela) — **NO usarlo, NO borrarlo** | Comandos de test |

**Ortogonal a (NO tocar, NO depender) — estados re-verificados 2026-07-23 (C1):**
- **Plan 158** (fix telemetría claude_code_cli, **IMPLEMENTADO F0-F7 + AUDITADO** — evidencia:
  backfill en `cost_analytics.py:547` y flags Plan 158 en `harness_flags.py:272-273`) —
  **frontera dura intacta**: el 158 arregló la PRODUCCIÓN de telemetría del runner claude;
  el 171 solo la CONSUME vía el extractor canónico. PROHIBIDO acá tocar
  `services/claude_code_cli_runner.py` o el backfill. La degradación **"sin dato"** /
  `cost_kind="unknown"` aplica HOY solo a **corridas históricas pre-158 que el backfill no
  alcanzó** — sigue siendo obligatoria (NUNCA inventar modelo) pero es residual, no el caso
  dominante (§8.3). El Plan 199 (cosecha desde disco) reducirá ese residuo aún más.
- **Plan 199** (cosecha histórica telemetría, CRITICADO v2 SIN implementar): frontera
  espejo declarada en **§8.4** — el 199 NO hace salud/tendencias/baselines/traza ni
  `/ops-*` (su §6); ambos tocan `CostFilters`/`ExecRecord`/`CostCenterPage.tsx` de forma
  aditiva → reglas de merge en §8.4.
- **Plan 117** (insights locales, IMPLEMENTADO): interpretación
  CUALITATIVA por LLM local (TL;DR, triage narrado, digest). El 171 es 100% determinista,
  agregado y sin LLM. Comparten UI vecina en el drawer (F7 se ancla DESPUÉS del bloque 117).
- **Plan 163** (identidad de build + huellas de regresión en LOGS crudos, **IMPLEMENTADO y
  MERGEADO 2026-07-20**): sus "regresiones" son clases de error resueltas reapareciendo en
  texto de logs; las del 171 son MÉTRICAS (tasa de error/latencia/costo) contra ventanas
  baseline. Cero archivos en común.
- **Planes 152/153/154/156/163/164/165** (**IMPLEMENTADOS/MERGEADOS 2026-07-20**):
  ortogonales. Del **156** (latido único, KPI ≤2 req/tick) este plan hereda el
  guardarraíl: **cero polling nuevo** (§3.6).
- **Serie RSI 167-170** (**IMPLEMENTADA y MERGEADA 2026-07-20**): el 171 NO modifica su
  ciclo, prompts ni stores; el ÚNICO toque es la clave aditiva `signals["ops"]` en
  `evolution_cycle.collect_signals()` (F2b), con el mismo patrón try/except que las claves
  existentes — si `ops_telemetry` fallara, el ciclo sigue intacto.
- **Plan 46 — `services/operational_health.py` + `/api/diag/operational-health`** (C4):
  triage read-only por corrida reciente (zombies/costo/needs_review stale) con umbrales
  por query param. NO se modifica ni se llama: el 171 opera sobre AGREGADOS con baseline y
  vive en el Centro de Costos. Único vínculo: el default de `stall_minutes` hereda la
  MISMA fuente única `EXECUTION_TIMEOUT_MINUTES` (§4.2/§4.8) para no contradecir al triage.
- **`services/harness_health.py`** (`compute_health`) y **`services/run_advisor.py`** (recomendador
  de runtime): NO se modifican; el 171 es un módulo nuevo paralelo (delimitación §2).
- **`api/metrics.py:_execution_costs` (:52)**: pipeline LEGACY con gotchas conocidas
  (solo lee `claude_telemetry`; trata `cost_estimated` bool como monto). El Plan 142 §6 ya
  decidió no tocarlo. El 171 TAMPOCO lo toca ni lo usa.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** Stacky ya persiste telemetría por corrida (columnas de
`AgentExecution` para los 3 runtimes + `metadata` con `harness_telemetry`/`claude_telemetry`/
claves del bridge) pero solo la explota para COSTOS (Plan 142) y tasas globales sin tiempo
(`harness-health`). Nadie responde las preguntas operativas que evolucionan la herramienta:
¿qué agente×runtime está degradándose ESTA semana vs su historia?, ¿cuánto tarda
normalmente un `developer` en `codex_cli` (p50/p90) y desde cuándo empeoró?, ¿hay corridas
colgadas ahora?, ¿cuánto quemé hoy contra mi presupuesto?, ¿qué pasó exactamente en la
corrida 4812? Este plan agrega: (a) un **núcleo puro y determinista** (`run_signals.py`)
que proyecta los registros existentes a puntos de salud y computa agregados por
agente×runtime×modelo, percentiles nearest-rank, series diarias, ventanas
actual-vs-baseline y reglas congeladas R-O1..R-O5; (b) **umbrales y presupuesto diario**
con defaults sensatos, editables desde la UI, que solo AVISAN (badge/chips — jamás una
acción automática); (c) **4 endpoints read-only** en el blueprint de métricas existente,
computados on-read (cero daemons, cero cron, cero polling); (d) la sección **"Salud
operativa"** dentro del Centro de Costos existente (misma página, mismos filtros, cero
navegación nueva) y la **traza estructurada** de una corrida en el drawer de detalle ya
existente; y (e) el contrato `evolution_signals()` **cableado de verdad** (F2b) como
clave aditiva `signals["ops"]` de `evolution_cycle.collect_signals()` (serie RSI ya
mergeada), con degradación graciosa.

**KPIs binarios:**

- **KPI-1 — Núcleo determinista verde:** percentiles nearest-rank, agrupación
  agente×runtime×modelo, series diarias con relleno de días vacíos, split de ventanas
  7/28 y reglas R-O1..R-O5 pasan con fixtures sintéticas.
  Comando: `.venv\Scripts\python.exe -m pytest tests/test_run_signals.py -q` → exit 0.
- **KPI-2 — API y umbrales verdes:** con flag OFF los endpoints devuelven
  `{"enabled": false}` 200 (y `/ops/health` SIEMPRE 200); con flag ON y datos sembrados
  devuelven groups/breaches/series correctos; GET/POST de umbrales hace roundtrip y
  rechaza valores inválidos con 400.
  Comando: `.venv\Scripts\python.exe -m pytest tests/test_ops_telemetry_api.py -q` → exit 0.
- **KPI-3 — Traza por corrida verde:** traza completa para una corrida codex con
  telemetría; degradación declarada para claude sin modelo (aparece `"model"` dentro de
  `sin_dato`, NUNCA un valor inventado); `None` para execution_id inexistente.
  Comando: `.venv\Scripts\python.exe -m pytest tests/test_run_trace.py -q` → exit 0.
- **KPI-4 — Cero regresión del Plan 142:** el campo aditivo de F1 no rompe nada.
  Comando: `.venv\Scripts\python.exe -m pytest tests/test_cost_analytics_extract.py tests/test_cost_center_api.py -q` → exit 0.
- **KPI-5 — Frontend tipa y sus helpers puros pasan:** `npx tsc --noEmit` → exit 0 y
  `npx vitest run src/services/__tests__/opsTelemetry.test.ts` → exit 0 (por archivo, G5).
- **KPI-6 — Cero pollers nuevos (contrato con el Plan 156):** el grep congelado de §F8
  sobre los archivos NUEVOS de frontend devuelve 0 hits de `setInterval` y
  `refetchInterval`.
- **KPI-7 — Ratchet:** `grep -c "tests/test_run_signals.py" scripts/run_harness_tests.sh`
  → `1`, e ídem para los otros 3 archivos de test y para el `.ps1`.

**KPIs de impacto (proyectados, verificables por observación):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Percentiles de duración por agente×runtime | inexistentes (ni `harness-health` ni Centro de Costos los tienen) | p50/p90 por celda y por día |
| Detección de regresión operativa (fallo/latencia) | manual, leyendo historial a ojo | determinista, R-O2/R-O3 contra baseline 7d vs 28d, chips en la página |
| Corridas colgadas visibles | solo entrando a cada ejecución | contador + ids en la misma página (R-O4) |
| Presupuesto diario con aviso | inexistente | `daily_budget_usd` opcional (default null = silencioso), solo AVISA (R-O5) |
| Reconstruir qué pasó en una corrida | leer metadata JSON crudo / logs | traza estructurada en el drawer (fases, costo, fuente de telemetría, incidente enlazado, campos sin dato EXPLÍCITOS) |
| Requests periódicas nuevas del frontend | — | **0** (on-mount + refresh manual; sin `refetchInterval`) |
| Filas claude_code_cli sin modelo (residuo histórico pre-158) | invisibles (se pierden en "unknown") | contadas y visibles como "sin dato" (`runs_sin_modelo`) — residuo que el backfill del 158 (implementado) ya redujo y la cosecha del 199 reducirá más |
| Señal operativa en el ciclo de evolución nocturno (RSI) | `collect_signals()` solo ve conteos/costos | `signals["ops"]` con regresiones R-O2/R-O3, breaches y stalls (F2b) |

---

## 2. Por qué ahora / gap que cierra

**Evidencia local (verificada en código):**

1. **La telemetría existe pero solo alimenta costos.** `cost_analytics.load_records`
   (`:167`) ya consolida en UNA query las 3 fuentes por corrida y las clasifica
   (`cost_kind`), pero sus únicos consumidores agregan dólares y tokens
   (`summarize/burn/breakdown`). Duración (`completed_at - started_at`, que el modelo ya
   sabe computar: `models.py:276-278`) no se agrega en NINGÚN lado.
2. **`harness_health.compute_health` es tasas sin tiempo.** `RuntimeStats`
   (`harness_health.py:30-75`) tiene `completed_rate`, `failure_kinds`, costo por ticket —
   pero cero duraciones, cero percentiles, cero series temporales, cero comparación entre
   ventanas, y agrupa por runtime (no por agente×runtime×modelo). Es una foto, no una
   tendencia.
3. **Nada detecta regresiones operativas.** El Plan 163 (implementado) detecta huellas de
   ERRORES RESUELTOS en logs crudos; ningún módulo compara métricas de HOY contra la
   historia del propio sistema. Un agente que pasó de 5% a 40% de error esta semana es
   invisible hasta que el operador lo sufre. (El triage del Plan 46,
   `operational_health.py`, mira corridas individuales recientes — no tendencias ni
   baselines por celda agente×runtime.)
4. **No hay traza por corrida.** El drawer de detalle muestra output/metadata cruda y el
   insight LLM del 117; no existe una vista determinista y estructurada (fases, fuente de
   telemetría, costo clasificado, incidente enlazado vía `find_by_execution`, campos
   ausentes explícitos).
5. **El Centro de Evolución (Plan 167, IMPLEMENTADO) ya recolecta señales pero sin salud
   operativa.** `evolution_cycle.collect_signals()` (`:57`) agrega
   ejecuciones/costos/incidencias/planes — cero percentiles, cero baseline, cero
   regresiones. La señal que este plan produce es exactamente el insumo que a ese ciclo
   le falta, y F2b la agrega como clave aditiva `signals["ops"]` sin tocar el resto del
   ciclo (§8.1).

**El gap real en una frase:** Stacky registra todo y no OBSERVA nada en el tiempo; este
plan convierte los datos ya persistidos en señal operativa determinista, visible donde el
operador ya mira (Centro de Costos + drawer), con avisos HITL y cero trabajo nuevo.

---

## 3. Principios y guardarraíles (NO negociables)

1. **Determinista o no existe.** Cero LLM en este plan (la interpretación cualitativa es
   del 117). Toda regla es una función pura con umbrales explícitos y testeables. Sin
   datos suficientes (mínimos de muestra), la regla NO dispara — un aviso falso es peor
   que ningún aviso.
2. **Human-in-the-loop innegociable.** Umbrales y presupuesto SOLO producen chips/badges
   en la UI cuando el operador abre la página. Ninguna acción automática, ninguna
   notificación push, ningún corte de ejecución, ningún daemon. El sistema AVISA; el
   operador decide.
3. **Cero trabajo extra del operador.** Las 3 flags nuevas son default **ON** (ninguna de
   las 4 excepciones duras aplica: es observabilidad read-only, no bypasea revisión, no
   es destructiva, no depende de prerequisito externo, no reduce seguridad). Los umbrales
   tienen defaults sensatos; editarlos es OPCIONAL y se hace desde la misma página
   (`operator-config-always-via-ui`). El presupuesto diario nace `null` (regla apagada,
   cero ruido).
4. **3 runtimes con paridad declarada campo a campo (§4.1).** La señal BASE (agente,
   runtime, status, started_at, completed_at → duración, tasas, percentiles, series,
   stalls) sale de columnas de `AgentExecution` que los 3 runtimes escriben SIEMPRE →
   paridad total. El enriquecimiento (modelo/tokens/costo) degrada por runtime con
   fallback explícito **"sin dato"** — jamás un valor inventado.
5. **Mono-operador sin auth real:** cero RBAC, cero multiusuario.
6. **No degradar performance (contrato con el Plan 156):** cómputo on-read con queries
   acotadas (`_MAX_ROWS` ya existente); cero daemons, cero cron, cero cache con TTL (no
   hace falta: los endpoints solo se llaman al abrir la página o al click de Refrescar);
   **cero `setInterval`/`refetchInterval`** en el frontend nuevo (KPI-6). Máximo 2
   queries SQL por request de `ops-summary` (la de la ventana visible + la de baseline).
7. **Reusar, no reinventar:** `cost_analytics` para registros y clasificación de costo
   (fuente ÚNICA), `incident_store` para enlaces, `format.ts` para todo formato,
   primitivas 138/162, estados 140, Toast 135, patrón de flags/ratchet/tests de la casa.
   PROHIBIDO: OpenTelemetry/Prometheus/DB nueva/dependencia nueva.
8. **Backward-compatible:** con `STACKY_OPS_TELEMETRY_ENABLED=false`, la app queda
   byte-idéntica en comportamiento visible (las secciones nuevas no se renderizan, los
   endpoints nuevos devuelven `{"enabled": false}`). Contratos del 142 intactos
   (`extract_cost_row`, `summarize`, `burn`, `breakdown`, endpoints `cost-*`: CERO cambios).

### Gotchas del repo que el implementador DEBE respetar (verificadas)

- **G1 — `config` vs `config.config`:** en los módulos de API la instancia de flags es
  `config.config`; `getattr(config, FLAG)` sobre el MÓDULO devuelve siempre el default.
  Espejo EXACTO a usar: `api/metrics.py:565-566` (`_cfg` + `getattr(_cfg, "FLAG", False)`).
- **G2 — Ratchet de tests:** los 4 `test_*.py` nuevos DEBEN agregarse a
  `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh` (ancla `HARNESS_TEST_FILES=(`
  en `:20`) **Y** al array `$HarnessTestFiles` de `backend/scripts/run_harness_tests.ps1`
  (formato con coma final: `  "tests/test_x.py",`). El meta-test parsea el `.sh`
  (`tests/test_harness_ratchet_meta.py:13,21`); el `.ps1` se mantiene por convención.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista en
  `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py`).
- **G4 — `_CURATED_DEFAULTS_ON`:** cada flag **bool** con `default=True` va al set de
  `backend/tests/test_harness_flags.py` (símbolo `_CURATED_DEFAULTS_ON`). Las 3 flags de
  este plan son bool ON → van las 3.
- **G5 — venv y tests por archivo:** backend con `backend\.venv`
  (`.venv\Scripts\python.exe -m pytest tests/<archivo> -q`), NUNCA la suite completa
  (contaminación cross-run conocida). Frontend con `npx vitest run src/<archivo>`, por
  archivo, mismo motivo. NO usar `backend\venv` (py3.11, WIP ajeno de sesión paralela).
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos tienen alcance 0 en
  `uiDebtRatchet`: TODO estilo va a `.module.css`; prohibido `style={{}}`. Para anchos
  dinámicos de barras usar ref imperativo (patrón congelado en §F6), NUNCA `style={{}}`.
- **G7 — `_CATEGORY_KEYS` obligatorio:** toda flag nueva va también al dict
  `_CATEGORY_KEYS` (`services/harness_flags.py:117`; nota normativa `:377`). Ancla de
  inserción: la línea `"STACKY_COST_CODEBURN_IMPORT_PATH",  # Plan 142` (hoy `:271`),
  dentro de la MISMA tupla (la de `"observabilidad_notif"` — ver nota C3 en F0: la
  categoría del ancla y el `group=` del FlagSpec divergen en el sustrato y así se queda).
- **G8 — `requires` profundidad 1:** las 2 aristas apuntan SIEMPRE al flag ROOT
  (`STACKY_OPS_TELEMETRY_ENABLED`), nunca en cadena.
- **G9 — Sin pollers nuevos (Plan 156):** carga on-mount + botón Refrescar + fetch
  on-open del drawer. Prohibido `setInterval`/`refetchInterval` (KPI-6 lo grepa).
- **G10 — `harness_defaults.env` NO se toca a mano:** lo regenera
  `scripts/export_harness_defaults.py` (riel del Plan 133 §3.6).
- **G11 — WIP ajeno / sesiones paralelas:** antes de editar cada archivo caliente
  (`config.py`, `harness_flags.py`, `harness_flags_help.py`, `api/metrics.py`,
  `cost_analytics.py`, `endpoints.ts`, `CostCenterPage.tsx`, `ExecutionDetailDrawer.tsx`,
  scripts de ratchet): `git status -- "<ruta>"`; PROHIBIDO `git stash/reset/checkout`;
  el implementador NO commitea (lo hace el orquestador).
- **G12 — Prosa vs gates propios:** ninguna cadena/comentario del código nuevo debe
  contener los literales `setInterval` ni `refetchInterval` (ni siquiera en comentarios),
  porque el grep de KPI-6 los detectaría (gotcha recurrido 6×: el gate siempre gana).
- **G13 — Números que se muestran:** TODO formato visible pasa por `format.ts`
  (`formatPercent/formatDuration/formatCostUsd/formatInt/formatDateTime`); `Intl` directo
  rompe el ratchet del Plan 161.
- **G14 — DB en tests:** los tests que sembran filas necesitan `db.init_db()` a nivel
  módulo (el `conftest.py` NO inicializa DB — precedente Plan 158 C1 y
  `test_plan117_insights_api.py`). El patrón completo está en el esqueleto de F4.

---

## 4. Contratos congelados (van tal cual al código)

### 4.1 Matriz de paridad por runtime y campo (fuente → fallback)

| Campo | codex_cli | claude_code_cli (residuo histórico pre-158 sin backfill) | claude_code_cli (corridas nuevas/backfilleadas — 158 IMPLEMENTADO, caso dominante HOY) | github_copilot | Fallback congelado |
|---|---|---|---|---|---|
| `agent_type/status/started_at/completed_at` | columnas `AgentExecution` ✔ | ✔ | ✔ | ✔ | siempre presentes (started_at); `completed_at` `null` si no terminó |
| `runtime` | `metadata["runtime"]` ✔ | ✔ | ✔ | ✔ | literal `"desconocido"` |
| `model` | `metadata` / `harness_telemetry` ✔ | ✖ (la clave vieja `claude_code_model` NO es canónica; `extract_cost_row` no la lee — 158 §2.3) | ✔ (`metadata["model"]`) | ✔ (bridge escribe `model`) | literal `"sin dato"` como clave de agrupación; `null` en la traza + entrada en `sin_dato[]` |
| `tokens_in/out` | `harness_telemetry` ✔ | `claude_telemetry.usage` (solo si hubo evento `result`) | ✔ | `tokens_in/tokens_out` ✔ | `null` (NUNCA 0 inventado) |
| costo | `reported`/`estimated` | `reported` si el CLI dio `total_cost_usd`; si no `unknown` (sin modelo no hay estimación — gap del 158) | `estimated`/`reported` | `nominal` (suscripción; NUNCA billable) | `cost_usd=null` + `cost_kind` del extractor; billable = `_billable(cost_kind)` (`cost_analytics.py:213`) |

Regla dura: este plan NO escribe ni corrige NINGUNA de estas fuentes (eso es el 158).
Solo las lee vía `extract_cost_row`/`load_records`.

### 4.2 Constantes del núcleo (`services/run_signals.py`)

```python
TERMINAL_STATUSES = ("completed", "needs_review", "error")   # espejo harness_health.py:26
ACTIVE_STATUSES = ("preparing", "running")                   # espejo agent_runner.py:479,:580
ERROR_STATUS = "error"
SIN_DATO = "sin dato"          # clave de agrupación para model=None
DESCONOCIDO = "desconocido"    # clave de agrupación para runtime/agent_type=None
CURRENT_WINDOW_DAYS = 7
BASELINE_WINDOW_DAYS = 28      # baseline = los 28 días ANTERIORES a la ventana actual

DEFAULT_THRESHOLDS = {
    "schema_version": 1,
    "error_rate_warn": 0.3,        # R-O1
    "error_rate_delta": 0.15,      # R-O2
    "min_runs": 5,                 # mínimo de runs terminales en ventana actual (R-O1/R-O2/R-O3)
    "baseline_min_runs": 10,       # mínimo de runs terminales en baseline (R-O2/R-O3)
    "p90_regression_factor": 1.5,  # R-O3
    "p90_min_seconds": 30.0,       # R-O3: baseline p90 menor a esto = ruido, no dispara
    "stall_minutes": None,         # R-O4 — C4: None = usar EXECUTION_TIMEOUT_MINUTES
                                   # (services/ticket_status.py, fuente ÚNICA del timeout,
                                   # misma que usa /api/diag/operational-health). La
                                   # resolución vive en ops_telemetry.load_thresholds();
                                   # el core puro SIEMPRE recibe el valor efectivo (int).
    "daily_budget_usd": None,      # R-O5: null = regla apagada (default silencioso)
}
```

Helper de tiempo congelado (C8 — py3.13 deprecó `datetime.utcnow()`; el sustrato de
`started_at` es **naive-UTC**, ver `cost_analytics.py:173`):

```python
def _utcnow() -> datetime:
    """Naive-UTC canónico del plan (comparable con started_at de la DB)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

Vive en `run_signals.py` (agregar `timezone` al import de `datetime`); TODO `now` de este
plan (F1/F2/F3) sale de acá — PROHIBIDO `datetime.utcnow()` y PROHIBIDO comparar
datetimes aware contra `started_at` naive.

### 4.3 `RunPoint` (proyección pura de un `ExecRecord`)

```python
@dataclass
class RunPoint:
    execution_id: int
    agent_type: str          # ex.agent_type or DESCONOCIDO
    runtime: str             # row.runtime or DESCONOCIDO
    model: str | None        # row.model (None si no hay — NUNCA inventar)
    status: str              # ex.status or ""
    started_at: datetime
    duration_seconds: float | None   # SOLO si status=="completed" y completed_at presente; si no None
    billable_usd: float      # row.cost_usd si _billable(row.cost_kind) y cost_usd is not None; si no 0.0
    has_model: bool          # row.model is not None
```

Decisión congelada: los percentiles de duración se computan SOLO sobre corridas
`status=="completed"` con `duration_seconds` disponible (los errores suelen fallar
rápido y falsearían la latencia "sana" hacia abajo).

### 4.4 Percentil nearest-rank (fórmula congelada)

`percentile_nearest_rank(values, q)`: si `values` vacío → `None`; si no:
ordenar ascendente, `rank = ceil(q * n)`, `idx = max(0, rank - 1)`, devolver
`round(values_ordenados[idx], 3)`.
Ejemplos normativos (van como tests): `[5,1,3,2,4]` con `q=0.5` → `3`; con `q=0.9` → `5`;
`[]` → `None`; `[7.0]` con cualquier `q` → `7.0`.

### 4.5 Shape de `GET /api/metrics/ops-summary` (flag ON)

```json
{
  "enabled": true,
  "generated_at": "<iso utc>",
  "window_days": 30,
  "totals": {
    "runs": 0, "terminal": 0, "completed": 0, "needs_review": 0, "error": 0, "running": 0,
    "error_rate": null, "p50_seconds": null, "p90_seconds": null,
    "billable_usd": 0.0, "runs_sin_modelo": 0
  },
  "groups": [
    {"agent_type": "developer", "runtime": "codex_cli", "runs": 0, "terminal": 0,
     "completed": 0, "error": 0, "error_rate": null,
     "p50_seconds": null, "p90_seconds": null, "billable_usd": 0.0,
     "models": {"claude-sonnet-5": 3, "sin dato": 1}}
  ],
  "baseline": {"enabled": true, "current_days": 7, "baseline_days": 28, "regressions": []},
  "breaches": [],
  "stalls": {"count": 0, "execution_ids": []},
  "thresholds": { }
}
```

Reglas: `error_rate = round(error / terminal, 4)` o `null` si `terminal == 0`;
`groups` ordenado por `runs` DESC y desempate por (`agent_type`, `runtime`) ASC;
`running` cuenta status en `ACTIVE_STATUSES`; `runs_sin_modelo` cuenta puntos con
`has_model == False`; `stalls.execution_ids` como máximo 20 ids (los más viejos primero);
`thresholds` es el dict efectivo (§4.2 + overrides). Con
`STACKY_OPS_BASELINE_ENABLED=false`: `"baseline": {"enabled": false, "current_days": 7,
"baseline_days": 28, "regressions": []}` y `breaches` EXCLUYE R-O2/R-O3 (las demás reglas
siguen).

### 4.6 Reglas deterministas (tabla congelada; `rule_id` literal)

Cada breach tiene el shape:

```json
{"rule_id": "R-O1", "severity": "warn", "agent_type": "developer", "runtime": "codex_cli",
 "message": "<literal con placeholders resueltos>", "observed": 0.4, "reference": null, "threshold": 0.3}
```

| rule_id | severity | ámbito | condición (sobre umbrales `t`) | message literal (placeholders `{}` resueltos con `format.ts`-equivalentes backend: números crudos, la UI formatea) |
|---|---|---|---|---|
| `R-O1` | `warn` | por (agent_type, runtime), ventana visible | `terminal >= t.min_runs` y `error_rate >= t.error_rate_warn` | `"Tasa de error alta: {error}/{terminal} corridas en la ventana"` |
| `R-O2` | `critical` | por (agent_type, runtime), ventanas 7/28 | `cur.terminal >= t.min_runs` y `base.terminal >= t.baseline_min_runs` y `cur.error_rate - base.error_rate >= t.error_rate_delta` | `"Regresión de tasa de error vs baseline: {cur_rate} ahora vs {base_rate} histórico"` (`observed=cur_rate`, `reference=base_rate`, `threshold=t.error_rate_delta`) |
| `R-O3` | `warn` | por (agent_type, runtime), ventanas 7/28 | ambas ventanas con `>= t.min_runs`/`t.baseline_min_runs` corridas completed con duración, `base.p90 >= t.p90_min_seconds` y `cur.p90 >= t.p90_regression_factor * base.p90` | `"Regresión de latencia: p90 {cur_p90}s ahora vs {base_p90}s histórico"` |
| `R-O4` | `warn` | global (agrega ids) | existe al menos 1 punto con `status in ACTIVE_STATUSES` y `(now - started_at) > t.stall_minutes` minutos | `"{n} corrida(s) activas hace más de {stall_minutes} minutos"` (`agent_type=null`, `runtime=null`, `observed=n`, `threshold=t.stall_minutes`) |
| `R-O5` | `warn` | global | `t.daily_budget_usd is not None` y `billable de HOY (UTC, started_at >= hoy 00:00) >= t.daily_budget_usd` | `"Presupuesto diario alcanzado: {hoy_usd} USD de {budget} USD"` |

R-O2/R-O3 usan ventanas FIJAS: actual = últimos `CURRENT_WINDOW_DAYS` días desde `now`;
baseline = los `BASELINE_WINDOW_DAYS` días inmediatamente anteriores. Independientes del
filtro `days` de la página (decisión: el baseline es una propiedad del sistema, no de la
vista). Cada regla emite a lo sumo UN breach por ámbito por request. Orden del array
`breaches`: `critical` primero, después `warn`; dentro de cada severidad por `rule_id` ASC.

### 4.7 Shape de `GET /api/metrics/ops-trends` (flag ON)

```json
{"enabled": true, "days": 30,
 "series": [{"date": "2026-07-18", "runs": 0, "errors": 0, "billable_usd": 0.0, "p50_seconds": null}]}
```

Bucket por fecha UTC de `started_at` (`YYYY-MM-DD`). La serie SIEMPRE trae exactamente
`days` entradas consecutivas terminando en HOY (días sin corridas van con ceros y
`p50_seconds: null`) — eje continuo determinista, orden ascendente por fecha.

### 4.8 Umbrales: persistencia y endpoint

Archivo: `data_dir()/telemetry/ops_thresholds.json` (crear directorio con
`mkdir(parents=True, exist_ok=True)`; lectura tolerante: ausente/corrupto → `{}`;
escritura bajo `_THRESHOLDS_LOCK = threading.Lock()`; `data_dir()` se llama EN CADA
operación — los tests lo monkeypatchean).

Efectivo = `DEFAULT_THRESHOLDS` con overrides superficiales del archivo (claves
desconocidas del archivo se IGNORAN al leer) **+ resolución final en
`load_thresholds()`**: si el efectivo trae `stall_minutes is None`, se reemplaza por
`EXECUTION_TIMEOUT_MINUTES` (import local `from services.ticket_status import
EXECUTION_TIMEOUT_MINUTES` en `ops_telemetry.py` — capa I/O, NO en `run_signals.py` que
sigue puro). El dict que viaja al core y al payload `thresholds` de §4.5 lleva SIEMPRE el
int resuelto.

- `GET /api/metrics/ops-thresholds` → 200 `{"enabled": true, "thresholds": {…efectivo…}}`
  (flag OFF → `{"enabled": false}`, 200).
- `POST /api/metrics/ops-thresholds` body JSON parcial (solo claves a cambiar) → valida y
  persiste SOLO claves conocidas; 200 `{"ok": true, "thresholds": {…efectivo nuevo…}}`.
  Validación congelada (400 `{"ok": false, "error": "invalid_thresholds:<clave>"}` en el
  PRIMER fallo): `error_rate_warn`/`error_rate_delta` float en `[0,1]`;
  `min_runs`/`baseline_min_runs` int `>= 1`; `stall_minutes` `null` (= volver al default
  del sistema `EXECUTION_TIMEOUT_MINUTES` — C4) o int `>= 1`; `p90_regression_factor`
  float `>= 1.0`; `p90_min_seconds` float `>= 0`; `daily_budget_usd` `null` o float `> 0`;
  `schema_version` NO editable (ignorar si viene); clave desconocida en el body → 400.

### 4.9 Shape de `GET /api/metrics/run-trace/<int:execution_id>` (flag ON)

```json
{"enabled": true, "trace": {
  "execution_id": 4812, "agent_type": "developer", "status": "completed",
  "runtime": "codex_cli", "model": null,
  "ticket": {"ticket_id": 7, "ado_id": 991234, "title": "…"},
  "phases": [{"name": "started", "ts": "<iso>"}, {"name": "completed", "ts": "<iso>"}],
  "duration_seconds": 123.4,
  "cost": {"cost_usd": 0.18, "cost_kind": "estimated", "tokens_in": 1000, "tokens_out": 500,
           "cache_read_tokens": null, "cache_savings_usd": null},
  "telemetry_source": "harness_telemetry",
  "session_id": null, "num_turns": null,
  "agent_name": null, "prompt_sha": null,
  "stalled": false,
  "incident": null,
  "sin_dato": ["model", "session_id", "num_turns"]
}}
```

Reglas: `phases` incluye `started` siempre (de `started_at`) y `completed` SOLO si
`completed_at` no es null (el `name` es literal `"completed"` sea cual sea el status
final; el status va aparte); `telemetry_source` determinista:
`"harness_telemetry"` si `metadata["harness_telemetry"]` es dict no vacío, si no
`"claude_telemetry"` si ese dict existe no vacío, si no `"bridge_metadata"` si existe
`metadata["tokens_in"]` o `metadata["tokens_out"]` o `metadata["model"]`, si no
`"ninguna"`; `session_id`/`num_turns` de `metadata` top-level o del dict de telemetría
detectado (primer no-null); `agent_name`/`prompt_sha` (C9 [ADICIÓN ARQUITECTO]) =
`metadata.get("agent_name")` / `metadata.get("prompt_sha")` — los runners YA los
persisten cuando `STACKY_EXECUTION_TRACE_ENABLED` está ON (`agent_runner.py:33`
`_build_trace_metadata`); si ausentes → `null` y NO entran en `sin_dato` (el orden de
chequeo de `sin_dato` queda congelado como está); PROHIBIDO exponer `prompt_text`
(privacidad — solo el SHA); `stalled` = `status in ACTIVE_STATUSES` y edad >
`stall_minutes` efectivo; `incident` = `{"id","title","status"}` del dict de
`incident_store.find_by_execution(execution_id)` o `null` (envuelto en try/except: un
store roto NUNCA rompe la traza); `sin_dato` lista (orden fijo de chequeo:
`model, tokens, cost, session_id, num_turns`) con los campos que quedaron null.
Execution inexistente → 404 `{"ok": false, "error": "execution_not_found"}`.
Flag `STACKY_OPS_TRACE_ENABLED` OFF → `{"enabled": false}`, 200.

### 4.10 Contrato hacia la serie RSI (MERGEADA — consumida de verdad en F2b, §8.1): `evolution_signals()`

```json
{"schema_version": 1, "generated_at": "<iso utc>", "window_days": 7,
 "groups": [ …mismas celdas que §4.5 groups, ventana 7d… ],
 "regressions": [ …breaches R-O2/R-O3… ],
 "breaches": [ …todos los breaches… ],
 "stalls": {"count": 0, "execution_ids": []}}
```

---

## 5. Fases

Orden por dependencia: **F0 → F1 → F2 → F2b → F3 → F4 → F5 → F6 → F7 → F8** (F2b se
valida junto con F4, que aporta el arnés de tests de integración).

> **Comandos de test:** backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`
> con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (equivalente Git Bash:
> `cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`).
> Verificado hoy: ese intérprete es Python 3.13.5 con pytest 8.3.3. Frontend desde
> `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con `npx vitest run src/<archivo>`
> y `npx tsc --noEmit`. SIEMPRE por archivo (G5).

---

### F0 — Flags del arnés (patrón triple)

**Objetivo (1 frase):** declarar las 3 flags del plan con el patrón triple para que todas
las fases queden protegidas y configurables desde la UI del Arnés.
**Valor:** kill-switch por UI de todo el feature, sin `.env` manual.

**Archivos a editar (5):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py`
3. `Stacky Agents/backend/services/harness_flags_help.py`
4. `Stacky Agents/backend/tests/test_harness_flags.py` (set `_CURATED_DEFAULTS_ON`)
5. `Stacky Agents/backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`)

**Flags (nombres EXACTOS):**

| Flag | type | Default | `requires=` | Excepción dura |
|---|---|---|---|---|
| `STACKY_OPS_TELEMETRY_ENABLED` | bool | **ON** | (ninguno — master) | ninguna (observabilidad read-only) |
| `STACKY_OPS_BASELINE_ENABLED` | bool | **ON** | `STACKY_OPS_TELEMETRY_ENABLED` | ninguna |
| `STACKY_OPS_TRACE_ENABLED` | bool | **ON** | `STACKY_OPS_TELEMETRY_ENABLED` | ninguna |

**`config.py`** — insertar inmediatamente DESPUÉS del bloque del Plan 142 (ubicar por
grep el literal `STACKY_COST_CODEBURN_IMPORT` y bajar hasta el fin de ese bloque; si el
Plan 158 ya se implementó y su bloque quedó ahí, insertar después del bloque 158 —
ambos son aditivos):

```python
    # ── Plan 171 — Telemetría operativa (salud/tendencias/baselines/traza) ──
    # Observabilidad read-only computada on-read. Default ON: no agrega daemons,
    # ni polling, ni escrituras (salvo el JSON de umbrales editado por el operador).
    STACKY_OPS_TELEMETRY_ENABLED: bool = os.getenv(
        "STACKY_OPS_TELEMETRY_ENABLED", "true"
    ).strip().lower() == "true"
    # Comparación ventana actual (7d) vs baseline (28d previos): reglas R-O2/R-O3.
    STACKY_OPS_BASELINE_ENABLED: bool = os.getenv(
        "STACKY_OPS_BASELINE_ENABLED", "true"
    ).strip().lower() == "true"
    # Traza estructurada por corrida en el drawer de detalle.
    STACKY_OPS_TRACE_ENABLED: bool = os.getenv(
        "STACKY_OPS_TRACE_ENABLED", "true"
    ).strip().lower() == "true"
```

**`harness_flags.py` — 2 toques:**
(a) `_CATEGORY_KEYS` (G7): ubicar la línea `"STACKY_COST_CODEBURN_IMPORT_PATH",  # Plan 142`
(hoy `:271`) y agregar inmediatamente después, dentro de la MISMA tupla:

```python
        "STACKY_OPS_TELEMETRY_ENABLED",   # Plan 171 — telemetría operativa (salud/tendencias)
        "STACKY_OPS_BASELINE_ENABLED",    # Plan 171 — baselines y regresiones deterministas
        "STACKY_OPS_TRACE_ENABLED",       # Plan 171 — traza estructurada por corrida
```

(b) `FLAG_REGISTRY`: insertar 3 `FlagSpec` inmediatamente DESPUÉS del último `FlagSpec`
del bloque `# ── Plan 142 — Centro de Costos + Codeburn` (ubicar por
`key="STACKY_COST_CODEBURN_IMPORT_PATH"`). Usar EXACTAMENTE el mismo literal `group=` que
tiene el `FlagSpec` de `STACKY_COST_CENTER_ENABLED` (leerlo del archivo; **C3: verificado
2026-07-23 = `"observabilidad"`**, `harness_flags.py:1681` — el v1 decía
`observabilidad_notif` y era FALSO; el 199 §F7 unificó al mismo grupo). OJO (divergencia
PREEXISTENTE del sustrato, NO corregirla acá): la CATEGORÍA de `_CATEGORY_KEYS` donde se
insertan las keys (paso a) es la tupla de `"observabilidad_notif"` (la del ancla), aunque
el `group=` del FlagSpec sea `"observabilidad"` — así está hoy el propio
`STACKY_COST_CENTER_ENABLED` y los meta-tests lo aceptan:

```python
    # ── Plan 171 — Telemetría operativa ─────────────────────────────────────────
    FlagSpec(
        key="STACKY_OPS_TELEMETRY_ENABLED",
        type="bool", default=True,
        label="Telemetría operativa",
        description="Salud y tendencias por agente/runtime/modelo dentro del Centro de Costos: tasas de fallo, percentiles de duración, series diarias y avisos por umbral. Solo lectura, calculado al abrir la página. (Distinta de 'Telemetría en vivo' STACKY_LIVE_TELEMETRY_ENABLED, que emite eventos durante la corrida.)",
        group="observabilidad",
    ),
    FlagSpec(
        key="STACKY_OPS_BASELINE_ENABLED",
        type="bool", default=True,
        label="Regresiones vs baseline",
        description="Compara la última semana contra las 4 semanas previas por agente y runtime, y avisa (solo avisa) si la tasa de error o la latencia p90 empeoraron más allá del umbral.",
        group="observabilidad", requires="STACKY_OPS_TELEMETRY_ENABLED",
    ),
    FlagSpec(
        key="STACKY_OPS_TRACE_ENABLED",
        type="bool", default=True,
        label="Traza por corrida",
        description="Vista estructurada de una ejecución en su panel de detalle: fases, duración, costo clasificado, fuente de telemetría, incidente enlazado y campos sin dato explícitos. (Distinta de 'Traza de ejecución' STACKY_EXECUTION_TRACE_ENABLED, que es la CAPTURA runner-side de prompt_sha/agent_name; esta flag solo LEE.)",
        group="observabilidad", requires="STACKY_OPS_TELEMETRY_ENABLED",
    ),
```

**`harness_flags_help.py`:** agregar 3 entradas `PlainHelp` (espejo del formato de las
entradas del Plan 142; ubicar por el texto de ayuda de `STACKY_COST_CENTER_ENABLED`), en
lenguaje llano: qué es, efecto de ON, efecto de OFF, un ejemplo cada una.

**Meta-tests:** agregar las 3 keys al set `_CURATED_DEFAULTS_ON` (G4) y las 2 aristas a
`_REQUIRES_MAP_FROZEN` (G3):

```python
    "STACKY_OPS_BASELINE_ENABLED": "STACKY_OPS_TELEMETRY_ENABLED",
    "STACKY_OPS_TRACE_ENABLED": "STACKY_OPS_TELEMETRY_ENABLED",
```

**Tests PRIMERO (TDD):** crear `Stacky Agents/backend/tests/test_ops_telemetry_flags.py`
con estos 7 casos (nombres EXACTOS):
1. `test_master_flag_en_registry` — existe FlagSpec `STACKY_OPS_TELEMETRY_ENABLED`, `type=="bool"`, `default is True`, sin `requires`.
2. `test_baseline_flag_requires_master` — spec BASELINE: `requires=="STACKY_OPS_TELEMETRY_ENABLED"`, `default is True`.
3. `test_trace_flag_requires_master` — ídem TRACE.
4. `test_las_3_estan_categorizadas` — las 3 keys aparecen en algún valor de `_CATEGORY_KEYS` (importar de `services.harness_flags`).
5. `test_config_defaults_on` — con env limpio (`monkeypatch.delenv` de las 3, `raising=False`) recargar `config` (patrón `importlib.reload`) y verificar las 3 en `True`.
6. `test_aristas_requires_congeladas` — las 2 aristas están en `_REQUIRES_MAP_FROZEN` de `tests.test_harness_flags_requires` apuntando al ROOT.
7. `test_help_presente` — el dict de `harness_flags_help` contiene las 3 keys.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_ops_telemetry_flags.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO:** los 3 archivos verdes (fotografiar ANTES fallos preexistentes de
los meta-tests si los hubiera; el criterio es "sin regresión vs. la foto").
**Impacto por runtime:** N/A (declaración). **Trabajo del operador:** ninguno.

---

### F1 — Núcleo puro `services/run_signals.py` + campo aditivo `ExecRecord.completed_at`

**Objetivo (1 frase):** computar TODA la señal (proyección, agregados, percentiles,
series, ventanas, reglas) como funciones puras sin Flask ni DB, alimentadas por los
`ExecRecord` que `cost_analytics` ya produce.
**Valor:** el corazón del plan 100% testeable con listas sintéticas.

**Archivo a EDITAR:** `Stacky Agents/backend/services/cost_analytics.py` — 2 toques
mínimos y aditivos (precedente EXACTO: el campo `raw_metadata` se agregó igual,
`cost_analytics.py:147-150`):
1. En el dataclass `ExecRecord` (ubicar por `class ExecRecord`), agregar al FINAL:
   ```python
       # Plan 171 (aditivo, default None = 100% retrocompatible): fin de la corrida,
       # para duraciones/percentiles en services/run_signals.py.
       completed_at: datetime | None = None
   ```
2. En `load_records` (ubicar el constructor `out.append(ExecRecord(`), agregar el kwarg
   `completed_at=ex.completed_at,` en la MISMA llamada (después de `started_at=ex.started_at`).

**Archivo a CREAR:** `Stacky Agents/backend/services/run_signals.py` — módulo PURO
(imports permitidos: `from __future__ import annotations`, `math`, `dataclasses`,
`datetime`; PROHIBIDO importar `db`, `models`, `flask`, `config`). Contiene las
constantes de §4.2, el dataclass de §4.3 y estas funciones (firmas EXACTAS):

```python
def from_exec_record(r) -> RunPoint
    # r es cost_analytics.ExecRecord (duck-typing; no se importa el tipo).
    # duration_seconds SOLO si r.status == "completed" y r.completed_at y r.started_at.
    # billable_usd usa la MISMA regla que _billable: r.row.cost_kind in ("reported","estimated").
def percentile_nearest_rank(values: list[float], q: float) -> float | None   # §4.4
def summarize_groups(points: list[RunPoint]) -> dict
    # Devuelve {"totals": {...}, "groups": [...]} EXACTO §4.5 (sin baseline/breaches).
def daily_series(points: list[RunPoint], days: int, now: datetime) -> list[dict]   # §4.7
def split_windows(points: list[RunPoint], now: datetime) -> tuple[list[RunPoint], list[RunPoint]]
    # current = started_at > now-7d; baseline = now-35d < started_at <= now-7d.
def detect_regressions(current: list[RunPoint], baseline: list[RunPoint], thresholds: dict) -> list[dict]
    # R-O2 y R-O3 de §4.6, por celda (agent_type, runtime).
def evaluate_thresholds(points: list[RunPoint], thresholds: dict, now: datetime) -> tuple[list[dict], dict]
    # (breaches R-O1 + R-O4 + R-O5, stalls_dict §4.5). R-O5 usa started_at >= hoy 00:00 UTC.
def merge_thresholds(overrides: dict | None) -> dict
    # DEFAULT_THRESHOLDS copiado + overrides superficiales SOLO de claves conocidas.
def sort_breaches(breaches: list[dict]) -> list[dict]
    # critical primero, luego warn; dentro de cada severidad por rule_id ASC (§4.6).
```

**Tests PRIMERO (TDD):** crear `Stacky Agents/backend/tests/test_run_signals.py`.
Helper local `_p(**kw)` que construye `RunPoint` con defaults razonables. 14 casos
(nombres EXACTOS):
1. `test_percentile_ejemplos_normativos` — los 4 ejemplos de §4.4.
2. `test_from_exec_record_completed_con_duracion` — record sintético (objeto `types.SimpleNamespace` con `.row` = `CostRow` real) status completed → duration correcta y billable según cost_kind.
3. `test_from_exec_record_error_sin_duracion` — status "error" con completed_at → `duration_seconds is None`.
4. `test_from_exec_record_model_none_es_sin_dato_en_grupos` — punto con model None → en `summarize_groups` la celda tiene `models == {"sin dato": 1}` y `totals["runs_sin_modelo"] == 1`.
5. `test_summarize_groups_totales_y_orden` — 3 celdas con runs distintos → orden por runs DESC y desempate alfabético; `error_rate` redondeado a 4.
6. `test_summarize_groups_vacio` — `[]` → totals en cero/null exactos de §4.5.
7. `test_daily_series_rellena_dias_vacios` — days=3 con 1 corrida ayer → 3 entradas consecutivas, ceros hoy y anteayer, `p50_seconds` null en días sin completed.
8. `test_split_windows_bordes` — puntos a 6d, 8d y 40d → current={6d}, baseline={8d}, el de 40d fuera.
9. `test_r_o1_dispara_y_respeta_min_runs` — 4/5 errores con min_runs=5 dispara; con 4 runs totales NO.
10. `test_r_o2_regresion_error_rate` — baseline 1/20, current 4/6 → breach `critical` con observed/reference correctos; con baseline de 5 runs (< baseline_min_runs) NO dispara.
11. `test_r_o3_regresion_latencia` — baseline p90 40s, current p90 90s → dispara; con baseline p90 10s (< p90_min_seconds) NO.
12. `test_r_o4_stalls` — 2 puntos running hace 90 min con stall_minutes=60 → breach observed=2 y `stalls == {"count": 2, "execution_ids": [id_viejo, id_nuevo]}`.
13. `test_r_o5_presupuesto_null_no_dispara_y_seteado_si` — default null nunca; con budget 1.0 y 1.5 billable hoy → dispara.
14. `test_merge_y_sort` — `merge_thresholds({"stall_minutes": 30, "desconocida": 1})` → 30 aplicado y clave desconocida ignorada; `sort_breaches` ordena critical>warn y por rule_id.

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_run_signals.py tests/test_cost_analytics_extract.py -q
```
**Criterio BINARIO:** ambos verdes (el segundo prueba que el campo aditivo no rompió el
Plan 142 — KPI-4 parcial).
**Flag:** ninguna (módulo puro sin efectos). **Impacto por runtime:** paridad total por
construcción (§4.1: la señal base son columnas que los 3 escriben; model degrada a
"sin dato"). **Trabajo del operador:** ninguno.

---

### F2 — Orquestación fina `services/ops_telemetry.py` (umbrales + payloads + contrato RSI)

**Objetivo (1 frase):** una capa delgada que carga registros vía `cost_analytics`,
persiste/lee umbrales en `data_dir()/telemetry/` y compone los payloads de §4.5/§4.7/§4.10.
**Valor:** separa I/O de lógica; los endpoints de F4 quedan de 10 líneas.

**Archivo a CREAR:** `Stacky Agents/backend/services/ops_telemetry.py`. Símbolos EXACTOS:

```python
import dataclasses, json, threading
from datetime import datetime
import runtime_paths                       # data_dir() EN CADA llamada (testabilidad)
from services import cost_analytics as ca
from services import run_signals as rs

_THRESHOLDS_LOCK = threading.Lock()
_THRESHOLDS_FILENAME = "ops_thresholds.json"

def telemetry_root() -> Path               # runtime_paths.data_dir() / "telemetry"
def load_thresholds() -> dict
    # merge_thresholds(overrides tolerantes del JSON) + resolución C4: si el efectivo
    # trae stall_minutes None -> from services.ticket_status import EXECUTION_TIMEOUT_MINUTES
    # (import LOCAL dentro de la función) y stall_minutes = EXECUTION_TIMEOUT_MINUTES.
    # Devuelve SIEMPRE stall_minutes int.
def save_thresholds(patch: dict) -> dict
    # Valida §4.8 (ValueError(f"invalid_thresholds:{clave}") en el primer fallo, claves
    # desconocidas incluidas), aplica sobre el efectivo actual, escribe el JSON bajo el
    # lock (mkdir parents=True exist_ok=True) y devuelve el efectivo nuevo.
def ops_summary(filters: "ca.CostFilters", *, baseline_enabled: bool) -> dict
    # 1) records = ca.load_records(filters); points = [rs.from_exec_record(r) ...]
    # 2) body = rs.summarize_groups(points); th = load_thresholds(); now = rs._utcnow()  # C8
    # 3) breaches, stalls = rs.evaluate_thresholds(points, th, now)
    # 4) baseline: si baseline_enabled: base_f = dataclasses.replace(filters,
    #        days=rs.CURRENT_WINDOW_DAYS + rs.BASELINE_WINDOW_DAYS, date_from=None, date_to=None)
    #    base_records = ca.load_records(base_f); cur, base = rs.split_windows(points_de_base_records, now)
    #    regressions = rs.detect_regressions(cur, base, th); breaches += regressions
    #    si no: regressions = []
    # 5) arma y devuelve el shape EXACTO §4.5 (breaches = rs.sort_breaches(breaches)).
def ops_trends(filters: "ca.CostFilters") -> dict          # shape §4.7
def evolution_signals() -> dict
    # Contrato §4.10: carga UNA vez con CostFilters(days=35), split_windows, summarize
    # de la ventana de 7d, detect_regressions, evaluate_thresholds sobre la ventana 7d.
```

**Tests PRIMERO (TDD):** los de persistencia/validación van en
`tests/test_ops_telemetry_api.py` (F4) para no duplicar seeding; en ESTA fase se
implementa el módulo y se valida su parte pura con un caso agregado a
`tests/test_run_signals.py`:
15. `test_ops_thresholds_roundtrip_con_tmp_path` — `monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)`; `load_thresholds()` == defaults **salvo `stall_minutes`, que llega resuelto**: `load_thresholds()["stall_minutes"] == EXECUTION_TIMEOUT_MINUTES` (importarlo de `services.ticket_status` en el test — C4) y NUNCA `None`; `save_thresholds({"stall_minutes": 30})` persiste y `load_thresholds()["stall_minutes"] == 30`; `save_thresholds({"stall_minutes": None})` vuelve al default del sistema; `save_thresholds({"error_rate_warn": 2})` lanza `ValueError` que empieza con `"invalid_thresholds:error_rate_warn"`; archivo corrupto (escribir `"{{{"`) → `load_thresholds()` devuelve defaults (con `stall_minutes` resuelto).

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_run_signals.py -q
```
**Criterio BINARIO:** verde, incluyendo el caso 15.
**Flag:** el gating vive en F4 (este módulo no lee flags — recibe `baseline_enabled` como
parámetro). **Impacto por runtime:** heredado de F1. **Trabajo del operador:** ninguno.

---

### F2b — [ADICIÓN ARQUITECTO — C2] `signals["ops"]` en el ciclo de evolución (RSI mergeada)

**Objetivo (1 frase):** que el ciclo nocturno de auto-mejora VEA la señal operativa —
regresiones, breaches y stalls — sin tocar nada más del ciclo.
**Valor:** el contrato §4.10 deja de ser una función sin consumidor: el Centro de
Evolución analiza salud real, no solo conteos y costos.

**Archivo a EDITAR:** `Stacky Agents/backend/services/evolution_cycle.py` — en
`collect_signals()` (`:57`), agregar inmediatamente ANTES del `return signals` final
(anclar por el literal `return signals`), con el MISMO patrón try/except de las claves
existentes (`executions/costs/incidents/plans` — cada una aislada):

```python
    # Plan 171 — señal operativa (salud/regresiones/stalls). Aislada: si falla,
    # el ciclo sigue con el resto de las señales.
    try:
        import config as _cfg_mod
        if getattr(_cfg_mod.config, "STACKY_OPS_TELEMETRY_ENABLED", False):
            from services import ops_telemetry
            signals["ops"] = ops_telemetry.evolution_signals()
    except Exception as exc:  # noqa: BLE001 — espejo de las claves vecinas
        signals["ops"] = {"error": str(exc)}
```

(G1 aplica: la instancia es `config.config`; con la flag OFF la clave `"ops"` NO se
agrega — el shape previo de `collect_signals()` queda byte-idéntico, cero regresión de la
serie RSI.)

**Tests (TDD — van en `tests/test_ops_telemetry_api.py`, F4, casos 10 y 11):**
10. `test_evolution_collect_signals_incluye_ops` — con flag ON (fixture) y datos
    sembrados, `from services.evolution_cycle import collect_signals`;
    `s = collect_signals()` → `"ops" in s` y `s["ops"]["schema_version"] == 1` y
    `"regressions" in s["ops"]`.
11. `test_evolution_collect_signals_flag_off_sin_ops` — monkeypatch
    `config.config.STACKY_OPS_TELEMETRY_ENABLED = False` (G1) → `"ops" not in
    collect_signals()`.

**Comando:** el de F4. **Criterio BINARIO:** casos 10-11 verdes y (regresión RSI) los
tests existentes del ciclo de evolución que nombre el ratchet siguen verdes por archivo.
**Flag:** `STACKY_OPS_TELEMETRY_ENABLED` (gate en call-site, patrón 199 F1).
**Impacto por runtime:** N/A (agregado). **Trabajo del operador:** ninguno (el ciclo RSI
ya tiene su propio HITL — este plan solo le suma datos de LECTURA; ninguna acción nueva).

---

### F3 — Traza por corrida `services/run_trace.py`

**Objetivo (1 frase):** `build_run_trace(execution_id)` arma el dict determinista de §4.9
desde la fila + metadata + extractor de costos + incidente enlazado.
**Valor:** reconstruir una corrida deja de ser leer JSON crudo.

**Archivo a CREAR:** `Stacky Agents/backend/services/run_trace.py`:

```python
def build_run_trace(execution_id: int) -> dict | None:
    # 1) with session_scope() as session: ex = session.get(AgentExecution, execution_id)
    #    -> None si no existe. tk = session.get(Ticket, ex.ticket_id) (puede ser None).
    #    LEER TODO lo necesario DENTRO del scope (md, campos, ticket) — precedente C7
    #    de cost_analytics.load_records.
    # 2) row = extract_cost_row(md); source = _telemetry_source(md) (§4.9).
    # 3) th = ops_telemetry.load_thresholds() para stall_minutes.
    # 4) incident: try: services.incident_store.find_by_execution(execution_id)
    #    except Exception: None. Si dict -> {"id","title","status"} con .get().
    # 5) devuelve el shape EXACTO §4.9 (sin la clave "enabled": eso lo agrega la API).

def _telemetry_source(md: dict) -> str      # §4.9, testeable directa
```

**Tests PRIMERO (TDD):** crear `Stacky Agents/backend/tests/test_run_trace.py` (patrón
de seeding de `test_cost_center_api.py:42-80`, con `db.init_db()` a nivel módulo — G14 —
y rango propio `_NEXT_ADO_ID = 171500`). 6 casos:
1. `test_trace_codex_completo` — seed codex con `harness_telemetry` (costo estimado) → `telemetry_source=="harness_telemetry"`, `duration_seconds==5.0`, `cost.cost_kind=="estimated"`, `phases` con started y completed.
2. `test_trace_claude_sin_modelo_declara_sin_dato` — seed `runtime="claude_code_cli"` con `claude_telemetry.usage` y SIN `model` → `model is None`, `"model" in trace["sin_dato"]`, `cost.cost_kind=="unknown"` (degradación 158 declarada, NUNCA inventada).
3. `test_trace_copilot_nominal` — seed `github_copilot` con `model`+`tokens_in/out` → `telemetry_source=="bridge_metadata"`, `cost.cost_kind=="nominal"`.
4. `test_trace_running_stalled` — seed status "running", `started_at` hace 2 h, sin completed_at → `stalled is True`, `phases` SOLO started, `duration_seconds is None`.
5. `test_trace_inexistente_none` — `build_run_trace(999999) is None`.
6. `test_trace_incidente_enlazado` — `monkeypatch.setattr` de `services.incident_store.find_by_execution` a lambda que devuelve `{"id": "inc-1", "title": "t", "status": "abierta", "otra": 1}` → `trace["incident"] == {"id": "inc-1", "title": "t", "status": "abierta"}`; y con lambda que lanza → `incident is None` sin excepción.

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_run_trace.py -q
```
**Criterio BINARIO:** verde.
**Flag:** gating en F4. **Impacto por runtime:** los 3 cubiertos por tests 1-3 con
degradación explícita. **Trabajo del operador:** ninguno.

---

### F4 — API: 5 rutas nuevas en `api/metrics.py`

**Objetivo (1 frase):** exponer summary/trends/thresholds/trace en el blueprint de
métricas existente, espejando los patrones del Plan 142 (mismo archivo).
**Valor:** superficie HTTP completa sin blueprint nuevo ni registro nuevo.

**Archivo a EDITAR:** `Stacky Agents/backend/api/metrics.py` — insertar al FINAL del
archivo (después de la última ruta `cost-*`; ubicar por `@bp.get("/cost-reconciliation-audit")`
y bajar hasta el final de esa función):

```python
# ── Plan 171 — Telemetría operativa (read-only, on-read; espejo patrones Plan 142) ──

def _ops_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_OPS_TELEMETRY_ENABLED", False))


@bp.get("/ops/health")
def ops_health():
    """SIEMPRE 200 (patrón /cost-center/health, metrics.py: la UI decide con esto)."""
    return jsonify({"ok": True, "flag_enabled": _ops_enabled()})


@bp.get("/ops-summary")
def ops_summary_route():
    if not _ops_enabled():
        return jsonify({"enabled": False}), 200
    f, err = _filters_or_error(request.args)
    if err:
        return err
    from services import ops_telemetry as ot
    baseline_on = bool(getattr(_cfg, "STACKY_OPS_BASELINE_ENABLED", False))
    return jsonify(ot.ops_summary(f, baseline_enabled=baseline_on))


@bp.get("/ops-trends")
def ops_trends_route():
    if not _ops_enabled():
        return jsonify({"enabled": False}), 200
    f, err = _filters_or_error(request.args)
    if err:
        return err
    from services import ops_telemetry as ot
    return jsonify(ot.ops_trends(f))


@bp.get("/ops-thresholds")
def ops_thresholds_get():
    if not _ops_enabled():
        return jsonify({"enabled": False}), 200
    from services import ops_telemetry as ot
    return jsonify({"enabled": True, "thresholds": ot.load_thresholds()})


@bp.post("/ops-thresholds")
def ops_thresholds_post():
    if not _ops_enabled():
        return jsonify({"enabled": False}), 200
    from services import ops_telemetry as ot
    body = request.get_json(silent=True) or {}
    try:
        effective = ot.save_thresholds(body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "thresholds": effective})


@bp.get("/run-trace/<int:execution_id>")
def run_trace_route(execution_id: int):
    if not _ops_enabled() or not bool(getattr(_cfg, "STACKY_OPS_TRACE_ENABLED", False)):
        return jsonify({"enabled": False}), 200
    from services import run_trace as rt
    trace = rt.build_run_trace(execution_id)
    if trace is None:
        return jsonify({"ok": False, "error": "execution_not_found"}), 404
    return jsonify({"enabled": True, "trace": trace})
```

(Los imports `jsonify/request` y el `_cfg` ya existen en el archivo — verificado
`metrics.py:21,:565-566`. NO agregar imports duplicados.)

**Tests PRIMERO (TDD):** crear `Stacky Agents/backend/tests/test_ops_telemetry_api.py`.
Esqueleto de cabecera OBLIGATORIO (G14; espejo `test_cost_center_api.py:7-37` + Plan 158 C1):

```python
from __future__ import annotations
import json, os, sys
from datetime import datetime, timedelta
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import db  # noqa: E402
db.init_db()


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_OPS_TELEMETRY_ENABLED"] = "true"
    os.environ["STACKY_OPS_BASELINE_ENABLED"] = "true"
    os.environ["STACKY_OPS_TRACE_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c
```

Más un fixture `autouse` de función que monkeypatchea `runtime_paths.data_dir` a un
`tmp_path` (umbrales aislados por test) y el helper `_seed_exec` copiado del patrón
`test_cost_center_api.py:42-80` con `_NEXT_ADO_ID = 171000`. 11 casos (1-9 acá; 10-11
especificados en F2b):
1. `test_ops_health_siempre_200` — GET `/api/metrics/ops/health` → 200 con `ok` y `flag_enabled` booleanos.
2. `test_summary_off_devuelve_enabled_false` — monkeypatch `config.config.STACKY_OPS_TELEMETRY_ENABLED = False` (G1: sobre la INSTANCIA) → `{"enabled": False}` 200; ídem `/ops-trends`, `/ops-thresholds`, `/run-trace/1`.
3. `test_summary_on_agrupa_por_agente_runtime` — seed 3 codex developer (1 error) + 1 copilot qa → groups correctos, `totals["error"] == 1`.
4. `test_summary_cuenta_runs_sin_modelo` — seed claude_code_cli SIN `model` en md → `totals["runs_sin_modelo"] >= 1` y celda con `models` conteniendo `"sin dato"`.
5. `test_summary_baseline_off_por_flag` — monkeypatch instancia `STACKY_OPS_BASELINE_ENABLED = False` → `baseline["enabled"] is False` y `regressions == []`.
6. `test_trends_serie_continua` — GET `/ops-trends?days=5` → exactamente 5 fechas consecutivas ascendentes terminando hoy (UTC).
7. `test_thresholds_roundtrip_y_400` — GET defaults → POST `{"stall_minutes": 30}` 200 → GET refleja 30 → POST `{"stall_minutes": 0}` → 400 con error `invalid_thresholds:stall_minutes` → POST `{"clave_falsa": 1}` → 400.
8. `test_run_trace_ok_y_404` — seed una corrida → GET `/run-trace/<id>` 200 con `trace.execution_id` correcto; GET `/run-trace/999999` → 404 `execution_not_found`.
9. `test_summary_fecha_malformada_400` — GET `/ops-summary?from=chau` → 400 `invalid_date` (reuso de `_filters_or_error` verificado).

**Comando:**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_ops_telemetry_api.py -q
```
**Criterio BINARIO:** verde; y KPI-4 re-verificado
(`.venv/Scripts/python.exe -m pytest tests/test_cost_center_api.py -q` → exit 0).
**Flags:** las 3 de F0 (default ON). **Impacto por runtime:** casos 3-4 cubren codex,
copilot y la degradación claude. **Trabajo del operador:** ninguno.

---

### F5 — Frontend: tipos + namespace `Ops` + helpers puros con vitest

**Objetivo (1 frase):** plomería tipada del frontend y helpers puros testeables (mapeo
severidad→tono, filas de traza, normalización de barras) SIN tocar componentes todavía.
**Valor:** F6/F7 quedan como render puro; la lógica ya está verde.

**Archivos a CREAR (3):**

1. `Stacky Agents/frontend/src/lib/opsTelemetryTypes.ts` — interfaces espejo de
   §4.5/§4.6/§4.7/§4.8/§4.9 (nombres EXACTOS): `OpsTotals`, `OpsGroup`, `OpsBreach`
   (`rule_id: string; severity: "warn" | "critical"; agent_type: string | null;
   runtime: string | null; message: string; observed: number; reference: number | null;
   threshold: number`), `OpsBaseline`, `OpsStalls`, `OpsThresholds`,
   `OpsSummaryResponse` (`enabled: boolean` + resto opcional), `OpsTrendPoint`,
   `OpsTrendsResponse`, `OpsThresholdsResponse`, `RunTraceResponse`, `RunTrace`.
2. `Stacky Agents/frontend/src/services/opsTelemetry.ts` — funciones PURAS (sin fetch,
   sin React):
   ```ts
   import type { StatusTone } from "../components/ui";
   export function severityTone(sev: "warn" | "critical"): StatusTone   // "critical"->"danger", "warn"->"warning" (si StatusTone no tiene esos literales, usar los 2 tonos más cercanos del union REAL leído de StatusChip.tsx y dejar comentario con la correspondencia)
   export function breachLabel(b: OpsBreach): string                    // `${b.rule_id} · ${scope} · ${b.message}` con scope = `${agent_type}/${runtime}` o "global"
   export function barPercents(values: number[]): number[]              // cada valor * 100 / max (max<=0 -> todos 0), redondeado a entero
   export function traceRows(t: RunTrace): { label: string; value: string }[]
       // filas deterministas en este orden: Estado, Runtime, Modelo (o "sin dato"),
       // Duración (formatDuration(duration_seconds*1000) o "—"), Costo
       // (formatCostUsd + ` (${cost_kind})` o "—"), Tokens (formatTokens in/out o "—"),
       // Fuente de telemetría, Sesión (o "—"), Turnos (formatInt o "—"),
       // Incidente (id — title o "—"). USA format.ts (G13), nunca Intl.
   ```
3. `Stacky Agents/frontend/src/services/__tests__/opsTelemetry.test.ts` — vitest, 6 casos:
   `severityTone` (2), `breachLabel` global y por celda, `barPercents` (incluye max 0 y
   lista vacía), `traceRows` con traza completa y con traza degradada (model null →
   "sin dato"; duración null → "—").

**Archivo a EDITAR:** `Stacky Agents/frontend/src/api/endpoints.ts` — insertar
inmediatamente DESPUÉS del cierre del objeto `export const CostCenter = { … };`
(ubicar por el literal `export const CostCenter = {`, hoy `:1417`):

```ts
// Plan 171 — Telemetría operativa (reusa costFiltersToQuery del Plan 142).
export const Ops = {
  health: () => api.get<{ ok: boolean; flag_enabled: boolean }>("/api/metrics/ops/health"),
  summary: (params?: CostFiltersParams) => {
    const qs = costFiltersToQuery(params).toString();
    return api.get<OpsSummaryResponse>(`/api/metrics/ops-summary${qs ? `?${qs}` : ""}`);
  },
  trends: (params?: CostFiltersParams) => {
    const qs = costFiltersToQuery(params).toString();
    return api.get<OpsTrendsResponse>(`/api/metrics/ops-trends${qs ? `?${qs}` : ""}`);
  },
  thresholds: () => api.get<OpsThresholdsResponse>("/api/metrics/ops-thresholds"),
  saveThresholds: (body: Partial<OpsThresholds>) =>
    api.post<{ ok: boolean; thresholds: OpsThresholds }>("/api/metrics/ops-thresholds", body),
  runTrace: (executionId: number) =>
    api.get<RunTraceResponse>(`/api/metrics/run-trace/${executionId}`),
};
```

(con el import de tipos correspondiente junto a los imports de `costCenterTypes`).

**Comandos:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/services/__tests__/opsTelemetry.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** ambos exit 0.
**Flag:** N/A (plomería). **Impacto por runtime:** N/A (frontend). **Trabajo del operador:** ninguno.

---

### F6 — Sección "Salud operativa" dentro del Centro de Costos

**Objetivo (1 frase):** renderizar salud, avisos, tendencias y umbrales en la página que
el operador YA usa, reutilizando sus filtros, sin tab nueva y sin polling.
**Valor:** la señal aparece donde ya se mira; cero navegación nueva.

**Archivos a CREAR (4):**
1. `Stacky Agents/frontend/src/components/costcenter/OpsHealthSection.tsx` (+ su
   `OpsHealthSection.module.css`) — props `{ data: OpsSummaryResponse | null; isLoading: boolean;
   error: unknown; onRetry: () => void }`. Render: `SectionHeader` título literal
   "Salud operativa"; si `isLoading` → `Skeleton`; si `error` → `LoadErrorState`
   (`what="la salud operativa"`); si `data.enabled === false` → `null` (sección
   invisible, cero ruido); si no: (a) fila de chips de breaches (`StatusChip` con
   `severityTone`, texto `breachLabel`; si no hay breaches un único chip tono neutro
   con texto literal "Sin avisos"); (b) tabla con columnas literales
   `Agente · Runtime · Corridas · Errores · % error · p50 · p90 · Costo · Modelos`
   (formatos: `formatPercent(error_rate*100, 1)` o "—"; `formatDuration(p*1000)` o "—";
   `formatCostUsd`; `models` como `clave ×n` separados por coma — "sin dato" se muestra
   tal cual); (c) línea de stalls SOLO si `stalls.count > 0`: literal
   `"{count} corrida(s) posiblemente colgadas: #{ids}"`.
2. `Stacky Agents/frontend/src/components/costcenter/OpsTrendsSection.tsx` (+ module.css)
   — props `{ data: OpsTrendsResponse | null; isLoading: boolean; error: unknown;
   onRetry: () => void }`. `SectionHeader` "Tendencia diaria (corridas y errores)".
   Barras verticales por día: contenedor flex; cada día un track con DOS fills (runs y
   errors) cuya altura se setea con **ref imperativo** (G6, patrón congelado):
   ```tsx
   <div
     className={styles.barFill}
     ref={(el) => { if (el) el.style.height = `${pct}%`; }}
   />
   ```
   con `pct` de `barPercents(series.map(s => s.runs))` (y errors análogo). Tooltip
   nativo `title` por día: `date · runs · errors · formatCostUsd(billable_usd)`.
3. `Stacky Agents/frontend/src/components/costcenter/OpsThresholdsForm.tsx` (+ module.css)
   — props `{ initial: OpsThresholds; onSaved: (t: OpsThresholds) => void }`. Form con
   primitivas del barrel (`Field`+`Input`, `Button`): SOLO 3 campos editables en UI —
   `error_rate_warn` (label "Umbral de tasa de error (0-1)"), `stall_minutes`
   (label "Minutos para considerar colgada"), `daily_budget_usd`
   (label "Presupuesto diario USD (vacío = sin aviso)"). Validación inline (patrón 162):
   fuera de rango → error en el `Field` y foco con `firstErrorFieldId`. Submit →
   `Ops.saveThresholds` → Toast éxito literal "Umbrales guardados" / Toast error con el
   `error` del backend. Sin auto-guardado (HITL explícito).
**Archivo a EDITAR:** `Stacky Agents/frontend/src/pages/CostCenterPage.tsx`:
- agregar 2 queries espejo de las existentes (`:26-37`), SIN `refetchInterval` (G9/G12):
  `opsQ` con `queryKey: ["ops", "summary", filters]` y `queryFn: () => Ops.summary(filters)`;
  `trendsQ` con `queryKey: ["ops", "trends", filters]` y `queryFn: () => Ops.trends(filters)`.
- renderizar al FINAL del `<div className={styles.page}>`, inmediatamente DESPUÉS del
  bloque `<CostTable …/>` (ancla `:93-98`):
  ```tsx
  <OpsHealthSection data={opsQ.data ?? null} isLoading={opsQ.isLoading} error={opsQ.error} onRetry={() => opsQ.refetch()} />
  <OpsTrendsSection data={trendsQ.data ?? null} isLoading={trendsQ.isLoading} error={trendsQ.error} onRetry={() => trendsQ.refetch()} />
  {opsQ.data?.enabled && opsQ.data.thresholds ? (
    <OpsThresholdsForm initial={opsQ.data.thresholds} onSaved={() => opsQ.refetch()} />
  ) : null}
  ```
- los filtros existentes (`CostFiltersBar`) aplican SIN cambios: `days/runtime/agent_type/project`
  viajan igual que en `CostCenter.summary` (mismo `costFiltersToQuery`).

**Tests:** los helpers puros ya están verdes (F5). Gate de esta fase (gap RTL/jsdom
conocido y aceptado en el repo):
```bash
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
más el grep de KPI-6 (ver F8) y smoke visual manual del operador (documentado en §11,
NO bloqueante para el implementador).
**Criterio BINARIO:** `tsc` exit 0 y grep KPI-6 con 0 hits.
**Flag:** `STACKY_OPS_TELEMETRY_ENABLED` (OFF → `{"enabled": false}` → las secciones
renderizan `null`; la página queda EXACTAMENTE como hoy).
**Impacto por runtime:** N/A (render). **Trabajo del operador:** ninguno (umbrales
opcionales con defaults).

---

### F7 — Traza en el drawer de detalle de ejecución

**Objetivo (1 frase):** montar `RunTraceBlock` en `ExecutionDetailDrawer` para ver la
traza estructurada de la corrida abierta, con fetch on-open (jamás periódico).
**Valor:** diagnóstico por corrida en 1 click donde ya está el detalle.

**Archivo a CREAR:** `Stacky Agents/frontend/src/components/RunTraceBlock.tsx`
(+ `RunTraceBlock.module.css`): props `{ executionId: number }`. `useQuery` con
`queryKey: ["run-trace", executionId]`, `queryFn: () => Ops.runTrace(executionId)`
(sin `refetchInterval` — G9/G12). Render: `isLoading` → `Skeleton`; error o
`data.enabled === false` → `null` (silencioso); si hay `data.trace`: `SectionHeader`
"Traza de la corrida" + lista definición desde `traceRows(trace)` + fila de fases
(`phases` como `name → formatDateTime(ts)`) + si `trace.sin_dato.length > 0` una línea
atenuada literal: `"Sin dato en esta corrida: {lista}. Las corridas claude_code_cli
históricas previas al Plan 158 pueden no registrar modelo si el backfill no las
alcanzó."` + si `trace.stalled`
un `StatusChip` tono warning con texto "Posiblemente colgada".

**Archivo a EDITAR:** `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx`:
import `RunTraceBlock` junto al import de `ExecutionInsightBlock` (`:6`), y montarlo
inmediatamente DESPUÉS del cierre del elemento `<ExecutionInsightBlock …/>` (`:95`,
anclar por el nombre del componente):

```tsx
<RunTraceBlock executionId={executionId} />
```

**Test/criterio BINARIO:**
```bash
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
exit 0; los helpers de render (`traceRows`) ya están cubiertos por vitest en F5.
**Flag:** `STACKY_OPS_TRACE_ENABLED` (OFF → el endpoint devuelve `{"enabled": false}` y
el bloque renderiza `null`; 1 request on-open aceptada — es acción explícita del
operador, no polling).
**Impacto por runtime:** la traza degrada por runtime según §4.1/§4.9 (tests F3).
**Trabajo del operador:** ninguno.

---

### F8 — Cierre: ratchet, KPI-6 y verificación final

**Objetivo (1 frase):** registrar los 4 tests nuevos en ambos scripts del ratchet,
verificar el gate anti-polling y correr la batería final.

**Archivos a EDITAR (2):**
1. `Stacky Agents/backend/scripts/run_harness_tests.sh` — dentro de
   `HARNESS_TEST_FILES=(` (ancla `:20`), agregar al FINAL de la lista actual (después de
   la última entrada existente al momento de editar — G11: NO tocar entradas ajenas):
   ```
     tests/test_ops_telemetry_flags.py
     tests/test_run_signals.py
     tests/test_run_trace.py
     tests/test_ops_telemetry_api.py
   ```
2. `Stacky Agents/backend/scripts/run_harness_tests.ps1` — en `$HarnessTestFiles`,
   mismas 4 entradas con el formato del array (comillas y coma final):
   ```
     "tests/test_ops_telemetry_flags.py",
     "tests/test_run_signals.py",
     "tests/test_run_trace.py",
     "tests/test_ops_telemetry_api.py",
   ```

**Gate KPI-6 (comando congelado, Git Bash desde `Stacky Agents/frontend`):**
```bash
grep -rn -e setInterval -e refetchInterval \
  src/lib/opsTelemetryTypes.ts src/services/opsTelemetry.ts \
  src/components/costcenter/OpsHealthSection.tsx src/components/costcenter/OpsTrendsSection.tsx \
  src/components/costcenter/OpsThresholdsForm.tsx src/components/RunTraceBlock.tsx ; test $? -eq 1
```
(exit 0 del compuesto = 0 hits = verde).

**Verificación final (batería completa, por archivo):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_ops_telemetry_flags.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_run_signals.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_run_trace.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_ops_telemetry_api.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_cost_analytics_extract.py tests/test_cost_center_api.py -q
cd "Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_harness_ratchet_meta.py -q
cd "Stacky Agents/frontend" && npx vitest run src/services/__tests__/opsTelemetry.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** todos exit 0 (para los meta-tests del arnés: sin regresión vs. la
foto previa — el drift ajeno preexistente del ratchet NO es de este plan).
Actualizar el encabezado de ESTE doc a IMPLEMENTADO al cerrar (riel
`feedback_actualizar-estado-plan-en-doc`).
**Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación (codificada en el plan) |
|---|---|---|
| R1 | Falsos avisos con pocas muestras (agente nuevo, semana corta) | mínimos de muestra congelados (`min_runs`/`baseline_min_runs`) — la regla NO dispara sin datos; percentiles `null` en vez de 0 |
| R2 | Doble carga SQL en `ops-summary` (ventana visible + baseline) percibida lenta | ambas queries acotadas por `_MAX_ROWS` e índices existentes (`ix_exec_status_started`); solo corren on-open/refresh; si el operador nota lentitud, apagar `STACKY_OPS_BASELINE_ENABLED` la elimina |
| R3 | Campo aditivo en `ExecRecord` rompe consumidores del 142 | default `None` (mismo patrón que `raw_metadata`); KPI-4 corre la suite del 142 en F1 y F4 |
| R4 | Sesiones paralelas editando los mismos archivos calientes | G11: `git status` por archivo antes de editar, anclas por contenido, cero stash/reset |
| R5 | Filas claude sin modelo distorsionan la lectura de costos | NUNCA se inventa: bucket "sin dato" + `runs_sin_modelo` visible + nota literal en la traza que cita al Plan 158 |
| R6 | El grep de KPI-6 matchea prosa propia | G12: prohibidos esos literales también en comentarios de los archivos nuevos |
| R7 | Umbrales corruptos a mano en disco | lectura tolerante → defaults; POST valida todo; `schema_version` no editable |
| R8 | Drift del ratchet por planes ajenos (meta-test rojo preexistente) | criterio binario "sin regresión vs. foto previa" (precedente Plan 146/154) |
| R9 | `stalls` no ve zombies más viejos que la ventana de filtro | limitación aceptada y documentada: R-O4 opera sobre la ventana visible (default 30d cubre cualquier stall real; un zombie de >30d ya es visible en el historial) |
| R10 | Colisión de merge con el 199 (mismos archivos aditivos: `CostCenterPage.tsx`, `endpoints.ts`, `CostFilters`/`ExecRecord`) | reglas de merge deterministas congeladas en §8.4 (espejo de la nota §10 del 199); ambos planes son append-only sobre atributos distintos |
| R11 | La clave `signals["ops"]` (F2b) rompe o enlentece el ciclo RSI | try/except aislado idéntico al de las claves vecinas + gate por flag en call-site; flag OFF = shape previo byte-idéntico; cómputo acotado por `_MAX_ROWS` (misma query que la página) |

## 7. Fuera de scope (explícito)

- Corregir la PRODUCCIÓN de telemetría de `claude_code_cli` o backfills (**Plan 158**).
- Interpretación LLM de corridas, TL;DR, triage narrado (**Plan 117**, implementado).
- Huellas de regresión en logs crudos e identidad de build (**Plan 163**).
- Notificaciones push/campana (**Plan 152**), polling/latido (**Plan 156**), deep-links
  nuevos (**Plan 165**): cero interacción.
- Tocar `harness_health.compute_health`, `run_advisor`, `_execution_costs` legacy, o
  CUALQUIER contrato del Plan 142 (`extract_cost_row`/`summarize`/`burn`/`breakdown`/
  endpoints `cost-*`).
- Daemons, cron, schedulers, caches con TTL, WebSockets, OpenTelemetry/Prometheus/DB
  nueva, export a archivos, acciones automáticas ante breaches (prohibido por §3.2).
- Tab de navegación nueva (la señal vive en la página de costos y el drawer existentes).

## 8. Contratos congelados hacia otros planes (implementados acá, consumidos allá)

### 8.1 → Serie RSI 167-170 (IMPLEMENTADA y MERGEADA 2026-07-20) — cableado en F2b

`services/ops_telemetry.py::evolution_signals()` (§4.10) queda implementado, testeado
(casos 10-11 de F2b) y CONSUMIDO: F2b agrega la clave aditiva `signals["ops"]` en
`evolution_cycle.collect_signals()` (`:57`) con try/except aislado y gate por flag en el
call-site. **Degradación:** flag OFF → la clave no existe y el shape previo del ciclo
queda byte-idéntico; excepción en `ops_telemetry` → `{"error": ...}` como las claves
vecinas, el ciclo nunca se cae por este plan.

### 8.2 → Plan 152 (centro de notificaciones, IMPLEMENTADO)

Los `breaches` de §4.6 son el shape natural para una futura entrada de notificación.
Este plan NO integra nada con el 152; si el 152 quisiera consumirlos, llama
`ops_summary` on-demand. Cero acoplamiento.

### 8.3 ← Plan 158 (fix telemetría claude_code_cli, IMPLEMENTADO + AUDITADO)

Contrato de convivencia: este plan lee SOLO por `extract_cost_row`. Con el 158 ya
implementado, las corridas claude nuevas (y las backfilleadas) traen `model` → el bucket
"sin dato" y `runs_sin_modelo` cubren solo el residuo histórico que el backfill no
alcanzó. Verificación cruzada declarativa: `runs_sin_modelo` debe ser ~0 en ejecuciones
nuevas; si NO lo es, eso señala una regresión del 158 (valor extra de esta métrica).

### 8.4 ↔ Plan 199 (cosecha histórica telemetría, CRITICADO v2 sin implementar) — frontera espejo (C5)

El 199 declaró su lado (su §6/§9-10): NO hace salud/tendencias/baselines/umbrales/traza
ni `/ops-*`. Espejo del 171: NO cosecha disco, NO agrega filtros multi-runtime/modelo ni
gráficos de costos (serie apilada/heatmap/distribución — esos son del 199). Reglas de
merge deterministas (ambos son aditivos, cualquiera puede aterrizar primero):
- **`ExecRecord`/`CostFilters`:** cada plan agrega SUS campos AL FINAL del dataclass al
  momento de editar (171: `completed_at`; 199: `runtimes/models/min_cost/max_cost`). El
  segundo en llegar rebasea los suyos al final — nunca reordenar los del otro.
- **`CostCenterPage.tsx`:** el orden congelado de secciones tras `<CostTable/>` es:
  secciones del 171 (`OpsHealthSection`, `OpsTrendsSection`, `OpsThresholdsForm`) y
  DESPUÉS las del 199 (gráficos + cosecha). Si el 199 aterrizó primero, insertar las del
  171 ENTRE `<CostTable/>` y las del 199.
- **`endpoints.ts`:** namespaces separados (`Ops` del 171, `TelemetryHarvest` del 199),
  ambos insertados después de `CostCenter` — el orden relativo entre ellos es indistinto.
- **Flags:** grupos coherentes (`group="observabilidad"` en ambos, C3/199-C2); keys
  disjuntas.
- **Sin dato claude:** la cosecha del 199 puede rellenar telemetría histórica → tras
  implementarla, `runs_sin_modelo` baja SOLO (mismo extractor); cero cambios acá.

## 9. Glosario (para un modelo menor)

- **runtime:** motor que ejecuta al agente: `codex_cli`, `claude_code_cli` o
  `github_copilot`. Vive en `metadata["runtime"]` de cada `AgentExecution`.
- **agent_type:** rol del agente (p. ej. `developer`, `qa`), columna de `AgentExecution`.
- **`harness_telemetry` / `claude_telemetry` / claves bridge:** las 3 formas en que la
  telemetría llega a `metadata_dict`; `extract_cost_row` las reconcilia (canónica >
  legacy > top-level).
- **cost_kind:** clasificación del costo por corrida: `reported` (el CLI lo dijo),
  `estimated` (calculado por pricing), `nominal` (suscripción plana, NO facturable),
  `unknown` (sin datos). "Billable" = reported+estimated.
- **terminal:** status final: `completed`, `needs_review`, `error`. Activo:
  `preparing`, `running`.
- **stall:** corrida activa hace más de `stall_minutes` (posiblemente colgada). Solo se
  AVISA.
- **baseline:** las 4 semanas anteriores a la última semana; sirve de referencia para
  detectar regresión de tasa de error o latencia.
- **nearest-rank:** método de percentil sin interpolación (§4.4): determinista y simple.
- **breach:** un aviso emitido por una regla R-O*; NUNCA una acción.
- **HITL (human-in-the-loop):** el sistema informa, el operador decide. Riel innegociable.
- **patrón triple de flags:** `config.py` + `_CATEGORY_KEYS` + `FlagSpec`, con meta-tests
  que fuerzan curaduría y aristas.
- **ratchet de tests:** todo test backend nuevo se registra en `HARNESS_TEST_FILES`
  (`.sh` y `.ps1`) o un meta-test rompe.
- **data_dir():** raíz de datos runtime (`runtime_paths.py:48`); en tests se
  monkeypatchea a `tmp_path`.

## 10. Orden de implementación

1. F0 — flags patrón triple + meta-tests (`test_ops_telemetry_flags.py` primero, rojo → verde).
2. F1 — `test_run_signals.py` (rojo) → campo aditivo `ExecRecord.completed_at` → `run_signals.py` (verde) → regresión 142.
3. F2 — caso 15 de umbrales (rojo) → `ops_telemetry.py` (verde).
4. F2b — casos 10-11 de `test_ops_telemetry_api.py` (rojos) → `signals["ops"]` en
   `evolution_cycle.collect_signals()` (verdes junto con F4).
5. F3 — `test_run_trace.py` (rojo) → `run_trace.py` (verde).
6. F4 — `test_ops_telemetry_api.py` (rojo) → rutas en `api/metrics.py` (verde) → regresión 142.
7. F5 — `opsTelemetry.test.ts` (rojo) → tipos + helpers + namespace `Ops` (verde) → `tsc`.
8. F6 — secciones en Centro de Costos → `tsc` + grep KPI-6.
9. F7 — `RunTraceBlock` en el drawer → `tsc`.
10. F8 — ratchet (.sh + .ps1) + batería final completa + actualizar estado del doc.

## 11. Definición de Hecho (DoD)

- [ ] KPI-1..KPI-7 en verde con los comandos EXACTOS de §1/§F8 (sin regresión vs. foto
      previa en meta-tests con drift ajeno preexistente).
- [ ] Las 3 flags visibles y toggleables en el panel del Arnés (registry dinámico), las
      3 en `_CURATED_DEFAULTS_ON`, las 2 aristas en `_REQUIRES_MAP_FROZEN`.
- [ ] Con `STACKY_OPS_TELEMETRY_ENABLED=false`: endpoints nuevos → `{"enabled": false}`
      200, `ops/health` → 200, página y drawer idénticos a hoy.
- [ ] Cero cambios en: `claude_code_cli_runner.py`, `codex_cli_runner.py`,
      `harness_health.py`, `run_advisor.py`, `operational_health.py`, contratos del 142,
      `_execution_costs`. (Excepción declarada y acotada: las líneas aditivas de F2b en
      `evolution_cycle.collect_signals()` — try/except aislado, flag-gated.)
- [ ] `signals["ops"]` presente en `collect_signals()` con flag ON y AUSENTE con flag OFF
      (casos 10-11 de F2b verdes); tests previos del ciclo RSI sin regresión.
- [ ] Los 3 FlagSpec con `group="observabilidad"` (C3 — espejo de
      `STACKY_COST_CENTER_ENABLED:1681`), y `stall_minutes` efectivo derivado de
      `EXECUTION_TIMEOUT_MINUTES` cuando no hay override (C4).
- [ ] Cero `setInterval`/`refetchInterval`/daemons/cron nuevos (KPI-6 + revisión de diff).
- [ ] `harness_defaults.env` NO editado a mano (G10).
- [ ] Smoke visual manual del operador (NO bloqueante, post-implementación): abrir
      Centro de Costos → ver "Salud operativa" y "Tendencia diaria"; abrir el detalle de
      una ejecución → ver "Traza de la corrida"; guardar un umbral → Toast.
- [ ] Estado de este doc actualizado (CRITICADO v2 → IMPLEMENTADO) con nota honesta de
      cualquier desvío.
