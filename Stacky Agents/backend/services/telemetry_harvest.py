"""Plan 199 F0 — Cosecha de telemetría histórica desde los artefactos en disco.

Los CLIs dejan en disco todo lo que gastaron: codex escribe `rollout-*.jsonl` en
`~/.codex/sessions` y Claude Code sus transcripts en `~/.claude/projects`. Todo
lo que se corrió antes de que Stacky existiera —o fuera de Stacky— está ahí y no
figura en ningún tablero. Este módulo lo descubre y lo normaliza.

Es PURO: descubre, lee y normaliza. No toca la base ni escribe nada; la ingesta
es otra fase. Y no reimplementa la extracción de campos donde ya existe: los
eventos de codex pasan por el MISMO `from_codex_event` que la captura en vivo,
así una diferencia de criterio entre histórico y live es imposible por
construcción.

Reglas duras:
- Ningún runtime ausente rompe nada: sin la carpeta, el descubridor devuelve [].
- Nunca sale una ruta absoluta: solo el basename, y pasado por el escáner de
  secretos (un directorio puede llamarse como un token).
- Todo `started_at` se normaliza a naive-UTC: comparar naive contra aware es un
  TypeError esperando a pasar.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("stacky.services.telemetry_harvest")

__all__ = [
    "HarvestedRun",
    "discover_codex_rollouts",
    "discover_claude_transcripts",
    "discover_copilot_sessions",
    "parse_codex_rollout",
    "parse_claude_transcript",
    "harvest",
    "backfill_from_harvest",
]

_HARVEST_MAX_FILES = 5000
_HARVEST_MAX_BYTES_PER_FILE = 25 * 1024 * 1024
_HARVEST_MAX_LINES_PER_FILE = 50000


@dataclass
class HarvestedRun:
    runtime: str
    session_id: str | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cache_read_tokens: int | None
    total_cost_usd: float | None
    cost_estimated: bool
    started_at: datetime | None
    project_hint: str | None
    cwd: str | None
    artifact: str
    source_format: str
    num_events: int
    num_turns: int | None = None

    def to_harness_telemetry(self) -> dict:
        """Las claves EXACTAS que lee `extract_cost_row` de `harness_telemetry`.

        `source` marca la procedencia para que un run cosechado no se confunda
        nunca con uno capturado en vivo.
        """
        return {
            "runtime": self.runtime,
            "session_id": self.session_id,
            "total_cost_usd": self.total_cost_usd,
            "input_tokens": self.tokens_in,
            "output_tokens": self.tokens_out,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_estimated": self.cost_estimated,
            "num_turns": self.num_turns,
            "source": "harvest_disk",
        }

    def dedup_key(self) -> str:
        return f"{self.runtime}:{self.session_id or self.artifact}"


# ---------------------------------------------------------------------------
# Raíces
# ---------------------------------------------------------------------------

def _roots_override() -> dict:
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
    return root if root.is_dir() else None


def _claude_projects_root() -> Path | None:
    ov = _roots_override().get("claude_code_cli")
    if ov:
        p = Path(ov).expanduser()
        return p if p.is_dir() else None
    root = Path.home() / ".claude" / "projects"
    return root if root.is_dir() else None


# ---------------------------------------------------------------------------
# Descubridores
# ---------------------------------------------------------------------------

def _iter_jsonl(root: Path, pattern: str, since: datetime, limit: int) -> list:
    """rglob capado y filtrado por mtime. Nunca lanza: un permiso denegado en una
    carpeta cualquiera no puede voltear la cosecha entera."""
    out: list = []
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
    try:
        return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    except OSError:
        return out[:limit]


def discover_codex_rollouts(since: datetime, limit: int = _HARVEST_MAX_FILES) -> list:
    root = _codex_sessions_root()
    return _iter_jsonl(root, "rollout-*.jsonl", since, limit) if root else []


def discover_claude_transcripts(since: datetime, limit: int = _HARVEST_MAX_FILES) -> list:
    root = _claude_projects_root()
    return _iter_jsonl(root, "*.jsonl", since, limit) if root else []


def discover_copilot_sessions(since: datetime, limit: int = _HARVEST_MAX_FILES) -> list:
    """FALLBACK EXPLÍCITO: Copilot corre por un bridge HTTP y no deja sesión local.

    Devuelve [] a propósito y lo dice en el log. No es un olvido de paridad: no
    hay artefacto que cosechar. Si algún día aparece un log local, se agrega acá.
    """
    logger.info("telemetry_harvest: github_copilot no persiste sesiones locales "
                "(bridge HTTP); nada que cosechar")
    return []


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def _to_naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_ts(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(float(value))
        s = str(value).strip().replace("Z", "+00:00")
        return _to_naive_utc(datetime.fromisoformat(s))
    except (ValueError, TypeError, OSError):
        return None


def _mask_path(raw: str | None) -> str | None:
    """Solo el basename, y redactado si parece un secreto.

    Una ruta absoluta en un tablero filtra la estructura del disco del operador;
    y un directorio puede llamarse como una credencial.
    """
    if not raw:
        return None
    try:
        from services.secret_scanner import scan_secrets

        base = os.path.basename(str(raw).rstrip("/\\")) or str(raw)
        return "<redacted>" if scan_secrets(base) else base
    except Exception:  # noqa: BLE001 — enmascarar nunca puede romper la cosecha
        return "<redacted>"


def _finalize_cost(run: HarvestedRun, model: str | None) -> None:
    """Estima el costo solo si el artefacto no lo trae. Lo reportado siempre gana."""
    if run.total_cost_usd is not None:
        return
    if run.tokens_in is None and run.tokens_out is None:
        return
    try:
        from harness.pricing import estimate_cost

        est = estimate_cost(model, run.tokens_in, run.tokens_out)
    except Exception:  # noqa: BLE001
        est = None
    if est is not None:
        run.total_cost_usd = est
        run.cost_estimated = True


def _mtime_naive(path: Path):
    try:
        return datetime.utcfromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _oversize(path: Path, etiqueta: str) -> bool:
    try:
        if path.stat().st_size > _HARVEST_MAX_BYTES_PER_FILE:
            logger.warning("telemetry_harvest: %s oversize, skip %s", etiqueta, path.name)
            return True
    except OSError:
        return True
    return False


def _iter_eventos(path: Path):
    """Líneas JSON del artefacto, tolerando parciales y corruptas.

    El CLI puede estar escribiendo el archivo mientras se lee: una línea a medias
    es normal, no un error.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= _HARVEST_MAX_LINES_PER_FILE:
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(ev, dict):
                yield ev


def parse_codex_rollout(path: Path) -> HarvestedRun | None:
    """Agrega un rollout de codex reusando el extractor de la captura en vivo."""
    from harness.telemetry import from_codex_event

    if _oversize(path, "codex rollout"):
        return None

    tin = tout = tcache = 0
    saw_usage = False
    session_id = model = total_cost = num_turns = started = cwd_raw = None
    n = 0
    try:
        for ev in _iter_eventos(path):
            n += 1
            t = from_codex_event(ev)
            if t.input_tokens or t.output_tokens or t.cache_read_tokens:
                saw_usage = True
                tin += t.input_tokens or 0
                tout += t.output_tokens or 0
                tcache += t.cache_read_tokens or 0
            if session_id is None and t.session_id:
                session_id = t.session_id
            if num_turns is None and t.num_turns:
                num_turns = t.num_turns
            if t.total_cost_usd is not None:
                total_cost = t.total_cost_usd   # el acumulado del CLI: gana el último
            m = ev.get("model") or (ev.get("item") or {}).get("model")
            if model is None and m:
                model = m
            if started is None:
                started = _parse_ts(ev.get("timestamp") or ev.get("ts") or ev.get("time"))
            if cwd_raw is None:
                cwd_raw = ev.get("cwd") or (ev.get("item") or {}).get("cwd")
    except OSError:
        return None

    run = HarvestedRun(
        runtime="codex_cli", session_id=session_id, model=model,
        tokens_in=(tin if saw_usage else None),
        tokens_out=(tout if saw_usage else None),
        cache_read_tokens=(tcache if saw_usage else None),
        total_cost_usd=total_cost, cost_estimated=False,
        started_at=started or _mtime_naive(path),
        project_hint=_mask_path(cwd_raw), cwd=_mask_path(cwd_raw),
        artifact=_mask_path(path.name) or "<artifact>",
        source_format="codex_rollout", num_events=n, num_turns=num_turns,
    )
    _finalize_cost(run, model)
    return run


def parse_claude_transcript(path: Path) -> HarvestedRun | None:
    """Agrega el uso de un transcript de Claude Code.

    OJO: el transcript NO tiene la forma que espera `from_claude_stream` (ese lee
    `usage` en el tope). Acá el uso vive por línea, dentro de
    `message.usage` de los eventos `type == "assistant"`. Reusar el extractor de
    live sobre este formato devolvería ceros en silencio.
    """
    if _oversize(path, "claude transcript"):
        return None

    tin = tout = tcache = 0
    saw_usage = False
    session_id = model = started = cwd_raw = None
    n = 0
    try:
        for ev in _iter_eventos(path):
            n += 1
            if session_id is None and ev.get("sessionId"):
                session_id = ev.get("sessionId")
            if cwd_raw is None and ev.get("cwd"):
                cwd_raw = ev.get("cwd")
            if started is None:
                started = _parse_ts(ev.get("timestamp"))
            if ev.get("type") != "assistant":
                continue
            msg = ev.get("message") or {}
            usage = msg.get("usage") or {}
            if model is None and msg.get("model"):
                model = msg.get("model")
            itok, otok = usage.get("input_tokens"), usage.get("output_tokens")
            ctok = usage.get("cache_read_input_tokens")
            if itok or otok or ctok:
                saw_usage = True
                tin += itok or 0
                tout += otok or 0
                tcache += ctok or 0
    except OSError:
        return None

    run = HarvestedRun(
        runtime="claude_code_cli", session_id=session_id or (path.stem or None),
        model=model,
        tokens_in=(tin if saw_usage else None),
        tokens_out=(tout if saw_usage else None),
        cache_read_tokens=(tcache if saw_usage else None),
        # El transcript no trae un costo confiable: se estima aguas abajo.
        total_cost_usd=None, cost_estimated=False,
        started_at=started or _mtime_naive(path),
        project_hint=_mask_path(cwd_raw), cwd=_mask_path(cwd_raw),
        artifact=_mask_path(path.name) or "<artifact>",
        source_format="claude_transcript", num_events=n, num_turns=None,
    )
    _finalize_cost(run, model)
    return run


def harvest(since: datetime, limit: int = _HARVEST_MAX_FILES) -> list:
    """Cosecha los 3 runtimes y devuelve los runs deduplicados, más nuevos primero."""
    runs: list = []
    for path in discover_codex_rollouts(since, limit):
        run = parse_codex_rollout(path)
        if run is not None:
            runs.append(run)
    for path in discover_claude_transcripts(since, limit):
        run = parse_claude_transcript(path)
        if run is not None:
            runs.append(run)
    discover_copilot_sessions(since, limit)   # deja constancia del fallback

    vistos: set = set()
    unicos: list = []
    for run in runs:
        clave = run.dedup_key()
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(run)

    unicos.sort(key=lambda r: r.started_at or datetime.min, reverse=True)
    return unicos


# ---------------------------------------------------------------------------
# Backfill — la única parte que toca la base
# ---------------------------------------------------------------------------

_HARVEST_BACKFILL_MAX_ROWS = 20000   # mismo cap que cost_analytics


def _index_executions_by_session(session, since) -> dict:
    """Indexa las ejecuciones de la ventana por session_id, en UNA sola query.

    Un run cosechado se ata a su ejecución por el id de sesión del CLI, que
    puede estar en dos lugares según el runtime.
    """
    from models import AgentExecution

    idx: dict = {}
    filas = (
        session.query(AgentExecution)
        .filter(AgentExecution.started_at >= since)
        .order_by(AgentExecution.id.desc())
        .limit(_HARVEST_BACKFILL_MAX_ROWS)
        .all()
    )
    for fila in filas:
        md = fila.metadata_dict or {}
        for sid in (md.get("codex_session_id"),
                    (md.get("harness_telemetry") or {}).get("session_id")):
            if sid and sid not in idx:
                idx[sid] = fila
    return idx


def _already_billable(md: dict) -> bool:
    """¿Esta fila ya tiene costo real, o ya la cosechamos antes?

    Lo reportado por el CLI en vivo SIEMPRE gana sobre lo que se lea del disco:
    pisarlo con una estimación sería degradar un dato bueno.
    """
    from services.cost_analytics import _billable, extract_cost_row

    if (md or {}).get("telemetry_harvest_backfilled") is True:
        return True
    fila = extract_cost_row(md or {})
    return fila.cost_usd is not None and _billable(fila.cost_kind)


def backfill_from_harvest(runs: list, *, lookback_days: int,
                          dry_run: bool = False) -> dict:
    """Rellena la telemetría de las ejecuciones que quedaron sin costo.

    Idempotente: la marca `telemetry_harvest_backfilled` hace que una segunda
    corrida no toque nada. Con `dry_run=True` computa los MISMOS conteos sin
    escribir — es el preview que el operador ve antes de decidir.
    """
    from datetime import timedelta

    from db import session_scope

    since = datetime.utcnow() - timedelta(days=max(1, min(int(lookback_days or 1), 3650)))
    scanned = matched = backfilled = skipped = 0
    matched_ids: dict = {}

    with session_scope() as session:
        idx = _index_executions_by_session(session, since)
        for run in runs or []:
            scanned += 1
            if not run.session_id or run.session_id not in idx:
                continue
            fila = idx[run.session_id]
            matched += 1
            matched_ids[run.dedup_key()] = fila.id

            md = fila.metadata_dict or {}
            if _already_billable(md):
                skipped += 1
                continue

            if not dry_run:
                md["harness_telemetry"] = run.to_harness_telemetry()
                if run.model and md.get("model") is None:
                    md["model"] = run.model
                md["telemetry_harvest_backfilled"] = True
                md["telemetry_harvest"] = {
                    "harvested_at": datetime.utcnow().isoformat() + "Z",
                    "artifact": run.artifact,
                    "source_format": run.source_format,
                }
                fila.metadata_dict = md
            # Se cuenta igual en preview: es "cuántas rellenaría".
            backfilled += 1

    return {
        "scanned": scanned, "matched": matched, "backfilled": backfilled,
        "skipped_billable": skipped, "dry_run": dry_run, "matched_ids": matched_ids,
    }


# ---------------------------------------------------------------------------
# Bitácora de lo NO matcheado
# ---------------------------------------------------------------------------

def _ledger_path() -> Path:
    return Path(data_dir()) / "telemetry_harvest.jsonl"


def read_ledger_keys() -> set:
    """dedup_keys ya presentes. Tolerante: una línea corrupta no invalida el resto."""
    path = _ledger_path()
    keys: set = set()
    if not path.is_file():
        return keys
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    clave = json.loads(line).get("dedup_key")
                except (ValueError, TypeError):
                    continue
                if clave:
                    keys.add(clave)
    except OSError:
        return keys
    return keys


def _is_attributed(cwd: str | None, project_hint: str | None) -> bool:
    """¿Esta sesión salió de un workspace que Stacky conoce?

    Conservador a propósito: sin señal clara devuelve False. Marcar como propia
    una sesión ajena metería gasto de otro proyecto en los números del operador.
    """
    if not project_hint:
        return False
    try:
        from runtime_paths import projects_dir, repo_root

        conocidos = set()
        carpeta = projects_dir()
        if carpeta.is_dir():
            conocidos = {d.name for d in carpeta.iterdir()}
        conocidos.add(repo_root().name)
    except Exception:  # noqa: BLE001
        return False
    return project_hint in conocidos


def append_to_ledger(runs: list, matched_ids: dict, *, attributed_only: bool,
                     dry_run: bool = False) -> dict:
    """Agrega a la bitácora lo que NO matcheó ninguna ejecución.

    Es una fuente SEPARADA a propósito: son sesiones que no pertenecen a ningún
    ticket, y mezclarlas con los números por ticket los volvería mentira.
    Idempotente por dedup_key.
    """
    existentes = read_ledger_keys()
    agregadas = dup = sin_atribuir = 0
    lineas: list = []

    for run in runs or []:
        clave = run.dedup_key()
        if clave in (matched_ids or {}):
            continue          # ya se rellenó en la base (F1): no va a la bitácora
        if clave in existentes:
            dup += 1
            continue
        atribuida = _is_attributed(run.cwd, run.project_hint)
        if attributed_only and not atribuida:
            sin_atribuir += 1
            continue

        existentes.add(clave)
        lineas.append(json.dumps({
            "dedup_key": clave, "runtime": run.runtime, "session_id": run.session_id,
            "model": run.model, "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
            "cache_read_tokens": run.cache_read_tokens,
            "total_cost_usd": run.total_cost_usd, "cost_estimated": run.cost_estimated,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "project_hint": run.project_hint, "attributed": atribuida,
            "artifact": run.artifact, "source_format": run.source_format,
            "harvested_at": datetime.utcnow().isoformat() + "Z",
        }, ensure_ascii=False))
        agregadas += 1

    if lineas and not dry_run:
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lineas) + "\n")

    return {"appended": agregadas, "skipped_dup": dup,
            "skipped_unattributed": sin_atribuir, "dry_run": dry_run}


def load_ledger_records(*, source_attributed_only: bool = True) -> list:
    """La bitácora como `ExecRecord` sintéticos, para reusar los agregadores del 142.

    El `execution_id` es negativo: son sesiones sin ejecución, y un id positivo
    chocaría con una real. Así `summarize`/`breakdown`/`burn` funcionan sin
    tocarles una línea.
    """
    from services.cost_analytics import CostRow, ExecRecord

    path = _ledger_path()
    salida: list = []
    if not path.is_file():
        return salida

    sentinela = -1
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(e, dict):
                    continue
                if source_attributed_only and not e.get("attributed"):
                    continue
                costo = e.get("total_cost_usd")
                clase = ("estimated" if e.get("cost_estimated")
                         else ("reported" if costo is not None else "unknown"))
                salida.append(ExecRecord(
                    execution_id=sentinela, ticket_id=None, ado_id=None,
                    project=e.get("project_hint"), agent_type=None, status=None,
                    started_at=_parse_ts(e.get("started_at")),
                    row=CostRow(
                        runtime=e.get("runtime"), model=e.get("model"),
                        tokens_in=e.get("tokens_in"), tokens_out=e.get("tokens_out"),
                        cache_read_tokens=e.get("cache_read_tokens"),
                        cost_usd=costo, cost_kind=clase, cache_savings_usd=None),
                ))
                sentinela -= 1
    except OSError:
        return salida
    return salida


def harvest_runs(*, lookback_days: int) -> list:
    """Atajo del call-site: cosecha la ventana configurada."""
    from datetime import timedelta

    since = datetime.utcnow() - timedelta(days=max(1, min(int(lookback_days or 1), 3650)))
    return harvest(since)
