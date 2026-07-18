"""tests/test_plan186_explain_plan.py — Plan 186 F4.

explain_plan: simulación del orden de ejecución (fases topológicas, C2).
KPI-4: diamante de stages + jobs paralelos por default.
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

from services.pipeline_lint import explain_plan  # noqa: E402

FLAG = "STACKY_DEVOPS_PIPELINE_LINT_ENABLED"


def _phase_names(plan):
    return [[n.name for n in phase] for phase in plan.phases]


def test_kpi4_diamante_stages_ado():
    y = (
        "stages:\n"
        "- stage: A\n  jobs:\n  - job: JA\n    steps:\n    - script: echo a\n"
        "- stage: B\n  dependsOn: A\n  jobs:\n  - job: JB\n    steps:\n    - script: echo b\n"
        "- stage: C\n  dependsOn: A\n  jobs:\n  - job: JC\n    steps:\n    - script: echo c\n"
        "- stage: D\n  dependsOn:\n  - B\n  - C\n  jobs:\n  - job: JD\n    steps:\n    - script: echo d\n"
    )
    plan = explain_plan(y, "ado")
    assert plan.ok is True
    assert _phase_names(plan) == [["A"], ["B", "C"], ["D"]]


def test_kpi4_jobs_ado_paralelos_sin_dependson():
    # pipeline jobs-only: J1 y J2 sin dependsOn → paralelos (C2), misma fase.
    y = (
        "jobs:\n"
        "- job: J1\n  steps:\n  - script: echo 1\n"
        "- job: J2\n  steps:\n  - script: echo 2\n"
    )
    plan = explain_plan(y, "ado")
    assert plan.ok is True
    assert _phase_names(plan) == [["J1", "J2"]]
    assert all(n.kind == "job" for n in plan.phases[0])


def test_deployment_job_aparece_en_plan():
    y = (
        "jobs:\n"
        "- deployment: DeployX\n"
        "  strategy:\n    runOnce:\n      deploy:\n        steps:\n        - script: echo hi\n"
    )
    plan = explain_plan(y, "ado")
    assert plan.ok is True
    node = plan.phases[0][0]
    assert node.kind == "job"
    assert node.name == "DeployX"


def test_gitlab_stages_y_needs():
    y = (
        "stages:\n- s1\n- s2\n- s3\n"
        "j1:\n  stage: s1\n  script:\n  - echo 1\n"
        "jx:\n  stage: s3\n  needs:\n  - j1\n  script:\n  - echo x\n"
    )
    plan = explain_plan(y, "gitlab")
    assert plan.ok is True
    names = _phase_names(plan)
    assert names[0] == ["j1"]
    assert names[1] == ["jx"]  # needs del stage 1 → fase 2


def test_ciclo_ok_false():
    y = (
        "stages:\n"
        "- stage: A\n  dependsOn: B\n  jobs:\n  - job: JA\n    steps:\n    - script: echo a\n"
        "- stage: B\n  dependsOn: A\n  jobs:\n  - job: JB\n    steps:\n    - script: echo b\n"
    )
    plan = explain_plan(y, "ado")
    assert plan.ok is False
    assert plan.phases == ()


def test_vars_literales_resueltas():
    y = (
        "variables:\n  LITERAL: hello\n  COMPUESTA: $(LITERAL)x\n"
        "stages:\n- stage: A\n  jobs:\n  - job: J\n    steps:\n    - script: echo hi\n"
    )
    plan = explain_plan(y, "ado")
    rv = plan.phases[0][0].resolved_vars
    assert rv["LITERAL"] == "hello"
    assert rv["COMPUESTA"] == "<dinámica>"


def test_condicional_warning():
    y = (
        "stages:\n- stage: A\n  condition: eq(1,1)\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo hi\n"
    )
    plan = explain_plan(y, "ado")
    assert any("condicional" in w for w in plan.phases[0][0].warnings)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@pytest.fixture
def _client(request):
    import config as cfg
    val = request.param
    original = getattr(cfg.config, FLAG, False)
    cfg.config.STACKY_DEVOPS_PIPELINE_LINT_ENABLED = val
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    cfg.config.STACKY_DEVOPS_PIPELINE_LINT_ENABLED = original


@pytest.mark.parametrize("_client", [False], indirect=True)
def test_endpoint_explain_404_off(_client):
    r = _client.post("/api/devops/pipeline-lint/explain",
                     json={"source": "ado", "yaml": "stages: []\n"})
    assert r.status_code == 404


@pytest.mark.parametrize("_client", [True], indirect=True)
def test_endpoint_explain_200_on(_client):
    r = _client.post("/api/devops/pipeline-lint/explain",
                     json={"source": "ado", "yaml": "jobs:\n- job: J1\n  steps:\n  - script: echo 1\n"})
    assert r.status_code == 200
    data = r.get_json()
    assert "plan" in data
    assert data["plan"]["ok"] is True
    assert data["plan"]["provider"] == "ado"
    # payload inválido → 400
    r2 = _client.post("/api/devops/pipeline-lint/explain", json={"source": "github", "yaml": "x: y\n"})
    assert r2.status_code == 400
