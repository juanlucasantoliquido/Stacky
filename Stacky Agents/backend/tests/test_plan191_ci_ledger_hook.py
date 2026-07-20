"""Plan 191 F1 — Hook best-effort del productor en el trigger + desenlace en el monitor.

Rieles verificados:
  - KPI-1: trigger exitoso persiste 1 entry (source="stacky"); ledger OFF → 0; append roto
    NO cambia la respuesta HTTP del trigger (best-effort total).
  - Trigger fallido → 0 entries; confirm sigue obligatorio (no-regresión HITL).
  - KPI-6 (ADICIÓN): monitor con estado final → last_status/finished_at; estado no-final o id
    desconocido → entry intacto y monitor sin cambios de respuesta.

Estilo espejado de tests/test_plan72_trigger_endpoint.py (Flask test client + provider mock).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import config
import runtime_paths


@pytest.fixture()
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture()
def app():
    from app import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_stores():
    import api.ci as ci_mod
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()
    yield
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()


def _mock_provider(tracker_type: str = "gitlab") -> MagicMock:
    mock = MagicMock()
    mock.name = tracker_type
    mock.trigger_pipeline.return_value = {
        "id": "42",
        "status": "created",
        "ref": "develop",
        "sha": "abc123",
        "web_url": "http://gitlab/p/42",
    }
    return mock


def _both_flags_on(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", True)


# ---------------------------------------------------------------------------
# KPI-1 — productor
# ---------------------------------------------------------------------------

def test_kpi1_trigger_exitoso_persiste(client, monkeypatch, _tmp_data_dir):
    _both_flags_on(monkeypatch)
    provider = _mock_provider("gitlab")
    with patch("api.ci.get_ci_provider", return_value=provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "newsha",
        })
    assert resp.status_code == 200

    from services.ci_run_ledger import list_runs
    runs = list_runs()
    assert len(runs) == 1
    entry = runs[0]
    assert entry["pipeline_id"] == "42"
    assert entry["ref"] == "develop"
    assert entry["project"] == "myproject"
    assert entry["tracker_type"] == "gitlab"
    assert entry["source"] == "stacky"
    assert entry["web_url"] == "http://gitlab/p/42"
    assert entry["last_status"] is None
    assert entry["finished_at"] is None


def test_kpi1_ledger_off_no_persiste(client, monkeypatch, _tmp_data_dir):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False)
    provider = _mock_provider("gitlab")
    with patch("api.ci.get_ci_provider", return_value=provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "newsha",
        })
    assert resp.status_code == 200
    assert resp.get_json()["id"] == "42"

    from services.ci_run_ledger import list_runs
    assert list_runs() == []


def test_kpi1_append_roto_no_rompe_trigger(client, monkeypatch, _tmp_data_dir):
    _both_flags_on(monkeypatch)
    provider = _mock_provider("gitlab")

    import api.ci as ci_mod

    # Respuesta de referencia SIN excepción del ledger.
    with patch("api.ci.get_ci_provider", return_value=provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        ref_resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "sha-ref",
        })
    ref_status, ref_body = ref_resp.status_code, ref_resp.get_json()

    # Limpiar idempotencia para que el 2do trigger DISPARE de nuevo (mismo ref/sha),
    # así ambos recorridos alcanzan el hook y las respuestas son comparables.
    ci_mod._RECENT_TRIGGERS.clear()

    # Ahora con append_run explotando: la respuesta HTTP debe ser IDÉNTICA.
    def _boom(*a, **k):
        raise RuntimeError("ledger caido")

    with patch("api.ci.get_ci_provider", return_value=provider), \
         patch("api.ci._read_pat_scopes", return_value=None), \
         patch("services.ci_run_ledger.append_run", _boom):
        broken_resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "sha-ref",
        })
    assert broken_resp.status_code == ref_status
    assert broken_resp.get_json() == ref_body


def test_trigger_fallido_no_persiste(client, monkeypatch, _tmp_data_dir):
    from services.tracker_provider import TrackerApiError
    _both_flags_on(monkeypatch)
    provider = _mock_provider("gitlab")
    provider.trigger_pipeline.side_effect = TrackerApiError(403, "forbidden", kind="forbidden")
    with patch("api.ci.get_ci_provider", return_value=provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "main", "sha": "err-sha",
        })
    assert resp.status_code == 403
    from services.ci_run_ledger import list_runs
    assert list_runs() == []


def test_confirm_sigue_obligatorio(client, monkeypatch, _tmp_data_dir):
    _both_flags_on(monkeypatch)
    resp = client.post("/api/ci/myproject/trigger", json={"ref": "develop"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# KPI-6 — desenlace persistido (monitor)
# ---------------------------------------------------------------------------

def _seed_entry(pipeline_id: str = "77"):
    from services.ci_run_ledger import append_run
    append_run({
        "project": "myproject", "tracker_type": "gitlab", "ref": "develop",
        "sha": "s", "pipeline_id": pipeline_id, "web_url": None,
        "triggered_at": "2024-01-01T00:00:00+00:00", "source": "stacky",
    })


def test_monitor_final_actualiza_ledger(client, monkeypatch, _tmp_data_dir):
    _both_flags_on(monkeypatch)
    _seed_entry("77")
    provider = _mock_provider("gitlab")
    provider.monitor_pipeline.return_value = {
        "id": "77", "status": "success", "ref": "develop", "web_url": "http://x/77",
    }
    with patch("api.ci.get_ci_provider", return_value=provider):
        resp = client.get("/api/ci/myproject/pipeline/77")
    assert resp.status_code == 200

    from services.ci_run_ledger import list_runs
    entry = [r for r in list_runs() if r["pipeline_id"] == "77"][0]
    assert entry["last_status"] == "success"
    assert entry["finished_at"] is not None


def test_monitor_no_final_no_actualiza(client, monkeypatch, _tmp_data_dir):
    _both_flags_on(monkeypatch)
    _seed_entry("88")
    provider = _mock_provider("gitlab")
    provider.monitor_pipeline.return_value = {
        "id": "88", "status": "running", "ref": "develop", "web_url": None,
    }
    with patch("api.ci.get_ci_provider", return_value=provider):
        resp = client.get("/api/ci/myproject/pipeline/88")
    assert resp.status_code == 200

    from services.ci_run_ledger import list_runs
    entry = [r for r in list_runs() if r["pipeline_id"] == "88"][0]
    assert entry["last_status"] is None
    assert entry["finished_at"] is None


def test_monitor_id_desconocido_noop(client, monkeypatch, _tmp_data_dir):
    _both_flags_on(monkeypatch)
    # sin entry para "999"
    provider = _mock_provider("gitlab")
    provider.monitor_pipeline.return_value = {
        "id": "999", "status": "failed", "ref": "develop", "web_url": None,
    }
    with patch("api.ci.get_ci_provider", return_value=provider):
        resp = client.get("/api/ci/myproject/pipeline/999")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "failed"

    from services.ci_run_ledger import list_runs
    assert list_runs() == []
