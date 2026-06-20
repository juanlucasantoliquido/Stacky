"""Plan 55 F1 — Tests del endpoint GET /api/tickets/epic-preview.

Valida:
- Con output de épica válida: 200, ok=True, html no vacío, title no vacío.
- Runtime codex_cli: publishable_runtime=False.
- Runtime github_copilot: publishable_runtime=False.
- Runtime claude_code_cli: publishable_runtime=True.
- Flag STACKY_ADO_PREVIEW_ENABLED=false → 404.
- execution_id inexistente → 404 con error="run_not_found".
- work_item_type=Issue: reusa la misma lógica (ok=True para HTML válido).
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock


OUTPUT_WITH_EPIC = (
    "Claro, acá va la épica:\n\n"
    "```html\n"
    "<h1>EP-9 — Portal de Autogestión</h1><p>Objetivo de negocio...</p>"
    "<hr><h2>RF-001 — Autenticación</h2><p>El usuario debe poder ingresar.</p>\n"
    "```\n\n"
    "Resumen: listo ✅"
)

OUTPUT_EMPTY = ""


def _make_fake_run(
    *,
    execution_id: int = 1,
    output: str | None = OUTPUT_WITH_EPIC,
    brief: str = "Necesito un portal",
    project_name: str = "Pacifico",
    runtime: str = "claude_code_cli",
):
    """Crea un objeto fake que imita AgentExecution para el endpoint."""
    run = MagicMock()
    run.id = execution_id
    run.output = output
    run.metadata = {"brief": brief}
    run.project_name = project_name
    run.runtime = runtime
    return run


@pytest.fixture()
def client(monkeypatch):
    """Flask test client con DB mockeada."""
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        with app.app_context():
            yield c, monkeypatch, app


def _patch_db(monkeypatch, run_or_none):
    """Parchea session_scope + AgentExecution.query para devolver el run fake."""
    import api.tickets as t_mod

    def _fake_get_run(execution_id: int, *, db):
        return run_or_none

    monkeypatch.setattr(t_mod, "_get_run_for_preview", _fake_get_run, raising=False)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_preview_returns_html_for_epic(client, monkeypatch):
    """200, ok=True, html y title no vacíos para output de épica válida."""
    c, mp, app = client
    fake_run = _make_fake_run(runtime="claude_code_cli")
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=1&work_item_type=Epic")
    assert resp.status_code == 200, resp.data
    data = resp.get_json()
    assert data["ok"] is True
    assert data["html"]
    assert data["title"]
    assert "RF-001" in data["html"]
    assert data["work_item_type"] == "Epic"
    assert data["publishable_runtime"] is True


def test_preview_returns_false_for_codex_publishable(client, monkeypatch):
    """runtime=codex_cli → publishable_runtime=False."""
    c, mp, app = client
    fake_run = _make_fake_run(runtime="codex_cli")
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["publishable_runtime"] is False


def test_preview_returns_false_for_copilot_publishable(client, monkeypatch):
    """runtime=github_copilot → publishable_runtime=False."""
    c, mp, app = client
    fake_run = _make_fake_run(runtime="github_copilot")
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["publishable_runtime"] is False


def test_preview_returns_true_for_claude_cli(client, monkeypatch):
    """runtime=claude_code_cli → publishable_runtime=True."""
    c, mp, app = client
    fake_run = _make_fake_run(runtime="claude_code_cli")
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["publishable_runtime"] is True


def test_preview_404_when_flag_off(client, monkeypatch):
    """STACKY_ADO_PREVIEW_ENABLED=false → 404."""
    c, mp, app = client
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "false")

    resp = c.get("/api/tickets/epic-preview?execution_id=1")
    assert resp.status_code == 404


def test_preview_404_when_run_not_found(client, monkeypatch):
    """execution_id inexistente → 404 con error='run_not_found'."""
    c, mp, app = client
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: None, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=9999")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "run_not_found"


def test_preview_empty_output_returns_200_ok_false(client, monkeypatch):
    """output vacío → 200, ok=False, error='empty_output' (run aún corriendo)."""
    c, mp, app = client
    fake_run = _make_fake_run(output="", runtime="claude_code_cli")
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "empty_output"


def test_preview_work_item_type_issue(client, monkeypatch):
    """work_item_type=Issue → misma lógica, ok=True para HTML válido."""
    c, mp, app = client
    fake_run = _make_fake_run(runtime="claude_code_cli")
    mp.setenv("STACKY_ADO_PREVIEW_ENABLED", "true")

    import api.tickets as t_mod
    mp.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)

    resp = c.get("/api/tickets/epic-preview?execution_id=1&work_item_type=Issue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["work_item_type"] == "Issue"
