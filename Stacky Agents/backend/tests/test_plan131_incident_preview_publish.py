"""tests/test_plan131_incident_preview_publish.py — Plan 131 F5.

GET /api/tickets/incident-preview + POST /api/tickets/incidents/publish.
FakeProvider en-memoria (CERO red, cero llamadas reales a ADO/GitLab) — patrón
de mock de `_get_run_for_preview` espejado de test_epic_preview_endpoint.py.
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
from services.tracker_provider import TrackerApiError, TrackerItem


@pytest.fixture(autouse=True)
def _isolate_docs_root(tmp_path, monkeypatch):
    """Aísla incident_docs.write_incident_doc (invocado por publish_incident)
    para que NUNCA escriba fuera de tmp_path — sin este fixture, los tests de
    publish escriben .md reales bajo Stacky Agents/docs/incidencias/ del repo."""
    monkeypatch.setattr(doc_indexer, "STACKY_AGENTS_ROOT", tmp_path)

OUTPUT_NARRATIVE = "Voy a analizar la incidencia y te cuento en un momento..."

OUTPUT_FULL_HTML = """
<h1>[INC] La pantalla de login se rompe</h1>
<h2>RESUMEN EJECUTIVO</h2><p>Los usuarios no pueden ingresar.</p>
<h2>CONTEXTO DE NEGOCIO</h2><p>Afecta el proceso de alta de clientes.</p>
<h2>ANALISIS FUNCIONAL</h2><p>Comportamiento esperado vs observado.</p>
<h2>ANALISIS TECNICO</h2><p>Hipotesis de causa raiz en backend/services/foo.py.</p>
<h2>PASOS DE REPRODUCCION</h2><ol><li>Entrar a login</li></ol>
<h2>CRITERIOS DE ACEPTACION</h2><ul><li>El login funciona</li></ul>
<h2>ARCHIVOS Y MODULOS PROBABLES</h2><ul><li>backend/services/foo.py</li></ul>
<h2>EPICA RELACIONADA</h2><p>EPICA: 267 | CONFIANZA: 85 | RAZON: afecta el alta de clientes</p>
<h2>PRIORIDAD Y ESTIMACION</h2><p>Prioridad: alta. Estimacion: S.</p>
"""

OUTPUT_NO_EPIC_HTML = OUTPUT_FULL_HTML.replace(
    "EPICA: 267 | CONFIANZA: 85 | RAZON: afecta el alta de clientes",
    "EPICA: ninguna",
)

OUTPUT_ONLY_TWO_SECTIONS = "<h1>Titulo</h1><h2>RESUMEN EJECUTIVO</h2><p>x</p><h2>ANALISIS FUNCIONAL</h2><p>x</p>"


class FakeProvider:
    """fail_mode: 'none' | 'parent_once' | 'always'."""

    def __init__(self, fail_mode: str = "none"):
        self.fail_mode = fail_mode
        self.created_items: list[TrackerItem] = []
        self.comments: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, str]] = []
        self.links: list[tuple[str, dict]] = []
        self._next_id = 900

    def create_item(self, item: TrackerItem) -> dict:
        self.created_items.append(item)
        if self.fail_mode == "always":
            raise TrackerApiError(status=500, message="tracker caído", kind="server_error")
        if self.fail_mode == "parent_once" and item.parent_id is not None:
            raise TrackerApiError(status=400, message="parent inválido", kind="bad_parent")
        self._next_id += 1
        return {"id": self._next_id, "web_url": f"https://fake.tracker/{self._next_id}"}

    def item_url(self, item_id: str) -> str:
        return f"https://fake.tracker/{item_id}"

    def post_comment(self, item_id: str, body_html: str) -> dict:
        self.comments.append((item_id, body_html))
        return {"ok": True}

    def upload_attachment(self, file_path: str, file_name: str) -> dict:
        if file_name == "fails.log":
            raise RuntimeError("upload falló")
        self.uploads.append((file_path, file_name))
        return {"id": f"att-{file_name}"}

    def link_attachment(self, item_id: str, attachment: dict) -> dict:
        self.links.append((item_id, attachment))
        return {"ok": True}


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _flag(enabled: bool):
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = enabled
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


def _patch_run(monkeypatch, output: str | None, execution_id: int = 1):
    import api.tickets as t_mod
    fake_run = MagicMock()
    fake_run.id = execution_id
    fake_run.output = output
    fake_run.project_name = None
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)


def _create_incident(tmp_path, monkeypatch, text="incidencia de prueba", files=None):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return incident_store.create_incident(text, files or [])


# ── 1. _looks_like_incident ────────────────────────────────────────────────


def test_looks_like_incident_full_html_true():
    from api.tickets import _looks_like_incident
    assert _looks_like_incident(OUTPUT_FULL_HTML) is True


def test_looks_like_incident_narrative_false():
    from api.tickets import _looks_like_incident
    assert _looks_like_incident(OUTPUT_NARRATIVE) is False


def test_looks_like_incident_two_sections_false():
    from api.tickets import _looks_like_incident
    assert _looks_like_incident(OUTPUT_ONLY_TWO_SECTIONS) is False


# ── 2. _parse_related_epic ─────────────────────────────────────────────────


def test_parse_related_epic_full_case():
    from api.tickets import _parse_related_epic
    result = _parse_related_epic(OUTPUT_FULL_HTML)
    assert result["epic_id"] == 267
    assert result["confidence"] == 85
    assert "alta de clientes" in result["reason"]


def test_parse_related_epic_ninguna_case():
    from api.tickets import _parse_related_epic
    result = _parse_related_epic(OUTPUT_NO_EPIC_HTML)
    assert result["epic_id"] is None


def test_parse_related_epic_missing_section_all_none():
    from api.tickets import _parse_related_epic
    result = _parse_related_epic("<h1>x</h1><p>sin nada relevante</p>")
    assert result == {"epic_id": None, "confidence": None, "reason": None}


def test_parse_related_epic_confidence_clamped_to_100():
    from api.tickets import _parse_related_epic
    html = "<p>EPICA: 5 | CONFIANZA: 150 | RAZON: motivo</p>"
    result = _parse_related_epic(html)
    assert result["confidence"] == 100


# ── 3-4. GET /incident-preview ─────────────────────────────────────────────


def test_preview_narrative_output_not_in_output(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_NARRATIVE)
    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "incident_not_in_output"
    assert data["publishable"] is False


def test_preview_happy_path(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    incident_store.update_incident(incident["id"], status="analizando", execution_id=1)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["title"] == "[INC] La pantalla de login se rompe"
    assert data["related_epic"]["epic_id"] == 267
    updated = incident_store.get_incident(incident["id"])
    assert updated["status"] == "analizada"


# ── 5. publish sin confirm ──────────────────────────────────────────────────


def test_publish_without_confirm_400(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1},
            )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "confirmation_required"


def test_publish_confirm_string_true_400(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": "true"},
            )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "confirmation_required"


# ── 6. publish feliz con épica ───────────────────────────────────────────────


def test_publish_happy_with_epic_parent(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider(fail_mode="none")
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert data["epic_link_mode"] == "parent"

    item = fake_provider.created_items[0]
    assert item.parent_id == "267"
    assert "incidencia" in item.labels
    assert item.fields["System.Tags"] == "incidencia; stacky-incident"
    # C1 congelado: System.Title/System.Description duplicados dentro de fields
    # (la rama WS1 de AdoClient.create_work_item ignora los posicionales).
    assert item.fields["System.Title"] == "[INC] La pantalla de login se rompe"
    assert item.fields["System.Title"] == item.title
    assert item.fields["System.Description"] == item.description_html


# ── 7. TrackerApiError con parent → retry sin parent + comment ─────────────


def test_publish_parent_fails_retries_without_parent_and_comments(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider(fail_mode="parent_once")
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert data["epic_link_mode"] == "comment"
    assert len(fake_provider.created_items) == 2
    assert fake_provider.created_items[0].parent_id == "267"
    assert fake_provider.created_items[1].parent_id is None
    assert len(fake_provider.comments) == 1
    assert fake_provider.comments[0][0] == "267"


# ── 8. override_epic_id=null ─────────────────────────────────────────────


def test_publish_override_epic_id_null_no_parent(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider(fail_mode="none")
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={
                    "incident_id": incident["id"], "execution_id": 1, "confirm": True,
                    "override_epic_id": None,
                },
            )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert data["epic_link_mode"] == "none"
    assert data["epic_id"] is None
    assert fake_provider.created_items[0].parent_id is None


# ── 9. attachments: 1 falla, 1 ok ────────────────────────────────────────


def test_publish_attachment_partial_failure_warns_but_publishes(tmp_path, monkeypatch):
    incident = _create_incident(
        tmp_path, monkeypatch,
        files=[("ok.png", b"okbytes"), ("fails.log", b"failbytes")],
    )
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider(fail_mode="none")
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert len(fake_provider.uploads) == 1
    assert any("attachment_failed:fails.log" in w for w in data["warnings"])


# ── 10. re-publish → 409 ─────────────────────────────────────────────────


def test_publish_already_published_409(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    incident_store.update_incident(incident["id"], tracker_id="123", status="publicada")

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error"] == "already_published"
    assert data["tracker_id"] == "123"


# ── 11. flag OFF en ambos endpoints ──────────────────────────────────────


def test_flag_off_404_both_endpoints(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()
    with _flag(False):
        with app.test_client() as client:
            preview_resp = client.get(
                f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}"
            )
            publish_resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert preview_resp.status_code == 404
    assert publish_resp.status_code == 404


# ── 12. (C7) create_item lanza SIEMPRE → 502 tracker_error, re-publicable ──


def test_publish_tracker_error_terminal_c7(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider(fail_mode="always")
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = client.post(
                "/api/tickets/incidents/publish",
                json={"incident_id": incident["id"], "execution_id": 1, "confirm": True},
            )
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["error"] == "tracker_error"

    updated = incident_store.get_incident(incident["id"])
    assert updated["status"] == "error"
    assert updated["tracker_id"] is None
    assert updated["doc_path"] is None


# ── 13. (C8) preview GET dos veces + publicada no retrocede ────────────────


def test_preview_idempotent_and_published_does_not_regress(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    incident_store.update_incident(incident["id"], status="analizando", execution_id=1)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    app = _make_app()

    with _flag(True):
        with app.test_client() as client:
            resp1 = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
            resp2 = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    assert resp1.get_json() == resp2.get_json()

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    incident_store.update_incident(incident["id"], status="publicada", tracker_id="999")
    with _flag(True):
        with app.test_client() as client:
            client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    still_published = incident_store.get_incident(incident["id"])
    assert still_published["status"] == "publicada"
