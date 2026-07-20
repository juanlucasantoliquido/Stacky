"""Plan 177 F4 — Auto-PR del Dev Resolutor de Incidencias.

Post-hook AGNÓSTICO de runtime (se dispara desde `ticket_status.on_execution_end`
para los 3 runtimes): al terminar un run `incident_dev` con `completed` y un intent
`open_pr`, enumera el delta del working tree, commitea los archivos (código + tests)
a una rama nueva vía el PROVEEDOR MR (REST, PAT del proyecto; sin git push local) y
abre el PR, comentando el link en la Issue.

NUNCA mergea/cierra/transiciona la Issue ni aprueba el PR: el PR es la propuesta que
el operador revisa. Corre en el thread del runner SIN app/request context → PROHIBIDO
`jsonify`/`request` (G8). Idempotente por `execution_id`; los fallos NUNCA quedan mudos
(comentario + log + `status="error"` en el intent, regla Plan 135).
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("stacky.services.incident_dev_autocommit")

_BRANCH_PREFIX = "stacky/incidencia-"   # + {ticket_id}-exec-{execution_id}
_MAX_FILES = 60                          # cap de archivos por PR (ver Riesgos R5)
_MAX_TEXT_BYTES = 1_000_000              # C7 — cap de texto propio del auto-PR (NO el del intake)
_TERMINAL_STATUSES = ("opened", "blocked_empty", "error", "skipped")


def maybe_open_pr_for_incident_dev(*, ticket_id, execution_id, final_status, agent_type, error=None, **_):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_INCIDENT_DEV_PR_ENABLED", False):
        return
    if agent_type != "incident_dev" or final_status != "completed":
        return
    from services import incident_dev_pr
    intent = incident_dev_pr.get_intent(execution_id)
    if not intent or not intent.get("open_pr"):
        return
    if intent.get("status") in _TERMINAL_STATUSES:
        return  # idempotente: ya se procesó este execution_id

    # C4 — el post-hook recibe la PK LOCAL del Ticket. Para comentar en el tracker
    # hace falta el ado_id; para el proveedor MR, el stacky_project_name. Una vez.
    ado_id, project = _ticket_ado_id_and_project(ticket_id)

    repo_root = intent.get("repo_root")
    baseline = intent.get("baseline") or {}
    try:
        current = incident_dev_pr.snapshot_worktree(repo_root)
        delta = incident_dev_pr.compute_changed_files(baseline, current)
        changed = delta.get("added_or_modified") or []
        deleted = delta.get("deleted") or []
        if not changed:
            # ⚠️ BLOQUEADO o diff vacío → NO se abre PR (K3).
            incident_dev_pr.mark_intent(execution_id, status="blocked_empty")
            _comment_issue_safe(ado_id, project, "🔧 El Dev Resolutor no dejó cambios de código, así que no se abrió ningún PR.")
            return
        if len(changed) > _MAX_FILES:
            incident_dev_pr.mark_intent(execution_id, status="skipped",
                                        error=f"demasiados archivos ({len(changed)} > {_MAX_FILES})")
            _comment_issue_safe(ado_id, project, f"🔧 El fix tocó {len(changed)} archivos (> {_MAX_FILES}); no se abrió PR automático. Revisá el working tree.")
            return

        # [ADICIÓN ARQUITECTO] Guardia de mapeo working-tree ↔ repo del tracker (C5).
        origin = incident_dev_pr.remote_origin_url(repo_root)
        if _worktree_maps_to_wrong_repo(origin, project):
            incident_dev_pr.mark_intent(execution_id, status="skipped",
                                        error=f"origin del working tree ({origin}) no mapea al repo del tracker")
            _comment_issue_safe(ado_id, project, f"🔧 El working tree apunta a otro remoto ({origin}); no se abrió PR automático para no commitear en el repo equivocado. Revisá manualmente.")
            return

        classify = incident_dev_pr.classify_changed_files(changed)
        branch = f"{_BRANCH_PREFIX}{ticket_id}-exec-{execution_id}"
        title, description = _build_pr_body(ado_id, classify, deleted, origin)

        from services.repo_writer import get_repo_writer
        from services.merge_request_provider import get_merge_request_provider
        writer = get_repo_writer(project)
        mrp = get_merge_request_provider(project)

        committed: list[str] = []
        skipped_binary: list[str] = []
        commit_msg = f"fix(incidencia #{ado_id if ado_id is not None else ticket_id}): resolución del Dev Resolutor + tests"
        for rel in changed:
            content = _read_text_or_none(repo_root, rel)   # None si binario/no-utf8/ilegible/>_MAX_TEXT_BYTES
            if content is None:
                skipped_binary.append(rel)
                continue
            writer.commit_file(rel, content, branch, commit_msg)   # crea la rama en el 1er call
            committed.append(rel)

        if not committed:
            incident_dev_pr.mark_intent(execution_id, status="skipped",
                                        error="todos los archivos eran binarios/ilegibles")
            _comment_issue_safe(ado_id, project, "🔧 Los cambios eran binarios; el PR automático (sólo texto) no aplica.")
            return
        if skipped_binary:
            logger.info("auto-PR exec=%s: %s archivos omitidos (binarios/ilegibles)", execution_id, len(skipped_binary))

        target = _default_branch_for(mrp, project)
        pr = mrp.create_merge_request(source_branch=branch, target_branch=target,
                                      title=title, description=description)
        pr_url = pr.get("web_url") or ""
        incident_dev_pr.mark_intent(execution_id, status="opened", pr_id=pr.get("id"),
                                    pr_url=pr_url, branch=branch, files_committed=committed, origin=origin)
        _comment_issue_safe(ado_id, project, f"🚀 PR abierto automáticamente con el fix y los tests: {pr_url}")
    except Exception as exc:  # noqa: BLE001 — K3/Plan 135: el fallo NUNCA queda mudo
        logger.warning("auto-PR incidencia exec=%s falló: %s", execution_id, exc, exc_info=True)
        try:
            incident_dev_pr.mark_intent(execution_id, status="error", error=str(exc))
            _comment_issue_safe(ado_id, project, f"⚠️ No se pudo abrir el PR automático: {exc}")
        except Exception:  # noqa: BLE001 — best-effort final
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ticket_ado_id_and_project(ticket_id):
    """(ado_id | None, stacky_project_name | None). Carga el Ticket por PK UNA vez.
    ProjectContext expone `stacky_project_name`/`workspace_root`, NO `.name`."""
    try:
        from db import session_scope
        from models import Ticket
        from services import project_context
        with session_scope() as s:
            t = s.get(Ticket, ticket_id)
            if t is None:
                return None, None
            ado_id = t.ado_id
            try:
                ctx = project_context.resolve_project_context(ticket=t)
            except Exception:  # noqa: BLE001
                ctx = None
            project = getattr(ctx, "stacky_project_name", None) if ctx else None
        return ado_id, project
    except Exception:  # noqa: BLE001 — best-effort
        return None, None


def _read_text_or_none(repo_root, rel_posix):
    """Contenido texto del archivo del working tree, o None si binario / no-utf8 /
    ilegible / excede _MAX_TEXT_BYTES (el proveedor MR sólo maneja texto)."""
    try:
        data = (Path(repo_root) / rel_posix).read_bytes()
    except OSError:
        return None
    if len(data) > _MAX_TEXT_BYTES:
        logger.info("auto-PR: %s excede %s bytes, se omite", rel_posix, _MAX_TEXT_BYTES)
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _default_branch_for(mrp, project):
    """Rama default del repo del tracker; reusa api/devops_production._default_branch
    (NO existe services/devops_production). Fallback DURO 'main'."""
    try:
        from api.devops_production import _default_branch
        return _default_branch(mrp, project) or "main"
    except Exception:  # noqa: BLE001
        return "main"


def _host_of(url):
    """Host de una URL git (http(s) o scp-like SSH git@host:org/repo), lower, o None."""
    if not url:
        return None
    u = str(url).strip()
    try:
        if "://" not in u and "@" in u:
            host = u.split("@", 1)[1].split(":", 1)[0]
            return host.lower() or None
        host = urlparse(u).hostname
        return host.lower() if host else None
    except Exception:  # noqa: BLE001
        return None


def _provider_host(project):
    """Host base del repo del tracker (sin red), o None si no se puede resolver."""
    try:
        from services.tracker_provider import get_tracker_provider
        prov = get_tracker_provider(project)
        client = getattr(prov, "_client", None)
        base = (
            getattr(client, "_base_proj", None)
            or getattr(prov, "base_url", None)
            or getattr(client, "base_url", None)
        )
        return _host_of(base) if base else None
    except Exception:  # noqa: BLE001
        return None


def _worktree_maps_to_wrong_repo(origin, project):
    """True SÓLO cuando el host del `origin` local difiere inequívocamente del host
    del repo del tracker. Ante cualquier duda → False (nunca degrada por debajo de v1)."""
    if not origin:
        return False
    oh = _host_of(origin)
    ph = _provider_host(project)
    return bool(oh and ph and oh != ph)


def _build_pr_body(ado_id, classify, deleted, origin):
    title = f"[Incidencia #{ado_id}] Fix automático del Dev Resolutor"
    code = classify.get("code") or []
    tests = classify.get("tests") or []
    lines = ["Resuelto por el **Dev Resolutor de Incidencias** (Stacky).", ""]
    lines.append("**Cambios de código**")
    lines += ([f"- `{p}`" for p in code] or ["- (ninguno)"])
    lines.append("")
    lines.append("**Tests incluidos**")
    lines += ([f"- `{p}`" for p in tests] or ["- (ninguno)"])
    if origin:
        lines += ["", f"**Origen del working tree:** `{origin}`"]
    if deleted:
        lines += ["", "**Archivos eliminados (no reflejados por la API REST, revisar manual)**"]
        lines += [f"- `{p}`" for p in deleted]
    return title, "\n".join(lines)


def _comment_issue_safe(ado_id, project, body):
    """Comenta en la Issue del tracker (ruta AGNÓSTICA de runtime, best-effort).
    Nunca transiciona ni cierra. PROHIBIDO usar la PK local o ado_client directo."""
    if ado_id is None:
        logger.info("auto-PR: sin ado_id, no se comenta la Issue: %s", body)
        return
    try:
        from services.tracker_provider import get_tracker_provider
        get_tracker_provider(project).post_comment(str(ado_id), body)
    except Exception:  # noqa: BLE001
        logger.info("auto-PR: no se pudo comentar la Issue ado_id=%s", ado_id, exc_info=True)


def register(register_post_hook):
    register_post_hook(maybe_open_pr_for_incident_dev)
