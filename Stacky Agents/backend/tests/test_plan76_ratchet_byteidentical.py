"""Plan 76 — Ratchet byte-idéntico con flag OFF.

Verifica que con STACKY_CODEBASE_MEMORY_MCP_ENABLED=False:
1. El endpoint retorna enabled=false (200, sin romper nada).
2. build_agent_env / prompt final NO contiene la subcadena "codebase-memory-mcp"
   (el server externo no se inyecta cuando el flag está OFF).
   IMPORTANTE: el assert es SOLO sobre el token "codebase-memory-mcp",
   NUNCA sobre "mcpServers" genérico (que YA existe del MCP interno stacky_mcp.py:64-65,
   clave "stacky" — asertar "mcpServers" daría FALSO-FALLO con CLAUDE_CODE_CLI_MCP_ENABLED ON).
3. Los tests del plan 76 están en HARNESS_TEST_FILES (ratchet Plan 49).
"""
from __future__ import annotations

import os


# ---------------------------------------------------------------------------
# Caso 1 — Flag OFF → endpoint 200 + enabled=false
# ---------------------------------------------------------------------------
def test_endpoint_flag_off_returns_enabled_false():
    import config as cfg
    original = cfg.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED
    cfg.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED = False
    try:
        from app import create_app
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/codebase-memory-mcp/status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.get_json()
        assert data["enabled"] is False
    finally:
        cfg.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED = original


# ---------------------------------------------------------------------------
# Caso 2 — Byte-identidad: build_agent_env con flag OFF no inyecta "codebase-memory-mcp"
# [C8/C10] Token específico "codebase-memory-mcp", NUNCA "mcpServers" genérico.
# ---------------------------------------------------------------------------
def test_build_agent_env_flag_off_no_codebase_mcp_token():
    """Con STACKY_CODEBASE_MEMORY_MCP_ENABLED=False, build_agent_env no debe
    contener el token "codebase-memory-mcp" en ningún valor del dict.

    NO se aserta sobre "mcpServers" (ese ya existe del MCP interno stacky_mcp.py:64-65).
    """
    import config as cfg

    # Guardar y parchear el flag a OFF
    original = cfg.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED
    cfg.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED = False
    try:
        from services.claude_code_cli_runner import build_agent_env  # type: ignore[import]
        env = build_agent_env()  # puede retornar None si no hay agente activo
        if env is None:
            # Sin agente activo: el runner no inyecta nada — byte-idéntico por construcción
            return
        # Verificar que NINGÚN valor del dict de env contiene el token específico del plan 76
        codebase_mcp_token = "codebase-memory-mcp"
        for key, val in env.items():
            if isinstance(val, str):
                assert codebase_mcp_token not in val, (
                    f"La env var '{key}' contiene el token '{codebase_mcp_token}' "
                    f"con el flag OFF. El server externo no debe inyectarse cuando el flag está OFF. "
                    f"Valor: {val[:200]}"
                )
    finally:
        cfg.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED = original


# ---------------------------------------------------------------------------
# Caso 3 — Ratchet: los test_plan76_* están en HARNESS_TEST_FILES (Plan 49)
# ---------------------------------------------------------------------------
def test_plan76_tests_in_harness_ratchet():
    """Los test_plan76_*.py deben estar registrados en HARNESS_TEST_FILES (scripts/run_harness_tests.sh).

    Esto asegura que el ratchet del Plan 49 los incluya.
    El assert busca el token "test_plan76" en el archivo sh.
    """
    ratchet_sh = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "run_harness_tests.sh"
    )
    ratchet_sh = os.path.normpath(ratchet_sh)
    assert os.path.exists(ratchet_sh), f"HARNESS_TEST_FILES sh no encontrado: {ratchet_sh}"

    content = open(ratchet_sh, encoding="utf-8").read()
    required_files = [
        "test_plan76_codebase_memory_mcp.py",
        "test_plan76_routes_registered.py",
        "test_plan76_ratchet_byteidentical.py",
    ]
    for f in required_files:
        assert f in content, (
            f"'{f}' no está en HARNESS_TEST_FILES ({ratchet_sh}). "
            f"Plan 49 F4 — todo test nuevo del backend debe registrarse en el ratchet."
        )
