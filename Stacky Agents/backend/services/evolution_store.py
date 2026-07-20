"""Plan 167 F1 — Store puro del Centro de Evolución.

Persistencia de aspectos, propuestas, ciclos y ledger bajo
`data_dir()/evolution/`, con máquina de estados validada y auditoría
append-only. SIN Flask y SIN side-effects de artefactos (eso vive en
`evolution_apply`, F2). Espeja el patrón de `incident_store` (Plan 131):
JSON tolerante + lock global.

Reglas duras (§4.1):
- `runtime_paths.data_dir()` se llama en CADA operación (sin cache a nivel
  módulo) para que los tests lo monkeypatcheen.
- Lecturas tolerantes: archivo ausente/corrupto → valor vacío.
- Escrituras bajo `_EVOLUTION_LOCK` (threading.Lock NO reentrante: los
  helpers `_read_*`/`_write_*`/`_append_*` NO toman el lock; el lock se
  adquiere UNA sola vez en cada función pública de escritura).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import runtime_paths

logger = logging.getLogger("stacky.evolution")

_EVOLUTION_LOCK = threading.Lock()

# C2 — allowlist dura de campos patcheables fuera de la máquina de estados.
_PATCHABLE_FIELDS = frozenset(
    {"title", "rationale", "snapshot_info", "fitness_before", "fitness_after"}
)

# §3.1 — closed_loop NO es un valor válido (prohibido para siempre en Stacky).
VALID_LOOP_MODES = frozenset({"human_in_the_loop", "human_on_the_loop"})
VALID_STATUSES = ("draft", "pending_review", "approved", "applied", "rejected", "rolled_back")
VALID_ORIGINS = ("manual", "agent", "optimizer", "mape")
VALID_ARTIFACT_TYPES = ("free_text", "knowledge_note", "prompt_file", "flag_change")
APPLIABLE_ARTIFACT_TYPES = frozenset({"knowledge_note", "prompt_file"})

TRANSITIONS: dict[str, dict] = {
    "submit":   {"from": ("draft",), "to": "pending_review"},
    "approve":  {"from": ("pending_review",), "to": "approved"},
    "reject":   {"from": ("draft", "pending_review", "approved"), "to": "rejected"},
    "apply":    {"from": ("approved",), "to": "applied"},
    "rollback": {"from": ("applied",), "to": "rolled_back"},
}


class InvalidTransition(ValueError):
    """La acción pedida no es válida desde el estado actual de la propuesta."""


# ── Seeds (§4.2 tabla F1) ───────────────────────────────────────────────────
_SEED_ASPECTS: tuple[dict, ...] = (
    {
        "id": "agent_prompts",
        "name": "Prompts y agentes de Stacky",
        "description": (
            "Los archivos .agent.md del runtime (backend/Stacky/agents/) que definen a "
            "cada agente. Se mejoran editando el prompt del agente con aprobación humana."
        ),
        "target_kind": "prompt_file",
        "loop_mode": "human_in_the_loop",
        "links": [],
    },
    {
        "id": "config_flags_models",
        "name": "Flags del arnés y selección de modelo/costo",
        "description": (
            "Los toggles del arnés y la elección de modelo/effort por tarea. Se mejoran "
            "cambiando la flag en el panel del Arnés (único camino de escritura de flags)."
        ),
        "target_kind": "flag_change",
        "loop_mode": "human_in_the_loop",
        "links": [{"label": "Abrir Configuración del Arnés", "href": "/settings"}],
    },
    {
        "id": "knowledge_rag",
        "name": "Conocimiento y lecciones (RAG)",
        "description": (
            "Lecciones aprendidas de fallos y patrones, persistidas en "
            "data_dir()/evolution/lessons.jsonl. Se mejoran agregando notas de "
            "conocimiento reversibles; el Plan 170 las promueve al corpus RAG."
        ),
        "target_kind": "knowledge_note",
        "loop_mode": "human_in_the_loop",
        "links": [],
    },
    {
        "id": "stacky_codebase",
        "name": "Código de Stacky (pipeline de planes)",
        "description": (
            "El código de Stacky. El pipeline proponer→criticar→implementar→supervisar YA "
            "existe y se visualiza en el Tablero de Planes (Plan 128); este aspecto solo lo "
            "enlaza en modo lectura, no re-orquesta nada."
        ),
        "target_kind": "link_only",
        "loop_mode": "human_in_the_loop",
        "links": [{"label": "Abrir Tablero de Planes", "href": "/planes"}],
    },
)


# ── Kill-switch env-only (A1, §8.0) ─────────────────────────────────────────
def evolution_hard_disabled() -> bool:
    """A1 — freno de emergencia FUERA del alcance de flags/propuestas.

    Lee `STACKY_EVOLUTION_HARD_DISABLE` en CADA llamada (testabilidad con
    monkeypatch.setenv). NO aparece en el registry del Arnés.
    """
    return os.getenv("STACKY_EVOLUTION_HARD_DISABLE", "").strip().lower() in ("1", "true", "yes")


# ── Paths ───────────────────────────────────────────────────────────────────
def evolution_root() -> Path:
    return runtime_paths.data_dir() / "evolution"


def _aspects_path() -> Path:
    return evolution_root() / "aspects.json"


def _proposals_path() -> Path:
    return evolution_root() / "proposals.json"


def _cycles_path() -> Path:
    return evolution_root() / "cycles.jsonl"


def _ledger_path() -> Path:
    return evolution_root() / "ledger.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── IO helpers (NO toman el lock — el caller lo hace) ───────────────────────
def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — archivo corrupto no debe tumbar el flujo
        return []


def _write_json_list(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
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
            except Exception:  # noqa: BLE001 — línea corrupta se ignora
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


# ── Aspectos ────────────────────────────────────────────────────────────────
def ensure_seed_aspects() -> list[dict]:
    """Idempotente: crea los 4 seeds si faltan; NO pisa existentes."""
    with _EVOLUTION_LOCK:
        aspects = _read_json_list(_aspects_path())
        existing = {a.get("id") for a in aspects}
        changed = False
        for seed in _SEED_ASPECTS:
            if seed["id"] not in existing:
                aspects.append({**seed, "links": list(seed["links"]), "created_at": _now_iso()})
                changed = True
        if changed:
            _write_json_list(_aspects_path(), aspects)
        return list(aspects)


def save_aspect(aspect: dict) -> dict:
    """Valida y upsert de un aspecto por id. Rechaza loop_mode inválido
    (incluye `closed_loop`, prohibido para siempre — §3.1, test F1 caso 11)."""
    mode = aspect.get("loop_mode")
    if mode not in VALID_LOOP_MODES:
        raise ValueError("loop_mode_invalido")
    normalized = {
        "id": aspect["id"],
        "name": aspect.get("name", ""),
        "description": aspect.get("description", ""),
        "target_kind": aspect.get("target_kind", "link_only"),
        "loop_mode": mode,
        "links": list(aspect.get("links") or []),
        "created_at": aspect.get("created_at") or _now_iso(),
    }
    with _EVOLUTION_LOCK:
        aspects = _read_json_list(_aspects_path())
        idx = next((i for i, a in enumerate(aspects) if a.get("id") == normalized["id"]), None)
        if idx is None:
            aspects.append(normalized)
        else:
            aspects[idx] = normalized
        _write_json_list(_aspects_path(), aspects)
    return normalized


def list_aspects() -> list[dict]:
    return ensure_seed_aspects()


def get_aspect(aspect_id: str) -> dict | None:
    for a in list_aspects():
        if a.get("id") == aspect_id:
            return a
    return None


# ── Ledger ──────────────────────────────────────────────────────────────────
def _normalize_event(event: dict) -> dict:
    return {
        "ts": event.get("ts") or _now_iso(),
        "event": event.get("event"),
        "proposal_id": event.get("proposal_id"),
        "action": event.get("action"),
        "from": event.get("from"),
        "to": event.get("to"),
        "actor": event.get("actor"),
        "note": event.get("note"),
        "cycle_id": event.get("cycle_id"),
    }


def _ledger_log_mirror(ev: dict) -> None:
    """A2 — espejo de auditoría en los logs del sistema (best-effort, jamás rompe)."""
    try:
        logger.info("evolution_ledger %s", json.dumps(ev, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass


def append_ledger(event: dict) -> None:
    ev = _normalize_event(event)
    with _EVOLUTION_LOCK:
        _append_jsonl(_ledger_path(), ev)
    _ledger_log_mirror(ev)


def read_ledger_tail(limit: int = 50) -> list[dict]:
    """Más nuevo primero, respetando `limit`."""
    events = _read_jsonl(_ledger_path())
    events.reverse()
    return events[: max(0, limit)]


# ── Ciclos ──────────────────────────────────────────────────────────────────
def append_cycle(record: dict) -> None:
    with _EVOLUTION_LOCK:
        _append_jsonl(_cycles_path(), record)


def read_cycles_tail(limit: int = 20) -> list[dict]:
    records = _read_jsonl(_cycles_path())
    records.reverse()
    return records[: max(0, limit)]


# ── Propuestas ──────────────────────────────────────────────────────────────
def _new_proposal_shape(**kw) -> dict:
    return {
        "id": kw["id"],
        "aspect_id": kw["aspect_id"],
        "title": kw["title"],
        "rationale": kw["rationale"],
        "origin": kw["origin"],
        "artifact_type": kw["artifact_type"],
        "target_ref": kw.get("target_ref"),
        "proposed_content": kw.get("proposed_content"),
        "base_hash": kw.get("base_hash"),
        "evidence": list(kw.get("evidence") or []),
        "status": kw["status"],
        "fitness_before": None,
        "fitness_after": None,
        "parent_proposal_id": kw.get("parent_proposal_id"),
        "cycle_id": kw.get("cycle_id"),
        "snapshot_info": None,
        "notes": [],
        "created_at": kw["created_at"],
        "updated_at": kw["updated_at"],
        "applied_at": None,
        "rolled_back_at": None,
    }


def create_proposal(
    *,
    aspect_id: str,
    title: str,
    rationale: str,
    origin: str,
    artifact_type: str,
    target_ref: str | None = None,
    proposed_content: str | None = None,
    evidence: list[str] | None = None,
    initial_status: str = "pending_review",
    cycle_id: str | None = None,
    parent_proposal_id: str | None = None,
    base_hash: str | None = None,
    actor: str = "operator",
) -> dict:
    # Validaciones (sin lock — get_aspect toma el lock por su cuenta).
    if get_aspect(aspect_id) is None:
        raise ValueError("invalid_payload:aspect_id")
    if origin not in VALID_ORIGINS:
        raise ValueError("invalid_payload:origin")
    if artifact_type not in VALID_ARTIFACT_TYPES:
        raise ValueError("invalid_payload:artifact_type")
    if initial_status not in ("draft", "pending_review"):
        raise ValueError("invalid_payload:initial_status")
    if artifact_type in ("knowledge_note", "prompt_file"):
        if not proposed_content or not str(proposed_content).strip():
            raise ValueError("invalid_payload:proposed_content")
    if artifact_type == "prompt_file":
        if not target_ref or not str(target_ref).strip():
            raise ValueError("invalid_payload:target_ref")

    now = _now_iso()
    pid = "prop-" + uuid4().hex
    proposal = _new_proposal_shape(
        id=pid, aspect_id=aspect_id, title=title, rationale=rationale,
        origin=origin, artifact_type=artifact_type, target_ref=target_ref,
        proposed_content=proposed_content, base_hash=base_hash, evidence=evidence,
        status=initial_status, parent_proposal_id=parent_proposal_id, cycle_id=cycle_id,
        created_at=now, updated_at=now,
    )
    event = _normalize_event({
        "event": "created", "proposal_id": pid, "action": None,
        "from": None, "to": initial_status, "actor": actor,
        "note": None, "cycle_id": cycle_id,
    })
    with _EVOLUTION_LOCK:
        proposals = _read_json_list(_proposals_path())
        proposals.append(proposal)
        _write_json_list(_proposals_path(), proposals)
        _append_jsonl(_ledger_path(), event)
    _ledger_log_mirror(event)
    return proposal


def list_proposals(status: str | None = None, aspect_id: str | None = None,
                   origin: str | None = None) -> list[dict]:
    with _EVOLUTION_LOCK:
        proposals = _read_json_list(_proposals_path())
    out = [
        p for p in proposals
        if (status is None or p.get("status") == status)
        and (aspect_id is None or p.get("aspect_id") == aspect_id)
        and (origin is None or p.get("origin") == origin)
    ]
    out.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    return out


def get_proposal(proposal_id: str) -> dict | None:
    with _EVOLUTION_LOCK:
        proposals = _read_json_list(_proposals_path())
    return next((p for p in proposals if p.get("id") == proposal_id), None)


def transition(proposal_id: str, action: str, *, actor: str, note: str | None = None) -> dict:
    """Valida contra TRANSITIONS. NO ejecuta side-effects de archivos (eso es
    evolution_apply, F2). Persiste status/updated_at/notes/applied_at/
    rolled_back_at y deja el evento en el ledger."""
    if action not in TRANSITIONS:
        raise InvalidTransition(f"{action} no es una acción válida")
    to_status = TRANSITIONS[action]["to"]
    valid_from = TRANSITIONS[action]["from"]

    with _EVOLUTION_LOCK:
        proposals = _read_json_list(_proposals_path())
        idx = next((i for i, p in enumerate(proposals) if p.get("id") == proposal_id), None)
        if idx is None:
            raise KeyError("proposal_not_found")
        p = proposals[idx]
        from_status = p.get("status")
        if from_status not in valid_from:
            raise InvalidTransition(f"{action} no es válida desde {from_status}")
        now = _now_iso()
        p["status"] = to_status
        p["updated_at"] = now
        if note:
            p.setdefault("notes", []).append({"ts": now, "actor": actor, "text": note})
        if action == "apply":
            p["applied_at"] = now
        elif action == "rollback":
            p["rolled_back_at"] = now
        proposals[idx] = p
        _write_json_list(_proposals_path(), proposals)
        event = _normalize_event({
            "event": "transition", "proposal_id": proposal_id, "action": action,
            "from": from_status, "to": to_status, "actor": actor,
            "note": note, "cycle_id": p.get("cycle_id"),
        })
        _append_jsonl(_ledger_path(), event)
        result = dict(p)
    _ledger_log_mirror(event)
    return result


def update_proposal_fields(proposal_id: str, **patch) -> dict:
    """C2 — patch superficial SOLO de claves en `_PATCHABLE_FIELDS`. Cualquier
    otra clave (status, applied_at, id, …) → ValueError("campo_no_patcheable:<clave>").
    El status SOLO muta vía `transition()`. NO deja evento en el ledger."""
    for key in patch:
        if key not in _PATCHABLE_FIELDS:
            raise ValueError(f"campo_no_patcheable:{key}")
    with _EVOLUTION_LOCK:
        proposals = _read_json_list(_proposals_path())
        idx = next((i for i, p in enumerate(proposals) if p.get("id") == proposal_id), None)
        if idx is None:
            raise KeyError("proposal_not_found")
        p = proposals[idx]
        for key, value in patch.items():
            p[key] = value
        p["updated_at"] = _now_iso()
        proposals[idx] = p
        _write_json_list(_proposals_path(), proposals)
        return dict(p)
