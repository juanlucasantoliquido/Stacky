"""M3.1 — Scopes/types configurables desde la UI.

Cubre:
  - STACKY_MEMORY_INJECT_SCOPES default = byte-idéntico (project,team,global)
  - agregar 'personal' → memorias personales entran a la inyección
  - quitar 'team' → memorias team dejan de inyectarse
  - GET /api/memory/types lista injectables y reservados
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_default_inject_scopes_byte_identical(client):
    from services import cli_feature_flags

    # sin flag → default histórico
    os.environ.pop("STACKY_MEMORY_INJECT_SCOPES", None)
    assert cli_feature_flags.memory_inject_scopes() == ("project", "team", "global")


def test_inject_scopes_can_add_personal(client):
    from services import cli_feature_flags

    os.environ["STACKY_MEMORY_INJECT_SCOPES"] = "project,team,global,personal"
    try:
        scopes = cli_feature_flags.memory_inject_scopes()
        assert "personal" in scopes
    finally:
        os.environ.pop("STACKY_MEMORY_INJECT_SCOPES", None)


def test_inject_scopes_can_drop_team(client):
    from services import cli_feature_flags

    os.environ["STACKY_MEMORY_INJECT_SCOPES"] = "project,global"
    try:
        scopes = cli_feature_flags.memory_inject_scopes()
        assert "team" not in scopes
        assert set(scopes) == {"project", "global"}
    finally:
        os.environ.pop("STACKY_MEMORY_INJECT_SCOPES", None)


def test_personal_scope_injected_when_enabled(client):
    from services import memory_store

    project = "M31SCOPE"
    memory_store.save_observation(
        project=project, type="bugfix", title="personal mem",
        content="nota personal del operador sobre xyz", scope="personal",
        author_email="op@x.com",
    )
    # default scopes (sin personal) → no entra
    ctx_default = memory_store.get_context_for_run(
        project=project, agent_type="developer", query_text="personal operador",
        inject_scopes=("project", "team", "global"),
    )
    # con personal → entra
    ctx_personal = memory_store.get_context_for_run(
        project=project, agent_type="developer", query_text="personal operador",
        inject_scopes=("project", "team", "global", "personal"),
    )
    assert ctx_personal["active_hits"] >= 1
    assert ctx_default["active_hits"] == 0


def test_types_endpoint(client):
    r = client.get("/api/memory/types")
    assert r.status_code == 200
    body = r.get_json()
    assert "reserved" in body and "injectable" in body
    assert "decision" in body["reserved"]
    assert "directive" in body["injectable"]
