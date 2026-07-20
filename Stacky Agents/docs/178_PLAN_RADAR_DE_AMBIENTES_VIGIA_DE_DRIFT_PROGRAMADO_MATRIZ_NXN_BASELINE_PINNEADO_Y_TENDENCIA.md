# Plan 178 — Radar de ambientes: vigía de drift programado, matriz N×N, baseline pinneado y tendencia

**Estado:** CRITICADO (v2, 2026-07-18, juez `criticar-y-mejorar-plan`). La v1 (PROPUESTO 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`) fue **RECHAZADA** por dos bloqueantes (C1 cosecha no idempotente de runs fallidos, C2 baseline auto-destruido por la retención de snapshots del motor); esta v2 los corrige in place y queda lista para `implementar-plan-stacky`.
**Serie:** Comparador de BD — capa 4 ("del comparador bajo demanda al radar continuo de ambientes"). Capa 1 = planes 122-126 (motor, IMPLEMENTADA). Capa 2 = plan 157 (entrada/config, CRITICADO v2, sin implementar). Capa 3 = plan 176 (triage/gates/cierre, PROPUESTO v1, sin implementar).

## Versión: v1 -> v2 (2026-07-18, criticar-y-mejorar-plan)

**CHANGELOG v1 -> v2:**
- **C1 (BLOQUEANTE, resuelto):** `_harvest_watch` re-cosechaba el MISMO run en `error`/stale en CADA tick de 60 s (incrementando `consecutive_errors` ~60 veces/hora y emitiendo `watch_error` duplicados hasta inundar el cap de 200 eventos en ~3,3 h), porque solo `last_done_run_id` marcaba cosecha y los runs fallidos nunca lo actualizan. Fix: campo nuevo `last_harvested_run_id` en Watch v1 (§4.1) — la cosecha es idempotente por run (done, error o stale marcan harvested exactamente una vez). KPI-4 reformulado para exigirlo; tests de idempotencia nuevos en F2.
- **C2 (BLOQUEANTE, resuelto) [ADICIÓN ARQUITECTO]:** el motor poda snapshots con `_MAX_SNAPSHOTS_PER_ALIAS = 20` (`services/dbcompare_snapshot.py:31`, `prune_snapshots` invocado por `take_snapshot` en `:226`). Un vigía con interval=60 min genera ~24 snapshots/día por alias ⇒ el snapshot pinneado como baseline era borrado en **menos de 1 día** de vigía activo y F4 degeneraba a no-op silencioso. Fix: **baseline autocontenido** — `pin_baseline` copia el Snapshot v1 completo a `baselines/<alias>.snapshot.json`; toda resolución usa fallback original→copia; `broken` solo si faltan ambos. KPI-8 nuevo lo sella.
- **C3 (IMPORTANTE, resuelto):** §2bis v1 afirmaba que el 176 "no declara tocar" `create_run` — FALSO: el 176 declara extender `create_run` con kwargs keyword-only y editar `services/dbcompare_runs.py` + `api/db_compare.py` (176 líneas 826 y 854). §2bis y R1 ahora declaran la colisión de firma como CONOCIDA con guía de merge explícita.
- **C4 (IMPORTANTE, resuelto):** el wiring de F7 (`onOpenRun={handleSelectHistoricalRun}`) no tipa — `handleSelectHistoricalRun` recibe `CompareRun`, no `run_id: string` (`DbComparePage.tsx:93`). El JSX exacto ahora incluye el adapter inline con cast.
- **C5 (IMPORTANTE, resuelto):** el presupuesto diario se cuenta desde runs retenidos (`_MAX_RUNS_KEPT = 100`), así que `max_value=500` prometía presupuestos incontables. Bound bajado a `max_value=100` y R3 reescrito con el cálculo real de desplazamiento del histórico manual (48/día ⇒ ~2,1 días para ocupar los 100 slots).
- **C6 (IMPORTANTE, resuelto):** F5 no especificaba manejo de body inválido (KeyError ⇒ 500). Rutas POST ahora con `request.get_json(silent=True) or {}` + validación explícita 400, pseudocódigo incluido.
- **C7 (IMPORTANTE, resuelto):** F4 v1 importaba privados cross-módulo (`_baseline_path`, `_IO_LOCK` de baseline desde watch; `_write_json_atomic` de watch desde baseline). Fix: API pública `dbcompare_baseline.mark_alerted()` + `load_baseline_snapshot()`, y baseline duplica sus 3 helpers triviales (decisión explícita: 8 líneas duplicadas > acoplamiento a privados ajenos).
- **C8 (MENOR, resuelto):** `assert kind in _EVENT_KINDS` desaparece bajo `python -O`; ahora `raise ValueError`.
- **C9 (MENOR, resuelto):** aliases conteniendo `__` colisionaban `watch_id` ("A__B"+"C" vs "A"+"B__C"); `upsert_watch` los rechaza con `DbCompareWatchError`.
- **C10 (MENOR, resuelto):** `test_config_defaults` "(con env limpio)" era vago; reescrito como asserts deterministas sobre los helpers de clamping con `monkeypatch`.
- **C11 (MENOR, resuelto):** el smoke F8 no cubría el deploy congelado (PyInstaller); ítem nuevo verificando el arranque del daemon y la API en el .exe empaquetado.
- **C12 (MENOR, resuelto) [ADICIÓN ARQUITECTO]:** el radar quedaba estático tras montar (badge de eventos congelado). `EnvironmentRadar` ahora auto-refresca `/radar` cada 60 s SOLO mientras está montado, con cleanup y corte ante error (spec exacta en F7).
- **C13 (MENOR, resuelto):** comportamiento con <2 ambientes especificado (sección colapsada con hint).
- Vaguedades eliminadas: `api.delete` EXISTE (verificado `endpoints.ts:3990,:3999`) — se afirma, no se condiciona; `relativeTime.ts` ya no se "verifica al implementar": helper local determinista `relativeFromIso` en `radarLogic.ts` con test; el tipo del diff se referencia como `NonNullable<CompareRun["diff"]>` sin adivinar nombres.

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Convertir el comparador de BD de una herramienta **bajo demanda** en un **radar continuo**: el operador marca pares origen→destino como "vigilados" con un click, un loop de background re-corre snapshot+diff de esquema (solo lectura) a intervalo configurable, y la UI muestra una matriz N×N de estado de drift, tendencia por par, baselines pinneados y avisos locales cuando aparece drift nuevo — sin que Stacky ejecute jamás una escritura ni publique nada afuera.

### 1.2 Qué cierra

Los dos diferidos explícitos que nadie tomó, declarados en 123 §6, 124 §6 y re-declarados en 176 §6 "Fuera de scope":

- (a) "Scheduling / diffs programados / notificaciones" → lo cierra el **vigía de drift** (F2/F3/F6) con avisos **locales** (F5), jamás push externo.
- (b) "Comparar 3+ ambientes a la vez" → lo cierra la **matriz N×N** (F5/F7): no compara 3 ambientes en una corrida (eso sigue diferido como corrida multi-ambiente), sino que muestra el estado de TODOS los pares a partir de corridas persistidas, que es lo que el operador de verdad necesita para "ver todos los ambientes de un vistazo".

### 1.3 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | Con `STACKY_DB_COMPARE_RADAR_ENABLED=false` (o master 122 OFF), la API y la UI son idénticas a main: endpoints nuevos devuelven 403, cero UI nueva renderizada, suite existente verde. | `tests/test_plan178_api.py` (403) + `EnvironmentRadar` retorna `null` ante error + `npx tsc --noEmit` |
| KPI-2 | Con la flag radar ON pero **cero pares vigilados**, `run_watch_sweep_once()` retorna 0 sin invocar `take_snapshot` ni `get_credential` ni abrir conexión alguna (costo ~0). | `tests/test_plan178_sweep.py::test_sweep_noop_sin_watches` con centinelas monkeypatch |
| KPI-3 | "Vigilar este par" es exactamente 1 click; el watch queda persistido en `watches.json` y la primera corrida del vigía se lanza en el primer tick con vencimiento cumplido. | `tests/test_plan178_watch_store.py` + `tests/test_plan178_sweep.py::test_due_lanza_create_run_fresh` |
| KPI-4 | Presupuesto y backoff se respetan de forma determinista: con `MAX_RUNS_PER_DAY=N`, el intento N+1 del día no lanza corrida; tras un run en `status="error"`, el próximo intento espera `interval * 2^consecutive_errors` (cap 1440 min) **y la cosecha de un run fallido incrementa `consecutive_errors` EXACTAMENTE una vez** (idempotencia por run: cosechar dos veces el mismo run no re-incrementa ni re-emite — fix C1). | `tests/test_plan178_sweep.py` (reloj inyectado, sin sleeps; incluye `test_harvest_error_es_idempotente`) |
| KPI-5 | Una transición sin-diff→con-diff emite EXACTAMENTE 1 `DriftEvent` `drift_new`; corridas subsiguientes con el mismo resultado emiten 0 eventos (sin duplicados). | `tests/test_plan178_events.py::test_dedup_transiciones` |
| KPI-6 | Pinnear baseline y pedir el diff-contra-baseline NO abre ninguna conexión a BD: opera 100% sobre snapshots ya persistidos en disco. | `tests/test_plan178_baseline.py` con centinela sobre `take_snapshot` |
| KPI-7 | Todo run lanzado por el vigía ejecuta ÚNICAMENTE el camino de snapshot de esquema + diff del motor 122/123 (SELECTs de metadata); el vigía no invoca jamás el data-diff (126) ni la generación de scripts (125). | Inspección de `run_watch_sweep_once` (solo llama `create_run`, que es solo-esquema por diseño, `services/dbcompare_runs.py:179-204`) + `tests/test_plan178_sweep.py` |
| KPI-8 | **(nuevo v2, fix C2)** Con el snapshot original del baseline BORRADO (simulando `prune_snapshots`), `baseline_diff` sigue funcionando desde la copia autocontenida y `list_baselines` reporta `broken == False`; `broken == True` solo si faltan original Y copia. | `tests/test_plan178_baseline.py::test_baseline_sobrevive_prune_de_snapshots` |

---

## 2. Por qué ahora / gap

1. **El motor ya existe y está congelado**: snapshots read-only por alias (`services/dbcompare_snapshot.py:144` `take_snapshot`), diff determinista con severidades (`services/dbcompare_diff.py:283` `diff_snapshots`, tabla `_KIND_SEVERITY` en `:28-52`), corridas con lock por par (`services/dbcompare_runs.py:130` `create_run`, `DbCompareBusyError` en `:38`, lock `:145-150`) y persistencia por archivo en `data_dir()/db_compare/runs/` (`:30`). Este plan NO agrega capacidad de comparación nueva: agrega **cadencia, memoria y visión de conjunto** sobre lo que ya funciona.
2. **El gap real del operador**: hoy el drift entre ambientes se descubre cuando muerde — en un pase a producción, o cuando alguien pregunta "¿TEST está igual a PROD?". El comparador responde esa pregunta solo si alguien se acuerda de correrlo. Un radar que re-corre solo y avisa localmente convierte "descubrir el drift tarde" en "verlo el mismo día que aparece".
3. **Los diferidos están documentados y maduros**: 123 §6 y 124 §6 difirieron scheduling/notificaciones y multi-ambiente; 176 §6 los volvió a diferir explícitamente. Con la capa 1 implementada y estable en main, es el momento de cerrarlos con reuso puro.
4. **Costo marginal mínimo**: la matriz, la tendencia, el baseline y los avisos se computan de datos locales ya persistidos (runs y snapshots). La única autonomía nueva — conectarse a BD sin click inmediato — queda acotada al vigía per-par, que nace apagado y se enciende con aprobación humana explícita (ver §3.2).

---

## 2bis. Relación con los planes 157, 176 y 152 (integración condicional, cero dependencia dura)

Al momento de escribir este plan, **ni el 157 ni el 176 están implementados** (sus archivos no existen en el working tree) y el **plan 152 (Centro de Notificaciones) tampoco** (grep de `NotificationCenter` en `frontend/src` da cero resultados, verificado 2026-07-18). Este plan se implementa contra **main tal como está hoy** y declara:

1. **Cero dependencia dura**: ningún archivo de este plan importa ni asume archivos del 157 (`EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `MigrationPanel.tsx`, `dbcompare_config_import.py`), del 176 (`Triage`, `Gates`, `TablePrefs`, `ClosureReport`) ni del 152 (`NotificationCenter`). Si esos planes se implementan antes, después o nunca, este plan funciona igual.
2. **Minimización de colisión de merge** con el 176 (que toca `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts`, `dbcompare.module.css`, `api/db_compare.py` y `services/dbcompare_runs.py`):
   - Backend: TODO el código nuevo vive en módulos NUEVOS (`services/dbcompare_watch.py`, `services/dbcompare_baseline.py`, `api/db_compare_watch.py`). `api/db_compare.py` NO se toca. Las ediciones a archivos existentes son puntuales: 2 líneas en `api/__init__.py` (el 176 no lo toca), 1 kwarg aditivo en `services/dbcompare_runs.py::create_run`, 1 bloque nuevo en `backend/app.py` (el 176 no lo toca), altas en `harness_flags.py`/`config.py`/runners de tests.
   - **Colisión CONOCIDA con el 176 en `create_run` (fix C3):** el 176 TAMBIÉN declara extender la firma de `create_run` con kwargs keyword-only (176 líneas 826 y 854, "modo snapshot histórico"). Ambos cambios son kwargs aditivos con default y ORTOGONALES (este plan: `initiated_by: str = "operator"`; el 176: los suyos). Guía de merge obligatoria: quien mergee segundo COMBINA ambos kwargs en la única firma (orden alfabético tras `mode`), conserva ambas claves en el dict de run, y re-corre por archivo los tests de ambos planes (`tests/test_plan178_sweep.py` + los del 176) más `tests/test_dbcompare_runs*.py` preexistentes.
   - Frontend: componentes NUEVOS autocontenidos (`EnvironmentRadar.tsx`, `DriftEventsPanel.tsx`, `radarLogic.ts`, `radarTypes.ts`). En `DbComparePage.tsx` el punto de montaje es **exactamente 1 import + 1 elemento JSX** (F7). En `endpoints.ts` se agrega un objeto NUEVO `DbCompareWatch` al final del archivo, sin tocar el objeto `DbCompare` existente (`frontend/src/api/endpoints.ts:3967`). `SummaryHero.tsx` NO se toca.
   - Gotcha conocido de merge (memoria del repo): cuando dos ramas agregan líneas al final del mismo archivo, git puede fusionar sin marcar conflicto y duplicar una línea de cierre. Tras cualquier merge que involucre `endpoints.ts` o `dbcompare.module.css`, correr `npx tsc --noEmit` y grep del identificador agregado (`DbCompareWatch`) esperando exactamente 1 declaración.
3. **Integración condicional con el 152** (mismo patrón que el 176 usó con el 157): el fallback primario de avisos es un **badge + panel propio dentro de la página DB Compare** (F7). SI al momento de implementar existe el Centro de Notificaciones del 152 (verificarlo con `grep -r "NotificationCenter" frontend/src`), el implementador PUEDE además publicar los `DriftEvent` en ese centro como fuente adicional — pero es opcional, aditivo y no bloquea ninguna fase de este plan. Si no existe, no se crea nada fuera de la página DB Compare.

---

## 3. Principios y guardarraíles

### 3.1 Doctrina de la serie (se hereda intacta)

- **Stacky GENERA/observa, nunca ejecuta**: el vigía corre SOLO el camino de snapshot de esquema + diff (SELECTs de metadata vía SQLAlchemy Inspector del motor 122). NUNCA ejecuta escrituras, NUNCA corre scripts, NUNCA publica nada fuera de la máquina (ni email, ni push, ni tickets automáticos). Los avisos son registros locales en disco + UI local.
- **Solo esquema, jamás datos**: el vigía NO compara datos (no invoca el data-diff del 126). Motivos: (1) más barato — metadata vs filas; (2) sin PII — el snapshot de esquema no contiene datos de negocio. La paridad de DATOS sigue siendo una acción 100% manual del operador (botón existente del 126).
- **Contratos congelados intocables**: Snapshot v1 (122 §F3), SchemaDiff v1 + `_KIND_SEVERITY` + semántica origen/destino (123 §F1, `services/dbcompare_diff.py:28`), Manifest v1 + backup pareado 1:1 (125 §F3), DataDiff v1 (126 §F1-F2). Este plan solo agrega contratos NUEVOS versionados (Watch v1, DriftEvent v1, Baseline v1) y UN campo aditivo opcional (`initiated_by` en el dict de run, que NO es un contrato congelado).
- **Human-in-the-loop innegociable**: el vigía observa y avisa; toda ACCIÓN (comparar datos, generar scripts, migrar, cerrar drift) sigue siendo del operador.
- **Mono-operador sin auth real**: nada de RBAC, nada de permisos por usuario.

### 3.2 La excepción dura del default apagado per-par (citarla literal en el código)

La conexión automática a BD en background es la ÚNICA parte de este plan con autonomía. Se trata así:

- La flag maestra del plan (`STACKY_DB_COMPARE_RADAR_ENABLED`) nace **ON**: la matriz, el baseline, la tendencia y los avisos no conectan nada solos — leen datos locales persistidos. ON no genera ninguna conexión.
- El vigía **per-par nace APAGADO por par** y se enciende con UN click del operador ("Vigilar este par"). Aplica la excepción dura **(3) prerequisito no garantizado**: las credenciales y la conectividad a la BD del cliente no están garantizadas en una instalación default — y además se evita la sorpresa de conexiones no pedidas a bases del cliente. **El click de "Vigilar" ES la aprobación humana explícita** para que Stacky se conecte periódicamente en background a ese par, y solo a ese par. Documentar este párrafo (resumido) como comentario en `services/dbcompare_watch.py` junto a `upsert_watch`.

### 3.3 Guardarraíles técnicos

- **Read-only garantizado por construcción**: el vigía solo invoca `create_run(...)` del motor (`services/dbcompare_runs.py:130`), cuyo `_execute_run` (`:179-204`) hace `take_snapshot` + `diff_snapshots` y nada más. No se agrega ningún camino nuevo de acceso a BD.
- **Respeto del lock existente**: si hay corrida activa del par, `create_run` lanza `DbCompareBusyError` (`services/dbcompare_runs.py:38`, chequeo `:147-150`); el vigía la captura y saltea el tick sin contar error.
- **Cosecha idempotente por run (fix C1)**: `last_harvested_run_id` en Watch v1 garantiza que un run (done, error o stale) se cosecha EXACTAMENTE una vez; sin ese marcador, un run en error se re-cosecharía cada tick de 60 s (backoff degenerado + eventos duplicados).
- **Baseline autocontenido (fix C2)**: al pinnear, el Snapshot v1 completo se COPIA a `baselines/<alias>.snapshot.json`; la retención del motor (`_MAX_SNAPSHOTS_PER_ALIAS = 20`, `services/dbcompare_snapshot.py:31`) puede borrar el original sin romper el baseline.
- **Escrituras de estado atómicas**: todo JSON de estado nuevo se escribe con patrón tmp + `os.replace` (mismo espíritu que `_write_bundle_atomic`, `services/dbcompare_scripts.py:706-723`).
- **Flags**: todas las flags nuevas en `FLAG_REGISTRY` con categoría `comparador_bd` (`services/harness_flags.py:106-108` y `_CATEGORY_KEYS` `:320-324`), `requires="STACKY_DB_COMPARE_ENABLED"` SIEMPRE plano (profundidad 1: jamás encadenar a una flag hija). Default ON solo vía `_CURATED_DEFAULTS_ON` (`services/harness_flags.py:310` ya contiene el master 122) y SOLO para bools; las flags int NO llevan `default=` en el spec (gotcha documentado en `services/harness_flags.py:3143-3147`), su default efectivo vive en `config.py`.
- **`config.config` en API**: en `api/*.py` la instancia de flags es `config.config`, NO el módulo (`api/db_compare.py:27-29` usa `getattr(_config.config, ...)` — copiar ese idioma).
- **Loop de background**: patrón literal del plan 117 (`backend/app.py:463-491`): guard `if "pytest" not in _sys.modules:`, `threading.Thread(target=..., name="stacky-...-daemon", daemon=True).start()`, `while True: try/except logger.exception → time.sleep(...)`, gates de flags evaluados EN CADA iteración dentro del sweep (hot-apply, sin restart). Bajo pytest el thread NO arranca (mismo guard) y además `backend/tests/conftest.py:11` setea `STACKY_TEST_MODE=1` — el sweep es funcion pura invocable en tests sin thread.
- **Cero egress en tests**: los tests del vigía monkeypatchean `create_run`/`data_dir` y NUNCA tocan una BD real (los ambientes de test ni existen); ningún test debe requerir red.
- **Frontend sin tests de render**: NO hay `@testing-library/react` ni `jsdom` (gap estructural conocido). Toda la lógica de UI va en helpers `.ts` puros con vitest por archivo + `npx tsc --noEmit`. CERO `style={{...}}` en `.tsx` nuevos (ratchet `uiDebtRatchet`): estilos en `dbcompare.module.css` con los tokens `--dbc-*` existentes (`--dbc-danger`, `--dbc-warn`, `--dbc-info`, `--dbc-unchanged`, `--dbc-added`, `--dbc-removed`, `--dbc-changed`); estilo dinámico = `ref` + effect imperativo.
- **Config del operador SIEMPRE por UI**: las 3 flags nuevas quedan visibles/toggleables en el panel del arnés (categoría `comparador_bd`) automáticamente al registrarlas; las int llevan `min_value`/`max_value` como `STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC` (`services/harness_flags.py:3137-3151`).
- **Tests backend por archivo**: cada `tests/test_plan178_*.py` nuevo se registra en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh:20` Y su espejo `backend/scripts/run_harness_tests.ps1`, o el meta-test del ratchet se pone rojo. Pytest SIEMPRE por archivo con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`.

### 3.4 Paridad de runtimes

Esta feature es de PANEL (backend Flask + React, sin LLM): idéntica en los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro). No hay fallback por runtime; la única degradación posible es la ya existente del comparador por drivers de BD faltantes (aviso de drivers en `DbComparePage.tsx:114` `missingDrivers`), que aplica igual al vigía: un run del vigía contra un ambiente sin driver termina en `status="error"` y activa el backoff — sin romper nada.

---

## 4. Contratos nuevos (versionados, aditivos)

Persistencia bajo `data_dir()/db_compare/` (consistente con `db_compare/snapshots` — `services/dbcompare_snapshot.py:30`, `db_compare/runs` — `services/dbcompare_runs.py:30`, `db_compare/bundles` — `services/dbcompare_scripts.py:660`):

### 4.1 Watch v1 — `data_dir()/db_compare/watch/watches.json`

```json
{
  "version": 1,
  "watches": [
    {
      "watch_id": "DEV__TEST",
      "source_alias": "DEV",
      "target_alias": "TEST",
      "enabled": true,
      "created_at": "2026-07-18T12:00:00Z",
      "last_attempt_at": "2026-07-18T13:00:00Z",
      "last_run_id": "run_20260718T130001Z_DEV_vs_TEST",
      "last_done_run_id": "run_20260718T120001Z_DEV_vs_TEST",
      "last_harvested_run_id": "run_20260718T120001Z_DEV_vs_TEST",
      "last_summary": {"by_severity": {"info": 0, "warn": 2, "danger": 0}, "parity_score": 98.5},
      "consecutive_errors": 0
    }
  ]
}
```

- `watch_id = f"{source_alias}__{target_alias}"` (separador doble guion bajo; el ORDEN importa: conserva la semántica origen→destino del SchemaDiff v1 del 123). Para que el id sea no-ambiguo, `upsert_watch` RECHAZA aliases que contengan `__` (fix C9).
- `last_summary` es la copia mínima del `summary` del último run `done` cosechado (para detectar transiciones sin releer runs viejos). `null` si nunca hubo run done.
- `last_run_id` = último run LANZADO (puede estar corriendo o en error); `last_done_run_id` = último cosechado con `status="done"`.
- `last_harvested_run_id` **(nuevo v2, fix C1)** = último run YA COSECHADO, sea cual fuere su desenlace (`done`, `error` o stale). Es el marcador de idempotencia de la cosecha: `_harvest_watch` NO hace nada si `last_run_id == last_harvested_run_id`. `null` inicial.
- Campos aditivos opcionales permitidos a futuro; NUNCA se reinterpretan los existentes.

### 4.2 DriftEvent v1 — `data_dir()/db_compare/watch/events.json`

```json
{
  "version": 1,
  "events": [
    {
      "event_id": "evt_20260718T130500Z_DEV__TEST",
      "kind": "drift_new",
      "watch_id": "DEV__TEST",
      "source_alias": "DEV",
      "target_alias": "TEST",
      "run_id": "run_20260718T130001Z_DEV_vs_TEST",
      "created_at": "2026-07-18T13:05:00Z",
      "read": false,
      "detail": {"by_severity": {"info": 1, "warn": 3, "danger": 1}, "parity_score": 91.2}
    }
  ]
}
```

- `kind` ∈ {`drift_new`, `drift_worse`, `drift_cleared`, `baseline_violation`, `watch_error`} (tabla CERRADA v1; ver F3 la semántica exacta).
- Lista capada a los **200** eventos más recientes (al append, recortar por `created_at` descendente). `event_id = f"evt_{timestamp:%Y%m%dT%H%M%SZ}_{watch_id}"` (con sufijo `_2`, `_3`… si colisiona en el mismo segundo).
- Para `baseline_violation`, `watch_id` puede ser `null` y se agrega `"alias"` + `"baseline_snapshot_id"` en `detail`.

### 4.3 Baseline v1 — `data_dir()/db_compare/baselines/<alias>.json` **+ copia autocontenida `<alias>.snapshot.json`**

```json
{
  "version": 1,
  "alias": "PROD",
  "snapshot_id": "snap_20260710T090000Z_PROD",
  "pinned_at": "2026-07-18T10:00:00Z",
  "note": "estado bendecido release 3.2",
  "last_alerted_content_hash": null
}
```

- Un (1) baseline por alias; pinnear de nuevo REEMPLAZA ambos archivos. Despinnear = borrar ambos archivos.
- `snapshot_id` debe existir en `data_dir()/db_compare/snapshots/<alias>/` al pinnear (validado con `load_snapshot`, `services/dbcompare_snapshot.py:261`).
- **[ADICIÓN ARQUITECTO] (fix C2) Copia autocontenida**: `pin_baseline` escribe el Snapshot v1 COMPLETO en `baselines/<alias>.snapshot.json` (escritura atómica). Motivo verificado: el motor poda snapshots (`_MAX_SNAPSHOTS_PER_ALIAS = 20`, `services/dbcompare_snapshot.py:31`; `prune_snapshots` corre en cada `take_snapshot`, `:226`) y un vigía activo genera ~24 snapshots/día por alias ⇒ sin copia, el baseline moría en <1 día. La resolución del snapshot del baseline SIEMPRE intenta primero el original (`load_snapshot`) y cae a la copia local. `"broken": true` solo si faltan AMBOS (borrado manual de la carpeta) — y la API lo reporta sin crashear.
- `last_alerted_content_hash`: dedup de `baseline_violation` — hash del último snapshot del ambiente por el que YA se avisó (ver F4).
- `note` opcional, máx. 200 chars.

### 4.4 Tendencia: SIN contrato nuevo (decisión justificada)

La serie temporal por par se **DERIVA** de los runs ya persistidos: cada run `done` trae `finished_at` + `summary.by_severity` + `summary.parity_score` (`services/dbcompare_diff.py:264-280`, persistido por `_execute_run` en `services/dbcompare_runs.py:194-197`). Es el mismo patrón "cero endpoints nuevos, cero estado nuevo" que ya usó `runHistory.ts` del plan 124 (`frontend/src/components/dbcompare/runHistory.ts:1-3`). Costo: la ventana de tendencia queda acotada por la retención del motor (`_MAX_RUNS_KEPT = 100`, `services/dbcompare_runs.py:32`) — aceptado y documentado en la UI como "tendencia de las últimas corridas retenidas". Beneficio: cero riesgo de divergencia entre dos fuentes de verdad. Se descarta TrendPoint v1.

---

## 5. Fases

Orden de dependencia: F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8. Cada fase es verificable sola; el sistema queda funcional (y byte-compatible con flags OFF) después de cada una.

---

### F0 — Flags, config y aristas requires

**Objetivo:** registrar las 3 flags del plan con sus defaults, categoría, bounds y aristas, sin ningún comportamiento nuevo.
**Valor:** el radar aparece en el panel del arnés (categoría "Comparador de BD entre ambientes") toggleable por UI desde el día 0.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/services/harness_flags.py`
   - En `_CURATED_DEFAULTS_ON` (el set que hoy contiene `"STACKY_DB_COMPARE_ENABLED"` en `:310`), agregar UNA entrada:
     ```python
     "STACKY_DB_COMPARE_RADAR_ENABLED",      # Plan 178 — radar de ambientes (matriz/baseline/tendencia/avisos; el vigía per-par nace OFF por par)
     ```
   - En `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`), agregar TRES keys (mantener orden por plan):
     ```python
     "STACKY_DB_COMPARE_RADAR_ENABLED",        # Plan 178
     "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN",   # Plan 178
     "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY",  # Plan 178
     ```
   - En `FLAG_REGISTRY`, inmediatamente después del bloque del Plan 126 (tras la FlagSpec de `STACKY_DB_COMPARE_DATA_MAX_ROWS`, `:3162-3175`), agregar TRES FlagSpec copiando el idioma exacto de las vecinas:
     ```python
     # ── Plan 178 — Radar de ambientes (vigía de drift + matriz N×N + baseline) ──
     FlagSpec(
         key="STACKY_DB_COMPARE_RADAR_ENABLED",
         type="bool",
         default=True,  # ON: matriz/baseline/tendencia/avisos solo LEEN datos locales; el vigía per-par nace OFF y se enciende con 1 click (aprobación humana explícita — excepción dura 3: credenciales/conectividad a BD del cliente no garantizadas).
         label="Comparador BD: radar de ambientes",
         description="Radar continuo (plan 178): matriz N×N de drift por par, baseline pinneado, tendencia y avisos locales. El vigía programado por par se activa con un click en la UI. OFF = todo invisible y el loop de fondo en no-op.",
         group="global",
         requires="STACKY_DB_COMPARE_ENABLED",
     ),
     FlagSpec(
         key="STACKY_DB_COMPARE_WATCH_INTERVAL_MIN",
         type="int",
         label="Comparador BD: intervalo del vigía (min)",
         description="Cada cuántos minutos el vigía re-corre snapshot+diff de esquema de cada par vigilado. Default 60.",
         group="global",
         # NO default= acá: mismo gotcha que STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
         # (Plan 122, ver services/harness_flags.py:3143-3147) — default_is_known()
         # trata cualquier spec.default no-None como "curado" y exige alta en
         # _CURATED_DEFAULTS_ON, set reservado a promociones bool=True. El valor
         # real "60" vive en config.py.
         requires="STACKY_DB_COMPARE_ENABLED",
         min_value=5,
         max_value=1440,
     ),
     FlagSpec(
         key="STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY",
         type="int",
         label="Comparador BD: presupuesto del vigía (corridas/día)",
         description="Cap duro de corridas lanzadas por el vigía por día calendario UTC, sumando todos los pares vigilados. Default 48.",
         group="global",
         # NO default= acá: mismo gotcha que arriba; el valor real "48" vive en config.py.
         # max_value=100 y no más (fix C5): el conteo diario se computa desde los runs
         # retenidos (_MAX_RUNS_KEPT=100, services/dbcompare_runs.py:32) — un presupuesto
         # mayor a la retención sería incontable y por lo tanto una promesa falsa.
         requires="STACKY_DB_COMPARE_ENABLED",
         min_value=1,
         max_value=100,
     ),
     ```
   - NOTA de profundidad 1: las tres aristas `requires` apuntan al master 122 `STACKY_DB_COMPARE_ENABLED`, NUNCA a `STACKY_DB_COMPARE_RADAR_ENABLED` (prohibido encadenar a flag hija).

2. `Stacky Agents/backend/config.py` — inmediatamente después del bloque del Plan 126 (`:127-133`), agregar copiando el idioma literal de `:119-133`:
   ```python
   # ── Plan 178 — Radar de ambientes (vigía de drift programado) ──────────
   # Default ON: la matriz/baseline/tendencia solo leen datos locales; el vigía
   # per-par nace OFF por par (excepción dura 3) y se enciende con 1 click.
   STACKY_DB_COMPARE_RADAR_ENABLED: bool = os.getenv(
       "STACKY_DB_COMPARE_RADAR_ENABLED", "true"
   ).strip().lower() == "true"
   STACKY_DB_COMPARE_WATCH_INTERVAL_MIN: int = int(
       os.getenv("STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", "60")
   )
   STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY: int = int(
       os.getenv("STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", "48")
   )
   ```

3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — en `_REQUIRES_MAP_FROZEN` (`:120`), junto a las aristas DB_COMPARE existentes (`:183-185`), agregar TRES líneas:
   ```python
   "STACKY_DB_COMPARE_RADAR_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 178
   "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN": "STACKY_DB_COMPARE_ENABLED",  # Plan 178
   "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY": "STACKY_DB_COMPARE_ENABLED",  # Plan 178
   ```

4. `Stacky Agents/backend/scripts/run_harness_tests.sh` (lista `HARNESS_TEST_FILES`, `:20`) y su espejo `run_harness_tests.ps1`: agregar `tests/test_plan178_flags.py` (y en cada fase siguiente, su archivo de test).

5. Regenerar `harness_defaults.env` con el generador oficial (PROHIBIDO editarlo a mano): `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" scripts/export_harness_defaults.py`.

**Test PRIMERO — `Stacky Agents/backend/tests/test_plan178_flags.py`:**
- `test_radar_flag_registrada_bool_default_on`: `FLAG_REGISTRY` contiene `STACKY_DB_COMPARE_RADAR_ENABLED`, `type=="bool"`, `spec.default is True`, `requires=="STACKY_DB_COMPARE_ENABLED"`.
- `test_flags_int_sin_default_con_bounds`: las dos int existen, `spec.default is None`, `min_value`/`max_value` == (5,1440) y (1,100), `requires=="STACKY_DB_COMPARE_ENABLED"`.
- `test_flags_en_categoria_comparador_bd`: las 3 keys están en `_CATEGORY_KEYS["comparador_bd"]`.
- `test_config_attrs_existen_con_tipo` (fix C10 — determinista, sin depender del env de la máquina): `isinstance(config.config.STACKY_DB_COMPARE_RADAR_ENABLED, bool)`, `isinstance(...WATCH_INTERVAL_MIN, int)`, `isinstance(...WATCH_MAX_RUNS_PER_DAY, int)`. Los VALORES default (60/48) y el clamping se verifican en F2 vía `_interval_minutes()`/`_max_runs_per_day()` con `monkeypatch.setattr(config.config, ..., raising=False)`, que es determinista.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_flags.py -q`
**También deben seguir verdes:** `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py` (mismo comando por archivo).

**Criterio de aceptación (binario):** los 4 tests nuevos + los 2 archivos preexistentes pasan; `harness_defaults.env` regenerado por script.
**Flag que protege la fase:** ninguna (solo registro); cero comportamiento nuevo.
**Runtimes:** idéntico en los 3 (panel).
**Trabajo del operador:** ninguno.

---

### F1 — Watch v1: store de pares vigilados (CRUD atómico)

**Objetivo:** módulo de persistencia de watches con escritura atómica, sin scheduler todavía.
**Valor:** base determinista y testeable de todo el vigía.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_watch.py`

Estructura EXACTA (firmas y comportamiento; el implementador copia esto):

```python
"""Plan 178 — Vigía de drift programado (Watch v1 + DriftEvent v1 + sweep).

Read-only por construcción: el vigía SOLO invoca dbcompare_runs.create_run()
(snapshot de esquema + diff del motor 122/123). Jamás compara datos (126),
jamás genera scripts (125), jamás publica fuera de la máquina.

Aprobación humana explícita: cada watch nace del click "Vigilar este par" del
operador (excepción dura 3: credenciales/conectividad a BD del cliente no
garantizadas en una instalación default — y se evita la sorpresa de conexiones
no pedidas). Sin ese click, este módulo no abre ninguna conexión.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

_WATCH_DIRNAME = "db_compare/watch"
WATCH_VERSION = 1
_IO_LOCK = threading.Lock()


class DbCompareWatchError(RuntimeError):
    """Watch inválido (aliases inexistentes, par duplicado, watch_id desconocido)."""


def _watch_dir() -> Path:
    d = data_dir() / _WATCH_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _watches_path() -> Path:
    return _watch_dir() / "watches.json"


def _write_json_atomic(path: Path, payload: dict) -> None:
    # Patrón tmp + os.replace (mismo espíritu que _write_bundle_atomic,
    # services/dbcompare_scripts.py:706): nunca queda un JSON parcial.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def watch_id_for(source_alias: str, target_alias: str) -> str:
    return f"{source_alias}__{target_alias}"


def list_watches() -> list[dict]:
    path = _watches_path()
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(doc.get("watches") or [])


def _save_watches(watches: list[dict]) -> None:
    _write_json_atomic(_watches_path(), {"version": WATCH_VERSION, "watches": watches})


def upsert_watch(source_alias: str, target_alias: str, *, enabled: bool) -> dict:
    # Valida contra el registry real (services/dbcompare_registry.py:107).
    from services import dbcompare_registry
    if source_alias == target_alias:
        raise DbCompareWatchError("origen y destino no pueden ser el mismo ambiente")
    if "__" in source_alias or "__" in target_alias:
        # Fix C9: el watch_id usa "__" como separador; un alias que lo contenga
        # haría ambiguo el id ("A__B"+"C" vs "A"+"B__C").
        raise DbCompareWatchError("aliases con '__' no son vigilables (separador reservado)")
    if dbcompare_registry.get_environment(source_alias) is None:
        raise DbCompareWatchError(f"ambiente desconocido: '{source_alias}'")
    if dbcompare_registry.get_environment(target_alias) is None:
        raise DbCompareWatchError(f"ambiente desconocido: '{target_alias}'")
    wid = watch_id_for(source_alias, target_alias)
    with _IO_LOCK:
        watches = list_watches()
        existing = next((w for w in watches if w["watch_id"] == wid), None)
        if existing is None:
            existing = {
                "watch_id": wid,
                "source_alias": source_alias,
                "target_alias": target_alias,
                "enabled": enabled,
                "created_at": _iso(_now()),
                "last_attempt_at": None,
                "last_run_id": None,
                "last_done_run_id": None,
                "last_harvested_run_id": None,
                "last_summary": None,
                "consecutive_errors": 0,
            }
            watches.append(existing)
        else:
            existing["enabled"] = enabled
        _save_watches(watches)
    return dict(existing)


def delete_watch(watch_id: str) -> bool:
    with _IO_LOCK:
        watches = list_watches()
        remaining = [w for w in watches if w["watch_id"] != watch_id]
        if len(remaining) == len(watches):
            return False
        _save_watches(remaining)
    return True


def _update_watch(watch_id: str, **fields) -> None:
    with _IO_LOCK:
        watches = list_watches()
        for w in watches:
            if w["watch_id"] == watch_id:
                w.update(fields)
                break
        _save_watches(watches)
```

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan178_watch_store.py`:**
Todos redirigen la persistencia con `monkeypatch.setattr(dbcompare_watch, "data_dir", lambda: tmp_path)` (mismo estilo que el motor: `dbcompare_runs.py:27` importa `data_dir` como nombre del módulo) y monkeypatchean `dbcompare_registry.get_environment` para devolver dicts fake `{"alias": ..., "engine": "mssql"}`.
- `test_upsert_crea_watch_deshabilitado_no_existe_archivo_antes`: `list_watches()==[]` de entrada; `upsert_watch("DEV","TEST",enabled=True)` crea `watches.json` con `version==1` y 1 watch con los 11 campos del contrato (incluye `last_harvested_run_id is None`).
- `test_upsert_alias_desconocido_lanza`: registry devuelve None para "NOPE" → `DbCompareWatchError`.
- `test_upsert_alias_con_separador_lanza` (fix C9): `upsert_watch("A__B","C",...)` → `DbCompareWatchError`.
- `test_upsert_mismo_par_actualiza_enabled_sin_duplicar`: dos upserts del mismo par dejan 1 solo watch.
- `test_source_igual_target_lanza`.
- `test_delete_watch_true_false`.
- `test_escritura_atomica_no_deja_tmp`: tras upsert no existe `watches.json.tmp`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_watch_store.py -q`
**Criterio de aceptación:** 7 tests verdes; el módulo NO importa nada de conexión (grep: `import` en `dbcompare_watch.py` no contiene `sqlalchemy` ni `dbcompare_connect`).
**Flag:** todavía sin efecto visible (el módulo no se invoca desde ningún lado).
**Runtimes:** idéntico en los 3. **Trabajo del operador:** ninguno.

---

### F2 — Vigía: sweep determinista (due, jitter, backoff, presupuesto, busy-skip, cosecha idempotente)

**Objetivo:** `run_watch_sweep_once()` que cosecha resultados de corridas previas y lanza las corridas vencidas, con todas las protecciones, como función pura testeable (sin thread todavía).
**Valor:** el corazón del radar: re-comparación automática segura y barata.

**Archivos a editar/crear:**

1. `Stacky Agents/backend/services/dbcompare_runs.py` — cambio ADITIVO mínimo (2 ediciones):
   - Firma: `def create_run(source_alias: str, target_alias: str, *, mode: str = "fresh", initiated_by: str = "operator") -> dict:` (`:130`).
   - En el dict `run` (`:154-162`), agregar la clave `"initiated_by": initiated_by,`.
   - Compat: los runs viejos no tienen el campo → SIEMPRE leer con `run.get("initiated_by", "operator")`. `list_runs` (`:217`) ya lo devuelve solo (meta = todo salvo `diff`, `:227`). El dict de run NO es un contrato congelado; el campo es aditivo opcional.
   - RECORDATORIO de merge (§2bis, fix C3): el plan 176 también agrega kwargs keyword-only a esta MISMA firma; si el 176 ya se implementó, combinar ambos sets de kwargs en la única firma y conservar ambas claves del dict.

2. `Stacky Agents/backend/services/dbcompare_watch.py` — agregar (después del CRUD de F1):

```python
# --------------------------------------------------------------------------
# Sweep del vigía (Plan 178 F2) — determinista: el reloj se inyecta en tests.
# --------------------------------------------------------------------------
import zlib

_BACKOFF_CAP_MIN = 1440  # 24 h


def _interval_minutes() -> int:
    import config as _config
    try:
        val = int(getattr(_config.config, "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", 60))
    except (TypeError, ValueError):
        val = 60
    return max(5, min(val, 1440))


def _max_runs_per_day() -> int:
    import config as _config
    try:
        val = int(getattr(_config.config, "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY", 48))
    except (TypeError, ValueError):
        val = 48
    return max(1, min(val, 100))


def _radar_enabled() -> bool:
    import config as _config
    return bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)) and bool(
        getattr(_config.config, "STACKY_DB_COMPARE_RADAR_ENABLED", False)
    )


def _jitter_seconds(watch_id: str, interval_min: int) -> int:
    """Jitter DETERMINISTA por par: 0..20% del intervalo, estable entre ticks.
    Distribuye pares sin aleatoriedad real (testeable sin seeds)."""
    span = max(1, (interval_min * 60) // 5)
    return zlib.crc32(watch_id.encode("utf-8")) % span


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_due(watch: dict, now: datetime, interval_min: int) -> bool:
    last = _parse_iso(watch.get("last_attempt_at"))
    if last is None:
        return True
    effective_min = min(interval_min * (2 ** int(watch.get("consecutive_errors") or 0)), _BACKOFF_CAP_MIN)
    due_at_sec = last.timestamp() + effective_min * 60 + _jitter_seconds(watch["watch_id"], interval_min)
    return now.timestamp() >= due_at_sec


def _runs_launched_today(now: datetime) -> int:
    from services import dbcompare_runs
    today = now.strftime("%Y-%m-%d")
    count = 0
    for meta in dbcompare_runs.list_runs(200):
        if meta.get("initiated_by", "operator") != "watch":
            continue
        if (meta.get("started_at") or "").startswith(today):
            count += 1
    return count


def _harvest_watch(watch: dict) -> None:
    """Cosecha el resultado del último run lanzado (dos tiempos: lanzar en un
    tick, leer el resultado en el siguiente). Actualiza backoff y emite eventos.

    IDEMPOTENTE POR RUN (fix C1): last_harvested_run_id marca el run ya
    cosechado — done, error o stale por igual. Sin este corte, un run en error
    se re-cosecharía en CADA tick de 60 s: consecutive_errors explotaría
    (~60/hora) y events.json se llenaría de watch_error duplicados."""
    from services import dbcompare_runs
    run_id = watch.get("last_run_id")
    if not run_id or run_id == watch.get("last_harvested_run_id"):
        return
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        # El run fue borrado por la retención antes de poder cosecharlo:
        # marcar harvested para no reintentar por siempre.
        _update_watch(watch["watch_id"], last_harvested_run_id=run_id)
        return
    status = run.get("status")
    if status == "running" and not run.get("stale"):
        return  # sigue corriendo; nada que cosechar todavía
    if status == "error" or (status == "running" and run.get("stale")):
        _update_watch(
            watch["watch_id"],
            consecutive_errors=int(watch.get("consecutive_errors") or 0) + 1,
            last_harvested_run_id=run_id,
        )
        _append_event_watch_error(watch, run)   # F3
        return
    if status == "done":
        new_summary = {
            "by_severity": (run.get("summary") or {}).get("by_severity") or {"info": 0, "warn": 0, "danger": 0},
            "parity_score": (run.get("summary") or {}).get("parity_score", 100.0),
        }
        _emit_transition_events(watch, run, new_summary)      # F3
        _check_baselines_for_run(watch, run)                  # F4
        _update_watch(
            watch["watch_id"],
            consecutive_errors=0,
            last_done_run_id=run_id,
            last_harvested_run_id=run_id,
            last_summary=new_summary,
        )


def run_watch_sweep_once(now: datetime | None = None) -> int:
    """Un tick del vigía. Retorna cuántas corridas LANZÓ (0 en no-op).
    Gates evaluados acá adentro (hot-apply, patrón plan 117 app.py:463-491)."""
    if not _radar_enabled():
        return 0
    watches = [w for w in list_watches() if w.get("enabled")]
    if not watches:
        return 0
    now = now or _now()
    interval_min = _interval_minutes()
    launched = 0
    from services import dbcompare_runs
    from services.dbcompare_runs import DbCompareBusyError, DbCompareRunError
    for watch in watches:
        _harvest_watch(watch)
    # Releer: la cosecha pudo actualizar backoff/last_summary/harvested.
    watches = [w for w in list_watches() if w.get("enabled")]
    budget = _max_runs_per_day() - _runs_launched_today(now)
    for watch in watches:
        if budget - launched <= 0:
            break
        if not _is_due(watch, now, interval_min):
            continue
        pending_id = watch.get("last_run_id")
        if pending_id and pending_id != watch.get("last_harvested_run_id"):
            run = dbcompare_runs.get_run(pending_id)
            if run is not None and run.get("status") == "running" and not run.get("stale"):
                continue  # aún corre: no encimar
        try:
            run = dbcompare_runs.create_run(
                watch["source_alias"], watch["target_alias"], mode="fresh", initiated_by="watch"
            )
        except DbCompareBusyError:
            continue  # lock del par ocupado (dbcompare_runs.py:147-150): skip sin error
        except DbCompareRunError as exc:
            # alias borrado o motores distintos: deshabilitar y avisar (F3)
            _update_watch(watch["watch_id"], enabled=False)
            _append_event_watch_error(watch, {"run_id": None, "error": str(exc)})
            continue
        launched += 1
        _update_watch(watch["watch_id"], last_attempt_at=_iso(now), last_run_id=run["run_id"])
    return launched
```

Notas duras para el implementador:
- `_emit_transition_events`, `_append_event_watch_error` y `_check_baselines_for_run` se crean en F3/F4; en F2 se declaran los TRES como stubs no-op de una línea — `def _emit_transition_events(watch, run, new_summary): return None`, `def _append_event_watch_error(watch, run): return None`, `def _check_baselines_for_run(watch, run): return None` (mismas firmas que F3/F4 definen en las líneas de sus pseudocódigos) — para que F2 sea verde sola.
- El sweep JAMÁS llama `take_snapshot`/`get_credential` directo: solo `create_run` (que internamente hace todo bajo su propio thread y lock).
- `mode="fresh"` SIEMPRE: un vigía con `cached` no detectaría nada nuevo.

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan178_sweep.py`:**
Fixtures comunes: monkeypatch `data_dir` → `tmp_path`; monkeypatch `dbcompare_registry.get_environment` → fakes; monkeypatch `dbcompare_runs.create_run` → registra llamadas y devuelve `{"run_id": "run_test_1", ...}`; monkeypatch `dbcompare_runs.list_runs`/`get_run` → listas controladas; monkeypatch `config.config` attrs con `monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_RADAR_ENABLED", True, raising=False)`, y el MISMO idioma (`monkeypatch.setattr(config.config, "<KEY>", <valor>, raising=False)`) para cualquier otra de las flags de F0 que un caso necesite.
- `test_sweep_noop_flag_off`: radar OFF → retorna 0 y create_run NO fue llamado.
- `test_sweep_noop_sin_watches` (KPI-2): flag ON, cero watches → 0; centinelas de `take_snapshot`/`get_credential` (monkeypatch que hace `raise AssertionError`) nunca disparan.
- `test_due_lanza_create_run_fresh` (KPI-3): watch enabled con `last_attempt_at=None` → 1 lanzamiento con `mode=="fresh"` e `initiated_by=="watch"`; `last_run_id` actualizado.
- `test_no_due_no_lanza`: `last_attempt_at` = now − (interval/2) → 0 lanzamientos.
- `test_jitter_determinista`: `_jitter_seconds("DEV__TEST", 60)` retorna el mismo valor 2 veces y está en `[0, 720)`.
- `test_backoff_exponencial`: watch con `consecutive_errors=2`, `last_attempt_at` = now − 3×interval → NO due (2²×interval=4×interval); con `last_attempt_at` = now − 5×interval → due.
- `test_budget_diario` (KPI-4): `MAX_RUNS_PER_DAY=1`, `list_runs` devuelve 1 run `initiated_by=="watch"` de hoy → 0 lanzamientos nuevos.
- `test_clamps_de_flags` (fix C10): `monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN", 100000, raising=False)` → `_interval_minutes()==1440`; con `2` → `5`; `_max_runs_per_day()` con `500` → `100`; con `0` → `1`; con valor no-int ("abc") → defaults 60/48.
- `test_busy_skip_sin_error`: `create_run` lanza `DbCompareBusyError` → 0 lanzados, `consecutive_errors` NO incrementa.
- `test_alias_borrado_deshabilita_watch`: `create_run` lanza `DbCompareRunError` → watch queda `enabled==False`.
- `test_harvest_done_resetea_backoff`: watch con `last_run_id` cuyo `get_run` devuelve `status=="done"` con summary → `consecutive_errors==0`, `last_done_run_id`, `last_harvested_run_id` y `last_summary` actualizados.
- `test_harvest_error_incrementa_backoff`: cosecha de run `status=="error"` → `consecutive_errors==1` y `last_harvested_run_id` == ese run.
- `test_harvest_error_es_idempotente` (KPI-4, fix C1): DOS invocaciones consecutivas de `run_watch_sweep_once()` (mismo `now`, mismo run en `error` sin run nuevo) → `consecutive_errors` queda en 1 (NO 2) y `_append_event_watch_error` fue llamado exactamente 1 vez (contarlo con monkeypatch contador).
- `test_harvest_stale_es_idempotente` (fix C1): mismo caso con run `status=="running"` + `stale==True` → 1 solo incremento, 1 solo evento.
- `test_run_activo_no_encima`: run del watch aún `running` no-stale → no lanza otro del mismo par.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_sweep.py -q` (y re-correr `tests/test_plan178_watch_store.py`; registrar el archivo nuevo en ambos runners).
**Criterio de aceptación:** 15 tests verdes; `git diff` de `dbcompare_runs.py` toca exactamente 2 zonas (firma + dict).
**Flag:** `STACKY_DB_COMPARE_RADAR_ENABLED` (gate interno del sweep) — default ON, pero sin watches el sweep es no-op (KPI-2).
**Runtimes:** idéntico en los 3. **Trabajo del operador:** ninguno (el vigía per-par sigue sin poder encenderse hasta F5/F7).

---

### F3 — DriftEvent v1: detección de transiciones y avisos locales persistidos

**Objetivo:** emitir y persistir eventos locales deduplicados cuando el drift aparece, empeora, se limpia o el watch falla.
**Valor:** el "aviso" del radar: el operador se entera sin mirar; HITL puro (registro local, jamás push externo).

**Archivo a editar:** `Stacky Agents/backend/services/dbcompare_watch.py` — reemplazar los stubs de F2:

```python
_EVENTS_CAP = 200
_EVENT_KINDS = ("drift_new", "drift_worse", "drift_cleared", "baseline_violation", "watch_error")


def _events_path() -> Path:
    return _watch_dir() / "events.json"


def list_events(limit: int = 50, *, unread_only: bool = False) -> list[dict]:
    path = _events_path()
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    events = list(doc.get("events") or [])
    if unread_only:
        events = [e for e in events if not e.get("read")]
    events.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return events[: max(0, min(int(limit), _EVENTS_CAP))]


def unread_count() -> int:
    return len(list_events(_EVENTS_CAP, unread_only=True))


def _append_event(kind: str, *, watch: dict | None, run_id: str | None, detail: dict) -> dict:
    if kind not in _EVENT_KINDS:
        # Fix C8: NO usar assert (desaparece bajo python -O).
        raise ValueError(f"DriftEvent kind desconocido: '{kind}'")
    now = _now()
    base_id = f"evt_{now:%Y%m%dT%H%M%SZ}_{(watch or {}).get('watch_id') or detail.get('alias') or 'global'}"
    with _IO_LOCK:
        events = list_events(_EVENTS_CAP)
        event_id, n = base_id, 1
        while any(e["event_id"] == event_id for e in events):
            n += 1
            event_id = f"{base_id}_{n}"
        event = {
            "event_id": event_id,
            "kind": kind,
            "watch_id": (watch or {}).get("watch_id"),
            "source_alias": (watch or {}).get("source_alias"),
            "target_alias": (watch or {}).get("target_alias"),
            "run_id": run_id,
            "created_at": _iso(now),
            "read": False,
            "detail": detail,
        }
        events.insert(0, event)
        _write_json_atomic(_events_path(), {"version": 1, "events": events[:_EVENTS_CAP]})
    return event


def mark_events_read(event_ids: list[str] | None = None) -> int:
    """event_ids=None => marcar TODOS. Retorna cuántos cambió."""
    with _IO_LOCK:
        events = list_events(_EVENTS_CAP)
        changed = 0
        for e in events:
            if not e.get("read") and (event_ids is None or e["event_id"] in event_ids):
                e["read"] = True
                changed += 1
        if changed:
            _write_json_atomic(_events_path(), {"version": 1, "events": events})
    return changed


def _items_count(summary: dict) -> int:
    sev = (summary or {}).get("by_severity") or {}
    return int(sev.get("info") or 0) + int(sev.get("warn") or 0) + int(sev.get("danger") or 0)


def _emit_transition_events(watch: dict, run: dict, new_summary: dict) -> None:
    prev = watch.get("last_summary")
    new_n = _items_count(new_summary)
    if prev is None:
        if new_n > 0:
            _append_event("drift_new", watch=watch, run_id=run["run_id"], detail=new_summary)
        return
    prev_n = _items_count(prev)
    prev_sev = prev.get("by_severity") or {}
    new_sev = new_summary.get("by_severity") or {}
    if prev_n == 0 and new_n > 0:
        _append_event("drift_new", watch=watch, run_id=run["run_id"], detail=new_summary)
    elif prev_n > 0 and new_n == 0:
        _append_event("drift_cleared", watch=watch, run_id=run["run_id"], detail=new_summary)
    elif int(new_sev.get("danger") or 0) > int(prev_sev.get("danger") or 0) or int(new_sev.get("warn") or 0) > int(prev_sev.get("warn") or 0):
        _append_event("drift_worse", watch=watch, run_id=run["run_id"], detail=new_summary)
    # info-only sube: silencio deliberado (anti-ruido).


def _append_event_watch_error(watch: dict, run: dict) -> None:
    _append_event(
        "watch_error", watch=watch, run_id=run.get("run_id"),
        detail={"error": (run.get("error") or "corrida stale/desconocida")[:300]},
    )
```

Semántica CERRADA de kinds (documentarla como comentario en el módulo):
- `drift_new`: primera cosecha con items>0, o transición 0→>0.
- `drift_worse`: sube `danger`, o sube `warn` (con items>0 antes y después). Subas solo de `info` NO emiten (anti-ruido).
- `drift_cleared`: transición >0→0 (paridad recuperada).
- `watch_error`: run del vigía terminó en error / quedó stale (`_STALE_AFTER_SEC=1800`, `dbcompare_runs.py:31`) / aliases inválidos (watch queda deshabilitado). Un run fallido emite este evento EXACTAMENTE una vez (cosecha idempotente por `last_harvested_run_id`, F2/fix C1).
- `baseline_violation`: la define F4.
- Dedup estructural: los eventos de transición SOLO se emiten en la cosecha de un run `done` nuevo (`last_harvested_run_id` cambia una única vez por run) — no hay re-emisión posible del mismo run (KPI-5).

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan178_events.py`:**
- `test_append_y_list_orden_desc`.
- `test_cap_200`: 205 appends → quedan 200, los más nuevos.
- `test_kind_desconocido_lanza_valueerror` (fix C8).
- `test_mark_read_ids_y_all`.
- `test_unread_count`.
- `test_dedup_transiciones` (KPI-5): watch sin `last_summary` + run done con 3 warns → 1 evento `drift_new`; simular segunda cosecha del MISMO run (`last_harvested_run_id` ya igual) → `_harvest_watch` retorna sin emitir; tercera corrida con summary idéntico → 0 eventos nuevos.
- `test_drift_worse_solo_danger_o_warn`: prev {1,1,0}→new {1,1,5} (solo info sube) = 0 eventos; new {1,2,1} = 1 `drift_worse`.
- `test_drift_cleared`.
- `test_watch_error_emite_evento`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_events.py -q` (+ re-correr sweep y store; registrar en runners).
**Criterio de aceptación:** 9 tests verdes; `events.json` capado; cero libs nuevas.
**Flag:** cubierta por el gate del sweep (F2). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — Baseline v1: pin de snapshot bendecido (autocontenido) y diff-contra-baseline sin conexión

**Objetivo:** pinnear un snapshot persistido como "baseline aprobado" de un ambiente — con copia local inmune a la retención del motor (fix C2) —, comparar cualquier estado contra él SIN abrir conexiones, y detectar violaciones en el sweep.
**Valor:** detecta drift respecto a un estado bendecido (release aprobada), no solo par-a-par.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_baseline.py`

```python
"""Plan 178 F4 — Baseline v1: snapshot pinneado como estado bendecido de un alias.

100% local: pin/unpin/diff operan sobre snapshots YA persistidos
(data_dir()/db_compare/snapshots/, services/dbcompare_snapshot.py:30).
NUNCA abre conexión a BD (KPI-6).

AUTOCONTENIDO (fix C2 / KPI-8): el motor poda snapshots con
_MAX_SNAPSHOTS_PER_ALIAS=20 (dbcompare_snapshot.py:31) y el vigía genera ~24
snapshots/día por alias vigilado ⇒ el snapshot original del baseline muere en
<1 día. Por eso pin_baseline COPIA el Snapshot v1 completo a
baselines/<alias>.snapshot.json y toda resolución cae a esa copia si el
original ya no existe. "broken" solo si faltan AMBOS.

NOTA de diseño (fix C7): este módulo duplica 3 helpers triviales
(_write_json_atomic/_now/_iso) en lugar de importarlos de dbcompare_watch:
8 líneas duplicadas valen más que acoplarse a privados de otro módulo.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

_BASELINES_DIRNAME = "db_compare/baselines"
BASELINE_VERSION = 1
_IO_LOCK = threading.Lock()


class DbCompareBaselineError(RuntimeError):
    """Pin inválido (snapshot inexistente o de otro alias)."""


def _baselines_dir() -> Path:
    d = data_dir() / _BASELINES_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _baseline_path(alias: str) -> Path:
    return _baselines_dir() / f"{alias}.json"


def _snapshot_copy_path(alias: str) -> Path:
    return _baselines_dir() / f"{alias}.snapshot.json"


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_baseline(alias: str) -> dict | None:
    path = _baseline_path(alias)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_baseline_snapshot(alias: str) -> dict | None:
    """Snapshot v1 del baseline del alias: primero el original del motor
    (load_snapshot), después la copia autocontenida. None si faltan ambos."""
    from services import dbcompare_snapshot
    baseline = get_baseline(alias)
    if baseline is None:
        return None
    snap = dbcompare_snapshot.load_snapshot(baseline.get("snapshot_id") or "")
    if snap is not None:
        return snap
    copy_path = _snapshot_copy_path(alias)
    if not copy_path.exists():
        return None
    try:
        return json.loads(copy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_baselines() -> list[dict]:
    out = []
    for path in sorted(_baselines_dir().glob("*.json")):
        if path.name.endswith(".snapshot.json"):
            continue  # las copias autocontenidas no son baselines
        b = get_baseline(path.stem)
        if b is not None:
            b = dict(b)
            b["broken"] = load_baseline_snapshot(b.get("alias") or path.stem) is None
            out.append(b)
    return out


def pin_baseline(alias: str, snapshot_id: str, *, note: str = "") -> dict:
    from services import dbcompare_snapshot
    snap = dbcompare_snapshot.load_snapshot(snapshot_id)
    if snap is None:
        raise DbCompareBaselineError(f"snapshot desconocido: '{snapshot_id}'")
    if snap.get("alias") != alias:
        raise DbCompareBaselineError(f"el snapshot '{snapshot_id}' no pertenece al ambiente '{alias}'")
    doc = {
        "version": BASELINE_VERSION,
        "alias": alias,
        "snapshot_id": snapshot_id,
        "pinned_at": _iso(_now()),
        "note": (note or "")[:200],
        "last_alerted_content_hash": None,
    }
    with _IO_LOCK:
        _write_json_atomic(_snapshot_copy_path(alias), snap)  # copia AUTOCONTENIDA (fix C2)
        _write_json_atomic(_baseline_path(alias), doc)
    return doc


def unpin_baseline(alias: str) -> bool:
    with _IO_LOCK:
        path = _baseline_path(alias)
        existed = path.exists()
        if existed:
            path.unlink()
        copy_path = _snapshot_copy_path(alias)
        if copy_path.exists():
            copy_path.unlink()
    return existed


def mark_alerted(alias: str, content_hash: str) -> None:
    """API pública para el dedup de baseline_violation (fix C7: el sweep NO
    toca privados de este módulo)."""
    with _IO_LOCK:
        baseline = get_baseline(alias)
        if baseline is None:
            return
        baseline["last_alerted_content_hash"] = content_hash
        _write_json_atomic(_baseline_path(alias), baseline)


def baseline_diff(alias: str) -> dict:
    """SchemaDiff v1 (reuso puro de diff_snapshots, services/dbcompare_diff.py:283)
    entre el baseline pinneado (ORIGEN, original o copia autocontenida) y el
    último snapshot persistido del alias (DESTINO). Efímero: NO se persiste
    como run. Sin conexiones (KPI-6)."""
    from services import dbcompare_diff, dbcompare_snapshot
    baseline = get_baseline(alias)
    if baseline is None:
        raise DbCompareBaselineError(f"'{alias}' no tiene baseline pinneado")
    base_snap = load_baseline_snapshot(alias)
    if base_snap is None:
        raise DbCompareBaselineError(f"el snapshot del baseline ya no existe (ni la copia): '{baseline['snapshot_id']}'")
    current = dbcompare_snapshot.latest_snapshot(alias)
    if current is None:
        raise DbCompareBaselineError(f"'{alias}' no tiene ningún snapshot; tomá uno primero")
    return dbcompare_diff.diff_snapshots(base_snap, current)
```

Y en `services/dbcompare_watch.py`, reemplazar el stub `_check_baselines_for_run` (SOLO API pública de `dbcompare_baseline` — fix C7):

```python
def _check_baselines_for_run(watch: dict, run: dict) -> None:
    """Tras cosechar un run done del vigía: si alguno de los 2 aliases tiene
    baseline pinneado, diffear el snapshot RECIÉN tomado (ya en disco) contra el
    baseline. Cero conexiones nuevas. Dedup por content_hash del snapshot."""
    from services import dbcompare_baseline, dbcompare_diff, dbcompare_snapshot
    for alias, snap_key in (
        (watch["source_alias"], "source_snapshot_id"),
        (watch["target_alias"], "target_snapshot_id"),
    ):
        baseline = dbcompare_baseline.get_baseline(alias)
        if baseline is None:
            continue
        fresh = dbcompare_snapshot.load_snapshot(run.get(snap_key) or "")
        base_snap = dbcompare_baseline.load_baseline_snapshot(alias)
        if fresh is None or base_snap is None:
            continue
        fresh_hash = fresh.get("content_hash")
        if fresh_hash == base_snap.get("content_hash"):
            continue  # idéntico al baseline: sin violación
        if fresh_hash == baseline.get("last_alerted_content_hash"):
            continue  # ya avisado por ESTE estado exacto (dedup)
        try:
            diff = dbcompare_diff.diff_snapshots(base_snap, fresh)
        except dbcompare_diff.DbCompareDiffError:
            continue
        if _items_count(diff.get("summary") or {}) == 0:
            continue
        _append_event(
            "baseline_violation", watch=watch, run_id=run["run_id"],
            detail={
                "alias": alias,
                "baseline_snapshot_id": baseline["snapshot_id"],
                "by_severity": (diff.get("summary") or {}).get("by_severity"),
                "parity_score": (diff.get("summary") or {}).get("parity_score"),
            },
        )
        dbcompare_baseline.mark_alerted(alias, fresh_hash)
```

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan178_baseline.py`:**
Fixtures: monkeypatch `data_dir` en `dbcompare_baseline`, `dbcompare_watch` Y `dbcompare_snapshot` hacia el mismo `tmp_path`; sembrar snapshots reales escribiendo JSONs Snapshot-v1 mínimos (`{"id","alias","engine","content_hash","schemas":{...}}`) en `tmp_path/db_compare/snapshots/<alias>/` — el formato lo lee `load_snapshot` (`dbcompare_snapshot.py:261`).
- `test_pin_ok_y_get`: además, existe `baselines/<alias>.snapshot.json` tras el pin (copia autocontenida).
- `test_pin_snapshot_inexistente_lanza`.
- `test_pin_snapshot_de_otro_alias_lanza`.
- `test_unpin_true_false`: unpin borra `<alias>.json` Y `<alias>.snapshot.json`.
- `test_list_baselines_marca_broken`: broken SOLO si faltan original y copia (borrar ambos a mano en el tmp).
- `test_list_baselines_ignora_copias`: con 1 baseline pinneado, `list_baselines()` retorna 1 entrada (no 2 — la copia `.snapshot.json` no cuenta como baseline).
- `test_baseline_sobrevive_prune_de_snapshots` (KPI-8, fix C2): pin → borrar el snapshot original de `snapshots/<alias>/` (simula `prune_snapshots`) → `baseline_diff(alias)` sigue devolviendo un SchemaDiff válido desde la copia y `list_baselines()[0]["broken"] is False`.
- `test_baseline_diff_reusa_schema_diff_v1` (KPI-6): siembra baseline y latest con 1 tabla de diferencia → el retorno tiene `version` == DIFF_VERSION del motor, `items` no vacío y `summary.by_severity`; centinela sobre `take_snapshot` garantiza cero conexión.
- `test_baseline_diff_sin_baseline_lanza` / `test_sin_snapshots_lanza`.
- `test_violacion_emite_evento_y_dedup_por_hash`: primera cosecha con hash distinto → 1 `baseline_violation` y `last_alerted_content_hash` actualizado (vía `mark_alerted`); segunda cosecha con el MISMO hash → 0 eventos.
- `test_mark_alerted_sin_baseline_no_crashea` (fix C7): `mark_alerted("NOPE", "h")` retorna sin error.
- `test_snapshot_igual_al_baseline_no_emite`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_baseline.py -q` (+ registrar en runners).
**Criterio de aceptación:** 13 tests verdes; grep en `dbcompare_baseline.py` sin imports de conexión NI imports de `dbcompare_watch` (fix C7).
**Flag:** gate en la API (F5); el servicio es inerte sin llamadores. **Runtimes:** idéntico. **Trabajo del operador:** pinnear es opcional (1 click cuando quiera bendecir un estado).

---

### F5 — API: blueprint nuevo `db_compare_watch` (watches, eventos, baselines, radar)

**Objetivo:** exponer todo por HTTP bajo `/api/db-compare/...` en un blueprint NUEVO (cero colisión con `api/db_compare.py`).
**Valor:** la UI (F7) y cualquier automatización local consumen el radar por API.

**Archivo a crear:** `Stacky Agents/backend/api/db_compare_watch.py`

```python
"""Plan 178 — API del radar de ambientes. Blueprint SEPARADO de api/db_compare.py
para minimizar colisión de merge con el plan 176 (que edita ese archivo).

Gate doble: master 122 + radar 178. OFF (cualquiera) => 403 en TODO (este
blueprint no tiene /health propio; el health del comparador ya existe)."""
from flask import Blueprint, jsonify, request

import config as _config
from services import dbcompare_baseline, dbcompare_registry, dbcompare_runs, dbcompare_watch

bp = Blueprint("db_compare_watch", __name__, url_prefix="/db-compare")


def _require_radar_enabled():
    # Idioma de api/db_compare.py:27-29 — la instancia de flags es config.config,
    # NO el módulo (gotcha conocido: getattr(config, FLAG) da default y mata el OFF).
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_RADAR_ENABLED", False):
        return jsonify({"ok": False, "error": "Radar de ambientes deshabilitado (STACKY_DB_COMPARE_RADAR_ENABLED)."}), 403
    return None
```

Rutas EXACTAS (todas arrancan con `gate = _require_radar_enabled(); if gate is not None: return gate`):

| Método y ruta | Función | Comportamiento |
|---|---|---|
| `GET /watches` | `list_watches_route` | `{"ok": true, "watches": dbcompare_watch.list_watches()}` |
| `POST /watches` | `upsert_watch_route` | body validado (pseudocódigo abajo, fix C6); 400 ante body inválido o `DbCompareWatchError`; 200 `{"ok":true,"watch":...}` |
| `DELETE /watches/<watch_id>` | `delete_watch_route` | 404 si no existía; 200 `{"ok":true}` |
| `GET /watch/events?limit=50&unread_only=false` | `list_events_route` | `{"ok":true,"events":[...],"unread_count":N}` (limit cap 200) |
| `POST /watch/events/mark-read` | `mark_events_read_route` | body validado (pseudocódigo abajo, fix C6); 200 `{"ok":true,"changed":N}` |
| `GET /baselines` | `list_baselines_route` | `{"ok":true,"baselines":[...]}` |
| `POST /environments/<alias>/baseline` | `pin_baseline_route` | body `{"snapshot_id","note"?}` — 400 si falta `snapshot_id` (fix C6); 400 ante `DbCompareBaselineError`; 200 `{"ok":true,"baseline":...}` |
| `DELETE /environments/<alias>/baseline` | `unpin_baseline_route` | 404 si no había; 200 `{"ok":true}` |
| `GET /baseline-diff/<alias>` | `baseline_diff_route` | 200 `{"ok":true,"diff":<SchemaDiff v1>}`; 400 ante `DbCompareBaselineError` |
| `GET /radar` | `radar_route` | ver payload abajo |

Parsing defensivo de bodies (fix C6 — pseudocódigo NORMATIVO para las rutas POST):

```python
@bp.post("/watches")
def upsert_watch_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    source = str(data.get("source_alias") or "").strip()
    target = str(data.get("target_alias") or "").strip()
    if not source or not target:
        return jsonify({"ok": False, "error": "source_alias y target_alias son obligatorios"}), 400
    try:
        watch = dbcompare_watch.upsert_watch(source, target, enabled=bool(data.get("enabled", True)))
    except dbcompare_watch.DbCompareWatchError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "watch": watch})


@bp.post("/watch/events/mark-read")
def mark_events_read_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    data = request.get_json(silent=True) or {}
    if data.get("all"):
        changed = dbcompare_watch.mark_events_read(None)
    else:
        ids = data.get("event_ids")
        if not isinstance(ids, list) or not ids:
            return jsonify({"ok": False, "error": "event_ids (lista no vacía) o all=true"}), 400
        changed = dbcompare_watch.mark_events_read([str(i) for i in ids])
    return jsonify({"ok": True, "changed": changed})
```

(`pin_baseline_route` sigue el mismo idioma: `data = request.get_json(silent=True) or {}`; `snapshot_id = str(data.get("snapshot_id") or "").strip()`; si vacío → 400.)

`radar_route` — computado 100% de datos locales (NUNCA abre conexiones; NO llama `take_snapshot`):

```python
@bp.get("/radar")
def radar_route():
    gate = _require_radar_enabled()
    if gate is not None:
        return gate
    environments = dbcompare_registry.list_environments()
    watches = {w["watch_id"]: w for w in dbcompare_watch.list_watches()}
    baselines = {b["alias"]: b for b in dbcompare_baseline.list_baselines()}
    latest_by_pair: dict[str, dict] = {}
    for meta in dbcompare_runs.list_runs(200):
        if meta.get("status") != "done" or not meta.get("summary"):
            continue
        key = f"{meta['source_alias']}__{meta['target_alias']}"
        if key not in latest_by_pair or (meta.get("finished_at") or "") > (latest_by_pair[key].get("finished_at") or ""):
            latest_by_pair[key] = meta
    cells = []
    for key, meta in latest_by_pair.items():
        sev = (meta["summary"] or {}).get("by_severity") or {}
        state = "green"
        if int(sev.get("danger") or 0) > 0:
            state = "red"
        elif int(sev.get("warn") or 0) + int(sev.get("info") or 0) > 0:
            state = "amber"
        cells.append({
            "source_alias": meta["source_alias"], "target_alias": meta["target_alias"],
            "state": state, "by_severity": sev,
            "parity_score": (meta["summary"] or {}).get("parity_score"),
            "run_id": meta["run_id"], "finished_at": meta.get("finished_at"),
            "initiated_by": meta.get("initiated_by", "operator"),
            "watched": key in watches and watches[key].get("enabled", False),
        })
    return jsonify({
        "ok": True,
        "environments": [{"alias": e["alias"], "engine": e["engine"], "has_baseline": e["alias"] in baselines} for e in environments],
        "cells": cells,          # pares SIN celda => estado "gray" (sin datos) en la UI
        "watches": list(watches.values()),
        "unread_events": dbcompare_watch.unread_count(),
    })
```

**Registro del blueprint:** `Stacky Agents/backend/api/__init__.py` — 2 líneas, copiando el idioma de `:57` y `:118`:
```python
from .db_compare_watch import bp as db_compare_watch_bp  # Plan 178 — radar de ambientes
...
api_bp.register_blueprint(db_compare_watch_bp)  # Plan 178 — url_prefix="/db-compare" → /api/db-compare/watches|radar|baselines...
```
(Flask admite dos blueprints con el mismo `url_prefix` y nombres distintos; las rutas no se pisan — verificado contra la tabla de rutas existentes `api/db_compare.py:52-411`, ninguna coincide con las nuevas.)

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan178_api.py`:**
Cliente Flask con el patrón de los tests de API existentes del comparador (buscar `test_dbcompare*` en `backend/tests/` y copiar su fixture de app/client; monkeypatch `data_dir` → `tmp_path`).
- `test_403_master_off` (KPI-1): con `STACKY_DB_COMPARE_ENABLED=False` en `config.config`, TODAS las rutas nuevas devuelven 403.
- `test_403_radar_off` (KPI-1): master ON + radar OFF → 403.
- `test_watch_crud_por_api`: POST → GET → DELETE feliz.
- `test_watch_post_body_invalido_400` (fix C6): POST sin body, POST `{}` y POST con `source_alias` vacío → 400 con `{"ok": false}` (no 500).
- `test_watch_post_alias_invalido_400`.
- `test_events_list_y_mark_read`: incluye POST mark-read `{}` → 400 (fix C6).
- `test_baseline_pin_diff_unpin`: siembra snapshots en tmp, pin por API, GET baseline-diff devuelve `diff.version` y `summary`, unpin. POST baseline sin `snapshot_id` → 400 (fix C6).
- `test_radar_shape`: siembra 1 run done + 1 watch → el payload tiene `environments`, `cells[0].state` correcto (`red` si danger>0), `watches`, `unread_events`.
- `test_radar_no_abre_conexiones`: centinela `take_snapshot` → nunca llamado por GET /radar.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_api.py -q` (+ registrar en runners).
**Criterio de aceptación:** 9 tests verdes; `api/db_compare.py` intacto (`git diff --stat` no lo lista).
**Flag:** doble gate 122+178 en cada ruta. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F6 — Loop de background del vigía en `app.py` (patrón plan 117, apagado bajo pytest)

**Objetivo:** un thread daemon que invoca `run_watch_sweep_once()` cada 60 s, con arranque inofensivo y hot-apply de flags.
**Valor:** el vigía pasa de invocable a AUTOMÁTICO — el radar late solo.

**Archivo a editar:** `Stacky Agents/backend/app.py` — insertar un bloque NUEVO inmediatamente DESPUÉS del bloque del plan 60 (después de la línea `logger.info("ado edit learning daemon armed (interval=%ds)", _ado_edit_seconds)`, hoy `:553`) y ANTES del comentario `# ── Structured logging middleware ──` (`:555`):

```python
    # ── Plan 178 — Vigía de drift del comparador de BD (radar de ambientes) ──
    # Mismo patrón que el sweep del plan 117 (app.py:463-491): el thread arranca
    # siempre en producción y los gates (flags + watches habilitados) se evalúan
    # en CADA iteración dentro de run_watch_sweep_once() → hot-apply real, sin
    # restart_required. Bajo pytest NO arranca (guard idéntico al del 117).
    # Costo con radar ON sin pares vigilados: ~0 (lee un JSON local y duerme).
    # El vigía JAMÁS escribe en BD: solo create_run() del motor 122/123 (SELECTs
    # de metadata de esquema). El data-diff (126) queda excluido por diseño.
    if "pytest" not in _sys.modules:
        def _dbcompare_watch_sweep_loop() -> None:
            from services import dbcompare_watch

            while True:
                try:
                    launched = dbcompare_watch.run_watch_sweep_once()
                    if launched:
                        logger.info("dbcompare watch sweep: %d corridas lanzadas", launched)
                except Exception:
                    logger.exception("dbcompare watch sweep daemon falló")
                time.sleep(60)

        threading.Thread(
            target=_dbcompare_watch_sweep_loop,
            name="stacky-dbcompare-watch-daemon",
            daemon=True,
        ).start()
        logger.info("dbcompare watch daemon armed")
```

Notas duras:
- `_sys` YA está importado en `create_app` (`app.py:468` `import sys as _sys`) y queda en scope; NO re-importar.
- El tick de 60 s es SOLO la cadencia de chequeo (leer `watches.json` + comparar timestamps); el intervalo real de corridas es la flag (F0) leída DENTRO del sweep — cambiarla por UI aplica sin reinicio.
- Si la BD del cliente no responde, `create_run` termina el run en `status="error"` en SU thread; el loop del vigía nunca muere por eso (`try/except` + backoff). El arranque de la app JAMÁS depende del vigía.

**Tests PRIMERO — agregar a `tests/test_plan178_sweep.py`:**
- `test_loop_no_arranca_bajo_pytest`: tras `create_app()` (o el fixture de app existente), `[t.name for t in threading.enumerate()]` NO contiene `"stacky-dbcompare-watch-daemon"`.
- `test_sweep_seguro_ante_excepcion`: monkeypatch `list_watches` para lanzar `RuntimeError` → `run_watch_sweep_once()` propaga la excepción (el loop la traga con `logger.exception`, mismo contrato que los sweeps 117/121) — el test documenta el reparto de responsabilidades: el sweep puede lanzar, el LOOP nunca muere.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan178_sweep.py -q`
**Criterio de aceptación:** ambos tests verdes; grep en `app.py` de `stacky-dbcompare-watch-daemon` da exactamente 1 hit dentro de un bloque con guard `if "pytest" not in _sys.modules:`.
**Flag:** `STACKY_DB_COMPARE_RADAR_ENABLED` evaluada en cada tick (hot-apply). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F7 — Frontend: radar N×N, vigilar con 1 click, sparkline de tendencia, eventos y baseline

**Objetivo:** la UI del radar dentro de la página DB Compare existente, con punto de montaje mínimo y cero UI nueva si la flag está OFF.
**Valor:** visión de conjunto instantánea: "¿qué ambientes driftearon y desde cuándo?" en un vistazo, con onboarding casi nulo (usa los ambientes YA registrados; aparece sola con los runs existentes).

**Archivos a crear:**

1. `Stacky Agents/frontend/src/components/dbcompare/radarTypes.ts` — tipos del payload de F5 (`RadarPayload`, `RadarCell`, `WatchEntry`, `DriftEvent`, `BaselineEntry`), espejando EXACTAMENTE las claves del backend. NO editar `dbcompareTypes.ts` (lo toca el 176).

2. `Stacky Agents/frontend/src/components/dbcompare/radarLogic.ts` — SOLO funciones puras (testeables con vitest):
   - `pairKey(a: string, b: string): string` — ordenada, para agrupar tendencia en cualquier dirección (misma semántica que `runHistory.ts:13-15`; se REDEFINE local porque allá no está exportada — no tocar `runHistory.ts`).
   - `buildMatrix(environments: {alias: string}[], cells: RadarCell[]): (RadarCell | null)[][]` — matriz N×N indexada [fila=origen][columna=destino], `null` = sin datos (gris), diagonal = `null`.
   - `cellStateClass(cell: RadarCell | null): "green" | "amber" | "red" | "gray"`.
   - `trendSeries(runs: CompareRun[], sourceAlias: string, targetAlias: string): {t: string; danger: number; warn: number; info: number}[]` — filtra runs `done` del par (cualquier orden de alias), ordena por `finished_at` ascendente, mapea `summary.by_severity`.
   - `sparklinePath(points: {danger: number; warn: number}[], width: number, height: number): string` — path SVG de la serie `danger+warn` normalizada (línea simple; reusar helpers de `svgMath.ts` SOLO si alguno aplica — los existentes son de arcos/gauge (`svgMath.ts:13-46`), así que el path lineal se implementa acá).
   - `relativeFromIso(iso: string, nowMs: number): string` — **(v2, elimina la vaguedad "verificar relativeTime.ts")** helper local determinista: `""` si el ISO no parsea; "hace <1 min" / `hace N min` / `hace N h` / `hace N d` según la distancia a `nowMs` (recibe el reloj como argumento para testearlo sin mocks).
   - `formatCellTitle(cell: RadarCell, nowMs: number): string` — tooltip: "DEV → TEST · paridad 98.5 · 2 warn · hace ..." usando `relativeFromIso`.

3. `Stacky Agents/frontend/src/components/dbcompare/EnvironmentRadar.tsx` — componente autocontenido:
   - Al montar: `DbCompareWatch.radar()`. Si la promesa RECHAZA (403 flag OFF / red / master OFF) → `return null` (patrón `health→null` de `DbComparePage.tsx:41-45`). KPI-1: cero UI con flag OFF.
   - **[ADICIÓN ARQUITECTO] Auto-refresh (fix C12):** además del fetch inicial, un `useEffect` monta `const id = window.setInterval(refetch, 60_000)` y lo limpia en unmount (`return () => window.clearInterval(id)`). Si CUALQUIER refetch rechaza → `setPayload(null)` y `clearInterval` inmediato (con flag OFF no se sigue pooleando; al remontar la página se reintenta una vez). Costo: 1 request/min SOLO mientras la página DB Compare está visible — el badge de eventos y las celdas quedan vivos sin recargar.
   - Render: encabezado de sección "Radar de ambientes (esquema)" + matriz N×N (`buildMatrix`): filas=origen, columnas=destino, celda con color de estado por clase CSS (tokens `--dbc-danger`/`--dbc-warn`/`--dbc-unchanged` y gris neutro), timestamp relativo de la última corrida (`relativeFromIso`) e ícono 👁 si `watched`.
   - **Con <2 ambientes registrados o (0 celdas y 0 watches)** (fix C13): la sección se colapsa a una sola línea con el hint "El radar aparece cuando hay al menos 2 ambientes registrados y una corrida hecha." — sin matriz vacía gigante.
   - Click en celda con datos → `props.onOpenRun(run_id)` (deep-link al run; el adapter de tipos lo define el punto 6).
   - Botón por celda "Vigilar" / "Dejar de vigilar" → `DbCompareWatch.upsertWatch({source_alias, target_alias, enabled: !watched})` + refresh del radar. UN click = aprobación humana explícita (§3.2).
   - Celda seleccionada → mini-panel con sparkline (`trendSeries` sobre `props.runs` — los runs YA cargados por el padre con `listRuns(20)`, `DbComparePage.tsx:52-56`; cero fetch extra) + botón del run.
   - Fila de encabezado por ambiente: ícono 📌 si `has_baseline`; click → pin/unpin: si no hay baseline, lista `DbCompare.listSnapshots(alias)` (endpoint existente, `endpoints.ts:4012`) en un `<select>` y `DbCompareWatch.pinBaseline(alias, snapshot_id)`; si hay, botones "Ver drift vs baseline" (`DbCompareWatch.baselineDiff(alias)` → counts por severidad en el panel) y "Despinnear".
   - Badge de eventos sin leer (`unread_events`) en el encabezado de la sección + toggle del panel de eventos.
   - PROHIBIDO `style={{...}}`: todo por clases del module.css; el sparkline usa atributos SVG (`d`, `viewBox`), que NO son style.

4. `Stacky Agents/frontend/src/components/dbcompare/DriftEventsPanel.tsx` — lista de `DriftEvent` (`DbCompareWatch.listEvents(50)`): ícono por kind (`drift_new` ⚠, `drift_worse` 🔺, `drift_cleared` ✅, `baseline_violation` 📌, `watch_error` ⛔), par, tiempo relativo (`relativeFromIso`), counts; click → `onOpenRun(run_id)` si tiene run; botón "Marcar todo leído" → `markEventsRead({all: true})`. Fallback primario de avisos del plan (§2bis punto 3): vive DENTRO de la página DB Compare; la integración con el Centro de Notificaciones del 152 es condicional y NO se implementa si el 152 no existe.

**Archivos a editar (mínimos):**

5. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar AL FINAL del archivo (después del objeto `DbCompare`, que empieza en `:3967`; NO tocarlo) el objeto NUEVO. `api.delete` EXISTE en este archivo (usado por `DbCompare.deleteEnvironment` `:3989-3992` y `clearPassword` `:3998-4001`) — usarlo directo:
   ```typescript
   // Plan 178 — Radar de ambientes (vigía de drift + matriz + baseline + eventos).
   export const DbCompareWatch = {
     radar: () => api.get<RadarPayload>("/api/db-compare/radar"),
     listWatches: () => api.get<{ ok: boolean; watches: WatchEntry[] }>("/api/db-compare/watches"),
     upsertWatch: (body: { source_alias: string; target_alias: string; enabled: boolean }) =>
       api.post<{ ok: boolean; watch: WatchEntry }>("/api/db-compare/watches", body),
     deleteWatch: (watchId: string) =>
       api.delete<{ ok: boolean }>(`/api/db-compare/watches/${encodeURIComponent(watchId)}`),
     listEvents: (limit = 50) =>
       api.get<{ ok: boolean; events: DriftEvent[]; unread_count: number }>(
         `/api/db-compare/watch/events?limit=${limit}`,
       ),
     markEventsRead: (body: { event_ids?: string[]; all?: boolean }) =>
       api.post<{ ok: boolean; changed: number }>("/api/db-compare/watch/events/mark-read", body),
     listBaselines: () => api.get<{ ok: boolean; baselines: BaselineEntry[] }>("/api/db-compare/baselines"),
     pinBaseline: (alias: string, snapshotId: string, note = "") =>
       api.post<{ ok: boolean; baseline: BaselineEntry }>(
         `/api/db-compare/environments/${encodeURIComponent(alias)}/baseline`,
         { snapshot_id: snapshotId, note },
       ),
     unpinBaseline: (alias: string) =>
       api.delete<{ ok: boolean }>(`/api/db-compare/environments/${encodeURIComponent(alias)}/baseline`),
     baselineDiff: (alias: string) =>
       api.get<{ ok: boolean; diff: NonNullable<CompareRun["diff"]> }>(
         `/api/db-compare/baseline-diff/${encodeURIComponent(alias)}`,
       ),
   };
   ```
   (imports de tipos: `RadarPayload`/`WatchEntry`/`DriftEvent`/`BaselineEntry` desde `../components/dbcompare/radarTypes`; el tipo del diff NO se adivina por nombre — se referencia como `NonNullable<CompareRun["diff"]>` importando `CompareRun` desde `../components/dbcompare/dbcompareTypes`, que ya lo exporta — es el tipo que usa `DbComparePage.tsx:32`.)

6. `Stacky Agents/frontend/src/components/dbcompare/DbComparePage.tsx` — EXACTAMENTE 2 ediciones:
   - 1 import: `import { EnvironmentRadar } from "./EnvironmentRadar";`
   - 1 elemento JSX, colocado inmediatamente ANTES del bloque del wizard dentro del render (después del header de la página). JSX EXACTO (fix C4 — `handleSelectHistoricalRun` recibe `CompareRun`, no un string (`DbComparePage.tsx:93`); el adapter inline castea el id al shape mínimo que esa función usa, que es solo `run.run_id` en `:95`; `CompareRun` ya está importado en la página):
     ```tsx
     <EnvironmentRadar
       environments={environments}
       runs={runs}
       onOpenRun={(runId: string) => { void handleSelectHistoricalRun({ run_id: runId } as CompareRun); }}
       onChanged={reloadRuns}
     />
     ```
   - Nada más: sin estado nuevo, sin efectos nuevos en la página.

7. `Stacky Agents/frontend/src/components/dbcompare/dbcompare.module.css` — agregar AL FINAL las clases nuevas (`.radarSection`, `.radarGrid`, `.radarCell`, `.radarCellGreen|Amber|Red|Gray`, `.radarSparkline`, `.eventsPanel`, `.eventRow`, `.unreadBadge`, `.baselinePin`, `.radarHint`) usando EXCLUSIVAMENTE `var(--dbc-danger)`, `var(--dbc-warn)`, `var(--dbc-info)`, `var(--dbc-unchanged)` y tokens globales del theme existente. Sin hex hardcodeado nuevo.

**Tests PRIMERO — `Stacky Agents/frontend/src/components/dbcompare/radarLogic.test.ts`:**
(vitest por archivo; sin RTL/jsdom — solo lógica pura)
- `buildMatrix`: 3 ambientes + 2 cells → matriz 3×3 con diagonal null y celdas en la posición [origen][destino] correcta.
- `cellStateClass`: danger>0→"red"; warn>0→"amber"; todo 0→"green"; null→"gray".
- `trendSeries`: filtra el par en ambas direcciones, ordena ascendente, ignora runs no-done.
- `sparklinePath`: 0 puntos → ""; 1 punto → path válido; serie conocida → path determinista (snapshot literal del string).
- `relativeFromIso` (v2): ISO inválido → ""; nowMs fijo → "hace <1 min" / "hace 5 min" / "hace 3 h" / "hace 2 d" para deltas conocidos (determinista, sin mocks de Date).
- `formatCellTitle`: contiene alias y parity (con nowMs fijo).

**Comandos:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/radarLogic.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio de aceptación (binario):** vitest del archivo verde + `tsc --noEmit` limpio + grep `style={{` en los `.tsx` nuevos = 0 hits + `git diff` de `DbComparePage.tsx` muestra exactamente 2 hunks (import + JSX).
**Flag:** el componente se auto-oculta si `/radar` responde 403 (KPI-1) — el frontend no lee flags.
**Runtimes:** idéntico en los 3 (panel). **Trabajo del operador:** ninguno para ver el radar (aparece solo con datos existentes); **opt-in de 1 click por par** para el vigía (excepción dura 3, §3.2); pin de baseline opcional.

---

### F8 — Compatibilidad, cierre y verificación integral

**Objetivo:** demostrar que con flags OFF nada cambió, que todo lo nuevo está registrado, y dejar el smoke manual documentado.
**Valor:** KPI-1 sellado y DoD verificable por cualquiera.

**Acciones:**
1. Verificar registro completo en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20` + espejo `.ps1`): `tests/test_plan178_flags.py`, `test_plan178_watch_store.py`, `test_plan178_sweep.py`, `test_plan178_events.py`, `test_plan178_baseline.py`, `test_plan178_api.py` (6 archivos).
2. Correr POR ARCHIVO los 6 nuevos + los preexistentes del área: `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`, y los `tests/test_dbcompare_*.py` existentes (por el kwarg aditivo de `create_run`) — todos con `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/<archivo> -q`.
3. `cd "Stacky Agents/frontend" && npx tsc --noEmit` limpio.
4. Smoke manual documentado (NO automatizable sin BD real; queda como checklist en el PR):
   - Levantar el dashboard con 2 ambientes registrados → la sección "Radar de ambientes" aparece con celdas de los runs históricos (o el hint colapsado si no hay datos).
   - Click "Vigilar" en un par → `watches.json` aparece en `data\db_compare\watch\`; bajar `STACKY_DB_COMPARE_WATCH_INTERVAL_MIN` a 5 por UI; en ≤6 min hay un run nuevo con `initiated_by=="watch"` en la timeline.
   - Provocar un cambio de esquema en el ambiente de prueba → al siguiente tick aparece 1 evento `drift_new` y el badge de no-leídos (que se actualiza solo por el auto-refresh de 60 s, sin recargar).
   - Forzar un error (apagar la BD de prueba o revocar la credencial) → 1 solo evento `watch_error` por corrida fallida (NO uno por minuto — verificación manual del fix C1).
   - Apagar `STACKY_DB_COMPARE_RADAR_ENABLED` por UI → la sección desaparece en el próximo tick del auto-refresh y el sweep deja de lanzar (sin reinicio).
5. **Smoke de deploy congelado (fix C11):** build PyInstaller + arrancar el .exe empaquetado → el log muestra `dbcompare watch daemon armed` y `GET /api/db-compare/radar` responde (200 con flag ON; 403 con flag OFF). Los módulos nuevos entran al bundle por la cadena de imports estáticos `app.py → api/__init__.py → api/db_compare_watch.py → services/dbcompare_watch|dbcompare_baseline` (los `import` dentro de funciones también los ve el análisis de PyInstaller). Gotcha conocido del repo: si el smoke tira `ModuleNotFoundError` en un submódulo nuevo, suele ser un SyntaxError REAL en ese archivo, no un problema de collect-submodules.
6. Confirmar `git diff --stat` global: `api/db_compare.py`, `SummaryHero.tsx`, `dbcompareTypes.ts`, `runHistory.ts` NO aparecen (promesa §2bis).

**Criterio de aceptación:** checklist 1-3 y 6 binarios verdes; smokes 4-5 documentados en el PR con resultados.
**Trabajo del operador:** ninguno obligatorio (el smoke lo hace quien implementa).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Colisión de merge con el 176 (toca `DbComparePage.tsx`, `endpoints.ts`, `dbcompare.module.css` **y `services/dbcompare_runs.py::create_run` — colisión de FIRMA conocida, fix C3**) | Conflictos o duplicado silencioso al mergear | Módulos/archivos NUEVOS + 2 hunks mínimos en `DbComparePage.tsx` + objeto nuevo al FINAL de `endpoints.ts`; para `create_run`: ambos planes agregan kwargs keyword-only aditivos ORTOGONALES — quien mergea segundo los combina en la única firma y re-corre los tests de ambos planes (§2bis). Tras merge: `npx tsc --noEmit` + grep `DbCompareWatch` = 1 declaración |
| R2 | El vigía conecta a BD sin pedido del operador | Sorpresa/carga en BD del cliente | Watch per-par nace OFF; solo el click "Vigilar" lo enciende (excepción dura 3, §3.2); presupuesto diario + backoff + skip por lock + kill-switch por flag con hot-apply |
| R3 | Runs del vigía inflan la retención y desplazan runs manuales (`_MAX_RUNS_KEPT=100`, `dbcompare_runs.py:32`, compartido) | Con el default 48/día, el vigía ocupa los 100 slots en ~2,1 días: el histórico MANUAL desaparece de la timeline y la tendencia por par queda acotada a ~2 días (fix C5: análisis honesto) | Aceptado y declarado: la tendencia se rotula "últimas corridas retenidas"; el presupuesto es configurable por UI (bajarlo alarga el histórico); `max_value=100` alineado con la retención para que el cap sea siempre contable; si en la práctica molesta, subir `_MAX_RUNS_KEPT` es un cambio de 1 constante FUERA de este plan |
| R4 | Ambiente borrado con watch activo | Corridas fallando para siempre | `DbCompareRunError` en el sweep ⇒ watch `enabled=False` + evento `watch_error` (F2/F3) |
| R5 | `events.json`/`watches.json` corruptos (corte de luz) | Radar sin avisos | Escritura atómica tmp+`os.replace` (§3.3); lectura defensiva devuelve `[]` y el sistema se recompone en el próximo tick |
| R6 | Reloj/DST del host | Dues corridos | TODO en UTC (`_now()` con `timezone.utc`, formato `%Y-%m-%dT%H:%M:%SZ`, presupuesto por día calendario UTC) |
| R7 | Dos ticks concurrentes (no debería: 1 solo thread) | Doble lanzamiento | El lock del motor por par (`_ACTIVE_LOCK`, `dbcompare_runs.py:145-150`) hace el segundo `create_run` `Busy` ⇒ skip; además `_IO_LOCK` serializa la persistencia del watch |
| R8 | Sesión paralela ocupa el número 178 antes del commit | Colisión de numeración (ya pasó con 171) | El número se recalculó listando `docs/` inmediatamente antes de escribir; si al commitear existe otro 178, renumerar el archivo completo al primer libre ANTES de commitear |
| R9 | El operador espera que el vigía compare DATOS | Falsa sensación de cobertura | La UI del radar dice "esquema" explícito en el encabezado de la sección y este doc lo declara en §3.1; la paridad de datos sigue siendo manual (126) |
| R10 | **(v2)** El snapshot pinneado es borrado por `prune_snapshots` (`_MAX_SNAPSHOTS_PER_ALIAS=20`, `dbcompare_snapshot.py:31`) — CERTEZA en <1 día con vigía activo, no caso raro | Baseline roto / violaciones nunca detectadas | Neutralizado por la copia autocontenida de F4 (fix C2, KPI-8): la resolución cae a `baselines/<alias>.snapshot.json`; `broken` solo si faltan ambos |
| R11 | **(v2)** Run fallido re-cosechado cada tick (bug v1) | Backoff degenerado + `events.json` inundado (cap 200 lleno de `watch_error` en ~3,3 h) | Eliminado por `last_harvested_run_id` (fix C1, KPI-4): cosecha idempotente por run; tests `test_harvest_error_es_idempotente` y `test_harvest_stale_es_idempotente` |

---

## 7. Fuera de scope (diferidos explícitos de este plan)

- **Corrida multi-ambiente real** (un diff de 3+ ambientes en una operación): sigue diferido; la matriz N×N cubre la necesidad de visión de conjunto con corridas par-a-par.
- **Notificaciones externas** (email, webhook saliente, push, tickets automáticos): PROHIBIDAS por doctrina, no diferidas — no se harán en ninguna capa.
- **Vigía de DATOS** (re-correr data-diff programado): excluido por PII y costo (§3.1); si algún día se considera, requiere su propio plan con masking.
- **Comparación contra baseline de OTRO ambiente** (p.ej. TEST vs baseline de PROD): técnicamente trivial (mismo `diff_snapshots`) pero se difiere para no ensanchar la UI v1 del radar.
- **Auto-retención diferenciada** de runs del vigía (borrar los `initiated_by=="watch"` antes que los manuales): diferido; hoy manda `_MAX_RUNS_KEPT` (R3 documenta el costo real).
- **Integración con el Centro de Notificaciones (152)**: condicional (§2bis); si el 152 no está implementado al momento de construir esto, NO se crea nada.
- Scheduling con cron por par / calendarios de ventana horaria: diferido (una sola cadencia global por flag alcanza para v1).
- Snapshot v2, masking PII, MERGE statements, mapeo a scripts ticketeados: siguen diferidos como en 176 §6.

---

## 8. Glosario, orden de implementación y DoD global

### Glosario
- **Radar**: la vista matriz N×N + tendencia + eventos + baselines (F5/F7).
- **Vigía**: el scheduler read-only que re-corre snapshot+diff de pares vigilados (F2/F6).
- **Watch**: la configuración persistida de un par vigilado (Watch v1, F1).
- **DriftEvent**: aviso local persistido de una transición de drift (DriftEvent v1, F3).
- **Baseline**: snapshot pinneado como estado bendecido de un ambiente, con copia autocontenida (Baseline v1, F4).
- **Cosecha (harvest)**: leer en el tick N+1 el resultado del run lanzado en el tick N (patrón de dos tiempos, F2). Idempotente por run vía `last_harvested_run_id` (v2).
- **Transición**: cambio entre el `last_summary` cosechado anterior y el nuevo (define qué evento se emite, F3).

### Orden de implementación (estricto)
F0 (flags) → F1 (store) → F2 (sweep) → F3 (eventos) → F4 (baseline) → F5 (API) → F6 (loop) → F7 (UI) → F8 (cierre). F3 y F4 podrían permutarse entre sí; nada más puede reordenarse. Cada fase termina con sus tests verdes ANTES de empezar la siguiente (TDD: escribir los tests de la fase primero, verlos fallar por la razón correcta, implementar, verlos pasar).

### Definition of Done global
1. Los 8 KPIs de §1.3 verificados con sus tests/comandos (incluye KPI-8 baseline autocontenido).
2. Los 6 archivos `tests/test_plan178_*.py` verdes POR ARCHIVO y registrados en ambos runners (`run_harness_tests.sh:20` + `.ps1`).
3. `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py` y los `tests/test_dbcompare_*.py` preexistentes verdes (sin regresión del kwarg aditivo).
4. `npx tsc --noEmit` limpio; vitest de `radarLogic.test.ts` verde; 0 `style={{` en `.tsx` nuevos.
5. `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py` (nunca a mano).
6. Con `STACKY_DB_COMPARE_RADAR_ENABLED=false`: API nueva 403, UI idéntica a main, loop en no-op (KPI-1).
7. Archivos que este plan promete NO tocar, intactos: `api/db_compare.py`, `services/dbcompare_diff.py`, `services/dbcompare_snapshot.py`, `services/dbcompare_registry.py`, `services/dbcompare_scripts.py`, `SummaryHero.tsx`, `dbcompareTypes.ts`, `runHistory.ts`.
8. Smoke manual de F8 (incluido el de deploy congelado, fix C11) documentado en el PR.
