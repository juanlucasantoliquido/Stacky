"""Plan 80 — Helpers puros para inyectar el server MCP externo codebase-memory-mcp.
PUROS: no tocan disco, no abren red, no spawnean binarios. Solo arman dicts/strings.
Contrato de clave (Plan 76, C4/C10): el server externo usa la clave 'codebase-memory-mcp',
NUNCA 'stacky' (esa es del MCP interno).
"""
from __future__ import annotations

EXTERNAL_MCP_KEY = "codebase-memory-mcp"  # contrato Plan 76 — NO cambiar a "stacky"


def build_external_server_entry(binary_path: str) -> dict | None:
    """Devuelve la entrada de mcpServers para el server externo, o None si no procede.
    None si binary_path está vacío (degradación segura: no se inyecta nada).
    None si binary_path contiene '..' (path traversal — seguridad; C-RES-1 adición v3).
    PURA: no verifica que el archivo exista (eso lo decide el operador); solo arma el dict."""
    if not binary_path or not binary_path.strip():
        return None
    # Seguridad (C-RES-1 [ADICIÓN v3]): rechazar paths con traversal.
    # El operador escribe binary_path desde la UI; si contiene ".." podría apuntar fuera de la ruta esperada.
    import pathlib
    try:
        parts = pathlib.PurePath(binary_path.strip()).parts
    except Exception:
        return None
    if ".." in parts:
        return None
    return {"command": binary_path.strip(), "args": []}


def merge_external_server(
    base_servers: dict, *, external_enabled: bool, binary_path: str
) -> dict:
    """Devuelve un NUEVO dict de servers, añadiendo 'codebase-memory-mcp' si corresponde.
    - external_enabled False -> devuelve base_servers SIN cambios (byte-idéntico).
    - external_enabled True pero binary_path vacío -> base_servers SIN cambios (degradación segura).
    - external_enabled True + binary_path -> base_servers + {'codebase-memory-mcp': {...}}.
    NUNCA pisa la clave 'stacky'. NUNCA muta base_servers (copia)."""
    if not external_enabled:
        return dict(base_servers)
    entry = build_external_server_entry(binary_path)
    if entry is None:
        return dict(base_servers)
    merged = dict(base_servers)
    merged[EXTERNAL_MCP_KEY] = entry
    return merged


def estimate_query_savings(chars_baseline: int, chars_mcp_response: int) -> dict:
    """Plan 80 — Estima ahorro de tokens de una query estructural (heurística ~4 chars/token).
    PURA. Devuelve {tokens_baseline, tokens_mcp, delta, delta_pct}.
    delta_pct = 0.0 si chars_baseline == 0 (evita div/0).
    delta y delta_pct pueden ser negativos (si el MCP devuelve más chars que el baseline)."""
    tb = max(0, chars_baseline) // 4
    tm = max(0, chars_mcp_response) // 4
    delta = tb - tm
    pct = (delta / tb) if tb > 0 else 0.0
    return {"tokens_baseline": tb, "tokens_mcp": tm, "delta": delta, "delta_pct": round(pct, 4)}


def aggregate_savings() -> dict:
    """Plan 80 — Retorna métricas agregadas de ahorro estimado.
    Hasta que el operador pobla la PoC (queries.md del 76), retorna samples=0 y delta_pct=null.
    PURA. No abre red ni disco."""
    return {
        "samples": 0,
        "delta_pct": None,
        "note": "Poblar con PoC de queries.md (Plan 76 docs/_evals/codebase-memory-mcp/).",
    }
