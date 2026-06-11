"""stacky_mcp_server.py — Stacky MCP server (stdio, F2.1).

Servidor MCP mínimo y SIN dependencias externas (no requiere el SDK `mcp`):
implementa el subconjunto del protocolo Model Context Protocol que Claude Code
necesita sobre JSON-RPC 2.0 por stdio (líneas newline-delimited):

  - initialize                → handshake + capabilities
  - notifications/initialized → ack (sin respuesta)
  - tools/list                → catálogo de tools
  - tools/call                → ejecución de una tool
  - ping                      → keepalive

Lo lanza el runtime claude_code_cli vía `--mcp-config` (ver stacky_mcp.py). Corre
como subproceso hijo del proceso `claude`, hereda el env del runner (DATABASE_URL,
sys.path) y habla con la DB/services de Stacky in-process. Es el ÚNICO canal por
el que el agente toca el estado de Stacky/ADO: las credenciales nunca salen de acá.

Contexto del run (ado_id, ticket_id, execution_id, project) llega por variables de
entorno STACKY_MCP_* que setea stacky_mcp.py al escribir el config.

Diseño defensivo: ninguna excepción de una tool tumba el server; se devuelve un
JSON-RPC error/result con `isError`. El loop solo termina con EOF en stdin.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "stacky"
SERVER_VERSION = "1.0.0"


# ── Definición de tools (schema declarado server-side) ─────────────────────────


def _tool_defs() -> list[dict]:
    return [
        {
            "name": "stacky_get_ticket",
            "description": (
                "Devuelve el ticket de Azure DevOps (título, descripción, tipo, estado) "
                "desde el estado local de Stacky. Usalo para pedir contexto fresco bajo "
                "demanda en vez de depender solo del prompt inicial."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ado_id": {"type": "integer", "description": "ADO id real del work item"}
                },
                "required": ["ado_id"],
            },
        },
        {
            "name": "stacky_search_memory",
            "description": (
                "Busca en la memoria colaborativa del proyecto (decisiones, convenciones, "
                "bugs conocidos). Complementa la inyección estática: inyectá poco, pedí más acá."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
        {
            "name": "stacky_search_similar",
            "description": (
                "Busca ejecuciones de agente pasadas similares (por embeddings TF-IDF) para "
                "reusar enfoques y evitar duplicar trabajo."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "stacky_submit_comment",
            "description": (
                "Entrega el comentario ADO final como HTML. Stacky lo valida server-side y lo "
                "publica en ADO (vos NO tocás ADO). Reemplaza escribir comment.html a mano: "
                "es imposible dejar un comentario vacío o mal ubicado."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ado_id": {"type": "integer", "description": "ADO id del ticket a comentar"},
                    "html": {"type": "string", "description": "comentario completo en HTML"},
                },
                "required": ["ado_id", "html"],
            },
        },
        {
            "name": "stacky_submit_task",
            "description": (
                "Entrega una Task hija para un Epic. Stacky valida el schema server-side "
                "(campos requeridos, status, epic_id real vs ordinal) y crea la Task en ADO. "
                "Reemplaza escribir pending-task.json a mano: imposible dejar un JSON inválido "
                "o un epic_id ordinal/mismatcheado."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "epic_ado_id": {"type": "integer", "description": "ADO id REAL del Epic padre"},
                    "payload": {
                        "type": "object",
                        "description": (
                            "campos del pending-task.json: rf_id, title, description_html, "
                            "plan_de_pruebas_path, parent_link_type (epic_id/generated_at/"
                            "generated_by/status se completan solos si faltan)"
                        ),
                    },
                },
                "required": ["epic_ado_id", "payload"],
            },
        },
        # ── H4 — Skills tool ─────────────────────────────────────────────────
        {
            "name": "stacky_get_skill",
            "description": (
                "Devuelve el cuerpo completo de una Stacky Skill por nombre exacto. "
                "Cuando el system prompt inyecta solo el índice de skills (lista con "
                "nombre: descripción), usá esta tool para obtener el procedimiento "
                "completo de la skill que sea relevante para la tarea actual."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nombre exacto de la skill (tal como aparece en el índice)",
                    }
                },
                "required": ["name"],
            },
        },
    ]


# ── Dispatch de tools/call ─────────────────────────────────────────────────────


def _run_context() -> dict[str, Any]:
    def _int(name: str) -> int | None:
        raw = os.getenv(name)
        try:
            return int(raw) if raw not in (None, "") else None
        except ValueError:
            return None

    return {
        "project": os.getenv("STACKY_MCP_PROJECT") or None,
        "ado_id": _int("STACKY_MCP_ADO_ID"),
        "ticket_id": _int("STACKY_MCP_TICKET_ID"),
        "execution_id": _int("STACKY_MCP_EXECUTION_ID"),
        "agent_type": os.getenv("STACKY_MCP_AGENT_TYPE") or None,
    }


def _call_tool(name: str, args: dict) -> dict:
    from services import stacky_mcp_tools as tools

    ctx = _run_context()
    if name == "stacky_get_ticket":
        return tools.get_ticket(ado_id=int(args["ado_id"]))
    if name == "stacky_search_memory":
        return tools.search_memory(
            project=ctx["project"],
            query=str(args.get("query") or ""),
            agent_type=ctx["agent_type"],
            k=int(args.get("k") or 8),
        )
    if name == "stacky_search_similar":
        return tools.search_similar(
            query=str(args.get("query") or ""),
            agent_type=ctx["agent_type"],
            k=int(args.get("k") or 5),
        )
    if name == "stacky_submit_comment":
        return tools.submit_comment(
            ado_id=int(args["ado_id"]),
            html=str(args.get("html") or ""),
            execution_id=ctx["execution_id"],
            ticket_id=ctx["ticket_id"],
        )
    if name == "stacky_submit_task":
        return tools.submit_task(
            epic_ado_id=int(args["epic_ado_id"]),
            payload=args.get("payload") or {},
            execution_id=ctx["execution_id"],
            ticket_id=ctx["ticket_id"],
        )
    if name == "stacky_get_skill":
        return tools.stacky_get_skill(name=str(args.get("name") or ""))
    raise ValueError(f"tool desconocida: {name}")


# ── Protocolo JSON-RPC / MCP ────────────────────────────────────────────────────


def handle_message(msg: dict) -> dict | None:
    """Procesa un mensaje JSON-RPC y devuelve la respuesta (o None si es notif)."""
    method = msg.get("method")
    msg_id = msg.get("id")

    # Notificaciones (sin id) → sin respuesta.
    if method == "notifications/initialized" or (method and msg_id is None):
        return None

    if method == "initialize":
        return _ok(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "ping":
        return _ok(msg_id, {})

    if method == "tools/list":
        return _ok(msg_id, {"tools": _tool_defs()})

    if method == "tools/call":
        params = msg.get("params") or {}
        tool_name = params.get("name") or ""
        args = params.get("arguments") or {}
        try:
            result = _call_tool(tool_name, args)
            is_error = isinstance(result, dict) and result.get("ok") is False
            return _ok(
                msg_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                    ],
                    "isError": bool(is_error),
                },
            )
        except Exception as exc:  # noqa: BLE001 — una tool nunca tumba el server
            return _ok(
                msg_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                    "isError": True,
                },
            )

    # Método no soportado.
    if msg_id is not None:
        return _err(msg_id, -32601, f"método no soportado: {method}")
    return None


def _ok(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve(stdin=None, stdout=None) -> None:
    """Loop principal: lee líneas JSON-RPC de stdin, responde por stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        response = handle_message(msg)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def _bootstrap_path() -> None:
    """Asegura que `backend/` esté en sys.path al correr como `-m`/script suelto."""
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend not in sys.path:
        sys.path.insert(0, backend)


if __name__ == "__main__":
    _bootstrap_path()
    serve()
