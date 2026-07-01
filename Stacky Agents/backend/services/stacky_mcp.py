"""stacky_mcp.py — Generación del --mcp-config para el Stacky MCP server (F2.1).

Escribe en el run_dir un `mcp-config.json` efímero que le dice a Claude Code CLI
cómo levantar el Stacky MCP server (stacky_mcp_server.py) como subproceso stdio.
El contexto del run (proyecto, ado_id, ticket_id, execution_id) viaja por env vars
STACKY_MCP_* declaradas en el config — el server las lee con _run_context().

Por proyecto, OFF por default (cli_feature_flags.mcp_enabled). Best-effort: si la
feature está apagada devuelve None y el runner spawnea sin --mcp-config.

Shape del config (formato de Claude Code CLI `--mcp-config`):
    {"mcpServers": {"stacky": {"command": "<python>", "args": [...], "env": {...}}}}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _build_internal_server_block(
    *,
    execution_id: int,
    port: int,
    project_name: str | None,
    ticket_id: int | None,
    ado_id: int | None,
    agent_type: str | None,
) -> dict:
    """Construye el dict de la entrada 'stacky' para mcpServers.
    Igual que el bloque inline anterior (stacky_mcp.py:42-70), extraído para
    permitir construir base_servers condicionalmente (Plan 80 F2)."""
    backend_dir = Path(__file__).resolve().parents[1]
    server_path = backend_dir / "services" / "stacky_mcp_server.py"
    env: dict[str, str] = {
        "STACKY_MCP_EXECUTION_ID": str(execution_id),
        "STACKY_MCP_PORT": str(port),
        # Heredar la conexión a la DB viva: sin esto el server arranca con otra DB.
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "PYTHONPATH": str(backend_dir),
    }
    if project_name:
        env["STACKY_MCP_PROJECT"] = project_name
    if ticket_id is not None:
        env["STACKY_MCP_TICKET_ID"] = str(ticket_id)
    if ado_id is not None:
        env["STACKY_MCP_ADO_ID"] = str(ado_id)
    if agent_type:
        env["STACKY_MCP_AGENT_TYPE"] = agent_type
    # No propagar valores vacíos (Claude pasa el env tal cual).
    env = {k: v for k, v in env.items() if v != ""}
    return {
        "command": sys.executable,
        "args": [str(server_path)],
        "env": env,
    }


def maybe_write_mcp_config(
    run_dir: Path,
    *,
    project_name: str | None,
    ticket_id: int | None,
    ado_id: int | None,
    execution_id: int,
    port: int,
    agent_type: str | None = None,
) -> Path | None:
    """Escribe el mcp-config.json si algún server (interno y/o externo Plan 80)
    está activo para el proyecto.

    Devuelve el Path del config, o None si todo está OFF. Nunca lanza por config
    inválido (deja que el runner capture errores de escritura).
    """
    from services import cli_feature_flags
    from config import config
    from services.codebase_memory_mcp_wiring import merge_external_server

    internal_on = cli_feature_flags.mcp_enabled(project_name)
    external_on = cli_feature_flags.codebase_memory_mcp_enabled(project_name)

    base_servers = (
        {
            "stacky": _build_internal_server_block(
                execution_id=execution_id,
                port=port,
                project_name=project_name,
                ticket_id=ticket_id,
                ado_id=ado_id,
                agent_type=agent_type,
            )
        }
        if internal_on
        else {}
    )
    servers = merge_external_server(
        base_servers,
        external_enabled=external_on,
        binary_path=config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH,
    )
    if not servers:
        return None  # nada que inyectar (byte-idéntico a hoy cuando todo OFF)

    config_obj = {"mcpServers": servers}
    config_path = run_dir / "mcp-config.json"
    config_path.write_text(
        json.dumps(config_obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return config_path
