"""Plan 169 F1 — Store del optimizador evolutivo (§4.1-§4.4).

Persistencia tolerante bajo `data_dir()/evolution/optimizer/`:
  runs.json      — lista completa de OptimizationRun (JSON entero, mutable con lock)
  archive.jsonl  — una línea por ArchiveEntry (append-only; el lineage NUNCA se borra)
  lessons.jsonl  — una línea por MutationLesson (append-only)
  pareto.json    — dict {aspect_key: [ParetoPoint, ...]} (frente vigente por aspecto)

Reglas duras (espejo de evolution_store §4.1 / case_store 168): `runtime_paths.data_dir()`
en CADA operación (sin cache de módulo — los tests lo monkeypatchean); lecturas tolerantes
(ausente/corrupto → vacío); escrituras bajo `_OPTIMIZER_LOCK`. Regla JSONL (C9): una línea
no parseable SE SALTEA (no vacía el archivo — una línea rota jamás borra el lineage).
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import runtime_paths

_OPTIMIZER_LOCK = threading.Lock()
_ARCHIVE_TEXT_MAX_CHARS = 20000
_PARETO_MAX = 8
_PARETO_PARENTS = 2
_STALE_RUN_HOURS = 2  # C6: reaper de runs huérfanos (contrato, no prosa)

VALID_RUN_STATUSES = ("running", "completed", "no_improvement",
                      "stopped_budget", "cancelled", "error")
TERMINAL_RUN_STATUSES = frozenset({"completed", "no_improvement",
                                   "stopped_budget", "cancelled", "error"})
VALID_VERDICTS = ("base", "winner", "pareto", "dominated", "invalid")
VALID_KINDS = ("base", "variant")
VALID_LESSON_OUTCOMES = ("mejoro", "empeoro", "igual", "invalida")
VALID_GENERATOR_MODES = ("local", "runtime")

_STEPS_CAP = 60


# ── Paths ────────────────────────────────────────────────────────────────────
def optimizer_root() -> Path:
    return runtime_paths.data_dir() / "evolution" / "optimizer"


def _runs_path() -> Path:
    return optimizer_root() / "runs.json"


def _archive_path() -> Path:
    return optimizer_root() / "archive.jsonl"


def _lessons_path() -> Path:
    return optimizer_root() / "lessons.jsonl"


def _pareto_path() -> Path:
    return optimizer_root() / "pareto.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── IO tolerante (NO toman el lock — el caller lo hace) ──────────────────────
def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — archivo corrupto no tumba el flujo
        return []


def _write_json_list(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_json_dict(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    """C9 — línea corrupta SE SALTEA; nunca vacía el archivo/lineage."""
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except Exception:  # noqa: BLE001
        return out
    return out


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ── Runs ─────────────────────────────────────────────────────────────────────
def _new_run_shape(**fields) -> dict:
    """Llena TODAS las claves de §4.2 (SIEMPRE presentes)."""
    now = fields.get("started_at") or _now_iso()
    return {
        "id": fields.get("id") or ("opt-" + uuid4().hex),
        "aspect_key": fields.get("aspect_key"),
        "target_ref": fields.get("target_ref"),
        "status": fields.get("status", "running"),
        "error": fields.get("error"),
        "cancel_requested": bool(fields.get("cancel_requested", False)),
        "generator": fields.get("generator") or {"mode": None, "runtime": None, "model": None},
        "use_judge": bool(fields.get("use_judge", True)),
        "variants_planned": int(fields.get("variants_planned", 3)),
        "variants_done": int(fields.get("variants_done", 0)),
        "base": fields.get("base"),
        "winner": fields.get("winner"),
        "proposal_id": fields.get("proposal_id"),
        "parent_proposal_id": fields.get("parent_proposal_id"),
        "margin_used": fields.get("margin_used", 0.02),
        "rng_seed": fields.get("rng_seed"),
        "base_hash": fields.get("base_hash"),
        "budget": fields.get("budget") or {
            "limit_tokens": 60000, "tokens_est_in": 0, "tokens_est_out": 0, "exhausted": False,
        },
        "steps": list(fields.get("steps") or []),
        "started_at": now,
        "finished_at": fields.get("finished_at"),
    }


def create_run(**fields) -> dict:
    """Crea un OptimizationRun (status="running"). ValueError("invalid_run:<campo>")
    si aspect_key/target_ref/generator.mode/status son inválidos."""
    run = _new_run_shape(**fields, status="running")
    if not isinstance(run["aspect_key"], str) or not run["aspect_key"]:
        raise ValueError("invalid_run:aspect_key")
    if not isinstance(run["target_ref"], str) or not run["target_ref"]:
        raise ValueError("invalid_run:target_ref")
    gen = run["generator"]
    if not isinstance(gen, dict) or gen.get("mode") not in VALID_GENERATOR_MODES:
        raise ValueError("invalid_run:generator")
    if run["status"] not in VALID_RUN_STATUSES:
        raise ValueError("invalid_run:status")
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
        runs.append(run)
        _write_json_list(_runs_path(), runs)
    return dict(run)


def get_run(run_id: str) -> dict | None:
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
    return next((dict(r) for r in runs if r.get("id") == run_id), None)


def list_runs(limit: int = 20) -> list[dict]:
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
    runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return [dict(r) for r in runs[: max(0, int(limit))]]


def update_run(run_id: str, **patch) -> dict:
    """Patch superficial de claves EXISTENTES de §4.2. Clave desconocida → ValueError;
    status fuera de VALID_RUN_STATUSES → ValueError. KeyError("run_not_found") si no existe."""
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
        idx = next((i for i, r in enumerate(runs) if r.get("id") == run_id), None)
        if idx is None:
            raise KeyError("run_not_found")
        run = runs[idx]
        for key in patch:
            if key not in run:
                raise ValueError(f"invalid_run:{key}")
        if "status" in patch and patch["status"] not in VALID_RUN_STATUSES:
            raise ValueError("invalid_run:status")
        run.update(patch)
        runs[idx] = run
        _write_json_list(_runs_path(), runs)
        return dict(run)


def append_step(run_id: str, text: str) -> None:
    """Append tolerante con tope EXACTO de 60 (§4.2, C10)."""
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
        idx = next((i for i, r in enumerate(runs) if r.get("id") == run_id), None)
        if idx is None:
            return
        steps = runs[idx].setdefault("steps", [])
        n = len(steps)
        if n >= _STEPS_CAP:
            return  # no-op
        if n == _STEPS_CAP - 1:
            steps.append({"ts": _now_iso(), "text": "log truncado"})
        else:  # n <= 58
            steps.append({"ts": _now_iso(), "text": str(text)})
        _write_json_list(_runs_path(), runs)


def request_cancel(run_id: str) -> dict:
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
        idx = next((i for i, r in enumerate(runs) if r.get("id") == run_id), None)
        if idx is None:
            raise KeyError("run_not_found")
        if runs[idx].get("status") in TERMINAL_RUN_STATUSES:
            raise ValueError("run_not_running")
        runs[idx]["cancel_requested"] = True
        _write_json_list(_runs_path(), runs)
        return dict(runs[idx])


def _parse_iso(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def any_run_running() -> bool:
    """C6 — reaper de huérfanos: cierra como error todo run 'running' más viejo que
    _STALE_RUN_HOURS antes de responder si queda algún 'running'."""
    with _OPTIMIZER_LOCK:
        runs = _read_json_list(_runs_path())
        now = datetime.now(timezone.utc)
        changed = False
        for run in runs:
            if run.get("status") != "running":
                continue
            started = _parse_iso(run.get("started_at"))
            if started is not None and (now - started) > timedelta(hours=_STALE_RUN_HOURS):
                run["status"] = "error"
                run["error"] = "stale_run_reaped"
                run["finished_at"] = now.isoformat()
                steps = run.setdefault("steps", [])
                if len(steps) < _STEPS_CAP:
                    steps.append({"ts": now.isoformat(), "text": "run huérfano cerrado por reaper"})
                changed = True
        if changed:
            _write_json_list(_runs_path(), runs)
        return any(r.get("status") == "running" for r in runs)


# ── Archive ──────────────────────────────────────────────────────────────────
def _new_archive_shape(**fields) -> dict:
    return {
        "id": fields.get("id") or ("var-" + uuid4().hex),
        "run_id": fields.get("run_id"),
        "aspect_key": fields.get("aspect_key"),
        "target_ref": fields.get("target_ref"),
        "parent_id": fields.get("parent_id"),
        "kind": fields.get("kind"),
        "artifact_hash": fields.get("artifact_hash"),
        "artifact_text": fields.get("artifact_text"),
        "fitness": fields.get("fitness"),
        "cost_proxy": fields.get("cost_proxy", 0),
        "verdict": fields.get("verdict"),
        "invalid_reason": fields.get("invalid_reason"),
        "critique_summary": fields.get("critique_summary"),
        "mutation_lesson": fields.get("mutation_lesson"),
        "generator_model": fields.get("generator_model"),
        "created_at": fields.get("created_at") or _now_iso(),
    }


def append_archive_entry(**fields) -> dict:
    entry = _new_archive_shape(**fields)
    if entry["kind"] not in VALID_KINDS:
        raise ValueError("invalid_archive:kind")
    if entry["verdict"] not in VALID_VERDICTS:
        raise ValueError("invalid_archive:verdict")
    text = entry.get("artifact_text")
    if text is not None:
        if not entry.get("artifact_hash"):
            entry["artifact_hash"] = _sha256(text)
        if len(text) > _ARCHIVE_TEXT_MAX_CHARS:
            entry["artifact_text"] = None  # se conserva el hash
    with _OPTIMIZER_LOCK:
        _append_jsonl(_archive_path(), entry)
    return dict(entry)


def read_archive(run_id: str | None = None, aspect_key: str | None = None,
                 limit: int = 50) -> list[dict]:
    rows = _read_jsonl(_archive_path())
    if run_id is not None:
        rows = [r for r in rows if r.get("run_id") == run_id]
    if aspect_key is not None:
        rows = [r for r in rows if r.get("aspect_key") == aspect_key]
    rows.reverse()  # más nuevo primero
    return rows[: max(0, int(limit))]


# ── Lessons ──────────────────────────────────────────────────────────────────
def append_lesson(**fields) -> dict:
    lesson = {
        "id": fields.get("id") or ("les-" + uuid4().hex),
        "run_id": fields.get("run_id"),
        "aspect_key": fields.get("aspect_key"),
        "variant_id": fields.get("variant_id"),
        "text": fields.get("text"),
        "outcome": fields.get("outcome"),
        "delta": fields.get("delta"),
        "created_at": fields.get("created_at") or _now_iso(),
    }
    if lesson["outcome"] not in VALID_LESSON_OUTCOMES:
        raise ValueError("invalid_lesson:outcome")
    with _OPTIMIZER_LOCK:
        _append_jsonl(_lessons_path(), lesson)
    return dict(lesson)


def read_lessons_tail(aspect_key: str | None = None, limit: int = 20) -> list[dict]:
    rows = _read_jsonl(_lessons_path())
    if aspect_key is not None:
        rows = [r for r in rows if r.get("aspect_key") == aspect_key]
    rows.reverse()
    return rows[: max(0, int(limit))]


# ── Frente Pareto (§4.4) ─────────────────────────────────────────────────────
def _dominates(a: dict, b: dict) -> bool:
    """`a` domina a `b` sii a.score>=b.score y a.cost<=b.cost y (a.score>b.score o a.cost<b.cost)."""
    return (a["score"] >= b["score"] and a["cost_proxy"] <= b["cost_proxy"]
            and (a["score"] > b["score"] or a["cost_proxy"] < b["cost_proxy"]))


def pareto_front(points: list[dict]) -> list[dict]:
    """PURA — dominancia §4.4; orden determinista total (score DESC, cost ASC, variant_id ASC).
    Puntos con score None NUNCA entran."""
    pts = [p for p in points if p.get("score") is not None]
    front = [p for p in pts if not any(_dominates(q, p) for q in pts if q is not p)]
    front = sorted(front, key=lambda p: (-p["score"], p["cost_proxy"], str(p.get("variant_id") or "")))
    return front


def _pareto_point(p: dict) -> dict:
    return {
        "variant_id": p.get("variant_id"),
        "run_id": p.get("run_id"),
        "score": p.get("score"),
        "cost_proxy": p.get("cost_proxy"),
        "artifact_hash": p.get("artifact_hash"),
        "created_at": p.get("created_at") or _now_iso(),
    }


def get_pareto(aspect_key: str) -> list[dict]:
    data = _read_json_dict(_pareto_path())
    front = data.get(aspect_key)
    return list(front) if isinstance(front, list) else []


def update_pareto(aspect_key: str, new_points: list[dict]) -> list[dict]:
    """Merge frente_previo + new_points → pareto_front → poda _PARETO_MAX (§4.4)."""
    with _OPTIMIZER_LOCK:
        data = _read_json_dict(_pareto_path())
        prev = data.get(aspect_key)
        prev = list(prev) if isinstance(prev, list) else []
        merged = prev + [_pareto_point(p) for p in (new_points or [])]
        front = pareto_front(merged)
        # Poda determinista total: front ya viene score DESC / cost ASC / variant_id ASC,
        # así que quedarse con los primeros _PARETO_MAX elimina los de MENOR score
        # (empate → mayor cost primero; doble empate → variant_id mayor primero) (C12).
        if len(front) > _PARETO_MAX:
            front = front[:_PARETO_MAX]
        data[aspect_key] = front
        _write_json_dict(_pareto_path(), data)
        return list(front)


def sample_parents(aspect_key: str, exclude_hash: str, rng) -> list[dict]:
    """Hasta _PARETO_PARENTS puntos del frente sin exclude_hash, con rng.sample."""
    front = get_pareto(aspect_key)
    candidates = [p for p in front if p.get("artifact_hash") != exclude_hash]
    if not candidates:
        return []
    k = min(_PARETO_PARENTS, len(candidates))
    return list(rng.sample(candidates, k))
