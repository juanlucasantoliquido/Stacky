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
    """Escribe el mcp-config.json si la feature está activa para el proyecto.

    Devuelve el Path del config, o None si está OFF. Nunca lanza por config
    inválido (deja que el runner capture errores de escritura).
    """
    from services import cli_feature_flags

    if not cli_feature_flags.mcp_enabled(project_name):
        return None

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

    config_obj = {
        "mcpServers": {
            "stacky": {
                "command": sys.executable,
                "args": [str(server_path)],
                "env": env,
            }
        }
    }
    config_path = run_dir / "mcp-config.json"
    config_path.write_text(
        json.dumps(config_obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return config_path
