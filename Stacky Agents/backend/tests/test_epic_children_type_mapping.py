"""Tests Plan 153 F3 — mapeo Feature->tipo disponible + pérdida parcial visible."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# OBLIGATORIO antes de cualquier import de módulos de la app:
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(autouse=True)
def _clear_cache():
    from api import tickets
    tickets._WIT_TYPES_CACHE.clear()
    yield
    tickets._WIT_TYPES_CACHE.clear()


class _FakeTypeClient:
    def __init__(self, types, raises=False):
        self._types = types
        self._raises = raises
        self.calls = 0

    def fetch_work_item_type_names(self):
        self.calls += 1
        if self._raises:
            raise RuntimeError("descubrimiento falló")
        return self._types


# ── Resolver ──────────────────────────────────────────────────────────────────

def test_template_agile_usa_feature():
    from api.tickets import _resolve_feature_type
    client = _FakeTypeClient(["Epic", "Feature", "User Story", "Task"])
    tipo, warning = _resolve_feature_type(client, "proj_agile")
    assert tipo == "Feature"
    assert warning is None


def test_template_basic_mapea_a_issue():
    from api.tickets import _resolve_feature_type
    client = _FakeTypeClient(["Epic", "Issue", "Task"])
    tipo, warning = _resolve_feature_type(client, "proj_basic")
    assert tipo == "Issue"
    assert warning is not None


def test_template_scrum_mapea_a_pbi():
    from api.tickets import _resolve_feature_type
    client = _FakeTypeClient(["Epic", "Product Backlog Item", "Task"])
    tipo, warning = _resolve_feature_type(client, "proj_scrum")
    assert tipo == "Product Backlog Item"
    assert warning is not None


def test_descubrimiento_falla_fallback_feature():
    from api.tickets import _resolve_feature_type
    client = _FakeTypeClient([], raises=True)
    tipo, warning = _resolve_feature_type(client, "proj_x")
    assert tipo == "Feature"
    assert warning is None  # byte-idéntico a hoy


def test_cache_por_proyecto():
    from api.tickets import _resolve_feature_type
    client = _FakeTypeClient(["Epic", "Feature", "Task"])
    _resolve_feature_type(client, "proj_cache")
    _resolve_feature_type(client, "proj_cache")
    assert client.calls == 1  # segunda llamada usa cache


# ── publish_epic_children con template sin Feature ────────────────────────────

class _FakeAdo:
    def __init__(self, types):
        self._types = types
        self.created_types: list[str] = []

    def fetch_work_item_type_names(self):
        return self._types

    def find_child_by_marker(self, parent, marker):
        return None

    def create_work_item(self, work_item_type, fields, parent_ado_id):
        self.created_types.append(work_item_type)
        return {"id": len(self.created_types)}


def test_publish_children_sin_feature_crea_mapeado_con_warning():
    from api import tickets
    from api.tickets import publish_epic_children, ChildNodePreview, EpicChildrenPlan

    plan = EpicChildrenPlan(
        ok=True,
        features=[ChildNodePreview(work_item_type="Feature", title="F1", html="<p>rf</p>", children=[])],
        total_children=1,
        error=None,
    )
    fake_ado = _FakeAdo(["Epic", "Issue", "Task"])  # template Basic: sin Feature

    with patch.object(tickets, "_provider_for_ticket", return_value=None):
        with patch.object(tickets, "_epic_decomposition_enabled", return_value=True):
            result = publish_epic_children(
                epic_ado_id=100, children_plan=plan, project_name="p", ado=fake_ado,
            )

    assert fake_ado.created_types == ["Issue"]  # Feature mapeado a Issue; VS402323 irreproducible
    assert result.warnings  # warning no vacío


# ── Endpoint create_epic_children: 207 pérdida parcial / 200 ok ────────────────

def _make_tickets_client():
    from flask import Flask, Blueprint
    from api.tickets import bp as tickets_bp
    app = Flask(__name__)
    parent = Blueprint("api", __name__, url_prefix="/api")
    parent.register_blueprint(tickets_bp)
    app.register_blueprint(parent)
    return app.test_client()


def test_endpoint_207_con_perdida_parcial():
    from api import tickets
    from api.tickets import _ChildrenPublishResult

    preview = MagicMock()
    preview.ok = True
    preview.html = "<h2>x</h2>"
    result = _ChildrenPublishResult(
        created_ids=[1], reused_ids=[], error="task_under_feature_rejected: boom",
        warnings=["el template no define Feature"],
    )
    client = _make_tickets_client()
    with patch.object(tickets, "_epic_decomposition_enabled", return_value=True):
        with patch.object(tickets, "build_epic_payload_preview", return_value=preview):
            with patch.object(tickets, "build_epic_children_plan", return_value=MagicMock()):
                with patch.object(tickets, "publish_epic_children", return_value=result):
                    resp = client.post("/api/tickets/epic-children",
                                       json={"epic_ado_id": 100, "output": "x"})

    assert resp.status_code == 207
    body = resp.get_json()
    assert body["error"]
    assert body["warnings"]


def test_endpoint_200_sin_error():
    from api import tickets
    from api.tickets import _ChildrenPublishResult

    preview = MagicMock()
    preview.ok = True
    preview.html = "<h2>x</h2>"
    result = _ChildrenPublishResult(created_ids=[1, 2], reused_ids=[], error=None, warnings=[])
    client = _make_tickets_client()
    with patch.object(tickets, "_epic_decomposition_enabled", return_value=True):
        with patch.object(tickets, "build_epic_payload_preview", return_value=preview):
            with patch.object(tickets, "build_epic_children_plan", return_value=MagicMock()):
                with patch.object(tickets, "publish_epic_children", return_value=result):
                    resp = client.post("/api/tickets/epic-children",
                                       json={"epic_ado_id": 100, "output": "x"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["error"] is None
    assert body["warnings"] == []
