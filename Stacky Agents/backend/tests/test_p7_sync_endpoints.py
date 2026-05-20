"""
Tests para endpoints de P7: rate limiting, sync status extendido, config frontend.

Capa: integration (Flask test client).
"""
from __future__ import annotations

import time
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente de test Flask con BD en memoria."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("STACKY_TICKET_SYNC_INTERVAL_MS", "45000")
    monkeypatch.setenv("STACKY_SYNC_MIN_INTERVAL_SEC", "15")
    monkeypatch.setenv("STACKY_STALE_THRESHOLD_SEC", "120")

    import sys
    import os
    backend_dir = os.path.join(os.path.dirname(__file__), "..")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    # Reset estado global del rate limiter antes de cada test
    import api.tickets as tickets_api
    tickets_api._last_sync_ts = 0.0
    tickets_api._sync_in_progress = False

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as c:
        yield c


def test_frontend_config_endpoint(client):
    """GET /api/tickets/config/frontend devuelve los campos esperados."""
    resp = client.get("/api/tickets/config/frontend")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "ticket_sync_interval_ms" in data
    assert "sync_min_interval_sec" in data
    assert "stale_threshold_sec" in data
    assert data["ticket_sync_interval_ms"] == 45000
    assert data["sync_min_interval_sec"] == 15


def test_sync_status_v2_returns_required_fields(client):
    """GET /api/tickets/sync/status-v2 devuelve todos los campos del contrato."""
    resp = client.get("/api/tickets/sync/status-v2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "last_synced_at" in data
    assert "seconds_since_sync" in data
    assert "is_stale" in data
    assert "stale_threshold_sec" in data
    assert "sync_in_progress" in data
    assert data["stale_threshold_sec"] == 120


def test_rate_limit_blocks_rapid_syncs(client, monkeypatch):
    """Segundo sync dentro del minimo de 15s devuelve 429."""
    # Mockear sync_tickets para que no llame a ADO real
    def mock_sync():
        return {"project": "test", "fetched": 0, "created": 0, "updated": 0,
                "removed": 0, "synced_at": "2026-05-19T12:00:00"}

    monkeypatch.setattr("api.tickets.sync_tickets", mock_sync)

    # Primer sync: debe pasar
    resp1 = client.post("/api/tickets/sync-v2")
    # Si el sync funciona, debe ser 200; si falla por config es 400/502
    # Lo que importa es que el segundo sea 429

    # Forzar timestamp reciente para simular que ya se hizo un sync hace poco
    import api.tickets as tickets_api
    tickets_api._last_sync_ts = time.time() - 5  # hace 5 segundos

    resp2 = client.post("/api/tickets/sync-v2")
    assert resp2.status_code == 429
    data = resp2.get_json()
    assert data["ok"] is False
    assert data["error"] == "rate_limited"
    assert "retry_after_sec" in data
    assert data["retry_after_sec"] > 0
