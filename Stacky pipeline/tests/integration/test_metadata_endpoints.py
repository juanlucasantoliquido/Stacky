"""
Tests de endpoints de metadata en dashboard_server.
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from dashboard_server import app
from ticket_metadata_store import get_store, reset_singleton_for_tests


@pytest.fixture(autouse=True)
def _reset_singletons(tmp_path, monkeypatch):
    """Reset de singletons antes de cada test."""
    import ticket_metadata_store
    monkeypatch.setattr(ticket_metadata_store, "_DATA_DIR", tmp_path / "data")
    reset_singleton_for_tests()
    yield
    reset_singleton_for_tests()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client."""
    import ticket_metadata_store
    monkeypatch.setattr(ticket_metadata_store, "_DATA_DIR", tmp_path / "data")
    app.config["TESTING"] = True
    with app.test_client() as cli:
        yield cli


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Fixture del store."""
    import ticket_metadata_store
    monkeypatch.setattr(ticket_metadata_store, "_DATA_DIR", tmp_path / "data")
    return get_store()


class TestMetadataEndpoints:
    """Tests de los endpoints de metadata."""

    def test_get_metadata_not_found(self, client):
        """GET /api/tickets/<id>/metadata con ticket inexistente → 404."""
        resp = client.get("/api/tickets/nonexistent/metadata")
        assert resp.status_code == 404

    def test_get_metadata_empty(self, client, store):
        """GET /api/tickets/<id>/metadata con ticket inexistente."""
        # No crear nada en el store
        resp = client.get("/api/tickets/999999/metadata")
        assert resp.status_code == 404  # Sin metadata = 404

    def test_patch_color_valid(self, client, store):
        """PATCH /api/tickets/<id>/color con color válido."""
        ticket_id = "123456"
        resp = client.patch(
            f"/api/tickets/{ticket_id}/color",
            json={"color": "#ff00aa"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["ticket_id"] == ticket_id
        assert data["color"] == "#ff00aa"

        # Verificar que se persistió en el store
        meta = store.get(ticket_id)
        assert meta is not None
        assert meta.color.hex == "#ff00aa"

    def test_patch_color_invalid_hex(self, client):
        """PATCH /api/tickets/<id>/color con hex inválido."""
        resp = client.patch(
            "/api/tickets/123456/color",
            json={"color": "notahex"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_patch_color_clear(self, client, store):
        """PATCH /api/tickets/<id>/color con color=null → borrar color."""
        ticket_id = "123456"
        # Primero set un color
        store.set_color(ticket_id, "#ff0000")
        assert store.get(ticket_id).color.hex == "#ff0000"

        # Luego borrar
        resp = client.patch(
            f"/api/tickets/{ticket_id}/color",
            json={"color": None},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["color"] is None

    def test_post_user_tag_valid(self, client, store):
        """POST /api/tickets/<id>/user_tags con tag válido."""
        ticket_id = "123456"
        resp = client.post(
            f"/api/tickets/{ticket_id}/user_tags",
            json={"tag": "urgente"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "urgente" in data["user_tags"]

    def test_post_user_tag_invalid(self, client):
        """POST /api/tickets/<id>/user_tags con tag inválido."""
        resp = client.post(
            "/api/tickets/333333/user_tags",
            json={"tag": "invalid tag with spaces"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_user_tag_dedup(self, client, store):
        """POST /api/tickets/<id>/user_tags no agrega duplicados."""
        ticket_id = "111111"
        store.add_user_tag(ticket_id, "urgente")
        assert len(store.get(ticket_id).user_tags.tags) == 1

        # Intentar agregar el mismo tag
        resp = client.post(
            f"/api/tickets/{ticket_id}/user_tags",
            json={"tag": "urgente"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_tags"].count("urgente") == 1

    def test_put_user_tags_replace(self, client, store):
        """PUT /api/tickets/<id>/user_tags reemplaza la lista."""
        ticket_id = "123456"
        store.add_user_tag(ticket_id, "old1")
        store.add_user_tag(ticket_id, "old2")

        resp = client.put(
            f"/api/tickets/{ticket_id}/user_tags",
            json={"tags": ["new1", "new2"]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data["user_tags"]) == {"new1", "new2"}

    def test_delete_user_tag(self, client, store):
        """DELETE /api/tickets/<id>/user_tags/<tag>."""
        ticket_id = "222222"
        store.add_user_tag(ticket_id, "urgente")
        store.add_user_tag(ticket_id, "refactor")
        assert len(store.get(ticket_id).user_tags.tags) == 2

        resp = client.delete(f"/api/tickets/{ticket_id}/user_tags/urgente")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "urgente" not in data["user_tags"]
        assert "refactor" in data["user_tags"]

    def test_delete_user_tag_not_found(self, client, store):
        """DELETE /api/tickets/<id>/user_tags/<tag> con tag inexistente → 404."""
        ticket_id = "123456"
        resp = client.delete(f"/api/tickets/{ticket_id}/user_tags/nonexistent")
        assert resp.status_code == 404

    def test_get_metadata_summary_basic(self, client, store):
        """GET /api/tickets/metadata/summary."""
        # Crear algunos tickets con metadata
        store.set_color("123", "#ff0000")
        store.add_user_tag("123", "urgente")
        store.set_color("124", "#00ff00")
        store.add_user_tag("124", "refactor")
        store.add_user_tag("124", "db")

        resp = client.get("/api/tickets/metadata/summary?group_by=color,user_tags")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] >= 2
        assert "per_color" in data
        assert "per_user_tag" in data

    def test_get_metadata_summary_with_groupby(self, client, store):
        """GET /api/tickets/metadata/summary?group_by=user_tags."""
        store.add_user_tag("123", "urgente")
        store.add_user_tag("123", "refactor")
        store.add_user_tag("124", "urgente")

        resp = client.get("/api/tickets/metadata/summary?group_by=user_tags")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "per_user_tag" in data
        assert data["per_user_tag"].get("urgente", {}).get("count", 0) >= 2

    def test_post_color_case_insensitive(self, client, store):
        """PATCH color normaliza hex a lowercase."""
        resp = client.patch(
            "/api/tickets/123456/color",
            json={"color": "#FF00AA"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["color"] == "#ff00aa"

    def test_concurrent_color_updates(self, client, store):
        """Test que múltiples PATCHes concurrentes no rompen el store."""
        ticket_id = "123456"
        import threading

        def patch_color(color_hex):
            client.patch(
                f"/api/tickets/{ticket_id}/color",
                json={"color": color_hex},
                content_type="application/json",
            )

        threads = [
            threading.Thread(target=patch_color, args=(f"#ff{i:02x}00",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # El store debe estar consistente
        meta = store.get(ticket_id)
        assert meta is not None
        assert meta.color is not None
        assert meta.color.hex.startswith("#")
