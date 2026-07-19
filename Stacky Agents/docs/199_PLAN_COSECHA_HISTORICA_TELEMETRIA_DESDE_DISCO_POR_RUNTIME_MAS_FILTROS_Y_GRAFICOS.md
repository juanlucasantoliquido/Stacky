# Plan 199 — Cosecha histórica de telemetría desde disco por runtime + más filtros + más gráficos

- **Estado:** PROPUESTO v1 (2026-07-18)
- **Autor:** StackyArchitectaUltraEficientCode (perfil normal, Opus 4.8)
- **Numeración:** 199 (máximo en `docs/` = 198; libre)
- **Runtimes:** Codex CLI · Claude Code CLI · GitHub Copilot Pro (paridad con fallback explícito)
- **Naturaleza:** read-only sobre los artefactos de runtime; aditivo sobre el store canónico; sin daemons bloqueantes; HITL.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy el Centro de Costos (Plan 142) sólo ve la telemetría que quedó guardada en `AgentExecution.metadata_json` en la DB. Todo lo que corrió **antes** de que existiera la captura de telemetría (o cuyo proceso murió antes del evento `result`, declarado "irrecuperable desde la DB" por el Plan 158 §6) es invisible: aparece como `cost_kind="unknown"` o directamente no existe. Sin embargo, **cada runtime CLI deja en disco su propia transcripción de sesión** (`~/.codex/sessions/**/rollout-*.jsonl`, `~/.claude/projects/**/<session>.jsonl`) con el uso real de tokens. El Plan 199 **cosecha esos artefactos locales** (read-only, idempotente, por runtime con fallback) y (A) **rellena** la telemetría faltante de las ejecuciones históricas de Stacky que sí existen en DB, y (B) **registra** en una bitácora durable las sesiones que no matchean ninguna ejecución (para verlas por separado, sin contaminar los números facturables por ticket). Además (C) agrega **más filtros** (multi-runtime, multi-modelo, rango de costo, fuente live/cosecha) y (D) **más gráficos** (serie apilada por runtime/modelo, heatmap día×hora, distribución de costo por corrida) al Centro de Costos existente.

**KPI / impacto esperado (binario y medible):**
- **K1 — Recuperación de costo histórico:** `% de ejecuciones históricas con cost_kind != "unknown"` sube tras el primer scan. Medible con `/api/metrics/cost-reconciliation-audit` antes/después (campo `runs_audited` + `canonical_billable_usd`).
- **K2 — Cobertura de cosecha:** nº de sesiones en disco descubiertas y clasificadas (matched / unmatched / sin-uso), reportado por `/api/metrics/telemetry-harvest/scan`.
- **K3 — Visibilidad codex:** el `codex_invisible_usd` reportado por la auditoría deja de crecer sin explicación, porque las sesiones codex históricas quedan atribuidas.
- **K4 — Analítica:** 3 gráficos nuevos + 4 filtros nuevos disponibles sin degradar los existentes (tsc verde + vitest por archivo verde).

**Trabajo del operador:** ninguno para el valor central (auto-scan en background, no bloqueante, default ON con degradación graciosa). Opt-in explícito sólo para ampliar el alcance a sesiones no atribuidas a Stacky (default: sólo sesiones de workspaces Stacky).

---

## 2. Por qué ahora / gap que cierra (fronteras vs 142/158/171)

El "loop de auto-mejora" cerró la serie DevOps (198) y la serie UX cockpit (172-175). La telemetría de costos es el eje transversal con más data ya presente pero **infrautilizada históricamente**. Los tres planes de dominio dejan un hueco exacto y verificado (subagente de exploración, 2026-07-18):

| Plan | Estado | Qué hace | Frontera relevante para 199 |
|---|---|---|---|
| **142** Centro de Costos | IMPLEMENTADO (commit a24f8848) | Extractor canónico `extract_cost_row` + agregadores puros `summarize`/`burn`/`breakdown` + 3 endpoints + UI SVG. Lee **sólo DB**. | 199 **reusa** `extract_cost_row`, `summarize`, `burn`, `breakdown`, `ExecRecord`, `CostFilters`, `_billable`; **no reescribe** ninguno. F7 `load_external_codeburn` es el **precedente** de "leer un archivo local sin shell-out" que 199 espeja apuntando a artefactos de runtime. |
| **158** Fix telemetría claude CLI | IMPLEMENTADO F0-F7 | Persiste `metadata["model"]` + `harness_telemetry` en runs claude nuevos; backfill **DB→DB** (`backfill_claude_model_key`, copia `claude_code_model→model`). §6: filas sin datos en DB son "irrecuperables" (no va a buscarlas a disco). | 199 **cierra exactamente ese hueco**: recupera desde disco lo que 158 declaró irrecuperable desde DB. **No toca** la producción de telemetría de runs nuevos ni `backfill_claude_model_key`. |
| **171** Telemetría operativa | PROPUESTO v1 (sin implementar) | Salud/tendencias/baselines/umbrales/traza **hacia adelante**, todo desde DB. Agrega `ExecRecord.completed_at` (aditivo) + endpoints `/ops-*`. | 199 **no duplica** salud/tendencias/baselines/traza ni ningún endpoint `/ops-*`. La adición de `completed_at` (171) y las adiciones de 199 a `CostFilters` son **sobre atributos distintos** → merge aditivo sin conflicto (ver §10 nota de colisión). |

**Espacio libre confirmado:** ninguno de los 3 lee `~/.codex` / `~/.claude` / rollout files para cosechar telemetría histórica. El Plan 199 es la **capa de cosecha desde disco** encima del extractor congelado del 142.

---

## 3. Principios y guardarraíles (aplican a TODAS las fases)

1. **READ-ONLY sobre los artefactos del runtime.** Nunca se escribe, mueve, borra ni trunca ningún archivo bajo `~/.codex` o `~/.claude`. Sólo `open(path, "r")` con lectura por líneas.
2. **Idempotente.** Correr el scan N veces produce el mismo estado final: el backfill DB salta filas ya rellenadas (marca de procedencia) o ya facturables; la bitácora deduplica por `dedup_key`.
3. **Degradación graciosa (excepción dura #3 citada).** Los directorios de sesión locales son un **prerequisito NO garantizado** en una instalación default. Cada descubridor devuelve `[]` si su raíz no existe; cada parser saltea líneas/archivos inválidos y continúa. **Jamás** una excepción propaga ni bloquea el arranque.
4. **Paridad de 3 runtimes con fallback explícito.** Discoverer+parser por runtime; `github_copilot` no persiste sesiones locales con uso de tokens (bridge HTTP, `copilot_bridge.py`) → su discoverer devuelve `[]` con razón logueada. Documentado, no roto.
5. **No contaminar lo facturable por ticket.** El backfill sólo toca ejecuciones Stacky existentes (matched). Las sesiones **no matcheadas** van a una bitácora SEPARADA y se muestran en una sección aparte, etiquetada, con `source` filtrable. Nunca se auto-mezclan en `billable_usd` por ticket.
6. **Privacidad por default.** Sólo se cosechan/atribuyen sesiones cuyo `cwd` cae bajo un workspace Stacky conocido (`STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY=ON`). El operador puede ampliar a "todo el disco" explícitamente.
7. **Sólo números + identificadores, nunca texto de prompt/respuesta.** La cosecha extrae `tokens/costo/modelo/session_id/timestamp`. **No** ingiere el contenido de los mensajes. Cualquier string conservado (paths) se enmascara: `cwd`→basename/proyecto; se descarta cualquier valor que dispare `secret_scanner.scan_secrets`.
8. **No bloquear el arranque.** El auto-scan corre en un daemon thread, con caps de archivos/tamaño/lookback, y guard `STACKY_TEST_MODE`.
9. **Reusar, no reinventar.** Extractor y agregadores del 142; `estimate_cost`/`from_claude_stream`/`from_codex_event` del arnés; patrón de bitácora JSONL en `data_dir()` del 191/198; `secret_scanner` existente para masking.
10. **Backward-compatible.** Todos los campos nuevos de `CostFilters` tienen default (append-only); los endpoints existentes no cambian su contrato; las flags nuevas son ON salvo la excepción citada.
11. **Mono-operador sin auth.** Sin RBAC, sin multiusuario.
12. **HITL.** El auto-scan sólo **muestra** datos; nada externo se dispara. El botón "Escanear históricos" es control manual del operador.

---

## 4. Fases

Dependencias: **F0 → F1 → F2 → F3 → F6** (backend+wiring), y **F4, F5** (filtros/gráficos) dependen sólo del 142 ya implementado, por lo que pueden ir en paralelo a F1-F3. F7 cierra flags/tests/docs.

---

### F0 — Descubridores + parsers por runtime (PURO, sin DB, sin ingestión)

**Objetivo (1 frase + valor).** Un módulo autocontenido que descubre en disco los artefactos de sesión de cada runtime y los normaliza a `HarvestedRun`, con fallback explícito por runtime; es la base verificable de todo lo demás y no toca DB ni escribe nada.

**Archivo a CREAR:** `Stacky Agents/backend/services/telemetry_harvest.py`

**Símbolos EXACTOS a crear:**

```python
from __future__ import annotations
import json, logging, os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("stacky.services.telemetry_harvest")

_HARVEST_MAX_FILES = 5000        # cap duro de archivos por scan (mono-operador)
_HARVEST_MAX_BYTES_PER_FILE = 25 * 1024 * 1024   # 25 MB: archivos mayores se saltean (log warn)
_HARVEST_MAX_LINES_PER_FILE = 50000              # cap de líneas por archivo

@dataclass
class HarvestedRun:
    runtime: str                     # "codex_cli" | "claude_code_cli" | "github_copilot"
    session_id: str | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cache_read_tokens: int | None
    total_cost_usd: float | None     # None si el artefacto no lo trae (se estima aguas abajo)
    cost_estimated: bool             # True si total_cost_usd fue estimado por pricing
    started_at: datetime | None      # primer timestamp del artefacto o mtime del archivo
    project_hint: str | None         # nombre de proyecto/carpeta derivado del cwd (enmascarado)
    cwd: str | None                  # cwd ENMASCARADO (basename), o None
    artifact: str                    # basename del archivo (enmascarado), nunca ruta absoluta
    source_format: str               # "codex_rollout" | "claude_transcript"
    num_events: int

    def to_harness_telemetry(self) -> dict:
        """Dict con EXACTAMENTE las claves que extract_cost_row(md) lee de
        md['harness_telemetry'] (runtime, session_id, total_cost_usd,
        cost_estimated, input_tokens, output_tokens, cache_read_tokens) + 'source'."""
        return {
            "runtime": self.runtime,
            "session_id": self.session_id,
            "total_cost_usd": self.total_cost_usd,
            "input_tokens": self.tokens_in,
            "output_tokens": self.tokens_out,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_estimated": self.cost_estimated,
            "num_turns": None,
            "source": "harvest_disk",     # procedencia, para distinguir de telemetría live
        }

    def dedup_key(self) -> str:
        return f"{self.runtime}:{self.session_id or self.artifact}"
```

**Resolución de raíces (con override):**

```python
def _roots_override() -> dict:
    """STACKY_TELEMETRY_HARVEST_ROOTS_JSON: {"codex_cli": "<path>", "claude_code_cli": "<path>"}.
    Vacío/malformado -> {} (sin override)."""
    from config import config as _cfg
    raw = (getattr(_cfg, "STACKY_TELEMETRY_HARVEST_ROOTS_JSON", "") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        logger.warning("telemetry_harvest: ROOTS_JSON malformado, ignorado")
        return {}

def _codex_sessions_root() -> Path | None:
    ov = _roots_override().get("codex_cli")
    if ov:
        p = Path(ov).expanduser()
        return p if p.is_dir() else None
    base = os.getenv("CODEX_HOME", "").strip()
    root = (Path(base).expanduser() if base else Path.home() / ".codex") / "sessions"
    return root if root.is_dir() else None       # excepción dura #3: ausente -> None (no crash)

def _claude_projects_root() -> Path | None:
    ov = _roots_override().get("claude_code_cli")
    if ov:
        p = Path(ov).expanduser()
        return p if p.is_dir() else None
    root = Path.home() / ".claude" / "projects"
    return root if root.is_dir() else None        # excepción dura #3: ausente -> None
```

**Descubridores (mtime-filtrados por lookback, capados):**

```python
def _iter_jsonl(root: Path, pattern: str, since: datetime, limit: int) -> list[Path]:
    """rglob capado + filtrado por mtime >= since; ordenado por mtime desc; nunca lanza."""
    out: list[Path] = []
    try:
        for p in root.rglob(pattern):
            if len(out) >= limit:
                break
            try:
                if datetime.utcfromtimestamp(p.stat().st_mtime) >= since:
                    out.append(p)
            except OSError:
                continue
    except OSError:
        return []
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

def discover_codex_rollouts(since: datetime, limit: int) -> list[Path]:
    root = _codex_sessions_root()
    return _iter_jsonl(root, "rollout-*.jsonl", since, limit) if root else []

def discover_claude_transcripts(since: datetime, limit: int) -> list[Path]:
    root = _claude_projects_root()
    return _iter_jsonl(root, "*.jsonl", since, limit) if root else []

def discover_copilot_sessions(since: datetime, limit: int) -> list[Path]:
    """FALLBACK EXPLÍCITO: github_copilot corre vía bridge HTTP (copilot_bridge.py) y
    NO persiste sesiones locales con uso de tokens. Devuelve [] y loguea la razón.
    Paridad documentada: si en el futuro aparece un log local, se agrega aquí."""
    logger.info("telemetry_harvest: github_copilot no persiste sesiones locales (bridge HTTP); skip")
    return []
```

**Parsers (por-archivo, streaming, tolerantes):**

```python
def parse_codex_rollout(path: Path) -> HarvestedRun | None:
    """Agrega tokens/costo de un rollout JSONL de codex. Reusa la MISMA extracción
    de campos que services/harness/telemetry.from_codex_event (usage|tokens,
    input_tokens|prompt_tokens, etc.). session_id/model del primer evento que los traiga.
    Sin uso en ninguna línea -> HarvestedRun con tokens=None (cost via estimate abajo)."""
    # 1) skip si tamaño > _HARVEST_MAX_BYTES_PER_FILE (log warn, return None)
    # 2) leer <= _HARVEST_MAX_LINES_PER_FILE líneas; por cada línea: json.loads en try/except
    #    (línea inválida -> continue). Extraer con la lógica de from_codex_event.
    # 3) acumular: tokens_in/out = suma de eventos de uso; cache_read idem; model/session_id
    #    = primero no-nulo; total_cost_usd = último no-nulo si viene, si no None.
    # 4) started_at = primer timestamp parseable, si no datetime.utcfromtimestamp(mtime).
    # 5) cwd/project_hint desde evento con "cwd" si existe -> _mask_path(cwd).
    # 6) _finalize_cost(run, model): si total_cost_usd None y hay tokens -> estimate_cost.
    ...

def parse_claude_transcript(path: Path) -> HarvestedRun | None:
    """Agrega usage de un transcript de Claude Code. Cada evento assistant trae
    message.usage {input_tokens, output_tokens, cache_read_input_tokens} y message.model.
    session_id = campo sessionId del evento o el stem del archivo (uuid). total_cost_usd
    NO viene fiable en el transcript -> None -> se estima -> cost_estimated=True.
    cwd derivado del nombre de carpeta escapada o de un campo 'cwd'."""
    ...
```

**Helpers de masking y estimación (reusan lo existente):**

```python
def _mask_path(raw: str | None) -> str | None:
    """Devuelve SOLO el basename (nunca ruta absoluta) y lo pasa por secret_scanner:
    si dispara un patrón, devuelve '<redacted>'."""
    if not raw:
        return None
    from services.secret_scanner import scan_secrets
    base = os.path.basename(raw.rstrip("/\\")) or raw
    return "<redacted>" if scan_secrets(base) else base

def _finalize_cost(run: HarvestedRun, model: str | None) -> None:
    """Reusa harness.pricing.estimate_cost. Si total_cost_usd None y hay tokens,
    estima y marca cost_estimated=True. Reportado siempre gana (idéntico a
    harness/telemetry._maybe_estimate_cost)."""
    if run.total_cost_usd is not None:
        return
    if run.tokens_in is None and run.tokens_out is None:
        return
    try:
        from harness.pricing import estimate_cost
        est = estimate_cost(model, run.tokens_in, run.tokens_out)
    except Exception:
        est = None
    if est is not None:
        run.total_cost_usd = est
        run.cost_estimated = True
```

**Orquestador (sin DB):**

```python
def harvest_runs(*, lookback_days: int, max_files: int = _HARVEST_MAX_FILES) -> list[HarvestedRun]:
    """Descubre + parsea las 3 fuentes. NO toca DB, NO escribe. Devuelve list[HarvestedRun].
    Nunca lanza: cualquier error por-archivo se saltea."""
    since = datetime.utcnow() - timedelta(days=max(1, min(lookback_days, 3650)))
    per_source = max(1, max_files // 2)
    runs: list[HarvestedRun] = []
    for path in discover_codex_rollouts(since, per_source):
        r = parse_codex_rollout(path)
        if r:
            runs.append(r)
    for path in discover_claude_transcripts(since, per_source):
        r = parse_claude_transcript(path)
        if r:
            runs.append(r)
    discover_copilot_sessions(since, per_source)   # no-op documentado (fallback)
    return runs
```

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan199_harvest_discovery.py`:**
- `test_codex_root_absent_returns_empty`: con `_codex_sessions_root` monkeypatch→None, `discover_codex_rollouts` == `[]`.
- `test_claude_root_absent_returns_empty`: idem claude.
- `test_copilot_discover_is_noop`: `discover_copilot_sessions(...)` == `[]`.
- `test_parse_codex_rollout_fixture`: fixture JSONL (tmp_path) con eventos `{"type":"system","session_id":"codex-sess-1"}` + `{"usage":{"input_tokens":100,"output_tokens":40}}` → `HarvestedRun(runtime="codex_cli", session_id="codex-sess-1", tokens_in=100, tokens_out=40)`.
- `test_parse_claude_transcript_fixture`: fixture con evento assistant `{"type":"assistant","sessionId":"claude-sess-9","message":{"model":"claude-sonnet-5","usage":{"input_tokens":200,"output_tokens":80,"cache_read_input_tokens":50}}}` → tokens agregados + `cost_estimated=True` (costo estimado por pricing) + `model="claude-sonnet-5"`.
- `test_parse_skips_malformed_lines`: archivo con una línea `not json` intercalada → no lanza, agrega el resto.
- `test_parse_oversize_file_skipped`: archivo > `_HARVEST_MAX_BYTES_PER_FILE` (monkeypatch del cap a 10 bytes) → `None`, sin lanzar.
- `test_mask_path_redacts_secret`: `_mask_path("/home/u/ghp_" + "A"*35)` → `"<redacted>"`.
- `test_to_harness_telemetry_keys`: el dict devuelto tiene exactamente las claves que `cost_analytics.extract_cost_row` lee (assert claves ⊇ {runtime, total_cost_usd, input_tokens, output_tokens, cache_read_tokens, cost_estimated}).

**Comando EXACTO (venv del repo):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_plan199_harvest_discovery.py -v
```

**Criterio de aceptación BINARIO:** el comando anterior sale 0 con todos los tests PASSED. Verificable con `echo $LASTEXITCODE` == 0 (PowerShell) tras el pytest.

**Flag que la protege:** ninguna (módulo puro sin efectos; sólo se ejecuta cuando F1/F3 lo llaman, ya gateados). **No** se importa en `create_app` en F0.

**Impacto por runtime + fallback:**
- Codex: lee `~/.codex/sessions/**/rollout-*.jsonl`. Fallback: dir ausente → `[]`.
- Claude Code: lee `~/.claude/projects/**/*.jsonl`. Fallback: dir ausente → `[]`.
- Copilot: no-op documentado (`discover_copilot_sessions` → `[]`).

**Trabajo del operador:** ninguno.

---

### F1 — Backfill idempotente a la DB de las ejecuciones matcheadas

**Objetivo (1 frase + valor).** Para cada `HarvestedRun` cuyo `session_id` matchea una `AgentExecution` existente **sin telemetría facturable**, escribir `metadata["harness_telemetry"]` + `metadata["model"]` desde el artefacto de disco; así el Centro de Costos (142) muestra automáticamente el costo real de esos tickets pasados sin cambiar nada del extractor.

**Archivo a EDITAR:** `Stacky Agents/backend/services/telemetry_harvest.py` (agregar al final; **NO** tocar `cost_analytics.py`, para respetar la frontera del 142).

**Símbolos EXACTOS a crear:**

```python
_HARVEST_BACKFILL_MAX_ROWS = 20000   # mismo cap que cost_analytics._MAX_ROWS

def _index_executions_by_session(session, since) -> dict[str, "AgentExecution"]:
    """Un solo query acotado a AgentExecution en la ventana; indexa por session_id
    tomado de md['codex_session_id'] y md['harness_telemetry']['session_id']."""
    from models import AgentExecution
    idx: dict[str, AgentExecution] = {}
    rows = (session.query(AgentExecution)
            .filter(AgentExecution.started_at >= since)
            .order_by(AgentExecution.id.desc())
            .limit(_HARVEST_BACKFILL_MAX_ROWS).all())
    for row in rows:
        md = row.metadata_dict
        for sid in (md.get("codex_session_id"),
                    (md.get("harness_telemetry") or {}).get("session_id")):
            if sid and sid not in idx:
                idx[sid] = row
    return idx

def _already_billable(md: dict) -> bool:
    """True si la fila ya tiene costo facturable o ya fue cosechada (idempotencia)."""
    from services.cost_analytics import extract_cost_row, _billable
    if md.get("telemetry_harvest_backfilled") is True:
        return True
    cr = extract_cost_row(md)
    return cr.cost_usd is not None and _billable(cr.cost_kind)

def backfill_from_harvest(runs: list[HarvestedRun], *, lookback_days: int) -> dict:
    """Matchea runs por session_id contra AgentExecution sin telemetría facturable
    y rellena harness_telemetry + model + procedencia. Idempotente. Devuelve
    {"scanned": N, "matched": M, "backfilled": K, "skipped_billable": S}.
    matched_ids: dict[dedup_key -> execution_id] para que F2 sepa cuáles NO van a la bitácora."""
    from db import session_scope
    since = datetime.utcnow() - timedelta(days=max(1, min(lookback_days, 3650)))
    scanned = matched = backfilled = skipped = 0
    matched_ids: dict[str, int] = {}
    with session_scope() as session:
        idx = _index_executions_by_session(session, since)
        for run in runs:
            scanned += 1
            if not run.session_id or run.session_id not in idx:
                continue
            row = idx[run.session_id]
            matched += 1
            matched_ids[run.dedup_key()] = row.id
            md = row.metadata_dict
            if _already_billable(md):
                skipped += 1
                continue
            md["harness_telemetry"] = run.to_harness_telemetry()
            if run.model and md.get("model") is None:
                md["model"] = run.model
            md["telemetry_harvest_backfilled"] = True
            md["telemetry_harvest"] = {
                "harvested_at": datetime.utcnow().isoformat() + "Z",
                "artifact": run.artifact, "source_format": run.source_format,
            }
            row.metadata_dict = md
            backfilled += 1
    return {"scanned": scanned, "matched": matched, "backfilled": backfilled,
            "skipped_billable": skipped, "matched_ids": matched_ids}
```

**Pseudocódigo de casos borde:**
- Run sin `session_id` → no matchea → no se toca DB.
- Ejecución ya facturable (reported/estimated) → `skipped_billable++`, no se sobreescribe (reportado gana).
- Segunda corrida → `telemetry_harvest_backfilled is True` → `_already_billable` True → skip. **Idempotente.**
- `harness_telemetry` escrito usa las MISMAS claves que `extract_cost_row` lee → el Centro de Costos lo clasifica (reported si vino cost real; estimated si se estimó).

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan199_harvest_backfill.py`** (usa DB de test; patrón de `test_plan158_claude_cli_cost_parity.py`):
- `test_backfill_matches_by_codex_session_id`: fixture AgentExecution con `md={"runtime":"codex_cli","codex_session_id":"s1"}` (sin harness_telemetry) + `HarvestedRun(session_id="s1", tokens_in=100, tokens_out=40)` → tras `backfill_from_harvest`, `md["harness_telemetry"]["input_tokens"]==100` y `extract_cost_row(md).cost_kind in ("estimated","reported")`.
- `test_backfill_matches_by_claude_session_id`: matchea vía `harness_telemetry.session_id` preexistente vacío... (fixture con `md={"runtime":"claude_code_cli","harness_telemetry":{"session_id":"c9"}}` y sin tokens) → se rellena.
- `test_backfill_idempotent`: correr 2×; segunda corrida `backfilled==0`, `skipped_billable>=1`.
- `test_backfill_skips_already_billable`: fixture con `harness_telemetry.total_cost_usd=1.23` (reported) → no se sobreescribe; `skipped_billable==1`.
- `test_backfill_unmatched_untouched`: run con `session_id="zzz"` sin ejecución → `matched==0`, DB intacta.
- `test_backfill_sets_provenance`: tras backfill, `md["telemetry_harvest"]["source_format"]` presente y `harness_telemetry["source"]=="harvest_disk"`.

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests/test_plan199_harvest_backfill.py -v` (desde backend). **Aceptación:** exit 0, todos PASSED.

**Flag que la protege:** `STACKY_TELEMETRY_HARVEST_ENABLED` (default ON) — el caller (F3/F0-autoscan) chequea la flag antes de invocar. La función en sí es pura de gate (no consulta la flag; el gate vive en el call-site, patrón del 158).

**Impacto por runtime + fallback:** matchea codex (por `codex_session_id`) y claude (por `harness_telemetry.session_id`); copilot no produce runs → no matchea (no-op). Fallback: sin ejecuciones en ventana → `matched=0`, sin escrituras.

**Trabajo del operador:** ninguno (lo dispara el auto-scan / botón).

---

### F2 — Bitácora durable de sesiones NO matcheadas (fuente "harvest")

**Objetivo (1 frase + valor).** Persistir en un JSONL durable las sesiones de disco que no matchean ninguna ejecución Stacky, deduplicadas y enmascaradas, para poder mostrarlas en el Centro de Costos como una **fuente separada** ("cosecha externa") sin contaminar los números por ticket.

**Archivo a EDITAR:** `Stacky Agents/backend/services/telemetry_harvest.py` (agregar; espeja el patrón de bitácora JSONL del 191/198 en `data_dir()`).

**Símbolos EXACTOS a crear:**

```python
def _ledger_path() -> Path:
    from runtime_paths import data_dir
    return data_dir() / "telemetry_harvest.jsonl"

def read_ledger_keys() -> set[str]:
    """Set de dedup_keys ya presentes (para no duplicar). Tolerante a líneas corruptas."""
    p = _ledger_path()
    keys: set[str] = set()
    if not p.is_file():
        return keys
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(json.loads(line).get("dedup_key"))
                except (ValueError, TypeError):
                    continue
    except OSError:
        return keys
    return keys

def _is_attributed(cwd: str | None, project_hint: str | None) -> bool:
    """True si la sesión cae bajo un workspace Stacky conocido. Compara project_hint
    contra los nombres de proyecto en projects_dir() y contra el basename de repo_root().
    Conservador: sin señales -> False."""
    from runtime_paths import projects_dir, repo_root
    if not project_hint:
        return False
    try:
        known = {d.name for d in projects_dir().iterdir()} if projects_dir().is_dir() else set()
        known.add(repo_root().name)
    except Exception:
        known = set()
    return project_hint in known

def append_to_ledger(runs: list[HarvestedRun], matched_ids: dict[str, int],
                     *, attributed_only: bool) -> dict:
    """Agrega al JSONL las runs NO matcheadas y aún no presentes. Idempotente por dedup_key.
    Si attributed_only=True, sólo agrega las atribuidas a Stacky. Devuelve
    {"appended": N, "skipped_dup": D, "skipped_unattributed": U}."""
    existing = read_ledger_keys()
    appended = skipped_dup = skipped_unattr = 0
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for run in runs:
        key = run.dedup_key()
        if key in matched_ids:          # ya rellenada en DB (F1) -> no va a la bitácora
            continue
        if key in existing:
            skipped_dup += 1
            continue
        attributed = _is_attributed(run.cwd, run.project_hint)
        if attributed_only and not attributed:
            skipped_unattr += 1
            continue
        existing.add(key)
        lines.append(json.dumps({
            "dedup_key": key, "runtime": run.runtime, "session_id": run.session_id,
            "model": run.model, "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
            "cache_read_tokens": run.cache_read_tokens, "total_cost_usd": run.total_cost_usd,
            "cost_estimated": run.cost_estimated,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "project_hint": run.project_hint, "attributed": attributed,
            "artifact": run.artifact, "source_format": run.source_format,
            "harvested_at": datetime.utcnow().isoformat() + "Z",
        }, ensure_ascii=False))
        appended += 1
    if lines:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return {"appended": appended, "skipped_dup": skipped_dup,
            "skipped_unattributed": skipped_unattr}

def load_ledger_records(*, source_attributed_only: bool = True) -> list["ExecRecord"]:
    """Convierte las líneas de la bitácora en ExecRecord SINTÉTICOS (execution_id negativo
    sentinel, ticket_id=None) para REUSAR ca.summarize/breakdown/burn sin tocarlos.
    Filtra por 'attributed' si source_attributed_only. Tolerante a líneas corruptas."""
    from services.cost_analytics import CostRow, ExecRecord
    p = _ledger_path()
    out: list[ExecRecord] = []
    if not p.is_file():
        return out
    neg = -1
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except (ValueError, TypeError):
                continue
            if source_attributed_only and not e.get("attributed"):
                continue
            cost = e.get("total_cost_usd")
            kind = ("estimated" if e.get("cost_estimated")
                    else ("reported" if cost is not None else "unknown"))
            started = None
            if e.get("started_at"):
                try:
                    started = datetime.fromisoformat(e["started_at"].replace("Z", ""))
                except ValueError:
                    started = None
            out.append(ExecRecord(
                execution_id=neg, ticket_id=None, ado_id=None,
                project=e.get("project_hint"), agent_type=None, status=None,
                started_at=started,
                row=CostRow(runtime=e.get("runtime"), model=e.get("model"),
                            tokens_in=e.get("tokens_in"), tokens_out=e.get("tokens_out"),
                            cache_read_tokens=e.get("cache_read_tokens"),
                            cost_usd=cost, cost_kind=kind, cache_savings_usd=None)))
            neg -= 1
    return out
```

**Nota de reuso clave:** `load_ledger_records` produce `ExecRecord` con el mismo shape que `load_records` → `ca.summarize(records)`, `ca.breakdown(records, dim)`, `ca.burn(records, bucket)` funcionan **sin modificarlos** (respeta la frontera del 142).

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan199_harvest_ledger.py`** (usa `tmp_path` + monkeypatch de `data_dir`):
- `test_append_dedup`: agregar la misma run 2× → segunda `appended==0`, `skipped_dup==1`.
- `test_append_skips_matched`: run cuyo `dedup_key` está en `matched_ids` → no se agrega.
- `test_attributed_only_filters`: run con `project_hint` desconocido y `attributed_only=True` → `skipped_unattributed==1`, archivo no la contiene.
- `test_ledger_masks_artifact`: la línea persistida no contiene rutas absolutas (solo basename) ni secretos.
- `test_load_ledger_records_shape`: tras append, `load_ledger_records` devuelve `ExecRecord` que `ca.summarize` agrega sin error.
- `test_ledger_tolerates_corrupt_line`: archivo con una línea basura → `read_ledger_keys`/`load_ledger_records` no lanzan.

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests/test_plan199_harvest_ledger.py -v`. **Aceptación:** exit 0.

**Flag:** `STACKY_TELEMETRY_HARVEST_ENABLED` (gate en call-site) + `STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY` (default ON) leído en el call-site F3 y pasado como `attributed_only`.

**Impacto por runtime + fallback:** cualquier runtime cuyo run no matchee cae acá; copilot no genera runs. Fallback: sin runs no matcheadas → `appended=0`, archivo no se crea.

**Trabajo del operador:** ninguno (default sólo atribuidas). Opt-in: apagar `ATTRIBUTED_ONLY` desde la UI para cosechar todo el disco.

---

### F3 — Endpoints HITL en el blueprint `metrics`

**Objetivo (1 frase + valor).** Exponer el scan bajo demanda (HITL) y la lectura agregada de la bitácora, con el mismo patrón gated de los endpoints del 142, para que la UI dispare y consuma la cosecha.

**Archivo a EDITAR:** `Stacky Agents/backend/api/metrics.py` (mismo blueprint `bp`, `url_prefix="/metrics"` → montado en `/api/metrics`).

**Símbolos/endpoints EXACTOS a crear:**

```python
def _harvest_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_TELEMETRY_HARVEST_ENABLED", False))

@bp.get("/telemetry-harvest/health")
def telemetry_harvest_health():
    """SIEMPRE 200 (la UI decide si muestra la sección). Patrón /cost-center/health."""
    return jsonify({"ok": True, "flag_enabled": _harvest_enabled()})

@bp.post("/telemetry-harvest/scan")
def telemetry_harvest_scan():
    """HITL — corre descubrimiento + backfill DB + bitácora. Devuelve conteos.
    Read-only sobre artefactos. Nunca 500 por artefacto inválido (degradación)."""
    if not _harvest_enabled():
        return jsonify({"enabled": False}), 200
    from services import telemetry_harvest as th
    lookback = int(getattr(_cfg, "STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS", 180))
    attributed_only = bool(getattr(_cfg, "STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY", True))
    runs = th.harvest_runs(lookback_days=lookback)
    bf = th.backfill_from_harvest(runs, lookback_days=lookback)
    led = th.append_to_ledger(runs, bf["matched_ids"], attributed_only=attributed_only)
    return jsonify({
        "ok": True, "enabled": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "discovered": len(runs),
        "backfill": {k: v for k, v in bf.items() if k != "matched_ids"},
        "ledger": led,
    })

@bp.get("/telemetry-harvest/summary")
def telemetry_harvest_summary():
    """Agrega la bitácora (fuente 'harvest') REUSANDO ca.summarize/breakdown.
    Query: attributed=1|0 (default 1), dimension=runtime|model|... (default runtime)."""
    if not _harvest_enabled():
        return jsonify({"enabled": False}), 200
    from services import telemetry_harvest as th
    attributed_only = request.args.get("attributed", "1") != "0"
    dim = (request.args.get("dimension") or "runtime").lower()
    if dim not in ("runtime", "model", "agent_type", "ticket", "project", "day"):
        return jsonify({"ok": False, "error": "invalid_dimension"}), 400
    records = th.load_ledger_records(source_attributed_only=attributed_only)
    return jsonify({
        "ok": True, "enabled": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "attributed_only": attributed_only,
        **ca.summarize(records, top_n=10),
        "breakdown": ca.breakdown(records, dim),
    })
```

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan199_harvest_api.py`** (Flask test client, patrón `test_cost_center_api.py`):
- `test_health_always_200`: GET `/api/metrics/telemetry-harvest/health` → 200, `flag_enabled` bool.
- `test_scan_flag_off`: con flag OFF → `{"enabled": false}`, 200; no toca disco.
- `test_scan_flag_on_empty_disk`: flag ON, discover monkeypatch→[] → 200, `discovered==0` (sin crash).
- `test_scan_backfills_and_returns_counts`: monkeypatch `harvest_runs`→[run matcheable] + fixture execution → `backfill.backfilled>=1`.
- `test_summary_invalid_dimension_400`: `?dimension=zzz` → 400 `invalid_dimension`.
- `test_summary_reuses_ca_aggregators`: con bitácora sembrada, la respuesta trae `billable_usd` y `breakdown.groups`.

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests/test_plan199_harvest_api.py -v`. **Aceptación:** exit 0.

**Flag:** `STACKY_TELEMETRY_HARVEST_ENABLED` (default ON). Los 3 endpoints la respetan (patrón `_cost_center_enabled`).

**Impacto por runtime + fallback:** transversal; fallback total = disco vacío → conteos 0.

**Trabajo del operador:** ninguno para leer; un click en "Escanear históricos" para re-scan manual (HITL).

---

### F0-bis — Auto-scan en background (no bloqueante) al arranque

**Objetivo (1 frase + valor).** Cosechar automáticamente una vez por arranque del backend, en un daemon thread capado, para que el operador tenga la data histórica sin hacer nada (cero trabajo), sin bloquear el arranque.

**Archivo a EDITAR:** `Stacky Agents/backend/app.py` (dentro de `create_app`, patrón del hook `_plan158_maybe_backfill_claude_model`).

**Símbolos EXACTOS a crear:**

```python
def _plan199_maybe_autoscan_harvest(logger) -> None:
    """Dispara UN scan en background por arranque. Gate: STACKY_TEST_MODE (no corre en tests),
    STACKY_TELEMETRY_HARVEST_ENABLED, STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED. Daemon thread,
    nunca bloquea. Excepción dura #3: los dirs de disco pueden faltar -> harvest degrada a 0."""
    import os, threading
    from config import config as _cfg
    if os.getenv("STACKY_TEST_MODE"):
        return
    if not getattr(_cfg, "STACKY_TELEMETRY_HARVEST_ENABLED", False):
        return
    if not getattr(_cfg, "STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED", False):
        return

    def _worker():
        try:
            from services import telemetry_harvest as th
            lookback = int(getattr(_cfg, "STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS", 180))
            attributed_only = bool(getattr(_cfg, "STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY", True))
            runs = th.harvest_runs(lookback_days=lookback)
            bf = th.backfill_from_harvest(runs, lookback_days=lookback)
            th.append_to_ledger(runs, bf["matched_ids"], attributed_only=attributed_only)
            logger.info("plan199 autoscan: discovered=%d backfilled=%d",
                        len(runs), bf["backfilled"])
        except Exception:
            logger.exception("plan199 autoscan: fallo no fatal")

    threading.Thread(target=_worker, name="plan199-harvest", daemon=True).start()
```

Llamada dentro de `create_app` **al final** (tras registrar blueprints), como el hook del 158.

**Test — `Stacky Agents/backend/tests/test_plan199_harvest_api.py`** (mismo archivo, sección autoscan):
- `test_autoscan_skipped_in_test_mode`: con `STACKY_TEST_MODE=1`, `_plan199_maybe_autoscan_harvest` no arranca thread (monkeypatch `threading.Thread` para contar llamadas → 0).
- `test_autoscan_gated_by_flags`: flag master OFF → no arranca.

**Comando/Aceptación:** dentro del pytest de F3 (mismo archivo).

**Flag:** `STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED` (default ON) + master. **Excepción dura #3 citada:** el prerequisito (dirs `~/.codex`/`~/.claude`) NO está garantizado; se resuelve con degradación graciosa (harvest → 0) y el thread es daemon no bloqueante, por eso es seguro dejarlo ON.

**Trabajo del operador:** ninguno (es el camino automático). Desactivable desde la UI si el operador prefiere sólo el botón.

---

### F4 — Más filtros (eje B): extensión aditiva de `CostFilters`

**Objetivo (1 frase + valor).** Agregar multi-runtime, multi-modelo, rango de costo y filtro de fuente (live/harvest) al Centro de Costos, sin romper los contratos congelados del 142.

**Archivos a EDITAR:**
- `Stacky Agents/backend/services/cost_analytics.py` — extender la dataclass `CostFilters` con campos **nuevos con default** (append-only) y aplicarlos en `load_records`.
- `Stacky Agents/backend/api/metrics.py` — extender `_parse_filters` para parsear los nuevos query params.
- `Stacky Agents/frontend/src/lib/costCenterTypes.ts` — extender `CostFiltersParams`.
- `Stacky Agents/frontend/src/api/endpoints.ts` — `costFiltersToQuery` (agregar los nuevos params).
- `Stacky Agents/frontend/src/components/costcenter/CostFiltersBar.tsx` — controles nuevos.

**Símbolos EXACTOS (backend, aditivos):**

```python
# En CostFilters (agregar AL FINAL, con default -> backward-compatible):
    runtimes: tuple[str, ...] = ()      # OR entre varios runtimes (csv). Coexiste con `runtime`.
    models: tuple[str, ...] = ()        # OR entre varios modelos (csv). Coexiste con `model`.
    min_cost_usd: float | None = None   # filtro Python: cost_usd >= min
    max_cost_usd: float | None = None   # filtro Python: cost_usd <= max
```

En `load_records`, tras construir `cr = extract_cost_row(md)` y antes de `out.append(...)`, agregar (aditivo, después de los filtros runtime/model/cost_kind existentes):

```python
    if f.runtimes and (cr.runtime or "") not in f.runtimes:
        continue
    if f.models and (cr.model or "") not in f.models:
        continue
    if f.min_cost_usd is not None and (cr.cost_usd is None or cr.cost_usd < f.min_cost_usd):
        continue
    if f.max_cost_usd is not None and (cr.cost_usd is None or cr.cost_usd > f.max_cost_usd):
        continue
```

En `filters_echo`, agregar al dict devuelto: `"runtimes": list(f.runtimes), "models": list(f.models), "min_cost_usd": f.min_cost_usd, "max_cost_usd": f.max_cost_usd`.

En `_parse_filters` (metrics.py), tras los existentes:

```python
    runtimes = tuple(s.strip() for s in (args.get("runtimes") or "").split(",") if s.strip())
    models = tuple(s.strip() for s in (args.get("models") or "").split(",") if s.strip())
    def _f(k):
        try: return float(args.get(k)) if args.get(k) else None
        except (TypeError, ValueError): return None
    # ... pasar runtimes=runtimes, models=models, min_cost_usd=_f("min_cost"), max_cost_usd=_f("max_cost")
```

**Símbolos EXACTOS (frontend, aditivos en `CostFiltersParams`):**
```ts
  runtimes?: string;   // csv
  models?: string;     // csv
  min_cost?: number;
  max_cost?: number;
  source?: "live" | "harvest" | "all";   // consumido por la UI (F6), no por load_records
```
En `costFiltersToQuery`: `if (params.runtimes) p.set("runtimes", params.runtimes)` etc. (`source` NO va a los endpoints del 142; lo usa F6 para elegir entre `CostCenter.summary` y `TelemetryHarvest.summary`).

**CostFiltersBar.tsx:** agregar inputs de texto "Runtimes (csv)" y "Modelos (csv)", dos `input type=number` "Costo min/max", y un `select` "Fuente" (live/harvest/all). **PROHIBIDO `style={{}}`** (ratchet inline-style; el archivo ya usa `styles.field` de CSS module — seguir ese patrón).

**Tests PRIMERO:**
- Backend `Stacky Agents/backend/tests/test_plan199_cost_filters_ext.py`:
  - `test_runtimes_multi_or`: records con runtime codex/claude/copilot; `CostFilters(runtimes=("codex_cli","claude_code_cli"))` → excluye copilot.
  - `test_models_multi_or`, `test_min_max_cost`, `test_filters_backward_compatible` (CostFilters() sin nuevos campos == comportamiento previo, byte-idéntico en el nº de records).
  - `test_parse_filters_new_params` (metrics `_parse_filters` con `runtimes=a,b&min_cost=0.5`).
- Frontend `Stacky Agents/frontend/src/lib/__tests__/costCenter.logic.test.ts` (extender): la lógica pura no cambia; el gate real de `.tsx` es tsc.

**Comandos:**
```
.\.venv\Scripts\python.exe -m pytest tests/test_plan199_cost_filters_ext.py -v
# frontend, POR ARCHIVO (contaminación cross-file conocida):
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/lib/__tests__/costCenter.logic.test.ts
npx tsc --noEmit -p tsconfig.json
```
**Aceptación BINARIA:** pytest exit 0 + `test_filters_backward_compatible` PASSED (prueba que lo viejo no cambió) + `tsc --noEmit` exit 0.

**Flag:** ninguna nueva (viven bajo `STACKY_COST_CENTER_ENABLED` existente; son filtros de una vista ya gateada).

**Impacto por runtime:** los filtros multi-runtime hacen visible/segmentable codex (que el legacy `_execution_costs` ignoraba — gotcha conocido); el filtro `source` separa live de cosecha. Fallback: params ausentes → comportamiento 142 idéntico.

**Trabajo del operador:** ninguno (opt-in de uso; defaults preservan la vista actual).

---

### F5 — Más gráficos (eje C): heatmap, serie apilada, distribución

**Objetivo (1 frase + valor).** Tres visualizaciones nuevas (serie apilada por runtime/modelo, heatmap día×hora, distribución de costo por corrida) para leer la telemetría con más profundidad, todas en SVG propio sin dependencia nueva (R5 del 142).

**Archivos a EDITAR/CREAR:**
- `Stacky Agents/backend/services/cost_analytics.py` — 3 agregadores puros nuevos (append-only).
- `Stacky Agents/backend/api/metrics.py` — 3 endpoints nuevos.
- `Stacky Agents/frontend/src/lib/costCenter.logic.ts` — helpers puros de math nuevos.
- `Stacky Agents/frontend/src/lib/costCenterTypes.ts` — tipos de respuesta nuevos.
- `Stacky Agents/frontend/src/api/endpoints.ts` — métodos nuevos en `CostCenter`.
- CREAR `Stacky Agents/frontend/src/components/costcenter/CostStackedBurnChart.tsx`, `CostHeatmap.tsx`, `CostDistributionChart.tsx` (+ sus `.module.css`).

**Símbolos EXACTOS (backend, puros):**

```python
def burn_stacked(records: list[ExecRecord], bucket: str, group_by: str) -> dict:
    """Como burn() pero cada punto trae 'groups': {group_key: billable_usd}. group_by in
    ('runtime','model','agent_type'). Reusa _bucket_start/_bucket_key/_bucket_step/_dim_key."""

def heatmap(records: list[ExecRecord]) -> dict:
    """Cells por (weekday 0..6, hour 0..23): {"cells":[{"weekday":D,"hour":H,
    "billable_usd":X,"runs":N}], "max_billable_usd":M}. Usa started_at; ignora None."""

def distribution(records: list[ExecRecord], bins: int) -> dict:
    """Histograma de cost_usd por corrida (solo cost_usd not None): {"bins":[{"lo":a,"hi":b,
    "count":n}], "total":T, "min":mn, "max":mx}. bins clamp 1..50."""
```

**Endpoints (metrics.py, gated por `_cost_center_enabled`, patrón idéntico a `/cost-breakdown`):**
```python
@bp.get("/cost-burn-stacked")   # ?bucket=day&group_by=runtime  -> ca.burn_stacked
@bp.get("/cost-heatmap")        # -> ca.heatmap
@bp.get("/cost-distribution")   # ?bins=20 -> ca.distribution
```
Cada uno: valida su parámetro (group_by in whitelist; bins int clamp), `records = ca.load_records(f)` con `_filters_or_error`, devuelve `{"ok":True,"enabled":True,"generated_at":...,**resultado}`. Con flag OFF → `{"enabled":false}`.

**Símbolos EXACTOS (frontend `costCenter.logic.ts`, puros, testeables con vitest):**
```ts
export function stackSeries(points: {bucket:string; groups:Record<string,number>}[], keys:string[]): ... // normaliza a barras apiladas
export function heatmapCells(cells: {weekday:number; hour:number; billable_usd:number}[], max:number): {weekday:number; hour:number; intensity:number}[]  // intensity 0..1
export function histogramLayout(bins:{lo:number;hi:number;count:number}[], width:number, height:number): {x:number;y:number;w:number;h:number}[]
```
(Reusan `scaleLinear`/`niceTicks`/`linePath` existentes.)

**Componentes .tsx (ratchet inline-style = 0):** usar `.module.css` para todo estilo; los atributos SVG (`x`, `y`, `width`, `height`, `fill`, `d`) son **atributos JSX de SVG, no la prop `style`** → permitidos por el ratchet (el ratchet sólo cuenta `style={{...}}`). Para color por intensidad, usar `fill={color}` con `color` derivado de un token CSS var (ej. `var(--status-info-text)` con `opacity` por intensidad vía atributo `fillOpacity`), **nunca** un hex literal (gate anti-drift 141). Patrón de referencia ya en `CostBurnChart.tsx`.

**Tests PRIMERO:**
- Backend `Stacky Agents/backend/tests/test_plan199_cost_charts.py`:
  - `test_burn_stacked_groups_sum_matches_billable`: la suma de `groups` de cada punto == `billable_usd` de burn() para el mismo bucket.
  - `test_heatmap_cells_bounds`: weekday 0..6, hour 0..23; `max_billable_usd` == max de cells.
  - `test_distribution_bins_clamp`: `bins=999` → clamp 50; counts suman == nº de records con costo.
  - `test_charts_empty_records`: los 3 con `[]` → estructuras vacías, sin crash.
- Frontend `Stacky Agents/frontend/src/lib/__tests__/costCenterCharts.logic.test.ts` (NUEVO):
  - `stackSeries`/`heatmapCells`/`histogramLayout` con inputs conocidos → outputs deterministas.

**Comandos:**
```
.\.venv\Scripts\python.exe -m pytest tests/test_plan199_cost_charts.py -v
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/lib/__tests__/costCenterCharts.logic.test.ts
npx tsc --noEmit -p tsconfig.json
```
**Aceptación BINARIA:** pytest exit 0 + vitest del archivo exit 0 + tsc exit 0.

**Flag:** `STACKY_COST_CENTER_ENABLED` (existente); los 3 endpoints la respetan.

**Impacto por runtime:** `group_by=runtime` hace visible la contribución de codex/claude/copilot lado a lado. Fallback: sin data → series/cells/bins vacíos.

**Trabajo del operador:** ninguno.

---

### F6 — Wiring de UI: sección "Cosecha histórica" + filtros + gráficos en el Centro de Costos

**Objetivo (1 frase + valor).** Integrar todo lo anterior en la página existente `CostCenterPage.tsx`: el botón HITL de scan, el filtro de fuente, la sección de cosecha externa, y los 3 gráficos nuevos.

**Archivos a EDITAR/CREAR:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — namespace nuevo `TelemetryHarvest` (`health`, `scan`, `summary`) + métodos nuevos en `CostCenter` (`burnStacked`, `heatmap`, `distribution`). Usar `api.get`/`api.post` (los endpoints devuelven 2xx siempre; el discriminante `enabled` narrowea, patrón del 142). **Gotcha:** `api.get/post` (client.ts) lanza en non-2xx; como estos endpoints devuelven 200 incluso deshabilitados (`{enabled:false}`), es correcto usarlos.
- `Stacky Agents/frontend/src/lib/costCenterTypes.ts` — interfaces de respuesta nuevas (`HarvestScanResult`, `HarvestSummary`, `BurnStacked`, `Heatmap`, `Distribution`).
- `Stacky Agents/frontend/src/pages/CostCenterPage.tsx` — montar: `<CostFiltersBar>` (ya extendido en F4), los charts nuevos, y una `<HarvestSection>` con botón "Escanear históricos" (llama `TelemetryHarvest.scan`, invalida las queries react-query al terminar) + tabla/KPIs de la fuente harvest gated por `TelemetryHarvest.health`.
- CREAR `Stacky Agents/frontend/src/components/costcenter/HarvestSection.tsx` (+ `.module.css`).

**Contrato de la sección de cosecha:**
- Al montar, `useQuery(["harvest","health"], TelemetryHarvest.health)`; si `flag_enabled=false`, la sección no se muestra (patrón `probeFlagHealth` del 142/171).
- Botón "Escanear históricos" → `useMutation(TelemetryHarvest.scan)`; on success muestra `discovered/backfilled/appended` y hace `queryClient.invalidateQueries(["cost-center"])` (para que los KPIs live reflejen el backfill) y `["harvest"]`.
- Toggle "Incluir no atribuidas" → cambia `attributed` en `TelemetryHarvest.summary`.

**Ratchet inline-style = 0:** `HarvestSection.tsx` y los 3 charts nuevos son archivos .tsx NUEVOS → alcance de inline-style DEBE ser 0. Usar `.module.css` + `className`; para valores dinámicos imperativos (ej. ancho de barra) usar atributos SVG o `ref`+`useEffect` imperativo, **nunca** `style={{}}`.

**Nav:** `costcenter` ya existe en `shellNav.ts` (grupo "observabilidad", gated `costCenterEnabled`). **No** se agrega tab nueva (la cosecha vive dentro del Centro de Costos). Frontera 171 respetada (tampoco agrega tab).

**Tests:** el gate real de `.tsx` es **tsc** (RTL/jsdom no instalados — gap estructural conocido). Toda la lógica testeable ya vive en F5 (`costCenterCharts.logic.test.ts`) y F4.

**Comando/Aceptación BINARIA:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit -p tsconfig.json
```
exit 0. Smoke visual manual: `/costcenter` renderiza los 3 gráficos + la sección de cosecha; el botón devuelve conteos.

**Flag:** `STACKY_COST_CENTER_ENABLED` (contenedor) + `STACKY_TELEMETRY_HARVEST_ENABLED` (sección cosecha).

**Impacto por runtime:** la UI muestra los 3 runtimes en los gráficos y separa live/harvest. Fallback: flag harvest OFF → sólo se ven los gráficos live nuevos.

**Trabajo del operador:** ninguno (la data ya llega por auto-scan); el botón es re-scan opcional (HITL).

---

### F7 — Flags (5-6 lugares), registro de tests y docs

**Objetivo (1 frase + valor).** Cablear las 5 flags nuevas en todos los lugares que los ratchets exigen y registrar los test files, para que el arnés quede verde y el operador pueda ver/tocar todo desde la UI.

**Flags a crear (nombres EXACTOS y default):**

| Flag | Tipo | Default | Requires | Excepción |
|---|---|---|---|---|
| `STACKY_TELEMETRY_HARVEST_ENABLED` | bool | **ON** | — | ninguna (endpoints read-only; degradan a vacío) |
| `STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED` | bool | **ON** | `STACKY_TELEMETRY_HARVEST_ENABLED` | **#3 citada** (prereq de disco no garantizado → degradación graciosa; daemon no bloqueante) |
| `STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY` | bool | **ON** | `STACKY_TELEMETRY_HARVEST_ENABLED` | ninguna (privacidad por default) |
| `STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS` | int | **180** (bounds 1..3650) | `STACKY_TELEMETRY_HARVEST_ENABLED` | ninguna |
| `STACKY_TELEMETRY_HARVEST_ROOTS_JSON` | json | **""** | `STACKY_TELEMETRY_HARVEST_ENABLED` | ninguna |

**Lugares de cableado (receta verificada en este repo):**
1. **`Stacky Agents/backend/config.py`** — atributo por flag (patrón línea 555): bools `os.getenv(K,"true"/"false").strip().lower()=="true"`; int `int(os.getenv(K,"180") or "180")` con try/except; json/str `os.getenv(K,"").strip()`.
2. **`Stacky Agents/backend/services/harness_flags.py`** — un `FlagSpec` por flag dentro de `FLAG_REGISTRY`. Bools default-ON llevan `default=True`. El **int NO lleva `default=`** (declarar `min_value=1, max_value=3650`) — un default declarado de cualquier tipo lo trata como "curado" y exigiría alta en `_CURATED_DEFAULTS_ON`; el default efectivo vive en config.py. El json/str **NO** lleva `default=`. Los 4 no-master llevan `requires="STACKY_TELEMETRY_HARVEST_ENABLED"`. Grupo `group="observabilidad_notif"`.
3. **`Stacky Agents/backend/services/harness_flags.py` → `_CATEGORY_KEYS["observabilidad_notif"]`** (línea ~262) — agregar las 5 keys (o el meta-test `test_every_registry_flag_is_categorized` se pone rojo).
4. **`Stacky Agents/backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON`** (línea 467) — agregar SÓLO las 3 **bools default-ON** (`STACKY_TELEMETRY_HARVEST_ENABLED`, `_AUTOSCAN_ENABLED`, `_ATTRIBUTED_ONLY`). El int y el json **NO** van acá (no declaran `default=` en FlagSpec). Si no, `test_default_known_only_for_curated` rojo.
5. **`Stacky Agents/backend/tests/test_harness_flags_requires.py` → `_REQUIRES_MAP_FROZEN`** (línea 120) — agregar las 4 aristas `{"STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED":"STACKY_TELEMETRY_HARVEST_ENABLED", ...}` para las 4 no-master. Si no, `test_requires_map_is_frozen` rojo.
6. **`Stacky Agents/backend/tests/test_harness_flags_bounds.py` → `_FROZEN_BOUNDS`** (línea 149) — agregar `"STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS": (1, 3650)`. Si no, `test_bounds_map_is_frozen` rojo. (Nota: este test ya arrastra deuda de flags int foráneas; agregá SÓLO tu arista.)

**Registro de test files — `Stacky Agents/backend/scripts/run_harness_tests.sh` → `HARNESS_TEST_FILES=(...)`** (línea 20): agregar las 6 líneas:
```
  tests/test_plan199_harvest_discovery.py
  tests/test_plan199_harvest_backfill.py
  tests/test_plan199_harvest_ledger.py
  tests/test_plan199_harvest_api.py
  tests/test_plan199_cost_filters_ext.py
  tests/test_plan199_cost_charts.py
```
Si no, `test_harness_ratchet_meta.py` (meta-test) se pone rojo.

**Tests PRIMERO — `Stacky Agents/backend/tests/test_plan199_flags.py`:**
- `test_all_five_flags_in_registry`: las 5 keys están en `FLAG_REGISTRY`.
- `test_defaults_effective`: `config.STACKY_TELEMETRY_HARVEST_ENABLED is True`, `_AUTOSCAN True`, `_ATTRIBUTED_ONLY True`, `_LOOKBACK_DAYS==180`, `_ROOTS_JSON==""`.
- `test_curated_contains_three_bools` / `test_int_not_curated`.
- `test_requires_edges_present` / `test_bounds_edge_present`.
(Registrar TAMBIÉN este archivo en `HARNESS_TEST_FILES` → 7 líneas en total.)

**Comando/Aceptación BINARIA (el arnés entero de flags verde):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_harness_flags_bounds.py tests/test_harness_ratchet_meta.py tests/test_plan199_flags.py -v
```
exit 0, todos PASSED.

**Impacto por runtime:** las flags son transversales; `ROOTS_JSON` permite instalaciones con `~/.codex`/`~/.claude` relocalizados por runtime.

**Trabajo del operador:** ninguno (defaults ON seguros); todo visible/editable desde Configuración → Arnés (categoría Observabilidad).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación (en qué fase) |
|---|---|---|
| R1 | Los dirs `~/.codex`/`~/.claude` no existen (instalación default) | Excepción dura #3 citada; descubridores → `[]`; nunca crash (F0). |
| R2 | Formato JSONL de codex/claude cambia o es desconocido | Parser tolerante línea-a-línea (skip inválidas); extrae "lo que se pueda" (mismo criterio que `from_codex_event`); si no hay uso → run con tokens=None (F0). |
| R3 | Ingesta de la actividad personal (no-Stacky) del operador contamina la vista | `ATTRIBUTED_ONLY=ON` por default; bitácora SEPARADA; nunca entra a `billable_usd` por ticket (F2). |
| R4 | Secretos/paths sensibles en los artefactos filtran a la UI | Sólo se persisten números + ids; `cwd`→basename; `secret_scanner.scan_secrets` descarta strings sospechosos; nunca se ingiere texto de prompt/respuesta (F0/principio 7). |
| R5 | Cosecha masiva bloquea el arranque o consume recursos | Daemon thread + caps (`_HARVEST_MAX_FILES=5000`, `_MAX_BYTES_PER_FILE=25MB`, `_MAX_LINES_PER_FILE=50000`, lookback 180d) (F0/F0-bis). |
| R6 | Doble ingesta / duplicados | Backfill con marca `telemetry_harvest_backfilled` + `_already_billable`; bitácora con `dedup_key`; idempotente (F1/F2). |
| R7 | Sobreescribir un costo real reportado con una estimación de disco | `_already_billable` protege: reportado siempre gana; sólo se rellena lo `unknown`/vacío (F1). |
| R8 | Colisión con 171 al tocar `CostFilters`/agregadores | 199 sólo AGREGA campos con default y funciones nuevas; 171 agrega `completed_at` (atributo distinto) — merge aditivo; ver §10 (F4/F5). |
| R9 | Ratchets rojos (flags/tests/inline-style) | Receta de 5-6 lugares documentada (F7) + archivos .tsx nuevos con CSS modules (F5/F6). |
| R10 | `github_copilot` sin artefacto local rompe la paridad | Discoverer no-op documentado; la paridad es "3 discoverers, uno degrada explícitamente" (F0). |

---

## 6. Fuera de scope (lo que 199 NO hace)

- **No** corrige la producción de telemetría de runs nuevos (eso es 158, ya implementado).
- **No** re-deriva `cost_kind` ni reescribe `extract_cost_row`/`summarize`/`burn`/`breakdown` (contrato congelado del 142).
- **No** agrega salud/tendencias/baselines/umbrales/traza ni endpoints `/ops-*` (eso es 171).
- **No** interpreta la telemetría con LLM (117), ni notificaciones/alertas/enforcement (142 §6 / 171).
- **No** hace shell-out a `ccusage`/`codeburn` ni agrega dependencias (reusa el precedente de lectura de archivo local del 142 F7).
- **No** modifica los artefactos del runtime (read-only estricto).
- **No** agrega tab de navegación nueva (vive dentro del Centro de Costos).
- **No** toca `_execution_costs`/`/ticket-costs`/`/project-costs` legacy.
- **No** RBAC/multiusuario.

---

## 7. Glosario, orden de implementación y DoD

### Glosario (dominio Stacky)
- **Runtime:** motor CLI que ejecuta al agente. Valores canónicos: `codex_cli`, `claude_code_cli`, `github_copilot`.
- **Artefacto de sesión:** archivo JSONL que el CLI del runtime deja en disco con el uso de tokens de una conversación (`rollout-*.jsonl` en codex; `<uuid>.jsonl` en claude).
- **`harness_telemetry`:** clave canónica en `AgentExecution.metadata_json` con `RunTelemetry.to_dict()` (runtime, session_id, tokens, costo, cost_estimated). Fuente única del Centro de Costos.
- **`extract_cost_row(md)`:** extractor puro del 142 que reconcilia las 3 fuentes de costo en una `CostRow` con `cost_kind` ∈ {reported, estimated, nominal, unknown}.
- **Backfill:** rellenar telemetría faltante en filas históricas. 158 = DB→DB (una clave). 199 = disco→DB (telemetría completa faltante) + bitácora para lo no matcheable.
- **Cosecha (harvest):** descubrir+parsear los artefactos de sesión de disco.
- **Atribuida:** sesión cuyo `cwd` cae bajo un workspace/proyecto Stacky conocido.
- **Fuente (source):** `live` = telemetría en DB (142); `harvest` = bitácora de cosecha externa (199).

### Orden de implementación (numerado, por dependencia)
1. **F0** — `telemetry_harvest.py`: dataclass + discoverers + parsers + masking (test discovery). *Base de todo.*
2. **F1** — backfill matched a DB (test backfill).
3. **F2** — bitácora durable + `load_ledger_records` (test ledger).
4. **F3** — endpoints `/telemetry-harvest/*` (test api).
5. **F0-bis** — auto-scan background en `create_app` (tests en el archivo de F3).
6. **F4** — extensión de `CostFilters` + `_parse_filters` + UI filtros (test filters_ext + tsc).
7. **F5** — 3 agregadores puros + 3 endpoints + helpers logic.ts + tipos (test charts + vitest + tsc).
8. **F6** — wiring UI: `HarvestSection` + 3 charts en `CostCenterPage` + endpoints.ts (tsc + smoke).
9. **F7** — flags (5-6 lugares) + registro de 7 test files + docs (test flags + arnés verde).

> F4 y F5 no dependen de F0-F3 (sólo del 142) → pueden ir en paralelo tras F0. F6 depende de F3+F4+F5. F7 al final.

### Definición de Hecho (DoD) global
- [ ] Los 7 archivos de test `test_plan199_*.py` PASSED con el venv `.\.venv\Scripts\python.exe -m pytest <archivo> -v` (uno por uno).
- [ ] `test_harness_flags.py`, `test_harness_flags_requires.py`, `test_harness_flags_bounds.py`, `test_harness_ratchet_meta.py` verdes tras el cableado.
- [ ] `npx tsc --noEmit` exit 0; `npx vitest run` de los 2 archivos de lógica nuevos exit 0 (POR ARCHIVO).
- [ ] Ratchet inline-style = 0 en los 4 .tsx nuevos (`HarvestSection`, `CostStackedBurnChart`, `CostHeatmap`, `CostDistributionChart`).
- [ ] Correr el scan 2× no duplica (idempotencia): `backfilled==0` y `ledger.appended==0` en la 2ª corrida.
- [ ] Con `~/.codex` y `~/.claude` ausentes, el backend arranca normal y `/telemetry-harvest/scan` devuelve `discovered==0` sin error (excepción #3, degradación graciosa).
- [ ] Ningún archivo bajo `~/.codex`/`~/.claude` fue modificado (read-only verificado).
- [ ] Las 5 flags visibles y editables en Configuración → Arnés → Observabilidad.
- [ ] `/api/metrics/cost-reconciliation-audit` muestra `runs_audited` mayor y/o `codex_invisible_usd` atribuido tras el primer scan (K1/K3).
- [ ] Smoke visual: `/costcenter` renderiza serie apilada, heatmap y distribución + sección "Cosecha histórica" con botón funcional.

---

## 8. Contratos que este plan CONGELA (para el crítico y el implementador)

- **Store canónico intacto:** la telemetría cosechada se escribe con las MISMAS claves que `extract_cost_row` ya lee (`harness_telemetry.{runtime,total_cost_usd,input_tokens,output_tokens,cache_read_tokens,cost_estimated}` + `model` top-level). Ningún cambio de esquema.
- **Reuso de agregadores:** `load_ledger_records` produce `ExecRecord` con el shape exacto de `load_records` → `ca.summarize/breakdown/burn` se usan sin modificar.
- **Aditividad de `CostFilters`:** los 4 campos nuevos tienen default `()`/`None` → todo caller previo (incl. 171) sigue funcionando byte-idéntico.
- **Procedencia:** `harness_telemetry.source == "harvest_disk"` distingue cosechado de live para toda auditoría futura.

---

## 9. Mapa de colisiones (resumen)

- **vs 142 (IMPLEMENTADO):** REUSA `extract_cost_row`, `CostRow`, `ExecRecord`, `CostFilters`, `load_records`, `summarize`, `burn`, `breakdown`, `_billable`, `estimate_cost`, endpoints/flag `STACKY_COST_CENTER_ENABLED`. AGREGA (append-only) 4 campos a `CostFilters` + 3 agregadores + 3 endpoints. NO reescribe ninguno.
- **vs 158 (IMPLEMENTADO):** cierra el hueco que 158 §6 declaró irrecuperable-desde-DB, cosechando desde disco. NO toca `_finalize_cost_telemetry`, `backfill_claude_model_key`, ni sus flags.
- **vs 171 (PROPUESTO):** frontera dura — 199 NO hace salud/tendencias/baselines/umbrales/traza ni `/ops-*`. Ambos agregan a `CostFilters`/`ExecRecord` pero sobre atributos DISTINTOS (171: `completed_at`; 199: `runtimes/models/min_cost/max_cost`) → merge aditivo sin conflicto. Si 171 se implementa primero, 199 rebasea sus 4 campos al final de la dataclass.

## 10. Notas de merge (si se implementa junto a 171/196/197)
- `CostFilters` y `api/metrics.py _parse_filters`: ambos planes ANEXAN; conservar todas las líneas de ambos (unión aditiva). Tras merge, correr `compileall` + `pytest tests/test_plan199_cost_filters_ext.py` + `test_cost_analytics_aggregate.py` para detectar duplicados silenciosos (gotcha merge 3-way).
- `run_harness_tests.sh HARNESS_TEST_FILES`: unión de líneas; no re-ordenar.
- `_CURATED_DEFAULTS_ON` / `_REQUIRES_MAP_FROZEN` / `_FROZEN_BOUNDS`: unión de claves; ordenar alfabéticamente para minimizar conflictos.
