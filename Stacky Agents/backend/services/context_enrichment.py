"""Pipeline de enriquecimiento de contexto reutilizable.

Extrae la lógica que vivía inline en `agent_runner._run_in_background` para que
TODOS los runtimes (github_copilot, codex_cli, claude_code_cli) inyecten el mismo
contexto: estructura de épica, artifacts en disco, tickets similares y comentarios
/adjuntos de ADO.

Contrato: `enrich_blocks(...)` es una función pura respecto a los `raw_blocks`
(no muta la lista de entrada; devuelve una nueva) y nunca lanza: cada paso de
enriquecimiento es best-effort y se degrada con un warning en el `log`. Devuelve
`(enriched_blocks, ado_enrich_stats)` donde `ado_enrich_stats` es el dict de
contadores de ADO (o None si el ticket no tiene `ado_id`).

El comportamiento es idéntico al que tenía github_copilot inline: los mismos
gates por `agent_type`, las mismas env vars y el mismo orden de inyección. El
PII masking NO se hace acá (lo aplica cada runner sobre el resultado, porque
github_copilot necesita el `mask_map` para re-hidratar el output).
"""
from __future__ import annotations

import os
from typing import Any, Callable

from db import session_scope
from models import AgentExecution, Ticket

LogFn = Callable[..., None]


def _noop_log(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - trivial
    pass


def enrich_blocks(
    *,
    ticket_id: int | None,
    agent_type: str,
    raw_blocks: list[dict] | None,
    project_ctx: Any = None,
    log: LogFn | None = None,
) -> tuple[list[dict], dict | None]:
    """Aplica el pipeline de enriquecimiento y devuelve (blocks, ado_stats).

    Orden (idéntico al flujo histórico de github_copilot):
      1. ado-epic-structured   (solo functional + ticket Epic)
      2. filesystem-artifacts  (artifact_context)
      3. ado-similar-tickets   (functional/technical, requiere ado_id)
      4. ado-comments/adjuntos (ado_context.enrich, requiere ado_id)
    """
    log = log or _noop_log
    blocks: list[dict] = list(raw_blocks or [])

    # Capturar escalares del ticket en una sesión propia (evita DetachedInstanceError).
    ticket_ado_id: int | None = None
    ticket_project: str | None = None
    ticket_obj = None
    with session_scope() as _sess:
        ticket_obj = _sess.get(Ticket, ticket_id) if ticket_id else None
        if ticket_obj is not None:
            ticket_ado_id = ticket_obj.ado_id
            ticket_project = ticket_obj.project

    project_name = project_ctx.stacky_project_name if project_ctx else None

    # Plan 16: inyectar primero el client-profile (si está disponible y el
    # feature flag lo permite) para que todos los pasos siguientes puedan
    # leerlo si lo necesitan.
    blocks = _inject_client_profile_block(blocks, project_name, log)
    blocks = _inject_epic_structured(ticket_id, agent_type, blocks, log)
    blocks = _inject_artifact_context(ticket_id, blocks, log)
    blocks = _inject_similar_tickets(
        ticket_id, agent_type, ticket_ado_id, blocks, project_name, log
    )
    blocks, ado_stats = _inject_ado_context(
        ticket_id=ticket_id,
        agent_type=agent_type,
        ticket_ado_id=ticket_ado_id,
        blocks=blocks,
        project=ticket_project,
        project_ctx=project_ctx,
        project_name=project_name,
        ticket_obj=ticket_obj,
        log=log,
    )
    return blocks, ado_stats


# ---------------------------------------------------------------------------
# Pasos individuales (cada uno best-effort)
# ---------------------------------------------------------------------------

def build_client_profile_block(
    project_name: str | None, log: LogFn | None = None
) -> dict | None:
    """Construye el bloque `client-profile` del proyecto activo (o None).

    Es el seam ÚNICO de armado del bloque: lo usan tanto el pipeline batch
    (`_inject_client_profile_block`, vía `enrich_blocks` para los runtimes
    github_copilot/codex_cli/claude_code_cli) como el flujo interactivo
    (`api/agents.open_chat`, que abre GitHub Copilot Chat y antes NO pasaba por
    `enrich_blocks` → el agente cliente-agnóstico arrancaba sin perfil). Tener un
    solo armador garantiza que el Developer reciba EXACTAMENTE el mismo perfil en
    ambos caminos.

    Garantía (plan "client profile siempre presente"): se devuelve un bloque
    SIEMPRE que haya proyecto — si el operador configuró un perfil se usa tal
    cual; si no, se cae al template default del tracker (marcado como "sin
    configurar") para que ningún agente arranque a ciegas.

    Feature flag: `STACKY_INJECT_CLIENT_PROFILE` (default `true`). Si está OFF
    devuelve None aunque haya perfil.

    Best-effort: cualquier excepción degrada en warning y devuelve None.
    """
    log = log or _noop_log
    if os.getenv("STACKY_INJECT_CLIENT_PROFILE", "true").lower() in {"0", "false", "off"}:
        return None
    if not project_name:
        return None

    try:
        from services.client_profile import (
            get_project_tracker_type,
            load_client_profile,
            merge_with_defaults,
        )

        persisted = load_client_profile(project_name)
        # "Configurado" = el operador guardó algo con contenido real. Un perfil
        # vacío (`{"schema_version": 1}`, p. ej. sembrado por un build viejo que
        # no traía templates) cuenta como NO configurado: igual lo completamos
        # con el layout estándar y lo marcamos como defaults.
        has_real_profile = isinstance(persisted, dict) and bool(
            set(persisted.keys()) - {"schema_version"}
        )
        tracker_type = get_project_tracker_type(project_name)
        # Completar SIEMPRE con el template default del tracker para que el
        # agente reciba rutas/estados/BD aunque el perfil guardado esté parcial
        # o vacío (plan 17 §3.5). `merge_with_defaults` incluye `database` —a
        # diferencia de `complete_client_profile`, usado por el editor— porque el
        # agente necesita type/dml_policy/naming (no hay secretos: el server va
        # vacío en el default y la credencial vive cifrada fuera del perfil).
        profile = merge_with_defaults(
            persisted if isinstance(persisted, dict) else {}, tracker_type
        )
        using_defaults = not has_real_profile
        if not profile:
            # Sin template default disponible: no hay nada útil que inyectar.
            return None

        # Render legible — YAML-ish para humanos, pero el contenido es plain text
        # (el LLM lo parsea como texto). Usamos json.dumps con indent porque es
        # determinístico y libre de dependencias adicionales.
        import json as _json

        terminology = profile.get("terminology") or {}
        client_label = (terminology.get("client_label") or "").strip()
        product = (terminology.get("product_name") or "").strip()
        title_suffix = ""
        if client_label or product:
            title_suffix = " — " + " · ".join([s for s in (client_label, product) if s])

        marker = " (defaults sin configurar)" if using_defaults else ""
        content = _json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True)
        if using_defaults:
            content = (
                "// NOTA: perfil no configurado por el operador. Estos son los "
                "defaults del tracker; confirmá rutas/estados antes de usarlos.\n"
                + content
            )
        block = {
            "kind": "text",
            "id": "client-profile",
            "title": f"Perfil del cliente: {project_name}{title_suffix}{marker}",
            "content": content,
        }
        log(
            "info",
            f"client-profile inyectado para proyecto={project_name} "
            f"(schema_version={profile.get('schema_version')}, "
            f"using_defaults={using_defaults})",
        )
        return block
    except Exception as exc:  # noqa: BLE001
        log("warn", f"client-profile no se pudo inyectar (continuando): {exc}")
        return None


def _inject_client_profile_block(
    blocks: list[dict], project_name: str | None, log: LogFn
) -> list[dict]:
    """Inyecta un bloque `client-profile` en `blocks`. Plan 16, Fase 2.

    Delega el armado del bloque en `build_client_profile_block` (seam único) y
    sólo agrega la deduplicación contra un bloque ya presente en la lista.
    """
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "client-profile" in existing_ids:
        log("info", "client-profile ya presente, omitiendo inyección")
        return blocks

    block = build_client_profile_block(project_name, log)
    if block is None:
        return blocks
    return list(blocks) + [block]


def _inject_epic_structured(
    ticket_id: int | None, agent_type: str, blocks: list[dict], log: LogFn
) -> list[dict]:
    """Inyecta ado-epic-structured cuando el agente es functional y el ticket es Epic."""
    with session_scope() as _epic_sess:
        _epic_ticket = _epic_sess.get(Ticket, ticket_id) if ticket_id else None
        _is_epic = (
            _epic_ticket is not None
            and agent_type == "functional"
            and (_epic_ticket.work_item_type or "").strip().lower() == "epic"
        )
        if not _is_epic:
            return blocks
        _existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
        if "ado-epic-structured" in _existing_ids:
            log("info", "ado-epic-structured ya presente, omitiendo inyección")
            return blocks
        _epic_block: dict = {
            "kind": "text",
            "id": "ado-epic-structured",
            "title": f"Epic ADO-{_epic_ticket.ado_id}: {_epic_ticket.title}",
            "content": (
                f"epic_id: {_epic_ticket.ado_id}\n"
                f"epic_title: {_epic_ticket.title}\n"
                f"epic_description:\n{_epic_ticket.description or ''}"
            ),
        }
        log("info", f"ado-epic-structured inyectado para Epic ADO-{_epic_ticket.ado_id}")
        return list(blocks) + [_epic_block]


def _inject_artifact_context(
    ticket_id: int | None, blocks: list[dict], log: LogFn
) -> list[dict]:
    """Inyecta filesystem-artifacts-status (comment.html / pending-task.json existentes)."""
    try:
        from services import artifact_context

        with session_scope() as _art_sess:
            _art_ticket = _art_sess.get(Ticket, ticket_id) if ticket_id else None
            _art_ado_id = _art_ticket.ado_id if _art_ticket else None
            _art_type = _art_ticket.work_item_type if _art_ticket else None
            _exec_rows = (
                _art_sess.query(AgentExecution.id)
                .filter(AgentExecution.ticket_id == ticket_id)
                .order_by(AgentExecution.id.desc())
                .limit(10)
                .all()
                if ticket_id
                else []
            )
            _exec_ids = [r[0] for r in _exec_rows]
        blocks, _art_info = artifact_context.inject_into_blocks(
            blocks,
            ado_id=_art_ado_id,
            work_item_type=_art_type,
            execution_ids=_exec_ids,
        )
        if _art_info and _art_info.get("injected"):
            log(
                "info",
                "filesystem-artifacts-status inyectado "
                f"(pending={_art_info.get('pending_count')}, "
                f"consumed={_art_info.get('consumed_count')}, "
                f"comment_html={_art_info.get('has_comment_html')})",
            )
    except Exception as _exc_art:  # noqa: BLE001
        log("warn", f"artifact_context falló (continuando sin bloque): {_exc_art}")
    return blocks


def _inject_similar_tickets(
    ticket_id: int | None,
    agent_type: str,
    ticket_ado_id: int | None,
    blocks: list[dict],
    project_name: str | None,
    log: LogFn,
) -> list[dict]:
    """Inyecta ado-similar-tickets para que el agente no proponga duplicados."""
    if (
        os.getenv("STACKY_SIMILAR_TICKETS_ENABLED", "true").lower() == "false"
        or agent_type not in {"functional", "technical"}
        or ticket_ado_id is None
    ):
        return blocks
    try:
        from services import similar_tickets

        with session_scope() as _sim_sess:
            _sim_ticket = _sim_sess.get(Ticket, ticket_id) if ticket_id else None
            _sim_title = _sim_ticket.title if _sim_ticket else ""
            _sim_project = _sim_ticket.project if _sim_ticket else "Strategist_Pacifico"
        blocks, _sim_info = similar_tickets.inject_into_blocks(
            blocks,
            current_ado_id=ticket_ado_id,
            current_title=_sim_title,
            project=_sim_project or "Strategist_Pacifico",
            project_name=project_name,
        )
        if _sim_info and _sim_info.get("injected"):
            log("info", f"ado-similar-tickets inyectado (count={_sim_info.get('count')})")
    except Exception as _exc_sim:  # noqa: BLE001
        log("warn", f"similar_tickets falló (continuando sin bloque): {_exc_sim}")
    return blocks


def build_ticket_context_text(
    *,
    ado_id: int | None,
    title: str | None,
    description: str | None,
    work_item_type: str | None,
    blocks: list[dict] | None,
) -> str:
    """Arma el texto legible de "## Ticket y contexto" para los runtimes CLI.

    Incluye el encabezado del ticket (ADO-id, tipo, título, descripción) y un
    render de los context_blocks enriquecidos (épica, comentarios ADO, tickets
    similares, "Mensaje adicional" del modal, nota del operador, etc.).

    Reemplaza el `ticket_message = ticket.title` que dejaba al agente arrancar a
    ciegas: ahora recibe lo mismo que recibiría el flujo github_copilot.
    """
    parts: list[str] = []

    header = f"ADO-{ado_id}" if ado_id is not None else "(ticket sin ADO id)"
    if work_item_type:
        header += f" · {work_item_type}"
    parts.append(f"**Ticket:** {header}")
    if title:
        parts.append(f"**Título:** {title}")
    if description and description.strip():
        parts.append(f"**Descripción:**\n{description.strip()}")

    rendered_blocks = _render_blocks(blocks)
    if rendered_blocks:
        parts.append("### Contexto adicional\n\n" + rendered_blocks)

    return "\n\n".join(parts).strip()


def _render_blocks(blocks: list[dict] | None) -> str:
    """Render legible de los context_blocks (mismo criterio de selección que el
    context_text de github_copilot, pero con encabezados por bloque)."""
    sections: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        title = (b.get("title") or "").strip()
        lines: list[str] = []
        content = b.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
        for it in b.get("items") or []:
            if isinstance(it, dict) and it.get("selected"):
                label = (it.get("label") or "").strip()
                if label:
                    lines.append(f"- {label}")
        body = "\n".join(lines).strip()
        if not title and not body:
            continue
        if title and body:
            sections.append(f"#### {title}\n{body}")
        elif title:
            sections.append(f"#### {title}")
        else:
            sections.append(body)
    return "\n\n".join(sections).strip()


def _inject_ado_context(
    *,
    ticket_id: int | None,
    agent_type: str,
    ticket_ado_id: int | None,
    blocks: list[dict],
    project: str | None,
    project_ctx: Any,
    project_name: str | None,
    ticket_obj: Any,
    log: LogFn,
) -> tuple[list[dict], dict | None]:
    """Inyecta comentarios/adjuntos de ADO. Devuelve (blocks, stats)."""
    if ticket_ado_id is None:
        return blocks, None
    try:
        from services import ado_context

        blocks, stats = ado_context.enrich(
            ticket_id=ticket_id,
            agent_type=agent_type,
            existing_blocks=blocks or [],
            ado_id=ticket_ado_id,
            project_name=project_name,
            tracker_project=project_ctx.tracker_project if project_ctx else project,
            ticket=ticket_obj,
            log=log,
            return_stats=True,
        )
        return blocks, stats
    except Exception as _exc_ado:  # noqa: BLE001
        log("warn", f"ado_context enrich falló (continuando sin enrichment): {_exc_ado}")
        return blocks, {"error": str(_exc_ado)}
