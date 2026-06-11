"""H1.2 — Capacidades declaradas por runtime.

CAPABILITIES es el contrato máquina-legible de qué puede/hace cada runtime.
Úsalo en lugar de isinstance/string-matching dispersos.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeCapabilities:
    runtime: str
    writes_artifacts: bool       # genera archivos de output que Stacky valida
    supports_stdin_feedback: bool  # acepta mensajes correctivos vía stdin
    supports_resume: bool        # soporta reanudación de sesión
    supports_mcp: bool           # soporta configuración MCP efímera
    has_stream_telemetry: bool   # emite telemetría nativa en el stream


CAPABILITIES: dict[str, RuntimeCapabilities] = {
    "claude_code_cli": RuntimeCapabilities(
        runtime="claude_code_cli",
        writes_artifacts=True,
        supports_stdin_feedback=True,
        supports_resume=True,
        supports_mcp=True,
        has_stream_telemetry=True,
    ),
    "codex_cli": RuntimeCapabilities(
        runtime="codex_cli",
        writes_artifacts=True,
        supports_stdin_feedback=False,   # codex cierra stdin; usa exec resume
        supports_resume=True,            # via codex exec resume <session_id>
        supports_mcp=False,              # binario no disponible / sin soporte verificado
        has_stream_telemetry=True,       # emite JSONL con campos de uso
    ),
    "github_copilot": RuntimeCapabilities(
        runtime="github_copilot",
        writes_artifacts=True,
        supports_stdin_feedback=False,
        supports_resume=False,
        supports_mcp=False,
        has_stream_telemetry=False,
    ),
}
