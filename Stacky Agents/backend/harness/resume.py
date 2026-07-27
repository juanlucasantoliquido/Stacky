"""H7.1 — Decisión unificada de reanudación de sesión previa.

Extrae y parametriza la lógica de _resolve_resume de claude_code_cli_runner
para que ambos runtimes con supports_resume=True usen el mismo camino.

Contrato público:
    resolve(*, runtime, ticket_id, agent_type, project) -> (session_ref | None, delta_prefix | None)

Claves de metadata por runtime (NO se renombran — son contrato con UI y harness_health):
    claude_code_cli → "session_id"
    codex_cli       → "codex_session_id"

Best-effort: cualquier fallo interno → (None, None). Nunca lanza salvo runtime desconocido.
"""
from __future__ import annotations

import logging

from harness.capabilities import CAPABILITIES
from services.log_throttle import log_throttled  # Plan 257 F1-bis
from services.silent_failure_counter import level_int_for, note_swallowed  # Plan 255 F2 / 257 F1-bis

logger = logging.getLogger(__name__)

# Clave de metadata donde cada runtime persiste su session ref
_SESSION_KEY: dict[str, str] = {
    "claude_code_cli": "session_id",
    "codex_cli": "codex_session_id",
}

# Plan 255 F0 rollout §3 — cota dura al prefijo de delta inyectado al prompt.
_DELTA_PREFIX_MAX_CHARS = 20_000

# Flag master + allowlist CSV por runtime (leídos de config en call-time)
_RESUME_FLAG: dict[str, tuple[str, str]] = {
    "claude_code_cli": ("CLAUDE_CODE_CLI_RESUME_ENABLED", "CLAUDE_CODE_CLI_RESUME_PROJECTS"),
    "codex_cli": ("CODEX_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_PROJECTS"),
}


def _resume_flag_enabled(runtime: str, project: str | None) -> bool:
    """Lee el par de flags del runtime y decide si resume está activo para el proyecto."""
    from config import config
    from services.cli_feature_flags import project_enabled

    flag_enabled_key, flag_projects_key = _RESUME_FLAG[runtime]
    master = getattr(config, flag_enabled_key, False)
    projects_csv = getattr(config, flag_projects_key, "")
    return project_enabled(enabled=master, projects_csv=projects_csv, project_name=project)


def resolve(
    *,
    runtime: str,
    ticket_id: int | None,
    agent_type: str | None,
    project: str | None,
    current_blocks: list[dict] | None = None,
    execution_id: int | None = None,
) -> tuple[str | None, str | None]:
    """Decide si continuar la sesión previa para el runtime dado.

    Returns:
        (session_ref, delta_prefix) — ambos None si no aplica resume.

    Raises:
        ValueError: si `runtime` no está en CAPABILITIES.
    """
    if runtime not in CAPABILITIES:
        raise ValueError(
            f"harness.resume: runtime desconocido {runtime!r}. "
            f"Runtimes válidos: {sorted(CAPABILITIES)}"
        )

    cap = CAPABILITIES[runtime]
    if not cap.supports_resume:
        return None, None

    if not _resume_flag_enabled(runtime, project):
        return None, None

    if not ticket_id:
        return None, None

    session_key = _SESSION_KEY[runtime]
    runtime_name = runtime  # nombre en metadata["runtime"]

    try:
        from db import session_scope
        from models import AgentExecution

        prev_session_id: str | None = None
        prev_output: str | None = None
        prev_blocks: list[dict] = []

        with session_scope() as db_session:
            # Plan 255 F0(A) — el filtro condicional va ANTES de order_by/limit.
            # SQLAlchemy 2.0.36 prohíbe .filter() sobre un Query que ya tiene
            # LIMIT/OFFSET; con `execution_id` (el caso NORMAL del runner) el
            # query reventaba, lo tragaba el except final y el resume quedó
            # muerto desde el 2026-07-17 sin más síntoma que un WARNING.
            query = (
                db_session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == ticket_id)
                .filter(AgentExecution.agent_type == agent_type)
                .filter(AgentExecution.status == "completed")
            )
            if execution_id is not None:
                query = query.filter(AgentExecution.id != execution_id)
            rows = query.order_by(AgentExecution.id.desc()).limit(5).all()

            for row in rows:
                md = row.metadata_dict or {}
                sid = md.get(session_key)
                if md.get("runtime") == runtime_name and sid:
                    prev_session_id = sid
                    prev_output = row.output or ""
                    prev_blocks = list(row.input_context or [])
                    break

        if not prev_session_id:
            return None, None

        # Delta prompt solo cuando hay bloques de contexto anteriores y actuales
        delta_prefix: str | None = None
        if current_blocks is not None and prev_blocks:
            try:
                from services import delta_prompt

                diff = delta_prompt.compute_diff(prev_blocks, current_blocks)
                if diff.is_delta_eligible:
                    delta_prefix = delta_prompt.build_delta_prompt(prev_output or "", diff)
                    # Plan 255 F0 rollout §3 — cota dura al delta. Un delta
                    # gigante inyectado al prompt es PEOR que no reanudar: se
                    # descarta y se arranca con el prompt completo.
                    if delta_prefix and len(delta_prefix) > _DELTA_PREFIX_MAX_CHARS:
                        logger.info(
                            "resume %s: delta descartado por tamaño (%d chars > %d) — "
                            "se arranca con el prompt completo",
                            runtime, len(delta_prefix), _DELTA_PREFIX_MAX_CHARS,
                        )
                        delta_prefix = None
                    else:
                        logger.info(
                            "resume %s: sesión=%s… contexto cambió %.0f%%",
                            runtime,
                            prev_session_id[:12],
                            diff.change_ratio * 100,
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("resume: delta_prompt falló (continuando sin delta): %s", exc)

        return prev_session_id, delta_prefix

    except Exception as exc:  # noqa: BLE001 — resume nunca tumba el run
        # Plan 255 F2 sitio 5 — este `warning` tapó el bug 9 días. El nivel
        # ahora lo decide la clase de excepción, y el contador lo registra
        # aunque el nivel bajara. El TEXTO no cambia: es la huella de F5.
        note_swallowed("harness.resume.resolve", exc)
        # Plan 257 F1-bis — el NIVEL lo sigue decidiendo el plan 255
        # (`level_int_for` es la misma regla que usa `log_at_level`): no se
        # revierte para hacerlo throttleable. Lo unico que agrega el 257 es la
        # ventana de 300 s, que `log_throttled` respeta sea cual sea el nivel
        # — incluido ERROR, que el filtro de F1 exime a proposito. El TEXTO no
        # cambia: es la huella de la que depende el plan 255.
        log_throttled(
            "harness.resume_resolve_failed",
            logger,
            level_int_for(exc),
            "harness.resume.resolve falló (arranque en frío): %s",
            exc,
            min_interval_s=300.0,
        )
        return None, None
