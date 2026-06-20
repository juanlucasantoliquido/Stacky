"""Plan 57 F3 — Tests para STACKY_SPECULATIVE_ENABLED y STACKY_SPECULATIVE_MODE."""
import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Tests sobre start() y claim() (capa de servicio)
# ---------------------------------------------------------------------------

def test_start_returns_minus_one_when_flag_off():
    """start() retorna -1 cuando STACKY_SPECULATIVE_ENABLED=false (default)."""
    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "false"}, clear=False):
        from services.speculative import start
        result = start(
            agent_type="business",
            ticket_id=1,
            context_blocks=[{"kind": "story", "content": "x"}],
            started_by="test",
        )
        assert result == -1, f"Esperado -1, got {result}"


def test_start_returns_minus_one_when_flag_absent():
    """start() retorna -1 cuando la var de entorno no está definida."""
    env = {k: v for k, v in os.environ.items() if k != "STACKY_SPECULATIVE_ENABLED"}
    with patch.dict(os.environ, env, clear=True):
        from services.speculative import start
        result = start(
            agent_type="business",
            ticket_id=1,
            context_blocks=[{"kind": "story", "content": "x"}],
            started_by="test",
        )
        assert result == -1


def test_claim_returns_none_when_flag_off():
    """claim() retorna None cuando STACKY_SPECULATIVE_ENABLED=false (miss → run normal)."""
    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "false"}, clear=False):
        from services.speculative import claim
        result = claim(
            agent_type="business",
            context_blocks=[{"kind": "story", "content": "x"}],
        )
        assert result is None


def test_claim_returns_none_when_flag_absent():
    """claim() retorna None cuando la var de entorno no está definida."""
    env = {k: v for k, v in os.environ.items() if k != "STACKY_SPECULATIVE_ENABLED"}
    with patch.dict(os.environ, env, clear=True):
        from services.speculative import claim
        result = claim(
            agent_type="business",
            context_blocks=[{"kind": "story", "content": "x"}],
        )
        assert result is None


def test_flag_registry_contains_speculative_enabled():
    """STACKY_SPECULATIVE_ENABLED está registrado en FLAG_REGISTRY con env_only=True."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_SPECULATIVE_ENABLED" in keys, \
        "STACKY_SPECULATIVE_ENABLED debe estar en FLAG_REGISTRY"
    spec = keys["STACKY_SPECULATIVE_ENABLED"]
    assert spec.type == "bool", f"Tipo esperado 'bool', got {spec.type!r}"
    assert spec.env_only is True, "STACKY_SPECULATIVE_ENABLED debe ser env_only=True"


def test_flag_registry_contains_speculative_mode():
    """STACKY_SPECULATIVE_MODE está registrado en FLAG_REGISTRY con env_only=True."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_SPECULATIVE_MODE" in keys, \
        "STACKY_SPECULATIVE_MODE debe estar en FLAG_REGISTRY"
    spec = keys["STACKY_SPECULATIVE_MODE"]
    assert spec.type == "csv", f"Tipo esperado 'csv', got {spec.type!r}"
    assert spec.env_only is True, "STACKY_SPECULATIVE_MODE debe ser env_only=True"


def test_mode_lazy_v1_documented_as_deferred():
    """STACKY_SPECULATIVE_MODE description menciona 'lazy' y 'deferred' (v1)."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_SPECULATIVE_MODE" in keys
    desc = keys["STACKY_SPECULATIVE_MODE"].description.lower()
    assert "lazy" in desc, "Description debe mencionar 'lazy'"
    assert "v1" in desc or "deferred" in desc, "Description debe mencionar v1/deferred"


# ---------------------------------------------------------------------------
# Tests sobre los endpoints (phase5) — flag OFF = 404
# ---------------------------------------------------------------------------

def test_endpoints_404_when_flag_off():
    """POST /agents/speculate retorna 404 cuando STACKY_SPECULATIVE_ENABLED=false."""
    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "false"}, clear=False):
        from app import create_app
        app = create_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/agents/speculate",
                json={"agent_type": "business", "ticket_id": 1},
            )
            assert resp.status_code == 404, \
                f"Esperado 404 con flag OFF, got {resp.status_code}"


def test_claim_endpoint_404_when_flag_off():
    """POST /agents/speculate/claim retorna 404 cuando flag OFF."""
    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "false"}, clear=False):
        from app import create_app
        app = create_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/agents/speculate/claim",
                json={"agent_type": "business", "context_blocks": []},
            )
            assert resp.status_code == 404
