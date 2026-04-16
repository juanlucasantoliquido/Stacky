"""
stacky_mcp_server.py — X-10: Stacky como MCP Server (Model Context Protocol).

Expone todo el conocimiento de Stacky como un servidor MCP estandar.
Cualquier cliente compatible (Claude Desktop, Cursor, VS Code Copilot)
puede consultar el pipeline, el historial de tickets y la knowledge base
directamente desde su interfaz de chat.

Herramientas MCP expuestas:
  - get_ticket_status      → estado actual de un ticket en el pipeline
  - get_ticket_analysis    → artefactos PM generados para un ticket
  - search_codebase        → busqueda semantica en el indice vectorial (G-02)
  - get_agent_memory       → memoria persistente de agentes (G-06)
  - get_pipeline_status    → resumen del pipeline completo
  - get_oracle_schema      → schema Oracle de tablas relevantes (G-03)
  - get_blast_radius       → mapa de impacto de archivos (G-05)
  - list_similar_tickets   → tickets similares al query (E-01)
  - get_tech_debt          → indice de deuda tecnica (X-07)

Uso:
    python stacky_mcp_server.py --project RIPLEY
    python stacky_mcp_server.py --project RIPLEY --port 3001
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mantis.mcp")

BASE_DIR = Path(__file__).parent


def _get_tool_definitions() -> list:
    """Retorna las definiciones de herramientas MCP en formato JSON Schema."""
    return [
        {
            "name": "get_ticket_status",
            "description": (
                "Obtiene el estado actual de un ticket Mantis en el pipeline Stacky. "
                "Incluye etapa, tiempo transcurrido, timeout y ultimo evento."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "ID del ticket, ej: '0027698'"},
                    "project":   {"type": "string", "description": "Nombre del proyecto, ej: 'RIPLEY'"},
                },
                "required": ["ticket_id"],
            },
        },
        {
            "name": "get_ticket_analysis",
            "description": (
                "Retorna los artefactos del analisis PM de un ticket: "
                "ANALISIS_TECNICO.md, ARQUITECTURA_SOLUCION.md, TAREAS_DESARROLLO.md."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticket_id":  {"type": "string"},
                    "artifact":   {
                        "type": "string",
                        "enum": ["analisis", "arquitectura", "tareas", "incidente", "all"],
                        "description": "Que artefacto leer. 'all' retorna todos.",
                    },
                    "project":    {"type": "string"},
                },
                "required": ["ticket_id"],
            },
        },
        {
            "name": "get_pipeline_status",
            "description": (
                "Retorna el estado completo del pipeline: tickets activos, "
                "en cola, completados hoy y metricas basicas."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                },
            },
        },
        {
            "name": "list_similar_tickets",
            "description": (
                "Busca en el historial de tickets resueltos los mas similares "
                "al query provisto. Util para encontrar soluciones previas."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query":   {"type": "string", "description": "Descripcion del problema o keywords"},
                    "project": {"type": "string"},
                    "top_k":   {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_tech_debt",
            "description": (
                "Retorna el indice de deuda tecnica del proyecto: modulos con mas "
                "tickets, candidatos a refactorizacion y patrones sistemicos."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "format":  {
                        "type": "string",
                        "enum": ["json", "markdown"],
                        "default": "markdown",
                    },
                },
            },
        },
        {
            "name": "get_blast_radius",
            "description": (
                "Analiza el impacto potencial de modificar uno o mas archivos: "
                "retorna dependientes directos y nivel de riesgo."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "files":   {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de archivos a analizar",
                    },
                    "project": {"type": "string"},
                },
                "required": ["files"],
            },
        },
        {
            "name": "get_agent_memory",
            "description": (
                "Consulta la memoria persistente de los agentes Stacky: "
                "patrones conocidos, modulos de alto riesgo y lecciones aprendidas."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent":   {
                        "type": "string",
                        "enum": ["pm", "dev", "qa", "all"],
                        "default": "all",
                    },
                    "project": {"type": "string"},
                    "query":   {
                        "type": "string",
                        "description": "Filtrar memoria por keyword (opcional)",
                    },
                },
            },
        },
    ]


# ── Implementacion de cada herramienta ───────────────────────────────────────

def _handle_get_ticket_status(args: dict) -> dict:
    ticket_id = args.get("ticket_id", "").lstrip("0") or args.get("ticket_id", "")
    project   = args.get("project", _detect_default_project())

    state_path = BASE_DIR / "pipeline" / "state.json"
    if not state_path.exists():
        return {"error": "state.json no encontrado"}

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}

    # Buscar por ID exacto o por sufijo
    matched_key = None
    for key in state:
        if key.lstrip("0") == ticket_id or key == ticket_id or ticket_id in key:
            matched_key = key
            break

    if not matched_key:
        return {"found": False, "ticket_id": ticket_id, "message": "Ticket no encontrado en el pipeline activo"}

    info  = state[matched_key]
    stage = info.get("stage", "desconocido")
    started = info.get("stage_started_at")
    elapsed = None
    if started:
        try:
            dt = datetime.fromisoformat(started)
            elapsed = round((datetime.now() - dt).total_seconds() / 60, 1)
        except Exception:
            pass

    return {
        "found":        True,
        "ticket_id":    matched_key,
        "stage":        stage,
        "project":      project,
        "elapsed_min":  elapsed,
        "timeout_min":  info.get("timeout_minutes"),
        "last_event":   info.get("last_event", ""),
    }


def _handle_get_ticket_analysis(args: dict) -> dict:
    ticket_id = args.get("ticket_id", "")
    artifact  = args.get("artifact", "all")
    project   = args.get("project", _detect_default_project())

    tickets_base = BASE_DIR / "projects" / project / "tickets"
    folder = _find_ticket_folder(tickets_base, ticket_id)

    if not folder:
        return {"error": f"Carpeta del ticket {ticket_id} no encontrada"}

    artifact_map = {
        "analisis":     "ANALISIS_TECNICO.md",
        "arquitectura": "ARQUITECTURA_SOLUCION.md",
        "tareas":       "TAREAS_DESARROLLO.md",
        "incidente":    "INCIDENTE.md",
    }

    result = {"ticket_id": ticket_id, "folder": str(folder)}

    if artifact == "all":
        for key, fname in artifact_map.items():
            fpath = folder / fname
            result[key] = fpath.read_text(encoding="utf-8", errors="ignore") if fpath.exists() else None
    else:
        fname = artifact_map.get(artifact)
        if fname:
            fpath = folder / fname
            result["content"] = fpath.read_text(encoding="utf-8", errors="ignore") if fpath.exists() else None

    return result


def _handle_get_pipeline_status(args: dict) -> dict:
    project   = args.get("project", _detect_default_project())
    state_path = BASE_DIR / "pipeline" / "state.json"

    if not state_path.exists():
        return {"active_tickets": [], "summary": "Pipeline no iniciado"}

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}

    stage_counts: dict[str, int] = {}
    active = []
    for ticket_id, info in state.items():
        stage = info.get("stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        if "completado" not in stage and "error" not in stage:
            active.append({"ticket_id": ticket_id, "stage": stage})

    return {
        "project":      project,
        "total_active": len(active),
        "active":       active[:10],
        "stage_counts": stage_counts,
        "checked_at":   datetime.now().isoformat(),
    }


def _handle_list_similar_tickets(args: dict) -> dict:
    query   = args.get("query", "")
    project = args.get("project", _detect_default_project())
    top_k   = int(args.get("top_k", 5))

    try:
        from knowledge_base import KnowledgeBase
        tickets_base = str(BASE_DIR / "projects" / project / "tickets")
        kb = KnowledgeBase(tickets_base, project)
        results = kb.search(query, k=top_k)
        return {"query": query, "results": results, "count": len(results)}
    except Exception as exc:
        return {"error": str(exc), "query": query}


def _handle_get_tech_debt(args: dict) -> dict:
    project = args.get("project", _detect_default_project())
    fmt     = args.get("format", "markdown")

    try:
        from tech_debt_analyzer import TechDebtAnalyzer
        tda = TechDebtAnalyzer(project)
        if fmt == "json":
            return tda.get_heatmap_data()
        else:
            return {"markdown": tda.get_debt_report()}
    except Exception as exc:
        return {"error": str(exc)}


def _handle_get_blast_radius(args: dict) -> dict:
    files   = args.get("files", [])
    project = args.get("project", _detect_default_project())

    try:
        from blast_radius_analyzer import BlastRadiusAnalyzer
        config_path = BASE_DIR / "projects" / project / "config.json"
        config      = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        workspace   = config.get("workspace_root", str(BASE_DIR.parent.parent))
        bra  = BlastRadiusAnalyzer()
        report = bra.analyze(files, workspace)
        return {"files": files, "report": report.__dict__ if hasattr(report, "__dict__") else str(report)}
    except Exception as exc:
        return {"error": str(exc), "files": files}


def _handle_get_agent_memory(args: dict) -> dict:
    agent   = args.get("agent", "all")
    project = args.get("project", _detect_default_project())
    query   = args.get("query", "").lower()

    memory_dir = BASE_DIR / "knowledge" / project / "agent_memory"
    if not memory_dir.exists():
        return {"error": "Directorio de memoria no encontrado", "project": project}

    files_to_read = []
    if agent == "all":
        files_to_read = list(memory_dir.glob("*.json"))
    else:
        fname = memory_dir / f"{agent}_memory.json"
        if fname.exists():
            files_to_read = [fname]

    result = {}
    for fpath in files_to_read:
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if query:
                # Filtrar por query
                filtered = {}
                for k, v in data.items():
                    v_str = json.dumps(v, ensure_ascii=False).lower()
                    if query in v_str:
                        filtered[k] = v
                data = filtered
            result[fpath.stem] = data
        except Exception:
            pass

    return result


# ── Dispatcher de herramientas ────────────────────────────────────────────────

_TOOL_HANDLERS = {
    "get_ticket_status":   _handle_get_ticket_status,
    "get_ticket_analysis": _handle_get_ticket_analysis,
    "get_pipeline_status": _handle_get_pipeline_status,
    "list_similar_tickets": _handle_list_similar_tickets,
    "get_tech_debt":       _handle_get_tech_debt,
    "get_blast_radius":    _handle_get_blast_radius,
    "get_agent_memory":    _handle_get_agent_memory,
}


def dispatch_tool(tool_name: str, tool_args: dict) -> Any:
    handler = _TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Herramienta no encontrada: {tool_name}"}
    try:
        return handler(tool_args)
    except Exception as exc:
        logger.exception("[X-10] Error en herramienta %s: %s", tool_name, exc)
        return {"error": str(exc)}


# ── Servidor MCP (JSON-RPC sobre stdio) ──────────────────────────────────────

def run_mcp_server():
    """
    Servidor MCP minimalista sobre stdio (JSON-RPC 2.0).
    Compatible con Claude Desktop, Cursor y cualquier cliente MCP estandar.
    """
    import sys

    # Configurar logging a stderr para no interferir con el protocolo stdio
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(levelname)s [mcp] %(message)s",
    )

    def write_response(response: dict):
        line = json.dumps(response, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def read_request() -> Optional[dict]:
        line = sys.stdin.readline()
        if not line:
            return None
        try:
            return json.loads(line.strip())
        except Exception:
            return None

    # Enviar capabilities al iniciar
    write_response({
        "jsonrpc": "2.0",
        "method":  "notifications/initialized",
        "params":  {},
    })

    while True:
        req = read_request()
        if req is None:
            break

        req_id  = req.get("id")
        method  = req.get("method", "")
        params  = req.get("params", {})

        try:
            if method == "initialize":
                write_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name":    "stacky-mcp",
                            "version": "1.0.0",
                        },
                    },
                })

            elif method == "tools/list":
                write_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": _get_tool_definitions()},
                })

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                result    = dispatch_tool(tool_name, tool_args)
                content   = json.dumps(result, ensure_ascii=False, indent=2)
                write_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": content}],
                    },
                })

            else:
                write_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })

        except Exception as exc:
            write_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_default_project() -> str:
    """Infiere el proyecto por defecto desde config.json raiz."""
    cfg = BASE_DIR / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return data.get("default_project", "RIPLEY")
        except Exception:
            pass
    return "RIPLEY"


def _find_ticket_folder(tickets_base: Path, ticket_id: str) -> Optional[Path]:
    padded = ticket_id.zfill(7)
    if not tickets_base.exists():
        return None
    for estado_dir in tickets_base.iterdir():
        if not estado_dir.is_dir():
            continue
        candidate = estado_dir / padded
        if candidate.exists():
            return candidate
    return None


from typing import Optional


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stacky MCP Server — expone el pipeline como herramientas MCP"
    )
    parser.add_argument("--project", default="RIPLEY", help="Proyecto por defecto")
    parser.add_argument(
        "--list-tools", action="store_true", help="Lista las herramientas disponibles y sale"
    )
    args = parser.parse_args()

    if args.list_tools:
        for tool in _get_tool_definitions():
            print(f"  {tool['name']:30s} {tool['description'][:70]}")
        sys.exit(0)

    run_mcp_server()
