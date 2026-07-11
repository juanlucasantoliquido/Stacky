"""Plan 76 — Tests para la integración opcional codebase-memory-mcp (TDD).

Casos:
1.  config.STACKY_CODEBASE_MEMORY_MCP_ENABLED = False por default.
2.  mcp_installation_status() con flag OFF → {"enabled": False, ...}
3.  mcp_installation_status() con flag ON → {"enabled": True, ...}
4.  build_installation_guide("claude_code") → markdown con clave de server "codebase-memory-mcp" (no "stacky")
5.  build_installation_guide("codex") → markdown no vacío
6.  build_installation_guide("copilot_pro") → markdown no vacío
7.  build_installation_guide con runtime inválido → ValueError
8.  Pureza (sin red): mcp_installation_status() y build_installation_guide no abren sockets
9.  GET /api/codebase-memory-mcp/status con flag OFF → 200 con enabled=false + guides
10. FLAG_REGISTRY contiene FlagSpec con env_only=False y key en _CATEGORY_KEYS["avanzado"]
"""
from __future__ import annotations

import socket
import unittest.mock as mock

import pytest


# ---------------------------------------------------------------------------
# Caso 1 — Default del atributo en config
# ---------------------------------------------------------------------------
def test_flag_default_is_false():
    import importlib
    import sys
    # Asegurar que config se reimporta sin variable de entorno seteada
    env_backup = {}
    import os
    if "STACKY_CODEBASE_MEMORY_MCP_ENABLED" in os.environ:
        env_backup["STACKY_CODEBASE_MEMORY_MCP_ENABLED"] = os.environ.pop(
            "STACKY_CODEBASE_MEMORY_MCP_ENABLED"
        )
    try:
        # Forzar reimport del módulo config
        if "config" in sys.modules:
            del sys.modules["config"]
        from config import Config
        # Activación operador 2026-07-10: default ON sin env var.
        assert Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED is True, (
            "El atributo STACKY_CODEBASE_MEMORY_MCP_ENABLED debe ser True por default (operador 2026-07-10)"
        )
    finally:
        os.environ.update(env_backup)
        # Restaurar módulo
        if "config" in sys.modules:
            del sys.modules["config"]


# ---------------------------------------------------------------------------
# Caso 2 — mcp_installation_status() con flag OFF
# ---------------------------------------------------------------------------
def test_mcp_installation_status_flag_off(monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.Config, "STACKY_CODEBASE_MEMORY_MCP_ENABLED", False)
    from services.codebase_memory_mcp_status import mcp_installation_status
    result = mcp_installation_status()
    assert result["enabled"] is False
    assert "installed_hint" in result


# ---------------------------------------------------------------------------
# Caso 3 — mcp_installation_status() con flag ON
# ---------------------------------------------------------------------------
def test_mcp_installation_status_flag_on(monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.Config, "STACKY_CODEBASE_MEMORY_MCP_ENABLED", True)
    from services import codebase_memory_mcp_status as mod
    import importlib
    importlib.reload(mod)  # reload por si la función cachea el config
    result = mod.mcp_installation_status()
    assert result["enabled"] is True


# ---------------------------------------------------------------------------
# Caso 4 — build_installation_guide("claude_code") cita clave de server "codebase-memory-mcp"
# ---------------------------------------------------------------------------
def test_guide_claude_code_contains_server_key():
    from services.codebase_memory_mcp_status import build_installation_guide
    guide = build_installation_guide("claude_code")
    assert guide.strip(), "La guía de claude_code no debe estar vacía"
    # La clave de server DEBE ser "codebase-memory-mcp" (no "stacky" — no colisionar C4/v3)
    assert "codebase-memory-mcp" in guide, (
        "La guía debe referenciar la clave de server 'codebase-memory-mcp'"
    )
    assert "stacky" not in guide.lower() or "codebase-memory-mcp" in guide, (
        "Si menciona 'stacky', debe aclarar que la clave del server externo es 'codebase-memory-mcp'"
    )


# ---------------------------------------------------------------------------
# Caso 5 — build_installation_guide("codex") → no vacío
# ---------------------------------------------------------------------------
def test_guide_codex_not_empty():
    from services.codebase_memory_mcp_status import build_installation_guide
    guide = build_installation_guide("codex")
    assert guide.strip(), "La guía de codex no debe estar vacía"


# ---------------------------------------------------------------------------
# Caso 6 — build_installation_guide("copilot_pro") → no vacío
# ---------------------------------------------------------------------------
def test_guide_copilot_pro_not_empty():
    from services.codebase_memory_mcp_status import build_installation_guide
    guide = build_installation_guide("copilot_pro")
    assert guide.strip(), "La guía de copilot_pro no debe estar vacía"


# ---------------------------------------------------------------------------
# Caso 7 — runtime inválido → ValueError
# ---------------------------------------------------------------------------
def test_guide_invalid_runtime_raises():
    from services.codebase_memory_mcp_status import build_installation_guide
    with pytest.raises(ValueError, match="runtime"):
        build_installation_guide("unknown_runtime")


# ---------------------------------------------------------------------------
# Caso 8 — Pureza: mcp_installation_status no abre red (C11 monkeypatch socket)
# ---------------------------------------------------------------------------
def test_mcp_status_is_pure_no_network(monkeypatch):
    """mcp_installation_status() y build_installation_guide() no deben abrir sockets."""
    def _raise_on_socket(*args, **kwargs):
        raise RuntimeError("Se intentó abrir un socket — la función NO es pura")

    monkeypatch.setattr(socket, "socket", _raise_on_socket)

    import config as cfg
    monkeypatch.setattr(cfg.Config, "STACKY_CODEBASE_MEMORY_MCP_ENABLED", False)

    from services.codebase_memory_mcp_status import mcp_installation_status, build_installation_guide

    # Ambas deben retornar sin levantar (no abren red)
    result = mcp_installation_status()
    assert result is not None

    guide = build_installation_guide("claude_code")
    assert guide is not None


# ---------------------------------------------------------------------------
# Caso 9 — GET /api/codebase-memory-mcp/status → 200 + enabled=false + guides
# ---------------------------------------------------------------------------
def test_endpoint_status_flag_off():
    from app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/codebase-memory-mcp/status")
    assert resp.status_code == 200, f"Esperaba 200, got {resp.status_code}: {resp.data}"
    data = resp.get_json()
    assert data is not None
    assert data.get("enabled") is False
    assert "guides" in data, "La respuesta debe incluir 'guides'"
    guides = data["guides"]
    assert "claude_code" in guides
    assert "codex" in guides
    assert "copilot_pro" in guides


# ---------------------------------------------------------------------------
# Caso 10 — FLAG_REGISTRY: FlagSpec con env_only=False + key en _CATEGORY_KEYS["avanzado"]
# ---------------------------------------------------------------------------
def test_flag_registry_has_codebase_memory_mcp_flag():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    # Buscar la FlagSpec
    spec = next(
        (f for f in FLAG_REGISTRY if f.key == "STACKY_CODEBASE_MEMORY_MCP_ENABLED"),
        None,
    )
    assert spec is not None, (
        "STACKY_CODEBASE_MEMORY_MCP_ENABLED no está en FLAG_REGISTRY. "
        "Regla dura: toda flag nueva del operador va en FLAG_REGISTRY (harness_flags.py:5-7)."
    )
    assert spec.env_only is False, (
        "env_only debe ser False para que aparezca en la UI (regla operator-config-always-via-ui)"
    )
    # Activación operador 2026-07-10: promovida a default ON (capacidad opt-in).
    assert spec.default is True, "El default debe ser True (promovida por el operador 2026-07-10)"

    # Activación operador 2026-07-10: la key se movió de "avanzado" a "capacidades_optin".
    optin_keys = _CATEGORY_KEYS.get("capacidades_optin", ())
    assert "STACKY_CODEBASE_MEMORY_MCP_ENABLED" in optin_keys, (
        f"La key debe estar en _CATEGORY_KEYS['capacidades_optin']. "
        f"Keys actuales de 'capacidades_optin': {optin_keys}"
    )
