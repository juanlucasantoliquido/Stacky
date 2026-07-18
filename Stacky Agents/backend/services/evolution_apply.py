"""Plan 167 F2 — Motor de aplicación y rollback (Execute del MAPE).

Aplica una propuesta APROBADA con snapshot previo del artefacto y la revierte
1-click; más el auto-apply human-on-the-loop gateado. Es la ÚNICA pieza del
plan que escribe artefactos del repo (`prompt_file`), con allowlist dura
anti path-traversal. Las lecciones (`knowledge_note`) van a runtime data.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths
from config import config as _cfg  # G1
from services import evolution_store as store

_HOTL_ALLOWED_ASPECTS = frozenset({"knowledge_rag"})
_APPLY_LOCK = threading.Lock()  # C3 — serializa apply/rollback end-to-end


def agents_prompts_dir() -> Path:
    """Directorio de los .agent.md del runtime (verificado en disco)."""
    return Path(runtime_paths.backend_root()) / "Stacky" / "agents"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_or_absent(path: Path) -> str:
    if path.exists():
        return _sha256_bytes(path.read_bytes())
    return "absent"


def _lessons_path() -> Path:
    return store.evolution_root() / "lessons.jsonl"


def _resolve_prompt_target(target_ref: str | None) -> Path:
    """Allowlist ANTI path-traversal: dentro de agents_prompts_dir(), sufijo
    `.md` y nombre `*.agent.md`. Si no cumple → ValueError('target_fuera_de_allowlist')."""
    base = agents_prompts_dir().resolve()
    target = (agents_prompts_dir() / (target_ref or "")).resolve()
    if (
        target.suffix != ".md"
        or not target.name.endswith(".agent.md")
        or not str(target).startswith(str(base))
    ):
        raise ValueError("target_fuera_de_allowlist")
    return target


def _append_lesson(proposal: dict) -> dict:
    path = _lessons_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lesson = {
        "lesson_id": proposal["id"],
        "aspect_id": proposal["aspect_id"],
        "text": proposal["proposed_content"],
        "origin": proposal["origin"],
        "created_at": _now_iso(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(lesson, ensure_ascii=False) + "\n")
    return {"kind": "lesson_append", "lesson_id": proposal["id"]}


def _remove_lesson(lesson_id: str) -> None:
    path = _lessons_path()
    if not path.exists():
        return
    kept: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except Exception:  # noqa: BLE001 — línea corrupta se conserva tal cual
            kept.append(line)
            continue
        if isinstance(obj, dict) and obj.get("lesson_id") == lesson_id:
            continue
        kept.append(line)
    path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")


def _apply_prompt_file(proposal: dict, target: Path) -> dict:
    snap_dir = store.evolution_root() / "snapshots" / proposal["id"]
    filename = target.name
    if target.exists():
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / f"before_{filename}").write_bytes(target.read_bytes())
        snapshot_info = {"kind": "file", "target": proposal["target_ref"], "absent": False}
    else:
        snapshot_info = {"kind": "file", "target": proposal["target_ref"], "absent": True}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(proposal["proposed_content"], encoding="utf-8")
    return snapshot_info


def apply_proposal(proposal_id: str, *, actor: str = "operator") -> dict:
    with _APPLY_LOCK:  # C3 — re-chequeo de status dentro del lock elimina la carrera
        if store.evolution_hard_disabled():  # A1
            raise RuntimeError("evolution_hard_disabled")
        p = store.get_proposal(proposal_id)
        if p is None:
            raise KeyError("proposal_not_found")
        if p.get("status") != "approved":
            raise store.InvalidTransition(f"apply no es válida desde {p.get('status')}")
        artifact_type = p.get("artifact_type")
        if artifact_type not in store.APPLIABLE_ARTIFACT_TYPES:
            raise ValueError("artifact_not_appliable")

        target: Path | None = None
        if artifact_type == "prompt_file":
            target = _resolve_prompt_target(p.get("target_ref"))  # ValueError allowlist
            # 3b) C6 anti-drift (solo con base_hash no nulo).
            if p.get("base_hash") is not None:
                actual = _sha256_or_absent(target)
                if p["base_hash"] != actual:
                    raise RuntimeError("target_drifted")

        try:
            if artifact_type == "knowledge_note":
                snapshot_info = _append_lesson(p)
            else:  # prompt_file
                assert target is not None
                snapshot_info = _apply_prompt_file(p, target)
        except Exception as exc:  # noqa: BLE001 — C7: side-effect real falló
            store.append_ledger({
                "event": "apply_failed", "proposal_id": proposal_id,
                "actor": actor, "note": str(exc),
            })
            raise RuntimeError(f"apply_failed: {exc}") from exc

        store.update_proposal_fields(proposal_id, snapshot_info=snapshot_info)
        return store.transition(proposal_id, "apply", actor=actor)


def rollback_proposal(proposal_id: str, *, actor: str = "operator", force: bool = False) -> dict:
    with _APPLY_LOCK:
        if store.evolution_hard_disabled():  # A1
            raise RuntimeError("evolution_hard_disabled")
        p = store.get_proposal(proposal_id)
        if p is None:
            raise KeyError("proposal_not_found")
        if p.get("status") != "applied":
            raise store.InvalidTransition(f"rollback no es válida desde {p.get('status')}")

        snap = p.get("snapshot_info") or {}
        kind = snap.get("kind")
        if kind == "lesson_append":
            _remove_lesson(snap.get("lesson_id"))
        elif kind == "file":
            target = _resolve_prompt_target(p.get("target_ref"))
            # C6 — si el archivo fue editado DESPUÉS del apply y no hay force → drift.
            if not force:
                current = _sha256_or_absent(target)
                proposed_sha = _sha256_bytes((p.get("proposed_content") or "").encode("utf-8"))
                if current != proposed_sha:
                    raise RuntimeError("target_drifted")
            if snap.get("absent"):
                if target.exists():
                    target.unlink()
            else:
                snap_file = store.evolution_root() / "snapshots" / p["id"] / f"before_{target.name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(snap_file.read_bytes())

        return store.transition(proposal_id, "rollback", actor=actor)


def maybe_auto_apply(proposal: dict) -> bool:
    """human-on-the-loop. Devuelve False (sin efecto) salvo que TODO se cumpla
    (kill-switch OFF + flag ON + aspecto en allowlist + knowledge_note + draft).
    Cualquier excepción → False, dejando rastro `apply_failed` best-effort (C7)."""
    try:
        if store.evolution_hard_disabled():  # A1 — el kill-switch gana SIEMPRE
            return False
        if not bool(getattr(_cfg, "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED", False)):
            return False
        if proposal.get("aspect_id") not in _HOTL_ALLOWED_ASPECTS:
            return False
        if proposal.get("artifact_type") != "knowledge_note":
            return False
        if proposal.get("status") != "draft":
            return False
        pid = proposal["id"]
        store.transition(pid, "submit", actor="auto_hotl")
        store.transition(pid, "approve", actor="auto_hotl")
        apply_proposal(pid, actor="auto_hotl")
        store.append_ledger({"event": "auto_apply", "proposal_id": pid, "actor": "auto_hotl"})
        return True
    except Exception as exc:  # noqa: BLE001 — nada muere en silencio (C7)
        try:
            store.append_ledger({
                "event": "apply_failed", "actor": "auto_hotl",
                "proposal_id": proposal.get("id"), "note": str(exc),
            })
        except Exception:  # noqa: BLE001
            pass
        return False
