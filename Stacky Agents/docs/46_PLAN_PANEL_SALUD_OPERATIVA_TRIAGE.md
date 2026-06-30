# Plan 46 — Panel de Salud Operativa (Triage pasivo, solo-lectura)

> Estado: IMPLEMENTADO 2026-06-19 (F0–F3). Numeración: 46.
>
> **Validación (2026-06-19):** test_operational_health.py (10), test_harness_flags_op_health.py (2),
> test_operational_health_endpoint.py (7, incl. anti-N+1 con joinedload); tsc --noEmit exit 0.
> Card montada en DiagnosticsPage bajo HarnessHealthCard, con drawer de detalle por execution.
> Flag STACKY_OPERATIONAL_HEALTH_ENABLED env_only, default true; OFF → endpoint 404 + card null.
> Autor: StackyArchitectaUltraEficientCode. Fecha: 2026-06-18.
> **Versión: v1 → v2 → v3** (segunda revisión adversarial del juez, 2026-06-19).

### Changelog v2 → v3 (segunda crítica `criticar-y-mejorar-plan`)
- **C4 (BLOQUEANTE → resuelto):** F2 reinventaba la query con `ex.ticket.stacky_project_name` en un loop sobre hasta 200 filas → **N+1 queries** (1 SELECT de execs + 1 por cada `ex.ticket`). Ya existe el patrón canónico `joinedload(AgentExecution.ticket)` en `services/harness_health.py:236` (comentado ahí mismo como "joinedload garantiza que no haya N+1"). `_recent_executions` corregido para usar `joinedload`. Sin esto el panel degradaba performance justo en el caso que R1 dice mitigar.
- **C5 (IMPORTANTE → resuelto):** inconsistencia interna sobre `zombie_minutes`. La [ADICIÓN ARQUITECTO] de v2 lo alinea a `EXECUTION_TIMEOUT_MINUTES`, pero (a) `DEFAULT_THRESHOLDS` seguía en `30`, (b) R4/G/glosario seguían diciendo "default 30", y (c) el valor real es **120** (`ticket_status.py:40`), no 30. Unificado: `DEFAULT_THRESHOLDS["zombie_minutes"]` documentado como fallback de la función pura (que NO importa nada del sistema, por diseño), y el endpoint siembra el valor real `EXECUTION_TIMEOUT_MINUTES` como default efectivo. R4/glosario corregidos a "default = timeout real del sistema".
- **C6 (MENOR → resuelto):** F2 hacía `from services.ticket_status import EXECUTION_TIMEOUT_MINUTES` LOCAL dentro de la función, pero ese símbolo YA está importado a nivel módulo en `diag.py:31`. Eliminado el import redundante; se usa el del módulo.
- **C7 (MENOR → resuelto):** R1 citaba el índice `ix_exec_status_started` (status, started_at) como mitigación de la query, pero la query ordena por `started_at DESC` SIN filtrar por status → ese índice compuesto no la acelera (no hay índice solo sobre `started_at`). Claim corregido: la mitigación real es el `LIMIT` + lazy, no el índice.

### Changelog v1 → v2 (primera crítica)
- **C1 (IMPORTANTE):** F2 usaba `from db import get_session` / `with get_session()`, símbolo que NO existe. El helper real es `session_scope` (`db`, usado en `diag.py:42`). Pseudocódigo corregido a `session_scope` y NOTA reescrita.
- **C2 (IMPORTANTE):** F2 parseaba `int(request.args.get("limit", 200))` fuera de try → `?limit=abc` tiraba 500. Corregido con parse defensivo + caso borde + test nuevo.
- **C3 (MENOR):** las keys `metadata["failure_kind"]`/`["runtime"]`/`["model"]` no estaban citadas a línea. Aclarado que su ausencia es esperable y el agregador degrada (no inventa); sin esto se sobre-prometía cobertura.
- **[ADICIÓN ARQUITECTO]:** el default de `zombie_minutes` se alinea a `EXECUTION_TIMEOUT_MINUTES` (ya importado en `diag.py:31`) en vez de un `30` mágico, para que "zombie" en el panel signifique lo mismo que el timeout real del sistema (single source of truth, reuso, cero trabajo al operador).

## 1. Título, objetivo y KPI

**Panel de Salud Operativa**: una vista solo-lectura, lazy y sin hot-path que destila las
runs recientes (`AgentExecution`) en **señales accionables de triage** para el operador
mono-usuario. Responde de un vistazo: *qué runs quedaron en `needs_review` esperando mi
revisión, cuáles fallaron y por qué (`failure_kind`), cuáles costaron de más (sobre un
umbral), y cuáles están zombie/stalled (running viejas sin cerrar)*. No genera nada, no
muta nada, no decide nada: **amplifica al operador** poniendo lo que requiere su atención
al frente, con un enlace directo a cada run.

**Valor / KPI:**
- KPI1 — *Tiempo a triage*: el operador identifica las runs que requieren su acción en
  **1 request** en vez de barrer la lista de ejecuciones manualmente.
- KPI2 — *Cobertura de revisión*: nº de runs `needs_review` pendientes visible y
  envejecido (días sin atender), para que ninguna quede olvidada.
- KPI3 — *Fugas de costo detectadas*: nº de runs por encima del umbral de costo,
  agregadas por modelo/runtime, para detectar configuración cara.
- KPI4 — *Zombies detectados*: nº de runs `running` con antigüedad > umbral (síntoma de
  sesión colgada — ver memoria `claude-cli-zombie-sessions`).

## 2. Por qué ahora / gap que cierra

La telemetría por-run ya es rica pero **no hay una vista que la convierta en acción**:

- **Plan 39** agregó historial de runs (`/history`) y duración, y guarda costo/modelo en
  `metadata_json`. Es una lista cronológica, no un triage: no separa "lo que necesita mi
  acción" del ruido.
- **Plan 44** (Observatorio de Grounding, PROPUESTO) mira **calidad de grounding de
  épicas** (epic_summary/confidence, sugeridor de diccionario). Es ortogonal: 44 mira la
  calidad semántica de un tipo de output; **46 mira la salud operativa de TODAS las runs**.
- **Plan 45** (catálogo UI + Issues, PROPUESTO) no toca telemetría de runs.
- **Plan 41** (pre-vuelo de intención, PROPUESTO grande) actúa **antes** de ejecutar; 46
  actúa **después**, sobre runs ya ocurridas. No se solapan.
- El **digest** existente (`Reports.digest`, doc 23) es un resumen agregado orientado a
  *management* (tasas, costo total, highlights). **No es accionable por-run**: no te dice
  *cuál* run específica revisar ni te enlaza a ella. 46 es triage por-run, no resumen.

Gap concreto: hoy, para saber si quedó una run en `needs_review` o un zombie colgado, el
operador debe abrir el panel de ejecuciones y leerlas una por una. 46 lo destila.

**Diferenciación dura vs digest (no duplicar):** el digest agrega *tasas y totales* por
período; 46 lista *runs individuales accionables* (id, ticket, antigüedad, enlace) en 4
categorías de triage. Si en review se considera redundante, la mitigación es: 46 NO
recalcula tasas; solo selecciona y rankea runs concretas.

## 3. Principios y guardarraíles (codificados por fase)

- **G1 — Funciones de agregación PURAS**: `services/operational_health.py` recibe una
  `list[dict]` (cada dict = `AgentExecution.to_dict(include_output=False)` enriquecido con
  `project` y `created_at_norm`) + un dict de umbrales, y devuelve un dict. **Cero I/O,
  cero import de Flask/DB.** Testeable con dicts en memoria.
- **G2 — Endpoint y query helper son los únicos con I/O**: el endpoint hace la query
  (lazy, al pedir), normaliza filas a dicts y llama al agregador puro.
- **G3 — Lazy, fuera del hot-path**: nada corre en background ni en el flujo de
  generación. Solo se computa al hacer GET del endpoint.
- **G4 — Solo-lectura**: ningún `INSERT`/`UPDATE`/`DELETE`. La query es `SELECT` con
  `LIMIT`.
- **G5 — Cero trabajo al operador**: feature solo-lectura. Flag default `true`; con OFF el
  endpoint responde **404** y la card **no se monta** (no aparece, no rompe).
- **G6 — Human-in-the-loop**: el panel **no toma decisiones ni dispara acciones**. Solo
  informa y enlaza. Prohibido botón de "reintentar/cancelar automático" en este plan.
- **G7 — Mono-operador sin auth**: sin RBAC, sin `current_user`. El header existente no se
  valida ni se usa aquí.
- **G8 — Backward-compatible**: no se altera ningún endpoint, modelo ni columna
  existentes. Solo se AGREGA: 1 servicio, 1 endpoint, 1 entrada en FLAG_REGISTRY, 1 helper
  de endpoints frontend, 1 card.
- **G9 — Paridad 3 runtimes**: el agregador es agnóstico al runtime; lee `metadata.runtime`
  / `agent_type` de cada fila. Las 3 (Codex CLI, Claude Code CLI, GitHub Copilot Pro)
  escriben en la misma tabla `agent_executions`, así que las 3 quedan cubiertas por
  construcción. Fallback por runtime: ver cada fase.

### Contratos de datos confirmados (citados contra el código)

- `AgentExecution` — `backend/models.py:207`. Campos reales:
  `status` (`:213`), `verdict` (`:214`), `metadata_json` (`:219`),
  `started_at` (`:223`), `completed_at` (`:224`), `agent_type` (`:212`),
  `error_message` (`:221`). **NO hay columnas `cost`/`model`/`failure_kind`/`project`**:
  viven dentro de `metadata_dict` (`:260`) y el proyecto se obtiene vía
  `ticket.stacky_project_name` (`Ticket.stacky_project_name`, `backend/models.py:48`).
- `to_dict(include_output=False)` — `backend/models.py:280`. Expone `id`, `ticket_id`,
  `agent_type`, `status`, `verdict`, `metadata` (= `metadata_dict`), `error_message`,
  `started_at` (iso), `completed_at` (iso), `duration_ms`. **No expone `created_at`** (la
  tabla usa `started_at` como referencia temporal; `created_at` no existe en
  `AgentExecution`). Usar `started_at` como tiempo de referencia.
- **Keys reales dentro de `metadata`** (confirmadas contra el digest existente y el
  HarnessHealthCard): `metadata["cost"]` puede ser número o dict
  `{"reported": x, "estimated": y, "total": z}` (ver `DigestTotals.cost_usd`,
  `endpoints.ts:1176`); `metadata["model"]`; `metadata["runtime"]`;
  `metadata["failure_kind"]`. **C3 — NO citadas a línea:** a diferencia de `cost`, las keys
  `runtime`/`model`/`failure_kind` no están confirmadas contra una línea concreta de
  escritura; su presencia depende de qué escribió cada runner. El plan NO sobre-promete
  cobertura: si faltan, el agregador degrada (`_runtime_of` cae a `agent_type`→`"unknown"`;
  `failure_kind`→`"unknown"`; sin `model` no agrupa por modelo). Nunca inventa. **CASO BORDE
  OBLIGATORIO**: cualquiera puede faltar o venir con shape distinto → el agregador debe ser
  defensivo (`_coerce_cost`, `.get(...)`).
- Blueprint `diag` — `backend/api/diag.py:36`, `url_prefix="/diag"`, montado bajo `/api`
  (el endpoint `health` vive en `/api/diag/health`). Patrón de endpoint solo-lectura: ver
  `health()` en `:282` (no muta, devuelve `jsonify`).
- `FlagSpec` / `FLAG_REGISTRY` — `backend/services/harness_flags.py:19` y `:29`. Módulo
  PURO (no toca disco ni Flask). Para leer el flag en call-time se usa
  `os.getenv(KEY, "true").lower() != "false"` (mismo patrón que `health()` usa para
  `STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS`, `diag.py:326`).
- Frontend: card consume vía `api.get` + `useEffect` (patrón de `HarnessHealthCard.tsx:9`).
  Helpers de API agrupados en objetos `export const X = {...}` en
  `frontend/src/api/endpoints.ts`. `DiagnosticsPage.tsx` ya monta `<HarnessHealthCard />`
  (`:198`) y refetchea a 30s (`:50`).

### Entorno de tests (confirmado por memoria del repo)

- Backend: intérprete `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe`,
  cwd = `Stacky Agents/backend`. **Correr por archivo** (la full-suite está contaminada;
  ver memoria `stacky-backend-test-suite-pollution`).
- Frontend: validar con `npx tsc --noEmit` (no hay vitest instalado).

---

## 4. Fases

### F0 — Servicio de agregación PURO (núcleo testeable, sin I/O)

**Objetivo (1 frase):** una función pura que, dadas las runs recientes como dicts + un
dict de umbrales, devuelve las 4 listas de triage y un resumen. **Valor:** núcleo
verificable con dicts en memoria, sin DB ni Flask, reutilizable y barato de testear.

**Archivo a CREAR:** `Stacky Agents/backend/services/operational_health.py`

**Símbolos EXACTOS a definir:**
- `DEFAULT_THRESHOLDS: dict` = `{"cost_usd": 1.0, "zombie_minutes": 30, "needs_review_stale_days": 3, "max_rows_per_bucket": 20}`
  > **C5 — sobre el `30`:** este es solo el fallback de la función PURA cuando se la llama
  > sin thresholds (G1: el servicio puro NO importa `EXECUTION_TIMEOUT_MINUTES` ni nada del
  > sistema, para no acoplarse). El default EFECTIVO en producción es `EXECUTION_TIMEOUT_MINUTES`
  > (=120), que el endpoint F2 siembra siempre. No tocar este `30`: mantiene la función pura
  > y autónoma para sus tests en memoria.
- `def _coerce_cost(metadata: dict) -> float | None` — normaliza `metadata.get("cost")`:
  - si es `int`/`float` → ese valor;
  - si es `dict` → `total` si existe y es numérico, si no `reported`, si no `estimated`;
  - si falta o no es numérico → `None`.
- `def _runtime_of(run: dict) -> str` — `run["metadata"].get("runtime") or run.get("agent_type") or "unknown"`.
- `def _age_minutes(now_iso: str, started_at: str | None) -> float | None` — diferencia en
  minutos entre `now_iso` y `started_at` (ambos ISO-8601). Si `started_at` es `None` o no
  parseable → `None`. **Sin `datetime.utcnow()` interno**: `now_iso` se inyecta (mantiene
  la función pura y determinista para el test).
- `def aggregate_operational_health(runs: list[dict], now_iso: str, thresholds: dict | None = None) -> dict`

**Pseudocódigo de `aggregate_operational_health`:**
```
th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
cap = th["max_rows_per_bucket"]

needs_review, failed, expensive, zombie = [], [], [], []

for run in runs:
    meta = run.get("metadata") or {}
    rt = _runtime_of(run)
    row = {  # fila accionable mínima (NO incluye output)
        "id": run.get("id"),
        "ticket_id": run.get("ticket_id"),
        "agent_type": run.get("agent_type"),
        "runtime": rt,
        "project": run.get("project"),         # inyectado por el endpoint
        "started_at": run.get("started_at"),
        "status": run.get("status"),
    }
    status = (run.get("status") or "").lower()
    age = _age_minutes(now_iso, run.get("started_at"))

    # 1) needs_review pendientes (envejecidos)
    if status == "needs_review":
        nr = {**row, "age_days": round(age/1440, 2) if age is not None else None}
        nr["stale"] = (nr["age_days"] is not None
                       and nr["age_days"] >= th["needs_review_stale_days"])
        needs_review.append(nr)

    # 2) failed con failure_kind
    if status in ("error", "failed"):
        failed.append({**row,
                       "failure_kind": meta.get("failure_kind") or "unknown",
                       "error_message": run.get("error_message")})

    # 3) caras por encima del umbral (cualquier status)
    cost = _coerce_cost(meta)
    if cost is not None and cost >= th["cost_usd"]:
        expensive.append({**row, "cost_usd": round(cost, 4),
                          "model": meta.get("model")})

    # 4) zombie: running con antigüedad > umbral
    if status == "running" and age is not None and age >= th["zombie_minutes"]:
        zombie.append({**row, "age_minutes": round(age, 1)})

# orden: lo más urgente primero
needs_review.sort(key=lambda r: (r["age_days"] is None, -(r["age_days"] or 0)))
failed.sort(key=lambda r: (r["started_at"] or ""), reverse=True)
expensive.sort(key=lambda r: -(r["cost_usd"] or 0))
zombie.sort(key=lambda r: -(r["age_minutes"] or 0))

def cost_by(key_fn, rows):  # agregación de costo de las caras por modelo/runtime
    out = {}
    for r in rows:
        k = key_fn(r) or "unknown"
        out[k] = round(out.get(k, 0) + (r["cost_usd"] or 0), 4)
    return out

return {
    "generated_at": now_iso,
    "thresholds": th,
    "summary": {
        "needs_review_pending": len(needs_review),
        "needs_review_stale": sum(1 for r in needs_review if r.get("stale")),
        "failed": len(failed),
        "expensive": len(expensive),
        "zombie": len(zombie),
        "scanned": len(runs),
    },
    "needs_review": needs_review[:cap],
    "failed": failed[:cap],
    "expensive": expensive[:cap],
    "zombie": zombie[:cap],
    "expensive_cost_by_model": cost_by(lambda r: r.get("model"), expensive),
    "expensive_cost_by_runtime": cost_by(lambda r: r.get("runtime"), expensive),
}
```

**Casos borde (cubrir en test):**
- `runs == []` → todas las listas vacías, summary en 0, no crashea.
- `metadata` ausente (`None`) o `cost` ausente → no entra a `expensive`, no crashea.
- `cost` como dict `{"total": ...}` y como float → ambos coerce a número.
- `started_at == None` → `age = None` → no entra a zombie; `age_days = None` y `stale=False`.
- `status` con mayúsculas (`"Needs_Review"`) → normalizado por `.lower()`.
- más de `max_rows_per_bucket` runs en un bucket → truncado al cap (summary refleja el
  total real, las listas el cap).
- `runtime` ausente en metadata → cae a `agent_type`, luego `"unknown"`.

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_operational_health.py`
Casos (nombres exactos):
- `test_empty_runs_returns_empty_buckets`
- `test_needs_review_bucket_and_stale_flag`
- `test_failed_bucket_uses_failure_kind_and_defaults_unknown`
- `test_expensive_bucket_respects_threshold`
- `test_coerce_cost_handles_float_and_dict_and_missing`
- `test_zombie_bucket_detects_old_running`
- `test_status_is_case_insensitive`
- `test_bucket_caps_at_max_rows_per_bucket`
- `test_expensive_cost_by_model_and_runtime`
- `test_age_minutes_handles_none_and_unparseable`

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" ; .\.venv\Scripts\python.exe -m pytest tests/test_operational_health.py -q
```

**Criterio de aceptación BINARIO:** el comando anterior termina con `0 failed` y los 10
tests `passed`.

**Flag que la protege:** ninguno a este nivel (función pura, sin efecto observable hasta
F2). Default seguro = no se invoca desde ningún lado todavía.

**Impacto por runtime:** ninguno (función pura, agnóstica). Fallback Codex/Claude/Copilot:
no aplica — no se ejecuta nada de runtime aquí.

**Trabajo del operador: ninguno.**

---

### F1 — Flag declarativo en el registry

**Objetivo (1 frase):** registrar el flag que gobierna el endpoint para que aparezca en el
panel de flags del arnés sin tocar frontend. **Valor:** control opt-out coherente con el
resto del arnés.

**Archivo a EDITAR:** `Stacky Agents/backend/services/harness_flags.py`

**Símbolo EXACTO a agregar** dentro de `FLAG_REGISTRY` (`:29`), como nueva `FlagSpec`:
```python
FlagSpec(
    key="STACKY_OPERATIONAL_HEALTH_ENABLED",
    type="bool",
    label="Panel de salud operativa",
    description="Plan 46 — Triage solo-lectura de runs (needs_review/failed/caras/zombie). OFF = endpoint 404 y card oculta.",
    group="global",
    env_only=True,
),
```

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_harness_flags_op_health.py`
Casos (nombres exactos):
- `test_operational_health_flag_is_registered` — `STACKY_OPERATIONAL_HEALTH_ENABLED` está
  en `[f.key for f in FLAG_REGISTRY]`.
- `test_operational_health_flag_is_bool_and_global` — su `type == "bool"` y
  `group == "global"` y `env_only is True`.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" ; .\.venv\Scripts\python.exe -m pytest tests/test_harness_flags_op_health.py -q
```

**Criterio de aceptación BINARIO:** 2 tests `passed`, `0 failed`.

**Flag que la protege:** este ES el flag. Default seguro: `STACKY_OPERATIONAL_HEALTH_ENABLED`
no seteado → `os.getenv(..., "true")` ⇒ habilitado (feature solo-lectura, default true por
G5). Para desactivar: `STACKY_OPERATIONAL_HEALTH_ENABLED=false`.

**Impacto por runtime:** ninguno. **Trabajo del operador: ninguno** (opt-out por env si lo
desea).

---

### F2 — Endpoint lazy solo-lectura (query helper + wiring del agregador)

**Objetivo (1 frase):** exponer `GET /api/diag/operational-health` que consulta las N runs
recientes, las normaliza a dicts (con `project` inyectado) y llama al agregador puro.
**Valor:** convierte el núcleo puro en una vista consumible, sin tocar el hot-path.

**Archivo a EDITAR:** `Stacky Agents/backend/api/diag.py` (agregar un endpoint nuevo al
blueprint `bp` existente; **no** crear blueprint nuevo).

**Símbolos EXACTOS a agregar:**
- helper de query `def _recent_executions(session, limit: int) -> list` — `SELECT` de
  `AgentExecution` ordenado por `started_at DESC` con `LIMIT limit`. **C4 — DEBE usar
  `joinedload(AgentExecution.ticket)`** para traer el `Ticket` en la misma query y evitar
  N+1 (patrón canónico ya usado en `services/harness_health.py:236`). **Solo SELECT** (G4).
  Forma EXACTA (copiar el patrón de `harness_health.py:236`):
```python
from sqlalchemy import select
from sqlalchemy.orm import joinedload

def _recent_executions(session, limit: int) -> list:
    """C4: joinedload evita N+1 al leer ex.ticket.stacky_project_name en el loop."""
    stmt = (
        select(AgentExecution)
        .options(joinedload(AgentExecution.ticket))   # carga el Ticket en la misma query
        .order_by(AgentExecution.started_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())
```
- endpoint:
```python
@bp.get("/operational-health")
def operational_health():
    """Plan 46 — Triage solo-lectura de runs recientes. No muta nada."""
    import os
    if os.getenv("STACKY_OPERATIONAL_HEALTH_ENABLED", "true").lower() == "false":
        return jsonify({"ok": False, "error": "disabled"}), 404

    from datetime import datetime
    from services.operational_health import aggregate_operational_health
    # C1: session_scope, AgentExecution, Ticket y request/jsonify YA están importados a
    # nivel módulo en diag.py (:23, :24, :21). C6: EXECUTION_TIMEOUT_MINUTES también
    # (:31) — NO re-importar localmente; usar el del módulo.

    # C2: parse defensivo de limit (no romper con ?limit=abc)
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, 500))

    # parámetros opcionales con defaults seguros
    thresholds = {}
    # [ADICIÓN ARQUITECTO] zombie default = timeout real del sistema, no un 30 mágico
    thresholds["zombie_minutes"] = EXECUTION_TIMEOUT_MINUTES
    for k in ("cost_usd", "zombie_minutes", "needs_review_stale_days"):
        v = request.args.get(k)
        if v is not None:
            try:                                     # C2: param malo → ignorar, no 500
                thresholds[k] = float(v) if k == "cost_usd" else int(float(v))
            except (TypeError, ValueError):
                pass

    rows = []
    with session_scope() as session:                 # C1: patrón real de diag.py:42
        execs = _recent_executions(session, limit)    # C4: joinedload → sin N+1
        for ex in execs:
            d = ex.to_dict(include_output=False)
            d["project"] = ex.ticket.stacky_project_name if ex.ticket else None
            rows.append(d)

    result = aggregate_operational_health(
        rows, now_iso=datetime.utcnow().isoformat(), thresholds=thresholds or None
    )
    result["ok"] = True
    return jsonify(result)
```
> NOTA para el implementador (C1/C6): `session_scope`, `AgentExecution`, `Ticket`,
> `request`, `jsonify` y `EXECUTION_TIMEOUT_MINUTES` YA están importados a nivel módulo
> en `diag.py` (`:23`, `:24`, `:21`, `:31`). NO existe `get_session` y NO hay que
> re-importar `EXECUTION_TIMEOUT_MINUTES` dentro de la función. Copiar el patrón de
> `diag.py` tal cual; no inventar. **[ADICIÓN ARQUITECTO] (C5):** sembrar
> `thresholds["zombie_minutes"] = EXECUTION_TIMEOUT_MINUTES` ANTES de leer los query
> params hace que el override del operador (si lo pasa) siga ganando, pero el default
> efectivo coincide con el timeout real del sistema (`EXECUTION_TIMEOUT_MINUTES = 120`,
> `ticket_status.py:40`) que ya se usa para declarar una run vencida — una sola fuente
> de verdad, sin número mágico, sin trabajo extra al operador. El `30` que figura en
> `DEFAULT_THRESHOLDS` (servicio puro) es solo el fallback de la función aislada cuando
> NADIE le pasa thresholds (el servicio puro, por diseño G1, no importa nada del
> sistema); en producción el endpoint SIEMPRE siembra el valor real.

**Casos borde:**
- flag en `false` → 404 con `{"ok": false, "error": "disabled"}`.
- sin runs → 200 con buckets vacíos.
- `limit` fuera de rango → capeado a `[1, 500]`.
- **C2** — `limit` no numérico (`?limit=abc`) → parse defensivo cae a `200` (NO 500).
- thresholds inválidos (no numéricos, `?cost_usd=abc`) → el parse en try ignora ese param y
  sigue con default (no romper el endpoint por un query param malo).

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_operational_health_endpoint.py`
Patrón de mock (ver memoria `stacky-plan28-lifecycle`: importar `db` a nivel módulo, parchear
en el módulo origen con lazy imports). Casos (nombres exactos):
- `test_endpoint_returns_404_when_flag_disabled` — monkeypatch
  `os.environ["STACKY_OPERATIONAL_HEALTH_ENABLED"]="false"` → status 404.
- `test_endpoint_returns_buckets_with_seeded_runs` — sembrar 3 `AgentExecution` (1
  needs_review, 1 error, 1 running viejo) en DB de test → 200 y cada bucket con su run.
- `test_endpoint_injects_project_from_ticket` — la run sembrada referencia un `Ticket` con
  `stacky_project_name="Pacifico"` → la fila tiene `project == "Pacifico"`.
- `test_endpoint_respects_limit_cap` — `?limit=9999` → no crashea, capeado.
- `test_endpoint_ignores_bad_threshold_param` — `?cost_usd=abc` → 200 con default.
- `test_endpoint_handles_non_numeric_limit` — **C2**: `?limit=abc` → 200 (no 500), cae a default 200.
- `test_endpoint_does_not_trigger_n_plus_one` — **[ADICIÓN ARQUITECTO v3] (C4):** sembrar
  5 `AgentExecution` cada una con su `Ticket`; suscribir el evento `after_cursor_execute`
  de SQLAlchemy (`event.listen(engine, "after_cursor_execute", counter)`) durante el GET y
  afirmar que el nº de SELECT a `agent_executions`/`tickets` es **constante** (no crece con
  el nº de filas: 1 SELECT con joinedload, NO 1+N). Guarda contra futuras regresiones que
  quiten el `joinedload`.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend" ; .\.venv\Scripts\python.exe -m pytest tests/test_operational_health_endpoint.py -q
```

**Criterio de aceptación BINARIO:** 7 tests `passed`, `0 failed`; y `GET /api/diag/operational-health`
con la app levantada devuelve `200` y un JSON con claves `summary`, `needs_review`,
`failed`, `expensive`, `zombie` (o `404` si el flag está en `false`).

**Flag que la protege:** `STACKY_OPERATIONAL_HEALTH_ENABLED` (F1). Default true; OFF ⇒ 404.

**Impacto por runtime:** el endpoint es agnóstico — lee filas que las 3 runtimes ya
escriben en `agent_executions`. **Fallback por runtime:**
- *Codex CLI*: si una run Codex no escribió `metadata.runtime`, `_runtime_of` cae a
  `agent_type` → la run igual aparece, sin perderse.
- *Claude Code CLI*: ídem; runs zombie (timeout) aparecen en el bucket `zombie` por
  `status="running"` + antigüedad (cubre el síntoma de `claude-cli-zombie-sessions`).
- *GitHub Copilot Pro*: ídem; si no reporta `cost`, simplemente no entra a `expensive`
  (degradación controlada: ausencia de costo ⇒ no se inventa, no se rompe).

**Trabajo del operador: ninguno.**

---

### F3 — Card frontend solo-lectura en DiagnosticsPage

**Objetivo (1 frase):** mostrar las 4 listas de triage con enlace a cada run, debajo del
`HarnessHealthCard`, solo si el endpoint responde 200. **Valor:** el operador ve qué
atender sin barrer la lista de ejecuciones.

**Archivos a CREAR/EDITAR:**
- CREAR `Stacky Agents/frontend/src/components/OperationalHealthCard.tsx`
- CREAR `Stacky Agents/frontend/src/components/OperationalHealthCard.module.css`
- EDITAR `Stacky Agents/frontend/src/api/endpoints.ts` — agregar helper.
- EDITAR `Stacky Agents/frontend/src/pages/DiagnosticsPage.tsx` — montar la card.

**Símbolos EXACTOS:**

En `endpoints.ts` (nuevo objeto, junto a `Metrics`/`Reports`):
```ts
export interface OperationalHealthRow {
  id: number; ticket_id: number | null; agent_type: string | null;
  runtime: string; project: string | null; started_at: string | null; status: string;
  age_days?: number | null; stale?: boolean;
  failure_kind?: string; error_message?: string | null;
  cost_usd?: number; model?: string | null; age_minutes?: number;
}
export interface OperationalHealthReport {
  ok: boolean; generated_at: string;
  summary: { needs_review_pending: number; needs_review_stale: number;
             failed: number; expensive: number; zombie: number; scanned: number; };
  needs_review: OperationalHealthRow[]; failed: OperationalHealthRow[];
  expensive: OperationalHealthRow[]; zombie: OperationalHealthRow[];
  expensive_cost_by_model: Record<string, number>;
  expensive_cost_by_runtime: Record<string, number>;
}
export const OperationalHealth = {
  get: () => api.get<OperationalHealthReport>("/api/diag/operational-health"),
};
```

En `OperationalHealthCard.tsx` (patrón `useEffect + api.get`, igual que
`HarnessHealthCard.tsx:9`):
```tsx
// fetch en useEffect; si la respuesta es 404 (flag off) o error → setHidden(true) y
// la card retorna null (NO se muestra). G5: con OFF la UI no aparece.
// Render: 4 secciones (Por revisar / Fallidas / Caras / Zombies), cada una con su count
// del summary y una tabla compacta de filas. Cada fila enlaza a la ejecución existente
// (reusar la ruta/handler que ya usa el panel de ejecuciones; si hay un drawer por
// execution id, enlazar a él — NO crear vista nueva de detalle).
// Badges: stale=true → badge "envejecida"; zombie → badge con age_minutes.
// Si todos los counts == 0 → mostrar estado "Todo en orden" (no tabla vacía).
```

En `DiagnosticsPage.tsx`: importar y montar `<OperationalHealthCard />` inmediatamente
**después** de `<HarnessHealthCard />` (`:198`).

**Casos borde:**
- endpoint 404 (flag off) → la card no se monta (retorna `null`).
- error de red → `null` (no romper la página).
- todos los buckets vacíos → card visible con "Todo en orden".
- runs sin `project`/`model` → mostrar "—".

**Tests PRIMERO:** no hay vitest (confirmado). Validación = compilación de tipos estricta.

**Comando exacto:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" ; npx tsc --noEmit
```

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` termina con **0 errores**; y al
abrir DiagnosticsPage con el flag ON, la card aparece bajo HarnessHealthCard; con el flag
en `false` (endpoint 404), la card NO aparece.

**Flag que la protege:** misma `STACKY_OPERATIONAL_HEALTH_ENABLED`; el front se apaga solo
al recibir 404 (no necesita conocer el flag).

**Impacto por runtime:** el front es agnóstico; muestra `runtime` por fila tal cual lo
devuelve el backend. **Fallback:** si `runtime`/`cost`/`model` faltan, renderiza "—".

**Trabajo del operador: ninguno** (la card es informativa; default visible).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | Query pesada si la tabla es enorme | **C7:** la mitigación real es `LIMIT` (default 200, cap 500) + **lazy** (solo al pedir el endpoint) + **`joinedload` para evitar N+1** (C4, patrón `harness_health.py:236`). Nota: el índice `ix_exec_status_started` (status, started_at) NO acelera este `ORDER BY started_at DESC` sin filtro por status; no se invoca como mitigación. |
| R2 | Shapes inconsistentes de `metadata.cost` entre runtimes | `_coerce_cost` defensivo (float/dict/ausente). Test `test_coerce_cost_*`. |
| R3 | Solaparse con el digest (doc 23) y con Plan 44 | 46 es triage **por-run accionable** (lista runs concretas + enlace), no tasas agregadas ni grounding. Sección 2 lo delimita. |
| R4 | Falsos zombies (running legítima de larga duración) | **C5:** umbral configurable (`zombie_minutes`), **default efectivo = `EXECUTION_TIMEOUT_MINUTES` (120 min, el timeout real del sistema)**, no un 30 mágico. Es **informativo**, no acciona (G6). El operador juzga. |
| R5 | Tentación de agregar botón "cancelar/reintentar" | Prohibido en este plan (G6). El cancel ya existe en ActiveRunsPanel; 46 no lo duplica ni automatiza. |
| R6 | Frozen deploy no toma el flag | flag `env_only` leído en call-time vía `os.getenv` (igual que `health()`); se hornea con el resto del `.env` del deploy (ver memoria `harness-default-baked-in-deploy`). |

## 6. Fuera de scope

- Cualquier acción mutante (cancelar/reintentar/reasignar runs) — viola G6.
- Recalcular tasas/costos agregados de management — eso es el digest (doc 23).
- Calidad de grounding de épicas / sugeridor de diccionario — eso es Plan 44.
- Pre-vuelo / intención antes de ejecutar — eso es Plan 41.
- Persistir señales en DB o correr el agregador en background — viola G3.
- Notificaciones push/email — fuera de alcance (el panel es pull, solo-lectura).
- Cambiar el modal/selector/runner/publicación de épicas (frente 42/43 saturado).

## 7. Glosario, orden de implementación y DoD

**Glosario:**
- *Triage*: clasificar runs recientes en categorías que requieren (o no) atención del
  operador, sin actuar sobre ellas.
- *Zombie/stalled*: run con `status="running"` y antigüedad mayor al umbral
  `zombie_minutes` (**default efectivo = `EXECUTION_TIMEOUT_MINUTES` = 120 min**, el
  timeout real del sistema; síntoma de sesión CLI colgada).
- *Run cara*: run cuyo costo normalizado ≥ umbral `cost_usd`.
- *Stale needs_review*: run en `needs_review` con antigüedad ≥ `needs_review_stale_days`.
- *Agregador puro*: función sin I/O que transforma dicts → dict.

**Orden de implementación (estricto, TDD por fase):**
1. F0 — servicio puro + sus 10 tests (todo en memoria; sin DB).
2. F1 — flag en registry + 2 tests.
3. F2 — endpoint + query helper (con `joinedload`, C4) + 7 tests (con DB de test).
4. F3 — card + helper de endpoints + montaje; `tsc --noEmit`.

**Definition of Done (binario):**
- [ ] `pytest tests/test_operational_health.py -q` → 0 failed (10 passed).
- [ ] `pytest tests/test_harness_flags_op_health.py -q` → 0 failed (2 passed).
- [ ] `pytest tests/test_operational_health_endpoint.py -q` → 0 failed (7 passed, incl. anti-N+1).
- [ ] `npx tsc --noEmit` (frontend) → 0 errores.
- [ ] Con flag ON: `GET /api/diag/operational-health` → 200 con las 5 claves de buckets.
- [ ] Con `STACKY_OPERATIONAL_HEALTH_ENABLED=false`: endpoint 404 y card oculta.
- [ ] No se modificó ningún endpoint/modelo/columna existente (solo se agregó).
- [ ] Ningún `INSERT/UPDATE/DELETE` en el código nuevo (grep limpio).

**Trabajo del operador, total: ninguno** (feature solo-lectura, default visible, opt-out por
env si lo desea).
