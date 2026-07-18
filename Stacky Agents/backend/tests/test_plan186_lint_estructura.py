"""tests/test_plan186_lint_estructura.py — Plan 186 F1.

Motor de reglas + reglas estructurales PL001..PL006 (semántica C1/C2).
Corpus INLINE: 6 ADO rotos + 6 GitLab rotos + válidos + KPI-2/KPI-3.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.pipeline_lint import lint_yaml  # noqa: E402


def _codes(report):
    return [f.code for f in report.findings]


# ── PL001 — YAML no parsea ────────────────────────────────────────────────────

YAML_PL001_ADO = "stages:\n" + "\t- stage: A\n"      # tab ilegal
YAML_PL001_GITLAB = "stages:\n" + "\t- build\n"


def test_pl001_yaml_invalido_ado():
    rep = lint_yaml(YAML_PL001_ADO, "ado")
    assert "PL001" in _codes(rep)
    f = next(x for x in rep.findings if x.code == "PL001")
    assert f.severity == "error"
    assert f.line is not None
    assert rep.counts["error"] >= 1


def test_pl001_yaml_invalido_gitlab():
    rep = lint_yaml(YAML_PL001_GITLAB, "gitlab")
    assert "PL001" in _codes(rep)


# ── PL002 — nombre duplicado ──────────────────────────────────────────────────

YAML_PL002_ADO = (
    "stages:\n"
    "- stage: A\n"
    "  jobs:\n"
    "  - job: J1\n"
    "    steps:\n"
    "    - script: echo hi\n"
    "- stage: A\n"
    "  jobs:\n"
    "  - job: J2\n"
    "    steps:\n"
    "    - script: echo hi\n"
)

YAML_PL002_GITLAB = (
    "stages:\n"
    "- build\n"
    "myjob:\n"
    "  stage: build\n"
    "  script:\n"
    "  - echo a\n"
    "myjob:\n"
    "  stage: build\n"
    "  script:\n"
    "  - echo b\n"
)

YAML_PL002_GITLAB_QUOTED = (
    "stages:\n"
    "- build\n"
    '"mi job":\n'
    "  stage: build\n"
    "  script:\n"
    "  - echo a\n"
    '"mi job":\n'
    "  stage: build\n"
    "  script:\n"
    "  - echo b\n"
)


def test_pl002_stage_duplicado_ado():
    rep = lint_yaml(YAML_PL002_ADO, "ado")
    assert "PL002" in _codes(rep)


def test_pl002_job_duplicado_gitlab():
    rep = lint_yaml(YAML_PL002_GITLAB, "gitlab")
    assert "PL002" in _codes(rep)


def test_pl002_gitlab_clave_quoteada_no_crashea():
    rep = lint_yaml(YAML_PL002_GITLAB_QUOTED, "gitlab")
    # límite documentado C5: claves quoteadas fuera de alcance → cero PL002, cero crash (PL000)
    assert "PL002" not in _codes(rep)
    assert "PL000" not in _codes(rep)


# ── PL003 — dependencia a nodo inexistente ────────────────────────────────────

YAML_PL003_ADO = (
    "stages:\n"
    "- stage: A\n"
    "  dependsOn: Zzz\n"
    "  jobs:\n"
    "  - job: J\n"
    "    steps:\n"
    "    - script: echo hi\n"
)

YAML_PL003_GITLAB = (
    "stages:\n"
    "- build\n"
    "myjob:\n"
    "  stage: build\n"
    "  needs:\n"
    "  - ghost\n"
    "  script:\n"
    "  - echo hi\n"
)


def test_pl003_dependson_roto_ado():
    rep = lint_yaml(YAML_PL003_ADO, "ado")
    assert "PL003" in _codes(rep)


def test_pl003_needs_roto_gitlab():
    rep = lint_yaml(YAML_PL003_GITLAB, "gitlab")
    assert "PL003" in _codes(rep)


# ── PL004 — ciclo de dependencias ─────────────────────────────────────────────

YAML_PL004_ADO = (
    "stages:\n"
    "- stage: A\n"
    "  dependsOn: B\n"
    "  jobs:\n"
    "  - job: JA\n"
    "    steps:\n"
    "    - script: echo a\n"
    "- stage: B\n"
    "  dependsOn: A\n"
    "  jobs:\n"
    "  - job: JB\n"
    "    steps:\n"
    "    - script: echo b\n"
)

YAML_PL004_GITLAB = (
    "stages:\n"
    "- build\n"
    "a:\n"
    "  stage: build\n"
    "  needs:\n"
    "  - b\n"
    "  script:\n"
    "  - echo a\n"
    "b:\n"
    "  stage: build\n"
    "  needs:\n"
    "  - a\n"
    "  script:\n"
    "  - echo b\n"
)


def test_pl004_ciclo_ado():
    rep = lint_yaml(YAML_PL004_ADO, "ado")
    assert "PL004" in _codes(rep)
    # aislado: no debe reportar PL003 (ambos existen)
    assert "PL003" not in _codes(rep)


def test_pl004_ciclo_gitlab():
    rep = lint_yaml(YAML_PL004_GITLAB, "gitlab")
    assert "PL004" in _codes(rep)
    assert "PL003" not in _codes(rep)


# ── PL005 — job sin pasos ejecutables ─────────────────────────────────────────

YAML_PL005_ADO = (
    "stages:\n"
    "- stage: A\n"
    "  jobs:\n"
    "  - job: Empty\n"
)

YAML_PL005_GITLAB = (
    "stages:\n"
    "- build\n"
    "emptyjob:\n"
    "  stage: build\n"
)

YAML_PL005_DEPLOYMENT_ADO = (
    "stages:\n"
    "- stage: A\n"
    "  jobs:\n"
    "  - deployment: DeployX\n"
    "    strategy:\n"
    "      runOnce:\n"
    "        deploy:\n"
    "          steps:\n"
    "          - script: echo hi\n"
)

YAML_PL005_RUN_EXTENDS_GITLAB = (
    "stages:\n"
    "- build\n"
    "job_run:\n"
    "  stage: build\n"
    "  run:\n"
    "  - echo hi\n"
    "job_ext:\n"
    "  extends: .base\n"
)


def test_pl005_job_sin_steps_ado():
    rep = lint_yaml(YAML_PL005_ADO, "ado")
    assert "PL005" in _codes(rep)


def test_pl005_job_sin_script_gitlab():
    rep = lint_yaml(YAML_PL005_GITLAB, "gitlab")
    assert "PL005" in _codes(rep)


def test_pl005_no_flaggea_deployment_ado():
    rep = lint_yaml(YAML_PL005_DEPLOYMENT_ADO, "ado")
    assert "PL005" not in _codes(rep)  # C1


def test_pl005_no_flaggea_run_ni_extends_gitlab():
    rep = lint_yaml(YAML_PL005_RUN_EXTENDS_GITLAB, "gitlab")
    assert "PL005" not in _codes(rep)  # C1


# ── PL006 — clave desconocida en la raíz ──────────────────────────────────────

YAML_PL006_ADO = "stages: []\nweirdkey: 1\n"
YAML_PL006_GITLAB = (
    "stages:\n"
    "- build\n"
    "weirdkey: 1\n"
    "j:\n"
    "  stage: build\n"
    "  script:\n"
    "  - echo hi\n"
)


def test_pl006_clave_desconocida_ambos():
    rep_a = lint_yaml(YAML_PL006_ADO, "ado")
    assert "PL006" in _codes(rep_a)
    rep_g = lint_yaml(YAML_PL006_GITLAB, "gitlab")
    assert "PL006" in _codes(rep_g)


# ── Válidos: cero errores ─────────────────────────────────────────────────────

YAML_VALIDO_ADO = (
    "name: demo\n"
    "trigger:\n"
    "  branches:\n"
    "    include:\n"
    "    - main\n"
    "stages:\n"
    "- stage: Build\n"
    "  jobs:\n"
    "  - job: Compile\n"
    "    steps:\n"
    "    - script: echo build\n"
    "- stage: Deploy\n"
    "  dependsOn: Build\n"
    "  jobs:\n"
    "  - deployment: DeployProd\n"
    "    strategy:\n"
    "      runOnce:\n"
    "        deploy:\n"
    "          steps:\n"
    "          - script: echo deploy\n"
)

YAML_VALIDO_GITLAB = (
    "stages:\n"
    "- build\n"
    "- test\n"
    "build-job:\n"
    "  stage: build\n"
    "  script:\n"
    "  - echo build\n"
    "test-job:\n"
    "  stage: test\n"
    "  needs:\n"
    "  - build-job\n"
    "  script:\n"
    "  - echo test\n"
)


def test_valido_ado_cero_errores():
    rep = lint_yaml(YAML_VALIDO_ADO, "ado")
    assert rep.counts["error"] == 0, _codes(rep)
    assert rep.ok is True


def test_valido_gitlab_cero_errores():
    rep = lint_yaml(YAML_VALIDO_GITLAB, "gitlab")
    assert rep.counts["error"] == 0, _codes(rep)
    assert rep.ok is True


# ── KPI-2 — round-trip de los renderers sin falsos positivos ──────────────────

def _minimal_spec_dict(name):
    return {
        "name": name,
        "stages": [{
            "name": "build",
            "jobs": [{
                "name": "build-job",
                "steps": [{"name": "compile", "script": "echo hello"}],
                "runner_tags": [],
                "variables": {},
                "artifacts": [],
                "services": [],
            }],
        }],
        "variables": {},
        "trigger_branches": [],
    }


def test_kpi2_round_trip_sin_falsos_positivos():
    from services.pipeline_spec import dict_to_spec
    from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml

    spec = dict_to_spec(_minimal_spec_dict("demo"))
    ado_yaml = to_ado_yaml(spec)
    gitlab_yaml = to_gitlab_yaml(spec)

    rep_ado = lint_yaml(ado_yaml, "ado")
    rep_gl = lint_yaml(gitlab_yaml, "gitlab")
    assert rep_ado.counts["error"] == 0, (ado_yaml, _codes(rep_ado))
    assert rep_gl.counts["error"] == 0, (gitlab_yaml, _codes(rep_gl))


# ── KPI-3 — rápido y sin red ──────────────────────────────────────────────────

def test_kpi3_rapido_y_sin_red(monkeypatch):
    import socket

    def _boom(*a, **k):
        raise AssertionError("red prohibida")

    monkeypatch.setattr(socket, "socket", _boom)

    corpus = [
        (YAML_PL002_ADO, "ado"), (YAML_PL002_GITLAB, "gitlab"),
        (YAML_PL003_ADO, "ado"), (YAML_PL003_GITLAB, "gitlab"),
        (YAML_PL004_ADO, "ado"), (YAML_PL004_GITLAB, "gitlab"),
        (YAML_PL005_ADO, "ado"), (YAML_PL005_GITLAB, "gitlab"),
        (YAML_VALIDO_ADO, "ado"), (YAML_VALIDO_GITLAB, "gitlab"),
    ]
    t0 = time.perf_counter()
    for _ in range(5):
        for y, p in corpus:
            lint_yaml(y, p)
    assert (time.perf_counter() - t0) < 0.5


# ── Robustez: una regla que explota no tira 500 ───────────────────────────────

def test_regla_que_explota_no_tira_500():
    import services.pipeline_lint as pl

    def _boom(ctx):
        raise RuntimeError("boom")

    orig = pl._RULES
    pl._RULES = [("PL999", pl.SEV_ERROR, ("ado", "gitlab"), _boom, ("ado", "stages: []\n"))]
    try:
        rep = pl.lint_yaml("stages: []\n", "ado")
        assert "PL000" in [f.code for f in rep.findings]
    finally:
        pl._RULES = orig
