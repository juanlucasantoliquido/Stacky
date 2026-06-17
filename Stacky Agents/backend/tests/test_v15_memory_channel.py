"""V1.5 — Consolidación estructural del doble canal de conocimiento (B5).

Garantía (no por convención): los tipos reservados al canal SYSTEM prompt (FA-*)
no se pueden crear por `POST /api/memory` (canal USER prompt) y nunca se inyectan
por `get_context_for_run`. Ambos lados deben leer de UNA sola fuente de verdad.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_reserved_types_are_the_injection_exclusion_set():
    """La allowlist de rechazo del POST y el filtro de inyección son el MISMO set."""
    from services import memory_store

    # Fuente única de verdad: el set que get_context_for_run excluye.
    assert memory_store.RESERVED_TYPES is memory_store._SYSTEM_PROMPT_TYPES
    # Los 4 tipos FA-* listados en el plan V1.5 están reservados.
    for reserved in ("decision", "anti_pattern", "glossary", "style"):
        assert reserved in memory_store.RESERVED_TYPES


@pytest.mark.parametrize("reserved", ["decision", "anti_pattern", "glossary", "style"])
def test_post_memory_rejects_reserved_type(client, reserved):
    r = client.post(
        "/api/memory",
        json={
            "project": "MEM_V15",
            "type": reserved,
            "title": "x",
            "content": "y",
        },
    )
    assert r.status_code == 400
    assert reserved in (r.get_data(as_text=True) or "")


def test_post_memory_allows_non_reserved_type(client):
    r = client.post(
        "/api/memory",
        json={
            "project": "MEM_V15",
            "type": "session_summary",
            "title": "ok",
            "content": "contenido inyectable por el canal USER",
        },
    )
    assert r.status_code == 201
