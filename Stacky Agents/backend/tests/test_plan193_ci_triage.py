"""Plan 193 F0 — Triage de fallos CI: jobs fallidos + log inline enmascarado (read-only).

Tests (TDD, por archivo — gotcha reload de config):
  - flag declarada bool default ON + requires edge + curada.
  - ambos endpoints 404 con flag OFF.
  - failed-jobs: passthrough del puerto 96 + provider en la respuesta.
  - KPI-1: cap 200K del tail + truncated + chars_total pre-mask.
  - KPI-2: el masking corre ANTES del tail (orden) sobre el texto COMPLETO.
  - log corto: sin truncar, completo.
  - KPI-4: TrackerConfigError → 400; TrackerApiError(404) → 404 (nunca 500 crudo).
  - KPI-3: LOGS_PORT_METHODS congelado.

El provider real se reemplaza por un FAKE monkeypatcheando
services.ci_logs_provider.get_ci_logs_provider (los routes lo importan per-request).
"""
from __future__ import annotations

import pytest

import config
import services.ci_logs_provider as ci_logs_provider
from services.secret_masking import MASK_PLACEHOLDER
from services.tracker_provider import TrackerApiError, TrackerConfigError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


class _FakeProvider:
    """CILogsProvider fake: 2 métodos + name; comportamiento inyectable."""

    def __init__(self, name="fake", jobs=None, log="", raise_on_jobs=None, raise_on_log=None):
        self.name = name
        self._jobs = jobs if jobs is not None else []
        self._log = log
        self._raise_on_jobs = raise_on_jobs
        self._raise_on_log = raise_on_log

    def list_failed_jobs(self, pipeline_id):
        if self._raise_on_jobs is not None:
            raise self._raise_on_jobs
        return self._jobs

    def get_job_log(self, job_id):
        if self._raise_on_log is not None:
            raise self._raise_on_log
        return self._log


def _patch_provider(monkeypatch, provider=None, factory_raises=None):
    """Reemplaza la fábrica get_ci_logs_provider por una que devuelve `provider`
    (o lanza `factory_raises`). El route la importa per-request → el patch aplica."""
    def _factory(project=None):
        if factory_raises is not None:
            raise factory_raises
        return provider
    monkeypatch.setattr(ci_logs_provider, "get_ci_logs_provider", _factory)


def _enable(monkeypatch, value=True):
    monkeypatch.setattr(config.config, "STACKY_CI_FAILURE_TRIAGE_ENABLED", value)


# ---------------------------------------------------------------------------
# Flag
# ---------------------------------------------------------------------------

def test_flag_declarada_bool_default_on():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert "STACKY_CI_FAILURE_TRIAGE_ENABLED" in by_key
    spec = by_key["STACKY_CI_FAILURE_TRIAGE_ENABLED"]
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_PIPELINE_TRIGGER_ENABLED"


def test_flag_en_curated_defaults_on():
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known

    spec = {s.key: s for s in FLAG_REGISTRY}["STACKY_CI_FAILURE_TRIAGE_ENABLED"]
    assert declared_default(spec) is True
    assert default_is_known(spec) is True


# ---------------------------------------------------------------------------
# Guards de flag
# ---------------------------------------------------------------------------

def test_endpoints_404_flag_off(client, monkeypatch):
    _enable(monkeypatch, False)
    _patch_provider(monkeypatch, _FakeProvider())
    assert client.get("/api/ci/proj/pipeline/5/failed-jobs").status_code == 404
    assert client.get("/api/ci/proj/job/9/log").status_code == 404


# ---------------------------------------------------------------------------
# failed-jobs
# ---------------------------------------------------------------------------

def test_failed_jobs_shape(client, monkeypatch):
    jobs = [
        {"job_id": "1", "name": "build", "stage": "ci", "web_url": "http://x/1"},
        {"job_id": "2", "name": "test", "stage": "ci", "web_url": None},
    ]
    _enable(monkeypatch)
    _patch_provider(monkeypatch, _FakeProvider(name="ado", jobs=jobs))
    resp = client.get("/api/ci/proj/pipeline/5/failed-jobs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jobs"] == jobs
    assert body["provider"] == "ado"


# ---------------------------------------------------------------------------
# log — tail + masking
# ---------------------------------------------------------------------------

def test_kpi1_tail_200k(client, monkeypatch):
    _enable(monkeypatch)
    _patch_provider(monkeypatch, _FakeProvider(log="z" * 1_000_000))
    resp = client.get("/api/ci/proj/job/9/log")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["log"]) <= 200_000
    assert body["truncated"] is True
    assert body["chars_total"] == 1_000_000
    assert body["provider"] == "fake"


def test_kpi2_masking_pre_tail(client, monkeypatch):
    # Token (literal PARTIDO — gotcha push-protection) dentro del tail de un log de 300K.
    token = "ghp_" + "x" * 20
    text = ("a" * 250_000) + token + ("b" * 50_000)  # total 300024; token en el tail
    _enable(monkeypatch)
    _patch_provider(monkeypatch, _FakeProvider(log=text))
    resp = client.get("/api/ci/proj/job/9/log")
    body = resp.get_json()
    assert body["truncated"] is True
    assert body["chars_total"] == len(text)
    assert len(body["log"]) <= 200_000
    assert token not in body["log"]
    assert "ghp_" not in body["log"]
    assert "x" not in body["log"]  # filler es 'a'/'b'; ninguna x del token sobrevive
    assert MASK_PLACEHOLDER in body["log"]


def test_kpi2_masking_orden_straddle():
    # Directo sobre el helper con max_chars chico: el token se parte en el corte del tail.
    # Si el masking corriera DESPUÉS del tail, el prefijo 'ghp_' quedaría cortado y las
    # 'x' sobrantes escaparían. Con el orden correcto (mask→tail) no sobrevive ninguna 'x'.
    from services.ci_log_view import tail_and_mask

    token = "ghp_" + "x" * 20
    text = ("a" * 90) + token + ("b" * 90)
    out = tail_and_mask(text, max_chars=100)
    assert out["truncated"] is True
    assert out["chars_total"] == len(text)
    assert "x" not in out["log"]
    assert token not in out["log"]


def test_log_corto_sin_truncar(client, monkeypatch):
    _enable(monkeypatch)
    _patch_provider(monkeypatch, _FakeProvider(log="linea 1\nlinea 2"))
    body = client.get("/api/ci/proj/job/9/log").get_json()
    assert body["truncated"] is False
    assert body["log"] == "linea 1\nlinea 2"
    assert body["chars_total"] == len("linea 1\nlinea 2")


# ---------------------------------------------------------------------------
# KPI-4 — mapeo de errores (nunca 500 crudo)
# ---------------------------------------------------------------------------

def test_kpi4_tracker_config_error_400(client, monkeypatch):
    _enable(monkeypatch)
    _patch_provider(monkeypatch, factory_raises=TrackerConfigError("tracker sin CILogsProvider"))
    resp = client.get("/api/ci/proj/pipeline/5/failed-jobs")
    assert resp.status_code == 400
    assert "tracker sin CILogsProvider" in resp.get_json()["error"]


def test_kpi4_tracker_api_error_status(client, monkeypatch):
    _enable(monkeypatch)
    err = TrackerApiError(404, "pipeline no existe", kind="not_found")
    _patch_provider(monkeypatch, _FakeProvider(raise_on_jobs=err))
    resp = client.get("/api/ci/proj/pipeline/5/failed-jobs")
    assert resp.status_code == 404
    assert "pipeline no existe" in resp.get_json()["error"]


def test_kpi4_log_tracker_api_error_status(client, monkeypatch):
    _enable(monkeypatch)
    err = TrackerApiError(403, "sin scope", kind="forbidden")
    _patch_provider(monkeypatch, _FakeProvider(raise_on_log=err))
    resp = client.get("/api/ci/proj/job/9/log")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# KPI-3 — puerto congelado
# ---------------------------------------------------------------------------

def test_kpi3_puerto_congelado():
    from services.ci_logs_provider import LOGS_PORT_METHODS

    assert LOGS_PORT_METHODS == ("list_failed_jobs", "get_job_log")
