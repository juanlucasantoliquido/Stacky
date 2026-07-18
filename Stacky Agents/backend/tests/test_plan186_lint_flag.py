"""tests/test_plan186_lint_flag.py — Plan 186 F0.

Wiring vertical slice: FlagSpec declarada (bool, default ON, requires panel 87),
pertenencia a _CURATED_DEFAULTS_ON, y endpoint POST /api/devops/pipeline-lint/validate
guardado por la flag (404 OFF / 200 vacío ON / 400 payload inválido).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

FLAG = "STACKY_DEVOPS_PIPELINE_LINT_ENABLED"


def _spec():
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == FLAG), None)


def test_flag_declarada_bool_default_on():
    spec = _spec()
    assert spec is not None, f"FlagSpec {FLAG} no está en el registry"
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_flag_en_curated_defaults_on():
    # La vía canónica del default ON es la pertenencia al set curado.
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert FLAG in _CURATED_DEFAULTS_ON


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, FLAG, False)
    cfg.config.STACKY_DEVOPS_PIPELINE_LINT_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PIPELINE_LINT_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, FLAG, False)
    cfg.config.STACKY_DEVOPS_PIPELINE_LINT_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PIPELINE_LINT_ENABLED = original


def test_endpoint_404_flag_off(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.post("/api/devops/pipeline-lint/validate",
                       json={"source": "ado", "yaml": "stages: []\n"})
    assert resp.status_code == 404


def test_endpoint_200_reporte_vacio_flag_on(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.post("/api/devops/pipeline-lint/validate",
                       json={"source": "ado", "yaml": "stages: []\n"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["findings"] == []
    assert data["engine_version"] == "186.1"
    assert data["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_endpoint_400_payload_invalido(app_flag_on):
    client = app_flag_on.test_client()
    # Sin source
    r1 = client.post("/api/devops/pipeline-lint/validate", json={"yaml": "x: y\n"})
    assert r1.status_code == 400
    # Sin yaml
    r2 = client.post("/api/devops/pipeline-lint/validate", json={"source": "ado"})
    assert r2.status_code == 400
    # source inválido (C8)
    r3 = client.post("/api/devops/pipeline-lint/validate",
                     json={"source": "github", "yaml": "x: y\n"})
    assert r3.status_code == 400
