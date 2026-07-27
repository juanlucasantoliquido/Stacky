"""Plan 196 — acciones HITL del pipeline de planes sobre el Tablero (Plan 128).

Modulo de servicio SIN Flask: prompts de las 4 skills, tabla estado->acciones,
serializacion de corridas, lock de lanzamiento y git log por doc. El modulo del
Plan 128 (services/plans_board.py) NO se modifica: solo se importa.
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

_LAUNCH_LOCK = threading.Lock()

# Sentinel del pool ticket one-shot. NOTA (Plan 196, desviacion documentada del
# doc): el -9 ya estaba dado de alta en _ONE_SHOT_ADO_IDS
# (services/claude_code_cli_runner.py) por el Plan 169 (variant_generator), que
# lo usa con stacky_project_name="stacky-evolution". Este pool usa el MISMO
# discriminador pero con project/stacky_project_name="default", asi que los dos
# lookups son disjuntos (uno filtra por stacky_project_name, el otro por
# project) y el indice unico (stacky_project_name, tracker_type, external_id)
# tampoco colisiona. Reusarlo evita editar claude_code_cli_runner.py, que tiene
# trabajo de otra sesion sin commitear; y sin estar en _ONE_SHOT_ADO_IDS la
# corrida quedaria colgada 1800 s como sesion conversacional.
PLANS_PIPELINE_ADO_ID = -9
PLANS_PIPELINE_AGENT_TYPE = "plans_pipeline"
_IDEA_MAX_CHARS = 500
_GIT_TIMEOUT_SEC = 5
_RUNNING_STALE_CAP_MINUTES = 120  # C2 — espejo del reaper (EXECUTION_TIMEOUT_MINUTES)

_ACTION_COMMANDS: dict[str, str] = {
    "proponer": "/proponer-plan-stacky",
    "criticar": "/criticar-y-mejorar-plan",
    "implementar": "/implementar-plan-stacky",
    "supervisar": "/supervisar-implementaciones-planes",
}

# nombre de la carpeta de la skill bajo .claude/skills/ por accion
_ACTION_SKILL_DIRS: dict[str, str] = {
    "proponer": "proponer-plan-stacky",
    "criticar": "criticar-y-mejorar-plan",
    "implementar": "implementar-plan-stacky",
    "supervisar": "supervisar-implementaciones-planes",
}


def _sanitize_idea(idea: str | None) -> str:
    if not idea:
        return ""
    # C8 — control chars no-whitespace a espacio (gotcha byte ESC 0x1B de la casa).
    cleaned = "".join(
        " " if ((ord(ch) < 32 and ch not in "\t\n\r") or ord(ch) == 127) else ch
        for ch in idea
    )
    return " ".join(cleaned.split())[:_IDEA_MAX_CHARS].strip()


def build_action_prompt(action: str, plan_number_str: str | None, idea: str | None) -> str:
    """Prompt de UNA linea (§4.1). ValueError si la accion es invalida o falta numero."""
    cmd = _ACTION_COMMANDS.get(action)
    if cmd is None:
        raise ValueError("invalid_action")
    if action == "proponer":
        extra = _sanitize_idea(idea)
        return f"{cmd} Tema: {extra}" if extra else cmd
    if not plan_number_str:
        raise ValueError("plan_number_requerido")
    return f"{cmd} {plan_number_str}"


def allowed_actions_for(estado: str, doc_drift: bool | None) -> tuple[str, ...]:
    """estado = card["estado"] del board 128; doc_drift = card["ledger"]["doc_drift"]."""
    acts: list[str] = []
    if estado == "PROPUESTO":
        acts.append("criticar")
    if estado == "CRITICADO":
        acts.append("implementar")
    if estado in ("IMPLEMENTADO", "IMPLEMENTADO_PARCIAL") or doc_drift is True:
        acts.append("supervisar")
    return tuple(acts)


def skill_file_for(action: str, root: Path) -> Path:
    return root / ".claude" / "skills" / _ACTION_SKILL_DIRS[action] / "SKILL.md"


def _started_recently(started_at, now=None) -> bool:
    """C2 — False si una corrida 'running' es mas vieja que el cap (fila
    zombie tras restart del backend). None cuenta como reciente."""
    if started_at is None:
        return True
    from datetime import datetime, timedelta

    now = now or datetime.utcnow()
    return (now - started_at) < timedelta(minutes=_RUNNING_STALE_CAP_MINUTES)


def find_running_pipeline_execution() -> int | None:
    """id de la corrida running mas reciente NO stale, o None (§4.5, C2).

    Las filas zombie (backend reiniciado con una corrida viva) NO bloquean el
    pipeline: el reaper existente ya las cierra como 'error'
    (recover_stale_running_tickets, EXECUTION_TIMEOUT_MINUTES=120); este cap es
    la defensa propia por si ese daemon esta apagado.
    """
    from db import session_scope
    from models import AgentExecution

    with session_scope() as s:
        rows = (
            s.query(AgentExecution)
            .filter(
                AgentExecution.agent_type == PLANS_PIPELINE_AGENT_TYPE,
                AgentExecution.status == "running",
            )
            .order_by(AgentExecution.id.desc())
            .all()
        )
        for row in rows:
            if _started_recently(row.started_at):
                return row.id
        return None


def serialize_run(row) -> dict:
    md = dict(row.metadata_dict or {})
    pp = md.get("plans_pipeline") or {}
    return {
        "id": row.id,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "action": pp.get("action"),
        "plan_number": pp.get("plan_number"),
        "model": pp.get("model"),
        "effort": pp.get("effort"),
        "prompt_line": pp.get("prompt_line"),
    }


def recent_commits_for_doc(filename: str) -> list[dict] | None:
    """git log -n 5 read-only del doc (§4.6). None ante CUALQUIER problema."""
    from services import plans_board

    root = plans_board.repo_root()
    if root is None:
        return None
    try:
        result = subprocess.run(
            [
                "git", "log", "-n", "5", "--date=short",
                "--pretty=format:%h|%ad|%s",
                "--", f"Stacky Agents/docs/{filename}",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    commits: list[dict] = []
    for raw_line in result.stdout.splitlines():
        parts = raw_line.strip().split("|", 2)
        if len(parts) != 3:
            continue
        commits.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
    return commits


def working_tree_status() -> dict | None:
    """`git status --porcelain` read-only. None ante CUALQUIER problema (sin
    repo, sin git, timeout). Solo informativo: la UI muestra un chip de
    advertencia; nunca bloquea acciones."""
    from services import plans_board

    root = plans_board.repo_root()
    if root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    changes = [ln for ln in result.stdout.splitlines() if ln.strip()]
    return {"dirty": bool(changes), "changes": len(changes)}
