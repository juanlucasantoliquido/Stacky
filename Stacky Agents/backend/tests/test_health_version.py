"""A1 — Tests para GET /api/diag/health incluya campo version."""
from __future__ import annotations

import pytest
from unittest.mock import patch


@pytest.fixture()
def client():
    from app import create_app
    app = create_app()
    with app.test_client() as c:
        yield c


def test_health_includes_version_field(client):
    """El endpoint /api/diag/health debe incluir el campo 'version'."""
    with patch("api.diag.get_app_version", return_value="1.0.0"):
        resp = client.get("/api/diag/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "version" in data


def test_health_version_matches_helper(client):
    """El campo version del health coincide con get_app_version()."""
    with patch("api.diag.get_app_version", return_value="2.5.0"):
        resp = client.get("/api/diag/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("version") == "2.5.0"


def test_health_other_fields_intact(client):
    """Los campos ok y healthy siguen presentes junto a version."""
    with patch("api.diag.get_app_version", return_value="0.0.0-test"):
        resp = client.get("/api/diag/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "ok" in data
    assert "healthy" in data
    assert "version" in data
