# Plan 142 — Centro de Costos + Codeburn: KPIs de tokens y USD multidimensionales

> Estado: CRITICADO v1→v2 · VEREDICTO: APROBADO-CON-CAMBIOS (2026-07-15)
> Rama sugerida de trabajo: `plan-142-centro-de-costos`
> Flag maestra: `STACKY_COST_CENTER_ENABLED` (default **ON**, activable/desactivable desde UI) — ver §3.7 y F3 para la justificación del cambio v2 (directiva operador: flags nuevas default ON salvo excepción dura; una vista read-only no califica para ninguna de las 4).
> Runtime: 3 runtimes con paridad y fallback explícito (claude_code_cli / codex_cli / github_copilot)

---

## CHANGELOG v1→v2 (crítica adversarial)

- **C1 (IMPORTANTE):** flag maestra pasa de **OFF → ON**. Una vista read-only no bypasea revisión humana, no es destructiva, no requiere prerequisito externo ni reduce seguridad → no aplica ninguna de las 4 excepciones duras; la directiva del operador manda default ON. Su vecino de misma categoría (`STACKY_EXECUTION_HISTORY_ENABLED`) ya es default `"true"`. F3 reescrita al patrón canónico (default=True + `_CURATED_DEFAULTS_ON` + config `"true"`).
- **C2 (IMPORTANTE):** dependencia de orden explícita: F6 (UI) **requiere** Plan 138 (primitivas/tokens), 140 (estados) y 141 (anti-drift) IMPLEMENTADOS. F0–F5 (backend + lógica pura TS) son implementables **independientemente** de esa serie. Se agrega **gate de prerequisito** a F6.
- **C3 (IMPORTANTE):** F0 tenía dos líneas `model = ...` duplicadas/contradictorias en el bloque de código (un modelo menor copiaría la incorrecta). Se dejó UNA sola línea correcta.
- **C4 (IMPORTANTE):** `_parse_filters` era un stub `...`. Se especifica parsing exacto y comportamiento ante fecha malformada.
- **C5 (IMPORTANTE):** `previous_period`/`burn_with_comparison`/`filters_echo` sólo aparecían en una nota en prosa. Se congelan contratos + semántica (from/to explícito vs days) + tests nombrados.
- **C6 (IMPORTANTE):** el seeding de `test_cost_center_api.py` omitía columnas NOT NULL de `AgentExecution` + su `Ticket` padre (riesgo `IntegrityError` en modelos menores). Se ancla el patrón de seeding a un test existente + factory mínima.
- **C7/C8/C9/C10 (MENOR):** robustez de sesión (extracción dentro del `with`), `outerjoin` para no descartar ejecuciones huérfanas, caveat del cap `_MAX_ROWS` con filtros de metadata, y guarda de `_as_float` en F0.
- **[ADICIÓN ARQUITECTO]:** nueva fase opcional **F8 — Auditoría de reconciliación read-only** que **cuantifica** la divergencia R3 (legacy `_execution_costs` vs `extract_cost_row` canónico), incluyendo `codex_invisible_usd`. Convierte el landmine verificado en valor medible y de-riesga la migración futura, sin tocar los endpoints legacy.

---

## 1. Título, objetivo e impacto

**Centro de Costos** es una vista **read-only, aditiva y activada por default (desactivable desde la UI)** que consolida TODA la telemetría de costo que Stacky ya persiste por ejecución (`AgentExecution.metadata_dict`) en un tablero **muy visual, ordenable y filtrable** de KPIs multidimensionales de USD y tokens, más un **"codeburn"** (burn-rate temporal de USD/tokens por bucket hora/día/semana) construido **nativamente sobre la propia telemetría de Stacky** (source of truth), sin dependencias externas obligatorias.

El operador hoy tiene los datos de costo **dispersos** en cuatro lugares que no conversan entre sí:
- `backend/harness/telemetry.py` → `RunTelemetry` (campos canónicos por run).
- `backend/harness/pricing.py` → `estimate_cost()` (fallback cuando el CLI no reporta costo).
- `backend/api/metrics.py` → `_execution_costs()` + `/ticket-costs` + `/project-costs` (parciales, y con una **divergencia real** documentada en §5).
- `backend/api/executions.py` → lista por ejecución con `cost_usd`, `tokens_in`, `tokens_out`.

No existe un **centro unificado** ni una **serie temporal de burn**. Este plan cierra ese gap sin capturar ni un solo dato nuevo: todo se **deriva** de lo ya registrado.

**KPI/impacto medible del plan (Definición de Éxito):**
- El operador ve, en **una sola pantalla**, el costo USD total (reportado + estimado, separados), tokens totales (in/out/cache), costo por runtime/modelo/agente/ticket/proyecto/día, top-N runs más caros y el burn temporal — **sin correr ninguna acción ni configurar nada** (con la flag ON).
- **Cero** costo de tokens de LLM: toda la agregación es determinista en Python sobre la DB local. Ninguna llamada a modelo.
- **Cero** dependencias nuevas (frontend y backend): charts en **SVG propio**, sin librería de gráficos.
- Latencia de cada endpoint < 400 ms para ventanas de 30 días en la escala mono-operador (una sola query SQL indexada + agregación en memoria acotada por cap de filas).

---

## 2. Por qué ahora / gap que cierra

El sustrato de costo YA existe y está **verificado** (archivo:símbolo):

| Fuente | Qué aporta | Evidencia |
|---|---|---|
| `harness/telemetry.py` | `RunTelemetry` con `total_cost_usd`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cost_estimated` (bool). `persist()` lo escribe en `metadata["harness_telemetry"]` para **ambos** runtimes CLI; claude además mantiene `metadata["claude_telemetry"]` (legacy). | `telemetry.py:28-50, 122-142` |
| `harness/pricing.py` | `estimate_cost(model, in, out)` con `DEFAULT_PRICES` por prefijo de modelo; costo REPORTADO siempre gana, sin match → `None` (nunca 0.0). | `pricing.py:24-98` |
| `api/metrics.py` | Blueprint `metrics` (url_prefix `/metrics`, montado bajo `/api`), `_execution_costs()`, endpoints `/ticket-costs`, `/project-costs`, `/agent-comparison`, `/harness-health`. | `metrics.py:29, 50-176` |
| `api/executions.py` | Lista por ejecución: `cost_usd`, `tokens_in`, `tokens_out`, `model`, `runtime`, `status`, `duration_ms`, `started_at`, `finished_at`(=`completed_at`), `ticket_id`, `agent_type`. | `executions.py:353-374` |
| `models.py` | `AgentExecution` con `metadata_dict` (property), `started_at`, `completed_at` (¡no existe `finished_at` como columna!), `duration_ms()`, índices `ix_exec_status_started (status, started_at)` y `ix_exec_ticket_started`. | `models.py:207-278` |

**Gap:** la data está, pero (a) no hay una vista única multidimensional, (b) no hay burn temporal, (c) la extracción de costo está **duplicada e inconsistente** entre `metrics.py` y `executions.py` (ver §5, C-divergencia), y (d) no se distingue costo **reportado vs estimado vs nominal (Copilot suscripción)**. Este plan resuelve las cuatro cosas con una capa de extracción canónica única.

---

## 3. Principios y guardarraíles (NO negociables — codificados por fase)

1. **Read-only / aditivo.** Ninguna escritura a DB, ADO, GitLab ni disco (salvo lectura opcional de un JSONL externo en F7). La vista se agrega detrás de la flag maestra `STACKY_COST_CENTER_ENABLED` **default ON** (C1). Backward-compatible: con la flag OFF (el operador puede apagarla desde la UI), el sistema se comporta EXACTAMENTE como hoy; con ON (default) aparece una tab nueva read-only. Nada cambia en flujos existentes en ningún caso.
2. **Paridad de 3 runtimes con fallback explícito por ítem** (§4 F0, tabla de clasificación de costo):
   - `claude_code_cli`: reporta `total_cost_usd` real → **cost_kind = "reported"**.
   - `codex_cli`: típicamente reporta tokens, no USD → `pricing.estimate_cost` → **cost_kind = "estimated"** (`cost_estimated=True`).
   - `github_copilot`: suscripción plana → **cost_kind = "nominal"**; se calcula sólo como *hint* vía pricing y **NUNCA** se suma al gasto facturable. La UI lo etiqueta "nominal (suscripción)".
3. **Human-in-the-loop innegociable.** El Centro de Costos **sólo visualiza/informa**. No decide, no enruta, no cancela, no aplica caps. Cero autonomía.
4. **Mono-operador sin auth.** Nada de RBAC ni multiusuario. `current_user` sigue siendo un header sin validar; no se construye control de acceso.
5. **No degradar performance/seguridad/estabilidad/DX.** Una sola query SQL por endpoint con filtros empujados a SQL (fecha/estado/agente/ticket/proyecto), cap duro de filas, agregación en memoria con funciones **puras** y testeables. Sin N+1. Sin traer todo al front (bucketing y agregación en backend).
6. **Reusar, no reinventar.** Se reusa `pricing.estimate_cost`, la telemetría existente, el patrón de endpoints de `metrics.py`, el sistema de diseño v2 (Plan 138: tokens semánticos + primitivas UI), los estados universales (Plan 140: skeletons/vacío/error) y el gate anti-drift de color (Plan 141). **Prohibido** color hardcodeado en el frontend.
7. **Toda flag activable/desactivable desde UI, default ON (C1).** Se agrega a `FLAG_REGISTRY` (con `default=True`) + `_CATEGORY_KEYS` + `_CURATED_DEFAULTS_ON` + `config.py` (`"true"`), con lo cual el panel genérico `HarnessFlagsPanel` la muestra y togglea automáticamente (no sólo env var). Justificación del default ON: la vista es read-only, no bypasea revisión humana, no es destructiva/irreversible, no depende de ningún prerequisito externo garantizado, y no reduce seguridad → **ninguna de las 4 excepciones duras aplica**, por lo que la directiva del operador (flags nuevas default ON) manda. Evidencia de coherencia: `STACKY_EXECUTION_HISTORY_ENABLED` (misma categoría `observabilidad_notif`) ya es default `"true"` en `config.py:500`.
8. **Sin datos nuevos.** Todo KPI se deriva de campos ya registrados. Si un run no tiene costo ni tokens, se cuenta en `runs_without_cost` y se muestra **"n/d"** — nunca se inventa 0.0.

---

## 4. Fases F0..F7

> **Convención de tests backend (env real del repo):** correr **por archivo** con el intérprete del venv py3.13 del backend. La suite completa está contaminada por orden (ver memoria del repo) → **nunca** `pytest` a secas.
> Comando plantilla (PowerShell, desde la raíz del repo):
> ```powershell
> $py = if (Test-Path "Stacky Agents\backend\.venv\Scripts\python.exe") { "Stacky Agents\backend\.venv\Scripts\python.exe" } else { "Stacky Agents\backend\venv\Scripts\python.exe" }
> & $py -m pytest "Stacky Agents/backend/tests/<ARCHIVO_DE_TEST>.py" -q
> ```
> **Convención de tests frontend:** `@testing-library/react` y `jsdom` **NO** están instalados (gap estructural confirmado). Por lo tanto **todo test de vitest apunta a funciones PURAS de TS** (formatters, CSV, sort/filter, math de SVG), **no** a render de React. El gate estructural de los `.tsx` es `npm run build` (que corre `tsc --noEmit`).
> Comandos frontend (desde `Stacky Agents/frontend`):
> ```powershell
> npx vitest run src/lib/__tests__/<ARCHIVO>.test.ts   # lógica pura
> npm run build                                          # tsc --noEmit + vite build (gate .tsx)
> ```

---

### F0 — Extractor canónico de costo/telemetría (linchpin, PURO, sin DB)

**Objetivo (1 frase):** una única función pura que, dado el `metadata_dict` de una ejecución, devuelva costo+tokens+clasificación reconciliando las 3 fuentes (harness_telemetry / claude_telemetry / top-level), eliminando la duplicación e inconsistencia actual.

**Valor:** fuente de verdad única para TODOS los KPIs; testeable en aislamiento; corrige la divergencia de §5.

**Archivo a crear:** `Stacky Agents/backend/services/cost_analytics.py`

**Símbolos EXACTOS a definir:**
```python
# services/cost_analytics.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from harness.pricing import _load_prices, estimate_cost, _MTOK

# Runtimes de suscripción plana: su costo NUNCA es facturable, sólo hint "nominal".
_SUBSCRIPTION_RUNTIMES: frozenset[str] = frozenset({"github_copilot"})

@dataclass
class CostRow:
    runtime: str | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cache_read_tokens: int | None
    cost_usd: float | None          # mejor número de costo disponible (o None si n/d)
    cost_kind: str                  # "reported" | "estimated" | "nominal" | "unknown"
    cache_savings_usd: float | None # ahorro ESTIMADO por cache reads (o None)

def input_price_per_mtok(model: str | None) -> float | None:
    """Precio input USD/Mtok del prefijo más largo que matchea. None si no matchea."""
    if not model:
        return None
    prices = _load_prices()
    best = None; best_len = -1
    for prefix, (in_price, _out) in prices.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best = in_price; best_len = len(prefix)
    return best

def _first_int(*vals) -> int | None:
    for v in vals:
        if v is not None:
            try: return int(v)
            except (TypeError, ValueError): continue
    return None

def extract_cost_row(md: dict | None) -> CostRow:
    md = md or {}
    ht = md.get("harness_telemetry") if isinstance(md.get("harness_telemetry"), dict) else {}
    ct = md.get("claude_telemetry") if isinstance(md.get("claude_telemetry"), dict) else {}
    ct_usage = ct.get("usage") if isinstance(ct.get("usage"), dict) else {}

    runtime = md.get("runtime") or ht.get("runtime")
    # C3 — UNA sola línea correcta (no copiar variantes). Precedencia: top-level > harness_telemetry.raw.model.
    _ht_raw = ht.get("raw") if isinstance(ht.get("raw"), dict) else {}
    model = md.get("model") or _ht_raw.get("model")

    tokens_in = _first_int(ht.get("input_tokens"), ct_usage.get("input_tokens"), md.get("tokens_in"))
    tokens_out = _first_int(ht.get("output_tokens"), ct_usage.get("output_tokens"), md.get("tokens_out"))
    cache_read = _first_int(ht.get("cache_read_tokens"), ct_usage.get("cache_read_input_tokens"))

    # raw_cost + is_estimated según precedencia (harness > claude legacy > top-level)
    raw_cost = None; is_estimated = False
    if ht.get("total_cost_usd") is not None:
        raw_cost = _as_float(ht.get("total_cost_usd")); is_estimated = bool(ht.get("cost_estimated"))
    elif ct.get("total_cost_usd") is not None:
        raw_cost = _as_float(ct.get("total_cost_usd")); is_estimated = False   # legacy claude = reportado
    elif md.get("cost_usd") is not None:
        raw_cost = _as_float(md.get("cost_usd")); is_estimated = False

    # Clasificación de cost_kind (mutuamente excluyente por run → sin doble conteo)
    if runtime in _SUBSCRIPTION_RUNTIMES:
        cost = raw_cost if raw_cost is not None else estimate_cost(model, tokens_in, tokens_out)
        kind = "nominal"
    elif raw_cost is None:
        est = estimate_cost(model, tokens_in, tokens_out)
        if est is not None: cost, kind = est, "estimated"
        else: cost, kind = None, "unknown"
    elif is_estimated:
        cost, kind = raw_cost, "estimated"
    else:
        cost, kind = raw_cost, "reported"

    # Ahorro estimado por cache reads: cache_read_tokens * input_price / 1e6
    savings = None
    ip = input_price_per_mtok(model)
    if cache_read and ip is not None:
        savings = round(cache_read * ip / _MTOK, 6)

    return CostRow(runtime=runtime, model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                   cache_read_tokens=cache_read, cost_usd=cost, cost_kind=kind, cache_savings_usd=savings)

def _as_float(v):
    try: return float(v)
    except (TypeError, ValueError): return None
```
> **Nota C3:** el bloque ya trae la línea `model` correcta y única (no hay que elegir entre variantes).
> **Nota C10 (borde):** si `harness_telemetry.total_cost_usd` está presente pero es no-numérico, `_as_float` devuelve `None` y **no** se cae a las fuentes legacy: la clasificación trata `raw_cost=None` como `estimated` (si hay tokens+modelo) o `unknown` (nunca 0.0). Degrade intencional y determinista; cubrir con el caso `test_malformed_harness_cost_falls_to_estimated_or_unknown` en F0.

**Casos borde obligatorios:**
- `md = {}` → `CostRow(cost_usd=None, cost_kind="unknown", tokens_*=None, cache_savings_usd=None)`.
- Sólo top-level `cost_usd` presente (claude legacy) → `reported`.
- `harness_telemetry.cost_estimated=True` con `total_cost_usd` → `estimated`.
- `runtime="github_copilot"` con tokens pero sin costo → `nominal` con `cost_usd = estimate_cost(...)`.
- `runtime="codex_cli"` sin `total_cost_usd` pero con tokens y modelo conocido → `estimated`.
- Modelo desconocido y sin costo → `cost_usd=None, cost_kind="unknown"` (NUNCA 0.0).
- `cache_read_tokens=50000`, modelo `claude-sonnet-5` (input 3.0/Mtok) → `cache_savings_usd = round(50000*3.0/1e6,6) = 0.15`.

**Test (crear PRIMERO):** `Stacky Agents/backend/tests/test_cost_analytics_extract.py`
Casos: `test_empty_md_is_unknown`, `test_top_level_cost_is_reported`, `test_harness_estimated_flag`, `test_copilot_is_nominal_never_reported`, `test_codex_tokens_only_estimated`, `test_unknown_model_no_cost_returns_none_not_zero`, `test_cache_savings_computed_from_input_price`, `test_precedence_harness_over_legacy_over_toplevel`, `test_malformed_harness_cost_falls_to_estimated_or_unknown` (C10).

**Comando de verificación:** correr el archivo de test (plantilla arriba). **Criterio binario:** 9/9 verdes.

**Flag que lo protege:** ninguna (módulo puro, sin efecto observable hasta que F2 lo use). **Impacto por runtime:** el propio F0 ES la capa de paridad. **Trabajo del operador: ninguno.**

---

### F1 — Motor de agregación (query acotada + funciones puras summarize/burn/breakdown)

**Objetivo (1 frase):** una capa que hace UNA query SQL acotada con filtros empujados a SQL y tres funciones puras que agregan las filas en summary/burn/breakdown, sin N+1.

**Valor:** performance controlada + lógica de agregación testeable con listas en memoria (sin DB).

**Archivo a editar:** `Stacky Agents/backend/services/cost_analytics.py` (agregar al mismo módulo).

**Símbolos EXACTOS:**
```python
from datetime import datetime, timedelta
from db import session_scope
from models import AgentExecution, Ticket

_MAX_ROWS = 20000  # cap duro de seguridad (mono-operador)

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

@dataclass
class CostFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    days: int = 30                 # usado sólo si date_from/date_to no vienen
    runtime: str | None = None     # filtro Python (metadata)
    model: str | None = None       # filtro Python (metadata), match exacto
    agent_type: str | None = None  # filtro SQL
    ticket_id: int | None = None   # filtro SQL
    project: str | None = None     # filtro SQL (stacky_project_name o project)
    statuses: tuple[str, ...] = () # filtro SQL (csv)
    cost_kind: str | None = None   # filtro Python: reported|estimated|nominal|unknown

def load_records(f: CostFilters) -> list[ExecRecord]:
    """UNA query SQL con filtros de columna + join Ticket. Cap _MAX_ROWS. Filtros
    de runtime/model/cost_kind se aplican en Python (viven en metadata)."""
    now = datetime.utcnow()
    start = f.date_from or (now - timedelta(days=max(1, min(f.days, 365))))
    end = f.date_to or (now + timedelta(seconds=1))
    out: list[ExecRecord] = []
    # C7 — construir los ExecRecord DENTRO del session_scope (robustez; no depender
    # de que expire_on_commit=False para que los atributos sigan legibles tras cerrar).
    # C8 — outerjoin: no descartar ejecuciones huérfanas (ticket borrado) del conteo de costo,
    # coherente con "consolida TODA la telemetría" (§1). tk puede ser None con outerjoin.
    with session_scope() as session:
        q = (session.query(AgentExecution, Ticket)
             .outerjoin(Ticket, Ticket.id == AgentExecution.ticket_id)
             .filter(AgentExecution.started_at >= start, AgentExecution.started_at < end))
        if f.agent_type: q = q.filter(AgentExecution.agent_type == f.agent_type)
        if f.ticket_id:  q = q.filter(AgentExecution.ticket_id == f.ticket_id)
        if f.statuses:   q = q.filter(AgentExecution.status.in_(list(f.statuses)))
        if f.project:
            # el filtro de proyecto excluye huérfanas por definición (no hay ticket) → OK.
            q = q.filter((Ticket.stacky_project_name == f.project) | (Ticket.project == f.project))
        q = q.order_by(AgentExecution.started_at.desc()).limit(_MAX_ROWS)
        for ex, tk in q.all():
            cr = extract_cost_row(ex.metadata_dict)
            if f.runtime and cr.runtime != f.runtime: continue
            if f.model and cr.model != f.model: continue
            if f.cost_kind and cr.cost_kind != f.cost_kind: continue
            out.append(ExecRecord(
                execution_id=ex.id, ticket_id=ex.ticket_id,
                ado_id=getattr(tk, "ado_id", None) if tk else None,
                project=(tk.stacky_project_name or tk.project) if tk else None,
                agent_type=ex.agent_type, status=ex.status, started_at=ex.started_at, row=cr))
    return out

def _billable(kind: str) -> bool:  # reported+estimated son facturables; nominal/unknown NO
    return kind in ("reported", "estimated")

def summarize(records: list[ExecRecord], top_n: int = 10) -> dict: ...
def burn(records: list[ExecRecord], bucket: str = "day") -> dict: ...
def breakdown(records: list[ExecRecord], dimension: str) -> dict: ...
```

**Contrato de `summarize` (dict de salida):**
```json
{
  "runs_total": 0, "runs_with_cost": 0, "runs_without_cost": 0,
  "reported_usd": 0.0, "estimated_usd": 0.0, "nominal_usd": 0.0,
  "billable_usd": 0.0,                        // reported+estimated (nominal EXCLUIDO)
  "pct_estimated": 0.0,                       // estimated_usd / billable_usd (0 si div0)
  "tokens_in_total": 0, "tokens_out_total": 0, "cache_read_total": 0,
  "cache_savings_usd_total": 0.0,             // "ahorro estimado"
  "avg_cost_per_run_usd": 0.0,                // billable_usd / runs_with_cost
  "cost_per_completed_task_usd": 0.0,         // billable_usd / count(status=="completed")
  "tokens_out_in_ratio": 0.0,                 // tokens_out_total / tokens_in_total (0 si div0)
  "top_runs": [ {"execution_id": 1, "ticket_id": 2, "agent_type": "developer",
                 "runtime": "claude_code_cli", "model": "claude-sonnet-5",
                 "cost_usd": 0.42, "cost_kind": "reported", "started_at": "ISO"} ]
}
```
> **Invariante anti-doble-conteo (test obligatorio):** cada run pertenece a exactamente UN `cost_kind`; `billable_usd == reported_usd + estimated_usd` siempre; `nominal_usd` nunca entra en `billable_usd`. Todos los montos `round(x, 6)`.

**Contrato de `burn` (dict de salida):** `bucket ∈ {"hour","day","week"}`.
```json
{
  "bucket": "day",
  "series": [ {"bucket": "2026-07-14", "reported_usd": 0.0, "estimated_usd": 0.0,
               "nominal_usd": 0.0, "billable_usd": 0.0, "cumulative_billable_usd": 0.0,
               "tokens_in": 0, "tokens_out": 0, "runs": 0} ],
  "period_comparison": {"current_billable_usd": 0.0, "previous_billable_usd": 0.0, "delta_pct": 0.0}
}
```
- Clave de bucket: `hour`→`"%Y-%m-%dT%H:00"`, `day`→`"%Y-%m-%d"`, `week`→ISO `"%G-W%V"`. Buckets vacíos intermedios: rellenar con 0 entre min y max (para que el chart no tenga huecos). `cumulative_billable_usd` = acumulado de `billable_usd` en orden temporal.
- `period_comparison`: compara el rango pedido contra el rango previo de **igual longitud** inmediatamente anterior (requiere `load_records` del rango previo; el endpoint hace 2 loads o el service acepta ambos sets). `delta_pct = (cur-prev)/prev*100` (0 si prev==0).

**Contrato de `breakdown` (dict de salida):** `dimension ∈ {"runtime","model","agent_type","ticket","project","day"}`.
```json
{
  "dimension": "runtime",
  "groups": [ {"key": "claude_code_cli", "reported_usd": 0.0, "estimated_usd": 0.0,
               "nominal_usd": 0.0, "billable_usd": 0.0, "tokens_in": 0, "tokens_out": 0,
               "runs": 0} ]
}
```
Ordenado por `billable_usd` desc, luego `runs` desc. `key` para `ticket` = `str(ticket_id)`; para `day` = clave de día.

**Casos borde:** lista vacía → todos los agregados en 0 y `series=[]`, `groups=[]` (no crash, no div0). `dimension` inválida → el endpoint (F2) devuelve 400; la función pura puede asumir válida (el endpoint valida antes).

**Test (crear PRIMERO):** `Stacky Agents/backend/tests/test_cost_analytics_aggregate.py` — construye `ExecRecord` a mano (sin DB) y verifica:
`test_summarize_billable_excludes_nominal`, `test_summarize_no_double_count_invariant`, `test_summarize_div0_guards`, `test_burn_fills_empty_buckets`, `test_burn_cumulative_monotonic`, `test_burn_period_comparison_delta`, `test_breakdown_sorted_desc_by_billable`, `test_breakdown_ticket_and_day_keys`, `test_empty_records_no_crash`, `test_previous_period_explicit_range_shifts_by_span` (C5), `test_previous_period_days_mode_shifts_by_days` (C5), `test_filters_echo_resolves_effective_range` (C5).
> `load_records` (que toca DB) se testea aparte con SQLite in-memory en `test_cost_analytics_load.py` (2 casos: filtros SQL aplicados + cap `_MAX_ROWS`), o se marca `@pytest.mark.skip` si el fixture de DB no está disponible en aislamiento — priorizar los tests PUROS de agregación como gate binario.

**Criterio binario:** 12/12 verdes en `test_cost_analytics_aggregate.py` (incluye los 3 casos C5 de `previous_period`/`filters_echo`). **Trabajo del operador: ninguno.**

---

### F2 — Endpoints backend `/metrics/cost-summary`, `/metrics/cost-burn`, `/metrics/cost-breakdown`

**Objetivo (1 frase):** exponer los tres agregados como endpoints REST gated por flag, reusando el Blueprint `metrics` existente, con contrato JSON congelado.

**Archivo a editar:** `Stacky Agents/backend/api/metrics.py` (agregar 3 rutas + helper de parseo de filtros). **NO** tocar los endpoints existentes.

**Símbolos/rutas EXACTAS:**
```python
from config import config as _cfg
from services import cost_analytics as ca

def _cost_center_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_COST_CENTER_ENABLED", False))

def _parse_date(s: str | None) -> datetime | None:
    """C4 — 'YYYY-MM-DD' → datetime (medianoche UTC). Vacío/None → None.
    Malformada → ValueError (el caller la convierte en 400)."""
    if not s: return None
    return datetime.strptime(s.strip(), "%Y-%m-%d")

def _parse_filters(args) -> ca.CostFilters:
    # C4 — comportamiento EXACTO:
    #   from/to: 'YYYY-MM-DD'. Si vienen y son válidas, ganan sobre days.
    #   Si from/to es malformada → el caller devuelve 400 {"ok":false,"error":"invalid_date"}.
    #   days: int, default 30, clamp 1..365; se ignora si from Y to válidas vinieron.
    #   statuses: csv → tuple[str,...] (vacío si no viene). ticket_id: int o None (no-int → None).
    #   runtime/model/agent_type/project/cost_kind: str o None (str vacío → None).
    date_from = _parse_date(args.get("from"))   # puede lanzar ValueError
    date_to = _parse_date(args.get("to"))       # puede lanzar ValueError
    try: days = int(args.get("days", 30))
    except (TypeError, ValueError): days = 30
    days = max(1, min(days, 365))
    try: ticket_id = int(args.get("ticket_id")) if args.get("ticket_id") else None
    except (TypeError, ValueError): ticket_id = None
    statuses = tuple(s for s in (args.get("status") or "").split(",") if s.strip())
    def _s(k): 
        v = (args.get(k) or "").strip(); return v or None
    return ca.CostFilters(date_from=date_from, date_to=date_to, days=days,
        runtime=_s("runtime"), model=_s("model"), agent_type=_s("agent_type"),
        ticket_id=ticket_id, project=_s("project"), statuses=statuses, cost_kind=_s("cost_kind"))

def _filters_or_error(args):
    """C4 — envuelve _parse_filters; fecha malformada → tupla (None, resp_400)."""
    try:
        return _parse_filters(args), None
    except ValueError:
        return None, (jsonify({"ok": False, "error": "invalid_date"}), 400)

@bp.get("/cost-summary")
def cost_summary():
    if not _cost_center_enabled(): return jsonify({"enabled": False}), 200
    f, err = _filters_or_error(request.args)
    if err: return err
    try: top_n = max(1, min(int(request.args.get("top_n", 10)), 50))
    except (TypeError, ValueError): top_n = 10
    records = ca.load_records(f)
    return jsonify({"ok": True, "enabled": True,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "filters_echo": ca.filters_echo(f),
                    **ca.summarize(records, top_n=top_n)})

@bp.get("/cost-burn")
def cost_burn():
    if not _cost_center_enabled(): return jsonify({"enabled": False}), 200
    bucket = (request.args.get("bucket") or "day").lower()
    if bucket not in ("hour", "day", "week"):
        return jsonify({"ok": False, "error": "invalid_bucket"}), 400
    f, err = _filters_or_error(request.args)
    if err: return err
    records = ca.load_records(f)
    prev = ca.load_records(ca.previous_period(f))   # rango previo de igual longitud
    return jsonify({"ok": True, "enabled": True,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    **ca.burn_with_comparison(records, prev, bucket=bucket)})

@bp.get("/cost-breakdown")
def cost_breakdown():
    if not _cost_center_enabled(): return jsonify({"enabled": False}), 200
    dim = (request.args.get("dimension") or "").lower()
    if dim not in ("runtime", "model", "agent_type", "ticket", "project", "day"):
        return jsonify({"ok": False, "error": "invalid_dimension"}), 400
    f, err = _filters_or_error(request.args)
    if err: return err
    records = ca.load_records(f)
    return jsonify({"ok": True, "enabled": True,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "dimension": dim, **ca.breakdown(records, dim)})
```
**Contratos EXACTOS de los 3 helpers (C5) — agregar a `cost_analytics.py`:**
```python
def filters_echo(f: CostFilters) -> dict:
    """Filtros efectivos resueltos, para que la UI muestre 'estás viendo: …'.
    Devuelve ISO strings y el rango efectivo ya resuelto (no None)."""
    now = datetime.utcnow()
    start = f.date_from or (now - timedelta(days=max(1, min(f.days, 365))))
    end = f.date_to or now
    return {"date_from": start.isoformat(), "date_to": end.isoformat(),
            "days_effective": (end - start).days or f.days,
            "runtime": f.runtime, "model": f.model, "agent_type": f.agent_type,
            "ticket_id": f.ticket_id, "project": f.project,
            "statuses": list(f.statuses), "cost_kind": f.cost_kind}

def previous_period(f: CostFilters) -> CostFilters:
    """Rango previo de IGUAL longitud, inmediatamente anterior. Semántica C5:
    - Si vinieron date_from Y date_to explícitas: span = (date_to - date_from);
      nuevo rango = [date_from - span, date_from).
    - Si NO (se usó days): span = days; nuevo rango = [now-2*days, now-days).
    Conserva TODOS los demás filtros (runtime/model/agent_type/ticket/project/status/cost_kind)."""
    import copy
    now = datetime.utcnow()
    if f.date_from and f.date_to:
        span = f.date_to - f.date_from
        p = copy.replace(f, date_from=f.date_from - span, date_to=f.date_from)
    else:
        d = max(1, min(f.days, 365))
        p = copy.replace(f, date_from=now - timedelta(days=2*d), date_to=now - timedelta(days=d))
    return p

def burn_with_comparison(cur: list[ExecRecord], prev: list[ExecRecord], bucket: str) -> dict:
    """burn(cur, bucket) + period_comparison contra el total billable de prev.
    delta_pct = (cur-prev)/prev*100, 0.0 si prev==0. Todos los montos round(x,6)."""
    b = burn(cur, bucket=bucket)
    cur_bill = round(sum(r.row.cost_usd or 0.0 for r in cur if _billable(r.row.cost_kind)), 6)
    prev_bill = round(sum(r.row.cost_usd or 0.0 for r in prev if _billable(r.row.cost_kind)), 6)
    delta = 0.0 if prev_bill == 0 else round((cur_bill - prev_bill) / prev_bill * 100, 2)
    b["period_comparison"] = {"current_billable_usd": cur_bill,
                              "previous_billable_usd": prev_bill, "delta_pct": delta}
    return b
```
> Nota: `copy.replace` requiere py3.13 (disponible en el venv del backend); alternativa `dataclasses.replace(f, ...)` es idéntica y más portable — usar `dataclasses.replace`.

**Contrato de request (query params, compartidos):**
`from` (YYYY-MM-DD, opcional), `to` (YYYY-MM-DD, opcional), `days` (int, default 30, clamp 1..365, ignorado si vienen from/to), `runtime`, `model`, `agent_type`, `ticket_id`, `project`, `status` (csv), `cost_kind`, `top_n` (solo summary), `bucket` (solo burn), `dimension` (solo breakdown, **requerido**).

**Registro del Blueprint:** ya está registrado (el `bp` de `metrics` se monta en `api/__init__.py`). **No** agregar registro nuevo (gotcha conocido: los blueprints se registran en `api/__init__.py`, no en `app.py`).

**Casos borde:** flag OFF → `{"enabled": false}` HTTP 200 (patrón idéntico a `caps_advisor`). `bucket`/`dimension` inválidos → 400 con `{"ok": false, "error": ...}`. Sin datos en la ventana → `ok:true` con agregados en 0 (no 404).

**Test (crear PRIMERO):** `Stacky Agents/backend/tests/test_cost_center_api.py` (usa el `app.test_client()` del repo).
`test_summary_disabled_returns_enabled_false`, `test_summary_shape_and_billable_excludes_nominal`, `test_burn_invalid_bucket_400`, `test_burn_invalid_date_400` (C4), `test_burn_shape_has_series_and_comparison`, `test_breakdown_invalid_dimension_400`, `test_breakdown_by_runtime_groups`, `test_filters_days_clamped`, `test_filters_runtime_and_cost_kind_applied`.

> **Seeding (C6 — obligatorio, evita `IntegrityError`):** `AgentExecution` tiene columnas `nullable=False`: `ticket_id` (FK a `tickets.id`), `agent_type`, `status`, `input_context_json`, `started_by` (ver `models.py:207-224`). **Primero** crear el `Ticket` padre, **después** las ejecuciones. **Replicar el patrón de un test existente que ya seedea ejecuciones** — usar como plantilla `tests/test_executions_history.py` o `tests/test_metrics_endpoint.py` (ambos crean `Ticket` + `AgentExecution` válidos). Factory mínima:
> ```python
> from db import session_scope
> from models import Ticket, AgentExecution
> import json
> def _seed(session, *, runtime, model, ht=None, top=None, status="completed"):
>     tk = Ticket(ado_id=-999, title="cost-test", project="P", status="active")  # ajustar a los NOT NULL reales de Ticket
>     session.add(tk); session.flush()
>     md = {"runtime": runtime, "model": model}
>     if ht is not None: md["harness_telemetry"] = ht           # p.ej. {"total_cost_usd":0.42,"input_tokens":1000,"output_tokens":200,"cost_estimated":False}
>     if top is not None: md.update(top)                        # p.ej. {"tokens_in":900} para copilot
>     ex = AgentExecution(ticket_id=tk.id, agent_type="developer", status=status,
>                         input_context_json="[]", started_by="test", metadata_json=json.dumps(md))
>     session.add(ex); session.flush(); return ex.id
> ```
> Antes de codear, **confirmar los NOT NULL reales de `Ticket`** leyendo `models.py` (no adivinar); el snippet es guía, no contrato.
> Para habilitar la flag en el test (default ON en v2, pero forzar explícito por si el env la apaga): `monkeypatch.setattr(config, "STACKY_COST_CENTER_ENABLED", True)` (o el patrón de override de config que usan los tests existentes — ver `test_harness_flags.py`).

**Criterio binario:** 9/9 verdes + `test_harness_flags.py` sigue verde tras F3.

**Impacto por runtime + fallback:** los endpoints no ejecutan runtimes; sólo agregan telemetría ya persistida. La paridad la garantiza F0. **Trabajo del operador: NINGUNO (default ON; desactivable desde UI).**

---

### F3 — Flag maestra + config + categoría (patrón triple default ON, activable/desactivable desde UI)

**Objetivo (1 frase):** registrar `STACKY_COST_CENTER_ENABLED` (**default ON**, C1) de forma que el panel genérico de flags la muestre y togglee, y que `config.STACKY_COST_CENTER_ENABLED` sea legible en runtime.

**Patrón canónico default ON (los 3 puntos deben quedar coherentes o rompe el ratchet `test_default_known_only_for_curated`, que exige `known_keys == _CURATED_DEFAULTS_ON` por igualdad de conjuntos — verificado en `test_harness_flags.py:705`):**

**Archivos a editar (3):**
1. `Stacky Agents/backend/services/harness_flags.py`:
   - Agregar al `FLAG_REGISTRY` (dentro del bloque de `observabilidad_notif`, coherente con `STACKY_EXECUTION_HISTORY_ENABLED`):
     ```python
     FlagSpec(
         key="STACKY_COST_CENTER_ENABLED",
         type="bool",
         default=True,   # C1 — default ON (read-only; no aplica ninguna de las 4 excepciones duras)
         label="Centro de Costos (KPIs + Codeburn)",
         description="Plan 142 — Vista read-only de costos USD/tokens multidimensionales y burn temporal. Default ON; desactivable desde la UI.",
         group="observabilidad",
     ),
     ```
   - Agregar la key a `_CATEGORY_KEYS["observabilidad_notif"]` (si no, `test_every_registry_flag_is_categorized` rompe).
   - Agregar la key al set `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`) — **obligatorio** al usar `default=True`, si no rompe `test_default_known_only_for_curated`.
2. `Stacky Agents/backend/config.py`: agregar el atributo con default `"true"` (idioma class-body annotation idéntico a `STACKY_EXECUTION_HISTORY_ENABLED` en `config.py:500`):
   ```python
   STACKY_COST_CENTER_ENABLED: bool = os.getenv("STACKY_COST_CENTER_ENABLED", "true").strip().lower() == "true"
   ```
3. (Opcional F7) atributos de la flag/ruta de importación externa — ver F7 (ésas SÍ default OFF, ver justificación en F7).

**NO regenerar `harness_defaults.env`** (guía permanente de planes previos: el generador hornea del `.env` del deploy y regenerar arrastraría el drift preexistente; la flag es legible por `config.py` sin tocar ese archivo).

**Test:** `Stacky Agents/backend/tests/test_harness_flags.py` (ya existe) — debe seguir verde: `test_every_registry_flag_is_categorized` y `test_default_known_only_for_curated`. Agregar (o confirmar) un caso `test_cost_center_flag_registered_default_on` que verifique `key in FLAG_REGISTRY`, `categorize("STACKY_COST_CENTER_ENABLED") == "observabilidad_notif"`, y que la key esté en `_CURATED_DEFAULTS_ON`.

**Criterio binario:** `test_harness_flags.py` verde completo.

**Activable/desactivable desde UI:** al estar en `FLAG_REGISTRY` + `_CATEGORY_KEYS`, el `HarnessFlagsPanel` genérico (sub-tab Arnés) la renderiza y togglea sin código extra. **Trabajo del operador: NINGUNO (default ON); puede desactivarla con un click si quiere.**

---

### F4 — Cliente API frontend + tipos

**Objetivo (1 frase):** exponer los 3 endpoints en la capa de API del frontend con tipos TS explícitos, sin lógica de UI.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts`: agregar
  ```ts
  export const COST_SUMMARY = '/metrics/cost-summary';
  export const COST_BURN = '/metrics/cost-burn';
  export const COST_BREAKDOWN = '/metrics/cost-breakdown';
  ```
- `Stacky Agents/frontend/src/api/client.ts`: agregar funciones `fetchCostSummary(params)`, `fetchCostBurn(params)`, `fetchCostBreakdown(params)` siguiendo el patrón de fetch existente (reusar el helper GET con querystring ya presente en el archivo — **grepear** cómo `metrics/ticket-costs` u otro `/metrics/*` se llama hoy y replicar).
- **Archivo a crear:** `Stacky Agents/frontend/src/lib/costCenterTypes.ts` con las interfaces que espejan EXACTAMENTE los contratos JSON de F2 (`CostSummary`, `CostBurn`, `CostBreakdown`, `CostFiltersParams`, `TopRun`, `BurnPoint`, `BreakdownGroup`, `CostKind = 'reported'|'estimated'|'nominal'|'unknown'`).

**Test:** no aplica test de runtime (es red). **Gate:** `npm run build` (tsc) verde.

**Criterio binario:** `npm run build` sin errores de tipo. **Trabajo del operador: ninguno.**

---

### F5 — Lógica pura de presentación (formatters, sort, filter, CSV, math de SVG) + tests vitest

**Objetivo (1 frase):** aislar TODA la lógica de la vista en funciones puras testeables con vitest (sin React), porque RTL/jsdom no están instalados.

**Archivo a crear:** `Stacky Agents/frontend/src/lib/costCenter.logic.ts`
**Símbolos EXACTOS:**
```ts
export function formatUsd(n: number | null): string;         // "$0.42" | "n/d"
export function formatTokens(n: number | null): string;      // "12.3k" | "1.2M" | "n/d"
export function formatPct(n: number): string;                // "23%"
export function sortRows<T>(rows: T[], key: keyof T, dir: 'asc'|'desc'): T[];  // estable
export function filterRows(rows: TopRun[], f: TableFilterState): TopRun[];
export function toCsv(rows: TopRun[]): string;               // header + filas, escape de comas/comillas
export function costKindLabel(k: CostKind): string;          // "Reportado"|"Estimado"|"Nominal (suscripción)"|"n/d"
export function costKindTokenVar(k: CostKind): string;       // devuelve NOMBRE de var CSS del design system, p.ej. 'var(--tone-positive)'
// Math de SVG (charts sin librería):
export function linePath(points: {x:number;y:number}[]): string;   // "M x y L x y ..."
export function areaPath(points: {x:number;y:number}[], baselineY: number): string;
export function scaleLinear(domain: [number,number], range: [number,number]): (v:number)=>number;
export function niceTicks(min: number, max: number, count: number): number[];
```
> `costKindTokenVar` DEBE devolver referencias a tokens semánticos del Plan 138 (p.ej. `--tone-positive` para reportado, `--tone-warning` para estimado, `--tone-neutral` para nominal). **Prohibido** devolver hex (gate anti-drift color Plan 141). Confirmar los nombres reales de tokens grepeando el CSS de tokens del Plan 138 antes de codificar; si un token no existe, usar el más cercano existente (no inventar).

**Test (crear PRIMERO):** `Stacky Agents/frontend/src/lib/__tests__/costCenter.logic.test.ts`
Casos: `formatUsd null→"n/d"`, `formatTokens 12345→"12.3k"`, `sortRows estable y por dir`, `filterRows por runtime+cost_kind`, `toCsv escapa comas y comillas`, `linePath genera M/L correctos`, `scaleLinear mapea extremos`, `niceTicks devuelve N ticks ordenados`, `costKindTokenVar nunca devuelve string con '#'`.

**Comando:** `npx vitest run src/lib/__tests__/costCenter.logic.test.ts`. **Criterio binario:** 9/9 verdes.

**Trabajo del operador: ninguno.**

---

### F6 — Componentes visuales + página + entrada de navegación gated

> **GATE DE PREREQUISITO (C2):** F6 consume las **primitivas UI del Plan 138** (p.ej. `Card`), los **estados universales del Plan 140** (skeleton/vacío/error) y los **tokens semánticos del Plan 141** (anti-drift de color). Al momento de escribir este plan, 138/140/141 están CRITICADOS pero **NO implementados**. Por lo tanto:
> - **F0–F5 son implementables YA, independientes de 138/140/141** (backend puro + lógica TS pura; `costKindTokenVar` devuelve *nombres* de var CSS como string, que no requieren que el token exista para compilar).
> - **F6 NO debe iniciarse hasta que 138, 140 y 141 estén IMPLEMENTADOS.** Antes de codear F6, verificar por `grep` que la primitiva `Card` (u equivalente del Plan 138) y los tokens `--tone-*` existan en el CSS/components del frontend. Si NO existen, **detener F6** y reportar la dependencia (no inventar primitivas ni hardcodear color — violaría el gate anti-drift del 141). El resto del plan (F0–F5, F7, F8) queda entregado y verde igual.

**Objetivo (1 frase):** montar la vista (KPI cards + charts SVG + tabla ordenable/filtrable + export CSV) usando primitivas del Plan 138 y estados universales del Plan 140, con entrada de nav gated por la flag.

**Archivos a crear (todos `.tsx`, en `Stacky Agents/frontend/src/components/costcenter/`):**
- `CostKpiCards.tsx` — fila de KPI cards (costo billable, reportado, estimado, nominal, tokens in/out/cache, ahorro cache, avg/run, costo/tarea, %estimado, ratio out/in). Usar primitiva Card del Plan 138. Cada monto pasa por `formatUsd`; `null`→"n/d".
- `CostBadge.tsx` — badge `reported|estimated|nominal|unknown` (color vía `costKindTokenVar`, texto vía `costKindLabel`). Leyenda visible que aclara "nominal = suscripción, no facturable".
- `CostBurnChart.tsx` — chart SVG **propio** (área + línea) del burn temporal usando `linePath`/`areaPath`/`scaleLinear`/`niceTicks`. Selector de bucket (hour/day/week) y toggle acumulado. **Fallback textual:** botón "Ver como tabla" que renderiza la serie como `<table>` (para cuando el SVG no aporta o accesibilidad). Estado vacío/skeleton/error del Plan 140.
- `CostBreakdownBars.tsx` — barras horizontales SVG por dimensión, con selector de dimensión (runtime/model/agent_type/ticket/project/day). Fallback tabla igual.
- `CostTable.tsx` — tabla de `top_runs` (y opción "ver todos" que consume breakdown/summary), **ordenable por cualquier columna** (usa `sortRows`) y **filtrable** (rango fechas, runtime, modelo, agente, ticket, proyecto, estado, cost_kind) vía `filterRows`. Botón **Export CSV** (client-side Blob con `toCsv`, sin dependencia).
- `CostFiltersBar.tsx` — controles de filtro globales (rango de fechas / days, runtime, modelo, agente, proyecto, estado, cost_kind) que actualizan el estado y refetchean.

**Archivo a crear:** `Stacky Agents/frontend/src/pages/CostCenterPage.tsx` — compone todo, dueño del estado de filtros, usa `@tanstack/react-query` (ya instalado) para llamar a los 3 endpoints. Maneja `{enabled:false}` mostrando un estado "Función desactivada (activala en Arnés)".

**Entrada de navegación gated:** `grep` en `frontend/src` por `STACKY_EXECUTION_HISTORY_ENABLED` o `STACKY_DOCS_GRAPH_ENABLED` para encontrar CÓMO se renderiza condicionalmente una tab/entrada de nav según una flag del arnés; **replicar exactamente** ese patrón para `STACKY_COST_CENTER_ENABLED` (misma fuente de flags — el store/hook que ya expone el estado de flags). Con la flag OFF, la entrada **no aparece**.

**Reglas de estilo (Plan 138/140/141):** sólo tokens semánticos; skeletons durante carga; distinguir **estado vacío** ("no hay ejecuciones en el rango") de **error** ("falló la carga") — nunca colapsar ambos; cero color hardcodeado.

**Test (crear PRIMERO, lógica pura ya cubierta en F5):** para los `.tsx` el gate es `npm run build` (tsc --noEmit). Agregar, si conviene, `src/lib/__tests__/costTable.reducer.test.ts` para el reducer de estado de filtros/orden si se extrae como función pura.

**Comando de verificación:** `npm run build` (desde `frontend`). **Criterio binario:** build verde (tsc 0 errores) + los tests de F5 verdes.

**Impacto por runtime:** la UI muestra badges `reported/estimated/nominal` por run → el operador ve de un vistazo qué es facturable (claude/codex) y qué es sólo hint (copilot). **Trabajo del operador: NINGUNO (default ON; desactivable desde UI).**

---

### F7 (OPCIONAL) — Reconciliación con export externo tipo ccusage/codeburn (flag default OFF, degrada en silencio)

> **Justificación del default OFF (excepción dura #3):** F7 lee un archivo JSONL externo cuya existencia y ruta **NO están garantizadas en una instalación default** (prerequisito no garantizado). Además sólo tiene sentido si el operador YA usa esa herramienta externa. Por eso `STACKY_COST_CODEBURN_IMPORT_ENABLED` es la **única** flag del plan que queda default OFF, y cita explícitamente la excepción #3. (La flag maestra F3 sigue default ON.)

**Objetivo (1 frase):** si el operador tiene un export JSONL de una herramienta externa (ccusage/codeburn) en una ruta configurable, parsearlo como fuente **adicional** de reconciliación; si no está, ignorarlo silenciosamente.

**Decisión de diseño (fija):** **NO** shell-out a ningún binario, **NO** dependencia nueva. Sólo lectura de un archivo JSONL local ya presente. Esto preserva la paridad de runtimes y no agrega carga.

**Archivos:**
- `config.py`: `STACKY_COST_CODEBURN_IMPORT_ENABLED: bool = ... == "true"` (default false) y `STACKY_COST_CODEBURN_IMPORT_PATH: str = os.getenv("STACKY_COST_CODEBURN_IMPORT_PATH", "").strip()` (default "" = desactivado).
- `harness_flags.py`: `FlagSpec(key="STACKY_COST_CODEBURN_IMPORT_ENABLED", type="bool", ..., group="observabilidad")` + su `pair`/knob `STACKY_COST_CODEBURN_IMPORT_PATH` (type="str"); ambas en `_CATEGORY_KEYS["observabilidad_notif"]`. Default OFF (no `_CURATED_DEFAULTS_ON`).
- `cost_analytics.py`: `load_external_codeburn() -> dict | None` — si flag OFF o path vacío/inexistente → `None`. Si existe: parsea JSONL (una línea = un registro con `{cost_usd, tokens_in, tokens_out, timestamp, model?}`), suma total, y devuelve `{"source": "external_jsonl", "total_usd": X, "records": N}`. Malformado → log warn + `None` (nunca crash).
- `metrics.py` `/cost-summary`: si `load_external_codeburn()` no es None, agregar clave `"external_reconciliation": {"external_total_usd": X, "stacky_billable_usd": Y, "delta_usd": X-Y}`. Si es None, la clave **no aparece** (silencio total).

**Casos borde:** flag OFF → clave ausente. Path inexistente → clave ausente. JSONL malformado → warn, clave ausente. Nunca afecta a `cost-burn`/`cost-breakdown`.

**Test:** `Stacky Agents/backend/tests/test_cost_codeburn_import.py`: `test_disabled_returns_none`, `test_missing_path_returns_none`, `test_valid_jsonl_parsed`, `test_malformed_jsonl_returns_none_no_crash`, `test_summary_includes_reconciliation_when_enabled`.

**Criterio binario:** 5/5 verdes + `/cost-summary` sin la flag sigue idéntico (test de F2 sin cambios). **Trabajo del operador: opt-in (default off, excepción dura #3); requiere setear ruta sólo si el operador YA usa esa herramienta.**

---

### F8 (OPCIONAL) — [ADICIÓN ARQUITECTO] Auditoría de reconciliación legacy vs canónico (read-only, cuantifica el landmine R3)

**Objetivo (1 frase):** un endpoint read-only que **mide** cuánto se equivoca hoy el cálculo legacy (`metrics._execution_costs`, que ignora Codex y trata `cost_estimated` bool como monto) comparándolo con el extractor canónico F0 sobre EXACTAMENTE las mismas ejecuciones — **sin modificar** los endpoints legacy.

**Por qué (alto valor, cero riesgo):** el plan documenta la divergencia R3 y la deja fuera de scope para no regresionar. Pero "documentarla" no la hace visible ni medible. Esta fase la **cuantifica** (incluyendo el gasto de Codex que hoy es invisible), dándole al operador y al futuro plan de migración una cifra dura de "cuánto costo real no estás viendo". Es 100% read-only, no captura dato nuevo, y reusa ambos caminos de código ya existentes.

**Archivo a editar:** `Stacky Agents/backend/api/metrics.py` (nuevo endpoint bajo el mismo Blueprint y la misma flag maestra).

**Ruta y contrato:**
```python
@bp.get("/cost-reconciliation-audit")
def cost_reconciliation_audit():
    if not _cost_center_enabled(): return jsonify({"enabled": False}), 200
    f, err = _filters_or_error(request.args)
    if err: return err
    records = ca.load_records(f)
    # Canónico (F0): billable por run.
    canonical_billable = round(sum(r.row.cost_usd or 0.0 for r in records
                                   if ca._billable(r.row.cost_kind)), 6)
    codex_invisible = round(sum(r.row.cost_usd or 0.0 for r in records
                               if (r.row.runtime == "codex_cli" and ca._billable(r.row.cost_kind))), 6)
    # Legacy: reusa la función existente _execution_costs SIN modificarla (read-only).
    #   → hay que releer las ejecuciones por id para pasarle el objeto AgentExecution.
    #   Alternativa determinista: recomputar el legacy con la MISMA lógica exacta que _execution_costs
    #   (sólo claude_telemetry.total_cost_usd + float(cost_estimated)) sobre los metadata_dict ya cargados.
    return jsonify({"ok": True, "enabled": True,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "canonical_billable_usd": canonical_billable,
                    "legacy_reported_usd": <suma legacy>,     # ver nota de implementación
                    "delta_usd": round(canonical_billable - <legacy>, 6),
                    "codex_invisible_usd": codex_invisible,    # gasto que el legacy NO ve
                    "runs_audited": len(records)})
```
> **Nota de implementación (determinismo):** para NO tocar `_execution_costs` ni requerir objetos ORM vivos, recomputar el número legacy con una función pura espejo en `cost_analytics.py`: `legacy_cost_mirror(md) -> float` que replica EXACTO lo que hoy hace `_execution_costs` (leer sólo `md["claude_telemetry"]["total_cost_usd"]` + `float(md.get("cost_estimated") or 0)`), documentada como "espejo del bug legacy, sólo para auditoría". Así el endpoint compara canónico vs legacy sobre los mismos `metadata_dict` ya cargados por `load_records`, sin segunda query ni mutación.

**Casos borde:** flag OFF → `{"enabled": false}`. Sin datos → todos 0. Nunca escribe. Nunca altera `/ticket-costs`/`/project-costs`.

**Test (crear PRIMERO):** `Stacky Agents/backend/tests/test_cost_reconciliation_audit.py`: `test_audit_disabled_returns_enabled_false`, `test_codex_invisible_usd_is_positive_when_codex_has_cost`, `test_legacy_mirror_matches_current_execution_costs_bug`, `test_delta_zero_when_only_claude_reported`.
**Criterio binario:** 4/4 verdes; `/ticket-costs` y `/project-costs` sin cambios (sus tests existentes siguen verdes). **Trabajo del operador: NINGUNO (default ON; desactivable desde UI).**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Doble conteo** estimado vs reportado. | `cost_kind` mutuamente excluyente por run (F0); invariante `billable_usd == reported_usd + estimated_usd` con test dedicado (F1). |
| R2 | **Presentar costo de Copilot como facturable.** | `github_copilot` → `cost_kind="nominal"`, EXCLUIDO de `billable_usd`; badge/leyenda "nominal (suscripción)"; test `test_copilot_is_nominal_never_reported`. |
| R3 | **Divergencia real detectada:** `metrics._execution_costs` lee sólo `claude_telemetry` (claude-only) y trata `cost_estimated` como **monto** (float), mientras `telemetry.py` lo escribe como **bool** en `harness_telemetry`. Codex quedaba invisible en `/ticket-costs`/`/project-costs`. | F0 introduce el extractor canónico que reconcilia las 3 fuentes. **No** se modifican los endpoints legacy en este plan (evitar regresión); se documenta la divergencia y se deja una nota para un plan futuro de migrar `_execution_costs` a `extract_cost_row`. (Fuera de scope de 142.) |
| R4 | **Performance** de agregación (N ejecuciones). | Una query SQL indexada (`ix_exec_status_started`, `ix_exec_ticket_started`) con filtros de columna + cap `_MAX_ROWS=20000` + ventana default 30 días; agregación en memoria O(n). Sin N+1 (join Ticket en la misma query). |
| R5 | **Sin librería de charts** en el front. | Charts en SVG propio (F5 provee la math); fallback tabla en cada chart. Cero dependencia nueva. |
| R6 | **RTL/jsdom ausentes** → no se pueden testear componentes React. | Toda la lógica testeable vive en funciones puras (F5) con vitest; el gate de los `.tsx` es `tsc --noEmit` (`npm run build`). |
| R7 | **Romper tests del arnés** al agregar la flag. | Flag default ON **coherente en los 3 puntos** (C1): `default=True` en `FlagSpec` + alta en `_CURATED_DEFAULTS_ON` + `config.py` `"true"` + alta en `_CATEGORY_KEYS`. Omitir cualquiera rompe `test_default_known_only_for_curated` (igualdad de conjuntos) o `test_every_registry_flag_is_categorized`; `test_harness_flags.py` como gate. |
| R8 | **Modelo desconocido** → costo inventado. | `estimate_cost` devuelve `None` sin match; F0 propaga `cost_kind="unknown"` y `cost_usd=None`; UI muestra "n/d". Nunca 0.0. |
| R9 | **cache_savings** malinterpretado como ahorro real. | Etiquetar siempre "ahorro estimado"; se calcula sólo si hay `cache_read_tokens` y modelo con precio; si no, `None`. |
| R10 (C9) | **Cap `_MAX_ROWS` aplicado en SQL ANTES de los filtros de metadata** (runtime/model/cost_kind se filtran en Python porque viven en JSON). Con > 20 000 ejecuciones en la ventana, un filtro por runtime podría ver sólo las 20 000 más recientes. | Escala mono-operador: 20 000 runs en 30 días es improbable. El endpoint agrega `"capped": len(records) == ca._MAX_ROWS` al JSON (junto a `filters_echo`) para que la UI muestre "resultados acotados a las 20 000 ejecuciones más recientes" cuando aplique. No se sube el cap (protege memoria). |
| R11 (C7) | Acceso a instancias ORM tras cerrar la sesión. | Verificado `expire_on_commit=False` (`db.py:33`) → los atributos ya cargados siguen legibles; aun así F1 construye los `ExecRecord` **dentro** del `with session_scope()` (robustez ante cambios futuros). |

---

## 6. Fuera de scope (explícito)

- Modificar `_execution_costs`/`/ticket-costs`/`/project-costs` existentes (se dejan intactos para no regresionar; la migración a `extract_cost_row` es un plan futuro).
- Persistir nuevos campos de telemetría o cambiar cómo los runtimes reportan costo.
- Presupuestos, alertas, enforcement de caps o cualquier **acción** sobre el costo (violaría human-in-the-loop). Este plan sólo **muestra**.
- Multiusuario / RBAC / atribución por usuario (mono-operador).
- Integración con APIs de facturación de proveedores (Anthropic/OpenAI billing). Sólo telemetría local.
- Proyecciones/forecast complejos: se permite sólo una proyección lineal simple **claramente etiquetada como estimación** dentro de `cost-burn` si sobra tiempo; si no, se omite (no es DoD).

---

## 7. Glosario, Orden de implementación y DoD

### Glosario
- **RunTelemetry** (`harness/telemetry.py`): dataclass canónica por ejecución con `total_cost_usd`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cost_estimated`.
- **AgentExecution.metadata_dict** (`models.py`): dict JSON por ejecución donde vive la telemetría (`harness_telemetry`, `claude_telemetry` legacy, y top-level `cost_usd`/`tokens_in`/`tokens_out`/`model`/`runtime`).
- **cost_estimated** (bool): `True` si `total_cost_usd` se derivó de `pricing.estimate_cost` (fallback), no del CLI.
- **cost_kind** (nuevo, este plan): clasificación por run → `reported` (USD real del CLI) | `estimated` (pricing fallback) | `nominal` (suscripción Copilot, no facturable) | `unknown` (sin costo ni tokens).
- **reportado vs estimado vs nominal**: reportado = gasto real facturable; estimado = aproximación por tokens×precio; nominal = hint de suscripción plana (excluido del gasto).
- **billable_usd**: `reported_usd + estimated_usd` (nunca incluye nominal).
- **burn-rate / codeburn**: USD y tokens consumidos por bucket temporal (hora/día/semana), con acumulado y comparación de período.
- **cache_read_tokens / ahorro estimado**: tokens servidos desde cache; el "ahorro estimado" = `cache_read_tokens × precio_input_del_modelo`.
- **runtime**: `claude_code_cli` | `codex_cli` | `github_copilot` (este último es el default y el de suscripción).

### Orden de implementación (numerado, por dependencia)
1. **F0** — extractor canónico (`cost_analytics.py` + `test_cost_analytics_extract.py`).
2. **F1** — motor de agregación (mismo módulo + `test_cost_analytics_aggregate.py`).
3. **F3** — flag + config + categoría **default ON** (`harness_flags.py`, `config.py`, `test_harness_flags.py`). *(Se hace antes de F2 para que los endpoints ya tengan la flag.)*
4. **F2** — endpoints (`metrics.py` + `test_cost_center_api.py`).
5. **F8** — (opcional, [ADICIÓN ARQUITECTO]) auditoría de reconciliación (`metrics.py` + `cost_analytics.legacy_cost_mirror` + `test_cost_reconciliation_audit.py`). Independiente del frontend.
6. **F4** — cliente API + tipos front (`endpoints.ts`, `client.ts`, `costCenterTypes.ts`).
7. **F5** — lógica pura de presentación (`costCenter.logic.ts` + test vitest).
8. **F6** — componentes + página + nav gated (`components/costcenter/*`, `CostCenterPage.tsx`). **BLOQUEADA hasta que Planes 138/140/141 estén IMPLEMENTADOS (C2).** F0–F5/F8 no dependen de ellos.
9. **F7** — (opcional) reconciliación externa (`cost_analytics.py`, `config.py`, `harness_flags.py`, `test_cost_codeburn_import.py`).

> **Nota de secuencia con la serie UX (C2):** este plan (142) se implementa **después** de 138→140→141. Las fases backend/lógica pura (F0–F5, F7, F8) pueden entregarse antes; sólo F6 exige la serie de diseño construida.

### Definición de Hecho (DoD) global
- [ ] F0: `test_cost_analytics_extract.py` 9/9 verde (incluye borde malformado C10).
- [ ] F1: `test_cost_analytics_aggregate.py` 12/12 verde (invariante anti-doble-conteo + 3 casos C5 de `previous_period`/`filters_echo`).
- [ ] F3: `test_harness_flags.py` verde completo (con la key en `_CURATED_DEFAULTS_ON`); flag **default ON**, visible y toggleable en el sub-tab Arnés.
- [ ] F2: `test_cost_center_api.py` 9/9 verde (incluye `test_burn_invalid_date_400`); con flag OFF los 3 endpoints devuelven `{"enabled": false}`; endpoints legacy intactos.
- [ ] F8 (si se implementa): `test_cost_reconciliation_audit.py` 4/4 verde; `codex_invisible_usd` medible; `/ticket-costs`/`/project-costs` sin cambios.
- [ ] F5: `costCenter.logic.test.ts` 9/9 verde; ningún token de color con `#`.
- [ ] F4+F6: `npm run build` verde (tsc 0 errores); **prerequisito C2 verificado (138/140/141 implementados)**; con la flag ON (default) la entrada de nav aparece, con OFF no; charts renderizan con fallback tabla; estados vacío/error distintos (Plan 140); sin color hardcodeado (Plan 141).
- [ ] F7 (si se implementa): `test_cost_codeburn_import.py` 5/5 verde; con flag OFF, `/cost-summary` idéntico a pre-F7.
- [ ] Guardarraíles: read-only verificado (ningún `session.add`/commit en la ruta nueva; `outerjoin` no descarta huérfanas); Copilot nunca en `billable_usd`; cero dato nuevo capturado; **flag maestra default ON (C1) — "Trabajo del operador: NINGUNO"**.

---

## Notas de paridad de runtimes (resumen ejecutivo)

| Runtime | Qué reporta | cost_kind | En billable_usd | Fallback |
|---|---|---|---|---|
| `claude_code_cli` | `total_cost_usd` real + tokens | `reported` | Sí | Si falta USD pero hay tokens → `estimated` vía pricing |
| `codex_cli` | tokens (USD raro) | `estimated` | Sí | Si no matchea modelo → `unknown`, "n/d" |
| `github_copilot` | suscripción plana | `nominal` | **No** | Hint vía pricing sólo si hay tokens+modelo; si no → "n/d" |
