"""R0.1 — Dispatcher de reaping de subprocesos.

Punto de entrada único para callers que conocen el execution_id pero no tienen
acceso directo al runner. Cada runner (claude_code_cli_runner, codex_cli_runner)
expone su propia funcion reap(execution_id) -> bool que opera bajo
_PROCESSES_LOCK del runner.

Reglas:
- Runtime desconocido → no-op (retorna False).
- Proceso ya muerto o no registrado → no-op idempotente (retorna False).
- NUNCA mata por nombre de proceso; solo por pid exacto registrado.
- Con el flag STACKY_RUNNER_REAP_ON_CLOSE_ENABLED=false → siempre False.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("stacky_agents.runner_reap")


def reap_execution(execution_id: int, runtime: str | None) -> bool:
    """Despacha reap al runner correcto segun runtime.

    Retorna True si el proceso fue terminado (existia y pudo ser killed).
    Retorna False en cualquier otro caso (no registrado, ya muerto, desconocido).
    """
    from config import config
    if not config.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED:
        return False

    if runtime == "claude_code_cli":
        try:
            from services import claude_code_cli_runner
            return claude_code_cli_runner.reap(execution_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("reap claude fallo (no critico): %s", exc, exc_info=True)
            return False
    elif runtime == "codex_cli":
        try:
            from services import codex_cli_runner
            return codex_cli_runner.reap(execution_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("reap codex fallo (no critico): %s", exc, exc_info=True)
            return False
    else:
        return False


def reap_by_db(execution_id: int) -> bool:
    """Resuelve el runtime desde la DB y despacha reap.

    Usado por callers sin acceso al runtime (ej: agent_completion_internal).
    """
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return False
            md = row.metadata_dict or {}
            runtime = md.get("runtime")
    except Exception as exc:  # noqa: BLE001
        logger.debug("reap_by_db: no se pudo leer runtime de DB: %s", exc)
        return False
    return reap_execution(execution_id, runtime=runtime)
