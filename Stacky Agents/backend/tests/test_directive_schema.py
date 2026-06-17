"""M1.1 — Schema de directiva (add-only) + directive_matches_run.

Cubre:
  - create_all sobre DB nueva crea las 3 columnas (enforcement/priority/applies_to_json)
  - filas legacy quedan con enforcement=NULL, priority=0, applies_to_json=NULL
  - una observación sin enforcement se comporta byte-idéntico
  - directive_matches_run: cada dimensión, AND multi-dimensión, vacío=matchea todo,
    keyword substring case-insensitive en title vs description
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


def test_columns_exist_and_legacy_defaults(app_ctx):
    from db import session_scope
    from services.memory_store import StackyMemoryObservation, save_observation

    mid = save_observation(
        project="DIR_SCHEMA1", type="bugfix", title="legacy obs",
        content="observacion sin directiva", author_email="op@x.com",
    )
    with session_scope() as s:
        row = s.query(StackyMemoryObservation).filter_by(memory_id=mid).first()
        assert row.enforcement is None
        assert row.priority == 0
        assert row.applies_to_json is None


_MATCH = None


def _matches(**kw):
    from services.memory_store import directive_matches_run

    applies = kw.pop("applies_to")
    return directive_matches_run(
        applies,
        agent_type=kw.get("agent_type"),
        project=kw.get("project"),
        ticket_title=kw.get("ticket_title"),
        ticket_description=kw.get("ticket_description"),
        work_item_type=kw.get("work_item_type"),
    )


def test_empty_applies_matches_everything(app_ctx):
    assert _matches(applies_to={}, agent_type="developer", project="P") is True
    assert _matches(applies_to=None, agent_type="developer", project="P") is True


def test_agent_types_dimension(app_ctx):
    a = {"agent_types": ["developer", "functional"]}
    assert _matches(applies_to=a, agent_type="developer") is True
    assert _matches(applies_to=a, agent_type="Developer") is True  # case-insensitive
    assert _matches(applies_to=a, agent_type="qa") is False


def test_projects_dimension(app_ctx):
    a = {"projects": ["Strategist_Pacifico"]}
    assert _matches(applies_to=a, project="strategist_pacifico") is True
    assert _matches(applies_to=a, project="Otro") is False


def test_work_item_types_dimension(app_ctx):
    a = {"work_item_types": ["Epic", "User Story"]}
    assert _matches(applies_to=a, work_item_type="user story") is True
    assert _matches(applies_to=a, work_item_type="Bug") is False


def test_title_keywords_in_title_and_description(app_ctx):
    a = {"title_keywords": ["nota de crédito"]}
    assert _matches(applies_to=a, ticket_title="Generar Nota de Crédito X") is True
    assert _matches(applies_to=a, ticket_description="incluye nota de CRÉDITO") is True
    assert _matches(applies_to=a, ticket_title="otra cosa", ticket_description="nada") is False


def test_and_multi_dimension(app_ctx):
    a = {
        "agent_types": ["developer"],
        "work_item_types": ["User Story"],
        "title_keywords": ["facturación"],
    }
    # cumple todas
    assert _matches(
        applies_to=a, agent_type="developer", work_item_type="User Story",
        ticket_title="proceso de facturación",
    ) is True
    # falla una dimensión → no matchea (AND)
    assert _matches(
        applies_to=a, agent_type="qa", work_item_type="User Story",
        ticket_title="proceso de facturación",
    ) is False
    assert _matches(
        applies_to=a, agent_type="developer", work_item_type="Bug",
        ticket_title="proceso de facturación",
    ) is False


def test_tags_do_not_participate_in_match(app_ctx):
    # tags presente pero NO restringe el run (decisión M1.1)
    a = {"tags": ["proceso-cobranzas"]}
    assert _matches(applies_to=a, agent_type="developer") is True
