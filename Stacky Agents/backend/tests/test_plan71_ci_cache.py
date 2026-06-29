"""Plan 71 F2 — Tests: fábrica get_ci_provider + set/get cache.

5 casos:
  1. get_ci_provider() con tracker_type=azure_devops → retorna AdoCIProvider.
  2. get_ci_provider() con gitlab + flag false → TrackerConfigError.
  3. get_ci_provider() con gitlab + flag true → retorna GitLabCIProvider.
  4. set_cached + get_cached round-trip (con TTL largo).
  5. Claves compuestas distintas no se mezclan.
"""
from __future__ import annotations

import json
import sys
import types
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import config


# ---------------------------------------------------------------------------
# Helpers de BD en memoria
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def in_memory_db(tmp_path):
    """Parchea la sesión de DB para usar SQLite en memoria."""
    import services.ci_inference_cache as cache_mod
    from models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    original = cache_mod._get_session
    def fake_session():
        return Session(engine)
    cache_mod._get_session = fake_session
    yield
    cache_mod._get_session = original


# ---------------------------------------------------------------------------
# C1 — get_ci_provider → AdoCIProvider cuando tracker es azure_devops
# ---------------------------------------------------------------------------
def test_get_ci_provider_returns_ado_provider(monkeypatch):
    from services.ci_provider import get_ci_provider
    from services.project_context import ProjectContext

    ctx = ProjectContext(
        stacky_project_name="test_proj",
        tracker_type="azure_devops",
        tracker_project="TestProject",
    )
    monkeypatch.setattr(
        "services.project_context.resolve_project_context",
        lambda project_name=None: ctx,
    )

    # Stub del módulo ado_ci_provider para que exista antes del import lazy
    stub_ado = types.ModuleType("services.ado_ci_provider")
    stub_provider = MagicMock()
    stub_provider.name = "azure_devops"
    stub_ado.AdoCIProvider = lambda project=None: stub_provider
    monkeypatch.setitem(sys.modules, "services.ado_ci_provider", stub_ado)

    provider = get_ci_provider("test_proj")
    assert provider.name == "azure_devops"


# ---------------------------------------------------------------------------
# C2 — get_ci_provider + gitlab + flag OFF → TrackerConfigError
# ---------------------------------------------------------------------------
def test_get_ci_provider_gitlab_flag_off_raises(monkeypatch):
    from services.ci_provider import get_ci_provider
    from services.project_context import ProjectContext
    from services.tracker_provider import TrackerConfigError

    ctx = ProjectContext(
        stacky_project_name="test_proj",
        tracker_type="gitlab",
        tracker_project="TestProject",
    )
    monkeypatch.setattr(
        "services.project_context.resolve_project_context",
        lambda project_name=None: ctx,
    )
    monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", False)

    with pytest.raises(TrackerConfigError, match="STACKY_GITLAB_ENABLED"):
        get_ci_provider("test_proj")


# ---------------------------------------------------------------------------
# C3 — get_ci_provider + gitlab + flag ON → GitLabCIProvider
# ---------------------------------------------------------------------------
def test_get_ci_provider_gitlab_flag_on(monkeypatch):
    from services.ci_provider import get_ci_provider
    from services.project_context import ProjectContext

    ctx = ProjectContext(
        stacky_project_name="test_proj",
        tracker_type="gitlab",
        tracker_project="TestProject",
    )
    monkeypatch.setattr(
        "services.project_context.resolve_project_context",
        lambda project_name=None: ctx,
    )
    monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", True)

    # Stub del módulo gitlab_ci_provider para que exista antes del import lazy
    stub_gl_mod = types.ModuleType("services.gitlab_ci_provider")
    stub_gl = MagicMock()
    stub_gl.name = "gitlab"
    stub_gl_mod.GitLabCIProvider = lambda project=None: stub_gl
    monkeypatch.setitem(sys.modules, "services.gitlab_ci_provider", stub_gl_mod)

    provider = get_ci_provider("test_proj")
    assert provider.name == "gitlab"


# ---------------------------------------------------------------------------
# C4 — set_cached + get_cached round-trip
# ---------------------------------------------------------------------------
def test_cache_set_and_get():
    from services.ci_inference_cache import set_cached, get_cached

    payload = {"overall_progress": 0.5, "source": "llm"}
    set_cached("azure_devops", "123", None, payload, "llm")

    result = get_cached("azure_devops", "123", None, ttl_minutes=60)
    assert result is not None
    assert result["overall_progress"] == 0.5


# ---------------------------------------------------------------------------
# C5 — Claves distintas no se mezclan
# ---------------------------------------------------------------------------
def test_cache_composite_keys_independent():
    from services.ci_inference_cache import set_cached, get_cached

    set_cached("azure_devops", "100", None, {"source": "llm", "progress": 0.1}, "llm")
    set_cached("azure_devops", "200", None, {"source": "ci", "progress": 0.9}, "ci")

    r1 = get_cached("azure_devops", "100", None, ttl_minutes=60)
    r2 = get_cached("azure_devops", "200", None, ttl_minutes=60)

    assert r1["progress"] == 0.1
    assert r2["progress"] == 0.9
