import hashlib
import html as _html
import json
import logging
import os
import uuid as _uuid_mod
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import OperationalError

import fingerprint
from db import session_scope
from models import AgentExecution, SystemLog, Ticket
from services import glossary
from services.ado_sync import (
    AdoApiError,
    AdoConfigError,
    get_last_sync_at,
    sync_tickets,
)
from services.pipeline_status import get_pipeline_status, get_pipeline_summary
from services.ado_pipeline_inference import infer_pipeline, invalidate_cache
from services.ado_client import AdoClient, AdoApiError as _AdoApiError, AdoConfigError as _AdoConfigError
from services.project_context import ProjectContextError, build_ado_client, resolve_project_context

logger = logging.getLogger("stacky_agents.api.tickets")

bp = Blueprint("tickets", __name__, url_prefix="/tickets")

# ── Fase 2: constantes para create_child_task ─────────────────────────────────

# Campos obligatorios en pending-task.json para que Stacky pueda procesarlo
_PENDING_TASK_REQUIRED_FIELDS = {
    "generated_at", "generated_by", "epic_id", "rf_id",
    "title", "description_html", "plan_de_pruebas_path",
    "parent_link_type", "status",
}

# Contrato de `status` del pending-task.json (Fase P4 — consistencia C3).
# Valor canónico que el agente debe escribir (ver agents/functional.py y el
# .agent.md del Analista Funcional). `pending` se acepta como alias legacy para
# no romper archivos en vuelo generados por prompts viejos. `consumed` marca un
# archivo ya procesado (idempotencia).
PENDING_TASK_STATUS_CANONICAL = "pending_manual_creation"
PENDING_TASK_STATUS_CONSUMED = "consumed"
_PENDING_TASK_STATUS_PENDING_ALIASES = {PENDING_TASK_STATUS_CANONICAL, "pending"}
_PENDING_TASK_STATUS_ALLOWED = _PENDING_TASK_STATUS_PENDING_ALIASES | {PENDING_TASK_STATUS_CONSUMED}

# Fase 0 plan creacion-tareas-comentarios-100-efectiva (2026-05-29):
# Campos que el endpoint create-child-task agrega al archivo cuando lo marca
# como consumed. Para calcular el hash "logico" del payload del agente
# excluimos estas claves, asi `payload_sha256` (el que persistimos al consumir)
# y `payload_sha256_current` (el que reportamos en /artifact-status) refieren
# al mismo dominio: el contenido producido por el agente.
_CONSUMED_METADATA_KEYS = {
    "consumed_at", "task_ado_id", "attachment_id", "status", "operator_reason",
    "operation_id", "payload_sha256", "hierarchy_bridge",
}


def _payload_logical_sha256(payload: dict) -> str:
    """Hash del pending-task.json ignorando los campos agregados al consumir.

    Permite detectar si el agente regenero el contenido (refresh) aun cuando el
    archivo ya tenga marcadores de consume. Si el agente cambia algun campo
    propio, este hash cambia; los campos de consumo no afectan.
    """
    clean = {k: v for k, v in payload.items() if k not in _CONSUMED_METADATA_KEYS}
    canonical = json.dumps(clean, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# Resuelve el root del repo donde viven Agentes/outputs.
# Delega en runtime_paths.repo_root() (frozen-aware): honra STACKY_REPO_ROOT,
# luego el workspace_root del proyecto activo en deploy congelado, luego el
# layout de fuentes. Antes usaba parents[5], que en el .exe apuntaba fuera del
# repo del cliente y hacía fallar la lectura del pending-task.json.
def _repo_root() -> Path:
    from runtime_paths import repo_root as _runtime_repo_root
    return _runtime_repo_root()

# Override opcional para tests (Path). En producción queda None y
# _resolve_repo_root() resuelve en vivo. NO cachear acá el resultado de
# _repo_root(): el backend importa este módulo ANTES de que el operador active
# el proyecto, y congelar el valor dejaba REPO_ROOT apuntando a un repo_root
# inexistente → create-child-task fallaba con PENDING_TASK_FILE_NOT_FOUND aunque
# el archivo existiera (misma clase de bug que P1 resolvió en el output_watcher).
REPO_ROOT: Path | None = None


def _resolve_repo_root() -> Path:
    """Root del repo donde viven Agentes/outputs — resuelto **lazy** por request.

    Si un test fijó `REPO_ROOT` explícito, se respeta. Si no (None, producción),
    se resuelve en vivo vía runtime_paths.repo_root() en CADA request, reflejando
    el proyecto activo aunque se haya activado después del import.
    """
    if REPO_ROOT is not None:
        return REPO_ROOT
    return _repo_root()


def _body_json() -> dict:
    body = request.get_json(silent=True) or {}
    return body if isinstance(body, dict) else {}


def _artifact_root_override_from_request(body: dict | None = None) -> str | None:
    """Lee un override local de ruta desde query/body.

    Acepta tanto repo root (`N:/.../RSPACIFICO`) como outputs dir
    (`N:/.../RSPACIFICO/Agentes/outputs`) o incluso un `epic-*` dentro de outputs.
    Es un override por request para el desatascador/rescate; no modifica el
    watcher global ni variables de entorno.
    """
    for key in ("outputs_root", "repo_root", "artifact_root", "root"):
        value = (request.args.get(key) or "").strip()
        if value:
            return value
    data = body if body is not None else _body_json()
    for key in ("outputs_root", "repo_root", "artifact_root", "root"):
        value = (data.get(key) or "").strip() if isinstance(data.get(key), str) else ""
        if value:
            return value
    return None


def _resolve_artifact_repo_root(body: dict | None = None) -> tuple[Path, dict]:
    """Resuelve repo_root efectivo para escanear artifacts.

    El desatascador necesita poder mirar rutas locales distintas del workspace
    donde corre Stacky (p.ej. app en N:/STACKY pero proyecto en N:/RSPACIFICO).
    """
    default_repo = _resolve_repo_root()
    raw = _artifact_root_override_from_request(body)
    if not raw:
        outputs = default_repo / "Agentes" / "outputs"
        return default_repo, {
            "override": None,
            "repo_root": str(default_repo),
            "repo_root_exists": default_repo.exists(),
            "outputs_dir": str(outputs),
            "outputs_dir_exists": outputs.is_dir(),
        }

    cleaned = raw.strip().strip('"').strip("'")
    p = Path(cleaned)
    if not p.is_absolute():
        p = default_repo / p
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p.absolute()

    lower_name = resolved.name.lower()
    parent_name = resolved.parent.name.lower() if resolved.parent else ""
    grandparent_name = resolved.parent.parent.name.lower() if resolved.parent and resolved.parent.parent else ""

    if lower_name.startswith("epic-") and parent_name == "outputs" and grandparent_name == "agentes":
        repo = resolved.parent.parent.parent
        outputs = resolved.parent
    elif lower_name == "outputs" and parent_name == "agentes":
        repo = resolved.parent.parent
        outputs = resolved
    else:
        repo = resolved
        outputs = repo / "Agentes" / "outputs"

    return repo, {
        "override": cleaned,
        "repo_root": str(repo),
        "repo_root_exists": repo.exists(),
        "outputs_dir": str(outputs),
        "outputs_dir_exists": outputs.is_dir(),
    }


def _artifact_scan_roots(repo_root: Path) -> list[dict]:
    roots = []
    for base in _EPIC_OUTPUT_BASES:
        path = repo_root.joinpath(*base)
        roots.append({
            "label": "/".join(base),
            "path": str(path),
            "exists": path.is_dir(),
        })
    return roots


def _watcher_snapshot() -> dict:
    try:
        from services.output_watcher import get_output_watcher
        watcher = get_output_watcher()
        if watcher is None:
            return {"running": False, "outputs_dir": None}
        return {
            "running": bool(watcher._thread is not None and watcher._thread.is_alive()),
            "outputs_dir": str(watcher.outputs_dir),
            "outputs_dir_exists": watcher.outputs_dir.exists(),
            "poll_interval": watcher.poll_interval,
            "stable_delay_a": watcher.stable_delay_a,
            "stable_delay_b": watcher.stable_delay_b,
        }
    except Exception as exc:  # noqa: BLE001
        return {"running": False, "error": str(exc)[:200]}


def _write_manual_finish_html(*, ado_id: int, operator: str, operator_reason: str) -> Path:
    """Crea un comment.html de cierre manual para publicarlo via ado_publisher."""
    from services import agent_html_output as html_io

    out_path = html_io.default_html_path(ado_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_operator = _html.escape(operator or "anonymous")
    escaped_reason = _html.escape(operator_reason or "")
    out_path.write_text(
        (
            "<p><b>Cierre manual desde Stacky Agents.</b></p>\n"
            f"<p>Operador: {escaped_operator}</p>\n"
            f"<p>Motivo: {escaped_reason}</p>\n"
        ),
        encoding="utf-8",
    )
    return out_path


def _pending_task_preflight_for_finish(ado_id: int | None) -> dict:
    """Resume pending-task.json no consumidos para bloquear cierres silenciosos."""
    if ado_id is None:
        return {
            "total_pending": 0,
            "total_consumed": 0,
            "parse_errors": [],
            "pending_tasks": [],
            "scan_error": None,
        }
    try:
        pending, consumed_count, parse_errors = _scan_pending_tasks_for_epic(
            _resolve_repo_root(),
            int(ado_id),
        )
        return {
            "total_pending": len(pending),
            "total_consumed": consumed_count,
            "parse_errors": parse_errors,
            "pending_tasks": pending,
            "scan_error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "finish_work: no se pudo escanear pending-task.json para ADO-%s: %s",
            ado_id,
            exc,
        )
        return {
            "total_pending": 0,
            "total_consumed": 0,
            "parse_errors": [],
            "pending_tasks": [],
            "scan_error": f"{type(exc).__name__}: {exc}",
        }


def _request_project_name() -> str | None:
    project = (request.args.get("project") or "").strip()
    if project:
        return project
    if request.method in {"POST", "PUT", "PATCH"}:
        body = request.get_json(silent=True) or {}
        body_project = (body.get("project") or "").strip()
        return body_project or None
    return None


def _ado_sync_error_response(
    exc: AdoApiError,
    *,
    route_label: str,
    project_name: str | None,
):
    ctx = resolve_project_context(project_name=project_name)
    status_code = getattr(exc, "status_code", None)
    if status_code not in {401, 403}:
        logger.warning("ADO %s — api: %s", route_label, exc)
        return jsonify({"ok": False, "error": "ado_api", "message": str(exc)}), 502

    auth_path = ctx.auth_path if ctx else None
    auth_exists = bool(auth_path and Path(auth_path).exists())
    logger.warning(
        "ADO %s — auth failed (project_name=%s tracker_project=%s org=%s auth_path=%s auth_exists=%s status_code=%s)",
        route_label,
        ctx.stacky_project_name if ctx else project_name,
        ctx.tracker_project if ctx else None,
        ctx.organization if ctx else None,
        auth_path,
        auth_exists,
        status_code,
    )
    message = (
        f"ADO auth failed for project "
        f"{(ctx.stacky_project_name if ctx else project_name) or '<unknown>'} "
        f"(org={(ctx.organization if ctx else None) or '?'} "
        f"project={(ctx.tracker_project if ctx else None) or '?'}). "
        f"Verificá backend/projects/{(ctx.stacky_project_name if ctx else project_name) or '<project>'}/auth/ado_auth.json "
        f"o renová el PAT."
    )
    return jsonify({
        "ok": False,
        "error": "ado_auth_invalid",
        "message": message,
        "project_name": ctx.stacky_project_name if ctx else project_name,
        "organization": ctx.organization if ctx else None,
        "tracker_project": ctx.tracker_project if ctx else None,
        "auth_path": auth_path,
        "auth_exists": auth_exists,
        "ado_status_code": status_code,
    }), 502


def _ticket_project_filter(project_name: str | None):
    ctx = resolve_project_context(project_name=project_name) if project_name else resolve_project_context()
    if not ctx:
        return None
    return or_(
        Ticket.stacky_project_name == ctx.stacky_project_name,
        and_(Ticket.stacky_project_name.is_(None), Ticket.project == ctx.tracker_project),
    )


def _ado_client_for_ticket(ticket: Ticket | None = None, project_name: str | None = None) -> AdoClient:
    if ticket is not None:
        return build_ado_client(
            project_name=project_name or ticket.stacky_project_name,
            tracker_project=ticket.project,
            ticket=ticket,
        )
    if project_name:
        return build_ado_client(project_name=project_name)
    return build_ado_client()


def _resolve_me_unique_name(project_name: str | None) -> str:
    """uniqueName ADO del operador para el filtro 'Mis tareas'.

    Wrapper fino sobre el servicio compartido `ado_identity.resolve_me_unique_name`
    (fuente única de verdad reusada por B1 filtro y B3 auto-asignación)."""
    from services.ado_identity import resolve_me_unique_name

    return resolve_me_unique_name(project_name)


def _resolve_agent_block_states(
    project_name: str | None, agent_type: str | None
) -> tuple[str | None, str | None]:
    """B7 (D7-2): devuelve (blocked_state, review_state) del agente según el
    client_profile efectivo del proyecto.

    `review_state` = primer `input_states` del rol (estado donde el agente recibe
    el ticket). Defensivo: ante cualquier fallo devuelve (None, None) → el guard
    queda inerte (no rompe flujos legítimos)."""
    if not project_name or not agent_type:
        return (None, None)
    try:
        from services.client_profile import load_effective_client_profile

        profile = load_effective_client_profile(project_name) or {}
        machine = (profile.get("tracker_state_machine") or {}).get(agent_type) or {}
        blocked = (machine.get("blocked_state") or "").strip() or None
        inputs = machine.get("input_states") or []
        review = (inputs[0].strip() if inputs and isinstance(inputs[0], str) else None) or None
        return (blocked, review)
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo resolver block/review states para %s/%s", project_name, agent_type, exc_info=True)
        return (None, None)


def _check_finish_manifest_gate(execution_id: int | None) -> dict | None:
    """Lee MANIFEST.json para una execution_id y retorna un resumen.

    Retorna None si no hay execution o el manifest no existe / es inválido.
    Caso contrario:
      { "exists": True, "status": "...", "work_completed": bool,
        "written_at": str|None, "execution_id": int }
    """
    if execution_id is None:
        return None
    from services.manifest_watcher import MANIFEST_FILENAME, default_runs_dir

    path = default_runs_dir() / str(execution_id) / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    signals = data.get("signals") or {}
    return {
        "exists": True,
        "execution_id": execution_id,
        "status": data.get("status"),
        "work_completed": bool(signals.get("work_completed", False)),
        "written_at": data.get("written_at"),
    }


@bp.get("/hierarchy")
def get_hierarchy():
    """Devuelve todos los tickets organizados en jerarquía Epic → hijos.

    Response:
      {
        "epics": [ { ...ticket, "children": [ {...ticket}, ... ] } ],
        "orphans": [ {...ticket} ]    // tickets sin parent o cuyo parent no está en BD
      }

    Incluye pipeline_summary (solo BD local, sin LLM) para cada ticket.
    """
    project_filter = _ticket_project_filter(_request_project_name())
    with session_scope() as session:
        q = session.query(Ticket)
        if project_filter is not None:
            q = q.filter(project_filter)
        all_tickets = q.order_by(Ticket.ado_id).all()

        ado_id_to_ticket: dict[int, dict] = {}
        for t in all_tickets:
            d = t.to_dict()
            d["pipeline_summary"] = get_pipeline_summary(t.id)
            d["children"] = []
            ado_id_to_ticket[t.ado_id] = d

        epics: list[dict] = []
        orphans: list[dict] = []

        for t in all_tickets:
            d = ado_id_to_ticket[t.ado_id]
            wi_type = (t.work_item_type or "").lower()

            if wi_type == "epic":
                epics.append(d)
            elif t.parent_ado_id and t.parent_ado_id in ado_id_to_ticket:
                # tiene parent en BD → agregar como hijo
                ado_id_to_ticket[t.parent_ado_id]["children"].append(d)
            else:
                orphans.append(d)

        return jsonify({"epics": epics, "orphans": orphans})


@bp.get("")
def list_tickets():
    project_name = _request_project_name()
    project_filter = _ticket_project_filter(project_name)
    search = request.args.get("search", "").strip().lower()

    # Requerimiento B: filtro por usuario asignado. `assigned_to=me` resuelve la
    # identidad ADO del operador (mapeo persistido o, en su defecto, vía PAT).
    # Cualquier otro valor se compara literal contra Ticket.assigned_to_ado.
    assigned_to = (request.args.get("assigned_to") or "").strip()
    if assigned_to.lower() == "me":
        assigned_to = _resolve_me_unique_name(project_name)

    with session_scope() as session:
        q = session.query(Ticket)
        if project_filter is not None:
            q = q.filter(project_filter)
        if assigned_to:
            # B1: comparación case-insensitive. assigned_to_ado se normaliza a
            # minúsculas en el sync, pero la identidad resuelta del operador
            # (connectionData) puede venir con otro casing, y pueden quedar
            # tickets viejos sin re-sincronizar.
            q = q.filter(func.lower(Ticket.assigned_to_ado) == assigned_to.strip().lower())
        rows = q.order_by(Ticket.last_synced_at.desc().nulls_last(), Ticket.id.desc()).limit(500).all()
        out = []
        for t in rows:
            if search and search not in (t.title or "").lower() and search not in str(t.ado_id):
                continue
            d = t.to_dict()
            last = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == t.id)
                .order_by(AgentExecution.started_at.desc())
                .first()
            )
            d["last_execution"] = last.to_dict(include_output=False) if last else None
            d["pipeline_summary"] = get_pipeline_summary(t.id)
            out.append(d)
        return jsonify(out)


@bp.post("/sync")
def sync_from_ado():
    """Trae los work items abiertos desde Azure DevOps y actualiza la BD local."""
    project_name = _request_project_name()
    try:
        result = sync_tickets(client=_ado_client_for_ticket(project_name=project_name))
    except AdoConfigError as e:
        logger.warning("ADO sync — config: %s", e)
        return jsonify({"ok": False, "error": "config", "message": str(e)}), 400
    except AdoApiError as e:
        return _ado_sync_error_response(e, route_label="sync", project_name=project_name)
    except Exception as e:
        logger.exception("ADO sync — fallo inesperado")
        return jsonify({"ok": False, "error": "unexpected", "message": str(e)}), 500
    return jsonify({"ok": True, **result})


@bp.get("/sync/status")
def sync_status():
    project_name = _request_project_name()
    last = get_last_sync_at(project_name=project_name)
    return jsonify({
        "project": project_name or (resolve_project_context().stacky_project_name if resolve_project_context() else None),
        "last_synced_at": last.isoformat() if last else None,
    })


@bp.get("/<int:ticket_id>")
def get_ticket(ticket_id: int):
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        d = t.to_dict()
        execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == ticket_id)
            .order_by(AgentExecution.started_at.desc())
            .limit(50)
            .all()
        )
        d["executions"] = [e.to_dict(include_output=False) for e in execs]
        return jsonify(d)


@bp.get("/<int:ticket_id>/pipeline-status")
def get_pipeline_status_endpoint(ticket_id: int):
    """Infiere qué etapas del pipeline (business, functional, technical, developer, qa)
    ya fueron ejecutadas para este ticket.

    Query params:
      include_ado_comments=true  — también escanea comentarios del work item en ADO
                                   (requiere una llamada extra a la API de ADO).
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    ado_comments = None
    if request.args.get("include_ado_comments", "").lower() in ("1", "true", "yes"):
        try:
            client = _ado_client_for_ticket(ticket=t)
            ado_comments = client.fetch_comments(ado_id, top=30)
        except Exception as e:
            logger.warning("pipeline-status: no se pudo leer comentarios ADO para %s: %s", ado_id, e)

    status = get_pipeline_status(ticket_id, ado_comments=ado_comments)
    return jsonify(status.to_dict())


@bp.get("/<int:ticket_id>/ado-pipeline-status")
def get_ado_pipeline_status(ticket_id: int):
    """Infiere el estado del pipeline usando ÚNICAMENTE datos de ADO + LLM.

    No depende de archivos locales. Reproducible en cualquier máquina.
    Cachea resultado 60 min por defecto.

    Query params:
      force_refresh=true  — ignora cache y re-llama al LLM
      model=gpt-4o-mini   — modelo LLM a usar (default: gpt-4o-mini)
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    force = request.args.get("force_refresh", "").lower() in ("1", "true", "yes")
    model = request.args.get("model") or None

    try:
        result = infer_pipeline(
            ado_id=ado_id,
            force_refresh=force,
            model=model,
            project_name=t.stacky_project_name,
            tracker_project=t.project,
        )
        return jsonify(result.to_dict())
    except Exception as e:
        logger.exception("ado-pipeline-status falló para ticket %s (ADO-%s)", ticket_id, ado_id)
        return jsonify({"error": str(e)}), 500


@bp.post("/ado-pipeline-batch")
def ado_pipeline_batch():
    """Infiere el pipeline para múltiples tickets en un solo request.

    Body: { "ticket_ids": [1, 2, 3], "force_refresh": false, "model": "gpt-4o-mini" }
    Retorna: { "results": { "1": {...}, "2": {...} } }

    Usa cache — solo re-infiere los que no tienen cache fresco.
    """
    body = request.get_json(silent=True) or {}
    ticket_ids: list[int] = [int(x) for x in (body.get("ticket_ids") or [])]
    force = bool(body.get("force_refresh", False))
    model = body.get("model") or None

    if not ticket_ids:
        return jsonify({"results": {}})

    # Resolver ado_ids desde BD
    with session_scope() as session:
        tickets = session.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
        ticket_by_id = {t.id: t for t in tickets}

    results: dict[str, dict] = {}
    for tid in ticket_ids:
        ticket = ticket_by_id.get(tid)
        if ticket is None:
            results[str(tid)] = {"error": "not_found"}
            continue
        try:
            r = infer_pipeline(
                ado_id=ticket.ado_id,
                force_refresh=force,
                model=model,
                project_name=ticket.stacky_project_name,
                tracker_project=ticket.project,
            )
            results[str(tid)] = r.to_dict()
        except Exception as e:
            logger.warning("batch inference falló para ticket %s (ADO-%s): %s", tid, ticket.ado_id, e)
            results[str(tid)] = {"error": str(e)}

    return jsonify({"results": results})


@bp.delete("/<int:ticket_id>/ado-pipeline-cache")
def delete_ado_pipeline_cache(ticket_id: int):
    """Invalida el cache de inferencia para forzar re-inferencia en la próxima llamada."""
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id
    invalidate_cache(ado_id)
    return jsonify({"ok": True, "ado_id": ado_id})


@bp.get("/<int:ticket_id>/fingerprint")
def get_fingerprint(ticket_id: int):
    """N3 — Ticket Pre-Analysis Fingerprint (TPAF).
    Retorna análisis rápido del ticket: dominio, tipo de cambio, complejidad, pack sugerido.
    Fase 1: keyword-based (sin LLM). Fase 3+: embeddings.
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        result = fingerprint.analyze(t)
        return jsonify(result.to_dict())


@bp.get("/<int:ticket_id>/glossary")
def get_glossary(ticket_id: int):
    """FA-09 — Glossary auto-detection.
    Devuelve un ContextBlock listo para inyectar con los términos detectados
    en el título + descripción del ticket.
    """
    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        block = glossary.build_glossary_block([t.title or "", t.description or ""])
        return jsonify(block)


@bp.get("/<int:ticket_id>/comments")
def get_comments(ticket_id: int):
    """Devuelve los comentarios/notas del ticket desde Azure DevOps (on-demand).

    Busca el ticket en BD para obtener su ado_id, luego llama a AdoClient.fetch_comments.
    Retorna: { "comments": [{ "author", "date", "text" }] }
    """
    from services.ado_client import AdoClient, AdoApiError, AdoConfigError
    from services.ado_sync import _html_to_text

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    try:
        client = _ado_client_for_ticket(ticket=t)
    except AdoConfigError as e:
        return jsonify({"comments": [], "error": str(e)}), 200

    raw = client.fetch_comments(ado_id)
    comments = [
        {
            "author": c["author"],
            "date": c["date"],
            "text": _html_to_text(c["text"]),
        }
        for c in raw
        if c.get("text")
    ]
    return jsonify({"comments": comments})


@bp.get("/<int:ticket_id>/attachments")
def get_attachments(ticket_id: int):
    """Devuelve los adjuntos del ticket desde Azure DevOps (on-demand).

    Retorna: { "attachments": [{ "name", "url", "size", "text_content" }] }
    text_content se incluye solo para archivos de texto <= 64KB.
    """
    from services.ado_client import AdoClient, AdoConfigError

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)
        ado_id = t.ado_id

    try:
        client = _ado_client_for_ticket(ticket=t)
    except AdoConfigError as e:
        return jsonify({"attachments": [], "error": str(e)}), 200

    attachments = client.fetch_attachments(ado_id)
    return jsonify({"attachments": attachments})


@bp.get("/<int:ticket_id>/stacky-status")
def get_stacky_status(ticket_id: int):
    """Devuelve el stacky_status actual del ticket y su historial de transiciones.

    Response:
      {
        "ticket_id": 1,
        "current_status": "idle" | "running" | "completed" | "error" | "cancelled",
        "history": [ { "id", "old_status", "new_status", "changed_by", "changed_at",
                        "execution_id", "agent_type", "reason", "metadata" } ]
      }
    """
    from services import ticket_status as ts

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)

    limit = request.args.get("limit", default=20, type=int)
    return jsonify({
        "ticket_id": ticket_id,
        "current_status": ts.get_current_status(ticket_id),
        "history": ts.get_history(ticket_id, limit=limit),
    })


@bp.patch("/<int:ticket_id>/stacky-status")
def set_stacky_status(ticket_id: int):
    """Permite actualizar manualmente el stacky_status de un ticket.

    Body: { "status": "idle" | "running" | "completed" | "error" | "cancelled",
            "reason": "texto libre opcional" }
    Útil para resets manuales del operador o integraciones externas.
    """
    from services import ticket_status as ts

    body = request.get_json(silent=True) or {}
    new_status = body.get("status", "").strip()
    reason = body.get("reason")
    user = request.headers.get("X-User-Email") or "anonymous"

    if not new_status:
        return jsonify({"error": "campo 'status' requerido"}), 400

    with session_scope() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            abort(404)

    try:
        ts.set_status(
            ticket_id,
            new_status,
            changed_by=user,
            reason=reason or f"Manual update via API by {user}",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "ticket_id": ticket_id,
        "current_status": ts.get_current_status(ticket_id),
    })


@bp.patch("/by-ado/<int:ado_id>/stacky-status")
def set_stacky_status_by_ado(ado_id: int):
    """Override manual auditado de stacky_status (endpoint legacy, plan §17).

    IMPORTANTE: Este endpoint se mantiene como OVERRIDE MANUAL AUDITADO.
    No debe usarse para el flujo normal de finalización de agentes — para eso
    está POST /api/tickets/by-ado/{ado_id}/agent-completion con el gateway.

    Cada invocación:
    - Escribe completion_source='manual' en la AgentExecution si el campo existe.
    - Emite SystemLog(source='legacy_stacky_status', action='manual_override') con
      correlation_id, user_email, reason.
    - Si STACKY_COMPLETION_GATEWAY=on, agrega warning en log indicando que se
      usó el override manual mientras el gateway está activo.
    - Auto-publish server-side: cuando status=completed Y html_output_path apunta
      a un archivo existente Y existe AgentExecution válida, Stacky invoca
      ado_publisher.publish_from_execution automáticamente. El agente NO envía
      ningún flag para activar esto — la decisión es enteramente server-side.
      Controlado por env var STACKY_LEGACY_AUTO_PUBLISH (default "on").
      Si está en "off", el publish se omite y se registra publish.skipped.
      Si publish falla, el error se registra pero NO rompe el PATCH (el estado
      local ya quedó guardado). El resultado de publish se incluye en el response.

    Body:
      {
        "status": "completed" | "error" | "cancelled" | "idle",
        "reason": "texto libre opcional",
        "agent_type": "developer" | "technical" | ... (opcional),
        "html_output_path": "Agentes/outputs/<ADO_ID>/comment.html" (opcional),
        "target_ado_state": "To Do" | "Blocked" | "Done" | null (opcional)
      }

    Nota: el campo "auto_publish" es ignorado si está presente en el body —
    el comportamiento de publicación es server-side y no puede ser controlado
    por el agente.

    Si `target_ado_state` se provee, Stacky cambia el System.State del work item
    en ADO DESPUÉS de publicar exitosamente el comentario. Si el publish falló
    o se saltó, el state change también se saltea (no queremos ticket "Done"
    sin comentario publicado). Este flujo permite que TechnicalAnalyst delegue
    la transición a "To Do" / "Blocked" sin tocar ADO directamente.

    Responde 200 aunque el ticket no esté en BD (para no romper al agente).
    """
    import os as _os
    import uuid as _uuid
    from services import ticket_status as ts
    from models import SystemLog

    body = request.get_json(silent=True) or {}
    new_status = body.get("status", "").strip()
    reason = body.get("reason")
    agent_type = body.get("agent_type")
    html_output_path = body.get("html_output_path")
    # target_ado_state — opcional: transición del System.State del work item ADO
    # post-publish. Útil para que el TechnicalAnalyst delegue el cambio a "To Do"
    # o "Blocked" sin tocar ADO directamente. Si None, no se cambia el estado.
    target_ado_state = (body.get("target_ado_state") or "").strip() or None
    user = request.headers.get("X-User-Email") or "agent"
    correlation_id = str(_uuid.uuid4())

    # Leer env vars de control server-side
    gateway_mode = _os.getenv("STACKY_COMPLETION_GATEWAY", "off").lower().strip()
    legacy_auto_publish = _os.getenv("STACKY_LEGACY_AUTO_PUBLISH", "on").lower().strip()

    # Warning si gateway está activo (plan §B-2)
    if gateway_mode == "on":
        logger.warning(
            "legacy_stacky_status: manual override while gateway is active — "
            "ado_id=%s user=%s corr=%s — verificar si fue intencional",
            ado_id, user, correlation_id,
        )

    if not new_status:
        return jsonify({"ok": False, "error": "campo 'status' requerido"}), 400

    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if t is None:
            logger.warning("set_stacky_status_by_ado: ADO-%s no encontrado en BD — ignorado", ado_id)
            return jsonify({"ok": True, "skipped": True, "reason": "ticket not in local DB"}), 200
        ticket_id = t.id

        # Persistir html_output_path + completion_source='manual' en la última AgentExecution
        last_exec = None
        if html_output_path or True:  # siempre intentar marcar completion_source
            q = session.query(AgentExecution).filter(
                AgentExecution.ticket_id == ticket_id
            )
            if agent_type:
                q = q.filter(AgentExecution.agent_type == agent_type)
            last_exec = q.order_by(AgentExecution.started_at.desc()).first()
            if last_exec is not None:
                # html_output_path y completion_source son atributos DINÁMICOS
                # (no columnas SQL). El check hasattr() del código viejo siempre
                # daba False y bloqueaba el set — bug raíz del 'comment no se
                # publica'. Setting dynamic attrs funciona en Python sin
                # importar el schema de la clase.
                if html_output_path:
                    last_exec.html_output_path = html_output_path
                last_exec.completion_source = "manual"

        # Emitir SystemLog de override manual auditado
        log_ctx = {
            "correlation_id": correlation_id,
            "ado_id": ado_id,
            "new_status": new_status,
            "agent_type": agent_type,
            "html_output_path": html_output_path,
            "reason": reason,
            "gateway_mode": gateway_mode,
            "legacy_auto_publish": legacy_auto_publish,
            "gateway_active_warning": gateway_mode == "on",
            "execution_id": last_exec.id if last_exec else None,
        }
        audit_log = SystemLog(
            level="WARNING" if gateway_mode == "on" else "INFO",
            source="legacy_stacky_status",
            action="manual_override",
            ticket_id=ticket_id,
            execution_id=last_exec.id if last_exec else None,
            user=user,
            context_json=__import__("json").dumps(log_ctx, ensure_ascii=False, default=str),
            tags_json=__import__("json").dumps(
                ["legacy", "manual_override"] + (["gateway_active_warning"] if gateway_mode == "on" else [])
            ),
        )
        session.add(audit_log)

    # ── Cierre unificado: ticket_status + auto-publish vía helper ────────────
    # close_execution_with_publish reemplaza el bloque de ~70 líneas que antes
    # vivía acá inline. Es el mismo path que usa el output_watcher para cerrar
    # runs huérfanos automáticamente.
    publish_result: dict
    if last_exec is None:
        # Caller pasó un ticket sin ejecuciones — sólo seteamos stacky_status manual,
        # sin path de auto-publish posible (no hay execution_id).
        try:
            ts.set_status(
                ticket_id,
                new_status,
                changed_by=user,
                agent_type=agent_type,
                reason=reason or f"Manual override via legacy endpoint (ADO-{ado_id}) corr={correlation_id}",
                metadata={"html_output_path": html_output_path, "completion_source": "manual"} if html_output_path else {"completion_source": "manual"},
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        if new_status != "completed":
            publish_result = {"skipped": True, "reason": "status_not_completed"}
        elif legacy_auto_publish == "off":
            publish_result = {"skipped": True, "reason": "legacy_auto_publish_disabled"}
        elif not html_output_path:
            publish_result = {"skipped": True, "reason": "html_output_path_missing"}
        else:
            publish_result = {"skipped": True, "reason": "no_execution_found"}
            logger.warning(
                "set_stacky_status_by_ado: publish.skipped(no_execution_found) — "
                "ADO-%s html_output_path=%s corr=%s",
                ado_id, html_output_path, correlation_id,
            )
    else:
        # Path normal: hay execution. Usar la helper unificada.
        from services.agent_completion_internal import close_execution_with_publish

        # Si estamos transicionando a estados no-terminal (p.ej. status=idle),
        # la helper no aplica (es solo para terminal). Caemos al set_status manual.
        if new_status not in {"completed", "error", "cancelled"}:
            try:
                ts.set_status(
                    ticket_id,
                    new_status,
                    changed_by=user,
                    agent_type=agent_type,
                    reason=reason or f"Manual override via legacy endpoint (ADO-{ado_id}) corr={correlation_id}",
                    metadata={"completion_source": "manual"},
                )
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
            publish_result = {"skipped": True, "reason": "status_not_completed"}
        else:
            close_result = close_execution_with_publish(
                execution_id=last_exec.id,
                triggered_by="legacy_auto_publish",
                final_status=new_status,
                html_output_path=html_output_path,
                user=user,
                reason=reason or f"Manual override via legacy endpoint (ADO-{ado_id}) corr={correlation_id}",
                completion_source="manual",
                agent_type_hint=agent_type,
                # Si legacy_auto_publish=="off" forzamos disable; sino dejamos default (lee env).
                auto_publish=False if legacy_auto_publish == "off" else None,
            )
            publish_result = close_result.publish
            # Backward-compat con el contrato legacy: el reason del skip era
            # "legacy_auto_publish_disabled" antes del refactor.
            if publish_result.get("reason") == "auto_publish_disabled":
                publish_result = dict(publish_result)
                publish_result["reason"] = "legacy_auto_publish_disabled"
            if close_result.publish.get("ok") is True:
                logger.info(
                    "set_stacky_status_by_ado: publish.succeeded — ADO-%s exec=%d corr=%s",
                    ado_id, last_exec.id, correlation_id,
                )
            elif close_result.publish.get("ok") is False:
                logger.warning(
                    "set_stacky_status_by_ado: publish.failed — ADO-%s exec=%d reason=%s corr=%s",
                    ado_id, last_exec.id, close_result.publish.get("reason"), correlation_id,
                )

    # ── B7 (D7-2): guard anti auto-bloqueo de agentes ────────────────────────
    # Un agente NUNCA puede auto-transicionar el ticket a `blocked_state`: debe
    # publicar una consulta pre-bloqueo y dejar el ticket en su estado de revisión
    # (D7-1, prompt). Este guard es la garantía dura por código: si el target es el
    # blocked_state del agente y el origen es el agente (sin X-User-Email — las
    # acciones del operador desde la UI siempre lo envían), forzamos el estado de
    # revisión y lo dejamos logueado. El bloqueo real queda reservado a una acción
    # humana confirmada. Gateable vía STACKY_BLOCK_GUARD (default "on").
    if (
        target_ado_state
        and _os.getenv("STACKY_BLOCK_GUARD", "on").lower().strip() != "off"
        and not request.headers.get("X-User-Email")  # origen agente (no operador)
    ):
        blocked_state, review_state = _resolve_agent_block_states(
            t.stacky_project_name, agent_type
        )
        if blocked_state and target_ado_state.strip().lower() == blocked_state.strip().lower():
            logger.warning(
                "block_guard: auto-bloqueo de agente DENEGADO — ADO-%s agent=%s target=%s → forzado a %s corr=%s",
                ado_id, agent_type, target_ado_state, review_state or "(sin cambio)", correlation_id,
            )
            # Forzar el estado de revisión si lo conocemos; si no, cancelar la
            # transición por completo (mejor dejar el ticket donde está que bloquearlo).
            target_ado_state = review_state or None

    # ── Transición de System.State en ADO (opcional, Fase TA-migration) ──────
    # Solo si: target_ado_state explícito + publish ok + ado_id presente.
    # Si el publish falló o se saltó, no cambiamos estado (no queremos un
    # ticket en "Done" sin comentario publicado).
    state_change_result: dict = {"skipped": True, "reason": "not_requested"}
    if target_ado_state:
        if ado_id is None:
            state_change_result = {"skipped": True, "reason": "no_ado_id"}
        elif not publish_result.get("ok"):
            state_change_result = {
                "skipped": True,
                "reason": "publish_not_ok",
                "publish_status": publish_result.get("reason") or publish_result.get("event"),
            }
        else:
            try:
                _ado_client_for_ticket(ticket=t).update_work_item_state(int(ado_id), target_ado_state)
                state_change_result = {"ok": True, "to": target_ado_state}
                logger.info(
                    "set_stacky_status_by_ado: ado state changed → %s (ADO-%s corr=%s)",
                    target_ado_state, ado_id, correlation_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "set_stacky_status_by_ado: update_work_item_state falló — ADO-%s target=%s corr=%s",
                    ado_id, target_ado_state, correlation_id,
                )
                state_change_result = {
                    "ok": False,
                    "to": target_ado_state,
                    "error": str(exc),
                    "type": type(exc).__name__,
                }

    return jsonify({
        "ok": True,
        "ado_id": ado_id,
        "ticket_id": ticket_id,
        "current_status": ts.get_current_status(ticket_id),
        "html_output_path": html_output_path,
        "completion_source": "manual",
        "correlation_id": correlation_id,
        "gateway_active_warning": gateway_mode == "on",
        "publish": publish_result,
        "ado_state_change": state_change_result,
    })


@bp.post("/by-ado/<int:ado_id>/agent-completion")
def agent_completion(ado_id: int):
    """Gateway canónico de finalización de agentes (Plan SSD P1).

    Endpoint: POST /api/tickets/by-ado/{ado_id}/agent-completion

    Auth obligatoria: header X-Stacky-Agent-Token. Si falta o es inválido → 401.
    X-User-Email opcional (trazabilidad).

    Feature flag STACKY_COMPLETION_GATEWAY:
      off    → 404 (endpoint deshabilitado, comportamiento P0).
      shadow → corre en simulación, no muta DB/ADO. Responde 200 con plan.
      on     → gateway canónico activo (reservado para P5, responde 501 por ahora).

    Payload v1:
      {
        "execution_id": 44,               // opcional; si se omite, se resuelve
        "agent_type": "functional",       // requerido
        "status": "completed",            // requerido; uno de: completed|error|cancelled|needs_review
        "html_output_path": "Agentes/outputs/149/comment.html",  // opcional
        "metadata": {
          "html_sha256": "...",           // opcional
          "agent_version": "Agente@2026-05-14",  // opcional
          "duration_ms": 184232          // opcional
        },
        "reason": "texto libre",          // opcional
        "allow_synthetic_rescue": false   // opcional; solo con status=completed
      }

    Respuesta shadow:
      {
        "mode": "shadow",
        "ok": true,
        "would_succeed": true|false,
        "correlation_id": "uuid",
        "ticket_id": 42,
        "execution_id": 44,
        "plan": [...],
        "errors": [...],
        "discrepancies": [...]
      }
    """
    import os as _os
    import uuid as _uuid
    from services.agent_completion import CompletionPayload, GatewayError

    correlation_id = str(_uuid.uuid4())
    # Leer el flag dinámicamente en cada request para permitir hot-reload en tests
    # y cambios sin reiniciar el proceso (via env var update o config en runtime).
    gateway_mode = _os.getenv("STACKY_COMPLETION_GATEWAY", "off").lower().strip()

    # ── Feature flag: off → 404 ──────────────────────────────────────────────
    if gateway_mode == "off":
        return jsonify({
            "ok": False,
            "error": {
                "code": "gateway_disabled",
                "message": (
                    "El gateway de finalización de agentes está deshabilitado. "
                    "Establezca STACKY_COMPLETION_GATEWAY=shadow para activarlo. "
                    "Use PATCH /api/tickets/by-ado/{ado_id}/stacky-status para el flujo legacy."
                ),
            },
        }), 404

    # ── Auth: X-Stacky-Agent-Token ───────────────────────────────────────────
    agent_token_header = request.headers.get("X-Stacky-Agent-Token", "").strip()
    expected_token = _os.getenv("STACKY_AGENT_TOKEN", "").strip()

    if not agent_token_header:
        logger.warning(
            "gateway[%s] 401 missing token: ado_id=%s corr=%s",
            gateway_mode, ado_id, correlation_id,
        )
        return jsonify({
            "ok": False,
            "error": {"code": "auth_required", "message": "Header X-Stacky-Agent-Token requerido"},
            "correlation_id": correlation_id,
        }), 401

    if expected_token and agent_token_header != expected_token:
        logger.warning(
            "gateway[%s] 401 invalid token: ado_id=%s corr=%s",
            gateway_mode, ado_id, correlation_id,
        )
        return jsonify({
            "ok": False,
            "error": {"code": "auth_required", "message": "X-Stacky-Agent-Token inválido"},
            "correlation_id": correlation_id,
        }), 401

    user = request.headers.get("X-User-Email") or "agent"

    # ── Parse payload v1 ─────────────────────────────────────────────────────
    body = request.get_json(silent=True) or {}
    if not body:
        return jsonify({
            "ok": False,
            "error": {"code": "payload_invalid", "message": "Body JSON requerido"},
            "correlation_id": correlation_id,
        }), 400

    try:
        payload = CompletionPayload.from_dict(body)
    except (ValueError, KeyError) as exc:
        return jsonify({
            "ok": False,
            "error": {"code": "payload_invalid", "message": str(exc)},
            "correlation_id": correlation_id,
        }), 400

    # ── Modo shadow ──────────────────────────────────────────────────────────
    if gateway_mode == "shadow":
        from services.agent_completion import run_shadow

        # legacy_state: si el cliente quiere que el gateway detecte discrepancias
        # puede pasar el resultado del legacy en body["_legacy_observed"].
        # Es opcional — si no viene, el gateway solo simula.
        legacy_state: dict | None = body.get("_legacy_observed")

        try:
            result, http_status = run_shadow(
                ado_id=ado_id,
                payload=payload,
                user=user,
                correlation_id=correlation_id,
                legacy_state=legacy_state,
            )
            return jsonify(result.to_dict()), http_status
        except Exception as exc:
            logger.exception(
                "gateway[shadow] internal_error: ado_id=%s corr=%s", ado_id, correlation_id,
            )
            return jsonify({
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "Error interno en el gateway shadow",
                    "detail": {"correlation_id": correlation_id},
                },
                "correlation_id": correlation_id,
            }), 500

    # ── Modo on (P5 — gateway canónico activo) ───────────────────────────────
    if gateway_mode == "on":
        from services.agent_completion import run_on

        try:
            result, http_status = run_on(
                ado_id=ado_id,
                payload=payload,
                user=user,
                correlation_id=correlation_id,
            )
            return jsonify(result.to_dict()), http_status
        except Exception as exc:
            logger.exception(
                "gateway[on] internal_error: ado_id=%s corr=%s", ado_id, correlation_id,
            )
            return jsonify({
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "Error interno en el gateway (modo on)",
                    "detail": {"correlation_id": correlation_id},
                },
                "correlation_id": correlation_id,
            }), 500

    # Modo desconocido (guardrail)
    return jsonify({
        "ok": False,
        "error": {
            "code": "gateway_config_error",
            "message": (
                f"STACKY_COMPLETION_GATEWAY='{gateway_mode}' no es un valor válido. "
                "Valores aceptados: off | shadow | on"
            ),
        },
        "correlation_id": correlation_id,
    }), 500


@bp.post("/recover-stale-status")
def recover_stale_status():
    """Corrige tickets con stacky_status='running' cuya última ejecución ya terminó.

    Equivalente al startup recovery pero invocable on-demand desde el frontend
    o el operador. También detecta ejecuciones con timeout (running por más de
    EXECUTION_TIMEOUT_MINUTES) y las cierra como 'error'.

    Response:
      {
        "ok": true,
        "fixed": N,                         // cantidad (compatibilidad)
        "count": N,                         // mismo valor, nombre explícito
        "trigger": "manual",
        "details": [
          { "ticket_id": 42, "ado_id": 122, "old_status": "running",
            "new_status": "completed", "execution_id": 99,
            "agent_type": "developer", "kind": "execution_ended",
            "reason": "...", "trigger": "manual" },
          ...
        ]
      }
    """
    from services.ticket_status import recover_stale_running_tickets

    try:
        details = recover_stale_running_tickets(trigger="manual")
    except Exception as exc:
        logger.exception("recover-stale-status falló")
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "fixed": len(details),
        "count": len(details),
        "trigger": "manual",
        "details": details,
    })


# ── Fase 4: cierre manual fallback ────────────────────────────────────────────


@bp.post("/<int:ticket_id>/finish-work")
def finish_work(ticket_id: int):
    """Cierre manual de un ticket cuando la automatización no lo logró (Fase 4).

    Acciones (en orden, todas con audit trail):
      1. Validar precondiciones (existe ticket, no está ya completed).
      2. Si publish_to_ado=True: localizar y publicar el HTML del agente en ADO.
      3. Si target_ado_state se provee: cambiar el System.State del work item.
      4. Marcar stacky_status='completed' con changed_by=operador.
      5. Registrar evento estructurado en stacky_logger ('manual_finish_work').

    Body (JSON):
      {
        "operator_reason": "texto obligatorio, min 5 chars",
        "publish_to_ado": true,         // default true
        "html_output_path": "..."|null, // override del HTML — opcional
        "target_ado_state": "Done"|null,// si null, no se cambia el estado ADO
        "force_publish": false,          // bypassea dedupe de ado_publisher
        "dry_run": false                 // si true, solo valida — no ejecuta
      }

    Response:
      {
        "ok": bool,
        "dry_run": bool,
        "ticket_id": int,
        "ado_id": int|null,
        "preconditions": { html_exists, html_valid_reason, current_stacky_status },
        "actions": [
          { "action": "publish_ado_comment", "ok": bool, "reason": str|null,
            "html_sha256": str|null, "record_id": int|null },
          { "action": "update_ado_state",    "ok": bool, "to": str, "reason": str|null },
          { "action": "update_stacky_status","ok": bool, "to": "completed" }
        ],
        "current_status": str
      }
    """
    from services import ticket_status as ts
    from services.ado_publisher import publish_from_execution
    from services import agent_html_output as html_io

    body = request.get_json(silent=True) or {}
    operator_reason = (body.get("operator_reason") or "").strip()
    publish_to_ado_flag = bool(body.get("publish_to_ado", True))
    html_output_path = body.get("html_output_path")
    target_ado_state = body.get("target_ado_state")
    force_publish = bool(body.get("force_publish", False))
    # force_finish=true permite cerrar manualmente aunque el MANIFEST diga
    # work_completed=false (caso: operador limpia un ticket conocido como
    # roto). Sin este flag, el manifest gate devuelve 409.
    force_finish = bool(body.get("force_finish", False))
    dry_run = bool(body.get("dry_run", False))
    # cancel_active_execution=true (default) instruye al endpoint a cancelar
    # la AgentExecution activa antes de ejecutar el cierre. Si false, se omite.
    cancel_active_execution = bool(body.get("cancel_active_execution", True))
    operator = request.headers.get("X-User-Email") or "anonymous"
    # Trazabilidad de origen: el frontend UI envía "manual_ui"; agentes envían "agent" u omiten.
    # Backward-compat: si no viene el header ni el campo, default "manual".
    completion_source: str = (
        request.headers.get("X-Completion-Source")
        or body.get("completion_source")
        or "manual"
    )

    if len(operator_reason) < 5:
        return jsonify({
            "ok": False,
            "error": "operator_reason requerido (mínimo 5 caracteres)",
        }), 400

    # ── 1. Cargar contexto ────────────────────────────────────────────────────
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            abort(404)
        ado_id: int | None = getattr(ticket, "ado_id", None)
        current_stacky = getattr(ticket, "stacky_status", "idle") or "idle"

        # Última ejecución para localizar el HTML del agente
        last_exec = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == ticket_id)
            .order_by(AgentExecution.started_at.desc())
            .first()
        )
        execution_id = last_exec.id if last_exec else None
        # html_output_path se setea dinámicamente (no es columna); usamos
        # getattr para no romper en runs que nunca lo recibieron.
        exec_hint = getattr(last_exec, "html_output_path", None) if last_exec else None

        # Ejecución activa (status=running) — puede diferir de last_exec si
        # la última terminó pero stacky_status no se actualizó aún.
        active_exec = (
            session.query(AgentExecution)
            .filter(
                AgentExecution.ticket_id == ticket_id,
                AgentExecution.status == "running",
            )
            .first()
        )
        active_execution_id: int | None = active_exec.id if active_exec else None
        active_execution_agent_type: str | None = (
            active_exec.agent_type if active_exec else None
        )

    if current_stacky == "completed":
        return jsonify({
            "ok": False,
            "error": "ticket ya está en stacky_status='completed'",
            "current_status": current_stacky,
        }), 409

    # ── 1b. Manifest gate (Fase 3/5) ──────────────────────────────────────────
    # Si la última ejecución dejó un MANIFEST que dice work_completed=false, el
    # cierre manual es probablemente prematuro. Devolvemos 409 con el manifest
    # para que la UI muestre por qué; el operador puede pasar force_finish=true
    # para override.
    manifest_check = _check_finish_manifest_gate(execution_id)
    if (
        manifest_check is not None
        and not manifest_check["work_completed"]
        and not dry_run
        and not force_finish
    ):
        return jsonify({
            "ok": False,
            "error": "manifest_work_not_completed",
            "message": (
                "La última ejecución dejó un MANIFEST con work_completed=false. "
                "Si querés cerrar igual, mandá force_finish=true."
            ),
            "manifest": manifest_check,
            "current_status": current_stacky,
        }), 409

    # ── 2. Preflight: HTML existe y es válido? ────────────────────────────────
    html_exists = False
    html_invalid_reason: str | None = None
    if ado_id is not None and publish_to_ado_flag:
        hint = html_output_path or exec_hint
        try:
            html_io.read_and_validate(int(ado_id), hint=hint)
            html_exists = True
        except html_io.ValidationError as exc:
            html_invalid_reason = str(exc)
            # NOT_FOUND no es bloqueante — publicaremos una nota de cierre manual.
            # SECRET_DETECTED sí: rechazar la operación.
            if exc.code == "SECRET_DETECTED":
                return jsonify({
                    "ok": False,
                    "error": f"HTML contiene secretos; cierre manual abortado: {exc.message}",
                    "preconditions": {
                        "html_exists": False,
                        "html_invalid_reason": html_invalid_reason,
                        "current_stacky_status": current_stacky,
                    },
                }), 422

    pending_task_preflight = _pending_task_preflight_for_finish(ado_id)
    has_unconsumed_task_artifacts = (
        pending_task_preflight["total_pending"] > 0
        or len(pending_task_preflight["parse_errors"]) > 0
    )

    preconditions = {
        "html_exists": html_exists,
        "html_invalid_reason": html_invalid_reason,
        "current_stacky_status": current_stacky,
        "execution_id": execution_id,
        "ado_id": ado_id,
        "pending_tasks": pending_task_preflight,
        # Ejecución activa detectada al momento del request (dry_run o real).
        # El frontend la muestra como precondición antes de confirmar el cierre.
        "active_execution": (
            {
                "execution_id": active_execution_id,
                "agent_type": active_execution_agent_type,
                "will_cancel": cancel_active_execution,
            }
            if active_execution_id is not None
            else None
        ),
    }

    if dry_run:
        return jsonify({
            "ok": True,
            "dry_run": True,
            "ticket_id": ticket_id,
            "ado_id": ado_id,
            "cancel_result": None,
            "preconditions": preconditions,
            "actions": [],
            "current_status": current_stacky,
            "operator": operator,
        })

    if has_unconsumed_task_artifacts and not force_finish:
        return jsonify({
            "ok": False,
            "error": "PENDING_TASKS_NOT_CONSUMED",
            "message": (
                "Hay pending-task.json sin consumir o malformados para este Epic. "
                "Creá/reintentá las Tasks antes de cerrar, o enviá force_finish=true "
                "si querés hacer un override explícito."
            ),
            "preconditions": preconditions,
            "current_status": current_stacky,
        }), 409

    actions: list[dict] = []

    if not publish_to_ado_flag and active_execution_id is not None:
        try:
            with session_scope() as session:
                row = session.get(AgentExecution, active_execution_id)
                if row is not None:
                    meta = row.metadata_dict
                    meta["skip_ado_publish"] = True
                    meta["skip_ado_publish_reason"] = "finish_work_publish_to_ado_false"
                    row.metadata_dict = meta
        except Exception:  # noqa: BLE001
            logger.exception("finish_work: no se pudo marcar skip_ado_publish")

    # ── 2b. Cancelar ejecución activa (bloqueante, timeout 5s) ───────────────
    cancel_result: dict | None = None
    if active_execution_id is not None and cancel_active_execution:
        import agent_runner as _ar
        try:
            wait_result = _ar.cancel_and_wait(active_execution_id, timeout_seconds=5.0)
            cancel_result = {
                "execution_id": active_execution_id,
                "agent_type": active_execution_agent_type,
                "cancel_ok": wait_result["cancel_ok"],
                "cancel_reason": wait_result.get("cancel_reason"),
            }
            if not wait_result["cancel_ok"]:
                # Fallo no bloquea el cierre — registrar en system_logs y continuar.
                logger.warning(
                    "finish_work: cancel_and_wait timeout para execution_id=%s (ticket=%s) — cierre continúa",
                    active_execution_id,
                    ticket_id,
                )
                try:
                    from services.stacky_logger import logger as slog
                    slog.warning(
                        "tickets",
                        "finish_work_cancel_failed",
                        ticket_id=ticket_id,
                        execution_id=active_execution_id,
                        context_data={
                            "error": wait_result.get("cancel_reason", "timeout"),
                            "final_status": wait_result.get("final_status"),
                        },
                        tags=["ticket", "finish_work", "cancel_failed"],
                    )
                except Exception:
                    logger.exception("emit finish_work_cancel_failed falló (no crítico)")
        except Exception as exc:  # noqa: BLE001
            logger.exception("finish_work: cancel_and_wait lanzó excepción inesperada")
            cancel_result = {
                "execution_id": active_execution_id,
                "agent_type": active_execution_agent_type,
                "cancel_ok": False,
                "cancel_reason": f"{type(exc).__name__}: {exc}",
            }

    # ── 3. Publicar en ADO ────────────────────────────────────────────────────
    if publish_to_ado_flag and ado_id is not None:
        if html_exists and execution_id is not None:
            result = publish_from_execution(
                execution_id,
                triggered_by="finish_work",
                force=force_publish,
            )
            actions.append({
                "action": "publish_ado_comment",
                "ok": result.ok,
                "status": result.status,
                "reason": result.reason,
                "html_sha256": result.html_sha256,
                "record_id": result.record_id,
            })
        elif execution_id is not None:
            try:
                _write_manual_finish_html(
                    ado_id=int(ado_id),
                    operator=operator,
                    operator_reason=operator_reason,
                )
                result = publish_from_execution(
                    execution_id,
                    triggered_by="finish_work_manual_note",
                    force=force_publish,
                )
                actions.append({
                    "action": "publish_ado_comment",
                    "ok": result.ok,
                    "status": result.status,
                    "reason": result.reason or "manual_finish_note_via_publisher",
                    "html_sha256": result.html_sha256,
                    "record_id": result.record_id,
                })
            except Exception as exc:  # noqa: BLE001
                logger.exception("finish_work: manual finish note via publisher falló")
                actions.append({
                    "action": "publish_ado_comment",
                    "ok": False,
                    "status": "failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "html_sha256": None,
                    "record_id": None,
                })
        else:
            actions.append({
                "action": "publish_ado_comment",
                "ok": True,
                "status": "skipped",
                "reason": "no_agent_html_or_execution",
                "html_sha256": None,
                "record_id": None,
            })

    # ── 4. Cambiar estado en ADO ──────────────────────────────────────────────
    if target_ado_state and ado_id is not None:
        try:
            _ado_client_for_ticket(ticket=ticket).update_work_item_state(int(ado_id), target_ado_state)
            actions.append({
                "action": "update_ado_state",
                "ok": True,
                "to": target_ado_state,
                "reason": None,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("finish_work: update_ado_state falló")
            actions.append({
                "action": "update_ado_state",
                "ok": False,
                "to": target_ado_state,
                "reason": f"{type(exc).__name__}: {exc}",
            })

    # ── 5. Cerrar en Stacky BD ────────────────────────────────────────────────
    try:
        import time

        status_metadata = {
            "trigger": "manual_finish_work",
            "completion_source": completion_source,
            "operator": operator,
            "operator_reason": operator_reason,
            "target_ado_state": target_ado_state,
            "publish_to_ado": publish_to_ado_flag,
            "actions": actions,
        }
        last_lock_error: OperationalError | None = None
        for attempt in range(3):
            try:
                ts.set_status(
                    ticket_id,
                    "completed",
                    changed_by=operator,
                    execution_id=execution_id,
                    reason=f"Manual finish-work: {operator_reason}",
                    metadata=status_metadata,
                )
                last_lock_error = None
                break
            except OperationalError as exc:
                last_lock_error = exc
                if attempt == 2:
                    raise
                time.sleep(0.1 * (attempt + 1))
        if last_lock_error is not None:
            raise last_lock_error
        actions.append({
            "action": "update_stacky_status",
            "ok": True,
            "to": "completed",
            "reason": None,
        })
    except ValueError as exc:
        actions.append({
            "action": "update_stacky_status",
            "ok": False,
            "to": "completed",
            "reason": str(exc),
        })

    # ── 6. Evento estructurado para audit ─────────────────────────────────────
    try:
        from services.stacky_logger import logger as slog
        _tags = ["ticket", "finish_work", "manual", completion_source]
        if cancel_result is not None:
            _tags.append("cancel_active")
        slog.info(
            "tickets",
            "manual_finish_work",
            ticket_id=ticket_id,
            execution_id=execution_id,
            user=operator,
            context_data={
                "ado_id": ado_id,
                "completion_source": completion_source,
                "operator_reason": operator_reason,
                "target_ado_state": target_ado_state,
                "preconditions": preconditions,
                "actions": actions,
                "dry_run": False,
                # Campos nuevos Feature #5 — TerminarTrabajo
                "cancel_attempted": cancel_result is not None,
                "cancel_execution_id": (
                    cancel_result["execution_id"] if cancel_result else None
                ),
                "cancel_ok": cancel_result["cancel_ok"] if cancel_result else None,
            },
            tags=_tags,
        )
    except Exception:
        logger.exception("emit manual_finish_work falló (no crítico)")

    overall_ok = all(a.get("ok") for a in actions)
    return jsonify({
        "ok": overall_ok,
        "dry_run": False,
        "ticket_id": ticket_id,
        "ado_id": ado_id,
        "cancel_result": cancel_result,
        "preconditions": preconditions,
        "actions": actions,
        "current_status": ts.get_current_status(ticket_id),
        "operator": operator,
    })


# ── Fase 2: Create Child Task from pending-task.json ──────────────────────────


@bp.get("/by-ado/<int:ado_id>/pending-tasks")
def list_pending_tasks(ado_id: int):
    """Lista los pending-task.json no consumidos para un Epic (CA-11).

    Escanea `Agentes/outputs/epic-{ado_id}/*/pending-task.json`.
    Retorna solo los que tienen status=pending_manual_creation (sin consumed_at).

    Response:
      {
        "ok": true,
        "epic_ado_id": 149,
        "pending_tasks": [ { rf_id, title, pending_task_path, generated_at,
                              plan_de_pruebas_path, plan_exists, status } ],
        "total_pending": N,
        "total_consumed": M
      }
    """
    repo_root, scan = _resolve_artifact_repo_root()
    # Escanea ambas bases conocidas (Agentes/outputs y output/tickets) — el
    # agente funcional a veces co-loca el pending-task.json con el análisis.
    pending, consumed_count, parse_errors = _scan_pending_tasks_for_epic(repo_root, ado_id)

    return jsonify({
        "ok": True,
        "epic_ado_id": ado_id,
        "pending_tasks": pending,
        "total_pending": len(pending),
        "total_consumed": consumed_count,
        "parse_errors": parse_errors,
        "total_errors": len(parse_errors),
        "repo_root": str(repo_root),
        "scan": scan,
    })


@bp.get("/by-ado/<int:ado_id>/artifact-status")
def artifact_status(ado_id: int):
    """Diagnostico end-to-end del estado de artifacts para un Epic ADO.

    Fase 0 plan creacion-tareas-comentarios-100-efectiva (2026-05-29).

    Permite responder rapidamente "el ticket X ya tiene Task hija creada?" sin
    abrir multiples herramientas: muestra los pending-task.json detectados,
    su status (consumed/pending), el task_ado_id si fue consumido, el
    payload_sha256 que el endpoint computaria ahora (para detectar refresh
    silenciosos), y los ultimos events de system_logs relevantes.

    Response:
      {
        "ok": true,
        "epic_ado_id": 167,
        "repo_root": "C:/.../RSPACIFICO",
        "epic_outputs_dir": "C:/.../Agentes/outputs/epic-167",
        "epic_outputs_exists": true,
        "artifacts": [
          {
            "rf_id": "RF-019",
            "pending_task_path": "Agentes/outputs/epic-167/rf-019-.../pending-task.json",
            "status": "consumed",
            "task_ado_id": 172,
            "task_url": "https://dev.azure.com/.../172",
            "consumed_at": "2026-05-19T18:50:28Z",
            "payload_sha256_current": "abc123...",
            "payload_sha256_at_consume": "abc123..." | null,
            "payload_hash_diverged": false,
            "plan_de_pruebas_path": "...",
            "plan_exists": true,
            "operation_id": "uuid..." | null
          }
        ],
        "recent_system_logs": [
          { id, level, action, context: {...}, created_at }
        ]
      }
    """
    project_name = _request_project_name()
    repo_root, scan = _resolve_artifact_repo_root()
    epic_dir = repo_root / "Agentes" / "outputs" / f"epic-{ado_id}"

    artifacts: list[dict] = []
    if epic_dir.is_dir():
        for rf_dir in sorted(epic_dir.iterdir()):
            if not rf_dir.is_dir():
                continue
            pt_file = rf_dir / "pending-task.json"
            if not pt_file.is_file():
                continue
            try:
                pt_bytes = pt_file.read_bytes()
                payload = json.loads(pt_bytes.decode("utf-8"))
            except Exception as exc:
                artifacts.append({
                    "rf_id": rf_dir.name,
                    "pending_task_path": str(pt_file.relative_to(repo_root)).replace("\\", "/"),
                    "status": "parse_error",
                    "error": str(exc)[:200],
                })
                continue

            # payload_sha256_current usa el hash logico (sin campos de consume)
            # para que sea comparable contra payload_sha256_at_consume (registrado
            # con el mismo dominio en _payload_logical_sha256).
            payload_sha256_current = _payload_logical_sha256(payload)
            payload_sha256_at_consume = payload.get("payload_sha256")
            task_ado_id = payload.get("task_ado_id")
            task_url = None
            if task_ado_id:
                try:
                    task_url = _ado_client_for_ticket(project_name=project_name).work_item_url(int(task_ado_id))
                except Exception:
                    pass

            plan_rel = payload.get("plan_de_pruebas_path", "")
            plan_path = repo_root / plan_rel if plan_rel else None
            plan_exists = bool(plan_path and plan_path.is_file())

            try:
                rel_path = str(pt_file.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                rel_path = str(pt_file)

            artifacts.append({
                "rf_id": payload.get("rf_id") or rf_dir.name,
                "pending_task_path": rel_path,
                "status": payload.get("status"),
                "task_ado_id": task_ado_id,
                "task_url": task_url,
                "consumed_at": payload.get("consumed_at"),
                "payload_sha256_current": payload_sha256_current,
                "payload_sha256_at_consume": payload_sha256_at_consume,
                "payload_hash_diverged": bool(
                    payload_sha256_at_consume
                    and payload_sha256_at_consume != payload_sha256_current
                ),
                "plan_de_pruebas_path": plan_rel,
                "plan_exists": plan_exists,
                "operation_id": payload.get("operation_id"),
                "operator_reason": payload.get("operator_reason"),
                "attachment_id": payload.get("attachment_id"),
            })

    # Ultimos system_logs de create_child_task para este ADO id
    recent_logs: list[dict] = []
    try:
        with session_scope() as session:
            rows = (
                session.query(SystemLog)
                .filter(SystemLog.source == "create_child_task")
                .order_by(SystemLog.id.desc())
                .limit(30)
                .all()
            )
            for r in rows:
                ctx = {}
                try:
                    ctx = json.loads(r.context_json or "{}")
                except Exception:
                    pass
                if int(ctx.get("ado_id") or 0) != int(ado_id):
                    continue
                recent_logs.append({
                    "id": r.id,
                    "level": r.level,
                    "action": r.action,
                    "ok": ctx.get("ok"),
                    "task_ado_id": ctx.get("task_ado_id"),
                    "operation_id": ctx.get("operation_id") or ctx.get("correlation_id"),
                    "payload_sha256": ctx.get("payload_sha256"),
                    "error": ctx.get("error"),
                    "timestamp": r.timestamp.isoformat() if getattr(r, "timestamp", None) else None,
                })
                if len(recent_logs) >= 10:
                    break
    except Exception as exc:
        logger.warning("artifact_status: fallo leyendo system_logs: %s", exc)

    return jsonify({
        "ok": True,
        "epic_ado_id": ado_id,
        "repo_root": str(repo_root),
        "epic_outputs_dir": str(epic_dir),
        "epic_outputs_exists": epic_dir.is_dir(),
        "scan": {
            **scan,
            "roots": _artifact_scan_roots(repo_root),
            "watcher": _watcher_snapshot(),
        },
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "recent_system_logs": recent_logs,
    })


# Bases donde puede vivir un pending-task.json de un Epic. La canónica es
# `Agentes/outputs/epic-{id}/`, pero el agente funcional a veces lo co-loca junto
# al análisis y el plan en `output/tickets/epic-{id}/` (su prompt mezcla ambas
# rutas). Escaneamos las dos para no perder archivos reales en disco.
_EPIC_OUTPUT_BASES: tuple[tuple[str, ...], ...] = (
    ("Agentes", "outputs"),
    ("output", "tickets"),
)


def _pending_payload_points_to_ado(payload: dict, ado_id: int) -> bool:
    for key in ("epic_id", "epic_ado_id", "parent_id", "parent_ado_id"):
        value = payload.get(key)
        if value is not None and str(value).strip() == str(ado_id):
            return True
    return False


def _pending_declared_parent_id(payload: dict) -> str | None:
    for key in ("epic_ado_id", "parent_id", "parent_ado_id"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def iter_epic_pending_task_files(repo_root: Path, ado_id: int) -> list[Path]:
    """Devuelve los pending-task.json de un Epic en cualquiera de las bases.

    Incluye el archivo directamente bajo `epic-{id}/` y bajo subcarpetas RF
    (`epic-{id}/<rf>/`). Deduplica por path resuelto.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for base in _EPIC_OUTPUT_BASES:
        base_dir = repo_root.joinpath(*base)
        epic_dir = base_dir / f"epic-{ado_id}"
        if not epic_dir.is_dir():
            candidates = []
        else:
            candidates = sorted(epic_dir.glob("pending-task.json")) + sorted(
                epic_dir.glob("*/pending-task.json")
            )
        for pt in candidates:
            try:
                key = pt.resolve()
            except OSError:
                key = pt
            if key in seen:
                continue
            seen.add(key)
            found.append(pt)

        # Rescate de carpetas mal nombradas: el agente puede usar la etiqueta
        # humana del título (`epic-26`) aunque el ADO real sea 241. Si el JSON
        # declara `parent_id`/`epic_ado_id` con el ADO buscado, lo incluimos.
        if not base_dir.is_dir():
            continue
        loose_candidates = sorted(base_dir.glob("epic-*/pending-task.json")) + sorted(
            base_dir.glob("epic-*/*/pending-task.json")
        )
        for pt in loose_candidates:
            try:
                key = pt.resolve()
            except OSError:
                key = pt
            if key in seen:
                continue
            if pt.parent == epic_dir or pt.parent.parent == epic_dir:
                continue
            try:
                payload = json.loads(pt.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(payload, dict) or not _pending_payload_points_to_ado(payload, ado_id):
                continue
            seen.add(key)
            found.append(pt)
    return found


def _scan_pending_tasks_for_epic(repo_root: Path, ado_id: int) -> tuple[list[dict], int, list[dict]]:
    """Escanea los pending-task.json de un Epic en ambas bases conocidas.

    Devuelve `(pending, consumed_count, parse_errors)`:
      - `pending`: pending-task.json NO consumidos, con readiness de plan.
      - `consumed_count`: cuántos ya fueron consumidos (Task creada).
      - `parse_errors`: archivos que EXISTEN en disco pero NO parsean como JSON.
        Causa típica: el agente metió comillas dobles sin escapar en
        `description_html` (JSON inválido). Antes se descartaban en silencio →
        el ticket quedaba "atascado" sin señal visible y la Task nunca se creaba.
        Ahora se reportan para que el board/list los muestre.

    Helper compartido por el board desatascador y por list_pending_tasks.
    """
    pending: list[dict] = []
    parse_errors: list[dict] = []
    consumed_count = 0

    for pt_file in iter_epic_pending_task_files(repo_root, ado_id):
        try:
            # utf-8-sig tolera un BOM accidental (otra causa común de parse fallido).
            payload = json.loads(pt_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            try:
                rel_err = str(pt_file.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                rel_err = str(pt_file)
            logger.warning("pending-task: no se pudo parsear %s: %s", pt_file, exc)
            parse_errors.append({
                "rf_id": pt_file.parent.name,
                "pending_task_path": rel_err,
                "error": str(exc)[:300],
            })
            continue

        if "consumed_at" in payload or payload.get("status") == PENDING_TASK_STATUS_CONSUMED:
            consumed_count += 1
            continue

        plan_rel = payload.get("plan_de_pruebas_path", "")
        plan_path = repo_root / plan_rel if plan_rel else None
        plan_exists = bool(plan_path and plan_path.is_file())
        try:
            rel_path = str(pt_file.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(pt_file)

        pending.append({
            "rf_id": payload.get("rf_id") or pt_file.parent.name,
            "title": payload.get("title", ""),
            "pending_task_path": rel_path,
            "generated_at": payload.get("generated_at", ""),
            "plan_de_pruebas_path": plan_rel,
            "plan_exists": plan_exists,
            "status": payload.get("status", PENDING_TASK_STATUS_CANONICAL),
        })

    return pending, consumed_count, parse_errors


@bp.get("/unblocker-board")
def unblocker_board():
    """Vista 'Desatascador': tickets en ejecución + readiness de artifacts.

    Agrega, a nivel board (cross-ticket / cross-epic), todo lo que el copilot
    está trabajando o dejó listo en disco, para que el operador pueda destrabar
    el flujo manualmente sin frenar al dev:

      - Detecta `Agentes/outputs/{ado_id}/comment.html` → listo para publicar
        comentario en ADO (botón "Generar comentario").
      - Detecta `Agentes/outputs/epic-{ado_id}/*/pending-task.json` pendientes →
        listo para crear Task(s) hija(s) (botón "Crear Tasks").
      - Marca tickets `running` sin archivos todavía como `waiting_files` con
        `blockers` legibles.

    Query params:
      ?project=<nombre>  filtra por proyecto Stacky activo.

    Response:
      {
        "ok": true,
        "repo_root": "...",
        "items": [ {
          ticket_id, ado_id, title, work_item_type, ado_state, stacky_status,
          ado_url, running, readiness, blockers: [...],
          comment: { exists, path, size_bytes },
          pending_tasks: [...], total_pending, total_consumed,
          last_execution: { id, agent_type, status, started_at } | null
        } ],
        "total": N,
        "counts": { running, comment_ready, task_ready, waiting_files }
      }
    """
    project_name = _request_project_name()
    repo_root, scan = _resolve_artifact_repo_root()
    outputs_dir = repo_root / "Agentes" / "outputs"

    items: list[dict] = []
    counts = {"running": 0, "comment_ready": 0, "task_ready": 0, "waiting_files": 0, "files_error": 0}

    with session_scope() as session:
        # Ejecuciones en curso → set de ticket_ids + última ejecución por ticket.
        running_ticket_ids: set[int] = set()
        last_exec_by_ticket: dict[int, AgentExecution] = {}
        running_execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.status == "running")
            .all()
        )
        for ex in running_execs:
            running_ticket_ids.add(ex.ticket_id)

        q = session.query(Ticket)
        if project_name:
            q = q.filter(Ticket.stacky_project_name == project_name)
        tickets = q.all()

        # Última ejecución (cualquier estado) por ticket para mostrar contexto.
        ticket_ids = [t.id for t in tickets]
        if ticket_ids:
            for ex in (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id.in_(ticket_ids))
                .order_by(AgentExecution.id.asc())
                .all()
            ):
                last_exec_by_ticket[ex.ticket_id] = ex  # asc → last wins = más reciente

        for t in tickets:
            ado_id = t.ado_id
            running = (t.stacky_status == "running") or (t.id in running_ticket_ids)

            # ── Artifact 1: comment.html ──────────────────────────────────────
            comment_info = {"exists": False, "path": None, "size_bytes": 0}
            if ado_id:
                comment_path = outputs_dir / str(ado_id) / "comment.html"
                if comment_path.is_file():
                    try:
                        size = comment_path.stat().st_size
                    except OSError:
                        size = 0
                    if size > 0:
                        try:
                            rel = str(comment_path.relative_to(repo_root)).replace("\\", "/")
                        except ValueError:
                            rel = str(comment_path)
                        comment_info = {"exists": True, "path": rel, "size_bytes": size}

            # ── Artifact 2: pending-task.json (Epics) ─────────────────────────
            pending, consumed_count, parse_errors = ([], 0, [])
            if ado_id:
                pending, consumed_count, parse_errors = _scan_pending_tasks_for_epic(repo_root, ado_id)
            total_pending = len(pending)
            total_errors = len(parse_errors)

            # Un pending-task.json malformado (JSON inválido) cuenta como artifact:
            # el archivo está en disco pero ningún consumidor puede usarlo. Hay que
            # mostrarlo, no esconderlo.
            has_artifacts = comment_info["exists"] or total_pending > 0 or total_errors > 0

            # Sólo incluir tickets relevantes para el desatascador.
            if not (running or has_artifacts):
                continue

            # ── Readiness + blockers ──────────────────────────────────────────
            blockers: list[str] = []
            # Surface SIEMPRE los pending-task.json malformados (causa silenciosa
            # de "ticket atascado / desatascador no encuentra los archivos").
            for e in parse_errors:
                blockers.append(
                    f"pending-task.json MALFORMADO (JSON inválido) en {e['pending_task_path']}: "
                    f"{e['error']} — regéneralo con FunctionalAnalyst (v2.0.2+, que escapa las "
                    f"comillas en description_html) o corregí el JSON a mano."
                )
            if total_pending > 0:
                readiness = "task_ready"
                missing_plans = [p["rf_id"] for p in pending if not p["plan_exists"]]
                if missing_plans:
                    blockers.append(
                        "Plan de pruebas no encontrado para: "
                        + ", ".join(missing_plans)
                        + " (se omitirá el adjunto)."
                    )
            elif comment_info["exists"]:
                readiness = "comment_ready"
            elif total_errors > 0:
                # Hay archivo(s) pero ninguno parsea: estado accionable distinto de
                # "esperando" (el agente ya terminó, sólo produjo JSON inválido).
                readiness = "files_error"
            elif running:
                readiness = "waiting_files"
                blockers.append(
                    "El agente está en ejecución pero todavía no escribió "
                    "comment.html ni pending-task.json. Esperar a que termine "
                    "o revisar la consola del runtime."
                )
            else:
                readiness = "artifacts_idle"

            if running:
                counts["running"] += 1
            if readiness == "comment_ready":
                counts["comment_ready"] += 1
            elif readiness == "task_ready":
                counts["task_ready"] += 1
            elif readiness == "waiting_files":
                counts["waiting_files"] += 1
            elif readiness == "files_error":
                counts["files_error"] += 1

            ex = last_exec_by_ticket.get(t.id)
            last_execution = None
            if ex is not None:
                last_execution = {
                    "id": ex.id,
                    "agent_type": ex.agent_type,
                    "status": ex.status,
                    "started_at": ex.started_at.isoformat() if ex.started_at else None,
                }

            items.append({
                "ticket_id": t.id,
                "ado_id": ado_id,
                "title": t.title,
                "work_item_type": t.work_item_type,
                "ado_state": t.ado_state,
                "stacky_status": t.stacky_status or "idle",
                "ado_url": t.ado_url,
                "running": running,
                "readiness": readiness,
                "blockers": blockers,
                "comment": comment_info,
                "pending_tasks": pending,
                "total_pending": total_pending,
                "total_consumed": consumed_count,
                "parse_errors": parse_errors,
                "total_errors": total_errors,
                "last_execution": last_execution,
            })

    # Orden: primero lo que requiere acción del operador (archivo malformado y
    # task lista), luego comment/running/idle.
    _order = {"files_error": 0, "task_ready": 1, "comment_ready": 2, "waiting_files": 3, "artifacts_idle": 4}
    items.sort(key=lambda it: (_order.get(it["readiness"], 9), -(it["ado_id"] or 0)))

    return jsonify({
        "ok": True,
        "repo_root": str(repo_root),
        "scan": {
            **scan,
            "roots": _artifact_scan_roots(repo_root),
            "watcher": _watcher_snapshot(),
        },
        "items": items,
        "total": len(items),
        "counts": counts,
    })


def _safe_slug(value: str, fallback: str = "artifact") -> str:
    out = []
    for ch in (value or "").strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_", " ", ".", "—"}:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return (slug or fallback)[:90]


def _uploaded_files_from_body(body: dict) -> list[dict]:
    files = body.get("files")
    if isinstance(files, list):
        out = []
        for f in files:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or "").strip()
            content = f.get("content")
            if name and isinstance(content, str):
                out.append({"name": Path(name).name, "content": content})
        return out
    name = str(body.get("filename") or "").strip()
    content = body.get("content")
    if name and isinstance(content, str):
        return [{"name": Path(name).name, "content": content}]
    return []


@bp.post("/by-ado/<int:ado_id>/rescue-artifact")
def rescue_artifact(ado_id: int):
    """Staging de emergencia para archivos arrastrados al desatascador.

    No escribe ADO directamente: deja el artifact en disco bajo la convención que
    ya consumen `create-child-task` y `finish-work`, y devuelve la ruta para que
    el frontend invoque esos endpoints inmediatamente con trazabilidad normal.
    """
    body = _body_json()
    files = _uploaded_files_from_body(body)
    if not files:
        return jsonify({
            "ok": False,
            "error": "NO_FILES",
            "message": "No se recibieron archivos para rescatar.",
        }), 400

    repo_root, scan = _resolve_artifact_repo_root(body)
    outputs_dir = repo_root / "Agentes" / "outputs"
    by_name = {f["name"].lower(): f for f in files}
    requested = str(body.get("artifact_type") or "auto").strip().lower()

    pending_file = by_name.get("pending-task.json")
    if pending_file is None and requested in {"auto", "pending_task", "task"}:
        for f in files:
            if f["name"].lower().endswith(".json"):
                try:
                    candidate = json.loads(f["content"])
                except Exception:
                    continue
                if isinstance(candidate, dict) and (
                    "description_html" in candidate or "parent_link_type" in candidate
                ):
                    pending_file = f
                    break

    comment_file = by_name.get("comment.html")
    if comment_file is None and requested in {"auto", "comment"}:
        for f in files:
            low = f["name"].lower()
            if low.endswith(".html") or low.endswith(".htm"):
                comment_file = f
                break

    if requested in {"pending_task", "task"} or (requested == "auto" and pending_file is not None):
        if pending_file is None:
            return jsonify({"ok": False, "error": "PENDING_TASK_NOT_FOUND"}), 400
        try:
            payload = json.loads(pending_file["content"])
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "PENDING_TASK_PARSE_ERROR",
                "message": str(exc),
            }), 400
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "PENDING_TASK_SCHEMA_INVALID"}), 400

        original_epic_id = payload.get("epic_id")
        payload["epic_id"] = str(ado_id)
        payload.setdefault("parent_id", ado_id)
        payload.setdefault("parent_link_type", "System.LinkTypes.Hierarchy-Reverse")
        payload.setdefault("status", PENDING_TASK_STATUS_CANONICAL)
        rf_id = str(payload.get("rf_id") or body.get("rf_id") or "RF-MANUAL").strip()
        title = str(payload.get("title") or rf_id)
        rf_dir_name = _safe_slug(f"{rf_id}-{title}", fallback="manual-upload")
        target_dir = outputs_dir / f"epic-{ado_id}" / rf_dir_name
        target_dir.mkdir(parents=True, exist_ok=True)

        plan_file = by_name.get("plan-de-pruebas.md")
        if plan_file is None:
            for f in files:
                if f["name"].lower().endswith(".md"):
                    plan_file = f
                    break
        if plan_file is not None:
            plan_path = target_dir / "plan-de-pruebas.md"
            plan_path.write_text(plan_file["content"], encoding="utf-8")
            payload["plan_de_pruebas_path"] = str(plan_path.relative_to(repo_root)).replace("\\", "/")

        payload["rescue_uploaded_at"] = datetime.now(timezone.utc).isoformat()
        payload["rescue_original_epic_id"] = original_epic_id
        payload["rescue_original_filename"] = pending_file["name"]
        target = target_dir / "pending-task.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        rel = str(target.relative_to(repo_root)).replace("\\", "/")
        return jsonify({
            "ok": True,
            "artifact_type": "pending_task",
            "repo_root": str(repo_root),
            "scan": scan,
            "pending_task_path": rel,
            "normalized_epic_id": str(ado_id),
            "original_epic_id": original_epic_id,
        })

    if requested == "comment" or (requested == "auto" and comment_file is not None):
        if comment_file is None:
            return jsonify({"ok": False, "error": "COMMENT_HTML_NOT_FOUND"}), 400
        target_dir = outputs_dir / str(ado_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "comment.html"
        target.write_text(comment_file["content"], encoding="utf-8")
        meta_file = by_name.get("comment.meta.json")
        if meta_file is not None:
            (target_dir / "comment.meta.json").write_text(meta_file["content"], encoding="utf-8")
        rel = str(target.relative_to(repo_root)).replace("\\", "/")
        return jsonify({
            "ok": True,
            "artifact_type": "comment",
            "repo_root": str(repo_root),
            "scan": scan,
            "html_output_path": rel,
        })

    return jsonify({
        "ok": False,
        "error": "UNSUPPORTED_ARTIFACT",
        "message": "Arrastrá pending-task.json o comment.html.",
    }), 400


# ── Inc.3 P0: jerarquía de work items + verificación post-creación ────────────
#
# Jerarquías estándar de ADO (tipo padre → tipos hijos DIRECTAMENTE permitidos,
# en minúsculas). Sirven para el preflight: en Agile/Scrum/CMMI un Epic NO admite
# Task como hijo directo (exige Epic→Feature→Story/PBI/Requirement→Task), que es
# exactamente lo que rompía las épicas 241/242 de Pacífico. Si el proyecto declara
# `issue_tracker.hierarchy` explícito en config.json, ese override gana.
_ADO_DEFAULT_HIERARCHY: dict[str, dict[str, set[str]]] = {
    "agile": {
        "epic": {"feature"},
        "feature": {"user story", "bug"},
        "user story": {"task", "bug"},
        "bug": {"task"},
    },
    "scrum": {
        "epic": {"feature"},
        "feature": {"product backlog item", "bug"},
        "product backlog item": {"task", "bug"},
        "bug": {"task"},
    },
    "cmmi": {
        "epic": {"feature"},
        "feature": {"requirement", "bug"},
        "requirement": {"task", "bug"},
        "bug": {"task"},
    },
    "basic": {
        "epic": {"issue"},
        "issue": {"task"},
    },
}


def _resolve_hierarchy_for_project(
    project_name: str | None,
) -> tuple[str | None, dict[str, set[str]] | None]:
    """Devuelve (process_template, mapa padre→hijos) para el proyecto.

    Fuente de verdad, en orden:
      1. `issue_tracker.hierarchy` explícito en config.json (override del operador):
         dict { "<parent_type>": ["<child_type>", ...] }.
      2. `issue_tracker.process_template` ('Agile'|'Scrum'|'CMMI'|'Basic') → tabla
         built-in `_ADO_DEFAULT_HIERARCHY`.
    Si no hay nada declarado, devuelve (None, None) → el preflight se omite y el
    flujo cae a la verificación post-creación (que valida el link real igual).
    Nunca lanza: ante cualquier fallo devuelve (None, None).
    """
    if not project_name:
        return None, None
    try:
        from project_manager import get_project_config
        cfg = get_project_config(project_name) or {}
    except Exception:  # noqa: BLE001 — defensivo: sin config → sin preflight
        return None, None
    tracker = (cfg.get("issue_tracker") or {}) if isinstance(cfg, dict) else {}

    explicit = tracker.get("hierarchy")
    if isinstance(explicit, dict) and explicit:
        mapping: dict[str, set[str]] = {}
        for parent, children in explicit.items():
            if isinstance(children, (list, tuple, set)):
                mapping[str(parent).strip().lower()] = {
                    str(c).strip().lower() for c in children if str(c).strip()
                }
        template = str(tracker.get("process_template") or "custom").strip() or "custom"
        return template, (mapping or None)

    template = str(tracker.get("process_template") or "").strip()
    if not template:
        return None, None
    mapping = _ADO_DEFAULT_HIERARCHY.get(template.lower())
    return template, mapping


def _hierarchy_preflight(
    *, ado, epic_ado_id: int, child_type: str,
    project_name: str | None, operation_id: str,
) -> dict | None:
    """Valida que `child_type` pueda colgar directo del tipo del padre `epic_ado_id`.

    Devuelve:
      - None: preflight omitido (flag off, sin template declarado, o no se pudo
        leer el tipo del padre) → el caller procede y confía en la verificación
        post-creación.
      - {"ok": True, ...}: jerarquía válida.
      - {"ok": False, "message": ..., "suggestion": ..., ...}: NO crear; el caller
        devuelve ADO_HIERARCHY_NOT_SUPPORTED y deja el pending-task.json pendiente.

    Gateable con STACKY_HIERARCHY_PREFLIGHT=off (rollback sin redeploy).
    """
    if os.getenv("STACKY_HIERARCHY_PREFLIGHT", "on").strip().lower() == "off":
        return None
    template, mapping = _resolve_hierarchy_for_project(project_name)
    if not mapping:
        return None  # nada declarado → confiar en la verificación post-creación

    get_wi = getattr(ado, "get_work_item", None)
    if not callable(get_wi):
        return None  # cliente sin soporte (tests legacy) → skip

    try:
        wi = get_wi(epic_ado_id, ["System.WorkItemType"])
        parent_type = str((wi.get("fields") or {}).get("System.WorkItemType") or "").strip()
    except Exception as exc:  # noqa: BLE001 — no bloquear por fallo de lectura
        logger.warning(
            "create_child_task: preflight no pudo leer tipo del padre ADO-%s "
            "operation_id=%s err=%s — se omite (post-verify cubre)",
            epic_ado_id, operation_id, str(exc)[:200],
        )
        return None
    if not parent_type:
        return None

    allowed = mapping.get(parent_type.lower(), set())
    if child_type.strip().lower() in allowed:
        return {"ok": True, "parent_type": parent_type, "process_template": template}

    intermediates = sorted(allowed)
    inter_label = ", ".join(intermediates) if intermediates else "Feature/Story"
    message = (
        f"El template '{template}' no permite crear '{child_type}' como hijo directo "
        f"de '{parent_type}'. Creá un nivel intermedio ({inter_label}) y colgá la "
        f"'{child_type}' de él."
    )
    return {
        "ok": False,
        "parent_type": parent_type,
        "process_template": template,
        "allowed_children": intermediates,
        "suggestion": message,
        "message": message,
    }


_WORK_ITEM_TYPE_DISPLAY = {
    "epic": "Epic",
    "feature": "Feature",
    "user story": "User Story",
    "product backlog item": "Product Backlog Item",
    "requirement": "Requirement",
    "issue": "Issue",
    "bug": "Bug",
    "task": "Task",
}

_HIERARCHY_CHILD_PREFERENCE = {
    "agile": ["feature", "user story", "task", "bug"],
    "scrum": ["feature", "product backlog item", "task", "bug"],
    "cmmi": ["feature", "requirement", "task", "bug"],
    "basic": ["issue", "task"],
    "custom": ["feature", "user story", "product backlog item", "requirement", "issue", "task", "bug"],
}


def _norm_work_item_type(value: str | None) -> str:
    return str(value or "").strip().lower()


def _display_work_item_type(value: str) -> str:
    norm = _norm_work_item_type(value)
    return _WORK_ITEM_TYPE_DISPLAY.get(norm, norm.title())


def _ordered_hierarchy_children(
    *, template: str | None, children: set[str], target_child: str,
) -> list[str]:
    """Orden estable para BFS: preferimos backlog items reales antes que Bug."""
    norm_template = _norm_work_item_type(template) or "custom"
    preferred = _HIERARCHY_CHILD_PREFERENCE.get(norm_template, _HIERARCHY_CHILD_PREFERENCE["custom"])
    target = _norm_work_item_type(target_child)
    ordered: list[str] = []
    for item in preferred:
        if item in children and item not in ordered:
            ordered.append(item)
    if target in children and target not in ordered:
        ordered.append(target)
    for item in sorted(children):
        if item not in ordered:
            ordered.append(item)
    return ordered


def _find_hierarchy_path(
    *, mapping: dict[str, set[str]], parent_type: str, child_type: str, template: str | None,
) -> list[str] | None:
    """Devuelve tipos desde parent_type hasta child_type, inclusive."""
    start = _norm_work_item_type(parent_type)
    target = _norm_work_item_type(child_type)
    if not start or not target:
        return None
    queue: list[list[str]] = [[start]]
    seen = {start}
    while queue:
        path = queue.pop(0)
        current = path[-1]
        if current == target:
            return path
        for child in _ordered_hierarchy_children(
            template=template,
            children=mapping.get(current, set()),
            target_child=target,
        ):
            if child in seen:
                continue
            seen.add(child)
            queue.append(path + [child])
    return None


def _candidate_hierarchy_paths(
    *,
    root_type: str,
    child_type: str,
    preferred_path: list[str],
    template: str | None,
) -> list[list[str]]:
    """Rutas de creación de más estricta a más permisiva.

    ADO puede tener un proceso custom cuya config local diga Agile pero cuyos
    tipos reales no incluyan Feature. En ese caso probamos rutas comprimidas
    antes de abandonar.
    """
    root = _norm_work_item_type(root_type)
    child = _norm_work_item_type(child_type)
    normalized_preferred = [_norm_work_item_type(p) for p in preferred_path if _norm_work_item_type(p)]
    candidates: list[list[str]] = []

    def add(path: list[str]) -> None:
        clean = [_norm_work_item_type(p) for p in path if _norm_work_item_type(p)]
        if len(clean) < 2 or clean[0] != root or clean[-1] != child:
            return
        if clean not in candidates:
            candidates.append(clean)

    add(normalized_preferred)
    # Comprimir quitando intermedios de a uno: Epic->Feature->Story->Task
    # pasa a Epic->Story->Task cuando Feature no existe en el proyecto.
    for idx in range(1, max(len(normalized_preferred) - 1, 1)):
        add(normalized_preferred[:idx] + normalized_preferred[idx + 1:])

    for mid in _HIERARCHY_CHILD_PREFERENCE.get(
        _norm_work_item_type(template),
        _HIERARCHY_CHILD_PREFERENCE["custom"],
    ):
        if mid not in {root, child}:
            add([root, mid, child])
    add([root, child])
    return candidates


def _ado_error_is_work_item_type_missing(exc: Exception, work_item_type: str) -> bool:
    raw = str(exc).lower()
    typ = work_item_type.lower()
    return (
        "vs402323" in raw
        or ("work item type" in raw and "does not exist" in raw and typ in raw)
        or ("work item type" in raw and "not exist" in raw and typ in raw)
    )


def _bridge_title(pt_payload: dict, work_item_type: str, operation_id: str) -> str:
    rf_id = str(pt_payload.get("rf_id") or "RF").strip()
    title = str(pt_payload.get("title") or "").strip()
    display_type = _display_work_item_type(work_item_type)
    base = f"{rf_id} - {title}" if title and not title.startswith(rf_id) else (title or rf_id)
    # ADO tolera bastante, pero mantenerlo corto evita rechazos por títulos largos.
    clean = " ".join(base.split())
    return f"{display_type} - {clean}"[:250] or f"{display_type} - {operation_id[:8]}"


def _bridge_description_html(
    *, pt_payload: dict, root_parent_ado_id: int, operation_id: str, payload_sha256: str,
) -> str:
    rf_id = _html.escape(str(pt_payload.get("rf_id") or ""))
    return (
        "<p><b>Nodo intermedio creado automaticamente por Stacky Agents.</b></p>"
        f"<p>Epic ADO origen: {root_parent_ado_id}</p>"
        f"<p>RF: {rf_id}</p>"
        f"<p><em>operation_id: {_html.escape(operation_id)}</em></p>"
        f"<p><em>payload_sha256: {_html.escape(payload_sha256)}</em></p>"
    )


def _persist_hierarchy_bridge(pt_file: Path, bridge: dict) -> None:
    try:
        current = json.loads(pt_file.read_text(encoding="utf-8"))
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}
    current["hierarchy_bridge"] = bridge
    pt_file.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _valid_bridge_step(
    *, ado, step: dict, expected_type: str, expected_parent_id: int,
) -> bool:
    try:
        step_id = int(step.get("ado_id"))
    except (TypeError, ValueError):
        return False
    get_wi = getattr(ado, "get_work_item", None)
    if not callable(get_wi):
        return True
    try:
        wi = get_wi(step_id, ["System.WorkItemType", "System.Parent"])
    except Exception:
        return False
    fields = (wi or {}).get("fields") if isinstance(wi, dict) else {}
    actual_type = _norm_work_item_type((fields or {}).get("System.WorkItemType"))
    if actual_type != _norm_work_item_type(expected_type):
        return False
    parent = (fields or {}).get("System.Parent")
    try:
        return parent is not None and int(parent) == int(expected_parent_id)
    except (TypeError, ValueError):
        return False


def _ensure_task_creation_parent(
    *,
    ado,
    root_parent_ado_id: int,
    child_type: str,
    project_name: str | None,
    pt_payload: dict,
    pt_file: Path,
    operation_id: str,
    payload_sha256: str,
) -> dict:
    """Devuelve el padre real donde debe colgar la Task.

    En Agile/Scrum/CMMI un Epic no acepta Task directa. En vez de abortar, crea
    los work items intermedios mínimos declarados por la jerarquía del proyecto y
    persiste sus IDs en el pending-task.json para que un retry no duplique nodos.
    """
    if os.getenv("STACKY_HIERARCHY_PREFLIGHT", "on").strip().lower() == "off":
        return {
            "ok": True,
            "parent_ado_id": root_parent_ado_id,
            "actions": [],
            "hierarchy_bridge": None,
        }

    template, mapping = _resolve_hierarchy_for_project(project_name)
    if not mapping:
        return {
            "ok": True,
            "parent_ado_id": root_parent_ado_id,
            "actions": [],
            "hierarchy_bridge": None,
        }

    get_wi = getattr(ado, "get_work_item", None)
    if not callable(get_wi):
        return {
            "ok": True,
            "parent_ado_id": root_parent_ado_id,
            "actions": [],
            "hierarchy_bridge": None,
        }

    try:
        wi = get_wi(root_parent_ado_id, ["System.WorkItemType", "System.Title"])
        root_type = str((wi.get("fields") or {}).get("System.WorkItemType") or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "create_child_task: hierarchy bridge no pudo leer padre ADO-%s "
            "operation_id=%s err=%s; se omite",
            root_parent_ado_id, operation_id, str(exc)[:200],
        )
        return {
            "ok": True,
            "parent_ado_id": root_parent_ado_id,
            "actions": [],
            "hierarchy_bridge": None,
        }

    direct_allowed = mapping.get(_norm_work_item_type(root_type), set())
    if _norm_work_item_type(child_type) in direct_allowed:
        return {
            "ok": True,
            "parent_ado_id": root_parent_ado_id,
            "parent_type": root_type,
            "process_template": template,
            "actions": [],
            "hierarchy_bridge": None,
        }

    path = _find_hierarchy_path(
        mapping=mapping,
        parent_type=root_type,
        child_type=child_type,
        template=template,
    )
    if not path or len(path) < 2 or path[-1] != _norm_work_item_type(child_type):
        allowed = sorted(direct_allowed)
        message = (
            f"El template '{template}' no permite crear '{child_type}' como hijo "
            f"directo de '{root_type}' y Stacky no encontró una ruta de jerarquía "
            "hasta Task en la configuración del proyecto."
        )
        return {
            "ok": False,
            "error": "ADO_HIERARCHY_NOT_SUPPORTED",
            "message": message,
            "parent_type": root_type,
            "child_type": child_type,
            "process_template": template,
            "allowed_children": allowed,
            "actions": [],
        }

    bridge = pt_payload.get("hierarchy_bridge") if isinstance(pt_payload.get("hierarchy_bridge"), dict) else {}
    existing_steps = bridge.get("steps") if isinstance(bridge.get("steps"), list) else []
    fallback_notes: list[dict] = []
    last_failure: dict | None = None

    for candidate_path in _candidate_hierarchy_paths(
        root_type=root_type,
        child_type=child_type,
        preferred_path=path,
        template=template,
    ):
        new_steps: list[dict] = []
        actions: list[dict] = list(fallback_notes)
        current_parent_id = root_parent_ado_id
        path_failed_before_creating = False

        for index, step_type in enumerate(candidate_path[1:-1]):
            display_type = _display_work_item_type(step_type)
            existing = existing_steps[index] if index < len(existing_steps) and isinstance(existing_steps[index], dict) else None
            if existing and _norm_work_item_type(existing.get("type")) == _norm_work_item_type(step_type):
                try:
                    existing_id = int(existing.get("ado_id"))
                except (TypeError, ValueError):
                    existing_id = None
                if existing_id and _valid_bridge_step(
                    ado=ado,
                    step=existing,
                    expected_type=step_type,
                    expected_parent_id=current_parent_id,
                ):
                    reused = {
                        "type": display_type,
                        "ado_id": existing_id,
                        "parent_ado_id": current_parent_id,
                        "reused": True,
                    }
                    new_steps.append(reused)
                    actions.append({
                        "action": "reuse_intermediate_work_item",
                        "ok": True,
                        "work_item_type": display_type,
                        "work_item_ado_id": existing_id,
                        "parent_ado_id": current_parent_id,
                    })
                    current_parent_id = existing_id
                    continue

            try:
                wi_result = ado.create_work_item(
                    work_item_type=display_type,
                    fields={
                        "System.Title": _bridge_title(pt_payload, step_type, operation_id),
                        "System.Description": _bridge_description_html(
                            pt_payload=pt_payload,
                            root_parent_ado_id=root_parent_ado_id,
                            operation_id=operation_id,
                            payload_sha256=payload_sha256,
                        ),
                    },
                    parent_ado_id=current_parent_id,
                )
                created_id = int(wi_result["id"])
            except Exception as exc:  # noqa: BLE001
                last_failure = {
                    "ok": False,
                    "error": "ADO_CREATE_INTERMEDIATE_WORK_ITEM_FAILED",
                    "message": (
                        f"No se pudo crear el nodo intermedio '{display_type}' "
                        f"bajo ADO-{current_parent_id}: {str(exc)[:300]}"
                    ),
                    "parent_type": root_type,
                    "child_type": child_type,
                    "process_template": template,
                    "actions": actions + [{
                        "action": "create_intermediate_work_item",
                        "ok": False,
                        "work_item_type": display_type,
                        "parent_ado_id": current_parent_id,
                        "reason": str(exc)[:300],
                    }],
                    "hierarchy_bridge": {
                        "root_parent_ado_id": root_parent_ado_id,
                        "process_template": template,
                        "path": [_display_work_item_type(p) for p in candidate_path],
                        "steps": new_steps,
                    },
                }
                if not new_steps and _ado_error_is_work_item_type_missing(exc, display_type):
                    fallback_notes.append({
                        "action": "skip_intermediate_work_item",
                        "ok": True,
                        "work_item_type": display_type,
                        "reason": "WORK_ITEM_TYPE_NOT_AVAILABLE",
                        "detail": str(exc)[:300],
                    })
                    path_failed_before_creating = True
                    break
                return last_failure

            created_step = {
                "type": display_type,
                "ado_id": created_id,
                "parent_ado_id": current_parent_id,
                "reused": False,
            }
            new_steps.append(created_step)
            current_parent_id = created_id
            bridge_payload = {
                "root_parent_ado_id": root_parent_ado_id,
                "process_template": template,
                "path": [_display_work_item_type(p) for p in candidate_path],
                "steps": new_steps,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "operation_id": operation_id,
            }
            _persist_hierarchy_bridge(pt_file, bridge_payload)
            actions.append({
                "action": "create_intermediate_work_item",
                "ok": True,
                "work_item_type": display_type,
                "work_item_ado_id": created_id,
                "parent_ado_id": created_step["parent_ado_id"],
            })

        if path_failed_before_creating:
            continue

        final_bridge = {
            "root_parent_ado_id": root_parent_ado_id,
            "process_template": template,
            "path": [_display_work_item_type(p) for p in candidate_path],
            "steps": new_steps,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "operation_id": operation_id,
        }
        _persist_hierarchy_bridge(pt_file, final_bridge)
        return {
            "ok": True,
            "parent_ado_id": current_parent_id,
            "parent_type": _display_work_item_type(candidate_path[-2]) if len(candidate_path) > 1 else root_type,
            "process_template": template,
            "actions": actions,
            "hierarchy_bridge": final_bridge,
        }

    return last_failure or {
        "ok": False,
        "error": "ADO_HIERARCHY_NOT_SUPPORTED",
        "message": "No se pudo resolver una ruta de jerarquía válida para crear la Task.",
        "parent_type": root_type,
        "child_type": child_type,
        "process_template": template,
        "actions": fallback_notes,
    }


def _parent_exists_preflight(
    *, ado, epic_ado_id: int, operation_id: str,
) -> dict | None:
    """Verifica que el work item padre EXISTA en ADO antes de crear la Task.

    Causa raíz de 241/242 (2026-06-05): el agente nombró la carpeta de salida
    `epic-<N>` usando la etiqueta humana del título (`EP-26` → 26) en vez del id
    real del work item de ADO (241), y el output_watcher POSTeaba contra
    `by-ado/26/create-child-task`. ADO respondía 404 TF401232 «Work item 26 does
    not exist», la Task nunca se creaba y el fallo quedaba enterrado dentro de
    create_work_item (e incluso se contaba como intento «creado»).

    Este preflight convierte ese 404 silencioso en un error temprano y accionable
    (`ADO_PARENT_NOT_FOUND`) y deja el pending-task.json SIN consumir.

    Gateable con STACKY_PARENT_PREFLIGHT=off (rollback sin redeploy).

    Devuelve:
      - None: preflight omitido (flag off, cliente sin get_work_item, o error de
        lectura NO concluyente) → el flujo procede y create_work_item + sus
        catches existentes cubren el caso.
      - {"ok": True, "parent_type": ...}: el padre existe.
      - {"ok": False, "reason": "ADO_PARENT_NOT_FOUND", "message": ..., "detail": ...}:
        NO crear; el caller devuelve 422 y no consume el archivo.
    """
    if os.getenv("STACKY_PARENT_PREFLIGHT", "on").strip().lower() == "off":
        return None
    get_wi = getattr(ado, "get_work_item", None)
    if not callable(get_wi):
        return None  # cliente sin soporte (tests legacy) → skip

    def _not_found_payload(detail: str) -> dict:
        message = (
            f"El work item padre {epic_ado_id} no existe en Azure DevOps. "
            f"Causa típica: la carpeta de salida se nombró 'epic-{epic_ado_id}' "
            f"usando la etiqueta 'EP-{epic_ado_id}' del título en vez del id real "
            f"del work item de ADO. Verificá el epic_id del pending-task.json y "
            f"renombrá la carpeta a 'epic-<id ADO real>'."
        )
        return {
            "ok": False,
            "reason": "ADO_PARENT_NOT_FOUND",
            "message": message,
            "detail": detail[:300],
        }

    try:
        wi = get_wi(epic_ado_id, ["System.Id", "System.WorkItemType", "System.Title"])
    except Exception as exc:  # noqa: BLE001 — clasificamos por mensaje/status
        raw = str(exc)
        low = raw.lower()
        status = getattr(exc, "status_code", None)
        not_found = (
            status == 404
            or "tf401232" in low
            or "does not exist" in low
            or "→ 404" in raw
            or " 404:" in raw
        )
        if not_found:
            logger.warning(
                "create_child_task: ADO_PARENT_NOT_FOUND operation_id=%s ado_id=%s err=%s",
                operation_id, epic_ado_id, raw[:200],
            )
            return _not_found_payload(raw)
        # Error transitorio o no concluyente (red, 5xx, permisos): no bloquear.
        logger.warning(
            "create_child_task: preflight no pudo verificar el padre ADO-%s "
            "operation_id=%s err=%s — se omite (create_work_item cubre)",
            epic_ado_id, operation_id, raw[:200],
        )
        return None

    fields = (wi or {}).get("fields") if isinstance(wi, dict) else None
    if not wi or (isinstance(wi, dict) and not wi.get("id") and not fields):
        # GET ok pero respuesta vacía/sin id → tratar como inexistente (defensivo).
        return _not_found_payload(repr(wi))
    parent_type = str((fields or {}).get("System.WorkItemType") or "").strip()
    return {"ok": True, "parent_type": parent_type}


def _verify_child_task_created(
    *, ado, task_ado_id: int, epic_ado_id: int,
    expected_title: str, operation_id: str,
) -> dict | None:
    """Relee la Task recién creada y verifica que quedó vinculada al Epic.

    ADO puede aceptar el POST de creación pero NO aplicar un link jerárquico
    inválido, dejando una Task HUÉRFANA (sin padre). Sin esta verificación el
    endpoint marcaba `consumed` dando por hecho un trabajo que en ADO no existe
    como Task hija (causa raíz de 241/242, junto con el fallback de finish_work).

    Devuelve:
      - None: cliente sin `get_work_item` (tests legacy) → verificación omitida.
      - {"ok": True}: System.Parent apunta al Epic.
      - {"ok": False, "reason": ..., "detail": ...}: NO marcar consumed.
    """
    get_wi = getattr(ado, "get_work_item", None)
    if not callable(get_wi):
        return None
    try:
        wi = get_wi(
            task_ado_id,
            ["System.Id", "System.Title", "System.Parent", "System.WorkItemType"],
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reason": "VERIFY_GET_FAILED",
            "detail": f"No se pudo releer la Task {task_ado_id} para verificarla: {str(exc)[:200]}",
        }
    fields = wi.get("fields") or {}
    parent = fields.get("System.Parent")
    try:
        parent_ok = parent is not None and int(parent) == int(epic_ado_id)
    except (TypeError, ValueError):
        parent_ok = False
    if not parent_ok:
        return {
            "ok": False,
            "reason": "PARENT_LINK_MISSING",
            "detail": (
                f"La Task {task_ado_id} no quedó vinculada al Epic {epic_ado_id} "
                f"(System.Parent={parent!r}); la jerarquía no se aplicó."
            ),
        }
    return {"ok": True}


@bp.post("/by-ado/<int:ado_id>/create-child-task")
def create_child_task(ado_id: int):
    """Crea una Task hija del Epic en ADO consumiendo un pending-task.json (Fase 2).

    Cadena de acciones:
      1. Leer y validar pending-task.json (schema + idempotencia).
      2. AdoClient.create_work_item → JSON Patch con Hierarchy-Reverse al Epic.
      3. AdoClient.upload_attachment → plan-de-pruebas.md como adjunto.
      4. AdoClient.link_attachment_to_work_item → vincular adjunto a la Task.
      5. AdoClient.post_comment → registrar operator_reason en la Task.
      6. Marcar pending-task.json como consumed (bajo file lock).
      7. Registrar SystemLog con auditoría completa.

    Body:
      { "pending_task_path": str, "operator_reason": str?, "dry_run": bool? }

    Response (éxito):
      { ok, dry_run, epic_ado_id, task_ado_id, task_url, attachment_id,
        actions, pending_task_consumed, idempotent?, correlation_id }
    """
    correlation_id = str(_uuid_mod.uuid4())
    # Fase 0 plan creacion-tareas-comentarios-100-efectiva: operation_id es el
    # identificador trazable de este intento de escritura ADO. correlation_id se
    # mantiene como alias de compatibilidad con consumidores actuales.
    operation_id = correlation_id
    body = _body_json()
    pending_task_path_str: str = (body.get("pending_task_path") or "").strip()
    operator_reason: str = (body.get("operator_reason") or "").strip()
    dry_run: bool = bool(body.get("dry_run", False))
    completion_source: str = (
        request.headers.get("X-Completion-Source")
        or body.get("completion_source")
        or "manual"
    )
    project_name = _request_project_name()
    user = request.headers.get("X-User-Email") or "anonymous"

    if not pending_task_path_str:
        logger.warning(
            "create_child_task: missing pending_task_path operation_id=%s ado_id=%s user=%s",
            operation_id, ado_id, user,
        )
        return jsonify({
            "ok": False,
            "error": "MISSING_PENDING_TASK_PATH",
            "message": "El campo 'pending_task_path' es obligatorio",
            "correlation_id": correlation_id,
            "operation_id": operation_id,
        }), 400

    repo_root, scan = _resolve_artifact_repo_root(body)
    pt_file = repo_root / pending_task_path_str

    logger.info(
        "create_child_task: start operation_id=%s ado_id=%s repo_root=%s "
        "pending_task_path=%s user=%s completion_source=%s dry_run=%s",
        operation_id, ado_id, str(repo_root), pending_task_path_str,
        user, completion_source, dry_run,
    )

    # ── [1a] Verificar existencia del archivo ──────────────────────────────────
    if not pt_file.is_file():
        # Fase 0: diagnostico claro de repo_root cuando el archivo no existe.
        # Contamos cuantos pending-task.json hay debajo para distinguir
        # "ningun output" de "repo_root incorrecto".
        outputs_root = repo_root / "Agentes" / "outputs"
        try:
            artifact_count = sum(1 for _ in outputs_root.rglob("pending-task.json"))
        except Exception:
            artifact_count = -1
        logger.warning(
            "create_child_task: PENDING_TASK_FILE_NOT_FOUND operation_id=%s "
            "ado_id=%s repo_root=%s expected_path=%s outputs_artifact_count=%s",
            operation_id, ado_id, str(repo_root), str(pt_file), artifact_count,
        )
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_FILE_NOT_FOUND",
            "message": f"No se encontró el archivo: {pending_task_path_str}",
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "repo_root": str(repo_root),
            "expected_absolute_path": str(pt_file),
            "outputs_artifact_count": artifact_count,
        }), 400

    # ── [1b] Parsear y validar schema ─────────────────────────────────────────
    try:
        pt_bytes = pt_file.read_bytes()
        pt_payload = json.loads(pt_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning(
            "create_child_task: PENDING_TASK_PARSE_ERROR operation_id=%s ado_id=%s path=%s err=%s",
            operation_id, ado_id, pending_task_path_str, exc,
        )
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_PARSE_ERROR",
            "message": f"No se pudo parsear el archivo JSON: {exc}",
            "correlation_id": correlation_id,
            "operation_id": operation_id,
        }), 400

    # Fase 0: hash logico del payload (excluye campos agregados al consumir).
    # Trazabilidad y futura deteccion de "refresh sin re-publicar" (Fase 2 outbox).
    payload_sha256 = _payload_logical_sha256(pt_payload)
    logger.info(
        "create_child_task: payload_loaded operation_id=%s ado_id=%s "
        "payload_sha256=%s rf_id=%s status=%s",
        operation_id, ado_id, payload_sha256,
        pt_payload.get("rf_id"), pt_payload.get("status"),
    )

    missing_fields = sorted(_PENDING_TASK_REQUIRED_FIELDS - set(pt_payload.keys()))
    if missing_fields:
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_SCHEMA_INVALID",
            "missing_fields": missing_fields,
            "message": f"Campos requeridos ausentes en pending-task.json: {missing_fields}",
            "correlation_id": correlation_id,
        }), 400

    # ── [1b] Validar el valor de `status` (Fase P4 — consistencia C3) ──────────
    pt_status = str(pt_payload.get("status", "")).strip()
    if pt_status not in _PENDING_TASK_STATUS_ALLOWED:
        return jsonify({
            "ok": False,
            "error": "PENDING_TASK_STATUS_INVALID",
            "status_found": pt_status,
            "status_allowed": sorted(_PENDING_TASK_STATUS_ALLOWED),
            "message": (
                f"status='{pt_status}' no es válido. Usá "
                f"'{PENDING_TASK_STATUS_CANONICAL}' (canónico) — valores aceptados: "
                f"{sorted(_PENDING_TASK_STATUS_ALLOWED)}."
            ),
            "correlation_id": correlation_id,
        }), 400

    # ── [1c] Verificar que epic_id coincide con la URL ─────────────────────────
    file_epic_id = str(pt_payload.get("epic_id", "")).strip()
    if file_epic_id != str(ado_id):
        declared_parent_id = _pending_declared_parent_id(pt_payload)
        if declared_parent_id != str(ado_id):
            return jsonify({
                "ok": False,
                "error": "PENDING_TASK_EPIC_MISMATCH",
                "message": (
                    f"epic_id en el archivo ('{file_epic_id}') no coincide con "
                    f"epic_ado_id en la URL ({ado_id})"
                ),
                "file_epic_id": file_epic_id,
                "declared_parent_id": declared_parent_id,
                "url_epic_ado_id": ado_id,
                "correlation_id": correlation_id,
            }), 400
        logger.warning(
            "create_child_task: epic_id legacy/mal nombrado pero parent_id coincide "
            "operation_id=%s file_epic_id=%s parent_id=%s url_ado_id=%s path=%s",
            operation_id, file_epic_id, declared_parent_id, ado_id, pending_task_path_str,
        )

    # ── [1d] Idempotencia: ¿ya fue consumido? ──────────────────────────────────
    if "consumed_at" in pt_payload or pt_payload.get("status") == "consumed":
        prev_task_id = pt_payload.get("task_ado_id")
        prev_url = None
        if prev_task_id:
            try:
                prev_url = _ado_client_for_ticket(project_name=project_name).work_item_url(int(prev_task_id))
            except Exception:
                pass
        # Fase 0: hash del payload al momento del consume (si lo guardamos
        # en algun paso futuro). Por ahora informamos el sha actual; permite
        # que el operador y la UI detecten "refresh sin re-publicar" comparando
        # contra system_logs previos.
        logger.info(
            "create_child_task: PENDING_TASK_ALREADY_CONSUMED operation_id=%s "
            "ado_id=%s task_ado_id=%s payload_sha256=%s",
            operation_id, ado_id, prev_task_id, payload_sha256,
        )
        return jsonify({
            "ok": True,
            "dry_run": False,
            "epic_ado_id": ado_id,
            "task_ado_id": prev_task_id,
            "task_url": prev_url,
            "attachment_id": pt_payload.get("attachment_id"),
            "actions": [],
            "pending_task_consumed": True,
            "idempotent": True,
            "reason": "PENDING_TASK_ALREADY_CONSUMED",
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "payload_sha256": payload_sha256,
        })

    # ── [dry_run] Retornar plan de acciones sin tocar ADO ─────────────────────
    plan_rel = pt_payload.get("plan_de_pruebas_path", "")
    plan_path = repo_root / plan_rel if plan_rel else None
    plan_exists = bool(plan_path and plan_path.is_file())

    if dry_run:
        dry_actions = [
            {
                "action": "create_work_item",
                "would_call": f"POST _apis/wit/workitems/$Task?api-version=7.1",
                "payload_preview": {
                    "title": pt_payload.get("title"),
                    "parent": ado_id,
                    "state": pt_payload.get("target_state", "Technical review"),
                },
            },
            {
                "action": "upload_attachment",
                "would_call": "POST _apis/wit/attachments?fileName=plan-de-pruebas.md",
                "file_exists": plan_exists,
            },
            {
                "action": "link_attachment",
                "would_call": "PATCH _apis/wit/workitems/{task_id}/relations/-",
            },
        ]
        return jsonify({
            "ok": True,
            "dry_run": True,
            "epic_ado_id": ado_id,
            "task_ado_id": None,
            "task_url": None,
            "attachment_id": None,
            "actions": dry_actions,
            "pending_task_consumed": False,
            "correlation_id": correlation_id,
        })

    # ── [2–7] Ejecución real ───────────────────────────────────────────────────
    actions: list[dict] = []
    task_ado_id: int | None = None
    task_url: str | None = None
    attachment_id: str | None = None
    human_action_required: str | None = None

    # Inicializar cliente ADO
    try:
        ado = _ado_client_for_ticket(project_name=project_name)
    except (_AdoConfigError, ProjectContextError) as exc:
        logger.warning(
            "create_child_task: ADO_CONFIG_MISSING operation_id=%s ado_id=%s err=%s",
            operation_id, ado_id, exc,
        )
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=[],
            error=str(exc),
            operation_id=operation_id,
            payload_sha256=payload_sha256,
            repo_root=str(repo_root),
        )
        return jsonify({
            "ok": False,
            "error": "ADO_CONFIG_MISSING",
            "message": str(exc),
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "payload_sha256": payload_sha256,
            "scan": scan,
        }), 503

    # ── [1d-bis] Preflight de existencia del padre (Inc.3 — épicas 241/242) ───
    # Si el work item padre no existe (carpeta `epic-<ordinal del título EP-NN>`
    # en vez de `epic-<ado_id real>`), fallamos temprano y claro en vez de dejar
    # que ADO devuelva un 404 enterrado dentro de create_work_item (que además se
    # contaba como intento "creado"). Deja el pending-task.json sin consumir.
    parent_check = _parent_exists_preflight(
        ado=ado, epic_ado_id=ado_id, operation_id=operation_id,
    )
    if parent_check is not None and not parent_check.get("ok"):
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=[{"action": "parent_exists_preflight", "ok": False,
                      "reason": parent_check.get("reason")}],
            error=parent_check.get("message"),
            operation_id=operation_id,
            payload_sha256=payload_sha256,
            repo_root=str(repo_root),
        )
        return jsonify({
            "ok": False,
            "error": parent_check.get("reason"),
            "message": parent_check.get("message"),
            "detail": parent_check.get("detail"),
            "epic_ado_id": ado_id,
            "task_ado_id": None,
            "task_url": None,
            "attachment_id": None,
            "actions": [],
            "pending_task_consumed": False,
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "payload_sha256": payload_sha256,
        }), 422

    # ── [1e] Preflight de jerarquía (Inc.3 P0) ────────────────────────────────
    # Si el process template del proyecto no admite Task como hijo directo del
    # tipo del padre (p.ej. Epic→Task en Agile), NO intentamos crear: ADO la
    # rechazaría o, peor, crearía una Task huérfana que luego degradaría a un
    # comentario en la épica. Devolvemos un error claro y dejamos el
    # pending-task.json SIN consumir para que el operador cree el nivel intermedio.
    hierarchy_parent = _ensure_task_creation_parent(
        ado=ado,
        root_parent_ado_id=ado_id,
        child_type="Task",
        project_name=project_name,
        pt_payload=pt_payload,
        pt_file=pt_file,
        operation_id=operation_id,
        payload_sha256=payload_sha256,
    )
    actions.extend(hierarchy_parent.get("actions") or [])
    if not hierarchy_parent.get("ok"):
        logger.warning(
            "create_child_task: %s operation_id=%s ado_id=%s parent_type=%s template=%s",
            hierarchy_parent.get("error"), operation_id, ado_id,
            hierarchy_parent.get("parent_type"), hierarchy_parent.get("process_template"),
        )
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=actions,
            error=hierarchy_parent.get("message"),
            operation_id=operation_id,
            payload_sha256=payload_sha256,
            repo_root=str(repo_root),
        )
        return jsonify({
            "ok": False,
            "error": hierarchy_parent.get("error") or "ADO_HIERARCHY_NOT_SUPPORTED",
            "message": hierarchy_parent.get("message"),
            "parent_type": hierarchy_parent.get("parent_type"),
            "child_type": "Task",
            "process_template": hierarchy_parent.get("process_template"),
            "allowed_children": hierarchy_parent.get("allowed_children"),
            "hierarchy_bridge": hierarchy_parent.get("hierarchy_bridge"),
            "epic_ado_id": ado_id,
            "task_ado_id": None,
            "task_url": None,
            "attachment_id": None,
            "actions": actions,
            "pending_task_consumed": False,
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "payload_sha256": payload_sha256,
        }), 422
    task_parent_ado_id = int(hierarchy_parent.get("parent_ado_id") or ado_id)

    # ── [2] create_work_item ───────────────────────────────────────────────────
    # No mandamos System.State en la creación: ADO rechaza con 400 cualquier
    # valor que no esté en la lista de estados iniciales del process template
    # (ej. "Technical review"). Dejamos que ADO use el estado por defecto
    # ("To Do" en Agile / "New" en Scrum) y, si target_state es distinto,
    # intentamos transicionarlo con un PATCH post-creación (paso [2b]).
    target_state = (pt_payload.get("target_state") or "").strip()
    try:
        wi_result = ado.create_work_item(
            work_item_type="Task",
            fields={
                "System.Title": pt_payload["title"],
                "System.Description": pt_payload.get("description_html", ""),
            },
            parent_ado_id=task_parent_ado_id,
        )
        task_ado_id = int(wi_result["id"])
        task_url = ado.work_item_url(task_ado_id)
        actions.append({
            "action": "create_work_item",
            "ok": True,
            "task_ado_id": task_ado_id,
            "parent_ado_id": task_parent_ado_id,
        })
    except _AdoApiError as exc:
        # Inc.3 P0: si el rechazo de ADO es por jerarquía (Epic→Task no permitido
        # en el process template), lo mapeamos a ADO_HIERARCHY_NOT_SUPPORTED para
        # que el operador entienda que necesita un nivel intermedio — no un retry.
        _raw = str(exc)
        _raw_low = _raw.lower()
        _is_hierarchy = (
            "tf401347" in _raw_low
            or "not allowed" in _raw_low
            or "is not a valid parent" in _raw_low
            or ("parent" in _raw_low and "child" in _raw_low and "type" in _raw_low)
        )
        _error_code = "ADO_HIERARCHY_NOT_SUPPORTED" if _is_hierarchy else "ADO_CREATE_WORK_ITEM_FAILED"
        logger.warning(
            "create_child_task: %s operation_id=%s "
            "ado_id=%s payload_sha256=%s err=%s",
            _error_code, operation_id, ado_id, payload_sha256, _raw[:200],
        )
        actions.append({
            "action": "create_work_item",
            "ok": False,
            "reason": (
                "ADO_HIERARCHY_NOT_SUPPORTED" if _is_hierarchy
                else ("ADO_CREATE_REJECTED_BY_POLICY" if "403" in _raw else str(type(exc).__name__))
            ),
            "detail": _raw[:300],
        })
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=actions,
            error=_raw,
            operation_id=operation_id,
            payload_sha256=payload_sha256,
            repo_root=str(repo_root),
        )
        return jsonify({
            "ok": False,
            "error": _error_code,
            "message": _extract_ado_error_message(_raw),
            "dry_run": False,
            "epic_ado_id": ado_id,
            "task_parent_ado_id": task_parent_ado_id,
            "task_ado_id": None,
            "task_url": None,
            "attachment_id": None,
            "actions": actions,
            "hierarchy_bridge": hierarchy_parent.get("hierarchy_bridge"),
            "pending_task_consumed": False,
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "payload_sha256": payload_sha256,
        }), (422 if _is_hierarchy else 200)

    # ── [2b] Transicionar al target_state si fue solicitado ────────────────────
    # Ignoramos estados vacíos y los defaults típicos ("To Do" en Agile, "New"
    # en Scrum). Si el PATCH falla (estado no válido o transición no permitida
    # por el process), lo registramos como acción fallida pero NO revertimos
    # la creación de la Task ni interrumpimos el flujo — la Task queda en su
    # estado inicial y el operador puede ajustarlo manualmente en ADO.
    if target_state and target_state.lower() not in ("to do", "new", "to-do", "todo"):
        try:
            ado.update_work_item_state(task_ado_id, target_state)
            actions.append({
                "action": "set_state",
                "ok": True,
                "to": target_state,
            })
        except Exception as exc:  # noqa: BLE001 — incluye _AdoApiError y errores inesperados
            actions.append({
                "action": "set_state",
                "ok": False,
                "reason": "ADO_STATE_TRANSITION_REJECTED",
                "to": target_state,
                "detail": str(exc)[:300],
            })
            human_action_required = (
                f"Task ADO-{task_ado_id} creada en estado inicial; "
                f"transición a '{target_state}' rechazada por ADO. "
                f"Ajustar manualmente en ADO si corresponde."
            )

    # ── [2c] Verificación post-creación (Inc.3 P0) ─────────────────────────────
    # ADO puede aceptar el create pero NO aplicar el link jerárquico inválido,
    # dejando una Task HUÉRFANA (sin padre). Releemos el work item y verificamos
    # que System.Parent apunte al Epic. Si no, NO consumimos el pending-task.json
    # (queda pendiente para reintento/creación manual) y devolvemos error claro:
    # nunca damos por hecho una Task hija que en ADO no existe como tal.
    verify = _verify_child_task_created(
        ado=ado,
        task_ado_id=task_ado_id,
        epic_ado_id=task_parent_ado_id,
        expected_title=pt_payload.get("title", ""),
        operation_id=operation_id,
    )
    if verify is not None and not verify.get("ok"):
        actions.append({
            "action": "verify_creation",
            "ok": False,
            "reason": verify.get("reason"),
            "detail": verify.get("detail"),
        })
        human_action_required = (
            f"Task ADO-{task_ado_id} creada pero su vínculo al Epic {ado_id} no se "
            f"verificó ({verify.get('reason')}). Revisar en ADO y reparentar o borrar; "
            f"el pending-task.json queda pendiente."
        )
        logger.warning(
            "create_child_task: ADO_CHILD_TASK_VERIFICATION_FAILED operation_id=%s "
            "ado_id=%s task_ado_id=%s reason=%s",
            operation_id, ado_id, task_ado_id, verify.get("reason"),
        )
        _audit_create_child_task(
            correlation_id=correlation_id,
            ado_id=ado_id,
            user=user,
            completion_source=completion_source,
            operator_reason=operator_reason,
            pt_path=pending_task_path_str,
            ok=False,
            actions=actions,
            error=verify.get("detail") or verify.get("reason"),
            level="WARNING",
            task_ado_id=task_ado_id,
            operation_id=operation_id,
            payload_sha256=payload_sha256,
            repo_root=str(repo_root),
        )
        return jsonify({
            "ok": False,
            "error": "ADO_CHILD_TASK_VERIFICATION_FAILED",
            "message": verify.get("detail") or verify.get("reason"),
            "dry_run": False,
            "epic_ado_id": ado_id,
            "task_parent_ado_id": task_parent_ado_id,
            "task_ado_id": task_ado_id,
            "task_url": task_url,
            "attachment_id": None,
            "actions": actions,
            "hierarchy_bridge": hierarchy_parent.get("hierarchy_bridge"),
            "pending_task_consumed": False,
            "human_action_required": human_action_required,
            "correlation_id": correlation_id,
            "operation_id": operation_id,
            "payload_sha256": payload_sha256,
        }), 422
    if verify is not None and verify.get("ok"):
        actions.append({"action": "verify_creation", "ok": True})

    # ── [3] upload_attachment ──────────────────────────────────────────────────
    if plan_exists and plan_path is not None:
        try:
            attach_result = ado.upload_attachment(
                file_path=plan_path,
                file_name="plan-de-pruebas.md",
            )
            attachment_id = attach_result.get("id") or attach_result.get("url", "")
            attach_url = attach_result.get("url", "")
            actions.append({
                "action": "upload_attachment",
                "ok": True,
                "attachment_id": attachment_id,
            })

            # ── [4] link_attachment_to_work_item ───────────────────────────────
            try:
                ado.link_attachment_to_work_item(
                    work_item_id=task_ado_id,
                    attachment_url=attach_url,
                    comment=f"Plan de pruebas - {pt_payload.get('rf_id', '')}",
                )
                actions.append({"action": "link_attachment", "ok": True})
            except _AdoApiError as exc:
                actions.append({
                    "action": "link_attachment",
                    "ok": False,
                    "reason": str(exc)[:300],
                })

        except _AdoApiError as exc:
            # Fallo de upload — Task creada pero adjunto no subido (degraded state CA-06)
            attachment_id = None
            attach_url = None
            actions.append({
                "action": "upload_attachment",
                "ok": False,
                "reason": "ATTACHMENT_UPLOAD_FAILED",
                "detail": str(exc)[:300],
            })
            human_action_required = (
                f"Task ADO-{task_ado_id} creada; subida de adjunto falló. "
                f"Reintentar o adjuntar plan-de-pruebas.md manualmente en ADO-{task_ado_id}."
            )
            # Registrar estado parcial en SystemLog con nivel WARNING
            _audit_create_child_task(
                correlation_id=correlation_id,
                ado_id=ado_id,
                user=user,
                completion_source=completion_source,
                operator_reason=operator_reason,
                pt_path=pending_task_path_str,
                ok=False,
                actions=actions,
                error=f"PARTIAL_FAILURE: Task {task_ado_id} creada, adjunto falló",
                level="WARNING",
                task_ado_id=task_ado_id,
                operation_id=operation_id,
                payload_sha256=payload_sha256,
                repo_root=str(repo_root),
            )
            return jsonify({
                "ok": False,
                "dry_run": False,
                "epic_ado_id": ado_id,
                "task_ado_id": task_ado_id,
                "task_url": task_url,
                "attachment_id": None,
                "actions": actions,
                "pending_task_consumed": False,
                "human_action_required": human_action_required,
                "correlation_id": correlation_id,
                "operation_id": operation_id,
                "payload_sha256": payload_sha256,
            })
    else:
        # Plan no existe — registrar como omitido
        actions.append({
            "action": "upload_attachment",
            "ok": False,
            "reason": "ATTACHMENT_FILE_NOT_FOUND",
            "detail": f"plan-de-pruebas.md no encontrado en {plan_rel}",
        })

    # ── [5] post_comment con operator_reason ──────────────────────────────────
    # Fase 1: post_comment ya no degrada silencioso — devuelve dict con id o
    # levanta AdoApiError. Aqui es no-critico (la Task ya fue creada): si falla
    # registramos la accion como ok=false con detalle visible, pero NO bloqueamos
    # el mark_consumed ni alteramos el overall_ok del flujo principal de Task.
    if operator_reason:
        comment_text = (
            f"<p><b>Creado desde Stacky Agents.</b></p>"
            f"<p><b>Motivo del operador:</b> {operator_reason}</p>"
            f"<p><em>correlation_id: {correlation_id}</em></p>"
            f"<!-- stacky-comment:create_child_task:operation_id={operation_id} -->"
        )
        try:
            resp = ado.post_comment(task_ado_id, comment_text, fmt="html")
            actions.append({
                "action": "post_comment",
                "ok": True,
                "comment_id": resp.get("id") if isinstance(resp, dict) else None,
            })
        except Exception as exc:
            logger.warning(
                "create_child_task: post_comment fallo operation_id=%s task_ado_id=%s err=%s",
                operation_id, task_ado_id, exc,
            )
            actions.append({
                "action": "post_comment",
                "ok": False,
                "reason": str(exc)[:200],
            })

    # ── [6] Marcar pending-task.json como consumed ────────────────────────────
    _mark_pending_task_consumed(
        pt_file=pt_file,
        task_ado_id=task_ado_id,
        attachment_id=attachment_id,
        operator_reason=operator_reason,
        operation_id=operation_id,
        payload_sha256=payload_sha256,
    )
    actions.append({"action": "mark_consumed", "ok": True})

    # ── [7] Auditoría ─────────────────────────────────────────────────────────
    _audit_create_child_task(
        correlation_id=correlation_id,
        ado_id=ado_id,
        user=user,
        completion_source=completion_source,
        operator_reason=operator_reason,
        pt_path=pending_task_path_str,
        ok=True,
        actions=actions,
        task_ado_id=task_ado_id,
        operation_id=operation_id,
        payload_sha256=payload_sha256,
        repo_root=str(repo_root),
    )
    logger.info(
        "create_child_task: succeeded operation_id=%s ado_id=%s task_ado_id=%s "
        "payload_sha256=%s actions=%s",
        operation_id, ado_id, task_ado_id, payload_sha256,
        [{"a": a.get("action"), "ok": a.get("ok")} for a in actions],
    )

    overall_ok = all(
        a.get("ok") for a in actions
        if a["action"] not in ("upload_attachment",)  # adjunto faltante no bloquea ok general
        or a.get("reason") != "ATTACHMENT_FILE_NOT_FOUND"
    )

    response_payload = {
        "ok": overall_ok,
        "dry_run": False,
        "epic_ado_id": ado_id,
        "task_parent_ado_id": task_parent_ado_id,
        "task_ado_id": task_ado_id,
        "task_url": task_url,
        "attachment_id": attachment_id,
        "actions": actions,
        "hierarchy_bridge": hierarchy_parent.get("hierarchy_bridge"),
        "pending_task_consumed": True,
        "idempotent": False,
        "correlation_id": correlation_id,
        "operation_id": operation_id,
        "payload_sha256": payload_sha256,
    }
    if human_action_required:
        response_payload["human_action_required"] = human_action_required
    return jsonify(response_payload)


# ── Helpers privados para create_child_task ───────────────────────────────────

def _extract_ado_error_message(raw: str) -> str:
    """Extrae un mensaje human-readable del error envuelto que devuelve AdoClient.

    Formato típico:
        "ADO POST <url> → <status>: <json-body>"
    donde <json-body> incluye un campo "ErrorMessage" o "Message" con el detalle
    real del rechazo de ADO. Si no podemos parsear el JSON, devolvemos el raw
    truncado para que el operador igual vea algo útil.
    """
    if not raw:
        return "Error desconocido de ADO"
    body_start = raw.find("{")
    if body_start >= 0:
        body = raw[body_start:]
        try:
            parsed = json.loads(body)
            msg = (
                parsed.get("ErrorMessage")
                or parsed.get("Message")
                or parsed.get("message")
            )
            if isinstance(parsed.get("customProperties"), dict):
                msg = msg or parsed["customProperties"].get("ErrorMessage")
            if msg:
                return str(msg)[:400]
        except (ValueError, TypeError):
            pass
    return raw[:400]


def _mark_pending_task_consumed(
    pt_file: Path,
    task_ado_id: int,
    attachment_id: str | None,
    operator_reason: str,
    operation_id: str | None = None,
    payload_sha256: str | None = None,
) -> None:
    """Actualiza el pending-task.json en disco para marcarlo como consumido.

    Usa un threading.Lock a nivel proceso para garantizar exclusión mutua
    en Flask single-process. En multi-proceso (Gunicorn multi-worker) la
    protección es a nivel de OS file lock si portalocker está disponible.

    Fase 0 plan creacion-tareas-comentarios-100-efectiva (2026-05-29):
    persiste operation_id y payload_sha256 en el archivo para que la
    auditoria local pueda correlacionar el archivo con la operacion ADO
    aun si el SystemLog se pierde o el operador re-genera el JSON.
    """
    import threading
    _FILE_LOCK = threading.Lock()

    with _FILE_LOCK:
        # Re-leer para detectar concurrent write (idempotencia defensiva)
        try:
            current = json.loads(pt_file.read_text(encoding="utf-8"))
        except Exception:
            current = {}

        if "consumed_at" in current:
            # Ya fue consumido por otra request concurrente — no sobreescribir
            return

        current["consumed_at"] = datetime.now(timezone.utc).isoformat()
        current["task_ado_id"] = task_ado_id
        current["attachment_id"] = attachment_id
        current["status"] = "consumed"
        if operator_reason:
            current["operator_reason"] = operator_reason
        if operation_id:
            current["operation_id"] = operation_id
        if payload_sha256:
            current["payload_sha256"] = payload_sha256

        pt_file.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _audit_create_child_task(
    *,
    correlation_id: str,
    ado_id: int,
    user: str,
    completion_source: str,
    operator_reason: str,
    pt_path: str,
    ok: bool,
    actions: list[dict],
    task_ado_id: int | None = None,
    error: str | None = None,
    level: str = "INFO",
    operation_id: str | None = None,
    payload_sha256: str | None = None,
    repo_root: str | None = None,
) -> None:
    """Persiste el evento de create_child_task en SystemLog (CA-07, CA-08).

    Fase 0 plan creacion-tareas-comentarios-100-efectiva (2026-05-29):
    incluye operation_id, payload_sha256 y repo_root para diagnostico
    end-to-end y permitir reconciliacion con el pending-task.json.
    """
    ctx = {
        "correlation_id": correlation_id,
        "operation_id": operation_id or correlation_id,
        "payload_sha256": payload_sha256,
        "repo_root": repo_root,
        "ado_id": ado_id,
        "completion_source": completion_source,
        "operator_reason": operator_reason,
        "pending_task_path": pt_path,
        "task_ado_id": task_ado_id,
        "ok": ok,
        "actions_summary": [
            {"action": a["action"], "ok": a.get("ok")} for a in actions
        ],
    }
    if error:
        ctx["error"] = error[:500]

    tags = ["create_child_task", completion_source]
    if not ok:
        tags.append("partial_failure" if task_ado_id else "failure")
        if error:
            level = level or "WARNING"

    try:
        with session_scope() as session:
            log = SystemLog(
                level=level,
                source="create_child_task",
                action="create_child_task_succeeded" if ok else "create_child_task_failed",
                trigger="create_child_task",
                user=user,
                context_json=json.dumps(ctx, ensure_ascii=False, default=str),
                tags_json=json.dumps(tags),
            ) if _system_log_has_trigger() else SystemLog(
                level=level,
                source="create_child_task",
                action="create_child_task_succeeded" if ok else "create_child_task_failed",
                user=user,
                context_json=json.dumps(ctx, ensure_ascii=False, default=str),
                tags_json=json.dumps(tags),
            )
            session.add(log)
    except Exception:  # noqa: BLE001
        logger.exception("create_child_task: audit SystemLog falló (no crítico)")


def _system_log_has_trigger() -> bool:
    """Detecta si SystemLog tiene el campo 'trigger' (compatibilidad con versiones anteriores)."""
    from models import SystemLog as _SL
    return hasattr(_SL, "trigger")


# ── P6: Recomendador de Asignacion ────────────────────────────────────────────

@bp.post("/<int:ticket_id>/assignment-recommendations")
def assignment_recommendations(ticket_id: int):
    """Genera recomendaciones de asignacion para un ticket.

    POST /api/tickets/{ticket_id}/assignment-recommendations

    Payload opcional (filtros):
      {
        "max_load_pct": 80,
        "only_skill": "frontend",
        "only_area_path": "Strategist_Pacifico\\\\UI",
        "exclude_ado_unique_names": ["admin@ubimia.com"]
      }

    advisory_only y publish_requires_human_approval son siempre true.
    """
    import time as _time
    from services.ticket_assigner import compute_recommendations
    from services.stacky_logger import logger as stacky_logger

    filters = request.get_json(silent=True) or {}
    t_start = _time.monotonic()

    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).first()
        if ticket is None:
            return jsonify({
                "ok": False,
                "error": "ticket_not_found",
                "message": f"Ticket {ticket_id} no existe en BD local",
            }), 404

        # Verificar si hay usuarios configurados
        from models import User
        has_users = session.query(User).filter(User.ado_unique_name.isnot(None)).first() is not None
        if not has_users:
            return jsonify({
                "ok": False,
                "error": "no_users_configured",
                "message": "No hay usuarios con ado_unique_name configurado. Usa POST /api/users/sync-from-ado primero.",
            }), 400

        result = compute_recommendations(ticket, filters)

    duration_ms = int((_time.monotonic() - t_start) * 1000)
    result["ticket_id"] = ticket_id
    result["duration_ms"] = duration_ms

    stacky_logger.info(
        "ticket_assigner",
        "assignment_recommendation_generated",
        ticket_id=ticket_id,
        context={
            "ticket_ado_id": result.get("ticket_ado_id"),
            "candidates_count": len(result.get("candidates") or []),
            "top_score": result["candidates"][0]["score"] if result.get("candidates") else None,
            "filters_applied": filters,
            "duration_ms": duration_ms,
        }
    )

    return jsonify(result)


@bp.post("/<int:ticket_id>/assign")
def assign_ticket(ticket_id: int):
    """Aplica una asignacion en ADO con doble confirmacion (human-in-the-loop).

    POST /api/tickets/{ticket_id}/assign

    Payload:
      {
        "ado_unique_name": "jluca@ubimia.com",   // requerido
        "dry_run": true,                           // default: true — NUNCA escribe sin dry_run=false explicito
        "reason": "Asignado por recomendacion"    // opcional
      }

    Con dry_run=true: devuelve lo que haria sin ejecutar nada en ADO.
    Con dry_run=false: llama a AdoClient.update_work_item_assigned_to().
    """
    from services.stacky_logger import logger as stacky_logger

    body = request.get_json(silent=True) or {}
    ado_unique_name = (body.get("ado_unique_name") or "").strip()
    dry_run = body.get("dry_run", True)  # default siempre True
    reason = body.get("reason") or "Asignacion manual desde Stacky"
    operator = request.headers.get("X-User-Email") or "unknown"

    if not ado_unique_name:
        return jsonify({
            "ok": False,
            "error": "missing_field",
            "message": "Campo 'ado_unique_name' requerido",
        }), 400

    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).first()
        if ticket is None:
            return jsonify({
                "ok": False,
                "error": "ticket_not_found",
                "message": f"Ticket {ticket_id} no existe en BD local",
            }), 404

        # Validar que el usuario exista en BD local (no permitir emails arbitrarios)
        from models import User
        user_row = session.query(User).filter_by(ado_unique_name=ado_unique_name).first()
        if user_row is None:
            return jsonify({
                "ok": False,
                "error": "user_not_found",
                "message": f"Usuario '{ado_unique_name}' no encontrado en BD local. Ejecuta sync-from-ado primero.",
            }), 404

        ado_id = ticket.ado_id
        current_assigned = ticket.assigned_to_ado

        if dry_run:
            stacky_logger.info(
                "ticket_assigner",
                "assignment_dry_run",
                ticket_id=ticket_id,
                context={
                    "ado_id": ado_id,
                    "ado_unique_name": ado_unique_name,
                    "current_assigned": current_assigned,
                    "operator": operator,
                }
            )
            return jsonify({
                "ok": True,
                "dry_run": True,
                "ticket_id": ticket_id,
                "ticket_ado_id": ado_id,
                "would_assign_to": ado_unique_name,
                "current_assigned": current_assigned,
                "reason": reason,
                "actions": [
                    {"action": "ado_patch_assigned_to", "would_call": f"PATCH ADO WI {ado_id} System.AssignedTo={ado_unique_name}"},
                    {"action": "local_db_update_assigned_to", "would_call": f"UPDATE tickets SET assigned_to_ado='{ado_unique_name}' WHERE id={ticket_id}"},
                ],
                "advisory_only": True,
                "message": "Preview de asignacion. Enviá dry_run=false para confirmar.",
            })

        # dry_run=false: aplicar asignacion real
        ado_ok = False
        ado_error = None
        try:
            _ado_client_for_ticket(ticket=ticket).update_work_item_assigned_to(ado_id, ado_unique_name)
            ado_ok = True
        except Exception as e:
            ado_error = str(e)
            logger.error("assign_ticket: fallo ADO — %s", e)

        local_ok = False
        if ado_ok:
            try:
                ticket.assigned_to_ado = ado_unique_name
                local_ok = True
            except Exception as e:
                logger.error("assign_ticket: fallo BD local — %s", e)

        stacky_logger.info(
            "ticket_assigner",
            "assignment_applied" if ado_ok else "assignment_failed",
            ticket_id=ticket_id,
            context={
                "ado_id": ado_id,
                "ado_unique_name": ado_unique_name,
                "ado_ok": ado_ok,
                "local_ok": local_ok,
                "ado_error": ado_error,
                "operator": operator,
            }
        )

        if not ado_ok:
            return jsonify({
                "ok": False,
                "dry_run": False,
                "ticket_id": ticket_id,
                "ticket_ado_id": ado_id,
                "error": "ado_api_error",
                "message": ado_error or "Error desconocido al llamar a ADO",
                "rollback_needed": False,
                "ado_updated": False,
                "local_db_updated": False,
            }), 502

        return jsonify({
            "ok": True,
            "dry_run": False,
            "ticket_id": ticket_id,
            "ticket_ado_id": ado_id,
            "assigned_to": ado_unique_name,
            "ado_updated": ado_ok,
            "local_db_updated": local_ok,
            "operator": operator,
            "actions": [
                {"action": "ado_patch_assigned_to", "ok": ado_ok},
                {"action": "local_db_update_assigned_to", "ok": local_ok},
            ],
        })


# ── P6: Panel de estadisticas por usuario ────────────────────────────────────

@bp.get("/user-stats")
def user_stats():
    """Devuelve estadisticas de tickets por usuario.

    GET /api/tickets/user-stats?user=jluca@ubimia.com

    Incluye tickets actuales y historicos por estado.
    """
    from services.ticket_assigner import get_user_stats

    ado_unique_name = request.args.get("user") or None
    result = get_user_stats(ado_unique_name)
    return jsonify({
        "ok": True,
        "users": result,
        "total": len(result),
    })


# ── P6: Auto-poblado de usuarios desde historial ADO ─────────────────────────

@bp.post("/users/sync-from-ado")
def sync_users_from_ado():
    """Puebla la tabla users con los asignados encontrados en tickets.

    POST /api/tickets/users/sync-from-ado

    No sobreescribe campos ya configurados manualmente.
    """
    from services.ticket_assigner import sync_users_from_ado_history
    from services.stacky_logger import logger as stacky_logger

    result = sync_users_from_ado_history()

    stacky_logger.info(
        "user_sync",
        "users_synced_from_ado_history",
        context=result,
    )

    return jsonify({"ok": True, **result})


# ── Requerimiento B (plan 2026-05-27): identidad ADO del operador ────────────

@bp.get("/ado-user")
def get_ado_user():
    """Resuelve y cachea la identidad ADO del operador para 'Mis tareas'.

    GET /api/tickets/ado-user?project=RSPACIFICO[&refresh=1]

    - Sin refresh: devuelve el mapeo cacheado si existe; si no, lo resuelve.
    - Con refresh=1: fuerza re-resolución vía PAT y re-cachea.

    Respuesta: { ok, linked, ado_unique_name, ado_display_name, verified_at,
                 stacky_user, project, source }
    """
    from services.ado_identity import (
        current_stacky_user,
        get_cached_identity,
        save_identity,
    )

    project_name = _request_project_name()
    refresh = request.args.get("refresh", "0") in {"1", "true", "yes"}
    stacky_user = current_stacky_user()

    cached = get_cached_identity(project_name or "")
    if cached and cached.get("ado_unique_name") and not refresh:
        return jsonify({
            "ok": True,
            "linked": True,
            "source": "cache",
            "ado_unique_name": cached.get("ado_unique_name"),
            "ado_display_name": cached.get("ado_display_name"),
            "verified_at": cached.get("verified_at"),
            "stacky_user": cached.get("stacky_user", stacky_user),
            "project": cached.get("project"),
        })

    try:
        identity = _ado_client_for_ticket(project_name=project_name).get_authenticated_user()
    except (AdoConfigError, _AdoConfigError) as exc:
        return jsonify({"ok": False, "linked": False, "error": "config", "message": str(exc)}), 400
    except (AdoApiError, _AdoApiError) as exc:
        return _ado_sync_error_response(exc, route_label="ado-user", project_name=project_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ado-user — fallo inesperado")
        return jsonify({"ok": False, "linked": False, "error": "unexpected", "message": str(exc)}), 500

    if not identity.get("unique_name"):
        return jsonify({
            "ok": True, "linked": False, "source": "ado",
            "message": "ADO no devolvió un identificador de usuario para el PAT configurado.",
            "ado_display_name": identity.get("display_name"),
            "stacky_user": stacky_user,
        })

    entry = save_identity(project_name or "", identity, stacky_user=stacky_user)
    return jsonify({
        "ok": True,
        "linked": True,
        "source": "ado",
        "ado_unique_name": entry["ado_unique_name"],
        "ado_display_name": entry["ado_display_name"],
        "verified_at": entry["verified_at"],
        "stacky_user": entry["stacky_user"],
        "project": entry["project"],
    })


# ── Feature B: Diagnosticos causales de bloqueos ─────────────────────────────

@bp.get("/<int:ticket_id>/diagnostics")
def ticket_diagnostics(ticket_id: int):
    """Genera un diagnostico causal sobre por que un ticket no avanza.

    GET /api/tickets/{ticket_id}/diagnostics

    Respeta cache de 60 minutos. Invalida con DELETE.
    """
    from services.ticket_diagnostics import generate_diagnostics

    result = generate_diagnostics(ticket_id)
    status = 200 if result.get("ok") else 404
    return jsonify(result), status


@bp.delete("/<int:ticket_id>/diagnostics/cache")
def invalidate_diagnostics_cache(ticket_id: int):
    """Invalida la cache de diagnostico para un ticket.

    DELETE /api/tickets/{ticket_id}/diagnostics/cache
    """
    from services.ticket_diagnostics import invalidate_cache

    removed = invalidate_cache(ticket_id)
    return jsonify({"ok": True, "ticket_id": ticket_id, "cache_removed": removed})


# ── P7: Endpoints extendidos de sync ─────────────────────────────────────────

# Rate limiting simple en memoria (P7)
import time as _sync_time
_SYNC_MIN_INTERVAL_SEC = 15
_last_sync_ts_by_project: dict[str, float] = {}
_sync_in_progress_by_project: set[str] = set()


@bp.post("/sync-v2")
def sync_from_ado_v2():
    """Sync con rate limiting, observabilidad y campos extendidos de respuesta.

    POST /api/tickets/sync-v2

    Diferencias vs /sync:
    - Rate limiting: minimo 15s entre syncs (configurable STACKY_SYNC_MIN_INTERVAL_SEC)
    - Campo duration_ms en respuesta
    - Campo idempotent: true si no hubo cambios
    - Header X-Stacky-Trigger registrado en system_logs
    - Flag sync_in_progress para evitar syncs concurrentes
    """
    min_interval = int(os.environ.get("STACKY_SYNC_MIN_INTERVAL_SEC", _SYNC_MIN_INTERVAL_SEC))
    now = _sync_time.time()
    triggered_by = request.headers.get("X-Stacky-Trigger", "manual")
    project_name = _request_project_name()
    ctx = resolve_project_context(project_name=project_name)
    sync_scope = ctx.stacky_project_name if ctx else "__global__"
    last_sync_ts = _last_sync_ts_by_project.get(sync_scope, 0.0)

    # Rate limiting
    if now - last_sync_ts < min_interval:
        remaining = int(min_interval - (now - last_sync_ts))
        return jsonify({
            "ok": False,
            "error": "rate_limited",
            "message": f"Sync demasiado frecuente. Espera {remaining}s.",
            "retry_after_sec": remaining,
            "project": ctx.stacky_project_name if ctx else project_name,
        }), 429

    # Evitar syncs concurrentes
    if sync_scope in _sync_in_progress_by_project:
        return jsonify({
            "ok": False,
            "error": "sync_in_progress",
            "message": "Ya hay un sync en curso. Intentá en unos segundos.",
            "project": ctx.stacky_project_name if ctx else project_name,
        }), 409

    _last_sync_ts_by_project[sync_scope] = now
    _sync_in_progress_by_project.add(sync_scope)
    t_start = _sync_time.monotonic()

    try:
        result = sync_tickets(client=_ado_client_for_ticket(project_name=project_name))
    except AdoConfigError as e:
        _sync_in_progress_by_project.discard(sync_scope)
        logger.warning("ADO sync-v2 — config: %s", e)
        return jsonify({"ok": False, "error": "config", "message": str(e)}), 400
    except AdoApiError as e:
        _sync_in_progress_by_project.discard(sync_scope)
        return _ado_sync_error_response(e, route_label="sync-v2", project_name=project_name)
    except Exception as e:
        _sync_in_progress_by_project.discard(sync_scope)
        logger.exception("ADO sync-v2 — fallo inesperado")
        return jsonify({"ok": False, "error": "unexpected", "message": str(e)}), 500
    finally:
        _sync_in_progress_by_project.discard(sync_scope)

    duration_ms = int((_sync_time.monotonic() - t_start) * 1000)
    idempotent = result.get("created", 0) == 0 and result.get("updated", 0) == 0 and result.get("removed", 0) == 0

    from services.stacky_logger import logger as stacky_logger
    stacky_logger.info(
        "ado_sync",
        "sync_completed",
        context={
            "fetched": result.get("fetched"),
            "created": result.get("created"),
            "updated": result.get("updated"),
            "removed": result.get("removed"),
            "duration_ms": duration_ms,
            "triggered_by": triggered_by,
            "idempotent": idempotent,
            "project_name": result.get("stacky_project_name") or (ctx.stacky_project_name if ctx else project_name),
        }
    )

    return jsonify({
        "ok": True,
        **result,
        "duration_ms": duration_ms,
        "idempotent": idempotent,
        "triggered_by": triggered_by,
        "project_name": result.get("stacky_project_name") or (ctx.stacky_project_name if ctx else project_name),
    })


@bp.get("/sync/status-v2")
def sync_status_v2():
    """Devuelve el estado extendido de la ultima sincronizacion.

    GET /api/tickets/sync/status-v2

    Incluye:
    - last_synced_at
    - seconds_since_sync
    - is_stale
    - stale_threshold_sec
    - sync_in_progress
    """
    stale_threshold = int(os.environ.get("STACKY_STALE_THRESHOLD_SEC", 120))
    project_name = _request_project_name()
    ctx = resolve_project_context(project_name=project_name)
    sync_scope = ctx.stacky_project_name if ctx else "__global__"
    last = get_last_sync_at(project_name=project_name)
    seconds_since = None
    is_stale = False

    if last:
        seconds_since = int((datetime.utcnow() - last).total_seconds())
        is_stale = seconds_since > stale_threshold

    return jsonify({
        "project_name": ctx.stacky_project_name if ctx else project_name,
        "last_synced_at": last.isoformat() if last else None,
        "seconds_since_sync": seconds_since,
        "is_stale": is_stale,
        "stale_threshold_sec": stale_threshold,
        "sync_in_progress": sync_scope in _sync_in_progress_by_project,
    })


@bp.get("/config/frontend")
def frontend_config():
    """Devuelve la configuracion del frontend relevante para auto-refresh.

    GET /api/tickets/config/frontend
    """
    return jsonify({
        "ticket_sync_interval_ms": int(os.environ.get("STACKY_TICKET_SYNC_INTERVAL_MS", 45000)),
        "sync_min_interval_sec": int(os.environ.get("STACKY_SYNC_MIN_INTERVAL_SEC", _SYNC_MIN_INTERVAL_SEC)),
        "stale_threshold_sec": int(os.environ.get("STACKY_STALE_THRESHOLD_SEC", 120)),
    })
