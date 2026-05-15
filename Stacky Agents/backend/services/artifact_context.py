"""Context block que resume el estado de los artifacts en disco para un ticket.

Resuelve el Bug #3 del plan de remediación: el agente preguntaba "¿creo la
task?" o "¿genero el output?" aún cuando los archivos ya existían en disco.
El bloque que produce este módulo se inyecta en el contexto del agente para
que la decisión sea determinista en lugar de quedar a discreción del LLM.

Inspecciona, por orden:
  1. `<repo>/Agentes/outputs/{ado_id}/comment.html` — output HTML del agente.
  2. `<repo>/Agentes/outputs/epic-{ado_id}/{rf_dir}/pending-task.json` — tasks
     pendientes generadas por el agente funcional para un Epic.
  3. `backend/data/codex_runs/<execution_id>/MANIFEST.json` de la última
     ejecución del ticket — `signals.work_completed` señala si la corrida
     anterior llegó a destino.

El módulo es defensivo: cualquier IOError o JSON malformado se ignora y se
sigue informando lo que sí pudo leerse. Devuelve `None` cuando no encontró
nada relevante (entonces el agent_runner no inyecta el bloque).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from services.agent_html_output import repo_root
from services.manifest_watcher import MANIFEST_FILENAME

logger = logging.getLogger("stacky.artifact_context")

ARTIFACT_BLOCK_ID = "filesystem-artifacts-status"


def _outputs_dir() -> Path:
    return repo_root() / "Agentes" / "outputs"


def _codex_runs_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "codex_runs"


# ── Inspectores ───────────────────────────────────────────────────────────────


def _scan_comment_html(ado_id: int | None) -> dict | None:
    if not ado_id:
        return None
    path = _outputs_dir() / str(ado_id) / "comment.html"
    if not path.is_file():
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "path": _rel_to_repo(path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
    }


def _scan_epic_pending_tasks(ado_id: int | None) -> dict | None:
    """Cuenta pending-task.json bajo Agentes/outputs/epic-{ado_id}/.

    Retorna {pending: [...], consumed: [...]} con metadata mínima por RF, o
    `None` si la carpeta del Epic no existe.
    """
    if not ado_id:
        return None
    epic_dir = _outputs_dir() / f"epic-{ado_id}"
    if not epic_dir.is_dir():
        return None

    pending: list[dict] = []
    consumed: list[dict] = []
    for rf_dir in sorted(epic_dir.iterdir()):
        if not rf_dir.is_dir():
            continue
        pt_file = rf_dir / "pending-task.json"
        if not pt_file.is_file():
            continue
        try:
            payload = json.loads(pt_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("artifact_context: pending-task inválido en %s: %s", pt_file, exc)
            continue
        entry = {
            "rf_id": payload.get("rf_id") or rf_dir.name,
            "title": payload.get("title", ""),
            "path": _rel_to_repo(pt_file),
            "generated_at": payload.get("generated_at", ""),
        }
        if "consumed_at" in payload or payload.get("status") == "consumed":
            entry["consumed_at"] = payload.get("consumed_at", "")
            consumed.append(entry)
        else:
            pending.append(entry)

    if not pending and not consumed:
        return None
    return {"pending": pending, "consumed": consumed}


def _scan_latest_manifest(execution_ids: list[int]) -> dict | None:
    """Lee el MANIFEST.json más reciente entre las execution_ids dadas.

    El reverso ordena por id descendente (más nueva primero). Recorta a las
    primeras 5 para acotar el costo.
    """
    if not execution_ids:
        return None
    runs_dir = _codex_runs_dir()
    for exec_id in sorted(execution_ids, reverse=True)[:5]:
        path = runs_dir / str(exec_id) / MANIFEST_FILENAME
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("artifact_context: manifest inválido en %s: %s", path, exc)
            continue
        if not isinstance(data, dict):
            continue
        return {
            "execution_id": exec_id,
            "status": data.get("status"),
            "signals": data.get("signals") or {},
            "written_at": data.get("written_at"),
        }
    return None


# ── Builder principal ─────────────────────────────────────────────────────────


def build_artifact_status_block(
    *,
    ado_id: int | None,
    work_item_type: str | None,
    execution_ids: list[int] | None = None,
) -> dict | None:
    """Construye el context block "filesystem-artifacts-status" para un ticket.

    Devuelve un dict listo para concatenarse a `raw_blocks` en agent_runner,
    o `None` si no encontró ningún artifact relevante.
    """
    is_epic = (work_item_type or "").strip().lower() == "epic"

    comment_html = _scan_comment_html(ado_id)
    pending_tasks = _scan_epic_pending_tasks(ado_id) if is_epic else None
    latest_manifest = _scan_latest_manifest(execution_ids or [])

    if comment_html is None and pending_tasks is None and latest_manifest is None:
        return None

    content_lines: list[str] = [
        "Estado actual de los artifacts en disco para este ticket.",
        "Si un archivo ya existe, NO vuelvas a preguntarle al operador si",
        "querés crearlo: el operador ya tiene la UI para revisarlo o consumirlo.",
        "",
    ]

    if comment_html:
        content_lines.append(
            f"- comment.html: existe ({comment_html['size_bytes']} bytes, "
            f"modificado {comment_html['modified_at']}) → {comment_html['path']}"
        )
    else:
        content_lines.append("- comment.html: no existe.")

    if is_epic:
        if pending_tasks is None:
            content_lines.append("- pending-task.json (Epic): carpeta del Epic vacía.")
        else:
            pending = pending_tasks["pending"]
            consumed = pending_tasks["consumed"]
            content_lines.append(
                f"- pending-task.json: {len(pending)} pendiente(s), "
                f"{len(consumed)} consumida(s) en ADO."
            )
            for entry in pending:
                content_lines.append(
                    f"    · PENDIENTE rf={entry['rf_id']} '{entry['title']}' "
                    f"(generado {entry['generated_at']}) → {entry['path']}"
                )
            for entry in consumed:
                content_lines.append(
                    f"    · CONSUMIDA rf={entry['rf_id']} '{entry['title']}' "
                    f"(consumida {entry.get('consumed_at', '')})"
                )
            content_lines.append(
                "  Regla: si hay PENDIENTES, NO preguntes 'querés crear la task?'. "
                "El operador las creará desde la UI."
            )

    if latest_manifest:
        sig = latest_manifest.get("signals") or {}
        content_lines.append(
            f"- Última ejecución (execution_id={latest_manifest['execution_id']}): "
            f"status={latest_manifest.get('status')}, "
            f"work_completed={sig.get('work_completed', False)}, "
            f"task_created_in_ado={sig.get('task_created_in_ado', False)}"
        )

    return {
        "kind": "text",
        "id": ARTIFACT_BLOCK_ID,
        "title": f"Estado de artifacts en disco para ADO-{ado_id}",
        "content": "\n".join(content_lines),
        "metadata": {
            "comment_html": comment_html,
            "pending_tasks": pending_tasks,
            "latest_manifest": latest_manifest,
        },
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _rel_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(repo_root())).replace("\\", "/")
    except ValueError:
        return str(path)


def inject_into_blocks(
    raw_blocks: list[dict] | None,
    *,
    ado_id: int | None,
    work_item_type: str | None,
    execution_ids: list[int] | None = None,
) -> tuple[list[dict], dict[str, Any] | None]:
    """Inyecta el bloque en `raw_blocks` si no está presente.

    Retorna (blocks_actualizados, info) donde info es un dict de diagnóstico
    útil para loguear desde el caller, o None si no se inyectó nada.

    Idempotente: si ya hay un bloque con id `filesystem-artifacts-status` no
    re-inyecta.
    """
    blocks = list(raw_blocks or [])
    existing_ids = {b.get("id") for b in blocks if isinstance(b, dict)}
    if ARTIFACT_BLOCK_ID in existing_ids:
        return blocks, {"skipped": "already_present"}

    block = build_artifact_status_block(
        ado_id=ado_id,
        work_item_type=work_item_type,
        execution_ids=execution_ids,
    )
    if block is None:
        return blocks, None

    blocks.append(block)
    return blocks, {
        "injected": True,
        "has_comment_html": block["metadata"]["comment_html"] is not None,
        "pending_count": len((block["metadata"]["pending_tasks"] or {}).get("pending") or []),
        "consumed_count": len((block["metadata"]["pending_tasks"] or {}).get("consumed") or []),
        "latest_manifest_status": (block["metadata"]["latest_manifest"] or {}).get("status"),
    }
