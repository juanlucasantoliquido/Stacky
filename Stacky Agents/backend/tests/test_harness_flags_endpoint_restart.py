"""
Tests F2 del Plan 84 — PUT honesto: restart_required_keys en la respuesta.

Tests monkeypatchean _ENV_PATH obligatoriamente para NO escribir el .env vivo.
"""

import os
import sys
import pytest
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api import harness_flags


def test_put_normal_flag_returns_empty_restart_keys(tmp_path, monkeypatch):
    """PUT de una flag no-startup → restart_required_keys == []."""
    # Monkeypatchear _ENV_PATH OBLIGATORIAMENTE
    monkeypatch.setattr(harness_flags, "_ENV_PATH", tmp_path / ".env")

    # Crear cliente Flask
    import app
    flask_app = app.create_app()
    client = flask_app.test_client()

    # PUT de una flag normal (STACKY_MAX_CONCURRENT_RUNS)
    response = client.put("/api/harness-flags", json={
        "updates": {"STACKY_MAX_CONCURRENT_RUNS": 4}
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["restart_required_keys"] == []


def test_put_startup_flag_returns_key(tmp_path, monkeypatch):
    """PUT de STACKY_DIGEST_INTERVAL_HOURS → restart_required_keys tiene la key."""
    monkeypatch.setattr(harness_flags, "_ENV_PATH", tmp_path / ".env")

    import app
    flask_app = app.create_app()
    client = flask_app.test_client()

    response = client.put("/api/harness-flags", json={
        "updates": {"STACKY_DIGEST_INTERVAL_HOURS": 2}
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["restart_required_keys"] == ["STACKY_DIGEST_INTERVAL_HOURS"]


def test_put_mixed_returns_only_startup_keys(tmp_path, monkeypatch):
    """PUT con una de cada → solo la startup en la lista."""
    monkeypatch.setattr(harness_flags, "_ENV_PATH", tmp_path / ".env")

    import app
    flask_app = app.create_app()
    client = flask_app.test_client()

    response = client.put("/api/harness-flags", json={
        "updates": {
            "STACKY_MAX_CONCURRENT_RUNS": 8,  # normal
            "STACKY_DIGEST_INTERVAL_HOURS": 3,  # startup
        }
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["restart_required_keys"] == ["STACKY_DIGEST_INTERVAL_HOURS"]
