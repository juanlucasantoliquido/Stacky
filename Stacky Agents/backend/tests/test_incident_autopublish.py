"""tests/test_incident_autopublish.py — Plan 166 F3.

Creación directa y en lote: con STACKY_INCIDENT_AUTO_PUBLISH_ENABLED ON, el
post-hook publica la Issue automáticamente al terminar el análisis, sin
confirmación humana; el endpoint /incidents/publish deja de exigir
`confirm` mientras el flag esté ON. Espeja los helpers de
tests/test_plan131_incident_preview_publish.py (_make_app/_patch_run/
FakeProvider) — C10 del plan.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runtime_paths
from services import doc_indexer, incident_store
from services.tracker_provider import TrackerItem


@pytest.fixture(autouse=True)
def _isolate_docs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_indexer, "STACKY_AGENTS_ROOT", tmp_path)


OUTPUT_FULL_HTML = """
<h1>[INC] La pantalla de login se rompe</h1>
<h2>RESUMEN EJECUTIVO</h2><p>Los usuarios no pueden ingresar.</p>
<h2>CONTEXTO DE NEGOCIO</h2><p>Afecta el proceso de alta de clientes.</p>
<h2>ANALISIS FUNCIONAL</h2><p>Comportamiento esperado vs observado.</p>
<h2>ANALISIS TECNICO</h2><p>Hipotesis de causa raiz en backend/services/foo.py.</p>
<h2>PASOS DE REPRODUCCION</h2><ol><li>Entrar a login</li></ol>
<h2>CRITERIOS DE ACEPTACION</h2><ul><li>El login funciona</li></ul>
<h2>ARCHIVOS Y MODULOS PROBABLES</h2><ul><li>backend/services/foo.py</li></ul>
<h2>EPICA RELACIONADA</h2><p>EPICA: ninguna</p>
<h2>PRIORIDAD Y ESTIMACION</h2><p>Prioridad: alta. Estimacion: S.</p>
"""


class FakeProvider:
    def __init__(self):
        self.created_items: list[TrackerItem] = []
        self._next_id = 999

    def create_item(self, item: TrackerItem) -> dict:
        self.created_items.append(item)
        self._next_id += 1
        return {"id": self._next_id, "web_url": f"https://fake.tracker/{self._next_id}"}

    def item_url(self, item_id: str) -> str:
        return f"https://fake.tracker/{item_id}"

    def post_comment(self, item_id: str, body_html: str) -> dict:
        return {"ok": True}

    def upload_attachment(self, file_path: str, file_name: str) -> dict:
        return {"id": f"att-{file_name}"}

    def link_attachment(self, item_id: str, attachment: dict) -> dict:
        return {"ok": True}


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _flag(*, resolver: bool = True, auto_publish: bool = True):
    import config as cfg
    original_resolver = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    original_auto = getattr(cfg.config, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = resolver
    cfg.config.STACKY_INCIDENT_AUTO_PUBLISH_ENABLED = auto_publish
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original_resolver
        cfg.config.STACKY_INCIDENT_AUTO_PUBLISH_ENABLED = original_auto


def _patch_run(monkeypatch, output: str | None, execution_id: int = 1):
    import api.tickets as t_mod
    fake_run = MagicMock()
    fake_run.id = execution_id
    fake_run.output = output
    fake_run.project_name = None
    fake_run.metadata_dict = {}
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)


def _create_incident(tmp_path, monkeypatch, text="incidencia de prueba", files=None, auto_publish=False):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return incident_store.create_incident(text, files or [], auto_publish=auto_publish)


# ── 1-4, 7. maybe_autopublish_incident (unidad, mockeando _do_publish_incident) ──


def test_autopublish_publishes_when_flag_on_and_auto_flag_set(tmp_path, monkeypatch):
    from services import incident_autopublish
    import config as cfg

    incident = _create_incident(tmp_path, monkeypatch, auto_publish=True)
    incident_store.update_incident(incident["id"], execution_id=1)
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", True, raising=False)

    calls = []

    def _fake_do_publish(incident_id, execution_id):
        calls.append((incident_id, execution_id))
        return {"ok": True, "tracker_id": "555"}, 201

    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_do_publish_incident", _fake_do_publish)

    incident_autopublish.maybe_autopublish_incident(
        ticket_id=1, execution_id=1, final_status="completed", agent_type="incident",
    )
    assert calls == [(incident["id"], 1)]


def test_autopublish_skips_when_flag_off(tmp_path, monkeypatch):
    from services import incident_autopublish
    import config as cfg

    incident = _create_incident(tmp_path, monkeypatch, auto_publish=True)
    incident_store.update_incident(incident["id"], execution_id=1)
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", False, raising=False)

    import api.tickets as t_mod
    calls = []
    monkeypatch.setattr(t_mod, "_do_publish_incident", lambda *a, **kw: calls.append(1))

    incident_autopublish.maybe_autopublish_incident(
        ticket_id=1, execution_id=1, final_status="completed", agent_type="incident",
    )
    assert calls == []


def test_autopublish_skips_when_incident_not_auto(tmp_path, monkeypatch):
    from services import incident_autopublish
    import config as cfg

    incident = _create_incident(tmp_path, monkeypatch, auto_publish=False)
    incident_store.update_incident(incident["id"], execution_id=1)
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", True, raising=False)

    import api.tickets as t_mod
    calls = []
    monkeypatch.setattr(t_mod, "_do_publish_incident", lambda *a, **kw: calls.append(1))

    incident_autopublish.maybe_autopublish_incident(
        ticket_id=1, execution_id=1, final_status="completed", agent_type="incident",
    )
    assert calls == []


def test_autopublish_idempotent_when_already_published(tmp_path, monkeypatch):
    from services import incident_autopublish
    import config as cfg

    incident = _create_incident(tmp_path, monkeypatch, auto_publish=True)
    incident_store.update_incident(incident["id"], execution_id=1, tracker_id="123")
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", True, raising=False)

    import api.tickets as t_mod
    calls = []
    monkeypatch.setattr(t_mod, "_do_publish_incident", lambda *a, **kw: calls.append(1))

    incident_autopublish.maybe_autopublish_incident(
        ticket_id=1, execution_id=1, final_status="completed", agent_type="incident",
    )
    assert calls == []


def test_autopublish_marks_error_on_exception(tmp_path, monkeypatch):
    """C3 — un fallo del autopublish NUNCA deja la cola muda en 'analizando'."""
    from services import incident_autopublish
    import config as cfg

    incident = _create_incident(tmp_path, monkeypatch, auto_publish=True)
    incident_store.update_incident(incident["id"], execution_id=1, status="analizando")
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", True, raising=False)

    def _boom(incident_id, execution_id):
        raise RuntimeError("boom")

    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_do_publish_incident", _boom)

    incident_autopublish.maybe_autopublish_incident(
        ticket_id=1, execution_id=1, final_status="completed", agent_type="incident",
    )
    updated = incident_store.get_incident(incident["id"])
    assert updated["status"] == "error"
    assert updated["error"] == "boom"


# ── 5-6. endpoint /incidents/publish con auto-publish ON/OFF ────────────────


def test_publish_endpoint_allows_no_confirm_when_flag_on(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider()
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(resolver=True, auto_publish=True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1},
            )
    assert resp.status_code == 201, resp.get_json()


def test_publish_endpoint_requires_confirm_when_flag_off(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()
    with _flag(resolver=True, auto_publish=False):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1},
            )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "confirmation_required"


# ── 8. [ADICIÓN ARQUITECTO]/C7 — el doc nace con el tracker_id real ─────────


def test_publish_backfills_doc_tracker_id(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider()
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(resolver=True, auto_publish=False):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    tracker_id = data["tracker_id"]
    doc_path = data["doc_path"]
    assert doc_path is not None

    doc_text = Path(doc_path).read_text(encoding="utf-8")
    assert f"tracker_id: {tracker_id}" in doc_text
    assert "estado: publicada" in doc_text

    # DoD — INDICE_INCIDENCIAS.md también nace con el tracker_id real
    # (_append_to_index usa la misma variable local que el doc).
    index_path = Path(doc_path).parent / "INDICE_INCIDENCIAS.md"
    index_text = index_path.read_text(encoding="utf-8")
    assert f"tracker#{tracker_id}" in index_text
