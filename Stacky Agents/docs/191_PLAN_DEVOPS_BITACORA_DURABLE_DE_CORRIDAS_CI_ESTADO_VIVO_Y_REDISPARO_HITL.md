# Plan 191 — DevOps: bitácora durable de corridas CI, estado vivo y re-disparo HITL

- **Versión:** v2 (CRITICADO — APROBADO-CON-CAMBIOS; v1 → v2 aplicada)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky → criticar-y-mejorar-plan)
- **Serie:** DevOps (extiende el trigger/monitor CI del plan 72; hermano de 186/188/189/190)

## Changelog v1 → v2 (crítica C1..C5 + adición)

- **C1 (MENOR, afirmación técnica falsa):** "Flask matchea la literal primero" NO es cómo rutea
  Werkzeug. La razón correcta de que `GET /api/ci/runs` no colisione: los demás paths difieren en
  método y cantidad de segmentos (`/<project>/trigger` = POST 2 seg; `/<project>/trigger-preview`
  = GET 2 seg; `/<project>/pipeline/<id>` = GET 3 seg). El test de congelamiento queda.
- **C2 (IMPORTANTE):** `list_runs` especificado sin ambigüedad: SORT explícito por `triggered_at`
  descendente (ISO-8601 UTC ordena lexicográficamente) — nunca confiar en el orden del archivo — y
  filtro de igualdad exacta `entry["project"] == project` cuando `project` viene.
- **C3 (IMPORTANTE):** el hook del trigger NO usa nombres especulativos: pasa las MISMAS
  EXPRESIONES que el call-site real de `_record_trigger` argumento por argumento; para `web_url`,
  grep de la construcción de la respuesta de éxito de la ruta — si no existe URL, `None` literal.
- **C4 (MENOR):** constante nombrada `POLL_INTERVAL_MS = 10_000` en el componente.
- **C5 (MENOR):** caso de test para `limit` fuera de rango (0 y negativo → clamp del servicio a
  [1, MAX_ROWS]).
- **[ADICIÓN ARQUITECTO]:** persistencia del DESENLACE: cuando `monitor_pipeline_route` (:174)
  devuelve un estado FINAL, un hook best-effort actualiza `last_status` + `finished_at` del entry
  (`update_run_status` en el ledger). El historial responde durablemente "¿cómo terminó?" aunque
  nadie haya estado mirando. +3 tests; la UI usa `last_status` como estado inicial antes del primer
  poll.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El plan 72 le dio a Stacky el disparo y monitoreo de pipelines CI con HITL
(`api/ci.py`: `POST /api/ci/<project>/trigger` :75 con `confirm=True`, `GET
/api/ci/<project>/pipeline/<id>` :174) — pero la memoria de esos disparos es un **dict in-process**
(`_RECENT_TRIGGERS`, `api/ci.py:29-33`): se pierde en cada reinicio del backend, y el operador que
disparó un pipeline ayer no tiene NINGÚN registro de qué disparó, con qué ref, ni cómo terminó. Este
plan agrega una **bitácora local durable** (`services/ci_run_ledger.py`, JSONL con lock y retención,
patrón de los ledgers existentes): cada trigger exitoso se anota solo (best-effort, JAMÁS rompe el
trigger), un `GET /api/ci/runs` la expone, y la sección de trigger existente
(`TriggerPipelineSection.tsx`) muestra la lista con **estado vivo** (reusando el monitor :174 con su
cap anti-N+1 ya incluido, `_ACTIVE_POLLS` :36) y **"Re-disparar…"** que precarga el MISMO flujo de
confirmación HITL de siempre — nunca un disparo directo. Trazabilidad completa de la actividad CI con
cero costo cognitivo.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Persistencia correcta | Trigger exitoso con flag ON → 1 entry JSONL con los campos EXACTOS del contrato; con flag OFF → 0 entries; y un `append_run` que lanza excepción NO cambia la respuesta HTTP del trigger (best-effort probado) |
| KPI-2 | Lectura estable | `GET /api/ci/runs` devuelve orden descendente por `triggered_at`, respeta `limit`, y da 404 con la flag OFF |
| KPI-3 | Retención acotada | Tras 501 appends, el archivo contiene exactamente 500 entries y el más viejo fue rotado |
| KPI-4 | Poll acotado | El helper de la UI elige como máximo 5 pipeline_ids para pollear (los más recientes no-finales); verificado puro en vitest |
| KPI-5 | Re-disparo 100% HITL | El builder del payload de re-disparo NO incluye `confirm` (el confirm lo agrega el paso de confirmación existente del flujo trigger); verificado puro en vitest |
| KPI-6 | Desenlace persistido (ADICIÓN) | Monitor con estado final → `last_status`/`finished_at` actualizados en el entry; estado no-final o id desconocido → entry intacto y monitor sin cambios de respuesta |

**Ganancia robusta:** auditar "¿qué disparé y cómo terminó?" pasa de memoria humana a un registro
durable con estado; repetir un disparo rutinario pasa de re-tipear ref/branch a 1 click + confirm.

**Onboarding casi nulo:** la lista aparece sola debajo del trigger que el operador ya usa; el
re-disparo es el mismo diálogo de confirmación de siempre, precargado.

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `api/ci.py:29-37` — comentario literal: "Stores in-process (mono-operador single-process)".
  `_RECENT_TRIGGERS` (:33) guarda SOLO el último trigger por `(tracker_type, ref)` y muere con el
  proceso. `_ACTIVE_POLLS` (:36) ya implementa el cap anti-N+1 de polls por pipeline (máx 5).
- `api/ci.py:75-…` — `trigger_pipeline_route`: flag `STACKY_PIPELINE_TRIGGER_ENABLED` per-request
  (:82, default OFF — excepción dura 1 del plan 72: dispara ejecución remota), `confirm=True`
  obligatorio (:88), `normalize_ref` (:93), `get_ci_provider(project)` (:98),
  `_record_trigger(tracker_type, ref, sha, pipeline_id)` (:50) al éxito.
- `api/ci.py:174` — `monitor_pipeline_route` ya expone estado por `pipeline_id`. NO se toca.
- `frontend/src/components/devops/TriggerPipelineSection.tsx` — la sección de disparo existente.
- Ledgers JSONL con lock ya son patrón de la casa: `services/deploy_store.py:98-158`,
  `services/incident_store.py:33` (`_LEDGER_LOCK`).
- El plan 103 (monitor vivo persistente) quedó PROPUESTO sin implementar; esta bitácora es su
  sustrato natural si algún día se retoma (se anota como sinergia, no como dependencia).
- Vecinos que NO se pisan: 186 (lint estático), 188 (evidencia de deploys del Centro 120 — otro
  dominio: esto es CI del tracker), 189 (rollback readiness), 190 (equipaje portable).

**Gap:** Stacky ejecuta acciones remotas costosas (pipelines) y no conserva memoria durable de
ellas. Es el único efecto remoto del ecosistema sin ledger (deploys 120 lo tienen, incidencias 131
lo tienen, transferencias 190 lo tendrán).

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** backend Python + UI React, cero LLM; idéntico
   en Codex CLI / Claude Code CLI / GitHub Copilot Pro o sin ninguno.
2. **Cero trabajo extra para el operador:** flag default **ON** (ninguna excepción dura: la
   bitácora es escritura LOCAL de metadata de acciones que el operador ya confirmó; leerla es
   local). El trigger en sí sigue gateado por SU flag (OFF por excepción dura 1, decisión del plan
   72 que NO se toca).
3. **Human-in-the-loop:** el re-disparo NUNCA envía `confirm=True` por sí solo — precarga el flujo
   de confirmación existente. El monitor es read-only.
4. **Mono-operador sin auth:** nada de roles.
5. **No degradar:** el hook de persistencia es best-effort (try/except + log): un ledger roto,
   lleno o read-only JAMÁS afecta el trigger. `monitor_pipeline_route` y `_ACTIVE_POLLS` intactos.
6. **Reusar, no reinventar:** patrón JSONL+lock de `deploy_store`/`incident_store`; monitor y cap
   anti-N+1 existentes; flujo de confirmación de trigger existente; `stacky_logger`.
7. **Gotcha config:** en `api/ci.py` la instancia es `_config.config` (import :18, uso :82) —
   mismo patrón para la flag nueva. **Gotcha tests:** correr SIEMPRE por archivo
   (`test_harness_flags.py` hace `importlib.reload(config)` y contamina corridas mixtas — gotcha
   registrado hoy).

---

## 4. Fases

### F0 — Flag + servicio de bitácora (JSONL, lock, retención) + endpoint de lectura

**Objetivo:** ledger durable funcionando de punta a punta en lectura (aún sin productor).
**Valor:** sustrato completo y verificable; F1 solo enchufa el productor.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- CREAR `Stacky Agents/backend/services/ci_run_ledger.py`
- EDITAR `Stacky Agents/backend/api/ci.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan191_ci_ledger_flag.py`

**Cambios exactos:**

1. `harness_flags.py` — FlagSpec al final del bloque DEVOPS (~:2743):

```python
FlagSpec(
    key="STACKY_CI_RUN_LEDGER_ENABLED",
    type="bool",
    label="Bitácora de corridas CI",
    description="Registra localmente cada pipeline disparado desde Stacky (ref, id, "
                "resultado) y muestra el historial con estado vivo y re-disparo con "
                "confirmación. Solo metadata local; sin secretos.",
    group="global",
    default=True,
    requires="STACKY_PIPELINE_TRIGGER_ENABLED",  # sin triggers no hay contenido (informativo UI)
),
```

2. Agregar la key a `_CURATED_DEFAULTS_ON` (~:200-216, comentario
   `# Plan 191 — bitácora de corridas CI`). **Gotcha:** fuera de la lista →
   `test_default_known_only_for_curated` rojo. Registrar el edge en
   `tests/test_harness_flags_requires.py` (arista `STACKY_CI_RUN_LEDGER_ENABLED →
   STACKY_PIPELINE_TRIGGER_ENABLED`).

3. CREAR `services/ci_run_ledger.py`:

```python
"""services/ci_run_ledger.py — Plan 191. Bitácora durable de corridas CI disparadas.

JSONL local (data_dir()/ci_runs.jsonl) con lock y retención. Patrón de la casa:
deploy_store.py:98-158 / incident_store.py:33. PURO local: cero red, cero provider.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

MAX_ROWS = 500           # retención dura: al superar, se conservan los 500 más nuevos
_LOCK = threading.Lock()


def _ledger_path() -> Path:
    return Path(runtime_paths.data_dir()) / "ci_runs.jsonl"


def append_run(entry: dict) -> None:
    """Agrega una corrida. Campos del CONTRATO (los ausentes se guardan como None):
    project, tracker_type, ref, sha, pipeline_id, web_url, triggered_at (ISO UTC;
    si falta se estampa acá), source ("stacky"). Claves fuera del contrato se DESCARTAN
    (allowlist, no denylist: jamás puede colarse un secreto por accidente).
    Aplica retención MAX_ROWS en el mismo write (reescritura atómica: tmp + replace)."""


def list_runs(project: str | None = None, limit: int = 50) -> list[dict]:
    """C2 — semántica EXACTA: (1) leer todas las líneas válidas; (2) si project no es None,
    filtrar entry["project"] == project (igualdad exacta); (3) SORT por entry["triggered_at"]
    DESCENDENTE (ISO-8601 UTC ordena lexicográficamente; nunca confiar en el orden del archivo);
    (4) limit acotado a [1, MAX_ROWS] (0/negativo → 1; > MAX_ROWS → MAX_ROWS)."""


def update_run_status(pipeline_id: str, status: str, finished_at: str | None = None) -> bool:
    """[ADICIÓN ARQUITECTO] — setea last_status (+ finished_at si viene) del entry con ese
    pipeline_id (el más reciente si hubiera duplicados). Reescritura atómica bajo _LOCK.
    Devuelve False (no-op silencioso) si el id no está. Solo estos 2 campos son actualizables."""
```

   Detalles duros para el implementador:
   - `append_run`: `with _LOCK:` leer líneas existentes (tolerar líneas corruptas: saltearlas y
     contarlas), agregar la nueva, recortar a `MAX_ROWS` (las más nuevas), escribir a
     `ci_runs.jsonl.tmp` y `Path.replace` (atómico en el mismo volumen).
   - ALLOWLIST de campos exacta: `("project", "tracker_type", "ref", "sha", "pipeline_id",
     "web_url", "triggered_at", "source", "last_status", "finished_at")` — constante módulo-nivel
     `ENTRY_FIELDS` (los últimos 2 los escribe SOLO `update_run_status`; `append_run` los inicializa
     en `None`).
   - `triggered_at` default: `datetime.now(timezone.utc).isoformat()`.
   - Cero imports de `ci_provider`/`requests` (el ledger no conoce la red).

4. `api/ci.py` — endpoint de lectura DESPUÉS de `monitor_pipeline_route`:

```python
@bp.get("/runs")
def list_ci_runs_route():
    """Bitácora local de corridas disparadas. Plan 191. Read-only."""
    if not getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
        abort(404)
    project = request.args.get("project") or None
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        return jsonify({"error": "limit inválido"}), 400
    from services.ci_run_ledger import list_runs
    return jsonify({"runs": list_runs(project=project, limit=limit)})
```

   (NOTA de ruta, C1: el blueprint ya cuelga de `/api/ci` — la ruta final es `GET /api/ci/runs`.
   No colisiona porque los demás paths difieren en MÉTODO y CANTIDAD DE SEGMENTOS:
   `/<project>/trigger` = POST 2 seg, `/<project>/trigger-preview` = GET 2 seg,
   `/<project>/pipeline/<id>` = GET 3 seg — `GET /runs` es 1 segmento. El test
   `test_runs_no_captura_como_project` lo congela igual.)

5. `test_plan191_ci_ledger_flag.py` a `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh`
   (**gotcha** meta-test).

**Tests PRIMERO** — `tests/test_plan191_ci_ledger_flag.py` (ledger en `tmp_path` monkeypatcheando
`runtime_paths.data_dir`):
- `test_flag_declarada_bool_default_on` — type/default/requires exactos.
- `test_flag_en_curated_defaults_on`.
- `test_endpoint_404_flag_off`.
- `test_endpoint_200_vacio_flag_on` — sin archivo → `{"runs": []}`.
- `test_kpi2_orden_y_limit` — 3 entries sembradas EN DESORDEN de archivo → desc por
  `triggered_at` (prueba que hay SORT, no orden de archivo, C2); `limit=2` → 2.
- `test_limit_fuera_de_rango_clampa` (C5) — `limit=0` y `limit=-5` → 1 entry; `limit=99999` →
  a lo sumo MAX_ROWS.
- `test_kpi3_retencion_500` — 501 appends → `len == 500` y el primero sembrado ya no está.
- `test_allowlist_descarta_extras` — `append_run({"pipeline_id": "1", "password": "x"})` → la
  línea guardada NO contiene `password`.
- `test_lineas_corruptas_no_rompen` — archivo con 1 línea basura + 1 válida → `list_runs` devuelve
  la válida sin excepción.
- `test_runs_no_captura_como_project` — `GET /api/ci/runs` NO cae en la ruta
  `/<project>/pipeline/...` ni en trigger (status 200 con flag ON).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan191_ci_ledger_flag.py -q`
(cwd = `Stacky Agents\backend`; SIEMPRE por archivo — gotcha reload de config).

**Criterio binario:** los 10 tests pasan Y `test_harness_ratchet_meta.py` verde.

**Flag:** `STACKY_CI_RUN_LEDGER_ENABLED` default **ON** (ninguna excepción dura: metadata local de
acciones ya confirmadas por el operador).

**Runtimes:** idéntico en los 3. Fallback: flag OFF → 404 y la UI no muestra la lista.

**Trabajo del operador:** ninguno.

---

### F1 — Productor: hook best-effort en el trigger existente

**Objetivo:** que cada trigger exitoso se anote solo, sin poder romper JAMÁS el trigger.
**Valor:** la bitácora se llena sin ningún cambio de hábito.

**Archivos:**
- EDITAR `Stacky Agents/backend/api/ci.py`
- CREAR `Stacky Agents/backend/tests/test_plan191_ci_ledger_hook.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Cambios exactos:**

1. LEER el cuerpo completo de `trigger_pipeline_route` (:75 en adelante) y ubicar el punto de
   ÉXITO donde se llama `_record_trigger(tracker_type, ref, sha, pipeline_id)` (:50 define el
   helper; el call-site está más abajo en la ruta). INMEDIATAMENTE DESPUÉS de ese call-site,
   agregar:

```python
    # Plan 191 — bitácora durable (best-effort: JAMÁS rompe el trigger)
    if getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
        try:
            from services.ci_run_ledger import append_run
            append_run({
                "project": project,
                "tracker_type": tracker_type,
                "ref": ref_value,
                "sha": sha,                      # usar las MISMAS variables locales que
                "pipeline_id": pipeline_id,      # recibe _record_trigger en ese punto
                "web_url": web_url_if_available, # si la respuesta del provider trae URL;
                                                 # si no existe esa variable local → None
                "source": "stacky",
            })
        except Exception:
            from services.stacky_logger import logger as stacky_logger
            stacky_logger.info("ci_run_ledger", "append_failed", pipeline_id=str(pipeline_id))
```

   Regla dura (C3): los valores se pasan con las MISMAS EXPRESIONES que usa el call-site real de
   `_record_trigger(...)` — argumento por argumento (si ahí dice `provider.name`, acá va
   `provider.name`; NO inventar locales como `tracker_type` si no existen). Para `web_url`: grep
   de la construcción de la respuesta de éxito de la ruta; si ningún campo URL existe →
   `"web_url": None` literal.

2. [ADICIÓN ARQUITECTO] Hook del DESENLACE en `monitor_pipeline_route` (:174): tras obtener
   `result = provider.monitor_pipeline(pipeline_id)` (:186), agregar best-effort:

```python
    # Plan 191 — persistir desenlace (best-effort; JAMÁS rompe el monitor)
    if getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
        try:
            status = str((result or {}).get("status") or "").lower()
            if status in ("success", "failed", "canceled", "skipped"):
                from datetime import datetime, timezone
                from services.ci_run_ledger import update_run_status
                update_run_status(str(pipeline_id), status,
                                  datetime.now(timezone.utc).isoformat())
        except Exception:
            pass  # el monitor nunca se degrada por el ledger
```

   (La clave exacta del estado en `result` se toma LEYENDO qué devuelve `monitor_pipeline` del
   provider — si el shape usa otra clave, usar esa; el mapeo a los 4 estados finales es el del
   glosario.)

3. NINGÚN otro cambio en las rutas (guards, confirm, idempotencia `_RECENT_TRIGGERS`,
   `_ACTIVE_POLLS` intactos).

**Tests PRIMERO** — `tests/test_plan191_ci_ledger_hook.py` (Flask test client; provider
monkeypatcheado para éxito — espejar el estilo de los tests EXISTENTES del plan 72: correr
`ls tests/ | grep -i "plan72\|ci_trigger"` y leer el que testee `trigger_pipeline_route`):
- `test_kpi1_trigger_exitoso_persiste` — trigger OK (ambas flags ON) → 1 entry con
  `pipeline_id`/`ref`/`project` correctos y `source == "stacky"`.
- `test_kpi1_ledger_off_no_persiste` — trigger flag ON + ledger OFF → 0 entries, respuesta igual.
- `test_kpi1_append_roto_no_rompe_trigger` — monkeypatch `ci_run_ledger.append_run` → `raise`;
  la respuesta HTTP del trigger es IDÉNTICA (status y body) a la del caso sin excepción.
- `test_trigger_fallido_no_persiste` — provider que falla → 0 entries.
- `test_confirm_sigue_obligatorio` — sin `confirm` → 400 (guardia de no-regresión HITL).
- `test_monitor_final_actualiza_ledger` (ADICIÓN) — entry sembrado + monitor devuelve estado final
  → `last_status` y `finished_at` seteados.
- `test_monitor_no_final_no_actualiza` (ADICIÓN) — estado "running" → entry intacto.
- `test_monitor_id_desconocido_noop` (ADICIÓN) — pipeline_id sin entry → monitor responde igual,
  sin excepción.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan191_ci_ledger_hook.py -q`

**Criterio binario:** los 8 tests pasan (KPI-1 y KPI-6 completos).

**Flag:** la de F0 (y la del trigger 72, intacta). **Runtimes:** idéntico.
**Trabajo del operador:** ninguno.

---

### F2 — UI: historial con estado vivo (poll acotado) y re-disparo HITL

**Objetivo:** ver la bitácora donde se dispara, con estado fresco y repetición en 1 click+confirm.
**Valor:** cierre del ciclo; trazabilidad y repetición sin fricción.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/devops/ciRunsLedger.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/devops/ciRunsLedger.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/devops/TriggerPipelineSection.tsx`

**Comportamiento exacto:**

1. `ciRunsLedger.ts` (puro):

```typescript
export interface CiRun {
  project: string; tracker_type: string; ref: string; sha: string | null;
  pipeline_id: string; web_url: string | null; triggered_at: string; source: string;
}
export const FINAL_STATUSES = ['success', 'failed', 'canceled', 'skipped'] as const;
export const POLL_INTERVAL_MS = 10_000; // C4 — constante nombrada
export function pollTargets(runs: CiRun[], statusById: Record<string, string | undefined>): string[] {
  // KPI-4: elegir los pipeline_id a pollear — los más recientes cuyo estado NO sea final,
  // máximo 5 (mismo espíritu que _ACTIVE_POLLS del backend, api/ci.py:36-37).
  // ADICIÓN: el estado inicial de cada run es su last_status persistido (si existe) — así los
  // runs ya terminados NO se pollean nunca al montar.
  return runs
    .filter((r) => {
      const s = statusById[r.pipeline_id] ?? (r as CiRun & { last_status?: string }).last_status ?? '';
      return !FINAL_STATUSES.includes(s as never);
    })
    .slice(0, 5)
    .map((r) => r.pipeline_id);
}
export function retriggerPayload(run: CiRun): { ref: string } {
  // KPI-5: SIN confirm — el confirm lo agrega el paso de confirmación del flujo existente.
  return { ref: run.ref };
}
export function runLabel(run: CiRun): string {
  return `${run.ref} · #${run.pipeline_id} · ${run.triggered_at}`;
}
```

2. `TriggerPipelineSection.tsx`:
   - Al montar (y tras cada trigger exitoso), `GET /api/ci/runs?project=<activo>&limit=20`; si
     404 (flag OFF) → no renderizar nada nuevo (sección idéntica a hoy) y no reintentar en la
     sesión.
   - Render de la lista bajo el formulario de trigger existente: filas con `runLabel(run)`, chip
     de estado (del mapa `statusById`), link "abrir" si `web_url` (target _blank), y botón
     "Re-disparar…" que PRECARGA el formulario/flujo de confirmación EXISTENTE con
     `retriggerPayload(run)` — el operador ve el mismo diálogo de confirmación de siempre y recién
     ahí se dispara (HITL intacto; PROHIBIDO llamar al trigger con confirm automático).
   - Poll de estado: cada 10 s, para los ids de `pollTargets(...)`, llamar el monitor EXISTENTE
     `GET /api/ci/<project>/pipeline/<id>` y actualizar `statusById`; detener el intervalo cuando
     `pollTargets` devuelve `[]` (todos finales) o al desmontar. Estilos por CSS module de la
     sección (**gotcha ratchet:** cero `style={{}}`).

**Tests PRIMERO** — `ciRunsLedger.test.ts` (vitest, sin @testing-library — gap conocido):
- `pollTargets` — excluye estados finales, cap a 5, respeta orden (KPI-4).
- `pollTargets_usa_last_status_persistido` (ADICIÓN) — run con `last_status: "success"` y sin
  entrada en `statusById` → NO se pollea.
- `retriggerPayload` — NO contiene la clave `confirm` (KPI-5: `'confirm' in payload === false`).
- `runLabel` — formato exacto.

**Comando:** `npx vitest run src/components/devops/ciRunsLedger.test.ts`
(cwd = `Stacky Agents\frontend`; por archivo).

**Criterio binario:** los 4 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Smoke manual (1 paso, opcional):** disparar un pipeline de prueba → aparece en la lista con
estado que se actualiza; "Re-disparar…" abre el diálogo de confirmación precargado.

**Flag:** la de F0 (404 → sección idéntica a hoy). **Runtimes:** UI pura.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| El hook rompe el trigger (peor caso) | try/except total + test KPI-1 con `append_run` explotando → respuesta idéntica; el ledger nunca es camino crítico |
| Secretos en el ledger | ALLOWLIST estricta de 8 campos (`ENTRY_FIELDS`) — lo no listado se descarta; test `test_allowlist_descarta_extras` |
| Ledger corrupto (crash a mitad de write) | Escritura atómica tmp+replace; lectura tolera líneas corruptas (test) |
| N+1 de polls de estado | `pollTargets` cap 5 + solo no-finales + stop al terminar; el backend ya tiene `_ACTIVE_POLLS` (:36) como segunda barrera |
| Colisión de ruta `/runs` con `/<project>/...` | Test `test_runs_no_captura_como_project` congela el matcheo |
| Re-disparo sin confirmación (violación HITL) | `retriggerPayload` SIN `confirm` + test KPI-5 + el flujo de confirmación existente es el único camino |
| Sesión paralela toca `api/ci.py` (177-190 activa) | Cambios ADITIVOS (ruta nueva al final + hook de 1 bloque tras `_record_trigger`); tras merge `python -m compileall` + grep duplicado silencioso (gotcha) |
| Contaminación de tests por reload de config | Correr por archivo (gotcha registrado hoy: `test_harness_flags.py` hace `importlib.reload(config)`) |

## 6. Fuera de scope (explícito)

- Logs inline de la corrida (existe `ci_logs_provider`; integrarlo es otro plan — acá solo
  deep-link `web_url` si el provider la dio).
- Registrar corridas disparadas FUERA de Stacky (detección de externas: requiere polling de listas
  del provider).
- Monitor vivo persistente del plan 103 (esta bitácora sería su sustrato; no se implementa acá).
- Retención configurable por UI (constante `MAX_ROWS=500`; configurabilidad = v2 si se pide).
- Métricas/tendencias agregadas sobre la bitácora (duración media, tasa de éxito) — v2 natural.

## 7. Glosario (para modelos menores)

- **Trigger CI (72):** `POST /api/ci/<project>/trigger` con `confirm=True` (HITL), flag
  `STACKY_PIPELINE_TRIGGER_ENABLED` default OFF (excepción dura 1: ejecuta remoto).
- **Monitor (72):** `GET /api/ci/<project>/pipeline/<id>` — estado read-only de una corrida.
- **`_RECENT_TRIGGERS` / `_ACTIVE_POLLS`:** dicts in-process de `api/ci.py:33,36` (idempotencia y
  cap de polls); NO son durables y NO se reemplazan — la bitácora es un registro paralelo durable.
- **Ledger JSONL:** archivo de líneas JSON con lock (patrón `deploy_store`/`incident_store`).
- **ALLOWLIST `ENTRY_FIELDS`:** los únicos 8 campos que pueden persistirse; el resto se descarta.
- **Estado final:** `success`/`failed`/`canceled`/`skipped` — deja de pollearse.
- **`_CURATED_DEFAULTS_ON` / HARNESS_TEST_FILES / ratchet UI / reload de config:** convenciones y
  gotchas de la casa (ver planes 186-190).

## 8. Orden de implementación

1. F0 — flag + `ci_run_ledger.py` + `GET /api/ci/runs` + 9 tests.
2. F1 — hook best-effort en `trigger_pipeline_route` + 5 tests.
3. F2 — helpers + lista con estado vivo + re-disparo HITL + 3 tests + `tsc`.

Cada fase se commitea sola con sus tests verdes ANTES de la siguiente (TDD estricto, cero falsos
verdes).

## 9. Definición de Hecho (DoD) global

- [ ] Los 3 archivos de test (`test_plan191_ci_ledger_flag.py`, `test_plan191_ci_ledger_hook.py`,
      `ciRunsLedger.test.ts`) pasan POR ARCHIVO con el intérprete correcto.
- [ ] `test_harness_ratchet_meta.py`, `test_harness_flags_requires.py` y
      `test_default_known_only_for_curated` siguen verdes.
- [ ] KPI-1..KPI-5 verificados por los tests nombrados.
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio.
- [ ] Flag `STACKY_CI_RUN_LEDGER_ENABLED` visible/toggleable en la UI de flags, default ON.
- [ ] Con la flag OFF: cero diferencias observables vs. hoy (404 + sección idéntica).
- [ ] `trigger_pipeline_route` conserva TODOS sus guards (flag, confirm, idempotencia) — diff del
      archivo muestra SOLO el bloque best-effort agregado y la ruta `/runs` nueva.
- [ ] `services/ci_run_ledger.py` sin imports de red ni de providers (grep del archivo: cero
      `requests`, cero `ci_provider`).
