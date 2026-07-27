"""Plan 214 F1 — GET /api/qa-uat/kb: inventario de la KB de navegación.

Contrato: SIEMPRE 200. Con el tool sano devuelve el inventario; con el tool roto
degrada a {ok:false, error:"kb_unavailable"} — nunca 5xx, porque el consumidor lo
lee de forma opcional.

Comando:
  cd "N:\\GIT\\RS\\STACKY\\Stacky\\Stacky Agents\\backend"
  & ".venv\\Scripts\\python.exe" -m pytest tests\\test_plan214_qa_uat_kb_endpoint.py -q
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(scope="module")
def app():
    from app import create_app
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_kb_endpoint_ok(client):
    resp = client.get("/api/qa-uat/kb")
    assert resp.status_code == 200
    body = resp.get_json()
    for key in ("ok", "screens_declared", "ui_maps", "playbooks",
                "playbooks_total", "missing_ui_maps", "coverage_pct"):
        assert key in body, f"falta la key {key!r} en {sorted(body)}"
    assert body["ok"] is True
    # Anti-inerte: el endpoint lee la KB REAL del tool, no un stub vacío.
    assert len(body["screens_declared"]) >= 5
    assert body["playbooks_total"] >= 1


def test_kb_endpoint_degrada(client, monkeypatch):
    """Con el inventario roto el endpoint sigue en 200 con ok:false."""
    from api.qa_uat import _ensure_pipeline_on_path
    _ensure_pipeline_on_path()
    import navigation_kb

    def _boom(*a, **kw):
        raise RuntimeError("cache ilegible")

    monkeypatch.setattr(navigation_kb, "kb_inventory", _boom)

    resp = client.get("/api/qa-uat/kb")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"] == "kb_unavailable"
    assert "cache ilegible" in body["message"]
